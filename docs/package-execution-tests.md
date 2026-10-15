# Controlled package execution acceptance

The same player harness exercises versioned controlled packages on desktop,
Android and iOS. Operator compilation runs separately; the player test executable
references only RuneCLR.Runtime and RuneCLR.Packages and their shared contract.
Roslyn and RuneCLR.Compiler are absent from its application directory, loaded
assemblies and loaded assembly references.

The harness retains host-owned reports, strings and weak unload observations.
Each completed session returns from its lifecycle callback before diagnostic GC; collection
therefore also checks that the retained results do not root script instances,
private assemblies or script exceptions. Diagnostic GC is not a gameplay policy.
The optional `--pump` mode also retains the stopped session object during
collection and validates the host-driven lifecycle.

## Operator fixture generation

Build from the repository root with the selected trusted SDK:

```powershell
dotnet build tools/RuneCLR.PackageFixtures -c Release
dotnet build tests/RuneCLR.PackageExecution.Tests -c Release
$fixtureOutput = Join-Path $PWD ("artifacts/package-execution/" + [Guid]::NewGuid().ToString("N"))
dotnet run --project tools/RuneCLR.PackageFixtures -c Release --no-build -- --framework-refs tools/RuneCLR.PackageFixtures/bin/Release/net11.0/refs --contract src/RuneCLR.Abstractions/bin/Release/net11.0/RuneCLR.Abstractions.dll --output $fixtureOutput
dotnet run --project tests/RuneCLR.PackageExecution.Tests -c Release --no-build -- --packages $fixtureOutput
```

The generator requires a new output directory and never overwrites one. Both
projects are included in `RuneCLR.slnx`; `eng/verify.ps1` generates a unique
fixture collection on each run and invokes the player. The desktop CI workflow
also runs both tools on Windows, Linux and macOS.

The generator build stages the same five fixed framework reference assemblies as the
[controlled compiler](controlled-packaging.md). Supply the approved contract
explicitly. Generation uses fixed operator-owned C# strings; no author project,
generator, build script or configuration executes.

By default the output root contains nine package directories and `fixtures.json`. Each
package contains only `package.json` and its declared DLLs, with dependencies
under `lib/`. The receipt records generation UTC, operator runtime version,
contract identity/image SHA-256, and each manifest hash/content identity.
Individual manifests record compiler, source, fixed reference and actual private
dependency identities/hashes. The receipt is evidence, not an approval signature.

| Directory | Input and expected behavior |
| --- | --- |
| source | Controlled C# compilation; normal synchronous lifecycle |
| import | Raw IL from source, imported through the same controlled builder |
| failure | Managed author exception after creating a host entity |
| tampered | Source DLL changed without updating its manifest hash; reject |
| forbidden | Replaced entry with hidden GC.Collect, then recomputed hashes; reject |
| private-a | Actual private SharedGameplay 1.0.0.0 with ordinary/generic statics |
| private-b | Same private simple name, version 2.0.0.0 and distinct behavior |
| private-import | Imported private-a entry with its declared version-1 helper |
| private-forbidden | Replaced/rehashed private helper with hidden GC.Collect; reject |

`--include-pumped` adds three valid controlled packages: `frames` records the
host's tick index, delta ticks and accumulated delta; `tick-failure` throws on
the second tick; `stop-failure` throws from `OnStop`. Their source passes the
same existing compiler, IL and capability gates. The extended collection has
twelve packages. The default generator remains nine packages for existing
acceptance drivers.

The forbidden fixtures deliberately bypass PackageBuilder admission only inside
this operator test tool. They model rehashed attacker inputs and are not runnable
approved packages. Keep this fixture collection separate from any production
publication endpoint. Hashes describe integrity and do not confer trust.

## Player acceptance

