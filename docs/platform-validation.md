# Target-platform validation preparation

Preparation inspected on 2026-10-12 for [issue #2](https://github.com/ReneeGA2020/RuneCLR/issues/2)
and the [accepted execution strategy](execution-strategy.md). This is a read-only
environment/source audit, not an Android or iOS execution result. The owner has
already exercised the interpreter in an earlier Preview; the next experiment
must establish RuneCLR's new-map loading and repeated retirement on devices.

A later [remote Mac experiment](remote-mac-experiment.md) on 2026-10-12 found
an SSH-accessible M1 Mac with Xcode/simulator runtimes, passed the stock macOS
ARM64 lifecycle suite and a native simulator app smoke. This supplies an actual
Mac preparation lane; it does not establish managed iOS or interpreter execution.
The Windows inventory below remains the earlier machine-local observation.
The later [Windows Android experiment](android-emulator-experiment.md) installed
Studio/emulator/ADB/NDK and passed a stock Android CoreCLR post-install IL
mini-fixture with 20/20 collected contexts. It confirmed the dependency resolver
constructor failure; the earlier missing-tool inventory is not the current setup.

## Scope and source baseline

The separate runtime checkout was on `runeclr/interpreter-baseline`, clean, at
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. Its applicable instructions and
checked-out iOS/Android build documentation were read. No runtime sources were
changed, no SDKs were downloaded, no cross-platform build was started, and no
device or emulator was deployed to or launched during this audit.

Use selective interpretation for UGC and private managed dependencies. Trusted
host/framework native code is allowed. Full-framework `InterpMode=3` is a
different configuration: the existing Windows Checked assertion in that mode
does not establish a blocker for this policy. Environment/method filters remain
diagnostic tools, not enforced per-session selection.

Pinned upstream references:

- [CoreCLR iOS build workflow](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/docs/workflow/building/coreclr/ios.md).
- [CoreCLR Android build workflow](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/docs/workflow/building/coreclr/android.md).
- [Interpreter feature defaults](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/src/coreclr/clrfeatures.cmake).
- [Target build configuration](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/eng/build.sh).
- [Platform limitations of AssemblyDependencyResolver](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/src/libraries/System.Private.CoreLib/src/System/Runtime/Loader/AssemblyDependencyResolver.cs).

## Windows environment actually inspected

The following are observations on this machine, not required portable paths.

| Item | Observation | Consequence |
| --- | --- | --- |
| Desktop runtime | Windows x64 Checked and Release output directories exist; validated desktop results are recorded separately | Reuse only the documented matching layouts/evidence |
| Other runtime output | Older `browser.wasm.Debug` output exists | No Android/iOS support evidence |
| Build tools on PATH | `dotnet`, Git and CMake found; `clang` and `ninja` not found on PATH | Existing VS desktop tools do not supply an Android Linux build environment |
| Installed SDKs | .NET 9.0.318; 10 Preview 7 and RC 1; 11 Preview 6 | Repository SDK selection still governs each checkout |
| .NET mobile workloads | `dotnet workload list` reports none | No installed workload-based mobile app setup was established; upstream in-tree workflow has its own packaging tools |
| WSL | `wsl.exe` exists, but listing/status reveals no usable distribution (`Wsl/WSL_E_DEFAULT_DISTRO_NOT_FOUND`) | The documented Windows-to-Android WSL route cannot start yet |
| Java | PATH resolves Microsoft OpenJDK 11.0.16.1; `JAVA_HOME` points to an emsdk Java 8 directory | Prepare a separate compatible JDK environment; do not assume either selection meets upstream requirements |
| Android SDK variables | `ANDROID_HOME`, `ANDROID_SDK_ROOT`, `ANDROID_NDK_ROOT`, `ANDROID_NDK_HOME` unset | Existing SDK location is not configured for the runtime workflow |
| Android SDK directory | Partial SDK found at `C:/Program Files (x86)/Android/android-sdk` | Inventory/reuse only compatible components; absence from PATH did not mean the SDK was absent |
| SDK components | Platform directories 29/30/36; build-tools 30.0.2/31.0.0/35.0.1; command-line-tools and emulator directories present | Directory presence does not prove a functioning toolchain |
| ADB / NDK | No `adb` on PATH, no `platform-tools` in inspected SDK, and no NDK directory in inspected locations | No device connectivity test was performed; NDK r27c/tooling must be supplied or located |
| AVD hint | Old API 28 `x86_64` Pixel 2 AVD configuration exists | It was not launched; working system image/emulator availability is unverified |
| Apple tooling | No `xcodebuild`/`xcrun` on this Windows host; no Mac/device/signing environment inspected | iOS build and real-device validation need a macOS environment |

The user operating Cindy remotely from an Android phone does not establish ADB
access to that phone. Since ADB was not found, there is no `adb devices` result
and no approved test-device claim. Search coverage was PATH, environment values
and common SDK locations, not every disk or external machine.

## Android: prepare the interpreter build deliberately

The pinned CoreCLR Android workflow supports Linux/macOS or Windows through WSL;
native Windows builds are not its supported path. Targets are x64 and arm64.
It specifies Android SDK API 24 minimum, NDK r27c and OpenJDK 23 (with OpenJDK 21
described as sufficient in Ubuntu WSL). Do not copy the adjacent Mono library
testing document's old JDK instructions or Mono interpreter flags as CoreCLR
configuration.

Android is excluded from `clrfeatures.cmake`'s default interpreter enablement,
and `eng/build.sh` normally enables dynamic compiled code on Android. Explicitly
enable `FeatureInterpreter` for this experiment. Disabling all dynamic compiled
code is not required by the selective UGC strategy.

After a suitable Linux/macOS/WSL environment is ready, the source-documented
package build can be adapted as follows; this command has not been run here:

```sh
./build.sh clr.runtime+clr.alljits+clr.corelib+clr.nativecorelib+clr.tools+clr.packages+libs+host+packs -os android -arch arm64 -c Release /p:FeatureInterpreter=true
```

Use x64 for an x64 emulator. Record resolved compiler/JDK/SDK/NDK versions,
generated build flags, runtime/framework hashes and upstream base before running
the sample. Start with the upstream CoreCLR Android sample, then the RuneCLR
lifecycle harness adapted for APK packaging. Android JIT sample success alone
does not establish interpretation.

## iOS: real-device preparation and acceptance

The pinned workflow builds on macOS with Xcode, the iPhone SDK and selected
command-line tools. Follow its macOS CMake/ICU/pkg-config/Python/Ninja prerequisites.
Provision a development-signable iOS device, signing identity/team and app
identifier; their availability was not inspected here.

The build driver defaults iOS-family targets to `FeatureDynamicCodeCompiled=false`
and explicitly enables `FeatureInterpreter`. Apple app packaging statically
links the interpreter; absence of a separate `libclrinterpreter.dylib` is not
proof that it is missing. `MonoForceInterpreter` is not the CoreCLR selection
mechanism. Use the CoreCLR sample/test configuration (`UseMonoRuntime=false`).

The upstream starting commands, not run on this machine, are:

```sh
./build.sh clr+clr.runtime+libs+packs -os ios -arch arm64 -cross -c Release
./dotnet.sh build src/mono/sample/iOS/Program.csproj -c Release /p:TargetOS=ios /p:TargetArchitecture=arm64 /p:UseMonoRuntime=false
```

First establish matched runtime and trusted framework packaging with the upstream
sample; then deploy a RuneCLR test host. Simulator runs can shorten packaging
debugging, but #2 requires a physical device. Trusted precompiled framework
coverage and trimming must be checked independently from UGC interpretation.

Required RuneCLR acceptance evidence:

1. Build/install the host first, record its bundle hashes, then compile a new
   map and private dependency through the controlled build pipeline. Load their
   IL from the device app's permitted storage without republishing the host.
2. Prove map callbacks, constructors, relevant generics and private dependency
   methods use the interpreter through supported diagnostics or debugger
   evidence. Record configuration; accepted environment variables are insufficient.
3. Run successive A -> B -> A sessions with version-distinct same-name private
   dependencies. Verify fresh static state, the shared Abstractions contract,
   host entity cleanup, ordinary managed failures and next-map recovery.
4. Repeat at least twenty sessions. Check weak-context collection only after
   invocation stacks return; forced GC is diagnostic. Retain bounded host-owned
   result data rather than map exceptions, metadata or delegates.
5. Save device model/OS/architecture, source and host revisions, build/signing
   configuration, package/runtime hashes, interpreter evidence and outcome.
   Report failed, unsupported and unperformed cases separately. Do not close #2
   using desktop/macOS/simulator evidence.

This is controlled-map lifecycle acceptance, not a claim of hostile-code
isolation or hard CPU limits.

## Tasks that can advance while device environments are prepared

Follow-up: [Android full lifecycle](android-lifecycle-experiment.md) and
[managed iOS simulator](ios-simulator-experiment.md) now have actual harness
results. Android interpretation and iOS physical-device acceptance remain open;
the iOS compiled-host interface crash is retained on Preview 6, official RC1 and the
pinned unpatched .NET 12 Debug source build. Its selective Runtime-IL full suite
passes 21/21 and post-install 22/22 with direct method evidence; the earlier
mini-fixture's 20/20 retirement is recorded separately.
The [current controlled-package lane](ios-controlled-packages.md) separately
passes 15/15 on the unpatched source .NET 12 Debug simulator with post-install
IL, direct callback/private-generic interpreter dumps, unchanged bundle hashes
and completed collection. Runtime and Packages remain IL. The
[CID cache comparison](ios-r2r-investigation.md) localizes the all-host-R2R
failure to collectible-target cached dispatch. The later
[minimal capture](ios-r2r-minimal.md) establishes stale mapping/address reuse,
and a private conservative candidate passes
[five-group Debug acceptance](ios-r2r-fix-validation.md). Full upstream, Release
and physical-device acceptance remain outstanding.

1. **Package dependency resolution (#4/#5).** At the initial audit the loader used
   `AssemblyDependencyResolver`, marked unsupported on both Android and iOS in
   this baseline. Design and test explicit approved package dependency resolution
   on desktop, preserving per-session private ownership and host Abstractions
   sharing. The later [resolver increment](package-resolution.md) implements
   this routing and passes the expanded Windows suites. This removes a known
   portable API dependency, but is not device proof.
2. **Portable lifecycle fixture.** Separate the post-host-build map input and
   bounded lifecycle result recording from desktop CLI/deployment plumbing, so
   the same cases can run in Android/iOS app wrappers. Avoid assuming desktop
   hostpolicy or filesystem layouts exist on devices.
   The [portable package execution harness](package-execution-tests.md) now
   implements this separation and passes desktop and iOS simulator acceptance.
3. **Execution policy and budget source design (#5/#6).** Inspect selective
   map-method ownership and safe terminal interruption on desktop without making
   a full-framework mode 3 fix a prerequisite. Preserve supported framework-call
   limits and test catch-and-continue behavior when implementation begins.
4. **Device environment setup in parallel.** Locate/provision a Mac and iOS
   device for #2; establish Linux/WSL + compatible Android toolchain and an
   explicitly chosen test target. Then run separate platform experiments.

Keep the iOS acceptance issue open until real-device evidence exists. Android
interpretation likewise remains unverified; opening/preparing its work does not
mark it complete.
