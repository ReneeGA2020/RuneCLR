using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text.Json;
using RuneCLR.TrustedUpdate;
using TrustedGameGenerics.Contracts;

namespace TrustedGameGenerics.Host;

internal static class Program
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    private static int Main(string[] args)
    {
        string? reportPath = null;
        string? contextModeArgument = null;
        try
        {
            reportPath = Value(args, "--report");
            contextModeArgument = OptionalValue(args, "--context-mode", "collectible");
            (string contextMode, bool isCollectible) = ParseContextMode(contextModeArgument);
            string modulePath = Path.GetFullPath(Value(args, "--module"));
            string variant = Value(args, "--variant");
            HostReport report = Run(modulePath, variant, contextMode, isCollectible);
            Write(reportPath, report);
            return 0;
        }
        catch (Exception error)
        {
            var failure = new
            {
                Passed = false,
                Error = error.ToString(),
                Arguments = Environment.GetCommandLineArgs(),
                ContextModeArgument = contextModeArgument,
                ProcessId = Environment.ProcessId,
                TimestampUtc = DateTimeOffset.UtcNow
            };
            string json = JsonSerializer.Serialize(failure, JsonOptions);
            if (reportPath is not null)
                File.WriteAllText(reportPath, json + Environment.NewLine);
            Console.WriteLine(json);
            return 1;
        }
    }

    private static HostReport Run(string modulePath, string variant, string contextMode,
        bool isCollectible)
    {
        DateTimeOffset startedUtc = DateTimeOffset.UtcNow;
        ResidentSnapshot before = Resident();
        string moduleSha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(modulePath)));
        Assembly hostAssembly = typeof(Program).Assembly;
        Assembly contractAssembly = typeof(IGameHost).Assembly;
        Assembly trustedUpdateAssembly = typeof(TrustedModuleSession<>).Assembly;

        var context = new ModuleLoadContext(isCollectible);
        IGameModule? module = null;
        TrustedModuleSession<IGameModule>? session = null;
        var host = new HostGameHost();
        var ledger = new HostLedger();
        var sink = new ResultSink();
        try
        {
            Assembly moduleAssembly = context.LoadFromAssemblyPath(modulePath);
            Type moduleType = moduleAssembly.GetType("TrustedGameGenerics.Module.GameModule", throwOnError: true)!;
            module = (IGameModule)Activator.CreateInstance(moduleType)!;
            session = new TrustedModuleSession<IGameModule>(module);

            TrustedModuleCallResult success = session.Invoke(candidate => candidate.Run(host, ledger, sink, fail: false));
            Check(success.Succeeded, "successful invocation failed: " + success.Failure);
            ModuleOutcome outcome = sink.Single();
            ValidateOutcome(outcome, variant, host, ledger, success.Value, moduleAssembly);
            ResidentSnapshot afterSuccess = Resident();

            int totalAfterSuccess = ledger.Total;
            int applicationsAfterSuccess = ledger.Applications;
            TrustedModuleCallResult failure = session.Invoke(candidate => candidate.Run(host, ledger, sink, fail: true));
            Check(failure.Failure == TrustedModuleCallFailure.CallbackFailed,
                "expected CallbackFailed, got " + failure.Failure);
            bool failureLedgerUnchanged = ledger.Total == totalAfterSuccess
                && ledger.Applications == applicationsAfterSuccess;
            Check(failureLedgerUnchanged, "failed callback mutated the host ledger");
            Check(sink.Count == 1, "failed callback reported an outcome");
            Check(session.IsClosed, "failed callback did not close the session");
            ResidentSnapshot afterFailure = Resident();

            TrustedModuleCallResult closed = session.Invoke(candidate => candidate.Run(host, ledger, sink, fail: false));
            Check(closed.Failure == TrustedModuleCallFailure.Closed,
                "expected Closed after failure, got " + closed.Failure);
            Check(closed.Value == 0, "closed result carried a value");

            return new HostReport(
                Passed: true,
                Variant: variant,
                Outcome: outcome,
                ModulePath: modulePath,
                ModuleSha256: moduleSha256,
                ModuleReportedFullName: outcome.ModuleFullName,
                ModuleReportedMvid: outcome.ModuleMvid,
                LoadedModuleFullName: moduleAssembly.GetName().FullName!,
                LoadedModuleMvid: moduleAssembly.ManifestModule.ModuleVersionId.ToString("D"),
                ContractFullName: contractAssembly.GetName().FullName!,
                ContractMvid: contractAssembly.ManifestModule.ModuleVersionId.ToString("D"),
                ContractPath: contractAssembly.Location,
                TrustedUpdateFullName: trustedUpdateAssembly.GetName().FullName!,
                TrustedUpdateMvid: trustedUpdateAssembly.ManifestModule.ModuleVersionId.ToString("D"),
                TrustedUpdatePath: trustedUpdateAssembly.Location,
                HostFullName: hostAssembly.GetName().FullName!,
                HostMvid: hostAssembly.ManifestModule.ModuleVersionId.ToString("D"),
                HostPath: hostAssembly.Location,
                HostReferences: hostAssembly.GetReferencedAssemblies().Select(name => name.FullName!).ToArray(),
                SuccessValue: success.Value,
                CallCounts: host.SnapshotCounts(),
                EchoTypes: host.EchoTypes,
                EchoReferenceChecksums: host.EchoReferenceChecksums,
                MeasureTypes: host.MeasureTypes,
                MeasureResults: host.MeasureResults,
                FoldResults: host.FoldResults,
                ReduceResults: host.ReduceResults,
                ReduceImplementations: host.ReduceImplementations,
                DelegateResults: host.DelegateResults,
                LateProbe: host.LastLate,
                Ledger: new LedgerSnapshot(ledger.Total, ledger.Applications),
                FailureResult: failure.Failure.ToString(),
                FailureLedgerUnchanged: failureLedgerUnchanged,
                PostFailureResult: closed.Failure.ToString(),
                SessionClosedAfterFailure: session.IsClosed,
                OutcomesReported: sink.Count,
                Invocations: 3,
                Before: before,
                AfterSuccess: afterSuccess,
                AfterFailure: afterFailure,
                StartedUtc: startedUtc,
                CompletedUtc: DateTimeOffset.UtcNow,
                ProcessId: Environment.ProcessId,
                Runtime: RuntimeInformation.FrameworkDescription,
                OSDescription: RuntimeInformation.OSDescription,
                ProcessArchitecture: RuntimeInformation.ProcessArchitecture.ToString(),
                Arguments: Environment.GetCommandLineArgs(),
                RequestedContextMode: contextMode,
                ContextIsCollectible: context.IsCollectible,
                UnloadRequested: context.IsCollectible,
                CollectionClaimed: false);
        }
        finally
        {
            session?.Dispose();
            module = null;
            if (context.IsCollectible)
                context.Unload();
        }
    }

    private static void ValidateOutcome(ModuleOutcome outcome, string variant, HostGameHost host,
        HostLedger ledger, int successValue, Assembly moduleAssembly)
    {
        Check(outcome.Variant == variant, "module variant differs: " + outcome.Variant);
        Check(outcome.LedgerApplications == 6, "module did not apply six ledger effects");
        Check(ledger.Applications == 6, "host ledger applications differ: " + ledger.Applications);
        Check(outcome.LedgerTotal == ledger.Total, "module and host ledger totals differ");
        Check(outcome.AggregateChecksum == successValue, "session return differs from reported aggregate");
        Check(outcome.AggregateChecksum == ScoreChecksum.Aggregate(outcome.ReferenceChecksum,
            outcome.StructChecksum, outcome.NestedChecksum, outcome.InterfaceChecksum,
            outcome.DelegateChecksum, outcome.LateChecksum), "aggregate checksum differs");

        Check(host.EchoCalls == 2, "reference generic calls differ: " + host.EchoCalls);
        Check(host.EchoReferenceChecksums.Count == 2, "reference checksum observations differ");
        Check(outcome.ReferenceChecksum == host.EchoReferenceChecksums[1],
            "reference checksum is not the host-returned state");

        Check(host.MeasureCalls == 3, "struct generic calls differ: " + host.MeasureCalls);
        Check(host.MeasureResults.Count == 3, "struct measurements differ");
        Check(outcome.StructChecksum == unchecked(host.MeasureResults[0] * 3 + host.MeasureResults[1] * 5
            + host.MeasureResults[2] * 7), "struct checksum is not composed from host results");

        Check(host.FoldCalls == 1 && host.FoldResults.Count == 1, "nested container call count differs");
        Check(outcome.NestedChecksum == host.FoldResults[0], "nested checksum is not the host result");

        Check(host.ReduceCalls == 1 && host.ReduceResults.Count == 1, "generic interface call count differs");
        Check(outcome.InterfaceChecksum == host.ReduceResults[0], "interface checksum is not the host result");
        Check(host.ReduceImplementations.Count == 1, "reducer implementation observation differs");

        Check(host.DelegateCalls == 1 && host.DelegateResults.Count == 1, "generic delegate call count differs");
        Check(outcome.DelegateChecksum == host.DelegateResults[0], "delegate checksum is not the host result");

        Check(host.LateCalls == 1, "late generic call count differs");
        LateProbeResult lateProbe = host.LastLate
            ?? throw new InvalidOperationException("late generic result was not observed");
        Check(outcome.LateChecksum == unchecked(lateProbe.Digest + lateProbe.TypeName.Length),
            "late checksum is not the host-observed digest");
        Check(outcome.LateIsValueType && lateProbe.IsValueType, "late type was not a value type");
        Check(outcome.LateAssemblyName == moduleAssembly.GetName().Name,
            "late type did not come from the loaded module");
        Check(outcome.LateTypeName == lateProbe.TypeName, "late type names differ");

        Check(outcome.ContractFullName == typeof(IGameHost).Assembly.GetName().FullName,
            "module did not report the host contract identity");
        Check(outcome.ContractMvid == typeof(IGameHost).Assembly.ManifestModule.ModuleVersionId.ToString("D"),
            "module did not report the host contract MVID");
        Check(outcome.ModuleFullName == moduleAssembly.GetName().FullName,
            "module reported a different assembly identity");
        Check(outcome.ModuleMvid == moduleAssembly.ManifestModule.ModuleVersionId.ToString("D"),
            "module reported a different MVID");

        Check(!moduleAssembly.GetReferencedAssemblies().Any(name => name.Name == moduleAssembly.GetName().Name),
            "module references itself");
        Check(!typeof(Program).Assembly.GetReferencedAssemblies().Any(name => name.Name == moduleAssembly.GetName().Name),
            "host references the module assembly");

        int expectedTotal = 0;
        expectedTotal = unchecked(expectedTotal + ScoreChecksum.Apply(outcome.ReferenceChecksum, 97, 1));
        expectedTotal = unchecked(expectedTotal + ScoreChecksum.Apply(outcome.StructChecksum, 89, 2));
        expectedTotal = unchecked(expectedTotal + ScoreChecksum.Apply(outcome.NestedChecksum, 83, 3));
        expectedTotal = unchecked(expectedTotal + ScoreChecksum.Apply(outcome.InterfaceChecksum, 79, 4));
        expectedTotal = unchecked(expectedTotal + ScoreChecksum.Apply(outcome.DelegateChecksum, 73, 5));
        expectedTotal = unchecked(expectedTotal + ScoreChecksum.Apply(outcome.LateChecksum, 71, 6));
        Check(outcome.LedgerTotal == expectedTotal, "ledger total is not derived from per-shape checksums");
    }

    private static ResidentSnapshot Resident() => new(
        GC.GetTotalMemory(forceFullCollection: false),
        Environment.WorkingSet,
        GC.CollectionCount(0),
        GC.CollectionCount(1),
        GC.CollectionCount(2));

    private static void Write(string path, object value)
    {
        string json = JsonSerializer.Serialize(value, JsonOptions);
        File.WriteAllText(path, json + Environment.NewLine);
        Console.WriteLine(json);
    }

    private static string Value(string[] args, string name)
    {
        int index = Array.IndexOf(args, name);
        if (index < 0 || index + 1 >= args.Length)
            throw new ArgumentException("Missing " + name);
        return args[index + 1];
    }

    private static string OptionalValue(string[] args, string name, string fallback)
    {
        int index = Array.IndexOf(args, name);
        if (index < 0)
            return fallback;
        if (index + 1 >= args.Length)
            throw new ArgumentException("Missing " + name + " value");
        string value = args[index + 1];
        if (string.IsNullOrWhiteSpace(value))
            throw new ArgumentException("Empty " + name + " value");
        return value.Trim();
    }

    private static (string Name, bool IsCollectible) ParseContextMode(string value)
    {
        return value.Trim().ToLowerInvariant() switch
        {
            "collectible" => ("collectible", true),
            "resident" => ("resident", false),
            _ => throw new ArgumentException(
                "Invalid --context-mode '" + value + "'; expected collectible or resident")
        };
    }

    private static void Check(bool condition, string message)
    {
        if (!condition)
            throw new InvalidOperationException(message);
    }
}

