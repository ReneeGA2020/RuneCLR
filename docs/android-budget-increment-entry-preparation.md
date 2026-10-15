# Android counter-increment method-entry contract preparation

On 2026-10-14, offline inspection of the actual new Android x64 Release
native images, matching separate DWARF and source produces a SHA-bound
entry-observer contract. This is **preparation only**:
`nativeEntryProof=false`. No emulator, app or attached debugger runs, builds,
APK changes or LAN services form part of this experiment.

The candidate is commit `112e97408de1ae1c2a6cbd2967dcd250cd2d491c`, tree
`91673a7980bda79006259e525741fecb04324444`, from the
[matching build](mobile-budget-increment-builds.md). Its new application has
separate [functional acceptance](android-budget-increment-acceptance.md).
Neither those functional results nor the
[old entry samples](android-budget-entry-acceptance.md) establish new
candidate method-entry evidence.

## Actual emitted-code changes

Matching LLDB source-line resolution and llvm-dwarfdump lookup independently
locate the regular child first-opcode dispatch at source line3751. Actual
ELF load-segment bytes and llvm-objdump support the following contract.

| Contract | Previous mobile image | New candidate |
| --- | --- | --- |
| First-opcode file PC | 0x3afe8d | 0x3b0aff |
| Opcode pointer register | r12 | r14 |
| Context spill | rbp-0xe40 | rbp-0xe48 |
| Typed startIp field offset | 8 | 8 |
| Preceding ReInit distance / checked bytes | 74 / 33 | 73 / 32 |
| Preceding frame reload distance / checked bytes | 97 / 7 | 96 / 7 |

The new first four dispatch instructions consume17 bytes. They read
`(%r14)` into ebx, reload the context from rbp-0xe48, load startIp through
offset8, and load the method pointer from that bytecode header. ReInit
stores r14 as startIp, loads the method and advances r14 by8. Multiple
DWARF type definitions consistently report startIp offset8. Optimized
pFrame local-variable locations are not claimed.

The [independently named adapter](../eng/android-budget-increment-entry-capture.py)
preserves the previous observer. Its future live preparation path pins the
new file PC, registers, spill and preceding byte sequences. The current
`contract` phase only produces the observer and offline receipt; it supplies
no invented live PID or nonce. Parent and four actually used render/metadata
dependencies are SHA-checked before rendering or inspection.

The `contract` command has actually executed successfully. The adapter's
`prepare` path and live LLDB capture have not executed. Its rendered observer
has no actual owner PID/nonce capture configuration; rendering and syntax
checks alone do not finish live preparation. A new gated APK/JNI bridge still
needs to be constructed and adapted for this exact candidate. The old
`android-session-budget-entry.py` runner cannot be treated directly as a
new-tree acceptance tool.

## Bound native and symbol inputs

Both actual native images and separate debug images have matching GNU build
IDs, in addition to exact SHA256/size bindings:

| Image | Build ID | Separate debug size |
| --- | --- | ---: |
| libcoreclr.so | 2a412f8dd3b32fdcb922998a5714fcb66168f8f7 | 43298896 |
| libclrinterpreter.so | 2c6760b98afce18dbcc688b4df8425e07b93ddd7 | 1952536 |

The core native SHA256 is
`d2e2b148216d14bd7f05175a4c61c413673def17a3781e723a83ca940ba859d6`;
its debug SHA256 is
`bd61167be1610de7e22c0ff5b1b2e7cdc997773ddf45df26b19ed6fbf78af919`.
The receipt binds the interpreter image/debug hashes separately. Both large
debug inputs remain on the Mac; only small receipts and raw textual logs
are downloaded. Live runtime commit/tree, tracked-clean status, all37 changed
source files and exact build/source-proof receipts are checked.

Five actual negative controls reject the old native image, old symbols and
one-byte changes to dispatch, ReInit and frame reload. Positive and negative
checks share the same SHA/code validators; altered code exists only in memory.

The [final receipt](../artifacts/mobile-budget-increment/android-entry-contract-20261014-attempt1/raw/results.json)
and [archive](../artifacts/mobile-budget-increment/android-entry-contract-20261014-attempt1/receipts.zip)
bind21 members and82010 bytes. Archive SHA256 is
`f59956bd377389fd5a6a16c7c62f0e5a61c5bf53cb8dec4432350bbccdf7bdc7`;
downloaded size/SHA and all20 indexed raw files pass. The final driver
SHA256 is `727b5d374d2eafcb90a58e4455393331fbf3b94ee1e4d04321728a4228984b34`.
Exploratory and first contract attempts remain on the Mac; the final frozen
output is `ROOT/android-budget-increment-entry-contract-20261014-attempt3`.

An [independent local review](../artifacts/mobile-budget-increment/root-android-entry-contract-review-20261014-attempt1/results.json)
reads the actual downloaded APK native ELF rather than using the log as its
machine-code authority. It verifies all three code pieces, decodes the r14 and
rbp-0xe48 contract, matches 34 logged instructions to actual bytes and checks
all 20 archived files and five pinned dependencies. Three additional in-memory
byte alterations are rejected. New DWARF remains a review of hash-bound Mac
command output; the large symbols were not downloaded and reparsed locally.
This review also reports preparedOnly=true and nativeEntryProof=false.

This offline preparation originally left fresh installation, real owner
PID/nonce and assessed live samples open. The later independent
[new application entry acceptance](android-budget-increment-entry-acceptance.md)
now supplies178 samples across nine requested groups and a same-APK gate-off
15/73 run. Original prepared-only receipts retain their scope unchanged.
Physical-device, complete-invocation and receiver-MethodTable coverage remain
separate.
