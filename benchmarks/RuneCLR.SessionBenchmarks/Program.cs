using System.Diagnostics;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using System.Text.Json;
using RuneCLR.Runtime;

if (args.Length > 1) throw new ArgumentException("Usage: RuneCLR.SessionBenchmarks [samples | --cold]");
bool cold = args.Contains("--cold");
int samples = cold || args.Length == 0 ? 7 : int.Parse(args[0]);
if (samples <= 0) throw new ArgumentOutOfRangeException(nameof(samples));
var runner = new MapRunner();
var empty = MapPackage.FromManifest(Path.Combine(AppContext.BaseDirectory, "fixtures/empty-map.json"));
var gameplay = MapPackage.FromManifest(Path.Combine(AppContext.BaseDirectory, "fixtures/map.json"));

if (cold)
{
    var measurement = Measure(runner, empty, 0);
    Write(new { kind = "cold", name = "empty-first-map", measurement.ms, measurement.allocatedBytes, measurement.gcCounts,
        scope = "first MapRunner.Run only; manifest read excluded; process startup measured by launcher" });
    return;
}

// Diagnostic inspection is separate from the measurement. Only primitive data
// crosses this no-inline frame; no collectible Type/MethodInfo/ALC survives it.
var proofRun = RunChecked(runner, gameplay, 128);
var proof = InspectExecutedMethods(proofRun.Unload, gameplay.EntryType);
var emptyProofRun = RunChecked(runner, empty, 1);
proof.AddRange(InspectExecutedMethods(emptyProofRun.Unload, empty.EntryType));
foreach (var entry in proof) Write(entry);
Collect();
if (!proofRun.Unload.IsCollected || !emptyProofRun.Unload.IsCollected)
    throw new InvalidOperationException("Execution probe retained the map context.");

foreach (var test in new[] { (Name: "empty-session", Package: empty, Ticks: 0),
    (Name: "gameplay-start", Package: gameplay, Ticks: 0),
    (Name: "gameplay-128-ticks", Package: gameplay, Ticks: 128) })
{
    for (int i = 0; i < 3; i++) RunChecked(runner, test.Package, test.Ticks);
    Collect(); // after warmup, never inside an individual timed session
    var times = new List<double>();
    var allocatedBytes = new List<long>();
    var gcCounts = new List<int[]>();
    var tickets = new List<UnloadTicket>();
    for (int i = 0; i < samples; i++)
    {
        var measurement = Measure(runner, test.Package, test.Ticks);
        times.Add(measurement.ms);
        allocatedBytes.Add(measurement.allocatedBytes);
        gcCounts.Add(measurement.gcCounts);
        tickets.Add(measurement.ticket);
    }
    int collectedBeforeDiagnosticGc = tickets.Count(ticket => ticket.IsCollected);
    Collect();
    int collectedAfterDiagnosticGc = tickets.Count(ticket => ticket.IsCollected);
    if (collectedAfterDiagnosticGc != samples) throw new InvalidOperationException("A session context survived diagnostic GC.");
    Write(new { kind = "session", name = test.Name, times, allocatedBytes, gcCounts, warmups = 3, ticks = test.Ticks,
        collectedBeforeDiagnosticGc, collectedAfterDiagnosticGc,
        scope = "fresh collectible ALC per sample; MapRunner.Run includes loading, activation, first-use compilation, callbacks, cleanup and unload request; manifest excluded" });
}

Collect();
var before = Snapshot();
var retainedTickets = new List<UnloadTicket>(40);
var retentionTimes = new List<double>(40);
for (int i = 0; i < 40; i++)
{
    var measurement = Measure(runner, gameplay, 128);
    retainedTickets.Add(measurement.ticket);
    retentionTimes.Add(measurement.ms);
}
var afterSessions = Snapshot();
int collectedBefore = retainedTickets.Count(ticket => ticket.IsCollected);
Collect();
var afterDiagnosticGc = Snapshot();
int collectedAfter = retainedTickets.Count(ticket => ticket.IsCollected);
if (collectedAfter != 40) throw new InvalidOperationException("Repeated-session context retention detected.");
Write(new { kind = "retention", sessions = 40, ticksPerSession = 128, before, afterSessions, afterDiagnosticGc,
    collectedBefore, collectedAfter, times = retentionTimes,
    scope = "snapshots from one process; no forced GC between the 40 sessions; full GC after stack return is diagnostic only" });

static void Write(object value) => Console.WriteLine(JsonSerializer.Serialize(value));

[MethodImpl(MethodImplOptions.NoInlining)]
static (double ms, long allocatedBytes, int[] gcCounts, UnloadTicket ticket) Measure(MapRunner runner, MapPackage package, int ticks)
{
    var options = Options(ticks);
    long allocatedBefore = GC.GetAllocatedBytesForCurrentThread();
    int gen0 = GC.CollectionCount(0), gen1 = GC.CollectionCount(1), gen2 = GC.CollectionCount(2);
    long start = Stopwatch.GetTimestamp();
    MapRunResult result = runner.Run(package, options);
    double ms = Stopwatch.GetElapsedTime(start).TotalMilliseconds;
    long allocated = GC.GetAllocatedBytesForCurrentThread() - allocatedBefore;
    int[] collections = [GC.CollectionCount(0) - gen0, GC.CollectionCount(1) - gen1, GC.CollectionCount(2) - gen2];
    Validate(result.Report, package, ticks);
    return (ms, allocated, collections, result.Unload);
}

