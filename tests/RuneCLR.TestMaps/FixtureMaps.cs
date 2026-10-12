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
