using System.Diagnostics;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using System.Text.Json;
using RuneCLR.Runtime;

if (args.Length != 4 || args[1] is not ("no-config" or "high-budget"))
    throw new ArgumentException("Usage: BudgetOverhead <author.dll> <no-config|high-budget> <nonce> <samples>");
string authorPath = Path.GetFullPath(args[0]);
bool budget = args[1] == "high-budget";
int samples = int.Parse(args[3]);
if (samples < 3 || samples > 100) throw new ArgumentOutOfRangeException(nameof(samples));
long affinity;
if (OperatingSystem.IsWindows())
{
    using var process = Process.GetCurrentProcess();
    process.ProcessorAffinity = (nint)4;
    affinity = process.ProcessorAffinity.ToInt64();
    if (affinity != 4) throw new InvalidOperationException("Logical processor2 affinity not acknowledged.");
}
else throw new PlatformNotSupportedException("The pinned observer supports Windows x64 only.");
var bridge = new PrivateBridge();
var direct = MeasureCallbacks(bridge, authorPath, budget, samples);
Collect();
if (direct.Weak.IsAlive) throw new InvalidOperationException("Direct callback context retained.");
var session = MeasureSessions(authorPath, budget, samples);
Collect();
if (session.Tickets.Any(ticket => !ticket.IsCollected)) throw new InvalidOperationException("Host session context retained.");
var hostProof = Inspect(typeof(MapRunner).GetMethod(nameof(MapRunner.Run))!);
if (hostProof.Interpreted) throw new InvalidOperationException("Trusted MapRunner unexpectedly interpreted.");
Console.WriteLine(JsonSerializer.Serialize(new { passed = true, processId = Environment.ProcessId, nonce = args[2],
    mode = args[1], runtime = RuntimeInformation.FrameworkDescription, architecture = RuntimeInformation.ProcessArchitecture.ToString(),
    budgetLimit = budget ? PrivateBridge.Limit : (long?)null, cleanupLimit = 4096, iterations = 100_000,
    warmups = 3, sampleCount = samples, affinity, hostProof, direct.SetupMilliseconds, direct.WarmupMilliseconds, direct.Callbacks, direct.Proof,
    direct.FinalSnapshot, directCollected = !direct.Weak.IsAlive, session.Samples, sessionCollected = session.Tickets.Count(ticket => ticket.IsCollected),
    baseline = "same instrumented runtime; no-config retains definition-owner lookup and null-meter branch; not compile-time instrumentation-off" }));

[MethodImpl(MethodImplOptions.NoInlining)]
static DirectResult MeasureCallbacks(PrivateBridge bridge, string path, bool budget, int samples)
{
    long started = Stopwatch.GetTimestamp();
    var context = bridge.Create(budget);
    var weak = new WeakReference(context);
    try
    {
        if (!context.IsCollectible || bridge.Policy(context) != 1) throw new InvalidOperationException("Native required policy missing.");
        var assembly = context.LoadFromAssemblyPath(path);
        var type = assembly.GetType("RuneCLR.BudgetKernel.Kernel", true)!;
        var execute = type.GetMethod("Execute")!;
        var update = type.GetMethod("Update", BindingFlags.NonPublic | BindingFlags.Static)!;
        var callback = execute.CreateDelegate<Func<int, long>>();
        double setup = Stopwatch.GetElapsedTime(started).TotalMilliseconds;
        long expected = Oracle(100_000);
        var warmups = new List<double>();
        for (int i = 0; i < 3; i++)
        {
            started = Stopwatch.GetTimestamp();
            long value = callback(100_000);
            warmups.Add(Stopwatch.GetElapsedTime(started).TotalMilliseconds);
            if (value != expected) throw new InvalidOperationException("Warmup checksum mismatch.");
        }
        var proof = new[] { Inspect(execute), Inspect(update) };
        if (proof.Any(item => !item.Interpreted)) throw new InvalidOperationException("Author method entry not interpreted.");
        var measurements = new List<CallbackSample>();
        for (int i = 0; i < samples; i++)
        {
            var before = budget ? bridge.Snapshot(context) : null;
            long allocations = GC.GetAllocatedBytesForCurrentThread();
            int gen0 = GC.CollectionCount(0), gen1 = GC.CollectionCount(1), gen2 = GC.CollectionCount(2);
            started = Stopwatch.GetTimestamp();
            long value = callback(100_000);
            double ms = Stopwatch.GetElapsedTime(started).TotalMilliseconds;
            long allocated = GC.GetAllocatedBytesForCurrentThread() - allocations;
            var after = budget ? bridge.Snapshot(context) : null;
            if (value != expected || (after is not null && (after.IsTerminated || after.Reason != 0)))
                throw new InvalidOperationException("Sample checksum or native budget latch mismatch.");
            measurements.Add(new(ms, value, allocated, [GC.CollectionCount(0)-gen0, GC.CollectionCount(1)-gen1, GC.CollectionCount(2)-gen2],
                before?.ExecutionExecuted, after?.ExecutionExecuted, before is null ? null : after!.ExecutionExecuted-before.ExecutionExecuted));
        }
        var final = budget ? bridge.Snapshot(context) : null;
        GC.KeepAlive(callback);
        return new(setup, warmups, measurements, proof, final, weak);
    }
    finally { context.Unload(); }
}

