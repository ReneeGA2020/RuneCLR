# Host instruction-budget prototype

The later [host-pumped lifecycle](host-pumped-sessions.md) now preserves this
same cumulative budget across separate host frame calls. Its explicit `-Pumped`
Windows Release suite passes 16 cases/74 collections, alongside the synchronous
15/73 control. Advancing a frame does not refill the native allowance.

The cumulative allowance above is measured prototype evidence. The scheduled UGC product limit is different and is not implemented. Issue 16 tracks a coarse per-callback interpreter deadline for untrusted code only. It does not limit trusted code, and it does not turn host API quotas into the anti-freeze mechanism.

On 2026-10-13, MapRunner's explicit prototype budget passed fifteen Windows x64
Checked subprocess cases, including twenty failure/good-session pairs. All
seventy-three actual contexts collected after Run returned, and all host-owned
entities were released. Ordinary SDK and older partial-runtime controls reject
unsupported budget requests before the runner reads the author entry file.

The later matching Windows 099dacd Release build passes the same fifteen cases
and 73 collections, with unchanged authored IL, exact scalar outcomes and host
resource cleanup. The [independent Release acceptance](windows-release-budget-acceptance.md)
binds the source/build/layout and rejects altered receipts. Its fifteen trusted
MapRunner native observations do not supply individual author-method entry
samples. The separate [production regression](windows-release-production.md)
passes 24/24 lifecycle and 15/15 player on that Release layout; controlled
[joined-worker coverage](windows-terminal-concurrency.md) is a distinct runtime
experiment, not a new MapRunner scheduling API.

The implementation is in RuneCLR's host; no runtime source changed in this
increment. It uses the matching private
[terminal/finalizer candidate](runtime-session-finalizer-boundary.md)
099dacd07d8d890822f7422f895337733457ab3c and official upstream base
0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de. The host remains a dirty development
checkout: evidence binds exact source/configuration and compiled file hashes,
not a presumed clean host commit.

## Opt in explicitly

~~~csharp
var result = new MapRunner().Run(package, new MapRunOptions
{
    ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
    PrototypeInstructionBudget = 100_000,
    PrototypeCleanupInstructionBudget = 4_096
});
var budget = result.Report.PrototypeBudget;
~~~

PrototypeInstructionBudget defaults to null. Both configured quotas must be
positive Int64 values, and enabling the execution budget requires
RequireInterpreter. The cleanup quota defaults to4096. Invalid values are
rejected before runtime binding or author-file access. Default and unbudgeted
required-interpreter sessions continue to return a null PrototypeBudget.

The execution allowance is cumulative for one session: constructor/cctor,
OnStart, all OnTick calls and an allowed OnStop share it, including private
helpers and callbacks attributed to that native definition owner. It counts
interpreter IR dispatches, not C# lines, milliseconds or host API charges.
OperationBudgetPerCallback remains a separate cooperative host API quota.

Before creating the resolver, the host binds exact private trusted CoreLib
signatures for policy version1, terminal-prototype version1 and GC finalizer
boundary version1. Native context creation must acknowledge required policy
and all eight initial budget scalars before loading an author assembly. There
is no fallback to an unbudgeted or JIT context when this binding fails.

After callbacks return, the host checks the native terminal latch before counting
a completed tick. A terminal session skips OnStop. An ordinary author error
with no native terminal latch still permits budgeted OnStop, which can itself
exhaust the allowance. Host resource cleanup runs independently of author code.
All actions after successful context creation, including ticket/context
allocation and native-query failures, are enclosed by the unload path.

For every budget-path error, the host uses the native latch or a bounded
nonvirtual exception type name. It never invokes author Message, ToString or
Data to produce the report, even before the quota is exhausted. Explicit
OperationCanceledException is an ordinary error unless the native latch says
otherwise. The unbudgeted error-reporting behavior is unchanged.

## Scalar results and measured behavior

PrototypeBudgetSnapshot contains ExecutionRemaining, ExecutionExecuted,
ExecutionExhausted, IsTerminated, Reason, Phase, CleanupRemaining and
CleanupExecuted. It contains no author object, exception, Type, Assembly,
delegate or ALC. Values are copied before Unload; separate native reads are
not an atomic concurrent snapshot. Remaining zero/ExecutionExhausted alone
does not establish termination: the persistent native latch and Reason do.

| Actual case | Result |
| --- | --- |
| Normal, twenty fresh sessions | Each completes three ticks, static state1, native execution96, no termination |
| Endless tick or OnStart | Execution8192, reason1, zero completed ticks, OnStop skipped |
| Typed/broad catch and signal filter | No catch/filter/resume side effects after termination |
| Exhaustion inside an ordinary filter | Filter enters first, then cannot return or enter fallback catch |
| Constructor/cctor loop | Execution8192; no lifecycle callback or entity creation |
| Finite finally/private helper/delegate | All finite cleanup effects occur; cleanup38, remaining4058 |
| Infinite private cleanup | Cleanup4096, phase2; host regains control |
| OnStop loop | Three genuinely returned ticks retained; stop begins, then execution8192/reason1 |
| Exception with infinite Message getter | Getter never compiles/executes; safe type-name error, native reason0; OnStop runs |
| Explicit cancellation before exhaustion | Ordinary type-name error, native reason0; OnStop runs |
| Twenty bad/good pairs | Forty ordered reports; every fresh good session completes, resets statics and collects |

