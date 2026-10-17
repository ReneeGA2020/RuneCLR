# Getting started

This guide exercises the current lifecycle prototype on a desktop SDK. Read
the [product direction](product-direction.md) for the hot-update and UGC goals.
A distributable iOS integration SDK remains planned work.

## Build and verify

Install a .NET 11 SDK compatible with `global.json`, then run from the repository
root:

```sh
dotnet build RuneCLR.slnx -c Release
dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build
dotnet run --project tests/RuneCLR.Packaging.Tests -c Release --no-build
dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --collect
```

On PowerShell, `./eng/verify.ps1` also compiles a separate script after the host
build, generates controlled source/IL packages and runs synchronous/pumped
player acceptance. Tests are executable harnesses; `dotnet test` is not their
entry point. The ordinary SDK lane does not establish interpreter selection.
Required interpretation and native budgets need a matching private runtime;
see [session policy](session-execution-policy.md) and
[budget options](host-instruction-budget.md).

The sample runs **Hello -> Arena -> Hello** in one process. Both Hello sessions
print `start-count=1` and each session releases its entities. `--collect` forces
GC for diagnostic collection checks. Without it, `unload: pending` is normal
until GC runs. Forced GC is not a frame scheduling strategy.

## Write a script

The prototype uses `Map` terminology; scripts need not be maps.

SpawnEntity belongs to this prototype host sample. Using the UGC mechanism does not require an entity API. A game without entities supplies its own host API; that extension point is not implemented here. On 2026-10-17 its decided shape is a game-owned shared CLR interface called directly by the script. See the product direction.

Reference
`RuneCLR.Abstractions` from a `net11.0` class library:

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
    }

    public void OnStop() { }
}
```

This minimal unversioned `map.json` is a trusted local-fixture path. Put it beside
the entry assembly:

```json
{
  "id": "my-map",
  "entryAssembly": "MyMap.dll",
  "entryType": "MyMap"
}
```

Run one or more fixtures sequentially:

```sh
dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- /path/to/map.json --collect
```

Private dependencies must be explicitly declared with relative paths, complete
assembly identities and SHA-256 hashes. They are not discovered through a script
`.deps.json` or arbitrary host directories. See [package resolution](package-resolution.md).

For versioned source/IL intake, use the [controlled package tool](controlled-packaging.md).
It applies the current restricted UGC profile; the unversioned fixture path
does not replace approval or a supported trusted hot-update distribution path.

## Drive a session

Add `--pump` to the sample for host-driven frames. In an embedding host,
`MapRunner.Start` creates a session, `Tick(delta)` runs one callback, and
`Stop`/`Dispose` retires it. Callbacks execute synchronously on the calling host
thread. `MapRunner.Run` remains a finite headless convenience. See
[host-pumped sessions](host-pumped-sessions.md). Events, timers and richer
resource registration are follow-up work.

## Resource and execution limits

The sample bounds entities/logs and offers voluntary `Charge()` checks. Without
the explicit native budget prototype, uncharged loops and blocking calls can
hang the host. Matching private runtime experiments add cumulative interpreted
instruction budgets with declared cleanup boundaries; they do not preempt every
host/native call. Managed allocations are not hard-capped.

Release script references before observing collectible-context retirement.
Results contain strings/scalars rather than script objects or exceptions.
See [architecture](architecture.md) and [the trust model](../SECURITY.md).
