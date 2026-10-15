# Roadmap

The active GitHub tracker is
[Roadmap #11](https://github.com/ReneeGA2020/RuneCLR/issues/11). Its ten sub-issues
contain acceptance criteria and dependency links. The #1 desktop acceptance
criteria are [locally verified](interpreter-experiment.md); independent
work can proceed when its prerequisites allow. Phases are capability milestones,
not release dates.

The [accepted execution strategy](execution-strategy.md) starts with interpreted
UGC on all target platforms, while trusted host/framework code can remain native.
UGC JIT is a later, separately validated exploration driven by a real pilot;
it is not required for the initial restricted profile. #5/#6 track the execution
boundary and interpreter enforcement, and #3 retains JIT performance comparisons.
Authors provide source/IL as inputs to controlled server builds; future native
execution does not permit author-supplied machine-code packages. #4 owns that
build/package trust boundary.

The [contribution sequence](work-sequence.md) gives the concrete next order:
extend #3 with session/host-boundary measurements, then build the minimal #4
controlled source/IL package pipeline and mobile-compatible dependency resolver.
Prepare #2 device environments in parallel; missing tooling does not block
independent desktop work or establish mobile support. Follow with #5's supported
execution surface and #6's terminal interpreter budgets, then #7/#8 and the game
pilot according to their dependencies. The
[platform audit](platform-validation.md) records the current environment gaps.

| Phase | Issue | Deliverable |
| --- | --- | --- |
| 1 | [#1](https://github.com/ReneeGA2020/RuneCLR/issues/1) | Reproducible interpreter build and proven map lifecycle execution |
| 1 | [#2](https://github.com/ReneeGA2020/RuneCLR/issues/2) | New map IL and repeated unloading on a real iOS device |
| 1 | [#3](https://github.com/ReneeGA2020/RuneCLR/issues/3) | Startup, gameplay callback, and memory benchmarks |
| 2 | [#4](https://github.com/ReneeGA2020/RuneCLR/issues/4) | Controlled C# compilation and versioned map packages |
| 2 | [#5](https://github.com/ReneeGA2020/RuneCLR/issues/5) | Initial map capability and dependency restrictions |
| 2 | [#6](https://github.com/ReneeGA2020/RuneCLR/issues/6) | Interpreter-enforced execution budgets and terminal interruption |
| 2 | [#7](https://github.com/ReneeGA2020/RuneCLR/issues/7) | Allocation attribution and a practical memory-limit design |
| 2 | [#8](https://github.com/ReneeGA2020/RuneCLR/issues/8) | Host-owned game-loop events, timers, and session resources |
| 3 | [#9](https://github.com/ReneeGA2020/RuneCLR/issues/9) | One server-authoritative game pilot with internal authors |
| 3 | [#10](https://github.com/ReneeGA2020/RuneCLR/issues/10) | Readiness gates for arbitrary public UGC |

Keep the milestone checklist below aligned with verified results. Issue closure
requires its stated evidence; creating a task or prototype does not establish
interpreter execution, platform support, or isolation.

## Phase 0: lifecycle prototype

- [x] Shared map contract and a small host capability API.
- [x] Manifest-based loading in per-session collectible contexts.
- [x] Sequential maps in the same process with fresh static state.
- [x] Host-owned entity cleanup and ordinary managed error reporting.
- [x] Cooperative operation, entity, and log quotas.
- [x] Weak-reference unload observation and regression tests.
- [x] Desktop build and validation workflow.

## Phase 1: interpreter and platform feasibility

- [x] Pin and build an upstream CoreCLR runtime separately from the host.
- [x] Establish interpreted map execution through runtime diagnostics (mode 1; CoreLib may JIT).
- [x] Run the lifecycle suite under the interpreter.
- [x] Load a map built after the host and verify private dependency isolation.
- [ ] Load and unload new IL on a real iOS device.
- [ ] Measure startup, callback overhead, representative loops, and memory.

Gate: downloaded C# maps execute and retire reliably on the target platforms.

## Phase 2: restricted game scripting

- [x] Initial controlled source compilation and explicit language/library support.
- [x] Initial static gameplay API/dependency gate for versioned packages.
- [ ] Dependency, reflection, dynamic loading, and native interop restrictions.
- [ ] Interpreter-enforced execution budgets and safe terminal cancellation.
- [ ] Allocation telemetry, then a design for meaningful memory limits.
- [ ] Host-owned events, timers, and resource handles with lifecycle cleanup.
- [ ] Game-loop integration and package/API versioning.

The initial [host-pumped session API](host-pumped-sessions.md) now passes Windows
ordinary and required-interpreter lifecycle suites plus cross-tick native budget
recovery. Controlled-package pumping also passes 22/22 on both Windows lanes.
Its [native-budget combination](controlled-package-native-budget.md) now passes
33/33 Windows cases with twenty-five native-budget context collections.
The broader integration item stays open for game-facing events/resources,
API versioning and matching mobile/real-device
acceptance.

The completed initial gates are documented in [controlled packaging](controlled-packaging.md)
and [capability policy](capability-policy.md). The
[portable player acceptance suite](package-execution-tests.md) adds private
version/generic state, author-failure retirement and invalid-package recovery
coverage without shipping operator compilation tooling. It passes 15/15 on
stock desktop, the pinned desktop interpreter and
[the pinned iOS simulator](ios-controlled-packages.md), alongside the existing suites.
The broader restriction milestone
remains open until runtime execution-selection and platform evidence are complete.

Gate: common author mistakes cannot leave the host stuck or leaking between games.

## Phase 3: real UGC pilot

- [ ] Integrate with an authoritative server for one game.
- [ ] Build representative UGC maps with internal authors.
- [ ] Evaluate author tooling, debugging, CPU/memory costs, and long-running sessions.
- [ ] Review untrusted-code threats and platform distribution requirements.
- [ ] Define the supported trust model before accepting arbitrary public maps.

## Outside current scope

- Live code replacement within an ongoing game.
- Cross-device deterministic simulation / lockstep networking.
- Full .NET or arbitrary NuGet package compatibility.
- A production security guarantee from the initial prototype.
