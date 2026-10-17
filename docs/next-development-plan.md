# Next development plan

Prepared on 2026-10-15 for implementation in a new session. Follow the
[product direction](product-direction.md) and the project development Skill.
Updated after the Windows independent-composition experiment. Completion is
limited to the explicitly recorded configuration; remaining acceptance is planned.

## Outcome and starting point

The next milestone is a small, engine-independent first-party C# update example:
independently built R2R updates cooperate with existing R2R application code,
with interpretation for methods without usable precompiled bodies. Establish
the build/execution and iOS delivery facts before designing a broad SDK.

The recorded starting commit is `5a1b060`. Recheck the actual checkout before
implementation. The owner removed `global.json` in `b63c6d8`; do not restore it
as part of this work. Record the SDK actually selected. Preserve unrelated
`.claude/` contents. Runtime source is a separate checkout; local setup belongs
in `docs/development.local.md`.

Existing desktop lifecycle, restricted packages, pumped sessions, native budgets
and mobile simulator/emulator experiments are baselines, not work to repeat.
Windows independent R2R composition now has positive native-frame evidence in
noncollectible contexts. Collectible interpreted contexts retire successfully,
but the selected upstream runtime explicitly disables their R2R bodies. On that measured result, RuneCLR does not pursue unloadable hot-update R2R: an update that must be unloaded stays interpreted, and ordinary first-party execution does not repeatedly unload old assemblies.
Physical iOS downloaded-R2R execution remains an acceptance gap. First-party code is trusted and does not inherit the
restricted UGC execution or API policy.

The first-party product loop is startup-oriented: at each process start, check
for an update, download and verify it, select one business version for that
process, load it once, and use it until process exit. Backgrounding, logout and
re-entering a game do not create a process boundary. Noncollectible native code
remaining resident for this lifetime is expected. Same-process multi-version
updates are not a prerequisite for the first iOS closure.
On that measured result, RuneCLR does not pursue unloadable hot-update R2R: an update that must be unloaded stays interpreted, and ordinary first-party execution does not repeatedly unload old assemblies.

## Current decision after the Windows experiment

Read the [measured report](independent-r2r-composition.md). Shared objects,
interfaces, delegates, generics, A -> B -> A, state reset and managed-failure
recovery passed the focused Windows controls. The runtime was not modified.
The driver correctly retains `milestoneComplete=false`: the original combined
step-1 acceptance below has not passed.

Proceed to step 2 using noncollectible contexts for the native update lane.
On the 2026-10-16 measured result, RuneCLR does not pursue unloadable hot-update R2R: an update that must be unloaded stays interpreted, and ordinary first-party execution does not repeatedly unload old assemblies.
Preserve the collectible interpreted lane as that unloadable control. Do not claim native unloading
from session cleanup, and do not treat the blocked collectible-R2R acceptance as work still to complete.
The experimental ReadyToRunCollectible switch was not retained.

## 1. Build and execute independent modules - #13, initial #14

Create a focused trusted fixture before introducing a production package format.
Use one shared contract, a non-updateable host/module, and two update versions
with a private managed dependency. Build each update version from identical
business sources in IL and target-specific R2R forms. Keep update and host R2R
builds independent; do not require one combined composite image.

Use ordinary supported runtime selection for trusted modules, retaining the
existing required-interpreter UGC tests separately. Record matching runtime,
CoreLib, reference inputs, crossgen2, architecture and configuration.

Acceptance:

- The same business sources build as IL and R2R with equivalent expected results.
- Both forms call a shared host object, preserve reference identity, and exercise
  an interface callback, delegate and generic case across the module boundary.
- Runtime diagnostics or native method-entry evidence prove selected methods
  execute their R2R bodies. R2R headers or successful loading alone do not pass.
- An intentionally IL-only helper supplies positive interpreter-entry evidence
  in a matching mixed-mode configuration. Separate desktop JIT controls.
- A -> B -> A runs reset module-private state and binds the intended private
  dependency version as a Windows control; this is not required for the first
  iOS product closure.
- A focused failure case releases references and permits a fresh session.
- One command reproduces the fixture and records inputs, expected results,
  execution evidence and configuration-specific limitations.

Start on Windows for a short feedback cycle. A desktop pass closes only the
scoped build/composition increment, not the iOS delivery milestone.

## 2. Test post-install R2R delivery on iOS - #12 and #2

The immediate assignment is the noncollectible native lane. Its selected update
image and loading context remain resident until process exit; this is the normal
first-party startup lifetime. Only session objects and host-owned resources are
retired within that process. This is a scoped experiment, not approval of a
broader multi-version lifetime policy.

Status on 2026-10-15: the first simulator pipeline run stopped before download
and load. Composite crossgen of the post-install A owner crashed with exit -6
while rewriting the update component. The synthetic Mach-O preflight is not
native execution. Next, isolate that rewrite crash and keep the pre-crash
component; do not repeat a full simulator install until an owner dylib links.

The in-place crash is now reproduced from a preserved 4096-byte component. The
non-composite Mach-O run is a format rejection, not that access violation. Next,
one composite attempt must write the object outside the input directory before
any further simulator install.

That separate-directory composite now exits 0 for the preserved inputs. Do not
return to in-place component rewrite. Next, link and ad-hoc sign the object
before any simulator launch.

The preserved object is now linked and ad-hoc signed, and the driver writes
owner output under crossgen-out. Next, one simulator process may load that
split-output payload and capture a method entry. Static acceptance is not that
capture.

The first simulator load mapped the downloaded owners but did not record an
update-method PC. Recapture only after the breakpoint selects Business.Execute
or Update.Run, not the first symbol whose name contains Update and Run.

The corrected Business.Execute breakpoint also missed. Arm it after the owner
dlopen returns and record whether the breakpoint gained a location before
running another load.

Version A's Business.Execute entry is now recorded at the downloaded image
base plus 5472. Capture B with the same returned-dlopen breakpoint before
calling the simulator lane accepted.

B is now recorded at base plus 5472 in TrustedUpdate.B.r2r.dylib. The simulator
method-entry pair exists. Do not treat it as physical-device acceptance or as
proof that the managed success line was captured.

A's managed success line is now present on stderr and matches result 216.
Stdout still does not contain it. Future checks must read both streams. B's
managed line and physical-device execution remain open.


The simulator follow-ups are measured. A's managed success line is on
stderr. The only available phone is an iPhone XR locked to iOS 18.7. That phone
is not the iOS 27 runtime, so do not start a physical-device build or install.









Reuse the smallest fixture from step 1 rather than porting the entire test suite.
Inspect the selected CoreCLR/crossgen2 Apple artifact and loading path first;
identify which files contain executable bodies and how those bodies are mapped.
Then build/install a fixed host, produce the update after installation, transfer
it through a repeatable download path, and load it without rebuilding the host.

Use the existing Mac simulator lane to debug the pipeline. Refresh physical
device reachability and signing/profile availability early, once. If unavailable,
record the concrete missing input, complete the simulator increment and proceed
to independent host work; physical acceptance remains pending.

Acceptance:

- Record build/install/update timestamps and source/artifact hashes before the
  process selects its one business version; the installed host and its bundled
  native images remain unchanged.
- Identify the actual target-specific update artifact, signing/loading steps and
  runtime switches. Report any required entitlements or environment conditions.
- Prove downloaded update methods enter their R2R native bodies, plus positive
  interpreter entry for the selected IL-only helper. A wholly interpreted R2R
  image does not establish downloaded native-code execution.
- Run separate processes that select A and B at startup. Each process must keep
  its selected version through process exit, with correct shared objects and
  explicit session-state initialization. A -> B -> A remains a Windows control,
  not a first-iOS-closure requirement.
- Exercise an ordinary update failure with host-owned diagnostics and verify the
  next process start falls back or retries according to the recorded policy.
  Record whether the failure occurred before or after native loading: a failed
  version may remain resident, so do not infer that it can be unloaded. State
  the required restart boundary explicitly.
- Keep basic single-version memory observations in this run. Do not treat disk
  cache deletion as unloading resident code.
