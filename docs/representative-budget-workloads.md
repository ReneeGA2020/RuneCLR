# Representative Budget Workloads

On 2026-10-14, new Windows x64 Release functional controls extend the
[derived-ledger candidate](windows-derived-ledger-candidate.md) from an
arithmetic kernel to entity objects and the shared host API. Twelve independent
processes pass; all 60 collectible contexts retire and collect after diagnostic
GC. Exact author dispatch counts agree across the phase-load parent and the
derived-ledger child with its switch OFF and ON. The original single-sample
smoke runs establish functional acceptance. A separate measured performance
run completed on 2026-10-15 as recorded below.

## Workloads And Ownership

The new author fixture links the unchanged
[existing workload source](../benchmarks/RuneCLR.Performance.Kernels/Workloads.cs).
The trusted host links the unchanged
[benchmark adapter](../benchmarks/RuneCLR.PerformanceHost/BenchmarkMapContext.cs).
It references RuneCLR.Runtime and shares RuneCLR.Abstractions with each
collectible author context; it does not reference or preload the author project.
The author fixture is built after the host in the recorded build sequence.

Each entity callback creates 512 objects and performs 200 updates per object.
Each API callback performs 8192 Charge/SpawnEntity/DestroyEntity operations,
with a log every 64 operations. The adapter independently checks entity IDs,
releases, logs and cooperative charges. Three-tick MapRunner sessions use the
production MapContext and retain IDs across ticks. Each fresh session observes
starts=1, exact logs, zero remaining entities and matching creation/release
counts. The API session creates and releases 24576 entities and records 385 logs.

The C# host and Python reviewer use closed-form oracles rather than invoking
the author implementation to generate expected results. Direct callbacks use
fresh adapters, so API IDs restart at one. Sessions retain their MapContext
across three ticks, so API IDs accumulate across all 24576 operations.

## Exact Results

| Workload | Callback checksum | Three-tick session checksum | Callback admitted dispatches | Session admitted dispatches |
| --- | ---: | ---: | ---: | ---: |
| Entity objects | 5149080 | 15447240 | 4135081 | 12405370 |
| Host API | 33558528 | 302002176 | 229908 | 689851 |

These configured-meter counts agree in all three profiles. Each configured
callback's counter delta is stable after three warmups. The terminal ledger
satisfies executed + remaining = 1000000000000; cleanup remains 4096 with zero
cleanup dispatches, and no exhaustion or termination is latched. No-config
controls report no meter or budget snapshot.

The private Release layouts belong to parent
`a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186` and child
`29ff781e157be82ba5a398a60bb05291e4a865af`, on upstream
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. All profiles explicitly enable
RuneCLRPhaseAcquireLoad. Child profiles explicitly disable/enable
RuneCLRDerivedLedger. Global interpreter mode and collectible override are
zero, ReadyToRun is enabled and tiering disabled; the native per-context
required-interpreter bridge selects author execution. Selected post-warmup
author entry/helper observations require interpreted StubType6, while trusted
MapRunner and adapter methods are not interpreted. This is selected-entry
coverage, not a complete invocation trace.

## Verification And Receipts

The accepted [fresh run](../artifacts/representative-budget/functional-20261014-attempt3/results.json)
passes 12 processes, 60 collections and 90 altered-receipt/launch controls.
1111 bound inputs include both accepted runtime layout inventories, build
receipts, source files, linked fixtures, private SDK executable and produced
managed files. Sources and products are hash-checked before/after execution.
Both new projects build with zero warnings and zero errors.

The [functional driver](../eng/verify-representative-budget.py) binds each
profile to its exact launch executable, full arguments and switch dictionary,
and checks the saved command against its original hash and process receipt.
It recomputes checksums, exact ledgers, resource/log observations, static reset
and collections from raw output. A separate read-only review passes the same
90 controls plus 24 alternate-real-layout/wrong-switch controls.

Attempt1 contains the initial project builds. Attempt2's actual commands used
the correct profiles, but independent review found that the reviewer did not
reject relabeled runtime paths or switches. The original raw receipts and
[pre-fix reviewer](../artifacts/representative-budget/review-20261014-attempt1/verify-representative-budget-before-launch-binding.py)
are preserved. Attempt3 rebuilds and reruns with the corrected binding; it is
the accepted run. This review defect is in RuneCLR's experiment tooling.

Recheck without rebuilding or launching author code:

```powershell
py -3 -B eng/verify-representative-budget.py review --output artifacts/representative-budget/functional-20261014-attempt3
```

For a fresh functional run, choose a new output directory:

```powershell
py -3 -B eng/verify-representative-budget.py run --output artifacts/representative-budget/functional-new-attempt
```

## Measured Performance And Scope

Recorded callback durations include fresh trusted-adapter creation, author
entry/helper execution and adapter verification; they exclude ALC setup and
collection. Session durations include new MapRunner sessions, three ticks and
retirement; diagnostic collection follows outside the timed scope. The
one-sample functional controls provide no budget slowdown ratio.

On 2026-10-15, the unchanged performance driver completed a fresh preparation,
40 synthetic corruption controls and one timed run at
`D:/RuneCLR-Android/representative-budget/performance-preparation-20261015-attempt1`.
It binds 1324 inputs, including the original 1111 functional inputs and 20
unchanged managed files. All64 process lanes and832 context collections pass,
with three warmups and nine timed samples per lane:576 callback samples and
576 session samples. Each workload/profile uses four alternating
no-config/high-budget pairs. Builds, debuggers, audits and other measurements
were suspended throughout the timed bracket. No author/runtime rebuild was
performed for this measurement.

High-budget pooled sample medians in milliseconds:

