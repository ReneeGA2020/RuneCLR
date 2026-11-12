using System.Reflection;
using System.Text.Json;
using RuneCLR;
using RuneCLR.Packages;
using RuneCLR.Runtime;
using SessionOrigin.Compiled;

internal static class Program
{
    private static string Contract => typeof(RuneCLR.IMapScript).Assembly.FullName!;
    private static string AuthorPath => Path.Combine(AppContext.BaseDirectory, "session-origin", "SessionOrigin.Author.dll");
    private static string DeniedPath => Path.Combine(AppContext.BaseDirectory, "session-origin", "ReflectionPolicy.DeniedDependency.dll");

    private static int Main(string[] args)
    {
        AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", true);
        OriginHooks.DeniedAssemblyBytes = File.ReadAllBytes(DeniedPath);
        bool requireOrigin = args.Length == 2 && args[1] == "--require-origin";
        bool IsRequiredMode(string name) => args.Length is 1 or 2 && args[0] == name &&
            (args.Length == 1 || requireOrigin);
        if (IsRequiredMode("--expect-fixed"))
        {
            var normalFixed = Run("SessionOrigin.Author.NormalThreadScript", requireOrigin);
            var threadFixed = Run("SessionOrigin.Author.SuppressedThreadScript", requireOrigin);
            var taskFixed = Run("SessionOrigin.Author.SuppressedTaskScript", requireOrigin);
            var compiledHelperFixed = Run("SessionOrigin.Author.CompiledHelperScript", requireOrigin);
            OriginHooks.Reset();
            int beforeHost = OriginHooks.ForbiddenEffects;
            bool hostThreadAllowedFixed;
            using (var hostSession = new MapRunner().Start(
                new MapPackage("session-origin", AuthorPath, "SessionOrigin.Author.NormalThreadScript"), Options(requireOrigin)))
            {
                var hostThread = new Thread(() => OriginHooks.ForbiddenEffect());
                hostThread.Start();
                hostThread.Join(10000);
                hostThreadAllowedFixed = OriginHooks.ForbiddenEffects == beforeHost + 1;
                hostSession.Stop();
            }
            bool fixedModeObserved = normalFixed.Restricted && threadFixed.FixedRestricted &&
                taskFixed.FixedRestricted && compiledHelperFixed.CompiledHelperRestricted && hostThreadAllowedFixed;
            Console.WriteLine(JsonSerializer.Serialize(new
            {
                normal = normalFixed,
                suppressedThread = threadFixed,
                suppressedTask = taskFixed,
                compiledHelper = compiledHelperFixed,
                fixedModeObserved,
                hostThreadAllowed = hostThreadAllowedFixed,
                originScanCapability = OriginHooks.GetOriginScanCapability()
            }));
            return fixedModeObserved ? 0 : 1;
        }
        if (IsRequiredMode("--frame-probes"))
        {
            var hidden = Run("SessionOrigin.Author.HiddenHelperScript", requireOrigin);
            var inlined = Run("SessionOrigin.Author.InlinedHelperScript", requireOrigin);
            OriginHooks.Reset();
            OriginHooks.RunCompiledOnlySuppressed();
            Console.WriteLine(JsonSerializer.Serialize(new
            {
                hidden,
                inlined,
                compiledOnlySuppressedRan = OriginHooks.CompiledOnlySuppressedRan,
                compiledOnlyEscaped = OriginHooks.CompiledOnlyEscaped,
                compiledOnlyFailure = OriginHooks.CompiledOnlyFailure,
                compiledOnlyEffects = OriginHooks.ForbiddenEffects,
                authorFrameSlice = "hidden/inlined probes have an author frame; compiled-only attempts reflection without one and its outcome is recorded, not required"
            }));
            return 0;
        }
        if (IsRequiredMode("--retirement"))
        {
            OriginHooks.Reset();
            using (var session = new MapRunner().Start(
                new MapPackage("session-origin", AuthorPath, "SessionOrigin.Author.RetirementScript"), Options(requireOrigin)))
            {
                session.Stop();
            }
            OriginHooks.InvokeRetainedOnSuppressedThread();
            Console.WriteLine(JsonSerializer.Serialize(new
            {
                RetiredProbeRan = OriginHooks.RetiredProbeRan,
                RetiredFailure = OriginHooks.RetiredFailure,
                Effects = OriginHooks.ForbiddenEffects
            }));
            return 0;
        }
        if (IsRequiredMode("--conflict"))
        {
            OriginHooks.Reset();
            using (var ownerB = new MapRunner().Start(
                new MapPackage("session-origin", AuthorPath, "SessionOrigin.Author.RetirementScript"), Options(requireOrigin)))
            {
                using var ownerA = new MapRunner().Start(
                    new MapPackage("session-origin", AuthorPath, "SessionOrigin.Author.ConflictingOwnerScript"), Options(requireOrigin));
                Console.WriteLine(JsonSerializer.Serialize(new
                {
                    BStored = OriginHooks.OtherProbe is not null,
                    ConflictProbeRan = OriginHooks.ConflictProbeRan,
                    ConflictFailure = OriginHooks.ConflictFailure,
                    Effects = OriginHooks.ForbiddenEffects
                }));
                ownerA.Stop();
                ownerB.Stop();
            }
            return 0;
        }
        if (IsRequiredMode("--overflow"))
        {
            OriginHooks.Reset();
            var chainPath = Path.Combine(AppContext.BaseDirectory, "session-origin", "SessionOrigin.Chain.dll");
            OriginHooks.BuildOverflowChain(File.ReadAllBytes(chainPath),
                "SessionOrigin.Chain.ChainStep", "Invoke", 17);
            using var session = new MapRunner().Start(
                new MapPackage("session-origin", AuthorPath, "SessionOrigin.Author.OverflowScript"), Options(requireOrigin));
            bool running = session.IsRunning;
            string? error = session.Result?.Report.Error;
            if (running) session.Stop();
            Console.WriteLine(JsonSerializer.Serialize(new
            {
                SessionRunning = running,
                Error = error,
                OriginHooks.ChainDepth,
                OriginHooks.ChainCompleted,
                OriginHooks.ChainFailure,
                OriginHooks.ChainLeafFailure,
                ProbeRan = OriginHooks.ChildProbeRan,
                ReflectionDenied = OriginHooks.ChildReflectionDenied,
                LoadDenied = OriginHooks.ChildLoadDenied,
                LoadSucceeded = OriginHooks.ChildLoadSucceeded,
                Effects = OriginHooks.ForbiddenEffects,
                ChildFailure = OriginHooks.ChildFailure
            }));
            return 0;
        }
        if (IsRequiredMode("--disposal"))
        {
            OriginHooks.Reset();
            bool parked;
            bool retiredWhileParked;
            bool childJoined;
            string? startError;
            using (var session = new MapRunner().Start(
                new MapPackage("session-origin", AuthorPath, "SessionOrigin.Author.DisposalScript"), Options(requireOrigin)))
            {
                parked = OriginHooks.WaitChildParked(15000);
                startError = session.Result?.Report.Error;
                retiredWhileParked = session.IsRunning;
                if (session.IsRunning) session.Stop();
                childJoined = OriginHooks.ReleaseBlockingChild(15000);
            }
            Console.WriteLine(JsonSerializer.Serialize(new
            {
                Parked = parked,
                RetiredWhileParked = retiredWhileParked,
                ChildJoined = childJoined,
                StartError = startError,
                ReflectionDenied = OriginHooks.ChildReflectionDenied,
                LoadDenied = OriginHooks.ChildLoadDenied,
                LoadSucceeded = OriginHooks.ChildLoadSucceeded,
                Effects = OriginHooks.ForbiddenEffects,
                ChildFailure = OriginHooks.ChildFailure
            }));
            return 0;
        }
        if (args.Length == 2 && args[0] == "--toggle-gate")
        {
            bool initial = bool.Parse(args[1]);
            AppContext.SetSwitch("RuneCLR.EnableReflectionPolicyOriginScan", initial);
            int? capabilityBefore = OriginHooks.GetOriginScanCapability();
            AppContext.SetSwitch("RuneCLR.EnableReflectionPolicyOriginScan", !initial);
            int? capabilityAfter = OriginHooks.GetOriginScanCapability();
            Exception? mapError = null;
            Exception? hostError = null;
            try
            {
                new MapRunner().Start(new MapPackage("missing", "missing.dll", "Missing"),
                    Options() with { PrototypeRequireOriginScan = true });
            }
            catch (Exception error) { mapError = error; }
            try
            {
                using var rejected = new HostContractSession(typeof(IOriginContract), new OriginContractHost(),
                    "missing.dll", "Missing.Entry", ["Echo"], new HostContractSessionOptions
                    {
                        ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
                        PrototypeApiPolicy = new OriginPolicy(),
                        PrototypeRequireOriginScan = true
                    });
            }
            catch (Exception error) { hostError = error; }
            Console.WriteLine(JsonSerializer.Serialize(new
            {
                initialScan = initial,
                capabilityBefore,
                capabilityAfter,
                mapRejectedBeforeFile = mapError is PlatformNotSupportedException,
                hostRejectedBeforeFile = hostError is PlatformNotSupportedException,
                mapError = mapError?.GetType().FullName,
                hostError = hostError?.GetType().FullName
            }));
            return 0;
        }
        if (args.Length == 2 && args[0] == "--host-required-origin-gate")
        {
            bool scan = bool.Parse(args[1]);
            AppContext.SetSwitch("RuneCLR.EnableReflectionPolicyOriginScan", scan);
            Exception? hostGateError = null;
            try
            {
                using var rejected = new HostContractSession(typeof(IOriginContract), new OriginContractHost(),
                    Path.Combine(Path.GetTempPath(), "missing-hostcontract-origin.dll"), "Missing.Entry",
                    ["Echo"], new HostContractSessionOptions
                    {
                        ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
                        PrototypeApiPolicy = new OriginPolicy(),
                        PrototypeRequireOriginScan = true
                    });
            }
            catch (Exception error) { hostGateError = error; }
            bool rejectedBeforeFile = hostGateError is PlatformNotSupportedException;
            Console.WriteLine(JsonSerializer.Serialize(new
            {
                requestedScan = scan,
                rejectedBeforeFile,
                errorType = hostGateError?.GetType().FullName,
                message = hostGateError?.Message
            }));
            // Report-only probe: the driver asserts accept vs reject semantics.
            return 0;
        }
        if (args.Length == 1 && args[0] == "--invalid-option-combos")
        {
            Exception? mapError = null;
            Exception? hostError = null;
            try
            {
                new MapRunner().Start(new MapPackage("missing", "missing.dll", "Missing"),
                    new MapRunOptions { PrototypeRequireOriginScan = true });
            }
            catch (Exception error) { mapError = error; }
            try
            {
                using var rejected = new HostContractSession(typeof(IOriginContract), new OriginContractHost(),
                    "missing.dll", "Missing.Entry", ["Echo"],
                    new HostContractSessionOptions { PrototypeRequireOriginScan = true });
            }
            catch (Exception error) { hostError = error; }
            bool invalidRejected = mapError is ArgumentException && hostError is ArgumentException;
            Console.WriteLine(JsonSerializer.Serialize(new
            {
                invalidRejected,
                mapError = mapError?.GetType().FullName,
                hostError = hostError?.GetType().FullName
            }));
            return invalidRejected ? 0 : 1;
        }
        if (args.Length == 2 && args[0] == "--required-origin-gate")
        {
            bool scan = bool.Parse(args[1]);
            AppContext.SetSwitch("RuneCLR.EnableReflectionPolicyOriginScan", scan);
            Exception? gateError = null;
            try
            {
                using var rejected = new MapRunner().Start(
                    new MapPackage("missing", Path.Combine(Path.GetTempPath(), "missing-session-origin.dll"), "Missing"),
                    Options() with { PrototypeRequireOriginScan = true });
            }
            catch (Exception error) { gateError = error; }
            bool rejectedBeforeFile = gateError is PlatformNotSupportedException;
            Console.WriteLine(JsonSerializer.Serialize(new
            {
                requestedScan = scan,
                rejectedBeforeFile,
                errorType = gateError?.GetType().FullName,
                message = gateError?.Message
            }));
            // Report-only probe: the driver asserts accept vs reject semantics.
            return 0;
        }
        if (args.Length == 2 && args[0] == "--capability-probe")
        {
            bool enabled = bool.Parse(args[1]);
            AppContext.SetSwitch("RuneCLR.EnableReflectionPolicyOriginScan", enabled);
            bool present = false;
            bool effective = OriginHooks.GetOriginScanSwitch(out present);
            Console.WriteLine(JsonSerializer.Serialize(new
            {
                requested = enabled,
                switchPresent = present,
                switchEffective = effective,
                originScanCapability = OriginHooks.GetOriginScanCapability()
            }));
            return 0;
        }
        if (args.Length != 1 || args[0] != "--require-private-runtime")
            return 2;
        OriginHooks.DeniedAssemblyBytes = File.ReadAllBytes(DeniedPath);
        var normal = Run("SessionOrigin.Author.NormalThreadScript");
        var thread = Run("SessionOrigin.Author.SuppressedThreadScript");
        var task = Run("SessionOrigin.Author.SuppressedTaskScript");
        var compiledHelper = Run("SessionOrigin.Author.CompiledHelperScript");
        bool hostThreadAllowed;
        using (var hostSession = new MapRunner().Start(
            new MapPackage("session-origin", AuthorPath, "SessionOrigin.Author.NormalThreadScript"), Options()))
        {
            int beforeHost = OriginHooks.ForbiddenEffects;
            var hostThread = new Thread(() => OriginHooks.ForbiddenEffect());
            hostThread.Start();
            hostThread.Join(10000);
            hostThreadAllowed = OriginHooks.ForbiddenEffects == beforeHost + 1;
            hostSession.Stop();
        }
        var result = new
        {
            normal,
            suppressedThread = thread,
            suppressedTask = task,
            compiledHelper,
            originScanCapability = OriginHooks.GetOriginScanCapability(),
            originScanSwitch = new { present = OriginHooks.GetOriginScanSwitch(out bool scanPresent), presentFlag = scanPresent },
            baselineGapObserved = normal.Restricted &&
                thread.FlowAbsentAndEscaped && task.FlowAbsentAndEscaped &&
                compiledHelper.CompiledHelperRestricted && hostThreadAllowed,
            hostThreadAllowed
        };
        Console.WriteLine(JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
        return result.baselineGapObserved ? 0 : 1;
    }

    private static ControlResult Run(string entryType, bool requireOrigin = false, bool resetHooks = true)
    {
        if (resetHooks) OriginHooks.Reset();
        using var session = new MapRunner().Start(new MapPackage("session-origin", AuthorPath, entryType), Options(requireOrigin));
        bool running = session.IsRunning;
        string? error = session.Result?.Report.Error;
        if (running) session.Stop();
        return new ControlResult(
            entryType,
            running,
            error,
            OriginHooks.ParentThreadId,
            OriginHooks.ChildThreadId,
            OriginHooks.ChildFlowAbsent,
            OriginHooks.ChildProbeRan || OriginHooks.CompiledHelperDenied || OriginHooks.CompiledHelperEscaped,
            OriginHooks.ChildReflectionDenied || OriginHooks.CompiledHelperDenied,
            OriginHooks.ChildLoadDenied,
            OriginHooks.ChildLoadSucceeded,
            OriginHooks.ForbiddenEffects,
            OriginHooks.ChildFailure);
    }

    private static MapRunOptions Options(bool requireOrigin = false) => new()
    {
        ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
        PrototypeSharedAssemblies = [typeof(OriginHooks).Assembly],
        PrototypeApiPolicy = new OriginPolicy(),
        PrototypeRequireOriginScan = requireOrigin
    };

    private sealed class OriginContractHost : IOriginContract
    {
        public int Echo(int value) => value;
    }

    private sealed class OriginPolicy : IApiAccessPolicy
    {
        private readonly IApiAccessPolicy legacy = GameplayCapabilityPolicy.CreateApiPolicy([], Contract);
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation)
        {
            if (target.IsSessionCode) return legacy.Evaluate(target, operation);
            if (target.MemberName == "ForbiddenEffect" || target.TypeName == "System.IO.File")
                return ApiDecision.Deny("Session-origin probe target is forbidden.");
            return ApiDecision.Allow;
        }
    }

