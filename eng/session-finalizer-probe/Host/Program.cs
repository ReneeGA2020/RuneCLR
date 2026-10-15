using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using System.Text.Json;
using FinalizerProbe.Contract;
using RuneCLR.Experiments;
namespace FinalizerProbe.Host;
internal static class Program
{
    private const long Limit=2048,Cleanup=4096;
    private static object? trustedRoot;
    private static AssemblyLoadContext? fatalContext;
    internal static void Check(bool value,string reason){if(!value)throw new InvalidOperationException(reason);}
    public static int Main(string[] args)
    {
        Console.SetOut(Console.Error);
        if(args.Length!=5)throw new ArgumentException("Expected payload directory, evidence directory, case, nonce, mode.");
        string directory=Path.GetFullPath(args[0]),evidence=Path.GetFullPath(args[1]),name=args[2],nonce=args[3],mode=args[4];
        Check(nonce.Length==32&&nonce.All(Uri.IsHexDigit),"Invalid owned nonce.");
        Check(mode is "terminal" or "ordinary" or "required" or "stock" or "default","Unknown finalizer mode.");
        Directory.CreateDirectory(evidence);Recorder.Reset();Recorder.FiniteControl=mode=="stock";
        if(mode is not ("stock" or "default"))Api.Initialize(evidence);
        Console.WriteLine($"FINALIZER RUN nonce={nonce} case={name} mode={mode} runtime={System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription}");
        Console.Error.Flush();
        if(name.StartsWith("Fatal",StringComparison.Ordinal))
        {
            FatalFrame(directory,name,nonce,mode,evidence);throw new InvalidOperationException("Expected fatal finalizer unexpectedly returned.");
        }
        Scenario scenario=Enum.Parse<Scenario>(name);
        Result result;
        if(scenario==Scenario.UnloadBeforeFinalization)
        {
            Prepared retired=PrepareRetired(directory,mode,evidence);
            GC.Collect();Check(retired.Context.IsAlive&&retired.Target.IsAlive,"Explicit trusted root did not retain object/context across unload.");
            DrainRootAndObserve(mode,evidence);DrainSentinels(nonce);
            result=new Result(retired.Context,retired.Target,retired.Before,null,Recorder.Copy(),retired.TerminationException,true);
        }
        else result=RunFrame(directory,scenario,mode,evidence,nonce);
        Validate(result,scenario,mode);Collect(result.Context);Check(!result.Target.IsAlive,"Finalized target remained alive.");
        int[] primary=result.Counts;BudgetSnapshot? before=result.Before,after=result.After;
        Recorder.Reset();Outcome good=GoodFrame(directory,mode);Collect(good.Context);
        Check(good.Value==73&&good.Counts[(int)Signal.Good]==1&&good.Counts[(int)Signal.Starts]==1,"Next independent good session value/static state differs.");
        if(mode=="terminal")Check(good.Snapshot is {IsTerminated:false,Reason:0,Phase:0},"Finalizer terminated the next independent session.");
        File.WriteAllText(Path.Combine(evidence,"result.json"),JsonSerializer.Serialize(new{passed=true,nonce,scenario=name,mode,counts=primary,before,after,
            result.TerminationException,retiredBeforeFinalization=result.RetiredBeforeFinalization,targetCollected=true,contextCollected=true,
            queueSentinels=2,nextGood=new{value=good.Value,counts=good.Counts,snapshot=good.Snapshot,collected=true},
            prototypeOnly=true,authorFinalizersProductionSupported=false,nativeEntryProof=false},new JsonSerializerOptions{WriteIndented=true}));
        Console.WriteLine($"FINALIZER COMPLETE nonce={nonce} case={name} mode={mode} targetCollected=true contextCollected=true sentinels=2 nextGood=73 nextCollected=true");
        return 0;
    }
    private static void Validate(Result result,Scenario scenario,string mode)
    {
        int C(Signal signal)=>result.Counts[(int)signal];
        Check(C(Signal.Constructor)==1&&C(Signal.Sentinel)==2,"Object creation or trusted queue progress differs.");
        if(mode=="stock")
        {
            if(scenario==Scenario.InheritedTrustedBase)Check(C(Signal.AuthorEntered)==0&&C(Signal.BaseEntered)==1,"Inherited trusted finalizer finite control differs.");
            else Check(C(Signal.AuthorEntered)==1&&C(Signal.AuthorPost)==1,"Finite authored finalizer control did not complete.");
            if(scenario is Scenario.ActiveLoopFinally or Scenario.UnloadBeforeFinalization or Scenario.AuthorOverrideFinite)Check(C(Signal.Finally)==1&&C(Signal.Helper)==1&&C(Signal.Delegate)==1,"Finite private cleanup control differs.");
            if(scenario is Scenario.ActiveLoopInfiniteFinally or Scenario.AuthorOverrideInfinite)Check(C(Signal.Finally)==1,"Finite substitute for infinite-finally control missing.");
            if(scenario is Scenario.AuthorOverrideFinite or Scenario.AuthorOverrideInfinite)Check(C(Signal.BaseEntered)==1,"Ordinary compiler-generated base-finalizer chain missing.");
            return;
        }
        Check(mode=="terminal","Positive actual finalizer cases require terminal factory.");
        if(scenario==Scenario.InheritedTrustedBase)
        {
            Check(C(Signal.AuthorEntered)==0&&C(Signal.BaseEntered)==1,"Actual trusted base finalizer was suppressed by derived context ownership.");
            Check(result.Before is {IsTerminated:true,Reason:1}&&result.After==result.Before,"Trusted inherited finalizer recharged the terminal author ledger.");return;
        }
        if(scenario==Scenario.AlreadyTerminated)
        {Check(C(Signal.AuthorEntered)==0&&C(Signal.AuthorPost)==0&&result.Before is {IsTerminated:true,Reason:1}&&result.After==result.Before,"Already-terminal author finalizer entered or reset native state.");return;}
        if(scenario==Scenario.GoodFiniteControl)
        {Check(C(Signal.AuthorEntered)==1&&C(Signal.AuthorPost)==1&&result.After is {IsTerminated:false,Reason:0,Phase:0},"Finite author finalizer was unexpectedly terminated.");return;}
        Check(C(Signal.AuthorEntered)==1&&C(Signal.AuthorPost)==0,"Author finalizer did not start and stop at its execution boundary.");
        if(!result.RetiredBeforeFinalization)
        {
            Check(result.Before is {IsTerminated:false,Executed:>0,Remaining:>0},"Finalizer setup already exhausted allowance.");
            BudgetSnapshot snapshot=result.After??throw new InvalidOperationException("Missing alive finalizer snapshot.");
            Check(snapshot is {IsTerminated:true,Reason:1,Remaining:0,Executed:Limit,Exhausted:true},"Active finalizer native latch/exact allowance differs.");
            Check(snapshot.CleanupExecuted>=0&&snapshot.CleanupRemaining>=0&&snapshot.CleanupExecuted+snapshot.CleanupRemaining==Cleanup,"Finalizer cleanup reserve arithmetic differs.");
            if(scenario is Scenario.ActiveLoopInfiniteFinally or Scenario.AuthorOverrideInfinite)Check(snapshot is {Phase:2,CleanupRemaining:0,CleanupExecuted:Cleanup},"Finalizer cleanup loop did not reach bounded no-author-execution phase.");
            else Check(snapshot.Phase==1,"Finite finalizer cleanup phase differs.");
        }
        if(scenario is Scenario.ActiveLoopFinally or Scenario.UnloadBeforeFinalization or Scenario.AuthorOverrideFinite)
            Check(C(Signal.Finally)==1&&C(Signal.Helper)==1&&C(Signal.Delegate)==1,"Active finalizer bounded private cleanup helper/delegate differs.");
        if(scenario is Scenario.ActiveLoopInfiniteFinally or Scenario.AuthorOverrideInfinite)Check(C(Signal.Finally)==1,"Infinite finalizer cleanup body did not actually start.");
        if(scenario==Scenario.AuthorOverrideFinite)Check(C(Signal.BaseEntered)==1,"Ample cleanup reserve omitted the automatic trusted base-finalizer call.");
        if(scenario==Scenario.AuthorOverrideInfinite)Check(C(Signal.BaseEntered)==0,"Exhausted authored cleanup unexpectedly continued the implicit base-finalizer chain.");
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static Result RunFrame(string directory,Scenario scenario,string mode,string evidence,string nonce)
    {
        AssemblyLoadContext context=Api.Create(directory,mode,Limit);var weak=new WeakReference(context);
        try
        {
            WeakReference target=HoldTarget(context,directory,scenario,evidence);
            WriteInventory(context,evidence);
            string? termination=null;
            if(scenario is Scenario.AlreadyTerminated or Scenario.InheritedTrustedBase)termination=Terminate(context,directory,mode);
            BudgetSnapshot? before=mode=="terminal"?Api.Read(context):null;
            DrainRootAndObserve(mode,evidence);
            BudgetSnapshot? after=mode=="terminal"?Api.Read(context):null;
            DrainSentinels(nonce);
            return new Result(weak,target,before,after,Recorder.Copy(),termination,false);
        }
        finally{context.Unload();if(mode!="stock")Api.AssertRetired(context);}
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static Prepared PrepareRetired(string directory,string mode,string evidence)
    {
        var context=Api.Create(directory,mode,Limit);var weak=new WeakReference(context);
        WeakReference target=HoldTarget(context,directory,Scenario.UnloadBeforeFinalization,evidence);WriteInventory(context,evidence);
        Check(Control(context,directory).PrepareCleanup()==7,"Retired-context cleanup dependency preparation differs.");
        BudgetSnapshot? before=mode=="terminal"?Api.Read(context):null;
        context.Unload();if(mode!="stock")Api.AssertRetired(context);
        Console.WriteLine("FINALIZER ROOT held-through-unload=true retiredQueriesRejected=true targetReleased=false");
        return new Prepared(weak,target,before,null);
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static WeakReference HoldTarget(AssemblyLoadContext context,string directory,Scenario scenario,string? evidence=null)
    {object target=Control(context,directory).Create(scenario);trustedRoot=target;if(evidence is not null)WriteFinalizerOwner(target,evidence);return new WeakReference(target);}
    private static void WriteFinalizerOwner(object target,string evidence)
    {
        Type type=target.GetType();MethodInfo method=type.GetMethod("Finalize",BindingFlags.NonPublic|BindingFlags.Instance)!;
        var row=new{targetType=type.FullName,targetAssembly=type.Assembly.GetName().Name,targetCollectible=type.Assembly.IsCollectible,
            definingType=method.DeclaringType!.FullName,definingAssembly=method.Module.Assembly.GetName().Name,definingCollectible=method.Module.Assembly.IsCollectible,
            module=method.Module.ModuleVersionId.ToString(),token=$"0x{method.MetadataToken:x8}",signature=method.ToString()};
        File.WriteAllText(Path.Combine(evidence,"finalizer-owner.json"),JsonSerializer.Serialize(row,new JsonSerializerOptions{WriteIndented=true}));
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static IControl Control(AssemblyLoadContext context,string directory)=>(IControl)Activator.CreateInstance(
        context.LoadFromAssemblyPath(Path.Combine(directory,"FinalizerProbe.Payload.dll")).GetType("FinalizerUGC.Payload.Entry",true)!)!;
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static string? Terminate(AssemblyLoadContext context,string directory,string mode)
    {try{Control(context,directory).Terminate();if(mode=="terminal")throw new InvalidOperationException("Termination loop returned.");return null;}catch(Exception exception){return exception.GetType().FullName;}}
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void ClearRoot()=>trustedRoot=null;
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void DrainRootAndObserve(string mode,string evidence)
    {
        MethodInfo? method=WindowsEntryObservation.Enabled?trustedRoot!.GetType().GetMethod("Finalize",BindingFlags.NonPublic|BindingFlags.Instance):null;
        ClearRoot();DrainTarget();
        if(method is null)return;
        bool authored=method.Module.Assembly.IsCollectible;
        Signal signal=authored?Signal.AuthorEntered:Signal.BaseEntered;
        int entered=Recorder.Copy()[(int)signal];
        object observation=entered==0?new{skipped=true,reason="No finalizer entry counter; suppressed body supplies no execution evidence",method=method.DeclaringType!.FullName+".Finalize"}:
            WindowsEntryObservation.Capture(method,authored&&mode is "terminal" or "required",$"counter={signal};value={entered};actual finalization drain returned");
        File.WriteAllText(Path.Combine(evidence,"post-finalizer-entry.json"),JsonSerializer.Serialize(observation,new JsonSerializerOptions{WriteIndented=true}));
    }
    private static void DrainTarget(){GC.Collect();GC.WaitForPendingFinalizers();GC.Collect();GC.WaitForPendingFinalizers();GC.Collect();}
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void CreateSentinel()=>_ = new QueueSentinel();
    private static void DrainSentinels(string nonce)
    {
        for(int pass=1;pass<=2;pass++){CreateSentinel();DrainTarget();Check(Recorder.Copy()[(int)Signal.Sentinel]==pass,"Trusted finalization queue did not advance.");Console.WriteLine($"FINALIZER QUEUE nonce={nonce} pass={pass} sentinel=true");}
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static Outcome GoodFrame(string directory,string mode)
    {
        var context=Api.Create(directory,mode,1000000);var weak=new WeakReference(context);
        try{return new Outcome(weak,Control(context,directory).Good(),Recorder.Copy(),mode=="terminal"?Api.Read(context):null);}
        finally{context.Unload();if(mode!="stock")Api.AssertRetired(context);}
    }
    private static void Collect(WeakReference context){for(int pass=0;pass<12&&context.IsAlive;pass++){GC.Collect();GC.WaitForPendingFinalizers();GC.Collect();}Check(!context.IsAlive,"Finalizer context retained after frames returned.");}
    private static void WriteInventory(AssemblyLoadContext context,string evidence)
    {
        const BindingFlags flags=BindingFlags.DeclaredOnly|BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static;
        var rows=context.Assemblies.SelectMany(a=>a.GetTypes().SelectMany(t=>t.GetMethods(flags).Cast<MethodBase>().Concat(t.GetConstructors(flags)).Distinct()
            .Select(m=>new{assembly=a.GetName().Name,module=a.ManifestModule.ModuleVersionId.ToString(),type=t.FullName,method=m.Name,token=$"0x{m.MetadataToken:x8}",signature=m.ToString()}))).ToArray();
        File.WriteAllText(Path.Combine(evidence,"method-inventory.json"),JsonSerializer.Serialize(rows,new JsonSerializerOptions{WriteIndented=true}));
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void FatalFrame(string directory,string name,string nonce,string mode,string evidence)
    {
        bool canceled=name.Contains("Canceled",StringComparison.Ordinal);
        if(name.StartsWith("FatalTrusted",StringComparison.Ordinal))HoldTrustedFatal(canceled,evidence);
        else
        {
            var context=Api.Create(directory,mode,1000000);HoldTarget(context,directory,canceled?Scenario.ExplicitCanceled:Scenario.ExplicitInvalid,evidence);
            if(mode=="terminal")Check(!Api.Read(context).IsTerminated,"Explicit authored exception control was already terminal.");
            // Fatal experiment intentionally retains its ALC until process termination.
            fatalContext=context;
        }
        string exception=canceled?"System.OperationCanceledException":"System.InvalidOperationException";
        Console.WriteLine($"FINALIZER FATAL ARMED nonce={nonce} case={name} mode={mode} exception={exception} nativeLatchBefore=false");Console.Error.Flush();
        ClearRoot();DrainTarget();
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void HoldTrustedFatal(bool canceled,string evidence)
    {object target=new TrustedFatal(canceled);trustedRoot=target;WriteFinalizerOwner(target,evidence);}
    private sealed class QueueSentinel{~QueueSentinel(){Recorder.Mark(Signal.Sentinel);}}
    private sealed class TrustedFatal(bool canceled)
    {~TrustedFatal(){if(canceled)throw new OperationCanceledException("trusted finalizer ordinary cancellation");throw new InvalidOperationException("trusted finalizer ordinary invalid operation");}}
}
internal readonly record struct BudgetSnapshot(long Remaining,long Executed,bool Exhausted,bool IsTerminated,int Reason,int Phase,long CleanupRemaining,long CleanupExecuted);
internal sealed record Result(WeakReference Context,WeakReference Target,BudgetSnapshot? Before,BudgetSnapshot? After,int[] Counts,string? TerminationException,bool RetiredBeforeFinalization);
internal sealed record Prepared(WeakReference Context,WeakReference Target,BudgetSnapshot? Before,string? TerminationException);
internal sealed record Outcome(WeakReference Context,int Value,int[] Counts,BudgetSnapshot? Snapshot);
internal static class Api
{
    private static Func<string,Func<AssemblyLoadContext,AssemblyName,Assembly?>,long,long,AssemblyLoadContext> terminal=null!;
    private static Func<string,Func<AssemblyLoadContext,AssemblyName,Assembly?>,AssemblyLoadContext> required=null!;
    private static Func<AssemblyLoadContext,long> remaining=null!,executed=null!,cleanupRemaining=null!,cleanupExecuted=null!;
    private static Func<AssemblyLoadContext,bool> exhausted=null!,terminated=null!;
    private static Func<AssemblyLoadContext,int> reason=null!,phase=null!,policy=null!;
    public static void Initialize(string evidence)
    {
        const BindingFlags flags=BindingFlags.NonPublic|BindingFlags.Static|BindingFlags.Instance|BindingFlags.DeclaredOnly;
        MethodInfo Get(string name){var method=typeof(AssemblyLoadContext).GetMethod(name,flags)??throw new PlatformNotSupportedException("Missing "+name);Program.Check(method.IsPrivate,"Expected private bridge: "+name);return method;}
        MethodInfo boundary=typeof(GC).GetMethod("RuneCLR_GetTerminalFinalizerBoundaryVersion",flags)??throw new PlatformNotSupportedException("Finalizer boundary unavailable.");
        Program.Check(boundary.IsPrivate&&boundary.IsStatic&&boundary.CreateDelegate<Func<int>>()()==1,"Finalizer boundary version differs.");
        Program.Check(Get("RuneCLR_GetTerminalPrototypeVersion").CreateDelegate<Func<int>>()()==1,"Terminal prototype version differs.");
        terminal=Get("RuneCLR_CreateTerminalPrototype").CreateDelegate<Func<string,Func<AssemblyLoadContext,AssemblyName,Assembly?>,long,long,AssemblyLoadContext>>();
        required=Get("RuneCLR_CreateInterpreterRequired").CreateDelegate<Func<string,Func<AssemblyLoadContext,AssemblyName,Assembly?>,AssemblyLoadContext>>();
        remaining=Get("RuneCLR_GetInstructionMeterRemaining").CreateDelegate<Func<AssemblyLoadContext,long>>();
        executed=Get("RuneCLR_GetInstructionMeterExecuted").CreateDelegate<Func<AssemblyLoadContext,long>>();
        exhausted=Get("RuneCLR_GetInstructionMeterExhausted").CreateDelegate<Func<AssemblyLoadContext,bool>>();
        terminated=Get("RuneCLR_GetTerminalPrototypeIsTerminated").CreateDelegate<Func<AssemblyLoadContext,bool>>();
        reason=Get("RuneCLR_GetTerminalPrototypeReason").CreateDelegate<Func<AssemblyLoadContext,int>>();
        phase=Get("RuneCLR_GetTerminalPrototypePhase").CreateDelegate<Func<AssemblyLoadContext,int>>();
        cleanupRemaining=Get("RuneCLR_GetTerminalPrototypeCleanupRemaining").CreateDelegate<Func<AssemblyLoadContext,long>>();
        cleanupExecuted=Get("RuneCLR_GetTerminalPrototypeCleanupExecuted").CreateDelegate<Func<AssemblyLoadContext,long>>();
        policy=Get("RuneCLR_GetExecutionPolicy").CreateDelegate<Func<AssemblyLoadContext,int>>();
        File.WriteAllText(Path.Combine(evidence,"boundary-api.json"),JsonSerializer.Serialize(new{version=1,boundarySignature=boundary.ToString(),terminalVersion=1},new JsonSerializerOptions{WriteIndented=true}));
        Console.WriteLine("FINALIZER API boundaryVersion=1 terminalVersion=1 private-api=true");
    }
    public static AssemblyLoadContext Create(string directory,string mode,long limit)
    {
        Func<AssemblyLoadContext,AssemblyName,Assembly?> resolver=(context,name)=>{if(name.Name==typeof(IControl).Assembly.GetName().Name)return typeof(IControl).Assembly;string path=Path.Combine(directory,name.Name+".dll");return File.Exists(path)?context.LoadFromAssemblyPath(path):null;};
        string name="finalizer-"+Guid.NewGuid().ToString("N");
        AssemblyLoadContext context=mode switch{"terminal"=>terminal(name,resolver,limit,4096),"required"=>required(name,resolver),_=>new FixtureContext(name,resolver)};
        Program.Check(context.IsCollectible,"Fixture context must be collectible.");
        if(mode is not ("stock" or "default"))Program.Check(policy(context)==(mode=="ordinary"?0:1),"Native context policy differs.");
        return context;
    }
    public static BudgetSnapshot Read(AssemblyLoadContext context)=>new(remaining(context),executed(context),exhausted(context),terminated(context),reason(context),phase(context),cleanupRemaining(context),cleanupExecuted(context));
    public static void AssertRetired(AssemblyLoadContext context)
    {
        int rejected=0;Action[] queries=[()=>remaining(context),()=>executed(context),()=>exhausted(context),()=>terminated(context),()=>reason(context),()=>phase(context),()=>cleanupRemaining(context),()=>cleanupExecuted(context)];
        foreach(var query in queries){try{query();}catch(InvalidOperationException){rejected++;}}
        Program.Check(rejected==8,"Retired finalizer context query reached native binder.");Console.WriteLine("FINALIZER RETIRED rejected=8 exception=System.InvalidOperationException");
    }
    private sealed class FixtureContext(string name,Func<AssemblyLoadContext,AssemblyName,Assembly?> resolver):AssemblyLoadContext(name,true)
    {protected override Assembly? Load(AssemblyName name)=>resolver(this,name);}
}
