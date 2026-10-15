using RuneCLR;

public sealed class Gameplay : IMapScript
{
    private IMapContext? context;
    private static int starts;

    public void OnStart(IMapContext value)
    {
        context = value;
        context.Log("starts=" + (++starts));
        context.SpawnEntity("hero");
    }

    public void OnTick(MapTick tick) => context!.Log("tick=" + tick.Index);
    public void OnStop() => context!.Log("stopped");
}
