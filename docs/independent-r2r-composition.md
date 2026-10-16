# Independent trusted IL/R2R composition - Windows

Measured on 2026-10-15 for step 1 of the [development plan](next-development-plan.md),
#13 and the initial object-interaction cases of #14. The focused fixture and
execution controls pass. **The combined native-R2R-and-collectible-unloading
acceptance is blocked by the selected upstream runtime.** On that measured result, RuneCLR does not pursue unloadable hot-update R2R: an update that must be unloaded stays interpreted, and ordinary first-party execution does not repeatedly unload old assemblies. This is a scoped
experiment, not a production trusted-update loader.

## Reproduce

From the RuneCLR root, with Python 3, the selected .NET 11 SDK, and the existing
clean, interpreter-enabled private Checked runtime build:

```powershell
py -3 -B eng/verify-trusted-composition.py --runtime E:/runtime --output artifacts/trusted-composition/my-new-run
```

Use a new output directory for every attempt. The driver builds the fixture,
crossgens each native module independently, runs five configurations, checks
native frames and interpreted helper entries, runs evidence and loader
regressions, and records source/toolchain/reference/product hashes and raw logs.
It returns **2** after successful controls because the combined collectible R2R
milestone remains blocked; unexpected failures return 1.
`--allow-known-collectible-blocker` changes only that expected final exit to 0;
`result.json` still records `milestoneComplete=false`.

The default SDK is the one selected by `dotnet`; `--sdk <dotnet.exe>` selects an
explicit SDK. No `global.json` is introduced. Runtime build preparation follows
the checked-out [CoreCLR build guide](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/docs/workflow/building/coreclr/README.md)
and the prior [desktop experiment](interpreter-experiment.md). The driver
validates the existing build/layout/source binding before execution; it does not
install or replace any system runtime.

## Inputs and boundaries

| Input | Measured configuration |
| --- | --- |
| RuneCLR starting revision | `5a1b060`, with the pre-existing handoff/plan edits preserved |
| Source SDK/compiler | `11.0.100-rc.2.26504.105`, default C# `15.0`, managed Release |
| Source reference framework | SDK's `net11.0` reference pack, `11.0.0-rc.2.26504.105` |
| Runtime source | clean `runeclr/interpreter-baseline`, `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` |
| Execution runtime | source product `.NET 12.0.0-dev`, Windows x64 Checked |
| CoreCLR/CoreLib/interpreter/JIT | exact Checked output hashes equal the private host's four matching files |
| Crossgen2 | matching `windows.x64.Checked/crossgen2-published/crossgen2.exe`, `12.0.0-dev` |
| Crossgen references | that private runtime's framework DLLs plus the specific contract/helper/private IL inputs |
| Native compilation | one input per invocation, Windows x64, `-O --map --mapcsv`; default per-assembly version bubble |

The .NET 11 source reference pack and the .NET 12 execution framework are
different recorded inputs. The source target does not identify the runtime
product version. `compiler-inputs.stdout` and `compiler-reference-hashes.json`
record the resolved compiler/language/reference paths; `reference-hashes.json`
records crossgen inputs. `inputs.json`, `runtime-CMakeCache.txt`, native commit
stamp, product PE information and command logs preserve the remaining bindings.
No runtime source was changed for this experiment.

The final measured run is
[`artifacts/trusted-composition/run-20261015-attempt6`](../artifacts/trusted-composition/run-20261015-attempt6/result.json).
Its [commands](../artifacts/trusted-composition/run-20261015-attempt6/commands.json),
[inputs](../artifacts/trusted-composition/run-20261015-attempt6/inputs.json),
[lane results](../artifacts/trusted-composition/run-20261015-attempt6/lanes.json),
[native process report](../artifacts/trusted-composition/run-20261015-attempt6/r2r-native.json),
[loader regressions](../artifacts/trusted-composition/run-20261015-attempt6/loader-controls/result.json)
and [evidence regressions](../artifacts/trusted-composition/run-20261015-attempt6/evidence-regressions.stdout)
are retained locally, including source snapshots and all earlier attempts. The
artifact directory is ignored by Git; the driver regenerates it.

Key measured SHA-256 bindings:

