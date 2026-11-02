# Shared UGC API decisions and reflection probe

The current opt-in follow-up is the [version 4 automatic MapSession policy and
managed-loading increment](ugc-session-policy.md). The matching private
post-commit fixed-runtime replay passes 123 groups, including review regressions for
internal delegate factories, bounded stream admission, resolver-depth event/
cross-session loading, private DynamicMethod MethodInvoker construction/
invocation and oversized byte[] symbol-store caps and the bounded opt-in
HostContractSession policy route. The runtime source is published on
ReneeGA2020/runtime branch `runeclr/reflection-policy-20261027` at commit
[`7cbdad39669188c1f49f0a41216829d9a9005591`](https://github.com/ReneeGA2020/runtime/commit/7cbdad39669188c1f49f0a41216829d9a9005591),
parent `5972a86966e56ae5f468a3e042327f0051e923d5`; its 22 managed files are
byte-equal to the accepted private snapshot. The pre-commit exact-final
733-input replay was not retested after the commit; the separate post-commit
732-input replay against 7cbd is the accepted receipt. The RuneCLR host
integration remains an opt-in/private experimental candidate; README and
default loader/host behavior are unchanged. The opt-in policy adapter
intentionally recognizes IsSessionCode and author Type construction. Earlier version 1-3 receipts below remain configuration-specific
history. Global session ownership and all-load enforcement remain incomplete.

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

## Initial probe limits

The original probe only guards operations invoked through that trusted test boundary.
It does not intercept arbitrary MethodInfo.Invoke, Activator, property/field
reflection or delegate creation elsewhere. It is not a new UGC wrapper API or
a required author coding style. The runtime increment below verifies ordinary
MethodInfo.Invoke and compiled-library calls under an explicitly installed
ambient scope. Actual virtual/interface dispatch, all assembly-loading paths
and full session ownership still need runtime implementation and evidence under
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

## Ordinary MethodInfo.Invoke runtime experiment (2026-10-27)

This section records version 1. The current local source and replay driver are
version 2, described in the construction/property/field increment below; the
earlier logs and source snapshot remain archived separately.

The local increment for #19 adds a CORECLR-only call at the beginning of
RuntimeMethodInfo.Invoke in the separate runtime repository. This is a runtime
source change in System.Private.CoreLib; the native VM is unchanged. It checks
before invocation flags, receiver validation, binder conversion, target type
initialization and method-body execution. The callback reuses
ReflectionAccessProbe.DemandInvocation and IApiAccessPolicy, including actual
declaring identity, constructed generic/signature/receiver/argument type checks.
No include/exclude rule parser or second policy table is introduced.

Trusted host setup calls PrototypeReflectionPolicy.Enter(policy). It requires
the matching private interpreter-policy bridge, reflection-policy version 1,
and the RuneCLR.EnableReflectionPolicy AppContext switch. Missing or disabled
support rejects before author loading. Author code continues to call
method.Invoke(receiver, arguments); a separately compiled default-context
library using that same API is checked under the scope too.

The CoreLib scope uses AsyncLocal with ordinary ExecutionContext propagation.
Nested scopes evaluate outer policies and cannot widen their permissions.
Retirement clears the host callback; an already captured context retains a
retired marker that refuses calls instead of dropping enforcement. Out-of-order
disposal rejects, repeated completed disposal is harmless, and recursive
reflection from a policy callback rejects. The recursion guard is implemented
but does not have a dedicated runtime regression in this increment. When no
scope has been installed, the entry check takes a fast return. Outside an
active/retired scope, trusted-host reflection retains its ordinary behavior.

### Measured scope

The author fixture is a deliberately trusted test build. Its raw reflection
and File metadata would still be rejected by the ordinary gameplay-v1 intake.
It is loaded in a collectible interpreter-required context with acknowledged
policy version 1. The test host prepares entry delegates and installs policy;
the author methods then use ordinary reflection, including inside the separate
compiled library. No production package profile has been opened for reflection.

Twelve private test groups pass:

- Author ABC and approved framework calls; approved and denied targets through
  the JIT-compiled library.
- Forbidden file output and a denied method's type initializer/body remain
  unexecuted; catching denial twice does not remove enforcement.
- Allowed constructed generics and forbidden generic arguments; a base virtual
  declaration that could dispatch elsewhere is refused before execution, while
  the concrete override is permitted.
- Allowed target exceptions retain TargetInvocationException semantics; nested
  scopes cannot widen policy, and Task.Run preserves allowed/denied decisions.
- Retired captured contexts refuse, disposal nesting is enforced, and the author
  context collects while a captured retired ExecutionContext remains alive.

Interpreter diagnostics contain 18 author-method records, including ABC and
the reflection callers. The JIT summary has no author methods, but does contain
the compiled library's Call and the test host's Exercise. This is method-level
desktop interpreter/JIT evidence, not a conclusion from environment variables.

| Gate | Measured result |
| --- | --- |
| CoreLib Checked x64 build | PASS, zero warnings/errors |
| Stock RuneCLR solution build | PASS, zero warnings/errors |
| Stock Runtime / Packaging / sample collection | PASS, 147/147 / 320/320 / collected |
| Stock and private-disabled reflection controls | PASS, refusal before author loading |
| Private ordinary reflection experiment | PASS, 12 groups |
| Private required-interpreter lifecycle | PASS, 147/147 |
| Unchanged upstream GitHub_130545 regression | PASS on patched private layout |

The upstream test source comes unchanged from the pinned runtime checkout and
is compiled with real xunit.core/xunit.assert binaries. A tiny driver invokes
DelegateOverStaticAbstractThroughGsharedvt and runs its actual assertions.
This checks ordinary out-of-scope reflection compatibility for that regression;
it is not the full upstream reflection suite or Mono/Wasm acceptance.

### Reproduce

Use the [historical local runtime branch/base and CoreLib build](runtime-fork.md#local-reflection-policy-experiment-2026-10-27).
Build RuneCLR with dotnet build RuneCLR.slnx -c Release. Prepare a separate
dotnet framework layout with the matching session-policy native runtime and
new managed CoreLib; do not replace an installed runtime. Then, from RuneCLR:

~~~powershell
python3 -B eng/verify-runtime-reflection.py --runtime-root E:/runtime-reflection-20261027 --layout E:/RuneCLR-reflection-evidence-20261027/layout --xunit-dir E:/runtime/artifacts/tests/coreclr/windows.x64.Checked/Tests/Core_Root --output E:/RuneCLR-reflection-evidence-20261027/repro-new
~~~

These are archival/local example paths, not repository dependencies or download
links. The driver requires a new output directory, records argv/environment
before each process, pins consumed sources/binaries before and after, compares
the layout CoreLib to the explicit build output, and checks interpreter/JIT
records. It does not build native code or establish binary provenance from a
hash alone. It records the historical v1 local runtime source state explicitly.
The original build/control logs and native reuse pins are at
E:/RuneCLR-reflection-evidence-20261027; final replay and hash receipts are
recorded there separately from both source repositories.

### Remaining boundaries

Scope activation is still trusted host setup, not runtime stack ownership of
every UGC transition. Suppressed ExecutionContext flow, unmanaged/new entry
paths and admission racing scope retirement require separate work. Other
reflection entry points (constructors/Activator, field/property operations,
delegates/DynamicInvoke/MethodInvoker, dynamic methods and metadata access)
have no complete automatic coverage claim. Some property paths may reach
MethodInfo.Invoke internally; this increment does not rely on that as coverage.
Custom Binder conversion behavior has no dedicated regression yet.

The current probe refuses unsupported polymorphic dispatch rather than
resolving the final virtual/interface target. All actual UGC loading routes
still need controlled interpretation and the common policy before the existing
intake restrictions can be removed. No broad async, hostile-code sandbox,
iOS/device, native/R2R body or third-party serializer compatibility is claimed.
Issue #19 stays open; #20 remains the later composable-rule increment.

## Construction, property and field runtime increment (2026-10-27)

The version 2 private CoreLib bridge sends MemberInfo, receiver,
arguments and an internal operation ID to trusted RuneCLR setup. IDs 0/1/2/3
mean method invocation, construction, field read and field write. These wire
IDs are independent of the public ApiOperation enum ordinals. The host checks
the exact version/delegate signature and refuses unknown operation/metadata
combinations; old version 1 CoreLib is refused before the author context opens.

The evaluator remains IApiAccessPolicy. Construction and field demand checks
are extracted from the existing ReflectionAccessProbe without executing the
operation in the callback. Properties use the actual getter/setter MethodInfo
and ApiOperation.Invoke, preserving declaration/signature/generic/receiver checks.

| Runtime entry | Version 2 behavior |
| --- | --- |
| Both RuntimeConstructorInfo.Invoke overloads | Check Construct before invocation flags, argument conversion, allocation/initialization or invoking an existing receiver |
| Property getter and indexed getter/setter | Existing RuntimeMethodInfo.Invoke check applies |
| Non-indexed property setter | Check the actual setter in InvokePropertySetter before its specialized fast invocation |
| RtFieldInfo.GetValue/SetValue | Check ReadField/WriteField before FieldAccessor, initialization, Binder conversion or storage access |
| Literal MdFieldInfo values | GetValue/GetRawConstantValue use the same ReadField check; literal writes remain rejected by CoreLib |
| RtFieldInfo.GetValueDirect/SetValueDirect | Refuse TypedReference-backed access while scoped; no native access is attempted |

No wrapper is required in author or library code. The private fixture calls
ConstructorInfo.Invoke, PropertyInfo.GetValue/SetValue and FieldInfo.GetValue/
SetValue directly, including the compiled-library path. Static constructors,
readonly writes and unsupported type shapes retain the probe's refusals.
The general gameplay intake is unchanged and still rejects raw reflection.

### Version 2 measurements

The final private replay passes all 27 groups (the original 12 plus 15 access
and retirement regressions). It checks scalar DTO construction and roundtrip,
the existing-instance constructor overload, separate field read/write decisions,
the fast property setter, indexed properties, literal fields, static field
initialization, readonly writes, runtime argument types, constructed generics,
constructor exception wrapping and compiled-library operations.

Negative writes attempt a different stored value. Denied constructors leave
type-initializer/body counters at zero; denied getters/setters leave accessor
counters unchanged. Field and property storage stays unchanged after denial.
Constructor, field-set and fast-setter tests deny before a custom
Binder.ChangeType callback, with three allowed conversions as live controls.
Recursive reflection from a policy callback refuses and subsequent normal
checks still work. Retired ExecutionContexts refuse all newly supported paths;
collectible retirement still passes while the retired context remains alive.

| Gate | Measured result |
| --- | --- |
| CoreLib Checked x64 and stock solution builds | PASS, zero warnings/errors |
| Stock Runtime / Packaging | PASS, 147/147 and 320/320 |
| Stock, switch-disabled and old-CoreLib mismatch controls | PASS, refusal before author loading |
| Private reflection / required-interpreter lifecycle | PASS, 27 groups and 147/147 |
| Upstream GitHub_130545 regression | PASS, unchanged source and real xUnit |
| Upstream TrySetReadonlyStaticField2.TestSetValue/TestSetValueDirect | PASS, unchanged source and real xUnit |
| Source/binary replay pins | 695 inputs, no before/after drift |

The upstream driver compiles the actual runtime sources with real xUnit and
the actual CoreClrConfigurationDetection helper (which supplies the referenced
TestLibrary namespace). It calls the three test methods directly, outside a
policy scope, to check ordinary reflection compatibility. This is targeted
CoreCLR regression coverage, not the complete upstream test suite.

The final interpreter dump records 58 author methods; no author methods appear
in the JIT summary. All six compiled-library reflection helpers and the host
Exercise method have JIT entries. Native binaries are reused pinned inputs;
only managed CoreLib was rebuilt for the eight-file runtime delta.

Use the same driver as the earlier example with the new private layout and a
fresh output directory. The current measured command is:

~~~powershell
python3 -B eng/verify-runtime-reflection.py --runtime-root E:/runtime-reflection-20261027 --layout E:/RuneCLR-reflection-access-evidence-20261027/layout --xunit-dir E:/runtime/artifacts/tests/coreclr/windows.x64.Checked/Tests/Core_Root --output E:/RuneCLR-reflection-access-evidence-20261027/repro-new
~~~

These are archival/local paths. Actual final replay receipts are under
E:/RuneCLR-reflection-access-evidence-20261027/repro-r3:

| Receipt | SHA-256 |
| --- | --- |
| summary.json | 08742476bdc20c95e5ee4cbab0ee74df3ebbeabb29590a751dfc206ea36beadc |
| execution-proof.json | 51f72219ef1904950a5e6f99577680f813f7c051f4dd42d48ea6c203c19a5bca |
| private.stdout.log | 804ff12bc338f3b2a10c07c22951be87ab180e3d2b18799cfc2bafeff81d1fab |
| upstream-private.stdout.log | f908268e4e911260fd1f1f4968ff5419883e1fa90a35a40ee30a4c28e69f7c6c |

The earlier v1 evidence/layout is preserved. The initial version 2 replay passed;
a later driver edit had a Python syntax error before launching any tests
(repro-r2-driver.log). It was corrected, and the accepted repro-r3 completed
all six lanes with stable source/binary pins.

### Next enforcement work

Resolve final virtual/interface targets while checking both the requested
declaration and actual implementation, instead of the current conservative
polymorphic refusal. Activator default/generic factories and the separate
ConstructorInvoker/MethodInvoker APIs also have optimized routes not established
by ConstructorInfo.Invoke coverage. Delegate creation, DynamicInvoke, dynamic
methods, metadata/attribute execution, runtime-owned policy propagation, every
UGC assembly-loading route and retirement races remain separate gaps.

This is still a trusted host-activated ambient experiment, not automatic policy
ownership on arbitrary suppressed-flow/unmanaged transitions. No production
reflection profile, general serializer/database compatibility, include/exclude
engine, iOS/device or hostile-code sandbox acceptance is claimed. #19 stays open.

## Actual dispatch, factories and attribute targets (2026-10-27)

Version 3 completes the current ordinary reflection target-checking increment.
It applies IApiAccessPolicy to actual targets regardless of application purpose.
DTO/serialization examples create no special permission; the integrating host
chooses its policy. The shipped gameplay intake still blocks raw reflection.
This is an opt-in host-activated runtime experiment, not general UGC admission.

### Target selection and entry coverage

Virtual calls check both the requested declaration and resolved implementation.
CoreLib uses the runtime's method-table slot or interface-implementation query,
then restores the closed generic method arguments. It does not select a method
by name. The final target's defining type, signature and generic arguments
pass the same evaluator, so permission on an interface/base method alone does
not approve a forbidden implementation. The standalone stock probe keeps its
conservative polymorphic refusal because it lacks these runtime internals.

| Entry | Scoped version 3 behavior |
| --- | --- |
| Ordinary method/property/event invocation | Existing target checks plus final virtual/interface implementation checks |
| MethodInvoker | Check every invocation, including pre-cached factories, fixed arities and spans; existing-receiver constructors use Construct |
| ConstructorInvoker | Check Construct before conversion, allocation, initialization or target code |
| Activator default/generic factories | Check the real parameterless constructor before creating the activation cache or target; parameterized calls converge on checked construction |
| Implicit default value types | Check Reference and Construct on the closed type; no fictitious constructor identity |
| Custom attributes | Check default and optimized parameterized constructors; named setter/field writes use the checked accessor/field routes |
| Reflected delegates | Reflection-based binding and DynamicInvoke/reflected Invoke explicitly refuse while scoped, including cached invokers; ordinary C# delegates remain usable |
| DynamicMethod | Scoped direct invocation, delegate creation, dynamic MethodInvoker creation and cached invocation refuse |
| COM, dynamic interface casts and generic array-interface dispatch | Explicit unsupported refusal; dynamic cast callbacks cannot run during receiver preflight |
| TypedReference fields, readonly writes and prior unsupported shapes | Existing refusals remain |

Wire IDs 0 through 3 retain invocation/construction/field-read/field-write
meaning. ID 4 checks a virtual declaration followed by runtime resolution and
an ID 0 final-target check. ID 5 denotes an implicit value-type default. The
host requires exact bridge version 3 and rejects unknown shapes. Version 2
CoreLib is refused before author loading.

The legacy policy adapter now permits type-level Construct for caller-validated
script identities, matching ordinary author value defaults. It still denies
framework type-level construction and type-level Invoke. A custom evaluator
can independently refuse Construct; actual closed-value/no-constructor shape
validation belongs to the runtime/probe. This does not open gameplay reflection.

Only the fixed CoreLib entry delegate is cached in trusted setup; no policy,
author metadata or session context is cached there. Nested policies continue
to narrow, captured retired contexts refuse, and disposed callbacks release
author references. Framework/library reflection inherits the same checks.
For example, the harness explicitly permits the host's SafeWaitHandle
construction and NeutralResourcesLanguageAttribute/enum references needed by
Task waits and exception-resource lookup. There is no framework exemption.
These test-host permissions are not added to the gameplay profile.

### Measurements

The final Windows x64 Checked replay passes 55 groups. In addition to the
version 2 tests, it covers base/abstract/explicit-interface/default-interface/
boxed-struct/variant-interface dispatch, inherited and hidden methods, generic
methods and generic declaring types, covariant returns, virtual properties
and events, and checks denial before the implementation body or custom cast.

Cached MethodInvoker and ConstructorInvoker test arities 0 through 5 under
both denying and allowing policies. Activator checks include interpreted
callers and JIT-compiled generic helpers, implicit/explicit structs, target
cctor/body counters, and Type.InvokeMember. Attribute construction and named
accessors have effect counters. Twelve scoped delegate/dynamic routes have
explicit refusal controls, including factories created before entering scope.
An existing-receiver constructor invoker has its own allowed/denied counter
control. Captured retired contexts refuse all newly supported dispatch,
factory, invoker and attribute routes before their target effect counters move.

The replay seals 710 inputs with zero drift. It records 141 author interpreter
method entries, no JIT entries whose declaring type is in the author assembly,
and JIT entries for the trusted host and all ordinary/fast/generic library
helpers. A compiled generic helper with an author type argument is correctly
classified by its declaring method rather than a substring of its name.

CoreLib and solution builds pass with zero warnings/errors. Stock Runtime
147/147, private required-interpreter Runtime 147/147, stock Packaging 320/320
and stock SampleHost collection pass. Four unchanged
upstream methods run outside policy scopes: GitHub_130545, the two readonly-field
tests, and DisallowAbstractConstructors.TestEntryPoint (expected 100). This is
targeted compatibility coverage, not the complete upstream test suite.

Generic Activator's Intrinsic attribute is disabled for CORECLR in this private
candidate, preventing JIT substitution from bypassing the managed check. Its
performance effect is unmeasured; no stock runtime installation is changed.
CoreLib's internal reflection invocation stubs use a dedicated internal delegate
factory after target checks; the public dynamic-code entry remains refused.
Sixteen managed runtime files differ from session-policy tip
5972a86966e56ae5f468a3e042327f0051e923d5; no native VM source/build is added.
The separate [RCLR-UP-004 record](upstream-bugs/dynamic-method-invoker-signature.md)
retains a pre-existing dynamic-invoker initialization failure and local fix.

Reproduce with the maintained driver and a fresh output directory:

~~~powershell
python3 -B eng/verify-runtime-reflection.py --runtime-root E:/runtime-reflection-20261027 --layout E:/RuneCLR-reflection-dispatch-evidence-20261027/layout --xunit-dir E:/runtime/artifacts/tests/coreclr/windows.x64.Checked/Tests/Core_Root --output E:/RuneCLR-reflection-dispatch-evidence-20261027/repro-new
~~~

The paths are archival/local identifiers. Accepted receipts are in repro-final2:

| Receipt | SHA-256 |
| --- | --- |
| summary.json | 3f1c7dc6941236c48b25034540d52a1cda7fa3ab3e7bcac95a2bd8965e3d6d14 |
| execution-proof.json | 9beee772fcc6c9c238aa848a7f9c142bccafb1d574e885e3bccfc0d6aeeffed2 |
| private.stdout.log | 20f136158af4cb5579b66b2323c2f74fa87dfaa95038d9259e4f52f36a35baed |
| upstream-private.stdout.log | ee94c0071ffae851a226fc3bc263671fa575aa2edf7724ba8e19c3a5275e37b1 |

Earlier failed/incomplete replays remain preserved: two initial trimming-analysis
errors, strict fixture-policy omissions, a JIT-name classification error and
the reduced dynamic-invoker assertion. They are not counted as passing runs.

### Remaining integration boundary

The supported target-checking routes are implemented and locally verified.
Author fixtures still use trusted experimental IL, not accepted gameplay
packages. General metadata discovery is not automatically filtered; supported
execution/storage operations check their targets even when metadata is obtained
first. Unsupported delegation/dynamic execution is refused in a live scope.

Every UGC loading route still needs controlled interpretation and policy
attachment; scope ownership is currently trusted host setup with normal
ExecutionContext flow. Suppressed flow, unmanaged entry, admission/retirement
races, and rechecking direct invocation of escaped delegates are not accepted.
They are not covered by an ambient reflection hook. Keep the current gameplay
reflection ban until the intended integration is selected and verified.
No serializer/database compatibility, include/exclude engine (#20), sandbox,
native/R2R body, iOS or device claim is added. At that v3 stage, source in both
repositories remained local, uncommitted and unpublished; #19 remains open for
integration.
