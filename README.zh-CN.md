# RuneCLR

**让 C# 成为支持 iOS 热更新的脚本语言。热更与非热更模块均可独立 R2R/AOT，同一基础也支持 UGC 管理。**

[English](README.md) | **简体中文**

iOS 上无法依靠常规 JIT 执行新下载的代码。游戏团队因此常常需要引入另一种脚本语言、维护跨语言绑定，或为独立 C# 解释方案适配语言特性与运行时行为。RuneCLR 的第一方路线是：**下载、加载独立预编译的 C# R2R 热更模块，与非热更 R2R 代码组合运行，共享同一个 CLR 对象模型。** R2R（ReadyToRun）提供预编译原生代码，CoreCLR 解释器补齐没有可用预编译实现的方法。

> **当前为实验项目。** 已在 iOS ARM64 模拟器中执行安装后编译的 IL，并验证 R2R 宿主互调、错误恢复和重复回收。**iOS 真机下载 R2R 热更并执行的验收仍待完成**；目前尚无可直接投产的移动端 SDK。

## 为什么选择这条路线

- **热更与非热更，都写 C#。** 保留同一套语言、类型与 API，减少把逻辑改写成 Lua 或维护两套实现的成本。目标是按构建配置调整代码的执行位置，而不是重写业务逻辑。
- **直接使用宿主对象。** 解释代码与可信 R2R 代码共享 CLR 类型、对象与 GC；普通托管对象交互不需要跨语言序列化、复制或代理转换。跨边界调用仍有执行开销，跨会话引用也需要明确管理。
- **热更与非热更，都能分别 R2R/AOT。** 第一方目标是独立构建 R2R 热更模块，加载后与非热更 R2R 模块组合执行，保留 C# 调用和共享对象。解释器补齐没有可用预编译方法体的部分。同源构建、模块组合与安装后 R2R 交付均列入正式验收。
- **现代 C#，可嵌入不同宿主。** 基于 CoreCLR 的类型与执行模型，核心项目不依赖 Unity。源码编译采用所选 SDK 编译器支持的最新正式 C# 版本，语言、运行时和库的兼容性分别验证。
- **UGC 管理建立在同一个基础上。** 为玩家脚本增加包验证、会话生命周期、执行预算和资源回收，开发团队自有代码的热更新接入可以独立推进。

## 第一方：R2R 热更新 + 解释器补齐

