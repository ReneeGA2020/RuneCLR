namespace TrustedGame.Contracts;

public interface IGameRules
{
    int Tick(GameState state, int delta);
}
