using System.Runtime.InteropServices;
using System.Text;

namespace RuneCLR.GroupedHost.Tests;

/// <summary>
/// Opt-in deterministic checkpoints for an external native collector. Enabled only when
/// GROUPED_WITNESS_CDB is exactly "1" on Windows, with GROUPED_WITNESS_JSONL and
/// GROUPED_WITNESS_CHECKPOINT pointing at rooted artifact paths. Without the environment it is a
/// no-op. It holds only scalars, flushes the host JSONL first, publishes the checkpoint with a
/// temp-then-replace write and only then calls DebugBreak. It refuses to break unless a native
/// debugger is already attached, so no JIT-debugger UI can appear.
/// </summary>
internal sealed class WitnessCheckpoint : IDisposable
{
    private readonly string _checkpointPath;
    private int _sequence;
    private string? _tempPath;

    private WitnessCheckpoint(bool enabled, string runId, string checkpointPath)
    {
        Enabled = enabled;
        RunId = runId;
        _checkpointPath = checkpointPath;
    }

    public bool Enabled { get; }

    public string RunId { get; }

    public string CheckpointPath => _checkpointPath;

    public static WitnessCheckpoint Create(string runId)
    {
        var cdb = Environment.GetEnvironmentVariable("GROUPED_WITNESS_CDB");
        if (!string.Equals(cdb, "1", StringComparison.Ordinal))
            return new WitnessCheckpoint(false, runId, string.Empty);

        if (!OperatingSystem.IsWindows())
            throw new InvalidOperationException("GROUPED_WITNESS_CDB=1 is Windows-only.");

        var jsonl = Environment.GetEnvironmentVariable("GROUPED_WITNESS_JSONL");
        if (string.IsNullOrWhiteSpace(jsonl) || !Path.IsPathRooted(jsonl))
            throw new InvalidOperationException(
                "GROUPED_WITNESS_JSONL must be a rooted artifact path when GROUPED_WITNESS_CDB=1.");

        var checkpoint = Environment.GetEnvironmentVariable("GROUPED_WITNESS_CHECKPOINT");
        if (string.IsNullOrWhiteSpace(checkpoint) || !Path.IsPathRooted(checkpoint))
            throw new InvalidOperationException(
                "GROUPED_WITNESS_CHECKPOINT must be a rooted artifact path when GROUPED_WITNESS_CDB=1.");

        var full = Path.GetFullPath(checkpoint);
        var directory = Path.GetDirectoryName(full);
        if (!string.IsNullOrEmpty(directory)) Directory.CreateDirectory(directory);

        if (!NativeMethods.IsDebuggerPresent())
            throw new InvalidOperationException(
                "GROUPED_WITNESS_CDB=1 requires an attached native debugger; refusing to DebugBreak without one.");

        return new WitnessCheckpoint(true, runId, full);
    }

    /// <summary>
    /// Flushes the host identity records, writes the checkpoint scalars with a temp-then-replace
    /// publish, then breaks into the attached native debugger.
    /// </summary>
    public void Enter(WitnessLog log, string phase, string group, int groupOrdinal)
    {
        if (!Enabled) return;
        log.Flush();
        _sequence++;
        var identifier = RunId + "-" + _sequence.ToString("D2");
        var createdUtc = DateTimeOffset.UtcNow.ToString("O");
        var json = "{"
            + "\"schema\":\"runeclr-grouped-checkpoint/1\","
            + "\"checkpoint_id\":\"" + identifier + "\","
            + "\"run_id\":\"" + RunId + "\","
            + "\"process_id\":" + Environment.ProcessId + ","
            + "\"group\":\"" + group + "\","
            + "\"group_ordinal\":" + groupOrdinal + ","
            + "\"phase\":\"" + phase + "\","
            + "\"created_utc\":\"" + createdUtc + "\""
            + "}";
        _tempPath = _checkpointPath + ".tmp-" + Environment.ProcessId;
        File.WriteAllText(_tempPath, json, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
        File.Move(_tempPath, _checkpointPath, overwrite: true);
        NativeMethods.DebugBreak();
    }

    public void Dispose()
    {
        if (_tempPath is null) return;
        try { if (File.Exists(_tempPath)) File.Delete(_tempPath); } catch { }
    }

    private static class NativeMethods
    {
        [DllImport("kernel32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool IsDebuggerPresent();

        [DllImport("kernel32.dll")]
        internal static extern void DebugBreak();
    }
}
