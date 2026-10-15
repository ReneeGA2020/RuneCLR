using System.Collections.Immutable;
using System.Reflection;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.Diagnostics;

// Runs the actual official source generator, then compiles its unchanged output
// against a controlled platform/GC-stress model. This is generator semantics
// evidence on the operator desktop, not execution on an Apple runtime.
internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length != 3 || args[0] is not ("baseline" or "patched"))
            throw new ArgumentException("baseline|patched <official generator root> <NEW output>");
        var patched = args[0] == "patched";
        var root = Path.GetFullPath(args[1]);
        var output = Path.GetFullPath(args[2]);
        if (Directory.Exists(output)) throw new IOException("Preserve old generated output");
        Directory.CreateDirectory(output);
        var references = ((string)AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES")!).Split(Path.PathSeparator)
            .Select(p => MetadataReference.CreateFromFile(p)).ToArray();
        var enumTrees = new[] { "TestPlatforms.cs", "RuntimeTestModes.cs" }
            .Select(n => CSharpSyntaxTree.ParseText(File.ReadAllText(Path.Combine(root, n)), path: n)).ToArray();
        var rows = new List<object>();
        var generated = new Dictionary<string, string>();
        foreach (var target in new[] { "ios", "iossimulator", "IOSSimulator", "tvos", "tvossimulator", "TvOSSimulator", "windows", "maccatalyst", "not-a-platform" })
        {
            var sources = new[] { CSharpSyntaxTree.ParseText(Fixture, path: "Fixture.cs") }.Concat(enumTrees);
            var compilation = CSharpCompilation.Create("GeneratedProbe", sources, references,
                new CSharpCompilationOptions(OutputKind.ConsoleApplication,
                    specificDiagnosticOptions: new Dictionary<string, ReportDiagnostic> { ["CS0436"] = ReportDiagnostic.Suppress }));
            GeneratorDriver driver = CSharpGeneratorDriver.Create(
                generators: new[] { new XUnitWrapperGenerator.XUnitWrapperGenerator().AsSourceGenerator() },
                optionsProvider: new Options(target));
            driver = driver.RunGeneratorsAndUpdateCompilation(compilation, out var actual, out var diagnostics);
            var errors = diagnostics.Concat(actual.GetDiagnostics()).Where(d => d.Severity == DiagnosticSeverity.Error).ToArray();
            if (errors.Length != 0) throw new Exception(string.Join(Environment.NewLine, errors.Select(d => d.ToString())));
            var result = driver.GetRunResult();
            var source = result.Results.Single().GeneratedSources.Single(s => s.HintName == "SimpleRunner.g.cs").SourceText.ToString();
            generated[target] = source;
            var dir = Path.Combine(output, target);
            Directory.CreateDirectory(dir);
            File.WriteAllText(Path.Combine(dir, "SimpleRunner.g.cs"), source);
            File.WriteAllLines(Path.Combine(dir, "diagnostics.txt"), diagnostics.Select(d => d.ToString()));
            using var pe = new MemoryStream();
            var emit = actual.Emit(pe);
            if (!emit.Success) throw new Exception(string.Join(Environment.NewLine, emit.Diagnostics.Select(d => d.ToString())));
            File.WriteAllBytes(Path.Combine(dir, "GeneratedProbe.dll"), pe.ToArray());
            var context = new AssemblyLoadContext("GeneratorSemantics-" + target, isCollectible: true);
            pe.Position = 0;
            var assembly = context.LoadFromStream(pe);
            var model = assembly.GetType("System.OperatingSystem")!;
            var config = assembly.GetType("TestLibrary.CoreClrConfigurationDetection")!;
            var fixture = assembly.GetType("Fixture")!;
            var normalized = target.ToLowerInvariant();
            var appleIOS = normalized is "ios" or "iossimulator";
            var appleTV = normalized is "tvos" or "tvossimulator";
            model.GetField("IOS")!.SetValue(null, appleIOS);
            model.GetField("TVOS")!.SetValue(null, appleTV);
            model.GetField("Catalyst")!.SetValue(null, normalized == "maccatalyst");
            model.GetField("Windows")!.SetValue(null, normalized == "windows");
            foreach (var gcStress in new[] { false, true })
            {
                fixture.GetField("Bodies")!.SetValue(null, 0);
                config.GetField("IsGCStress")!.SetValue(null, gcStress);
                var exit = (int)assembly.EntryPoint!.Invoke(null, null)!;
                var bodies = (int)fixture.GetField("Bodies")!.GetValue(null)!;
                var knownAlias = normalized is "iossimulator" or "tvossimulator";
                var omitted = normalized == "not-a-platform" || (!patched && knownAlias);
                var expected = omitted ? 8 : 8 + (appleIOS ? 2 : appleTV ? 4 : 0) + (gcStress ? 0 : 1);
                if (exit != 100 || bodies != expected)
                    throw new Exception($"{target} stress={gcStress}: exit={exit}, actual bodies={bodies}, expected={expected}");
                rows.Add(new { target, gcStress, exit, bodies, expected, passed = true });
                Console.WriteLine($"PASS {target} GCStress={gcStress}: body mask={bodies}; exit={exit}");
            }
            if (appleIOS && (patched || normalized == "ios"))
            {
                model.GetField("Catalyst")!.SetValue(null, true);
                config.GetField("IsGCStress")!.SetValue(null, false);
                fixture.GetField("Bodies")!.SetValue(null, 0);
                var exit = (int)assembly.EntryPoint!.Invoke(null, null)!;
                var bodies = (int)fixture.GetField("Bodies")!.GetValue(null)!;
                if (exit != 100 || bodies != 10) throw new Exception("Inherited iOS runtime guard must exclude MacCatalyst");
                rows.Add(new { target, modeledMacCatalyst = true, bodies, expected = 10, passed = true });
                Console.WriteLine($"PASS {target}: inherited iOS runtime guard excludes MacCatalyst");
            }
            context.Unload();
        }
        if (patched)
        {
            foreach (var (target, alias) in new[] { ("ios", "iossimulator"), ("ios", "IOSSimulator"), ("tvos", "tvossimulator"), ("tvos", "TvOSSimulator") })
                if (generated[target] != generated[alias]) throw new Exception("Alias generated Main differs: " + alias);
        }
        else if (!generated["iossimulator"].Contains("(false)") || !generated["tvossimulator"].Contains("(false)"))
            throw new Exception("Original false-condition regression was not reproduced");
        File.WriteAllText(Path.Combine(output, "results.json"), JsonSerializer.Serialize(new
        {
            mode = args[0], success = true, rows, aliasGeneratedMainEquivalent = patched,
            sourceHashes = Directory.GetFiles(root, "*.cs").Order().ToDictionary(p => Path.GetFileName(p)!, p => Hash(File.ReadAllBytes(p))),
            generatorAssemblySha256 = Hash(File.ReadAllBytes(typeof(XUnitWrapperGenerator.XUnitWrapperGenerator).Assembly.Location)),
            runtime = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription,
            roslyn = typeof(CSharpCompilation).Assembly.GetName().Version!.ToString(),
            scope = "Actual official generator source; generated Main compiled/executed against controlled platform model on desktop; no Apple runtime/XHarness claim"
        }, new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($"GENERATOR {args[0]} PASS: {rows.Count}/{rows.Count} generated-body checks");
        return 0;
    }

    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    private sealed class Options(string target) : AnalyzerConfigOptionsProvider
    {
        public override AnalyzerConfigOptions GlobalOptions { get; } = new Values(target);
        public override AnalyzerConfigOptions GetOptions(SyntaxTree tree) => GlobalOptions;
        public override AnalyzerConfigOptions GetOptions(AdditionalText textFile) => GlobalOptions;
        private sealed class Values(string target) : AnalyzerConfigOptions
        {
            private readonly Dictionary<string, string> values = new(StringComparer.OrdinalIgnoreCase)
            { ["build_property.TargetOS"] = target, ["build_property.RuntimeFlavor"] = "CoreCLR",
              ["build_property.InMergedTestDirectory"] = "false", ["build_property.BuildAsStandalone"] = "true" };
            public override bool TryGetValue(string key, out string value) => values.TryGetValue(key, out value!);
        }
    }

    private const string Fixture = """
        namespace Xunit
        {
            public sealed class FactAttribute : System.Attribute { }
            public sealed class SkipOnCoreClrAttribute(string reason, RuntimeTestModes modes) : System.Attribute { }
            public sealed class PlatformSpecificAttribute(TestPlatforms platforms) : System.Attribute { }
        }
        namespace TestLibrary
        {
            public static class CoreClrConfigurationDetection { public static bool IsGCStress; }
        }
        namespace System
        {
            public static class OperatingSystem
            {
                public static bool IOS, TVOS, Catalyst, Windows;
                public static bool IsIOS() => IOS;
                public static bool IsTvOS() => TVOS;
                public static bool IsMacCatalyst() => Catalyst;
                public static bool IsWindows() => Windows;
            }
        }
        public static class Fixture
        {
            public static int Bodies;
            [Xunit.Fact, Xunit.SkipOnCoreClr("stress", Xunit.RuntimeTestModes.AnyGCStress)]
            public static void StressSensitive() { Bodies |= 1; }
            [Xunit.Fact, Xunit.PlatformSpecific(Xunit.TestPlatforms.iOS)]
            public static void IOSOnly() { Bodies |= 2; }
            [Xunit.Fact, Xunit.PlatformSpecific(Xunit.TestPlatforms.tvOS)]
            public static void TVOnly() { Bodies |= 4; }
            [Xunit.Fact] public static void PlainControl() { Bodies |= 8; }
        }
        """;
}
