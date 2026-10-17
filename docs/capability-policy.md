# Initial gameplay capability policy

This is an additional restricted UGC policy, not the API/feature ceiling for
trusted developer-owned hot updates. A broader trusted integration profile is
planned separately; the current versioned loader still applies this policy.
See [product direction](product-direction.md) for that distinction.

The game API row below is the current prototype host surface. It does not require a game to expose entities, and it does not define the UGC mechanism. A host-defined API is not implemented here. On 2026-10-17 its decided shape is a game-owned shared CLR interface called directly by the script. IMapContext is not renamed.

The operator package tool writes hostInterface and allowedMethods only when both are supplied. PackageBuilder does the same. When either field is present, package loading requires both and checks the entry OnStart against that interface and those method names before the gameplay profile. Omitting both leaves an ordinary gameplay manifest and its content hash unchanged. Allowed methods are simple names, not signatures. That OnStart check rejects a call that is not on the named interface and not a method in the entry or a declared private assembly, so a normal gameplay script that also calls approved framework members is not given these fields by default. A configurable allow list that includes the BCL is later work.

HostContractSession can load private assemblies declared by that manifest into the same collectible context. The entry may call methods on those assemblies, and those assemblies may call methods on the entry and on each other. A later Invoke may pass one int to a public void method, and InvokeInt may return one int from a public int method with one int parameter. Either method may also take the host contract before that int. Both are checked before OnStart runs, so a bad later callback does not run the host method. The failed load unloads its collectible context. The error names that callback. A call from that callback into a declared private assembly is included, as is constructing a type declared there. OnStart may construct a type declared by the entry or a private assembly; that constructor is checked, and a framework constructor is still rejected. The called method is checked with the same host-contract rules before it runs, so a call into the BCL, including System.IO, is still rejected. Copying a framework assembly into the package does not approve it. This session does not apply the gameplay member allow list. The package validator accepts an OnStart call into the entry or a declared private assembly and checks that method before accepting it. It also checks a later public callback on the entry when the callback takes nothing, the host, one int, or the host and one int. An unsupported public method is left unchecked. A call from a checked callback into a declared private assembly is checked too. A BCL call such as System.IO.File.ReadAllText is still rejected. Gameplay validation is unchanged.

