using System.Text.Json;

if (args is ["--self-test"])
    return SelfTest.Run();
if (args is ["--integration"])
    return IntegrationProbe.Run();
if (args.Length == 3 && args[0] == "--integration-child")
    return IntegrationProbe.Child(args);
if (args.Length == 5 && args[0] == "--http-server")
    return HttpLoopbackServer.Run(args);
if (args.Length == 2 && args[0] == "--distinct-http")
    return DistinctHttpDriver.Run(args[1]);
if (args.Length == 3 && args[0] == "--distinct-http-child")
    return DistinctHttpDriver.Child(args[1], args[2]);
if (args.Length > 1 && args[0] == "--child")
    return SelfTest.Child(args);

if (args.Length > 0 && args[0] == "stage-start")
    return await Cli.Stage(args);
if (args.Length > 0 && args[0] == "recover")
    return Cli.Recover(args);

Cli.Usage();
return 2;

static class Cli
{
    static readonly JsonSerializerOptions FactsJson = new() { IncludeFields = true };

    public static async Task<int> Stage(string[] args)
    {
        if (args.Contains("--offer")
            || !TryNeed(args, "--releases", out var releases)
            || !TryNeed(args, "--final", out var finalDir)
            || !TryNeed(args, "--document", out var document)
            || !TryNeed(args, "--spki", out var spki)
            || !TryNeed(args, "--receipt", out var receipt)
            || !TryFiles(args, out var files))
        {
            Console.Error.WriteLine("ERROR argument");
            return 2;
        }

        var facts = await DeliverySession.StageAsync(releases, finalDir, document, spki, receipt, files, args.Contains("--fail"));
        Print(facts);
        return facts.Activated ? 0 : 1;
    }

    public static int Recover(string[] args)
    {
        if (args.Contains("--offer")
            || !TryNeed(args, "--releases", out var releases)
            || !TryNeed(args, "--spki", out var spki)
            || !TryNeed(args, "--receipt", out var receipt))
        {
            Console.Error.WriteLine("ERROR argument");
            return 2;
        }

        var facts = DeliverySession.RecoverOnly(releases, spki, receipt, args.Contains("--fail"));
        Print(facts);
        return facts.Activated ? 0 : 1;
    }

    public static void Usage()
    {
        Console.Error.WriteLine("ERROR argument");
        Console.Error.WriteLine("Usage:");
        Console.Error.WriteLine("  stage-start --releases <root> --final <dir> --document <file> --spki <file> --receipt <file> --file <relative>=<path> [--fail]");
        Console.Error.WriteLine("  recover --releases <root> --spki <file> --receipt <file> [--fail]");
        Console.Error.WriteLine("  --self-test");
    }

    static bool TryFiles(string[] args, out List<(string Relative, string Absolute)> files)
    {
        files = [];
        for (var i = 0; i < args.Length - 1; i++)
        {
            if (args[i] != "--file")
                continue;
            var pair = args[i + 1];
            var split = pair.IndexOf('=');
            if (split <= 0 || split == pair.Length - 1)
                return false;
            files.Add((pair[..split], pair[(split + 1)..]));
        }

        return files.Count > 0;
    }

    static bool TryNeed(string[] args, string name, out string value)
    {
        var index = Array.IndexOf(args, name);
        value = index >= 0 && index + 1 < args.Length ? args[index + 1] : "";
        return !string.IsNullOrWhiteSpace(value) && !value.StartsWith("--", StringComparison.Ordinal);
    }

    public static void Print(DeliveryFacts facts)
    {
        Console.WriteLine("ACTIVATED " + facts.Activated);
        Console.WriteLine("VERSION " + facts.Version);
        Console.WriteLine("SOURCE " + facts.Source);
        Console.WriteLine("VALUE " + facts.Value);
        Console.WriteLine("PRIVATE " + facts.PrivateValue);
        Console.WriteLine("HELPER " + facts.HelperValue);
        Console.WriteLine("PRIVATE_VERSION " + facts.PrivateVersion);
        Console.WriteLine("IDENTITY " + facts.Identity);
        Console.WriteLine("TOUCH " + facts.TouchValue);
        Console.WriteLine("INTERFACE " + facts.InterfaceValue);
        Console.WriteLine("DELEGATE " + facts.DelegateValue);
        Console.WriteLine("GENERIC " + facts.GenericValue);
        Console.WriteLine("STATIC " + facts.StaticCount);
        Console.WriteLine("PRIVATE_COUNT " + facts.PrivateCount);
        Console.WriteLine("CALLS " + facts.Calls);
        Console.WriteLine("DETAIL " + facts.Detail);
        Console.WriteLine("STAGE " + facts.Stage);
        Console.WriteLine("CANDIDATE " + facts.Candidate);
        Console.WriteLine("RECOVERY " + facts.Recovery);
        Console.WriteLine("PERSIST " + facts.Persist);
        Console.WriteLine("ENTRY " + facts.Entry);
        Console.WriteLine("LISTED_PRIVATE " + facts.ListedPrivate);
        Console.WriteLine("LISTED_HELPER " + facts.ListedHelper);
        Console.WriteLine("LOADED_ENTRY " + facts.LoadedEntry);
        Console.WriteLine("LOADED_PRIVATE " + facts.LoadedPrivate);
        Console.WriteLine("LOADED_HELPER " + facts.LoadedHelper);
        Console.WriteLine("HELPER_LOADED " + facts.HelperLoaded);
        Console.WriteLine("WITNESSES " + facts.Witnesses);
        Console.WriteLine("FACTS " + JsonSerializer.Serialize(facts, FactsJson));
    }
}
