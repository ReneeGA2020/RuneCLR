using System.IO;
using System.Reflection;
using System.Runtime.Loader;
using System.Threading;
using System.Threading.Tasks;

namespace SessionOrigin.Compiled;

public interface IOriginContract
{
    int Echo(int value);
}

public static class OriginHooks
{
    public static byte[]? DeniedAssemblyBytes;
    public static int ParentThreadId;
    public static int ChildThreadId;
    public static bool ChildFlowAbsent;
    public static bool ChildProbeRan;
    public static bool ChildReflectionDenied;
    public static bool ChildLoadDenied;
    public static bool ChildLoadSucceeded;
    public static int ForbiddenEffects;
    public static string ChildFailure = "";
    public static bool CompiledHelperDenied;
    public static bool CompiledHelperEscaped;
    public static MethodInfo? RetainedProbe;
    public static MethodInfo? OtherProbe;
    public static bool RetiredProbeRan;
    public static bool ConflictProbeRan;
    public static string RetiredFailure = "";
    public static string ConflictFailure = "";
    public static bool CompiledOnlySuppressedRan;
    public static bool CompiledOnlyEscaped;
    public static string CompiledOnlyFailure = "";
    public static readonly AsyncLocal<string?> FlowMarker = new();
    public static Action? OverflowChain;
    public static int ChainDepth;
    public static bool ChainCompleted;
    public static string ChainFailure = "";
    public static string ChainLeafFailure = "";
    private static readonly List<AssemblyLoadContext> ChainContexts = [];
    private static Thread? BlockingChild;
    private static readonly ManualResetEventSlim BlockingParked = new(false);
    private static readonly ManualResetEventSlim BlockingRelease = new(false);

    public static void ForbiddenEffect() => ForbiddenEffects++;

    public static void ReflectForbiddenCompiledHelper()
    {
        try
        {
            typeof(OriginHooks).GetMethod(nameof(ForbiddenEffect))!.Invoke(null, null);
            CompiledHelperEscaped = true;
        }
        catch (InvalidOperationException)
        {
            CompiledHelperDenied = true;
        }
    }

    public static void RecordReflectionDenied() => ChildReflectionDenied = true;
    public static void RecordLoadDenied() => ChildLoadDenied = true;
    public static void RecordLoadSucceeded() => ChildLoadSucceeded = true;

    public static int? GetOriginScanCapability()
    {
        var type = typeof(object).Assembly.GetType("System.Reflection.RuneCLRReflectionPolicy");
        var method = type?.GetMethod("RuneCLR_GetReflectionPolicyCapabilities",
            BindingFlags.Static | BindingFlags.NonPublic);
        if (method is null) return null;
        return method.CreateDelegate<Func<int>>()();
    }

    public static bool GetOriginScanSwitch(out bool present)
    {
        present = AppContext.TryGetSwitch("RuneCLR.EnableReflectionPolicyOriginScan", out bool value);
        return !present || value;
    }

    public static void Reset()
    {
        ParentThreadId = 0;
        ChildThreadId = 0;
        ChildFlowAbsent = false;
        ChildProbeRan = false;
        ChildReflectionDenied = false;
        ChildLoadDenied = false;
        ChildLoadSucceeded = false;
        ForbiddenEffects = 0;
        ChildFailure = "";
        CompiledHelperDenied = false;
        CompiledHelperEscaped = false;
        RetainedProbe = null;
        OtherProbe = null;
        RetiredProbeRan = false;
        ConflictProbeRan = false;
        RetiredFailure = "";
        ConflictFailure = "";
        CompiledOnlySuppressedRan = false;
        CompiledOnlyEscaped = false;
        CompiledOnlyFailure = "";
        OverflowChain = null;
        ChainDepth = 0;
        ChainCompleted = false;
        ChainFailure = "";
        ChainLeafFailure = "";
        ClearChainContexts();
        BlockingChild = null;
        BlockingParked.Reset();
        BlockingRelease.Reset();
    }

    private static void ClearChainContexts()
    {
        foreach (var context in ChainContexts.ToArray()) context.Unload();
        ChainContexts.Clear();
    }

    public static void SetRetainedProbe(MethodInfo probe)
    {
        RetainedProbe = probe;
        OtherProbe = probe;
    }

    public static void InvokeRetainedOnSuppressedThread()
    {
        if (RetainedProbe is null) { RetiredFailure = "missing-probe"; return; }
        var thread = new Thread(() =>
        {
            try { RetainedProbe.Invoke(null, null); RetiredProbeRan = true; }
            catch (Exception error) { RetiredFailure = (error is TargetInvocationException && error.InnerException is not null
                ? error.InnerException : error).GetType().Name; }
        });
        using (ExecutionContext.SuppressFlow()) thread.Start();
        thread.Join(10000);
    }

    public static void InvokeOther()
    {
        if (OtherProbe is null) { ConflictFailure = "missing-probe"; return; }
        try { OtherProbe.Invoke(null, null); ConflictProbeRan = true; }
        catch (Exception error) { ConflictFailure = (error is TargetInvocationException && error.InnerException is not null
            ? error.InnerException : error).GetType().Name; }
    }

