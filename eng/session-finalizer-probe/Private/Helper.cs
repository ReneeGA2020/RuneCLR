using System.Runtime.CompilerServices;
using FinalizerProbe.Contract;
namespace FinalizerUGC.Private;
public static class Helper
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int Prepare()=>7;
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void Cleanup()
    {
        Recorder.Mark(Signal.Helper);
        Action body=()=>Recorder.Mark(Signal.Delegate);
        body();
    }
}
