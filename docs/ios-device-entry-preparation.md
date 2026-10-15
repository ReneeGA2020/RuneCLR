# iOS Device Interpreter Entry Preparation

On 2026-10-15, offline preparation binds the actual device ARM64 native image,
its DWARF and the device-bound author pair to nine requested method groups.
This prepares a future observer; it does not sample a running process.

The [preparation tool](../eng/ios-device-entry-prepare.py) passes on the
configured Mac in `ios-device-entry-preparation-20261015-attempt3`, with
13 rejection controls. Failed attempt1 and the earlier passing attempt2 are
preserved. Downloaded receipts are retained at
`D:/RuneCLR-Android/device-build/ios-device-entry-preparation-20261015-attempt3`.
The receipt ZIP has 73 members, 156321 bytes and SHA256
`857c53b01180ece2d5cb70a784d7e6f1c05af549cdd28c19ffabb5f39fbd8a70`.
Full raw DWARF dumps remain on the Mac; downloaded exact DIE subtrees include
the original dump hashes, sizes and character offsets.

## Actual Device Layout

The device `libcoreclr.dylib` SHA256 is
`34c27daf3d6ef73a1558c21733d9f101bea4dcc839b9380d182d68cea2e2b93b`,
with UUID `8d0cfc4395f633dba043d5a1c116dad1`. Six DWARF layouts and
80 instructions are bound to this image. The device child dispatch contract
uses source line3784 / PC `0x2f8b54`, beginning with `ldr w8,[x9]`.
The frame pointer is loaded from `x19+0x98` (152); the older simulator
offset `+0x88` must not be reused. The frame store is at `0x2f8b18`, bytes
`684e00f9`, and the contextual header load at `0x2f8b24`, bytes `288540f8`.
The InterpreterStub at `0x3d470c` assigns the bytecode register with
`mov x19,x12`.

The `pFrame` DWARF location range `[0x2f8b20,0x2f8b48)` covers the contextual
header load, but does not cover the proposed capture PC. Consequently
`pFrameDwarfCoversCapturePc=false` and `liveRegisterContentsVerified=false`.
A future observer must verify the live registers at its actual stopped PC.
Static disassembly alone cannot establish that those registers contain the
expected frame or author method during execution.

## Independent Review And Remaining Gates

The root's separate `root-review.json` directly checks the downloaded device
native bytes, all80 instructions, the `pFrame` subtree and the actual original
author metadata. It passes all nine required method groups and the13 controls.
The original device-bound pair in
`D:/RuneCLR-Android/device-build/post-device-app-author-20261015-attempt1`
remains distinct from later fresh simulator pairs. Its payload/private MVIDs
are `f3b655ec-5458-45b1-aeb4-2bc9f73bff7a` and
`08897279-36fe-4a3e-b555-e2c75ad22db6`.

Physical-device, installed-host, delivered-author and native-entry proof flags
remain false. No target process was launched or attached by this preparation.
See [device readiness](ios-device-readiness.md) and
[the unsigned application build](ios-device-application-build.md) for the
separate signing, installation, delivery and lifecycle prerequisites.
The simulator scene-entry failure also requires a device wrapper continuation
before future iOS27 application acceptance; it does not alter this native
runtime/DWARF contract.
