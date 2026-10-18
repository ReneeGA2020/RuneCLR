# Descriptive Performance Results - 2026-10-18

Published 2026-10-19. The project lead accepted the following experiment-scoped
measurements after delegated implementation, independent review and separate
passive integrity, semantic and arithmetic checks. This is a self-contained
record of conclusions, not a formal execution-mode-qualified baseline or a
portable performance guarantee. All figures below are measured, not estimates.

## Three Separate Experiments

| Experiment | Retained observations | Meaning |
| --- | --- | --- |
| Earlier warm / direct first use | 1008 formal warm samples; 105 child intervals; 6 additional Windows parent windows; 480 first-use functional rows | Eight warm scopes and seven direct first-use scopes; not the 25-group extension |
| Access / collections / dispatch extension | 22 apps/processes; 3150 formal samples; 1350 warmups; 100 untimed group checks; 704 original lifecycle-gate rows | 25 groups in six separate platform/request lanes |
| Later same-iOS R2R / IL pair | 9 apps: 1 diagnostic, 2 functional, 6 measured; 1050 formal samples; 450 warmups; 288 original gate rows | Same workload input IL, installed composite versus late pure IL on one simulator |

These datasets are distinct: do not add their distributions, relabel old
default-request measurements as R2R, or pool requests/platforms. Default and
selective-author are configuration requests, not execution proofs.

## Same-iOS Workload R2R / IL Comparison

Same Mac mini (Macmini9,1, Apple ARM64, 8 CPUs, 16 GiB), macOS 27.0.1
(26A434), Xcode 27.0 (27A266a), iPhone 16 ARM64 iOS 27.0 simulator.
Both packages use the same cached .NET 12 runtime/CoreLib input and unchanged
business IL. R2R includes Access.Workloads in an installed trusted composite;
the control loads the original pure-IL workload under the same no-JIT iOS
runtime. This is not downloaded independently compiled R2R delivery.

Every kernel uses seed 137 and 262144 logical operations. Each lane has three
fresh measured PIDs, three warmups then seven formal observations per group
per PID: 21 formal observations/group/lane, 525/lane. Launch order alternates
R2R0, IL0, R2R1, IL1, R2R2, IL2 after the native-entry and both functional gates.
No retry or sample removal. Medians are ns/logical operation, rounded to three
decimals; IL/R2R is the ratio of exact pooled medians, rounded to two decimals.

| Workload | R2R ns/op | IL ns/op | IL/R2R |
| --- | ---: | ---: | ---: |
| field-readwrite | 1.284 | 146.164 | 113.82 |
| auto-property-readwrite | 1.218 | 249.389 | 204.81 |
| noinline-property-readwrite | 2.894 | 249.229 | 86.11 |
| interface-property-readwrite | 4.374 | 257.730 | 58.92 |
| array-index-read | 0.699 | 99.705 | 142.66 |
| array-index-write | 0.756 | 117.991 | 156.08 |
| list-index-read | 0.868 | 102.210 | 117.75 |
| list-index-write | 2.191 | 113.844 | 51.97 |
| list-foreach | 2.264 | 58.877 | 26.01 |
| dictionary-int-hit | 7.691 | 130.342 | 16.95 |
| dictionary-int-miss | 5.424 | 146.184 | 26.95 |
| dictionary-int-update | 4.392 | 115.562 | 26.31 |
| dictionary-string-hit | 20.837 | 162.885 | 7.82 |
| dictionary-string-miss | 13.678 | 166.303 | 12.16 |
| direct-method-call | 1.176 | 209.837 | 178.43 |
| virtual-call-monomorphic | 2.095 | 216.043 | 103.11 |
| virtual-call-polymorphic | 2.520 | 216.477 | 85.91 |
| abstract-call-monomorphic | 2.098 | 213.300 | 101.68 |
| abstract-call-polymorphic | 2.513 | 215.035 | 85.58 |
| interface-call-monomorphic | 2.057 | 217.274 | 105.62 |
| interface-call-polymorphic | 2.906 | 210.013 | 72.26 |
| delegate-call-single-target | 1.678 | 219.105 | 130.59 |
| delegate-call-alternating-targets | 2.683 | 220.261 | 82.09 |
| host-to-script-abstract-call | 1.384 | 60.247 | 43.53 |
| script-to-host-interface-call | 2.141 | 110.462 | 51.60 |

### Actual Execution Evidence And Limits

