# Android session-policy validation

On 2026-10-13 (local date), the matching Android x64 Checked APK passed the
current production lifecycle, controlled-package and sample suites with required
session interpretation. This is an actual owned-emulator run, using
InterpMode=0 and RuneCLRInterpretCollectible=0. Its receipt records
functionalPassed=true and executionEvidencePassed=true, while
platformAccepted=false. The separate five-lane Checked selection/refusal matrix
also now passes; the remaining platform milestones are separate gates.

## APK and runtime identity

The candidate is 1724cdec553a7aff7a373a271a4be612651c7625, tree
71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2, on official base
0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de. It consumes the accepted
[Checked source build](android-session-policy-build.md),
[same-source Release framework](android-session-policy-framework.md) and
[195-file private layout](android-session-policy-layout.md). This is a private
source product, not a stock shipping NuGet runtime.

The build used the frozen current production DLLs plus a new Android wrapper
and JNI/Java APK bridge. Builder and wrapper builds report zero warnings/errors;
APK generation, alignment and signing all exit0. APK SHA256 is
6ec70c85f1dea4c3e8a076ca2b1b32ba322c2994842960a4071b1af454ba727f.
The actual APK classes2.dex SHA256 is
36e3a02b5e2711086b1cffc7894702c14a711de87191409c6a2294d6f5566425,
matching the same-source crypto DEX input exactly. The crypto JAR is retained as
provenance, not installed as a managed/native runtime asset.

The owned AVD was RuneCLR_API_35_x64, emulator-5556, with actual API35,
x86_64 kernel and 4096-byte pages. The new application ID is
net.dot.RuneCLR_Session_d2c3a04dd958. Trusted host/framework IL can JIT natively
on Android; author/private IL remains in session-owned required contexts.
CoreCLR, CoreLib, the dynamic interpreter and target JIT are matching source
outputs. This topology differs from iOS's trusted R2R/no-JIT player.

## Current production all lane

The preserved [request](../artifacts/android-session-policy/20261013-apk-attempt1/run-all-14293d6156da439cb09a8d939dd68d06/request.json)
and [results](../artifacts/android-session-policy/20261013-apk-attempt1/run-all-14293d6156da439cb09a8d939dd68d06/results.json)
bind runId 14293d6156da439cb09a8d939dd68d06 and owned PID6128. Java's
Process.myPid() was recorded before CoreCLR initialization; native and managed
headers and managed-result.json agree on the PID/nonce. Runtime path evidence
comes from the same process's maps.log, and raw device sha256sum reads bind the
APK, installed runtime and host/payload files. The results SHA256 is
89d4acb21dc07b53fb17b71d0561f963d8d273676a38e80c51468c86fa27af5c.

Actual settings are InterpMode0, global collectible diagnostic0, ReadyToRun1,
tiered compilation1, JitDisasmSummary1, InterpList1 and InterpDump=*:*.
The trusted CoreLib policy query reports version1, default0, ordinary0 and
required1; all three production entry points acknowledge required interpretation.

The [managed log](../artifacts/android-session-policy/20261013-apk-attempt1/run-all-14293d6156da439cb09a8d939dd68d06/managed.log)
contains:

- 24/24 lifecycle tests, including reset/unload, exceptions, dependency isolation,
  late IL and default-context dependency rejection.
- 15/15 controlled-package tests, including source/import/source, private-helper
  version/generic-static isolation, admission failures and recovery.
- Hello → Arena → Hello, with all three contexts collected and each Hello run
  starting with fresh statics.

Installation was recorded at 2026-10-12T21:17:29.8624773Z. Controlled fixtures
and the separate late map were produced by the operator after installation;
the producer completed at 21:18:11.5478495Z. The all run started at
21:18:54.3748104Z and completed at 21:19:27.5599303Z. These UTC times fall on
2026-10-13 locally. Compilation tooling was not copied into the player, and
the same APK and trusted host bytes were retained while new IL was transferred.

