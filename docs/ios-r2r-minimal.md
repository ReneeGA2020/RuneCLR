# iOS R2R collectible CID minimum

On 2026-10-12, the original iOS simulator ARM64 runtime was reduced to a
native R2R caller, a shared interface and an interpreted collectible plugin.
Two interface callbacks in the first session, completed retirement with
diagnostic GC, and the first callback in the second session reproduce the
PC-zero crash. A debugger capture then recorded a retained CID cache entry
matching a reused MethodTable address and branching through precode whose
target and MethodDesc data were both zero.

## Inputs and isolation

[The script](../eng/ios-r2r-minimal.py) extends the existing
[successful one-callback fixture](../eng/ios-r2r-repro.py). The contract is
`IProbe.Start`, `IProbe.Tick(Tick)` and `IProbe.Stop`, with a readonly
`Tick(int, TimeSpan)` value. The trusted no-inline `Driver.CallSite` loops at
one native interface call site and flushes `TICK_BEFORE` / `TICK_AFTER`
markers around every call. `PROBE_TICKS`, `PROBE_CYCLES` and `PROBE_MODE`
select the case without changing the host or plugin. The shared contract is
cached before collectible loading. Plugin IL is excluded from TPA and
composite inputs.

The pinned source is `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`, .NET 12
Debug iOS simulator ARM64, using its own .NET 11 RC1 build SDK. This
experiment does not modify runtime source. The private diagnostic library
is the already measured trace-control revision, commit
`f3645d95d3a3b40a12cc3d79ea1ca30bae976ed5`, unsigned SHA-256
`c7bf47bf9a84128caf402d92050ba3879aa6ed916d5498ca152eb9a02f7fecde`.
Its build scope and controls are documented in
[the full-host investigation](ios-r2r-investigation.md).

The output root on the experiment Mac is
`/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/ios-r2r-minimal-20261012T1500Z`.
The native `ProbeHost_Driver__CallSite` symbol is present in `probe.dylib`.
The final probe composite SHA-256 is
`07e5ea1ec40fb14cd897c723f763ff9ac6c2c88874966fe305362558c94e312b`;
the retained matching framework SHA-256 is
`11e21475a182ecabe4045a251e30f4124b63d11ceb632e5dfd2ba7fde2565128`.
All managed DLL hashes and both native composites match across original and
diagnostic runtime comparisons. Re-signing changes the wrapper executable's
signature, so its `__TEXT/__text` bytes are checked separately and match.
The IL-host comparison keeps the same plugin and matching framework but
excludes `ProbeHost.dll` from the new native composite.

## Forty-group matrix

Each cell below runs in a fresh app process. All groups use the same fixture
and dedicated simulator. `collect` requests unload and performs diagnostic
GC only after the execution stack has returned; `unload` requests unload
without forcing GC; `retain` retains all contexts.

| Case | Original native | Diagnostic off (0) | Trace only (2) | Skip insertion (1) | IL host |
| --- | --- | --- | --- | --- | --- |
| 1 session, 1 Tick, retain | Pass | Pass | Pass | Pass | Pass |
| 1 session, 2 Ticks, retain | Pass | Pass | Pass | Pass | Pass |
| 1 session, 3 Ticks, retain | Pass | Pass | Pass | Pass | Pass |
| 20 sessions, 1 Tick, collect | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| 20 sessions, 2 Ticks, collect | SIGSEGV | SIGSEGV | SIGSEGV | 20/20 | 20/20 |
| 20 sessions, 3 Ticks, retain | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| 20 sessions, 3 Ticks, collect | SIGSEGV | SIGSEGV | SIGSEGV | 20/20 | 20/20 |
| 20 sessions, 3 Ticks, unload without forced GC | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |

Final totals are **34 passing groups and six expected native faults**. All
six failures occur at the first Tick of session 2: the two-Tick cases record
three before/two after markers, while the three-Tick cases record four
before/three after. Each has one returned session, one unload request and one
`COLLECTED=True` before the fault. This establishes retirement involvement
in this fixture; it does not retroactively establish the original full
production harness's exact failing session.

Cold one-Tick calls produce no diagnostic CID records. A retained two-Tick
session records one insertion; three Ticks can use that cache successfully
before retirement. The skip-insertion comparison records 20 skips for
20 two-Tick sessions and 40 skips for 20 three-Tick sessions. All 16
skip-insertion and IL-host controls pass, including collection checks.
The unload-without-forced-GC passes do not assert completed retirement.

