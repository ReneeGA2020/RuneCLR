# Interpreter performance experiment — 2026-10-12

This is a local Windows x64 comparison prompted by the choice between
cross-platform interpreted UGC and platform-dependent interpreter/JIT UGC.
It does not change RuneCLR's execution policy. Follow
[the benchmark procedure](../benchmarks/README.md) to reproduce.

## Environment and evidence

- CPU: Intel Core i7-10700K, 8 cores / 16 logical processors; sequential engines.
- CoreCLR base: `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`, branch
  `runeclr/interpreter-baseline`, no source patch. Release with
  `/p:FeatureInterpreter=true`; matching libraries from the same source base.
- Host baseline commit: `c99c5cc7fc690b71a7db609a5598acddc390076e` plus these
  uncommitted benchmark sources. Source hashes are included in the raw result.
- Host SDK: `11.0.100-preview.6.26359.118`; test IL built in Release.
- JavaScript: Node.js `v24.13.0`, default V8 JIT and `--jitless` in separate runs.
- Lua: official 5.4.9, MSVC x64 `/O2 /DNDEBUG /MD`; no LuaJIT. Archive SHA-256:
  `2335b6c582a52654f94612bf10d2f4672805d05329aa6568b1d8cd9e5c6fb8e6`.
- Evidence directory:
  `artifacts/performance/20261012-143715-7ca26886e472479c9ebe55af2d4f7b1a`.
  It contains all 15 process logs, raw timing samples, source and runtime hashes,
  commands/settings, versions, and positive execution-entry probes.
- The launcher now also records SHA-256 hashes of the executed benchmark host
  and kernel DLLs, `Directory.Build.props`, `global.json`, the measurement script
  and the report-generation script before measurement, then verifies they and
  recorded benchmark sources remain unchanged. These additional fields apply
  to new runs; they were not captured by the original run above, whose evidence
  has not been retroactively rewritten.
- Release runtime build completed with 0 warnings/errors. The regular project
  verification passed; the same Release private runtime also passed 12/12
  lifecycle cases and the three-map sample with all contexts collected.
  Logs: `artifacts/performance/project-verification.log`,
  `release-lifecycle.log`, and `release-sample.log`.

## Measurements

Elapsed milliseconds; lower is faster. Median of 21 measurements per case
and engine (three fresh processes, three warmups then seven samples each).
Initialization, startup, backend probe and printing are outside timing. Kernels
are warmed before measurement; the timed interval includes the kernel and its
checksum summation. Default V8 tiered JIT may continue optimizing or deoptimizing
during measurement, so compilation overhead is not guaranteed to be excluded.

| Kernel | CoreCLR interpreter | Lua 5.4.9 | JS jitless | CoreCLR JIT | JS JIT |
| --- | ---: | ---: | ---: | ---: | ---: |
| Numeric, 1,000,000 recurrence steps | 25.42 | 15.66 | 22.23 | 3.32 | 2.98 |
| Entities, separate arrays | 94.66 | 101.13 | 123.11 | 3.71 | 4.44 |
| Entities, object fields | 72.44 | 81.56 | 63.54 | 3.03 | 4.61 |
| Skill state machine, object fields | 43.43 | 44.90 | 43.06 | 0.96 | 2.21 |

Entity kernels update 4096 entities for 256 ticks: 1,048,576 entity updates.
These batch times are not the cost of one game frame. The interpreter object
update's arithmetic average is approximately 0.283 ms per 4096-entity tick,
before additional gameplay, bindings and enforcement costs; it is not a
measured frame-latency guarantee.

All engines produced the same checksums: numeric `32760817287`, both entity
update cases `180282568`, skills `449798`. Every interpreter process positively
identified all four workload entries as `InterpreterPrecode` type 0x06;
every JIT process identified none of them as interpreted. The probe is pinned
to the Windows x64 source layouts in `vm/precode.h`, `vm/precode.cpp` and
`vm/amd64/thunktemplates.asm`.

Compared with Lua, the interpreter used 1.62x time for the numeric recurrence,
0.94x for separate arrays, 0.89x for object fields, and 0.97x for skills.
Small differences should not be read as a reliable universal ranking: Lua's
skill round medians ranged from 41.24 to 46.96 ms, while CoreCLR's ranged from
42.94 to 44.07 ms. The HTML report and JSON show variation for every case.

The same C# kernels used approximately 8–45x more time interpreted than JITted
in this experiment. This is a workload-specific range, not a general .NET
interpreter slowdown or an estimate of whole-game slowdown.

## What this supports

The measured object/state-machine workloads put the CoreCLR interpreter near
Lua 5.4 on this desktop. It is reasonable to continue evaluating interpreted
C# as a gameplay script layer. Static typing does not guarantee superiority:
the dependent numeric recurrence was slower than Lua and V8 jitless here.

The JIT difference is material for a project intending to move existing C#
gameplay wholesale into interpreted UGC. Preserve a JIT comparison, measure
real game workloads and consider trusted host batch APIs for expensive work.
These results alone do not settle the default cross-platform execution policy.

## Limits and next measurement

This compares language-appropriate arrays/objects, not identical memory layouts.
Lua tables, JS typed arrays and C# integer arrays have different semantics and
costs. The synthetic kernels are allocation-light, monomorphic and warmed;
they omit host bindings, cold methods, map packaging/unloading, allocation-heavy
logic, GC tail latency and interpreter-enforced quota checks. No memory usage
or actual game-frame P95/P99 is established.

No iOS/Android or ARM64 speed claim follows from these measurements. Before
choosing a production policy, repeat with a real gameplay workload and then
with enforced-budget instrumentation on the intended devices. Do not infer
that the uninstrumented baseline will retain the same cost after enforcement.
