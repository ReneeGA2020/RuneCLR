using System.Reflection;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text.Json;
using RuneCLR.Runtime;
using RuneCLR.Experiments;
namespace HostBudgetProbe.Host;
internal static class Program
{
    private const long Limit=8192,Cleanup=4096;
    public static int Main(string[] args)
    {
        Console.SetOut(Console.Error);
        if(args.Length is not (5 or 6)||args.Length==6&&args[5]!="--pumped")throw new ArgumentException("Expected payload directory, evidence directory, case, nonce, mode, optional --pumped.");
        bool pumped=args.Length==6;
        string directory=Path.GetFullPath(args[0]),evidence=Path.GetFullPath(args[1]),name=args[2],nonce=args[3],mode=args[4];
        Check(nonce.Length==32&&nonce.All(Uri.IsHexDigit),"Invalid nonce.");Check(mode is "budget" or "stock" or "missing-capability","Unknown mode.");
        Directory.CreateDirectory(evidence);
        Console.WriteLine($"HOST BUDGET RUN nonce={nonce} case={name} mode={mode} runtime={System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription}");
        if(mode=="missing-capability")
        {
            string path=Path.Combine(evidence,"author-not-present.dll");Check(!File.Exists(path),"Missing-author refusal path unexpectedly exists.");
            try{var package=new MapPackage("missing",path,"HostBudgetUGC.Missing");if(pumped)new MapRunner().Start(package,Options(Limit));else new MapRunner().Run(package,Options(Limit));throw new InvalidOperationException("Budget capability unexpectedly accepted.");}
            catch(PlatformNotSupportedException){Console.WriteLine($"HOST BUDGET REFUSAL nonce={nonce} exception=System.PlatformNotSupportedException beforeAuthorFile=true");}
            File.WriteAllText(Path.Combine(evidence,"result.json"),JsonSerializer.Serialize(new{passed=true,nonce,scenario=name,mode,beforeAuthorFile=true,exception="System.PlatformNotSupportedException"}));return 0;
        }
        if(mode=="stock"&&name!="Normal")throw new ArgumentException("Stock only runs finite normal control.");
        var rows=new List<object>();
        int count=name is "Recovery" or "Normal"?20:1;
        for(int session=1;session<=count;session++)
        {
            string type=name=="Recovery"?"CatchResume":name;
            MapRunResult result=RunFrame(directory,type,mode,pumped,out var retained,out int hostReturns);Validate(result.Report,type,mode);Collect(result.Unload);GC.KeepAlive(retained);
            if(WindowsEntryObservation.Enabled&&session==1)
            {
                MethodInfo method=typeof(MapRunner).GetMethod(pumped?nameof(MapRunner.Start):nameof(MapRunner.Run))!;
                var entry=WindowsEntryObservation.Capture(method,false,pumped?"MapRunner.Start returned session; host-pumped callbacks completed and retained stopped session collected":"MapRunner.Run returned validated host report and collected ticket");
                File.WriteAllText(Path.Combine(evidence,"trusted-entry.json"),JsonSerializer.Serialize(entry,new JsonSerializerOptions{WriteIndented=true}));
            }
            rows.Add(pumped?(object)new{session,role=name=="Recovery"?"bad":"case",report=result.Report,collected=true,pumped=true,successfulHostReturns=hostReturns,retainedStoppedSessionCollected=true}:new{session,role=name=="Recovery"?"bad":"case",report=result.Report,collected=true});
            if(name=="Recovery")
            {MapRunResult good=RunFrame(directory,"Normal",mode,pumped,out var retainedGood,out int goodReturns);Validate(good.Report,"Normal",mode);Collect(good.Unload);GC.KeepAlive(retainedGood);rows.Add(pumped?(object)new{session,role="good",report=good.Report,collected=true,pumped=true,successfulHostReturns=goodReturns,retainedStoppedSessionCollected=true}:new{session,role="good",report=good.Report,collected=true});}
            Console.WriteLine($"PASS host-budget session={session} case={name} collected=true resources=true");
        }
        File.WriteAllText(Path.Combine(evidence,"result.json"),JsonSerializer.Serialize(new{passed=true,nonce,scenario=name,mode,rows,prototypeOnly=true,
            packageProfileScope="fixed trusted raw-IL fixture; production author finalizers remain unsupported"},new JsonSerializerOptions{WriteIndented=true}));
        Console.WriteLine($"HOST BUDGET COMPLETE nonce={nonce} case={name} mode={mode} rows={rows.Count} prototypeOnly=true");return 0;
    }
    private static MapRunOptions Options(long? limit)
    {
        var options=new MapRunOptions{ExecutionPolicy=limit is null?MapExecutionPolicy.Default:MapExecutionPolicy.RequireInterpreter,TickCount=3,OperationBudgetPerCallback=100000,MaxLogMessages=128};
        // Reflect only the host-owned public API during preparation. Delegate/metadata
        // never crosses the author execution frame. Exact property types are required.
        var execution=typeof(MapRunOptions).GetProperty("PrototypeInstructionBudget")??throw new NotSupportedException("Host budget API absent.");
        var cleanup=typeof(MapRunOptions).GetProperty("PrototypeCleanupInstructionBudget")??throw new NotSupportedException("Host cleanup budget API absent.");
        Check(execution.PropertyType==typeof(long?)&&cleanup.PropertyType==typeof(long),"Host budget option types differ.");
        execution.SetValue(options,limit);cleanup.SetValue(options,Cleanup);return options;
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static MapRunResult RunFrame(string directory,string type,string mode,bool pumped,out MapSession? retained,out int hostReturns)
    {
        string payload=Path.Combine(directory,"HostBudgetProbe.Payload.dll"),helper=Path.Combine(directory,"HostBudgetProbe.Private.dll");
        var package=new MapPackage("host-budget-"+type,payload,"HostBudgetUGC."+type){EntrySha256=Hash(payload),
            Dependencies=[new MapDependency("HostBudgetProbe.Private.dll",AssemblyName.GetAssemblyName(helper).FullName!,Hash(helper))]};
        var options=Options(mode=="stock"?null:type=="Normal"?1000000:Limit);
        retained=null;hostReturns=0;
        if(!pumped)return new MapRunner().Run(package,options);
        // Every callback returns through this trusted host frame; TickCount does not schedule manual sessions.
        retained=new MapRunner().Start(package,options with{TickCount=0});
        int maximumTicks=type=="TickWork"?64:3;
        for(int tick=0;retained.IsRunning&&tick<maximumTicks;tick++)
        {
            Check(retained.CompletedTicks==hostReturns&&retained.Result is null,"Running session state differs before host tick.");
            bool completed=PumpTick(retained);
            if(completed)hostReturns++;
            Check(retained.CompletedTicks==hostReturns,"Tick return and completed count differ.");
        }
        if(type=="TickWork")Check(!retained.IsRunning&&hostReturns>=2&&hostReturns<maximumTicks,"Cumulative quota did not terminate across multiple successful host returns.");
        var result=retained.Stop();
        Check(!retained.IsRunning&&ReferenceEquals(result,retained.Result)&&ReferenceEquals(result,retained.Stop()),"Stopped session did not retain one idempotent scalar result.");
        retained.Dispose();
        bool rejected=false;
        try{retained.Tick();}catch(InvalidOperationException){rejected=true;}
        Check(ReferenceEquals(result,retained.Result)&&rejected,"Stopped or disposed session admitted another tick.");
        return result;
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static bool PumpTick(MapSession session)=>session.Tick();
    private static string Hash(string path)=>Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
    private static void Validate(MapRunReport report,string type,string mode)
    {
        Check(report.ExecutionPolicy==(mode=="stock"?MapExecutionPolicy.Default:MapExecutionPolicy.RequireInterpreter)&&report.ExecutionPolicyVersion==(mode=="stock"?0:1),"Actual policy acknowledgement differs.");
        bool construction=type is "ConstructorLoop" or "StaticConstructorLoop";
        Check(report.CreatedEntities==(construction?0:1)&&report.ReleasedEntities==report.CreatedEntities&&report.RemainingEntities==0,"Host-owned entities not released.");
        if(type=="Normal")
        {Check(report.Outcome==MapRunOutcome.Completed&&report.CompletedTicks==3&&report.Error is null&&report.Logs.SequenceEqual(new[]{"start","static=1","tick=0","tick=1","tick=2","stop"}),"Normal values/static reset/lifecycle differ.");}
        else
        {
            Check(report.Outcome==MapRunOutcome.Failed&&report.Error is not null&&(type=="TickWork"?report.CompletedTicks>=2&&report.CompletedTicks<64:report.CompletedTicks==(type=="StopLoop"?3:0)),"Failure outcome/completed ticks untruthful.");
            if(type=="TickWork")
            {
                // The failing callback can log before its final return dispatch exhausts the allowance.
                int workLogs=report.Logs.Count-1;
                Check(workLogs>=report.CompletedTicks&&workLogs<=report.CompletedTicks+1&&report.Logs.SequenceEqual(new[]{"start"}.Concat(Enumerable.Range(0,workLogs).Select(tick=>"work="+tick))),"Finite tick logs do not match host-return prefix.");
            }
            Check(!report.Logs.Any(log=>log is "catch" or "broad-catch" or "resume" or "signal-filter" or "filter-catch" or "fallback-catch" or "filter-after" or "tick-after" or "stop-after" or "start-after" or "unexpected-tick"),"Authored catch/filter/continuation escaped terminal policy.");
            if(type=="FiniteCleanup")Check(report.Logs.Contains("finally")&&report.Logs.Contains("private-finally")&&report.Logs.Contains("private-delegate"),"Finite private cleanup did not execute.");
            if(type=="InfiniteCleanup")Check(report.Logs.Contains("private-infinite-finally"),"Infinite private cleanup never entered.");
            if(type=="FilterExhaustion")Check(report.Logs.Contains("filter-before"),"Ordinary filter was not entered before exhausting its budget.");
            if(type=="StopLoop")Check(report.Logs.Contains("stop-before"),"OnStop loop never entered.");
            if(type is "MaliciousMessage" or "ExplicitCanceled")Check(report.Logs.Contains("stop"),"Unlatched ordinary error skipped allowed OnStop.");
            else Check(!report.Logs.Contains("stop"),"OnStop ran after the native terminal latch.");
        }
        var property=typeof(MapRunReport).GetProperty("PrototypeBudget")??throw new NotSupportedException("Host scalar budget report absent.");
        object? snapshot=property.GetValue(report);
        if(mode=="stock"){Check(snapshot is null,"Stock fabricated native budget state.");return;}
        Check(snapshot is not null,"Actual native budget report absent.");
        long ReadLong(string name)=>(long)snapshot!.GetType().GetProperty(name)!.GetValue(snapshot)!;
        bool ReadBool(string name)=>(bool)snapshot!.GetType().GetProperty(name)!.GetValue(snapshot)!;
        int ReadInt(string name)=>(int)snapshot!.GetType().GetProperty(name)!.GetValue(snapshot)!;
        bool terminated=type is not ("Normal" or "MaliciousMessage" or "ExplicitCanceled");
        Check(ReadBool("IsTerminated")==terminated&&ReadInt("Reason")== (terminated?1:0),"Native scalar latch differs from actual case.");
        Check(ReadLong("CleanupRemaining")+ReadLong("CleanupExecuted")==Cleanup,"Cleanup ledger arithmetic differs.");
        Check(ReadLong("ExecutionRemaining")+ReadLong("ExecutionExecuted")== (type=="Normal"?1000000:Limit),"Session execution ledger reset or arithmetic differs.");
        if(terminated)Check(ReadLong("ExecutionRemaining")==0&&ReadLong("ExecutionExecuted")==Limit&&ReadBool("ExecutionExhausted"),"Native total session allowance reset or boundary differs.");
        else Check(ReadLong("ExecutionRemaining")>0&&!ReadBool("ExecutionExhausted"),"Unlatched ordinary error or normal session exhausted unexpectedly.");
        if(!terminated)Check(ReadInt("Phase")==0&&ReadLong("CleanupExecuted")==0,"Active session used termination cleanup reserve.");
        else Check(report.Error!.Contains("The native prototype instruction budget terminated author execution.",StringComparison.Ordinal),"Native termination was reported as an authored ordinary exception.");
        if(type=="FiniteCleanup")Check(ReadInt("Phase")==1&&ReadLong("CleanupExecuted")>0,"Finite finally did not use native cleanup reserve.");
        if(type=="InfiniteCleanup")Check(ReadInt("Phase")==2&&ReadLong("CleanupRemaining")==0&&ReadLong("CleanupExecuted")==Cleanup,"Infinite cleanup was not bounded.");
        if(type=="MaliciousMessage")Check(report.Error!.Contains("HostBudgetUGC.BadMessage",StringComparison.Ordinal),"Error reporting did not copy authored exception type.");
        if(type=="ExplicitCanceled")Check(report.Error!.Contains("System.OperationCanceledException",StringComparison.Ordinal),"Explicit cancellation incorrectly reported as native quota.");
    }
    private static void Collect(UnloadTicket ticket){for(int i=0;i<12&&!ticket.IsCollected;i++){GC.Collect();GC.WaitForPendingFinalizers();GC.Collect();}Check(ticket.IsCollected,"MapRunner retained author state after returning.");}
    private static void Check(bool value,string reason){if(!value)throw new InvalidOperationException(reason);}
}
