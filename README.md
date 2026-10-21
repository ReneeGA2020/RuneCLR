# RuneCLR

**C# scripting for iOS hot updates. Updateable and non-updateable modules can each use R2R/AOT, with UGC management on the same foundation.**

**English** | [简体中文](README.zh-CN.md)

iOS cannot rely on conventional JIT compilation to execute newly downloaded code. Game teams often introduce another scripting language, maintain cross-language bindings, or adapt a separate C# interpreter's language and runtime coverage. RuneCLR's first-party direction is **download and load independently precompiled C# R2R update modules alongside non-updateable R2R code, sharing one CLR object model.** R2R (ReadyToRun) provides ahead-of-time native code; the CoreCLR interpreter complements it for methods without usable precompiled implementations.

> **Experimental.** iOS ARM64 simulator runs execute IL compiled after installation, with trusted R2R interaction, failure recovery and repeated collection. **Downloaded R2R hot-update execution on physical iOS still needs acceptance.** A production-ready mobile SDK is not yet available.

## Why This Route

- **C# on both sides of the update boundary.** Keep one language, type system and API instead of rewriting logic in Lua or maintaining parallel implementations. The goal is to move code by changing build configuration, rather than rewriting business logic.
- **Use host objects directly.** Interpreted and trusted R2R code share CLR types, objects and GC. Ordinary managed interactions do not require cross-language serialization, copying or proxy conversion. Calls still have execution overhead; cross-session references need explicit ownership.
- **Compile either part with R2R/AOT.** The first-party goal is independently built R2R update modules loaded alongside non-updateable R2R modules, retaining C# calls and shared objects. The interpreter covers methods without usable precompiled bodies. Same-source builds, module composition and post-install R2R delivery are tracked acceptance work.
- **Modern C# and engine-independent embedding.** Build on CoreCLR's type and execution model; the core projects have no Unity dependency. Source compilation follows the selected SDK compiler's latest stable C# version. Language/runtime/library compatibility is verified separately.
- **Add UGC management on the same foundation.** Package validation, session lifetimes, execution budgets and resource cleanup serve player scripts. Trusted developer-owned hot-update integration can progress independently.

## First-Party: R2R Hot Updates With Interpreter Support

**First-party updates target R2R plus interpreter support.** A game team's own hot-update modules are trusted code. The direction is to download independently built R2R modules and load them into the existing application, using precompiled native implementations together with interpreted methods in the same CLR. Runtime, framework and target architecture must be compatible. Reproducible same-source builds and independent R2R module composition are tracked in [#13](https://github.com/ReneeGA2020/RuneCLR/issues/13).

| Code | Execution direction |
| --- | --- |
| Trusted non-updateable modules | Independently built R2R |
| Trusted updateable modules | Download/load independently built R2R; interpreter support for methods without usable precompiled bodies |
| Current restricted UGC code and private dependencies | IL interpreted across target platforms |

**UGC currently chooses interpretation for management reasons.** R2R contains machine code, which needs additional mechanisms for instruction accounting, terminal interruption and capability control. The current UGC policy therefore uses interpretation and rejects author-supplied native bodies. This policy does not mean updateable C# lacks R2R/AOT capability.

CoreCLR's upstream direction combines R2R with partial interpretation ([maintainer explanation](https://github.com/dotnet/runtime/issues/112748#issuecomment-2681260591)). Our existing post-install IL experiments establish the interpreted path; they do not yet establish downloaded R2R native execution on iOS. Packaging, signing/loading, actual R2R method entry and interpreter fallback remain explicit acceptance items for that target. R2R/AOT here means ReadyToRun precompilation, distinct from NativeAOT.

## Comparing First-Party Game Hot-Update Routes

The comparison assumes a game team updates its own trusted C# gameplay code. The focus is source reuse, object interaction, precompilation and engine integration.

| Route | First-party integration work | RuneCLR's approach |
| --- | --- | --- |
| Lua integrations such as xLua / ToLua | Move selected C# logic to Lua; maintain C#/Lua object bindings and cross-language debugging | Keep updateable and non-updateable logic in C#, sharing CLR types and objects |
| Standalone C# IL interpreters such as ILRuntime | Adapt the separate interpreter to the native host; check language/library coverage and engine workflow for the chosen version | Reuse CoreCLR's type/runtime mechanisms; the same module can use interpreted IL or its own R2R build, with an engine-independent embedding goal |
| Application code executed only through AOT | New IL has no native method body in the installed application; code changes need an additional execution/delivery mechanism | Target independently built, downloadable R2R updates that run with existing R2R modules; use the interpreter for methods without usable precompiled bodies |

Same-source IL/R2R builds and independent R2R module composition remain planned RuneCLR acceptance work. Performance comparisons for this use should use trusted first-party configurations and measure startup, gameplay callbacks and host interaction. The existing [Windows kernel benchmark](docs/performance-experiment.md) is a separate reference; it does not establish an ILRuntime/xLua/ToLua ranking or physical iOS performance.

## Two Uses, One Runtime Foundation

| Use | Audience | Focus |
| --- | --- | --- |
| **C# hot updates** | Teams updating their own trusted game code | Download/load independent R2R updates, interpreter support, shared host objects, version switching/rollback and embedding |
| **C# UGC** | Games accepting player or external scripts | Add controlled compilation, capability policy, budgets, resource ownership and retirement |

