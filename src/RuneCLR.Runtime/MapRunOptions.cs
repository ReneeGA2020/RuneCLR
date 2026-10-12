namespace RuneCLR.Runtime;

public sealed record MapRunOptions
{
    public int TickCount { get; init; } = 3;
    public TimeSpan TickDuration { get; init; } = TimeSpan.FromMilliseconds(50);
    public int OperationBudgetPerCallback { get; init; } = 1_000;
    public int MaxEntities { get; init; } = 128;
    public int MaxLogMessages { get; init; } = 128;

    internal void Validate()
    {
        ArgumentOutOfRangeException.ThrowIfNegative(TickCount);
        ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(TickDuration, TimeSpan.Zero);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(OperationBudgetPerCallback);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(MaxEntities);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(MaxLogMessages);
    }
}

public enum MapRunOutcome
{
    Completed,
    Failed
}

public sealed record MapRunReport(
    string MapId,
    MapRunOutcome Outcome,
    int CompletedTicks,
    int CreatedEntities,
    int ReleasedEntities,
    int RemainingEntities,
    IReadOnlyList<string> Logs,
    string? Error);

public sealed record MapRunResult(MapRunReport Report, UnloadTicket Unload);

public sealed class UnloadTicket
{
    private readonly WeakReference _context;

    internal UnloadTicket(WeakReference context) => _context = context;

    // Observe this after Run returns; the executing stack itself can keep the context alive.
    public bool IsCollected => !_context.IsAlive;
}
