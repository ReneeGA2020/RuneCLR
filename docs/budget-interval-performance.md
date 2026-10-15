# Actual 100/1000 Budget Measurements

On 2026-10-14, the real opt-in batching candidate was built and measured on
Windows x64. Arithmetic benefits substantially; entity updates regress slightly
and frequent host calls improve modestly. Increasing 100 to 1000 produces
little additional benefit in these workloads.
The later [best-exact comparison](budget-batch-best-exact.md) now measures the
derived-ledger ON baseline directly: arithmetic still saves about44%, entities
regress15-17%, and host-API changes shrink to about2%. The original data below
remain the independent-counter experiment.

## Results

All times are warmed callback medians in milliseconds. Each cell has two fresh
processes and 18 measured samples. Ratio means configured budget elapsed time
divided by that configuration's own no-config elapsed time; lower is better.

| Workload | Exact0 time / ratio | Every100 time / ratio | Every1000 time / ratio |
| --- | ---: | ---: | ---: |
| Flat arithmetic loop | 40.5813 / 2.53x | 19.8683 / 1.26x | 19.2515 / 1.22x |
| Entity updates | 79.5268 / 2.67x | 83.5601 / 2.77x | 84.3936 / 2.86x |
| Frequent host APIs | 5.0786 / 2.61x | 4.6939 / 2.42x | 4.6862 / 2.15x |

Relative to the same-binary Exact0 configured time, arithmetic uses 51.04%
less time with 100 and 52.56% less with 1000. Entity updates use 5.07% and
6.12% more time. Host APIs use 7.57% and 7.73% less time. Calls and memory
operations force settlement, so a configured interval does not guarantee a
full batch in those workloads.

Arithmetic's 1000 result uses 3.10% less configured callback time than 100.
The host-API difference is only 0.16%; its 1000 no-config baseline is 12.40%
slower than the 100 baseline. Therefore the 2.42x -> 2.15x ratio alone is not
evidence of additional host-API budget improvement. This experiment does not
establish statistical confidence for small differences.

Fresh-session medians include loading, three ticks, cleanup and unload request;
diagnostic collection happens outside the timed region:

| Workload | Exact0 ms | Every100 ms | Every1000 ms |
| --- | ---: | ---: | ---: |
| Arithmetic | 120.0183 | 61.6701 | 59.4967 |
| Entity updates | 240.7592 | 254.7878 | 256.6134 |
| Host APIs | 16.7231 | 15.2726 | 15.4547 |

## Controls And Scope

The [raw experiment](../artifacts/budget-batching/performance-20261014-attempt1/results.json)
passes 60 fresh processes and 780 collected contexts. Each process uses three
warmups and nine measured samples. Profiles are Exact0, N1-before, N100, N1000
and N1-after. Within each workload/configuration, no-config/high-budget order
is alternated twice. All use the same runtime and unchanged workload IL.

The [independent raw review](../artifacts/budget-batching/performance-independent-review-20261014-attempt1/results.json)
passes 1260 sample checks, re-reading actual stdout, argv, settings, PID/nonce,
checksums, native ledgers, author entries and resource-release observations.
N1 configured callback before/after drift is -0.62% arithmetic, -2.62% entities
and -0.49% host APIs. N1 itself is more expensive than Exact0: it exercises
the batch implementation while settling every instruction, and is not the
accepted exact algorithm. Comparing only against N1 would overstate the gain.

All five profiles set RuneCLRDerivedLedger=0. Exact0 is the independent-counter
exact control. This is not a comparison against the best derived-ledger exact
implementation. The later fresh same-IL, same-binary Exact0 + derived-ledger ON
comparison is now recorded in [the follow-up](budget-batch-best-exact.md);
old helper-kernel measurements are kept separate. No-config still retains instrumentation
and definition-owner lookup, so the ratios are incremental configured-meter
cost rather than full instrumentation overhead.

Source: runtime d0da7dfafc0c4894ae7aa5332ee171f023a0a88e, tree
adb0be61097c9514a2d4a817d93125666ed7c03e, based on upstream 0d73c1f2.
The [matching Release build](../artifacts/budget-batching/windows-release-build-20261014-attempt1/build-result.json)
passes with zero warnings/errors and 527 private-layout files. Host machine:
Intel i7-10700K, 8 cores/16 logical processors, Windows 11 build26300. Processes
acknowledge affinity mask4 (logical processor2); there were no concurrent
experiment builds or debuggers during timing. No installed runtime is replaced.

Actual [small-budget boundary tests](../artifacts/budget-batching/boundary-run-20261014-attempt1/results.json)
pass 168 collections, partial counts, catch suppression and same-process recovery.
Observed excess in those particular loops is 0-4 dispatches. The experimental
general single-worker bound remains N-1, allowing up to 99/999 excess dispatches;
it does not apply globally to shared workers. Mobile timing and device acceptance
are separate remaining work. See [the implementation](budget-interval-candidate.md).

After timing completed, separate native debugger captures verify actual full
100/1000 batches and partial14 settlements, numeric meter values and interpreter
caller stacks. Their 14 context collections pass and owned debug processes exit.
Debugger runs contribute no time samples to this experiment.

## Reproduction

Use the prepared private build and matching boundary receipt, with a fresh
output directory:

~~~powershell
py -3 -B eng/benchmark-batch-interval.py run --build artifacts/budget-batching/windows-release-build-20261014-attempt1 --boundary artifacts/budget-batching/boundary-run-20261014-attempt1/results.json --output <fresh-output>
py -3 -B eng/benchmark-batch-interval.py review --build artifacts/budget-batching/windows-release-build-20261014-attempt1 --output <same-output>
~~~

The driver freezes actual source/layout/managed hashes before and after the
run and rejects different boundary/native/CoreLib bindings. Numeric DWORD
intervals 0/1/100/1000 are encoded as hexadecimal environment values 0/1/64/3e8.
