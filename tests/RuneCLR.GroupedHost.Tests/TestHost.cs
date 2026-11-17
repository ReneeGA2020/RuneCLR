using RuneCLR.GroupedHost.Fixtures;

namespace RuneCLR.GroupedHost.Tests;

/// <summary>
/// Host-side contract implementation used by the grouped-host harness. It owns every external root
/// the author installs (subscriptions) so the harness can prove that releasing those roots, not
/// clearing business statics, is what lets the group retire.
/// </summary>
internal sealed class TestHost : IGroupedHostContract
{
    private readonly List<string> _records = [];
    private readonly List<Action> _retained = [];

    public string Mode { get; set; } = "normal";

    public byte[] DynamicImage { get; set; } = [];

    public IReadOnlyList<string> Records => _records;

    public int RetainedCount => _retained.Count;

    /// <summary>Optional in-flight observer; used by the reentrant-entry case.</summary>
    public Action<string>? Observer { get; set; }

    public Exception? ObserverError { get; set; }

    public void Record(string message)
    {
        _records.Add(message);
        Observer?.Invoke(message);
    }

    public void Subscribe(Action callback) => _retained.Add(callback);

    public void Unsubscribe(Action callback) => _retained.Remove(callback);

    public void ReleaseRetained() => _retained.Clear();

    public int Count(string prefix) => _records.Count(line => line.StartsWith(prefix, StringComparison.Ordinal));

    public int AuthorRecords => Count("author:");

    public IReadOnlyList<string> Lines(string prefix) =>
        _records.Where(line => line.StartsWith(prefix, StringComparison.Ordinal)).ToArray();
}
