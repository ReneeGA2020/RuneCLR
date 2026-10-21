using System.Reflection;
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
    ("Required interpretation is acknowledged or rejected before loading author IL", RequiredExecutionPolicy),
    ("Invalid execution policies fail before opening author files", InvalidExecutionPolicy),
    ("Private dependency versions and generic statics remain session-local", PrivateDependencies),
    ("Generic collections and constrained calls execute and unload", Generics),
    ("Manifest rejects a missing declared dependency", MissingDependency),
    ("Manifest rejects dependency identity mismatches", DependencyIdentityMismatch),
    ("Manifest rejects dependency paths outside the package", DependencyTraversal),
    ("Manifest rejects dependency hash mismatches", DependencyHashMismatch),
    ("Manifest rejects entry hash mismatches", EntryHashMismatch),
    ("Manifest rejects entries using contract or framework identities", ReservedEntryIdentity),
    ("Manifest rejects duplicate private assembly identities", DuplicateDependencyIdentity),
    ("Direct package construction cannot bypass dependency validation", DirectDependencyValidation),
    ("Map references cannot bind a different declared private version", DependencyReferenceMismatch)
};

RuntimeTestSettings.ExecutionPolicy = args.Contains("--require-interpreter", StringComparer.Ordinal)
    ? MapExecutionPolicy.RequireInterpreter : MapExecutionPolicy.Default;
args = args.Where(argument => argument != "--require-interpreter").ToArray();
tests.AddRange(SessionTests.Cases());
tests.AddRange(HostContractSessionTests.Cases());
tests.AddRange(CallbackDeadlineTests.Cases());

if (args.Length == 2 && args[0] == "--late-map")
{
    var manifest = Path.GetFullPath(args[1]);
    tests.Add(("Map compiled after the host executes and unloads", () => LateMap(manifest)));
}
else if (args.Length != 0)
{
    Console.Error.WriteLine("Usage: RuneCLR.Runtime.Tests [--late-map <manifest>] [--require-interpreter]");
    return 2;
}

// This test intentionally puts a private fixture in the default context. Run it
// last so the existing isolation test can still verify a clean default context.
tests.Add(("Undeclared private dependencies cannot fall back to the default context", DefaultDependencyFallback));

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
        var result = RunMap(runner, Package("CounterMap"));
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
    var result = RunMap(new MapRunner(), Package("ThrowingMap"));
    Check(result.Report.Outcome == MapRunOutcome.Failed, "Expected failure.");
    Check(result.Report.CompletedTicks == 0, "A failed tick was counted as completed.");
    Check(result.Report.Error?.Contains("MapDefinedException", StringComparison.Ordinal) == true, "Missing map error.");
    Check(result.Report.Logs.Contains("stopped-after-error"), "OnStop did not run.");
    Check(result.Report.ReleasedEntities == 1, "Entity leaked after exception.");
    CheckReleased(result);
}

static void BudgetViolation()
{
    var result = RunMap(new MapRunner(), Package("CatchingBudgetMap"));
    Check(result.Report.Outcome == MapRunOutcome.Failed, "A caught budget violation was ignored.");
    Check(result.Report.Error?.Contains("operation budget", StringComparison.Ordinal) == true, "Missing budget error.");
    CheckReleased(result);
}

static void EntityQuota()
{
    var result = RunMap(new MapRunner(), Package("EntityLimitMap"), new MapRunOptions { MaxEntities = 1 });
    Check(result.Report.Outcome == MapRunOutcome.Failed, "Expected entity quota failure.");
    Check(result.Report.CreatedEntities == 1 && result.Report.ReleasedEntities == 1, "Quota failure leaked entities.");
    CheckReleased(result);
}

static void StopFailure()
{
    var result = RunMap(new MapRunner(), Package("StopThrowingMap"));
    Check(result.Report.Outcome == MapRunOutcome.Failed, "Expected stop failure.");
    Check(result.Report.Error?.StartsWith("OnStop:", StringComparison.Ordinal) == true, "Missing stop error.");
    Check(result.Report.ReleasedEntities == 1, "OnStop failure leaked entities.");
    CheckReleased(result);
}

