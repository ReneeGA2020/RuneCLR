# Mobile Batch Build Preparation

On 2026-10-14, the Windows interval candidate is composed with the existing
collectible CID fix for a separate mobile source candidate. This preparation
does not establish mobile compilation, interpreter execution or performance.
Windows [best-exact timing](budget-batch-best-exact.md) keeps N100 opt-in and
does not justify making N1000 the preferred interval.

## Verified Source

Commit3126bbc9a8851a09ac6435b18a12882bad48f3ee, tree
710936ae1729a5689ab0e0896f3cf722ddd3d31c, is a direct child of Windows
d0da7df. Its only additional changed file is virtualcallstub.cpp for CIDv2.
Three private-index compositions produce the same tree: Windows batch plus
CIDv2, previous mobile derived-ledger plus four batch files, and upstream
0d73c1f2 plus the ten pinned patches.

The [actual source proof](../artifacts/mobile-budget-batching/source-review-20261015-attempt6/source-proof.json)
passes 38 actual LF source files and 21 source/missing-patch rejection controls.
It retains FEATURE_INTERPRETER guards, computed-goto/switch charging and trap
flush contracts. The new sparse worktree is tracked clean; original Windows
and mobile source/index observations remain unchanged. Earlier failed tool
attempts are preserved, including anchor, sparse-index, newline and output-name
errors; they are not runtime failures.

The [root independent review](../artifacts/mobile-budget-batching/root-source-review-20261014-attempt1/results.json)
matches all 38 working files with actual Git blob bytes, commit/tree and exact
Windows/previous-mobile deltas, and checks the recorded rejection inventory.
It also verifies the Git transfer bundle's sole head and unchanged SHA.
The bundle is 3669 bytes, with prerequisite29ff781 and SHA256
93ad55938cc9c9572a07d977199bc1ecae65b9472b260f1c1c8a9d911239c85e.
On 2026-10-15, the bundle was imported once on the remote Mac. The detached
full source checkouts retain the exact commit/tree and all 38 LF blob hashes;
the original checkout/index and earlier products remain unchanged.

## Next Build

The [prepared build entry](../artifacts/mobile-budget-batching/source-review-20261015-attempt6/mobile-build-entry.json)
records exact source/proof/bundle identities and official iOS simulator ARM64
and Android x64 Release build arguments. Both fresh official builds now pass
exit0 with zero warnings/errors; see [matching build acceptance](mobile-batch-builds.md).

The existing derived-ledger builders retain their 37 sources, nine patches and
64-byte meter checks. Separate batch adapters now bind 38 sources, ten patches,
meter72/alignment8 and interval offset64. Each remote build uses a fresh full
checkout and private SDK clone. Actual compiled objects/compiler preprocessing,
native metadata and three matching CoreLib stages pass separately from the
source composition proof. The root independently rechecks both downloaded
preprocessing outputs and all 69 archived receipt members.

Fresh five-lane application checks now pass on the iOS simulator and Android
emulator: normal completion, partial settlements, quota termination/catch
suppression, cleanup and same-process recovery, with168 collections each.
Separate iOS direct-method entry sampling also passes. Android method entries
and actual long-kernel settlement cadence remain next; see the matching build
acceptance for distinct raw evidence. Numeric intervals100/1000 use
canonical hexadecimal DWORD values64/3e8. Mobile timing, physical-device loading
and repeated retirement remain distinct acceptance steps.
