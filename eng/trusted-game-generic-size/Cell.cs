using System.Runtime.CompilerServices;

namespace TrustedGameGenericSize;

// The generic bodies are byte-identical in every variant.  The experiment
// changes only which closed instantiations the public root reaches.
public sealed class Cell<T>
{
    private T _value;

    public Cell(T value) => _value = value;

    [MethodImpl(MethodImplOptions.NoInlining)]
    public T Get() => _value;

    [MethodImpl(MethodImplOptions.NoInlining)]
    public void Set(T value) => _value = value;
}

public static class Ops
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static T Relay<T>(Cell<T> cell) => cell.Get();
}

// Non-generic control used by the baseline.  It performs the same object
// construction / set / relay work without a closed generic instantiation.
public sealed class CellB
{
    private object? _value;

    public CellB(object? value) => _value = value;

    [MethodImpl(MethodImplOptions.NoInlining)]
    public object? Get() => _value;

    [MethodImpl(MethodImplOptions.NoInlining)]
    public void Set(object? value) => _value = value;
}

public static class OpsB
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static object? Relay(CellB cell) => cell.Get();
}

public sealed class RefA
{
    public int Value;

    public RefA(int value) => Value = value;
}

public sealed class RefB
{
    public int Value;

    public RefB(int value) => Value = value;
}

public sealed class RefC
{
    public int Value;

    public RefC(int value) => Value = value;
}

public readonly struct Blob
{
    public readonly long A;
    public readonly long B;
    public readonly long C;

    public Blob(long a, long b, long c)
    {
        A = a;
        B = b;
        C = c;
    }
}

