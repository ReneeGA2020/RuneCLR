# Upstream defect register

Created 2026-10-13. Record defects in official dotnet/runtime separately from
RuneCLR implementation errors, unsupported APIs and experimental hosting choices.
Prepare local fixes or workarounds first where evidence supports them; retain
the original failure and controls. RCLR-UP-001 and RCLR-UP-002 are filed; see
Filed - 2026-10-16. RCLR-UP-003 is not submitted.

## Tracked findings

The [source reproduction checker](../runtime-patch-reproduction.md) verifies
that the exported desktop stack reconstructs the pinned candidate and the two
confirmed-defect patches apply independently on top. This is patch/source
coherence evidence; each finding retains its own original failure, local
execution acceptance and official-fix review requirements.

| ID | Finding | Attribution | Local disposition | Upstream report |
| --- | --- | --- | --- | --- |
| RCLR-UP-001 | [Collectible cached-interface lifetime](collectible-cid-lifetime.md) | Confirmed failure in unmodified pinned CoreCLR; reduced fixture needs no RuneCLR runtime assemblies | Private conservative native candidate; Debug and matching Release simulator acceptance | [Ready-to-paste report](reports/001-collectible-cid-lifetime.md), [dotnet/runtime #135848](https://github.com/dotnet/runtime/issues/135848) |
| RCLR-UP-002 | [Apple simulator test-generator mapping](apple-simulator-test-generator.md) | Confirmed official generator omission and generated false condition; complete official mobile runner integration remains unverified | Private two-arm source fix passes 21/21 actual-generator/model-body checks; validated TargetOS=ios experiment workaround retained | [Ready-to-paste report](reports/002-apple-simulator-test-generator.md), [dotnet/runtime #135849](https://github.com/dotnet/runtime/issues/135849) |
| RCLR-UP-003 | [Full-framework interpreter assertion](full-framework-interpreter-assert.md) | Suspected upstream interpreter issue; minimal repro and root cause pending | Continue supported selective mode 1 experiments; no assertion bypass | Investigation, not ready to submit |

The confirmed affected source is official main commit
0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de, product .NET 12, using its own
.NET 11 RC1 build SDK. These records do not establish whether a later upstream
commit already fixes a finding. No current upstream HEAD or issue-duplication
search was performed when creating this register.

## Filing preparation - 2026-10-15

Two English reports now follow the upstream bug-report template, with expected
and actual behavior, reproduction, configuration, controls, private-fix scope
and public commit-pinned references. The [filing guide](reports/README.md)
identifies both documents and a local source/evidence attachment ZIP. Neither
issue has been submitted; no upstream issue number is assigned.

Upstream main was source-reviewed at
2ef0256337f918788487bde223a7bce2f16dffc1. The two implicated source files still
have the same Git blobs as the affected baseline. Scoped issue/PR searches
found related #134766 and #126199 with different causes, but no exact duplicate
in the reviewed results. This is not proof of behavior on a rebuilt latest main.
The actual pinned-source generator probe was freshly rebuilt and rerun on
Windows: zero build warnings/errors and 19/19 expected-baseline checks,
reproducing the skipped simulator bodies. No mobile runtime experiment was
replayed for this preparation. RCLR-UP-003 remains an investigation.

## Filed - 2026-10-16

RCLR-UP-001 is filed as [dotnet/runtime #135848](https://github.com/dotnet/runtime/issues/135848)
and RCLR-UP-002 as [dotnet/runtime #135849](https://github.com/dotnet/runtime/issues/135849).
Both were open when recorded. Filing is not an upstream fix and does not
retire the private candidates. RCLR-UP-003 was not filed. The 2026-10-15
preparation section above still describes the state before these issue
numbers existed.

## Issue status check - 2026-10-18

A read-only GitHub check finds both #135848 and #135849 still open. Their
currently reported comments total three, all from policy bots; none of those
comments links a fix. The observation is recorded at
`artifacts/lead-upstream-status-20261018cq/receipt.json`.
This check covers issue metadata and current comments, not current-main source
or a full PR graph search. It does not establish that no upstream fix exists.
No official fix is adopted, private candidate retired, runtime branch changed,
or simulator/device run added by this status check. The regression and
official-fix adoption requirements below still apply.

## Do not classify as an official defect without more evidence

| Observation | Current classification / resolution |
| --- | --- |
| Debug CoreLib with Release native fails during AppContext.Setup | Our mixed-layout integration error: Debug/Release MethodTable offsets differ; matching CoreLib/tools/composites pass. See [Release investigation](../ios-r2r-release-validation.md). |
| AssemblyDependencyResolver unavailable on Android/iOS | Explicit upstream platform limitation, not an unexpected runtime regression. RuneCLR uses [explicit resolution](../package-resolution.md). |
| First private corerun layout cannot locate hostpolicy | Our original hosting/dependency-resolver integration mismatch. |
| A clr.runtime-only clean build cannot install the Compression native archive | Native build prerequisite/subset problem; clr.runtime+clr.native succeeds. Not presently established as an upstream build-graph defect. |
| Crossgen input PE is also its rewritten output | Our packaging input/output misuse. Separate original-input files resolve it; the failed compiler attempt is not evidence of a player runtime bug. |
| Release controlled-player receipt says 0/0 despite raw 15/15 | Our count-parser error. The original failure is retained; a corrected read-only reassessment passes without replaying the app. See [Release package evidence](../ios-r2r-release-packages.md). |
| Native package-entry capture misses 15/15 in the app's unified JSON log | Our raw-text parser misses JSON's escaped slash. The eventMessage values contain fifteen PASS events and the aggregate; a read-only assessment preserves the original receipt. See [native package entry evidence](../ios-release-package-entry.md). |
| Official standalone runner exits 100 | Insufficient evidence of test execution; inspect generated conditions and actual payload output. RCLR-UP-002 records a specific upstream cause. |

## Reassess an official fix before adopting it

1. Link the actual upstream issue/PR and fix commit to the relevant record.
   Record the source revision checked, review date and affected platform/configuration.
   A release number or an issue marked closed is not acceptance evidence.
2. Inspect the official fix's ownership/configuration assumptions and overlap with
   our private changes. Build a separate clean worktree using matching native,
   CoreLib, tools and framework inputs. Keep previous failing/passing evidence.
3. Run that record's regression gates on the upstream fix without our overlapping
   patch. Compare with the private candidate where practical. Require actual
   execution/retirement evidence, not merely launcher or test-runner exit codes.
4. Replace or remove only the overlapping private change after those gates pass.
   Record the replacement commit, evidence paths and any remaining local differences.
   If it fixes only some topologies, retain the unresolved scope in the register.

Each record carries its own expected behavior, evidence, local disposition,
filing draft and acceptance gates. Keep confidence distinct from operational
impact: a high-impact crash can remain a suspected defect until attribution is clear.
