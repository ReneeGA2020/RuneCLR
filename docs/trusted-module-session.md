# Trusted module session

TrustedModuleSession<TContract> is a small host-owned synchronous owner for an
already loaded trusted module. The module supplies a normal CLR game interface;
the session owns only the call lifecycle and does not load, verify, sign, stage,
or unload anything.

## Minimal game interface

    public interface IGameScoring
    {
        int AddScore(int delta);
    }

    var module = LoadGameScoringModule();
    using var session = new TrustedModuleSession<IGameScoring>(module);
    var result = session.Invoke(game => game.AddScore(5));
    if (!result.Succeeded)
    {
        // result.Failure is None, Closed, ReentrantCall, or CallbackFailed.
        // result.Value is meaningful only when Succeeded is true.
    }

The callback receives the exact typed module for that call. The public result
contains only a failure enum and an integer value; it does not retain the module,
callback, exception, reflection metadata, or delegate.

## Ownership and scheduling

- The constructor rejects a null module and does not load a module.
- Invoke borrows the module for one synchronous callback. A close during that
  callback does not interrupt the call already entered; later calls return
  Closed.
- Calls are serial. In an open session, a nested call returns ReentrantCall
  without entering the nested callback; the outer call can finish normally.
- If the outer callback closes the session before making a nested call, the
  nested call returns Closed (closed state wins); the already-entered outer call
  can still finish.
- A non-null callback that throws closes the session and returns CallbackFailed.
  No exception text or exception object is retained.
- A null callback is checked first in every state and is a host argument error
  that throws ArgumentNullException, including after close and inside a nested
  call. A nested null-callback exception propagates into the outer callback, so
  the outer Invoke returns CallbackFailed and closes the session.
- Close, Dispose, and repeated disposal are idempotent. Closing clears the
  session's module reference.
- The session is not thread-safe and has no asynchronous, event-scheduler,
  version-switching, or assembly/ALC unloading contract. The caller schedules
  calls.

## Composition with loading and recovery

Use the existing release path first: TrustedReleaseStaging and
TrustedRelease for publication and signatures, TrustedUpdateProcess and
TryStartHostLoaded for selection/load coordination, and
TrustedReleaseRecovery.TryStart for receipt-based recovery. The host supplies
the resulting typed module instance to this session. The session is not a
replacement for package verification, the loader, the process selection gate,
or recovery.

A successful stock build/run through this session does not establish R2R method
execution, interpreter fallback, arbitrary fallback, assembly unloading, CPU or
performance attribution, iOS delivery, or physical-device behavior.