# Mobile host-budget acceptance on 2026-10-13

Both iOS simulator ARM64 and Android emulator x64 Release application runs pass **15 budget scenarios and 73 collectible-context collections in one process**. Strict audits bind installed inventories, process identity and raw results. Separate debugger runs now sample all nine requested author method groups on each platform. Physical-device execution remains open.

## Exact iOS run

Runtime commit `1c623a776b4471e641e95e4e3c82959c6cb9590f`, tree `b54537ff42a066e41a01ea611a21f2e5e49934a1`, uses official base `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. The [matching builds](mobile-instruction-budget-builds.md) bind the new Release native/CoreLib/compiler. Original framework IL, new CoreLib, four current trusted DLLs and a fixed executable bridge were rebuilt as a composite. Both author DLLs were absent from the app bundle and transferred after installation unchanged.

Remote output: `ROOT/ios-session-budget-acceptance-20261013-attempt6`, with ROOT `/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr`. Owned iOS27 simulator: `8F33BEEB-6B6F-401E-9090-06CA79DF6723`. The single all launch used PID `94221`, nonce `47e25883ef3d45f29ccd3acf17f80459`, InterpMode0, RuneCLRInterpretCollectible0, ReadyToRun1 and no debugger.

The [native stream](../artifacts/mobile-session-budget/ios-acceptance-20261013-attempt1/raw/current/run-all/launch.log) has one matching PID/config header, owned managed completion15/73, `CORECLR_INITIALIZE_HRESULT=0x0` and `CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0`. Platform launch exit0 and [simulator shutdown exit0](../artifacts/mobile-session-budget/ios-acceptance-20261013-attempt1/raw/current/cleanup.json) are recorded.

The [aggregate](../artifacts/mobile-session-budget/ios-acceptance-20261013-attempt1/raw/current/run-all/adapter-evidence/result.json) binds fifteen original child receipts. The [independent row audit](../artifacts/mobile-session-budget/root-ios-functional-review-20261013-attempt1/results.json) checks all73 business rows and rejects fifteen in-memory corruption controls. Counts are measured without hardcoding desktop values: normal execution96, finite cleanup38, infinite cleanup4096, exhausted execution8192. Ordinary cancellation and malicious exception-message reporting retain native reason0.

The [root binding](../artifacts/mobile-session-budget/ios-acceptance-20261013-attempt1/root-functional-binding.json) independently verifies all89 archive members, nineteen run hashes, matching source/products, PID/nonce/native completion, author hashes and shutdown. The116711-byte [archive](../artifacts/mobile-session-budget/ios-acceptance-20261013-attempt1/evidence.zip) SHA256 is `20bf91b70ffb1132891134030fc7b21fd167096c9acc0a0d1ab7b0318f8c6347`. Five failed preparation attempts and the frozen successful repair driver are retained; these are RuneCLR experiment-driver defects, not new upstream runtime bugs.

## Independent normal run with actual installed inventories

A second fresh nondebugger run on the same frozen application independently
passes 15 scenarios and 73 collections. PID `95481`, nonce
`50418ad90389461994f7d75ea256fdc3`, belongs to
`ROOT/ios-session-budget-functional-20261013-attempt1`. The controller samples
actual installed app/author files before launch and after completion: all
200 bundle files and both original author DLLs match. Native initialization,
execution and managed exits are zero; the simulator shuts down successfully.
The [independent strict audit](../artifacts/mobile-session-budget/ios-functional-independent-20261013-attempt2/independent-review.json)
and [root audit](../artifacts/mobile-session-budget/root-ios-functional-complete-20261013/results.json)
both pass with `mobileVerified=true` and 15 corruption controls rejected.
The new [77184-byte archive](../artifacts/mobile-session-budget/ios-functional-20261013-attempt1/evidence.zip)
has 34 members/33 raw hashes, SHA256
`aaee4c42d405eba42f2bf836cccd8a3048693a0581959ae5e7885a8c57caa440`.
The first offline manifest parser failure is retained separately; original
archive bytes and application output were unchanged.

## Evidence boundaries

For the first run, the pre-install **built bundle** inventory matches the
actual post-run **installed bundle** inventory for 200 files. No installed
pre-run sample exists for that historical run. Its original strict gate
remains pending, while the separately measured normal run above closes the
project's installed-before/after gap. The updated reviewer supports both
transport schemas without modifying their original evidence.

The initial functional runs collected no native interpreter-entry samples from these budget author DLLs. The later separate iOS debugger run below supplies samples for nine method groups; its samples do not count every invocation. Production intake rejects authored finalizers; this host lane does not establish mobile finalizer controls, concurrent termination, blocking host/native calls or hostile-code isolation. [Physical iOS device readiness](ios-device-readiness.md) remains separate.

## Android framework increment

A fresh Android x64 Release framework/layout passed:180 original framework IL assemblies plus new CoreLib and four trusted DLLs give185 inputs,186 R2R outputs and200 layout files. Crossgen took23 seconds, exit0, no warnings. The old1724 layout was rejected; explicitly inventoried original IL and unchanged OS shims were reused. New critical7 remain bound to the new candidate.

The [independent local review](../artifacts/mobile-session-budget/android-layout-evidence-20261013-attempt1/independent-local-review.json) checks raw hashes, CoreLib methods/fields/MVID equality and four negative controls. The194680-byte,34-member [archive](../artifacts/mobile-session-budget/android-layout-evidence-20261013-attempt1/android-session-budget-layout-receipts.zip) SHA256 is `e8cb95e55bde224d8167f751402cbfbebc0732d1cbd6d167b1e407cd31b5649e`; layout receipt SHA256 `cafcfcf076c1dc392186a607b23031940befa890c892005db9e9b1e441d9441d`.

## Android APK actual functional run

A new executable Android bridge calls fixed `Entry.Run`; its complete
composite uses 186 inputs and produces 187 R2R outputs in a 201-file layout.
The actual application is `net.dot.RuneCLR_Budget_cebe2d0c7756`, APK SHA256
`8489551ec2ec05000ad8f49a165fd26d3052b1dc03e1156ff9d5e302f925da1e`.
The dedicated Android API35 x64 emulator is `emulator-5556`. Author DLLs are
copied unchanged after installation. The single actual all-scenario run uses
PID `5393`, nonce `73e7a0305f1042dc8218c982e2b2e4f5`. Java/native/managed
identities agree, initialization/execution/managed/instrumentation exits are
zero, all 15 scenarios and 73 collections complete, and 203 installed entries
match before and after the run. The original
[run receipt](../artifacts/mobile-session-budget/android-budget-apk-20261013-attempt1/run-all-73e7a0305f1042dc8218c982e2b2e4f5/mobile-run.json)
and [aggregate](../artifacts/mobile-session-budget/android-budget-apk-20261013-attempt1/run-all-73e7a0305f1042dc8218c982e2b2e4f5/adapter-evidence/result.json)
are retained. The preflight attempt used a different nonce and never launched
the app; it stopped because the observer assumed a parent native-library
directory rather than resolving its x86_64 child. That failure is preserved.

The [root row audit](../artifacts/mobile-session-budget/root-android-functional-review-20261013-attempt1/results.json)
passes every actual row and 15 negative controls. The historical initial
full-mobile gate remained pending because Android managed Console output
lives in managed.log rather than native.log. The later strict audits below
bind both original streams without changing them. Native/JIT diagnostics show a mapped dynamic
interpreter, trusted MapRunner native JIT compilation and no targeted author
namespace JIT compilation. They do not establish method-entry proof. Although
trusted R2R components were generated, trusted Tier0 JIT is actually observed;
no claim is made that every generated trusted R2R body was selected.
The [189815-byte complete functional archive](../artifacts/mobile-session-budget/android-budget-evidence-20261013-attempt1/android-budget-functional-evidence.zip)
has 21 members and SHA256
`a10ef9b10494150a143fe289a6bf228cc8f6d950f352128b71c5b39c1abe1249`.
The independent strict result
[`results.json`](../artifacts/mobile-session-budget/android-functional-independent-20261013-attempt2/results.json)
and the root result
[`results.json`](../artifacts/mobile-session-budget/root-android-functional-complete-20261013/results.json)
both bind the separate native/managed streams and report `mobileVerified=true`;
they deliberately report `nativeEntryProof=false`.

## iOS method-entry observer attempts

The budget author DLLs were inspected independently without loading them: two
assemblies contain 45 methods, with source hashes and metadata tokens verified.
The first four LLDB observer attempts produced zero valid samples and are kept
as observer failures. In particular, attempt 4 showed that the immediate
`x19,#0x88` in an optimized load is not the DWARF field offset for
`InterpMethodContextFrame.startIp`; treating it as a fixed offset would be
invalid. Attempt 5 completes the same 15/73 adapter run normally and captures
340 valid stub samples, including six of nine required method groups. The
[offline assessment](../artifacts/mobile-session-budget/ios-entry-20261013-attempt5/root-assessment-build-bound.json)
binds every sample to raw LLDB output, independent author PE hashes/MVID/tokens,
the matching Release build/source tree, exact breakpoint and bytecode identity;
four corruption controls reject.
The [38-member archive](../artifacts/mobile-session-budget/ios-entry-20261013-attempt5/evidence.zip)
has SHA256 `5096eeeff5807f7b44acadb36714a5d63d2ec86e028c6d2b0368943cdd5bc055`.

