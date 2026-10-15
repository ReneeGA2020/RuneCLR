using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using System.Text.Json;
using ConcurrencyProbe.Contract;
using RuneCLR.Experiments;
namespace ConcurrencyProbe.Host;
internal static class Program
{
    internal static void Check(bool value, string message)
    { if (!value) throw new InvalidOperationException(message); }
    public static int Main(string[] args)
    {
        TextWriter stdout = Console.Out; Console.SetOut(Console.Error);
        Check(args.Length == 5, "Expected author path, worker count, lane, nonce, evidence.");
        string author = Path.GetFullPath(args[0]), lane = args[2], nonce = args[3], evidence = args[4];
        int workers = int.Parse(args[1]);
        Check(workers is 2 or 4 && nonce.Length == 32 && nonce.All(Uri.IsHexDigit), "Invalid owned run.");
        Check(lane is "terminal" or "finite-cleanup" or "tight-cleanup" or "high" or "diagnostic" or "required", "Unknown lane.");
        Check(WindowsEntryObservation.Enabled, "Post-invocation observer required.");
        Api.Initialize();
        var outcome = Frames(author, workers, lane);
        foreach (WeakReference weak in outcome.Weak)
        {
            for (int pass = 0; pass < 16 && weak.IsAlive; pass++)
            { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }
            Check(!weak.IsAlive, "Joined context retained beyond returned host frames.");
        }
        var result = new { passed = true, processId = Environment.ProcessId, nonce, workers, lane,
            outcome.Rows, collected = outcome.Weak.Length, outcome.OwnerIsolation, outcome.OwnershipSnapshots,
            outcome.RetiredQueriesRejected, nativePolicyAcknowledged = 1,
            scope = "Trusted joined workers only; quiescent ledger reconciliation; no author thread API or transactional snapshot claim" };
        string json = JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true });
        File.WriteAllText(Path.Combine(evidence, "result.json"), json); stdout.WriteLine(json);
        return 0;
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static FrameOutcome Frames(string author, int workers, string lane)
    {
        string mode = lane is "required" or "diagnostic" ? lane : "terminal";
        long limit = lane == "high" ? 10000000 : 2048, cleanup = lane == "tight-cleanup" ? 64 : 8192;
        var bad = Api.Create(author, mode, limit, cleanup);
        var good = Api.Create(author, "terminal", 10000000, 8192);
        var weak = new[] { new WeakReference(bad), new WeakReference(good) };
        var rows = new List<RunRow>();
        int[] retiredQueries = [0, 0];
        var ownership = new Dictionary<string, Snapshot?>();
        bool isolated = false;
        try
        {
            Snapshot beforeGood = Api.Read(good);
            ownership["goodBefore"] = beforeGood;
            RunRow first = Invoke(bad, author, workers, lane, limit, cleanup); rows.Add(first);
            Snapshot afterGood = Api.Read(good);
            ownership["goodAfterBad"] = afterGood;
            ownership["badAfterBad"] = first.After;
            Check(beforeGood == afterGood, "Active concurrent owner charged idle good owner.");
            RunRow recovery = Invoke(good, author, 1, "high", 10000000, 8192); rows.Add(recovery);
            ownership["goodAfterGood"] = Api.Read(good);
            ownership["badAfterGood"] = mode == "required" ? null : Api.Read(bad, mode);
            if (lane is "high" or "diagnostic")
                Check(first.PostGateDispatches == workers * recovery.PostGateDispatches, "Concurrent finite loop ledger differs from joined single-worker reference.");
            Check(mode == "required" || Api.Read(bad, mode) == first.After, "Good owner altered completed owner.");
            isolated = true;
            return new(weak, rows, isolated, ownership, retiredQueries);
        }
        finally
        {
            bad.Unload(); good.Unload();
            retiredQueries[0] = Api.Retired(bad); retiredQueries[1] = Api.Retired(good);
            Check(retiredQueries.SequenceEqual(new[] { 8, 8 }), "Retired queries did not reject binder access.");
        }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static RunRow Invoke(AssemblyLoadContext context, string author, int workers, string lane, long allowance, long cleanupAllowance)
    {
        string mode = lane is "required" or "diagnostic" ? lane : "terminal";
        Type type = context.LoadFromAssemblyPath(author).GetType("ConcurrencyUGC.Entry", true)!;
        var warm = type.GetMethod("Warm")!.CreateDelegate<Func<int>>();
        Check(warm() == 1, "Fresh owner static state was not reset.");
        string method = lane is "finite-cleanup" or "tight-cleanup" ? "WorkFinally" : "Work";
        var work = type.GetMethod(method)!.CreateDelegate<Func<int, uint>>();
        Coordinator.Reset(workers);
        var returned = new bool[workers]; var values = new uint[workers]; var errors = new string?[workers];
        var workerIds = new int[workers]; var threads = new Thread[workers];
        for (int slot = 0; slot < workers; slot++)
        {
            int captured = slot;
            threads[slot] = new Thread(() =>
            {
                workerIds[captured] = Environment.CurrentManagedThreadId;
                try { values[captured] = work(captured); returned[captured] = true; }
                catch (Exception error) { errors[captured] = error.GetType().FullName; }
            }) { IsBackground = true, Name = "trusted-concurrency-" + slot };
            threads[slot].Start();
        }
        bool admitted = Coordinator.AwaitAdmissions();
        Snapshot? atGate = mode == "required" ? null : Api.Read(context, mode);
        Coordinator.Release();
        bool joined = true; foreach (Thread thread in threads) joined &= thread.Join(TimeSpan.FromSeconds(30));
        Snapshot? after = mode == "required" ? null : Api.Read(context, mode);
        Snapshot scalarAfter = after.GetValueOrDefault();
        object counters = Coordinator.Snapshot();
        var entries = new List<EntryObservation>
        {
            WindowsEntryObservation.Capture(type.GetMethod("Warm")!, true, "Warm returned1 before concurrent admission"),
        };
        if (Coordinator.Entered > 0) entries.Add(WindowsEntryObservation.Capture(type.GetMethod(method)!, true,
            $"Trusted gate observed{Coordinator.Entered} actual author invocations; joined={joined}"));
        if (Coordinator.CleanupStarted > 0) entries.Add(WindowsEntryObservation.Capture(type.GetMethod("FiniteCleanup", BindingFlags.Static | BindingFlags.NonPublic)!, true,
            $"Trusted CleanupStart observed{Coordinator.CleanupStarted}; joined={joined}"));
        var row = new RunRow(workers, lane, allowance, cleanupAllowance, admitted, joined, workerIds,
            returned, values, errors, atGate, after, counters, entries, Coordinator.Entered, Coordinator.Completed,
            Coordinator.CleanupStarted, Coordinator.CleanupCompleted, StaticStarts:1,
            PostGateDispatches:after is null ? null : scalarAfter.Executed - atGate!.Value.Executed);
        Console.WriteLine(JsonSerializer.Serialize(row));
        Check(admitted && joined && row.Entered == workers && workerIds.Distinct().Count() == workers, "Trusted concurrent admission/join failed.");
        Check(atGate is null || atGate.Value.Executed > 0 && atGate.Value.Remaining > 0, "Allowance exhausted before common gate release.");
        bool terminal = lane is "terminal" or "finite-cleanup" or "tight-cleanup";
        if (terminal)
        {
            Check(after is { Remaining: 0, Executed: 2048, IsTerminated: true, Reason: 1 }, "Concurrent execution lost exact allowance or sticky reason.");
            Check(!returned.Any(v => v) && errors.All(e => e == typeof(OperationCanceledException).FullName) && row.Completed == 0, "Concurrent author work returned/escaped terminal signal.");
            Check(scalarAfter.CleanupRemaining + scalarAfter.CleanupExecuted == cleanupAllowance, "Quiescent cleanup lost increments or exceeded allowance.");
            if (lane == "terminal") Check(scalarAfter.CleanupExecuted == 0 && scalarAfter.Phase == 1, "No-finally lane consumed cleanup.");
            if (lane == "finite-cleanup") Check(row.CleanupStarted == workers && row.CleanupCompleted == workers && scalarAfter.Phase == 1, "Concurrent finite cleanup did not complete all owners.");
            if (lane == "tight-cleanup") Check(after is { Phase: 2, CleanupRemaining: 0, CleanupExecuted: 64 } && row.CleanupCompleted == 0, "Bounded concurrent cleanup escaped its shared reserve.");
        }
        else
        {
            Check(returned.All(v => v) && errors.All(e => e is null) && values.All(v => v == Coordinator.Expected(10000)) && row.Completed == workers, "Finite concurrent control/checksum failed.");
            if (lane == "diagnostic") Check(after is { Remaining: 0, Executed: >2048, IsTerminated: false }, "Diagnostic lane did not continue after quota.");
            if (lane == "high") Check(after is { IsTerminated: false, Reason: 0, Phase: 0 } && scalarAfter.Remaining + scalarAfter.Executed == allowance, "High allowance ledger did not reconcile at join.");
        }
        return row;
    }
}
internal readonly record struct Snapshot(long Remaining, long Executed, bool Exhausted, bool IsTerminated, int Reason, int Phase, long CleanupRemaining, long CleanupExecuted);
internal sealed record FrameOutcome(WeakReference[] Weak, List<RunRow> Rows, bool OwnerIsolation,
    Dictionary<string, Snapshot?> OwnershipSnapshots, int[] RetiredQueriesRejected);
