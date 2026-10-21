# Trusted update recovery sample

This sample restarts a signed release across process launches. The host calls
TrustedReleaseRecovery.TryStart. The receipt is separate from the unsigned
last-known-good file. With no offer, a later process restores the receipt's
release. The host does not choose that release by hand and does not publish it
again.

This is a desktop standalone IL demonstration. It is not a network service,
anti-rollback log, iOS gate, or ReadyToRun native execution.

## Commands

    dotnet run --project samples/RuneCLR.TrustedUpdateHost -c Release -- --recoverable-start <releases-root> <receipt-file> <host-spki-file> [offered-content-root signed-release-file]
    dotnet run --project samples/RuneCLR.TrustedUpdateHost -c Release -- --recovery-self-test

The SPKI file is host trust configuration. Its length must be the pinned P-256
size. The public key is not taken from the release or the receipt. The host
reads the SPKI and any offered document with one capped stream. An offered
document that is too large or cannot be read is a pre-activation rejection.
The same start may still restore the receipt. That read failure is printed as
OFFER-READ. It is not reported as a successful signature check, and it does
not use the unsigned last-known-good file.

The receipt is read, bounded, and verified again inside TrustedReleaseRecovery.
The sample does not build a candidate or approval for it. The releases root
may be canonicalized before the call. The receipt path is only made absolute
with Path.GetFullPath. A receipt file symlink stays intact so the library can
reject that leaf before it reads or writes the receipt. The sample does not
resolve the leaf itself.

On success the line is RECOVERY-START OK. source is Candidate for a new offer
or LastKnownGood for receipt recovery. The activator reports the verified
additional-file count. Activation success with a persistence failure is still
a successful start; persistence is reported separately on that line.

A rejected start distinguishes config, candidate, and recovery. Each reason
keeps verification, plan, and activation. A thrown entry fails activation,
does not fall back in that process, and does not replace the receipt. The same-process
probe does not treat an arbitrary second failure as a lock. After the thrown entry,
and after a successful offer, the next no-offer start in that process must report
recovery plan ProcessSelectionLocked with detail locked, keep the activator call
count at 1, and must not activate again. The successful offer still writes marker
130 and its receipt before that lock.

Normalizing the releases root or offered content root can fail with a local
path error. The receipt path is not resolved through its leaf. The sample
reports config=path and RECOVERY-CALLS 0 when that normalization throws. It
does not print the exception text. A receipt file symlink is config=receipt-link,
with no activator call and no change to the target receipt.

The self-test signs real P-256 packages in the parent process only. The entry
computes 41 * 3 + 7 and writes 130 to a marker. Private and helper files are
signed and hash-checked. The IL does not reference them. That is package
integrity, not evidence that a private dependency executed. The recovery core
itself is not claimed to be accepted by this sample.
