# Optional epoch callback deadline — host integration (2026-11-12)

This branch integrates the reviewed 2026-11-10 epoch callback-deadline experiment onto the
current RuneCLR `origin/main` (cbac2a657793dca7f22b1e1feff4aab26b898b4e) and pairs it with the
matching native runtime branch `runeclr/optional-callback-epoch-integration-20261112`
(commit 7f5a0bc8c6d58a46d2dff91571cad04b2b3a9416, parent `runeclr/dev` 474eb8ad).

## What is integrated

- `MapDeadlineMode` (`Clock` default, `Epoch` opt-in) plus the epoch period on `MapRunOptions`.
- `CallbackEpochTicker` (process-wide lease, one shared ticker) and `CallbackEpochDiagnostics`.
- `CallbackDeadlineBridge` gains the additive epoch factory, tick/read delegates and the capability
  check; `MapSession` leases the ticker before any author file is opened and releases it after the
  author stack has returned.
- Epoch tests and the verifier under `eng/verify-epoch-integration.py`.

The clock path is unchanged and remains the default.

## Behaviour beyond the archive snapshot

This is not a whitespace-only port. Compared with the archived experiment the host now has
intentional behaviour changes:

- The callback-deadline ABI is independent of the old instruction-terminal prototype. A
  deadline-only session binds only the deadline bridge; a session with an explicit instruction
  budget still binds the terminal bridge, and both-feature sessions bind both. Previously a
  deadline session required the terminal API, which a minimal deadline-only runtime does not have.
- Termination reporting picks the mechanism that actually tripped: the deadline snapshot reason
  when a deadline budget was exceeded, otherwise the instruction-terminal state. Author failures
  still report the exception type only, and the session still fails closed.
- The ticker-fault case is a real regression (child processes for arm/wait and live-lease/last-stop)
  instead of a placeholder skip.

The archive branch keeps its original bytes and is untouched.

## Verification status (current)

- Stock desktop build `dotnet build RuneCLR.slnx -c Release`: 0 warnings, 0 errors.
- Stock regression `tests/RuneCLR.Runtime.Tests`: 156/156 passed.
- Epoch suite against the matching private runtime: **24 passed / 0 skipped / 0 failed**
  (host commits 17a41fb and the P3 reporting fix 2387d81).
- `eng/verify-epoch-integration.py`: PASS with 658 pinned inputs and a 520-file private layout
  (verifier commit 0f2f135; run evidence `run13`).

Historical figures are kept separate: the earlier stock-runtime run was 5 passed / 19 skipped
because no matching runtime was present, and the 2026-11-10 campaign numbers came from the
archived binaries. Those are history, not the current result.

## Runtime expectation (paired branch)

Matching runtime must provide, on `System.Runtime.Loader.AssemblyLoadContext`:

- `RuneCLR_GetCallbackDeadlineVersion() -> long` returning 1 (existing clock ABI);
- `RuneCLR_GetCallbackDeadlineCapabilities() -> int`: **bit0 (0x1) is the clock ABI and bit1 (0x2)
  is the epoch ABI** — hosts test `(capabilities & 2) != 0`; there is no `1 << 2` bit;
- `RuneCLR_CreateCallbackDeadlineEpoch(name, resolver, deadlineTicks, pollInterval, cleanupBudget,
  epochPeriodMicros)`;
- `RuneCLR_TickCallbackDeadlineEpoch() -> long` and `RuneCLR_ReadCallbackDeadlineEpoch() -> long`.

## Provenance

- Paired native: fork branch `runeclr/optional-callback-epoch-integration-20261112` at 7f5a0bc8,
  parent `runeclr/dev` 474eb8ad; frozen binaries used for the run: coreclr `ed76bfa6…`, CoreLib
  `6f181812…` (under IL/), clrinterpreter `905bb9bb…`, corerun `24ffba3e…`, clrjit `23e3411d…`.
- The verifier's source manifest `{head 7f5a0bc8, files {}}` records the CURRENT clean Git identity
  of that worktree. It does not prove the binaries were compiled from that clean tree: the build
  record is base 474eb8ad plus a 14-file delta with its own raw source hashes.

## Limits

- One active callback per session and a single owner thread; a competing callback or thread fails
  closed with reason 4.
- Windows x64 Release interpreter only. No device, AOT, unmanaged-entry or global all-load evidence.
- Native blocking cannot be interrupted, including a `Sleep` inside a finally block; finalizers run
  outside the deadline. This is not a sandbox.
- `InstallTestTimerFault` is an internal test hook compiled into the experiment assembly, not a
  product API. `Stop`/`Dispose` must be called from an ordinary host thread, never from the ticker
  path; the trusted tick/read calls are assumed non-blocking and the final join has no timeout.
- The both-feature case is not validated natively: the minimal epoch runtime has no
  instruction-terminal API, so only the pre-author missing-capability path is covered.

## Performance

Unresolved. The 5.33x (poll interval 1) and 3.18x (poll interval 100) figures are a historical
microbenchmark scope (arithmetic lane versus the unconfigured interpreter), not a CPU gate and not
an acceptance for the roughly 2x budget tolerance. Conflicting measurements across runtime builds
mean a dedicated matched audit is still pending; no default-OFF cost conclusion is drawn here.
