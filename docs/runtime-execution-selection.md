# Runtime-backed UGC execution selection — source plan, 2026-10-13

The next useful runtime increment is an opt-in, fail-closed interpreter route
for methods defined by collectible modules. It can establish the missing
selection mechanics while trusted host/framework code retains native execution.
It is a controlled diagnostic experiment, not yet the per-session UGC policy.
After those mechanics pass, replace the diagnostic predicate with an immutable
policy assigned when the trusted host creates a session context.

This document records the initial read-only source review and proposed
patch/acceptance plan. The following private
[diagnostic candidate](runtime-execution-selection-candidate.md) implements
the selection mechanics in a separate runtime worktree. Its
[execution acceptance](runtime-execution-selection-validation.md) is recorded
separately from the source plan.
The [accepted strategy](execution-strategy.md) is all-platform interpreted UGC
and private dependencies, with trusted native host/framework execution allowed.
The [package entry evidence](ios-release-package-entry.md) establishes sampled
execution in the existing configuration; it does not enforce that strategy.
Budgets and framework-call restrictions are separate increments.

## Source and build scope

Reviewed official runtime base
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`, local branch
`runeclr/interpreter-baseline`, tracked-clean at review. Product is .NET 12.
The checkout's applicable instructions and CoreCLR build guide were inspected.
All source links below are pinned to that base, not claims about current main.

The matching private iOS ARM64 simulator Release candidate build was inspected
read-only over Cindy SSH. Its CMake cache has `FEATURE_INTERPRETER=1`; the actual
**VM** `jitinterface.cpp` compile command contains `FEATURE_INTERPRETER`,
`FEATURE_READYTORUN` and `TARGET_IOS`, and omits
`FEATURE_DYNAMIC_CODE_COMPILED`. The AOT-tools file with the same basename is
not the VM compilation unit. These definitions are build evidence, not proof
of a specific method's execution.

[clrfeatures.cmake](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/src/coreclr/clrfeatures.cmake#L85)
defaults interpreter support to Debug/Checked on the listed architectures,
excluding Android; Release desktop and Android require an explicit enabled
build. [Managed CoreLib feature definitions](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/src/coreclr/clr.featuredefines.props#L61)
also enable the interpreter for Apple mobile/Mac Catalyst. Build matching
native/CoreLib/interpreter/compiler artifacts; do not mix Debug/Release layouts.

## Actual routing and existing escape paths

There is no `ShouldUseInterpreter` function in this base's selection path.
The relevant decisions are distributed:

| Point | Observed behavior | Consequence for required interpretation |
| --- | --- | --- |
| `MethodDesc::DoPrestub`, `prestub.cpp` | May backpatch existing code; handles unboxing/instantiating stubs and special native methods before ordinary IL preparation | Policy must exist before any method/type preparation; late registration cannot repair already native or inlined bodies |
| `MethodDesc::PrepareInitialCode` / `PrepareCode`, `prestub.cpp:310/334` | `MayUsePrecompiledCode` causes R2R lookup before compilation | An interpreter compiler switch alone does not dominate R2R |
| `GetPrecompiledR2RCode`, `prestub.cpp:484` | Definition module, alternate generic location, then unrelated R2R modules | Guard lookup by the target definition's policy, including direct callers/unboxing and alternate generic search |
| `JitCompileCode`, `prestub.cpp:629` | Can return a concurrent prepared result or stored multicore-JIT code before compiler invocation | Skip multicore retrieval for required methods; immutable creation-time policy prevents old native winners |
| `UnsafeJitFunction`, `jitinterface.cpp:13949` | Attempts interpreter if loaded, then desktop native JIT when returned pointer is null | Required methods must load interpreter independently of environment config and throw before native fallback |
| `CILInterp::compileMethod`, `interpreter/eeinterp.cpp:71` | With dynamic compilation enabled, uses `InterpMode`, method-set selection, and a remembered module handle | Add a VM-supplied required flag that takes precedence over those diagnostic filters |
| `PrepareInterpreterCode`, `interpexec.cpp:1392` | Calls prestub, reads bytecode; null is poisoned and subsequently treated as a native target | A required body must never proceed to this native-target path; add a release-build failure guard before poisoning |
| `CEEInfo::getMethodAttribsInternal` / `canInline`, `jitinterface.cpp:6548/7916` | Native compiler can import a callee's IL without compiling a standalone callee body | Required UGC callees must report `DONT_INLINE` and fail inline requests, overriding `AggressiveInlining` |

Pinned primary sources:
[prestub](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/src/coreclr/vm/prestub.cpp),
[VM compiler interface](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/src/coreclr/vm/jitinterface.cpp),
[interpreter compiler entry](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/src/coreclr/interpreter/eeinterp.cpp),
[interpreter execution](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/src/coreclr/vm/interpexec.cpp).

Some protective behavior already exists.
[`ReadyToRunInfo::Initialize`](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/src/coreclr/vm/readytoruninfo.cpp#L575)
rejects collectible modules; `ComputeAlternateGenericLocationForR2RCode`
rejects methods with collectible loader allocators.
[`CodeVersionManager::IsMethodSupported`](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/src/coreclr/vm/codeversion.cpp#L2254)
excludes collectible and dynamic methods, preventing their ordinary tiering
and ReJIT versioning in this base. These are useful existing defenses, not
substitutes for an explicit required-method policy or future-base regression.

Unsupported execution can fall back. `SKIPCODE` throws an `InterpException`
whose result is `CORJIT_SKIPPED`; `compileMethod` returns that result.
`UnsafeJitFunctionWorker` maps `CORJIT_SKIPPED` to a null result, and
`UnsafeJitFunction` invokes the desktop JIT if dynamic compilation is built in.
The current specific compiler `SKIPCODE` site is the
`NextCallReturnAddress` intrinsic without a following `POP`, not every
unsupported instruction. `BADCODE`/`NO_WAY` return distinct failures that
normally become exceptions. On no-JIT builds the null path contains an
assertion; an assertion is not the explicit recoverable Release rejection
required for this profile. The proposed guard covers both selection refusal
and compiler skip without changing trusted-method fallback.

## Small diagnostic candidate for the next build

Use one new retail diagnostic startup switch, for example
`RuneCLRInterpretCollectible=0` by default. Keep the configuration request
recognizable in all candidate builds; guard the actual interpreter routing
with `FEATURE_INTERPRETER`. Otherwise a build without that feature would
silently ignore an unknown environment variable instead of rejecting it.
This name is proposed, not currently implemented. Freeze its value at startup;
do not allow changing policy after methods are prepared. Enabling it on a build
without interpreter support must return an explicit unsupported configuration
error, not ignore the request. A trusted runner must also verify a candidate
support acknowledgement on an unmodified runtime; an unknown switch alone
cannot establish support. Use mode 0 for acceptance so host behavior does
not depend on full-framework mode 3.

Define a single VM helper with no allocation, loading or GC side effects:

```cpp
// Proposed semantic predicate, not an applied patch.
bool RequiresInterpreterBody(MethodDesc* md)
{
    return StartupDiagnosticEnabled() && md->IsIL() &&
           md->GetModule()->IsCollectible();
}
```

Use the **IL definition module**, rather than just
`md->GetLoaderAllocator()->IsCollectible()`. A trusted
`List<UGCStruct>` method can acquire a collectible loader allocator although
its IL comes from CoreLib. Blanket allocator interpretation would incorrectly
pull trusted framework generic bodies into this experiment. Collectible module
is still not synonymous with UGC: ordinary trusted plugin modules are covered
in this diagnostic lane and must be disclosed. Dynamic methods without a
metadata-owned UGC body are outside this initial predicate and must not be
presented as covered.

Apply these changes together before claiming required interpretation:

1. In `PrepareCode` and `GetPrecompiledR2RCode`, suppress native body lookup
   for required methods. Keep the low-level guard because unboxing and portable
   entrypoint preparation can call R2R lookup directly. In `JitCompileCode`,
   skip `GetMulticoreJitCode` for the same methods. Preserve trusted R2R/JIT.
2. In `UnsafeJitFunction`, load the interpreter if the method requires it even
   when `g_pConfig->EnableInterpreter()` is false. After its worker returns,
   if a required method has no result, throw a stable managed unsupported-body
   error **before** the `FEATURE_DYNAMIC_CODE_COMPILED` native-JIT branch.
   Propagate malformed IL/OOM errors normally. Release must reject as explicitly
   as Checked; do not replace runtime invariants with assertions-only checks.
3. Carry a `CORJIT_FLAG_INTERPRET_REQUIRED` from VM to the interpreter in the
   existing `CORJIT_FLAGS` exchange. Choose a free flag bit on the pinned source
   (33 is currently free), update `JITEEVersionIdentifier`, and rebuild both
   runtime, interpreter and native JIT; the versioned compiler interface forbids quietly
   reusing an existing unrelated flag. Set the flag after ordinary compile flags
   are computed: `CInterpreterJitInfo`'s constructor can call
   `getJitFlagsInternal()->Set(...)` after the `CEECodeGenInfo` base constructor
   assigns `m_jitFlags = GetCompileFlags(...)`. This affects only the interpreter
   compile request. Read `compHnd->getJitFlags(...)` before the selection gate
   in `CILInterp::compileMethod`, which currently reads flags only later when
   constructing `InterpCompiler`. No new virtual `ICorJitInfo` query is needed.
   Audit the flag mirrors in tools/Common/JitInterface/CorInfoTypes.cs and
   jit/jitee.h, including its FLAGS_EQUAL checks. The changed interface GUID
   also requires matching native clrjit and any crossgen/JIT-interface tools
   used in the experiment; a native-only CID replacement build is insufficient.
   When required, bypass the mode/method-set gate; preserve normal compiler
   validation and exceptions. No managed author attribute supplies this flag.
4. Add `CORINFO_FLG_DONT_INLINE` for required callees before honoring
   `AggressiveInlining`, and return `INLINE_NEVER` from `canInline` for them.
   A native trusted host invoking UGC must enter its bytecode body; inspecting
   only standalone method compilation would miss an inline escape.
5. In `PrepareInterpreterCode`, reject null bytecode for a required method
   before `PoisonInterpreterCode` / `InvokeManagedMethod`. This covers internal
   interpreter calls as well as stub entry. Let trusted methods keep the normal
   null/native transition. Add an explicit policy exclusion to tier eligibility
   and reject required-body OSR requests; current collectible versioning already
   excludes them, but required policy must not rely on that forever.

Runtime-created unboxing, instantiating, delegate and calling-convention
bridges may remain native where they marshal/dispatch to an interpreted UGC
IL body. They must not embed or substitute the author's body. Identify the
underlying `MethodDesc` in diagnostics rather than treating a native bridge
entry as either proof or failure of body interpretation. The intake profile
already rejects author native/PInvoke/internal-call routes; changing their
rejection rules is not a prerequisite for this diagnostic patch.

Constructors are ordinary selection targets: include `.ctor`, `.cctor` and
module initialization bodies, not just lifecycle callbacks.
`MethodTable::RunClassInitEx` invokes the canonical class-constructor slot via
the trusted `CallClassConstructor` helper. This is another native-to-UGC entry
to observe, not a reason to interpret the trusted helper. Generic UGC bodies
remain selected through their defining module; test reference, value, shared
canonical, interface/default and constrained cases separately.

This flag exchange is smaller than adding a new virtual compiler-interface
method or attempting to infer a collectible module in the interpreter's opaque
`CORINFO_MODULE_HANDLE`. It still changes the versioned contract, so the GUID
and all consumers used by the lane must match. A VM-only forced interpreter attempt would
still be skipped by mode 0 unless this compiler-side gate is changed.

No global registry of `Module*`, `MethodDesc*` or managed reflection objects
is necessary for the diagnostic predicate. Keep audit data as copied IDs,
tokens, hashes and enum outcomes. The existing interpreter method-set global
remembered `g_interpModule` is a mutable raw handle to the last method-set
opt-in module, not the policy/lifetime storage or a per-session registration.

## Production host registration boundary

After diagnostic acceptance, add immutable `InterpreterRequired` policy to
the session's binder/loader allocator **at ALC creation**, propagated to modules
loaded through that binder before their initialization/preparation.
[`AssemblyNative_InitializeAssemblyLoadContext`](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/src/coreclr/vm/assemblynative.cpp#L1192)
creates the `AssemblyLoaderAllocator` and passes it into
`CustomAssemblyBinder::SetupContext`; this is the concrete lifecycle insertion
point. `AssemblyNative_LoadFromPath`/`LoadFromStream` receive that binder.
Registering only an entry assembly after `LoadFromAssemblyPath` returns is too
late for initialization/preparation and misses later private dependencies.

The host must request the policy before loading any package bytes, query a
supported policy/version acknowledgement, and fail package startup if the
patched runtime cannot enforce it. The existing `MapLoadContext` constructor
requests only `isCollectible: true`; ALC name, module name, manifest and hash
alone cannot request or revoke execution policy. Shared contract/framework
assemblies retain their original trusted definition-module policies.

The production helper should ask the **definition module's** binder policy,
not whichever allocator happens to own a closed generic instantiation. Store
scalar immutable state in the runtime-owned lifetime object; retire it with
that object. Host results keep primitive IDs/counters/strings, no `Assembly`,
`Type`, delegate, exception or persistent native metadata pointers.

Do not expose a public managed toggle that can downgrade an existing context.
A trusted-native registrar or private matching CoreLib creation path can be
prototyped, but managed visibility alone is not a security barrier against
reflection. Marking one session context also does not stop author code from
creating another unmarked ALC, loading into default context, or emitting a
dynamic method. Current intake/API conventions restrict these cases; a later
author-resistant loader/execution boundary must deny or propagate policy for
such attempts. This is a concrete limit on the registered-module claim, not a
requirement to complete hostile-code sandboxing before the first useful patch.

## Validation matrix and pass gates

Keep switch-off official-baseline controls and switch-on candidate controls
on identical managed bytes. Start on Windows x64 Checked with matching
CoreLib/interpreter; repeat required rows on Release, Android enabled build
and iOS ARM64 simulator. Real iOS device remains a separate acceptance lane.
No builds or rows below were executed for this source plan.
Reuse the independent `eng/execution-selection-probe` fixture being developed
alongside this review for constructor/inlining/generic/delegate/interface/filter
and collection controls. Its ordinary JIT and mode 1 results are diagnostic
baselines; the required-policy, R2R-on, OSR-on and forced-skip rows still need
the private selection candidate. Do not duplicate that fixture or call its
mode 1 acceptance enforcement.

| Case | Required evidence / expected outcome |
| --- | --- |
| Startup mode 0, no Interpreter method-set, diagnostic on | Entry/private bodies interpreted despite no environment opt-in; trusted host/CoreLib ordinary methods still native |
| Switch off and unsupported runtime build | Switch-off behavior identical to pinned baseline; unsupported enabled configuration rejected explicitly |
| `.ctor`, `.cctor`, module initializer before first callback | Native entry/first-opcode evidence on each required body; ordinary initialization exceptions copied and next session recovers |
| Direct/interface/default/constrained/delegate/reflection calls | Resolved author body starts in interpreter on cold and warmed repeated paths; private dependencies included |
| `AggressiveInlining`, host generic callback calling a tiny UGC helper | Native JIT inline decision rejects required inlinee; sampled helper body execution and no native body publication |
| UGC ref/value generic bodies and helpers | Definition-module identity and tokens bind execution samples to package hashes; generic adapters audited separately |
| Trusted `List<UGCStruct>`/trusted generic method | Trusted body may JIT/R2R; collectible instantiation does not incorrectly force full-framework interpretation |
| Trusted host/framework R2R enabled; submitted UGC R2R | Host R2R remains usable; production intake rejects native payload; isolated runtime-selection fixture never selects required native body |
| Compiler skip and malformed IL | Exercise actual known skip if a legitimate fixture is accessible; otherwise a test-only scoped interpreter refusal returns `CORJIT_SKIPPED`; required method throws before native JIT, unmarked control may fallback |
| Hot loops, tiering/OSR on, repeated calls | Required body remains bytecode; no required Tier1/OSR native publication; trusted hot-loop native promotion allowed |
| Multicore JIT enabled, concurrent first call | No required cached native winner, no double-policy race; all callers agree on interpreted body/failure |
| 20+ sessions, static/private generic reset, failure recovery | Existing full lifecycle and controlled package suites pass, WeakReference collection observed after stack return; scalar audit data survives without retaining maps |
| Registered policy follow-up | Trusted collectible plugin remains ordinary; package+late private dependency required before prepare; late/downgrade registration fails; unsupported acknowledgement rejects startup |

JIT events named `JITCompilationStarted` are not sufficient negatives: this
base uses the compiler notification machinery for interpreter preparation too.
Record manager/backend plus body identity. Use native `InterpreterStub` and
internal child first-opcode samples with MethodDesc/owner module/token/bytecode
integrity checks, as in the [Release package capture](ios-release-package-entry.md).
Internal calls can reuse the interpreter loop without another stub. Native
publication/inline diagnostics supply the escape-path negatives; functional
counts and unload receipts remain independent from sampled method entries.

The next patch is reviewable when the switch, predicate, selection/fallback
guards and no-inline behavior land together in a separate runtime worktree,
with a portable diff/base, matching-build identities, and the desktop matrix
plus existing lifecycle/package regressions. It then advances to mobile builds.
Production session registration is a following acceptance step, not a claim
earned by the diagnostic switch or the current successful simulator player.
