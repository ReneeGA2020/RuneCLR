# Release native compatibility investigation

On 2026-10-12 UTC, the [fresh Release native build](ios-r2r-release-build.md)
completed successfully, but replacing native CoreCLR in the preserved Debug
framework applications failed before managed host startup. This is a failed
mixed-configuration experiment, not Release acceptance of the CID fix.

## Measured result

The unchanged full R2R lifecycle host, minimal collectible probe and controlled
package player were separately installed on a dedicated ARM64 iOS simulator.
Prepared managed assemblies and trusted composites retained their original
hashes; native and wrapper Mach-O sections were checked after signing.
The replacement native SHA-256 was
8ed0a3cae73584f69f59ab43020b3d6a5ae17be9ce9a0f74b7099cffbbfd1a8e.

All three applications emitted a native SIGSEGV during System.AppContext.Setup.
Their stacks include StaticsHelpers.GetGCStaticBase, followed by an attempted
DataMisalignedException construction and further thread-static failure.
None reached successful CORECLR_INITIALIZE_HRESULT=0x0, callback execution,
context retirement or RUNECLR_EXIT=0. The launcher returned zero despite the
native faults, so launch status alone is not a passing application result.
The results.json receipt records all three functional groups as failed.

The dedicated simulator was shut down successfully. Local preserved evidence is
artifacts/ios-r2r-investigation/20261012-release-native-mixed/evidence.tar.gz,
33,077 bytes, SHA-256
e20fb4f0935753947b95028f9422652fec753d644f165dcd730f769d2691a434.
Its 39 members were downloaded in bounded chunks, hash-checked and extracted.
The prior passing Debug evidence remains separate.

## Source configuration mismatch

At the pinned source, CoreCLR's managed CoreLib deliberately reflects native
Debug layout. RuntimeHelpers.CoreCLR.cs defines DebugClassNamePtr as eight
bytes on a 64-bit Debug build, zero otherwise. Its MethodTable
AuxiliaryDataOffset is 0x20 + DebugClassNamePtr; ParentMethodTableOffset
is 0x10 + DebugClassNamePtr. Native methodtable.h includes
debug_m_szClassName only under _DEBUG, before the parent/module/auxiliary
fields. The preserved Debug managed CoreLib therefore expects auxiliary data
at 0x28, while the new Release native layout supplies it at 0x20.

StaticsHelpers.GetGCStaticBase reads mt->AuxiliaryData and then the GC
static base. This layout mismatch explains why mixing these inputs is invalid
and matches the measured early-static failure. It does not establish a CID
guard regression: this application has not reached a collectible interface call.
Matching-base source alone does not establish matching native/managed layout.

## Debugger evidence and next acceptance

The first interpreter capture also failed independently: LLDB attached while
the application was stopped in dyld, before libcoreclr.dylib loaded, and could
not associate its DWARF symbol file with a loaded module. That attempt provides
no interpreter evidence. Its script/log are retained in the failure archive.

A separate startup capture waits for the native library to load and stops at
EXC_BAD_ACCESS, address 0x20, inside native MethodTable class-initialization
helpers. Its selected-thread stack retains the original framework
GetGCStaticBase / AppContext.Setup path beneath exception construction.
This captures a downstream startup fault, not an interpreted plugin call or
proof of the exact first invalid load. The installed bundle remains unchanged
and the simulator shuts down. Hash-verified local evidence is
artifacts/ios-r2r-investigation/20261012-release-startup-capture/evidence.tar.gz,
28,305 bytes, SHA-256
956bc4ea4dd43b0a39069ecc581c4cb12b5e854b867a9ccb6e76bf78037ec868.

