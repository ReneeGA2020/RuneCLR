using System.Reflection;
using System.Runtime.CompilerServices;
using TrustedGameGenerics.Contracts;

namespace TrustedGameGenerics.Module;

public sealed partial class GameModule : IGameModule
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public int Run(IGameHost host, IScoreLedger ledger, IModuleResultSink sink, bool fail)
    {
        if (fail)
            throw new ModuleFailureException("fixture failure before ledger mutation");

        var packet = new ScorePacket("ref-" + VariantLabel, 7 + VariantCode, 0);
        ScorePacket firstEcho = host.Echo(packet);
        if (!ReferenceEquals(firstEcho, packet))
            throw new InvalidOperationException("reference identity was not preserved");
        firstEcho.Revision = 11 + VariantCode;
        ScorePacket secondEcho = host.Echo(firstEcho);
        int referenceChecksum = ScoreChecksum.Reference(secondEcho);
        if (referenceChecksum != ScoreChecksum.Reference(packet))
            throw new InvalidOperationException("reference state checksum differs");

        var vector = new ScoreVector(2 + VariantCode, 3 + VariantCode, 5 + VariantCode);
        var pair = new ScorePair(7_000_000_000L + VariantCode, (short)(13 + VariantCode));
        var stamp = new ScoreStamp(new Guid("8c2d4f2e-4f5a-4b39-9a6f-0f1c2d3e4f50"), (byte)(3 + VariantCode));
        int vectorMeasure = host.Measure(vector);
        int pairMeasure = host.Measure(pair);
        int stampMeasure = host.Measure(stamp);
        if (vectorMeasure != ScoreChecksum.Measure(vector)
            || pairMeasure != ScoreChecksum.Measure(pair)
            || stampMeasure != ScoreChecksum.Measure(stamp))
            throw new InvalidOperationException("struct measurements differ");
        int structChecksum = unchecked(vectorMeasure * 3 + pairMeasure * 5 + stampMeasure * 7);

        var envelopes = new List<ScoreEnvelope<ScoreVector>>
        {
            CreateEnvelope("env-" + VariantLabel + "-one", VariantCode, 3),
            CreateEnvelope("env-" + VariantLabel + "-two", VariantCode + 4, 2)
        };
        int nestedChecksum = host.FoldEnvelopes(envelopes, 100 + VariantCode);
        if (nestedChecksum != ScoreChecksum.FoldEnvelopes(envelopes, 100 + VariantCode))
            throw new InvalidOperationException("nested generic container checksum differs");

        var pairs = new ScorePair[]
        {
            new(11_000_000L + VariantCode, (short)(2 + VariantCode)),
            new(22_000_000L + VariantCode, (short)(4 + VariantCode)),
            new(33_000_000L + VariantCode, (short)(6 + VariantCode))
        };
        var reducer = new VariantReducer(VariantReducerFactor);
        int interfaceChecksum = host.Reduce(pairs, reducer, 9 + VariantCode);
        if (interfaceChecksum != ScoreChecksum.Reduce(pairs, reducer, 9 + VariantCode))
            throw new InvalidOperationException("generic interface checksum differs");

        var vectors = new ScoreVector[]
        {
            new(VariantCode, 2 + VariantCode, 3 + VariantCode),
            new(4 + VariantCode, 5 + VariantCode, 6 + VariantCode),
            new(7 + VariantCode, 8 + VariantCode, 9 + VariantCode)
        };
        Func<ScoreVector, int, int> step = static (value, accumulated) => unchecked(accumulated * 13 + value.Value);
        int delegateChecksum = host.Accumulate(vectors, step, 9 + VariantCode);
        if (delegateChecksum != ScoreChecksum.Accumulate(vectors, step, 9 + VariantCode))
            throw new InvalidOperationException("generic delegate checksum differs");

        var token = new LateToken(VariantCode + 5, VariantSalt, "late-" + VariantLabel);
        int expectedLateDigest = LateDigest(token);
        LateProbeResult late = host.LateRoundTrip(token, LateDigest);
        if (!late.IsValueType
            || late.TypeName != typeof(LateToken).FullName
            || late.AssemblyName != typeof(LateToken).Assembly.GetName().Name
            || late.Digest != expectedLateDigest)
            throw new InvalidOperationException("author-private late type interaction differs");
        int lateChecksum = unchecked(late.Digest + late.TypeName.Length);

        ledger.Add(ScoreChecksum.Apply(referenceChecksum, 97, 1));
        ledger.Add(ScoreChecksum.Apply(structChecksum, 89, 2));
        ledger.Add(ScoreChecksum.Apply(nestedChecksum, 83, 3));
        ledger.Add(ScoreChecksum.Apply(interfaceChecksum, 79, 4));
        ledger.Add(ScoreChecksum.Apply(delegateChecksum, 73, 5));
        ledger.Add(ScoreChecksum.Apply(lateChecksum, 71, 6));

        int aggregate = ScoreChecksum.Aggregate(referenceChecksum, structChecksum, nestedChecksum,
            interfaceChecksum, delegateChecksum, lateChecksum);
        AssemblyName contractName = typeof(IGameHost).Assembly.GetName();
        AssemblyName moduleName = typeof(GameModule).Assembly.GetName();
        var outcome = new ModuleOutcome(
            VariantLabel,
            referenceChecksum,
            structChecksum,
            nestedChecksum,
            interfaceChecksum,
            delegateChecksum,
            lateChecksum,
            late.TypeName,
            late.AssemblyName,
            late.IsValueType,
            contractName.FullName!,
            typeof(IGameHost).Assembly.ManifestModule.ModuleVersionId.ToString("D"),
            moduleName.FullName!,
            typeof(GameModule).Assembly.ManifestModule.ModuleVersionId.ToString("D"),
            ledger.Total,
            ledger.Applications,
            aggregate);
        sink.Report(outcome);
        return aggregate;
    }

    private static ScoreEnvelope<ScoreVector> CreateEnvelope(string name, int seed, int count)
    {
        var envelope = new ScoreEnvelope<ScoreVector>(name);
        envelope.Groups["alpha"] = new List<ScoreVector>();
        envelope.Groups["beta"] = new List<ScoreVector>();
        for (int index = 0; index < count; index++)
        {
            int x = seed + index;
            envelope.Groups["alpha"].Add(new ScoreVector(x, x + 1, x + 2));
            envelope.Groups["beta"].Add(new ScoreVector(x + 10, x + 11, x + 12));
        }

        return envelope;
    }

    private static int LateDigest(LateToken token) =>
        unchecked(token.Seed * 7919 + token.Salt * 104729 + token.Label.Length);
}

internal sealed class VariantReducer(int factor) : IScoreReducer<ScorePair>
{
    public int Reduce(ScorePair value, int accumulated) => unchecked(accumulated * factor + value.Value);
}

internal readonly struct LateToken
{
    public LateToken(int seed, int salt, string label)
    {
        Seed = seed;
        Salt = salt;
        Label = label;
    }

    public int Seed { get; }
    public int Salt { get; }
    public string Label { get; }
}

internal sealed class ModuleFailureException(string message) : Exception(message) { }