using System.Reflection;

// The portable diagnostic build omits the trusted framework native bridge so the framework role
// image contains no P/Invoke. It exists only because the current GroupedHostSession framework
// catalog applies the managed-IL intake profile (which rejects P/Invoke) to the trusted framework
// role; see tests/RuneCLR.GroupedHost.Tests/README.md. The default build keeps the real probe.
#if !GROUPED_HOST_PORTABLE_FRAMEWORK
using System.Runtime.InteropServices;
#endif

namespace RuneCLR.GroupedHost.Fixtures;

/// <summary>
/// Framework-side fixture. Static state belongs to the loaded framework assembly in its own load
/// context; it is not process-wide by construction. The harness proves that one selected framework
/// assembly instance is shared by both author assemblies by comparing observed tokens/counters.
/// </summary>
/// <summary>
/// Fixture-defined failure type for the framework initialization mode. A grouped host is expected to
/// surface a host-owned, type-only failure that names this bounded type and drops the message and any
/// inner exception, so the framework domain never leaks metadata across the boundary.
/// </summary>
public sealed class FrameworkInitException : Exception
{
    public FrameworkInitException() : base("framework-init-failure")
    {
    }
}

public static class FrameworkEntry
{    private sealed class FrameworkInstance
    {
        internal FrameworkInstance(string token) => Token = token;
        internal string Token { get; }
    }

    private static int s_initCount;
    private static FrameworkInstance s_instance = new("uninitialized");
    private static int s_callCount;
    private static Action? s_frameworkEvent;

    /// <summary>Number of successful Initialize calls in this loaded framework assembly.</summary>
    public static int StaticInitCount => s_initCount;

    /// <summary>Token of the current framework instance (fresh on every Initialize call).</summary>
    public static string InstanceToken => s_instance.Token;

    /// <summary>Number of Touch calls seen by this loaded framework assembly.</summary>
    public static int CallCount => s_callCount;

    /// <summary>
    /// Initializes the fixture. The mode comes from <see cref="IGroupedHostContract.Mode"/>:
    /// "normal" records the init line and returns; "throw-init" records it and then throws a generic
    /// framework-init failure. No host or business static is reset by this method.
    /// </summary>
    public static void Initialize(IGroupedHostContract host)
    {
        ArgumentNullException.ThrowIfNull(host);
        string mode = host.Mode;
        if (mode == "raise-denied-reflection")
        {
            // Test-only mode: raise the existing static event without re-initializing any state.
            Action? current = s_frameworkEvent;
            current?.Invoke();
            return;
        }
        if (mode == "framework-own-reflection")
        {
            // Test-only mode: trusted framework-owned reflection with no author frame.
            var marker = typeof(FrameworkEntry).GetMethod("PrivateFrameworkMarker", BindingFlags.NonPublic | BindingFlags.Static);
            if (marker is null)
            {
                host.Record("framework:own-reflection:missing-marker");
                throw new FrameworkInitException();
            }
            var value = (int)marker.Invoke(null, null)!;
            host.Record("framework:own-reflection:" + value + ":allowed");
            return;
        }
        s_initCount++;
        s_instance = new FrameworkInstance("fw-" + Guid.NewGuid().ToString("N"));
        host.Record("framework:init:" + mode + ":count=" + s_initCount + ":token=" + s_instance.Token);
        if (mode == "throw-init")
        {
            throw new FrameworkInitException();
        }
    }

    /// <summary>Reports framework identity and current counters for the calling author tag.</summary>
    public static string Describe(string caller)
    {
        ArgumentNullException.ThrowIfNull(caller);
        return "framework:describe:caller=" + caller
               + ":count=" + s_initCount
               + ":token=" + s_instance.Token
               + ":calls=" + s_callCount;
    }

    /// <summary>Touches shared framework state and returns the running call count.</summary>
    public static int Touch(string caller)
    {
        ArgumentNullException.ThrowIfNull(caller);
        s_callCount++;
        return s_callCount;
    }

    /// <summary>Adds an author callback to the framework-owned static event.</summary>
    public static void SubscribeFrameworkEvent(Action callback)
    {
        ArgumentNullException.ThrowIfNull(callback);
        s_frameworkEvent += callback;
    }

    /// <summary>Removes an author callback from the framework-owned static event.</summary>
    public static void UnsubscribeFrameworkEvent(Action callback)
    {
        ArgumentNullException.ThrowIfNull(callback);
        s_frameworkEvent -= callback;
    }

    /// <summary>Invokes every callback currently held by the framework static event.</summary>
    public static int RaiseFrameworkEvent()
    {
        Action? handlers = s_frameworkEvent;
        handlers?.Invoke();
        return handlers?.GetInvocationList().Length ?? 0;
    }

    /// <summary>
    /// Trusted-framework native bridge probe. This wrapper lives in the ordinary trusted framework
    /// assembly (not in an author assembly): the author reaches native code only through this
    /// framework API, so using it from an author fixture is a positive trusted-native bridge probe
    /// subject to the host's explicit API allow policy. Windows-guarded; other platforms throw
    /// PlatformNotSupportedException instead of loading native code.
    /// </summary>
    public static int NativeThreadProbe()
    {
#if GROUPED_HOST_PORTABLE_FRAMEWORK
        throw new PlatformNotSupportedException("framework-native-probe-unavailable-in-portable-diagnostic-fixture");
#else
        if (!OperatingSystem.IsWindows())
        {
            throw new PlatformNotSupportedException("native-thread-probe-is-windows-only");
        }
        return NativeThreadId.GetCurrentThreadId();
#endif
    }

    private static int PrivateFrameworkMarker() => 7001;

#if !GROUPED_HOST_PORTABLE_FRAMEWORK
    private static class NativeThreadId
    {
        [DllImport("kernel32.dll")]
        internal static extern int GetCurrentThreadId();
    }
#endif
}
