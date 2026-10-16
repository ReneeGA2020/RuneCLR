# Host-pumped sessions

`MapRunner.Start(package, options)` creates a collectible session, constructs the
script and calls `OnStart` before returning a `MapSession`. The game host then
chooses when to call `Tick` and when to call `Stop`. There is no wall-clock timer, sleep,
wall-clock deadline or imposed frame cadence inside the session.

```csharp
var runner = new MapRunner();
using var session = runner.Start(package, options);

// In the authoritative host's frame loop, while this session is active:
if (session.IsRunning)
{
    session.Tick(hostFrameDelta);
}

// When the host retires this session:
MapRunResult result = session.Stop();
```

The `using` scope in this sketch spans the session's lifetime; it must not be
created and disposed afresh each frame. Store the session in a host-owned
container and stop it when that container is retired. Callbacks are synchronous.
Lifecycle calls are serialized, and reentrant calls are rejected. Keep scheduling
under the owning game loop's control. The
prototype does not support author-created threads, background tasks, timers or
asynchronous callbacks. That remains an API convention rather than an enforced
prohibition.

## Lifecycle and results

- `IsRunning` reports whether further author callbacks can run.
- `CompletedTicks` counts successful `OnTick` callbacks, starting at zero.
- `Tick()` supplies `options.TickDuration`; `Tick(delta)` supplies the host's
  positive delta. Tick indices start at zero. A tick returns `true` when its
  callback succeeds. Calling `Tick` after closure throws `InvalidOperationException`;
  an invalid delta throws before invoking author code.
- Manual sessions do not stop at `options.TickCount`. The host owns their
  lifetime. `MapRunner.Run` retains its finite `TickCount` behavior.
- Author failure closes the session and records a failed result. `Result` is
  absent while a session runs and available after it closes.
  A failed `Tick` returns `false`; failed construction or `OnStart` returns an
  already stopped session from `Start`, with the failure in `Result`.
- `Stop()` closes the session and returns its `MapRunResult`. Repeated calls
  return the same result. `Dispose()` also stops it.

The owner must stop or dispose every session. There is no finalizer that invokes
author cleanup. Configuration or package-admission errors can still throw from
`Start` before a session is returned.

Ordinary callback failure still attempts `OnStop` when an instance exists;
native terminal-budget exhaustion skips further author execution. Host entity
cleanup and collectible-context unloading happen independently of successful
author cleanup. Completed results contain host-owned strings, counters and a weak
unload ticket. A closed session releases its script/context references.

Observe `result.Unload.IsCollected` after the lifecycle call stack has returned.
`Unload` initiates retirement, and a pending weak reference does not establish a
leak. If diagnostic forced GC is needed, use a separate non-inlined lifecycle
helper, as the sample does, then inspect its returned result. Do not force GC
each frame.

## Callback signal

`IMapContext.Signal` and `RaiseSignal` are available only while `OnStart`, `OnTick`, or
`OnStop` is running. Returning from that callback, including by an exception,
closes the signal and drops every subscriber. A later raise or subscription
throws `InvalidOperationException` with the message "The map signal is closed."
and does not invoke the old handler. The session does not retain the subscribers
after the callback. This desktop host contract is not part of the restricted
`managed-il-gameplay-v1` profile, which still denies delegate-based work.

## Tick schedule

`Schedule(dueInTicks, value)` stores one primitive while a callback is running.
`dueInTicks` is at least 1. From OnStart, 1 is ready on the first tick. During
tick 0, 1 is ready on tick 1. `TryTakeScheduled` returns a due value only during
that later tick callback, choosing the earliest due value first. It does not
call author code by itself. After the callback returns, schedule and take throw
`InvalidOperationException` ("The map schedule is closed."). `Stop` clears
anything still pending before `OnStop`. There is still no background thread,
sleep, or wall-clock timer. The restricted profile does not include this surface. A later session does not observe values cancelled by an earlier session.

## Callback resources

SpawnEntity, DestroyEntity, Log, and Charge are accepted only while OnStart,
OnTick, or OnStop is running. After that callback returns, a retained context
receives InvalidOperationException ("The map callback is closed.") and does not
add, remove, or record anything. Entities created while the callback was open
are still released by Stop, including when the script never destroys them.
Between callbacks, MapSession.CopyEntities copies the current entity ids and
names into host-owned values. Keep the returned array; a later tick does not
change it. Copying after Stop throws InvalidOperationException. Call it between
callbacks, not from inside one, because the session lock is already held there.
This is not an asynchronous resource API.

## Registered resource names

RegisterResource and ReleaseResource run only during OnStart, OnTick, or OnStop.
A blank name is rejected. A name longer than 128 characters hits the callback
limit. Registering the same ordinal name twice throws InvalidOperationException.
ReleaseResource returns false when that name is not registered. PendingResources
uses the same closed-callback rejection, "The map callback is closed."
Between callbacks, MapSession.CopyResources copies the current names into
host-owned values. Stop clears the remaining names before OnStop. Copying after
Stop throws InvalidOperationException ("The session has stopped."). A later
session does not see them. The restricted profile does not include this surface.
Desktop tests/RuneCLR.Runtime.Tests passed 48/48 in Release on 2026-10-16,
including this case and two live sessions that do not share names. There is still no background thread, sleep, or wall-clock
timer.


## Host-completed work

