# Immutable session execution policy — private source candidate

On 2026-10-13 the execution-selection diagnostic was extended with a native
creation-time policy for a specific collectible load context. This implements
the next step in the [selection plan](runtime-execution-selection.md), on top
of [the diagnostic candidate](runtime-execution-selection-candidate.md).
The source is a private RuneCLR experiment, not an official runtime defect or
upstream submission. Matching-build and execution acceptance remain separate
from this source record.

Base commit is `6bb5f60be8de39b22fb19b95aea03e3252756cb3`, branch
`runeclr/session-policy`, derived from official runtime
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. The source snapshot changes
12 files, 176 insertions and 16 deletions, including three reflection-only
CoreLib method roots. Root reviewed and committed the initial 11-file snapshot
as `16d794a6cf297a3e52f0588d6437c512e13d8451`. Its first native build failed
locally as recorded below. The corrected commit
`8d809df480f96e8130af15dbcd203dba32043130` built successfully, but its private
bridge methods were removed by CoreLib trimming. Root committed the minimal
descriptor fix as `5972a86966e56ae5f468a3e042327f0051e923d5`; this is the
current tracked-clean candidate. Its fresh matching build completed with zero
warnings/errors; the five-stage metadata checks below pass. Session-factory
execution acceptance is tracked separately.

## Matching CoreLib interface

The private methods are declared on `AssemblyLoadContext` in its CoreCLR
partial. Public ALC constructors still create ordinary contexts. These are
private experiment interfaces, not a supported public .NET API:

```csharp
private static AssemblyLoadContext RuneCLR_CreateInterpreterRequired(
    string name, Func<AssemblyLoadContext, AssemblyName, Assembly?> managedResolver);
private static int RuneCLR_GetExecutionPolicyVersion();
private int RuneCLR_GetExecutionPolicy();
```

The factory validates arguments and checks native version acknowledgement
before constructing a context. A native candidate with `FEATURE_INTERPRETER`
returns version 1; one built without that feature returns 0, and the factory
throws `PlatformNotSupportedException` before package loading or context
construction. The required native creation entry also rejects unsupported
builds directly. A stock CoreLib lacks these methods; trusted host integration
must fail startup rather than load a package under an ordinary context.

The nested sealed context always creates a collectible native custom binder.
Its `Load` override calls the supplied resolver with `(this, assemblyName)`;
its `LoadUnmanagedDll` override throws `NotSupportedException`. The resolver
is assigned before the factory returns and before any package load. RuneCLR
retains package resolution, shared-contract identity validation, private
dependency hashes and session ownership.

The instance query locks the existing unload lock, calls `VerifyIsAlive`,
queries the native binder scalar and calls `GC.KeepAlive(this)`. It reports
explicit native policy 1 or ordinary policy 0. Querying after unloading is
rejected, avoiding a stale native-binder address. The old global diagnostic
switch does not change this explicit-context acknowledgement.

## Native creation and method ownership

`AssemblyBinder` stores `const bool m_runeCLRInterpreterRequired`, set by its
protected constructor, with a scalar nonvirtual getter and no setter. Default
binders use false. `CustomAssemblyBinder::SetupContext` passes the requested
value to the custom binder constructor before the binder is published or any
module is loaded. Native policy retires with that binder; there is no global
registry of assemblies, methods, types or managed script references.

`MethodDesc::HasRequiredInterpreterPolicy` asks the **defining** module's
`PEAssembly::GetAssemblyBinder()` for this flag, OR the prior all-collectible
startup diagnostic. It does not classify ownership by the allocator of a
closed generic instantiation. A trusted `List<UGCStruct>` body remains under
its trusted definition's policy, while private dependency methods loaded
through the required binder automatically inherit that policy.

The existing broader policy guard still covers R2R lookup, native inline
requests, multicore cache retrieval and tier eligibility, including wrapper
descriptors. `RequiresInterpreterBody` continues to exclude runtime-generated
ABI wrappers from the bytecode-body requirement. The underlying author's IL
remains required; unboxing/instantiating bridges cannot use native body lookup
or inlining to substitute that IL. The previous required compiler flag and
fail-closed fallback/null-bytecode guards are retained unchanged.

