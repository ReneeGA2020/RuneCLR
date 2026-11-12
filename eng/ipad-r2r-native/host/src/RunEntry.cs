using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.Loader;
using System.Text;

public static class ProbeEntry
{
    private const BindingFlags StaticFlags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static;

    private static string Esc(string value)
    {
        if (string.IsNullOrEmpty(value)) return "";
        var builder = new StringBuilder(value.Length + 8);
        foreach (var c in value)
        {
            if (c == '"' || c == '\\') builder.Append('\\').Append(c);
            else if (c == '\n') builder.Append("\\n");
            else if (c == '\r') builder.Append("\\r");
            else if (c == '\t') builder.Append("\\t");
            else if (c < 0x20) builder.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
            else builder.Append(c);
        }
        return builder.ToString();
    }

    private static string Token(string line, string key)
    {
        var at = 0;
        while (true)
        {
            at = line.IndexOf(key + "=", at, StringComparison.Ordinal);
            if (at < 0) return "";
            var start = at + key.Length + 1;
            var end = start;
            while (end < line.Length && line[end] != ' ' && line[end] != '\r') end++;
            return line.Substring(start, end - start);
        }
    }

    private static bool LineStartsWith(string line, string prefix)
    {
        return line.TrimStart().StartsWith(prefix, StringComparison.Ordinal);
    }