internal sealed class HostGameHost : IGameHost
{
    public int EchoCalls { get; private set; }
    public List<string> EchoTypes { get; } = new();
    public List<int> EchoReferenceChecksums { get; } = new();
    public int MeasureCalls { get; private set; }
    public List<string> MeasureTypes { get; } = new();
    public List<int> MeasureResults { get; } = new();
    public int FoldCalls { get; private set; }
    public List<int> FoldResults { get; } = new();
    public int ReduceCalls { get; private set; }
    public List<int> ReduceResults { get; } = new();
    public List<string> ReduceImplementations { get; } = new();
    public int DelegateCalls { get; private set; }
    public List<int> DelegateResults { get; } = new();
    public int LateCalls { get; private set; }
    public LateProbeResult? LastLate { get; private set; }

    public T Echo<T>(T value)
    {
        EchoCalls++;
        EchoTypes.Add(typeof(T).FullName ?? typeof(T).Name);
        if (value is ScorePacket packet)
            EchoReferenceChecksums.Add(ScoreChecksum.Reference(packet));
        return value;
    }

    public int Measure<T>(T value) where T : struct, IGameValue
    {
        MeasureCalls++;
        MeasureTypes.Add(typeof(T).FullName ?? typeof(T).Name);
        int result = ScoreChecksum.Measure(value);
        MeasureResults.Add(result);
        return result;
    }

