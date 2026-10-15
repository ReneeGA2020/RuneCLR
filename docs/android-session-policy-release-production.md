# Android Release production and recovery acceptance

The [Release functional driver](../eng/android-session-policy-release-accept.py)
extends the [independent normal selection lane](android-session-policy-release-functional.md)
with production, failure-recovery and ordinary-selection controls. The current
frozen APK uses candidate `1724cdec553a7aff7a373a271a4be612651c7625`; no new APK,
payload production or device installation is needed for these lanes. The
Checked driver and its actual-bytecode gate remain unchanged. Release checks
do not require Debug-only interpreter dumps and do not claim method-entry
observations for production methods.

The new driver accepts `run --lane all|required|required-refusal|ordinary|unmarked-fallback`.
Its default is still `required`; the earlier actual normal Release run is
reassessed offline rather than rerun. Each requested lane needs its own fresh
output, nonce and one instrumentation launch. Example:

```powershell
py -3 -B eng/android-session-policy-release-accept.py run `
  --evidence artifacts/android-session-policy/20261013-release-entry-apk-attempt1 `
  --serial emulator-5556 --adb <absolute-adb.exe> --lane all `
  --output artifacts/android-session-policy/<fresh-all-lane>
```

All lanes retain APK and 246 installed file identities before and after,
matching product/source/CoreLib receipts, post-install author-production
chronology, Java/native/managed PID and nonce agreement, native mapped-image
identity, actual live TracerPid zero, no owned debugger servers or forwards,
exact zero native HRESULT/exit and instrumentation completion, and every
required original raw hash. No lane supplies the native-entry gate opt-in.
Global collectible diagnostic mode remains zero. Global interpreter mode is
zero except the unmarked-fallback control, where it is one to make the actual
compiler refusal attempt possible.

| Lane | Required functional observations | Native JIT diagnostic control |
| --- | --- | --- |
| all | Exact ordered 24 lifecycle labels and 15 package labels; three hello/arena/hello sample contexts complete three ticks, reset hello starts to one, release all entities and collect; three production policy acknowledgements | Trusted MapRunner and default-context dependency seed positive; targeted map and package helper owners absent |
| required | Twenty exact seventeen-field results and collections; 260 required queries, twenty retired guards | Trusted contract positive; targeted SelectionUGC owners absent |
| required-refusal | Actual scoped CORJIT_SKIPPED marker; NotSupportedException, refusal-context collection and retirement; then twenty normal recovery sessions, 260 recovery queries and twenty more retired guards | Trusted contract positive; refused method and recovery author owners absent |
| ordinary | Same twenty values and collections; 260 ordinary policy-zero queries and twenty retired guards | Ordinary author native JIT positive |
| unmarked-fallback | Same exact refusal body returns 73 after actual CORJIT_SKIPPED injection, MethodDef 06000001 | Refusal body native JIT positive |

The refusal operator setting selects only
`SelectionProbe.Refusal` / `SelectionUGC.Refusal.Entry:Reject`; it injects a
real compiler SKIPPED result before bytecode emission. This tests required
policy rejection and ordinary fallback, rather than establishing a natural
unsupported-IL case. The refused context has its own policy queries before
the refusal PASS line; recovery queries are counted separately. Retired
guards total twenty-one. Ordinary/fallback payloads remain unmarked even
though the wrapper creates a separate required context for capability
preflight.

The final lifecycle test intentionally invokes a default-context
`RuneCLR.PrivateDependency.PrivateState<int>.Start` native body to seed a
same-name collision. This is a trusted control. The required private helper
with the same type name must still produce fresh declared-package statics.
JIT summaries alone do not distinguish these two owners; this lane does not
generalize targeted author-JIT absence into a full owner-level native-entry
proof.

Failures preserve original logs and receipts. There is no automatic app
retry or lane repetition; independent lanes may be reviewed separately.
Functional acceptance deliberately leaves `entryProofCollected` and
`platformAccepted` false.

The actual frozen run driver SHA256 is
`9a15660ef0df03ab48fe4c1df4c2a168d843f57a828923bc62c02753f0092a27`.
The [offline review](../artifacts/android-session-policy/release-production-parser-review-b5decdf3a1444955a291be98cd1efafb/results.json)
passes the original normal Release required evidence, checks parser
compatibility against four actual earlier Checked lanes, and rejects five
content mutations: a missing lifecycle PASS, an incorrect sample static, a
missing production acknowledgement, missing compiler SKIPPED, and native
JIT of the refused author. This review performed no device commands or app
reruns. Old Checked raw is not new Release execution evidence.

Actual Release results on 2026-10-13:

| Lane | Original assessment | PID / nonce | Observed result |
| --- | --- | --- | --- |
| all | [Original raw assessment](../artifacts/android-session-policy/release-production-runner-344a0b3cf1774f28b95fea9186db89bb/run-all/assessment.json) | 3358 / be85cf9de22b45c7ac0aaa692d3cbc0f | 24 lifecycle + 15 packages + 3 sample collections; 246 installed hashes before/after; 30 original raw hashes; 9 TracerPid-zero samples |
| required-refusal | [Original raw assessment](../artifacts/android-session-policy/release-production-runner-344a0b3cf1774f28b95fea9186db89bb/run-required-refusal/assessment.json) | 3999 / f458b4b55a544bda852ffc8caf882852 | Actual compiler SKIPPED and NotSupportedException; refused context collected, 5 refusal queries; 20 recovery sessions/collections, 260 recovery queries, 21 total retired guards; 246 installed hashes; 26 original raw hashes; 5 TracerPid-zero samples |
| ordinary | [Original raw assessment](../artifacts/android-session-policy/release-production-runner-344a0b3cf1774f28b95fea9186db89bb/run-ordinary/assessment.json) | 4642 / fffefbb6dc5b4ca582e7455acb711dcb | 20 exact results and collections, 260 policy-zero queries, 20 retired guards; ordinary author JIT positive; 246 installed hashes; 25 original raw hashes; 4 TracerPid-zero samples |
| unmarked-fallback | [Original raw assessment](../artifacts/android-session-policy/release-production-runner-344a0b3cf1774f28b95fea9186db89bb/run-unmarked-fallback/assessment.json) | 5307 / 22cb3bed2e094fb88f8295a8203de28d | Mode one, actual compiler SKIPPED followed by value 73 and native Refusal body JIT; 246 installed hashes; 25 original raw hashes; 4 TracerPid-zero samples |

Current source adds three assessment checks after the frozen runs: actual
MapRunner Run JIT rather than accepting any MapRunner method, optional leading
dot in author JIT formatter output, and the exact distribution of all 260
session policy-query phases. Its SHA256 is
`850856116c7790d96a0cc12da18c86e05cc9ddd01dc41b561aa92965a2c51bc3`.
The [strict offline review](../artifacts/android-session-policy/release-production-strict-review-2584969172ac4b10814eae6377c2b887/results.json)
passes both original Release runs and rejects three SHA-rebound copies with
constructor-only MapRunner JIT, leading-dot author JIT, or a wrong query phase
while keeping the query count 260. No app was rerun for these checks, and the
actual frozen run source remains unchanged. A
[four-lane strict offline review](../artifacts/android-session-policy/release-production-four-review-d932b72a449e4c068c067a890e950398/results.json)
also passes all four original Release runs and binds each transport receipt.
The four actual runs have distinct PIDs and nonces and share unchanged APK,
runtime, player and post-install author fixtures. No production method-entry
capture or physical Android ARM64-device validation is claimed here.

The [independent peer audit](../artifacts/android-session-policy/release-independent-review-20261013/results.json)
checks all 106 original raw hashes, four distinct owned PIDs/nonces, 22 live
PID-bound TracerPid-zero samples, exact per-phase query counts, all ordered
production PASS labels and sample bodies. Ten semantic negative controls are
rejected without any device commands. The
[root source/raw binding verification](../artifacts/android-session-policy/release-production-runner-344a0b3cf1774f28b95fea9186db89bb/root-independent-verification.json)
also verifies all 74 frozen wrapper/generated source files, the APK, peer source
and receipt, and the separately reviewed thirteen budget source files. A regex
escaping error in the first root verifier was corrected offline; no app reran.
The [owned shutdown receipt](../artifacts/android-session-policy/release-production-runner-344a0b3cf1774f28b95fea9186db89bb/root-shutdown.json)
confirms app/debugger and owned forwards absent, emulator kill exit zero and
serial absent afterwards. Session instruction budgets remain
[proposed, not implemented](runtime-session-budget-plan.md).

The [production evidence archive](../artifacts/android-session-policy/release-production-20261013-344a0b3c.zip)
contains all four actual runs, original and strict tools, the four offline review
directories and negative copies, independent source/raw verification, bootstrap
and shutdown records, identity/source snapshots and budget-plan/source receipts.
Its [archive verification receipt](../artifacts/android-session-policy/release-production-20261013-344a0b3c.receipt.json)
passes exact membership, safe paths, member sizes/SHA256, CRC and unchanged
original-source checks: 243 files, 1,444,038 bytes, SHA256
0a3db3678ccae23dcac620923cb2a8935058fcdcf53fc0710814e43a35a5b99c.
The full matching APK/layout and the earlier entry/normal archives remain
separately retained and bound by identities. The documentation snapshot in this
archive precedes this archive-reference paragraph. Offline scripts retain their
original repository/input paths; the ZIP's manifest verifies archived bytes
without starting a device or resolving those external runtime paths.
