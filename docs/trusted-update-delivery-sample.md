# Trusted update delivery sample

This sample shows a local file-stream handoff into the signed host start.
It is a desktop IL demonstration. It does not implement HTTP, and it is not
ReadyToRun native execution or iOS evidence.

## Commands

    dotnet run --project samples/RuneCLR.TrustedUpdateHost -c Release -- --stage-signed-start <source-content-root> <signed-release-file> <host-spki-file> <new-final-directory> <last-known-good-file>
    dotnet run --project samples/RuneCLR.TrustedUpdateHost -c Release -- --staged-self-test

The SPKI file is host trust configuration. The public key is not taken from the
release package. The host first reads the signed document and SPKI with a capped
stream, then calls TrustedRelease.Verify on the source root only to learn the
signed relative paths. A file name may contain two dots, such as Helper..bin. Only a whole path segment of . or .., an absolute path, or a relative path that escapes the source root is rejected. Those paths are opened as file streams and passed to
TrustedReleaseStaging.PublishAsync. Staging copies them, verifies the staged
tree, and publishes with one directory move. The sample does not treat its own
source check as the final publish decision.

On success the sample passes Staging's candidate and approval through unchanged,
including every AdditionalContent file, to TrustedUpdateProcess.TryStartHostLoaded.
The selector still checks version, target, hashes, and the process gate.
Verification or publish failure does not start the payload and does not change
the last-known-good file. An existing final directory is not overwritten.
A thrown activation leaves the previous last-known-good file in place and does
not switch packages in that process. A later process can publish the correct
signed package to a new final directory and start it.

The self-test uses one standalone IL assembly. Activate computes 41 * 3 + 7 and
writes that value to a marker file. The private and helper files are signed and
hash-checked. The IL does not reference them. That is package integrity, not
evidence that a private dependency executed. The host loads only the verified
entry assembly. It does not scan the payload directory or load unlisted files.

The private key exists only in the parent self-test process. It is not written
to the repository or logs.

The filename check rejects complete `.` and `..` path segments and paths
outside the source root. A filename containing two consecutive dots, such as
`TrustedUpdate.Helper..bin`, remains valid. The `dotted-helper` self-test signs
that file, publishes it with the other listed content, and checks actual entry
activation with `additional=2`.
