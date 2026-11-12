
# Session-origin integration branch (2026-11-12)

Status: review-ready integration branch, not merged into `main` or `runeclr/dev`.

| repository | branch | base |
| --- | --- | --- |
| `ReneeGA2020/RuneCLR` | `feature/session-origin-integration-20261112` | `origin/main` `cbac2a657793dca7f22b1e1feff4aab26b898b4e` |
| `ReneeGA2020/runtime` | `runeclr/session-origin-integration-20261112` | `fork/runeclr/dev` `474eb8ad7230122cc0d34318b25d673da63fd138` |

The archived experiment (`experiment/session-origin-20261112`,
`runeclr/session-origin-20261112`) is the source reference only; this branch is
rebuilt on the current integration bases and does not copy the old files over
the newer upstream state.

## Opt-in contract

- Runtime: capability bit 0 (`SessionOriginCapability`) is reported only when the
  process is started with `RuneCLR.EnableReflectionPolicyOriginScan=true` in its
  runtime configuration. An absent switch means **disabled**.
- When enabled, `RuneCLRReflectionPolicy_GetStackLoadContext` returns the
  managed `AssemblyLoadContext` of a bounded 16-frame stack walk; saturation or a
  walk error returns no context and the caller fails closed.
- Host: `PrototypeRequireOriginScan` on `MapRunOptions` and
  `HostContractSessionOptions` binds the capability before author loading and
  throws `PlatformNotSupportedException` when bit 0 is absent, so no author
  assembly loads. The option asserts the capability; it does not enable scanning
  by itself, and it requires `RequireInterpreter` plus an API policy.
- Consequence: a host that does not opt in keeps the pre-existing
  reflection-policy behavior - no stack scanning and no capability bit. A host
  that wants origin scanning must set both the process startup switch and the
  host option.

## Tests

`eng/verify-runtime-session-origin.py --expect-fixed` drives the matrix against a
matching private runtime layout: fixed, frame, retirement, conflict, overflow,
disposal, default-off, capability-on, capability-off, map-gate-on/off,
host-gate-on/off, toggle-on/off and invalid option combinations. The `default-off`
mode starts without the switch and requires capability bit 0 to be absent.

Measured results for this branch are recorded in the integration artifact
(`session-origin-integration-20261112/`), together with the fresh source,
runtime, toolchain and binary identities and the before/after pins.

## Source provenance

Three distinct relations, not one:

- Tested working tree vs test manifest: runtime 5/5 raw sha256 equal (the matrix ran on those bytes).
- Tested bytes vs the published runtime commit: 5/5 equal after CRLF to LF normalization; Git stores
  text normalized (`text=auto`).
- Integration vs the archived experiment commit: 3/5 byte-identical (`assemblynative.cpp`,
  `assemblynative.hpp`, `ILLink.Descriptors.Shared.xml`); `qcallentrypoints.cpp` differs because the
  registration is re-applied onto the newer dev upstream; `RuneCLRReflectionPolicy.cs` differs by the
  deliberate default-off change. The archived experiment is not overwritten.
- Host: 12 of 16 archived source/test files are byte-identical. Four changed intentionally:
  `PrototypeReflectionPolicy.cs` (fail-closed message), `eng/verify-runtime-session-origin.py`
  (default-off mode and startup switch wiring), and the two session-origin fixture project files,
  whose line endings were normalized to LF for the integration (integration-only change; the
  archived snapshot bytes stay on the archive branch).

Upstream focused tests (dotnet/runtime, matching Checked runtime, default origin-scan off):
ContextualReflection, CollectibleAssemblies/Statics and CollectibleAssemblies/GenericVirtualMethod
pass (expected 100, actual 100). A switch-on ContextualReflection run also succeeds; because those
upstream tests do not attach a RuneCLR session, that run shows only switch parsing, not enforcement.
Enforcement evidence remains the committed host matrix below. The full run identity and logs are in
the focused-upstream report recorded with the session-origin integration evidence.

The RuneCLR lifecycle harness also passes **156/156** on the matching private Checked runtime
in each of two separate processes: ordinary runtime selection and explicit `--require-interpreter`.
Both runs use the existing Release host harness from host source `46c80a1b`; the runtime source
stays clean at `2077f147` and all five private runtime binary hashes match the committed-source
receipt. These lifecycle runs are separate from the stock-SDK regression and the origin-scan
enforcement matrix. Their evidence is recorded under `lead-patched-lifecycle/` in the integration
artifact (default/required logs, launch receipts and binary identities).