The actual JIT log includes native RuneCLR.Runtime.MapRunner:Run. The native
interpreter log contains same-method author bytecode bodies with Locals size
and IR instructions, rather than just accepted environment switches or method
names. An independent reread finds 155 body sections for the checked
RuneCLR.TestMaps/GameScript/Maps.Hello/Maps.Arena names and no author JIT summary
entries for those names. These sections are not unique-method or invocation
counts, and this diagnostic body evidence is not native method-entry sampling.
Successful managed completion supplies the independent functional evidence.

Instrumentation and managed exits are0, native initialize/execute HRESULTs are0,
and the native managed-exit marker is0. All 11 SHA-bound raw files reread
correctly; installed runtime hashes match product-manifest.json, current host
hashes match the frozen host inputs, and bundleUnchanged/payloadUnchanged are
true. Full native/JIT/managed files were retained without log truncation.

## Required selection lane

The separate required run used PID7210 and nonce
64aa6601a97143e1b6687974f8818afe, with the same APK, runtime and managed-input
identities. Its [append-only recovery assessment](../artifacts/android-session-policy/20261013-apk-attempt1/run-required-64aa6601a97143e1b6687974f8818afe/method-assessment-recovery.json)
passes 20/20 functional sessions and 20 collected contexts, 260 native policy
queries, 20 retired-query guards, 26 author/private bytecode groups and 520
actual body dumps. Author-owner JIT summary count is0, with no skipped methods.
The assessment explicitly records methodNativeEntryProof as not collected:
bytecode preparation plus values/native-JIT diagnostics is not per-method
native-entry tracing.

The original host-side assessment launch failed because a PowerShell scalar
argument-concatenation bug malformed the Python command. Its
[failure assessment](../artifacts/android-session-policy/20261013-apk-attempt1/run-required-64aa6601a97143e1b6687974f8818afe/failure-assessment.json)
and original results remain intact. The root independently reassessed the same
preserved raw logs by directly invoking Python with the actual arguments,
before the launcher fix was complete; appRerun=false. This is a local
assessment-launch error, not an Android runtime refusal or application failure.

## Five-lane Checked matrix

The actual [core-matrix.json](../artifacts/android-session-policy/20261013-apk-attempt1/core-matrix.json)
passes with sameRuntimeAndManagedInputs=true. Its SHA256 is
034147c62df88b9d229933525a130466ea38286d9e170cd8c7f8de7a4729349f.
All five assessment hashes and their original raw-file hashes independently
reread correctly. Each lane binds the same APK, product-manifest SHA256
f60a536d18a305d0be3339a1946d3622f75add802db1734a9e3c1798b46cda75
and managed-identity SHA256
d3f3f8d1a66ac48e9a51c46df3a63794c622a170d538ea96dd8c39e6698e022e.
Installed runtime hashes match the mapped private runtime for every lane;
native/managed exits are0 and host/payload hashes remain unchanged.

| Lane | Native policy / InterpMode | Functional result | Bytecode groups / body dumps | Author JIT summaries | Native queries / retired guards |
| --- | --- | --- | --- | ---: | --- |
| required | 1 / 0 | 20/20 values and collected contexts | 26 / 520 | 0 | 260 / 20 |
| ordinary | 0 / 0 | 20/20 values and collected contexts | 0 / 0 | 180 | 260 / 20 |
| required-refusal | 1 / 0 | Refusal collected, then 20/20 recovery sessions collected | 26 / 520 | 0 | 265 / 21 |
| unmarked-fallback | 0 / 1 | Refused interpretation falls back natively; value73 | 0 / 0 | 1 | 0 / 0 |
| required-boxed | 1 / 0 | 20/20 interface/closed-delegate values and collected contexts | 5 / 100 | 0 | 120 / 20 |

