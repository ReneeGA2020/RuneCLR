# Android Release debugger transport and native-entry preparation

Prepared on 2026-10-13. A matching Android x86_64 Release layout and actual
native/debug files are available. Actual same-UID debugger attachment, memory
reading, detachment and subsequent fixture completion passed on the owned
x86_64 emulator. Nine required fixture groups now have actual native method-entry
samples. Independent normal Release acceptance remains a separate gate. The root/operator owns device actions and their
separately preserved receipts. [Checked acceptance](android-session-policy-validation.md) remains
separate, with its complete bytecode-dump gates unchanged.

## Fresh gated APK

[android-session-policy-entry.py](../eng/android-session-policy-entry.py)
creates a derived private APK driver while preserving the original driver.
The derived script binds the actual RuneCLR repository path explicitly, so its
location under artifacts does not change tools/global.json resolution. Its
receipt records original-driver, derived-driver and gate-generator hashes.

~~~powershell
$python = 'C:/Users/XD/AppData/Local/Programs/Python/Python314/python.exe'
& $python -B ./eng/android-session-policy-entry.py prepare-driver --driver ./eng/verify-android-session-policy.ps1 --python $python --output NEW_PREPARATION_DIRECTORY
& ./NEW_PREPARATION_DIRECTORY/verify-android-session-entry.ps1 -Phase Build -NativeConfiguration Release <the ordinary explicit matching layout/host/build arguments> -EvidenceDirectory NEW_APK_DIRECTORY
~~~

The copied driver transforms its owned JNI template before the single native
compilation. It inserts the function before PROPERTY_COUNT and calls it just
before coreclr_initialize. JNI log/PID/nonce setup has already occurred; no
managed code has started. Java's existing onCreate handler accepts every env:
instrumentation extra and calls setEnv before initRuntime. It therefore passes
the new opt-in variable through without another Java transformation.

With RUNECLR_SESSION_NATIVE_ENTRY_WAIT absent, the gate immediately returns0.
When explicitly set to1, it validates the 32-hex run nonce, rejects an already
existing release file, attempts PR_SET_DUMPABLE and emits the actual result.
It waits up to180 seconds for files/session-<nonce>.entry-release using a
monotonic clock. Waiting/released/timeout records bind PID and nonce. The same
APK can therefore support a gated debugger run and a distinct ordinary
functional run. Gate waiting and attachment are not interpreted-method evidence.

The actual derived driver preparation is
[entry-driver-preparation-3c6f32a232944adfaecaadf723f3b785](../artifacts/android-session-policy/entry-driver-preparation-3c6f32a232944adfaecaadf723f3b785/results.json).
Its PowerShell AST and transformation of an actual previously generated JNI
session template passed. NDK r27c clang accepted the gate under actual Android
x86_64/API24 headers. Standalone header syntax checking reported one unused
static-function warning; the injected JNI call consumes that function. No
runtime, APK or target application was built/run by these preparation checks.
The gate generator is frozen at SHA256
b18c5a0523367870f87923bf7819dfb8adc060d6b9675147753d0cd07a871f50.

## Owned attach and release sequence

Use an explicit already-running owned emulator, a fresh nonce and the installed
private package. Keep the blocking instrumentation process/log separate from
the debugger process. The argument vector is:

~~~text
adb -s DEVICE shell am instrument -w -e env:RUNECLR_SESSION_RUN_ID NONCE -e env:RUNECLR_SESSION_LANE required -e env:RUNECLR_SESSION_MODE 0 -e env:RUNECLR_SESSION_NATIVE_ENTRY_WAIT 1 PACKAGE/net.dot.MonoRunner
~~~

Before attaching, independently read files/session-NONCE.pid-query.txt through
run-as and the native log's ANDROID_ENTRY_GATE waiting record. Both PIDs and the
nonce must agree; there must be no CoreCLR initialization completion marker yet.
Use the pinned x86_64 lldb-server, record its original and deployed hashes, and
launch it from run-as PACKAGE sh using exec and --attach PID. The measured run
used gdbserver 127.0.0.1:54329 and an ephemeral host TCP forward to tcp:54329.
Use the NDK lldb.cmd wrapper with gdb-remote 127.0.0.1:PORT. Preserve connection
failures; successful same-UID attachment on this emulator does not establish
other device SELinux/seccomp or ptrace permissions.

The NDK Windows wrapper supplies its private Python environment. Calling
lldb.exe directly can fail with C0000135; that is a host dependency/launcher
issue and does not identify a CoreCLR bug.

