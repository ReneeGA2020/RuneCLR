using System.Runtime.CompilerServices;
using FinalizerProbe.Contract;
using FinalizerUGC.Private;
namespace FinalizerUGC.Payload;
public sealed class Entry:IControl
{
    private static int starts;
    static Entry(){starts++;}
    [MethodImpl(MethodImplOptions.NoInlining)]
    public object Create(Scenario scenario)=>scenario switch
    {
        Scenario.InheritedTrustedBase=>new InheritedTarget(),
        Scenario.AuthorOverrideFinite=>new OverrideFiniteTarget(),
        Scenario.AuthorOverrideInfinite=>new OverrideInfiniteTarget(),
        _=>new Target(scenario)
    };
    [MethodImpl(MethodImplOptions.NoInlining)]
    public void Terminate()=>Bodies.Spin();
    [MethodImpl(MethodImplOptions.NoInlining)]
    public int PrepareCleanup()=>Helper.Prepare();
    [MethodImpl(MethodImplOptions.NoInlining)]
    public int Good(){Recorder.Mark(Signal.Good);Recorder.Mark(Signal.Starts);return starts==1?73:-1;}
}
public static class Bodies
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void Spin()
    {
        if(Recorder.FiniteControl){int sum=0;for(int i=0;i<1000;i++)sum+=i;if(sum!=499500)throw new InvalidOperationException();return;}
        int ticks=0;while(true)ticks=unchecked(ticks+1);
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void FiniteCleanup(){Recorder.Mark(Signal.Finally);Helper.Cleanup();}
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void InfiniteCleanup(){Recorder.Mark(Signal.Finally);Spin();}
}
public sealed class Target
{
    private readonly Scenario scenario;
    public Target(Scenario scenario){this.scenario=scenario;Recorder.Mark(Signal.Constructor);}
    ~Target()
    {
        Recorder.Mark(Signal.AuthorEntered);
        if(scenario==Scenario.ExplicitCanceled)throw new OperationCanceledException("finalizer explicit canceled before native latch");
        if(scenario==Scenario.ExplicitInvalid)throw new InvalidOperationException("finalizer ordinary invalid operation");
        if(scenario is Scenario.ActiveLoopFinally or Scenario.UnloadBeforeFinalization)
        {try{Bodies.Spin();}finally{Bodies.FiniteCleanup();}}
        else if(scenario==Scenario.ActiveLoopInfiniteFinally)
        {try{Bodies.Spin();}finally{Bodies.InfiniteCleanup();}}
        else if(scenario!=Scenario.GoodFiniteControl)Bodies.Spin();
        Recorder.Mark(Signal.AuthorPost);
    }
}
public sealed class InheritedTarget:TrustedBase
{
    public InheritedTarget(){Recorder.Mark(Signal.Constructor);}
}
public sealed class OverrideFiniteTarget:TrustedBase
{
    public OverrideFiniteTarget(){Recorder.Mark(Signal.Constructor);}
    ~OverrideFiniteTarget(){Recorder.Mark(Signal.AuthorEntered);try{Bodies.Spin();}finally{Bodies.FiniteCleanup();}Recorder.Mark(Signal.AuthorPost);}
}
public sealed class OverrideInfiniteTarget:TrustedBase
{
    public OverrideInfiniteTarget(){Recorder.Mark(Signal.Constructor);}
    ~OverrideInfiniteTarget(){Recorder.Mark(Signal.AuthorEntered);try{Bodies.Spin();}finally{Bodies.InfiniteCleanup();}Recorder.Mark(Signal.AuthorPost);}
}