    public int FoldEnvelopes<T>(IReadOnlyList<ScoreEnvelope<T>> envelopes, int seed)
        where T : struct, IGameValue
    {
        FoldCalls++;
        int result = ScoreChecksum.FoldEnvelopes(envelopes, seed);
        FoldResults.Add(result);
        return result;
    }

    public int Reduce<T>(IReadOnlyList<T> values, IScoreReducer<T> reducer, int seed)
        where T : struct, IGameValue
    {
        ReduceCalls++;
        ReduceImplementations.Add(reducer.GetType().FullName ?? reducer.GetType().Name);
        int result = ScoreChecksum.Reduce(values, reducer, seed);
        ReduceResults.Add(result);
        return result;
    }

    public int Accumulate<T>(IReadOnlyList<T> values, Func<T, int, int> step, int seed)
    {
        DelegateCalls++;
        int result = ScoreChecksum.Accumulate(values, step, seed);
        DelegateResults.Add(result);
        return result;
    }

    public LateProbeResult LateRoundTrip<T>(T value, Func<T, int> digest)
    {
        LateCalls++;
        var result = new LateProbeResult(
            typeof(T).FullName ?? typeof(T).Name,
            typeof(T).Assembly.GetName().Name ?? string.Empty,
            typeof(T).IsValueType,
            digest(value));
        LastLate = result;
        return result;
    }

