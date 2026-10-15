using System.Runtime.CompilerServices;
namespace ConcurrencyProbe.Contract;
public static class Coordinator
{
    private static CountdownEvent admitted = new(1);
    private static ManualResetEventSlim release = new(false);
    private static int[] entries = [], completed = [], cleanupStarted = [], cleanupCompleted = [];
    public static void Reset(int workers)
    {
        admitted.Dispose(); release.Dispose();
        admitted = new(workers); release = new(false);
        entries = new int[workers]; completed = new int[workers];
        cleanupStarted = new int[workers]; cleanupCompleted = new int[workers];
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void Enter(int slot)
    {
        Interlocked.Increment(ref entries[slot]); admitted.Signal();
        if (!release.Wait(TimeSpan.FromSeconds(20))) throw new TimeoutException("Trusted admission gate expired.");
    }
    public static bool AwaitAdmissions() => admitted.Wait(TimeSpan.FromSeconds(20));
    public static void Release() => release.Set();
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void Complete(int slot) => Interlocked.Increment(ref completed[slot]);
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void CleanupStart(int slot) => Interlocked.Increment(ref cleanupStarted[slot]);
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void CleanupEnd(int slot, uint value)
    {
        if (value != Expected(64)) throw new InvalidOperationException("Cleanup checksum differs.");
        Interlocked.Increment(ref cleanupCompleted[slot]);
    }
    public static uint Expected(int count)
    { uint value = 1; for (int i = 0; i < count; i++) value = unchecked(value * 1664525u + 1013904223u); return value; }
    public static object Snapshot() => new { entries = (int[])entries.Clone(), completed = (int[])completed.Clone(),
        cleanupStarted = (int[])cleanupStarted.Clone(), cleanupCompleted = (int[])cleanupCompleted.Clone() };
    public static int Entered => entries.Sum();
    public static int Completed => completed.Sum();
    public static int CleanupStarted => cleanupStarted.Sum();
    public static int CleanupCompleted => cleanupCompleted.Sum();
}
