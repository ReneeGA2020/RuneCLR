# Session-origin reflection policy experiment (2026-11-12)

Status: experimental snapshot, kept off the integration line.
`main` and the private runtime `runeclr/dev` do **not** include this work.
No public policy, default selection or API surface is changed by this snapshot.

## Pair and exact parents

| repository | branch | exact parent commit |
| --- | --- | --- |
| `ReneeGA2020/RuneCLR` | `experiment/session-origin-20261112` | `bdbc7f52f82eda342c43559cbeabc2ac484fe484` |
| `ReneeGA2020/runtime` | `runeclr/session-origin-20261112` | `7cbdad39669188c1f49f0a41216829d9a9005591` |

Paired runtime commit: 35f6c0e84112de967089a6167df94d23bb7c3b16.

The runtime commit is based on the published reflection-policy commit and is not rebased
onto newer upstream. The host commit adds only the opt-in session-origin surface plus tests.

## What the pair adds

- Runtime: `RuneCLR_GetReflectionPolicyCapabilities` reports capability bit 0
  (`SessionOriginCapability`) and `RuneCLRReflectionPolicy_GetStackLoadContext` returns the
  managed `AssemblyLoadContext` of a bounded 16-frame stack walk. No managed ALC handle is
  returned when the walk saturates or fails.
- Host: `PrototypeRequireOriginScan` on `MapRunOptions` and `HostContractSessionOptions`
  binds the capability before author loading. With a runtime that does not expose bit 0 the
  option fails closed with `PlatformNotSupportedException` and no author assembly is loaded.
- Tests: `tests/RuneCLR.SessionOrigin.Tests` plus the author/chain/compiled fixtures, and
  `eng/verify-runtime-session-origin.py` (14-mode matrix, capability/gate/overflow/disposal checks).

## Honest behavior note

The runtime reads `RuneCLR.EnableReflectionPolicyOriginScan` from the startup `AppContext`
and treats an **absent** switch as enabled, so a process that attaches reflection-policy
sessions scans stack origins unless the switch is explicitly set to `false` at startup.
`PrototypeRequireOriginScan` is a capability assertion, not a behavior toggle: it neither
enables nor disables scanning. Do not read this snapshot as proof that default behavior is
unchanged for every host.

## Evidence and scope

Acceptance was local, not published. Receipts are kept outside the repositories as local
archival identifiers (not links, not downloadable from here):

- `RuneCLR-session-origin-evidence-20261103`: 14 checks / 265 pins, later 15-check replay /
  398 pins with zero drift, runtime head `7cbdad39`, source manifest sha256
  `5805d37f01c596e034d094fec01c6427c9965e819feae7c40e9490b9695b6a05`.
- `review-origin-x3yd-20261103`: independent source review, 39/39 static checks, findings F1-F9
  resolved in the harness/driver with replays.
- Interpreter/JIT and stock/private compatibility receipts are in the same archived bundle.

No new build or test was run for these commits. The source bytes are the accepted snapshot
bytes; a matching private runtime build is required to reproduce the matrix:

```
py -3 -B eng/verify-runtime-session-origin.py \
  --runtime-root <runtime worktree> --layout <composed layout> \
  --corelib <Checked System.Private.CoreLib.dll> --runtime-source-manifest <manifest.json> \
  --output <new empty directory> --expect-fixed
```

Remaining gaps stay open: native walker status 1 (more than 16 distinct non-default load
contexts) and status 2 (walker error) coverage, compile-only suppressed child, unmanaged entry,
AOT/mobile, global all-load enforcement, and the published walk-cost bound. No sandbox,
native/R2R body, device or unload claim is made.

## Source pins

Host files (16) are byte-identical to the tested snapshot. The two documents were sanitized:
drive-prefixed local paths were replaced with `<local-archival>/`; their tested and published
hashes are listed separately and they are **not** byte-identical to the tested copies.

