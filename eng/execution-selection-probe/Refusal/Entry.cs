using System.Runtime.CompilerServices;

namespace SelectionUGC.Refusal;

public static class Entry
{
    // Valid IL deliberately refused only by the candidate's scoped test switch.
    // The unmarked control executes these same bytes through native fallback.
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int Reject() => 73;
}
