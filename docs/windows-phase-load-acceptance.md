# Windows phase-load functional acceptance

On 2026-10-14, both explicit OFF and ON profiles of the isolated phase-load
candidate passed all sixteen recorded functional suite/auditor commands on
the matching private Windows x64 Release layout. This is functional acceptance
of the tested profiles; configuration records alone do not establish that
the new acquire branch executed. No benchmark was run.

Runtime commit is `a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186`, direct parent
`20405f7ae23e183e038703aa5e356b3310fef427`, upstream
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. The
[fresh build/layout receipt](../artifacts/phase-load/windows-release-build-20261014-attempt1/layout-receipt.json)
binds the native runtime, CoreLib, compiler, 36 patched sources, seven native
compile owners and 527 layout files. The
[paired native header compilation](../artifacts/phase-load/header-layout-20261014-attempt2/layout-receipt.json)
confirms unchanged old field offsets and size48/align8; the immutable cached
flag occupies padding at offset2. The option defaults to OFF.

## Recorded Results

Each profile has a fixed `DOTNET_RuneCLRPhaseAcquireLoad` value (0 or 1) in
its child settings. Other selection settings retain the accepted Release
profile. Exact source/build/layout guards run before and after the suites.

| Suite or audit | OFF | ON | Evidence boundary |
| --- | --- | --- | --- |
| Terminal | PASS: 44 lanes / 84 rows | PASS: 44 lanes / 84 rows | 70 interpreted and 14 native post-invocation selected entries per profile |
| Finalizer | PASS: 9 recovery lanes + 6 original fatal controls | PASS: 9 recovery lanes + 6 original fatal controls | 7 interpreted, 1 trusted native and 1 suppressed observation; no fatal per-method entry samples |
| Host budgets | PASS: 15 cases / 73 collected contexts | PASS: 15 cases / 73 collected contexts | Ordinary failures, sticky termination, bounded cleanup, resource cleanup and next-session recovery |
| Combined budget audit | PASS: 22 rejected corruption controls | PASS: 22 rejected corruption controls | Raw/process/nonce/PE-definition/scalar-ledger bindings, including an altered phase switch |
| Joined-worker concurrency | PASS: 36 processes / 72 collected contexts | PASS: 36 processes / 72 collected contexts | 2 or 4 trusted workers, exact joined execution/cleanup ledgers, owner isolation and recovery; 10 driver corruption controls |
| Independent concurrency audit | PASS: 156 selected entries / 4 rejected ledger controls | PASS: 156 selected entries / 4 rejected ledger controls | Offline raw/PE/quiescent-ledger review; no scheduler trace or transactional snapshots |
| Production and official controls | PASS: 9 functional rows | PASS: 9 functional rows | Five business controls and four original official tests |
| Independent production audit | PASS: 9 rejected corruption controls | PASS: 9 rejected corruption controls | 24 original official source files remain bound; phase-switch alteration rejected; no method-entry claim |

Business controls include the lifecycle harness, normal/late-IL/controlled
package samples and package-execution harness. The original official tests are
GenericVirtualMethod, CollectibleStatics, ResolvedFromDifferentContext and
ByRefLocals. Their original assertions and generated-entry guards are retained.
Their functional pass does not imply that they exercise a terminal meter.

## Exact Receipts

The [run receipt](../artifacts/phase-load/windows-acceptance-run-20261014-attempt1/run-receipt.json)
records sixteen successful commands, PIDs, raw stdout/stderr hashes and profiles.
The [preparation manifest](../artifacts/phase-load/windows-acceptance-preparation-20261014-attempt2/preparation.json)
binds both source snapshots and complete command lists, including the frozen
`artifacts/session-finalizer/upstream-20261013-attempt1` inputs. Attempt1 is
preserved; attempt2 adds production commands and explicit 22/9 audit-count
guards. Actual profile binding, 18 Python AST parses, six PowerShell parses
and four profile-binding corruption controls per profile pass before execution.

| Profile | Budget audit | Concurrency audit | Production audit |
| --- | --- | --- | --- |
| OFF | [results](../artifacts/phase-load/windows-acceptance-preparation-20261014-attempt2/off/evidence/budget-audit/results.json) | [results](../artifacts/phase-load/windows-acceptance-preparation-20261014-attempt2/off/evidence/concurrency-audit.json/results.json) | [results](../artifacts/phase-load/windows-acceptance-preparation-20261014-attempt2/off/evidence/production-audit.json) |
| ON | [results](../artifacts/phase-load/windows-acceptance-preparation-20261014-attempt2/on/evidence/budget-audit/results.json) | [results](../artifacts/phase-load/windows-acceptance-preparation-20261014-attempt2/on/evidence/concurrency-audit.json/results.json) | [results](../artifacts/phase-load/windows-acceptance-preparation-20261014-attempt2/on/evidence/production-audit.json) |

Use [the preparation driver](../eng/prepare-phase-load-windows.py) with a fresh
output directory and explicit upstream input, then execute its frozen
`off/eng/commands.json` and `on/eng/commands.json` through
[the functional runner](../eng/run-phase-load-windows.py). Successful commands
are preserved rather than rerun. The old runtime-candidate and acceptance
tools retain their original guards. The generated benchmark-named sibling
contains only the full provenance helper; it has no benchmark entry point.

## Limits

The exact candidate checker binds the direct-child tree and the two changed
source blobs. The functional provenance binds the complete patched build
source inventory; three precode source files are inspected separately. These
checks establish identity and tested outcomes, not acquire-branch execution.
See the separate [actual machine-code review](windows-phase-load-hotpath.md)
for emitted paths and ordering qualifications. Live branch observation is a
separate experiment and is not claimed by this document.

Post-invocation selected entries are not a complete invocation or opcode trace.
Host-budget author methods and fatal controls are not individually sampled.
Finalizer tests preserve CLR unwinding and queue recovery boundaries, while
production author finalizers remain unsupported by the prototype. Joined
snapshots do not establish transactional live snapshots or close the existing
phase-read/admission gap. Acquire loads retain weaker ordering than the old
full interlocked read fence.

These results cover Windows x64 only. No new ARM64/mobile build, physical
device acceptance, instruction batching, throughput measurement, time quota
or security-sandbox guarantee follows from them.
