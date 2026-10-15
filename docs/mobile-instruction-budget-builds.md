# Matching mobile instruction-budget builds

On 2026-10-13, the Windows terminal/finalizer candidate was combined with the
collectible CID publication fix for fresh mobile builds. The iOS simulator
ARM64 and Android x64 Release runtime/CoreLib/compiler builds and independent
product assessments pass. Android has a preserved initial checker failure
and a separate successful review of the same products. A later
[mobile host-budget acceptance](mobile-host-budget-acceptance.md) now measures
15 cases/73 collections in an actual iOS simulator application and builds a
fresh Android framework/layout. The later Android APK run passes the same
15 cases/73 collections with strict installed-inventory binding. Separate iOS
entry samples now cover nine requested author method groups; Android budget
method-entry and physical-device acceptance remain open.

## Exact source composition

The upstream base is `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. The source
is Windows candidate `099dacd07d8d890822f7422f895337733457ab3c` plus only the
CID v2 publication guard in `src/coreclr/vm/virtualcallstub.cpp`. The local
combined commit is `bd9a19c29e2785f6551d47dfb8180da9bf6ef896`; the Mac commit
is `1c623a776b4471e641e95e4e3c82959c6cb9590f`. Both have exact tree
`b54537ff42a066e41a01ea611a21f2e5e49934a1`.

A private Git index independently reapplied all six portable patches to the
official base and produced that same tree. Thirty-seven changed Git blobs
are bound by exact LF hashes in the [source proof](../artifacts/mobile-session-budget/source-review-20261013/source-proof.json).
Windows checkout CRLF hashes are recorded separately. The canonical upstream
checkout and earlier policy/meter/terminal/finalizer worktrees are preserved.

The ordered patches are in [runtime-patches](../eng/runtime-patches/):

1. `0001-collectible-cid-publication.patch`
2. `0003-collectible-interpreter-selection.patch`
3. `0004-interpreter-required-load-context.patch`
4. `0005-native-session-instruction-meter.patch`
5. `0006-session-terminal-prototype.patch`
6. `0007-session-terminal-finalizer-boundary.patch`

This remains the private prototype described by the [host budget contract](host-instruction-budget.md).
The [CID upstream record](upstream-bugs/collectible-cid-lifetime.md) is separate
from our budget/execution-policy changes.

## Fresh matching runtime products

Both platforms use new worktrees, fresh native/managed artifacts and a private
APFS clone of source-build SDK `11.0.100-rc.1.26420.103`. No prior native,
CoreLib or compiler output is copied into either build. Only one expensive
build runs at a time on the 16 GiB Mac. Sanitized child environments leave
global configuration unchanged.

The [iOS build driver](../eng/ios-session-budget-build.py) runs the checked-out
official build for `iossimulator.arm64.Release`, interpreter enabled, Ninja,
deployment target 15.3 and MSBuild `/m:1`. The actual build completes in
5m19.38s with exit0, zero warnings and zero errors. Its ten actual target/host
compile owners have Release flags; target objects contain interpreter/R2R
features with dynamic JIT disabled. The native image and crossarch JIT share
the candidate interface GUID. Three actual CoreLib stages retain the exact
private policy5, meter8, terminal12 and GC3 method families, nested context
constructors, native owner-query signatures and required QCall ABI.
An independent read-only preprocessing run of the actual opcode/finalizer
compile owners preserves textual PCH and removes binary PCH/compile-output
options. It confirms `USE_COMPUTED_GOTO=1`, 346 expanded indirect dispatches
with charging, execution/cleanup accounting bodies and the finalizer definition-
owner branch. Actual CoreCLR symbols include the statically linked interpreter
and the GC/EH owner queries. These are compilation observations, not execution.

Original [iOS build receipts](../artifacts/mobile-session-budget/ios-build-receipts-20261013-attempt1/build/results.json),
[receipt hash index](../artifacts/mobile-session-budget/ios-build-receipts-20261013-attempt1/receipt-file-index.json)
and [independent root binding](../artifacts/mobile-session-budget/root-review-20261013/ios-result.json)
are retained. Large raw build logs, compile databases and preprocessed output
remain on the Mac with sizes and hashes in the index. An independent
[typed metadata review](../artifacts/mobile-session-budget/ios-typed-review-20261013-attempt1/remote/results.json)
also resolves all three CoreLib stages: the GC owner query returns Byte and
takes ObjectHandleOnStack by value; the EH query returns Byte and takes
StackFrameIterator*. Neither has a hidden error-status parameter. Each
factory has its explicit trailing IntPtr* hidden status. This separate review
leaves the frozen build assessor and original receipts unchanged.

| iOS product | SHA256 |
| --- | --- |
| ARM64 native runtime | `d783dbeb5952c123d7081e391510ca72ed69769be33ebf2608a8d4495fa9a789` |
| Published CoreLib IL | `1aa8d6c01d7dadb7cf9aa556aba625837248edbcfa6e94eb01c4d9a4ac1627a6` |
| Matching crossgen2 | `79b68e69e9ced7e12093fd8ecc8331c0c8b3b621e19a6341fd6ab343294622b7` |

The [Android build driver](../eng/android-session-budget-build.py) has separate
`prepare` and one-shot `run --build-slot-granted` phases. The actual
[preparation receipt](../artifacts/mobile-session-budget/android-prepare-20261013/prepared.json)
binds the same source tree, pinned Darwin NDK r27c, private SDK and unchanged
old critical products. The native build uses Android x64 Release, including
explicit runtime/library Release configuration. Build completion, actual
computed-goto preprocessing and exact trimmed CoreLib metadata now pass:
4m38.64s, exit0, zero warnings/errors, thirteen native compile owners and
346 expanded dispatches with charging/denial branches. Corrupted copies
with one charge or indirect goto removed are rejected without changing the
original preprocessed output. Matching GUID bytes occur in the native runtime,
shared interpreter, target JIT and host crossarch JIT. Android allows trusted
JIT compilation; its actual target uses virtual-stub dispatch rather than CID.

Three Android CoreLib stages retain the same exact policy5/meter8/terminal12/GC3
families, constructors and factory/native-owner-query ABI. Both owner-query
value types resolve precisely; PostTrim and ProductIL bytes are identical. A
separate fourth PE is the managed ILCompiler.Compiler assembly, whose required
interpretation flag remains bit33. It is not a fourth CoreLib copy. All seven
critical products and the original source/products retain their hashes.

The frozen first driver has SHA256
`f8d4167c488fda66df5d33a505d45f7275cae6dc5ee0363335b4188216bd6ed9`.
Its aggregate result stays false: a regular expression stopped at the charge
function name before the same-line goto, incorrectly rejecting the compiled
dispatcher. Independent read-only assessment binds that original failure and
actual build exit0, then verifies the complete macro and expanded bodies. The
future driver now reads the whole macro line; no runtime rebuild or app rerun
was needed. The first metadata observer also assumed a nonexistent compiler-
directory CoreLib mirror; that failure is retained before the correct three
CoreLib stages plus compiler-flag PE review. These are our observer errors.
Old Android policy-only artifacts do not establish budget support.

The [original Android aggregate failure](../artifacts/mobile-session-budget/android-release-evidence-20261013-attempt1/extracted/payload/original/results.json),
[successful compile review](../artifacts/mobile-session-budget/android-release-evidence-20261013-attempt1/extracted/payload/build-review/results.json),
[successful metadata review](../artifacts/mobile-session-budget/android-release-evidence-20261013-attempt1/extracted/payload/metadata-assessment/results.json)
and [independent root binding](../artifacts/mobile-session-budget/root-review-20261013/android-result.json)
are retained together. The archive contains 75 members, including 74 individually
hashed payload files; its SHA256 is
`1491e453e714c89b44f891fd6ddb14d5a52098165589900bce47428b6c09c87b`.
The corrected future driver SHA256 is
`8ee55cd98d12af718c0f866c0a9859ee2aa9e6d99b154b9981cf0c7693347135`.
These critical runtime products now feed a
[fresh Android framework/layout](mobile-host-budget-acceptance.md#android-framework-increment).
The matching APK construction and execution are recorded in the actual mobile
acceptance section; method-entry evidence remains a separate gate.

For reproduction, use fresh output directories and the private paths recorded
in each request. The iOS driver requires `--root`, `--output`, `--patches`,
`--source-proof` and `--metadata-tool`. The metadata tool is the trusted
[PE inspector](../eng/runtime-metadata-inspector/Program.cs), which reads PE
metadata using the host SDK without loading the inspected target assembly.
Android preparation requires `--root`, `--output`, `--repository`,
`--source-proof`, `--toolchain` and `--commit`. Its run phase consumes those
frozen inputs. A failed attempt is retained rather than reused.

## Fixed managed adapter and actual desktop control

The [input preparation driver](../eng/mobile-budget-inputs.py) built
[MobileHostBudgetProbe](../eng/mobile-host-budget-probe/Entry.cs) using the
private Windows SDK `11.0.100-rc.1.26425.128`, with zero warnings/errors. It links
the already accepted host fixture source unchanged and exposes a fixed public
`Entry.Run(string[] args)`; this class library has no `Assembly.EntryPoint`.
The four arguments are the author IL directory, fresh writable evidence
directory, owned 32-hex nonce and `all` or a fixed scenario.

The adapter calls all fifteen cases sequentially in one process, deriving a
distinct owned nonce for each case and retaining the original case assertions.
Its result holds only scalar counts, receipt hashes and the process identity.
It restores the trusted console writer after each case; capture both output
streams. Runtime/Packages/Abstractions bytes match the accepted Windows host,
and both author DLLs are copied unchanged rather than recompiled.

The [input manifest](../artifacts/host-budget/mobile-inputs-20261013-attempt1/input-manifest.json)
binds all six DLLs and thirty source files. The input archive SHA256 is
`acf7ac2b4eb61d34e18a0cbe76d7a0e2dcae8e4d4f54e40154587ffd7e06aba4`.

Root actually invoked this adapter on the matching Windows099 private runtime:
**15 scenarios, 73 completed context collections, one process, exit0**.
All six DLL hashes remain unchanged; trusted MapRunner compilation is reported
and no author namespace JIT compilation is reported. The actual
[desktop result](../artifacts/host-budget/mobile-adapter-desktop-20261013-attempt1/actual/result.json)
and raw streams are preserved. This verifies the adapter's desktop invocation,
including repeated bad/good recovery; it supplies no mobile execution evidence.
The [independent adapter audit](../artifacts/host-budget/mobile-adapter-desktop-20261013-attempt1/independent-review.json)
also verifies every row, owned nonce, receipt hash and original Windows IL
identity. Its first offline parser rejected a valid marker with a native
stdout prefix; that failure and the corrected owned-marker parser are retained.
The application and original streams were not rerun or changed. This adapter
smoke test uses the previously accepted private layout; it does not itself
provide a fresh before/after identity audit of every native runtime component.

## Acceptance preparation failures retained on 2026-10-13

The new [iOS acceptance driver](../eng/ios-session-budget-accept.py) is being
integrated in fresh output directories under the private Mac experiment root.
Attempts 1 and 2 stopped before compiling the composite: the driver hash
comprehension accidentally read the final loop variable for every trusted DLL.
Independent SHA256 checks showed the actual transferred DLLs matched the
manifest; this was a RuneCLR experiment-driver defect, not an upstream runtime
failure. The fixed comprehension reads each corresponding file.

Attempt 3 stopped compiling the trusted bridge because its `-nostdlib` reference
set omitted CoreLib. Attempt 4 exposed the adapter's `System.Runtime` facade
reference as well. Both failures are preserved; the revised bridge compilation
uses the matching CoreLib and the complete original framework IL reference set.
The new composite includes that framework IL plus the four current trusted
assemblies and bridge. Old generated components and bundled author fixtures
are removed from the template. Author DLLs remain outside the preinstall app.
Attempt 5 completed full-framework crossgen and composite linking, then failed
in the native wrapper: an unanchored `setenv` cleanup expression partially
matched `unsetenv`, leaving an invalid `un` token. Wrapper cleanup must remove
complete anchored lines, and the completed composite can be reused only with
its exact stage provenance and hashes recorded. These are preparation fixes;
none of these failed attempts supplies mobile budget execution or
interpreter-entry evidence. Attempt 6 then reused the completed composite
with explicit hashes, repaired and signed the wrapper, and completed the
[actual simulator run](mobile-host-budget-acceptance.md). The successful
wrapper/sign logic is now shared by fresh build and repair. The
[fresh driver preflight](../artifacts/mobile-session-budget/ios-fresh-driver-preflight-20261013-attempt1/results.json)
actually passes clang and produces the same wrapper bytes as the executed
application; it does not rerun that application. Final driver SHA256 is
`cfe2ab27a62e84cbc3b181f40b582d1cb90ab6c93a8323f2de49d2ec5c1cc8a7`.

## Next acceptance

Rebuild the trusted executable bridge and framework/host composite using each
platform's new native runtime, CoreLib and crossgen2. In iOS mode0 without JIT,
all four trusted DLLs need matching R2R bodies. Keep both author DLLs outside
that composite as collectible IL; transfer them after application installation.
Do not substitute old policy-only CoreLib or carry over old app receipts.

Run the same fifteen budget scenarios with owned launch identities and
watchdogs, validate native termination/reason/cleanup counts, completed
collections and recovery, and capture method-level interpreter entries from
these exact author DLLs. Separately repeat the unchanged lifecycle/player and
relevant upstream controls on the patched mobile runtime. Release computed-goto
compilation alone does not establish dispatch or correct termination.

Physical-device execution remains open; see [iOS device prerequisites](ios-device-readiness.md).
Shared locks, blocking native/framework calls, concurrent termination, actual
IL fault clauses, finalization storms/resurrection and overhead remain separate
limits of the prototype. Production packaging still rejects authored finalizers.
