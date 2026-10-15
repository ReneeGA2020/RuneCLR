# RuneCLR

An embeddable C# runtime for player-created worlds.

RuneCLR explores using the CoreCLR interpreter as the foundation for a
restricted UGC game scripting engine. Games keep authority over gameplay and
resources; map authors implement C# lifecycle callbacks. The intended model is
server-authoritative gameplay, with no cross-device deterministic or lockstep
simulation requirement.

UGC scripts need not live in a container called a map: a host can attach them to
levels, game modes, minigames or other host-owned scopes. Custom maps are an
authoring analogy. The prototype currently uses `Map` names; a later naming
review will align the public API and package terminology with this broader scope.

**Status: experimental UGC runtime, not a security sandbox.** The default host
uses ordinary .NET runtime selection to validate loading, callbacks, resource
cleanup and collectible contexts. The explicit
[RequireInterpreter option](docs/session-execution-policy.md) now uses a
matching private CoreCLR/CoreLib build to fix interpreter policy before
loading author IL. Its [Windows acceptance](docs/runtime-session-policy-build.md)
passes lifecycle 24/24, player packages 15/15 and ordinary native controls with
global interpretation disabled. Stock SDKs reject unsupported required mode.
A pinned private CoreCLR build previously passed interpreted lifecycle; see
[the desktop interpreter experiment](docs/interpreter-experiment.md). Its mode 1
allows CoreLib JIT. Full-framework mode 3 hits a retained
[suspected upstream Checked assertion](docs/upstream-bugs/full-framework-interpreter-assert.md);
runtime metering and real-device iOS acceptance remain future milestones.
The [iOS simulator experiment](docs/ios-simulator-experiment.md) passes the
full harness with selective trusted R2R and the runtime assembly left as IL;
the fully R2R host interface boundary crashes on Preview 6, official RC1 and the pinned
unpatched .NET 12 Debug source build.
The [minimal cache-path reproduction](docs/ios-r2r-minimal.md) now captures
stale type/entrypoint mappings after retirement. A private conservative CoreCLR
candidate passes [Debug simulator acceptance](docs/ios-r2r-fix-validation.md):
the unchanged full R2R host passes 21/21 and controlled packages pass 15/15.
Matching [Release simulator acceptance](docs/ios-r2r-release-validation.md)
also passes. Upstream submission and real-device acceptance remain open;
these earlier mobile builds do not validate the new session policy. The later
[matching session-policy Release simulator](docs/ios-session-policy-build.md)
passes current lifecycle 24/24, packages 15/15 and 20 selection sessions with
native policy 1 and global interpretation disabled. Its separate native capture
has 11 interpreter-entry samples covering nine installed-fixture method groups.
Android policy validation, mobile refusal recovery and physical iOS execution
remain unverified.

**Direction:** start with interpreted UGC across all target platforms, then
explore UGC JIT when recovery and real-game performance evidence mature. Trusted
host/framework native code remains allowed. See
[the execution strategy](docs/execution-strategy.md) and
[the local performance comparison](docs/performance-experiment.md).

## Quick start

Install a .NET 11 SDK compatible with `global.json`, then run from the repository
root:

```sh
dotnet build RuneCLR.slnx -c Release
dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build
dotnet run --project tests/RuneCLR.Packaging.Tests -c Release --no-build
dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --collect
```

The sample runs **Hello -> Arena -> Hello in one process**. Both Hello sessions
print `start-count=1`, demonstrating fresh map static state. Each session releases
its entities. `--collect` forces GC for diagnostic unload checks; without it,
`unload: pending` is normal until GC runs. Forced GC is not a gameplay scheduling
strategy and can pause the process or wait on map finalizers.
Add `--pump` to exercise the [host-pumped session API](docs/host-pumped-sessions.md):
`MapRunner.Start` creates a session that the game host drives with `Tick(delta)`
and retires with `Stop`/`Dispose`.

On PowerShell, `./eng/verify.ps1` also compiles a separate map after the host
build and includes its execution/unloading in the tests. The tests are an
executable integration harness without third-party test packages; use the command
above rather than `dotnet test`.
The verification script also generates controlled source/IL fixtures and runs
[a compiler-free player acceptance harness](docs/package-execution-tests.md)
for rejection, failure recovery, private dependencies and retirement.

