# Mobile Batch Builds

The experimental interval candidate now has matching iOS simulator ARM64 and
Android x64 Release builds, completed on 2026-10-15 (local time). Both use
commit3126bbc9a8851a09ac6435b18a12882bad48f3ee and
tree710936ae1729a5689ab0e0896f3cf722ddd3d31c, composed from Windows batch
d0da7df plus the existing collectible CIDv2 fix. The
[source preparation](mobile-batch-build-preparation.md) preserves the upstream
base and exact ten-patch/38-source inventory.

## Actual Build Results

| Target | Official build | Native/CoreLib verification | Application execution |
| --- | --- | --- | --- |
| iOS simulator ARM64 Release | exit0, 0 warnings/errors, 5:30.63 | ten compile owners, three CoreLib stages, static interpreter/dynamic JIT disabled | five functional processes/168 collections; four-method entry lane/35 collections; two full/tail kernel lanes/four collections |
| Android x64 Release | exit0, 0 warnings/errors, 6:36.29 | six compile owners, three CoreLib stages, typed owner queries/compiler GUID | five functional processes/168 collections; separate four-method entry lane/35 collections |

The original derived-ledger builders remain frozen. The new
[iOS adapter](../eng/ios-batch-interval-build.py) and
[Android adapter](../eng/android-batch-interval-build.py) retain their native
and metadata checks while adding the separate
[actual compile assessor](../eng/mobile-batch-compile-assessment.py).
Actual objects, recorded compiler flags and replayed preprocessing confirm
meter72/alignment8/offset64, the exact 47 safe opcode set, charged computed-goto,
unsafe/trap flushes, exact cleanup and independent batch execution counts.
Android still includes dynamic-code support; it requires the session policy
and actual invocation evidence to establish author interpretation.

Both original product sets and pinned SDK/tool dependencies retain their hashes.
Build drivers and official child processes have exited. The iOS and Android
receipt archives contain 32 and 37 members respectively. The
[root independent review](../artifacts/mobile-budget-batching/root-build-review-20261015-attempt1/results.json)
matches all archive/extracted bytes, source proof, successful exits, critical
receipt hashes and both actual preprocessing contracts. The Android raw
preprocessing was downloaded separately without recompiling it.

Detailed original results:

- [iOS build](../artifacts/mobile-budget-batching/ios-build-receipts-20261015-attempt1/extracted/build/results.json)
- [Android build](../artifacts/mobile-budget-batching/android-build-receipts-20261015-attempt1/results.json)
- [Compile-assessor controls](../artifacts/mobile-budget-batching/compile-assessor-controls-20261015-attempt2/results.json)
- [Frozen adapter review](../artifacts/mobile-budget-batching/mobile-adapter-review-20261015-attempt1/results.json)

The build records prove matching compilation and retained interfaces. The
separate simulator application results below establish functional boundary
and recovery behavior; invocation cadence, timing and physical-device use
remain separate.

## Boundary Application

The [fixed input preparation](../eng/prepare-mobile-batch-boundary.py) wraps
the already accepted Windows fixture in public Entry.Run(string[]), preserving
all method bodies and assertions. Author/contract DLLs remain byte-identical;
the author is absent from the trusted host. Its Release build has zero warnings
and errors. The new wrapper's Windows control passes five processes/168
collections. That control does not establish mobile execution.

The new [iOS application driver](../eng/ios-batch-boundary-accept.py) rebuilds
all trusted components using matching CoreLib/crossgen2 and the frozen original
framework IL. The actual first application build produces 184 R2R components.
Before launch, it exposed a RuneCLR verification-tool issue: codesigning changes
the native hash, but the initial state retained the unsigned source hash.
The corrected driver records signed and source identities separately. Its
rebind phase validates the entire previously signed bundle and writes fresh
launch metadata while retaining the application and original records.
This is our application-recording bug, not an upstream runtime defect.

The first actual simulator attempt runs its initial lane successfully (29 rows,
28 collections, native initialize/execute and managed exit0). Its controller
then rejects the completion marker because iOS Console prefixes managed output
with a timestamp and Session[PID:thread]. The
[root first-lane recheck](../artifacts/mobile-budget-batching/root-ios-boundary-first-lane-20261015-attempt1/results.json)
preserves that failed overall attempt. The corrected parser accepts only the
bare marker or the exact timestamp format with the same PID, still requiring
one marker. Five corruption controls reject trailing text, unrelated prefixes,
wrong PID and duplicate markers. The original app remains unchanged.

