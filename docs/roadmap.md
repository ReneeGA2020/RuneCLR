# Roadmap

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
