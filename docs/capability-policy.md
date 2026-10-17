# Initial gameplay capability policy

This is an additional restricted UGC policy, not the API/feature ceiling for
trusted developer-owned hot updates. A broader trusted integration profile is
planned separately; the current versioned loader still applies this policy.
See [product direction](product-direction.md) for that distinction.

The game API row below is the current prototype host surface. It does not require a game to expose entities, and it does not define the UGC mechanism. A host-defined API is not implemented here. On 2026-10-17 its decided shape is a game-owned shared CLR interface called directly by the script. IMapContext is not renamed.

The operator package tool writes hostInterface and allowedMethods only when both are supplied. Supplying only one of those compile options exits 2 and publishes no package. A repeated or blank allowed method also exits 2 and publishes no package. A source directory that contains a file other than .cs also exits 2 and publishes no package. A source tree nested past 16 directories also exits 2 and publishes no package. A source directory that is a filesystem link, or that contains one, also exits 2 and publishes no package. More than 64 source files, or more than 8000000 source bytes, also exits 2 and publishes no package. A source file that does not compile also exits 2, prints the compiler diagnostic, and publishes no package. Importing a file that is not a managed assembly also exits 2 and publishes no package. Importing an assembly that does not define the entry type also exits 2 and publishes no package. The operator CLI --help exits 0. An unknown command, a missing required option, or a repeated option exits 2. An unknown option, or an option without a value, also exits 2. PackageBuilder does the same. When either field is present, package loading requires both and checks the entry OnStart against that interface and those method names before the gameplay profile. Omitting both leaves an ordinary gameplay manifest and its content hash unchanged. Allowed methods are simple names, not signatures. That OnStart check rejects a call that is not on the named interface and not a method in the entry or a declared private assembly, so a normal gameplay script that also calls approved framework members is not given these fields by default. A configurable allow list that includes the BCL is later work.

