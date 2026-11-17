# RuneCLR.GroupedHost.Tests — grouped-host acceptance harness

Executable console harness (no `dotnet test`) for the public grouped-host API in
`src/RuneCLR.Runtime/GroupedHostSession.cs`. It references `RuneCLR.Runtime` and the fixture
contract normally and stages the fixture role images with `ReferenceOutputAssembly=false`, so no
fixture Framework/Author assembly is loaded into the Default context.

## Staged roles (deterministic folders under `$(OutDir)/fixtures`)

| folder | contents | role |
| --- | --- | --- |
| `framework` | RuneCLR.GroupedHost.Framework.dll, Contracts.dll | real trusted framework image with the kernel32 probe |
| `framework-portable` | same assembly identity, portable build | diagnostic image without P/Invoke (not acceptance) |
| `author-a` | RuneCLR.GroupedHost.Author.dll (tag A), Contracts.dll | author role |
| `author-b` | RuneCLR.GroupedHost.Author.dll (tag B), Contracts.dll | author role |
| `author-native-rejected` | RuneCLR.GroupedHost.Author.NativeRejected.dll, Contracts.dll | negative author role |
| `dynamic` | RuneCLR.GroupedHost.Author.NativeRejected.dll | byte payload for the dynamic-load case, outside every role catalog |

Author role directories contain no framework copy: the framework resolves from the group context
through the admission lease, and the staging target deletes only the three named stale
`RuneCLR.GroupedHost.Framework.dll` artifacts left by earlier layouts (bounded paths, no recursive
deletes). Approved-framework-copy acceptance is exercised by `--framework-copy`, which builds
throwaway author role directories in the temp root with (a) the exact native framework bytes and
(b) the same identity with different bytes.

The portable image exists only as a diagnostic: it is the same source compiled with
`GROUPED_HOST_PORTABLE_FRAMEWORK`, where the native probe throws instead of binding kernel32. The
real framework image is accepted by the trusted framework intake; the portable image is never
acceptance evidence and is selected only by `--portable`.

## Modes

Stock SDK (installed runtime, no private CoreLib):

- `--stock-negative` — both policy-switch states must be rejected by the missing private-runtime
  preflight, with zero framework/author records (a negative control, not a grouped pass).
- `--policy-negative` — explicit allow/deny expectations, including the standard BCL delegate
  constructor being allowed and `CreateDelegate` being denied.
- `--policy-audit` — re-evaluates the fixture policy over every assembly/type/member reference in
  the staged author A and B images; must report zero denials.
- `--probe-entry` — the selected framework image's `Initialize` parameter is the Default-context
  contract type.
- `--dump-refs <assembly.dll>` — diagnostic member-reference dump.

Private runtime (Release x64 layout with clrinterpreter and the RuneCLR CoreLib patches):

- `--runtime-check` — prints the runtime description, CoreLib path and SHA-256, both switch states,
  the reflection capabilities integer and the origin-scan bit.
- `--origin-negative` (origin-off config) — a grouped `Open` must fail closed without the
  session-origin-scan capability and produce zero host records.
- `--positive` — the eight baseline cases: A/B/A group reset with a shared framework instance,
  pending-cleanup rejection (entry/Close/Dispose/missing drain ack) with retry, duplicate `Close`
  idempotence, host-retained resolver lease negative control and release, `NativeRejected`
  author-admission gates A/B/C, wrong-group cleanup token, reentrant entry, and framework/author
  exception retirement followed by a succeeding group. Every group must collect both domains.
- `--framework-native` — the trusted framework native call returns a real value in the ordinary
  framework context.
- `--rejected-author` — gate A: the real framework image passes the framework catalog phase; gate B:
  the rejected author bytes fail strict intake on their own P/Invoke; gate C: a grouped `Open`
  rejects in the author catalog phase with zero host records.
- `--callback-policy` — 2/2: the author-installed callback runs during `InvokeFramework` with no
  `InvokeAuthor` scope, reflects an explicitly denied target (`System.String.StartsWith`) and the
  origin scan rejects it (in-process record plus host-owned boundary error without inner);
  framework-owned reflection through a private marker stays allowed and does not re-initialize state.
- `--dynamic-rejected` — the host reads `fixtures/dynamic/...NativeRejected.dll` before `Open` and
  passes the bytes through the contract's `byte[] DynamicImage` property; during a normal entry the
  author resolves its own context and calls `LoadFromStream(new MemoryStream(host.DynamicImage,
  writable: false))` on it. The image is outside the initial role catalogs, so the strict load hook
  rejects it with a host-owned `InvalidDataException` naming the P/Invoke/IL-intake reason; no
  `ALLOWED` record, both domains collect, next group succeeds.
- `--framework-copy` — temp author role with the exact native framework bytes opens and shares the
  selected framework instance token; the same identity with different bytes is rejected for the byte
  mismatch before any code runs.
- `--rollback` — a wrong author entry method fails `Open` after the contexts exist. Contexts are
  observed only as weak references captured in an `AssemblyLoad` handler unhooked in `finally`; the
  failure is a host-owned `InvalidDataException` naming the missing entry with no inner exception,
  no framework/author records or retained roots exist, every observed context collects, and the next
  normal group succeeds.
- `--unload-retry` — 3/3 host-owned `AssemblyLoadContext.Unloading` handler cases (no product hook):
  framework handler throws once then `Close` retry; author handler throws after the framework request
  then retry; `Dispose` retirement failure then controlled retry. Each asserts a host-owned
  `InvalidOperationException` naming `UnloadHandlerException` with no inner, the correct phase text,
  `IsClosed` false after the failure, entries rejected, a completing retry, terminal ticket flags
  true with null failure fields, collection of both domains after the `NoInlining` helper returns,
  handlers removed before observation, and a succeeding next group.

