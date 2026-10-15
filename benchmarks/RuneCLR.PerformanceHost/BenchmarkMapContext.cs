using System.Runtime.CompilerServices;
using RuneCLR;

// A trusted benchmark adapter of the actual shared IMapContext API. The real
// MapRunner/MapContext lifecycle is measured separately by the SessionMap fixture.
// Stores retain only primitive handles/strings; no map-owned objects or delegates.
internal sealed class BenchmarkMapContext : IMapContext
{
    private readonly Dictionary<EntityId, string> _entities = new(1);
    private readonly List<string> _logs = new(2_048);
    private long _nextEntity;
    private int _charged, _released;

    public string MapId => "benchmark";

    [MethodImpl(MethodImplOptions.NoInlining)]
    public void Charge(int operations = 1)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(operations);
        _charged += operations;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public EntityId SpawnEntity(string name)
    {
        Charge(8);
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        var id = new EntityId(++_nextEntity);
        _entities.Add(id, name);
        return id;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public void DestroyEntity(EntityId entity)
    {
        Charge(4);
        if (!_entities.Remove(entity)) throw new InvalidOperationException("Unknown entity");
        _released++;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public void Log(string message)
    {
        Charge();
        ArgumentNullException.ThrowIfNull(message);
        _logs.Add(message);
    }

    public void VerifyCompleted(int operations, int logs)
    {
        if (_entities.Count != 0 || _nextEntity != operations || _released != operations ||
            _logs.Count != logs || _charged != operations * 13 + logs)
            throw new InvalidOperationException("Host API operation counts differ");
    }
}
