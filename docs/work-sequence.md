# Work sequence

This sequence follows the [product direction](product-direction.md), clarified
on 2026-10-15: C# iOS hot updates first, UGC management on the same foundation.
The tracker is [Roadmap #11](https://github.com/ReneeGA2020/RuneCLR/issues/11).
An issue stays open until its acceptance evidence exists. Scheduling a task does
not establish that an unperformed experiment has passed.

## Current contribution order - 2026-10-15

1. Complete #2 physical iOS new-IL acceptance when a target is reachable.
   Independently document/build #12's minimal engine-independent trusted-update
   host: load post-build C# IL, call shared host objects, retire and recover.
2. Validate #13's identical business sources in interpreted IL and trusted R2R builds,
   including independently built R2R updateable and non-updateable modules
   running together without requiring one composite image. Verify shared API
   identity, equivalent behavior and actual R2R execution of selected methods.
   First-party modules are trusted and do not inherit UGC's interpreter-only
   policy. On iOS, newly downloaded IL is interpreted; native R2R follows the
   application build/signing pipeline. This work does not depend on #5/#6/#7.
3. Define #14's direct-object/ownership matrix and #15's separate compiler language,
   runtime feature, framework and UGC-policy compatibility. Publish diagnostics
   and an honest supported surface; source syntax follows the selected compiler's
   latest stable C# version independently of the UGC API policy.
4. Integrate one real game's trusted hot-update path: version switching at safe
   boundaries, rollback, errors, callback costs and retention. This is the first
   stage of #9, independent of arbitrary public UGC readiness.
5. Extend #8 events/resources, #7 allocation observation and the remaining
   #4/#5/#6 package/capability/budget boundaries for UGC; then validate the UGC
   stage of #9 and #10 public readiness. Shared host work can proceed earlier.

The [roadmap](roadmap.md) links the dedicated hot-update issues. Desktop
interpreter feasibility, controlled packages, pumping and budget prototypes
already have evidence below; do not repeat them as prerequisites.

## Scope of the retained UGC sequence

The original sequence was arranged on 2026-10-12 and is retained below with
its dated evidence. Its restricted-author rules apply to UGC, rather than
imposing those constraints on every trusted hot-update host.

UGC map code and map-private managed dependencies use interpretation first.
Trusted host/framework code may remain native. Authors submit source or IL;
controlled builds create runnable packages. Future R2R/JIT must preserve the
same restrictions and cannot directly execute author-supplied native bodies.

The user also requested a later naming review: scripts need not live in a
container called a map. Plan the public API/package/documentation rename as a
separate contribution after current platform checks; the replacement terminology
is not selected yet. Existing names do not constrain the intended embedding API.

## Current evidence

The initial [host-pumped lifecycle](host-pumped-sessions.md) is now implemented
as an independent #8 increment: explicit start/tick/stop, host-supplied delta,
automatic failure cleanup and retained-stopped-session collection. Fresh
Windows verification passes 37 lifecycle/84 packaging/15 player cases; required
interpreter lifecycle also passes 37/37. The native pumped 16-case/74-collection
suite demonstrates a single cumulative allowance across six successful host
returns before tick 7 terminates. Synchronous and stock controls remain passing.
The [controlled-package pumped lane](package-execution-tests.md) subsequently
passes 22/22 on Windows stock and required interpretation, with unchanged
15/15 synchronous controls. The later
[controlled-package native-budget lane](controlled-package-native-budget.md)
passes 33/33 with twenty-five native-budget collections and exact cumulative
execution/cleanup accounting. Game-facing events/resources, mobile execution
of this controlled-package combination, and real-device acceptance remain
follow-ups.
The updated [iOS simulator application](ios-pumped-budget-acceptance.md)
separately passes the diagnostic pumped-budget 16-case/74-collection route
with post-install author IL and the current trusted host. Updated Android
applications and physical-device results remain outstanding.

Current checkpoint, 2026-10-15: [fresh-author entry acceptance](ios-fresh-author-entry-acceptance.md)
binds nine selected interpreter method groups in IL compiled after simulator
installation, with 15 budget cases and all 73 contexts collected. The dedicated
open-delegate branch is now covered in a separate
[three-path capture](ios-open-delegate-entry-acceptance.md) with the same nine
method groups and15/73 results. The latest
[read-only device refresh](ios-device-readiness.md) at 06:12 UTC reports zero
reachable physical targets; simulator evidence does not close real-device #2.
The paragraphs below retain the earlier experiment sequence, with later
acceptance links where preparation has advanced.

On 2026-10-14 the matching Windows 099dacd Release budget increment now has
[independent terminal/finalizer/host acceptance](windows-release-budget-acceptance.md),
[complete production functional controls](windows-release-production.md) and
[controlled joined-worker accounting](windows-terminal-concurrency.md).
Respect their sampled-entry and concurrent-snapshot limits. The smallest
[terminal-counter optimization](windows-budget-increment-hotpath.md) now has
separate20405f7 matching Release products,
[execution/cleanup/finalizer/host acceptance](windows-budget-increment-acceptance.md)
and [concurrent/production controls](windows-budget-increment-concurrency.md).
The actual normal admitted machine-code path has five locked RMWs instead of
six. [Bracketed same-machine measurement](windows-budget-increment-performance.md)
now shows14.73-16.06% less budgeted callback time in the fixed kernel, with
identical managed images and312 collections across24 processes. Original099
products and evidence remain intact. Fresh [matching mobile core builds](mobile-budget-increment-builds.md)
now pass on iOS simulator ARM64 and Android x64 Release, with downloaded bound
receipts and exact37-source composition. New [iOS application/entry acceptance](ios-budget-increment-acceptance.md)
passes15/73 and147 samples/nine requested method groups; independent root
review binds actual source/products, installed observations and ARM64 bytes.
New [Android ABI/framework](android-budget-increment-layout.md) and
[fresh APK acceptance](android-budget-increment-acceptance.md) pass15/73 with203
identical installed hashes. An independent frozen-product review also verifies
actual APK bytes, every installed observation and all 73 scenario rows, with
four additional transport corruption controls. New
[Android observer contract preparation](android-budget-increment-entry-preparation.md)
passed matching machine-code/DWARF checks and five rejection controls. Its
subsequent [actual method-entry acceptance](android-budget-increment-entry-acceptance.md)
now records 178 valid samples across nine requested groups, 15/73 functional
acceptance and a separate same-APK gate-off run on the Android x64 emulator.
The requested [Lua count-hook reference](lua-budget-overhead.md)
now passes raw-log review: every1/100/1000 traced instructions cost6.37x/2.49x/2.44x
the no-hook arithmetic median on Windows. Its non-atomic, catchable hook is
not matched terminal enforcement. The requested [batch100/batch1000 experiment](budget-batching-experiment.md)
is now implemented and measured. The [best-exact desktop comparison](budget-batch-best-exact.md)
passes 48 processes/624 collections: batching saves 44% on arithmetic but
regresses 15-17% on entities. The [mobile timing and cadence record](mobile-batch-measurement.md)
includes actual full/tail settlements on both platforms and separate
debugger-free timing. Android configured arithmetic medians fall from
1.90-1.94x the no-config baseline to 1.095x/1.068x at 100/1000; the extra
benefit of 1000 over 100 is not stable, and iOS timing remains variable. Keep
exact accounting as default and N100 opt-in. Representative physical-device
performance and actual device IL loading/retirement remain outstanding.

The later 2026-10-13 [Android session-policy validation](android-session-policy-validation.md)
passes the matching source-built Checked x64 runtime: 24/24 lifecycle, 15/15
controlled-package cases, three collected sample sessions and five core
selection/refusal controls. The required path does not JIT-fallback after a real
compiler refusal and recovers into twenty successfully collected sessions.
The [iOS simulator session-policy validation](ios-session-policy-acceptance.md)
also records the matching runtime experiment. Its separate
[Release refusal/recovery control](ios-session-policy-refusal.md) now passes one
real scoped compiler refusal, refused-context collection and twenty successful
recovery sessions/collections. The [fresh Android Release core assessment](android-session-policy-release-build-assessment.md)
also passes source, compile and frozen metadata checks; it does not establish
APK execution. The later [Release APK transport experiment](android-session-policy-release-entry-preparation.md)
passes matching construction/deployment and debugger attach/detach followed by
twenty functional sessions/collections. That transport receipt retains
entryProofCollected=false. The subsequent [Release native-entry samples](android-session-policy-entry.md)
cover nine fixture method groups, and an independent
[non-debugger Release selection run](android-session-policy-release-functional.md)
passes twenty exact sessions/collections with unchanged installed bytes.
The later [independent Release production and control lanes](android-session-policy-release-production.md)
pass 24/24 lifecycle, 15/15 packages, three sample collections, scoped compiler
refusal followed by twenty successful recovered collections, ordinary JIT and
unmarked fallback on the same frozen APK. Earlier evidence below remains
historical. Physical devices, production/refusal method-entry samples,
fast-dispatch coverage and further execution-boundary controls remain open.

- [#4](https://github.com/ReneeGA2020/RuneCLR/issues/4): the local controlled
  source/IL CLI and versioned managed-IL intake, including the later capability
  increment, now pass 84/84 packaging
  regressions; the existing lifecycle suite remains 22/22. Fresh operator-built
  source/import/source packages also pass collection/static reset on the pinned
  private interpreter with successful callback dumps. See
  [the contract, commands and evidence](controlled-packaging.md). Server approval
  authentication remains open. The [new Android host/profile](android-controlled-packages.md)
  passes 8/8 controlled package cases plus the original 22/22 late-IL suite;
  iOS new-profile deployment and Android interpretation remain open.

- The [iOS R2R investigation](ios-r2r-investigation.md) captures the original
  production PC-zero fault under LLDB. The later [minimal reproduction](ios-r2r-minimal.md)
  identifies stale collectible cached-interface state. The private native
  candidate passes [Debug lifecycle/package comparisons](ios-r2r-fix-validation.md),
  [explicit interface regressions](ios-r2r-patched-regressions.md) and
  [matching Release package acceptance](ios-r2r-release-packages.md). The
  [upstream defect register](upstream-bugs/README.md) tracks this confirmed
  official-source defect as RCLR-UP-001 with a local fix and an unsubmitted
  report draft; official-fix replacement still requires independent regression
  review. This does not establish physical-device acceptance.

- [#5](https://github.com/ReneeGA2020/RuneCLR/issues/5): the
  [initial static gameplay policy](capability-policy.md) checks every entry/private
  IL image at packaging and versioned loading. Its 25 focused regressions cover
  allowed sessions, denied APIs/unsafe routes, recomputed hashes, profile
  downgrade and identity spoofing. Runtime-backed interpreter selection, hard
  budgets and target-device acceptance remain open; this does not close #5.

- [#1](https://github.com/ReneeGA2020/RuneCLR/issues/1): the pinned Windows
  interpreter lifecycle baseline has passed locally, including twelve cases,
  private dependencies, generic state and a post-host-build map. See
  [the detailed evidence](interpreter-experiment.md).
- [#3](https://github.com/ReneeGA2020/RuneCLR/issues/3): Release synthetic
  kernels have been measured against Lua and V8; see
  [the performance record](performance-experiment.md). The first desktop
  [real-session/boundary increment](session-performance.md) is now measured;
  callback distributions, real workloads, devices and budget overhead remain
  open rather than a reason to declare #3 complete.
- [#2](https://github.com/ReneeGA2020/RuneCLR/issues/2): real-device RuneCLR
  loading/retirement remains unverified. The
  [environment audit](platform-validation.md) records concrete missing tooling
  and separates it from observed Windows results.
  A later [remote Mac preparation](remote-mac-experiment.md) passed stock
  macOS ARM64 lifecycle and a native simulator smoke; managed iOS execution
  was initially outstanding. The later [managed simulator result](ios-simulator-experiment.md)
  passes the actual harness with selective trusted R2R and Runtime IL-only,
  retaining the fully R2R host interface crash on Preview 6, official RC1 and the pinned
  .NET 12 Debug source build as a limitation. The source selective full harness
  now also passes 21/21 and post-install 22/22 with direct callback IR and
  private-generic interpretation evidence; its mini-fixture's 20/20 result is
  recorded separately. Real-device
  acceptance remains outstanding.

## 1. Measure the current session and host boundary — #3

**Dependency:** the proven desktop interpreter layout and existing lifecycle
host; no new production execution backend is needed.

**Deliverable:** extend local measurement beyond warmed kernels to the current
RuneCLR session path. Separate load/start, gameplay callbacks, stop/cleanup and
diagnostic collection; exercise calls into the shared host API and collect
allocation/GC observations. Preserve a same-IL JIT development baseline and
record runtime selection evidence.

**Acceptance:** reproducible commands, workload sizes, raw samples, source and
runtime hashes, checksums/expected gameplay effects and clear timing boundaries.
Report steady-state callback distributions separately from whole-session cost.
Allocation counters describe the measured process/thread scope, not map-owned
heap isolation. Diagnostic forced GC must not be included in a claimed normal
per-frame policy.

The coordinating agent owns integration and the result report. This desktop
extension still leaves target-device, real-game and eventual budget-overhead
measurements open under [#3](https://github.com/ReneeGA2020/RuneCLR/issues/3).

## 2. Build the minimum controlled source/IL-to-package path — #4

**Dependency:** existing map contracts and collectible lifecycle tests. The
session measurements give a baseline for package/load regressions, but do not
need to settle production performance before packaging starts.

**Deliverable:** a local prototype of the controlled server pipeline: accept
source or managed IL, compile/validate using fixed project-owned settings and
approved references, then produce a versioned approved package. The prototype
does not run arbitrary submitted build projects, scripts or NuGet restore.
Document the supported initial language/library surface and package identity.

Split implementation into three independently reviewable tasks once #4 begins:

| Task | Owned deliverable | Focused acceptance |
| --- | --- | --- |
| Manifest and content hashes | Versioned manifest, package file list, API compatibility fields and deterministic hashing rules | Detect changed/missing/extra contents, invalid paths and incompatible format/API; explain that a hash alone does not establish trusted approval |
| Fixed-reference source compilation | Compiler entry point using approved references/options, bounded diagnostics and declared language version | Compile a valid map; reject missing/unsupported references and supplied build instructions; record compiler/reference identities |
| IL-only intake | PE/metadata inspection of map and private managed dependencies without executing them | Accept declared supported managed IL; reject malformed, mixed-mode and embedded R2R/native-body input for the initial profile with explicit reasons; do not equate IL-only with safe API use |

Agents can own these three tasks in parallel; the coordinating agent defines
their common input/output contract, integrates them and owns end-to-end tests.
File ownership must be agreed before overlapping edits. This planning
contribution scheduled the split. The three components and their local CLI are
now implemented; see [the controlled packaging contract](controlled-packaging.md).

**First increment implemented:** explicit [package dependency resolution](package-resolution.md)
replaces the mobile-unsupported `AssemblyDependencyResolver`. Windows normal
and private Checked interpreter suites pass 22/22. The [actual Android harness](android-lifecycle-experiment.md)
passes 21/21, then 22/22 with IL compiled after APK installation, on both the
historical Preview 6 and updated official .NET 11 RC1
JIT-capable runtime. Android interpretation remains separate. The subsequent
local tool adds source/IL compilation/intake and a versioned package format;
authenticated approval/distribution remains outstanding. Keep Abstractions
shared, private dependencies in each collectible session, and resolution of
trusted framework dependencies explicit. Preserve A -> B -> A behavior with
same-name version-distinct dependencies; do not rely on unrestricted default
context fallback or desktop hostpolicy as the portable contract.

**Acceptance:** source and IL paths both create approved packages that load in
the desktop lifecycle harness, including a package compiled after the host.
Tampering/rejected input fails before map execution with host-owned diagnostics.
Unloading and next-map recovery still pass. Record producer provenance and
content identity; production authentication/distribution can remain a separately
stated limitation. Desktop resolver tests prepare mobile integration, not proof
of mobile behavior.

Track this work in [#4](https://github.com/ReneeGA2020/RuneCLR/issues/4), with
the dependency policy coordinated with
[#5](https://github.com/ReneeGA2020/RuneCLR/issues/5). Do not implement source
compilation or packaging merely by adding a plan. The current local increment
has executable compiler/intake/manifest/pipeline regressions, including private
dependency A -> B -> A isolation, tamper recovery and source/import lifecycle.
Mobile versioned-package deployment is the next packaging/platform integration
increment; prior mobile results validate the preceding host snapshot.

## Parallel lane: prepare devices, then prove mobile lifecycle — #2

**Environment preparation can run beside steps 1 and 2.** An owner-supplied M1
Mac with Xcode and working managed iOS simulator deployment is now available.
Preserve the measured configurations, compare the latest official release
package/current source runtime, and locate signing setup and a real iOS device.
The Windows Android SDK/JDK/NDK/emulator lane now runs
the full lifecycle harness with official CoreCLR. For Android interpretation,
prepare an appropriate runtime-build environment and interpreter-enabled binaries
with positive method evidence; repeat on an ARM64 device. Use
[the platform checklist](platform-validation.md), not presumed connectivity
from Cindy's remote phone.

**Runtime/app work depends on:** a matching private mobile runtime/framework
layout and mobile-compatible package resolution. Begin with upstream CoreCLR
samples, then use the RuneCLR lifecycle fixtures in app wrappers.

**Acceptance:** prove execution of IL built after the installed host, actual
interpretation of UGC/private dependencies, static-state reset, ordinary-failure
cleanup, resource release and repeated collectible-context retirement on a
physical iOS device. Record versions/hashes and runtime diagnostics. Android
interpretation gets its own platform evidence; emulator results do not replace
iOS-device acceptance.

Missing environments are recorded blockers. Continue the independent desktop
tasks and schedule toolchain setup separately; environment preparation alone
does not pass platform milestones. [#2](https://github.com/ReneeGA2020/RuneCLR/issues/2)
remains open until its real-device acceptance is met.

## 3. Narrow the supported execution and API surface — #5

**Dependency:** #4's package/reference/dependency identities; #2 supplies
platform evidence as it becomes available.

**Deliverable:** an initial capability/dependency profile covering approved
framework and game APIs, reflection, dynamic loading, native interop and
background work. State which checks happen at intake and which require runtime
enforcement. Establish selection coverage for map-owned methods rather than
presenting method-filter switches as an author-resistant policy.

**Acceptance:** supported maps still load and retire; focused fixtures reject
disallowed dependencies/API routes with bounded diagnostics. Verify constructor,
generic and private-dependency coverage, and unsupported native/JIT/R2R routes.
Document any remaining bypasses/trust assumptions instead of calling the initial
profile a public hostile-code sandbox.

Track [#5](https://github.com/ReneeGA2020/RuneCLR/issues/5). Source review of
runtime control points can occur earlier; final enforcement depends on the
profile being explicit.

## 4. Implement safe terminal execution budgets — #6

**Dependency:** #5's interpreted ownership and supported call boundaries. Keep
runtime changes small and switch-controlled in the separate runtime checkout.
Desktop experimentation can start while mobile validation proceeds; release
claims on each platform require its own regressions.

The [source-reviewed implementation plan](runtime-session-budget-plan.md) records
the actual session-policy source anchors and the next matching desktop patch:
native binder-owned irreversible state, common dispatch charging, owner-aware
catch/filter suppression, finite cleanup reserve and safe finalizer handling.
The separate [diagnostic accounting increment](runtime-session-meter.md) is now
implemented and measured on matching Windows Checked inputs: per-binder counters,
actual owner-aware IR dispatch, twenty fresh sessions per metered lane, boundary
and isolation controls, and joined concurrency. Existing lifecycle 24/24,
player 15/15 and four official loader controls also pass on that private build.
This non-throwing meter continues after exhaustion. Persistent terminal state,
catch/filter suppression, bounded cleanup and finalizer handling remain next;
the milestone is not complete. The later
[terminal prototype](runtime-session-terminal-prototype.md) now establishes
sticky exhaustion, author catch/filter suppression and finite cleanup reserves
for its measured Windows Checked cases. All44 isolated lanes,20 bad/good pairs,
the unchanged production24/24/player15/15 and four official loader controls pass.
The later [finalizer boundary](runtime-session-finalizer-boundary.md) passes
nine scoped recovery cases and six ordinary fatal-exception controls on a
matching Windows Checked build. A later [host budget prototype](host-instruction-budget.md)
passes15 isolated cases and73 collections with explicit opt-in limits and safe
scalar results. The [matching mobile build preparation](mobile-instruction-budget-builds.md)
now combines that source with CID v2; the later
[mobile budget acceptance](mobile-host-budget-acceptance.md) records actual
iOS simulator15/73 functional results and a fresh Android framework/layout.
The separate iOS normal run now also passes installed-before/after sampling,
and Android's strict emulator budget audit passes 15/73 with matching identity
bindings. A separate iOS debugger lane passes 147 entry samples across nine
requested author method groups. The later
[Android budget entry acceptance](android-budget-entry-acceptance.md) passes178
samples across its nine requested groups and a separate same-APK gate-off15/73
run. The [matching Release cost experiment](budget-overhead.md) measures a4.80x
configured-meter ratio for its arithmetic callback after emulator cleanup.
The later [Release acceptance](windows-release-budget-acceptance.md) closes its
scoped terminal/finalizer/host baseline. Subsequent hot-path and
[desktop batching comparisons](budget-batch-best-exact.md), plus
[mobile arithmetic measurements](mobile-batch-measurement.md), are accepted
within their measured scope. Representative physical-device performance and
physical-device validation remain outstanding.
Remaining EH/concurrent topologies and mobile/physical-device
regressions remain open. The
prototype deliberately has a separately named private factory rather than a
complete terminal capability bit. A throw-only counter likewise cannot satisfy
the milestone.

**Deliverable:** interpreter-enforced accounting plus termination that regains
host control for the supported profile, with a persistent terminated session
state. Declare costly framework/native-call restrictions and accounting.

**Acceptance:** dead loops and catch-and-continue loops cannot keep executing
game APIs; host cleanup and the next map work. Include constructors, nested
calls, exception filters/finally, cleanup/finalizer policy and failure paths.
Runtime unwinding must preserve CLR invariants. Cooperative `Charge()` and
arbitrary native jumps are not substitutes. Run relevant upstream tests and
the RuneCLR lifecycle suite on the patched runtime; measure enforcement cost.

Track [#6](https://github.com/ReneeGA2020/RuneCLR/issues/6). Full-framework
mode 3 is not a prerequisite for interpreting and controlling UGC.

## 5. Extend memory and host-owned scheduling — #7 / #8

These two contributions can proceed in parallel after package/capability and
terminal-session contracts are established. Earlier telemetry/design is useful,
but must not predeclare enforcement complete.

| Issue | Deliverable | Acceptance and dependencies |
| --- | --- | --- |
| [#7](https://github.com/ReneeGA2020/RuneCLR/issues/7) | Allocation attribution experiments and a practical memory-limit design | Distinguish direct map, framework-on-behalf and retained host allocations; test repeated-session growth and allocation-heavy maps; explain shared-heap limits and recovery compatibility with #6 before claiming a hard cap |
| [#8](https://github.com/ReneeGA2020/RuneCLR/issues/8) | Host-owned ticks, events, timers and resource handles | Use #4 API versions and #5 capabilities; callbacks obey #6 terminal state; session retirement cancels work, releases subscriptions/resources and allows the next map; map delegates/metadata must not survive in host results |

## 6. Validate one game, then decide later native work — #9 / #10

[The pilot #9](https://github.com/ReneeGA2020/RuneCLR/issues/9) depends on the
supported package/API profile, lifecycle/termination and scheduling contracts,
with a declared practical memory policy. Integrate one server-authoritative game
with internal authors; collect representative frame/session latency, memory
trends, recovery behavior, author feedback and actual device results.

Use those measurements to decide whether UGC JIT/R2R is worth a separate
experiment. Controlled compiler provenance remains mandatory, and equivalent
capability/resource/termination tests must pass before native UGC joins the
restricted profile. Retain the interpreter path and same-IL JIT development
comparison; do not make a speculative public backend API a prerequisite.

[Public UGC readiness #10](https://github.com/ReneeGA2020/RuneCLR/issues/10)
follows the pilot: define distribution/approval, hostile-input review and
operational recovery gates against the supported trust model. It is not a
prerequisite for every controlled-map experiment, and the earlier milestones
do not claim that readiness on its behalf.
