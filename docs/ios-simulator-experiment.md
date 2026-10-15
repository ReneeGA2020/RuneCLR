# CoreCLR UGC script lifecycle on iOS simulator

On 2026-10-12, the pinned .NET 12 Debug source runtime and official .NET 11
RC1/Preview 6 apps ran the actual RuneCLR harness
on an iOS 27 ARM64 simulator: **21/21 baseline**, then **22/22 with IL compiled
after app installation**. This result uses a selective packaging configuration:
trusted framework, test entrypoint, bridge and Abstractions are composite R2R;
`RuneCLR.Runtime` and UGC assemblies remain IL. It does not establish that a
fully R2R-compiled RuneCLR host works, or that physical iPhone acceptance passed.

The current primary source lane supplies direct interpreter diagnostics for
the production script callbacks, including post-install LateMap. Official
Release package results retain their separate evidence level.
The later [compiled interface investigation](ios-r2r-investigation.md) captures
the original PC-zero failure under LLDB and adds smaller passing controls. The
subsequent [minimal reproduction](ios-r2r-minimal.md) captures stale cache
mapping/address reuse. A private conservative candidate passes
[five-group Debug simulator acceptance](ios-r2r-fix-validation.md), including
the unchanged all-host-R2R harness. The unpatched results below remain distinct;
upstream, Release and physical-device acceptance are outstanding.

## Environment and separate build lanes

The owner-supplied remote Mac is Apple M1/16 GiB, macOS 27.0.1, Xcode 27.0.
The dedicated simulator is iOS 27 ARM64, UUID
`FB0B68D4-E1A6-42F0-B6D4-FB3A2A8B12FD`. Global installations and unrelated
projects/simulators were preserved. See [earlier preparation](remote-mac-experiment.md).

The measured Preview 6 lane uses:

- Official `Microsoft.NETCore.App.Runtime.iossimulator-arm64`
  `11.0.0-preview.6.26359.118`, provenance dotnet/dotnet
  `ba53d0ed335bed4ab7bfd01988c8e3953ee5ffbe`. Package SHA-256:
  `2d04df459937ca3b8c7fc814e3a524392314bdbc21e5d76fb5cb0b569a822cca`.
- Matching official `Microsoft.NETCore.App.Crossgen2.osx-arm64` Preview 6 and
  the private Preview 6 SDK used for earlier Mac preparation.
- CoreCLR hosting wrapper, Apple clang/linker and ad-hoc simulator signing.
  Globalization invariant mode is enabled for this experiment.
- Crossgen2 `--targetos:iossimulator --targetarch:arm64 --obj-format:macho
  --composite --inputbubble --parallelism:2 --resilient --optimize`; link the
  Mach-O object to a dylib before signing/loading it. Exact response files and
  wrapper sources are in the evidence archive.

A separate unpatched source checkout is pinned to
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. Its Debug iOS simulator CoreCLR,
framework and packs have built with 0 warnings/errors. Its own SDK is
`11.0.100-rc.1.26420.103`. These binaries are not substituted into the Preview 6
evidence. Runtime/app diagnostic results from that lane are recorded separately.
The checked-out source product version is **12.0.0**, from official
`dotnet/runtime` main; the RC1 SDK is its build tool, not its runtime product
version. Preview 6 is a historical official-package comparison, not the current
upstream release: .NET 11 RC1 was published on 2026-09-08. A separate RC1 package
comparison now passes with the selective layout below; earlier measurements
remain labelled Preview 6.

Xcode 27 rejects the old iOS 13 deployment target and requires UIKit scenes.
The source runtime build uses a private CMake deployment override of 15.3; the
in-tree app builder needs the same override through a private CMake wrapper.
The standalone Preview 6 shell also uses 15.3 and a scene manifest/delegate.
These are experiment packaging adaptations, not runtime-source patches or
proof of support for all device OS versions starting at 15.3.

## First probe: post-install IL and twenty contexts

The independent mini-fixture successfully initializes CoreCLR, loads the trusted
R2R composite, and executes a DLL compiled only after installation. The DLL has
`ILOnly=true` and no managed native/R2R header. All twenty executions report
static counter 1 and collectible contexts; all twenty weak references clear
after execution frames return and diagnostic GC. Host identities remain unchanged.

Actual runtime reports `OperatingSystem.IsIOS=True`, RID `iossimulator-arm64`,
architecture ARM64, `IsDynamicCodeSupported=True` and `IsDynamicCodeCompiled=False`.
Support for dynamic code here is not permission to dynamically compile native
code. The Release runtime does not emit the requested per-method interpreter
dumps. Executing genuinely new non-R2R IL with dynamic compilation disabled is
functional simulator evidence; it is not a per-method dump proof.

