# Batching Versus The Best Exact Configuration

On 2026-10-14, a fresh same-binary experiment closes the missing derived-ledger
ON control from [the first batching measurement](budget-interval-performance.md).
Arithmetic still benefits substantially. Entity updates regress more than the
independent-counter comparison suggested; frequent host-call gains are small.
The exact configuration remains the default. N100 stays an opt-in experiment,
and these measurements do not justify preferring N1000.

## Actual Callback Results

Times are warmed callback medians in milliseconds. Exact-before and exact-after
both set RuneCLRBatchInterval=0 and RuneCLRDerivedLedger=1. Batching sets
interval100/1000 and DerivedLedger=0. All set PhaseAcquireLoad=1 and use the
identical private Release binary, host and author IL.

| Workload | Exact before / after | N100 | N1000 | Batch change versus both exact brackets |
| --- | ---: | ---: | ---: | --- |
| Flat arithmetic | 35.0361 / 34.8571 | 19.5920 | 19.4829 | 43.8-44.4% less time |
| Entity updates | 72.6637 / 72.0621 | 84.1811 | 83.3839 | 14.8-16.8% more time |
| Frequent host APIs | 4.7364 / 4.7119 | 4.6354 | 4.6117 | 1.6-2.6% less time |

Configured/no-config callback ratios are respectively 2.28x/2.37x for arithmetic
exact brackets, 1.31x for N100 and 1.32x for N1000. The latter ratio uses a
slightly different no-config denominator; it does not contradict its lower
configured absolute median. Entity ratios are 2.46x/2.49x exact, 2.77x N100 and
2.86x N1000. Host-API ratios are 2.42x exact, 2.38x N100 and 2.25x N1000.
Absolute configured time and exact brackets are the direct comparison.

N1000 saves only 0.56% arithmetic, 0.95% entities and 0.51% host-API configured
callback time relative to N100 in this run. Two fresh processes per cell and
18 pooled samples do not establish confidence for these small differences.
They do not establish a benefit sufficient to relax the experimental
single-worker worst-case excess from 99 to 999 admitted dispatches.

Fresh-session medians include load, three ticks, cleanup and unload request;
diagnostic collection remains outside timing:

| Workload | Exact before / after ms | N100 ms | N1000 ms |
| --- | ---: | ---: | ---: |
| Arithmetic | 105.8194 / 105.7169 | 60.0526 | 59.9586 |
| Entity updates | 214.9759 / 221.1453 | 254.5577 | 252.2203 |
| Host APIs | 15.1881 / 15.1509 | 14.8629 | 14.7894 |

Exact callback before/after drift is -0.51%, -0.83% and -0.52% respectively.
Session drift is -0.10%, +2.87% and -0.24%. Arithmetic saves about43% session
time, entities regress14-18%, and host-API differences remain about2%.
Calls, memory operations and other required settlement boundaries can shorten
batches; larger configured intervals cannot remove those boundaries.

## Actual Verification

The [fresh smoke run](../artifacts/budget-batching/best-exact-smoke-20261014-attempt1/results.json)
passes 12 processes, 84 collections and six corruption controls. The
[actual timed run](../artifacts/budget-batching/best-exact-performance-20261014-attempt1/results.json)
passes 48 processes and 624 collected contexts, with three warmups and nine
measured samples per process. Four profiles run in order: exact-before, N100,
N1000, exact-after. Each workload/profile alternates no-config/high-budget and
high-budget/no-config in two fresh process pairs.

The [independent raw review](../artifacts/budget-batching/best-exact-independent-review-20261014-attempt1/results.json)
passes 1008 sample checks and recomputes all medians, ratios and bracket changes
from actual stdout. It checks exact launch arguments/settings, PID/nonce,
selected interpreted entries, checksums, completed native ledgers, resource
release, static reset and collection. Six corruptions cover derived/interval
settings, collection, checksum, ledger and interpreted-entry claims.

Source review confirms that exact execution and getter use derived accounting
only when the native meter's derived flag is enabled and interval is zero.
Batch execution retains the independent saturated admitted counter even if
that flag were enabled, so excess work cannot be hidden by derived accounting.
These normal high-budget runs do not enter terminated cleanup phase; all
cleanup ledgers remain 0 executed /4096 remaining. They supplement the earlier
boundary and actual cadence tests rather than replacing them.

Runtime commit/tree, matching Release layout, source hashes, affinity mask4,
Windows i7-10700K machine, and workload IL remain the same as
[the first experiment](budget-interval-performance.md). There are no concurrent
builds, debugger captures or source audits during timing. No-config retains
instrumentation and owner lookup; these ratios are configured-meter overhead,
not full instrumentation overhead. Mobile performance remains unmeasured.

The new [driver](../eng/benchmark-batch-best-exact.py) reuses the frozen fixture
contract from the original driver while checking its distinct derived/interval
settings first. It leaves the first experiment's driver, inputs and receipts
unchanged. Source, native, CoreLib and managed identities are checked before
and after timing; boundary evidence must bind the same products.

## Reproduction

~~~powershell
py -3 -B eng/benchmark-batch-best-exact.py run --build artifacts/budget-batching/windows-release-build-20261014-attempt1 --boundary artifacts/budget-batching/boundary-run-20261014-attempt1/results.json --output <fresh-output>
py -3 -B eng/benchmark-batch-best-exact.py review --build artifacts/budget-batching/windows-release-build-20261014-attempt1 --output <same-output>
~~~
