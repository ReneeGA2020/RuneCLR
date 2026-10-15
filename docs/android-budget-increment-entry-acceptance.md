# Android method-entry acceptance of the counter increment

On 2026-10-14, a fresh gated APK over the exact minimal counter candidate
produces **178 valid interpreter-entry samples across all nine requested
author method groups**, with no capture errors. The same capture completes
15 budget scenarios and73 collectible-context collections. A separate
nondebugger run of the same APK with the gate absent also passes strict15/73
acceptance. This is Android API35 x64 emulator evidence.

## Fresh gate and preserved inputs

Commit `112e97408de1ae1c2a6cbd2967dcd250cd2d491c`, tree
`91673a7980bda79006259e525741fecb04324444`, is the
[matched mobile build](mobile-budget-increment-builds.md). The new
[gated APK adapter](../eng/android-budget-increment-entry.py) pins the accepted
APK adapter and gate-source hashes, and reuses the downloaded new bridge/layout
without rebuilding CoreCLR, framework R2R or the managed bridge.

The original [functional APK](android-budget-increment-acceptance.md) remains
unchanged. All original native/managed app hashes are identical in the new
package. Removing the inserted JNI gate restores the original JNI source
exactly; Java source remains byte-identical. The default absent switch returns
immediately; explicitly enabling `RUNECLR_BUDGET_NATIVE_ENTRY_WAIT=1` waits
before CoreCLR initialization with a fresh nonce and a180-second bound.

The new package is `net.dot.RuneCLR_Budget_73767b32248f`, APK SHA256
`11a3984b74ed564e325a802a779bee9bb6d4fc83ae953a5501884d7b28185652`. Its
[build receipt](../artifacts/mobile-budget-increment/android-entry-apk-20261014-attempt1/entry-build.json)
binds the gate, APK and exact input comparisons. Native and trusted managed
inputs are transferred in a bulk archive; original author IL is transferred
in a separate archive after installation. The actual installed inventory
contains203 entries.

## Matching symbols and actual entry capture

The [symbol verification](../artifacts/mobile-budget-increment/android-entry-symbols-20261014-attempt1/verification.json)
checks both native/debug GNU build-ID pairs, source and exact hashes. A
bounded one-shot transfer downloads16108685 bytes, SHA256
`1b37dea94a4dba5d42be300ca8a85885d98559f1dc0149de9c06ca89aa1b5b54`;
archive CRC/member hashes pass. The
[server receipt](../artifacts/mobile-budget-increment/android-entry-symbols-20261014-attempt1/transfer-results.json)
records one successful GET, zero failed requests and the same sent bytes/hash.
The private token is excluded from evidence and logs.

The previously [prepared contract](android-budget-increment-entry-preparation.md)
now executes in a fresh actual capture: PID3363, nonce
`2e12397007a444e89535aef1f90158e4`. The
[controller](../eng/android-budget-increment-entry-run.py) creates observer
configuration only after reading the actual owned Java/native PID at the
pre-initialization gate. Same-UID LLDB attachment binds the actual CoreCLR
offset0 mapping and its ELF header before releasing that gate.

There are127 InterpreterStub and51 regular child first-opcode samples.
Child dispatch binds file PC0x3b0aff, r14 opcode pointer, rbp-0xe48 context
spill, typed startIp offset8 and actual preceding ReInit/reload bytes. These
preceding bytes are read from the live process in this capture, rather than
credited solely from the offline image. Optimized-local pFrame DWARF locations
remain unclaimed.

| Requested method group | Samples |
| --- | ---: |
| Base constructor / OnStart / OnStop | 28 / 27 / 20 |
| Normal constructor / OnStart / OnTick | 20 / 20 / 60 |
| FiniteCleanup.OnTick | 1 |
| Private.Helper.Finite / nested delegate | 1 / 1 |

The [raw-sample assessment](../artifacts/mobile-budget-increment/android-entry-assessment-20261014-attempt1/results.json)
reparses all178 raw LLDB records, matching PE MVID/tokens, collectible
definition owners, bytecode headers/first-opcode addresses and breakpoint
identity. Four altered entry controls and13 altered ledger controls reject.
It reports `nativeEntryProof=true` for this sampled scope and
`completeInvocationCapture=false`. The original controller conservatively
retains its `nativeEntryProof=false`; its frozen result is not rewritten.

LLDB observes debugger process status9, preserved as observed. Native
initialization/execution, managed completion and Java instrumentation all
return0, with15/73 complete and all203 installed hashes unchanged. The
hash-bound Java source forwards the actual executeEntryPoint result to
instrumentation finish. This accepts this runner's completed execution;
status9 without these independent zero-exit signals would not pass.

## Independent normal run and cleanup

The same APK runs without an active gate or debugger as PID3545, nonce
`d836914c338145ae9883d4abc463975d`. Its
[strict audit](../artifacts/mobile-budget-increment/android-entry-normal-audit-20261014-attempt1/results.json)
passes `mobileVerified=true`,15/73 and15 corruption controls. Native logs
contain no entry-gate marker;203 installed-before/after entries match.
The [actual cleanup check](../artifacts/mobile-budget-increment/android-entry-apk-20261014-attempt1/cleanup-check.json)
confirms successful app uninstall, absent owned emulator/PID and absent owned
debugger forwards. No physical device is touched.

An [independent offline cross-check](../artifacts/mobile-budget-increment/root-android-entry-review-20261014-attempt2/results.json)
recomputes all178 raw samples against original PE-derived identities, checks
APK native bytes, both native/debug GNU build-ID pairs and three emitted code
pieces, and matches both15/73 ledgers and203 observed inputs. Four altered
sample controls reject. The [review script](../eng/android-budget-increment-entry-review.py)
checks recorded cleanup and performs no new process/device actions. Its first
passing receipt is preserved; attempt2 adds original PE hashes and identity,
native owner/init logs and cross-run installed-input/ledger binding.

Three local installation-preparation failures remain in distinct evidence
children: missing fresh files directory, a native-path parser error and an
exec-out command-quoting error. They occur before author transfer/application
launch. The final bulk install checks the unchanged installed APK and finishes
without reinstalling or recompiling it. These are experiment-driver defects,
not new CoreCLR failures.

This lane does not establish complete invocation capture, receiver-MethodTable
comparison, mobile finalizer/concurrent termination, physical-device behavior
or performance.
