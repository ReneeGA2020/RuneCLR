using System.Runtime.CompilerServices;
using TerminalProbe.Contract;
using TerminalUGC.Private;
namespace TerminalUGC.Payload;
public sealed class Entry : IWork
{
    private static int starts;
    private readonly int channel;
    static Entry()
    {
        starts++;
        if (Recorder.Scenario == Scenario.StaticConstructor)
        { Recorder.Mark(Signal.StaticBefore,Recorder.Channel); Spin(); Recorder.Mark(Signal.StaticAfter,Recorder.Channel); }
    }
    public Entry(int channel)
    {
        this.channel = channel;
        if (Recorder.Scenario == Scenario.Constructor)
        { Recorder.Mark(Signal.ConstructorBefore,channel); Spin(); Recorder.Mark(Signal.ConstructorAfter,channel); }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public int SafeValue() { Recorder.Mark(Signal.Good,channel); Recorder.Mark(Signal.Starts,channel); return starts == 1 ? 73 : -1; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void Spin()
    {
        if (Recorder.FiniteControl) { int sum=0; for(int i=0;i<1000;i++) sum=unchecked(sum+i); if(sum!=499500) throw new InvalidOperationException(); return; }
        int ticks=0; while(true) ticks=unchecked(ticks+1);
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void SpinThenControlException() { Spin(); if(Recorder.FiniteControl) throw new OperationCanceledException("finite control sentinel"); }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private bool Filter()
    { Recorder.Mark(Signal.FilterEntered,channel); Spin(); Recorder.Mark(Signal.FilterReturned,channel); return true; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private bool SentinelFilter()
    { Recorder.Mark(Signal.FilterEntered,channel); Recorder.Mark(Signal.FilterReturned,channel); return true; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private void FiniteCleanup()
    { Recorder.Mark(Signal.Finally,channel); Helper.Cleanup(channel); }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void ThrowCleanup() => throw new InvalidOperationException("cleanup replacement exception");
    [MethodImpl(MethodImplOptions.NoInlining)]
    public int Run(Scenario scenario,int ignoredChannel)
    {
        Recorder.Mark(Signal.Enter,channel);
        switch(scenario)
        {
            case Scenario.TightLoop: Spin(); break;
            case Scenario.TypedCatch:
                try { SpinThenControlException(); } catch(OperationCanceledException) { Recorder.Mark(Signal.Catch,channel); }
                break;
            case Scenario.BroadCatch:
                try { SpinThenControlException(); } catch { Recorder.Mark(Signal.Catch,channel); }
                break;
            case Scenario.CatchReturn:
                try { SpinThenControlException(); } catch(Exception) { Recorder.Mark(Signal.Catch,channel); return 99; }
                break;
            case Scenario.Filter:
                try { throw new InvalidOperationException("ordinary filter trigger"); }
                catch(InvalidOperationException) when(Filter()) { Recorder.Mark(Signal.FilterCatch,channel); }
                catch { Recorder.Mark(Signal.Catch,channel); }
                break;
            case Scenario.SignalFilter:
                try { SpinThenControlException(); }
                catch(OperationCanceledException) when(SentinelFilter()) { Recorder.Mark(Signal.FilterCatch,channel); }
                break;
            case Scenario.FiniteFinally:
                try { Spin(); } finally { FiniteCleanup(); }
                break;
            case Scenario.NestedFinally:
                try { try { Spin(); } finally { Recorder.Mark(Signal.InnerFinally,channel); Helper.Cleanup(channel); } }
                finally { Recorder.Mark(Signal.OuterFinally,channel); Helper.Cleanup(channel); }
                break;
            case Scenario.InfiniteFinally:
                try { try { Spin(); } finally { Recorder.Mark(Signal.InnerFinally,channel); Spin(); } }
                finally { Recorder.Mark(Signal.OuterFinally,channel); }
                break;
            case Scenario.ThrowingFinally:
                try { try { Spin(); } finally { Recorder.Mark(Signal.ThrowingFinally,channel); ThrowCleanup(); } }
                finally { Recorder.Mark(Signal.OuterFinally,channel); }
                break;
            case Scenario.TrustedReenter:
                Recorder.Callback(() => { SpinThenControlException(); return 0; },SafeValue,channel);
                break;
            case Scenario.Constructor:
            case Scenario.StaticConstructor:
                break;
            case Scenario.Good: return SafeValue();
            default: throw new ArgumentOutOfRangeException(nameof(scenario));
        }
        Recorder.Mark(Signal.Post,channel);
        return 17;
    }
}
