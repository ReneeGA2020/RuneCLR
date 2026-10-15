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
