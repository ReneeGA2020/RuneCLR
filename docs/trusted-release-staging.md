# Trusted release staging

`TrustedReleaseStaging.PublishAsync` copies a signed release into a new private
stage directory next to the caller-chosen final directory. It publishes only
with one `Directory.Move`. The signing helper still owns `TrustedRelease.Verify`.
This step does not load author code, write a last-known-good record, or talk
to the network.

## Commit point

The host passes one stream opener per relative path. Those openers are snapshotted
before the first await, so a callback cannot change a path that was already
checked. Each returned stream is disposed by the publisher, before the move.

After every byte is in the stage directory, `TrustedRelease.Verify` must succeed
and the files on disk must be exactly the verified entry plus `AdditionalContent`.
The candidate is then retargeted onto the final paths. Hashes, entry metadata,
and the original approval stay as verified. Every retargeted path must stay
inside the final directory. The last cancellation check happens after that and
before `Directory.Move`.

`Directory.Move` is the commit. After it succeeds, this method does not verify
the final files again and does not delete the final directory. A later selector
`Plan` rehashes those paths. If the move does not happen, only the stage
directory this call created is removed. An existing final directory is not
overwritten.

## Limits and errors

The signed document must already be within `TrustedRelease.MaxDocumentBytes`.
The subject public key info must be exactly `TrustedRelease.SpkiBytes` before
any copy of that buffer. File count and per-file size use the signing helper
limits (`MaxFiles`, `MaxFileBytes`). The total copy budget is their product.
Relative paths must be canonical: no duplicates, no case conflicts, and no
`..`, backslash, or absolute path.

Ordinary failures return `TrustedReleaseStageFailure` and a short detail.
Verification failures also carry `TrustedReleaseFailure`. The result does not
retain an exception object.

## What this is not

Not a race-proof snapshot. Not network authentication, anti-rollback, an iOS
native gate, or a sandbox. Two publishers racing for the same final path are
not coordinated beyond `Directory.Move` failing when the destination exists.
The parent and published directories must remain under host control. The host
keeps published files unchanged through planning and activation; copying,
hashing and renaming do not prevent another writer from replacing them.

## Desktop evidence

Stock desktop JIT. Not interpreter evidence and not iOS.

`dotnet build tests/RuneCLR.TrustedReleaseStaging.Tests/RuneCLR.TrustedReleaseStaging.Tests.csproj -c Release --nologo`

then the test executable. Result: 17/17 passed, exit 0. The run covered a
signed payload whose returned paths sit under the final directory and which
`TryPlanCandidate` accepts, an oversized SPKI that opens no stream and creates
no directory, a source-list mutation inside `Open` that cannot change the
snapshot, cancellation before open and after the bytes are copied, a paused
first read while the final directory is still absent, an existing final
directory left byte-for-byte, plus missing, extra, wrong-key, tampered,
incomplete, throwing, oversize, duplicate, and case-conflict failures.

## Transport exception boundary - 2026-10-18

An Orca Worker measured six synthetic exceptions against the frozen
RuneCLR.TrustedUpdate binary. The lead copied and reran the diagnostic in a
fresh directory and checked each outcome, not just its exit code. Evidence is
`artifacts/lead-http-boundary-acceptance-20261018cs/receipt.json`.

IOException from the second Open returns IoFailure/open; from ReadAsync it
returns IoFailure/read. OperationCanceledException at either point returns
Canceled/cancel, even though the caller token was not pre-canceled in these
cases. HttpRequestException escapes at both points after finally runs. Every
returned stream is observed disposed, every final stays absent, and no owned
stage directory remains. Open failures occur before a stage is created.

An HTTP adapter must handle its transport/status errors explicitly and retain
ownership of any response acquired before Open returns a stream. The core
cannot dispose a response it never received. These synthetic observations do
not establish real HTTP behavior, response-wrapper disposal, timeout taxonomy
or acceptance of the separately implemented HTTP Host. They require no core
change and do not identify a regression in the existing stream contract.

## Streaming-body deadline observation - 2026-10-18

A separate lead diagnostic makes real ephemeral loopback HTTP requests under
stock .NET 11.0.0-rc.2.26504.105 without loading author assemblies or invoking
staging. With ResponseHeadersRead and HttpClient.Timeout=500ms, a stalled
header request times out after 516ms while the caller token remains uncanceled.
After headers and a one-byte prefix arrive, the next read remains pending past
a 1500ms observation window and is explicitly canceled for diagnostic cleanup.
Keeping a 1200ms caller-owned deadline alive across SendAsync and body reads
cancels that stalled read at 1209ms. The user-cancellation token stays uncanceled;
the deadline token is canceled. All three listener tasks stop, and neither
the build nor run watchdog fires. Both process exits are 0.

Evidence is artifacts/lead-http-timeout-observation-20261018cw/receipt.json,
with raw timings, loaded framework hashes and exact process commands beside it.
This measures framework behavior; it does not accept the separately implemented
HTTP adapter, prove its response disposal or exercise its stage/receipt cleanup.

## Scoped loopback HTTP acceptance - 2026-10-18

The separate HTTP Host now has joined exact-image acceptance (archival/local evidence: `../artifacts/lead-http-joined-acceptance-20261018dc/receipt.json`).
Independent Orca Worker reproduction passes nine lanes on Host a908231b:
success, offline LKG recovery, tampered payload, early EOF, 404, caller
cancellation, stalled-body deadline, oversized documents and repeated success.
Failures produce no author entry, published final, receipt or leftover stage;
watchdogs remain false. The same Host's stock 17/10 baseline is joined without
borrowing older-image results. Existing Debug fixtures make that baseline
non-hermetic. Redirects, TLS, external networking, native frames, different-version
HTTP switching, SDK promotion and devices are not accepted by this result.
The adapter still needs its own stalled-body cancellation and recovery evidence.
