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

The reflection probe serializes **and deserializes** a closed
`Pair<TLeft,TRight>` whose generic definition is in Default and whose type
arguments come from the two collectible contexts. The constructed `Type` is
collectible even though its defining `Assembly` is not. Distinct non-default
sentinels and actual round-trip type identity are checked on both sides. Array,
nonempty list and four-level `Nest<T>` envelopes exercise the same graph.

Owned options use a fresh `DefaultJsonTypeInfoResolver`, independent of the
foreign session. Metadata is captured after serialization freezes the options;
repeated `GetTypeInfo` must return the same cached instance. `held` keeps only
that actual cached `JsonTypeInfo`, which also owns its options. The handcrafted
type-info graphs in the ordinary ownership tests are a separate control and are
not described as actual reflection-cache owners.

The `equivalent` comparison first warms **real** `JsonSerializerOptions.Default`
with a stable Default DTO. A configuration-identical copy is made read-only,
and its stable type info must be `ReferenceEquals` to Default's before it ever
sees a collectible graph. A shared resolver or an options copy alone is not
accepted as proof of shared caching state. Real Default is used again with the
stable DTO before collection, so its root-type fast slot is not the only root
being exercised. Default/equivalent and held controls assert each role's context,
assembly and type alive, rather than merely asserting that not all collected.

The foreign session round-trips again after the old session requests unload,
before the first GC phase, and stays strongly held through the old session's
observation. Its whole owning helper then returns before the outer observer
collects it. No further STJ call is made during these GC phases; the JSON report
is printed only after all lifetime snapshots have been taken. The failure mode
exits its exception helper, retaining only error type/message strings, never an
exception or `ExceptionDispatchInfo` object. Options, resolver and cached info
have separate weak-reference observations alongside contexts, assemblies, types
and the constructed generic envelope type.

The bounded test codec reads exactly three declared instance fields: an `int`,
a bounded `string`, and an optional peer whose `int` is copied. It writes those
values with `Utf8JsonWriter`. It does not give collectible types to STJ's
reflection serializer. Its temporary `FieldInfo` objects leave the helper stack
before collection. Tests cover A-B-A fresh dual-context sessions, an active
foreign session, invalid field shapes and a DTO with a throwing property that
the bounded codec never calls.

An additional bounded regression unwraps only the explicitly selected generic
pair/array/list/nest shapes and copies their two scalar fields. It does not send
those collectible graphs back into `JsonNode.Deserialize<T>` or another general
reflection fallback.

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

The seven ownership/codec cases are part of the normal executable harness:

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
dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build -- --serialization-probe held list
```

| Mode | Controlled difference |
| --- | --- |
| `none` | Load/create/release the two-role closed generic graph without serialization. |
| `bounded` | Use only the explicit bounded graph/field codec. |
| `owned` | Reflect with a distinct resolver/options graph, then return with only weak metadata references; retain foreign options independently. |
| `held` | Keep the actual frozen-options cached cross-domain `JsonTypeInfo` alive, then release that single owner. |
| `equivalent` | Copy real Default options unchanged, freeze and prove stable metadata identity sharing before touching collectible types. |
| `default` | Reflect through real Default; overwrite its fast slot with a stable DTO before observing its remaining metadata ownership. |
| `failure` | Reflect with distinct options; a synthetic author getter throws. Retain error text only. |

The optional final argument selects `pair` (default), `array`, `list` or `nest`.
Schema-2 output records runtime and STJ assembly versions/MVID, both roles'
context/assembly/type and envelope liveness, options/resolver/cached-info
liveness, cache/sharing assertions, the functional oracle and any error text.
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
`return SerializationOwnershipTests.Probe(args.Length > 0 ? args[0] : "bounded", args.Length > 1 ? args[1] : "pair");`.
Those files use only BCL APIs; no RuneCLR production assembly, package or engine
is required. Supply one mode as the executable's argument in each fresh process.

### Measured stock desktop baseline (2026-11-28)

Windows x64, SDK 11.0.100, runtime .NET 11.0.0, STJ assembly 11.0.0.0
(MVID `cb8c0bdb-0233-45f5-8f9b-38dd940c302e`): Release solution build had
0 warnings/errors, the normal Runtime harness passed 162/162 including the six
initial cases, and all three SampleHost sessions collected with `--collect`.

The strengthened closed-generic controls pass the normal harness at 163/163,
including the new bounded pair/array/list/nest case. In schema-2 pair probes,
all seven modes pass their functional assertions. `none`/`bounded` observe retired
and foreign graphs collected (exit 0). `owned`/`held`/`equivalent`/`default`/`failure`
report incomplete collection (exit 3), with both retired roles and the envelope
still alive. In `owned` and `failure`, options/resolver/cached-info weak targets
are already dead; `held` shows all three alive while cached info is held and dead
after its release. `equivalent` proves metadata identity sharing with Default,
whose resolver/info remain alive even after the temporary options copy dies.
The failure helper records only its synthetic getter-error text.

The full seven-mode by four-envelope matrix ran in 28 separate processes on
that same stock runtime. All functional assertions passed: the eight
no-serialization/bounded observations collected, while the twenty reflection
observations explicitly returned exit 3. Each equivalent-options case proved
sharing and each held/Default case asserted every role target alive.

The earlier simple-record probe logs remain distinct from this closed-generic
graph. A bounded observation does not identify the actual retaining roots or
predict a newer STJ version. No private-cache reflection is used to force a
successful outcome, and no accessor is requested during GC to drive a TTL.

### Separate .NET 12 fork evidence

A separate STJ investigation publishes its patch and focused tests on the
[runtime fork at `01cecc2a`](https://github.com/ReneeGA2020/runtime/commit/01cecc2a1af0bdca86a7e5e16780633fecf6e208).
Its reviewed xUnit/RemoteExecutor results use runtime
`12.0.0-alpha.1.26557.102` and verified .NET 12 library/reference metadata,
separately from this repository's stock .NET 11 probes above. A version label
alone does not establish the actual target framework or available APIs.

That six-case suite reports 3 passing / 3 failing on the official unpatched STJ,
and 6/6 passing with the patched fork library and with the same patch on the
fixed official source baseline `a33eebbe8e6cc76c22f30ac9b9f166ac6469d088`.
A corrected unpatched rebuild from that same source pin also reproduces the
same 3 passing / 3 failing result; an earlier invalid auxiliary baseline is
excluded from that comparison. In the unpatched collection failures,
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
The fork's inherited-`ReflectedType` factory control is a direct accessor test;
ordinary serialization does not necessarily exercise that exact member shape.
No internal accessor reflection probe is copied into these SDK regressions.

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
