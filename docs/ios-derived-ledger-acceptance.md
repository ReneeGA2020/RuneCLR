# iOS Derived-Ledger Application Acceptance

On 2026-10-14, a fresh iOS ARM64 simulator application using the
[matching derived-ledger runtime](mobile-derived-ledger-builds.md) passes15
scenarios and73 collected contexts in one process without a debugger. This
establishes functional terminal-budget and recovery behavior for the new
candidate. Actual optimized-branch/method-entry sampling and physical-device
execution remain open.

## Functional Result

The [summary](../artifacts/mobile-derived-ledger/ios-functional-receipts-20261014-attempt1/results.json)
records process73355 and nonce0a52d8f310dd495981eaf61e659f5964. Build, install,
post-install unchanged author-IL transfer, run and simulator cleanup exit0.
The15 ordered scenarios cover normal execution/static reset, tick/start/stop
loops, constructor/static-constructor loops, catch/filter continuation attempts,
finite/infinite cleanup, ordinary managed failures and20 failure/recovery pairs.
All73 retirement tickets collect after diagnostic GC outside the author stack.

Normal sessions consume96 dispatches. Terminal execution stops at8192;
finite cleanup consumes38 dispatches and infinite cleanup stops at4096.
Same-process fresh sessions recover with reset static state and matching resource
release observations. Counts are from the actual native ledger and rows, not
copied from another platform. Author finalizers are not enabled as a production
API by this experiment.

## Identity And Independent Review

The source is commit2d86588f8cef4b3c48ce2ba4d4af15ad7bc83e7c,
tree3292fc9acf3c15632f3bde34f675caec44f399e2. Build/source/native/app receipts
bind the new64-byte/align8 meter and matching CoreLib/compiler products.
Mac-side byte comparison matches eighteen unsigned/signed native code/data
sections and UUIDd6e785aee19b39c9880c9df150591972. The200 installed bundle files
and two author DLLs retain their before/after hashes.

The504533-byte ZIP has SHA256
0fff981e48ec1d1e94364532b82351ec3c7d1ca101ec4f0c3517acd618e289c5:
132 hash/size-covered files plus the manifest. The
[root receipt review](../artifacts/mobile-derived-ledger/root-followup-review-20261014-attempt1/results.json)
reconciles actual local ZIP/member bytes, the original build receipt, source37,
raw run/transport/process records and installed identities. Native product
binaries remain remote; root does not claim local machine-code analysis.
The [root business-row recheck](../artifacts/mobile-derived-ledger/root-followup-review-20261014-attempt1/ios-rows/results.json)
reruns the frozen original auditor against all73 rows and rejects15 altered
business receipts. The fresh Mac candidate assessor additionally rejects eight
binding changes; three preflight controls pass. The first assessor failed on a
missing original-input ZIP path; its failure remains archived. Correcting the
input path required only another audit, not an application rerun or runtime fix.

## Remaining Execution Evidence

Both phase-acquire-load and derived-ledger settings are configuredON before
runtime initialization. These settings and passing ledgers do not establish
that the new meter flag/optimized branch is observed live. The
[offline entry preparation](../artifacts/mobile-derived-ledger/ios-functional-receipts-20261014-attempt1/frozen/entry-preparation/results.json)
identifies source line3751 and file PC0x2f9efc with dispatch instruction
ldr w26, [x24] and frame/startIp load at x19+0x88. The oldw25 observer cannot
be reused without adapting and validating its new native contract. No debugger
or sampled application process was created by this preparation.

The [device refresh](../artifacts/mobile-derived-ledger/ios-functional-receipts-20261014-attempt1/frozen/device-readiness/results.json)
lists42 CoreDevice entries, including one physical iPad8,9 with developer mode
enabled and tunnel unavailable. DDI availability is unknown; no simulator is
booted at observation. No signing or physical application operations occurred.
See [physical-device prerequisites](ios-device-readiness.md).