One diagnostic app (PID 50320) stopped at the first native instruction of
AccessKernels.Auto (MethodDef 0x06000005), ArrayRead (0x06000008), AbstractCall
(0x06000014) and AbstractA.Calculate (0x06000029). Actual PC and loaded Mach-O
UUID/base/executable section, complete bounded method memory bytes, crossgen
method map, linker symbols and ARM64 RuntimeFunctions begin/unwind lengths
bind these entries to original metadata tokens, signatures and workload MVID.
No global interpreter-stub stepping or target evaluation manufactured entries.
The diagnostic app has debugger-observed exit 0, separate from debugger wait.

Earlier, a separate bounded diagnostic captured interpreter entries for the
late-IL workload constructor, Prepare, get_ScriptTarget, Execute, Verify and
AbstractA.Calculate. That original package had no workload R2R body available;
its interpretation does not demonstrate refusal of available R2R. Neither
diagnostic proves every method/helper/call or the historical timed invocations.
Original timing labels stay unproven-selection. The new four native entries
are accepted narrowly, not as all-25-method execution qualification.

Both new packages share Host/bridge input IL, native wrapper, runtime libraries
and selection settings. AccessHost loads through the default, noncollectible
ALC; Access.Contract identity stays shared. WarmModule and session lifecycle
inputs remain unchanged late/collectible IL. All emitted component method IL,
locals, EH, MaxStack and signatures match input IL. Complete bridge deps
membership was supplied for this new pair, not retroactively for old apps.

Input-bubble composite optimization, normal inlining/devirtualization, native
code/component layout, loading paths and uncontrolled caches differ. The
7.82-204.81 descriptive median ratios are package-pair results, not isolated
opcode/property/dispatch costs, universal interpreter penalties or a promise
for phones. No new native witness was inserted into measurement intervals.

## Earlier Six-Lane Access / Collections / Dispatch Extension

Representative medians, ns/logical operation; same 262144 operations and seed
137, three PIDs/request, three warmups plus seven formal/group/PID (21/group).
Windows and macOS each ran one 25-group check plus six measurements; mobile
each ran one check plus three measurements. All 22 products passed the
original 32-row lifecycle gate. These earlier iOS values are late IL, NOT the
new R2R package. No cross-platform ranking or native/interpreter ratio follows.

| Workload | Win default | Win selective | Mac default | Mac selective | Android default | iOS sim default |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| field-readwrite | 1.156 | 181.138 | 1.562 | 27.269 | 1.100 | 152.582 |
| auto-property-readwrite | 1.162 | 217.116 | 0.866 | 43.271 | 1.110 | 272.762 |
| array-index-read | 0.555 | 164.554 | 0.651 | 14.252 | 0.494 | 108.087 |
| list-index-read | 0.834 | 133.597 | 0.801 | 18.198 | 0.779 | 105.637 |
| dictionary-int-hit | 5.622 | 157.719 | 8.153 | 40.452 | 4.113 | 141.090 |
| dictionary-string-hit | 20.160 | 298.676 | 18.143 | 47.197 | 19.022 | 177.911 |
| abstract-call-monomorphic | 1.624 | 399.150 | 1.575 | 35.215 | 1.639 | 215.940 |
| abstract-call-polymorphic | 1.623 | 399.586 | 2.029 | 35.464 | 1.608 | 237.522 |
| delegate-call-single-target | 1.789 | 785.365 | 1.568 | 37.916 | 1.764 | 229.053 |
| host-to-script-abstract-call | 1.091 | 192.548 | 1.087 | 26.404 | 1.211 | 70.966 |
| script-to-host-interface-call | 1.770 | 292.702 | 1.495 | 26.824 | 1.768 | 115.900 |

The complete 25 groups include field control; auto, noinline and interface
property read/write; array read/write; List indexed read/write and foreach;
integer dictionary hit/miss/update; ordinal string dictionary hit/miss;
nonvirtual, virtual/abstract/interface mono- and polymorphic dispatch; cached
single/alternating-target delegates; host-to-script abstract and script-to-host
interface calls. Receivers, delegates, keys and collection capacity are prepared
outside timers, outputs/writes verified afterward. Outer kernels retain their
noinline boundaries, normal callee optimization is allowed. The two cross-module
directions have different loop/data-access scopes; they are not a symmetric
transition tax. BCL and host execution can differ from script execution.

## Earlier Warm And First-Use Baseline (Kept Separate)

