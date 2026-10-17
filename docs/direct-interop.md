# Direct host and script objects

Draft of interop facts already measured. This does not close #14. It is not an iOS result.

## Measured on desktop

Trusted-update selector cases already record OBJECT-SAME when the update echoes the same host reference it was given. Negative cases record that OBJECT-SAME is absent when the wrong method would have run. That is reference identity for those echo calls, not a serialized copy, and not a framework-wide API pass.

The 2026-10-16 desktop trusted composition recorded object-identity sessions A,B,A,A,A and HostIdentity=true. Combined collectible R2R acceptance stays blocked. Do not pursue unloadable hot-update R2R.

Map sessions copy entity ids and names, resource names, and posted event ids between callbacks. Copying or posting after Stop throws. Two live sessions do not share resource names or posts. A host can retain a stopped session while its report stays host-owned. Recorded failure results do not keep the script exception text.

On 2026-10-16, eng/verify.ps1 exited 0 and did not start a simulator.

## Not accepted from these facts

The shape table below is not every supported or unsupported type. TrustedUpdateMutableBox is one measured host class, not a general contract for arbitrary classes. A retained update field keeping one host object alive is measured. A retained script instance or delegate keeping its collectible map context alive is also measured. The delegate case is not a UGC grant. Physical iOS was not run. The iPhone XR on iOS 18.7 is not a target of the iOS 27 runtime. Full .NET and arbitrary NuGet are not accepted. This document does not close #14.

## Explicitly untested

These are not implied by the measured rows.

- Ref structs, pointers, and function pointers.
- An arbitrary third-party assembly or NuGet package.
- Physical iOS. The iPhone XR on iOS 18.7 is not a target of the iOS 27 runtime.

## Measured shapes

These rows are desktop results already recorded. A blank shape is not a pass.

| Shape | Recorded result |
| --- | --- |
| System.Object through EchoGeneric | OBJECT-SAME. ReferenceEquals is true. The type has no writable fields. |
| string through EchoGeneric | STRING-SAME. The string is immutable. |
| int through EchoGeneric | INT 11. This is a value, not a reference-identity claim. |
| int[] through MutateFirst | MUTATE-SAME. Element 0 becomes 7 and the array reference is unchanged. CALLS stays 3. |
| TrustedUpdateMutableBox through MutateBox | BOX-SAME. Value becomes 7 and the instance is unchanged. |
| A value passed to the object echo | VALUE-REJECTED. The echo is not called. |
| Instance-only, inherited, or private-only echo | ECHO ActivationFailed. Counters stay 0. OBJECT-SAME is absent. |
| Interface callback | Desktop composition recorded nine interface callbacks and HostIdentity=true. Not a UGC grant. |
| Trusted composition delegates | Desktop composition recorded nine delegate calls and HostIdentity=true. The host report retains neither the exception nor author metadata, delegates, or objects. Not a UGC grant. |
| Released host input and held object | EchoDifferentStillSucceeds records INPUT-COLLECTED and HELD-COLLECTED, and does not record INPUT-ALIVE or HELD-ALIVE. |
| Update static reference | RetainedIdentityStaysAlive records BEFORE-ALIVE while the update Held field stores the host object, and AFTER-COLLECTED after ReleaseHeldObjects. |
| Retained script instance | RetainedScriptKeepsContext keeps the collectible map context alive while the test holds the script instance, then unloads it after that reference is dropped. |
| Retained script delegate | RetainedDelegateKeepsContext keeps the collectible map context alive while the test holds only the script delegate, then unloads it after that delegate is dropped. Not a UGC grant. |

## Restricted UGC

The gameplay profile allows IMapContext members get_MapId, SpawnEntity, DestroyEntity, Log, and Charge. It still excludes Signal, RaiseSignal, the tick schedule, Repeat, host-completed work, resource registration, and host-posted events. Delegate callbacks stay denied. Trusted updates are not limited to this profile.

This profile is the current prototype host allowlist. It does not define the UGC mechanism, and it does not require a game to have entities. Trusted updates remain outside this profile. A host-defined API is not implemented here. On 2026-10-17 its decided shape is a game-owned shared CLR interface called directly by the script. IMapContext is not renamed.

HostContractSession loads private assemblies named by the package into the same collectible context. A script may call methods on those assemblies, and a declared private assembly may call back into the entry or into another declared private assembly. A later Invoke may pass one int into a void callback, and InvokeInt may return one int. The callback is checked before it runs. OnStart may construct a type declared by those assemblies. A framework constructor is still rejected. The called method is checked before it runs, and a BCL call such as System.IO.File.ReadAllText is rejected. This does not add a BCL allow list and does not change the gameplay profile. The package validator accepts an OnStart call into the entry or a declared private assembly and checks that method. A BCL call is still rejected.

## Calls the selector does not make

Desktop selector tests EchoInstanceOnlyIsNotCalled, EchoInheritedIsNotCalled, and EchoPrivateOnlyIsNotCalled require OBJECT-SAME to be absent. Those tests record ECHO ActivationFailed, leave the echo counters at 0, and do not print OBJECT-SAME. This is not a complete list of unsupported shapes, and it does not close #14.

## Echo payload

The successful OBJECT-SAME case is GenericSample in samples/RuneCLR.TrustedUpdateHost/Program.cs. It passes new object() to TryEchoGenericObject. EchoGeneric returns that argument unchanged, and the host checks ReferenceEquals. System.Object has no instance fields and no writable properties. The same sample also echoes a string, which is immutable. The following sections measure an in-place array element and TrustedUpdateMutableBox. This does not close #14.

## In-place mutation

GenericSample calls MutateFirst with a one-element int array after the existing echo checks. The update writes 7 into element 0 and returns the same array. The desktop self-test prints MUTATE-SAME together with OBJECT-SAME and CALLS 3. The trusted-update selector suite passed in that Release run. This is one array store, not an arbitrary host class, and it does not close #14. It is not an iOS result.

## Host class mutation

PersistedAssemblyBuilder in WriteGenericAssembly is constructed with typeof(object).Assembly. Its only constructor does not take a reference list, so RuneCLR.TrustedUpdate.dll cannot be supplied as the core assembly. MutateBox still names TrustedUpdateMutableBox in its signature, and the emitter records that reference. The method sets Value to 7 and returns the same instance. The desktop self-test prints BOX-SAME together with OBJECT-SAME, MUTATE-SAME, and CALLS 3. The trusted-update selector suite passed in that Release run. This is one host class, not every type shape, and it does not close #14. It is not an iOS result.