The remaining three child groups have zero samples and 94 observer errors.
`x19` is the interpreter's dynamic stack base; DWARF and the actual instruction
show that `pFrame` must be read from the spill at `[x19+0x88]`, then its typed
`startIp` field read. Using `x19` itself as the context pointer was an observer
error. The original result retains `nativeEntryProof=false`; the passing
offline assessment establishes consistency of the partial samples, not full
coverage. The subsequent attempt below resolves those child groups.

## Successful iOS method-entry run

Attempt 8 uses the corrected frame spill and passes with 147 valid samples,
all nine requested method groups and zero capture errors. PID `4699`, nonce
`01d2131667f946b5ae2ecf79298d854d`, belongs to a fresh debugger launch of the
same installed app with unchanged author IL. LLDB, native initialization,
native execution, managed completion and simulator shutdown exit successfully;
the same run completes 15 scenarios/73 context collections. Attempts 6 and 7
stopped during observer setup and remain recorded separately with shutdown0.

| Requested author method | Entry samples |
| --- | --- |
| Base constructor | 1 |
| Base.OnStart / Base.OnStop | 7 / 20 |
| Normal constructor / OnStart / OnTick | 20 / 20 / 60 |
| FiniteCleanup.OnTick | 1 |
| Private.Helper.Finite / nested delegate | 1 / 1 |

