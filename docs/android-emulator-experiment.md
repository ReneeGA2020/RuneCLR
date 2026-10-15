# Windows Android emulator and CoreCLR smoke — 2026-10-12

The owner requested a local official Android emulator/Android Studio installation
and an Android execution experiment. This establishes an Android x64 development
lane and a small CoreCLR post-install IL/unloading fixture. It does not establish
RuneCLR's production MapRunner, interpreted execution or phone performance.

## Installed environment

- Windows 11 x64, Intel Core i7-10700K, 32 GiB RAM. The official emulator's
  acceleration check reports WHPX installed and usable; guest startup also
  confirms acceleration. WMI CPU virtualization fields alone were misleading
  with the Windows hypervisor already active. No reboot was required.
- Android Studio Rabbit 1, official download version `2026.2.1.8`, build
  `AI-262.9437.185.2621.16467767`, bundled JBR `25.0.3`. The ZIP matched the
  official download page's SHA-256. Studio was extracted into its own directory,
  with desktop launch shortcuts and process-scoped SDK/AVD variables.
- Stable Android Emulator `37.2.12.0` / build `16428233`, platform tools
  `37.0.1`, command-line tools `23.0`, and NDK r27c `27.2.12479018`. Downloads
  matched Google repository metadata checksums; existing SDK installations and
  old AVDs were preserved. No global PATH modification was made.
- Dedicated `RuneCLR_API_35_x64` AVD: Android 15/API 35 Google APIs image,
  revision 9, four virtual CPUs, 3 GiB RAM, 720×1280 display and software GPU.
  The pre-existing system image was copied into the dedicated SDK. Guest kernel
  architecture is `x86_64`, page size 4096; managed process architecture is X64.
  Its advertised ARM64 ABI does not turn this into an ARM64-native test.
- SDK platform 36 and build tools 35.0.1 were copied from the installed SDK for
  APK compilation; the test APK targets API 35 with minimum API 24.

Official sources: [Studio download](https://developer.android.com/studio),
[emulator acceleration](https://developer.android.com/studio/run/emulator-acceleration),
[Google repository metadata](https://dl.google.com/android/repository/repository2-3.xml).

## Measured results

The dedicated AVD booted with both the pre-existing official emulator 36.1.9
and the newly installed 37.2.12. ADB connection, Java APK installation and
activity startup passed. A small Java activity wrote and read app-private data
and reported `storageRoundTrip=true`. This step did not execute .NET.

A separate debug APK packaged the official
[Android x64 CoreCLR runtime pack](https://www.nuget.org/packages/Microsoft.NETCore.App.Runtime.android-x64/11.0.0-preview.6.26359.118).
The managed host built with SDK `11.0.100-preview.6.26359.118`. The running
CoreLib identifies `11.0.0-preview.6.26359.118+ba53d0ed335bed4ab7bfd01988c8e3953ee5ffbe`.
That shipping runtime is different from the pinned desktop interpreter source
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. Its JNI/APK wrapper was compiled
from isolated copies of the pinned AndroidAppBuilder/MobileBuildTasks sources
using NDK r27c and JBR 25. No runtime source patch or replacement of an installed
.NET runtime occurred.

The final APK contains no late-map asset. After installing and first running
that APK, a new pure-IL `late-map.dll` was compiled with a unique marker and
copied into the app-private directory through ADB/run-as. The next run loaded
that assembly into twenty fresh collectible contexts.

| Check | Observed result |
| --- | --- |
| CoreCLR entry point on Android | .NET 11 Preview 6, Android API 35, X64; return code 42 |
| Managed arithmetic | Checksum `150015000` |
| IL compiled after APK installation | Marker `after-install-20261012-174102-73b296af` executed twenty times |
| Per-context static reset | All twenty markers reported `starts=1` |
| Collectible context retirement | 20/20 collected after execution returned and diagnostic GC |
| Installed APK and managed host unchanged | Device SHA-256 matched the pre-late-build hashes |
| Current desktop dependency resolver API | Constructor throws `System.PlatformNotSupportedException` on Android |

Final installed APK SHA-256:
`9f336d7e3bfb2caec560bfd047863b97da3c75795d415a702016dcd91c49832c`.
Host DLL: `c10a1e626c7f49bb53c8a9bacae874c2bac4a5c9a2b05db3cd88aafc198ee9e0`.
Post-install IL: `7740149e7036d71c290cb3226309413f8ccc9887df503307d5446c6190fa1fe4`.
Device-side hashes were checked after execution, not inferred from local files.

## Limits and next work

This original smoke was followed by the [full RuneCLR lifecycle experiment](android-lifecycle-experiment.md):
the explicit resolver and real harness pass 21/21, then 22/22 with post-install
IL. Its results supersede the runner/resolver gap below, while Android
interpretation remains unverified.

This is a controlled mini-fixture, not the existing RuneCLR lifecycle suite.
It does not test private dependency versioning, host resource recovery,
budget enforcement, hostile maps, or representative game frames. R2R and tiering
were disabled for this smoke with JIT allowed. No positive interpreter evidence
was collected; package contents or accepted switches do not establish it.

The separate resolver probe observed an actual constructor failure rather than
only reading UnsupportedOSPlatform attributes. Follow [the work sequence](work-sequence.md)
to implement explicit approved-package dependency resolution under #4/#5, then
run the complete lifecycle suite through an Android app wrapper. A matching
interpreter-enabled Android runtime build and positive method execution evidence
remain necessary. Physical Android/iOS device and mobile performance acceptance
remain open.

An earlier wrapper attempt used NDK 21 after lowering a version check in an
isolated template; its success was superseded by the final unmodified-template
NDK 27 build. Command-line tools 23's legacy sdkmanager entry incorrectly split
the NDK package argument and began downloading the emulator again. That owned
installer process was stopped; r27c was installed from Google's checksum-verified
archive. No Android CLI agent skills were installed.

## Evidence and reuse

Logs, source snapshots, APK/asset checks, installation timestamps, marker and
hash results are retained under `artifacts/android/20261012-windows-api35`.
`report.html` is a self-contained Chinese preview containing the Java activity
screenshot and the managed result. Machine paths and desktop launchers are
recorded in the ignored local setup document. The dedicated emulator was shut
down after testing; its apps/data remain available for the next launch.

Reuse `prepare.ps1`, `build.ps1` and `compile-late.ps1` from the evidence sources
with their recorded inputs; review their machine paths before reuse. The APK
installation must precede the late compilation. Upstream instrumentation extracts
packaged assets on each run, so the late DLL must stay absent from the APK.
