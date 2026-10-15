# RuneCLR development

## Project intent

RuneCLR first makes C# usable for iOS hot-update scripting, then adds the
management needed for C# UGC. New IL executes through the CoreCLR interpreter
and interacts with trusted R2R host code through shared CLR types and objects.
Keep hot-update and non-hot-update logic in C# and aim for engine-independent
embedding. Read docs/product-direction.md for the two uses and their boundaries.

Trusted developer-owned hot updates must not wait for all restricted-UGC
capabilities. The current UGC compiler/API restrictions are a profile, not the
language or runtime's universal compatibility ceiling. Same-source IL/R2R
builds and broad object interoperability need their own reproducible acceptance.
Source compilation follows the selected SDK compiler's latest stable C#
version. Do not impose an older source-language cap as a substitute for API
capability policy or runtime compatibility checks.
On iOS, newly downloaded IL is interpreted; trusted R2R belongs to the
application's native build/signing pipeline.

Successive script sessions/maps are one integration model. Initial version
switches can happen at module/session boundaries; active-stack replacement and
automatic live-state migration are not required. Server-authoritative gameplay
describes the current game examples, not every embedding host. Lockstep and
cross-device deterministic simulation remain outside scope.

Work incrementally toward use in company games. Prioritize platform feasibility
and recovery from ordinary author mistakes before full hostile-code hardening.
Keep the prototype's actual trust model explicit without making comprehensive
security a prerequisite for every useful experiment.

## Start here

- Read `docs/product-direction.md` for positioning and `docs/development.md`
  for handoff status and the next experiment.
- If present, `docs/development.local.md` records machine-specific paths.
- Use `.agents/skills/runeclr-development/SKILL.md` for lifecycle, interpreter,
  execution-budget, or coordinated CoreCLR work.
- Read `docs/architecture.md` for ownership and unloading; `docs/coreclr.md` for
  interpreter integration; `docs/roadmap.md` for milestones.

## Implementation boundaries

The default stock-SDK path uses ordinary runtime selection. Explicit
`RequireInterpreter` and native budget prototypes need matching private
CoreCLR/CoreLib builds; unsupported required mode rejects before author loading.
ALC loading, cooperative `Charge()` checks, and a native loader override do not
establish a security sandbox. Environment variables alone do not prove
interpreter execution.

Map code, dependencies, and static state belong to a per-session collectible
context. Share the host's `RuneCLR.Abstractions` assembly. Host-owned results
must not retain map instances, delegates, reflection metadata, or exceptions.
Observe unloading after the execution stack has returned; pending GC is not
proof of failure. Forced GC is diagnostic and not a per-frame policy.

Keep packaging, resource ownership, scheduling, and game APIs in RuneCLR. Place
changes in CoreCLR only where runtime enforcement requires them. Prefer small,
switch-controlled runtime patches and record their upstream base.

## Two repositories

RuneCLR and `dotnet/runtime` are separate repositories. Locate the runtime from
the local document or the user's environment; do not vendor it into this repo.
Before editing it, read its applicable `AGENTS.md` files, check its branch and
working tree, and read its checked-out build documentation. Preserve unrelated
work and use a dedicated branch or worktree for RuneCLR runtime changes when
appropriate. Keep commits and validation evidence separate for each repository.

Use private build outputs or a Core_Root to test runtime patches. Do not replace
the installed .NET runtime with experimental binaries. Existing runtime
artifacts are not evidence of their source version or interpreter configuration.

## Verification

From this repository's root:

```sh
dotnet build RuneCLR.slnx -c Release
dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build
dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --collect
```

PowerShell: `./eng/verify.ps1`. Tests are an executable integration harness;
`dotnet test` is not its entry point. Lifecycle and quota changes need meaningful
regressions. Documentation-only changes need link/content checks, not a runtime
rebuild. Runtime patches also require relevant upstream tests and the RuneCLR
lifecycle suite on the patched runtime.

Record measured capabilities separately from proposed ones. In particular,
desktop JIT results and macOS CI do not establish interpreter or iOS support.
