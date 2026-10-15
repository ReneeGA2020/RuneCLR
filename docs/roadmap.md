# Roadmap

RuneCLR first makes **C# usable for iOS hot updates**, then adds **UGC
management** on the same runtime foundation. The [product direction](product-direction.md)
records this priority; [Roadmap #11](https://github.com/ReneeGA2020/RuneCLR/issues/11)
is the live tracker. Milestones express capabilities, not release dates.

## Shared foundation

| Issue | Deliverable | Recorded status |
| --- | --- | --- |
| [#1](https://github.com/ReneeGA2020/RuneCLR/issues/1) | Reproducible CoreCLR interpreter execution and lifecycle | Closed; desktop acceptance completed and merged into main |
| [#2](https://github.com/ReneeGA2020/RuneCLR/issues/2) | Post-publication IL and repeated retirement on physical iOS | Open; ARM64 simulator evidence exists, device execution remains pending |
| [#3](https://github.com/ReneeGA2020/RuneCLR/issues/3) | Startup, callbacks, host interaction and memory measurements | Desktop and mobile simulator/emulator experiments recorded; representative game/device envelope remains open |
| [#4](https://github.com/ReneeGA2020/RuneCLR/issues/4) | Controlled UGC source/IL packages and version compatibility | Local compiler/intake/player implemented; authenticated approval/distribution remains open |
| [#8](https://github.com/ReneeGA2020/RuneCLR/issues/8) | Host-driven callbacks, events, timers and resource ownership | Pumped Start/Tick/Stop implemented; richer events/resources remain open |

The current versioned loader uses restricted `managed-il-gameplay-v1`; #4 does
not yet provide a general trusted-update profile. Shared loading, diagnostics,
compatibility and lifecycle components can serve both uses. Existing `Map` names
are prototype terminology, not a restriction to maps.

## First application: developer-owned C# hot updates

| Issue | Deliverable | Acceptance focus |
| --- | --- | --- |
| [#12](https://github.com/ReneeGA2020/RuneCLR/issues/12) | Engine-independent iOS hot-update integration | Post-build IL, pinned host/runtime build, approved version activation, rollback and recovery |
| [#13](https://github.com/ReneeGA2020/RuneCLR/issues/13) | Same-source interpreted IL and trusted R2R builds | Identical business sources/shared APIs, actual execution evidence and matching behavior |
| [#14](https://github.com/ReneeGA2020/RuneCLR/issues/14) | Direct-object interoperability and ownership contract | Reference identity, calls, generic/delegate cases, release and retirement |
| [#15](https://github.com/ReneeGA2020/RuneCLR/issues/15) | C#/.NET compatibility matrix and useful diagnostics | Separate compiler, runtime, framework and UGC-policy support |

These are planned acceptance milestones. Start a minimal #12 integration while
#13/#14/#15 establish its build, interop and compatibility contracts. Run #2 when
a real device is available; device preparation must not block independent work.
Then validate the trusted-update stage of [game pilot #9](https://github.com/ReneeGA2020/RuneCLR/issues/9).
The [work sequence](work-sequence.md) gives the contribution order.

Trusted integration does not depend on completing public-UGC isolation or hard
CPU/memory limits. On iOS, new IL is interpreted; trusted R2R is built into the
application through its native build/signing pipeline. #13 is not a downloaded
native-code route or an expansion of restricted UGC execution.

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
