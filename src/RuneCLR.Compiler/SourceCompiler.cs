using System.Globalization;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.Text;
using RuneCLR.Packages;

namespace RuneCLR.Compiler;

/// <summary>Compiles author-provided text using only the server's approved references.</summary>
public static class SourceCompiler
{
    public const string LanguageVersion = "12.0";
    public const int MaximumSources = 64;
    public const int MaximumSourceCharacters = 2_000_000;
    public const int MaximumDiagnostics = 100;
    private const int MaximumDiagnosticCharacters = 1_024;
    private const int MaximumReferences = 256;

    public static CompilationResult Compile(string assemblyName, IReadOnlyList<SourceFile> sources,
        IReadOnlyList<string> approvedReferencePaths)
    {
        InputIdentity[] compilerIdentities = [];
        try
        {
            compilerIdentities = [CompilerIdentity(typeof(Compilation).Assembly),
                CompilerIdentity(typeof(CSharpCompilation).Assembly)];
            if (!ValidAssemblyName(assemblyName))
                return Failure("RC1001", "Assembly name must contain 1-128 letters, digits, '.', '_' or '-'.");
            if (sources is null || sources.Count is < 1 or > MaximumSources)
                return Failure("RC1002", $"Supply between 1 and {MaximumSources} source files.");
            if (approvedReferencePaths is null || approvedReferencePaths.Count is < 1 or > MaximumReferences)
                return Failure("RC1003", $"The server must supply 1-{MaximumReferences} approved assembly references.");

            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            long characters = 0;
            foreach (var source in sources)
            {
                if (source is null || !ValidSourceName(source.Name))
                    return Failure("RC1004", "Source names must be relative forward-slash .cs paths without empty, '.' or '..' segments.");
                if (!names.Add(source.Name))
                    return Failure("RC1005", $"Duplicate source name: {Bound(source.Name)}.");
                if (source.Text is null)
                    return Failure("RC1006", $"Source {Bound(source.Name)} requires text.");
                characters += source.Text.Length;
                if (characters > MaximumSourceCharacters)
                    return Failure("RC1007", $"Total source text exceeds {MaximumSourceCharacters} UTF-16 characters.");
            }

            var references = new List<MetadataReference>(approvedReferencePaths.Count);
            for (var index = 0; index < approvedReferencePaths.Count; index++)
            {
                var path = approvedReferencePaths[index];
                try
                {
                    if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
                        return Failure("RC1008", $"Approved reference #{index + 1} is missing; the server must provide a readable managed assembly.");
                    // Snapshot trusted staged bytes now; Roslyn does not reopen a changing reference file.
                    references.Add(MetadataReference.CreateFromImage(File.ReadAllBytes(path),
                        filePath: Path.GetFileName(path)));
                }
                catch (Exception exception) when (exception is IOException or UnauthorizedAccessException
                    or ArgumentException or BadImageFormatException)
                {
                    return Failure("RC1008", $"Approved reference #{index + 1} cannot be read as assembly metadata; check the server reference profile.");
                }
            }

            var parseOptions = new CSharpParseOptions(
                global::Microsoft.CodeAnalysis.CSharp.LanguageVersion.CSharp12,
                DocumentationMode.None, SourceCodeKind.Regular);
            var trees = sources.Select(source => CSharpSyntaxTree.ParseText(
                SourceText.From(source.Text, Encoding.UTF8), parseOptions, source.Name)).ToArray();
            var options = new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary,
                optimizationLevel: OptimizationLevel.Release, allowUnsafe: false,
                platform: Platform.AnyCpu, deterministic: true, nullableContextOptions: NullableContextOptions.Enable,
                metadataReferenceResolver: null, sourceReferenceResolver: null, xmlReferenceResolver: null);
            var compilation = CSharpCompilation.Create(assemblyName, trees, references, options);
            using var output = new MemoryStream();
            var result = compilation.Emit(output); // No PDB, disk output, analyzers or generators.
            var diagnostics = result.Diagnostics
                .Where(diagnostic => diagnostic.Severity is DiagnosticSeverity.Error or DiagnosticSeverity.Warning)
                .Take(MaximumDiagnostics).Select(ConvertDiagnostic).ToArray();
            return new CompilationResult(result.Success ? output.ToArray() : null, diagnostics, compilerIdentities);
        }
        catch (Exception exception) when (exception is not OutOfMemoryException and not StackOverflowException)
        {
            // Internal errors and machine paths are server details, not author-facing diagnostics.
            return Failure("RC1099", "Compilation could not be completed. Check the server compiler installation and approved reference profile.");
        }

        CompilationResult Failure(string code, string message) =>
            new(null, [new CompilationDiagnostic(code, Bound(message), "Error")], compilerIdentities);
    }

    private static bool ValidAssemblyName(string? name) => name is { Length: > 0 and <= 128 }
        && name is not "." and not ".."
        && name.All(character => char.IsLetterOrDigit(character) || character is '.' or '_' or '-');

    private static bool ValidSourceName(string? name) => name is { Length: > 0 and <= 240 }
        && name.EndsWith(".cs", StringComparison.OrdinalIgnoreCase)
        && !name.Any(character => char.IsControl(character) || character == (char)92
            || character is ':' or '*' or '?' or '"' or '<' or '>' or '|')
        && name.Split('/').All(segment => segment.Length > 0 && segment is not "." and not "..");

    private static InputIdentity CompilerIdentity(Assembly assembly) => new(
        assembly.GetName().Name + ".dll",
        Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(assembly.Location))), assembly.FullName);

    private static CompilationDiagnostic ConvertDiagnostic(Diagnostic diagnostic)
    {
        string? file = null;
        int? line = null;
        int? column = null;
        if (diagnostic.Location.IsInSource)
        {
            var span = diagnostic.Location.GetLineSpan(); // Original label; never author's #line remapping.
            file = span.Path;
            line = span.StartLinePosition.Line + 1;
            column = span.StartLinePosition.Character + 1;
        }
        return new CompilationDiagnostic(diagnostic.Id, Bound(diagnostic.GetMessage(CultureInfo.InvariantCulture)),
            diagnostic.Severity.ToString(), file, line, column);
    }

    private static string Bound(string value) => value.Length <= MaximumDiagnosticCharacters
        ? value : value[..MaximumDiagnosticCharacters];
}
