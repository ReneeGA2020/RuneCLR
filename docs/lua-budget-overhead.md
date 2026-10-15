# Stock Lua count-hook budget reference

On 2026-10-14, stock Lua 5.4.9 on the same Windows x64 i7-10700K machine
measured **6.37x elapsed time** with a native budget hook on every counted
instruction, relative to the hook-disabled case. Checking every 100/1000
counted instructions measured **2.49x/2.44x**. These are warmed arithmetic
kernel results, not a general Lua overhead constant or game-frame estimate.

## Measured results

Each mode has four fresh processes with three warmups and nine timed samples
per process. Medians pool 36 timed samples per mode. Round ratios compare
each mode's process median with that round's no-config process median.

| Mode | Median ms | Raw min-max ms | Relative elapsed time | Added elapsed time | Round ratio range | Hook events per invocation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| No hook | 2.46835 | 2.4586-2.9050 | 1.000x | 0% | 1.000-1.000x | Not counted |
| Count 1 | 15.73075 | 15.1661-21.0664 | 6.373x | 537.30% | 6.188-6.543x | 1,100,007 |
| Count 100 | 6.14665 | 6.0363-6.8823 | 2.490x | 149.02% | 2.477-2.507x | 11,000 |
| Count 1000 | 6.01340 | 5.8885-7.1210 | 2.436x | 143.62% | 2.396-2.447x | 1,100 |

For example, 6.373x elapsed time means about 15.7% of hook-disabled throughput,
not a 537% throughput loss. Count 100 and count 1000 retain approximately
40.2% and 41.0% of hook-disabled throughput.

The source-level explanation for the remaining batch overhead is in stock
`src/lvm.c::vmfetch` and `src/ldebug.c::luaG_traceexec`. Once count hooks are
enabled, the VM enters the trace/check path on each traced instruction and
decrements `L->hookcount`; batching reduces calls to the embedding hook but
does not remove that per-instruction path. The result is consistent with
this mechanism. No CPU sampling or machine-code attribution was performed,
so the measurements do not isolate its share of elapsed time.

## Inputs and timer boundary

- Official unmodified Lua 5.4.9 archive SHA256:
  `2335b6c582a52654f94612bf10d2f4672805d05329aa6568b1d8cd9e5c6fb8e6`.
  Every extracted C/header file is compared with its archive member before
  compilation; the compiler excludes only standalone `lua.c` and `luac.c`.
- MSVC 14.44.35207 x64, `/O2 /DNDEBUG /MD /DLUA_USE_WINDOWS`, private executable.
  Windows Lua configuration already defines `LUA_USE_WINDOWS`; the retained
  build log records C4005 macro-redefinition warnings. They are not hidden or
  claimed as a warning-free build. The official VM source remains unchanged.
- Intel Core i7-10700K; Windows version 10.0.26300.0. Each process sets and
  verifies affinity mask 4, logical processor 2. The experiment was sequential
  while other agents avoided local heavy workloads. OS scheduling, clocks,
  thermals and unrelated background work are not isolated.
- [Arithmetic workload](../benchmarks/scripts/budget-workload.lua): private
  helper, 100,000 updates starting at state 12345,
  `(state * 1664525 + 1013904223) & 0xffffffff`, summing `state & 255`;
  every invocation must return checksum 12,749,776.
- [Native runner](../benchmarks/scripts/lua-budget-runner.c) stores a budget
  pointer in Lua extra space and installs `lua_sethook(..., LUA_MASKCOUNT, N)`.
  The hook increments a normal non-atomic event counter and subtracts N
  instruction units from a normal non-atomic remaining counter. It never
  calls a Lua function for successful accounting. High allowance is
  1,000,000,000,000 units and resets before every invocation.
- QPC wall clock surrounds the protected C-to-Lua invocation and workload
  execution. Loading/opening libraries, quota reset, hook installation,
  result validation, JSON output and recovery controls are outside the timer.
  The Lua function body computes its checksum inside the timer. Hook and
  quota are reset identically before each warmup/sample.
- Round order rotates through each mode in each position exactly once:
  no-config/count1/count1000/count100; count1/count100/no-config/count1000;
  count100/count1000/count1/no-config; count1000/no-config/count100/count1.

