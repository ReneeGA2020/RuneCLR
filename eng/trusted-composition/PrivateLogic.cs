using System.Runtime.CompilerServices;
using TrustedComposition.Contract;

namespace TrustedComposition;

public static class PrivateLogic
{
    public static int Count { get; private set; }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int Read()
    {
        ExecutionWitness.Capture("private");
        Count++;
#if PRIVATE_A
        return 101;
#else
        return 202;
#endif
    }
}
