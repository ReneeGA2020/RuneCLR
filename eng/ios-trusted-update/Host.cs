using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Runtime.Loader;
using System.Security.Cryptography;
using RuneCLR.TrustedUpdate;

namespace TrustedUpdate;

public sealed class HostApi : IHostApi
{
    public int Echo(int value)
    {
        Console.WriteLine("HOST_ECHO=" + value);
        return value + 1;
    }
}

public static class Driver
{
    private sealed class HostCallScope : IHostApi
    {
        private readonly HostApi host;
        private bool accepting;

        public HostCallScope(HostApi host)
        {
            this.host = host;
            accepting = true;
        }

        public void Close()
        {
            accepting = false;
        }

        public int Echo(int value)
        {
            if (!accepting)
                throw new InvalidOperationException("host callback closed");
            return host.Echo(value);
        }

        public Func<int, int> CreateCallback()
        {
            return value =>
            {
                if (!accepting)
                    throw new InvalidOperationException("host callback closed");
                Console.WriteLine("HOST_DELEGATE=" + value);
                return value + 2;
            };
        }
    }

    private static void Require(bool value, string message)
    {
        if (!value) throw new InvalidOperationException(message);
    }

    private static Dictionary<string, string> payloadFiles;

    private static Assembly LoadUpdate(string directory)
    {
        string updatePath = Path.Combine(directory, "TrustedUpdate.Update.dll");
        Require(File.Exists(updatePath), "Update DLL missing: " + updatePath);
        LoadPayloadManifest(directory);
        RequireListed(directory, "TrustedUpdate.Update.dll");
        var context = new AssemblyLoadContext("trusted-update", isCollectible: false);
        context.Resolving += (_, name) =>
        {
            foreach (var assembly in AssemblyLoadContext.Default.Assemblies)
            {
                if (string.Equals(assembly.GetName().Name, name.Name, StringComparison.Ordinal))
                    return assembly;
            }

            string file = name.Name + ".dll";
            string candidate = Path.Combine(directory, file);
            if (!File.Exists(candidate))
                return null;
            RequireListed(directory, file);
            return context.LoadFromAssemblyPath(candidate);
        };
        return context.LoadFromAssemblyPath(updatePath);
    }

