# Official managed CoreCLR tests on the patched iOS simulator

On 2026-10-12, four unchanged official CoreCLR test projects and their official
generated standalone `Main` entrypoints passed on the patched Debug ARM64 iOS
simulator. Each test returned managed exit 100 with successful CoreCLR
execution, positive interpreter dumps for its collectible payload, and no
native fault. The independent verifier records `success=true` and all checks
true in `apps-ios/verified.json`.

This advances beyond the earlier
[two upstream source-adapter executions](ios-r2r-patched-regressions.md): the
managed entrypoints here come directly from the upstream generator and retain
the upstream conditions/assertions. Packaging and launching still use RuneCLR's
private native simulator wrapper. This is not a completed upstream XHarness
or Helix lane, a full upstream suite, Release acceptance, or physical-device
evidence.

## Four executed projects

All paths below are under `src/tests/Loader/CollectibleAssemblies` in the
isolated candidate worktree.

| Project | Actual payload evidence | Result |
| --- | --- | --- |
| `GenericVirtualMethod/GenericVirtualMethod.csproj` | Ten `.DerivedMachine:Construct[System.__Canon]()` dumps, one per upstream load/unload iteration | Official `Main` exit 100 |
| `Statics/CollectibleStatics.csproj` | One dump each for `StaticTest.SetStatic`, `GetStatic`, `SetStaticObject`, and `GetStaticObject` | Official `Main` assertion accepted exit 100 |
| `ResolvedFromDifferentContext/ResolvedFromDifferentContext.csproj` | Two `.TestClass.Class:MainTest()` dumps in the positive scenarios | Official `Main` assertion accepted exit 100 |
| `ByRefLocals/ByRefLocals.csproj` | `SpanAccessor.GetSpan` body, emitted `GetSpanType.GetSpan` compilation, and twenty loop outputs | Official `Main` assertion accepted exit 100 |

The verifier uses anchored method-name parsing to separate actual method dumps
from names appearing inside IR strings. Broader payload dump counts are 30, 7,
4 and 3 respectively; these include constructors or helpers and must not be
reported as callback counts. The original test assertions and collection
checks execute through their official `Main`; the evidence does not run every
other project in the same source directories.

The trusted test entry methods have native symbols in each `official.dylib`,
and their names have no interpreter compilation notice. The packaged entry
assembly has a managed native header. Collectible payload assemblies remain
outside that trusted composite; positive payload dumps establish their
interpreted execution. These tests supplement the explicit CID controls and
dynamic-interface-owner regression; they do not independently prove that
every test dispatched through the affected collectible CID cache entry.

## Simulator alias and skipped-body trap

The first successful project compilation used `TargetOS=iossimulator`.
Inspection of its preserved generated `SimpleRunner.g.cs` exposed a generator
alias omission before accepting that configuration as execution evidence.
At the pinned source,
`src/tests/Common/XUnitWrapperGenerator/XUnitWrapperGenerator.cs:1198`,
`GetPlatformForTargetOS` maps `ios` to `Xunit.TestPlatforms.iOS` but has no
`iossimulator` entry; an unrecognized value returns zero.

`DecorateWithSkipOnCoreClrConfiguration` at line 1042 combines the target
platform with the skipped-platform mask. For `GenericVirtualMethod` and
`ResolvedFromDifferentContext`, the resulting generated GC-stress condition is:

```csharp
if (!TestLibrary.CoreClrConfigurationDetection.IsGCStress && (false))
```

That condition skips the body, while the standalone generated wrapper can still
return 100. Exit 100 by itself therefore cannot establish these test executions.
The simulator-target generated files are retained in `iossimulator-generated/`;
they are not counted as passing payload executions. This identifies an upstream
generator alias issue at this revision; the runtime and generator source were
not edited to bypass the condition.

The final managed project build uses `TargetOS=ios`, retaining the upstream
generated runner unchanged. Its condition becomes:

```csharp
if (!TestLibrary.CoreClrConfigurationDetection.IsGCStress
    && ((System.OperatingSystem.IsIOS() && !System.OperatingSystem.IsMacCatalyst())))
```

The actual native target and execution platform remain **ARM64 iOS simulator**:
crossgen2 uses `--targetos:iossimulator`, native compilation uses
`arm64-apple-ios15.3-simulator`, and execution uses an iOS 27.0 simulator.
`TargetOS=ios` describes the managed generation configuration here, not a
physical-device run. Final verification requires `generatedFalseCondition=false`
and the specific positive payload evidence for all four tests.

