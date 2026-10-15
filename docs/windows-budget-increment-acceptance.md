# Windows Budget Increment Acceptance

On 2026-10-14 the matching Windows x64 Release build and all three functional
suites passed for the minimal terminal counter optimization. An independent
offline review accepted their retained raw process results and immutable
source/build/layout bindings. The earlier
[Release acceptance](windows-release-budget-acceptance.md) remains a separate
baseline; its receipts are unchanged.

## Exact Candidate

- Upstream: `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`.
- Parent: `099dacd07d8d890822f7422f895337733457ab3c`.
- Candidate: `20405f7ae23e183e038703aa5e356b3310fef427`.
- Private source: `E:/runtime-increment-20261014`.
- Build evidence: `artifacts/budget-increment/windows-release-build-20261014-attempt1`.
- Private Release layout: `artifacts/budget-increment/windows-release-build-20261014-attempt1/layout`.
- Product: `E:/runtime-increment-20261014/artifacts/bin/coreclr/windows.x64.Release`.

The candidate is a direct, single-parent child of the previously accepted
finalizer runtime. Its only changed file is `src/coreclr/vm/runeclrinstructionmeter.h`.
Inside terminal `TryConsume`, the successful remaining-budget reservation now
increments `executed` with `InterlockedIncrement64` rather than a zero-CAS read
and a CAS increment loop. The remaining-budget CAS reservation, terminal latch,
cleanup reserve, diagnostic accounting and runtime unwinding logic are unchanged.
This source description does not establish correctness or performance.

## Source And Tool Checks

The shared source checker accepts the exact baseline or a direct single-file
child whose committed bytes equal that precise eight-line to two-line
replacement. It requires a full explicit candidate SHA, matching HEAD, an
identified branch and tracked-clean worktree.

The independent auditor separately reconstructs that replacement from the
parent Git blob, checks the direct parent, changed-file list, file mode and
actual worktree bytes, and freezes precode-layout sources from the selected
candidate. Baseline `099dacd` and new `20405f7` precode binding both passed;
using either SHA with the other checkout was rejected. Evidence:
`artifacts/budget-increment/source-tool-checks-20261014-attempt1`.

The three functional drivers retain their existing business, quota, watchdog,
entry and collection checks and now pass `-CandidateCommit` explicitly to both
provenance `freeze` and `check`. The offline reviewer accepts explicit terminal,
finalizer and host evidence paths and requires the selected candidate in source
snapshots, successful build/configuration, layout and native source stamps.
For this new child, all build and functional receipts must bind the same strict
candidate validation and frozen checker hash.

Python AST and all three PowerShell parsers passed after these parameter changes.

## Measured Functional Acceptance

The fresh matching native/CoreLib/compiler build returned zero with zero
warnings/errors. The build and layout receipts bind 36 frozen source files,
seven actual native compile owners and 527 layout files to the exact candidate,
with `FEATURE_INTERPRETER=1` and `FEATURE_DYNAMIC_CODE_COMPILED=1`. Each suite
passed the exact Release provenance checks before and after execution.

| Experiment | Accepted behavior | Selected post-invocation entries |
| --- | --- | --- |
| Terminal attempt 1 | 44 process lanes, 84 scalar rows; ordinary/diagnostic controls, sticky exhaustion, catch/filter suppression, bounded cleanup, constructors, two-context isolation and twenty bad/good recovery pairs | 70 interpreted and 14 ordinary native entries |
| Finalizer attempt 1 | Nine recovery cases and six original fatal-exception controls; two queue sentinels and a fresh collected good session per recovery | Seven authored interpreted finalizers, one inherited trusted native finalizer, one suppressed finalizer |
| Host budget attempt 1 | 15 cases and 73 completed context collections; lifecycle failures, private cleanup, resource release, ordinary exceptions and recovery | 15 trusted native `MapRunner.Run` observations; author methods individually unsampled |

The previously completed new-candidate terminal attempt was read and audited
without replay. Finalizer and host-budget ran sequentially in fresh directories,
retaining their raw streams, launcher records and scalar receipts:

- `artifacts/budget-increment/windows-terminal-20261014-attempt1`.
- `artifacts/budget-increment/windows-finalizer-20261014-attempt1`.
- `artifacts/budget-increment/windows-host-budget-20261014-attempt1`.

## Independent Offline Review

Accepted output:
`artifacts/budget-increment/windows-independent-budget-review-20261014-attempt1/results.json`.
The review independently reconstructed the exact two-line candidate replacement
from its parent Git blob and checked the direct parent, changed-file list, file
mode, worktree bytes and frozen checker binding. It then verified the original
raw stdout/stderr, positive launcher PIDs, nonce/argument/environment ownership,
watchdog status, immutable runtime and fixture hashes, 14 unique managed PE
identities, definition tokens/MVIDs and the candidate's frozen precode sources.

Semantic checks passed exact execution/cleanup ledgers and sticky latches,
cross-context ownership, catch/filter/cleanup counters, finalizer definition
ownership and queue progress, retired-query guards, next-session reset, host
resource cleanup and completed collection. Fatal controls retain their original
`OperationCanceledException` or `InvalidOperationException`, nonzero owned exits
and `Finalize`/`GC.RunFinalizers` stack evidence. No watchdog termination was
accepted as recovery or as an expected fatal result. All 21 semantic corruption
controls were rejected without editing or rerunning experiment evidence.

Reproduce the offline review into a fresh output directory:

```powershell
py -3 -B eng/audit-release-budget.py --candidate-commit 20405f7ae23e183e038703aa5e356b3310fef427 --terminal-evidence artifacts/budget-increment/windows-terminal-20261014-attempt1 --finalizer-evidence artifacts/budget-increment/windows-finalizer-20261014-attempt1 --host-evidence artifacts/budget-increment/windows-host-budget-20261014-attempt1 --output artifacts/budget-increment/windows-independent-budget-review-FRESH
```

Observed output:

```text
PASS Release audit: terminal 44 lanes/84 rows/70 interpreted+14 native entries; finalizer 9 recovery+6 original fatal controls/7 interpreted+1 trusted native/1 suppressed; host 15 cases/73 collected contexts; 21 semantic corruption controls rejected
```

Post-invocation observations remain selected method entries, not a complete
invocation trace. Fatal controls and host author methods remain individually
unsampled. The suppressed already-terminated finalizer has no execution claim.
The observer's separately read precode type byte is not contained in its raw
code span. PID attribution remains the launcher-recorded process binding; raw
managed markers do not independently report a PID. These results establish no
mobile or physical-device result and do not approve production author finalizers.
Concurrent/production coverage and performance are measured separately.
