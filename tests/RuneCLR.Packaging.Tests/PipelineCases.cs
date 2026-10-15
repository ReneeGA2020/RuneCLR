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
        yield return ("Same source produces identical package identities independent of output path", DeterministicPackage);
        yield return ("Raw IL import preserves bytes and runs through the same versioned loader", ImportLifecycle);
        yield return ("Changed files are rejected and the next valid session still succeeds", TamperRecovery);
        yield return ("Compilation errors publish no package and existing outputs are preserved", FailedPublication);
        yield return ("Input and reference snapshots survive later operator file changes", ReferenceSnapshot);
        yield return ("Version-distinct private dependencies stay isolated in source and IL packages", PrivateDependencies);
        yield return ("Undeclared transitive dependencies fail intake before publication", UndeclaredDependency);
        yield return ("A packaged author exception cleans up, unloads and permits the next package", AuthorFailure);
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
}
