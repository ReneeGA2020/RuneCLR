# Architecture

## Goal

Make C# usable for iOS hot-update scripting, then add managed UGC. New IL uses
the CoreCLR interpreter while trusted application/framework code may remain
R2R, sharing CLR types and objects. See [product direction](product-direction.md).

A host can retire one script module/session and load different C# code without
restarting the process. Successive custom maps are one example. Existing `Map`
names are prototype terminology scheduled for a later naming review. Initial
updates do not require replacing active stacks or migrating live object state.
The server-authoritative model describes the game examples, not all hosts;
deterministic lockstep is not a project goal.

## Direct interaction and trust profiles

The interpreter and trusted R2R code use CLR calls and managed references;
ordinary object interaction does not require serialization into a second
language's object model. Shared contract identity and reference ownership are
essential. Formal same-source IL/R2R and object-interop matrices remain planned
acceptance work, rather than a claim of arbitrary .NET compatibility.

The current entity handles and narrow gameplay API serve the restricted UGC
prototype. They are not a requirement that every trusted hot-update host expose
only scalar values. Richer objects/delegates can also retain collectible code;
their release contract must precede successful retirement. Host-owned final
results must remain free of script objects, exceptions and metadata.

The versioned loader currently applies `managed-il-gameplay-v1`. A supported
trusted-update integration profile is a deliverable, not an existing policy
switch. Native budget/capability work for UGC need not block that deliverable.

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

The prototype's entity store uses primitive handles and bounded log strings.
Ordinary error reporting copies the exception type name/message to a
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
complete reversal of map side effects. The lifecycle API does not yet own
background tasks, script-created threads, timers or asynchronous callbacks.
The restricted versioned policy also denies those static API routes; legacy
trusted fixtures do not pass that gate. Neither establishes a universal CLR
prohibition or a hostile-code sandbox.

## Execution backend

Assembly loading is separate from how CoreCLR executes methods. Ordinary
runtime selection is the default SDK path; the explicit policy below needs a
matching private runtime. Loading IL through an ALC alone does not make
execution interpreted.

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
[host budget option](host-instruction-budget.md). The
[controlled-package/pumped combination](controlled-package-native-budget.md)
passes 33/33 Windows groups. The updated
[iOS simulator pumped application](ios-pumped-budget-acceptance.md) passes
16 cases/74 collections in a separate diagnostic IL lane. Updated Android
host combinations, full boundary coverage and physical-device acceptance remain
open; host API charging remains separately cooperative.

Runtime changes should stay small: execution checks and allocation attribution
where host-level APIs cannot provide them. Lifecycle policy, resource stores,
capabilities, packaging, and compilation tooling belong outside CoreCLR. The
current bridge is a private matching-CoreLib experiment, with native capability
and per-context acknowledgement. Its visibility is not a security boundary.

## Game integration

The initial host-pumped session API lets the embedding host control
tick cadence and retirement. Callbacks are serialized and reentrant lifecycle
calls are rejected. There is no internal timer or native budget refill between
frames. Event dispatch, game-facing entity access, timers and async work still
need host-owned APIs and cleanup contracts. In the current server-authoritative
game example, the server validates gameplay effects. Other trusted hot-update
hosts can choose their own application model.

Time and randomness need useful game APIs, not cross-device determinism. API
versions and package compatibility need explicit contracts before public UGC
distribution.
