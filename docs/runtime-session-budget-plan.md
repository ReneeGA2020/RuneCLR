# Session instruction budget — source-reviewed implementation plan

Reviewed on 2026-10-13. This records the source plan at its original
session-policy snapshot. Later implementation/evidence is separate: the
[diagnostic meter](runtime-session-meter.md) and
[Windows terminal prototype](runtime-session-terminal-prototype.md) now have
matching builds and scoped execution results. They do not complete this plan's
production/mobile acceptance. The later
[finalizer boundary](runtime-session-finalizer-boundary.md) supplies scoped
Windows recovery and ordinary-fatal-exception controls; remaining lifecycle
topologies are not yet complete. The later
[host prototype](host-instruction-budget.md) exposes explicit budget options
with matching Windows recovery results; query/allocation fault injection and
mobile acceptance remain open. Existing
[required-session selection](session-execution-policy.md) and
[Android Release fixture acceptance](android-session-policy-entry.md) establish
execution selection and recovery, not instruction limits. The current
OperationBudgetPerCallback charges cooperative host API work and cannot stop an
author loop that never calls an API.

The next concrete goal is a creation-time, per-session interpreter budget that
returns control to the trusted host after an ordinary author loop, including a
loop that catches the first quota exception. Run-time ownership, EH cleanup and
finalizers are part of that goal. Wall-clock deadlines, arbitrary native-call
interruption and allocation limits are separate work.

Scheduled product direction, not implemented: issue 16. It narrows the UGC anti-freeze goal to a coarse per-callback interpreter deadline. That is not a cumulative instruction total and not an API call count. Exact milliseconds are not required, so this is not a precise wall-clock contract. The host decides how to treat a cutoff. Trusted code stays unlimited. Arbitrary native-call interruption and allocation limits remain separate. The prototype measurements in this plan remain evidence.

## Inspected source and actual anchors

The inspected local worktree is E:/runtime-selection-20261013, tracked-clean on
runeclr/session-policy at5972a86966e56ae5f468a3e042327f0051e923d5, derived from
official base0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de. The mobile combined
candidate1724cdec553a7aff7a373a271a4be612651c7625 is a different snapshot; any
mobile port must recheck anchors and rebuild matching native/CoreLib inputs.
The [source receipt](../artifacts/session-budget/source-plan-fbb9a2b5cd024738aa4d227c5af3123a/source.json)
records hashes and exact matching lines for13 source/build-document files.
No source-applicable runtime AGENTS.md was present; eng/common/AGENTS.md applies
to a different directory. The checked-out CoreCLR build guide was read.

| Source, relative to the separate runtime | Actual anchor | Implication |
| --- | --- | --- |
| src/coreclr/vm/method.cpp:1621 | HasRequiredInterpreterPolicy | Use defining module/binder ownership, not the loader allocator of a closed trusted generic. |
| src/coreclr/vm/assemblybinder.h:37 | RuneCLRRequiresInterpreter | The existing immutable native policy is available before author loading. |
| src/coreclr/binder/customassemblybinder.cpp:214,255 | Context release | Managed unload releases handles; the native binder survives until allocator deletion. |
| src/coreclr/vm/loaderallocator.cpp:1773,1787 | Allocator destructor/RegisterBinder | The collectible allocator ultimately deletes its registered custom binder. |
| src/coreclr/vm/interpexec.h:40,51,101 | ReInit/thread context/ExceptionClauseArgs | Frame ownership is reusable; EH currently distinguishes filters, not every cleanup kind. |
| src/coreclr/vm/interpexec.cpp:892,904,1455,1525 | InterpThrow/dispatch/main loop | Publish the current IP before throwing; account at actual opcode dispatch. |
| src/coreclr/vm/interpexec.cpp:3581,3688,4948,4998 | Child creation/return/resume | Refresh cached owner/mode after ordinary calls, delegate calls, tail calls, returns and EH resume. |
| src/coreclr/vm/interpexec.cpp:4558 | INTOP_CALL_FINALLY | Normal control flow can enter finally without a new native funclet call. |
| src/coreclr/vm/eetwain.cpp:1879 | CallInterpreterFuncletWorker | EH reenters the interpreter for filters, catches and cleanup. |
| src/coreclr/vm/exceptionhandling.cpp:3447 | EHEnumNextWorker | Native enumeration maintains clause identities and catch-type resolution. |
| src/coreclr/nativeaot/Runtime.Base/src/System/Runtime/ExceptionHandling.cs:1022,1244 | First-pass handler search/second-pass cleanup | This file is compiled into CoreCLR CoreLib too, via System.Private.CoreLib.csproj:217. |
| src/coreclr/System.Private.CoreLib/src/System/GC.CoreCLR.cs:342 | RunFinalizers | The current loop catches only exceptions accepted by the global handler. An unhandled budget exception is unsafe here. |