| file | sha256 |
| --- | --- |
| `RuneCLR.slnx` | `d87b2e02056d057dbc2be5c57039f8197dd5a571debc563e807fd4c37deb2dc3` |
| `src/RuneCLR.Runtime/HostContractSession.cs` | `65f23cc0c2566120287d1181ee24dd229249b71f4e1ef9745c635748420343d8` |
| `src/RuneCLR.Runtime/HostContractSessionOptions.cs` | `8cbeb46a2f3f37e9d9da9999990e3ea5fbf5f6ad822f2d70a51a9b7be5e5df71` |
| `src/RuneCLR.Runtime/MapRunOptions.cs` | `7a414a868971824142fc81372395fe3273c06cb0839d789ce260befea5321b1d` |
| `src/RuneCLR.Runtime/MapSession.cs` | `122481ee6ad36c1e9e3abc677245d2f07d1dbcb9106d73a6115ee593f2737114` |
| `src/RuneCLR.Runtime/PrototypeReflectionPolicy.cs` | `ee8f30e33ff887924ac23692f0b2a81e70da35916fa4ada96c99539fda9d19a3` |
| `eng/test-session-origin-provenance.py` | `c88f7571e4924308e09eb4d203ee2eaf191e55dd0f5e3fce441c58b2da010aab` |
| `eng/verify-runtime-session-origin.py` | `62e4570902e5fa95e320c09d053af1249006f50e76271c1d9bf7feb285e457ea` |
| `tests/RuneCLR.SessionOrigin.Tests/Program.cs` | `c1d8b8bfb8d0ef5c6a0dc9203ff8592dcffc5e58601fcd0065a659b9bcef6239` |
| `tests/RuneCLR.SessionOrigin.Tests/RuneCLR.SessionOrigin.Tests.csproj` | `633f3bbaeb06793b67d2958b23a0bb2bf25bebd42051dbb646c38ab448e02e46` |
| `tests/SessionOrigin.Author/OriginScript.cs` | `2a2820a3ccf45bec807bc353c3b993975dab62c5afff7c30828813227fc7d4bd` |
| `tests/SessionOrigin.Author/SessionOrigin.Author.csproj` | `d8981b2c04dccdbf986fd79dbe8dd2bfa51841a4779e3ad45cfd1712c695224d` |
| `tests/SessionOrigin.Chain/ChainStep.cs` | `5bd2438911047394b6484f41bf7e6bff87ac06467ae84d090324ee572c99de18` |
| `tests/SessionOrigin.Chain/SessionOrigin.Chain.csproj` | `8d654c44b7bebb6b31a9f2f606927f45b5072193adc4eef8cce3f3cf3b278df3` |
| `tests/SessionOrigin.Compiled/OriginHooks.cs` | `ae4f45c5227ab84dd07223bbb2e164d9b3dbb865700ec6b2d3d3987a40880258` |
| `tests/SessionOrigin.Compiled/SessionOrigin.Compiled.csproj` | `e6fcb8e1e93a724d47a829cffd19d47840a5eb088e9ace43f3a34bbaf1524b07` |
| `docs/development.md` (sanitized; tested `25a3d8e88864dd135c40cc8f35e8dbd6107e632bb02daedf2947014279ebe336`) | `ceae5459782d6abcb95f34795e58f879c7be2ea94ca9a2ce500aa2f13b2502b6` |
| `docs/ugc-session-policy.md` (sanitized; tested `72acbc73add0a4091318c3de6ee4f214486fa6d71ceea929a617b5a32f17f699`) | `a789c83768456adcd9f4bc128c2a762430ab10f988380751de759433197a4634` |
| `src/coreclr/System.Private.CoreLib/src/ILLink/ILLink.Descriptors.Shared.xml` | `c28a8de2bc362b524c9cfd0db8a43ec7e19dc214382b316c055c9dcf52dcdf5d` |
| `src/coreclr/System.Private.CoreLib/src/System/Reflection/RuneCLRReflectionPolicy.cs` | `1a4582aa690c794f3c7565560c694d1b52943d8c747f5e1d8771ea956772b56c` |
| `src/coreclr/vm/assemblynative.cpp` | `5e6f61a0180f553d4685572a3219cd7d42d7e4e719158bf683d31a690bb28f28` |
| `src/coreclr/vm/assemblynative.hpp` | `88bc13363f5d280fdfcbef1ad61ade76393a7d9df2e12cc90682e480b22b3bfc` |
| `src/coreclr/vm/qcallentrypoints.cpp` | `3283add5979f1b44ac22c94cce3fe8062f2ebf9a0c40f3aac81cfa8f909b22cf` |

The runtime files match `source-manifest.json` (base = head = `7cbdad39`, no extras, no deletions).
