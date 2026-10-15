# Fresh Author Interpreter Entry Acceptance

The subsequent [open-delegate capture](ios-open-delegate-entry-acceptance.md)
adds actual delegate-special dispatch for the original closure while retaining
the same nine groups and15/73 harness. This page preserves the earlier
two-path result and its unchanged evidence.

On 2026-10-15, a separate owned iOS 27 ARM64 simulator passed the fresh-author
method-entry experiment. Both author DLLs were compiled after installation
readback of the unchanged trusted application. Nine selected method groups
were identified inside the CoreCLR interpreter, including private cleanup code.
The complete budget harness passed 15 cases and collected all 73 contexts.

## Measured Scope

The diagnostic target was PID 80284, nonce
`3ba590e886ee47e897cad3c152dae4e0`. LLDB observed target exit 0; six exact
native initialization/invocation/exit markers independently bind that PID and
nonce. The launch tool's exit is checked separately from the target exit.
Installed bundle/author inventories were equal before and after execution;
the original application stayed unchanged. Adapter receipts were copied out
before shutdown and deletion of the owned simulator. Cleanup passed.

| Author method group | Observed interpreter path | Meter phase |
| --- | --- | --- |
| Normal..ctor | Function entry | Execution 0 |
| Base..ctor | Ordinary child dispatch | Execution 0 |
| Normal.OnStart | Function entry | Execution 0 |
| Base.OnStart | Ordinary child dispatch | Execution 0 |
| Normal.OnTick | Function entry | Execution 0 |
| Base.OnStop | Function entry | Execution 0 |
| FiniteCleanup.OnTick | Function entry | Execution 0 |
| Private.Helper.Finite | Ordinary child dispatch | Cleanup 1 |
| Closure `<>c__DisplayClass0_0.<Finite>b__0` | Ordinary child dispatch | Cleanup 1 |

All nine samples bind loaded metadata MVID, MethodDef token, qualified method
name, installed DLL hash/path, collectible module, bytecode owner, definition
binder and embedded instruction meter. Cleanup samples additionally bind the
thread's cleanup owner, terminated execution budget and phase 1 reserve.
There were 16,432 breakpoint hits, nine retained groups and zero capture errors;
the breakpoints disabled after coverage. Hits are not instruction or invocation
counts. Sampling does not establish execution of every opcode or a full trace.

The delegate-special breakpoint was installed and its native bytes/layout
validated, but no retained author sample used that path. This fixture's closed
instance Action closure takes `CALL_INTERP_METHOD` and ordinary child dispatch.
The separate open-delegate branch remains a future fixture/entry test.
Physical-device execution remains pending.

## Corrected Live Contract

The immutable offline v2 planner is preserved. The separate
[live driver](../eng/ios-fresh-author-entry-capture-v2-live.py) versions its
correction as `v2-live-ordinary-current-opcode-1`. At ordinary child file PC
`0x2e7b0c`, native bytes `280140b9` are `ldr w8,[x9]`: the preceding code has
already advanced x9 to `bytecodeStart+8`. Its observer advance must be 0.
The delegate-special PC `0x2e6df8` has `488f40b8`, a pre-indexed
`ldr w8,[x26,#8]!`, and retains advance 8. Earlier diagnostic failures and
attempt8 are preserved; attempt8 lacked archived managed completion evidence.
Only attempt9 has the complete acceptance recorded here. This offset defect
was in RuneCLR's sampling contract, not a Microsoft runtime defect.

The live driver also binds plan/source/review hashes and timeout, validates
live breakpoint PID/UUID/bytes/layouts/slide, verifies managed recovery
semantics and input inventories, records the actual observer hash, and makes
cleanup failure fail the final run receipt. Its SHA256 is
`bba5e5625916702f506aa792f8a74e008adc5d1bb2e02984803c4157127a1d67`.

## Runtime And Evidence

This uses the existing [matching batch-capable Release build](mobile-batch-builds.md):
upstream `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`, runtime commit
`3126bbc9a8851a09ac6435b18a12882bad48f3ee`, tree
`710936ae1729a5689ab0e0896f3cf722ddd3d31c`. No runtime changes were made for
this capture. The unsigned native SHA256 is
`b0670a7604bd8857409f1ea9ac543f293c99047286f6f762d0eb720ca6f877ae`, UUID
`b475d28282de361c9faefdf40c3ad5c0`.

Configuration is InterpMode 0, InterpretCollectible 0, ReadyToRun 1,
phase-acquire-load 1, derived-ledger 1, batch interval 0 and tiering 0.
This is exact accounting on a batch-capable runtime, not another 100/1000
timing experiment. The compiler's `sanity` phase only produces fixed IL;
the live driver's separate timestamp, installed-byte and loaded-metadata
checks establish delivery after diagnostic installation.

The original remote lane is
`fresh-author-entry-v2-live-20261015-attempt9` under the experiment root.
The downloaded [evidence archive](../artifacts/ios-fresh-author-live/20261015-attempt9/evidence.zip)
is 254,883 bytes, SHA256
`ce6bb46fc81be38c96f3571e0d787d084e2267840ff1cdcc90fb785c765ba4bd`.
It includes raw debugger/native output, adapter receipts, freshly compiled
DLLs, frozen tools, before/after inventories, binding snapshots and cleanup.
The [portable local recheck](../artifacts/ios-fresh-author-live/20261015-attempt9/local-review-final.json)
passes against those actual bytes, including DLL MVID/token/IL-only metadata
and 13 semantic corruption controls on copies of actual managed results.
An independent [archive review](../artifacts/ios-fresh-author-live/20261015-attempt9/independent-review-controls-final.json)
also rejects 11 altered copies, including changed DLL bytes, target exit,
summary PID/nonce, thread contract, hit limit and simulator retirement.

Recheck the extracted archive without starting a target:

```sh
py -3 eng/review-ios-fresh-author-live.py --archive-root artifacts/ios-fresh-author-live/20261015-attempt9/extracted
py -3 eng/verify-ios-fresh-author-live.py
```

The second command passes 43 synthetic controls for exit/PID/hash/metadata,
terminal continuation, static reset, cleanup ownership, recovery, live plan
binding and cleanup-failure reporting. These controls are distinct from the
actual simulator execution. Preserve the accepted debugger-free
[fresh-author run](ios-fresh-author-simulator.md) alongside this diagnostic lane.
The next platform gate is [physical-device readiness](ios-device-readiness.md).