The controlled operator tool accepts raw C# or IL and produces a versioned
`package.json` with file, compiler and approved-reference hashes. It uses fixed
compiler settings and does not execute author build projects or generators.
See [the runnable source/IL packaging examples](docs/controlled-packaging.md).
The compiler-free [player acceptance harness](docs/package-execution-tests.md)
supports `--pump` for controlled-package frame scheduling, recovery and unloading.
This local tool does not authenticate approval or enforce a security sandbox.
The [initial gameplay policy](docs/capability-policy.md) checks approved API
references in every entry/private DLL during packaging and again at versioned
loading; unsupported process APIs are rejected before script execution.

## Write a map

Reference `RuneCLR.Abstractions` from a `net11.0` class library:

```csharp
using RuneCLR;

public sealed class MyMap : IMapScript
{
    private IMapContext _context = null!;

    public void OnStart(IMapContext context)
    {
        _context = context;
        context.SpawnEntity("hero");
    }

    public void OnTick(MapTick tick)
    {
        _context.Log($"Host tick {tick.Index}");
        // Add Charge() checkpoints to long loops in this cooperative prototype.
    }

    public void OnStop() { }
}
```

The following unversioned `map.json` is a trusted local-fixture compatibility
path. Use the controlled packaging tool for the versioned intake path.
Place it beside the built assembly. For a package without private
dependencies:

```json
{
  "id": "my-map",
  "entryAssembly": "MyMap.dll",
  "entryType": "MyMap"
}
```

Private dependencies must be explicitly declared with relative paths, full
assembly identities and SHA-256 hashes. They are not discovered from a map
`.deps.json` or the host directory. See [package resolution](docs/package-resolution.md)
for the schema and host framework inventory requirement.

Run one or more packages sequentially:

```sh
dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- /path/to/map.json --collect
```

The map has a public, parameterless entry constructor. Its callbacks run
synchronously on the calling host thread. `MapTick` is a callback input, not a
lockstep contract. `MapRunner.Run` remains a finite headless convenience;
`MapRunner.Start` exposes synchronous callbacks for an owning game loop.
Game-facing events, timers and networking integration remain future work.

## What works today

- Each session gets a collectible `AssemblyLoadContext`; the contract assembly
  is shared with the host and package dependencies are resolved locally.
- `OnStart`, `OnTick`, and `OnStop` run with a host-owned context.
- Entity and log quotas bound resources retained through these host APIs.
- Cooperative operation budgets are reset per callback; violations remain
  latched even when a map catches the exception and returns.
- Host entity cleanup and unload requests happen after ordinary managed failures.
- Results contain host data and error strings, not map exceptions or reflection
  objects that would accidentally retain the map context.
- `UnloadTicket.IsCollected` observes completed context collection through a
  weak reference; pending collection is not an unload failure.

## Important boundaries

Only run trusted maps in this prototype. Maps still execute ordinary .NET code
with the process's authority. A collectible context is not a security boundary.
The versioned gameplay gate rejects unsupported static API routes. Trusted
legacy fixtures do not pass that gate. The native-library loader override only
rejects its loader path; complete runtime isolation from process authority,
malformed hostile IL and runtime vulnerabilities remains outside this prototype.

`Charge()` is voluntary metering. A loop with no checkpoints, blocking library
call, constructor, finalizer, or `OnStop` can hang the host. Script allocations
are not capped. Background work and references outside the session can prevent
unloading. Versioned packages now pass controlled source/IL intake and a small
static gameplay API policy. Trusted legacy fixtures bypass that policy; complete
malicious IL verification and runtime CPU/memory enforcement remain open.

## Repository

| Path | Purpose |
| --- | --- |
| `src/RuneCLR.Abstractions` | Map lifecycle and host capability API |
| `src/RuneCLR.Runtime` | Package loading, session execution, quotas, cleanup |
| `samples/Maps.Hello`, `samples/Maps.Arena` | Independently compiled maps |
| `samples/RuneCLR.SampleHost` | Same-process multi-session demonstration |
| `tests` | Lifecycle, unload, failure, and quota integration tests |
| `docs` | Architecture, runtime integration plan, and roadmap |
| `eng` | Local verification tools |

Read [the architecture](docs/architecture.md), [CoreCLR integration plan](docs/coreclr.md),
[roadmap](docs/roadmap.md), and [security model](SECURITY.md).
The [upstream defect register](docs/upstream-bugs/README.md) tracks official
runtime findings, private fixes and future upstream-fix adoption checks.
For continuing development in a new agent session, start with
[AGENTS.md](AGENTS.md) and [the development handoff](docs/development.md). The
project Skill lives in `.agents/skills/runeclr-development/SKILL.md`.

## License

MIT. RuneCLR is an independent project, not an official Microsoft .NET component.