[MethodImpl(MethodImplOptions.NoInlining)]
static SessionResult MeasureSessions(string path, bool budget, int samples)
{
    var package = new MapPackage("budget-overhead", path, "RuneCLR.BudgetKernel.KernelMap");
    var runner = new MapRunner();
    var options = new MapRunOptions { ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
        PrototypeInstructionBudget = budget ? PrivateBridge.Limit : null, PrototypeCleanupInstructionBudget = 4096,
        TickCount = 3, MaxLogMessages = 1 };
    var all = new List<SessionSample>();
    var tickets = new List<UnloadTicket>();
    long expected = 3 * Oracle(100_000);
    for (int i = -3; i < samples; i++)
    {
        long start = Stopwatch.GetTimestamp();
        var result = runner.Run(package, options);
        double ms = Stopwatch.GetElapsedTime(start).TotalMilliseconds;
        var report = result.Report;
        if (report.Outcome != MapRunOutcome.Completed || report.CompletedTicks != 3 || report.RemainingEntities != 0 ||
            report.Logs.Count != 1 || report.Logs[0] != "budget-kernel:sum=" + expected || report.ExecutionPolicyVersion != 1 ||
            (budget ? report.PrototypeBudget is null || report.PrototypeBudget.IsTerminated : report.PrototypeBudget is not null))
            throw new InvalidOperationException("Host budget option/session checksum mismatch.");
        all.Add(new(i < 0, ms, expected, report.PrototypeBudget));
        tickets.Add(result.Unload);
    }
    return new(all, tickets);
}

static long Oracle(int iterations)
{
    uint state = 12345;
    long checksum = 0;
    for (int i = 0; i < iterations; i++) { state = unchecked(state * 1664525u + 1013904223u); checksum += state & 255; }
    return checksum;
}

static EntryProof Inspect(MethodInfo method)
{
    if (!OperatingSystem.IsWindows() || RuntimeInformation.ProcessArchitecture != Architecture.X64)
        throw new PlatformNotSupportedException("Pinned method-entry observer is Windows x64 only.");
    nint entry = method.MethodHandle.GetFunctionPointer(), code = entry;
    if (Marshal.ReadByte(entry) == 0xff && Marshal.ReadByte(entry, 1) == 0x25)
        code = Marshal.ReadIntPtr(entry + 6 + Marshal.ReadInt32(entry, 2));
    bool stub = Marshal.ReadByte(code) == 0x4c && Marshal.ReadByte(code, 1) == 0x8b && Marshal.ReadByte(code, 2) == 0x15 &&
        Marshal.ReadByte(code, 7) == 0xff && Marshal.ReadByte(code, 8) == 0x25;
    int stubType = stub ? Marshal.ReadByte(code + 7 + Marshal.ReadInt32(code, 3) + 16) : -1;
    var bytes = new byte[16];
    Marshal.Copy(code, bytes, 0, bytes.Length);
    return new(method.DeclaringType!.FullName + "." + method.Name, method.MetadataToken.ToString("x8"),
        stub && stubType == 6, stubType, Convert.ToHexString(bytes));
}

static void Collect()
{
    for (int i = 0; i < 3; i++) { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }
}

sealed record EntryProof(string Method, string Token, bool Interpreted, int StubType, string Bytes);
sealed record CallbackSample(double Milliseconds, long Checksum, long AllocatedBytes, int[] GcCounts, long? ExecutedBefore, long? ExecutedAfter, long? DispatchDelta);
sealed record SessionSample(bool Warmup, double Milliseconds, long Checksum, PrototypeBudgetSnapshot? Budget);
sealed record DirectResult(double SetupMilliseconds, List<double> WarmupMilliseconds, List<CallbackSample> Callbacks, EntryProof[] Proof, PrototypeBudgetSnapshot? FinalSnapshot, WeakReference Weak);
sealed record SessionResult(List<SessionSample> Samples, List<UnloadTicket> Tickets);

