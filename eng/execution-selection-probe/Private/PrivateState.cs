using System.Runtime.CompilerServices;

namespace SelectionUGC.Private;

public sealed class PrivateState
{
    private static int starts;
    private static int instances;
    static PrivateState() { starts++; }
    public PrivateState() { instances++; }
    public static int Starts => starts;
    public int Instances => instances;
    public int Value => 30;
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public int InlineAdd(int value) => value + Value;
    public Func<int> MakeDelegate(int captured) => () => captured + Value;
}

public static class PrivateGeneric<T>
{
    private static int starts;
    static PrivateGeneric() { starts++; }
    public static int Next() => starts++;
    public static TItem Identity<TItem>(TItem value) => value;
}
