# Mobile Derived-Ledger Builds

On 2026-10-14, the Windows
[derived-ledger candidate](windows-derived-ledger-candidate.md) gains an exact
mobile source composition and successful matching iOS ARM64 simulator and
Android x64 Release core builds. The later matching iOS simulator application
passes 15 scenarios and 73 context collections; Android bridge metadata and a
fresh trusted framework composite also pass. Method-entry capture, mobile
performance and physical devices remain unverified for these new products.
Earlier mobile entry samples belong to the previous increment candidate.

## Exact Source

The [source proof](../artifacts/mobile-derived-ledger/source-review-20261014-attempt5/source-proof.json)
passes three independently reconstructed Git-index compositions:

- Windows `29ff781e157be82ba5a398a60bb05291e4a865af` plus CID v2.
- Upstream `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` plus nine patches.
- The previous mobile increment tree plus phase-load and derived-ledger patches.

All three produce tree `3292fc9acf3c15632f3bde34f675caec44f399e2`.
The dedicated mobile commit is
`2d86588f8cef4b3c48ce2ba4d4af15ad7bc83e7c`, a direct child of Windows29ff.
There are 37 exact LF source files and 21 rejected alterations. Phase-load
and derived-ledger switches remain independent and default-OFF. The native
meter size is 64 bytes, aligned to 8 bytes. This preserves per-opcode admission;
no 100/1000 batching or delayed flush is introduced.

A small verified Git bundle transfers the exact commit identity to the Mac.
The iOS task imports it once; the Android task creates its own detached
worktree from those objects. The original worktrees, products and receipts
are retained. Apple generator patch0002 remains separate from runtime source
composition. The earlier source-proof attempts and their tooling failures
are preserved; attempt5 is the accepted source proof.

## iOS Simulator Build

The [matching build receipt](../artifacts/mobile-derived-ledger/ios-build-receipts-20261014-attempt1/results.json)
records iossimulator.arm64 Release, exit0 and zero warnings/errors. The
official runtime/native/CoreLib/tools/crossarchtools build runs in a fresh
worktree with a private .NET11 RC1 SDK clone. Build results bind the exact
source proof, bundle, 5838 SDK files, actual Xcode/Clang/CMake/Ninja inputs
and ten preserved earlier products. Source and preserved-product identities
remain unchanged after the build.

The frozen existing Mac assessor checks ten actual native compilation owners,
static-interpreter enablement, dynamic-JIT disablement and matching compiler
GUID. Three CoreLib metadata stages retain the private policy5, meter8,
terminal12 and GC3 method families. Native meter size64/alignment8 is checked
against the actual header. These are build/metadata observations, not proof
that a deployed application selects the new branch.

The downloaded receipt archive is 1239481 bytes, SHA256
`ad6b4fb18b9aca5fbc26254c5442163894ae7c1b7a57d6267adad2e84b731a12`.
All 65 members and 37 source files pass hash/size checks. A separate
[root offline review](../artifacts/mobile-derived-ledger/root-ios-build-review-20261014-attempt1/results.json)
reconciles the archive, source proof, launch/build receipts, frozen tooling,
SDK inventory and preserved-product identities. Native binaries remain on
the Mac; the root review does not analyze their machine code locally. The
single-use download server has exited.

The first launch stopped before compilation because the new builder assumed
the wrong CMake path. That preflight log is retained. The corrected builder
freezes the actual CMake found on its controlled PATH; fresh attempt2 is the
successful native build. This was RuneCLR experiment tooling, not an upstream
runtime failure.

## Android And Next Steps

The new Android builder passes six dependency-inventory helper controls and
twelve adapter controls. Its prepare stage verifies the same exact commit,
37 LF source files and thirteen preserved products. A complete Mac-side
dependency inventory includes the Android SDK/NDK, resolved NuGet packages,
CMake/tool directories and macOS SDK. Selected
[preparation and launch receipts](../artifacts/mobile-derived-ledger/android-preparation-receipts-20261014-attempt2/download-result.json)
are downloaded and checked; the full inventory is still on the Mac.

After the iOS build releases the heavy-build slot, Android completes the
[official x64 Release runtime/CoreLib/compiler build](../artifacts/mobile-derived-ledger/android-build-receipts-20261014-attempt1/results.json) with exit0 and zero
warnings/errors. Six native compile owners, seven critical products, charged
computed-goto preprocessing and actual meter64/alignment8 pass the build
assessment. Source, thirteen earlier products and complete dependencies retain
their before/after identities. The later metadata and framework stages are
recorded below. APK, author execution and device validation remain pending.
The [download result](../artifacts/mobile-derived-ledger/android-build-receipts-20261014-attempt1/download-result.json)
checks six selected receipts by size/hash. A separate
[root offline cross-check](../artifacts/mobile-derived-ledger/root-android-build-review-20261014-attempt1/results.json)
reconciles selected raw files, source/launch/build identities, seven product
bindings and the Mac-side compile assessment. Full dependency inventories,
preprocessing and native products remain on the Mac. Both builds and their
owned transfer processes have exited.

The [new metadata receipts](../artifacts/mobile-derived-ledger/android-metadata-receipts-20261014-attempt1/download-result.json)
bind four actual PE observations: three CoreLib stages and the managed compiler
mirror. Private policy5/meter8/terminal12/GC3 families, constructor arities2/3/4,
typed ObjectHandleOnStack/StackFrameIterator queries, native Byte returns and
absence of hidden-error status pass. PostTrim and ProductIL bytes match;
compiler bit33 and GUID7c844228-f051-4b9b-9b8f-4e221230806f are retained.
Five metadata alteration controls reject. The archive covers14 files plus its
index; products remain on the Mac.

The [new layout receipts](../artifacts/mobile-derived-ledger/android-layout-receipts-20261014-attempt1/download-result.json)
record a successful matching crossgen process:185 original trusted IL inputs
produce186 PE files, including the composite. The layout contains200 products,
nine embedded receipts and its descriptor. The CoreLib component retains the
private ABI and MVID. Mac-side checks preserve37 source files, seven core
products, all210 old layout files and thirteen earlier products. Five layout
alteration controls reject without compilation. This reuses original framework
IL and rebuilds the composite with the matching compiler; it does not reuse the
old native composite. The downloaded archive covers39 files plus its index.

A [root offline reconciliation](../artifacts/mobile-derived-ledger/root-followup-review-20261014-attempt1/results.json)
independently checks the actual ZIP/member bytes, metadata/typed raw rows,
crossgen process/request/exit records, component ABI/MVID and embedded receipt
chains. Root does not locally rehash the remote native/PE products or infer
Android application execution from this build result.

The [iOS application acceptance](ios-derived-ledger-acceptance.md) establishes
fresh budget/recovery semantics for the new candidate. The
[Android APK preparation](../artifacts/mobile-derived-ledger/android-apk-plan-20261014-attempt1/plan.md)
passes read-only prerequisites and specifies four new adapters. APK construction,
installation and execution have not started. Fresh mobile method-entry and live
branch evidence remain next. Physical-device dynamic IL loading and repeated
retirement remain separate acceptance requirements.
