# Windows Release terminal budget: trusted joined workers

On 2026-10-14, the unchanged private099dacd Windows x64 Release runtime
passed 36 owned subprocess lanes: six finite-work cases, two worker counts
(2 and 4), and three repetitions. Every process exited zero before the
100-second watchdog; all 72 collectible contexts were observed collected
after host/author execution frames returned. Ten in-memory corruption controls
were rejected. This adds a controlled concurrent-ledger baseline before the
proposed TryConsume optimization; the native algorithm was not changed.

## Inputs and execution proof

The exact private runtime commit is
099dacd07d8d890822f7422f895337733457ab3c, upstream base
0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de. The tracked-clean source, actual
Release CMake configuration, native commands, matching CoreLib/compiler and
527-file layout are frozen and rechecked by
[windows-runtime-validation.py](../eng/windows-runtime-validation.py),
using the existing successful
[Release build](../artifacts/budget-overhead/windows-release-build-20261013-attempt1/build-result.json).
No installed runtime or native source was modified.

The independent [fixture](../eng/session-terminal-concurrency-probe/Host/Program.cs)
and [driver](../eng/run-terminal-concurrency.py) build fresh author/host
assemblies with the recorded private RC1 SDK. The fixed author work is a
10,000-step uint32 recurrence, with checksum4089345937. Its optional finally
calls a private non-inline finite64-step recurrence; there is no infinite
author loop and no author-created thread.

The host creates the workers and joins every worker. Each author method
calls a trusted gate; the host waits until all distinct worker threads
have actually entered the method before releasing their common gate.
This makes author calls simultaneously ready, but does not record the OS
scheduler or prove that every CAS executed under contention. The trusted
gate waits are bounded; timeout or watchdog termination is always failure.

Global InterpMode=0 and RuneCLRInterpretCollectible=0, ReadyToRun=1 and
tiering=0 are frozen with each owned PID/nonce/argument vector. The
private factory's native policy acknowledgement is1 before author loading.
Actual completed Warm and actual gated Work/WorkFinally invocations, plus
CleanupStart side effects where available, precede the Windows x64 type6
precode observations. These observations bind ModuleMVID, MethodDef token,
entry bytes and invocation evidence. They are selected post-invocation
entry observations, not preparation-only or complete child-dispatch traces.

## Measured boundaries

| Lane | Two workers | Four workers | Required outcome |
| --- | --- | --- | --- |
| Shared terminal quota | Execution2048, remaining0 | Execution2048, remaining0 | Both/all workers catch the native terminal signal in trusted host; authored completion0 |
| Finite finally | Cleanup1832, remaining6360 | Cleanup3664, remaining4528 | Every worker's finite cleanup completes, phase1 |
| Tight shared cleanup64 | Cleanup64, remaining0 | Cleanup64, remaining0 | Phase2; authored cleanup completion0; all workers still join |
| High terminal allowance10,000,000 | Execution280046, remaining9719954 | Execution560080, remaining9439920 | All return4089345937, reason0 and phase0 |
| Diagnostic limit2048 | Execution280046, remaining0 | Execution560080, remaining0 | All return despite exhausted accounting; no terminal latch |
| Required interpretation, no meter | All return4089345937 | All return4089345937 | Terminal queries reject an alive nonterminal owner |

Every terminal failure retains reason1; no worker returns successfully or
reaches the author's completion side effect. Both high-allowance and
diagnostic controls compare their post-gate dispatch totals with the same
Work method executed by a single trusted worker in the fresh recovery context:

| Quiescent interval | Single reference | Two workers | Four workers |
| --- | --- | --- | --- |
| Dispatches after common gate to joined completion | 140013 | 280026 | 560052 |
| Initial Warm plus pre-gate execution | 16 | 20 | 28 |

The joined post-gate counts equal exactly two/four times the reference.
Shared terminal execution consumes only2028/2020 dispatches after the
two/four-worker gate, respectively; the initial20/28 are included in the
same2048 allowance. Execution and cleanup counters each reconcile against
their immutable allowance after all charges finish. Snapshots are separate
scalar native reads; no two-field atomic snapshot or per-opcode transaction
is claimed.

Each process holds a separate idle good context during the concurrent run.
Exported before/after native snapshots prove that the active context does
not charge the idle owner and the later good context does not reactivate
or recharge the completed owner. The good context returns the expected
checksum and its independent static Warm state is1. All eight meter/terminal
queries reject each retired context; the explicit result records[8,8].
Only weak references and host-owned scalars survive the NoInlining frame
that owns reflection metadata, delegates, threads and contexts. Collection
is checked after that frame returns.

## Receipts and reproduction

- [Final attempt4 results](../artifacts/terminal-concurrency/windows-release-20261014-attempt4/results.json),
  SHA256 fd6a0a77c55f75fd3cd2a67bd0b297c7409a6e68d1aa07ae51b2c44856ecc117.
- [Runtime/build/layout binding](../artifacts/terminal-concurrency/windows-release-20261014-attempt4/runtime-provenance.json),
  [frozen source request](../artifacts/terminal-concurrency/windows-release-20261014-attempt4/request.json)
  and [managed image hashes](../artifacts/terminal-concurrency/windows-release-20261014-attempt4/managed-identity.json).
- Every final result binds raw stdout/stderr, process PID/nonce, settings,
  timedOut=false and exitCode0. Per-process result.json is also hashed.
- [Root independent offline audit](../artifacts/terminal-concurrency/root-review-20261014-attempt1/results.json)
  checks all 36 raw process receipts, matching stdout/stderr business rows,
  source/managed/runtime bindings, joined execution/cleanup conservation,
  owner isolation and 72 collections. A PE-only reader binds 156 selected
  entries to the real payload MVID, MethodDef token, declaring type and IL.
  Four additional ledger/owner/join corruption controls are rejected.
- Negative controls reject lost/extra execution increments, missing worker
  admission, unjoined worker, owner cross-charge, an entry without actual
  invocation evidence, terminal continuation, retained context, accepted
  retired query and a forged owner-isolation snapshot. Original evidence
  is unchanged by these in-memory mutations.

~~~powershell
py -3 -B eng/run-terminal-concurrency.py --output artifacts/terminal-concurrency/new-release-run --runtime E:/runtime-finalizer-20261013 --build-evidence artifacts/budget-overhead/windows-release-build-20261013-attempt1 --repeats 3
py -3 -B eng/audit-terminal-concurrency.py --evidence artifacts/terminal-concurrency/new-release-run --output artifacts/terminal-concurrency/new-release-review
~~~

The preserved [attempt1 build failure](../artifacts/terminal-concurrency/windows-release-20261014-attempt1/failure.json)
was CS8629 in the new fixture's nullable Snapshot access; no author execution
occurred. [Attempt2](../artifacts/terminal-concurrency/windows-release-20261014-attempt2/failure.json)
omitted Instance in reflection lookup, so private instance getters were
not found before author loading. Both are fixture errors, not runtime
defects. [Attempt3](../artifacts/terminal-concurrency/windows-release-20261014-attempt3/results.json)
passed the initial twelve-lane matrix; attempt4 adds explicit retirement
receipts, owner snapshots and three repetitions with fresh builds/processes.

This baseline does not authorize an author thread API, demonstrate all
race schedules, prove interruption of a blocking framework/native call,
or establish mobile/physical-device behavior. Author threads, threadpool
work, unload concurrent with active frames, broader lock/finalizer races
and sustained contention stress remain separate experiments.
