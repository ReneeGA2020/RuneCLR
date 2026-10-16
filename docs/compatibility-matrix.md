# Compatibility matrix

Draft of facts already measured in this repository. A blank or "untested" cell is not a pass. Launcher exit status is not a business-success signal. Only the desktop self-test sample row below records a duration. It is not a distribution, it does not close #13, and it is not iOS.

Compiler syntax, runtime behavior, framework API, platform/architecture, and the restricted UGC policy are separate columns. A pass in one column does not fill another. Measured host and script reference facts are collected in [direct interop](direct-interop.md). That note does not close #14.

| Record | Compiler syntax | Runtime feature | Framework API | Platform / architecture | Restricted UGC policy |
| --- | --- | --- | --- | --- | --- |
| Desktop selector, `tests/RuneCLR.TrustedUpdate.Tests` 270/270 | Not a syntax measurement | Passed 270/270. One version for the process, next-start rollback, no same-process switch or native unload | Host work, echo, generic echo, and additional content checks covered by that suite | Desktop. Not iOS and not a physical device | Not the restricted UGC profile. That profile still excludes the delegate surface, the tick schedule, and host-completed work |
| Desktop trusted composition, 2026-10-16, `artifacts/trusted-composition-20261016-desktop` | Not a syntax measurement | Five functional/execution controls passed (`controlsPassed=true`). Combined acceptance is `status=blocked-collectible-r2r` and `milestoneComplete=false`. The noncollectible `r2r-native` report passed; the IL-only helper was interpreted | Object-identity sessions `A,B,A,A,A` with `HostTouches=9`, `InterfaceCalls=9`, `DelegateCalls=9`, `GenericCalls=18`, `HostIdentity=true` | Desktop runtime `runeclr/interpreter-baseline` at `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. Not iOS | Not a UGC grant. Policy from that measurement: do not pursue unloadable hot-update R2R. An update that must be unloaded stays interpreted. Ordinary first-party execution does not repeatedly unload old assemblies |
| iOS 27 simulator `rerun-a9164cd-20261016-10` | Not a syntax measurement | `verify-ios-trusted-update.py` exited 0, `passed=true`, `nativeExecutionProven=true`. A and B both `RUNECLR_EXIT=0` and `TRUSTED_UPDATE_SUCCESS result=216` | Trusted-update host path used by that receipt. Not a framework-wide API pass | iOS 27 simulator. Not a physical device | Trusted first-party lane, not the restricted UGC profile |
| iOS 27 simulator `rerun-c268026-20261016-01` on clean `c268026` | Not a syntax measurement | `verify-ios-trusted-update.py` exited 0, `passed=true`, `nativeExecutionProven=true`. A and B both `RUNECLR_EXIT=0` and `TRUSTED_UPDATE_SUCCESS result=216` | Same trusted-update receipt shape. Not a framework-wide API pass | iOS 27 simulator. Not a physical device | Trusted first-party lane, not the restricted UGC profile |
| Desktop self-test sample, `dotnet run --project samples/RuneCLR.TrustedUpdateHost -c Release -- --timings`, exit 0, `scope=one-desktop-self-test-sample` | Not a syntax measurement | One run printed `TIMING_STARTUP_MS 99`, `TIMING_CALLBACK_MS 0`, and `TIMING_BOUNDARY_MS 1`, plus `TICK 5` and `LATE-CLOSED`. `TIMING_STARTUP_MS` includes writing the dynamic assembly, selection, and opening the session. `TIMING_CALLBACK_MS` is one `TryTick` callback in whole milliseconds; 0 means under 1 ms, not proof of zero cost. `TIMING_BOUNDARY_MS` includes `LATE-CLOSED`. Not a distribution and does not close #13 | One sample callback, not a framework-wide API pass | Desktop self-test sample. Not iOS and not a physical device | Not the restricted UGC profile |

The source compiler follows the selected SDK compiler's latest stable C# version. There is no project-imposed C# 12 ceiling. That choice is not a measurement that every language feature or every framework API runs on every platform.

| Desktop pumped sessions, tests/RuneCLR.Runtime.Tests 55/55 | Not a syntax measurement | Passed 55/55 in Release. Includes host-owned resource names, one-slot Repeat, and host-posted primitives in FIFO order. Not a wall-clock timer | Resource registration, Repeat, Subscribe, and Post are covered by that suite. Not a framework-wide API pass | Desktop. Not iOS and not a physical device | Not the restricted UGC profile. That profile still excludes resource registration, Repeat, and host-posted events |

| Desktop sample host --pump, 2026-10-16 | Not a syntax measurement | Release --pump exited 0. hello, arena, and hello each Completed with ticks=3. --collect unloaded all three. --require-interpreter on the installed SDK exited 1 before a map ran | Sample maps only. Not a framework-wide API pass | Desktop ordinary runtime selection. Not iOS and not a physical device | Not the restricted UGC profile. Not interpreter execution |

| Desktop eng/verify.ps1, 2026-10-16 | Not a syntax measurement | Exited 0. Covered the Release solution, late map, runtime tests, packaging, controlled player, trusted-update selector, desktop iOS-host source check, trusted-update self-test, and both sample collection paths. No simulator | Not a framework-wide API pass | Desktop. Not a physical device | Not a UGC grant. The ordinary sample path is not interpreter proof |

## Untested

These are untested. They are not implied by the rows above.

- iPhone XR on iOS 18.7. That phone is not the iOS 27 runtime used for the simulator receipts.
- Any `iphoneos` physical-device run.
- Native R2R for a collectible module. The desktop composition result stays `blocked-collectible-r2r`.
- Full .NET, or an arbitrary NuGet package.
