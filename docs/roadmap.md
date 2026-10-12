# Roadmap

The active GitHub tracker is
[Roadmap #11](https://github.com/ReneeGA2020/RuneCLR/issues/11). Its ten sub-issues
contain acceptance criteria and dependency links. Start with #1; independent
work can proceed when its prerequisites allow. Phases are capability milestones,
not release dates.

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

- [ ] Pin and build an upstream CoreCLR runtime separately from the host.
- [ ] Establish interpreted execution through runtime diagnostics.
- [ ] Run the lifecycle suite under the interpreter.
- [ ] Load a map built after the host and verify private dependency isolation.
- [ ] Load and unload new IL on a real iOS device.
- [ ] Measure startup, callback overhead, representative loops, and memory.

Gate: downloaded C# maps execute and retire reliably on the target platforms.

## Phase 2: restricted game scripting

- [ ] Controlled source compilation and explicit language/library support.
- [ ] Dependency, reflection, dynamic loading, and native interop restrictions.
- [ ] Interpreter-enforced execution budgets and safe terminal cancellation.
- [ ] Allocation telemetry, then a design for meaningful memory limits.
- [ ] Host-owned events, timers, and resource handles with lifecycle cleanup.
- [ ] Game-loop integration and package/API versioning.

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
