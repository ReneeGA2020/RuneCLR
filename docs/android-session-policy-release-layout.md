# Android matching Release layout

On 2026-10-13, the fresh private Android x64 Release layout passed its source,
configuration, framework closure and native/managed identity checks. This
establishes prepared inputs for an APK and method-entry experiment; Android
Release method-entry and independent normal acceptance are still pending. The
later [APK transport experiment](android-session-policy-release-entry-preparation.md)
records actual installation, attach/detach and twenty resumed functional sessions
separately from this layout preparation result.

The official base is 0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de; combined
candidate commit is 1724cdec553a7aff7a373a271a4be612651c7625 and tree is
71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2. The source remains tracked-clean.
CoreCLR, CoreLib and Darwin-host compiler inputs are freshly built Release;
the build SDK is 11.0.100-rc.1.26420.103 and the product is .NET12 development.
The source's framework TFM remains net11.0. These separate version identities
come from the actual source and build receipts.

The [actual Release core assessment](android-session-policy-release-build-assessment.md)
passed source27, nine object owners, required bit33/GUID and private bridge
retention. Android native owners use -O2; Darwin-host tools use -O3. Actual VM
definitions have interpreter1, dynamic-code1, R2R1, VSD1 and Retail/NDEBUG; CID
capability is absent, matching this JIT-capable Release source configuration.
This layout therefore does not exercise the iOS cached-interface-dispatch route.

## Matching framework and layout inputs

The fresh framework attempt2 completed the library and actual runtime-pack deps
stages with exit0. The library build reported zero warnings/errors and elapsed
6m9.87s. The resulting inventory has 180 framework DLLs and 28 native-stage
inputs; the latter include static libraries and actual Android crypto JAR/DEX,
not 28 deployed shared objects. The accepted seven core-critical products,
including their published duplicate copies, remained unchanged and source clean.
The retry used process-scoped UseSharedCompilation=false; the original compiler
MSB3883 failure remains preserved separately with unconfirmed attribution.

Actual remote outputs are under ROOT, where ROOT is
`/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr`:

| Receipt | SHA256 |
| --- | --- |
| android-session-policy-release-framework-20261013-attempt2/results.json | ac491a83b59ffd6d9abd396f2da3a415d4f171830e7c4b1af287e1948cfc86a3 |
| Its input-inventory.json | bb87538a5f80cecb6f6dbe82eee7f41a1e7f735929d42438d582d960f4fd013e |
| Actual Android framework deps | fc9a3bc678b15c5b703f30a991b68105e76636b9c61d1303128d92ea04912ca7 |
| android-session-policy-release-layout-20261013-attempt1/layout.json | 5e64df771212b456e677db0a0517a4d1a0a07a50d10abfcfc3e48f1913e83b97 |

The [layout tool](../eng/android-session-policy-layout.py) consumed that fresh
framework receipt and the pre-cleanup freeze-only snapshot, not a replacement
CoreLib pretending to be PreTrim. The frozen three CoreLib stages, managed
compiler mirror and generated descriptor retain their original assessment
hashes. Its actual running layout-v2 driver SHA is
3ab977377032cca005a41b959fb21b2162c67dcc7658b44a1e43df85ca7d61eb.
The framework-v2 driver SHA is
bb38e3fb18164f4692ab797a59f5ef22843bb941ca3b2415751a3081064a2c44.

The layout includes 195 player input files: 182 managed/deps files, ten target
shared objects, the crypto DEX and two hosting headers. Actual ELF dependencies
resolve against packaged inputs or the pinned NDK API24 linker stubs. This
private IL framework is not a shipping pack. New RuneCLR trusted hosts and
post-install author payloads belong to the subsequent APK stage.

## Matching symbols and Windows archive

Ten separate native symbol images were copied from the actual corresponding
build products, and their GNU build-ids match the packaged shared objects. The
three execution-critical pairs are:

| Native image | SHA256 | GNU build-id, also present in .dbg |
| --- | --- | --- |
| libcoreclr.so | ea39871706c6452c9b66de0ab4fe18111389f36eaf28559a618970c3fcf68208 | 37c227b17623d79ee1d640cbaa9df77162e020a1 |
| libclrinterpreter.so | 604eafc27fe5e8e2f2e113b97f8d76903da62ff9d7474bd475495f5f99a0d9fc | d977478229302417956cd6a18f9e9fd5cf5dce31 |
| libclrjit.so | 05f9cff9e0cb9b6d6fa7d7fb21b4308d52bec755206b8c124c61a7a289e72e0e | b46d758c561eeca196c03a576cf191d007935447 |

The complete archive was transferred through one authenticated bounded LAN GET,
with zero failed requests and no persistent service. SHA/size verification
preceded Windows safe extraction. Its size is 71,241,124 bytes and SHA256 is
71c8ecbe51d8b76d746f18672ebbf072cfe470c9cd021f55db0391f1d34d7932.

[Independent local verification](../artifacts/android-session-policy/20261013-release-layout/verification-results.json)
passes all 272 tar members / 271 file sizes and hashes, the 195 player inputs,
36 layout evidence files, six layout receipts, both actual tool identities and
ten native/symbol build-id pairs. Original framework attempt2 request, evaluated
properties, inventory, raw logs and launch receipts are included. The first
framework failure remains in the separate
[core archive](../artifacts/android-session-policy/20261013-release-core-evidence/verification-results.json).

The actual Windows player input path is
`E:/RuneCLR/artifacts/android-session-policy/20261013-release-layout/extracted/layout`;
matching symbols are alongside it in `extracted/symbols`. Original remote and
Checked outputs remain preserved. No build, application or device run was
performed to create this archive.

Release acceptance still requires native policy1 with diagnostic0/mode0, IL
generated after APK installation, functional/refusal/recovery/retirement checks,
and actual Unix AMD64 interpreter method-entry samples with a trusted-native
control. Debug-only bytecode dumps cannot substitute for that Release capture.
ARM64 phones and alternate page sizes remain later platform targets.
