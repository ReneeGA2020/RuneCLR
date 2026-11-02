using System.Runtime.CompilerServices;
using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.Loader;
using ReflectionPolicy.CompiledLibrary;
using RuneCLR.Packages;
using RuneCLR.Runtime;

internal static partial class ReflectionPolicyTests
{
    private static void ExerciseSessions()
    {
        var image = File.ReadAllBytes(SessionPackage("SessionScript").AssemblyPath);
        var info = ManagedAssemblyInspector.Inspect(image);
        GameplayCapabilityPolicy.ValidateWithApiPolicy(image, [info.AssemblyName], Contract, new SessionPolicy(), allowReflectionTypeTokens: true);
        SessionHooks.InterpreterPolicy = typeof(AssemblyLoadContext).GetMethod("RuneCLR_GetExecutionPolicy",
            BindingFlags.Instance | BindingFlags.NonPublic)!.CreateDelegate<Func<AssemblyLoadContext, int>>();
        AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", false);
        try
        {
            Expect<PlatformNotSupportedException>(() => new MapRunner().Start(new("missing", "missing-author.dll", "Missing"), SessionOptions()));
        }
        finally { AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", true); }
        Pass("disabling an already-bound bridge rejects before opening a missing author file");
        var retained = ExerciseSuccessfulSession();
        for (int i = 0; i < 15 && !retained.Session.Result!.Unload.IsCollected; i++)
        {
            GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
        }
        Assert(retained.Session.Result!.Unload.IsCollected, "A retained stopped session/flow kept author code alive.");
        GC.KeepAlive(retained.Flow);
        Pass("automatic session binding releases author code while stopped session and captured flow survive");

        foreach (string name in new[] { "DeniedConstructorScript", "DeniedStartScript", "DeniedTickScript", "DeniedStopScript" })
        {
            int before = SessionHooks.Effects;
            using var session = new MapRunner().Start(SessionPackage(name), SessionOptions());
            if (session.IsRunning) session.Tick();
            var result = session.Stop();
            Assert(result.Report.Outcome == MapRunOutcome.Failed && SessionHooks.Effects == before,
                name + " did not reject before the target effect.");
            Assert(result.Report.Error?.Contains("InvalidOperationException", StringComparison.Ordinal) == true,
                name + " did not report a bounded failure.");
            Pass("automatic reflection policy rejects compiled-library target during " + name);
        }
        SessionHooks.Flow = null;
        var tickets = ExerciseLoads().ToList();
        tickets.AddRange(ExerciseReviewFindings());
        for (int i = 0; i < 15 && tickets.Any(ticket => !ticket.IsCollected); i++)
        {
            GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
        }
        Assert(tickets.All(ticket => ticket.IsCollected), "Controlled DLL loading retained a retired UGC context.");
        Pass("all ordinary loading/admission-control sessions unload after their execution stacks return");
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static UnloadTicket[] ExerciseLoads()
    {
        var tickets = new List<UnloadTicket>();
        string safePath = Path.Combine(AppContext.BaseDirectory, "session-author", "System.Custom.UgcDependency.dll");
        var hostCopy = Assembly.LoadFile(safePath);
        var hostTarget = hostCopy.GetType("DynamicDependency.Payload")!.GetMethod("ABC")!;
        Expect<InvalidOperationException>(() => new ReflectionAccessProbe(new SessionPolicy()).Invoke(hostTarget, null));
        Pass("an existing same-name host assembly is not classified as UGC by its identity");
        for (int route = 0; route < 13; route++)
        {
            SessionHooks.Route = route;
            int before = SessionHooks.LoadedEffects;
            SessionHooks.TargetPath = safePath;
            using var allowed = new MapRunner().Start(SessionPackage("LoadingScript"), SessionOptions());
            Assert(allowed.IsRunning, "Allowed load failed at route " + route + ": " + allowed.Result?.Report.Error);
            var result = allowed.Stop();
            tickets.Add(result.Unload);
            Assert(result.Report.Outcome == MapRunOutcome.Completed && SessionHooks.LoadedEffects == before + 1 &&
                result.Report.Logs.Contains("loaded:41"), "Allowed load was not executed under the session.");
            SessionHooks.TargetPath = Path.Combine(AppContext.BaseDirectory, "session-author", "ReflectionPolicy.DeniedDependency.dll");
            using var denied = new MapRunner().Start(SessionPackage("LoadingScript"), SessionOptions());
            tickets.Add(denied.Result!.Unload);
            Assert(!denied.IsRunning && denied.Result!.Report.Outcome == MapRunOutcome.Failed &&
                SessionHooks.LoadedEffects == before + 1, "Denied IL reached loading/cctor at route " + route);
            Pass("ordinary DLL load route " + route + " inherits the session; disallowed IL rejects before target initialization");
        }
        ExerciseLoadBoundaries(safePath, tickets);
        bool eventSeen = false;
        bool eventDenied = false;
        bool emitDenied = false;
        bool stateDenied = false;
        var policyType = typeof(object).Assembly.GetType("System.Reflection.RuneCLRReflectionPolicy", true)!;
        var currentState = policyType.GetField("s_current", BindingFlags.Static | BindingFlags.NonPublic)!;
        var loaderState = typeof(AssemblyLoadContext).GetField("s_runeCLRPolicySessions", BindingFlags.Static | BindingFlags.NonPublic)!;
        AssemblyLoadEventHandler handler = (_, args) =>
        {
            if (args.LoadedAssembly.GetName().Name != "System.Custom.UgcDependency") return;
            eventSeen = true;
            try { SessionHooks.ReflectEffect(); }
            catch (InvalidOperationException) { eventDenied = true; }
            try { AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("UncontrolledEmission"), AssemblyBuilderAccess.RunAndCollect); }
            catch (NotSupportedException) { emitDenied = true; }
            try { currentState.GetValue(null); }
            catch (InvalidOperationException)
            {
                try { loaderState.GetValue(null); }
                catch (InvalidOperationException) { stateDenied = true; }
            }
        };
        AppDomain.CurrentDomain.AssemblyLoad += handler;
        try
        {
            SessionHooks.Route = 8;
            SessionHooks.TargetPath = safePath;
            int before = SessionHooks.Effects;
            using var session = new MapRunner().Start(SessionPackage("LoadingScript"), SessionOptions());
            Assert(session.IsRunning && eventSeen && eventDenied && emitDenied && stateDenied && SessionHooks.Effects == before,
                "Assembly-load callbacks escaped the session while its trusted resolver was active.");
            tickets.Add(session.Stop().Unload);
        }
        finally { AppDomain.CurrentDomain.AssemblyLoad -= handler; }
        Pass("assembly-load event callbacks cannot inherit the host resolver's binding privilege");
        Pass("dynamic assembly emission refuses before creating an unchecked assembly under a UGC session");
        Pass("even a permissive API evaluator cannot expose reflection-policy or loader enforcement state");
        SessionHooks.Flow = null;
        SessionHooks.InterpreterPolicy = null!;
        SessionHooks.TargetPath = "";
        return tickets.ToArray();
    }

    private static void ExerciseLoadBoundaries(string safePath, List<UnloadTicket> tickets)
    {
        string deniedPath = Path.Combine(AppContext.BaseDirectory, "session-author", "ReflectionPolicy.DeniedDependency.dll");
        using (var session = new MapRunner().Start(SessionPackage("SessionScript"), SessionOptions()))
        {
            Assert(session.IsRunning, "Boundary session did not start.");
            var owner = AssemblyLoadContext.All.Single(context => context.Name?.StartsWith("map:reflection-session:", StringComparison.Ordinal) == true);
            Expect<InvalidDataException>(() => owner.LoadFromAssemblyPath(deniedPath));
            Pass("an attached UGC context enforces byte admission even when the host loads outside a callback");
            var flow = SessionHooks.Flow!;
            int before = SessionHooks.LoadedEffects;
            Expect<InvalidOperationException>(() => ExecutionContext.Run(flow, _ => Assembly.LoadFile(safePath), null));
            Assert(SessionHooks.LoadedEffects == before, "A returned activation loaded executable code.");
            Pass("captured returned callback refuses subsequent assembly loading");
            tickets.Add(session.Stop().Unload);
        }
        string directory = Path.Combine(Path.GetTempPath(), "RuneCLR UGC extra files " + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            string path = Path.Combine(directory, "arbitrary file name.dll");
            File.WriteAllText(Path.Combine(directory, "unlisted notes.txt"), "unrelated file");
            File.Copy(safePath, path);
            SessionHooks.Route = 2;
            SessionHooks.TargetPath = path;
            using (var renamed = new MapRunner().Start(SessionPackage("LoadingScript"), SessionOptions()))
            {
                Assert(renamed.IsRunning, "A renamed/unlisted DLL or unrelated file was rejected: " + renamed.Result?.Report.Error);
                var result = renamed.Stop();
                tickets.Add(result.Unload);
                Assert(result.Report.Outcome == MapRunOutcome.Completed, "Renamed DLL session failed.");
            }
            Pass("an unlisted DLL with an arbitrary filename loads alongside unrelated directory files");

            SessionHooks.TargetPath = typeof(SessionHooks).Assembly.Location;
            using (var spoof = new MapRunner().Start(SessionPackage("LoadingScript"), SessionOptions()))
            {
                Assert(!spoof.IsRunning && spoof.Result!.Report.Outcome == MapRunOutcome.Failed,
                    "New bytes replaced a host-provided trusted shared instance.");
                tickets.Add(spoof.Result!.Unload);
            }
            Pass("loading trusted-library bytes does not replace the host-provided shared assembly instance");

            SessionHooks.TargetPath = path;
            using (var snapshot = new MapRunner().Start(SessionPackage("LoadingScript"), SessionOptions() with
            { PrototypeApiPolicy = new MutatingPolicy(path, File.ReadAllBytes(deniedPath)) }))
            {
                Assert(snapshot.IsRunning, "Validated-byte snapshot was replaced by later path contents: " + snapshot.Result?.Report.Error);
                var result = snapshot.Stop();
                tickets.Add(result.Unload);
                Assert(result.Report.Outcome == MapRunOutcome.Completed && File.ReadAllBytes(path).SequenceEqual(File.ReadAllBytes(deniedPath)),
                    "Snapshot mutation control did not execute.");
            }
            Pass("policy-time path replacement cannot replace the exact admitted bytes consumed by the loader");
        }
        finally { Directory.Delete(directory, recursive: true); }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static (MapSession Session, ExecutionContext Flow) ExerciseSuccessfulSession()
    {
        var session = new MapRunner().Start(SessionPackage("SessionScript"), SessionOptions());
        Assert(session.IsRunning, "Session startup failed: " + session.Result?.Report.Error);
        var oldFlow = SessionHooks.Flow!;
        Expect<InvalidOperationException>(() => ExecutionContext.Run(oldFlow, _ => SessionHooks.ReflectEffect(), null));
        Assert(session.Tick() && session.Tick(), "A new activation could not reuse the live session policy.");
        int before = SessionHooks.Effects;
        SessionHooks.ReflectEffect();
        Assert(SessionHooks.Effects == before + 1, "Session policy leaked into trusted host code.");
        var result = session.Stop();
        Assert(result.Report.Outcome == MapRunOutcome.Completed && result.Report.CompletedTicks == 2 &&
            result.Report.Logs.SequenceEqual(new[] { "start:41", "tick:41", "tick:41", "stop:41" }),
            "Lifecycle reflection did not complete: " + result.Report.Error);
        var flow = SessionHooks.Flow!;
        Expect<InvalidOperationException>(() => ExecutionContext.Run(flow, _ => SessionHooks.ReflectEffect(), null));
        SessionHooks.Flow = null;
        Pass("session construction/start/two ticks/stop activate policy and restore unrestricted host context");
        Pass("returned callback contexts refuse while new callbacks retain the live session policy");
        return (session, flow);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static UnloadTicket[] ExerciseReviewFindings()
    {
        var tickets = new List<UnloadTicket>();
        string safePath = Path.Combine(AppContext.BaseDirectory, "session-author", "System.Custom.UgcDependency.dll");
        string deniedPath = Path.Combine(AppContext.BaseDirectory, "session-author", "ReflectionPolicy.DeniedDependency.dll");
        string outsideDynamic = SessionHooks.ProbeDynamicFactory();
        string outsideStub = SessionHooks.ProbeStubFactory();
        string outsideStream = SessionHooks.ProbeStreamOutsidePolicy(safePath);
        bool outsideEvent = SessionHooks.ProbeResolverEventOutside(safePath, deniedPath);
        SessionHooks.ProbeAssemblyPath = safePath;
        string preCreatedCreate = SessionHooks.CreatePreCreatedDynamicInvoker();
        string outsideSymbols = SessionHooks.ProbeOversizedSymbolsOutside();
        string privateInvoker;
        string preCreatedInvoke;
        using (var permissive = EnterPermissiveBridge())
        {
            privateInvoker = SessionHooks.ProbePrivateDynamicInvoker();
            preCreatedInvoke = SessionHooks.ProbePreCreatedDynamicInvoker();
        }

        var beforeContexts = AssemblyLoadContext.All.ToHashSet();
        using var sessionB = new MapRunner().Start(SessionPackage("SessionScript"), SessionOptions());
        Assert(sessionB.IsRunning, "Attached session B did not start: " + sessionB.Result?.Report.Error);
        var attachedB = AssemblyLoadContext.All.Except(beforeContexts)
            .Single(context => context.Name?.StartsWith("map:reflection-session:", StringComparison.Ordinal) == true);
        SessionHooks.CrossSessionTarget = attachedB;
        SessionHooks.CrossSessionPath = safePath;
        SessionHooks.ResolverPath = safePath;
        SessionHooks.ResolverDeniedPath = deniedPath;

        using var sessionA = new MapRunner().Start(SessionPackage("ReviewProbeScript"), SessionOptions());
        Assert(sessionA.IsRunning, "Review probe session A did not start: " + sessionA.Result?.Report.Error);
        var depth = typeof(object).Assembly.GetType("System.Reflection.RuneCLRReflectionPolicy", true)!
            .GetField("TrustedResolutionDepth", BindingFlags.Static | BindingFlags.NonPublic);
        Assert(depth is not null, "TrustedResolutionDepth field is unavailable for the resolver-depth probe.");
        bool ticked;
        depth!.SetValue(null, 1);
        try { ticked = sessionA.Tick(); }
        finally { depth.SetValue(null, 0); }
        Assert(ticked, "Review probe tick did not execute.");
        var stoppedA = sessionA.Stop();
        var stoppedB = sessionB.Stop();
        tickets.Add(stoppedA.Unload);
        tickets.Add(stoppedB.Unload);

        var failures = new List<string>();
        if (SessionHooks.DynamicFactoryResult.StartsWith("escaped:", StringComparison.Ordinal))
            failures.Add("DynamicMethod.CreateDelegateForInvoker produced an executable delegate under the session (" + SessionHooks.DynamicFactoryResult + ")");
        if (SessionHooks.StubFactoryResult.StartsWith("escaped:", StringComparison.Ordinal))
            failures.Add("InvokerEmitUtil.CreateStubDelegate produced an executable delegate under the session (" + SessionHooks.StubFactoryResult + ")");
        if (SessionHooks.RepeatedReflectionSum != 25 * 41 || SessionHooks.MethodInvokerSum != 25 * 41)
            failures.Add("ordinary repeated reflected invocations failed under the session (reflection=" +
                SessionHooks.RepeatedReflectionSum + ", invoker=" + SessionHooks.MethodInvokerSum + ")");
        if (!SessionHooks.SeekableStreamResult.StartsWith("refused:", StringComparison.Ordinal) || SessionHooks.SeekableStreamBytes > 33L * 1024 * 1024)
            failures.Add("oversized seekable stream was not refused within bounded reads (" + SessionHooks.SeekableStreamResult + ", bytes=" + SessionHooks.SeekableStreamBytes + ")");
        if (!SessionHooks.NonseekableStreamResult.StartsWith("refused:", StringComparison.Ordinal) || SessionHooks.NonseekableStreamBytes > 33L * 1024 * 1024)
            failures.Add("nonseekable oversized stream was not bounded (" + SessionHooks.NonseekableStreamResult + ", bytes=" + SessionHooks.NonseekableStreamBytes + ")");
        if (outsideStream != "System.Custom.UgcDependency")
            failures.Add("outside-policy stream load control failed (" + outsideStream + ")");
        if (!SessionHooks.ResolverEventSeen || !SessionHooks.ResolverEventDenied)
            failures.Add("resolver path AssemblyLoad event inherited loading privilege (" + SessionHooks.ResolverEventResult + ")");
        if (!SessionHooks.CrossSessionResult.StartsWith("refused:", StringComparison.Ordinal))
            failures.Add("resolver-depth load crossed from session A to attached session B (" + SessionHooks.CrossSessionResult + ")");
        if (attachedB.Assemblies.Any(assembly => assembly.GetName().Name == "System.Custom.UgcDependency"))
            failures.Add("attached session B accepted a cross-session load.");
        if (!outsideEvent)
            failures.Add("outside-policy host resolver event control was unexpectedly restricted.");
        if (!privateInvoker.StartsWith("refused:", StringComparison.Ordinal) && privateInvoker != "unavailable")
            failures.Add("reflective private MethodInvoker(DynamicMethod) path executed or did not refuse (" +
                privateInvoker + ")");
        if (preCreatedCreate == "created" && !preCreatedInvoke.StartsWith("refused:", StringComparison.Ordinal))
            failures.Add("pre-created DynamicMethod MethodInvoker executed under the permissive scope (" +
                preCreatedInvoke + ")");
        Console.WriteLine("REVIEW_PROBE privateInvoker=" + privateInvoker +
            "; preCreatedCreate=" + preCreatedCreate + "; preCreatedInvoke=" + preCreatedInvoke +
            "; symbols=" + SessionHooks.OversizedSymbolsResult + "; outsideSymbols=" + outsideSymbols);
        if (!IsLimitFailure(SessionHooks.OversizedSymbolsResult, out string symbolDetail))
            failures.Add("oversized byte[] symbols were not refused at the managed limit (" + symbolDetail + ")");
        if (IsLimitFailure(outsideSymbols, out _))
            failures.Add("outside-policy byte[] symbols unexpectedly hit the managed UGC limit");
        Assert(failures.Count == 0, "Review regression failures: " + string.Join(" | ", failures));

        Pass("permissive session refuses internal DynamicMethod delegate factory (outside=" + outsideDynamic + ", inside=" + SessionHooks.DynamicFactoryResult + ")");
        Pass("permissive session refuses InvokerEmitUtil stub-delegate factory (outside=" + outsideStub + ", inside=" + SessionHooks.StubFactoryResult + ")");
        Pass("ordinary repeated reflected invocations and MethodInvoker factory still execute under the session");
        Pass("oversized seekable stream refuses within the bounded read limit");
        Pass("oversized nonseekable stream refuses within the bounded read limit");
        Pass("host-side stream load outside policy remains unrestricted");
        Pass("host resolver path load cannot inherit loading privilege into AssemblyLoad events");
        Pass("resolver-depth load cannot cross from active session A into attached session B");
        Pass("outside-policy host resolver event load remains unrestricted");
        Pass("reflective private MethodInvoker(DynamicMethod) path is refused under the session");
        Pass("pre-created DynamicMethod MethodInvoker cannot execute under the session");
        Pass("oversized byte[] symbol store refuses at the managed input limit before native load");
        SessionHooks.CrossSessionTarget = null;
        SessionHooks.CrossSessionPath = "";
        SessionHooks.ResolverPath = "";
        SessionHooks.ResolverDeniedPath = "";
        return tickets.ToArray();
    }

    private static IDisposable EnterPermissiveBridge()
    {
        var type = typeof(object).Assembly.GetType("System.Reflection.RuneCLRReflectionPolicy", true)!;
        var method = type.GetMethod("RuneCLR_EnterReflectionPolicy", BindingFlags.Static | BindingFlags.NonPublic);
        Assert(method is not null, "The raw reflection-policy entry point is unavailable.");
        var enter = method!.CreateDelegate<Func<Action<MemberInfo, object?, object?[]?, int>, IDisposable>>();
        return enter(static (_, _, _, _) => { });
    }

    private static bool IsLimitFailure(string result, out string detail)
    {
        detail = result;
        if (!result.StartsWith("threw:", StringComparison.Ordinal)) return false;
        var parts = result.Split(':', 3);
        if (parts.Length < 3) return false;
        detail = parts[1] + ": " + parts[2];
        bool typed = parts[1] is "BadImageFormatException" or "InvalidDataException" or "ArgumentException";
        bool managed = parts[2].Contains("UGC", StringComparison.OrdinalIgnoreCase) ||
            parts[2].Contains("symbol", StringComparison.OrdinalIgnoreCase) ||
            parts[2].Contains("managed-IL", StringComparison.OrdinalIgnoreCase);
        bool bounded = parts[2].Contains("limit", StringComparison.OrdinalIgnoreCase) ||
            parts[2].Contains("exceed", StringComparison.OrdinalIgnoreCase);
        return typed && managed && bounded;
    }

    private static MapPackage SessionPackage(string name) => new("reflection-session",
        Path.Combine(AppContext.BaseDirectory, "session-author", "ReflectionPolicy.SessionAuthor.dll"), "ReflectionPolicy.Author." + name);
    private static MapRunOptions SessionOptions() => new()
    {
        ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
        PrototypeSharedAssemblies = [typeof(SessionHooks).Assembly],
        PrototypeApiPolicy = new SessionPolicy()
    };
    private sealed class SessionPolicy : IApiAccessPolicy
    {
        private readonly IApiAccessPolicy legacy = GameplayCapabilityPolicy.CreateApiPolicy([], Contract);
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation)
        {
            if (target.IsSessionCode) return legacy.Evaluate(target, operation);
            if (target.MemberName == "Effect" || target.TypeName == "System.IO.File" || target.TypeName == "DynamicDependency.Payload")
                return ApiDecision.Deny("Test target effect is forbidden.");
            return ApiDecision.Allow;
        }
    }

    private sealed class MutatingPolicy(string path, byte[] replacement) : IApiAccessPolicy
    {
        private readonly SessionPolicy inner = new();
        private bool mutated;
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation)
        {
            if (!mutated && target.MemberName == "MarkLoaded" && operation == ApiOperation.Reference)
            {
                mutated = true;
                File.WriteAllBytes(path, replacement);
            }
            return inner.Evaluate(target, operation);
        }
    }
}
