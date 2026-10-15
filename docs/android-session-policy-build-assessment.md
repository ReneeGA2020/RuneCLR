# Android matching-build assessment

Prepared on 2026-10-13 while the matching build was running. The first attempt
failed in native globalization compilation because inherited Mac CPATH,
LIBRARY_PATH and SDKROOT polluted the Android cross-compiler environment. This
was a local driver/environment integration error, not an identified upstream bug.
The corrected driver clears those process variables and starts a fresh attempt2
with the same source tree. The subsequent [actual matching build and revised
assessment](android-session-policy-build.md) passed. Emulator execution remains
unperformed for this candidate.

[android-session-policy-build-assess.py](../eng/android-session-policy-build-assess.py)
requires official base 0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de,
combined commit 1724cdec553a7aff7a373a271a4be612651c7625,
tree 71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2, exact27 source hashes,
and tracked-clean source. Its scope is distinct from
[actual iOS assessment](ios-session-policy-build-assessment.md).

## Minimum subsets and framework

The first build needs clr.runtime+clr.native+clr.corelib+clr.tools+clr.crossarchtools,
the fixed source SDK and Darwin-host r27c NDK. These targets do not build Java
classes, APKs, Android samples or test runners; Android SDK/JDK installation is
not required for this subset. The NDK supplies JNI/native headers and the sysroot.
The wider checked-out Android workflow lists SDK/JDK for applications/testing.
Adding clr.nativecorelib to crossgen CoreLib does not add Java compilation.

The root build driver's command is:

~~~sh
./build.sh clr.runtime+clr.native+clr.corelib+clr.tools+clr.crossarchtools \
  -os android -arch x64 -cross -c Release -rc Checked -lc Release \
  -clrinterpreter -ninja /m:1
~~~

Android is excluded from automatic Debug/Checked interpreter defaults. Explicit
-clrinterpreter must reach native and managed feature definitions. Runtime/CoreLib
use Checked; ordinary libraries use Release. Dynamic compilation remains enabled
for trusted code and the ordinary-context comparison; required author bodies must
not fall back to JIT. This topology requires the shared libclrinterpreter.so and
matching native JIT, unlike the static interpreter/no-JIT iOS topology.

Next build libs.native+libs.sfx from the same source for Android framework/native
inputs; do not borrow iOS-specific libraries. This avoids libs.pretest and Android
test-runner projects. Preserve any real prerequisite failures and handle their
specific target rather than attributing source-build success to the .NET11 pack.

The actual pinned Microsoft.DotNet.SharedFramework.Sdk target
_GenerateSharedFrameworkDepsFile in targets/sharedfx.targets depends on
GetFilesToPackage and applies to PlatformPackageType=RuntimePack. It is imported by
src/installer/pkg/sfx/Microsoft.NETCore.App/Microsoft.NETCore.App.Runtime.CoreCLR.sfxproj.
After matching CLR/library inputs exist, invoke that project/target with consistent
Android/x64/runtime/libraries properties. PublishReadyToRun=false can retain an
initial private IL framework layout; fresh crossgen later must use matching tools.
The broader _GetAllSharedFrameworkFiles also generates runtimeconfig/manifests and
checks closure. libs.sfx alone does not establish that the pack deps file exists;
clr.packages is not required merely to invoke the dependency-file target.

An alternative test-layout target is
src/libraries/pretest.proj:GenerateTestSharedFrameworkAssets, using the repository
GenerateTestSharedFrameworkDepsFile. Its task deliberately writes placeholder
TFM/RID and derives framework/version from parent directories. Keep that labeled
test layout if used; prefer the SDK runtime-pack target for this private framework.

## Assessor invocation

Upload the assessor beside the unchanged ios-session-policy-build-assess.py shared
utility, SHA256 bada00fed05717d5d8b16e50e73705754bfe8629cd6b5a09fba38ca27c6e4645.
Use the existing RuneCLR.MetadataInspector DLL/deps/runtimeconfig bundle. Its
PEReader never loads inspected assemblies; the helper runs only on the selected
host-SDK .NET11 runtime. No new inspector build is needed.

~~~sh
python3 android-session-policy-build-assess.py \
  --build ROOT/android-session-policy-checked-20261013-attempt2 \
  --metadata-tool ROOT/metadata-inspector/RuneCLR.MetadataInspector.dll \
  --llvm-bin PRIVATE_NDK/toolchains/llvm/prebuilt/darwin-x86_64/bin \
  --output ROOT/android-session-policy-build-assessment-20261013
~~~

Replace ROOT/PRIVATE_NDK with inspected absolute paths. Use a new output directory
outside the runtime worktree. Failures preserve partial receipts and a results.json
traceback. Source and critical products are checked again at completion. The tool
does not build, install, launch an emulator or modify source/products.

## Evidence checks

Actual CMake caches and complete native/host compile databases establish Checked
optimization/debug definitions, x64 Android API24 NDK target, interpreter/JIT/R2R
features and Mac ARM64 compiler roles. Nine object owners cover the
VM/binder/interpreter/compiler roles, the Android target-native JIT and the
actual host JIT selected for compiler publication.
Checked CID capability does not establish that execution used that dispatch route.

CoreCLR/interpreter/JIT must be ELF64 little-endian x86_64 shared objects. Host
crossgen2 and its interface/JIT dependencies must be Mac ARM64 Mach-O images with
matching published source copies. On this x64 cross build, the source's
AotCompilerCommon.props selects host libclrjit.dylib and renames it to the
single-JIT target name; the separately built unix-any-OS crossarch image is
recorded as another compile owner. Native GUID bytes plus actual host JitCompileMethod
instruction comparisons bind the compiler interface. Three QCall native symbols
are checked by exact names; a separate stripped-symbol debug image must share
the target GNU build-id.

CoreLib PreTrim/PostTrim/ProductIL must retain five private bridge wrappers,
the nested constructor/Load/native-load override and three native imports. The
generated linker descriptor must retain three reflection entry points. PostTrim
and ProductIL must match. The compiled managed JIT mirror must contain required
interpreter enum value33.

Archive original databases/caches, generated linker descriptors, source hashes,
native identities/GUID disassembly and three-stage PE receipts. Include the four
raw managed PEs for independent review. A successful build assessment records
executionVerified=false; actual Android policy acknowledgement, body interpretation,
post-install IL and rejection/recovery remain required by the
[session plan](android-session-policy-plan.md).

Preparation checks passed Python AST/CLI and ELF parsing of the historical official
Android RC1 x64 CoreCLR with its GNU build-id. The shared GUID decoder and PE helper
already passed independent iOS/Windows checks. Those checks are not new Android
candidate results.
