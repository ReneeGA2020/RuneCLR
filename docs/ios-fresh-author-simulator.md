# Fresh Author IL After Simulator Installation

This 2026-10-15 experiment checks the fixed15-case/73-context budget harness
with author IL compiled after installing a matching simulator application.
It uses the accepted batch-capable runtime with exact accounting selected:
phase-acquire-load1, derived-ledger1, batch interval0, InterpMode0,
InterpretCollectible0 and ReadyToRun1. Method-entry sampling and physical
execution remain separate requirements.

## Build And Preserved Failure

The [original simulator builder](../eng/ios-fresh-author-simulator.py) generates
186 simulator ARM64 R2R components, reusing the accepted trusted raw harness
and device application's `SessionBridge` raw DLL. It uses runtime commit
`3126bbc9a8851a09ac6435b18a12882bad48f3ee`, tree
`710936ae1729a5689ab0e0896f3cf722ddd3d31c`, upstream
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. The simulator runtime build
receipt SHA256 is
`c071b2c67103b5646f37cffdc8a442a8e711105585df9740635459ef1bb86745`.
The original application build completes crossgen/composite/wrapper/signing
with exit0 at `2026-10-14T20:49:31.964742+00:00`.

Its first actual launch crashes before CoreCLR initialization on iOS27.
PID51048 and bundle `org.runeclr.freshauthor.c8f2430e483a` are bound to
`Session-2026-10-15-045803.ips`, SHA256
`d4d9f27d8f1a1ae95997d4388e5cb60d9423543565491601624de0d448efe391`.
The UIKit no-scene-lifecycle trap leads to `UIApplicationMain`; no native
initialization marker or managed result appears. `simctl` exit0 is preserved
as launch-tool success, not application success. This is our custom minimal
UIKit entry's defect, not evidence of a runtime or budget failure.
The failed simulator plist already contains a minimal scene manifest; its
`main.m` lacks the scene delegate and scene-connection configuration. The
manifest alone does not adopt the scene lifecycle. The original device plist
has no scene manifest, a separate difference checked against the actual files.
The original failed application, installed-byte observations, fresh author pair,
crash and owned cleanup receipts remain in their original experiment/archive.
The original owned simulator is shut down and deleted.

## Separate Scene Repair And New Compilation

The [scene-only repair](../eng/ios-fresh-author-simulator-wrapper-repair.py)
creates a new application/output and uses the historically accepted scene
delegate `main.m`, SHA256
`c49f3cd9050f5d6fcbf73b92996e8b3a1c291a7ec0fc7e3d44b4be722f3c670a`,
retaining the simulator scene manifest and assigning a new owned bundle ID.
It changes only the main executable, plist
and simulator signature. All197 other signed bundle files,186 R2R/raw inputs,
native runtime, bridge, profile and delegate wrapper remain byte-identical.
Wrapper/signing/verify exit0 at `2026-10-14T21:03:09Z`; runtime and R2R
components are not rebuilt in this continuation.

The separately frozen [install/run controller](../eng/ios-fresh-author-simulator-continuation.py)
installs bundle `org.runeclr.freshauthorscene.6f740b7c8a85` on owned simulator
`8015359F-25A1-43F5-B12F-3EC7F7316B51`. Installation completes at
`2026-10-14T21:05:02.941246+00:00`; whole signed bundle readback and absent
author-directory verification complete at `2026-10-14T21:05:04.657281+00:00`.
Its actual receipt is
`D:/RuneCLR-Android/device-build/fresh-author-simulator-scene-install-20261015-attempt1/installation/results.json`,
SHA256 `84976011a332c9e5ff1ea4c399d049e1fc21850460e331711432bb3587b5b3b9`.

Only then, two real fixed-source Roslyn processes compile another IL-only pair
in `D:/RuneCLR-Android/device-build/post-simulator-install-author-20261015-attempt2`.
The existing compiler still binds the accepted unsigned device app's shared
contract; a separate ordering receipt binds this compilation to the new
simulator installation. Author binding starts at
`2026-10-14T21:06:24.817364+00:00`, with nonce
`6eade3ff00f14880b7797c2186bdacc1`.

| Assembly | SHA256 | MVID |
| --- | --- | --- |
| Payload | `37483ac26d596c463406ee5feefd0d8866078ce28485b029764e98dc38ada1c2` | `a5a85fe5-30aa-44b7-840f-848c02a24dac` |
| Private | `2d70da9c913bc900b920891d0b77ccf47073d372739785998a413fc6892da2a2` | `3a81270a-c338-474a-84aa-f49eb8a9e489` |

The [author binding reviewer](../eng/verify-ios-device-author-binding.py) passes
all199 unchanged device app files and both compiler/output bindings. The actual
review SHA256 is
`c452286e93bd058c0d77c3cd3b457d6ae23b43291e9f1d7a1e64ee4e4f804cdf`.
The separate `simulator-install-order.json` verifies install/readback before
binding and both ordered compiler starts/ends, and rejects replay of either
the original device pair or the first failed simulator pair by hashes/MVIDs.
The original physical-run plan and its device-bound pair remain distinct.

## Run Acceptance Gates

