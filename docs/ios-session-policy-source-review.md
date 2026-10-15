# iOS simulator combined-policy source/build review

Reviewed on 2026-10-13 against official runtime base
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. This record checks composition
and the required matching build. It does not report a new simulator build or
execution result. The earlier [Release CID build](ios-r2r-release-build.md) and
[Windows session candidate](runtime-session-policy-candidate.md) are separate
measured baselines.

## Source composition

The following patches apply in order from the official base:

1. [0001](../eng/runtime-patches/0001-collectible-cid-publication.patch): CID v2 publication guard.
2. [0003](../eng/runtime-patches/0003-collectible-interpreter-selection.patch): required compiler flag/routing and fail-closed diagnostic selection.
3. [0004](../eng/runtime-patches/0004-interpreter-required-load-context.patch): immutable native binder policy, private CoreLib factory/query and exact three ILLink method roots.

All three `git apply --check --cached` and actual cached applications passed
using a private index initialized with the official base. Neither tracked
checkout nor build products changed. The resulting 27-file source tree is
`71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2`: byte-for-byte identical to session
candidate `5972a86966e56ae5f468a3e042327f0051e923d5` except for the intended
CID modification in `virtualcallstub.cpp`. There is no overlap/conflict
between the CID guard and session-policy edits. The same compiler-interface
GUID is retained; composition itself adds no interface change.

The local receipt and cumulative LF diff are in
`artifacts/ios-session-policy-source-review/20261013`. Combined diff SHA-256:
`dbe68e19784f945a2922a5eaedfab416e07e1a0147415db1c6280dae73b5953f`.
The private index is only a source-composition check, not a remote candidate
commit or proof that Apple compilation succeeds.

In the new isolated Mac checkout, apply the separate files before committing:

```sh
git apply --check /absolute/patches/0001-collectible-cid-publication.patch
git apply /absolute/patches/0001-collectible-cid-publication.patch
git apply --check /absolute/patches/0003-collectible-interpreter-selection.patch
git apply /absolute/patches/0003-collectible-interpreter-selection.patch
git apply --check /absolute/patches/0004-interpreter-required-load-context.patch
git apply /absolute/patches/0004-interpreter-required-load-context.patch
git diff --check
```

0004 is incremental from 0003's candidate, not independently applicable to
the official base. The combined source tree/hash permits comparison against
an independently committed remote candidate without reusing Windows binaries.

## Matching Release build

Start with empty native objects/generated headers and clone only the pinned
SDK `11.0.100-rc.1.26420.103`. The already verified Release sequence is:

```sh
./build.sh clr.runtime+clr.native -os iossimulator -arch arm64 -cross \
  -c Release -ninja -cmakeargs -DCMAKE_OSX_DEPLOYMENT_TARGET=15.3 /m:1
./build.sh clr.corelib+clr.tools+clr.crossarchtools \
  -os iossimulator -arch arm64 -cross -c Release -ninja \
  -cmakeargs -DCMAKE_OSX_DEPLOYMENT_TARGET=15.3 /m:1
```

`clr.native` requests full native dependency targets, avoiding the known
clean-runtime-only prerequisite failure. `clr.corelib` produces matching
Release IL; `clr.tools` builds in-tree crossgen2 and its compiler interface;
explicit `clr.crossarchtools` supplies the host JIT needed for the target
compiler. The product prefix is
`artifacts/bin/coreclr/iossimulator.arm64.Release`. Ordinary library inputs
may retain their recorded base, but the trusted framework/host composites
and component DLLs must be rebuilt from that combined source's Release
CoreLib using its new compiler. This is a private matching layout, not shipping
packs. A separate `clr.nativecorelib` invocation is only needed if consuming
the official standalone CoreLib Mach-O/component outputs; it does not replace
regenerating the application's full trusted composite.

At this base, `eng/build.sh` defaults `iossimulator` dynamic compilation to
false and sets `FeatureInterpreter=true`. `RuntimeIdentifier.props` classifies
the simulator as `TargetsiOS`; CoreLib feature definitions enable the
interpreter and cached interface dispatch. `runtime.proj` passes the native
interpreter flag. Native `clrfeatures.cmake` selects static linking and CID
when dynamic compilation is disabled. Interpreter objects are linked into
CoreCLR, so a separate interpreter dylib is not required evidence of support.

Inspect the **VM** compilation commands, not the similarly named AOT tool
`jitinterface.cpp`. They must identify the new checkout, ARM64/iPhone simulator
sysroot, Release optimization/retail definitions, interpreter and R2R support,
CID and Apple mapped thunks, with no dynamic native compilation or Debug
layout definitions. Check the managed CoreLib evaluated constants for
`TARGET_ARM64`, `FEATURE_INTERPRETER` and no `DEBUG`. Existing CMake/source
defaults do not replace these actual compilation/configuration receipts.

## Interface and layout constraints

Required flag bit 33 and GUID `7c844228-f051-4b9b-9b8f-4e221230806f` agree in
the native CORJIT definition, JIT flag mirror/assertions, managed CorInfoTypes
and interpreter. The native AOT JIT wrapper checks this GUID against its JIT
dependency before compilation. Rebuild/bind the in-tree crossgen2,
`libjitinterface_arm64.dylib` and `libclrjit_universal_arm64_arm64.dylib`
together; do not reuse the old CID-only compiler. Hash and source-bind every
consumed compiler dependency, not only the crossgen2 executable. A native-only
replacement cannot carry the new private CoreLib factory or layout contracts.

Windows already exposed the reflection-only bridge being trimmed from
CoreLib despite a successful build. The current 0004 includes the three exact
roots. Before packaging, inspect actual PreTrim/post-trim/product IL metadata
for the five bridge/wrapper MethodDefs, three native entry imports and nested
`.ctor`, `Load`, `LoadUnmanagedDll`. Repeat against generated R2R component
metadata and check final deployment hashes. A fresh compiler log alone does
not establish the private API survived trimming.

Keep Release CoreLib/native MethodTable layouts matched. The earlier mixed
Debug-CoreLib/Release-native startup fault remains a local layout error and
must not be reclassified as a CID or policy defect. Existing drivers hardcode
CID commit `8f5815a...`, earlier native hashes and output roots; adapt them
in a new driver/evidence directory rather than running them against altered
inputs or overwriting their historical receipts.

## Mobile acceptance boundaries

Use required factory contexts with mode 0 and global diagnostic off, including
late private dependency loading, ordinary-context query 0, managed refusal
and recovery, and repeated retirement. Source preserves the required-body
rejection before the no-native-JIT platform branch. Native method-entry
evidence must identify the new package bodies, not previous fixtures. Release
builds omit Debug-only bytecode dump switches.

Windows's ordinary-new-IL mode-0 native JIT positive and unmarked compiler-skip
fallback returning 73 require native JIT support and cannot be transplanted
unchanged to iOS. Trusted framework/host native controls should use the freshly
generated matching R2R image; an ordinary newly loaded IL body lacks such code
and has no JIT fallback on this target. Keep the Windows fallback control as
its platform-specific result. Simulator acceptance remains distinct from
physical iOS deployment and execution.
