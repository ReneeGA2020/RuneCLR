namespace RuneCLR.Packages;

public static class PackageFormat
{
    public const int CurrentVersion = 1;
    public const int CurrentApiVersion = 1;
    public const string InputProfile = GameplayCapabilityPolicy.Profile;
    public const string ManifestFileName = "package.json";
}

public sealed record PackageFile(string Path, string Sha256);
public sealed record PackageDependency(string Path, string AssemblyName, string Sha256);
public sealed record InputIdentity(string Name, string Sha256, string? AssemblyName = null);
public sealed record PackageProducer(string Tool, string ToolVersion, string InputKind,
    InputIdentity[] Compiler, InputIdentity[] References, InputIdentity[] Sources);

public sealed record PackageManifest(int FormatVersion, int ApiVersion, string InputProfile,
    string Id, string EntryAssembly, string EntryType, string EntrySha256,
    PackageDependency[] Dependencies, PackageFile[] Files, PackageProducer Producer,
    string ContentSha256);
