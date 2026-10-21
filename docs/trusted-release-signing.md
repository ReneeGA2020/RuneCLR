# Trusted release signing

This is an opt-in offline check for a developer-owned trusted update package.
It does not change TrustedUpdateApproval, and it is not a UGC sandbox, a
download service, an anti-rollback counter, or iOS signing admission.

## Run

From the repository root:

    dotnet run --project tests/RuneCLR.TrustedRelease.Tests -c Release

The project is an executable harness included in RuneCLR.slnx, eng/verify.ps1,
and the three-platform CI workflow.

## What is signed

ECDSA P-256 and SHA-256. The caller supplies the private key only for Sign.
The host supplies a fixed SubjectPublicKeyInfo (91-byte P-256 SPKI) to Verify.
The manifest does not carry a public key.

The signed payload is one canonical JSON line. It binds formatVersion, version,
runtime, architecture, entry type, entry method, entry relative path, and every
listed file path and SHA-256. Native owner, private, and helper files are
ordinary listed files. Signing only the entry DLL is not enough.

Wire format, UTF-8, three LF-separated lines and no CR:

    RTRSIG1
    <standard base64 of the 64-byte P1363 signature>
    <canonical JSON payload>

After the host key accepts that payload, Verify returns a TrustedUpdateCandidate
and TrustedUpdateApproval. The candidate's entry hash is the entry file. Every
other listed file is AdditionalContent. The existing TryPlanCandidate and
TryStartHostLoaded methods then hash those paths again. Verification failure
returns no candidate and no approval, loads nothing, and writes no last-known-good
record.

## Limits

- Pass the returned candidate and approval together. Rebuilding the candidate,
  or dropping AdditionalContent with a record with-expression, is not a verified
  package. The selector's approval record still matches only version and entry
  hash.
- Unlisted files in the directory are not authenticated and must not be loaded.
- No expiry, key rotation, certificate chain, revocation, or version monotonicity.
- No download staging or same-process native unload.
- Paths are relative, slash-separated, and case-sensitive in the manifest.
  Empty, duplicate, case-conflicting, absolute, and .. segments are rejected.
  Reparse points are rejected on the content root and on every directory walked down to the file, not only on the leaf. A junction or symlink used as the root or as a parent directory cannot admit an outside payload. The harness creates a Windows junction or, on other systems, a directory symlink, and skips only when that creation is unsupported or denied. A file can still change after Verify and before
  Plan; Plan hashes it again.
- Private keys are not stored by this helper. Do not write them into the
  repository or logs.


## Host startup

The sample host can verify a signed release with its own SPKI file. That file is
host trust configuration. The public key is not read from the release package.
The host reads the signed document and SPKI with one capped stream. One byte past the limit is rejected without allocating the rest of the file.

    dotnet run --project samples/RuneCLR.TrustedUpdateHost -c Release -- --signed-start <content-root> <signed-release-file> <host-spki-file> <last-known-good-file>
    dotnet run --project samples/RuneCLR.TrustedUpdateHost -c Release -- --signed-self-test

--signed-start passes the TrustedRelease.Verify candidate and approval through
unchanged. The selector still hashes the files and checks the target. Verification
failure does not load the payload and does not change the last-known-good file.
A later process can start the same correctly signed package after a failed
activation. This sample is desktop IL only. It is not ReadyToRun native execution
and it is not iOS evidence.

The self-test builds one standalone IL assembly. Its Activate method computes
41 * 3 + 7 and writes that result to a marker file. The private and helper files
are signed and hash-checked, but the IL does not reference them. That is file
verification, not evidence that a private dependency executed. The host loads
only the verified entry assembly. It does not scan the payload directory or
load unlisted files.

On 2026-10-17 the lead independently ran both `--signed-self-test` and the
existing `--self-test` on Windows in Release; both exited 0. The signed harness
reported `SIGNED-SELF-TEST passed`, including oversized document and SPKI
rejection, wrong key, private-file and metadata tampering, throwing activation
with unchanged last-known-good, and recovery in a fresh process. Metadata and
key reads use one stream and read at most the configured limit plus one byte.
These sample checks are included in `eng/verify.ps1` and three-platform CI; this
receipt records Windows desktop IL execution only.

The macOS arm64 follow-up used SDK 11.0.100-preview.6.26359.118 in an isolated
source snapshot. The worker's run and the lead's independent rerun both exited
0 with `TRUSTED_RELEASE_TESTS passed`. All seven source hashes match the accepted
Windows snapshot. Parent-directory and root-directory symlinks were actually
created and rejected as `InvalidPath reparse`; these cases were not skipped.
P-384 rejection passed. The platform could not create secp256k1, so that case was
skipped and is not macOS curve-rejection evidence. The local receipt is
`artifacts/lead-macos-signing-receipt.json`. This adds macOS desktop JIT/IL
coverage, not interpreter, native R2R, or iOS execution evidence.
