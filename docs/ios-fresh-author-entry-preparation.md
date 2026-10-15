# Fresh Author Simulator Entry Capture Preparation

The subsequent [live simulator acceptance](ios-fresh-author-entry-acceptance.md)
now records nine actual method groups, 15 cases/73 collections and successful
target exit/cleanup. It corrects the ordinary-child opcode advance to0 in a
separate versioned live driver. The frozen drafts and pending statements below
describe historical offline preparation, not the latest live result.

On 2026-10-15, the separately accepted scene-aware simulator application has
a [debugger-free fresh-IL run](ios-fresh-author-simulator.md) of fifteen cases
and73 collected contexts. This record covers subsequent offline sampler
preparation only. No new simulator was created, application installed or
launched, or live debugger attached for this preparation.

## Ordinary Child Dispatch Contract

The [capture draft](../eng/ios-fresh-author-entry-capture.py) reads the matching
Release native image, DWARF and source without creating a target process.
Function entry alone cannot cover the requested nine groups: `ReInit` can
switch to another interpreted method inside the same `InterpExecMethod` loop.
The ordinary CALL child path therefore needs its own observation point.

The frozen plan2 contract binds source line3784 and file PC `0x2e7b0c`, with
frame spill `x19+0x98`, opcode pointer `x9` and first opcode register `w8`.
Actual native instruction bytes bind the frame store, bytecode header skip
and reload. The contextual DWARF interval `[3046104,3046144)` excludes the
capture PC; the frame location relies on the checked instruction window and
unchanged base register, rather than a claim that DWARF directly covers it.
Live register contents remain unverified.

The owner chain is `Module -> PEAssembly -> CustomAssemblyBinder`: actual
DWARF binds the80-byte PEAssembly's binder pointer at72 and the344-byte
CustomAssemblyBinder's embedded meter at272. The synthetic decoder validates
loaded metadata MVID, author path/token, bytecode owner and definition-owned
meter gate, with both flat and RVA-mapped PE layouts.

Receipts are retained at
`D:/RuneCLR-Android/device-build/fresh-author-entry-capture-plan-receipts-20261015-attempt1`.
`extracted/plan` contains raw source/DWARF/instruction receipts and the plan;
`extracted/frozen-tools/controls-plan2.json` passes36 synthetic controls.
These include decoder/reviewer acceptance, prefilters and rejection cases;
they are not36 captured runtime entries or nine-group execution evidence.
The plan's driver SHA256 is
`b8953d80a49dc05f3b5ccc6bfabe5b16f264c73b2dc60a5e547f4930d56678ad`,
and its generated observer SHA256 is
`e839b05b365b2f4835be73f3d31dd9f4b44074a30f782ee1ac2cd2eb31c4c5f3`.
The complete helper snapshot is preserved under `source-freeze/eng`.

The [independent offline reviewer](../eng/review-ios-fresh-author-entry.py)
passes12 controls against the actual ordinary-child native/source/DWARF
contract and current blocked draft. Its result is
`D:/RuneCLR-Android/device-build/fresh-author-entry-offline-independent-review-20261015-attempt2/results.json`,
SHA256 `0b4f35f3d73802f6904ae7bda7b814f298997dbf0000f6d7d585f6b6592a429d`.
Reviewer source SHA256 is
`220f2fc7ca237f31cdf5606f5c01dc446244eed5571d124285a97c5836d8a8cf`;
the frozen current draft is
`bc922779f4a64b83ca69b6b5dd1f13a9f842277e9b7f60226910508c6f1d779a`.
Both sources and the result are retained in the passing review directory.

## Remaining Capture Work

The current draft has `CAPTURE_READY=False` and two explicit pending contracts:

- Delegate child dispatch at the current source line3667 needs a separate
  native/DWARF/register contract and observer path.
- `FiniteCleanup.OnTick` calls private `Helper.Finite` from `finally`; that
  helper invokes the private Action closure. Both private groups need
  cleanup phase1 binding, instead of the draft's phase0-only gate.

The current synthetic cleanup-phase rejection documents this limitation; it
does not establish that cleanup samples are supported. The false readiness
gate rejects installation, launch and attach, even if a copied plan claims
readiness. The run rejection path still permits failure cleanup of an already
owned target; the guard controls stub that cleanup and do not prove a general
absence of cleanup operations. This preparation has no owned diagnostic target.
Keep capture disabled until both paths are implemented and independently reviewed.
The current draft differs from the frozen plan2 driver; regenerate and bind
the plan after the draft is completed. Bounded container/device queries and
plan-bound diagnostic timeouts are part of the subsequent draft.

## Phase-Aware Draft Review

The next draft adds separate function-entry, ordinary-child and delegate-child
paths, and maps only `Helper.Finite` plus its closure to cleanup phase1. The
delegate contract is the distinct file PC `0x2e6df8` (source line3667), with
`x26` and a pre-index `ldr w8,[x26,#8]!`; ordinary child remains file PC
`0x2e7b0c` (line3784) with `x9`. Both paths retain the `x19+0x98` frame spill.
The thread-context layout is 88 bytes with `pStackPointer` at16 and
`runeclrCleanupOwner` at80; raw and derived spill slots are checked separately.

The independent [v2 source reviewer](../eng/review-ios-fresh-author-entry-v2.py)
passes17 source/config checks and10 mutation controls. Its final result is
`D:/RuneCLR-Android/device-build/fresh-author-entry-v2-config-review-attempt6.json`,
and the driver SHA256 is
`c9d6f483c22559e9629bc8a801619421ad3b7fa447484162446d2368fd0f559b`.
The read-only plan result is
`D:/RuneCLR-Android/device-build/fresh-author-entry-v2-plan-20261015-attempt6/results.json`.
It binds all three path names, the 9-method phase map and the thread layout;
the function-entry prefix is sourced from the frozen instruction receipt, while
ordinary/delegate live native prefixes remain explicitly unbound. `CAPTURE_READY` remains false;
the plan is not live method-entry evidence and no target was created, installed,
launched or attached.

The subsequent native-only binding reads the same ARM64 image at all three file
PCs. Its native SHA256 is
`b0670a7604bd8857409f1ea9ac543f293c99047286f6f762d0eb720ca6f877ae` and
UUID is `b475d28282de361c9faefdf40c3ad5c0`. The 64-byte windows and
offsets are retained at
`D:/RuneCLR-Android/device-build/fresh-author-entry-v2-native-bind-attempt1`;
the independent config review there passes all path/ABI and mutation checks.
This is static native-byte evidence only. It does not prove a loaded image,
live registers, method execution or cleanup-phase entry.

After that review, create a separate owned diagnostic simulator and verify
installed host bytes and an absent author directory. Compile another fresh
author pair only after that installation readback, then bind delivery and
sample all nine groups through function entry, ordinary child and delegate
child paths with the correct execution/cleanup phases. Require actual target
exit, all fifteen cases/73 collections, unchanged installed inputs and owned
simulator retirement. Preserve the accepted debugger-free run and prior
author pairs. Physical-device execution remains a separate
[readiness and signing gate](ios-device-readiness.md).