Results are in `run-20261012T150004Z/results-verified.json`; all six native
`.ips` reports and full logs are retained. The strengthened parser checks
the requested configuration marker, callback counts, returned sessions,
collection where required, managed exit zero, launcher status zero and no
assertion/native-fault marker before accepting a pass. Native failures have
their own explicit status. `verify.exit` is zero; a separate archive check
verifies the exact six failing case names and their post-retirement markers.

## Live code and data capture

`capture-20261012T151013Z` contains LLDB's full transcript and three JSON
snapshots read directly from the breakpoint/fault frame. The debugger changes
allocation timing: the second observed dispatch uses a different MethodTable
and misses the old entry, while a later context reuses the old address and
faults. The debugger run therefore does not prove a session-2 crash; that
timing comes from the non-debugger matrix.

| Snapshot | Object MethodTable | First cached MethodTable | Cached target | Observed state |
| --- | --- | --- | --- | --- |
| `dispatch-1.json` | `0x1057910f8` | `0x1057910f8` | `0x107f80030` | Live matching cache entry; precode data nonzero |
| `dispatch-2.json` | `0x107fb90f8` | `0x1057910f8` | `0x107f80030` | Different receiver type; old target address unmapped |
| `fault.json` | `0x1057910f8` | `0x1057910f8` | `0x107f80030` | Address reused; precode mapped RX, both data slots zero, PC 0 |

The target instructions decode to:

```text
0x107f80030: ldr x10, 0x107f84038
0x107f80034: ldr x12, 0x107f84030
0x107f80038: br  x10
```

The helper decodes the actual ARM64 PC-relative literal instructions rather
than assuming a data-page offset. The first snapshot's `x10` literal data is
`0x104c9004c`; its `x12` data is `0x105760218`. At the fault, those exact
slots are both zero in a readable/writable, non-executable mapping. The
precode instruction mapping is readable/executable and non-writable.
Registers show `x13=0x107f80030`, `x10=0`, `x12=0`, `pc=0`; the retained
target is nonzero. The CID stub loads a MethodTable/target pair, compares
the MethodTable, and branches through `x13`. The retained caller cell has
grown to four entries by the fault and still contains the original pair.

The trusted caller's `lr-4` is `blr x16`, with LR at
`ProbeHost_Driver__CallSite+456`. Its preceding instructions load the Tick
indirection cell into `x11` and the dispatch stub into `x16`. The live
snapshot supplies both caller and precode disassembly, cell/cache contents
and permissions.

The original helper's textual `register read` inside the first two breakpoint
callbacks uses LLDB's selected thread, which can differ from the callback
thread. Those two textual register dumps must not override the direct-frame
JSON values. The fault dump and fault JSON agree. The final script explicitly
selects the callback thread/frame for future text dumps; the archived original
helper preserves exactly what generated this capture.

The observed failure is a retained collectible cache entry matching a reused
MethodTable address and using a retired/reused precode address with zero
target data. Source teardown unmaps executable allocator pages; the sequence
does not establish that teardown merely clears a permanently retained page.
The later mapped code/data addresses demonstrate reuse. A shipping runtime
fix and its independent regressions remain a separate experiment.

## Evidence and reproduction

Compact evidence has been downloaded and extracted to
`artifacts/ios-r2r-investigation/20261012-minimal`. Archive SHA-256:
`b0b9ce6f7221468b4139966c5d224e2a3752a00e99c263263b1f44d9ca818de6`
(860831 bytes). It includes 184 files: scripts, generated sources,
compiler/native identities and response files, complete matrix logs, filtered
event traces, results, six crash reports, LLDB helpers/transcript/JSON, and
final source/simulator states. Large apps, objects and native libraries remain
on the experiment Mac.

The baseline tracked files are unchanged, its pre-existing Mono smoke
directory remains, and the diagnostic worktree is clean. Both minimal
investigation simulators are shut down. LLDB exited zero and its owned app
was terminated. No installed .NET runtime is changed.

Run against the preserved pinned layout on the experiment Mac, using a new
output directory:

```sh
python3 eng/ios-r2r-minimal.py build ROOT UNIQUE_OUTPUT
python3 eng/ios-r2r-minimal.py run ROOT UNIQUE_OUTPUT
python3 eng/ios-r2r-minimal.py verify-run ROOT UNIQUE_OUTPUT/run-TIMESTAMP
python3 eng/ios-r2r-minimal.py capture ROOT UNIQUE_OUTPUT
```

The build requires sibling `eng/ios-r2r-repro.py` and the matching existing
diagnostic library. It refuses to replace an existing output directory.
These are source-layout simulator experiments, not general iOS publishing
commands or physical-device acceptance. Forced GC remains diagnostic.
