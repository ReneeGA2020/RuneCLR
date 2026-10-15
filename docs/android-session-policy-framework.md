# Matching Android framework inputs

The [framework driver](../eng/android-session-policy-framework.py) builds Android
x64 managed libraries and OS native shims only after a successful matching
Checked CoreCLR build and its actual [build assessment](android-session-policy-build-assessment.md).
It then asks the runtime-pack SDK to generate the real Android framework deps
file. This stage does not install an APK or establish interpreter execution.

On 2026-10-13 (local date), actual attempt2 passed: library and deps stages both
exit0, with zero warnings and zero errors in the library build. Its inventory
contains 180 framework DLLs and 28 native-stage inputs, including shared/static
libraries and the actual crypto JAR/DEX. The 28 inputs are not 28 deployed shared
libraries. All inventory hashes were independently reread successfully; source
remains tracked-clean and the seven core-critical product identities, including
their published duplicate copies, remain unchanged.

Source is the reviewed combined candidate 1724cdec553a7aff7a373a271a4be612651c7625,
tree 71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2, on official base
0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de. The source worktree is reused
sequentially after its core build, without source modifications. CoreCLR/CoreLib
remain Checked; libraries are Release. The first core attempt's inherited Mac
include/library environment failure remains separate evidence of our integration
error. This driver applies the same process-only cross-compilation cleanup.

Run on the Mac build host, substituting the experiment root:

~~~sh
python3 android-session-policy-framework.py \
  --build ROOT/android-session-policy-checked-20261013-attempt2 \
  --assessment ROOT/android-session-policy-build-assessment-20261013-attempt3 \
  --toolchain ROOT/android-toolchain-r27c-20261013 \
  --android-tools ROOT/android-framework-tools-20261013 \
  --output ROOT/android-session-policy-framework-20261013-attempt2
~~~

Output must be fresh and outside the runtime source worktree. No SDK/runtime is
replaced. The selected native subset uses Android NDK r27c; JNI headers and
Android logging imports come from its sysroot. Native CMake does not compile
Java, but its MSBuild entry point build-native.proj runs BuildNativeAndroid
before BuildNativeUnix. AndroidLibBuilderTask compiles the Android crypto Java
sources with javac, then produces an actual jar and dex with jar and SDK d8.
This complete library stage therefore requires the private Android SDK/JDK
receipt supplied with --android-tools. APK installation remains a later stage.

The first framework attempt failed before CMake because ANDROID_SDK_ROOT was
empty. Its source remained clean and every accepted core-critical hash remained
unchanged. Our earlier prerequisite inspection covered native CMake but missed
the MSBuild Java task; this is a local build-driver integration error, not a
confirmed upstream defect. Keep that failed attempt and use a fresh output for
the corrected SDK/JDK attempt.

The actual library command is:

~~~sh
./build.sh libs.native+libs.sfx -os android -arch x64 -cross \
  -c Release -rc Checked -lc Release -clrinterpreter -ninja /m:1 \
  /p:RuntimeFlavor=CoreCLR /p:FeatureInterpreter=true \
  /p:FeatureDynamicCodeCompiled=true
~~~

RuntimeFlavor must be explicit: eng/Subsets.props defaults a mobile libs-only
build without any clr subset to Mono. Shared-framework source projects reference
CoreLib, and eng/references.targets forwards the Checked CoreCLR configuration.
The driver preserves the assessed CoreLib/native/compiler and their published
duplicate copies by hash; any change rejects this stage before deps generation.
No extra CoreCLR runtime subset is requested.

The driver removes CPATH, C_INCLUDE_PATH, CPLUS_INCLUDE_PATH, OBJC_INCLUDE_PATH,
LIBRARY_PATH, SDKROOT, MACOSX_DEPLOYMENT_TARGET, CMAKE_PREFIX_PATH and
PKG_CONFIG_PATH from its child-process environment. The user's persistent
environment is untouched. It records removed values and the exact commands.
ANDROID_SDK_ROOT and JAVA_HOME are set only for child processes from the verified
tools receipt; its JDK bin directory is first in PATH so javac and jar resolve to
the accepted tools. The receipt and the actual selected platform/build-tools
files are checked by hash before any library target is run.
The framework-toolchain v1 receipt binds JDK17 on darwin-arm64, executable probe
logs, java/javac/jar, SDK android.jar, d8/lib/d8.jar and platform/build-tools
source.properties. AndroidSdkHelper selects the highest installed numeric API
and stable build-tools version; the driver verifies that selection agrees with
the accepted receipt. The complete native inventory must contain both actual
libSystem.Security.Cryptography.Native.Android.jar and its dex output.

