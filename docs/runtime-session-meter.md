# Diagnostic session instruction meter

On 2026-10-13, the standalone [fixture](../eng/session-meter-probe/Host/Program.cs)
and [driver](../eng/verify-session-meter.ps1) were prepared for the private
instruction-meter candidate. The final stock-SDK smoke passed twenty exact-value
sessions and twenty collectible-context retirements; both project builds reported
zero warnings and zero errors. Its
[receipt](../artifacts/session-budget/meter-20261013/stock-smoke-attempt2/results.json)
explicitly says `executionVerified=false`. The later matching private Windows
Checked candidate passed all three actual processes: metered, compatibility,
and trusted-host concurrent. That separate acceptance is recorded below.

The meter records actual interpreter IR opcode dispatches. It neither throws an
exhaustion exception nor terminates a script. Remaining zero means diagnostic
exhaustion; finite code still returns and its executed counter continues growing.
The [terminal-budget proposal](runtime-session-budget-plan.md) is a separate,
unimplemented feature. This fixture does not expand the production package/API
profile or allow author-created background work.

## Candidate and bridge

The source reviewed for this fixture is the separate
`E:/runtime-budget-20261013` worktree at
`b8e5b0b4b7db30385265f935c00a39a3ba507aea`, parent
`5972a86966e56ae5f468a3e042327f0051e923d5` and official base
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. These are private RuneCLR
accounting changes; this document makes no Microsoft-defect attribution.

Private matching CoreLib methods are invoked through exact typed reflection
delegates. There is no stock-runtime meter fallback:

| Method on AssemblyLoadContext | Contract |
| --- | --- |
| RuneCLR_CreateInstructionMetered(name, managedResolver, long limit) | Collectible, interpreter-required context; strictly positive limit |
| RuneCLR_GetInstructionMeterVersion() | Static version 1 |
| RuneCLR_GetInstructionMeterRemaining() | Instance long, saturating at zero |
| RuneCLR_GetInstructionMeterExecuted() | Instance long, saturating at long.MaxValue |
| RuneCLR_GetInstructionMeterExhausted() | Instance bool, remaining == 0 |

The resolver is supplied at creation and returns the host-owned contract assembly
or a fixture-private assembly loaded into that same context. Creation verifies the
existing native execution-policy query is one. The fixture inspects private bridge
signatures and records the read-only meter method declarations; it rejects a
meter method named as a setter. Ordinary and required-but-unmetered contexts
must reject all three queries with InvalidOperationException. All three getters
must also reject a context immediately after Unload, before collection is observed.

The source hook in `src/coreclr/vm/interpexec.cpp` resolves the current MethodDesc's
defining-module binder on every dispatch. Both the Windows switch dispatcher
and the non-Windows Release computed-goto macro contain the charge. The native
state belongs to CustomAssemblyBinder; the state contains no managed roots.
This source review does not establish execution of the computed-goto path.
An opcode unit includes interpreter debug opcodes and their real dispatches;
it is not a C# statement, IL instruction, CPU instruction, elapsed-time quota,
allocation limit or native-call duration.

## Meaningful fixture checks

The trusted host, shared contract, collectible payload and private dependency are
four small projects outside the production solution. No author csproj or build
script is accepted as production input. All source is a fixed trusted experiment.

Each normal frame returns only scalar dictionaries, a scalar snapshot and a
WeakReference. Reflection types, author objects/delegates and exceptions remain
inside a non-inlined frame. Diagnostic GC runs only after that frame returns.

| Check | Assertion |
| --- | --- |
| Twenty fresh sessions | Static starts and instance count both one; identical business values; twenty contexts collected |
| Static/instance initialization | Explicit RunClassConstructor and subsequent instance creation each produce positive separate deltas |
| Empty versus finite loop | Loop(1000) returns 499500; its delta exceeds ten times properties/empty delta |
| Private late load | Dependency absent before Helper, then owned by the same ALC; constructor/cctor/private generic and generic class cctor actually return helper value 27 |
| Return to trusted host | TrustedBusy after author/private return leaves all three snapshot values unchanged |
| Trusted callback and generic definition | Interface callback returns 30; trusted generic definition instantiated with collectible type returns 46; author static body produces a positive delta |
| Direct, virtual and delegate bodies | Combined value 33, positive opcode increment |
| Catch, filter, finally | Actual InvalidOperationException, filter side effect 2, catch 3, finally 5; result 10 and positive increment |
| Diagnostic limit one | Exhausted before a final finite call; call returns 35 and increases executed count while remaining stays zero |
| Invalid limits | Zero and minus one rejected with ArgumentOutOfRangeException |
| Maximum valid limit | long.MaxValue limit remains positive; remaining equals limit minus measured executed count |
| Two interleaved ALCs | Left/right callbacks increment only their own counters, including restoration to left and subsequent trusted work |
| Unmetered compatibility | Same payload bytes execute ordinary and interpreter-required contexts; all meter getters reject both |
| Optional trusted-host concurrency | Four joined finite calls return total 1998000; executed delta equals four times one warmed call's exact delta |

