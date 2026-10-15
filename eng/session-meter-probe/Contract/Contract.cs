using System.Runtime.CompilerServices;
namespace MeterProbe.Contract;
public interface IWork
{
    int Starts { get; }
    int Instances { get; }
    int Empty();
    int Loop(int count);
    int Helper();
    int Paths();
    int Exceptions();
    int AfterZero();
}
public interface IStaticWork { static abstract int ReadStatic(); }
public static class TrustedCaller
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int Generic<T>() where T : IStaticWork => T.ReadStatic() + 5;
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int Call(IWork work) => work.Helper() + 3;
}
