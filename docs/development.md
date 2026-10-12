# Development handoff

## Product decisions

RuneCLR is an open-source C# UGC game scripting experiment based on the CoreCLR
interpreter. The intended outcome is an embeddable engine that may serve company
games after a real pilot. The custom-map analogy describes authoring freedom and
per-game script loading, not Warcraft III's networking architecture.

- Games are server-authoritative; deterministic lockstep is not required.
- Players can run successive maps in one process. Mid-game code replacement is
  outside scope.
- iOS execution of newly downloaded IL is a central platform requirement to
  investigate.
- Development is incremental. Controlled maps and ordinary mistake recovery
  precede a production hostile-code sandbox.
- Full .NET and arbitrary NuGet compatibility are not assumed.

## Established baseline on 2026-10-12

The lifecycle prototype was introduced in commit `1ec2589`. Recheck current code
and Git state rather than treating this snapshot as the latest implementation.

The host loads manifest-selected IL assemblies in collectible contexts, shares
the map contract, invokes synchronous start/tick/stop callbacks, reclaims
host-owned entities, and exposes weak-reference collection observation.

The sample runs Hello -> Arena -> Hello in one process. Both Hello executions
start with fresh map static state. Diagnostic collection confirmed all three
contexts retired. The integration harness passed nine cases, including twenty
successive sessions, map-defined exceptions, stop failures, caught cooperative
budget violations, and host resource quotas.

Windows local validation used SDK `11.0.100-preview.6.26359.118`. The initial
GitHub workflow passed on Windows, Ubuntu, and macOS:
[baseline CI](https://github.com/ReneeGA2020/RuneCLR/actions/runs/38203072522).
The repository is public and MIT licensed:
[ReneeGA2020/RuneCLR](https://github.com/ReneeGA2020/RuneCLR).

No custom CoreCLR was built or patched as part of that prototype. The sample
does not select or prove interpreted execution. No iOS-device validation, hard
CPU/memory isolation, source compiler, or comprehensive permission boundary has
been implemented. Read [SECURITY.md](../SECURITY.md) for the current trust model.

## Resume in a new session

Set the workspace to the RuneCLR checkout. Its root `AGENTS.md` identifies the
project rules; the project Skill is at
`.agents/skills/runeclr-development/SKILL.md`. Cindy discovers this shared project
Skill root in new or restarted agent sessions. Agents without skill discovery
can read the file directly.

Read `docs/development.local.md` if present for this machine's setup. Check both
repositories' current state. The existing `global.json` selects an SDK for
RuneCLR; `dotnet/runtime` has its own toolchain configuration. Running `dotnet`
from one checkout does not establish the configuration of the other.

Re-run `./eng/verify.ps1` when starting implementation or if the environment has
changed. Read only the architecture or integration documents relevant to the
requested change; the handoff does not authorize additional work on its own.

## Recommended next experiment

Track future work in [Roadmap #11](https://github.com/ReneeGA2020/RuneCLR/issues/11).
The desktop acceptance criteria of
[#1: proven interpreter lifecycle execution](https://github.com/ReneeGA2020/RuneCLR/issues/1)
were verified locally on 2026-10-12; see [the experiment record](interpreter-experiment.md).
The next platform experiment is [#2: real-device iOS execution](https://github.com/ReneeGA2020/RuneCLR/issues/2).
See [the roadmap issue index](roadmap.md) for platform, tooling, enforcement, and
pilot tasks with their acceptance criteria and dependencies. The handoff commit
`615e832` also passed
[its three-platform CI](https://github.com/ReneeGA2020/RuneCLR/actions/runs/38205851287).

**Desktop map interpretation is verified with mode 1.** The private Checked
runtime passed all 12 lifecycle cases and both sample runs, including private
dependencies, generic static reset and a map built after the host. Successful
interpreter bytecode dumps and absence of reported map JIT compilation provide
execution evidence. CoreLib is JIT-enabled in this mode.

The separate runtime remains unpatched at
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` on branch
`runeclr/interpreter-baseline`. Its build produces a private dotnet host layout.
Use `./eng/verify-interpreter.ps1 -RuntimeRepo <checkout>` to reproduce.
Plain corerun lacks the initialized hostpolicy required by the current package
resolver. The installed .NET installation is untouched.

**Full-framework mode 3 currently fails a Checked object-reference assertion**
during manifest serialization/reflection. Do not claim a JIT-free runtime or
iOS readiness from the mode 1 result. The pinned CoreLib also marks the current
`AssemblyDependencyResolver` API unsupported on iOS. These are concrete inputs
to #2, alongside real-device dynamic loading and repeated retirement.

For a different upstream base, repeat the desktop experiment:

1. Inspect the separate runtime checkout, its build requirements, existing
   artifacts, interpreter feature gates, and mode definitions.
2. Select and record a reproducible upstream base and private runtime layout;
   build the necessary components with matching libraries.
3. Establish through runtime diagnostics that map methods actually take the
   interpreter path. Avoid assuming a switch worked merely because startup did.
4. Run the sample and integration suite using that runtime. Verify static-state
   reset, ordinary failures, resource cleanup, and completed unloading.
5. Add focused coverage for map-private dependencies and relevant generics, and
   execute a map compiled after the host build.

Follow with real-device iOS loading/unloading and then an interpreter-enforced
execution-budget prototype. See [CoreCLR integration](coreclr.md) and
[roadmap](roadmap.md) for the larger progression.

## Preserve experiment evidence

For each actual runtime experiment, record the upstream base, runtime patch
commit, host commit, OS/architecture, build configuration, runtime/library layout,
switches, proof of interpreted execution, reproduction command, and outcome.
Distinguish a failed experiment from an unperformed one. Do not fill these fields
with presumed results or reuse an unexplained artifact directory as evidence.

Update this handoff when the verified baseline changes. Keep detailed source
history in Git and machine paths in the ignored local setup document.
