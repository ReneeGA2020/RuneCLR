# Private terminal finalizer boundary — Windows Checked

The same 099dacd candidate now also passes the nine recovery cases and six
original fatal-exception controls on a matching Windows Release build. The
[independent Release review](windows-release-budget-acceptance.md) checks queue
progress, actual definition owners, recovery, collection and exact ledgers.
Seven entered author finalizers have selected type6 observations; one inherited
trusted definition is native and one already-terminal body is suppressed.
Fatal controls have no per-method entry samples. The historical Checked
build/evidence below remain separate; no new finalizer policy is advertised.

On 2026-10-13, the matching Windows x64 Checked candidate passed nine finalizer
recovery cases and six ordinary-exception subprocess controls. The finalization
queue progressed twice after every accepted recovery, the target and both
collectible contexts collected, and the next independent session returned73
with fresh static state. Ordinary finalizer exceptions still terminated their
control processes with the original exception type. No accepted child timed out.

This is an opt-in runtime prototype. Production package policy still rejects
author finalizers; the later [host increment](host-instruction-budget.md) adds
explicit prototype-named options with separate acceptance evidence. It does
not establish a complete terminal capability, mobile enforcement or device support.

## Source and matching build

Candidate099dacd07d8d890822f7422f895337733457ab3c is in the independent
E:/runtime-finalizer-20261013 worktree, directly above the
[terminal prototype](runtime-session-terminal-prototype.md) at
7660f3069b3751b648f038bf7f3e9cfc6f96ff09. Official upstream base remains
0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de. This is a private RuneCLR
enforcement change, not an identified Microsoft defect. Earlier worktrees and
the installed runtime remain unchanged.

The [five-file portable patch](../eng/runtime-patches/0007-session-terminal-finalizer-boundary.patch)
has SHA256 c21c940db0f5041f3e681d4bafafbc555f51412f2c9a188c142981af27c468ef.
Applying it was checked against the unchanged terminal parent; it was not applied
to that parent or the canonical runtime.

The fresh build used private SDK11.0.100-rc.1.26420.103 and
clr.runtime+clr.jit+clr.hosts+clr.corelib+clr.tools+clr.nativecorelib, Checked x64,
with clrinterpreter. It completed in7m25 with zero warnings/errors. Actual
native compile commands/objects cover seven reviewed owners. The layout overlays
fresh matching runtime/CoreLib/compiler inputs on unchanged same-base framework
libraries/hosts:517 hashes were verified. This is not a shipping framework pack.

Four actual CoreLib PE stages retain the old policy5, meter8 and terminal12
private method families and their ABI. They retain three new private GC methods
and two new native imports without a hidden QCall exception-status argument.
Creation and scalar query imports retain their previously required hidden status.
The private GC discovery method returns boundary version1; the older terminal
prototype version1 remains unchanged. It does not advertise a complete budget.

## Runtime behavior

GC.RunFinalizers consults the actual finalizer-slot MethodDesc and its defining
module's binder. A collectible derived receiver can inherit a trusted finalizer;
that trusted definition is allowed to run even when the derived context is
terminal. The target stays rooted through the no-GC native query, with KeepAlive
after the existing finalizer-thread reset and accounting. No managed ALC object
or metadata escapes the query.

An already terminated author's finalizer body is skipped. An active author's
finalizer uses its existing cumulative session allowance. Exhaustion latches the
native terminal reason and reaches the trusted finalization boundary after CLR
unwinding; the boundary handles only a terminated finalizer definition owner.
Other exceptions continue through the original global-handler/fatal behavior.
The implementation does not classify termination by OperationCanceledException.

| Actual recovery case | Observation |
| --- | --- |
| Active loop | Exactly2048 cumulative author dispatches; reason1; returns to queue |
| Loop with finite finally/private helper/delegate | All finite cleanup effects occur; cleanup51, remaining4045 |
| Loop with infinite finally | Cleanup4096, remaining0, phase2; queue continues |
| Already terminal | Author finalizer never enters; existing ledger unchanged |
| Unload before finalization | Trusted strong root spans retirement; release triggers bounded finalizer and completed collection |
| Inherited trusted base | Actual trusted base finalizer runs natively; terminal author ledger unchanged |
| Author override, finite cleanup | Private cleanup and automatic trusted base finalizer execute |
| Author override, infinite cleanup | Cleanup4096 exhausted; implicit base-finalizer call is omitted |
| Finite author control | Author body completes; executed79, remaining1969; no terminal latch |

Every row separately proves two later trusted sentinel finalizers, next-session
value73/static reset, retired query rejection, and completed collection after
frames return. The unload-before-finalization case deliberately exports no
post-retirement native snapshot: getters reject a retired ALC. Its evidence is
the strong-root lifetime, real authored bytecode, side effects and recovery.
Private cleanup dependencies are preloaded before retirement.

Six independent fatal controls cover default trusted and ordinary collectible
OperationCanceledException/InvalidOperationException, a prototype author's
explicit cancellation before any terminal latch, and required-interpreter
unmetered cancellation. All exit-532462766 with their original unhandled type
and actual Finalize stack; a nonzero exit alone is insufficient. The180-second
watchdog always fails a case. Nonces, recorded PIDs, arguments and raw hashes
bind actual process outcomes; PID reuse is allowed across different lifetimes.

Cleanup exhaustion can truncate authored resource release and even a compiler's
implicit base-finalizer chain. This is measured behavior, not guaranteed cleanup.
Host-owned resources must use independent trusted ownership. Finalizable-object
storms, resurrection, failed-cctor finalization, concurrent terminal races, actual
IL fault clauses, tail calls, localloc, GC stress, locks and native-call deadlines
still need separate coverage.

## Evidence and reproduction

Use a new evidence directory with the exact matching private layout:

~~~powershell
./eng/verify-session-finalizer.ps1 -RuntimeRepo E:/runtime-finalizer-20261013 -RuntimeLayout E:/RuneCLR/artifacts/session-finalizer/build-20261013-attempt1/layout -CandidateCommit 099dacd07d8d890822f7422f895337733457ab3c -EvidenceDirectory artifacts/session-finalizer/probe-new
~~~

- [Build/native compilation](../artifacts/session-finalizer/build-20261013-attempt1/compile-evidence.json)
- [Matching layout](../artifacts/session-finalizer/build-20261013-attempt1/layout-receipt.json)
- [Four-stage metadata](../artifacts/session-finalizer/metadata-20261013-attempt2/results.json)
- [Actual15-lane finalizer acceptance](../artifacts/session-finalizer/probe-full-20261013-attempt1/results.json)
- [Independent raw audit](../artifacts/session-budget/finalizer-independent-audit-20261013/results.json)
- [Root source/build/regression binding](../artifacts/session-finalizer/root-review-20261013/results.json)

On this same candidate, the frozen original terminal driver passes44 lanes
(84 collected contexts), lifecycle24/24, controlled player15/15, legacy required
selection20/20 and four unchanged official loader tests return expected100.
Production/upstream controls remain unmetered. The old terminal driver reports
finalizersIntegrated=false because its fixture does not test finalizers; the
separate new15-lane result supplies that scoped evidence.

Local fixture failure and reviewer mistakes are preserved separately: the first
stock fatal target remained rooted on a JIT frame; the metadata reviewer initially
assumed a generated parameter name; the raw reviewer initially used a greedy
header expression. These are experiment-tool issues, not runtime defects.

The later [host budget increment](host-instruction-budget.md) implements explicit
binding, native scalar outcomes, safe exception reporting and skip-OnStop after
terminal state. Matching mobile builds, Release dispatch and physical-device acceptance
remain separate required experiments.
