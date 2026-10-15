# Private terminal execution prototype — Windows Checked

The later matching 099dacd Windows Release candidate now passes 44 lanes/84 rows
with [independent raw/source/build/PE review](windows-release-budget-acceptance.md).
Its 70 interpreted and 14 ordinary native observations are selected entries after
actual invocations, not a complete trace. The later [joined-worker baseline](windows-terminal-concurrency.md)
adds 36 processes/72 collections, exact shared execution/cleanup quotas and
single-worker count controls. The historical 7660 Checked experiment below
retains its original candidate and evidence; broader EH/race/device guarantees
remain unestablished.

On 2026-10-13, the matching Windows x64 Checked prototype passed forty-four
standalone subprocess lanes: fourteen ordinary controls, fourteen diagnostic
meter controls and sixteen terminal cases. All eighty-four contexts collected
after their execution frames returned: twenty-eight controls and fifty-six
terminal-session outcomes. No watchdog killed an accepted child. This establishes
the tested synchronous prototype, not a complete terminal-budget guarantee.
Author finalizers are not integrated in this7660 candidate; the separate later
[finalizer boundary](runtime-session-finalizer-boundary.md) records099dacd
implementation and matching execution evidence.

The candidate is `7660f3069b3751b648f038bf7f3e9cfc6f96ff09` in the separate
`E:/runtime-terminal-20261013` worktree, based on the verified diagnostic meter
`b8e5b0b4b7db30385265f935c00a39a3ba507aea` and official upstream base
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. The candidate is a private
RuneCLR runtime change. Its [portable patch](../eng/runtime-patches/0006-session-terminal-prototype.patch)
was checked against the unchanged meter parent; this is not an upstream fix.

## Matching inputs and actual evidence

- [Build result](../artifacts/session-terminal/build-20261013-attempt1/build-result.json),
  [source hashes](../artifacts/session-terminal/build-20261013-attempt1/source-hashes.json)
  and [matching layout](../artifacts/session-terminal/build-20261013-attempt1/layout-receipt.json).
- [Actual CoreLib metadata](../artifacts/session-terminal/metadata-20261013-attempt1/results.json):
  original five policy methods, eight meter methods and twelve terminal methods
  survive the inspected stages; the nested factory and native imports are retained.
- [Full process matrix](../artifacts/session-terminal/probe-full-20261013-attempt1/results.json),
  using the [fixed fixture](../eng/session-terminal-probe/Host/Program.cs) and
  [driver](../eng/verify-session-terminal.ps1).
- [Independent raw review](../artifacts/session-terminal/raw-review-20261013-attempt1/results-final.json):
  341 raw-file hashes, eight fixed source hashes, seventeen managed-output hashes,
  seven runtime/host identities, forty-four owned launches and exact scalar outcomes.
