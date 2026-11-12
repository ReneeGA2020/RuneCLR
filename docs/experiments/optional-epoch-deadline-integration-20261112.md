# Optional epoch callback deadline — host integration (2026-11-12)

This branch integrates the reviewed epoch callback-deadline experiment onto the current RuneCLR
`origin/main` (cbac2a657793dca7f22b1e1feff4aab26b898b4e) and pairs it with the native runtime
publication branch `runeclr/optional-callback-epoch-integration-final-20261112` (tested code
commit e637bd791bd824b3a8118fca47073f6390bcb52a, parent `runeclr/dev` 474eb8ad). The earlier
local 7f5a0bc8 snapshot and its numbers are kept only as history.

## What is integrated

- `MapDeadlineMode` (`Clock` default, `Epoch` opt-in) plus the epoch period on `MapRunOptions`.
- `CallbackEpochTicker` (process-wide lease, one shared ticker) and `CallbackEpochDiagnostics`.
- `CallbackDeadlineBridge` gains the additive epoch factory, tick/read delegates and the capability
  check; `MapSession` leases the ticker before any author file is opened and releases it after the
  author stack has returned.
- Configuration happens on a fresh interpreter-required context before any author file is opened;
  a context that already executed is rejected (configure-before-first-execution), with no
  additional host API surface.
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
- Final host join against the delivered epoch runtime (coreclr `08e031af…`, CoreLib `30020d07…`,
  clrinterpreter `f4d5ea48…`, corerun `09017fa3…`, clrjit `4b15f3ae…`; source `e637bd79…`):
  the epoch suite passes **24 passed / 0 skipped / 0 failed**, and
  `eng/verify-epoch-integration.py` passes with **659 pinned inputs**, a **521-file** private
  layout and zero drift.