| Workload / scope | Parent before | Child OFF | Child ON | Parent after | ON time reduction versus both parent endpoints |
| --- | ---: | ---: | ---: | ---: | ---: |
| Entities callback | 71.1024 | 75.8542 | 64.2689 | 71.2748 | 9.61-9.83% |
| Entities three-tick session | 214.0253 | 216.5078 | 187.9709 | 216.1424 | 12.17-13.03% |
| Host API callback | 4.5810 | 4.6123 | 4.2110 | 4.5895 | 8.08-8.25% |
| Host API three-tick session | 14.7405 | 15.2548 | 13.8296 | 14.8857 | 6.18-7.09% |

For Child ON, the no-config callback medians are18.0526ms entities and1.4373ms
host API. Configured/no-config pooled median ratios are3.560x/2.930x for
callbacks and3.392x/2.426x for sessions. No-config retains owner lookup and
the null-meter branch in the same instrumented required-interpreter runtime;
these ratios measure the incremental cost of a configured meter. The earlier
arithmetic [3.60x ratio](windows-derived-ledger-performance.md) belongs to a
different workload.

High-budget parent endpoint drift is+0.24%/+0.18% for entity/API callbacks
and+0.99%/+0.98% for sessions. No-config session drift is-3.37%/-1.43%. Child
ON entity callback process medians range61.2719-80.5669ms, with the median of
four process medians63.6914ms. The independent review retains all process
medians and32 paired ratios; pooled samples are nested within four processes
per cell and are not independent trials. Profiles are sequential time blocks,
so this run does not establish a confidence interval or real-game/device cost.

The original driver recheck passes without executing author code again.
Measurement `results.json` SHA256 is
`efd6b9a77e16980eb15c23b664d138909e363211d02993e168cbecf2a311c46b`.
The [independent raw reviewer](../eng/review-representative-budget-independent.py)
also passes64 actual launches/832 collections and recomputes both sets of576
timed samples at
`D:/RuneCLR-Android/representative-budget/performance-independent-review-20261015-attempt1/results.json`.
The final strengthened review is retained separately at
`D:/RuneCLR-Android/representative-budget/performance-independent-review-20261015-attempt2/results.json`,
with56/56 independent corruption controls and five positive controls at
`D:/RuneCLR-Android/representative-budget/performance-independent-controls-20261015-attempt1/results.json`.
The frozen final reviewer SHA256 is
`b807ad1b32855deacdfd66b18f59e0ed224ee29d9dad3c31554e7746e4379f53`.
It rebuilds expected launch arguments/settings, checks pinned runtime
commit/build/source/layout chains and hashes every original stream, all1324
bound inputs and frozen snapshots.
Child ON entity/API callbacks take15.27%/8.70% less time than Child OFF.
Its process-paired configured/no-config callback ratio medians are3.551/2.876,
with ranges3.369-4.517 and2.777-3.113 respectively. These differ from ratios of
pooled sample medians because each process pair has its own denominator.

These preserved profiles use exact per-opcode admission. The separate
[100/1000 batching experiment](budget-batching-experiment.md) has been
implemented and measured against the [best exact path](budget-batch-best-exact.md),
with [mobile batch measurements](mobile-batch-measurement.md) recorded separately.
This representative comparison measures the exact derived-ledger optimization.

The run completed once from UTC20:20:56 to20:34:36. Its supervisor, raw streams,
partial receipts, original review and `measurement-handoff.json` are retained
beneath the preparation directory. Preserve this completed measurement;
additional runs require new output directories. Mobile/physical-device
execution remains separate work, and the low-budget controls below add no
timing or mobile claims.

## Low-Budget Termination And Recovery

A separate [recovery probe](../eng/representative-budget-recovery-probe/Program.cs)
uses the unchanged frozen author DLL and production host assemblies from the
functional run. It varies the native allowance across 1, 32, 64, 128, 2048,
8192 and 100000 admitted dispatches for both entity and API workloads. Each
failed session is immediately followed by a fresh three-tick HostApiMap session
in the same process. The required native policy stays enabled for both.

The [new run](../artifacts/representative-budget/recovery-20261014-attempt1/results.json)
and raw recheck pass three parent/OFF/ON processes: 42 terminal sessions,
42 successful recoveries, all 84 contexts collected and 24 altered
receipt/launch controls rejected. The new host builds with zero warnings/errors.
Every native failure admits exactly its allowance, returns zero remaining
execution budget, latches reason1/phase1 and retains the unused4096 cleanup
reserve. No failed session completes a tick or emits its OnStop checksum log.

API failures before resource creation report zero entities. Larger allowances
observe 3, 71, 290 and 3562 entities at128/2048/8192/100000 respectively,
all released with zero remaining. Release totals include author destroy calls
and host disposal; these reports do not identify which mechanism released each
entity. Every recovery creates/releases24576 entities, records385 exact logs,
resets starts=1, returns checksum302002176 and admits689851 dispatches. All
failed/recovery reports match exactly across the three runtime profiles.

The [new driver](../eng/verify-representative-budget-recovery.py) binds the
same frozen source/runtime/build/author inputs plus the new probe, actual
launch arguments, switches, PID/nonce and raw streams. The result contains only
host-owned reports/scalars/strings and weak unload tickets. Diagnostic GC runs
after the MapRunner execution frame returns.

```powershell
py -3 -B eng/verify-representative-budget-recovery.py review --output artifacts/representative-budget/recovery-20261014-attempt1
```

This adds ordinary entity/API budget recovery coverage. The fixtures contain
no author catches, filters or finally blocks, so they add no new evidence for
those boundaries, concurrent workers, finalizers or live method entries. Those
have distinct earlier acceptance receipts. No timing or mobile claim is made.
