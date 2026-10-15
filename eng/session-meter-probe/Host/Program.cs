using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using System.Text.Json;
using MeterProbe.Contract;

namespace MeterProbe.Host;
internal static class Program
{
    private const long NormalLimit = 1000000;
    private static int trustedSideEffect;
    public static int Main(string[] args)
    {
        Console.SetOut(Console.Error);
        if (args.Length is < 2 or > 3) throw new ArgumentException("Expected payload directory, evidence directory, optional --stock-smoke, --metered-only, --compatibility or --concurrent.");
        string payload = Path.GetFullPath(args[0]);
        string evidence = Path.GetFullPath(args[1]);
        Directory.CreateDirectory(evidence);
        bool stock = args.Length == 3 && args[2] == "--stock-smoke";
        bool concurrent = args.Length == 3 && args[2] == "--concurrent";
        bool meteredOnly = args.Length == 3 && args[2] == "--metered-only";
        bool compatibility = args.Length == 3 && args[2] == "--compatibility";
        if (args.Length == 3 && !stock && !concurrent && !meteredOnly && !compatibility) throw new ArgumentException("Unknown optional mode.");
        if (!stock) Api.Initialize(evidence);
        Console.WriteLine($"METER runtime={System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription} stock={stock.ToString().ToLowerInvariant()}");
        if (compatibility) { Compatibility(payload); Console.WriteLine("METER COMPATIBILITY COMPLETE contexts=2 collected=2"); return 0; }
        for (int session = 1; session <= 20; session++)
        {
            var result = RunFrame(payload, stock ? Kind.Stock : Kind.Metered, NormalLimit, session == 1 ? evidence : null);
            Collect(result.Context);
            Console.WriteLine($"PASS meter-session={session} collected=true values={JsonSerializer.Serialize(result.Values)} deltas={JsonSerializer.Serialize(result.Deltas)} final={JsonSerializer.Serialize(result.Final)}");
        }
        if (!stock)
        {
            Api.AssertInvalidLimit(payload, 0);
            Api.AssertInvalidLimit(payload, -1);
            var tiny = RunFrame(payload, Kind.Metered, 1, null);
            Collect(tiny.Context);
            Check(tiny.Final.Exhausted && tiny.Final.Remaining == 0 && tiny.Final.Executed > 1, "Limit1 did not exhaust diagnostic meter.");
            Console.WriteLine($"PASS boundary-one finite-return=true counting-after-zero=true collected=true executed={tiny.Final.Executed}");
            var maximum = RunFrame(payload, Kind.Metered, long.MaxValue, null);
            Collect(maximum.Context);
            Check(!maximum.Final.Exhausted && maximum.Final.Remaining == long.MaxValue - maximum.Final.Executed, "Max-limit arithmetic differs.");
            Console.WriteLine($"PASS boundary-max collected=true remaining={maximum.Final.Remaining} executed={maximum.Final.Executed}");
            var interleaved = InterleavedFrame(payload);
            Collect(interleaved.Left); Collect(interleaved.Right);
            Console.WriteLine($"PASS interleaved owner-isolation=true returned-owner=true collected=2 left={interleaved.LeftExecuted} right={interleaved.RightExecuted}");
            if (!meteredOnly && !concurrent) Compatibility(payload);
            if (concurrent)
            {
                var result = ConcurrentFrame(payload);
                Collect(result.Context);
                Console.WriteLine($"PASS concurrent trusted-tasks=4 joined-before-snapshot=true value={result.Value} executed={result.Executed} collected=true");
            }
        }
        Console.WriteLine($"METER COMPLETE sessions=20 collected=20 stock={stock.ToString().ToLowerInvariant()} diagnostic-only=true");
        return 0;
    }
    private static void Compatibility(string payload)
    {
        foreach (Kind kind in new[] { Kind.Ordinary, Kind.RequiredUnmetered })
        {
            var result = RunFrame(payload, kind, NormalLimit, null);
            Collect(result.Context);
            Console.WriteLine($"PASS unmetered kind={kind} values-correct=true getters=System.InvalidOperationException collected=true");
        }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static Outcome RunFrame(string directory, Kind kind, long limit, string? evidence)
    {
        AssemblyLoadContext context = Api.Create(directory, kind, limit);
        var weak = new WeakReference(context);
        bool metered = kind == Kind.Metered;
        var deltas = new Dictionary<string, long>();
        var values = new Dictionary<string, int>();
        try
        {
            Snapshot before = metered ? Api.Read(context, limit) : default;
            Check(!metered || before.Executed == 0, "Fresh context already charged.");
            Assembly assembly = context.LoadFromAssemblyPath(Path.Combine(directory, "MeterProbe.Payload.dll"));
            if (metered) Check(Api.Read(context, limit) == before, "Metadata loading charged instructions.");
            Type type = assembly.GetType("MeterUGC.Payload.Entry", true)!;
            RuntimeHelpers.RunClassConstructor(type.TypeHandle);
            Snapshot afterStatic = metered ? Api.Read(context, limit) : default;
            if (metered) { deltas["cctor"] = PositiveDelta(before, afterStatic, "static constructor"); before = afterStatic; }
            IWork work = (IWork)Activator.CreateInstance(type)!;
            Snapshot afterConstructor = metered ? Api.Read(context, limit) : default;
            if (metered) { deltas["constructor"] = PositiveDelta(before, afterConstructor, "constructor"); before = afterConstructor; }
            values["starts"] = work.Starts; values["instances"] = work.Instances;
            Check(values["starts"] == 1 && values["instances"] == 1, "Static state leaked across contexts.");
            values["empty"] = work.Empty();
            Snapshot empty = metered ? Api.Read(context, limit) : default;
            if (metered) { deltas["properties-and-empty"] = PositiveDelta(before, empty, "empty"); before = empty; }
            values["loop"] = work.Loop(1000);
            Snapshot loop = metered ? Api.Read(context, limit) : default;
            if (metered)
            {
                deltas["loop1000"] = PositiveDelta(before, loop, "loop");
                Check(deltas["loop1000"] > deltas["properties-and-empty"] * 10, "Loop did not charge substantially more than empty."); before = loop;
            }
            Check(!context.Assemblies.Any(a => a.GetName().Name == "MeterProbe.Private"), "Private helper loaded before its operation.");
            values["helper"] = work.Helper();
            Check(context.Assemblies.Any(a => a.GetName().Name == "MeterProbe.Private"), "Late private helper not owned by session.");
            Snapshot helper = metered ? Api.Read(context, limit) : default;
            if (metered) { deltas["author-private-helper-return"] = PositiveDelta(before, helper, "private helper"); before = helper; }
            TrustedBusy();
            if (metered) Check(Api.Read(context, limit) == before, "Trusted execution retained author instruction owner after return.");
            values["trusted-callback"] = TrustedCaller.Call(work);
            Snapshot callback = metered ? Api.Read(context, limit) : default;
            if (metered) { deltas["trusted-author-private-return"] = PositiveDelta(before, callback, "trusted callback"); before = callback; }
            MethodInfo definition = typeof(TrustedCaller).GetMethod(nameof(TrustedCaller.Generic))!;
            MethodInfo constructed = definition.MakeGenericMethod(type);
            Check(!definition.Module.Assembly.IsCollectible && constructed.Module == definition.Module && type.Assembly.IsCollectible, "Trusted generic definition ownership differs.");
            values["trusted-generic"] = constructed.CreateDelegate<Func<int>>()();
            Snapshot generic = metered ? Api.Read(context, limit) : default;
            if (metered) { deltas["trusted-generic-author-static"] = PositiveDelta(before, generic, "generic callback"); before = generic; }
            values["paths"] = work.Paths();
            Snapshot paths = metered ? Api.Read(context, limit) : default;
            if (metered) { deltas["direct-virtual-delegate"] = PositiveDelta(before, paths, "paths"); before = paths; }
            values["eh"] = work.Exceptions();
            Snapshot eh = metered ? Api.Read(context, limit) : default;
            if (metered) { deltas["catch-filter-finally"] = PositiveDelta(before, eh, "EH"); before = eh; }
            values["after-zero"] = work.AfterZero();
            Snapshot final = metered ? Api.Read(context, limit) : default;
            if (metered) { deltas["finite-after-zero"] = PositiveDelta(before, final, "finite continuation"); if (limit == 1) Check(before.Exhausted && final.Exhausted, "Finite continuation not actually after zero."); }
            Check(values["empty"] == 7 && values["loop"] == 499500 && values["helper"] == 27 && values["trusted-callback"] == 30 &&
                values["trusted-generic"] == 46 && values["paths"] == 33 && values["eh"] == 10 && values["after-zero"] == 35, "Finite fixture side effects/values differ.");
            if (kind is Kind.Ordinary or Kind.RequiredUnmetered) Api.AssertUnmetered(context);
            if (evidence is not null) WriteInventory(context, evidence);
            return new Outcome(weak, values, deltas, final);
        }
        finally { context.Unload(); if (kind != Kind.Stock) Api.AssertRetired(context); }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static InterleavedOutcome InterleavedFrame(string directory)
    {
        AssemblyLoadContext left = Api.Create(directory, Kind.Metered, NormalLimit);
        AssemblyLoadContext right = Api.Create(directory, Kind.Metered, NormalLimit);
        var lw = new WeakReference(left); var rw = new WeakReference(right);
        try
        {
            IWork a = LoadWork(left, directory); IWork b = LoadWork(right, directory);
            Snapshot ls = Api.Read(left, NormalLimit); Snapshot rs = Api.Read(right, NormalLimit);
            Check(a.Loop(30) == 435, "Interleaved left value differs.");
            Snapshot la = Api.Read(left, NormalLimit); PositiveDelta(ls, la, "interleaved left");
            Check(Api.Read(right, NormalLimit) == rs, "Left call charged right context.");
            Check(TrustedCaller.Call(b) == 30, "Interleaved right callback differs.");
            Snapshot rb = Api.Read(right, NormalLimit); PositiveDelta(rs, rb, "interleaved right");
            Check(Api.Read(left, NormalLimit) == la, "Right call charged left context.");
            Check(a.AfterZero() == 35, "Return-to-left value differs.");
            Snapshot last = Api.Read(left, NormalLimit); PositiveDelta(la, last, "restored left");
            Check(Api.Read(right, NormalLimit) == rb, "Restored left charged right context.");
            TrustedBusy(); Check(Api.Read(left, NormalLimit) == last && Api.Read(right, NormalLimit) == rb, "Host return owner was stale.");
            return new InterleavedOutcome(lw, rw, last.Executed, rb.Executed);
        }
        finally { left.Unload(); right.Unload(); Api.AssertRetired(left); Api.AssertRetired(right); }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static ConcurrentOutcome ConcurrentFrame(string directory)
    {
        var context = Api.Create(directory, Kind.Metered, NormalLimit); var weak = new WeakReference(context);
        try
        {
            IWork work = LoadWork(context, directory);
            long baselineBefore = Api.Read(context, NormalLimit).Executed;
            Program.Check(work.Loop(1000) == 499500, "Concurrent warm value differs.");
            long before = Api.Read(context, NormalLimit).Executed;
            long perCall = before - baselineBefore;
            var tasks = Enumerable.Range(0, 4).Select(_ => Task.Run(() => work.Loop(1000))).ToArray();
            Task.WaitAll(tasks); // Authored code creates no tasks; the trusted host joins every callback.
            int result = tasks.Sum(task => task.Result); Snapshot after = Api.Read(context, NormalLimit);
            Check(result == 1998000 && perCall > 0 && after.Executed - before == 4 * perCall, "Joined concurrent values/exact atomic total differ.");
            return new ConcurrentOutcome(weak, result, after.Executed);
        }
        finally { context.Unload(); Api.AssertRetired(context); }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static IWork LoadWork(AssemblyLoadContext context, string directory) => (IWork)Activator.CreateInstance(
        context.LoadFromAssemblyPath(Path.Combine(directory, "MeterProbe.Payload.dll")).GetType("MeterUGC.Payload.Entry", true)!)!;
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void TrustedBusy() { for (int i = 0; i < 1000; i++) trustedSideEffect = unchecked(trustedSideEffect + i); }
    private static long PositiveDelta(Snapshot before, Snapshot after, string operation)
    {
        Check(after.Executed > before.Executed, $"No positive opcode count for {operation}."); return after.Executed - before.Executed;
    }
    private static void Collect(WeakReference context)
    {
        for (int pass = 0; pass < 12 && context.IsAlive; pass++) { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }
        Check(!context.IsAlive, "Collectible fixture context remained alive after execution frame returned.");
    }
    private static void WriteInventory(AssemblyLoadContext context, string directory)
    {
        var flags = BindingFlags.DeclaredOnly | BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
        var inventory = context.Assemblies.OrderBy(a => a.GetName().Name).SelectMany(a => a.GetTypes().OrderBy(t => t.FullName)
            .SelectMany(t => t.GetMethods(flags).Cast<MethodBase>().Concat(t.GetConstructors(flags)).Distinct()
            .OrderBy(m => m.MetadataToken).Select(m => new { assembly = a.GetName().Name, module = a.ManifestModule.ModuleVersionId.ToString(),
                type = t.FullName, method = m.Name, token = $"0x{m.MetadataToken:x8}", signature = m.ToString() }))).ToArray();
        File.WriteAllText(Path.Combine(directory, "method-inventory.json"), JsonSerializer.Serialize(inventory, new JsonSerializerOptions { WriteIndented = true }));
    }
    internal static void Check(bool condition, string reason) { if (!condition) throw new InvalidOperationException(reason); }
}
internal enum Kind { Stock, Metered, Ordinary, RequiredUnmetered }
internal readonly record struct Snapshot(long Remaining, long Executed, bool Exhausted);
internal sealed record Outcome(WeakReference Context, Dictionary<string, int> Values, Dictionary<string, long> Deltas, Snapshot Final);
internal sealed record InterleavedOutcome(WeakReference Left, WeakReference Right, long LeftExecuted, long RightExecuted);
internal sealed record ConcurrentOutcome(WeakReference Context, int Value, long Executed);

internal static class Api
{
    private static Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, AssemblyLoadContext> metered = null!;
    private static Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, AssemblyLoadContext> required = null!;
    private static Func<AssemblyLoadContext, long> remaining = null!, executed = null!;
    private static Func<AssemblyLoadContext, bool> exhausted = null!;
    private static Func<AssemblyLoadContext, int> policy = null!;
    public static void Initialize(string evidence)
    {
        const BindingFlags flags = BindingFlags.DeclaredOnly | BindingFlags.Static | BindingFlags.Instance | BindingFlags.NonPublic;
        MethodInfo Get(string name)
        {
            MethodInfo method = typeof(AssemblyLoadContext).GetMethod(name, flags) ?? throw new PlatformNotSupportedException($"Missing {name}.");
            Program.Check(method.IsPrivate, $"Expected private API: {name}."); return method;
        }
        int version = Get("RuneCLR_GetInstructionMeterVersion").CreateDelegate<Func<int>>()();
        Program.Check(version == 1, "Instruction meter version not1.");
        metered = Get("RuneCLR_CreateInstructionMetered").CreateDelegate<Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, AssemblyLoadContext>>();
        required = Get("RuneCLR_CreateInterpreterRequired").CreateDelegate<Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, AssemblyLoadContext>>();
        remaining = Get("RuneCLR_GetInstructionMeterRemaining").CreateDelegate<Func<AssemblyLoadContext, long>>();
        executed = Get("RuneCLR_GetInstructionMeterExecuted").CreateDelegate<Func<AssemblyLoadContext, long>>();
        exhausted = Get("RuneCLR_GetInstructionMeterExhausted").CreateDelegate<Func<AssemblyLoadContext, bool>>();
        policy = Get("RuneCLR_GetExecutionPolicy").CreateDelegate<Func<AssemblyLoadContext, int>>();
        var methods = typeof(AssemblyLoadContext).GetMethods(flags).Where(m => m.Name.Contains("InstructionMeter", StringComparison.Ordinal))
            .Select(m => new { m.Name, signature = m.ToString(), m.IsStatic, m.IsPrivate }).ToArray();
        Program.Check(!methods.Any(m => m.Name.Contains("Set", StringComparison.Ordinal)), "Meter setter exists.");
        File.WriteAllText(Path.Combine(evidence, "meter-api.json"), JsonSerializer.Serialize(new { version, methods }, new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine("METER API version=1 private-api=true no-setter=true diagnostic-only=true");
    }
    public static AssemblyLoadContext Create(string directory, Kind kind, long limit)
    {
        Func<AssemblyLoadContext, AssemblyName, Assembly?> resolver = (context, name) =>
        {
            if (name.Name == typeof(IWork).Assembly.GetName().Name) return typeof(IWork).Assembly;
            string path = Path.Combine(directory, name.Name + ".dll");
            return File.Exists(path) ? context.LoadFromAssemblyPath(path) : null;
        };
        string name = "meter-" + Guid.NewGuid().ToString("N");
        AssemblyLoadContext result = kind switch
        {
            Kind.Metered => metered(name, resolver, limit),
            Kind.RequiredUnmetered => required(name, resolver),
            _ => new FixtureContext(name, resolver)
        };
        Program.Check(result.IsCollectible, "Context is not collectible.");
        if (kind != Kind.Stock) Program.Check(policy(result) == (kind == Kind.Ordinary ? 0 : 1), "Native policy does not match context creation.");
        return result;
    }
    public static Snapshot Read(AssemblyLoadContext context, long limit)
    {
        var result = new Snapshot(remaining(context), executed(context), exhausted(context));
        Program.Check(result.Remaining >= 0 && result.Executed >= 0 && result.Exhausted == (result.Remaining == 0) &&
            result.Remaining == (result.Executed >= limit ? 0 : limit - result.Executed), "Single-threaded/joined meter arithmetic differs.");
        return result;
    }
    public static void AssertInvalidLimit(string directory, long value)
    {
        try { var unexpected = Create(directory, Kind.Metered, value); unexpected.Unload(); throw new InvalidOperationException("Invalid limit accepted."); }
        catch (ArgumentOutOfRangeException) { Console.WriteLine($"PASS invalid-limit={value} exception=System.ArgumentOutOfRangeException"); }
    }
    public static void AssertUnmetered(AssemblyLoadContext context) => AssertUnavailable(context, false);
    public static void AssertRetired(AssemblyLoadContext context) => AssertUnavailable(context, true);
    private static void AssertUnavailable(AssemblyLoadContext context, bool retired)
    {
        int rejected = 0;
        try { remaining(context); } catch (InvalidOperationException) { rejected++; }
        try { executed(context); } catch (InvalidOperationException) { rejected++; }
        try { exhausted(context); } catch (InvalidOperationException) { rejected++; }
        Program.Check(rejected == 3, "Meter query did not reject retired/unmetered context.");
        Console.WriteLine($"METER QUERY retired={retired.ToString().ToLowerInvariant()} rejected=3 exception=System.InvalidOperationException");
    }
    private sealed class FixtureContext(string name, Func<AssemblyLoadContext, AssemblyName, Assembly?> resolver) : AssemblyLoadContext(name, true)
    {
        protected override Assembly? Load(AssemblyName name) => resolver(this, name);
    }
}
