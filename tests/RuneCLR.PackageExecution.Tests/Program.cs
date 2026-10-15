using RuneCLR.Packages;
using RuneCLR.Runtime;

namespace RuneCLR.PackageExecution.Tests;

public static class Program
{
    public static int Main(string[] args) => PackageExecutionHarness.Run(args);
}

/// <summary>Player-side acceptance entry point, also callable by a native mobile bridge. No compiler dependency.</summary>
public static partial class PackageExecutionHarness
{
    public static int Run(string[] args)
    {
        if (args is ["--help"] or ["-h"])
        {
            Console.WriteLine("RuneCLR.PackageExecution.Tests --packages <controlled fixture directory> [--require-interpreter] [--pump] [--native-budget] [--budget-evidence <NEW directory>]");
            Console.WriteLine("--pump requires fixtures generated with --include-pumped.");
            Console.WriteLine("--native-budget requires --pump --require-interpreter and fixtures generated with --include-budget.");
            return 0;
        }
        var required = args.Contains("--require-interpreter", StringComparer.Ordinal);
        var pump = args.Contains("--pump", StringComparer.Ordinal);
        var nativeBudget = args.Contains("--native-budget", StringComparer.Ordinal);
        string? budgetEvidence = null;
        var evidenceIndex = Array.IndexOf(args, "--budget-evidence");
        if (args.Count(argument => argument == "--native-budget") > 1 ||
            args.Count(argument => argument == "--budget-evidence") > 1 ||
            evidenceIndex >= 0 && (evidenceIndex + 1 >= args.Length || args[evidenceIndex + 1].StartsWith("--", StringComparison.Ordinal)))
        {
            Console.Error.WriteLine("Native budget options must be supplied once with a fresh evidence directory when requested.");
            return 2;
        }
        if (evidenceIndex >= 0)
        {
            budgetEvidence = Path.GetFullPath(args[evidenceIndex + 1]);
            args = args.Where((_, index) => index != evidenceIndex && index != evidenceIndex + 1).ToArray();
        }
        if (nativeBudget && (!required || !pump) || budgetEvidence is not null && (!nativeBudget || Path.Exists(budgetEvidence)))
        {
            Console.Error.WriteLine("--native-budget requires --pump --require-interpreter; --budget-evidence requires native mode and a new directory.");
            return 2;
        }
        args = args.Where(argument => argument is not ("--require-interpreter" or "--pump" or "--native-budget")).ToArray();
        if (args is not ["--packages", var directory])
        {
            Console.Error.WriteLine("Expected --packages <controlled fixture directory>.");
            return 2;
        }
        var root = Path.GetFullPath(directory);
        var options = new MapRunOptions { TickCount = 2, ExecutionPolicy = required ? MapExecutionPolicy.RequireInterpreter : MapExecutionPolicy.Default };
        if (nativeBudget && !NativeBudgetAvailable()) return 2;
        if (budgetEvidence is not null) Directory.CreateDirectory(budgetEvidence);
        var budgetReceipts = new List<NativeBudgetReceipt>();
        var policyReported = false;
        void Proof(MapRunResult result)
        {
            Require(result.Report.ExecutionPolicy == options.ExecutionPolicy, "Session execution policy changed.");
            Require(result.Report.ExecutionPolicyVersion == (required ? 1 : 0), "Unexpected session execution-policy acknowledgment.");
            Require(result.Report.PrototypeBudget is null, "Unbudgeted package unexpectedly acquired an instruction budget.");
            if (!required) return;
            Require(result.Report.ExecutionPolicyVersion == 1, "Native execution-policy acknowledgment missing.");
            if (!policyReported)
            {
                Console.WriteLine("SESSION_EXECUTION_POLICY required-interpreter version=1");
                policyReported = true;
            }
        }
        var cases = Cases(root, options, Proof, pump)
            .Concat(pump ? PumpedCases(root, options, Proof) : [])
            .Concat(nativeBudget ? NativeBudgetCases(root, budgetReceipts) : [])
            .Append(("Player default context contains no operator compiler assemblies", (Action)CompilerAbsent)).ToArray();
        var passed = 0;
        foreach (var (name, test) in cases)
        {
            try { test(); passed++; Console.WriteLine($"PASS {name}"); }
            catch (Exception error) { Console.Error.WriteLine($"FAIL {name}: {error.GetType().Name}: {error.Message}"); }
        }
        Console.WriteLine($"{passed}/{cases.Length} package execution tests passed.");
        if (budgetEvidence is not null)
            File.WriteAllText(Path.Combine(budgetEvidence, "results.json"), System.Text.Json.JsonSerializer.Serialize(new
            {
                schemaVersion = 1, passed = passed == cases.Length, nativeGroups = 11,
                packageTestsPassed = passed, packageTestsTotal = cases.Length, receipts = budgetReceipts
            }, new System.Text.Json.JsonSerializerOptions { WriteIndented = true }));
        return passed == cases.Length ? 0 : 1;
    }