The second actual simulator attempt now passes all five lanes: five fresh
processes, 168 completed collections, bounded single-worker terminal outcomes,
same-process recovery and successful owned-simulator shutdown. Its controller
exits0 without a debugger. Framework/host remain R2R and author IL is transferred
after installation. Original failed attempts and signed/unsigned bindings are
retained. The
[actual application result](../artifacts/mobile-budget-batching/ios-boundary-run-20261015-attempt2/extracted/run/results.json)
and [root independent acceptance](../artifacts/mobile-budget-batching/root-ios-boundary-review-20261015-attempt1/results.json)
reconcile all 57 archived receipt members, exact lane/author/PID/settings,
native and managed completion markers, signed/source product bindings,
184 R2R layouts and installed/author observations before and after execution.
Twenty-five altered actual-lane controls reject incorrect overshoot, terminal
catch continuation, uncollected contexts, promoted evidence and wrong authors.
N100/N1000 partial calibration counts match their same-platform exact controls.
The largest native-reported terminal excess in these fixtures is four dispatches
for both intervals; that observation does not tighten the N-1 design allowance.

All five app processes and the launch controller have exited; the owned
simulator is shut down. No native method-entry/cadence sampling or mobile
performance is claimed from these functional receipts.

The [single-lane reviewer](../eng/assess-mobile-batch-boundary.py) retains all
frozen single-worker semantic checks with explicit architecture selection.
Actual native Mach-O platform validation belongs to the controller. Five
Windows receipts/168 collections and 75 rejection controls pass; synthetic
ARM64/Android records establish parser coverage only. The
[signed binding review](../artifacts/mobile-budget-batching/ios-boundary-rebind-review-20261015-attempt1/results.json)
also passes five rejection controls without running a simulator.

Each application process selects its interval before CoreCLR initialization.
The five (configured interval, boundary matrix) lanes are (1,1), (1,100),
(1,1000), (100,100), (1000,1000). CLR DWORD environment settings must be
hexadecimal1/64/3e8. Validate bounded single-worker overshoot, post-frame partial
settlement, catch suppression, finite cleanup, same-process recovery and 168
completed context collections. The simulator's debugger-free functional run
passes; actual entry/cadence sampling remains separate from this evidence.

The [Android read-only preparation](../artifacts/mobile-budget-batching/android-boundary-readonly-preflight-20261015-attempt1/remote-verification.json)
binds seven current runtime products, 180 original framework IL inputs, 28
native support files, one dependency manifest and nine author/host inputs.
That preparation precedes the actual Android stages below.

## Android Application Acceptance

The new [layout driver](../eng/android-batch-boundary-layout.py) and
[APK driver](../eng/android-batch-boundary-apk.py) preserve the old tools. Actual
preflight confirms that the frozen 180 framework IL inputs exclude CoreLib.
Adding current CoreLib, the boundary host/contract and executable bridge gives
184 trusted IL inputs and 185 fresh Linux x64 R2R outputs. The first incorrect
183/184 expectation was rejected before crossgen and is retained as a tool
failure. The executable bridge's final private csc run exits0 without warnings;
its actual argv carries /noconfig. The
[root bridge review](../artifacts/mobile-budget-batching/root-android-bridge-review-20261015-attempt1/results.json)
reconciles its original archive, compiler log and raw-IL entrypoint.

One actual matching composite completes successfully. Native critical products,
SDK/compiler/NDK, 38 source files and original framework inputs remain unchanged.
CoreLib component private methods, fields, MVID and typed owner queries agree
with current CoreLib IL. The
[root layout review](../artifacts/mobile-budget-batching/root-android-layout-review-20261015-attempt1/results.json)
matches all 210 archived files, 209 product/receipt hashes, 185 actual R2R PE
headers, three actual ELF x64 critical images and the actual component MVID.

The first fresh APK runs its initial lane with 29 observations/28 collections
and native initialize/execute plus managed exit0. Its controller rejects missing
synchronous shutdown evidence: the official test wrapper releases resources in
asynchronous onDestroy, and managed Console forwards to Android logging rather
than native stdout. The
[first-lane audit](../artifacts/mobile-budget-batching/root-android-boundary-first-lane-20261015-attempt1/results.json)
preserves that overall failed attempt. The new wrapper shuts down before
publishing the instrumentation result and copies the original completed managed
stream byte-for-byte into native stdout. Handle/domain/mapped-file state resets
make the later onDestroy cleanup idempotent. These are RuneCLR acceptance-tool
issues, not upstream runtime defects.

