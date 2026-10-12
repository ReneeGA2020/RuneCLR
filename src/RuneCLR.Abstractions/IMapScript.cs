namespace RuneCLR;

public interface IMapScript
{
    void OnStart(IMapContext context);
    void OnTick(MapTick tick);
    void OnStop();
}

public interface IMapContext
{
    string MapId { get; }
    EntityId SpawnEntity(string name);
    void DestroyEntity(EntityId entity);
    void Log(string message);

    // Cooperative checkpoints only; arbitrary IL is not metered yet.
    void Charge(int operations = 1);
}

public readonly record struct EntityId(long Value);
public readonly record struct MapTick(int Index, TimeSpan Delta);
