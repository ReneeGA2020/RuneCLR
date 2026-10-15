# Covariance and constrained-call boundaries on the iOS simulator

On 2026-10-13, the fresh Debug v2 CID candidate passed two additional interface
boundary cases on the ARM64 iOS simulator: covariant interface dispatch and
interpreted generic constrained calls to a collectible value type. Each case
completed twenty fresh collectible contexts with static-state reset and
observed context collection after the execution stack returned.

The controls differ by case. Covariant dispatch faults on the original and
trace-only runtimes after earlier contexts have been collected; constrained
value calls pass on all three runtimes. `verified.json` records `success=true`
for these actual outcomes rather than requiring every control to crash. This
supplements the [explicit interface regressions](ios-r2r-patched-regressions.md)
and [fresh Debug lifecycle acceptance](ios-r2r-clean-build.md).

## Measured outcomes

All three apps use identical managed assemblies, framework composite, probe
composite and native wrapper. Only native CoreCLR differs. Each runtime/case
combination launches a fresh process.

| Case | Original runtime | Trace-only runtime | Fresh Debug v2 |
| --- | --- | --- | --- |
| Covariance | SIGSEGV at context 4, first call; 3 contexts collected and 9 calls returned | SIGSEGV at context 2, first call; 1 context collected and 3 calls returned; one CID resolution record | 20 contexts collected; 60 calls returned |
| Constrained value calls | 20 contexts collected; 20 outer calls and 60 value steps returned | Same success; no CID resolution records | Same success; no CID resolution records |

Both covariance controls have a before-call marker without its matching
after-call marker at the fault. The original has ten before/nine after markers;
the trace-only runtime has four before/three after markers. They have no
managed assertion failure, launcher timeout or startup failure. The simulator
launcher reports exit zero even for these native faults, so log fault markers
and payload progress are required to interpret the outcome.

The trace-only run sets
`DOTNET_RuneCLRDisableCollectibleInterfaceDispatchCache=2`. It records
`RUNECLR_CID_RESOLVE skip=0`, preserving cache publication rather than applying
the fix. Its covariance record identifies the receiver MethodTable and target
at the native host callsite. The varying fault context across original and
trace controls must not be reported as a uniform second-context crash. This
lane does not contain a debugger capture attributing the precise faulting
instruction; the existing [minimal CID investigation](ios-r2r-minimal.md)
supplies that separate evidence.

## Covariant dispatch

The shared contract defines `IProducer<out T>`. A collectible plugin implements
`IProducer<string>`; the trusted host confirms both `IProducer<string>` and
`IProducer<object>` conversions, then makes three `Produce` calls through
`IProducer<object>` at the same no-inline native host callsite. Each result
must be a string with values `item=1`, `item=2`, `item=3`. The static plugin
counter must reset in every new context.

The candidate has twenty covariance-conversion markers, sixty paired call
markers, twenty returned/collected context markers, and twenty anchored
`.Plugin:Produce(...)` interpreter dumps, one per fresh context. Multiple calls
within one context reuse that compiled interpreter body. The host
`Driver.Variance` has a native symbol in the trusted R2R composite and no
interpreter compilation notice.

This case extends the lifetime regression to an interface variant conversion
with a reference return type. The positive conversion and result checks also
exercise ordinary semantics; they are not evidence for all generic variance
combinations or all dispatch implementations.

## Generic constrained value calls

The collectible plugin has a mutable `BoundaryCounter` struct implementing
`IValueStep.Next`. Its generic helper is:

```csharp
private static int Step<T>(ref T value) where T : struct, IValueStep
    => value.Next();
```

`Plugin.Run(3)` invokes that helper on the same local struct by reference three
times. The required values are 1, 2 and 3, with sum 6. An invocation counter
must reset to one in each collectible context; the outer host verifies the
returned value is 601. The host also records the helper's actual IL bytes.

All three runtimes produce twenty helper-IL records with a `constrained.`
opcode (`FE 16`, followed by its type token) immediately before `callvirt`
(`6F`). Each run has twenty `.Plugin:Run(...)` body dumps, twenty
`.Plugin:Step...` body dumps, twenty `BoundaryCounter.Next` interpreter
compilation notices, sixty step markers and twenty
`CONSTRAINED_RESET=1 SUM=6` markers. Each context returns and is collected.
The trusted `Driver.Constrained` caller has a native symbol and no interpreter
compilation notice.