sealed class PrivateBridge
{
    public const long Limit = 1_000_000_000_000;
    private readonly Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, AssemblyLoadContext> _required;
    private readonly Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, long, AssemblyLoadContext> _terminal;
    public readonly Func<AssemblyLoadContext, int> Policy;
    private readonly Func<AssemblyLoadContext, long> _remaining, _executed, _cleanupRemaining, _cleanupExecuted;
    private readonly Func<AssemblyLoadContext, bool> _exhausted, _terminated;
    private readonly Func<AssemblyLoadContext, int> _reason, _phase;
    public PrivateBridge()
    {
        if (Bind<Func<int>>("RuneCLR_GetExecutionPolicyVersion", true)() != 1 ||
            Bind<Func<int>>("RuneCLR_GetTerminalPrototypeVersion", true)() != 1 ||
            Bind<Func<int>>("RuneCLR_GetTerminalFinalizerBoundaryVersion", true, typeof(GC))() != 1)
            throw new PlatformNotSupportedException("Private policy/terminal/finalizer version must be 1.");
        _required = Bind<Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, AssemblyLoadContext>>("RuneCLR_CreateInterpreterRequired", true);
        _terminal = Bind<Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, long, AssemblyLoadContext>>("RuneCLR_CreateTerminalPrototype", true);
        Policy = Bind<Func<AssemblyLoadContext, int>>("RuneCLR_GetExecutionPolicy", false);
        _remaining = Bind<Func<AssemblyLoadContext, long>>("RuneCLR_GetInstructionMeterRemaining", false);
        _executed = Bind<Func<AssemblyLoadContext, long>>("RuneCLR_GetInstructionMeterExecuted", false);
        _cleanupRemaining = Bind<Func<AssemblyLoadContext, long>>("RuneCLR_GetTerminalPrototypeCleanupRemaining", false);
        _cleanupExecuted = Bind<Func<AssemblyLoadContext, long>>("RuneCLR_GetTerminalPrototypeCleanupExecuted", false);
        _exhausted = Bind<Func<AssemblyLoadContext, bool>>("RuneCLR_GetInstructionMeterExhausted", false);
        _terminated = Bind<Func<AssemblyLoadContext, bool>>("RuneCLR_GetTerminalPrototypeIsTerminated", false);
        _reason = Bind<Func<AssemblyLoadContext, int>>("RuneCLR_GetTerminalPrototypeReason", false);
        _phase = Bind<Func<AssemblyLoadContext, int>>("RuneCLR_GetTerminalPrototypePhase", false);
    }
    public AssemblyLoadContext Create(bool budget)
    {
        Func<AssemblyLoadContext, AssemblyName, Assembly?> resolver = (_, name) =>
            name.Name == typeof(RuneCLR.IMapScript).Assembly.GetName().Name ? typeof(RuneCLR.IMapScript).Assembly : null;
        var context = budget ? _terminal("budget-overhead", resolver, Limit, 4096) : _required("budget-overhead", resolver);
        if (budget && Snapshot(context) != new PrototypeBudgetSnapshot(Limit, 0, false, false, 0, 0, 4096, 0))
        { context.Unload(); throw new InvalidOperationException("Initial native budget acknowledgement mismatch."); }
        return context;
    }
    public PrototypeBudgetSnapshot Snapshot(AssemblyLoadContext context) => new(_remaining(context), _executed(context), _exhausted(context),
        _terminated(context), _reason(context), _phase(context), _cleanupRemaining(context), _cleanupExecuted(context));
    private static T Bind<T>(string name, bool isStatic, Type? owner = null) where T : Delegate
    {
        owner ??= typeof(AssemblyLoadContext);
        var invoke = typeof(T).GetMethod("Invoke")!;
        var parameters = invoke.GetParameters().Select(parameter => parameter.ParameterType).ToArray();
        if (!isStatic) parameters = parameters.Skip(1).ToArray();
        var method = owner.GetMethod(name, BindingFlags.NonPublic | BindingFlags.DeclaredOnly | (isStatic ? BindingFlags.Static : BindingFlags.Instance),
            null, parameters, null);
        if (method is null || !method.IsPrivate || method.IsStatic != isStatic || method.ReturnType != invoke.ReturnType || method.IsGenericMethod)
            throw new PlatformNotSupportedException("Private exact CoreLib signature missing: " + name);
        return method.CreateDelegate<T>();
    }
}
