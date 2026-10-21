# Development handoff

## Generic Body Diagnostic And Module Witness Handoff (2026-10-21)

The artifact-only r2 function-pointer body-witness candidate has one isolated
stock-SDK compile and a bounded two-process stock smoke; neither is execution
attribution. The compile root
D:/RuneCLR-artifacts/trusted-game-generic-body-fnptr-r2-compile-20261021-x3yd3fe4
records exactly one stock Host build command (exit 0, zero warnings/errors) with
no module execution. The Lead r2 compile review passes 268 checks and
recomputes all 97 original input seals. Separately, metadata-only inspect-il
assertions verify three direct calli sites inside three NoInlining generic
bodies and four kernel32 infrastructure imports; those are metadata-only checks,
not part of the 268-count provenance. See the
r2 compile validation (archival/local evidence: `../artifacts/lead-generic-body-fnptr-r2-compile-review-20261021/VALIDATION.md`).

The retained smoke root
D:/RuneCLR-artifacts/trusted-game-generic-body-fnptr-r2-stock-smoke-20261021-x3yd3fe4
contains exactly two released stock Host processes: default-off PID 33988 and
enabled PID 29052, both integer exit 0 and boolean timeout false. Pre-spawn
argv/cwd/environment match the process records; stdout equals the report bytes
and stderr is empty. Source-derived business goldens, counters, ledger and
failure closure are equal between lanes: reference 118189, aggregate -6047711,
ledger 248/6, CallbackFailed with unchanged ledger then Closed. The campaign is
resident and uses mixed build provenance (new r2 Host/Contracts/TrustedUpdate
trio plus retained Module A IL and retained leaf), not one same-build campaign.
The default-off report only omits the diagnostic field; no I/O trace exists, so
this is not a no-I/O claim. The enabled report has six ordered success records
(Echo 2, Measure 3, LateRoundTrip 1) with nonzero raw PCs and TypeHandles, no
capture errors, exact type MVIDs and closed-argument keys; raw PCs stay
unclassified and sharing unknown. This earlier fnptr diagnostic campaign is
its own bounded stock diagnostic observation: the Lead review passes 137 checks
and the independent audit passes 333 checks. It has no module-side records; its
enabled Host-side diagnostics carry closedMethodKeys with implementation
MethodDefs 0x060000A1/0x060000A2/0x060000A6.
The limitations of that diagnostic are part of the record: the launch harness crashed after both
lanes while serializing a tuple-keyed validation dict (TypeError), so reports and
after-pins were produced by an offline postprocessor without another Host run;
before-pins were written before the lanes but after-pins are POST-HOC, not
continuous immutability; five temporary harness scripts listed in the layout
snapshot were later removed and three logs added, while all consumed
lane/Host/module/leaf/pin entries remain hash-stable. See the
Lead smoke validation (archival/local evidence: `../artifacts/lead-generic-body-fnptr-r2-smoke-review-20261021/VALIDATION.md`)
and
D:/RuneCLR-artifacts/trusted-game-generic-body-fnptr-r2-smoke-audit-l12z-20261021/REVIEW.md
(SHA-256 750724b1f0242d83f172a8544453116273d9b56a18aafa795d91352bbed4564d).

The later module-invocation witness stock smoke is a separate campaign, not a
rerun of the fnptr diagnostic: exactly two stock-SDK Host processes ran, default
off PID 40020 then enabled PID 28180, both integer exit 0 and boolean timeout
false, with no third run or retry. The enabled lane has six ordered Host records
and produced one witness header and twelve module phase records for six calls
(Echo 2, Measure 3, LateRoundTrip 1), with source-derived business goldens equal
to the earlier campaign (reference 118189, aggregate -6047711, ledger 248/6).
Its 22,053-byte witness file has SHA-256
6e2e0252c418ad182fd7ae39ad0f605fae3e6eef7c9d721bcfed58014514c6ad; the
disabled lane omits diagnostics and has no witness file. Independent audit
passes 370 checks over 80 pins with zero drift and no new products.
Static PE metadata links MethodSpecs 0x2B000002/000007/00000C/000011/00001B at
GameModule.Run IL offsets 64/198/392/505/618/1161 to callvirt instructions;
this is static callsite metadata, not a runtime module PC. Host implementation
MethodDefs 0x060000A1/0x060000A2/0x060000A6 are distinct from Contracts
interface MethodDefs 0x06000008/0x06000009/0x0600000D. Provenance is mixed: the
r2 Host nine-file layout, the corrected Module A build and the retained leaf;
module MVID 8a8309a7-f2c2-40ed-93b2-0ac9a523007f and Contracts MVID
f601ceab-2245-471d-bd7c-bf86905853db. This is bounded stock functional/text
record correlation only: runtime ResolveMethod invocation, a reflective
CurrentScenario read and runtime module dispatch are not independently proven,
and no module PC/IR/native/interpreter/R2R/fallback, unload, iOS/device or
overall acceptance follows. See the stock acceptance (archival/local evidence: `../artifacts/lead-module-invocation-witness-review-20261021/stock-independent-acceptance.json`)
and
D:/RuneCLR-artifacts/trusted-game-generic-module-witness-stock-audit-l12z-20261021/REVIEW.md
(SHA-256 9ad56c924abd549f52529224c09100268375baa39ff3ccc3f114139ae8c9d6d5).

The r6 entry campaign remains FAILED-CLOSED: exactly two stock-SDK Publishers
and the stageA forced-control Host ran (PIDs 7836/24672/31904, all exit 0);
stageB and recoverB were not launched, and no retry occurred. The runner exited
1 with EntryProbeError entry-unknown-prefix 1892 on the native "Slot ... li"
fragment. An independent raw audit returns GO only for the bounded stageA
observation (gameplay 1/3/6, six intact kind-6 entry records, CALLERDLL hash),
and the offline repair still has no reusable acceptance. Version 1's actual
reading passed, but v1 remained NO-GO for reusable validation (independent
signature lineage absent, scalar types and framing too broad, IR row
order/duplicates wrong, negative-test setup masking). The successor r2 guarded
suite then passed 89 tests and 70 negatives with 57 pins, and fixed the Lead's
seven replay cases, but the Lead found an actual AssemblyRef public-key-token
byte-order bug: the retained Host's System.Runtime token b03f5f7f11d50a3a is
decoded as 3a0ad5117f5f3fb0. That kept reusable acceptance NO-GO at that point; the r3
correction remained unaccepted and was not inspected. The maintained
28-test text IR reader is separate from the artifact 46-PASS suite, which is
also not reusable validation. See
D:/RuneCLR-artifacts/trusted-game-entry-proof-continuation-r6-execution-audit-bocx5e-20261021/REVIEW.md
and
D:/RuneCLR-artifacts/trusted-game-entry-proof-continuation-r6-offline-repair-review-bocx5e-20261021/REVIEW.md.

The original r7 entry campaign is terminal FAILED and is not promoted: two
stock Publishers plus stageA and stageB forced-control Hosts all exited 0;
stageA validation passed before stageB launch, stageB was rejected with
EntryProbeError entry-unknown-prefix 1890, and recoverB was never launched. No
retry was released. Offline demux and reader reconstruction do not change the
campaign status. See the
r7 execution audit (archival/local evidence: `../artifacts/lead-entry-r6-offline-repair-r3-review-20261021/r7-independent-execution-audit-acceptance.json`).

Independent public-signature verification passes 36 checks: the P-256 A/B
envelopes verify over exact payload bytes, the public receipt binds A and its
staged TrustedGame.Update.dll SHA, bit flips and cross-package signatures reject,
and no private key was read. This does not prove a B Host, B receipt or
recovery. See the
signature validation (archival/local evidence: `../artifacts/lead-entry-r6-public-signature-review-20261021/VALIDATION.md`).

The module-invocation witness compile campaign is terminal FAILED, not pending:
exactly one authorized Module.A stock build ran (PID 45948, integer exit 1,
boolean timeout false; Module.B not attempted) and produced no module DLL, while
the referenced Contracts dependency compiled. Both errors are CS0118 at
ModuleInvocationWitness.cs 227:36 and 254:49, where the simple name Module binds
to the namespace instead of System.Reflection.Module. No Host run, source
correction or live edit occurred in that campaign, and the Lead verified the raw
logs and absent outputs. Report
D:/RuneCLR-artifacts/trusted-game-generic-module-witness-compile-20261021-x3yd3fe4/REPORT.md
(SHA-256 b39c4a09be1135b90b5f3c01e112ceee247ead1f3d37400920386d5beceac2f5).
The corrected artifact-only derivative changes exactly those two parameter types
to System.Reflection.Module. Its cumulative compile record is three stock build
commands: the retained failed Module.A command (PID 45948, exit 1, two CS0118
errors) plus successful Module.A and Module.B commands, A before B, with no Host
execution. This is compile-only acceptance; this corrected compile campaign
itself ran zero Hosts and has no runtime module records, and runtime MethodSpec
resolution and serialization remain unestablished for it. The separate later
stock smoke above supplies actual module phase records and static callsite
metadata, but not independently proven runtime dispatch. See the
compile acceptance (archival/local evidence: `../artifacts/lead-module-invocation-witness-review-20261021/compile-independent-acceptance.json`)
and compile release (archival/local evidence: `../artifacts/lead-module-invocation-witness-review-20261021/COMPILE-R2-RELEASE.md`).
The join reader r5 is accepted only as synthetic trusted-descriptor/profile text
validation, not an actual runtime join. Static exporter r3 and demux r4 have
separate bounded offline acceptances below; none establishes PC/image or
RuntimeFunction binding.

These additions do not alter the separate historical records: r4/r5 entry NO-GO,
F3 443-per-campaign replay, strict generic-runner 64/136, the original
6-build/4-Host deviation, and the resident two-Host stock baseline. The
first-party goal of independent trusted R2R modules plus interpreter coverage
for methods without usable bodies is unchanged. Physical devices remain skipped.

## Offline Evidence Consolidation (2026-10-21)

The accepted offline artifacts are separate from campaign execution and from one
another. The join reader r5 passes 138 tests and an independent review GO within
a trusted caller-supplied descriptor and the limited CoreLib profile; it
validates TypeDef kind/bounds syntactically, does not derive descriptor
provenance from PE, and is not an actual runtime join. See the
r5 acceptance (archival/local evidence: `../artifacts/lead-module-invocation-witness-review-20261021/join-reader-r5-independent-acceptance.json`).

The static exporter r3 passes 61 checks and 48 negatives, with 210 witness checks
and 44 independent PE-reader checks, under a scoped retained
implicit-signature/no-MethodImpl profile. This is static PE/IL evidence, not
general ECMA metadata completeness and not runtime dispatch. See the
r3 acceptance (archival/local evidence: `../artifacts/lead-module-invocation-witness-review-20261021/static-export-r3-independent-acceptance.json`).

The demux r4 passes 34 original PASS/22 negatives, 9 fix PASS/2 negatives and
93 regression PASS/73 negatives, including 89 canonical splits and three actual
reference reconstructions. Exact/canonical modes are retained-reference GO only
under an externally pinned caller-trusted manifest. Structure mode leaves
caller-selected intops unanchored and all reference flags false. See the
r4 demux acceptance (archival/local evidence: `../artifacts/lead-entry-r6-offline-repair-r3-review-20261021/r7-demux-r4-independent-acceptance.json`).
The original r7 campaign remains FAILED at entry-unknown-prefix 1890 with
recoverB absent.

