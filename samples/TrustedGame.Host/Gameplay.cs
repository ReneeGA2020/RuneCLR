using RuneCLR.TrustedUpdate;
using TrustedGame.Contracts;

internal static class Gameplay
{
    public static void Run(TrustedModuleSession<IGameRules> normal, Type rulesType, int expectedScoreMultiplier)
    {
        var expectedFirst = expectedScoreMultiplier;
        var expectedSecond = checked(3 * expectedScoreMultiplier);
        var expectedThird = checked(6 * expectedScoreMultiplier);
        var normalState = new GameState();
        try
        {
            var first = normal.Invoke(item => item.Tick(normalState, 1));
            Require(first.Succeeded && first.Value == expectedFirst, "first tick returned " + first.Value);
            var second = normal.Invoke(item => item.Tick(normalState, 2));
            Require(second.Succeeded && second.Value == expectedSecond, "second tick returned " + second.Value);
            var third = normal.Invoke(item => item.Tick(normalState, 3));
            Require(third.Succeeded && third.Value == expectedThird, "third tick returned " + third.Value);
            Require(normalState.Score == expectedThird && normalState.Ticks == 3, "shared GameState did not reach expected score/ticks");
            Console.WriteLine($"TRUSTED-GAME normal results={first.Value},{second.Value},{third.Value} score={normalState.Score} ticks={normalState.Ticks} multiplier={expectedScoreMultiplier}");

            normal.Close();
            Require(normal.IsClosed, "session did not close");
            normal.Close();
            normal.Dispose();
            Require(normal.IsClosed, "session did not remain closed");

            var closed = normal.Invoke(item => item.Tick(normalState, 4));
            Require(!closed.Succeeded && closed.Failure == TrustedModuleCallFailure.Closed,
                "invoke after close did not return Closed");
            Require(normalState.Score == expectedThird && normalState.Ticks == 3,
                "invoke after close entered the module");
        }
        finally
        {
            normal.Dispose();
        }

        var negativeState = new GameState();
        var negative = new TrustedModuleSession<IGameRules>(
            (IGameRules)Activator.CreateInstance(rulesType)!);
        try
        {
            var failed = negative.Invoke(item => item.Tick(negativeState, -1));
            Require(!failed.Succeeded && failed.Failure == TrustedModuleCallFailure.CallbackFailed,
                "negative delta did not return CallbackFailed");
            Require(negative.IsClosed, "negative delta did not close the session");
            Require(negativeState.Score == 0 && negativeState.Ticks == 0,
                "negative delta mutated host state");

            var after = negative.Invoke(item => item.Tick(negativeState, 4));
            Require(!after.Succeeded && after.Failure == TrustedModuleCallFailure.Closed,
                "invoke after callback failure did not return Closed");
            Require(negativeState.Score == 0 && negativeState.Ticks == 0,
                "callback after failure entered the module");
            Console.WriteLine($"TRUSTED-GAME negative failure={failed.Failure} next={after.Failure} score={negativeState.Score}");
        }
        finally
        {
            negative.Dispose();
        }
    }

    static void Require(bool condition, string message)
    {
        if (!condition)
            throw new InvalidOperationException(message);
    }
}
