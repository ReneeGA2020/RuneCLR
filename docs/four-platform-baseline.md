# Four-platform performance baseline

Status on 2026-10-18. The approved order is native shared-object composition,
frozen four-platform no-deadline measurements, then an interpreted UGC callback
deadline and matched OFF/ON measurements. Physical devices remain deferred;
iOS simulator and Android emulator work is authorized.

The native graph has scoped Windows acceptance (archival/local evidence: `../artifacts/lead-native-graph-acceptance-20261018hv/ACCEPTANCE.md`).
The portable semantic freeze (archival/local evidence: `../artifacts/lead-performance-example-freeze-20261018hw/FREEZE.md`)
and functional repair review (archival/local evidence: `../artifacts/lead-portable-repair-review-20261018il/REVIEW.md`)
provide common workloads. The formal four-platform execution baseline is open.

Four-platform descriptive warm and direct-first-use coverage is complete by
scoped Lead acceptances. The source-linked consolidation (archival/local evidence: `../artifacts/four-platform-descriptive-performance-20261018/REPORT.md`)
contains exact Fraction JSON/CSV:1008 retained warm samples,105 child first-use
intervals,6 separate Windows parent-ready windows and480 first-use functional
rows. This is not a mode-qualified baseline, ranking or physical-device result.

## iOS Same-Workload R2R Follow-Up

The subsequent Lead-accepted iOS simulator package comparison (archival/local evidence: `../artifacts/lead-ios-r2r-comparison-acceptance-20261018/ACCEPTANCE.md`)
precompiles the same25-group business IL and compares it with a pure-IL control
on the same machine/runtime. Four actual native entries bind Auto, ArrayRead,
AbstractCall and AbstractA.Calculate to the final composite. Nine applications
completed, with1050 formal observations,450 warmups and288 original gate rows.
The full25-row table (archival/local evidence: `../artifacts/iossim-access-r2r-comparison-bocx5e-20261018/REPORT.md`)
and exact data (archival/local evidence: `../artifacts/iossim-access-r2r-comparison-bocx5e-20261018/exact-statistics.json`)
give descriptive IL/R2R median ratios7.82-204.81 across these workloads.
Original iOS benchmark workloads were late IL without workload R2R bodies;
default never guaranteed workload R2R. This new comparison includes composite
optimization, layout and loading-path differences; it is not isolated call
overhead, all-method qualification, downloaded R2R or physical-device evidence.
The older four-platform results and original mode labels remain unchanged.

## Accepted Access, Collections And Dispatch Extension

The separate25group extension has
scoped Lead acceptance (archival/local evidence: `../artifacts/lead-access-collections-acceptance-20261018/ACCEPTANCE.md`).
Its immutable report and readable medians (archival/local evidence: `../artifacts/access-collections-performance-bocx5e-20261018/REPORT.md`),
exact Fraction statistics (archival/local evidence: `../artifacts/access-collections-performance-bocx5e-20261018/reporting-r3/statistics.json`),
pooled CSV (archival/local evidence: `../artifacts/access-collections-performance-bocx5e-20261018/reporting-r3/pooled.csv`)
and per-PID CSV (archival/local evidence: `../artifacts/access-collections-performance-bocx5e-20261018/reporting-r3/per-pid.csv`)
cover field/property readwrite, array/List access and enumeration, integer and
ordinal-string dictionaries, direct/virtual/abstract/interface dispatch,
single/alternating-target delegates and both host/script loop directions.
The report's original pending-review wording is historical; the linked Lead
acceptance records the subsequent descriptive disposition.

Six request lanes remain separate: Windows default/selective-author, Mac
default/selective-author, Android emulator default and iOS simulator default.
All22 products completed: Windows7 + Mac7 + Android4 + iOSsim4. Each platform
has one untimed25group check; each request has three measured PIDs. Per PID,
each group has3 warmups and7 formal samples,262144 logical operations per
interval. Totals are3150 formal samples,1350 warmups,100 untimed workload
checks and4644 new rows, plus704 original32row lifecycle-gate records.
The150 pooled and450 per-PID distributions include exact seconds and
ns/logical-operation statistics and retained allocation/GC observations;
Lead independent math (archival/local evidence: `../artifacts/lead-access-independent-statistics-20261018/ADJUDICATION.md`)
and evidence checks (archival/local evidence: `../artifacts/lead-access-collections-evidence-check-20261018/receipt.json`)
support this scope. The older1008 warm samples and105 child first-use intervals
remain a distinct accepted baseline; this extension neither replaces nor pools
with them or the6 Windows parent-ready windows.

