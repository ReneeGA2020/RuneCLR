namespace RuneCLR.Runtime;

/// <summary>
/// Read-only process-wide epoch ticker scalars for tests and diagnostics. There is no control
/// surface here: it cannot start, stop, retarget or tick the ticker.
/// </summary>
public static class CallbackEpochDiagnostics
{
    /// <summary>Number of live sessions currently leasing the shared ticker (0 in clock-only processes).</summary>
    public static int ActiveLeaseCount => CallbackEpochTicker.ActiveLeases;

    /// <summary>Host-latched period in microseconds (0 before the first lease).</summary>
    public static int LatchedPeriodMicros => CallbackEpochTicker.LatchedPeriodMicros;

    /// <summary>Total successful ticker increments since process start.</summary>
    public static long TotalTicks => CallbackEpochTicker.TotalTicks;

    /// <summary>True once the ticker thread captured a fault.</summary>
    public static bool Faulted => CallbackEpochTicker.Faulted;

    /// <summary>Captured fault type name, or null. Never an author message.</summary>
    public static string? FaultTypeName => CallbackEpochTicker.FaultType;
}
