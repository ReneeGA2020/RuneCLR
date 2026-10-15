using System.Reflection;
using System.Runtime.Loader;

namespace RuneCLR.Runtime;

// Private matching-CoreLib experiment. All delegates target trusted CoreLib, not author code.
// Versions acknowledge the individual prototype features, not a complete terminal capability.
internal sealed class TerminalPrototypeBridge
{
    private readonly RequiredInterpreterBridge _required;
    private readonly Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, long, AssemblyLoadContext> _create;
    private readonly Func<AssemblyLoadContext, long> _remaining;
    private readonly Func<AssemblyLoadContext, long> _executed;
    private readonly Func<AssemblyLoadContext, bool> _exhausted;
    private readonly Func<AssemblyLoadContext, bool> _terminated;
    private readonly Func<AssemblyLoadContext, int> _reason;
    private readonly Func<AssemblyLoadContext, int> _phase;
    private readonly Func<AssemblyLoadContext, long> _cleanupRemaining;
    private readonly Func<AssemblyLoadContext, long> _cleanupExecuted;

    private TerminalPrototypeBridge(RequiredInterpreterBridge required)
    {
        _required = required;
        var type = typeof(AssemblyLoadContext);
        _create = RequiredInterpreterBridge.Method(type, "RuneCLR_CreateTerminalPrototype", true,
            typeof(AssemblyLoadContext), typeof(string), typeof(Func<AssemblyLoadContext, AssemblyName, Assembly?>),
            typeof(long), typeof(long)).CreateDelegate<
                Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, long, AssemblyLoadContext>>();
        _remaining = Getter<long>("RuneCLR_GetInstructionMeterRemaining");
        _executed = Getter<long>("RuneCLR_GetInstructionMeterExecuted");
        _exhausted = Getter<bool>("RuneCLR_GetInstructionMeterExhausted");
        _terminated = Getter<bool>("RuneCLR_GetTerminalPrototypeIsTerminated");
        _reason = Getter<int>("RuneCLR_GetTerminalPrototypeReason");
        _phase = Getter<int>("RuneCLR_GetTerminalPrototypePhase");
        _cleanupRemaining = Getter<long>("RuneCLR_GetTerminalPrototypeCleanupRemaining");
        _cleanupExecuted = Getter<long>("RuneCLR_GetTerminalPrototypeCleanupExecuted");
    }

    public static TerminalPrototypeBridge Bind(RequiredInterpreterBridge required)
    {
        try
        {
            var version = RequiredInterpreterBridge.Method(typeof(AssemblyLoadContext),
                "RuneCLR_GetTerminalPrototypeVersion", true, typeof(int)).CreateDelegate<Func<int>>();
            var finalizerVersion = RequiredInterpreterBridge.Method(typeof(GC),
                "RuneCLR_GetTerminalFinalizerBoundaryVersion", true, typeof(int)).CreateDelegate<Func<int>>();
            if (version() != 1 || finalizerVersion() != 1)
                throw Unsupported("Terminal prototype and finalizer-boundary versions must both be 1.");
            return new TerminalPrototypeBridge(required);
        }
        catch (PlatformNotSupportedException) { throw; }
        catch (Exception error)
        {
            throw Unsupported("The trusted CoreLib terminal-prototype bridge cannot be bound.", error);
        }
    }

    public AssemblyLoadContext Create(string name, Func<AssemblyLoadContext, AssemblyName, Assembly?> resolver,
        long instructionBudget, long cleanupBudget)
    {
        AssemblyLoadContext? context = null;
        try
        {
            context = _create(name, resolver, instructionBudget, cleanupBudget);
            _required.Acknowledge(context);
            var initial = Snapshot(context!);
            if (initial != new PrototypeBudgetSnapshot(instructionBudget, 0, false, false, 0, 0, cleanupBudget, 0))
                throw Unsupported("The new context did not acknowledge the exact initial native prototype budget.");
            return context!;
        }
        catch
        {
            if (context?.IsCollectible == true) context.Unload();
            throw;
        }
    }

    public bool IsTerminated(AssemblyLoadContext context) => _terminated(context);

    // Separate scalar native reads, taken on the synchronous host execution path.
    // This does not claim an atomic snapshot across concurrent author threads.
    public PrototypeBudgetSnapshot Snapshot(AssemblyLoadContext context) => new(
        _remaining(context), _executed(context), _exhausted(context), _terminated(context),
        _reason(context), _phase(context), _cleanupRemaining(context), _cleanupExecuted(context));

    private static Func<AssemblyLoadContext, T> Getter<T>(string name) =>
        RequiredInterpreterBridge.Method(typeof(AssemblyLoadContext), name, false, typeof(T))
            .CreateDelegate<Func<AssemblyLoadContext, T>>();

    private static PlatformNotSupportedException Unsupported(string message, Exception? inner = null) =>
        new("PrototypeInstructionBudget needs matching RuneCLR CoreLib/native terminal-prototype and finalizer-boundary support. " + message, inner);
}
