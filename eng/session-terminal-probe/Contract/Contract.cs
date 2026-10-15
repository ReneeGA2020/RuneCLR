using System.Runtime.CompilerServices;
namespace TerminalProbe.Contract;
public enum Scenario { TightLoop, TypedCatch, BroadCatch, CatchReturn, Filter, SignalFilter, FiniteFinally, NestedFinally, InfiniteFinally, ThrowingFinally, Constructor, StaticConstructor, TrustedReenter, Good }
public enum Signal { Enter, Catch, Post, FilterEntered, FilterReturned, Finally, Helper, Delegate, OuterFinally, InnerFinally, ThrowingFinally, ConstructorBefore, ConstructorAfter, StaticBefore, StaticAfter, TrustedEntered, TrustedCaught, ReentryAttempt, ReentrySucceeded, Starts, Good, FilterCatch, Count }
public interface IWork { int Run(Scenario scenario, int channel); int SafeValue(); }
public static class Recorder
{
    private static readonly int[,] counters = new int[2, (int)Signal.Count];
    public static Scenario Scenario { get; set; }
    public static int Channel { get; set; }
    public static bool FiniteControl { get; set; }
    public static void Reset() { Array.Clear(counters); }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void Mark(Signal signal, int channel) { if ((uint)channel > 1 || (uint)signal >= (uint)Signal.Count) throw new ArgumentOutOfRangeException(); counters[channel,(int)signal]++; }
    public static int[] Copy(int channel) { var copy = new int[(int)Signal.Count]; for (int i=0;i<copy.Length;i++) copy[i]=counters[channel,i]; return copy; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int Callback(Func<int> work, Func<int> reentry, int channel)
    {
        Mark(Signal.TrustedEntered,channel);
        try { work(); }
        catch (Exception) { Mark(Signal.TrustedCaught,channel); }
        Mark(Signal.ReentryAttempt,channel);
        int value = reentry();
        Mark(Signal.ReentrySucceeded,channel);
        return value;
    }
}
