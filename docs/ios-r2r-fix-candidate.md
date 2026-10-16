# Collectible cached interface dispatch candidate

This is an isolated CoreCLR candidate prepared on 2026-10-12, based on
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. It is not merged upstream or
installed as a system runtime. The [cache analysis](ios-r2r-cache-analysis.md)
and [investigation](ios-r2r-investigation.md) distinguish the source-visible
lifetime concern, measured reduced-fixture failure, and native fault evidence.

## Change

Current candidate branch `runeclr/iossim-cid-collectible-fix-v2` has commit
`8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d`. The first receiver-only candidate
`bfefc844a5501250b473cfeb4dabfa05b07e841d` remains preserved on its separate
`runeclr/iossim-cid-collectible-fix` worktree with its original outputs. Only
`src/coreclr/vm/virtualcallstub.cpp` changes, inside
`CachedInterfaceDispatchResolveWorker`: after resolution, set `patch=FALSE`
when `objectType->Collectible() || objectType->IsIDynamicInterfaceCastable()`
before the existing cache-publication block.

The resolved target is still returned and immediately invoked. A collectible
receiver is resolved on each invocation instead of contributing a raw
MethodTable/entrypoint mapping to a longer-lived CID cell. Noncollectible
receivers without dynamic-interface implementation selection retain the existing
publication and fast dispatch. Dynamic receivers resolve normally each time,
because their implementation owner can differ from their receiver owner.
This is ordinary
default behavior in the candidate source: there is no Debug-only conditional,
environment switch, tracing, configuration-table change, or assembly rewrite.
The initial lane builds Debug ARM64 simulator native code. Subsequent
[fresh Release/CoreLib/tool builds](ios-r2r-release-build.md) and
[matching Release execution](ios-r2r-release-validation.md) have separate
identities and acceptance records; do not attribute them to this incremental binary.

This trades collectible dispatch-cache speed for a simpler lifetime rule. The
cost and a more selective ownership-compatible cache policy remain unmeasured.

## Build provenance

[`eng/ios-r2r-fix-build.py`](../eng/ios-r2r-fix-build.py) creates a fresh remote
worktree and private object directory. The baseline checkout remains at the
pinned source on `runeclr/iossim-baseline`; its existing untracked
`src/mono/sample/RuneCLRSimSmoke/` experiment is preserved. The separate
diagnostic branch and native outputs are also preserved.

Remote candidate root:
`/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/ios-r2r-fix-v2-20261012`.
The native library is `obj/dlls/mscoree/coreclr/libcoreclr.dylib`; build evidence
is under `logs/`. Local small evidence copies are under
`artifacts/ios-r2r-investigation/20261012-fix-build-v2/`; the receiver-only
candidate retains its separate `20261012-fix-build/` evidence. Build v2 with
`python3 eng/ios-r2r-fix-build.py --dynamic-publication-guard` on the configured
Mac. The script refuses to overwrite an existing candidate root.

The checked-out CoreCLR build guide, relevant upstream instructions, worktree
state, compiler evidence and CMake configuration were inspected before editing.
The baseline is `iossimulator.arm64.Debug`, with interpreter, collectible types,
cached interface dispatch and Apple mapped-thunk support; Xcode clang targets
the iPhone simulator SDK with minimum iOS 15.3.

This is a recorded incremental native build, rather than a clean full-source
rebuild. APFS clones copy the same-base baseline objects privately. The baseline
compile command recompiles only the VM `virtualcallstub.cpp` object using the
candidate source and cloned output paths; unchanged headers and PCH are reused.
The baseline CoreCLR link command then relinks the private library. No generated
configuration/header changes are part of the candidate, so their translation
units do not require rebuilding. Hash inventories establish that exactly one
object changes while 2,715 `.o`, `.a` and `.pch` files remain identical. The
baseline inventory and library hash are checked again after the private build.

| Evidence | Measured value |
| --- | --- |
| Candidate v2 unsigned native SHA-256 | `475e10c45d81c62d212a631dc6fc61ea6a40dcaf369fa97a3870426b1ec8c438` |
| Baseline unsigned native SHA-256 | `eece91b1e916e8965333a96fcd519ea6599949c841b75ca6488cf01333f4f544` |
| Candidate v2 patch SHA-256 | `43b36606fa94967e97f2640e8d76dcfa8f0af21eeb77a065a0eea5c83c915857` |
| Changed object SHA-256 | `f2ada0f45a1e2193ccbee9d5ff0784062e4029f1f924d95607aa876df8e27219` |
| Private native compile and link | Passed, `logs/build.exit=0` |
| Candidate source status | Clean after build |
| Baseline objects and native library | Hashes unchanged |

`logs/source.json` records base, branch, commit, source/patch hashes and default
behavior. `logs/artifacts.json` records native/object hashes, unchanged count,
compiler-command and CMake-cache hashes. Full inventories and exact compile/link
argument arrays are retained remotely. Signing an application may change its
embedded library hash; acceptance must connect the unsigned input to the signed
bundle and compare managed/composite inputs separately.