The public mobile bridge entry point is
`RuneCLR.PackageExecution.Tests.PackageExecutionHarness.Run(string[] args)`.
Call it with `--packages` and the fixture root. The normal executable entry point
forwards the same arguments. Successful cases in the original suite use two ticks, release the
created host entity, then observe completed collectible-context retirement.

The fifteen cases cover source/import/source with fresh static state; managed
failure followed by a valid session; integrity and rehashed capability rejection
followed by recovery; private A/B/A/import binding with ordinary and generic
static reset; private capability rejection followed by recovery; and absence
of operator/compiler tooling. Normal exit 0 requires all cases to pass:

```text
15/15 package execution tests passed.
```

Normal source logs are `starts=1`, `tick=0`, `tick=1`, `stopped`. Private helpers
produce `A:1:1` or `B:1:1`, followed by `stopped`; the final two counters cover
ordinary and closed-generic static state. Failure logs `stopped-after-error`.
Script callback types are `GameScript`; private helper types are `SharedHelper`
and `GenericCounter<T>`. Interpreter diagnostics can check `GameScript.OnStart`,
`GameScript.OnTick`, `GameScript.OnStop`, `SharedHelper.Read` and
`GenericCounter<T>.Next` directly.

## Host-pumped packages

Generate the extended fixture collection in a fresh directory, then run the
same compiler-free player with `--pump`:

```powershell
$pumpedFixtures = Join-Path $PWD ("artifacts/package-execution/pumped-" + [Guid]::NewGuid().ToString("N"))
dotnet run --project tools/RuneCLR.PackageFixtures -c Release --no-build -- --framework-refs tools/RuneCLR.PackageFixtures/bin/Release/net11.0/refs --contract src/RuneCLR.Abstractions/bin/Release/net11.0/RuneCLR.Abstractions.dll --output $pumpedFixtures --include-pumped
dotnet run --project tests/RuneCLR.PackageExecution.Tests -c Release --no-build -- --packages $pumpedFixtures --pump
```

`--require-interpreter` can be added on a matching private runtime. The normal
fifteen cases use `MapRunner.Start`, host-scheduled `Tick(delta)` and `Stop`
where execution is expected; pre-execution rejection cases remain admission
checks. Seven additional groups cover overlapping source and private-version
sessions, stopping before any tick, observable 5ms/17ms deltas despite
`TickCount = 0`, tick/stop failure followed by recovery, and three changes after
initial package validation: entry bytes, a validly resealed changed manifest,
and the host `MapPackage` record snapshot. These last three are rejected by
`Start` before any collectible assembly load, followed by a fresh valid package.
The compiler-absence check runs after all cases.

```text
22/22 package execution tests passed.
```

The extra fixtures are required; `--pump` on an old nine-package collection
fails rather than skipping the new cases. Keep package directories immutable
for the active session's lifetime, as required by the existing resolver's trust
model. Pre-start revalidation does not establish protection against filesystem
races or changes during lazy dependency loading.

On 2026-10-15, Windows stock RC1 and the matching private
`20405f7ae23e183e038703aa5e356b3310fef427` Release layout both pass synchronous
15/15 and pumped 22/22, with exit 0 and empty stderr. The pumped cases check
24 completed context collections while retaining stopped sessions. The required
lane acknowledges native execution policy version 1 with both global
`InterpMode` and `RuneCLRInterpretCollectible` set to zero. Sixty-nine recorded
player, fixture and source inputs are unchanged before/after; exact runtime
source/build/layout provenance passes freeze/check. These package cases have
`PrototypeBudget = null`; the separate native-budget probes do not establish
the controlled-package/native-budget combination. No fresh author-method native
entry or mobile execution evidence is claimed here.

Evidence under `artifacts/host-pumped-packages/`:

- `20261015-package-lanes-attempt1/`: four lane streams/process records, frozen
  source, before/after input inventories and Release provenance. The final
  player build includes the compiler-absence check after the extra cases.
