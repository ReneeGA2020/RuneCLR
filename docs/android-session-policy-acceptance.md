# Android private session-policy APK driver

Prepared on 2026-10-13. No matching Android product, APK, installation or
application execution was completed by this driver during preparation. Android
session-policy enforcement remains unmeasured. The existing [stock Android
baseline](android-controlled-packages.md), [Windows required-policy result](session-interpreter-validation.md)
and [iOS simulator result](ios-session-policy-acceptance.md) are separate evidence.

[verify-android-session-policy.ps1](../eng/verify-android-session-policy.ps1)
implements a private source-layout consumer. It does not request or impersonate
a shipping runtime NuGet package. The [Android build plan](android-session-policy-plan.md)
and [isolated source-build driver](../eng/android-session-policy-build.py) own
the native build. The APK driver never builds CoreCLR or the production RuneCLR
solution, starts an emulator, changes the installed desktop runtime, clears an
old app's data, or updates an old APK. Device phases require an explicit,
already-running device serial and check its actual x86_64 kernel and owned AVD.

## Private layout contract

Supply explicit SourceLayoutDirectory and LayoutReceiptPath. The exported root
contains managed/, native/, java/, headers/ and provenance receipts. Every listed
runtime/framework file must come from the reviewed combined source. NDK runtime
dependencies have a separate toolchain owner. A source build's minimal native
results.json does not by itself constitute a complete framework layout.

~~~json
{
  "schema": "runeclr.android.session-policy.layout.v1",
  "success": true,
  "base": "0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de",
  "commit": "1724cdec553a7aff7a373a271a4be612651c7625",
  "tree": "71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2",
  "sourceTrackedClean": true,
  "target": "android.x64",
  "nativeConfiguration": "Checked",
  "frameworkConfiguration": "Release",
  "features": { "interpreter": true, "dynamicCodeCompiled": true },
  "files": [
    { "path": "native/libcoreclr.so", "sha256": "ACTUAL_SHA256", "role": "runtime", "sourceCommit": "1724cdec553a7aff7a373a271a4be612651c7625" }
  ],
  "receipts": [
    { "path": "receipts/native-results.json", "sha256": "ACTUAL_SHA256", "kind": "native-build" }
  ],
  "evidenceFiles": [
    { "path": "receipts/native-build.log", "sha256": "ACTUAL_SHA256" }
  ]
}
~~~

The shortened example shows the schema, not an accepted complete layout. The
actual files array must include:

- native/libcoreclr.so, libclrinterpreter.so and target libclrjit.so, roles
  runtime/interpreter/jit. All packaged native files must be ELF64 little-endian
  x86_64. Mac-host crossgen2, libjitinterface and other Darwin tools do not enter
  the APK.
- managed/System.Private.CoreLib.dll, role corelib; the complete matching
  Android framework DLL inventory and Microsoft.NETCore.App.deps.json, role
  framework. CoreLib is the matching Checked native build's product; the other
  framework libraries are same-source Android Release products.
- native/libSystem.Native.so and all other Android OS libraries required by
  that framework, role os-native. Any libc++_shared.so dependency uses
  ndk-native and toolchainReceiptSha256. Resolve actual DT_NEEDED recursively
  against APK libraries and the target Android system libraries.