internal sealed record RunRow(int Workers, string Lane, long Allowance, long CleanupAllowance, bool Admitted, bool Joined,
    int[] WorkerIds, bool[] Returned, uint[] Values, string?[] Errors, Snapshot? AtGate, Snapshot? After, object Counters,
    List<EntryObservation> Entries, int Entered, int Completed, int CleanupStarted, int CleanupCompleted, int StaticStarts, long? PostGateDispatches);
internal static class Api
{
    private static Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, long, AssemblyLoadContext> terminal = null!;
    private static Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, AssemblyLoadContext> diagnostic = null!;
    private static Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, AssemblyLoadContext> required = null!;
    private static Func<AssemblyLoadContext, long> remaining = null!, executed = null!, cleanupRemaining = null!, cleanupExecuted = null!;
    private static Func<AssemblyLoadContext, bool> exhausted = null!, terminated = null!;
    private static Func<AssemblyLoadContext, int> reason = null!, phase = null!, policy = null!;
    public static void Initialize()
    {
        MethodInfo Get(string name)
        {
            var method = typeof(AssemblyLoadContext).GetMethod(name, BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance | BindingFlags.DeclaredOnly)!;
            Program.Check(method is { IsPrivate: true }, "Missing private bridge:" + name); return method!;
        }
        Program.Check(Get("RuneCLR_GetTerminalPrototypeVersion").CreateDelegate<Func<int>>()() == 1, "Version differs.");
        terminal = Get("RuneCLR_CreateTerminalPrototype").CreateDelegate<Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, long, AssemblyLoadContext>>();
        diagnostic = Get("RuneCLR_CreateInstructionMetered").CreateDelegate<Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, AssemblyLoadContext>>();
        required = Get("RuneCLR_CreateInterpreterRequired").CreateDelegate<Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, AssemblyLoadContext>>();
        remaining = Get("RuneCLR_GetInstructionMeterRemaining").CreateDelegate<Func<AssemblyLoadContext, long>>();
        executed = Get("RuneCLR_GetInstructionMeterExecuted").CreateDelegate<Func<AssemblyLoadContext, long>>();
        exhausted = Get("RuneCLR_GetInstructionMeterExhausted").CreateDelegate<Func<AssemblyLoadContext, bool>>();
        terminated = Get("RuneCLR_GetTerminalPrototypeIsTerminated").CreateDelegate<Func<AssemblyLoadContext, bool>>();
        reason = Get("RuneCLR_GetTerminalPrototypeReason").CreateDelegate<Func<AssemblyLoadContext, int>>();
        phase = Get("RuneCLR_GetTerminalPrototypePhase").CreateDelegate<Func<AssemblyLoadContext, int>>();
        cleanupRemaining = Get("RuneCLR_GetTerminalPrototypeCleanupRemaining").CreateDelegate<Func<AssemblyLoadContext, long>>();
        cleanupExecuted = Get("RuneCLR_GetTerminalPrototypeCleanupExecuted").CreateDelegate<Func<AssemblyLoadContext, long>>();
        policy = Get("RuneCLR_GetExecutionPolicy").CreateDelegate<Func<AssemblyLoadContext, int>>();
    }
    public static AssemblyLoadContext Create(string author, string mode, long limit, long cleanup)
    {
        Func<AssemblyLoadContext, AssemblyName, Assembly?> resolver = (_, name) =>
            name.Name == typeof(Coordinator).Assembly.GetName().Name ? typeof(Coordinator).Assembly : null;
        string name = "concurrency-" + Guid.NewGuid().ToString("N");
        var context = mode switch
        {
            "terminal" => terminal(name, resolver, limit, cleanup),
            "diagnostic" => diagnostic(name, resolver, limit),
            _ => required(name, resolver)
        };
        Program.Check(context.IsCollectible && policy(context) == 1, "Native required-interpreter acknowledgement missing.");
        if (mode == "terminal") Program.Check(Read(context) == new Snapshot(limit, 0, false, false, 0, 0, cleanup, 0), "Initial native state differs.");
        if (mode != "terminal")
        {
            int rejected = 0; foreach (Action query in new Action[] { () => terminated(context), () => reason(context), () => phase(context), () => cleanupRemaining(context), () => cleanupExecuted(context) })
                try { query(); } catch (InvalidOperationException) { rejected++; }
            Program.Check(rejected == 5, "Nonterminal owner exposes terminal state.");
        }
        return context;
    }
    public static Snapshot Read(AssemblyLoadContext context, string mode = "terminal") => mode == "diagnostic"
        ? new(remaining(context), executed(context), exhausted(context), false, 0, 0, 0, 0)
        : new(remaining(context), executed(context), exhausted(context), terminated(context), reason(context), phase(context), cleanupRemaining(context), cleanupExecuted(context));
    public static int Retired(AssemblyLoadContext context)
    {
        int rejected = 0; foreach (Action query in new Action[] { () => remaining(context), () => executed(context), () => exhausted(context), () => terminated(context), () => reason(context), () => phase(context), () => cleanupRemaining(context), () => cleanupExecuted(context) })
            try { query(); } catch (InvalidOperationException) { rejected++; }
        return rejected;
    }
}
