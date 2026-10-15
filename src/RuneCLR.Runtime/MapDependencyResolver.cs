using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text.Json;

namespace RuneCLR.Runtime;

// Resolves the package's declared files without hostpolicy or loading them into Default.
// Package directories remain trusted/immutable inputs for this prototype; path/hash
// checks alone do not defend against symlink replacement or filesystem races.
internal sealed class MapDependencyResolver
{
    private static readonly Lazy<HashSet<string>> FrameworkNames = new(ReadFrameworkNames);
    private readonly Dictionary<string, Binding> _private = new(StringComparer.OrdinalIgnoreCase);
    private readonly Binding _entry;

    public string EntryPath => _entry.Path;

    public MapDependencyResolver(MapPackage package)
    {
        package.ValidateVersionedSnapshot();
        var entryPath = Path.GetFullPath(package.AssemblyPath);
        _entry = new Binding(entryPath, ReadIdentity(entryPath, package.EntrySha256));
        if (string.Equals(_entry.Identity.Name, typeof(IMapScript).Assembly.GetName().Name, StringComparison.OrdinalIgnoreCase) ||
            FrameworkNames.Value.Contains(_entry.Identity.Name!))
        {
            throw new InvalidDataException("The map entry cannot use a shared contract or framework assembly identity.");
        }
        var directory = package.ManifestDirectory ?? Path.GetDirectoryName(entryPath)!;
        if (package.Dependencies is null)
        {
            throw new InvalidDataException("The dependency list must not be null.");
        }

        foreach (var dependency in package.Dependencies)
        {
            if (dependency is null || string.IsNullOrWhiteSpace(dependency.AssemblyName) ||
                string.IsNullOrWhiteSpace(dependency.Sha256))
            {
                throw new InvalidDataException("Each dependency requires a path, full assembly identity and SHA-256.");
            }

            var path = MapPackage.ResolvePackagePath(directory, dependency.Path);
            var identity = ReadIdentity(path, dependency.Sha256);
            if (!string.Equals(identity.FullName, dependency.AssemblyName, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException($"Dependency identity does not match the packaged file: {dependency.Path}.");
            }

            if (string.Equals(identity.Name, typeof(IMapScript).Assembly.GetName().Name, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(identity.Name, _entry.Identity.Name, StringComparison.OrdinalIgnoreCase) ||
                FrameworkNames.Value.Contains(identity.Name!))
            {
                throw new InvalidDataException($"Dependency identity is reserved by the entry, contract or framework: {identity.Name}.");
            }

            if (!_private.TryAdd(identity.Name!, new Binding(path, identity)))
            {
                throw new InvalidDataException($"Duplicate private dependency identity: {identity.Name}.");
            }
        }
    }

    public string? Resolve(AssemblyName requested)
    {
        var name = requested.Name;
        if (name is not null && _private.TryGetValue(name, out var binding))
        {
            RequireIdentity(requested, binding.Identity);
            return binding.Path;
        }

        if (string.Equals(name, _entry.Identity.Name, StringComparison.OrdinalIgnoreCase))
        {
            RequireIdentity(requested, _entry.Identity);
            return _entry.Path;
        }

        if (name is not null && FrameworkNames.Value.Contains(name))
        {
            // Default owns the trusted framework and its normal version binding.
            return null;
        }

        throw new FileLoadException($"Private dependency is not declared in the map package: {requested.FullName}.");
    }

    internal static void RequireIdentity(AssemblyName requested, AssemblyName actual)
    {
        if (!string.Equals(requested.Name, actual.Name, StringComparison.OrdinalIgnoreCase) ||
            (requested.Version is not null && requested.Version != actual.Version) ||
            !string.Equals(requested.CultureName ?? "", actual.CultureName ?? "", StringComparison.OrdinalIgnoreCase) ||
            !(requested.GetPublicKeyToken() ?? Array.Empty<byte>()).AsSpan().SequenceEqual(
                actual.GetPublicKeyToken() ?? Array.Empty<byte>()))
        {
            throw new FileLoadException($"Assembly identity mismatch. Requested {requested.FullName}; package provides {actual.FullName}.");
        }
    }

    private static AssemblyName ReadIdentity(string path, string? expectedHash)
    {
        using var stream = File.OpenRead(path);
        if (expectedHash is not null)
        {
            if (expectedHash.Length != 64 || !expectedHash.All(Uri.IsHexDigit))
            {
                throw new InvalidDataException($"Invalid SHA-256 for {Path.GetFileName(path)}.");
            }

            var actualHash = Convert.ToHexString(SHA256.HashData(stream));
            if (!string.Equals(actualHash, expectedHash, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException($"SHA-256 mismatch for {Path.GetFileName(path)}.");
            }
            stream.Position = 0;
        }

        using var pe = new PEReader(stream);
        if (!pe.HasMetadata)
        {
            throw new InvalidDataException($"Package file is not a managed assembly: {path}.");
        }
        var metadata = pe.GetMetadataReader();
        if (!metadata.IsAssembly)
        {
            throw new InvalidDataException($"Package file is not an assembly: {path}.");
        }
        var definition = metadata.GetAssemblyDefinition();
        var identity = new AssemblyName
        {
            Name = metadata.GetString(definition.Name),
            Version = definition.Version,
            CultureName = definition.Culture.IsNil ? "" : metadata.GetString(definition.Culture)
        };
        var publicKey = definition.PublicKey.IsNil ? Array.Empty<byte>() : metadata.GetBlobBytes(definition.PublicKey);
        if (publicKey.Length > 0) identity.SetPublicKey(publicKey);
        else identity.SetPublicKeyToken(Array.Empty<byte>());
        return identity;
    }

    private static HashSet<string> ReadFrameworkNames()
    {
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            typeof(object).Assembly.GetName().Name!
        };
        // This is the trusted runtime's inventory, not a map .deps.json. Include it
        // beside the framework/host when packaging a mobile CoreCLR application.
        var directories = new[]
        {
            Path.GetDirectoryName(typeof(object).Assembly.Location), AppContext.BaseDirectory
        };
        var manifest = directories.Where(directory => !string.IsNullOrEmpty(directory))
            .Select(directory => Path.Combine(directory!, "Microsoft.NETCore.App.deps.json"))
            .FirstOrDefault(File.Exists);
        if (manifest is null)
        {
            throw new InvalidDataException("The host must package the trusted Microsoft.NETCore.App.deps.json framework inventory.");
        }
        using var stream = File.OpenRead(manifest);
        using var document = JsonDocument.Parse(stream);
        foreach (var target in document.RootElement.GetProperty("targets").EnumerateObject())
        foreach (var library in target.Value.EnumerateObject())
        {
            if (!library.Name.StartsWith("Microsoft.NETCore.App.Runtime.", StringComparison.Ordinal) &&
                !library.Name.StartsWith("Microsoft.NETCore.App/", StringComparison.Ordinal)) continue;
            if (!library.Value.TryGetProperty("runtime", out var runtime)) continue;
            foreach (var asset in runtime.EnumerateObject())
            {
                if (asset.Name.EndsWith(".dll", StringComparison.OrdinalIgnoreCase))
                    names.Add(Path.GetFileNameWithoutExtension(asset.Name));
            }
        }
        if (names.Count == 1) throw new InvalidDataException("The trusted framework inventory has no managed runtime assets.");
        return names;
    }

    private sealed record Binding(string Path, AssemblyName Identity);
}
