# iOS R2R cached interface dispatch analysis

This is a read-only analysis of CoreCLR base
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`, performed on 2026-10-12.
The separate local runtime checkout remains on the unpatched
`runeclr/interpreter-baseline` branch. No runtime source or binary changes were
made by this analysis. See the [experiment record](ios-r2r-investigation.md)
and [selective mobile package acceptance](ios-controlled-packages.md).

## Measured evidence

Local evidence is under
`artifacts/ios-r2r-investigation/20261012-cache/`. The remote diagnostic revision
is `f3645d95d3a3b40a12cc3d79ea1ca30bae976ed5`, based on the pinned source. Its
Debug-only configuration flag can trace collectible CID resolutions, skip
publishing their cache entries, or leave the default path unchanged. This is an
experimental diagnostic, not an accepted upstream fix.

The verified results of `compare-20261012T134720Z` establish:

| Native runtime / switch | Managed result | Collectible trace/cache skips |
| --- | --- | --- |
| Original / 0 | SIGSEGV, no managed successful exit | 0 / 0 |
| Diagnostic / 0 | SIGSEGV, no managed successful exit | 0 / 0 |
| Diagnostic / 2, trace without changing caching | SIGSEGV, no managed successful exit | 1 / 0 |
| Diagnostic / 1, do not publish collectible mappings | 21/21 suite passed, managed exit 0 | 52 / 52 |

The trace-only run logs the interpreted `CounterMap.OnTick` bytecode, then
`RUNECLR_CID_RESOLVE skip=0 cell=0x15c3f8e60 mt=0x14bac5778 target=0x14baec030`,
then a native SIGSEGV. Addresses describe that one process, not stable symbols.
The corresponding upstream-source test adaptations pass both tests across ten
cycles on original and diagnostic binaries, but record zero collectible cache
skips. They therefore supply useful unrelated behavior checks, not direct
coverage of the failing CID path.

Simulator launcher exit 0 is not the managed success condition: all four
launches recorded that launcher status, including native crashes. The verified
matrix requires the suite pass line, managed exit marker and absence of native
SIGSEGV/assertions. Preserve the original logs and `results-verified.json`.

## Exact runtime path

The following file/line references are in the separate `dotnet/runtime`
repository at the base above.

1. `src/coreclr/vm/arm64/CachedInterfaceDispatchCoreCLR.S:65` creates the
   transition block and calls `CID_ResolveWorker`; it restores the original
   argument state before tail-branching to the returned target.
2. `src/coreclr/vm/virtualcallstub.cpp:1394` resolves the object MethodTable and
   dispatch token through `VirtualCallStubManager::Resolver`.
3. `src/coreclr/vm/virtualcallstub.cpp:2372` checks whether the implementation
   slot still calls the prestub. A cold nongeneric slot is returned for immediate
   invocation without publishing a persistent cache mapping. An already
   prepared slot permits caching.
4. `src/coreclr/vm/contractimpl.h:57` returns the slot's PCODE unchanged;
   `src/coreclr/vm/virtualcallstub.cpp:2485` uses that value as the target.
5. `src/coreclr/vm/virtualcallstub.cpp:1423` publishes that same target when
   patching is permitted. The worker subsequently returns the target for the
   immediate slow-path invocation.
6. `src/coreclr/runtime/CachedInterfaceDispatch.cpp:417` writes a raw
   `(MethodTable*, PCODE)` mapping, growing the cache if required. The empty-entry
   update and cell's stub/cache publication use aligned two-pointer atomic
   compare/exchange.
7. `src/coreclr/runtime/arm64/StubDispatch.S:32` loads the cached type/target
   pair, compares the object's MethodTable, then `br x13` on a match. Cache
   pointer tags and cache sizes are checked before probing. The fast path does
   not recreate the slow resolver's managed transition frame.

The relevant fast stub is the shared CoreCLR runtime `StubDispatch.S`. The
NativeAOT `DispatchResolve.S` has a different hashtable-based implementation and
must not be substituted when describing this crash.

## Targets and lifetime

On this ARM64 iOS configuration the target is an ordinary executable entry
point/precode, not a WASM portable-entrypoint data record. The base's
`src/coreclr/clrfeatures.cmake:77` selects portable entrypoints for WASM.
Portable-entrypoint decoding is therefore not a justified ARM64 iOS fix.

Interpreted native calls use an executable InterpreterPrecode allocated from
the callee LoaderAllocator's stub heap:
`src/coreclr/vm/precode.cpp:237`. Initialization stores the bytecode address and
InterpreterStub target at `src/coreclr/vm/precode.cpp:624`; allocation flushes
the dynamically mapped stub as required. ARM64 StubPrecode loads its target
and secret parameter before branching:
`src/coreclr/vm/arm64/thunktemplates.S:124`. The interpreter entry stub receives
the bytecode address in the MethodDesc/secret register:
`src/coreclr/vm/arm64/asmhelpers.S:671`.

An opaque method slot and a stable callable entrypoint are distinct contracts;
`src/coreclr/vm/method.hpp:1609` explicitly warns that copying a method slot is
not generally an API for acquiring a callable address. This alone does not
prove the CID target is wrong: the resolver's prestub check and the executable
precode machinery must be considered. The full-harness trace address was not
individually classified in its original process; subsequent reduced-fixture
capture classifies the same dispatch/precode path, as recorded below.

The trace-run IPS does narrow the native failure: `pc=far=0`,
`EXC_BAD_ACCESS / KERN_INVALID_ADDRESS`, and ESR `0x82000006` describes an
instruction-abort translation fault. The first native caller is
`MapRunner.Run+776`; `lr=0x15906ada8`. Registers retain `x13=0x14baec030`,
exactly the traced nonzero target, and `x11=0x15c3f8e60`, the OnTick CID cell,
while `x10=x12=0` and `x9=0x14ba7d620`. Original and diagnostic-off IPS reports
also have a nonzero `x13`, zero `x10/x12`, and zero PC. These are observations
from `compare-20261012T134720Z/*-crash.ips`, not a live memory inspection.

The register state fits a cached branch to StubPrecode which loads zero
Target/SecretParam and then executes `br x10`. It does not fit an immediately
null cached target in `x13`. The reduced fixture subsequently confirms this
sequence by disassembling its resolved address and reading actual literal-load
destinations. The full-harness address is at offset `0x30` in a 16 KiB page, consistent with
slot 2 of the Apple 24-byte precode template. This arithmetic alone does not
classify an executable page. A null interpreter routine would instead require
examining InterpreterStub's `blr x11` and established transition frame; the IPS
retains the dispatch-cell value in `x11` and the direct MapRunner return address.

### ARM64 register contract

`src/coreclr/vm/arm64/asmconstants.h:61` defines the method/secret register as
`x12`. The scratch-register use is valid when the target is initialized precode:

| Stage | x9 | x10 | x11 | x12 | x13 |
| --- | --- | --- | --- | --- | --- |
| Fast CID probe | Cache pointer | Receiver MethodTable | Dispatch cell | Cached MethodTable | Cached target |
| Slow CID return | Resolved target | Scratch | Dispatch-cell/worker scratch | Restored/scratch | Scratch |
| Stub/InterpreterPrecode | Unchanged | Loaded native Target | Unchanged | Loaded SecretParam/bytecode | Unchanged |
| InterpreterStub | Method/callstub/stack pointers | Callstub routines | Thread context, then first routine | Bytecode copied to x19 | Scratch |

The fast stub preserves argument registers `x0-x8`; the slow stub saves and
restores them with its transition block. Apple StubPrecode's three instructions
are `ldr x10, Target; ldr x12, SecretParam; br x10`
(`src/coreclr/vm/arm64/thunktemplates.S:33`). InterpreterPrecode data has bytecode
at offset 0, target at offset 8, and type `0x06` at offset 16
(`src/coreclr/vm/precode.h:311`). InterpreterStub copies `x12` to `x19`, preserves
`x0` through the Apple thread lookup, and invokes the generated callstub routine
with `blr x11` (`src/coreclr/vm/arm64/asmhelpers.S:671`). Thus a fast probe
overwriting `x12` with a cached MethodTable is not itself evidence of secret
argument loss: initialized precode replaces it before the interpreter entry.

There is also a source-visible lifetime concern independent of the current
SIGSEGV mechanism. CID cache storage comes from the global LoaderAllocator
(`src/coreclr/vm/CachedInterfaceDispatch_Coreclr.cpp:12`). Discarded cache blocks
are recycled at GC (`src/coreclr/runtime/CachedInterfaceDispatch.cpp:356`); this
reclamation is not a sweep of every live mapping to an unloaded MethodTable.

LoaderAllocator destruction suspends the runtime, flushes other resolution
caches, destroys the unloading allocator's virtual call stub manager and clears
the interpreter dispatch cache:
`src/coreclr/vm/loaderallocator.cpp:646`. The CID manager teardown discards caches
belonging to that manager's own indirection-cell blocks:
`src/coreclr/vm/virtualcallstub.cpp:713`. That does not visibly invalidate a
mapping held by a longer-lived host/R2R cell pointing to a shorter-lived script
MethodTable and its precode. The ordinary VSD path separately detects calls to
shorter-lived targets at `src/coreclr/vm/virtualcallstub.cpp:1911`.

Apple precode teardown actually deallocates both mapped code and data pages:
`src/coreclr/utilcode/interleavedloaderheap.cpp:78` calls
`FreeThunksFromTemplate`, whose Apple implementation uses `vm_deallocate` over
twice the template size (`src/coreclr/minipal/Unix/doublemapping.cpp:632`).
The reduced live capture establishes unmapping followed by address reuse,
described below. The backout path zeros
an individual data slot at `interleavedloaderheap.cpp:402`; that separate path
must not be described as the normal allocator destructor.

The invariant for any accepted CID cache policy is: a cached MethodTable and
callable target remain valid for every possible cache hit, including entrypoint
updates and collectible LoaderAllocator retirement; publication must also
preserve the method's native calling convention and argument state. Global
storage allocation does not itself extend the lifetime of its raw pointers.

## What the one trace proves

The diagnostic prints only when `patch` is true and prints before cache
publication. Thus one trace followed by a crash does not identify the failing
machine instruction, a cache hit, or an unload event. Two plausible timings
must be distinguished:

- Cold tick 1 resolves without caching and compiles the interpreted method;
  tick 2 traces and attempts the first publication. A crash can happen during
  allocation, pointer-pair publication or that invocation.
- If tick 2 completes, tick 3 can be the first direct cached hit. A crash then
  can occur while the first session is still alive, before OnStop/Unload/GC.

The failing harness begins with twenty repeated sessions, each with three
ticks. Its first test pass line appears only after all twenty sessions, so the
absence of that line cannot identify the particular session or prove that
unloading happened. The original trace therefore required a reduced probe with
explicit callback/stop/unload markers; its measured follow-up appears below.

Subsequent reduced-fixture measurements distinguish these timings. With an
unchanged R2R callsite, original/diagnostic-off/trace runtimes pass the first
single session with 1, 2, or 3 ticks. Twenty one-tick sessions with collection
also pass. Twenty two- or three-tick sessions with collection crash at the
first tick of session 2: the first session returned, requested unload, and
reported collection. Twenty retained three-tick sessions, and twenty unloaded
three-tick sessions without forced collection, pass. Cache-skip mode passes the
collected sequences. These measurements localize the reduced fixture to a
post-collection cached mapping; they do not identify the exact failing session
of the separate full harness. The minimal driver is
[`eng/ios-r2r-minimal.py`](../eng/ios-r2r-minimal.py); its run-specific evidence
is maintained in the [investigation record](ios-r2r-investigation.md).
The verified remote matrix is
`ios-r2r-minimal-20261012T1500Z/run-20261012T150004Z/results-verified.json`
under the configured experiment root. It records 40 groups: 34 passed and six
expected original/off/trace SIGSEGV controls; all 16 skip/IL groups passed.
`original-twenty-two` and `trace-twenty-two` are the two-tick collected-session
controls; `original-collect-three` and `trace-collect-three` use three ticks.

### Native debugger checks

The [live minimal capture](ios-r2r-minimal.md) now supplies native classification
in `artifacts/ios-r2r-investigation/20261012-minimal/capture-20261012T151013Z`.
Direct-frame JSON is the register source; the first two textual callback dumps
can refer to LLDB's selected thread instead of the breakpoint thread.

| Snapshot | Receiver MT | Original cached MT | Original target | Precode data |
| --- | --- | --- | --- | --- |
| First live hit | `0x1057910f8` | `0x1057910f8` | `0x107f80030` | x10 target `0x104c9004c`, x12 bytecode `0x105760218` |
| Later receiver | `0x107fb90f8` | `0x1057910f8` | `0x107f80030` | Original target address unmapped |
| Native fault | `0x1057910f8` | `0x1057910f8` | `0x107f80030` | Both literal-loaded pointers zero |

The captured precode is `ldr x10, 0x107f84038; ldr x12, 0x107f84030; br x10`.
At the fault the code mapping is RX, its data mapping RW, the cache retains the
initial MT/target pair among four entries, and receiver MT equals the reused
original address. Registers are `x13=0x107f80030`, `x10=x12=pc=0`, with the
trusted caller return at `CallSite+456`. This establishes stale mapping plus
address reuse and a null precode branch in the reduced fixture. The debugger
changes allocation timing: its later failure is not the non-debugger matrix's
session-2 timing, and it does not supply the original full-harness crash's exact
session number.

The following checks remain useful when extending the reproduction or reviewing
a different runtime build; they describe the capture recipe, rather than
evidence still missing from the measured minimal case.

At the stopped null-PC fault retain `register read x0 x9 x10 x11 x12 x13 x19
x22 x23 lr pc sp fp` and `thread backtrace`. Classify `x13` with
`memory region $x13` and `disassemble --start-address $x13 --count 6`. Read the
dispatch cell with `memory read --size 8 --format x --count 2 $x11`; use the
compiled cache layout to capture the pointed-to header and `(MT,target)` pair.
Compare that cached MT with the new receiver's first pointer at `x0`, and retain
first-session addresses before allocator retirement to prove address reuse.

For a confirmed Apple 16 KiB StubPrecode template, read the paired data at
`x13+0x4000`: bytecode/secret at +0, native target at +8, type byte at +16. Prefer
decoding the literal-load addresses from the actual instructions over assuming
the mapping. Capture permissions and contents before unload, after collection,
and during the second session. Step the fast stub's `br x13` and precode's
`br x10`, or set address breakpoints, to identify the actual zero branch. If
InterpreterStub is reached, validate `x12/x19` bytecode and the callstub/context
pointers before its `blr x11`. Changing target representation or register choice
without this evidence would be speculative.

## Small candidate and required regressions

A conservative candidate policy is to avoid publishing collectible instance
MethodTable mappings into CID caches until their lifetime/entrypoint contract is
implemented. Retain normal resolution and immediate invocation, and leave
noncollectible caching unchanged. The diagnostic's switch-1 result demonstrates
that this branch can recover the full failing harness on the measured Debug
configuration. It does not establish the precise root cause or production cost.

A narrower later policy can retain mappings only when cache/callee ownership
is compatible, or register/sweep shorter-lived mappings during allocator
retirement. That requires an explicit ownership mechanism; updating discarded
cache free lists alone is insufficient. A blanket stable-entrypoint substitution
also requires validation of target decoding, loader lifetime and ABI.

Before accepting a runtime patch, cover single-session cold/publication/hot-hit
calls; many sessions with GC/address reuse; exceptions and cleanup; value-type
arguments and returns; inherited/default interface implementations; generic
interfaces and constrained calls; noncollectible cache behavior; and concurrent
cache publication where supported. Run relevant upstream tests plus RuneCLR's
lifecycle and controlled-package suites against private patched outputs, retain
positive interpreter dumps, and verify that the original negative control still
reproduces under the same package layout. Keep a dedicated runtime branch/commit
and record the base, patch and measured configuration separately.

This analysis does not change the [accepted execution strategy](execution-strategy.md),
demonstrate physical-device iOS acceptance, or provide hostile-code isolation.
