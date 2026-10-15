# iOS Device Application Build

On 2026-10-15, a matching unsigned iPhoneOS ARM64 application build completed
from a single launch on the configured Mac. It uses the accepted
[device framework](ios-device-batch-framework.md), private device CoreCLR and
the frozen 15-case/73-context budget harness. Physical execution remains
unperformed.

## Actual Build Route

The [application driver](../eng/ios-device-application-build.py) compiles a
fresh trusted `SessionBridge` against 181 raw framework components and four
frozen trusted harness assemblies. It generates a new 186-component device
composite using matching host crossgen2 with `--targetos:ios`. The native
UIKit wrapper and composite are linked using iphoneos/ARM64/minimum15.3.
Existing runtime/framework bytes are retained and checked before/after.

The native wrapper comes from matching frozen official Apple/CoreCLR source.
It retains TPA and the native-code-data host contract, replacing the executable
entry call with `coreclr_create_delegate` and a zero-argument integer delegate
to `SessionBridge.Run`. The bridge passes the app-owned Documents plugin and
fresh evidence paths, a 32-hex launch nonce and fixed `all` selection to
`MobileHostBudgetProbe.Entry.Run`. Compilation neither invokes that delegate
nor runs the test cases. The template exits without an explicit
`coreclr_shutdown` call; a future runtime receipt must preserve that distinction.

The pre-initialization profile selects phase-acquire-load and derived-ledger
with batch interval0, InterpMode0, InterpretCollectible0 and ReadyToRun1.
Those source settings do not establish execution of any method. Session-owned
required-interpreter policy and budgets remain the frozen harness's behavior.

The bundle contains trusted framework/harness components and device dylibs,
with no author DLLs, compiler, signing or installation. Actual output checks
require `MH_EXECUTE` for the main, `MH_DYLIB` for native libraries, device
platform2, compatible OS minima, resolved private dylib dependencies and no
`LC_CODE_SIGNATURE`.

## Launch And Review

The frozen driver SHA256 is
`c86af795e75cc810ac949a3ff31269465cd7f34665f798f5c1c168a866c5c15d`.
The durable single-launch receipt is
`D:/RuneCLR-Android/device-build/application-build-handoff-20261015-attempt1/launch.json`;
supervisor PID47556 owns
`ios-device-application-20261015-attempt1` and its separate supervisor directory.
Read its completion receipt before any continuation; a launch is not a
successful application build. Each build stage retains argv/PID/stdout/stderr
and exit status. Owned process groups are retired on timeout before stream
hashing. No runtime rebuild, signing or device operation was requested.

Independent output review must bind the complete relative app inventory to the
actual build-result hash, parse raw/R2R identities and method metadata, check
private CoreLib ABI and device native dependencies, and retain all original
streams. The current build/review outcome is recorded in the handoff.

Actual bridge/crossgen/composite-link/wrapper stages all exit0 with empty
stderr. Build completion is `2026-10-14T20:05:22Z`; the original result SHA256
is `e437a2f78ae3a8433e5c63123f998b3032a1380f6c8afd0ca7d894191d215507`.
The main and composite declare minimum15.3. All eleven native binaries
(main plus ten dylibs) are device ARM64 and contain no signature command.

The complete app is retained at
`D:/RuneCLR-Android/device-build/ios-device-application-receipts-20261015-attempt1/extracted/ios-device-application-20261015-attempt1/app/Session.app`.
Its archive SHA256 is
`ae46ad84b17b7d11df85f14083f64ccbcbbcc78ff50ebb3a1275857d2c6abdd9`;
435 payloads and 436 exact ZIP members pass size/hash checks.
The [independent review tool](../eng/ios-device-application-review.py) passes
at `D:/RuneCLR-Android/device-build/ios-device-application-independent-review-20261015-attempt1/actual-review-attempt2/results.json`
(SHA256 `b1a4d379aac39a99a25cb986df71ce29d28214f6cb2a8a50c562bd580a761dab`).
It matches all199 app files, all186 raw/R2R assembly identities/MVIDs, complete
metadata, IL/EH bodies and initialized field bytes,52 private CoreLib ABI
entries, device-library hashes and resolved dependencies. The first checker
mistakenly classified an official CompilerServices assembly as a compiler;
that failed review is preserved, the exact-tool-name guard is corrected, and
the application bytes are unchanged.

