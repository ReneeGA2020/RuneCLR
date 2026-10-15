# RCLR-UP-001: Collectible cached-interface lifetime

Status on 2026-10-13: confirmed pinned-upstream defect; local candidate validated;
upstream report not submitted; latest upstream fix status unknown.

## Attribution and impact

Unmodified official CoreCLR at
0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de fails in the ARM64 iOS simulator
when a trusted R2R caller invokes an interpreted interface implementation in a
collectible AssemblyLoadContext across completed context retirement.
Expected behavior is normal managed execution, fresh plugin state and eventual
context collection. The measured result is a native process fault after retirement.

The reduced managed fixture has a shared interface, trusted caller and plugin;
it does not require RuneCLR.Runtime, packaging, gameplay APIs or quota checks.
Original native runtime and identical managed/composite inputs fail; preventing
the offending cache publication or using an IL caller changes the outcome.
This attributes the lifetime problem to CoreCLR, while retaining the important
qualification that simulator packaging uses a private native wrapper.
Physical devices and complete upstream XHarness execution have not established
this finding independently. Passing Windows controls do not reproduce it.

The implicated source is src/coreclr/vm/virtualcallstub.cpp,
CachedInterfaceDispatchResolveWorker. A dispatch cache owned by a longer-lived
caller can retain a collectible target beyond its allocator lifetime. A dynamic
interface receiver can be noncollectible while its implementation owner is collectible.
Treat receiver and implementation ownership separately when reviewing a fix.

## Evidence and existing local fix

- [Minimal controls and diagnostic attribution](../ios-r2r-minimal.md): forty
  groups, thirty-four passing controls and six expected original/diagnostic faults.
- [Dynamic implementation owner](../ios-cid-dynamic-repro.md): receiver-only v1
  is insufficient; the v2 candidate and IL controls each complete twenty retirements.
- [Candidate source and tradeoff](../ios-r2r-fix-candidate.md): private commit
  8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d. The resolved target is still invoked;
  collectible and dynamic-interface receivers do not publish CID mappings.
- [Fresh Debug acceptance](../ios-r2r-clean-build.md): lifecycle 21/21,
  controlled packages 15/15 and twenty-session collected probes.
- [Matching Release acceptance](../ios-r2r-release-validation.md): lifecycle
  21/21, twenty retirements/sixty calls and sampled native interpreter entries.
- [Interface boundaries](../ios-r2r-interface-boundaries.md) and
  [official managed runners](../ios-r2r-official-managed-tests.md) supply additional
  regressions; their actual execution scopes remain as recorded.

The exact small [portable candidate patch](../../eng/runtime-patches/0001-collectible-cid-publication.patch)
is retained in RuneCLR; full runtime source is not vendored. It matches the
private candidate's patch receipt, SHA-256
43b36606fa94967e97f2640e8d76dcfa8f0af21eeb77a065a0eea5c83c915857.
The local baseline runtime repository and installed runtimes remain unchanged.
This is a conservative private fix, not an upstream-approved implementation.
It trades caching for lifetime safety; dispatch cost and other cache topologies
remain unmeasured. [Release controlled packages](../ios-r2r-release-packages.md)
pass 15/15 functional cases; the subsequent
[native package/helper capture](../ios-release-package-entry.md) records 33
valid samples covering all 23 required method groups on those fixed inputs.
The later [combined immutable-session Release build](../ios-session-policy-build.md)
retains this exact guard and passes the current lifecycle 24/24, packages
15/15 and twenty selection sessions/collections with the global diagnostic
disabled. Its separate native samples cover nine installed selection-fixture
groups. These combined-candidate results extend integration coverage; they do
not replace the original failing controls or establish upstream approval.

## Future issue draft

Suggested title: Cached interface dispatch retains collectible targets across
AssemblyLoadContext retirement on iOS CoreCLR.

Suggested body: On official main commit 0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de,
an ARM64 iOS simulator experiment fails with a native fault when an R2R caller
invokes a collectible interpreted interface implementation across completed ALC
retirement. The reduced managed fixture has no RuneCLR dependencies. Native and
managed input identities, retirement observations and caller-layout controls are
retained. A conservative publication guard passes our Debug and matching Release
regressions. A receiver-only guard is insufficient for dynamic interface
implementation owners. We would welcome review of allocator ownership and cache
invalidation. These results use private simulator packaging, not physical-device
or complete upstream XHarness acceptance. Attach a reviewed portable fixture and
selected logs when submitting; link the candidate and its measured limitations.

## Official-fix acceptance gates

Run collectible receivers and noncollectible dynamic receivers with collectible
implementation owners; include original failing controls, retained/noncollectible
controls, interface variance/default/generic/value/exception cases and repeated
completed retirement. Repeat full lifecycle and controlled-package acceptance.
Require matching Debug/Release runtime-critical inputs and actual interpreter
execution evidence. Review concurrent publication, performance and physical-device
scope separately. Do not remove the local guard solely because an upstream change
mentions collectible types or because an unrelated Windows test passes.
