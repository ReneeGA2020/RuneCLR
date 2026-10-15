# Private Android session-policy layout

On 2026-10-13, [the offline layout assembler](../eng/android-session-policy-layout.py)
successfully assembled actual attempt2 from the matching Android native build,
build assessment and successful separate framework stage. The 195-file private
layout and its six provenance receipts pass independent hash rereads. This is
completed layout preparation; later [APK runs](android-session-policy-validation.md)
establish execution separately. The assembler executes no runtime,
compiler, emulator, APK or remote command; local read-only Git queries verify
the source checkout. The operator/root runs it where the actual input paths exist.

## Inputs and command

    python3 eng/android-session-policy-layout.py \
      --build ACTUAL_NATIVE_BUILD_DIRECTORY \
      --assessment ACTUAL_ACCEPTED_BUILD_ASSESSMENT_DIRECTORY \
      --framework ACTUAL_SUCCESSFUL_FRAMEWORK_STAGE_DIRECTORY \
      --toolchain ACTUAL_DARWIN_R27C_TOOLCHAIN_DIRECTORY \
      --output NEW_PRIVATE_LAYOUT_DIRECTORY

The required inputs are directories. The output must be fresh. All failures retain
results.json with success=false and the error; an existing output is never
overwritten. Source is pinned to base
0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de, combined commit
1724cdec553a7aff7a373a271a4be612651c7625 and tree
71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2. The native build must have succeeded,
with nine actual compile owners, source27, GUID and metadata assessments. Its
currently tracked-clean checkout and changed-source hashes are checked again.
The exact framework input inventory, deps, preserved CoreLib assessment and
unchanged critical inputs must bind that same source and native assessment.

The default native/CoreLib configuration is Android x64 Checked.
`--configuration Release` explicitly selects matching Android x64 Release
native/CoreLib inputs. Native build/request/source, build assessment, framework
result/inventory, compile assessment and both target/host CMake caches must agree
with this selection. Historical Checked assessments without the later explicit
configuration field remain accepted as Checked only. Framework IL and OS-native libraries
are Android Release from the same source. The actual source currently evaluates
NetCoreAppCurrent=net11.0 while the product is .NET 12; the assembler checks the
real android-x64 deps target/assets rather than inventing a net12.0 TFM. No iOS
framework or shipping NuGet product is used as a substitute.

## Layout and provenance

