using System.Runtime.CompilerServices;
using ScoreGame;
using RuneCLR.Runtime;

if (args.Length != 3)
{
    Console.Error.WriteLine("Usage: ScoreGame.Host <version-a package.json> <version-b package.json> <fail package.json>");
    return 2;
}

var a = RunAdding("SCORE_A", args[0], 3);
var b = RunAdding("SCORE_B", args[1], 30);
var failed = RunFault(args[2]);
var recovered = RunAdding("SCORE_RECOVER", args[0], 3);
var ok = a && b && failed && recovered;
Console.WriteLine(ok
    ? "SCORE_DESKTOP managed-il not-interpreter not-ios not-sandbox"
    : "SCORE_DESKTOP failed");
return ok ? 0 : 1;

static bool RunAdding(string label, string manifest, int expected)
{
    var board = new ScoreBoard();
    var session = HostContractSession.Open(manifest, typeof(IScoreRules), board);
    session.Invoke("OnTick", 1);
    session.Invoke("OnTick", 1);
    session.Invoke("OnTick", 1);
    var callback = session.InvokeInt("Total", 0);
    var points = board.Points;
    var collected = Collect(session);
    Console.WriteLine(label + " total=" + points + " callback=" + callback + " collected=" + collected.ToString().ToLowerInvariant());
    return points == expected && callback == expected && collected;
}

static bool RunFault(string manifest)
{
    var board = new ScoreBoard();
    var session = HostContractSession.Open(manifest, typeof(IScoreRules), board);
    var kind = "none";
    try
    {
        session.Invoke("OnTick", 1);
    }
    catch (InvalidOperationException error)
    {
        kind = error.Message.Contains("DivideByZeroException", StringComparison.Ordinal)
            ? "DivideByZeroException" : "other";
    }

    var points = board.Points;
    var collected = Collect(session);
    Console.WriteLine("SCORE_FAIL " + kind + " total=" + points + " collected=" + collected.ToString().ToLowerInvariant());
    return kind == "DivideByZeroException" && points == 0 && collected;
}

[MethodImpl(MethodImplOptions.NoInlining)]
static bool Collect(HostContractSession session)
{
    var reference = session.ContextReference;
    session.Dispose();
    for (var attempt = 0; attempt < 10 && reference.IsAlive; attempt++)
    {
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
    }

    return !reference.IsAlive;
}

sealed class ScoreBoard : IScoreRules
{
    public int Points { get; private set; }

    public void Add(int points) => Points += points;

    public int Total() => Points;
}
