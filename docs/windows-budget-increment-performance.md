# Minimal terminal-counter performance - Windows Release

On 2026-10-14, a sequential baseline/candidate/baseline experiment measures
the minimal terminal-counter increment on the same i7-10700K Windows x64
machine. The budgeted arithmetic callback median falls from75.679/76.880ms
in the two099 baseline runs to64.534ms in20405f7: 14.73-16.06% less elapsed
time in this fixture. This is one controlled kernel, not a mobile or game-frame
performance claim. The new configured-meter lane still costs4.68x its own
no-config callback median.

## Inputs and measurement boundary

- Baseline runtime: `099dacd07d8d890822f7422f895337733457ab3c`; private
  `E:/runtime-finalizer-20261013` matching Release layout.
- Candidate: `20405f7ae23e183e038703aa5e356b3310fef427`; private
  `E:/runtime-increment-20261014` matching Release layout.
- Upstream base: `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`.
- Both builds retain matching source/native/CoreLib/compiler/layout provenance.
  Candidate source is exactly the single-parent, single-header
  [minimal increment](windows-budget-increment-hotpath.md).
- All host, author, driver and full managed-image inventories are identical
  across the three measurements. Author DLL SHA256 is
  `74504451a283fa9995f4762429538ec0ed44787c43c2621bfd2182e3b93f3bb8`.
- All processes pin logical CPU2, mask4. Each run has four alternating
  no-config/high-budget pairs, eight fresh processes, three warmups and nine
  timed callbacks plus nine timed fresh three-tick sessions per lane process.

All functional/native builds and subagent CPU work finished before measurement;
the three measurements ran sequentially, with independent audits afterwards.
The OS, CPU clocks/thermals and unrelated machine activity are not isolated.
This brackets observed drift without supplying a confidence interval or a
cross-runtime randomized trial. Earlier2026-10-13 timings remain separate.

No-config still pays the patched interpreter's definition-owner lookup and
null-meter checks. High-budget adds terminal accounting with execution
allowance1,000,000,000,000 and cleanup4096. This is configured-meter cost,
not instrumentation-off versus instrumentation-on. Native entry observation
and GC/validation occur outside the callback timer. The whole-session timer
also includes setup, host lifecycle/cleanup and unload request.

## Actual results

All values are pooled medians from36 measured observations per mode per run.
Raw min/max and all paired process samples remain in the original receipts.

| Run | No-config callback ms | Budgeted callback ms | Budgeted/no-config | No-config session ms | Budgeted session ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline before099 | 13.657 | 75.679 | 5.54x | 43.363 | 226.970 |
| Candidate204 | 13.796 | 64.534 | 4.68x | 40.288 | 204.107 |
| Baseline after099 | 14.821 | 76.880 | 5.19x | 41.866 | 236.575 |

Budgeted callback elapsed time decreases14.73% relative to baseline-before
and16.06% relative to baseline-after. Budgeted whole-session medians decrease
10.07% and13.72% respectively. Session timing includes host/loading costs;
neither delta attributes CPU time solely to atomics. No-config callback
medians also vary, so its fluctuations are not a demonstrated improvement.

Each callback returns checksum12749776, with zero measured-thread allocations
and zero GC-count deltas. Every budgeted callback admits2,600,016 dispatches;
each budgeted three-tick session admits7,800,101. Execution ledgers reconcile
after calls return, terminal reason stays0 and cleanup remains unused. Every
run collects104 contexts, for312 across24 processes, after frames return.
Selected post-invocation entries show interpreted author Execute/Update and
native trusted MapRunner.Run. These are selected entries, not a full trace.

## Evidence and review

Each raw review checks process/nonces, source and managed identities, matching
Release provenance, checksum, dispatch deltas, collections and independently
computed timing summaries. All12 corruption controls per run are rejected.

- [Baseline-before result](../artifacts/budget-increment/benchmark-baseline-before-20261014-attempt1/results.json)
  and [audit](../artifacts/budget-increment/benchmark-baseline-before-review-20261014-attempt1/results.json).
- [Candidate result](../artifacts/budget-increment/benchmark-candidate-20261014-attempt1/results.json)
  and [audit](../artifacts/budget-increment/benchmark-candidate-review-20261014-attempt1/results.json).
- [Baseline-after result](../artifacts/budget-increment/benchmark-baseline-after-20261014-attempt1/results.json)
  and [audit](../artifacts/budget-increment/benchmark-baseline-after-review-20261014-attempt1/results.json).
- [Cross-run identity and median comparison](../artifacts/budget-increment/bracket-review-20261014-attempt1/results.json)
  binds all three audits/results, identical sources/images and measured
  medians. Its [frozen comparison script](../artifacts/budget-increment/bracket-review-20261014-attempt1/compare.py)
  preserves the calculation.

The [machine-code audit](windows-budget-increment-hotpath.md) independently
verifies that the admitted normal path uses five locked RMWs instead of six.
[Budget acceptance](windows-budget-increment-acceptance.md) and
[concurrent/production controls](windows-budget-increment-concurrency.md) pass.
This supports keeping the narrow candidate for further platform validation;
it does not validate broader phase-load or owner-cache optimizations.

## Reproduction and next gates

Keep the original directories unchanged. Run a baseline measurement, then
the candidate, then another baseline; build and audit outside measurement.

~~~powershell
py -3 -B eng/benchmark-budget-overhead.py --configuration Release --runtime E:/runtime-finalizer-20261013 --layout artifacts/budget-overhead/windows-release-build-20261013-attempt1/layout --build-evidence artifacts/budget-overhead/windows-release-build-20261013-attempt1 --output artifacts/budget-increment/baseline-new --pairs 4 --samples 9
py -3 -B eng/benchmark-budget-overhead.py --candidate-commit 20405f7ae23e183e038703aa5e356b3310fef427 --configuration Release --runtime E:/runtime-increment-20261014 --layout artifacts/budget-increment/windows-release-build-20261014-attempt1/layout --build-evidence artifacts/budget-increment/windows-release-build-20261014-attempt1 --output artifacts/budget-increment/candidate-new --pairs 4 --samples 9
py -3 -B eng/budget-overhead-audit.py --candidate-commit 20405f7ae23e183e038703aa5e356b3310fef427 --evidence artifacts/budget-increment/candidate-new --output artifacts/budget-increment/candidate-review-new/results.json
~~~

Use the baseline SHA when auditing each baseline. Later
[matching Android/iOS builds](mobile-budget-increment-builds.md),
[Android budget/recovery acceptance](android-budget-increment-acceptance.md)
and [iOS acceptance with emitted ARM64 entry inspection](ios-budget-increment-acceptance.md)
now pass for the composed minimal increment. Mobile timing has not been
measured, and new Android method-entry samples remain outstanding.
Representative workloads and physical-device IL loading/retirement remain
required separately. The last [iOS device check](ios-device-readiness.md)
reports an unavailable tunnel; no physical-device success is claimed.
