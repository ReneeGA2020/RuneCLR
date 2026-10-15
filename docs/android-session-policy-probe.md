# Android required-session probe — prepared, not executed

On 2026-10-13, [the independent probe tool](../eng/android-session-policy-probe.py)
prepared a Checked Android x64 raw-log acceptance interface for
[the matching-runtime plan](android-session-policy-plan.md).
**No Android product, APK, device or emulator was built or executed by this
tool. Android session-policy acceptance is not yet established.**
The Windows archives used to verify parsing remain Windows evidence.

The tool owns execution-log assessment, while the separate APK driver owns
packaging, instrumentation, native initialization, deployment, process identity,
device hash reads and cleanup. The Android candidate needs matching private
CoreCLR/interpreter/JIT/CoreLib with FEATURE_INTERPRETER explicitly enabled;
historical shipping Android RC1/JIT results do not establish this feature.

## Actual fixture semantics and lanes

This reuses the trusted [independent session fixture](session-interpreter-validation.md),
with a shared default-context contract, per-context IL/private dependencies,
NoInlining execution frames and values/weak references returned to the host.
The private dependency is absent after entry construction and resolves during
the first Run body. Observed native policy must remain 1 throughout required
load/run/retirement boundaries, while ordinary/default policy is 0.

| Semantic probe lane | Required raw observation |
| --- | --- |
| `required` | 20 exact business values/static resets and collected contexts; 26 actual bytecode groups × 20; no reported author-definition native JIT; trusted RunFrame native JIT positive |
| `ordinary` | Same host/payload bytes; policy 0; 20 values/collection; zero author bytecode and actual Entry.Run native JIT positive |
| `required-refusal` | Exact scoped real CORJIT_SKIPPED on Refusal.Entry:Reject; managed NotSupportedException and refused-context collection; next 20 normal required contexts pass 26 × 20 bytecode; 21 retirement guards |
| `unmarked-fallback` | Same Refusal DLL with mode 1; one actual SKIPPED; native Reject body executes, returning 73 |
| `required-boxed` | 20 cold/warm interface and closed-delegate values/reset/collection; five underlying IL groups × 20 bytecode; trusted BoxedFrame native positive |
| `ordinary-inline` | 20 trusted native generic callers and 20 actual successful concrete author inlines; correct values/collection |
| `required-inline` | Same bytes; trusted definition remains native; 20 exact inline rejection decisions, 20 underlying IL bytecode dumps; no author-definition JIT or successful inline; 20 contexts collected |

Main lanes require InterpMode 0, RuneCLRInterpretCollectible 0, R2R 1 and
tiering 1. Inline lanes deliberately use tiering 0 for immediate FullOpts
inline decisions. Only the unmarked-refusal comparison uses mode 1.
Required-refusal and unmarked-fallback set the exact test-only methodset
`SelectionUGC.Refusal.Entry:Reject`. This is compiler injection into the
real interpreter return path, not an exception string manufactured by a fixture.

Every ordinary/required control must bind identical managed producer hashes.
The optional `matrix` command checks five core lanes or all seven, one
independent assessment each, with matching runtime and managed-input identities.
It cannot promote a Windows parser result into an Android matrix.

## APK interface and owned logs

The cooperating APK driver uses one run ID and separate owned files:

    run-<lane>-<id>/
      request.json
      results.json
      native.log
      jit.log
      managed.log
      managed-result.json
      instrumentation.log
      hash-reads.log
      pid-query.txt
      maps.log

JNI redirects native stdout/stderr before coreclr_initialize; bytecode output
must remain untruncated in its original native file. Native JIT diagnostics go
to an explicit DOTNET_JitStdOutFile, preventing tiered summary lines from
corrupting bytecode lines. The managed writer must be installed as both
Console.Out and Console.Error: the fixture selects Console.Error itself.

Required native pre-initialization header:

    ANDROID_SESSION_NATIVE pid=<PID> runId=<RUN_ID> InterpMode=0 RuneCLRInterpretCollectible=0

Mode 1 is allowed only for unmarked fallback. Runtime initialization/execute
HRESULT zero and RUNECLR_EXIT zero are required independently of managed PASS.
The native PID/nonce must match the wrapper/transport receipt and an actual
owned-process query. The original managed header independently binds the same
PID/run ID/lane and reports X64. Original instrumentation must complete with
return-code=0, and request/result bind the same source and manifest identities.
Preserved JSON-lines framing (pid/message) or logcat
threadtime framing is supported; only the owned PID is decoded. Raw framing
files remain SHA-bound. Logcat is not a substitute for complete native dump
storage when its line/buffer limits would truncate the source.

The tool currently requires the following explicit proof fields. They are
integration requirements, not fabricated actual receipts:

- Request: platform=android, abi=x86_64, probeLane, runId, settings, optional
  logFraming by native/jit/managed source. DOTNET settings or the APK's
  interpMode/diagnostic/readyToRun/tiered/jitStdOutFile/refuseMethods aliases are
  accepted; contradictory aliases fail. Native-JIT negative evidence also
  requires explicit jitDisasmSummary=1, interpList=1 and interpDump=*:* coverage.