Request differences and iOSsim access/dispatch costs depend on the workload,
not a uniform platform multiplier or an established execution mechanism.
Default/selective-author remain unproven-selection requests; the desktop
selective filter is Access.Workloads!*. Normal callee inlining/devirtualization
is allowed. Host-to-script and script-to-host have different loop/data-access
scopes, not isolated symmetric transition costs. Hardware/runtime/builds differ,
including Windows Checked native bytes and the ARM64 simulator composite.
No ranking, native-versus-interpreter ratio, causal diagnosis, physical-device
result or formal method-mode qualification follows.

The accepted limitations (archival/local evidence: `../artifacts/lead-access-collections-acceptance-20261018/ACCEPTANCE.md#preserved-limits`)
retain mobile bridge-deps omissions; command-time Python identities without a
separate earlier Windows/Mac Python binary seal; Android resolved-tool rather
than entire SDK/JBR sealing and line-normalized builder child streams. Retained
remote/installed snapshots are recorded identities, not current requery.
Mobile managed/native/transport success is distinct from unknown app OS
directwait/exit; native process-return markers and ADB/simctl0 do not supply it.
Successful descriptive measurements are accepted within these limits; execution
proof, formal four-platform baseline and deadline work remain open.

## Current platform status

| Platform | New portable functionality | New timing | Remaining work |
| --- | --- | --- | --- |
| Windows x64 | Functional gates and six first-use32-row gates reviewed | 336 warm samples,42 child intervals and6 separate parent windows; scoped accepted | Execution-mode evidence; actual native image matches Checked PDB despite Release-named directory |
| macOS ARM64 | Fresh ten-process campaign passes its own gates; old snapshot separate | 336 warm samples and21 child intervals; independent review and scoped Lead acceptance complete | Execution-mode evidence and historical build-provenance limits; no old-gap backfill |
| iOS simulator ARM64 | Warm untimed gate has32 records; new three-app first-use campaign has96 records | 168 warm samples and21 direct first-use intervals; independent review and scoped descriptive acceptance complete | Execution-mode evidence and outermost bootstrap wait gap; historical broad timeline gate failure retained, normal output append is not a blocker |
| Android emulator x86_64 | Warm untimed gate has32 records; new three-app first-use campaign has96 records | 168 warm samples and21 direct first-use intervals; independent Orca review and scoped Lead acceptance complete | Actual execution-mode evidence and broader timing coverage remain open |

## Historical Mac Preparation And Recovery

The following describes earlier preparation, not the current measured campaign.
Mac attempts1-3 are retained failures, not usable runtime deliveries. Attempt3
could not discover an installed ICU header: the
Lead reproduction (archival/local evidence: `../artifacts/lead-mac-icu-discovery-review-20261018iv/REVIEW.md`)
isolated semicolon versus colon in the environment CMAKE_PREFIX_PATH. The
attempt4 contract (archival/local evidence: `../artifacts/lead-mac-cmake-environment-repair-task-20261018iw/TASK.md`)
permits one unchanged-source rebuild after discovery preflight.
Attempt4 has now succeeded: child96624 direct wait0, watchdog=false. The
Lead build/output review (archival/local evidence: `../artifacts/lead-mac-attempt4-runtime-review-20261018/REVIEW.md`)
retains the full original log and verifies ARM64 outputs/framework copies.
Command-record rewrite and incomplete environment/tool closure remain declared;
strict launch-provenance and runtime functional acceptance are not established.
The next isolated adapter needs its own complete prelaunch freeze.
The first portable adapter (archival/local evidence: `../artifacts/macos-portable-harness-cc7q-20261018/review.md`)
has now terminated with two failures: default18961/-6 cannot resolve
PortableHost; selective18993/90 forwards --diag to the public entry, and its
dyld provider fails to load. The
Lead failure review (archival/local evidence: `../artifacts/lead-macos-functional-failure-review-20261018/REVIEW.md`)
reproduces the argument defect offline and retains both results. The old
closure covers only four framework files. A
separate repair task (archival/local evidence: `../artifacts/lead-macos-functional-repair-task-20261018/TASK.md`)
requires complete closure and static/native readiness before at most two new
functional products; the old allowance remains exhausted. At that checkpoint,
final Mac adapter and timing acceptance remained open.
The repair Worker subsequently ended abnormally before final delivery. A
Lead recovery check (archival/local evidence: `../artifacts/lead-macos-repair-recovery-20261018/RECOVERY.md`)
finds two already-completed repair processes19842/19847, each direct wait0 and
32 original records matching stdout, in its retained records.b64 ZIP. This is
a recovery checkpoint, not functional acceptance. Both new repair slots are
consumed; resume only evidence finalization/strict offline checks, never a
replacement product. Original failed runs18961/18993 remain separate.
The independent Orca raw review (archival/local evidence: `../artifacts/macos-recovered-functional-review-bocx5e-20261018/review.md`)
is now terminal. Lead raw-functional adjudication (archival/local evidence: `../artifacts/lead-macos-recovered-raw-adjudication-20261018/ADJUDICATION.md`)
verifies its99-file delivery,68 original pins and25 ZIP entries unchanged and
accepts only the two recovered functional results. Missing full prelaunch/tool/
runtime/SSH history, inherited inner config/parent labels and remote-payload
byte availability remain explicit limits. That old candidate does not fill
historical gaps or authorize extra repair starts. The separately frozen new
measured campaign below supersedes the pending timing status.