The Release, non-Windows/non-WASM computed-goto path dispatches directly through
INTOP_DISPATCH. A check only at the while-loop header misses most execution.
The Windows switch path also has direct dispatch for debugger bypass. Branch
or method-entry checks alone miss straight-line work and runtime-generated
callback/private-helper paths. One charge means one interpreter opcode dispatch,
not one32-bit operand slot, one C# statement or one host API operation. This unit
is runtime-version-dependent and is not a deterministic cross-platform metric.

## State ownership and opt-in bridge

Give the required collectible custom binder a native scalar BudgetState. Its
lifetime belongs to the registered collectible allocator's binder deletion,
not to a process registry or a managed exception/delegate. Embedding it in that
binder avoids looking through GetLoaderAllocator after ReleaseLoadContext has
cleared its allocator pointer. Retiring the managed ALC must not free state
while native method/frame/finalization ownership still requires it.

State contains immutable execution/cleanup limits, saturating remaining counts,
an irreversible terminal reason and phase, and bounded diagnostic counters.
It retains no managed objects or reflection metadata. Use a monotonically
increasing state model:

~~~text
Active -> Terminating (author catch/filter disabled; bounded unwind cleanup)
       -> NoAuthorExecution (cleanup reserve exhausted or cleanup complete)
       -> native state destruction with the allocator
~~~

Instruction exhaustion or an explicit trusted stop request latches the reason
before allocating/throwing a managed exception. There is no reset, quota refill
or return to Active. Saturating subtraction must not underflow into a fresh
large quota. Any supported concurrent execution, including a finalizer, must
share the same ledger; a thread-local fresh quota would be a bypass. Start with
correct atomic accounting and measure its cost before introducing batching.

Keep the accepted version1 execution-policy API intact. Add a separately
versioned, exact-signature private budget factory accepting name, the existing
managed resolver, execution units and cleanup units. A host-created snapshot
query returns only scalar remaining/reason/count data, guarded by the existing
unload lock, VerifyIsAlive and KeepAlive pattern. All reflection-only bridge
roots must survive actual CoreLib trimming. If host-requested stop is included,
its only mutation is an irreversible latch; it cannot reactivate a context.

RuneCLR supplies a nullable host InstructionBudgetPerSession option alongside
the cooperative API budget. A positive budget requires RequireInterpreter and
native budget capability acknowledgement before assembly/type loading; stock or
incompatible runtimes fail before author construction. The package cannot select
or increase it. First implementation uses a cumulative session quota rather than
resetting fuel at every callback. Private reflection visibility still does not
make the broader runtime an author-resistant sandbox.

## Minimal runtime change that could establish terminal behavior

1. Add native budget state and creation/query QCalls to the existing required
   context path. Keep ordinary contexts and unbudgeted required contexts on a
   null-budget fast path. Validate limits before publication; record capability
   and native scalar acknowledgement before any author type initializer.
2. Add a common opcode-dispatch charge for switch and computed-goto builds.
   Cache the defining binder's budget for the currently executing method, and
   refresh it wherever pMethod/pFrame changes. Save pFrame->ip before the slow
   throw path, inside the installed managed exception/unwind handlers. Do not
   introduce an allocating check in EXIT_FRAME's explicitly GC-free region.
