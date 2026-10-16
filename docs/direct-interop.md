# Direct host and script objects

Draft of interop facts already measured. This does not close #14. It is not an iOS result.

## Measured on desktop

Trusted-update selector cases already record OBJECT-SAME when the update echoes the same host reference it was given. Negative cases record that OBJECT-SAME is absent when the wrong method would have run. That is reference identity for those echo calls, not a serialized copy, and not a framework-wide API pass.

The 2026-10-16 desktop trusted composition recorded object-identity sessions A,B,A,A,A and HostIdentity=true. Combined collectible R2R acceptance stays blocked. Do not pursue unloadable hot-update R2R.

Map sessions copy entity ids and names, resource names, and posted event ids between callbacks. Copying or posting after Stop throws. Two live sessions do not share resource names or posts. A host can retain a stopped session while its report stays host-owned. Recorded failure results do not keep the script exception text.

On 2026-10-16, eng/verify.ps1 exited 0 and did not start a simulator.

## Not accepted from these facts

No matrix yet lists every supported and unsupported type or call shape. An arbitrary host class with in-place field mutation is not a general contract beyond the echo cases above. Physical iOS was not run. The iPhone XR on iOS 18.7 is not a target of the iOS 27 runtime. Full .NET and arbitrary NuGet are not accepted. This document does not close #14.

## Restricted UGC

The gameplay profile allows IMapContext members get_MapId, SpawnEntity, DestroyEntity, Log, and Charge. It still excludes Signal, RaiseSignal, the tick schedule, Repeat, host-completed work, resource registration, and host-posted events. Delegate callbacks stay denied. Trusted updates are not limited to this profile.

## Calls the selector does not make

Desktop selector tests EchoInstanceOnlyIsNotCalled, EchoInheritedIsNotCalled, and EchoPrivateOnlyIsNotCalled require OBJECT-SAME to be absent. Those tests record ECHO ActivationFailed, leave the echo counters at 0, and do not print OBJECT-SAME. This is not a complete list of unsupported shapes, and it does not close #14.
