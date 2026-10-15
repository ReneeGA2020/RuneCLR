# Matching iOS simulator session-policy build

On 2026-10-13 a fresh private Release build completed for the immutable
session policy already accepted on [Windows](runtime-session-policy-build.md).
This page records matching build provenance; actual mobile execution and
physical-device acceptance are separate gates.

## Source and isolated build

Official base: `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`.
The independently [reviewed combination](ios-session-policy-source-review.md)
applies patches 0001, 0003 and 0004 in that order: CID publication lifetime,
required-body selection and immutable context policy. Its tree is
`71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2`, exactly the Windows
`5972a869...` source plus the CID guard in `virtualcallstub.cpp`.
The new Mac detached commit is
`1724cdec553a7aff7a373a271a4be612651c7625`; all 27 changed-file hashes
and individual patch identities are recorded in `source.json`.

The [build driver](../eng/ios-session-policy-build.py) uses a new worktree
and output, `ROOT/ios-session-policy-release-20261013`. Only the fixed
SDK `11.0.100-rc.1.26420.103` is APFS-cloned; native objects, generated
headers, CoreLib and compiler products start empty. It does not replace
the installed runtime or modify the preserved baseline.

```sh
python3 eng/ios-session-policy-build.py --root ROOT --output NEW_OUTPUT --patches PATCH_DIRECTORY
```

The recorded official build command is:

```sh
./build.sh clr.runtime+clr.native+clr.corelib+clr.tools+clr.crossarchtools \
  -os iossimulator -arch arm64 -cross -c Release -clrinterpreter -ninja \
  -cmakeargs -DCMAKE_OSX_DEPLOYMENT_TARGET=15.3 /m:1
```

The private compiler interface changed with patch 0003. Matching native
CoreCLR, CoreLib, crossgen2, JIT interface and cross-target compiler inputs
must therefore be rebuilt together. Earlier CID-only Release products
are retained as historical evidence and are not inputs to this candidate.

The first clean invocation completed with exit 0, **0 warnings and 0 errors**,
in 5m03s. Source remained tracked-clean and the baseline native hash was
unchanged. Local copied build receipts are in
`artifacts/ios-session-policy/20261013-release-build`.

| Matching product | SHA-256 |
| --- | --- |
| libcoreclr.dylib | `891cec1e2880ef983110ba4487ed63f8cd2a524c3fad8f1ea7acd7495b509c69` |
| IL/System.Private.CoreLib.dll | `ae328f90d5feb596d1331581d54be6c2a455bcb42175690fddd90bd962c1e1eb` |
| arm64/crossgen2/crossgen2 | `18ef35a8431cd794b3850a2ef1bd0b1508b53b7458ec636a4245771da9d8ad01` |

`results.json` deliberately records `executionVerified=false`. Compilation
and file identity alone do not establish required-context execution.

## Player inputs and measured acceptance

The current frozen Windows IL harnesses, host components and fixture/map
files were synchronized to a new Mac input directory. The transfer
contained 27 DLL/manifest files and a source/input identity receipt; all
destination files matched their SHA-256 values. Transfer archive SHA-256:
`17f7c85ed7213e18fc94e55bfbeb5eb3ed6d2c97c67e45ecd6b58be2df604a96`.
This is input identity, not evidence of mobile execution or post-install
IL production. Operator tools and SDK assemblies are not player inputs.

iOS disables dynamic JIT. With `InterpMode=0` and the global collectible
diagnostic off, ordinary trusted host IL cannot rely on interpreter
fallback. The new player includes Runtime, Packages, harnesses and
bridge in the matching trusted R2R composite. UGC and private definitions
loaded in required contexts must still execute through the interpreter.
This differs from the earlier selective Runtime/Packages-IL topology.

The lifecycle suite's intentional default-context dependency seed uses a
locally generated version-A R2R component. The same component loaded privately
obeys required policy; its original IL and generated component identities
are recorded separately. The test remains enabled, with global mode 0.