Count 1 observes 1,100,007 hook events. Count 100/1000 debit 1,100,000 units,
leaving a final seven-instruction partial batch unchecked in this workload.
No-config uses a null hook and reports null counts: no instruction total is
inferred for an uninstrumented run. Hook events count Lua's trace mechanism;
the estimates for N > 1 are event count times N, not a CoreCLR IR count.

## Precision and semantic limits

Batching trades a less frequent native hook call for delayed checks: up to
N - 1 traced Lua instructions can occur before the next hook rejects an
insufficient allowance. This is an instruction-accounting precision bound
for ordinary Lua VM execution, not a time limit. Native C functions can do
arbitrary work between Lua instructions, and this hook does not meter it.

The runner performs zero-quota and two-batch-quota controls for every budgeted
process. They must fail through `lua_pcall` with the hook's budget-exhaustion
error at the first and third hook events respectively, then successfully
execute the full checksum workload in the same state after the host removes
the hook. All 24 rejection/recovery controls pass.

This is a lightweight, single-state budget reference. It has no shared atomic
session owner, terminal phase, separately budgeted cleanup or finalizer
integration. The hook raises a Lua error; script protected calls may catch
errors, and this fixture does not establish sticky termination or hostile
code containment. It also does not exercise coroutine hook propagation or
author changes to debug hooks. Those require separate embedding policy and
tests.

The [RuneCLR optimized Windows callback](windows-budget-increment-performance.md)
currently costs 4.68x its own no-config median. Lua count 1 demonstrates that
instruction-level budgeting can also be expensive on a smaller stock VM.
The ratios are informative references, not matched enforcement or runtime
performance rankings: RuneCLR uses shared atomic terminal accounting and
definition-owner selection, Lua uses a per-state non-atomic C debug hook.
The Lua helper uses 64-bit Lua integers with explicit uint32 masking; the C#
helper uses uint32 arithmetic. Lua counted events and CoreCLR dispatched IR
instructions have different meanings and totals. Callback boundaries and
host setup differ, and the experiments were not randomized together.

## Evidence and reproduction

[Independent raw-log audit](../artifacts/lua-budget/windows-20261014-attempt1/audit.json)
passes 16 owned PID/nonce receipts, 144 timed samples, 48 warmups, QPC tick
recalculation, source/executable/compiler hashes, quota recovery and stable
hook counts. Six in-memory corruption controls reject altered checksum,
elapsed ticks, affinity, nonce, event count and recovered checksum. The audit
recomputes summaries from stdout logs rather than accepting stored timing
summaries. This is a separate audit invocation of the same tool, not an
independently authored second implementation.

A later [independently authored read-only review](../artifacts/lua-budget/root-independent-review-20261014-attempt1/results.json)
recalculates all four medians from original QPC ticks and checks16 PID/nonce
receipts,144 timed samples,48 warmups and24 quota recovery controls. It binds
61 official C/header archive members,32 compiled Lua C files, the runner,
executable and compiler hashes. Five independent corruption controls reject
altered raw timing, count, identity and precision claims; no measurement or
build is repeated.

[Input manifest](../artifacts/lua-budget/windows-20261014-attempt1/manifest.json)
records all source/compiler/executable hashes and settings.
[Process receipts](../artifacts/lua-budget/windows-20261014-attempt1/processes.json)
bind commands, PID/nonces and original stdout/stderr hashes. Frozen sources
and raw logs remain under that evidence directory; no installed Lua or .NET
runtime is replaced.

Use a fresh directory and avoid other local CPU workloads during `measure`:

~~~powershell
py -3 -B eng/benchmark-lua-budget.py --phase prepare --output artifacts/lua-budget/windows-fresh
py -3 -B eng/benchmark-lua-budget.py --phase measure --output artifacts/lua-budget/windows-fresh
py -3 -B eng/benchmark-lua-budget.py --phase audit --output artifacts/lua-budget/windows-fresh
~~~

The measured configuration is deliberately fixed at four rounds, three
warmups and nine timed samples per mode per process. Each phase refuses to
overwrite its existing evidence. More representative allocation-heavy,
table/entity or host-call workloads and ARM64/mobile runs remain useful
follow-up experiments.