## macOS Descriptive Warm And Direct First Use

The fresh delivery (archival/local evidence: `../artifacts/macos-complete-performance-bocx5e-20261018/README.md`)
has ten successful processes35542..35551: one check, six interleaved default/
selective-author warm measurements and three default first-use runs.
Scoped Lead acceptance (archival/local evidence: `../artifacts/lead-macos-complete-performance-acceptance-20261018/ACCEPTANCE.md`)
follows independent Orca review/correction and separate Lead process, exact
statistics, semantic and archive checks. It accepts336 warm samples and21
direct intervals/96 functional rows, not the old final acceptance draft.

The new1265-input freeze seals sources/launcher/readers, two binary-reference
wrappers, seven unchanged business binaries, configs and private framework/
ICU/OpenSSL closure.681 retrieved inputs were locally rehashed;584 external
pins use real remote before/after guards. Old scoped Mac/runtime inputs stayed
unchanged; original tool/review failures remain. Both requests are unproven-
selection. Macmini9,1/macOS27.0.1/ARM64 data is not phone, disk-cold, all-Release
native or per-method execution evidence. Complete distributions are in the
consolidation (archival/local evidence: `../artifacts/four-platform-descriptive-performance-20261018/REPORT.md`).

The iOS adapter contract (archival/local evidence: `../artifacts/lead-iossim-portable-adapter-task-20261018iz/TASK.md`)
requires a fresh composite/app closure. Three cached runtime hashes alone do
not establish a new app. The new
functional delivery (archival/local evidence: `../artifacts/iossim-portable-harness-bocx5e-20261018/README.md`)
has two actual starts: app17425 returned managed1 because the framework deps
inventory was omitted; repaired app18281 returned managed0 with 32 original
records. Both simctl transports returned0 independently. The
Lead offline check (archival/local evidence: `../artifacts/lead-iossim-portable-review-20261018/REVIEW.md`)
verifies the final2548-file closure,1155 business MethodDefs and repair limited
to deps plus signing bytes. The
independent Orca review (archival/local evidence: `../artifacts/iossim-portable-harness-review-cc7q-20261018/review.md`)
is terminal; scoped Lead functional acceptance (archival/local evidence: `../artifacts/lead-iossim-functional-acceptance-20261018/ACCEPTANCE.md`)
retains the narrower independent entry-file guard and supplements it with
complete Lead guards spanning the review. Each original/final start ledger
matches its own run; the independent stale-ledger label is clarified. Bootstrap
direct-wait gaps and initial truncated inventory remain declared; dyld
observations do not prove per-method execution. A separate iOS timing campaign
has now delivered168 real samples, described below. The
Android functional review (archival/local evidence: `../artifacts/lead-android-portable-review-20261018it/REVIEW.md`)
separates app managed return0, native hosting HRESULTs0 and ADB transport exit0;
app OS exit is unavailable. Its captured managed Console.Out matches the raw
JSONL. Empty managed assembly locations remain null with MVID/component evidence.
No new mobile timing or interpreter execution claim follows from these checks.
The payload equivalence check (archival/local evidence: `../artifacts/lead-platform-workload-equivalence-20261018/README.md`)
confirms seven common business binaries across retained platform payloads. A
separate iOS timing task (archival/local evidence: `../artifacts/lead-iossim-portable-timing-preparation-20261018/TASK.md`)
extends the hardcoded check bridge and creates a fresh trusted composite/app,
then permits one untimed gate and three measured app processes after explicit
dispatch and terminal completion of the Worker's Android timing task. Those
four new starts are now terminal; all historical allowances remain closed.

## iOS Simulator Descriptive Timing Pilot

