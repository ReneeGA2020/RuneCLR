namespace ScoreGame;

public interface IScoreRules
{
    void Add(int points);
    int Total();
}
