using System.Runtime.CompilerServices;
using BatchBoundary.Contract;

namespace BatchBoundary.Author;

public static class Entries
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int ShortReturn() => 73;

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int OrdinaryThrow() => throw new InvalidOperationException("ordinary boundary control");

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int FiniteProgress()
    {
        Progress.Start();
        int sum = 0;
        int completed = 0;
        for (int i = 0; i < 7; i++)
        {
            sum += i;
            completed++;
        }
        Progress.ReportIterations(completed);
        Progress.Returning();
        return sum;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int EndlessCatch()
    {
        Progress.Start();
        int iterations = 0;
        try
        {
            try
            {
                // Keep the hot block pure: a trusted marker call would flush every iteration.
                while (true) iterations = unchecked(iterations + 1);
            }
            catch (Exception)
            {
                Progress.Caught();
            }
        }
        finally { Progress.FinallyProgress(iterations); }
        Progress.Returning();
        return -1;
    }
}