The Orca Worker delivery (archival/local evidence: `../artifacts/iossim-portable-timing-pilot-bocx5e-20261018/README.md`)
has check app20513 plus measurements20544/20578/20609, each managed0 with
native HRESULT/latched/process-return markers0. Separate simctl transports
direct-wait0; app OS exit remains unavailable. Check32 plus three116-row streams
total380 rows,240 timed intervals including72 warmups, and168 retained samples.

The Lead review (archival/local evidence: `../artifacts/lead-iossim-timing-pilot-review-20261018/REVIEW.md`)
checks849 declared files unchanged,1155 business MethodDefs, final signed
executable identity, eight raw mutations and exact8pooled/24per-PID Fraction
statistics/resource samples.
Independent Orca review (archival/local evidence: `../artifacts/iossim-timing-pilot-review-cc7q-20261018/review.md`)
is terminal. Scoped descriptive acceptance (archival/local evidence: `../artifacts/lead-iossim-descriptive-pilot-acceptance-20261018/ACCEPTANCE.md`)
verifies all851 declared files/entries against both independent guards and
the original Lead IL/static/statistics input set. Independent Worker evidence
covers raw/closure/counts; exact Fraction/type-7 recomputation remains the
Lead's separate result. App OS exit and the outermost bootstrap wait remain
unavailable; no formal execution baseline follows.

Milliseconds per complete workload/session, default request,21 samples/group:

| Workload | Median ms | IQR ms |
| --- | ---: | ---: |
| numeric | 110.849167 | 22.646251 |
| lcg | 11.759667 | 4.888792 |
| scalar | 0.658708 | 0.723417 |
| graph | 0.647958 | 0.447750 |
| allocation | 15.508750 | 10.396000 |
| Empty0 | 0.124250 | 0.011043 |
| Gameplay0 | 0.284250 | 0.016833 |
| Gameplay128 | 3.463375 | 2.656166 |

These are ARM64/iOS27 simulator observations on the recorded Mac host. The
fresh composite includes the new measurement bridge; original business IL and
late modules stay unchanged. Host/CoreLib Location is nonempty in this recipe.
Dyld base/path and separate file hashes do not prove loaded-memory bytes or
per-call execution. Outer SSH bootstrap OS-parent waits remain a declared gap;
inner supervisor/controller/transport waits are retained. No phone performance,
cross-platform ratio, cold-start latency or deadline claim follows.

The Android timing contract (archival/local evidence: `../artifacts/lead-android-portable-timing-task-20261018/TASK.md`)
extends the existing check-only bridge after the current iOS functional task
terminates. A new default-request pilot permits one untimed gate and three
fresh measurement processes, aiming for 168 actual samples using unchanged
workload binaries. Its static prerequisite check preserves all 1851 parent
manifest entries. The four-start campaign is now terminal with168 actual
samples and no product failure. The original functional task's unused repair
slot remains closed; the new campaign's four slots are also exhausted.

## Android descriptive timing pilot

The Orca Worker delivery (archival/local evidence: `../artifacts/android-portable-timing-pilot-bocx5e-20261018/README.md`)
has one untimed app3411 and measured apps3955/4471/4986, each managed0 with
native initialize/execute/shutdown HRESULTs0. ADB transport waits0 are separate;
app OS exit remains unavailable. Each measured process has116 rows and80 timed
intervals:24 warmups and56 samples. There are168 retained samples,8 pooled
groups and24 per-process/workload summaries. All samples have positive ticks.

The Lead offline review (archival/local evidence: `../artifacts/lead-android-timing-pilot-review-20261018/REVIEW.md`)
verifies1517 declared files unchanged, replays the original transport/functional
checks with ten rejected mutations, and independently recomputes exact Fraction
distributions and resource samples.
Independent Orca review (archival/local evidence: `../artifacts/android-timing-pilot-review-cc7q-20261018/review.md`)
is terminal. Scoped descriptive acceptance (archival/local evidence: `../artifacts/lead-android-descriptive-pilot-acceptance-20261018/ACCEPTANCE.md`)
verifies all1519 declared files/entries against both review guards and the
original Lead exact-statistics inputs. Independent Worker review covers raw/
functional/closure checks; exact Fraction/type-7 recomputation remains the
Lead's separate result. Neither channel establishes a formal execution baseline.

Milliseconds per complete workload/session, default request,21 samples/group:

