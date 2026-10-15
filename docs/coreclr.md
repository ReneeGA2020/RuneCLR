# CoreCLR interpreter integration

## Why it matters

The primary product goal is C# iOS hot-update scripting, with UGC management
built on top. The first-party direction is downloading and loading independently
built R2R update modules alongside non-updateable R2R code, with interpretation
for methods without usable precompiled bodies. They share one managed
type/object model. Restricted UGC currently chooses interpretation for management
control. Formal same-source builds, independent R2R module composition, post-install
delivery and object compatibility matrices remain separate milestones. See
[product direction](product-direction.md).

Desktop JIT runtimes can execute newly downloaded IL. A pure AOT runtime cannot
generally execute arbitrary new IL that has no precompiled native body. An IL
interpreter provides an execution path on platforms that prohibit dynamic native
code generation, including iOS. Dynamic assembly loading and collectible-context
support must also be verified for the selected platform and publishing pipeline.

Upstream references:

- [CoreCLR interpreter tracking issue](https://github.com/dotnet/runtime/issues/112748)
- [CoreCLR on WebAssembly](https://github.com/dotnet/runtime/issues/121511)
- [.NET 11 runtime changes](https://learn.microsoft.com/en-us/dotnet/core/whats-new/dotnet-11/runtime)
- [CoreCLR build workflow](https://github.com/dotnet/runtime/blob/main/docs/workflow/building/coreclr/README.md)
- [RuneCLR runtime fork targets](runtime-fork.md)

## R2R plus interpreter: design and delivery evidence

The [upstream tracking issue](https://github.com/dotnet/runtime/issues/112748)
explains that R2R still has cases that crossgen cannot precompile. The interpreter
provides execution without requiring a JIT for those methods. The maintainer
[clarified](https://github.com/dotnet/runtime/issues/112748#issuecomment-2681260591):

> Running everything interpreted is not the end goal. We will have a combination
> of precompiled managed code with only some of the code being interpreted.

That explanation identifies R2R as the precompiled code, rather than NativeAOT.
The [iOS workflow](https://github.com/dotnet/runtime/blob/main/docs/workflow/building/coreclr/ios.md)
lists both interpreter and R2R execution modes. Neither statement alone proves
execution of a downloaded R2R native body after application installation.

RuneCLR's first-party delivery acceptance must bind the post-install downloaded
image to actual native R2R method entries, separately observe expected interpreter
fallback, and document the target's packaging/signing/loading route. Loading an
R2R-marked file while interpreting all its methods is insufficient evidence of
R2R native execution. Physical iOS results remain required for device claims.

## Baseline

The prototype targets `net11.0`. Initial local verification used the
installed .NET 11 Preview 6 SDK; later official RC1 validation is recorded in
the handoff. `global.json` sets the compatible minimum SDK and permits later
.NET 11 feature-band/prerelease SDKs through `latestFeature`, including RC1.
It does not pin the separate runtime checkout's product version. CI selects the latest .NET 11 prerelease SDK
available to `setup-dotnet`. No .NET installation is modified, no upstream
runtime binaries are replaced, and no CoreCLR source is vendored in this commit.

Interpreter configuration is runtime-build-dependent. An environment variable
such as `DOTNET_InterpMode` must not be treated as proof that a shipping runtime
supports or selected interpretation: unsupported configuration can be ignored.
Runtime execution traces, interpreter breakpoints, or equivalent diagnostics
must establish which methods execute through the interpreter. The demo therefore
reports its runtime version and makes no interpretation claim.

## Verified desktop baseline and next platform experiment

On 2026-10-12, a pinned unpatched Checked CoreCLR build passed all twelve
lifecycle tests with interpreted maps, including private dependency versions,
generics, failure cleanup and a map compiled after the host. Mode 1 permits
CoreLib JIT; R2R and tiering were disabled, successful interpreter bytecode dumps
were checked, and map JIT compilation was not observed. The build, mode
definitions, launcher and raw evidence references are recorded in
[the desktop experiment](interpreter-experiment.md).

Full-framework mode 3 hits an object-reference assertion in the selected build.
The previous `AssemblyDependencyResolver` API is marked unsupported on
Android and iOS. RuneCLR now uses explicit [package resolution](package-resolution.md)
without desktop hostpolicy. The expanded Windows lifecycle suite passes 22/22
on the same private Checked mode 1 layout, with interpreter bytecode evidence
for map callbacks, private helpers and generic methods. The next platform
experiment must verify dynamic
loading and repeated collection on a real iOS device, accounting for trimming,
runtime packaging, missing precompiled methods and framework APIs. Desktop
success does not establish that capability.

The [iOS simulator follow-up](ios-simulator-experiment.md) runs the real 21/22-case
harness with post-install non-R2R IL and dynamic compilation disabled. The
Preview 6 and official RC1 all-host-R2R interface paths crash; leaving RuneCLR.Runtime as IL
passes while trusted framework/bridge/tests/contract stay R2R. The same original
all-host-R2R harness also crashes on the unpatched .NET 12 Debug source build.
Its selective Runtime-IL full harness passes 21/21 and post-install 22/22
with positive script/private-generic diagnostics and successful callback IR
dumps; the earlier mini-fixture passed 20/20 separately. Preserve these distinct
configurations; the later candidate acceptance is recorded below, and
physical-device acceptance remains outstanding.
The [subsequent native-interface investigation](ios-r2r-investigation.md)
reproduces the production PC-zero fault under LLDB; smaller R2R interface
controls retire twenty contexts successfully. Ordinary retirement and a
MapTick-shaped argument alone do not reproduce it. A dedicated runtime-worktree
comparison keeps all managed and framework bytes unchanged: original,
diagnostic-off and trace-only native runtimes crash, while skipping
collectible-target cache insertion passes 21/21. This localizes the failure to
cached dispatch and excludes logging alone as the passing explanation. The
Debug-only diagnostic remains an experimental control. The later
[minimal reproduction](ios-r2r-minimal.md) captures stale MethodTable and
entrypoint mappings surviving retirement, followed by type-address reuse and
zero precode data at the fault. A separate
[default-behavior candidate](ios-r2r-fix-candidate.md) avoids publishing
collectible/dynamic-interface receiver mappings. Its
[five-group Debug acceptance](ios-r2r-fix-validation.md) passes the unchanged
full R2R lifecycle 21/21, twenty collected sessions with two and three ticks,
and controlled packages 15/15; the original negative control still crashes.
The candidate is privately built and unmerged. Its
[fresh native Debug rebuild](ios-r2r-clean-build.md) also passes that five-group
comparison independently. The later [matching Release acceptance](ios-r2r-release-validation.md)
passes lifecycle 21/21 and twenty collected sessions with sixty probe calls,
with sampled native interpreter entries for the three probe callbacks. The
[Release controlled player](ios-r2r-release-packages.md) separately passes 15/15
functional cases; probe entries do not establish package/helper execution.
Four [official generated managed runners](ios-r2r-official-managed-tests.md)
execute on the patched Debug simulator using a private native wrapper and
the retained managed-target workaround. Complete official mobile-runner
integration, full Release shipping packs, performance and real-device
validation remain open.
The [read-only source analysis](ios-r2r-cache-analysis.md) separates cache
publication, hot invocation and target lifetime. Related
[official Windows upstream controls](ios-r2r-upstream-validation.md) now pass
16/16 project executions with JIT/interpreter and requested cached dispatch;
their passing result does not reproduce the ARM64 iOS failure.

The pinned official main source produces .NET 12, using its own .NET 11 RC1 SDK
as a build tool. RuneCLR's target framework and historical Preview 6 package
tests do not identify that source runtime's version. Official .NET 11 RC1
package comparison passes Android and selective iOS lifecycle independently
of the primary source lane.

## Runtime patch boundary

The [accepted execution strategy](execution-strategy.md) selects interpretation
for UGC and its private dependencies across the target platforms. Host/framework
native code remains allowed. The full-framework mode 3 failure does not establish
a blocker for selective UGC interpretation. Method-set environment switches are
experiment tools, not an author-resistant per-session execution policy. #5/#6
must establish selection coverage and prevent map JIT/R2R bypasses.

The [source-reviewed execution-selection plan](runtime-execution-selection.md)
now has a [privately implemented candidate](runtime-execution-selection-candidate.md)
and [matching Windows acceptance](runtime-execution-selection-build.md):
collectible bodies are required in mode 0, actual interpreter skip cannot
fall back to native JIT, and a native trusted generic caller refuses the
concrete UGC inlinee. Lifecycle 22/22, player 15/15 and four official loader
regressions pass. The subsequent [matching session-policy build](runtime-session-policy-build.md)
now assigns immutable native policy at context creation and acknowledges it
before author loading. Mode 0 with diagnostic 0 passes marked/ordinary
controls, actual refusal/recovery, late private loading and unloading; the
production host passes 24/24 lifecycle and 15/15 package cases. This is a
private opt-in. The later [matching iOS simulator Release candidate](ios-session-policy-build.md)
combines the CID fix and session policy: current lifecycle 24/24, player 15/15
and 20 collected selection contexts pass with diagnostic 0. Eleven native
interpreter-entry samples cover nine installed-fixture method groups. The separate
[iOS refusal/recovery run](ios-session-policy-refusal.md) passes scoped compiler
SKIPPED refusal and twenty recovered collections. The matching
[Android Checked player](android-session-policy-validation.md) passes the current
production and five selection/refusal controls. Android Release has separate
[nine-group native-entry samples](android-session-policy-entry.md) and
[independent production/recovery/control acceptance](android-session-policy-release-production.md):
24/24 lifecycle, 15/15 packages, three collected samples, scoped refusal with
twenty recovered collections, ordinary JIT and unmarked native fallback.
Production/refusal method-entry coverage and physical-device acceptance remain
open; simulator/emulator acceptance does not close those gates.
The next [source-reviewed session instruction-budget plan](runtime-session-budget-plan.md)
covers native ownership, common dispatch accounting, irreversible termination,
catch/filter suppression, bounded CLR unwinding and finalizers. Its separate
[diagnostic meter increment](runtime-session-meter.md) now has a fresh Windows
x64 Checked build, per-binder native state and actual current-definition-owner
dispatch counts. Three meter/compatibility/concurrency processes, the original
policy matrix, lifecycle 24/24, player 15/15 and four official loader controls
pass on that same private layout. The meter is non-throwing and keeps counting
after remaining reaches zero; that meter increment implements no terminal semantics.
Computed-goto accounting has only source review, with no measured mobile port
or performance result. Script-inserted checkpoints or a catchable exception do
not establish termination.

The later [terminal prototype](runtime-session-terminal-prototype.md) adds a
separate creation-time opt-in on top of that meter. Matching Windows Checked
acceptance passes44 isolated lanes, including sticky exhaustion/catch/filter
suppression, bounded finite/infinite cleanup, constructor/cctor failures,
trusted catch and denied author reentry, two-context isolation and20 bad/good
recoveries. Existing production24/24 and player15/15, legacy policy20/20 and
four official loader controls pass on the same private candidate. Those
production/upstream contexts remain unmetered. A later
[host increment](host-instruction-budget.md) wires an explicit prototype-named
budget into MapRunOptions; its15 Windows cases/73 collections pass. The native
owner predicate keeps EH clauses/indices unchanged,
and exhausted actual cleanup funclets use their normal worker return path.
Cleanup truncation can omit author child/outer finally and leave arbitrary
author resources/locks unreleased. A later
[finalizer boundary](runtime-session-finalizer-boundary.md) at099dacd passes
nine Windows Checked recovery cases and six original-fatal-exception controls,
using the actual finalizer-slot MethodDesc owner before skipping or handling
termination. Full terminal capability, mobile budget acceptance and remaining
lifecycle topologies are still unestablished. Mobile/accounting performance
remains separate.

Design questions to resolve before calling this a sandbox:

- How is the active session associated with interpreted calls and nested host
  calls without leaking state to another session?
- Can a map catch a quota exception and continue indefinitely? A terminal budget
  violation needs runtime semantics that regain host control safely.
- Which map methods must remain interpreted, and how are JIT/R2R bypasses avoided?
- How are costly framework/native calls restricted, interrupted, or charged?
- How do constructors, exception filters, cleanup blocks, and finalizers behave
  during termination?
- How can allocations be attributed in a shared heap, including framework and
  host allocations on the map's behalf?

Hard termination must preserve runtime invariants; an arbitrary native jump out
of the interpreter is not a safe implementation. Keep proposed patches behind
explicit build/runtime switches, with regression tests and a documented upstream
base commit. Framework allowlists, source checks, and host API design complement
this work but are not substitutes for enforcement.
