# Android budget debugger transport and matching symbols

On 2026-10-13, a fresh gated APK passed actual pre-initialization debugger
attachment, native memory reading, detachment and subsequent budget execution
on the owned Android API35 x86_64 emulator. This establishes debugger transport
for the current budget candidate. No budget method-entry samples were collected
in that transport run. The subsequent
[entry acceptance](android-budget-entry-acceptance.md) now passes all nine groups
with178 samples and a separate same-APK gate-off15/73 run. The transport-only
evidence below remains unchanged.

## Exact application and scope

The [entry driver](../eng/android-session-budget-entry.py) consumes the existing
201-file budget bridge layout with unchanged runtime, CoreLib, trusted managed
composite and original author DLL inputs. It adds only an explicitly enabled
JNI gate before coreclr_initialize; it does not modify runtime source.
The application is `net.dot.RuneCLR_Budget_b0f4aac7280b`, APK SHA256
`1e11fe22c41070830c3b6e9ba09dc4e7675ac64d2d4742b98e7103e6123412e7`.
Builder compilation completes with zero warnings/errors; APK construction exits0.
The original ungated APK and its independent normal acceptance remain separate.

The gate activates only with `RUNECLR_BUDGET_NATIVE_ENTRY_WAIT=1`, validates
the fresh nonce and rejects an existing release file. It attempts PR_SET_DUMPABLE
and waits at most180 seconds using a monotonic clock. The default absent switch
returns immediately. Author IL is copied unchanged after installation.
The [build receipt](../artifacts/mobile-session-budget/android-budget-entry-apk-20261013-attempt1/entry-build.json)
binds original and derived driver hashes, the generated gate and native source.

## Actual transport run

PID `5340`, nonce `9d09db71e3ff4e6c9bcbb92ad7609fdb`, runs all15 budget
scenarios. Java and native PID/nonce agree at the waiting gate; CoreCLR
initialization has not completed. The same-UID NDK lldb-server attaches to that
PID through an ephemeral owned host forward. A local symbolic CoreCLR ELF target
has its slide established from the actual offset0 mapping and ELF PT_LOAD;
actual executable `/system/bin/app_process64` remains unchanged and hash-bound.

Actual ReadMemory returns the matching native ELF header. LLDB then detaches
successfully before the operator releases the gate. Native initialization and
execution, managed result and instrumentation exits are0; the resumed process
completes15 scenarios and73 context collections. All203 installed bundle/author/
APK hashes match before and after. The
[original receipt](../artifacts/mobile-session-budget/android-budget-entry-apk-20261013-attempt1/transport-9d09db71e3ff4e6c9bcbb92ad7609fdb/results.json)
and [root assessment](../artifacts/mobile-session-budget/android-budget-entry-apk-20261013-attempt1/root-transport-assessment.json)
both keep `nativeEntryProof=false`. The assessment verifies every actual budget
row, raw hashes, immutable inputs, ownership, mapped runtime and13 in-memory
row-corruption controls.

The first transport writer used adb shell text output, which converted LF to
CRLF; Windows writing added a second CR. Those original files remain unchanged.
Separate byte-preserving exec-out pulls of the same completed run bind all
device logs and child receipts. The first supplementary comparison failure
remains as a partial pull; the second
[pull receipt](../artifacts/mobile-session-budget/android-budget-entry-apk-20261013-attempt1/device-raw-9d09db71e3ff4e6c9bcbb92ad7609fdb-attempt2/pull-results.json)
records exact device hashes and the explicit newline-equivalence comparison.
No application rerun corrected this transport representation issue. Future
entry-driver pulls use exec-out bytes directly.

The app is uninstalled, the owned emulator is shut down and the ephemeral
debugger forward is absent. The
[cleanup check](../artifacts/mobile-session-budget/android-budget-entry-apk-20261013-attempt1/root-cleanup-check.json)
records these observations. No physical device or global debugger settings changed.

## Matching native symbols

The [symbol/source verification](../artifacts/mobile-session-budget/android-budget-entry-symbols-20261013-attempt1/verification.json)
binds private Release source tree `b54537ff42a066e41a01ea611a21f2e5e49934a1`,
exact native hashes, both .dbg images and interpexec.cpp. The16,102,436-byte
[archive](../artifacts/mobile-session-budget/android-budget-entry-symbols-20261013-attempt1/evidence.zip)
has SHA256 `c4c926c18c77ea0d1c30dd80779bc1f4d82ffe00c45a8a38149efcb713b5292c`.
Both local native/debug ELF pairs have matching actual GNU build IDs:

| Image | Build ID |
| --- | --- |
| libcoreclr.so | a7c85bcced09707ac0ce034bdd295fbeacaaf38b |
| libclrinterpreter.so | 15364d129ba166d8d530fa70f94bf75d1c205952 |

The bounded one-shot transfer completed one GET with exact size/SHA and zero
failed requests; the receiver independently rechecked archive CRC, file hashes
and native/symbol identities. An earlier overbroad remote symbol search timed
out; the subsequent lookup used only the explicit matching product directory.
Symbol availability alone does not establish method execution.

## Next actual gate

Reuse the frozen APK in a fresh owned run with a new nonce, preserving the
completed transport receipts. Bind the current author constructor/lifecycle/
private helper/delegate tokens and MVIDs to actual InterpreterStub or first-
opcode observations using these matching symbols. Validate optimized x64
variables against real instructions and DWARF rather than reusing ARM64 register
assumptions. Android's instrumentation completion and observed debugger process
status must remain distinct. Independently run the same gated APK with its
gate disabled after capture. Neither this transport run nor the older policy
fixture entries satisfy those method-entry/normal-run gates.
