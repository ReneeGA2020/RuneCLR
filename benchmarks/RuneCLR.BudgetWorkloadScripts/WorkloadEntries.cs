using System.Runtime.CompilerServices;
using RuneCLR.Performance;

namespace RuneCLR.BudgetWorkloadScripts;

public static class WorkloadEntries
{
    public const int EntityCount = 512;
    public const int EntityTicks = 200;
    public const int HostOperations = 8_192;

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static long Entities(IMapContext context, int ticks)
    {
        var data = new Entity[EntityCount];
        for (int i = 0; i < data.Length; i++)
            data[i] = new Entity { X = i * 13, Y = i * 17, Vx = i % 7 + 1, Vy = i % 11 + 1, Hp = 100 };
        return Workloads.EntitiesObjects(data, ticks);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static long HostApi(IMapContext context, int operations) => Workloads.HostApi(context, operations);
}

public abstract class WorkloadMap : IMapScript
{
    private static int _starts;
    private IMapContext? _context;
    private long _checksum;
    private int _start;
    protected abstract string Kind { get; }
    protected abstract long Execute(IMapContext context);

    [MethodImpl(MethodImplOptions.NoInlining)]
    public void OnStart(IMapContext context)
    {
        _context = context;
        _start = ++_starts;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public void OnTick(MapTick tick) => _checksum += Execute(_context!);

    [MethodImpl(MethodImplOptions.NoInlining)]
    public void OnStop() => _context!.Log("budget-workloads:" + Kind + ":starts=" + _start + ";sum=" + _checksum);
}

public sealed class EntityMap : WorkloadMap
{
    protected override string Kind => "entities";
    [MethodImpl(MethodImplOptions.NoInlining)]
    protected override long Execute(IMapContext context) => WorkloadEntries.Entities(context, WorkloadEntries.EntityTicks);
}

public sealed class HostApiMap : WorkloadMap
{
    protected override string Kind => "host-api";
    [MethodImpl(MethodImplOptions.NoInlining)]
    protected override long Execute(IMapContext context) => WorkloadEntries.HostApi(context, WorkloadEntries.HostOperations);
}
