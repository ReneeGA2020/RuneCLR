# RuneCLR

**C# scripting for iOS hot updates. Updateable and non-updateable modules can each use R2R/AOT, with UGC management on the same foundation.**

**English** | [简体中文](README.zh-CN.md)

iOS cannot rely on conventional JIT compilation to execute newly downloaded code. Game teams often introduce another scripting language, maintain cross-language bindings, or adapt a separate C# interpreter's language and runtime coverage. RuneCLR builds on **one CLR object model for interpreted IL and independently precompiled R2R modules. Both updateable and non-updateable C# modules can have their own R2R builds and run together.** R2R (ReadyToRun) provides ahead-of-time native code; newly downloaded iOS IL uses the interpreter.

> **Experimental.** iOS ARM64 simulator runs execute IL compiled after installation, with trusted R2R interaction, failure recovery and repeated collection. **Physical iOS device acceptance is still pending.** A production-ready mobile SDK is not yet available.

## Why This Route

- **C# on both sides of the update boundary.** Keep one language, type system and API instead of rewriting logic in Lua or maintaining parallel implementations. The goal is to move code by changing build configuration, rather than rewriting business logic.
- **Use host objects directly.** Interpreted and trusted R2R code share CLR types, objects and GC. Ordinary managed interactions do not require cross-language serialization, copying or proxy conversion. Calls still have execution overhead; cross-session references need explicit ownership.
- **Compile either part with R2R/AOT.** Updateable and non-updateable modules can be compiled separately to R2R and run together in one runtime, retaining C# calls and shared objects. Interpretation is another execution choice, rather than an inherent limit on updateable code. Formal same-source and separately built R2R-module acceptance is on the roadmap.
- **Modern C# and engine-independent embedding.** Build on CoreCLR's type and execution model; the core projects have no Unity dependency. Source compilation follows the selected SDK compiler's latest stable C# version. Language/runtime/library compatibility is verified separately.
- **Add UGC management on the same foundation.** Package validation, session lifetimes, execution budgets and resource cleanup serve player scripts. Trusted developer-owned hot-update integration can progress independently.

## R2R/AOT Applies to Both Parts

**The update boundary and the execution mode are separate choices.** A game team's own hot-update modules are trusted code and can use R2R without adopting the restricted UGC policy. Separately built R2R modules can run together and interact with interpreted IL in the same CLR; a single composite image is not inherently required. Runtime, framework and target architecture must be compatible. Reproducible same-source builds and independent R2R module composition are tracked in [#13](https://github.com/ReneeGA2020/RuneCLR/issues/13).

| Code | Execution direction |
| --- | --- |
| Trusted non-updateable modules | Independently built R2R |
| Trusted updateable modules | Independently built R2R or interpreted IL, according to platform and delivery requirements |
| Current restricted UGC code and private dependencies | IL interpreted across target platforms |

**UGC currently chooses interpretation for management reasons.** R2R contains machine code, which needs additional mechanisms for instruction accounting, terminal interruption and capability control. The current UGC policy therefore uses interpretation and rejects author-supplied native bodies. This policy does not mean updateable C# lacks R2R/AOT capability.

On iOS, newly downloaded IL is interpreted; native R2R modules go through the application's native build/signing pipeline. A module's R2R build capability does not establish a downloaded native-code delivery route. R2R/AOT here means ReadyToRun precompilation, distinct from NativeAOT.

## Compared With Common Routes

| Route | Integration concern | RuneCLR's focus |
| --- | --- | --- |
| Lua integrations such as xLua / ToLua | C#/Lua logic migration, object bindings and cross-language debugging | Keep business logic in C# and interact through one CLR object model |
| Standalone C# IL interpreters such as ILRuntime | Evaluate each implementation's language/library coverage, bindings and engine workflow | Reuse CoreCLR foundations and validate direct interpreter/trusted-R2R collaboration |
| Pure AOT execution | New IL has no native method body compiled into the installed app | Interpret new IL while trusted modules retain their R2R builds |

These are architectural tradeoffs, not a competitor speed ranking. In the existing [Windows Release benchmark](docs/performance-experiment.md), selected CoreCLR interpreter object/state workloads were near Lua 5.4: object updates took 72.44 ms versus 81.56 ms; numeric recurrence was about 1.62x slower than Lua. Results depend on the workload. There is no direct ILRuntime, xLua or ToLua performance comparison here, and these measurements do not establish physical iOS performance.

## Two Uses, One Runtime Foundation

| Use | Audience | Focus |
| --- | --- | --- |
| **C# hot updates** | Teams updating their own trusted game code | Independent R2R/IL builds, new iOS IL, shared host objects, version switching/rollback and embedding |
| **C# UGC** | Games accepting player or external scripts | Add controlled compilation, capability policy, budgets, resource ownership and retirement |

Hot update initially means obtaining and executing new logic after application publication, with version changes at module/session boundaries. Replacing active stack frames or automatically migrating live object state is not promised. Server-authoritative gameplay is a choice of the current game examples, not an embedding prerequisite.

## What Has Been Demonstrated

Results apply to the linked configurations. Desktop counts include the latest source-compiler regression.

| Capability | Recorded evidence |
| --- | --- |
| Desktop loading, recovery and retirement | [37 lifecycle, 85 packaging, 15 synchronous-player and 22 pumped-player cases](docs/package-execution-tests.md), plus [interpreter execution evidence](docs/interpreter-experiment.md) |
| New IL on the iOS ARM64 simulator | [Nine fresh-IL method groups across three interpreter entry paths](docs/ios-open-delegate-entry-acceptance.md); [updated pumped-budget host: 16 scenarios / 74 collected contexts](docs/ios-pumped-budget-acceptance.md) |
| Android x64 emulator | [Release selection, refusal/recovery and native controls](docs/android-session-policy-release-production.md); [100/1000 batch accounting and timing](docs/mobile-batch-measurement.md) |
| Execution-budget prototype | [Windows controlled packages with pumped native budgets: 33/33 groups](docs/controlled-package-native-budget.md), with separate diagnostic-IL acceptance on the iOS simulator |
| Upstream runtime defect tracking | [Independent defect register](docs/upstream-bugs/README.md), including R2R/collectible-cache defects and private fix validation |

Still ahead: physical iOS execution, formal same-source IL/R2R builds, a full object-interop and language compatibility matrix, distributable runtime packages and a real game integration. **This is not a hostile-code sandbox or a hard memory-isolation boundary.**

## Quick Start

Install a .NET 11 SDK compatible with `global.json`, then run from the repository root:

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
- [Development handoff](docs/development.md) / [Contributor instructions](AGENTS.md)

Current APIs retain prototype `Map` names; scripts need not be maps. Restricted UGC policy, trusted hot-update requirements and CLR capabilities are documented separately. Full .NET/NuGet compatibility requires explicit validation.

## License

MIT. RuneCLR is an independent project, not an official Microsoft .NET component.
