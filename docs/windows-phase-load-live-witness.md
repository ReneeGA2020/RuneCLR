# Windows phase-load live branch witness

On 2026-10-14, four independent owned Windows x64 Release processes establish
the actual ON/OFF selection of the phase-load precursor inside the instruction
meter hot loop. Both Good processes return73 after53 admitted dispatches and
collect their contexts. Both TightLoop processes terminate at exactly2048
dispatches, record phase1 and collect. These are debugger witnesses, not timing
measurements.

The [joined offline receipt](../artifacts/phase-load/windows-live-witness-20261014-attempt4/review/results.json)
replays all four lanes, binds32 original files and checks identical native/managed
inputs. Each original lane reviewer rejects five in-memory alterations; its
immutable receipt retains those five controls. The set reviewer adds one
non-hot-loop caller alteration per lane:20 original controls plus four caller
controls make24 combined rejections. It supplements the
[compiled-path review](windows-phase-load-hotpath.md) and separate
[functional acceptance](windows-phase-load-acceptance.md).

## Actual branch and hot-loop caller

The [capture driver](../eng/capture-phase-load-windows.py) launches the unchanged
trusted TerminalProbe host and original payload with the private matching
layout. All children use InterpMode=0, RuneCLRInterpretCollectible=0,
ReadyToRun=1 and tiering enabled. Each has a fresh32-hex nonce, output directory
and JIT log; runtime settings are applied only to that child. Parent DOTNET,
COMPlus and RUNECLR settings are removed before explicit child settings are set.
The installed runtime and both source repositories remain unchanged.

The native DLL SHA256 is
b1e9c8ffc40ffa20f4c4744a280152fe65fc2c7bfac0191486ca329e25b06b3c;
its PE/PDB identity is ab785a5f-4446-4757-8a83-ae3f8db1834e, age1. Every
request binds the executable, CDB, native DLL/PDB, CoreLib, interpreter/compiler,
trusted host files and original author DLLs. Native/managed hashes are rechecked
after each run, and the exact capture script and debugger commands are retained.

The entry breakpoint at RVA0x18e320 accepts only callers returning to the
normal meter hot-loop RVAs0x1986f5 or0x1987bf. It saves the actual meter address
and stack return address. Branch and post-instruction breakpoints accept only
that same meter/caller, then remove themselves. In all four actual processes,
the observed caller is RVA0x1986f5. Every marker reads the actual immutable
meter flag at rcx+2, phase at rcx+0x28, PC and live instruction bytes.

| Lane | PID | Actual flag | Branch RVA / live bytes | Completed result |
| --- | ---: | ---: | --- | --- |
| OFF Good | 28392 | 0 | 0x18e336 / f00fb15128 | value73, executed53, collected |
| OFF TightLoop | 46208 | 0 | 0x18e336 / f00fb15128 | executed2048, phase1, collected |
| ON Good | 33616 | 1 | 0x18e326 / 8b4128 | value73, executed53, collected |
| ON TightLoop | 692 | 1 | 0x18e326 / 8b4128 | executed2048, phase1, collected |

ON executes mov eax,[rcx+28h]; OFF executes the original
lock cmpxchg [rcx+28h],edx. The next instruction is also witnessed with EAX0
and the same meter/caller, establishing the actual phase0 read result. The
[offline reviewer](../eng/audit-phase-load-windows-witness.py) compares the
live memory dumps directly with actual PE raw bytes, checks the native mapping
and exact PE/PDB identity, and reads the completed fixture ledger and collection
from its real stderr stream. The
[set reviewer](../eng/audit-phase-load-windows-witness-set.py) joins all four
distinct PID/nonce lanes and adds the four caller corruption controls.

## Preserved preparation attempts and cleanup

Attempt1 cannot load the event command file because a backslash path inside a
CDB command string is parsed differently; it exits before fixture execution.
Attempt2 actually completes ON Good and observes Phase selection, but the
deferred checksum warning interrupts its first printf PID field. A separate
[offline review](../artifacts/phase-load/windows-live-witness-20261014-attempt2/on-Good/review.json)
accepts those immutable streams after removing that specific warning. This
earlier run establishes Phase selection only: its first call precedes payload
loading, and no hot-loop stack caller was captured.

Attempt3 stops at its first Phase breakpoint because MASM does not accept the
C-style logical operators in the conditional debugger command. CDB exits and
the incomplete evidence is preserved. Attempt4 uses MASM bitwise operators on
boolean comparisons, explicitly loads symbols before printing markers and
limits capture to actual hot-loop callers. These are experiment-driver issues,
not new CoreCLR failures. No successful process is resumed or rerun in place.

The [owned-PID cleanup check](../artifacts/phase-load/windows-live-witness-20261014-attempt4/review/cleanup-targets.json)
observes all14 owned CDB/target PIDs absent after execution. No kill operation
was issued and unrelated suite processes were not operated on. An earlier
partial PID check is retained separately.

This establishes four selected phase0 branches and actual normal/exhaustion
collection. It does not establish cleanup-path live selection, complete EH or
dispatch tracing, concurrency ordering, performance or mobile/device behavior.