HostContractSession can load private assemblies declared by that manifest into the same collectible context. The entry may call methods on those assemblies, and those assemblies may call methods on the entry and on each other. A later Invoke may pass one int to a public void method, and InvokeInt may return one int from a public int method with one int parameter. Either method may also take the host contract before that int. Both are checked before OnStart runs, so a bad later callback does not run the host method. The failed load unloads its collectible context. Open also rejects an unlisted file in the package directory before loading. The message contains missing or extra files, and the host method does not run. Open also rejects a private dependency whose assembly identity differs from the manifest, even when the file hash matches. The message contains identity mismatch, and the host method does not run. Open also rejects a manifest whose format version is not current, even when the content hash matches. The same check requires the current API version and input profile. The message contains Unsupported package format, and the host method does not run. Open also rejects an entry or dependency larger than the assembly size limit, and a set of listed files that would pass the package size limit, before loading those bytes. The message contains size limits, and the host method does not run. Open also rejects a filesystem link in the package directory, and a directory nested past the package limit, before loading. The messages contain filesystem links and nesting limit, and the host method does not run. Open also rejects a producer input kind other than source or il before loading, even when the content hash matches. The message contains Unsupported producer input kind, and the host method does not run. Open also rejects a producer with no references before loading, even when the content hash matches. The message contains Producer references identities are required and bounded, and the host method does not run. Open also rejects a blank or oversized package id before loading, even when the content hash matches. The message contains Missing or oversized id, and the host method does not run. Open also rejects a producer that does not name the supplied contract assembly exactly once, even when the content hash matches. The message contains exactly one shared host contract, and the host method does not run. The session also rejects an entry assembly whose simple name matches the supplied contract assembly before the host method runs. The message contains duplicates the host contract assembly. Open also rejects a blank or oversized producer tool before loading, even when the content hash matches. The message contains Missing or oversized producer.tool, and the host method does not run. Open also rejects a package path with a segment that ends with a dot or a space, even when the content hash matches. The message contains canonical relative DLL, and the host method does not run. The one contract reference must match the supplied assembly's full identity, not only its simple name. A different version does not run the host method. A package compiled with RuneCLR.IMapContext, Log, and SpawnEntity opens in HostContractSession and runs OnStart. Imported IL with those methods also logs ok and spawns fixture. A compiled OnStart can also call Charge(7). Imported IL can call Charge(7) from OnStart. A compiled OnStart can also spawn fixture and destroy that entity. Imported IL can spawn fixture and destroy that entity from OnStart. A compiled OnStart can read MapId when get_MapId is allowed, and the log is fixture. Imported IL can read MapId from OnStart and log fixture. An allow list that names MapId instead of get_MapId is rejected and publishes no package. A later callback can read the stored host MapId and log fixture. Imported IL can read that stored MapId from OnStop. The operator CLI compile command accepts --allowed-method get_MapId, and OnStart logs fixture. The operator CLI import command accepts that name, and OnStart logs fixture. The operator CLI compile command rejects --allowed-method MapId and publishes no package. The operator CLI import command rejects that name and publishes no package. A declared private assembly can read MapId when the entry passes the host and get_MapId is allowed. Imported IL can do the same. A declared private assembly can call Charge(7) when the entry passes the host. Imported IL can do that too. A declared private assembly can spawn fixture, and the entry can destroy that entity. Imported IL can spawn that entity and the entry can destroy it. A declared private assembly can both spawn fixture and destroy that entity. Imported IL can do that too. A declared private assembly can call Log when the entry passes the host. Imported IL can do that too. That host can also cross from one private assembly into a second before Log runs. Imported IL can cross those two private assemblies before Log runs. A second private assembly that calls SpawnEntity while only Log is allowed is rejected and publishes no package. Imported IL is rejected the same way. A second private assembly can read MapId when get_MapId is allowed, and the entry logs fixture. Imported IL can do that too. A second private assembly can call Charge(7) when the entry passes the host. Imported IL can do that too. A second private assembly can spawn fixture and destroy that entity. Imported IL can do that too. A second private assembly can return that EntityId, and the entry can destroy it. Imported IL can return that EntityId too. The operator CLI compile command can pass two private assemblies, and the second can log. The operator CLI import command can do that too. The operator CLI validate command accepts a host-contract package with two private assemblies, and rejects that package after one byte in the second assembly changes. It also rejects a private dependency whose manifest assembly identity no longer matches the DLL, after the content hash is recomputed. It also rejects a published package whose entry file is a filesystem link. The operator CLI validate command also rejects that package after its directories nest past the limit. It also rejects that package when the entry bytes are replaced by an assembly named System.IO and the content hash is recomputed. It also rejects that package when the entry file grows past the assembly size limit, before those bytes are hashed. It also rejects that package after the format version is increased and the content hash is recomputed. It also rejects that package after the producer input kind is changed from source and the content hash is recomputed. It also rejects that package after the producer references are removed and the content hash is recomputed. It also rejects that package after the producer references name another assembly instead of the shared host contract and the content hash is recomputed. It also rejects that package after the package id is blank and the content hash is recomputed. It also rejects that package after the producer tool is blank and the content hash is recomputed. It also rejects that package after the entry path escapes the package directory and the content hash is recomputed. It also rejects that package after an entry path segment ends with a dot and the content hash is recomputed. It also rejects that package after the entry path does not end in .dll and the content hash is recomputed. It also rejects that package after the file list names a different assembly than the entry and the content hash is recomputed. It also rejects that package after the file list hash for the entry disagrees with the entry hash and the content hash is recomputed. It also rejects that package after a private dependency path escapes the package directory and the content hash is recomputed. It also rejects that package after a private dependency is replaced by bytes that are not a PE image and the hashes are recomputed. It also rejects that package after a private dependency is replaced by an assembly named System.IO and the hashes and declared identity are updated to match. It also rejects that package after a private dependency is replaced by an assembly with the entry simple name and the hashes and declared identity are updated to match. It also rejects that package after a private dependency is declared with the shared host contract name and the content hash is recomputed. It also rejects that package after a second private dependency is declared with the first dependency assembly identity and the content hash is recomputed. It also rejects that package after a listed private dependency file is removed from the package directory. It also rejects that package after the producer tool version is blank and the content hash is recomputed. It also rejects that package after the producer sources are removed and the content hash is recomputed. It also rejects a source package after the producer compiler identities are removed and the content hash is recomputed. It also rejects a source package after a producer compiler identity name is repeated and the content hash is recomputed. It also rejects that package after a producer source identity name is repeated and the content hash is recomputed. It also rejects that package after a producer reference identity name is repeated and the content hash is recomputed. It also rejects that package after a second producer reference with a different name still identifies the shared host contract and the content hash is recomputed. It also rejects that package after a producer source digest is not a SHA-256 hexadecimal digest and the content hash is recomputed. A compiled package can store the spawned EntityId and destroy it from a later callback. Imported IL can store that EntityId and destroy it from a later callback. Invoke can then run OnStop on that same opened package and pass the stored context back to Log. Imported IL can run OnStop and log stopped. InvokeInt can call Measure(40) on a compiled package and get 41 back. The operator CLI compile command, run as RuneCLR.PackageTool with --host-interface and --allowed-method, produces that package and Measure(40) returns 41. The operator CLI validate command accepts that manifest and prints its id and content hash. Changing that id without updating the content hash makes validate exit 2, and the error contains content identity. Changing an entry file byte without updating its hash makes validate exit 2, and the error names that file. Adding a file that is not in the manifest makes validate exit 2, and the error contains missing or extra files. Invoke can call Report with the host and 41, and that int reaches Charge. Imported IL can call Report(41) and charge 41. Invoke can call Apply with only 41, and that int reaches Charge. Imported IL can call Apply(41) and charge 41. InvokeInt can call Measure with the host and 40, charge 40, and return 41. Imported IL can do the same. A later callback on that compiled package can call a declared private AddOne and return 41. The operator CLI compile command does the same when that assembly is passed with --dependency. That callback can also cross from one declared private assembly into a second and still return 41. Imported IL can cross those two private assemblies and return 41. A declared private assembly can also call back into the entry and still return 41. A later callback can construct an author Box and return its value. Imported IL can construct that Box and return 41. Compile rejects a later callback that constructs System.InvalidOperationException before publishing a package. The operator CLI compile command exits with that same rejection and publishes no package. A later callback can construct a Box declared in a private assembly and return 41. Imported IL can construct that private Box and return 41. An IL assembly imported with the same host fields also opens, and Measure(40) returns 41. The operator CLI import command produces that package from submitted IL. That imported entry can call AddOne in a declared private assembly and still return 41. The operator CLI import command does the same when that assembly is passed with --dependency. Import also rejects a later callback that constructs System.InvalidOperationException before publishing a package. The operator CLI import command exits with that same rejection and publishes no package. Imported IL can also let a private assembly call back into the entry and return 41. An OnStart failure after the host method runs does not return the session and also unloads that context. The error names that callback and the rejected member. A call from that callback into a declared private assembly is included, as is constructing a type declared there. A private call to System.IO.File.ReadAllText is named and that failed load unloads. OnStart may construct a type declared by the entry or a private assembly; that constructor is checked, and a framework constructor is still rejected. The called method is checked with the same host-contract rules before it runs, so a call into the BCL, including System.IO, is still rejected. Copying a framework assembly into the package does not approve it. This session does not apply the gameplay member allow list. The package validator accepts an OnStart call into the entry or a declared private assembly and checks that method before accepting it. It also checks a later public callback on the entry when the callback takes nothing, the host, one int, or the host and one int. An unsupported public method is left unchecked. A call from a checked callback into a declared private assembly is checked too. A BCL call such as System.IO.File.ReadAllText is still rejected. PackageBuilder.Compile runs that later-callback check when both host fields are supplied. A supported OnStop that calls an unlisted host method is rejected before publication, and the error names that callback and the member. Gameplay validation is unchanged.

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
