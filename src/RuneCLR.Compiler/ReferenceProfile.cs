using System.Reflection;
using System.Security.Cryptography;
using RuneCLR.Packages;

namespace RuneCLR.Compiler;

/// <summary>Operator-selected trusted reference bytes; never read from an author configuration.</summary>
public sealed class ReferenceProfile
{
    public static IReadOnlyList<string> FrameworkNames { get; } = Array.AsReadOnly(new[]
        { "System.Runtime", "System.Collections", "System.Linq", "System.ObjectModel", "System.Runtime.Extensions" });
    internal ReferenceImage[] Images { get; }
    public string ContractIdentity { get; }

    public ReferenceProfile(string frameworkReferenceDirectory, string contractAssemblyPath)
        : this(frameworkReferenceDirectory, contractAssemblyPath, requireAbstractions: true)
    {
    }

    public ReferenceProfile(string frameworkReferenceDirectory, string contractAssemblyPath, bool requireAbstractions)
    {
        Images = FrameworkNames.Select(name => Read(Path.Combine(frameworkReferenceDirectory, name + ".dll"), name))
            .Append(Read(contractAssemblyPath, requireAbstractions ? "RuneCLR.Abstractions" : null)).ToArray();
        var actualName = new AssemblyName(Images[^1].Identity.AssemblyName!).Name;
        if (requireAbstractions)
        {
            if (actualName != "RuneCLR.Abstractions")
                throw new InvalidDataException("The operator must supply the approved RuneCLR.Abstractions contract.");
        }
        else if (string.IsNullOrEmpty(actualName) || FrameworkNames.Contains(actualName, StringComparer.OrdinalIgnoreCase))
        {
            throw new InvalidDataException("The operator must supply one shared host contract assembly.");
        }

        ContractIdentity = Images[^1].Identity.AssemblyName!;
    }

    private static ReferenceImage Read(string path, string? expectedName)
    {
        var info = new FileInfo(path);
        if (!info.Exists || info.Length is < 1 or > 32 * 1024 * 1024)
            throw new InvalidDataException("An approved reference is missing or exceeds 32 MiB.");
        var bytes = File.ReadAllBytes(path);
        // Trusted references can contain reference-only bodies. Do not apply author-IL rules here.
        using var pe = new System.Reflection.PortableExecutable.PEReader(new MemoryStream(bytes));
        if (!pe.HasMetadata) throw new InvalidDataException("An approved reference has no managed metadata.");
        var metadata = System.Reflection.Metadata.PEReaderExtensions.GetMetadataReader(pe);
        if (!metadata.IsAssembly) throw new InvalidDataException("An approved reference is not an assembly.");
        var definition = metadata.GetAssemblyDefinition();
        if (expectedName is not null && !string.Equals(metadata.GetString(definition.Name), expectedName, StringComparison.Ordinal))
            throw new InvalidDataException("An approved reference does not match its fixed profile assembly name.");
        var name = new AssemblyName
        {
            Name = metadata.GetString(definition.Name), Version = definition.Version,
            CultureName = metadata.GetString(definition.Culture),
            Flags = (AssemblyNameFlags)(definition.Flags & System.Reflection.AssemblyFlags.Retargetable),
            ContentType = (definition.Flags & System.Reflection.AssemblyFlags.WindowsRuntime) != 0
                ? AssemblyContentType.WindowsRuntime : AssemblyContentType.Default
        };
        name.SetPublicKey(metadata.GetBlobBytes(definition.PublicKey));
        return new(bytes, new(Path.GetFileName(path), Hash(bytes), name.FullName));
    }

    internal static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    internal sealed record ReferenceImage(byte[] Bytes, InputIdentity Identity);
}
