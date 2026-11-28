# Serialization across collectible sessions

Serialization is a host integration boundary. A host's `JsonSerializerOptions`,
resolver, `JsonTypeInfo`, converter, delegate, reflection member, exception or DTO
can keep collectible code alive after a session requests unloading. An options
object is not automatically session-local just because the host constructed it
inside a callback. Equivalent options may share serializer caching state; an
independently allocated wrapper is not evidence of independent ownership.

This guide adds synthetic tests and an optional runtime compatibility probe. It
does not add a production codec, cache cleanup API, GC policy or runtime patch.
The tests use two **ordinary** collectible contexts with a DTO graph from the
author role to the framework role. They do not exercise required interpretation
or establish acceptance for `GroupedHostSession`, whose author role needs a
matching private runtime. They live in the existing Runtime test harness because
the stock host-contract callbacks intentionally do not expose arbitrary DTOs.

## Decide who owns each reference

| Object | Ownership rule |
| --- | --- |
| DTO, `Type`, `Assembly`, `MemberInfo`, getter/converter delegate | Keep within the owning session or an explicit lease. Release after callbacks/serialization finish. |
| Session options and resolver | Release the entire graph, including resolver modifiers and captured objects. Releasing only the options variable does not release a separately retained resolver. |
| `JsonTypeInfo` and property metadata | Treat as a strong lease on its type and on referenced property types, accessors and options. A Default-context metadata object may still refer to either collectible role. |
| Default or configuration-equivalent options | Treat as shared state whose lifetime can exceed one session. Verify the exact serializer/runtime combination before using reflection over collectible types. |
| Host result | Copy only independent scalar values or bytes. Do not return collectible objects, metadata, delegates or exception objects in an unload report. |
| A still-active foreign session | Keep its objects and metadata usable. Retiring one session does not authorize clearing unrelated or global serializer state. |

The ordinary regressions construct a public `JsonTypeInfo` graph referencing
both collectible roles, then retain **one** of options, resolver, type info or a
DTO. They prove the explicit owner keeps the two types alive, release it and
observe both contexts, assemblies and types collected. These are ownership
controls. They do not assert that STJ's reflection resolver caches have the same
release behaviour. A foreign pair stays active and serializable throughout,
then is retired and observed separately.

## Reflection and bounded field codecs have different contracts

The reflection probe uses real `JsonSerializer.Serialize(object, Type, options)`
against collectible types. It checks traversal of both roles, holds a foreign
session and its options, retires another session, and records weak-reference
state before and after releasing the retired session's options lease. The
failure mode invokes a synthetic throwing getter and retains only error text.

The bounded test codec reads exactly three declared instance fields: an `int`,
a bounded `string`, and an optional peer whose `int` is copied. It writes those
values with `Utf8JsonWriter`. It does not give collectible types to STJ's
reflection serializer. Its temporary `FieldInfo` objects leave the helper stack
before collection. Tests cover A-B-A fresh dual-context sessions, an active
foreign session, invalid field shapes and a DTO with a throwing property that
the bounded codec never calls.

That codec is only a fixture illustrating a finite host-owned schema. It is
not general-purpose reflection serialization: properties, arbitrary nested
graphs, collections, polymorphism, cycles, constructors, reference preservation,
custom converters and schema evolution require separate contracts and tests.
Do not infer that arbitrary author DTOs or a different codec are unload-safe.

## Observe unloading after the owning frames return

1. Close entry admission and finish or drain in-flight callbacks and serialization.
2. Release session-owned options, resolver/type-info leases, DTOs and reflection
   references. Keep independent output bytes or scalar diagnostics only.
3. Request unloading and return out of the session/serializer helper. The tests
   use `NoInlining` boundaries so local reflection and exception objects cannot
   accidentally remain on the observing frame.
4. At a diagnostic boundary, collect, wait for pending finalizers, collect again,
   then read weak references. Finalization can release native loader state that
   an earlier collection alone could not reclaim. Observe context, assembly and
   type separately; a dead wrapper alone is insufficient evidence.

The synthetic harness allows up to 12 diagnostic cycles, with no sleeps or
elapsed-time pass threshold. This is a bounded observation, not a runtime
guarantee about the number of collections. A still-live target is not by itself
proof of a runtime defect. Determine the actual root and its owner. Diagnostic
GC cannot erase a deliberate strong root and does not belong in `MapSession.Stop`
or a per-frame host policy. Existing sample/test collection helpers already use
the collect/finalizer/collect order; this does not require changing them globally.

## Run the neutral fixtures

The six ownership/codec cases are part of the normal executable harness:

```sh
dotnet build RuneCLR.slnx -c Release
dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build
```

Run **one probe mode per fresh process** so reflection-cache state from one mode
cannot contaminate the next. These optional probes are deliberately not tests
that quietly pass when collection was not observed:

```sh
dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build -- --serialization-probe bounded
dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build -- --serialization-probe owned
```