    public HostCallCounts SnapshotCounts() =>
        new(EchoCalls, MeasureCalls, FoldCalls, ReduceCalls, DelegateCalls, LateCalls);
}

internal sealed class HostLedger : IScoreLedger
{
    private int total;
    private int applications;

    public int Total => total;
    public int Applications => applications;

    public int Add(int delta)
    {
        total = unchecked(total + delta);
        applications++;
        return total;
    }
}

internal sealed class ResultSink : IModuleResultSink
{
    private readonly List<ModuleOutcome> outcomes = new();

    public int Count => outcomes.Count;

    public ModuleOutcome Single()
    {
        if (outcomes.Count != 1)
            throw new InvalidOperationException("Expected one outcome, got " + outcomes.Count);
        return outcomes[0];
    }

    public void Report(ModuleOutcome outcome) => outcomes.Add(outcome);
}

internal sealed class ModuleLoadContext : AssemblyLoadContext
{
    public ModuleLoadContext(bool isCollectible)
        : base("trusted-game-generics", isCollectible)
    {
    }

    protected override Assembly? Load(AssemblyName name)
    {
        Assembly contract = typeof(IGameModule).Assembly;
        if (name.Name == contract.GetName().Name)
        {
            if (name.FullName != contract.GetName().FullName)
                throw new FileLoadException("Contract identity differs: " + name.FullName);
            return contract;
        }

        return null;
    }
}