- Transport result: platform/abi, appPid/runId, pidQueryObservedPid and
  pidQueryCommand, normalExitCode=0, nativeManagedExitZero=true,
  bundleUnchanged/payloadUnchanged, candidateCommit, productManifestSha256,
  installedRuntimeHashes, managedIdentitySha256, installedManagedHashes and
  rawHashes of all eight raw/result/query files listed above. Truncated output
  cannot pass. Managed-result contains the same runId, appPid, lane, exitCode=0
  and native version/default/ordinary/required acknowledgements.
- Matching product identity: platform/abi/configuration=Checked, pinned
  base/commit, tracked-clean source, actual featureInterpreter and
  featureDynamicCodeCompiled receipts, and artifactHashes matching device-side
  runtime hashes. Matching source/build provenance must be established by the
  builder, not inferred from the product directory name.
- Managed producer identity: files map matching installed trusted/payload
  bytes, including the same Refusal DLL across required and ordinary controls.
  The assessor independently parses the original standard sha256sum records
  for every runtime/managed input and the request's installed APK SHA. Runtime
  native paths must share the actual mapped CoreCLR directory; CoreLib and
  relative managed files must match the app-owned files paths. Repeated hashes
  must agree. The original pre-CoreCLR Java Process.myPid query must match the
  native/managed PID, and a required lane must actually map libclrinterpreter.so.
  Device command execution and matching-source build provenance remain the
  APK driver's responsibility; the offline assessor binds and checks its reads.

## Commands and scope

    python3 eng/android-session-policy-probe.py plan \
      --lane required-refusal --payload DEVICE_FILES/plugin \
      --evidence DEVICE_FILES/probe-evidence \
      --jit DEVICE_FILES/session-<id>.jit.log

    python3 eng/android-session-policy-probe.py assess \
      --lane required-refusal --run ACTUAL_DOWNLOADED_RUN \
      --product MATCHING_ANDROID_PRODUCT_JSON \
      --managed-identity MANAGED_PRODUCER_IDENTITY_JSON \
      --output NEW_ASSESSMENT_JSON

    python3 eng/android-session-policy-probe.py matrix \
      --assessment REQUIRED_JSON --assessment ORDINARY_JSON \
      --assessment REFUSAL_JSON --assessment FALLBACK_JSON \
      --assessment BOXED_JSON --output NEW_MATRIX_JSON

The assessor reads original logs without restarting instrumentation, an app or
the runtime. It compares all seventeen actual business values, exact session
numbers, bytecode group multiplicity, native owner classifications, native
policy queries and protected retirement. Trusted generic signatures may include
a collectible type argument; author JIT classification follows the method
definition owner immediately after JIT compiled, not any UGC string in the
line. A successful bytecode preparation dump is not itself a native execution
entry trace; each compiled method record must retain its actual Locals size and
IR bytecode body, while business execution and zero reported author JIT are distinct
evidence. Native entry tracing, matching Release parity, ARM64 phones/16KiB
pages, full hostile-code isolation and author-created unmarked contexts remain
separate work.

## Preparation checks

`check-windows-parser` reads the actual previously verified Windows raw
archives; it emits only explicitly Windows historical parser compatibility
output and produces no Android acceptance JSON. The current parser matched
all five real Windows core lanes plus both inline controls, including actual
compiler-SKIPPED/refusal/recovery and same-IL native fallback. This validates
the parser against preserved execution data without rerunning an application.
AST, framing and negative-control checks are preparation checks only.

The 2026-10-13 preparation receipt is under
`artifacts/session-policy/android-probe-parser-preparation-20261013-043047-22e43e7dad4b48d79bdc9a741cd99e0a`.
Seven mutations of actual preserved Windows logs were rejected: removing the
real compiler-SKIPPED marker, refusal exception, one compilation or retirement
guard; inserting an author JIT record; changing a business value or observed
policy. JSON-lines and logcat decoding retained the actual owned-PID messages
and ignored foreign-PID contamination. The target POSIX Refusal path remained
POSIX even when preparation ran on Windows. This receipt explicitly records
applicationExecuted=false and androidAcceptanceEstablished=false.

The follow-up identity parser checks are under
`artifacts/session-policy/android-probe-identity-preparation-20261013-043944-5a4b7f1aed9b40b890c21138bae2b0a8`.
Controlled hash-record tests rejected wrong runtime/managed hashes, absent APK,
wrong mapped native directory and conflicting repeated reads. These are
synthetic contract checks, explicitly not device hash evidence. Removing the
first bytecode-body header from the actual Windows refusal archive also failed.
All seven historical Windows lanes still parsed with the stricter actual-body
gate; that preparation did not execute Android.

## Later actual Android execution

On 2026-10-13, the same assessor passed five independently owned Android x64
Checked core lanes with the matching source-built runtime and unchanged APK/IL.
The [actual matrix](android-session-policy-validation.md) includes required
interpretation, ordinary JIT, compiler refusal with subsequent recovery,
unmarked fallback and boxed calls. The first required lane's host-side Python
argument error was recovered by assessing its preserved logs without rerunning
the app. These are actual emulator bytecode/JIT/refusal observations; native
method-entry tracing, optional inline controls and ARM64 devices remain separate.
