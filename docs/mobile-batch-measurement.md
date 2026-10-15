# Mobile Batch Measurement

The actual desktop N100/N1000 comparison is complete in
[the best-exact experiment](budget-batch-best-exact.md). Mobile functional
acceptance and iOS initial method entries are recorded in
[the mobile build record](mobile-batch-builds.md). This follow-up uses the
unchanged long Kernel.Execute author IL to observe complete batches and measure
callback costs on the matching mobile runtime. Actual iOS simulator and Android
x64 emulator timing runs are now available below; physical-device runs remain
outstanding.

## Scalar Ledger Review

The [standalone reviewer](../eng/assess-mobile-batch-kernel.py) checks the frozen
long-kernel observation: exact PID/nonce, author bytes, shared contract
identity/MVID, supplied trusted component hash, architecture, checksums,
2100016 dispatches per callback, three warmups, complete post-frame collection
and eight retired getter rejections for configured budgets. It rejects JSON
booleans where counters must be integers, duplicate JSON fields and promoted
native/mobile/timing claims. A mobile R2R contract component must be bound by its
own file hash and layout provenance; it is not expected to equal its raw IL.

The [actual offline replay](../artifacts/mobile-budget-batching/kernel-scalar-assessor-controls-20261015-attempt2/results.json)
passes two retained Windows observations, eight callback rows, two collections
and 54 rejection controls. The
[control driver](../eng/verify-mobile-batch-kernel-assessor.py) checks original
process records, raw completion streams and input bytes without rerunning the
desktop benchmark. Both new tools parse as Python3.9. The first invocation used
the machine's Python2.7 alias and failed before creating results; use py -3.

~~~powershell
py -3 -B eng/verify-mobile-batch-kernel-assessor.py --output <fresh-output>
py -3 -B eng/assess-mobile-batch-kernel.py --receipt <raw-observation.json> --mode high-budget --nonce <32-hex-nonce> --pid <owned-pid> --samples 1 --platform iossimulator.arm64 --component-hash <actual-trusted-R2R-contract-sha256> --output <fresh-review.json>
~~~

Supplied process and component identifiers do not prove executable provenance.
The application controller must bind the original launch arguments/settings,
installed components, loaded native image, author transfer and actual exit.
Scalar ledger correctness alone does not establish full-batch cadence.

## Actual Settlement Capture

Capture the current runtime's actual RecordBatch entry for N100 and N1000. Bind
the meter, active Kernel.Execute frame, original MethodDef/MVID and loaded
author path. Inspect current native bytes and DWARF/caller unwinding rather
than carrying forward a previous runtime's offsets. Retain actual full batches
equal to the selected interval and partial batches strictly between zero and
that interval. The arithmetic remainder for 2100016 dispatches is16 in both
configurations; inspect the real partial settlement rather than substituting
this calculation for a sample. Required host/framework transitions can force
additional partial settlements.

