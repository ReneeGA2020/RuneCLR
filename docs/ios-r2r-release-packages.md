# Matching Release controlled-package acceptance

The [Release controlled-player driver](../eng/ios-r2r-release-packages.py)
extends the matching runtime-critical input layout to the portable package
player. It rebuilds its trusted composite with the validated Release CoreLib
and crossgen2, replaces native CoreCLR with the CID v2 candidate, and retains
the original Runtime and Packages IL bytes. Other framework libraries remain
the preserved same-base managed inputs. This is not a complete Release
shipping-pack build.

## Provenance and acceptance boundary

The driver checks candidate source commit, tracked cleanliness, build receipts
and native/CoreLib/compiler hashes. It preserves the earlier Debug app,
compares signed native and wrapper code/data sections, records all input and
bundle hashes, and rejects compiler/operator tools in the player.

Its separate install phase launches the empty player before fresh operator
fixture generation. The run phase requires production after installation,
the exact approved contract image and managed-il-gameplay-v1 profile, all nine
fixture directories, matching manifest/installed payload hashes and IL-only
payloads. The portable fifteen-case harness supplies source/import recovery,
private version/generic state, ordinary exception cleanup, admission rejection
and completed context retirement checks. The installed bundle must remain
unchanged.

Release does not emit the Debug interpreter dumps required by the earlier
[Debug package experiment](ios-controlled-packages.md). This driver explicitly
reports functional acceptance separately and leaves methodInterpreterProof
pending. DynamicCodeCompiled=False, IL headers and a successful launch do not
prove method-level interpretation. The earlier ProbePlugin native entry
capture does not establish execution of these GameScript/private-helper methods.

## Reproduction

Use new output directories; the existing Debug and Release experiments are
immutable evidence. Copy the driver beside ios-r2r-fix-verify.py and
verify-ios-packages.py on the prepared Mac.

```sh
python3 eng/ios-r2r-release-packages.py build --output /path/to/new-output \
  --candidate /path/to/clean-release-candidate \
  --managed /path/to/matching-release-managed-build \
  --controlled /path/to/preserved-debug-controlled-player
python3 eng/ios-r2r-release-packages.py install --output /path/to/new-output
# Generate fresh fixtures on the operator after installation, then transfer.
python3 eng/ios-r2r-release-packages.py run --output /path/to/new-output \
  --packages /path/to/new-fixtures --produced-utc <operator-start-UTC>
python3 eng/ios-r2r-release-packages.py cleanup --output /path/to/new-output
python3 eng/ios-r2r-release-packages.py archive --output /path/to/new-output
```

## Recorded run

The 2026-10-13 local-date experiment uses a new remote output named
ios-r2r-release-packages-20261013. Build and functional acceptance pass:
**15/15** actual harness cases, managed exit zero, disabled dynamic compilation,
unchanged bundle, post-install fresh fixtures, private/static state reset,
ordinary failure/rejection recovery and completed context collection.

| Event | UTC |
| --- | --- |
| App installed | 2026-10-12T16:45:15.810522+00:00 |
| Fresh operator production started | 2026-10-12T16:46:12.9723887+00:00 |
| App logged 15/15 | 2026-10-12T16:46:43 |

The source/corelib/compiler/native identities match the preceding
[Release acceptance](ios-r2r-release-validation.md). The original IL contract
hash is 86bc966dd4e9f5f349b0c3d8fb869e180f76823af0ee6aa6e1ce64e7bbd16f31.
The fresh fixture transfer archive hash is
30529a127ba11090aad0be743cabd111ecb97e5addb6a62f923f6b3ed2764d04.

An experiment-driver error initially classified the successful run as a failure:
its count regex accidentally matched d+ instead of decimal digits. This is our
receipt-parser error, not a runtime defect. The original results.json,
driver.py and run-driver.log remain unchanged. A corrected read-only reassess
phase independently checks fifteen individual PASS lines, the aggregate
15/15 line, zero managed/launcher exit, log/receipt/driver hashes, and unchanged
installed bundle and payloads. It writes functional-reassessment.json and
reassessment-driver.py without rerunning the app. Its result is
functionalPassed=true and appRerun=false.

The owned simulator 85D718CD-E562-415D-955C-833E4D5A1D4F shut down successfully.
The local evidence archive is
artifacts/ios-r2r-investigation/20261013-release-packages/evidence.tar.gz,
96,749 bytes, 45 members, SHA-256
e6cacf31929990aff5e271d3a2c9120368337be31262747dfb1a63f2bc12549a.
Bounded download, archive hash, original failure preservation, reassessment
hashes, raw PASS counts and recorded shutdown were independently verified.
The later [native package/helper entry capture](ios-release-package-entry.md)
uses these same player and fixture bytes in a new diagnostic installation.
It records 33 valid samples covering all 23 required method groups and normal
exit, including private Read and generic Next methods. Its fifteen PASS events
and 15/15 aggregate appear in the owned app's unified log. The original
raw-JSON substring parser misses the escaped slash and records false; a
read-only assessment parses actual eventMessage values without replaying the
app. This new diagnostic evidence does not rewrite the earlier functional receipt.
Physical-device acceptance and runtime-enforced execution selection remain open.
