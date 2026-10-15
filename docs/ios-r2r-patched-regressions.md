# Patched iOS simulator interface regressions

On 2026-10-12, the v2 [CID lifetime candidate](ios-r2r-fix-candidate.md)
passed **4/4 explicit interface regressions** and **2/2 unchanged upstream
source-adapter tests** on the Debug ARM64 iOS simulator. The four interface
cases completed eighty collectible-context retirements and 240 callbacks.
Original and trace-only native controls used identical managed assemblies and
the same trusted R2R composite: three cases crashed after retirement, while
the default-interface case stalled and reached the bounded launcher timeout.

This supplements the [independent lifecycle/package acceptance](ios-r2r-fix-validation.md)
and [original investigation](ios-r2r-investigation.md). It does not establish
physical-device support or an upstream-approved fix.

## Explicit CID cases

Each case runs a fresh process, twenty fresh collectible contexts, and three
interface calls at one no-inline trusted host callsite per context. The host
shares `RegressionContract` with the collectible plugin, requests unload only
after the execution stack returns, and observes completed collection through
weak references and diagnostic GC. Plugin counters reset in every context.

| Case | Callback coverage | Original runtime | Trace-only runtime | V2 candidate |
| --- | --- | --- | --- | --- |
| `values` | Readonly `Tick(int, TimeSpan)` argument and `long` return | SIGSEGV on context 2, call 1 | Same SIGSEGV; one CID record | 20 contexts collected, 60 calls returned |
| `defaults` | Shared interface implemented by an inherited collectible default-interface implementation | Context 2, call 1 stalls; 120-second timeout | Same sampled timeout; one CID record | 20 contexts collected, 60 calls returned |
| `generic` | Closed `IGeneric<int>` interface dispatch | SIGSEGV on context 2, call 1 | Same SIGSEGV; one CID record | 20 contexts collected, 60 calls returned |
| `exceptions` | Author exception on call 2, trusted catch, call 3 recovery | SIGSEGV on context 2, call 1 | Same SIGSEGV; one CID record | 20 contexts collected, 60 calls completed, 20 exceptions caught |

Every negative control completed and collected its first context, then recorded
four before-call markers and three after-call markers. The trace-only variant
uses diagnostic value `2`, which records `RUNECLR_CID_RESOLVE skip=0` without
skipping cache publication. All four cases therefore exercise CID in that
control. The candidate uses its default publication guard with no diagnostic
cache switch.

The two default-interface stalls have separate one-second native stack samples.
The worker stack reaches an unknown native address beneath R2R
`RegressionDriver.Cycle`; neither log reports SIGSEGV. The driver terminates
each owned app after the bounded launch. This is evidence of a retirement-related
stall in these inputs, not a resolved attribution of the sampled instruction.

Every candidate case has sixty before/after markers and twenty successful
`Compiled method:` dumps for the actual callback, one per fresh context. The
forty general plugin/default-method dumps per case include constructors and
must not be reported as forty callback dumps. An anchored method-name parser
avoids counting method names embedded as string literals in IR.

`RegressionDriver.Values`, `Defaults`, `Generic`, and `Exceptions` have native
symbols in `regression.dylib` and no interpreter compilation notice. The host
PE has a managed native header; the plugin is IL-only with no native header
and remains outside the composite. Positive successful callback IR establishes
interpreted plugin execution; ALC loading and environment configuration alone
do not provide that evidence.

## Related upstream source adapters

The existing `ResolvedFromDifferentContext` adapter completed its original four
scenarios; `GenericVirtualMethod` completed ten cycles. The candidate run reports
`UPSTREAM_SUITE_PASS tests=2`, managed exit 0 and successful CoreCLR execution.
The adapter's managed inputs are copied unchanged from the preserved prior
source-adapter experiment and checked during preparation.

These are related upstream sources with an existing simulator adapter, not the
official generated upstream runners. They do not independently prove that a
collectible CID cache entry was used. The four explicit cases above supply the
CID trace controls. The [16/16 official Windows executions](ios-r2r-upstream-validation.md)
remain separate unpatched desktop evidence.