The independent [build assessment](ios-session-policy-build-assessment.md)
passed against the actual source, native compile owners, configuration,
private CoreLib APIs at three IL stages and matching compiler interfaces.
The regenerated player then passed [functional acceptance](ios-session-policy-acceptance.md)
with native policy version 1, InterpMode=0 and the global collectible diagnostic
disabled:

| Actual simulator Release run | Result |
| --- | --- |
| Current production lifecycle | 24/24 |
| Controlled package player | 15/15 |
| Hello / Arena / Hello sample | All three contexts collected; fresh Hello statics |
| Independent selection fixture | 20 correct sessions and 20 contexts collected |
| Native interpreter entry capture | 11 valid samples covering all nine required method groups |
| Owned simulator cleanup | Shutdown exit 0, independently confirmed Shutdown |

The new controlled fixtures and late-map IL were produced after player
installation and transferred without changing the bundle. The producer's
receipt-formatting step initially failed after both generation commands had
succeeded; the original driver and logs remain preserved, and a read-only
receipt reconstruction records filesystem chronology without claiming an
exact command-start timestamp. Generation was not repeated.

The separate [native method-entry assessment](ios-session-policy-entry.md)
binds installed selection-fixture IL, MethodDef tokens and live interpreter
bytecode pointers. Its 11 samples cover constructors, initializers, delegates
and a private generic helper; they are neither complete call counting nor
entry evidence for the post-install production package definitions. The
capture also records 260 required-policy queries and 20 post-Unload query
guards. Mobile compiler-refusal/recovery, additional native controls, Android
matching builds and physical-device execution remain pending. Windows JIT
positive controls do not apply to this no-JIT simulator. Device signing,
connectivity and execution remain [separate work](ios-device-readiness.md).

## Retained evidence

The completed build, player and entry evidence is retained separately under
`artifacts/ios-session-policy/20261013-evidence-attempt2`. The build archive
includes the original native and host compile databases/caches, actual linker
descriptor, changed source snapshots, all build-assessment receipts and four
raw managed PE evidence files. Player and entry archives retain their own
raw logs, frozen drivers, payload inputs and receipts. Native runtime/DWARF
binaries remain in the isolated remote product; their hashes bind the samples.

| Evidence archive | SHA-256 |
| --- | --- |
| [Build](../artifacts/ios-session-policy/20261013-evidence-attempt2/build.tar.gz) | `f5b4c0e0761375e51be0a3a31ac3595d5cc1f7af0c639bf59640b79fc8475ded` |
| [Player](../artifacts/ios-session-policy/20261013-evidence-attempt2/player.tar.gz) | `1dd822be22e538f8bfcb6fe5378520c0fde43908fe45ad6d82f76924be4755bf` |
| [Entry](../artifacts/ios-session-policy/20261013-evidence-attempt2/entry.tar.gz) | `ca74354dcfdc2894dbdf61ac75bda00b7e0ee0da9128d4bd10c1fa20025c79e4` |

The first archive attempt reused `build-manifest.json` for its member ledger,
creating a duplicate tar member and overwriting that archive-only manifest.
Local verification rejected it. The original archives and
[failure diagnosis](../artifacts/ios-session-policy/20261013-evidence/archive-attempt1-diagnostic.json)
remain preserved; this is our evidence-archiver defect, not a runtime defect.
The corrected [archiver](../eng/ios-session-policy-evidence.py) uses distinct
member-ledger names and verifies uniqueness and every member hash remotely.
Repacking does not rebuild or rerun the player. The independent
[local verifier](../eng/ios-session-policy-evidence-verify.py) checks full
archive hashes, all member identities and the cross-run acceptance counts.
Local verification passed: three archive hashes, 214 member hashes, 72
raw-log/receipt hashes and 27 committed-source hashes match. Native product
identity, installed bundle identity and commit/tree identity agree across
build, player and entry receipts. The
[local verification receipt](../artifacts/ios-session-policy/20261013-evidence-attempt2/local-verification.json)
records shutdown exit 0 and the still-unperformed mobile refusal lane.
