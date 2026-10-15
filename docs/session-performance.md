# Host-boundary and real-session measurements — 2026-10-12

This extends [the Lua/V8 kernel comparison](performance-experiment.md) under
[#3](https://github.com/ReneeGA2020/RuneCLR/issues/3). It compares identical C#
IL interpreted versus JITted; it does not benchmark Lua/JS bindings or establish
mobile, representative game-frame or enforced-budget performance.

## Reproduction and evidence

Use the pinned, tracked-clean runtime base
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`, Release with
`FeatureInterpreter=true`, and a private dotnet layout containing matching
framework libraries and Release CLR outputs. The launcher checks the source
base, CMake flags, native product stamp and CLR file hashes against the layout.
It builds both benchmark hosts and records their actual DLLs, fixture DLLs,
source, project/configuration and launcher hashes before measurement, checking
that the inputs are unchanged afterwards.

```powershell
./eng/benchmark-sessions.ps1 -RuntimeRepo E:/runtime -PrivateLayout <private-Release-dotnet-layout>
```

The machine was Windows x64, Intel Core i7-10700K (8/16), SDK
`11.0.100-preview.6.26359.118`. Runtime branch: `runeclr/interpreter-baseline`,
no runtime source patch. Host base: `c99c5cc7fc690b71a7db609a5598acddc390076e`
plus the locally recorded sources. Evidence:

`artifacts/performance/sessions-20261012-162542-25684374505a46f48aeea266506ce6be`

It contains build logs, twelve extended/session logs, forty-two cold-process
logs, raw samples/probes, `results.json` and `summary.csv`. Generate the
self-contained Chinese mobile-readable report with:

```powershell
./eng/write-session-report.ps1 -Results <evidence-directory>/results.json
```

Each benchmark host uses three fresh processes per backend, three warmups and
seven samples per workload (21 samples total). Processes run sequentially in
recorded shuffled order. Each round additionally starts seven fresh cold
processes and runs a 40-session retention test. R2R and tiered compilation are
disabled for both backends, with mode 0 and a recorded method selector.

## Results and timing boundaries

Median elapsed milliseconds; lower is faster. Allocations are the median bytes
reported by `GC.GetAllocatedBytesForCurrentThread` inside the timed region,
not all process allocations or a map-only attribution mechanism.

| Workload | Interpreter ms | JIT ms | Allocated bytes, both modes |
| --- | ---: | ---: | ---: |
| Warm host API batch | 11.627 | 2.277 | 0 |
| Warm allocations / generics batch | 5.952 | 1.365 | 2,844,672 |
| Empty fresh map session | 0.665 | 0.757 | 5,048 |
| Fresh gameplay start/stop, no ticks | 0.998 | 2.711 | 11,448 |
| Fresh gameplay session, 128 ticks | 1.671 | 3.023 | 122,048 |
| Cold process start through exit | 761.806 | 755.986 | different timing scope |

The host API batch performs 131,072 spawn/destroy pairs, explicit cooperative
charges and 2,048 logs through the actual shared `IMapContext` interface. The
trusted benchmark adapter preallocates stores; this isolates a representative
managed-to-host boundary, not an engine's native bindings. The timed batch
includes a final primitive count validation. Checksum: `8590000128`.

The allocation batch creates Lists/Dictionary groups and invokes a private
closed generic sum, with 256 × 128 values. Checksum: `16514272`. Interpreter
time is 5.11× JIT in the host API batch and 4.36× in this allocation batch.
These are workload-specific comparisons; no universal backend multiplier follows.

Real sessions call the existing `MapRunner.Run` unchanged. Each sample has a
fresh collectible ALC: loading, activation, first-use compilation/interpretation,
start/ticks/stop, host resource cleanup and unload request are all timed. Manifest
reading, result validation, printing and diagnostic collection are outside this
interval. Warmups warm the process/framework, not the next map's fresh methods.
Thus the short-session JIT result includes repeated compilation. Its slower
result does not establish slower steady-state JIT callbacks. Callback-by-callback
frame distributions and individual loader/cleanup phase costs remain unmeasured.

Gameplay start creates 64 persistent host entities; every tick creates/releases
eight temporary entities and performs small List/Dictionary/generic work. The
128 ticks run synchronously without sleeping, rendering or a real game loop.
Each of the 128-tick sessions creates/releases 1,088 entities, leaves zero
remaining, and logs `session:starts=1;ticks=128;checksum=916496`. The zero-tick
case creates/releases 64 and logs checksum `2576`. The start counter is one in
every new session; this checks static reset rather than simply trusting loading.

Cold timing uses direct `Process.Start` through exit, including startup, manifest
reads, the first empty map and JSON output/stream capture; saving the log file is
outside timing. The inner first `MapRunner.Run` median is 53.128 ms interpreted
and 52.859 ms JIT. OS file caches are not flushed. Crucially, trusted-framework
R2R is disabled for this controlled comparison; these process numbers are not
a prediction of packaged production startup with trusted precompiled libraries.

## Execution proof and retention

Every extended-host interpreter process positively identified the two kernel entries
and their closed generic helper as interpreter precodes; four benchmark host
APIs stayed native. The real-session probe identified both maps' three callbacks
plus gameplay's private allocation and closed generic helper as interpreted.
`MapRunner.Run` stayed native. The equivalent JIT processes identified none of
these UGC entries as interpreted. This is the same pinned Windows x64 code-entry
diagnostic as the original kernel experiment, not production policy enforcement.

The session diagnostic temporarily reads the weak context from `UnloadTicket`
after Run returns, holds it while inspecting executed method entries, and returns
only primitive/string data from a non-inlined helper. It verifies collection
after that inspection, retaining no map Type/Assembly/MethodInfo or instance.
This private-field coupling is isolated to the benchmark, not a host API.

For each backend, three separate processes ran 40 consecutive gameplay sessions
without forced GC between them. Managed memory before/after/final diagnostic GC
was approximately 0.36 / 5.03 / 0.35 MiB. All three generations' collection
counts stayed unchanged during these small batches: all 40 weak contexts were
still alive before collection and all 40 were collected afterwards, in every
process. Pending GC was not an unloading failure. Each process's seven-sample
workload groups also fully collected after diagnostic GC.

Process-private memory did not return immediately to its initial level: final
snapshots were roughly 3.6–5.3 MiB above baseline across the six processes. The
CLR can retain heap segments, native allocations and caches; this experiment
does not attribute those bytes or prove bounded long-run native memory. Managed
allocation counts and context collection alone are not evidence of whole-process
memory isolation or a hard quota. Forced collection remains diagnostic.

## What comes next

The desktop increment demonstrates reproducible host-boundary, allocation and
whole-session observations while preserving lifecycle invariants. #3 remains
open for callback/GC-tail distributions, real workloads, target devices and
eventual runtime-budget overhead. The next implementation is #4's minimum
controlled compilation/package path; device preparation can proceed alongside
it. See [the ordered work sequence](work-sequence.md).