Warm counts: Windows 336 + macOS 336 + Android 168 + iOS 168 = 1008 formal
samples. Each request/group has 21 samples from three PIDs after three warmups.
Five warm-callback composite scopes use Numeric (1000000 operations), Lcg
(100000), Scalar (10000), graph (1024) and allocation (256). Three session
scopes (Empty0, Gameplay0, Gameplay128) include load/activate/run/close/unload
request; eventual collection is not part of that timer. Values below are
milliseconds per WHOLE scope, not the ns/op unit of the tables above.

| Lane | Warm Numeric median ms | Warm Gameplay128 median ms |
| --- | ---: | ---: |
| Windows / default | 3.319400 | 15.602500 |
| Windows / selective-author | 28.740300 | 7.723600 |
| macOS / default | 4.766125 | 1.438708 |
| macOS / selective-author | 17.871708 | 0.791084 |
| Android emulator / default | 3.462415 | 2.774286 |
| iOS simulator / default | 110.849167 | 3.463375 |

Direct first use retains seven separate child intervals: module load, module
activation, first Numeric call, package read, session start, first tick and
session stop. Windows has 42 intervals across two requests; macOS, Android and
iOS have 21 each (default only), totaling 105. Each metric/request has only
three observations: use min/median/max, not population-tail estimates.
Verification and post-stack diagnostic GC follow the series, then exactly
one original 32-row gate per PID (480 rows total). Numeric 32760817287,
one-tick checksum 3620, 72 entities created/released, zero remaining and
after-stack collection passed. Fresh processes do not imply disk-cold caches.

Six additional Windows parent launch-to-pipe-ready windows use the parent
monotonic clock: median 844.532500 ms default, 797.526500 ms selective-author.
They are separate from child Stopwatch intervals: no cross-clock subtraction
or decomposition into pure runtime startup is supported.

## Hardware, Configuration And Identity

| Platform | Observed environment and runtime |
| --- | --- |
| Windows x64 | Windows 10.0.26300; selected original Windows inventory has no CPU marketing model. Private framework 12.0.0; actual coreclr matches Checked PDB despite a Release-named directory. |
| macOS ARM64 | Macmini9,1; 8 CPUs/16 GiB; macOS 27.0.1/26A434. Cached attempt4 private .NET 12 framework plus ICU/OpenSSL, not a uniform all-Release build claim. |
| Android emulator x86_64 | API 35, 4 vCPUs/3072 MiB; guest Intel Core i7-10700K 3.80GHz. Cached mobile runtime; emulator, not a phone. |
| iOS simulator ARM64 | Mac host above; iPhone 16/iOS 27.0, Xcode 27.0; cached mobile runtime and signed trusted composite plus late IL. |

Desktop requests use ReadyToRun=1, TieredCompilation=0, InterpMode=0.
The extension selective filter is Access.Workloads!*; the older warm/first-use
filter targets WarmModule!* and RuneCLR.SessionMap!*. Mobile uses the default
recipe; the new iOS pair uses ReadyToRun=1, TieredCompilation=0, invariant
globalization and no forced Interpreter/InterpMode setting. No invented
1000-call promotion threshold is used. Common extension IL compiler:
SDK 11.0.100-rc.2.26504.105, csc 5.12.0-1.26504.105 with matching net11
reference pack; new iOS binary-reference bridge/crossgen cache uses SDK
11.0.100-rc.1.26420.103. No runtime/CoreLib rebuild for the comparison.

Selected SHA-256 identities (input IL, unsigned cache and signed output are
different identities, not interchangeable):