| Workload | Median ms | IQR ms |
| --- | ---: | ---: |
| numeric | 3.462415 | 0.083756 |
| lcg | 0.085457 | 0.007947 |
| scalar | 0.017118 | 0.003276 |
| graph | 0.006433 | 0.000396 |
| allocation | 1.848721 | 0.269063 |
| Empty0 | 0.286518 | 0.017456 |
| Gameplay0 | 2.392975 | 0.155842 |
| Gameplay128 | 2.774286 | 0.181902 |

These are x86_64/API35 emulator observations on the retained3126 runtime, not
phone performance or a native/interpreter comparison. Requests remain
unproven-selection with InterpMode0/R2R1/tiering0. Maps/file hashes observe
CoreCLR/JIT before/after Entry.Run; managed Host/CoreLib Location is empty with
null file hashes and actual MVID. Console.Out capture is managed output, not an
OS pipe; parentPid is controller correlation. Builder child record limitations
remain declared. The source/product/runtime/config freeze and original common
business implementation preserve the same callback/session composite scopes
as Windows; no cross-platform speed ratio or formal execution baseline follows.

## Windows descriptive timing pilot

Implementation ran through an Orca Worker. The
Lead raw/statistics review (archival/local evidence: `../artifacts/lead-windows-timing-pilot-review-20261018ix/REVIEW.md`)
independently recomputed exact tick/frequency distributions from original raw
records: 16 pooled distributions and 48 per-process distributions agree.
The independent Orca review (archival/local evidence: `../artifacts/windows-timing-pilot-review-cc7q-20261018/review.md`)
is terminal. Scoped Lead acceptance (archival/local evidence: `../artifacts/lead-windows-descriptive-pilot-acceptance-20261018/ACCEPTANCE.md`)
accepts the descriptive request distributions, with the raw-count clarification
below. Formal execution-mode/four-platform baseline acceptance remains open.

Seven products ran: one untimed check and three fresh measured processes for
each request, interleaved by process ordinal. All have actual integer exit0
and watchdog=false. Each workload has three warmups and seven samples per
process: 21 samples per request/workload, 168 per request, 336 total. No samples
were discarded. The seven-start allowance is exhausted.

Each measured PID has 80 timed intervals: 24 warmups and 56 actual samples.
Across six PIDs the CSV has 48 workload/process summary rows, eight per PID.
The independent report's 65-row count excludes 15 callback warmup-kind rows;
it is not the full timed-interval count. Its original report remains retained.

Milliseconds per complete workload/session, pooled across three processes;
IQR uses type-7 quantiles. Requests remain separate distributions.

| Workload | Default median ms | Default IQR ms | Selective-author median ms | Selective-author IQR ms |
| --- | ---: | ---: | ---: | ---: |
| numeric | 3.3194 | 0.0082 | 28.7403 | 1.1085 |
| lcg | 0.0854 | 0.0001 | 2.8203 | 0.0471 |
| scalar | 0.0151 | 0.0022 | 1.4398 | 0.0293 |
| graph | 0.0063 | 0.0001 | 1.7719 | 0.0678 |
| allocation | 2.2847 | 0.7363 | 20.5120 | 1.2548 |
| Empty0 | 1.7763 | 0.0916 | 1.5206 | 0.1165 |
| Gameplay0 | 14.5140 | 0.2379 | 5.0099 | 0.3944 |
| Gameplay128 | 15.6025 | 0.6392 | 7.7236 | 0.4650 |

Both requests use the pinned private framework12 with R2R1, tiering0 and
InterpMode0. Selective-author additionally requests
`DOTNET_Interpreter=WarmModule!* RuneCLR.SessionMap!*`. Inner records retain
`unproven-selection`. Loaded native module identities show CoreCLR/JIT in both
requests and the interpreter library additionally in selective-author. Neither
the switch nor library presence proves per-call execution mode. The faster
selective session results also have no execution-mode attribution.

The later symbol preflight review (archival/local evidence: `../artifacts/lead-windows-interpreter-preflight-review-20261018/REVIEW.md`)
independently binds the accepted coreclr.dll RSDS GUID/age to the local Checked
PDB, and rejects the proposed Release PDB. The Release-named testhost directory
does not establish the native build configuration. This zero-product result
does not invalidate the byte-pinned descriptive observations, but they cannot
be presented as an all-Release native performance baseline. An actual-image
Checked-layout entry-witness plan must validate native type offsets before any
new author process; no interpreter execution has yet been observed by that task.

