namespace RuneCLR.Runtime;

public enum MapExecutionPolicy
{
    Default,
    RequireInterpreter
}

public sealed record MapRunOptions
{
    public MapExecutionPolicy ExecutionPolicy { get; init; } = MapExecutionPolicy.Default;
    // Experimental native IR-dispatch budget, not a complete execution-time sandbox.
    public long? PrototypeInstructionBudget { get; init; }
    public long PrototypeCleanupInstructionBudget { get; init; } = 4_096;
    // Only MapRunner.Run uses TickCount; pumped sessions advance when the host calls Tick.
    public int TickCount { get; init; } = 3;
    public TimeSpan TickDuration { get; init; } = TimeSpan.FromMilliseconds(50);
    public int OperationBudgetPerCallback { get; init; } = 1_000;
    public int MaxEntities { get; init; } = 128;
    public int MaxLogMessages { get; init; } = 128;

    internal void Validate()
    {
        if (!Enum.IsDefined(ExecutionPolicy)) throw new ArgumentOutOfRangeException(nameof(ExecutionPolicy));
        if (PrototypeInstructionBudget is { } instructionBudget)
            ArgumentOutOfRangeException.ThrowIfNegativeOrZero(instructionBudget, nameof(PrototypeInstructionBudget));
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(PrototypeCleanupInstructionBudget);
        if (PrototypeInstructionBudget is not null && ExecutionPolicy != MapExecutionPolicy.RequireInterpreter)
            throw new ArgumentException("Prototype instruction budgets require RequireInterpreter.", nameof(ExecutionPolicy));
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
    string? Error)
{
    public MapExecutionPolicy ExecutionPolicy { get; init; }
    public int ExecutionPolicyVersion { get; init; }
    public PrototypeBudgetSnapshot? PrototypeBudget { get; init; }
}

// Scalars copied before Unload; no session context, author metadata or exception is retained.
public sealed record PrototypeBudgetSnapshot(
    long ExecutionRemaining,
    long ExecutionExecuted,
    bool ExecutionExhausted,
    bool IsTerminated,
    int Reason,
    int Phase,
    long CleanupRemaining,
    long CleanupExecuted);

public sealed record MapRunResult(MapRunReport Report, UnloadTicket Unload);

public sealed class UnloadTicket
{
    private readonly WeakReference _context;

    internal UnloadTicket(WeakReference context) => _context = context;

    // Observe after Run/Stop or a failed Tick returns; callback stacks can keep the context alive.
    public bool IsCollected => !_context.IsAlive;
}