internal sealed record HostCallCounts(int Echo, int Measure, int Fold, int Reduce, int Delegate, int Late);

internal sealed record LedgerSnapshot(int Total, int Applications);

internal sealed record ResidentSnapshot(long ManagedBytes, long WorkingSetBytes, int Gen0, int Gen1, int Gen2);

internal sealed record HostReport(
    bool Passed,
    string Variant,
    ModuleOutcome Outcome,
    string ModulePath,
    string ModuleSha256,
    string ModuleReportedFullName,
    string ModuleReportedMvid,
    string LoadedModuleFullName,
    string LoadedModuleMvid,
    string ContractFullName,
    string ContractMvid,
    string ContractPath,
    string TrustedUpdateFullName,
    string TrustedUpdateMvid,
    string TrustedUpdatePath,
    string HostFullName,
    string HostMvid,
    string HostPath,
    string[] HostReferences,
    int SuccessValue,
    HostCallCounts CallCounts,
    IReadOnlyList<string> EchoTypes,
    IReadOnlyList<int> EchoReferenceChecksums,
    IReadOnlyList<string> MeasureTypes,
    IReadOnlyList<int> MeasureResults,
    IReadOnlyList<int> FoldResults,
    IReadOnlyList<int> ReduceResults,
    IReadOnlyList<string> ReduceImplementations,
    IReadOnlyList<int> DelegateResults,
    LateProbeResult? LateProbe,
    LedgerSnapshot Ledger,
    string FailureResult,
    bool FailureLedgerUnchanged,
    string PostFailureResult,
    bool SessionClosedAfterFailure,
    int OutcomesReported,
    int Invocations,
    ResidentSnapshot Before,
    ResidentSnapshot AfterSuccess,
    ResidentSnapshot AfterFailure,
    DateTimeOffset StartedUtc,
    DateTimeOffset CompletedUtc,
    int ProcessId,
    string Runtime,
    string OSDescription,
    string ProcessArchitecture,
    string[] Arguments,
    string RequestedContextMode,
    bool ContextIsCollectible,
    bool UnloadRequested,
    bool CollectionClaimed);