using System.Reflection;
using System.Text;
using RuneCLR.Packages;

namespace RuneCLR.Compiler;

public sealed record PackageBuildResult(string? ManifestPath, CompilationDiagnostic[] Diagnostics)
{
    public bool Succeeded => ManifestPath is not null;
}

/// <summary>Controlled operator-side builder. Hashes record provenance, not approval or sandboxing.</summary>
public static class PackageBuilder
{
    public static PackageBuildResult Compile(string id, string entryType, IReadOnlyList<SourceFile> sources,
        ReferenceProfile profile, string outputDirectory, IReadOnlyList<string>? dependencies = null) =>
        Build(id, entryType, sources, null, profile, outputDirectory, dependencies ?? []);

    public static PackageBuildResult Import(string id, string entryType, string entryAssembly,
        ReferenceProfile profile, string outputDirectory, IReadOnlyList<string>? dependencies = null) =>
        Build(id, entryType, null, entryAssembly, profile, outputDirectory, dependencies ?? []);

    private static PackageBuildResult Build(string id, string entryType, IReadOnlyList<SourceFile>? sources,
        string? entryAssembly, ReferenceProfile profile, string outputDirectory, IReadOnlyList<string> dependencies)
    {
        if (string.IsNullOrWhiteSpace(id) || id.Length > 64 || !id.All(ch => char.IsAsciiLetterOrDigit(ch) || ch is '.' or '_' or '-')
            || id is "." or "..") throw new InvalidDataException("Package id must contain 1-64 ASCII letters, digits, '.', '_' or '-'.");
        ArgumentException.ThrowIfNullOrWhiteSpace(entryType);
        ArgumentNullException.ThrowIfNull(profile);
        if (dependencies.Count > 64) throw new InvalidDataException("At most 64 explicit private dependencies are supported.");
        var destination = Path.GetFullPath(outputDirectory);
        if (Path.Exists(destination)) throw new IOException("Output directory must be new; existing packages are never overwritten.");
        var parent = Path.GetDirectoryName(destination) ?? throw new InvalidDataException("Output requires a parent directory.");
        Directory.CreateDirectory(parent);
        var staging = Path.Combine(parent, ".runeclr-build-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(staging);
        try
        {
            if (dependencies.Sum(path => new FileInfo(path).Length) > PackageValidator.MaximumPackageBytes - PackageValidator.MaximumAssemblyBytes)
                throw new InvalidDataException("Private IL inputs exceed the package size limit.");
            var privateImages = dependencies.Select(ReadInput).ToArray();
            var trusted = profile.Images.Select(image => image.Identity.AssemblyName!).ToHashSet(StringComparer.Ordinal);
            var simpleNames = profile.Images.Select(image => new AssemblyName(image.Identity.AssemblyName!).Name!)
                .ToHashSet(StringComparer.OrdinalIgnoreCase);
            foreach (var image in privateImages)
            {
                if (!simpleNames.Add(image.Info.SimpleName) || Reserved(image.Info.SimpleName))
                    throw new InvalidDataException("Private dependencies cannot duplicate or replace trusted runtime/host assemblies.");
                trusted.Add(image.Info.AssemblyName);
            }

            byte[] entryBytes;
            InputIdentity[] compiler = [];
            InputIdentity[] sourceIdentities;
            if (sources is not null)
            {
                var referenceDirectory = Path.Combine(staging, "references");
                Directory.CreateDirectory(referenceDirectory);
                var references = new List<string>();
                foreach (var image in profile.Images)
                {
                    var path = Path.Combine(referenceDirectory, new AssemblyName(image.Identity.AssemblyName!).Name + ".dll");
                    File.WriteAllBytes(path, image.Bytes); references.Add(path);
                }
                foreach (var image in privateImages)
                {
                    var path = Path.Combine(referenceDirectory, image.Info.SimpleName + ".dll");
                    File.WriteAllBytes(path, image.Bytes); references.Add(path);
                }
                var result = SourceCompiler.Compile(id, sources, references);
                if (!result.Succeeded) return new(null, result.Diagnostics);
                entryBytes = result.Assembly!;
                compiler = result.CompilerIdentities;
                sourceIdentities = sources.Select(source => new InputIdentity(source.Name,
                    ReferenceProfile.Hash(Encoding.UTF8.GetBytes(source.Text)))).ToArray();
            }
            else
            {
                var input = ReadInput(entryAssembly!);
                entryBytes = input.Bytes;
                sourceIdentities = [new("entry.dll", ReferenceProfile.Hash(entryBytes), input.Info.AssemblyName)];
            }
            var entryInfo = ManagedAssemblyInspector.Inspect(entryBytes);
            if (!simpleNames.Add(entryInfo.SimpleName) || Reserved(entryInfo.SimpleName))
                throw new InvalidDataException("Entry assembly duplicates a trusted or private assembly identity.");
            trusted.Add(entryInfo.AssemblyName);
            foreach (var info in privateImages.Select(image => image.Info).Append(entryInfo))
                foreach (var reference in info.References)
                    if (!trusted.Contains(reference))
                        throw new InvalidDataException($"Assembly {info.SimpleName} references an undeclared or unapproved assembly: {reference}.");
            ManagedAssemblyInspector.ValidateEntry(entryBytes, entryType, profile.ContractIdentity);
            var scriptIdentities = privateImages.Select(image => image.Info.AssemblyName)
                .Append(entryInfo.AssemblyName).ToArray();
            foreach (var bytes in privateImages.Select(image => image.Bytes).Append(entryBytes))
                GameplayCapabilityPolicy.Validate(bytes, scriptIdentities, profile.ContractIdentity);
            var packageDirectory = Path.Combine(staging, "package");
            Directory.CreateDirectory(packageDirectory);
            var entryName = id + ".dll";
            var entryHash = ReferenceProfile.Hash(entryBytes);
            File.WriteAllBytes(Path.Combine(packageDirectory, entryName), entryBytes);
            var declared = new List<PackageDependency>();
            var files = new List<PackageFile> { new(entryName, entryHash) };
            foreach (var image in privateImages)
            {
                var path = "lib/" + image.Info.SimpleName + ".dll";
                Directory.CreateDirectory(Path.Combine(packageDirectory, "lib"));
                File.WriteAllBytes(Path.Combine(packageDirectory, path), image.Bytes);
                var hash = ReferenceProfile.Hash(image.Bytes);
                declared.Add(new(path, image.Info.AssemblyName, hash)); files.Add(new(path, hash));
            }
            var privateIdentities = privateImages.Select(image => new InputIdentity(image.Info.SimpleName + ".dll",
                ReferenceProfile.Hash(image.Bytes), image.Info.AssemblyName)).ToArray();
            var producer = new PackageProducer("RuneCLR.PackageTool", "0.1.0", sources is null ? "il" : "source", compiler,
                profile.Images.Select(image => image.Identity).Concat(privateIdentities).ToArray(),
                sourceIdentities.Concat(privateIdentities).ToArray());
            var manifest = new PackageManifest(PackageFormat.CurrentVersion, PackageFormat.CurrentApiVersion,
                PackageFormat.InputProfile, id, entryName, entryType, entryHash, declared.ToArray(), files.ToArray(), producer, "");
            manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
            var stagedManifest = Path.Combine(packageDirectory, PackageFormat.ManifestFileName);
            PackageManifestIO.Write(stagedManifest, manifest);
            PackageValidator.Validate(manifest, stagedManifest);
            Directory.Move(packageDirectory, destination);
            return new(Path.Combine(destination, PackageFormat.ManifestFileName), []);
        }
        finally
        {
            // Delete only this operation's checked sibling staging directory, never the output or input.
            if (Path.GetDirectoryName(Path.GetFullPath(staging)) != parent
                || !Path.GetFileName(staging).StartsWith(".runeclr-build-", StringComparison.Ordinal))
                throw new InvalidOperationException("Invalid build staging cleanup target.");
            Directory.Delete(staging, recursive: true);
        }
    }

    private static bool Reserved(string name) => name.StartsWith("System.", StringComparison.OrdinalIgnoreCase)
        || name.StartsWith("Microsoft.", StringComparison.OrdinalIgnoreCase)
        || new[] { "RuneCLR.Abstractions", "RuneCLR.Runtime", "RuneCLR.Packages", "RuneCLR.Compiler", "RuneCLR.PackageTool" }.Contains(name, StringComparer.OrdinalIgnoreCase)
        || name.Equals("mscorlib", StringComparison.OrdinalIgnoreCase)
        || name.Equals("netstandard", StringComparison.OrdinalIgnoreCase);

    private static InputImage ReadInput(string path)
    {
        var file = new FileInfo(path);
        if (!file.Exists || file.Length is < 1 or > 32 * 1024 * 1024)
            throw new InvalidDataException("An IL input is missing or exceeds 32 MiB.");
        var bytes = File.ReadAllBytes(path);
        return new(bytes, ManagedAssemblyInspector.Inspect(bytes));
    }
    private sealed record InputImage(byte[] Bytes, ManagedAssemblyInfo Info);
}