The subsequent Checked-layout attempt (archival/local evidence: `../artifacts/lead-windows-checked-entry-failure-review-20261018/REVIEW.md`)
validated native field offsets but consumed its sole author process in a CDB
command-file failure. There are only two functional rows and an unidentified
first-instruction stub stop; no complete method-entry chain or32-row gate.
Debugger wait0x8007001e, unknown app exit and missing managed return remain
distinct. The old attempt is closed; native-only command protocol controls
must precede any separately authorized future capture.
The subsequent four-slot native control task has not passed that gate. The
Lead transcript review (archival/local evidence: `../artifacts/lead-cdb-protocol-recovery-review-20261018/REVIEW.md`)
found that marker/register/stack reads preceded the native boundary hit and
that debugger quit did not establish the helper's natural exit. The
offline correction adjudication (archival/local evidence: `../artifacts/lead-cdb-protocol-correction-adjudication-20261018/ADJUDICATION.md`)
accepts the Orca Worker's factual correction only: all four old slots are
closed, the old command-file cause remains unresolved, and the command
protocol and interpreter-entry gates remain open. A new native-only script
and strict offline reader must pass static review before another bounded run.
The subsequent readiness-gated single native trial (archival/local evidence: `../artifacts/lead-cdb-native-trial-review-20261018/REVIEW.md`)
has now consumed its one slot. Its launched reader failed closed on actual
lmv/exit-text formats, retaining controller exit1 and null helper-exit fields.
Independent Lead inspection of the unchanged raw records observes capture after
the real export breakpoint, result43 and a matching debugger last-event exit0;
this is supplemental evidence, not a rewritten successful campaign or a helper
OS direct wait. The scoped observation adjudication (archival/local evidence: `../artifacts/lead-cdb-native-observation-adjudication-20261018/ADJUDICATION.md`)
now records terminal independent Orca review of that literal sequence, retaining
the original reader failure. Its claimed mutation matrix is not present in the
delivered script; those control claims are excluded. A complete observed-schema
reader/control implementation remained open then, with no native or author retry.
The subsequent decoder review (archival/local evidence: `../artifacts/lead-cdb-observed-reader-review-20261018/r2/REVIEW.md`)
then reproduced seven equal-length/hash-relinked false accepts; five delivered
negative fixtures rejected only stream length. This decoder is not accepted.
The literal native observation above remains unchanged, and no extra launch
is authorized by either offline result.

The later full-reader adjudication (archival/local evidence: `../artifacts/lead-cdb-full-reader-adjudication-20261018/ADJUDICATION.md`)
now accepts the repaired offline observation reader only, including exact17
Lead counterexample rejections and a variable-length observation positive.
Historical controller exit1/gatefalse/null helper OS wait stay unchanged.
No live interpreter witness, launch or mode upgrade follows; this sidebranch
is separate from completed Mac descriptive measurements.

Warm timing uses `warm-callback-composite-typed-session-boundary`; session
timing uses `load-activate-first-use-run-close-unload-request`. These cover
composite operations, not process startup, pure host-call overhead or a frame
budget. Setup and verification are outside callback intervals; natural
allocation/GC remains inside. Forced diagnostic GC is outside throughput
intervals. Current-thread allocation and process-wide GC are distinct metrics.
Per-process distributions, ranges and resource deltas remain in the
pilot report (archival/local evidence: `../artifacts/windows-portable-timing-pilot-bocx5e-20261018/README.md`).

The timer-boundary check (archival/local evidence: `../artifacts/lead-timing-scope-boundary-review-20261018/REVIEW.md`)
also verifies 480 original intervals including warmups, with diagnostics outside
the inner entry stream. Session manifest parsing and initial package validation
precede the timer. Fresh context creation, assembly identity reads, activation,
callbacks, gameplay checksum logging, resource cleanup and the unload request
are inside it. These actual manifests omit the optional entry hash; no timed
SHA cost is claimed. Verification and forced collection follow the interval.
Cold process startup, separate Start/Tick/Stop timings and eventual retirement
latency remain unmeasured by this pilot.

The existing first-use event windows (archival/local evidence: `../artifacts/lead-windows-first-use-event-windows-20261018/REPORT.md`)
provide diagnostic clues from the same six processes, without new performance
samples. For example, the package-read marker window is about 617-664ms and the
first-Tick marker window about 10ms. Event serialization/write/flush and earlier
initialization affect those windows; they are not accepted pure operation or
cold-start latencies. A dedicated first-use run needs direct operation timers
and deferred reporting under a separate source freeze and product allowance.
The original 336-sample acceptance and current mobile tasks stay unchanged.

## Windows Direct First-Use Timing