After installing and checking observation breakpoints, emit ANDROID_ENTRY_READY.
A second terminal explicitly releases the gate:

~~~text
adb -s DEVICE shell run-as PACKAGE touch files/session-NONCE.entry-release
~~~

Continue the debugger to managed completion. Record debugger exit, native and
managed exits, instrumentation result, original maps, installed native/CoreLib/
IL/APK hashes, run/PID ownership and gate markers. Remove only the owned forward
and stop only the owned lldb-server process after completion/failure; preserve
all failed logs. If the setup is not ready within the180-second gate, retain the
timeout and use a fresh attempt/nonce. No automatic app retry is part of these
tools.

## Actual transport result, 2026-10-13

The [v5 transport receipt](../artifacts/android-session-policy/20261013-release-entry-apk-attempt1/transport-preflight-bcd19a9fd4fd43b2a1df1c93a86b52d0/results.json)
passed for package net.dot.RuneCLR_Session_4528d856a5d8, PID6160 and nonce
bcd19a9fd4fd43b2a1df1c93a86b52d0 on emulator-5556. The frozen v5 driver SHA256
is 25fbf6914adca4404fc984f2b09f8308a2233c0ff9d2f491a2491b0e25f7892c.
Independent read-only review verified all15 raw hashes, matching Java/native
PID and nonce, mode0/global diagnostic0, LLDB exit0, the actual detach record,
gate release and native initialization/execution exit0. Ordered session1..20
PASS records and20 collected contexts followed detachment; the log also records
260 policy1 queries and20 protected retired-query failures. These observations
describe this debugger-affected run, not independent normal Release acceptance.

Android automatic shared-library enumeration did not provide the CoreCLR module.
The successful sequence used a synthetic local CoreCLR ELF target. The actual
Android main executable remained /system/bin/app_process64, separately pulled
and hash-checked; it was not replaced by that symbolic target. Owned
/proc/6160/maps identified the installed libcoreclr.so, whose device SHA matched
the local product SHA ea39871706c6452c9b66de0ab4fe18111389f36eaf28559a618970c3fcf68208.
The sole offset0 mapping and the matching ELF PT_LOAD with p_offset=0/p_vaddr=0
established slide0x7b7a284ab000 for this process only.

~~~text
platform select host
target create --arch x86_64-pc-linux-android MATCHING_LOCAL/libcoreclr.so
target symbols add MATCHING_LOCAL/libcoreclr.so.dbg
gdb-remote 127.0.0.1:OWNED_FORWARDED_PORT
target modules load --file MATCHING_LOCAL/libcoreclr.so --slide ACTUAL_MAPS_ELF_BIAS
~~~

The modules load command supplies section addresses without --load: it does not
write the file into device memory. An actual LLDB ReadMemory at that load bias
returned the same first16 ELF bytes as the SHA-bound local native image. Thread
and register inspection then completed, followed by process detach. Only after
detachment did the operator touch the nonce release file. Removal of the owned
TCP forward and both temporary server files returned0; server output records
exit. The receipt does not independently prove the final remote process/forward
list, nor complete installed-byte identity after execution.

Attempts1..4 remain preserved: the first waited for an absent listening message,
the second had no associated images, the third detached successfully but found
only the executable/vdso, and the fourth failed remote-android module caching
with GetCachedSharedModule. The successful local symbolic target avoids that
cache path. Pre-initialization register r10 was not read at InterpreterStub and
is not a bytecode-header sample. entryProofCollected remains false.

## Matching symbols and actual method identity

[android-session-policy-entry-capture.py](../eng/android-session-policy-entry-capture.py)
prepares a separate LLDB observer. It requires actual Release layout/debug
build-ID/hash agreement, fixed frozen IL fixture hashes, real PID/nonce/device
files path and an independently hashed matching interpexec.cpp. CRLF-to-LF
normalization permits a byte-equivalent Windows source copy. On 2026-10-13 the
actual Mac Release source and normalized local source independently matched
3e90e1c04ce527f3e0876a4c21ece30b3f8e935faa445e928dd2c0e2a3f2b02e.

~~~powershell
py -3 -B ./eng/android-session-policy-entry-capture.py prepare --layout ACTUAL_RELEASE_LAYOUT --source E:/runtime-selection-20261013/src/coreclr/vm/interpexec.cpp --expected-source-sha256 3e90e1c04ce527f3e0876a4c21ece30b3f8e935faa445e928dd2c0e2a3f2b02e --payload ACTUAL_FROZEN_APP/plugin --managed-identity ACTUAL_APK/managed-identity.json --device-files /data/user/0/PACKAGE/files --app-pid ACTUAL_JAVA_PID --run-id FRESH_NONCE --output NEW_CAPTURE_DIRECTORY
~~~

