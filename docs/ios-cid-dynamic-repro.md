# Dynamic interface implementation retirement probe

[`eng/ios-cid-dynamic-repro.py`](../eng/ios-cid-dynamic-repro.py) creates a
focused simulator fixture for the explicit dynamic implementation-owner route
identified in the [CID candidate analysis](ios-r2r-fix-candidate.md). This is a
new RuneCLR regression fixture, not an unchanged upstream test adaptation.

The host owns a single noncollectible receiver implementing
`IDynamicInterfaceCastable`. Its shared `IProbe` contract is compiled with the
host. Each of twenty cycles loads a fresh collectible assembly containing a
`[DynamicInterfaceCastableImplementation]` interface and a default `IProbe.Tick`
implementation. The receiver holds that implementation Type only during three
calls at the same R2R host callsite. The implementation static counter must
return 1, 2, and 3 each cycle.

The call stack returns before collection. A `finally` clears the receiver's
Type field before unload. The outer driver forces diagnostic GC and requires
both the context and implementation Type weak references to die. The receiver
itself remains alive across all cycles. Logs record the receiver TypeHandle
address to verify that all calls use the same receiver MethodTable. This tests
both a noncollectible receiver with a collectible callee owner and removal of
the host's explicit Type reference.

The fixture compares original native CoreCLR, receiver-only candidate v1, and
collectible-or-dynamic-receiver candidate v2 with identical managed inputs,
framework composite, small R2R host composite and wrapper machine code. An
original-runtime IL-host control is recorded separately. The plugin stays IL
in all lanes. Interpreter compile and completed-bytecode dump lines for the
actual `Plugin` Tick implementation are required for a passing lane.

The driver reuses the pinned simulator framework and native wrapper sources,
compiling only the small fixture composite and wrapper. It preserves every
earlier candidate and experiment, refuses an existing output root, uses an
owned simulator, clears inherited diagnostic runtime environment variables,
and shuts its simulator down in a `finally`. Source, managed, composite and
native hashes are retained under `logs/identity.json`; signing provenance
connects candidate unsigned native inputs to their embedded signed libraries.

Run on the configured Mac:

```sh
python3 eng/ios-cid-dynamic-repro.py all \
  /Users/editor/RuneCLR-experiments/20261012-iossim-coreclr \
  /Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/NEW-DYNAMIC-OUTPUT
```

The build inputs and runtime candidates must already exist as documented in
[the candidate build record](ios-r2r-fix-candidate.md). Build and run can also be
invoked separately. `run/results-verified.json` records managed exit conditions,
60 completed ticks, twenty clear/unload/collection results, one receiver type,
interpreter evidence, native faults and simulator shutdown. Launcher exit 0
alone is not a successful execution.

The first experiment is under
`/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/ios-cid-dynamic-20261012T1550Z`.
That initial attempt asserts in all four lanes before the first callback:
`CrstNativeImageEagerFixups` level 21 is requested while
`CrstPendingTypeLoadEntry` level 20 is held. It therefore does not compare
dispatch lifetime. The first resolver evaluated `typeof(IProbe).Assembly`
inside collectible loading. The revised fixture caches that shared Assembly
before loading, and its resolver returns the cached value. This follows the
existing minimal fixture's shared-contract pattern and removes the observed
precondition failure without modifying runtime source or disabling assertions.
Both attempts and their exact source hashes are preserved.

## Measured result

The revised output is `ios-cid-dynamic-20261012T1550Z-retry1` under the same
experiment root. On 2026-10-12 its four lanes establish:

| Native / trusted caller | Result | Completed ticks | Cleared field and collected context/Type |
| --- | --- | --- | --- |
| Original / R2R | SIGSEGV on session 2 first Tick | 3 | 1 / 1 |
| Receiver-only candidate v1 / R2R | Same SIGSEGV | 3 | 1 / 1 |
| Collectible-or-dynamic candidate v2 / R2R | Managed exit 0 | 60 | 20 / 20 |
| Original / IL host | Managed exit 0 | 60 | 20 / 20 |

All four execute the actual collectible Plugin.Tick through the interpreter
before their respective outcomes. Each records exactly one receiver MethodTable
throughout its process. The passing lanes reset the plugin static counter in
every context, remove all explicit host Type references, collect both context
and implementation Type after return, and have no native fault or assertion.
This demonstrates why a collectible-receiver-only guard misses a noncollectible
receiver's collectible dynamic implementation. V2 avoids that mapping and passes
the tested topology. It does not establish all other runtime-cache lifetimes.

`run/results-reverified.json` is the final result: `success=true`, with simulator
shutdown confirmed and verifier exit 0. The initial counting code treated three
interpreter-dump string literals as completed IL-host callbacks (63 instead of
60). The current checker matches numeric Tick markers, and a separate
`verify` action recomputes the results from unchanged logs. The old
`results.json` and `results-verified.json` remain archived, alongside the final
reverified result and exact checker revision.

Evidence is downloaded and safely extracted under
`artifacts/ios-r2r-investigation/20261012-dynamic/`. The 136322-byte archive has
SHA-256 `79cf43414a09a6fba8cfe1a7288d143604ea46ae86de674525b1ab39fcdaa219`.
It includes both attempt sources, small managed fixture binaries, compile and
crossgen response files/logs, source/native identities, wrapper sources,
original/v1 crash reports, all run logs, old/final results and driver revisions.
Candidate worktrees are verified clean at their recorded commits. Both owned
simulators have shutdown exit 0.

Generic dynamic methods, concurrent receiver mutation and physical-device
execution are outside this focused probe.
