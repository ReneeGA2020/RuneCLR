using System.Reflection;
using System.Runtime.Loader;

namespace RuneCLR.Runtime;

internal sealed class CallbackDeadlineBridge
{
    private readonly Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, int, long, AssemblyLoadContext> _create;
    private readonly Func<AssemblyLoadContext, long> _begin;
    private readonly Func<AssemblyLoadContext, long, bool> _end;
    private readonly Func<AssemblyLoadContext, int, long> _query;

    private CallbackDeadlineBridge()
    {
        var type = typeof(AssemblyLoadContext);
        _create = RequiredInterpreterBridge.Method(type, "RuneCLR_CreateCallbackDeadline", true,
            type, typeof(string), typeof(Func<AssemblyLoadContext, AssemblyName, Assembly?>), typeof(long), typeof(int), typeof(long))
            .CreateDelegate<Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, int, long, AssemblyLoadContext>>();
        _begin = RequiredInterpreterBridge.Method(type, "RuneCLR_BeginCallbackDeadline", false, typeof(long))
            .CreateDelegate<Func<AssemblyLoadContext, long>>();
        _end = RequiredInterpreterBridge.Method(type, "RuneCLR_EndCallbackDeadline", false, typeof(bool), typeof(long))
            .CreateDelegate<Func<AssemblyLoadContext, long, bool>>();
        _query = RequiredInterpreterBridge.Method(type, "RuneCLR_QueryCallbackDeadline", false, typeof(long), typeof(int))
            .CreateDelegate<Func<AssemblyLoadContext, int, long>>();
    }

    public static CallbackDeadlineBridge Bind()
    {
        try
        {
            var version = RequiredInterpreterBridge.Method(typeof(AssemblyLoadContext), "RuneCLR_GetCallbackDeadlineVersion", true,
                typeof(long)).CreateDelegate<Func<long>>();
            if (version() != 1) throw new PlatformNotSupportedException("Callback deadline version 1 is required.");
            return new CallbackDeadlineBridge();
        }
        catch (Exception error)
        {
            throw new PlatformNotSupportedException("PrototypeCallbackDeadline requires matching private CoreLib/native support.", error);
        }
    }

    public AssemblyLoadContext Create(string name, Func<AssemblyLoadContext, AssemblyName, Assembly?> resolver,
        MapRunOptions options) => _create(name, resolver, options.PrototypeCallbackDeadline!.Value.Ticks,
            options.PrototypeDeadlinePollInterval, options.PrototypeCleanupInstructionBudget);
    public long Begin(AssemblyLoadContext context) => _begin(context);
    public bool End(AssemblyLoadContext context, long token) => _end(context, token);
    public CallbackDeadlineSnapshot Snapshot(AssemblyLoadContext context) => new(
        _query(context, 0), _query(context, 1), _query(context, 2), _query(context, 3) != 0,
        checked((int)_query(context, 4)), _query(context, 5), checked((int)_query(context, 6)));
}