Libraries sfx-finish.proj produces framework/reference artifacts but does not
generate the shared-framework deps file. The second stage uses the actual
Microsoft.NETCore.App.Runtime.CoreCLR.sfxproj SDK target
_GenerateSharedFrameworkDepsFile, with PublishReadyToRun=false and the same
Android/CoreCLR configurations. GetFilesToPackage resolves actual local runtime
and library outputs. MSBuild's evaluated _SharedFrameworkDepsFile item and
LibrariesSharedFrameworkBinArtifactsPath/LibrariesNativeArtifactsPath properties
identify the outputs; the driver does not fabricate a nuspec or JSON manifest.
The test pretest target's placeholder netcoreapp0.0/rid deps is not used.

At this official source baseline, NetCoreAppCurrent remains net11.0 while the
product version is 12.0.0-dev. Paths/TFMs come from actual MSBuild properties;
the driver does not invent a net12.0 build output directory. It verifies the
generated runtimeTarget includes android-x64 and that the asset closure contains
CoreLib, System.Runtime, CoreCLR, the interpreter and target native JIT.

Receipts include request.json, per-stage command/exit/raw output, actual evaluated
deps properties/items, core-critical-before.json, core-critical-after-libraries.json
and core-critical-after.json. Failed stages retain their original output and
results.json; later stages are not run after a failure. A successful result also
requires unchanged tracked source and all accepted source27 hashes.

input-inventory.json records base/commit/tree/target/configurations/source and
groups named framework, native, headers and deps. Each entry has path, sha256 and
size. Framework lists actual DLLs; native lists Android shared/static shims and
core sharedFramework assets, including any real jar/dex assets. Header inventory
may be empty; layout can separately retain reviewed source hosting headers.
results.json exposes the actual frameworkDirectory, nativeDirectory,
coreNativeDirectory, depsFile/depsSha256 and inventory hash. It links the accepted
three-stage CoreLib metadata-assessment.json and its hash without rerunning or
weakening its private-API/trim checks.

frameworkInputsAvailable and depsGenerated describe build inputs, not a deployed
player. frameworkComplete and executionVerified remain false. The next
[Android session-policy plan](android-session-policy-plan.md) still requires a
matching private layout/APK, native policy acknowledgement with diagnostic0,
method-level interpretation evidence, post-install IL, ordinary trusted controls,
failure refusal/recovery and collectible retirement.

The actual receipt is ROOT/android-session-policy-framework-20261013-attempt2/results.json,
SHA256 d4fbefe34fe0b35e8d3bf6f8cec1737cab669a6ddf11c0a5c67031984556fb81.
Its input-inventory.json SHA256 is
d135051b35cb38aae74775a21be69121c75620113da13345638fc109d228427e;
the generated deps SHA256 is
fc9a3bc678b15c5b703f30a991b68105e76636b9c61d1303128d92ea04912ca7.
The [matching layout](android-session-policy-layout.md) now passes separately.
The original framework receipt still honestly has frameworkComplete=false and
executionVerified=false: successful input generation does not establish a
deployed player. The later [actual APK validation](android-session-policy-validation.md)
records deployment and five Checked selection/refusal controls separately.

## Later matching Release inputs

The 2026-10-13 Release core now has an independent successful framework stage
at ROOT/android-session-policy-release-framework-20261013-attempt2. Both the
native runtime and library configurations are Release. Actual libraries
compilation reported zero warnings/errors in 6m9.87s; the official runtime-pack
deps target also exited0. There are 180 framework DLLs and 28 native-stage
inputs; all seven previously assessed critical core identities and tracked
source remain unchanged. Its input-inventory SHA256 is
bb87538a5f80cecb6f6dbe82eee7f41a1e7f735929d42438d582d960f4fd013e,
and deps SHA256 remains
fc9a3bc678b15c5b703f30a991b68105e76636b9c61d1303128d92ea04912ca7.
This establishes matching build inputs, not Release APK execution.

The original Release framework attempt1 failed in the Roslyn build-tool path
with MSB3883 and "Cannot release a lock that is not owned by the current thread."
Its original log, command, exit and unchanged-core receipts are preserved in
the [Release core archive](android-session-policy-release-build-assessment.md).
No exception stack or minimal reproduction yet identifies the faulty component;
this is not a confirmed dotnet/runtime defect. Attempt2 uses the same source
with --no-shared-compilation, passing UseSharedCompilation=false to both stages.
The successful retry is an observed workaround, not proof of the lock's root
cause. The driver retains Checked as the default --configuration.
