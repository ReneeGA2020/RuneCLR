# Architecture

## Goal

A host can retire one UGC script session and load different C# code without
restarting the game process. Successive custom maps are one example; scripts
may belong to other host-owned containers. Existing `Map` names are prototype
terminology scheduled for a later naming review. No live code replacement
within a session is required. Target gameplay is server-authoritative; reproducible lockstep
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

`MapPackage` reads a manifest and validates entry/private assembly metadata and
declared hashes before creating a collectible context. `MapLoadContext` uses
the explicit [package resolver](package-resolution.md), sharing the host API
assembly with matching identity. Private dependencies require a declared path,
full assembly identity and SHA-256; unknown private names fail instead of
falling back to arbitrary host assemblies. Trusted framework names come from
the host runtime inventory and use normal framework binding. This inventory
does not restrict framework APIs. Native loads through this context are
rejected, which is only a narrow restriction.

`MapRunner.Start` creates a context, constructs the entry type, invokes `OnStart`
and returns a [host-pumped session](host-pumped-sessions.md). The game loop owns
each synchronous `Tick` and the final `Stop`/`Dispose`. `MapRunner.Run` wraps the
same lifecycle with a finite tick count. Failure automatically stops the session;
resources are released in `finally`. Without a native budget, `OnStop`
is attempted whenever an instance exists, including after a failed `OnStart`;
entry constructors are not charged by the cooperative API quota. The explicit
[instruction-budget prototype](host-instruction-budget.md) charges constructors
and callbacks cumulatively and skips `OnStop` after native termination. Host
cleanup does not depend on a successful `OnStop`.

An operation or resource violation remains latched for the session. Catching
its exception does not make the session successful once control returns to the
host. It does not force a script to return, and can prevent further API use in
`OnStop`; host-owned entities are still cleared.

## Ownership and unloading

The host owns entities and retains only primitive handles and bounded log
strings. Ordinary error reporting copies the exception type name/message to a
string; the native-budget path copies a bounded type name or fixed host message
without invoking the author's virtual exception properties.
No script instance, map `Type`, `Assembly`, exception, or delegate is returned
in `MapRunResult`.

The runner and session callback frames are non-inlined so their stack and
reflection locals disappear before the caller observes unloading. A stopped
session clears its author and load-context fields even when the host retains the
session object. `Unload()` initiates collection; a weak reference
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

The [accepted target strategy](execution-strategy.md) starts with interpreted
UGC on every target platform and explores UGC JIT later. Trusted host/framework
code may remain native. Keep package/API/lifecycle contracts independent of
backend internals. The explicit [RequireInterpreter host option](session-execution-policy.md)
now requests immutable native policy before loading author assemblies. Its
[matching Windows acceptance](runtime-session-policy-build.md) passes with
global interpretation and the collectible diagnostic switch disabled. Ordinary
selection remains the default on stock SDKs; unsupported required mode fails
before author loading. Matching [iOS simulator](ios-session-policy-acceptance.md)
and [Android Checked](android-session-policy-validation.md) production suites
now pass; the separate [Android Release selection fixture](android-session-policy-release-functional.md)
and [Release production/recovery/control lanes](android-session-policy-release-production.md)
also pass. Production/refusal method-entry coverage and real-device acceptance
remain open. The [session instruction-budget plan](runtime-session-budget-plan.md)
now has matching Windows meter/terminal/finalizer prototypes and an explicit
[host budget option](host-instruction-budget.md). Its full lifecycle/mobile
acceptance is incomplete; host API charging remains separately cooperative.

Runtime changes should stay small: execution checks and allocation attribution
where host-level APIs cannot provide them. Lifecycle policy, resource stores,
capabilities, packaging, and compilation tooling belong outside CoreCLR. The
current bridge is a private matching-CoreLib experiment, with native capability
and per-context acknowledgement. Its visibility is not a security boundary.

## Game integration

The initial host-pumped session API lets the authoritative game host control
tick cadence and retirement. Callbacks are serialized and reentrant lifecycle
calls are rejected. There is no internal timer or native budget refill between
frames. Event dispatch, game-facing entity access, timers and async work still
need host-owned APIs and cleanup contracts. Client-side execution may serve UI or presentation,
but the authoritative server must validate gameplay effects.

Time and randomness need useful game APIs, not cross-device determinism. API
versions and package compatibility need explicit contracts before public UGC
distribution.
