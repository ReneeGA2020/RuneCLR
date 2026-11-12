namespace RuneCLR.Runtime;

public enum MapExecutionPolicy
{
    Default,
    RequireInterpreter
}

public sealed record MapRunOptions
{
    public MapExecutionPolicy ExecutionPolicy { get; init; } = MapExecutionPolicy.Default;
    // Opt-in until every loading/entry path has matching runtime enforcement.
    public RuneCLR.Packages.IApiAccessPolicy? PrototypeApiPolicy { get; init; }
    public IReadOnlyList<System.Reflection.Assembly> PrototypeSharedAssemblies { get; init; } = [];
    // Experimental native IR-dispatch budget, not a complete execution-time sandbox.
    public long? PrototypeInstructionBudget { get; init; }
    public TimeSpan? PrototypeCallbackDeadline { get; init; }
    // Experimental sampling source for the callback deadline; Clock is the baseline.
    // Epoch mode needs the additive runtime epoch capability; the ticker period is
    // latched per process, so period variants run in separate processes.
    public MapDeadlineMode PrototypeDeadlineMode { get; init; } = MapDeadlineMode.Clock;
    public int PrototypeDeadlineEpochPeriodMicros { get; init; } = 1_000;
    public int PrototypeDeadlinePollInterval { get; init; } = 100;
    public long PrototypeCleanupInstructionBudget { get; init; } = 4_096;
    // Only MapRunner.Run uses TickCount; pumped sessions advance when the host calls Tick.
    public int TickCount { get; init; } = 3;
    public TimeSpan TickDuration { get; init; } = TimeSpan.FromMilliseconds(50);
    public int OperationBudgetPerCallback { get; init; } = 1_000;
    public int MaxEntities { get; init; } = 128;
    public int MaxLogMessages { get; init; } = 128;
    public int MaxScheduledSignals { get; init; } = 128;
    public int MaxWorkItems { get; init; } = 128;
    public int MaxResources { get; init; } = 128;

    internal void Validate()
    {
        if (!Enum.IsDefined(ExecutionPolicy)) throw new ArgumentOutOfRangeException(nameof(ExecutionPolicy));
        if (PrototypeApiPolicy is not null && ExecutionPolicy != MapExecutionPolicy.RequireInterpreter)
            throw new ArgumentException("A UGC API policy requires RequireInterpreter.", nameof(ExecutionPolicy));
        ArgumentNullException.ThrowIfNull(PrototypeSharedAssemblies);
        if (PrototypeSharedAssemblies.Count != 0 && PrototypeApiPolicy is null)
            throw new ArgumentException("Explicit shared assemblies require a UGC API policy.");
        if (PrototypeInstructionBudget is { } instructionBudget)
            ArgumentOutOfRangeException.ThrowIfNegativeOrZero(instructionBudget, nameof(PrototypeInstructionBudget));
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(PrototypeCleanupInstructionBudget);
        if (PrototypeInstructionBudget is not null && ExecutionPolicy != MapExecutionPolicy.RequireInterpreter)
            throw new ArgumentException("Prototype instruction budgets require RequireInterpreter.", nameof(ExecutionPolicy));
        if (PrototypeCallbackDeadline is { } deadline)
        {
            ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(deadline, TimeSpan.Zero);
            if (ExecutionPolicy != MapExecutionPolicy.RequireInterpreter || PrototypeInstructionBudget is not null)
                throw new ArgumentException("Callback deadlines require RequireInterpreter and a separate instruction-budget lane.");
            if (PrototypeDeadlinePollInterval is not (1 or 100 or 1000))
                throw new ArgumentOutOfRangeException(nameof(PrototypeDeadlinePollInterval));
            if (!Enum.IsDefined(PrototypeDeadlineMode))
                throw new ArgumentOutOfRangeException(nameof(PrototypeDeadlineMode));
            if (PrototypeDeadlineMode == MapDeadlineMode.Epoch &&
                PrototypeDeadlineEpochPeriodMicros is < 1 or > 1_000_000)
                throw new ArgumentOutOfRangeException(nameof(PrototypeDeadlineEpochPeriodMicros));
        }
        else if (PrototypeDeadlineMode != MapDeadlineMode.Clock)
        {
            throw new ArgumentException("A deadline mode requires a callback deadline.");
        }
        ArgumentOutOfRangeException.ThrowIfNegative(TickCount);
        ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(TickDuration, TimeSpan.Zero);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(OperationBudgetPerCallback);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(MaxEntities);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(MaxLogMessages);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(MaxScheduledSignals);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(MaxWorkItems);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(MaxResources);
    }
}

public enum MapDeadlineMode
{
    Clock,
    Epoch
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
    public CallbackDeadlineSnapshot? PrototypeDeadline { get; init; }
}

public sealed record CallbackDeadlineSnapshot(long ClockFrequency, long ClockChecks, long AdmittedOperations,
    bool Active, int PollInterval, long LastToken, int Reason)
{
    // Epoch-mode evidence; zero in clock mode and on runtimes without the epoch ABI.
    public int Mode { get; init; }
    public long EpochBudgetTicks { get; init; }
    public long CurrentGlobalEpoch { get; init; }
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

public readonly record struct MapEntityInfo(EntityId Id, string Name);

public readonly record struct MapWorkInfo(long Id, string Name);

public readonly record struct MapResourceInfo(string Name);

public sealed class UnloadTicket
{
    private readonly WeakReference _context;

    internal UnloadTicket(WeakReference context) => _context = context;

    // Observe after Run/Stop or a failed Tick returns; callback stacks can keep the context alive.
    public bool IsCollected => !_context.IsAlive;
}
