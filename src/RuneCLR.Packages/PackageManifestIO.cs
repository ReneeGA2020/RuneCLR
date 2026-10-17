using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace RuneCLR.Packages;

public static class PackageManifestIO
{
    public const int MaximumManifestBytes = 1024 * 1024;
    private static readonly JsonSerializerOptions ReadOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        RespectRequiredConstructorParameters = true,
        MaxDepth = 32
    };

    public static PackageManifest Read(string path)
    {
        using var stream = File.OpenRead(path);
        var bytes = new byte[MaximumManifestBytes + 1];
        var length = 0;
        while (length < bytes.Length)
        {
            var read = stream.Read(bytes, length, bytes.Length - length);
            if (read == 0) break;
            length += read;
        }
        if (length > MaximumManifestBytes) throw new InvalidDataException("The package manifest exceeds the size limit.");
        try
        {
            using var document = JsonDocument.Parse(bytes.AsMemory(0, length), new JsonDocumentOptions { MaxDepth = 32 });
            RejectDuplicateProperties(document.RootElement);
            return document.RootElement.Deserialize<PackageManifest>(ReadOptions)
                ?? throw new InvalidDataException("The package manifest is empty.");
        }
        catch (JsonException exception)
        {
            throw new InvalidDataException("The package manifest does not match format 1.", exception);
        }
    }

    public static void Write(string path, PackageManifest manifest)
    {
        ArgumentNullException.ThrowIfNull(manifest);
        var bytes = SerializeCanonical(manifest, includeContentHash: true);
        if (bytes.Length > MaximumManifestBytes) throw new InvalidDataException("The package manifest exceeds the size limit.");
        File.WriteAllBytes(path, bytes);
    }

    public static string ComputeContentSha256(PackageManifest manifest) =>
        Convert.ToHexString(SHA256.HashData(SerializeCanonical(manifest, includeContentHash: false)));

    private static void RejectDuplicateProperties(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in element.EnumerateObject())
            {
                if (!names.Add(property.Name)) throw new InvalidDataException($"Duplicate manifest property: {property.Name}.");
                RejectDuplicateProperties(property.Value);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in element.EnumerateArray()) RejectDuplicateProperties(item);
        }
    }

    private static byte[] SerializeCanonical(PackageManifest manifest, bool includeContentHash)
    {
        ArgumentNullException.ThrowIfNull(manifest);
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream))
        {
            writer.WriteStartObject();
            writer.WriteNumber("formatVersion", manifest.FormatVersion);
            writer.WriteNumber("apiVersion", manifest.ApiVersion);
            writer.WriteString("inputProfile", manifest.InputProfile);
            writer.WriteString("id", manifest.Id);
            writer.WriteString("entryAssembly", manifest.EntryAssembly);
            writer.WriteString("entryType", manifest.EntryType);
            writer.WriteString("entrySha256", manifest.EntrySha256);
            if (manifest.HostInterface is not null || manifest.AllowedMethods is not null)
            {
                writer.WriteString("hostInterface", manifest.HostInterface);
                writer.WriteStartArray("allowedMethods");
                foreach (var method in (manifest.AllowedMethods ?? []).OrderBy(item => item, StringComparer.Ordinal))
                    writer.WriteStringValue(method);
                writer.WriteEndArray();
            }
            writer.WriteStartArray("dependencies");
            foreach (var dependency in manifest.Dependencies.OrderBy(item => item.Path, StringComparer.Ordinal))
            {
                writer.WriteStartObject();
                writer.WriteString("path", dependency.Path);
                writer.WriteString("assemblyName", dependency.AssemblyName);
                writer.WriteString("sha256", dependency.Sha256);
                writer.WriteEndObject();
            }
            writer.WriteEndArray();
            writer.WriteStartArray("files");
            foreach (var file in manifest.Files.OrderBy(item => item.Path, StringComparer.Ordinal))
            {
                writer.WriteStartObject();
                writer.WriteString("path", file.Path);
                writer.WriteString("sha256", file.Sha256);
                writer.WriteEndObject();
            }
            writer.WriteEndArray();
            writer.WriteStartObject("producer");
            writer.WriteString("tool", manifest.Producer.Tool);
            writer.WriteString("toolVersion", manifest.Producer.ToolVersion);
            writer.WriteString("inputKind", manifest.Producer.InputKind);
            WriteInputs(writer, "compiler", manifest.Producer.Compiler);
            WriteInputs(writer, "references", manifest.Producer.References);
            WriteInputs(writer, "sources", manifest.Producer.Sources);
            writer.WriteEndObject();
            if (includeContentHash) writer.WriteString("contentSha256", manifest.ContentSha256);
            writer.WriteEndObject();
        }
        return stream.ToArray();
    }

    private static void WriteInputs(Utf8JsonWriter writer, string name, InputIdentity[] inputs)
    {
        writer.WriteStartArray(name);
        foreach (var input in inputs.OrderBy(item => item.Name, StringComparer.Ordinal)
            .ThenBy(item => item.AssemblyName, StringComparer.Ordinal).ThenBy(item => item.Sha256, StringComparer.Ordinal))
        {
            writer.WriteStartObject();
            writer.WriteString("name", input.Name);
            writer.WriteString("sha256", input.Sha256);
            writer.WriteString("assemblyName", input.AssemblyName);
            writer.WriteEndObject();
        }
        writer.WriteEndArray();
    }
}
