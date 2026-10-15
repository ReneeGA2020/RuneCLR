using System.Runtime.CompilerServices;
using SelectionProbe.Contract;

namespace SelectionUGC.Inline;

public struct Entry : IStaticProbe
{
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static int ReadInline(int value) => value + 31;
}