| Mode | Controlled difference |
| --- | --- |
| `none` | Load/create/release the two-role graph without serialization. |
| `bounded` | Use only the bounded scalar-field codec. |
| `owned` | Reflect with a distinct resolver/options graph for the retiring session; retain foreign options. |
| `equivalent` | Reflect with a copy of foreign options using the same resolver. The configuration is equivalent; the probe does not inspect private caches to claim actual cache sharing. |
| `default` | Reflect with `JsonSerializerOptions.Default` held by the process. Scalar/peer properties make both roles observable even though Default omits fields. |
| `failure` | Reflect with distinct options; a synthetic author getter throws. Retain error text only. |

Output records runtime and STJ assembly versions/MVID, both roles' context,
assembly and type liveness, the functional oracle and the error text, if any.
Actual diagnostic cycle counts are reported separately from the cycle limit.
Exit **0** means the functional checks passed and collection was observed for
retired and foreign pairs after their owning frames returned. Exit **3** means
functional checks passed but collection remained incomplete within the stated
observation. Other failures/invalid arguments must not be treated as retention
observations. No mode clears private caches or swaps installed runtime files.

For an independent repro, copy `SerializationFixtures.cs` and
`SerializationOwnershipTests.cs` from `tests/RuneCLR.Runtime.Tests` into a console
project targeting `net11.0`, with nullable and implicit usings enabled. The only
entry statement needed is
`return SerializationOwnershipTests.Probe(args.Length == 1 ? args[0] : "bounded");`.
Those files use only BCL APIs; no RuneCLR production assembly, package or engine
is required. Supply one mode as the executable's argument in each fresh process.

### Measured stock desktop baseline (2026-11-28)

Windows x64, SDK 11.0.100, runtime .NET 11.0.0, STJ assembly 11.0.0.0
(MVID `cb8c0bdb-0233-45f5-8f9b-38dd940c302e`): Release solution build had
0 warnings/errors, the normal Runtime harness passed 162/162 including the six
new cases, and all three SampleHost sessions collected with `--collect`.

All six fresh-process probes passed their functional checks. `none` and `bounded`
observed both retired and foreign pairs collected (exit 0). `owned`, `equivalent`
and `default` still observed both pairs' contexts, assemblies and types alive
after release (exit 3). In `failure`, the retired framework role collected but
the retired author role and the foreign pair remained alive; the synthetic
getter failure was copied to text (exit 3). The observation bound was 12
collect/finalizer/collect cycles, without a sleep or elapsed-time condition.
These observations do not identify the retaining roots or predict a newer STJ
version. A separate BCL-only console build of the same two source files reproduced
all six probe dispositions. No private-cache reflection was used to force a
successful outcome.

### Separate .NET 12 fork evidence

A separate STJ investigation publishes its patch and focused tests on the
[runtime fork at `01cecc2a`](https://github.com/ReneeGA2020/runtime/commit/01cecc2a1af0bdca86a7e5e16780633fecf6e208).
Its reviewed xUnit/RemoteExecutor results use runtime
`12.0.0-alpha.1.26557.102` and verified .NET 12 library/reference metadata,
separately from this repository's stock .NET 11 probes above. A version label
alone does not establish the actual target framework or available APIs.

That six-case suite reports 3 passing / 3 failing on the official unpatched STJ,
and 6/6 passing with the patched fork library and with the same patch on the
fixed official source baseline `a33eebbe`. In the unpatched collection failures,
options/resolver/type-info weak references are already dead while collectible
contexts, types and assemblies remain alive. Focused controls cover two-round
dual contexts, four-thread first metadata use, held metadata followed by release,
stable accessor reuse, collectible constructor type arguments and the
dynamic-code-disabled reflection fallback. No host cache cleanup is used.

This is a different focused suite; the six probe modes in this repository have
not been rerun against those .NET 12 library layouts. In particular, the passing
Default-options test is a **retention control**: live Default metadata still owns
collectible types. It does not prove that held Default or equivalent options can
be left alive while their DTO contexts collect. Bounded field/JSON-node codecs
and post-finalizer observation timing remain separate host integration concerns.

## Evidence needed before an STJ upstream change

Keep this lifecycle contract separate from the diagnosis of STJ internals.
A submit-ready upstream case still needs the exact upstream source/runtime/STJ
revision, an independently runnable synthetic repro and control, the relevant
retaining root(s), and a public-API-compatible fix with focused upstream tests.
The fork's fixed-baseline results provide reproducibility and focused patch
evidence, but do not establish validation on the latest upstream main: that
source needs matching newer type APIs in its references/runtime. Keep that
toolchain gap explicit rather than relabeling an older runtime or widening the
claim from the fixed source pin to latest main.
Exercise reflection metadata, Default/equivalent options, concurrent or foreign
sessions and failure paths on the intended versions. Preserve failures and
report version-dependent retention instead of skipping the assertion or adding
a longer sleep. Desktop stock-runtime observations do not establish interpreter,
mobile, performance, or comprehensive cache ownership guarantees.
