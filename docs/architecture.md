# Architecture

## Goal

A player can finish a game, select another UGC map, and load different C# code
without restarting the game process. No live code replacement within a session
is required. Target gameplay is server-authoritative; reproducible lockstep
simulation is not a project goal.

## Current prototype

```text
Game / sample host (default load context)
  RuneCLR.Runtime
  RuneCLR.Abstractions (shared contract)
  host-owned MapContext and entity/log stores
       |
       +-- session load context (collectible)
             map entry assembly
             map-private managed dependencies
             script instance and map static state
```

`MapPackage` reads a manifest and locates the entry assembly. `MapLoadContext`
uses `AssemblyDependencyResolver` while returning the host's API assembly for
the shared contract. Other unresolved dependencies can fall back to the default
context; this is normal CLR resolution, not a dependency allowlist. Native
loads through this context are rejected, which is only a narrow restriction.

`MapRunner.Run` creates a context, constructs the entry type, invokes lifecycle
callbacks, and releases resources in `finally`. `OnStop` is attempted whenever
an instance exists, including after a failed `OnStart`. The host cleanup path
does not depend on a successful `OnStop`. Entry constructors are not budgeted.

An operation or resource violation remains latched for the session. Catching
its exception does not make the session successful once control returns to the
host. It does not force a script to return, and can prevent further API use in
`OnStop`; host-owned entities are still cleared.

## Ownership and unloading

The host owns entities and retains only primitive handles and bounded log
strings. Error reporting copies the exception type name/message to a string.
No script instance, map `Type`, `Assembly`, exception, or delegate is returned
in `MapRunResult`.

The runner is non-inlined so its stack and reflection locals disappear before
the caller observes unloading. `Unload()` initiates collection; a weak reference
tracks the load context without keeping it alive. Production hosts should observe
collection at suitable lifecycle points. Forced GC in the demo and tests is
diagnostic, may pause execution, and cannot make retained references disappear.

Contexts share the CLR heap, process permissions, and framework libraries.
Unloadability does not establish memory isolation, execution isolation, or
complete reversal of map side effects. The first version does not support map
background tasks, script-created threads, timers, or asynchronous callbacks.
That is an API convention, not an enforced prohibition.

## Execution backend

Assembly loading is separate from how CoreCLR executes methods. The installed
runtime currently selects JIT/interpreter behavior. RuneCLR does not pretend
that loading IL through an ALC makes execution interpreted.

Runtime changes should stay small: execution checks and allocation attribution
where host-level APIs cannot provide them. Lifecycle policy, resource stores,
capabilities, packaging, and compilation tooling belong outside CoreCLR. The
exact runtime integration API will be designed after inspecting a pinned
upstream implementation rather than introducing a speculative public interface.

## Future game integration

Replace the headless runner with a session that is pumped by the authoritative
game host. Keep tick cadence, event dispatch, entity access, timers, and async
work under host ownership. Client-side execution may serve UI or presentation,
but the authoritative server must validate gameplay effects.

Time and randomness need useful game APIs, not cross-device determinism. API
versions and package compatibility need explicit contracts before public UGC
distribution.
