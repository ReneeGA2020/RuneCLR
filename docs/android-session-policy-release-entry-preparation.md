# Android Release APK and debugger transport

On 2026-10-13, the matching Android x64 Release APK was built, installed on the
owned API35 emulator, and received newly produced controlled packages and late
IL after installation. A real pre-initialization debugger connection then
passed; after detach and gate release, the same process completed twenty correct
sessions and twenty context collections. This is transport and functional
evidence. Nine method-entry groups and a distinct non-debugger Release acceptance
run remain outstanding.

## Matching inputs and actual construction

The official base is 0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de. Runtime candidate
1724cdec553a7aff7a373a271a4be612651c7625, tree
71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2, is the same combined session/CID
source used for the [Release core assessment](android-session-policy-release-build-assessment.md)
and [matching framework/layout](android-session-policy-release-layout.md).
All source27, metadata, compile configuration and symbol build-ID checks passed.
The Android Release VM has VSD, interpreter and native JIT support; CID is absent
in this configuration. This is not the static iOS execution topology.

Local evidence is
artifacts/android-session-policy/20261013-release-entry-apk-attempt1.
The player uses the unchanged 32-file host/fixture snapshot. Windows APK builder
and bridge compilation use the private official SDK11.0.100-rc.1.26425.128;
the Mac runtime source build used its pinned SDK11.0.100-rc.1.26420.103.
All three local construction stages exited0. APK SHA256 is
5edc4372e29d497999f89226fc2bad62f1d39dbbf9c4fbe7b91a279372854d6a,
with unique application ID net.dot.RuneCLR_Session_4528d856a5d8.
The wrapper/native template is a private experimental copy; runtime source and
the original player DLLs were not edited or rebuilt.

The original APK driver remains unchanged by gate generation. The derived driver
has SHA256 5b8f692f412e7b1809dba8432ecadd9fc744cf59afb6d3409047bec6fe616246;
the frozen gate generator SHA256 is
b18c5a0523367870f87923bf7819dfb8adc060d6b9675147753d0cd07a871f50.
The opt-in RUNECLR_SESSION_NATIVE_ENTRY_WAIT=1 gate is inserted before the single
JNI compilation, before coreclr_initialize. It waits at most180s for a
nonce-specific release file. Ordinary runs do not enable it. Only this diagnostic
path sets process dumpability for an app-UID debugger; it is not a runtime policy
or a production hardening mechanism.

Actual installation completed at 2026-10-12T22:02:58.548711Z, and new operator
production ran from 22:03:30.1160159Z to 22:03:32.7988224Z, all on 2026-10-13
locally. Forty-three payload files were transferred and checked on the device.
The new producer receipt SHA256 is
7a96491dc6cf074eb93b1bd180593c7d6788ae822d6985193ce9e3e496172025;
the actual managed identity receipt SHA256 is
d7650af1713e47e251906f10535139daaa4a3a97096bdecf5b6978eaf66b98ea.
This new production event is separate from the earlier Checked APK's fixtures.

## Actual transport and resumed execution

The successful transport directory is
transport-preflight-bcd19a9fd4fd43b2a1df1c93a86b52d0 under the local evidence
root. Native header and the independent Java PID query both identify app PID6160
and nonce bcd19a9fd4fd43b2a1df1c93a86b52d0. Before attachment, the gate reported
waiting/dumpableResult0 and CoreCLR initialization had not occurred. NDK r27c
x86_64 lldb-server ran under that app UID and attached only that PID.
Host LLDB18.0.3 connected through one explicitly owned adb forward.

Android automatic library enumeration did not supply the full module inventory.
The successful procedure instead creates a local synthetic CoreCLR ELF target
and loads the matching symbols before connecting. The actual Android executable
is recorded independently as /system/bin/app_process64, SHA256
fa2d6ccaff829790163035d6e50d52137ad7eeb19a1e35a7249a8cae9b68ecb6.
The synthetic symbol target does not claim CoreCLR is the Android executable.

