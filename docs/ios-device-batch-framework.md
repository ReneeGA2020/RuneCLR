# iOS Device Batch Framework

On 2026-10-15, the matching iPhoneOS ARM64 Release framework completed with
181 raw/R2R components. Libraries, dependency generation, crossgen, composite
linking and CoreLib metadata commands all exit 0. The libraries build reports
zero warnings/errors and elapsed 6m17.50s. This extends the accepted
[device runtime build](ios-device-batch-build.md); the subsequent
[unsigned application](ios-device-application-build.md) now passes build and
post-build author binding. Physical execution remains unperformed.

## Source And Products

The runtime checkout is the same private commit
`3126bbc9a8851a09ac6435b18a12882bad48f3ee`, tree
`710936ae1729a5689ab0e0896f3cf722ddd3d31c`, based on official
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. The
[framework driver](../eng/ios-device-batch-framework.py) uses its private
RC1 SDK and accepted Mac-host crossgen2. The library subset is
`libs.native+libs.sfx -os ios -arch arm64 -cross`, with CoreCLR flavor,
interpreter enabled and dynamic-code compilation disabled. Original 22
runtime products and 38 source hashes remain unchanged.

Crossgen's actual response file specifies `--targetos:ios`, ARM64, Mach-O,
composite, input-bubble and optimization. The actual final linker uses
`xcrun --sdk iphoneos clang -target arm64-apple-ios15.3 -dynamiclib`.
The final `framework.dylib` SHA256 is
`05a7da16e2b3edd2a38ee8b8ac8170cee78031d9e828f1078e934acf4de0e66b`.
Root directly reparses its ARM64 Mach-O: platform 2, minimum 15.3, SDK27 and
no `LC_CODE_SIGNATURE`. These properties are build evidence, not script
execution evidence.

Native inventory retains both raw sources: 24 products containing 203 Mach-O
members, all device ARM64. CoreCLR compile commands use minimum 15.3; the 227
libraries-native commands use iphoneos with compatible minimum 13.0. Their
earlier minimum is valid for a 15.3 application. Host compiler inputs remain
separate from packaged device-native inputs.

## Layout Corrections And Preserved Attempts

The initial library build succeeded. Layout construction then refused six
same-name static libraries whose CoreCLR and libraries-native bytes differ.
The correction selects native assets using actual evaluated `FilesToPackage`
identities, checked against generated deps native assets; unlisted library
products only supplement absent basenames. The final selected native layout
contains 18 products, while both raw sources are preserved.

The first continuation also rejected a non-native license item at the native
path guard. The second continuation limits that guard to `.a`/`.dylib` items
and succeeds. Both failures are RuneCLR experiment-driver defects; these
records do not establish a Microsoft runtime bug. Successful libraries/deps
stages were reused with their original stream hashes; neither was rerun.

## Retained Evidence

The [final handoff](../artifacts/ios-device-batch-framework-handoff-20261015-attempt1/continuation-results.json)
records outcomes and cleanup. Original streams, commands, compile databases,
objects, source bindings, native-selection records, deps and raw/R2R metadata
are retained at
`D:/RuneCLR-Android/device-build/ios-device-batch-framework-receipts-20261015-continuation2/extracted/`.
The 156866444-byte archive SHA256 is
`ac5e98e8ad4b2459dff456cfdff5fb0a18a61af3ef8e2f39c24e4fbc01ac7bf3`.
Root independently checks all 952 payload sizes/hashes and the archive hash.
Independent framework semantic review also passes at
`D:/RuneCLR-Android/device-build/framework-independent-review-20261015-continuation2/review.json`
(SHA256 `02ec60b94821300e9f94bb3f84b7c209e29367c3ac521db6b9d942c95634ed11`).
It directly parses all 181 raw/R2R MVIDs and full method-definition metadata,
52 private ABI/ImplMap entries, actual packaged-native source identities and
the 227/2604 library/CoreCLR compile commands. The staged native/CoreLib bytes
match the accepted products. Compiler bytes are read from the earlier retained
native-build archive and bound to current before/after receipts and actual
command paths; this review does not reread live Mac files.
The separate `semantic-checks.json` in the same review directory also passes
(SHA256 `324e7e5d8f2d4901e31b759cec958cdb2eb2e38a45bc81c0dc6ef7d0f7931aa4`):
180 original library hashes match raw framework inputs, actual evaluated
properties select CoreCLR/iOS/interpreter without dynamic-code compilation,
five selected runtime compile rows contain the interpreter/static/iOS flags
without `FEATURE_JIT`, and six frozen wrapper-source files match the accepted
commit/tree/archive binding. The original main review remains unchanged.
The separate `archive-checks.json` (SHA256
`5f0ea4d8b8cd241b34acb95a296e15a96aede7563bf36534487a1fc8146f46b1`)
also reconciles the main ZIP's 953 members (952 payloads plus index) and the
wrapper ZIP's eight members against their exact indexes and extracted bytes.

All owned build and transfer processes have exited; the Mac build slot is
released. No application, signing, installation or device operation was run.

## Next Application

Use these matching device raw IL/native assets for the
[unsigned application route](ios-device-application-preparation.md), with
the fixed 15-case/73-context harness and no author DLLs or compiler in the
bundle. Inspect actual executable/dylib types, platform, deployment, signatures
and resolved dependencies. Compile fresh author IL after the host build and
deliver it after installation. Connected physical hardware, matching signing
provenance, interpreter entries and lifecycle/recovery results are still
required by the [device readiness record](ios-device-readiness.md).
