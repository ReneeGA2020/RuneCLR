using ScoreGame;

public sealed class Script
{
    public void OnStart(IScoreRules rules)
    {
        rules.Add(0);
    }

    public void OnTick(IScoreRules rules, int amount)
    {
        int zero = amount - amount;
        rules.Add(amount / zero);
    }

    public int Total(IScoreRules rules, int scale)
    {
        return rules.Total() + (scale - scale);
    }
}
