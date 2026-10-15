using System.Diagnostics;
using System.Globalization;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text.Json;

namespace MobileBatchTimingProbe;

public static class Entry
{
    private const string AuthorHash = "d743ecb6ba897366a276ab700e79a42f3885ba2eaf69d1713bb086346f2fd09e";
    private const string ContractHash = "ebfe72469b640b63991189123971beadbf9c3fe74d303a9b7ce66f87596a807b";
    private const string ContractIdentity = "RuneCLR.Abstractions, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null";
    private const string ContractMvid = "92efbbd4-8ae3-4686-824b-bafe67f2dd69";
    private const int Iterations = 100_000, Warmups = 3;
    private const long Checksum = 12_749_776, Dispatches = 2_100_016;

    public static int Main(string[] args) => Run(args);

    public static int Run(string[] args)
    {
        if (args.Length != 6 || args[1] is not ("no-config" or "high-budget") ||
            args[2] is not ("no-config" or "best-exact" or "N100" or "N1000") ||
            (args[1] == "high-budget" && args[2] == "no-config") ||
            args[3].Length != 32 || !args[3].All(Uri.IsHexDigit) ||
            !int.TryParse(args[4], NumberStyles.None, CultureInfo.InvariantCulture, out int samples) || samples is < 1 or > 100)
            throw new ArgumentException("Usage: <author.dll> <no-config|high-budget> <no-config|best-exact|N100|N1000> <32-hex nonce> <samples 1..100> <fresh receipt.json>");
        string author = Path.GetFullPath(args[0]), output = Path.GetFullPath(args[5]);
        var requestedSettings = RequestedSettings(args[2]);
        Need(requestedSettings.All(pair => Environment.GetEnvironmentVariable(pair.Key) == pair.Value), "Requested lane environment differs.");
        long frequency = Stopwatch.Frequency;
        Need(frequency > 0, "Stopwatch frequency must be positive.");
        string contract = Path.Combine(Path.GetDirectoryName(author)!, "RuneCLR.Abstractions.dll");
        Assembly shared = typeof(RuneCLR.IMapScript).Assembly;
        Need(shared.FullName == ContractIdentity && shared.ManifestModule.ModuleVersionId.ToString() == ContractMvid &&
            AssemblyLoadContext.GetLoadContext(shared) == AssemblyLoadContext.Default, "Loaded trusted shared contract identity/MVID differs.");
        // Mobile R2R component bytes differ from their frozen raw IL input; bind both identities separately.
        string? loadedContractComponentHash = string.IsNullOrEmpty(shared.Location) ? null : Hash(shared.Location);
        Need(Hash(author) == AuthorHash && Hash(contract) == ContractHash, "Frozen author/shared contract bytes differ.");
        Need(!File.Exists(output), "Receipt already exists.");
        var api = new Api();
        bool budget = args[1] == "high-budget";
        Frame frame = InvokeFrame(api, author, budget, samples, frequency);
        Collect(frame.Context);
        Need(Hash(author) == AuthorHash && Hash(contract) == ContractHash, "Author/shared contract changed during invocation.");
        using (var stream = new FileStream(output, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            JsonSerializer.Serialize(stream, new
            {
                schema = "runeclr.mobile-batch-timing.observation.v1", passed = true, processId = Environment.ProcessId,
                nonce = args[3], mode = args[1], lane = args[2], requestedSettings, runtime = RuntimeInformation.FrameworkDescription,
                architecture = RuntimeInformation.ProcessArchitecture.ToString(), authorHash = AuthorHash, contractHash = ContractHash,
                contractIdentity = ContractIdentity, contractMvid = ContractMvid, loadedContractComponentHash,
                iterations = Iterations, expectedChecksum = Checksum, expectedDispatchDelta = Dispatches, warmups = Warmups,
                sampleCount = samples, budgetLimit = budget ? Api.Limit : (long?)null, cleanupLimit = Api.Cleanup,
                stopwatchFrequency = frequency, stopwatchIsHighResolution = Stopwatch.IsHighResolution, callbackTimingObserved = true,
                timingScope = "Stopwatch timestamps surround only the direct frozen Kernel.Execute delegate invocation.",
                api.Capabilities, frame.Initial, frame.Rows, frame.Final, collected = !frame.Context.IsAlive,
                frame.RetiredGetterRejections, nativeEntryProof = false, liveBatchPathVerified = false,
                mobileExecutionVerified = false, physicalDeviceVerified = false, performanceVerified = false,
                baseline = "Same instrumented runtime; no-config has required interpreter policy without a native meter; not compile-time instrumentation-off.",
                scope = "Direct callback timing and scalar native ledgers in one collectible context; snapshots, validation, collection, JSON and process startup are outside callback timing; no affinity, entry-byte inspection, concurrency, device or comparative performance acceptance."
            }, new JsonSerializerOptions { WriteIndented = true });
        Console.WriteLine($"MOBILE_BATCH_TIMING_COMPLETE nonce={args[3]} pid={Environment.ProcessId} lane={args[2]} mode={args[1]} callbacks={Warmups + samples}");
        return 0;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static Frame InvokeFrame(Api api, string author, bool budget, int samples, long frequency)
    {
        AssemblyLoadContext context = api.Create(budget);
        var weak = new WeakReference(context);
        var rows = new List<Row>();
        Snapshot? initial = null;
        Snapshot? final = null;
        int retiredRejections = 0;
        try
        {
            initial = budget ? api.StableRead(context) : null;
            Assembly assembly = context.LoadFromAssemblyPath(author);
            Need(AssemblyLoadContext.GetLoadContext(assembly) == context, "Author was not loaded in the owned context.");
            Type type = assembly.GetType("RuneCLR.BatchKernel.Kernel", true)!;
            MethodInfo method = type.GetMethod("Execute", BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly,
                null, [typeof(int)], null) ?? throw new InvalidOperationException("Frozen kernel entry missing.");
            Need(method.ReturnType == typeof(long) && !method.IsGenericMethod, "Frozen kernel signature differs.");
            Func<int, long> callback = method.CreateDelegate<Func<int, long>>();
            for (int index = 0; index < Warmups + samples; index++)
            {
                Snapshot? before = budget ? api.StableRead(context) : null;
                long started = Stopwatch.GetTimestamp();
                long value = callback(Iterations);
                long finished = Stopwatch.GetTimestamp();
                Snapshot? after = budget ? api.StableRead(context) : null;
                long elapsed = checked(finished - started);
                double seconds = (double)elapsed / frequency;
                Need(started >= 0 && elapsed > 0 && double.IsFinite(seconds) && seconds > 0, "Direct callback timestamp interval differs.");
                Need(value == Checksum, "Kernel checksum differs.");
                if (budget)
                {
                    Need(before == Api.Expected(index * Dispatches) && after == Api.Expected((index + 1) * Dispatches),
                        "Exact callback native ledger differs.");
                    Need(after!.Value.Executed - before!.Value.Executed == Dispatches, "Callback dispatch delta differs.");
                }
                rows.Add(new(index, index < Warmups, value, before, after, budget ? Dispatches : null, started, finished, elapsed, seconds));
            }
            final = budget ? api.StableRead(context) : null;
            Need(!budget || final == Api.Expected((Warmups + samples) * Dispatches), "Final native ledger differs.");
            GC.KeepAlive(callback);
        }
        finally
        {
            context.Unload();
            if (budget) retiredRejections = api.Retired(context);
        }
        // The caller collects only after this frame and all author metadata/delegates have returned.
        return new(weak, initial, rows, final, retiredRejections);
    }

    private static void Collect(WeakReference weak)
    {
        for (int i = 0; i < 12 && weak.IsAlive; i++) { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }
        Need(!weak.IsAlive, "Collectible kernel context retained after frame returned.");
    }

    private static string Hash(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
    private static Dictionary<string, string> RequestedSettings(string lane) => new()
    {
        ["DOTNET_InterpMode"] = "0", ["DOTNET_RuneCLRInterpretCollectible"] = "0", ["DOTNET_ReadyToRun"] = "1",
        ["DOTNET_TieredCompilation"] = "0", ["DOTNET_MULTILEVEL_LOOKUP"] = "0", ["DOTNET_RuneCLRPhaseAcquireLoad"] = "1",
        ["DOTNET_RuneCLRDerivedLedger"] = lane == "best-exact" ? "1" : "0",
        ["DOTNET_RuneCLRBatchInterval"] = lane == "N1000" ? "3e8" : lane == "N100" ? "64" : "0"
    };
    private static void Need(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }

    private readonly record struct Snapshot(long Remaining, long Executed, bool Exhausted, bool IsTerminated, int Reason,
        int Phase, long CleanupRemaining, long CleanupExecuted);
    private sealed record Row(int Index, bool Warmup, long Checksum, Snapshot? Before, Snapshot? After, long? DispatchDelta,
        long StartedTimestamp, long FinishedTimestamp, long ElapsedTicks, double Seconds);
    private sealed record Frame(WeakReference Context, Snapshot? Initial, List<Row> Rows, Snapshot? Final, int RetiredGetterRejections);

    private sealed class Api
    {
        public const long Limit = 1_000_000_000_000, Cleanup = 4096;
        private readonly Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, AssemblyLoadContext> required;
        private readonly Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, long, AssemblyLoadContext> terminal;
        private readonly Func<AssemblyLoadContext, int> policy, reason, phase;
        private readonly Func<AssemblyLoadContext, long> remaining, executed, cleanupRemaining, cleanupExecuted;
        private readonly Func<AssemblyLoadContext, bool> exhausted, terminated;
        public object Capabilities { get; }

        public Api()
        {
            int policyVersion = Bind<Func<int>>("RuneCLR_GetExecutionPolicyVersion", true)();
            int terminalVersion = Bind<Func<int>>("RuneCLR_GetTerminalPrototypeVersion", true)();
            int finalizerVersion = Bind<Func<int>>("RuneCLR_GetTerminalFinalizerBoundaryVersion", true, typeof(GC))();
            Need(policyVersion == 1 && terminalVersion == 1 && finalizerVersion == 1, "Private API versions differ.");
            Capabilities = new { policyVersion, terminalVersion, finalizerVersion, privateBridge = true };
            required = Bind<Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, AssemblyLoadContext>>("RuneCLR_CreateInterpreterRequired", true);
            terminal = Bind<Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, long, long, AssemblyLoadContext>>("RuneCLR_CreateTerminalPrototype", true);
            policy = Bind<Func<AssemblyLoadContext, int>>("RuneCLR_GetExecutionPolicy", false);
            remaining = Bind<Func<AssemblyLoadContext, long>>("RuneCLR_GetInstructionMeterRemaining", false);
            executed = Bind<Func<AssemblyLoadContext, long>>("RuneCLR_GetInstructionMeterExecuted", false);
            exhausted = Bind<Func<AssemblyLoadContext, bool>>("RuneCLR_GetInstructionMeterExhausted", false);
            terminated = Bind<Func<AssemblyLoadContext, bool>>("RuneCLR_GetTerminalPrototypeIsTerminated", false);
            reason = Bind<Func<AssemblyLoadContext, int>>("RuneCLR_GetTerminalPrototypeReason", false);
            phase = Bind<Func<AssemblyLoadContext, int>>("RuneCLR_GetTerminalPrototypePhase", false);
            cleanupRemaining = Bind<Func<AssemblyLoadContext, long>>("RuneCLR_GetTerminalPrototypeCleanupRemaining", false);
            cleanupExecuted = Bind<Func<AssemblyLoadContext, long>>("RuneCLR_GetTerminalPrototypeCleanupExecuted", false);
        }

        public AssemblyLoadContext Create(bool budget)
        {
            Assembly shared = typeof(RuneCLR.IMapScript).Assembly;
            AssemblyName sharedName = shared.GetName();
            Assembly? Resolver(AssemblyLoadContext _, AssemblyName name)
            {
                if (name.Name != sharedName.Name) return null;
                Need(name.FullName == sharedName.FullName, "Author requested a different shared contract identity.");
                return shared;
            }
            string label = "mobile-batch-kernel-" + Guid.NewGuid().ToString("N");
            AssemblyLoadContext context = budget ? terminal(label, Resolver, Limit, Cleanup) : required(label, Resolver);
            try
            {
                Need(context.IsCollectible && policy(context) == 1, "Collectible required interpreter policy acknowledgement differs.");
                Need(!budget || StableRead(context) == Expected(0), "Initial native ledger differs.");
                return context;
            }
            catch { context.Unload(); throw; }
        }

        public static Snapshot Expected(long count) => new(Limit - count, count, false, false, 0, 0, Cleanup, 0);
        private Snapshot Read(AssemblyLoadContext context) => new(remaining(context), executed(context), exhausted(context),
            terminated(context), reason(context), phase(context), cleanupRemaining(context), cleanupExecuted(context));
        public Snapshot StableRead(AssemblyLoadContext context)
        {
            Snapshot first = Read(context);
            Need(first == Read(context), "Read-only native ledger drift.");
            return first;
        }

        public int Retired(AssemblyLoadContext context)
        {
            Action[] getters = [() => remaining(context), () => executed(context), () => exhausted(context), () => terminated(context),
                () => reason(context), () => phase(context), () => cleanupRemaining(context), () => cleanupExecuted(context)];
            int rejected = 0;
            foreach (Action getter in getters) { try { getter(); } catch (InvalidOperationException) { rejected++; } }
            Need(rejected == getters.Length, "Retired native ledger queries were not rejected.");
            return rejected;
        }

        private static T Bind<T>(string name, bool isStatic, Type? owner = null) where T : Delegate
        {
            owner ??= typeof(AssemblyLoadContext);
            MethodInfo invoke = typeof(T).GetMethod("Invoke")!;
            Type[] parameters = invoke.GetParameters().Select(parameter => parameter.ParameterType).ToArray();
            if (!isStatic) parameters = parameters.Skip(1).ToArray();
            MethodInfo? method = owner.GetMethod(name, BindingFlags.NonPublic | BindingFlags.DeclaredOnly |
                (isStatic ? BindingFlags.Static : BindingFlags.Instance), null, parameters, null);
            Need(method is not null && method.IsPrivate && method.IsStatic == isStatic && method.ReturnType == invoke.ReturnType &&
                !method.IsGenericMethod, "Private exact CoreLib signature missing: " + name);
            return method!.CreateDelegate<T>();
        }
    }
}
