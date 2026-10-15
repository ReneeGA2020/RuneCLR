# Minimal terminal-counter mobile build increment

The2026-10-14 follow-up carries the
[Windows-accepted counter increment](windows-budget-increment-performance.md)
into fresh matching mobile builds. It retains the old mobile sources/products
and keeps compilation evidence separate from application execution.

## Exact source composition

- Upstream base: `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`.
- Windows candidate: `20405f7ae23e183e038703aa5e356b3310fef427`.
- Previous mobile tree: `b54537ff42a066e41a01ea611a21f2e5e49934a1`.
- New mobile tree: `91673a7980bda79006259e525741fecb04324444`.
- Mac composed commit: `112e97408de1ae1c2a6cbd2967dcd250cd2d491c`.

The [source-proof tool](../eng/mobile-increment-source-proof.py) independently
reconstructs the tree using three private Git indices: Windows204 plus CID,
the official base plus seven exported patches, and the old mobile tree plus
0008. All three produce the same tree. Relative to Windows204, only the CID
publication guard in virtualcallstub.cpp differs. Relative to the old mobile
tree, only the exact meter-header increment differs. The Apple generator
patch0002 remains separate.

The [actual proof](../artifacts/mobile-budget-increment/source-review-20261014-attempt1/source-proof.json)
binds37 changed LF Git blobs and seven frozen patches, with six negative
controls rejected. Its SHA256 is
`6dea87eae1bbbb3142319707c2af4f5cca142a5bc1e4fe8ef665d8a93a2e4d48`.
Runtime checkout, branch, HEAD and normal Git index remain unchanged; the
shared object store receives the independently reconstructed tree objects.

## Build stages

The new [iOS driver](../eng/ios-budget-increment-build.py) and
[Android driver](../eng/android-budget-increment-build.py) preserve their
original session-budget builders. They pin the new tree, Windows candidate,
source-proof SHA and precise increment/CID composition. Each request records
its parent driver hash, actual source and fresh output layout.

Both use the configured Mac. Only one expensive build runs at a time. Fresh
worktrees have no copied native/managed build outputs; only the fixed source
SDK11.0.100-rc.1.26420.103 is APFS-cloned. Android also verifies the pinned
NDK r27c receipt and actual toolchain bytes. Child environments are scoped;
installed .NET and global configuration are unchanged.

| Target | Recorded stage | Execution evidence |
| --- | --- | --- |
| iOS simulator ARM64 Release | Fresh official core/runtime/CoreLib/compiler build passes; ten compile owners and three CoreLib metadata stages verified | New application15/73 and separate147 samples/nine method groups pass |
| Android x64 Release | Fresh official core/runtime/CoreLib/compiler build, CoreLib ABI and new framework/bridge layout pass | Fresh APK15/73 and installed203-file inventories pass; new method-entry samples pending |

Build outputs are isolated at Mac experiment-root children
`ios-budget-increment-release-20261014-attempt1` and
`android-budget-increment-release-20261014-attempt1`. The controller snapshots
both old mobile native runtimes, CoreLib IL and compilers before launch;
post-build checks must prove those bytes unchanged.

The iOS build completed in5m08.78s; the Android build followed after it and
completed in4m37.32s. Both report tracked-clean source at the composed commit
above. The [iOS receipts](../artifacts/mobile-budget-increment/ios-build-receipts-20261014-attempt1/results.json)
and [Android receipts](../artifacts/mobile-budget-increment/android-build-receipts-20261014-attempt1/results.json)
are downloaded with zip and individual-file SHA/size validation. The iOS
archive binds14 receipt/controller files; Android binds16. Large build logs,
compile databases and Android preprocessing remain on the Mac with SHA/size
indices in each receipt directory. A local read-only recheck confirms all
archived bindings; it does not independently re-execute compilation or
application acceptance.

iOS records a static interpreter with dynamic JIT disabled, a matching
compiler GUID and retained policy5/meter8/terminal12/GC3 private API families
across three CoreLib stages. Android records the interpreter/dynamic-code
configuration, native terminal/finalizer symbols and charged computed-goto
dispatch in actual preprocessing, while keeping metadataVerified=false,
frameworkComplete=false and executionVerified=false. Its produced CoreLib
has now passed the separately retained [ABI/framework increment](android-budget-increment-layout.md).

A later [independently authored live Android review](../artifacts/mobile-budget-increment/android-independent-review-20261014-attempt1/results.json)
matches the downloaded receipts against actual remote bytes: 37 LF worktree
files and Git blobs, six compile-database entries and x64 relocatable objects,
seven products including three Android x64 shared ELF images, and charged
computed-goto macro/call excerpts. Four corruption controls reject a changed
meter source hash, object hash, ELF machine or dirty base. The original base
remains tracked-clean; six old mobile products and the Debug baseline retain
their recorded hashes. This review verifies native core build bindings while
leaving metadata, framework, APK and device execution unverified in that review.
The later [new Android APK acceptance](android-budget-increment-acceptance.md)
passes actual15/73 execution and installed before/after inventories. Separate
[new iOS application and entry acceptance](ios-budget-increment-acceptance.md)
passes15/73 and147 sampled entries across nine groups. Earlier build-only
receipts retain their original false execution flags.

## Next acceptance gates

Both new applications now pass budget/recovery/collection cases with unchanged
author IL transferred after installation. New Android author-entry sampling
remains next before performance measurement; iOS sampling passes within its
declared selected-entry scope. Preserve matching framework/host, native compile,
CoreLib metadata and compiler bindings for subsequent experiments.

The earlier [mobile budget runs](mobile-host-budget-acceptance.md) establish
the old tree's simulator/emulator behavior. They do not establish the new
candidate's execution or performance; the later acceptance above supplies new
functional evidence. iOS entry inspection reads emitted ARM64 bytes, but a full
counter-hotpath cost inspection and representative/device performance remain
open, as does
[physical iOS readiness](ios-device-readiness.md).
