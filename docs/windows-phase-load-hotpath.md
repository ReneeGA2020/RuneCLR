# Opt-in acquire phase loads - Windows Release

On 2026-10-14, the isolated candidate
`a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186` adds an opt-in replacement for
the terminal meter's phase reads. Its direct parent is the accepted counter
increment candidate `20405f7ae23e183e038703aa5e356b3310fef427`; upstream is
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. This optimizes RuneCLR's custom
meter; it is separate from the [official runtime defect records](upstream-bugs/README.md).
It does not implement instruction batches.

## Source and matching products

Only `src/coreclr/inc/clrconfigvalues.h` and
`src/coreclr/vm/runeclrinstructionmeter.h` change from the direct parent.
`DOTNET_RuneCLRPhaseAcquireLoad` defaults to zero. A terminal meter caches the
option at construction in an immutable bool at offset2; existing fields and
the size48/align8 layout remain unchanged. When enabled, `Phase()` uses the
runtime's `VolatileLoad` helper. When disabled, it retains a zero-CAS read.
The phase-changing CAS operations, per-opcode admission, counter increments,
definition ownership and exception/finalizer handling retain their source.

The [exact candidate preparation](../artifacts/phase-load/candidate-20261014-attempt1/candidate-receipt.json)
binds the direct-parent two-file change and copied private SDK. The
[paired native header compilation](../artifacts/phase-load/header-layout-20261014-attempt2/layout-receipt.json)
checks old and new field offsets and sizes. Its initial missing-UCRT-include
attempt remains retained; the second attempt corrects the observer's include
paths without changing the runtime.

The [fresh Windows x64 Release build](../artifacts/phase-load/windows-release-build-20261014-attempt1/build-result.json)
passes with zero warnings/errors and interpreter/dynamic-code compilation
enabled. The [layout receipt](../artifacts/phase-load/windows-release-build-20261014-attempt1/layout-receipt.json)
binds36 patch sources, seven native compile owners and527 files. Matching new
native/CoreLib/compiler products overlay the pinned same-upstream framework
layout. Nine fresh product/PDB symbol pairs are included; old native PDBs are
not treated as matching new products. The [final adapter receipt](../artifacts/phase-load/build-adapter-20261014-attempt1/adapter-receipt.json)
records this build driver's baseline, SDK and symbol guards separately from
the earlier preparation snapshot. The worktree is
`E:/runtime-phase-load-20261014`, branch `runeclr/phase-acquire-load`.

## Actual emitted paths

The [main-function inspection](../artifacts/phase-load/hotpath-20261014-attempt1/results.json)
and [helper disassembly](../artifacts/phase-load/phase-helper-20261014-attempt2/cdb.stdout)
use the actual PE and private PDB. The
[path auditor](../eng/audit-phase-load-hotpath.py), with a newly reviewed
[frozen profile](../eng/runtime-patches/phase-load-hotpath-profile.json),
passes305 instruction-byte matches against the actual DLL and seven alteration
controls. The [review receipt](../artifacts/phase-load/hotpath-review-20261014-attempt1/results.json)
checks actual branch destinations and matched calls/returns for four paths.
The common PE/PDB reader is shared with the earlier auditor; the new path
selection and source guard are specific to this candidate.

PE/PDB identity is `ab785a5f-4446-4757-8a83-ae3f8db1834e`, age1.
`Phase()` is compiled as a separate function at RVA0x18e320. Its bool test is
at0x18e320; the enabled path loads phase at0x18e326, stores it to `[rsp+8]`,
reloads it and returns. The disabled path zeros EDX/EAX and executes
`lock cmpxchg [rcx+28h],edx` at0x18e336. These are emitted instructions, not
an assumption that replacing a source helper inlines to one load.

| Admitted path | Locked RMWs | Phase calls | Phase loads | Connected rows |
| --- | --- | --- | --- | --- |
| Normal, option on | 3 | 2 | 2 | 51 |
| Normal, option off | 5 | 2 | 0 | 51 |
| Cleanup, option on | 3 | 3 | 3 | 67 |
| Cleanup, option off | 6 | 3 | 0 | 67 |

The normal path calls `Phase()` at0x1986f0 and0x1987ba; its three remaining
locked operations are the remaining read0x1987d3, admission CAS0x1987e9 and
executed increment0x1987f1. Cleanup calls at0x1986f0,0x198716 and0x19872c;
its counter operations are0x198738,0x198749 and0x198751. Counts assume the
reviewed normal phase0 or cleanup phase1, positive allowance, matching cleanup
owner, valid opcode and first-CAS success. Contention, denial and diagnostic
paths differ. The parent204 inlined its phase reads, so the new option-off
code is not machine-code identical to the parent.

CDB's checksum0 and incomplete-flow warnings remain recorded. The supplemental
stdout sometimes joins adjacent instruction rows; the observer separates their
encoded addresses and validates every byte against PE sections. Original raw
outputs are retained. This review does not establish live branch selection,
complete invocation coverage, CPU attribution or a speedup.

## Acceptance and timing boundaries

An acquire load has weaker ordering than the old locked RMW read. Emitted x64
loads and source layout checks alone do not prove ordering equivalence across
admission, snapshots, cleanup or other architectures. Functional ON/OFF suites
and live branch witnesses are separate evidence. The existing phase/admission
gap and independent nontransactional snapshots remain.

The later [paired functional acceptance](windows-phase-load-acceptance.md)
passes all sixteen suite/auditor commands. The separate
[four-process live witness](windows-phase-load-live-witness.md) observes
actual normal-dispatch callers, flags and ON/OFF instruction bytes, with
normal return, exact2048 exhaustion and collection. Its20 original and four
caller alteration controls reject. That evidence samples phase0 branches;
it does not turn this offline inventory into a complete execution trace.

The later [independent bracketed measurement](windows-phase-load-performance.md)
records25.36-26.04% less budgeted callback time than its two parent brackets
and a current4.07x configured/no-config ratio for this arithmetic kernel.
This offline code inventory contains no timing data; the accepted parent's
earlier4.68x and Lua's100/1000-hook ratios remain separate experiments. New
out-of-line calls and stack accesses prevent predicting a ratio from lock
counts or attributing the measured change to one instruction alone.
The [batching proposal](budget-batching-experiment.md) describes the
separate future accounting experiment; mobile matching builds and physical
device acceptance of this phase-load candidate remain unperformed.

Reassess the retained matching evidence without running a runtime:

~~~powershell
py -3 -B eng/audit-phase-load-hotpath.py --evidence artifacts/phase-load/hotpath-20261014-attempt1 --helper artifacts/phase-load/phase-helper-20261014-attempt2 --output artifacts/phase-load/hotpath-review-new
~~~

The exact profile binds these products. Another build or compiler layout needs
a fresh disassembly and reviewed profile. Keep original controls and receipts.