The subsequent [actual iOS long-kernel capture](mobile-batch-builds.md#ios-long-kernel-settlements)
now passes N100 samples100/100/14/14 and N1000 samples1000/1000/14/14, with
normal exit, exact callback ledgers and same-process recovery. The actual
partial settlement is14 in both lanes, not the arithmetic remainder16.
Independent raw review checks eight actual samples and rejects twelve altered
samples; this establishes cadence separately from the pending timing runs.

Disable covered breakpoints so a long callback can complete. Native entries,
raw sampled counts, ledger agreement, target exit and simulator/debugger cleanup
belong to the capture receipt. Timing under this debugger is excluded from
performance results.

## Independent Callback Timing

Use a separate trusted timing adapter with the same original author IL and
shared contract. Place a monotonic Stopwatch around only the direct delegate
call. Native ledger getters, JSON, checksum assertions, loading/unloading and
diagnostic collection stay outside the timed region. Retain raw start/end ticks,
elapsed ticks and frequency so the callback duration can be recomputed.

The [new timing adapter](../eng/mobile-batch-timing-probe/Entry.cs) and
[preparation driver](../eng/prepare-mobile-batch-timing.py) now have frozen
[inputs](../artifacts/mobile-budget-batching/timing-inputs-20261015-attempt1/input-manifest.json).
Their small Windows sanity passes two fresh processes/eight callbacks/two
collections at N1000, including the matching meter-free control. The author's
original IL remains unchanged. The driver's offline controls replay actual
receipts and reject91 altered timing/ledger/binding values plus five source
scope mutations; synthetic lane/architecture checks are explicitly not runs.
The [independent root review](../artifacts/mobile-budget-batching/root-timing-input-review-20261015-attempt1/results.json)
checks ten frozen files/twelve archive members, actual process arguments, raw
streams, ticks/frequency and ledgers, and rejects20 further altered receipts.
The [standalone timing reviewer](../eng/assess-mobile-batch-timing.py) recomputes
durations and removes warmup rows while reusing the strict scalar reviewer.
Neither small sanity provides a performance ratio or mobile result.

All profiles use PhaseAcquireLoad=1, identical Release native/CoreLib/compiler
and trusted/author products, and three callback warmups. The best exact path
requires BatchInterval=0; interval1 does not enable the derived ledger path.
CLR DWORD values are hexadecimal strings.

| Profile | BatchInterval | DerivedLedger | Meter mode |
| --- | --- | --- | --- |
| Best exact | 0 | 1 | High budget, with matching no-config control |
| N100 | 64 | 0 | High budget, with matching no-config control |
| N1000 | 3e8 | 0 | High budget, with matching no-config control |

For each platform, run exact-before, N100, N1000, exact-after in sequence. Each
profile has two fresh process pairs, reversing no-config/high-budget order in
the second pair. Nine measured callbacks per process give16 processes and144
measured samples, plus48 warmup callbacks. Each no-config process selects the
same interval/derived settings as its paired budget process, but creates no
meter. Check ledgers and post-frame collection for all configured processes.

Keep builds, debugger runs and other timing sessions away from this resource
window. Report pooled warmed callback medians, configured/no-config ratios,
N100/N1000 changes against both exact brackets and exact before/after drift.
Do not include startup or instrumentation-wrapper time. These ratios measure
configured budget overhead against the already instrumented no-config runtime;
they do not measure the entire instrumentation overhead or establish a game
frame budget. Small differences need more evidence before choosing a default.

Physical devices require their own compatible runtime, launch and timing
receipts. Simulator/emulator measurements remain platform experiments.

The [independent iOS application builder](../eng/ios-batch-timing-application.py)
and [sixteen-process runner](../eng/ios-batch-timing-run.py) are now prepared.
Native profile settings precede CoreCLR initialization, and the run alternates
the two meter modes in exact-before/N100/N1000/exact-after brackets. The new
matching timing composite and its sixteen-process run completed with exit0
after the cadence targets/debuggers exited. The following results use actual
raw application/source, process and callback receipts.

## Actual iOS Simulator Timing - 2026-10-15

The independent Release application ran on the Apple M1 iOS27 ARM64 simulator
with the unchanged author IL and matching 3126bbc/710936a native/framework
products. All 16 processes completed, 192 callback rows have exact checksums,
144 measured callbacks remain after 48 warmups, and 16 collectible contexts
retired. Each configured callback records exactly 2100016 dispatches. The owned
simulator is Shutdown and the build/run/transfer processes exited.

The [retained archive](../artifacts/mobile-budget-batching/ios-timing-receipts-20261015-attempt1/ios-timing-review.zip)
contains 605 payloads plus the manifest, including actual signed app/native
bytes, raw composite inputs, build records and all launch/quiet/timing receipts.
Its SHA256 is 34dae8aee1c4866062ff86b1b7b0bccc6e525fe9c674004087ac3bb667052f34.
The [root replay](../artifacts/mobile-budget-batching/root-ios-timing-review-20261015-attempt1/results.json)
independently rechecks original launch settings/native completion logs,
unchanged installed products and post-install author files, 35 process quiet
snapshots, typed ledgers and all raw timestamp deltas/frequency. The
[replay tool](../eng/review-ios-batch-timing.py) calculates medians directly
from receipts and does not use the runner's timing summary.
The [actual product binding review](../artifacts/mobile-budget-batching/root-ios-timing-review-20261015-attempt1/product-bindings.json)
also verifies all 198 signed bundle files and the known matching native,
contract, source commit/tree and frozen application-state hashes; author IL is
absent from the installed trusted bundle.
The [second independent review](../artifacts/mobile-budget-batching/ios-timing-independent-review-20261015-attempt1/review.json)
also binds actual native UUID/platform/file-backed sections and Release
compiler settings, checks the trusted composite inputs and confirms the
timing-scope and process-variance limitations.

The original [root reviewer source](../artifacts/mobile-budget-batching/root-ios-timing-review-20261015-attempt1/reviewer-frozen.py)
is retained with its initial receipt. The current reviewer now accepts an
explicit sample count and frozen runner source hash for repeat experiments.
Its [backward-compatible offline replay](../artifacts/mobile-budget-batching/root-ios-timing-review-20261015-attempt1/parameterized-replay-final.json)
passes the same original 144 samples and additionally checks the exact owned
application launch command. This is receipt replay, not a new timing run.

Each median pools 18 measured callbacks from two fresh processes per mode.
Times surround only the direct delegate call; load, native getters, collection
and startup remain outside the interval.

| Profile | No-config median ms | Configured median ms | Configured / no-config | Configured reduction vs exact before / after |
| --- | --- | --- | --- | --- |
| Exact before | 14.438 | 74.153 | 5.136x | Reference |
| N100 | 13.090 | 23.459 | 1.792x | 68.36% / 69.31% |
| N1000 | 17.848 | 15.942 | 0.893x | 78.50% / 79.14% |
| Exact after | 18.480 | 76.427 | 4.136x | Reference |

This is an actual arithmetic-kernel measurement, but the timing environment
has substantial variance. Exact configured bracket drift is +3.07%; the
no-config bracket drifts +28.00%. The exact-before no-config process medians
are 10.210/18.815ms. N1000 paired process ratios are 0.797x and 1.144x, on opposite
sides of 1. Its pooled 0.893x ratio does not establish that budgeting accelerates
execution. Likewise, its observed 32.04% lower configured median than N100
needs a repeat with a steadier baseline before being treated as a stable gain.
No game-frame or physical-device performance conclusion follows.

Keep best exact as the default and N100 as opt-in. Preserve this first run
including its noisy controls; a future repeated run should report the same
per-process medians and both exact brackets. Subsequent Android full/tail
capture and debugger-free callback timing are recorded below.

## iOS Timing Repeat - 31 Samples Per Process

The [repeat runner](../eng/ios-batch-timing-repeat.py) reuses the identical
signed application, native runtime and author IL. It increases each process
to 31 measured callbacks, retains three warmups and both exact brackets, and
waits 30 seconds after installation/author transfer before timing. No runtime,
application or IL was rebuilt. The actual settling duration is 30.005 seconds.

The [independent repeat replay](../artifacts/mobile-budget-batching/root-ios-timing-repeat-review-20261015-attempt1/results.json)
passes 16 fresh processes, 544 callback rows, 496 measured samples, 48 warmups,
16 collections and 35 quiet snapshots. It checks the original launch/settings,
all raw timestamps and ledgers, unchanged installed/author hashes and actual
settling duration against the frozen runner. The
[new raw archive](../artifacts/mobile-budget-batching/ios-timing-repeat-receipts-20261015-attempt1/verification.json)
has 163 verified payloads; it references the complete first-run application
archive. Its SHA256 is eb3a663a427821a5c56e3ed6adfea6da50d5ae6e2d24f963885ab94578129f39.
Owned app/controller/transfer processes exited and the simulator is Shutdown.

| Profile | No-config median ms | Configured median ms | Configured / no-config | Configured reduction vs exact before / after |
| --- | --- | --- | --- | --- |
| Exact before | 11.601 | 79.705 | 6.871x | Reference |
| N100 | 9.167 | 14.718 | 1.605x | 81.53% / 79.36% |
| N1000 | 8.321 | 12.795 | 1.538x | 83.95% / 82.06% |
| Exact after | 8.343 | 71.324 | 8.549x | Reference |

N1000 paired ratios are now 1.541x/1.537x; the first-run ratio below one did
not repeat. Its two configured process medians are 12.812/12.789ms. N100's
configured medians are 13.949/16.314ms. The repeat's observed N1000 reduction
against N100 is 13.06%, compared with 32.04% in the first run. Preserve both
runs rather than selecting only the steadier rows. Exact configured drift is
-10.51% and no-config drift is -28.08%, so longer sampling and settling did
not remove whole-window variability. These arithmetic-kernel observations
support batching's substantial reduction against exact accounting on this
simulator, while its stable percentage and N1000's extra benefit remain
uncertain. The default/opt-in decision and physical-device limits remain.
The [two-run comparison](../artifacts/mobile-budget-batching/root-ios-timing-repeat-review-20261015-attempt1/two-run-comparison.json)
retains all 640 measured samples and 32 collections across both actual runs.

## Android Long-Kernel Capture

The fresh matching Android x64 Release layout contains 184 trusted IL inputs
and 185 R2R outputs; author IL is transferred after installation. The
[independent static review](../artifacts/mobile-budget-batching/android-kernel-independent-review-20261015-attempt1/review.json)
checks actual native ELF/build-id, contract MVID, 199 products and 10 receipts,
all R2R headers, and original source/input hash bindings. It independently
decodes 343 unsafe Flush call sites among 1032 actual RecordBatch calls.

The two actual debugger captures retain N100 settlements 100/100/14/14 and
N1000 settlements 1000/1000/14/14. Each completes four configured callbacks
and four same-process no-config recovery callbacks, with correct checksums,
2100016 configured dispatches per callback and two collected contexts. The
original controller reviews failed because memory-bundled shared assemblies
have an empty Location, giving loadedContractComponentHash=null. This is an
observer assumption; the original receipts and failures remain unchanged.

The [bundle-aware scalar reviewer](../eng/review-android-batch-kernel-ledger.py)
binds actual application bytes and the 201 installed-file hashes to the
trusted R2R contract/raw IL input separately from the managed shared
identity/MVID acknowledgement. It explicitly retains the absent Location
hash and checks all other fields through the frozen strict scalar reviewer.
The [N100 review](../artifacts/mobile-budget-batching/root-android-kernel-ledger-review-20261015-attempt1/N100.json)
and [N1000 review](../artifacts/mobile-budget-batching/root-android-kernel-ledger-review-20261015-attempt1/N1000.json)
each pass eight callbacks/two collections. Scalar acceptance is separate from
the [completed independent live cadence review](../artifacts/mobile-budget-batching/android-kernel-cadence-independent-review-20261015-attempt1/review.json).
That review verifies actual ELF entry/call bytes and relative targets, native
slide plus the true stack return PC, loaded Kernel metadata SHA/MVID/MethodDef,
active frame/spill/context and the PEAssembly/binder embedded meter for all
eight retained settlements. Observation breakpoints were disabled after
coverage. This establishes the sampled method entry and batch path; it does
not establish an exhaustive dispatch trace or performance.
The [root raw-capture reconciliation](../artifacts/mobile-budget-batching/root-android-kernel-ledger-review-20261015-attempt1/raw-cadence-bindings.json)
checks every completion-bound raw hash, eight sample/active-entry ownership
bindings, original native completion streams and unchanged installed hashes.

Both managed/instrumentation results and init/execute/shutdown HRESULTs are
zero. The debugger's target exit status remains 9 after functional completion;
do not describe these as normal target exit0 runs. Before/after 201 installed
hashes agree. The [owned-resource cleanup](../artifacts/mobile-budget-batching/android-kernel-apk-20261015-attempt1/cleanup-final.json)
verifies the APK uninstalled and owned emulator/forwards absent. Debugger
capture times are excluded from performance; independent Android timing follows
below. Physical-device work remains outstanding.

## Android Timing Preparation

The separate Android timing application is composed from the same
matching native/framework inputs and frozen direct-callback timing host used
by iOS. The intended matrix keeps four profiles, two reversed process pairs,
three warmups and 31 measured callbacks per process, with post-install
settling and no debugger during timing. Build/preflight results do not establish
actual performance; retain original launch, installed product and callback
receipts before reporting ratios.

The [Android memory-bundle timing adapter](../eng/review-android-batch-timing.py)
preserves absent managed Location hashes while supplying separately established
actual bundle-component provenance to the frozen strict timing reviewer.
Its [preparation check](../artifacts/mobile-budget-batching/android-timing-adapter-controls-20261015-attempt1/results.json)
binds actual previously accepted Android APK/installed bytes and passes three
rejection controls using a retained Windows observation with a synthetic
platform adaptation. This is not an Android timing run. Full application,
native-launch and debugger-free process evidence is checked separately below.

## Actual Android Emulator Timing - 2026-10-15

The actual Release APK completed one full debugger-free matrix on the owned
Android x64 emulator: 16 fresh processes, 544 callbacks, 496 measured samples
after 48 warmups and 16 collected contexts. Each profile uses two reversed
no-config/high-budget pairs, 31 measured callbacks per process and identical
matching native/framework/author bytes. Installation is followed by 30 seconds
of settling. Native, managed, instrumentation and CoreCLR HRESULT completions
are zero. The APK, owned emulator and forwards have been removed.

The [whole-run reviewer](../eng/review-android-batch-timing-run.py) replays
original launch settings, 33 quiet process snapshots, 445 hash-bound raw
payloads, actual installed SHA256 streams and executable native mappings,
all callback ticks/ledgers and cleanup. Its small JSON result is retained at
`D:/RuneCLR-Android/timing-run-20261015-attempt2/root-review-final.json`; the
independent direct raw review is at
`D:/RuneCLR-Android/timing-independent-review-20261015-attempt1/review.json`.
The [offline controls](../eng/verify-android-batch-timing-run.py) pass actual
496-sample replay and reject four edited launch-interval, native-mapping,
native-completion and cleanup records, rebinding their payload hashes so the
semantic guard must reject each one. Results are at
`D:/RuneCLR-Android/timing-run-controls-20261015-attempt1/results.json`; no
timing target is rerun by these controls.
Large APK/raw receipts use D: because E: is nearly full. The earlier partial
APK copy (`WinError 112`) and pre-launch quiet rejection are retained; neither
launched a timing target. The quiet rejection came from an idle private MSBuild
node, cleared by private build-server shutdown before this actual run.

Actual APK SHA256 is
`ad5c2d8c1a62379c8c6bbbf91c6c40534ad8c5862a0e94d9a2234bc69024cbed`.
All 201 installed entries agree before/after. The loaded coreclr file maps to
the installed native directory and retains matching native SHA256
`c357ec9c3e8f37a5f12a465b8fdc04d5bb3f25c48c064e15f82f628fcc2de10d`.
The shared memory-bundle assembly's managed Location hash remains null;
separate actual product/input/MVID provenance supplies the contract binding.
Timing maps prove image provenance; sampled interpreter/batch entries come
from the separate cadence captures, not from these debugger-free timing runs.

Each median pools 62 warmed callbacks per profile/mode. The interval surrounds
only the unchanged long Kernel.Execute delegate call. Every configured
callback records 2100016 dispatches and the unchanged checksum.

| Profile | No-config median ms | Configured median ms | Configured / no-config | Configured reduction vs exact before / after |
| --- | --- | --- | --- | --- |
| Exact before | 18.331 | 35.527 | 1.938x | Reference |
| N100 | 18.328 | 20.062 | 1.095x | 43.53% / 42.54% |
| N1000 | 18.602 | 19.875 | 1.068x | 44.06% / 43.08% |
| Exact after | 18.367 | 34.916 | 1.901x | Reference |

The paired process ratios are 1.896/1.977 before and 1.911/1.911 after for
exact, 1.099/1.090 for N100 and 1.077/1.075 for N1000. The exact bracket
drifts +0.19% without a meter and -1.72% with one. These controls are much
steadier than the retained iOS simulator runs and support a substantial
configured-budget reduction for this arithmetic kernel. They compare against
the already instrumented no-config runtime, not an unpatched runtime.

N1000's pooled configured time is only 0.93% lower than N100. Comparing their
two configured process medians gives opposite directions: N1000 is 0.77%
slower in one pair and 1.96% faster in the other. This does not establish
a stable extra benefit from 1000 over 100 or justify changing the default.
Keep exact default/N100 opt-in. Host-call-heavy, allocating, concurrent and
physical-device workloads need their own comparisons; no game-frame claim
follows from this emulator arithmetic result.
