# Trusted composition delivery

This note records the desktop host under `eng/trusted-composition-delivery/Host`. It connects the existing signed-release staging and recovery helpers to the existing TrustedComposition Update A/B, Private A/B, and IlOnlyHelper projects. It does not change those projects, the trusted-update core, or the old composition host.

The measured run is stock desktop JIT. It is not R2R evidence, not interpreter evidence, and not iOS.

## Boundary

The host references Contract, RuneCLR.TrustedUpdate, and DeliveryAppDep for compile and copy. DeliveryAppDep exists so a TPA application assembly can be distinguished from the framework. It is not part of a signed update manifest. Update A and Update B are build dependencies only (`ReferenceOutputAssembly=false`, `Private=false`). The host deps file does not list Update, Private, or IlOnlyHelper. The activator loads the signed entry in a non-collectible load context and resolves additional content from the verified manifest. One process selects one version. There is no unload and no collection claim.

`WindowsEntryObservation.cs` is compiled into this same assembly with a `Compile` link. The observation source is not modified and is not a separate referenced assembly.

A failed stage calls `TrustedReleaseRecovery.TryStart` with no offer and keeps the stage failure on `STAGE`. The source directory is not a candidate. A successful stage offers only `FinalDirectory`. The production CLI has no `--offer` override. The receipt stays outside the releases root. The self-test parent signs with an in-memory P-256 key; child processes read the SPKI file only. Unsigned last-known-good is not consulted.

File reads are bounded: the signed document is at most `TrustedRelease.MaxDocumentBytes`, and the SPKI must be exactly `TrustedRelease.SpkiBytes`. Argument errors and IO failures are short codes. The process does not print exception objects.

## Resolver

The load context shares the host Contract assembly only when the simple name matches and the full name is exactly the host Contract identity. A different Contract identity throws `contract` and does not fall through. A manifest file is loaded only when its full name matches the request. The self-test compares loaded files by canonical path, not by an unresolved GetFullPath prefix. Ancestor directory links are followed component by component. The loaded entry, private, and helper must be the exact signed files. Assembly simple names use ordinal ignore case. That comparison is not an OS path rule.

Default sharing is not every `TRUSTED_PLATFORM_ASSEMBLIES` entry. A name falls through to the default binder only when every TPA path for that simple name is inside the directory that actually contains `System.Private.CoreLib`. That directory comes from `typeof(object).Assembly.Location`, not from a folder name or a `System.*` prefix. The request must match that file's name, and its version, culture, and public key token when those parts are present. `TrustedComposition.DeliveryHost`, `RuneCLR.TrustedUpdate`, and any other application DLL live outside that directory, so a TPA simple name does not load them. Returning null is only this framework fall-through. It is not a sandbox and it is not a complete deny list.

Before the author assembly is loaded, the verified entry and additional files are inventoried. An empty or unreadable assembly identity returns `assembly-identity`. Two files with the same assembly simple name return `duplicate-assembly`. The last path does not replace the first. Both checks run after the activator has been entered, so the process gate stays occupied, the receipt is not rewritten, and the host does not fall back. The detail is an owned short code on `ActivationFailed`, not a plan failure.

An unlisted helper beside a final directory is still `helper-not-listed`. That result alone does not prove the manifest boundary. The same self-test also calls `DeliveryAppDep.Marker.Touch` from a signed entry whose manifest does not list `DeliveryAppDep`. That assembly is on the host TPA list, beside the host, and outside the framework directory. The call does not run, the dependency is not loaded, calls stay 1, and no receipt is written. A signed package with Private A and Private B at different relative paths fails with `duplicate-assembly` before `TrustedComposition.Update.A` is loaded. The previous receipt bytes stay, and the same process does not restore A. A signed non-assembly file fails with `assembly-identity` the same way. Framework and Contract sharing still let stage A return 101/310 and stage B return 202/613.

## Observation

`FACTS` is the last printed line and is primitive `DeliveryFacts` JSON (`IncludeFields`). `WITNESS` lines, when `TRUSTED_COMPOSITION_WITNESS=1` on Windows x64, use the `NativeWitness` keys `Label`, `Pc`, `Image`, `AllocationBase`, `Rva`, and `Executable`. Paths stay inside the JSON string.

