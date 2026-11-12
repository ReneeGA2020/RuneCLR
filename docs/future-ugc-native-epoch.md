# Future direction: controlled-build UGC with a dedicated runtime epoch

Recorded 2026-11-12 from an explicit user request. This is a **future exploration direction**, not an
implementation, a security or performance acceptance, or a change to the current UGC policy. The current
interpreter-only restricted profile and its terminal-latch semantics stay as they are; nothing here is
scheduled.

## Motivation

The interpreter keeps UGC predictable, but the measured gap to JIT on numeric workloads is real. If a game
needs more throughput later, a controlled native route may be worth exploring - provided the trust model
stays the same: authors submit build inputs, never executable machine code.

## Mechanism under consideration

- Authors submit source or IL. The provider reviews it, freezes the dependency set and runs a controlled
  build that produces the final package.
- On platforms that allow it, the dedicated runtime produces JIT code; ReadyToRun code is produced by a
  matching controlled compiler. Native paths that cannot carry the required instrumentation are refused,
  and author-supplied machine code is never reused.
- Trust in the build and trust in behaviour stay separate: an approved build of hostile gameplay logic is
  still hostile gameplay logic.

## Runtime epoch and checkpoints

- A runtime epoch plus a per-execution deadline, with checkpoints in compiled code (loop back-edges and the
  necessary entry points).
- The value hypothesis is coarse wall-clock limiting plus compiled-code performance. No exact
  instruction/CPU accounting and no known-overhead figure is promised.
- JIT and ReadyToRun need separate validation. Tiering, OSR, generics and inlining must not skip a
  checkpoint.

## The hard part is termination, not detection

- Catching the deadline is easy; ending execution reliably is not. A catch block cannot undo a latched
  termination state, finally/cleanup has edges, and host callbacks, asynchronous re-entry and new
  dependencies must keep the correct session ownership.
- A new entry must not reset a latched termination.
- The existing interpreter terminal-latch work is a semantic reference only; it is not native acceptance.

## Explicit limits

- Framework or native calls without checkpoints cannot be interrupted at will. APIs need their own time,
  cancellation and admission boundaries; a future epoch cannot pretend otherwise.
- Permissions, reflection targets, loading, memory and platform signing/distribution remain independent
  constraints. This is not a complete sandbox.
- No claim about iOS JIT, App Store distribution, or safety of arbitrary native code is made.

## Minimum future validation

1. Desktop JIT and controlled ReadyToRun: tight loops, recursion, generics.
2. Termination edges: catch around the latched state, infinite finally, re-entry after failure.
3. After a failed run, a normal work still runs in the same process.
4. Same-source OFF/ON plus the interpreter baseline: real business timing, deadline error and allocation
  overhead.

Parameters are deliberately unspecified and no experiment or schedule is created here. Whether to pursue
this at all depends on real game requirements; it must not block the current engine integration work.

