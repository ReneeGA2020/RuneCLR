# Execution strategy — decision on 2026-10-12

## Decision

Start with interpreted UGC on every target platform, including desktop, Android
and iOS. Explore JIT for UGC after the restricted interpreter profile and a real
game pilot provide enough correctness and performance evidence. This records
the project owner's accepted direction; it is not a claim that the current host
already enforces it.

The scope is map code and its map-private managed dependencies. The trusted
host and approved framework libraries may use their platform's JIT, R2R or AOT
execution. The project does not require full-framework interpretation or a
JIT-free desktop process. Server-authoritative gameplay remains the model;
backend uniformity is not a cross-device determinism requirement.

Authors submit source or IL as build inputs. Final runnable packages are produced
by the project's controlled server-side validation/build pipeline, including any
future R2R route. Author-built runnable packages or native machine-code payloads
are not accepted for direct execution. Source/IL remains untrusted input; approval
and a trusted compiler do not automatically make gameplay behavior safe.
For a future JIT route, servers produce approved IL packages and the controlled
runtime normally generates machine code on the execution device.

## Why this sequence

The first priority is reliable map retirement and recovery from ordinary author
mistakes. One UGC execution backend lets the initial budget/termination work
concentrate on interpreter control points. It simplifies the first enforcement
experiment without claiming that interpretation itself supplies a sandbox.

The [local Release comparison](performance-experiment.md) found the interpreter
near Lua 5.4 for the selected entity/state-machine workloads on Windows x64,
with a slower numeric recurrence and a substantial gap to C# JIT. This supports
continued evaluation as a script layer, not an assumption that existing JIT
gameplay can move unchanged at the same cost. Device, real-game, allocation and
budget-instrumentation measurements are still needed.

This choice adds runtime-build and regression responsibility, especially for
Android, whose interpreter is not enabled by default in the pinned source.
Desktop measurements do not establish Android or iOS support.

## Initial execution and R2R boundary

- The restricted UGC profile accepts IL and must execute map-owned methods
  through the selected interpreter path. Constructors, generic map methods,
  callbacks and private dependencies must be considered, not just OnTick.
- Map authors cannot opt themselves into JIT or native execution. Unsupported
  execution paths must be rejected explicitly rather than silently weakening
  the restricted profile. The precise runtime enforcement remains work in #5/#6.
- Author-supplied R2R/native bodies are not an executable route in this profile.
  This remains true if JIT/R2R becomes available later. IL intake must establish
  whether to reject embedded native bodies or safely extract accepted IL, then
  produce an approved package; submitted native bodies must not be reused.
- Trusted host/framework R2R remains allowed. Calls into it must have an explicit
  accounting/restriction policy; interpreter checkpoints cannot interrupt every
  blocking native call.
- A future map R2R route must be built by the controlled server pipeline; map
  JIT uses approved IL and the project's controlled runtime. Both must retain
  equivalent restrictions before becoming part of the restricted profile.
  Trusted compiler provenance alone does not add missing budget checks.

These are target-policy requirements. The current ALC loader, environment
switches and cooperative Charge() API do not yet enforce them.

## Preserve work for a later backend

Keep map packages, supported C# features, game APIs, capability rules, resource
ownership and session outcomes independent of interpreter implementation details.
Describe budget exhaustion and termination as session behavior: a terminated map
cannot resume game API use, the host regains control safely for supported paths,
resources are reclaimed and the next map can start. Do not promise identical
internal instruction counts across future backends.

Keep interpreter-specific accounting/unwinding changes small and switch-controlled
in the separate runtime repository. Do not introduce a speculative public backend
API ahead of the runtime experiment. Lifecycle regressions, compilation/package
tooling, capability tests and author tools should serve either backend. Native
execution accounting and terminal interruption will require additional work
for JIT; this part is not assumed to transfer automatically.

Retain JIT as a development baseline, using identical gameplay IL where supported.
The benchmark's opt-in method selection is diagnostic, not production policy
enforcement. A trusted development comparison must not enable authors to bypass
the default restricted execution route.

## When to explore UGC JIT

1. The supported interpreter profile has demonstrated lifecycle recovery and
   terminal budget behavior, including catch-and-continue loops and declared
   framework/native-call limits.
2. A real game pilot identifies CPU bottlenecks and a concrete performance need,
   after measuring representative workloads and useful host batch APIs.
3. A separate JIT experiment can keep the same capability/resource/session
   contracts and pass the relevant restriction and recovery tests.

Initial JIT exploration may use trusted test maps. Making it a restricted UGC
backend requires equivalent enforcement; enabling ordinary JIT is not that
milestone. Comprehensive public hostile-code readiness remains #10, rather
than a prerequisite for every internal experiment.

## Tracking

- [#11](https://github.com/ReneeGA2020/RuneCLR/issues/11): accepted strategy and roadmap.
- [#2](https://github.com/ReneeGA2020/RuneCLR/issues/2): real iOS loading/retirement.
- [#3](https://github.com/ReneeGA2020/RuneCLR/issues/3): performance evidence, including JIT comparisons.
- [#5](https://github.com/ReneeGA2020/RuneCLR/issues/5): execution/capability/dependency boundary and target-platform coverage.
- [#6](https://github.com/ReneeGA2020/RuneCLR/issues/6): initial interpreter budget/terminal interruption.
- [#9](https://github.com/ReneeGA2020/RuneCLR/issues/9): real game pilot informing later JIT work.

Keep these issues open until their acceptance evidence exists. No separate JIT
implementation milestone is scheduled by this decision.
