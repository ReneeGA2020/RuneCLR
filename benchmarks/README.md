# Local interpreter performance comparison

These standalone projects are intentionally outside `RuneCLR.slnx`. The kernel
host compares warmed gameplay workloads; the session host exercises the actual
collectible MapRunner path. See [the Lua/V8 experiment](../docs/performance-experiment.md)
and [the host-boundary/session measurements](../docs/session-performance.md).

From the separate pinned `dotnet/runtime` checkout:

```powershell
./build.cmd -subset clr -configuration Release -arch x64 /p:FeatureInterpreter=true
```

The matching framework libraries and private dotnet layout from the issue #1
`clr+libs` build must already exist. From the RuneCLR root:

```powershell
./eng/benchmark.ps1 -RuntimeRepo E:/runtime
```

The launcher requires Windows x64, Visual Studio's x64 C compiler, Node.js,
`tar`, and this repo's selected .NET SDK. It verifies the pinned runtime source,
Release/interpreter build configuration and native product stamp. It downloads
official Lua 5.4.9 source with a pinned SHA-256 and compiles a private optimized
Lua executable. No system runtime, PATH, or production host code is changed.

The Lua VM is unmodified. The small C runner adds a `QueryPerformanceCounter`
wall-clock function to avoid comparing Lua's CPU clock against .NET/Node wall
clocks. The private framework layout is copied and its CLR binaries replaced
with matching Release outputs; the previous Checked layout remains intact.

`DOTNET_Interpreter=RuneCLR.Performance.Workloads:*` with mode 0 selects the
kernel assembly, while the timing host and framework remain native. JIT and
interpreter cases use identical IL and the same private runtime. R2R and tiered
compilation are disabled for these two cases; Node's default JIT configuration
is retained. Three warmups precede seven timed samples in each of three fresh
processes. Engine process order is shuffled with a recorded fixed seed.

The execution probe follows the published Windows x64 method entry to detect
the pinned source's `InterpreterPrecode` stub and its type 0x06. This positively
identifies interpreted kernels in Release, whose debug-only bytecode dump
switches are unavailable. It is a diagnostic implementation detail for this
specific source base, not a portable host enforcement API. All four kernel
entries must match the requested backend before a result is accepted.

All implementations use equivalent integer calculations and return checked
checksums. C# uses `int[]`/class instances, JS uses `Int32Array`/objects, and Lua
uses ordinary tables. Representations, bytecode counts and optimization paths
are not identical. Initialization is excluded; result summation is included.
Each entity case updates 4096 entities for 256 ticks. Numeric runs 1,000,000
dependent recurrence steps; it is not a broad mathematical workload suite.

Outputs under ignored `artifacts/performance/<run>` include raw per-process
logs, source/runtime hashes, versions, commands, timing samples, `summary.csv`,
`results.json`, and an offline single-file `report.html`. The report shows round
variation. The four-language-kernel results exclude allocation-heavy workloads,
host bindings, enforcement overhead and platform-device differences.

## Host API, allocations and real sessions

After the private Release layout exists, reuse it without modifying its files:

```powershell
./eng/benchmark-sessions.ps1 -RuntimeRepo E:/runtime -PrivateLayout <private-Release-dotnet-layout>
./eng/write-session-report.ps1 -Results <new-evidence-directory>/results.json
```

This two-backend extension needs neither Lua nor Node. It checks source/runtime
identity, builds the kernel and session hosts, captures actual DLL/configuration
hashes, then measures two warmed kernels and three fresh-map session workloads.
The performance host also accepts `[samples] --extended-only` or `--extended`;
its default four-case protocol remains compatible with the Lua/V8 launcher.

The session fixture is staged as a private package, never referenced by the
host for execution. `RuneCLR.SessionMap.*:*` selects its UGC methods; the host
remains native. Positive code-entry probes cover the callbacks/private helpers
and verify that probe metadata does not retain its collectible context.
The fresh-session interval includes load, activation, first-use compilation,
callbacks, cleanup and unload request; manifest reads and diagnostic GC are
outside. It is not a warmed callback or frame-latency benchmark.

Three rounds additionally measure seven fresh cold processes and forty
consecutive sessions per backend. Counters record current-thread allocation
and process-wide GC; snapshots distinguish pre-GC growth from completed context
collection and retained process-private memory. R2R is disabled even for trusted
frameworks in this comparison, so cold-process results are not production
startup predictions. The report embeds all data and works offline on a phone.

## Lua native budget-hook reference

The separate [Lua budget measurement](../docs/lua-budget-overhead.md) compares
stock Lua5.4.9 with no hook and native count hooks every1/100/1000 counted
instructions. It uses the same arithmetic recurrence/checksum as the RuneCLR
budget kernel, four rotated rounds and raw QPC/PID/nonce receipts.

~~~powershell
py -3 -B eng/benchmark-lua-budget.py --phase prepare --output artifacts/lua-budget/windows-new
py -3 -B eng/benchmark-lua-budget.py --phase measure --output artifacts/lua-budget/windows-new
py -3 -B eng/benchmark-lua-budget.py --phase audit --output artifacts/lua-budget/windows-new
~~~

Native per-state hook accounting is non-atomic and catchable. It does not
provide RuneCLR's shared terminal or cleanup/finalizer semantics. Batching
changes accounting precision; Lua trace events and CoreCLR IR are distinct
units. The measured ratios are references, not equivalent enforcement rankings.
