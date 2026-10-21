using System.Reflection;
using System.Text.Json;
using RuneCLR.Packages;

namespace RuneCLR.Runtime;

public sealed record MapPackage(string Id, string AssemblyPath, string EntryType)
{
    private static readonly HashSet<string> VersionedFields = new(StringComparer.OrdinalIgnoreCase)
    {
        "formatVersion", "apiVersion", "inputProfile", "files", "producer", "contentSha256"
    };
    public IReadOnlyList<MapDependency> Dependencies { get; init; } = Array.Empty<MapDependency>();

    // Optional for the existing trusted local fixtures; distributed packages should supply it.
    public string? EntrySha256 { get; init; }

    internal string? ManifestDirectory { get; init; }
    internal string? VersionedManifestPath { get; init; }
    internal PackageManifest? VersionedSnapshot { get; init; }

    public static MapPackage FromManifest(string manifestPath)
    {
        var fullPath = Path.GetFullPath(manifestPath);
        if (new FileInfo(fullPath).Length > PackageManifestIO.MaximumManifestBytes)
            throw new InvalidDataException("The package manifest exceeds the size limit.");
        using (var probeStream = File.OpenRead(fullPath))
        using (var probe = JsonDocument.Parse(probeStream, new JsonDocumentOptions { MaxDepth = 32 }))
        {
            if (probe.RootElement.ValueKind == JsonValueKind.Object && probe.RootElement.EnumerateObject().Any(
                property => VersionedFields.Contains(property.Name)))
                return FromVersionedManifest(fullPath);
        }
        using var stream = File.OpenRead(fullPath);
        var manifest = JsonSerializer.Deserialize<Manifest>(stream, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        }) ?? throw new InvalidDataException("The map manifest is empty.");

        ArgumentException.ThrowIfNullOrWhiteSpace(manifest.Id);
        ArgumentException.ThrowIfNullOrWhiteSpace(manifest.EntryAssembly);
        ArgumentException.ThrowIfNullOrWhiteSpace(manifest.EntryType);

        var directory = Path.GetDirectoryName(fullPath)!;
        var assemblyPath = ResolvePackagePath(directory, manifest.EntryAssembly);
        var package = new MapPackage(manifest.Id, assemblyPath, manifest.EntryType)
        {
            Dependencies = manifest.Dependencies ?? Array.Empty<MapDependency>(),
            EntrySha256 = manifest.EntrySha256,
            ManifestDirectory = directory
        };
        // Validate before a collectible context is created. Direct constructor callers
        // receive the same checks when MapRunner starts a session.
        _ = new MapDependencyResolver(package);
        return package;
    }

    private static MapPackage FromVersionedManifest(string path)
    {
        var manifest = PackageManifestIO.Read(path);
        RejectHostDefinedContract(manifest);
        PackageValidator.Validate(manifest, path);
        var directory = Path.GetDirectoryName(path)!;
        var package = new MapPackage(manifest.Id, PackageValidator.ResolvePath(directory, manifest.EntryAssembly), manifest.EntryType)
        {
            Dependencies = manifest.Dependencies.Select(dependency => new MapDependency(
                dependency.Path, dependency.AssemblyName, dependency.Sha256)).ToArray(),
            EntrySha256 = manifest.EntrySha256, ManifestDirectory = directory,
            VersionedManifestPath = path, VersionedSnapshot = manifest
        };
        _ = new MapDependencyResolver(package);
        return package;
    }

    internal void ValidateVersionedSnapshot()
    {
        if (VersionedSnapshot is null) return;
        var original = VersionedSnapshot;
        RejectHostDefinedContract(original);
        // Provenance records describe compiler inputs, but do not define the
        // actual host contract. Reject incompatible versioned inputs before
        // creating an ALC; reference image hashes need not equal host R2R bytes.
        var hostIdentity = typeof(IMapScript).Assembly.GetName();
        var recordedContract = original.Producer.References.Single(input => input.AssemblyName is not null &&
            string.Equals(new AssemblyName(input.AssemblyName).Name, hostIdentity.Name, StringComparison.OrdinalIgnoreCase));
        try { MapDependencyResolver.RequireIdentity(new AssemblyName(recordedContract.AssemblyName!), hostIdentity); }
        catch (FileLoadException exception)
        {
            throw new InvalidDataException("The versioned package references an incompatible host contract.", exception);
        }
        if (VersionedManifestPath is null || ManifestDirectory is null || Dependencies is null ||
            Id != original.Id || EntryType != original.EntryType || EntrySha256 != original.EntrySha256 ||
            AssemblyPath != PackageValidator.ResolvePath(ManifestDirectory, original.EntryAssembly) ||
            Dependencies.Count != original.Dependencies.Length ||
            !Dependencies.SequenceEqual(original.Dependencies.Select(dependency => new MapDependency(
                dependency.Path, dependency.AssemblyName, dependency.Sha256))))
            throw new InvalidDataException("A versioned package cannot be modified after manifest validation.");
        var current = PackageManifestIO.Read(VersionedManifestPath);
        PackageValidator.Validate(current, VersionedManifestPath);
        if (!string.Equals(current.ContentSha256, original.ContentSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("The versioned manifest changed after package creation.");
    }

    private static void RejectHostDefinedContract(PackageManifest manifest)
    {
        if (!string.IsNullOrWhiteSpace(manifest.HostInterface) &&
            !string.Equals(manifest.HostInterface, "RuneCLR.IMapContext", StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "This package uses a host-defined contract. Open it with HostContractSession.");
        }
    }
    internal static string ResolvePackagePath(string directory, string path)
    {
        if (string.IsNullOrWhiteSpace(path) || Path.IsPathRooted(path) ||
            path.Contains('\\') || path.Contains(':'))
        {
            throw new InvalidDataException("Package assembly paths must be relative and use forward slashes.");
        }

        var fullPath = Path.GetFullPath(path, directory);
        var relativePath = Path.GetRelativePath(directory, fullPath);
        if (relativePath == ".." || relativePath.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal))
        {
            throw new InvalidDataException("Package assembly paths must stay inside the map directory.");
        }

        return fullPath;
    }

    private sealed record Manifest(string Id, string EntryAssembly, string EntryType,
        MapDependency[]? Dependencies = null, string? EntrySha256 = null);
}
