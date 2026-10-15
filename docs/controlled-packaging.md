# Controlled source/IL packages

This is the current restricted UGC intake profile. Developer-owned C# hot-update
integration is a separate first-class use in [product direction](product-direction.md);
its supported packaging/approval path remains to be delivered. Source language
selection follows the selected compiler's latest stable version. The gameplay
allowlist is a separate API policy, not a source-language version cap.

The local operator-side pipeline for #4 accepts raw C# or managed IL and creates
a versioned package. It never executes an author project, MSBuild target,
analyzer, generator, NuGet restore, or author assembly during intake. This is a
prototype of our controlled server build path, not a network service, approval
signature, interpreter selector, or security sandbox.

## Run the tool

Build the solution first. Its packaging test target stages the five SDK framework
reference assemblies into a known directory; operators can instead point at an
approved SDK's Microsoft.NETCore.App.Ref reference directory. Select the SDK
explicitly as appropriate to the machine, rather than relying on an old global
installation. These PowerShell commands run from the repository root:

```powershell
dotnet build RuneCLR.slnx -c Release
$refs = 'tests/RuneCLR.Packaging.Tests/bin/Release/net11.0/refs'
$contract = 'src/RuneCLR.Abstractions/bin/Release/net11.0/RuneCLR.Abstractions.dll'
dotnet run --project tools/RuneCLR.PackageTool -c Release --no-build -- compile --source samples/Source --id Gameplay --entry-type Gameplay --framework-refs $refs --contract $contract --output artifacts/packages/source
dotnet run --project tools/RuneCLR.PackageTool -c Release --no-build -- validate --manifest artifacts/packages/source/package.json
dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- artifacts/packages/source/package.json artifacts/packages/source/package.json --collect

dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- artifacts/packages/source/package.json --pump --collect
dotnet run --project tools/RuneCLR.PackageTool -c Release --no-build -- import --assembly artifacts/packages/source/Gameplay.dll --id Imported --entry-type Gameplay --framework-refs $refs --contract $contract --output artifacts/packages/imported
```

Output directories must be new. Repeated builds use a different output directory;
existing packages are never overwritten. Compilation diagnostics are JSON with
source labels and one-based line/column positions; failures exit 2 and publish no
package. Source input directories contain only .cs files. Compiler controls,
contract/reference paths and explicit --dependency arguments belong to the
operator; authors must not choose those options in a future server endpoint.

`--pump` runs the same validated versioned package through the host-pumped
session API. A game host can use `MapPackage.FromManifest` followed by
`MapRunner.Start` and its own synchronous frame calls. The
[player acceptance harness](package-execution-tests.md) covers frame deltas,
author-failure recovery and revalidation when a package changes before `Start`.

## Initial supported profile

- Latest stable C# supported by the selected SDK compiler, regular source files,
  Release deterministic AnyCPU library, nullable
  enabled, unsafe disabled. See [the compiler contract](source-compiler.md).
- Fixed reference assemblies: System.Runtime, System.Collections, System.Linq,
  System.ObjectModel, System.Runtime.Extensions, the approved host
  RuneCLR.Abstractions, and explicitly approved private IL dependencies. These
  references are snapshotted, then the compiler sees those same bytes in private
  staging. Arbitrary framework/NuGet compatibility is not promised.
- Every entry/private AssemblyRef must match a full approved reference identity
  or declared private identity. Missing transitive dependencies fail intake.
  A private DLL cannot replace the host contract, framework or tool assemblies.
- Entry is a public, concrete, non-generic, non-nested class directly deriving
  from System.Object and directly implementing the exact host IMapScript.
  It has a public parameterless constructor and public, non-generic void
  OnStart(IMapContext), OnTick(MapTick), OnStop callbacks. Inherited/explicit
  interface callback implementations are outside this first profile.
- PE/metadata checks reject malformed images, mixed-mode/native implementations,
  embedded ReadyToRun/native headers, P/Invoke and InternalCall. Method body,
  exception-region and metadata ranges are checked without Assembly.Load.
  Synthetic native-header tests verify rejection; they are not measurements of
  executing actual crossgen-produced R2R input. Structural checks do not fully
  verify IL instructions, typing or control flow.

## Version and identity

New packages contain package.json and only the entry/private DLLs it declares.
Format version 1, API version 1 and managed-il-gameplay-v1 are explicit compatibility
gates. The manifest lists every file SHA-256, dependency full identity and
producer tool/version/input kind. Provenance includes compiler/reference/input
hashes and logical names, without machine paths. Source hashes cover the UTF-8
encoding of the submitted text; IL hashes cover original DLL bytes.

