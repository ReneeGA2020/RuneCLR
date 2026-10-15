namespace RuneCLR.Runtime;

/// <summary>A private managed assembly declared by the map package.</summary>
/// <param name="Path">Path relative to the package directory.</param>
/// <param name="AssemblyName">Full assembly identity, including version, culture and public-key token.</param>
/// <param name="Sha256">Hexadecimal SHA-256 of the packaged file.</param>
public sealed record MapDependency(string Path, string AssemblyName, string Sha256);