    [System.Diagnostics.StackTraceHidden]
    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    private static void InvokeAuthorHidden(MethodInfo probe) => probe.Invoke(null, null);

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.AggressiveInlining)]
    private static void InvokeAuthorInlined(MethodInfo probe) => probe.Invoke(null, null);

    public static void RunChild(MethodInfo probe, bool suppressFlow, bool useTask, int timeoutMs = 15000,
        bool hiddenFrame = false, bool inlinedFrame = false)
    {
        ParentThreadId = Environment.CurrentManagedThreadId;
        FlowMarker.Value = "scheduled";
        Action child = () =>
        {
            ChildThreadId = Environment.CurrentManagedThreadId;
            ChildFlowAbsent = FlowMarker.Value is null;
            try
            {
                if (hiddenFrame) InvokeAuthorHidden(probe);
                else if (inlinedFrame) InvokeAuthorInlined(probe);
                else probe.Invoke(null, null);
                ChildProbeRan = true;
            }
            catch (Exception error)
            {
                ChildFailure = (error is TargetInvocationException && error.InnerException is not null
                    ? error.InnerException : error).GetType().Name;
            }
        };

        if (useTask)
        {
            Task task;
            if (suppressFlow)
            {
                using (ExecutionContext.SuppressFlow()) task = Task.Run(child);
            }
            else
            {
                task = Task.Run(child);
            }
            task.Wait(timeoutMs);
        }
        else
        {
            Thread thread;
            if (suppressFlow)
            {
                using (ExecutionContext.SuppressFlow())
                {
                    thread = new Thread(() => child());
                    thread.Start();
                }
            }
            else
            {
                thread = new Thread(() => child());
                thread.Start();
            }
            thread.Join(timeoutMs);
        }
        FlowMarker.Value = null;
    }

    /// <summary>Loads one helper assembly into distinct collectible contexts and chains them
    /// so a single call nests that many foreign ALC frames.</summary>
    public static void BuildOverflowChain(byte[] helperBytes, string typeName, string methodName, int depth)
    {
        ChainDepth = 0;
        ChainCompleted = false;
        ChainFailure = "";
        ChainLeafFailure = "";
        Action chain = () =>
        {
            // The author sets the retained probe during OnStart, before the chain is entered.
            var probe = RetainedProbe;
            if (probe is null) { ChainLeafFailure = "missing-probe"; return; }
            try { probe.Invoke(null, null); }
            catch (Exception error) { ChainLeafFailure = Describe(error); }
        };
        for (var index = 0; index < depth; index++)
        {
            var context = new AssemblyLoadContext("session-origin-chain-" + index, isCollectible: true);
            var assembly = context.LoadFromStream(new MemoryStream(helperBytes));
            var method = assembly.GetType(typeName, throwOnError: true)!.GetMethod(methodName,
                BindingFlags.Public | BindingFlags.Static)
                ?? throw new InvalidOperationException("The chain helper method is missing.");
            var step = method.CreateDelegate<Action<Action>>();
            ChainContexts.Add(context);
            var next = chain;
            var level = index + 1;
            chain = () =>
            {
                ChainDepth = Math.Max(ChainDepth, level);
                step(next);
            };
        }
        OverflowChain = chain;
    }

    public static void RunOverflowChain()
    {
        try { OverflowChain?.Invoke(); ChainCompleted = true; }
        catch (Exception error) { ChainFailure = Describe(error); }
    }

    /// <summary>Starts an author frame on a suppressed-flow thread and leaves it parked.</summary>
    public static void StartBlockingChild(MethodInfo probe)
    {
        BlockingParked.Reset();
        BlockingRelease.Reset();
        var thread = new Thread(() =>
        {
            try { probe.Invoke(null, null); }
            catch (Exception error) { ChildFailure = Describe(error); }
        });
        using (ExecutionContext.SuppressFlow()) thread.Start();
        BlockingChild = thread;
    }

    public static bool WaitChildParked(int timeoutMs) => BlockingParked.Wait(timeoutMs);

    public static bool ReleaseBlockingChild(int joinMs)
    {
        BlockingRelease.Set();
        return BlockingChild?.Join(joinMs) == true;
    }

    public static void ParkUntilReleased(int timeoutMs)
    {
        BlockingParked.Set();
        BlockingRelease.Wait(timeoutMs);
    }

    private static string Describe(Exception error)
    {
        var inner = error is TargetInvocationException { InnerException: not null } wrapped ? wrapped.InnerException! : error;
        return inner.GetType().FullName ?? inner.GetType().Name;
    }

    /// <summary>Suppressed-flow child with no author frame that attempts the forbidden
    /// reflection. The outcome is recorded, never asserted as an escape.</summary>
    public static void RunCompiledOnlySuppressed()
    {
        var thread = new Thread(() =>
        {
            CompiledOnlySuppressedRan = true;
            try
            {
                typeof(OriginHooks).GetMethod(nameof(ForbiddenEffect))!.Invoke(null, null);
                CompiledOnlyEscaped = true;
            }
            catch (Exception error)
            {
                CompiledOnlyFailure = Describe(error);
            }
        });
        using (ExecutionContext.SuppressFlow()) thread.Start();
        thread.Join(10000);
    }
}
