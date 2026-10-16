using System.Reflection;
using System.Security.Cryptography;
using RuneCLR;
using RuneCLR.Compiler;
using RuneCLR.Packages;
using RuneCLR.Runtime;

internal static class Fixtures
{
    public static string TestAssembly => Path.Combine(AppContext.BaseDirectory, "fixtures", "RuneCLR.TestMaps.dll");
    public static string ContractAssembly => typeof(IMapScript).Assembly.Location;
    public static string FrameworkReferenceDirectory => Path.Combine(AppContext.BaseDirectory, "refs");
    public static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    public static InputIdentity Identity(string path) => new(Path.GetFileName(path), Hash(File.ReadAllBytes(path)), AssemblyName.GetAssemblyName(path).FullName);
    public static PackageProducer ValidProducer(string inputKind = "il") => new("RuneCLR.PackageTool", "0.1.0", inputKind,
        inputKind == "source" ? SourceCompiler.Compile("ProducerProbe", [new("probe.cs", "public class Probe { }")], CompilerFixture.ApprovedReferences()).CompilerIdentities : [],
        CompilerFixture.ApprovedReferences().Select(Identity).ToArray(), [Identity(TestAssembly)]);
}

internal static class CompilerFixture
{
    public static IReadOnlyList<string> ApprovedReferences() => new[] { "System.Runtime", "System.Collections", "System.Linq", "System.ObjectModel", "System.Runtime.Extensions" }
        .Select(name => Path.Combine(Fixtures.FrameworkReferenceDirectory, name + ".dll")).Append(Fixtures.ContractAssembly).ToArray();
}

internal static class Check
{
    public static void Assert(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
    public static T Throws<T>(Action action) where T : Exception
    {
        try { action(); } catch (T exception) { return exception; }
        throw new InvalidOperationException($"Expected {typeof(T).Name}.");
    }
    public static void Collected(MapRunResult result)
    {
        for (var attempt = 0; attempt < 10 && !result.Unload.IsCollected; attempt++)
        { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); Thread.Sleep(10); }
        Assert(result.Unload.IsCollected, "The collectible context is still alive.");
    }
}

internal sealed class TempDirectory : IDisposable
{
    public string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "RuneCLR-packaging-" + Guid.NewGuid().ToString("N"));
    public TempDirectory() => Directory.CreateDirectory(Path);
    public void Dispose()
    {
        var fullPath = System.IO.Path.GetFullPath(Path);
        if (System.IO.Path.GetDirectoryName(fullPath) != System.IO.Path.GetFullPath(System.IO.Path.GetTempPath()).TrimEnd(System.IO.Path.DirectorySeparatorChar)
            || !System.IO.Path.GetFileName(fullPath).StartsWith("RuneCLR-packaging-", StringComparison.Ordinal))
            throw new InvalidOperationException("Temporary directory cleanup target is invalid.");
        // LoadFromAssemblyPath can keep the file mapped until a loader finalizer runs, after the collectible context weak reference is already dead.
        for (var attempt = 1; attempt <= 5; attempt++)
        {
            try
            {
                Directory.Delete(fullPath, recursive: true);
                return;
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
                if (attempt == 5) throw;
                GC.Collect();
                GC.WaitForPendingFinalizers();
                GC.Collect();
                Thread.Sleep(50);
            }
        }
    }
}
