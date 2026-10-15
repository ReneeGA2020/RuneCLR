# RCLR-UP-002: Apple simulator test-generator mapping

Status on 2026-10-13: confirmed mapping omission and skipped generated bodies at
the pinned source; validated local source fix, actual source-fixed standalone
simulator execution and earlier configuration workaround; not reported upstream.
Complete official simulator runner integration and latest upstream fix status remain unknown.

## Official source inconsistency

At 0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de, the official
src/tests/build.sh advertises ios and iossimulator targets. Official execution
targets also distinguish the simulator. However,
src/tests/Common/XUnitWrapperGenerator/XUnitWrapperGenerator.cs,
GetPlatformForTargetOS, recognizes ios but not iossimulator; unknown values return zero.
The same omission exists for tvossimulator, but that target has not been executed
in our experiment and must not be reported as a measured failure.

Generated standalone Main for GenericVirtualMethod and ResolvedFromDifferentContext
under TargetOS=iossimulator contains a GC-stress guard ending in (false).
The test body is therefore skipped even though the runner can return 100.
Expected behavior is applying the iOS platform condition and normal declared skip
conditions, or clearly rejecting an unsupported target, rather than silently
turning those bodies into non-executing tests.

No custom generator or test-source change causes this result. The preserved
official source, generated Main and build properties establish it. Our private
packaging does not establish that every official merged/mobile runner has the
same behavior; confirm that path before making a broader upstream claim.

## Local workaround and evidence

Generate the managed official standalone runner with TargetOS=ios. Keep
crossgen2 targetos=iossimulator, native simulator targeting and actual simulator
execution unchanged. The corrected managed conditions use OperatingSystem.IsIOS
and exclude MacCatalyst; this is not a physical-device result.

Four official generated managed entrypoints execute and pass with positive
payload evidence. The generator and tests are not patched. This is a validated
configuration workaround, not a claim that the default official mobile workflow
is fixed. See [the exact source/generated comparison and receipts](../ios-r2r-official-managed-tests.md).
Evidence archive SHA-256 is
05eabfd1fbd2fb4f2c432a10e2b29b8b35d9453d279c514e365c11a69c012e71.

The [direct source fix and generated-output regression](../apple-generator-regression.md)
now map both simulator aliases to their existing platform conditions. Private
commit 2f3ef1faaf3630f3f57c5402ebd1ab20445b0692 changes two switch arms in a
separate runtime worktree. Its actual-source Roslyn probe reproduces the original
false guard and skipped bodies, then passes 21/21 generated-body/condition
checks with alias-equivalent Main and unchanged existing-target output. The
generated Main executes against a controlled platform model on desktop; this
does not replace actual official mobile-runner execution or establish tvOS
platform support. A later actual official-project rebuild and simulator run
now passes with the source fix and TargetOS=iossimulator, as detailed below.
The earlier managed-target workaround evidence remains unchanged. The
[portable patch](../../eng/runtime-patches/0002-apple-simulator-test-generator.patch)
is retained with the exact tested source and receipts.

## Source-fixed official standalone execution

On 2026-10-13, all four unchanged official managed projects were actually
rebuilt using the fixed official generator and TargetOS=iossimulator. The
native target and actual simulator execution also remain iossimulator. The
two conditional entrypoints have valid iOS/MacCatalyst and GC-stress guards;
none contains the old false guard. All four official Main entrypoints pass
with their original assertions and specific positive payload evidence, not
just exit 100. Independent verification records 41/41 checks true.

This new isolated test source commit is
4ffb6fe2a784aa36a83c9382498f0767edfaec92, combining the existing CID v2 base
with only the two generator switch-arm changes. Native/framework artifacts
remain the matching Debug candidate; no runtime rebuild or test-source edits
were required. The owned simulator is shut down.

See [the actual project builds, generated guards, execution and preserved
failures](../ios-generator-fixed-tests.md). The locally downloaded successful
archive has SHA-256
f035d56f77d524a53cab93ecdbaad06910831779b6f46afc8ed5a1e89fb30b68.
Two earlier patch-format preparation failures are separately preserved; no
app ran in those attempts. The original CRLF patch export is retained in
snapshots, and the current portable patch uses LF for the Mac source checkout.

This removes the managed-target workaround for this new standalone experiment.
Packaging/launching still use the private native UIKit wrapper. Full upstream
XHarness/Helix, tvOS execution and current upstream fix status remain unverified.

## Prepared issue report

The [complete English report](reports/002-apple-simulator-test-generator.md)
follows the upstream template and supplies a desktop command that invokes the
actual official generator, expected/actual body masks, a two-arm patch and
separately scoped simulator results. It supersedes the short draft below.
See the [filing guide](reports/README.md) for the source/evidence attachment and
2026-10-15 source/duplicate review. No issue has been submitted.

Suggested title: XUnitWrapperGenerator silently skips conditional test bodies
when TargetOS is iossimulator.

Suggested body: The official CoreCLR build script accepts iossimulator, but
GetPlatformForTargetOS at commit 0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de
does not map that value. Two unchanged Loader/CollectibleAssemblies projects
generate standalone Main conditions containing false and can return 100 without
executing their bodies. We retain both generated-source configurations.
Generating with TargetOS=ios produces an iOS runtime condition and the same
official test bodies actually execute on the ARM64 simulator. Please confirm
the expected target normalization and consider alias handling or a diagnostic
for unsupported values. Attach generated Main comparisons and exact MSBuild
properties; distinguish standalone generation from full mobile runner execution.
The proposed two-arm simulator alias source fix also passes actual unchanged
official-project rebuilds and all four standalone tests with TargetOS=iossimulator.

## Official-fix acceptance gates

Generate the unchanged projects with ios and iossimulator and compare their
platform/GC-stress semantics. Verify valid runtime platform conditions, actual
payload execution and intended skips. Include an invalid target diagnostic case
if that is the chosen official fix. Review tvOS/MacCatalyst separately instead
of broadening a simulator alias to AnyOS. Revalidate the real official mobile
runner before removing our managed-target workaround.
