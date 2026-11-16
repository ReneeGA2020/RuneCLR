# Grouped collectible contexts for framework and author code

Status: **partly implemented**, 2026-11-16. The public v1 API described in
[the grouped host guide](grouped-alc-host.md) exists in this worktree and compiles; it has NOT been
accepted. The grouped acceptance suite (own fixtures, lifecycle and weak-collection evidence, private
CoreCLR positive runs) is still pending, so none of the behaviour below is claimed as verified. The rest
of this page remains the design target that v1 only partially covers.

## Implemented in v1 vs still open

Implemented: one ordinary collectible framework context and one required-interpreter collectible author
context per group; immutable per-role image catalogs built from bytes before any context exists; exact
framework Assembly sharing from the selected catalog with lazy loading of framework dependencies;
group-only admission reservation so author copies cannot take framework identities; three-phase cleanup
(begin, acknowledge drain, complete) with entry admission closed while pending; staged retirement that
requests both unloads before releasing leases and returns weak tickets only.

Still open: A -> B -> A in one process, joint collection observation after lifecycle frames return, the
deliberately retained resolver-lease negative control, pending-cleanup retry under failure, external
event rooting versus internal cycles, failed initialisation followed by a successful group, terminal
reports that never root either domain, and any private-runtime policy/execution evidence. Method-level
JIT/interpreter witness and multi-platform claims remain out of scope.
Status (original proposal): design proposal, 2026-11-16. This describes a reusable RuneCLR host
scenario, not an implemented public API or a production-supported profile.
It does not request a runtime patch or change existing session defaults.

## Purpose and topology

A host may need both a trusted framework and an author module to have fresh
per-session static state, while allowing different execution policies:

| Role | Lifetime | Execution and sharing |
| --- | --- | --- |
| Host, runtime and stable contracts | Process-wide | Default context; stable contract identity |
| Trusted framework and its session-private dependencies | One group | Ordinary collectible context; normal CLR/JIT where the platform allows it |
| Author module and its private dependencies | One group | Required-interpreter collectible context; references the exact framework assemblies chosen by the host |

Trust, lifetime and execution policy are separate decisions. Collectible does
not mean untrusted or interpreter-only. This proposal does not promise
unloadable R2R, add JIT to platforms that prohibit it, or establish a sandbox.

Framework and author contexts form one retirement group. Their objects,
delegates and generic types may reference each other. Such internal cycles are
not a reason to prohibit normal static fields or object interaction.

## Current public-host boundary

The current `HostContractSessionOptions.PrototypeSharedAssemblies` option
requires existing Default-context assemblies. Its validation, the session
loader and assembly admission agree on that restriction. The public facade
does not currently express this grouped scenario.

Supporting it requires an explicit group-aware ownership and policy contract,
not simply removing the Default-context check. Existing callers and shared
contracts should keep their current semantics. The exact public API shape and
whether it extends an existing facade or introduces a separate profile remain
open design choices.

## Resolution and assembly leases

An assembly lease here means any host-owned strong reference that keeps a
session assembly or its context reachable. It is a design term, not an existing
RuneCLR API. Resolver dictionaries, captured resolver delegates, reflection
metadata and cached framework objects can all create such leases.

While a group is active, the host may cache exact `Assembly` instances and
return them from the author resolver. Sharing must preserve full assembly and
type identity; matching a simple name is not enough. The host owns the role
assignment and admitted images. Author-supplied metadata cannot designate an
assembly as trusted or redirect a private load into ordinary execution.

The group contract must identify the owner and release point of every resolver
lease, including references from one context's resolver to the other context.
Do not rely on the context becoming collectible to clear its own dictionaries.

During normal CoreCLR unloading, a transition handle keeps the ALC object alive
until its loader allocator can retire. A retained chain such as
`ALC -> resolver/cache -> Assembly -> LoaderAllocator` can prevent that
retirement. Finding the transition handle alone does not diagnose a runtime
leak; determine why the loader allocator remains reachable.

Stable process-shared assemblies are borrowed, not owned by the group. Releasing
a group lease drops the group's reference; it must not dispose unrelated host
services or unload native modules shared by other groups.

## Group retirement contract

Retirement is host-controlled and serialized with entry and callback admission:

1. Close the group to new author entries, queued work and new subscriptions.
2. Unsubscribe external callbacks, acknowledge native detach, drain required
   in-flight work and finish host resource cleanup. Partial or pending cleanup
   retains the references needed to complete it and reports that state.
3. Once no further session calls are permitted and cleanup is complete, request
   unloading of each context and explicitly release the session resolver/cache
   leases and host context references as part of the retirement boundary.
4. Return from lifecycle and resolver frames before observing the two weak
   context references. Collection is complete only when both targets are gone.

The implementation must define ordering, idempotency and partial-failure
handling for step 3. An unload request is not a synchronous collection result;
waiting for collection before releasing a blocking resolver lease is incorrect.
Any interval in which a resolver lease is released must already reject new
resolution and callbacks. An unload failure must not discard roots still
needed for a safe retry. Do not release everything merely because one cleanup
operation returned successfully.

Legitimate within-group static state need not be cleared field by field to
manufacture a collection result. External host/native roots and resolver leases
must have explicit release responsibilities. Diagnostic forced GC, if needed,
runs after stacks return and is never a per-frame lifecycle policy.

## Proposed results and diagnostics

Return only host-owned values and weak collection tickets. Do not return or
retain session `Assembly`, `Type`, delegates, instances, exception objects or
resolver closures in terminal reports.

Report these dimensions separately:

- Last business result and host cleanup result.
- Entry admission closed, callbacks detached and in-flight drain status.
- Resolver leases released, including a distinct pending or failed outcome.
- Framework and author unload requests and any individual request failure.
- Framework collected, author collected and the joint collection result.
- Context role, effective execution-policy acknowledgement and actual method
  execution evidence, when collected. Policy acknowledgement alone is not a
  method-level JIT or interpreter witness.

Unobserved, pending and failed are distinct from success. Process exit is not
in-process collection evidence. A retained weak target during a bounded
observation is not, by itself, proof of a runtime leak.

## Independent fixture and acceptance plan

A future implementation should use a small repository-owned fixture with a
stable contract, a framework assembly and an author assembly. It must contain
no embedding application's source, payloads, paths or private evidence. This
document adds no fixture implementation or test run.

The planned acceptance should cover:

- Same-process A -> B -> A with fresh framework and author static/instance state,
  shared contract identity, exact framework assembly sharing and no stale calls.
- Ordinary framework and required-author policy acknowledgements; separate
  method-level execution witnesses where required by the target profile.
- Native interop belonging to an explicitly admitted trusted framework, while
  author native-load restrictions and dynamic private-load admission remain.
- Both contexts collected after lifecycle stacks return and resolver leases are
  released, without clearing business static fields as a substitute.
- A negative control that deliberately retains a resolver assembly lease and
  stays alive, followed by lease release and successful joint collection using
  the same fixture/probe bytes and runtime.
- Within-group object/static/callback cycles contrasted with a real external
  event root; separate unsubscribe and lease-release responsibilities.
- Pending cleanup preserving retry state, failed initialization and callback
  failure, repeated retirement, and the next normal group after recovery.
- Host-owned terminal reports that do not themselves retain either context.

Successful experiments in an embedding host can motivate this contract. They
do not establish that the public RuneCLR facade already supports it. Public
acceptance requires the independent fixture, matching runtime identities and
relevant lifecycle regressions after implementation is explicitly selected.

See [architecture and ownership](architecture.md),
[host-pumped sessions](host-pumped-sessions.md), and
[the product direction](product-direction.md).
