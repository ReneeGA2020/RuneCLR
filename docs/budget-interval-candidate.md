# Budget Interval Candidate

On 2026-10-14, the requested 1/100/1000 experiment becomes a real independent
runtime candidate. Its private matching Windows x64 Release build passes with
zero warnings/errors. Actual interpreter boundary and completed-work controls
also pass. Earlier per-opcode optimization ratios are separate measurements.
The [actual three-workload timing](budget-interval-performance.md) now passes:
60 processes and 780 collections. Arithmetic improves markedly; entities
regress slightly and host calls improve modestly against its Exact0 control.

## Actual Implementation

Runtime commitd0da7dfafc0c4894ae7aa5332ee171f023a0a88e is a direct child of
29ff781e157be82ba5a398a60bb05291e4a865af, at tree
adb0be61097c9514a2d4a817d93125666ed7c03e. Four changed files introduce the
default-OFF RuneCLRBatchInterval switch, an immutable interval at meter offset64,
a72-byte/align8 meter, stack-local pending state and the dispatch integration.
The accepted parent and all its earlier products are retained.

Interval0 preserves exact admission. Values1/100/1000 collect admitted pure
scalar/branch instructions locally and settle at the configured cadence.
Calls, returns, potentially throwing/memory/allocating instructions, owner/frame
changes and actual GC/abort safepoint traps settle pending counts first. Forty-seven
handlers are reviewed as safe; no-trap loop safepoints can continue a batch.
Cleanup keeps its existing per-opcode allowance. The independent executed
counter records admitted work, including any excess; remaining clamps at zero.
Mixed exact/batched counter updates saturate rather than overflow INT64_MAX.

This experimental single-worker design can delay terminal rejection by at most
N-1 admitted dispatches. It permits up to99/999 excess dispatches at100/1000;
pending counts are not yet visible in public getters until settlement. Shared
workers do not inherit that global bound. The production bridge does not gain
a new precision guarantee from this experiment.

CoreCLR DWORD environment switches parse hexadecimal: numeric interval
0/1/100/1000 uses values0/1/64/3e8. Passing decimal strings100/1000 would select
unsupported256/4096 and normalize to0. New runners encode the values explicitly.

## Verification Already Run

The [actual MSVC native-header test](../artifacts/budget-batching/native-header-20261014-attempt2/results.json)
passes35 cases/10017 checks. It observes chunks100,100,7 and1000,1000,7;
partial/owner/unwind settlement, termination/cleanup and saturation controls pass.
These execute the candidate headers, not an interpreter application.
The [independent final patch review](../artifacts/budget-batching/check-interval-patch-review-20261014-attempt2/results.json)
passes after correcting a mixed-counter saturation race. Source preparation
also rejects19 alterations and copies32965 verified private SDK files.

The new scalar [author](../benchmarks/RuneCLR.BatchKernel/Kernel.cs) computes
inside its loop; a per-iteration helper call would settle every short fragment
and prevent a real100/1000 cadence. The new
[host](../benchmarks/RuneCLR.BatchOverhead/Program.cs) and author build with
zero warnings/errors. A [functional calibration](../artifacts/budget-batching/benchmark-inputs-20261014-attempt1/baseline-smoke.json)
on the accepted parent passes checksum12749776, callback2100016 dispatches,
session6300101 dispatches and seven collected contexts. Its incidental timer
values do not establish interval performance.

The [boundary fixtures](../artifacts/budget-batching/boundary-inputs-20261014-attempt4/results.json)
build with zero warnings/errors and21 frozen inputs. Their old-parent fixture
control passes35 collections and ordinary/partial/termination/recovery checks;
nine altered receipts reject. This confirms the fixture can observe local loop
progress from a finite finally. It does not establish the new candidate's bounds.

## Actual Interpreter Controls

The [matching build result](../artifacts/budget-batching/windows-release-build-20261014-attempt1/build-result.json)
passes with 37 patch sources, seven compiled owners, eight critical products
and 527 matching private-layout files; Release /O2 and FEATURE_INTERPRETER=1
are checked. The build process has exited.

The [actual small-budget run](../artifacts/budget-batching/boundary-run-20261014-attempt1/results.json)
passes five processes, 168 collections and 20 corruption controls. It compares
1/N-1/N/N+1 allowances, normal return, ordinary throw, finite finally progress,
sticky termination with catch suppression and fresh recovery in the same process.
Completed partial counts agree with N=1. In these particular small-limit loops,
observed terminal excess is 0-4 admitted dispatches. That observation does not
replace the candidate's general single-worker bound of N-1.

The [high-budget smoke run](../artifacts/budget-batching/benchmark-smoke-20261014-attempt1/results.json)
and its independent raw review pass 12 processes and 84 collected contexts:
exact0 and intervals 1/100/1000 across arithmetic, entity updates and host APIs.
All completed native counts, checksums, static reset and resource releases agree.
Its incidental timer values are not the performance experiment.

## Actual Cadence And Performance

The matching full Release build uses the upstream build tools and independent
private outputs. [Its request](../artifacts/budget-batching/windows-release-build-20261014-attempt1/request.json)
records build.cmd PID44096 and the exact source/SDK/configuration. Raw stdout
and stderr remain beside it; no performance timing runs concurrently.

The [actual N100 capture](../artifacts/budget-batching/windows-cadence-N100-20261014-attempt2/results.json)
and [N1000 capture](../artifacts/budget-batching/windows-cadence-N1000-20261014-attempt1/results.json)
both pass, including separate raw review. Actual RecordBatch arguments are
100/100 and 1000/1000 respectively, with partial settlements 14/14 in each.
The native meter at offset64 holds the actual numeric interval. All sampled
call stacks include InterpExecMethod; matching native/PDB/source identities
bind entry RVA0x19fce0. Four samples per process avoid a full opcode trace.
Both complete with seven collections, correct checksum and completed ledger.
All six owned debugger/target PIDs have exited. Debugger Stopwatch fields are
ignored. The first N100 attempt's module-marker newline fails automatic review
and remains preserved; its corrected fresh attempt passes.

The [performance driver](../eng/benchmark-batch-interval.py) uses the same
new binary for exact0, interval1 before/after,100 and1000. It reuses unchanged
entity/host-API author IL and the new flat scalar loop. Two alternating
no-config/high-budget pairs with nine measured samples per process give60
processes and780 expected collections. It checks exact completed ledgers,
checksums, resources, source/native/managed identities and raw launches, and
recomputes callback/session medians and ratios. Boundary acceptance must bind
the same source, dotnet, native and CoreLib identities before timing starts.
The actual run and independent raw review are recorded in
[the measured results](budget-interval-performance.md). Exact0 here disables
the separate derived-ledger optimization. The later
[best-exact control](budget-batch-best-exact.md) now passes 48 processes and624
collections: arithmetic saves44%, entities regress15-17%, and host-call gains
are about2%. Exact remains the default; N100 is an opt-in experiment.
No-config retains runtime instrumentation;
these are incremental configured
meter costs on one desktop, not device or full instrumentation-off results.

The later [mobile source preparation](mobile-batch-build-preparation.md) now
composes the same batch implementation with CIDv2 and passes source/Git/bundle
checks. Both matching Release core builds now pass. The
[mobile build and application evidence](mobile-batch-builds.md) includes the
debugger-free iOS simulator and Android emulator five-lane runs, each with
168 completed collections. A separate iOS capture also samples the four
direct author interpreter entries with 35 further collections. Android method
entries, mobile full/partial settlement cadence and performance measurements
remain outstanding; simulator/emulator results do not establish physical-device
support.
