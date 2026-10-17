using System.Diagnostics;
using RuneCLR;
using RuneCLR.Compiler;
using RuneCLR.Packages;
using RuneCLR.Runtime;

internal static class PipelineCases
{
    internal const string Script = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            private static int starts;
            private IMapContext? context;
            public void OnStart(IMapContext value) { context = value; context.Log("starts=" + (++starts)); context.SpawnEntity("test"); }
            public void OnTick(MapTick tick) { context!.Log("tick=" + tick.Index); }
            public void OnStop() { context!.Log("stopped"); }
        }
        """;

    internal static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Source to versioned package runs and unloads across successive sessions", SourceLifecycle);
        yield return ("Modern C# source packages execute and retire with the existing UGC policy", ModernLanguageLifecycle);
        yield return ("Same source produces identical package identities independent of output path", DeterministicPackage);
        yield return ("Raw IL import preserves bytes and runs through the same versioned loader", ImportLifecycle);
        yield return ("Changed files are rejected and the next valid session still succeeds", TamperRecovery);
        yield return ("Compilation errors publish no package and existing outputs are preserved", FailedPublication);
        yield return ("Input and reference snapshots survive later operator file changes", ReferenceSnapshot);
        yield return ("Version-distinct private dependencies stay isolated in source and IL packages", PrivateDependencies);
        yield return ("Undeclared transitive dependencies fail intake before publication", UndeclaredDependency);
        yield return ("A packaged author exception cleans up, unloads and permits the next package", AuthorFailure);
        yield return ("Package build records the host interface and allowed methods", HostInterfaceFields);
        yield return ("Package build rejects an OnStart call outside the allowed methods", HostInterfaceRejectsUnlisted);
        yield return ("Package build rejects a later callback outside the allowed methods", LaterCallbackRejectsUnlisted);
        yield return ("Package build requires both host interface fields", HostInterfacePairRequired);
        yield return ("Compiled host-contract package opens and runs OnStart", HostInterfaceSession);
        yield return ("Compiled host-contract package charges from OnStart", HostInterfaceOnStartCharges);
        yield return ("Compiled host-contract package destroys an entity from OnStart", HostInterfaceOnStartDestroys);
        yield return ("Compiled host-contract package reads MapId from OnStart", HostInterfaceOnStartReadsMapId);
        yield return ("Compiled host-contract package rejects the MapId property name", HostInterfaceRejectsMapIdPropertyName);
        yield return ("Compiled host-contract package reads MapId from a later callback", HostInterfaceLaterReadsMapId);
        yield return ("Imported host-contract IL reads MapId from a later callback", HostInterfaceImportsLaterMapId);
        yield return ("Imported host-contract IL rejects the MapId property name", HostInterfaceImportRejectsMapIdPropertyName);
        yield return ("Compiled host-contract package releases a stored entity", HostInterfaceReleasesStoredEntity);
        yield return ("Compiled host-contract package runs a later callback", HostInterfaceLaterCallback);
        yield return ("Compiled host-contract package returns an int from a later callback", HostInterfaceReturnsInt);
        yield return ("Compiled host-contract package passes the host and an int", HostInterfacePassesHostAndInt);
        yield return ("Compiled host-contract package passes only an int", HostInterfacePassesIntOnly);
        yield return ("Compiled host-contract package returns an int with the host", HostInterfaceReturnsHostAndInt);
        yield return ("Compiled host-contract package calls a private assembly from a later callback", HostInterfacePrivateCallback);
        yield return ("Compiled host-contract package lets a private assembly read MapId", HostInterfacePrivateReadsMapId);
        yield return ("Compiled host-contract package lets a private assembly charge", HostInterfacePrivateCharges);
        yield return ("Compiled host-contract package lets a private assembly spawn", HostInterfacePrivateSpawns);
        yield return ("Compiled host-contract package lets a private assembly destroy", HostInterfacePrivateDestroys);
        yield return ("Compiled host-contract package lets a private assembly log", HostInterfacePrivateLogs);
        yield return ("Imported host-contract IL lets a private assembly log", HostInterfaceImportsPrivateLog);
        yield return ("Imported host-contract IL lets a private assembly destroy", HostInterfaceImportsPrivateDestroy);
        yield return ("Imported host-contract IL lets a private assembly spawn", HostInterfaceImportsPrivateSpawn);
        yield return ("Imported host-contract IL lets a private assembly charge", HostInterfaceImportsPrivateCharge);
        yield return ("Imported host-contract IL lets a private assembly read MapId", HostInterfaceImportsPrivateMapId);
        yield return ("Compiled host-contract package lets one private assembly call another", HostInterfacePrivateChain);
        yield return ("Compiled host-contract package lets a second private assembly log", HostInterfacePrivateChainLogs);
        yield return ("Compiled host-contract package lets a second private assembly read MapId", HostInterfacePrivateChainReadsMapId);
        yield return ("Compiled host-contract package lets a second private assembly charge", HostInterfacePrivateChainCharges);
        yield return ("Compiled host-contract package lets a second private assembly destroy", HostInterfacePrivateChainDestroys);
        yield return ("Compiled host-contract package returns an entity from a second private assembly", HostInterfacePrivateChainReturnsEntity);
        yield return ("Imported host-contract IL returns an entity from a second private assembly", HostInterfaceImportsPrivateChainReturnsEntity);
        yield return ("Imported host-contract IL lets a second private assembly destroy", HostInterfaceImportsPrivateChainDestroys);
        yield return ("Imported host-contract IL lets a second private assembly charge", HostInterfaceImportsPrivateChainCharges);
        yield return ("Imported host-contract IL lets a second private assembly read MapId", HostInterfaceImportsPrivateChainReadsMapId);
        yield return ("Compiled host-contract package rejects a second private spawn", HostInterfacePrivateChainRejectsSpawn);
        yield return ("Imported host-contract IL rejects a second private spawn", HostInterfaceImportsPrivateChainRejectsSpawn);
        yield return ("Imported host-contract IL lets a second private assembly log", HostInterfaceImportsPrivateChainLogs);
        yield return ("Compiled host-contract package lets a private assembly call the entry", HostInterfacePrivateCallsEntry);
        yield return ("Compiled host-contract package constructs an author type", HostInterfaceConstructsAuthorType);
        yield return ("Compiled host-contract package rejects a framework constructor", HostInterfaceRejectsFrameworkNew);
        yield return ("Compiled host-contract package constructs a private assembly type", HostInterfaceConstructsPrivateType);
        yield return ("Imported host-contract IL opens and returns an int", HostInterfaceImportsIl);
        yield return ("Imported host-contract IL returns an int with the host", HostInterfaceImportsHostMeasure);
        yield return ("Imported host-contract IL passes only an int", HostInterfaceImportsIntOnly);
        yield return ("Imported host-contract IL passes the host and an int", HostInterfaceImportsHostAndInt);
        yield return ("Imported host-contract IL runs a later callback", HostInterfaceImportsLaterCallback);
        yield return ("Imported host-contract IL constructs an author type", HostInterfaceImportsAuthorType);
        yield return ("Imported host-contract IL constructs a private type", HostInterfaceImportsPrivateType);
        yield return ("Imported host-contract IL lets one private assembly call another", HostInterfaceImportsPrivateChain);
        yield return ("Imported host-contract IL runs OnStart", HostInterfaceImportsOnStart);
        yield return ("Imported host-contract IL charges from OnStart", HostInterfaceImportsOnStartCharge);
        yield return ("Imported host-contract IL destroys an entity from OnStart", HostInterfaceImportsOnStartDestroy);
        yield return ("Imported host-contract IL reads MapId from OnStart", HostInterfaceImportsOnStartMapId);
        yield return ("Imported host-contract IL releases a stored entity", HostInterfaceImportsStoredEntity);
        yield return ("Imported host-contract IL calls a private assembly", HostInterfaceImportsPrivate);
        yield return ("Imported host-contract IL rejects a framework constructor", HostInterfaceImportRejectsFrameworkNew);
        yield return ("Imported host-contract IL lets a private assembly call the entry", HostInterfaceImportPrivateCallsEntry);
        yield return ("Operator CLI compiles a host-contract package", HostInterfaceOperatorCli);
        yield return ("Operator CLI rejects a framework constructor", HostInterfaceOperatorCliRejectsFrameworkNew);
        yield return ("Operator CLI imports a host-contract assembly", HostInterfaceOperatorCliImportsIl);
        yield return ("Operator CLI import rejects a framework constructor", HostInterfaceOperatorCliImportRejectsFrameworkNew);
        yield return ("Operator CLI compiles a private dependency", HostInterfaceOperatorCliCompilesDependency);
        yield return ("Operator CLI imports a private dependency", HostInterfaceOperatorCliImportsDependency);
        yield return ("Operator CLI validates a host-contract package", HostInterfaceOperatorCliValidates);
        yield return ("Operator CLI rejects a tampered host-contract manifest", HostInterfaceOperatorCliRejectsTamperedManifest);
        yield return ("Operator CLI rejects a changed host-contract file", HostInterfaceOperatorCliRejectsChangedFile);
        yield return ("Operator CLI rejects an extra host-contract file", HostInterfaceOperatorCliRejectsExtraFile);
        yield return ("Operator CLI rejects a partial host-contract pair", HostInterfaceOperatorCliRejectsPartialPair);
        yield return ("Operator CLI rejects unknown arguments", OperatorCliRejectsBadArguments);
        yield return ("Operator CLI rejects a repeated or blank allowed method", OperatorCliRejectsRepeatedAllowedMethod);
        yield return ("Operator CLI rejects a non-source file", OperatorCliRejectsNonSourceFile);
        yield return ("Operator CLI rejects a deeply nested source", OperatorCliRejectsDeepSource);
        yield return ("Operator CLI rejects a linked source directory", OperatorCliRejectsSourceLink);
        yield return ("Operator CLI rejects an oversized source directory", OperatorCliRejectsSourceLimit);
        yield return ("Operator CLI rejects an unknown option", OperatorCliRejectsUnknownOption);
        yield return ("Operator CLI rejects a compiler error", OperatorCliRejectsCompileError);
        yield return ("Operator CLI rejects a file that is not an assembly", OperatorCliRejectsBadImport);
        yield return ("Operator CLI rejects a missing entry type", OperatorCliRejectsMissingEntry);
        yield return ("Operator CLI reads MapId from OnStart", OperatorCliReadsMapId);
        yield return ("Operator CLI imports a MapId read", OperatorCliImportsMapId);
        yield return ("Operator CLI rejects the MapId property name", OperatorCliRejectsMapIdName);
        yield return ("Operator CLI import rejects the MapId property name", OperatorCliImportRejectsMapIdName);
        yield return ("Operator CLI compiles two private dependencies", OperatorCliCompilesTwoDependencies);
        yield return ("Operator CLI imports two private dependencies", OperatorCliImportsTwoDependencies);
        yield return ("Operator CLI rejects a changed private dependency", OperatorCliRejectsChangedDependency);
        yield return ("Operator CLI rejects a private dependency identity", OperatorCliRejectsDependencyIdentity);
        yield return ("Operator CLI rejects a linked package file", OperatorCliRejectsPackageLink);
        yield return ("Operator CLI rejects a deeply nested package", OperatorCliRejectsPackageNesting);
        yield return ("Operator CLI rejects a spoofed entry assembly", OperatorCliRejectsSpoofedEntry);
        yield return ("Operator CLI rejects an oversized entry", OperatorCliRejectsOversizedEntry);
        yield return ("Operator CLI rejects an unsupported package format", OperatorCliRejectsPackageFormat);
        yield return ("Operator CLI rejects an unsupported producer input kind", OperatorCliRejectsProducerKind);
        yield return ("Operator CLI rejects empty producer references", OperatorCliRejectsEmptyProducerReferences);
        yield return ("Operator CLI rejects a missing host contract reference", OperatorCliRejectsMissingContractReference);
        yield return ("Operator CLI rejects a blank package id", OperatorCliRejectsBlankPackageId);
        yield return ("Operator CLI rejects a blank producer tool", OperatorCliRejectsBlankProducerTool);
        yield return ("Operator CLI rejects an escaping entry path", OperatorCliRejectsEscapingPath);
        yield return ("Operator CLI rejects an entry path segment that ends with a dot", OperatorCliRejectsDottedPath);
        yield return ("Operator CLI rejects an entry that is not a DLL", OperatorCliRejectsNonDllEntry);
        yield return ("Operator CLI rejects a file list that omits the entry", OperatorCliRejectsUnlistedEntry);
        yield return ("Operator CLI rejects an entry hash that disagrees with the file list", OperatorCliRejectsMismatchedFileHash);
        yield return ("Operator CLI rejects an escaping dependency path", OperatorCliRejectsEscapingDependency);
        yield return ("Operator CLI rejects a dependency that is not a managed assembly", OperatorCliRejectsOpaqueDependency);
        yield return ("Operator CLI rejects a dependency that spoofs a framework name", OperatorCliRejectsSpoofedDependency);
        yield return ("Operator CLI rejects a dependency that duplicates the entry", OperatorCliRejectsDuplicateEntryIdentity);
        yield return ("Operator CLI rejects a dependency declared as the host contract", OperatorCliRejectsContractDependency);
        yield return ("Operator CLI rejects two dependencies with the same identity", OperatorCliRejectsDuplicateDependencyIdentity);
        yield return ("Operator CLI rejects a missing dependency file", OperatorCliRejectsMissingDependency);
        yield return ("Operator CLI rejects a blank producer tool version", OperatorCliRejectsBlankProducerToolVersion);
        yield return ("Operator CLI rejects empty producer sources", OperatorCliRejectsEmptyProducerSources);
        yield return ("Operator CLI rejects empty producer compiler identities", OperatorCliRejectsEmptyProducerCompiler);
        yield return ("Operator CLI rejects a repeated producer compiler name", OperatorCliRejectsDuplicateProducerCompiler);
        yield return ("Operator CLI rejects a repeated producer source name", OperatorCliRejectsDuplicateProducerSource);
    }
    private const string HostFieldScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            public void OnStart(IMapContext context)
            {
                context.Log("ok");
                context.SpawnEntity("fixture");
            }
            public void OnTick(MapTick tick) { }
            public void OnStop() { }
        }
        """;

    private static void HostInterfaceFields()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostFields", "GameScript", [new("GameScript.cs", HostFieldScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["SpawnEntity", "Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        Check.Assert(manifest.HostInterface == "RuneCLR.IMapContext", "Host interface was not written.");
        Check.Assert(manifest.AllowedMethods is not null && manifest.AllowedMethods.SequenceEqual(["Log", "SpawnEntity"]),
            "Allowed methods were not stored canonically.");
    }

    private static void HostInterfaceSession()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostFields", "GameScript", [new("GameScript.cs", HostFieldScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["SpawnEntity", "Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
        Check.Assert(host.Spawned == "fixture", host.Spawned ?? "no entity");
    }

    private const string OnStartChargeScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            public void OnStart(IMapContext context) { context.Log("ok"); context.Charge(7); }
            public void OnTick(MapTick tick) { }
            public void OnStop() { }
        }
        """;

    private static void HostInterfaceOnStartCharges()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCharge", "GameScript", [new("GameScript.cs", OnStartChargeScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "Charge"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Charged == 7, "Charge received " + host.Charged + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private const string OnStartDestroyScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            public void OnStart(IMapContext context)
            {
                context.Log("ok");
                var id = context.SpawnEntity("fixture");
                context.DestroyEntity(id);
            }
            public void OnTick(MapTick tick) { }
            public void OnStop() { }
        }
        """;

    private static void HostInterfaceOnStartDestroys()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostDestroy", "GameScript", [new("GameScript.cs", OnStartDestroyScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "SpawnEntity", "DestroyEntity"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Spawned == "fixture", host.Spawned ?? "no entity");
        Check.Assert(host.Destroyed == new EntityId(1), "Destroy received " + host.Destroyed + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private const string OnStartMapIdScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            public void OnStart(IMapContext context) { context.Log(context.MapId); }
            public void OnTick(MapTick tick) { }
            public void OnStop() { }
        }
        """;

    private static void HostInterfaceOnStartReadsMapId()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostMapId", "GameScript", [new("GameScript.cs", OnStartMapIdScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "get_MapId"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["fixture"]), string.Join(", ", host.Logs));
    }

    private const string StoredEntityScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            private EntityId id;
            public void OnStart(IMapContext context)
            {
                context.Log("ok");
                id = context.SpawnEntity("fixture");
            }
            public void OnTick(MapTick tick) { }
            public void OnStop() { }
            public void Release(IMapContext context) { context.DestroyEntity(id); }
        }
        """;

    private static void HostInterfaceReleasesStoredEntity()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostRelease", "GameScript", [new("GameScript.cs", StoredEntityScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "SpawnEntity", "DestroyEntity"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Invoke("Release");
        session.Dispose();
        Check.Assert(host.Spawned == "fixture", host.Spawned ?? "no entity");
        Check.Assert(host.Destroyed == new EntityId(1), "Destroy received " + host.Destroyed + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceRejectsMapIdPropertyName()
    {
        using var temp = new TempDirectory();
        var output = Path.Combine(temp.Path, "package");
        var error = Check.Throws<InvalidDataException>(() => PackageBuilder.Compile("HostMapName", "GameScript",
            [new("GameScript.cs", OnStartMapIdScript)], Profile(), output,
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "MapId"]));
        Check.Assert(error.Message.Contains("get_MapId", StringComparison.Ordinal), error.Message);
        Check.Assert(error.Message.Contains("OnStart", StringComparison.Ordinal), error.Message);
        Check.Assert(!Directory.Exists(output), "A property-name allow list published a package.");
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");
    }

    private static void HostInterfaceImportRejectsMapIdPropertyName()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostImportMapName", [new("GameScript.cs", OnStartMapIdScript)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportMapName.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var output = Path.Combine(temp.Path, "package");
        var error = Check.Throws<InvalidDataException>(() => PackageBuilder.Import("HostImportMapName", "GameScript", dll, Profile(), output,
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "MapId"]));
        Check.Assert(error.Message.Contains("get_MapId", StringComparison.Ordinal), error.Message);
        Check.Assert(error.Message.Contains("OnStart", StringComparison.Ordinal), error.Message);
        Check.Assert(!Directory.Exists(output), "A property-name allow list published a package.");
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");
    }

    private const string LaterMapIdScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            private IMapContext? context;
            public void OnStart(IMapContext value) { context = value; context.Log("ok"); }
            public void OnTick(MapTick tick) { }
            public void OnStop() { context!.Log(context.MapId); }
        }
        """;

    private static void HostInterfaceLaterReadsMapId()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostLaterMap", "GameScript", [new("GameScript.cs", LaterMapIdScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "get_MapId"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Invoke("OnStop");
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["ok", "fixture"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsLaterMapId()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostImportLaterMap", [new("GameScript.cs", LaterMapIdScript)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportLaterMap.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportLaterMap", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "get_MapId"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Invoke("OnStop");
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["ok", "fixture"]), string.Join(", ", host.Logs));
    }

    private const string LaterSessionScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            private IMapContext? context;
            public void OnStart(IMapContext value) { context = value; context.Log("ok"); }
            public void OnTick(MapTick tick) { }
            public void OnStop() { context!.Log("stopped"); }
        }
        """;

    private static void HostInterfaceLaterCallback()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostLater", "GameScript", [new("GameScript.cs", LaterSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Invoke("OnStop");
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["ok", "stopped"]), string.Join(", ", host.Logs));
    }

    private const string IntSessionScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            public void OnStart(IMapContext context) { context.Log("ok"); }
            public void OnTick(MapTick tick) { }
            public void OnStop() { }
            public int Measure(int value) => value + 1;
        }
        """;

    private static void HostInterfaceReturnsInt()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostInt", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 40);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private const string HostAndIntScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            public void OnStart(IMapContext context) { context.Log("ok"); }
            public void OnTick(MapTick tick) { }
            public void OnStop() { }
            public void Report(IMapContext context, int value) { context.Charge(value); }
        }
        """;

    private static void HostInterfacePassesHostAndInt()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostAndInt", "GameScript", [new("GameScript.cs", HostAndIntScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "Charge"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Invoke("Report", 41);
        session.Dispose();
        Check.Assert(host.Charged == 41, "Charge received " + host.Charged + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private const string IntOnlyScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            private IMapContext? context;
            public void OnStart(IMapContext value) { context = value; context.Log("ok"); }
            public void OnTick(MapTick tick) { }
            public void OnStop() { }
            public void Apply(int value) { context!.Charge(value); }
        }
        """;

    private static void HostInterfacePassesIntOnly()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostIntOnly", "GameScript", [new("GameScript.cs", IntOnlyScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "Charge"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Invoke("Apply", 41);
        session.Dispose();
        Check.Assert(host.Charged == 41, "Charge received " + host.Charged + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private const string HostMeasureScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            public void OnStart(IMapContext context) { context.Log("ok"); }
            public void OnTick(MapTick tick) { }
            public void OnStop() { }
            public int Measure(IMapContext context, int value) { context.Charge(value); return value + 1; }
        }
        """;

    private static void HostInterfaceReturnsHostAndInt()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostMeasure", "GameScript", [new("GameScript.cs", HostMeasureScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "Charge"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 40);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Charged == 40, "Charge received " + host.Charged + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfacePrivateCallback()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "input"), "SharedLibrary", """
            public static class SharedHelper { public static int AddOne(int value) => value + 1; }
            """);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
                public int Measure(int value) => SharedHelper.AddOne(value);
            }
            """;
        var build = PackageBuilder.Compile("HostPrivate", "GameScript", [new("GameScript.cs", script)], Profile(),
            Path.Combine(temp.Path, "package"), [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 40);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfacePrivateReadsMapId()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "input"), "SharedMap", """
            using RuneCLR;
            public static class SharedMap { public static string Id(IMapContext context) => context.MapId; }
            """);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log(SharedMap.Id(context)); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var build = PackageBuilder.Compile("HostPrivateMap", "GameScript", [new("GameScript.cs", script)], Profile(),
            Path.Combine(temp.Path, "package"), [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "get_MapId"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["fixture"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfacePrivateCharges()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "input"), "SharedBill", """
            using RuneCLR;
            public static class SharedBill { public static void Bill(IMapContext context) => context.Charge(7); }
            """);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); SharedBill.Bill(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var build = PackageBuilder.Compile("HostPrivateCharge", "GameScript", [new("GameScript.cs", script)], Profile(),
            Path.Combine(temp.Path, "package"), [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "Charge"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Charged == 7, "Charge received " + host.Charged + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfacePrivateSpawns()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "input"), "SharedSpawn", """
            using RuneCLR;
            public static class SharedSpawn { public static EntityId Create(IMapContext context) => context.SpawnEntity("fixture"); }
            """);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context)
                {
                    context.Log("ok");
                    var id = SharedSpawn.Create(context);
                    context.DestroyEntity(id);
                }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var build = PackageBuilder.Compile("HostPrivateSpawn", "GameScript", [new("GameScript.cs", script)], Profile(),
            Path.Combine(temp.Path, "package"), [helper], hostInterface: "RuneCLR.IMapContext",
            allowedMethods: ["Log", "SpawnEntity", "DestroyEntity"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Spawned == "fixture", host.Spawned ?? "no entity");
        Check.Assert(host.Destroyed == new EntityId(1), "Destroy received " + host.Destroyed + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfacePrivateDestroys()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "input"), "SharedLife", """
            using RuneCLR;
            public static class SharedLife
            {
                public static void Cycle(IMapContext context)
                {
                    var id = context.SpawnEntity("fixture");
                    context.DestroyEntity(id);
                }
            }
            """);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); SharedLife.Cycle(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var build = PackageBuilder.Compile("HostPrivateLife", "GameScript", [new("GameScript.cs", script)], Profile(),
            Path.Combine(temp.Path, "package"), [helper], hostInterface: "RuneCLR.IMapContext",
            allowedMethods: ["Log", "SpawnEntity", "DestroyEntity"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Spawned == "fixture", host.Spawned ?? "no entity");
        Check.Assert(host.Destroyed == new EntityId(1), "Destroy received " + host.Destroyed + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfacePrivateLogs()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "input"), "SharedNote", """
            using RuneCLR;
            public static class SharedNote { public static void Note(IMapContext context) => context.Log("from-private"); }
            """);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); SharedNote.Note(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var build = PackageBuilder.Compile("HostPrivateLog", "GameScript", [new("GameScript.cs", script)], Profile(),
            Path.Combine(temp.Path, "package"), [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["ok", "from-private"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfacePrivateChain()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedSecond", """
            public static class Second { public static int AddOne(int value) => value + 1; }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedFirst", """
            public static class First { public static int Through(int value) => Second.AddOne(value); }
            """, [second]);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
                public int Measure(int value) => First.Through(value);
            }
            """;
        var build = PackageBuilder.Compile("HostChain", "GameScript", [new("GameScript.cs", script)], Profile(),
            Path.Combine(temp.Path, "package"), [first, second], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 40);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfacePrivateChainLogs()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedLogSecond", """
            using RuneCLR;
            public static class Second { public static void Note(IMapContext context) => context.Log("from-second"); }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedLogFirst", """
            using RuneCLR;
            public static class First { public static void Through(IMapContext context) => Second.Note(context); }
            """, [second]);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); First.Through(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var build = PackageBuilder.Compile("HostChainLog", "GameScript", [new("GameScript.cs", script)], Profile(),
            Path.Combine(temp.Path, "package"), [first, second], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["ok", "from-second"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfacePrivateChainRejectsSpawn()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedSpawnSecond", """
            using RuneCLR;
            public static class Second { public static void Note(IMapContext context) => context.SpawnEntity("nope"); }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedSpawnFirst", """
            using RuneCLR;
            public static class First { public static void Through(IMapContext context) => Second.Note(context); }
            """, [second]);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); First.Through(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var output = Path.Combine(temp.Path, "package");
        var error = Check.Throws<InvalidDataException>(() => PackageBuilder.Compile("HostChainSpawn", "GameScript",
            [new("GameScript.cs", script)], Profile(), output, [first, second],
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]));
        Check.Assert(error.Message.Contains("OnStart", StringComparison.Ordinal), error.Message);
        Check.Assert(error.Message.Contains("SpawnEntity", StringComparison.Ordinal), error.Message);
        Check.Assert(!Directory.Exists(output), "An unlisted private spawn published a package.");
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");
    }

    private static void HostInterfacePrivateChainReadsMapId()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedIdSecond", """
            using RuneCLR;
            public static class Second { public static string Id(IMapContext context) => context.MapId; }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedIdFirst", """
            using RuneCLR;
            public static class First { public static string Through(IMapContext context) => Second.Id(context); }
            """, [second]);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log(First.Through(context)); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var build = PackageBuilder.Compile("HostChainMap", "GameScript", [new("GameScript.cs", script)], Profile(),
            Path.Combine(temp.Path, "package"), [first, second], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "get_MapId"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["fixture"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfacePrivateChainCharges()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedBillSecond", """
            using RuneCLR;
            public static class Second { public static void Bill(IMapContext context) => context.Charge(7); }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedBillFirst", """
            using RuneCLR;
            public static class First { public static void Through(IMapContext context) => Second.Bill(context); }
            """, [second]);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); First.Through(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var build = PackageBuilder.Compile("HostChainCharge", "GameScript", [new("GameScript.cs", script)], Profile(),
            Path.Combine(temp.Path, "package"), [first, second], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "Charge"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Charged == 7, "Charge received " + host.Charged + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfacePrivateChainDestroys()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedLifeSecond", """
            using RuneCLR;
            public static class Second
            {
                public static void Cycle(IMapContext context)
                {
                    var id = context.SpawnEntity("fixture");
                    context.DestroyEntity(id);
                }
            }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedLifeFirst", """
            using RuneCLR;
            public static class First { public static void Through(IMapContext context) => Second.Cycle(context); }
            """, [second]);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); First.Through(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var build = PackageBuilder.Compile("HostChainLife", "GameScript", [new("GameScript.cs", script)], Profile(),
            Path.Combine(temp.Path, "package"), [first, second], hostInterface: "RuneCLR.IMapContext",
            allowedMethods: ["Log", "SpawnEntity", "DestroyEntity"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Spawned == "fixture", host.Spawned ?? "no entity");
        Check.Assert(host.Destroyed == new EntityId(1), "Destroy received " + host.Destroyed + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfacePrivateChainReturnsEntity()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedReturnSecond", """
            using RuneCLR;
            public static class Second { public static EntityId Create(IMapContext context) => context.SpawnEntity("fixture"); }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedReturnFirst", """
            using RuneCLR;
            public static class First { public static EntityId Through(IMapContext context) => Second.Create(context); }
            """, [second]);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context)
                {
                    context.Log("ok");
                    var id = First.Through(context);
                    context.DestroyEntity(id);
                }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var build = PackageBuilder.Compile("HostChainReturn", "GameScript", [new("GameScript.cs", script)], Profile(),
            Path.Combine(temp.Path, "package"), [first, second], hostInterface: "RuneCLR.IMapContext",
            allowedMethods: ["Log", "SpawnEntity", "DestroyEntity"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Spawned == "fixture", host.Spawned ?? "no entity");
        Check.Assert(host.Destroyed == new EntityId(1), "Destroy received " + host.Destroyed + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfacePrivateCallsEntry()
    {
        using var temp = new TempDirectory();
        var stub = EmitDependency(Path.Combine(temp.Path, "stub"), "HostReturn", """
            [assembly: System.Reflection.AssemblyVersion("1.0.0.0")]
            public sealed class GameScript { public static int FromEntry(int value) => value + 1; }
            """);
        var helper = EmitDependency(Path.Combine(temp.Path, "helper"), "SharedReturn", """
            [assembly: System.Reflection.AssemblyVersion("1.0.0.0")]
            public static class Helper { public static int Through(int value) => GameScript.FromEntry(value); }
            """, [stub]);
        const string script = """
            using RuneCLR;
            [assembly: System.Reflection.AssemblyVersion("1.0.0.0")]
            public sealed class GameScript : IMapScript
            {
                public static int FromEntry(int value) => value + 1;
                public void OnStart(IMapContext context) { context.Log("ok"); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
                public int Measure(int value) => Helper.Through(value);
            }
            """;
        var build = PackageBuilder.Compile("HostReturn", "GameScript", [new("GameScript.cs", script)], Profile(),
            Path.Combine(temp.Path, "package"), [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 40);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private const string AuthorTypeScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            public void OnStart(IMapContext context) { context.Log("ok"); }
            public void OnTick(MapTick tick) { }
            public void OnStop() { }
            public int Measure(int value) => new Box(value).Get();
        }

        public sealed class Box
        {
            private readonly int value;
            public Box(int value) { this.value = value; }
            public int Get() => value;
        }
        """;

    private static void HostInterfaceConstructsAuthorType()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostBox", "GameScript", [new("GameScript.cs", AuthorTypeScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 41);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private const string FrameworkNewScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            public void OnStart(IMapContext context) { context.Log("ok"); }
            public void OnTick(MapTick tick) { }
            public void OnStop() { }
            public void Report() { _ = new System.InvalidOperationException("x"); }
        }
        """;

    private static void HostInterfaceRejectsFrameworkNew()
    {
        using var temp = new TempDirectory();
        var output = Path.Combine(temp.Path, "package");
        var error = Check.Throws<InvalidDataException>(() => PackageBuilder.Compile("HostFrameworkNew", "GameScript",
            [new("GameScript.cs", FrameworkNewScript)], Profile(), output,
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]));
        Check.Assert(error.Message.Contains("Report", StringComparison.Ordinal), error.Message);
        Check.Assert(error.Message.Contains("InvalidOperationException..ctor", StringComparison.Ordinal), error.Message);
        Check.Assert(!Directory.Exists(output), "A rejected framework constructor published a package.");
    }

    private static void HostInterfaceConstructsPrivateType()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "input"), "SharedBox", """
            public sealed class Box
            {
                private readonly int value;
                public Box(int value) { this.value = value; }
                public int Get() => value;
            }
            """);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
                public int Measure(int value) => new Box(value).Get();
            }
            """;
        var build = PackageBuilder.Compile("HostPrivateBox", "GameScript", [new("GameScript.cs", script)], Profile(),
            Path.Combine(temp.Path, "package"), [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(build.ManifestPath!, typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 41);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsIl()
    {
        using var temp = new TempDirectory();
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
                public int Measure(int value) => value + 1;
            }
            """;
        var compiled = SourceCompiler.Compile("HostImport", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImport.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImport", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 40);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsHostMeasure()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostImportMeasure", [new("GameScript.cs", HostMeasureScript)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportMeasure.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportMeasure", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "Charge"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 40);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Charged == 40, "Charge received " + host.Charged + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsIntOnly()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostImportInt", [new("GameScript.cs", IntOnlyScript)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportInt.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportInt", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "Charge"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Invoke("Apply", 41);
        session.Dispose();
        Check.Assert(host.Charged == 41, "Charge received " + host.Charged + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsHostAndInt()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostImportReport", [new("GameScript.cs", HostAndIntScript)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportReport.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportReport", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "Charge"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Invoke("Report", 41);
        session.Dispose();
        Check.Assert(host.Charged == 41, "Charge received " + host.Charged + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsLaterCallback()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostImportLater", [new("GameScript.cs", LaterSessionScript)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportLater.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportLater", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Invoke("OnStop");
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["ok", "stopped"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsAuthorType()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostImportBox", [new("GameScript.cs", AuthorTypeScript)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportBox.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportBox", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 41);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsPrivateType()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "input"), "SharedImportBox", """
            public sealed class Box
            {
                private readonly int value;
                public Box(int value) { this.value = value; }
                public int Get() => value;
            }
            """);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
                public int Measure(int value) => new Box(value).Get();
            }
            """;
        var compiled = SourceCompiler.Compile("HostImportPrivateBox", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, helper]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportPrivateBox.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportPrivateBox", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 41);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsPrivateChain()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedImportSecond", """
            public static class Second { public static int AddOne(int value) => value + 1; }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedImportFirst", """
            public static class First { public static int Through(int value) => Second.AddOne(value); }
            """, [second]);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
                public int Measure(int value) => First.Through(value);
            }
            """;
        var compiled = SourceCompiler.Compile("HostImportChain", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, first]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportChain.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportChain", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            [first, second], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 40);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsOnStart()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostImportStart", [new("GameScript.cs", HostFieldScript)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportStart.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportStart", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "SpawnEntity"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
        Check.Assert(host.Spawned == "fixture", host.Spawned ?? "no entity");
    }

    private static void HostInterfaceImportsOnStartCharge()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostImportCharge", [new("GameScript.cs", OnStartChargeScript)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportCharge.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportCharge", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "Charge"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Charged == 7, "Charge received " + host.Charged + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsOnStartDestroy()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostImportDestroy", [new("GameScript.cs", OnStartDestroyScript)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportDestroy.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportDestroy", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "SpawnEntity", "DestroyEntity"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Spawned == "fixture", host.Spawned ?? "no entity");
        Check.Assert(host.Destroyed == new EntityId(1), "Destroy received " + host.Destroyed + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsOnStartMapId()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostImportMapId", [new("GameScript.cs", OnStartMapIdScript)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportMapId.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportMapId", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "get_MapId"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["fixture"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsStoredEntity()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostImportRelease", [new("GameScript.cs", StoredEntityScript)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportRelease.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportRelease", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "SpawnEntity", "DestroyEntity"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Invoke("Release");
        session.Dispose();
        Check.Assert(host.Spawned == "fixture", host.Spawned ?? "no entity");
        Check.Assert(host.Destroyed == new EntityId(1), "Destroy received " + host.Destroyed + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsPrivateMapId()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "input"), "SharedImportMap", """
            using RuneCLR;
            public static class SharedMap { public static string Id(IMapContext context) => context.MapId; }
            """);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log(SharedMap.Id(context)); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var compiled = SourceCompiler.Compile("HostImportPrivateMap", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, helper]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportPrivateMap.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportPrivateMap", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "get_MapId"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["fixture"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsPrivateCharge()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "input"), "SharedImportBill", """
            using RuneCLR;
            public static class SharedBill { public static void Bill(IMapContext context) => context.Charge(7); }
            """);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); SharedBill.Bill(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var compiled = SourceCompiler.Compile("HostImportPrivateCharge", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, helper]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportPrivateCharge.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportPrivateCharge", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "Charge"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Charged == 7, "Charge received " + host.Charged + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsPrivateSpawn()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "input"), "SharedImportSpawn", """
            using RuneCLR;
            public static class SharedSpawn { public static EntityId Create(IMapContext context) => context.SpawnEntity("fixture"); }
            """);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context)
                {
                    context.Log("ok");
                    var id = SharedSpawn.Create(context);
                    context.DestroyEntity(id);
                }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var compiled = SourceCompiler.Compile("HostImportPrivateSpawn", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, helper]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportPrivateSpawn.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportPrivateSpawn", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "SpawnEntity", "DestroyEntity"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Spawned == "fixture", host.Spawned ?? "no entity");
        Check.Assert(host.Destroyed == new EntityId(1), "Destroy received " + host.Destroyed + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsPrivateDestroy()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "input"), "SharedImportLife", """
            using RuneCLR;
            public static class SharedLife
            {
                public static void Cycle(IMapContext context)
                {
                    var id = context.SpawnEntity("fixture");
                    context.DestroyEntity(id);
                }
            }
            """);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); SharedLife.Cycle(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var compiled = SourceCompiler.Compile("HostImportPrivateLife", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, helper]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportPrivateLife.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportPrivateLife", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "SpawnEntity", "DestroyEntity"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Spawned == "fixture", host.Spawned ?? "no entity");
        Check.Assert(host.Destroyed == new EntityId(1), "Destroy received " + host.Destroyed + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsPrivateLog()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "input"), "SharedImportNote", """
            using RuneCLR;
            public static class SharedNote { public static void Note(IMapContext context) => context.Log("from-private"); }
            """);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); SharedNote.Note(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var compiled = SourceCompiler.Compile("HostImportPrivateLog", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, helper]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportPrivateLog.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportPrivateLog", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["ok", "from-private"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsPrivateChainLogs()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedImportLogSecond", """
            using RuneCLR;
            public static class Second { public static void Note(IMapContext context) => context.Log("from-second"); }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedImportLogFirst", """
            using RuneCLR;
            public static class First { public static void Through(IMapContext context) => Second.Note(context); }
            """, [second]);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); First.Through(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var compiled = SourceCompiler.Compile("HostImportChainLog", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, first]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportChainLog.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportChainLog", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            [first, second], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["ok", "from-second"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsPrivateChainRejectsSpawn()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedImportSpawnSecond", """
            using RuneCLR;
            public static class Second { public static void Note(IMapContext context) => context.SpawnEntity("nope"); }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedImportSpawnFirst", """
            using RuneCLR;
            public static class First { public static void Through(IMapContext context) => Second.Note(context); }
            """, [second]);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); First.Through(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var compiled = SourceCompiler.Compile("HostImportChainSpawn", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, first]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportChainSpawn.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var output = Path.Combine(temp.Path, "package");
        var error = Check.Throws<InvalidDataException>(() => PackageBuilder.Import("HostImportChainSpawn", "GameScript", dll, Profile(), output,
            [first, second], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]));
        Check.Assert(error.Message.Contains("OnStart", StringComparison.Ordinal), error.Message);
        Check.Assert(error.Message.Contains("SpawnEntity", StringComparison.Ordinal), error.Message);
        Check.Assert(!Directory.Exists(output), "An unlisted private spawn published a package.");
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");
    }

    private static void HostInterfaceImportsPrivateChainReadsMapId()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedImportIdSecond", """
            using RuneCLR;
            public static class Second { public static string Id(IMapContext context) => context.MapId; }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedImportIdFirst", """
            using RuneCLR;
            public static class First { public static string Through(IMapContext context) => Second.Id(context); }
            """, [second]);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log(First.Through(context)); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var compiled = SourceCompiler.Compile("HostImportChainMap", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, first]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportChainMap.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportChainMap", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            [first, second], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "get_MapId"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["fixture"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsPrivateChainCharges()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedImportBillSecond", """
            using RuneCLR;
            public static class Second { public static void Bill(IMapContext context) => context.Charge(7); }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedImportBillFirst", """
            using RuneCLR;
            public static class First { public static void Through(IMapContext context) => Second.Bill(context); }
            """, [second]);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); First.Through(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var compiled = SourceCompiler.Compile("HostImportChainCharge", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, first]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportChainCharge.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportChainCharge", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            [first, second], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "Charge"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Charged == 7, "Charge received " + host.Charged + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsPrivateChainDestroys()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedImportLifeSecond", """
            using RuneCLR;
            public static class Second
            {
                public static void Cycle(IMapContext context)
                {
                    var id = context.SpawnEntity("fixture");
                    context.DestroyEntity(id);
                }
            }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedImportLifeFirst", """
            using RuneCLR;
            public static class First { public static void Through(IMapContext context) => Second.Cycle(context); }
            """, [second]);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); First.Through(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var compiled = SourceCompiler.Compile("HostImportChainLife", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, first]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportChainLife.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportChainLife", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            [first, second], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "SpawnEntity", "DestroyEntity"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Spawned == "fixture", host.Spawned ?? "no entity");
        Check.Assert(host.Destroyed == new EntityId(1), "Destroy received " + host.Destroyed + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsPrivateChainReturnsEntity()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedImportReturnSecond", """
            using RuneCLR;
            public static class Second { public static EntityId Create(IMapContext context) => context.SpawnEntity("fixture"); }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedImportReturnFirst", """
            using RuneCLR;
            public static class First { public static EntityId Through(IMapContext context) => Second.Create(context); }
            """, [second]);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context)
                {
                    context.Log("ok");
                    var id = First.Through(context);
                    context.DestroyEntity(id);
                }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var compiled = SourceCompiler.Compile("HostImportChainReturn", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, first]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportChainReturn.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportChainReturn", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            [first, second], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log", "SpawnEntity", "DestroyEntity"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Spawned == "fixture", host.Spawned ?? "no entity");
        Check.Assert(host.Destroyed == new EntityId(1), "Destroy received " + host.Destroyed + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportsPrivate()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "input"), "SharedImport", """
            public static class SharedHelper { public static int AddOne(int value) => value + 1; }
            """);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
                public int Measure(int value) => SharedHelper.AddOne(value);
            }
            """;
        var compiled = SourceCompiler.Compile("HostImportPrivate", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, helper]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportPrivate.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportPrivate", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 40);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceImportRejectsFrameworkNew()
    {
        using var temp = new TempDirectory();
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
                public void Report() { _ = new System.InvalidOperationException("x"); }
            }
            """;
        var compiled = SourceCompiler.Compile("HostImportFramework", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportFramework.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var output = Path.Combine(temp.Path, "package");
        var error = Check.Throws<InvalidDataException>(() => PackageBuilder.Import("HostImportFramework", "GameScript", dll, Profile(), output,
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]));
        Check.Assert(error.Message.Contains("Report", StringComparison.Ordinal), error.Message);
        Check.Assert(error.Message.Contains("InvalidOperationException..ctor", StringComparison.Ordinal), error.Message);
        Check.Assert(!Directory.Exists(output), "A rejected framework constructor published a package.");
    }

    private static void HostInterfaceImportPrivateCallsEntry()
    {
        using var temp = new TempDirectory();
        var stub = EmitDependency(Path.Combine(temp.Path, "stub"), "HostImportReturn", """
            [assembly: System.Reflection.AssemblyVersion("1.0.0.0")]
            public sealed class GameScript { public static int FromEntry(int value) => value + 1; }
            """);
        var helper = EmitDependency(Path.Combine(temp.Path, "helper"), "SharedImportReturn", """
            [assembly: System.Reflection.AssemblyVersion("1.0.0.0")]
            public static class Helper { public static int Through(int value) => GameScript.FromEntry(value); }
            """, [stub]);
        const string script = """
            using RuneCLR;
            [assembly: System.Reflection.AssemblyVersion("1.0.0.0")]
            public sealed class GameScript : IMapScript
            {
                public static int FromEntry(int value) => value + 1;
                public void OnStart(IMapContext context) { context.Log("ok"); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
                public int Measure(int value) => Helper.Through(value);
            }
            """;
        var compiled = SourceCompiler.Compile("HostImportReturn", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, helper]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostImportReturn.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var imported = PackageBuilder.Import("HostImportReturn", "GameScript", dll, Profile(), Path.Combine(temp.Path, "package"),
            [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(imported.Succeeded, string.Join("; ", imported.Diagnostics.Select(item => item.Message)));
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(imported.ManifestPath!, typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 40);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }


    private static void HostInterfaceOperatorCli()
    {
        using var temp = new TempDirectory();
        var source = Path.Combine(temp.Path, "source");
        Directory.CreateDirectory(source);
        File.WriteAllText(Path.Combine(source, "GameScript.cs"), IntSessionScript);
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "compile",
            "--source", source,
            "--id", "HostCli",
            "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory,
            "--contract", Fixtures.ContractAssembly,
            "--output", output,
            "--host-interface", "RuneCLR.IMapContext",
            "--allowed-method", "Log");
        Check.Assert(exit == 0 && stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + exit + ". " + stdout + stderr);
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(Path.Combine(output, "package.json"), typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 40);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceOperatorCliRejectsFrameworkNew()
    {
        using var temp = new TempDirectory();
        var source = Path.Combine(temp.Path, "source");
        Directory.CreateDirectory(source);
        File.WriteAllText(Path.Combine(source, "GameScript.cs"), FrameworkNewScript);
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "compile",
            "--source", source,
            "--id", "HostCliFramework",
            "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory,
            "--contract", Fixtures.ContractAssembly,
            "--output", output,
            "--host-interface", "RuneCLR.IMapContext",
            "--allowed-method", "Log");
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("Report", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("InvalidOperationException..ctor", StringComparison.Ordinal), stderr);
        Check.Assert(!Directory.Exists(output), "A rejected framework constructor published a package.");
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");
    }

    private static void HostInterfaceOperatorCliImportsIl()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostCliImport", [new("GameScript.cs", IntSessionScript)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostCliImport.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "import",
            "--assembly", dll,
            "--id", "HostCliImport",
            "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory,
            "--contract", Fixtures.ContractAssembly,
            "--output", output,
            "--host-interface", "RuneCLR.IMapContext",
            "--allowed-method", "Log");
        Check.Assert(exit == 0 && stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + exit + ". " + stdout + stderr);
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(Path.Combine(output, "package.json"), typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 40);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceOperatorCliImportRejectsFrameworkNew()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostCliImportFramework", [new("GameScript.cs", FrameworkNewScript)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostCliImportFramework.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "import",
            "--assembly", dll,
            "--id", "HostCliImportFramework",
            "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory,
            "--contract", Fixtures.ContractAssembly,
            "--output", output,
            "--host-interface", "RuneCLR.IMapContext",
            "--allowed-method", "Log");
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("Report", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("InvalidOperationException..ctor", StringComparison.Ordinal), stderr);
        Check.Assert(!Directory.Exists(output), "A rejected framework constructor published a package.");
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");
    }

    private static void HostInterfaceOperatorCliCompilesDependency()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "input"), "SharedLibrary", """
            public static class SharedHelper { public static int AddOne(int value) => value + 1; }
            """);
        var source = Path.Combine(temp.Path, "source");
        Directory.CreateDirectory(source);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
                public int Measure(int value) => SharedHelper.AddOne(value);
            }
            """;
        File.WriteAllText(Path.Combine(source, "GameScript.cs"), script);
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "compile",
            "--source", source,
            "--id", "HostCliPrivate",
            "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory,
            "--contract", Fixtures.ContractAssembly,
            "--output", output,
            "--dependency", helper,
            "--host-interface", "RuneCLR.IMapContext",
            "--allowed-method", "Log");
        Check.Assert(exit == 0 && stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + exit + ". " + stdout + stderr);
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(Path.Combine(output, "package.json"), typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 40);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceOperatorCliImportsDependency()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "input"), "SharedCliImport", """
            public static class SharedHelper { public static int AddOne(int value) => value + 1; }
            """);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
                public int Measure(int value) => SharedHelper.AddOne(value);
            }
            """;
        var compiled = SourceCompiler.Compile("HostCliImportPrivate", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, helper]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostCliImportPrivate.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "import",
            "--assembly", dll,
            "--id", "HostCliImportPrivate",
            "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory,
            "--contract", Fixtures.ContractAssembly,
            "--output", output,
            "--dependency", helper,
            "--host-interface", "RuneCLR.IMapContext",
            "--allowed-method", "Log");
        Check.Assert(exit == 0 && stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + exit + ". " + stdout + stderr);
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(Path.Combine(output, "package.json"), typeof(IMapContext), host);
        var result = session.InvokeInt("Measure", 40);
        session.Dispose();
        Check.Assert(result == 41, "Measure returned " + result + ".");
        Check.Assert(host.Logs.SequenceEqual(["ok"]), string.Join(", ", host.Logs));
    }

    private static void HostInterfaceOperatorCliValidates()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliValidate", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 0 && stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stdout.Contains("\"id\":\"HostCliValidate\"", StringComparison.Ordinal), stdout);
        Check.Assert(stdout.Contains("\"contentSha256\":\"" + manifest.ContentSha256 + "\"", StringComparison.Ordinal), stdout);
    }

    private static void HostInterfaceOperatorCliRejectsTamperedManifest()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliSeal", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var manifestPath = build.ManifestPath!;
        var json = File.ReadAllText(manifestPath);
        var changed = json.Replace("\"id\":\"HostCliSeal\"", "\"id\":\"HostCliTampered\"", StringComparison.Ordinal);
        Check.Assert(changed != json, "Package id was not found.");
        File.WriteAllText(manifestPath, changed);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", manifestPath);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("content identity", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(Directory.Exists(Path.GetDirectoryName(manifestPath)), "Validate removed the package directory.");
    }

    private static void HostInterfaceOperatorCliRejectsChangedFile()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliBytes", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        var entryPath = Path.Combine(Path.GetDirectoryName(build.ManifestPath!)!, manifest.EntryAssembly);
        var bytes = File.ReadAllBytes(entryPath);
        bytes[^1] ^= 0xFF;
        File.WriteAllBytes(entryPath, bytes);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("hash mismatch", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains(manifest.EntryAssembly, StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(Directory.Exists(Path.GetDirectoryName(build.ManifestPath!)), "Validate removed the package directory.");
    }

    private static void HostInterfaceOperatorCliRejectsExtraFile()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliExtra", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var packageDirectory = Path.GetDirectoryName(build.ManifestPath!)!;
        var extra = Path.Combine(packageDirectory, "note.txt");
        File.WriteAllText(extra, "extra");
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("missing or extra files", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(extra), "Validate removed the extra file.");
    }

    private static void HostInterfaceOperatorCliRejectsPartialPair()
    {
        using var temp = new TempDirectory();
        var source = Path.Combine(temp.Path, "source");
        Directory.CreateDirectory(source);
        File.WriteAllText(Path.Combine(source, "GameScript.cs"), IntSessionScript);
        Reject(Path.Combine(temp.Path, "interface-only"), hostInterface: true);
        Reject(Path.Combine(temp.Path, "method-only"), hostInterface: false);
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");

        void Reject(string output, bool hostInterface)
        {
            var arguments = new List<string>
            {
                "compile", "--source", source, "--id", "HostCliPair", "--entry-type", "GameScript",
                "--framework-refs", Fixtures.FrameworkReferenceDirectory, "--contract", Fixtures.ContractAssembly, "--output", output,
            };
            if (hostInterface) arguments.AddRange(["--host-interface", "RuneCLR.IMapContext"]);
            else arguments.AddRange(["--allowed-method", "Log"]);
            var (exit, stdout, stderr) = RunPackageTool(arguments.ToArray());
            Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
            Check.Assert(stderr.Contains("must both be present", StringComparison.Ordinal), stderr);
            Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
            Check.Assert(!Directory.Exists(output), "A partial host-contract pair published a package.");
        }
    }

    private static void OperatorCliRejectsBadArguments()
    {
        var help = RunPackageTool("--help");
        Check.Assert(help.ExitCode == 0, "Help exited " + help.ExitCode + ". " + help.Stdout + help.Stderr);
        Check.Assert(help.Stdout.Contains("--host-interface", StringComparison.Ordinal), help.Stdout);
        var unknown = RunPackageTool("pack");
        Check.Assert(unknown.ExitCode == 2 && unknown.Stderr.Contains("Unknown command", StringComparison.Ordinal), unknown.Stdout + unknown.Stderr);
        Check.Assert(unknown.Stderr.Contains("\"success\":false", StringComparison.Ordinal), unknown.Stderr);
        var missing = RunPackageTool("compile");
        Check.Assert(missing.ExitCode == 2 && missing.Stderr.Contains("Missing --framework-refs.", StringComparison.Ordinal), missing.Stdout + missing.Stderr);
        var duplicate = RunPackageTool("compile", "--id", "A", "--id", "B");
        Check.Assert(duplicate.ExitCode == 2 && duplicate.Stderr.Contains("supplied more than once", StringComparison.Ordinal), duplicate.Stdout + duplicate.Stderr);
    }

    private static void OperatorCliRejectsRepeatedAllowedMethod()
    {
        using var temp = new TempDirectory();
        var source = Path.Combine(temp.Path, "source");
        Directory.CreateDirectory(source);
        File.WriteAllText(Path.Combine(source, "GameScript.cs"), IntSessionScript);
        Reject(Path.Combine(temp.Path, "repeated"), ["--allowed-method", "Log", "--allowed-method", "Log"]);
        Reject(Path.Combine(temp.Path, "blank"), ["--allowed-method", ""]);
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");

        void Reject(string output, string[] methods)
        {
            var arguments = new List<string>
            {
                "compile", "--source", source, "--id", "HostCliDup", "--entry-type", "GameScript",
                "--framework-refs", Fixtures.FrameworkReferenceDirectory, "--contract", Fixtures.ContractAssembly,
                "--output", output, "--host-interface", "RuneCLR.IMapContext",
            };
            arguments.AddRange(methods);
            var (exit, stdout, stderr) = RunPackageTool(arguments.ToArray());
            Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
            Check.Assert(stderr.Contains("nonempty and unique", StringComparison.Ordinal), stderr);
            Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
            Check.Assert(!Directory.Exists(output), "A repeated or blank allowed method published a package.");
        }
    }

    private static void OperatorCliRejectsNonSourceFile()
    {
        using var temp = new TempDirectory();
        var source = Path.Combine(temp.Path, "source");
        Directory.CreateDirectory(source);
        File.WriteAllText(Path.Combine(source, "GameScript.cs"), IntSessionScript);
        File.WriteAllText(Path.Combine(source, "GameScript.csproj"), "<Project />");
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "compile", "--source", source, "--id", "HostCliSource", "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory, "--contract", Fixtures.ContractAssembly,
            "--output", output, "--host-interface", "RuneCLR.IMapContext", "--allowed-method", "Log");
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("only regular .cs files", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(!Directory.Exists(output), "A non-source file published a package.");
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");
    }

    private static void OperatorCliRejectsDeepSource()
    {
        using var temp = new TempDirectory();
        var source = Path.Combine(temp.Path, "source");
        var deep = source;
        for (var level = 0; level < 17; level++) deep = Path.Combine(deep, "n");
        Directory.CreateDirectory(deep);
        File.WriteAllText(Path.Combine(deep, "GameScript.cs"), IntSessionScript);
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "compile", "--source", source, "--id", "HostCliDeep", "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory, "--contract", Fixtures.ContractAssembly,
            "--output", output, "--host-interface", "RuneCLR.IMapContext", "--allowed-method", "Log");
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("nesting limit", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(!Directory.Exists(output), "A deeply nested source published a package.");
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");
    }

    private static void OperatorCliRejectsSourceLink()
    {
        using var temp = new TempDirectory();
        var real = Path.Combine(temp.Path, "real");
        Directory.CreateDirectory(real);
        File.WriteAllText(Path.Combine(real, "GameScript.cs"), IntSessionScript);
        var linked = Path.Combine(temp.Path, "linked");
        Directory.CreateSymbolicLink(linked, real);
        var child = Path.Combine(temp.Path, "child");
        Directory.CreateDirectory(child);
        File.WriteAllText(Path.Combine(child, "GameScript.cs"), IntSessionScript);
        Directory.CreateDirectory(Path.Combine(temp.Path, "target"));
        Directory.CreateSymbolicLink(Path.Combine(child, "link"), Path.Combine(temp.Path, "target"));
        Reject(linked);
        Reject(child);
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");

        void Reject(string source)
        {
            var output = Path.Combine(temp.Path, "package-" + Path.GetFileName(source));
            var (exit, stdout, stderr) = RunPackageTool(
                "compile", "--source", source, "--id", "HostCliLink", "--entry-type", "GameScript",
                "--framework-refs", Fixtures.FrameworkReferenceDirectory, "--contract", Fixtures.ContractAssembly,
                "--output", output, "--host-interface", "RuneCLR.IMapContext", "--allowed-method", "Log");
            Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
            Check.Assert(stderr.Contains("filesystem links", StringComparison.Ordinal), stderr);
            Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
            Check.Assert(!Directory.Exists(output), "A linked source published a package.");
        }
    }

    private static void OperatorCliRejectsSourceLimit()
    {
        using var temp = new TempDirectory();
        var many = Path.Combine(temp.Path, "many");
        Directory.CreateDirectory(many);
        for (var index = 0; index < 65; index++)
            File.WriteAllText(Path.Combine(many, "f" + index.ToString("00") + ".cs"), "class A { }\n");
        var huge = Path.Combine(temp.Path, "huge");
        Directory.CreateDirectory(huge);
        File.WriteAllBytes(Path.Combine(huge, "GameScript.cs"), new byte[8_000_001]);
        Reject(many);
        Reject(huge);
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");

        void Reject(string source)
        {
            var output = Path.Combine(temp.Path, "package-" + Path.GetFileName(source));
            var (exit, stdout, stderr) = RunPackageTool(
                "compile", "--source", source, "--id", "HostCliLimit", "--entry-type", "GameScript",
                "--framework-refs", Fixtures.FrameworkReferenceDirectory, "--contract", Fixtures.ContractAssembly,
                "--output", output, "--host-interface", "RuneCLR.IMapContext", "--allowed-method", "Log");
            Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
            Check.Assert(stderr.Contains("compiler input limits", StringComparison.Ordinal), stderr);
            Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
            Check.Assert(!Directory.Exists(output), "An oversized source directory published a package.");
        }
    }

    private static void OperatorCliRejectsUnknownOption()
    {
        Reject(RunPackageTool("compile", "--bogus", "value"));
        Reject(RunPackageTool("compile", "--id"));
        Reject(RunPackageTool("compile", "--id", "--entry-type"));

        static void Reject((int ExitCode, string Stdout, string Stderr) result)
        {
            Check.Assert(result.ExitCode == 2, "Package tool exited " + result.ExitCode + ". " + result.Stdout + result.Stderr);
            Check.Assert(result.Stderr.Contains("Unknown option or missing value", StringComparison.Ordinal), result.Stderr);
            Check.Assert(result.Stderr.Contains("\"success\":false", StringComparison.Ordinal), result.Stderr);
        }
    }

    private static void OperatorCliRejectsCompileError()
    {
        using var temp = new TempDirectory();
        var source = Path.Combine(temp.Path, "source");
        Directory.CreateDirectory(source);
        File.WriteAllText(Path.Combine(source, "Broken.cs"), "public class Broken { MissingType value; }\n");
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "compile", "--source", source, "--id", "HostCliDiag", "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory, "--contract", Fixtures.ContractAssembly,
            "--output", output, "--host-interface", "RuneCLR.IMapContext", "--allowed-method", "Log");
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stdout.Contains("\"success\":false", StringComparison.Ordinal), stdout + stderr);
        Check.Assert(stdout.Contains("CS0246", StringComparison.Ordinal), stdout + stderr);
        Check.Assert(stdout.Contains("MissingType", StringComparison.Ordinal), stdout + stderr);
        Check.Assert(!Directory.Exists(output), "A compiler error published a package.");
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");
    }

    private static void OperatorCliRejectsBadImport()
    {
        using var temp = new TempDirectory();
        var assembly = Path.Combine(temp.Path, "NotAnAssembly.dll");
        File.WriteAllText(assembly, "not a pe image\n");
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "import", "--assembly", assembly, "--id", "HostCliBad", "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory, "--contract", Fixtures.ContractAssembly,
            "--output", output, "--host-interface", "RuneCLR.IMapContext", "--allowed-method", "Log");
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("Malformed managed assembly", StringComparison.Ordinal), stdout + stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(!Directory.Exists(output), "A bad import published a package.");
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");
    }

    private static void OperatorCliRejectsMissingEntry()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostCliMissingEntry", [new("Other.cs", "public sealed class OtherScript { }\n")],
            CompilerFixture.ApprovedReferences().ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var assembly = Path.Combine(temp.Path, "HostCliMissingEntry.dll");
        File.WriteAllBytes(assembly, compiled.Assembly!);
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "import", "--assembly", assembly, "--id", "HostCliMissingEntry", "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory, "--contract", Fixtures.ContractAssembly,
            "--output", output, "--host-interface", "RuneCLR.IMapContext", "--allowed-method", "Log");
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("GameScript", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("was not found", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(!Directory.Exists(output), "A missing entry type published a package.");
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");
    }

    private static void OperatorCliReadsMapId()
    {
        using var temp = new TempDirectory();
        var source = Path.Combine(temp.Path, "source");
        Directory.CreateDirectory(source);
        File.WriteAllText(Path.Combine(source, "GameScript.cs"), OnStartMapIdScript);
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "compile", "--source", source, "--id", "HostCliMap", "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory, "--contract", Fixtures.ContractAssembly,
            "--output", output, "--host-interface", "RuneCLR.IMapContext",
            "--allowed-method", "Log", "--allowed-method", "get_MapId");
        Check.Assert(exit == 0 && stdout.Contains("\"success\":true", StringComparison.Ordinal), "Package tool exited " + exit + ". " + stdout + stderr);
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(Path.Combine(output, "package.json"), typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["fixture"]), string.Join(", ", host.Logs));
    }

    private static void OperatorCliImportsMapId()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostCliImportMap", [new("GameScript.cs", OnStartMapIdScript)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostCliImportMap.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "import", "--assembly", dll, "--id", "HostCliImportMap", "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory, "--contract", Fixtures.ContractAssembly,
            "--output", output, "--host-interface", "RuneCLR.IMapContext",
            "--allowed-method", "Log", "--allowed-method", "get_MapId");
        Check.Assert(exit == 0 && stdout.Contains("\"success\":true", StringComparison.Ordinal), "Package tool exited " + exit + ". " + stdout + stderr);
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(Path.Combine(output, "package.json"), typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["fixture"]), string.Join(", ", host.Logs));
    }

    private static void OperatorCliRejectsMapIdName()
    {
        using var temp = new TempDirectory();
        var source = Path.Combine(temp.Path, "source");
        Directory.CreateDirectory(source);
        File.WriteAllText(Path.Combine(source, "GameScript.cs"), OnStartMapIdScript);
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "compile", "--source", source, "--id", "HostCliMapName", "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory, "--contract", Fixtures.ContractAssembly,
            "--output", output, "--host-interface", "RuneCLR.IMapContext",
            "--allowed-method", "Log", "--allowed-method", "MapId");
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("get_MapId", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("OnStart", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(!Directory.Exists(output), "A property-name allow list published a package.");
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");
    }

    private static void OperatorCliImportRejectsMapIdName()
    {
        using var temp = new TempDirectory();
        var compiled = SourceCompiler.Compile("HostCliImportMapName", [new("GameScript.cs", OnStartMapIdScript)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostCliImportMapName.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "import", "--assembly", dll, "--id", "HostCliImportMapName", "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory, "--contract", Fixtures.ContractAssembly,
            "--output", output, "--host-interface", "RuneCLR.IMapContext",
            "--allowed-method", "Log", "--allowed-method", "MapId");
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("get_MapId", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("OnStart", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(!Directory.Exists(output), "A property-name allow list published a package.");
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");
    }

    private static void OperatorCliCompilesTwoDependencies()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedCliLogSecond", """
            using RuneCLR;
            public static class Second { public static void Note(IMapContext context) => context.Log("from-second"); }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedCliLogFirst", """
            using RuneCLR;
            public static class First { public static void Through(IMapContext context) => Second.Note(context); }
            """, [second]);
        var source = Path.Combine(temp.Path, "source");
        Directory.CreateDirectory(source);
        File.WriteAllText(Path.Combine(source, "GameScript.cs"), """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); First.Through(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """);
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "compile", "--source", source, "--id", "HostCliChain", "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory, "--contract", Fixtures.ContractAssembly,
            "--output", output, "--dependency", first, "--dependency", second,
            "--host-interface", "RuneCLR.IMapContext", "--allowed-method", "Log");
        Check.Assert(exit == 0 && stdout.Contains("\"success\":true", StringComparison.Ordinal), "Package tool exited " + exit + ". " + stdout + stderr);
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(Path.Combine(output, "package.json"), typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["ok", "from-second"]), string.Join(", ", host.Logs));
    }

    private static void OperatorCliImportsTwoDependencies()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedCliImportLogSecond", """
            using RuneCLR;
            public static class Second { public static void Note(IMapContext context) => context.Log("from-second"); }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedCliImportLogFirst", """
            using RuneCLR;
            public static class First { public static void Through(IMapContext context) => Second.Note(context); }
            """, [second]);
        const string script = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); First.Through(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var compiled = SourceCompiler.Compile("HostCliImportChain", [new("GameScript.cs", script)],
            CompilerFixture.ApprovedReferences().Concat([Fixtures.ContractAssembly, first]).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var dll = Path.Combine(temp.Path, "HostCliImportChain.dll");
        File.WriteAllBytes(dll, compiled.Assembly!);
        var output = Path.Combine(temp.Path, "package");
        var (exit, stdout, stderr) = RunPackageTool(
            "import", "--assembly", dll, "--id", "HostCliImportChain", "--entry-type", "GameScript",
            "--framework-refs", Fixtures.FrameworkReferenceDirectory, "--contract", Fixtures.ContractAssembly,
            "--output", output, "--dependency", first, "--dependency", second,
            "--host-interface", "RuneCLR.IMapContext", "--allowed-method", "Log");
        Check.Assert(exit == 0 && stdout.Contains("\"success\":true", StringComparison.Ordinal), "Package tool exited " + exit + ". " + stdout + stderr);
        var host = new RecordingMapContext();
        var session = HostContractSession.Open(Path.Combine(output, "package.json"), typeof(IMapContext), host);
        session.Dispose();
        Check.Assert(host.Logs.SequenceEqual(["ok", "from-second"]), string.Join(", ", host.Logs));
    }

    private static void OperatorCliRejectsChangedDependency()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedCliSealSecond", """
            using RuneCLR;
            public static class Second { public static void Note(IMapContext context) => context.Log("from-second"); }
            """);
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedCliSealFirst", """
            using RuneCLR;
            public static class First { public static void Through(IMapContext context) => Second.Note(context); }
            """, [second]);
        var build = PackageBuilder.Compile("HostCliSealDeps", "GameScript", [new("GameScript.cs", """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); First.Through(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """)], Profile(), Path.Combine(temp.Path, "package"), [first, second],
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        var relative = manifest.Dependencies.Single(item => item.Path.Contains("SharedCliSealSecond", StringComparison.Ordinal)).Path;
        var dependencyPath = Path.Combine(Path.GetDirectoryName(build.ManifestPath!)!, relative.Replace('/', Path.DirectorySeparatorChar));
        var bytes = File.ReadAllBytes(dependencyPath);
        bytes[^1] ^= 0xFF;
        File.WriteAllBytes(dependencyPath, bytes);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("hash mismatch", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains(relative, StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(dependencyPath), "Validate removed the changed dependency.");
    }


    private static void OperatorCliRejectsDependencyIdentity()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "helper"), "SharedCliIdentity", """
            using RuneCLR;
            public static class Helper { public static void Note(IMapContext context) => context.Log("from-helper"); }
            """);
        var build = PackageBuilder.Compile("HostCliIdentity", "GameScript", [new("GameScript.cs", """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log("ok"); Helper.Note(context); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """)], Profile(), Path.Combine(temp.Path, "package"), [helper],
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        var dependency = manifest.Dependencies.Single();
        manifest = manifest with
        {
            Dependencies = [dependency with { AssemblyName = "SharedCliIdentity, Version=9.0.0.0, Culture=neutral, PublicKeyToken=null" }]
        };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("identity mismatch", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains(dependency.Path, StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        var dependencyPath = Path.Combine(Path.GetDirectoryName(build.ManifestPath!)!, dependency.Path.Replace('/', Path.DirectorySeparatorChar));
        Check.Assert(File.Exists(dependencyPath), "Validate removed the dependency.");
    }


    private static void OperatorCliRejectsPackageLink()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliPkgLink", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        var packageDirectory = Path.GetDirectoryName(build.ManifestPath!)!;
        var entryPath = Path.Combine(packageDirectory, manifest.EntryAssembly);
        var target = Path.Combine(temp.Path, "target.dll");
        File.Move(entryPath, target);
        File.CreateSymbolicLink(entryPath, target);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("filesystem links", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(entryPath), "Validate removed the package link.");
        Check.Assert(File.Exists(target), "Validate removed the link target.");
    }


    private static void OperatorCliRejectsPackageNesting()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliPkgNest", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var packageDirectory = Path.GetDirectoryName(build.ManifestPath!)!;
        var nested = packageDirectory;
        for (var level = 0; level < 17; level++)
        {
            nested = Path.Combine(nested, "n");
            Directory.CreateDirectory(nested);
        }
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("nesting limit", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("Package directories", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(Directory.Exists(nested), "Validate removed the nested directory.");
    }


    private static void OperatorCliRejectsSpoofedEntry()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliSpoof", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var spoof = SourceCompiler.Compile("System.IO", [new("GameScript.cs", IntSessionScript)], CompilerFixture.ApprovedReferences());
        Check.Assert(spoof.Succeeded, string.Join("; ", spoof.Diagnostics.Select(item => item.Message)));
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        var entryPath = Path.Combine(Path.GetDirectoryName(build.ManifestPath!)!, manifest.EntryAssembly);
        File.WriteAllBytes(entryPath, spoof.Assembly!);
        var hash = Fixtures.Hash(spoof.Assembly!);
        manifest = manifest with
        {
            EntrySha256 = hash,
            Files = manifest.Files.Select(file => file.Path == manifest.EntryAssembly ? file with { Sha256 = hash } : file).ToArray()
        };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("spoofs", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("System.IO", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(entryPath), "Validate removed the spoofed entry.");
    }


    private static void OperatorCliRejectsOversizedEntry()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliSize", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        var entryPath = Path.Combine(Path.GetDirectoryName(build.ManifestPath!)!, manifest.EntryAssembly);
        using (var stream = new FileStream(entryPath, FileMode.Open, FileAccess.Write, FileShare.None))
            stream.SetLength(PackageValidator.MaximumAssemblyBytes + 1);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("size limits", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(new FileInfo(entryPath).Length == PackageValidator.MaximumAssemblyBytes + 1, "Validate changed the oversized entry.");
    }


    private static void OperatorCliRejectsPackageFormat()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliFormat", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        manifest = manifest with { FormatVersion = PackageFormat.CurrentVersion + 1 };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("Unsupported package format", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsProducerKind()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliKind", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        manifest = manifest with { Producer = manifest.Producer with { InputKind = "native" } };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("Unsupported producer input kind", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsEmptyProducerReferences()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliRefs", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        manifest = manifest with { Producer = manifest.Producer with { References = [] } };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("Producer references identities are required", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsMissingContractReference()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliContract", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        manifest = manifest with
        {
            Producer = manifest.Producer with
            {
                References = [new InputIdentity("other.dll", new string('d', 64), "Other.Contract, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null")]
            }
        };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("exactly one shared host contract", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsBlankPackageId()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliBlank", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        manifest = manifest with { Id = " " };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("Missing or oversized id", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsBlankProducerTool()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliTool", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        manifest = manifest with { Producer = manifest.Producer with { Tool = " " } };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("Missing or oversized producer.tool", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsEscapingPath()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliEscape", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        manifest = manifest with { EntryAssembly = "../entry.dll" };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("canonical relative DLL", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsDottedPath()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliDot", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        manifest = manifest with { EntryAssembly = "bad./echo.dll" };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("canonical relative DLL", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsNonDllEntry()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliTxt", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        manifest = manifest with { EntryAssembly = "entry.txt" };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("canonical relative DLL", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsUnlistedEntry()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliList", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        manifest = manifest with { Files = [new PackageFile("other.dll", manifest.EntrySha256)] };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("exactly match the entry", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsMismatchedFileHash()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliHash", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        var hash = manifest.EntrySha256.StartsWith('a') ? new string('b', 64) : new string('a', 64);
        manifest = manifest with
        {
            Files = manifest.Files.Select(file => file.Path == manifest.EntryAssembly ? file with { Sha256 = hash } : file).ToArray()
        };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("exactly match the entry", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsEscapingDependency()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "helper"), "SharedCliEscape", """
            public static class Helper { public static int Value() => 1; }
            """);
        var build = PackageBuilder.Compile("HostCliDepPath", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        Check.Assert(manifest.Dependencies.Length == 1, "Expected one private dependency.");
        manifest = manifest with { Dependencies = [manifest.Dependencies[0] with { Path = "../lib.dll" }] };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("canonical relative DLL", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsOpaqueDependency()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "helper"), "SharedCliOpaque", """
            public static class Helper { public static int Value() => 1; }
            """);
        var build = PackageBuilder.Compile("HostCliOpaque", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        var relative = manifest.Dependencies.Single().Path;
        var dependencyPath = Path.Combine(Path.GetDirectoryName(build.ManifestPath!)!, relative.Replace('/', Path.DirectorySeparatorChar));
        byte[] bytes = [1, 2, 3, 4];
        File.WriteAllBytes(dependencyPath, bytes);
        var hash = Fixtures.Hash(bytes);
        manifest = manifest with
        {
            Dependencies = [manifest.Dependencies[0] with { Sha256 = hash }],
            Files = manifest.Files.Select(file => file.Path == relative ? file with { Sha256 = hash } : file).ToArray()
        };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("PE", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(dependencyPath), "Validate removed the opaque dependency.");
    }


    private static void OperatorCliRejectsSpoofedDependency()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "helper"), "SharedCliSpoofDep", """
            public static class Helper { public static int Value() => 1; }
            """);
        var build = PackageBuilder.Compile("HostCliSpoofDep", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var spoof = SourceCompiler.Compile("System.IO", [new("Helper.cs", "public static class Helper { public static int Value() => 1; }")],
            CompilerFixture.ApprovedReferences());
        Check.Assert(spoof.Succeeded, string.Join("; ", spoof.Diagnostics.Select(item => item.Message)));
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        var relative = manifest.Dependencies.Single().Path;
        var dependencyPath = Path.Combine(Path.GetDirectoryName(build.ManifestPath!)!, relative.Replace('/', Path.DirectorySeparatorChar));
        File.WriteAllBytes(dependencyPath, spoof.Assembly!);
        var hash = Fixtures.Hash(spoof.Assembly!);
        var identity = ManagedAssemblyInspector.Inspect(spoof.Assembly!).AssemblyName;
        manifest = manifest with
        {
            Dependencies = [manifest.Dependencies[0] with { Sha256 = hash, AssemblyName = identity }],
            Files = manifest.Files.Select(file => file.Path == relative ? file with { Sha256 = hash } : file).ToArray()
        };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("spoofs", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("System.IO", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(dependencyPath), "Validate removed the spoofed dependency.");
    }


    private static void OperatorCliRejectsDuplicateEntryIdentity()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "helper"), "SharedCliDup", """
            public static class Helper { public static int Value() => 1; }
            """);
        var build = PackageBuilder.Compile("HostCliDup", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var duplicate = SourceCompiler.Compile("HostCliDup", [new("Helper.cs", "public static class Helper { public static int Value() => 2; }")],
            CompilerFixture.ApprovedReferences());
        Check.Assert(duplicate.Succeeded, string.Join("; ", duplicate.Diagnostics.Select(item => item.Message)));
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        var relative = manifest.Dependencies.Single().Path;
        var dependencyPath = Path.Combine(Path.GetDirectoryName(build.ManifestPath!)!, relative.Replace('/', Path.DirectorySeparatorChar));
        File.WriteAllBytes(dependencyPath, duplicate.Assembly!);
        var hash = Fixtures.Hash(duplicate.Assembly!);
        var identity = ManagedAssemblyInspector.Inspect(duplicate.Assembly!).AssemblyName;
        manifest = manifest with
        {
            Dependencies = [manifest.Dependencies[0] with { Sha256 = hash, AssemblyName = identity }],
            Files = manifest.Files.Select(file => file.Path == relative ? file with { Sha256 = hash } : file).ToArray()
        };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("duplicates the entry assembly identity", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(dependencyPath), "Validate removed the duplicate dependency.");
    }


    private static void OperatorCliRejectsContractDependency()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "helper"), "SharedCliContract", """
            public static class Helper { public static int Value() => 1; }
            """);
        var build = PackageBuilder.Compile("HostCliContractDep", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        var declared = new System.Reflection.AssemblyName(
            "RuneCLR.Abstractions, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null").FullName!;
        manifest = manifest with { Dependencies = [manifest.Dependencies.Single() with { AssemblyName = declared }] };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("contract or duplicate private assembly identity", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsDuplicateDependencyIdentity()
    {
        using var temp = new TempDirectory();
        var first = EmitDependency(Path.Combine(temp.Path, "first"), "SharedCliDupA", """
            public static class First { public static int Value() => 1; }
            """);
        var second = EmitDependency(Path.Combine(temp.Path, "second"), "SharedCliDupB", """
            public static class Second { public static int Value() => 2; }
            """);
        var build = PackageBuilder.Compile("HostCliDupDeps", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), [first, second], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        Check.Assert(manifest.Dependencies.Length == 2, "Expected two private dependencies.");
        manifest = manifest with
        {
            Dependencies = [manifest.Dependencies[0], manifest.Dependencies[1] with { AssemblyName = manifest.Dependencies[0].AssemblyName }]
        };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("contract or duplicate private assembly identity", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsMissingDependency()
    {
        using var temp = new TempDirectory();
        var helper = EmitDependency(Path.Combine(temp.Path, "helper"), "SharedCliMissing", """
            public static class Helper { public static int Value() => 1; }
            """);
        var build = PackageBuilder.Compile("HostCliMissing", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), [helper], hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        var relative = manifest.Dependencies.Single().Path;
        var dependencyPath = Path.Combine(Path.GetDirectoryName(build.ManifestPath!)!, relative.Replace('/', Path.DirectorySeparatorChar));
        File.Delete(dependencyPath);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("missing or extra files", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
        Check.Assert(!File.Exists(dependencyPath), "Validate restored the missing dependency.");
    }


    private static void OperatorCliRejectsBlankProducerToolVersion()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliToolVer", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        manifest = manifest with { Producer = manifest.Producer with { ToolVersion = " " } };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("Missing or oversized producer.toolVersion", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsEmptyProducerSources()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliSources", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        manifest = manifest with { Producer = manifest.Producer with { Sources = [] } };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("Producer sources identities are required", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsEmptyProducerCompiler()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliCompiler", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        Check.Assert(manifest.Producer.InputKind == "source", manifest.Producer.InputKind);
        manifest = manifest with { Producer = manifest.Producer with { Compiler = [] } };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("Producer compiler identities are required", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsDuplicateProducerCompiler()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliCompilerDup", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        Check.Assert(manifest.Producer.Compiler.Length > 0, "Expected a producer compiler identity.");
        var compiler = manifest.Producer.Compiler[0];
        manifest = manifest with { Producer = manifest.Producer with { Compiler = [compiler, compiler] } };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("Duplicate producer compiler input name", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static void OperatorCliRejectsDuplicateProducerSource()
    {
        using var temp = new TempDirectory();
        var build = PackageBuilder.Compile("HostCliSourceDup", "GameScript", [new("GameScript.cs", IntSessionScript)], Profile(),
            Path.Combine(temp.Path, "package"), hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        var intact = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(intact.ExitCode == 0 && intact.Stdout.Contains("\"success\":true", StringComparison.Ordinal),
            "Package tool exited " + intact.ExitCode + ". " + intact.Stdout + intact.Stderr);
        var manifest = PackageManifestIO.Read(build.ManifestPath!);
        Check.Assert(manifest.Producer.Sources.Length > 0, "Expected a producer source identity.");
        var source = manifest.Producer.Sources[0];
        manifest = manifest with { Producer = manifest.Producer with { Sources = [source, source] } };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(build.ManifestPath!, manifest);
        var (exit, stdout, stderr) = RunPackageTool("validate", "--manifest", build.ManifestPath!);
        Check.Assert(exit == 2, "Package tool exited " + exit + ". " + stdout + stderr);
        Check.Assert(stderr.Contains("Duplicate producer sources input name", StringComparison.Ordinal), stderr);
        Check.Assert(stderr.Contains("\"success\":false", StringComparison.Ordinal), stderr);
        Check.Assert(File.Exists(build.ManifestPath!), "Validate removed the manifest.");
    }


    private static (int ExitCode, string Stdout, string Stderr) RunPackageTool(params string[] arguments)
    {
        var start = new ProcessStartInfo
        {
            FileName = "dotnet",
            WorkingDirectory = RepositoryRoot(),
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
        };
        start.Environment["DOTNET_NOLOGO"] = "1";
        foreach (var argument in new[] { "run", "--project", "tools/RuneCLR.PackageTool", "-c", BuildConfiguration(), "--no-build", "--" })
            start.ArgumentList.Add(argument);
        foreach (var argument in arguments) start.ArgumentList.Add(argument);
        using var process = Process.Start(start) ?? throw new InvalidOperationException("The package tool did not start.");
        var stdoutTask = process.StandardOutput.ReadToEndAsync();
        var stderrTask = process.StandardError.ReadToEndAsync();
        if (!process.WaitForExit(120_000))
        {
            process.Kill(entireProcessTree: true);
            process.WaitForExit();
            throw new InvalidOperationException("The package tool did not exit.");
        }
        process.WaitForExit();
        return (process.ExitCode, stdoutTask.GetAwaiter().GetResult(), stderrTask.GetAwaiter().GetResult());
    }

    private static string RepositoryRoot()
    {
        for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
            if (File.Exists(Path.Combine(directory.FullName, "RuneCLR.slnx"))) return directory.FullName;
        throw new InvalidOperationException("Repository root was not found from the test output.");
    }

    private static string BuildConfiguration()
    {
        foreach (var part in AppContext.BaseDirectory.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar))
        {
            if (part.Equals("Release", StringComparison.OrdinalIgnoreCase)) return "Release";
            if (part.Equals("Debug", StringComparison.OrdinalIgnoreCase)) return "Debug";
        }
        return "Release";
    }

    private const string LaterCallbackScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            private IMapContext? context;
            public void OnStart(IMapContext value) { context = value; context.Log("ok"); }
            public void OnTick(MapTick tick) { }
            public void OnStop() { context!.SpawnEntity("late"); }
        }
        """;

    private static void LaterCallbackRejectsUnlisted()
    {
        using var temp = new TempDirectory();
        var output = Path.Combine(temp.Path, "package");
        var error = Check.Throws<InvalidDataException>(() => PackageBuilder.Compile("HostFields", "GameScript",
            [new("GameScript.cs", LaterCallbackScript)], Profile(), output,
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]));
        Check.Assert(error.Message.Contains("OnStop", StringComparison.Ordinal), error.Message);
        Check.Assert(error.Message.Contains("SpawnEntity", StringComparison.Ordinal), error.Message);
        Check.Assert(!Directory.Exists(output), "A rejected later callback published a package.");
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");
    }

    private static void HostInterfaceRejectsUnlisted()
    {
        using var temp = new TempDirectory();
        var error = Check.Throws<InvalidDataException>(() => PackageBuilder.Compile("HostFields", "GameScript",
            [new("GameScript.cs", HostFieldScript)], Profile(), Path.Combine(temp.Path, "package"),
            hostInterface: "RuneCLR.IMapContext", allowedMethods: ["Log"]));
        Check.Assert(error.Message.Contains("SpawnEntity", StringComparison.Ordinal), error.Message);
    }

    private static void HostInterfacePairRequired()
    {
        using var temp = new TempDirectory();
        Check.Throws<InvalidDataException>(() => PackageBuilder.Compile("HostFields", "GameScript",
            [new("GameScript.cs", HostFieldScript)], Profile(), Path.Combine(temp.Path, "package"),
            hostInterface: "RuneCLR.IMapContext"));
    }

    private static ReferenceProfile Profile() => new(Fixtures.FrameworkReferenceDirectory, Fixtures.ContractAssembly);
    private static PackageBuildResult Build(string output, string source = Script, ReferenceProfile? profile = null) =>
        PackageBuilder.Compile("Gameplay", "GameScript", [new("GameScript.cs", source)], profile ?? Profile(), output);
    private static void Run(string manifest)
    {
        var result = new MapRunner().Run(MapPackage.FromManifest(manifest), new MapRunOptions { TickCount = 2 });
        Check.Assert(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Script did not complete.");
        Check.Assert(result.Report.Logs.SequenceEqual(new[] { "starts=1", "tick=0", "tick=1", "stopped" }), "Lifecycle/static state mismatch.");
        Check.Assert(result.Report.CreatedEntities == 1 && result.Report.RemainingEntities == 0, "Session-owned entity was not released.");
        Check.Collected(result);
    }
    private static void SourceLifecycle()
    {
        using var temp = new TempDirectory();
        var build = Build(Path.Combine(temp.Path, "package"));
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        for (var cycle = 0; cycle < 3; cycle++) Run(build.ManifestPath!);
    }
    private static void ModernLanguageLifecycle()
    {
        using var temp = new TempDirectory();
        var build = Build(Path.Combine(temp.Path, "modern"), """
            using RuneCLR;
            using System.Collections.Generic;
            public sealed class GameScript : IMapScript
            {
                private int Value { get; set => field = value; }
                private static int Sum(params List<int> values)
                {
                    int sum = 0;
                    foreach (int value in values) sum += value;
                    return sum;
                }
                public void OnStart(IMapContext context)
                {
                    Value = Sum(20, 22);
                    context.Log("value=" + Value);
                }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """);
        Check.Assert(build.Succeeded, string.Join("; ", build.Diagnostics.Select(item => item.Message)));
        for (var cycle = 0; cycle < 3; cycle++)
        {
            var result = new MapRunner().Run(MapPackage.FromManifest(build.ManifestPath!));
            Check.Assert(result.Report.Outcome == MapRunOutcome.Completed
                && result.Report.Logs.SequenceEqual(new[] { "value=42" }),
                result.Report.Error ?? "Modern language fixture did not produce the expected result.");
            Check.Collected(result);
        }
    }
    private static void DeterministicPackage()
    {
        using var temp = new TempDirectory();
        var first = Build(Path.Combine(temp.Path, "one")); var second = Build(Path.Combine(temp.Path, "two"));
        Check.Assert(first.Succeeded && second.Succeeded, "Compilation failed.");
        var a = PackageManifestIO.Read(first.ManifestPath!); var b = PackageManifestIO.Read(second.ManifestPath!);
        Check.Assert(a.ContentSha256 == b.ContentSha256 && a.EntrySha256 == b.EntrySha256, "Output path affected package identity.");
        Check.Assert(!File.ReadAllText(first.ManifestPath!).Contains(temp.Path, StringComparison.OrdinalIgnoreCase), "Manifest leaks an absolute build path.");
    }
    private static void ImportLifecycle()
    {
        using var temp = new TempDirectory();
        var source = Build(Path.Combine(temp.Path, "source"));
        Check.Assert(source.Succeeded, "Source fixture failed.");
        var imported = PackageBuilder.Import("Imported", "GameScript", Path.Combine(temp.Path, "source", "Gameplay.dll"), Profile(), Path.Combine(temp.Path, "imported"));
        Check.Assert(imported.Succeeded, "IL import failed."); Run(imported.ManifestPath!);
        Check.Assert(PackageManifestIO.Read(imported.ManifestPath!).EntrySha256 == PackageManifestIO.Read(source.ManifestPath!).EntrySha256, "Import modified submitted IL bytes.");
    }
    private static void TamperRecovery()
    {
        using var temp = new TempDirectory();
        var bad = Build(Path.Combine(temp.Path, "bad")); var good = Build(Path.Combine(temp.Path, "good"));
        var saved = MapPackage.FromManifest(bad.ManifestPath!);
        File.AppendAllText(Path.Combine(temp.Path, "bad", "Gameplay.dll"), "tampered");
        Check.Throws<InvalidDataException>(() => MapPackage.FromManifest(bad.ManifestPath!));
        Check.Throws<InvalidDataException>(() => new MapRunner().Run(saved));
        Run(good.ManifestPath!);
    }
    private static void FailedPublication()
    {
        using var temp = new TempDirectory(); var output = Path.Combine(temp.Path, "bad");
        var failed = Build(output, "public class Broken { MissingType value; }");
        Check.Assert(!failed.Succeeded && failed.Diagnostics.Length > 0 && !Directory.Exists(output), "Compiler error published output.");
        var good = Build(output); Check.Assert(good.Succeeded, "Valid recovery build failed.");
        var original = File.ReadAllBytes(good.ManifestPath!);
        Check.Throws<IOException>(() => Build(output));
        Check.Assert(original.AsSpan().SequenceEqual(File.ReadAllBytes(good.ManifestPath!)), "Existing package changed.");
        Check.Assert(!Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(), "Build left private staging behind.");
    }
    private static void ReferenceSnapshot()
    {
        using var temp = new TempDirectory(); var refs = Path.Combine(temp.Path, "refs"); Directory.CreateDirectory(refs);
        foreach (var name in ReferenceProfile.FrameworkNames) File.Copy(Path.Combine(Fixtures.FrameworkReferenceDirectory, name + ".dll"), Path.Combine(refs, name + ".dll"));
        var profile = new ReferenceProfile(refs, Fixtures.ContractAssembly);
        foreach (var path in Directory.EnumerateFiles(refs)) File.WriteAllText(path, "changed after snapshot");
        var build = Build(Path.Combine(temp.Path, "package"), profile: profile);
        Check.Assert(build.Succeeded, "Reference profile reopened changed files."); Run(build.ManifestPath!);
    }

    private static string EmitDependency(string directory, string assemblyName, string source, IReadOnlyList<string>? extraReferences = null)
    {
        var compiled = SourceCompiler.Compile(assemblyName, [new("Dependency.cs", source)],
            CompilerFixture.ApprovedReferences().Concat(extraReferences ?? []).ToArray());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, assemblyName + ".dll"); File.WriteAllBytes(path, compiled.Assembly!); return path;
    }
    private static void PrivateDependencies()
    {
        using var temp = new TempDirectory();
        const string script = """
            using RuneCLR;
            public sealed class PrivateScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log(SharedHelper.Read()); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var a = EmitDependency(Path.Combine(temp.Path, "input-a"), "SharedLibrary", """
            [assembly: System.Reflection.AssemblyVersion("1.0.0.0")]
            public static class SharedHelper { private static int starts; public static string Read() => "A:" + (++starts); }
            """);
        var b = EmitDependency(Path.Combine(temp.Path, "input-b"), "SharedLibrary", """
            [assembly: System.Reflection.AssemblyVersion("2.0.0.0")]
            public static class SharedHelper { private static int starts; public static string Read() => "B:" + (++starts); }
            """);
        var first = PackageBuilder.Compile("PrivateA", "PrivateScript", [new("PrivateScript.cs", script)], Profile(), Path.Combine(temp.Path, "a"), [a]);
        var second = PackageBuilder.Compile("PrivateB", "PrivateScript", [new("PrivateScript.cs", script)], Profile(), Path.Combine(temp.Path, "b"), [b]);
        Check.Assert(first.Succeeded && second.Succeeded, "Private dependency source build failed.");
        var imported = PackageBuilder.Import("PrivateImported", "PrivateScript", Path.Combine(temp.Path, "a", "PrivateA.dll"), Profile(), Path.Combine(temp.Path, "import"), [a]);
        Check.Assert(imported.Succeeded, "Private dependency import failed.");
        foreach (var (manifest, expected) in new[] { (first.ManifestPath!, "A:1"), (second.ManifestPath!, "B:1"), (first.ManifestPath!, "A:1"), (imported.ManifestPath!, "A:1") })
        {
            var result = new MapRunner().Run(MapPackage.FromManifest(manifest));
            Check.Assert(result.Report.Outcome == MapRunOutcome.Completed && result.Report.Logs.SequenceEqual(new[] { expected }), result.Report.Error ?? "Dependency state/version escaped session.");
            Check.Collected(result);
        }
    }
    private static void UndeclaredDependency()
    {
        using var temp = new TempDirectory();
        var second = EmitDependency(Path.Combine(temp.Path, "input"), "TransitiveLibrary", "public static class Second { public static int Value() => 42; }");
        var first = EmitDependency(Path.Combine(temp.Path, "input"), "PrimaryLibrary", "public static class First { public static int Value() => Second.Value(); }", [second]);
        var output = Path.Combine(temp.Path, "package");
        var error = Check.Throws<InvalidDataException>(() => PackageBuilder.Compile("Undeclared", "GameScript", [new("GameScript.cs", Script)], Profile(), output, [first]));
        Check.Assert(error.Message.Contains("TransitiveLibrary", StringComparison.Ordinal) && !Directory.Exists(output), "Undeclared transitive reference was published or not identified.");
    }
    private static void AuthorFailure()
    {
        using var temp = new TempDirectory();
        const string faultyScript = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                private IMapContext? context;
                public void OnStart(IMapContext value)
                {
                    context = value;
                    context.SpawnEntity("before-error");
                    throw new AuthorFailureException();
                }
                public void OnTick(MapTick tick) { }
                public void OnStop() { context!.Log("stopped-after-error"); }
            }
            public sealed class AuthorFailureException : System.Exception { }
            """;
        var faulty = Build(Path.Combine(temp.Path, "faulty"), faultyScript);
        Check.Assert(faulty.Succeeded, "Author exception fixture did not compile.");
        var result = new MapRunner().Run(MapPackage.FromManifest(faulty.ManifestPath!));
        Check.Assert(result.Report.Outcome == MapRunOutcome.Failed && result.Report.Error?.Contains("AuthorFailureException", StringComparison.Ordinal) == true,
            "Author exception was not captured as a host-owned description.");
        Check.Assert(result.Report.CreatedEntities == 1 && result.Report.ReleasedEntities == 1 && result.Report.RemainingEntities == 0
            && result.Report.Logs.SequenceEqual(new[] { "stopped-after-error" }), "Author failure did not stop and clean up.");
        Check.Collected(result);
        var next = Build(Path.Combine(temp.Path, "next")); Check.Assert(next.Succeeded, "Next package failed to compile.");
        Run(next.ManifestPath!);
    }

    private sealed class RecordingMapContext : IMapContext
    {
        public List<string> Logs { get; } = [];
        public string? Spawned { get; private set; }
        public string MapId => "fixture";
        public EntityId SpawnEntity(string name) { Spawned = name; return new EntityId(1); }
        public EntityId? Destroyed { get; private set; }
        public void DestroyEntity(EntityId entity) { Destroyed = entity; }
        public void Log(string message) => Logs.Add(message);
        public int? Charged { get; private set; }
        public void Charge(int operations = 1) { Charged = operations; }
        public event Action<int>? Signal { add { } remove { } }
        public void RaiseSignal(int value) { }
        public void Schedule(int dueInTicks, int value) { }
        public void Repeat(int everyTicks, int value) { }
        public bool TryTakeScheduled(out int value) { value = 0; return false; }
        public int PendingScheduled => 0;
        public long RequestWork(string name) => 0;
        public bool TryTakeWork(out long id, out int value, out bool succeeded) { id = 0; value = 0; succeeded = false; return false; }
        public int PendingWork => 0;
        public void RegisterResource(string name) { }
        public bool ReleaseResource(string name) => false;
        public int PendingResources => 0;
        public void Subscribe(int id) { }
        public bool TryTakePosted(out int id, out int value) { id = 0; value = 0; return false; }
        public int PendingPosted => 0;
    }
}
