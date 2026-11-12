# Trusted update download flow (desktop reference path)

This is the runnable desktop reference for "download an update, check it, publish it
completely, load it on the next start, and fall back to the previous version when
anything fails". It is stock desktop JIT. It is not R2R evidence, not interpreter
evidence, and not an iOS or device result.

## Run it

    dotnet build eng/trusted-composition-delivery/Host/TrustedComposition.DeliveryHost.csproj -c Release --nologo
    eng/trusted-composition-delivery/Host/bin/Release/net11.0/TrustedComposition.DeliveryHost.exe --distinct-http <fresh-empty-directory>

Use a fresh output directory outside the source tree. The run writes every lane's
request, argv/PID, raw stdout/stderr, exit code, server log and receipts under
`<directory>/lanes/`, and one summary line (`DISTINCT_HTTP_OBSERVED` or
`DISTINCT_HTTP_FAIL <problems>`) to stdout and `driver-result.txt`.

## What the driver does

The driver copies an already built `OrbitGame.Contracts.dll` to a seal directory and
records its hash before compiling anything. It then compiles two genuinely different
modules from source: module A calls `host.Move(3)`, module B calls `host.Move(5)`.
They are separate compilations with different bytes, not a renamed copy. The private
P-256 key lives only in the driver process; children receive the public key file.

Twenty-three lanes share one releases root and one host receipt (the two mvid lanes and the two legacy-receipt lanes use their own small world):

| Lane | What it proves |
| --- | --- |
| `offer-a` | HTTP download of A, signature+hash verification, full staging, publish, activation, business calls (0, 3, 6) |
| `restore-a` | server stopped: the same receipt restarts A without downloading again |
| `bad-b` | tampered body: staging fails with `ContentMismatch`, no final directory, receipt unchanged, A still starts |
| `offer-b` | a new process downloads B and activates it; the shared receipt advances from A to B, A's published bytes are untouched |
| `restore-b` | server stopped: the receipt restarts B (business calls 0, 5, 10) |
| `stall-body` | body stalled after a prefix: the per-download deadline cancels, no final, receipt unchanged |
| `eof-body` | declared length not delivered: transport failure, no final, receipt unchanged |
| `oversize` | document above `TrustedRelease.MaxDocumentBytes`: rejected by staging, no final |
| `incompatible` | signed package for another runtime string: `IncompatibleTarget`, no author activation, last known good (B) starts |
| `contract-bad` | signed package whose compat sidecar names a different Contract MVID: rejected before the activation gate, last known good (B) starts |
| `incompatible-arch` | signed architecture differs from the host: the sidecar target check rejects it before the gate |
| `sidecar-missing` | required mode, package without the sidecar: rejected before the gate, last known good starts |
| `sidecar-unlisted` | a valid-looking sidecar that is not in the signed file set is ignored, so the package is rejected as missing |
| `sidecar-tampered` | sidecar bytes changed after publish: verification fails before any author call |
| `throw` | activator throws: `ActivationFailed`, receipt unchanged, a second start in the same process is `ProcessSelectionLocked` (no in-process fallback) |
| `crash` | the child is killed while the activator is running: the receipt is never written |
| `restore-after-crash` | after that kill, a new process restores the previous verified version (B, business calls 0, 5, 10) |
| `sidecar-mvid-heap-order` | sidecar MVID written as the raw metadata-heap hex is a valid Guid but a different value: rejected with `contract-mvid` |
| `sidecar-mvid-n-format` | the same Contract MVID in canonical `N` form is accepted and version I activates; this also advances the shared receipt, so two lanes change it, not one |
| `lkg-seed-legacy` | legacy mode (requirement off) activates a signed package that has no sidecar and persists its receipt |
| `lkg-required-restore` | required mode restores that receipt: the candidate is rejected before the gate, nothing activates; unchanged-ness is the child's own byte comparison plus the actual receipt file in `world-lkg`, not the shared main receipt file |
| `check-throw-offer` | the host check throws for the offered version: treated like a rejected candidate (InvalidCandidate/compat), the valid last known good B activates, no author code for the offered version, no exception text in the output |
| `check-throw-lkg` | the host check throws for the receipt candidate: LastKnownGoodUnusable, nothing activates, receipt unchanged; a second selection in the same process then activates B, so the gate was not occupied |

## Recovery success point