3. Add a frame-owner terminal predicate to the first-pass EH handler search.
   A terminated owner cannot select its catches or execute its filters. Recheck
   after a filter: exhaustion inside that filter may be swallowed by CLR's
   normal filter semantics, but must still stop subsequent author execution.
   Preserve EH clause indices and collided-unwind/rethrow positions; simply
   removing clauses from enumeration can change the indices used by the shared
   CoreLib EH algorithm. A CoreCLR-only native frame-iterator query used by the
   shared first-pass loop is a candidate; its ABI/GC contracts need review.
4. Mark second-pass finally/fault execution with an explicit cleanup mode using
   the actual clause kind. ExceptionClauseArgs.isFilter=false alone conflates
   catches and finally. Normal INTOP_CALL_FINALLY continues charging execution
   fuel until termination. EH cleanup after termination consumes a separate,
   finite reserve shared by all author helpers/delegates in that cleanup.
5. On cleanup-reserve exhaustion, latch NoAuthorExecution. The existing EH
   mechanism must unwind out of the current funclet and omit remaining author
   funclets without resetting the reserve. Trusted CLR/host cleanup still runs.
   Preserve interpreter frame-pop, stack-pointer, GC-root and shadow-stack
   bookkeeping. This is a source hypothesis to prove with collided-unwind tests,
   not a claim that throwing inside finally is already safe in every topology.
6. Integrate author finalizers with the trusted finalization dispatcher. Resolve
   the finalizer's defining owner, not the finalizer thread's preceding session.
   An active author's finalizer charges the same session ledger. A terminal
   owner's later finalizers cannot execute fresh author code. Handle only the
   specifically acknowledged budget termination at this dispatcher so it does
   not escape as an unhandled exception and terminate the process. Preserve
   queue progress and existing ordinary-exception behavior; do not install a
   process-wide handler that swallows unrelated finalizer failures.

These are the smallest coherent areas for a terminal candidate. An early patch
that only counts/throws can be tested as accounting instrumentation, but must
not expose a terminal capability bit before handler suppression, bounded cleanup
and finalizer recovery pass. No Thread.Abort substitution, arbitrary longjmp,
raw stack reset or process-kill success is part of this design.

## Host, native calls and lifecycle behavior

The interpreter call opcode is charged before leaving author code. Trusted JIT/
R2R/framework/native work remains outside instruction accounting. Carry only
native owner/mode information through trusted call transitions so reentrant
author callbacks use the same session state. On return, recheck terminal state
before the next author opcode. Two nested sessions keep distinct ledgers; a
trusted generic instantiated with an author type stays classified by definition.

A blocking/native call or a long trusted framework operation cannot be stopped
by an interpreter instruction budget while it has control. Returning or
reentering author code is guarded; elapsed time inside that operation is not.
Host API restrictions, weighted API charges and cancellable native operations
remain RuneCLR responsibilities. Shared GC, allocations/OOM, process memory and
script-created threads/tasks are not isolated by this feature.

MapRunner must obtain the native budget before Activator.CreateInstance, so both
entry/private constructors and static constructors are covered. After catching
any exception it queries the latched native reason before Unload and copies only
trusted scalar/string diagnostics. Do not call a terminated author's virtual
Exception.Message override to construct a report. Constructor failures may wrap
the signal in TypeInitializationException; the native latch, not exception text,
is authoritative.

For this first candidate, skip author OnStop after terminal exhaustion instead
of granting it a fresh quota. An ordinary failure with an active budget still
attempts OnStop, which remains budgeted and can itself exhaust. RuneCLR's trusted
MapContext.Dispose/resource release and ALC retirement always run. Finite author
EH finally blocks get the reserved cleanup window; a separate, explicit bounded
OnStop cleanup permission can be considered later without clearing termination.