Actual app-UID /proc/PID/maps identified the deployed CoreCLR path. Its file hash
matches ea39871706c6452c9b66de0ab4fe18111389f36eaf28559a618970c3fcf68208,
and its .dbg matches
49b8cb73bcc617735b4799a6642d0e7c107b83d342187f0154ca0f145071f34d.
The offset0 mapping and the actual ELF PT_LOAD offset0/vaddr0 establish the
load bias0x7b7a284ab000 for this process. LLDB only sets local section load
addresses with --slide; --load is not used. A sixteen-byte live process read
matches the actual file's ELF header. Thread/register reads, module/symbol
loading and detach all complete with LLDB exit0. Registers read during this
pre-init stop are not interpreter-entry samples.

After actual detach, the explicit app-UID touch command released the nonce gate.
Native initialization/execute and managed/instrumentation exits are0. Exact
seventeen-field expected results match in all twenty sessions, with twenty
collections, 260 live required-policy1 queries and twenty retired query guards.
The frozen shared contract has actual JIT summaries, and targeted SelectionUGC
names have none. These controls do not substitute for actual author method-entry
observations or a complete invocation counter.

The [independent final preparation verification](../artifacts/android-session-policy/20261013-release-entry-apk-attempt1/final-preparation-verification.json)
checks all fifteen raw transport hashes, exact functional values/policies,
246 installed asset/payload/native file identities and the installed APK hash.
Its saved process list finds app PID6160 and server PID6187 absent; the saved
forward list finds the owned forward removed. The transport result SHA256 is
a1cdb528a3d0b197132453b5b6c1314a27c0aed6b1d7428c67da75f612266eb0.
The [owned emulator cleanup](../artifacts/android-session-policy/20261013-release-entry-apk-attempt1/emulator-shutdown.json)
records kill exit0 and confirms emulator-5556 is no longer reported by adb.
The AVD was RuneCLR_API_35_x64, API35/x86_64/4096-byte pages; this is not a phone
or a16KiB-page result.

The [complete evidence ZIP](../artifacts/android-session-policy/20261013-release-entry-apk-attempt1-fresh-aa104efcfd754124be6b838eb4935465.zip)
contains all 556 source files, including the four failed transport attempts and
the successful fifth attempt. Its size is 69,681,641 bytes and SHA256 is
52aa2ee97d66d53f785e8e87552384b63f7df87256e0acb6096caaaeafc7f5f6.
The [archive verification receipt](../artifacts/android-session-policy/20261013-release-entry-apk-attempt1-fresh-aa104efcfd754124be6b838eb4935465.receipt.json)
is outside the archived source directory. Independent verification rechecked
archive identity, exact membership, every file's size/hash and all CRCs against
the unchanged source directory. Archiving did not rerun the app or emulator.

## Preserved integration failures and next capture

The first emulator launch omitted ANDROID_AVD_HOME and exited before installation;
the next launch supplied the private AVD path through process-local environment.
Four failed transport attempts remain preserved with separate nonces and logs:
console-readiness detection; a connection without Android target configuration;
incomplete automatic module enumeration; and remote-android GetCachedSharedModule
failure. The first failure did not reach LLDB. The later trials' partial attach
results do not establish completed application execution. Failure cleanup's
instrumentation Process crashed message is not evidence of a CoreCLR defect.
Two read-only final verifier errors also remain recorded: treating an assembly
name as a type name, and looking for APK native libraries in the data-files
directory. Corrected verification used actual types and installation paths;
the application was not rerun for those checks.

Use the [prepared entry observer and native capture procedure](android-session-policy-entry.md)
with a fresh PID/nonce on this unchanged APK. Load matching native/symbol files
using the validated synthetic-target procedure and actual mapping bias. Capture
the nine fixture method groups and check actual bytecode/MethodDesc/module/token
identity, then run a distinct normal lane for independent functional evidence.
Release does not provide Debug-only InterpDump output. The original Checked
assessor's bytecode requirements remain intact. Physical ARM64, inline controls,
further refusal-entry cases and terminal budgets remain separate work.