`TrustedReleaseRecovery.TryStart` writes the host receipt (relative content root plus
the original signed document) only after the activator returns success. There is no
separate pending-candidate file:

- killed between activation and receipt write: the old receipt survives, and the next
  process restores the previous verified version (the `crash` lane measures this);
- activator throws: the process stays occupied, the receipt is unchanged, and only a
  new process can start another version;
- the receipt is host state outside the releases root. The package never supplies it.

## Contract compatibility sidecar

The envelope schema is unchanged. A package may include one extra file,
`runeclr.compat.json`, inside the signed file set, so its bytes are covered by the
release signature:

    {
      "schema": "runeclr.compat.v1",
      "runtime": "net11.0",
      "architecture": "x64",
      "contract": {
        "name": "TrustedComposition.Contract",
        "version": "1.0.0.0",
        "mvid": "<MVID of the Contract the update was compiled against>"
      }
    }

The host reads the sidecar from the verified content root, reads its own deployment
Contract assembly identity from PE metadata (no load, no author code), and compares
name, version and MVID before `TryStartHostLoaded` runs. A mismatch drops the offer:
the process gate is not occupied and the last known good starts. The driver's
`contract-bad` lane signs a package whose sidecar deliberately names a different MVID;
that package is authentic but incompatible, and it is still rejected before any author
activation.

Two modes exist. Legacy callers leave the requirement off: a package without the
sidecar only gets the host's own preload identity check, and the host reports
"sidecar-absent/unchecked" rather than claiming cross-package compatibility.
In required mode a missing sidecar, a sidecar that is on disk but not in the signed file
set, tampered bytes, an unsupported schema, missing or null fields, or a name/version/MVID
mismatch all reject the candidate before `TryStartHostLoaded` (no process gate, no author
activation); an offered failure still falls back to the last known good, and a rejected
last known good leaves the process without an activated version.

Who turns it on: the desktop CLI can enable required mode with the environment variable
`RUNECLR_COMPAT_REQUIRED=1`; `--distinct-http` does not depend on that variable and instead
passes an explicit required check callback to `TrustedReleaseRecovery.TryStart` for both the
offered and the receipt candidate. The portable iPad bridge is planned to hardcode
required:true in its own check callback; device integration for it has not been accepted
yet, so no shipped device path relies on either the variable or this desktop flow.

A host check is ordinary host code. If it throws a normal exception (for example
`InvalidOperationException` or `IOException`), the candidate is treated exactly like a rejected one:
an offered candidate still falls back to the last known good, a restored candidate reports
`LastKnownGoodUnusable`, the process gate stays free, the activator is not called, and the
exception object is not retained or turned into author-visible text. Process-fatal exceptions are
not caught. The two `check-throw-*` lanes cover both paths against real signed packages and a real
receipt.

Coverage is not uniform, and the lane table is not the whole contract:
- Process lanes: the twenty-one rows above. Each one spawns real server/client processes; each rejection row asserts that nothing activated and the receipt did not change.
- In-process delivery-host self-test (run by `--self-test`): author failure and receipt preservation, duplicate simple name, invalid assembly identity, unlisted helper and unlisted TPA dependency, tampered final private, and path-alias containment. These are assembly/identity and activation rules; none of them drives the compatibility sidecar.
- Source-review only, with no fixture and no lane: malformed or unsupported sidecar schema, missing or null sidecar fields, non-Guid or out-of-range MVID text, wrong contract name or version, a second sidecar file in the signed set, a sidecar outside the content root, and the `contract-in-payload` rule that refuses a second Contract assembly. These branches exist in `ContractCompatibility` and `DeliverySession.TryInventory` but are not independently exercised here.
- Documented only: culture, public-key-token, component-hash and host-digest fields are not implemented, so they are neither accepted nor rejected; this host understands a sidecar with the four fields shown above.

Only the four fields shown are implemented: schema, runtime, architecture and
contract{name, version, mvid}. The device lane will later add the values measured on the
new dev host (culture, public key token, component hash, bound host digest) once that
host exists; they are not parsed or compared today, and must come from the installed
host, never from a package or an old probe.

## MVID text form

