using System.Runtime.CompilerServices;
using ConcurrencyProbe.Contract;
namespace ConcurrencyUGC;
public static class Entry
{
    private static int starts;
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int Warm() => ++starts;
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static uint Work(int slot)
    {
        Coordinator.Enter(slot);
        uint value = 1;
        for (int i = 0; i < 10000; i++) value = unchecked(value * 1664525u + 1013904223u);
        Coordinator.Complete(slot);
        return value;
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static uint WorkFinally(int slot)
    {
        Coordinator.Enter(slot);
        try
        {
            uint value = 1;
            for (int i = 0; i < 10000; i++) value = unchecked(value * 1664525u + 1013904223u);
            Coordinator.Complete(slot);
            return value;
        }
        finally { FiniteCleanup(slot); }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void FiniteCleanup(int slot)
    {
        Coordinator.CleanupStart(slot);
        uint value = 1;
        for (int i = 0; i < 64; i++) value = unchecked(value * 1664525u + 1013904223u);
        Coordinator.CleanupEnd(slot, value);
    }
}
