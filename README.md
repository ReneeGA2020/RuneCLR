# RuneCLR

An embeddable C# runtime for player-created worlds.

RuneCLR explores using the .NET 11 CoreCLR interpreter as the foundation for a
restricted UGC game scripting engine. Games keep authority over gameplay and
resources; map authors implement C# lifecycle callbacks. The intended model is
server-authoritative gameplay, with no cross-device deterministic or lockstep
simulation requirement.

**Status: lifecycle prototype, not a security sandbox.** This repository does not
yet fork CoreCLR or force interpreted execution. The initial host uses the
installed .NET 11 runtime to validate loading, callbacks, resource cleanup, and
collectible assembly contexts. Interpreter execution, runtime metering, and iOS
are explicit next milestones, not capabilities established by this demo.

## Quick start

Install a .NET 11 SDK compatible with `global.json`, then run from the repository
root:

```sh
dotnet build RuneCLR.slnx -c Release
dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build
dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --collect
```

The sample runs **Hello -> Arena -> Hello in one process**. Both Hello sessions
print `start-count=1`, demonstrating fresh map static state. Each session releases
its entities. `--collect` forces GC for diagnostic unload checks; without it,
`unload: pending` is normal until GC runs. Forced GC is not a gameplay scheduling
strategy and can pause the process or wait on map finalizers.

On PowerShell, `./eng/verify.ps1` performs all three steps. The tests are an
executable integration harness without third-party test packages; use the command
above rather than `dotnet test`.

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

Place a `map.json` beside the built assembly and its private dependencies:

```json
{
  "id": "my-map",
  "entryAssembly": "MyMap.dll",
  "entryType": "MyMap"
}
```

Run one or more packages sequentially:

```sh
dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- /path/to/map.json --collect
```

The map has a public, parameterless entry constructor. Its callbacks run
synchronously on the calling host thread. `MapTick` is a callback input, not a
lockstep contract. `MapRunner` is a small headless session runner, not yet an
integration with a real game loop or networking stack.

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
The native-library loader override rejects that loader path only; it does not
prevent other native APIs, reflection, filesystem/network access, new threads,
dynamic loading, or process termination.

`Charge()` is voluntary metering. A loop with no checkpoints, blocking library
call, constructor, finalizer, or `OnStop` can hang the host. Script allocations
are not capped. Background work and references outside the session can prevent
unloading. Source compilation, dependency validation, and malicious IL
verification are not implemented.

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

## License

MIT. RuneCLR is an independent project, not an official Microsoft .NET component.