contentSha256 hashes compact UTF-8 JSON with fixed field order. Arrays are
sorted by ordinal path/input name (input identity/hash break ties); the content
hash field itself is omitted. Whitespace in the supplied JSON and array order
do not change identity; scalar case and source text do. DLLs and source records
already have their own hashes. With identical compiler, contract, references,
source names/text, entry and id, different output directories give the same
package identity. Changing the selected SDK/compiler or references can change it.

The runtime validates compatibility, complete inventory, hashes, private
identities and IL entry structure before creating a collectible context, and
rechecks a previously parsed package before each run. Unknown/duplicate JSON
fields, missing/extra/changed content and invalid paths are rejected. The
versioned manifest is bounded to 1 MiB, content to 256 DLLs/128 MiB with 32 MiB
per DLL. The CLI additionally allows at most 64 private inputs. Filesystem links
are rejected; callers still supply immutable directories without concurrent
replacement. This does not implement race-proof file loading.

Existing unversioned map.json and direct MapPackage constructors remain trusted
local-fixture compatibility APIs. They do not pass through the new managed-IL
intake contract and must not become public author upload endpoints. Compiler
and Roslyn are operator tooling only: RuneCLR.Runtime references the small
RuneCLR.Packages library, not RuneCLR.Compiler or Roslyn.

## Remaining boundaries

Hashes and producer fields prove consistency, not who approved a package. A
server/distribution approval channel is still needed before public intake.
The [gameplay capability policy](capability-policy.md) rejects unsupported static
API routes in actual entry/private IL at packaging and versioned load time.
The preceding structural-only managed-il-v1 packages must be rebuilt/reimported;
the loader rejects that old profile rather than granting it the new restrictions.
Static API checking does not enforce CPU/memory limits, fully verify malicious IL,
or force interpretation. Host runtime enforcement is tracked in #5/#6; worker process/container time/memory limits for
hostile compiler inputs also remain outstanding. Controlled authors are the
prototype's trust model. See [SECURITY.md](../SECURITY.md).

Desktop tests exercise compilation/import, rejection, lifecycle and collection.
The [new Android validation](android-controlled-packages.md) passes the original
22/22 late-IL harness plus 8/8 source/import/rejection/recovery cases with the
Packages host assembly and new gameplay profile. The
[new iOS profile validation](ios-controlled-packages.md) now passes the portable
15/15 player suite on the unpatched source .NET 12 Debug simulator, with
post-install source/IL fixtures, private version/generic state, rejection recovery,
completed retirement and direct interpreter dumps. Trusted Runtime and Packages
remain IL; host/framework native bodies use the matching source compiler.
Physical iOS and Android interpretation remain open.

## Measured initial desktop increment — 2026-10-12

The private official SDK 11.0.100-rc.1.26425.128 builds the complete solution
with zero warnings/errors. The normal lifecycle harness passes 22/22, the new
packaging harness 59/59 (compiler 10, intake 24, manifest 16, pipeline 9), and
the original three sample contexts collect. The packaging regressions include
private version isolation, static reset, deterministic package identity,
source-location diagnostics, failed publication, changed-file recovery, author
exception stop/resource cleanup and next-package recovery, strict
versioned parsing and compatibility with the actual host contract.

CLI compile/validate/import also pass outside the harness; a directory containing
an author csproj is rejected with JSON/exit 2 and no output. The resulting
source/import/source sample sessions each start at 1 and collect. Evidence:
artifacts/packages/cli-6c24ccce247741cbb83ad61b1d25b524. Final normal verification:
artifacts/toolchains/verify-packaging-final.log.

The updated eng/verify-interpreter.ps1 compiles a fresh source package after the
host build, imports its original IL, checks unchanged host files and then runs
source/import/source on the unpatched source .NET 12 Checked layout. The full
existing interpreter harness still passes 22/22; all three controlled package
sessions collect with fresh static state and successful OnStart/OnTick/OnStop
bytecode dumps, without reported UGC JIT fallback. Mode 1 still permits CoreLib
JIT; R2R/tiering are off. Roslyn runs only on the operator SDK runtime.
Upstream base: 0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de. Final evidence:
artifacts/interpreter/20261012-203904-c2fe093a8f884d3584d155bd88dfbce0.
This validates desktop packaging integration, not Android interpretation,
physical iOS, authenticated distribution or execution-budget enforcement.

The later [static gameplay capability increment](capability-policy.md) extends
the packaging harness to 84/84, retains lifecycle 22/22 and repeats the desktop
interpreter source/import/source checks with the new profile. The linked policy
records its acceptance evidence and explicit runtime-enforcement limits.