`ENTRYOBSERVATION` is optional. It runs only after this `Execute` has loaded the helper, only on Windows x64, and only when `RUNECLR_POST_EXECUTION_PRECODE=1`. The expected interpreter bit comes from `RUNECLR_DELIVERY_EXPECT_HELPER_INTERPRETED=1` or `0`. Capture reads the post-call entry of `Compute`. It does not invoke the helper a second time. The evidence string is the checked helper value from this call, or the expected author exception after the helper ran. The `MethodInfo` is not retained. A precode mismatch prints `{"Error":"precode"}` and leaves the activation result unchanged. The environment variable is not itself proof of execution.

`DeliveryHostObject.Touch` stays `NoInlining` and still calls `ExecutionWitness.Capture("host")`. The native symbol is not `TrustedComposition_HostObject__Touch`. The old assessor is not adapted here.

## Evidence

The experimental Host also exposes a signed typed-session integration check:

```text
dotnet run --project eng/trusted-composition-delivery/Host/TrustedComposition.DeliveryHost.csproj -c Release --no-build -- --integration
```

The activator constructs the verified IUpdateModule before binding it to
TypedSession. InvokeLogical borrows a synchronous typed callback; CloseLogical
clears the session module and the owner's separate host root. Close does not
unload the resident context, reset statics, release the process gate or rewrite
the receipt. The fixed author-failed token means a callback threw a managed
exception; it does not identify its cause. Initial activation keeps the existing
loader failure codes. The ten integration checks cover successive calls, close
while a signed call is active, reentry, host ownership, unchanged receipts,
process locking and fresh-process recovery. The Release solution build, local
verification and CI include this check. See the [typed ownership brief](trusted-embedding-next.md)
for exact accepted source combinations and runtime evidence.

Command:

```text
dotnet build eng/trusted-composition-delivery/Host/TrustedComposition.DeliveryHost.csproj -c Release --nologo
eng/trusted-composition-delivery/Host/bin/Release/net11.0/TrustedComposition.DeliveryHost.exe --self-test
```

The Release build reported 0 warnings and 0 errors. The apphost self-test exited 0 and printed `SELFTEST PASS`, including:

- stage A executes 101/310
- next process restores A without staging
- bad signature restores A before activation
- tampered source private restores A before activation
- existing final restores A and does not execute source B
- author failure does not fall back or replace the receipt (`SECOND None/ProcessSelectionLocked/None/locked calls=0`, `TOTAL 1`)
- next process restores A after the locked failure
- unlisted helper on disk is not loaded (`TOTAL 1`, detail `helper-not-listed`)
- independent stage B executes 202/613
- tampered final private is refused with no call (`ContentMismatch`, calls 0)
- duplicate simple name does not load or replace the receipt (`DETAIL duplicate-assembly`, `CALLS 1`, `LOADED_ENTRY` empty, `PRIVATE 0`, `CANDIDATE None/None/ActivationFailed/activation`, same-process `SECOND None/ProcessSelectionLocked/None/locked calls=0`, `TOTAL 1`, receipt bytes unchanged)
- invalid assembly identity does not load or replace the receipt (`DETAIL assembly-identity`, `CALLS 1`, `LOADED_ENTRY` empty, receipt bytes unchanged, no fallback)
- unlisted TPA application dependency is not called (`TPA True`, `LOADED_DEP False`, `DETAIL unlisted-assembly`, `CALLS 1`, `PRIVATE 0`, no receipt file)

Stage A facts included private 101, helper 310, private version 1.0.0.0, touch 112, interface 20, delegate 20, generic 310, and shared identity. Stage B facts included private 202, helper 613, and private version 2.0.0.0. Witness lines were absent because the witness variable was unset.

## Not claimed

This is not a sandbox, a race-proof snapshot, network authentication, anti-rollback, crash-durable directory replacement, or an iOS native admission gate. Publishing still commits at the existing staging `Directory.Move`. Recovery still treats the activator call as the irreversible process gate.
