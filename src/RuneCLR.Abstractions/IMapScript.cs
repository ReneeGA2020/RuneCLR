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

    // Open only while the current start, tick, or stop callback is running.
    // The host drops subscribers when that callback returns.
    event Action<int> Signal;

    void RaiseSignal(int value);

    // Primitive host tick schedule. Accepted only while a callback is running.
    // A value can be taken only on a later tick, and stopping the session drops the rest.
    void Schedule(int dueInTicks, int value);
    bool TryTakeScheduled(out int value);
    int PendingScheduled { get; }

    // Host-completed work. The script requests it during a callback and takes a
    // primitive result on a later callback. Stopping the session drops the rest.
    long RequestWork(string name);
    bool TryTakeWork(out long id, out int value, out bool succeeded);
    int PendingWork { get; }

    // Host-owned resource names. Accepted only while a callback is running.
    // The host can copy them between callbacks. Stopping the session drops the rest.
    void RegisterResource(string name);
    bool ReleaseResource(string name);
    int PendingResources { get; }
}

public readonly record struct EntityId(long Value);
public readonly record struct MapTick(int Index, TimeSpan Delta);