The second fresh APK now passes all five configured/matrix lanes: five distinct
processes, 169 observations and 168 completed collections. One zero-budget
rejection creates no context. Java/native/managed PID and nonce agree, the actual
hexadecimal settings match, all three initialize/execute/shutdown HRESULTs are
zero and real instrumentation return-code is zero. Late author IL remains
byte-identical and outside the APK; complete installed observations and native
maps remain bound to the matched runtime. The
[actual matrix](../artifacts/mobile-budget-batching/android-boundary-apk-20261015-attempt2/matrix-results.json)
and [independent assessor](../eng/assess-android-batch-boundary.py) establish
termination, catch suppression, finite cleanup and same-process recovery. The
[root acceptance](../artifacts/mobile-budget-batching/root-android-boundary-review-20261015-attempt1/results.json)
replays raw APK/layout/installed evidence and all actual semantic rows, rejects
30 altered receipts, and compares partial calibration counts with the exact
same-platform controls. Both test packages are uninstalled; owned emulator5556
and its PID42160 are verified absent. Failed APKs/receipts remain local.

This functional Android run has no debugger. The separate native method-entry
run below supplements it. Observed full100/1000 settlements, timing and
physical-device execution remain separate from these functional receipts.

## Android Direct Method Entries

Four new android-batch-boundary-entry tools prepare an independent opt-in gated
APK and initial-entry observer using the current ELF/DWARF. The accepted
functional APK and its host/runtime components remain byte-identical; only the
new wrapper adds a bounded pre-initialization gate. The actual new InterpExecMethod
entry is0x3f53a0, using RSI for the context frame and RCX==0 for initial
invocations. This is distinct from the previous increment observer's addresses.

The
[actual capture](../artifacts/mobile-budget-batching/android-batch-entry-apk-20261015-attempt1/capture-9fea138cf1bd41c09a064203ada9c2be/results.json)
records PID3790, ten initial hits and four retained author entries: ShortReturn,
OrdinaryThrow, FiniteProgress and EndlessCatch. Loaded complete metadata bytes,
MethodDef/MVID, collectible ownership, module path and interpreter bytecode
definition agree. After coverage the observation breakpoint is disabled. The
same process completes35 semantic rows and35 collections, with managed and
instrumentation exit0 and all initialize/execute/shutdown HRESULTs zero.

The
[independent root review](../artifacts/mobile-budget-batching/root-android-batch-entry-review-20261015-attempt1/results.json)
replays40 raw hashes and19 original symbol/source payloads, parses the actual
ELF entry bytes, compares native/debug Build ID2673b334e703ea2000e69578ef5a402e650bdb68,
reads original author metadata and embedded cDAC, matches original printed
LLDB samples and rejects eight altered entries. Installed201-item observations
match before and after. Owned application, forward and emulator are removed;
the original runtime and test inputs remain intact.

LLDB observes target exit9 after functional completion. This remains an explicit
debugger observation, not a normal target exit0 claim or a general crash
exemption. The earlier independent debugger-free five-process run remains the
normal functional baseline. Initial entries do not establish first-opcode
sampling, full/tail cadence or performance.

ADB10055 during installation and a controller stdin wait were retained as
experiment-controller failures. ADB recovered without daemon restart; one
archive transfer and direct batch SHA commands then succeeded. No runtime
patch, original APK rebuild or physical-device operation was used to recover.

## iOS Direct Method Entries

The [new preparation tool](../eng/ios-batch-boundary-entry-prepare.py) reads the
current native/DWARF identity, eight actual type layouts, three symbols and four
original author MethodDefs/MVID without starting a target. Its retained first
attempt encounters simctl code405 because the accepted simulator is shut down;
the corrected preparation binds its existing installed author path through
accepted receipts and the simulator metadata without booting it. The
[root preparation review](../artifacts/mobile-budget-batching/root-ios-entry-prepare-review-20261015-attempt1/results.json)
reconciles 79 raw payload files and all layouts/symbols/author metadata.

