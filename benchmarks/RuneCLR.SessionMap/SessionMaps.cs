using System.Runtime.CompilerServices;

namespace RuneCLR.SessionMap;

public sealed class EmptyMap : IMapScript
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public void OnStart(IMapContext context) { }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public void OnTick(MapTick tick) { }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public void OnStop() { }
}

public sealed class GameplayMap : IMapScript
{
    private static int _starts;
    private IMapContext? _context;
    private long _checksum;
    private int _ticks, _thisStart;

    [MethodImpl(MethodImplOptions.NoInlining)]
    public void OnStart(IMapContext context)
    {
        _context = context;
        _thisStart = ++_starts;
        // Intentionally leave these host resources for guaranteed host cleanup.
        for (int i = 0; i < 64; i++) _checksum += context.SpawnEntity("persistent-unit").Value;
        _checksum += AllocateGroups(0);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public void OnTick(MapTick tick)
    {
        IMapContext context = _context!;
        context.Charge();
        for (int i = 0; i < 8; i++)
        {
            EntityId entity = context.SpawnEntity("temporary-unit");
            _checksum += entity.Value;
            context.DestroyEntity(entity);
        }
        _checksum += AllocateGroups(tick.Index);
        _ticks++;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public void OnStop()
    {
        _context!.Log($"session:starts={_thisStart};ticks={_ticks};checksum={_checksum}");
        _context = null;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static long AllocateGroups(int tick)
    {
        var groups = new Dictionary<int, List<int>>(4);
        for (int group = 0; group < 4; group++) groups.Add(group, new List<int>());
        for (int i = 0; i < 32; i++) groups[i & 3].Add(tick + i);
        long sum = 0;
        foreach (List<int> values in groups.Values) sum += Sum(values);
        return sum;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static long Sum<T>(List<T> values) where T : struct, IConvertible
    {
        long sum = 0;
        foreach (T value in values) sum += value.ToInt64(null);
        return sum;
    }
}
