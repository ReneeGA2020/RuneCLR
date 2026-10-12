using RuneCLR.PrivateDependency;

namespace RuneCLR.DependencyMap;

public sealed class DependencyMap : IMapScript
{
    public void OnStart(IMapContext context)
    {
        // Value and reference generic instantiations must both belong to this map.
        context.Log(PrivateState<int>.Start(42));
        context.Log(PrivateState<string>.Start("map"));
        context.SpawnEntity("private-dependency");
    }

    public void OnTick(MapTick tick) { }
    public void OnStop() { }
}