All owned build/transfer processes have exited. The stage timeout fix also
passes an actual child-process timeout/termination control; its receipt is
`D:/RuneCLR-Android/device-build/application-build-handoff-20261015-attempt1/timeout-control.json`.

## Post-Build Author Preparation

After successful independent application review, run the
[fresh author compiler](../eng/prepare-ios-device-author.py) in `prepare` phase
against the actual downloaded unsigned `.app`. The
[post-build binding review](../eng/verify-ios-device-author-binding.py) checks
that its complete app inventory equals the independent review and pre-compile
request, that build completion precedes both real compiler processes, and that
fixed source/reference/compiler identities, raw process streams and actual
IL-only output identities match. It does not install or execute author IL.

This actual sequence now passes: two real compiler processes produce fresh
IL-only DLLs at
`D:/RuneCLR-Android/device-build/post-device-app-author-20261015-attempt1/`.
The binding review passes at
`D:/RuneCLR-Android/device-build/post-device-app-author-review-20261015-attempt1/review.json`,
including all199 unchanged app files and build/compile ordering. Three
synthetic corruption controls reject changed app inventories, compilation
predating build completion and an unbound build receipt. The same fresh IL
also passes20 stock Windows Normal sessions/20 collections with reset statics,
three ticks and released resources. Normal declares the private dependency
without invoking its Helper; this is finite desktop control evidence. Receipts
are retained in `post-device-app-author-binding-controls-20261015-attempt1` and
`post-device-app-author-stock-control-20261015-attempt1` under the same D root.

The [offline physical run preflight](../eng/ios-device-run-preflight.py) then
creates a separate fresh-author manifest and Documents/nonce/child-receipt
plan. It rejects an unbound desktop `sanity` result. Existing simulator tools
and their old author hashes cannot establish physical-device transport for
these fresh DLLs. Reachable device/signing, installed host provenance,
post-install delivery/readback, actual entries and lifecycle recovery remain
the [physical acceptance prerequisites](ios-device-readiness.md).

The actual offline run plan now passes at
`D:/RuneCLR-Android/device-build/device-run-plan-20261015-attempt1/`, with a
separate fresh-author manifest, all15 scenarios/73 contexts, independently
recomputed child nonces and matching native/managed source contracts. The
actual seven help-only `devicectl` queries are retained at
`D:/RuneCLR-Android/device-build/devicectl-help-20261015-attempt1/`; their plan
confirms appDataContainer/bundle-ID copy arguments, JSON launch environment,
console/file-output constraints, timeout and installation/launch synchronization
flags. Help and offline planning do not prove device transport.

The next experiment needs a reachable physical target and a matching project
development profile, then signing provenance, installation, post-install IL
delivery/readback, fixed lifecycle/budget recovery and actual interpreter
method entries. No physical device application was signed, installed or run
by this build/preparation increment.

## Offline Lifecycle Result Auditor

The [device result auditor](../eng/ios-device-result-audit.py) reuses the frozen
15-case/73-context row rules without the simulator/Android transport gate or
its historical author hashes. Optional `--plan` matches ordered scenarios,
child nonces/receipt paths/counts, native launch environment, Documents paths
and managed entry arguments to the planned launch. It reports lifecycle
semantics only: physical-device, installed-host, delivered-author identity and
interpreter-entry flags remain false even when the rows pass.

On 2026-10-15, an actual Mac offline replay uses the preserved nondebugger iOS
simulator receipts from
`ios-budget-increment-acceptance-20261014-attempt1-functional/adapter-evidence`,
nonce `05fa545c32694a79b2df063e4593fcd1`, PID27973. All15 cases/73 contexts and
13 altered-row controls pass. The actual new physical-run plan rejects this
historical nonce. A clearly synthetic matching historical plan then passes
all19 controls, including six plan-binding changes. Original aggregate/child
receipt hashes remain unchanged. This exercises the new tool against actual
historical rows; it adds no physical execution or fresh-author execution claim.

Commands, raw streams, exit codes, unchanged hashes and separate reports are
retained on the configured Mac at
`/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/ios-device-result-offline-review-20261015-attempt1/`.
The review SHA256 is
`d45e7cd6440c3422489f4108e3021a18d66090982c2e78fbdbedb556934656c2`.
All18 report/source/stream files are also downloaded and hash-verified at
`D:/RuneCLR-Android/device-build/ios-device-result-offline-review-20261015-attempt1/`.
The tested driver SHA256 is
`7c85064e47d47522a9d0f48db2a4c6486b96faf946ee301d2fb490388a3b4c3a`,
identical to the current repository file.

