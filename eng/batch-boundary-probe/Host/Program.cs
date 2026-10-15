using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text.Json;
using BatchBoundary.Contract;

if (args.Length != 4) throw new ArgumentException("Expected author DLL, output file, interval and nonce.");
string author = Path.GetFullPath(args[0]), output = Path.GetFullPath(args[1]), nonce = args[3];
int interval = int.Parse(args[2]);
if (interval is not (1 or 100 or 1000) || nonce.Length != 32 || !nonce.All(Uri.IsHexDigit))
    throw new ArgumentException("Invalid owned interval/nonce.");
Api.Bind();
string authorHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(author)));
long[] limits = [1, interval - 1, interval, interval + 1];
var rows = new List<Row>();
foreach (string method in new[] { "ShortReturn", "OrdinaryThrow", "FiniteProgress" })
{
    Result high = RunFrame(author, method, 1_000_000);
    Collect(high.Context);
    rows.Add(new("calibration", "high", 1_000_000, method, high.Scalars, !high.Context.IsAlive));
}
for (int i = 0; i < limits.Length; i++)
{
    long limit = limits[i];
    string label = new[] { "one", "N-minus-one", "N", "N-plus-one" }[i];
    if (limit == 0)
    {
        bool rejected = false;
        try { var invalid = Api.Create(author, limit); invalid.Unload(); }
        catch (ArgumentOutOfRangeException) { rejected = true; }
        if (!rejected) throw new InvalidOperationException("Zero-budget create was not rejected.");
        rows.Add(new("zero-budget-rejected", label, limit, "Create", null, null));
        Recovery(author, rows, label, limit);
        continue;
    }
    foreach (string method in new[] { "ShortReturn", "OrdinaryThrow", "FiniteProgress", "EndlessCatch" })
    {
        Result actual = RunFrame(author, method, limit);
        Collect(actual.Context);
        rows.Add(new("boundary", label, limit, method, actual.Scalars, !actual.Context.IsAlive));
        Recovery(author, rows, label, limit);
    }
}
if (authorHash != Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(author))))
    throw new InvalidOperationException("Author bytes changed.");
