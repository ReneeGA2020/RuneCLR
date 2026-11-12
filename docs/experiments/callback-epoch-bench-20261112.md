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


## Snapshot provenance and scope (2026-11-12 correction)

- Base commits: bench `bdbc7f52f82eda342c43559cbeabc2ac484fe484`, runtime
  `3126bbc9a8851a09ac6435b18a12882bad48f3ee` (archived on `runeclr/callback-epoch-20261110`,
  commit `15e0a1508a46ec01537988a273f65bb41c3a1cc7`, 14 files).
- The 11 imported bench source/project files are **raw-byte identical** to the experiment worktree
  (the reviewed bench worktree at the time of archiving). This document is new in the archive step
  and has no counterpart in the source worktree.
- Runtime import: 13 of the 14 files are stored LF in the branch while the accepted source files
  are CRLF (`* text=auto`); 1 file (`src/coreclr/vm/runeclrdeadline.h`) was already LF. Raw bytes
  are identical for 1/14, text-normalized bytes for 14/14. The measured binaries were built from
  the CRLF working tree and were **not** rebuilt from these commits.
- Reproducible hash basis: per-file sha256 (above) plus the runtime delta aggregate
  `bf1fcadaccda42f27265cc63ab019f2443617b6d7171d76da6e21cc0d2e3e016` (`write-pins.py`
  `digest_set`: sha256 over `sha256(file) + "  " + absolute path`, paths sorted). The aggregate
  embeds absolute local paths and is path-dependent, not a portable identity; an earlier
  `79d75e56bc8e` figure is withdrawn as unreproducible.
- Whitespace: `git diff --check` for this branch is clean. (The sibling integration branch has two
  findings at `CallbackEpochTicker.cs:392` because it preserves the measured snapshot bytes.)
