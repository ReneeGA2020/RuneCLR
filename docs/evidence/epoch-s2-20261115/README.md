# Epoch S2: portable formal readings (2026-11-15)

These are allowlisted readings from the sole formal run `s2-quiet-20261115-153718`, not a new
run. The [experiment record](../../experiments/epoch-large-interval-s2-20261114.md) gives the
implementation, results, OFF regression, scoped provenance and limitations.

- [samples.csv](samples.csv): 90 readings with original integer ticks and frequency, workload
  identity, exit/timeout status and the SHA256 of the original stdout stream. Absolute local
  file paths, inherited environment and process-environment tables are excluded.
- [pairs.csv](pairs.csv): 45 pair rows, preserving all samples, arm order, sequence numbers,
  elapsed times and candidate/reference ratios.
- [summary.csv](summary.csv): nine kernel/lane summaries, five pairs each. Negative
  `paired_elapsed_change_percent` means less elapsed time; positive means more elapsed time.

Reference is REF10K `6810f142b4e98d36f0b7ab98615e2a05bfdbab3b`; candidate is S2
`64571e93fb27d7817f00786dd22d7f549ca7fa00`. These are unpublished local runtime-source pins.
Both arms share the frozen managed cohort; this is not a claim that CoreLib was rebuilt from
each candidate. Native coreclr SHA256 values are:

- reference: `089a82f0b51c4782225836717d223756f0d9002ddb8ed1faa199f154eef72794`
- candidate: `7a0423acf4347aa591b6f3b14fc5e6a99a2e6ddab3c36b7cbe5ec490dd445718`
- shared CoreLib: `10913f56bc97b61f14dc74baefb135204724d4193a4fd7b5aed61455518aa720`
- driver: `5747c1e034587f99b96c53d2f85e0e7f97790156b059c4264a783f4e618ba7e0`

The frozen 541-input digest is
`bd211afb992f3c2088b52eed9f8fe062522af949aeb12c7ae58b39808f05dea2`; preflight and batch
before/after agree. The actual controller OS exit is 0, as recorded by its launcher, with
window 2026-11-15 15:39:13–15:40:27 +08:00. All 90 child exits are 0, without timeout or drift.

Recompute elapsed milliseconds as `tick / freq * 1000`; for each kernel/lane/pair compute
`candidate_ms / reference_ms`. Report its median separately from the ratio of the two arm
medians. Percentage elapsed change is `100 * (median_paired_ratio - 1)`.
OFF is an uncharged label, not a strict null. Five pairs are exploratory, not a significance or
minimum-detectable-effect analysis. Do not normalize away the OFF regression or interpret the
result as pure helper cost. No readings were removed, including CallBoundary primary pair 4.

SHA256 of the portable extracts:

| file | SHA256 |
| --- | --- |
| samples.csv | `edbd1ab52b8d16e30bbccf6803f836adb65c23b0a0e0ebfe48623fbb20cc6c9c` |
| pairs.csv | `4c86c4443b658cf72f3dadb2e9be5f0ee058e1a005081712923cd428b189acf9` |
| summary.csv | `15196be14b83dc418e0c9aba5c51b33917202d10418258df3be36c1f965b1659` |

Source file hashes bind the extract to the full local capture, which is not uploaded here:

- receipts.json: `b8c770f05411f96e685f6c51b3dcd9ff021c4ea41c84284a4799375d384a5b48`
- batch.json: `c224d9a5146f483f1ce34ccb657001701dc595015ce79da8ce6ed3243dad3634`

Orca Worker developer-4 executed the batch; Orca Worker developer-3 independently checked the
capture, inputs, native/managed identity and counters; Orca Worker developer-5 independently
parsed all raw ticks and recomputed the statistics without importing the original analyzer.
Lead exported only the listed sample fields, rechecked 90 raw stdout hashes and all 45 pair
ratios, and published these records. The extract supports numerical recomputation; it is not
a replacement for the full local stream, launcher and runtime-binding evidence.
