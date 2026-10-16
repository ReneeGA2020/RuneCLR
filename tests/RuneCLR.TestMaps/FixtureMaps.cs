namespace RuneCLR.TestMaps;

public sealed class CounterMap : IMapScript
{
    private static int _starts;
    private IMapContext _context = null!;

    public void OnStart(IMapContext context)
    {
        _context = context;
        context.Log($"starts={++_starts}");
        context.SpawnEntity("fixture");
    }

    public void OnTick(MapTick tick) => _context.Log($"tick={tick.Index}");
    public void OnStop() => _context.Log("stopped");
}

public sealed class ThrowingMap : IMapScript
{
    private IMapContext _context = null!;

    public void OnStart(IMapContext context)
    {
        _context = context;
        context.SpawnEntity("before-error");
    }

    public void OnTick(MapTick tick) => throw new MapDefinedException();
    public void OnStop() => _context.Log("stopped-after-error");
}

public sealed class MapDefinedException() : Exception("map-defined failure");

public sealed class ConstructorThrowingMap : IMapScript
{
    public ConstructorThrowingMap() => throw new MapDefinedException();
    public void OnStart(IMapContext context) { }
    public void OnTick(MapTick tick) { }
    public void OnStop() { }
}

public sealed class ThrowingMessageException : Exception
{
    public override string Message => throw new MapDefinedException();
}

public sealed class ThrowingMessageMap : IMapScript
{
    public void OnStart(IMapContext context) => context.SpawnEntity("before-message-error");
    public void OnTick(MapTick tick) => throw new ThrowingMessageException();
    public void OnStop() => throw new ThrowingMessageException();
}

public sealed class ManualTickMap : IMapScript
{
    private IMapContext _context = null!;
    public void OnStart(IMapContext context)
    {
        _context = context;
        context.SpawnEntity("manual");
        context.Log("started");
    }
    public void OnTick(MapTick tick) => _context.Log($"tick={tick.Index}:delta={tick.Delta.Ticks}");
    public void OnStop() => _context.Log("stopped");
}

public sealed class StartThrowingMap : IMapScript
{
    private IMapContext _context = null!;
    public void OnStart(IMapContext context)
    {
        _context = context;
        context.SpawnEntity("before-start-error");
        throw new MapDefinedException();
    }
    public void OnTick(MapTick tick) { }
    public void OnStop() => _context.Log("stopped-after-start-error");
}

public sealed class ThrowAfterFirstTickMap : IMapScript
{
    private IMapContext _context = null!;
    public void OnStart(IMapContext context)
    {
        _context = context;
        context.SpawnEntity("before-tick-error");
    }
    public void OnTick(MapTick tick)
    {
        if (tick.Index == 1) throw new MapDefinedException();
    }
    public void OnStop() => _context.Log("stopped-after-tick-error");
}

public sealed class TickCatchingBudgetMap : IMapScript
{
    private IMapContext _context = null!;
    public void OnStart(IMapContext context)
    {
        _context = context;
        context.SpawnEntity("before-caught-budget");
    }
    public void OnTick(MapTick tick)
    {
        try { _context.Charge(int.MaxValue); }
        catch (Exception) { }
    }
    public void OnStop() { }
}

public sealed class CatchingBudgetMap : IMapScript
{
    public void OnStart(IMapContext context)
    {
        try
        {
            context.Charge(int.MaxValue);
        }
        catch (Exception)
        {
            // The host must still detect a caught quota violation after the callback returns.
        }
    }

    public void OnTick(MapTick tick) { }
    public void OnStop() { }
}

public sealed class EntityLimitMap : IMapScript
{
    public void OnStart(IMapContext context)
    {
        context.SpawnEntity("first");
        context.SpawnEntity("second");
    }

    public void OnTick(MapTick tick) { }
    public void OnStop() { }
}

public sealed class StopThrowingMap : IMapScript
{
    public void OnStart(IMapContext context) => context.SpawnEntity("before-stop");
    public void OnTick(MapTick tick) { }
    public void OnStop() => throw new MapDefinedException();
}

