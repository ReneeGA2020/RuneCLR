using System.Runtime.CompilerServices;
using RuneCLR;

namespace RuneCLR.BatchKernel;

public static class Kernel
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static long Execute(int iterations)
    {
        uint state = 12345;
        long checksum = 0;
        for (int i = 0; i < iterations; i++)
        {
            state = unchecked(state * 1664525u + 1013904223u);
            checksum += state & 255;
        }
        return checksum;
    }

}

public sealed class KernelMap : IMapScript
{
    private IMapContext? _context;
    private long _checksum;
    public void OnStart(IMapContext context) => _context = context;
    public void OnTick(MapTick tick) => _checksum += Kernel.Execute(100_000);
    public void OnStop() => _context!.Log("batch-kernel:sum=" + _checksum);
}
