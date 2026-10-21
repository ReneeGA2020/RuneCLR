# Direct host and script objects

Draft of interop facts already measured. This does not close #14. It is not an iOS result.

## Measured on desktop

The 2026-10-21 stock-SDK generic fixture covers mutable reference identity,
three structurally different value types, nested generic containers, generic
interface dispatch, generic delegates and an internal module-owned value type
unknown when the Host was built. Host has no module dependency; its resident
outputs stay unchanged during the late A/B builds. A throwing callback leaves
the ledger unchanged, closes the session and makes the next call return Closed.
The Lead offline validation (archival/local evidence: `../artifacts/lead-offline-integration-20261021/VALIDATION.md`)
and independent Orca Worker source/raw review support these selected behaviors;
the reviewer independently recomputed all six checksums. Runtime comparisons
share a checksum helper, so they alone are not an independent algorithm oracle.
The original campaign exceeded its allowed 4 builds/2 Hosts with actual totals
of 6 builds/4 Hosts across w01/w02. Their different binaries and w01 reporting
failure remain preserved. This is stock managed compatibility evidence only;
R2R/interpreter method attribution and collection remain unproven here.

The Lead also accepted a bounded resident stock .NET 11 RC2 Windows x64
observation: exactly two separately released fresh Host invocations, A then B
(PIDs 872/27340, exit 0), six fixture-derived shape outcomes plus callback
failure, and resident mode with contextIsCollectible=false,
unloadRequested=false and collectionClaimed=false. The campaign used a new
Host/Contracts/TrustedUpdate trio plus retained w02 A/B module images, which is
mixed build provenance rather than one same-build campaign; it performed zero
builds/crossgen. A callback failure preserves ledger state and the next call
returns Closed. The
Lead validation (archival/local evidence: `../artifacts/lead-resident-stock-review-20261021/VALIDATION.md`)
records 138 audit checks. This remains stock managed interoperability only: no
R2R/native execution, interpreter selection/fallback, collection/unload,
iOS/device or restricted-UGC claim follows; devices remain skipped.

The 2026-10-21 generic body diagnostic is a separate diagnostic observation,
not an interop shape acceptance. One isolated stock compile (exit 0, zero
warnings/errors) produced an r2 Host, followed by a bounded two-process stock
smoke: default-off PID 33988 and enabled PID 29052, both exit 0, resident, with
source-derived A goldens (reference 118189, aggregate -6047711, ledger 248/6)
and CallbackFailed then Closed in both lanes. The enabled lane recorded six
ordered success records for Echo/Measure/LateRoundTrip with actual closed type
MVIDs, nonzero raw PCs and TypeHandles and no capture errors; the disabled lane
only omitted the diagnostic field. Mixed provenance (new r2 Host trio plus
retained Module A IL and leaf) and post-hoc after-pins from an offline repair
are part of the record. Raw PCs remain unclassified, so this does not establish
native/R2R/interpreter/fallback execution, a module-side invocation join,
PC/image/RuntimeFunction attribution or whole-method behavior. This earlier
fnptr diagnostic campaign is its own bounded observation: the Lead review passes
137 checks and the independent audit passes 333 checks. It has no module-side
records; its enabled Host-side diagnostics carry closedMethodKeys with
implementation MethodDefs 0x060000A1/0x060000A2/0x060000A6.

The later module-invocation witness stock smoke is distinct: default-off PID
40020 then enabled PID 28180, both exit 0 with timeout false and no retry. The
enabled lane has six ordered Host records plus one witness header and twelve
module phase records for Echo 2, Measure 3 and LateRoundTrip 1. Its 22,053-byte
witness file has SHA-256
6e2e0252c418ad182fd7ae39ad0f605fae3e6eef7c9d721bcfed58014514c6ad; the
disabled lane omits diagnostics. Independent audit passes 370 checks over 80
pins with zero drift and no new products. Static PE metadata links MethodSpecs
0x2B000002/000007/00000C/000011/00001B to callvirt at GameModule.Run IL
offsets 64/198/392/505/618/1161; this is static callsite metadata, not a runtime
module PC. Host implementation MethodDefs 0x060000A1/0x060000A2/0x060000A6 are
distinct from Contracts interface MethodDefs 0x06000008/0x06000009/0x0600000D.
The campaign's provenance is mixed (r2 Host nine-file layout, corrected Module A
build and retained leaf; module MVID 8a8309a7-f2c2-40ed-93b2-0ac9a523007f,
Contracts MVID f601ceab-2245-471d-bd7c-bf86905853db). This is recorded
functional/text correlation, not proof of runtime ResolveMethod, reflective
CurrentScenario, dispatch, module PC/IR/native/interpreter/R2R/fallback, unload,
iOS/device or overall acceptance. See the
stock acceptance (archival/local evidence: `../artifacts/lead-module-invocation-witness-review-20261021/stock-independent-acceptance.json`)
and
D:/RuneCLR-artifacts/trusted-game-generic-module-witness-stock-audit-l12z-20261021/REVIEW.md.

