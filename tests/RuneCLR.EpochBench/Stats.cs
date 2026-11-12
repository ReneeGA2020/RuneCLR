namespace RuneCLR.EpochBench;

public static class Stats
{
    public static double Median(IReadOnlyList<double> values) => Quantile(values, 0.5);

    public static double Quantile(IReadOnlyList<double> values, double q)
    {
        if (values.Count == 0) return double.NaN;
        var ordered = values.OrderBy(value => value).ToArray();
        var index = (int)Math.Round((ordered.Length - 1) * q, MidpointRounding.AwayFromZero);
        return ordered[Math.Clamp(index, 0, ordered.Length - 1)];
    }

    public static (int Positive, int Negative) SignCount(IReadOnlyList<double> deltas)
    {
        var positive = deltas.Count(delta => delta > 0);
        return (positive, deltas.Count - positive);
    }
}
