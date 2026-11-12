using System.Reflection;
using System.Runtime.Loader;

namespace RuneCLR.Runtime;

/// <summary>Binds the private callback-deadline surface. The clock factory and its instance methods
/// are the original version-1 contract; the epoch factory, ticker delegates and epoch snapshot
/// fields are additive and are only bound when a session explicitly selects epoch mode.</summary>
internal sealed class CallbackDeadlineBridge
{
    private readonly MapDeadlineMode _mode;
    private readonly Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, int, long, AssemblyLoadContext> _createClock;
    private readonly Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, int, long, long, AssemblyLoadContext>? _createEpoch;
    private readonly Func<AssemblyLoadContext, long> _begin;
    private readonly Func<AssemblyLoadContext, long, bool> _end;
    private readonly Func<AssemblyLoadContext, int, long> _query;
    private readonly Func<long>? _tickEpoch;
    private readonly Func<long>? _readEpoch;

    private CallbackDeadlineBridge(MapDeadlineMode mode,
        Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, int, long, AssemblyLoadContext> createClock,
        Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, int, long, long, AssemblyLoadContext>? createEpoch,
        Func<long>? tickEpoch, Func<long>? readEpoch)
    {
        _mode = mode;
        _createClock = createClock;
        _createEpoch = createEpoch;
        _tickEpoch = tickEpoch;
        _readEpoch = readEpoch;
        var type = typeof(AssemblyLoadContext);
        _begin = RequiredInterpreterBridge.Method(type, "RuneCLR_BeginCallbackDeadline", false, typeof(long))
            .CreateDelegate<Func<AssemblyLoadContext, long>>();
        _end = RequiredInterpreterBridge.Method(type, "RuneCLR_EndCallbackDeadline", false, typeof(bool), typeof(long))
            .CreateDelegate<Func<AssemblyLoadContext, long, bool>>();
        _query = RequiredInterpreterBridge.Method(type, "RuneCLR_QueryCallbackDeadline", false, typeof(long), typeof(int))
            .CreateDelegate<Func<AssemblyLoadContext, int, long>>();
    }

    internal MapDeadlineMode Mode => _mode;

    public static CallbackDeadlineBridge Bind(MapDeadlineMode mode, int epochPeriodMicros)
    {
        try
        {
            var type = typeof(AssemblyLoadContext);
            var version = RequiredInterpreterBridge.Method(type, "RuneCLR_GetCallbackDeadlineVersion", true, typeof(long))
                .CreateDelegate<Func<long>>();
            if (version() != 1) throw new PlatformNotSupportedException("Callback deadline version 1 is required.");
            if (mode == MapDeadlineMode.Clock)
                return new CallbackDeadlineBridge(mode, ClockFactory(), null, null, null);

            // Epoch is explicit: an old runtime without the capability rejects here, before files.
            var capabilities = RequiredInterpreterBridge.Method(type, "RuneCLR_GetCallbackDeadlineCapabilities", true, typeof(int))
                .CreateDelegate<Func<int>>();
            if ((capabilities() & 2) == 0)
                throw new PlatformNotSupportedException("The runtime does not advertise the epoch callback-deadline capability.");
            if (epochPeriodMicros is < 1 or > 1_000_000)
                throw new PlatformNotSupportedException("The epoch period is outside the supported 1..1000000 microsecond range.");
            var tick = RequiredInterpreterBridge.Method(type, "RuneCLR_TickCallbackDeadlineEpoch", true, typeof(long))
                .CreateDelegate<Func<long>>();
            var read = RequiredInterpreterBridge.Method(type, "RuneCLR_ReadCallbackDeadlineEpoch", true, typeof(long))
                .CreateDelegate<Func<long>>();
            return new CallbackDeadlineBridge(mode, ClockFactory(), EpochFactory(), tick, read);
        }
        catch (PlatformNotSupportedException) { throw; }
        catch (Exception error)
        {
            throw new PlatformNotSupportedException(
                "PrototypeCallbackDeadline requires matching private CoreLib/native support.", error);
        }
    }

    private static Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, int, long, AssemblyLoadContext> ClockFactory()
    {
        var type = typeof(AssemblyLoadContext);
        return RequiredInterpreterBridge.Method(type, "RuneCLR_CreateCallbackDeadline", true,
                type, typeof(string), typeof(Func<AssemblyLoadContext, AssemblyName, Assembly?>), typeof(long), typeof(int), typeof(long))
            .CreateDelegate<Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, int, long, AssemblyLoadContext>>();
    }

    private static Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, int, long, long, AssemblyLoadContext> EpochFactory()
    {
        var type = typeof(AssemblyLoadContext);
        return RequiredInterpreterBridge.Method(type, "RuneCLR_CreateCallbackDeadlineEpoch", true,
                type, typeof(string), typeof(Func<AssemblyLoadContext, AssemblyName, Assembly?>), typeof(long), typeof(int), typeof(long), typeof(long))
            .CreateDelegate<Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, int, long, long, AssemblyLoadContext>>();
    }

    internal long TickEpoch() => (_tickEpoch ?? throw new InvalidOperationException("Epoch mode is not active."))();
    internal long ReadEpoch() => (_readEpoch ?? throw new InvalidOperationException("Epoch mode is not active."))();

    public AssemblyLoadContext Create(string name, Func<AssemblyLoadContext, AssemblyName, Assembly?> resolver,
        MapRunOptions options)
    {
        var deadline = options.PrototypeCallbackDeadline!.Value;
        if (_mode == MapDeadlineMode.Clock)
            return _createClock(name, resolver, deadline.Ticks, options.PrototypeDeadlinePollInterval,
                options.PrototypeCleanupInstructionBudget);
        try
        {
            return _createEpoch!(name, resolver, deadline.Ticks, options.PrototypeDeadlinePollInterval,
                options.PrototypeCleanupInstructionBudget, options.PrototypeDeadlineEpochPeriodMicros);
        }
        catch (ArgumentOutOfRangeException error)
        {
            // The native side latches the epoch period process-wide; an externally or earlier
            // latched different period surfaces as ArgumentOutOfRangeException from the factory.
            // Only this configuration failure is normalized - resolver/author exceptions are not.
            throw new PlatformNotSupportedException(
                $"The runtime epoch period {options.PrototypeDeadlineEpochPeriodMicros} us conflicts with the period already latched by the process.",
                error);
        }
    }

    public long Begin(AssemblyLoadContext context) => _begin(context);
    public bool End(AssemblyLoadContext context, long token) => _end(context, token);

    public CallbackDeadlineSnapshot Snapshot(AssemblyLoadContext context)
    {
        var snapshot = new CallbackDeadlineSnapshot(
            _query(context, 0), _query(context, 1), _query(context, 2), _query(context, 3) != 0,
            checked((int)_query(context, 4)), _query(context, 5), checked((int)_query(context, 6)));
        // Clock snapshots never touch the additive fields: an old v1 runtime has no fields 8..10.
        if (_mode == MapDeadlineMode.Clock) return snapshot;
        return snapshot with
        {
            Mode = (int)MapDeadlineMode.Epoch,
            EpochBudgetTicks = _query(context, 9),
            CurrentGlobalEpoch = _query(context, 10)
        };
    }
}