The controlled-author profile for [#5](https://github.com/ReneeGA2020/RuneCLR/issues/5)
adds a static API check to source/IL packaging and to versioned package loading.
It is implemented in
[GameplayCapabilityPolicy](../src/RuneCLR.Packages/GameplayCapabilityPolicy.cs).
The loader checks actual entry/private DLL bytes after integrity validation,
before creating a collectible context. A producer claim or a recomputed package
hash cannot authorize a denied API. No author assembly is loaded during checking.

The profile identifier is `managed-il-gameplay-v1`; format and game API versions
remain 1. Older `managed-il-v1` versioned packages must be rebuilt or reimported
through the operator tool. Their structural-only profile is rejected by the new
loader. The trusted legacy `map.json` and direct `MapPackage` fixture APIs remain
outside this profile and must not serve as author upload endpoints.

## Supported surface

The initial library surface is deliberately small. The type/member tables in the
checker are authoritative; an assembly being a compiler reference does not make
every one of its APIs available to a packaged script.

| Route | Initial policy |
| --- | --- |
| Game APIs | Shared `IMapScript`, `IMapContext`, `EntityId`, `MapTick`; synchronous lifecycle, entities, logging, cooperative charging |
| Computation | Primitive values, strings, selected math/time/array operations and generic collections/interfaces |
| Author failures | Ordinary exceptions and approved exception constructors/message access; host results keep only error text |
| Script helpers | Constructors, callbacks, static initializers, private helpers, nested types, generic definitions/instantiations, and declared private IL dependencies are checked |
| Reflection and activation | Deny `Object.GetType`, `Type`, reflective invocation/activation and unapproved reflection members |
| Loading and process authority | Deny assembly loading, filesystem/network access, process/environment control and runtime-management APIs |
| Background execution | Deny tasks, threads, timers, delegate-based work, async infrastructure and thread/context static state |
| Retirement | Deny script finalizers and module initializers; static state still belongs to the collectible session |
| Native and unsafe routes | Structural intake denies R2R/native/mixed-mode implementations and P/Invoke/InternalCall; capability checking denies unsafe signatures and unsupported IL call routes |

Metadata-only compiler/assembly attributes are explicitly allowed where required
for supported C# output, including C# 13 `ParamCollectionAttribute`; this does
not allow general reflection or impose a language-version ceiling. String
interpolation has a specific compiler-handler allowance. LINQ, arbitrary
framework/NuGet APIs and custom delegate declarations are outside the initial
profile; use ordinary loops and supported collections.

Every external type/member reference is checked, including unused metadata.
This avoids deciding authority from entry callback names or only scanning calls
that the author says will execute. Unsupported code in a private dependency is
rejected even if the entry does not invoke it. Dependency identities are checked
against actual packaged IL, not names invented in provenance.
Private assembly names reserve `System.*`, `Microsoft.*`, `RuneCLR.*` and the
framework facade names. Use game/project names for private libraries.

Member approval uses declaring type and member name, followed by decoded
signature-type checks; it does not enumerate every overload's exact signature.
There are no approved framework fields (for example, use `TimeSpan.FromSeconds(0)`
instead of `TimeSpan.Zero`). Signature blobs are limited to 512 bytes, nested
type decoding to 64 levels/1024 active specification bytes, and capability error
messages to 2048 characters. Custom-attribute values are not semantically decoded.

## Enforcement and limits

| Layer | What it establishes | What remains open |
| --- | --- | --- |
| Fixed C# compilation | Language/options/reference snapshots; no submitted builds or generators | Compiler-worker CPU/memory containment |
| IL structural intake | Supported managed PE/metadata and entry shape; no author native bodies | Full IL semantic/type/stack verification |
| Capability checker | Approved static type/member/signature/IL routes across every packaged assembly | Runtime vulnerabilities, malicious malformed IL, authentication and filesystem races |
| Package resolver | Declared private identities, shared host contract, bounded inventory and integrity | Permission isolation and comprehensive runtime enforcement |
| CoreCLR execution | Measured interpreter selection in separately recorded experiments | Author-resistant selection and hard CPU/memory budgets |
| Host lifecycle | Ordinary managed error reporting, stop/resource cleanup and collection observation | Dead loops, blocking calls, process failures and arbitrary allocations |

The host still does not force interpretation. Desktop JIT execution of a checked
package is useful development evidence, not acceptance of the interpreted
execution policy. Runtime constructors, generic instances, framework native
calls and private dependencies need execution-selection/accounting coverage in
#5/#6; static rejection does not supply that coverage.

The packaging suite through 101/101, commit 76852ad, measures stock desktop JIT. That is not interpreter evidence and it is not an iOS result. The exception-filter case added after that measurement is also desktop JIT only.

The allowlist reduces accidental access to unsupported process APIs for
controlled authors. It does not make arbitrary public hostile IL safe. Even
allowed string/collection operations can allocate heavily or take excessive
time; `Charge()` remains cooperative. Host framework and contract bytes are
trusted inputs. Hashes record consistency, not server approval.

A coarse per-callback interpreter deadline is the scheduled UGC anti-freeze limit, tracked by issue 16. It is not implemented. One untrusted synchronous callback should stop so it cannot wedge the player machine or a server thread. Exact milliseconds are not required. The host decides whether a cutoff drops that call or ends the match. Trusted code is not limited. API call quotas stay in the host. `Charge()` is not that limit.

## Reproduction

Run `./eng/verify.ps1` with an explicitly selected compatible SDK. The executable
packaging harness includes allowed computation/lifecycle and denied-API cases,
source/import rejection before publication, private-dependency coverage and
loader checks after an attacker recomputes hashes.

Use `./eng/verify-interpreter.ps1 -RuntimeRepo <separate-runtime-checkout>` for
the pinned desktop interpreter experiment. The
[new Android profile validation](android-controlled-packages.md) passes 8/8
controlled cases alongside the 22/22 late-IL lifecycle harness. It uses a
JIT-capable x64 emulator. The
[iOS new-profile validation](ios-controlled-packages.md) passes 15/15 on the
unpatched source .NET 12 Debug ARM64 simulator, including rehashed forbidden
entry/private helpers and next-package recovery, with direct script/private
generic interpreter evidence. Android interpretation and physical iOS
acceptance remain open. See [the packaging contract](controlled-packaging.md),
[CoreCLR integration](coreclr.md) and [SECURITY.md](../SECURITY.md).

## Measured desktop increment - 2026-10-12

The final official RC1 SDK `11.0.100-rc.1.26425.128` verification builds with
zero warnings/errors, passes **84/84 packaging tests** (25 capability cases),
passes **22/22 lifecycle tests**, and observes all three sample contexts collected.
The capability regressions include rejected hidden/constructor/generic APIs,
unused private code, recomputed entry/private content hashes, structural-profile
downgrade, framework-token spoofing and full private identity binding.
Log: `artifacts/toolchains/verify-capability-final.log`.

The unpatched pinned source .NET 12 Checked interpreter verification also
passes 22/22 plus source/import/source new-profile sessions, each starting with
static count 1 and collecting. All three callbacks have successful interpreter
bytecode dumps; no reported UGC JIT fallback is observed. Mode 1 permits CoreLib
JIT and does not enforce an author-resistant interpreter policy. Runtime base:
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. Evidence:
`artifacts/interpreter/20261012-210157-6a3b8937480c460aaf3e220cf24c5e92`.
Host/runtime source and artifact hashes are retained there; the host snapshot
includes preserved uncommitted work. No runtime patch is introduced by this gate.
