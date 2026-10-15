# Full RuneCLR lifecycle on Android

On 2026-10-12, the complete executable `RuneCLR.Runtime.Tests` harness ran in an
Android 15 x64 emulator using the new [explicit package resolver](package-resolution.md).
The baseline passed **21/21**. After APK installation, newly compiled IL added
the late-script case and passed **22/22** without republishing the host.
Both the historical Preview 6 package and the subsequent official .NET 11 RC1
comparison pass these slices. Runtime-package provenance is separate from the
.NET 12 source checkout used for the app-builder/header snapshot.

This follows the earlier [mini-fixture and resolver failure probe](android-emulator-experiment.md).
It uses the actual production runner and original test harness through a thin
Android entrypoint wrapper, rather than duplicating lifecycle logic.

## Historical Preview 6 inputs and packaging

- Official `Microsoft.NETCore.App.Runtime.android-x64`
  `11.0.0-preview.6.26359.118`, provenance
  `ba53d0ed335bed4ab7bfd01988c8e3953ee5ffbe` from dotnet/dotnet.
- The app builder/header snapshot comes from the separate unpatched runtime
  checkout at `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`; this is not the
  provenance of the official runtime binaries.
- Windows SDK 11 Preview 6, Android Studio JBR, NDK r27c, build tools 35.0.1,
  compile API 36 and target API 35. The dedicated WHPX AVD uses API 35, x86_64
  and a 4096-byte page size.
- Full official framework assets, including `Microsoft.NETCore.App.deps.json`,
  are packaged. Map entry/private DLLs stay in fixture subdirectories, outside
  root assets/Default framework probing.
- APK asset inspection confirms the late DLL is absent. After installation,
  original late-fixture source is compiled in an independent temporary project
  against the packaged Abstractions binary, then copied into app-owned storage.

`eng/verify-android.ps1` reproduces the test with the prepared SDK/runtime-pack/
builder inputs documented by the earlier experiment and machine-local setup.
Its defaults refer to this machine; review parameters before reuse elsewhere.
`-BuildOnly` packages without starting an emulator. A fresh evidence directory
and unique experiment package name prevent stale results/signing conflicts.

```powershell
./eng/verify-android.ps1
```

## Results

| Check | Observed result |
| --- | --- |
| Existing lifecycle/recovery suite | Static reset, twenty sessions, failures, stop errors, quotas, host cleanup and post-stack collection passed |
| Explicit private dependencies | A -> B -> A version isolation and generic static reset passed, without map `.deps.json` |
| Invalid packages | Missing DLL, metadata/version mismatch, escaping path, incorrect hashes, duplicate/reserved identity and direct-constructor bypass rejected |
| Default collision | Undeclared private dependency rejected despite a same-name assembly loaded in Default; explicitly declared session dependency remains fresh |
| Baseline | 21/21, exit code 0 |
| Post-install IL | 22/22, exit code 0; host/APK unchanged |
| Dedicated emulator | Shut down after test; historical apps and evidence retained |

The APK was installed at `2026-10-12T10:33:57.2761908Z`; late compilation began
at `2026-10-12T10:34:05.8261417Z`. Device-side hashes match local APK, wrapper,
harness and late DLL:

```text
APK: A3D7FD06BE09FA6FB9B080008DDC11F6597A8583810BF2BA0A6386F569C4BBBC
wrapper: 811DD3B3778AA5D5B2E179CAF822C9E66350D889C66C315F8E32F4C5E26E9814
harness: F6C9DD5F42996288AC1E947330E337CCEE9088581352FF3E389165A256CA3D20
late: AD863572B10D71E42D3155C2F682FF1CBB3F2B0F5EBF70A23716AAB198EDC1CB
```

Evidence: `artifacts/android/lifecycle-20261012-183252-db77b3b0021643669ac88772d8f06ce5`.
It contains source/runtime hashes, asset inventory, build/install logs, both
harness outputs and result JSON. The self-contained `report.html` is a Chinese
preview. Generated wrapper/source snapshots are private experiment artifacts,
not a production Android SDK integration.

## Official .NET 11 RC1 comparison

The official Android x64 runtime package `11.0.0-rc.1.26425.128`, provenance
dotnet/dotnet `3551975be08744f0418857c5bed8ab1545c5dd47`, passes **21/21**
baseline and **22/22** with post-install IL in a fresh APK/app process. Both
runs report `.NET 11.0.0-rc.1.26425.128`; device-side hashes match the local
APK, host, harness and late DLL. APK/host identities remain unchanged.

The app-builder/header snapshot remains source commit `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`.
The build tool for this comparison is the private source-build SDK
`11.0.100-rc.1.26420.103`; it does not identify the packaged runtime version.
The same dedicated Android 15 x64 AVD/4096-byte page setup is used and was shut
down afterwards. R2R/tiering are disabled; JIT is allowed and interpretation
is not demonstrated.

Installation: `2026-10-12T11:25:30.5428758Z`; late compilation:
`2026-10-12T11:25:39.0733975Z`. Late DLL SHA-256:
`5f623d385d43922589747b9334321051a7cf68e335025c4a1d32b57bd73ef618`.
Evidence: `artifacts/android/lifecycle-20261012-192408-92100d662c8147a4885db2df892abd24`,
including request/evidence JSON, original logs and device hash reads.

The driver now accepts `-RuntimePackDirectory` for an extracted official
Android-x64 package and `-DotnetExecutable` for a selected SDK executable.
Choose them explicitly to reproduce this comparison; the original template's
default package remains historical Preview 6. These parameters do not install
or replace the system runtime.

The first complete run passed 20/21: one test assumed CoreLib `Assembly.Location`
was nonempty. The test now falls back to the real packaged DLL in the application
directory and retains the reserved-identity assertion. A later packaging attempt
hit `INSTALL_FAILED_UPDATE_INCOMPATIBLE` because separate debug keys signed the
same package; the driver now uses unique experiment package IDs. Failed runs
remain in their original evidence directories.

## Limits and next step

The official Android runtime allows JIT. R2R and tiering are disabled for this
experiment; no positive interpreter-method evidence was collected. Therefore
this result establishes Android package/lifecycle compatibility, not interpreted
Android execution, ARM64 phone performance or an enforced UGC sandbox.

The later [controlled gameplay package increment](android-controlled-packages.md)
now passes source/import and failure/rejection recovery on the new host snapshot.
Continue with an interpreter-enabled Android runtime experiment with positive
execution diagnostics and versioned private-dependency mobile coverage. iOS simulator
and physical-device acceptance are separate. Collection uses diagnostic forced
GC, not a per-frame policy.