The current generic-runner strict context validation passes 64 default and 136
explicit checks, rejects 66/66 mutations and rejects each/both missing
unloadRequested/collectionClaimed fields. Historical F3 443-per-campaign counts
remain historical and were not produced by this validator. See the
Lead context checks (archival/local evidence: `../artifacts/lead-resident-stock-review-20261021/context-checks.json`).

The 2026-10-21 generic R2R build root
D:/RuneCLR-artifacts/trusted-game-generics-r2r-build-20261021-x3yd3fe4
records exactly three managed builds, five independent non-composite crossgen
images and zero Host executions. New A/B module images were built after the
Host; Host/Contracts/TrustedUpdate outputs stayed frozen during those late
builds, source inputs were unchanged, and each module pair preserves IL/R2R
MVID parity. The
Lead audit (archival/local evidence: `../artifacts/lead-generic-r2r-build-review-20261021/VALIDATION.md`)
and artifact checks (archival/local evidence: `../artifacts/lead-generic-r2r-build-review-20261021/checks.json`)
pass 414 artifact checks. The parent report's 8-byte-stride R2R section
tables remain a retained defect; corrected 12-byte type/RVA/size tables are
accepted only in the fresh derivative
D:/RuneCLR-artifacts/trusted-game-generics-r2r-report-repair-20261021-x3yd3fe4,
with seven parser tests and 377 repair checks (archival/local evidence: `../artifacts/lead-generic-r2r-build-review-20261021/repair-checks.json`), all 226 parent files preserved
and no product reruns. This is build/report evidence only, not generic native
or interpreter execution and not same-source behavioral acceptance.

The actual maps contain canonical Echo and LateRoundTrip rows only. Measure has
copied IL and no selected native row. An empty exactHostCandidates set does not
prevent a future canonical Echo witness joined to the actual T identity, PC,
PID and call id. Map absence and module fixups are not interpreter evidence.
The
map supplement review (archival/local evidence: `../artifacts/lead-generic-map-supplement-review-20261021/VALIDATION.md`)
passes 31 offline checks; no deliberate root is released.

The portable constructed-generic IR reader has 28 synthetic/source-shaped tests
and rejects four former malformed-input acceptances. It is text-only, retains
exact generic arguments and complete signatures, and derives no assembly,
token, MVID, real-dump, executed-method or execution-mode evidence. See the
Lead hardening validation (archival/local evidence: `../artifacts/lead-generic-ir-hardening-review-20261021/VALIDATION.md`).
The reader/test wiring is now Lead-accepted in maintained local verification
and CI configuration. eng/verify.ps1 and .github/workflows/ci.yml each gained
exactly two lines invoking the 28-test suite once immediately after
generic-interaction portability, with a PowerShell exit guard and unchanged
three-OS matrix. Exact before/after bytes were verified; 60 Lead checks and
PowerShell AST (PS_PARSE_OK), YAML parsing and scoped git diff --check pass. One
measured local Windows invocation exited 0 with 28 tests, zero failures/errors
and zero products. Remote CI was not triggered; the three-OS matrix is
configured, not executed. Reader/test source hashes are unchanged.

