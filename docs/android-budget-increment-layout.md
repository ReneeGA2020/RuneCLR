# Android counter-increment ABI and framework layout

On 2026-10-14 the new Android x64 Release core build received an actual retained
PE ABI review and a fresh matching trusted framework composite. This establishes
build/layout compatibility; APK execution, method entry and device acceptance
remain separate gates.

The candidate is commit `112e97408de1ae1c2a6cbd2967dcd250cd2d491c`, tree
`91673a7980bda79006259e525741fecb04324444`, based on official upstream
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. Its exact counter change is bound
by the [mobile source proof](mobile-budget-increment-builds.md).

## Retained ABI

The new [metadata assessor](../eng/android-budget-increment-metadata.py) retains
the original assessor's checks. Actual metadata-only reads inspect PreTrim,
PostTrim, product CoreLib IL, and the managed compiler flag mirror. All three
CoreLib stages retain private policy5/meter8/terminal12/GC3 methods, constructor
arities2/3/4 and QCall factory signatures. Typed owner queries resolve
ObjectHandleOnStack and StackFrameIterator with native Byte return and no hidden
error status. Generated roots and compiler bit33 also pass. PostTrim and product
IL are byte-identical.

Live native symbol inspection finds the five recorded terminal/finalizer entry
symbols. The matching JIT/EE GUID `7c844228-f051-4b9b-9b8f-4e221230806f` occurs
as contiguous bytes in native CoreCLR, interpreter, target JIT and crossarch JIT.
Crossgen2 and jitinterface have no contiguous copy; their exact product hashes
are bound and the subsequent actual crossgen invocation succeeds.

Metadata attempt1 preserved an overly strict failed check requiring a contiguous
GUID in all six products. Attempt2 corrects the ownership requirement without
rebuilding or replacing products. Five mutated metadata controls reject a
missing method, public bridge visibility, changed factory signature, hidden-error
owner query and wrong compiler bit.

The [successful metadata receipt](../artifacts/mobile-budget-increment/android-layout-receipts-20261014-attempt1/metadata/results.json)
has SHA256 `525eea3f041d8194ea3a2b98c05cccab588ac4f81464ba4c287e10c4770034a2`.
The [negative controls](../artifacts/mobile-budget-increment/android-layout-receipts-20261014-attempt1/metadata/negative-controls.json)
include the actual positive recheck.

## Fresh Matching Composite

The [new layout driver](../eng/android-budget-increment-layout.py) preserves the
old driver. It reuses the inventoried 180 original framework IL images and OS
libraries from commit `1724cdec553a7aff7a373a271a4be612651c7625`, at the same
official base. Live library/native source differences are limited to the
explicitly replaced CoreLib source. Every reused inventory size/hash matches;
the reused managed inputs have no R2R header.

The new candidate CoreLib supplies the matching core image, and the unchanged frozen four
trusted RuneCLR/mobile-probe DLLs enter the composite. The original author DLL
remains collectible IL and is excluded. The matching new crossgen2 compiles185
inputs into186 outputs, with a new composite and component images. The retained
CoreLib methods, fields and MVID match the new product IL after compilation.
ELF dependency closure resolves against the pinned NDK r27c/API24 system inputs.

Fresh output on the configured Mac is
`ROOT/android-budget-increment-layout-20261014-attempt1/layout`; ROOT is the
experiment root recorded in [the machine handoff](remote-mac-experiment.md).
It contains200 inventoried files and nine frozen receipts. The
[layout result](../artifacts/mobile-budget-increment/android-layout-receipts-20261014-attempt1/layout/results.json)
has SHA256 `3286a122a8eaa6bd564f0d1ac8eef38976128dda31d3402474069b09bef6f19b`.
The new CoreLib R2R component SHA256 is
`d6e0ee1f955a98c1484edf13ef988f8f984213f3d71cda35461807090aa7780b`.

A [post-build live recheck](../artifacts/mobile-budget-increment/android-layout-receipts-20261014-attempt1/layout/live-review-corrected.json)
verifies source37, critical7, all200 files, nine receipts, unchanged tracked
source, and seven preserved products. Its predecessor's scope text mistakenly
said ten receipts; the machine-readable count was nine. Both records remain
preserved, with the corrected record identifying the predecessor hash.

The downloaded [receipt index](../artifacts/mobile-budget-increment/android-layout-receipts-20261014-attempt1/file-index.json)
binds37 files with checked size and SHA256. Archive SHA256 is
`eee2ad60629708d06e56fea5d156c860b0abe6103d35dd14f2f6acec6f52729e`,
size115922 bytes. This includes drivers, logs, metadata, negative controls and
layout receipts; it does not download the full native/framework binaries.

The subsequent [APK adapter](../eng/android-budget-increment-apk.py) adds a
pre-bridge check of all185 actual composite-input DLL names and hashes, plus
the fixed metadata inspector SHA256. This prevents a changed input directory
from being silently recomposited behind unchanged old generated-layout hashes.
The adapter freezes the exact local parent driver separately; the historical
Mac APK driver has different bytes and remains preserved. This source review
does not establish that the new APK has been built or run.