| Product | SHA-256 |
| --- | --- |
| `coreclr.dll` | `a9391606e33afcd41e2f117ea2c83f4a045c5e0bddc32320d50205a95fbf36dd` |
| `System.Private.CoreLib.dll` | `f3b765d3d04f816a418282bca88b05679084d70b42a4ff88533c7f0d71346db1` |
| `clrinterpreter.dll` | `6f9c915791e34054415ef7a3e0ff763f6abca0025432d3161d190e73f6d26ccc` |
| native `crossgen2.exe` | `2adf7303383fb7528a1e4f61d361bfca6df12f292c16b4d3222fe971843b85d9` |

This fixture uses trusted first-party code and ordinary CLR execution selection.
It does not request the UGC `RequireInterpreter` policy, native budgets, capability
allowlists or restricted package compilation. Environment variables select the
experiment; the entry evidence establishes what actually executed.

## Fixture and observed behavior

The [fixture](../eng/trusted-composition/README.md) has a shared CLR contract, a
non-updateable C# host, two update versions, version-specific private dependencies
with the same assembly name, and an intentionally IL-only helper. A and B link
exactly the same `Business.cs`; version behavior comes from their private
dependency. IL outputs are copied unchanged as crossgen inputs. The host,
contract, each update and each private dependency are separate R2R images. The
helper is never crossgened. There is no composite host/update image.

Every configuration runs A, B, A, failing A, recovered A. Each successful session
executes twice, checking module/private static counters 1 then 2. Fresh sessions
start at 1. A binds private version `1.0.0.0`, returns 101 and helper result 310;
B binds `2.0.0.0`, returns 202 and helper result 613. All five configurations
produce identical checked business results.

The actual host object crosses the boundary and returns with `ReferenceEquals`
identity preserved, including `Echo<object>`. An interface callback and a delegate
call return the expected values; `Echo<int>` checks a value-type generic case.
Each configuration makes nine host calls, nine interface callbacks, nine delegate
calls and eighteen generic calls, including calls before the managed failure.
The exception is owned by the update assembly; the host copies its type/message
and retains neither the exception nor author metadata/delegates/objects in its
report. A subsequent fresh session succeeds with reset private state.

| Configuration | Selected host method | Selected update/private methods | IL helper | Collected contexts |
| --- | --- | --- | --- | --- |
| IL updates, collectible, mode 1 | R2R, 9 active native frames | Interpreted | Interpreted | 5/5 |
| R2R updates, collectible, mode 1 | R2R, 9 active native frames | R2R explicitly refused; interpreted | Interpreted | 5/5 |
| Independent R2R, noncollectible, mode 1 | R2R, 9 active native frames | R2R, 9 update + 9 private active native frames | Interpreted | Unsupported, not asserted |
| IL desktop JIT control, mode 0 | Native post-call entry | Native JIT post-call entries | Native JIT post-call entry | 5/5 |
| R2R disabled control, noncollectible, mode 1 | Interpreted | Interpreted | Interpreted | Unsupported, not asserted |

The native positive lane requires update and private method-frame matches in
**each** session, including B, the second A, the failure and recovery. Each
activation uses a distinct physical copy: the selected runtime gives a native
R2R image one module owner. Noncollectible contexts remain loaded; fresh copies
reset their statics but do not establish unloading or bounded repeated-update
memory. Collectible collection is observed after the non-inlined execution
frame returns. Forced GC is diagnostic, outside a game loop.

## Execution proof and regression checks

Selected `[NoInlining]` methods `HostObject.Touch`, `UpdateModule.Execute` and
`PrivateLogic.Read` call a shared witness while their frames are active. It uses
`RtlCaptureStackBackTrace` and records only primitive addresses and mapped-image
paths. The assessor binds each return PC to the image SHA-256, allocation base,
executable page and PE section, AMD64 R2R RuntimeFunctions, and the exact selected
method's crossgen map range. These are active native frames inside the selected
R2R bodies, rather than preparation of a function pointer or an R2R header.
For example, the recorded host return RVA `0x5c2b` is inside `Touch` at
`0x5c10`, length 40; update A returns to `0x1744` inside `Execute` at
`0x1710`, length 462; private A returns to `0x1704` inside `Read` at
`0x16f0`, length 42. Per-session paths and full image hashes distinguish A/B
and subsequent activations.

