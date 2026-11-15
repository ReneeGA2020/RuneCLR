# Per-session ALC diagnostics for the Spark client (2026-11-15)

This record summarises a read-only diagnostic handoff from an independent Spark client
experiment. It asks whether per-session collectible AssemblyLoadContexts can give the game the
state isolation the earlier WASM route had, and what remains unproven. No RuneCLR runtime or host
change was made, and no RuneCLR defect was confirmed.

Three acceptance layers must stay separate; only the first is a PASS, and it is fixture-level.

| layer | status | evidence boundary |
| --- | --- | --- |
| minimal CLR mechanism | PASS, fixture only | two sessions isolate statics and instances, share contract types from Default, and release an event-retained context after unsubscribe |
| real framework migratability | not accepted | only GameCore loading, type resolution and a static read of Game.Initialized were observed; no full initialisation, no production contract crossing, no GameCore collection |
| real host close and reclaim | not measured | no SCE host or GUI was started; native-root clearing, native callback draining and ALC collection have no joint evidence |

## Session and context topology (layer 1)

- `Fixture.Contracts` resolves in the Default context; `Fixture.Framework` and `Fixture.Author`
  load into one collectible per session with required-interpreter policy 1 and never fall back to
  a Default copy.
- Per-session counters and instance counts start at zero before the next-session transition and
  then return 1, 2, 3 independently. StaticInstance differs per context while the DefaultShared
  control persists across sessions.
- Shared interfaces cast correctly across the boundary, and the bridge reports version 1,
  policy 1 and IsCollectible with no fallback.
- This shows the minimal CLR mechanics only. It does not show that a trusted framework on an
  ordinary policy and author code on a forced-interpreter policy can be separated, because both
  fixtures shared one policy-1 context in this probe.

A read-only PE metadata inventory covered 22 real assemblies (21 producer DLLs plus the author
GameEntry). Historical client logs place 19 trusted assemblies in Default and the author in a
collectible policy-1 context. The inventory only reads PE metadata and correlates existing logs;
it executes nothing and does not prove future binding.

## Retention and release probe (layer 3 mechanism, fixture only)

A single p3 run, after the previous two runs produced invalid negative controls:

- creation, author call, subscription, End, Dispose and Unload happen inside a NoInlining method;
  only a WeakReference, strings and primitive values cross the return boundary.
- With one live event handler, three bounded GC rounds leave the context alive.
- Unsubscription runs in a separate NoInlining method; after it returns, handlers are zero and one
  GC round makes the WeakReference invalid.
- Ended and UnloadRequested are both true; business result and cleanup status are recorded
  separately; exit code 0, failures empty, no residual process.

GC round counts are bounded diagnostics, not a performance or latency statement. This does not
cover native roots held by a real host, asynchronous callback draining, real Close or sandbox
properties.

## Corrections to the earlier runs (harness defects, not runtime bugs)

- p1 wrote the real `Collected` value into the result object but summarised a stale field, so its
  negative conclusion was wrong; the original run log shows collected true and cleanup collected.
- p2 called GC while its own frame still held the context argument, and the negative control did
  the same, so its five false observations cannot demonstrate a leak. The failing exit and both
  assertion failures are preserved as-is.
- p3 moves observation after the lifecycle stack unwinds, which is why it can distinguish
  retained from released state.

No runtime bug is inferred from any of these. Raw failure records are kept.

## Static state ownership

Per-session isolation of author code is not sufficient by itself: framework statics in Default
(Game.Instance, Initialized, static tables, official event subscriptions) survive a session. The
current client uses a conservative re-entry guard and requires a restart when a clean rollback
cannot be proven; that is a host state-model mismatch, not a collectible-context defect.

Design guidance that follows, without approving any implementation:

- classify assemblies by role: process-shared contract, per-session framework state, author code;
- do not blanket-ban statics; decide by state ownership and lifetime;
- if framework state must be per session, the route of putting a trusted framework into a
  per-session context is untested and must not be assumed to work;