Before sourcing the generated capture.lldb, establish the synthetic local target
and actual CoreCLR slide using the successful transport sequence above. Add any
other SHA/build-ID-bound native image needed by its symbol commands with target
modules add while using the host platform; record each image's actual load bias
from the owned PID maps when it is mapped. A locally added image without a live
mapping supplies symbols only and cannot establish execution. The generated
capture file adds debug symbols but does not create/load native modules; a bare
remote-android target followed by module addition repeats the failed cache path.
The new capture must keep the debugger attached while installing breakpoints,
releasing the gate and continuing, rather than copying v5's early detach.

At the exact InterpreterStub symbol entry, Unix AMD64 passes the bytecode-header
address in r10. asmhelpers.S copies it into rbx before reusing r10. The observer
reads header -> InterpMethod -> methodHnd/MethodDesc, checks MethodDesc's own
m_interpreterCode equals that header and reads the first opcode bytes. It
reconstructs MethodDescChunk, MethodTable and Module, checks collectible ownership
and the actual full installed Module path, then binds MethodDef token to metadata
from the SHA-bound submitted IL file. It does not count compilation/preparation
hooks as method execution.

Interpreted child calls can bypass InterpreterStub. Two distinct actual
interpexec.cpp dispatch lines cover the regular-call and fast-delegate paths.
The observer uses live DWARF pFrame/pMethod/ip and requires ip=startIp+8 and
startIp->Method=pMethod. The actual Release symbol file resolved both lines
3590 and3707 to one location each during static LLDB inspection. Missing or
ambiguous optimized variables and missing group coverage must not be accepted
as successful capture.

The actual capture below sampled the regular-call line3707 only. Its live
pFrame/pMethod/ip variables and first-opcode identity were read successfully.
Line3590 resolved statically and had breakpoint hits, but produced no accepted
target samples. Matching DWARF location lists do not expose all three variables
at that fast-delegate point; no live coverage of that path is claimed.

The actual Android Release debug image exposes InterpMethod, MethodDesc,
MethodDescChunk, Module and InterpMethodContextFrame layouts. MethodTable only
has forward declarations; a typed MethodTable lookup failed. The observer uses
the actual embedded cDAC JSON instead of assumed offsets: its MethodTable
MTFlags and Module fields are0 and24 in this product. During attachment it must
read the exported DotNetRuntimeContractDescriptor, verify actual magic64,
64-bit flags and JSON size, and require the live JSON SHA to match the exact
matching native file before using those offsets. All other pointer/token fields
retain their matching DWARF checks. This is diagnostic interpretation of an
existing runtime contract, not an additional runtime patch.

The [static DWARF check](../artifacts/android-session-policy/entry-dwarf-preparation-7ac212c5c6a8491ea613d20480702c84/static-dwarf-attempt3.json)
records actual field offsets and breakpoint addresses. Earlier failed inspections
remain in the same preparation directory: one LLDB Python import rejected a
hyphenated module filename and the next found the missing MethodTable definition.
The successful follow-up inspected the remaining types; cDAC supplies the missing
MethodTable fields. Those static checks launched no target process.

## Assessment boundary

The observer targets nine groups: payload constructor/static constructor/Run
and its generated callback, plus private constructor/static constructor/InlineAdd,
private generic Identity and generated delegate callback. This is a trusted
experimental fixture, separate from production managed-il-gameplay-v1 support.
At least one actual entry sample is required for each group. Samples do not
establish complete invocation capture or the26x20 Checked dump matrix.

The inspect subcommand validates captured live pointer/token samples and
successful debugger completion but deliberately emits platformAccepted=false
and functionalProofPending=true. Final acceptance must also bind original
Android PID/nonce/maps/installed bytes, matching source/symbol identities,
mode0/global diagnostic0, native policy1, all20 correct values/static resets,
20 retired-query guards and20 completed context retirements. A distinct normal
same-APK run provides independent functional evidence. No Release Debug-only
InterpDump gate is fabricated or removed from the existing Checked assessor.
Additional execution topologies, physical ARM64 evidence, refusal-entry recovery
and terminal execution budgets remain separate gates.

## Actual nine-group capture, 2026-10-13

