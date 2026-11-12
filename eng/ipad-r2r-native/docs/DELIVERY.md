# Delivery host mode (HTTP + offline) and sealing

This describes the host-mode glue that runs an HTTP delivery (or an offline last-known-good
restore) before the author entry runs, and the sealing recipe for the release directory.

State: unsigned compile verification only. The portable bridge sources are frozen
(production-seal-manifest adea4e17...) but review and real author-load tests are still
running, so this host must not be signed or installed yet.

## Process flow

    native runtime.m
      --delivery  -> resolves Documents/results/<runId>.json, exports RUNECLR_RESULT_PATH,
                     RUNECLR_RUN_ID, RUNECLR_HOST_MODE=delivery, RUNECLR_DOCUMENTS_PHYSICAL
      coreclr_initialize, then coreclr_execute_assembly(RunEntry.dll)
    RunEntry.Main
      RUNECLR_HOST_MODE=delivery ? TrustedUpdate.DeliveryHost.Run() : TrustedUpdate.Driver.Run()
    DeliveryHost.Run
      reads the real deployment Contract identity, builds DeliveryOptions, then:
        mode=http    -> await IpadDeliveryBridge.DeliverAsync(options, offer, ct)
                        success -> use result.Offer (verified root + private document copy)
        mode=offline -> no offer, the recovery receipt last-known-good is used
      IpadDeliveryBridge.Start(options, offer, Activate)
        the required compatibility check runs after host-SPKI verification of the offered
        and of the last-known-good candidate, and before activation
    Activate(candidate, source, candidateFailure)
      loads candidate.AssemblyPath (inside the verified content root), resolves the entry type
      and method named by the SIGNED manifest, invokes it with the host scope, and returns
      the value the selector reports

Entry selection authority is the signed envelope. The unsigned side only supplies the
document URL, the content URL mapping and the expected version name, and each of those is
only an expected-match check against the signed candidate.

## Host configuration

| variable | meaning | trust |
| --- | --- | --- |
| RUNECLR_HOST_MODE | delivery | placement |
| RUNECLR_DELIVERY_MODE | http or offline | placement |
| RUNECLR_EXPECTED_VERSION | expected version name (also expected-match for http) | placement |
| RUNECLR_DELIVERY_DOCUMENT_URL | signed release document URL | placement (signature decides) |
| RUNECLR_DELIVERY_CONTENT_BASE | base URL for content files | placement (signature decides) |
| RUNECLR_DELIVERY_CONTENT | comma-separated relative paths to fetch | placement (staging rejects any set that differs from the signed list) |
| RUNECLR_DELIVERY_RELEASES | releases root (default <documents>/releases) | placement |
| RUNECLR_DELIVERY_RECEIPT | last-known-good receipt (default <documents>/state/recovery-receipt.json) | placement |
| RUNECLR_DELIVERY_RELEASE_NAME | final release directory name (default expected version) | placement |
| compiled constant | pinned P-256 SubjectPublicKeyInfo | HOST TRUST ANCHOR |
| read from disk | deployment Contract name/version/mvid | HOST TRUST ANCHOR |

RequireRuntimeContractCompatibility is a compiled constant true; there is no switch.

## iOS path note

iOS exposes Documents as /var/mobile/..., and /var is a symlink to /private/var. The delivery
options reject reparse points anywhere in the root chain, so a raw /var path would be rejected.
runtime.m therefore resolves the Documents directory with realpath(3) and exports
RUNECLR_DOCUMENTS_PHYSICAL, which DeliveryHost prefers. If a device still reports a rejection,
record the exact path and the reported FileAttributes instead of loosening the check.

## Pinned key provenance (test builds)

Generated 2026-11-10 on mac-172-26-202-95 for test builds only:

    openssl ecparam -name prime256v1 -genkey -noout -out $HOME/RuneCLR-secrets/delivery-test-p256.pem
    chmod 700 $HOME/RuneCLR-secrets; chmod 600 $HOME/RuneCLR-secrets/delivery-test-p256.pem
    openssl ec -in $HOME/RuneCLR-secrets/delivery-test-p256.pem -pubout -outform DER -out spki.der

Embedded public value:

    SPKI base64  MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEpzwSXIQSZ5Zq3yWoIgIVSzeMeoxnTGoAVGD3T1WMpoZxz86JTXc0PLZPG6Pxg2L1tg9FzAVJhCkO8WUI5ygpBg==
    SPKI sha256  936c3bbc98b7725b467deb1e18380d49ccb9caf088709b9a0a4ab781c759c732

DeliveryHostKey.SpkiMatchesPin() re-hashes the embedded constant at startup, so an accidental
edit fails closed before any download. The private key lives only at
$HOME/RuneCLR-secrets/delivery-test-p256.pem (mode 600, outside the repository, never copied to
the device or printed). Production builds replace the constant with a release key held by the
release owner; the same sealing path applies.

## Sealing recipe (after native owner code signing)

