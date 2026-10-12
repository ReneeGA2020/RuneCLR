namespace RuneCLR.LateMap;

public sealed class LateMap : IMapScript
{
    public void OnStart(IMapContext context)
    {
        context.Log("late-map=42");
        context.SpawnEntity("built-after-host");
    }

    public void OnTick(MapTick tick) { }
    public void OnStop() { }
}