A module/Host runtime join still has a concrete constraint that is not met: the
module MethodSpec resolves to the Contracts IGameHost interface MethodDef,
while the Host body records identify the implementing HostGameHost MethodDef.
Literal token equality is not a valid join. The original module witness compile
is terminal FAILED: one Module.A build (PID 45948, exit 1) produced two CS0118
errors at ModuleInvocationWitness.cs 227:36 and 254:49 (Module namespace versus
System.Reflection.Module); Module.B was not attempted and no module DLL exists.
The corrected two-line System.Reflection.Module derivative has three cumulative
stock build commands: the retained failed Module.A command plus successful
Module.A and Module.B, A before B, with no Host execution. This is compile-only
acceptance; this corrected compile campaign itself has zero Hosts and no runtime
module records, and runtime MethodSpec resolution and serialization remain
unestablished for it. The separate later stock smoke above supplies actual
module records and static callsite metadata, but not independently proven
runtime dispatch; there the Host implementation MethodDefs are distinct from the
Contracts interface MethodDefs.

Join reader r5 passes 138 tests with an independent GO only within a trusted
caller-supplied descriptor and limited CoreLib profile; TypeDef kind/bounds are
syntactic and descriptor provenance is not PE-derived. Static exporter r3 passes
61 checks and 48 negatives under a scoped retained implicit-signature/
no-MethodImpl static PE/IL profile; it is not general ECMA completeness or
runtime dispatch. Demux r4 passes 34/22 original, 9/2 fixes and 93/73 regression
cases with 89 canonical splits and three actual reference reconstructions; exact
and canonical are retained-reference GO only under an externally pinned
caller-trusted manifest, while structure mode leaves caller-selected intops
unanchored and all reference flags false. See the
r5 acceptance (archival/local evidence: `../artifacts/lead-module-invocation-witness-review-20261021/join-reader-r5-independent-acceptance.json`),
r3 exporter acceptance (archival/local evidence: `../artifacts/lead-module-invocation-witness-review-20261021/static-export-r3-independent-acceptance.json`)
and
r4 demux acceptance (archival/local evidence: `../artifacts/lead-entry-r6-offline-repair-r3-review-20261021/r7-demux-r4-independent-acceptance.json`).

