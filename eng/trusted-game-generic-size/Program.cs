using System.Runtime.CompilerServices;

namespace TrustedGameGenericSize;

public static class Program
{
    // Real public root: Main calls Root, Root calls every selected closed
    // specialization.  No variant relies on dead declarations alone.
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static object?[] Root()
    {
        var results = new object?[8];
        VariantRoot.Fill(results);
        return results;
    }

    public static int Main()
    {
        return Root().Length;
    }
}

