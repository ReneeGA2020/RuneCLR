using System.Runtime.CompilerServices;
using RuneCLR;
using HostBudgetUGC.Private;
namespace HostBudgetUGC;
public abstract class Base:IMapScript
{
    protected IMapContext Context=null!;
    public virtual void OnStart(IMapContext context){Context=context;context.SpawnEntity("budget-owned");context.Log("start");}
    public abstract void OnTick(MapTick tick);
    public virtual void OnStop(){Context.Log("stop");}
    [MethodImpl(MethodImplOptions.NoInlining)]
    protected static void Spin(){int value=0;while(true)value=unchecked(value+1);}
}
public sealed class Normal:Base
{
    private static int starts;
    public override void OnStart(IMapContext context){base.OnStart(context);starts++;context.Log("static="+starts);}
    public override void OnTick(MapTick tick){Context.Log("tick="+tick.Index);}
}
public sealed class TickWork:Base
{
    private int checksum;
    public override void OnTick(MapTick tick)
    {
        for(int index=0;index<64;index++)checksum=unchecked(checksum*31+index+tick.Index);
        Context.Log("work="+tick.Index);
    }
}
public sealed class EndlessTick:Base{public override void OnTick(MapTick tick){Context.Log("tick-before");Spin();Context.Log("tick-after");}}
public sealed class StartLoop:Base{public override void OnStart(IMapContext context){base.OnStart(context);Spin();context.Log("start-after");}public override void OnTick(MapTick tick){Context.Log("unexpected-tick");}}
public sealed class CatchResume:Base
{public override void OnTick(MapTick tick){try{Spin();}catch(OperationCanceledException){Context.Log("catch");}Context.Log("resume");}}
public sealed class BroadCatchResume:Base
{public override void OnTick(MapTick tick){try{Spin();}catch{Context.Log("broad-catch");}Context.Log("resume");}}
public sealed class SignalFilter:Base
{
    [MethodImpl(MethodImplOptions.NoInlining)] private bool Filter(){Context.Log("signal-filter");return true;}
    public override void OnTick(MapTick tick){try{Spin();}catch(OperationCanceledException)when(Filter()){Context.Log("filter-catch");}Context.Log("resume");}
}
public sealed class FilterExhaustion:Base
{
    [MethodImpl(MethodImplOptions.NoInlining)] private bool Filter(){Context.Log("filter-before");Spin();Context.Log("filter-after");return true;}
    public override void OnTick(MapTick tick){try{throw new InvalidOperationException("ordinary filter trigger");}catch(InvalidOperationException)when(Filter()){Context.Log("filter-catch");}catch{Context.Log("fallback-catch");}Context.Log("resume");}
}
public sealed class ConstructorLoop:Base{public ConstructorLoop(){Spin();}public override void OnTick(MapTick tick){}}
public sealed class StaticConstructorLoop:Base{static StaticConstructorLoop(){Spin();}public override void OnTick(MapTick tick){}}
public sealed class FiniteCleanup:Base{public override void OnTick(MapTick tick){try{Spin();}finally{Context.Log("finally");Helper.Finite(Context);}}}
public sealed class InfiniteCleanup:Base{public override void OnTick(MapTick tick){try{Spin();}finally{Helper.Infinite(Context);}}}
public sealed class StopLoop:Base{public override void OnTick(MapTick tick){Context.Log("tick="+tick.Index);}public override void OnStop(){Context.Log("stop-before");Spin();Context.Log("stop-after");}}
public sealed class BadMessage:Exception
{
    public override string Message { get { int value=0;while(true)value=unchecked(value+1); } }
}
public sealed class MaliciousMessage:Base{public override void OnTick(MapTick tick){throw new BadMessage();}}
public sealed class ExplicitCanceled:Base{public override void OnTick(MapTick tick){throw new OperationCanceledException("ordinary authored cancellation");}}
