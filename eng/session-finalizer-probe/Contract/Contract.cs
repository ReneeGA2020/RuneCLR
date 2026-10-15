using System.Runtime.CompilerServices;
namespace FinalizerProbe.Contract;
public enum Scenario { ActiveLoop, ActiveLoopFinally, ActiveLoopInfiniteFinally, AlreadyTerminated, UnloadBeforeFinalization, InheritedTrustedBase, AuthorOverrideFinite, AuthorOverrideInfinite, GoodFiniteControl, ExplicitCanceled, ExplicitInvalid }
public enum Signal { Constructor, AuthorEntered, AuthorPost, Finally, Helper, Delegate, BaseEntered, Sentinel, Good, Starts, Count }
public interface IControl { object Create(Scenario scenario); void Terminate(); int Good(); int PrepareCleanup(); }
public static class Recorder
{
    private static readonly int[] counters=new int[(int)Signal.Count];
    public static bool FiniteControl { get; set; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void Mark(Signal signal)=>Interlocked.Increment(ref counters[(int)signal]);
    public static void Reset()=>Array.Clear(counters);
    public static int[] Copy()=>(int[])counters.Clone();
}
public class TrustedBase
{
    ~TrustedBase(){ Recorder.Mark(Signal.BaseEntered); }
}
