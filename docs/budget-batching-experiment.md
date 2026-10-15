# Budget batching experiment

The user asked on 2026-10-14 whether checking or accounting every100/1000
instructions could improve RuneCLR's configured-budget ratio. It is a useful
experiment: the accepted terminal meter performs several shared atomic
operations per dispatched author opcode. The later opt-in interval candidate
is now implemented, with a successful matching Release build and actual
interpreter boundary/high-budget controls. See
[the implementation and actual runs](budget-interval-candidate.md).
The [real timing](budget-interval-performance.md) now measures arithmetic
2.53x Exact0 -> 1.26x/1.22x at100/1000, with smaller or negative gains in other
workloads. All are same-binary independent-counter controls, not the best
derived-ledger exact profile. Sixty processes and780 collections pass.
The [fresh best-exact comparison](budget-batch-best-exact.md) now closes that
control with48 processes/624 collections: arithmetic saves44%, entities
regress15-17%, and host-call gains are small. It preserves the default exact
profile and keeps batching an opt-in experiment.
The sections below retain the earlier proposal and measured precursor history;
those measurements do not supply batch100/batch1000 performance ratios.

## Current Evidence

The accepted Windows20405f7 candidate costs4.68x its own no-config callback
median in the [fixed arithmetic experiment](windows-budget-increment-performance.md).
Actual [PE/PDB inspection](windows-budget-increment-hotpath.md) verifies five
locked RMW operations on its normal, uncontended admitted path: two phase
reads, a remaining read, an admission CAS and an executed increment. Cleanup,
diagnostic saturation, contention and denial take different paths. The current
definition-owner lookup also runs on each charged dispatch.

The [stock Lua reference](lua-budget-overhead.md) measures6.37x/2.49x/2.44x
for native C hooks every1/100/1000 traced Lua instructions. Its non-atomic,
catchable per-state hook is not equivalent to RuneCLR terminal accounting.
Neither the Lua ratios nor Windows lock counts predict RuneCLR batch timing.

## Smaller Precursor

A later [source-only review](../artifacts/budget-batching/source-review-20261014-attempt1/source-review.json)
identifies the existing runtime VolatileLoad helper as a candidate replacement
for the phase scalar's zero-CAS read. This would retain every phase check and
both phase-changing CAS operations. The helper supplies acquire-load behavior
on ARM64 and the runtime's established volatile-load convention on x64.

An acquire load has weaker ordering than the current full RMW operation.
Alignment and atomicity alone do not establish equivalent behavior across
admission, snapshots, cleanup and exception handling. The review must check
whether any code relies on the removed fence, and acceptance still requires
actual emitted code plus terminal, finalizer and joined-worker regressions.
Binder lifetime remains a CLR ownership property; a phase read does not keep
the defining binder alive or close the existing phase/admission gap.

The precursor is now implemented as the isolated opt-in candidate a24661d,
directly based on20405f7, with a matching Windows x64 Release build.
[Actual PE/PDB review](windows-phase-load-hotpath.md) verifies three locked
operations on the enabled normal admitted path, versus five when disabled,
and three versus six on cleanup. The compiler emits out-of-line Phase calls
and additional stack accesses. [Functional ON/OFF acceptance](windows-phase-load-acceptance.md)
now passes, and a separate [four-process live witness](windows-phase-load-live-witness.md)
observes the actual phase0 hot-loop branches with normal return, exact exhaustion
and collection. Neither establishes ARM64 ordering equivalence. A later
[separate bracketed measurement](windows-phase-load-performance.md) passes
four raw audits and the joined32-process/416-collection review. Phase-load ON
uses25.36-26.04% less budgeted callback time than its two current parent
brackets; its configured/no-config ratio is4.07x. This is a single desktop
arithmetic kernel with unchanged per-opcode admission, not batching.
The accepted executed-increment change's earlier4.68x measurement and future
batch100/batch1000 results remain separate.