- Treat the already verified collectible interpreted loading/recovery as a
  separate control; do not repeat it for this iOS native lane. Do not require or
  report collection of the native update contexts.
- Preserve negative results with exact loader/runtime diagnostics. If the selected
  format cannot execute its native bodies, isolate that failure before expanding
  the SDK and identify the next concrete runtime/packaging experiment.
- Keep simulator and physical-device outcomes separate. Physical iOS is the
  acceptance target for this delivery claim; technical execution and distribution
  approval remain separate facts.

## 2a. Follow-up: measure resident-version costs when the product needs it

The first iOS closure does not require same-process multi-version updates. When
the product needs that behavior, measure it separately from the startup loop.
The Windows fixture copies images into a new directory for each activation. That
proves independent native composition and fresh module statics, not a bounded
production session model. The selected runtime gives each loaded R2R image one
module owner. Reusing an image across contexts needs explicit controls.

Build a separate experiment that loads a version once and creates multiple
session instances from it, then activates additional distinct versions and rolls
back to an already loaded version. Verify actual R2R execution on reactivation,
dependency identity and explicit state initialization rather than assuming that
reusing a resident version reproduces a fresh module's static state.

Measure repeated sessions on one version separately from increasing numbers of
versions. Record mapped images, native/loader memory observations, managed heap
and retained references, with the scope of each counter. Release session objects,
delegates, event subscriptions and resources; version statics can still retain
objects. Noncollectible context lifetime alone does not measure their live heap.

Use these results to propose version admission and restart requirements. Disk
cache deletion does not unload resident code, and a failure after loading may
leave the failed version resident. A resident-version count can be bounded only
by stopping further distinct-version loads or ending the process; do not describe
it as eviction. Define a new-version admission limit, diagnostics and
persistence/restart behavior before adopting same-process updates in a real
game. This follow-up does not block the startup-oriented first iOS closure.
On the 2026-10-16 measured result, RuneCLR does not pursue unloadable hot-update R2R: an update that must be unloaded stays interpreted, and ordinary first-party execution does not repeatedly unload old assemblies.
This follow-up may measure resident noncollectible versions; it does not reopen collectible native R2R.

## 3. Turn the fixture into a trusted update path - #12

Extract a small reusable loader/session interface and a console embedding sample.
Use a distinct trusted-update contract rather than weakening the existing
`managed-il-gameplay-v1` UGC policy. Preserve shared validation and resolution
where appropriate.

Acceptance:

- Describe module/dependency identities, host API compatibility and target runtime/
  architecture requirements. Reject incompatible inputs before activation.
- Stage and validate a candidate from a configured trusted origin before selecting
  it. Distinguish content hashes from approval/authentication.
- Define activation at process startup and retention of the last known good
  version. Test rejected candidates, startup failure and next-start rollback
  without contaminating the selected version's state.
- Return host-owned errors without retaining update exceptions or metadata.
- Document the public ownership and release contract and the supported version
  boundary. Active-frame replacement and automatic state migration are outside
  this increment.
- Distinguish session cleanup, managed-object collection and native module
  residency in APIs and diagnostics. Enforce one selected business version per
  process; do not promise native code unloading with the selected upstream runtime.

## 4. Publish interop and compatibility acceptance - #14 and #15

The measured draft is [compatibility-matrix.md](compatibility-matrix.md). It does not close #14 or #15.

Extend the small fixture with shared object identity, virtual/interface calls,
delegates/events, generic methods/types and exceptions in both directions.
Include a deliberately retained session object, followed by reference release
and object collection where no version static retains it. Context-unloading
checks belong to the collectible interpreted lane; noncollectible native
contexts remain resident. Unsubscribe callbacks at session retirement.

Publish a matrix separating compiler syntax, emitted runtime features, framework
APIs, platform/architecture and restricted UGC policy. Record IL and independent
R2R results independently. Source syntax follows the selected compiler's latest
stable C# version. Do not promise full .NET or arbitrary NuGet compatibility.

## 5. Integrate one game, then resume UGC expansion - #9, #8, #7

Integrate a small real gameplay loop with host-driven callbacks and one update
that changes visible behavior. Measure startup/version selection, callback distributions,
host-boundary costs and retained memory with representative objects. Keep
diagnostic forced collection outside frame timings. Compare first-party IL/R2R
paths before choosing further runtime optimizations.

After the trusted-update milestone, prioritize host-owned subscriptions, timers
and resources, mobile controlled-package budgets, then practical allocation/
memory policy for UGC. Existing exact and N100/N1000 experiments remain evidence;
do not start another budget optimization as a prerequisite to first-party use.
Review public naming separately; existing `Map` names do not limit the host model.

## Maintenance alongside the milestone