    private sealed record ControlResult(
        string EntryType,
        bool SessionRunning,
        string? Error,
        int ParentThreadId,
        int ChildThreadId,
        bool FlowAbsent,
        bool ProbeRan,
        bool ReflectionDenied,
        bool LoadDenied,
        bool LoadSucceeded,
        int ForbiddenEffects,
        string ChildFailure)
    {
        public bool Restricted => SessionRunning && ChildThreadId != 0 && ChildThreadId != ParentThreadId &&
            !FlowAbsent && ProbeRan && ReflectionDenied && LoadDenied && !LoadSucceeded &&
            ForbiddenEffects == 0 && string.IsNullOrEmpty(ChildFailure);
        public bool FlowAbsentAndEscaped => SessionRunning && ChildThreadId != 0 && ChildThreadId != ParentThreadId &&
            FlowAbsent && ProbeRan && !ReflectionDenied && !LoadDenied && LoadSucceeded &&
            ForbiddenEffects == 1 && string.IsNullOrEmpty(ChildFailure);
        public bool CompiledHelperRestricted => SessionRunning && ReflectionDenied && ForbiddenEffects == 0 &&
            string.IsNullOrEmpty(ChildFailure);
        public bool FixedRestricted => SessionRunning && FlowAbsent && ChildThreadId != 0 &&
            ChildThreadId != ParentThreadId && ProbeRan && ReflectionDenied && LoadDenied &&
            !LoadSucceeded && ForbiddenEffects == 0 && string.IsNullOrEmpty(ChildFailure);
    }
}
