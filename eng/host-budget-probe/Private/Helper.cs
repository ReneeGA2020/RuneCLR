using System.Runtime.CompilerServices;
namespace HostBudgetUGC.Private;
public static class Helper
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void Finite(RuneCLR.IMapContext context){context.Log("private-finally");Action callback=()=>context.Log("private-delegate");callback();}
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void Infinite(RuneCLR.IMapContext context){context.Log("private-infinite-finally");int n=0;while(true)n=unchecked(n+1);}
}