All seventy-three reports prove zero remaining entities and completed context
collection after the execution frame returns. Actual successful author bytecode
and trusted MapRunner native compilation are positive controls; no author
namespace JIT compilation is reported with global interpretation and the
collectible diagnostic switch both disabled. These are diagnostic body/counter
results, not exhaustive native entry samples.

The original lifecycle24/24 and player15/15 also pass on the same private
runtime with the new host and no instruction budget. The ordinary SDK's full
verification passes lifecycle24/24, packaging84/84 and player15/15 with zero
build warnings/errors. Invalid-budget precedence and unbudgeted-null-report
checks were added to existing lifecycle cases. Existing samples and late/source
package collections pass.

## Reproduce and evidence

~~~powershell
./eng/verify-host-budget.ps1 -RuntimeRepo E:/runtime-finalizer-20261013 -RuntimeLayout E:/RuneCLR/artifacts/session-finalizer/build-20261013-attempt1/layout -CandidateCommit 099dacd07d8d890822f7422f895337733457ab3c -EvidenceDirectory artifacts/host-budget/probe-new
~~~

Use a fresh evidence directory. The driver records fixed source/configuration,
managed/runtime hashes, real PIDs, argument vectors, nonces and raw streams.
An owned180-second timeout always fails; no accepted child was killed.

- [Host source review](../artifacts/session-budget/host-integration-source-review-20261013/source-review.json)
- [Driver source review](../artifacts/session-budget/host-driver-source-review-20261013/source-review.json)
- [Actual fifteen-case result](../artifacts/host-budget/probe-full-20261013-attempt1/results.json)
- [Stock finite/refusal result](../artifacts/host-budget/fixture-stock-20261013-attempt1/results.json)
- [Older terminal-only runtime refusal](../artifacts/host-budget/older-boundary-refusal-20261013-attempt1/results.json)
- [Full stock verification](../artifacts/host-budget/stock-20261013-attempt1/result.json)
- [Matching unbudgeted production verification](../artifacts/host-budget/production-20261013-attempt1/evidence.json)
- [Independent raw audit and twenty rejected corruption controls](../artifacts/session-budget/host-budget-independent-audit-20261013/final-binding.json)
- [Root source/build/result binding](../artifacts/host-budget/root-review-20261013/results.json)

An offline refusal reviewer variable mistake and the root reviewer's assumption
that a binding manifest had a passed field are preserved with their corrections.
They were read-only tool failures; no application rerun, original evidence change
or runtime defect was involved.

## Remaining acceptance

The public option deliberately remains prototype-named. Runtime-query failure
and post-create host-allocation failure cleanup were source-reviewed, not fault
injected. The fixture uses fixed trusted raw IL; production gameplay intake
still rejects authored finalizers. This does not add finalizer support to the
package capability profile.

Cleanup truncation can omit author resource release. Shared locks, blocking
framework/native calls, concurrency, finalizable-object storms/resurrection,
actual IL fault clauses, tail calls, localloc and GC stress remain distinct
boundaries. There is no native-call wall-clock deadline or memory isolation.

The next [matching mobile build increment](mobile-instruction-budget-builds.md)
combines this terminal/finalizer source with CID v2. Fresh iOS simulator ARM64
and Android x64 Release builds, retained CoreLib metadata and actual computed-
goto charging compilation pass. Android's original observer failure and a
separate passing assessment of unchanged products are both retained.
A fixed fifteen-case adapter also passes73
collections in one desktop process. The later
[actual mobile budget increment](mobile-host-budget-acceptance.md) now passes
15 scenarios/73 collections in an iOS simulator application and generates a
fresh Android framework/layout. A second actual iOS run also passes strict
installed-before/after sampling. Android APK execution now also has a strict
15-case/73-context emulator audit with dual-stream and inventory binding.
The separate iOS debugger lane now passes 147 entry samples for nine requested
author method groups. The later [Android budget entry run](android-budget-entry-acceptance.md)
also passes nine requested groups with178 samples and independent reviews.
Both traces are sampled scope. Mobile overhead and physical-device
acceptance remain next. Earlier mobile session-policy traces supply their own
execution-selection evidence only.
The later [Windows Checked cost experiment](budget-overhead.md) measures
configured-meter increments with the same interpreted author IL and native
ledger checks. It does not measure instrumentation-off, Release or mobile
cost. Subsequent matching Release runs now pass with a4.80x second-run
configured-meter ratio for the arithmetic fixture. The later
[Release terminal/finalizer acceptance](windows-release-budget-acceptance.md)
now passes; representative game/mobile performance gates remain open.
