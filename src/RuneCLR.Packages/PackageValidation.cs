using System.Reflection;
using System.Security.Cryptography;

namespace RuneCLR.Packages;

public static class PackageValidator
{
    public const int MaximumFiles = 256;
    public const long MaximumAssemblyBytes = 32 * 1024 * 1024;
    public const long MaximumPackageBytes = 128 * 1024 * 1024;
    private const string ContractName = "RuneCLR.Abstractions";

    // Integrity/provenance validation, not authentication or runtime isolation.
    // The caller owns an immutable package directory; filesystem races are not
    // a supported concurrent package-update mechanism.
    public static void Validate(PackageManifest manifest, string manifestPath)
    {
        ArgumentNullException.ThrowIfNull(manifest);
        if (manifest.FormatVersion != PackageFormat.CurrentVersion ||
            manifest.ApiVersion != PackageFormat.CurrentApiVersion || manifest.InputProfile != PackageFormat.InputProfile)
            throw new InvalidDataException("Unsupported package format, API version or input profile.");
        Text(manifest.Id, "id", 128);
        Text(manifest.EntryType, "entryType", 1024);
        Hash(manifest.EntrySha256);
        Hash(manifest.ContentSha256);
        if (manifest.Files is null || manifest.Dependencies is null || manifest.Producer is null ||
            manifest.Files.Length == 0 || manifest.Files.Length > MaximumFiles || manifest.Dependencies.Length >= MaximumFiles)
            throw new InvalidDataException("The package requires bounded files, dependencies and producer metadata.");
        ValidateProducer(manifest.Producer);
        var root = Path.GetDirectoryName(Path.GetFullPath(manifestPath))!;
        var expected = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        AddPath(expected, manifest.EntryAssembly, manifest.EntrySha256);
        var privateNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var dependency in manifest.Dependencies)
        {
            if (dependency is null) throw new InvalidDataException("Null package dependency.");
            AddPath(expected, dependency.Path, dependency.Sha256);
            var identity = ParseIdentity(dependency.AssemblyName);
            if (identity.Name == ContractName || !privateNames.Add(identity.Name!))
                throw new InvalidDataException("The package includes a contract or duplicate private assembly identity.");
        }
        var listed = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var file in manifest.Files)
        {
            if (file is null) throw new InvalidDataException("Null package file.");
            AddPath(listed, file.Path, file.Sha256);
        }
        if (listed.Count != expected.Count || expected.Any(item => !listed.Keys.Contains(item.Key, StringComparer.Ordinal) ||
            !listed.TryGetValue(item.Key, out var hash) ||
            !string.Equals(hash, item.Value, StringComparison.OrdinalIgnoreCase)))
            throw new InvalidDataException("The file list must exactly match the entry and private dependencies.");
        if (!string.Equals(PackageManifestIO.ComputeContentSha256(manifest), manifest.ContentSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("The package content identity does not match the manifest.");
        var actualFiles = EnumerateFiles(root).Where(path =>
            !string.Equals(Path.GetFullPath(path), Path.GetFullPath(manifestPath), StringComparison.Ordinal))
            .Select(path => Path.GetRelativePath(root, path).Replace(Path.DirectorySeparatorChar, '/'))
            .Take(MaximumFiles + 1).ToArray();
        if (actualFiles.Length != listed.Count || actualFiles.Any(path => !listed.Keys.Contains(path, StringComparer.Ordinal)))
            throw new InvalidDataException("The package contains missing or extra files.");
        long totalBytes = 0;
        var assemblies = new Dictionary<string, ManagedAssemblyInfo>(StringComparer.OrdinalIgnoreCase);
        var images = new List<byte[]>();
        var bytesByPath = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase);
        byte[]? entryBytes = null;
        foreach (var file in manifest.Files)
        {
            var path = Path.Combine(root, file.Path);
            var length = new FileInfo(path).Length;
            totalBytes += length;
            if (length > MaximumAssemblyBytes || totalBytes > MaximumPackageBytes)
                throw new InvalidDataException("The package exceeds the assembly/content size limits.");
            var bytes = File.ReadAllBytes(path);
            if (!string.Equals(Convert.ToHexString(SHA256.HashData(bytes)), file.Sha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"Package file hash mismatch: {file.Path}.");
            var info = ManagedAssemblyInspector.Inspect(bytes);
            images.Add(bytes);
            if (string.Equals(info.SimpleName, ContractName, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("The shared host contract cannot be packaged as script code.");
            assemblies.Add(file.Path, info);
            bytesByPath.Add(file.Path, bytes);
            if (file.Path == manifest.EntryAssembly) entryBytes = bytes;
        }
        foreach (var dependency in manifest.Dependencies)
            if (!string.Equals(assemblies[dependency.Path].AssemblyName, dependency.AssemblyName, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"Dependency metadata identity mismatch: {dependency.Path}.");
        if (privateNames.Contains(assemblies[manifest.EntryAssembly].SimpleName))
            throw new InvalidDataException("A private dependency duplicates the entry assembly identity.");
        var contract = manifest.Producer.References.Where(input => input.AssemblyName is not null &&
            string.Equals(ParseIdentity(input.AssemblyName).Name, ContractName, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (contract.Length != 1) throw new InvalidDataException("Producer references must identify exactly one shared host contract.");
        ManagedAssemblyInspector.ValidateEntry(entryBytes!, manifest.EntryType, contract[0].AssemblyName!);
        if (manifest.HostInterface is not null || manifest.AllowedMethods is not null)
        {
            if (string.IsNullOrWhiteSpace(manifest.HostInterface) || manifest.AllowedMethods is null ||
                manifest.AllowedMethods.Length == 0 || manifest.AllowedMethods.Any(string.IsNullOrWhiteSpace) ||
                manifest.AllowedMethods.Distinct(StringComparer.Ordinal).Count() != manifest.AllowedMethods.Length)
                throw new InvalidDataException("The host interface and allowed methods must both be present, nonempty and unique.");
            var privateImages = manifest.Dependencies.Select(dependency => bytesByPath[dependency.Path]).ToArray();
            GameplayCapabilityPolicy.ValidateHostContract(entryBytes!, manifest.EntryType, manifest.HostInterface, manifest.AllowedMethods, privateImages);
        }
        // Recompute the policy from actual IL at load time, not producer claims.
        var scriptIdentities = assemblies.Values.Select(info => info.AssemblyName).ToArray();
        foreach (var image in images)
            GameplayCapabilityPolicy.Validate(image, scriptIdentities, contract[0].AssemblyName!);
    }

    public static string ResolvePath(string directory, string relativePath)
    {
        ValidatePath(relativePath);
        return Path.Combine(Path.GetFullPath(directory), relativePath);
    }

    private static void AddPath(Dictionary<string, string> paths, string path, string hash)
    {
        ValidatePath(path);
        Hash(hash);
        if (!paths.TryAdd(path, hash)) throw new InvalidDataException($"Duplicate package path: {path}.");
    }

    private static void ValidatePath(string path)
    {
        Text(path, "path", 240);
        if (Path.IsPathRooted(path) || path.Contains((char)92) || path.Contains(':') ||
            path.Any(character => character < 32 || "<>\"|?*".Contains(character)) ||
            path.Split('/').Any(part => part is "" or "." or ".." || part.EndsWith(' ') || part.EndsWith('.')) ||
            !path.EndsWith(".dll", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Package content paths must be canonical relative DLL paths using forward slashes.");
    }

    private static void ValidateProducer(PackageProducer producer)
    {
        Text(producer.Tool, "producer.tool", 128);
        Text(producer.ToolVersion, "producer.toolVersion", 128);
        if (producer.InputKind is not ("source" or "il")) throw new InvalidDataException("Unsupported producer input kind.");
        Inputs(producer.Compiler, producer.InputKind == "source", "compiler");
        Inputs(producer.References, required: true, "references");
        Inputs(producer.Sources, required: true, "sources");
    }

    private static void Inputs(InputIdentity[] inputs, bool required, string category)
    {
        if (inputs is null || inputs.Length > MaximumFiles || (required && inputs.Length == 0))
            throw new InvalidDataException($"Producer {category} identities are required and bounded.");
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var input in inputs)
        {
            if (input is null) throw new InvalidDataException("Null producer input identity.");
            Text(input.Name, "input name", 1024);
            Hash(input.Sha256);
            if (!names.Add(input.Name)) throw new InvalidDataException($"Duplicate producer {category} input name.");
            if (input.AssemblyName is not null) _ = ParseIdentity(input.AssemblyName);
        }
    }

    private static AssemblyName ParseIdentity(string identity)
    {
        Text(identity, "assembly identity", 4096);
        try
        {
            var name = new AssemblyName(identity);
            if (name.Version is null || name.Name is null ||
                !string.Equals(name.FullName, identity, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("A full canonical assembly identity is required.");
            return name;
        }
        catch (ArgumentException exception) { throw new InvalidDataException("Invalid assembly identity.", exception); }
        catch (FileLoadException exception) { throw new InvalidDataException("Invalid assembly identity.", exception); }
    }

    private static IEnumerable<string> EnumerateFiles(string directory, int depth = 0)
    {
        if (depth > 16) throw new InvalidDataException("Package directories exceed the nesting limit.");
        foreach (var path in Directory.EnumerateFileSystemEntries(directory))
        {
            var attributes = File.GetAttributes(path);
            if ((attributes & FileAttributes.ReparsePoint) != 0) throw new InvalidDataException("Package content cannot contain filesystem links.");
            if ((attributes & FileAttributes.Directory) != 0)
            {
                foreach (var file in EnumerateFiles(path, depth + 1)) yield return file;
            }
            else yield return path;
        }
    }

    private static void Hash(string hash)
    {
        if (hash is null || hash.Length != 64 || !hash.All(Uri.IsHexDigit))
            throw new InvalidDataException("Each content/input identity requires a SHA-256 hexadecimal digest.");
    }

    private static void Text(string value, string field, int maximumLength)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Length > maximumLength)
            throw new InvalidDataException($"Missing or oversized {field}.");
    }
}
