using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using RuneCLR.TrustedUpdate;

if (args is not ["run", var planPath])
{
    Console.Error.WriteLine("Usage: TrustedComposition.NativeHarness run <plan.json>");
    return 2;
}

var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath), JsonOptions())
    ?? throw new InvalidOperationException("plan");
using var key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(plan.Spki))!);
File.WriteAllBytes(plan.Spki, key.ExportSubjectPublicKeyInfo());
var documents = new Dictionary<string, string>(StringComparer.Ordinal);
foreach (var package in plan.Packages)
{
    var signed = TrustedRelease.Sign(
        package.Root,
        new TrustedReleaseIdentity(package.Version, "net11.0", "x64", package.EntryType, package.EntryMethod, package.EntryPath),
        package.Files,
        key);
    if (!signed.Succeeded || signed.Document is null)
    {
        Console.Error.WriteLine("SIGN " + package.Name + " " + signed.Failure + " " + signed.Detail);
        return 3;
    }

    Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(package.Document))!);
    File.WriteAllBytes(package.Document, signed.Document);
    documents[package.Name] = package.Document;
}

var results = new List<StepResult>();
foreach (var step in plan.Steps)
{
    var arguments = new List<string>();
    if (step.Mode == "stage-start")
    {
        var package = plan.Packages.Single(item => item.Name == step.Package);
        arguments.AddRange(["stage-start", "--releases", step.Releases, "--final", step.Final,
            "--document", documents[package.Name], "--spki", plan.Spki, "--receipt", step.Receipt]);
        foreach (var file in package.Files)
            arguments.AddRange(["--file", file + "=" + Path.Combine(package.Root, file)]);
    }
    else if (step.Mode == "recover")
    {
        arguments.AddRange(["recover", "--releases", step.Releases, "--spki", plan.Spki, "--receipt", step.Receipt]);
    }
    else
    {
        Console.Error.WriteLine("MODE " + step.Mode);
        return 2;
    }

    if (step.Fail)
        arguments.Add("--fail");
    var beforeReceipt = FileSha(step.Receipt);
    var beforeTree = Tree(step.Releases);
    var exit = await Launch(plan, arguments, step.Stdout, step.Stderr);
    results.Add(new StepResult
    {
        Name = step.Name,
        ExitCode = exit,
        ReceiptShaBefore = beforeReceipt,
        ReceiptShaAfter = FileSha(step.Receipt),
        FinalTreeBefore = beforeTree,
        FinalTreeAfter = Tree(step.Releases),
    });
    Console.WriteLine("STEP " + step.Name + " exit=" + exit);
}

File.WriteAllText(plan.Summary, JsonSerializer.Serialize(results, JsonOptions()));
return 0;

static string FileSha(string path) =>
    File.Exists(path) ? Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path))) : "";

static Dictionary<string, string> Tree(string root)
{
    var map = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
    if (string.IsNullOrWhiteSpace(root) || !Directory.Exists(root))
        return map;
    foreach (var file in Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories))
    {
        var relative = Path.GetRelativePath(root, file).Replace(Path.DirectorySeparatorChar, '/');
        map[relative] = FileSha(file);
    }

    return map;
}

static async Task<int> Launch(Plan plan, List<string> arguments, string stdoutPath, string stderrPath)
{
    var start = new ProcessStartInfo(plan.Host)
    {
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
    };
    foreach (var argument in arguments)
        start.ArgumentList.Add(argument);
    start.Environment["DOTNET_ROOT"] = plan.DotnetRoot;
    start.Environment["DOTNET_ROOT_X64"] = plan.DotnetRoot;
    start.Environment["DOTNET_MULTILEVEL_LOOKUP"] = "0";
    foreach (var pair in plan.Environment)
        start.Environment[pair.Key] = pair.Value;
    using var process = Process.Start(start) ?? throw new InvalidOperationException("host");
    var stdout = process.StandardOutput.ReadToEndAsync();
    var stderr = process.StandardError.ReadToEndAsync();
    await process.WaitForExitAsync();
    Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(stdoutPath))!);
    Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(stderrPath))!);
    await File.WriteAllTextAsync(stdoutPath, await stdout);
    await File.WriteAllTextAsync(stderrPath, await stderr);
    return process.ExitCode;
}

static JsonSerializerOptions JsonOptions() => new() { PropertyNameCaseInsensitive = true, WriteIndented = true };

sealed class Plan
{
    public string Host { get; set; } = "";
    public string DotnetRoot { get; set; } = "";
    public string Spki { get; set; } = "";
    public string Summary { get; set; } = "";
    public Dictionary<string, string> Environment { get; set; } = new();
    public List<Package> Packages { get; set; } = new();
    public List<Step> Steps { get; set; } = new();
}

sealed class Package
{
    public string Name { get; set; } = "";
    public string Root { get; set; } = "";
    public string Document { get; set; } = "";
    public string Version { get; set; } = "";
    public string EntryType { get; set; } = "";
    public string EntryMethod { get; set; } = "";
    public string EntryPath { get; set; } = "";
    public List<string> Files { get; set; } = new();
}

sealed class Step
{
    public string Name { get; set; } = "";
    public string Mode { get; set; } = "";
    public string Package { get; set; } = "";
    public string Releases { get; set; } = "";
    public string Final { get; set; } = "";
    public string Receipt { get; set; } = "";
    public bool Fail { get; set; }
    public string Stdout { get; set; } = "";
    public string Stderr { get; set; } = "";
}

sealed class StepResult
{
    public string Name { get; set; } = "";
    public int ExitCode { get; set; }
    public string ReceiptShaBefore { get; set; } = "";
    public string ReceiptShaAfter { get; set; } = "";
    public Dictionary<string, string> FinalTreeBefore { get; set; } = new();
    public Dictionary<string, string> FinalTreeAfter { get; set; } = new();
}
