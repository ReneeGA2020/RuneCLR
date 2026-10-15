using System.Reflection.PortableExecutable;
using RuneCLR.Compiler;

internal static class CompilerCases
{
    internal static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Controlled compiler emits a real multi-source script without executing it", ValidScript);
        yield return ("Compiler output is deterministic and contains no PDB", DeterministicOutput);
        yield return ("Compiler diagnostics use real one-based source labels despite #line", DiagnosticLocations);
        yield return ("Compiler rejects unsafe and does not return partial assemblies", UnsafeRejected);
        yield return ("Authors cannot reference assemblies outside the approved profile", UnapprovedReference);
        yield return ("Regular C# rejects author #r and #load directives", ScriptDirectives);
        yield return ("Compiler rejects invalid source labels and duplicate files", InvalidNames);
        yield return ("Compiler bounds source count, total text and diagnostic output", InputLimits);
        yield return ("Missing approved references produce actionable diagnostics", MissingReference);
        yield return ("Compiler accepts modern syntax from the selected SDK without a C# 12 cap", ModernLanguage);
    }

    private static SourceFile[] ScriptSources() =>
    [
        new("ugc/GameScript.cs", """
            using RuneCLR;
            using System.Collections.Generic;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context)
                {
                    var values = new List<int> { 1, 2, 3 };
                    context.Log(Helper.Sum(values).ToString());
                }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """),
        new("ugc/Helper.cs", """
            using System;
            using System.Collections.Generic;
            using System.Runtime.CompilerServices;
            public static class Helper
            {
                public static int Sum(List<int> values)
                {
                    int sum = 0;
                    foreach (int value in values) sum += value;
                    return sum;
                }
                [ModuleInitializer]
                public static void MustNotRunDuringCompilation() =>
                    throw new InvalidOperationException("author code was executed");
            }
            """)
    ];

    private static CompilationResult Compile(params SourceFile[] sources) =>
        SourceCompiler.Compile("CompilerCaseScript", sources, CompilerFixture.ApprovedReferences());

    private static void ValidScript()
    {
        var result = Compile(ScriptSources());
        Check.Assert(result.Succeeded, string.Join("; ", result.Diagnostics.Select(item => item.Message)));
        Check.Assert(result.Assembly is { Length: > 0 }, "No compiled DLL was returned.");
        Check.Assert(result.CompilerIdentities.Length == 2, "Expected both actual Roslyn compiler identities.");
        foreach (var identity in result.CompilerIdentities)
        {
            Check.Assert(identity.Name.EndsWith(".dll", StringComparison.Ordinal), "Compiler identity must name a DLL.");
            Check.Assert(!identity.Name.Contains('/') && !identity.Name.Contains((char)92), "Compiler identity exposes a machine path.");
            Check.Assert(identity.Sha256.Length == 64 && identity.Sha256.All(Uri.IsHexDigit), "Compiler hash is invalid.");
            Check.Assert(identity.AssemblyName?.Contains("Version=", StringComparison.Ordinal) == true, "Compiler version was not recorded.");
        }
        using var stream = new MemoryStream(result.Assembly!);
        using var pe = new PEReader(stream);
        Check.Assert(pe.HasMetadata && pe.PEHeaders.CorHeader is not null, "Output is not a managed PE.");
        Check.Assert((pe.PEHeaders.CorHeader!.Flags & CorFlags.ILOnly) != 0, "Output is not IL-only.");
        Check.Assert((pe.PEHeaders.CorHeader.Flags & CorFlags.Requires32Bit) == 0, "Output is not AnyCPU.");
        Check.Assert((pe.PEHeaders.CoffHeader.Characteristics & Characteristics.Dll) != 0, "Output is not a DLL.");
    }

    private static void DeterministicOutput()
    {
        var first = Compile(ScriptSources());
        var second = Compile(ScriptSources());
        Check.Assert(first.Succeeded && second.Succeeded, "Determinism fixture did not compile.");
        Check.Assert(first.Assembly!.AsSpan().SequenceEqual(second.Assembly), "Same inputs produced different DLL bytes.");
        using var stream = new MemoryStream(first.Assembly!);
        using var pe = new PEReader(stream);
        Check.Assert(!pe.ReadDebugDirectory().Any(entry => entry.Type is DebugDirectoryEntryType.CodeView
            or DebugDirectoryEntryType.EmbeddedPortablePdb), "Compiler output unexpectedly contains a PDB.");
    }

    private static void DiagnosticLocations()
    {
        var result = Compile(new SourceFile("authors/problem.cs", """
            #line 700 "invented.cs"
            public sealed class Broken
            {
                MissingType value;
            }
            """));
        Check.Assert(!result.Succeeded && result.Assembly is null, "Invalid source returned a DLL.");
        var error = result.Diagnostics.First(item => item.Code == "CS0246");
        Check.Assert(error.File == "authors/problem.cs" && error.Line == 4 && error.Column == 5,
            $"Expected actual source 4:5, got {error.File} {error.Line}:{error.Column}.");
    }

    private static void UnsafeRejected()
    {
        var result = Compile(new SourceFile("unsafe.cs", "public unsafe class PointerScript { public int* Pointer; }"));
        Check.Assert(!result.Succeeded && result.Assembly is null, "Unsafe source was accepted.");
        Check.Assert(result.Diagnostics.Any(item => item.Code == "CS0227"), "Unsafe rejection lacks an actionable C# diagnostic.");
    }

    private static void UnapprovedReference()
    {
        var result = Compile(new SourceFile("references.cs", "public sealed class Sneak { public RuneCLR.Compiler.SourceFile? Source; }"));
        Check.Assert(!result.Succeeded && result.Assembly is null, "Compiler implicitly exposed a host-loaded assembly.");
        Check.Assert(result.Diagnostics.Any(item => item.Severity == "Error"), "Missing reference had no author diagnostic.");
    }

    private static void ScriptDirectives()
    {
        foreach (var directive in new[] { "#r \"unapproved.dll\"", "#load \"unapproved.cs\"" })
        {
            var result = Compile(new SourceFile("directives.cs", directive + Environment.NewLine + "public class Script { }"));
            Check.Assert(!result.Succeeded && result.Assembly is null, "Author script directive was accepted.");
            Check.Assert(result.Diagnostics.Any(item => item.File == "directives.cs" && item.Line == 1),
                "Directive rejection did not identify the author source.");
        }
    }

    private static void InvalidNames()
    {
        foreach (var name in new[] { "/absolute.cs", "C:/absolute.cs", "../escape.cs", "a/../escape.cs", "a/./file.cs",
            "a//file.cs", "script.txt", "a" + (char)92 + "file.cs", "" })
        {
            var result = Compile(new SourceFile(name, "public class Script { }"));
            Check.Assert(!result.Succeeded && result.Diagnostics[0].Code == "RC1004", $"Invalid source label accepted: {name}.");
        }
        var duplicates = Compile(new SourceFile("a.cs", "public class A { }"), new("A.cs", "public class B { }"));
        Check.Assert(!duplicates.Succeeded && duplicates.Diagnostics[0].Code == "RC1005", "Duplicate source labels were accepted.");
    }

    private static void InputLimits()
    {
        var tooMany = Enumerable.Range(0, SourceCompiler.MaximumSources + 1)
            .Select(index => new SourceFile($"file{index}.cs", "")).ToArray();
        Check.Assert(Compile(tooMany).Diagnostics[0].Code == "RC1002", "Source count was not bounded.");
        var tooLong = Compile(new SourceFile("large.cs", new string(' ', SourceCompiler.MaximumSourceCharacters + 1)));
        Check.Assert(!tooLong.Succeeded && tooLong.Diagnostics[0].Code == "RC1007", "Source text was not bounded.");
        var errors = Compile(new SourceFile("errors.cs", string.Join(Environment.NewLine,
            Enumerable.Range(0, 180).Select(index => $"public class E{index} {{ Missing{index} value; }}"))));
        Check.Assert(!errors.Succeeded && errors.Diagnostics.Length is > 0 and <= SourceCompiler.MaximumDiagnostics,
            "Author diagnostic count was not bounded.");
        Check.Assert(errors.Diagnostics.All(item => item.Message.Length <= 1_024), "Diagnostic messages were not bounded.");
        var longDiagnostic = Compile(new SourceFile("long-diagnostic.cs", "public class LongDiagnostic { "
            + new string('X', 2_000) + " value; }"));
        Check.Assert(!longDiagnostic.Succeeded && longDiagnostic.Diagnostics.Any(item => item.Message.Length == 1_024),
            "A long compiler diagnostic was not truncated to the configured bound.");
    }

    private static void MissingReference()
    {
        var result = SourceCompiler.Compile("MissingReference", [new("script.cs", "public class Script { }")],
            [Path.Combine(Path.GetTempPath(), "RuneCLR-missing-" + Guid.NewGuid().ToString("N") + ".dll")]);
        Check.Assert(!result.Succeeded && result.Assembly is null && result.Diagnostics[0].Code == "RC1008",
            "Missing reference should produce a controlled diagnostic.");
        Check.Assert(!result.Diagnostics[0].Message.Contains(Path.GetTempPath(), StringComparison.OrdinalIgnoreCase),
            "Reference diagnostic exposes a server machine path.");
    }

    private static void ModernLanguage()
    {
        var result = Compile(new SourceFile("new-language.cs", """
            using System.Collections.Generic;
            public sealed class NewLanguage
            {
                public int Value { get; set => field = value; }
                public static int Sum(params List<int> values)
                {
                    int sum = 0;
                    foreach (int value in values) sum += value;
                    return sum;
                }
                public void SetValue() => Value = Sum(20, 22);
            }
            """));
        Check.Assert(result.Succeeded,
            $"C# 13 params collections and C# 14 field properties must compile (C# {SourceCompiler.LanguageVersion}): "
            + string.Join("; ", result.Diagnostics.Select(item => item.Message)));
    }
}

