# Remote Mac and simulator preparation — 2026-10-12

The project owner supplied an existing Cindy SSH Mac connection for platform
experiments. This follow-up establishes a usable remote build/test environment
and a macOS ARM64 lifecycle baseline. It does not establish managed execution
inside an iOS app or complete
[#2](https://github.com/ReneeGA2020/RuneCLR/issues/2).

## Environment and source identity

- Apple M1 / arm64, macOS 27.0.1, Xcode 27.0 (`27A266a`).
- Available simulator runtimes: iOS 18.0, 18.1, 18.4, 26.5 and 27.0.
- Private .NET SDK `11.0.100-preview.6.26359.118`; stock desktop CoreCLR
  `11.0.0-preview.6.26359.118`, source stamp `ba53d0ed33`. This is a different
  runtime from the pinned Windows interpreter experiment.
- SDK tarball downloaded from Microsoft's official release metadata and
  verified against its published SHA-512. It was extracted into an experiment
  directory, not installed over an existing system runtime or added to global
  PATH. CLI home and test processes use that private directory.
- RuneCLR source: `c99c5cc7fc690b71a7db609a5598acddc390076e` plus the local
  documentation changes, copied without Git metadata, build outputs or
  machine-local notes. Source archive SHA-256:
  `f52978451b01ff168cc3637cf107c19a03720b2f59e5e6b47bc7e6cd1c0e7ed5`.
- Local evidence: `artifacts/remote/20261012-mac95-c2a7ea76`. Environment,
  executed runtime hashes, SDK archive checksum, source archive identity,
  command records, app source/build script and all test logs are preserved.
  Machine-specific connection/workspace paths are in the ignored local setup.

## Measured: stock macOS ARM64 lifecycle

The source copy built in Release with zero warnings/errors. The ordinary
eleven-case integration harness passed, and Hello -> Arena -> Hello completed
with fresh static state, full host entity cleanup and three collected contexts.

After that host build, LateMap was rebuilt separately without traversing its
dependency project graph. Host/harness output hashes and modification times
were unchanged. The late-map harness passed **12/12** and the standalone late
sample completed and collected its context.

Reproduction with the private SDK on PATH and a private CLI home:

```sh
dotnet build RuneCLR.slnx -c Release
dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build
dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --collect
dotnet build tests/RuneCLR.LateMap -c Release -t:Rebuild -p:BuildProjectReferences=false
dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build -- --late-map tests/RuneCLR.LateMap/bin/Release/net11.0/map.json
dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --collect tests/RuneCLR.LateMap/bin/Release/net11.0/map.json
```

Inherited DOTNET/COMPlus settings were cleared for these processes. No
interpreter selector was applied or positive interpreter trace collected. This
is a stock macOS desktop baseline, not interpreter or iOS evidence. Its
regressions cover successive maps, ordinary exceptions, cooperative budget and
resource failures, private dependency versions and map-private generic statics.

## Measured: native iOS simulator smoke

A small Objective-C/UIKit probe was compiled with the iPhoneSimulator 27.0 SDK
for arm64, ad-hoc signed and installed into a newly created, dedicated iPhone
17 Pro / iOS 27.0 simulator. Mach-O build metadata identified `IOSSIMULATOR`,
minimum OS 27.0 and SDK 27.0. Existing simulator devices were not reused.

The simulator booted, the app launched, wrote/read its own 38-byte temporary
payload and emitted `storageRoundTrip=true`. It exited automatically, and the
dedicated simulator was confirmed shut down afterwards. App source and the
complete build/deployment script are in the evidence archive.

This verifies SSH-controlled Xcode compilation, simulator startup, deployment,
execution/log capture and basic app-owned storage access. It does not load
CoreCLR, execute C# or download/run a map. Native app success cannot substitute
for RuneCLR's managed loading/interpreter/unloading acceptance. No physical
iPhone, signing-team availability or device performance was validated.

## Next simulator experiment

The subsequent [managed simulator experiment](ios-simulator-experiment.md)
has now run post-install IL and the real RuneCLR lifecycle harness. Its
selective IL/R2R packaging success and retained native-interface crash are
separate from the native-only smoke recorded above.

The Mac can now supply the simulator lane beside the controlled-package work.
Use a separate pinned `dotnet/runtime` checkout and follow its applicable
instructions/build documentation before changing or building it. The source
workflow is recorded in [the platform checklist](platform-validation.md).
The first diagnostic build can follow its iOSSimulator arm64 route:

```sh
./build.sh clr+clr.runtime+libs+packs -os iossimulator -arch arm64 -cross -c Debug
./dotnet.sh publish src/mono/sample/iOS/Program.csproj -c Debug /p:TargetOS=iossimulator /p:TargetArchitecture=arm64 /p:UseMonoRuntime=false /p:MonoForceInterpreter=false /p:RunAOTCompilation=false /p:DeployAndRun=true
```

These commands were **not run** in this experiment. The runtime repository
bootstraps its own private SDK; do not assume the desktop test SDK is its
required build SDK. Resolve the checkout's native prerequisites and packages
before claiming the mobile runtime exists.

In the pinned source, iOSSimulator disables dynamic compiled code and enables
the interpreter. Apple CoreCLR packaging preserves trusted host/framework R2R.
Do not copy the Windows benchmark's global `ReadyToRun=0` or mode 3 setup, and
do not use Mono's force-interpreter sample route as CoreCLR configuration.

Next, wrap the lifecycle fixtures in an app; coordinate #4/#5's approved
dependency resolver instead of using the mobile-unsupported
`AssemblyDependencyResolver`. Build a new IL map after completing the host
bundle, verify the unchanged host identity, and load it from app-owned storage.
Debug interpreter traces/breakpoints must prove map execution; the existing
Windows x64 precode probe is not an ARM64 diagnostic. Recheck private
dependencies, static reset, ordinary failures, resource release and repeated
collection. Simulator results prepare #2; physical-device acceptance remains.