## Measured on 2026-11-12

Toolchain and binary identities:
- Runtime build: `build.cmd -subset clr -configuration Checked -arch x64` on `474eb8ad` plus the five
  source files; SDK 12.0.100-alpha.1.26480.102, CMake 4.2.1, MSVC 19.44.35229.0; build exit 0.
- Private binaries: coreclr `42933493...`, clrjit `dd432f9e...`, clrinterpreter `83b2f6bb...`,
  corerun `cda4877d...`, CoreLib `57808983...`.
- Host toolchain: `dotnet` 11.0.100 (ambient SDK; no global.json). Rebuilt host outputs embed the
  source revision; earlier outputs are history.
- Private layout reuses the dev Release managed framework (same source pin); the matrix verifies
  the native outputs and CoreLib against the fresh build hashes.

### Runs (keyed by provenance, host commit and consumed source sha)

| provenance | host commit | consumed source | modes | pins | drift | output |
| --- | --- | --- | --- | --- | --- | --- |
| source-manifest (dirty build) | cbac2a6 + dirty | manifest `49609720...` | 16 | 696 | 0 | repro-matrix/ |
| committed-integration | 24e5a8fa | receipt `c911c665...` | 16 | 695 | 0 | repro-matrix-committed/ |
| committed-integration | 49fc6df1 | receipt `c911c665...` | 16 | 696 | 0 | repro-matrix-committed2/ |
| committed-integration | 46c80a1b | receipt `c911c665...` | 16 | 696 | 0 | repro-matrix-final/ |

The pin count is not the acceptance key: 695 vs 696 reflects whether the consumed receipt was
included in the frozen inputs. The final row is the current result; earlier rows are kept as history.

Receipt consistency versus build-log provenance: the receipt is a self-declared tooling input.
This branch freezes its bytes (single read, before/after pin, in-output copy) and verifies the
declared relations to the current commit and to the fresh binaries, but it cannot re-prove from the
receipt alone that a specific build produced those binaries. That part rests on the recorded build
log, the build-source head and the binary hashes. The mixed basis is deliberate: four runtime files
were built from their raw (CRLF) bytes and RuneCLRReflectionPolicy.cs from its canonical (LF) form;
the verifier records each as raw or normalized-canonical.

## Committed-source verification

The verifier accepts the committed integration snapshot without moving HEAD:

- `--runtime-committed-source <receipt>` requires a clean runtime worktree at the receipt
  commit, that commit's exact parent, and a modification-only delta equal to the receipt's five files.
- The receipt records the build source (parent commit plus raw file hashes that were built), the
  integration commit (canonical Git blob hashes) and the private runtime binary hashes.
- Per file the working bytes must equal the recorded build source (raw) or, when the build read the
  canonical form while the checkout materialises CRLF, normalise to the committed blob
  (normalized-canonical). Any other difference is rejected.
- Fresh build outputs and CoreLib must match the receipt binaries.
- The existing source-manifest (dirty build) and clean-commit modes are unchanged.

Tooling tests: `eng/test-session-origin-provenance.py` (24 cases) builds synthetic repositories and
covers both provenance modes: a positive with four raw and one normalized-canonical file, and
rejections for wrong build source, wrong parent, inconsistent parent, unexpected dirty tree, binary
mismatch, receipt drift and receipt copy mismatch. The historical real-tree native negative remains
in the artifact evidence.

Receipt integrity: the verifier reads the receipt bytes once, parses those bytes and pins the same
file before and after the run. The summary records the consumed sha256, byte count and the in-output
copy (`consumed-source-receipt.json`). A receipt that changes between load and pin is rejected, and a
change during the run (or a runtime commit/parent/worktree change) fails the run; the dirty
source-manifest mode gets the same consumed-bytes identity and post-run re-check without relaxing
its existing checks.

## Limits

Native walker status 1 (saturation) and status 2 (walker error) have only
indirect coverage; the compiled-only suppressed child has no author frame;
unmanaged entry, AOT/mobile, global all-load and the published walk-cost bound
remain out of scope. No sandbox, native/R2R body, device or unload claim is made
by this branch.

Review-tool note: the verifier's `RUNTIME_BASE` (7cbdad39) is a historical ancestor check for
provenance, not the PR base. PR base resolution is a separate explicit merge-base and diff check
against the target branch (`origin/main` for the host, fork `runeclr/dev` for the runtime), because the
verifier has no `--base` option. The two checks answer different questions.
