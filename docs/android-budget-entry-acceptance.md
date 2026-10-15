# Android Release budget method-entry samples

On 2026-10-13, the frozen APK from the
[debugger preparation](android-budget-entry-preparation.md) produced 178 valid
interpreter-entry samples covering all nine requested author method groups.
The same run completes 15 budget scenarios and 73 context collections, with
203 installed hashes unchanged. A separate gate-off run of the same APK also
passes strict 15/73 acceptance. This is Android API35 x64 emulator evidence,
not physical-device or exhaustive invocation coverage.

## Actual capture and independent checks

The second run uses PID 6436 and nonce 4e28d30e6b0a45999cb27b4eab7768ed.
There are 127 InterpreterStub and 51 regular child first-opcode samples, with
zero capture errors. Loaded PE MVID, token, collectible definition owner,
bytecode header, MethodDesc bytecode identity and exact native breakpoint bind
the unchanged two author DLLs and matching Release symbols.

| Requested method group | Samples |
| --- | ---: |
| Base constructor / OnStart / OnStop | 28 / 27 / 20 |
| Normal constructor / OnStart / OnTick | 20 / 20 / 60 |
| FiniteCleanup.OnTick | 1 |
| Private.Helper.Finite / nested delegate | 1 / 1 |

The [independent assessment](../artifacts/mobile-session-budget/android-budget-entry-independent-prep-20261013/live-results.json)
and [root replay](../artifacts/mobile-session-budget/android-budget-entry-independent-prep-20261013/root-live-results.json)
pass raw hashes, actual PE/bytecode and all 15/73 budget rows. Four entry
alterations and thirteen ledger alterations are rejected. Both report
nativeEntryProof=true for the nine sampled groups and
completeInvocationCapture=false. No independent receiver MethodTable match
is claimed from the recorded definition-owner MethodTable.

## Optimized x64 frame contract

The Release DWARF has no usable pFrame formal-variable location at this PC.
Actual child dispatch at file PC 0x3afe8d reads the frame from rbp-0xe40 and
the bytecode start through typed field offset 8. The r12 opcode pointer must
equal the first opcode address. Source line 3751, type metadata, live dispatch
instructions and 33 preceding ReInit bytes support this emitted-code contract.
The receipt explicitly records localVariableDwarfAvailable=false.

The [native contract review](../artifacts/mobile-session-budget/android-budget-entry-independent-prep-20261013/contract-results.json)
also verifies the seven-byte preceding spill reload against the matching native
file. Those seven bytes were not separately read from the live process. The
current [prepare tool](../eng/android-session-budget-entry-capture.py) adds that
live read and an author-state hash check for future runs; neither addition is
credited to the frozen executed observer. The retained preparation receipt's
old wording is clarified by a separate
[scope note](../artifacts/mobile-session-budget/android-budget-entry-operator-20261013-attempt1/capture-4e28d30e6b0a45999cb27b4eab7768ed/preparation-scope-note.json).

## Completion and independent normal run

LLDB observes process status 9. The original value remains unchanged. Actual
native initialization/execution, managed completion and Java instrumentation
all return 0, with all 15/73 rows and 203 before/after hashes. Hash-bound Java
source passes the actual executeEntryPoint result to finish. This accepts this
Android runner completion only; status 9 without those independent successful
signals would fail the assessment.

The gate-off run uses PID 7395, nonce 054e43e3be8f4864a781dc9d2df1f656. Its
[strict independent audit](../artifacts/mobile-session-budget/android-budget-entry-independent-normal-20261013-attempt1/results.json)
passes mobileVerified=true, 15/73, 203 unchanged installed entries and 15
corruption controls. It contains no active entry-wait gate. The
[cleanup check](../artifacts/mobile-session-budget/android-budget-entry-operator-20261013-attempt1/root-cleanup-check.json)
confirms app uninstall, emulator shutdown and absent owned debugger forwards.
No physical device was touched.

The first capture retains 273 stub samples across six groups and 150 observer
errors, despite successful functional completion. Its original receipt remains
unchanged. The second controller conservatively retains nativeEntryProof=false;
use the independent/root assessment for the final sampled conclusion. Original
streams, observers and receipts remain in the operator evidence directory.

Relevant unchanged lifecycle/upstream controls on matching budget builds, full
Release terminal/finalizer boundaries, mobile performance and physical-device
acceptance remain separate work. See the
[mobile acceptance record](mobile-host-budget-acceptance.md).
