# Roadmap

## Current Performance Milestone (2026-10-19)

See the [published performance results](performance-results-20261018.md) for
accepted descriptive coverage and the bounded iOS native-entry comparison. Next:
callback-scoped time limits, then a matched OFF/ON validation; this publication
does not implement enforcement or close physical-device/execution-mode gaps.

RuneCLR first makes **C# usable for iOS hot updates**, then adds **UGC
management** on the same runtime foundation. The [product direction](product-direction.md)
records this priority; [Roadmap #11](https://github.com/ReneeGA2020/RuneCLR/issues/11)
is the live tracker. Milestones express capabilities, not release dates.

## Shared foundation

| Issue | Deliverable | Recorded status |
| --- | --- | --- |
| [#1](https://github.com/ReneeGA2020/RuneCLR/issues/1) | Reproducible CoreCLR interpreter execution and lifecycle | Closed; desktop acceptance completed and merged into main |
| [#2](https://github.com/ReneeGA2020/RuneCLR/issues/2) | Post-publication IL and repeated retirement on physical iOS | Open; ARM64 simulator evidence exists, device execution remains pending |
| [#3](https://github.com/ReneeGA2020/RuneCLR/issues/3) | Startup, callbacks, host interaction and memory measurements | Four-platform descriptive coverage complete: Windows336 + Mac336 + Android168 + iOS168 warm samples;105 child first-use intervals,6 separate Windows parent windows and480 functional rows. Original report (archival/local evidence: `../artifacts/four-platform-descriptive-performance-20261018/REPORT.md`) retained separately. New25group access/collections/override-dispatch extension has scoped Lead acceptance (archival/local evidence: `../artifacts/lead-access-collections-acceptance-20261018/ACCEPTANCE.md`):22 products,3150 formal samples,1350 warmups,100 untimed checks and704 original-gate rows in six separate request lanes; extension report (archival/local evidence: `../artifacts/access-collections-performance-bocx5e-20261018/REPORT.md`) and exact statistics (archival/local evidence: `../artifacts/access-collections-performance-bocx5e-20261018/reporting-r3/statistics.json`). Formal [execution-mode baseline and declared limits](four-platform-baseline.md) stay open; no numerical mode/causal inference; normal output append permitted, historical iOS broad-gate failure retained; devices skipped |
| [#4](https://github.com/ReneeGA2020/RuneCLR/issues/4) | Controlled UGC source/IL packages and version compatibility | Local compiler/intake/player implemented; authenticated approval/distribution remains open |
| [#8](https://github.com/ReneeGA2020/RuneCLR/issues/8) | Host-driven callbacks, events, timers and resource ownership | Pumped Start/Tick/Stop implemented; a callback-scoped map signal closes on return. A primitive tick schedule is taken on a later host tick and dropped on stop. Entity, log, and Charge calls require an open callback, and stop still releases those entities. The host can copy live entity ids and names between callbacks and can complete or fail primitive work between callbacks without retaining an exception. Wall-clock timers remain outside the session |

The subsequent same25-workload iOS simulator R2R comparison (archival/local evidence: `../artifacts/lead-ios-r2r-comparison-acceptance-20261018/ACCEPTANCE.md`)
accepts four native method-entry observations and a same-machine R2R/IL
package pair:9 apps,1050 formal observations and450 warmups. Descriptive median
ratios span7.82-204.81; composite optimization/layout/loading differ. This
increment does not close independent downloaded R2R, devices or all-method
execution qualification. Original four-platform results remain separate.

The current versioned loader uses restricted `managed-il-gameplay-v1`; #4 does
not yet provide a general trusted-update profile. Shared loading, diagnostics,
compatibility and lifecycle components can serve both uses. Existing `Map` names
are prototype terminology, not a restriction to maps.

## First application: developer-owned C# hot updates

| Issue | Deliverable | Acceptance focus |
| --- | --- | --- |
| [#12](https://github.com/ReneeGA2020/RuneCLR/issues/12) | Engine-independent iOS hot-update integration | Download/load trusted R2R updates, interpreter support, approved activation, rollback and recovery; platform delivery evidence |
| [#13](https://github.com/ReneeGA2020/RuneCLR/issues/13) | Same-source interpreted IL and trusted R2R builds | Identical business sources/shared APIs, separately built R2R module composition, actual execution evidence and matching behavior |
| [#14](https://github.com/ReneeGA2020/RuneCLR/issues/14) | Direct-object interoperability and ownership contract | Reference identity, calls, generic/delegate cases, release and retirement |
| [#15](https://github.com/ReneeGA2020/RuneCLR/issues/15) | C#/.NET compatibility matrix and useful diagnostics | Separate compiler, runtime, framework and UGC-policy support |

These are planned acceptance milestones. Start a minimal #12 integration while
#13/#14/#15 establish its build, interop and compatibility contracts. Run #2 when
a real device is available; device preparation must not block independent work.
Then validate the trusted-update stage of [game pilot #9](https://github.com/ReneeGA2020/RuneCLR/issues/9).
The [work sequence](work-sequence.md) gives the contribution order.
The [desktop signed-delivery example](trusted-update-delivery-sample.md) now
verifies and stages a complete signed payload before entry activation. Its
Windows startup/staging checks and macOS signature, staging and host checks are recorded in the
[handoff](development.md). A local-file-stream prototype now stages, starts
and automatically recovers a signed release across process restarts in the
lead's Windows checks and the accepted macOS arm64 snapshot. External network transport,
rollback policy and physical iOS delivery acceptance remain open under #12.
The Windows x64 [signed composition driver](trusted-composition-delivery-native.md)
now executes independently built R2R updates and private dependencies through
signed staging and next-process recovery. The lead reran both native-positive
and ReadyToRun-disabled controls and audited actual method PCs, final payload
hashes, helper interpreter entries and shared-object behavior. This desktop
acceptance does not establish the iOS delivery path.

The [typed session experiments](trusted-embedding-next.md) separately accept
canonical repeated native calls and score-specific native game rounds on
Windows x64, plus same-version successive rounds on stock desktop IL. Rounds
retain selected code/statics while creating new instances. Post-seal
changed-update validation now has scoped offline acceptance; no new native run
is credited to that checker repair. The two-game contract integration has
passed its stock-IL gate. Its distinct desktop native experiment has delivered
eight honest exit-0 processes, but independent review rejects native bindings:
18 armed attempts produce no targeted frames. Final Host parity now returns
unsupported FieldRVA signature; both modules match. The delivered checker still
rejects full per-call scope coverage, and a lead synthetic probe finds missing
PC/base/RVA consistency checking. Orca Workers continue review and mapping
diagnosis. The loopback HTTP download/staging implementation now has joined
scoped acceptance for nine independently reproduced deadline-enabled lanes and
the same final Host's stock 17/10 baseline. Separately, a lead
stock-.NET diagnostic measures that ResponseHeadersRead body reads outlive
HttpClient.Timeout and terminate with an explicit body-spanning deadline;
that framework diagnostic is separate from HTTP-adapter acceptance. Current evidence is linked from the
[compatibility matrix](compatibility-matrix.md). These results do not establish
same-process version switching or close #12 or #13.

Different business versions now have a separate
desktop loopback acceptance (archival/local evidence: `../artifacts/lead-distinct-http-acceptance-20261018ez/receipt.json`)
on Host e5c00853. Independently compiled signed A/B modules produce Host state
0/3/6 and 0/5/10. Original and independent five-process runs cover selection,
server-free recovery, tampered-B fallback to A and fresh-process B selection;
same-process B is rejected by the existing gate. This advances trusted delivery
at process boundaries without establishing same-process replacement or native
execution. Prelaunch/full-Host-seal evidence is a separate repair task. The
artifact remains outside the SDK; external networking/TLS and physical iOS
packaging, loading and execution remain open.

Trusted integration does not depend on completing public-UGC isolation or hard
CPU/memory limits. A first-party update module is trusted and can use its own
R2R build alongside other R2R modules. The first-party direction is downloadable
R2R updates with interpreter support. #13 validates independent R2R builds,
composition and actual method execution; #12 owns post-install delivery and
platform packaging/signing/loading acceptance. Existing post-install IL evidence
does not establish downloaded R2R native execution on iOS. These milestones do
not expand restricted UGC execution.
On the 2026-10-16 measured desktop result, RuneCLR does not pursue unloadable hot-update R2R: an update that must be unloaded stays interpreted, and ordinary first-party execution does not repeatedly unload old assemblies.

Gate: a developer can integrate C# updates, use supported host objects, change
versions at declared boundaries and recover from ordinary update failures, with
physical evidence before claiming iOS device support.

## Second application: managed C# UGC

| Issue | Deliverable | Remaining gate |
| --- | --- | --- |
| [#5](https://github.com/ReneeGA2020/RuneCLR/issues/5) | Capability/dependency policy and interpreter selection | Complete the declared supported execution surface and remaining call/platform boundaries |
| [#6](https://github.com/ReneeGA2020/RuneCLR/issues/6) | Native interpreted budgets and terminal interruption | Stable contract, remaining interruption/host-call boundaries and matching mobile combinations |
| [#7](https://github.com/ReneeGA2020/RuneCLR/issues/7) | Allocation attribution and practical memory policy | Distinguish allocation volume, retained/shared memory and any feasible limit |
| [#8](https://github.com/ReneeGA2020/RuneCLR/issues/8) | Managed scheduling/resources | Events, timers, subscriptions and cleanup ownership |
| [#9](https://github.com/ReneeGA2020/RuneCLR/issues/9) | Real game pilot | Trusted-update stage first, then controlled-author UGC with explicit prerequisites |
| [#10](https://github.com/ReneeGA2020/RuneCLR/issues/10) | Public UGC readiness | Threat model, abuse coverage, distribution and runtime maintenance decision |

The [UGC execution strategy](execution-strategy.md) starts with interpreted
author code/private dependencies across target platforms. Authors submit source
or IL; controlled builds create runnable packages. Trusted host/framework R2R
remains allowed. Later native UGC needs equivalent restrictions and is separate
from trusted same-source builds.

The current IMapContext entity surface is a prototype host. A game does not need entities to use the UGC mechanism. The mechanism is script loading, capability limits, execution, and unload. The desktop score-game sample runs a shared host contract. See score-game.md. On 2026-10-17 its decided shape is a game-owned shared CLR interface called directly by the script. IMapContext is not renamed. See the product direction.

Current UGC evidence includes [controlled packaging](controlled-packaging.md),
[capability policy](capability-policy.md), [required interpretation](session-execution-policy.md),
[Windows controlled-package pumped budgets](controlled-package-native-budget.md)
(33/33 groups) and the separate [updated iOS simulator diagnostic application](ios-pumped-budget-acceptance.md)
(16 scenarios / 74 collected contexts). These results do not close physical-device,
public-hostile-code or hard-memory-isolation milestones.

Gate: declared author mistakes do not leave the host stuck or retaining old
sessions; public-author acceptance additionally requires #10's readiness decision.

## Evidence and scope

See the [development handoff](development.md) for current results and the
[upstream defect register](upstream-bugs/README.md) for Microsoft-runtime fixes.
Keep historical experiment reports configuration-specific; do not reinterpret
simulator evidence as device execution or compiler success as feature support.

Initial hot updates can switch at module/session boundaries. Active-stack
replacement, automatic live-state migration, deterministic lockstep, full
.NET/arbitrary NuGet compatibility and a security guarantee from the prototype
are outside the current commitment. Server-authoritative gameplay belongs to
the existing examples/UGC pilot, not every host.
