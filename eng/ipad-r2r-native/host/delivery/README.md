# Portable iPad delivery bridge

Source-only bridge for the iPad host: bounded HTTP fetch, signed-release staging, required
compatibility gate, and process-start recovery. No native code, no desktop exe, no Windows-only APIs.

## Files to compile into the host TrustedUpdate assembly

Add these to the same csc invocation that already builds source/trusted-update-src/*.cs
(same assembly so the RuneCLR.TrustedUpdate types are shared):

    BoundedHttpFetch.cs
    ContractCompatibility.cs
    DeliveryContracts.cs
    IpadDeliveryBridge.cs
    IpadDeliveryBridge.Deliver.cs
    PackageSealer.cs

Do NOT add selftest/* or the *.csproj files to the host build (desktop verification only).

Required core patch (not in fresh main): the 7-parameter
TrustedReleaseRecovery.TryStart(..., Func<string, TrustedUpdateCandidate, bool>? candidateCheck)
from src/RuneCLR.TrustedUpdate/TrustedReleaseRecovery.cs in the private core worktree that carries the patch.

## References

Additional BCL assemblies beyond what the host already references:

    System.Net.Http, System.Net.Primitives, System.Security.Cryptography, System.Text.Json,
    System.Reflection.Metadata, System.Collections, System.Memory, System.Threading, System.Threading.Tasks

Same -target:library / -nologo flags and the same -r: set as the existing TrustedUpdate build.
No CoreCLR 12 / crossgen flag changes: the bridge is IL-only, no new P/Invoke, no unmanaged code.

## Host usage

    var result = IpadDeliveryBridge.Start(options, offerOrNull, hostActivator);   // process start
    await IpadDeliveryBridge.DeliverAsync(options, offer, cancellationToken);    // staging only

offerOrNull == null restores the receipt last known good. The required compatibility check runs after
host-SPKI verification of both the offered and LKG candidate and before host-loaded activation; a
rejected candidate never occupies the process gate, never calls hostActivator and never writes a receipt.
DeliverAsync only downloads, stages, verifies and gates: it does NOT activate and does NOT write a receipt.
If the host must block, do it off the UI thread; the preferred path is to await.

## Options the host must supply

    HostSubjectPublicKeyInfo  fixed pinned SPKI bytes (never from network/package/env)
    Target                    e.g. ("ios-arm64","arm64")
    HostContract              host-owned Contract name/version/mvid
    HostDeploymentContractPath host-owned Contract assembly path
    AllowedReleasesRoot / RecoveryReceiptPath / FinalReleaseDirectory
    RequireRuntimeContractCompatibility = true (false is rejected)

HostContract is cross-checked against the real deployment Contract assembly; the signed
runeclr.compat.json must then match that identity (same-buffer SHA-256 + JSON parse).

## Packaging (after native code signing)

    var sealedPackage = PackageSealer.Seal(contentRoot, identity, consumedRelativePaths, hostContract, target, privateKey);

Rewrites payload-files.txt from the final signed bytes, writes the canonical runeclr.compat.json, signs
the complete consumed set and writes runeclr.release.json. The private key is only used through the
supplied instance and is never written or logged. Re-run after any GUI/native re-sign.

## Verification

    dotnet build eng/ipad-r2r-native/host/delivery/selftest/IpadDelivery.SelfTest.csproj -c Release \
        -p:CoreTrustedUpdateRoot=<path-to-core-trustedupdate-with-the-7-param-overload>
    dotnet eng/ipad-r2r-native/host/delivery/selftest/bin/Release/net11.0/IpadDelivery.SelfTest.dll

Selftest covers bounded fetch (normal, redirect refused, body cap, deadline), sealing round-trip,
partial stage rejection with no final directory, unlisted sidecar rejection, offer delivery, process
start from the offered release, offline restore from the receipt, activation throw keeping the old
receipt, and a required Contract mismatch rejecting the candidate.


## Usage (authoritative)

DeliverAsync is a ValueTask. Await it (or block off the UI thread) and use the result as-is:

    DeliveryResult delivery = await IpadDeliveryBridge.DeliverAsync(options, offer, cancellationToken);
    if (!delivery.Succeeded) { /* reject: nothing was activated, no receipt was written */ }
    TrustedReleaseOffer verified = delivery.Offer!;
    var start = IpadDeliveryBridge.Start(options, verified, hostActivator);

Never re-download the envelope and never construct the document yourself: the offer returned by
DeliverAsync carries the exact document that was verified against that content root.

Compatibility predicate: DeliverAsync, Start(offer) and Start(null receipt restore) all run the SAME internal
check (host Contract identity vs the real deployment metadata, plus the verified signed sidecar
membership/hash/schema/identity, with the bounded MaxCompatSidecarBytes read wired into the same guard).
There is no parallel weaker path; an unset or wrong HostContract, or an oversized/missing sidecar, fails
the delivery before any activation.

## Known test-evidence limits

- The historical real-flow log recorded 22 PASS / 0 FAIL without archived PIDs; a later summary line claiming 23/23 is stale and is being corrected by the test owner.
- serverDisposed counts server-side disposals, not client response disposal.
- The caller-cancel case covers only cancellation before the request; cancel-during-body is not covered.
- Client disposal is a source-level using fact, not an observed client-side measurement.
