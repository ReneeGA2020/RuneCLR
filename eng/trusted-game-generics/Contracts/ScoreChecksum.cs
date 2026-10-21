namespace TrustedGameGenerics.Contracts;

public static class ScoreChecksum
{
    public static int Reference(ScorePacket packet) =>
        unchecked(packet.Value * 1009 + packet.Revision * 9176 + packet.Name.Length);

    public static int Measure<T>(T value) where T : struct, IGameValue =>
        unchecked(value.Value * 31 + typeof(T).Name.Length + 17);

    public static int FoldEnvelopes<T>(IReadOnlyList<ScoreEnvelope<T>> envelopes, int seed)
        where T : struct, IGameValue
    {
        int accumulated = seed;
        foreach (ScoreEnvelope<T> envelope in envelopes)
        {
            accumulated = unchecked(accumulated * 31 + envelope.Name.Length);
            foreach (KeyValuePair<string, List<T>> group in envelope.Groups.OrderBy(pair => pair.Key, StringComparer.Ordinal))
            {
                accumulated = unchecked(accumulated * 17 + group.Key.Length);
                foreach (T item in group.Value)
                    accumulated = unchecked(accumulated * 101 + item.Value);
            }
        }

        return accumulated;
    }

    public static int Reduce<T>(IReadOnlyList<T> values, IScoreReducer<T> reducer, int seed)
        where T : struct, IGameValue
    {
        int accumulated = seed;
        foreach (T value in values)
            accumulated = reducer.Reduce(value, accumulated);
        return accumulated;
    }

    public static int Accumulate<T>(IReadOnlyList<T> values, Func<T, int, int> step, int seed)
    {
        int accumulated = seed;
        foreach (T value in values)
            accumulated = step(value, accumulated);
        return accumulated;
    }

    public static int Apply(int checksum, uint modulus, int offset) =>
        (int)((uint)checksum % modulus) + offset;

    public static int Aggregate(int reference, int structs, int nested, int interfaceValue, int delegated, int late) =>
        unchecked(reference * 3 + structs * 5 + nested * 7 + interfaceValue * 11 + delegated * 13 + late * 17);
}