Order matters: sign the owner dylib first, then seal, because the payload list and the envelope
hashes are computed from the final signed bytes.

    dotnet build eng/ipad-r2r-native/host/test/Seal/Seal.csproj -c Release -p:CoreTrustedUpdateRoot=<core> -p:DeliverySourceRoot=<delivery>
    dotnet eng/ipad-r2r-native/host/test/Seal/bin/Release/net11.0/SealRelease.dll --content <releaseDir> --version A --runtime ios-arm64 --architecture arm64 --entry-type TrustedUpdate.Update --entry-method Run --entry-path TrustedUpdate.Update.dll --files <comma list> --contract <app>/TrustedUpdate.Contract.dll --key $HOME/RuneCLR-secrets/delivery-test-p256.pem

The tool prints the sealed file set and writes payload-files.txt, runeclr.compat.json and
runeclr.release.json, then re-verifies the just-written envelope with the public half of the
same key. It never prints key material.

## Future end-to-end command sequence (after review GO)

    1. owners: generate A and B AFTER the new host install receipt exists (postinstall),
       unsigned, then GUI codesign each owner dylib.
    2. sealer: run the Seal command above per version; keep the printed file set.
    3. serve: python3 -m http.server --directory <sealedRoot> 8099  (or an HTTPS host).
       URLs: /<ver>/runeclr.release.json plus /<ver>/<file> for each content file.
    4. launch (device): devicectl device process launch --console --terminate-existing
       --device <UDID> --environment-variables <see table> <bundle> --delivery --payload A-delivery-1 --nonce <owner nonce>
    5. offline/fallback: same launch with RUNECLR_DELIVERY_MODE=offline (no URL) after a
       successful activation wrote the receipt; a candidate whose sidecar/version/contract
       does not match must be rejected pre-gate and leave the receipt unchanged.

## Known limits

- Not signed or installed; the bridge review and the real author-load tests are still running.
- The native owner loader is shared with the existing flow; this glue adds delivery and entry
  selection, not a new loader or a new unload model.
- A stale final release directory makes staging fail closed; bump RUNECLR_DELIVERY_RELEASE_NAME
  for a fresh attempt instead of deleting evidence.
## Operations: server layout, URL mapping, receipt cases

Seal once per version and serve the sealed directory as-is; the host fetches exactly the
files listed in payload-files.txt plus the document and the sidecar.

    <servedRoot>/
      A/
        runeclr.release.json      <- signed document (RUNECLR_DELIVERY_DOCUMENT_URL)
        runeclr.compat.json       <- signed sidecar
        payload-files.txt         <- signed list (post-sign bytes)
        TrustedUpdate.Update.dll
        TrustedUpdate.Private.dll
        TrustedUpdate.IlOnlyHelper.dll
        TrustedUpdate.A.r2r.dylib

Print the exact host configuration for one sealed directory:

    python3 -B eng/ipad-r2r-native/host/tools/release_urls.py \
      --root <servedRoot>/A --base-url http://<mac-ip>:8099/A --version A

It prints the document URL, each content URL, the RUNECLR_DELIVERY_* environment object and the
launch arguments. RUNECLR_DELIVERY_CONTENT_BASE always ends with a slash; a base without one
would resolve content as a sibling path (the host also normalises this, belt and braces).

Serve:

    python3 -m http.server 8099 --directory <servedRoot>   # test only, plaintext LAN

Sanity checks before a device run:

    curl -sS -o /dev/null -w '%{http_code} %{size_download}\n' http://<ip>:8099/A/runeclr.release.json
    curl -sS http://<ip>:8099/A/runeclr.compat.json | python3 -m json.tool
    shasum -a 256 <servedRoot>/A/*.dylib      # must equal the payload-files.txt lines

### Case matrix

| case | expected host behaviour |
| --- | --- |
| valid A over HTTP | full stage, verify, compat check, activation; result JSON ok, exit 0 |
| valid B over HTTP after A | new process, B selected from the signed document |
| offline (mode=offline, no URL) after a success | last-known-good from the receipt, no network |
| document signature tampered | download/stage ok, verification fails, no activation, receipt unchanged |
| sidecar missing or not listed in the signed set | required check fails before the gate |
| sidecar contract MVID/version != host Contract | rejected before the gate |
| sidecar runtime/architecture != ios-arm64/arm64 | rejected before the gate |
| expected version != signed version | version-mismatch, no activation |
| activation throws | ActivationFailed, no same-process fallback, receipt not replaced |
| receipt points at a release whose compat no longer matches | LastKnownGoodUnusable, no author code runs |
| HTTP deadline exceeded or oversized body | DownloadFailed / DownloadTooLarge, no staging |

Receipt and result locations on device:

    Documents/state/recovery-receipt.json      last-known-good receipt (host-owned)
    Documents/releases/<name>/                 staged/final release content
    Documents/results/<runId>.json             per-run result JSON written by RunEntry

`--payload <runId>` in delivery mode only names that result file; the release content comes from
the delivery root, never from the payload directory.