- [Root's independent review](../artifacts/session-terminal/root-review-20261013/results.json)
  additionally binds sixteen runtime source files, 517 layout files, actual native
  compilation owners and the separate production/legacy/upstream compatibility runs.

All processes used global InterpMode=0 and the collectible diagnostic switch zero,
with ReadyToRun and tiering enabled. The metered and terminal paths require native
policy acknowledgement before author loading. Successful author Spin/SafeValue
bytecode was checked by case, including twenty of each in the recovery process;
reported author-definition JIT compilation was absent. Trusted host native
compilation was positive. These checks are not a native method-entry trace.

## Observable behavior

The private factory `RuneCLR_CreateTerminalPrototype(name, resolver,
executionLimit, cleanupLimit)` creates a collectible interpreter-required context.
Its version is one; the fixture reads native termination/reason/phase and both
execution and cleanup counters. Each allowed opcode dispatch consumes one unit.
With execution limit 2048, the next dispatch refuses execution and latches reason1.
Executed remains 2048 and remaining zero. Counts measure this runtime's IR dispatch,
including interpreter debug opcodes; they do not measure C# statements or time.

The initial signal is OperationCanceledException, but trusted reporting uses the
native latch. Exhaustion inside an ordinary-exception filter can leave the original
InvalidOperationException; throwing cleanup can replace the exception too.
Activator reports TargetInvocationException for constructor/static-constructor
failures. The fixture retains only exception type strings, not authored exceptions,
delegates, reflection objects or messages.

| Terminal case | Actual assertion |
| --- | --- |
| Tight loop | Returns to the trusted host with executed2048, remaining0, reason1 |
| Typed catch, broad catch, catch-and-return | Authored catch0 and post0; no catch-and-return success |
| Filter on the terminal signal | Filter entered0, returned0 and catch0 |
| Exhaustion inside an ordinary-exception filter | Entered1, returned0, later catches/post0; native latch remains reason1 |
| Finite finally | Finally/helper/delegate each1; cleanup executed41, remaining4055, phase1 |
| Nested finally | Inner/outer each1; private helper/delegate each2; cleanup72, remaining4024 |
| Infinite finally | Inner1, outer0; cleanup exactly4096, remaining0, phase2; trusted host regains control |
| Throwing finally | Throwing cleanup1 and outer1; cleanup16, remaining4080; replacement exception does not reset reason1 |
| Constructor and static constructor | Before1, after0; lifecycle body never entered |
| Trusted callback catches and reenters | Trusted catch1 and reentry attempt1; authored reentry success0 and body side effects0 |
| Two live contexts | Six exported snapshots prove the failed context never charges the idle good context and the later good call never reactivates the failed context |
| Twenty bad/good pairs | Forty ordered scalar outcomes, all forty contexts collected; every fresh good context returns73 with static state1 |

The good context uses limit1000000 and executes53 dispatches, leaving999947.
Ordinary controls demonstrate real matching catches/filters and normal finally
behavior. Diagnostic-meter controls demonstrate finite execution continuing after
remaining reaches zero. Alive nonterminal contexts reject all five terminal
queries; every retired context rejects all eight terminal/meter getters.

Cleanup limit4096 is shared by the tested finally bodies and their private helpers
and delegates. A completed bounded cleanup retains phase1; phase2 means its reserve
was exhausted. Exhaustion deliberately truncates authored cleanup: outer finally
side effects and author-owned resource cleanup are not guaranteed. Trusted host
cleanup remains responsible for host-owned resources.

## Reproduce, verification scope and gaps

Use a new evidence directory and the exact matching private runtime:

~~~powershell
./eng/verify-session-terminal.ps1 -RuntimeRepo E:/runtime-terminal-20261013 -RuntimeLayout E:/RuneCLR/artifacts/session-terminal/build-20261013-attempt1/layout -CandidateCommit 7660f3069b3751b648f038bf7f3e9cfc6f96ff09 -EvidenceDirectory artifacts/session-terminal/probe-new
~~~

Each case is a separate process with a fresh nonce, saved PID/argument vector,
settings and raw stream hashes. PID alone is not a unique lifetime identity:
Windows reused one PID across sequential launches. Nonce, process receipt and
owned completion bind each run. The 180-second watchdog is a failure mechanism;
all actual accepted children exited zero before it fired. The kill branch was
source-reviewed, not exercised as an accepted terminal case.

Fourteen isolated, in-memory negative controls modified copies of actual receipts
or logs and were rejected, including catch/filter escape, incorrect counters,
cleanup reset, cross-context charging, author JIT, missing bytecode, wrong nonce
and a watchdog timeout. No application was rerun and no original evidence changed.
The root's first offline review mistakenly required all sequential PIDs to be
different; its [failure receipt](../artifacts/session-terminal/root-review-20261013/first-review-failure.json)
remains intact. Correcting that reviewer did not change the runtime or replay tests.

The native implementation distinguishes finally/fault clauses, but this C# fixture
tests finally only; an actual IL fault-clause test remains outstanding. Tail calls,
localloc, GC stress, shared locks, concurrent terminal execution and interruption
of blocking framework/native calls are unmeasured. A trusted native operation can
hold control beyond the interpreter's instruction quota.

The [finalizer integration design](../artifacts/session-budget/finalizer-design-20261013/design.json)
is preparation, not implementation or execution evidence for this7660 candidate.
The later [finalizer increment](runtime-session-finalizer-boundary.md) measures
its scoped queue/ownership/fatal controls. Until the remaining lifecycle
boundaries are tested, the private API remains explicitly a
prototype. It does not establish hostile-code isolation, physical-device support,
mobile Release computed-goto behavior or a production-supported execution budget.
