# Android native session-policy validation plan

Read-only preparation on 2026-10-13. No Android candidate runtime was built,
installed or executed during this preparation. The next target is the existing
Android **x64** emulator with a matching private runtime that acknowledges the
creation-time interpreter-required binder policy. Android interpretation and
Android native session-policy enforcement remain unmeasured.
The later [matching Android Checked prerequisite build](android-session-policy-build.md)
and independent assessment pass; framework/APK execution remain subsequent work.

## Existing measured baseline

The [official Android RC1 lane](android-controlled-packages.md) passed lifecycle
22/22 and its historical controlled-package slice 8/8. It loaded IL generated
after APK installation and collected fresh per-session contexts. That lane uses
shipping .NET 11 RC1, permits JIT, disables R2R / tiering and has no positive
interpreter-method evidence. Its native package is distinct from the .NET 12
source snapshot used for the JNI app-builder headers.

The dedicated Windows AVD is `RuneCLR_API_35_x64`, historically
`emulator-5556`, Android 15 / API35 / 4096-byte pages. Its actual config has
`abi.type=x86_64`, `hw.cpu.arch=x86_64` and an x86_64 system-image path.
An advertised ARM64 guest ABI does not establish ARM64-native execution.
The [Windows native-policy candidate](session-interpreter-validation.md) and
[iOS simulator acceptance](ios-session-policy-acceptance.md) are separate
platform evidence and cannot substitute for this Android experiment.

## Actual available tools and missing preparation

The following paths were inspected, rather than inferred from old reports.

| Host | Available | Missing / unresolved |
| --- | --- | --- |
| Windows | `D:/RuneCLR-Android/sdk`, NDK `27.2.12479018`, JBR `25.0.3`, API36/build-tools35.0.1, the historical APK builder and x64 AVD | Native CoreCLR Android builds are not supported directly on Windows in the checked-out build docs; no registered WSL distribution was found (`Wsl/WSL_E_DEFAULT_DISTRO_NOT_FOUND`) |
| Mac `.95` | `/opt/homebrew/bin/cmake` resolves to CMake3.31.1; `ROOT/tools/bin/ninja`; pinned `ROOT/runtime/.dotnet/dotnet` | No Android SDK/NDK at the inspected conventional paths; no Android Studio application or configured Android environment; no JVM under `/Library/Java/JavaVirtualMachines` or the inspected Homebrew JDK paths |

Here `ROOT` is
`/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr` and `.95` is the
configured Cindy SSH connection `mac-172-26-202-95`. Its non-login SSH PATH
does not contain Homebrew or the private tools; an explicit process PATH is
required. `/usr/bin/java` alone does not establish an installed JDK. The Mac
NDK check covered `~/Library/Android/sdk`, `~/Android/Sdk` and conventional
Homebrew SDK locations; it was not an exhaustive filesystem search.

The Windows NDK contains only `toolchains/llvm/prebuilt/windows-x86_64`;
`clang.exe --version` reports Android r27c clang18.0.3 with Windows host target.
Its `x86_64-linux-android24-clang.cmd` and ARM64 counterpart can compile the
existing Windows-built JNI wrapper, but cannot run on the Mac. The next build
needs an isolated **Darwin-host r27c NDK**, with
`build/cmake/android.toolchain.cmake` and the Darwin-host LLVM binaries.
Verify their actual executable architecture and that they run on the M1 before
building. A Linux NDK plus a prepared WSL distro is an alternative build host,
not a prerequisite for using the existing Windows emulator. No tool installation
or environment change was performed here.

## Source and feature gates

The source review used the clean Windows candidate worktree
`E:/runtime-selection-20261013`, branch `runeclr/session-policy`, commit
`5972a86966e56ae5f468a3e042327f0051e923d5`, and its checked-out
`docs/workflow/building/coreclr/android.md`, CoreCLR build README, native build
scripts and feature definitions. Its only AGENTS file is under `eng/common`,
whose Arcade-owned files are not changed by this plan.

For the new Android worktree, use the already reviewed [combined source](ios-session-policy-source-review.md):
official base `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`, portable patches
0001 then 0003 then 0004, exact tree
`71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2` (27 changed files). The existing
combined commit is `1724cdec553a7aff7a373a271a4be612651c7625`. Keep Android
objects and outputs separate from the frozen Windows and iOS products.

