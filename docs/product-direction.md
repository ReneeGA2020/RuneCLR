# Product direction

## Purpose

RuneCLR makes C# usable as an iOS hot-update scripting language, then adds the
management needed for C# UGC. This ordering was clarified by the project owner
on 2026-10-15. It broadens the earlier UGC-first plan without invalidating its
runtime experiments or weakening the restricted UGC contract.

The core value is keeping gameplay in C#: download and load independently built
trusted R2R update modules alongside non-updateable R2R code, with interpreter
support for methods without usable precompiled bodies. They use CLR calls and
shared objects instead of introducing a second language
and its object bridge. The runtime should be embeddable independently of Unity
or a specific game engine. Current project APIs and examples are early
integration surfaces, not a finished general-purpose mobile SDK.

## Two uses

| Concern | Developer-owned hot updates | Managed UGC |
| --- | --- | --- |
| Code source | The game's trusted development/build pipeline | Player/external source or IL, processed by controlled builds |
| Execution direction | Download/load independent trusted R2R updates; interpreter support for methods without usable precompiled bodies | Author IL/private dependencies interpreted across target platforms |
| Objects and APIs | Direct managed interaction with supported host APIs | The same CLR mechanism, narrowed by capability and resource policy |
| Recovery | Defined module/version boundaries, useful errors and reference ownership | Session retirement plus budget, capability and resource management |
| Compatibility | Explicit language, framework and interop support matrix | An additional, deliberately narrower approved surface |
| Delivery | Version/compatibility checks, approved update origin, rollback | Controlled intake, provenance, authenticated approval and distribution |

These are product requirements, not two fully implemented selectable profiles.
The shipped versioned loader currently applies `managed-il-gameplay-v1`. Its
legacy trusted fixture APIs do not constitute a production trusted-update SDK.
The source compiler follows the selected SDK compiler's latest stable C#
version, without a project-imposed C# 12 ceiling. Compiler syntax, emitted IL/runtime features,
framework availability and UGC policy must be reported separately.

## What hot update means here

The first delivery target is code produced after application publication, loaded
without rebuilding the installed native host. Version changes may happen at
host-controlled module/session boundaries. Replacing active stack frames or
automatically migrating live object state is outside the initial scope. This
does not make successive-module hot updates out of scope.

For a first-party game, update modules are trusted by the game team and do not
inherit the UGC profile's interpreter-only restriction. The direction is to
download independently built R2R updates and load them with existing R2R
modules and the host, using precompiled bodies and interpretation where needed.
Based on the measured desktop result that the pinned runtime disables R2R for collectible modules, RuneCLR does not pursue unloadable hot-update R2R: an update that must be unloaded stays interpreted, and ordinary first-party execution does not repeatedly unload old assemblies.
This follows CoreCLR's R2R-plus-interpreter architecture; see the
[upstream explanation](https://github.com/dotnet/runtime/issues/112748#issuecomment-2681260591).
The current post-install IL experiments establish a useful interpreted path,
not the full first-party delivery target. Downloaded R2R native execution on
iOS still needs explicit packaging, signing/loading, method-entry and physical
device evidence. Upstream mixed-mode support does not by itself establish that
post-publication delivery path. Technical execution evidence and distribution
approval are separate facts.

The same-source goal is to keep business logic and shared APIs stable when
choosing interpreted IL or trusted R2R at build time. It does not promise equal
performance, identical native artifacts or unrestricted library support.
Formal same-source and downloaded-R2R delivery acceptance remains pending.
The owner reports separate-session experiments; these are motivation,
not a replacement for reproducible evidence in this repository.

The update boundary and execution mode are separate choices. Both trusted
updateable and non-updateable modules can have independent R2R builds and run
together, with compatible runtime/framework/architecture inputs; a single
composite image is not inherently required. They can also interact with
interpreted IL. R2R precompilation is an AOT route, distinct from NativeAOT.
Formal RuneCLR acceptance must include separately compiled module composition,
not just an interpreted module calling an R2R host.

The current UGC route deliberately chooses interpretation: machine-code R2R
would require additional budget, termination and capability enforcement. This
restriction belongs to the UGC profile, rather than to first-party hot-update
modules.

## Direct object interaction

Shared CLR types allow ordinary managed references to cross the host/script
boundary without compulsory serialization or conversion to another language's
object representation. Calls still have execution/dispatch overhead. Shared
type identity, generics, delegates, exceptions and reference lifetimes require
explicit coverage. Reflection and delegate diagnostic fixtures do not expand
the current UGC allowlist.

A host retaining a script object, delegate, exception or metadata can prevent
its collectible context from retiring. Rich interaction and unloading are
compatible only with a declared ownership/release contract. Host-owned result
records must remain free of such script references after retirement.

## Priorities

1. Complete physical iOS new-IL execution evidence and maintain reproducible
   platform runtime builds. Device access must not block independent host work.
2. Deliver a small engine-independent trusted hot-update example, same-source
   IL/R2R builds, independent downloaded R2R module loading, direct-object
   interoperability and a compatibility matrix.
3. Validate version switching, rollback and author diagnostics in a real game.
4. Extend the UGC layer with host-owned events/resources, practical memory
   observation and the remaining capability/budget boundaries. Public hostile
   UGC readiness remains a distinct later decision.

Existing UGC prototypes remain useful and can advance independently. Completing
hostile-code isolation, hard memory caps or native UGC execution is not a gate
for a trusted developer's first hot-update integration. Server-authoritative
gameplay describes the current examples and UGC pilot; it is not a universal
embedding requirement. Deterministic lockstep is not a runtime milestone.

On 2026-10-16 the project owner confirmed that the UGC mechanism must not require an entity API. SpawnEntity, entity names, and the other current IMapContext members are rules of the prototype host session. A game without entities can use script loading, capability limits, execution, and unload through its own host API. That separation is not yet an implemented extension point, and no rename is selected.

On 2026-10-17 the project owner set the host API shape. The game supplies a shared assembly and an ordinary CLR interface. The script receives an instance and calls its methods directly. RuneCLR still owns loading, capability limits, execution, and unload, and it does not define gameplay methods. SpawnEntity is not required, and calls are not dispatched by name. IMapContext remains the prototype sample and the current managed-il-gameplay-v1 allowlist. It is not renamed. A later restricted UGC allowlist names members of the host-supplied interface. Trusted hot updates are not limited to that allowlist. This decision does not implement the extension point.

Dedicated acceptance issues: [trusted integration #12](https://github.com/ReneeGA2020/RuneCLR/issues/12),
[same-source builds #13](https://github.com/ReneeGA2020/RuneCLR/issues/13),
[object interoperability #14](https://github.com/ReneeGA2020/RuneCLR/issues/14) and
[compatibility #15](https://github.com/ReneeGA2020/RuneCLR/issues/15). Physical
iOS evidence remains [#2](https://github.com/ReneeGA2020/RuneCLR/issues/2).

## Claims and comparisons

Lead public documentation with the developer problem and architectural benefits.
Separate implemented capabilities, measured configurations and planned APIs.
The existing desktop comparison found selected CoreCLR interpreter object/state
workloads near Lua 5.4 and a slower numeric recurrence. It did not benchmark
ILRuntime, xLua or ToLua, or establish a universal ranking. Future comparisons
should use representative workloads, declared versions, equivalent semantics,
host-boundary costs, warm/cold timing and actual device results.

See the [roadmap](roadmap.md), [execution strategy](execution-strategy.md),
[architecture](architecture.md) and [development handoff](development.md).