`IlOnlyHelper.Compute` supplies checked arithmetic plus post-invocation
interpreter precode type 6 and a successful `Compiled method` bytecode dump in
every mixed/interpreted session. Mode 1 keeps R2R available; modes 2/3 disable it
in this source. Tiering and OSR are disabled throughout. The separate mode-0
control executes the same helper using native JIT entries and produces no helper
interpreter dump. The native stack walker yields no mapped fixture frames in
that JIT control; no stack-witness claim is made for that configuration.

The R2R-disabled mode-1 control exercises the same native-witness pipeline and
must lose all three selected R2R frame matches. The real-evidence regression
runner rejects missing frames, wrong image identity, corrupt PC arithmetic,
non-executable pages, wrong selected labels and shifted method ranges. It also
rejects helper precode without a successful dump, a dump without the called
interpreter entry, and an entry without invocation evidence. Loader controls
reject a mismatched private version and missing helper, then run fresh valid
sessions after each failure. All 10 real-evidence regressions pass; the four
loader processes produce two expected rejections and two successful recoveries,
with 10/10 recovered contexts collected. These dependency-error recoveries use
fresh processes; ordinary managed-failure recovery within one process is covered
by each fixture lane.

The ordinary repository baseline also passes with this SDK: lifecycle 37/37,
packaging 85/85, package player 15/15, pumped player 22/22 and six collected
sample sessions. These counts are separate from this focused fixture.
The [private matching-runtime lifecycle run](../artifacts/trusted-composition/private-lifecycle-20261015.log)
also passes 37/37 with mode 1 and R2R enabled. Its ordinary-selection result is
separate from the existing patched required-interpreter UGC acceptance. The
stock baseline log is retained under
`artifacts/trusted-composition/baseline-20261015-173621-14c6dd9b/verify.log`.

## Concrete blocker and next runtime experiment

Pinned upstream `src/coreclr/vm/readytoruninfo.cpp:588` explicitly returns NULL
for `pModule->IsCollectible()` and logs:

```text
Ready to Run disabled - collectible module
```

The R2R-marked collectible lane reproduces this message for the actual update
and private images, then positively observes their interpreted entries. Source
at line 774 also excludes collectible generic loader allocators from alternate
R2R placement. `AcquireImage` at line 467 publishes a module pointer into a
native image, and initialization at line 672 refuses an image already acquired
by another context. This is a runtime design constraint, not evidence of a UGC
restriction or failed R2R compilation.

Deleting only the collectible guard would leave ownership, native fixup/cache
lifetimes and generic placement unvalidated. On that measured result, RuneCLR does not pursue unloadable hot-update R2R: an update that must be unloaded stays interpreted, and ordinary first-party execution does not repeatedly unload old assemblies.
The first-party native lifetime keeps the selected noncollectible module loaded and retires session state only. That is an explicit choice from the measured blocker, not a silent substitution for collectible native unloading. The combined collectible R2R acceptance stays blocked and is not current work.

Windows native composition does not establish iOS downloaded-native execution,
packaging, signing, distribution approval or physical-device acceptance. Step 2
has not started as part of this contribution.

On 2026-10-16 one Windows run at artifacts/trusted-composition-timing-20261016 exited 0 and printed PASS five functional/execution controls. controlsPassed=true, milestoneComplete=false, and status=blocked-collectible-r2r. Startup, callback, and boundary microseconds accumulated across the sessions in that one process were il-collectible 47279/226526/13186, r2r-collectible 47760/222400/13389, r2r-native 44706/222359/0, il-jit-control 45633/345580/11850, and r2r-disabled-control 164025/282338/2. The same noncollectible semantics are r2r-disabled-control, with ReadyToRun off so the update module runs as interpreter IL, and r2r-native, which is noncollectible R2R. Their boundary totals are 2 and 0 microseconds. A total of 0 is under 1 microsecond. il-collectible and r2r-collectible are not noncollectible R2R. Collectible R2R remains refused by upstream. These figures are not a distribution across processes and not an iOS result. Issue 3 stays open. Issue 13 stays open.