Abandoning an author cleanup block can leave author-managed resources or locks
unreleased. Preserving CLR GC/unwind invariants does not reverse arbitrary map
side effects or release every shared monitor. The prototype's handle-based host
resource ownership makes trusted host cleanup independent of author code; it
does not establish recovery from arbitrary shared-framework locks/native state.
Document and test this boundary rather than treating all finally truncation as
semantically harmless.

## Matching desktop acceptance to implement next

Use a fresh runtime worktree/commit and matching Windows x64 Checked CoreLib/
native/compiler layout. Run with InterpMode=0 and global collectible diagnostic0.
Keep author bytecode-positive/native-JIT-negative proof and trusted JIT-positive
controls. A test-harness watchdog detects hangs, preserves logs and fails the
case; killing a hung child is not a passing termination result.

| Regression | Required observable result |
| --- | --- |
| Tight loop with no API calls; straight-line/recursive private work | Exact native quota exhaustion, managed return to host, bounded no-underflow counter. |
| Constructor and private/generic cctor loops | Budget applies before first lifecycle callback; wrapped initialization failure still reports the latched reason. |
| Catch quota and loop; catch-and-return; nested catches | No author handler/next gameplay opcode after termination; host reports failure even if trusted code catches a signal. |
| Infinite/throwing filters and exhaustion during a normal exception filter | No lost latch or new handler continuation; filter failure does not erase the terminal outcome. |
| Nested finite finally/fault plus helpers and delegates | Reserved cleanup is charged, finite cleanup completes, original EH ordering stays coherent. |
| Loop/catch inside finally; cleanup throws an ordinary exception | Reserve remains finite, further author cleanup is not restarted, safe host unwinding and next-session recovery. |
| Trusted native callback reentering author; both child-call dispatch paths; tail call | One ledger is restored correctly across transitions; no preparation hook substituted for executed-opcode evidence. |
| Active and retired author finalizers, failed cctor finalization, unrelated ordinary finalizer failure | Correct owner and limited fuel, finalization queue progresses, no unrelated global exception swallowing. |
| Ordinary OnStop loop; terminal session OnStop | Active OnStop can exhaust; terminal OnStop is skipped; trusted resource stores still release everything. |
| Two interleaved contexts, nested trusted calls and20 consecutive bad/good sessions | Separate quotas/reasons, no cached-owner address reuse, all eligible contexts eventually collect after frames return. |
| Counter boundary1, large64-bit limit, cancelled/retired query, invalid options and stock runtime | Saturation/immutable acknowledgement, existing retired-query guard, fail-before-author-load behavior. |

Use actual executing IL fixtures, native opcode accounting and business side
effects to assert these outcomes, rather than tests that merely mirror the
state-machine implementation. Run relevant upstream interpreter/loader/EH tests,
then the current24-case RuneCLR lifecycle and15-case player suite on the same
patched runtime. Ordinary stock behavior and existing immutable policy/refusal
controls must remain unchanged. Observe unloading after the non-inlined run frame
returns; diagnostic forced GC is not a per-frame execution policy.

## Mobile and performance follow-up

Only after matching desktop EH/finalizer acceptance, port onto the combined mobile
source and rebuild matching CoreLib, native runtime and symbol inputs. iOS ARM64
and Android x64/ARM64 Release exercise computed-goto dispatch, native interpreter
entry/cctor/private-helper execution, quota/catch/finally recovery and repeated
retirement. Debug-only dumps are not Release proof; use exact matching native
samples plus separate normal functional runs. Keep emulator/simulator, physical
device and production package matrices distinct.

Measure Release budget-disabled, budget-enabled non-exhausting, and exhaustion/
cleanup costs separately. Reuse the existing warmed arithmetic/object/host-call
kernels and fresh-session retention experiments, with native/trusted control
lanes. Report time per executed IR opcode, relative throughput, cold-session
cost, atomic/concurrent cost and terminal unwind latency. Compare dispatch
strategies and both architectures before choosing batching; any optimization
must retain a stated maximum overshoot bound and the same terminal regressions.
No instruction-count result should be presented as a native-call deadline,
allocation sandbox or universal game frame-time guarantee.