The actual child dispatch instruction sequence resolves the frame spill136,
with the matching DWARF location active at the preceding ReInit state and
typed `startIp` offset8. Each sample binds loaded Module MVID, collectible
MethodTable, MethodDesc token, independently inspected author PE hash and
bytecode header/first opcode to the exact native breakpoint.
The [root assessment](../artifacts/mobile-session-budget/ios-entry-20261013-attempt8/root-assessment.json)
and [independent assessment](../artifacts/mobile-session-budget/ios-entry-20261013-attempt8/independent-assessment.json)
re-parses the raw DWARF and LLDB samples, binds the Release build/source tree,
and rejects four token/PC/MVID/bytecode corruption controls. It reports
`nativeEntryProof=true` for this sampled scope.
The [70277-byte archive](../artifacts/mobile-session-budget/ios-entry-20261013-attempt8/evidence.zip)
has 38 members, SHA256
`5a877440225e15d52ceca00c250f17332df3def09d19c96b2aaa3aeb989905f0`.
The executed driver SHA256 is
`19672c99bede524767a0095466237bb88cae537bc43b8cddd434d13a194b1c36`;
the current driver additionally strengthens instruction-count validation and
clarifies scope wording without changing frozen evidence.

These are entry samples for the requested groups, not a complete invocation
capture, every budget scenario's method proof or physical iOS execution.
The recorded MethodTable belongs to the MethodDesc owner; no independent
receiver MethodTable comparison was performed. Sampling stops after all nine
requested groups appear.

The later [Android budget entry acceptance](android-budget-entry-acceptance.md)
passes178 samples across all nine requested groups, zero observer errors and
independent/root raw reviews. The same run completes15/73 and203 unchanged
installed hashes; a separate same-APK gate-off run strictly passes15/73.
These samples are not complete invocation coverage. Relevant unchanged
lifecycle/upstream controls and physical-device acceptance remain next.
The later [Android debugger preparation](android-budget-entry-preparation.md)
now passes actual attach/read/detach and resumed15/73 execution on a fresh
gated APK with unchanged managed/runtime inputs. Matching Release symbols are
downloaded and verified; the subsequent entry record completes the requested
sampled method groups.