public sealed class LogLimitMap : IMapScript
{
    public void OnStart(IMapContext context)
    {
        context.Log("first");
        context.Log("second");
    }

    public void OnTick(MapTick tick) { }
    public void OnStop() { }
}

public sealed class GenericMap : IMapScript
{
    public void OnStart(IMapContext context)
    {
        var values = new Dictionary<string, List<int>> { ["answer"] = [40, 2] };
        var number = Identity(values["answer"].Sum());
        var text = Identity("map");
        context.Log($"generic={number}:{text}:{Read(new MapValue(7))}");
    }

    private static T Identity<T>(T value) => value;
    private static int Read<T>(T value) where T : struct, IValue => value.Read();
    public void OnTick(MapTick tick) { }
    public void OnStop() { }

    private interface IValue { int Read(); }
    private readonly record struct MapValue(int Value) : IValue
    {
        public int Read() => Value;
    }
}

public sealed class SignalMap : IMapScript
{
    public static int Seen;
    public static IMapContext? Kept;
    private IMapContext _context = null!;

    public void OnStart(IMapContext context) => _context = context;

    public void OnTick(MapTick tick)
    {
        Kept = _context;
        _context.Signal += OnSignal;
        _context.RaiseSignal(4);
        _context.Log($"seen={Seen}");
    }

    public void OnStop() => _context.Log("stopped");

    private void OnSignal(int value) => Seen += value;
}

public sealed class TimerMap : IMapScript
{
    public static IMapContext? Kept;
    private IMapContext _context = null!;

    public void OnStart(IMapContext context)
    {
        _context = context;
        context.Schedule(1, 4);
        context.Schedule(2, 9);
    }

    public void OnTick(MapTick tick)
    {
        Kept = _context;
        var taken = "";
        while (_context.TryTakeScheduled(out var value))
            taken = taken.Length == 0 ? value.ToString() : taken + "+" + value;
        _context.Log("tick=" + tick.Index + ":taken=" + (taken.Length == 0 ? "none" : taken));
        var rejectedZero = false;
        try { _context.Schedule(0, 1); }
        catch (ArgumentOutOfRangeException) { rejectedZero = true; }
        if (!rejectedZero) _context.Log("accepted-zero");
        if (tick.Index == 0) _context.Schedule(2, 5);
    }

    public void OnStop() => _context.Log("pending=" + _context.PendingScheduled);
}

public sealed class ResourceMap : IMapScript
{
    public static IMapContext? Kept;
    public static long KeptEntity;
    private IMapContext _context = null!;

    public void OnStart(IMapContext context) => _context = context;

    public void OnTick(MapTick tick)
    {
        Kept = _context;
        KeptEntity = _context.SpawnEntity("kept").Value;
        _context.Log("spawned");
    }

    public void OnStop() => _context.Log("stopped");
}

public sealed class HostViewMap : IMapScript
{
    private IMapContext _context = null!;
    private EntityId _first;

    public void OnStart(IMapContext context) => _context = context;

    public void OnTick(MapTick tick)
    {
        if (tick.Index == 0)
        {
            _first = _context.SpawnEntity("kept");
            _context.Log("spawned");
            return;
        }

        _context.DestroyEntity(_first);
        _context.SpawnEntity("next");
        _context.Log("replaced");
    }

    public void OnStop() => _context.Log("stopped");
}

public sealed class HostWorkMap : IMapScript
{
    public static IMapContext? Kept;
    private IMapContext _context = null!;

    public void OnStart(IMapContext context) => _context = context;

    public void OnTick(MapTick tick)
    {
        Kept = _context;
        if (tick.Index == 0)
        {
            _context.RequestWork("load");
            _context.RequestWork("bad");
            _context.Log("requested");
            return;
        }

        var success = false;
        var failure = false;
        while (_context.TryTakeWork(out _, out var value, out var succeeded))
        {
            if (succeeded && value == 4) success = true;
            if (!succeeded && value == 9) failure = true;
        }

        _context.Log(success && failure ? "taken=4:failed=9" : "mismatch");
        _context.RequestWork("later");
    }