The sole repaired-app normal launch passes all15 cases/73 collected contexts
without a debugger, PID52220 and launch nonce
`d4e68435470d46d18effa589ada489c8`. The launch runs from
`2026-10-14T21:09:22.195Z` to `2026-10-14T21:09:24.774Z` with exit0 and no
timeout. Six exact native markers bind the actual PID, nonce and profile;
initialization/create-delegate HRESULTs and managed/actual exits are zero.
The template explicitly reports that `coreclr_shutdown` was not attempted.
All installed host and delivered-author hashes match before/after execution.
Recovery includes40 contexts in the same process. A debugger-free functional
pass alone does not establish sampled interpreter method entries.

The [independent reviewer](../eng/review-ios-fresh-author-simulator.py) and
[corruption controls](../eng/verify-ios-fresh-author-simulator-review.py) bind
the full raw/R2R metadata and method bodies, actual native images, frozen build
and continuation sources, installation/compile/transfer ordering and raw
lifecycle receipts. The final full independent run review now passes at
`D:/RuneCLR-Android/device-build/fresh-author-simulator-scene-independent-review-20261015-attempt2/results.json`,
SHA256 `8a6f4536cfea982c240c23f4efcaaeaae43966e66c004473fd3f830ca7b4be46`.
It binds186 raw/R2R assemblies,11 native images,38 runtime source files,
the scene-only difference, actual fresh compilation and delivery,15/73 raw
rows, sole launch and completed cleanup. Its separate controls pass63/63
altered-input rejections at
`D:/RuneCLR-Android/device-build/fresh-author-simulator-scene-independent-controls-20261015-attempt2/results.json`,
SHA256 `5038903b918ebe8704b7894eac4dccae75da8d178a0b28478a996e984ded090c`.

The [independent startup-failure reviewer](../eng/review-ios-fresh-author-startup-failure.py)
also passes the original IPS, signed native UUID, PID/bundle/owned-container,
time ordering, compiler/transport identity, absent initialization and cleanup
bindings, with six rejection controls. It reads the actual crash rather than
the experiment owner's crash summary. Its final attempt3 result is
`D:/RuneCLR-Android/device-build/fresh-author-startup-failure-independent-review-20261015-attempt3/results.json`,
SHA256 `93a2a96fc7279fa9e84f8cad8894ca57b640fb100728dbe88b91ea11d2bde3d5`.
An earlier reviewer incorrectly assumed that the failed simulator plist lacked
the scene manifest; its failed receipt is preserved. The corrected review
checks the actual minimal manifest and scene-less main.

The final three review/control sources and report hashes are frozen separately
in `fresh-author-simulator-independent-source-freeze-20261015-attempt1/manifest.json`
under the same D root, SHA256
`9c6146db67c41b6c98899c9a2a93dd1b0cd9f726926c89d2a369905cec1a4d0c`.
The earlier successful review/53-control run remains preserved.
The root's separate actual-row review already passes15/73 and13 altered-row
controls at
`D:/RuneCLR-Android/device-build/fresh-author-simulator-root-row-review-20261015-attempt1`.
Its separate `transport-check.json` matches six raw native markers,200 installed
bundle files and both delivered DLLs to the actual local compilation, verifies
launch exit0 and confirms owned simulator shutdown/deletion in the retained
device list. All native-entry and physical-device flags remain false.

The full successful receipt archive is retained at
`D:/RuneCLR-Android/device-build/fresh-author-simulator-scene-receipts-20261015-attempt1`.
It contains567 entries and120095911 bytes, SHA256
`cae75138d46e99053d9244757de689656bae0a0a20d0a7823ea3b7fff6f58e84`.
The cleanup result SHA256 is
`d199bad750ffc463d7f47321c01655e84bceaad2711f946358012dd0c464bdd4`.
Owned application/simulator and the one-shot artifact service have exited.

## Next Method Sampling

The separately frozen [entry preparation](../eng/ios-fresh-author-entry-prepare.py)
now passes offline binding of this scene application, current simulator
native/DWARF image, raw/R2R CoreLib and bridge, and the second fresh author
pair's nine required method groups, with13 in-memory rejection controls.
Its receipts are retained at
`D:/RuneCLR-Android/device-build/fresh-author-simulator-entry-preparation-20261015-attempt1/receipts`.
Driver SHA256 is
`0d93b52d36151bb3cd5c02f839b796021c0f33b4a5bdb4bb6b9f8e98cca928b8`;
the small receipt ZIP SHA256 is
`0855e1cc8ab8c65fcbbdbe560043489d0a0d1c824517483e1d38dc330ea97829`.
Full raw DWARF/nm outputs remain on the Mac. Preparation is explicitly draft
and creates no target process or native-entry proof.

Next, implement and independently review the live decoder/observer, then use
a separate owned simulator and diagnostic launch. Each sample must bind actual
native UUID/slide/PC, live frame/startIp, MethodDef token, loaded PE MVID/path/hash,
meter owner, PID/nonce and caller stack. Repeat recovery and owned cleanup.
The old sampler's fixture and derived-ledger0 assumptions cannot be used
unchanged for this derived-ledger1/interval0 application. New post-install
compilation is required to claim that ordering for a new installation.

See [device application follow-up](ios-device-application-build.md#scene-lifecycle-follow-up)
for the separate unsigned-device wrapper continuation and remaining review.
