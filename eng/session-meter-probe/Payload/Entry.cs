using System.Runtime.CompilerServices;
using MeterProbe.Contract;
using MeterUGC.Private;
namespace MeterUGC.Payload;
public class Base
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public virtual int ReadVirtual() => 2;
}
public sealed class Entry : Base, IWork, IStaticWork
{
    private static int starts;
    private static int instances;
    private readonly int seed;
    static Entry() { starts++; }
    public Entry() { instances++; seed = 7; }
    public int Starts => starts;
    public int Instances => instances;
    [MethodImpl(MethodImplOptions.NoInlining)]
    public int Empty() => seed;
    [MethodImpl(MethodImplOptions.NoInlining)]
    public int Loop(int count)
    {
        int sum = 0;
        for (int i = 0; i < count; i++) sum += i;
        return sum;
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public int Helper() => new Helper().Read() + seed;
    [MethodImpl(MethodImplOptions.NoInlining)]
    public override int ReadVirtual() => seed + 2;
    [MethodImpl(MethodImplOptions.NoInlining)]
    private int Direct() => seed + 3;
    [MethodImpl(MethodImplOptions.NoInlining)]
    public int Paths()
    {
        int captured = 4;
        Func<int> callback = () => Direct() + captured;
        Base target = this;
        return Direct() + target.ReadVirtual() + callback();
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static bool Filter(ref int value) { value += 2; return true; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public int Exceptions()
    {
        int value = 0;
        try { throw new InvalidOperationException("meter finite EH fixture"); }
        catch (InvalidOperationException) when (Filter(ref value)) { value += 3; }
        finally { value += 5; }
        return value;
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public int AfterZero() => Loop(8) + seed;
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int ReadStatic() => starts + 40;
}