This confirms preserved by-reference value mutation, interpreted constrained
execution, reset and retirement for these inputs. The trace-only run has zero
CID resolution records here, so it does not establish that the constrained
call exercised the affected cached-interface worker. Its passing original
control is useful semantic coverage and must not be recast as a fixed crash.

## Source and artifact identity

| Item | Recorded value |
| --- | --- |
| Upstream base | `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` |
| Fresh candidate commit | `8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d` |
| Native configuration | `iossimulator.arm64.Debug` |
| Runtime report | `.NET 12.0.0-dev`, `compiled=False` |
| Source SDK | `11.0.100-rc.1.26420.103` |
| Fresh unsigned candidate CoreCLR SHA-256 | `e97efd27370d02b6767bbaa1e4cb968f92fa3341d53e345626ff6f8498f572d8` |
| Signed candidate CoreCLR SHA-256 | `42169c19acc54dafbbd5ed1ee15e1530a780c57582e58d8e990b9bcee7063877` |
| Trusted probe composite SHA-256 | `f9ecb45cc9aed841b85746e82bad49100ef87a72cea15137fa5770eac8e4aad8` |
| Framework composite SHA-256 | `11e21475a182ecabe4045a251e30f4124b63d11ceb632e5dfd2ba7fde2565128` |
| Simulator | iPhone 17 / iOS 27.0, UUID `3654EAEE-A1F3-4BD8-ADEE-06C34D838709` |

`state.json` records all 189 shared managed-file hashes, each native input and
signed-bundle hash, composite identities, wrapper file-backed Mach-O section
hashes, source hashes and PE layouts. The trusted host has a managed native
header; the collectible plugin is IL-only with no managed native header and is
outside the composite. Build-time checks compare signed and unsigned native
sections. The verifier checks unchanged shared inputs, composites and wrapper
across the three apps, native caller symbols, actual log results and final
simulator `Shutdown` state. No runtime source is edited for these fixtures.

The host shares its contract assembly with the collectible context. It observes
collection through weak references after `Cycle` returns, using diagnostic GC
and finalizer waits rather than retaining plugin objects in host-owned results.
These measurements concern ordinary lifecycle and dispatch behavior; they do
not establish a hostile-code sandbox.

## Reproduction and archives

The [boundary driver](../eng/ios-r2r-interface-boundaries.py) supplies
`build`, `run`, `verify` and `archive` phases. It uses preserved private
[repro packaging](../eng/ios-r2r-repro.py) and
[iOS verification helpers](../eng/verify-ios-packages.py). Remote output:

```text
/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/ios-r2r-interface-boundaries-20261012
```

The existing results and independent verifier were checked before archival
work. No build or execution was repeated. The archive phase ran once after
confirming no prior archive existed. The full `evidence.tar.gz` remains remote:
10279805 bytes, SHA-256
`e87491277c8fe75b7d55236ab80e779f71a9bd9ea6abde8ab3de5e4779819e93`.
It includes the original managed DLL inputs.

A separate `compact-evidence.tar.gz` preserves logs, source fixtures, state,
results, verification, simulator state, response/wrapper files and driver/helper
snapshots, with original input DLL identities retained as hashes. It leaves
the full archive unchanged: 84121 bytes, SHA-256
`55baf21f78f1a463517b33d80f10c0fb0b67b85e940528d3cb8ed2c8b9559824`.
The compact archive is downloaded to
`artifacts/ios-r2r-investigation/20261012-interface-boundaries/` in six exact
binary chunks and safely extracted after checking all 67 members. Local checks
confirm archive size/hash, source/driver identities, successful verification
and independent reparsing of all six logs, including the different control
outcomes and constrained IL. The original DLL inputs remain in the remote full
archive rather than the compact local evidence.

Both boundary cases pass on this fresh Debug simulator candidate. They do not
measure performance, Release or Checked behavior, physical-device execution,
all variance/constrained cases, or upstream acceptance of the CID change.
