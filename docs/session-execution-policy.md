# Host-selected session execution policy

RuneCLR now accepts an explicit execution policy for each run. The default
preserves ordinary runtime selection and works with the stock SDK. A host can
request interpretation before loading author assemblies:

~~~csharp
var options = new MapRunOptions
{
    ExecutionPolicy = MapExecutionPolicy.RequireInterpreter
};
var result = new MapRunner().Run(package, options);
~~~

The option belongs to the host, not the package manifest or author code.
There is no environment variable that silently changes RuneCLR's default.
Runtime diagnostic switches are separate from this option and do not establish
that a required session was acknowledged or executed by the interpreter.

## Trusted CoreLib bridge

[RequiredInterpreterBridge](../src/RuneCLR.Runtime/RequiredInterpreterBridge.cs)
binds only these exact private methods declared on the trusted
typeof(AssemblyLoadContext), using typed CreateDelegate calls:

~~~csharp
private static AssemblyLoadContext RuneCLR_CreateInterpreterRequired(
    string name, Func<AssemblyLoadContext, AssemblyName, Assembly?> managedResolver);
private static int RuneCLR_GetExecutionPolicyVersion();
private int RuneCLR_GetExecutionPolicy();
~~~

The method visibility, static/instance shape, parameter and return types are
checked. Version must be 1. The factory must return a collectible context whose
instance query reports native policy 1. Missing or incompatible support throws
PlatformNotSupportedException; it never falls back to ordinary loading. Invalid
enum values throw ArgumentOutOfRangeException. Binding occurs before
MapRunner opens author files; context acknowledgement occurs before it loads
the entry assembly. Package intake can read manifests and validate IL before
MapRunner is called.

[MapLoadContext](../src/RuneCLR.Runtime/MapLoadContext.cs) returns an ordinary
subclass for the default option and the CoreLib factory context for a required
run. The factory receives the existing host resolver callback, with the actual
context passed into each resolution. Its Load override resolves declared
private dependencies before default-context collisions can win. Contract
sharing, full identity/hash checks, framework binding and native-load rejection
retain their existing behavior; see [package resolution](package-resolution.md).

Bridge delegates are local to a run. There is no static context or resolver
root. A created context that fails acknowledgement is unloaded. Normal and
managed-failure cleanup retain the existing collectible-session ownership.
MapRunReport returns only the policy enum and integer acknowledgement version
(0 for ordinary, 1 for acknowledged required sessions), alongside the existing
host-owned report. These fields are not a substitute for native execution
evidence. Interpretation does not establish a complete security sandbox or
force cooperative author code to return.

## Command-line selection

The runtime harness, sample host and player package harness accept
--require-interpreter anywhere in their argument list. Existing mobile
--packages arguments remain valid. Examples after a Release build:

~~~powershell
dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build -- --late-map tests/RuneCLR.LateMap/bin/Release/net11.0/map.json --require-interpreter
dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --collect --require-interpreter
dotnet run --project tests/RuneCLR.PackageExecution.Tests -c Release --no-build -- --packages <fixtures> --require-interpreter
~~~

After a run has obtained native policy acknowledgement, each harness emits
SESSION_EXECUTION_POLICY required-interpreter version=1 once. An unsupported
stock runtime emits no acknowledgement marker and loads no author assembly
through that attempted run. The lifecycle harness separately tests unsupported
preflight on stock CoreLib and real required-policy execution when version 1 is
available, plus invalid-enum rejection before opening a missing author path.

## Measured stock regression — 2026-10-13

The private SDK at artifacts/toolchains/dotnet-11-rc1/dotnet.exe was version
11.0.100-rc.1.26425.128, running .NET 11.0.0. It was selected by an absolute
path or process-local PATH; the installed runtime was not replaced.

Release build and the existing eng/verify.ps1 completed with exit 0 and no
build warnings/errors: 24/24 lifecycle tests (including the late-built map),
84/84 packaging tests, 15/15 player package tests, and all three sample contexts
collected. This establishes ordinary stock behavior and the two new policy
regressions. It does not establish stock interpreter execution.

An explicit stock sample invocation with --require-interpreter returned exit 1,
reported the missing fixed CoreLib factory for all three attempted runs, and
produced no script-start or native-acknowledgement marker. Original logs and
source/output SHA-256 identities are recorded in the
[stock receipt](../artifacts/session-policy-stock-20261013.json).

Matching Windows x64 Checked candidate
5972a86966e56ae5f468a3e042327f0051e923d5 now passes actual required-session
acceptance and an independent raw-evidence audit: 24/24 lifecycle, 15/15 player
package tests, three collected sample contexts, the collected late-built map,
and source/import/source with three collected contexts. Every entry point
acknowledges native policy version 1 with InterpMode=0 and the global collectible
diagnostic switch 0. Callback/private/generic bytecode evidence is positive,
while trusted MapRunner remains native. The first candidate's trimmed-away
bridge failure remains recorded; the accepted build adds three exact method
roots. See the [matching build and acceptance](runtime-session-policy-build.md)
for source, layout identities, logs and measured limits.

The matching [iOS Release simulator player](ios-session-policy-acceptance.md)
now passes the current lifecycle, package, sample and selection lanes. Its
[separate refusal/recovery run](ios-session-policy-refusal.md) also passes.
The [Android Checked player](android-session-policy-validation.md) passes
the same production suites and five selection/refusal controls. The later
[Android Release transport experiment](android-session-policy-release-entry-preparation.md)
passes debugger attachment/detachment followed by twenty successful sessions.
A separate [Release entry capture](android-session-policy-entry.md) now samples
nine fixture method groups, followed by an independent
[non-debugger selection run](android-session-policy-release-functional.md)
with twenty exact sessions/collections and unchanged installed bytes. These
records identify the actual matching runtime and execution evidence for each
lane. The subsequent [independent Release production and control runs](android-session-policy-release-production.md)
pass 24/24 lifecycle, 15/15 packages, three collected samples, scoped refusal
followed by twenty successful recovered collections, ordinary JIT and unmarked
fallback. These results use the same frozen APK and preserve the earlier
selection fixture's separate entry scope. Production/refusal method-entry
samples and real-device validation remain outstanding. The proposed
[session instruction budget](runtime-session-budget-plan.md) requires further
native/EH/finalizer work and does not follow automatically from execution selection.
The stock receipt remains the original stock-only snapshot, including this
document's hash before the native acceptance update.

An independent ordinary-stock recheck on 2026-10-13 again completed
eng/verify.ps1: 24/24 lifecycle, 84/84 packaging, 15/15 player cases and
three collected sample contexts. The [new original log](../artifacts/toolchains/verify-20261013-normal-baseline-b999cc8285084d16aed0663203cd08a8.log)
is separate from the frozen mobile host and original stock receipt. This check
does not establish stock interpreter execution or mobile execution.
