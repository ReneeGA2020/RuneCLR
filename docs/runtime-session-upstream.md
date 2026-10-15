# Official loader regression on the session-policy candidate

On 2026-10-13, four unchanged official Windows x64 Checked loader tests passed
on the matching session-policy candidate. Each freshly generated standalone
`Main` executed the original assertions and returned 100. Trusted callers had
positive native JIT diagnostics; selected collectible payloads had successful
bytecode diagnostics and no reported native JIT. This is a focused regression
of the ordinary-binder path and shared execution-selection guards.

These official tests use their existing ordinary collectible contexts.
`RuneCLRInterpretCollectible=1` selects the earlier diagnostic route; they do
**not** call the new native required-context factory. They complement the
[separate session-policy fixture](session-interpreter-validation.md), rather
than establish that factory's behavior. This desktop run is neither a complete
upstream suite nor mobile validation or native interpreter-entry tracing.

## Matching inputs and results

- Official source base: `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`.
- Current candidate: `5972a86966e56ae5f468a3e042327f0051e923d5`,
  `runeclr/session-policy`, tracked-clean before and after execution.
- Private runtime: `artifacts/session-policy/runtime-build-20261013/layout`.
- SDK: `11.0.100-rc.1.26420.103`; product runtime is .NET 12.
- Selection: mode 0, diagnostic 1, R2R enabled, tiering disabled,
  ordinary native inlining enabled and GC stress disabled.
- Four runtime/CoreLib hashes match the committed build product; CoreCLR,
  interpreter and native JIT source stamps identify the candidate. The full
  host/runtime hashes and copied reference-pack identities are in `request.json`.
- Source/project hashes match the independent tracked-clean official checkout.
  Generated guards include the intended body calls without false-only skips.
  All managed input and runtime hashes remained unchanged after the runs.

| Official test | Original result | Positive body evidence |
| --- | --- | --- |
| GenericVirtualMethod | Exit 100 | 10 collectible generic `DerivedMachine.Construct` bytecode bodies |
| CollectibleStatics | Exit 100 | `SetStatic`, `GetStatic`, `SetStaticObject`, `GetStaticObject`, one each |
| ResolvedFromDifferentContext | Exit 100 | All four resolver/Load-override scenarios; two collectible `MainTest` bodies |
| ByRefLocals | Exit 100 | Metadata and dynamically emitted `GetSpan` bytecode bodies; 20 expected loop outputs |

The driver rebuilt the official projects using `BuildAsStandalone=true` and
retained the real generated entrypoints. It did not modify official test
sources, assertion outcomes or generated guards. Dynamic-method evidence here
belongs to the all-collectible diagnostic scope; it does not extend the
registered-module session policy to arbitrary author-emitted dynamic methods.

## Command and evidence

```powershell
./eng/verify-required-upstream.ps1 `
  -RuntimeLayout E:/RuneCLR/artifacts/session-policy/runtime-build-20261013/layout `
  -CandidateCommit 5972a86966e56ae5f468a3e042327f0051e923d5 `
  -EvidenceDirectory E:/RuneCLR/artifacts/session-policy/upstream-20261013-attempt2
```

[The driver](../eng/verify-required-upstream.ps1) completed successfully on the
fresh matching current layout:

```text
PASS 4/4 official Windows Checked loader tests under mode0 + RuneCLRInterpretCollectible=1.
```

`artifacts/session-policy/upstream-20261013-attempt2` contains build receipts,
raw stdout/stderr, generated guards, copied original sources, managed hashes
and `results.json` with `success=true`. `focused-evidence-hashes.json` records
180 raw-file hashes, independently verified against the archive. The focused
archive includes all top-level receipts/logs/driver, original sources,
generated entrypoints and standalone output files; copied reference packs
and intermediate build directories are omitted, with their input identities
retained in the request.

Archive: `artifacts/session-policy/upstream-20261013-attempt2.focused.tar.gz`,
181 files, 3,111,731 bytes. SHA-256:
`7b5121e0b29cee8d79ce1533ed64fe9b6b362ff47a1961e2822da98a64243989`.
Its adjacent receipt binds the archive to the candidate and records the scope.
The earlier `8d809df480f96e8130af15dbcd203dba32043130` candidate also passed
these four tests. Its `upstream-20261013-attempt1` evidence and focused archive
remain unchanged (SHA-256
`70b27ef7f5acf3e2c516b24396bdfe4dd7d856cc87266be3f074b1bf50719c95`).
That build omitted the reflection-only factory after trimming, so its official
diagnostic-route result does not establish factory availability. The current
rerun follows the exact-method root correction, a fresh matching build and
[five-stage CoreLib metadata checks](runtime-session-policy-candidate.md).
Neither version of these official diagnostic tests substitutes for the
independent diagnostic-off session-factory acceptance.