- headers/hosts/* including coreclrhost.h and
  headers/native/corehost/host_runtime_contract.h, role header. These are the
  matching candidate headers used to compile the JNI wrapper.
- java/libSystem.Security.Cryptography.Native.Android.dex, role android-java,
  generated from the matching source by AndroidLibBuilderTask. The official APK
  builder packages it as a separate classesN.dex; the driver checks that its
  exact bytes appear once in the APK. The original jar is retained as a build
  evidence file. Java dependencies are separate from ELF DT_NEEDED closure.
  The extra installed files copy is also hash checked; the immutable APK binds
  the actual class-loader input.

Six immutable JSON receipts are required, each bound by SHA256:

| Kind | Required observed fields |
| --- | --- |
| native-build | success=true, exact commit/tree, target=android.x64; original minimal build receipt is accepted here |
| framework-build | success=true, exact commit, target=android.x64 |
| source | source/base/tree/clean working-tree evidence from the isolated worktree |
| features | featureInterpreter=true, featureDynamicCodeCompiled=true, compileEvidenceVerified=true, backed by real compile commands/generated feature inputs |
| trim-api | corelibSha256, fixedBridgeSignaturesVerified=true, privateApiCount=3 for the three exact private policy methods, checked in the deployed CoreLib |
| elf-needed | abi=x86_64, allDependenciesResolved=true, actual native dependencies and their platform/toolchain owners |

Put original command logs, source hashes, CMake cache/compile commands, generated
feature inputs, CoreLib pre/post-trim inspection and dependency reads in
evidenceFiles. The driver copies these bytes and the six receipts into its new
provenance/ archive. These attestations must be generated from inspection of the
actual build; a successful restore, environment switch or filename is not
compile evidence or a native policy acknowledgement.

## Frozen host and APK topology

HostInputReceipt has a files object mapping POSIX relative keys to SHA256 and a
rootsAtSnapshot object mapping player, lifecycle, sample and optional selection
to existing frozen output roots. Values can also be objects containing sha256.
The current iOS snapshot schema can be reused as an input-format example;
create a new snapshot if adding the Android inline fixture. It is not evidence
of a fresh Android build or run.

Only framework, RuneCLR.Runtime, RuneCLR.Packages, RuneCLR.Abstractions, the
current executable test/sample DLLs and SelectionProbe's trusted Host/Contract
enter root managed APK assets. They retain their exact original IL hashes and
use the ordinary Android native/JIT path. This differs from iOS's no-JIT trusted
R2R composite. Author maps, dependency-a/b, sample maps and probe payloads remain
pure IL in child directories. The Android ordinary default-context dependency-A
seed can compile natively; the same private bytes inside required contexts must
interpret. The iOS special R2R seed component is not reused.

No author payload, late map or controlled package enters the APK. The driver
inspects the actual nested assets.zip and each APK native entry, checks exact
staged hashes and rejects author/operator compiler material in root assets. It
records the generated JNI shim's packaged native hash, original/modified builder
source hashes, matching header hashes, wrapper sources, SDK and tool identities.
The existing APK builder mechanical snapshot may be based on official 0d73;
that provenance is recorded explicitly. Its runtime headers and runtime bytes
come from the matching candidate, and its private JNI resource is separately
modified and hashed. No shipping nuspec/commit is borrowed to label this APK.

The wrapper uses the three fixed private signatures on trusted CoreLib through
CreateDelegate. Before loading any author assembly it requires version1,
default-policy0, ordinary collectible-policy0 and required collectible-policy1.
It then passes --require-interpreter to the unchanged current production CLI
entrypoints. Reflection does not scan author assemblies. Both Console.Out and
Console.Error use one owned managed.log writer, preserving SelectionProbe's
explicit Console.SetOut(Console.Error).

## Phases and commands

Use PowerShell7 and an absolute private SDK when the installed SDK is unsuitable.
Build changes only its fresh evidence directory. CPATH, C_INCLUDE_PATH,
CPLUS_INCLUDE_PATH, LIBRARY_PATH, SDKROOT and MACOSX_DEPLOYMENT_TARGET are removed
for the local NDK subprocess environment and restored afterwards.

~~~powershell
$driver = './eng/verify-android-session-policy.ps1'
$layout = 'D:/RuneCLR-Android/private-source-layout-NEW'
$run = 'E:/RuneCLR/artifacts/android/session-policy-NEW'
$sdk = 'E:/RuneCLR/artifacts/toolchains/dotnet-11-rc1/dotnet.exe'
& $driver -Phase Validate -Offline -SourceLayoutDirectory $layout -LayoutReceiptPath "$layout/layout.json" -HostInputReceipt 'NEW-host-inputs.json'
& $driver -Phase Build -Offline -SourceLayoutDirectory $layout -LayoutReceiptPath "$layout/layout.json" -HostInputReceipt 'NEW-host-inputs.json' -EvidenceDirectory $run -DotnetExecutable $sdk
~~~

The following are future explicit device phases, not commands executed during
preparation. Install requires an unused generated package ID, uses no -r and
records installedUtc. Exact validated APK managed assets are materialized before
the first app startup so device hashes can be read. Produce runs the prebuilt
operator fixture generator and compiles only an isolated late-map source copy
after that timestamp. It records the operator SDK, generator, fixed references,
approved contract, generated payloads and source hashes; it does not rebuild the
player. Transfer permits only child author directories, checks pure IL CLR
headers/no ReadyToRun directory and records actual device sha256sum reads.

~~~powershell
& $driver -Phase Install -EvidenceDirectory $run -DeviceSerial emulator-5556
& $driver -Phase Produce -EvidenceDirectory $run -OperatorDotnetExecutable $sdk -FixtureGenerator 'E:/RuneCLR/tools/RuneCLR.PackageFixtures/bin/Release/net11.0/RuneCLR.PackageFixtures.dll' -FrameworkReferences 'E:/RuneCLR/tests/RuneCLR.Packaging.Tests/bin/Release/net11.0/refs'
# Use the NEW payloads-<nonce> directory reported by Produce.
& $driver -Phase Transfer -EvidenceDirectory $run -DeviceSerial emulator-5556 -PayloadDirectory 'NEW-payload-directory'
& $driver -Phase Run -EvidenceDirectory $run -DeviceSerial emulator-5556 -Lane all
& $driver -Phase Run -EvidenceDirectory $run -DeviceSerial emulator-5556 -Lane required -ProbeAssessorPath './eng/android-session-policy-probe.py'
& $driver -Phase Archive -EvidenceDirectory $run
~~~

The production all lane requires current lifecycle24/24 including late IL,
packages15/15 and three sample contexts collected. The lifecycle harness without
late IL has23 cases; it is not accepted as the requested24-case lane. It also
requires native initialization/managed exit0, actual policy query1, global
diagnostic0/mode0, positive author bytecode and a native MapRunner JIT summary.
Production executable tests use return0, not official runtime test return100.

Probe lanes are required, ordinary, required-refusal, unmarked-fallback,
required-boxed and optionally required-inline/ordinary-inline. All use mode0,
global diagnostic0, R2R1, tiering1 except unmarked-fallback uses mode1 for the
real compiler-skip fallback control, and inline uses tiering0. Diagnostics enable
InterpList1, full InterpDump, all JIT summaries and a separate JitStdOutFile;
diagnostic output does not itself enable collectible interpretation. The refusal
filter is exactly SelectionUGC.Refusal.Entry:Reject. Variant args use the actual
Refusal/Boxed/Inline directories. Inline lanes reject a fixture identity without
plugin/Inline/SelectionProbe.Inline.dll; the historical iOS selection ZIP does
not contain it. Selection strict assessment is delegated to the
[Checked Android probe assessor](android-session-policy-probe.md).

## Owned run receipts and acceptance boundary

Each Run creates run-<lane>-<nonce>/ with request.json, results.json,
native.log, jit.log, managed.log, managed-result.json, instrumentation.log,
pid-query.txt, maps.log and hash-reads.log. JNI redirects native stdout/stderr
to one file before CoreCLR initialization using a shared file description;
large bytecode dumps do not travel through truncated logcat. Binary adb exec-out
copies preserve original log bytes. The native header binds PID/nonce/mode/
global diagnostic, Java Process.myPid independently records the same PID, and
managed results must agree. Original /proc/self/maps supplies the loaded CoreCLR
directory; actual device SHA reads check its native products and matching
CoreLib. Required lanes must map libclrinterpreter.so. The installed APK and all
trusted/author files are checked again after execution.

Transport results bind product-manifest.json and managed-identity.json SHA,
installedRuntimeHashes/installedManagedHashes, exact commands/config and every
raw-file SHA. Failed commands and assessments remain in the fresh attempt
directory. An external strict assessment does not rewrite its original transport
receipt; final-assessment.json points to both. No automatic retry occurs.

Prepared/build success is not platform acceptance. Production functional counts
are not complete per-method selection counts. Complete core selection/refusal/
boxed matrix evidence, optional inline controls, a fresh Release native-entry
experiment and physical ARM64-device validation remain separately scoped. No
terminal execution budget or hostile-code sandbox is claimed. Archive creates
a new ZIP and SHA receipt without modifying historical evidence.

## Assessor launch failure and preserved recovery

The first measured required-policy run on 2026-10-13 completed its Android
application execution, but the desktop driver failed to launch the Python
assessor. PowerShell unwrapped the single-item if-expression to a string, so
the subsequent argument addition concatenated strings. The launcher reported
`Unknown option: -3`. This was a host-orchestration defect; it did not indicate
a runtime or author-code failure. The original
[failed assessment receipt](../artifacts/android-session-policy/20261013-apk-attempt1/run-required-64aa6601a97143e1b6687974f8818afe/failure-assessment.json)
and [launcher log](../artifacts/android-session-policy/20261013-apk-attempt1/run-required-64aa6601a97143e1b6687974f8818afe/assessment.log)
remain unchanged.

An explicit `py -3 -B` invocation assessed those original logs without rerunning
the application. Its separate
[recovery receipt](../artifacts/android-session-policy/20261013-apk-attempt1/run-required-64aa6601a97143e1b6687974f8818afe/method-assessment-recovery.json)
records passed=true and appRerun=false, PID7210, 20 successful/collected contexts,
260 native policy queries, 20 retired-query guards and 26 body groups with
520 bytecode dumps. This recovery is scoped to that required lane; it does not
establish the remaining lanes.

The driver now declares the launcher prefix as `string[]` before adding
assessor arguments. A separate
[argument-vector check](../artifacts/android-session-policy/python-argv-preparation-e7ef5788937246c4a69262b5eb065b41/results.json)
executed the actual source-extracted argument block and Invoke-Logged helper
against a temporary Python argv echo. Both default `py` and explicit
`Python314/python.exe` branches passed: all 12 script/assessor arguments retained
their order and paths containing spaces remained single arguments. This check
executed no Android application. Its receipt SHA256 is
`c3196b7ad0f8fe836fccaece0618dae98bef286b5ab99b05b51352a491919a77`.

## Original preparation checks

PowerShell AST parsing and SelfTest passed, including missing lifecycle/package
counts, missing native acknowledgement, pending sample collection and path
escape rejection. The frozen current-host snapshot was rehashed read-only and
the actual existing JNI/Java transformation anchors were checked. The generated
managed wrapper was compiled under a private RC1 SDK in an isolated directory;
this validates wrapper C# only, not Android runtime compatibility. No production
DLL was rebuilt and no AVD was started/installed/run for these checks.
The wrapper build completed with zero warnings/errors. A separate stock desktop
wrapper invocation returned1 with the fixed-bridge PlatformNotSupportedException
before an author DLL was available or loaded; it emitted no policy-success/test
markers. This confirms its early refusal path, not Android execution.

The [preparation receipt](../artifacts/android-session-policy-offline-4fa7c8bb5d794b31aa0fb5243b88febe/preparation.json)
(SHA256 612f7d26d99dad583ca4d680b8016eea902a556163734ca8f14701f43577b06a)
binds the isolated wrapper source, build/raw refusal logs and offline checks.
Its recorded document hash refers to the preserved preparation-doc-original.md
snapshot, before these receipt links were appended. The directory also preserves
the successful zero-warning [build log](../artifacts/android-session-policy-offline-4fa7c8bb5d794b31aa0fb5243b88febe/build.log)
and [self-test log](../artifacts/android-session-policy-offline-4fa7c8bb5d794b31aa0fb5243b88febe/self-test.log).

~~~powershell
& ./eng/verify-android-session-policy.ps1 -Phase SelfTest -Offline -HostInputReceipt ./artifacts/session-policy/ios-session-accept-host-snapshot-20261013.json
~~~