The scoped first-use acceptance (archival/local evidence: `../artifacts/lead-windows-first-use-acceptance-20261018/ACCEPTANCE.md`)
now covers six new fresh processes, three per request, implemented and reviewed
through Orca Workers. There are42 direct child operation intervals,6 separate
parent pipe-ready windows and192 original functional rows. All six processes
have direct integer exit0 and watchdog=false. The six-start allowance is exhausted.
Lead verified245 candidate files, all48 observations and16 exact distributions.
The independent review's original frequency-as-summary error is retained; its
separate correction (archival/local evidence: `../artifacts/windows-first-use-review-correction-cc7q-20261018/receipt.json`)
now agrees with the original raw and candidate statistics.

| Operation | Default median ms | Selective-author median ms |
| --- | ---: | ---: |
| module load | 8.4689 | 8.2785 |
| module activation | 0.7462 | 1.1182 |
| first numeric call | 4.3003 | 31.7497 |
| package read | 1740.7875 | 1631.2945 |
| session start | 139.2027 | 128.0368 |
| first tick | 11.1943 | 11.9627 |
| session stop | 24.7994 | 19.9829 |
| parent launch to pipe-ready | 844.5325 | 797.5265 |

Each group has only three observations; min/median/max are descriptive. Parent
perf_counter_ns and child Stopwatch remain separate clock domains. No cross-domain
subtraction, disk-cold/pure CLR startup or frame-budget claim follows. Prelaunch
hashing can warm filesystem caches and helper JIT/type resolution can precede
the child timers. Stop includes cleanup and an unload request; collection follows.
Requests remain unproven-selection. The authorized reference-document drift and
historical source-manifest omission of launch.py are retained in the acceptance.

## Android Direct First Use

The scoped acceptance (archival/local evidence: `../artifacts/lead-android-first-use-acceptance-20261018/r2/ACCEPTANCE.md`)
adds three fresh Android x86_64 API35 emulator apps, with seven direct operation
intervals and one post-series32-row functional gate per app. Implementation and
independent review (archival/local evidence: `../artifacts/android-first-use-review-cc7q-20261018/review.md`)
both used Orca Workers; Lead independently checked all1426 files,21 original
tick/frequency observations,96 raw rows and seven exact min/median/max summaries.
The three-app budget is exhausted, without smoke, replacement or retry starts.

| Operation | Median ms |
| --- | ---: |
| Module load | 4.5750 |
| Module activation | 20.6084 |
| First numeric call | 3.8839 |
| Package read | 480.9933 |
| Session start | 34.5040 |
| First tick | 2.2063 |
| Session stop | 11.1606 |

Each summary contains only three observations. The direct series returns before
verification/diagnostic GC and the unchanged Entry.Run gate. Numeric32760817287,
one-tick checksum3620,72 resources created/released,0 remaining and after-stack
collection pass. ADB direct wait0/watchdogfalse, managed return0 and native
HRESULT0 remain distinct; app OS exit is unknown. No parent startup window was
measured. Caches are uncontrolled and helper JIT/setup can precede timers.
Package read and session operations retain their declared composite boundaries.
Inherited builder records and late source/report supplements retain their
provenance limits. These observations do not establish phone/disk-cold/pure
startup/frame-budget performance or interpreted execution.

## iOS Simulator Direct First Use

The scoped acceptance (archival/local evidence: `../artifacts/lead-iossim-first-use-acceptance-20261018/r1/ACCEPTANCE.md`)
adds three fresh ARM64 simulator apps,21 direct operation intervals and96 original
functional rows. Implementation and independent review (archival/local evidence: `../artifacts/iossim-first-use-review-cc7q-20261018/REVIEW.md`)
used separate Orca Workers. Lead verified831 candidate and760 preparation files;
all seven groups of three tick/frequency observations and exact min/median/max
agree with the independent calculation. The three-app quota is exhausted.

| Operation | Median ms |
| --- | ---: |
| Module load | 0.949042 |
| Module activation | 1.856416 |
| First numeric call | 164.074667 |
| Package read | 37.401167 |
| Session start | 9.160458 |
| First tick | 0.339959 |
| Session stop | 0.743459 |

The original remote timeline gained9413 bytes of campaign events; its35981-byte
prelaunch prefix is exact. The historical broad all-remote-files immutability
gate failed and remains preserved, not retroactively all-guards-equal. Normal
append-only owned output logs are permitted and do not block descriptive
measurements; input freezes are distinct. Other original remote files, measurement
freeze, signed app, source, runtime and business bytes remain unchanged. The
earlier preparation ZIP timeline34949 bytes precedes upload completion.

