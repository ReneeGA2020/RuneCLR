using System.Runtime.InteropServices;

namespace RuneCLR.GroupedHost.Fixtures;

/// <summary>
/// Negative author-admission fixture: the author assembly itself declares a direct kernel32 P/Invoke.
/// The grouped host is expected to reject this assembly at admission, before any code executes.
/// Not referenced by the normal Author.A/B fixtures.
/// </summary>
public static class AuthorEntry
{
    /// <summary>Author tag for the rejected variant.</summary>
    public const string Tag = "NativeRejected";

    /// <summary>Static run counter (would never increment when admission rejects the assembly).</summary>
    public static int RunCount { get; private set; }

    /// <summary>
    /// Would call kernel32!GetCurrentThreadId directly from author code. The grouped host must reject
    /// this assembly before this method runs; the return value is only meaningful if admission is
    /// incorrectly allowed.
    /// </summary>
    public static int Run(IGroupedHostContract host, int value)
    {
        ArgumentNullException.ThrowIfNull(host);
        RunCount++;
        host.Record("author:NativeRejected:run=" + RunCount + ":value=" + value);
        return NativeThreadId.GetCurrentThreadId();
    }

    private static class NativeThreadId
    {
        [DllImport("kernel32.dll")]
        internal static extern int GetCurrentThreadId();
    }
}
