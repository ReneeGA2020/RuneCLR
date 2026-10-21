# Trusted release recovery

`TrustedReleaseRecovery.TryStart` restarts one signed release across process
launches. The unsigned legacy last-known-good file is not an authentication
record. The receipt is a separate host-owned pointer outside the immutable
releases root. It stores a relative content root and the original signed
document. It does not store a package public key, and a deserialized candidate
or approval in the receipt is not trusted.

The host passes its own 91-byte SPKI. Every offer and every receipt is checked
with `TrustedRelease.Verify` against that key and the files on disk. The
selector then plans the verified candidate. `TryStartHostLoaded` is called with
`lastKnownGoodPath: null`. The receipt path is not the selector record.

## When recovery is allowed

A rejection before the activator runs may fall back to the receipt. That
includes a bad signature, an incompatible target, a missing file, a content
root outside the releases root, and a content root that cannot be stored as a
safe relative path. The relative-path check happens before `Verify` and before
the activator, so a path with a space, another disallowed character, or more
than `TrustedRelease.MaxPathLength` characters does not activate and then
discover that no future process can restore it.

`TryStartHostLoaded` plans again. The wrapper records whether the activator was
actually entered. If it was not entered and the result is not
`ProcessSelectionLocked`, that second plan is still a pre-activation rejection
and recovery continues. The failure enum alone is not treated as proof that
activation ran. Once the activator is entered, a failure result or a thrown
exception stops the process. The static process gate stays occupied. This
process does not retry or fall back.

On the recovery path the activator is called with source `LastKnownGood`. Its
candidate-failure argument is the offer plan failure when there was one, such
as an incompatible target. A signature failure stays `None` there;
`Candidate.Verification` carries it. `AdditionalContent` comes from verifying
the original document again, not from extra receipt fields.

## Receipt and failure to save

The receipt cap is `MaxReceiptBytes` (96 KiB). The signed document cap stays
`TrustedRelease.MaxDocumentBytes` (64 KiB). A document that is over its own cap
but still inside the receipt cap is `document-size`. A larger file is
`receipt-size`. The reader uses one `FileStream` and stops after
`MaxReceiptBytes + 1` bytes. It does not trust `FileInfo.Length` or a single
`Read`.

The receipt is written only after the candidate activator returns success.
The writer creates `receipt-*.tmp` with `FileMode.CreateNew` in the receipt
directory. Ownership starts when that handle returns. A failure while writing,
flushing, disposing, or moving deletes that temp and no other file. The
previous receipt bytes stay. The result is activated, plus
`TrustedReleasePersistenceFailure`, and the gate stays locked. The next process
still uses the old receipt. A crash between creating the temp and replacing the
pointer can leave a temp; the next start does not read temps. Replacing the
pointer with `File.Move` is not a crash-durable directory snapshot.

If the offer is absent, or recovery itself is what was running, a later start in
the same process reports `ProcessSelectionLocked` on `Recovery.Plan` with
detail `locked`. That lock is not attributed to an offer that was not supplied.
An offered start that finds the gate already taken reports it on the candidate.

## Path and link boundary

The releases root, the offer content root, and the receipt path are canonicalized
the same way before any inside check. Each existing component is visited. A
junction or symlink contributes one hop from a single budget of 32. The target
path is walked component by component with that same budget, so a link in the
middle of the target is expanded too. A cycle or a target that cannot be
resolved stops the walk. Containment then uses those paths: ordinal ignore-case
on Windows and ordinal comparison elsewhere.

The detail is chosen in this order, and a system temp symlink does not change it:

1. The receipt leaf is itself a reparse point, or a link on the receipt path
   cannot be resolved or exceeds the hop budget: receipt-link. This is decided
   before containment, so a leaf link is rejected even when its target is outside.
2. The canonical receipt is inside the canonical releases directory: receipt-root.
   That includes a normal path, a releases ancestor alias, and a shared ancestor
   such as /tmp or /var. It is not receipt-link merely because an ancestor is a
   symlink.
3. A canonical receipt outside that directory is allowed, including when the
   outside path still goes through the same ancestor link.

A prefix such as releases-extra is outside releases. The resolved releases
directory must be a real directory. There is no second ancestor scan with a
different rule. Links created after the check are outside this claim. This is
not race-proof.

Configuration inside the releases root, a short SPKI, and an unusable receipt
parent are rejected before load. Ordinary failures are short codes. Results do
not retain exception objects or document text.

## What this is not

Not a race-proof snapshot. Not anti-rollback. Not network authentication. Not
an iOS native admission gate. Not a sandbox. The internal persist and
before-start hooks are test-only seams in this assembly; they are not a host
contract.

## Desktop evidence

Stock desktop JIT on Windows and macOS arm64. Not interpreter evidence and not
iOS. Linux was not executed here. No scenario is skipped. The releases-root alias cases create a real junction on Windows and a real
symlink on other systems. One case stores a link target whose middle component is itself a link.
A shared ancestor junction covers a receipt inside the releases tree and one
outside it. An ancestor link into the releases tree is receipt-root. A receipt
file that is itself a link stays receipt-link.
The case comparison and the persist failure do not depend on a Windows file lock.
A valid RTRSIG1 receipt with one flipped signature byte is InvalidSignature.
A receipt that keeps A's document but points contentRoot at an existing
different package is ContentMismatch.

`dotnet build tests/RuneCLR.TrustedReleaseRecovery.Tests/RuneCLR.TrustedReleaseRecovery.Tests.csproj -c Release --artifacts-path artifacts/recovery-check --nologo`

Build exit 0, 0 warnings, 0 errors.

`artifacts/recovery-check/bin/RuneCLR.TrustedReleaseRecovery.Tests/release/RuneCLR.TrustedReleaseRecovery.Tests.exe`

Test exit 0, 37/37 passed. No scenario is skipped. Child processes are started from the apphost.
`dotnet <dll> -- --child` is not a valid launch because `Environment.ProcessPath`
would then be the `dotnet` host.

On 2026-10-18 an Orca Worker ran the fixed snapshot on macOS arm64 with the
existing private SDK 11.0.100-preview.6.26359.118. Direct apphost runs passed
37/37 under each of the `/var`, `/tmp` and `/private/tmp` temp prefixes; all five
trusted-host self-tests also passed under each prefix. No link scenario was
skipped. The lead checked the archive hash, 15 source bindings and all 18 test
outputs against the receipts. See
`artifacts/lead-macos-recovery-final-receipt.json` and
`artifacts/lead-macos-recovery-final-run.log`. The original system-temp-alias
diagnostic failure remains separately recorded in
`artifacts/lead-macos-recovery-receipt.json`.