    private static IEnumerable<(string Name, Action Test)> Cases(string root, MapRunOptions options, Action<MapRunResult> proof, bool pump)
    {
        string Manifest(string name) => Path.Combine(root, name, PackageFormat.ManifestFileName);
        Action Normal(string name) => () => Successful(Manifest(name), ["starts=1", "tick=0", "tick=1", "stopped"], options, proof, pump);
        Action Private(string name, string version) => () => Successful(Manifest(name), [version + ":1:1", "stopped"], options, proof, pump);
        yield return ("Source package executes, resets statics, cleans entities and unloads", Normal("source"));
        yield return ("Raw IL import executes with the same lifecycle", Normal("import"));
        yield return ("Source executes again with fresh static state", Normal("source"));
        yield return ("Author exception stops, releases entities and unloads", () => AuthorFailure(Manifest("failure"), options, proof, pump));
        yield return ("Valid package recovers after author failure", Normal("source"));
        yield return ("Tampered package fails integrity before execution", () => Rejected(Manifest("tampered"), capability: false));
        yield return ("Rehashed forbidden entry fails capability admission", () => Rejected(Manifest("forbidden"), capability: true));
        yield return ("Valid package recovers after invalid entries", Normal("source"));
        yield return ("Private helper A executes with fresh ordinary and generic statics", Private("private-a", "A"));
        yield return ("Same-name private helper B binds its declared version", Private("private-b", "B"));
        yield return ("Private helper A executes again with fresh statics", Private("private-a", "A"));
        yield return ("Imported entry retains its declared private helper", Private("private-import", "A"));
        yield return ("Rehashed forbidden private helper fails capability admission", () => Rejected(Manifest("private-forbidden"), capability: true));
        yield return ("Valid private package recovers after forbidden dependency", Private("private-a", "A"));
    }

    private static void Successful(string manifest, string[] logs, MapRunOptions options, Action<MapRunResult> proof, bool pump = false)
    {
        var (result, session) = Execute(MapPackage.FromManifest(manifest), options, pump);
        proof(result);
        Require(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Expected successful execution.");
        Require(result.Report.CompletedTicks == 2, "Tick callbacks did not complete.");
        Require(result.Report.Logs.SequenceEqual(logs), "Unexpected logs or static/generic state.");
        CleanedAndCollected(result);
        GC.KeepAlive(session);
    }

    private static void AuthorFailure(string manifest, MapRunOptions options, Action<MapRunResult> proof, bool pump)
    {
        var (result, session) = Execute(MapPackage.FromManifest(manifest), options, pump);
        proof(result);
        Require(result.Report.Outcome == MapRunOutcome.Failed && result.Report.Error?.Contains("AuthorFailureException", StringComparison.Ordinal) == true,
            "Author exception was not captured as a host-owned description.");
        Require(result.Report.CompletedTicks == 0 && result.Report.Logs.SequenceEqual(new[] { "stopped-after-error" }),
            "Failure cleanup callback did not run.");
        CleanedAndCollected(result);
        GC.KeepAlive(session);
    }

    private static void CleanedAndCollected(MapRunResult result, int expectedEntities = 1)
    {
        Require(result.Report.CreatedEntities == expectedEntities && result.Report.ReleasedEntities == expectedEntities && result.Report.RemainingEntities == 0,
            "Session-owned entity cleanup failed.");
        // Run/Stop (or a failed callback) returned. Forced collection is diagnostic only.
        for (var attempt = 0; attempt < 12 && !result.Unload.IsCollected; attempt++)
        {
            GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); Thread.Sleep(10);
        }
        Require(result.Unload.IsCollected, "Collectible context remains alive after diagnostic collection.");
    }

    private static void Rejected(string manifest, bool capability)
    {
        try { _ = MapPackage.FromManifest(manifest); }
        catch (InvalidDataException error)
        {
            Require(capability ? error.Message.Contains(GameplayCapabilityPolicy.Profile, StringComparison.Ordinal)
                : error.Message.Contains("hash", StringComparison.OrdinalIgnoreCase), "Package failed for an unexpected reason: " + error.Message);
            return;
        }
        throw new InvalidOperationException("Invalid package passed pre-execution admission.");
    }

    private static void CompilerAbsent()
    {
        static bool OperatorAssembly(string? name) => name is "RuneCLR.Compiler" or "RuneCLR.PackageFixtures" or "RuneCLR.PackageTool" ||
            (name?.StartsWith("Microsoft.CodeAnalysis", StringComparison.Ordinal) ?? false);
        var loaded = AppDomain.CurrentDomain.GetAssemblies().Select(assembly => assembly.GetName().Name).ToArray();
        Require(!loaded.Any(OperatorAssembly),
            "Operator compiler assemblies entered the player process.");
        Require(!AppDomain.CurrentDomain.GetAssemblies().Any(assembly => assembly.GetReferencedAssemblies().Any(name => OperatorAssembly(name.Name))),
            "A loaded player assembly references operator compiler tooling.");
        Require(!Directory.EnumerateFiles(AppContext.BaseDirectory, "*.dll", SearchOption.AllDirectories)
            .Any(path => OperatorAssembly(Path.GetFileNameWithoutExtension(path))),
            "Operator compiler tooling is present in the player application directory.");
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
