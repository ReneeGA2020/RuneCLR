# Shared UGC API decisions and reflection probe

This work follows [the product direction](product-direction.md). It adds a
shared decision contract and a trusted-boundary reflection experiment. It does
not enable general reflection in the shipped gameplay profile.

## Implementation sequence

1. [Issue #18](https://github.com/ReneeGA2020/RuneCLR/issues/18): extract target,
   operation and decision values, adapt the existing gameplay policy, and use
   the same evaluator from IL inspection and reflection target checks.
2. [Issue #19](https://github.com/ReneeGA2020/RuneCLR/issues/19): establish the
   supported runtime reflection boundaries with ordinary author C# code. The
   initial trusted-boundary probe is an experiment toward this issue.
3. [Issue #20](https://github.com/ReneeGA2020/RuneCLR/issues/20): implement
   composable include/exclude rules after default, precedence, signature and
   wildcard semantics are specified. No rule parser is implemented here.

These are sub-issues of [#5](https://github.com/ReneeGA2020/RuneCLR/issues/5).
Trusted developer-owned hot updates remain independent of these UGC rules.

## Decision contract

IApiAccessPolicy.Evaluate accepts an ApiTarget and an ApiOperation and returns
an ApiDecision. Targets contain strings/value-only declaration signatures:
assembly identity, type name, member kind/name, return and parameter types,
generic arity and instance/static shape. There are no Assembly, Type,
MemberInfo or script-object references in the decision values. Method signatures
use generic declaration parameters (!0/!!0), full type names and array/byref
suffixes; the initial policy still matches member names rather than overloads.
Custom modifiers and constructed MethodSpec rule matching are not implemented
as new permissions. Existing signature/IL restrictions still apply.

GameplayCapabilityPolicy.CreateApiPolicy creates an immutable adapter of the
existing managed-il-gameplay-v1 surface. Its script identities must be derived
by a trusted caller from validated script bytes. Passing a claimed identity to
this factory is not evidence that a DLL was validated or interpreted. Assembly
names, type/member names and framework tokens are compatibility policy inputs,
not authentication of an arbitrary file with matching metadata.

The existing Validate entry point and versioned loader continue to select that
fixed profile. ValidateWithApiPolicy lets trusted integration code exercise a
different evaluator within the managed-IL envelope; it neither selects a new
versioned package profile nor automatically permits author reflection/loading.
Host-contract callback validation remains a separate additional gate.

An author-defined ABC does not need a predeclared name: the legacy evaluator
recognizes validated script identities. The member names allowed on external
framework/host types remain restricted. This identity classification is an
adapter of the current intake, not the long-term requirement that authors keep
all dynamically loaded assemblies in a hand-maintained permission list.

## Trusted reflection probe

ReflectionAccessProbe in RuneCLR.Runtime checks actual runtime reflection
metadata before executing its own operations. It supports method invocation,
construction, field reads/writes and property accessors. It also produces
value-only metadata descriptions. Constructed generic arguments, receiver and
signature types are checked; an inherited member uses its actual DeclaringType
and defining assembly rather than its ReflectedType. Forwarded framework types
are checked at their actual defining runtime assembly, not a guessed facade.

The probe rejects open/abstract invocation, native/byref/byref-like shapes,
readonly field writes and unsupported metadata providers. It rejects delegate
creation and polymorphic calls through a base method before execution. A later
runtime bridge must handle real dispatch instead of checking a base declaration
and executing an unchecked override. These are explicit experiment limits,
not prescribed special syntax for UGC authors.

The regression fixture is compiled and checked as IL before collectible loading.
It roundtrips scalar DTO field/property values, calls its own ABC and approved
framework methods, and checks rejection before file creation, constructors,
property accessor counters and field writes. Policy objects contain no metadata
cache; a test keeps the policy alive while observing context retirement.

## Enforcement still required

The probe only guards operations invoked through that trusted test boundary.
It does not intercept arbitrary MethodInfo.Invoke, Activator, property/field
reflection or delegate creation elsewhere. It is not a new UGC wrapper API or
a required author coding style. Reflection performed by compiled libraries,
ambient session-policy propagation, actual virtual/interface dispatch and all
assembly-loading paths still need runtime implementation and evidence under
#19/#5. Raw reflection remains rejected by the ordinary gameplay loader.

DLL count, names, changed bytes, extra files and author-initiated loads are not
the intended permission boundary. Existing package checks are unchanged by this
increment. Removing them without replacement loading/execution enforcement is
not demonstrated here. Stock tests establish neither interpreted execution nor
iOS/device support or a sandbox.

Game teams may use Microsoft's BannedApiAnalyzers and BannedSymbols.txt for
early author/AI diagnostics. That consumer-owned development practice does not
replace the IL/runtime checks and requires no custom RuneCLR analyzer/template.

## Measured stock validation (2026-10-26)

The isolated feature worktree at base c99d39e0 was built and exercised with the
stock Windows SDK. These measurements were taken locally before publication;
GitHub CI results are tracked on the pull request. No private-runtime
reflection-interception result is claimed.

| Command | Result | Local evidence log |
| --- | --- | --- |
| dotnet build RuneCLR.slnx -c Release | PASS, zero warnings/errors | build-final.log |
| dotnet run --project tests/RuneCLR.Packaging.Tests -c Release --no-build | PASS, 320/320, including 13 new policy/probe cases | packaging.log |
| dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build | PASS, 145/145, no optional late-map argument | runtime.log |
| dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --collect | PASS, context collected | sample.log |

Full logs are archival/local evidence at E:/RuneCLR-ugc-policy-evidence-20261026,
not downloadable repository artifacts. Their SHA-256 values are:

| Log | SHA-256 |
| --- | --- |
| build-final.log | 2c3c703fed804fbb2c32479d0889555e206d38fc31ef85ab8f7081f11b246845 |
| packaging.log | 719fee8354354732f413144dd1bf31539e053152d4a4abb34ed8b5c36a05eae2 |
| runtime.log | 51048f50d3064c53d93102e1dc4c6229b712edc3d7bbd9b43f53253058673240 |
| sample.log | c10805f7f991c7c2d3c998d5f06956c1df3b3b2b6e054a5e5b4ba65a6e488df2 |

The DTO test copies scalar field/property values through a dictionary; it is
not acceptance of a third-party serializer, database driver or networking stack.
Only the probe's own operations were checked before execution. Existing raw
reflection and package-intake restrictions remain covered by the unchanged
legacy tests; controlled dynamic loading and runtime reflection coverage remain
open work.
