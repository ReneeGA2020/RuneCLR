using System.Security.Cryptography;
using System.Text.Json;

// A package directory owned by one test. Copy only explicit IL artifacts, so a
// passing resolver test cannot rely on a generated desktop .deps.json file.
internal sealed class TemporaryMapPackage : IDisposable
{
    public string DirectoryPath { get; } = Path.Combine(
        Path.GetTempPath(), $"runeclr-package-test-{Guid.NewGuid():N}");

    public TemporaryMapPackage() => Directory.CreateDirectory(DirectoryPath);

    public string CopyAssembly(string fixture, string fileName, string? destinationName = null) =>
        CopyFile(Path.Combine(AppContext.BaseDirectory, fixture, fileName), destinationName);

    public string CopyFile(string source, string? destinationName = null)
    {
        var destination = Path.Combine(DirectoryPath, destinationName ?? Path.GetFileName(source));
        File.Copy(source, destination);
        return destination;
    }

    public string WriteManifest(object manifest)
    {
        var path = Path.Combine(DirectoryPath, "map.json");
        File.WriteAllText(path, JsonSerializer.Serialize(manifest));
        return path;
    }

    public static string Sha256(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream));
    }

    public void Dispose() => Directory.Delete(DirectoryPath, recursive: true);
}