static MapRunOptions Options(int ticks) => new() { TickCount = ticks, OperationBudgetPerCallback = 100_000, MaxEntities = 128, MaxLogMessages = 4 };

[MethodImpl(MethodImplOptions.NoInlining)]
static MapRunResult RunChecked(MapRunner runner, MapPackage package, int ticks)
{
    var result = runner.Run(package, Options(ticks));
    Validate(result.Report, package, ticks);
    return result;
}

static void Validate(MapRunReport report, MapPackage package, int ticks)
{
    bool gameplay = package.EntryType.EndsWith("GameplayMap", StringComparison.Ordinal);
    int entities = gameplay ? 64 + ticks * 8 : 0;
    string expected = ticks == 0 ? "session:starts=1;ticks=0;checksum=2576" : "session:starts=1;ticks=128;checksum=916496";
    if (report.Outcome != MapRunOutcome.Completed || report.CompletedTicks != ticks || report.CreatedEntities != entities ||
        report.ReleasedEntities != entities || report.RemainingEntities != 0 || report.Logs.Count != (gameplay ? 1 : 0) ||
        (gameplay && report.Logs[0] != expected))
        throw new InvalidOperationException("Unexpected map outcome/static state/resource accounting: " + JsonSerializer.Serialize(report));
}

static void Collect()
{
    for (int i = 0; i < 3; i++)
    {
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
    }
}

static object Snapshot()
{
    using var process = Process.GetCurrentProcess();
    return new { managedBytes = GC.GetTotalMemory(false), gcHeapBytes = GC.GetGCMemoryInfo().HeapSizeBytes,
        privateBytes = process.PrivateMemorySize64, workingSetBytes = process.WorkingSet64,
        gcCounts = new[] { GC.CollectionCount(0), GC.CollectionCount(1), GC.CollectionCount(2) } };
}

[MethodImpl(MethodImplOptions.NoInlining)]
static List<ExecutionEntry> InspectExecutedMethods(UnloadTicket ticket, string entryTypeName)
{
    // Deliberately diagnostic-only coupling to the current host's weak ticket.
    // Hold the context while reading code, then release all metadata on return.
    var weak = (WeakReference)typeof(UnloadTicket).GetField("_context", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(ticket)!;
    var context = weak.Target as AssemblyLoadContext ?? throw new InvalidOperationException("Map collected before execution inspection.");
    var assembly = context.Assemblies.Single(item => item.GetName().Name == "RuneCLR.SessionMap");
    Type type = assembly.GetType(entryTypeName, true)!;
    var methods = new List<MethodInfo>();
    foreach (string name in new[] { "OnStart", "OnTick", "OnStop" })
        methods.Add(type.GetMethod(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static)!);
    if (entryTypeName.EndsWith("GameplayMap", StringComparison.Ordinal))
    {
        methods.Add(type.GetMethod("AllocateGroups", BindingFlags.NonPublic | BindingFlags.Static)!);
        methods.Add(type.GetMethod("Sum", BindingFlags.NonPublic | BindingFlags.Static)!.MakeGenericMethod(typeof(int)));
    }
    var entries = methods.Select(method => Inspect("execution", method)).ToList();
    entries.Add(Inspect("host-execution", typeof(MapRunner).GetMethod(nameof(MapRunner.Run))!));
    GC.KeepAlive(context);
    return entries;
}

static ExecutionEntry Inspect(string kind, MethodInfo method)
{
    if (!OperatingSystem.IsWindows() || RuntimeInformation.ProcessArchitecture != Architecture.X64)
        throw new PlatformNotSupportedException("The pinned execution probe supports Windows x64 only.");
    nint entry = method.MethodHandle.GetFunctionPointer();
    nint code = entry;
    if (Marshal.ReadByte(entry) == 0xff && Marshal.ReadByte(entry, 1) == 0x25)
        code = Marshal.ReadIntPtr(entry + 6 + Marshal.ReadInt32(entry, 2));
    bool stub = Marshal.ReadByte(code) == 0x4c && Marshal.ReadByte(code, 1) == 0x8b &&
        Marshal.ReadByte(code, 2) == 0x15 && Marshal.ReadByte(code, 7) == 0xff && Marshal.ReadByte(code, 8) == 0x25;
    int stubType = stub ? Marshal.ReadByte(code + 7 + Marshal.ReadInt32(code, 3) + 16) : -1;
    var bytes = new byte[16];
    Marshal.Copy(code, bytes, 0, bytes.Length);
    return new(kind, method.DeclaringType!.FullName + "." + method.Name, stub && stubType == 6, stubType, Convert.ToHexString(bytes));
}

sealed record ExecutionEntry(string kind, string method, bool interpreted, int type, string bytes);
