# Matching Android session-policy source build

On 2026-10-13, the Android x64 Checked CoreCLR/CoreLib/compiler prerequisite
build and its independent source/configuration/binary/metadata assessment passed.
The actual build reported zero warnings and zero errors. This result does not
establish Android execution of the session policy. The matching framework and
private layout now also pass. The later [owned APK runs](android-session-policy-validation.md)
separately establish Checked emulator execution and refusal/recovery.
The later [fresh Release core assessment](android-session-policy-release-build-assessment.md)
also passes the same source/compile/metadata gates. The build driver accepts
--configuration Checked|Release, default Checked; Release application execution
requires its own matching framework, layout and native-entry evidence.

The official base is 0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de. Combined
candidate 1724cdec553a7aff7a373a271a4be612651c7625, tree
71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2, contains the reviewed Windows
session-policy candidate plus the conservative iOS CID fix. All 27 changed
source hashes match the accepted combined source. The new worktree is
tracked-clean, and the original baseline native image remains unchanged.

## Actual toolchain and build

The remote Mac uses the source SDK 11.0.100-rc.1.26420.103 and a private
Darwin-host NDK r27c, revision 27.2.12479018. The
[toolchain driver](../eng/android-session-policy-toolchain.py) obtained the
Darwin archive from Google's official Android repository metadata. Its
836128272-byte size and published SHA1
0217c10ffbec496bb9fbfbb3c6fc2477c6b77297 both match; archive SHA256 is
8c5685457c58a88527367d46d3f14e8c727d962c39f85344cff0c0768a73c3b7.
The extracted clang18 executable actually runs on the Mac. No global environment
or installed runtime was replaced.

[android-session-policy-build.py](../eng/android-session-policy-build.py)
created a fresh detached worktree, cloned only the pinned SDK and used:

~~~sh
./build.sh clr.runtime+clr.native+clr.corelib+clr.tools+clr.crossarchtools \
  -os android -arch x64 -cross -c Release -rc Checked -lc Release \
  -clrinterpreter -ninja /m:1
~~~

The first attempt failed when inherited CPATH=/usr/local/include reached the
NDK compiler, triggering -Wpoison-system-directories. The corrected driver
removes inherited include/library/Apple SDK variables only from the child
process and starts a fresh worktree. Its build succeeds; the first attempt's
log and receipts remain archived. This is a local build-environment error,
not an identified upstream runtime defect.

## Actual independent assessment

The [assessor](android-session-policy-build-assessment.md) passed on the second
build. Nine native object owners bind actual source and CMake compile commands,
Checked definitions, Android x86_64/API24, shared interpreter, native JIT and
Mac-host compiler inputs. Target products are ELF64 x86_64; compiler products
are Mac ARM64 Mach-O. Native interface GUIDs, three native factory/query symbols
and managed enum bit33 match. Three CoreLib IL stages retain five private bridge
methods, three imports and the nested required-context methods.

The initial assessment incorrectly expected the published single-JIT image to
equal the separately built unix-any-OS crossarch image. The checked-out
AotCompilerCommon.props selects arm64/libclrjit.dylib and publishes it under
the single-JIT name. The revised assessment verifies that actual source mapping,
matching bytes and the ninth compiled host owner. Both assessment attempts are
preserved. No source or product was changed to satisfy the check. This proves
the recorded compiler input identity, not execution of Android code by it.

| Product | SHA256 |
|---|---|
| libcoreclr.so | 2be16461f86937a635556d59b35cb91056d4f69979fb549f74ac1aa19574e453 |
| Checked CoreLib IL | 628ed6551471ffc7d18f2724ebe4e0c8cd2efc8fab04b15a571bfd4307de1444 |
| Mac-host crossgen2 | b9b5265737b526944be7bb41beac7eabee8a7584e66dc39b32ef2dad86fd2709 |

These products allow trusted native compilation. Required author methods still
need actual interpretation/no-fallback evidence; Android does not use the iOS
static-interpreter/no-JIT topology.

## Preserved evidence and next stage

[Local archive verification](../artifacts/android-session-policy/20261013-core-build/local-verification.json)
checks archive SHA256, 60 member hashes and all 27 source hashes. The archive is
912541 bytes, 61 members, SHA256
69433f69b170243033da1377f67be7f96a4addc998d7e4d19c2564ce1a925322. It includes
original source snapshots, build logs, CMake caches/databases and metadata
receipts. Native binaries and the inspected PE inputs remain in the private
remote build; they are not included in this small archive.
The [archive driver](../eng/android-session-policy-evidence.py) also supports
including the four inspected managed PE inputs in a separate new archive.

Remote root is the project-private experiment path recorded in the local setup.
Relevant directory names are:

- android-toolchain-r27c-20261013: verified Darwin NDK and toolchain receipts.
- android-session-policy-checked-20261013: preserved failed original build.
- android-session-policy-checked-20261013-attempt2: successful fresh source build.
- android-session-policy-build-assessment-20261013-attempt2: preserved failed assessment.
- android-session-policy-build-assessment-20261013-attempt3: successful revised assessment.
- android-session-policy-core-evidence-20261013: verified receipt/configuration archive.

The same-source [framework attempt2](android-session-policy-framework.md) now
passes with zero warnings/errors, 180 framework DLLs, 28 native-stage inputs and
the actual Android framework deps file. RuntimeFlavor=CoreCLR was explicit;
mobile library-only subsets otherwise default to Mono. All assessed core inputs
remain unchanged. The [private layout attempt2](android-session-policy-layout.md)
passes with 195 file hashes and all six normalized provenance receipts verified.
The later actual runs consume the
[private APK driver](android-session-policy-acceptance.md) and
[owned-log assessor](android-session-policy-probe.md); see
[their measured results](android-session-policy-validation.md). ARM64/16KiB
pages, Release parity, native method-entry sampling and physical devices remain
separate verification work.

The first actual framework attempt stopped in BuildNativeAndroid because
AndroidLibBuilderTask requires an Android SDK to generate the crypto Java jar
and dex. Inspecting only the native CMake target had missed this MSBuild
prerequisite. All accepted core hashes and tracked source remain unchanged.
The [preserved failure archive](../artifacts/android-session-policy/20261013-framework-attempt1/evidence.tar.gz)
has SHA256 b848e5ae692a9a25bb2c3cb8791eb5f32fecc2c618bf1688cc043cc31b0a4042.
The [private Darwin SDK/JDK bootstrap](android-session-policy-framework-toolchain.md)
passed before the fresh framework retry: API36, build-tools35.0.1 and Temurin17,
with three checked archives, 11 critical files and six successful executable
probes. The original launcher identities remain preserved in the
[historical process receipt](../artifacts/android-session-policy/20261013-pending-launchers.json).
This failure is a local prerequisite gap, not a demonstrated runtime bug.

Layout attempt1 subsequently found the previously assessed PreTrim CoreLib
intermediate missing. Its cause is not a confirmed upstream cleanup defect.
A separate CoreLib evidence refresh passes with zero warnings/errors: four
inspected PE files and the linker descriptor exactly match the original
assessment, and all seven critical product identities remain unchanged. Both
the failed layout and the successful refresh are preserved; a fresh layout
attempt2 passes. This restores original evidence bytes rather than establishing
a new runtime capability. The [layout document](android-session-policy-layout.md)
records both receipts and their hashes. Subsequent APK runs are recorded
separately in [the validation record](android-session-policy-validation.md).