## Source and input identity

| Identity | Recorded value |
| --- | --- |
| Upstream base | `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` |
| Candidate branch | `runeclr/iossim-cid-collectible-fix-v2` |
| Candidate commit | `8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d` |
| Configuration | `iossimulator.arm64.Debug` |
| Runtime report | `.NET 12.0.0-dev`, `compiled=False` |
| Source build SDK | `11.0.100-rc.1.26420.103` |
| Simulator | iPhone 17, iOS 27.0; macOS 27.0.1 ARM64 host |
| Candidate unsigned CoreCLR SHA-256 | `475e10c45d81c62d212a631dc6fc61ea6a40dcaf369fa97a3870426b1ec8c438` |
| Candidate signed bundle CoreCLR SHA-256 | `e6722b9e4a1122da5d1e7a9917a1c185c1ddd1b445fe2fe93e04d31f2f9645b5` |
| Candidate patch SHA-256 | `43b36606fa94967e97f2640e8d76dcfa8f0af21eeb77a065a0eea5c83c915857` |
| Trusted custom composite SHA-256 | `fae890d9c24d5de12f5a00e3825d34d2c9472cfcbb7aa8501fa1131f6c790492` |

Matching source framework libraries and source crossgen2 build the trusted
contract/entry/host composite. The wrapper loads the framework composite and
custom composite before running the host. `state.json` records framework,
source, PE-layout and assembly hashes, native input and signed-library hashes,
and bundle IDs. All 197 managed files and the custom composite are byte-identical
across original, trace-only and candidate apps. The verifier compares the
candidate unsigned input with signed bundle file-backed Mach-O sections.

The candidate source has no tracked changes before or after validation. Its
private native library comes from the recorded incremental build: APFS clones
of matching Debug objects, one VM source rebuilt and relinked, 2,715 objects
unchanged. This run does not establish a clean full build; any later clean-build
acceptance needs its own input identity and results. No runtime source was
edited by this regression lane, and installed runtimes remain untouched.

## Reproduction and evidence

[`eng/ios-r2r-patched-regressions.py`](../eng/ios-r2r-patched-regressions.py)
provides `build`, `run`, `verify`, and `archive` phases on the configured Mac.
It uses the existing [package verification helper](../eng/verify-ios-packages.py).
Choose a new output directory for a new build; existing inputs are preserved.

```sh
ROOT=/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr
CANDIDATE=$ROOT/ios-r2r-fix-v2-20261012
OUT=$ROOT/ios-r2r-patched-regressions-20261012/run
python3 eng/ios-r2r-patched-regressions.py verify \
  --root $ROOT --candidate $CANDIDATE --output $OUT
```

The retained run reports:

```text
PASS v2: 4 CID cases + 2 unchanged upstream source-adapter tests
PASS v2 CID regressions 4/4 + unchanged upstream adapters 2/2; native callers, CID trace controls, input identities and simulator shutdown verified
```

Remote experiment: `$ROOT/ios-r2r-patched-regressions-20261012/`. Local evidence:
`artifacts/ios-r2r-patched-regressions-20261012/`. The 150,700-byte
`evidence.tar.gz` archive has SHA-256
`a46bd0b9a55f4dceaeb1aa99e8ba6a740a7504b38b8aecb40269de1d971746a9`;
the downloaded copy matches. It preserves generated sources, original input
DLLs, response file, wrapper, logs, samples, input inventories, result JSON,
verified JSON, simulator state and driver snapshots. Native apps and framework
binaries remain in the private remote output rather than the small archive.

The dedicated simulator `961478E3-120C-4B73-AC1A-92E454E6439F` was shut down
in the driver's final cleanup, and a subsequent `simctl` query confirmed
`Shutdown`. These results do not measure dispatch cost, Release/Checked behavior,
physical iPhone execution, or a hostile-code sandbox.