Three new QCalls implement creation, version and instance policy. The original
three-argument `AssemblyNative_InitializeAssemblyLoadContext` native/managed
signatures remain unchanged. Both creation routes call an internal worker;
the old route passes ordinary policy, the new route has a fixed collectible
custom-context topology. No Mono/NativeAOT Initialize signature changes.

The shared managed constructor gains a private internal overload; existing
constructors delegate with false. Only the CoreCLR required branch catches
native initialization failure, frees its newly allocated `GCHandle` and sets
`_unloadLock = null!` to prevent a finalizer from calling native release with
a zero binder pointer. The ordinary initialization branch retains its previous
behavior. No managed ALC field is added, so its native object-field mirror does
not change. The native binder layout does change and must match the compiled
DAC/cDAC offset descriptions; actual compilation remains build acceptance.

## Trust and coverage limits

Private method visibility is not a security barrier against reflection. This
interface registers a requested execution route at context creation; it does
not establish who may call reflection, create other ALCs, load default-context
IL, emit dynamic methods or invoke expensive trusted code. Such paths remain
outside the current registered-module policy. The factory supplies no method
to downgrade an existing context, but public ordinary ALC creation still
exists. Do not label this candidate an author-resistant sandbox.

Context policy is assigned before package initialization/preparation and
includes later private dependency loads. It is stronger than a method-name
environment selection or late entry-assembly registration. Host outcomes
still must retain only primitive values and copied strings; factory/resolver
delegates and temporary reflection data must not retain a retired script.
Host integration should acknowledge version and context policy before loading
any package and preserve cleanup/unloading on errors.

## Scoped skip regression with the global diagnostic disabled

The test-only `RuneCLRInterpreterRefuseMethods` input remains empty by default.
In this extension its explicit nonempty method-set works with
`RuneCLRInterpretCollectible=0`; it still requires exact metadata identity:
assembly `SelectionProbe.Refusal`, namespace `SelectionUGC.Refusal`,
class `Entry`, method `Reject`. Arbitrary production methods cannot be
refused by a wildcard method-set. The emitted diagnostic is unchanged:

```text
RuneCLRInterpreterRefusal: SelectionUGC.Refusal.Entry:Reject CORJIT_SKIPPED
```

The required-factory mode-0 fixture must throw managed `NotSupportedException`
before native JIT, unload and recover. The ordinary default-context mode-1
control must see actual `CORJIT_SKIPPED`, then return 73 using native fallback
from identical DLL bytes. This explicit injection is a regression tool, not
automatic author-facing rejection behavior. Previous diagnostic-snapshot
receipts retain their earlier global-switch gating description.

## Portable source receipt and pending acceptance

[Patch 0004](../eng/runtime-patches/0004-interpreter-required-load-context.patch)
is an LF diff **from `6bb5f60...`**, excluding patch 0003. SHA-256:
`714ba322b3df83ccb3feb5b91043b779e4c75b212ea9d4dbf95db06c0e330657`.
Initial source hashes and 12 static checks are retained in
`artifacts/runtime-session-policy-source/20261013-pre-review`;
`20261013-committed` binds the unchanged source/patch to root's reviewed commit.
`git apply --check --cached` passed against the unchanged base index, and
`git diff --check` passed. This agent did not build or commit the source;
the root experiment owns those steps and preserves their separate receipts.

The initial native build reported `C2143`/`C2059` at the argument-taking custom
binder allocation. The existing `SAFE_NEW(Object, Class)` macro appends `()`,
so passing `CustomAssemblyBinder(interpreterRequired)` there is invalid.
The correction uses `SAFE_NEW_CONSTR` for that complete constructor expression.
This is a local candidate implementation error, not an upstream defect; the
failed build is retained independently. The one-line correction, cumulative
patch/source hashes and thirteenth static check are recorded in
`artifacts/runtime-session-policy-source/20261013-binder-constructor-fix`.
Its reverse `git apply --check` passed without modifying the worktree.
`20261013-binder-fix-committed` binds the corrected patch and all 11 normalized
source hashes to `8d809df480f96e8130af15dbcd203dba32043130`. The portable diff
matches the committed `6bb5f60...` to `8d809df...` diff byte-for-byte; all 13
static checks pass and the worktree is tracked-clean. These checks do not
stand in for the matching-build retry or execution acceptance.