## Full production harness and retained failure

The thin bridge invokes the unmodified executable test harness. Original
production binaries/source snapshots are retained; the source snapshot reflects
uncommitted work rather than only the repository HEAD. Fixture/private assemblies
stay in `fixtures`, `dependency-a` and `dependency-b`, excluded from composite
inputs and root TPA enumeration. The official framework inventory is readable
beside the host. No desktop resolver or map `.deps.json` is needed.

**All-host-R2R configuration fails:** the first repeated-session case crashes
with `SIGSEGV`, PC 0, at R2R `MapRunner.Run+760` calling `IMapScript.OnTick`.
The crash contains `RhpInterfaceDispatch1`, `InterpExecMethod` and
`ExecuteInterpretedMethod` frames. It is a process crash, not a recoverable
script exception. The original log/crash report remains preserved.

**Selective configuration passes:** exclude only `RuneCLR.Runtime` from the
composite and retain its original IL. Framework, bridge, tests and Abstractions
remain R2R. Production `OnTick` interface calls are unchanged; no reflection
replacement, global `ReadyToRun=0`, mode 3 or runtime patch is introduced.
PE-layout evidence verifies Runtime and scripts have no R2R header, while
tests/bridge/Abstractions do.

| Acceptance slice | Observed result |
| --- | --- |
| Full baseline | 21/21, CoreCLR initialize/execute HRESULT 0, managed exit 0 |
| Session behavior | Twenty repeated sessions, fresh statics, A -> B -> A private versions/generic state, ordinary failures, cooperative quotas, resource cleanup and collection pass |
| Package behavior | Missing/changed dependencies, identity/version/hash/path/duplicate/reserved-name failures and Default collision cases pass |
| Post-install IL | Exact LateMap source compiled after installation against the packaged Abstractions binary; 22/22 passes, log 42, entity reclaimed and context collected |
| Host identity | Six host files unchanged and match installed bundle; late DLL local/device hash matches |
| Compilation/retirement | Dynamic native compilation reported disabled; diagnostic collection observed, not a per-frame GC policy |

Baseline and post-install runs use separate native app processes (PIDs 77369 and
77587); each harness run itself tests repeated sessions within one process.
The last Default-collision test intentionally seeds Default, so it is not
appropriate to invoke the entire harness twice in one app process.

Installation completed at `2026-10-12T10:56:04Z`; late compilation started at
`2026-10-12T10:56:47Z`. Late DLL SHA-256:
`32431b04602123390422488a64ab4eb00f856873263940fc54bb5683690db09e`.
Its metadata marker is
`after-harness-install-20261012T105647Z-14F3628A-3844-47A4-99B5-103D42B1B774`.

## Official .NET 11 RC1 comparison

The newer official `Microsoft.NETCore.App.Runtime.iossimulator-arm64` and matching
`Microsoft.NETCore.App.Crossgen2.osx-arm64` are both `11.0.0-rc.1.26425.128`,
provenance dotnet/dotnet `3551975be08744f0418857c5bed8ab1545c5dd47`.
The wrapper/template/header ABI also comes from that revision. No Preview 6 or
source .NET 12 runtime/framework/compiler outputs are mixed into this lane.
Bridge and late IL use private SDK `11.0.100-rc.1.26420.103`; the original
portable harness snapshot is unchanged. Runtime and SDK identities are distinct.

The all-trusted-host-R2R configuration still crashes in `RepeatedSessions`: PC 0,
`SIGSEGV`, `MapRunner.Run+748`, no full test/suite pass. The selective layout
excluding only RuneCLR.Runtime from R2R passes **21/21 baseline and 22/22 with
post-install IL**. Framework/tests/bridge/contract stay R2R; production interface
callbacks are unchanged. Actual runtime reports .NET 11 RC1, iOS 27 ARM64 and
dynamic native compilation disabled. Release emits no requested per-method dumps.

Installation completed at `2026-10-12T11:30:46Z`, baseline completed at
`11:30:49Z`, and late compilation began at `11:31:37Z`. Late DLL SHA-256:
`f9ba03bfb0620ddae5a4eaf2f92ce717c8828c8309e8e2a6eeff00301795e5b5`;
its PE is IL-only with no R2R/native header. All 220 bundle files remain unchanged
and match the installed bundle. Bundle manifest SHA-256:
`2f7985e5fcf390ae4e54331345eadcc86b6906eca756e359dc465e760fa7b6d3`.
Baseline and late runs use fresh app processes, PIDs 82056 and 82205; the
all-R2R failure is PID 81784. Each harness tests repeated sessions itself.

