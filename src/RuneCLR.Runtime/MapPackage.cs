using System.Text.Json;

namespace RuneCLR.Runtime;

public sealed record MapPackage(string Id, string AssemblyPath, string EntryType)
{
    public static MapPackage FromManifest(string manifestPath)
    {
        var fullPath = Path.GetFullPath(manifestPath);
        using var stream = File.OpenRead(fullPath);
        var manifest = JsonSerializer.Deserialize<Manifest>(stream, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        }) ?? throw new InvalidDataException("The map manifest is empty.");

        ArgumentException.ThrowIfNullOrWhiteSpace(manifest.Id);
        ArgumentException.ThrowIfNullOrWhiteSpace(manifest.EntryAssembly);
        ArgumentException.ThrowIfNullOrWhiteSpace(manifest.EntryType);

        if (Path.IsPathRooted(manifest.EntryAssembly))
        {
            throw new InvalidDataException("entryAssembly must be relative to the manifest.");
        }

        var directory = Path.GetDirectoryName(fullPath)!;
        var assemblyPath = Path.GetFullPath(manifest.EntryAssembly, directory);
        var relativePath = Path.GetRelativePath(directory, assemblyPath);
        if (relativePath == ".." || relativePath.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal))
        {
            throw new InvalidDataException("entryAssembly must stay inside the map directory.");
        }

        if (!File.Exists(assemblyPath))
        {
            throw new FileNotFoundException("The map entry assembly does not exist.", assemblyPath);
        }

        return new MapPackage(manifest.Id, assemblyPath, manifest.EntryType);
    }

    private sealed record Manifest(string Id, string EntryAssembly, string EntryType);
}