All three snapshot reads are separate calls. Equality checks occur only without
concurrent authored execution, or after every trusted task has joined. The fixture
does not advertise an atomic three-field snapshot. It tests the near-maximum
limit arithmetic, not actually executing long.MaxValue opcodes or reaching the
executed-counter saturation boundary. It also does not measure finalizers, an
OnStop policy, allocation limits, native-call interruption or terminal catch escape.

## Reproduce and retain failures

Use a fresh directory for each run. Stock smoke proves only values/collection:

~~~powershell
./eng/verify-session-meter.ps1 -StockSmoke -EvidenceDirectory artifacts/session-budget/meter-20261013/stock-smoke-new
~~~

The matching Checked candidate requires explicit source identity and layout:

~~~powershell
./eng/verify-session-meter.ps1 -RuntimeRepo E:/runtime-budget-20261013 -RuntimeLayout <fresh-matching-private-layout> -CandidateCommit b8e5b0b4b7db30385265f935c00a39a3ba507aea -EvidenceDirectory artifacts/session-budget/meter-20261013/candidate-new -Concurrent
~~~

The driver validates the exact tracked-clean source commit, upstream ancestry,
CoreCLR source stamp and matching CoreCLR/JIT/interpreter/CoreLib hashes. It saves
source copies, driver bytes, managed identities, child settings/argument vectors,
stdout/stderr, diagnostics and results. Every child has a 180-second deadline;
an owned hung process tree is killed and remains a failed run with saved streams.
No installed runtime or global environment is changed.

The metered process uses InterpMode=0, the collectible diagnostic switch zero,
R2R and tiering enabled. Its checks require seventeen selected successful bytecode
method groups at least twenty times, no reported author-definition JIT compilation,
and positive native trusted RunFrame compilation. The separate compatibility
process requires positive ordinary author JIT and required-unmetered bytecode;
its ordinary compilation cannot contaminate the metered negative check.

Counters and values are actual execution checks; successful bytecode dumps prove
compilation and aid execution selection attribution. They are not an exhaustive
native method-entry trace. Submitted R2R author bodies are not part of this fixture.
Desktop Checked switch-dispatch results do not establish mobile
Release computed-goto accounting, device performance or physical-device support.

## Measured Windows Checked acceptance

The [fresh build result](../artifacts/session-budget/meter-build-20261013-attempt1/build-result.json)
reports exit zero and its retained log reports zero warnings/errors.
The [compile evidence](../artifacts/session-budget/meter-build-20261013-attempt1/compile-evidence.json)
binds all eleven changed sources, the three actual native compile owners and
fresh runtime-critical hashes. The
[matching layout receipt](../artifacts/session-budget/meter-build-20261013-attempt1/layout-receipt.json)
records 517 framework hashes, with fresh matching CoreCLR/CoreLib/compiler and
unchanged same-base libraries/hosts. These are private experimental inputs,
not a shipping runtime pack. The four-stage
[CoreLib metadata review](../artifacts/instruction-meter/metadata-20261013-attempt2/results.json)
checks old policy5, new meter8, four new QCalls, exact generated hidden-error
ABI and private bridge roots. The first metadata-tool attempt's RC1 tool-host
version mismatch remains retained; the candidate build itself passed.

The actual [three-process result](../artifacts/session-budget/meter-20261013/candidate-attempt1/results.json)
passed on the exact candidate above, using the matching layout under
`artifacts/session-budget/meter-build-20261013-attempt1/layout`. R2R and tiering
were enabled, global InterpMode and the collectible diagnostic switch were zero.
The [independent raw review](../artifacts/session-budget/meter-20261013/raw-review-20261013-attempt2/results.json)
verified 64 raw-file hashes, 20 frozen source-file hashes, 17 managed-output
hashes and seven runtime/host artifact hashes. It did not rerun the application.
The driver and fixture source used for these runs remain frozen in the raw folder.

