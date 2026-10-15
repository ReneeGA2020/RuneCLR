using System.Runtime.CompilerServices;
using SelectionProbe.Contract;
using SelectionUGC.Private;

namespace SelectionUGC.Payload;

public interface IDefaultProbe { int DefaultRead() => 17; }
public class VirtualBase { public virtual int VirtualRead() => 2; }
public sealed class Entry : VirtualBase, IProbe, IDefaultProbe
{
    private static int starts;
    private static int instances;
    private int filterHits;
    static Entry() { starts++; }
    public Entry() { instances++; }
    public int Value => 7;
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public int InlineAdd(int value) => value + Value;
    public override int VirtualRead() => 13;
    private bool Accept(Exception exception) { filterHits++; return exception is InvalidOperationException; }
    public ProbeResult Run()
    {
        var state = new PrivateState();
        int captured = 4;
        Func<int> callback = () => captured + Value;
        try { throw new InvalidOperationException("expected author failure"); }
        catch (Exception exception) when (Accept(exception)) { }
        return new(starts, instances, Value, InlineAdd(5), GenericState<string>.Next(),
            GenericState<string>.Identity(19), callback(), ((VirtualBase)this).VirtualRead(),
            ((IDefaultProbe)this).DefaultRead(), filterHits, PrivateState.Starts, state.Instances,
            state.Value, state.InlineAdd(8), PrivateGeneric<string>.Next(),
            PrivateGeneric<string>.Identity(41), state.MakeDelegate(12)());
    }
}

public static class GenericState<T>
{
    private static int starts;
    static GenericState() { starts++; }
    public static int Next() => starts++;
    public static TItem Identity<TItem>(TItem value) => value;
}
