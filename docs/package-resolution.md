# Explicit package dependency resolution

Implemented on 2026-10-12 as the first portable packaging increment under
[#4](https://github.com/ReneeGA2020/RuneCLR/issues/4). The runtime no longer uses
`AssemblyDependencyResolver` or a map `.deps.json`. This resolves the observed
Android unsupported-API problem without introducing a desktop hostpolicy
dependency. Controlled compilation and approved IL-only intake remain pending.

## Manifest

The existing minimal manifest remains valid for trusted packages without private
dependencies. Packages with private dependencies declare every private assembly:

```json
{
  "id": "example",
  "entryAssembly": "Example.dll",
  "entryType": "Example.Script",
  "entrySha256": "<64 hexadecimal characters from the entry DLL>",
  "dependencies": [
    {
      "path": "lib/Example.Helpers.dll",
      "assemblyName": "Example.Helpers, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null",
      "sha256": "<64 hexadecimal characters from the dependency DLL>"
    }
  ]
}
```

Hash placeholders above must be replaced with actual SHA-256 values. The
`assemblyName` is the full metadata identity, not just a filename. Paths are
relative to the manifest directory, use forward slashes, and must stay within
that directory after normalization. Absolute paths, backslashes and colon
syntax are rejected. Hash and identity comparisons are case insensitive.

`entrySha256` is optional for compatibility with existing trusted local fixtures;
distributed packages should supply it. Every declared private dependency requires
a hash. Missing files, mismatched metadata/hashes, duplicate simple names and
identities reserved by the entry, shared contract or framework are rejected.
`FromManifest` validates before an ALC exists; `MapRunner.Run` revalidates so
direct `MapPackage` construction cannot bypass checks. Invalid packages throw
input/IO exceptions before a session result is created.

## Binding and ownership

The shared `RuneCLR.Abstractions` identity must match the host contract. Each
session loads the entry and declared private dependencies into its collectible
context. Requested private versions, culture and public-key tokens must match;
the resolver does not silently unify different private versions. Unknown private
names throw rather than returning arbitrary Default-context assemblies, even
if a matching DLL is already loaded by the host. Merely copying a DLL beside the
entry is no longer sufficient: existing implicit-private packages must add their
dependency declarations.

Trusted framework names come from `Microsoft.NETCore.App.deps.json` beside
CoreLib or in `AppContext.BaseDirectory`. Mobile app packaging must include that
official host-owned inventory. Both runtime-pack `Microsoft.NETCore.App.Runtime.*`
and source-built `Microsoft.NETCore.App/<version>` inventory layouts are supported.
Map `.deps.json` files never grant framework status. Framework names use Default
and normal runtime version binding; this is routing, not an API capability list.

Resolver state contains paths and metadata identities, not collectible loaded
assemblies, map types or delegates. Host result ownership and post-stack-return
collection observation are unchanged. Forced GC remains diagnostic.

## Trust and verification

Package directories and the host inventory are trusted immutable inputs. Lexical
path containment and pre-load hashing do not prevent symlink replacement or
filesystem races. Hashes establish content consistency, not server approval.
The legacy fixture path does not implement IL-only/native-body rejection.
New [versioned packages](controlled-packaging.md) apply structural managed-IL
intake and entry compatibility checks; neither path prevents script-initiated
dynamic loading. The host still does not force interpretation
or isolate hostile scripts. See [the security model](../SECURITY.md).

Windows Release verification passes **22/22**, including late-built IL and
normal lifecycle/resource recovery. The private pinned Checked mode 1 runtime
also passes **22/22**, with successful interpreter bytecode dumps and no reported
map JIT fallback. Commands:

```powershell
./eng/verify.ps1
./eng/verify-interpreter.ps1 -RuntimeRepo <separate-runtime-checkout>
```

Final interpreter follow-up evidence: `artifacts/interpreter/20261012-183757-ee8c388a673247528218c43cef814585`.
After selecting the official .NET 11 RC1 SDK for host compilation, the same
private runtime passes 22/22 again; evidence:
`artifacts/interpreter/20261012-192907-c98f7819d5f247278ed61ec44ddebe75`.
It uses the same unpatched upstream base and layout described in
[the original desktop experiment](interpreter-experiment.md). The prior
performance measurements predate this resolver and do not measure its overhead.
The first new-resolver private-layout attempt rejected the source-built inventory
because it only recognized runtime-pack library names (9/22). Supporting the
actual source-built `Microsoft.NETCore.App/<version>` shape fixed it; the failed
logs remain under `artifacts/interpreter/20261012-182826-b3306afbedf64032b6f7decd968cb2c8`.
The [Android full-harness follow-up](android-lifecycle-experiment.md) passes
21/21 and 22/22 with post-install IL on official JIT-capable CoreCLR. Android
interpretation is still open. The [iOS simulator follow-up](ios-simulator-experiment.md)
also passes the actual full harness with selective host R2R/Runtime IL and
post-install scripts. It retains the all-R2R host boundary crash and does not
establish physical-device acceptance.
