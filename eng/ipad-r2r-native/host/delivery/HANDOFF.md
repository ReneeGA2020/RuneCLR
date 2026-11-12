# iPad delivery bridge — handoff (production source seal)

Status: production bridge sources are frozen for review; integration tests live in the sibling
`selftest/` directory owned by another worker and are NOT part of this source seal or its build claim.

## Source revision

    worktree  E:/RuneCLR-ipad-delivery-20261110
    branch    feature/ipad-delivery-bridge-20261110 (base origin/main 55d3ef8)
    state     uncommitted working tree, nothing staged or pushed

## Files in this seal (production only)

    BoundedHttpFetch.cs
    ContractCompatibility.cs      (local diff: bounded sidecar read, see below)
    DeliveryContracts.cs
    IpadDeliveryBridge.cs
    IpadDeliveryBridge.Deliver.cs
    PackageSealer.cs
    RuneCLR.IpadDelivery.csproj
    README.md
    HANDOFF.md

`selftest/` and `selftest/IpadDelivery.SelfTest.csproj` are owned by another worker; do not treat them as
part of this seal's build claim.

## Scripted API (what the host actually calls)

    DeliveryResult DeliverAsync(DeliveryOptions, DeliveryOffer, CancellationToken)
    TrustedReleaseRecoveryStart Start(DeliveryOptions, TrustedReleaseOffer?, TrustedUpdateActivator)
    Func<string, TrustedUpdateCandidate, bool> RequiredCheck(DeliveryOptions)
    SealedPackage PackageSealer.Seal(contentRoot, identity, consumedRelativePaths, contract, target, key)
    TrustedReleaseVerification PackageSealer.Verify(contentRoot, hostSpki, documentPath)

DeliverAsync result semantics:
- On success `DeliveryResult.Offer` is a `TrustedReleaseOffer(contentRoot, private document copy)` built from the
  SAME final root that was just verified. Hand exactly that offer to Start; never re-download or rebuild it.
- DeliverAsync downloads, stages (signed-list exact match), re-verifies the same root, applies the expected-entry
  match, and runs the required compatibility gate. It does NOT activate and does NOT write a receipt.
- `ReceiptAdvanced` stays false for DeliverAsync by contract; only a successful Start writes the receipt.

Start semantics:
- `offer == null` restores the last known good release from the receipt.
- The required check runs after host-SPKI verification of the offered and the LKG candidate and before host-loaded
  activation; a rejected candidate never occupies the process gate, never calls the activator and never writes a receipt.

## Root invariants (P1-1)

`DeliveryOptions.Validate()` runs before any download, directory creation or write and requires:
- `AllowedReleasesRoot` exists and contains no reparse point;
- `FinalReleaseDirectory` is a non-empty child of that root (not the root itself) with no reparse points;
- `RecoveryReceiptPath` is OUTSIDE the releases root and contains no reparse points.

## Expected-entry match (P2-2)

`DeliveryOffer.EntryAssemblyName/EntryTypeName/EntryMethodName` are optional. When non-empty they must equal the
verified candidate's entry assembly file name, entry type and entry method; any mismatch fails the delivery.
Empty means "no expectation". The signed manifest remains the authority.

## Sidecar and compatibility

The required sidecar is the reserved `runeclr.compat.json` inside the verified AdditionalContent; its relative path
is not configurable. `ContractCompatibility.cs` is the frozen desktop implementation (SHA-256
97820082277705F36172E20ADF1806D2E67F510D48D0B76ECE61B38F5424BFA8) with ONE documented local diff: an optional
`maxSidecarBytes` argument that bounds the read (the desktop copy reads the whole file). Hash and parse still use
the same single buffer.

## Packaging (PackageSealer)

- Canonically validates every consumed path before reading or writing (relative, no empty/./.. segments, no
  duplicates or case conflicts, no reserved-name collision, inside the root, existing).
- Rewrites `payload-files.txt` from the final signed bytes, writes the canonical `runeclr.compat.json`, signs the
  complete consumed set and writes `runeclr.release.json`.
- Verifies the just-written envelope against the on-disk files with the public half of the same key, so a
  hash/sign mismatch can never be packaged.
- The private key is only used through the supplied instance; it is never written or logged.

## Build prerequisites

Core TrustedUpdate sources must be the patched tree that contains the 7-parameter
`TrustedReleaseRecovery.TryStart(..., Func<string, TrustedUpdateCandidate, bool>? candidateCheck)`.
The final frozen core is `TrustedReleaseRecovery.cs`
SHA-256 2b02cae292d1fd11ab308bf611acd8e3a3d18577b7850d3846145e069f8abfd1.

    dotnet build eng/ipad-r2r-native/host/delivery/RuneCLR.IpadDelivery.csproj -c Release \
        -p:CoreTrustedUpdateRoot=<patched-core-dir>

The project default is the repo-relative `../../../../src/RuneCLR.TrustedUpdate`; before the core patch is merged
that default build is EXPECTED TO FAIL (missing the 7-parameter overload). The override is the supported path today.

Additional BCL references beyond the host's existing set:
System.Net.Http, System.Net.Primitives, System.Security.Cryptography, System.Text.Json,
System.Reflection.Metadata, System.Collections, System.Memory, System.Threading, System.Threading.Tasks.
No CoreCLR 12 / crossgen change: IL-only, no P/Invoke, no unmanaged code.

## Scope and limits

- Desktop-only. No iPhone/iPad execution was performed here; device acceptance belongs to the native owner.
- DeliverAsync stages/verifies/gates only; Start performs activation. The core's own Verify happens before the
  bridge gate, so no pre-gate claim is made for it.
- The real end-to-end (author assembly actually loaded and invoked) and the network negative cases are exercised by
  the separate test owner's suite, not by this source seal.


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