- The same layout and unchanged host binaries run the lifecycle harness **156/156** in ordinary
  mode and **156/156** with explicit `--require-interpreter`, in separate processes (host commits
  17a41fb and the reporting fix 2387d81 are in this branch's history).
- Focused upstream compatibility on that exact Release runtime: four official tests pass
  (Expected 100 / Actual 100, exit 0).
- `eng/test-epoch-integration-provenance.py`: **11 passed / 0 skipped / 0 failed** (see below).

Historical figures are kept separate: the earlier 7f5a0bc8 snapshot ran the epoch suite 24/24
with 658 pins and a 520-file layout (run13/run14); the stock-runtime run was 5 passed / 19 skipped
because no matching runtime was present; and the 2026-11-10 campaign numbers came from the
archived binaries. Those are history, not the current result.

## Tooling regressions

`eng/test-epoch-integration-provenance.py` builds throwaway Git/host/layout fixtures and drives the
real `main()` of `eng/verify-epoch-integration.py` with a fixture-only stub for the harness child;
git, digest and input-pinning code all run for real. Run from the repository root:

```sh
python3 eng/test-epoch-integration-provenance.py
```

Result for this candidate: **11 passed / 0 skipped / 0 failed**, confirmed both with the default
host root and with an explicit `--host-root`. The cases are: a dirty declared-source positive and a
clean committed-worktree positive (both also require the produced IL CoreLib to be pinned); IL
produced-file drift; a manifest change between parse and pin; a manifest change during the run; a
corrupted consumed manifest copy; runtime HEAD drift; untracked runtime-source status drift; a
relative `--source-manifest` resolved under a deliberate working directory and pinned under its
resolved key; and stdout appended after the run (stdout is not an input, so that is harmless).

The suite exposed one remaining path bug in the base verifier: the pin set still used the raw
`--source-manifest` argument, so a relative path failed the parse-to-pin equality even though the
path had already been normalised for parsing. The fix reuses that normalisation and is a single
line; absolute paths pin exactly the same set as before.

## Focused upstream regression on the frozen runtime

The final run composes a private flat Core_Root from the delivered layout (519 shared-framework
files plus ten official xunit runner files, 529 files total) without modifying any layout, binary,
host branch or SDK. Four official tests each reported **Expected 100 / Actual 100, exit 0**:
`ContextualReflection`, `CollectibleStatics`, `GenericVirtualMethod` and `InterpreterTester`. The
five runtime binaries were identical before and after the runs: coreclr `08e031af…`, clrjit
`4b15f3ae…`, clrinterpreter `f4d5ea48…`, corerun `09017fa3…`, System.Private.CoreLib `30020d07…`.
The test assemblies are the official Checked build from the 474-based test source, reused unchanged.

`InterpreterTester` is the official wrapper and sets `DOTNET_Interpreter=RunInterpreterTests`
internally. That runner configuration alone is not an independent per-method interpreted-mode
trace: the same app also exits 100 with the switch off, and `DOTNET_InterpList`/`DOTNET_InterpDump`
produced no method lines in this build. The pass is therefore compatibility evidence for the
documented configuration, not proof of interpreted method entry, and it is not an epoch timing or
overhead measurement.

The earlier `ed76bfa6` run on the 7f5a0bc8 snapshot is historical and is not reused for this
candidate; the current evidence is the exact delivered `08e031af` Release binary above.

## Runtime expectation (paired branch)

Matching runtime must provide, on `System.Runtime.Loader.AssemblyLoadContext`. The published
implementation and its limits are in
[the runtime callback-epoch document](https://github.com/ReneeGA2020/runtime/blob/runeclr/optional-callback-epoch-integration-final-20261112/docs/runeclr-callback-epoch.md);
the tested code pin is `e637bd79…` and the publication branch adds documentation only:

- `RuneCLR_GetCallbackDeadlineVersion() -> long` returning 1 (existing clock ABI);
- `RuneCLR_GetCallbackDeadlineCapabilities() -> int`: **bit0 (0x1) is the clock ABI and bit1 (0x2)
  is the epoch ABI** — hosts test `(capabilities & 2) != 0`; there is no `1 << 2` bit;
- `RuneCLR_CreateCallbackDeadlineEpoch(name, resolver, deadlineTicks, pollInterval, cleanupBudget,
  epochPeriodMicros)`;
- `RuneCLR_TickCallbackDeadlineEpoch() -> long` and `RuneCLR_ReadCallbackDeadlineEpoch() -> long`.

## Provenance

- Paired native publication branch: `runeclr/optional-callback-epoch-integration-final-20261112`
  in `ReneeGA2020/runtime`, tested code `e637bd79…`, base `runeclr/dev` `474eb8ad`. Delivery
  identity for the measured run: coreclr `08e031af…`, CoreLib `30020d07…`, clrinterpreter
  `f4d5ea48…`, corerun `09017fa3…`, clrjit `4b15f3ae…`; the delivery manifest and per-file hashes
  ship with the evidence.
- The source is the clean `e637` worktree (manifest `{head e637bd79, files {}}`). The inspected
  Release build log stamps `1ac56d5` because that build predates `e637`; `e637` consolidates
  preprocessor guards and updates comments and the test fixture, with 0 differing active Windows
  Release interpreter implementation lines. Its Windows Debug compile is separate; Checked backend
  selection has source proof only. The documentation commit on the publication branch is not a
  new build.
- The earlier 7f5a0bc8 frozen set (coreclr `ed76bfa6…`, CoreLib `6f181812…`, clrinterpreter
  `905bb9bb…`, corerun `24ffba3e…`, clrjit `23e3411d…`) and its run13/run14 numbers are
  historical.

## Limits

- One active callback per session and a single owner thread; a competing callback or thread fails
  closed with reason 4.
- Windows x64 Release interpreter only. No Linux, Wasm, device, AOT, unmanaged-entry, global
  all-load or JIT/R2R instrumentation evidence; the Debug configuration is proven to compile, not
  to execute this backend.
- Native blocking cannot be interrupted, including a `Sleep` inside a finally block; finalizers run
  outside the deadline. This is a fail-closed budget, not a sandbox.
- The minimal epoch runtime has no instruction quota or terminal bridge; the both-feature case is
  only validated at its pre-author missing-capability check.
- The host must keep the ticker alive and dispose it from an ordinary thread; the trusted tick/read
  calls are assumed non-blocking and the final join has no timeout.
- `InstallTestTimerFault` is an internal test hook compiled into the experiment assembly, not a
  product API.

## Performance (measured scope, not a CPU gate)

All figures are one machine, Windows x64 Release interpreter, one driver image, 7 timed samples per
round and no CPU pinning; they are medians in milliseconds unless stated.

- Default OFF (patched but unconfigured) versus the unpatched `474eb8ad` runtime, final three-round
  confirmation: **1.03 / 1.11 / 0.97** for TightLoop / CallBoundary / BusinessLoop. An earlier
  six-round window on the `1ac` revision measured 0.96 / 1.04 / 0.95; that window is history. The
  arithmetic lanes return to baseline and the call lane recovers to about 1.04-1.11x, so no
  universal "zero overhead" or speedup claim is made.
- Epoch ON against the same build's OFF lanes in three micro lanes at intervals 1 / 100 / 1000:
  about **3.4x to 5.3x**. The 2x budget tolerance is a granularity choice, not a CPU acceptance
  threshold; these ratios are workload-specific.
- Cross-module delegate calls (300k calls per sample, callee in a second interpreter-required ALC)
  were measured with a corrected artifact-only driver (`a49635576a84…`) in three interleaved rounds
  only. The native headline used the **minimum of the three round minima: 13.9 ms cross-module
  versus 13.9 ms baseline**. The lead-normalised receipt over the same logs gives baseline 14.6 vs
  final 14.3 ms as the median of per-round min-of-7 values, and 16.8 vs 14.6 ms as the median of
  the sample medians. The minimum is not a median, and none of these figures is a noiseless
  speedup claim.
- The first cross-module attempt failed with a driver NullReferenceException (the artifact driver
  lacked a helper that only the native test assembly had); only the driver was fixed
  (`a49635576a84…`). Runtime source, HEAD and the delivery were untouched, and the blocked attempt
  is not counted as a measurement.