## Official managed build and private packaging

The isolated test worktree is at the candidate commit, tracked-clean. SDK and
baseline managed/native artifacts are privately APFS-cloned, and native runtime
inputs are replaced with the separately verified fresh Debug candidate. No
installed runtime or baseline artifacts are changed. The project build uses
the official `dotnet.sh` entry point, restores test dependencies, builds the
external targeting pack and builds the four unchanged projects with:

```text
-p:Configuration=Debug
-p:TargetOS=ios -p:TargetArchitecture=arm64
-p:RuntimeFlavor=coreclr -p:LibrariesConfiguration=Debug
-p:BuildAsStandalone=true -p:CLRTestPriorityToBuild=1
-p:EmitCompilerGeneratedFiles=true -p:BuildTestsOnHelix=false
-p:EnableAggressiveTrimming=false -p:PublishTrimmed=false
```

`BuildAsStandalone=true` selects the official simple managed runner, rather
than the merged XHarness runner. Upstream test source, generated `Main`, test
dependencies and payload inputs remain unchanged. A custom trusted R2R
composite compiles the test entry assembly and its shared contract assemblies;
the existing UIKit/CoreCLR wrapper invokes the assembly's actual managed entry
point. It does not replace `Main` with a custom managed source adapter.

Earlier build attempts are preserved: `restore` rejected `-c Debug` with
`MSB1001`, and the next project build needed the external targeting-pack
attributes. The final driver supplies `-p:Configuration=Debug` and builds that
pack explicitly. A first crossgen attempt used the same PE as input and rewritten
output and failed with `System.AccessViolationException`; the preserved
`failed-inplace-crossgen.log` is compiler-stage evidence. Successful packaging
reads a separate `original-input` copy and writes the app's component PE. It
does not convert that failed attempt into runtime-test evidence.

## Identity and retained evidence

| Item | Recorded value |
| --- | --- |
| Upstream base | `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` |
| Candidate commit | `8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d` |
| Fresh Debug unsigned CoreCLR SHA-256 | `e97efd27370d02b6767bbaa1e4cb968f92fa3341d53e345626ff6f8498f572d8` |
| Signed app CoreCLR SHA-256 | `42169c19acc54dafbbd5ed1ee15e1530a780c57582e58d8e990b9bcee7063877` |
| Source SDK | `11.0.100-rc.1.26420.103` |
| Managed build target | `ios.arm64.Debug`, standalone official runner |
| Native/run target | `iossimulator.arm64.Debug`, iPhone 17 / iOS 27.0 |
| Dedicated simulator | `00DECE13-CFCD-4BBA-B24A-117A59374933`, verified `Shutdown` |

The independent verifier checks unchanged official source and generated `Main`
hashes, actual payload execution, native caller symbols, input/composite
identities, signed versus unsigned file-backed Mach-O sections, clean candidate
and test worktrees, and shutdown of the owned simulator. `state.json` records
per-test managed input, generated entrypoint, signed native and composite hashes;
`results.json` records the four launcher exits, managed exits, dump counts and
log hashes.

The implementation is split between the
[official project build driver](../eng/ios-r2r-official-patched-tests.py) and
[managed-entry packaging/verification driver](../eng/ios-r2r-official-managed-runner.py).
The retained verifier reports:

```text
PASS 4/4 official generated managed entrypoints on patched Debug ARM64 iOS simulator; actual payload IR, native hosts, unchanged source/input identities and simulator shutdown verified
```

Remote root:
`/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/ios-r2r-official-patched-tests-20261012`.
Archive: `official-managed-evidence-ios.tar.gz`, 467082 bytes, SHA-256
`05eabfd1fbd2fb4f2c432a10e2b29b8b35d9453d279c514e365c11a69c012e71`.
The exact archive is downloaded to
`artifacts/ios-r2r-investigation/20261012-official-managed/` and safely extracted
there. Thirty binary chunks preserve the exact bytes. All 257 members pass
relative-path/type checks before extraction; local checks confirm archive
size/hash, successful verification, four log identities, generated `Main`
identities and positive execution results. No tests are rerun for this archival
verification.

The archive preserves official sources, original managed inputs, both managed
generation configurations, response files, wrapper sources, symbol/dump logs,
build attempts and driver snapshots. Full app bundles and native framework
outputs remain in the private remote experiment. These results establish the
four official managed entrypoint executions with custom simulator packaging;
complete upstream XHarness execution, physical-device acceptance and upstream
review remain separate work.