Hot update initially means obtaining and executing new logic after application publication, with version changes at module/session boundaries. Replacing active stack frames or automatically migrating live object state is not promised. Server-authoritative gameplay is a choice of the current game examples, not an embedding prerequisite.

## What Has Been Demonstrated

Each count belongs to the linked suite and configuration.

| Capability | Recorded evidence |
| --- | --- |
| Experimental signed typed sessions | [17 delivery and 10 session checks](docs/trusted-embedding-next.md) on stock Windows and the pinned private runtime: repeated typed calls, host ownership, close, unchanged receipt and process selection |
| Signed R2R initial activation | [Windows x64 native execution](docs/trusted-composition-delivery-native.md): 15 bound native PC matches, none with R2R disabled, and ten interpreted-helper proofs |
| Desktop loading, recovery and retirement | [37 lifecycle, 85 packaging, 15 synchronous-player and 22 pumped-player cases](docs/package-execution-tests.md), plus [interpreter execution evidence](docs/interpreter-experiment.md) |
| New IL on the iOS ARM64 simulator | [Nine fresh-IL method groups across three interpreter entry paths](docs/ios-open-delegate-entry-acceptance.md); [updated pumped-budget host: 16 scenarios / 74 collected contexts](docs/ios-pumped-budget-acceptance.md) |
| Android x64 emulator | [Release selection, refusal/recovery and native controls](docs/android-session-policy-release-production.md); [100/1000 batch accounting and timing](docs/mobile-batch-measurement.md) |
| Execution-budget prototype | [Windows controlled packages with pumped native budgets: 33/33 groups](docs/controlled-package-native-budget.md), with separate diagnostic-IL acceptance on the iOS simulator |
| Upstream runtime defect tracking | [Independent defect register](docs/upstream-bugs/README.md), including R2R/collectible-cache defects and private fix validation |
| Offline recorded module/Host text correlation | [r9 bounded offline acceptance](docs/validation/trusted-update-milestone-20261022.md#r9-recorded-text-correlation): 138 synthetic, 79 recorded and 7 manifest tests; enabled/off text records only, not runtime execution |

The measured Windows stock gate is ./eng/verify.ps1 exit 0 in 385.901 s on
SDK 11.0.100-rc.2.26504.105 (UTC 2026-10-21T17:07:54 to 17:14:20; local
2026-10-22). Runtime 146/146, Packaging 307/307, trusted update 272/272, package
execution 15/15 plus pumped 22/22, staging 17/17 and recovery 37/37 passed;
six new callback-deadline tests also passed. Source was stable before/after at
dbd6574a1222e492300c15016554f7d00c3725cb58e44cabcde55cc32618148b. Windows,
Linux and macOS CI remains pending, so this is not merge-ready. Stock
rejection/option tests do not establish private callback timing, interpreter,
iOS or native execution. Archival/local receipt:
E:/RuneCLR-publish-evidence-20261022/verify-run-20261022/ (verify-portable-summary.json;
verify-portable-final.log SHA-256
8ae4f252fc595add24999c36e2de987ca41f4650322a8cd934a8ecf14cce233d); the full
log is not committed.

The trusted-session checks use an experimental desktop Host. Closing a logical
session releases instance ownership; its selected native modules remain resident
until process exit. Repeated-call native execution has separate acceptance.

Still ahead: physical iOS execution, formal same-source IL/R2R builds, a full object-interop and language compatibility matrix, distributable runtime packages and a real game integration. **This is not a hostile-code sandbox or a hard memory-isolation boundary.**

## Quick Start

Install a .NET 11 SDK, then run from the repository root. The repository does not
pin an SDK with `global.json`; use `dotnet --version` to record the selected SDK.

```sh
dotnet build RuneCLR.slnx -c Release
dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build
dotnet run --project tests/RuneCLR.Packaging.Tests -c Release --no-build
dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --collect
```

The sample runs **Hello -> Arena -> Hello in one process**, with Hello's static start count reset to 1 each time. Add `--pump` for host-driven frames. `--collect` is diagnostic, not a per-frame GC strategy. PowerShell users can run `./eng/verify.ps1` for full ordinary-SDK verification.

This quick start uses ordinary SDK runtime selection. Required interpretation and native budgets need matching private CoreCLR/CoreLib builds; see the [execution strategy](docs/execution-strategy.md). Running the sample alone does not prove interpreter execution.

## Explore

- [Getting started and script example](docs/getting-started.md) / [Controlled source and IL packages](docs/controlled-packaging.md)
- [Product direction](docs/product-direction.md) / [Roadmap](docs/roadmap.md) / [GitHub tracker](https://github.com/ReneeGA2020/RuneCLR/issues/11)
- [Architecture and object lifetimes](docs/architecture.md) / [CoreCLR integration](docs/coreclr.md) / [Security and trust](SECURITY.md)
- [Trusted update integration milestone](docs/validation/trusted-update-milestone-20261022.md) / [Development handoff](docs/development.md) / [Contributor instructions](AGENTS.md)

Current APIs retain prototype `Map` names; scripts need not be maps. Restricted UGC policy, trusted hot-update requirements and CLR capabilities are documented separately. Full .NET/NuGet compatibility requires explicit validation.

## License

MIT. RuneCLR is an independent project, not an official Microsoft .NET component.
