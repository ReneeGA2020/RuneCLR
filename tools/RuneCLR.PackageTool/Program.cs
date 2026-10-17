using System.Text.Json;
using RuneCLR.Compiler;
using RuneCLR.Packages;

try
{
    if (args.Length == 0 || args[0] is "--help" or "-h")
    {
        Console.WriteLine("RuneCLR.PackageTool (trusted operator/server tool; author projects are never executed)");
        Console.WriteLine("compile --source <C#-only directory> --id <id> --entry-type <type> --framework-refs <approved reference directory> --contract <approved RuneCLR.Abstractions.dll> --output <new directory> [--dependency <private IL DLL>]... [--host-interface <type> --allowed-method <name>...]");
        Console.WriteLine("import --assembly <IL DLL> --id <id> --entry-type <type> --framework-refs <directory> --contract <DLL> --output <new directory> [--dependency <private IL DLL>]... [--host-interface <type> --allowed-method <name>...]");
        Console.WriteLine("validate --manifest <package.json>");
        return 0;
    }
    var command = args[0];
    if (command is not ("compile" or "import" or "validate")) throw new ArgumentException("Unknown command. Use --help.");
    var allowed = command == "validate" ? new[] { "--manifest" } : new[] { "--id", "--entry-type", "--framework-refs", "--contract", "--output", "--dependency", "--host-interface", "--allowed-method", command == "compile" ? "--source" : "--assembly" };
    var options = new Dictionary<string, string>(StringComparer.Ordinal);
    var dependencies = new List<string>();
    var allowedMethods = new List<string>();
    for (var index = 1; index < args.Length; index += 2)
    {
        if (!allowed.Contains(args[index]) || index + 1 >= args.Length || args[index + 1].StartsWith("--", StringComparison.Ordinal))
            throw new ArgumentException("Unknown option or missing value. Use --help.");
        if (args[index] == "--dependency") dependencies.Add(args[index + 1]);
        else if (args[index] == "--allowed-method") allowedMethods.Add(args[index + 1]);
        else if (!options.TryAdd(args[index], args[index + 1])) throw new ArgumentException("An option was supplied more than once.");
    }
    string Required(string name) => options.TryGetValue(name, out var value) ? value : throw new ArgumentException($"Missing {name}.");
    if (command == "validate")
    {
        var path = Required("--manifest");
        var manifest = PackageManifestIO.Read(path);
        PackageValidator.Validate(manifest, path);
        Console.WriteLine(JsonSerializer.Serialize(new { success = true, id = manifest.Id, contentSha256 = manifest.ContentSha256 }));
        return 0;
    }
    var profile = new ReferenceProfile(Required("--framework-refs"), Required("--contract"));
    PackageBuildResult result;
    if (command == "compile")
    {
        var directory = Path.GetFullPath(Required("--source"));
        var sources = new List<SourceFile>();
        long totalBytes = 0;
        foreach (var path in SourcePaths(directory))
        {
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0 || !path.EndsWith(".cs", StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Source input must contain only regular .cs files, with no author project/build configuration or linked files.");
            totalBytes += new FileInfo(path).Length;
            if (sources.Count >= SourceCompiler.MaximumSources || totalBytes > 8_000_000)
                throw new InvalidDataException("Source directory exceeds the compiler input limits.");
            sources.Add(new(Path.GetRelativePath(directory, path).Replace(Path.DirectorySeparatorChar, '/'), File.ReadAllText(path)));
        }
        result = PackageBuilder.Compile(Required("--id"), Required("--entry-type"), sources.OrderBy(item => item.Name, StringComparer.Ordinal).ToArray(), profile, Required("--output"), dependencies, options.GetValueOrDefault("--host-interface"), allowedMethods.Count == 0 ? null : allowedMethods);
    }
    else result = PackageBuilder.Import(Required("--id"), Required("--entry-type"), Required("--assembly"), profile, Required("--output"), dependencies, options.GetValueOrDefault("--host-interface"), allowedMethods.Count == 0 ? null : allowedMethods);
    Console.WriteLine(JsonSerializer.Serialize(new { success = result.Succeeded, manifest = result.ManifestPath, diagnostics = result.Diagnostics }));
    return result.Succeeded ? 0 : 2;
}
catch (Exception exception) when (exception is ArgumentException or IOException or InvalidDataException or UnauthorizedAccessException or BadImageFormatException or JsonException)
{
    Console.Error.WriteLine(JsonSerializer.Serialize(new { success = false, error = exception.Message }));
    return 2;
}

static IEnumerable<string> SourcePaths(string directory, int depth = 0)
{
    if (depth > 16) throw new InvalidDataException("Source directories exceed the nesting limit.");
    if ((File.GetAttributes(directory) & FileAttributes.ReparsePoint) != 0)
        throw new InvalidDataException("Source directories cannot contain filesystem links.");
    foreach (var path in Directory.EnumerateFileSystemEntries(directory))
    {
        var attributes = File.GetAttributes(path);
        if ((attributes & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("Source directories cannot contain filesystem links.");
        if ((attributes & FileAttributes.Directory) == 0) yield return path;
        else foreach (var file in SourcePaths(path, depth + 1)) yield return file;
    }
}
