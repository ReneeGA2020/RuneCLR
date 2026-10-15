# iOS Device Application Preparation

The [device runtime build](ios-device-batch-build.md) now has verified native,
CoreLib and Mac-host compiler products. The next application uses matching
device framework IL/R2R products and the existing 15-case host budget harness,
including 73 collectible contexts and same-process bad/good recovery.
The [matching device framework](ios-device-batch-framework.md) now completes
181 raw/R2R components. Its subsequent unsigned application construction and
post-build author preparation are now accepted; physical execution remains
unperformed.
The [matching unsigned application build](ios-device-application-build.md) is
now completes from one launch with frozen source and durable result receipts.
Its compilation/output acceptance is separate from physical-device execution.

## Unsigned Build Route

The [source preflight](../eng/ios-device-application-preflight.py) checks the
actual archived ARM64 device runtime, three critical product hashes and four
frozen trusted harness components. The official AppleAppBuilder/Xcode source
supports `DevTeamProvisioning=-`, emitting `CODE_SIGN_IDENTITY=""`,
`CODE_SIGNING_REQUIRED=NO` and `CODE_SIGNING_ALLOWED=NO`. It selects the
iphoneos SDK for the device target. These source checks prepare an unsigned
application build; they neither build an app nor establish installability.
Actual offline preflight passes all three critical device products and four
trusted components at
`D:/RuneCLR-Android/device-build/device-app-preparation-20261015-attempt2/`.
Its three rejection controls refuse platform 7, an author DLL in the trusted
directory and altered trusted bytes. The initial attempt remains separately
retained. Matching-source Apple generator files agree with the inspected
upstream source after LF normalization; the framework archive retains their
remote provenance separately.
The strengthened source preflight is also rerun successfully in
`D:/RuneCLR-Android/device-build/device-app-preparation-20261015-attempt3/`.
It now requires the frozen harness source hash as well as case/count checks;
its framework/application/execution flags remain false because this tool only
performs source and native-input preflight. Earlier receipts remain unchanged.

Retain actual device-platform Mach-O checks for the executable and every linked
dylib, application deployment 15.3, the trusted composite/input identities and resolved
native dependencies. Check whether the linker inserts an ad-hoc signature even
when Xcode signing is disabled. Simulator executables, native shims and
framework composites cannot be reused as device-native products.
Native dependencies may declare an earlier minimum OS (the actual new device
shims compile for 13.0); require their minimum to be compatible with the app's
15.3 minimum rather than demanding every shim equal the CoreCLR minimum.

Create a fresh bundle with no compiler or author DLLs. Its trusted bridge calls
`MobileHostBudgetProbe.Entry.Run` with the fixed `all` case selection; it
does not use a desktop executable entry point or an author-supplied build
project. The harness source and frozen trusted input manifest remain unchanged.

## Newly Compiled Author IL

The [fresh author compiler](../eng/prepare-ios-device-author.py) invokes the
explicit private RC1 Roslyn compiler directly against fixed reference DLLs,
the frozen shared contract and the two original host-budget fixture sources.
It adds a unique assembly metadata marker to produce fresh DLL bytes while
retaining the fixed lifecycle scenarios. Author project files, generators and
build scripts are not executed. Each compiler response, stdout/stderr, source,
reference and output hash is retained. Outputs must be IL-only with no R2R.

The `sanity` phase prepares actual fixture DLLs without claiming a device host.
The `prepare` phase first inventories an actual unsigned device bundle, checks
device-platform executable/native bytes and author absence, then generates
the marker/source and compiles. It requires unchanged host bundle hashes
after compilation. A later review corrected the bundle guard to require an
`MH_EXECUTE` main, `MH_DYLIB` native libraries, no `LC_CODE_SIGNATURE` commands
and application minimum15.3. Device library minima may be earlier compatible
versions. This fixes preparation-tool misclassification and does not prove
installability. Its matching native hash check is for the unsigned build;
signed installed products need separate signing/delivery provenance.

The corrected guards pass ten independent controls at
`D:/RuneCLR-Android/device-build/device-author-static-review-20261015-attempt2/review.json`
(SHA256 `27e180239de16e4225991d62168f4de8e846517acb0b13f506dbb1fecba7a6a9`).
They reject the two original misclassifications and incompatible minima,
accept synthetic unsigned executable/native declarations, retain compatible
13.0 dylibs and reject harness source drift. These are parser/source-gate
controls, not a constructed or installable app. The original compiler/desktop
receipts below refer to the earlier frozen driver; compilation code is unchanged.

The first actual Windows compiler sanity passes two fresh author assemblies at
`D:/RuneCLR-Android/device-build/fresh-author-sanity-20261015-attempt1/`.
This establishes preparation, not execution or compilation after an actual
device host build. The independent replay/finite execution check is recorded
separately below.

The [independent verification driver](../eng/verify-ios-device-author.py) now
passes a second actual compiler run: two DLLs have new nonces/hashes/MVIDs and
remain IL-only, with unchanged fixed source and references. The frozen desktop
stock host also runs `Normal` against the new fixtures: 20 sessions/20 collected
contexts, static reset, three ticks and resource cleanup all pass. Four
rejection controls cover author-bundled/device-platform guards, altered input
manifest and a damaged private dependency. The first two are explicitly
synthetic bundle controls; the latter two use actual child-process failures.
Evidence is at
`D:/RuneCLR-Android/device-build/fresh-author-independent-20261015-attempt1/review.json`
(SHA256 `ad8f5654c7469994e1bc0f35663425ff05cbc7ff9d5b1caa04562a15409a6c03`).
Normal does not call the private Helper method; this control validates its
dependency identity declaration/rejection, not a private-method execution entry.
Device bundle binding and physical execution remain false.

## Device Run Sequence

Complete and inspect the device framework and unsigned app first. Then resolve
the [device connection/signing prerequisites](ios-device-readiness.md), sign
the exact inspected products and retain their new hashes. Deliver author IL
after host installation; preserve host-build/author-compile/install/delivery
ordering and verify delivered versus loaded author identity. Author IL need
not be compiled on the device.

Run the fixed lifecycle/terminal recovery cases and inspect actual interpreter
method entries, static reset, resource cleanup and completed retirement.
Neither the unsigned build route nor desktop compiler/collection controls
satisfy this physical-device acceptance.
