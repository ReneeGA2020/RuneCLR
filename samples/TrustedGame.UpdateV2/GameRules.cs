using TrustedGame.Contracts;

namespace TrustedGame.Update;

public sealed class GameRules : IGameRules
{
    public int Tick(GameState state, int delta)
    {
        ArgumentNullException.ThrowIfNull(state);
        if (delta < 0)
            throw new ArgumentOutOfRangeException(nameof(delta), "delta must be non-negative");

        state.Score += delta * 2;
        state.Ticks++;
        return state.Score;
    }
}