The original r7 entry campaign remains FAILED: two stock Publishers plus stageA
and stageB Hosts all exited 0; stageA validation passed before stageB launch,
stageB was rejected with EntryProbeError entry-unknown-prefix 1890, and recoverB
was never launched. No retry was released, and offline reconstruction does not
change that status. The r9 recorded module/Host text correlation is accepted
only as an offline artifact result under a caller-trusted 50-input manifest: 138
synthetic, 79 recorded (71 intended negatives) and 7 manifest tests pass; 49
hashes, 48 outputs and 50 pins verify. Enabled PID 28180 records six Host records
and twelve module phases; off PID 40020 validates identity, business closure and
resident context without fabricated records. The r8 bad pin is preserved and r7
remains frozen unchanged; the original r7 campaign remains FAILED at
entry-unknown-prefix 1890 with recoverB absent. The general manifest_tool API is
not accepted because beforeUnchanged is unconditional, write_entries trusts a
supplied pathKey, and verify_relative_manifest lacks general containment. None
of the offline reader, exporter or demux results is a
runtime/native/interpreter/R2R/fallback/PC/whole-method/unload/iOS/overall
acceptance. See the
[milestone evidence summary](validation/trusted-update-milestone-20261022.md#r9-recorded-text-correlation).

Trusted-update selector cases already record OBJECT-SAME when the update echoes the same host reference it was given. Negative cases record that OBJECT-SAME is absent when the wrong method would have run. That is reference identity for those echo calls, not a serialized copy, and not a framework-wide API pass.

The 2026-10-16 desktop trusted composition recorded object-identity sessions A,B,A,A,A and HostIdentity=true. Combined collectible R2R acceptance stays blocked. Do not pursue unloadable hot-update R2R.

The 2026-10-18 two-contract stock desktop IL integration has joined scoped
acceptance at `artifacts/lead-generic-native-start-20261018ck/receipt.json`.
Orbit and Quest call their own shared CLR host interfaces through the same
generic resident owner. The host observes position 0/3/6 and stars 0/4/8,
callback counts 0/1/2, and unchanged state after the failing call. Fresh rounds
use distinct actual module references. Signed return-only modules enter the
same normal child modes and fail the first ordinary state/count predicate.
The cached control changes the owner Host; it is not a signed cached author
module. These are stock IL results. The separate native attempt preserves the
business predicates across eight honest processes, but independent review
rejects native binding because all 18 armed attempts lack targeted frames.
That result does not change the stock-IL gate or establish native interaction.
See the review (archival/local evidence: `../artifacts/generic-native-delivery-review-cc7q-20261018/review.md`).
COLLECT host1Alive=True is not unloading.

Map sessions copy entity ids and names, resource names, and posted event ids between callbacks. Copying or posting after Stop throws. Two live sessions do not share resource names or posts. A host can retain a stopped session while its report stays host-owned. Recorded failure results do not keep the script exception text.

On 2026-10-16, eng/verify.ps1 exited 0 and did not start a simulator.

## Not accepted from these facts

The shape table below is not every supported or unsupported type. TrustedUpdateMutableBox is one measured host class, not a general contract for arbitrary classes. A retained update field keeping one host object alive is measured. A retained script instance or delegate keeping its collectible map context alive is also measured. The delegate case is not a UGC grant. Physical iOS was not run. The iPhone XR on iOS 18.7 is not a target of the iOS 27 runtime. Full .NET and arbitrary NuGet are not accepted. The generic R2R build/report and map supplement do not establish executed generic bodies, interpreter/native selection or same-source behavioral acceptance. This document does not close #14.

## Explicitly untested

These are not implied by the measured rows.

- Ref structs, pointers, and function pointers as interop shapes. The r2
diagnostic uses a host-side function-pointer leaf call inside Host generic
bodies; that is not function-pointer interop and is not native/interpreter
evidence.
- An arbitrary third-party assembly or NuGet package.
- A real constructed-generic interpreter dump, executed constructed method body, assembly/token/MVID attribution or execution-mode observation.
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

This profile is the current prototype host allowlist. It does not define the UGC mechanism, and it does not require a game to have entities. Trusted updates remain outside this profile. The desktop score-game sample runs a shared host contract. See score-game.md. On 2026-10-17 its decided shape is a game-owned shared CLR interface called directly by the script. IMapContext is not renamed.

HostContractSession loads private assemblies named by the package into the same collectible context. A script may call methods on those assemblies, and a declared private assembly may call back into the entry or into another declared private assembly. A later Invoke may pass one int into a void callback, and InvokeInt may return one int. Either callback may also take the host contract before that int. The callback is checked before OnStart runs, including by the package validator when that shape is a public method on the entry. The error names the callback and the rejected member. OnStart may construct a type declared by those assemblies. A framework constructor is still rejected. The called method is checked before it runs, and a BCL call such as System.IO.File.ReadAllText is rejected. This does not add a BCL allow list and does not change the gameplay profile. The package validator accepts an OnStart call into the entry or a declared private assembly and checks that method. A BCL call is still rejected.

## Calls the selector does not make

Desktop selector tests EchoInstanceOnlyIsNotCalled, EchoInheritedIsNotCalled, and EchoPrivateOnlyIsNotCalled require OBJECT-SAME to be absent. Those tests record ECHO ActivationFailed, leave the echo counters at 0, and do not print OBJECT-SAME. This is not a complete list of unsupported shapes, and it does not close #14.

## Echo payload

The successful OBJECT-SAME case is GenericSample in samples/RuneCLR.TrustedUpdateHost/Program.cs. It passes new object() to TryEchoGenericObject. EchoGeneric returns that argument unchanged, and the host checks ReferenceEquals. System.Object has no instance fields and no writable properties. The same sample also echoes a string, which is immutable. The following sections measure an in-place array element and TrustedUpdateMutableBox. This does not close #14.

## In-place mutation

GenericSample calls MutateFirst with a one-element int array after the existing echo checks. The update writes 7 into element 0 and returns the same array. The desktop self-test prints MUTATE-SAME together with OBJECT-SAME and CALLS 3. The trusted-update selector suite passed in that Release run. This is one array store, not an arbitrary host class, and it does not close #14. It is not an iOS result.

## Host class mutation

PersistedAssemblyBuilder in WriteGenericAssembly is constructed with typeof(object).Assembly. Its only constructor does not take a reference list, so RuneCLR.TrustedUpdate.dll cannot be supplied as the core assembly. MutateBox still names TrustedUpdateMutableBox in its signature, and the emitter records that reference. The method sets Value to 7 and returns the same instance. The desktop self-test prints BOX-SAME together with OBJECT-SAME, MUTATE-SAME, and CALLS 3. The trusted-update selector suite passed in that Release run. This is one host class, not every type shape, and it does not close #14. It is not an iOS result.