static void LogQuota()
{
    var result = RunMap(new MapRunner(), Package("LogLimitMap"), new MapRunOptions { MaxLogMessages = 1 });
    Check(result.Report.Outcome == MapRunOutcome.Failed, "Expected log quota failure.");
    Check(result.Report.Logs.Count == 1, "Log quota was not enforced.");
    CheckReleased(result);
}

static void InvalidEntry()
{
    var result = RunMap(new MapRunner(), Package("MapDefinedException"));
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

static void InvalidOptions()
{
    Expect<ArgumentOutOfRangeException>(() =>
        RunMap(new MapRunner(), Package("CounterMap"), new MapRunOptions { OperationBudgetPerCallback = 0 }));
    Expect<ArgumentOutOfRangeException>(() =>
        RunMap(new MapRunner(), Package("CounterMap"), new MapRunOptions { MaxScheduledSignals = 0 }));
    Expect<ArgumentOutOfRangeException>(() =>
        RunMap(new MapRunner(), Package("CounterMap"), new MapRunOptions { MaxWorkItems = 0 }));
    Expect<ArgumentOutOfRangeException>(() =>
        RunMap(new MapRunner(), Package("CounterMap"), new MapRunOptions { MaxResources = 0 }));
    // Invalid budgets must win over missing-file and unavailable-runtime failures.
    var missing = new MapPackage("invalid-budget", Path.Combine(Path.GetTempPath(), Guid.NewGuid()+".dll"), "Unused");
    foreach (var limit in new long[] { 0, -1, long.MinValue })
    {
        Expect<ArgumentOutOfRangeException>(() => new MapRunner().Run(missing,
            new MapRunOptions { ExecutionPolicy = MapExecutionPolicy.RequireInterpreter, PrototypeInstructionBudget = limit }));
        Expect<ArgumentOutOfRangeException>(() => new MapRunner().Run(missing,
            new MapRunOptions { ExecutionPolicy = MapExecutionPolicy.RequireInterpreter, PrototypeInstructionBudget = 1, PrototypeCleanupInstructionBudget = limit }));
    }
    Expect<ArgumentException>(() => new MapRunner().Run(missing,
        new MapRunOptions { PrototypeInstructionBudget = 1 }));
}

static void PrivateDependencies()
{
    var runner = new MapRunner();
    var results = new List<MapRunResult>();
    var packages = new List<TemporaryMapPackage>();
    try
    {
        // Keep retired contexts pending while resolving the next package's same-named assemblies.
        foreach (var (directory, flavor, version) in new[]
        {
            ("dependency-a", "A", "1.0.0.0"),
            ("dependency-b", "B", "2.0.0.0"),
            ("dependency-a", "A", "1.0.0.0")
        })
        {
            // Only explicit IL files are staged: resolution cannot use .deps.json.
            var files = new TemporaryMapPackage();
            packages.Add(files);
            files.CopyAssembly(directory, "RuneCLR.DependencyMap.dll");
            var dependency = files.CopyAssembly(directory, "RuneCLR.PrivateDependency.dll");
            var declaration = DeclaredDependency(dependency);
            if (results.Count == 0)
            {
                // Assembly identities and hexadecimal digests are case-insensitive.
                declaration = declaration with
                {
                    AssemblyName = declaration.AssemblyName.ToUpperInvariant(),
                    Sha256 = declaration.Sha256.ToLowerInvariant()
                };
            }
            var package = MapPackage.FromManifest(DependencyManifest(files, declaration));
            var result = RunMap(runner, package);
            results.Add(result);
            Check(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Dependency map failed.");
            Check(result.Report.Logs.SequenceEqual(new[]
            {
                $"{flavor}:v{version}:starts=1:value=42",
                $"{flavor}:v{version}:starts=1:value=map"
            }), "Private dependency version or generic static state escaped its session.");
            Check(result.Report.CreatedEntities == 1 && result.Report.ReleasedEntities == 1, "Dependency map leaked entities.");
        }

        foreach (var result in results) CheckReleased(result);
        Check(!System.Runtime.Loader.AssemblyLoadContext.Default.Assemblies.Any(assembly =>
            assembly.GetName().Name is "RuneCLR.PrivateDependency" or "RuneCLR.DependencyMap"),
            "Map-private assemblies entered the default context.");
    }
    finally
    {
        // Diagnostic collection also allows temporary package deletion on Windows.
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
        foreach (var package in packages) package.Dispose();
    }
}

static void Generics()
{
    var result = RunMap(new MapRunner(), Package("GenericMap"));
    Check(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Generic map failed.");
    Check(result.Report.Logs.SequenceEqual(new[] { "generic=42:map:7" }), "Incorrect generic result.");
    CheckReleased(result);
}

static void MissingDependency()
{
    using var files = DependencyEntry();
    var dependency = DeclaredDependency(Path.Combine(AppContext.BaseDirectory, "dependency-a", "RuneCLR.PrivateDependency.dll"));
    Expect<FileNotFoundException>(() => MapPackage.FromManifest(DependencyManifest(files, dependency)));
}

static void DependencyIdentityMismatch()
{
    using var files = DependencyEntry();
    var dependency = DeclaredDependency(files.CopyAssembly("dependency-a", "RuneCLR.PrivateDependency.dll"));
    var wrongIdentity = dependency.AssemblyName.Replace("Version=1.0.0.0", "Version=2.0.0.0", StringComparison.Ordinal);
    Check(wrongIdentity != dependency.AssemblyName, "The identity fixture did not have its expected version.");
    Expect<InvalidDataException>(() => MapPackage.FromManifest(DependencyManifest(files, dependency with { AssemblyName = wrongIdentity })));
}

static void DependencyTraversal()
{
    using var files = DependencyEntry();
    var path = files.CopyAssembly("dependency-a", "RuneCLR.PrivateDependency.dll");
    var dependency = DeclaredDependency(path);
    foreach (var invalidPath in new[] { "../outside.dll", path })
        Expect<InvalidDataException>(() => MapPackage.FromManifest(DependencyManifest(files, dependency with { Path = invalidPath })));
}

static void DependencyHashMismatch()
{
    using var files = DependencyEntry();
    var dependency = DeclaredDependency(files.CopyAssembly("dependency-a", "RuneCLR.PrivateDependency.dll"));
    Expect<InvalidDataException>(() => MapPackage.FromManifest(DependencyManifest(files, dependency with { Sha256 = new string('0', 64) })));
}

static void EntryHashMismatch()
{
    using var files = new TemporaryMapPackage();
    files.CopyAssembly("fixtures", "RuneCLR.TestMaps.dll");
    var manifest = files.WriteManifest(new
    {
        id = "wrong-entry-hash", entryAssembly = "RuneCLR.TestMaps.dll",
        entryType = "RuneCLR.TestMaps.CounterMap", entrySha256 = new string('0', 64)
    });
    Expect<InvalidDataException>(() => MapPackage.FromManifest(manifest));
}

static void DirectDependencyValidation()
{
    using var files = DependencyEntry();
    var dependency = DeclaredDependency(files.CopyAssembly("dependency-a", "RuneCLR.PrivateDependency.dll"));
    var package = new MapPackage("direct", Path.Combine(files.DirectoryPath, "RuneCLR.DependencyMap.dll"),
        "RuneCLR.DependencyMap.DependencyMap")
    {
        Dependencies = new[] { dependency with { Sha256 = new string('0', 64) } }
    };
    Expect<InvalidDataException>(() => RunMap(new MapRunner(), package));
}

static void ReservedEntryIdentity()
{
    foreach (var assembly in new[] { typeof(RuneCLR.IMapScript).Assembly, typeof(object).Assembly })
    {
        using var files = new TemporaryMapPackage();
        // Bundled mobile assemblies may have an empty Location. The host
        // packaging layout still supplies their real IL files beside the app.
        var source = string.IsNullOrEmpty(assembly.Location)
            ? Path.Combine(AppContext.BaseDirectory, assembly.GetName().Name + ".dll")
            : assembly.Location;
        var path = files.CopyFile(source);
        var manifest = files.WriteManifest(new
        {
            id = "reserved-entry", entryAssembly = Path.GetFileName(path), entryType = "Unused"
        });
        Expect<InvalidDataException>(() => MapPackage.FromManifest(manifest));
    }
}

static void DuplicateDependencyIdentity()
{
    using var files = DependencyEntry();
    var dependencyA = DeclaredDependency(files.CopyAssembly("dependency-a", "RuneCLR.PrivateDependency.dll"));
    var dependencyB = DeclaredDependency(files.CopyAssembly("dependency-b", "RuneCLR.PrivateDependency.dll",
        "PrivateDependency.V2.dll"));
    Expect<InvalidDataException>(() => MapPackage.FromManifest(DependencyManifest(files, dependencyA, dependencyA)));
    // Different versions still have the same simple name within one session.
    Expect<InvalidDataException>(() => MapPackage.FromManifest(DependencyManifest(files, dependencyA, dependencyB)));
}

static void DependencyReferenceMismatch()
{
    // The declaration matches the actual v2 file, but the map requests v1.
    using var files = DependencyEntry();
    var dependency = DeclaredDependency(files.CopyAssembly("dependency-b", "RuneCLR.PrivateDependency.dll"));
    var package = MapPackage.FromManifest(DependencyManifest(files, dependency));
    CheckDependencyFailure(RunMap(new MapRunner(), package));
}

static void DefaultDependencyFallback()
{
    var defaultContext = System.Runtime.Loader.AssemblyLoadContext.Default;
    var dependencyPath = Path.Combine(AppContext.BaseDirectory, "dependency-a", "RuneCLR.PrivateDependency.dll");
    var defaultAssembly = defaultContext.LoadFromAssemblyPath(dependencyPath);
    Check(!defaultAssembly.IsCollectible &&
        System.Runtime.Loader.AssemblyLoadContext.GetLoadContext(defaultAssembly) == defaultContext,
        "The collision seed must belong to the non-collectible default context.");
    Check(defaultContext.Assemblies.Any(assembly => assembly.GetName().Name == "RuneCLR.PrivateDependency"),
        "The fallback test did not establish a default-context collision.");
    // Seed a default-owned static so an incorrectly shared declared dependency
    // cannot accidentally pass the fresh-static assertion below.
    var defaultState = defaultAssembly.GetType("RuneCLR.PrivateDependency.PrivateState`1", throwOnError: true)!
        .MakeGenericType(typeof(int));
    var seedMethod = defaultState.GetMethod("Start")!;
    Console.WriteLine($"DEFAULT_DEPENDENCY_SEED collectible=false module={seedMethod.Module.ModuleVersionId} token=0x{seedMethod.MetadataToken:x8}");
    var seed = (string)seedMethod.Invoke(null, new object[] { 0 })!;
    Check(seed == "A:v1.0.0.0:starts=1:value=0", "Unexpected default-context fixture state.");

    using var files = DependencyEntry();
    var dependency = DeclaredDependency(files.CopyAssembly("dependency-a", "RuneCLR.PrivateDependency.dll"));
    // A physically present DLL and default-context match must not substitute for
    // an omitted declaration. A valid declaration must still resolve privately.
    var undeclared = MapPackage.FromManifest(DependencyManifest(files));
    CheckDependencyFailure(RunMap(new MapRunner(), undeclared));
    var declared = MapPackage.FromManifest(DependencyManifest(files, dependency));
    var result = RunMap(new MapRunner(), declared);
    Check(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Declared collision map failed.");
    Check(result.Report.Logs.SequenceEqual(new[] { "A:v1.0.0.0:starts=1:value=42", "A:v1.0.0.0:starts=1:value=map" }),
        "Declared private statics did not remain session-local with a default-context collision.");
    CheckReleased(result);
}

static void CheckDependencyFailure(MapRunResult result)
{
    Check(result.Report.Outcome == MapRunOutcome.Failed, "Invalid private dependency resolution succeeded.");
    Check(result.Report.Error?.Contains("FileLoadException", StringComparison.Ordinal) == true, "Expected a dependency binding failure.");
    Check(result.Report.Logs.Count == 0 && result.Report.CreatedEntities == 0, "Dependency failure executed map side effects.");
    CheckReleased(result);
}

static TemporaryMapPackage DependencyEntry()
{
    var files = new TemporaryMapPackage();
    files.CopyAssembly("dependency-a", "RuneCLR.DependencyMap.dll");
    return files;
}

static MapDependency DeclaredDependency(string path) => new(Path.GetFileName(path),
    AssemblyName.GetAssemblyName(path).FullName!, TemporaryMapPackage.Sha256(path));

static string DependencyManifest(TemporaryMapPackage files, params MapDependency[] dependencies) =>
    files.WriteManifest(new
    {
        id = "dependency-fixture", entryAssembly = "RuneCLR.DependencyMap.dll",
        entryType = "RuneCLR.DependencyMap.DependencyMap",
        entrySha256 = TemporaryMapPackage.Sha256(Path.Combine(files.DirectoryPath, "RuneCLR.DependencyMap.dll")),
        dependencies = dependencies.Select(dependency => new
        {
            path = dependency.Path, assemblyName = dependency.AssemblyName, sha256 = dependency.Sha256
        })
    });

static void LateMap(string manifest)
{
    var result = RunMap(new MapRunner(), MapPackage.FromManifest(manifest));
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


static MapRunResult RunMap(MapRunner runner, MapPackage package, MapRunOptions? options = null)
{
    options = (options ?? new MapRunOptions()) with { ExecutionPolicy = RuntimeTestSettings.ExecutionPolicy };
    var result = runner.Run(package, options);
    Check(result.Report.ExecutionPolicy == options.ExecutionPolicy, "Session did not report the requested policy.");
    Check(result.Report.PrototypeBudget is null, "Unbudgeted session unexpectedly acquired a native instruction budget.");
    if (options.ExecutionPolicy == MapExecutionPolicy.RequireInterpreter)
    {
        Check(result.Report.ExecutionPolicyVersion == 1, "Missing native context-policy acknowledgment.");
        if (!RuntimeTestSettings.MarkerWritten)
        {
            Console.WriteLine("SESSION_EXECUTION_POLICY required-interpreter version=1");
            RuntimeTestSettings.MarkerWritten = true;
        }
    }
    else Check(result.Report.ExecutionPolicyVersion == 0, "Ordinary session unexpectedly acquired a policy.");
    return result;
}

static void RequiredExecutionPolicy()
{
    var type = typeof(System.Runtime.Loader.AssemblyLoadContext);
    var versionMethod = type.GetMethod("RuneCLR_GetExecutionPolicyVersion", BindingFlags.NonPublic | BindingFlags.Static,
        binder: null, types: Type.EmptyTypes, modifiers: null);
    var supported = versionMethod is not null && versionMethod.ReturnType == typeof(int) && versionMethod.CreateDelegate<Func<int>>()() == 1;
    var authorLoads = 0;
    void Observe(object? sender, AssemblyLoadEventArgs loaded)
    {
        if (loaded.LoadedAssembly.IsCollectible && loaded.LoadedAssembly.GetName().Name == "RuneCLR.TestMaps") authorLoads++;
    }
    AppDomain.CurrentDomain.AssemblyLoad += Observe;
    try
    {
        var options = new MapRunOptions { ExecutionPolicy = MapExecutionPolicy.RequireInterpreter, TickCount = 0 };
        if (!supported)
        {
            Expect<PlatformNotSupportedException>(() => new MapRunner().Run(Package("CounterMap"), options));
            Check(authorLoads == 0, "Unsupported policy loaded author IL before rejection.");
            var missing = new MapPackage("unsupported", Path.Combine(Path.GetTempPath(), Guid.NewGuid()+".dll"), "Unused");
            Expect<PlatformNotSupportedException>(() => new MapRunner().Run(missing, options));
            Check(authorLoads == 0, "Unsupported policy opened or executed the missing author package.");
            return;
        }
        var result = new MapRunner().Run(Package("CounterMap"), options);
        Check(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Required session failed.");
        Check(result.Report.ExecutionPolicy == MapExecutionPolicy.RequireInterpreter && result.Report.ExecutionPolicyVersion == 1,
            "Supported runtime failed to acknowledge required native policy.");
        Check(authorLoads == 1 && result.Report.Logs.SequenceEqual(new[] { "starts=1", "stopped" }), "Required session did not execute fresh author state.");
        CheckReleased(result);
    }
    finally { AppDomain.CurrentDomain.AssemblyLoad -= Observe; }
}

static void InvalidExecutionPolicy()
{
    var missing = new MapPackage("invalid-policy", Path.Combine(Path.GetTempPath(), Guid.NewGuid()+".dll"), "Unused");
    Expect<ArgumentOutOfRangeException>(() => new MapRunner().Run(missing,
        new MapRunOptions { ExecutionPolicy = (MapExecutionPolicy)int.MaxValue }));
}

internal static class RuntimeTestSettings
{
    public static MapExecutionPolicy ExecutionPolicy;
    public static bool MarkerWritten;
}
