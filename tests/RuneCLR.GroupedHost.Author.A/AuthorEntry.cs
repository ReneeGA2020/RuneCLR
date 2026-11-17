using System.Runtime.CompilerServices;

namespace RuneCLR.GroupedHost.Fixtures;

/// <summary>Fixture-defined failure for the author initialization mode; the host must surface a type-only failure.</summary>
public sealed class AuthorInitException : Exception
{
    public AuthorInitException() : base("author-init-failure")
    {
    }
}

/// <summary>Fixture-defined failure for the author callback mode; the host must surface a type-only failure.</summary>
public sealed class AuthorCallbackException : Exception
{
    public AuthorCallbackException() : base("author-callback-failure")
    {
    }
}

/// <summary>
/// Author-side fixture (A). Same AssemblyName as the other author variant; identity differs by
/// content/MVID and by the tag reported at run time.
/// </summary>
public static class AuthorEntry
{
    /// <summary>Author variant tag.</summary>
    public const string Tag = "A";

    /// <summary>Per-assembly static run counter (never reset by the fixtures).</summary>
    public static int RunCount { get; private set; }

    /// <summary>Per-assembly static token created on first use.</summary>
    public static string Token { get; private set; } = "uninitialized";

    private static Action? s_authorCallback;
    private static IGroupedHostContract? s_witnessHost;

    /// <summary>
    /// Runs one author call.
    /// value >= 0  : returns value + 100 after proving shared framework access.
    /// value == -1 : throws AuthorCallbackException after the callback is installed.
    /// value == -2 : throws AuthorInitException before touching statics.
    /// value == -3 : calls FrameworkEntry.NativeThreadProbe() and returns its value. This is a positive
    ///               trusted-native bridge probe through the trusted framework API, not an author P/Invoke;
    ///               it is subject to the host's explicit API allow policy.
    /// </summary>
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int Run(IGroupedHostContract host, int value)
    {
        ArgumentNullException.ThrowIfNull(host);
        if (value == -2)
        {
            throw new AuthorInitException();
        }

        RunCount++;
        if (Token == "uninitialized")
        {
            Token = "author-A-" + Guid.NewGuid().ToString("N");
        }

        host.Record("author:A:initial:run=" + RunCount + ":token=" + Token);
        host.Record(FrameworkEntry.Describe("A"));
        int touched = FrameworkEntry.Touch("A");
        host.Record("author:A:framework-touch=" + touched);

        if (IsWitnessMode(host.Mode))
        {
            // Witness modes bind the direct no-argument method group so the specified OnFrameworkEvent
            // method itself is the callback entry; the host is retained in an author-owned static only.
            s_witnessHost = host;
            s_authorCallback ??= OnFrameworkEvent;
        }
        else
        {
            // Original closure baseline: unchanged behaviour, no policy widening.
            s_authorCallback ??= () => OnFrameworkEventCore(host);
        }
        FrameworkEntry.SubscribeFrameworkEvent(s_authorCallback);

        // Retention negative control: the host holds this delegate in its own external root until
        // it calls Unsubscribe. Fixtures never reset static fields to fake collection.
        Action hostCallback = () => host.Record("author:A:host-event-fired");
        host.Subscribe(hostCallback);
        host.Record("author:A:current:run=" + RunCount + ":token=" + Token);

        if (IsWitnessMode(host.Mode))
        {
            host.Record("author:" + Tag + ":witness-entry:mode=" + host.Mode + ":run=" + RunCount + ":token=" + Token);
        }
        if (host.DynamicImage is { Length: > 0 })
        {
            AttemptDynamicLoad(host);
        }
        if (value == -1)
        {
            throw new AuthorCallbackException();
        }
        if (value == -3)
        {
            return FrameworkEntry.NativeThreadProbe();
        }
        return value + 100;
    }

    /// <summary>
    /// Author-owned framework event callback. Under the host mode "raise-denied-reflection" it records
    /// the attempt and then reflects an explicitly denied target (String.StartsWith) so the runtime's
    /// origin scan must reject it even though no InvokeAuthor scope surrounds the framework entry.
    /// </summary>
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void OnFrameworkEvent()
    {
        OnFrameworkEventCore(s_witnessHost!);
    }

    // Ordinal prefix check that avoids String.StartsWith, which the fixture policy denies for the callback case.
    private static bool IsWitnessMode(string mode)
    {
        return mode.Length >= 7 && string.CompareOrdinal(mode, 0, "witness", 0, 7) == 0;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void OnFrameworkEventCore(IGroupedHostContract host)
    {
        host.Record("author:" + Tag + ":framework-event-fired");
        if (IsWitnessMode(host.Mode))
        {
            host.Record("author:" + Tag + ":witness-callback:mode=" + host.Mode);
            return;
        }
        if (!string.Equals(host.Mode, "raise-denied-reflection", StringComparison.Ordinal))
        {
            return;
        }
        host.Record("author:" + Tag + ":reflection-attempt");
        try
        {
            var method = typeof(string).GetMethod("StartsWith", new[] { typeof(string) });
            if (method is null)
            {
                host.Record("author:" + Tag + ":reflection-missing-target");
                return;
            }
            var value = method.Invoke("abc", new object[] { "a" });
            host.Record("author:" + Tag + ":reflection-allowed:" + value);
        }
        catch (Exception error)
        {
            host.Record("author:" + Tag + ":reflection-denied:type=" + error.GetType().Name
                + ":inner=" + (error.InnerException is null ? "null" : error.InnerException.GetType().Name)
                + ":message=" + error.Message);
            throw;
        }
    }

    /// <summary>
    /// Dynamic admission probe: host.Mode carries an absolute path to a NativeRejected author image
    /// that is not part of the group's initial role catalogs. The strict load hook must reject it.
    /// </summary>
    private static void AttemptDynamicLoad(IGroupedHostContract host)
    {
        host.Record("author:" + Tag + ":dynamic-load-attempt");
        var context = System.Runtime.Loader.AssemblyLoadContext.GetLoadContext(typeof(AuthorEntry).Assembly);
        if (context is null)
        {
            host.Record("author:" + Tag + ":dynamic-load-skipped:no-context");
            return;
        }
        try
        {
            using var stream = new System.IO.MemoryStream(host.DynamicImage, writable: false);
            _ = context.LoadFromStream(stream);
            host.Record("author:" + Tag + ":dynamic-load-ALLOWED");
        }
        catch (Exception error)
        {
            var message = error.Message.Length > 240 ? error.Message.Substring(0, 240) : error.Message;
            host.Record("author:" + Tag + ":dynamic-load-rejected:" + error.GetType().Name + ":message=" + message);
        }
    }
}