Evidence: `artifacts/ios-rc1-transfer/evidence/REPORT.md`, `logs/results.json`,
`all-r2r/logs` crash records and `selective-runtime/logs` successful traces,
PE checks, provenance and bundle verification. Archive SHA-256:
`4fa2c7cae85ba87ce77b23147f56cf50e230ed6e380d4b7df7d2445119c5a3bc`.
Runtime package SHA-256:
`ae4a7897ed271a0590c4dd08ea5270a4b884495239412d42dd58bdf10143fda7`;
crossgen2 package SHA-256:
`69e073cf75ed94ed8f4381533826533dba4bd7ad361cdd44ca54db5d3a189e52`.
This remains simulator acceptance under the stated packaging workaround,
not physical-device support or a fix for the native-host interface boundary.

## Pinned Debug interpretation proof

The separate source-built Debug lane now also executes genuinely post-install
non-R2R IL on iOS 27 ARM64. It reports `.NET 12.0.0-dev`, 16 KiB pages and
`IsDynamicCodeCompiled=False`, with trusted host/framework composite R2R.
Actual target compiler definitions include `FEATURE_INTERPRETER` and
`FEATURE_COLLECTIBLE_TYPES`, and exclude `FEATURE_DYNAMIC_CODE_COMPILED`.

The late DLL is compiled after the initial installed app run, absent from its
original bundle, and contains no native/R2R header. Twenty collectible contexts
return static counter 1 and all twenty collect after stacks return. The Debug
log contains **40 interpreter compile notices** for `LateMap.Start/Marker`,
plus **20 successful bytecode/IR dumps for each method**. This supplies direct
map-method interpretation evidence in addition to runtime feature reporting.
The entire installed bundle's hashes remain unchanged after late compilation.

This is a reflection-based mini-fixture, not the complete RuneCLR harness or
proof that the compiled-host interface issue is fixed. The same-source fully
R2R-host harness comparison below also reproduces a native crash.

Evidence: `artifacts/ios-pinned-debug-transfer/pinned-debug-evidence`, including
`REPORT.md`, `results.json`, target compiler definitions, fixture/packaging
sources, full build/publish logs and `source-late-run.log`. Archive SHA-256:
`78bdd2d4275847c00b0acb55c31e0da1c025b41c3823c97726ff7783e8eb4ed4`.
Runtime-pack SHA-256:
`16c8b1c4ed159d4fdcbfc1394812a67f88bd0a4145a893b4e9ed98113c477ad4`.
Late DLL SHA-256:
`107ac400330570990a4144030de210d19094f7881c7c8ee6fb375c9644f19582`.
Marker: `after-install-20261012T110259Z-B835D18B-6CF0-4C44-9296-9F99DB7D84E3`.
Source branch `runeclr/iossim-baseline` has no tracked runtime changes. The
dedicated source simulator `A01112EF-5B24-4692-8EBC-B095F35C8061` was shut down
after the mini run.

## Pinned .NET 12 full R2R-host comparison

The unpatched Debug runtime at the same source commit also ran the original
production harness with framework, bridge, tests, RuneCLR.Runtime and
Abstractions all in trusted composite R2R. The runtime, CoreLib, framework and
crossgen2 all come from that source build; no Preview 6 runtime/compiler outputs
are reused. Compatible `net11.0` managed harness inputs retain their own identity.

CoreCLR initializes successfully and reports `.NET 12.0.0-dev`, iOS 27 ARM64
and dynamic native compilation disabled. During the first `RepeatedSessions`
test it terminates with `SIGSEGV`, PC 0, at `MapRunner.Run+776`; no complete
test case or suite pass is reported. The interpreter log shows the first
CounterMap constructor/start/tick/stop followed by a second constructor/start.
The original harness advances only after its first-session outcome, resource
and collection assertions, so the crash is during repeated-session execution,
not proof that the first individual session could never execute.

This reproduces the native-host/interpreted-script boundary problem on the
newer source base. At the time of this original experiment, an interface cache
surviving collectible retirement was a hypothesis. The later
[minimal capture](ios-r2r-minimal.md) and
[candidate comparison](ios-r2r-fix-validation.md) supply the follow-up evidence. The source
Debug selective-Runtime-IL variant below also passes the original full harness.
The official-package passes and the .NET 12 mini remain separately recorded
configurations. Physical-device acceptance is open.

Evidence: `artifacts/ios-preview6-transfer/pinned-debug-harness`, including
`REPORT.md`, `logs/results.json`, the original managed log, OS crash report,
native frames, matching source-artifact hashes and packaging response file.
The enclosing directory name is historical; the runtime in this comparison
is .NET 12. Archive SHA-256:
`061b43c67d1b520c3ab6745156b8afadc8178cd5ab913385ce9b975ada8f02dc`.
The dedicated comparison simulator was shut down after capture.

