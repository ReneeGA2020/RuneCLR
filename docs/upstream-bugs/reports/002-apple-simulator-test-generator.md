# [tests][Apple] XUnitWrapperGenerator skips conditional bodies for iossimulator TargetOS

### Description

`XUnitWrapperGenerator.GetPlatformForTargetOS` maps `ios` and `tvos` but
not `iossimulator` or `tvossimulator`. Unrecognized targets return the zero
platform mask. Standalone tests with platform/GC-stress conditions can generate
a literal false guard, skip their bodies and still return exit 100.

The official CoreCLR build infrastructure accepts simulator targets, and the
same generator recognizes simulator aliases in other branches. The omission is
in its target-to-platform-mask mapping.

This concerns standalone generation, separately from #134766's Apple launch
argument becoming a merged-runner filter. The desktop reproduction below
invokes the actual generator before any Apple launcher is involved.

### Reproduction Steps

Use a clean runtime tree at
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` and a .NET 11 SDK. This
source-linked probe compiles and invokes the **actual upstream generator**
with Roslyn, rather than substituting a copy of the mapping function.

~~~sh
git clone https://github.com/ReneeGA2020/RuneCLR.git runeclr-repro
git -C runeclr-repro checkout 13d6154860cdf7ea4b6389ae81f778f76d78f969
cd runeclr-repro

runtime_repo=/absolute/path/to/the/pinned/runtime
repro_out=/absolute/path/to/a/new/repro-output

dotnet build eng/apple-generator-regression/GeneratorProbe.csproj -c Release \
  -p:GeneratorRoot="$runtime_repo/src/tests/Common" \
  -p:BaseIntermediateOutputPath="$repro_out/obj/" \
  -p:OutputPath="$repro_out/bin/"

dotnet "$repro_out/bin/GeneratorProbe.dll" baseline \
  "$runtime_repo/src/tests/Common/XUnitWrapperGenerator" \
  "$repro_out/results"
~~~

The probe supplies these generator properties:

~~~text
build_property.TargetOS = ios | iossimulator | IOSSimulator | tvos | tvossimulator | TvOSSimulator
build_property.RuntimeFlavor = CoreCLR
build_property.InMergedTestDirectory = false
build_property.BuildAsStandalone = true
~~~

It includes an unconditional body and these conditional bodies:

~~~csharp
[Fact, SkipOnCoreClr("stress", RuntimeTestModes.AnyGCStress)]
public static void StressSensitive() { Bodies |= 1; }

[Fact, PlatformSpecific(TestPlatforms.iOS)]
public static void IOSOnly() { Bodies |= 2; }

[Fact, PlatformSpecific(TestPlatforms.tvOS)]
public static void TVOnly() { Bodies |= 4; }

[Fact]
public static void PlainControl() { Bodies |= 8; }
~~~

Inspect `iossimulator/SimpleRunner.g.cs` in the results directory and compare
with `ios/SimpleRunner.g.cs`. The simulator case contains a false guard.
The probe compiles the unchanged generated output against a controlled
platform/GC-stress model and checks which bodies actually execute. Its baseline
mode intentionally expects the broken alias behavior: a successful probe exit
means the defect/control observations were reproduced, not that the generator
is correct.

### Expected behavior

Simulator aliases should select the corresponding iOS/tvOS platform semantics,
preserving existing platform and GC-stress skip rules. An unsupported target
could alternatively produce an explicit diagnostic rather than a silent false
test body.

### Actual behavior

| Target | Normal body mask | GC-stress body mask |
| --- | --- | --- |
| ios | 11 | 10 |
| iossimulator / IOSSimulator | 8 | 8 |
| tvos | 13 | 12 |
| tvossimulator / TvOSSimulator | 8 | 8 |

All generated Main entrypoints return 100. Only the unconditional body runs for
unmapped aliases. The masks identify bodies, not pass/fail exit codes.

The pinned-source probe was freshly rebuilt/rerun on Windows on 2026-10-15:
zero build warnings/errors and 19/19 expected-baseline checks, reproducing the
body masks above. The patched comparison and simulator results below retain
their original 2026-10-13 evidence; they were not replayed in this fresh run.

The omission was also observed in actual unchanged
`Loader/CollectibleAssemblies/GenericVirtualMethod` and
`Loader/CollectibleAssemblies/ResolvedFromDifferentContext` project builds
with `TargetOS=iossimulator`: generated standalone Main contained a false
condition.

### Regression?

No introducing commit has been identified. On 2026-10-15 the complete
`XUnitWrapperGenerator.cs` file at upstream main
`2ef0256337f918788487bde223a7bce2f16dffc1` still has the same Git blob as
the tested baseline: `0dbb5b386effc1a6f0455f958c9c2e75f6c95e5c`.
This is source review, not a rebuilt current-main mobile test lane.

### Known Workarounds

Generate the managed standalone runner with `TargetOS=ios`, keeping crossgen2's
target, the native host and actual simulator execution as `iossimulator`.
Four unchanged official standalone test bodies executed under this workaround.
This does not establish a fix for every upstream mobile-runner path.

A two-arm private source fix is:

~~~diff
- "ios" => Xunit.TestPlatforms.iOS,
- "tvos" => Xunit.TestPlatforms.tvOS,
+ "ios" or "iossimulator" => Xunit.TestPlatforms.iOS,
+ "tvos" or "tvossimulator" => Xunit.TestPlatforms.tvOS,
~~~

With this change the source-linked probe passes 21/21 generated-body/condition
checks. Device/simulator alias output becomes identical, including mixed-case
aliases. Existing ios/tvos/windows/maccatalyst and unknown-target outputs remain
unchanged.

Four unchanged official projects were also rebuilt with the fixed generator
using `TargetOS=iossimulator` and executed on an ARM64 iOS simulator. All had
positive payload evidence and original assertions, with 41/41 verification
checks. Packaging used a private UIKit/native wrapper. Complete XHarness/Helix
integration and actual tvOS execution were not measured.

### Configuration

- Probe: .NET SDK `11.0.100-rc.1.26425.128`, desktop Roslyn generator invocation.
- Confirmed affected source: official commit listed above, product .NET 12.
- Separate execution: ARM64 iOS simulator, official standalone managed entrypoints.
- tvossimulator omission is source/model-confirmed; no tvOS runtime execution claim.

### Other information

- [Affected mapping in official source](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/src/tests/Common/XUnitWrapperGenerator/XUnitWrapperGenerator.cs).
- [Probe project and sources](https://github.com/ReneeGA2020/RuneCLR/tree/13d6154860cdf7ea4b6389ae81f778f76d78f969/eng/apple-generator-regression).
- [Portable two-arm patch](https://github.com/ReneeGA2020/RuneCLR/blob/13d6154860cdf7ea4b6389ae81f778f76d78f969/eng/runtime-patches/0002-apple-simulator-test-generator.patch).
- [Generator body/condition results](https://github.com/ReneeGA2020/RuneCLR/blob/13d6154860cdf7ea4b6389ae81f778f76d78f969/docs/apple-generator-regression.md).
- [Actual source-fixed standalone simulator execution](https://github.com/ReneeGA2020/RuneCLR/blob/13d6154860cdf7ea4b6389ae81f778f76d78f969/docs/ios-generator-fixed-tests.md).