The [review's boundary analysis](../artifacts/budget-batching/source-review-20261014-attempt1/review.md)
also identifies a narrower batching step: keep remaining-allowance admission
on every opcode and aggregate only executed updates. With the old phase reads,
its conditional RMW count is 4+1/N, rather than the full-reservation design's
2+3/N model below. It still needs explicit pending-count flushes at every
owner/return/exception/native transition and a declared live snapshot contract.
Neither design has a built or measured batching candidate.

A subsequent [source-only derived-ledger review](../artifacts/budget-batching/derived-ledger-review-20261014-attempt1/review.md)
identifies another small alternative before introducing local batch state.
Terminal execution and cleanup only admit unit decrements, never reset/refund
their remaining allowances, and refuse zero admissions. Their admitted counts
can therefore be derived from immutable initial allowance minus an atomic
remaining read. This could remove the separate executed increment on each
admission without reservations or flushes. Diagnostic mode continues counting
after zero and must retain its independent saturating ledger.

The review binds13 source files and passes248 bounded interleaving states,
signed-limit algebra and nine source/algebra rejection controls. It is not
runtime or memory-ordering evidence. Derived counts include an admission at
its successful debit CAS, earlier than the current separate increment;
independent host getter calls still do not form a transactional snapshot.
Preserving initial allowances also requires either explicit mode-dependent
native slots or a larger matching binder layout. The later
[derived-ledger candidate](windows-derived-ledger-candidate.md) chooses two
appended immutable allowances and a64-byte meter. It is now committed and
passes41 native header cases/807 checks and a matching Windows x64 Release
build. Independent36-source/527-layout/five-PE-PDB review and all16 ON/OFF
functional commands pass. Static native review confirms two locked RMWs on
enabled admitted paths versus three disabled. Four actual normal-admission
branch witnesses pass with four collected contexts and24 rejected alterations.
The [new timing bracket](windows-derived-ledger-performance.md) passes with
ON configured callback time down8.1%/9.6% against the new parents and a3.60x
configured/no-config ratio. Per-opcode admission
and terminal phase checks stay intact. This supplies no100/1000 result or
promised ratio; the source-only review itself remains an earlier analysis.

## Separate The Changes

First test reducing shared counter updates while retaining prompt termination
checks. A design could reserve a small allowance and consume it locally, or
accumulate accounting between explicit synchronization boundaries. Both still
need to maintain the declared cumulative session budget and count actual
admitted dispatches rather than unconsumed reservations. The current meter
charges before dispatch; its executed ledger counts admitted interpreter
opcodes, including an admitted opcode that subsequently throws. It does not
count successfully completed operations or time spent in a native call.

For intuition only, if the three counter operations occurred once per batch
while the existing two phase reads remained per opcode, their average lock
frequency would be2+3/N:2.03 at100 and2.003 at1000, versus5 today. This is a
conditional operation-count model, not an emitted-code profile or throughput
estimate. Boundary flushes, final partial batches, owner changes, contention
and additional synchronization can increase the cost. It explains why simply
increasing a batch100 to1000 may have diminishing returns.
The model assumes full, uncontended normal-execution batches and an executed
counter update by the consumed batch amount. It does not model the cleanup
path's six locked operations, local counter instructions, owner resolution,
cache traffic or the relative latency of any instruction. In particular,
it supplies no calculation of a new4.68x ratio or a promised speedup.

Reservations need a separate conservation ledger. At a joined-worker snapshot,
unreserved allowance plus unused live reservations plus admitted dispatches
must equal the initial allowance; after unused reservations are returned, the
current remaining-plus-executed identity can hold again. Reservation admission
must not increment executed byN when fewer thanN dispatches were admitted.
Shared workers can exhaust the unreserved pool while another worker retains
unused credits. Latching terminal phase at that point would stop that worker
early and spend less than the declared allowance. A candidate needs an explicit
rule for transferring/returning credits and deciding true exhaustion, including
an idle or blocked credit holder; a smaller numeric upper bound alone does not
preserve current quota behavior. If terminal phase is latched, cached execution
credits cannot authorize further ordinary author dispatches or become cleanup
credits. Cleanup retains its own bounded allowance and phase checks.

Reducing termination checks is a separate semantic change. A naive debit or
check only everyN instructions can delay rejection and allow partial batches
to go unaccounted. An N-1 precision claim needs a concrete single-owner,
uninterrupted accounting model; it cannot be assumed for shared workers,
transitions, caught errors, cleanup or finalizers. Such a mode must stay an
explicit experimental profile until its actual bounds are tested.

## Acceptance Before Performance

Keep the accepted per-opcode products intact and use a separate switch-controlled
runtime worktree. Freeze exact source, compiler and managed inputs forN=1/100/1000.
Do not silently enable batching in the production prototype or change the
existing bridge acknowledgment to advertise unverified enforcement.

- Test zero, one, N-1, N and N+1 allowances and returns at partial batches.
- Charge nested calls, recursion, constructors and static constructors to the
  defining session; trusted host/framework work retains its declared ownership.
- Check tail calls, generic/shared method bodies, trusted calls that callback
  into authors, and return to a previous owner. Flush or transfer local state at
  the boundaries the chosen design declares; a caller's reservation must not
  pay for a different definition owner. Native/blocking work has no interpreter
  dispatch count and does not acquire a time limit from batching.
- Reconcile local/reserved units at return and ordinary/terminal unwinding;
  abandoned cached state must not retain a retired session.
- Preserve catch/filter suppression, bounded finite/infinite cleanup, finalizer
  handling and the next normal session after a terminated author.
- Repeat joined-worker controls, checking exact admitted execution and unused
  reservations separately; a depleted reservation pool alone is not evidence
  that all reserved instructions executed.
- Exercise partial batches before ordinary exceptions, filter/catch selection,
  finally/fault callbacks and finalizer-thread entry. Normal finally remains
  execution accounting; only the existing terminated-owner cleanup scope can
  use cleanup allowance. Reconcile unused credits on worker exit and frame
  retirement without retaining the defining collectible binder.

The accepted source already has a phase-read/admission gap and independent
nontransactional scalar snapshots; batching must not be described as fixing
either race. Joined-worker checks observe ledgers after all workers return.
They must compare both early-termination behavior and quota conservation, not
merely verify that an aggregate count did not exceed the configured limit.

Only passing candidates enter same-machine paired or bracketed measurements.
Use unchanged author IL/checksum, no-config and current per-opcode controls,
exact native ledgers and collected contexts. Shut down owned mobile emulators
and avoid other builds during CPU timing. Compare arithmetic, entity/table-like
work and frequent host-call boundaries: a single tight loop can overstate the
benefit of batches that flush at boundaries. Mobile measurement requires new
matching application products and actual method-entry evidence separately.