The `8d809df...` matching build completed with zero warnings/errors, but the
session fixture rejected startup before any package load: all private bridge
methods were absent. Raw MethodDef inspection found five `RuneCLR_` methods
in the actual `PreTrim` CoreLib, zero in the post-trim object and copied IL,
and zero in the final R2R/deployed CoreLib. Source compilation was fresh;
`ILLinkTrimAssembly=true` legally removed unreachable reflection-only private
methods. The diagnosis and copied trim targets/descriptors are retained in
`artifacts/session-policy/corelib-trim-diagnosis-20261013-8d809df`. This is a
local integration omission, not an official runtime defect.

The correction roots exactly the factory, version and instance query methods
in CoreCLR's shared ILLink descriptor. It does not preserve the whole ALC or
change method visibility. Factory reachability retains the nested context and
its resolver/initialization chain; actual post-trim metadata and factory
execution remain fresh-build checks. The additional descriptor, cumulative
12-file source hashes and 15 static checks are recorded in
`artifacts/runtime-session-policy-source/20261013-corelib-root-fix`. The
`20261013-corelib-root-committed` receipt binds all 12 hashes and the byte-for-byte
portable diff to `5972a86966e56ae5f468a3e042327f0051e923d5`, tracked-clean. The earlier
[four official loader regressions](runtime-session-upstream.md) on `8d809df...`
remain valid for the diagnostic ordinary-context route, not factory acceptance.

On the matching `5972a869...` build, actual raw metadata inspection of PreTrim,
post-trim object, product IL, product R2R and deployed CoreLib finds all five
bridge/import wrapper methods at every stage. The three generated PInvoke
entries identify the exact new QCalls, and the nested context's `.ctor`, `Load`
and `LoadUnmanagedDll` are present. Post-trim and product IL hashes match;
product R2R and deployed hashes match. Evidence is
`artifacts/session-policy/corelib-metadata-5972-verified`, including the
read-only verifier and every observed signature, flags and native import name.
This proves the reflection surface survived trimming; actual factory/owning
context acknowledgement remains an independent managed execution check.

That independent check also passed on `5972a869...`: the diagnostic-off
session driver records version 1, required contexts with policy 1, ordinary
contexts with policy 0, and exact post-unload query rejection counts of 20
normal/ordinary/boxed contexts and 21 refusal-plus-recovery contexts. Raw
`policy-api.json` and native-query markers are retained in
`artifacts/session-policy/session-20261013-031436-113be3f7cccd4db49da546977097c7d0`.
The separate concrete generic inline driver also passed, with ordinary native
inline positives and required-body rejection/bytecode evidence. See
[the fixture acceptance record](session-interpreter-validation.md) for the
complete counts and limitations; these results do not capture native method
execution entries or establish mobile support.

Static checks cover old ABI preservation, all new QCall declarations/imports/
registrations/definitions, scalar creation-time immutability, ordinary
constructor behavior, version-before-construction, locked native query,
unsupported native rejection, definition-binder ownership, exact fixture
refusal, required-path constructor cleanup and LF patch bytes. Existing
`PTR_AssemblyBinder` is the DAC-aware `DPTR` alias; `GetPEAssembly` and
`GetAssemblyBinder` are available to DAC and the new getter is a scalar
nonvirtual read. Static inspection does not claim a DAC build passed.

Acceptance must use a matching candidate native runtime and freshly built
CoreLib, with global diagnostic disabled and mode 0: factory version/query
acknowledgement, ordinary collectible native control, constructor/private
generic/interface/delegate/filter bodies, boxed ABI bridges, real compiler
skip and recovery, retirement, and the production lifecycle/package suites.
Unsupported/stock runtime startup rejection must happen before package loads.
Host JIT/R2R may remain enabled, and neither environment values nor successful
functional counters alone prove this native policy was enforced.
