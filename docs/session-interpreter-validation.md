# Session policy acceptance fixture

Validated on 2026-10-13 on Windows x64 Checked, private candidate
`5972a86966e56ae5f468a3e042327f0051e923d5`, branch
`runeclr/session-policy`, upstream base
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. Both session drivers passed
against fresh matching native/CoreLib outputs with the global collectible
diagnostic switch off. The earlier
[diagnostic collectible selection](runtime-execution-selection-validation.md)
results do not establish this new per-context factory behavior.

The [session driver](../eng/verify-session-interpreter.ps1) checks a committed
tracked-clean candidate, pinned ancestry, matching native/interpreter/JIT/
CoreLib hashes and source-stamped CoreCLR before any execution. All lanes
set `RuneCLRInterpretCollectible=0`; the ordinary/marked comparisons use
`InterpMode=0`, with existing R2R/tiering enabled. Unsupported/missing API
acknowledgement rejects fixture startup. No production host or installed
runtime is modified.

## Creation and ownership checks

The trusted [fixture factory](../eng/execution-selection-probe/Host/SessionContextFactory.cs)
uses the matching private CoreLib API through reflection, so the SDK reference
packs remain unchanged:

- `RuneCLR_GetExecutionPolicyVersion()` must return 1.
- `RuneCLR_CreateInterpreterRequired(name, managedResolver)` creates the marked
  collectible context before loading any payload bytes.
- Instance `RuneCLR_GetExecutionPolicy()` must return 1 for that marked context,
  0 for an ordinary collectible context and 0 for the default context.

The factory receives a `Func<AssemblyLoadContext, AssemblyName, Assembly?>`
resolver at creation time. It serves as the Load override, not a later
`Resolving` event. The callback loads private dependencies back into the
calling owner context and shares only the default-context contract. Before/
after explicit loads, private resolution and execution, native query results
must retain the creation-time value. The private helper is absent after entry
construction and loaded during the first actual `Run` body. This late-body-load
boundary is asserted, and the helper's resulting bytecode/body values must
inherit the marked context's policy.

`policy-api.json` records actual version and the three exact bridge method
signatures separately from two known private, static, read-only native imports
(`RuneCLR_GetExecutionPolicyNative` and `RuneCLR_GetExecutionPolicyVersionNative`).
All five actual declarations are inspected; the read-only imports are not
misclassified as extra bridge APIs. No setter is exposed by that named surface.
This is an API immutability check, not protection against arbitrary hostile
reflection, native code or creating another unmarked ALC. Runtime-owned
creation-time policy and absence of a native downgrade path require source
review independently of this fixture.

After `Unload()`, the fixed query must throw `InvalidOperationException` through
its `VerifyIsAlive` guard rather than read a retired native binder. Normal and
boxed/inline lanes require 20 precise retirement-query markers each; the
refusal/recovery lane requires 21 (one refused context plus 20 normal ones).
Only the copied exception type/marker escapes the check, not the exception.

Environment `RUNECLR_PROBE_FACTORY=required|ordinary` selects the trusted
experimental host branch; it is not the runtime enforcement mechanism. With
that variable absent, the host preserves its original collectible diagnostic
path and previous driver modes. Results retain only host-owned values, weak
references and copied metadata IDs; reflection/delegates and exceptions remain
inside `NoInlining` frames.

## Measured lanes

| Lane | Actual result |
| --- | --- |
| Marked factory, mode 0, diagnostic off | PASS: 20 correct sessions/collected contexts; 260 native-query markers all value 1; 26 bytecode method groups × 20; host native JIT positive; no reported UGC-owner native JIT |
| Ordinary collectible, same IL, mode 0, diagnostic off | PASS: 20 sessions/collection; 260 query markers all value 0; same values/static resets/inventory; UGC native JIT positive, zero UGC bytecode |
| Marked factory refusal/recovery | PASS: one actual scoped `CORJIT_SKIPPED` on `SelectionUGC.Refusal.Entry:Reject`; `NotSupportedException`, refused context collected; next 20 marked contexts pass with 26 × 20 bytecode groups and private-owner policy 1 |
| Unmarked default-context fallback, mode 1, diagnostic off | PASS: same refusal DLL and one actual scoped `CORJIT_SKIPPED`; existing native JIT fallback executes `Reject`, returning 73 |
| Marked boxed bridge | PASS: 20 cold/warm interface plus closed delegate sessions/collection; five underlying IL groups × 20 bytecode dumps; 120 query markers value 1; trusted caller native JIT positive |

