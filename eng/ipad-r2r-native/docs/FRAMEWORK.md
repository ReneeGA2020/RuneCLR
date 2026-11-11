# iPadOS framework build (public entry)

This is the maintained, parameterized version of the framework build verified on 2026-11-10.
It produces exactly what build_host.py consumes with --framework-root.

## Inputs you must supply

| input | meaning |
| --- | --- |
| private runtime checkout | a dotnet/runtime worktree with artifacts/ from a completed iOS build |
| runtime pack nupkg | artifacts/packages/Release/Shipping/*Runtime.ios-arm64*.nupkg (auto-discovered, must be unique) |
| crossgen2 | artifacts/bin/coreclr/ios.arm64.Release/arm64/crossgen2/crossgen2 (default) |
| dotnet | <runtime>/.dotnet/dotnet (default; recorded for provenance) |

## Runtime preparation (done once per runtime line)

    git clone <dotnet/runtime fork> runtime && cd runtime
    git checkout runeclr/dev          # public fork branch
    # verified full pin for the 2026-11-10 build:
    #   474eb8ad7230122cc0d34318b25d673da63fd138
    git rev-parse HEAD               # record the full pin

    # two target-specific patches (device minimum 15.3, host tooling untouched):
    #   Directory.Build.props:      <iOSVersionMin>13.0</iOSVersionMin> -> 15.3
    #   eng/native/build-commons.sh: CMAKE_OSX_DEPLOYMENT_TARGET=13.0 -> 15.3 (iOS device only)
    git diff > ios-min-15.3.patch

    ./build.sh clr+clr.runtime+libs+packs -os ios -arch arm64 -cross -c Release -clrinterpreter

`build_framework.py` records the runtime commit and the sha256 of the working-tree diff, so a
different patch set is visible in the inventory instead of being silently assumed.

## Framework build

    python3 -B eng/ipad-r2r-native/host/tools/build_framework.py \
      --runtime-root <runtime checkout> \
      --output <fresh directory> \
      [--min-os 15.3] [--parallelism 4] \
      [--pack <nupkg>] [--crossgen2 <exe>] [--dotnet <dotnet>]

Output layout (consumed by build_host.py --framework-root):

    input/                 181 managed inputs (pack libs) into the composite image
    layout/                198 files: deps.json, native dylibs/.a, rewritten component DLLs,
                           framework.dylib
    input-inventory.json   compositeInputs{name:sha256}, layout{name:sha256}, depsFile,
                           sourceCommit, target, pack, crossgen2, dotnet, coreLib,
                           runtimePatch, inputs/layoutFiles details, nativeAudit, stages

The steps are the verified recipe: crossgen2 with --composite --inputbubble --targetos:ios
--targetarch:arm64 --obj-format:macho, then one `xcrun --sdk iphoneos clang -target
arm64-apple-ios<min> -dynamiclib` link of the composite object as framework.dylib.

## Verified reproduction (2026-11-10 dev runtime)

| item | value |
| --- | --- |
| runtime commit | 474eb8ad7230122cc0d34318b25d673da63fd138 (dirty: 2 iOS-min lines) |
| patch diff sha256 | 1480a1a4395d77b8... |
| dotnet | 12.0.100-alpha.1.26480.102 |
| crossgen2 | 7bdd26744a7857f5ba21c44836370009d1f3f94cae31a1ed7e3b7347b7eb113d |
| pack nupkg | Microsoft.NETCore.App.Runtime.ios-arm64.12.0.0-dev.nupkg, 430f90d7ac506955... |
| CoreLib input (pack IL) | 8a9f9d04ee83528a... |
| CoreLib shipped in layout | 552e9fb713ff9f02... |
| framework.dylib | 1949fab68b348d0ef2ec150417f02904a4369e7268109b94ac665d085b29cf21 |
| platform / minos | 2 / 15.3 (0xF0300) |

Two runs produced the same framework.dylib hash: framework-export-1 and framework-export-2,
and build_host.py built an app with identical exe (726f6c96...) and host composite
(930f7715...) from that fresh framework root. Precision: export-1 ran the pre-fix revision of
this tool whose input-inventory.json emitted lists; only export-2 ran the sealed tool
(sha256 8631ed5b..., dict-shaped inventory). Both produced the same framework bytes and the
same crossgen response file content, but this is not two executions of the sealed source.

CoreLib identities stay separate: the pack input copy recorded here is 8a9f9d04..., the
shipped component in layout/ is 552e9fb7..., and the private IL produced by the runtime build
is a third file, d6f4a42a... . This tool only copies the pack input and records the shipped
rewrite; it does not build or assert the private IL.

The tool records platform/minos by parsing the Mach-O it produced; it does not assert them as a
gate. build_host.py's native audit is the step that validates platform 2 / arm64 / minos 15.3.

## Downstream (unchanged tools)

    python3 -B eng/ipad-r2r-native/host/tools/build_host.py --runtime-root <runtime> \
      --framework-root <framework output> --output <fresh host dir> \
      --dotnet <dotnet> --csc <sdk>/Roslyn/bincore/csc.dll \
      --source-root <host/src> --update-source-root <update-src> \
      --trusted-source-root <trusted sources> --bundle-id <bundle> --min-os 15.3

    python3 -B eng/ipad-r2r-native/host/tools/generate_update_v2.py --framework-root <framework output> ...
    python3 -B eng/ipad-r2r-native/host/tools/release_urls.py --root <sealed dir> --base-url ...

Signing, sealing and device steps stay in docs/STEP1-RECIPE.md and docs/DELIVERY.md.

## Limits

- Windows/macOS host builds only in this recipe; no production, App Store or iOS 13 support claim.
- The tool never builds the runtime; it consumes an existing iOS runtime build.
- Device validation of this framework line is the Step2 evidence, not this tool.