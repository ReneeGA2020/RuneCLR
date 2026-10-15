using System.Runtime.CompilerServices;
using RuneCLR.Runtime;

var collect = args.Contains("--collect", StringComparer.Ordinal);
var pump = args.Contains("--pump", StringComparer.Ordinal);
var required = args.Contains("--require-interpreter", StringComparer.Ordinal);
var options = new MapRunOptions { ExecutionPolicy = required ? MapExecutionPolicy.RequireInterpreter : MapExecutionPolicy.Default };
var manifests = args.Where(argument => argument is not "--collect" and not "--require-interpreter" and not "--pump").ToArray();
if (manifests.Length == 0)
{
    manifests = [
        Path.Combine(AppContext.BaseDirectory, "maps", "hello", "map.json"),
        Path.Combine(AppContext.BaseDirectory, "maps", "arena", "map.json"),
        Path.Combine(AppContext.BaseDirectory, "maps", "hello", "map.json")
    ];
}

Console.WriteLine($"RuneCLR prototype | .NET {Environment.Version} | process {Environment.ProcessId}");
Console.WriteLine(required ? "Session policy: required interpretation." : "Session policy: ordinary runtime selection.");
var runner = new MapRunner();
var failed = false;
var policyReported = false;

foreach (var manifest in manifests)
{
    try
    {
        var package = MapPackage.FromManifest(manifest);
        var result = pump ? RunPumped(runner, package, options) : runner.Run(package, options);
        if (required && !policyReported)
        {
            if (result.Report.ExecutionPolicyVersion != 1) throw new InvalidOperationException("Native execution-policy acknowledgment missing.");
            Console.WriteLine("SESSION_EXECUTION_POLICY required-interpreter version=1");
            policyReported = true;
        }
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

[MethodImpl(MethodImplOptions.NoInlining)]
static MapRunResult RunPumped(MapRunner runner, MapPackage package, MapRunOptions options)
{
    using var session = runner.Start(package, options);
    for (var tick = 0; tick < options.TickCount && session.IsRunning; tick++)
    {
        session.Tick();
    }

    // Return before the caller observes collection, after callback frames have unwound.
    return session.Stop();
}