The separate [session inline driver](../eng/verify-session-interpreter-inline.ps1)
reuses the concrete trusted generic caller fixture in two factory modes. It
passed 20 actual successful native inlines for ordinary contexts, versus
20 exact no-inline decisions/body bytecode dumps for marked contexts. Both
lanes returned the correct values and collected all 20 contexts. The
generic caller's definition module stays trusted although its concrete type
argument is collectible; JIT classification is by definition owner, not
any UGC type name appearing in its signature. Both lanes leave the global
diagnostic switch off. Each had 20 trusted native generic caller compilations,
120 native policy query markers (ordinary 0, required 1), and 20 protected
post-unload query failures. Ordinary had no UGC bytecode; required had no
successful inline or reported UGC-definition-owner native JIT.

## Preparation and commands

The changed trusted host compiles with the private RC1 SDK with zero warnings
and errors; both PowerShell drivers parse successfully. The initial compile-only
preparation logs are retained at:
`artifacts/session-policy/fixture-prepare-20261013-024859-dec1c38c84224d92bf59c72c055b864b`.
No old candidate layout is used to manufacture session-policy evidence.

The first matching-build attempt at commit
`8d809df480f96e8130af15dbcd203dba32043130` was rejected at API acknowledgement,
before payload loading. The private bridge methods were present in compiled
PreTrim CoreLib but absent in the trimmed IL and final R2R CoreLib. Matching
product/layout hashes alone did not establish preservation of the requested
private metadata. The ordinary missing-capability check correctly stopped
startup; this is an experimental trimming/integration issue, not evidence of
an upstream runtime defect or failed script execution. Original streams and
a read-only five-location metadata/hash/MVID comparison are retained at
`artifacts/session-policy/session-20261013-025655-9ebf805175074ea89c9bf53f168fab21`.
No success receipt overwrites that failed attempt. Candidate `5972a869` rooted
the private factory/query surface and nested resolver implementation. An
independent PE metadata review verified all five bridge/import declarations
and nested constructor/Load methods across PreTrim, posttrim, IL, R2R and
deployed CoreLib before the actual factory matrix. The review is retained at
`artifacts/session-policy/corelib-metadata-5972-verified`.

Reproduction using the verified private candidate/layout:

```powershell
./eng/verify-session-interpreter.ps1 `
  -RuntimeLayout E:/RuneCLR/artifacts/session-policy/runtime-build-20261013/layout `
  -BuiltProduct E:/runtime-selection-20261013/artifacts/bin/coreclr/windows.x64.Checked `
  -CandidateCommit 5972a86966e56ae5f468a3e042327f0051e923d5

./eng/verify-session-interpreter-inline.ps1 `
  -RuntimeLayout E:/RuneCLR/artifacts/session-policy/runtime-build-20261013/layout `
  -BuiltProduct E:/runtime-selection-20261013/artifacts/bin/coreclr/windows.x64.Checked `
  -CandidateCommit 5972a86966e56ae5f468a3e042327f0051e923d5
```

Each invocation needs a fresh evidence directory. Native bytecode stdout,
managed markers stderr and native JIT diagnostics are stored separately;
`DOTNET_JitStdOutFile` prevents tiered JIT summary corruption of bytecode lines.
All lanes bind unchanged managed hashes and matching method inventories.
Successful runs:

- Main matrix: `artifacts/session-policy/session-20261013-031436-113be3f7cccd4db49da546977097c7d0`.
- Concrete generic caller: `artifacts/session-policy/inline-20261013-031518-38c8b09aad34486ea18bf98aae3e0699`.

Each contains request/results receipts, pinned sources, exact policy API
signatures, copied MethodDef/MVID inventories, and separate raw native/managed
logs. A read-only second assessment checked source/managed/runtime hashes,
all native policy markers, retirement guards, business/collection counts,
bytecode groups and actual inline decisions without rerunning either app.
The inline assessor initially used case-sensitive uppercase `SUCCESS`; raw
JIT output uses lowercase `success`. Its matching correction and untouched
logs are recorded in `assessment-preflight-note.json`, with no app failure.

| Evidence archive | Bytes | SHA256 |
| --- | ---: | --- |
| Main matrix `.tar.gz` beside the directory above | 2,839,859 | `0327aee83821d2cd8df907d4b19ddf83f7ec9080e6347614382c919fedcbc1ad` |
| Concrete caller `.tar.gz` beside its directory | 629,002 | `694ea0265d53095923ab64453fd1e63560950c07570266867e28ae2ed7edbd43` |

Correct values and successful bytecode compilation are distinct evidence.
These drivers do not capture per-method native interpreter execution
entries, inject submitted R2R bodies, test multicore/concurrent native winners,
or establish mobile capability. Ordinary trusted plugins remain eligible for
JIT in this candidate policy; dynamic methods and author-created unmarked
contexts remain separate limitations. Production profile acceptance is unchanged.
