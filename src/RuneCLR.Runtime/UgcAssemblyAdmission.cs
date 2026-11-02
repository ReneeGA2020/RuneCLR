using System.Reflection;
using System.Runtime.Loader;
using System.Security.Cryptography;
using RuneCLR.Packages;

namespace RuneCLR.Runtime;

// Exact bytes or a declared path source consumed by the interpreter-required binder.
// Names locate dependencies; only host-supplied assembly instances are shared as trusted code.
internal sealed record UgcAssemblySource(string Name, string Identity, string? Path, byte[]? Bytes, string? Sha256);

internal sealed class UgcAssemblyAdmission
{
    private readonly IApiAccessPolicy _policy;
    private readonly Dictionary<string, Assembly> _shared = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, UgcAssemblySource> _sources = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, string> _paths = new(StringComparer.OrdinalIgnoreCase);
    private readonly HashSet<string> _directories = new(OperatingSystem.IsWindows() ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal);
    private readonly HashSet<string> _identities = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, string> _expectedHashes = new(OperatingSystem.IsWindows() ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal);
    private readonly string _contract;

    internal UgcAssemblyAdmission(IApiAccessPolicy policy, MapPackage package, IReadOnlyList<Assembly> shared)
        : this(policy, typeof(IMapScript).Assembly, PackageSources(package), shared)
    {
    }

    internal UgcAssemblyAdmission(IApiAccessPolicy policy, Assembly contract,
        IReadOnlyList<UgcAssemblySource> sources, IReadOnlyList<Assembly> shared)
    {
        ArgumentNullException.ThrowIfNull(policy);
        ArgumentNullException.ThrowIfNull(contract);
        ArgumentNullException.ThrowIfNull(sources);
        ArgumentNullException.ThrowIfNull(shared);
        _policy = policy;
        _contract = contract.FullName!;
        _shared.Add(contract.GetName().Name!, contract);
        foreach (var assembly in shared)
        {
            if (assembly is null || assembly.IsDynamic || AssemblyLoadContext.GetLoadContext(assembly) != AssemblyLoadContext.Default ||
                !_shared.TryAdd(assembly.GetName().Name!, assembly))
                throw new ArgumentException("Shared assemblies must be unique, existing default-context assemblies.");
        }
        foreach (var source in sources)
        {
            AddSource(source);
            _identities.Add(source.Identity);
        }
    }

    private static IReadOnlyList<UgcAssemblySource> PackageSources(MapPackage package)
    {
        var entryPath = Path.GetFullPath(package.AssemblyPath);
        var entry = AssemblyName.GetAssemblyName(entryPath);
        var result = new List<UgcAssemblySource>
        {
            new(entry.Name!, entry.FullName!, entryPath, null, package.EntrySha256)
        };
        var directory = package.ManifestDirectory ?? Path.GetDirectoryName(entryPath)!;
        foreach (var dependency in package.Dependencies)
        {
            var path = MapPackage.ResolvePackagePath(directory, dependency.Path);
            var identity = AssemblyName.GetAssemblyName(path);
            result.Add(new UgcAssemblySource(identity.Name!, identity.FullName!, path, null, dependency.Sha256));
        }
        return result;
    }

    private void AddSource(UgcAssemblySource source)
    {
        if (source is null || string.IsNullOrWhiteSpace(source.Name) || string.IsNullOrWhiteSpace(source.Identity) ||
            (source.Path is null && source.Bytes is null))
            throw new ArgumentException("Each UGC assembly source requires a simple name, identity and bytes or path.");
        if (!_sources.TryAdd(source.Name, source))
            throw new InvalidDataException("Duplicate UGC assembly source identity: " + source.Name + ".");
        if (_shared.ContainsKey(source.Name) || MapDependencyResolver.IsFrameworkName(source.Name))
            throw new InvalidDataException("UGC source cannot shadow a framework or shared assembly identity: " + source.Name + ".");
        if (source.Path is null) return;
        _paths[source.Name] = source.Path;
        _directories.Add(Path.GetDirectoryName(source.Path)!);
        if (source.Sha256 is not null)
            _expectedHashes[source.Path] = source.Sha256;
    }

    internal void Admit(byte[] image, string? sourcePath)
    {
        if (sourcePath is not null && _expectedHashes.TryGetValue(Path.GetFullPath(sourcePath), out var expected) &&
            !HashMatches(image, expected))
            throw new InvalidDataException("Assembly bytes no longer match the package's declared SHA-256.");
        var info = ManagedAssemblyInspector.Inspect(image);
        if (_shared.ContainsKey(info.SimpleName))
            throw new InvalidDataException("UGC bytes cannot replace a host-supplied shared assembly instance.");
        var identities = _identities.Append(info.AssemblyName).ToArray();
        GameplayCapabilityPolicy.ValidateWithApiPolicy(image, identities, _contract, _policy,
            allowReflectionTypeTokens: true, allowSessionAssemblyNames: true);
        _identities.Add(info.AssemblyName);
        if (sourcePath is not null)
        {
            _directories.Add(Path.GetDirectoryName(Path.GetFullPath(sourcePath))!);
            _paths[info.SimpleName] = Path.GetFullPath(sourcePath);
        }
    }

    internal Assembly? Resolve(AssemblyLoadContext context, AssemblyName requested)
    {
        string name = requested.Name ?? throw new FileLoadException("An assembly simple name is required.");
        if (_shared.TryGetValue(name, out var shared))
        {
            MapDependencyResolver.RequireIdentity(requested, shared.GetName());
            return shared;
        }
        if (name != Path.GetFileName(name) || name.Contains('/') || name.Contains((char)92) || name.Contains(':'))
            throw new FileLoadException("An assembly simple name cannot contain a path.");
        if (MapDependencyResolver.IsFrameworkName(name)) return null;
        if (_sources.TryGetValue(name, out var source))
        {
            MapDependencyResolver.RequireIdentity(requested, new AssemblyName(source.Identity));
            if (source.Bytes is not null)
            {
                if (source.Sha256 is not null && !HashMatches(source.Bytes, source.Sha256))
                    throw new InvalidDataException("UGC assembly bytes no longer match the declared SHA-256.");
                return context.LoadFromStream(new MemoryStream(source.Bytes, writable: false));
            }
            return context.LoadFromAssemblyPath(source.Path!);
        }
        string? path = _paths.GetValueOrDefault(name);
        if (path is null)
            path = _directories.Select(directory => Path.Combine(directory, name + ".dll")).FirstOrDefault(File.Exists);
        if (path is null) throw new FileNotFoundException("No UGC dependency was found: " + requested.FullName);
        MapDependencyResolver.RequireIdentity(requested, AssemblyName.GetAssemblyName(path));
        return context.LoadFromAssemblyPath(path);
    }

    private static bool HashMatches(byte[] image, string expected) =>
        expected.Length == 64 && expected.All(Uri.IsHexDigit) &&
        string.Equals(Convert.ToHexString(SHA256.HashData(image)), expected, StringComparison.OrdinalIgnoreCase);
}