The same layout independently passes the
[legacy policy matrix](../artifacts/session-budget/meter-selection-20261013-attempt1/results.json)
with twenty successful sessions/collections, refusal recovery and ordinary
native controls; the [production regression receipt](../artifacts/session-budget/meter-production-20261013-attempt1/evidence.json)
records lifecycle24/24, player15/15, three sample collections, one late-built
sample and source/import/source3/3 collections. Those production contexts use
the existing unmetered required-policy factory. Production fixture builds used
the recorded Preview6 SDK; the private runtime build used its own RC1 SDK.
Four [actual official loader runs](../artifacts/session-budget/meter-upstream-20261013-attempt1/results.json)
each return expected100 with unchanged generated guards/original assertions;
they use mode0/global collectible diagnostic1 and ordinary unmetered contexts,
so they do not exercise the new factory. The
[root evidence binding](../artifacts/session-budget/meter-root-review-20261013/results.json)
rechecks source/layout/product hashes, raw process exits, all complete production
PASS labels and official generated-source/log hashes without relaunching an app.
Native diagnostics sometimes interleave with Console output; a PASS label need
not start at a line boundary.

The [portable patch](../eng/runtime-patches/0005-native-session-instruction-meter.patch)
has SHA256 `5ecb5d595aba473c5709d8b172821ae7de228ee7705f140535df3b890ea7ec94`.
It passes apply-check against the unchanged session-policy parent; no patch
was applied to that parent or the canonical baseline. The separate
[source peer review](../artifacts/session-budget/eh-review-20261013/results.json)
records dispatcher/CAS/lifetime checks and the still-unimplemented terminal
EH/finalizer constraints. No production budget option was added.

| Actual process | Result |
| --- | --- |
| Metered | 20/20 normal sessions collected, plus limit-one, maximum-limit and two interleaved contexts; 24 retired-context guards, each rejects all three getters |
| Compatibility | Ordinary and required-unmetered both return all correct values and collect; six alive-unmetered and six retired getter rejections; actual ordinary author JIT and required-unmetered bytecode positive |
| Trusted-host concurrent | 20/20 normal sessions collected, same boundary/interleave controls, plus four joined callbacks; 25 retired guards; result 1998000 and final executed 60098 |

All forty normal-session rows have identical opcode deltas and exact business
values. Their per-session executed total is 12376 and remaining is 987624 from
limit 1000000. The raw reviewer recomputed executed as the sum of all exported
deltas and checked the remaining formula for each ordered session.

| Operation | Actual IR-dispatch increment |
| --- | ---: |
| Static constructor | 11 |
| Instance constructor | 21 |
| Two state getters and empty body | 17 |
| Loop(1000) | 12013 |
| Author to late private helper and return | 49 |
| Trusted callback to author/private helper and return | 35 |
| Trusted generic definition to author static body | 8 |
| Direct, virtual and delegate bodies | 59 |
| Exception filter, catch and finally | 45 |
| Final finite continuation | 118 |

The limit-one frame returned all the same values with executed 12376 while
remaining stayed zero; its final finite continuation also produced a positive
increment after exhaustion. The maximum-limit frame finished with executed
12376 and remaining 9223372036854763431. The interleaved contexts reported
left 524 and right 82. Native trusted RunFrame and TrustedCaller.Generic
compilation were observed; no author-definition native compilation was reported
in either metered process. Seventeen selected successful bytecode groups each
appeared at least twenty times.

The frozen host actually asserts owner isolation after each interleaved call and
the exact four-times warmed-call delta after joining every trusted task. The
exported log contains only the final interleaved and concurrent totals, not
their intermediate snapshots. The independent review binds those assertions to
the executed source and zero exit, but does not claim to reconstruct the omitted
intermediate counters. A later richer fixture receipt should export those fields.

Eight isolated in-memory negative controls were rejected: altered business value,
remaining formula, limit-one executed count, exported second-owner total, optional
leading-dot author JIT, removed bytecode target, altered concurrent total, and a
lost dispatch in the pure four-times arithmetic predicate. The last predicate uses
the actual normal-loop delta but is not another native concurrent invocation.
These controls leave every original raw file unchanged.

The first offline review incorrectly required compiler-generated QCall import
wrappers to be private. Its [failure receipt](../artifacts/session-budget/meter-20261013/raw-review-20261013/failure.json)
and original script/stderr remain intact; the corrected review verifies the exact
five private bridge declarations separately from generated wrappers. This was an
offline-review error, not a runtime or application failure. The original source
inventory also includes generated obj C# files; all twenty entries are hashed,
and those extra files are recorded as generated build evidence.

This acceptance is diagnostic desktop accounting and recovery after finite
execution. It is not terminal enforcement, a complete native-entry trace,
mobile computed-goto validation, a public stable runtime API or a performance
measurement. No physical-device or hostile-code claim follows from it.
