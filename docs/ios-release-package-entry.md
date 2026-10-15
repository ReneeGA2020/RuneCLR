# Release controlled-package interpreter entries

The [capture driver](../eng/ios-release-package-entry-capture.py) installs the
unchanged [matching Release player](ios-r2r-release-packages.md) and existing
fixtures on a new, owned ARM64 simulator. Runtime and Packages remain IL;
trusted player/framework inputs retain their original R2R bytes. This capture
makes no new post-install fixture-production claim.

## Execution evidence

Native calls enter InterpreterStub with bytecode start in x12. Calls already
inside interpreted Runtime or script code can switch interpreter child frames
directly. The capture also stops after ReInit at the first opcode dispatch
of the new method. PrepareInterpreterCode alone is not counted as execution.

In the matching Release source, this child dispatch is interpexec.cpp:3702,
native file address 0x28c1fc. The driver derives the line from the actual source
and requires a unique breakpoint with first instruction ldr w24, [x28].
It reads pFrame and pMethod through DWARF, verifies
pFrame.startIp->Method == pMethod, and verifies x28 == pFrame.startIp + 8.
Stub and child execution samples are labeled separately.
Preparation only opens a short observation window for an unsampled target
MethodDesc. The child breakpoint closes after that confirmed execution, and
all observation breakpoints turn off once the fixed 23 method groups are covered.

Both paths bind InterpMethod.methodHnd to MethodDesc, reconstruct its owning
MethodDescChunk, and follow m_methodTable to MethodTable.m_pModule.
Module.m_path must identify an installed fixture DLL, bound to its verified
SHA-256. Module simple name, PEAssembly, Assembly and mapped base are recorded.
Chunk token range and MethodDesc token remainder reconstruct the MethodDef
token. Offline TypeDef MethodList ranges establish its declaring type/method.
Readable bytecode size/prefix and matching MethodDesc.m_interpreterCode provide
the bytecode identity checks.

Every stop reads its identity anew; collectible pointer reuse is not a stable
identity. Same-name SharedGameplay dependencies are distinguished by actual
private-a/private-b/private-import file paths and hashes. Static SharedHelper.Read
and GenericCounter<T>.Next use method Module identity, without an object receiver.

## Reproduction and acceptance

Copy the driver beside ios-r2r-fix-verify.py, verify-ios-packages.py and the
updated ios-r2r-release-verify.py metadata reader. Pass --app, --packages,
--native, --runtime and a new --output directory. Native requires its matching
.dwarf sibling; runtime requires its matching source. The driver creates and
shuts down its own simulator and preserves all input bytes.

Required samples cover GameScript.OnStart/OnTick/OnStop in source, import and
three private packages, failure.OnStart/OnStop, and SharedHelper.Read plus
GenericCounter<T>.Next in all three private dependencies. Acceptance also
requires fifteen-case functional completion, unchanged app/fixtures and no
capture read error. NSLog test markers can be in stderr; native exit markers
are in stdout. Sampling is not a complete invocation counter. Physical-device
acceptance and runtime-backed execution selection remain separate.

## Recorded capture

The 2026-10-13 local-date attempt uses a new output named
ios-release-package-entry-20261013-attempt3. It records **33 valid samples**,
ten native InterpreterStub entries and 23 child first-opcode dispatches.
All **23/23 fixed required method groups** have one execution sample: source,
import and three private packages each supply all three callbacks; failure
supplies start/stop; all three private dependency paths supply Read and Next.
Every preparation gate in this run is followed by child execution evidence.
The native process and LLDB exit normally with zero; all inputs remain unchanged,
no identity read fails, and the owned simulator shuts down successfully.

The unified-log query is tied to this simulator and app PID 48250, with its
command and start/end UTC recorded. Parsing its 273 JSON events finds 15
individual PASS messages and the exact 15/15 aggregate. The original driver
matched the raw JSON text, whose slash escaping hid that aggregate; its
results.json remains false and unchanged. The
[read-only assessor](../eng/ios-release-package-entry-assess.py) independently
checks actual eventMessage values, all method identities, normal native exit,
original log/driver hashes, unchanged input files and shutdown. Its appended
entry-assessment.json passes with appRerun=false. The current driver parses
the JSON event messages and checks their process IDs directly.

The source remains the private Release CID v2 candidate at commit
8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d, upstream base
0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de. Native SHA-256 is
8ed0a3cae73584f69f59ab43020b3d6a5ae17be9ce9a0f74b7099cffbbfd1a8e.
The identity receipt retains the actual DWARF/source hashes and full bundle
and fixture inventories. These are simulator measurements, with the selective
IL layout and preserved other same-base managed inputs.

Local evidence is under
artifacts/ios-r2r-investigation/20261013-release-package-entry/attempt3.
Both archives were downloaded in bounded chunks and hash-checked:

| Archive | Bytes | SHA-256 |
| --- | ---: | --- |
| Original evidence.tar.gz | 66,559 | 1448c647449b55c41bea5fb879bb273eacf4a126e984da8a74cc6640e8d43a67 |
| entry-assessment-evidence.tar.gz | 77,121 | cb509f29295481b4b55d550182db5c86d711489163e945054d245cb9c0660835 |

Two earlier diagnostic attempts are preserved separately. Global child
breakpoints imposed excessive stop/resume overhead; both were intentionally
interrupted, with explicit diagnostic-abort receipts, without a runtime-fault
claim. Attempt1 retains 24 valid source/import/failure samples, archive SHA-256
2efa4bee7a0454e06c1364c5f275272efc0cd193a2865910d4636f7bced277b6.
Attempt2 retains 19 samples, archive SHA-256
7b3e33a75ea5e56f921aecb35120757d38a098adb381571795bca4eb5afb3cb3.
Their inputs remain unchanged and both owned simulators shut down.