File.WriteAllText(output, JsonSerializer.Serialize(new
{
    observed = true, processId = Environment.ProcessId, nonce, interval, limits, authorHash, rows,
    runtime = RuntimeInformation.FrameworkDescription, architecture = RuntimeInformation.ProcessArchitecture.ToString(),
    capabilities = Api.Capabilities, configuredInterval = Environment.GetEnvironmentVariable("RUNECLR_BATCH_TEST_SWITCH") is { } key ? Environment.GetEnvironmentVariable(key) : null,
    performanceMeasured = false, nativeEntryProof = false, liveBatchPathVerified = false,
    scope = "Pure author local loops and host-owned scalar markers, finite-finally progress capture, existing native getters after frame return; no independent dispatch oracle, timing, concurrency, broad cleanup/finalizer or mobile acceptance."
}, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine($"BATCH_BOUNDARY_COMPLETE nonce={nonce} pid={Environment.ProcessId} N={interval} rows={rows.Count}");

static void Recovery(string author, List<Row> rows, string label, long limit)
{
    Result good = RunFrame(author, "FiniteProgress", 1_000_000);
    Collect(good.Context);
    if (!good.Scalars.Returned || good.Scalars.Value != 21 || good.Scalars.ErrorType is not null ||
        good.Scalars.Progress != new Markers(1, 7, 0, 1, 0, true) || good.Scalars.Snapshot.IsTerminated)
        throw new InvalidOperationException("Same-process recovery differs.");
    rows.Add(new("recovery", label, limit, "FiniteProgress", good.Scalars, !good.Context.IsAlive));
}

[MethodImpl(MethodImplOptions.NoInlining)]
static Result RunFrame(string author, string method, long limit)
{
    Progress.Reset();
    AssemblyLoadContext context = Api.Create(author, limit);
    var weak = new WeakReference(context);
    bool returned = false;
    int value = 0;
    string? errorType = null;
    try
    {
        try
        {
            MethodInfo entry = context.LoadFromAssemblyPath(author).GetType("BatchBoundary.Author.Entries", true)!.GetMethod(method)!;
            value = entry.CreateDelegate<Func<int>>()();
            returned = true;
        }
        catch (Exception e) { errorType = e.GetType().FullName; }
        var progress = new Markers(Progress.Starts, Progress.CompletedIterations, Progress.Catches, Progress.ReturnedMarkers, Progress.FinallyMarkers, Progress.ProgressObserved);
        Snapshot first = Api.Read(context), second = Api.Read(context);
        if (first != second) throw new InvalidOperationException("Read-only post-frame snapshot drift.");
        return new(weak, new(returned, value, errorType, progress, first));
    }
    finally { context.Unload(); Api.Retired(context); }
}

static void Collect(WeakReference weak)
{
    for (int i = 0; i < 12 && weak.IsAlive; i++) { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }
    if (weak.IsAlive) throw new InvalidOperationException("Context retained after the author frame returned.");
}

sealed record Row(string Role, string LimitLabel, long Limit, string Method, Scalars? Observations, bool? Collected);
sealed record Result(WeakReference Context, Scalars Scalars);
sealed record Scalars(bool Returned, int Value, string? ErrorType, Markers Progress, Snapshot Snapshot);
sealed record Markers(int Starts, int CompletedIterations, int Catches, int ReturnedMarkers, int FinallyMarkers, bool ProgressObserved);
readonly record struct Snapshot(long Remaining, long Executed, bool Exhausted, bool IsTerminated, int Reason, int Phase, long CleanupRemaining, long CleanupExecuted);

static class Api
{
    private static Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, long, AssemblyLoadContext> create = null!;
    private static Func<AssemblyLoadContext, long> remaining = null!, executed = null!, cleanupRemaining = null!, cleanupExecuted = null!;
    private static Func<AssemblyLoadContext, bool> exhausted = null!, terminated = null!;
    private static Func<AssemblyLoadContext, int> reason = null!, phase = null!, policy = null!;
    public static object Capabilities { get; private set; } = null!;
    public static void Bind()
    {
        const BindingFlags f = BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance | BindingFlags.DeclaredOnly;
        MethodInfo Method(string n)
        {
            MethodInfo m = typeof(AssemblyLoadContext).GetMethod(n, f) ?? throw new PlatformNotSupportedException("Missing private bridge " + n);
            if (!m.IsPrivate) throw new PlatformNotSupportedException("Non-private bridge " + n);
            return m;
        }
        int version = Method("RuneCLR_GetTerminalPrototypeVersion").CreateDelegate<Func<int>>()();
        if (version != 1) throw new PlatformNotSupportedException("Terminal API version differs.");
        create = Method("RuneCLR_CreateTerminalPrototype").CreateDelegate<Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, long, AssemblyLoadContext>>();
        remaining = Method("RuneCLR_GetInstructionMeterRemaining").CreateDelegate<Func<AssemblyLoadContext, long>>();
        executed = Method("RuneCLR_GetInstructionMeterExecuted").CreateDelegate<Func<AssemblyLoadContext, long>>();
        exhausted = Method("RuneCLR_GetInstructionMeterExhausted").CreateDelegate<Func<AssemblyLoadContext, bool>>();
        terminated = Method("RuneCLR_GetTerminalPrototypeIsTerminated").CreateDelegate<Func<AssemblyLoadContext, bool>>();
        reason = Method("RuneCLR_GetTerminalPrototypeReason").CreateDelegate<Func<AssemblyLoadContext, int>>();
        phase = Method("RuneCLR_GetTerminalPrototypePhase").CreateDelegate<Func<AssemblyLoadContext, int>>();
        cleanupRemaining = Method("RuneCLR_GetTerminalPrototypeCleanupRemaining").CreateDelegate<Func<AssemblyLoadContext, long>>();
        cleanupExecuted = Method("RuneCLR_GetTerminalPrototypeCleanupExecuted").CreateDelegate<Func<AssemblyLoadContext, long>>();
        policy = Method("RuneCLR_GetExecutionPolicy").CreateDelegate<Func<AssemblyLoadContext, int>>();
        Capabilities = new { terminalVersion = version, privateBridge = true };
    }
    public static AssemblyLoadContext Create(string author, long limit)
    {
        var context = create("batch-boundary-" + Guid.NewGuid().ToString("N"), (owner, name) =>
            name.Name == typeof(Progress).Assembly.GetName().Name ? typeof(Progress).Assembly : null, limit, 4096);
        if (!context.IsCollectible || policy(context) != 1 || Read(context) != new Snapshot(limit, 0, false, false, 0, 0, 4096, 0))
            throw new InvalidOperationException("Exact initial context acknowledgement differs.");
        return context;
    }
    public static Snapshot Read(AssemblyLoadContext c) => new(remaining(c), executed(c), exhausted(c), terminated(c), reason(c), phase(c), cleanupRemaining(c), cleanupExecuted(c));
    public static void Retired(AssemblyLoadContext c)
    {
        int rejected = 0;
        Action[] getters = [() => remaining(c), () => executed(c), () => exhausted(c), () => terminated(c), () => reason(c), () => phase(c), () => cleanupRemaining(c), () => cleanupExecuted(c)];
        foreach (Action get in getters) { try { get(); } catch (InvalidOperationException) { rejected++; } }
        if (rejected != 8) throw new InvalidOperationException("Retired binder queries were not rejected.");
    }
}
