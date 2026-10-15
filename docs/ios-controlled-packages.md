# Controlled gameplay packages on the iOS simulator

The later [matching Release player](ios-r2r-release-packages.md) also passes
15/15 functional cases with fresh post-install packages. Its method-level
native capture remains pending; the successful Debug dumps below apply only
to this original Debug experiment.

On 2026-10-12, the unpatched source .NET 12 Debug CoreCLR runtime passed
**15/15** reusable `managed-il-gameplay-v1` package execution cases on an
ARM64 iOS 27.0 simulator. All package payloads were produced after app
installation and added only to the app data container. The 200-file installed
bundle remained unchanged. The native wrapper reported
`CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0`.

This extends the [selective host-IL simulator experiment](ios-simulator-experiment.md)
to current versioned source/imported packages, capability rejection, and private
dependencies. It uses the same [portable player harness](package-execution-tests.md)
as desktop validation. No runtime patch was required for this lane.

## Measured acceptance

| Cases | Observed result |
| --- | --- |
| Source, imported IL, source again | Fresh `starts=1`, both ticks, stop callback, entity cleanup and completed collectible-context retirement |
| Ordinary author exception, then valid source | Failure captured as host-owned text, stop callback and cleanup completed, next package succeeded |
| Tampered entry, rehashed forbidden entry, then valid source | Integrity and capability admission rejected the invalid packages; next package succeeded |
| Private helper A, same-name helper B, then A again | Declared helper versions 1.0.0.0 and 2.0.0.0 resolved independently; ordinary and generic statics restarted at 1 |
| Imported entry with private helper | Declared private helper executed and retired with its session |
| Rehashed forbidden private helper, then valid private package | Dependency capability admission rejected the invalid helper; next package succeeded |
| Player/compiler separation | Default context and app inventory contained no RuneCLR compiler, fixture producer or Roslyn assemblies |

The 15 cases ran together in one app process, PID 94211. All executed sessions
released owned entities and completed collectible-context retirement after the
runner returned. Forced GC is a diagnostic retirement check, not a frame policy.

The app reported `.NET 12.0.0-dev`, `iossimulator-arm64`, iOS 27.0.0, ARM64,
`DynamicCodeSupported=True`, and `DynamicCodeCompiled=False`. Successful
interpreter bytecode dumps independently establish execution of the newly
delivered script and helper methods:

| Successful `Compiled method:` dumps | Count |
| --- | ---: |
| `GameScript:OnStart` | 11 |
| `GameScript:OnTick` | 10 |
| `GameScript:OnStop` | 11 |
| `SharedHelper:Read` | 5 |
| `GenericCounter` generic helper | 5 |

