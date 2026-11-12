# Callback epoch bench harness — archived experiment (2026-11-12)

Snapshot of the host-side harness that produced the sealed campaign-6 measurements
(2026-11-10). It is archived because the bench used a **different host wiring revision**
than the `experiment/optional-epoch-deadline-20261112` branch, so the two must not be
merged into a single branch.

## Parents

- base: `bdbc7f52` (same base as the epoch integration branch)
- runtime: `3126bbc9a8851a09ac6435b18a12882bad48f3ee`, archived as
  `runeclr/callback-epoch-20261110` (14-file delta)

## Contents

- `src/RuneCLR.Runtime/CallbackDeadlineBridge.cs`, `MapRunOptions.cs`, `MapSession.cs` — the
  wiring revision used by the bench runs (differs from the integration branch).
- `tests/EpochBench.Author/` — workload author script (`Workloads.cs`).
- `tests/RuneCLR.EpochBench/` — bench driver, ticker and statistics.
- `eng/verify-callback-epoch.py` — campaign driver; `--build-rid` defaults to
  `windows.x64.Release`.

## Source hashes (this branch)

| file | sha256 (first 16) |
| --- | --- |
| `src/RuneCLR.Runtime/CallbackDeadlineBridge.cs` | `65a703c8a67c6094` |
| `src/RuneCLR.Runtime/MapRunOptions.cs` | `0bf3e791b126d46f` |
| `src/RuneCLR.Runtime/MapSession.cs` | `e1be5bbe0416dfff` |
| `tests/EpochBench.Author/Workloads.cs` | `339ed46400fbfdc2` |
| `tests/RuneCLR.EpochBench/Program.cs` | `c6ba325d825175e8` |
| `tests/RuneCLR.EpochBench/Ticker.cs` | `f35c9be18b203482` |
| `eng/verify-callback-epoch.py` | `3862a7b7e7a781b7` |

The campaign input seal and per-lane receipts stay outside the repository; the reviewed
summary reports 1382 pinned input files, zero drift during the run, and 15/15 independent
re-audit checks.

## Honest limits

- Source-only archive; the measured binaries were built before this commit.
- 10 ms high-resolution lane is outside the strict 5% tick-dilation band (1.0507) and is
  reported only under the accepted ~2x coarse tolerance; the 1 ms spin lane is inside it.
- No causal attribution of the wall-time win to the clock read; frozen-ticker liveness is a
  host watchdog concern, not runtime recovery.

## Reproduction

1. `dotnet build RuneCLR.slnx -c Release`
2. `python eng/verify-callback-epoch.py --runtime-root <coreclr root> --build-rid windows.x64.Release`
3. Compare against `runeclr/callback-epoch-20261110` runtime sources (parent `3126bbc9`).
