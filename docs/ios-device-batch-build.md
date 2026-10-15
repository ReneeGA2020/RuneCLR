# iOS Device-Target Batch Runtime Build

On 2026-10-15, a fresh private `ios.arm64.Release` runtime build completed on
the configured Mac with exit 0, zero warnings/errors and elapsed 5m21s. It uses
the actual iphoneos SDK 27 and minimum deployment 15.3. This is a native,
CoreLib and crossarch-compiler build. The subsequent
[matching framework layout](ios-device-batch-framework.md) has also completed;
the [unsigned application](ios-device-application-build.md) is now accepted.
Physical-device execution remains unperformed.

## Source And Build

The separate runtime source is upstream
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` plus the same controlled mobile
patch set used by the simulator/emulator batch experiments:

- Source commit: `3126bbc9a8851a09ac6435b18a12882bad48f3ee`.
- Source tree: `710936ae1729a5689ab0e0896f3cf722ddd3d31c`.
- Source proof SHA256: `29d83ae68ca57ec2067261d15a901e81f8422981609f1fe6aaad5cb37879de5e`.
- Build SDK: private `11.0.100-rc.1.26420.103`; source product is .NET12.

The [device build adapter](../eng/ios-device-batch-build.py) creates a dedicated
fresh worktree, checks 38 source hashes/ten patches and preserves earlier
simulator/Android runtime and timing-app products. The actual build uses
`-os ios -arch arm64 -cross -c Release -clrinterpreter`, the subset
`clr.runtime+clr.native+clr.corelib+clr.tools+clr.crossarchtools`, Ninja and
the iphoneos sysroot. It reuses only a fixed SDK APFS clone, not prior native
or managed build artifacts. No installed runtime or global environment is replaced.

## Checked Products

The retained commands/objects and caches bind eight device-native owners to
Release, ARM64, iphoneos SDK and deployment 15.3; the two crossarch compiler
owners use the Mac-host SDK. Runtime Mach-O
`LC_BUILD_VERSION` declares platform 2 (iOS), rather than platform 7 (simulator).
Interpreter code is statically built and dynamic JIT is disabled. These are
source/build properties; they do not prove execution of a downloaded script.

Three CoreLib metadata stages retain the private session policy/meter ABI and
trimming roots. Batch preprocessing retains 47 safe opcodes, native meter
size 72/alignment 8 and interval offset 64. The device-native platform check
rejects actual simulator output and a platform 7 mutation in the device lane.

| Product | SHA256 |
| --- | --- |
| libcoreclr.dylib | `34c27daf3d6ef73a1558c21733d9f101bea4dcc839b9380d182d68cea2e2b93b` |
| CoreLib IL | `9ce8a9f4028c66521b6211f7ca58df060b980208d449dfddbec0c1fd4451c0b0` |
| Host crossgen2 | `a518c15912febb36f48bce3c13b5d1e6fd85f45780c7a9d00860c71cb2d6c337` |

The [durable handoff](../artifacts/ios-device-batch-build-handoff-20261015-attempt1/results.json)
records the single actual launch and completion; the
[cleanup receipt](../artifacts/ios-device-batch-build-handoff-20261015-attempt1/cleanup.json)
checks the supervisor/build/transfer processes exited. Large original products,
compile objects/databases/caches and raw logs are retained at
`D:/RuneCLR-Android/device-build/ios-device-batch-build-receipts-20261015-attempt1/extracted/`.
The archive SHA256 is
`67581c654ff848cab2f59706c8ad98ad665b5406dfdb4e8d95d77cd33fc352b1`.
All 137 payload sizes/hashes pass. This archive verification is separate from
independent source/product review.

The subsequent independent review now also passes at
`D:/RuneCLR-Android/device-build/independent-review-20261015-attempt1/review.json`
(SHA256 `307eb2573b276df823e1c45a83bda9ec64f00aeb43d5b94c092d5c1d6c07bb44`).
It directly parses actual Mach-O platform/minimum, all ten compile-owner
database rows/object hashes and CoreLib PE/MVID/IL-only metadata. Each of the
three CoreLib stages retains 52 private ABI methods with matching tokens,
owners, signatures, visibility and PInvoke/ImplMap native entries. The source
proof, actual build commands/completion streams and batch preprocessing bytes
are checked against the original archive. Prior-product preservation uses
archived before/after receipts; this offline review does not reread live Mac
files or claim runtime execution.

## Remaining Device Acceptance

The [unsigned application preparation](ios-device-application-preparation.md)
now verifies the official no-sign route and fixed 15-case/73-context harness
inputs. Newly compiled fixture IL also passes separate desktop finite-session
controls. The matching device framework now completes 181 raw/R2R components;
these preparation/build results do not establish an application or physical execution.

Construct the matching application using the accepted framework/R2R layout, then run the
post-install author IL lifecycle, ordinary failure/terminal-budget recovery
and collectible-context retirement on physical hardware with method-entry
evidence. Simulator timing and this native build do not satisfy those checks.

The [readiness record](ios-device-readiness.md) still reports an unavailable
CoreDevice tunnel/DDI uncertainty and no provisioning profile matching the
candidate bundle/device/identity together. Native building needed neither a
connected device nor signing changes; this experiment changed neither.
