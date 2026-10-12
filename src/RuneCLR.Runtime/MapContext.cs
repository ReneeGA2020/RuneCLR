namespace RuneCLR.Runtime;

internal sealed class MapContext : IMapContext, IDisposable
{
    private readonly MapRunOptions _options;
    private readonly Dictionary<EntityId, string> _entities = [];
    private readonly List<string> _logs = [];
    private int _remainingOperations;
    private string? _violation;
    private bool _disposed;
    private long _nextEntity;

    public MapContext(string mapId, MapRunOptions options)
    {
        MapId = mapId;
        _options = options;
    }

    public string MapId { get; }
    public int CreatedEntities { get; private set; }
    public int ReleasedEntities { get; private set; }
    public int RemainingEntities => _entities.Count;
    public string[] Logs => _logs.ToArray();

    public void BeginCallback()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        _remainingOperations = _options.OperationBudgetPerCallback;
    }

    public void CheckViolation()
    {
        if (_violation is not null)
        {
            throw new MapLimitException(_violation);
        }
    }

    public void Charge(int operations = 1)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(operations);
        CheckViolation();
        if (operations > _remainingOperations)
        {
            Violate("The cooperative operation budget was exceeded.");
        }

        _remainingOperations -= operations;
    }

    public EntityId SpawnEntity(string name)
    {
        Charge(8);
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        if (name.Length > 128)
        {
            Violate("Entity names cannot exceed 128 characters.");
        }

        if (_entities.Count >= _options.MaxEntities)
        {
            Violate("The entity limit was exceeded.");
        }

        var id = new EntityId(++_nextEntity);
        _entities.Add(id, name);
        CreatedEntities++;
        return id;
    }

    public void DestroyEntity(EntityId entity)
    {
        Charge(4);
        if (!_entities.Remove(entity))
        {
            throw new ArgumentException("The entity does not belong to this session.", nameof(entity));
        }

        ReleasedEntities++;
    }

    public void Log(string message)
    {
        Charge();
        ArgumentNullException.ThrowIfNull(message);
        if (message.Length > 2_048 || _logs.Count >= _options.MaxLogMessages)
        {
            Violate("The session log limit was exceeded.");
        }

        _logs.Add(message);
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        ReleasedEntities += _entities.Count;
        _entities.Clear();
        _disposed = true;
    }

    private void Violate(string message)
    {
        _violation ??= message;
        throw new MapLimitException(_violation);
    }
}

public sealed class MapLimitException(string message) : Exception(message);