```powershell
py -3 -B eng/ios-device-result-audit.py --evidence <original-receipts> --nonce <actual-launch-nonce> --pid <actual-pid> --output <fresh-review-directory> --plan <frozen-plan.json> --selftest
```

Receipt content alone cannot prove that the planned device launch occurred;
transport, installation/delivery/readback and native-entry evidence remain
separate prerequisites.

## Scene Lifecycle Follow-Up

A new matching simulator application on 2026-10-15 reused this builder's
minimal custom UIKit `main.m`. Its first launch on iOS27 crashed before
CoreCLR initialization: PID51048, bundle
`org.runeclr.freshauthor.c8f2430e483a`, crash
`Session-2026-10-15-045803.ips`. The crash is bound to that bundle's native
UUID and the UIKit
`___UIApplicationEvaluateRuntimeIssueForNoSceneLifecycleAdoption_block_invoke`
frame. Launch-tool exit0 did not establish application success, and no managed
budget evidence was emitted. This is our application-fixture entry bug.

The unsigned device application above uses the same minimal main and needs
a scene-aware wrapper continuation before future iOS27 device acceptance.
Its completed static metadata review remains valid within that scope; no
physical-device crash has been observed. Preserve the frozen builder, unsigned
app, original author pair and physical run plan. The simulator repair uses a
separate output and the historically accepted scene delegate source SHA256
`c49f3cd9050f5d6fcbf73b92996e8b3a1c291a7ec0fc7e3d44b4be722f3c670a`,
and the scene manifest/new bundle identity. The failed simulator already has
the minimal manifest, but its main lacks a scene delegate and connection
configuration. The device plist separately needs the manifest added.
Only the simulator main executable, plist and
simulator signatures change; runtime and186 R2R component bytes are retained.
The device continuation requires its own review and fresh binding.

After the repaired simulator's actual normal15/73 run, the separate
[device scene continuation](../eng/ios-device-scene-continuation.py) now passes
source preflight and eight synthetic in-memory rejection controls, then
completes one actual unsigned iphoneos/ARM64/min15.3 wrapper compile/link
with exit0. Its gate reads the actual simulator rows, six native markers,
launch streams and unchanged installed hashes before permitting device relink.
The new private output is `ios-device-scene-continuation-20261015-attempt1`
on the configured Mac. Only `Session` and `Info.plist` change;197 other files,
186 R2R components, ten native dylibs and trusted wrapper/bridge sources
remain byte-identical. The bundle inventory SHA256 is
`2d89013d354648217b0cd5efd8ce384bebe6baee2b00eed85c318d6cb07f89b1`.

This child remains unsigned, with no signature load command and no physical
installation or execution. At the small-review stage, full independent
child-bundle review and fresh author binding are still pending; the later
complete acceptance is recorded below. The old199-file author review/physical plan
belongs to the original bundle and cannot be reused as proof for this child.
Small receipts and the actual new executable/plist are downloaded to
`D:/RuneCLR-Android/device-build/ios-device-scene-continuation-20261015-attempt1`.
The48-member/164118-byte archive SHA256 is
`910eae07ff655ca79774a76defb662d157a203acf97c7c8f6e0d1daca0bad7d1`;
the actual child result SHA256 is
`38180dfc40749b4b036ad1092138ae4e4477dfcb3969de930156f87db08830a6`.
Its separate small-receipt review parses the actual new executable as
device ARM64 `MH_EXECUTE`, platform2/min15.3, with no signature command.
The197 protected files are checked through bound inventories in this review;
the complete new application is not downloaded or independently byte-reviewed.
That statement describes the earlier small review. The later
[complete child acceptance](ios-device-scene-acceptance.md) now downloads all199
files and independently checks197 protected bytes,186 canonical raw/R2R
metadata/IL/EH/field pairs, all eleven unsigned device native images and twelve
alteration controls. It also binds a separately compiled new author pair to
the child, with nine copied-receipt rejection controls. No physical execution
or post-install device delivery is claimed.

The [offline device entry preparation](ios-device-entry-preparation.md)
separately binds the actual device native image and DWARF to nine requested
author method groups. It adds no device execution evidence.
