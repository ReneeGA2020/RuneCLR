using System.Runtime.CompilerServices;
using TerminalProbe.Contract;
namespace TerminalUGC.Private;
public static class Helper
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void Cleanup(int channel)
    {
        Recorder.Mark(Signal.Helper,channel);
        Action nested = () => Recorder.Mark(Signal.Delegate,channel);
        nested();
    }
}
