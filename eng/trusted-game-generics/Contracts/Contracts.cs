namespace TrustedGameGenerics.Contracts;

public interface IScoreLedger
{
    int Total { get; }
    int Applications { get; }
    int Add(int delta);
}

public interface IGameValue
{
    int Value { get; }
}

public interface IScoreReducer<T>
{
    int Reduce(T value, int accumulated);
}

public interface IModuleResultSink
{
    void Report(ModuleOutcome outcome);
}

public interface IGameModule
{
    int Run(IGameHost host, IScoreLedger ledger, IModuleResultSink sink, bool fail);
}

public interface IGameHost
{
    T Echo<T>(T value);
    int Measure<T>(T value) where T : struct, IGameValue;
    int FoldEnvelopes<T>(IReadOnlyList<ScoreEnvelope<T>> envelopes, int seed) where T : struct, IGameValue;
    int Reduce<T>(IReadOnlyList<T> values, IScoreReducer<T> reducer, int seed) where T : struct, IGameValue;
    int Accumulate<T>(IReadOnlyList<T> values, Func<T, int, int> step, int seed);
    LateProbeResult LateRoundTrip<T>(T value, Func<T, int> digest);
}

public sealed class ScorePacket
{
    public ScorePacket(string name, int value, int revision)
    {
        Name = name;
        Value = value;
        Revision = revision;
    }

    public string Name { get; }
    public int Value { get; }
    public int Revision { get; set; }
}

public readonly struct ScoreVector : IGameValue
{
    public ScoreVector(int x, int y, int z)
    {
        X = x;
        Y = y;
        Z = z;
    }

    public int X { get; }
    public int Y { get; }
    public int Z { get; }
    public int Value => unchecked(X * 3 + Y * 5 + Z * 7);
}

public readonly struct ScorePair : IGameValue
{
    public ScorePair(long left, short right)
    {
        Left = left;
        Right = right;
    }

    public long Left { get; }
    public short Right { get; }
    public int Value => unchecked((int)(Left ^ (Left >> 32)) + Right * 37);
}

public readonly struct ScoreStamp : IGameValue
{
    public ScoreStamp(Guid id, byte kind)
    {
        Id = id;
        Kind = kind;
    }

    public Guid Id { get; }
    public byte Kind { get; }
    public int Value => unchecked(Id.GetHashCode() + Kind * 53);
}

public sealed class ScoreEnvelope<T> where T : struct, IGameValue
{
    public ScoreEnvelope(string name) => Name = name;

    public string Name { get; }
    public Dictionary<string, List<T>> Groups { get; } = new(StringComparer.Ordinal);
}

public sealed record LateProbeResult(string TypeName, string AssemblyName, bool IsValueType, int Digest);

public sealed record ModuleOutcome(
    string Variant,
    int ReferenceChecksum,
    int StructChecksum,
    int NestedChecksum,
    int InterfaceChecksum,
    int DelegateChecksum,
    int LateChecksum,
    string LateTypeName,
    string LateAssemblyName,
    bool LateIsValueType,
    string ContractFullName,
    string ContractMvid,
    string ModuleFullName,
    string ModuleMvid,
    int LedgerTotal,
    int LedgerApplications,
    int AggregateChecksum);