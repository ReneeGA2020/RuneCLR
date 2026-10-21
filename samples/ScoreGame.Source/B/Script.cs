using ScoreGame;

public sealed class Script
{
    public void OnStart(IScoreRules rules)
    {
        rules.Add(0);
    }

    public void OnTick(IScoreRules rules, int amount)
    {
        rules.Add(amount * 10);
    }

    public int Total(IScoreRules rules, int scale)
    {
        return rules.Total() + (scale - scale);
    }
}
