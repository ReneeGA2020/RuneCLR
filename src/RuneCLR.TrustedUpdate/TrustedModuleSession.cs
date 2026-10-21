using System;

namespace RuneCLR.TrustedUpdate;

/// <summary>
/// Result of one synchronous typed-module call. The result retains only a
/// failure code and a primitive value; it does not retain the module, callback,
/// exception, or metadata.
/// </summary>
public readonly record struct TrustedModuleCallResult(TrustedModuleCallFailure Failure, int Value)
{
    public bool Succeeded => Failure == TrustedModuleCallFailure.None;
}

public enum TrustedModuleCallFailure
{
    None = 0,
    Closed,
    ReentrantCall,
    CallbackFailed,
}

/// <summary>
/// Host-owned synchronous lifetime for one typed trusted module. The caller
/// supplies the already loaded module and schedules calls serially. This type
/// does not load, verify, unload, or switch modules, and it is not a thread-safe
/// or asynchronous scheduler.
/// </summary>
public sealed class TrustedModuleSession<TContract> : IDisposable
    where TContract : class
{
    TContract? module;
    int depth;

    public TrustedModuleSession(TContract module)
    {
        ArgumentNullException.ThrowIfNull(module);
        this.module = module;
    }

    public bool IsClosed => module is null;

    /// <summary>
    /// Invokes the callback with the borrowed module for one synchronous call.
    /// A callback exception closes the session and returns CallbackFailed without
    /// retaining the exception. A nested call is rejected before the callback is
    /// entered. Closing during the callback does not interrupt the call already
    /// running; later calls are rejected.
    /// </summary>
    public TrustedModuleCallResult Invoke(Func<TContract, int> callback)
    {
        ArgumentNullException.ThrowIfNull(callback);
        if (module is null)
            return new TrustedModuleCallResult(TrustedModuleCallFailure.Closed, 0);
        if (depth != 0)
            return new TrustedModuleCallResult(TrustedModuleCallFailure.ReentrantCall, 0);

        var borrowed = module;
        depth++;
        try
        {
            return new TrustedModuleCallResult(TrustedModuleCallFailure.None, callback(borrowed));
        }
        catch (Exception)
        {
            Close();
            return new TrustedModuleCallResult(TrustedModuleCallFailure.CallbackFailed, 0);
        }
        finally
        {
            depth--;
        }
    }

    public void Close() => module = null;

    public void Dispose() => Close();
}