## Scope and edge cases

The guard applies to the concrete receiver MethodTable, independent of whether
its implementation is declared on that class, inherited, or a default interface
method. Even an implementation in a noncollectible module cannot make a cached
collectible receiver pointer safe after retirement. These paths should therefore
remain uncached, with normal resolver errors and immediate invocation preserved.

Generic receiver instantiations whose MethodTable is collectible follow the
same guard. A nongeneric implementation such as `CounterMap.OnTick(MapTick)`
requires no special generic-register explanation. Generic virtual methods can
instead use `JIT_VirtualFunctionPointer` and other caches; their coverage cannot
be inferred from this worker alone. Interface variance, constrained/value-type
calls and default-method ambiguity require dedicated regressions.

Receiver collectibility is not a complete classification of every possible
callee owner. `VirtualCallStubManager::Resolver` can recurse through
`IDynamicInterfaceCastable` to a different implementation MethodTable. A
noncollectible receiver resolving to a collectible implementation was not covered
by the receiver-only v1 guard. V2 conservatively skips publication for every
dynamic receiver, covering this explicit recursive-resolution route without
changing the Resolver ABI. This also avoids assuming a receiver-only cache key
captures dynamic implementation selection. The [focused dynamic regression](ios-cid-dynamic-repro.md)
now reproduces the failure with original and receiver-only v1 runtimes: after
one returned and collected context, the next dynamic invocation SIGSEGVs. V2
passes sixty interpreted callbacks across twenty context/implementation-Type
retirements on one noncollectible receiver MethodTable; the original IL-host
control also passes. This validates the explicit dynamic owner route in the
tested Debug simulator topology.

The debug worker already exempts dynamic receivers from its direct-target
MethodDesc consistency check; this supports treating the path separately, but
does not prove arbitrary implementation-owner safety. An upstream lifetime fix
may still require implementation-ownership information or a broader
allocator-compatible invalidation design for other caches. Do not label this
candidate a complete solution for all collectible dispatch targets.

## Measured acceptance and remaining checks

Independent v2 verification passed on the Debug ARM64 simulator with diagnostic
switches cleared. Under identical managed/composite inputs, the original full
harness still SIGSEGVs, while v2 passes 21/21 lifecycle cases with twenty
CounterMap interpreter dumps. Reduced two- and three-tick collected sequences
each pass twenty sessions. The controlled-package player suite passes 15/15
with the expected interpreted helper methods. Simulator shutdown is recorded
successful. The remote evidence is
`ios-r2r-fix-verifier-20261012/run-retry1/results.json` under the experiment
root; `verify-retry1.exit` is 0. Its archive SHA-256 is
`1b01dd2b6ba9df16c25b9a5cb01f3a4fb25884a84e57a79800fb83518808593b`.
See the [independent acceptance record](ios-r2r-fix-validation.md) for the
identity comparisons and run conditions.

Additional v2 simulator regressions pass 4/4: value-type arguments and return,
an inherited default-interface implementation, a closed generic interface, and
exception followed by successful next-call recovery. Each completes twenty
sessions with three calls and twenty interpreted-method dumps. The two unchanged
upstream-source tests also pass through their adapter. These are measured
regressions, not execution of the official generated upstream test runner.

Later [official generated managed runners](ios-r2r-official-managed-tests.md)
and [variance/constrained boundaries](ios-r2r-interface-boundaries.md) pass with
their recorded native identities and topology limits. Complete upstream
XHarness integration, concurrent publication, performance, Checked builds,
Release controlled packages and physical devices remain separate acceptance
work. The candidate remains an unmerged experiment.

Keep an original negative control with identical managed/composite files. Run
the reduced first-session cold/publication/hot cases, twenty collected sessions
with two and three ticks, retained/noncollectible controls, the full lifecycle
harness and controlled-package player harness. Clear all diagnostic environment
variables and require managed exit markers plus absence of native crashes.
Retain the additional interface/value-type/generic and exception regressions and
their positive interpreter dumps when extending the candidate. Upstream tests
should also cover the CID path: the previously adapted upstream tests recorded
zero collectible CID resolutions and cannot alone validate this change.

The subsequent [fresh native Debug build](ios-r2r-clean-build.md) starts without
baseline native objects and repeats the five-group simulator comparison
successfully. Its artifact hash and build/acceptance receipts are separate from
the incremental artifact above. Matching Release lifecycle/probe acceptance
now passes independently; complete managed packs, Release controlled packages
and Checked acceptance remain open. Additional interface results are recorded in
[the patched regression lane](ios-r2r-patched-regressions.md).

The execution strategy and physical-device requirement remain as recorded in
[CoreCLR integration](coreclr.md) and
[iOS controlled packages](ios-controlled-packages.md).
Track upstream reporting and replacement in
[RCLR-UP-001](upstream-bugs/collectible-cid-lifetime.md), filed as
[dotnet/runtime #135848](https://github.com/dotnet/runtime/issues/135848).
