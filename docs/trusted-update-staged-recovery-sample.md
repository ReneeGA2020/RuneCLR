# Staged signed recovery sample

This sample publishes a signed release with a local file stream, starts it, and
can restore the last signed receipt in a later process. The host calls
TrustedReleaseStaging.PublishAsync and then TrustedReleaseRecovery.TryStart.
It does not use the unsigned last-known-good file.

The flow is local file streams only. It is a desktop standalone IL
demonstration. It is not HTTP, not an interpreter proof, not ReadyToRun native
execution, and not an iOS result. Passing this sample does not accept the
recovery core.

## Commands

    dotnet run --project samples/RuneCLR.TrustedUpdateHost -c Release -- --stage-recoverable-start <releases-root> <receipt-file> <host-spki-file> <source-content-root> <signed-release-file> <new-final-dir>
    dotnet run --project samples/RuneCLR.TrustedUpdateHost -c Release -- --staged-recovery-self-test

The SPKI file is host trust configuration and must be the pinned P-256 length.
The host reads it and the signed document with one capped stream. It verifies
the source only to learn the signed relative paths, then opens those files as
streams for staging. A source read, verify, or stage failure is printed as
STAGED-RECOVERY SOURCE and is not reported as a successful offer check. The
same start may then call recovery with no offer. An offer is passed to
recovery only after staging succeeds. Recovery verifies the final directory
again with the original signed document. The sample does not rebuild the
candidate or approval and does not drop additional files.
The receipt path passed into recovery is only Path.GetFullPath. The sample does not
resolve a receipt file symlink, including after a source read, verify, or stage
failure. The library reports config=receipt-link before it reads or replaces the
target receipt, and the activator is not called. A final directory already
committed by staging is left in place.

If that offer is rejected before activation, recovery decides whether the
receipt can run. If the activator is entered and fails, this start does not
try the receipt again and does not replace it. An existing final directory is
left in place. A failed stage does not delete an already verified release.
After a successful directory move, the sample does not delete the final
directory.

A later process can restore the receipt with --recoverable-start and no offer.
That does not publish the release again and does not ask the operator to name
it. Activation success with a persistence failure is still a successful start;
persistence is reported on the same line.

The self-test signs real P-256 packages in the parent process only. The entry
computes 41 * 3 + 7 and writes 130 to a marker. Private, helper, and
TrustedUpdate.Helper..bin files are signed and hash-checked. The IL does not
reference them. That is package integrity, not evidence that a private
dependency executed.
