using System.Runtime.CompilerServices;
using SelectionProbe.Contract;

namespace SelectionUGC.Boxed;

public struct Entry : IBoxProbe
{
    private static int starts;
    private static int instances;
    private int value;
    static Entry() { starts++; }
    public Entry() { instances++; value = 17; }
    public int Starts => starts;
    public int Instances => instances;
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public int Read() => value;
}
