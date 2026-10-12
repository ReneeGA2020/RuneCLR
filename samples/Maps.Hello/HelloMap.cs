namespace RuneCLR.Samples;

public sealed class HelloMap : IMapScript
{
    private static int _startCount;
    private IMapContext _context = null!;
    private EntityId _hero;

    public void OnStart(IMapContext context)
    {
        _context = context;
        _context.Log($"Hello map started; start-count={++_startCount}");
        _hero = _context.SpawnEntity("hero");
    }

    public void OnTick(MapTick tick) => _context.Log($"Hello tick {tick.Index}");

    public void OnStop()
    {
        _context.DestroyEntity(_hero);
        _context.Log("Hello map stopped");
    }
}
