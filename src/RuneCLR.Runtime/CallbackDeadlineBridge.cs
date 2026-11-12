using System.Reflection;
using System.Runtime.Loader;

namespace RuneCLR.Runtime;

/// <summary>Binds the private callback-deadline surface. The clock factory and its
/// instance methods are the original version-1 contract; the epoch factory is the
/// additive capability and is only bound when a session asks for epoch mode.</summary>
internal sealed class CallbackDeadlineBridge
{
    private readonly MapDeadlineMode _mode;
    private readonly Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, int, long, AssemblyLoadContext> _createClock;
    private readonly Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, int, long, long, AssemblyLoadContext>? _createEpoch;
    private readonly Func<AssemblyLoadContext, long> _begin;
    private readonly Func<AssemblyLoadContext, long, bool> _end;
    private readonly Func<AssemblyLoadContext, int, long> _query;

    private CallbackDeadlineBridge(MapDeadlineMode mode,
        Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, int, long, AssemblyLoadContext> createClock,
        Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, int, long, long, AssemblyLoadContext>? createEpoch)
    {
        _mode = mode;
        _createClock = createClock;
        _createEpoch = createEpoch;
        var type = typeof(AssemblyLoadContext);
        _begin = RequiredInterpreterBridge.Method(type, "RuneCLR_BeginCallbackDeadline", false, typeof(long))
            .CreateDelegate<Func<AssemblyLoadContext, long>>();
        _end = RequiredInterpreterBridge.Method(type, "RuneCLR_EndCallbackDeadline", false, typeof(bool), typeof(long))
            .CreateDelegate<Func<AssemblyLoadContext, long, bool>>();
        _query = RequiredInterpreterBridge.Method(type, "RuneCLR_QueryCallbackDeadline", false, typeof(long), typeof(int))
            .CreateDelegate<Func<AssemblyLoadContext, int, long>>();
    }

    public static CallbackDeadlineBridge Bind(MapDeadlineMode mode, int epochPeriodMicros)
    {
        try
        {
            var type = typeof(AssemblyLoadContext);
            var version = RequiredInterpreterBridge.Method(type, "RuneCLR_GetCallbackDeadlineVersion", true, typeof(long))
                .CreateDelegate<Func<long>>();
            if (version() != 1) throw new PlatformNotSupportedException("Callback deadline version 1 is required.");
            if (mode == MapDeadlineMode.Clock)
                return new CallbackDeadlineBridge(mode, ClockFactory(), null);

            var capabilities = RequiredInterpreterBridge.Method(type, "RuneCLR_GetCallbackDeadlineCapabilities", true, typeof(int))
                .CreateDelegate<Func<int>>();
            if ((capabilities() & 2) == 0)
                throw new PlatformNotSupportedException("The runtime does not advertise the epoch callback-deadline capability.");
            if (epochPeriodMicros is < 1 or > 1_000_000)
                throw new PlatformNotSupportedException("The epoch period is outside the supported 1..1000000 microsecond range.");
            return new CallbackDeadlineBridge(mode, ClockFactory(), EpochFactory());
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

    public AssemblyLoadContext Create(string name, Func<AssemblyLoadContext, AssemblyName, Assembly?> resolver,
        MapRunOptions options)
    {
        var deadline = options.PrototypeCallbackDeadline!.Value;
        if (_mode == MapDeadlineMode.Clock)
            return _createClock(name, resolver, deadline.Ticks, options.PrototypeDeadlinePollInterval,
                options.PrototypeCleanupInstructionBudget);
        return _createEpoch!(name, resolver, deadline.Ticks, options.PrototypeDeadlinePollInterval,
            options.PrototypeCleanupInstructionBudget, options.PrototypeDeadlineEpochPeriodMicros);
    }

    public long Begin(AssemblyLoadContext context) => _begin(context);
    public bool End(AssemblyLoadContext context, long token) => _end(context, token);
    public CallbackDeadlineSnapshot Snapshot(AssemblyLoadContext context) => new(
        _query(context, 0), _query(context, 1), _query(context, 2), _query(context, 3) != 0,
        checked((int)_query(context, 4)), _query(context, 5), checked((int)_query(context, 6)))
    {
        Mode = checked((int)_query(context, 8)),
        EpochBudgetTicks = _query(context, 9),
        CurrentGlobalEpoch = _query(context, 10)
    };
}
