# Independent Android Release functional acceptance

The private Release candidate is source commit
`1724cdec553a7aff7a373a271a4be612651c7625`, with the matching Android x64
CoreLib, interpreter and JIT frozen in the
[Release layout](android-session-policy-release-layout.md). This lane checks
session behavior in a fresh process without opting into the native entry gate
or starting a debugger. It does not replace native method-entry evidence.

The [driver](../eng/android-session-policy-release-accept.py) retains the
existing Checked bytecode gate in the older driver unchanged. The new run uses
the immutable APK, player, producer receipts and golden values from
`artifacts/android-session-policy/20261013-release-entry-apk-attempt1`, rather
than rebuilt production bin directories. Its post-install payload production
timestamps and 43 input hashes are checked before any device command.

Run once on the explicitly owned, already installed API 35 x64 AVD:

```powershell
py -3 -B eng/android-session-policy-release-accept.py run `
  --evidence artifacts/android-session-policy/20261013-release-entry-apk-attempt1 `
  --serial emulator-5556 --adb <absolute-adb.exe> `
  --output artifacts/android-session-policy/<fresh-normal-run>
```

The output must be outside the frozen evidence and not already exist. The
driver does not start an emulator, install an APK, build inputs, or retry the
application. It stops only the owned package before one fresh nonce-bound
instrumentation command. The command omits
`env:RUNECLR_SESSION_NATIVE_ENTRY_WAIT` entirely. Failure preserves command
records and raw logs, and stops the owned launched process if necessary.

Acceptance requires these actual observations:

- Java, native and managed PID/nonce agree; runtime is .NET 12 x64, global
  interpreter mode and collectible diagnostic switch are both zero, and native
  required policy is one while ordinary/default contexts report zero.
- Twenty sessions match all seventeen golden fields, collect twenty contexts,
  perform 260 required policy queries and reject twenty retired queries.
- Native initialization/execution, managed exit and the exact instrumentation
  return code all succeed. Trusted contract JIT diagnostics are positive;
  targeted author JIT diagnostics are absent.
- The installed APK hash and all 246 installed file hashes agree before and
  after execution. Actual maps name the unique installed CoreCLR, interpreter
  and JIT paths for those inputs.
- Before/after owned-UID process and serial-forward snapshots contain no
  debugger server or owned forward. Live status samples have TracerPid zero;
  raw native logs have no entry-gate or observer markers. The owned process has
  exited after completion.
- Every required original raw log, request, identity snapshot and tracer
  sample is SHA256-bound by the transport receipt. A separate assessment
  records the outcome without mutating the transport receipt.

Offline reassessment does not launch the app:

```powershell
py -3 -B eng/android-session-policy-release-accept.py assess `
  --evidence artifacts/android-session-policy/20261013-release-entry-apk-attempt1 `
  --run <normal-run-directory> --output <fresh-assessment-directory>
```

The actual normal run passed on 2026-10-13. Its
[original assessment](../artifacts/android-session-policy/normal-functional-runner-02e88cd4e948420598bbd316ef226574/run/assessment.json)
binds PID 3621 and nonce `02ccd2af6bfe4adbacf5b823c0ba4641`: twenty sessions,
twenty collections, 260 required queries, twenty retired guards, 246 installed
identities before and after, twenty-five original raw hashes and four live
TracerPid-zero observations. Instrumentation launched exactly once; no gate
opt-in or debugger was used. The frozen driver SHA256 is
`ee29f0d4c6b748568ab6614bee3e90f5439737fd76cf0b1ae48016557541ada8`.
That actual frozen tool and its raw run are retained unchanged. Subsequent
review found its native HRESULT substring check could accept `0x01` as a
zero prefix. The current source instead requires one complete initialization
line with `0x0` and one complete execution line with
`0x0;RUNECLR_EXIT=0`; its SHA256 is
`14441bc9aaf8c5b0040d22c2dc32b41ce1f8ba359301098f4dfbc823ba3e79d6`.
An [exact-HRESULT offline review](../artifacts/android-session-policy/release-functional-hresult-review-91d21ce0aae64bc0a0710ad75715fa4e/results.json)
passes the same original normal raw and rejects three SHA-rebound copies with
initialization `0x01`, execution `0x01`, or execution `0x01` plus exit one.
This correction required no additional app launch.

A separate [offline review](../artifacts/android-session-policy/release-functional-offline-review-ded31ec9d55b4f32a9882f5a0ac4c807/results.json)
reassessed the original run successfully and rejected four copies with an
active gate marker, a foreign managed PID, an incorrect golden value, or a
missing original raw hash. The first three copies have their changed raw
hashes rebound so rejection tests content as well as transport integrity.
The original raw files were preserved; no application or device command was
repeated. The earlier gated v5 run remains ineligible for this acceptance even
though its twenty sessions have correct values.

This functional lane covers the selection fixture, not the full production
24-case lifecycle and 15-case package harnesses. The functional assessment
deliberately leaves `entryProofCollected` and `platformAccepted` false;
separate native method-entry receipts establish the execution path for
specific methods.

The later [Release production and recovery acceptance](android-session-policy-release-production.md)
separately runs the 24-case lifecycle and 15-case package suites, three samples,
scoped refusal/recovery and ordinary/fallback controls on this same frozen APK.
Those functional results do not expand the method-entry coverage of the earlier
nine-group selection capture.

The [independent root verification](../artifacts/android-session-policy/normal-functional-runner-02e88cd4e948420598bbd316ef226574/root-independent-verification.json)
rechecks all 25 normal raw hashes, each policy phase's query count, live
PID-bound tracer samples, 246 before/after identities and the separately bound
nine entry samples. The [owned emulator shutdown receipt](../artifacts/android-session-policy/normal-functional-runner-02e88cd4e948420598bbd316ef226574/root-shutdown.json)
records absent application/debugger processes, absent owned forwards, kill0
and emulator-5556 absent from adb afterwards.

The [complete normal-run archive](../artifacts/android-session-policy/normal-functional-20261013-02ccd2af.zip)
retains the original frozen driver/raw run, strict assessor, independent
verification, shutdown and all seven negative-case copies and assessments.
Its 234 files passed exact membership, size/hash and CRC verification against
unchanged source files; archive size is 1,497,236 bytes and SHA256 is
5d5d22b76396d7ea074da3a258dc3523d18e2a433bcf1861817fd76c773e8faa.
The [archive receipt](../artifacts/android-session-policy/normal-functional-20261013-02ccd2af.receipt.json)
also binds the separate entry archive's SHA256. The matching runtime layout,
APK and input evidence remain separately retained.
