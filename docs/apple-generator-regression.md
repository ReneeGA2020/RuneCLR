# Apple simulator generator alias regression

On 2026-10-13, a small private source fix maps iossimulator to the existing iOS
platform flag and tvossimulator to the existing tvOS flag in the official
XUnitWrapperGenerator. It changes two switch arms, retaining case normalization,
existing platform checks and all unrelated/unknown-target behavior. The
[upstream defect record](upstream-bugs/apple-simulator-test-generator.md)
retains the original skipped generated-body evidence.

## Actual generator and generated-body checks

The [source-linked probe](../eng/apple-generator-regression/Program.cs) compiles
the official generator's thirteen C# files and its official TestFilter dependency
against the operator SDK Roslyn assemblies. CSharpGeneratorDriver invokes that
actual incremental generator. No copy of its target-platform switch is used as
the implementation under test. The pinned official TestPlatforms and
RuntimeTestModes sources also provide the fixture's enum values.

The probe stores every generated SimpleRunner.g.cs, compiles the unchanged
generated Main with a controlled platform/GC-stress model, invokes it, and checks
which test bodies actually executed. It never uses exit 100 alone as execution
evidence. Fixtures cover a stress-sensitive body, iOS-only body, tvOS-only body
and an unconditional body. The platform model supplies the runtime condition
values; it does not rewrite the generated conditions. This is desktop generator
semantics testing, not execution on an Apple runtime.

| Target | Unpatched normal / GC-stress body mask | Patched normal / GC-stress body mask |
| --- | --- | --- |
| ios | 11 / 10 | 11 / 10 |
| iossimulator, IOSSimulator | 8 / 8 | 11 / 10 |
| tvos | 13 / 12 | 13 / 12 |
| tvossimulator, TvOSSimulator | 8 / 8 | 13 / 12 |
| windows, maccatalyst | 9 / 8 | 9 / 8 |
| not-a-platform | 8 / 8 | 8 / 8 |

Bits identify the executed bodies: stress-sensitive=1, iOS-only=2, tvOS-only=4,
unconditional=8. Every Main returns 100, including the original alias bodies
that were skipped. The body masks distinguish those outcomes. Additional
checks exercise the inherited iOS runtime condition's MacCatalyst exclusion;
only the intended stress-sensitive body is suppressed by that runtime guard.
Compile-time PlatformSpecific selection continues to assume its build target.

The baseline reproduces the omission and passes **19/19** expected-control
checks. The patched generator passes **21/21** body/condition checks. Its
generated Main is byte-identical between each device target and both
lower/mixed-case simulator aliases. Existing ios/tvos/windows/maccatalyst and
unknown-target outputs are byte-identical to the unpatched outputs. Both source
builds complete with zero warnings/errors after correcting a nullable filename
annotation in our probe; the initial probe build failure is retained.

## Source and local disposition

Official base: 0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de. Private candidate:
2f3ef1faaf3630f3f57c5402ebd1ab20445b0692, branch
runeclr/apple-simulator-generator in a separate sparse worktree. The original
runtime baseline and candidate are tracked-clean after committing the two-arm
change. Tested source hashes remain identical after the commit. No installed
runtime was changed and no upstream issue/PR was submitted.

The [portable source patch](../eng/runtime-patches/0002-apple-simulator-test-generator.patch)
uses LF line endings and has SHA-256
caad7cb0a870c43b28f0507adc891720889e4ce9b1a2b02466047099993ec239.
The original Windows-exported CRLF patch remains in the unchanged evidence
archives with SHA-256 62a683fff82bf70eedcf838ae2a974e6c33bc0aa917cc6424db45de9c2a89ffe.
Its source edits are identical, but applying those CRLF bytes to the Mac's LF
checkout fails the context check. The portable copy was normalized without
changing either switch arm. git apply --check for the LF patch also succeeds
against the unmodified Windows pinned source; it was not applied to that baseline.

Operator SDK: 11.0.100-rc.1.26425.128. The probe receipt records actual operator
runtime/Roslyn versions, generator assembly and all generator source hashes.
This source-linked operator project is independent of the official
netstandard2.0 generator build project and complete CoreCLR test-build lane.

Keep the previously validated TargetOS=ios evidence in the existing simulator
experiments. The later [source-fixed official simulator test run](ios-generator-fixed-tests.md)
now rebuilds and executes all four unchanged projects with both managed and
native target iossimulator, corrected guards and positive payload evidence.
It uses the private native wrapper; validate the full official mobile runner
before claiming the complete default upstream workflow passes. tvOS execution
and current upstream fix/duplicate-issue status remain unverified.

## Reproduction and evidence

Supply the separate original/candidate runtime source roots to the probe
project; use independent outputs and intermediate directories for each build.
The probe does not apply patches or create runtime worktrees automatically.

```powershell
$dotnet = '/path/to/operator-sdk/dotnet'
& $dotnet build eng/apple-generator-regression/GeneratorProbe.csproj -c Release `
  -p:GeneratorRoot=/path/to/original-runtime/src/tests/Common `
  -p:BaseIntermediateOutputPath=/path/to/new-original-obj/ `
  -p:OutputPath=/path/to/new-original-bin/
& $dotnet /path/to/new-original-bin/GeneratorProbe.dll baseline `
  /path/to/original-runtime/src/tests/Common/XUnitWrapperGenerator /path/to/new-baseline-results
# Build against the candidate source with separate obj/bin paths, then run:
& $dotnet /path/to/new-candidate-bin/GeneratorProbe.dll patched `
  /path/to/candidate-runtime/src/tests/Common/XUnitWrapperGenerator /path/to/new-candidate-results
```

Local evidence: artifacts/upstream-bugs/apple-generator-20261013/.
The original pre-commit archive evidence.tar.gz is retained with SHA-256
d0463a5f8b4b42f401424311ffb355378e3f2857f7f5aeddaaecb92617e173ff.
The later evidence-committed.tar.gz includes the separate commit/source-identity
receipt, 90,200 bytes, SHA-256
254ac91f1ec4c89f44955148ab34feff77b78589da7b65eb8ab4bac4ab6747c0.
They include actual generated output, body-check receipts, build/run logs,
source-linked probe, compiled generator/probe binaries and portable patch.
