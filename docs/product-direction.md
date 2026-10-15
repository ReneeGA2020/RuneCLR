# Product direction

## Purpose

RuneCLR makes C# usable as an iOS hot-update scripting language, then adds the
management needed for C# UGC. This ordering was clarified by the project owner
on 2026-10-15. It broadens the earlier UGC-first plan without invalidating its
runtime experiments or weakening the restricted UGC contract.

The core value is keeping gameplay in C#: an interpreter executes new managed
IL while trusted host/framework code can remain R2R, using CLR calls and shared
objects instead of introducing a second language and its object bridge. The
runtime should be embeddable independently of Unity or a specific game engine.
Current project APIs and examples are early integration surfaces, not a finished
general-purpose mobile SDK.

## Two uses

| Concern | Developer-owned hot updates | Managed UGC |
| --- | --- | --- |
| Code source | The game's trusted development/build pipeline | Player/external source or IL, processed by controlled builds |
| Initial execution | Downloaded iOS IL interpreted; trusted application code may be R2R | Author IL/private dependencies interpreted across target platforms |
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

On iOS, new IL uses interpretation. Trusted R2R code is built ahead of time and
included through the application's native build/signing pipeline. A server-built
R2R image is not assumed to be an executable downloaded-code route on iOS. No
device-side JIT or native code generation is required by the hot-update goal.
Technical execution evidence and app-distribution approval are separate facts.

The same-source goal is to keep business logic and shared APIs stable when
choosing interpreted IL or trusted R2R at build time. It does not promise equal
performance, identical native artifacts, unrestricted library support or native
execution of newly downloaded iOS code. Formal repository acceptance remains
pending. The owner reports separate-session experiments; these are motivation,
not a replacement for reproducible evidence in this repository.

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
   IL/R2R builds, direct-object interoperability and a compatibility matrix.
3. Validate version switching, rollback and author diagnostics in a real game.
4. Extend the UGC layer with host-owned events/resources, practical memory
   observation and the remaining capability/budget boundaries. Public hostile
   UGC readiness remains a distinct later decision.

Existing UGC prototypes remain useful and can advance independently. Completing
hostile-code isolation, hard memory caps or native UGC execution is not a gate
for a trusted developer's first hot-update integration. Server-authoritative
gameplay describes the current examples and UGC pilot; it is not a universal
embedding requirement. Deterministic lockstep is not a runtime milestone.

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
