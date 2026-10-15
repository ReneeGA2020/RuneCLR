using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using System.Text.Json;
using TerminalProbe.Contract;
using RuneCLR.Experiments;
namespace TerminalProbe.Host;
internal static class Program
{
    internal const long ExecutionLimit = 2048, CleanupLimit = 4096;
    internal static void Check(bool condition,string reason) { if(!condition) throw new InvalidOperationException(reason); }
    public static int Main(string[] args)
    {
        Console.SetOut(Console.Error);
        if(args.Length!=5) throw new ArgumentException("Expected payload directory, evidence directory, case, nonce and terminal/ordinary/diagnostic/stock mode.");
        string directory=Path.GetFullPath(args[0]), evidence=Path.GetFullPath(args[1]), name=args[2], nonce=args[3], mode=args[4];
        Check(nonce.Length==32 && nonce.All(Uri.IsHexDigit),"Owned nonce must be 32 hex digits.");
        Check(mode is "terminal" or "ordinary" or "diagnostic" or "stock","Unknown mode.");
        Directory.CreateDirectory(evidence); Recorder.Reset();
        if(mode!="stock") Api.Initialize(evidence);
        Console.WriteLine($"TERMINAL RUN nonce={nonce} case={name} mode={mode} runtime={System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription}");
        var rows=new List<ScalarOutcome>();
        if(name=="Recovery")
        {
            Check(mode=="terminal","Recovery requires actual terminal prototype.");
            for(int session=1;session<=20;session++)
            {
                Recorder.Reset();
                Outcome bad=RunFrame(directory,Scenario.BroadCatch,mode,0,ExecutionLimit); Validate(bad,Scenario.BroadCatch,mode); Collect(bad.Context);
                Outcome good=RunFrame(directory,Scenario.Good,mode,1,1000000); Validate(good,Scenario.Good,mode); Collect(good.Context);
                rows.Add(Scalar(bad,session,"bad")); rows.Add(Scalar(good,session,"good"));
                Console.WriteLine($"PASS terminal-recovery session={session} badCollected=true goodCollected=true goodValue=73 starts=1");
            }
        }
        else if(name=="TwoContexts")
        {
            Check(mode=="terminal","TwoContexts requires actual terminal prototype.");
            var pair=TwoFrames(directory); Collect(pair.Bad.Context); Collect(pair.Good.Context);
            Validate(pair.Bad,Scenario.BroadCatch,mode); Validate(pair.Good,Scenario.Good,mode);
            rows.Add(Scalar(pair.Bad,1,"bad")); rows.Add(Scalar(pair.Good,1,"good"));
            Console.WriteLine("PASS terminal-two-contexts ownerIsolated=true badCollected=true goodCollected=true");
        }
        else
        {
            Scenario scenario=Enum.Parse<Scenario>(name);
            Outcome outcome=RunFrame(directory,scenario,mode,0,scenario==Scenario.Good?1000000:ExecutionLimit,evidence);
            Validate(outcome,scenario,mode); Collect(outcome.Context); rows.Add(Scalar(outcome,1,"case"));
            Console.WriteLine($"PASS terminal-case={name} collected=true counts={JsonSerializer.Serialize(outcome.Counts)} snapshot={JsonSerializer.Serialize(outcome.Snapshot)} exception={outcome.ExceptionType}");
        }
        File.WriteAllText(Path.Combine(evidence,"result.json"),JsonSerializer.Serialize(new {passed=true,nonce,scenario=name,mode,rows,
            prototypeOnly=true,finalizersIntegrated=false,nativeEntryProof=false},new JsonSerializerOptions{WriteIndented=true}));
        Console.WriteLine($"TERMINAL COMPLETE nonce={nonce} case={name} mode={mode} rows={rows.Count} prototypeOnly=true");
        return 0;
    }
    private static ScalarOutcome Scalar(Outcome result,int session,string role) => new(session,role,result.Returned,result.Value,result.ExceptionType,result.Counts,result.Snapshot,result.Ownership,result.Entry);
    private static int Count(Outcome result,Signal signal)=>result.Counts[(int)signal];
    private static void Validate(Outcome result,Scenario scenario,string mode)
    {
        Check(result.Counts.Length==(int)Signal.Count,"Recorder length differs.");
        if(scenario==Scenario.Good)
        {
            Check(result.Returned && result.Value==73 && Count(result,Signal.Starts)==1 && Count(result,Signal.Good)==1,"Independent good session state/value differs.");
            if(mode=="terminal") Check(result.Snapshot is { IsTerminated:false, Reason:0, Phase:0 },"Good context unexpectedly terminated.");
            return;
        }
        if(mode!="terminal")
        {
            if(scenario==Scenario.ThrowingFinally) Check(!result.Returned && result.ExceptionType==typeof(InvalidOperationException).FullName,"Ordinary throwing finally control differs.");
            else Check(result.Returned && result.Value==(scenario==Scenario.CatchReturn?99:17),"Finite ordinary/diagnostic control did not return expected value.");
            if(scenario is Scenario.TypedCatch or Scenario.BroadCatch or Scenario.CatchReturn) Check(Count(result,Signal.Catch)==1,"Actual matching sentinel catch control missing.");
            if(scenario is Scenario.Filter or Scenario.SignalFilter) Check(Count(result,Signal.FilterEntered)==1 && Count(result,Signal.FilterReturned)==1 && Count(result,Signal.FilterCatch)==1,"Actual ordinary filter control missing.");
            if(scenario is Scenario.FiniteFinally or Scenario.NestedFinally) Check(Count(result,Signal.Helper)>0 && Count(result,Signal.Delegate)>0,"Ordinary private cleanup helper/delegate missing.");
            if(scenario==Scenario.TrustedReenter) Check(Count(result,Signal.TrustedCaught)==1 && Count(result,Signal.ReentrySucceeded)==1 && Count(result,Signal.Good)==1,"Ordinary trusted callback/reentry missing.");
            if(mode=="diagnostic") Check(result.Snapshot is {Remaining:0, Executed:>ExecutionLimit, Exhausted:true, IsTerminated:false},"Diagnostic control did not continue after exhausting accounting limit.");
            return;
        }
        Check(!result.Returned && result.ExceptionType is not null,"Terminal script returned without trusted host failure.");
        Check(result.Snapshot is {Remaining:0, Executed:ExecutionLimit, Exhausted:true, IsTerminated:true, Reason:1},"Native terminal latch/execution boundary differs.");
        Check(Count(result,Signal.Catch)==0 && Count(result,Signal.Post)==0 && Count(result,Signal.FilterCatch)==0,"Terminal author catch/continuation executed.");
        BudgetSnapshot snapshot=result.Snapshot!.Value;
        Check(snapshot.CleanupRemaining>=0 && snapshot.CleanupExecuted>=0 && snapshot.CleanupRemaining+snapshot.CleanupExecuted==CleanupLimit,"Cleanup reserve arithmetic differs.");
        if(scenario==Scenario.Filter) Check(Count(result,Signal.FilterEntered)==1 && Count(result,Signal.FilterReturned)==0,"Exhaustion-in-filter escape differs.");
        if(scenario==Scenario.SignalFilter) Check(Count(result,Signal.FilterEntered)==0 && Count(result,Signal.FilterReturned)==0,"Filter on terminal sentinel was executed.");
        if(scenario==Scenario.FiniteFinally) Check(Count(result,Signal.Finally)==1 && Count(result,Signal.Helper)==1 && Count(result,Signal.Delegate)==1 && snapshot.Phase==1 && snapshot.CleanupExecuted>0,"Finite finally helper/delegate reserve path differs.");
        if(scenario==Scenario.NestedFinally) Check(Count(result,Signal.InnerFinally)==1 && Count(result,Signal.OuterFinally)==1 && Count(result,Signal.Helper)==2 && Count(result,Signal.Delegate)==2 && snapshot.Phase==1,"Nested finite cleanup differs.");
        if(scenario==Scenario.InfiniteFinally) Check(Count(result,Signal.InnerFinally)==1 && Count(result,Signal.OuterFinally)==0 && snapshot.Phase==2 && snapshot.CleanupRemaining==0 && snapshot.CleanupExecuted==CleanupLimit,"Infinite cleanup did not exhaust bounded reserve and suppress outer author finally.");
        if(scenario==Scenario.ThrowingFinally) Check(Count(result,Signal.ThrowingFinally)==1 && Count(result,Signal.OuterFinally)==1 && snapshot.Phase==1,"Throwing cleanup lost sticky terminal reason or outer unwind.");
        if(scenario==Scenario.Constructor) Check(Count(result,Signal.ConstructorBefore)==1 && Count(result,Signal.ConstructorAfter)==0 && Count(result,Signal.Enter)==0,"Constructor budget boundary differs.");
        if(scenario==Scenario.StaticConstructor) Check(Count(result,Signal.StaticBefore)==1 && Count(result,Signal.StaticAfter)==0 && Count(result,Signal.Enter)==0,"Static constructor budget boundary differs.");
        if(scenario==Scenario.TrustedReenter) Check(Count(result,Signal.TrustedEntered)==1 && Count(result,Signal.TrustedCaught)==1 && Count(result,Signal.ReentryAttempt)==1 && Count(result,Signal.ReentrySucceeded)==0 && Count(result,Signal.Good)==0,"Trusted catch or sticky author reentry boundary differs.");
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static Outcome RunFrame(string directory,Scenario scenario,string mode,int channel,long limit,string? evidence=null)
    {
        Recorder.Scenario=scenario; Recorder.Channel=channel; Recorder.FiniteControl=mode!="terminal";
        AssemblyLoadContext context=Api.Create(directory,mode,limit); var weak=new WeakReference(context);
        bool returned=false; int value=0; string? exceptionType=null;
        try
        {
            try
            {
                Assembly assembly=context.LoadFromAssemblyPath(Path.Combine(directory,"TerminalProbe.Payload.dll"));
                Type type=assembly.GetType("TerminalUGC.Payload.Entry",true)!;
                IWork work=(IWork)Activator.CreateInstance(type,channel)!;
                value=work.Run(scenario,channel); returned=true;
            }
            catch(Exception exception) { exceptionType=exception.GetType().FullName; }
            BudgetSnapshot? snapshot=mode=="terminal"?Api.Read(context):mode=="diagnostic"?Api.ReadDiagnostic(context):null;
            if(mode is "ordinary" or "diagnostic") Api.AssertUnbudgeted(context);
            if(evidence is not null) WriteInventory(context,evidence);
            EntryObservation? entry=ObserveExecuted(context,scenario,mode,channel);
            return new Outcome(weak,returned,value,exceptionType,Recorder.Copy(channel),snapshot,Entry:entry);
        }
        finally { context.Unload(); if(mode!="stock") Api.AssertRetired(context); }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static (Outcome Bad,Outcome Good) TwoFrames(string directory)
    {
        var bad=Api.Create(directory,"terminal",ExecutionLimit); var good=Api.Create(directory,"terminal",1000000);
        var bw=new WeakReference(bad); var gw=new WeakReference(good);
        try
        {
            BudgetSnapshot goodBefore=Api.Read(good),badBefore=Api.Read(bad); bool returned=false; string? error=null;
            Recorder.Scenario=Scenario.BroadCatch; Recorder.Channel=0; Recorder.FiniteControl=false;
            try { Load(bad,directory,0).Run(Scenario.BroadCatch,0); returned=true; } catch(Exception exception) { error=exception.GetType().FullName; }
            BudgetSnapshot goodAfterBad=Api.Read(good),badAfterBad=Api.Read(bad);
            Check(goodAfterBad==goodBefore,"Bad session charged or terminated inactive good context.");
            var failed=new Outcome(bw,returned,0,error,Recorder.Copy(0),badAfterBad);
            Recorder.Scenario=Scenario.Good; Recorder.Channel=1;
            int value=Load(good,directory,1).Run(Scenario.Good,1);
            BudgetSnapshot badAfterGood=Api.Read(bad),goodAfterGood=Api.Read(good);
            Check(badAfterGood==failed.Snapshot,"Good session recharged/reactivated bad context.");
            var ownership=new Dictionary<string,BudgetSnapshot>{["badBefore"]=badBefore,["goodBefore"]=goodBefore,["goodAfterBad"]=goodAfterBad,
                ["badAfterBad"]=badAfterBad,["badAfterGood"]=badAfterGood,["goodAfterGood"]=goodAfterGood};
            return(failed with{Ownership=ownership,Entry=ObserveExecuted(bad,Scenario.BroadCatch,"terminal",0)},
                new Outcome(gw,true,value,null,Recorder.Copy(1),goodAfterGood,Entry:ObserveExecuted(good,Scenario.Good,"terminal",1)));
        }
        finally {bad.Unload();good.Unload();Api.AssertRetired(bad);Api.AssertRetired(good);}
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static IWork Load(AssemblyLoadContext context,string directory,int channel)=>(IWork)Activator.CreateInstance(
        context.LoadFromAssemblyPath(Path.Combine(directory,"TerminalProbe.Payload.dll")).GetType("TerminalUGC.Payload.Entry",true)!,channel)!;
    private static EntryObservation? ObserveExecuted(AssemblyLoadContext context,Scenario scenario,string mode,int channel)
    {
        if(!WindowsEntryObservation.Enabled)return null;
        Type type=context.Assemblies.Single(a=>a.GetName().Name=="TerminalProbe.Payload").GetType("TerminalUGC.Payload.Entry",true)!;
        int[] counts=Recorder.Copy(channel);
        MethodBase method=scenario==Scenario.StaticConstructor?type.TypeInitializer!:scenario==Scenario.Constructor?
            type.GetConstructor(new[]{typeof(int)})!:type.GetMethod("Run")!;
        Signal signal=scenario==Scenario.StaticConstructor?Signal.StaticBefore:scenario==Scenario.Constructor?Signal.ConstructorBefore:Signal.Enter;
        Check(counts[(int)signal]>0,"Selected entry lacks actual invocation counter.");
        return WindowsEntryObservation.Capture(method,mode is "terminal" or "diagnostic",$"counter={signal};value={counts[(int)signal]};callback frame returned or host caught actual failure");
    }
    private static void Collect(WeakReference context)
    {for(int pass=0;pass<12&&context.IsAlive;pass++){GC.Collect();GC.WaitForPendingFinalizers();GC.Collect();}Check(!context.IsAlive,"Context retained after author frame returned.");}
    private static void WriteInventory(AssemblyLoadContext context,string evidence)
    {
        const BindingFlags flags=BindingFlags.DeclaredOnly|BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static;
        var rows=context.Assemblies.SelectMany(a=>a.GetTypes().SelectMany(t=>t.GetMethods(flags).Cast<MethodBase>().Concat(t.GetConstructors(flags)).Distinct()
            .Select(m=>new{assembly=a.GetName().Name,module=a.ManifestModule.ModuleVersionId.ToString(),type=t.FullName,method=m.Name,token=$"0x{m.MetadataToken:x8}",signature=m.ToString()}))).ToArray();
        File.WriteAllText(Path.Combine(evidence,"method-inventory.json"),JsonSerializer.Serialize(rows,new JsonSerializerOptions{WriteIndented=true}));
    }
}
internal readonly record struct BudgetSnapshot(long Remaining,long Executed,bool Exhausted,bool IsTerminated,int Reason,int Phase,long CleanupRemaining,long CleanupExecuted);
internal sealed record Outcome(WeakReference Context,bool Returned,int Value,string? ExceptionType,int[] Counts,BudgetSnapshot? Snapshot,Dictionary<string,BudgetSnapshot>? Ownership=null,EntryObservation? Entry=null);
internal sealed record ScalarOutcome(int Session,string Role,bool Returned,int Value,string? ExceptionType,int[] Counts,BudgetSnapshot? Snapshot,Dictionary<string,BudgetSnapshot>? Ownership,EntryObservation? Entry);

internal static class Api
{
    private static Func<string,Func<AssemblyLoadContext,AssemblyName,Assembly?>,long,long,AssemblyLoadContext> terminal=null!;
    private static Func<string,Func<AssemblyLoadContext,AssemblyName,Assembly?>,long,AssemblyLoadContext> diagnostic=null!;
    private static Func<AssemblyLoadContext,long> remaining=null!,executed=null!,cleanupRemaining=null!,cleanupExecuted=null!;
    private static Func<AssemblyLoadContext,bool> exhausted=null!,terminated=null!;
    private static Func<AssemblyLoadContext,int> reason=null!,phase=null!,policy=null!;
    public static void Initialize(string evidence)
    {
        const BindingFlags flags=BindingFlags.NonPublic|BindingFlags.Static|BindingFlags.Instance|BindingFlags.DeclaredOnly;
        MethodInfo Get(string name){var method=typeof(AssemblyLoadContext).GetMethod(name,flags)??throw new PlatformNotSupportedException("Missing "+name);Program.Check(method.IsPrivate,"Expected private bridge: "+name);return method;}
        Program.Check(Get("RuneCLR_GetTerminalPrototypeVersion").CreateDelegate<Func<int>>()()==1,"Terminal prototype capability version differs.");
        terminal=Get("RuneCLR_CreateTerminalPrototype").CreateDelegate<Func<string,Func<AssemblyLoadContext,AssemblyName,Assembly?>,long,long,AssemblyLoadContext>>();
        diagnostic=Get("RuneCLR_CreateInstructionMetered").CreateDelegate<Func<string,Func<AssemblyLoadContext,AssemblyName,Assembly?>,long,AssemblyLoadContext>>();
        remaining=Get("RuneCLR_GetInstructionMeterRemaining").CreateDelegate<Func<AssemblyLoadContext,long>>();
        executed=Get("RuneCLR_GetInstructionMeterExecuted").CreateDelegate<Func<AssemblyLoadContext,long>>();
        exhausted=Get("RuneCLR_GetInstructionMeterExhausted").CreateDelegate<Func<AssemblyLoadContext,bool>>();
        terminated=Get("RuneCLR_GetTerminalPrototypeIsTerminated").CreateDelegate<Func<AssemblyLoadContext,bool>>();
        reason=Get("RuneCLR_GetTerminalPrototypeReason").CreateDelegate<Func<AssemblyLoadContext,int>>();
        phase=Get("RuneCLR_GetTerminalPrototypePhase").CreateDelegate<Func<AssemblyLoadContext,int>>();
        cleanupRemaining=Get("RuneCLR_GetTerminalPrototypeCleanupRemaining").CreateDelegate<Func<AssemblyLoadContext,long>>();
        cleanupExecuted=Get("RuneCLR_GetTerminalPrototypeCleanupExecuted").CreateDelegate<Func<AssemblyLoadContext,long>>();
        policy=Get("RuneCLR_GetExecutionPolicy").CreateDelegate<Func<AssemblyLoadContext,int>>();
        var declarations=typeof(AssemblyLoadContext).GetMethods(flags).Where(m=>m.Name.Contains("TerminalPrototype",StringComparison.Ordinal))
            .Select(m=>new{m.Name,signature=m.ToString(),m.IsPrivate,m.IsStatic}).ToArray();
        Program.Check(!declarations.Any(m=>m.Name.Contains("Set",StringComparison.Ordinal)),"Unexpected terminal reset/setter method.");
        File.WriteAllText(Path.Combine(evidence,"terminal-api.json"),JsonSerializer.Serialize(new{version=1,declarations},new JsonSerializerOptions{WriteIndented=true}));
        Console.WriteLine("TERMINAL API version=1 private-api=true prototypeOnly=true finalizersIntegrated=false");
    }
    public static AssemblyLoadContext Create(string directory,string mode,long limit)
    {
        Func<AssemblyLoadContext,AssemblyName,Assembly?> resolver=(context,name)=>
        {if(name.Name==typeof(IWork).Assembly.GetName().Name)return typeof(IWork).Assembly;string path=Path.Combine(directory,name.Name+".dll");return File.Exists(path)?context.LoadFromAssemblyPath(path):null;};
        string name="terminal-"+Guid.NewGuid().ToString("N");
        AssemblyLoadContext context=mode switch {"terminal"=>terminal(name,resolver,limit,Program.CleanupLimit),"diagnostic"=>diagnostic(name,resolver,limit),_=>new FixtureContext(name,resolver)};
        Program.Check(context.IsCollectible,"Fixture must be collectible.");
        if(mode!="stock")Program.Check(policy(context)==(mode=="ordinary"?0:1),"Native policy acknowledgement differs.");
        if(mode=="terminal")Program.Check(Read(context)==new BudgetSnapshot(limit,0,false,false,0,0,Program.CleanupLimit,0),"Initial terminal snapshot differs.");
        return context;
    }
    public static BudgetSnapshot Read(AssemblyLoadContext context)=>new(remaining(context),executed(context),exhausted(context),terminated(context),reason(context),phase(context),cleanupRemaining(context),cleanupExecuted(context));
    public static BudgetSnapshot ReadDiagnostic(AssemblyLoadContext context)=>new(remaining(context),executed(context),exhausted(context),false,0,0,0,0);
    public static void AssertUnbudgeted(AssemblyLoadContext context)
    {
        int rejected=0;
        Action[] queries=[()=>terminated(context),()=>reason(context),()=>phase(context),()=>cleanupRemaining(context),()=>cleanupExecuted(context)];
        foreach(var query in queries){try{query();}catch(InvalidOperationException){rejected++;}}
        Program.Check(rejected==5,"Unbudgeted context exposed terminal state.");
        Console.WriteLine("TERMINAL UNBUDGETED rejected=5 exception=System.InvalidOperationException");
    }
    public static void AssertRetired(AssemblyLoadContext context)
    {
        int rejected=0;
        Action[] queries=[()=>remaining(context),()=>executed(context),()=>exhausted(context),()=>terminated(context),()=>reason(context),()=>phase(context),()=>cleanupRemaining(context),()=>cleanupExecuted(context)];
        foreach(var query in queries){try{query();}catch(InvalidOperationException){rejected++;}}
        Program.Check(rejected==8,"Retired terminal/meter query accessed retired binder.");
        Console.WriteLine("TERMINAL RETIRED rejected=8 exception=System.InvalidOperationException");
    }
    private sealed class FixtureContext(string name,Func<AssemblyLoadContext,AssemblyName,Assembly?> resolver):AssemblyLoadContext(name,true)
    {protected override Assembly? Load(AssemblyName name)=>resolver(this,name);}
}
