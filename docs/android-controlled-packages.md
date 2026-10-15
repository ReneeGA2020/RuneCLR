# Controlled gameplay packages on Android

On 2026-10-12, the official .NET 11 RC1 Android x64 CoreCLR package passed
the new `managed-il-gameplay-v1` package lane in the dedicated Android 15
emulator. The original [lifecycle suite](android-lifecycle-experiment.md)
passed **21/21** before late IL and **22/22** after late IL. With controlled
packages added, the same suite remained **22/22** and the additional package
acceptance passed **8/8**, exit code 0.

## Measured acceptance

| Case | Observed result |
| --- | --- |
| Source package, imported IL package, original source again | All three started with `starts=1`, stopped, released their entity and collected |
| Ordinary author exception after spawning an entity | Failure recorded, stop callback ran, entity released and context collected |
| Valid package after author failure | Completed with fresh static state, cleanup and collection |
| Changed package bytes with original hashes | Rejected during manifest loading |
| Forbidden `GC.Collect` call with recomputed entry/file/content hashes | Rejected during manifest loading by `managed-il-gameplay-v1` capability policy |
| Valid package after both rejected packages | Completed with fresh static state, cleanup and collection |

The additional cases execute together in one Android app process after the
original lifecycle harness. Forced GC checks completed retirement after each
runner call returns; they are diagnostic checks, not a gameplay GC policy.

## Inputs and provenance

- Official `Microsoft.NETCore.App.Runtime.android-x64`
  `11.0.0-rc.1.26425.128`, dotnet/dotnet commit
  `3551975be08744f0418857c5bed8ab1545c5dd47`. The app reports that version and
  CoreLib informational commit.
- App-builder/header snapshot: separate unpatched .NET 12 source checkout
  `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. Its SDK
  `11.0.100-rc.1.26420.103` builds the APK wrapper; it does not identify the
  packaged Android runtime.
- Operator SDK: private official `11.0.100-rc.1.26425.128`. The trusted operator
  helper invokes `PackageBuilder`/`SourceCompiler` with the fixed reference
  snapshot and packaged host Abstractions. Submitted script text never supplies
  a project or build script. Each versioned manifest records producer inputs.
- Dedicated `RuneCLR_API_35_x64`, `emulator-5556`, API 35, x86_64, 4096-byte
  pages. Android SDK compile API 36, target API 35, NDK 27.2.12479018.

APK installation completed at `2026-10-12T13:07:42.1455801Z`. Late baseline IL
compilation started at `2026-10-12T13:07:49.9487681Z`; controlled source/IL
production started at `2026-10-12T13:07:55.7060815Z`. All controlled payloads
were generated after installation and copied only to the unique experiment
app's files. Nested APK asset inspection confirms these payloads, Roslyn,
`RuneCLR.Compiler`, and `RuneCLR.PackageTool` are absent from the APK.

Device-side hashes match every pushed package DLL and manifest. They also
match the unchanged APK, wrapper, original test harness and these host libraries:

```text
APK: b9fb345547933bc7a52d9092c12fb213427d8deebee9245e4edf3d6eaf1ca850
wrapper: 4ce30cf995ba9c9f47763228715e8151a62fa6362d654f0a5da3b3026dcd9d4c
Runtime: 65bb59be57d1b45961439c68bf4932941845f404a18516a77613b8ee55248e27
Packages: 7ee84d7c2afce7ce6d42a1a382790a59638f26e729560037f895d3ccda854bc0
Abstractions: 4de6dd2fbf59d994b23b76ab2693f4d8075f95cc1dfb41c182d852cb71ed1823
source/import IL: ea59e37468ed1ae05afb86783024be52879af60698d2b6bc54850c4daf7d53fe
```

## Reproduction and evidence

Use the prepared Android SDK, template builder and extracted official runtime
pack described in [the Android setup](android-emulator-experiment.md). Choose
the build SDK and operator SDK explicitly:

```powershell
./eng/verify-android.ps1 -ControlledPackages `
  -RuntimePackDirectory D:/RuneCLR-Android/runtime-packs/11.0.0-rc.1.26425.128/extracted `
  -DotnetExecutable E:/runtime/.dotnet/dotnet.exe `
  -OperatorDotnetExecutable E:/RuneCLR/artifacts/toolchains/dotnet-11-rc1/dotnet.exe
```

Paths above identify this validation machine; use parameters for other prepared
machines. `-ControlledPackages` extends the existing driver while its ordinary
lifecycle mode remains available. `-BuildOnly` prepares the APK and operator
without installing or producing post-install script packages. Each run uses a
fresh evidence directory and unique app ID, preserves older apps, and shuts down
the dedicated emulator only when that run started it. This run shut it down.

Evidence is under `artifacts/android/controlled-20261012-policy-v1`: original
build/install/test logs, `request.json`, `evidence.json`, generated wrapper and
operator sources, source/imported/mutated packages, APK asset inventory and
`controlled-device-hashes.txt`. No failed attempt preceded this acceptance run.

## Scope

This establishes versioned package/capability/lifecycle compatibility on a
JIT-capable Android x64 emulator. R2R and tiering are disabled; no positive
interpreter execution evidence was collected. Physical Android ARM64 devices,
iOS acceptance, frame performance, package authentication and enforced execution
budgets remain separate work. The static capability gate restricts referenced
APIs and IL forms; it does not establish a hostile-code sandbox.