The [new exact-entry observer](../eng/ios-batch-boundary-entry-capture.py) then
uses a separate simulator with the unchanged accepted signed app and late
author IL. Its 16 offline controls exercise the decoder and reviewer; the
actual capture subsequently passes all four direct methods: ShortReturn,
OrdinaryThrow, FiniteProgress and EndlessCatch. Entry filePC0x28a08c binds the
fresh UUID, actual first64 loaded native bytes and six live DWARF layouts. Each
sample binds x1 context, x3==0, collectible MethodTable, exact loaded Module
path, original MethodDef/MVID and MethodDesc interpreter bytecode ownership.
The observer disables itself after coverage: 376 hits, four retained samples,
zero errors. Target14532 exits0; the same process completes 35 semantic rows
and 35 collections at interval1000, including recovery. Owned simulator
shutdown succeeds and debugger/target/log-stream PIDs have exited.

The [actual capture](../artifacts/mobile-budget-batching/ios-entry-capture-receipts-20261015-attempt1/extracted/capture/results.json)
and [root independent review](../artifacts/mobile-budget-batching/root-ios-entry-capture-review-20261015-attempt1/results.json)
reconcile all 52 raw payloads, original LLDB sample printing, native entry
bindings, ordinary completion and installed/author observations. Eight altered
actual entries are rejected. The original debugger-free five-lane run remains
unchanged. This establishes selected initial interpreter invocations; first
opcode execution, full/partial RecordBatch cadence and timing remain separate.
The small boundary fixture does not guarantee long batches; cadence needs the
separate long-kernel trusted host and late frozen Kernel.Execute IL.

## Long Kernel Inputs

The [portable trusted host](../eng/mobile-batch-kernel-probe/Entry.cs) and
[input preparation](../eng/prepare-mobile-batch-kernel.py) are now ready for that
next experiment. Public Entry.Run(string[]) accepts author path, no-config or
high-budget mode, nonce, sample count and a fresh receipt. It reuses the unchanged
Windows Kernel.Execute author IL and shared contract: 100000 iterations,
checksum12749776 and calibrated2100016 completed dispatches per callback. It
retains scalar rows, unloads before post-frame collection and checks retired
budget getters. The host has no timing, platform affinity or Windows entry-byte
observer.

The frozen [input manifest](../artifacts/mobile-budget-batching/kernel-inputs-20261015-attempt3/input-manifest.json)
keeps author and raw shared-contract bytes separate from trusted host outputs.
The loaded default-context contract binds its exact identity/MVID; a future
mobile R2R component has different bytes and needs its own layout provenance.
The [Windows private-runtime sanity](../artifacts/mobile-budget-batching/kernel-windows-sanity-20261015-attempt2/results.json)
passes two fresh processes, eight callback checks and two completed collections
at N1000 with no timer, plus 20 altered-receipt rejections. The
[root input review](../artifacts/mobile-budget-batching/root-kernel-input-review-20261015-attempt1/results.json)
reconciles unchanged author/contract, zero-warning compilation, archive/manifest
and raw process/ledger receipts. This is new-host preparation, not another
desktop performance comparison or a mobile cadence result. The actual separate
iOS long-kernel application and capture below now use these inputs.

The [best-exact desktop comparison](budget-batch-best-exact.md) still supports
exact metering as default and N100 as an opt-in experiment. Desktop arithmetic
gains do not establish mobile gains, and N1000 is not selected as the default.

The new [long-kernel measurement workflow](mobile-batch-measurement.md) records
separate full/tail capture and debugger-free callback timing. Its strict scalar
reviewer replays two retained actual Windows observations/eight callbacks and
rejects54 altered bindings, ledgers and JSON-type controls. This prepares
independent review of new mobile runs; it does not promote the existing
functional receipts into cadence or performance evidence.

## iOS Long Kernel Settlements

The [independent application adapter](../eng/ios-batch-kernel-application.py)
creates a fresh trusted composite/app with the frozen kernel host and shared
contract. Original author IL is transferred after installation and is absent
from the trusted app. Contract raw IL and actual R2R component are bound
separately by SHA/MVID. The
[actual settlement observer](../eng/ios-batch-kernel-capture.py) now passes two
fresh simulator processes using that application and the same native runtime.

