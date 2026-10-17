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
        yield return ("Compiled host-contract package runs a later callback", HostInterfaceLaterCallback);
        yield return ("Compiled host-contract package returns an int from a later callback", HostInterfaceReturnsInt);
        yield return ("Compiled host-contract package passes the host and an int", HostInterfacePassesHostAndInt);
        yield return ("Compiled host-contract package calls a private assembly from a later callback", HostInterfacePrivateCallback);
        yield return ("Compiled host-contract package lets one private assembly call another", HostInterfacePrivateChain);
        yield return ("Compiled host-contract package lets a private assembly call the entry", HostInterfacePrivateCallsEntry);
        yield return ("Compiled host-contract package constructs an author type", HostInterfaceConstructsAuthorType);
        yield return ("Compiled host-contract package rejects a framework constructor", HostInterfaceRejectsFrameworkNew);
        yield return ("Compiled host-contract package constructs a private assembly type", HostInterfaceConstructsPrivateType);
        yield return ("Imported host-contract IL opens and returns an int", HostInterfaceImportsIl);
        yield return ("Imported host-contract IL calls a private assembly", HostInterfaceImportsPrivate);
        yield return ("Imported host-contract IL rejects a framework constructor", HostInterfaceImportRejectsFrameworkNew);
        yield return ("Imported host-contract IL lets a private assembly call the entry", HostInterfaceImportPrivateCallsEntry);
        yield return ("Operator CLI compiles a host-contract package", HostInterfaceOperatorCli);
        yield return ("Operator CLI rejects a framework constructor", HostInterfaceOperatorCliRejectsFrameworkNew);
        yield return ("Operator CLI imports a host-contract assembly", HostInterfaceOperatorCliImportsIl);
        yield return ("Operator CLI import rejects a framework constructor", HostInterfaceOperatorCliImportRejectsFrameworkNew);
        yield return ("Operator CLI compiles a private dependency", HostInterfaceOperatorCliCompilesDependency);
        yield return ("Operator CLI imports a private dependency", HostInterfaceOperatorCliImportsDependency);
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
        public void DestroyEntity(EntityId entity) { }
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