    public void OnStop() => _context.Log("pending=" + _context.PendingWork);
}

public sealed class FaultingWorkMap : IMapScript
{
    private IMapContext _context = null!;

    public void OnStart(IMapContext context) => _context = context;

    public void OnTick(MapTick tick)
    {
        if (tick.Index == 0)
        {
            _context.RequestWork("load");
            _context.Schedule(2, 4);
            _context.Log("requested");
            return;
        }

        _context.RequestWork("again");
        _context.Schedule(1, 9);
        _context.Log("requested-again");
        throw new MapDefinedException();
    }

    public void OnStop() => _context.Log("pending=" + _context.PendingWork + ":" + _context.PendingScheduled);
}

public sealed class NextScheduleMap : IMapScript
{
    private IMapContext _context = null!;

    public void OnStart(IMapContext context)
    {
        _context = context;
        context.Schedule(1, 6);
    }

    public void OnTick(MapTick tick)
    {
        var taken = _context.TryTakeScheduled(out var value) ? value.ToString() : "none";
        _context.Log("tick=" + tick.Index + ":taken=" + taken);
    }

    public void OnStop() => _context.Log("pending=" + _context.PendingScheduled);
}

public sealed class CatchingWorkLimitMap : IMapScript
{
    private IMapContext _context = null!;

    public void OnStart(IMapContext context)
    {
        _context = context;
        context.RequestWork("kept");
        try
        {
            context.RequestWork("extra");
        }
        catch (Exception)
        {
        }
    }

    public void OnTick(MapTick tick) { }

    public void OnStop()
    {
        if (_context.PendingWork != 0) throw new InvalidOperationException("pending-work");
    }
}

public sealed class CatchingScheduleLimitMap : IMapScript
{
    private IMapContext _context = null!;

    public void OnStart(IMapContext context)
    {
        _context = context;
        context.Schedule(1, 4);
        try
        {
            context.Schedule(1, 9);
        }
        catch (Exception)
        {
        }
    }

    public void OnTick(MapTick tick) { }

    public void OnStop()
    {
        if (_context.PendingScheduled != 0) throw new InvalidOperationException("pending-schedule");
    }
}

public sealed class CatchingResourceLimitMap : IMapScript
{
    private IMapContext _context = null!;

    public void OnStart(IMapContext context)
    {
        _context = context;
        context.RegisterResource("kept");
        try
        {
            context.RegisterResource("extra");
        }
        catch (Exception)
        {
        }
    }

    public void OnTick(MapTick tick) { }

    public void OnStop()
    {
        if (_context.PendingResources != 0) throw new InvalidOperationException("pending-resource");
    }
}

public sealed class HostResourceMap : IMapScript
{
    public static IMapContext? Kept;
    private IMapContext _context = null!;

    public void OnStart(IMapContext context) => _context = context;

    public void OnTick(MapTick tick)
    {
        Kept = _context;
        if (tick.Index == 0)
        {
            _context.RegisterResource("alpha");
            _context.RegisterResource("beta");
            if (_context.ReleaseResource("missing"))
            {
                throw new InvalidOperationException("A missing resource was released.");
            }

            var duplicate = false;
            try { _context.RegisterResource("alpha"); duplicate = true; }
            catch (InvalidOperationException) { }
            var blank = false;
            try { _context.RegisterResource(" "); blank = true; }
            catch (ArgumentException) { }
            _context.Log(!duplicate && !blank ? "registered" : "rejected-wrong");
            return;
        }

        if (!_context.ReleaseResource("alpha"))
        {
            _context.Log("mismatch");
            return;
        }

        _context.Log("pending=" + _context.PendingResources);
    }

    public void OnStop() => _context.Log("pending=" + _context.PendingResources);
}