`contract.mvid` is a standard Guid in canonical `D` (8-4-4-4-12) or canonical `N` (32 hex) text; the host compares parsed Guid values, never raw strings. The 16 bytes in a metadata heap are little-endian for the first three fields, so a generator must decode them (for example `uuid.UUID(bytes_le=raw)`) before writing the text. Taking the raw heap hex directly yields a different Guid and is rejected with `contract-mvid`; the two mvid lanes cover both forms. The reader here uses `PEReader` and `MetadataReader.GetGuid(module.Mvid)` and formats that value as `D`, so its output is already canonical.

## Limits

- `--distinct-http` is opt-in: it is not part of `eng/verify.ps1` or CI, and it is not a
  public SDK. Only the delivery host self-test/integration run inside the repo gate.
- Loopback HTTP only. TLS, redirects, proxies and the public network are not accepted
  by this result; the adapter refuses redirects.
- Not anti-rollback, not a race-proof snapshot, not a sandbox. The publish commit is the
  existing single `Directory.Move`; a crash after that move leaves the published
  directory in place.
- A package that verifies and stages but is rejected later by target or contract checks
  keeps its staged final directory in the releases root. It is never activated and the
  receipt is never advanced.
- One business version per process. The host does not unload the context and does not
  switch versions in-process.
- Desktop stock JIT only: this says nothing about iOS, R2R native execution, or the
  interpreter.

## Runtime source base and the two local iOS patch lines

Branch and pin (use the branch ref, not a bare commit abbreviation):

- fork branch: https://github.com/ReneeGA2020/runtime/tree/runeclr/dev
- full commit pin measured for this host: 474eb8ad7230122cc0d34318b25d673da63fd138
- upstream base: 275f (the fork branch tracks it; no retarget onto a newer upstream main)

Two LOCAL, build-only edits were applied on top of that pin for the device build. They are not committed to the
remote branch and exist only for the measurement pin:

| file | change | scope |
|---|---|---|
| runtime `Directory.Build.props` | `iOSVersionMin` 13.0 -> 15.3 | iOS targets only |
| runtime `eng/native/build-commons.sh` | iOS device branch `CMAKE_OSX_DEPLOYMENT_TARGET` 13.0 -> 15.3 | iOS device branch only; the 15.3 value is not propagated globally to macOS/cross components |

Historical source of record for the measured host: patch 1480a1a4... (recorded then, not regenerated here and not
claimed byte-identical). Rebuilding from this repository alone does not reproduce the device binary; apply the two
edits above to the pinned commit, or use a tree that already carries them. No private worktree path is required.

## Step 2 device status (measured, scoped)

Superseded: the earlier HTTP-app-networking-restricted / pending wording is history, kept in the errata trail only.
Physical iPad Step 2 has since been measured and independently reviewed:

- Native full-evidence audit: scoped GO, 77 checks / 0 failures (REVIEW-STEP2-FULL.md, gate-step2-full.log).
- HTTP / host-key / Contract audit: 136/136 PASS (REVIEW-STEP2-HTTP-FINAL2.md, audit-output.log, assertions.json).
- Fresh acceptance: A-http-31 (PID 1633, PC 0x130ecc050, UUID <uuid-A>) business 216/100/307;
  B-http-32 (PID 1635, PC 0x12e5c8050, UUID <uuid-B>) business 216/200/607; each 7 HTTP 200 responses, correct mode,
  same-PID fresh result, native and tool exit 0.
- Negatives (tamper 33, bad compatibility 34, signature mismatch 35, activation throw 36) each rejected while keeping the
  B-http-32 receipt bytes untouched; offline recoveries 37-40 then restored B with 216/200/607.
- Host public key pin 936c... extracted from the signed Host.dll and ECDSA-verified; Contract canonical MVID f36e... parsed
  from the raw component. Signed source app bytes match the recorded digest/build/install chain; this is not a device
  binary readback.

Scope: trusted-developer downloaded R2R with restart recovery. It does NOT claim App Store distribution, production
TLS/CDN, assembly unload, same-process version swap, or any sandbox property.
Archive accounting: the payload inventory lists 175 entries; the mirrored tar holds 227 regular members (175 listed +
49 AppleDouble ._* + 3 metadata) and the expanded tree has 228 files including INVENTORY-ASSERT.json. AppleDouble
entries are ignored. The raw receipt digest 71d736f4 uses an undocumented scheme and is not used; the supported
independently reproducible digest is the 207-file signed app digest bba62ae4...