- `20261015-full-verification-attempt1/verify.log`: full Release build,
  37/37 lifecycle, 84/84 packaging, 15/15 synchronous and 22/22 pumped player
  cases, plus six sample collections; zero warnings/errors.
- `20261015-generator-controls-attempt1/`: default nine-package generation,
  duplicate-flag rejection with no publication, and missing-extra-fixture
  rejection.

`eng/verify.ps1` and the CI matrix now generate the extended fixtures and run
both player modes. The CI configuration is updated; hosted CI was not run as
part of this local acceptance.

## Mobile and interpreter evidence

The later [controlled-package native-budget acceptance](controlled-package-native-budget.md)
adds `--native-budget` to `--pump --require-interpreter`: 33/33 Windows cases
and twenty-five collected native-budget sessions now pass. Generate its
additional approved fixtures with `--include-budget`; optional
`--budget-evidence <NEW directory>` records scalar ledgers. The original
15/22-case modes remain unbudgeted and unchanged.

Build and install the player harness before generating the fixture collection
when testing new IL after host installation. Record the host build/install UTC
and hashes, generate with the separate operator tool, then transfer only the
fixtures into application-owned storage. Run the harness against that storage
path. Do not package the operator executable, compiler, reference pack or Roslyn
into the mobile application.

The staged IL contract and installed R2R contract may have different byte hashes
while retaining the same full identity/API. Runtime compatibility is checked
against the actual host contract identity; compilation input hashes describe
the staged approved image. Keep both images' provenance distinct.

A successful stock desktop/mobile run establishes package admission and
lifecycle behavior on that configuration. It does not prove interpretation,
physical iOS-device support, hard CPU/memory budgets or a security sandbox.
Use runtime diagnostics and the [interpreter validation](interpreter-experiment.md)
for execution-path evidence. The [capability policy](capability-policy.md)
describes the static gate and its limits.

`eng/verify-interpreter.ps1 -RuntimeRepo <separate-runtime-checkout>` also runs
these 15 cases on the pinned private .NET 12 Checked runtime. It checks successful
interpreter dumps for the script callbacks and both private helper methods,
rejects reported UGC JIT fallback, and retains the fixture receipt and player
hash in the evidence directory. Mode 1 allows CoreLib JIT. Its unchanged-host
checks include the new player harness output.

## Recorded desktop baseline

On 2026-10-12 both new projects built using the private official
`11.0.100-rc.1.26425.128` SDK with zero warnings/errors. Fresh fixture generation
and stock Windows x64 execution passed all 15/15 cases, including actual private
dependency version isolation, generic reset, both rehashed rejection paths and
retirement after the author exception. Initial fixture evidence is at
`artifacts/package-execution/20261012-213007/fixtures.json`.

The integrated `eng/verify.ps1` run also builds with zero warnings/errors and
passes lifecycle 22/22, packaging 84/84 and player acceptance 15/15, with all
three sample contexts collected. Log:
`artifacts/toolchains/verify-package-execution-final.log`.

The expanded private interpreter launcher completed with exit 0 on the
unpatched pinned .NET 12 Windows x64 Checked runtime. It retains lifecycle
22/22 and source/import/source collection and additionally passes player
acceptance 15/15. Successful callback, `SharedHelper.Read` and
`GenericCounter<int>.Next` bytecode dumps are present; no reported UGC JIT
fallback was found. Mode 1 permits CoreLib JIT. Evidence:
`artifacts/interpreter/20261012-package-execution/evidence.json` and
`package-execution.log` in that directory. Runtime source remains at
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`.

The separate [iOS simulator lane](ios-controlled-packages.md) now passes the
same 15/15 cases on the unpatched pinned .NET 12 Debug ARM64 runtime. The
installed bundle is unchanged, fixtures were produced after installation,
native compilation is disabled, and all script callbacks/private helpers have
successful interpreter dumps. This establishes the new-profile simulator lane;
physical-device acceptance and Android interpretation remain open.
