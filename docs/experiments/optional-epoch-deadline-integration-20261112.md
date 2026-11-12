# Optional epoch callback deadline — host integration (2026-11-12)

This branch integrates the reviewed 2026-11-10 epoch callback-deadline experiment onto the
current RuneCLR `origin/main` (cbac2a657793dca7f22b1e1feff4aab26b898b4e). It replaces the
archive branch `experiment/optional-epoch-deadline-20261112` (base bdbc7f52) as the host
integration line; that branch stays untouched as the sealed source snapshot.

## What is integrated

- `MapDeadlineMode` (`Clock` default, `Epoch` opt-in) plus the epoch period on `MapRunOptions`.
- `CallbackEpochTicker` (process-wide lease, single shared ticker) and
  `CallbackEpochDiagnostics`, ported unchanged from the reviewed experiment.
- `CallbackDeadlineBridge` gains the additive epoch factory, tick/read delegates and the
  capability check; `MapSession` leases the ticker before any author file is opened and releases
  it after the author stack has returned.
- Epoch tests and the acceptance script from the experiment.

The clock path is unchanged and remains the default. Epoch mode is explicit: a runtime without
the additive capability (version-1 clock ABI plus capability bit 2 plus the epoch factory/tick/
read entry points) fails before author files are opened, never silently downgrades.

## Difference from the archive snapshot

- The only source edit beyond the reviewed experiment is whitespace: the trailing blank line at
  the end of `CallbackEpochTicker.cs` (the archive has a CRLF blank line at EOF) is removed so
  this branch is `git diff --check` clean. The archive branch keeps its original bytes.
- No other behaviour changes.

## Verification status

- Stock desktop build: `dotnet build RuneCLR.slnx -c Release` — 0 warnings, 0 errors.
- Stock regression: `tests/RuneCLR.Runtime.Tests` — 156/156 passed.
- Epoch tests on stock runtime: 5 passed, 19 skipped (matching private CoreCLR/native runtime not
  present), 0 failed. Epoch enforcement is therefore **pending a matching runtime build**; the
  2026-11-10 campaign numbers come from the archived binaries and do not validate this branch.
- Native JIT/R2R remains a future direction: this work is an interpreter callback deadline.

## Runtime expectation

Matching runtime must provide, on `System.Runtime.Loader.AssemblyLoadContext`:

- `RuneCLR_GetCallbackDeadlineVersion() -> long` returning 1 (existing clock ABI);
- `RuneCLR_GetCallbackDeadlineCapabilities() -> int` with bit 2 set for epoch support;
- `RuneCLR_CreateCallbackDeadlineEpoch(name, resolver, deadlineTicks, pollInterval, cleanupBudget, epochPeriodMicros)`;
- `RuneCLR_TickCallbackDeadlineEpoch() -> long` and `RuneCLR_ReadCallbackDeadlineEpoch() -> long`.

The native side (reviewer5) owns that runtime delta; this branch is host-only.