- if the framework stays process-shared, a complete Reset/End contract is needed; unsubscribing
  author events alone is not a global reset.

## Close, cleanup, unload and collection are different results

The latest real run failed registration at `set_sprite_size` with -50, yet close still released
controls, views, tokens, author subscriptions and native references. The host returned the
business failure code from Close; the native side saw -50 and called Close again, which returned 0
because the session no longer existed.

Recommended reporting fields, kept separate: last business status, cleanup status,
sessionRemoved, callbacksDrained, unload requested, and context collected. A business failure is
not a request to destroy again, and an unknown-session Close should stay idempotent. Failed
initialisation must take the same cleanup path as a normal close; unsubscribing events must not
discard owner or provider tables that later cleanup still needs.

## Execution policy is not a sandbox

required-interpreter is an execution-policy contract. An ALC does not reproduce WASM memory or
filesystem isolation, and loading clrjit for trusted runtime code does not by itself show that
author code escaped the policy. The direct CLR path also does not need the WASM byte-marshalling
of the old adapter: typed cdecl P/Invoke replaces it for the bridge that was converted, and the
old facade is not yet fully removed. No new security bypass was tested or claimed.

## Runtime identity and budget

The probe ran on a private CoreCLR 12 layout with a net9.0 managed fixture and a runtimeconfig
pinned to 12.0.0 with rollForward disabled. Loaded component hashes from the final receipt:

| component | SHA256 |
| --- | --- |
| coreclr.dll | `48289d63f3b326f60ab787620ab7c07d364b47359572884f4f9693fff2fac85c` |
| System.Private.CoreLib.dll | `e9a94ae013b06c702114cd62c0689026e1c50e0fe1d1b02d8cd124bc3285a875` |
| clrjit.dll | `197834f4042bc5352df2f85c99d2c5b3e981b08795a6ee1fff470be176cf2e03` |
| clrinterpreter.dll | `6b861fc7c8296b9af30512dc6003150eb34c664a4f07fb1bdc70cae6ab19d975` |

The report's earlier transcription of the interpreter hash is incomplete; the final receipt value
above supersedes it and the original report is kept unchanged.

This runtime is unrelated to the S2 large-interval experiment: different layout and pins, no
deadline or budget configuration, and no performance measurement.

Session budget for this investigation was 10 of 10 (p1 four, p2 five, p3 one) and is finished.
No new sessions were started. GUI work remains paused at `set_sprite_size` and was not repaired
here.

## Unverified or open

- full game initialisation, registration and Tick on the CLR host;
- re-entry after a completed game;
- real GameCore/GameUI migration;
- real host native close with joint ALC collection;
- failed-initialisation cleanup as a final acceptance;
- separation of trusted ordinary-policy code from author forced-interpreter code;
- any memory/filesystem isolation claim.

## Evidence (local-only)

These paths exist only on the experiment machine; they are not repository-relative.

- D:/SCE-RuneCLR-integration-20261114/probes/ALC-DIAGNOSTIC-HANDOFF-20261115.md
- D:/SCE-RuneCLR-integration-20261114/probes/session-alc-20261115-p3/ (probe source, receipt, stdout/stderr, lead review log)
- D:/SCE-RuneCLR-integration-20261114/probes/session-alc-20261115-p2/ (static observations and the preserved failing run)
- D:/SCE-RuneCLR-integration-20261114/probes/session-alc-20261115-p1/ (original records)
- E:/NE/_experiments/sce-runeclr-integration-20261114/docs/RUNECLR-DESIGN-FEEDBACK-20261115.md

## Execution channels

p1 and p2 were managed Orca workers; p3 was an Orca validator worker; the Lead wrote the p3
source and performed offline receipt, source and identity review. Nothing was pushed, and no
business source tree, producer app root or frozen stage was modified.