The current source explicitly excludes Android from the automatic
Debug/Checked interpreter default in both `src/coreclr/clrfeatures.cmake`
and `clr.featuredefines.props`. Therefore selecting Checked alone is
insufficient. `-clrinterpreter` is essential: `eng/build.sh` sets
`FeatureInterpreter=true`, `runtime.proj` passes `-DFEATURE_INTERPRETER=1`,
and CoreLib receives the matching `FEATURE_INTERPRETER` definition. Actual
compile commands and generated managed inputs must confirm that this override
took effect.

Android normally keeps `FeatureDynamicCodeCompiled=true`. Preserve this for
the first policy experiment: trusted host/framework code can compile natively,
while required author bodies must not fall back to JIT. Android uses a shared
`libclrinterpreter.so` in this topology; packaging only CoreCLR and CoreLib
would omit a required component. The static interpreter topology used on iOS
cannot be copied without changing and separately validating the Android build.

`eng/native/build-commons.sh` supplies Android API24 and maps target x64 to
`ANDROID_ABI=x86_64` through the NDK CMake toolchain. Android does not require
an Ubuntu `ROOTFS_DIR`. The version-ack QCall returns1 only with native
`FEATURE_INTERPRETER`; otherwise it returns0 and factory creation rejects
with PlatformNotSupportedException before package loading.

## Concrete next build and product

Prepare the Mac-host NDK and an isolated SDK/JDK only as needed for the selected
build subsets. APK packaging/deployment can stay on the already prepared Windows
host. Start a fresh runtime worktree at the combined source identity, clone only
the pinned source SDK `11.0.100-rc.1.26420.103`, and record tool hashes / versions.
Do not reuse native objects, generated CoreLib, compiler outputs or shipping
Android CoreLib from the prior .NET11 package.

The checked-out official Android build command supplies the following subset
template. Add interpreter support and host cross tools; target x64 for the
existing AVD. The command below is a proposed first **Checked** build, not a
command already executed:

```sh
export ROOT=/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr
export ANDROID_NDK_ROOT=/absolute/private/android-ndk-r27c
export ANDROID_SDK_ROOT=/absolute/private/android-sdk
export JAVA_HOME=/absolute/private/jdk
export PATH="$ROOT/tools/bin:/opt/homebrew/bin:$JAVA_HOME/bin:/usr/bin:/bin:/usr/sbin:/sbin"
./build.sh clr.runtime+clr.native+clr.alljits+clr.corelib+clr.nativecorelib+clr.tools+clr.crossarchtools+clr.packages+libs \
  -os android -arch x64 -cross -c Release -rc Checked -lc Release -clrinterpreter -ninja /m:1
```

The intended product prefix is `artifacts/bin/coreclr/android.x64.Checked`.
Runtime-native and its CoreLib use Checked; the ordinary libraries use Release,
following the checked-out CoreCLR guide. Record that split explicitly.
Discover the actual Mac-host crossgen2/JIT paths from the build manifest;
execute host tools on the Mac, never the Android target compiler executable.
The official full shipping-pack alternative additionally requests `host+packs`;
that is only needed if consuming its produced installer layout. If a smaller
private layout is assembled instead, record every framework/native input and
do not call it a shipping pack. The command and resource usage may need a
reviewed adjustment once the fresh Android restore/build reveals actual
prerequisites; preserve every failed attempt.

The first Checked build provides interpreter bytecode dumps and native JIT
diagnostics for an Android-specific positive/negative execution comparison.
Follow it with a fresh matching Release build and native method-entry proof;
never place Checked CoreLib beside Release native binaries.

For each build retain source/tree/clean receipts, CMake caches, complete compile
databases, VM/binder/interpreter object owners, LLVM target / Android ABI / API,
CoreLib PreTrim/PostTrim/ProductIL and actual linker descriptors. Verify the
private five bridge methods, nested context methods and three native imports
survive trimming. The three reflection entry points must remain rooted.
Bind required bit33 and GUID `7c844228-f051-4b9b-9b8f-4e221230806f` across
CoreCLR, `libclrinterpreter.so`, target-native clrjit, managed compiler mirror
and the host crossgen2/JIT-interface dependencies. Inspect actual ELF x86_64
target images and Mach-O host images separately. A native-only replacement
cannot establish this matching layout.

