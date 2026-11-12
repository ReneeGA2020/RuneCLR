# Optional epoch callback deadline — archived experiment (2026-11-12)

This branch archives the reviewed callback-deadline **epoch** experiment exactly as it was
measured on 2026-11-10. It is an archive of existing sealed experimental source, not new
development and not a merge into `main` or `runeclr/dev`.

## Parents

- host repository: `bdbc7f52` (the reviewed epoch worktree base; its published file blobs for
  `CallbackDeadlineBridge.cs`, `MapRunOptions.cs` and `MapSession.cs` are identical to the
  current `origin/main` blobs, so this diff applies on top of published content)
- runtime repository: `3126bbc9a8851a09ac6435b18a12882bad48f3ee`
  (`runeclr/mobile-batch-interval`), archived as `runeclr/callback-epoch-20261110`
  (commit `15e0a1508a46ec01537988a273f65bb41c3a1cc7`, 14 files)

## What the experiment is

A host-driven **epoch tick counter** with an optionally declared tick period, read by the
interpreter at its existing checkpoints as an alternative to reading a wall/monotonic clock.
It adds experimental, default-disabled switches; the published clock-based prototype deadline
(`PrototypeCallbackDeadline`) remains the default path.

- `CallbackEpochTicker.cs` — host ticker (1 ms spin or 10 ms high-resolution variants).
- `CallbackEpochDiagnostics.cs` — epoch query/diagnostic surface.
- `CallbackDeadlineBridge.cs`, `MapRunOptions.cs`, `MapSession.cs` — epoch mode wiring.
- `tests/EpochDeadline.Author/`, `tests/RuneCLR.EpochDeadline.Tests/` — author script and tests.
- `eng/verify-epoch-integration.py` — acceptance harness (pins inputs before/after).

## Source pins (this branch)

| file | sha256 (first 16) |
| --- | --- |
| `src/RuneCLR.Runtime/CallbackDeadlineBridge.cs` | `b929ffafbfca521b` |
| `src/RuneCLR.Runtime/MapRunOptions.cs` | `a46f92f458be5ee0` |
| `src/RuneCLR.Runtime/MapSession.cs` | `05354592fec45893` |
| `src/RuneCLR.Runtime/CallbackEpochTicker.cs` | `946823c214baf962` |
| `src/RuneCLR.Runtime/CallbackEpochDiagnostics.cs` | `6757884f5a5c3fcd` |
| `eng/verify-epoch-integration.py` | `f77dcd68cc5c387f` |

Runtime delta: 14 files, aggregate `bf1fcadaccda42f27265cc63ab019f2443617b6d7171d76da6e21cc0d2e3e016`,
source manifest `c58f4a1065af7bef588dd0bd3e360544dc04ee047a0eaaaac4bab27f81935568`.

## Measured result (campaign-6, 2026-11-10, Windows x64 Release, sealed)

Sealed run: 1382 input files pinned before launch, zero drift during the run, independent
re-audit 15/15. 15 paired replicates per kernel/poll, 7 concurrency replicates, 12 cutoffs.

- 1 ms spin ticker: p50 tick 1001.5 us (dilation 1.0015, inside the strict 5% band); epoch
  faster than clock on arithmetic 0.934/0.936 and mixed 0.878/0.893 (15/15 and 14/15 sign
  wins); process CPU is much higher (~2.8 s vs ~1.5 s).
- 10 ms high-resolution ticker: p50 ~10.51 ms (dilation 1.0507, **outside** the strict 5%
  band but inside the accepted ~2x coarse tolerance); lower CPU than clock (1.39 s vs 1.50 s
  arithmetic, 0.91 s vs 1.03 s mixed) and ~7.5%/12.3% lower wall on arithmetic/mixed;
  cutoff overshoot ~18 ms / 57 ms / 259 ms at 100 ms / 1 s / 5 s budgets.
- Clock baseline: ~6.5 ms cutoff overshoot, no ticker.
- Controls: catch/filter, constructor failure, bounded cleanup, two terminations followed by a
  good session, both ALC unload tickets collected; a frozen ticker only proves
  liveness-not-provided (the host watchdog kills the process).

## Honest gaps

- The wall-time win is not causally attributed to the clock read alone (no profile).
- A frozen ticker has no runtime-side recovery; ticker liveness is a host responsibility.
- Single machine, Windows x64 Release, 15/7 replicates; not a product acceptance.
- The binaries used for the sealed campaign were built before these commits; this branch
  archives source and does not claim the measured binaries were rebuilt from it.

## Non-claims

Not native JIT/R2R instrumentation or enforcement, not a sandbox, not mobile/AOT, not a
global interruption mechanism. Epoch ticks are advanced by the host and read at the
interpreter's existing checkpoints.

## Reproduction

1. Build: `dotnet build RuneCLR.slnx -c Release`.
2. Test: `dotnet run --project tests/RuneCLR.EpochDeadline.Tests -c Release`.
3. Acceptance: `python eng/verify-epoch-integration.py --runtime-root <Release layout> --build-rid windows.x64.Release`.
4. Runtime sources for the matching native build are on `runeclr/callback-epoch-20261110`
   (parent `3126bbc9`); the sealed measurement used those 14 files plus a private Windows
   x64 Release CoreCLR build.
