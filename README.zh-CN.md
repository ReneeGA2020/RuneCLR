# RuneCLR

**让 C# 成为支持 iOS 热更新的脚本语言。热更与非热更，业务代码都用 C#。同一基础也支持 UGC。**

[English](README.md) | **简体中文**

iOS 上无法依靠常规 JIT 执行新下载的代码。游戏团队因此常常需要引入另一种脚本语言、维护跨语言绑定，或为独立 C# 解释方案适配语言特性与运行时行为。RuneCLR 探索另一条路：**以 CoreCLR 解释器执行新增 C# IL，让它与可信 R2R 宿主在同一个 CLR 中协作。** R2R（ReadyToRun）是随应用构建发布的预编译原生代码。

> **当前为实验项目。** 已在 iOS ARM64 模拟器中执行安装后编译的 IL，并验证 R2R 宿主互调、错误恢复和重复回收。**iOS 真机验收仍待完成**；目前尚无可直接投产的移动端 SDK。

## 为什么选择这条路线

- **热更与非热更，都写 C#。** 保留同一套语言、类型与 API，减少把逻辑改写成 Lua 或维护两套实现的成本。目标是按构建配置调整代码的执行位置，而不是重写业务逻辑。
- **直接使用宿主对象。** 解释代码与可信 R2R 代码共享 CLR 类型、对象与 GC；普通托管对象交互不需要跨语言序列化、复制或代理转换。跨边界调用仍有执行开销，跨会话引用也需要明确管理。
- **让性能敏感的部分留在可信原生代码中。** 新下载的 IL 走解释，随应用发布的宿主/框架可用 R2R。两部分保持 C# 调用关系；同源代码在 IL/R2R 构建间迁移的正式验收已列入路线图。
- **面向现代 C# 和可嵌入宿主。** 基于 CoreCLR 的类型与执行模型，核心项目不依赖 Unity；以可验证的语言/库兼容性逐步扩展支持范围。当前受限 UGC 编译配置固定为 C# 12，不代表已支持全部 C#/.NET 特性。
- **UGC 管理建立在同一个基础上。** 为玩家脚本增加包验证、会话生命周期、执行预算和资源回收，开发团队自有代码的热更新接入可以独立推进。

## 和常见路线相比

| 路线 | 需要处理的问题 | RuneCLR 的着力点 |
| --- | --- | --- |
| Lua 集成，例如 xLua / ToLua | C# 与 Lua 的业务迁移、对象绑定及跨语言调试 | 业务逻辑保持 C#，在同一个 CLR 对象模型中交互 |
| 独立 C# IL 解释方案，例如 ILRuntime | 评估各方案的语言/库覆盖、绑定需求和引擎工作流 | 复用 CoreCLR 基础能力，验证解释代码与可信 R2R 的直接协作 |
| 纯 AOT 执行 | 新下载 IL 没有随应用预编译的原生方法体 | 为新增 IL 提供解释执行路径，可信宿主继续使用 R2R |

这些是架构取舍，不是竞品性能排名。已有 [Windows Release 实测](docs/performance-experiment.md)中，CoreCLR 解释器在对象更新和状态机负载上接近 Lua 5.4；对象更新耗时为 72.44 ms 对 81.56 ms，数值递推则比 Lua 慢约 1.62 倍。结果与负载有关，尚未建立对 ILRuntime、xLua 或 ToLua 的直接性能结论，也不代表 iOS 真机表现。

## 两个用途，一个运行时基础

| 用途 | 面向谁 | 重点 |
| --- | --- | --- |
| **C# 热更新** | 更新自己游戏业务代码的开发团队 | iOS 新 IL、宿主对象互调、同源构建、版本切换与回退、诊断和嵌入 |
| **C# UGC** | 开放玩家或外部作者脚本的游戏 | 在热更新能力上增加受控编译、能力策略、预算、资源归属和回收 |

“热更新”首先指应用发布后获取并执行新逻辑，可以在模块或会话边界切换版本；当前不承诺替换正在执行的调用栈或自动迁移存活对象状态。服务端权威是现有游戏示例的选择，不是运行时的嵌入前提。

## 已经验证到哪里

以下为已记录的结果，本次文档更新没有重新运行这些实验。

| 能力 | 已有证据 |
| --- | --- |
| 桌面加载、错误恢复和回收 | [37 项生命周期、84 项打包、15 项同步执行、22 项逐帧执行验收](docs/package-execution-tests.md)，以及 [解释器执行证明](docs/interpreter-experiment.md) |
| iOS ARM64 模拟器新增 IL | [安装后生成 IL 的九组方法、三种解释入口采样](docs/ios-open-delegate-entry-acceptance.md)；[更新宿主的逐帧预算应用通过 16 个场景、74 个上下文回收](docs/ios-pumped-budget-acceptance.md) |
| Android x64 模拟器 | [Release 解释选择、拒绝恢复及正常原生对照](docs/android-session-policy-release-production.md)；[100/1000 批量计量与计时](docs/mobile-batch-measurement.md) |
| 执行预算原型 | [Windows 受控包与逐帧原生预算组合通过 33/33 组](docs/controlled-package-native-budget.md)，iOS 模拟器另有诊断 IL 验收 |
| 官方运行时缺陷跟踪 | [独立缺陷档案](docs/upstream-bugs/README.md)，包含 R2R/可回收上下文缓存缺陷与私有修复验证 |

仍待完成：iOS 真机运行、正式同源 IL/R2R 构建验收、完整对象互操作与语言兼容矩阵、可分发运行包，以及真实游戏接入。**尚未实现恶意代码安全沙箱或硬内存隔离。**

## 快速体验

安装与 `global.json` 兼容的 .NET 11 SDK，在仓库根目录运行：

```sh
dotnet build RuneCLR.slnx -c Release
dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build
dotnet run --project tests/RuneCLR.Packaging.Tests -c Release --no-build
dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --collect
```

示例在同一进程中执行 **Hello -> Arena -> Hello**，两次 Hello 的静态计数都会从 1 开始。添加 `--pump` 可体验宿主逐帧驱动。`--collect` 仅用于诊断回收，不应作为逐帧 GC 策略。PowerShell 可用 `./eng/verify.ps1` 执行完整常规验证。

这个快速体验使用普通 SDK 的运行时选择。强制解释和原生预算需要匹配的私有 CoreCLR/CoreLib 构建，详见 [执行策略](docs/execution-strategy.md)；运行示例本身不证明已走解释器。

## 继续了解

- [入门与脚本示例](docs/getting-started.md) / [受控源码与 IL 打包](docs/controlled-packaging.md)
- [产品方向](docs/product-direction.md) / [路线图](docs/roadmap.md) / [GitHub 总任务](https://github.com/ReneeGA2020/RuneCLR/issues/11)
- [架构与对象生命周期](docs/architecture.md) / [CoreCLR 集成](docs/coreclr.md) / [安全与信任模型](SECURITY.md)
- [开发交接](docs/development.md) / [贡献约定](AGENTS.md)

当前 API 仍使用 `Map` 命名，脚本用途不限于地图。UGC 受限配置、可信热更新配置与 CLR 本身的能力会分别记录；完整 .NET/NuGet 兼容性仍需逐项验证。

## 许可证

MIT。RuneCLR 是独立开源项目，并非微软官方 .NET 产品。