## APK and post-install payload sequence

Use a new app ID and output directory, leaving historical apps/data intact.
Reuse the existing JNI builder source as packaging machinery with the **new**
matching headers and product inputs. The current
[verify-android.ps1](../eng/verify-android.ps1) expects an extracted stock
android-x64/net11.0 NuGet layout and labels its output stock JIT; simply passing
a source-product directory to that parameter is insufficient. Add a separate
explicit private-layout integration or consume a newly built matching package;
do not fabricate a stock nuspec/version merely to satisfy its directory checks.

Package current trusted RuneCLR/player fixtures and the native interpreter/JIT
libraries; exclude author entry/private IL, source compiler, Roslyn and operator
tooling. Install and hash the fresh APK first. Only then compile unique author
IL / private dependencies and controlled source/imported packages against the
packaged contract with the trusted operator, and push them to that app private
directory. Record install/compile/push timestamps and device-side DLL/manifest
hashes. The APK, wrapper and trusted-host hashes must remain unchanged.

Configure the required-session main lane with `DOTNET_InterpMode=0`,
`DOTNET_RuneCLRInterpretCollectible=0`, R2R enabled and tiering enabled. Native
policy must be acknowledged before the entry or late-resolved private assembly
loads. Keep environment receipts separate from policy/query and execution proof.
In Checked, use actual successful bytecode identities plus zero author-body
native-JIT records, with positive trusted-host native control. For Release,
capture MethodDesc / owner-module / interpreter bytecode method-entry evidence
and trusted native control, adapting the existing iOS verifier to Android x64
ABI rather than reusing ARM64 register assumptions.

## Required acceptance matrix

| Lane | Required observation |
| --- | --- |
| Capability query before loading | Version1; Default/ordinary collectible policy0; factory context policy1 with diagnostic switch0 |
| Main selection fixture | Existing 26 body groups over20 contexts, fresh static state, private dependency first loaded by its real late resolution, shared contract stays policy0; every required author-body group interpreted and no body JIT |
| Boxed/interface/delegate bridge | Existing independent20-context boxed fixture; runtime ABI wrapper may remain native while constructor/cctor/Read/property IL bodies interpret; all contexts collected |
| Native generic/inline callers | Trusted caller native positive; author AggressiveInlining / generic body still interpreted; required-session inline rejection, ordinary identical bytes positive native control |
| Forced real refusal | Exact test-only `SelectionProbe.Refusal` / `SelectionUGC.Refusal.Entry:Reject` methodset yields real CORJIT_SKIPPED with diagnostic0; required context reports NotSupportedException, retires and20 subsequent valid required contexts recover |
| Ordinary refusal comparison | Same bytes in ordinary context, InterpMode1 and test-only refusal enabled, produce the real SKIPPED marker then native result73; demonstrates the injection is exercised and required-path no-fallback is policy-specific |
| Lifecycle / packages / sample | Current actual lifecycle harness, controlled source/import/failure/rejection recovery and sample contexts pass in one app process with required policy; record current counts rather than reuse historical22/8 |
| Retirement query | Policy query after unload consistently throws InvalidOperationException; no result retains context/delegates/reflection metadata/exceptions; forced GC occurs after execution stack return |
| Build without interpreter | Separate correctly matched no-feature candidate reports version0 and refuses factory before author loading; do not silently accept an unknown switch as acknowledgement |

For Checked-only CID follow-up, use a separately recorded
`DOTNET_UseCachedInterfaceDispatch=1` lane and verify the actual dispatch route.
The JIT-capable Android default VSD path is not evidence that the iOS CID fix
has been exercised. Keep R2R-on/tiering-on main policy tests distinct from
ordinary-JIT diagnostic controls and source/profile rejection tests.

Completion means actual Android x64 functional, policy-acknowledgement,
method-execution and recovery receipts on the new matching build, followed by
Release parity. ARM64 phones, 16KiB-page devices and performance remain later
targets. The private factory/policy is an execution-selection mechanism, not a
complete hostile-code sandbox; author-created unmarked contexts are outside
this controlled loading route.