## Pinned .NET 12 selective full harness

The same unpatched Debug source `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`,
matching .NET 12 CoreLib/framework/crossgen2/native ABI, now passes the actual
production harness with RuneCLR.Runtime kept as IL. Trusted framework,
bridge, tests and Abstractions remain composite R2R; script/private assemblies
remain IL in their original subdirectories. Production `IMapScript` callbacks
are unchanged. This is the current primary source baseline, not a runtime patch.

Baseline **21/21** passes in PID 83355. The subsequent fresh-process run in
PID 83462 passes **22/22**, including the exact LateMap fixture compiled after
installation and the successful baseline run. Positive Debug method notices
cover scripts/private generics, and successful interpreter IR dumps include
CounterMap.OnTick and LateMap constructor/OnStart/OnTick/OnStop. Thus the
full suite now has its own method evidence, independently of the older mini.

All 220 bundle files remain unchanged and match the installed bundle. Bundle
manifest SHA-256:
`c0c148a7ae3f29859785b279f161ff217329409669ae1e4c9ee362c857ffd0d9`.
Late execution asserts log 42, created/released entity and completed context
collection. Diagnostic GC is still not a per-frame policy. The source
all-host-R2R failure above remains retained and unresolved; the passing layout
does not establish unrestricted native-host interface compatibility.

Source runtime/late IL build SDK is `11.0.100-rc.1.26420.103`. The portable
bridge IL reuses the previous snapshot compiled with SDK
`11.0.100-preview.6.26359.118`; its native R2R image is newly generated by
matching source .NET 12 crossgen2. These input compiler identities do not
change the actual executing runtime's .NET 12 identity.
Installation: `2026-10-12T11:43:21Z`; baseline completion: `11:43:25Z`;
late compilation: `11:45:05Z`. Late DLL SHA-256:
`cc8e273f626b963c47d5143de88ee2cce1c324409a458473653e65e3965c17a3`.
It is IL-only without a native/R2R header.

Evidence: `artifacts/ios-source12-selective-transfer/evidence`, including
`REPORT.md`, `logs/results.json`, original baseline/late logs, PE layouts,
source identities and bundle verification. Archive SHA-256:
`b4736a33d3e0a22fccff3e10e8e5be44bad08c44f74cd47b1c8cbb68a99b1564`.
Each run records 20 CounterMap.OnTick compilation notices, 9 private-generic
and 66 Runtime method notices; the late run adds its four script methods.
These are diagnostic occurrences, not unique-method or executed-instruction
counts. The dedicated simulator is shut down after both successful runs.

## Next compiled-interface investigation (planned)

Reduce the retained full-suite failure to one shared interface, one trusted
host call site and one post-install IL implementation. At the fixed source
base, run twenty load/call/retire cycles and record callbacks and completed
collection after execution frames return. Compare trusted-host R2R versus
host IL, and repeated retirement versus retaining the same context. Keep
runtime/framework/compiler and the managed inputs identical within each
comparison. Positive method diagnostics, the exact failing cycle and original
native crash frames should accompany any upstream report.

This is a planned reduction, not a completed minimal reproduction. It tests
whether retirement or native call-site selection is relevant without assuming
a stale-cache root cause. Preserve the passing packaging workaround and
ordinary lifecycle work while investigating; do not patch the runtime until
the failing boundary is isolated.

## Evidence and remaining acceptance

Local compact evidence: `artifacts/ios-preview6-transfer/mini` and
`artifacts/ios-preview6-transfer/harness`. Reports, native/managed sources,
response files, raw successful/failed logs, source archives, hash metadata and
PE-layout checks are included; original runtime packages/app binaries remain
on the Mac. Archive SHA-256 values:

```text
evidence-preview6.tar.gz: b44baf1e7dbe91e81f2a1ef1a5a7ff95b0ac4890f27fc2b9dcb1a8907f26052e
evidence-harness-preview6.tar.gz: 5a87eb329a90435259f07697c65aa3c3a6c9b900f7fd8f1f99ec24a6d9693530
```

Remote experiment root:
`/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/preview6-experiment`.
The dedicated Preview 6 simulator was shut down after validation.

Keep [#2](https://github.com/ReneeGA2020/RuneCLR/issues/2) open: physical-device
execution/signing, representative performance and the compiled-host interface
boundary still need acceptance. This controlled experiment does not implement
hostile-code isolation, hard execution/memory limits, controlled author intake
or UGC distribution approval. The newer pinned Debug comparison still fails
at the compiled-host boundary; upgrading the source alone has not resolved it.