**第一方热更以 R2R + 解释器协作为方向。** 游戏团队自有的热更模块属于可信代码，目标是下载独立构建的 R2R 模块并加载到现有应用中，让预编译原生实现与需要解释的方法在同一个 CLR 中协作；运行时、框架及目标架构需要兼容。可复现的同源构建与独立 R2R 模块组合验收由 [#13](https://github.com/ReneeGA2020/RuneCLR/issues/13) 跟踪。

| 代码 | 执行方向 |
| --- | --- |
| 可信非热更模块 | 独立构建的 R2R |
| 可信热更模块 | 下载、加载独立构建的 R2R；解释器补齐没有可用预编译方法体的部分 |
| 当前受限 UGC 代码及私有依赖 | 各目标平台统一采用 IL 解释 |

**UGC 当前选择纯解释，是管理控制的阶段策略。** R2R 包含机器码，指令计量、终止和能力控制需要额外机制，因此当前 UGC 策略统一解释执行，并拒绝直接执行作者提供的原生方法体。这不代表热更 C# 没有 R2R/AOT 能力。

CoreCLR 上游的方向也是 R2R 与部分解释执行组合（[维护者说明](https://github.com/dotnet/runtime/issues/112748#issuecomment-2681260591)）。现有安装后 IL 实验验证了解释路径，尚未证明 iOS 下载 R2R 后的原生执行；该目标仍需验收打包、签名与加载、实际 R2R 方法入口和解释回退。这里的 R2R/AOT 指 ReadyToRun 预编译，与 NativeAOT 区分。

## 第一方游戏热更新方案对比

以游戏团队更新自己的可信 C# 业务代码为前提，重点比较源码复用、对象互调、预编译与引擎接入成本。

| 路线 | 第一方热更新的接入工作 | RuneCLR 的路线 |
| --- | --- | --- |
| Lua 集成，例如 xLua / ToLua | 将选定的 C# 业务改写为 Lua，维护 C#/Lua 对象绑定与跨语言调试 | 热更与非热更业务都保持 C#，共享 CLR 类型和对象 |
| 独立 C# IL 解释方案，例如 ILRuntime | 适配独立解释器与原生宿主，按所选版本核对语言/库覆盖及引擎工作流 | 复用 CoreCLR 类型与运行时机制，同一模块可选解释 IL 或自身的 R2R 构建，以引擎无关嵌入为目标 |
| 仅通过 AOT 执行的应用代码 | 新增 IL 没有已安装应用中的原生方法体，更新代码需要额外的执行与交付机制 | 目标是独立构建、下载 R2R 热更，与现有 R2R 模块组合运行；解释器补齐没有可用预编译方法体的部分 |

同源 IL/R2R 构建与独立 R2R 模块组合仍待 RuneCLR 正式验收。这个用途的性能对比应采用第一方可信配置，衡量启动、业务回调与宿主互调成本。已有 [Windows 内核基准](docs/performance-experiment.md)可作为独立参考，尚未建立 ILRuntime/xLua/ToLua 性能排名，也不代表 iOS 真机表现。

## 两个用途，一个运行时基础

| 用途 | 面向谁 | 重点 |
| --- | --- | --- |
| **C# 热更新** | 更新自己游戏可信业务代码的开发团队 | 下载、加载独立 R2R 热更，解释器补齐，共享宿主对象、版本切换与回退、宿主嵌入 |
| **C# UGC** | 开放玩家或外部作者脚本的游戏 | 在热更新能力上增加受控编译、能力策略、预算、资源归属和回收 |

“热更新”首先指应用发布后获取并执行新逻辑，可以在模块或会话边界切换版本；当前不承诺替换正在执行的调用栈或自动迁移存活对象状态。服务端权威是现有游戏示例的选择，不是运行时的嵌入前提。

## 已经验证到哪里

每项计数以链接中的对应套件和配置为准。

| 能力 | 已有证据 |
| --- | --- |
| 实验性签名强类型会话 | 普通 Windows 与匹配的私有运行时通过 [17 项交付和 10 项会话检查](docs/trusted-embedding-next.md)：重复强类型调用、宿主所有权、关闭、receipt 不变和进程版本选择 |
| 已签 R2R 首次激活 | [Windows x64 原生执行](docs/trusted-composition-delivery-native.md)：15 个绑定到方法的原生 PC，禁用 R2R 时匹配为零，另有 10 次 helper 解释执行证明 |
| 桌面加载、错误恢复和回收 | [37 项生命周期、85 项打包、15 项同步执行、22 项逐帧执行验收](docs/package-execution-tests.md)，以及 [解释器执行证明](docs/interpreter-experiment.md) |
| iOS ARM64 模拟器新增 IL | [安装后生成 IL 的九组方法、三种解释入口采样](docs/ios-open-delegate-entry-acceptance.md)；[更新宿主的逐帧预算应用通过 16 个场景、74 个上下文回收](docs/ios-pumped-budget-acceptance.md) |
| Android x64 模拟器 | [Release 解释选择、拒绝恢复及正常原生对照](docs/android-session-policy-release-production.md)；[100/1000 批量计量与计时](docs/mobile-batch-measurement.md) |
| 执行预算原型 | [Windows 受控包与逐帧原生预算组合通过 33/33 组](docs/controlled-package-native-budget.md)，iOS 模拟器另有诊断 IL 验收 |
| 官方运行时缺陷跟踪 | [独立缺陷档案](docs/upstream-bugs/README.md)，包含 R2R/可回收上下文缓存缺陷与私有修复验证 |
| 离线记录的模块/Host 文本关联 | [r9 有界离线验收](docs/validation/trusted-update-milestone-20261022.md#r9-recorded-text-correlation)：138 项合成、79 项记录和 7 项清单测试；仅验证启停记录的文本关联，不代表运行时执行 |

本候选的 Windows 普通 SDK 门禁已实测通过：./eng/verify.ps1 退出码 0，耗时
385.901 秒，SDK 11.0.100-rc.2.26504.105（UTC 2026-10-21T17:07:54 至
17:14:20；本地 2026-10-22）。Runtime 146/146、Packaging 307/307、可信更新
272/272、包执行 15/15 加逐帧 22/22、staging 17/17、recovery 37/37 通过，
另有 6 项新增 callback-deadline 测试通过；源码前后稳定于
dbd6574a1222e492300c15016554f7d00c3725cb58e44cabcde55cc32618148b。
Windows、Linux 和 macOS 的最新 CI 结果见 [PR #17](https://github.com/ReneeGA2020/RuneCLR/pull/17)，
合并前要求最新 PR 提交的三平台检查全部通过。Stock 拒绝/选项测试不证明
私有 callback 时序、解释器、iOS 或原生执行。归档/本地收据：
E:/RuneCLR-publish-evidence-20261022/verify-run-20261022/（verify-portable-summary.json；
verify-portable-final.log SHA-256
8ae4f252fc595add24999c36e2de987ca41f4650322a8cd934a8ecf14cce233d）；不提交完整日志。

可信会话检查使用实验性桌面 Host。关闭逻辑会话会释放实例所有权，已选原生模块仍驻留到进程退出。同会话重复调用的原生执行单独验收。

仍待完成：iOS 真机运行、正式同源 IL/R2R 构建验收、完整对象互操作与语言兼容矩阵、可分发运行包，以及真实游戏接入。**尚未实现恶意代码安全沙箱或硬内存隔离。**

## 快速体验

安装 .NET 11 SDK，在仓库根目录运行。仓库没有通过 `global.json` 固定 SDK；使用 `dotnet --version` 记录实际选中的版本。

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
- [可信更新集成里程碑](docs/validation/trusted-update-milestone-20261022.md) / [开发交接](docs/development.md) / [贡献约定](AGENTS.md)

当前 API 仍使用 `Map` 命名，脚本用途不限于地图。UGC 受限配置、可信热更新配置与 CLR 本身的能力会分别记录；完整 .NET/NuGet 兼容性仍需逐项验证。

## 许可证

MIT。RuneCLR 是独立开源项目，并非微软官方 .NET 产品。
