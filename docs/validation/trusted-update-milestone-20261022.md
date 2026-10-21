# Trusted update integration milestone - 2026-10-22

Status: milestone summary for GitHub publication. The measured Windows stock
gate passed (./eng/verify.ps1, exit 0). Current Windows, Linux and macOS CI
results are linked from [PR #17](https://github.com/ReneeGA2020/RuneCLR/pull/17).
This page records maintained surfaces, bounded offline evidence and the local
Windows stock receipt; the PR checks record validation of later commits.

## Maintained surfaces

- **Typed trusted sessions.** `TrustedModuleSession<TContract>` is a
  host-owned synchronous call owner for an already loaded trusted module. It
  exposes `Closed`, `ReentrantCall` and `CallbackFailed` outcomes without
  retaining the module, callback, exception, reflection metadata or delegate.
- **TrustedGame sample.** A game-owned Contracts assembly is shared by exact
  identity, while the update module is built independently with
  `BuildProjectReferences=false`. The host pins the module SHA-256 and owns the
  game state; local and signed release modes are separate.
- **Signed release path.** ECDSA P-256/SHA-256 signed manifests, a host SPKI,
  staging under a releases root, receipt persistence and next-process recovery
  are implemented through `RuneCLR.TrustedUpdate`.
- **Startup lifetime.** One process selects one business version. A successful
  activation occupies the process gate; a failed activation does not retry or
  fall back in the same process.
- **Offline verification.** Portable Python self-tests cover trusted-game
  observations, IL/R2R builds, composition delivery and generic interactions.
  Retained-run replay remains separate from product execution.

## Tracked commands

These are ordinary stock-SDK or stdlib-Python entry points. They do not require
a private runtime, external signing key or local artifact tree unless noted as
optional.

```sh
dotnet build RuneCLR.slnx -c Release
dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build
dotnet run --project tests/RuneCLR.Packaging.Tests -c Release --no-build
dotnet run --project tests/RuneCLR.TrustedUpdate.Tests -c Release
dotnet run --project tests/RuneCLR.TrustedRelease.Tests -c Release
dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --collect
./eng/trusted-game.ps1
./eng/score-game.ps1
python -B eng/test-trusted-game-observations.py
./eng/verify.ps1
```

`./eng/trusted-game-signed.ps1 -OutputRoot <new-directory>` is an optional
local demonstration of signing, staging and recovery. It creates a local demo
P-256 key/SPKI and uses a new output directory; production hosts must pin their
own key material, and private keys must never be committed.

The private-runtime build/observation drivers and `--run-root` replay commands
are optional archival experiments. They are not prerequisites for the public
stock-SDK commands above.

## Windows stock gate

On 2026-10-22 (UTC 2026-10-21T17:07:54 to 17:14:20), ./eng/verify.ps1 exited
0 after 385.901 seconds on SDK 11.0.100-rc.2.26504.105 with ordinary stock
Windows runtime selection. The gate passed Runtime 146/146, Packaging 307/307,
trusted update 272/272, package execution 15/15 plus pumped 22/22, staging
17/17 and recovery 37/37; six new callback-deadline tests passed. The source
aggregate was stable before/after at
dbd6574a1222e492300c15016554f7d00c3725cb58e44cabcde55cc32618148b.

Archival/local receipt:
E:/RuneCLR-publish-evidence-20261022/verify-run-20261022/
(verify-portable-summary.json; verify-portable-final.log SHA-256
8ae4f252fc595add24999c36e2de987ca41f4650322a8cd934a8ecf14cce233d). The full
log is not committed. This final run includes the portable Python 3 resolver
(`python3`, `python`, then `py -3`); it selected Python 3.12.10 on Windows.

## r9 recorded text correlation

The r9 correction has a bounded GO for the **actual r9 manifest and retained
enabled/off text correlation** under an externally caller-trusted 50-input
manifest:

- 138 synthetic, 79 recorded (71 intended negatives) and 7 manifest tests pass.
- 49 r9 hashes, 48 generated outputs and 50 immutable pins verify; inputs and
  outputs are disjoint and pins-before equals pins-after.
- Enabled run PID 28180: six Host records and one module header with twelve
  phase records; `textRecordCorrelation=true`.
- Off run PID 40020: Host identity, business closure and resident/no-collection
  context validate; `textRecordCorrelation=false` with no fabricated call
  records.
- The original r8 manifest error is preserved: its bad `REPORT.md` pin remains
  in the r8 before/after manifests. r7 is frozen unchanged, its `REPORT.md`
  remains 9701 bytes at SHA-256 `2fedd0eb977778e2ffcf102649da22eb7929844fc7207c44a76b8969af6b9822`,
  and the original entry campaign remains FAILED at `entry-unknown-prefix 1890`
  with `recoverB` absent.
- The general `manifest_tool` API is **not** accepted. Its three residuals are
  unconditional `beforeUnchanged`, a writer trusting a supplied `pathKey`, and
  missing general containment in `verify_relative_manifest`; a documentation
  line reference is also off. The actual r9 manifests are unaffected.

This is offline text-record correlation only. It is not runtime
MethodSpec/dispatch, module runtime join, native/interpreter/R2R body,
PC-image attribution, whole-method, unload, iOS/device or overall acceptance.
The r9 `audit.py`/checks link remains caller-trusted secondary provenance, not a
re-executed audit.

Archival/local evidence:

- Acceptance: `E:/RuneCLR/artifacts/lead-recorded-join-r9-acceptance-20261022/acceptance.json`
- Candidate: `D:/RuneCLR-artifacts/trusted-game-module-host-recording-join-r9-dw517j-20261022`
- Review: `D:/RuneCLR-artifacts/trusted-game-module-host-recording-join-r9-review-bocx5e-20261022/REVIEW-R9.md`
  (SHA-256 `bbc6c060a93088c0ed69e4ff14377c54c7663f2b4cb96a5bf3ff1cc1efa50ae2`)

## Evidence identifier convention

Paths beginning `artifacts/`, `D:/` or `E:/` identify **archival/local
evidence** held outside this repository. They are not GitHub-accessible
downloads and may not be reproducible from this checkout alone. Recorded
hashes and counts remain facts of the cited run; do not infer a public test
step from them.

## Historical separation

- Earlier fnptr diagnostic: PIDs 33988/29052; Lead 137 checks and independent
  333 checks. Its Host-side diagnostics carry `closedMethodKeys` with
  implementation MethodDefs `0x060000A1`/`0x060000A2`/`0x060000A6`.
- Later module-witness stock smoke: PIDs 40020/28180; 370 checks over 80 pins,
  six Host records plus one header/twelve module phases. Static callsite
  metadata is not a runtime module PC or dispatch proof.
- Entry r6 remained FAILED-CLOSED; entry r7 remained FAILED at
  `entry-unknown-prefix 1890` with `recoverB` absent.
- Physical iOS, R2R native delivery, interpreter fallback and a security
  sandbox remain outside this milestone claim.

## CI and remaining gates

The measured Windows stock gate above is a local stock-runtime result. Merging
requires Windows, Linux and macOS CI to pass on the latest PR commit. Following
the local gate, CI exposed Windows short-path alias containment and a macOS
temporary-directory assertion issue; dedicated regressions cover both fixes.
The replay suite now has 11 tests, including Windows alias and handle-lifetime
checks, and the observation suite checks fixtures below a `private` ancestor.
Stock rejection/option tests do not establish private callback timing,
interpreter/native execution or iOS/device behavior.
