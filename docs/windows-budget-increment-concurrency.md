# Windows Budget Increment Concurrency And Production

On 2026-10-14, the minimal terminal counter candidate passes the Windows x64
Release joined-worker acceptance and independent raw/PE/ledger audit. This
record keeps its receipts separate from the unchanged
[099dacd concurrency baseline](windows-terminal-concurrency.md).

## Exact Inputs

- Upstream: `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`.
- Parent: `099dacd07d8d890822f7422f895337733457ab3c`.
- Candidate: `20405f7ae23e183e038703aa5e356b3310fef427`.
- Private runtime: `E:/runtime-increment-20261014`, branch
  `runeclr/terminal-counter-increment`, tracked-clean.
- Matching build/layout:
  `artifacts/budget-increment/windows-release-build-20261014-attempt1/layout`.
- Host Git HEAD: `c99c5cc7fc690b71a7db609a5598acddc390076e`; the existing
  dirty host source is bound by frozen file hashes rather than Git HEAD alone.
- Private host SDK: official `11.0.100-rc.1.26425.128`.

The direct child changes only terminal TryConsume's admitted executed increment
from the zero-CAS read/CAS loop to InterlockedIncrement64. Diagnostic accounting,
admission, cleanup allowance, terminal latch and CLR unwinding retain their
parent source. Each experiment freezes and post-checks the exact candidate,
native/CoreLib/compiler sources, compile owners and private layout hashes.

## Joined-Worker Results

Fresh Host and Payload Release builds both report zero warnings/errors. Two and
four trusted host workers run six lanes with three repetitions each: 36 owned
processes, 72 completed context collections. Every process has exit0, no
watchdog timeout, a bound PID/nonce, raw stdout/stderr hashes and an actual
per-process result. All workers join before scalar snapshots are reconciled.

| Lane | Two workers | Four workers | Result |
| --- | --- | --- | --- |
| Shared terminal allowance | Executed2048, remaining0 | Executed2048, remaining0 | Reason1; authored completion0 |
| Finite finally | Cleanup1832, remaining6360 | Cleanup3664, remaining4528 | Every finite cleanup completes; phase1 |
| Tight cleanup allowance64 | Cleanup64, remaining0 | Cleanup64, remaining0 | Authored cleanup completion0; phase2 |
| High terminal allowance10,000,000 | Executed280046, remaining9719954 | Executed560080, remaining9439920 | All return4089345937; reason0 |
| Diagnostic allowance2048 | Executed280046, remaining0 | Executed560080, remaining0 | Finite continuation without terminal latch |
| Required interpreter, no meter | All return4089345937 | All return4089345937 | No native meter ledger |

High-budget and diagnostic post-gate counts are280026/560052, exactly two/four
times the single-worker reference140013. The initial20/28 dispatches share the
same terminal2048 allowance. Every process proves idle-owner isolation, fresh
recovery static state1, unchanged finished-owner accounting, and rejection of
all eight native queries on each retired context. These values match the
099dacd baseline.

The driver rejects ten corruption controls. Independent offline review passes
all36 raw receipts, matching stdout/stderr business rows, quota conservation,
ownership and72 collections. A PE reader binds156 selected post-invocation
entries to payload MVID, MethodDef, declaring type, actual IL and saved x64
type6 precode bytes. Four additional execution/cleanup/idle-owner/join
corruption controls are rejected.

- [Concurrency results](../artifacts/budget-increment/concurrency-20261014-attempt1/results.json),
  SHA256 `f94e34f2a7b6126ce4912db3b56de15bef12b7bd8ba540a270f26e079947e24e`.
- [Runtime binding](../artifacts/budget-increment/concurrency-20261014-attempt1/runtime-provenance.json),
  SHA256 `7cbf1b4d09a2320ea84c1308dc34a9620492327daa9815da4c9c42c3ffb3cbe2`.
- [Independent concurrency audit](../artifacts/budget-increment/concurrency-review-20261014-attempt1/results.json),
  SHA256 `3e09f9cb3d442bd82511d0228ab815c6270b34207185ccf5c874892ea0613b3c`.

## Production Gate

The terminal/finalizer/host-budget suites completed before the production
build. The same candidate/layout passes 24/24 lifecycle and 15/15 package
execution cases, three sample collections, IL compiled after the host, and
controlled source/import/source sessions with static reset and collection.
The solution build reports zero warnings/errors. Four official loader tests
reuse their unchanged managed IL and original assertions from
`artifacts/session-finalizer/upstream-20261013-attempt1`; all exit100 without
skip markers.

The [production result](../artifacts/budget-increment/production-20261014-attempt1/results.json)
and [independent audit](../artifacts/budget-increment/production-review-20261014-attempt1/results.json)
pass nine functional rows, 24 original official source files and eight rejected
corruption controls. Source, managed images and matching runtime/layout bindings
remain unchanged. This is functional and policy-acknowledgement evidence;
production author methods have no individual entry observations in this run.

## Reproduction And Scope

Use fresh output directories; the recorded attempt directories must remain
unchanged.

~~~powershell
py -3 -B eng/run-terminal-concurrency.py --output artifacts/budget-increment/concurrency-new --runtime E:/runtime-increment-20261014 --build-evidence artifacts/budget-increment/windows-release-build-20261014-attempt1 --candidate-commit 20405f7ae23e183e038703aa5e356b3310fef427 --repeats 3
py -3 -B eng/audit-terminal-concurrency.py --evidence artifacts/budget-increment/concurrency-new --output artifacts/budget-increment/concurrency-review-new --candidate-commit 20405f7ae23e183e038703aa5e356b3310fef427
py -3 -B eng/verify-release-production.py --runtime E:/runtime-increment-20261014 --layout artifacts/budget-increment/windows-release-build-20261014-attempt1/layout --build-evidence artifacts/budget-increment/windows-release-build-20261014-attempt1 --upstream artifacts/session-finalizer/upstream-20261013-attempt1 --output artifacts/budget-increment/production-new --candidate-commit 20405f7ae23e183e038703aa5e356b3310fef427
py -3 -B eng/audit-release-production.py --evidence artifacts/budget-increment/production-new --output artifacts/budget-increment/production-review-new/results.json --candidate-commit 20405f7ae23e183e038703aa5e356b3310fef427
~~~

The concurrency result covers trusted joined workers and finite author
workloads. It does not trace all scheduler races, establish an author thread
API, provide a transactional native snapshot, or measure sustained contention.
The156 observations are selected invoked entries, not a complete execution
trace. Native/blocking-call duration, broader locks/unload races, mobile and
physical-device behavior remain separate. No performance measurement is
included in this record.
