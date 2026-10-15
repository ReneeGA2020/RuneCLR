# Matching Windows execution-selection build and lifecycle acceptance

Measured on 2026-10-13. The private diagnostic candidate now passes mode-0
required interpretation, real compiler-skip rejection/recovery, native-caller
inline controls, the complete RuneCLR lifecycle/player suites and four unchanged
official loader tests. This advances the
[execution strategy](execution-strategy.md); production context registration
and mobile acceptance remain separate work.

## Source and matching build

Official base: `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`, product .NET 12.
Candidate: `6bb5f60be8de39b22fb19b95aea03e3252756cb3`, private branch
`runeclr/execution-selection` in the separate `E:/runtime-selection-20261013`
worktree. The original `E:/runtime` baseline remains tracked-clean.
The [candidate source description](runtime-execution-selection-candidate.md) and
[portable patch](../eng/runtime-patches/0003-collectible-interpreter-selection.patch)
record the scope, ABI-wrapper distinction, new compiler GUID and source checks.
No upstream report or push was made.

The runtime worktree uses SDK `11.0.100-rc.1.26420.103`. From its root:

```powershell
./build.cmd -subset clr.runtime+clr.jit+clr.hosts+clr.corelib+clr.tools+clr.nativecorelib -configuration Checked -arch x64 -clrinterpreter
```

The build completed with **0 warnings and 0 errors**. Actual VM/interpreter
compilation units, the Checked CMake cache and the candidate source stamp are
bound in `compile-evidence.json`. Dynamic native JIT remains enabled.

Evidence root: `artifacts/execution-selection/runtime-build-20261013`.
Its `layout` copies same-base Release framework libraries and
dotnet/hostfxr/hostpolicy from the private baseline, then replaces CoreCLR,
interpreter, native JIT, CoreLib and debugging binaries with fresh matching
Checked outputs. CoreLib was rebuilt and crossgenned with the matching new
compiler interface. This is a private test layout, not a complete shipping pack.
`layout-receipt.json` records every framework hash and the consumed CoreLib IL,
crossgen2, native compiler interface and optimization inputs.

| Consumed file | SHA-256 |
| --- | --- |
| coreclr.dll | `0e32cb575c97eb83d98e2fefa1cef41b866bc4f546675113e91862edd6ca4309` |
| clrinterpreter.dll | `f7bca2862dba3e3fbfefac5b6f19a0127f97b175e06c29014328c1d29ea78b4a` |
| clrjit.dll | `9114dda1e87252ddbe4384a9cd8719683abf4c475131c9082c824f1ec6aff11d` |
| System.Private.CoreLib.dll | `a9a4a1d3ef12b0d40872721796d5ad78099432feb59c77da7831e9ffcdb31b60` |

The initial parameter-parser failure and the first native candidate C2027
failure remain in `attempt1` and `attempt2`. The corrected constructor is
out of line where MethodDesc is complete. These were local build/implementation
errors; neither is an upstream runtime defect.

## Executed checkpoints

The [selection matrix](runtime-execution-selection-validation.md) passes five
lanes: two required/recovery runs each prepare 26 body groups in 20 collectible
contexts; switch-off actually compiles UGC natively; actual CORJIT_SKIPPED
throws NotSupportedException for the required body, collects it and recovers
through 20 normal contexts; the unmarked same DLL falls back natively and returns
73; boxed interface/delegate calls cover five body groups and 20 retirements.
Its separate native generic caller comparison has 20 actual inline successes
with the switch off versus 20 exact inline rejections and 20 bytecode bodies
with it on. The trusted definition remains native despite its collectible
concrete type argument.

The [four official loader runners](required-interpreter-upstream.md) were
freshly rebuilt and executed against this layout. Actual generated guards,
original assertions, precise collectible-body checkpoints, native trusted
callers and unchanged inputs passed. This is a focused standalone lane, not the
complete upstream test suite.

The [lifecycle verifier](../eng/verify-interpreter.ps1) now accepts an explicitly
identified candidate without changing its default mode-1 baseline route:

```powershell
$env:PATH = "E:/RuneCLR/artifacts/toolchains/dotnet-11-rc1;" + $env:PATH
./eng/verify-interpreter.ps1 -RuntimeRepo E:/runtime-selection-20261013 -RuntimeLayout E:/RuneCLR/artifacts/execution-selection/runtime-build-20261013/layout -Mode 0 -RequiredCandidateCommit 6bb5f60be8de39b22fb19b95aea03e3252756cb3
```

The fresh run at `artifacts/execution-selection/lifecycle-required-20261013-attempt2`
passes **22/22 lifecycle cases**, **15/15 player package cases**, the three-map
sample, late-built IL and source/import/source with fresh statics and three
collected contexts. R2R/tiering are enabled, global no-inline is disabled,
successful callback/private/generic bytecode dumps are present and trusted
MapRunner has positive native JIT evidence. Host files remain unchanged while
the late map and operator packages are built.

The existing collision test deliberately loads and seeds the same private
dependency in the non-collectible default ALC. Its explicit ownership/MVID/token
marker and exactly one native Start(int) seed are required; collectible copies
retain independent state and successful bytecode. JIT summaries are separated
into per-process `.jit` files, avoiding background tiered JIT text interleaving
with interpreter dumps. The earlier failed assessment is retained in attempt1.
Names and counters alone do not give per-MethodDesc native-entry attribution.

Root independently checked raw functional markers, bytecode group counts,
compiler-skip outcomes, inline decisions, generated runners and input/archive
hashes. `artifacts/execution-selection/root-assessment-20261013.json` records
those checks separately from the subagent receipts.

The build-receipt archive is
`artifacts/execution-selection/matching-required-build-evidence-20261013.tar.gz`,
SHA-256 `664801c745dbf8944d6a79ff740d17f7c8548e4a6be241e854a86712aabb2492`.
The lifecycle archive includes both attempts and the root assessment:
`artifacts/execution-selection/required-lifecycle-evidence-20261013.tar.gz`,
SHA-256 `bd2418172813db5a88d07b8af21699f08178fcea11d1ad23f4a405a596bef3b6`.
Selection/inline and official-test archives are indexed by their respective
acceptance documents. Experimental installed-runtime replacement was not used.

## Remaining gates

This diagnostic selects every collectible metadata IL definition at startup;
it is not yet an immutable policy registered per UGC session. Ordinary trusted
collectible plugins are also selected. Dynamic methods without such a definition
and new unmarked loading routes remain outside the scope.

No Windows native interpreter-entry capture, no-feature startup execution,
concurrent preparation/multicore winner control or submitted R2R body rejection
was measured here. The pinned base already excludes ordinary collectible R2R
and tiering, so enabling those switches is not independent proof of the new
guards. No terminal CPU budget or sandbox is claimed.

The next increment is creation-time session policy plus acknowledgement and
downgrade checks, followed by matching mobile builds. The iOS CID fix is a
separate candidate; combining it with the changed compiler interface requires
a full matching rebuild. Existing simulator results do not establish this new
selection policy on iOS or Android. Physical iOS acceptance remains outstanding.
