using System.Runtime.CompilerServices;

namespace RuneCLR.Runtime;

public sealed class MapRunner
{
    /// <summary>Loads a script and invokes OnStart, leaving tick scheduling to the host.</summary>
    public MapSession Start(MapPackage package, MapRunOptions? options = null) => MapSession.Start(package, options);

    // Keep author callback stacks out of the caller's unload observation.
    [MethodImpl(MethodImplOptions.NoInlining)]
    public MapRunResult Run(MapPackage package, MapRunOptions? options = null)
    {
        options ??= new MapRunOptions();
        using var session = Start(package, options);
        for (var tick = 0; tick < options.TickCount && session.IsRunning; tick++)
            session.Tick();
        return session.Stop();
    }
}