Each series returns before independent verification/diagnostic GC and the one
unchanged32-row gate. Numeric32760817287, one-tick checksum3620,72created/released,
0remaining and after-stack collection pass. simctl direct wait0/watchdogfalse,
managed return0 and native markers remain separate; app OS exit is unknown.
Caches are uncontrolled, helper JIT/setup may precede timers, and inherited
business logging is included. No parent startup window, phone, disk-cold, pure
startup, frame-budget or execution-mode claim follows. The formal baseline is open.

## Descriptive Coverage Complete; Formal Gates Remain

The coverage check (archival/local evidence: `../artifacts/lead-baseline-remaining-coverage-20261018/COVERAGE.md`)
keeps the original stage2 gate separate from the current eight-group descriptive
pilots. Windows has336, Mac336, Android168 and iOS168 scoped-accepted descriptive
samples. The linked coverage check
predates the new iOS timing delivery; its ios0 count is a historical snapshot.
Mac's fresh frozen ten-process campaign now has scoped descriptive acceptance,
separate from its older recovered snapshot. Sample counts remain platform/
request-specific and cannot be pooled into one distribution.

The warm pilots do not establish cold process/loading latency or per-call
execution lanes. Windows, Android and iOS simulator now have scoped direct
first-use increments above; Mac now also has21 accepted direct intervals.
Actual execution-lane evidence remains open on these exact timing images.
Earlier marker windows remain diagnostic.
The prepared first-use latency contract (archival/local evidence: `../artifacts/lead-first-use-latency-preparation-20261018/TASK.md`)
specifies the implemented Windows-first increment: seven direct child operation intervals
and a separate parent-clock launch-to-ready pipe window, using unchanged
business binaries. The contract itself authorizes no starts; implementation
required a separate Orca dispatch. Its six-process budget is now exhausted and
separate from exhausted warm pilots;
fresh-process first use does not mean cold filesystem caches. Android's separate
three-app first-use budget is also exhausted, as is the iOS simulator three-app
budget. Mac's ten-process warm/first-use budget is exhausted as well;
per-call execution evidence remains separate work.
The prepared Mac timing task (archival/local evidence: `../artifacts/lead-macos-portable-timing-preparation-20261018/TASK.md`)
defined the bounded implementation now completed by the fresh campaign and
independent/Lead review. It is not dispatched by this document and
cannot turn a failed repair into permission to measure. No deadline source
implementation is started by these preparations.

The minimal wrapper binary-references the unchanged public Entry.Run and late
assemblies. Runtime identity diagnostics bracket that entry outside its inner
timed intervals. Source SDK11 RC2 is separate from product framework12.
Semantic, compiler, source, product, runtime, config and environment guards
surround builds/runs. The complete final evidence entry is
final-receipt.json (archival/local evidence: `../artifacts/windows-portable-timing-pilot-bocx5e-20261018/final-receipt.json`)
and final-delivery-files.json (archival/local evidence: `../artifacts/windows-portable-timing-pilot-bocx5e-20261018/final-delivery-files.json`);
the earlier delivery snapshot is retained as historical. No formal native,
interpreter or four-platform execution baseline is accepted by this pilot.

## Deadline stage after the baseline

The callback wall-clock deadline is not implemented. Existing instruction
budgets, HTTP deadlines and test-process watchdogs do not implement it.
The source readiness review (archival/local evidence: `../artifacts/lead-deadline-source-readiness-20261018hm/READINESS.md`)
and clock review (archival/local evidence: `../artifacts/lead-deadline-clock-review-20261018hs/CLOCK.md`)
identify enforcement points and remaining implementation decisions.

1. Descriptive review and adapters now cover all four platforms. Establish
   method-bound execution evidence against exact images/runtime/layout and
   functional gates before mode-qualified comparisons. Preserve source/runtime/
   config freezes; switches/library presence never upgrade unproven-selection.
2. Implement a coarse monotonic callback deadline for untrusted interpreted
   UGC, with host-owned activation, an irreversible terminal latch and safe
   CLR unwinding. Trusted host/framework code remains unlimited. Cover catch
   attempts, construction, cleanup, reentry/concurrency and finalizer policy.
   Polling does not interrupt arbitrary blocking native calls.
3. Preserve the original baseline and compare deadline OFF/ON on the same new
   runtime. Measure ordinary overhead, expiry overshoot and fresh-session
   recovery using unchanged workloads/checksums and explicit clock backends.

The existing actual [100/1000 batching experiments](budget-batching-experiment.md)
and [mobile measurements](mobile-batch-measurement.md) remain evidence for
instruction charging. They do not select a wall-clock polling interval or
replace the deadline OFF/ON experiment.
