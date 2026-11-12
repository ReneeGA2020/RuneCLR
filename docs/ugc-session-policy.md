# Automatic UGC session policy and managed loading

Opt-in Windows x64 increment, 2026-11-02. This continues
[reflection target enforcement](ugc-api-policy.md) on runtime base
5972a86966e56ae5f468a3e042327f0051e923d5. The runtime source is published on
ReneeGA2020/runtime branch `runeclr/reflection-policy-20261027` at commit
[`7cbdad39669188c1f49f0a41216829d9a9005591`](https://github.com/ReneeGA2020/runtime/commit/7cbdad39669188c1f49f0a41216829d9a9005591),
parent `5972a86966e56ae5f468a3e042327f0051e923d5`; its 22 managed files are
byte-equal to the accepted private snapshot. The pre-commit exact-final
733-input replay was not retested after the commit; the accepted receipt is the
separate post-commit 732-input replay against 7cbd. The RuneCLR host integration
remains an opt-in/private experimental integration; default loader/host behavior
and README claims are unchanged. The opt-in adapter intentionally recognizes
IsSessionCode and author Type construction. This is an opt-in MapSession and
HostContractSession integration, not a completed global UGC boundary.

## Host configuration and lifetime

The host configures RequireInterpreter, MapRunOptions.PrototypeApiPolicy and
the private RuneCLR.EnableReflectionPolicy AppContext switch. Optional
PrototypeSharedAssemblies contains actual existing default-context assembly
instances; the shared IMapScript contract is automatic. Names alone do not
grant trust. Missing/mismatched/disabled support rejects before author files,
including when bridge delegates were already cached.

Private reflection bridge version 4 separates a session owner from callback
activations. Construction, OnStart, every OnTick and OnStop activate the policy
and restore the previous host scope on return. Returning retires that activation,
not the live session. Captured returned contexts refuse reflection/loading.
Stop/startup failure clears the evaluator, admission callback and owner-context
reference. Retained session options contain no policy/shared-assembly list;
results remain strings, scalars and weak unload tickets.

Compiled trusted libraries called by UGC inherit reflection checks. Host code
outside an activation keeps normal reflection behavior. A ConditionalWeakTable
associates contexts and sessions without changing AssemblyLoadContext's native-
shared instance layout. The current delta is 22 managed CoreLib/build/linker
files; no native VM source or binary rebuild was needed.

## Managed loading and authority

The tested Assembly.Load byte/name overloads, LoadFrom, LoadFile, UnsafeLoadFrom,
ALC path/stream/name/native-image-path APIs and assembly-qualified Type.GetType
direct new loads to the current interpreter-required collectible session.
Requesting Default/another context or hitting a host LoadFile cache does not
upgrade the load. An attached context also performs admission for host-initiated
loads outside callbacks. Nested loads cannot change UGC session ownership.

These loads deliberately share the session's type identity and lifetime rather
than Assembly.Load(byte[])'s usual isolated context. This does not establish
arbitrary custom-ALC library compatibility. Explicit bytes cannot replace a
host-provided shared instance. Dependencies search known package/source
directories and need not be individually listed; unrelated files are ignored
by this experimental direct-package route.

Path/array input is privately snapshotted. The exact admitted bytes reach the
native binder without reopening the path after validation. Declared path hashes
are checked against those bytes when present. Managed PE/IL structure and API
references are checked before loading; R2R/mixed/native input is unsupported.
Ordinary typeof gains a type-token option; method/field tokens and unsafe IL
remain refused. The controlled-session name option removes the legacy reserved-
name heuristic. The regression dependency is named System.Custom.UgcDependency
and also loads under an unrelated filename with an unlisted text file nearby.

ApiTarget.IsSessionCode comes from trusted IL admission or actual runtime
context ownership. The old evaluator therefore accepts newly admitted author
functions without prelisting their assembly/member names. Custom evaluators
still receive the supported targets and can deny individual author members.
An existing host assembly with the same identity does not gain this origin.
The flag is trusted evaluation input, not authentication for arbitrary callers.

The host resolver's own type dependencies retain their original binding context.
That internal binding privilege is reset before native loading can call assembly-
load events; it never exempts reflection targets. Reflected access to policy/
loader enforcement state and unchecked dynamic assembly emission refuse even
with a permissive evaluator. Existing scoped delegate/DynamicMethod refusals
remain.

## Measured validation

The 123-group/156/156/732 result below is a post-commit private replay against
the clean published runtime commit. source-state.json records runtimeCommit and
runtimeHead as 7cbdad..., with parent/base 5972a869... and 22 declared files.

- CoreLib and RuneCLR solution builds pass with zero warnings/errors.
- Private replay: 123 groups; stock/disabled controls pass. The suite includes the
  review-fix regressions described below. Thirteen loading routes
  each include allowed and denied-IL controls. Effects, returned contexts,
  trusted caches, path replacement, enforcement-state access and assembly-load
  callbacks have separate controls; all 31 loading-test contexts collect.
- Private required-interpreter Runtime: 156/156; four unchanged targeted upstream
  methods pass outside scopes. This is not the full upstream test suite.
- Diagnostics record 365 interpreted author entries (221 session entries) and
  32 dynamic-dependency entries, with no corresponding author/dependency JIT
  declarations. Host and ordinary/fast/generic/loading library helpers are JIT.
- The driver seals 732 input pins, zero drift. Earlier failed/incomplete replays
  remain preserved and are not promoted to final acceptance.

Current archival/local evidence root: E:/RuneCLR-hostcontract-policy-evidence-20261102.
Earlier MapSession/runtime receipts are under E:/RuneCLR-session-binding-evidence-20261102.
Accepted replay: E:/RuneCLR-publication-20261102/repro-published-runtime.
summary.json SHA-256:
66dac68fec68b9d451d77dc5a978954e4fa1f70db210a1fadbf61ccd2d885d2f.
execution-proof.json: 0596a071bbb52b937e476b6aafe82a937a296aaa8a8f5c94ea3b0b6a29cfd1f6.
CoreLib: ddbf9e33d75e2188278ee8d37a58981ced6ccf90f6ab49b69406b9bc27b2ec5d.
Earlier fixed-runtime history remains: repro-hostcontract-exact-final (123 groups;
733 pins; pre-commit byte-equal snapshot), repro-hostcontract-generic-final (121 groups;
733 pins; CoreLib ddbf9e33...), repro-hostcontract-closure-final (115 groups;
733 pins; CoreLib ddbf9e33...), repro-hostcontract-final (107 groups; 732 pins;
CoreLib ddbf9e33...) and repro-adjacent-fixes-final (98 groups; 729 pins; CoreLib
ddbf9e33...), repro-review-fixes-final (95 groups; CoreLib 721b2a13...) and the
pre-fix repro-final3 (86 groups; CoreLib
f3bb7aca7e60da4bdfb2a873b0bfb3adf9a2cbc49b3358aa49d3df0b04909f7c). The 107-group
snapshot predates the allowedMethods/identity guard fixes and is not acceptance for
the closure build. Earlier receipts do not establish the current host integration.
Earlier v1/v2/v3 and uncommitted receipts remain historical and do not establish
the current candidate.

Reproduce with eng/verify-runtime-reflection.py, a clean worktree at the
published branch/commit above, layout-hostcontract-exact-final and a fresh output
directory. The default driver requires the exact published commit, its exact
base parent, a clean worktree and the exact 22-file delta; old dirty-base
experiments are historical only. Paths are local identifiers.

## Review corrections

The focused runtime fixes close the independent bridge-v4 review findings.
Exact immediate internal delegates can no longer be obtained through
DynamicMethod/InvokerEmitUtil reflection; ordinary MethodInvoker creation still
works. Session-owned stream loads enforce the 32 MiB bound before unbounded
allocation or read. Resolver-depth path loads clear the trusted resolution
depth around native loading and retain the cross-session owner check.

The observed pre-fix counterexample is preserved under the tests review evidence:
the old layout escaped both internal factories at 77, read all 67,108,864 stream
bytes, allowed a resolver-event load and crossed into attached session B. The
fixed replay above is the acceptance receipt.
HostContractSession policy integration is now accepted in this bounded Windows
opt-in scope; suppressed flow, unmanaged entries, wider escaped delegates and
full retirement races remain outside this scope.

Two adjacent findings are also closed. The private MethodInvoker(DynamicMethod)
constructor refuses before reading Signature.Arguments, and CheckInvoker rejects
pre-created DynamicMethod-backed invokers while a scope is active; ordinary
MethodInvoker creation and invocation still work. Byte[] symbol stores are
checked against the same 32 MiB limit before cloning, admission or native load.
Session-owned non-seekable assembly and symbol streams are read in bounded
chunks; stock/non-session LoadFromStream keeps the original Length/ReadAllBytes
behavior. A pre-adjacent counterexample on the frozen 721b layout escaped the
private invoker at 77 and loaded a 33 MiB symbol store; the adjacent replay
above is the acceptance receipt.

## Host contract policy integration

HostContractSession now accepts an optional public HostContractSessionOptions
record: ExecutionPolicy (default Default), an optional PrototypeApiPolicy and
explicit PrototypeSharedAssemblies. Supplying a policy requires
RequireInterpreter; explicit shared assemblies require a policy and must be
unique existing default-context instances. The two original overloads remain
unchanged and keep the legacy static scanner and fallback behavior.

The policy route creates the required-interpreter collectible context, attaches
and activates the reflection-policy session around entry load, construction,
OnStart, Invoke(string), Invoke(string,int) and InvokeInt, and uses exact entry
and dependency bytes through admission. The supplied interface assembly is
shared automatically; other shared assemblies are explicit actual instances.
DLL names, file counts and extra files do not grant trust. allowedMethods and
the host evaluator are composed into one effective policy for
admission and reflection, including base-interface and actual interface-map
implementation aliases; shared host code is not scanned as author code. Host
code outside activations remains ordinary trusted code, while trusted compiled
libraries called by UGC inherit the checks. Declared source identities are seeded
before entry admission as session code. Framework shadows are rejected by the
actual runtime framework inventory, not a broad System.* prefix rule, so
System.Custom.UgcDependency remains valid.

Policy mode removes the duplicate bespoke legacy IL vetoes but still uses the
common shared IL/API profile and lifecycle shape checks. Policy failure text is
bounded exception type only, with no author virtual Message read. Constructed
generic contracts are normalized to their generic definition for allowedMethods
membership; constructed, inherited, explicit distinct-name and supplied-instance
override aliases are covered by tests. Base-method matching uses ExactBinding so a
direct reflected nonvirtual base alias with the same name and exact parameters is
denied, while a base Hidden(object) overload remains callable when the contract
method is Hidden(int). allowedMethods remains name-only: all overloads and generic
methods under a listed name share the decision, and property/event accessors use
get_/set_/add_/remove_ names. This is not a signature-rule engine.

The direct five-argument constructor and manifest Open are both supported with
options as the last argument. Open keeps the existing manifest, hash, file-list,
producer, contract-reference and allow-list checks before the policy load; the
direct constructor covers the no-manifest case without manifest-declared
dependencies; policy-controlled dynamic dependency loading still applies.
Legacy options-free sessions are unchanged.

## Remaining integration

Runtime-owned propagation beyond normal ExecutionContext remains open:
suppressed flow, unmanaged entries, escaped direct delegates and retirement
races are not accepted. Common managed entry hooks do not prove global all-load
enforcement. HostContractSession consumes this option in the policy route; other UGC entry
surfaces and custom-host/AOT scenarios remain open. Options validation and
reflection-bridge preparation run before author file reads; native required-
context create/acknowledge runs before LoadFromStream/author execution.
RequireInterpreter without a policy is explicitly rejected before author files,
while legacy options-free sessions keep normal Default behavior. The existing versioned gameplay loader retains its fixed policy,
manifest checks and raw-reflection prohibition. General metadata discovery is
not filtered. Include/exclude rules remain #20. Combined budget/deadline runtimes,
non-Windows builds and physical iOS need separate validation.

No hostile-code sandbox, serializer/database compatibility, native/R2R execution
or physical-device claim is added.

## Session-origin integration (2026-11-12)

An opt-in session-origin capability is prepared on top of this policy in the
integration branches; see
[validation/session-origin-integration-20261112.md](validation/session-origin-integration-20261112.md).
The runtime `RuneCLR.EnableReflectionPolicyOriginScan` switch defaults to
disabled, so the policy described here is unchanged for existing hosts.
