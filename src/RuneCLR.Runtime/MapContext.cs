namespace RuneCLR.Runtime;

internal sealed class MapContext : IMapContext, IDisposable
{
    private readonly MapRunOptions _options;
    private readonly Dictionary<EntityId, string> _entities = [];
    private readonly List<string> _logs = [];
    private int _remainingOperations;
    private string? _violation;
    private bool _disposed;
    private bool _signalOpen;
    private long _nextEntity;
    private Action<int>? _signal;
    private readonly List<ScheduledSignal> _scheduled = [];
    private int? _openTick;
    private int _nextTick;
    private readonly Dictionary<long, string> _openWork = [];
    private readonly Queue<FinishedWork> _finishedWork = [];
    private readonly HashSet<long> _finishedIds = [];
    private long _nextWork;
    private readonly HashSet<string> _resources = new(StringComparer.Ordinal);

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

    public MapEntityInfo[] CopyEntities()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        var copy = new MapEntityInfo[_entities.Count];
        var index = 0;
        foreach (var (id, name) in _entities)
        {
            copy[index++] = new MapEntityInfo(id, name);
        }

        return copy;
    }

    public event Action<int> Signal
    {
        add => ChangeSignal(value, add: true);
        remove => ChangeSignal(value, add: false);
    }

    public void BeginCallback()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        _remainingOperations = _options.OperationBudgetPerCallback;
        _signal = null;
        _signalOpen = true;
        _openTick = null;
    }

    public void BeginTick(int tickIndex)
    {
        BeginCallback();
        ArgumentOutOfRangeException.ThrowIfNegative(tickIndex);
        if (tickIndex == int.MaxValue) throw new ArgumentOutOfRangeException(nameof(tickIndex));
        _openTick = tickIndex;
        _nextTick = tickIndex + 1;
    }

    public void EndCallback()
    {
        _signalOpen = false;
        _signal = null;
    }

    public void RaiseSignal(int value)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        if (!_signalOpen)
        {
            throw new InvalidOperationException("The map signal is closed.");
        }

        _signal?.Invoke(value);
    }

    public void Schedule(int dueInTicks, int value)
    {
        EnsureScheduleOpen();
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(dueInTicks);
        int due;
        try
        {
            due = _openTick is int tick
                ? checked(tick + dueInTicks)
                : checked(_nextTick + dueInTicks - 1);
        }
        catch (OverflowException)
        {
            throw new ArgumentOutOfRangeException(nameof(dueInTicks));
        }

        Charge();
        if (_scheduled.Count >= _options.MaxScheduledSignals)
        {
            Violate("The scheduled signal limit was exceeded.");
        }

        _scheduled.Add(new ScheduledSignal(due, value, 0));
    }

    public bool TryTakeScheduled(out int value)
    {
        EnsureScheduleOpen();
        value = 0;
        if (_openTick is not int tick) return false;
        var index = -1;
        for (var i = 0; i < _scheduled.Count; i++)
        {
            if (_scheduled[i].DueTick <= tick && (index < 0 || _scheduled[i].DueTick < _scheduled[index].DueTick))
                index = i;
        }

        if (index < 0) return false;
        var item = _scheduled[index];
        value = item.Value;
        if (item.EveryTicks == 0)
        {
            _scheduled.RemoveAt(index);
            return true;
        }

        int next;
        try
        {
            next = checked(item.DueTick + item.EveryTicks);
        }
        catch (OverflowException)
        {
            throw new ArgumentOutOfRangeException("everyTicks");
        }

        _scheduled.RemoveAt(index);
        _scheduled.Add(new ScheduledSignal(next, item.Value, item.EveryTicks));
        return true;
    }

    public void Repeat(int everyTicks, int value)
    {
        EnsureScheduleOpen();
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(everyTicks);
        int due;
        try
        {
            due = _openTick is int tick
                ? checked(tick + everyTicks)
                : checked(_nextTick + everyTicks - 1);
        }
        catch (OverflowException)
        {
            throw new ArgumentOutOfRangeException(nameof(everyTicks));
        }

        Charge();
        if (_scheduled.Count >= _options.MaxScheduledSignals)
        {
            Violate("The scheduled signal limit was exceeded.");
        }

        _scheduled.Add(new ScheduledSignal(due, value, everyTicks));
    }

    public int PendingScheduled
    {
        get
        {
            EnsureScheduleOpen();
            return _scheduled.Count;
        }
    }

    public void CancelScheduled() => _scheduled.Clear();

    public long RequestWork(string name)
    {
        Charge();
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        if (name.Length > 128)
        {
            Violate("Work names cannot exceed 128 characters.");
        }

        if (_openWork.Count + _finishedWork.Count >= _options.MaxWorkItems)
        {
            Violate("The work limit was exceeded.");
        }

        var id = ++_nextWork;
        _openWork.Add(id, name);
        return id;
    }

    public bool TryTakeWork(out long id, out int value, out bool succeeded)
    {
        Charge();
        if (_finishedWork.Count == 0)
        {
            id = 0;
            value = 0;
            succeeded = false;
            return false;
        }

        var finished = _finishedWork.Dequeue();
        _finishedIds.Remove(finished.Id);
        id = finished.Id;
        value = finished.Value;
        succeeded = finished.Succeeded;
        return true;
    }

    public int PendingWork
    {
        get
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            if (!_signalOpen)
            {
                throw new InvalidOperationException("The map callback is closed.");
            }

            return _openWork.Count + _finishedWork.Count;
        }
    }

    public MapWorkInfo[] CopyPendingWork()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        var copy = new MapWorkInfo[_openWork.Count];
        var index = 0;
        foreach (var (id, name) in _openWork)
        {
            copy[index++] = new MapWorkInfo(id, name);
        }

        return copy;
    }

    public void CompleteWork(long id, int value) => FinishWork(id, value, succeeded: true);

    public void FailWork(long id, int reason) => FinishWork(id, reason, succeeded: false);

    private void FinishWork(long id, int value, bool succeeded)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        if (_finishedIds.Contains(id))
        {
            throw new InvalidOperationException("The work is already complete.");
        }

        if (!_openWork.Remove(id))
        {
            throw new ArgumentException("The work does not belong to this session.", nameof(id));
        }

        _finishedIds.Add(id);
        _finishedWork.Enqueue(new FinishedWork(id, value, succeeded));
    }

    public void CancelWork()
    {
        _openWork.Clear();
        _finishedWork.Clear();
        _finishedIds.Clear();
    }

    public void RegisterResource(string name)
    {
        Charge();
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        if (name.Length > 128)
        {
            Violate("Resource names cannot exceed 128 characters.");
        }

        if (_resources.Contains(name))
        {
            throw new InvalidOperationException("The resource is already registered.");
        }

        if (_resources.Count >= _options.MaxResources)
        {
            Violate("The resource limit was exceeded.");
        }

        _resources.Add(name);
    }

    public bool ReleaseResource(string name)
    {
        Charge();
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        return _resources.Remove(name);
    }

    public int PendingResources
    {
        get
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            if (!_signalOpen)
            {
                throw new InvalidOperationException("The map callback is closed.");
            }

            return _resources.Count;
        }
    }

    public MapResourceInfo[] CopyResources()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        var copy = new MapResourceInfo[_resources.Count];
        var index = 0;
        foreach (var name in _resources)
        {
            copy[index++] = new MapResourceInfo(name);
        }

        return copy;
    }

    public void CancelResources() => _resources.Clear();

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
        if (!_signalOpen)
        {
            throw new InvalidOperationException("The map callback is closed.");
        }

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

        CancelScheduled();
        CancelWork();
        CancelResources();
        EndCallback();
        ReleasedEntities += _entities.Count;
        _entities.Clear();
        _disposed = true;
    }

    private void ChangeSignal(Action<int>? handler, bool add)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        if (!_signalOpen)
        {
            throw new InvalidOperationException("The map signal is closed.");
        }

        if (add) _signal += handler;
        else _signal -= handler;
    }

    private void EnsureScheduleOpen()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        if (!_signalOpen)
        {
            throw new InvalidOperationException("The map schedule is closed.");
        }
    }

    private void Violate(string message)
    {
        _violation ??= message;
        throw new MapLimitException(_violation);
    }

    private readonly record struct ScheduledSignal(int DueTick, int Value, int EveryTicks);

    private readonly record struct FinishedWork(long Id, int Value, bool Succeeded);
}

public sealed class MapLimitException(string message) : Exception(message);
