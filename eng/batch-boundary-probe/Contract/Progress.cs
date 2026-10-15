using System.Runtime.CompilerServices;

namespace BatchBoundary.Contract;

public static class Progress
{
    public static int Starts { get; private set; }
    public static int CompletedIterations { get; private set; }
    public static int Catches { get; private set; }
    public static int ReturnedMarkers { get; private set; }
    public static int FinallyMarkers { get; private set; }
    public static bool ProgressObserved { get; private set; }
    public static void Reset()
    {
        Starts = CompletedIterations = Catches = ReturnedMarkers = FinallyMarkers = 0;
        ProgressObserved = false;
    }
    [MethodImpl(MethodImplOptions.NoInlining)] public static void Start() => Starts++;
    [MethodImpl(MethodImplOptions.NoInlining)] public static void ReportIterations(int count)
    {
        CompletedIterations = count;
        ProgressObserved = true;
    }
    [MethodImpl(MethodImplOptions.NoInlining)] public static void FinallyProgress(int count)
    {
        FinallyMarkers++;
        ReportIterations(count);
    }
    [MethodImpl(MethodImplOptions.NoInlining)] public static void Caught() => Catches++;
    [MethodImpl(MethodImplOptions.NoInlining)] public static void Returning() => ReturnedMarkers++;
}
