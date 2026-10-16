using System.Runtime.CompilerServices;
using TrustedComposition.Contract;

namespace TrustedComposition;

public static class IlOnlyHelper
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int Compute(int value)
    {
        ExecutionWitness.Capture("helper");
        return value * 3 + 7;
    }
}
