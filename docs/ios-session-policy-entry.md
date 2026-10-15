# iOS immutable-session entry preparation

On 2026-10-13, [the independent driver](../eng/ios-session-policy-entry.py)
validated the [session-policy fixture](session-interpreter-validation.md) on
an ARM64 iOS simulator with matching Release native/CoreLib and trusted R2R
inputs. Actual native entry capture covered all nine required method groups;
the separate functional markers passed twenty sessions and twenty completed
context collections with the global collectible diagnostic switch off.
These are simulator results, not physical-device evidence.

The source preparation preserves the existing constructor, callback,
private-dependency, generic and delegate bodies. A generated Host-only adapter
handles the mobile native bridge invoking its entry point with zero arguments.
It defaults to the required factory, loads `plugin/SelectionProbe.Payload.dll`
and its private dependency, writes copied scalar/metadata evidence under a
temporary directory, and runs the existing twenty-session functional fixture.
It does not change the original desktop sources or production host.

## Inputs and entry observation

The trusted composite receives `SelectionProbe.Host.dll` and the shared
`SelectionProbe.Contract.dll`. Payload and private dependency stay plain IL
outside that composite. The capture requires actual producer and installed
absolute module paths, unchanged SHA256 values, and matching Release native,
CoreLib/compiler and source provenance. Native requires its `.dwarf` sibling.
The preparation compares installed native code/data with the supplied product.
Runtime build configuration and matching managed-input verification remain
the build receipt's responsibility.

Nine fixed execution groups are selected from actual TypeDef/MethodDef
metadata, without loading payload code:

- Payload entry static constructor, instance constructor and `Run`.
- Payload generated `Run` delegate body.
- Private helper static constructor, instance constructor and `InlineAdd`.
- Private generic `Identity` and generated private delegate body.

Generated display-class ordinals are read from metadata; the preparation does
not guess their names. Every native stop re-reads the live MethodDesc chunk,
MethodTable and Module path, token, bytecode pointer and bytecode prefix.
Recycled collectible pointers are not cached as identity.

`InterpreterStub` stops observe x12 bytecode at a native transition. The
preparation breakpoint only opens a short observation window. An interpreted
child is sampled at the first actual opcode dispatch after ReInit, with
`pFrame.startIp->Method == pMethod` and x28 equal to the bytecode start plus
eight. The exact line is derived from matching `interpexec.cpp`; LLDB requires
one location and the first instruction `ldr w24, [x28]`. All observation
breakpoints disable once the required set is covered. This reuses the reviewed
[Release capture mechanics](ios-release-package-entry.md), without Debug-only
InterpDump/InterpList requirements.

Nine sampled groups are not a claim that all 26 desktop groups were captured,
or that every invocation was traced. The independent managed twenty-session
markers establish values, static reset and completed context collection.
Factory version 1, default policy 0, required policy 1 before/after explicit
loads and late private dependency resolution, and post-Unload query rejection
are required separately. Deterministic load/run/retirement phase counts are
checked exactly; framework resolver request counts may differ with the mobile
composite, but every observed required-context query must be 1.

Ordinary context policy 0 remains acknowledged by the private API. An ordinary
IL body on iOS with native compilation unavailable is not the Windows JIT
positive control. A separately attempted unsupported lane must preserve its
actual outcome; a crash cannot be relabeled as successful expected rejection.

## Preparation and operator capture

    python3 eng/ios-session-policy-entry.py fixture --output NEW_SOURCE_DIRECTORY

Build Host and Payload from the prepared sources through the private SDK.
Include trusted Host/Contract in the matching composite; copy only payload/
private IL to the installed plugin directory. Install/launch remains external.

    python3 eng/ios-session-policy-entry.py prepare \
      --native MATCHING_PRODUCT/libcoreclr.dylib \
      --runtime MATCHING_RUNTIME_SOURCE \
      --app INSTALLED_APP \
      --payload PRODUCER_IL_DIRECTORY \
      --installed-payload ABSOLUTE_INSTALLED_PLUGIN_DIRECTORY \
      --output NEW_CAPTURE_DIRECTORY

Launch the selection phase waiting for debugger, with InterpMode=0,
RuneCLRInterpretCollectible=0 and RUNECLR_PROBE_FACTORY=required. Attach LLDB
and source NEW_CAPTURE_DIRECTORY/capture.lldb. Save stdout/stderr and lldb.log;
PID-bound unified JSON can supplement markers.

    python3 eng/ios-session-policy-entry.py assess \
      --output NEW_CAPTURE_DIRECTORY --app-pid ACTUAL_CAPTURED_PID

Optional mobile lane `RUNECLR_PROBE_LANE=refusal` loads the unchanged
`plugin/Refusal/SelectionProbe.Refusal.dll`; the operator must set exact scoped
`RuneCLRInterpreterRefuseMethods=SelectionUGC.Refusal.Entry:Reject`. Assessment
with `--refusal` additionally requires actual `CORJIT_SKIPPED`, managed
`NotSupportedException`, the refused context's completed collection, and the
twenty subsequent normal sessions. It does not demand an interpreter entry
for a body deliberately declined by the compiler.

