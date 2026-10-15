# Android Release build assessment

On 2026-10-13, fresh Android x64 Release CoreCLR, CoreLib and
Darwin-host compiler inputs were built at combined commit
1724cdec553a7aff7a373a271a4be612651c7625, tree
71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2. This tool preparation and the
Checked compatibility check below do not establish Release execution. The actual
Release assessment and freeze-only snapshot now pass; application execution is
still a separate acceptance stage.

[The build assessor](../eng/android-session-policy-build-assess.py) accepts
`--configuration Checked|Release`, default Checked. Build/request/source receipts
must agree with the explicitly selected configuration; a Release product is never
accepted by silently weakening a Checked check. All 27 source identities, clean
source, nine compiled object owners, actual ELF64 x86_64 identities, matching
Mac-host compiler publication, GUID, five private CoreLib bridge methods, three
imports, nested context methods, linker roots and compiled bit33 gates remain.

The checked-out `eng/native/configurecompiler.cmake` defines Release as
`NDEBUG` and `URTBLDENV_FRIENDLY=Retail`; it does not define BUILDENV_RELEASE.
The Release assessor requires those actual definitions and excludes DEBUG,
_DEBUG, _DBG, BUILDENV_CHECKED and BUILDENV_DEBUG. The target Android owners
require -O2; Darwin-host compiler owners require -O3, following the actual
`eng/native/configureoptimization.cmake` target distinction. Both native and
host CMake caches must identify the chosen configuration.

With actual FEATURE_DYNAMIC_CODE_COMPILED=1, the source
`src/coreclr/clrfeatures.cmake` enables cached-interface-dispatch capability for
Debug/Checked AMD64/ARM64 and enables virtual-stub-dispatch for all configurations.
The assessor binds this source rule by hash and checks the VM compile definitions:
Checked has CID and VSD; this Release topology has VSD without CID. If the rule
changes, the tool rejects the inputs for review. This is a build capability
check, not evidence that an application exercised either dispatch route.

Run with fresh output outside the worktree, replacing ROOT and PRIVATE_NDK with
the inspected paths:

~~~sh
python3 ROOT/android-release-assessment-tools-20261013/android-session-policy-build-assess.py \
  --build ROOT/android-session-policy-release-20261013-attempt1 \
  --configuration Release \
  --metadata-tool ROOT/ios-session-policy-build-assessment-tools-20261013/RuneCLR.MetadataInspector.dll \
  --llvm-bin PRIVATE_NDK/toolchains/llvm/prebuilt/darwin-x86_64/bin \
  --output ROOT/android-session-policy-release-build-assessment-20261013-attempt1
~~~

ROOT is `/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr`. The exact
shared assessor utility must remain beside the new assessor. Its SHA256 remains
bada00fed05717d5d8b16e50e73705754bfe8629cd6b5a09fba38ca27c6e4645.

Before a later library target can remove intermediate CoreLib inputs, run
[the evidence freezer](../eng/android-session-policy-corelib-evidence.py) with
`--configuration Release --freeze-only`. This path invokes no build. It copies
the actually assessed PreTrim, PostTrim, ProductIL and managed compiler-mirror
PEs plus the generated descriptor. Each frozen stage retains originalPath, path,
sha256, originalAssessmentSha256 and matchesOriginal. Request/results bind
base/commit/tree/target/configuration, source27, the metadata receipt and the
seven unchanged critical products. The three CoreLib stages remain distinct
evidence even when PostTrim and ProductIL bytes are equal.

The existing rebuild mode remains available for the historical incremental-cleanup
case; it must not be confused with freeze-only. Checked stays the default in both
tools, so old invocations preserve their configuration.

## Actual Checked compatibility check

The frozen new tools were uploaded to
ROOT/android-release-assessment-tools-20261013. The new assessor actually reran
against the old unchanged Checked worktree without any build or application run.
It passed source27, nine object owners, native/compiler identity, three-stage
CoreLib metadata and bit33, writing fresh
ROOT/android-release-assessor-checked-compat-20261013-attempt1. The new freezer
then passed with buildInvoked=false, source clean and all seven critical products
unchanged; four frozen PEs and the descriptor match the new actual assessment.
Its output is ROOT/android-release-freeze-checked-compat-20261013-attempt1.
The original Checked receipts and products were preserved.

## Actual Release assessment and frozen inputs

The fresh source build completed with zero warnings and zero errors. The assessor
then passed at ROOT/android-session-policy-release-assessment-20261013-attempt1.
All nine compile owners have the expected Release definitions and target-specific
optimization. The VM's actual definitions contain FEATURE_INTERPRETER=1,
FEATURE_DYNAMIC_CODE_COMPILED=1, FEATURE_READYTORUN=1,
FEATURE_VIRTUAL_STUB_DISPATCH=1, NDEBUG=1 and URTBLDENV_FRIENDLY=Retail;
FEATURE_CACHED_INTERFACE_DISPATCH is absent, matching the checked-out source rule.
The assessment results SHA256 is
b3b807182328ff247f8e49dc7d2f3f43b9e245dc163be9090e234f39b32aa388.