The r9 recorded module/Host text correlation is accepted only as an offline
artifact result under a caller-trusted 50-input manifest: 138 synthetic, 79
recorded (71 intended negatives) and 7 manifest tests pass; 49 r9 hashes, 48
generated outputs and 50 immutable pins verify. The enabled run records six Host
records and twelve module phases at PID 28180; the off run validates identity,
business closure and resident context at PID 40020 without fabricated call
records. The original r8 bad pin is preserved, r7 is frozen unchanged, and the
original r7 campaign remains FAILED at entry-unknown-prefix 1890 with recoverB
absent. The general manifest_tool API is not accepted because beforeUnchanged is
unconditional, write_entries trusts a supplied pathKey, and
verify_relative_manifest lacks general containment. This is text-record
correlation, not runtime MethodSpec/dispatch, native/interpreter/R2R body,
PC-image, whole-method, unload, iOS/device or overall acceptance. See the
[milestone evidence summary](validation/trusted-update-milestone-20261022.md#r9-recorded-text-correlation).

## Generic Interop And Offline Verification (2026-10-21)

The [selected generic interactions](direct-interop.md#measured-on-desktop) have
stock-SDK raw evidence, Lead offline checks and independent Orca Worker review,
including a module-private value type unknown to the prebuilt Host. The current
generic-runner strict context validation passes 64 default and 136 explicit
checks, rejects 66/66 mutations, and rejects each/both missing
unloadRequested/collectionClaimed fields (3 cases); see the
Lead context checks (archival/local evidence: `../artifacts/lead-resident-stock-review-20261021/context-checks.json`).
The historical F3 retained replay (archival/local evidence: `../artifacts/lead-generics-f3-review-20261021/checks.json`)
passed 443 checks per campaign, and the earlier
portable/explicit run (archival/local evidence: `../artifacts/lead-generics-portability-20261021/command.json`)
passed 19/86 checks (including its 66 mutation rejections); those counts remain
historical and were not produced by the current strict validator. An earlier
integrated replay recorded 299 checks
per campaign; that count is also historical. Process-launch
entry points are blocked during the selftests. Observation, generic-size and
generic-interaction portable selftests are wired into local verification and
the existing three-OS CI configuration; the remote matrix has not been executed
here. The original campaign exceeded the authorized 4 builds/2 Hosts: actual
totals are 6 builds/4 Hosts. Both roots, their distinct binaries and w01's
reporting failure remain preserved. No additional product runs were used for
these offline checks.

## Generic R2R Build, Report And Map Evidence (2026-10-21)

The retained root D:/RuneCLR-artifacts/trusted-game-generics-r2r-build-20261021-x3yd3fe4
records exactly three managed builds, five independent non-composite crossgen
images and zero Host executions. New A/B module images were built after the
Host; Host/Contracts/TrustedUpdate outputs stayed frozen during the late module
builds, source inputs were unchanged, and each module pair preserves IL/R2R
MVID parity. The
Lead artifact audit (archival/local evidence: `../artifacts/lead-generic-r2r-build-review-20261021/VALIDATION.md`)
and artifact checks (archival/local evidence: `../artifacts/lead-generic-r2r-build-review-20261021/checks.json`)
pass 414 checks over command and raw-stream identities, build outputs, actual
PE MVIDs, R2R headers, maps and layout independence, with zero new products.

The parent report's five R2R section tables used an 8-byte stride and omitted
sizes. Corrected 12-byte type/RVA/size tables are accepted only in the fresh
derivative D:/RuneCLR-artifacts/trusted-game-generics-r2r-report-repair-20261021-x3yd3fe4;
the Lead reran seven parser tests and 377 repair checks, all 226 parent files
still match the preservation manifest, and no product was rerun. Useful repair
artifacts are
check_repair.py (archival/local evidence: `../artifacts/lead-generic-r2r-build-review-20261021/check_repair.py`)
and repair-checks.json (archival/local evidence: `../artifacts/lead-generic-r2r-build-review-20261021/repair-checks.json`).

The actual maps contain canonical Echo and LateRoundTrip rows only. Measure has
copied IL and no selected native row. An empty exactHostCandidates set does not
prevent a future canonical Echo witness joined to the actual T identity, PC,
PID and call id. Map absence, fixups and section tables are not interpreter
evidence. The
map supplement review (archival/local evidence: `../artifacts/lead-generic-map-supplement-review-20261021/VALIDATION.md`)
passes 31 offline checks; no deliberate root is released. These are
build/report facts only: no generic native or interpreter execution and no
same-source behavioral acceptance follows. Host execution remains zero for the
R2R build campaign.

## Constructed Generic IR Reader (2026-10-21)

eng/trusted_game_observations/generic_ir.py is a side-effect-free, text-only
reader for extracted interpreter IR and explicit complete constructed-generic
target identities. The Lead accepted 28 portable synthetic/source-shaped tests
and four former malformed-input acceptances that now reject: unbalanced
generic/array brackets, whitespace-only method names, malformed reserved
Compiled method headers and malformed reserved End of method lines. The
hardening validation (archival/local evidence: `../artifacts/lead-generic-ir-hardening-review-20261021/VALIDATION.md`)
and checks (archival/local evidence: `../artifacts/lead-generic-ir-hardening-review-20261021/checks.json`)
record zero product calls and stable source pins.

Matching retains generic arguments and complete parameter signatures exactly;
canonical and concrete type spellings are not equated. The reader requires one
nonempty End-terminated block per unique target, counts only source-shaped
opcode rows, and rejects nested/truncated/empty/duplicate selected blocks. It
does not derive assembly, token or MVID identity, parse a real dump here, or
establish executed method, native/interpreter selection or execution mode. The
reader/test wiring is now Lead-accepted in maintained local verification
and CI configuration. eng/verify.ps1 and .github/workflows/ci.yml each gained
exactly two lines invoking the 28-test suite once immediately after
generic-interaction portability, with a PowerShell exit guard and unchanged
three-OS matrix. Exact before/after bytes were verified; 60 Lead checks and
PowerShell AST (PS_PARSE_OK), YAML parsing and scoped git diff --check pass. One
measured local Windows invocation exited 0 with 28 tests, zero failures/errors
and zero products. Remote CI was not triggered; the three-OS matrix is
configured, not executed. Reader/test source hashes are unchanged. See the
integration validation (archival/local evidence: `../artifacts/lead-generic-ir-integration-review-20261021/VALIDATION.md`) and
checks (archival/local evidence: `../artifacts/lead-generic-ir-integration-review-20261021/checks.json`).

## Resident Generic Stock Compatibility (2026-10-21)

The Lead accepted a bounded resident managed compatibility observation on stock
.NET 11 RC2 Windows x64. The
validation (archival/local evidence: `../artifacts/lead-resident-stock-review-20261021/VALIDATION.md`)
records exactly two separately released fresh Host invocations, A then B (PIDs
872 and 27340, both exit 0, no timeout or retry) and zero builds, crossgens or
Publisher calls in the campaign. The campaign used a new
Host/Contracts/TrustedUpdate trio plus retained w02 A/B module images, so it is
explicitly mixed build provenance and not one same-build campaign.

Both reports record resident mode with contextIsCollectible=false,
unloadRequested=false and collectionClaimed=false. Six fixture-derived shape
outcomes and the callback-failure state pass; failure preserves ledger state and
the next call returns Closed. The Lead audit executed no products and passed 138
checks over raw streams, commands, process identities, actual PE MVIDs, pins,
shared Contracts identity and the six shape goldens. The earlier compile-only
resident build and its 22 artifact checks (archival/local evidence: `../artifacts/lead-generics-portability-20261021/resident-checks.json`)
remain historical. The retained before/after pin manifest is
`6960d5422cbb671babfe940ff7fe8e2fed16fae89f374df35c95ae09d24f099d`,
and original and copied artifacts remain byte-identical.

This is stock managed resident compatibility only. It does not establish R2R or
native execution, interpreter selection or fallback, collection/unload,
iOS/device or restricted-UGC behavior. Physical devices remain skipped. The
original unauthorized 6-build/4-Host deviation and w01 evidence remain
preserved.

## Entry Preparation Release (2026-10-21)

The old prep-r4/plan-r5 review remains historical NO-GO evidence for entry
execution. It found unsealed expected Host shared Contracts/TrustedUpdate and
Host deps/runtimeconfig identities and a misaligned plan-mutation harness; no
entry products were executed. The old review is
D:/RuneCLR-artifacts/trusted-game-entry-proof-continuation-r4-r5-review-bocx5e-20261021/REVIEW.md.

The later prep-r5/plan-r6 package passed Lead offline review: 40 input files,
82 checks, 97 retained checks and 16 aligned gate-specific mutations, covering
guarded synthetic/selftest and the actual sealed preflight only, with zero
products. The independent prep-r6 review then returned GO
(SHA-256 8e923f3f480ead0f2911ae61f866666f43696e4be251eda7c37fd0aea817016b),
and the Lead released exactly one execute invocation of the sealed r5 runner
against the existing r6 plan: two stock-SDK Publishers followed by three private
Checked forced-control Hosts, stageA multiplier 1, stageB multiplier 2, recoverB
multiplier 2. Zero builds, crossgens, retries or devices; stop at first failure.
See the Lead release (archival/local evidence: `../artifacts/lead-entry-r6-release-20261021/RELEASE.md`).
The independent review is
D:/RuneCLR-artifacts/trusted-game-entry-proof-continuation-prep-r6-review-bocx5e-20261021/REVIEW.md.

The released execution has now terminated FAILED-CLOSED. Exactly two stock-SDK
Publishers and the stageA forced-control Host ran and exited 0; stageB and
recoverB were not launched, and no retry or rerun occurred. The runner exited 1
with EntryProbeError (entry-unknown-prefix 1892). The entire raw stageA.stdout
has SHA-256 bb112fbdc5c01aca655d601484a35420dab62a2fb454faaf1e4f6e542b28b5ca;
its failing line 1892 carries the unrecognized native diagnostic fragment
"Slot 2 (local var #4 offset 64) li" immediately before an otherwise valid
ENTRYOBSERVATION. Six stageA ENTRYOBSERVATION records cover Host/Tick ordinals
1/2/3 with results 1/3/6, KindByte 6, DecodedKind Interpreter and
ObservedInterpreted true; those are entry/kind observations only and do not
establish interpretation. Host exit 0 and Host output are not attribution
acceptance, and stageA attribution remains unaccepted. The independent raw audit returns GO only for the bounded stageA observation;
the offline repair v1 actual reading passed but its reusable validator is NO-GO,
its successor r2 still fails reusable acceptance on an AssemblyRef token
byte-order bug (r3 remained unaccepted at that point), and independent public-signature
verification passes 36 checks without proving a B Host. Acceptance is false:
stageB/recoverB behavior and the expected B 2,6,12 results were not observed.
The retained control report is
D:/RuneCLR-artifacts/trusted-game-entry-proof-continuation-r6-execution-control-dw517j-20261021/REPORT.md.
A runner pass alone is not raw attribution acceptance. The subsequent raw audit
and public-signature check cover only their bounded scopes; the old
results-filename refusal and weak IR prefix/signature matching remain explicit
residuals. This run does not establish natural mixed fallback, generic-body,
whole-method, performance, unload, iOS or overall acceptance; physical devices
remain skipped.

## Generic R2R Size Observation (2026-10-21)

Orca Worker developer-5 produced five managed builds and five independent
Windows x64 crossgen images. The Lead byte audit (archival/local evidence: `../artifacts/lead-generic-size-review-20261021/VALIDATION.md`)
passes 148 checks over file hashes/sizes, deterministic gzip round trips, actual
IL/R2R MVIDs, R2R headers and selected map method nodes. Increasing this fixture
from one to eight reference types keeps raw R2R at 20480 bytes (gzip 3413 to
4560); one to eight value types grows raw R2R from 20480 to 24576 bytes (gzip
3489 to 5292). Canonical method nodes remain 50 bytes; selected exact nodes grow
from 30 to 288 bytes for the value-type pair. File alignment, callsite/metadata
differences and method-node payloads prevent a universal per-type multiplier.
This measures file composition only, without execution or interpreter evidence.
The offline replay (archival/local evidence: `../artifacts/lead-generic-size-replay-review-20261021/VALIDATION.md`)
also passes eight portable tests and an actual retained-data replay; sixteen
Lead checks reproduce the original independently audited sizes and method-node
totals without builds/crossgen or image execution.
These eight portable tests are now included in eng/verify.ps1 and the existing
three-OS CI matrix; twelve Lead entry checks and PowerShell parsing pass. Only
the local Windows test execution is recorded here.
The initial report failed after all products; offline regeneration preserved
that failure and performed no extra builds/crossgen. Compression is for
distribution and requires decompression before loading.

## Maintained Desktop Regression (2026-10-21)

The Lead reran the complete maintained `eng/verify.ps1` on Windows with stock
SDK `11.0.100-rc.2.26504.105`: exit 0, no timeout, zero build warnings/errors,
and 235 fixed preexisting source inputs unchanged. The
execution record (archival/local evidence: `../artifacts/lead-desktop-regression-20261021-06f87e58/VALIDATION.md`)
includes raw streams and 22 independent Lead checks. Runtime tests pass 140/140,
packaging 307/307, controlled-package execution 15/15 and pumped execution
22/22, trusted-update tests 272/272, typed-module lifecycle 15/15, staging
17/17 and recovery 37/37. Signature tests, startup selftests, callback closure,
signed delivery integration, the runner's six selftests and the signed real-A/B
game sample also pass. This refreshes the ordinary desktop baseline; it does
not qualify interpreter/R2R method selection or Worker-owned fixtures/tools
created after the fixed source set was captured. Generic interoperability,
generic R2R size measurement and method-entry evidence remain separate work.
Physical devices remain skipped.

## Current Engineering Focus (2026-10-20)

The current implementation moves toward a maintained, engine-independent
trusted-update example: a reusable typed module session in
`RuneCLR.TrustedUpdate`, lifecycle regressions in the normal verification
pipeline, and a game-owned contract with a host built before its update module.
The Windows stock-SDK baseline now builds with zero warnings/errors. The
[typed session](trusted-module-session.md) has 15 passing lifecycle checks,
including module/callback/exception release while the closed owner remains
alive. Independent source review found no blocking lifetime defect; its
closed/reentry/null documentation and coverage findings were addressed and
the 15-check harness rerun by the lead. The experimental wrapper's null
constructor, invalid callback and valid subsequent call are also covered by
three executed delivery-host self-test checks. The existing runtime harness
passes 139/139 and the original sample's three contexts collect. The
[trusted game sample](trusted-game.md) builds its host before the update,
checks the unchanged host, and returns 1/3/6 through the shared GameState.
Its negative delta closes before mutation; later calls, a wrong content hash,
and an unrecognized local approval are rejected. The host dependency list
contains no update module. This establishes desktop managed integration,
without qualifying native R2R or interpreter execution. Verification and
three-OS CI entries are configured; the CI matrix has not been run here.
The [same-source build driver](trusted-game-builds.md) now also passes its
Windows private-runtime functional baseline: four independent R2R derivatives
preserve their IL MVIDs, both layouts return 1/3/6, and both reject a wrong
content hash. The Lead validation (archival/local evidence: `../artifacts/lead-trusted-game-builds-20261020/VALIDATION.md`)
records actual-byte and raw-log checks and the remaining source-pin limits.
This qualifies build/layout behavior, without establishing actual method
execution mode. The signed staging/recovery sample now has a reported Windows
functional run: A stages and recovers, a tampered signed payload recovers only
authenticated A, and a validly signed B with a missing entry type fails without
same-process fallback; the next process recovers A. Lead review of the raw
streams agrees with those behaviors. The corrected script has now passed a
worker-run no-argument PowerShell 7 invocation and a separate
Lead end-to-end run (archival/local evidence: `../artifacts/lead-trusted-game-signed-20261020/VALIDATION.md`),
with all 12 selected source hashes unchanged. Portable child-shell selection
and native-architecture defaults are implemented; Linux/macOS remain unrun.
Independent Host source review is complete with no blocking defect; all 35
review pins match before, after and the actual inputs. That historical baseline
used a wrong-entry negative over A's bytes. The maintained sample now also has
an independently built real B with the same assembly identity and different
business logic. The Lead A/B run (archival/local evidence: `../artifacts/lead-trusted-game-ab-20261020/VALIDATION.md`)
passes 18 command-result checks with 14 selected source hashes unchanged: A
returns 1/3/6, B returns 2/6/12 for the same inputs, B persists and recovers in
the next process, and tampered offers preserve authenticated recovery. A wrong
Host expectation fails on B's actual result 2 and leaves the B receipt intact.
Targeted review of this A/B delta found no concrete source-level defect; all
13 review pins match the actual files without drift.
The optional signed A/B same-source driver now also has a completed Windows
private-runtime run and scoped Lead acceptance (archival/local evidence: `../artifacts/lead-signed-ab-driver-acceptance-20261020/VALIDATION.md`):
30 commands, 221 independent evidence checks and ten actual-image metadata
reads. Five separate IL/R2R pairs preserve MVID; both layouts stage real A/B,
replace the receipt with B and recover B in a fresh process. All 25 captured
source pins and copies match. The parser diagnostic-field correction is now
promoted: the maintained runner self-test passes all six checks, and offline
replay accepts six actual success rows while rejecting six contradictory
activation rows. Historical inputs and raw results remain unchanged. This establishes build/layout and signed business
behavior, without establishing actual method execution mode.
An isolated diagnostic overlay now has a
Lead method-PC audit (archival/local evidence: `../artifacts/lead-method-proof-run2-review-20261020/REVIEW-STATUS.md`):
291 checks verify 18 enabled return-PC bindings in Host/A/B target methods and
18 disabled observations in the sealed runtime image. Independent Orca Worker
review supports the selected native return-site result with 324 checks and 88
unchanged review pins. The original disabled non-image gate remains failed, and a separate
post-processing error leaves the parent exit at 1. This does not establish
interpreter fallback or promote the diagnostic overlay to the maintained sample.
The full packaging harness has completed 307/307 checks,
and the solution including the new Publisher builds with zero warnings/errors.
The maintained integration checks (archival/local evidence: `../artifacts/lead-maintained-integration-20261020/VALIDATION.md`)
record the completed package and runner checks. The signed baseline now has
both Lead functional execution and independent source review; the distinct
business-version increment has its own execution record and completed targeted
source review.
The stock sample's independent source review found no blocking
bug. It records the current hash-check/load time window and the need to accept
authenticated LastKnownGood activations in the recovery route; the local-build
approval marker is not reused as signed authorization. See the
[current sequence](next-development-plan.md#current-engineering-sequence---2026-10-20).
Physical devices remain skipped.

## Latest Mixed-Execution Handoff (2026-10-20)

A same-process Windows x64 trusted mixed observation now links a selected native
return site inside R2R GraphRules.Apply to post-invocation interpreted entries
for a plain-IL helper, with two shared-object calls returning 107/127 and one
helper compilation serving both calls. The scoped Lead acceptance (archival/local evidence: `../artifacts/lead-trusted-mixed-fallback-acceptance-20261020/ACCEPTANCE.md`)
covers that narrow raw observation. The campaign's automatic acceptance remains
false: the frozen reader expected the previous module hash, the adapter counted
post-End GC text as compiled code, and the draft PLAN's allowance marker
conflicts with the separately authorized single product; these remain traceable
process defects.

The next engineering item is to read expected module hash, size, map and related
identities from one frozen descriptor and compare them with actual bytes before
launch; also fix the End-before instruction count and keep PLAN authorization
status consistent. Do not rerun the old product to manufacture a green result.
Physical devices remain skipped.


## Published Performance Results (2026-10-19)

The [durable performance report](performance-results-20261018.md) records scoped
accepted four-platform measurements and the same-iOS R2R/IL comparison. Next is
callback-scoped time-limit work after this documentation is committed and pushed;
no callback deadline or formal execution-mode baseline is established here.

## Current Four-Platform Descriptive Status (2026-10-18)

Subsequent iOS same25-workload R2R/IL comparison now has
scoped Lead acceptance (archival/local evidence: `../artifacts/lead-ios-r2r-comparison-acceptance-20261018/ACCEPTANCE.md`):
four actual native method entries,9 completed apps,1050 formal observations
and450 warmups. Results (archival/local evidence: `../artifacts/iossim-access-r2r-comparison-bocx5e-20261018/REPORT.md`)
show workload-dependent IL/R2R median ratios7.82-204.81 on the same simulator.
Original iOS workloads were late IL without R2R bodies; default is a request
label. The new installed-composite comparison preserves input IL and runtime,
but includes composite optimization/layout/loading-path effects. Independent
downloaded R2R, per-call/all-method qualification and devices remain open.
Both this campaign and the earlier two diagnostic attempts are closed.

Four-platform descriptive warm and direct-first-use coverage is complete by
scoped Lead acceptances, including the fresh
Mac campaign (archival/local evidence: `../artifacts/lead-macos-complete-performance-acceptance-20261018/ACCEPTANCE.md`).
The source-linked consolidation (archival/local evidence: `../artifacts/four-platform-descriptive-performance-20261018/REPORT.md`)
contains exact Fraction JSON/CSV:1008 retained warm samples,105 child intervals,
6 additional Windows parent-ready windows and480 first-use functional rows.
Desktop warm has two separate requests; mobile warm and non-Windows first-use
are default-only. No cross-platform pooling, ranking or mode claims. Windows
coreclr matches Checked PDB despite its Release-named directory.

The separate25group access/collections/override-dispatch extension now has
scoped Lead acceptance (archival/local evidence: `../artifacts/lead-access-collections-acceptance-20261018/ACCEPTANCE.md`):
22 products,3150 formal samples,1350 warmups,100 untimed checks and704 original
lifecycle-gate rows across six separate request lanes. See the immutable
report (archival/local evidence: `../artifacts/access-collections-performance-bocx5e-20261018/REPORT.md`),
exact statistics (archival/local evidence: `../artifacts/access-collections-performance-bocx5e-20261018/reporting-r3/statistics.json`)
and [scope/limits](four-platform-baseline.md#accepted-access-collections-and-dispatch-extension).
The older1008 warm/105 child first-use baseline stays separate. Workload-dependent
request differences do not establish mode or cause. Mobile bridge-deps omissions,
Windows/Mac Python-seal scope, Android resolved-tool/normalized-child-stream
limits, unknown mobile app OS exits and hardware/build differences remain
explicit; they do not make accepted descriptive measurements pending again.

All quotas remain closed. Formal method-execution qualification stays open;
switches, loaded libraries and file hashes do not prove per-call mode. Devices
stay skipped. Later interpreted-UGC coarse deadline work needs execution/
enforcement prerequisites and matched OFF/ON on the same new runtime with
frozen workload/runner/checksums; it is not implemented by existing charges,
transport watchdogs or this report.

Normal append-only owned output logs are permitted, not measurement blockers;
input freezes are separate. The historical iOS9413-byte timeline append and
broad all-remote-files gate failure remain preserved, not rewritten as all-
guards-equal. Old Mac failures/recovered-snapshot gaps are not backfilled.
The final CDB reader adjudication (archival/local evidence: `../artifacts/lead-cdb-full-reader-adjudication-20261018/ADJUDICATION.md`)
accepts offline observation/regressions only. Original controller exit1/gatefalse
and unknown direct helper OS wait remain; no live CLR/interpreter witness or
launch permission follows. Earlier pending Mac/reader notes below are historical
and superseded by this current status; unrelated evidence remains unchanged.

## Product decisions

RuneCLR first makes C# usable for iOS hot-update scripting, then adds UGC
management on the same runtime foundation. Keep gameplay in C#: trusted
updateable and non-updateable modules can each have independent R2R builds. The
first-party direction is downloadable R2R updates composing with the existing
application, with interpreter support for methods without usable precompiled
bodies, direct CLR calls and shared objects.
Aim for engine-independent embedding. The [product direction](product-direction.md),
clarified on 2026-10-15, distinguishes trusted developer-owned updates from
restricted UGC. The custom-map analogy is one integration model.

- The current game examples are server-authoritative; this is not a prerequisite
  for every embedding host. Deterministic lockstep is not required.
- Hot updates initially switch at host-controlled module/session boundaries.
  Active-stack replacement and automatic live-state migration are outside scope.
- First-party iOS hot updates target downloaded R2R modules plus interpreter
  support. Current post-install IL experiments establish the interpreted path;
  downloaded R2R native execution needs separate packaging, signing/loading,
  method-entry and physical-device acceptance. Pure interpretation remains the
  current restricted UGC strategy, not the first-party product direction.
- First-party update modules are trusted game-team code and do not inherit
  UGC's interpreter-only policy. Reproducible same-source IL/R2R builds and
  independent R2R module composition remain acceptance work under #13.
- Based on the 2026-10-16 measured desktop composition result, RuneCLR does not pursue unloadable hot-update R2R: an update that must be unloaded stays interpreted, and ordinary first-party execution does not repeatedly unload old assemblies. The first-party native lane stays noncollectible and resident until process exit.
- Development is incremental. Controlled maps and ordinary mistake recovery
  precede a production hostile-code sandbox.
- Full .NET and arbitrary NuGet compatibility are not assumed.
- UGC scripts are not limited to maps. On 2026-10-12 the user requested a later
  naming review: the Warcraft map analogy should not constrain public API and
  package terminology. Existing `Map` names remain until a separate coherent
  rename; no replacement term has been selected.
- On 2026-10-16 the project owner confirmed that using UGC does not require MapContext.SpawnEntity or an entity concept. Those rules belong to the current prototype host. The framework mechanism is session loading, capability limits, execution, and unload. A host-defined API is the intended boundary. No extension point is implemented by this note, and no rename is selected.
- On 2026-10-17 the project owner set that host API to a game-owned shared CLR interface. The script calls its methods directly. SpawnEntity is not required, and calls are not dispatched by name. IMapContext stays the prototype sample and the current managed-il-gameplay-v1 allowlist. The extension point is not implemented by this note.
- Execution strategy accepted on 2026-10-12: interpret UGC map code/private
  dependencies across all target platforms first; explore UGC JIT after
  interpreter recovery and real-game evidence mature. Trusted host/framework
  native execution remains allowed. See [the decision and gates](execution-strategy.md).
- UGC authors submit source or IL; final executable packages are generated by our
  controlled server build pipeline. Even future R2R/JIT support does not permit
  direct execution of author-built runnable packages/native bodies. JIT normally
  generates machine code on the execution device from approved IL.

## Approved next sequence - 2026-10-18

The owner approved native Host/module shared-object graph composition, then a
frozen basic performance baseline on Windows, macOS, iOS simulator and Android
emulator, followed by a coarse callback deadline for untrusted interpreted UGC
and a matched performance/cutoff/recovery rerun. Physical devices stay skipped.
This updates the historical four-platform deferral of 2026-10-16.
The [four-platform baseline status](four-platform-baseline.md) consolidates
current platform gates, real Windows distributions and deadline entry conditions.
The new iOS simulator functional Lead check (archival/local evidence: `../artifacts/lead-iossim-portable-review-20261018/REVIEW.md`)
passes final32 records and1155 business-method IL comparisons without new app
starts. The original missing-deps managed1 failure and repaired managed0 remain
separate. Independent review is now terminal and
scoped functional acceptance (archival/local evidence: `../artifacts/lead-iossim-functional-acceptance-20261018/ACCEPTANCE.md`)
is complete, retaining helper/provenance limitations. No iOS timing or
execution-mode acceptance follows. Android timing and Mac functional adaptation remain their
separately assigned Orca tasks.
Mac's first portable adapter has since reported two failed functional starts;
the Lead failure review (archival/local evidence: `../artifacts/lead-macos-functional-failure-review-20261018/REVIEW.md`)
confirms dependency resolution, argument forwarding and dyld diagnostic gaps.
The fresh repair contract (archival/local evidence: `../artifacts/lead-macos-functional-repair-task-20261018/TASK.md`)
requires readiness checks before new bounded starts; neither old run passes the
Mac gate. The successful runtime build is retained separately.
The Android descriptive timing Lead review (archival/local evidence: `../artifacts/lead-android-timing-pilot-review-20261018/REVIEW.md`)
now passes the original four-start campaign and independently recomputes168
actual samples,8 pooled and24 per-PID distributions. Complete1517-file guards
remain unchanged. Independent review is now terminal and
scoped descriptive acceptance (archival/local evidence: `../artifacts/lead-android-descriptive-pilot-acceptance-20261018/ACCEPTANCE.md`)
is complete; executed mode and app OS exit remain unproven/unavailable.
The Worker checks raw/closure evidence; exact statistics are the Lead's separate
Fraction/type-7 result. No phone result follows.
The iOS descriptive timing Lead review (archival/local evidence: `../artifacts/lead-iossim-timing-pilot-review-20261018/REVIEW.md`)
also passes168 actual samples from one new four-start campaign, with849-file
guards,1155-method IL parity and exact8pooled/24per-PID statistics. Independent
timing review is terminal and
scoped descriptive acceptance (archival/local evidence: `../artifacts/lead-iossim-descriptive-pilot-acceptance-20261018/ACCEPTANCE.md`)
is complete, retaining app OS-exit/outermost-bootstrap-wait and execution-mode
limits. Mac repair records recovered
after Worker interruption contain two wait0/32-row results; the recovery task
permits finalization only, with zero remaining product slots.
The recovered Mac raw results now have terminal independent Orca review and
scoped Lead adjudication (archival/local evidence: `../artifacts/lead-macos-recovered-raw-adjudication-20261018/ADJUDICATION.md`):
99 review files,68 snapshot pins and25 ZIP entries match. This accepts the
two functional records only; full candidate reconciliation and declared
prelaunch/tool/runtime/SSH gaps remained at that checkpoint. The fresh frozen
Mac campaign now supplies separate descriptive timing acceptance.

The Windows direct first-use increment (archival/local evidence: `../artifacts/lead-windows-first-use-acceptance-20261018/ACCEPTANCE.md`)
now has scoped Lead acceptance: six exit0/watchdogfalse processes,42 child
intervals,6 separate parent-ready windows and192 functional rows. Lead verified
245 files and all48 observations/16 summaries after the independent Orca review
corrected its frequency-as-summary error in a separate artifact. The original
error, failed close, authorized reference-document drift and source-manifest
omission remain recorded. Fresh-process caches are uncontrolled; parent/child
clock domains stay separate and execution mode stays unproven.
The Android direct first-use increment (archival/local evidence: `../artifacts/lead-android-first-use-acceptance-20261018/r2/ACCEPTANCE.md`)
now also has scoped acceptance after terminal independent Orca review. All1426
files,21 direct intervals,96 functional rows and seven exact three-observation
summaries match. The three fresh apps report managed return0/native HRESULT0
with ADB direct wait0/watchdogfalse; app OS exit remains unknown. Cache state
is uncontrolled and no parent startup window was measured. Its three-app budget
is exhausted. The iOS simulator direct first-use increment (archival/local evidence: `../artifacts/lead-iossim-first-use-acceptance-20261018/r1/ACCEPTANCE.md`)
now has scoped acceptance after terminal independent Orca review: three apps,
21 direct intervals,96 original functional rows and seven exact summaries agree.
All831 candidate and760 preparation files remain unchanged locally. The original
remote timeline appended9413 bytes while retaining its35981-byte prefix; the
historical broad remote-immutability gate failed and remains preserved. Normal
append-only output is allowed, not a measurement blocker; frozen measurement
inputs are separate and unchanged. simctl wait0,
managed/native zero markers and unknown app OS exit remain distinct. Its three
slots are exhausted, with no retry or replacement. Mode stays unproven and caches
uncontrolled. Mac now also has21 scoped-accepted first-use intervals; formal
execution-mode-qualified four-platform baseline remains open.

The Windows interpreter-entry preflight stopped before any author/debugger
process: the actual accepted coreclr.dll matches the Checked PDB, not the
proposed Release PDB. The independent Lead check (archival/local evidence: `../artifacts/lead-windows-interpreter-preflight-review-20261018/REVIEW.md`)
rehashes1886 inputs and verifies37 delivery files. A Release-named testhost
directory is not native build provenance; existing byte-pinned timings remain
descriptive, with execution mode unproven. Native type-layout validation against
the matching Checked PDB is required before a separately authorized capture.
That subsequent single-process capture has now failed to load its breakpoint
command file. The Lead failure adjudication (archival/local evidence: `../artifacts/lead-windows-checked-entry-failure-review-20261018/REVIEW.md`)
confirms138 files, raw2 and no complete entry chain; old1/1 author budget is
exhausted. Native protocol controls and a separate future dispatch are required,
without changing old mode labels. Android first-use implementation transferred
to the existing Android adapter author after cc's zero-product preparation;
the terminal total is cc0+boc3=3/3, with no extra smoke or retry.
The native CDB control task subsequently used all four slots without proving
breakpoint-origin capture and natural helper exit. Lead's
correction adjudication (archival/local evidence: `../artifacts/lead-cdb-protocol-correction-adjudication-20261018/ADJUDICATION.md`)
accepts the Orca Worker's corrected account, retaining the original false-positive
claims and streams. The observed native boundary hit is insufficient: capture
commands ran at the loader initial break and q ended debugging at the boundary.
Next prepare a native-only script/controller and offline predicate that reject
that transcript; Lead static review precedes any new bounded launch. No author
retry or execution-mode upgrade is accepted.
The prepared replacement then received a single native-only trial. Lead's
passive trial review (archival/local evidence: `../artifacts/lead-cdb-native-trial-review-20261018/REVIEW.md`)
verifies42 trial and806 preparation files, preserving the launched reader's
path/exit-format rejection. The original raw supports post-hit register/read
capture, result43 and debugger last-event exit0, subject to independent offline
schema review. The observation adjudication (archival/local evidence: `../artifacts/lead-cdb-native-observation-adjudication-20261018/ADJUDICATION.md`)
now accepts that literal native sequence after terminal independent Orca review,
but excludes its unimplemented mutation-control claims. Complete schema-aware
reader regression coverage remains open; original failed gate and unknown direct
helper OS wait remain unchanged. No extra helper or CLR author launch follows. The
iOS simulator first-use preparation (archival/local evidence: `../artifacts/lead-iossim-first-use-preparation-20261018/TASK.md`)
defined the compiled adapter and offline gates. A separate bounded campaign
followed Lead readiness review; its scoped descriptive acceptance and explicit
timeline deviation are recorded above, without reopening its exhausted slots.
Lead's decoder regression review (archival/local evidence: `../artifacts/lead-cdb-observed-reader-review-20261018/r2/REVIEW.md`)
has since reproduced seven false accepts with equal-length mutations and
relinked hashes. The new decoder remains rejected; repair must retain the
prepared reader's anchored prompt/output, PE/file/freeze and strict record
checks while adapting only the observed path/exit formats.
The repair2 regression review (archival/local evidence: `../artifacts/lead-cdb-reader-repair2-review-20261018/REVIEW.md`)
confirms that the original seven counterexamples now reject, but ten additional
relinked record/event mutations still falsely accept. The reduced repair omits
full frozen-file/environment/controller/clock/launch-link checks and event order.
Reader acceptance remained rejected at that checkpoint. The subsequent final
full-reader adjudication accepts offline observation only, without additional
debugger/helper/author products or live mode witness.

Existing Orca Workers have received the native graph implementation and
performance preparation tasks. After the original graph Worker's model-service
capacity failure (503 account_candidate_capacity), Lead transferred implementation
to the existing native specialist under a distinct artifact directory; the
transfer contract (archival/local evidence: `../artifacts/lead-native-graph-transfer-20261018hj/TRANSFER.md`)
preserves the total product-start limit and requires residual-process checks.
The failed dispatch is not a product/build failure or a delivered capability.
Preparation runs alongside composition; actual
performance measurements follow graph review and example freeze. The deadline
is not implemented by existing instruction budgets or HTTP transport timeouts.
Trusted code remains unlimited. Lead retains scoped acceptance; independent
review follows delivery. See the [current sequence](trusted-embedding-next.md#approved-sequence-2026-10-18)
and stage acceptance gates (archival/local evidence: `../artifacts/lead-approved-stage-gates-20261018hg/GATES.md`).

Stage 1 now has scoped Lead acceptance (archival/local evidence: `../artifacts/lead-native-graph-acceptance-20261018hv/ACCEPTANCE.md`)
after the terminal independent Orca Worker review. Four original Windows x64
product runs preserve the signed shared-object graph semantics; seven observed
Apply/Seen return sites bind to the exact independently compiled R2R files and
method intervals. This is resident instrumented callsite evidence, without
whole-method, Func-native, interpreter fallback, unloading or mobile claims.
The disabled lane is not interpreter proof; no extra graph product was started.

The minimal semantic example (archival/local evidence: `../artifacts/lead-performance-example-freeze-20261018hw/FREEZE.md`)
fixes workload parameters and independent expected values. The next implementation
is the portable functional harness (archival/local evidence: `../artifacts/lead-portable-baseline-harness-task-20261018hx/TASK.md`),
with separate platform runtime prerequisites (archival/local evidence: `../artifacts/lead-platform-mode-prerequisites-task-20261018hy/TASK.md`).
Its implemented sources/adapters need functional review and a final timing-source
freeze before any new baseline. Current read-only tool metadata confirms Mac
ARM64/Xcode27/iOS simulator SDK27 and local Android tooling; it does not establish
compatible private execution modes. No new baseline or deadline is implemented.

The exact Mac cache query (archival/local evidence: `../artifacts/lead-exact-mac-runtime-cache-20261018id/README.md`)
now confirms that the retained mobile-batch iOS simulator Release CoreCLR,
IL CoreLib and ARM64 Crossgen2 still exist with their recorded hashes. The
preceding prerequisite report's unknown cache status is superseded for those
three files only. A newly packaged harness and its invocation/mode evidence
remain outstanding; desktop Mac runtime selection is a separate prerequisite.

The portable harness functional delivery (archival/local evidence: `../artifacts/portable-baseline-harness-bocx5e-20261018/README.md`)
now has a final Windows stock-runtime run with five workload checks and real
collectible session/resource controls. The Lead review (archival/local evidence: `../artifacts/lead-portable-harness-review-20261018ih/REVIEW.md`)
verified its 32 raw records, 40 frozen inputs and 908 compiler closure files.
No new performance sample was taken. Five offline helper misacceptances
(role, timing scopes and chronology) prevent timing freeze; the
repair task (archival/local evidence: `../artifacts/lead-portable-harness-repair-task-20261018ii/TASK.md`)
also adds the reusable public managed entry needed by platform bridges.
Mac private-runtime preparation proceeds separately. Four-platform packaging,
execution-mode evidence, baseline timing and deadline work remain outstanding.

The independent JSONL statistics adapter (archival/local evidence: `../artifacts/lead-portable-statistics-adapter-20261018ij/README.md`)
now checks the implemented event format with eight workload groups, separate
process config identities, exact clock conversion and retained distributions.
Its 23 rejection controls and synthetic schedule pass; the actual 32-row
functional stream correctly fails timing eligibility. These are verification
results only: no new performance sample or execution-mode acceptance follows.

The mobile adapter reuse check (archival/local evidence: `../artifacts/lead-mobile-adapter-reuse-review-20261018ik/REVIEW.md`)
also verifies the newer retained Android batch APK against its exact 199-file
layout and 198 application inputs, including 11 x86_64 native libraries. The
old bridge's budget/matrix settings require replacement; iOS needs a fresh
composite for the new trusted assembly closure. These provide concrete build
inputs, without a new package, simulator run or mobile execution-mode claim.

The portable repair Lead review (archival/local evidence: `../artifacts/lead-portable-repair-review-20261018il/REVIEW.md`)
now accepts the public-entry/helper repair within its stock Windows functional
scope. Five original misacceptances reject independently; the new image has its
own 32-row run and unchanged workload bodies. The
Windows private adapter task (archival/local evidence: `../artifacts/lead-windows-private-harness-task-20261018im/TASK.md`)
is the next implementation step: actual private-runtime functionality, loaded
identity and carefully separated method-entry diagnostics. It authorizes no
timing and does not infer interpreter execution from a switch or prepared entry.

Mac private-runtime attempt1 failed before native compilation because pkg-config
was unavailable. The independent failure review (archival/local evidence: `../artifacts/lead-mac-build-failure-review-20261018in/REVIEW.md`)
retains the complete log and confirms that no usable native runtime resulted.
The diagnosed retry task (archival/local evidence: `../artifacts/lead-macos-toolchain-retry-task-20261018io/TASK.md`)
allows prerequisite tools only in a new private experiment prefix, with full
preflight before the one remaining runtime-build attempt. It changes no system
installation and does not advance benchmark or mobile acceptance.

The Windows private adapter Lead review (archival/local evidence: `../artifacts/lead-windows-private-adapter-review-20261018ip/REVIEW.md`)
now accepts its two untimed functional lanes within their Windows x64 scope.
Both retain32 raw rows and exact private framework identities; selective-author
also observes loaded clrinterpreter and37 installed interpreter precodes. These
are installed-entry diagnostics, without per-call interpretation or performance
eligibility. Lead's zero-product replay passes30 controls and preserves all
candidate inputs. The Android portable adapter contract (archival/local evidence: `../artifacts/lead-android-portable-adapter-task-20261018iq/TASK.md`)
advances to a fresh emulator app and bounded functional run using the reviewed
public entry and exact retained mobile runtime. Mac build2 remains separate;
actual four-platform timings and deadline implementation are still pending.

Mac build2 also failed before native compilation: the isolated tools now work,
but OpenSSL pkg-config metadata is unavailable. The
Lead failure review (archival/local evidence: `../artifacts/lead-mac-openssl-failure-review-20261018ir/REVIEW.md`)
retains its full125096-byte log and original recorder files; command SHA links
and exclusive creation were missing, so the failure is not upgraded to full
launch-provenance acceptance. The
OpenSSL recovery contract (archival/local evidence: `../artifacts/lead-mac-openssl-recovery-task-20261018is/TASK.md`)
explicitly extends the exhausted two-build limit by one diagnosed attempt only
after real private OpenSSL/ICU compiler/linker/CMake preflight. Source and system
installations stay unchanged; no usable Mac runtime or timing result yet.

The Android adapter Lead review (archival/local evidence: `../artifacts/lead-android-portable-review-20261018it/REVIEW.md`)
now checks the new app's one successful emulator run,32 original functional
rows,19 reader cases and full package/transport closure. The managed return0,
native hosting HRESULTs0 and ADB transport0 stay distinct; CoreCLR/JIT maps do
not prove interpretation. No new Android timing was taken. The
Windows timing pilot contract (archival/local evidence: `../artifacts/lead-windows-timing-pilot-task-20261018iu/TASK.md`)
now authorizes a frozen minimal measurement wrapper, one untimed gate and
three real measured processes per request configuration. These will be
descriptive default/selective-request timings under unproven-selection, not
formal interpreter/native or four-platform baseline acceptance. Deadline
implementation still follows the formal no-deadline baseline.

Mac attempt3 passed private OpenSSL checks but failed ICU header discovery.
The Lead reproduction (archival/local evidence: `../artifacts/lead-mac-icu-discovery-review-20261018iv/REVIEW.md`)
isolates a CMAKE_PREFIX_PATH environment separator defect: semicolon cannot
find the existing header; colon resolves it with the same CMake expression.
The environment repair contract (archival/local evidence: `../artifacts/lead-mac-cmake-environment-repair-task-20261018iw/TASK.md`)
authorizes one further unchanged-source build after that discovery check,
with corrected full-command-file hash links. Three failures remain preserved;
the private runtime and formal Mac baseline are not established yet.

The Windows real pilot Lead review (archival/local evidence: `../artifacts/lead-windows-timing-pilot-review-20261018ix/REVIEW.md`)
now independently verifies336 actual samples from six measured processes plus
the untimed gate. Exact rational distributions agree for16 request/workload
groups and48 per-process groups, without new launches. Numeric pooled medians
are3.3194ms default and28.7403ms selective-author; the faster selective session
groups remain request observations without mode attribution. The
independent Orca review (archival/local evidence: `../artifacts/lead-timing-pilot-independent-review-task-20261018iy/TASK.md`)
is the next review task after cc's current Mac build. The
iOS simulator adapter contract (archival/local evidence: `../artifacts/lead-iossim-portable-adapter-task-20261018iz/TASK.md`)
advances a fresh app/composite and bounded functional run using existing cached
mobile outputs. Formal four-platform execution baseline and deadline remain pending.

Mac attempt4 now has a successful original build and scoped
Lead output review (archival/local evidence: `../artifacts/lead-mac-attempt4-runtime-review-20261018/REVIEW.md`):
actual child96624 exit0,565006-byte original stdout,13 layout files and four
matching core/framework hashes. ARM64 runtime/interpreter/muxer outputs exist.
The recorder rewrote command.json before launch and lacks complete inherited
environment/tool guards; strict launch-provenance acceptance remains false.
The Mac portable functional contract (archival/local evidence: `../artifacts/lead-macos-portable-functional-task-20261018/TASK.md`)
requires a fresh complete freeze and two bounded untimed lanes after cc's
independent Windows review. No runtime rebuild or historical-record repair.

The independent Windows timing review is now terminal. Lead
accepts the descriptive pilot scope (archival/local evidence: `../artifacts/lead-windows-descriptive-pilot-acceptance-20261018/ACCEPTANCE.md`)
after rehashing the435-file delivery and reconciling raw counts. Each measured
PID has80 intervals including24 warmups and56 actual samples;336 actual samples
total. The48 CSV rows are eight workload summaries per PID across six PIDs.
The independent report's65 timed-row figure excludes15 callback warmup-kind
rows and is retained with this explicit correction. No executed-mode or formal
four-platform baseline acceptance follows. Mac adapter work follows its own
functional contract; deadline implementation still follows the complete baseline.

The Android descriptive timing contract (archival/local evidence: `../artifacts/lead-android-portable-timing-task-20261018/TASK.md`)
now defines the next implementation after boc's iOS functional task terminates.
Static readiness checks all1851 original Android manifest files and unchanged
portable Host/schedule. The existing bridge is check-only; the new adapter must
freeze before its one untimed gate plus three fresh default-request measured
processes. Target168 actual samples, not yet measured. This is a separate
four-start allowance; no old successful task is rerun or given a repair slot.
Execution-mode/formal four-platform acceptance remains pending.

Lead also extracted first-use diagnostic event windows (archival/local evidence: `../artifacts/lead-windows-first-use-event-windows-20261018/REPORT.md`)
from the six existing Windows measurement streams. They retain exact child-clock
ticks but include event reporting; they are not new samples, pure callback or
cold-start measurements. The later scoped Windows first-use acceptance above
uses dedicated direct timers with deferred reporting and a separate freeze.
Other-platform first-use coverage remains open. Do not use
event-marker differences to select deadline thresholds or rerun the closed pilot.

## Host integration status - 2026-10-17

The [score-game example](score-game.md) uses a game-owned
`ScoreGame.Contracts` assembly, without gameplay methods in RuneCLR's shared
abstractions. The desktop source-to-package-to-session run produced scores 3
and 30, recovered after a failing callback, and collected all four contexts.
The lead's independent packaging rerun passed 307/307, preserving the original
gameplay contract checks. The lead also independently reran the score example.
Passing this package to MapPackage now rejects it before loading and directs
the caller to HostContractSession. The packaging receipt is recorded in
`artifacts/lead-packaging-review.log`.
This is stock desktop managed-IL evidence; required interpretation and native
budgets are not integrated into this host-contract session path.

The [trusted startup boundary](trusted-update-startup-lifetime.md) now occupies
the process before loading or calling a host activator. Activation failure,
reentry and concurrent activation cannot select another version in that
process. Planning rejections still permit last-known-good fallback. The focused
desktop selector suite passed 272/272 in the lead's independent rerun.

The optional [signed release helper](trusted-release-signing.md) verifies a
complete listed payload and activation metadata using a host-pinned P-256 key.
The lead's desktop rerun passed signature, tamper, directory-junction and curve
checks. Existing local approval records do not acquire signatures automatically.
The sample's `--signed-start` now passes the verified candidate and approval
unchanged into the startup selector and executes a standalone IL entry. The
lead independently ran `--signed-self-test` and the existing `--self-test`,
both with exit code 0. The signed checks cover successful activation, oversized
metadata/key rejection, wrong keys, metadata/private-file tampering, activation
failure without changing last-known-good, and a good start in the next process.
Additional payload files are authenticated, but this fixture does not execute
private dependencies. Both sample checks run in local verification and CI.
The [stream-based staging helper](trusted-release-staging.md) now verifies the
complete copied inventory before one directory move. It returns final-rooted
paths, never overwrites an existing destination, and cleans only its own stage
on failure. The worker's run and lead's isolated rerun each passed 17/17 desktop
tests, including cancellation, source-list mutation, stream failures and an
incomplete copy that remains invisible at the final path. It is included in
the solution, local verification and three-platform CI. The
[local delivery sample](trusted-update-delivery-sample.md) joins it to signed
startup. The final Release solution build completed with zero warnings/errors.
The lead reran runtime tests (140/140, including the late-built map), selector
tests (272/272), signature tests, staging tests (17/17), and all three trusted
host self-tests successfully. The staged self-test includes an authenticated
`TrustedUpdate.Helper..bin` and actual entry execution after publication.
Both ordinary and pumped sample-host runs collected every context. The earlier
307/307 packaging result covers the unchanged packaging source. Final logs are
`artifacts/lead-final-build.log`, `artifacts/lead-final-runtime.log`, and
`artifacts/lead-final-trusted.log`. These are Windows desktop JIT/IL receipts.
Network transport, rollback policy across restarts, and physical iOS delivery
acceptance remain separate work. On macOS arm64 the worker and lead each ran
the signed-release suite successfully with the existing private .NET SDK
11.0.100-preview.6.26359.118. All seven source hashes match the accepted Windows
snapshot. Both directory-symlink rejection cases ran and passed; secp256k1 was
unavailable and skipped. A separate Orca Worker then ran the accepted staging
suite (17/17) and all three trusted-host self-tests on macOS arm64, including
`dotted-helper`, with no skips or failures. The lead checked all 12 source
hashes against the accepted snapshot and current files, the archive hash, all
six command exit codes, and the output markers. Receipts are
`artifacts/lead-macos-delivery-receipt.json` and
`artifacts/lead-macos-delivery-run.log`. This snapshot excludes the in-progress
signed-recovery helper. Linux and the remaining macOS integration suites remain
unverified here. These macOS receipts are desktop managed-IL evidence.

On 2026-10-18 the [signed recovery helper](trusted-release-recovery.md) passed
37/37 in the lead's isolated Windows snapshot. Both original directory-alias
probes now reject before activation, with zero calls and no receipt created.
The receipt stores the original signed document and a relative release path;
every restore verifies the pinned key, complete payload and target again. It
does not use the selector's unsigned legacy last-known-good file. Activation
failure locks the process; successful activation with a failed receipt write
remains successful and reports persistence failure separately.

The lead independently built and ran the [recovery startup sample](trusted-update-recovery-sample.md)
(15/15) and [staged recovery sample](trusted-update-staged-recovery-sample.md)
(9/9), plus all three previous trusted-host self-tests, with no skips. These
checks include receipt-file symlink rejection, real IL entry execution, a
failed offer restoring the old signed release, no fallback after activation
failure, and automatic recovery in the next process without republishing it.
The final directory stays intact after a committed stage, including a failed
activation. Build output has zero warnings/errors. The logs are
`artifacts/lead-recovery-crossplatform-final-host-build.log` and
`artifacts/lead-recovery-crossplatform-final-*-self-test.log`. Recovery and staged recovery
are included in local verification and three-platform CI. Additional files are
authenticated, not executed as dependencies in these standalone-IL fixtures.

The Orca Worker's macOS arm64 rerun passed 37/37 under each of `/var/folders/.../T/`,
`/tmp/` and `/private/tmp/`. All five host self-tests also passed under each
prefix, including both receipt-leaf-link checks, without skips. Both Release
builds had zero warnings/errors, using the existing private SDK
11.0.100-preview.6.26359.118 and direct arm64 apphosts. The lead checked the
archive hash, all 15 source bindings, all 18 test outputs and reported exit
codes against the accepted snapshot. Evidence is
`artifacts/lead-macos-recovery-final-receipt.json` and
`artifacts/lead-macos-recovery-final-run.log`; the snapshot pointer is
`artifacts/lead-recovery-crossplatform-final-snapshot-path.txt`.
The original 30/35 diagnostic failure under system temp aliases remains in
`artifacts/lead-macos-recovery-receipt.json`. The fix preserves leaf-link
rejection and uses canonical containment for `receipt-root`.
These are Windows/macOS desktop JIT/IL results. Linux, network transport,
rollback policy and physical iOS delivery remain separate acceptance work.

The lead then ran `./eng/verify.ps1` on Windows for the integrated recovery
snapshot; it exited 0 on 2026-10-18. This covers the Release solution build,
late-built map, runtime 140/140, packaging 307/307, package execution 15/15 and
22/22, selector 272/272, signature checks, staging 17/17, recovery 37/37, the
plan/source parity checks, all five trusted-host self-tests, both collection
samples and the ScoreGame failure/recovery run. Logs are
`artifacts/lead-recovery-full-verify.log` and
`artifacts/lead-recovery-full-verify-receipt.json`. The signed composition
adapter for actual private-dependency execution is a separate Orca Worker
assignment and is not included in this acceptance.

The same accepted recovery test binaries also passed 37/37 with the pinned
private Windows x64 Checked .NET 12 runtime, using mode 1 and R2R enabled.
The lead rechecked all four runtime/framework hashes and the accepted source
bindings before and after the run. A separate short-SPKI call returned the
expected rejection without activation and emitted successful interpreter IR
for `TrustedReleaseRecovery.TryStart`. This is library compatibility plus
that early-rejection entry observation; it does not establish signed native
module execution. The receipt is
`artifacts/lead-recovery-private-runtime-receipt.json`, with raw logs under the
directory in `artifacts/lead-recovery-private-runtime-path.txt`.

The [signed composition delivery driver](trusted-composition-delivery-native.md)
is an opt-in Windows x64 experiment under development, separate from the
accepted recovery suites. The lead built a frozen copy of its signing harness
with zero warnings/errors and used it to sign an existing independent R2R
update/private pair and an IL-only helper. Verification retained both additional
files; changing the private DLL was rejected with `ContentMismatch`. This
preflight launched no update host and proves no native execution. Its receipt
is `artifacts/lead-delivery-signing-preflight-receipt.json`.

The first full driver attempt stopped at `host-build-blocked`: the host project
had not compiled the shared Windows entry observer. Preserve
`artifacts/trusted-composition-delivery-20261018-native/result.json` as failed
evidence. The lead's review also found that receipt hashes were sampled only
after every child finished, so they could not establish persistence behavior
at each process boundary. Per-step snapshots, complete frozen observer inputs,
authenticated final load paths and the full shared-object result checks must
be verified before accepting either native lane. Review evidence is
`artifacts/lead-delivery-native-driver-review.json`. The Orca Workers own the
host and driver corrections; this first attempt establishes no native execution.

After the observer link and self-test call sites were corrected, the lead
built a new 25-file frozen host snapshot with zero warnings/errors. Its direct
apphost self-test passed 11/11 on the stock Windows desktop runtime. Eight
successful activations produced the expected private/helper values (A:
101/310, B: 202/613), shared object identity, callback/delegate/generic results,
fresh counters and loaded paths matching the authenticated candidate paths.
The checks also exercised recovery without republishing, destination collision
without source-B activation, an unlisted helper planted before first activation,
and author failure followed by process-lock rejection and next-process recovery.
Four malformed CLI requests returned the owned argument diagnostic and exit 2.
Evidence is `artifacts/lead-signed-dependency-execution-receipt.json`, with the
source/log directory in `artifacts/lead-signed-dependency-execution-path.txt`.
The host Orca Worker subsequently delivered its implementation and reported the
same 11 passing checks. This is a measured managed-IL snapshot. Resolver review
and signed native R2R execution remain pending.
The independent Orca Worker review then reproduced two resolver defects: an
unlisted application DLL in TPA could load from the host directory, and two
listed assemblies with the same simple name silently selected the last path.
The ordinary adjacent unlisted-helper rejection still holds, but does not cover
these cases. Preserve `artifacts/lead-delivery-host-review-probe-output.txt` and
`artifacts/lead-delivery-host-review-snapshot/review-note.json`.
The host Orca Worker fixed both cases: framework fallback now checks exact
assembly identities and actual corelib-directory TPA paths, and the signed
inventory rejects duplicate simple names or unreadable assembly identities
before loading author assemblies. These inventory failures occur after
activator entry, keep the process locked and leave the receipt unchanged.
The lead independently built a new 29-file frozen snapshot with zero
warnings/errors; its direct Windows stock-runtime apphost passed 16/16 checks,
including a real unlisted application dependency in TPA that did not execute.
Evidence is `artifacts/lead-delivery-resolver-fix-receipt.json`, with the frozen
source/log directory in `artifacts/lead-delivery-resolver-fix-path.txt`.
The independent Orca Worker then bound its v2 probe to that frozen real host
assembly. The lead reran it: the fixed DLL returned exit 0 / FAILURES 0, while
the old DLL returned the expected exit 1 / FAILURES 3. The probe verifies
unlisted real-TPA application rejection, exact Contract sharing, framework
availability and explicit duplicate-inventory rejection before author ALC
creation. Evidence is `artifacts/lead-delivery-host-bound-regression-v2`;
lead rerun logs are in the directory named by
`artifacts/lead-delivery-parser-review-path.txt`. macOS built the same 29
sources with zero warnings/errors: the physical `/private/tmp` run passed
16/16, but `/tmp` returned exit 1 with 6 passes and 10 failures. Those checks
compared lexical `/tmp` expectations with actual `/private/tmp` loaded paths;
the reported business values were correct. Preserve
`artifacts/lead-delivery-resolver-fix-macos-receipt.json` and its run log.
The host Orca Worker then corrected only SelfTest path identity checks, with
bounded component-wise link resolution, exact final-file matching and sibling
prefix rejection. Its new 29-source archive passes 17/17 on macOS under both
`/tmp` and `/private/tmp`, with empty stderr and no skips. The lead checked
archive/receipt/raw-log hashes, rebuilt that archive on Windows and passed
17/17 through its direct apphost. Production DeliverySession is unchanged.
Evidence is `artifacts/lead-delivery-path-alias-macos-receipt.json` and
`artifacts/lead-path-alias-acceptance-receipt.json`. Windows signed native R2R
delivery was separately accepted in the two-lane run recorded below.

The earlier 25-file frozen host also passed all 11 checks on the pinned private Windows
x64 Checked runtime with mode 1 and R2R enabled. Nine actual helper invocations,
including the author-failure case, supplied interpreter precode type 6 and
successful `IlOnlyHelper.Compute` IR output; each observation path matched the
loaded helper from the signed candidate. The four runtime/build hashes and all
25 source hashes matched before and after. Evidence is
`artifacts/lead-signed-dependency-private-runtime-receipt.json`. Native diagnostics
preceded every `ENTRYOBSERVATION` marker on the same line, so an anchored
line parser found zero of these nine records; retain the raw stdout and parse
the marker plus JSON. This establishes compatibility and the observed helper
entries, not native execution of signed R2R updates or complete interpretation
coverage.

The fixed 29-file resolver snapshot subsequently passed all 16 self-tests on
that same pinned private Checked runtime, with mode 1 and R2R enabled. Eleven
actual helper invocations supplied `Interpreted=true`, precode 6, matching
loaded-helper paths and eleven successful Compute IR dumps. Source and runtime
hashes matched before and after; stderr was empty. One PASS marker also had a
native diagnostic prefix, so acceptance checks each expected full test label
rather than assuming a line begins with PASS. Evidence is
`artifacts/lead-delivery-fixed-private-runtime-receipt.json`; raw output and the
initial anchored-count assessment remain in the frozen snapshot directory.
This validates the repaired loader with the private runtime and observed helper
entries. The later signed native R2R delivery acceptance is recorded below.
The lead also independently crossgen'd that fixed host with 198 references,
including the new `DeliveryAppDep` application dependency. Compilation exited
0; the exact `TrustedComposition_DeliveryHost_DeliveryHostObject__Touch` map
body starts at RVA 31664, inside both an executable section and an AMD64
RuntimeFunction. Input/reference hashes remained unchanged. Evidence is
`artifacts/lead-fixed-host-crossgen-receipt.json`. This is compilation and
method-map evidence only; no live return PC or signed update activation was
measured in that preflight.

The driver Orca Worker subsequently completed the Windows x64 signed R2R
delivery experiment at
`artifacts/trusted-composition-delivery-20261018-rerun4`: both lanes passed.
The lead checked all 35 frozen source hashes, independently audited the raw
ten-process outputs, and reran the frozen driver into a fresh directory. That
rerun exited 0, printed `proven` and had empty stderr; its independent audit
also passed. The directory is named by
`artifacts/lead-signed-native-acceptance-path.txt`; the audit receipts are
`artifacts/lead-signed-native-worker-audit.json` and
`artifacts/lead-signed-native-acceptance-audit.json`.

Host, Contract, Update A/B and Private A/B were independently crossgen'd; the
helper remained IL. Each lane stages A, recovers A in a new process, activates
an intentionally failing B, recovers A again, then stages B successfully.
With ReadyToRun enabled, each of the five steps supplies actual return PCs for
the exact host Touch, update Execute and private Read methods, bound to final
image paths/SHA, executable sections, RuntimeFunctions and method maps. With
ReadyToRun disabled, those matches disappear using the same payload bytes.
Each process also supplies a real helper invocation, precode 6,
`Interpreted=true` and successful Compute IR. Business values, shared-object
identity, callbacks/delegates/generics, fresh counters and loaded final paths
match; author failure preserves A's receipt and retains B's committed final.
The next process restores A without republishing it. This accepts the scoped
Windows desktop signed local-file R2R delivery path. iOS packaging/signing/
loading and device execution, network transport, anti-rollback and native
unloading are not established by it.

The verification Orca Worker added the desktop delivery host and all required
fixture projects to the solution, then wired its no-build self-test into
`eng/verify.ps1` and the existing three-OS CI matrix. Explicit fixture solution
entries preserve Release output selection; Private A/B remain in separate
directories. The lead rebuilt the solution and ran the exact wired command:
both exited 0, with 17 passing self-tests and empty stderr. Changed input
hashes remained stable during verification. Evidence is
`artifacts/lead-delivery-wiring-acceptance-receipt.json`. This validates the
Windows command, not an unperformed Ubuntu/macOS CI run. The native driver
remains opt-in.

The lead subsequently ran the integrated Windows verification. The first run
passed the Release build, runtime 140/140 and packaging 307/307, then exited 1
because access to the fixture staging directory was denied. Without product
changes, the remaining verification commands passed using a fresh isolated
fixture output: package execution 15/15 and 22/22, selector 272/272, signatures,
staging 17/17, recovery 37/37, parity/host-callback checks, the five old host
self-tests, delivery host 17/17, both collection samples and ScoreGame.
The tracked verification inputs remained identical. This is combined coverage
across two runs, not an uninterrupted successful `verify.ps1` run. The initial
failure is preserved alongside `tail-retry/receipt.json` and
`combined-receipt.json` in the directory named by
`artifacts/lead-delivery-integrated-verification-path.txt`.

The follow-up fixture diagnosis located a reproduced `IOException`
(`0x80070005`) at the outer `Directory.Move`; cleanup succeeded in that run.
The responsible external condition remains unknown. The fixture tool now
retries that move at most five times after the first attempt, 50 ms apart,
and preserves a primary failure if cleanup also fails. The Orca Worker's
synthetic diagnostics cover transient failure, six exhausted attempts and a
secondary cleanup failure. The lead's real-tool rerun generated 12 packages
with exit 0 and empty stderr, then rejected the existing output with exit 2
and its receipt unchanged; no staging directory remained. Evidence is
`artifacts/lead-fixture-staging-hardening-acceptance-2ef6b6d232874ad0933edf7233470b80/receipt.json`.
This focused check does not establish the original external cause or replace
the failed integrated run with a successful uninterrupted one.

After that hardening, a new uninterrupted Windows run of
`eng/verify.ps1` exited 0. The lead checked all 467 input hashes and the suite
summaries: runtime 140/140, packaging 307/307, package execution 15/15 and
22/22, selector 272/272, staging 17/17, recovery 37/37, all host self-tests,
collection samples and ScoreGame. The delivery self-test passed 17/17. Evidence
is `artifacts/lead-post-hardening-full-verify-unbounded-626a93ce533844368543fd1e17eddc93/receipt.json`;
the raw-log audit is `artifacts/lead-typed-evidence-audit-20261018f/full-verify-audit.json`.
The earlier failed run and launcher-timeout run remain separate records. This
active-tree verification excludes the isolated signed typed-session changes.

The portable `--probe` now constructs synthetic protocol vectors
without historical artifacts or a private runtime. The lead copied only the
driver into a fresh source tree and reproduced exit 0, `probe passed`, and empty
stderr. `--probe-log` explicitly opts into existing stdout replay. The helper
proof and native execution functions are unchanged from the accepted driver;
only the probe and its CLI routing changed. Evidence is named by
`artifacts/lead-portable-probe-acceptance-path.txt`. This is parser and timeline
validation, not an additional native execution receipt.

The [typed-session ownership brief](trusted-embedding-next.md) also has a small
Orca Worker prototype outside the product libraries. The lead froze its five
source/design files, built it and ran its executable: six checks passed with
empty stderr. It borrows a synchronous typed callback, rejects reentry, supports
idempotent close and closes on author failure. A retained closed session does
not keep its module or an instance-owned host alive after the stack returns.
Close during a call clears the session field immediately; the active stack
still holds its borrowed module until it returns. No cleanup callback runs.
The separate Orca Worker implementation review found no defects in this policy:
the active stack keeps its borrowed instance until return. The lead froze the
real implementation together with that reviewer's probe and passed five checks
with empty stderr, including actual exception-object and delegate collection
and a game interface as TModule. The acceptance directory is named by
`artifacts/lead-typed-implementation-review-acceptance-path.txt`.
The Orca Worker also ran that exact six-file review closure on macOS arm64:
Release build and direct Mach-O apphost both exited 0, with five passing probes,
empty stderr and no skips. The lead checked the archive, source hashes and raw
outputs in `artifacts/typed-session-review-macos-20261018c`. This is desktop
JIT/IL ownership coverage, separate from signed loading.
Evidence is named by `artifacts/lead-typed-session-acceptance-path.txt`; the
design review is `artifacts/typed-trusted-session-design-review-20261018a/review.md`.
This is an ownership spike, not a public API, signed loading, cross-ALC,
interpreter, native R2R or iOS acceptance. The implementation review is accepted;
the revised isolated signed integration passes the old 17 delivery checks,
ten integration checks and 24 real-assembly resolver checks in the lead's
frozen-source Windows rerun. It now exercises the borrowed signed module after
Close, preserves the receipt and process lock on normal close, and clears the
separate host root on close or later author failure. Independent adapter and
v2 owner review require no implementation change under the documented callback
failure contract. The reviewed implementation is now in the experimental Host.
The isolated native initial-activation regression is accepted as described
below. Functional evidence is named
by `artifacts/lead-typed-delivery-v2-acceptance-path.txt`; see the
[integration acceptance brief](trusted-embedding-next.md) for measured scope.
The same frozen Host DLL also passes all ten integration checks on the pinned
private Windows runtime in mode 1 with ReadyToRun disabled. Successful Update
Execute interpreter IR appears in all four child processes; their stderr is
empty and runtime hashes stay unchanged. Evidence is
`artifacts/lead-signed-typed-private-runtime-0ce394771ac14aad9814d9fc6de8333c/receipt.json`.
This adds configuration-specific signed multi-call compatibility, not native
R2R, iOS or a per-call helper precode observation.

The signed typed integration also has accepted macOS arm64 execution evidence.
The Orca Worker supplied raw outputs and persisted exits for the same r2 apphost
under both TMPDIR=/tmp and TMPDIR=/private/tmp: each passed 17 delivery and ten
integration checks. The lead checked the archive, all 31 source hashes, stream
hashes and four exit records. Only IntegrationProbe path assertions differ from
v2; the session and loader implementations are unchanged. Original build logs
were not retained, so this accepts execution of the existing apphost, without
claiming an independently verified Mac build. See
`artifacts/lead-typed-evidence-audit-20261018f/macos-acceptance.json`.

A separate Orca Worker regression triggers a real unlisted DeliveryAppDep load
only on the signed module's second call. The lead reran that probe using its
already accepted v2 Host DLL in a fresh directory: exit 0, LATE_FAILURE_PASS,
empty stderr. The call returns author-failed, closes the session and clears the
host root; the receipt stays unchanged, later calls do not enter, same-process
recovery remains locked and a fresh process restores the signed release. The
unlisted dependency sentinel never runs. Evidence is
`artifacts/lead-typed-evidence-audit-20261018f/late-failure-acceptance.json`.
This is stock Windows signed IL evidence.

The Orca Worker then ran both signed native lanes against the reviewed v2
implementation. The lead re-evaluated all ten raw process outputs with the
unchanged proof functions, verified the 37-file frozen closure and product
hashes, and checked the receipt timelines. R2R enabled produced 15 bound native
PC matches across five processes; R2R disabled produced none. All ten helper
invocations have interpreted-entry plus IR evidence. The audit is
`artifacts/lead-typed-native-v2-audit-20261018g/receipt.json`. This accepts the
initial-activation native regression and permits experimental Host promotion.
Repeated typed calls still need their own native witnesses.

The Orca Worker promoted the four selected Host files without changing their
reviewed bytes, using the combined path/positive-owner IntegrationProbe overlay.
It added --integration after the existing --self-test in local verification
and the CI matrix. The lead checked all 31 active source hashes and the raw
outputs: Release build exit 0, delivery 17/17, integration 10/10 and selector
272/272. Evidence:
`artifacts/lead-typed-promotion-acceptance-20261018j/receipt.json`.
The lead also froze that exact combination and passed 17+10 checks on stock
Windows and the pinned private runtime, using identical Host DLL bytes. The
private run used mode 1, R2R off and produced two InvokeLogical IR entries.
Evidence: `artifacts/lead-canonical-typed-runtime-20261018h/receipt.json`.
This is experimental Host adoption, not a public SDK. The canonical native
initial-activation rerun now passes both lanes, with all 37 frozen files checked
by the lead: 15 positive method PC matches, none in the disabled lane, and ten
helper interpreter proofs. Evidence:
`artifacts/lead-canonical-native-audit-20261018l/receipt.json`.
Post-promotion full verification is now accepted from one uninterrupted local
Windows run: actual Popen.wait returncode 0, 469 inputs unchanged, all existing
suites and samples complete, plus delivery 17/17 and integration 10/10. Evidence
is `artifacts/lead-promoted-full-verify-acceptance-20261018s/receipt.json`. The
earlier run with an empty exit file remains preserved and is not used as exit
evidence. This does not establish execution of all three configured CI jobs.

The repeated-call native experiment reuses accepted v2 products. The lead
checked 14 call segments across eight processes: 21 enabled native PC matches,
zero disabled witnesses/matches, 14 post-call helper observations and unchanged
receipt snapshots. Thirty of 31 source files match the current Host; only the
unused IntegrationProbe overlay differs. Revision r3 fixes the original helper
MVID/token and result-shape false positives, and passes lead replay and scoped
independent review. That disposition is recorded in
`artifacts/lead-r3-review-disposition-20261018x/receipt.json`; it does not accept
the remaining cross-call witness gap.
Acceptance remains pending: independent review found that copying call 1's
witness rows into call 2 still passes, also reproduced on r3 in
`artifacts/lead-repeat-native-r3-provenance-20261018u/receipt.json`. A new
Orca Worker measurement will bind each fresh capture to its call identifier;
identical native PCs across calls remain valid. The later-failure outcome never
returns, so its zero result fields are not business values. The enabled native
lane and disabled control must be reported separately. Original output and
reviews remain preserved. The isolated game-owned typed-interface pilot revision q
now passes a lead rebuild and six-process run from its exact 36-source copy,
plus the unchanged 17 self-tests and 10 integration checks. Start and every Tick
are checked independently; the lead's 0, 0, then three-times-step mutation is
rejected with exit 1. A fourth module Tick throws from the actual module; fresh
recovery after that failure explicitly requires LastKnownGood/A and resets the
score to zero. Receipt, gate and object-release assertions pass. Independent
Orca Worker review also accepts q within the isolated private desktop IL scope.
The lead rechecked the exact sources, process results, negative control and
review in `artifacts/lead-score-pilot-q-acceptance-20261018ae/receipt.json`.
The seam is not promoted to a public SDK and proves no native, interpreter,
iOS or successive-session capability. The original pilot and its falsely
accepted mutation remain preserved.

The subsequent same-version successive-session experiment is now independently
accepted within the private synchronous stock Windows desktop IL scope. The
Orca Worker implementation and separate Orca Worker review match the lead's
37-source rebuild: five child processes exit 0, the original 17/10 checks and
six-process score pilot pass, and a cached-module mutant is rejected in the
normal second round. The lead's final evidence check is
`artifacts/lead-successive-sessions-acceptance-20261018ak/receipt.json`. Each
explicit Open creates a new module for the already-selected A; static state
and the process gate remain resident. Pre-gate rejection, bound-activator
failure and post-activation persistence failure have separate checked results.
LastKnownGood records version selection before construction or gameplay, and
GC evidence covers only the first closed module/host pair. This does not
promote an SDK or establish same-process version switching, interpretation,
native execution, iOS support or context unloading.

The fresh call-scoped native batch has now been reviewed by the lead and a
separate Orca Worker: eight actual exit-0 processes, 14 call segments, 21 enabled
host/private/update method bindings, zero disabled witnesses and 14 unchanged
receipt snapshots. Independent helper metadata was also checked against the
published final file. Scope identity rejects copied call-1 witnesses with the
old ID while allowing repeated PCs. This reuses the identified v2 Host; it is
not a canonical Host compilation. Evidence is
`artifacts/lead-call-scope-raw-audit-20261018aj/receipt.json`. The original
validator accepted a contradictory returned outcome for later-fail and
incorrect recovery FACTS semantics. Both reviews confirmed the untouched raw
streams have the correct exceptional exit and LastKnownGood/A recovery; the
repair replays those streams without another native measurement.

The r4 validator revision now passes the lead's replay of those same eight raw
processes and 26 targeted negative mutations across both lanes, including the
fully success-shaped false outcome and each invalid recovery field. The raw
files remain unchanged. Independent Orca Worker review accepts this exact
revision. The lead also directly requires zero raw witnesses in the disabled
streams, because r4 alone does not reject every extra unbound witness. Scoped
acceptance is recorded at
`artifacts/lead-call-scope-r4-acceptance-20261018aq/receipt.json`: 14 call
segments, 21 enabled method bindings and zero disabled witnesses. This is
frozen-v2 Windows x64 evidence, not a fresh native run or canonical Host build.

The follow-up r5 guard closes the validator's disabled-witness gap. Lead replay
passes 26 protocol negatives and eight inside/outside disabled-witness negatives,
keeps all raw files unchanged and accepts the real call2/call3 shared PCs.
Evidence is `artifacts/lead-call-scope-r5-review-20261018at/receipt.json`.
This is a lead-reviewed minimal replay revision of the independently reviewed
r4 parent. The relocated canonical repeated-call measurement now has lead and
independent Orca Worker scoped acceptance: eight actual exits 0, 14 scopes,
21 enabled bindings and zero disabled witnesses. It reuses canonical products
without rebuilding Host. Evidence is
`artifacts/lead-current-delivery-disposition-20261018bh/canonical-measurement-acceptance.json`.
The reusable driver's map-reference repair passes lead preflight and offline
replay plus independent Orca Worker review. Its scoped acceptance is
`artifacts/lead-map-closure-acceptance-20261018bj/receipt.json`.
Historical input snapshots are unchanged, and no hermetic compiler-input
closure, SDK or CI promotion is claimed.

The durable2 post-seal run now has actual scenario exits 0/0/0/0/1 and ordered
seal/pin/source/build events. Lead raw review and fresh read-only product parity
checks are at `artifacts/lead-post-seal-durable2-review-20261018au/receipt.json`
and `artifacts/lead-durable2-product-parity-20261018av/receipt.json`. The raw run
is retained. The recorded-final-path repair replaces stdout-derived path
expectations; its stage-provenance derivative 3b0cedf3 also rejects duplicate
stage keys and pins two local stale maps outside the historical closure.
Independent Orca Worker review still rejects this derivative: an outside final
produces an error but remains available to enabled, recover and author-fail.
The lead reproduces this with three same-byte payload copies at
`artifacts/lead-post-seal-containment-20261018cb/receipt.json`. The batch entry
point would abort on that error; the five recorded streams are not false
accepts. That rejected generation required withholding all affected
expectations while preserving the 211 historical files and original pin. Review is
`artifacts/post-seal-stage-provenance-review-k6zi-20261018/review.md`.
The fresh containment derivative 4bcceeed now passes lead copied replay and
four direct null-expectation/order/collision controls. It retains the historical
raw closure and pin and keeps recovery on the real enabled final. Independent
Orca Worker review now grants scoped acceptance, joined with the lead replay at
`artifacts/lead-post-seal-acceptance-20261018cj/receipt.json`. This accepts the
offline checker derivative without another native run. A command missing
`--final` is rejected before duplicate membership; a valid sibling may still
derive expectations, but any such problem aborts the batch. The five-file
derivative closure is not a hermetic whole-tool dependency closure.
The game-interface native multi-round delivery is now scoped-accepted after
r2 replay and independent Orca Worker review. Five original exits are 0/0/0/0/1,
with per-tick 2/4/6, an author-failing fourth tick and fresh same-version rounds.
Evidence is
`artifacts/lead-score-acceptance-map-check-20261018bi/score-acceptance.json`.
This remains the score-specific private Windows x64 integration. The two
unrelated contract assemblies and generic resident owner have been delivered
in isolated stock desktop IL. Independent review rejects full interaction
acceptance of the original: a signed return-only mutant passes with zero host
state. A fresh revision checks honest host state and callback counts, including
failure/close preservation. Independent review rejects its negative-control
evidence: return-only modules use alternate zero-state checks followed by a
forced exit 1, rather than the normal Ok/QuestOk failure path. The lead confirms
the latest identity derivative inherits this at
`artifacts/lead-generic-shared-predicate-20261018cc/receipt.json`. A new repair
must run honest and signed return-only modules through the same predicates.
That derivative is now delivered (0a2e6ce5 / Host a8aa4802). Lead source and raw
log audit confirms shared normal child modes and first-call GAME_BAD rejection;
independent Orca Worker focused F1/current cached-shared F2 review accepts it.
Evidence is
`artifacts/lead-generic-shared-predicate-review-20261018cf/receipt.json`.
The lead also directly runs six fresh stock-IL processes with copied Host and
signed inputs, exits 0/1/0/0/1/0, without rebuilding/signing. Evidence is
`artifacts/lead-generic-shared-predicate-execution-20261018ch/receipt.json`.
A joined independent Orca Worker review now accepts the bounded stock-IL
integration gate for a separate private Windows x64 native experiment. Lead
source/image/input verification and the gate decision are at
`artifacts/lead-generic-native-start-20261018ck/receipt.json`. This opens
implementation and measurement, without claiming native evidence. New-Host
persistence failure remains unmeasured and is a declared nonblocking limit.
The identity derivative separately delivers actual
module-reference comparisons and a rejected cached-module control. Independent
Orca Worker review scoped-accepts those checks and the new 4691e436 Host's
persistence control at
`artifacts/generic-module-identity-review-k6zi-20261018/receipt.json`, while
rejecting complete generic acceptance because F1 remains open.
Its valid run is pilot-output-2, while
the earlier DestinationExists run is excluded. Published typed calls are audited
at `artifacts/lead-generic-typed-call-audit-20261018ca/receipt.json`. A real
receipt-lock persistence control is scoped to the older frozen 02bbe359 Host
at `artifacts/lead-generic-persistence-control-20261018by/receipt.json`.
Independent Orca Worker review accepts only that older Host's persistence
control at `artifacts/host-state-f1-persistence-review-cc7q-20261018/receipt.json`.
Those older controls remain image-scoped. The current joined gate accepts the
stock-IL integration. The separate dual-contract native implementation has
now delivered pilot-native-4: eight honest process exits are 0, with 18 armed
capture attempts across the two lanes but no targeted native frames. Final
Host parity now returns unsupported fieldrva-signature (exit 4); both module
pairs match. Lead replay verifies 35 supplement mutations and exact-final
Host 17/10 managed baselines. Complete per-call validation remains rejected:
counts are cumulative, failure scopes are missing and round stays 1.
Independent Orca Worker
review rejects native bindings, while retaining the recorded business and
armed disabled-control observations. That review also identifies incomplete
failure/closed scopes and missing final-image baseline/runtime-pin records.
The lead's frozen-delivery observation and independent signature/byte audit
are artifacts/lead-generic-native-delivery-20261018ct/receipt.json and
artifacts/lead-generic-native-inventory-20261018cu/receipt.json. The latter
verifies 22 signatures and 47 file copies, without native execution acceptance.
The standalone same-API diagnostic reproduces one unnamed MEM_MAPPED PC in
five stock/private-runtime processes. It identifies neither mapping ownership
nor the cause of the truncated walk. Final HTTP Host a908231b also has its own
verified 17/10 stock baseline.
The independent copied-binary HTTP review now scoped-accepts nine loopback
lanes on that same a908231b image (parent PID 9160, exit 0). The joined decision
accepts those lanes with the separately delivered final-image baseline at
artifacts/lead-http-joined-acceptance-20261018dc/receipt.json. Redirects,
TLS and external networking are unmeasured.
Evidence is artifacts/lead-delivery-supplement-review-20261018da/receipt.json
and artifacts/lead-capture-diagnostic-review-20261018cz/receipt.json.
Current checkpoints are in
[the integration brief](trusted-embedding-next.md).

The separate distinct-version experiment now has Lead and independent Orca
Worker scoped acceptance on Host e5c00853. Two independently compiled, signed
Orbit modules produce actual Host state 0/3/6 and 0/5/10. Five original and
five independently reproduced client processes exit 0: HTTP A selection,
server-free A recovery, tampered B rejection followed by A recovery, fresh-
process B selection, and server-free B recovery. A verified B offer in A's
process remains ProcessSelectionLocked without another activation or receipt
change. Independent public-key verification binds both signed inventories to
the downloaded bytes; compiled Step bodies differ only in their 3/5 constant.
The exact-image 17/10 baseline and the two receipt epochs are joined at
the acceptance receipt (archival/local evidence: `../artifacts/lead-distinct-http-acceptance-20261018ez/receipt.json`).
This is an isolated Windows desktop IL loopback artifact, not SDK promotion,
same-process hot swap, interpreter fallback, downloaded R2R or device evidence.
Its post-start process records do not establish launch-time image identity or
the loaded runtime. A fresh-sibling launch-evidence repair and a separate
repaired-Host R2R execution pair remain in progress; their results do not
transfer from this acceptance. Physical devices and simulators remain deferred.

The standalone managed IL/R2R comparison diagnostic has lead and independent
Orca Worker scoped acceptance, including fixed-layout static data, nonempty
resources and malformed-input controls. Evidence is
`artifacts/lead-managed-parity-acceptance-20261018bu/receipt.json`. This is
structural comparison, without executing inspected assemblies.
These increments do not promote a public SDK or add physical-device evidence.

Current-canonical macOS arm64 desktop acceptance is complete. The Orca Worker
built the exact 31-source closure, including IntegrationProbe e7d54821, and
directly ran the Mach-O apphost under both `/tmp` and `/private/tmp`. Build and
all four runs have persisted exit 0; each alias passes delivery 17/17 and
integration 10/10. The lead compared archived sources and raw logs and directly
checked the remote source hashes and managed Host DLL hash. Evidence is
`artifacts/lead-canonical-macos-acceptance-20261018v/receipt.json`. The remote
attestation checks current post-run files; it is not a second historical
before/after capture. This is desktop IL, without native, interpreter or iOS
claims, and does not imply execution of all configured CI jobs.

## Current priorities - 2026-10-15

For implementation in the next session, follow the
[development plan](next-development-plan.md). On 2026-10-16 the host-pumped map
context gained a callback-scoped signal. `IMapContext.Signal` and `RaiseSignal`
work only during `OnStart`, `OnTick`, or `OnStop`. The session closes the signal and
drops subscribers when that callback returns. A later raise or subscription
throws `InvalidOperationException` ("The map signal is closed.") and does not run
the old handler. Desktop `tests/RuneCLR.Runtime.Tests` passed 46/46 in Release, including that closure and the tick schedule. The
same desktop suite now also covers a primitive tick schedule: a value stored during OnStart is taken on a later host tick, a closed callback cannot add or take one, and Stop drops anything still pending before OnStop. Entity, log, and Charge changes also stay inside the open callback. After it returns they throw InvalidOperationException ("The map callback is closed.") and do not change host state. Entities created during the callback are still released. Between callbacks the host can copy live entity ids and names. That copy stays stable when a later tick replaces the entity, and copying after Stop throws. The host can also complete a primitive work request between callbacks. The script takes that int on a later callback. FailWork supplies an int reason and does not store an exception. Stop drops anything not taken. Author failure also stops the session, so the host cannot complete or fail a request it already observed. A caught work or schedule limit also stops the session and clears the accepted item before OnStop. When OnStop returns, that latched limit is not reported again as an OnStop failure. Two live sessions do not share work requests. After one session fails, the next session can reuse the same work id and complete its own request. A cancelled tick signal is not delivered to that next session. The restricted UGC profile still excludes the delegate surface, the tick schedule, and host-completed work. The trusted-update selector passed 270/270, including primitive host work completed between calls and dropped when the session closes, and a host object or signal kept from an earlier call that stays closed on the next call. A throwing Work call becomes ActivationFailed, drops only that call's new request, keeps an earlier open request and an earlier completed result, and does not keep the exception text. The console sample self-test also prints WORK 0, WORK ActivationFailed, OPEN load, TAKE 4, and CLOSED, without the private exception text. It also prints NAMES bad,good, TAKE 7, and TAKE 4 when a failed result is completed before a later success. Closing a session drops a completed result that was not taken, and opening it again does not restore that result. Physical iOS remains
paused. Windows independent IL/R2R
composition is recorded below. Simulator A and B now each have a combined
receipt: Business.Execute at the downloaded owner base plus 5472, and
TRUSTED_UPDATE_SUCCESS result=216 on the console log, using the rebuilt host.
The only available phone is an iPhone XR locked to iOS 18.7. That is not the
iOS 27 runtime used here, so do not start a physical-device build or install. The desktop selector is the step-3 loop: one version for the
process, next-start rollback, and no same-process switch or native unload.

On 2026-10-16 the iOS 27 simulator reran the experiment host after rebuilding
TrustedUpdate.Host.dll
(8e557980bbfb45a17650983edf1fb03e3095bf88f5644e4547c5d8c6218c753d from
eng/ios-trusted-update/Host.cs
7c01535fb17c9173fe27eefc013f3016179172c3af9ed360257d6ba61195d84c). Version A
still printed TRUSTED_UPDATE_SUCCESS version=A result=216 with PRIVATE_VALUE=100
and IL_HELPER_RESULT=307. A throwing Update.Run whose message is
update-private-failure-9f3c printed only TRUSTED_UPDATE_FAILURE version=T
failure=ActivationFailed. That simulator log did not contain the update
message and did not print success. This receipt is host logging, not a new
Business.Execute native entry. The simulator was deleted. Physical iOS remains
paused. The later source treats every reflected exception as ActivationFailed,
including a message that starts with "payload file ".
eng/verify-ios-host-callback.py prints UPDATE_DIAGNOSTIC_NOT_SPOOFED. The iOS
27 simulator then ran that source as TrustedUpdate.Host.dll SHA-256
2061648ac08d33ccad6b526242a87f6257e614ecfaadb0464ce19a278331e0a5. Version A
again printed result=216 with PRIVATE_VALUE=100 and IL_HELPER_RESULT=307. Both
update-private-failure-9f3c and payload file leaked-from-update printed only
failure=ActivationFailed, and neither text appeared in the log. That is host
logging, not a new native entry. The simulator was deleted. The experiment host
can now call TryPlanCandidate before load when selector-plan.txt is present.
Approval and the host target come from the process environment. On the iOS 27
simulator, host c2e1530cd2924e05b6ab0ab3fe523ab0d13611757ed8f1ac8604f0e024dc285f
and selector 8fa1f1cfe3cf0f51fbfbe413b3d4c713f2b08c31285bab2674edfcb22c155209
accepted the same A files (Update.dll
738a10408add5ba0e8163872d449e9d9b66aad82319b56e8461d1930a347029f) with
SELECTOR_PLAN version=A and result=216, then rejected those unchanged files as
NotApproved when the approval hash was 64 zeros. The rejection log had no echo,
private value, or success line. That NotApproved receipt did not restore a previous version. A later host
build does. After A succeeds it writes the last known good record. An
unapproved B then prints SELECTOR_FALLBACK version=A candidateFailure=NotApproved
and runs A: result=216, PRIVATE_VALUE=100, IL_HELPER_RESULT=307. The record
bytes stay the same. An approved B whose Run throws prints failure=ActivationFailed,
does not fall back, and does not change the record. Host
7ab5ce9336eeae5c135f60333ac7cd14be10a966a7c64b9fd5855967b13fe9cc and selector
3cb386cccaefd250f7c5c17daf6e04945e8aca890fce1a630fa7a0cabff4afef were used. The
loader is still the experiment host, not TrySelectCandidate. This is not a
native entry. The simulator was deleted. A later build calls
TryStartHostLoaded: the selector decides the version and the host still runs
Run. On the iOS 27 simulator, host
464e419805f0a8b475ce79f530a89f3caddeedf432107345ccb614fe83f89595 and selector
db8507ab468edf15524fed1f0df7e563d1dddbe4486ee71dced4b56081055ba8 accepted A
(SELECTOR_PLAN, result=216, PRIVATE_VALUE=100, IL_HELPER_RESULT=307), fell
back to A for an unapproved B without changing the record, and reported
ActivationFailed for an approved throwing B without fallback or the private
message. The simulator was deleted. This is not a native entry.

The first selector slice is in src/RuneCLR.TrustedUpdate.
tests/RuneCLR.TrustedUpdate.Tests passes 270/270. A stored candidate can be reread without loading, and TryStartHostLoaded lets the host activate without the selector loading an assembly. TryStart uses a candidate that passes planning, and otherwise restores last known good before load. An activation failure does not fall back in that process. The console sample --start command prints FALLBACK good ContentHashMismatch when the new directory hash does not match, and REJECTED ActivationFailed when activation throws, without changing the stored bytes. Additional content files are checked before load and before approval: a missing file, a hash mismatch, or a path that resolves outside the content root is rejected, and a .. path that still resolves inside is accepted. Last known good repeats those recorded file hashes on restore. The console sample self-test also selects the good candidate, rejects a hash mismatch, a missing approval, an additional file whose hash does not match, an additional file name of .., selects a matching additional file and then rejects restore after those bytes change, and a last-known-good assembly path outside the candidate directory, restores the last known good version from inside that directory, then prints TICK 5 and LATE-CLOSED for one host Echo call. The same self-test prints LISTEN 10, SEEN 10, and SUBSCRIBE-CLOSED when one open subscriber is removed and a later subscription is rejected. It also prints VALUE-REJECTED, CALLS-BEFORE 0, OBJECT-SAME, STRING-SAME, INT 11, and CALLS 3 for generic echo.
 An open session can also round-trip one host object with reference equality and, after the update releases it, the object can be collected while the selected version stays resident. An EchoObject that stores the host object and then throws becomes ActivationFailed, keeps no exception text, leaves the object only in the update until release clears that field, and a later EchoObject still returns the same reference. EchoGeneric<T> returns the same object reference and the same int. A throwing EchoGeneric becomes ActivationFailed, keeps no exception text, and the next generic int and object echo still succeed. A boxed value passed to generic object echo throws ArgumentException before the update runs, and a string still comes back as the same reference. A generic method that does not return its type argument is not called. Null still throws ArgumentNullException, and Tick still runs. When a matching EchoGeneric<T>(T) is also present, that overload is used and the mismatched one is not called. An EchoObject that returns a different object still succeeds. The input is not retained, and release lets the created object be collected. Completing or failing a work id a second time is rejected and the first result stays. Completing that id after it is taken is also rejected. A blank work name fails that call, drops only the request made in that call, and keeps an earlier request. A null work name does the same and still leaves an earlier completed result to be taken. A whitespace-only name is rejected without trimming a name that contains other characters. Two requests with the same name keep distinct ids, and completing one does not complete the other. Results are taken in completion order, not request order. A failed result completed first is taken before a later success. An unknown work id is rejected and does not replace the open request. Closing the session drops an untaken failure, and the next session does not take that reason. The next session uses a new id, and the old id does not complete that request. A null host object and a null echoed object are rejected before the update runs. A null host callback is rejected the same way and does not select the no-callback Tick. A successful callback Tick does not run the plain Tick. If that callback throws, the plain Tick is not run either, and a later plain Tick still succeeds. The same split holds for an ITrustedUpdateHost Tick, including when Echo throws. When all three Tick shapes are present, each call runs only its own method. When several Listen methods are present, only the one that takes ITrustedUpdateSignals is called. If that method throws, the parameterless Listen is not called, and the next Listen still uses the signal method. When several Work methods are present, only the one that takes ITrustedUpdateWork is called. If that method throws, the parameterless Work is not called, its new request is dropped, and the next Work still uses the gate method. When several EchoObject methods are present, only the one that takes object and returns object is called. If that method throws, the parameterless EchoObject is not called, and the next EchoObject still uses the object method. When several ReleaseHeldObjects methods are present, only the parameterless void method is called. If that method throws, the ReleaseHeldObjects method that takes object is not called, and the next release still uses the parameterless method. When an instance Listen and a static Listen both take ITrustedUpdateSignals, only the static method is called. When the only signal Listen is an instance method, TryListen fails before calling it and does not call a static parameterless Listen. When an instance Work and a static Work both take ITrustedUpdateWork, only the static method is called. When the only gate Work is an instance method, TryWork fails before calling it and does not call a static parameterless Work. When an instance EchoObject and a static EchoObject both take object and return object, only the static method is called. When the only object EchoObject is an instance method, TryEchoObject fails before calling it and does not call a static parameterless EchoObject. When an instance ReleaseHeldObjects and a static ReleaseHeldObjects are both parameterless void methods, only the static method is called. When the only parameterless ReleaseHeldObjects is an instance method, TryReleaseHeldObjects fails before calling it and does not call a static ReleaseHeldObjects that takes object. When an instance Tick and a static Tick both take int and return int, only the static method is called. When the only Tick that takes int and returns int is an instance method, TryTick fails before calling it and does not call a static Tick that also takes ITrustedUpdateHost. A Listen declared only on a base type is not called, and TryListen does not call a parameterless Listen declared on the entry type. A Work declared only on a base type is not called, and TryWork does not call a parameterless Work declared on the entry type. An EchoObject declared only on a base type is not called, and TryEchoObject does not call a parameterless EchoObject declared on the entry type. A parameterless ReleaseHeldObjects declared only on a base type is not called, and TryReleaseHeldObjects does not call a ReleaseHeldObjects that takes object on the entry type. A Tick that takes int and returns int declared only on a base type is not called, and TryTick does not call a Tick that also takes ITrustedUpdateHost on the entry type. When a non-public Listen and a public Listen both take ITrustedUpdateSignals, only the public method is called. When the only signal Listen is non-public, TryListen fails before calling it and does not call a public parameterless Listen. When a non-public Work and a public Work both take ITrustedUpdateWork, only the public method is called. When the only gate Work is non-public, TryWork fails before calling it and does not call a public parameterless Work. When a non-public EchoObject and a public EchoObject both take object and return object, only the public method is called. When the only object EchoObject is non-public, TryEchoObject fails before calling it and does not call a public parameterless EchoObject. When a non-public ReleaseHeldObjects and a public ReleaseHeldObjects are both parameterless void methods, only the public method is called. When the only parameterless ReleaseHeldObjects is non-public, TryReleaseHeldObjects fails before calling it and does not call a public ReleaseHeldObjects that takes object. When a non-public Tick and a public Tick both take int and return int, only the public method is called. When the only Tick that takes int and returns int is non-public, TryTick fails before calling it and does not call a public Tick that also takes ITrustedUpdateHost. When one Tick takes int and returns long and another takes int and returns int, only the int-returning method is called. When the only Tick that takes int returns long, TryTick fails before calling it and does not call a Tick that also takes ITrustedUpdateHost. When one Listen takes ITrustedUpdateSignals and returns long and another takes ITrustedUpdateSignals and returns int, only the int-returning method is called. When the only signal Listen returns long, TryListen fails before calling it and does not call a parameterless Listen that returns int. When one Work takes ITrustedUpdateWork and returns long and another takes ITrustedUpdateWork and returns int, only the int-returning method is called. When the only gate Work returns long, TryWork fails before calling it and does not call a parameterless Work that returns int. When one EchoObject takes object and returns string and another takes object and returns object, only the object-returning method is called. When the only object EchoObject returns string, TryEchoObject fails before calling it and does not call a parameterless EchoObject that returns object. When one parameterless ReleaseHeldObjects returns int and another returns void, only the void method is called. When the only parameterless ReleaseHeldObjects returns int, TryReleaseHeldObjects fails before calling it and does not call a ReleaseHeldObjects that takes object and returns void. When one parameterless Activate returns int and another returns void, only the void method is called. When the only parameterless Activate returns int, selection fails before calling it, the version is not resident, and last known good is not written. When one Activate takes int and another is parameterless, and both return void, only the parameterless method is called. When the only Activate takes int, selection fails before the method body runs, the version is not resident, and last known good is not written. When an instance Activate and a static Activate are both parameterless void methods, only the static method is called. When the only parameterless Activate is an instance method, selection fails before calling it, does not call a static Activate that takes int, the version is not resident, and last known good is not written. A parameterless Activate declared only on a base type is not called, selection does not call a static Activate that takes int on the entry type, the version is not resident, and last known good is not written. When a non-public Activate and a public Activate are both parameterless void methods, only the public method is called. When the only parameterless Activate is non-public, selection fails before calling it, does not call a public Activate that takes int, the version is not resident, and last known good is not written. When a parameterless Activate throws, selection becomes ActivationFailed, does not call an Activate that takes int, keeps no exception text, the version is not resident, and last known good is not written. When one parameterless method is named activate and another is named Activate, only Activate is called. When the only parameterless method is named activate, selection fails before calling it, does not call an Activate that takes int, the version is not resident, and last known good is not written. When one entry type is named entry and another is named Entry, only Activate on Entry is called. When the only entry type is named entry, selection fails before calling its Activate, the version is not resident, and last known good is not written. When one parameterless Activate is an open generic method and another is not, only the non-generic method is called. When the only parameterless Activate is an open generic method, selection fails before calling it, does not call an Activate that takes int, the version is not resident, and last known good is not written. When the entry type name selects a nested type, only that nested Activate is called. When the entry type name uses a dot for a nested type, selection fails before calling either Activate, the version is not resident, and last known good is not written. When the entry type is an open generic type, selection fails before calling Activate, does not call Activate on another type, the version is not resident, and last known good is not written. When an open generic type and a non-generic entry type are both present, only Activate on the named non-generic type is called. When one parameterless ReleaseHeldObjects is an open generic method and another is not, only the non-generic method is called. When the only parameterless ReleaseHeldObjects is an open generic method, TryReleaseHeldObjects fails before calling it and does not call a ReleaseHeldObjects that takes object. When one Listen takes ITrustedUpdateSignals and is an open generic method and another is not, only the non-generic method is called. When the only signal Listen is an open generic method, TryListen fails before calling it and does not call a parameterless Listen. When one Work takes ITrustedUpdateWork and is an open generic method and another is not, only the non-generic method is called. When the only gate Work is an open generic method, TryWork fails before calling it and does not call a parameterless Work. When one Tick takes int and returns int and is an open generic method and another is not, only the non-generic method is called. When the only Tick that takes int and returns int is an open generic method, TryTick fails before calling it and does not call a Tick that also takes ITrustedUpdateHost. When one EchoObject takes object and returns object and is an open generic method and another is not, only the non-generic method is called. When the only object EchoObject is an open generic method, TryEchoObject fails before calling it and does not call a parameterless EchoObject. When one Tick takes int and ITrustedUpdateHost and is an open generic method and another is not, only the non-generic method is called. When the only Tick that takes int and ITrustedUpdateHost is an open generic method, TryTick fails before calling it and does not call a Tick that only takes int. When one Tick takes int and Func<int, int> and is an open generic method and another is not, only the non-generic method is called. When the only Tick that takes int and Func<int, int> is an open generic method, TryTick fails before calling it, the callback is not run, and a Tick that only takes int is not called. When EchoGeneric has two type parameters and another EchoGeneric has one, only the one-parameter method is called. When the only EchoGeneric has two type parameters, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric returns object and another returns its type argument, only the type-argument method is called. When the only EchoGeneric returns object, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric takes two arguments and another takes its type argument, only the one-argument method is called. When the only EchoGeneric takes two arguments, object and int echo fail before calling it, and Tick still runs. When one generic echo is named echoGeneric and another is named EchoGeneric, only EchoGeneric is called. When the only generic echo is named echoGeneric, object and int echo fail before calling it, and Tick still runs. When an instance EchoGeneric and a static EchoGeneric both take and return their type argument, only the static method is called. When the only EchoGeneric is an instance method, object and int echo fail before calling it, and Tick still runs. An EchoGeneric declared only on a base type is not called, a two-argument EchoGeneric on the entry type is not called, and Tick still runs. When a non-public EchoGeneric and a public EchoGeneric both take and return their type argument, only the public method is called. When the only one-argument EchoGeneric is non-public, object and int echo fail before calling it, a public two-argument EchoGeneric is not called, and Tick still runs. When one EchoGeneric takes its type argument by reference and another takes it by value, only the by-value method is called. When the only EchoGeneric takes its type argument by reference, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric returns its type argument by reference and another returns it by value, only the by-value method is called. When the only EchoGeneric returns its type argument by reference, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric returns an array of its type argument and another returns the type argument, only the type-argument method is called. When the only EchoGeneric returns an array of its type argument, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric takes an array of its type argument and another takes the type argument by value, only the by-value method is called. When the only EchoGeneric takes an array of its type argument, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric takes a list of its type argument and another takes the type argument by value, only the by-value method is called. When the only EchoGeneric takes a list of its type argument, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric returns a list of its type argument and another returns the type argument, only the type-argument method is called. When the only EchoGeneric returns a list of its type argument, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric takes a nullable of its type argument and another takes the type argument by value, the unreadable nullable signature is skipped and only the by-value method is called. When the only EchoGeneric takes a nullable of its type argument, the unreadable signature is skipped, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric returns a nullable of its type argument and another returns the type argument, the unreadable nullable signature is skipped and only the type-argument method is called. When the only EchoGeneric returns a nullable of its type argument, the unreadable signature is skipped, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric takes a pointer to its type argument and another takes the type argument by value, only the by-value method is called. When the only EchoGeneric takes a pointer to its type argument, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric returns a pointer to its type argument and another returns the type argument, only the type-argument method is called. When the only EchoGeneric returns a pointer to its type argument, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric takes its type argument as an out parameter and another takes it by value, only the by-value method is called. When the only EchoGeneric takes its type argument as an out parameter, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric takes its type argument as an in parameter and another takes it by value, only the by-value method is called. When the only EchoGeneric takes its type argument as an in parameter, object and int echo fail before calling it, and Tick still runs. When the only EchoGeneric takes its type argument by value and the parameter is marked in, object and int echo call that method and Tick still runs. When the only EchoGeneric takes its type argument by value and the parameter is marked out, object and int echo call that method and Tick still runs. When the only EchoGeneric takes its type argument by value and the parameter is optional, object and int echo call that method and Tick still runs. When the only EchoGeneric has a class constraint, an object echo calls it, an int echo fails before the body runs, and Tick still runs. When the only EchoGeneric has a struct constraint, an int echo calls it, an object echo fails before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Exception, an exception echo calls it, an object echo and an int echo fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IDisposable, a disposable echo calls it, an object echo and an int echo fail before the body runs, and Tick still runs. When the only EchoGeneric has a public parameterless constructor constraint, an object echo and an int echo call it, a string echo fails before the body runs, and Tick still runs. When the only EchoGeneric has a class constraint and a public parameterless constructor constraint, an object echo calls it, a string echo and an int echo fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IComparable<T>, a string echo and an int echo call it, an object echo fails before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Delegate, a delegate echo calls it, an object echo and an int echo fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IEnumerable<char>, a string echo calls it, an object echo and an int echo fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEnumerable<char> and IComparable<T>, a string echo calls it, a char array, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric has a class constraint and is constrained to IComparable<T>, a string echo calls it, an object echo and an int echo fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IDisposable and a public parameterless constructor, a memory stream echo calls it, a timer, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Exception and a public parameterless constructor, an invalid-operation exception echo calls it, a target-invocation exception, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IEnumerable<object>, an object-array echo calls it, a string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IComparer<string>, a comparer of object echo calls it, a string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<object>, a string-array echo and an object-array echo call it, a string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<object>, a list of object is called, while a list of string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IReadOnlyList<object>, a list of string and a list of object are called, a string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<string>, a list of string and a string array are called, a list of object, an object array, a string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<int>, an int array and a list of int are called, a string array, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<object>, a string array is called, an int array, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IReadOnlyList<object>, a list of string is called, a list of int, an int array, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IComparer<int>, a comparer of int is called, a comparer of object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<string>, a one-dimensional string array is called, a rectangular string array, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<string>, a zero-based string array is called, a string array with a non-zero lower bound, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<string[]>, a jagged string array is called, a string array, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IReadOnlyList<Exception[]>, a jagged array of invalid-operation exceptions and a jagged array of exceptions are called, an exception array, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<Exception[]>, a jagged array of invalid-operation exceptions and a jagged array of exceptions are called, an exception array, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<Exception[]>, a list of exception arrays is called, a list of invalid-operation-exception arrays, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IReadOnlyList<Exception[]>, a list of invalid-operation-exception arrays and a list of exception arrays are called, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IComparer<Exception[]>, a comparer of exception arrays and a comparer of object are called, a comparer of invalid-operation-exception arrays, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IComparer<InvalidOperationException[]>, a comparer of invalid-operation-exception arrays and a comparer of exception arrays are called, a comparer of exception, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<Exception[], int>, a function of exception arrays and a function of object are called, a function of invalid-operation-exception arrays, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<object, Exception>, a function returning an exception and a function returning an invalid-operation exception are called, a function returning object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<Exception[], Exception>, a function of exception arrays returning an exception and a function of object returning an invalid-operation exception are called, a function of object returning object, a function of invalid-operation-exception arrays returning an invalid-operation exception, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Action<Exception[]>, an action of exception arrays and an action of object are called, an action of invalid-operation-exception arrays, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Action<int>, an action of int is called, an action of object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<int, object>, a function of int returning object and a function of int returning string are called, a function of object returning object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<object, int?>, a function of object returning a nullable int is called, a function of object returning int, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<object, string>, a function returning string and a function whose return is annotated as nullable string are both called, an object and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<int?, object>, a function of nullable int is called, a function of int, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<string, object>, a function of string and a function whose input is annotated as nullable string are both called, a function of int, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Predicate<string>, a predicate of string and a predicate of object are called, a function of string returning bool, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<string, bool>, a function of string returning bool and a function of object returning bool are called, a predicate of string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Comparison<string>, a comparison of string and a comparison of object are called, a function of two strings returning int, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<string, string, int>, a function of two strings and a function of two objects are called, a function of object and int, a comparison of string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<string, string, object>, a function of two strings returning object and a function of two objects returning string are called, a function of two strings returning int, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<string, string, object>, a function of two strings returning object is called, a function of string and int returning string, a function of int and string returning string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IProgress<string>, a progress of string and a progress of object are called, a progress of int, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IProgress<int>, a progress of int is called, a progress of object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IObservable<Exception>, an observable of exception and an observable of invalid-operation exception are called, an observable of object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IObservable<int>, an observable of int is called, an observable of object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IObserver<Exception>, an observer of exception and an observer of object are called, an observer of invalid-operation exception, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IObserver<int>, an observer of int is called, an observer of object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IEquatable<string>, a string is called, an object that is only equatable to object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IEquatable<int>, an int echo calls it, a string, an object that is only equatable to object, and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IComparable<string>, a string and an object that is comparable to object are called, a plain object and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IComparable<int>, an int echo calls it, a string, an object that is comparable to object, and a plain object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<string> and IComparable<string>, a string is called, an object that is only comparable to object, an object that is only equatable to object, a plain object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo calls it, a string, an object that is only comparable to object, an object that is only equatable to object, and a plain object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<string> and IComparable<string>, a string and another type that implements both interfaces are called, an object that is only comparable to object, an object that is only equatable to object, a plain object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo calls it, a struct that implements both interfaces is rejected before the generic call, and a string and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo and a class that implements both interfaces are called, a struct that implements both interfaces is rejected before the generic call, and a string and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo and a class that implements both are called, a class that implements only IEquatable<int>, a class that implements only IComparable<int>, and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo and a type whose interface extends both are called, a type that implements only one of them and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo and a derived class whose base implements both are called, a type that implements only one of them and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo and a generic box closed over int are called, a generic box closed over string and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo and a class derived from a generic box closed over int are called, a generic box closed over string and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo and a generic box closed over int are called, a generic box closed over nullable int and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DayOfWeek> and IComparable<DayOfWeek>, a generic box closed over that enum is called, an enum value is rejected before the generic call, and a generic box closed over int, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a box closed over that enum is called, an enum value is rejected before the generic call, and a box closed over a different enum, an object, and an int fail before the body runs and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class derived from a generic box closed over that enum is called, an enum value is rejected before the generic call, and a class derived from a generic box closed over a different enum, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a generic box closed over that enum is called, an enum value is rejected before the generic call, and a generic box closed over the nullable enum, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that implements both is called, an enum value is rejected before the generic call, and a class that implements only IEquatable<DateTimeKind>, a class that implements only IComparable<DateTimeKind>, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a type whose interface extends both is called, an enum value is rejected before the generic call, and a type that implements only one of them, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a derived class whose base implements both is called, an enum value is rejected before the generic call, and a type that implements only one of them, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that implements both is called, a struct that implements both is rejected before the generic call, and a string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that implements both enum interfaces is called, an enum value is rejected before the generic call, and a type that implements both object interfaces, a type that implements only one of them, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that implements both specific enum interfaces is called, an enum value is rejected before the generic call, and a class that implements both interfaces closed over System.Enum, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that implements both generic enum interfaces is called, an enum value is rejected before the generic call, and a class that implements IEquatable<DateTimeKind> plus the non-generic IComparable, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that implements both non-nullable enum interfaces is called, an enum value is rejected before the generic call, and a class that closes either interface over the nullable enum, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to struct, an int echo calls it, an enum value is rejected before the generic call, and an object, a string, and a class fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to System.Enum, an enum value is rejected before the generic call, and an object, a class, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class, an object and a class are called, an enum value is rejected before the generic call, and an int fails before the body runs, and Tick still runs. When the only EchoGeneric is constrained to new(), an object, a class, and an int echo are called, an enum value is rejected before the generic call, and a string fails before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both class and new(), an object and a class with a public parameterless constructor are called, an enum value is rejected before the generic call, and a string and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to struct and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, an enum value is rejected before the generic call, and an object, a class, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that implements both is called, an enum value is rejected before the generic call, and an object, a string, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class, new(), and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that implements both and has a public parameterless constructor is called, an enum value is rejected before the generic call, and a class without that constructor, an object, a string, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class, new(), and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class with a public parameterless constructor is called, an enum value is rejected before the generic call, and a class with only a private parameterless constructor, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class, new(), and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class with a public parameterless constructor is called, an enum value is rejected before the generic call, and a class whose only public constructor has an optional parameter, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class, new(), and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a derived class whose base implements both and which has its own public parameterless constructor is called, an enum value is rejected before the generic call, and a class without a public parameterless constructor, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class, new(), and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a derived class with its own public parameterless constructor is called, an enum value is rejected before the generic call, and a derived class that only declares a parameterized constructor, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class, new(), and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that also declares a static constructor is called, an enum value is rejected before the generic call, and a derived class that only declares a parameterized constructor, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class, new(), and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that declares both a public parameterless constructor and another constructor is called, an enum value is rejected before the generic call, and a derived class that only declares a parameterized constructor, an object, and an int fail before the body runs, and Tick still runs. The console sample self-test prints NULL-CALLBACK, TICK ActivationFailed, CALLS-BEFORE 0, TICK 2, and CALLS 1 for that path. When several EchoGeneric methods have the same shape, the selector does not choose among them by constraints, and the reflection order itself is not a contract.
 A signal subscriber added during Listen is dropped when that call returns, and a later Raise or subscription does not run or attach a handler. Removing one subscriber while Listen is open drops only that subscriber. A host object kept from Tick and a signal kept from Listen stay closed when the next call runs, while that next call still uses its own host or signal. The same drop happens when Listen throws after the first Raise: the host reports ActivationFailed, does not keep the exception text, and the selected version stays resident. A subscriber that throws during Raise does the same, and the next Listen still runs. TryPlanCandidate checks hash and approval before any assembly load. A selected version reports resident-until-process-exit, with unload and same-process switching unsupported. Closing a session releases only that session; the selected version stays resident. An open session can call Tick; after close the call returns SessionNotOpen and the version remains. A Tick exception becomes ActivationFailed, without the update exception, and the version stays resident. Tick can also take a host callback. It runs only during that call, the process does not store it, and a copy kept by the update cannot call the host after TryTick returns. A throwing host callback becomes ActivationFailed without the exception text, and the version stays resident. Tick can also take ITrustedUpdateHost. Echo is valid only during that call, the process does not store the host, and a copy kept by the update cannot call Echo afterwards. A throwing Echo becomes ActivationFailed without the exception text, and the version stays resident. A correct content hash without
a matching host approval returns NotApproved before any assembly load. Approval
is a version, hash and approval id record, not a signature. The iOS driver startup plan and TryPlanCandidate agree on missing content, an invalid candidate, hash mismatch, approval failure, an incompatible target, and a file outside the content root. A path containing .. is accepted only when it still resolves inside that root. The console sample passes its candidate directory as the content root when it plans and selects. eng/verify-trusted-update-plan.py checks that agreement locally. The iOS driver also compares every hash in the compile manifest files map with the copied payload before launch, including when no approval file is present. A mismatch or missing listed file is rejected before the business process. A payload name containing .. or a separator is InvalidCandidate and is not opened. If that candidate fails and a last-known-good directory still matches its file hashes, the driver copies that payload to trusted-update-last-known-good and starts that directory instead of the bad candidate. The rejected trusted-update-* directory is then removed. The last-known-good directory and any other directory are not removed. That deletion is checked locally and was not part of the simulator launch that follows. On 2026-10-16 a tampered B private file was ContentHashMismatch. The same host binary then started the matching A payload: process 26975, directory trusted-update-last-known-good, HOST_ECHO=41, PRIVATE_VALUE=100, IL_HELPER_RESULT=307, TRUSTED_UPDATE_SUCCESS version=A result=216. The tampered private hash was 5488e92bbf48ca2aec9667618f43a79a0b04a6c99e1064a7a0196555ec886f83 and was not the file that ran. Simulator 585B0C45-9336-4AEB-8D6B-18FA2537F59B was deleted. This launch did not capture a native method entry. A later iPhone 17 iOS 27 launch did exercise the deletion. Process 27566 used trusted-update-last-known-good and printed HOST_ECHO=41, PRIVATE_VALUE=100, IL_HELPER_RESULT=307 and TRUSTED_UPDATE_SUCCESS version=A result=216. trusted-update-B was retired before launch and was still absent afterward. The good private file stayed 38163d3c8ea5b571c366660f4b01b8ca53208794d0446edcfc0e7d457fb2b6a8. Simulator 8E7378D0-69AD-4CF5-8A40-7D53394CACF8 was deleted. That launch also did not capture a native method entry. The copy keeps rewritten crossgen-out DLL and dylib files when names collide with inputs. On 2026-10-16 the preserved simload A and B manifests were compared with that copy rule: Update.dll, Private.dll, IlOnlyHelper.dll and the owner dylib all matched, while the 4096-byte input Update.dll did not. Contract, AnchorHost and AnchorEntry were copied from crossgen-out but were not in those older file maps. New manifests hash those rewritten components too. No simulator was booted for this comparison. It is not a simulator receipt. When payload-files.txt is present, the iOS host source checks those hashes again before it loads the update or a listed dependency, and refuses an unlisted dependency. Payloads without that file keep the previous host behavior. eng/verify-ios-host-callback.py covers a matching list, an unlisted private file, and a changed private file on the desktop. On 2026-10-16 that host source was compiled with the pinned iOS simulator csc and only TrustedUpdate.Host.dll was replaced in a copy of the simload app. Host SHA-256 is 70574db7a3e66938d8ca0fffc37e8794910eafe77a62b89422e907cc43b944be. One iPhone 17 iOS 27 simulator process then printed HOST_ECHO=41, PRIVATE_VALUE=100, IL_HELPER_RESULT=307 and TRUSTED_UPDATE_SUCCESS version=A result=216. A second process with the private hash replaced by 64 zeroes printed TRUSTED_UPDATE_FAILURE and payload file hash mismatch: TrustedUpdate.Private.dll, with no success line. The private file itself stayed 38163d3c8ea5b571c366660f4b01b8ca53208794d0446edcfc0e7d457fb2b6a8. Simulator 76B8C584-77BC-47C0-819A-9A0590C71C7D was deleted. The same host binary then ran prepared B on a new iPhone 17 iOS 27 simulator. Process 25031 printed HOST_ECHO=41, PRIVATE_VALUE=200, IL_HELPER_RESULT=607 and TRUSTED_UPDATE_SUCCESS version=B result=216. Update.dll stayed d83ec82a13f71d54dc9817ffde348d30711a6145f12b59d803513a1ea8b373f5 and TrustedUpdate.B.r2r.dylib stayed e9dcf6ff668d3dbb14b242d2dfc3b64d605152ae06aab45430a2392215a1a589. Simulator 0DD4A1EB-5397-40CB-9174-9DDC48E50FD6 was deleted. Neither of those two launches captured a native method entry. A later capture with the same host binary did. Process 25456 on iPhone 17 iOS 27 hit Business.Execute in the downloaded TrustedUpdate.A.r2r.dylib: base 4676419584, PC 4676425056, end 4676425968, which is base+5472 through base+6384. The PC was inside the executable owner, the owner SHA-256 stayed 5287adf15b833579245ea02b78c33440333f6fde4a2a973153f26408486d9c89, and the console log had TRUSTED_UPDATE_SUCCESS version=A result=216 with PRIVATE_VALUE=100 and IL_HELPER_RESULT=307. lldb exited 0. Simulator 6619093B-C2E3-4B09-BE6C-18856A50C519 was deleted. B was then captured with the same host binary. Process 26080 on iPhone 17 iOS 27 hit Business.Execute in the downloaded TrustedUpdate.B.r2r.dylib: base 5557600256, PC 5557605728, end 5557606640, which is base+5472 through base+6384. The PC was inside the executable owner, the owner SHA-256 stayed e9dcf6ff668d3dbb14b242d2dfc3b64d605152ae06aab45430a2392215a1a589, and the console log had TRUSTED_UPDATE_SUCCESS version=B result=216 with PRIVATE_VALUE=200 and IL_HELPER_RESULT=607. lldb exited 0. Simulator 54A5D6C9-3DE0-4D3A-93E1-F9843D194A64 was deleted. The iOS host source now closes Echo and the delegate when Run returns, reuses an already loaded host contract, and eng/verify-ios-host-callback.py passed that closure on the desktop. That run is not a simulator receipt and does not replace the recorded A/B native entries. On 2026-10-16 the same host source was compiled with the pinned iOS simulator csc, replacing only TrustedUpdate.Host.dll in a copy of the simload app. One iPhone-17 iOS 27 simulator process then printed HOST_ECHO=41, HOST_DELEGATE=41, PRIVATE_VALUE=100, IL_HELPER_RESULT=307 and TRUSTED_UPDATE_SUCCESS version=A result=216. The owner dylib SHA-256 remained 5287adf15b833579245ea02b78c33440333f6fde4a2a973153f26408486d9c89. The simulator was deleted. The same host binary then ran prepared B on a new iPhone-17 iOS 27 simulator. Owner SHA-256 remained e9dcf6ff668d3dbb14b242d2dfc3b64d605152ae06aab45430a2392215a1a589, and the console showed HOST_ECHO=41, HOST_DELEGATE=41, PRIVATE_VALUE=200, IL_HELPER_RESULT=607 and TRUSTED_UPDATE_SUCCESS version=B result=216. That simulator was deleted too. With that same new host and the original entry assembly, lldb again hit Business.Execute in both downloaded owners. A: base 4392714240, PC 4392719712, end 4392720624. B: base 4448600064, PC 4448605536, end 4448606448. Both are base+5472, the breakpoint had one location, the PC was inside the executable owner, and the owner hashes were unchanged. A later capture with the fixed script wrote results.json for A: pid 21743, PC 5509076320 at base 5509070848 plus 5472, one executable owner hit, owner hash unchanged. A following capture started log stream before lldb. Its results.json has managedSuccess true from the console log and the native entry together: pid 22230, base 4386504704, PC 4386510176 (base plus 5472), owner hash unchanged, and TRUSTED_UPDATE_SUCCESS version=A result=216 with HOST_ECHO=41, HOST_DELEGATE=41, PRIVATE_VALUE=100 and IL_HELPER_RESULT=307. The simulator was deleted. The same capture for B then wrote managedSuccess true from the console log together with the native entry: pid 22667, base 4449386496, PC 4449391968 (base plus 5472), end 4449392880, owner hash e9dcf6ff668d3dbb14b242d2dfc3b64d605152ae06aab45430a2392215a1a589, PRIVATE_VALUE=200, IL_HELPER_RESULT=607 and TRUSTED_UPDATE_SUCCESS version=B result=216. That simulator was deleted. A separate IL probe, not the R2R business module, then ran on another iPhone-17 iOS 27 simulator with the same host binary. During Run it printed HOST_ECHO=41, HOST_DELEGATE=41, PROBE echo=42 callback=43 and TRUSTED_UPDATE_SUCCESS version=P result=85. After Run returned it printed LATE_ECHO_CLOSED and LATE_CALLBACK_CLOSED. That probe has no owner dylib and is not native-entry evidence. The simulator was deleted.


Step 1 now has a [Windows independent IL/R2R composition experiment](independent-r2r-composition.md)
with identical business sources, shared object/interface/delegate/generic calls,
A -> B -> A, private state reset, failure recovery and actual native R2R frame
evidence for independently compiled host/update/private methods. The IL-only
helper has positive interpreter-entry/bytecode evidence. Collectible contexts
retire successfully, but the pinned upstream runtime explicitly disables their
R2R bodies: native composition uses noncollectible controls and establishes no
native unloading. On that measured result, RuneCLR does not pursue unloadable hot-update R2R: an update that must be unloaded stays interpreted, and ordinary first-party execution does not repeatedly unload old assemblies.
Same-process multi-version residency is follow-up only when a product needs it, and it does not reopen collectible native R2R. The
reproduction driver records this distinction and returns 2 for the known blocker
after its execution/regression controls pass. No iOS delivery claim is added,
and no runtime patch was made.

On 2026-10-16, `py -3 eng/verify-trusted-composition.py --runtime E:/runtime --output artifacts/trusted-composition-20261016-desktop --allow-known-collectible-blocker` completed with standard output `PASS five functional/execution controls; BLOCKED combined collectible R2R acceptance`. Its `result.json` recorded `controlsPassed=true`, `milestoneComplete=false`, and `status=blocked-collectible-r2r`; the `r2r-native` report had `Passed=true` and the IL-only helper was interpreted. The object-identity sessions used version sequence `A,B,A,A,A` with `HostTouches=9`, `InterfaceCalls=9`, `DelegateCalls=9`, `GenericCalls=18`, and `HostIdentity=true`. Loader controls recorded `passed=true`, `rejected=2`, `recoveryContextsCollected=10`, and `originalInputsUnchanged=true`. The runtime was `runeclr/interpreter-baseline` at `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. This is not native R2R for collectible modules and is not iOS or physical-device evidence; launcher exit status is not a business-success signal.
The collectible rejection is ReadyToRunInfo::Initialize in src/coreclr/vm/readytoruninfo.cpp, which logs Ready to Run disabled - collectible module and returns NULL; ReadyToRun, InterpMode, and ReadyToRunExcludeList do not enable collectible modules alone. On that measured result, RuneCLR does not pursue unloadable hot-update R2R: an update that must be unloaded stays interpreted, and ordinary first-party execution does not repeatedly unload old assemblies.
The experimental ReadyToRunCollectible switch was not retained; E:/runtime stays the clean pinned commit 0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de, and the installed dotnet was not replaced.

On 2026-10-16, simulator directory `rerun-a9164cd-20261016-10` was checked with `python3 eng/verify-ios-trusted-update.py`. The verifier exited 0 with `passed=true` and `nativeExecutionProven=true`. A and B both recorded `RUNECLR_EXIT=0` and `TRUSTED_UPDATE_SUCCESS result=216`. This is an iOS simulator receipt, not a physical-device result.
A later clean checkout of c268026 reproduced that result as rerun-c268026-20261016-01. verify-ios-trusted-update.py exited 0 with passed=true and nativeExecutionProven=true. A and B both recorded RUNECLR_EXIT=0. Host.cs in that tree has no failure-type diagnostics. This is still an iOS 27 simulator receipt, not a physical-device result.
Measured cells and explicit non-results are listed in [compatibility-matrix.md](compatibility-matrix.md).

Proceed with the noncollectible native lane for iOS delivery. A first iOS run
may launch separate processes selecting A and B, and must verify startup
selection, unchanged host files, selected native and IL-helper entries, ordinary
failure diagnostics and next-start fallback. Resident native code through process
exit is normal in this mode; backgrounding, logout and re-entry are not process
exit. Keep basic single-version memory observation in the first run. A failed
version may remain resident after loading, so record the restart boundary and do
not equate disk-cache cleanup with unloading. Same-process version residency and
its growth costs are follow-up work when needed. Collectible interpretation
loading/recovery is already verified and need not be repeated.

The 2026-10-15 iOS simulator attempt did not reach native execution. Local
synthetic Mach-O preflight passed and is not a receipt. On the Mac, fixed-host
build, boot and install completed, then composite crossgen for version A hit
AccessViolationException (exit -6) while rewriting TrustedUpdate.Update.dll.
No owner dylib was linked or loaded, and no method entry was captured. See
docs/ios-trusted-update-simulator.md.

A later in-place isolation reproduced that access violation from a preserved
4096-byte Update.dll. The non-composite Mach-O attempt is only the compiler's
composite-only format rejection, not the same crash and not native execution.

Writing that same composite to a separate output directory then exited 0 and
left the 4096-byte input unchanged. The access violation is the in-place
rewrite, not evidence that composite Mach-O output cannot be produced. No
owner dylib was linked and no method entry was captured.

Version A's object has since been linked and ad-hoc signed as an iOS
Simulator dylib exporting _RTR_HEADER. Offline structure still does not prove
native execution.

The later simulator load mapped both downloaded owners and matched callback
path, hash and base, but recorded no native method entry. The capture breakpoint
was on anchor Driver.Run, not the update method. Native execution remains unproven.

A recapture placed the breakpoint on Business.Execute and still recorded no
PC. The dlopen callback can arm that breakpoint before the owner is mapped.

Arming Business.Execute after dlopen return then recorded one A-process PC at
that symbol's entry in the downloaded simulator dylib. B and the managed success
line remain unrecorded, so this is not the full two-version acceptance.

Version B then hit the same Business.Execute file offset in its own downloaded
dylib and process. Both simulator entries are recorded. The success line is
still absent, and device signing remains separate.

The A managed path then completed: stderr, not stdout, contains
TRUSTED_UPDATE_SUCCESS version=A result=216, and the preceding echo, callback
and business values match the source formulas. B's stderr now contains TRUSTED_UPDATE_SUCCESS version=B result=216, PRIVATE_VALUE=200 and IL_HELPER_RESULT=607.









The desktop baseline is published and merged into `main` at
`7c11bb656f7d733de0e767f2ea87a278a6aaead3`; #1 is closed. Its
[Windows/Linux/macOS CI run](https://github.com/ReneeGA2020/RuneCLR/actions/runs/38697667369)
passed on that same commit. This is desktop regression evidence.

Next work should establish trusted hot-update integration: a minimal
engine-independent host, same-source interpreted IL/trusted R2R builds with
independent R2R update/non-update module composition and post-install delivery,
direct-object and reference-lifetime coverage, and a language/library support
matrix. Complete physical iOS acceptance when a target is available. These
increments do not depend on completing the UGC budget/security/memory profile.
See the [current work order](work-sequence.md) and [roadmap](roadmap.md).

The evidence below records distinct configurations and historical increments;
older next-step statements apply to their date/configuration, not the current
product-wide priority. No experiment was rerun for the positioning update.

## Latest verified increments

The operator source compiler now uses the selected SDK Roslyn's latest stable
language version instead of fixing C# 12. Its regression covers C# 13 params
collections and C# 14 field-backed properties; the corresponding end-to-end
package fixture checks execution and repeated retirement. The gameplay gate
accepts the compiler's `ParamCollectionAttribute` metadata marker. Historical
reports below retain the compiler configuration actually used for those runs;
their hashes/results are not retroactively updated.
Fresh Windows RC1 verification passes 37/37 lifecycle, 85/85 packaging, 15/15
synchronous and 22/22 pumped player cases, plus six sample collections. The
modern package fixture executes and collects three times; no new mobile
interpreter result is claimed.

The [controlled-package/pumped/native-budget combination](controlled-package-native-budget.md)
now passes 33/33 on the matching Windows 20405f7 Release runtime. Twenty-five
native-budget sessions cover constructor/start/tick/stop exhaustion, cumulative
finite ticks, catch/resume suppression, bounded private finally helpers, and
repeated fresh-package recovery. Retained stopped sessions do not prevent
collection; execution and cleanup ledgers conserve their exact limits. Stock
SDK refusal occurs before author files/assemblies. All ninety-two recorded
inputs and runtime provenance remain unchanged; ordinary 15/22-case lanes and
full 37/84 lifecycle/packaging verification remain passing. New fixture flags
preserve the default nine and pumped twelve-package collections. No runtime
source changed. Next: mobile controlled-package budgets, game-facing
event/resource ownership, and real-device acceptance.

The updated [iOS simulator pumped-budget application](ios-pumped-budget-acceptance.md)
also passes 16 cases / 74 collected contexts with the current managed host.
A new trusted R2R composite uses the preserved 3126bbc9 Release native runtime;
two author IL files are compiled after installation. Six host returns precede
tick-seven cumulative exhaustion. Independent downloaded-source, archive,
installed-image, process and all-row ledger review passes. The owned simulator
is deleted. This diagnostic raw-IL lane adds no controlled-package mobile
acceptance, new method-entry samples, Android update, or physical-device result.

Controlled-package [host-pumped acceptance](package-execution-tests.md) now
passes 22/22 on Windows stock RC1 and matching 20405f7 Release required
interpretation; synchronous controls stay 15/15. New controlled fixtures observe
frame deltas and tick/stop failures. The suite also checks overlapping private
versions, retirement while stopped sessions remain retained, prevalidated
package tampering rejected before author loading, and recovery. All 69 recorded
inputs and exact Release provenance remain unchanged. The full verify command
passes 37 lifecycle/84 packaging/15 synchronous/22 pumped cases and six sample
collections, with zero build warnings/errors. CI now includes the pumped lanes;
the published baseline's hosted CI has since passed as linked above. The portable
mobile budget adapter compiles again
after linking its missing observer dependency, and its optional pumped route
passes local Windows 16/74 plus default 15/73. Those Windows adapter smoke
results precede the actual iOS application acceptance above. Updated Android
applications and mobile controlled-package native budgets remain follow-ups.

The initial [host-pumped session API](host-pumped-sessions.md) now lets a game
loop call `Start`/`Tick`/`Stop` with host-supplied deltas. Failed callbacks close
the session automatically; stopped sessions clear author/context references.
`MapRunner.Run` now wraps the same lifecycle and retains its finite tick count.
Fresh private RC1 verification passes zero build warnings/errors, 37/37 lifecycle,
84/84 packaging, 15/15 player and both sample paths (six collections). The
matching Windows 20405f7 Release required-interpreter lane passes 37/37 with
43 unchanged input hashes. Native pumped budgets pass 16 cases/74 collections:
six successful host returns precede exact cumulative 8192 termination on tick 7.
The preserved synchronous 15/73 and ordinary SDK 20-collection controls also pass;
independent source/runtime/process/receipt review passes all 167 probe collections.
No runtime source changed. Next independent host work includes game-facing
events/resources. Matching Android and physical-device acceptance of this new
host API remain outstanding; the updated iOS simulator lane is recorded above.

The latest [open-delegate interpreter capture](ios-open-delegate-entry-acceptance.md)
now passes all three prepared entry paths on the iOS ARM64 simulator. Two
DLLs compiled after diagnostic installation cover the same nine actual method
groups; the original private closure now enters through delegate child
dispatch in phase1 cleanup. The full15-case/73-collection budget suite, target
exit0, unchanged input inventories and owned simulator deletion all pass.
Portable actual-byte review and23 additional synthetic controls pass; the
[previous two-path capture](ios-fresh-author-entry-acceptance.md) and43 live
driver controls are preserved. This uses unchanged runtime/host/capture
products and exact accounting. Physical-device execution/entry evidence is
still required: the06:12 UTC read-only refresh found zero reachable devices.
Independent roadmap work can continue while the physical lane is unavailable.

The matching Windows 099dacd Release baseline now has independent
[terminal/finalizer/host acceptance](windows-release-budget-acceptance.md):
44 terminal lanes/84 rows, nine finalizer recovery cases with six original
fatal-exception controls, and fifteen host-budget cases/73 collected contexts.
Twenty-one semantic corruption controls reject altered results. Selected
post-invocation entries are recorded; fatal finalizers and host author methods
do not have individual entry samples, and no full invocation trace is claimed.
The root offline recheck (archival/local evidence: `../artifacts/release-budget-functional/budget-root-review-20261014-attempt1/results.json`)
passes against the unchanged native/CoreLib/compiler/source/layout bindings.

The same Release layout also passes [production and official controls](windows-release-production.md):
24/24 lifecycle, 15/15 package execution, sample and post-host-build IL
collections, controlled source/import/source static reset, and four unchanged
official loader tests. Ordinary private RC1 verification was rerun on
2026-10-14: zero build warnings/errors, 24/24 lifecycle, 84/84 packaging,
15/15 player and all three sample collections.

The new [joined-worker experiment](windows-terminal-concurrency.md) passes
36 owned Release processes and 72 collections. Two/four trusted host threads
share exactly 2048 admitted dispatches; finite cleanup completes and the small
cleanup reserve stops at 64. High-budget/diagnostic post-gate counts equal
two/four times the single-worker reference. Independent raw/PE/ledger review
passes 156 selected entries and four additional corruption controls. This is
controlled joined-worker coverage, not exhaustive races or an author thread API.

The smallest [terminal-counter optimization](windows-budget-increment-hotpath.md)
is now implemented on the separate direct child20405f7. A matching Windows
Release build passes with zero warnings/errors and527 bound layout files.
[Fresh budget acceptance](windows-budget-increment-acceptance.md) and
[joined-worker/production controls](windows-budget-increment-concurrency.md)
pass while preserving diagnostic saturation, admission/phase checks and owner
lifetime. Independent actual PE/PDB review verifies five locked RMWs on the
normal admitted path, down from six, and single increments for execution and
cleanup. The original099 source/products/evidence remain intact.

The [same-machine bracketed measurement](windows-budget-increment-performance.md)
now passes three eight-process runs with identical host/author/images and312
collections. Budgeted callback medians75.679/76.880ms in the two baseline runs
become64.534ms in the candidate:14.73-16.06% less time for this kernel.
Independent raw reviews pass12 corruption controls per run. The configured
candidate still costs4.68x its own no-config median; this is not full
instrumentation overhead or real-game/mobile performance.

The exact minimal change now has fresh [matching mobile core builds](mobile-budget-increment-builds.md)
at composed tree91673a7: iOS simulator ARM64 Release and Android x64 Release
both pass exit0 with zero warnings/errors, after independent source37/seven-patch
composition proof. iOS retains the private bridges through three CoreLib
metadata stages and binds ten native compile owners. Android binds six native
compile owners and charged computed-goto preprocessing. The later Android
[ABI/framework layout](android-budget-increment-layout.md) passes three CoreLib
stages and a fresh matching composite. Downloaded receipt archives and
individual-file SHA/size checks preserve both build results.

The new [iOS application acceptance](ios-budget-increment-acceptance.md)
passes15 scenarios/73 context collections without a debugger and in a separate
entry run, with147 selected samples across nine requested method groups.
An independent root review (archival/local evidence: `../artifacts/mobile-budget-increment/root-ios-acceptance-review-20261014-attempt1/results.json`)
recomputes entries, directly reads actual ARM64 bytes and signed/unsigned
sections, and rejects five corruption controls. New iOS child dispatch uses
w25; its new observer binds the actual change while retaining the old tools.

The new [Android APK acceptance](android-budget-increment-acceptance.md)
passes15 scenarios/73 context collections with Java/native/managed identity,
zero exits and203 identical installed-before/after hashes. Post-install author
IL stays byte-identical. ADB10055 during asset transfer and later observer
precheck/empty-line failures are retained; recovery preserves already transferred
bytes and the original APK. The strict later audit passes15 corruption controls
and mobileVerified=true. New Android method-entry sampling is now accepted below.
An independent APK review (archival/local evidence: `../artifacts/mobile-budget-increment/root-android-acceptance-review-20261014-attempt1/results.json`)
rechecks the actual archive/APK, complete installed observations and four
transport corruption controls; its
scenario supplement (archival/local evidence: `../artifacts/mobile-budget-increment/root-android-acceptance-review-20261014-attempt1/supplement-results.json`)
matches all 73 rows, exact logs, recovery roles and mapped native paths.
The [new Android observer preparation](android-budget-increment-entry-preparation.md)
now passes actual ELF/DWARF/source binding and five rejection controls. Its
child contract changes to PC 0x3b0aff, opcode pointer r14 and rbp-0xe48.
An independent ELF review (archival/local evidence: `../artifacts/mobile-budget-increment/root-android-entry-contract-review-20261014-attempt1/results.json`)
matches actual native bytes, 34 instructions, five dependency hashes and
three additional code alterations.
The fresh [gated Android entry acceptance](android-budget-increment-entry-acceptance.md)
now samples178 interpreter entries across all nine requested author groups,
including live ReInit/reload byte checks. The capture completes15/73; the same
APK with the gate absent and no debugger independently passes15/73 and203
unchanged installed inputs. The independent offline cross-check (archival/local evidence: `../artifacts/mobile-budget-increment/root-android-entry-review-20261014-attempt2/results.json`)
recomputes raw samples/PE identities, APK native bytes and two native/debug
GNU build-ID pairs, matches three emitted code pieces, rejects four altered
samples and verifies both ledgers plus recorded cleanup. This is sampled
emulator evidence, not complete invocation capture or physical-device proof.
Owned applications/simulators/emulators have completed cleanup.

The requested [stock Lua budget reference](lua-budget-overhead.md) now measures
the same-machine arithmetic kernel across16 processes/144 timed samples.
Native C count hooks every1/100/1000 traced instructions cost6.37x/2.49x/2.44x
their no-hook median. Independent raw-log/source review and24 rejection/recovery
controls pass. Per-state non-atomic hooks and catchable Lua errors do not have
the same enforcement semantics as RuneCLR; these ratios are reference points,
not matched VM rankings or representative game costs.

The initial [100/1000 batching review](budget-batching-experiment.md)
recorded options and acceptance boundaries. It distinguishes
batched counter settlement from less frequent terminal checks, including shared
worker reservations and actual admitted-dispatch accounting. The implemented
interval candidate and its actual runs are recorded below.
The later source review identifies an acquire phase-load precursor and
executed-only batching boundaries. The precursor is now implemented as the
isolated opt-in child a24661d of20405f7, with a fresh matching Windows x64
Release build. [Actual PE/PDB review](windows-phase-load-hotpath.md) passes
305 instruction-byte matches and seven alteration controls: normal ON/OFF
paths have three/five locked RMWs; cleanup has three/six. The compiler emits
out-of-line Phase calls and stack accesses, so fewer locks do not establish
a timing gain. [ON/OFF terminal, finalizer, host, joined-worker and production
suites](windows-phase-load-acceptance.md) and their independent audits pass.
The later [four-process live witness](windows-phase-load-live-witness.md)
observes actual normal-dispatch callers, the immutable meter flag and matching
ON load/OFF locked-CAS bytes. Normal return53-op and terminal2048-op ledgers
and all four collections pass;24 combined alteration controls reject. This
samples one phase0 branch per process, not every dispatch or cleanup phase.
All owned debugger/target processes have exited. The later
[bracketed phase-load measurement](windows-phase-load-performance.md) now
passes four independent raw audits and a cross-run comparison:32 processes,
416 collections,24 identical host/author source files and20 identical managed
inventory files. Budgeted callback medians63.87670/64.46335ms in the parent
brackets become47.67865ms with phase-load ON:25.36-26.04% less elapsed time.
The current configured/no-config ratio is4.07x; the current parent brackets
are5.36x/5.35x. These are new arithmetic-kernel measurements, separate from
the earlier4.68x result. The child OFF result is66.83670ms; its new calls and
switch selection are not machine-code identical to the parent.
At that precursor stage, the executed-only batching design still had
pending-count flush requirements. A separate
source-only alternative review (archival/local evidence: `../artifacts/budget-batching/derived-ledger-review-20261014-attempt1/review.md`)
supports deriving terminal admitted counts from initial allowance minus
remaining, avoiding the separate executed increment without batch flushes.
Diagnostic saturation must retain its existing independent counter. That
review predates implementation; it identifies the changed concurrent scalar
observation timing and required storage/layout choice. Its algebra checks
remain distinct from the later native header evidence below.
The [exported phase-load patch](runtime-patch-reproduction.md) also reconstructs
the exact36-file candidate and retains the previous patch inventories.

The isolated default-OFF [terminal derived-ledger candidate](windows-derived-ledger-candidate.md)
is now implemented and committed as29ff781, a direct child ofa24661d. It
preserves diagnostic saturation and per-opcode admission, and appends two
immutable initial allowances: meter size64/alignment8, old offsets unchanged.
The actual header passes41 native cases/807 checks, including real successful
CAS pauses and trusted2/4-thread exact ledgers. The matching fresh Windows x64
Release build now passes with zero warnings/errors; independent source,
527-file layout and five PE/PDB-pair review also pass. Full16-command ON/OFF
functional acceptance now passes, including terminal/finalizer/host recovery,
joined workers and production controls. Actual static native review confirms
two locked RMWs on enabled admission paths versus three disabled. Four new
64-byte live witnesses pass4/4 collections and24 rejected alterations. The
performance freeze passes785 inputs and19 rejected alterations. The
[new bracketed timing](windows-derived-ledger-performance.md) passes32
distinct processes/416 collections and unchanged24 common sources/20 managed
products. ON configured callback time is41.65925ms, down8.1%/9.6% versus
the new parents; its configured/no-config ratio is3.60x (parents3.84x/3.87x).
The new [representative entity/API controls](representative-budget-workloads.md)
now pass12 owned Windows Release processes/60 collections with90 rejected
alterations and1111 bound inputs. Exact callback/session checksums, native
ledgers, static reset and resource releases agree across parent/child-OFF/ON;
both new projects build with zero warnings/errors. A separate review confirms
actual launch-path/switch binding and rejects24 alternate-layout controls.
These one-sample functional runs do not establish representative performance.
The later [representative low-budget recovery](representative-budget-workloads.md#low-budget-termination-and-recovery)
passes three parent/OFF/ON processes,42 native terminations followed by42
same-process fresh-session recoveries,84 collected contexts and24 rejected
alterations. Seven exact allowances preserve terminal ledgers, skip OnStop
after termination and release observed host entities; every recovery resets
statics and matches the original checksum/689851 dispatches. This does not
add catch/filter/finally, concurrent, live-entry or mobile evidence.
The user explicitly requested the actual100/1000 comparison rather than further
precursor work. The [interval candidate](budget-interval-candidate.md) is now
implemented asd0da7df, a direct child of29ff. Actual native tests pass35 cases/
10017 checks, including full100/1000 chunks and tail7. A mixed-counter saturation
race is corrected; independent final patch review and19 source controls pass.
The matching Windows x64 Release build now passes with zero warnings/errors,
37 patch sources, seven compiled owners and 527 matching layout files. Actual
small-budget acceptance passes five processes, 168 collections and 20 corruption
controls; partial counts, catch suppression and same-process recovery agree.
High-budget controls pass all four configurations across three workloads:
12 processes and 84 collections with exact completed ledgers/checksums.
The [actual same-binary timing](budget-interval-performance.md) now passes
60 processes/780 collections and independent raw review. Arithmetic Exact0
40.5813ms/2.53x becomes 19.8683ms/1.26x at100 and 19.2515ms/1.22x at1000.
Entities regress5-6%; host APIs improve about8%. Exact0 disables derived-ledger
optimization. The later [best-exact ON control](budget-batch-best-exact.md)
passes48 processes/624 collections and1008 independent sample checks:
arithmetic saves44%, entities regress15-17%, and host-API gains shrink to2%.
N1000 provides less than1% additional callback savings versus N100 in all
three workloads. Exact remains the default; N100 stays opt-in.
Actual cadence samples also pass full100/1000 and partial14 settlements, native
interval values and matching InterpExecMethod stacks; 14 contexts collect and
all owned debuggers exit. See the interval candidate for raw evidence.
The separate
representative exact-only bracket is prepared but paused for this requested
experiment. This experimental post-admission interval design permits bounded
single-worker excess and does not replace the accepted exact products.
The [mobile batching source preparation](mobile-batch-build-preparation.md)
now passes38 LF sources/10 patches/21 rejection controls and three identical
composition trees. New mobile commit3126bbc/tree710936a adds only CIDv2 to
Windowsd0da7df. Root independently matches actual Git/working bytes and validates
the small transfer bundle. The [fresh matching mobile builds](mobile-batch-builds.md)
now pass iOS simulator ARM64 and Android x64 Release with exit0 and zero
warnings/errors. Separate38/10/meter72 adapters preserve the frozen37/9 tools.
The root rechecks all69 archived receipt members and both actual preprocessing
outputs: exact safe47, unsafe/trap flush, cleanup exact and interval offset64.
The new iOS boundary application produces184 R2R components; a launch-record
signed/unsigned native hash issue is fixed through separate validated metadata
without rebuilding the app. The actual iOS simulator five-lane run now passes
five fresh processes/168 collections, termination/catch suppression/cleanup,
same-process recovery and simulator shutdown. The
root independent iOS audit (archival/local evidence: `../artifacts/mobile-budget-batching/root-ios-boundary-review-20261015-attempt1/results.json`)
matches57 receipt members and rejects25 altered actual-lane controls.
N100/N1000 partial settlements match their exact calibration controls.
The new matching Android boundary layout now passes184 trusted IL inputs/185
actual Linux x64 R2R outputs and retained CoreLib private ABI/MVID checks. Its
second fresh APK passes five distinct processes,169 observations/168
collections, three actual zero HRESULTs, late unchanged author IL, installed
byte checks and same-process recovery. The
root Android audit (archival/local evidence: `../artifacts/mobile-budget-batching/root-android-boundary-review-20261015-attempt1/results.json`)
rechecks raw APK/native/row evidence and rejects30 altered receipts. The initial
failed APK and tool fixes remain recorded; both owned apps and emulator5556 are
cleaned up.
The new separate iOS exact-entry capture now covers four direct author methods
at filePC0x28a08c with loaded bytes, six live DWARF layouts and original
MethodDef/MVID/path bindings. The
root iOS entry review (archival/local evidence: `../artifacts/mobile-budget-batching/root-ios-entry-capture-review-20261015-attempt1/results.json`)
reconciles52 raw payloads,376 bounded hits/four samples/zero errors, normal
target exit0 and35 completed collections; eight actual-entry alterations are
rejected. The original normal run/app are unchanged and the separate simulator
is shut down. The later Android initial-entry capture now has
independent root acceptance (archival/local evidence: `../artifacts/mobile-budget-batching/root-android-batch-entry-review-20261015-attempt1/results.json`):
four author methods/ten hits,35 semantic rows/35 collections,40 raw hashes and
19 symbol/source payloads verified, eight altered samples rejected. Actual
ELF entry0x3f53a0 and loaded complete metadata are bound; managed/instrumentation
and three HRESULTs are zero. Debugger target exit9 remains explicit; the
independent normal five-process baseline is unchanged. Owned APK/forward/emulator
are cleaned up. Mobile long-kernel full/partial settlement cadence, timing and
physical-device validation remain next.
The [portable long-kernel inputs](mobile-batch-builds.md#long-kernel-inputs) now
compile with zero warnings/errors and keep the accepted author/contract IL
unchanged. Their new Windows private-runtime sanity passes two processes/eight
callbacks/two collections and20 rejected alterations at N1000, with no timings
or mobile invocation claim. Root independently verifies the archive, compile
and raw process/ledger receipts. Use these inputs for the next separate mobile
full/partial settlement capture; preserve both accepted boundary apps/runs.
The later [actual iOS long-kernel acceptance](mobile-batch-builds.md#ios-long-kernel-settlements)
now passes two independent processes: N100 full100/100 and tail14/14; N1000
full1000/1000 and tail14/14. Root reconciles245 archived payloads, original
loaded instructions/eight settlement samples and16 callback rows/four
collections, with twelve altered-sample rejections. Both targets exit0 and
owned simulators/processes are shut down. The actual tail14 differs from the
total dispatch remainder16; required direct-charge boundaries remain involved.
Keep debugger cadence records separate from the next independent timing run.
The [mobile measurement follow-up](mobile-batch-measurement.md) now has a strict
standalone scalar reviewer (two retained observations/eight callbacks and54
rejections) and a frozen direct-callback timing variant. The timing variant's
small Windows sanity passes two processes/eight callbacks/two collections;
root independently checks ten frozen files/twelve archive members, raw
timestamp conversion and20 altered receipts. These are preparation results,
with no mobile timing ratio. Best exact comparison requires interval0/derived1;
each meter-free control can select the same profile as its paired budget run.
The later [actual iOS simulator timing](mobile-batch-measurement.md#actual-ios-simulator-timing---2026-10-15)
now completes 16 debugger-free processes, 144 measured callbacks after 48
warmups and 16 collections. Root independently replays original native launch
logs, unchanged installed hashes, 35 quiet process snapshots, every scalar
ledger and raw timestamp. Configured arithmetic medians are 74.153/76.427ms in
the exact brackets, 23.459ms at N100 and 15.942ms at N1000. These observed
reductions remain distinct from stable overhead ratios: no-config bracket
drift is 28.00%, and N1000 paired ratios 0.797/1.144 straddle 1. Keep exact
default/N100 opt-in; preserve this run's variance and repeat timing before
selecting N1000. Subsequent Android long-kernel capture and mobile timing
follow-ups are recorded below; physical-device validation remains outstanding. The owned iOS timing
simulator and build/run/transfer processes are stopped.
The [31-sample iOS repeat](mobile-batch-measurement.md#ios-timing-repeat---31-samples-per-process)
now passes another 16 fresh processes, 496 measured callbacks, 48 warmups,
16 collections and 35 quiet snapshots after 30.005 seconds of settling, using
the identical application/runtime/author. N100/N1000 configured medians are
14.718/12.795ms; N1000's paired budget/no-config ratios both become about
1.54. Exact before/after medians are 79.705/71.324ms, with -10.51% configured
and -28.08% no-config drift. Preserve both runs and their variability;
the measured N1000-over-N100 reduction changes from 32.04% to 13.06%.
The [Android long-kernel follow-up](mobile-batch-measurement.md#android-long-kernel-capture)
also captures full100/100 or1000/1000 and tail14/14. Both lanes complete
eight callbacks/two collections and same-process recovery. The original
controller's memory-bundle Location-null review failure is retained;
external actual installed-contract binding plus strict scalar replay now
passes both lanes. Independent live cadence review now also passes all eight
settlements against actual ELF call/entry bytes, true stack return PCs,
loaded author metadata and the owning binder meter, with observations disabled
after coverage. Method entry and batch path are verified for this sample set.
Managed/instrumentation/HRESULTs are zero, while debugger target exit9
remains explicit. Owned APK/emulator/forwards are cleaned up. Independent
Android timing now also completes one debugger-free 16-process matrix with
496 measured callbacks/48 warmups/16 collections. Root and independent raw
reviews bind native launch/settings, 201 unchanged installed products,
executable native maps, all ticks/ledgers, 33 quiet snapshots and cleanup.
The [Android timing results](mobile-batch-measurement.md#actual-android-emulator-timing---2026-10-15)
give exact before/after 35.527/34.916ms, N100 20.062ms and N1000 19.875ms;
no-config medians remain 18.328-18.602ms. Paired budget/no-config ratios are
about 1.90-1.98 exact, 1.09-1.10 N100 and 1.075-1.077 N1000. Exact bracket drift
is -1.72% configured/+0.19% no-config. The N1000 versus N100 pooled change
is only 0.93%, with opposite per-process comparison directions; keep exact
default/N100 opt-in. These are arithmetic-kernel emulator observations.
The [separate iOS device runtime build](ios-device-batch-build.md) also now
completes actual ios.arm64.Release with build exit0/zero warnings/errors,
iphoneos sysroot and Mach-O platform2/min15.3. Its raw native/CoreLib/compiler
products are retained separately from the simulator. Independent raw review
passes all 137 payloads, eight device/two Mac compile owners and 52 private
ABI methods in each of three CoreLib stages. The subsequent
[device framework](ios-device-batch-framework.md) completes 181 raw/R2R
components and the iPhoneOS ARM64/min15.3 unsigned composite. Root checks
all 952 archive payloads; independent semantic review also passes all181
raw/R2R MVID/method metadata pairs,52 private ABI entries, actual package-native
selection and device compile commands. The matching application is accepted
below; reachable device/signing and physical execution remain outstanding.
The [device application preparation](ios-device-application-preparation.md)
now checks the official unsigned build path, actual device runtime inputs and
fixed 15-case/73-context production harness. Fresh author IL compilation passes
two independent raw-Roslyn invocations with distinct hashes/MVIDs; the desktop
finite Normal control passes 20 sessions/20 collections, with four rejection
controls. No device host binding or physical execution is claimed. A separate
matching libraries/framework build now succeeds: the original libraries build
passes zero warnings/errors, and a continuation completes deps/crossgen/link
without rerunning successful stages. Two local layout-driver failures remain
preserved. The later device-bundle guard review found and corrected acceptance
of a dylib as the main executable and missing signature rejection. Ten
independent parser/source-gate controls pass, and the strengthened source
preflight rerun also passes platform2 and the fixed15/73 inputs. Actual
physical execution remains unperformed.
The [matching unsigned application experiment](ios-device-application-build.md)
now completes from one supervised launch: four stages exit0/empty stderr,
186 new raw/R2R components,199 app files and an unsigned device ARM64 UIKit
main plus ten dylibs. Independent whole-metadata/IL/EH/initialized-data,52 ABI,
native/deps and source-binding reviews pass. All build/transfer processes exit,
and the owned-group timeout fix passes a real child-process control. Actual
post-build author compilation and independent199-file/time/compiler/IL binding
pass, with three corruption rejections and20 stock Normal sessions/collections.
The offline physical-run plan also passes with fresh DLL hashes/MVIDs, fixed
15/73 cases and actual devicectl help bindings. No application was signed,
installed or run on a physical device. Next: reachable device/profile, actual
installation/post-install IL readback, recovery and method-entry acceptance.
The [offline device-result auditor](ios-device-application-build.md#offline-lifecycle-result-auditor)
now passes an actual Mac replay of historical simulator15/73 rows with13
corruption controls. The new physical plan rejects the old launch nonce; a
clearly synthetic matching plan passes19 controls including six plan changes.
Original receipt hashes are unchanged. The auditor deliberately leaves device,
installed-host, delivered-author and interpreter-entry proof false; this is
tool validation against historical rows, not a new device run.
Normal private RC1 verification on2026-10-15 also passes zero build warnings
and errors,24/24 lifecycle,84/84 packaging,15/15 package execution and all three
sample collections.
The [matching mobile derived-ledger composition](mobile-derived-ledger-builds.md)
now passes37 exact LF sources/nine patches/21 rejected alterations and three
independent Git-index trees. New mobile commit2d86588/tree3292fc9 adds only
CIDv2 to Windows29ff. The fresh ARM64 iOS simulator Release build passes
exit0/zero warnings/errors, ten native compile owners and three CoreLib
metadata stages. Downloaded65-member receipts and37 source hashes pass
separate root offline reconciliation. Android x64 Release also passes
exit0/zero warnings/errors, six native compile owners and actual charged
computed-goto/meter64 preprocessing after independently checked preparation.
Its later metadata stage passes four PE observations/three typed queries and
five rejection controls. The fresh matching framework composite passes185
original IL inputs/186 PE outputs,200 products and five layout controls.
The [fresh iOS derived-ledger application](ios-derived-ledger-acceptance.md)
passes15 scenarios/73 collections without a debugger, including terminal
cleanup and same-process recovery. Root independently reconciles132/14/39
covered archive members for iOS/Android metadata/layout plus their manifests,
and rechecks all73 iOS rows with15 rejection controls. Actual optimized-branch
and method-entry sampling remain unperformed for this candidate. Android APK
read-only preparation passes; its four new adapters and execution remain next.
The representative performance preparation (archival/local evidence: `../artifacts/representative-budget/performance-preparation-20261014-attempt2/preparation.json`)
freezes1324 inputs including the original1111 and20 byte-identical managed
files,64 launch lanes and832 expected collections. Forty synthetic corruption
controls pass; preparation/selftest alone do not constitute measured timings.
A fresh unchanged-driver preparation on2026-10-15 passes the same input/plan
and control counts at
`D:/RuneCLR-Android/representative-budget/performance-preparation-20261015-attempt1`.
Its single64-process representative measurement run and original/independent
raw reviews now pass832 collections and576 callback/576 session samples.
Configured entity/API callbacks with exact derived accounting take9.61-9.83%
and8.08-8.25% less time than both parent endpoints. Child ON configured/no-config
pooled ratios remain3.560x/2.930x; no-config still retains instrumentation.
See the [measured scopes and process variation](representative-budget-workloads.md#measured-performance-and-scope).
The separate100/1000 measurements are already complete and retain distinct
same-binary comparisons. The latest read-only
physical-device refresh still reports zero reachable targets and zero matching
bundle/device/signing-profile combinations; see the readiness record.
The [offline device entry preparation](ios-device-entry-preparation.md) now
passes actual ARM64/DWARF/author binding for nine method groups,80 instructions
and13 rejection controls. Independent local native-byte/subtree/metadata review
also passes. The device frame spill offset is152, different from the older
simulator; the contextual DWARF interval excludes the proposed capture PC.
Live registers and physical method entries remain unverified.
The new fresh-author simulator application uncovered our minimal UIKit main's
missing scene lifecycle on iOS27: its first process crashed before CoreCLR
initialization, despite launch-tool exit0. The original failed app, fresh IL,
crash and cleanup receipts are preserved. A separately frozen scene-only
repair retains186 R2R components and runtime bytes; after its actual
installation/empty-author readback a second new author pair is compiled and
independently bound. Its sole debugger-free
[fresh-author simulator run](ios-fresh-author-simulator.md) now passes15/73,
including40 recovery contexts, six exact native markers and zero native/managed
exits. Root actual-row review passes13 corruption controls and separately
checks200 unchanged installed files, both delivered author DLLs and completed
owned simulator deletion. Full independent186-component/11-native/38-source
composition/run review now also passes, with63 altered-input controls; the
original UIKit crash has separate independent IPS/identity/time review and
six rejection controls. The new offline simulator observer preparation also
passes nine method bindings and13 in-memory controls; it creates no target
process. Method-entry sampling and physical execution remain unperformed. The original
unsigned [device application](ios-device-application-build.md#scene-lifecycle-follow-up)
now also has a separately built unsigned scene-aware child: source/eight-control
preflight and one actual iphoneos wrapper compile/link pass, preserving197
non-wrapper files and all186 R2R components. The later
[complete child acceptance](ios-device-scene-acceptance.md) now downloads all199
files and independently verifies197 protected bytes,186 canonical raw/R2R
metadata/IL/EH/fields and11 unsigned device native images, with12 alteration
controls. Two real new author compiler processes and the scene-aware binding
review pass against its199 unchanged files; nine copied provenance controls
reject stale host/author/build inputs. The new physical run/observer plan still
needs this child/pair's identities. The latest read-only device refresh at
2026-10-15 05:24 China time still has zero reachable targets and zero matching
bundle/device/development-identity profile intersections.
Sampler source review confirms internal child methods can remain in the same
`InterpExecMethod` loop. The new diagnostic sampler therefore needs separate
actual child-dispatch PC/DWARF/register binding as well as function entry;
the [ordinary-child offline preparation](ios-fresh-author-entry-preparation.md)
now binds actual PC0x2e7b0c/frame spill x19+0x98 and passes36 synthetic controls.
Delegate child dispatch and the two private cleanup-phase1 groups remain
pending; `CAPTURE_READY=False` prevents installation/launch/attach while allowing
already-owned failure cleanup. Independent static/guard review passes12 controls.
Frozen plan2 and
the later bounded-query draft remain distinct. No new target process was
created, and this preparation is not accepted as nine-group execution coverage.
The subsequent phase-aware v2 sampler source adds separate function, ordinary
child and delegate-child contracts and a phase1 map for the two private cleanup
methods. Its independent source/config review passes17 checks and10 mutation
controls; a read-only plan now binds the 3 path/ABI contracts and 9-method
phase map. A separate static read binds all three 64-byte windows to the
matching native SHA/UUID; live-register and loaded-image evidence remain open.
CAPTURE_READY=False still
rejects install/run before any host stage, so no v2 target or method entry has
been executed.
Preserve the accepted per-opcode runtime and earlier mobile execution evidence.
New mobile application entry checks, Android recovery and the
[unreachable physical iOS target](ios-device-readiness.md) remain open.

## Established baseline and later increments

The 2026-10-13 [matching mobile budget preparation](mobile-instruction-budget-builds.md)
combines Windows099 terminal/finalizer source with only CID v2, independently
verified as tree b54537ff42a066e41a01ea611a21f2e5e49934a1. A fresh iOS simulator
ARM64 and Android x64 Release runtime/CoreLib/compiler builds pass with exact
private bridge metadata retained and actual computed-goto charging compiled.
Android's original checker failure is preserved alongside a separate passing
review of the same products; the future observer is corrected.
The fixed mobile adapter has actually passed fifteen cases and73
context collections in one desktop process, using unchanged author IL. This
is desktop control evidence. The later
[actual mobile increment](mobile-host-budget-acceptance.md) passes the iOS
simulator15-case/73-context budget run with native completion and independent
row/raw/source review. A second independent normal run now samples installed
before/after inventories: 200 app files and two author DLLs match, and strict
root/independent audits pass mobileVerified=true. A separate iOS debugger run
now passes 147 valid entry samples across nine requested author method groups,
with raw DWARF/PE/bytecode review and four corruption controls. Android budget
also passes [nine-group native sampling](android-budget-entry-acceptance.md):
178 samples, zero observer errors, independent/root reviews and a separate
same-APK gate-off15/73 run. Neither platform trace is exhaustive invocation
coverage. Android also has a strict emulator APK audit for the actual
15-case/73-context run, including dual-stream and installed-inventory binding.
Physical devices remain outstanding.
The later [Android budget debugger preparation](android-budget-entry-preparation.md)
passes pre-init attach/read/detach, resumed15/73 execution and203 unchanged
installed hashes on a fresh gated APK; matching native symbols/source are
locally verified. Its subsequent entry/normal acceptance is recorded above;
owned app/emulator/forward are cleared.

The [configured-budget cost experiment](budget-overhead.md) now compares the
same required-interpreter author IL with no meter and a high terminal allowance
on Windows 099dacd Checked: eight paired processes,36 callbacks per lane and104
collected contexts. Pinned callback medians31.505/91.655ms imply2.91x for this
kernel; checksum and native ledgers bind the result. No-config still executes
definition-owner lookup/null-meter checks, so this measures configured-meter
increment only. A fresh matching Windows Release build now passes zero
warnings/errors and two paired cost runs. After Android cleanup, the second
run measures18.850/90.434ms callbacks, a4.80x configured-meter ratio, with
104 collections, interpreted author entries, exact ledgers and nine audit
corruption controls. Source/CoreLib/compiler/configuration and527 layout
hashes bind that result. The later [Release acceptance](windows-release-budget-acceptance.md)
and [joined concurrency](windows-terminal-concurrency.md) now pass within their
declared scopes. The later20405f7
[minimal optimization](windows-budget-increment-performance.md) is accepted
and measured on Windows; matching mobile and representative game workloads
remain next.

The 2026-10-13 [host instruction-budget option](host-instruction-budget.md)
now passes fifteen isolated Windows Checked cases on the unchanged099dacd
runtime, with73 completed context collections. It exposes explicit prototype
execution/cleanup limits and scalar results, binds capability before entry-file
access, skips OnStop after native termination, and avoids author virtual exception
properties when reporting even an unlatched error. Twenty bad/good pairs,
constructors/cctors, start/tick/stop, filters and finite/infinite private cleanup
pass. Ordinary cancellation retains reason0. Stock/full verification passes
24/24 lifecycle,84/84 packaging and15/15 player; matching unbudgeted production
24/24 and15/15 also pass. Stock and terminal-only runtime budget requests reject
before reading a missing author file. Native-query/allocation failure cleanup
has static review only, not fault injection. The simulator functional results
above cover budget dispatch and recovery; overhead measurement, physical-device
acceptance and remaining lifecycle/concurrency boundaries are still open.

The later 2026-10-13 [finalizer boundary](runtime-session-finalizer-boundary.md)
is built and measured at099dacd07d8d890822f7422f895337733457ab3c, directly
above terminal prototype7660f3069b3751b648f038bf7f3e9cfc6f96ff09. Matching
Windows x64 Checked acceptance passes9 recovery cases and6 fatal controls:
actual finalizer definition ownership, active/retired contexts, bounded cleanup,
two subsequent queue sentinels, next good session/static reset and completed
collection. Ordinary finalizer exceptions retain their original fatal behavior.
Four-stage metadata, native compile evidence and independent raw audit pass.
The original terminal44 lanes, production24/24/player15/15, legacy selection20/20
and four official loader tests also pass on this candidate. Production finalizers
remain rejected by package policy. That increment prepared explicit prototype-named host budget
binding and scalar reporting, then remaining EH/concurrency and matching mobile
regressions; physical-device acceptance remains outstanding.

The next 2026-10-13 [terminal prototype](runtime-session-terminal-prototype.md)
is now measured in the separate Windows x64 Checked worktree at
7660f3069b3751b648f038bf7f3e9cfc6f96ff09, parent diagnostic-meter commit
b8e5b0b4b7db30385265f935c00a39a3ba507aea. Fresh runtime/CoreLib/compiler build
passes with zero warnings/errors, five actual native compile owners and
517 matching framework hashes. Four CoreLib PE stages preserve old policy/meter
ABI and the new private prototype signatures. All44 isolated process lanes
pass: fourteen ordinary controls, fourteen non-throwing diagnostic controls,
and sixteen terminal cases including two-context isolation and20 bad/good pairs.
Terminal failures allow exactly 2048 author IR dispatches before an irreversible
reason1 latch. Typed/broad catches, catch-return and post-terminal filters do
not regain author execution; exhaustion within an ordinary filter also retains
the latch. Finite cleanup/private helper/delegate and nested cleanup complete;
infinite cleanup consumes4096 reserved dispatches, suppresses the remaining
outer author cleanup and returns to the trusted host. A replacement exception
from cleanup retains native reason1. Constructor/cctor exhaustion and trusted
catch followed by author reentry also fail with the persistent latch.
All56 terminal scalar rows and their retired query guards/collections pass.
On the same candidate, unchanged unmetered production contexts pass lifecycle
24/24, player15/15 and sample/late/source-import collections; legacy policy
selection passes20/20 and four official loader controls return expected100.
The root review (archival/local evidence: `../artifacts/session-terminal/root-review-20261013/results.json`)
binds the frozen source/build, native objects, PE metadata and actual raw process
outcomes without rerunning applications. The first production invocation's
wrong parameter failed before tests; the corrected attempt and the offline
review's corrected PID-reuse assumption are preserved separately.
This private factory remains a prototype: no production budget option or
complete terminal capability is exposed. At that earlier candidate, author finalizer recovery, native-call
duration, shared locks, concurrent terminal races, full EH topology, Release
computed-goto execution, performance and mobile/physical-device acceptance
remain unverified. The next increment is the trusted finalizer invocation
boundary and its isolated failure/queue-progress regressions; the
source-reviewed finalizer design (archival/local evidence: `../artifacts/session-budget/finalizer-design-20261013/design.json`)
uses the actual finalizer-slot definition owner instead of the object's type.
The canonical baseline and both earlier policy/meter worktrees remain unchanged.

The 2026-10-13 [diagnostic session instruction meter](runtime-session-meter.md)
is now built and measured in a separate Windows x64 Checked worktree at
`b8e5b0b4b7db30385265f935c00a39a3ba507aea`, parent session-policy commit
`5972a86966e56ae5f468a3e042327f0051e923d5`. Its fresh native/CoreLib build
reports zero warnings/errors; four actual CoreLib metadata stages preserve the
old policy and new private meter bridge/QCall ABI. The three actual meter,
compatibility and joined-concurrency processes pass. Both metered lanes collect
20/20 normal sessions; each normal session executes 12376 IR dispatches, with
positive constructor, private-helper, callback and exception-path increments.
Limit-one, maximum-limit, interleaved-owner and four-call concurrency controls
also pass. Metered author JIT summaries remain zero, with positive successful
bytecode and trusted JIT controls. These are Windows switch-dispatch counters,
not exhaustive native method-entry samples or mobile accounting evidence.
On this same private layout the original session-policy matrix passes twenty
sessions/collections, production lifecycle passes 24/24, controlled player
passes 15/15, and four unchanged official loader tests return their expected100.
The root evidence review (archival/local evidence: `../artifacts/session-budget/meter-root-review-20261013/results.json`)
binds 517 framework hashes, eleven source files, three compiled objects and
64 raw meter files without launching the applications again. Ordinary production
and upstream contexts in those regressions are unmetered; the official loader
lane uses the legacy global diagnostic switch. Terminal enforcement is still
unimplemented in the diagnostic-meter increment: remaining zero deliberately
permits finite code to continue. The following increment needed persistent
termination, author catch/filter
suppression, bounded finally/fault cleanup and safe finalizer handling before
exposing a production budget option. The existing baseline and session-policy
worktrees remain unchanged; physical-device acceptance remains outstanding.

The 2026-10-13 [matching Android session-policy prerequisite build](android-session-policy-build.md)
now passes with zero warnings/errors: same combined source27 as the iOS candidate,
Checked x64/API24 CoreCLR/CoreLib, shared interpreter and native JIT. Independent
compile-owner/GUID/trimmed-metadata assessment passes. First build-environment
and assessor-copy-mapping failures are preserved as local integration errors.
The [private Darwin SDK/JDK](android-session-policy-framework-toolchain.md) now
passes three archive checks, 11 critical file hashes and six executable probes.
[Framework attempt2](android-session-policy-framework.md) passes with zero
warnings/errors, 180 framework DLLs, 28 native-stage inputs and actual Android
deps; all seven core-critical product identities remain unchanged. The first
framework run's missing SDK/JDK prerequisite failure remains preserved as a
local integration error. [Matching layout attempt2](android-session-policy-layout.md)
passes all 195 file hashes and six provenance receipts. Its first attempt's
missing PreTrim intermediate is preserved; the separate CoreLib evidence
refresh reproduces all four inspected PE files and the descriptor exactly,
without changing the seven critical products. The cause of the missing
intermediate is not a confirmed upstream cleanup bug. The later actual
[matching Android APK production run](android-session-policy-validation.md)
now passes 24/24 lifecycle, 15/15 controlled packages and three collected sample
contexts on the owned API35/x64/4096-byte-page emulator. Native policy1 is
acknowledged with mode0/global diagnostic0, a trusted MapRunner JIT body and
author interpreter bytecode bodies; checked author names have no JIT summary
entries. PID/nonce, mapped runtime hashes and unchanged host/payload bytes bind
the evidence. The separate five-lane Checked matrix now passes on the same
runtime/IL: required and boxed interpretation, ordinary native control, required
refusal with recovery, and unmarked mode1 native fallback. Five distinct owned
PIDs/nonces bind raw method assessments; required author JIT summaries remain0.
Native method-entry proof was not collected. The original all-lane and final
method receipts honestly remain platformAccepted=false. Physical ARM64,
16KiB pages and frozen inline fixtures remain pending; the later Release
entry samples are recorded separately below. The fresh [Android Release core assessment](android-session-policy-release-build-assessment.md)
now passes the same source27, nine actual compile owners and frozen CoreLib
metadata inputs. Its matching framework and [Release layout](android-session-policy-release-layout.md)
also pass: 195 player files, preserved metadata snapshots and matching native
symbol build-ids. Release APK execution and method-entry capture are separate
requirements. The later [Release APK and debugger transport](android-session-policy-release-entry-preparation.md)
now pass construction, installation and post-install production/transfer.
After actual debugger detach and gate release, twenty exact functional results
and twenty collections pass; all 246 installed files and the APK identity remain
unchanged. This is transport/resumed-execution evidence. A subsequent
[Release native-entry run](android-session-policy-entry.md) now samples nine
fixture method groups: four exact InterpreterStub entries and five regular
child dispatch entries, with live bytecode/MethodDesc/module/token identity.
The separate [non-debugger Release selection run](android-session-policy-release-functional.md)
also passes twenty exact sessions/collections, 260 policy queries, twenty
retired-query guards, four live TracerPid0 samples and 246 before/after installed
file hashes. The subsequent [independent Release production and recovery runs](android-session-policy-release-production.md)
now pass 24/24 lifecycle, 15/15 controlled-package cases, three collected sample
contexts, one actual scoped compiler refusal followed by twenty recovered and
collected sessions, and ordinary JIT/unmarked-fallback controls. All four fresh
PIDs/nonces retain the same APK and 246 installed hashes with live TracerPid zero.
Original raw and strict offline reviews are retained separately. Production and
refusal method-entry samples, complete invocation counts, fast-dispatch coverage
and physical-device acceptance remain open. The owned emulator is shut down.
The four-lane evidence archive receipt (archival/local evidence: `../artifacts/android-session-policy/release-production-20261013-344a0b3c.receipt.json`)
verifies 243 files, all member sizes/hashes and CRC, with unchanged original
sources; the complete frozen APK/layout is retained separately.
The first Release framework attempt's MSB3883 compiler lock
exception is preserved as an unresolved tooling failure, not a confirmed runtime
defect; the retry disables shared compilation without changing runtime sources.

The separate [iOS Release refusal/recovery run](ios-session-policy-refusal.md)
now passes one real scoped CORJIT_SKIPPED refusal, NotSupportedException and
collection, followed by 20 successful sessions and 20 collected contexts.
Mode0/global diagnostic0, native policy queries, owned PID/nonce, unchanged
bundle/payload and shutdown are verified against the archived raw logs. The
fixtures were delivered after installation but were not newly compiled in this
run. Refusal-lane method-entry samples and physical-device acceptance remain
open. The [read-only device readiness check](ios-device-readiness.md) currently
finds no connected eligible device and no matching probe signing profile.

The lifecycle prototype was introduced in commit `1ec2589`. Recheck current code
and Git state rather than treating this snapshot as the latest implementation.

The host loads manifest-selected IL assemblies in collectible contexts, shares
the map contract, invokes synchronous start/tick/stop callbacks, reclaims
host-owned entities, and exposes weak-reference collection observation.

The sample runs Hello -> Arena -> Hello in one process. Both Hello executions
start with fresh map static state. Diagnostic collection confirmed all three
contexts retired. The integration harness passed nine cases, including twenty
successive sessions, map-defined exceptions, stop failures, caught cooperative
budget violations, and host resource quotas.

Windows local validation used SDK `11.0.100-preview.6.26359.118`. The initial
GitHub workflow passed on Windows, Ubuntu, and macOS:
[baseline CI](https://github.com/ReneeGA2020/RuneCLR/actions/runs/38203072522).
The repository is public and MIT licensed:
[ReneeGA2020/RuneCLR](https://github.com/ReneeGA2020/RuneCLR).

No custom CoreCLR was built or patched as part of that prototype. The sample
does not select or prove interpreted execution. No iOS-device validation, hard
CPU/memory isolation, source compiler, or comprehensive permission boundary has
been implemented. Read [SECURITY.md](../SECURITY.md) for the current trust model.

That paragraph describes the original baseline. The later controlled
[source/IL packaging increment](controlled-packaging.md) now implements a local
operator CLI, fixed C# 12 compiler/reference snapshots, managed-IL structural
intake and versioned manifests. Runtime loads versioned packages with format/API,
content and entry checks while retaining trusted legacy fixture APIs. The
compiler/Roslyn remain operator tooling and do not enter player dependencies.
The [initial static gameplay capability policy](capability-policy.md) now checks
every entry/private assembly during packaging and again at versioned loading.
It rejects unsupported APIs and unsafe routes, with bounded diagnostics. The
new `managed-il-gameplay-v1` profile rejects earlier structural-only versioned
packages; recompile/reimport them. Trusted legacy fixtures remain separate.
The [Android new-profile increment](android-controlled-packages.md) now passes
21/21 baseline, 22/22 with late IL, and 8/8 additional controlled package cases
on official RC1 x64 CoreCLR. Source/import/source, author failure cleanup and
rejection recovery collect; compilation tooling is absent from the APK. Android
interpreter selection is still unverified.
The [iOS new-profile increment](ios-controlled-packages.md) now passes 15/15
with source/import/source, actual private version/generic state, author failure
cleanup, rehashed entry/private rejection, recovery and retirement. Fixtures
were generated after installing the unchanged player bundle. The unpatched
pinned .NET 12 Debug ARM64 simulator runtime reports native compilation
disabled and successful script/private-helper interpreter dumps. Runtime and
Packages remain IL; the trusted harness/bridge/contract/framework remain R2R.
The reduced iOS R2R reproduction and private Debug fix are established below.
The active next steps are #5 runtime-backed execution selection and full
official mobile-runner integration;
server approval/authentication, hard execution budgets and physical iOS acceptance
remain outstanding. Existing dirty work from platform/performance increments
is preserved alongside the packaging implementation.
Official RC1 normal verification now passes lifecycle 22/22 and packaging 84/84;
the private unpatched source .NET 12 interpreter still passes 22/22 plus three
fresh-static controlled source/import/source sessions with direct callback dumps
and collection. Reproduction: eng/verify.ps1, followed by
eng/verify-interpreter.ps1 -RuntimeRepo <separate-runtime-checkout>. Current
packaging/capability evidence is recorded in the linked contracts; no runtime
patch is introduced by the static gate. The latest desktop evidence is
artifacts/interpreter/20261012-210157-6a3b8937480c460aaf3e220cf24c5e92.
The [portable package acceptance harness](package-execution-tests.md) now
separates fixed operator fixture generation from a compiler-free player.
Normal verification passes lifecycle 22/22, packaging 84/84 and its new 15/15
player cases, including actual private version/generic state and rejection
recovery. The expanded unpatched desktop interpreter run also passes 15/15
with successful callback/helper bytecode dumps. Latest evidence:
artifacts/interpreter/20261012-package-execution. Both projects and the player
suite are integrated into the solution, local verification and desktop CI.
On 2026-10-13 the ordinary RC1 suite again passes 22/22 lifecycle, 84/84
packaging, 15/15 package execution and all three sample context collections.
Log: artifacts/toolchains/verify-20261013-next-stage.log; hash receipt:
artifacts/toolchains/verify-20261013-next-stage.json.
The independent [execution-path probe](execution-selection-probe.md) now passes
twenty sessions and twenty context collections in each SDK JIT and private
Checked mode 1 lane. All 26 targeted constructor/initializer/property/inlining/
private-generic/delegate/interface/filter groups emit twenty successful
bytecode records each, with an observed JIT control and no reported UGC JIT
fallback in mode 1. This trusted fixture is outside the production capability
profile and does not establish runtime enforcement or native entry sampling.
The [runtime selection source plan](runtime-execution-selection.md) identifies
R2R/cache/inline/fallback gates and the matching compiler-interface change for
the switch-controlled [private candidate](runtime-execution-selection-candidate.md).
Its [matching Windows Checked build and lifecycle acceptance](runtime-execution-selection-build.md)
now pass with commit `6bb5f60be8de39b22fb19b95aea03e3252756cb3`: mode-0
required interpretation, actual compiler-skip rejection/recovery, boxed bridges,
native trusted generic caller inline refusal, lifecycle 22/22, player packages
15/15 and four unchanged [official loader tests](required-interpreter-upstream.md).
That diagnostic covers all collectible metadata IL definitions. The subsequent
[creation-time session policy](runtime-session-policy-build.md) now passes on
`5972a86966e56ae5f468a3e042327f0051e923d5`: native factory/acknowledgement,
ordinary collectible JIT control, late private loading, immutable policy and
post-unload query rejection, actual compiler refusal/recovery, and native
caller inline controls, all with the diagnostic switch disabled. Production
`RequireInterpreter` passes lifecycle 24/24 and player 15/15; stock SDK
verification passes 24/24, packaging 84/84 and player 15/15. Four official
loader regressions pass on the current candidate through the distinct
diagnostic ordinary-context route. The subsequent
[matching iOS simulator Release build](ios-session-policy-build.md), combined
with the CID lifetime fix at `1724cdec553a7aff7a373a271a4be612651c7625`,
completed with zero warnings/errors. Source, native configuration, private
CoreLib API preservation and compiler-interface checks all pass. Its current
production player passes lifecycle 24/24, controlled packages 15/15, three
sample context collections and 20 independent selection sessions/collections
with native policy 1, InterpMode=0 and the global collectible diagnostic off.
New late IL and controlled fixtures were produced after installing the unchanged
bundle. The [separate native capture](ios-session-policy-entry.md) has 11 valid
interpreter-entry samples covering nine installed-fixture method groups,
260 policy queries and 20 retired-query guards; it is not complete invocation
counting or method-entry proof for the post-install package definitions.
The owned simulator is shut down and raw evidence is archived separately;
local archive verification (archival/local evidence: `../artifacts/ios-session-policy/20261013-evidence-attempt2/local-verification.json`)
passes all three archives, 214 members, 72 raw hashes and 27 source hashes.
The later Android Release core, framework, matching layout, selection-fixture
entry samples and separate production/refusal/control runs now pass within
their recorded scopes. Windows Release policy acceptance, remaining method-entry
coverage, additional mobile native-path controls and physical-device acceptance
remain next. The Android Checked and iOS Release scoped refusal/recovery runs
are recorded separately above. The
[Android build preparation](android-session-policy-plan.md) confirms that the
existing AVD is x64 and Android interpreter support must be enabled explicitly.
The later [matching source build](android-session-policy-build.md) now uses a
verified project-private Darwin NDK r27c, with same-source framework and layout
inputs also accepted. Preserve Android's
JIT-capable trusted-host path and dynamic interpreter library rather than
copying the iOS no-JIT/static layout. The original
runtime baseline remains tracked-clean and installed runtimes are untouched.
The [iOS R2R investigation](ios-r2r-investigation.md) captures the original
PC-zero production fault under LLDB. Its isolated Debug diagnostic localizes
the failure to collectible cached-interface dispatch without changing managed
or framework inputs. The subsequent [minimal reproduction](ios-r2r-minimal.md)
passes single-session cold/publication/hot calls but fails after completed
retirement in six original/off/trace controls. All sixteen skip/IL controls
pass. Native memory captures show an old cache mapping surviving retirement,
then matching a reused MethodTable address and jumping through reused precode
whose native target and secret data are zero. Debugger-induced allocation
timing differs from the non-debugged second-session failure.
The [conservative default-behavior candidate](ios-r2r-fix-candidate.md) avoids
publishing collectible and dynamic-interface receiver mappings. Its isolated
Debug ARM64 [five-group acceptance](ios-r2r-fix-validation.md) passes: original
negative control still crashes, while the candidate passes the unchanged full
R2R lifecycle 21/21, reduced two/three-tick collected sequences 20/20 each, and
controlled player 15/15 with interpreter dumps and unchanged bundles. This is
a private incremental native build, not an upstream-accepted release. A focused
[dynamic-interface comparison](ios-cid-dynamic-repro.md) also passes v2 and IL
controls (60 calls, twenty context/type retirements per group); original and
receiver-only v1 both crash after the first retirement. Additional
[patched regressions](ios-r2r-patched-regressions.md) pass four value/default/
generic/exception cases (twenty sessions each) and two unchanged upstream source
adaptations. Original/trace default-interface controls stall at the second
session; the other controls SIGSEGV there. A separate
[fresh native Debug build](ios-r2r-clean-build.md) now completes and passes the
five-group comparison again without baseline native-object reuse. Four
[official generated managed runners](ios-r2r-official-managed-tests.md) now pass
on that patched Debug simulator with actual collectible payload interpreter
evidence. They retain upstream Main/assertions but use a custom native wrapper
and TargetOS=ios generation. The later
[generator alias source fix](apple-generator-regression.md) passes 21/21 actual
generator/body-semantic checks on desktop. The subsequent
[source-fixed official simulator tests](ios-generator-fixed-tests.md) rebuild
and execute all four unchanged managed projects with TargetOS=iossimulator,
correct generated guards, positive payload interpreter dumps and successful
assertions. That experiment uses the private native wrapper, so full XHarness
integration remains outstanding. Earlier workaround evidence is preserved. A
[fresh Release native build and matching CoreLib/tools](ios-r2r-release-build.md)
also pass their build/provenance checks. The first
[mixed-configuration execution](ios-r2r-release-validation.md) fails at startup:
Debug CoreLib and Release native have incompatible MethodTable field offsets.
Regenerated matching trusted composites now pass full lifecycle 21/21 and a
twenty-session, sixty-call collected probe. A separate Release LLDB sample
proves actual interpreter entry for all three probe callbacks through
bytecode/MethodDesc/metadata identities; it records eight sampled entries and
does not claim complete invocation capture. The
[additional interface boundaries](ios-r2r-interface-boundaries.md) also pass
candidate covariance 20 contexts/60 calls; original/trace controls crash after
retirement. Constrained value-type calls pass in all three configurations and
the trace shows no CID cache record for that path. The
[matching Release controlled player](ios-r2r-release-packages.md) now passes
15/15 functional cases with fresh post-install fixtures and an unchanged
bundle. Its original count-parser error and independently passing read-only
reassessment are both retained. A separate [native execution-entry capture](ios-release-package-entry.md)
records 33 valid samples across all 23 required package/helper method groups,
including the three same-name private dependencies and generic static helpers.
That diagnostic run exits normally with unchanged inputs and fifteen actual
PASS events in the owned app's unified log. Its original raw-JSON substring
parser misreads the escaped 15/15 aggregate; a separate read-only assessment
parses eventMessage and retains the original failure. The preceding non-debugger
15/15 result remains independently recorded. Sampling is not a complete invocation counter.
Complete managed packs, performance,
full upstream runner integration and physical-device acceptance remain outstanding.
Retain the passing Runtime-IL
deployment layout until deployment acceptance is complete.
The [physical-device preparation check](ios-device-readiness.md) finds a
cached paired iPad with developer mode enabled, but no current usable tunnel
and no development profile matching the proposed RuneCLR probe bundle.
The Mac has an iOS SDK and a valid development signing identity. Device
reconnection and an appropriate project profile remain necessary; no signing
settings or credentials were changed by the read-only check.
The [read-only cache analysis](ios-r2r-cache-analysis.md) separates the cold
prestub, cache publication, hot-hit and lifetime mechanisms.
[Official Windows regression controls](ios-r2r-upstream-validation.md) pass
16/16 generated upstream project executions across JIT/interpreter and requested
cached-dispatch settings. The two-tick R2R/IL desktop control passes 4/4 groups
with all eighty collectible contexts retired; the three-tick control also
passes 4/4 with 240 callback returns and eighty completed retirements. These
passing Windows controls do not
exercise or fix the observed iOS failure.

## Upstream defects and private fixes

The [exported-patch reproduction check](runtime-patch-reproduction.md) now
reconstructs all36 changed Git source blobs of the099dacd desktop candidate
from the pinned official base. Both optional CID/generator patches also apply
in a separate source snapshot. All seven checks/applications return0; this is
source-only evidence and does not replace build/platform acceptance.

On 2026-10-13, the user requested separate records for official runtime defects,
local fixes/workarounds and future upstream reports. The
[upstream defect register](upstream-bugs/README.md) records the confirmed
collectible CID lifetime defect and simulator generator mapping omission,
plus the mode 3 assertion as an unconfirmed investigation. It explicitly
separates our mixed-layout/packaging failures and unsupported APIs.
The private generator alias patch is retained alongside its 21/21 regression
and separate runtime commit. Keep the validated private CID patch and
managed-target workaround until an
official replacement passes the record's regression gates. Record the actual
upstream fix commit and revalidate without overlapping private changes before
adoption; a newer version or closed issue is insufficient. On 2026-10-13 the
reports were local drafts. On 2026-10-16 RCLR-UP-001 and RCLR-UP-002 were filed
as [dotnet/runtime #135848](https://github.com/dotnet/runtime/issues/135848)
and [dotnet/runtime #135849](https://github.com/dotnet/runtime/issues/135849);
RCLR-UP-003 was not filed.

## Resume in a new session

Set the workspace to the RuneCLR checkout. Its root `AGENTS.md` identifies the
project rules; the project Skill is at
`.agents/skills/runeclr-development/SKILL.md`. Cindy discovers this shared project
Skill root in new or restarted agent sessions. Agents without skill discovery
can read the file directly.

Read `docs/development.local.md` if present for this machine's setup. Check both
repositories' current state. The existing `global.json` selects an SDK for
RuneCLR; `dotnet/runtime` has its own toolchain configuration. Running `dotnet`
from one checkout does not establish the configuration of the other.

Re-run `./eng/verify.ps1` when starting implementation or if the environment has
changed. Read only the architecture or integration documents relevant to the
requested change; the handoff does not authorize additional work on its own.

## Recommended next experiment

Scheduled, not implemented: issue 16 tracks a coarse per-callback deadline for untrusted UGC interpreter calls. It is not a cumulative instruction quota, not an API call limit, and it does not apply to trusted code.

Track future work in [Roadmap #11](https://github.com/ReneeGA2020/RuneCLR/issues/11).
The desktop acceptance criteria of
[#1: proven interpreter lifecycle execution](https://github.com/ReneeGA2020/RuneCLR/issues/1)
were verified locally on 2026-10-12; see [the experiment record](interpreter-experiment.md).
The local [#4 controlled compilation/packages](https://github.com/ReneeGA2020/RuneCLR/issues/4)
and [#5 static capability increment](capability-policy.md) are implemented.
Continue [matching mobile session-policy integration](runtime-session-policy-build.md),
combining the iOS CID fix with the changed compiler interface and matching
CoreLib/trusted composites. Run the required factory with ordinary native
controls and post-build IL; earlier mobile results do not establish this new
policy. Extend runtime native-entry/concurrent preparation controls and
execution accounting afterwards. Device preparation for
[#2: real-device iOS execution](https://github.com/ReneeGA2020/RuneCLR/issues/2)
can proceed in parallel; see [the ordered contributions](work-sequence.md) and
[the platform environment audit](platform-validation.md).
The subsequent [remote Mac preparation](remote-mac-experiment.md) passed the
stock macOS ARM64 lifecycle suite (12/12 with a post-host-build map) and a
native iOS 27 simulator deployment/storage smoke. A Mac is now accessible for
the simulator lane. The later [managed iOS simulator experiment](ios-simulator-experiment.md)
passes 21/21 and 22/22 with post-install IL on both historical Preview 6 and
official .NET 11 RC1 CoreCLR,
dynamic compilation disabled. Framework/tests/bridge/Abstractions remain R2R,
but RuneCLR.Runtime must remain IL to avoid a recorded native-interface crash.
The pinned .NET 12 Debug source runtime now also passes the original full
harness 21/21 and post-install 22/22 with the same Runtime-IL selective layout,
positive script/private-generic diagnostics and successful callback IR dumps.
Its earlier reflection-based mini-fixture passed 20/20 separately. The
all-host-R2R configuration still crashes during repeated sessions on unpatched
.NET 12 Debug. The later minimal reproduction identifies stale cached
MethodTable/precode address reuse, and a private conservative candidate passes
the measured Debug simulator regressions; see the records above. Physical-device
acceptance remains outstanding. RC1 also reproduces the all-host-R2R crash.
The primary pinned source is official main / .NET 12, built using its own
.NET 11 RC1 SDK. Preview 6 results remain historical package comparisons;
RC1 uses independently verified matching runtime/framework/compiler inputs.
The [Windows Android emulator experiment](android-emulator-experiment.md) installed
an official Android 15 x64 test lane and ran a stock CoreCLR APK with IL compiled
after APK installation: twenty fresh contexts reset statics and collected 20/20.
The old Android resolver probe throws PlatformNotSupportedException. After its
replacement, the [full RuneCLR Android harness](android-lifecycle-experiment.md)
passed 21/21 and 22/22 with post-install IL, including private dependencies and
recovery. Android interpreter execution remains unverified. On the updated
official .NET 11 RC1 Android package the same 21/21 baseline and post-install
22/22 also pass, independently of the historical Preview 6 run.
See [the roadmap issue index](roadmap.md) for platform, tooling, enforcement, and
pilot tasks with their acceptance criteria and dependencies. The handoff commit
`615e832` also passed
[its three-platform CI](https://github.com/ReneeGA2020/RuneCLR/actions/runs/38205851287).

**Desktop map interpretation is verified with mode 1.** The private Checked
runtime passed all 12 lifecycle cases and both sample runs, including private
dependencies, generic static reset and a map built after the host. Successful
interpreter bytecode dumps and absence of reported map JIT compilation provide
execution evidence. CoreLib is JIT-enabled in this mode.

The separate runtime remains unpatched at
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` on branch
`runeclr/interpreter-baseline`. Its build produces a private dotnet host layout.
Use `./eng/verify-interpreter.ps1 -RuntimeRepo <checkout>` to reproduce.
The earlier experiment used a private dotnet host because its then-current
resolver required hostpolicy. The new explicit resolver has no such dependency;
plain corerun has not been revalidated. The installed .NET installation is untouched.

**Full-framework mode 3 currently fails a Checked object-reference assertion**
during manifest serialization/reflection. Do not claim a JIT-free runtime or
iOS readiness from the mode 1 result. The pinned CoreLib also marks the current
`AssemblyDependencyResolver` API unsupported on Android and iOS. It has now been
replaced by explicit [package resolution](package-resolution.md); normal Windows
and private Checked mode 1 suites pass 22/22 after the change. Controlled
compiler/intake and package approval remain part of #4/#5. Mode 3's failure does not establish
a blocker for selective UGC interpretation; #2 still needs real-device dynamic
loading and repeated retirement.

The official Windows SDK `11.0.100-rc.1.26425.128` was downloaded to a private
toolchain directory and checked against the published SHA-512. Selecting it
through process-local PATH passed `eng/verify.ps1` (22/22 and all three sample
contexts collected). The same RC1-built host passed the unpatched pinned
Checked mode 1 interpreter suite again: 22/22, positive bytecode evidence and
unchanged host identities. Evidence:
`artifacts/toolchains/verify-rc1.log` and
`artifacts/interpreter/20261012-192907-c98f7819d5f247278ed61ec44ddebe75`.
`global.json` remains a compatible minimum with `latestFeature`; the explicitly
selected RC1 SDK is actually used. No installed runtime or global PATH is replaced.

For a different upstream base, repeat the desktop experiment:

1. Inspect the separate runtime checkout, its build requirements, existing
   artifacts, interpreter feature gates, and mode definitions.
2. Select and record a reproducible upstream base and private runtime layout;
   build the necessary components with matching libraries.
3. Establish through runtime diagnostics that map methods actually take the
   interpreter path. Avoid assuming a switch worked merely because startup did.
4. Run the sample and integration suite using that runtime. Verify static-state
   reset, ordinary failures, resource cleanup, and completed unloading.
5. Add focused coverage for map-private dependencies and relevant generics, and
   execute a map compiled after the host build.

Follow the [ordered work sequence](work-sequence.md): controlled packages and
device preparation, supported execution/API boundaries, then interpreter-enforced
budgets. The next [source-reviewed budget implementation plan](runtime-session-budget-plan.md)
identifies per-binder native state, common opcode dispatch accounting, terminal
catch/filter suppression, bounded unwind cleanup and finalizer handling. It is
not yet complete as terminal enforcement. A separate
[diagnostic meter foundation](runtime-session-meter.md) now implements and
measures binder-owned opcode accounting; the later
[terminal prototype](runtime-session-terminal-prototype.md) measures sticky
exhaustion, owner-aware catch/filter suppression and bounded cleanup in its
declared Windows cases. A later [finalizer boundary](runtime-session-finalizer-boundary.md)
now has matching Windows recovery/fatal-control evidence. Production integration
is now available as an explicit [host prototype](host-instruction-budget.md);
remaining lifecycle/mobile boundaries remain next. Neither the non-throwing meter nor a catchable exception alone
establishes terminal enforcement. The proposal's thirteen
source-file hashes and thirty-two anchors were checked against the separate
Windows session-policy worktree; later meter source/build evidence is retained
separately.
See [CoreCLR integration](coreclr.md) and [roadmap](roadmap.md).

On 2026-10-16 the desktop restricted UGC packaging suite passed 124/124 at commit c196707. A caught host limit fails the session at the end of that callback: OnTick does not run after OnStart fails, and a later tick does not run after the first tick fails. The failed tick is not counted. An empty OnStop does not add an OnStop: prefix. Reading MapId during that OnStop does not throw. A charging host call in OnStop raises the latched limit again and adds OnStop:. If OnTick catches the limit and then throws an author exception, the latched limit is appended after the author failure without an OnStop: prefix. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open. The earlier 85/85 packaging sentence remains the historical RC1 result.

On 2026-10-16 packaging tests passed 126/126 at commit 215663d. Charge(0) and Charge(-1) fail in OnStart with System.ArgumentOutOfRangeException before OnTick. Charge(int.MaxValue) fails with the cooperative operation budget, not ArgumentOutOfRangeException, and does not wrap. An empty OnStop does not add OnStop:. The 125/125 strict text was confirmed by a later Release run. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 128/128 at commit 5ca90e0. With OperationBudgetPerCallback set to 1, Charge(1) succeeds in OnStart, OnTick, and OnStop, and the session completes one tick. After OnStart spends that one operation, OnTick still receives a fresh budget, and Charge(2) fails that tick without counting it. An empty OnStop does not add OnStop:. Refill does not disable the per-callback cap. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 129/129 at commit 700acaf. With TickCount 2 and TickDuration 50 milliseconds, OnTick logs 0:500000 and 1:500000. Both ticks complete. Commit e595193 accepts both LF and CRLF before the non-positive Charge detail line. Prototype checks run 38891953960 passed on ubuntu-latest, macos-latest, and windows-latest. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 131/131 at commit 9642eee. With TickCount 0, OnStart and OnStop still run and OnTick does not. The logs are start and stop. A negative TickCount throws ArgumentOutOfRangeException with ParamName TickCount before the author runs. The Message is TickCount ('-1') must be a non-negative value. (Parameter 'TickCount'), then Actual value was -1. Windows separates that line with CRLF. Ubuntu and macOS separate it with LF. The next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 132/132 at commit 407dc0a. A zero TickDuration throws ArgumentOutOfRangeException with ParamName TickDuration before the author runs. The Message is TickDuration ('00:00:00') must be greater than '00:00:00'. (Parameter 'TickDuration'), then Actual value was 00:00:00. Windows separates that line with CRLF. Ubuntu and macOS separate it with LF. The next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 133/133 at commit ff8e7e3. A TickDuration of one negative tick throws ArgumentOutOfRangeException with ParamName TickDuration before the author runs. The Message is TickDuration ('-00:00:00.0000001') must be greater than '00:00:00'. (Parameter 'TickDuration'), then Actual value was -00:00:00.0000001. Windows separates that line with CRLF. Ubuntu and macOS separate it with LF. The next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 134/134 at commit f894b2d. The default MapRunOptions run three ticks of 50 milliseconds. OnTick logs 0:500000, 1:500000, and 2:500000. The session completes. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 135/135 at commit 8909dc1. An entity spawned in OnStart is destroyed on the first tick. The next tick logs tick1 and then DestroyEntity fails because the entity is gone. That tick is not counted. CompletedTicks stays 1. An empty OnStop does not add OnStop:. The entity is released, and the next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 136/136 at commit 87ed913. An entity spawned in OnStart and left alive is released when the session completes. The logs are made and tick. One tick completes, created 1, released 1, remaining 0, and no error is reported. The next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 137/137 at commit dbb8868. The author catches a second DestroyEntity of the same id, and the session still completes. The other entity is then destroyed. The logs are made, tick, gone, and kept. One tick completes, created 2, released 2, remaining 0. A caught argument error is not a latched host limit. The next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 138/138 at commit 5721b5a. Destroying one entity leaves the other alive until session completion. The logs are made and tick. One tick completes, created 2, released 2, remaining 0, and no error is reported. The next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 139/139 at commit 88c32f1. OnStop can destroy an entity spawned in OnStart. The logs are made, tick, and stopped. One tick completes, created 1, released 1, remaining 0, and no error is reported. The next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 140/140 at commit c039cd9. Destroying an already removed entity in OnStop fails and adds OnStop:. The completed tick remains. The logs are made and tick, not stopped. CompletedTicks stays 1. The entity stays released, and the next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 141/141 at commit ced0bbb. An empty log string is stored. It is not treated as a null log. The session completes one tick, and the next package still runs. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 142/142 at commit a49b9a8. A log of one space is stored unchanged. It is not rejected as whitespace. The session completes one tick, and the next package still runs. Entity names still reject whitespace. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 143/143 at commit 1d990e4. An entity name of one space is rejected. No entity is created, no tick completes, and the next package still runs. A log of one space is still stored. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 packaging tests passed 144/144 at commit 8d093b9. A log of exactly 2048 characters is stored. The session completes one tick, and the next package still runs. A log of 2049 characters still exceeds the limit. This is stock desktop JIT, not interpreter evidence and not iOS. Issue 5 stays open. Issue 8 stays open.

On 2026-10-16 one Windows run at artifacts/trusted-composition-timing-20261016 exited 0 and printed PASS five functional/execution controls. controlsPassed=true, milestoneComplete=false, and status=blocked-collectible-r2r. Startup, callback, and boundary microseconds accumulated across the sessions in that one process were il-collectible 47279/226526/13186, r2r-collectible 47760/222400/13389, r2r-native 44706/222359/0, il-jit-control 45633/345580/11850, and r2r-disabled-control 164025/282338/2. The same noncollectible semantics are r2r-disabled-control, with ReadyToRun off so the update module runs as interpreter IL, and r2r-native, which is noncollectible R2R. Their boundary totals are 2 and 0 microseconds. A total of 0 is under 1 microsecond. il-collectible and r2r-collectible are not noncollectible R2R. Collectible R2R remains refused by upstream. These figures are not a distribution across processes and not an iOS result. Issue 3 stays open. Issue 13 stays open.

On 2026-10-16 the owner deferred a four-platform performance pass. Windows, macOS, iOS, and Android still need performance measurements, but that pass is not current work. The Windows composition timing above is one process aggregate and does not cover macOS, iOS, or Android. Do not start a runtime build, simulator, or emulator only to open that pass. Simulator and physical-device results stay separate. Physical iOS remains paused because the only phone is an iPhone XR locked to iOS 18.7. Issue 3 stays open.

On 2026-10-17 desktop runtime tests passed 58/58 after adding HostContractSession. The script OnStart receives the game-supplied interface instance and calls Echo(41). The assembly is loaded from memory, and Dispose drops the collectible context. An OnStart parameter that is not that interface fails before the author method runs. The managed-il-gameplay-v1 allowlist is unchanged. IMapContext is not renamed. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 59/59 after rejecting a foreign OnStart call. OnStart may call only methods declared by the game-supplied interface. Object.ToString is rejected before the author method runs, and the host echo is not called. This is not a full packaging allowlist. IMapContext is not renamed. This is not an iOS result.

On 2026-10-17 packaging tests passed 146/146 after adding ValidateHostContract. It reads the entry OnStart without loading the author assembly. A call to Echo on HostContract.IApi is accepted. Object.ToString is rejected before loading, and the message contains Capability profile and host contract member. Existing managed-il-gameplay-v1 validation is unchanged. PackageValidator.Validate does not call ValidateHostContract, so gameplay packages keep the prototype profile. IMapContext is not renamed. This is not an iOS result.

On 2026-10-17 packaging tests passed 147/147 after also checking the OnStart parameter. The parameter type must be the named host interface. OnStart(object) is rejected before loading. Echo on HostContract.IApi still passes. PackageValidator.Validate is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 148/148 after rejecting an interface method that was not allowed. HostContract.IApi.Other is named in the error and is not called. Echo remains allowed. PackageValidator.Validate is unchanged. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 60/60. HostContractSession now takes the allowed method names. An OnStart call to IHostEcho.Other is rejected before the host method runs when only Echo is allowed. Echo(41) still reaches the host. This is not an iOS result.

On 2026-10-17 packaging tests passed 151/151. package.json may include hostInterface and allowedMethods. When either is present, PackageValidator.Validate requires both and runs ValidateHostContract on the entry before the gameplay profile. Omitting both leaves existing manifests and their content hashes unchanged. Allowed methods remain simple names, not signatures. This is not an iOS result.

On 2026-10-17 packaging tests passed 154/154. PackageBuilder and RuneCLR.PackageTool write hostInterface and allowedMethods when both are supplied. Loading then checks OnStart against that interface and those method names. A build that supplies only one of them is rejected. Omitting both leaves ordinary gameplay manifests unchanged, because the OnStart check still rejects calls that are not on the named interface. Allowed methods remain simple names. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 62/62. HostContractSession.Invoke runs one later public parameterless void method on the same script instance. Its IL is checked before that method runs, using the host interface and allowed method names from construction. An unlisted call does not run, and the earlier Echo remains. Dispose drops the script reference, and a later Invoke throws ObjectDisposedException. The collectible context unloads. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 63/63. HostContractSession.Invoke can pass the same host instance into a later public void method that takes the host interface. A parameterless callback still runs. The IL check still happens before the method runs. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 64/64. HostContractSession rejects a reentrant Invoke while OnStart or a later callback is still running. The message is A session lifecycle callback is already running. The nested callback does not run. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 65/65. A host-contract callback failure is reported as a new InvalidOperationException. Its message contains the caught type and message, and InnerException is null. The session can Invoke a later callback after that failure. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 66/66. After a host-contract callback failure, Dispose still unloads the collectible context while the host keeps the text exception. An OnStart failure is also text with no InnerException, and the constructor does not return the session. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 69/69. HostContractSession.Open reads hostInterface and allowedMethods from package.json. It checks the content hash and the entry file hash, then uses that method list for OnStart. It does not run the managed-il-gameplay-v1 profile. A different interface name is rejected before the author runs. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 71/71. HostContractSession rejects a type initializer before creating the script. An instance constructor may call only Object..ctor. Both checks happen before OnStart, and the host method is not called. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 72/72. HostContractSession inspects the assembly before loading it. An image that is not IL-only is rejected, and the host method is not called. This is the structural intake check, not the gameplay member allowlist. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 73/73. HostContractSession rejects an author assembly whose simple name is mscorlib, netstandard, System, Microsoft, RuneCLR, or starts with System., Microsoft., or RuneCLR. The host method is not called. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 74/74. HostContractSession allows references only to System.Runtime, System.Private.CoreLib, netstandard, and the assembly that declares the host contract. A reference to RuneCLR.Packages is rejected before the host method runs. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 75/75. HostContractSession rejects localloc, cpblk, initblk, ldind, and stind in OnStart, a later callback, and the instance constructor. The host method is not called. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 76/76. HostContractSession rejects ldsfld, stsfld, and ldtoken in OnStart, a later callback, and the instance constructor. Instance fields can still store the host. The host method is not called. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 78/78. HostContractSession.Open rejects a changed entry file before loading it. The message contains hash mismatch. A manifest whose host interface was edited without updating the content hash is also rejected. The message contains content identity. The host method is not called. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 80/80. HostContractSession.Open rejects an entry path containing .. and an entry that does not end in .dll. Both fail before the file is opened. The message says the path must be a canonical relative DLL path. The host method is not called. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 82/82. HostContractSession.Open requires the entry path to appear once in the file list with the same hash. A missing entry or a different file hash is rejected before the file is opened. The message says the file list must exactly match the entry. The host method is not called. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 84/84. HostContractSession.Open requires every file to be the entry or one private dependency, with the same path and hash. A dependency path containing .. is rejected before any file is opened. An extra file is rejected. The host method is not called. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 87/87. HostContractSession.Open checks each private dependency file hash before loading the entry. A missing or changed dependency is rejected. A matching dependency still lets the host method run. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 89/89. HostContractSession.Open inspects each private dependency after its hash matches. A file that is not a managed PE is rejected. A dependency named System.IO is rejected as a spoof. A valid IL dependency still lets the host method run. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 90/90. HostContractSession rejects boxing a value type that is not in System.Private.CoreLib or System.Runtime. The check covers OnStart, a later callback, and the instance constructor. The host method is not called. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 91/91. HostContractSession rejects newarr and initobj of a type that is not in System.Private.CoreLib or System.Runtime, using the same rule as box. The host method is not called. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 92/92. The host-contract author-type check now also covers castclass, isinst, unbox, unbox.any, ldobj, stobj, mkrefany, refanyval, sizeof, and constrained. A castclass of an author class is rejected before the host method runs. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 93/93. HostContractSession rejects ldftn and ldvirtftn. An ldftn of Object.ToString is rejected before the host method runs. ldsflda is rejected with static field loads. ldelem, stelem, and ldelema use the author-type rule. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 94/94. HostContractSession rejects cpobj of a type that is not in System.Private.CoreLib or System.Runtime. Copying an author value type is rejected before the host method runs. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 95/95. HostContractSession allows ldfld, stfld, and ldflda only for a field declared on the method's own type. A field of another type is rejected before the host method runs. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 96/96. HostContractSession reads exception handlers from the assembly metadata. A catch of an author exception type is rejected before the method runs. A filter handler is rejected. Catch types in System.Private.CoreLib or System.Runtime stay allowed. The host method is not called for the author catch. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 98/98. A host-contract OnStart can catch System.Exception and still call the host. An exception filter is rejected before the method runs, and the host method is not called. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 99/99. HostContractSession rejects a generic OnStart before the method runs. The host method is not called. A later callback was already required to be non-generic. This is not an iOS result.

On 2026-10-17 desktop runtime tests passed 101/101. HostContractSession.Open loads a declared private assembly into the collectible context. OnStart may call a method on that assembly, and that method is checked before it runs. A private call to System.IO.File.ReadAllText is rejected, and the host method is not called. A framework assembly name is still rejected. The package validator still rejects an OnStart call that is not on the named interface. Its gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 158/158. ValidateHostContract accepts an OnStart call to a method in the entry assembly or a declared private assembly, and checks that method before accepting it. A same-assembly helper and HostHelper.Math.AddOne are accepted. A private call to System.IO.File.ReadAllText is rejected, as is a private call whose assembly image was not supplied. PackageValidator passes declared private images into that check. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 103/103 and packaging tests passed 160/160. A declared private method may call a method on the entry assembly, and that entry method is checked before it runs. The callback returns 41 to the host. string.IsNullOrEmpty reached through the entry method is rejected, and the host method is not called. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 105/105 and packaging tests passed 162/162. OnStart may construct a type declared by the entry or a private assembly, and that constructor is checked before it runs. An author box returns 41 to the host. new System.InvalidOperationException is rejected, and the host method is not called. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 107/107 and packaging tests passed 164/164. OnStart can construct a type declared in a private assembly, and that constructor is checked before it runs. The private box returns 41 to the host. string.IsNullOrEmpty inside that constructor is rejected, and the host method is not called. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 109/109 and packaging tests passed 166/166. One declared private assembly may call another. The call returns 41 to the host. string.IsNullOrEmpty reached through the second assembly is rejected, and the host method is not called. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 112/112. HostContractSession.Invoke can pass one int to a later public void method. The method is checked before it runs. OnTick receives 41. string.IsNullOrEmpty in that callback is rejected, and the earlier Echo(1) remains. Invoke without the int does not run the int method. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 115/115. HostContractSession.InvokeInt calls a public int method with one int parameter and returns its int. Measure(40) returns 41 without calling the host again. string.IsNullOrEmpty in that method is rejected, and the earlier Echo(1) remains. A void callback is rejected by InvokeInt. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 118/118. A later callback may take the host contract and then one int. Invoke passes 41 to OnTick. InvokeInt Measure(40) echoes 40 and returns 41. string.IsNullOrEmpty in that shape is rejected, and the earlier Echo(1) remains. This is not an iOS result.


On 2026-10-17 packaging tests passed 169/169. ValidateHostContract checks a later public callback on the entry when it takes the host and one int. A callback that echoes the int is accepted. string.IsNullOrEmpty in that callback is rejected. A public method with an unsupported signature is not checked. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 171/171. A later host-and-int callback may call a declared private assembly, and that private method is checked. A private AddOne used by the callback is accepted. string.IsNullOrEmpty inside that private method is rejected. OnStart itself does not call the private method. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 119/119. HostContractSession rejects a supported later callback with a disallowed call before OnStart. An int callback, an int return, a host-and-int callback, and an unlisted host call all fail before Echo. A public method with an unsupported signature does not block OnStart. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 121/121. A later host-and-int callback may call a declared private assembly. OnTick(40) echoes 41. string.IsNullOrEmpty inside that private method is rejected before OnStart, and Echo is not called. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 123/123. A later host-and-int callback may construct a type declared in a private assembly. OnTick(41) echoes 41. string.IsNullOrEmpty inside that constructor is rejected before OnStart, and Echo is not called. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 124/124. Rejecting a later callback before OnStart unloads the collectible context. The host method is not called. This is not an iOS result.


On 2026-10-17 the same desktop runtime suite stayed at 124/124 and the packaging suite stayed at 171/171. A rejected later callback is named in the error. The runtime text contains The callback OnTick. The package text contains OnTick calls a method. This is not an iOS result.


On 2026-10-17 the desktop runtime suite stayed at 124/124. A rejected later callback names both the callback and the member. The OnTick text contains IsNullOrEmpty. An unlisted host call contains .Other. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 125/125. An OnStart host failure still reaches the host, keeps the failure text, and does not return the session. The collectible context is unloaded. This is not an iOS result.


On 2026-10-17 the desktop runtime suite stayed at 125/125. A later callback into a private assembly that calls System.IO.File.ReadAllText is rejected before OnStart. The text names OnTick and ReadAllText. The collectible context unloads. This is not an iOS result.

On 2026-10-17 packaging tests passed 172/172. PackageBuilder.Compile rejects a supported later callback that calls a method outside the allowed list. OnStop calling SpawnEntity fails before a package is published. The error names OnStop and SpawnEntity. OnStart itself only calls Log. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 126/126. HostContractSession.Open rejects a package directory that contains a file not listed in the manifest. An extra.dll beside a valid entry is rejected before the host method runs. The message contains missing or extra files. A listed entry and its declared dependencies still load. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 127/127. HostContractSession.Open rejects a private dependency whose assembly identity does not match the manifest. The file hash can still match. The message contains identity mismatch and lib.dll. The host method does not run. A dependency whose manifest identity matches the image still loads. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 128/128. HostContractSession.Open rejects a manifest whose format version is not current, even after the content hash is recomputed. The same check also requires the current API version and input profile. The message contains Unsupported package format. The host method does not run. A current manifest still loads. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 129/129. HostContractSession.Open rejects an entry larger than the assembly size limit before loading it. The message contains size limits. The host method does not run. The same read also stops when the listed files would pass the package size limit. A normal-sized entry still loads. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 131/131. HostContractSession.Open rejects a filesystem link in the package directory before loading. Replacing the entry with a symbolic link does not run the host method. The message contains filesystem links. A directory nested past the package limit is also rejected. The message contains nesting limit. A normal package still loads. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 132/132. HostContractSession.Open rejects a producer input kind other than source or il, even after the content hash is recomputed. The message contains Unsupported producer input kind. The host method does not run. An il producer still loads. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 133/133. HostContractSession.Open rejects a producer with no references, even after the content hash is recomputed. The message contains Producer references identities are required and bounded. The host method does not run. The same check requires sources, and compiler identities when the input kind is source. An il producer with one reference and one source still loads. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 134/134. HostContractSession.Open rejects a blank package id, even after the content hash is recomputed. The message contains Missing or oversized id. The host method does not run. The same check bounds the entry type and requires SHA-256 hashes and a bounded file list. A normal id still loads. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 135/135. HostContractSession.Open rejects a producer whose references do not name the supplied contract assembly exactly once, even after the content hash is recomputed. A reference to Other.Contract does not run the host method. The message contains exactly one shared host contract. The check uses the supplied contract assembly, not a fixed RuneCLR.Abstractions name. A producer that names that assembly once still loads. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 136/136. HostContractSession rejects an entry assembly whose simple name matches the supplied contract assembly. The host method does not run. The message contains duplicates the host contract assembly and the assembly name. A framework spoof such as System.IO still reports the spoof message. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 137/137. HostContractSession.Open rejects a blank producer tool, even after the content hash is recomputed. The message contains Missing or oversized producer.tool. The host method does not run. The same check bounds the producer tool version. A normal tool name still loads. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 138/138. HostContractSession.Open rejects an entry path whose segment ends with a dot, even after the content hash is recomputed. bad./echo.dll does not run the host method. The message contains canonical relative DLL. The same check rejects control characters, reserved path punctuation, and segments that end with a space. A path longer than 240 characters is missing or oversized. A normal echo.dll path still loads. This is not an iOS result.


On 2026-10-17 desktop runtime tests passed 139/139. HostContractSession.Open rejects a producer reference that keeps the contract assembly name but changes its version, even after the content hash is recomputed. The host method does not run. The message contains exactly one shared host contract. A reference whose full identity matches the supplied contract still loads. This is not an iOS result.


On 2026-10-17 packaging tests passed 173/173. PackageBuilder.Compile can produce a host-contract package that HostContractSession.Open runs. The source uses RuneCLR.IMapContext with Log and SpawnEntity allowed. OnStart logs ok and spawns fixture. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 174/174. A compiled host-contract package can run a later callback after Open. OnStart logs ok, and Invoke OnStop logs stopped through the same IMapContext. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 175/175. A compiled host-contract package can return an int from a later callback. OnStart logs ok. InvokeInt Measure(40) returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 176/176. A compiled host-contract package can take the host and an int in a later callback. OnStart logs ok. Invoke Report(41) calls Charge with 41. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 177/177. A compiled host-contract package can call a declared private assembly from a later callback. OnStart logs ok. InvokeInt Measure(40) calls SharedHelper.AddOne and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 178/178. A compiled host-contract package can let one declared private assembly call another from a later callback. OnStart logs ok. InvokeInt Measure(40) goes through First.Through to Second.AddOne and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 179/179. A compiled private assembly can call back into the host-contract entry. OnStart logs ok. InvokeInt Measure(40) goes through Helper.Through to GameScript.FromEntry and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 180/180. A compiled host-contract package can construct an author type from a later callback. OnStart logs ok. InvokeInt Measure(41) constructs Box and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 181/181. PackageBuilder.Compile rejects a later callback that constructs System.InvalidOperationException. The message names Report and InvalidOperationException..ctor. No package directory is published. Publishing and staging cleanup retry an access-denied move or delete a few times. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 182/182. A compiled host-contract package can construct a type declared in a private assembly. OnStart logs ok. InvokeInt Measure(41) constructs Box from the SharedBox assembly and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 183/183. An imported host-contract IL package opens and returns an int. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok. InvokeInt Measure(40) returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 184/184. Imported host-contract IL can call a declared private assembly. The entry and SharedImport are submitted as IL. OnStart logs ok. InvokeInt Measure(40) calls AddOne and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 185/185. PackageBuilder.Import rejects host-contract IL whose later callback constructs System.InvalidOperationException. The message names Report and InvalidOperationException..ctor. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 186/186. Imported host-contract IL can let a private assembly call back into the entry. OnStart logs ok. InvokeInt Measure(40) goes through Helper.Through to GameScript.FromEntry and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 187/187. The operator CLI compile command writes a host-contract package. The test runs RuneCLR.PackageTool with --host-interface RuneCLR.IMapContext and --allowed-method Log. OnStart logs ok. InvokeInt Measure(40) returns 41. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 188/188. The operator CLI compile command rejects a later callback that constructs System.InvalidOperationException. The process exits 2. The error names Report and InvalidOperationException..ctor. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 189/189. The operator CLI import command writes a host-contract package from submitted IL. The assembly is not compiled by the package tool. OnStart logs ok. InvokeInt Measure(40) returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 190/190. The operator CLI import command rejects submitted IL whose later callback constructs System.InvalidOperationException. The process exits 2. The error names Report and InvalidOperationException..ctor. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 191/191. The operator CLI compile command accepts one --dependency and writes a host-contract package. OnStart logs ok. InvokeInt Measure(40) calls SharedHelper.AddOne and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 192/192. The operator CLI import command accepts one --dependency and writes a host-contract package from submitted IL. The entry and SharedCliImport are not compiled by the package tool. OnStart logs ok. InvokeInt Measure(40) calls AddOne and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 193/193. The operator CLI validate command accepts a host-contract manifest. The process exits 0 and prints the package id HostCliValidate and its content hash. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 194/194. The operator CLI validate command rejects a host-contract manifest whose id changed without a new content hash. The process exits 2. The error contains content identity. The package directory remains. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 195/195. The operator CLI validate command rejects a host-contract package whose entry file byte changed. The manifest content hash is left unchanged. The process exits 2. The error names that file and contains hash mismatch. The package directory remains. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 196/196. The operator CLI validate command rejects a host-contract package that contains a file absent from the manifest. The process exits 2. The error contains missing or extra files. The extra file remains. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 197/197. The operator CLI compile command rejects a host-contract build that supplies only --host-interface or only --allowed-method. The process exits 2. The error says both must be present. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 198/198. The operator CLI --help exits 0 and mentions --host-interface. An unknown command, compile without --framework-refs, and a repeated --id each exit 2. The errors name the unknown command, the missing option, and the repeated option. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 199/199. The operator CLI compile command rejects a repeated allowed method and a blank allowed method. Both processes exit 2. The error says the methods must be nonempty and unique. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 200/200. The operator CLI compile command rejects a source directory that also contains a .csproj file. The process exits 2. The error says source input must contain only regular .cs files. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 201/201. The operator CLI compile command rejects a source tree nested past 16 directories. The process exits 2. The error says source directories exceed the nesting limit. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 202/202. The operator CLI compile command rejects a source directory that is a filesystem link and a source directory that contains one. Both processes exit 2. The error says source directories cannot contain filesystem links. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 203/203. The operator CLI compile command rejects 65 source files and one source file of 8000001 bytes. Both processes exit 2. The error says the source directory exceeds the compiler input limits. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 204/204. The operator CLI rejects an unknown option, an option with no value, and a value that starts with --. Each process exits 2. The error says unknown option or missing value. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 205/205. The operator CLI compile command rejects a source file that names MissingType. The process exits 2. Standard output contains success false and CS0246. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 206/206. The operator CLI import command rejects a file that is not a managed assembly. The process exits 2. The error says the image is a malformed managed assembly. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 207/207. The operator CLI import command rejects an assembly that does not define GameScript. The process exits 2. The error says that entry type was not found. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 208/208. A compiled host-contract package can take only an int in a later callback. OnStart logs ok. Invoke Apply(41) calls Charge with 41. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 209/209. A compiled host-contract package can take the host and an int and return an int. OnStart logs ok. InvokeInt Measure(40) calls Charge with 40 and returns 41. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 210/210. Imported host-contract IL can take the host and an int and return an int. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok. InvokeInt Measure(40) calls Charge with 40 and returns 41. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 211/211. Imported host-contract IL can take only an int in a later callback. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok. Invoke Apply(41) calls Charge with 41. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 212/212. Imported host-contract IL can take the host and an int in a later void callback. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok. Invoke Report(41) calls Charge with 41. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 213/213. Imported host-contract IL can run a later callback after Open. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok, and Invoke OnStop logs stopped through the same IMapContext. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 214/214. Imported host-contract IL can construct an author type from a later callback. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok. InvokeInt Measure(41) constructs Box and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 215/215. Imported host-contract IL can construct a type declared in a private assembly. The entry and SharedImportBox are submitted as IL, not compiled by PackageBuilder. OnStart logs ok. InvokeInt Measure(41) constructs Box and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 216/216. Imported host-contract IL can let one declared private assembly call another. The entry, SharedImportFirst, and SharedImportSecond are submitted as IL, not compiled by PackageBuilder. OnStart logs ok. InvokeInt Measure(40) goes through First.Through to Second.AddOne and returns 41. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 217/217. Imported host-contract IL can run OnStart with Log and SpawnEntity. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok and spawns fixture. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 218/218. A compiled host-contract package can call Charge from OnStart. OnStart logs ok and charges 7. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 219/219. Imported host-contract IL can call Charge from OnStart. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok and charges 7. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 220/220. A compiled host-contract package can spawn and destroy an entity from OnStart. OnStart logs ok, spawns fixture, and destroys that entity. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 221/221. Imported host-contract IL can spawn and destroy an entity from OnStart. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok, spawns fixture, and destroys that entity. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 222/222. A compiled host-contract package can read MapId from OnStart. The allowed names are Log and get_MapId. OnStart logs fixture. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 223/223. Imported host-contract IL can read MapId from OnStart. The assembly is submitted as IL, not compiled by PackageBuilder. The allowed names are Log and get_MapId. OnStart logs fixture. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 224/224. A compiled host-contract package can store a spawned EntityId and destroy it from a later callback. OnStart logs ok and spawns fixture. Invoke Release destroys that entity. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 225/225. Imported host-contract IL can store a spawned EntityId and destroy it from a later callback. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok and spawns fixture. Invoke Release destroys that entity. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 226/226. A compiled host-contract package rejects an allow list that names MapId instead of get_MapId. The error names OnStart and get_MapId. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 227/227. Imported host-contract IL rejects an allow list that names MapId instead of get_MapId. The assembly is submitted as IL, not compiled by PackageBuilder. The error names OnStart and get_MapId. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 228/228. A compiled host-contract package can read MapId from a later callback. OnStart logs ok. Invoke OnStop logs fixture through the stored IMapContext. Log and get_MapId are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 229/229. Imported host-contract IL can read MapId from a later callback. The assembly is submitted as IL, not compiled by PackageBuilder. OnStart logs ok. Invoke OnStop logs fixture through the stored IMapContext. Log and get_MapId are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 230/230. The operator CLI compile command accepts --allowed-method get_MapId. OnStart logs fixture. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 231/231. The operator CLI import command accepts --allowed-method get_MapId. The assembly is submitted as IL, not compiled by the package tool. OnStart logs fixture. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 232/232. The operator CLI compile command rejects --allowed-method MapId when the script reads the property. The process exits 2. The error names OnStart and get_MapId. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 233/233. The operator CLI import command rejects --allowed-method MapId when the assembly reads the property. The assembly is submitted as IL, not compiled by the package tool. The process exits 2. The error names OnStart and get_MapId. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 234/234. A compiled host-contract package can let a declared private assembly read MapId. OnStart passes the host to SharedMap.Id and logs fixture. Log and get_MapId are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 235/235. Imported host-contract IL can let a declared private assembly read MapId. The entry and SharedImportMap are submitted as IL, not compiled by PackageBuilder. OnStart passes the host to SharedMap.Id and logs fixture. Log and get_MapId are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 236/236. A compiled host-contract package can let a declared private assembly call Charge. OnStart logs ok and passes the host to SharedBill.Bill, which charges 7. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 237/237. Imported host-contract IL can let a declared private assembly call Charge. The entry and SharedImportBill are submitted as IL, not compiled by PackageBuilder. OnStart logs ok and passes the host to SharedBill.Bill, which charges 7. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 238/238. A compiled host-contract package can let a declared private assembly spawn an entity. OnStart logs ok, passes the host to SharedSpawn.Create, and destroys the returned entity. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 239/239. Imported host-contract IL can let a declared private assembly spawn an entity. The entry and SharedImportSpawn are submitted as IL, not compiled by PackageBuilder. OnStart logs ok, passes the host to SharedSpawn.Create, and destroys the returned entity. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 240/240. A compiled host-contract package can let a declared private assembly spawn and destroy an entity. OnStart logs ok and passes the host to SharedLife.Cycle. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 241/241. Imported host-contract IL can let a declared private assembly spawn and destroy an entity. The entry and SharedImportLife are submitted as IL, not compiled by PackageBuilder. OnStart logs ok and passes the host to SharedLife.Cycle. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 242/242. A compiled host-contract package can let a declared private assembly call Log. OnStart logs ok and passes the host to SharedNote.Note, which logs from-private. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 243/243. Imported host-contract IL can let a declared private assembly call Log. The entry and SharedImportNote are submitted as IL, not compiled by PackageBuilder. OnStart logs ok and passes the host to SharedNote.Note, which logs from-private. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 244/244. A compiled host-contract package can pass the host from one private assembly into a second that calls Log. OnStart logs ok. First.Through reaches Second.Note, which logs from-second. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 245/245. Imported host-contract IL can pass the host from one private assembly into a second that calls Log. The entry, SharedImportLogFirst, and SharedImportLogSecond are submitted as IL, not compiled by PackageBuilder. OnStart logs ok. First.Through reaches Second.Note, which logs from-second. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 246/246. A compiled host-contract package rejects a second private assembly that calls SpawnEntity when only Log is allowed. The error names OnStart and SpawnEntity. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 247/247. Imported host-contract IL rejects a second private assembly that calls SpawnEntity when only Log is allowed. The assemblies are submitted as IL, not compiled by PackageBuilder. The error names OnStart and SpawnEntity. No package directory is published. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 248/248. A compiled host-contract package can let a second private assembly read MapId. OnStart passes the host through First.Through to Second.Id and logs fixture. Log and get_MapId are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 249/249. Imported host-contract IL can let a second private assembly read MapId. The entry, SharedImportIdFirst, and SharedImportIdSecond are submitted as IL, not compiled by PackageBuilder. OnStart passes the host through First.Through to Second.Id and logs fixture. Log and get_MapId are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 250/250. A compiled host-contract package can let a second private assembly call Charge. OnStart logs ok and passes the host through First.Through to Second.Bill, which charges 7. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 251/251. Imported host-contract IL can let a second private assembly call Charge. The entry, SharedImportBillFirst, and SharedImportBillSecond are submitted as IL, not compiled by PackageBuilder. OnStart logs ok and passes the host through First.Through to Second.Bill, which charges 7. Log and Charge are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 252/252. A compiled host-contract package can let a second private assembly spawn and destroy an entity. OnStart logs ok and passes the host through First.Through to Second.Cycle. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 253/253. Imported host-contract IL can let a second private assembly spawn and destroy an entity. The entry, SharedImportLifeFirst, and SharedImportLifeSecond are submitted as IL, not compiled by PackageBuilder. OnStart logs ok and passes the host through First.Through to Second.Cycle. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 254/254. A compiled host-contract package can return an EntityId from a second private assembly. OnStart logs ok, passes the host through First.Through to Second.Create, and destroys the returned entity. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 255/255. Imported host-contract IL can return an EntityId from a second private assembly. The entry, SharedImportReturnFirst, and SharedImportReturnSecond are submitted as IL, not compiled by PackageBuilder. OnStart logs ok, passes the host through First.Through to Second.Create, and destroys the returned entity. Log, SpawnEntity, and DestroyEntity are allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 256/256. The operator CLI compile command accepts two --dependency arguments. OnStart logs ok and passes the host through First.Through to Second.Note, which logs from-second. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 packaging tests passed 257/257. The operator CLI import command accepts two --dependency arguments. The assemblies are submitted as IL, not compiled by the package tool. OnStart logs ok and passes the host through First.Through to Second.Note, which logs from-second. Only Log is allowed. The session is disposed after that call. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 258/258. The operator CLI validate command accepts a host-contract package with two private assemblies, then rejects that package after one byte in the second assembly changes. The error names the hash mismatch and lib/SharedCliSealSecond.dll. The changed file stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 259/259. The operator CLI validate command accepts a host-contract package with one private assembly. After the manifest assembly identity is changed to Version=9.0.0.0 and the content hash is recomputed, validate exits 2. The error names identity mismatch and lib/SharedCliIdentity.dll. The dependency file stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 260/260. The operator CLI validate command accepts a host-contract package, then rejects it after the entry assembly is replaced by a filesystem link to the moved DLL. The error names filesystem links. The link and its target stay in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 261/261. The operator CLI validate command accepts a host-contract package, then rejects it after 17 nested directories are added inside the package. The error names Package directories and the nesting limit. The nested directory stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 262/262. The operator CLI validate command accepts a host-contract package, then rejects it after the entry bytes are replaced by an assembly named System.IO and the file and content hashes are recomputed. The error names spoofs and System.IO. The entry file stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 263/263. The operator CLI validate command accepts a host-contract package, then rejects it after the entry file is extended past the assembly size limit. The error names size limits. The oversized file stays in place and is not hashed. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 264/264. The operator CLI validate command accepts a host-contract package, then rejects it after the format version is increased and the content hash is recomputed. The error names Unsupported package format. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 265/265. The operator CLI validate command accepts a host-contract package, then rejects it after the producer input kind is changed to native and the content hash is recomputed. The error names Unsupported producer input kind. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 266/266. The operator CLI validate command accepts a host-contract package, then rejects it after the producer references are removed and the content hash is recomputed. The error names Producer references identities are required. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 267/267. The operator CLI validate command accepts a host-contract package, then rejects it after the producer references name Other.Contract instead of the shared host contract and the content hash is recomputed. The error names exactly one shared host contract. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 268/268. The operator CLI validate command accepts a host-contract package, then rejects it after the package id is a single space and the content hash is recomputed. The error names Missing or oversized id. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 269/269. The operator CLI validate command accepts a host-contract package, then rejects it after the producer tool is a single space and the content hash is recomputed. The error names Missing or oversized producer.tool. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 270/270. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path is changed to ../entry.dll and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 271/271. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path is changed to bad./echo.dll and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 272/272. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path is changed to entry.txt and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 273/273. The operator CLI validate command accepts a host-contract package, then rejects it after the file list names other.dll instead of the entry and the content hash is recomputed. The error names exactly match the entry. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 274/274. The operator CLI validate command accepts a host-contract package, then rejects it after the file list keeps the entry path but stores a different SHA-256 and the content hash is recomputed. The error names exactly match the entry. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 275/275. The operator CLI validate command accepts a host-contract package with one private assembly, then rejects it after that dependency path is changed to ../lib.dll and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 276/276. The operator CLI validate command accepts a host-contract package with one private assembly, then rejects it after that dependency is replaced by the bytes 1, 2, 3, 4 and the file and content hashes are recomputed. The error names PE. The dependency file stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 277/277. The operator CLI validate command accepts a host-contract package with one private assembly, then rejects it after that dependency is replaced by an assembly named System.IO and the file hash, content hash, and declared assembly identity are updated to match. The error names spoofs and System.IO. The dependency file stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 278/278. The operator CLI validate command accepts a host-contract package with one private assembly, then rejects it after that dependency is replaced by another assembly named HostCliDup and the file hash, content hash, and declared assembly identity are updated to match. The error names duplicates the entry assembly identity. The dependency file stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 279/279. The operator CLI validate command accepts a host-contract package with one private assembly, then rejects it after that dependency is declared as RuneCLR.Abstractions and the content hash is recomputed. The dependency bytes stay unchanged. The error names contract or duplicate private assembly identity. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 280/280. The operator CLI validate command accepts a host-contract package with two private assemblies, then rejects it after the second dependency is declared with the first dependency assembly identity and the content hash is recomputed. The dependency bytes stay unchanged. The error names contract or duplicate private assembly identity. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 281/281. The operator CLI validate command accepts a host-contract package with one private assembly, then rejects it after that dependency file is deleted. The manifest is left unchanged. The error names missing or extra files. The manifest stays in place and the dependency file stays absent. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 282/282. The operator CLI validate command accepts a host-contract package, then rejects it after the producer tool version is a single space and the content hash is recomputed. The error names Missing or oversized producer.toolVersion. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 283/283. The operator CLI validate command accepts a host-contract package, then rejects it after the producer sources are removed and the content hash is recomputed. The error names Producer sources identities are required. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 284/284. The operator CLI validate command accepts a source host-contract package, then rejects it after the producer compiler identities are removed and the content hash is recomputed. The error names Producer compiler identities are required. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 285/285. The operator CLI validate command accepts a source host-contract package, then rejects it after the producer compiler list is two copies of the first compiler identity and the content hash is recomputed. The error names Duplicate producer compiler input name. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 286/286. The operator CLI validate command accepts a host-contract package, then rejects it after the producer source list is two copies of the first source identity and the content hash is recomputed. The error names Duplicate producer sources input name. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 287/287. The operator CLI validate command accepts a host-contract package, then rejects it after the producer reference list is two copies of the first reference identity and the content hash is recomputed. The error names Duplicate producer references input name. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 288/288. The operator CLI validate command accepts a host-contract package, then rejects it after a second producer reference uses another input name but the same RuneCLR.Abstractions identity and the content hash is recomputed. The error names exactly one shared host contract. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 289/289. The operator CLI validate command accepts a host-contract package, then rejects it after the first producer source digest is changed to invalid and the content hash is recomputed. The error names SHA-256 hexadecimal digest. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 290/290. The operator CLI validate command accepts a host-contract package, then rejects it after the first producer source name is a single space and the content hash is recomputed. The error names Missing or oversized input name. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 291/291. The operator CLI validate command accepts a host-contract package, then rejects it after the first producer reference assembly identity is changed to NotCanonical and the content hash is recomputed. The error names full canonical assembly identity. This does not compare contract versions. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 292/292. The operator CLI validate command accepts a host-contract package, then rejects it after the file list repeats the entry path with the same entry hash and the content hash is recomputed. The error names Duplicate package path and that entry path. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 293/293. The operator CLI validate command accepts a host-contract package, then rejects it after the entry file is deleted. The manifest is left unchanged. The error names missing or extra files. The manifest stays in place and the entry file stays absent. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 294/294. The operator CLI validate command accepts a host-contract package, then rejects it after the API version is increased while the format version stays current and the content hash is recomputed. The error names API version. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 295/295. The operator CLI validate command accepts a host-contract package, then rejects it after the input profile is changed to other while the format version and API version stay current and the content hash is recomputed. The error names input profile. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 296/296. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path is changed to bad /echo.dll and the content hash is recomputed. The segment before the slash ends with a space. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 297/297. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path is changed to bad//echo.dll and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 298/298. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path uses a backslash instead of a forward slash and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 299/299. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path is changed to bad:echo.dll and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 300/300. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path is changed to echo?.dll and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 301/301. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path contains a tab and the content hash is recomputed. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 302/302. The operator CLI validate command accepts a host-contract package, then rejects it after the entry path is changed to ./echo.dll and the content hash is recomputed. The segment is only a dot, not a segment that ends with a dot. The error names canonical relative DLL. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 303/303. The operator CLI validate command accepts a host-contract package, then rejects it after the content hash is changed to invalid and is not recomputed. The error names SHA-256 hexadecimal digest. This is the package content identity, not a producer source digest. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 304/304. The operator CLI validate command accepts a host-contract package, then rejects it after the entry hash is changed to invalid and the content hash is recomputed. The error names SHA-256 hexadecimal digest. This is the entry hash, not the package content identity. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 305/305. The operator CLI validate command accepts a host-contract package, then rejects it after the file list keeps the entry path but its digest is changed to invalid, while the entry hash field stays the original digest and the content hash is recomputed. The error names SHA-256 hexadecimal digest. This is the file list digest, not the entry hash field. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.

On 2026-10-17 packaging tests passed 306/306. The operator CLI validate command accepts a host-contract package, then rejects it after the package id is 129 letters and the content hash is recomputed. The error names Missing or oversized id. The id is not blank. The manifest stays in place. Only Log is allowed. Gameplay validation is unchanged. This is not an iOS result.


On 2026-10-17 the desktop score-game sample runs two managed-IL script versions and a failing script through HostContractSession. The contract is ScoreGame.IScoreRules in samples/ScoreGame.Contracts, not RuneCLR.Abstractions or IMapContext. See score-game.md. This is not an iOS result.

## Preserve experiment evidence

On 2026-10-12, a separate Release interpreter performance experiment compared
four warmed kernels against Lua 5.4.9 and V8 with/without JIT. Object update and
state-machine costs were near Lua on this Windows x64 machine; the numeric
recurrence was slower, and C# JIT was substantially faster. See
[the measured results and limits](performance-experiment.md). This experiment
does not establish device/frame performance. A subsequent desktop increment
measured host API calls, allocations/generics, real fresh-map sessions and
three forty-session retention runs per backend. All observed contexts collected
after diagnostic GC; process-private bytes did not immediately return to baseline.
See [the session results and their distinct timing scopes](session-performance.md).
These standalone benchmark projects leave production host behavior unchanged.
The later accepted execution
direction and its limits are recorded in [the strategy decision](execution-strategy.md).

For each actual runtime experiment, record the upstream base, runtime patch
commit, host commit, OS/architecture, build configuration, runtime/library layout,
switches, proof of interpreted execution, reproduction command, and outcome.
Distinguish a failed experiment from an unperformed one. Do not fill these fields
with presumed results or reuse an unexplained artifact directory as evidence.

Update this handoff when the verified baseline changes. Keep detailed source
history in Git and machine paths in the ignored local setup document.
