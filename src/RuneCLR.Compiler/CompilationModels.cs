using RuneCLR.Packages;

namespace RuneCLR.Compiler;

public sealed record SourceFile(string Name, string Text);
public sealed record CompilationDiagnostic(string Code, string Message, string Severity,
    string? File = null, int? Line = null, int? Column = null);
public sealed record CompilationResult(byte[]? Assembly, CompilationDiagnostic[] Diagnostics,
    InputIdentity[] CompilerIdentities)
{
    public bool Succeeded => Assembly is not null;
}