| Actual interval | Full RecordBatch samples | Partial RecordBatch samples | Callbacks / collected contexts |
| --- | --- | --- | --- |
| N100 | 100,100 | 14,14 | 8 /2 |
| N1000 | 1000,1000 | 14,14 | 8 /2 |

Each lane runs four high-budget callbacks with exactly2100016 dispatches per
callback, then four callbacks in a fresh meter-free context in the same process.
Both contexts collect after their invocation frames return; all eight retired
budget getters reject. Both targets exit0 and simulators shut down. The
[independent root acceptance](../artifacts/mobile-budget-batching/root-ios-kernel-cadence-review-20261015-attempt1/results.json)
matches245 original archive payloads, actual printed LLDB samples, eight live
settlements, sixteen scalar callback rows/four collections and twelve altered
settlement rejection controls. Loaded RecordBatch first64 bytes agree with the
current original disassembly, and347 exact partial-gate BL instructions resolve
to the same actual RecordBatch entry0x329d58.

Full settlements bind actual Admit return0x329b3c, live x22 and the unwound
interpreter x19+296 batch local verified by live DWARF. Partial settlements
bind the precise gate, actual LR/return, batch/meter/frame/bytecode, collectible
Kernel.Execute MethodDef/MVID and loaded author path. Actual meter state is
terminal1/phaseAcquire1/derived0/phase0 with the selected interval. Two samples
of each kind complete coverage, then all observation breakpoints are disabled.
The post-capture process/device receipt confirms every owned target, debugger,
controller, build and log process has exited.

The first two observer attempts fail their caller guards because LLDB inserts
inline Flush frames and displays a physical frame's scope PC separately from
the real LR return address. Their original failed capture records remain in
the archive; both targets still exit0 and their independent scalar ledgers pass.
The final observer preserves the exact actual LR/inner return PC and resolves
its file address, using physical frames only for owner, register unwind and
DWARF-local binding. No runtime or managed app rebuild fixes these observer
issues.

The observed partial count is14 in both lanes; total dispatch remainder16 does
not predict it because the interpreter also directly charges instructions at
required boundaries. These are selected real settlement samples, not an
exhaustive trace of every batch or a concurrent overshoot test. Debugger time is
excluded from performance. Two later debugger-free iOS timing runs now have
640 measured callbacks/32 collected contexts in total; actual ratios and
their timing drift are retained in [the measurement record](mobile-batch-measurement.md).
The later [Android timing matrix](mobile-batch-measurement.md#actual-android-emulator-timing---2026-10-15)
now completes496 measured callbacks/16 collected contexts. Physical-device
acceptance remains outstanding.

## Android Long-Kernel Settlements

The fresh trusted Kernel composite and owned APK now complete two actual
debugger captures on the matching Android x64 Release native runtime. N100
settlements are 100/100/14/14; N1000 settlements are 1000/1000/14/14. Sixteen
callback rows/four collections include same-process meter-free recovery.
The [independent actual cadence review](../artifacts/mobile-budget-batching/android-kernel-cadence-independent-review-20261015-attempt1/review.json)
checks current ELF entry/call bytes, true stack return PCs, loaded Kernel
metadata and binder-owned meter for each retained sample. Observations are
disabled once coverage completes.

Android Release inlines Admit and optimizes away a continuous batch-object
location. The observer uses exact RecordBatch SysV RDI/ESI arguments, the
actual stack return PC and the active interpreter frame/PEAssembly/binder
owner instead of reusing the iOS batch-local layout. The sampled full/tail
path is verified; an exhaustive execution trace is not claimed.

The original scalar review rejects null loadedContractComponentHash because
the official APK memory bundle gives the shared assembly an empty Location.
Both original failures remain. [External actual installed component binding](mobile-batch-measurement.md#android-long-kernel-capture)
plus strict scalar replay passes separately, without rewriting either raw
observation or claiming a Location-derived hash. Managed/instrumentation and
native HRESULTs are zero, while both debugger target exit statuses remain 9.
Installed products are unchanged; owned APK/emulator/forwards are cleaned up.
The later Android timing experiment uses a separate adapter without a debugger
and now passes16 actual processes/496 measured samples. See the
[measured results](mobile-batch-measurement.md#actual-android-emulator-timing---2026-10-15).
A [separate device-target iOS runtime build](ios-device-batch-build.md) now
passes native/CoreLib/compiler preparation; it has no physical execution result.
