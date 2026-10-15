# iOS Device Scene Child Static Acceptance

On 2026-10-15, the complete unsigned scene-aware device application passes
independent static review, followed by new fixed-source author IL compilation
and binding to its actual199 files. Physical execution remains unperformed.
The [original application and separate scene relink](ios-device-application-build.md)
remain frozen; this increment neither rebuilds nor signs them.

## Complete Artifact And Independent Review

The full child is downloaded from the configured Mac into
`D:/RuneCLR-Android/device-build/ios-device-scene-full-receipts-20261015-attempt1/extracted/ios-device-scene-continuation-20261015-attempt1`.
Its archive contains244 members/243 payload files,49071022 bytes, SHA256
`f9a9815838340b639d11f25ee021d4110bbc3bdddbf8d5b7bde2cdefd8987aff`.
Every extracted payload passes size/hash checks. The one-shot artifact service
completes one GET with zero failures and exits.

The [independent scene child reviewer](../eng/review-ios-device-scene-continuation.py)
passes at
`D:/RuneCLR-Android/device-build/ios-device-scene-full-independent-review-20261015-attempt3/results.json`,
SHA256 `c82c7067b27033a23dcbf6bc4cea95196fc7b7d030968e1fb3510f2f39aa3ded`.
It reads the complete actual bundle, not just the earlier small receipt archive:

- All199 filenames/hashes match the actual child inventory. Only `Session`
  and `Info.plist` differ from the accepted parent; all197 other files compare
  byte-for-byte against the complete downloaded parent.
- All186 raw/R2R canonical metadata, method IL/EH and initialized fields match.
  Ten original dylibs remain unchanged; the executable and all eleven native
  images meet device ARM64/platform2/minimum15.3/unsigned requirements.
- The accepted scene main, plist-only manifest addition, retained wrapper and
  bridge sources, parent provenance and native profile match.
- The actual successful simulator15/73 gate precedes the sole device wrapper
  compile/link. Its master command, argv/PID, raw streams and exit0 are bound.
- Twelve copied/in-memory alteration controls reject changed native/managed
  bytes, added authors, missing components, scene/target/gate changes and
  promotion of static evidence to physical execution.

The final reviewer SHA256 is
`ef12e9420d992d101ab609004121a828f5a6ab8ee980dcb46c83bf1e27f2e0e4`.
Its source and result are frozen in the passing review directory. The two
earlier reviewer failures remain preserved: the first assumed an optional
small-archive plist snapshot was present, and the second compared different
native parser field schemas. The corrected review reads actual parent/child
plists and native data; no application rebuild was needed.

## New Child-Bound Author IL

After complete review, the frozen [author compiler](../eng/prepare-ios-device-author.py)
executes two real Roslyn processes against the actual unsigned child. Source
binding is `2026-10-14T21:26:05.128549+00:00`, after the wrapper completed at
`2026-10-14T21:13:24Z`. Both compiler processes exit0 in order.
Outputs and exact source/reference/response/process records are retained at
`D:/RuneCLR-Android/device-build/post-device-scene-author-20261015-attempt1`.

| Assembly | SHA256 | MVID |
| --- | --- | --- |
| Payload | `f58acca95bb456bf2e89f5104bcea742ddf99c986d719195c0081e4dec80cb24` | `0e87971d-759f-4da1-951f-996068426032` |
| Private | `4053e4b1562e9d0a5a246926c879f90636099fb7684101fcf3ed3b6af30992be` | `063bbca8-8f44-4f72-bd94-381c9709e4b5` |

The new [scene author binding reviewer](../eng/verify-ios-scene-author-binding.py)
passes all199 app files, actual wrapper completion/streams, ordered compiler
processes, complete response arguments, fixed references/compiler/source and
fresh nonce/hash/MVID/IL-only outputs. The raw compilation contract is bound
to the independently compared R2R host contract; their whole-file hashes
differ by design. The original binding tool and original author pair remain
unchanged. This pair is not a post-install compilation or delivery claim.

The actual review is
`D:/RuneCLR-Android/device-build/post-device-scene-author-binding-review-20261015-attempt1/review.json`,
SHA256 `4a976973c2f2dc76d652221eed9b4a36b5609d1348a2dde48a973d47348d342f`.
The [copied-receipt controls](../eng/verify-ios-scene-author-binding-controls.py)
pass nine rejection cases at
`D:/RuneCLR-Android/device-build/post-device-scene-author-binding-controls-20261015-attempt1/results.json`:
stale parent/inventory/time reviews, changed stream, failed/timed-out wrapper,
wrong approved review digest, original-host author replay and current-pair
replay. Original inputs are unchanged; no target code executes in these controls.

## Physical Gates

The latest [read-only readiness refresh](ios-device-readiness.md) at
`2026-10-14T21:24:39.158592+00:00` still reports zero reachable physical targets
and zero bundle/device/development-identity profile intersections. The cached
paired device has developer mode enabled, but its tunnel is unavailable and
DDI services are unknown. No profile, pairing, setting or signing operation
was performed.

Update the physical run/observer plan for this new app and pair before use.
The original app's run plan and fixed author identities cannot establish
delivery or method entries for this child. Physical acceptance still requires
reachable device/profile, signed-to-installed host identity, IL compiled and
delivered after installation, actual loaded method entries, lifecycle/budget
recovery and completed retirement. Static device acceptance and the independent
[fresh-author simulator run](ios-fresh-author-simulator.md) remain distinct.
