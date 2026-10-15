using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using RuneCLR.Performance;

bool extendedOnly = args.Contains("--extended-only");
bool extended = extendedOnly || args.Contains("--extended");
string[] sampleArguments = args.Where(arg => !arg.StartsWith("--", StringComparison.Ordinal)).ToArray();
if (sampleArguments.Length > 1 || args.Any(arg => arg.StartsWith("--", StringComparison.Ordinal) &&
    arg is not ("--extended" or "--extended-only")))
    throw new ArgumentException("Usage: RuneCLR.PerformanceHost [samples] [--extended | --extended-only]");
int samples = sampleArguments.Length == 0 ? 7 : int.Parse(sampleArguments[0]);
if (samples <= 0) throw new ArgumentOutOfRangeException(nameof(samples));
const int count = 4096, ticks = 256, iterations = 1_000_000;
var cases = new List<(string Name, string Method, Func<Func<long>> Prepare)>
{
    ("numeric", nameof(Workloads.Numeric), () => () => Workloads.Numeric(iterations)),
    ("entities-soa", nameof(Workloads.EntitiesSoA), () =>
    {
        var d = new SoA(count);
        for (int i = 0; i < count; i++)
        {
            d.X[i] = i * 13 % 65521; d.Y[i] = i * 7 % 65521;
            d.Vx[i] = 1 + i % 7; d.Vy[i] = 1 + i % 11; d.Hp[i] = 100 + i % 100;
        }
        return () => Workloads.EntitiesSoA(d, ticks);
    }),
    ("entities-objects", nameof(Workloads.EntitiesObjects), () => { var d = CreateEntities(); return () => Workloads.EntitiesObjects(d, ticks); }),
    ("skills", nameof(Workloads.Skills), () => { var d = CreateEntities(); return () => Workloads.Skills(d, ticks); })
};
if (extendedOnly) cases.Clear();
if (extended)
{
    cases.Add(("host-api", nameof(Workloads.HostApi), () =>
    {
        var context = new BenchmarkMapContext();
        return () =>
        {
            long checksum = Workloads.HostApi(context, 131_072);
            context.VerifyCompleted(131_072, 2_048);
            return checksum;
        };
    }));
    cases.Add(("allocations-generics", nameof(Workloads.AllocationsGenerics),
        () => () => Workloads.AllocationsGenerics(256, 128)));
}

foreach (var test in cases)
{
    long expected = 0;
    for (int i = 0; i < 3; i++) expected = test.Prepare()();
    var times = new List<double>();
    var allocatedBytes = new List<long>();
    var gcCounts = new List<int[]>();
    for (int i = 0; i < samples; i++)
    {
        Func<long> run = test.Prepare(); // allocation and initialization are outside timing
        long allocatedBefore = GC.GetAllocatedBytesForCurrentThread();
        int gen0 = GC.CollectionCount(0), gen1 = GC.CollectionCount(1), gen2 = GC.CollectionCount(2);
        long start = Stopwatch.GetTimestamp();
        long checksum = run();
        double ms = Stopwatch.GetElapsedTime(start).TotalMilliseconds;
        long allocated = GC.GetAllocatedBytesForCurrentThread() - allocatedBefore;
        int[] collections = [GC.CollectionCount(0) - gen0, GC.CollectionCount(1) - gen1, GC.CollectionCount(2) - gen2];
        if (checksum != expected) throw new InvalidOperationException("Unstable checksum");
        times.Add(ms);
        allocatedBytes.Add(allocated);
        gcCounts.Add(collections);
    }
    Console.WriteLine(JsonSerializer.Serialize(new { kind = "result", name = test.Name, checksum = expected, times,
        allocatedBytes, gcCounts, warmups = 3, allocationScope = "current-thread timed region",
        gcScope = "process-wide collection counts" }));
}

// Separate from timing: check the actual published code for each workload.
// Windows x64 only, pinned to runtime 0d73c1f's FixupPrecode and InterpreterPrecode layouts.
// Follow the entry's RIP-relative indirect jump, then identify the interpreter stub's
// RIP-relative secret-param load and its data Type=0x06; do not execute or mutate bytes.
var methods = cases.Select(test => typeof(Workloads).GetMethod(test.Method)!).ToList();
if (extended) methods.Add(typeof(Workloads).GetMethod("GenericSum", BindingFlags.NonPublic | BindingFlags.Static)!
    .MakeGenericMethod(typeof(int)));
foreach (MethodInfo method in methods) PrintExecution("execution", method);
if (extended)
    foreach (string name in new[] { "Charge", "SpawnEntity", "DestroyEntity", "Log" })
        PrintExecution("host-execution", typeof(BenchmarkMapContext).GetMethod(name)!);

static void PrintExecution(string kind, MethodInfo method)
{
    nint entry = method.MethodHandle.GetFunctionPointer();
    nint code = entry;
    if (Marshal.ReadByte(entry) == 0xff && Marshal.ReadByte(entry, 1) == 0x25)
        code = Marshal.ReadIntPtr(entry + 6 + Marshal.ReadInt32(entry, 2));
    bool stub = Marshal.ReadByte(code) == 0x4c && Marshal.ReadByte(code, 1) == 0x8b &&
        Marshal.ReadByte(code, 2) == 0x15 && Marshal.ReadByte(code, 7) == 0xff && Marshal.ReadByte(code, 8) == 0x25;
    int type = stub ? Marshal.ReadByte(code + 7 + Marshal.ReadInt32(code, 3) + 16) : -1;
    bool interpreted = stub && type == 6;
    Console.WriteLine(JsonSerializer.Serialize(new { kind, method = method.Name, interpreted, type,
        entry = entry.ToString("x"), code = code.ToString("x"), bytes = ReadBytes(code) }));
}

static Entity[] CreateEntities()
{
    var data = new Entity[count];
    for (int i = 0; i < count; i++)
        data[i] = new Entity { X = i * 13 % 65521, Y = i * 7 % 65521, Vx = 1 + i % 7,
            Vy = 1 + i % 11, Hp = 100 + i % 100, State = 0, Cooldown = 1 + i % 11 };
    return data;
}

static string ReadBytes(nint address)
{
    var bytes = new byte[16]; Marshal.Copy(address, bytes, 0, bytes.Length); return Convert.ToHexString(bytes);
}
