# iOS compiled interface dispatch investigation

On 2026-10-12, a controlled native-runtime comparison localized the retained
.NET 12 Debug all-host-R2R crash to the collectible-target cached interface
dispatch (CID) path. The unchanged full host crashes at PC 0 from
`MapRunner.Run+776` with the original runtime, with the diagnostic switch off,
and with logging alone. Disabling collectible-target cache insertion passes
the original 21/21 lifecycle tests. The diagnostic remains an experimental
control. A subsequent [minimal reproduction](ios-r2r-minimal.md) now captures
an old MethodTable/entrypoint mapping surviving retirement and matching reused
addresses with zero precode data. A separate
[conservative candidate](ios-r2r-fix-candidate.md) passes its
[five-group Debug simulator acceptance](ios-r2r-fix-validation.md). Full
upstream/release/device acceptance remains outstanding. The earlier small
native-host fixture described here is preserved as a successful control.

## Fixed source and evidence

The runtime remains unpatched at
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`, branch
`runeclr/iossim-baseline`, on the experiment Mac. No tracked runtime changes
were present; the pre-existing untracked Mono smoke directory was preserved.
The source runtime is .NET 12 Debug iOS simulator ARM64, built with its own
`11.0.100-rc.1.26420.103` SDK. This investigation does not mix official
Preview 6/RC1 native runtimes or compilers into the source lane.

The original harness package and crash are described in
[the simulator experiment](ios-simulator-experiment.md). Its historical
`preview6-experiment/pinned-debug-harness` directory contains a source .NET 12
comparison, despite the parent directory name. New experiments live beside it
under `ios-r2r-interface-repro-*`; diagnostic tools/logs are in `ios-r2r-tools`.

## Live production failure

The first LLDB capture, PID 87098, records:

```text
stop reason = EXC_BAD_ACCESS (code=1, address=0x0)
frame #0: 0x0000000000000000
frame #1: framework.dylib`RuneCLR_Runtime_RuneCLR_Runtime_MapRunner__Run + 776
x11 = 0x1494b8e60  [VSD] OnTick indirection cell
cell: [RhpInterfaceDispatch1, 0x138ff1620]
cache entry at 0x138ff1640: [MethodTable 0x139039778, target 0x139060030]
x13 = 0x139060030
x10 = 0; x12 = 0; pc = 0
lr = MapRunner.Run+776
```

The cell identifies the actual `IMapScript.OnTick` call. Its cache entry's
target is nonzero at the crash, so the available capture does not demonstrate
a zero cached target. A target precode whose indirect destination was retired
is a candidate explanation, but target memory/disassembly was not captured
before the first process was terminated. Registers can have changed after a
tail branch; they do not independently establish the final branch instruction.

Two further LLDB attempts did not reach the same crash before termination.
One sampled inside startup type loading, with `CHECK::t_count` as the top
symbol; this is an inconclusive diagnostic attempt, not an additional
successful PC-zero reproduction. The original package was preserved.

## Smaller controlled fixture

[The builder](../eng/ios-r2r-repro.py) creates one shared `IProbe` interface,
one no-inline trusted native `Driver.CallSite`, and one IL-only plugin outside
root TPA/composite inputs. The final callback has the same basic argument
shape as `MapTick`: a readonly `Tick(int, TimeSpan)` value. Each plugin context
owns its statics; the shared contract is cached before loading plugins.

The framework/native runtime and compiler come from the same pinned source
build. The previously measured framework composite is retained, while a new
small composite contains contract, entrypoint and optionally host. The IL-host
variant restores the original host IL. Logs retain compiler version, source
HEAD/status, source/native hashes, response files, native build/sign logs and
original managed inputs. A native `ProbeHost_Driver__CallSite` symbol is present
and execution diagnostics do not report it as interpreter compiled in the
native-host run; plugin method diagnostics do report interpretation.

| Comparison | Measured result |
| --- | --- |
| Native host, parameterless Tick, unload and diagnostic GC | 20/20 returned, statics reset, all contexts collected |
| Native host, Tick(int, TimeSpan), unload and diagnostic GC | 20/20 returned, all contexts collected; argument fields correct |
| Native host, Tick(int, TimeSpan), retain all contexts | 20/20 returned; collection intentionally not requested |
| Native host, Tick(int, TimeSpan), unload without forced GC | 20/20 returned; completed collection not asserted |
| IL host, Tick(int, TimeSpan), unload and diagnostic GC | 20/20 returned, all contexts collected |

The final four-group runner completed with exit 0, eighty returned cycles and
forty observed collections in its two collection groups. An earlier transport
from PowerShell appended a standalone carriage-return line, causing shell
exit 127 after all four managed groups passed. The script was transferred with
LF normalization and the entire four-group runner was rerun successfully;
`final-run-verified.log` and `final-verified.exit` retain that outcome.

Compact local evidence is in
`artifacts/ios-r2r-investigation/20261012/evidence.tar.gz` (SHA-256
`d4ad4e28382d49b92f415d4e40ebabd77abc725b8cf3c97957d5a20805e77505`).
It includes the full first native LLDB capture, subsequent inconclusive
captures, compiler inputs/hashes/sources and filtered managed event traces
with hashes/pointers to the original full IR logs. Final matrix results are
`run-20261012T131734Z/results.json` in the extracted evidence; the original
logs remain in the Mac's recorded `ios-r2r-interface-repro-final/run-*` paths.
All three newly created dedicated investigation simulators are shut down.
No owned debugger, probe process or crossgen background job remains.

Initial cold-loader variants asserted on a Debug lock-level check involving
`CrstNativeImageEagerFixups` and `CrstPendingTypeLoadEntry`, before any plugin
callback. Caching the contract assembly before collectible type loading, as
the production host already does, removed that separate assertion. Both
single-composite and split-composite cold variants had the assertion; it was
not evidence that splitting composites caused the original PC-zero crash.

The new plugin is built before installation. This reduction does not add
post-install-IL evidence; the full prior selective harness already has it.
The successful smaller runs show that ordinary collectible retirement and
the value-type callback shape alone are insufficient to trigger the retained
failure in these inputs. They do not establish that native interface dispatch
is safe for every collectible target.

## Run the reduction

Prerequisites are the matching pinned source build and preserved source-lane
framework package at the paths above. This is a reproduction against that
recorded experiment layout, not a general iOS publishing tool. The builder
refuses to overwrite an existing output directory. Run on the experiment Mac:

```sh
python3 eng/ios-r2r-repro.py /Users/editor/RuneCLR-experiments/20261012-iossim-coreclr /Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/ios-r2r-new-run
bash eng/ios-r2r-run.sh /Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/ios-r2r-new-run
```

[The runner](../eng/ios-r2r-run.sh) creates a dedicated simulator, runs native
host collect/retain/unload-without-forced-GC and IL-host collect comparisons,
checks managed pass markers/cycle counts, records JSON results and shuts down
its simulator on exit. `PROBE_CYCLES` can raise the default twenty cycles.
Actual collection after stack return is diagnostic; it is not a frame policy.

For live capture of the original production package, launch with
`xcrun simctl launch --wait-for-debugger <owned-simulator> org.runeclr.pinned.debug.harness`,
then attach LLDB to the reported PID. At the native fault, retain
`thread backtrace`, `register read x0 x9 x10 x11 x12 x13 pc lr`, the cell/cache
memory, target memory and disassembly of both target and `lr-4`. Verify target
registers still correspond to the dispatch stub before interpreting them.

## Collectible CID cache comparison

At this base, `CachedInterfaceDispatchResolveWorker` in
`src/coreclr/vm/virtualcallstub.cpp` updates the cell whenever
`patch && pCallSite != NULL`. The separate virtual-stub-dispatch path explicitly
accounts for a call to a shorter-lived collectible target. The cached-dispatch
destructor discards cells owned by collectible allocators, while the observed
R2R caller cell belongs to the long-lived trusted host. This is source-level
support for investigating target lifetime, not proof of a missing invalidation.

The independent worktree is
`/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/ios-r2r-cache-20261012/runtime`,
branch `runeclr/iossim-cid-cache-diagnostic`, based on the pinned commit above.
Its local diagnostic commits are `f9d3fe58c9d85093e26899660f539766a184626b`
(skip insertion) and `f3645d95d3a3b40a12cc3d79ea1ca30bae976ed5`
(add the logging-only control). Only `virtualcallstub.cpp` and
`clrconfigvalues.h` differ from the base. No upstream patch or issue is submitted.

The Debug-only configuration
`DOTNET_RuneCLRDisableCollectibleInterfaceDispatchCache` defaults to zero.
In `CachedInterfaceDispatchResolveWorker`, when `patch`, the call site and a
collectible receiver MethodTable are present, a nonzero mode logs the cell,
MethodTable and resolved target. Bit 0 clears `patch` before cache insertion.
Mode 2 records the same resolution without suppressing insertion.

| Full original R2R package / native runtime | Result | CID records |
| --- | --- | --- |
| Original unpatched native runtime | SIGSEGV, PC 0, `MapRunner.Run+776` | 0 |
| Diagnostic runtime, mode 0 | Same native crash | 0 |
| Same diagnostic runtime, mode 2 | Same native crash | 1, no skips |
| Same diagnostic runtime, mode 1 | 21/21 tests passed, managed exit 0, no assertion | 52 skipped insertions |

The final matrix is `compare-20261012T134720Z`. Process IDs are respectively
93176, 93307, 93363 and 93423. Each group starts a fresh app process. Native
`.ips` reports confirm `EXC_BAD_ACCESS` / `KERN_INVALID_ADDRESS at 0`, PC 0
and the same R2R call site in all three failing groups. The logging-only crash
shows that adding diagnostic output alone did not remove the failure in this
comparison. The earlier three-group matrix also passed its enabled 21/21
suite, with the original and disabled groups crashing at the same call site.

The comparison copies the original app, replaces only `libcoreclr.dylib`, and
ad-hoc signs the copy. `identity.json` verifies every managed DLL and
`framework.dylib` remain byte-for-byte unchanged; neither the production host
nor its native wrapper is rewritten. The unsigned final diagnostic library
SHA-256 is
`c7bf47bf9a84128caf402d92050ba3879aa6ed916d5498ca152eb9a02f7fecde`.
The final patch SHA-256 is
`820f2d8120c50886509bb576275812a0fa4cb681950ca24d70b9c4df6a128bb5`.

[The private builder](../eng/ios-r2r-cache-build.py) uses APFS object clones
from the matching baseline build. It recompiles two precompiled headers,
`clrconfig.cpp.o` and `virtualcallstub.cpp.o`, then relinks using the baseline
Ninja link command. A Clang VFS overlay maps the configuration header to the
worktree revision; all other source reads and untouched objects use the pinned
baseline. This is a private incremental diagnostic build, not a complete
upstream rebuild. It refuses a dirty diagnostic worktree or an existing private
object directory. No installed runtime or baseline build output is replaced.

[The full-host runner](../eng/ios-r2r-cache-run.py) checks native initialization,
the SIGSEGV markers in the three expected failures, logging-only records,
and the enabled suite's 21/21 marker, managed exit, skips and absence of
assertions or native faults. `simctl launch` returned zero even for the crashed
apps, so launcher exit alone is not a success check. Its strengthened parser
was run over the final existing logs and returned `matrixPassed: true` with
exit 0; `results-verified.json` records that verification.

## Related upstream source tests

[The source-test adapter](../eng/ios-r2r-cache-upstream.py) compiles unchanged
pinned sources from `Loader/CollectibleAssemblies/ResolvedFromDifferentContext`
and `Loader/CollectibleAssemblies/GenericVirtualMethod`. It directly invokes
their methods through a thin adapter supplying Xunit attributes, actual
`False`, `NotNull`, `Equal` and `Throws` assertions, and matching platform
metadata. This is not the official generated upstream test runner.

The first test covers four cross-context resolve/unload/rejection scenarios.
The second performs ten GVM invocation/retirement cycles and asserts its
virtual-function-pointer-cache flush sentinel. Both source tests pass 2/2 on
the original, diagnostic-off and diagnostic-on runtimes, with managed exit 0
and no assertions. Each has zero CID skips; these are related regression
controls and do not cover the failing CID path. Final results and input source
hashes are under `upstream-source-tests-trace/logs` in the evidence archive.
The official runner and an exact CID regression remain necessary for a fix.
The subsequent [official Windows regression run](ios-r2r-upstream-validation.md)
passes 16/16 generated upstream project executions and a two-tick desktop
R2R/IL control. This advances related regression coverage on Windows; it does
not establish that the failing iOS cached-dispatch path is covered.

## Evidence and next step

The compact local archive is
`artifacts/ios-r2r-investigation/20261012-cache/evidence.tar.gz`, SHA-256
`7465d36bb092519ef826639299db797a721cc802e314791ccd3c2684120274a5`.
It has been downloaded, hash-checked and extracted locally. It includes
diagnostic patch/source, compile/link commands, source/native identity hashes,
both matrices, final full console logs and native crash reports, the source
adapter and unchanged upstream inputs. Large object trees and app binaries
remain on the experiment Mac. Baseline HEAD/status and diagnostic HEAD/status
are in `logs-trace/final-state.json`: baseline tracked files unchanged, the
pre-existing Mono smoke directory preserved, diagnostic worktree clean. All
four cache/source-test simulators are shut down and no owned background
process remains.

The subsequent [minimal experiment](ios-r2r-minimal.md) completes the
cold/publication/hot and retirement distinction: 34 groups pass and six
original/off/trace groups reproduce a second-session SIGSEGV after the first
context collects. Native captures separately retain old cache targets,
unmapped and reused precode pages, reused MethodTable addresses, decoded
literal loads and zero target/secret slots. The
[source analysis](ios-r2r-cache-analysis.md) relates these observations to
cache ownership and allocator teardown.

The [default-behavior candidate](ios-r2r-fix-candidate.md) skips collectible and
dynamic-interface receiver publication while retaining immediate resolution.
Its [five-group acceptance](ios-r2r-fix-validation.md) passes the original
full R2R lifecycle suite, reduced retirement sequences and controlled player;
the unchanged original negative control still crashes. Official upstream
patched-platform coverage, full/release builds, performance and physical-device
acceptance remain separate requirements.
