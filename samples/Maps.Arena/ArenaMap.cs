namespace RuneCLR.Samples;

public sealed class ArenaMap : IMapScript
{
    private IMapContext _context = null!;

    public void OnStart(IMapContext context)
    {
        _context = context;
        _context.Log("Arena started");
    }

    public void OnTick(MapTick tick)
    {
        var enemy = _context.SpawnEntity($"enemy-{tick.Index}");
        _context.Log($"Spawned entity {enemy.Value}");
    }

    // Remaining entities are reclaimed by the host, even without manual destruction.
    public void OnStop() => _context.Log("Arena stopped");
}
