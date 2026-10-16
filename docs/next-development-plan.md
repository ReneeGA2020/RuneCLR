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
stderr, and no physical device is reachable. The user will connect an iPhone XR
later; do not start a device install until then.









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

Step 2's simulator method-entry pair is measured: separate A and B processes
entered Business.Execute in their downloaded owners, and A's managed result
matched the source formulas on stderr. Physical iOS waits until the user
connects an iPhone XR. Do not boot another simulator or query devices for this
assignment.

Implement the first slice of step 3 on the desktop host. Add a trusted-update
selector that is not the UGC map policy: at process start, validate one
candidate's identity and content hash, reject a bad candidate before activation,
and keep the last known good version for the next start. Return a host-owned
error and do not retain the update exception. One selected version stays for
the process; do not unload native code or switch versions in-process.