The exact generic marker is ``GenericCounter`1``. Interpreter notices alone
are not counted as proof: `results.json` records notices and successful dumps
separately and requires positive successful dumps for all five method groups.

## Runtime and packaging provenance

- Separate source checkout base:
  `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`, tracked source clean.
- Native runtime and matching managed framework: source
  `iossimulator.arm64.Debug` build. All 181 baseline framework DLL hashes match
  the selected source Debug runtime pack.
- Source SDK `11.0.100-rc.1.26420.103` builds the bridge. The fixture operator
  uses the separately selected official .NET 11 RC1 SDK/runtime; neither SDK
  version identifies the app runtime.
- Source crossgen2 builds a composite containing framework libraries, the
  trusted test player, bridge and shared Abstractions contract.
  `RuneCLR.Runtime.dll` and `RuneCLR.Packages.dll` are excluded from this
  composite and retain byte-identical original IL. Every delivered entry and
  private helper is IL-only with no managed native header.
- `DOTNET_InterpList=1` and targeted `DOTNET_InterpDump` are diagnostic
  selections. There is no global `ReadyToRun=0` override.
- Dedicated iPhone 17 Pro simulator, UUID
  `FEFD0D26-C948-4D66-88D7-1EAC64FC91B1`, unique bundle ID
  `org.runeclr.packages.b7ce75f2f508`. Only this owned simulator was shut down
  after acceptance; its app and original evidence remain preserved.

Ad-hoc signing changes raw Mach-O signature bytes. Provenance therefore
compares the native UUID and every file-backed code/data section with the
source runtime, in addition to recording both raw file hashes. All 19
file-backed sections match; UUID `43658a5f2d7e3264861556d2379f2a7d`, sections
SHA-256 `ecf35102b7139beec238084fe855521f37a2b612bd9d8f7bdad7f24dfbf10979`.

```text
source libcoreclr: eece91b1e916e8965333a96fcd519ea6599949c841b75ca6488cf01333f4f544
signed libcoreclr: 1072b40284a6f7e9a2b372d359f354ca2633b447c781f08ce9f4047d33d8e4dc
source CoreLib IL: dc54cd96e677d6d409922b5f7b895623697434285cdb7f5d0647c76c7fafa9a5
crossgen2: 05d4646025e6b6982b9257bcf14fba0409bbf61d13bb3aeff20df7e0643ab608
portable Runtime: b224b60925de45c0b7e3c2c8cf57c0e06d6f113278452dd782ec9feb56fc4301
portable Packages: bf16e2abe3d085509bec1b3019b51915221bc4cebec683c206ebb538e1a74de8
portable Abstractions: 86bc966dd4e9f5f349b0c3d8fb869e180f76823af0ee6aa6e1ce64e7bbd16f31
```

## Post-install production

The initially installed player launched without payloads and reported
`PACKAGE_WAITING_FOR_POSTINSTALL_IL`, exit 0. The following UTC timestamps
establish subsequent source/imported package generation:

| Event | UTC |
| --- | --- |
| Installation completed | `2026-10-12T13:49:51.723317+00:00` |
| Operator production started | `2026-10-12T13:50:45.4283829+00:00` |
| Producer receipt generated | `2026-10-12T13:50:47.7676194+00:00` |
| Acceptance completed | `2026-10-12T13:54:38.618414+00:00` |

The operator creates nine package fixture directories plus `fixtures.json`.
The driver checks receipt timing, the portable contract image hash, profile,
complete inventory, and every manifest hash before copying packages to
`Documents/controlled`. It verifies all copied payload hashes and IL headers,
then checks the entire installed bundle again after execution. Compiler and
fixture-production tools stay on the operator machine.

## Reproduction and evidence

Prepare the source runtime and baseline wrapper described in the
[simulator experiment](ios-simulator-experiment.md), and transfer the four
portable player DLLs from the operator build. On the prepared Mac, use distinct
phase invocations so package production follows installation:

```sh
python3 eng/verify-ios-packages.py build --output /path/to/new-experiment \
  --runtime /path/to/runtime --baseline /path/to/source12-selective-experiment \
  --player /path/to/portable-player
python3 eng/verify-ios-packages.py install --output /path/to/new-experiment
# Produce fresh fixtures on the operator after installation; transfer them.
python3 eng/verify-ios-packages.py run --output /path/to/new-experiment \
  --packages /path/to/fresh-packages --produced-utc <operator-start-UTC>
python3 eng/verify-ios-packages.py cleanup --output /path/to/new-experiment
python3 eng/verify-ios-packages.py archive --output /path/to/new-experiment
```

The trusted producer command is:

```sh
dotnet RuneCLR.PackageFixtures.dll --framework-refs /path/to/fixed-references \
  --contract /path/to/portable-player/RuneCLR.Abstractions.dll \
  --output /path/to/new-fixtures
```

Build output must be new. `--resume-build` only reuses this experiment
after an unfinalized, uninstalled build failure; it rejects finalized output.
The run phase preserves an existing installed payload directory by refusing
to overwrite it. Device type and simulator runtime can be selected explicitly.

Local evidence: `artifacts/ios-controlled-packages-20261012/`. Its
`evidence.tar.gz` SHA-256 is
`507b086f8cee7c4c145b0fce281ed3a6694195d92fd6aa541c1d9bade9ea4489`
(121983 bytes). Original logs, state, results, producer receipt, portable
player DLLs, bridge/wrapper sources, driver and crossgen response file are
included; giant framework/native artifacts remain in the source experiment.
Remote experiment: `/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/controlled-packages-20261012/run`.

Two tooling failures preceded successful acceptance and remain in the archive:
the initial bundle guard incorrectly matched framework
`System.Runtime.CompilerServices` filenames, and the first run request rejected
a seven-digit .NET fractional timestamp on Xcode Python 3.9. The guard now
matches operator/compiler assembly prefixes precisely; timestamp comparison
accepts the .NET precision while preserving raw evidence. Both failures occurred
before payload execution and do not represent CoreCLR failures.

## Scope

This establishes post-install controlled-package loading, interpreted execution,
private/generic static reset, ordinary author-failure recovery, and completed
retirement on this ARM64 simulator runtime. It does not establish physical
iPhone support, App Store deployment, frame performance, package authentication,
hard execution budgets, or a hostile-code sandbox. The
[all-host-R2R crash investigation](ios-r2r-investigation.md) remains a separate
runtime experiment; this passing selective host-IL layout does not resolve it.