The successful output has native/, managed/, java/, headers/, receipts/ and
same-byte layout.json/results.json. Supply layout.json to the APK driver's
LayoutReceiptPath parameter. Its
runeclr.android.session-policy.layout.v1 receipt matches
[the APK driver's strict Validate-Layout contract](../eng/verify-android-session-policy.ps1).
It includes libcoreclr.so, libclrinterpreter.so, libclrjit.so, matching IL
System.Private.CoreLib.dll, the actual generated Microsoft.NETCore.App.deps.json,
framework DLLs and Android OS-native shared libraries. Hosting headers come
from the verified checkout's actual coreclrhost.h and host_runtime_contract.h.
Identical duplicate destinations are recorded; differing collisions fail.

Each deployed file has its hash, source path, role and source commit. Actual
framework DEX companions appear under java/ with role=android-java; the APK
builder must package them as separate classesN.dex entries (N >= 2) and verify
their actual entry hashes. Original JAR inputs are preserved under
receipts/java/ as evidenceFiles and are not installed as runtime payloads.
A needed NDK libc++_shared.so has sourceCommit=null and the actual toolchain-receipt SHA.
It is added only when a real DT_NEEDED edge requires it. Static archives remain
in the framework provenance/omitted-input list. Java companions are not
represented as native shared libraries; their actual APK packaging/entry checks
remain a separate gate from ELF DT_NEEDED closure.

Six SHA-bound receipts record actual native build, framework build, source,
compile features, trimmed API and ELF dependency closure. Preserved original
build/request/source, compile/native/metadata assessment, framework inventory and
NDK receipts are copied with independent hashes and source paths.
Original provenance files also appear in evidenceFiles for the APK driver to
preserve beside the six normalized receipts and Java archive.
Successful layout assembly establishes these input relationships; it does not establish
session execution, interpreter entry or post-install gameplay.

Release assembly additionally requires libcoreclr.so.dbg and
libclrinterpreter.so.dbg. Both debug images and their corresponding .so files
must match the original build's artifacts.json hashes/sizes. The assembler reads
each actual ELF .note.gnu.build-id section and requires the paired native/debug
GNU build IDs to match. The debug images are copied under receipts/symbols/
as evidenceFiles, with the original artifact-inventory SHA and matching native
hash/build ID. They are not APK runtime payloads. Missing images, missing build
IDs or mismatches fail Release assembly; copying symbols alone does not prove
debugger attachment or method entry. Checked assembly keeps its original scope.

## API and dependency checks

### Immutable CoreLib intermediate evidence

An optional `--corelib-evidence ACTUAL_FROZEN_CORELIB_EVIDENCE_DIRECTORY`
consumes the successful output of
[android-session-policy-corelib-evidence.py](../eng/android-session-policy-corelib-evidence.py).
Freeze the four assessed PE files before the framework stage can remove
intermediate build outputs. The source inspector receipt and original stdout
remain the authoritative metadata; the snapshot supplies preserved file bytes.
For a fresh Release lane, the command adds:

    --configuration Release \
    --corelib-evidence ACTUAL_RELEASE_CORELIB_SNAPSHOT_DIRECTORY

Snapshot request/results must bind the exact prior metadata-assessment SHA,
source receipt/source27 hashes, combined source identity and unchanged seven
critical product hashes. Target/configuration and success/source-clean/descriptor
checks remain mandatory. `frozenStages` contains exactly four ordered, distinct
copies under managed-pe/stage0 through stage3. Each originalPath equals the
corresponding prior inspector stage, and both its recorded assessment hash and
actual frozen PE hash must match that exact original stage. ProductIL cannot
substitute for the PreTrim byte sequence. The original descriptor hash must
match its preserved copy.

Signature decoding and mirror checks read the immutable paths through that
originalPath-to-frozenPath mapping. The assembler still compares raw inspector
stdout to the original metadata rows, verifies the actual inspector binary,
reads real PE signatures and checks the three APIs, five private wrappers,
three QCall imports, nested methods and bit33 mirror. It records the raw
stdout hash and snapshot bindings in trim-api.json. The snapshot request/result,
build.exit, all four PE files and descriptor are copied under
receipts/corelib-evidence/ as SHA-bound evidenceFiles. They are provenance
assets and must not be installed into the APK runtime payload.

Without this option, existing Checked callers still read the original stage
paths and fail if those bytes are absent. No automatic regeneration or weakened
metadata fallback occurs. Release support is prepared here; its measured layout
result must be recorded independently after actual matching inputs are assembled.

### Fixed APIs and native dependencies

The host-only metadata assessment must match its original inspector output,
inspector binary and linker descriptor hashes. The assembler reads the actual
PE TypeDef/TypeRef tables to resolve the recorded signature blobs. Across
PreTrim, PostTrim and ProductIL it checks the three private reflection APIs:

- static RuneCLR_CreateInterpreterRequired(string, Func<ALC,AssemblyName,Assembly>)
  returns AssemblyLoadContext;
- static RuneCLR_GetExecutionPolicyVersion() returns int;
- instance RuneCLR_GetExecutionPolicy() returns int.

The five private wrapper methods, three actual static PInvoke/QCall imports,
nested context constructor/Load/LoadUnmanagedDll and compiled bit33 mirror must
remain. PostTrim, ProductIL and the copied CoreLib must have the same hash. The
fixedBridgeSignaturesVerified flag is emitted only after these checks.

ELF64 little-endian x86_64 PT_LOAD/PT_DYNAMIC parsing reads actual DT_NEEDED
and SONAME strings, including stripped images. Every dependency recursively
resolves to a packaged shared library, the actual pinned NDK libc++_shared.so,
or an existing actual API24 ELF linker stub in the pinned NDK sysroot. Unknown
edges, invalid images and SONAME/basename mismatches fail. The ELF closure
receipt explicitly distinguishes Android system stubs from packaged binaries:
those stubs prove link-time availability, not the identity of device libraries.

## Preparation evidence and limits

Actual output is ROOT/android-session-policy-layout-20261013-attempt2. Its
same-byte layout.json/results.json SHA256 is
9f596dcab1ad6e17e74dc5da2038136bec6cebaf9cff3ca756ac653fbfa38e05.
The 195 files are: one CoreCLR, one interpreter, one JIT, one CoreLib,
181 framework assets (180 DLLs plus deps), seven OS-native shared libraries,
one crypto DEX and two hosting headers. The actual ELF closure did not require
an extra packaged NDK libc++ library. Exact bridge signatures and recursive ELF
dependency closure passed; sourceTrackedClean=true and executionVerified=false.

The preserved attempt1 failed because the previously assessed PreTrim CoreLib
intermediate was missing after the framework stage. The cause of that missing
build intermediate has not been established as an upstream cleanup bug. A
separate ROOT/android-corelib-evidence-refresh-20261013-attempt1 rebuilt CoreLib
and froze four inspected PE files. All four exactly match the prior assessment,
the linker descriptor matches, and all seven core-critical product identities
remain unchanged. Its results.json SHA256 is
daff2e22ce824bd7563169e746fee6b4115fc395057699c5fe6b5d3b8a82972c.
Attempt1's failure receipt remains intact; attempt2 uses the restored original
evidence bytes without changing source or weakening metadata checks.

The actual preserved Windows PreTrim/PostTrim CoreLib bridge signatures decoded
correctly, and existing r27c API24 libc/libm/liblog ELF files parsed correctly.
These are parser preparation checks, not candidate Android build or execution
evidence. Native, framework and private layout now pass; APK construction,
installation and the actual execution/refusal
matrix remain governed by [the Android validation plan](android-session-policy-plan.md)
and [the offline execution assessor](android-session-policy-probe.md).

The later configuration/snapshot extension passed a separate
[local preparation check](../artifacts/android-session-policy/layout-snapshot-preparation-e324401446d74dddb94bb598cce48fba/results.json).
It decoded nine actual historical Android Checked bridge signatures from the
four preserved PE stages. A clearly labeled schema rehearsal verified exact
snapshot bindings and rejected seven mutations: Checked-as-Release, a changed
metadata receipt, missing/swapped stages, ProductIL substituted for PreTrim,
a changed descriptor hash and changed critical product hashes. Those rehearsal
receipts are preparation fixtures; they are not a newly measured source build
or Release snapshot.

A separate [GNU build-ID parser check](../artifacts/android-session-policy/layout-build-id-preparation-c5fd646e2e77459396e9beceac846236/results.json)
read the actual historical Android Checked libcoreclr.so and interpreter ELF
notes and matched independent NDK llvm-readelf output for both. An attempted
lldb-server executable input was rejected by the shared-object type gate and
retained as a negative observation. This verifies parser preparation only;
fresh Release native/debug pairs and their artifact bindings still require
actual layout assembly. No application or debugger was run by either check.

The later [actual Release layout](android-session-policy-release-layout.md) now
passes the 195 player inputs, exact frozen CoreLib metadata and GNU build-ID
pairs. Its complete archive preserves framework-stage raw logs and matching
symbols separately from player inputs. This later result establishes matching
Release inputs; Android method-entry capture remains a separate experiment.