[The Release verifier](../eng/ios-r2r-release-verify.py) now waits at
coreclr_initialize before loading symbols. A separate
[entry/fault capture tool](../eng/ios-interpreter-entry-capture.py) preserves
new debugger attempts without rerunning completed functional groups. Successful
probe evidence requires an actual InterpreterStub entry, the receiver's
MethodTable matching the method owner, the MethodDesc bytecode pointer matching
the entry register, and metadata tokens matching the plugin's Start/Tick/Stop
methods. It also requires normal completion and collection. These checks are
implemented; their results must be recorded independently of source inspection.
The initial Debug smoke capture followed only the populated cache stub, but the
candidate leaves collectible cells on the initial slow-dispatch path. Both
initial and populated dispatch entries are now observed. Two subsequent Debug
captures sample eight InterpreterStub invocations covering all three callback
metadata tokens, matching bytecode/owner identities, with native execution
returning managed zero. They fail their original exact-ten-entry threshold;
those attempts remain unchanged. The current verifier records observed versus
expected counts and explicitly labels incomplete invocation capture. It
requires actual entries for every callback, rather than treating a sampled
breakpoint trace as a complete call counter. Independent non-debugged probes
remain the evidence for complete callback counts and retirement.

Matching Release CoreLib and compilation tools now build successfully. The
[layout builder](../eng/ios-r2r-release-layout.py) also completes: it regenerates
the trusted full-host/framework composite and reduced R2R probe composite with
those tools, replaces their generated R2R component DLLs, preserves the IL
plugin and wrapper code/data, and verifies source/native/CoreLib/compiler
identities. Its private output is ios-r2r-matching-release-layout-20261012.
Other managed libraries remain the preserved same-base inputs; this is not a
new full Release shipping framework build. The build receipt separately marks
executionVerified=false. The compact layout evidence SHA-256 is
12c859e5cb1d4a6ed461fcdea969cf8af282341abdb41e17c304a9f8fffc8fc8.

[Functional acceptance](../eng/ios-r2r-release-accept.py) now passes against
this matching layout. The unchanged full R2R lifecycle host passes 21/21.
The minimal probe completes twenty three-Tick sessions with sixty before/after
markers, twenty returned sessions, twenty unload requests and twenty completed
collections. Both applications report dynamic compilation disabled and managed
exit zero, retain their installed bundle identities and emit no native fault.
The independent functional receipt records success=true and shutdownExit=0.

A separate Release LLDB run captures eight valid InterpreterStub entries:
Start once, Tick five times, Stop twice. Every recorded entry has an actual
plugin receiver MethodTable matching the method owner, a bytecode header
pointing to its InterpMethod/MethodDesc, and a MethodDesc interpreter pointer
matching the entry's bytecode register. Tokens 0x06000001/2/3 match the original
IL plugin's Start/Tick/Stop metadata. The app executes to managed zero and its
simulator shuts down. The proof receipt records passed=true and
completeInvocationCapture=false: these are sampled entries covering all three
methods, not the complete ten-call trace from the two-session debugger fixture.
The independent non-debugged probe supplies complete callback/collection counts.
Release emits no Debug interpreter dumps; this proof uses native entry and
memory/metadata evidence rather than assuming the configuration was selected.

The local hash-verified evidence paths are:

| Evidence | Local archive | SHA-256 |
| --- | --- | --- |
| Matching layout build | artifacts/ios-r2r-investigation/20261012-matching-release-layout/evidence.tar.gz | 12c859e5cb1d4a6ed461fcdea969cf8af282341abdb41e17c304a9f8fffc8fc8 |
| Functional acceptance | artifacts/ios-r2r-investigation/20261012-matching-release-functional/evidence.tar.gz | 8ad117aadf51c0b79cbb2a7f8d1f0b44294cecefc7ca5ccc7d0cd5ba647c3597 |
| Native interpreter entry | artifacts/ios-r2r-investigation/20261012-matching-release-entry/evidence.tar.gz | 522b86fcb99424a6d8c9a776de85466ef1abb92e07705dca0b03d0ecbc17b2ff |

The later [matching Release controlled-player run](ios-r2r-release-packages.md)
passes all fifteen functional package cases with fresh post-install fixtures
and an unchanged bundle. A driver count-parser error and its independent
read-only reassessment are both preserved. Native method-entry proof for those
particular script/helper methods is still pending; the probe capture above
must not be transferred to them. Complete Release
shipping packs, physical-device acceptance, performance, complete upstream
XHarness integration and an upstream accepted patch remain separate work.