Diagnostic-only modes (not acceptance): `--diagnose-prewarm`, `--positive-prewarm`, `--portable`.

## Session-origin-scan prerequisite

The grouped profile preflights the required-interpreter bridge and the session-origin-scan CoreLib
capability at the top of `Open`, before any context or author image exists. The private test process
must be started with BOTH switches:

    RuneCLR.EnableReflectionPolicy=true
    RuneCLR.EnableReflectionPolicyOriginScan=true

The capability is read at process start; a late managed switch does not enable it. `--positive` and
`--framework-native` fail fast when capability bit 0 is absent, so no v4-only runtime is used
silently and no positive case is counted as skipped.

## Private runtime launch (parameterized; no machine paths)

Point the launcher at a private Release x64 layout and an owned runtimeconfig; the repository
contains no machine path.

```powershell
$dotnet  = Join-Path $env:GROUPED_HOST_RUNTIME_LAYOUT 'dotnet.exe'
$harness = 'tests/RuneCLR.GroupedHost.Tests/bin/Release/net11.0/RuneCLR.GroupedHost.Tests.dll'
& $dotnet exec --runtimeconfig $env:GROUPED_HOST_RUNTIMECONFIG $harness --positive
```

The runtimeconfig selects `Microsoft.NETCore.App` 12.0.0 (`rollForward: Disable`) and sets both
switches:

```json
{ "runtimeOptions": { "tfm": "net11.0",
  "framework": { "name": "Microsoft.NETCore.App", "version": "12.0.0" },
  "rollForward": "Disable",
  "configProperties": {
    "RuneCLR.EnableReflectionPolicy": true,
    "RuneCLR.EnableReflectionPolicyOriginScan": true } } }
```

A second config that enables the policy but not the origin scan is used only for
`--origin-negative`.

## Capability witness vs method witness

The [November 17 method-entry experiment](../../docs/experiments/grouped-method-witness-20261117.md)
adds a separate external CDB collector and verifier. Its accepted Windows x64
capture has 16 framework JIT / author interpreter observations across A/B/A
and recovery, including a direct method-group callback. The original closure
callback remains behavior-only. See the [collector instructions](../../eng/grouped-method-witness/README.md)
for explicit private-runtime inputs and fresh output paths.

`--method-witness-fixture` validates scalar identities and lifecycle gates and
exits 0 without claiming execution mode. `--method-witness` deliberately exits
3 (NOT-VERIFIED) because host records cannot self-verify. Both modes keep every
host record's witness_verified=false. Only the external verifier report carries
the measured verdict. Without an attached native debugger, explicitly enabling
the checkpoint environment is refused before DebugBreak.

- Capability witness: `--runtime-check` and `--origin-negative` prove the process configuration and
  the fail-closed preflight, not how any method executes.
- Functional/metadata probes: `--probe-entry`, `--policy-audit`, `--rejected-author` and the
  functional cases prove their metadata/admission/execution outcomes. Those modes alone do not
  prove that a body ran interpreted or JIT-compiled; no tier or performance claim is made.

## Host contract, policy and exception contracts

`TestHost` owns every external root the fixtures install (the author's `host.Subscribe` delegate and
the optional `DynamicImage` payload); releasing that list — never clearing business statics — is what
lets a group retire. `DynamicImage` is empty except in `--dynamic-rejected`, where the host fills it
before `Open`.

`GroupedHostFixturePolicy` is default-deny. It delegates ordinary BCL decisions to the shared
gameplay surface and adds only exact plumbing: the contract members (including `get_DynamicImage`),
the framework fixture member list, `System.Action` construction/invocation, `System.Guid.NewGuid`,
`ArgumentNullException.ThrowIfNull`, `Object.GetType`, `Exception.GetType`/`get_InnerException`,
`Type.GetMethod`/`GetTypeFromHandle`/`get_Assembly`, `MethodBase`/`MethodInfo.Invoke`, the
`Assembly` type, `RuntimeTypeHandle`, `MemberInfo.get_Name`, `AssemblyLoadContext.GetLoadContext`/
`LoadFromStream`, `MemoryStream..ctor`, the `Stream` type, and the `System.Runtime.Loader` assembly
reference (name, public-key token, culture and retargetable checked). It denies `CreateDelegate`
and one explicit target (`System.String.StartsWith`) used by the callback case. Direct author
P/Invoke is never granted: the author image is rejected by byte intake first.

Two failure contracts are asserted separately: bad entry metadata/signature (including an
after-context `Open` rollback) is a host-owned `InvalidDataException` with no inner exception,
naming the offending entry and carrying no stack; author/framework execution failures are a
host-owned `InvalidOperationException` with no inner exception naming the bounded fixture exception
type. The obsolete original fixture message is neither required nor asserted.

## Unloading-handler evidence wording

`--unload-retry` attaches host handlers to `AssemblyLoadContext.Unloading`. The evidence is: the CLR
raises that event for a context exactly once, even when the handler throws; the retry then succeeds
without the event being raised again. That event count is not an instrumented count of `Unload()`
calls or of native unload transitions, so the observation alone does not prove "no duplicate call".
The no-duplicate-request property is asserted separately by the protocol/source flags (the session
marks a role as requested only after `Unload()` returns normally), and by the ticket reporting both
roles requested with null failure fields after the retry.

## Final result (Windows x64, rev2 cut)

`--positive` 8/8, `--framework-native`, `--rejected-author`, `--callback-policy` 2/2,
`--framework-copy`, `--dynamic-rejected`, `--rollback`, `--unload-retry` 3/3, plus `--stock-negative`
2/2, `--policy-negative` 11/11, `--policy-audit` 0 denials and the capability negatives. Historical
failing runs remain in the artifact directory as evidence; there are no current known runtime
blockers.