    private static void LoadPayloadManifest(string directory)
    {
        payloadFiles = null;
        string path = Path.Combine(directory, "payload-files.txt");
        if (!File.Exists(path))
            return;
        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (string raw in File.ReadAllLines(path))
        {
            string line = raw.Trim();
            if (line.Length == 0)
                continue;
            int space = line.IndexOf(' ');
            if (space <= 0)
                throw new InvalidOperationException("payload file list is invalid");
            string name = line.Substring(0, space);
            string hash = line.Substring(space + 1).Trim();
            if (name.IndexOfAny(new[] { '/', '\\' }) >= 0 || name == "." || name == ".." || hash.Length != 64)
                throw new InvalidOperationException("payload file list is invalid");
            string full = Path.Combine(directory, name);
            if (!File.Exists(full) || !string.Equals(HashFile(full), hash, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("payload file hash mismatch: " + name);
            map[name] = hash;
        }
        if (!map.ContainsKey("TrustedUpdate.Update.dll"))
            throw new InvalidOperationException("payload file list is invalid");
        payloadFiles = map;
    }

    private static void RequireListed(string directory, string file)
    {
        if (payloadFiles == null)
            return;
        string expected;
        if (!payloadFiles.TryGetValue(file, out expected))
            throw new InvalidOperationException("payload file is not listed: " + file);
        if (!string.Equals(HashFile(Path.Combine(directory, file)), expected, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("payload file hash mismatch: " + file);
    }

    private static string HashFile(string path)
    {
        using (var stream = File.OpenRead(path))
            return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    public static int Run()
    {
        string directory = Environment.GetEnvironmentVariable("RUNECLR_UPDATE_DIR") ?? "";
        string expected = Environment.GetEnvironmentVariable("RUNECLR_EXPECTED_VERSION") ?? "";
        bool forceFailure = Environment.GetEnvironmentVariable("RUNECLR_FORCE_FAILURE") == "1";
        Console.WriteLine($"TRUSTED_UPDATE_BEGIN expected={expected} directory={directory}");
        Console.Out.Flush();
        var run = new LoadedRun();
        try
        {
            int result;
            string selectedVersion;
            int gate = TryStartLoaded(directory, expected, forceFailure, run, out result, out selectedVersion);
            if (gate > 0)
                return gate;
            long managedBytes = GC.GetTotalMemory(false);
            Console.WriteLine("TRUSTED_UPDATE_SUCCESS version=" + selectedVersion + " result=" + result + " MANAGED_BYTES=" + managedBytes);
            Console.Out.Flush();
            return 0;
        }
        catch (Exception error)
        {
            Console.WriteLine("TRUSTED_UPDATE_FAILURE version=" + expected + " failure=" + HostFailure(error));
            Console.Out.Flush();
            return 17;
        }
        finally
        {
            if (run.Scope != null)
                run.Scope.Close();
        }
    }

    private sealed class LoadedRun
    {
        public HostCallScope Scope;
    }

    private static string HostFailure(Exception error)
    {
        if (error is System.Reflection.TargetInvocationException)
            return "ActivationFailed";
        string message = error.Message ?? "";
        if (message.StartsWith("payload file ", StringComparison.Ordinal)
            || message.StartsWith("Update DLL missing", StringComparison.Ordinal)
            || message == "intentional update activation failure"
            || message == "selector plan is invalid")
            return message;
        return "ActivationFailed";
    }

    private static int TryStartLoaded(string directory, string expected, bool forceFailure, LoadedRun run, out int result, out string selectedVersion)
    {
        result = 0;
        selectedVersion = expected;
        string planPath = Path.Combine(directory, "selector-plan.txt");
        if (!File.Exists(planPath))
        {
            result = ExecuteLoaded(directory, forceFailure, run);
            return 0;
        }
        Dictionary<string, string> plan = ReadSelectorPlan(planPath);
        string assemblyFile = plan["assemblyFile"];
        if (!string.Equals(assemblyFile, "TrustedUpdate.Update.dll", StringComparison.Ordinal))
            return RejectPlan(expected, "InvalidCandidate");
        string hostRuntime = Environment.GetEnvironmentVariable("RUNECLR_HOST_RUNTIME") ?? "";
        string hostArchitecture = Environment.GetEnvironmentVariable("RUNECLR_HOST_ARCHITECTURE") ?? "";
        string approvalId = Environment.GetEnvironmentVariable("RUNECLR_APPROVAL_ID") ?? "";
        string approvalVersion = Environment.GetEnvironmentVariable("RUNECLR_APPROVAL_VERSION") ?? "";
        string approvalHash = Environment.GetEnvironmentVariable("RUNECLR_APPROVAL_HASH") ?? "";
        if (hostRuntime.Length == 0 || hostArchitecture.Length == 0
            || approvalId.Length == 0 || approvalVersion.Length == 0 || approvalHash.Length == 0)
            return RejectPlan(expected, "InvalidCandidate");
        var candidate = new TrustedUpdateCandidate(
            plan["versionName"],
            plan["contentSha256"],
            Path.Combine(directory, assemblyFile),
            plan["entryTypeName"],
            plan["entryMethodName"],
            new TrustedUpdateTarget(plan["runtime"], plan["architecture"]));
        var approval = new TrustedUpdateApproval(approvalVersion, approvalHash, approvalId);
        var hostTarget = new TrustedUpdateTarget(hostRuntime, hostArchitecture);
        string storePath = Environment.GetEnvironmentVariable("RUNECLR_LAST_KNOWN_GOOD") ?? "";
        string root = Environment.GetEnvironmentVariable("RUNECLR_LAST_KNOWN_GOOD_ROOT") ?? "";
        string fallbackId = Environment.GetEnvironmentVariable("RUNECLR_FALLBACK_APPROVAL_ID") ?? "";
        string fallbackVersion = Environment.GetEnvironmentVariable("RUNECLR_FALLBACK_APPROVAL_VERSION") ?? "";
        string fallbackHash = Environment.GetEnvironmentVariable("RUNECLR_FALLBACK_APPROVAL_HASH") ?? "";
        bool fallbackReady = storePath.Length > 0 && root.Length > 0
            && fallbackId.Length > 0 && fallbackVersion.Length > 0 && fallbackHash.Length > 0;
        TrustedUpdateHostStart started = new TrustedUpdateProcess().TryStartHostLoaded(
            candidate,
            hostTarget,
            storePath.Length == 0 ? null : storePath,
            approval,
            directory,
            fallbackReady ? new TrustedUpdateApproval(fallbackVersion, fallbackHash, fallbackId) : null,
            fallbackReady ? root : null,
            expected,
            (chosen, source, candidateFailure) =>
            {
                if (source == TrustedUpdateStartSource.LastKnownGood)
                    Console.WriteLine("SELECTOR_FALLBACK version=" + chosen.VersionName + " candidateFailure=" + candidateFailure);
                else
                    Console.WriteLine("SELECTOR_PLAN version=" + chosen.VersionName);
                Console.Out.Flush();
                if (!string.Equals(Path.GetFileName(chosen.AssemblyPath), "TrustedUpdate.Update.dll", StringComparison.Ordinal))
                    return new TrustedUpdateActivation(TrustedUpdateFailure.InvalidCandidate, 0);
                string loadDirectory = Path.GetDirectoryName(chosen.AssemblyPath);
                if (string.IsNullOrEmpty(loadDirectory))
                    return new TrustedUpdateActivation(TrustedUpdateFailure.InvalidCandidate, 0);
                int value = ExecuteLoaded(loadDirectory, forceFailure, run);
                return new TrustedUpdateActivation(TrustedUpdateFailure.None, value);
            });
        if (!started.Succeeded)
        {
            Console.WriteLine("TRUSTED_UPDATE_FAILURE version=" + expected + " failure=" + started.Failure);
            Console.Out.Flush();
            return 17;
        }
        result = started.Value;
        selectedVersion = started.SelectedVersionName ?? expected;
        return 0;
    }

    private static int ExecuteLoaded(string loadDirectory, bool forceFailure, LoadedRun run)
    {
        Assembly assembly = LoadUpdate(loadDirectory);
        var update = Activator.CreateInstance(assembly.GetType("TrustedUpdate.Update", true)!);
        if (forceFailure) throw new InvalidOperationException("intentional update activation failure");
        run.Scope = new HostCallScope(new HostApi());
        var method = update!.GetType().GetMethod("Run")!;
        int result = (int)method.Invoke(update, new object[] { run.Scope, run.Scope.CreateCallback() })!;
        Assembly privateAssembly = contextAssembly(assembly, loadDirectory, "TrustedUpdate.Private.dll");
        int privateValue = (int)privateAssembly.GetType("TrustedUpdate.PrivateBehavior", true)!.GetMethod("Value")!.Invoke(null, null)!;
        Assembly helperAssembly = contextAssembly(assembly, loadDirectory, "TrustedUpdate.IlOnlyHelper.dll");
        int helperValue = (int)helperAssembly.GetType("TrustedUpdate.IlOnlyHelper", true)!.GetMethod("Compute")!.Invoke(null, new object[] { privateValue })!;
        Console.WriteLine($"HOST_REFLECTION_PRIVATE={privateValue} HOST_REFLECTION_HELPER={helperValue}");
        return result;
    }

    private static int RejectPlan(string expected, string failure)
    {
        Console.WriteLine("TRUSTED_UPDATE_FAILURE version=" + expected + " failure=" + failure);
        Console.Out.Flush();
        return 17;
    }

    private static Dictionary<string, string> ReadSelectorPlan(string path)
    {
        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        string[] required = new[]
        {
            "versionName", "contentSha256", "assemblyFile", "entryTypeName",
            "entryMethodName", "runtime", "architecture"
        };
        foreach (string raw in File.ReadAllLines(path))
        {
            string line = raw.Trim();
            if (line.Length == 0)
                continue;
            int space = line.IndexOf(' ');
            if (space <= 0)
                throw new InvalidOperationException("selector plan is invalid");
            string key = line.Substring(0, space);
            string value = line.Substring(space + 1).Trim();
            if (value.Length == 0 || map.ContainsKey(key))
                throw new InvalidOperationException("selector plan is invalid");
            map[key] = value;
        }
        foreach (string key in required)
        {
            if (!map.ContainsKey(key))
                throw new InvalidOperationException("selector plan is invalid");
        }
        return map;
    }

    private static Assembly contextAssembly(Assembly update, string directory, string file)
    {
        RequireListed(directory, file);
        string path = Path.Combine(directory, file);
        return AssemblyLoadContext.GetLoadContext(update)!.LoadFromAssemblyPath(path);
    }
}