Required-refusal and unmarked-fallback each have one actual interpreter skipped
method, SelectionUGC.Refusal.Entry:Reject. The required context produces the
expected NotSupportedException without author native fallback, retires that
context and then completes the recovery sessions. The unmarked ordinary
control, explicitly in InterpMode1, instead JIT-compiles that refused method
and returns73. It is a diagnostic fallback control; mode1 is not used to make
the required production lanes pass. Global collectible diagnostic remains0 in
every lane. The boxed lane exercises actual value-type interface calls and
closed delegates, with interface/warm-interface/closed-delegate value17.

All five runs have distinct owned PIDs and nonces:

| Lane assessment | PID | Run nonce |
| --- | ---: | --- |
| [required](../artifacts/android-session-policy/20261013-apk-attempt1/run-required-64aa6601a97143e1b6687974f8818afe/method-assessment-recovery.json) | 7210 | 64aa6601a97143e1b6687974f8818afe |
| [ordinary](../artifacts/android-session-policy/20261013-apk-attempt1/run-ordinary-f7b8068d71144cbbb3e892cdcbb8f413/method-assessment.json) | 8314 | f7b8068d71144cbbb3e892cdcbb8f413 |
| [required-refusal](../artifacts/android-session-policy/20261013-apk-attempt1/run-required-refusal-9106fa8a3d984eb8bb5c298b803fe5b4/method-assessment.json) | 9377 | 9106fa8a3d984eb8bb5c298b803fe5b4 |
| [unmarked-fallback](../artifacts/android-session-policy/20261013-apk-attempt1/run-unmarked-fallback-765dc0383736498bb6da0631bf1a1d76/method-assessment.json) | 10435 | 765dc0383736498bb6da0631bf1a1d76 |
| [required-boxed](../artifacts/android-session-policy/20261013-apk-attempt1/run-required-boxed-f75ccb0951664086b3ce09a6c564c72e/method-assessment.json) | 11501 | f75ccb0951664086b3ce09a6c564c72e |

The ordinary/refusal/fallback/boxed transport results retain their original
pre-assessment functional flags; append-only final-assessment.json records the
successful method assessment separately. The recovered required assessment
likewise preserves its original failed launcher receipt. No application was
rerun to obtain these assessments. Bytecode groups, body dumps and JIT summaries
are diagnostic records rather than complete invocation counts. Every method
assessment explicitly states that native method-entry proof was not collected.

## Preserved evidence

The [independent final review](../artifacts/android-session-policy/20261013-apk-attempt1/final-verification.json)
verifies the APK, 203 player files, 203 nested APK assets, 11 APK native images,
43 payload files, 30 provenance checks and the original raw assessment hashes.
Its SHA256 is 26fdcf8e71667d14b364a96b7158a6028aff9568efc6c4851325ccd9e9fa1174.
The owned emulator was [confirmed shut down](../artifacts/android-session-policy/20261013-apk-attempt1/emulator-shutdown.json).

The final [evidence archive](../artifacts/android-session-policy/20261013-apk-attempt1-505b08cc186c43c0ad6084159b6d3fd4.zip)
is 60,835,166 bytes, SHA256
4fb2c661eb3473e9cf01f425c27d442e92b8e147f23cc41550b35f367ff92d41.
An [independent archive check](../artifacts/android-session-policy/20261013-apk-attempt1-505b08cc186c43c0ad6084159b6d3fd4.zip.verification.json)
passes SHA256, ZIP CRC and all 578 member hashes against the retained files.
The earlier ZIP is preserved separately: its 577 members matched, but the
review agent appended its attempt ledger after that snapshot, so the final
archive was created only after all writers finished. No app was rerun.
Documentation snapshots inside the archive predate this archive-link addition.

## Remaining gates

The production all lane and five-lane Checked matrix are independent evidence.
Platform acceptance remains false. The additional inline
fixture has not been frozen, fresh Release native entry has not run, and
physical ARM64 devices, 16KiB-page acceptance and iOS refusal/recovery remain
unverified. Checked
emulator evidence does not establish those capabilities or a hostile-code
security sandbox. See the [acceptance driver](android-session-policy-acceptance.md)
and [method assessor](android-session-policy-probe.md) for the distinct gates.