The helper never starts or shuts down a simulator, builds/edits a runtime,
installs an app, or attaches a debugger. The invoking capture procedure must
retain its simulator/PID/exit/shutdown receipts. It must additionally verify
the native stdout markers for mode 0/diagnostic switch 0 and managed exit zero,
plus LLDB exit zero and simulator shutdown. The frozen read-only entry assessor
checks normal process exit and the separate managed session/ownership markers;
it does not replace those outer capture configuration/exit checks.
Physical-device support,
concurrency, submitted R2R bodies, hostile reflection/native code and author
creation of unmarked contexts remain unverified boundaries.

## Preparation record

Local source-only output is
`artifacts/session-policy/ios-fixture-prepared-20261013`.
Python AST and generated LLDB helper parse checks passed. Read-only PE metadata
inspection selected all nine target groups from the actual fixture assemblies.
Root subsequently authorized compilation only: Host, Payload, Refusal and
Boxed all built with zero warnings/errors using private SDK
`11.0.100-rc.1.26425.128`. This initial preparation ran no application;
the separate actual simulator capture is recorded below.

The transfer archive is
`artifacts/session-policy/ios-selection-inputs-20261013/selection-inputs.zip`,
29,706 bytes, SHA256
`77940f51e9e7cf1009f9c5e01f17e6c91d5b06ae95f7741e620a27791dcf734a`.
Its `selection/input-identity.json` pins actual DLL/source hashes and exact
metadata groups. Contract copies from all project builds are identical; the
plugin directory contains no shared-contract duplicate. Adapted host source
SHA256 is `0d94c1baa39a21520ccc94a263cadfa726864ea5ab4fcf7fb21fb9d43d82f753`.

The uploaded entry driver is frozen at SHA256
`a6b18c4a813ac7a21956b14003b49e6cce533c2311e89d680e5ad0d74e3bfb7c`.
The first combined matching player includes selection IL under its app plugin
directory. Unless an explicit Documents path is supplied in the mobile
adapter environment, its actual Module paths therefore refer to that installed
bundle plugin, and no post-install selection-production claim follows from
this fixture. Newly produced late-map production is a separate harness lane.

## Recorded Release execution

The actual capture is under the remote experiment root at
`ios-session-policy-entry-20261013-attempt1`, with app PID 85731.
`entry-assessment.json` passes with `appRerun=false`. The native
capture ran once; subsequent receipt/hash inspection did not rerun the app or
assessor. Its matching combined runtime is private commit
`1724cdec553a7aff7a373a271a4be612651c7625`, upstream base
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`.

| Observation | Actual result |
| --- | --- |
| Required native execution groups | 9/9, each with one valid sample |
| All native execution samples | 11: six InterpreterStub transitions, five first-opcode child entries |
| Extra observed groups | Payload and private generic static constructors, one sample each |
| Independent functional sessions | 20 correct results/static resets; 20 contexts collected |
| Required native policy queries | 260, every query value 1; version 1 and default-context policy 0 acknowledged |
| Late private helper ownership | 20 absent-before-run and 20 loaded-after-run markers; resolver loads into required owner |
| Post-Unload query boundary | 20 `InvalidOperationException` protection markers |
| Interpreter refusal | Not run in this capture; `refusalVerified=false` |
| Native transport | Mode 0 / diagnostic switch 0, LLDB exit 0, managed native exit 0, unchanged bundle, no recorded crash/assertion |

The nine sampled required groups are the payload Entry constructor/static
constructor/Run/delegate body and private PrivateState constructor/static
constructor/InlineAdd, PrivateGeneric.Identity and private delegate body.
The live bytecode pointer and MethodDesc identity checks bind each to the
installed IL file hash and actual MethodDef token. Observation stops once
that fixed set is covered; this is not a trace of every call or all 26
desktop bytecode groups.

Native policy phase counts are 20 before load, 40 before explicit load,
40 after explicit load, 80 resolver requests, 20 before Run, 20 after private
resolution, 20 after Run and 20 before unload. Managed markers came from
the PID-bound unified eventMessage stream; stdout additionally establishes
native configuration and zero managed exit. Independent outer transport
receipt and method-entry assessment both pass. Simulator cleanup/archive
completion is recorded by the invoking procedure separately and is not
inferred from this entry assessment.

The new child first-opcode breakpoint comes from matching source line 3707,
with one location and `ldr w24, [x28]` as its first instruction. It does
not reuse the older CID Release source line or native address. Native/DWARF
UUID is `5E96E0B4-0C9C-3038-AECC-641B1CF9D4F8`.

| Bound input / receipt | SHA256 |
| --- | --- |
| Native | `891cec1e2880ef983110ba4487ed63f8cd2a524c3fad8f1ea7acd7495b509c69` |
| DWARF | `dfeb2f50f058ae2d03d43cc640979b47c2a0dbfb86a6693fb65496401c5a44e6` |
| Matching interpexec.cpp | `3e90e1c04ce527f3e0876a4c21ece30b3f8e935faa445e928dd2c0e2a3f2b02e` |
| Entry assessment | `4686126991370bbae391effd3b847a64d2a6d2fec210a9c4a195b1ef8e29df30` |
| Outer transport result | `e55431a536540fe026ff479aa6919f047a77a12cb73cfb4534a9a75e60c9b7b9` |

Payloads were the compiled fixture IL already copied into the installed app's
plugin directory. This capture establishes required-session execution of
those installed bytes and repeated retirement, without a claim that the
selection fixtures were produced after this player build/installation.
Ordinary IL/JIT comparison, mobile refusal/fallback, submitted R2R fixture
bodies and physical-device acceptance remain separate work.
