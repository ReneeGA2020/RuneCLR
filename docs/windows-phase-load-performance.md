# Windows phase-load performance

On 2026-10-14, the same-machine bracketed measurement runs in the order
parent-before, phase child OFF, phase child ON, parent-after. The new ON
budgeted callback median is 47.67865ms, versus 63.87670/64.46335ms for the two
parent brackets: 25.36-26.04% less elapsed time for this arithmetic kernel.
ON uses 28.66% less time than the new child's own OFF result. Budgeted
whole-session medians fall by 23.79528%/25.06481% against those parent brackets.
The parent budgeted callback median increases by 0.91841% between brackets.

The current ON configured/no-config callback ratio is 4.07x. The two current
parent brackets are 5.36x and 5.35x; the current child OFF ratio is 5.62x.
These are the ratios from this new measurement, not the earlier 4.68x
candidate run. They describe incremental configured-meter cost on an already
instrumented runtime, not all interpreter/instrumentation overhead.

## Raw measured medians

All times are milliseconds. Callback medians pool 36 non-warmup samples per
mode and run; session medians pool 36 sessions per mode and run. A session
includes three callbacks. Each run alternates four no-config/high-budget
process pairs, pins all children to logical CPU2 (mask4), and keeps three
session warmups separate from timing summaries.

| Run | No-config callback | Budgeted callback | No-config session | Budgeted session | Callback ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| Parent before | 11.92145 | 63.87670 | 36.45805 | 189.81620 | 5.35813x |
| Child OFF | 11.89440 | 66.83670 | 35.64275 | 199.78940 | 5.61917x |
| Child ON | 11.71815 | 47.67865 | 34.56645 | 144.64890 | 4.06879x |
| Parent after | 12.05485 | 64.46335 | 36.22170 | 193.03200 | 5.34750x |

The original result receipts are
[parent before](../artifacts/phase-load/performance-parent-before-20261014-attempt1/results.json),
[child OFF](../artifacts/phase-load/performance-off-20261014-attempt1/results.json),
[child ON](../artifacts/phase-load/performance-on-20261014-attempt1/results.json)
and [parent after](../artifacts/phase-load/performance-parent-after-20261014-attempt1/results.json).
Time reduction is calculated as 100*(1 - ON budgeted callback median / compared
budgeted callback median). This is a reduction in elapsed time, not an equal
percentage increase in throughput.

## Accepted evidence

The [OFF audit](../artifacts/phase-load/performance-off-review-20261014-attempt1/results.json)
and [ON audit](../artifacts/phase-load/performance-on-review-20261014-attempt1/results.json)
both pass eight actual processes, 104 context collections and 36 callback
samples per mode. Each retains the original twelve corruption controls in a
separate unchanged receipt and adds a thirteenth phase-environment substitution
control. The [new auditor](../eng/audit-phase-load-overhead.py) executes the
original raw/managed/ledger/median verifier while strictly replacing its
candidate guard with the exact phase checker.

The [parent-before audit](../artifacts/phase-load/performance-parent-before-review-20261014-attempt1/results.json)
and [parent-after audit](../artifacts/phase-load/performance-parent-after-review-20261014-attempt1/results.json)
also pass eight processes and 104 collections each, with all original twelve
corruption controls rejected per run.

The exact candidate is a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186, direct child
of parent 20405f7ae23e183e038703aa5e356b3310fef427. Both child profiles bind the
same Release source/build/layout, the complete frozen preparation and adapter,
and exact per-process environment values 0/1. The audit checks actual native
images, the complete layout inventory, managed hashes, PID/nonce/raw streams,
checksum 12749776, zero callback allocations and GC counts, actual ledgers,
all pooled/paired statistics and completed collections.

Each budgeted callback accounts for 2600016 admitted dispatches; each timed
session accounts for 7800101. There is no batching or allowance change. The
matching [functional acceptance](windows-phase-load-acceptance.md) and
[actual hot-loop witnesses](windows-phase-load-live-witness.md) establish the
tested ON/OFF behavior separately. The debugger witnesses are not timed data.
The [benchmark adapter](../eng/benchmark-phase-load-overhead.py) retains the
original arithmetic and whole-session fixtures.

The [four-run comparison](../artifacts/phase-load/performance-comparison-20261014-attempt1/results.json)
passes 32 distinct process PID/nonce pairs and 416 completed context collections.
It binds 24 identical shared source files and 20 identical managed-inventory
files across the four runs, along with machine/CPU, SDK, sample counts and run
order. Eight additional cross-run corruption controls reject changed images,
author source, CPU, sample counts, duplicate PID/nonce, collection totals and
order. The [comparison tool](../eng/compare-phase-load-overhead.py) recomputes
the ratios, time reductions and parent-bracket drift from actual raw medians.

## Interpretation limits

Child OFF is 4.63% slower than parent-before and 3.68% slower than parent-after.
The new compiled candidate introduces calls and switch selection around Phase;
OFF preserves the interlocked read but is not byte-identical to the old inlined
parent hot loop. ON/OFF measures the switch within the new binary, while the
parent brackets compare the full candidate implementation. These differences
do not isolate one instruction as the sole cause of the speed change.

The [machine-code review](windows-phase-load-hotpath.md) records the actual
locked operations, helper calls and weaker acquire ordering relative to the
old full interlocked fence. Functional and joined-worker acceptance do not
establish exhaustive races or resolve the existing phase-read/admission gap.

No 100/1000 instruction batches are implemented or measured here. This single
desktop arithmetic kernel does not establish frame/game cost, mobile/ARM64
performance, physical-device behavior, a time quota or a security sandbox.
