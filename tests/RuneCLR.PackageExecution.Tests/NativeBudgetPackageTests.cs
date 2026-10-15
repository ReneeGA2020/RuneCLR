using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using RuneCLR.Packages;
using RuneCLR.Runtime;

namespace RuneCLR.PackageExecution.Tests;

public static partial class PackageExecutionHarness
{
    private const long NativeExecutionLimit = 8192, NativeCleanupLimit = 4096, NativeRecoveryLimit = 1000000;

    private sealed record NativeBudgetReceipt(
        string caseId, string role, int sequence, string executionPolicy, int executionPolicyVersion, long executionLimit, long cleanupLimit,
        string outcome, int completedTicks, int successfulHostReturns, int created, int released, int remaining,
        string[] logs, string? error, PrototypeBudgetSnapshot budget, bool collected, bool retainedStoppedSessionCollected);

    private static MapRunOptions NativeOptions(long limit) => new()
    {
        ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
        PrototypeInstructionBudget = limit, PrototypeCleanupInstructionBudget = NativeCleanupLimit,
        TickCount = 0, OperationBudgetPerCallback = 100000, MaxLogMessages = 128
    };

    private static bool NativeBudgetAvailable()
    {
        var missing = Path.Combine(Path.GetTempPath(), "runeclr-unavailable-author-" + Guid.NewGuid().ToString("N") + ".dll");
        var authorLoads = 0;
        var before = AppDomain.CurrentDomain.GetAssemblies().Count(assembly => assembly.IsCollectible);
        void Observe(object? sender, AssemblyLoadEventArgs loaded)
        {
            if (loaded.LoadedAssembly.IsCollectible) authorLoads++;
        }
        AppDomain.CurrentDomain.AssemblyLoad += Observe;
        try
        {
            try
            {
                using var unexpected = new MapRunner().Start(new MapPackage("budget-preflight", missing, "MissingAuthor"), NativeOptions(NativeExecutionLimit));
            }
            catch (PlatformNotSupportedException)
            {
                var after = AppDomain.CurrentDomain.GetAssemblies().Count(assembly => assembly.IsCollectible);
                Require(before == 0 && after == 0 && authorLoads == 0 && !File.Exists(missing), "Unsupported native budget loaded author code.");
                Console.Error.WriteLine("NATIVE_BUDGET_UNAVAILABLE beforeAuthorFile=true collectibleBefore=0 collectibleAfter=0 authorLoads=0");
                return false;
            }
            catch (FileNotFoundException error) when (error.FileName == missing)
            {
                Require(before == 0 && authorLoads == 0, "Native capability preflight loaded author code.");
                Console.WriteLine("NATIVE_BUDGET_AVAILABLE beforeAuthorFile=true authorLoads=0");
                return true;
            }
            throw new InvalidOperationException("Native capability preflight unexpectedly accepted a missing author file.");
        }
        finally { AppDomain.CurrentDomain.AssemblyLoad -= Observe; }
    }

    private static IEnumerable<(string Name, Action Test)> NativeBudgetCases(string root, List<NativeBudgetReceipt> receipts)
    {
        void Recover(string role) => NativeCase(root, "source", role, receipts, NativeRecoveryLimit);
        yield return ("Controlled package native budget completes and retires a retained pumped session", () => Recover("baseline"));
        foreach (var name in new[]
        {
            "budget-work", "budget-constructor-loop", "budget-static-constructor-loop", "budget-start-loop",
            "budget-tick-loop", "budget-catch-resume", "budget-finite-cleanup", "budget-infinite-cleanup", "budget-stop-loop"
        })
        {
            yield return ($"Controlled package {name} terminates, cleans up and admits a fresh session", () =>
            {
                NativeCase(root, name, "case", receipts, NativeExecutionLimit);
                Recover("recovery-after-" + name);
            });
        }
        yield return ("Controlled package terminal catches cannot prevent repeated bad-good recovery", () =>
        {
            for (var attempt = 0; attempt < 3; attempt++)
            {
                NativeCase(root, "budget-catch-resume", "repeated-bad-" + attempt, receipts, NativeExecutionLimit);
                Recover("repeated-good-" + attempt);
            }
        });
    }