The fresh capture used PID3117 and nonce1067e723602348cda2425a8955e55a17,
the same installed Release APK and source1724cdec553a7aff7a373a271a4be612651c7625.
Its [original run receipt](../artifacts/android-session-policy/native-entry-runner-5e320482176b442bba9a6c1418cb01f4/capture-1067e723602348cda2425a8955e55a17/results.json)
preserves the initial assessment failure. That failure was a desktop-style
debugger exit0 requirement: Android reported final process status9 after the
instrumentation had already reported successful completion. No app rerun was
used to correct the platform-specific assessment.

The [Android completion assessment](../artifacts/android-session-policy/native-entry-runner-5e320482176b442bba9a6c1418cb01f4/entry-assessment-android-completion-final.json)
passed with nine samples: four InterpreterStub entries and five first-opcode
entries at regular-call line3707. Each fixed constructor/static constructor/Run,
generated callback, private constructor/static constructor/InlineAdd, private
generic Identity and private delegate callback group has one sample. Their live
collectible MethodTable/Module, MethodDesc/InterpMethod bytecode pointer identity,
bound PE hashes, MethodDef tokens and exact observation PCs passed. The live
cDAC JSON matched the native file, and capture-errors.json was absent. The
observer saw six stub hits and23 child hits before disabling observation after
all required groups; hit counts are not accepted method-entry sample counts.

All26 original raw hashes remained unchanged. Before execution, device hashes
matched the installed APK, CoreLib and51 managed-identity files. The native
CoreCLR matched the product manifest and had an independently verified maps/ELF
load bias. The debugger-run functional log contained20 ordered PASS results,
20 collected contexts,260 policy1 queries and20 protected retired-query failures;
native execute HRESULT, managed exit and instrumentation return-code were all0.

The new inspect options bind status9 to those original raw hashes, actual built
MonoRunner.java source/hash and its executeEntryPoint -> finish(retcode,result)
path, instrumentation return-code0/code0, owned PID/nonce, successful native and
managed completion, and an error-free LLDB result. Status9 remains the observed
Android process termination status; it is not converted to native exit0 and is
not an allowance for arbitrary crashes. Original prepared observer bytes and the
failed receipt are retained. Reassessment requires explicit evidence:

~~~text
android-session-policy-entry-capture.py inspect --capture ORIGINAL_CAPTURE/observer --android-completion ORIGINAL_CAPTURE --apk-evidence FROZEN_APK_EVIDENCE --prepared-driver FROZEN_ORIGINAL_PREPARATION_DRIVER --output NEW_ASSESSMENT.json
~~~

The [device handoff](../artifacts/android-session-policy/native-entry-runner-5e320482176b442bba9a6c1418cb01f4/device-handoff.json)
verified the owned app and lldb-server absent from ps, no owned TCP forward and
the emulator still booted for the operator's separate normal run. The entry
assessment still reports platformAccepted=false, functionalProofPending=true
and completeInvocationCapture=false. All20 invocations, both dispatch paths,
physical ARM64 execution and Release refusal/recovery are not established by
these nine samples.

The operator then completed a distinct same-APK, non-debugger run using PID3621
and nonce02ccd2af6bfe4adbacf5b823c0ba4641. Its [independent functional assessment](../artifacts/android-session-policy/normal-functional-runner-02e88cd4e948420598bbd316ef226574/run/assessment.json)
passed20 exact values and context retirements,260 policy queries,20 retired-query
guards,246 installed file hashes before/after, and four TracerPid0 samples.
It did not enable the gate or attach a debugger. See the separate
[Release functional scope](android-session-policy-release-functional.md).
These two runs provide complementary evidence for the nine sampled fixture
groups and normal fixture behavior; they do not establish the complete production
Release lifecycle/package suites or a26-body-group native-entry matrix.

The later [independent Release production and recovery lanes](android-session-policy-release-production.md)
now pass the full current lifecycle/package/sample suites and scoped refusal
with recovery, plus ordinary/fallback controls. These new functional runs add no
native-entry samples to this nine-group capture; production/refusal method-entry
coverage and the remaining dispatch paths still require separate observations.

The [frozen entry archive receipt](../artifacts/android-session-policy/entry-capture-frozen-20261013-1067e723.archive.json)
binds a420701-byte ZIP with SHA256
1922d28cb42f18734b56eee8d5604d70a640643175ea449d2b14440fbbc161e5.
Its46 files include unchanged original raw evidence/failure, both reassessments,
the original and final helpers, metadata-reader dependencies, actual Java source,
matching interpexec.cpp, fixture PEs and input identity receipts. All archive
members were hash-checked; matching layout/APK and the independent normal-run
assessment are referenced by exact hashes rather than duplicated. The archive
contains the documentation snapshot before this archive-reference paragraph.