| Matching product | SHA256 |
| --- | --- |
| CoreCLR | ea39871706c6452c9b66de0ab4fe18111389f36eaf28559a618970c3fcf68208 |
| CoreLib ProductIL | 8a1f56ea04dd87844b7c07bcbb8a429ce7147c62416f0ded29c2aa2766428899 |
| Dynamic interpreter | 604eafc27fe5e8e2f2e113b97f8d76903da62ff9d7474bd475495f5f99a0d9fc |
| Target native JIT | 05f9cff9e0cb9b6d6fa7d7fb21b4308d52bec755206b8c124c61a7a289e72e0e |
| Host crossgen2 | d0b0455a3dbcc2734a5728e08ec3a0ba03675bf7e4e7748e1cd3c7d54929fcdf |

The freeze-only snapshot passed at
ROOT/android-session-policy-release-corelib-evidence-20261013-attempt1, with
buildInvoked=false, clean source and every critical product unchanged. Its actual
PreTrim SHA is 93dad6555ea05fda0ae83800b16f4a86bc37c8203f11903a12529435f886aa07;
PostTrim and ProductIL both match the table. The compiled managed mirror SHA is
f686cb79c9b2443e3d4a83145491e8dc04ed11f0d2d1ce50580b6330f27bb335,
and the generated descriptor SHA is
ef875e5740e64bc1a2f7ea75d3de3a9a1b0cef26f702cb071eb9c88a485038c8.
All four frozen PE inputs match their original actual assessment hashes. The
snapshot results SHA is
ae055677bae1ae6e942b9bca6b7d4ade377f0f1c5fc8c16e665ad779c74db24a.

The [local evidence verification](../artifacts/android-session-policy/20261013-release-core-evidence/verification-results.json)
passes 102 original file sizes/hashes in a 103-member archive, including source27,
actual compile databases/caches, new Release and old Checked compatibility raw
receipts, eight frozen PEs, both descriptors and the exact running tools. Tool
hashes match the build request, assessor and freezer receipts. The archive also
preserves the first Release framework failure's eight raw files. The actual
library log reports MSB3883 in Microsoft.CSharp.Core.targets and
`Cannot release a lock that is not owned by the current thread` while building
System.Collections/ref. The pinned SDK runs this compiler task; these records
contain no managed compiler exception stack or minimal reproduction. Attribution
remains a suspected compiler/tooling error, with no confirmed runtime defect or
proved root cause. Source was clean and the accepted core products were unchanged.
The separate fresh retry requests UseSharedCompilation=false for both library
and deps commands; this document does not claim that retry passed. No build or
application was rerun to create this archive.
The archive size is 14,179,667 bytes and its SHA256 is
b9926e54bdbc5caa16d9cb25dc0f1a81d95e3d9efa2d6a22469747afdd07b6a1.
Its bounded LAN server completed one authenticated GET, zero failed requests and
exact SHA/size verification before Windows safe extraction.

## Release execution proof still required

Release omits the Debug-only interpreter dumps. Preserve functional/policy/retirement
checks and collect native method-entry samples on a fresh matching APK; simply
removing bytecode-dump checks would not establish execution. The Windows NDK r27c
contains lldb.exe and an x86_64 Android lldb-server. Their file availability is
verified. The later [matching APK transport experiment](android-session-policy-release-entry-preparation.md)
now passes attachment, actual symbol/memory binding, detach and resumed functional
completion. Actual method-entry capture and distinct normal acceptance remain
separate requirements.

Use an owned debuggable app, its actual PID/nonce, a bounded pre-CoreCLR gate or
launch-under-debugger path, and matching separate-symbol images whose GNU build-id
equals each deployed runtime/interpreter image. The current ungated instrumentation
runner can finish before an external attach; it needs an explicit capture path.
Use a process-scoped lldb-server connection with explicit port forwarding and
cleanup. Never infer readiness from a Java debugger wait or reuse an iOS simulator
attach/register script without an Android-specific adaptation.

At the actual Unix AMD64 `InterpreterStub` entry, r10 contains the interpreter IR
bytecode address (`METHODDESC_REGISTER` is the register name, not its payload
identity on this path). The bytecode header points to InterpMethod; establish the
MethodDesc, defining module and metadata token from matching symbols/actual memory,
and correlate with the post-install author PE and required native policy. Use
receiver MethodTable identity where applicable; object addresses can move. Also
record a trusted-host native execution control. Method-entry samples establish
the captured methods, while separate non-debugger runs establish complete lifecycle
and collection counts. ARM64 phones, page-size compatibility and a complete
hostile-code sandbox remain outside this x64 emulator evidence.