    private static void NativeCase(string root, string name, string role, List<NativeBudgetReceipt> receipts, long limit)
    {
        var (result, retained, hostReturns) = RunNativeFrame(root, name, limit);
        var report = result.Report;
        var budget = report.PrototypeBudget ?? throw new InvalidOperationException("Native scalar budget report is absent.");
        var terminated = name != "source";
        Require(report.ExecutionPolicy == MapExecutionPolicy.RequireInterpreter && report.ExecutionPolicyVersion == 1,
            "Native package session did not acknowledge required interpretation.");
        Require(report.CompletedTicks == hostReturns, "Successful host returns differ from completed author ticks.");
        Require(budget.ExecutionRemaining >= 0 && budget.ExecutionExecuted >= 0 &&
            budget.ExecutionRemaining + budget.ExecutionExecuted == limit && budget.CleanupRemaining >= 0 &&
            budget.CleanupExecuted >= 0 && budget.CleanupRemaining + budget.CleanupExecuted == NativeCleanupLimit,
            "Native cumulative execution or cleanup ledger changed across host returns.");
        Require(budget.IsTerminated == terminated && budget.ExecutionExhausted == terminated && budget.Reason == (terminated ? 1 : 0),
            "Native terminal latch disagrees with the controlled package scenario.");
        if (terminated)
        {
            Require(report.Outcome == MapRunOutcome.Failed && budget.ExecutionRemaining == 0 && budget.ExecutionExecuted == limit &&
                report.Error?.Contains("The native prototype instruction budget terminated author execution.", StringComparison.Ordinal) == true,
                "Controlled package did not stop at its exact native execution boundary.");
            Require(!report.Logs.Any(log => log is "stop" or "broad-catch" or "resume" or "start-after" or "tick-after" or "stop-after" or "helper-infinite-after"),
                "Author catch, continuation or OnStop ran after native terminal exhaustion.");
            Require(name == "budget-work" ? hostReturns >= 2 && hostReturns < 64 : hostReturns == (name == "budget-stop-loop" ? 2 : 0),
                "Native package termination did not preserve its successful host-return prefix.");
            ValidateNativeLogs(name, report);
            if (name == "budget-finite-cleanup")
                Require(budget.Phase == 1 && budget.CleanupExecuted > 0 && budget.CleanupRemaining > 0, "Finite package finally did not use its bounded cleanup reserve.");
            else if (name == "budget-infinite-cleanup")
                Require(budget.Phase == 2 && budget.CleanupExecuted == NativeCleanupLimit && budget.CleanupRemaining == 0, "Infinite package cleanup was not bounded.");
            else Require(budget.CleanupExecuted == 0, "A package without finally consumed the cleanup reserve.");
        }
        else
        {
            Require(report.Outcome == MapRunOutcome.Completed && report.Error is null && hostReturns == 2 &&
                report.Logs.SequenceEqual(new[] { "starts=1", "tick=0", "tick=1", "stopped" }),
                "Native package recovery did not restore lifecycle or fresh static state.");
            Require(budget.ExecutionRemaining > 0 && budget.ExecutionExecuted > 0 && budget.Phase == 0 && budget.CleanupExecuted == 0,
                "A finite package consumed the terminal cleanup reserve or fabricated an empty execution ledger.");
        }
        var entities = name is "budget-constructor-loop" or "budget-static-constructor-loop" ? 0 : 1;
        CleanedAndCollected(result, entities);
        GC.KeepAlive(retained);
        var receipt = new NativeBudgetReceipt(name, role, receipts.Count + 1, report.ExecutionPolicy.ToString(), report.ExecutionPolicyVersion, limit, NativeCleanupLimit, report.Outcome.ToString(),
            report.CompletedTicks, hostReturns, report.CreatedEntities, report.ReleasedEntities, report.RemainingEntities,
            report.Logs.ToArray(), report.Error, budget, true, true);
        receipts.Add(receipt);
        Console.WriteLine("NATIVE_BUDGET_RECEIPT " + JsonSerializer.Serialize(receipt));
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static (MapRunResult Result, MapSession Retained, int HostReturns) RunNativeFrame(string root, string name, long limit)
    {
        var package = MapPackage.FromManifest(Path.Combine(root, name, PackageFormat.ManifestFileName));
        var retained = new MapRunner().Start(package, NativeOptions(limit));
        try
        {
            var hostReturns = 0;
            var maximumTicks = name == "budget-work" ? 64 : 2;
            for (var tick = 0; retained.IsRunning && tick < maximumTicks; tick++)
            {
                Running(retained, hostReturns);
                if (retained.Tick(TimeSpan.FromMilliseconds(5 + tick))) hostReturns++;
                Require(retained.CompletedTicks == hostReturns, "Host tick return was not reflected in session progress.");
            }
            if (name == "budget-work") Require(!retained.IsRunning, "Cumulative package budget reset between finite host ticks.");
            var result = retained.Stop();
            Stopped(retained, result);
            return (result, retained, hostReturns);
        }
        finally { retained.Dispose(); }
    }

    private static void ValidateNativeLogs(string name, MapRunReport report)
    {
        var logs = report.Logs;
        if (name is "budget-constructor-loop" or "budget-static-constructor-loop")
            Require(logs.Count == 0, "A looping constructor reached OnStart.");
        else
        {
            Require(logs.FirstOrDefault() == "start", "Native package did not enter OnStart.");
            if (name == "budget-work")
            {
                var workLogs = logs.Count - 1;
                Require(workLogs >= report.CompletedTicks && workLogs <= report.CompletedTicks + 1 &&
                    logs.SequenceEqual(new[] { "start" }.Concat(Enumerable.Range(0, workLogs).Select(index => "work=" + index))),
                    "Finite native tick logs do not match the completed host-return prefix.");
            }
            else if (name == "budget-tick-loop") Require(logs.SequenceEqual(new[] { "start", "tick-before" }), "Endless tick entry changed.");
            else if (name == "budget-finite-cleanup")
                Require(logs.Count == 4 && logs[1] == "finally" && logs[2] == "helper-finite" && logs[3].StartsWith("cleanup-checksum=", StringComparison.Ordinal),
                    "Approved private finite cleanup did not finish.");
            else if (name == "budget-infinite-cleanup") Require(logs.SequenceEqual(new[] { "start", "helper-infinite-before" }), "Infinite private cleanup did not enter.");
            else if (name == "budget-stop-loop") Require(logs.SequenceEqual(new[] { "start", "tick=0", "tick=1", "stop-before" }), "OnStop loop changed successful frame progress.");
            else Require(logs.SequenceEqual(new[] { "start" }), "Native package reached an unexpected continuation.");
        }
    }
}