The two [upstream reports](upstream-bugs/reports/README.md) and combined evidence
ZIP are prepared. On 2026-10-16 RCLR-UP-001 is
[dotnet/runtime #135848](https://github.com/dotnet/runtime/issues/135848) and
RCLR-UP-002 is
[dotnet/runtime #135849](https://github.com/dotnet/runtime/issues/135849).
Both were open when recorded. Filing is not an upstream fix. Do not file
either report again. Keep private CID/generator fixes until official
replacements pass their recorded regression gates. Do not expand the
unreduced mode-3 assertion investigation unless it blocks the chosen fixture.

At implementation start, check both repository states and run the relevant
baseline using the selected matching toolchain. Host changes require the RuneCLR
verification entry points; runtime patches also require focused upstream tests.
Update the handoff with actual commands, products, results and remaining gaps.

## Next new-session assignment

On 2026-10-16 commit c268026 records simulator directory rerun-a9164cd-20261016-10. python3 eng/verify-ios-trusted-update.py exited 0 with passed=true and nativeExecutionProven=true. A and B both recorded RUNECLR_EXIT=0 and TRUSTED_UPDATE_SUCCESS result=216. That run used a Mac clone which also printed temporary failure-type diagnostics. The committed tree does not contain those prints. On 2026-10-16 a clean checkout of c268026 at /Users/editor/RuneCLR-experiments/RuneCLR-c268026 reproduced the iOS 27 simulator as rerun-c268026-20261016-01: verify-ios-trusted-update.py exited 0 with passed=true and nativeExecutionProven=true, and A and B both recorded RUNECLR_EXIT=0. That is still not a physical-device result.

The only available phone is an iPhone XR locked to iOS 18.7. Do not build an iphoneos CoreCLR or install on that phone. The committed simulator path was reproduced on clean c268026. Do not repeat that simulator run. An iOS 18.7 device runtime is still not started, because the only phone is an iPhone XR locked to iOS 18.7 and this iOS 27 runtime does not target it. Hot-update DLLs are not built per iOS version. The desktop selector is 270/270. Do not pursue unloadable hot-update R2R. One selected noncollectible version stays resident for the process.


On 2026-10-16 one desktop self-test, `dotnet run --project samples/RuneCLR.TrustedUpdateHost -c Release -- --timings`, exited 0 and printed TIMING_STARTUP_MS 99, TIMING_CALLBACK_MS 0, and TIMING_BOUNDARY_MS 1. Startup includes writing the candidate, selection, and opening the session. The callback value is whole milliseconds, so 0 means under 1 ms. This is not a distribution, not an iOS result, and it does not close #3 or #13.

On 2026-10-16 the desktop session suite passed 56/56 in Release after adding host-owned resource names. MaxResources defaults to 128. Zero is rejected before map execution, and a caught limit stops the session before OnStop. RegisterResource, ReleaseResource, and CopyResources are covered, including two live sessions that do not share names. Repeat keeps one schedule slot and requeues after it is taken. A one-shot Schedule does not. The host can post one subscribed primitive between callbacks, and Stop drops it. Two live sessions do not share posts. A duplicate id and a negative id are rejected. Two posts to the same id are taken in FIFO order. This does not add a wall-clock timer, and it does not close #8.

On 2026-10-16, after the host-session additions, desktop samples/RuneCLR.SampleHost Release --pump exited 0. hello, arena, and hello each Completed with ticks=3. Without --collect, unload stayed pending. With --pump --collect, all three were collected. --pump --require-interpreter on the installed SDK exited 1 before any map ran, because CoreLib lacks RuneCLR_CreateInterpreterRequired. That rejection is not interpreter execution and not an iOS result.

On 2026-10-16 dotnet build RuneCLR.slnx -c Release exited 0 with 0 warnings and 0 errors. The trusted-update selector suite then passed in Release with the same count already recorded. This is not an iOS result and does not close #8, #12, or #13.

On 2026-10-16 the controlled package player passed 15/15 without --pump and 22/22 with --pump --include-pumped fixtures. Both used a new artifacts/package-execution directory and the Release player. Packaging tests passed 85/85 in the same Release build. This is desktop only and does not close #4 or #8.

On 2026-10-16 ./eng/verify.ps1 exited 0. The desktop script covered the Release solution, late map, runtime tests, packaging, controlled player, trusted-update selector, the desktop iOS-host source check, the trusted-update self-test, and both sample collection paths. It did not start a simulator and does not close #2, #8, or #12.

docs/direct-interop.md records the desktop reference-identity facts already measured. It does not list every supported type, it does not accept physical iOS, and it does not close #14.

The controlled player already covers an author failure followed by a valid package, and a pumped tick or stop failure followed by a fresh package. That is desktop evidence for ordinary-failure recovery. It does not close #8 and is not physical iOS.

docs/actionable-diagnostics.md records the desktop InvalidDataException prefixes for capability denial, identity mismatch, and unsupported managed-IL shape. They share one exception type. This does not close #15 and is not physical iOS.

On 2026-10-16 commit f509043 recorded one Windows composition timing run at artifacts/trusted-composition-20261016-timings-2. verify-trusted-composition.py exited through the known collectible blocker: controlsPassed=true, milestoneComplete=false, status=blocked-collectible-r2r. Startup, callback, and boundary microseconds were il-collectible 47618/246259/15724, r2r-collectible 47086/224708/12936, r2r-native 45569/238021/0, il-jit-control 48614/362020/12659, and r2r-disabled-control 168279/290414/2. The two noncollectible lanes did not call Collect; 0 means under 1 microsecond. Do not rerun that probe to recapture the same numbers. Issue 13 stays open. Physical iOS remains paused.

The c268026 simulator receipt already prints a managed-heap snapshot: A MANAGED_BYTES=74248 and B MANAGED_BYTES=74264 from GC.GetTotalMemory(false) after success. A 2026-10-15 A launch and a 2026-10-16 A relaunch both printed 41040. That counter is not a stable peak and is not physical footprint. The relaunch paused footprint was 80 KB with peak 96 KB before coreclr_initialize; sampling after process exit failed. Do not boot another simulator to recapture these numbers. Physical iOS remains paused. Issue 12 stays open.

One 2026-10-16 iOS 27 simulator relaunch of version A stopped at libsystem_c exit while the process was still alive. footprint --noCategories printed phys_footprint 24 MB and phys_footprint_peak 24 MB, formatted, 16384-byte pages, not --format bytes. The same process printed MANAGED_BYTES=41040 and result=216. The simulator was deleted. This is not the c268026 process that printed 74248, and it is not a physical-device result. Do not boot another simulator to recapture this formatted 24 MB line. Issue 12 stays open.

On 2026-10-16 the Windows composition run artifacts/trusted-composition-20261016-reactivate kept controlsPassed=true and milestoneComplete=false. In the r2r-native lane the first A directory 2b34f122b2044e3f995fddc559f92f6c has 4 native update frames and 4 native private frames. Later A copies have 3 frames in other directories, B has 3, and the failing session has 1. Returning to the already loaded copy ran native code there. It did not create a new copy. Do not rerun that probe for the same frame counts. Issue 13 stays open. This is not an iOS result.

In that same reactivate run, r2r-disabled-control also reported residentReactivationStaticCount 4 while native host, update, and private frame counts were all 0. Continuing statics does not prove a native frame. Do not rerun for this negative. Issue 13 stays open. This is not an iOS result.

Those 4 update frames are TrustedComposition_Update_A_TrustedComposition_UpdateModule__Execute, and those 4 private frames are TrustedComposition_Private_TrustedComposition_PrivateLogic__Read. Do not rerun for these symbol names. Issue 13 stays open. This is not an iOS result.

One Windows composition run at artifacts/trusted-composition-20261016-managed recorded GC.GetTotalMemory(false) at the end of each lane: il-collectible 313544, r2r-collectible 313552, r2r-native 2964664, il-jit-control 266728, and r2r-disabled-control 3127800. That is not a forced collection, not a peak, and not physical footprint. Noncollectible lanes still reference the loaded modules; collectible lanes have unloaded those contexts. controlsPassed=true and milestoneComplete=false. Do not rerun for these snapshots. Issue 13 stays open. This is not an iOS result.

One Windows composition run at artifacts/trusted-composition-20261016-workingset recorded Environment.WorkingSet beside GC.GetTotalMemory(false): il-collectible 60940288 and 313688, r2r-collectible 60968960 and 313728, r2r-native 68587520 and 2965656, il-jit-control 63520768 and 266872, r2r-disabled-control 69156864 and 3136808. The working set is not a peak and not an iOS physical footprint. controlsPassed=true and milestoneComplete=false. Do not rerun for these paired snapshots. Issue 13 stays open.

One Windows composition run at artifacts/trusted-composition-20261016-private returned to the already loaded A module after B. r2r-native and r2r-disabled-control both reported PrivateValue 101, PrivateVersion 1.0.0.0, and static count 4. Collectible lanes reported null. controlsPassed=true and milestoneComplete=false. Do not rerun for this private binding. Issue 13 stays open. This is not an iOS result.

On 2026-10-16 the desktop restricted UGC packaging suite passed 124/124 at commit c196707. A caught host limit fails the session at the end of that callback: OnTick does not run after OnStart fails, and a later tick does not run after the first tick fails. The failed tick is not counted. An empty OnStop does not add an OnStop: prefix. Reading MapId during that OnStop does not throw. A charging host call in OnStop raises the latched limit again and adds OnStop:. If OnTick catches the limit and then throws an author exception, the latched limit is appended after the author failure without an OnStop: prefix. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open. The earlier 85/85 packaging sentence remains the historical RC1 result.

On 2026-10-16 packaging tests passed 126/126 at commit 215663d. Charge(0) and Charge(-1) fail in OnStart with System.ArgumentOutOfRangeException before OnTick. Charge(int.MaxValue) fails with the cooperative operation budget, not ArgumentOutOfRangeException, and does not wrap. An empty OnStop does not add OnStop:. The 125/125 strict text was confirmed by a later Release run. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 128/128 at commit 5ca90e0. With OperationBudgetPerCallback set to 1, Charge(1) succeeds in OnStart, OnTick, and OnStop, and the session completes one tick. After OnStart spends that one operation, OnTick still receives a fresh budget, and Charge(2) fails that tick without counting it. An empty OnStop does not add OnStop:. Refill does not disable the per-callback cap. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 129/129 at commit 700acaf. With TickCount 2 and TickDuration 50 milliseconds, OnTick logs 0:500000 and 1:500000. Both ticks complete. Commit e595193 accepts both LF and CRLF before the non-positive Charge detail line. Prototype checks run 38891953960 passed on ubuntu-latest, macos-latest, and windows-latest. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 131/131 at commit 9642eee. With TickCount 0, OnStart and OnStop still run and OnTick does not. The logs are start and stop. A negative TickCount throws ArgumentOutOfRangeException with ParamName TickCount before the author runs. The Message is TickCount ('-1') must be a non-negative value. (Parameter 'TickCount'), then Actual value was -1. Windows separates that line with CRLF. Ubuntu and macOS separate it with LF. The next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 132/132 at commit 407dc0a. A zero TickDuration throws ArgumentOutOfRangeException with ParamName TickDuration before the author runs. The Message is TickDuration ('00:00:00') must be greater than '00:00:00'. (Parameter 'TickDuration'), then Actual value was 00:00:00. Windows separates that line with CRLF. Ubuntu and macOS separate it with LF. The next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 133/133 at commit ff8e7e3. A TickDuration of one negative tick throws ArgumentOutOfRangeException with ParamName TickDuration before the author runs. The Message is TickDuration ('-00:00:00.0000001') must be greater than '00:00:00'. (Parameter 'TickDuration'), then Actual value was -00:00:00.0000001. Windows separates that line with CRLF. Ubuntu and macOS separate it with LF. The next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 134/134 at commit f894b2d. The default MapRunOptions run three ticks of 50 milliseconds. OnTick logs 0:500000, 1:500000, and 2:500000. The session completes. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 135/135 at commit 8909dc1. An entity spawned in OnStart is destroyed on the first tick. The next tick logs tick1 and then DestroyEntity fails because the entity is gone. That tick is not counted. CompletedTicks stays 1. An empty OnStop does not add OnStop:. The entity is released, and the next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 136/136 at commit 87ed913. An entity spawned in OnStart and left alive is released when the session completes. The logs are made and tick. One tick completes, created 1, released 1, remaining 0, and no error is reported. The next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 137/137 at commit dbb8868. The author catches a second DestroyEntity of the same id, and the session still completes. The other entity is then destroyed. The logs are made, tick, gone, and kept. One tick completes, created 2, released 2, remaining 0. A caught argument error is not a latched host limit. The next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 138/138 at commit 5721b5a. Destroying one entity leaves the other alive until session completion. The logs are made and tick. One tick completes, created 2, released 2, remaining 0, and no error is reported. The next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 139/139 at commit 88c32f1. OnStop can destroy an entity spawned in OnStart. The logs are made, tick, and stopped. One tick completes, created 1, released 1, remaining 0, and no error is reported. The next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 140/140 at commit c039cd9. Destroying an already removed entity in OnStop fails and adds OnStop:. The completed tick remains. The logs are made and tick, not stopped. CompletedTicks stays 1. The entity stays released, and the next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 141/141 at commit ced0bbb. An empty log string is stored. It is not treated as a null log. The session completes one tick, and the next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 142/142 at commit a49b9a8. A log of one space is stored unchanged. It is not rejected as whitespace. The session completes one tick, and the next package still runs. Entity names still reject whitespace. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 143/143 at commit 1d990e4. An entity name of one space is rejected. No entity is created, no tick completes, and the next package still runs. A log of one space is still stored. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 144/144 at commit 8d093b9. A log of exactly 2048 characters is stored. The session completes one tick, and the next package still runs. A log of 2049 characters still exceeds the limit. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 one Windows run at artifacts/trusted-composition-timing-20261016 exited 0 and printed PASS five functional/execution controls. controlsPassed=true, milestoneComplete=false, and status=blocked-collectible-r2r. Startup, callback, and boundary microseconds accumulated across the sessions in that one process were il-collectible 47279/226526/13186, r2r-collectible 47760/222400/13389, r2r-native 44706/222359/0, il-jit-control 45633/345580/11850, and r2r-disabled-control 164025/282338/2. The same noncollectible semantics are r2r-disabled-control, with ReadyToRun off so the update module runs as interpreter IL, and r2r-native, which is noncollectible R2R. Their boundary totals are 2 and 0 microseconds. A total of 0 is under 1 microsecond. il-collectible and r2r-collectible are not noncollectible R2R. Collectible R2R remains refused by upstream. These figures are not a distribution across processes and not an iOS result. Issue 3 stays open. Issue 13 stays open.

On 2026-10-16 the owner deferred a four-platform performance pass. Windows, macOS, iOS, and Android still need performance measurements, but that pass is not current work. The Windows composition timing above is one process aggregate and does not cover macOS, iOS, or Android. Do not start a runtime build, simulator, or emulator only to open that pass. Simulator and physical-device results stay separate. Physical iOS remains paused because the only phone is an iPhone XR locked to iOS 18.7. Issue 3 stays open.

On 2026-10-17 desktop runtime tests passed 58/58 after adding HostContractSession. The script OnStart receives the game-supplied interface instance and calls Echo(41). The assembly is loaded from memory, and Dispose drops the collectible context. An OnStart parameter that is not that interface fails before the author method runs. The managed-il-gameplay-v1 allowlist is unchanged. IMapContext is not renamed. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 59/59 after rejecting a foreign OnStart call. OnStart may call only methods declared by the game-supplied interface. Object.ToString is rejected before the author method runs, and the host echo is not called. This is not a full packaging allowlist. IMapContext is not renamed. This is not an iOS result.

On 2026-10-17 packaging tests passed 146/146 after adding ValidateHostContract. It reads the entry OnStart without loading the author assembly. A call to Echo on HostContract.IApi is accepted. Object.ToString is rejected before loading, and the message contains Capability profile and host contract member. Existing managed-il-gameplay-v1 validation is unchanged. PackageValidator.Validate does not call ValidateHostContract, so gameplay packages keep the prototype profile. IMapContext is not renamed. This is not an iOS result.

On 2026-10-17 packaging tests passed 147/147 after also checking the OnStart parameter. The parameter type must be the named host interface. OnStart(object) is rejected before loading. Echo on HostContract.IApi still passes. PackageValidator.Validate is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 148/148 after rejecting an interface method that was not allowed. HostContract.IApi.Other is named in the error and is not called. Echo remains allowed. PackageValidator.Validate is unchanged. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 60/60. HostContractSession now takes the allowed method names. An OnStart call to IHostEcho.Other is rejected before the host method runs when only Echo is allowed. Echo(41) still reaches the host. This is not an iOS result.

On 2026-10-17 packaging tests passed 151/151. package.json may include hostInterface and allowedMethods. When either is present, PackageValidator.Validate requires both and runs ValidateHostContract on the entry before the gameplay profile. Omitting both leaves existing manifests and their content hashes unchanged. Allowed methods remain simple names, not signatures. This is not an iOS result.

On 2026-10-17 the project owner set the host API shape. The game supplies a shared assembly and an ordinary CLR interface. The script receives an instance and calls its methods directly. RuneCLR still owns loading, capability limits, execution, and unload, and it does not define gameplay methods. SpawnEntity is not required, and calls are not dispatched by name. IMapContext remains the prototype sample and the current managed-il-gameplay-v1 allowlist. It is not renamed. A later restricted UGC allowlist names members of the host-supplied interface. Trusted hot updates are not limited to that allowlist. This decision does not implement the extension point.

On 2026-10-17 packaging tests passed 154/154. PackageBuilder and RuneCLR.PackageTool write hostInterface and allowedMethods when both are supplied. Loading then checks OnStart against that interface and those method names. A build that supplies only one of them is rejected. Omitting both leaves ordinary gameplay manifests unchanged, because the OnStart check still rejects calls that are not on the named interface. Allowed methods remain simple names. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 62/62. HostContractSession.Invoke runs one later public parameterless void method on the same script instance. Its IL is checked before that method runs, using the host interface and allowed method names from construction. An unlisted call does not run, and the earlier Echo remains. Dispose drops the script reference, and a later Invoke throws ObjectDisposedException. The collectible context unloads. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 63/63. HostContractSession.Invoke can pass the same host instance into a later public void method that takes the host interface. A parameterless callback still runs. The IL check still happens before the method runs. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 64/64. HostContractSession rejects a reentrant Invoke while OnStart or a later callback is still running. The message is A session lifecycle callback is already running. The nested callback does not run. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 65/65. A host-contract callback failure is reported as a new InvalidOperationException. Its message contains the caught type and message, and InnerException is null. The session can Invoke a later callback after that failure. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 66/66. After a host-contract callback failure, Dispose still unloads the collectible context while the host keeps the text exception. An OnStart failure is also text with no InnerException, and the constructor does not return the session. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 69/69. HostContractSession.Open reads hostInterface and allowedMethods from package.json. It checks the content hash and the entry file hash, then uses that method list for OnStart. It does not run the managed-il-gameplay-v1 profile. A different interface name is rejected before the author runs. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 71/71. HostContractSession rejects a type initializer before creating the script. An instance constructor may call only Object..ctor. Both checks happen before OnStart, and the host method is not called. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 72/72. HostContractSession inspects the assembly before loading it. An image that is not IL-only is rejected, and the host method is not called. This is the structural intake check, not the gameplay member allowlist. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 73/73. HostContractSession rejects an author assembly whose simple name is mscorlib, netstandard, System, Microsoft, RuneCLR, or starts with System., Microsoft., or RuneCLR. The host method is not called. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 74/74. HostContractSession allows references only to System.Runtime, System.Private.CoreLib, netstandard, and the assembly that declares the host contract. A reference to RuneCLR.Packages is rejected before the host method runs. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 75/75. HostContractSession rejects localloc, cpblk, initblk, ldind, and stind in OnStart, a later callback, and the instance constructor. The host method is not called. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 76/76. HostContractSession rejects ldsfld, stsfld, and ldtoken in OnStart, a later callback, and the instance constructor. Instance fields can still store the host. The host method is not called. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 78/78. HostContractSession.Open rejects a changed entry file before loading it. The message contains hash mismatch. A manifest whose host interface was edited without updating the content hash is also rejected. The message contains content identity. The host method is not called. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 80/80. HostContractSession.Open rejects an entry path containing .. and an entry that does not end in .dll. Both fail before the file is opened. The message says the path must be a canonical relative DLL path. The host method is not called. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 82/82. HostContractSession.Open requires the entry path to appear once in the file list with the same hash. A missing entry or a different file hash is rejected before the file is opened. The message says the file list must exactly match the entry. The host method is not called. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 84/84. HostContractSession.Open requires every file to be the entry or one private dependency, with the same path and hash. A dependency path containing .. is rejected before any file is opened. An extra file is rejected. The host method is not called. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 87/87. HostContractSession.Open checks each private dependency file hash before loading the entry. A missing or changed dependency is rejected. A matching dependency still lets the host method run. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 89/89. HostContractSession.Open inspects each private dependency after its hash matches. A file that is not a managed PE is rejected. A dependency named System.IO is rejected as a spoof. A valid IL dependency still lets the host method run. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 90/90. HostContractSession rejects boxing a value type that is not in System.Private.CoreLib or System.Runtime. The check covers OnStart, a later callback, and the instance constructor. The host method is not called. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 91/91. HostContractSession rejects newarr and initobj of a type that is not in System.Private.CoreLib or System.Runtime, using the same rule as box. The host method is not called. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 92/92. The host-contract author-type check now also covers castclass, isinst, unbox, unbox.any, ldobj, stobj, mkrefany, refanyval, sizeof, and constrained. A castclass of an author class is rejected before the host method runs. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 93/93. HostContractSession rejects ldftn and ldvirtftn. An ldftn of Object.ToString is rejected before the host method runs. ldsflda is rejected with static field loads. ldelem, stelem, and ldelema use the author-type rule. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 94/94. HostContractSession rejects cpobj of a type that is not in System.Private.CoreLib or System.Runtime. Copying an author value type is rejected before the host method runs. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 95/95. HostContractSession allows ldfld, stfld, and ldflda only for a field declared on the method's own type. A field of another type is rejected before the host method runs. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 96/96. HostContractSession reads exception handlers from the assembly metadata. A catch of an author exception type is rejected before the method runs. A filter handler is rejected. Catch types in System.Private.CoreLib or System.Runtime stay allowed. The host method is not called for the author catch. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 98/98. A host-contract OnStart can catch System.Exception and still call the host. An exception filter is rejected before the method runs, and the host method is not called. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 99/99. HostContractSession rejects a generic OnStart before the method runs. The host method is not called. A later callback was already required to be non-generic. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 101/101. HostContractSession.Open loads a declared private assembly into the collectible context. OnStart may call a method on that assembly, and that method is checked before it runs. A private call to System.IO.File.ReadAllText is rejected, and the host method is not called. A framework assembly name is still rejected. The package validator still rejects an OnStart call that is not on the named interface. Its gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 158/158. ValidateHostContract accepts an OnStart call to a method in the entry assembly or a declared private assembly, and checks that method before accepting it. A same-assembly helper and HostHelper.Math.AddOne are accepted. A private call to System.IO.File.ReadAllText is rejected, as is a private call whose assembly image was not supplied. PackageValidator passes declared private images into that check. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 103/103 and packaging tests passed 160/160. A declared private method may call a method on the entry assembly, and that entry method is checked before it runs. The callback returns 41 to the host. string.IsNullOrEmpty reached through the entry method is rejected, and the host method is not called. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 105/105 and packaging tests passed 162/162. OnStart may construct a type declared by the entry or a private assembly, and that constructor is checked before it runs. An author box returns 41 to the host. new System.InvalidOperationException is rejected, and the host method is not called. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 107/107 and packaging tests passed 164/164. OnStart can construct a type declared in a private assembly, and that constructor is checked before it runs. The private box returns 41 to the host. string.IsNullOrEmpty inside that constructor is rejected, and the host method is not called. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 109/109 and packaging tests passed 166/166. One declared private assembly may call another. The call returns 41 to the host. string.IsNullOrEmpty reached through the second assembly is rejected, and the host method is not called. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 112/112. HostContractSession.Invoke can pass one int to a later public void method. The method is checked before it runs. OnTick receives 41. string.IsNullOrEmpty in that callback is rejected, and the earlier Echo(1) remains. Invoke without the int does not run the int method. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 115/115. HostContractSession.InvokeInt calls a public int method with one int parameter and returns its int. Measure(40) returns 41 without calling the host again. string.IsNullOrEmpty in that method is rejected, and the earlier Echo(1) remains. A void callback is rejected by InvokeInt. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 118/118. A later callback may take the host contract and then one int. Invoke passes 41 to OnTick. InvokeInt Measure(40) echoes 40 and returns 41. string.IsNullOrEmpty in that shape is rejected, and the earlier Echo(1) remains. This is not an iOS result.

On 2026-10-17 packaging tests passed 169/169. ValidateHostContract checks a later public callback on the entry when it takes the host and one int. A callback that echoes the int is accepted. string.IsNullOrEmpty in that callback is rejected. A public method with an unsupported signature is not checked. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 171/171. A later host-and-int callback may call a declared private assembly, and that private method is checked. A private AddOne used by the callback is accepted. string.IsNullOrEmpty inside that private method is rejected. OnStart itself does not call the private method. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 119/119. HostContractSession rejects a supported later callback with a disallowed call before OnStart. An int callback, an int return, a host-and-int callback, and an unlisted host call all fail before Echo. A public method with an unsupported signature does not block OnStart. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 121/121. A later host-and-int callback may call a declared private assembly. OnTick(40) echoes 41. string.IsNullOrEmpty inside that private method is rejected before OnStart, and Echo is not called. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 123/123. A later host-and-int callback may construct a type declared in a private assembly. OnTick(41) echoes 41. string.IsNullOrEmpty inside that constructor is rejected before OnStart, and Echo is not called. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 124/124. Rejecting a later callback before OnStart unloads the collectible context. The host method is not called. This is not an iOS result.

On 2026-10-17 the same desktop runtime suite stayed at 124/124 and the packaging suite stayed at 171/171. A rejected later callback is named in the error. The runtime text contains The callback OnTick. The package text contains OnTick calls a method. This is not an iOS result.

On 2026-10-17 the desktop runtime suite stayed at 124/124. A rejected later callback names both the callback and the member. The OnTick text contains IsNullOrEmpty. An unlisted host call contains .Other. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 125/125. An OnStart host failure still reaches the host, keeps the failure text, and does not return the session. The collectible context is unloaded. This is not an iOS result.

On 2026-10-17 the desktop runtime suite stayed at 125/125. A later callback into a private assembly that calls System.IO.File.ReadAllText is rejected before OnStart. The text names OnTick and ReadAllText. The collectible context unloads. This is not an iOS result.

On 2026-10-17 packaging tests passed 172/172. PackageBuilder.Compile rejects a supported later callback that calls a method outside the allowed list. OnStop calling SpawnEntity fails before a package is published. The error names OnStop and SpawnEntity. OnStart itself only calls Log. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 126/126. HostContractSession.Open rejects a package directory that contains a file not listed in the manifest. An extra.dll beside a valid entry is rejected before the host method runs. The message contains missing or extra files. A listed entry and its declared dependencies still load. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 127/127. HostContractSession.Open rejects a private dependency whose assembly identity does not match the manifest. The file hash can still match. The message contains identity mismatch and lib.dll. The host method does not run. A dependency whose manifest identity matches the image still loads. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 128/128. HostContractSession.Open rejects a manifest whose format version is not current, even after the content hash is recomputed. The same check also requires the current API version and input profile. The message contains Unsupported package format. The host method does not run. A current manifest still loads. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 129/129. HostContractSession.Open rejects an entry larger than the assembly size limit before loading it. The message contains size limits. The host method does not run. The same read also stops when the listed files would pass the package size limit. A normal-sized entry still loads. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 131/131. HostContractSession.Open rejects a filesystem link in the package directory before loading. Replacing the entry with a symbolic link does not run the host method. The message contains filesystem links. A directory nested past the package limit is also rejected. The message contains nesting limit. A normal package still loads. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 132/132. HostContractSession.Open rejects a producer input kind other than source or il, even after the content hash is recomputed. The message contains Unsupported producer input kind. The host method does not run. An il producer still loads. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 133/133. HostContractSession.Open rejects a producer with no references, even after the content hash is recomputed. The message contains Producer references identities are required and bounded. The host method does not run. The same check requires sources, and compiler identities when the input kind is source. An il producer with one reference and one source still loads. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 134/134. HostContractSession.Open rejects a blank package id, even after the content hash is recomputed. The message contains Missing or oversized id. The host method does not run. The same check bounds the entry type and requires SHA-256 hashes and a bounded file list. A normal id still loads. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 135/135. HostContractSession.Open rejects a producer whose references do not name the supplied contract assembly exactly once, even after the content hash is recomputed. A reference to Other.Contract does not run the host method. The message contains exactly one shared host contract. The check uses the supplied contract assembly, not a fixed RuneCLR.Abstractions name. A producer that names that assembly once still loads. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 136/136. HostContractSession rejects an entry assembly whose simple name matches the supplied contract assembly. The host method does not run. The message contains duplicates the host contract assembly and the assembly name. A framework spoof such as System.IO still reports the spoof message. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 137/137. HostContractSession.Open rejects a blank producer tool, even after the content hash is recomputed. The message contains Missing or oversized producer.tool. The host method does not run. The same check bounds the producer tool version. A normal tool name still loads. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 138/138. HostContractSession.Open rejects an entry path whose segment ends with a dot, even after the content hash is recomputed. bad./echo.dll does not run the host method. The message contains canonical relative DLL. The same check rejects control characters, reserved path punctuation, and segments that end with a space. A path longer than 240 characters is missing or oversized. A normal echo.dll path still loads. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 139/139. HostContractSession.Open rejects a producer reference that keeps the contract assembly name but changes its version, even after the content hash is recomputed. The host method does not run. The message contains exactly one shared host contract. A reference whose full identity matches the supplied contract still loads. This is not an iOS result.

On 2026-10-17 packaging tests passed 173/173. PackageBuilder.Compile can produce a host-contract package that HostContractSession.Open runs. The source uses RuneCLR.IMapContext with Log and SpawnEntity allowed. OnStart logs ok and spawns fixture. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 174/174. A compiled host-contract package can run a later callback after Open. OnStart logs ok, and Invoke OnStop logs stopped through the same IMapContext. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 175/175. A compiled host-contract package can return an int from a later callback. OnStart logs ok. InvokeInt Measure(40) returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 176/176. A compiled host-contract package can take the host and an int in a later callback. OnStart logs ok. Invoke Report(41) calls Charge with 41. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 177/177. A compiled host-contract package can call a declared private assembly from a later callback. OnStart logs ok. InvokeInt Measure(40) calls SharedHelper.AddOne and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 178/178. A compiled host-contract package can let one declared private assembly call another from a later callback. OnStart logs ok. InvokeInt Measure(40) goes through First.Through to Second.AddOne and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 179/179. A compiled private assembly can call back into the host-contract entry. OnStart logs ok. InvokeInt Measure(40) goes through Helper.Through to GameScript.FromEntry and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 180/180. A compiled host-contract package can construct an author type from a later callback. OnStart logs ok. InvokeInt Measure(41) constructs Box and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 181/181. PackageBuilder.Compile rejects a later callback that constructs System.InvalidOperationException. The message names Report and InvalidOperationException..ctor. No package directory is published. Publishing and staging cleanup retry an access-denied move or delete a few times. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 182/182. A compiled host-contract package can construct a type declared in a private assembly. OnStart logs ok. InvokeInt Measure(41) constructs Box from the SharedBox assembly and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 183/183. An imported host-contract IL package opens and returns an int. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok. InvokeInt Measure(40) returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 184/184. Imported host-contract IL can call a declared private assembly. The entry and SharedImport are submitted as IL. OnStart logs ok. InvokeInt Measure(40) calls AddOne and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 185/185. PackageBuilder.Import rejects host-contract IL whose later callback constructs System.InvalidOperationException. The message names Report and InvalidOperationException..ctor. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 186/186. Imported host-contract IL can let a private assembly call back into the entry. OnStart logs ok. InvokeInt Measure(40) goes through Helper.Through to GameScript.FromEntry and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 187/187. The operator CLI compile command writes a host-contract package. The test runs RuneCLR.PackageTool with --host-interface RuneCLR.IMapContext and --allowed-method Log. OnStart logs ok. InvokeInt Measure(40) returns 41. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 188/188. The operator CLI compile command rejects a later callback that constructs System.InvalidOperationException. The process exits 2. The error names Report and InvalidOperationException..ctor. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 189/189. The operator CLI import command writes a host-contract package from submitted IL. The assembly is not compiled by the package tool. OnStart logs ok. InvokeInt Measure(40) returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 190/190. The operator CLI import command rejects submitted IL whose later callback constructs System.InvalidOperationException. The process exits 2. The error names Report and InvalidOperationException..ctor. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 191/191. The operator CLI compile command accepts one --dependency and writes a host-contract package. OnStart logs ok. InvokeInt Measure(40) calls SharedHelper.AddOne and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 192/192. The operator CLI import command accepts one --dependency and writes a host-contract package from submitted IL. The entry and SharedCliImport are not compiled by the package tool. OnStart logs ok. InvokeInt Measure(40) calls AddOne and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 193/193. The operator CLI validate command accepts a host-contract manifest. The process exits 0 and prints the package id HostCliValidate and its content hash. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 194/194. The operator CLI validate command rejects a host-contract manifest whose id changed without a new content hash. The process exits 2. The error contains content identity. The package directory remains. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 195/195. The operator CLI validate command rejects a host-contract package whose entry file byte changed. The manifest content hash is left unchanged. The process exits 2. The error names that file and contains hash mismatch. The package directory remains. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 196/196. The operator CLI validate command rejects a host-contract package that contains a file absent from the manifest. The process exits 2. The error contains missing or extra files. The extra file remains. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 197/197. The operator CLI compile command rejects a host-contract build that supplies only --host-interface or only --allowed-method. The process exits 2. The error says both must be present. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 198/198. The operator CLI --help exits 0 and mentions --host-interface. An unknown command, compile without --framework-refs, and a repeated --id each exit 2. The errors name the unknown command, the missing option, and the repeated option. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 199/199. The operator CLI compile command rejects a repeated allowed method and a blank allowed method. Both processes exit 2. The error says the methods must be nonempty and unique. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 200/200. The operator CLI compile command rejects a source directory that also contains a .csproj file. The process exits 2. The error says source input must contain only regular .cs files. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 201/201. The operator CLI compile command rejects a source tree nested past 16 directories. The process exits 2. The error says source directories exceed the nesting limit. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 202/202. The operator CLI compile command rejects a source directory that is a filesystem link and a source directory that contains one. Both processes exit 2. The error says source directories cannot contain filesystem links. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 203/203. The operator CLI compile command rejects 65 source files and one source file of 8000001 bytes. Both processes exit 2. The error says the source directory exceeds the compiler input limits. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 204/204. The operator CLI rejects an unknown option, an option with no value, and a value that starts with --. Each process exits 2. The error says unknown option or missing value. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 205/205. The operator CLI compile command rejects a source file that names MissingType. The process exits 2. Standard output contains success false and CS0246. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 206/206. The operator CLI import command rejects a file that is not a managed assembly. The process exits 2. The error says the image is a malformed managed assembly. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 207/207. The operator CLI import command rejects an assembly that does not define GameScript. The process exits 2. The error says that entry type was not found. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 208/208. A compiled host-contract package can take only an int in a later callback. OnStart logs ok. Invoke Apply(41) calls Charge with 41. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 209/209. A compiled host-contract package can take the host and an int and return an int. OnStart logs ok. InvokeInt Measure(40) calls Charge with 40 and returns 41. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 210/210. Imported host-contract IL can take the host and an int and return an int. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok. InvokeInt Measure(40) calls Charge with 40 and returns 41. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 211/211. Imported host-contract IL can take only an int in a later callback. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok. Invoke Apply(41) calls Charge with 41. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 212/212. Imported host-contract IL can take the host and an int in a later void callback. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok. Invoke Report(41) calls Charge with 41. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 213/213. Imported host-contract IL can run a later callback after Open. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok, and Invoke OnStop logs stopped through the same IMapContext. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 214/214. Imported host-contract IL can construct an author type from a later callback. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok. InvokeInt Measure(41) constructs Box and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 215/215. Imported host-contract IL can construct a type declared in a private assembly. The entry and SharedImportBox are submitted as IL, not compiled by PackageBuilder. OnStart logs ok. InvokeInt Measure(41) constructs Box and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 216/216. Imported host-contract IL can let one declared private assembly call another. The entry, SharedImportFirst, and SharedImportSecond are submitted as IL, not compiled by PackageBuilder. OnStart logs ok. InvokeInt Measure(40) goes through First.Through to Second.AddOne and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 217/217. Imported host-contract IL can run OnStart with Log and SpawnEntity. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok and spawns fixture. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 218/218. A compiled host-contract package can call Charge from OnStart. OnStart logs ok and charges 7. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 219/219. Imported host-contract IL can call Charge from OnStart. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok and charges 7. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 220/220. A compiled host-contract package can spawn and destroy an entity from OnStart. OnStart logs ok, spawns fixture, and destroys that entity. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 221/221. Imported host-contract IL can spawn and destroy an entity from OnStart. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok, spawns fixture, and destroys that entity. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 222/222. A compiled host-contract package can read MapId from OnStart. The allowed names are Log and get_MapId. OnStart logs fixture. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 223/223. Imported host-contract IL can read MapId from OnStart. The assembly is submitted as IL, not compiled by PackageBuilder. The allowed names are Log and get_MapId. OnStart logs fixture. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 224/224. A compiled host-contract package can store a spawned EntityId and destroy it from a later callback. OnStart logs ok and spawns fixture. Invoke Release destroys that entity. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 225/225. Imported host-contract IL can store a spawned EntityId and destroy it from a later callback. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok and spawns fixture. Invoke Release destroys that entity. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 226/226. A compiled host-contract package rejects an allow list that names MapId instead of get_MapId. The error names OnStart and get_MapId. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 227/227. Imported host-contract IL rejects an allow list that names MapId instead of get_MapId. The assembly is submitted as IL, not compiled by PackageBuilder. The error names OnStart and get_MapId. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 228/228. A compiled host-contract package can read MapId from a later callback. OnStart logs ok. Invoke OnStop logs fixture through the stored IMapContext. Log and get_MapId are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 229/229. Imported host-contract IL can read MapId from a later callback. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok. Invoke OnStop logs fixture through the stored IMapContext. Log and get_MapId are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 230/230. The operator CLI compile command accepts --allowed-method get_MapId. OnStart logs fixture. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 231/231. The operator CLI import command accepts --allowed-method get_MapId. The assembly is submitted as IL, not compiled by the package tool. OnStart logs fixture. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 232/232. The operator CLI compile command rejects --allowed-method MapId when the script reads the property. The process exits 2. The error names OnStart and get_MapId. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 233/233. The operator CLI import command rejects --allowed-method MapId when the assembly reads the property. The assembly is submitted as IL, not compiled by the package tool. The process exits 2. The error names OnStart and get_MapId. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 234/234. A compiled host-contract package can let a declared private assembly read MapId. OnStart passes the host to SharedMap.Id and logs fixture. Log and get_MapId are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 235/235. Imported host-contract IL can let a declared private assembly read MapId. The entry and SharedImportMap are submitted as IL, not compiled by PackageBuilder. OnStart passes the host to SharedMap.Id and logs fixture. Log and get_MapId are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 236/236. A compiled host-contract package can let a declared private assembly call Charge. OnStart logs ok and passes the host to SharedBill.Bill, which charges 7. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 237/237. Imported host-contract IL can let a declared private assembly call Charge. The entry and SharedImportBill are submitted as IL, not compiled by PackageBuilder. OnStart logs ok and passes the host to SharedBill.Bill, which charges 7. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 238/238. A compiled host-contract package can let a declared private assembly spawn an entity. OnStart logs ok, passes the host to SharedSpawn.Create, and destroys the returned entity. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 239/239. Imported host-contract IL can let a declared private assembly spawn an entity. The entry and SharedImportSpawn are submitted as IL, not compiled by PackageBuilder. OnStart logs ok, passes the host to SharedSpawn.Create, and destroys the returned entity. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 240/240. A compiled host-contract package can let a declared private assembly spawn and destroy an entity. OnStart logs ok and passes the host to SharedLife.Cycle. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 241/241. Imported host-contract IL can let a declared private assembly spawn and destroy an entity. The entry and SharedImportLife are submitted as IL, not compiled by PackageBuilder. OnStart logs ok and passes the host to SharedLife.Cycle. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 242/242. A compiled host-contract package can let a declared private assembly call Log. OnStart logs ok and passes the host to SharedNote.Note, which logs from-private. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 243/243. Imported host-contract IL can let a declared private assembly call Log. The entry and SharedImportNote are submitted as IL, not compiled by PackageBuilder. OnStart logs ok and passes the host to SharedNote.Note, which logs from-private. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 244/244. A compiled host-contract package can pass the host from one private assembly into a second that calls Log. OnStart logs ok. First.Through reaches Second.Note, which logs from-second. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 245/245. Imported host-contract IL can pass the host from one private assembly into a second that calls Log. The entry, SharedImportLogFirst, and SharedImportLogSecond are submitted as IL, not compiled by PackageBuilder. OnStart logs ok. First.Through reaches Second.Note, which logs from-second. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 246/246. A compiled host-contract package rejects a second private assembly that calls SpawnEntity when only Log is allowed. The error names OnStart and SpawnEntity. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 247/247. Imported host-contract IL rejects a second private assembly that calls SpawnEntity when only Log is allowed. The assemblies are submitted as IL, not compiled by PackageBuilder. The error names OnStart and SpawnEntity. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 248/248. A compiled host-contract package can let a second private assembly read MapId. OnStart passes the host through First.Through to Second.Id and logs fixture. Log and get_MapId are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 249/249. Imported host-contract IL can let a second private assembly read MapId. The entry, SharedImportIdFirst, and SharedImportIdSecond are submitted as IL, not compiled by PackageBuilder. OnStart passes the host through First.Through to Second.Id and logs fixture. Log and get_MapId are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 250/250. A compiled host-contract package can let a second private assembly call Charge. OnStart logs ok and passes the host through First.Through to Second.Bill, which charges 7. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 251/251. Imported host-contract IL can let a second private assembly call Charge. The entry, SharedImportBillFirst, and SharedImportBillSecond are submitted as IL, not compiled by PackageBuilder. OnStart logs ok and passes the host through First.Through to Second.Bill, which charges 7. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 252/252. A compiled host-contract package can let a second private assembly spawn and destroy an entity. OnStart logs ok and passes the host through First.Through to Second.Cycle. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 253/253. Imported host-contract IL can let a second private assembly spawn and destroy an entity. The entry, SharedImportLifeFirst, and SharedImportLifeSecond are submitted as IL, not compiled by PackageBuilder. OnStart logs ok and passes the host through First.Through to Second.Cycle. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 254/254. A compiled host-contract package can return an EntityId from a second private assembly. OnStart logs ok, passes the host through First.Through to Second.Create, and destroys the returned entity. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 255/255. Imported host-contract IL can return an EntityId from a second private assembly. The entry, SharedImportReturnFirst, and SharedImportReturnSecond are submitted as IL, not compiled by PackageBuilder. OnStart logs ok, passes the host through First.Through to Second.Create, and destroys the returned entity. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 256/256. The operator CLI compile command accepts two --dependency arguments. OnStart logs ok and passes the host through First.Through to Second.Note, which logs from-second. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 257/257. The operator CLI import command accepts two --dependency arguments. The assemblies are submitted as IL, not compiled by the package tool. OnStart logs ok and passes the host through First.Through to Second.Note, which logs from-second. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 258/258. The operator CLI validate command accepts a host-contract package with two private assemblies, then rejects that package after one byte in the second assembly changes. The error names the hash mismatch and lib/SharedCliSealSecond.dll. The changed file stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 259/259. The operator CLI validate command accepts a host-contract package with one private assembly. After the manifest assembly identity is changed to Version=9.0.0.0 and the content hash is recomputed, validate exits 2. The error names identity mismatch and lib/SharedCliIdentity.dll. The dependency file stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 260/260. The operator CLI validate command accepts a host-contract package, then rejects it after the entry assembly is replaced by a filesystem link to the moved DLL. The error names filesystem links. The link and its target stay in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 261/261. The operator CLI validate command accepts a host-contract package, then rejects it after 17 nested directories are added inside the package. The error names Package directories and the nesting limit. The nested directory stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 262/262. The operator CLI validate command accepts a host-contract package, then rejects it after the entry bytes are replaced by an assembly named System.IO and the file and content hashes are recomputed. The error names spoofs and System.IO. The entry file stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 263/263. The operator CLI validate command accepts a host-contract package, then rejects it after the entry file is extended past the assembly size limit. The error names size limits. The oversized file stays in place and is not hashed. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 264/264. The operator CLI validate command accepts a host-contract package, then rejects it after the format version is increased and the content hash is recomputed. The error names Unsupported package format. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 265/265. The operator CLI validate command accepts a host-contract package, then rejects it after the producer input kind is changed to native and the content hash is recomputed. The error names Unsupported producer input kind. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 266/266. The operator CLI validate command accepts a host-contract package, then rejects it after the producer references are removed and the content hash is recomputed. The error names Producer references identities are required. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 267/267. The operator CLI validate command accepts a host-contract package, then rejects it after the producer references name Other.Contract instead of the shared host contract and the content hash is recomputed. The error names exactly one shared host contract. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 268/268. The operator CLI validate command accepts a host-contract package, then rejects it after the package id is a single space and the content hash is recomputed. The error names Missing or oversized id. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 269/269. The operator CLI validate command accepts a host-contract package, then rejects it after the producer tool is a single space and the content hash is recomputed. The error names Missing or oversized producer.tool. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 270/270. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path is changed to ../entry.dll and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 271/271. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path is changed to bad./echo.dll and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 272/272. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path is changed to entry.txt and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 273/273. The operator CLI validate command accepts a host-contract package, then rejects it after the file list names other.dll instead of the entry and the content hash is recomputed. The error names exactly match the entry. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 274/274. The operator CLI validate command accepts a host-contract package, then rejects it after the file list keeps the entry path but stores a different SHA-256 and the content hash is recomputed. The error names exactly match the entry. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 275/275. The operator CLI validate command accepts a host-contract package with one private assembly, then rejects it after that dependency path is changed to ../lib.dll and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 276/276. The operator CLI validate command accepts a host-contract package with one private assembly, then rejects it after that dependency is replaced by the bytes 1, 2, 3, 4 and the file and content hashes are recomputed. The error names PE. The dependency file stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 277/277. The operator CLI validate command accepts a host-contract package with one private assembly, then rejects it after that dependency is replaced by an assembly named System.IO and the file hash, content hash, and declared assembly identity are updated to match. The error names spoofs and System.IO. The dependency file stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 278/278. The operator CLI validate command accepts a host-contract package with one private assembly, then rejects it after that dependency is replaced by another assembly named HostCliDup and the file hash, content hash, and declared assembly identity are updated to match. The error names duplicates the entry assembly identity. The dependency file stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 279/279. The operator CLI validate command accepts a host-contract package with one private assembly, then rejects it after that dependency is declared as RuneCLR.Abstractions and the content hash is recomputed. The dependency bytes stay unchanged. The error names contract or duplicate private assembly identity. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 280/280. The operator CLI validate command accepts a host-contract package with two private assemblies, then rejects it after the second dependency is declared with the first dependency assembly identity and the content hash is recomputed. The dependency bytes stay unchanged. The error names contract or duplicate private assembly identity. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 281/281. The operator CLI validate command accepts a host-contract package with one private assembly, then rejects it after that dependency file is deleted. The manifest is left unchanged. The error names missing or extra files. The manifest stays in place and the dependency file stays absent. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 282/282. The operator CLI validate command accepts a host-contract package, then rejects it after the producer tool version is a single space and the content hash is recomputed. The error names Missing or oversized producer.toolVersion. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 283/283. The operator CLI validate command accepts a host-contract package, then rejects it after the producer sources are removed and the content hash is recomputed. The error names Producer sources identities are required. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 284/284. The operator CLI validate command accepts a source host-contract package, then rejects it after the producer compiler identities are removed and the content hash is recomputed. The error names Producer compiler identities are required. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 285/285. The operator CLI validate command accepts a source host-contract package, then rejects it after the producer compiler list is two copies of the first compiler identity and the content hash is recomputed. The error names Duplicate producer compiler input name. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 286/286. The operator CLI validate command accepts a host-contract package, then rejects it after the producer source list is two copies of the first source identity and the content hash is recomputed. The error names Duplicate producer sources input name. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 287/287. The operator CLI validate command accepts a host-contract package, then rejects it after the producer reference list is two copies of the first reference identity and the content hash is recomputed. The error names Duplicate producer references input name. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 288/288. The operator CLI validate command accepts a host-contract package, then rejects it after a second producer reference uses another input name but the same RuneCLR.Abstractions identity and the content hash is recomputed. The error names exactly one shared host contract. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 289/289. The operator CLI validate command accepts a host-contract package, then rejects it after the first producer source digest is changed to invalid and the content hash is recomputed. The error names SHA-256 hexadecimal digest. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 290/290. The operator CLI validate command accepts a host-contract package, then rejects it after the first producer source name is a single space and the content hash is recomputed. The error names Missing or oversized input name. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 291/291. The operator CLI validate command accepts a host-contract package, then rejects it after the first producer reference assembly identity is changed to NotCanonical and the content hash is recomputed. The error names full canonical assembly identity. This does not compare contract versions. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 292/292. The operator CLI validate command accepts a host-contract package, then rejects it after the file list repeats the entry path with the same entry hash and the content hash is recomputed. The error names Duplicate package path and that entry path. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 293/293. The operator CLI validate command accepts a host-contract package, then rejects it after the entry file is deleted. The manifest is left unchanged. The error names missing or extra files. The manifest stays in place and the entry file stays absent. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 294/294. The operator CLI validate command accepts a host-contract package, then rejects it after the API version is increased while the format version stays current and the content hash is recomputed. The error names API version. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 295/295. The operator CLI validate command accepts a host-contract package, then rejects it after the input profile is changed to other while the format version and API version stay current and the content hash is recomputed. The error names input profile. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 296/296. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path is changed to bad /echo.dll and the content hash is recomputed. The segment before the slash ends with a space. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 297/297. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path is changed to bad//echo.dll and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 298/298. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path uses a backslash instead of a forward slash and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 299/299. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path is changed to bad:echo.dll and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 300/300. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path is changed to echo?.dll and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 301/301. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path contains a tab and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 302/302. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path is changed to ./echo.dll and the content hash is recomputed. The segment is only a dot, not a segment that ends with a dot. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.
