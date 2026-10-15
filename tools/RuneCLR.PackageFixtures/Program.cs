using System.Security.Cryptography;
using System.Text.Json;
using RuneCLR.Compiler;
using RuneCLR.Packages;

namespace RuneCLR.PackageFixtures;

internal static class Program
{
    private static int Main(string[] args)
    {
        try
        {
            if (args is ["--help"] or ["-h"])
            {
                Console.WriteLine("RuneCLR.PackageFixtures --framework-refs <fixed reference directory> --contract <approved Abstractions.dll> --output <NEW directory> [--include-pumped] [--include-budget]");
                Console.WriteLine("Operator-only acceptance fixture generator; includes intentionally invalid test packages.");
                return 0;
            }
            var includePumped = args.Contains("--include-pumped", StringComparer.Ordinal);
            var includeBudget = args.Contains("--include-budget", StringComparer.Ordinal);
            if (args.Count(argument => argument == "--include-pumped") > 1)
                throw new ArgumentException("--include-pumped may only be supplied once.");
            if (args.Count(argument => argument == "--include-budget") > 1)
                throw new ArgumentException("--include-budget may only be supplied once.");
            args = args.Where(argument => argument is not ("--include-pumped" or "--include-budget")).ToArray();
            var options = new Dictionary<string, string>(StringComparer.Ordinal);
            for (var index = 0; index < args.Length; index += 2)
                if (index + 1 >= args.Length || args[index] is not ("--framework-refs" or "--contract" or "--output") ||
                    !options.TryAdd(args[index], args[index + 1]))
                    throw new ArgumentException("Expected each of --framework-refs, --contract, --output exactly once.");
            string Required(string option) => options.TryGetValue(option, out var value) && !string.IsNullOrWhiteSpace(value)
                ? value : throw new ArgumentException("Missing " + option + ".");
            Generate(Required("--framework-refs"), Required("--contract"), Required("--output"), includePumped, includeBudget);
            return 0;
        }
        catch (Exception error) when (error is ArgumentException or IOException or InvalidDataException or UnauthorizedAccessException or BadImageFormatException)
        {
            Console.Error.WriteLine($"Fixture generation failed: {error.Message}");
            return 2;
        }
    }

