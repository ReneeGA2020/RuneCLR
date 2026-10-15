using System.Runtime.CompilerServices;
namespace MeterUGC.Private;
public sealed class Helper
{
    private static readonly int Seed;
    private readonly int value;
    static Helper() { Seed = 11; }
    public Helper() { value = Seed + 2; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public int Read() => Identity<int>(value) + Generic<int>.Seed;
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static T Identity<T>(T value) => value;
}
internal static class Generic<T>
{
    public static readonly int Seed;
    static Generic() { Seed = 7; }
}