| Object | SHA-256 / identity |
| --- | --- |
| Access.Workloads original input IL | b2cb8e4f637278c4ac233c758e41e618c9e44ea7203b565850e62936b39ec95c |
| Workload MVID | fdb9518b-a4fe-4247-abd2-7b37b2141eb3 |
| Mobile runtime source commit | 3126bbc9a8851a09ac6435b18a12882bad48f3ee |
| iOS unsigned cached libcoreclr | b0670a7604bd8857409f1ea9ac543f293c99047286f6f762d0eb720ca6f877ae |
| iOS signed deployed libcoreclr (both new lanes) | 71b0aa28e76e8672ff7041a442f1a2696006ed53f2fc423f7324385713f05ef9 |
| iOS CoreLib input IL | 60bcb3e62ca1b1ba2504b7b00c8d57723b426eb66ea425e9082afb9255607c81 |
| iOS crossgen2 | 1b5da2959311a58ff8ed09c8f695be6869d143ab36f65974bb478b89cc0ab8b7 |
| New R2R signed composite | 50be9a73520e35c3d1e3c89fc5200cb11d8255e5509f1bf709d4bd4ac6fb696d |
| New IL-control signed composite | 295ae089c598974ff6ad59f9d982a9e365f9838045d9d2493a0b9a2139fa5b37 |
| New R2R composite UUID | F2C8722C-BE10-3D0F-B6ED-F2BB389B6E3D |
| Windows coreclr | a9391606e33afcd41e2f117ea2c83f4a045c5e0bddc32320d50205a95fbf36dd |
| macOS coreclr | 98dfcbc501c98dbda00ad0366bce47abd76355bf415345d65b87883a129ee9da |
| Android coreclr | c357ec9c3e8f37a5f12a465b8fdc04d5bb3f25c48c064e15f82f628fcc2de10d |

## Provenance, Reproducibility And Remaining Work

The lead accepted descriptive results on 2026-10-18 after exact Fraction
recomputation: type-7 quantiles, both whole-scope seconds and normalized ns/op,
pooled within a lane and per PID, all samples including zero ticks, allocation
(current thread) and GC collections (process-wide). Natural GC stays timed;
forced diagnostic GC is outside throughput timers. Only three measured PIDs
and seven formal observations/PID/group support descriptive, not reliable
population-tail claims. Scheduler/power/thermal/cache state is uncontrolled.

Original local experiment records retain frozen source/input IL/config/argv/
environment/product/tool manifests, per-product before/after guards, exclusive
precommands, launch PIDs, direct integer tool waits, boolean watchdogs, dual
streams, SSH transport envelopes, raw JSONL, signed packages, native maps and
passive semantic/provenance controls. Source checksums and resource/alias/Func/
throw/closed/release/session predicates passed. Normal append-only outputs are
not frozen inputs; historical failures and earlier gate failures remain intact.

These private-machine raw archives, binaries and experiment runners are local
records and are NOT committed or downloadable through this report. There is
no published one-command reproducible benchmark runner claimed here. A future
rerun needs equivalent exact runtime/tool packages, reviewed adapters, fixed
workload oracles and newly authorized process budgets; hashes alone do not
supply missing binaries or reconstruct original runtime build provenance.

Selected retained evidence identities (not download links):

| Local evidence object | SHA-256 |
| --- | --- |
| New iOS pair exact statistics | 5d532b6ac042ad384d5e295e5edbd0dcf8a07e1479681536c6db901ccadb3110 |
| Earlier six-lane extension exact statistics | 24f590a33a5770a27d4e85dd60c7f6b0918f3205dfe2d0835b4c21a171fbe1f6 |
| Earlier baseline exact consolidation | bf4862a1d189d5f94fe98098facd2fd000307b14a6c408d15e0c5d2eab865e6b |
| New iOS pair raw archive | b5ee5c76adc8499840e118b35f96ddab206718812cf6cb495fb6f8e3daefd45e |

Scope limits retained: earlier mobile deps omitted explicit bridge-library
membership; successful embedded execution is not canonical package closure.
Windows/Mac earlier Python identities were command-time, not separate earlier
binary seals. Android seals cover resolved tools rather than entire SDK/JBR,
and inherited builder child streams are line-normalized. New iOS pair pins
selected SDK inputs, not every Apple SDK header; Python executable, not whole
stdlib. Mobile managed/native return markers, transport waits and application
OS exit are distinct: mobile app OS directwait and outer SSH OS wait remain
unknown. A successful transport is not fabricated app OS exit evidence.
The separate offline CDB reader work accepts failed-trial observation parsing
only; it does not supply a live CLR/interpreter witness for these timings.

Physical devices, downloaded independent iOS R2R delivery and formal
all-method/per-call execution-mode qualification remain open. Trusted hot
updates and restricted interpreted UGC remain different policies; this
installed composite result does not impose interpreter-only first-party code.

Next, after publishing this report: callback-scoped coarse time-limit work
for interpreted UGC, followed by matched OFF/ON on the same new runtime with
frozen workloads/runner/oracles and cutoff/recovery tests. No such enforcement
was implemented or benchmarked by these experiments. Transport watchdogs and
cooperative charges do not establish runtime callback enforcement.