    public static int Main()
    {
        var resultPath = Environment.GetEnvironmentVariable("RUNECLR_RESULT_PATH") ?? "";
        var runId = Environment.GetEnvironmentVariable("RUNECLR_RUN_ID") ?? "";
        var expectedVersion = Environment.GetEnvironmentVariable("RUNECLR_EXPECTED_VERSION") ?? "";
        var expectedNonce = Environment.GetEnvironmentVariable("RUNECLR_PROBE_NONCE") ?? "";
        var goldenResult = Environment.GetEnvironmentVariable("RUNECLR_GOLDEN_RESULT") ?? "";
        var goldenPrivate = Environment.GetEnvironmentVariable("RUNECLR_GOLDEN_PRIVATE") ?? "";
        var goldenHelper = Environment.GetEnvironmentVariable("RUNECLR_GOLDEN_HELPER") ?? "";

        var buffer = new StringWriter();
        var original = Console.Out;
        var driverExit = 1;
        var error = "";
        var contractMvid = "";
        var contractFromDefault = false;
        try
        {
            var contract = AssemblyLoadContext.Default.LoadFromAssemblyPath(
                Path.Combine(AppContext.BaseDirectory, "TrustedUpdate.Contract.dll"));
            contractMvid = contract.ManifestModule.ModuleVersionId.ToString();
            contractFromDefault = AssemblyLoadContext.GetLoadContext(contract) == AssemblyLoadContext.Default;
            Console.SetOut(buffer);
            driverExit = string.Equals(Environment.GetEnvironmentVariable("RUNECLR_HOST_MODE"),                "delivery", StringComparison.Ordinal)                ? TrustedUpdate.DeliveryHost.Run()                : TrustedUpdate.Driver.Run();
        }
        catch (Exception failure)
        {
            error = failure.GetType().Name + ": " + failure.Message;
            driverExit = 1;
        }
        finally
        {
            Console.SetOut(original);
        }

        var log = buffer.ToString();
        Console.Write(log);

        var scriptVersion = "";
        var scriptNonce = "";
        var stampFound = false;
        try
        {
            foreach (var alc in AssemblyLoadContext.All)
                foreach (var assembly in alc.Assemblies)
                {
                    if (assembly.GetName().Name != "TrustedUpdate.Update") continue;
                    var stamp = assembly.GetType("RunStamp");
                    if (stamp == null) continue;
                    scriptVersion = (string)(stamp.GetField("Version", StaticFlags)?.GetValue(null) ?? "");
                    scriptNonce = (string)(stamp.GetField("Nonce", StaticFlags)?.GetValue(null) ?? "");
                    stampFound = scriptVersion.Length > 0 && scriptNonce.Length > 0;
                }
        }
        catch (Exception stampError)
        {
            error = (error.Length == 0 ? "" : error + "; ") + "stamp-read-failed: " + stampError.GetType().Name;
        }
        if (!stampFound && error.Length == 0)
            error = "stamp-missing";

        var successLines = log.Split('\n').Where(l => LineStartsWith(l, "TRUSTED_UPDATE_SUCCESS ")).ToList();
        var reflectionLines = log.Split('\n').Where(l => LineStartsWith(l, "HOST_REFLECTION_PRIVATE=")).ToList();
        var successMarker = successLines.Count == 1;
        var observedVersion = "";
        var observedResult = "";
        var observedPrivate = "";
        var observedHelper = "";
        if (successMarker)
        {
            observedVersion = Token(successLines[0], "version");
            observedResult = Token(successLines[0], "result");
            if (reflectionLines.Count == 1)
            {
                observedPrivate = Token(reflectionLines[0], "HOST_REFLECTION_PRIVATE");
                observedHelper = Token(reflectionLines[0], "HOST_REFLECTION_HELPER");
            }
        }
        var ambiguous = successLines.Count > 1 || reflectionLines.Count > 1;

        var nonceMatches = expectedNonce.Length > 0 && scriptNonce == expectedNonce;
        var versionMatches = expectedVersion.Length > 0 && scriptVersion == expectedVersion
                             && (!successMarker || observedVersion == expectedVersion);
        bool goldenMatches = true;
        if (goldenResult.Length > 0 && observedResult != goldenResult) goldenMatches = false;
        if (goldenPrivate.Length > 0 && observedPrivate != goldenPrivate) goldenMatches = false;
        if (goldenHelper.Length > 0 && observedHelper != goldenHelper) goldenMatches = false;

        var fieldsPresent = observedVersion.Length > 0 && observedResult.Length > 0
                            && observedPrivate.Length > 0 && observedHelper.Length > 0;
        var ok = driverExit == 0 && error.Length == 0 && stampFound && nonceMatches && versionMatches
                 && successMarker && !ambiguous && fieldsPresent && goldenMatches && contractFromDefault;
        if (!ok && error.Length == 0)
        {
            if (ambiguous) error = "final-success-ambiguous";
            else if (!successMarker) error = "driver-success-marker-missing";
            else if (!nonceMatches) error = "nonce-mismatch";
            else if (!versionMatches) error = "version-mismatch";
            else if (!fieldsPresent) error = "final-success-fields-missing";
            else if (!goldenMatches) error = "golden-mismatch";
            else if (!contractFromDefault) error = "contract-not-from-default";
        }

        var excerpt = log.Length > 1200 ? log.Substring(0, 1200) : log;
        Func<bool, bool, string> build = (isOk, writeFailed) =>
        {
            var json = new StringBuilder();
            json.Append("{\"schema\":\"runeclr.ipados.r2r.result.v1\"");
            json.Append(",\"runId\":\"").Append(Esc(runId)).Append('"');
            json.Append(",\"expectedVersion\":\"").Append(Esc(expectedVersion)).Append('"');
            json.Append(",\"scriptVersion\":\"").Append(Esc(scriptVersion)).Append('"');
            json.Append(",\"observedVersion\":\"").Append(Esc(observedVersion)).Append('"');
            json.Append(",\"scriptNonce\":\"").Append(Esc(scriptNonce)).Append('"');
            json.Append(",\"nonceMatches\":").Append(nonceMatches ? "true" : "false");
            json.Append(",\"versionMatches\":").Append(versionMatches ? "true" : "false");
            json.Append(",\"goldenMatches\":").Append(goldenMatches ? "true" : "false");
            json.Append(",\"observedResult\":\"").Append(Esc(observedResult)).Append('"');
            json.Append(",\"observedPrivate\":\"").Append(Esc(observedPrivate)).Append('"');
            json.Append(",\"observedHelper\":\"").Append(Esc(observedHelper)).Append('"');
            json.Append(",\"goldenResult\":\"").Append(Esc(goldenResult)).Append('"');
            json.Append(",\"goldenPrivate\":\"").Append(Esc(goldenPrivate)).Append('"');
            json.Append(",\"goldenHelper\":\"").Append(Esc(goldenHelper)).Append('"');
            json.Append(",\"driverExitCode\":").Append(driverExit);
            json.Append(",\"contractMvid\":\"").Append(contractMvid).Append('"');
            json.Append(",\"contractFromDefault\":").Append(contractFromDefault ? "true" : "false");
            json.Append(",\"resultWriteFailed\":").Append(writeFailed ? "true" : "false");
            json.Append(",\"ok\":").Append(isOk ? "true" : "false");
            json.Append(",\"error\":\"").Append(Esc(error)).Append('"');
            json.Append(",\"logLength\":").Append(log.Length);
            json.Append(",\"logExcerpt\":\"").Append(Esc(excerpt)).Append('"');
            json.Append('}');
            return json.ToString();
        };

        var writeFailed = false;
        if (resultPath.Length == 0)
        {
            writeFailed = true;
            if (error.Length == 0) error = "result-path-missing";
            ok = false;
        }
        else
        {
            try
            {
                var directory = Path.GetDirectoryName(resultPath);
                if (!string.IsNullOrEmpty(directory)) Directory.CreateDirectory(directory);
                File.WriteAllText(resultPath, build(ok, false) + "\n");
            }
            catch (Exception writeError)
            {
                writeFailed = true;
                ok = false;
                error = (error.Length == 0 ? "" : error + "; ") + "result-write-failed: " + writeError.GetType().Name;
                Console.WriteLine("RUNE_IPAD_RESULT_WRITE_FAIL " + writeError.GetType().Name + ": " + writeError.Message);
            }
        }

        var finalText = build(ok, writeFailed);
        if (writeFailed && resultPath.Length > 0)
        {
            try { File.WriteAllText(resultPath, finalText + "\n"); } catch { }
        }
        Console.WriteLine("RUNE_IPAD_RESULT " + finalText);
        Console.Out.Flush();
        return ok && !writeFailed ? 0 : 1;
    }
}
