using System.Reflection;
using System.Text;

namespace RuneCLR.GroupedHost.Tests;

/// <summary>
/// Scalar-only witness record. It never holds a MethodInfo, Type, Assembly, delegate, Exception or
/// AssemblyLoadContext; every field is a copied value.
/// </summary>
internal sealed record WitnessRecord(
    int Seq,
    string Phase,
    string Role,
    int CallOrdinal,
    string Group,
    int GroupOrdinal,
    string RunId,
    int ProcessId,
    string ImageName,
    string ImageFullName,
    string ImageSha256,
    string ImageMvid,
    int ImageBytes,
    string AlcName,
    int MethodToken,
    long MethodHandle,
    string DeclaredEntry,
    string MarkerKind,
    int MarkerRun,
    string MarkerToken,
    string WitnessSource,
    bool WitnessVerified,
    string TimestampUtc);

/// <summary>
/// Appends newline-delimited JSON identity records. witness_verified is hard-coded false: nothing in
/// the fixtures, host records, policy acks or environment can set it true.
/// </summary>
internal sealed class WitnessLog : IDisposable
{
    private readonly StreamWriter? _writer;
    private int _sequence;

    public WitnessLog(string? path)
    {
        if (!string.IsNullOrWhiteSpace(path))
        {
            var full = Path.GetFullPath(path);
            var directory = Path.GetDirectoryName(full);
            if (!string.IsNullOrEmpty(directory)) Directory.CreateDirectory(directory);
            _writer = new StreamWriter(full, append: false, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
        }
        RunId = Guid.NewGuid().ToString("N");
    }

    public string RunId { get; }

    public void Write(WitnessRecord record)
    {
        _sequence++;
        var line = "{"
            + "\"schema\":\"runeclr-grouped-witness/1\","
            + "\"seq\":" + _sequence + ","
            + "\"phase\":\"" + Quote(record.Phase) + "\","
            + "\"role\":\"" + Quote(record.Role) + "\","
            + "\"call_ordinal\":" + record.CallOrdinal + ","
            + "\"group\":\"" + Quote(record.Group) + "\","
            + "\"group_ordinal\":" + record.GroupOrdinal + ","
            + "\"run_id\":\"" + Quote(record.RunId) + "\","
            + "\"process_id\":" + record.ProcessId + ","
            + "\"image_name\":\"" + Quote(record.ImageName) + "\","
            + "\"image_full_name\":\"" + Quote(record.ImageFullName) + "\","
            + "\"image_sha256\":\"" + Quote(record.ImageSha256) + "\","
            + "\"image_mvid\":\"" + Quote(record.ImageMvid) + "\","
            + "\"image_bytes\":" + record.ImageBytes + ","
            + "\"alc_name\":\"" + Quote(record.AlcName) + "\","
            + "\"method_token\":" + record.MethodToken + ","
            + "\"method_handle\":" + record.MethodHandle + ","
            + "\"declared_entry\":\"" + Quote(record.DeclaredEntry) + "\","
            + "\"marker_kind\":\"" + Quote(record.MarkerKind) + "\","
            + "\"marker_run\":" + record.MarkerRun + ","
            + "\"marker_token\":\"" + Quote(record.MarkerToken) + "\","
            + "\"witness_source\":\"" + Quote(record.WitnessSource) + "\","
            + "\"witness_verified\":false,"
            + "\"timestamp_utc\":\"" + Quote(DateTimeOffset.UtcNow.ToString("O")) + "\""
            + "}";
        _writer?.WriteLine(line);
        _writer?.Flush();
    }

    private static string Quote(string value)
    {
        var text = value ?? string.Empty;
        var builder = new StringBuilder(text.Length + 8);
        foreach (var character in text)
        {
            switch (character)
            {
                case '"': builder.Append("\\\""); break;
                case '\\': builder.Append("\\\\"); break;
                case '\r': builder.Append("\\r"); break;
                case '\n': builder.Append("\\n"); break;
                case '\t': builder.Append("\\t"); break;
                default:
                    if (character < ' ') builder.Append("\\u").Append(((int)character).ToString("x4"));
                    else builder.Append(character);
                    break;
            }
        }
        return builder.ToString();
    }

    public void Flush() => _writer?.Flush();

    public void Dispose() => _writer?.Dispose();
}

/// <summary>Deliberate host-side observer root used only by the rooting negative control; cleared after use.</summary>
internal static class WitnessControlRoot
{
    internal static MethodInfo? Root;
}

/// <summary>Collects fixture-gate failures so one run reports every identity/lifecycle gate.</summary>
internal sealed class WitnessGate
{
    private readonly List<string> _failures = [];

    public void Check(bool condition, string message)
    {
        if (!condition) _failures.Add(message);
    }

    public bool Passed => _failures.Count == 0;

    public string Summary() => Passed
        ? "identity/lifecycle gates: PASS"
        : "identity/lifecycle gates: FAIL (" + _failures.Count + "): " + string.Join(" | ", _failures);
}
