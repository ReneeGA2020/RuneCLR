using RuneCLR.Runtime;

var collect = args.Contains("--collect", StringComparer.Ordinal);
var manifests = args.Where(argument => argument != "--collect").ToArray();
if (manifests.Length == 0)
{
    manifests = [
        Path.Combine(AppContext.BaseDirectory, "maps", "hello", "map.json"),
        Path.Combine(AppContext.BaseDirectory, "maps", "arena", "map.json"),
        Path.Combine(AppContext.BaseDirectory, "maps", "hello", "map.json")
    ];
}

Console.WriteLine($"RuneCLR prototype | .NET {Environment.Version} | process {Environment.ProcessId}");
Console.WriteLine("CoreCLR execution mode is controlled by the runtime; this host does not enforce interpretation.");
var runner = new MapRunner();
var failed = false;

foreach (var manifest in manifests)
{
    try
    {
        var result = runner.Run(MapPackage.FromManifest(manifest));
        Console.WriteLine($"[{result.Report.MapId}] {result.Report.Outcome}; ticks={result.Report.CompletedTicks}");
        foreach (var message in result.Report.Logs)
        {
            Console.WriteLine($"  {message}");
        }

        Console.WriteLine($"  entities: created={result.Report.CreatedEntities}, released={result.Report.ReleasedEntities}, remaining={result.Report.RemainingEntities}");
        if (result.Report.Error is not null)
        {
            Console.Error.WriteLine($"  {result.Report.Error}");
        }

        if (collect)
        {
            for (var attempt = 0; attempt < 10 && !result.Unload.IsCollected; attempt++)
            {
                GC.Collect();
                GC.WaitForPendingFinalizers();
                GC.Collect();
            }
        }

        Console.WriteLine($"  unload: {(result.Unload.IsCollected ? "collected" : "pending")}");
        failed |= result.Report.Outcome != MapRunOutcome.Completed || (collect && !result.Unload.IsCollected);
    }
    catch (Exception exception)
    {
        Console.Error.WriteLine($"Cannot run map: {exception.Message}");
        failed = true;
    }
}

return failed ? 1 : 0;
