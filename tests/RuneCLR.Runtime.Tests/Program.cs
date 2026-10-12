using System.Text.Json;
using RuneCLR.Runtime;

var tests = new List<(string Name, Action Run)>
{
    ("Repeated sessions reset map statics and unload", RepeatedSessions),
    ("Map-defined exceptions do not retain the map", MapExceptions),
    ("Caught cooperative budget violations still fail the session", BudgetViolation),
    ("Entity quota failures reclaim host resources", EntityQuota),
    ("OnStop failures still reclaim resources and unload", StopFailure),
    ("Log quotas bound retained host messages", LogQuota),
    ("Invalid entry types fail without retaining the context", InvalidEntry),
    ("Manifest rejects entry paths outside the package", ManifestTraversal),
    ("Invalid options are rejected before map execution", InvalidOptions),
    ("Private dependency versions and generic statics remain session-local", PrivateDependencies),
    ("Generic collections and constrained calls execute and unload", Generics)
};

if (args.Length == 2 && args[0] == "--late-map")
{
    var manifest = Path.GetFullPath(args[1]);
    tests.Add(("Map compiled after the host executes and unloads", () => LateMap(manifest)));
}
else if (args.Length != 0)
{
    Console.Error.WriteLine("Usage: RuneCLR.Runtime.Tests [--late-map <manifest>]");
    return 2;
}

var failures = 0;
foreach (var (name, run) in tests)
{
    try
    {
        run();
        Console.WriteLine($"PASS {name}");
    }
    catch (Exception exception)
    {
        failures++;
        Console.Error.WriteLine($"FAIL {name}: {exception}");
    }
}

Console.WriteLine($"{tests.Count - failures}/{tests.Count} tests passed");
return failures == 0 ? 0 : 1;

static MapPackage Package(string type) => new(
    "fixture",
    Path.Combine(AppContext.BaseDirectory, "fixtures", "RuneCLR.TestMaps.dll"),
    $"RuneCLR.TestMaps.{type}");