RequestWork asks for one named operation while a callback is running. The host
then calls CopyPendingWork, CompleteWork, or FailWork between callbacks. Both
results are ints, and FailWork does not store an exception. The script reads
them with TryTakeWork on a later callback. A retained context cannot request or
take work after the callback returns. An unknown id is rejected, and finishing
the same id twice throws. Stop drops both open requests and results the script
has not taken, before OnStop. Author failure stops the session too, so the host cannot complete or fail a request it already observed. Pending tick-schedule values are cleared at the same time. Catching a work or schedule limit does not leave the session running, and the request or signal already accepted is cleared before OnStop. A latched limit is not labeled as an OnStop failure when OnStop returns. Call the host methods between callbacks, not from
inside one. No thread, task, or wall-clock timer is started. Two live sessions do not share requests: completing one does not finish the other, and stopping one leaves the other running. After a session fails and releases its context, the next session can reuse the same work id and complete its own request.

## Budgets and execution policy

Cooperative host API quota resets for each callback; an observed violation is
latched for the session. It cannot interrupt an author loop that never returns
to the host API. The optional native `PrototypeInstructionBudget` applies
cumulatively across construction, start and all frames. Advancing a host frame
does not refill it. Native terminal recovery retains its separate cleanup
budget. See [host instruction budgets](host-instruction-budget.md).

`RequireInterpreter` still needs the matching private runtime and its native
acknowledgment. An ordinary desktop run with the installed SDK exercises host
lifecycle behavior; it does not establish interpreter execution or iOS support.
This API addition does not replace the separately recorded mobile method-entry
and real-device acceptance work.

## Sample

```powershell
dotnet run --project samples/RuneCLR.SampleHost -c Release -- --pump --collect
```

`--pump` starts a manual session, calls `Tick` at most `options.TickCount` times
and stops it. It preserves the normal report and diagnostic collection output.
Without `--pump`, the sample uses the existing `MapRunner.Run` path. A game
integration should replace this finite loop with its own authoritative frame
loop and explicitly retire sessions.

## Measured acceptance - 2026-10-15

The full private RC1 Windows verification passes a Release solution build with
zero warnings/errors, 37/37 lifecycle cases (including post-host-build IL),
84/84 packaging cases and 15/15 player cases. Both synchronous and pumped sample
paths complete three sessions, release all entities and collect all contexts.
Thirteen lifecycle groups cover host tick/delta control, startup/constructor/
tick/stop failures, caught quota violations, throwing exception-message getters,
overlapping sessions, serialized concurrent host ticks and retained stopped
session collection. The same 37/37 lifecycle suite passes with
`RequireInterpreter` on the matching private Windows Release layout; global
`InterpMode` and `RuneCLRInterpretCollectible` are both zero and native policy
version 1 is acknowledged. All 43 recorded managed/runtime input hashes remain
unchanged. These are Windows functional results, not fresh author-method native
entry samples or mobile acceptance of this new host API.

The private native-budget layout is the preserved
`20405f7ae23e183e038703aa5e356b3310fef427` Release candidate on upstream
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`; no runtime source changed here.
The opt-in `eng/verify-host-budget.ps1 -Pumped` suite passes 16 cases and 74
collections, alongside the unchanged default 15-case/73-collection suite.
A finite 64-iteration-per-tick workload returns successfully to the host six
times; its seventh tick terminates at exactly 8192 cumulative dispatches. It
skips `OnStop`, releases its entity and collects even with the stopped session
object retained. Finite/infinite cleanup, constructor exhaustion, attempted
catch/resume, malicious exception messages and twenty failure/recovery pairs
also pass. The ordinary SDK pumped control adds twenty collections and rejects
the missing native capability before accessing the absent author file.

Evidence under `artifacts/host-pumped-session/`:

- `20261015-host-verification-attempt1/verify.log`: complete build/host suites.
- `required-lifecycle-20261015-attempt1/`: required-policy invocation, streams
  and before/after hashes.
- `windows-budget-20261015-attempt2/`: pumped native suite and exact source,
  runtime provenance, process and scalar receipts.
- `windows-legacy-budget-20261015-attempt1/`: synchronous native regression.
- `windows-stock-control-20261015-attempt1/`: ordinary SDK controls.
- `20261015-host-verification-attempt1/root-review.json`: independent source,
  native runtime, receipt/stream/process hash and ledger review; 167 probe
  collections in total. Stock runtime provenance is not claimed.

Native attempt 1 is preserved as a failed probe: it initially expected a
stopped `Tick` to return false. The documented API rejects it with
`InvalidOperationException`; correcting the probe produced attempt 2.

The [controlled-package pumped integration](package-execution-tests.md) now
passes 22/22 on Windows ordinary and required-interpreter lanes, alongside the
15/15 synchronous controls. Frame deltas, failures, private versions and
pre-start package revalidation are covered. Those player cases are unbudgeted.
The later [controlled-package native-budget combination](controlled-package-native-budget.md)
now passes 33/33 Windows cases, adding twenty-five native-budget sessions and
exact execution/cleanup ledgers to the original twenty-two groups. All contexts
collect with stopped sessions retained, including constructor exhaustion,
attempted catch/resume, private finally helpers and bad/good recovery.

The portable mobile budget adapter now accepts an optional fifth `--pumped`
argument. Its missing observer source dependency is fixed. Local Windows
smoke on the matching Release layout passes default 15 cases/73 collections
and pumped 16/74, with two argument-rejection controls. This adapter result
(`artifacts/host-pumped-packages/mobile-adapter-20261015-attempt1/results.json`)
is a Windows smoke result. The later
[actual iOS simulator application](ios-pumped-budget-acceptance.md) now passes
16/74 with the updated trusted host and author IL compiled after installation.
All seventy-four scalar ledgers and context collections pass independent
downloaded-evidence review; the owned simulator is deleted. This raw diagnostic
fixture adds no controlled-package mobile or physical-device acceptance. Old
mobile input preparers/controllers remain frozen at their original 15/73
contracts.

Next host work is a game-facing event or wall-clock timer, mobile execution of the
controlled-package combination, and physical-device acceptance.