    private static void Generate(string referencesDirectory, string contractPath, string output, bool includePumped, bool includeBudget)
    {
        var destination = Path.GetFullPath(output);
        if (Path.Exists(destination)) throw new IOException("Output directory must be new.");
        var parent = Path.GetDirectoryName(destination) ?? throw new ArgumentException("Output needs a parent directory.");
        Directory.CreateDirectory(parent);
        var staging = Path.Combine(parent, ".runeclr-fixtures-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(staging);
        try
        {
            var profile = new ReferenceProfile(referencesDirectory, contractPath);
            var references = ReferenceProfile.FrameworkNames.Select(name => Path.Combine(referencesDirectory, name + ".dll"))
                .Append(contractPath).ToArray();
            string Package(string name) => Path.Combine(staging, name);
            void Build(string name, string id, string source, params string[] dependencies)
            {
                var result = PackageBuilder.Compile(id, "GameScript", [new("GameScript.cs", source)], profile, Package(name), dependencies);
                RequireBuild(result);
            }
            Build("source", "Gameplay", Script);
            RequireBuild(PackageBuilder.Import("GameplayImport", "GameScript", Path.Combine(Package("source"), "Gameplay.dll"),
                profile, Package("import")));
            Build("failure", "GameplayFailure", FailureScript);
            if (includePumped)
            {
                Build("frames", "GameplayFrames", FrameScript);
                Build("tick-failure", "GameplayTickFailure", TickFailureScript);
                Build("stop-failure", "GameplayStopFailure", StopFailureScript);
            }
            CopyPackage(Package("source"), Package("tampered"));
            using (var stream = new FileStream(Path.Combine(Package("tampered"), "Gameplay.dll"), FileMode.Append)) stream.WriteByte(1);
            CopyPackage(Package("source"), Package("forbidden"));
            // Deliberate attacker fixture: compile without admission, then change IL and reseal integrity metadata.
            // This bypass belongs exclusively to this operator test tool, never to a package publishing endpoint.
            Reseal(Package("forbidden"), "Gameplay.dll", Compile("Gameplay", Script.Replace(
                "public void OnStop()", "private static void ForbiddenHelper() { System.GC.Collect(); } public void OnStop()", StringComparison.Ordinal), references));

            var inputs = Path.Combine(staging, ".operator-inputs");
            Directory.CreateDirectory(inputs);
            if (includeBudget)
            {
                Build("budget-work", "BudgetWork", BudgetScript(BudgetWorkMethods));
                Build("budget-constructor-loop", "BudgetConstructorLoop", BudgetScript("public GameScript() { Spin(); }"));
                Build("budget-static-constructor-loop", "BudgetStaticConstructorLoop", BudgetScript("static GameScript() { Spin(); }"));
                Build("budget-start-loop", "BudgetStartLoop", BudgetScript("public override void OnStart(IMapContext value) { base.OnStart(value); Spin(); value.Log(\"start-after\"); }"));
                Build("budget-tick-loop", "BudgetTickLoop", BudgetScript("public override void OnTick(MapTick tick) { Context.Log(\"tick-before\"); Spin(); Context.Log(\"tick-after\"); }"));
                Build("budget-catch-resume", "BudgetCatchResume", BudgetScript("public override void OnTick(MapTick tick) { try { Spin(); } catch { Context.Log(\"broad-catch\"); } Context.Log(\"resume\"); }"));
                Build("budget-stop-loop", "BudgetStopLoop", BudgetScript("public override void OnStop() { Context.Log(\"stop-before\"); Spin(); Context.Log(\"stop-after\"); }"));
                var helper = Path.Combine(inputs, "BudgetHelper.dll");
                File.WriteAllBytes(helper, Compile("BudgetHelper", BudgetHelperScript, references));
                Build("budget-finite-cleanup", "BudgetFiniteCleanup", BudgetScript("public override void OnTick(MapTick tick) { try { Spin(); } finally { Context.Log(\"finally\"); BudgetHelper.Finite(Context); } }"), helper);
                Build("budget-infinite-cleanup", "BudgetInfiniteCleanup", BudgetScript("public override void OnTick(MapTick tick) { try { Spin(); } finally { BudgetHelper.Infinite(Context); } }"), helper);
            }
            string Helper(string version, string label)
            {
                var directory = Path.Combine(inputs, label); Directory.CreateDirectory(directory);
                var path = Path.Combine(directory, "SharedGameplay.dll");
                File.WriteAllBytes(path, Compile("SharedGameplay", HelperSource(version, label), references));
                return path;
            }
            var a = Helper("1.0.0.0", "A"); var b = Helper("2.0.0.0", "B");
            Build("private-a", "PrivateA", PrivateScript, a);
            Build("private-b", "PrivateB", PrivateScript, b);
            RequireBuild(PackageBuilder.Import("PrivateImport", "GameScript", Path.Combine(Package("private-a"), "PrivateA.dll"),
                profile, Package("private-import"), [a]));
            CopyPackage(Package("private-a"), Package("private-forbidden"));
            Reseal(Package("private-forbidden"), "lib/SharedGameplay.dll", Compile("SharedGameplay",
                HelperSource("1.0.0.0", "A") + "public static class ForbiddenHelper { public static void Hidden() { System.GC.Collect(); } }", references));
            // These are this operation's own bounded child inputs. Final packages contain only manifest and DLL files.
            Directory.Delete(inputs, recursive: true);
            var names = new List<string> { "source", "import", "failure", "tampered", "forbidden", "private-a", "private-b", "private-import", "private-forbidden" };
            if (includePumped) names.AddRange(["frames", "tick-failure", "stop-failure"]);
            if (includeBudget) names.AddRange(["budget-work", "budget-constructor-loop", "budget-static-constructor-loop",
                "budget-start-loop", "budget-tick-loop", "budget-catch-resume", "budget-stop-loop",
                "budget-finite-cleanup", "budget-infinite-cleanup"]);
            var receipt = new
            {
                fixtureFormatVersion = 1, tool = "RuneCLR.PackageFixtures", toolVersion = "0.1.0",
                inputProfile = GameplayCapabilityPolicy.Profile, generatedUtc = DateTimeOffset.UtcNow,
                operatorRuntime = Environment.Version.ToString(), contractAssemblyIdentity = profile.ContractIdentity,
                contractImageSha256 = Hash(File.ReadAllBytes(contractPath)),
                intentionallyInvalid = new[] { "tampered", "forbidden", "private-forbidden" },
                packages = names.Select(name => new
                {
                    directory = name, manifest = name + "/package.json",
                    manifestSha256 = Hash(File.ReadAllBytes(Path.Combine(Package(name), "package.json"))),
                    contentSha256 = PackageManifestIO.Read(Path.Combine(Package(name), "package.json")).ContentSha256
                }).ToArray()
            };
            File.WriteAllText(Path.Combine(staging, "fixtures.json"), JsonSerializer.Serialize(receipt, new JsonSerializerOptions { WriteIndented = true }));
            Directory.Move(staging, destination);
            Console.WriteLine($"Generated {names.Count} controlled package fixtures at {destination}");
            Console.WriteLine("Includes intentionally invalid admission fixtures: tampered, forbidden, private-forbidden.");
        }
        finally
        {
            if (Path.GetDirectoryName(Path.GetFullPath(staging)) != parent ||
                !Path.GetFileName(staging).StartsWith(".runeclr-fixtures-", StringComparison.Ordinal))
                throw new InvalidOperationException("Invalid fixture staging cleanup target.");
            if (Directory.Exists(staging)) Directory.Delete(staging, recursive: true);
        }
    }

    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static byte[] Compile(string name, string source, string[] references)
    {
        var result = SourceCompiler.Compile(name, [new("Fixture.cs", source)], references);
        if (!result.Succeeded) throw new InvalidDataException(string.Join("; ", result.Diagnostics.Select(item => item.Message)));
        return result.Assembly!;
    }
    private static void RequireBuild(PackageBuildResult result)
    {
        if (!result.Succeeded) throw new InvalidDataException(string.Join("; ", result.Diagnostics.Select(item => item.Message)));
    }
    private static void CopyPackage(string source, string destination)
    {
        Directory.CreateDirectory(destination);
        foreach (var input in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
        {
            var output = Path.Combine(destination, Path.GetRelativePath(source, input));
            Directory.CreateDirectory(Path.GetDirectoryName(output)!); File.Copy(input, output);
        }
    }
    private static void Reseal(string package, string relativePath, byte[] image)
    {
        var path = Path.Combine(package, "package.json");
        var manifest = PackageManifestIO.Read(path); var hash = Hash(image);
        File.WriteAllBytes(Path.Combine(package, relativePath), image);
        manifest = manifest with
        {
            EntrySha256 = relativePath == manifest.EntryAssembly ? hash : manifest.EntrySha256,
            Dependencies = manifest.Dependencies.Select(item => item.Path == relativePath ? item with { Sha256 = hash } : item).ToArray(),
            Files = manifest.Files.Select(item => item.Path == relativePath ? item with { Sha256 = hash } : item).ToArray()
        };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(path, manifest);
    }

    private const string Script = """
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
    private const string FailureScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            private IMapContext? context;
            public void OnStart(IMapContext value) { context = value; context.SpawnEntity("before-error"); throw new AuthorFailureException(); }
            public void OnTick(MapTick tick) { }
            public void OnStop() { context!.Log("stopped-after-error"); }
        }
        public sealed class AuthorFailureException : System.Exception { }
        """;
    private const string PrivateScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            private IMapContext? context;
            public void OnStart(IMapContext value) { context = value; context.Log(SharedHelper.Read()); context.SpawnEntity("private"); }
            public void OnTick(MapTick tick) { }
            public void OnStop() { context!.Log("stopped"); }
        }
        """;
    private const string FrameScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            private IMapContext? context;
            private long total;
            public void OnStart(IMapContext value) { context = value; context.SpawnEntity("frames"); context.Log("started"); }
            public void OnTick(MapTick tick)
            {
                total += tick.Delta.Ticks;
                context!.Log("tick=" + tick.Index + ":delta=" + tick.Delta.Ticks + ":total=" + total);
            }
            public void OnStop() { context!.Log("stopped"); }
        }
        """;
    private const string TickFailureScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            private IMapContext? context;
            public void OnStart(IMapContext value) { context = value; context.SpawnEntity("tick-error"); }
            public void OnTick(MapTick tick) { if (tick.Index == 1) throw new AuthorFailureException(); context!.Log("tick=" + tick.Index); }
            public void OnStop() { context!.Log("stopped-after-tick-error"); }
        }
        public sealed class AuthorFailureException : System.Exception { }
        """;
    private const string StopFailureScript = """
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            private IMapContext? context;
            public void OnStart(IMapContext value) { context = value; context.SpawnEntity("stop-error"); }
            public void OnTick(MapTick tick) { context!.Log("tick=" + tick.Index); }
            public void OnStop() { throw new AuthorFailureException(); }
        }
        public sealed class AuthorFailureException : System.Exception { }
        """;
    private const string BudgetWorkMethods = """
        private int checksum;
        public override void OnTick(MapTick tick)
        {
            for (var index = 0; index < 64; index++)
                checksum = unchecked(checksum * 31 + index + tick.Index);
            Context.Log("work=" + tick.Index);
        }
        """;
    private static string BudgetScript(string methods) => $$"""
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            private IMapContext Context = null!;
            private void Start(IMapContext value)
            {
                Context = value;
                Context.SpawnEntity("budget-owned");
                Context.Log("start");
            }
            {{(methods.Contains("void OnStart(", StringComparison.Ordinal) ? "" : "public void OnStart(IMapContext value) { Start(value); }")}}
            {{(methods.Contains("void OnTick(", StringComparison.Ordinal) ? "" : "public void OnTick(MapTick tick) { Context.Log(\"tick=\" + tick.Index); }")}}
            {{(methods.Contains("void OnStop(", StringComparison.Ordinal) ? "" : "public void OnStop() { Context.Log(\"stop\"); }")}}
            private static void Spin()
            {
                var value = 0;
                while (true) value = unchecked(value + 1);
            }
            {{methods.Replace("public override ", "public ", StringComparison.Ordinal).Replace("base.OnStart(value)", "Start(value)", StringComparison.Ordinal)}}
        }
        """;
    private const string BudgetHelperScript = """
        using RuneCLR;
        public static class BudgetHelper
        {
            public static void Finite(IMapContext context)
            {
                var checksum = 0;
                for (var index = 0; index < 32; index++)
                    checksum = unchecked(checksum * 31 + index);
                context.Log("helper-finite");
                context.Log("cleanup-checksum=" + checksum);
            }
            public static void Infinite(IMapContext context)
            {
                context.Log("helper-infinite-before");
                var value = 0;
                while (true) value = unchecked(value + 1);
            }
        }
        """;
    private static string HelperSource(string version, string label) => $$"""
        [assembly: System.Reflection.AssemblyVersion("{{version}}")]
        public static class SharedHelper
        {
            private static int starts;
            public static string Read() => "{{label}}:" + (++starts) + ":" + GenericCounter<int>.Next();
        }
        public static class GenericCounter<T> { private static int starts; public static int Next() => ++starts; }
        """;
}