static void RepeatedSessions()
{
    var runner = new MapRunner();
    for (var session = 0; session < 20; session++)
    {
        var result = runner.Run(Package("CounterMap"));
        Check(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Session failed.");
        Check(result.Report.CompletedTicks == 3, "Unexpected tick count.");
        Check(result.Report.Logs[0] == "starts=1", "Static state escaped the session.");
        Check(result.Report.Logs[^1] == "stopped", "OnStop was not invoked.");
        Check(result.Report.CreatedEntities == 1 && result.Report.ReleasedEntities == 1, "Entity cleanup was incomplete.");
        CheckReleased(result);
    }
}

static void MapExceptions()
{
    var result = new MapRunner().Run(Package("ThrowingMap"));
    Check(result.Report.Outcome == MapRunOutcome.Failed, "Expected failure.");
    Check(result.Report.CompletedTicks == 0, "A failed tick was counted as completed.");
    Check(result.Report.Error?.Contains("MapDefinedException", StringComparison.Ordinal) == true, "Missing map error.");
    Check(result.Report.Logs.Contains("stopped-after-error"), "OnStop did not run.");
    Check(result.Report.ReleasedEntities == 1, "Entity leaked after exception.");
    CheckReleased(result);
}

static void BudgetViolation()
{
    var result = new MapRunner().Run(Package("CatchingBudgetMap"));
    Check(result.Report.Outcome == MapRunOutcome.Failed, "A caught budget violation was ignored.");
    Check(result.Report.Error?.Contains("operation budget", StringComparison.Ordinal) == true, "Missing budget error.");
    CheckReleased(result);
}

static void EntityQuota()
{
    var result = new MapRunner().Run(Package("EntityLimitMap"), new MapRunOptions { MaxEntities = 1 });
    Check(result.Report.Outcome == MapRunOutcome.Failed, "Expected entity quota failure.");
    Check(result.Report.CreatedEntities == 1 && result.Report.ReleasedEntities == 1, "Quota failure leaked entities.");
    CheckReleased(result);
}

static void StopFailure()
{
    var result = new MapRunner().Run(Package("StopThrowingMap"));
    Check(result.Report.Outcome == MapRunOutcome.Failed, "Expected stop failure.");
    Check(result.Report.Error?.StartsWith("OnStop:", StringComparison.Ordinal) == true, "Missing stop error.");
    Check(result.Report.ReleasedEntities == 1, "OnStop failure leaked entities.");
    CheckReleased(result);
}

static void LogQuota()
{
    var result = new MapRunner().Run(Package("LogLimitMap"), new MapRunOptions { MaxLogMessages = 1 });
    Check(result.Report.Outcome == MapRunOutcome.Failed, "Expected log quota failure.");
    Check(result.Report.Logs.Count == 1, "Log quota was not enforced.");
    CheckReleased(result);
}

static void InvalidEntry()
{
    var result = new MapRunner().Run(Package("MapDefinedException"));
    Check(result.Report.Outcome == MapRunOutcome.Failed, "Invalid map entry was accepted.");
    CheckReleased(result);
}

static void ManifestTraversal()
{
    var directory = Path.Combine(Path.GetTempPath(), $"runeclr-test-{Guid.NewGuid():N}");
    Directory.CreateDirectory(directory);
    try
    {
        var path = Path.Combine(directory, "map.json");
        File.WriteAllText(path, JsonSerializer.Serialize(new
        {
            id = "outside", entryAssembly = "../outside.dll", entryType = "Outside"
        }));
        Expect<InvalidDataException>(() => MapPackage.FromManifest(path));
    }
    finally
    {
        File.Delete(Path.Combine(directory, "map.json"));
        Directory.Delete(directory);
    }
}

static void InvalidOptions() => Expect<ArgumentOutOfRangeException>(() =>
    new MapRunner().Run(Package("CounterMap"), new MapRunOptions { OperationBudgetPerCallback = 0 }));

static void PrivateDependencies()
{
    var runner = new MapRunner();
    var results = new List<MapRunResult>();
    // Keep retired contexts pending while resolving the next package's same-named assemblies.
    foreach (var (directory, flavor, version) in new[]
    {
        ("dependency-a", "A", "1.0.0.0"),
        ("dependency-b", "B", "2.0.0.0"),
        ("dependency-a", "A", "1.0.0.0")
    })
    {
        var package = new MapPackage(flavor,
            Path.Combine(AppContext.BaseDirectory, directory, "RuneCLR.DependencyMap.dll"),
            "RuneCLR.DependencyMap.DependencyMap");
        var result = runner.Run(package);
        Check(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Dependency map failed.");
        Check(result.Report.Logs.SequenceEqual(new[]
        {
            $"{flavor}:v{version}:starts=1:value=42",
            $"{flavor}:v{version}:starts=1:value=map"
        }), "Private dependency version or generic static state escaped its session.");
        Check(result.Report.CreatedEntities == 1 && result.Report.ReleasedEntities == 1, "Dependency map leaked entities.");
        results.Add(result);
    }

    foreach (var result in results) CheckReleased(result);
    Check(!System.Runtime.Loader.AssemblyLoadContext.Default.Assemblies.Any(assembly =>
        assembly.GetName().Name is "RuneCLR.PrivateDependency" or "RuneCLR.DependencyMap"),
        "Map-private assemblies entered the default context.");
}

static void Generics()
{
    var result = new MapRunner().Run(Package("GenericMap"));
    Check(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Generic map failed.");
    Check(result.Report.Logs.SequenceEqual(new[] { "generic=42:map:7" }), "Incorrect generic result.");
    CheckReleased(result);
}

static void LateMap(string manifest)
{
    var result = new MapRunner().Run(MapPackage.FromManifest(manifest));
    Check(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Late map failed.");
    Check(result.Report.Logs.SequenceEqual(new[] { "late-map=42" }), "Incorrect late map result.");
    Check(result.Report.CreatedEntities == 1 && result.Report.ReleasedEntities == 1, "Late map leaked entities.");
    CheckReleased(result);
}

static void CheckReleased(MapRunResult result)
{
    Check(result.Report.RemainingEntities == 0, "Host resources remain after the session.");
    for (var attempt = 0; attempt < 10 && !result.Unload.IsCollected; attempt++)
    {
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
    }

    Check(result.Unload.IsCollected, "The collectible context is still alive.");
}

static void Expect<T>(Action action) where T : Exception
{
    try
    {
        action();
    }
    catch (T)
    {
        return;
    }

    throw new InvalidOperationException($"Expected {typeof(T).Name}.");
}

static void Check(bool condition, string message)
{
    if (!condition)
    {
        throw new InvalidOperationException(message);
    }
}
