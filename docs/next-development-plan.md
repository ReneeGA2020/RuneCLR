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
ZIP are prepared. No upstream issue URL has been recorded. After actual filing,
record the URLs in the defect register. Keep private CID/generator fixes until
official replacements pass their recorded regression gates. Do not expand the
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
