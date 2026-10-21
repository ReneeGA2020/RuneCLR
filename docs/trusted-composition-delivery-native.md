# Signed delivery native proof

This driver measures Windows x64 ReadyToRun execution after a signed local
stage and a later process recovery. It is not an iOS result, not a platform
signature gate, not a network transport, and not an anti-rollback log.
The older collectible-module R2R blocker is a different milestone and is not
reported here as success or failure of this startup path.

Run from the repository root:

    py -3 eng/verify-trusted-composition-delivery.py --runtime E:/runtime --output <fresh-directory>

The driver checks the pinned private runtime commit and the reviewed hashes of
coreclr.dll, clrinterpreter.dll, clrjit.dll, System.Private.CoreLib.dll, and
crossgen2 before it builds anything. Managed sources stay on the current
net11.0 SDK. The copied DeliveryHost runtimeconfig in the fresh output is
retargeted to Microsoft.NETCore.App 12.0.0 and the apphost is started with
DOTNET_ROOT pointed at the private testhost layout. The installed runtime is
not replaced.

The frozen source guard now requires the reviewed typed DeliverySession,
TypedSession and combined IntegrationProbe overlay. Missing files or a hash
change reject the closure before native compilation. The guard update leaves
all 30 parser, timeline and proof functions unchanged; the lead independently
checked six negative guard cases and ran the portable probe from a tree
containing only the driver. Evidence is
`artifacts/lead-typed-driver-audit-20261018i/receipt.json`.
The isolated v2 native initial-activation regression is accepted separately at
`artifacts/lead-typed-native-v2-audit-20261018g/receipt.json`. Its test overlay
predates the combined probe. The promoted canonical closure has since passed
its own real two-lane run, with the lead checking all 37 frozen files, actual
product hashes, raw process facts, receipt timelines and method/entry evidence.
The audit is `artifacts/lead-canonical-native-audit-20261018l/receipt.json`;
raw results are `artifacts/typed-delivery-native-canonical-20261018k/result.json`.
Both versions prove initial activation only; neither proves repeated native
calls in one session.

A separate call-scoped measurement now has scoped lead acceptance after the
r4 validator replay and independent Orca Worker review: eight processes, 14
call segments, 21 enabled method bindings and zero disabled raw witnesses. It
reuses the frozen v2 Host rather than recompiling the canonical Host. Evidence
is `artifacts/lead-call-scope-r4-acceptance-20261018aq/receipt.json`. The lead
separately enforces zero disabled witnesses; r4 alone does not reject every
unbound witness. This does not extend the initial-activation driver itself.

The minimal r5 revision now rejects every parsed disabled witness, including
unbound and out-of-scope events. Lead replay passes 26 protocol mutations and
eight disabled-witness mutations while accepting eight shared PC tuples from
real enabled calls. Evidence is
`artifacts/lead-call-scope-r5-review-20261018at/receipt.json`. This is lead review
of a replay-only revision of the independently reviewed r4 parent. A portable
canonical-product repeated-call draft has now been delivered by an Orca Worker;
its new measurement remains under lead review before any eng or CI promotion.

Update and private assemblies are crossgen'd independently. The IL-only helper
is not crossgen'd and is not part of a composite image. The C# harness keeps
the ECDSA private key in memory, writes only the SPKI and signed documents,
and drains host stdout and stderr together.

The managed build still uses the Host project graph, which also builds the
update projects. It is followed by separate crossgen invocations. This proves
independent R2R composition; it does not separately record an edited update
compiled after the installed Host closure was sealed. The build-order audit is
`artifacts/lead-post-seal-update-build-audit-20261018z/receipt.json`. A follow-up
must seal the host first, compile changed update sources in a separate tree,
observe the new behavior and native entries, and prove every installed-host
file hash remains unchanged. That experiment is assigned to an Orca Worker.
The lead's current read-only preflight matches all 17 prepared host files,
checks four assemblies without update/private/helper static dependencies,
and matches the private runtime's four binary hashes and crossgen to the
canonical baseline. Evidence is
`artifacts/lead-post-seal-preflight-20261018af/receipt.json`. This checks the
current prepared inputs; it does not establish a post-seal build or new native
execution. The worker must capture its own host/config seal before the new
update-source revision and record runtime identity around the actual run.

The first post-seal delivery has changed Update/Private IL and R2R products.
The lead's read-only PE comparison confirms identical managed method bodies
and metadata after normalizing only relocated MethodDef RVAs: three private
methods and four update methods. An old update product fails that comparison.
Evidence is `artifacts/lead-post-seal-il-parity-20261018am/receipt.json`.
Same-MVID copies with a changed Read IL body or changed type metadata are both
rejected while the untouched pair passes; original inputs remain unchanged.
These diagnostic-only controls are at
`artifacts/lead-il-parity-controls-20261018ap/receipt.json`.
This is product parity, not acceptance of build chronology or native execution.
The original orchestration did not persist its timeline or original process
exits. Separate exitcheck processes cannot supply those missing returncodes.
The lead records the gap at
`artifacts/lead-post-seal-delivery-triage-20261018al/receipt.json`; a complete
durably recorded run and independent review are assigned to Orca Workers.

The newer durable2 measurement records all five real scenario exits
(enabled/disabled/stale/recover/author-fail: 0/0/0/0/1), 16 command pairs and
ordered host-seal, public-pin, source-write and build events. The lead verifies
17 unchanged host files, receipt stability and final helper identities at
`artifacts/lead-post-seal-durable2-review-20261018au/receipt.json`. This does not
repair the old run. Its checker accepts duplicate FACTS, malformed disabled
witnesses and a version-only stale difference. The strict checker revision now
passes lead replay with 19 original and 30 additional targeted negatives,
including transaction facts, exact failure classification and helper identity.
All 211 raw-input files and the original public pin remain unchanged. Evidence
is `artifacts/lead-post-seal-strict-review-20261018ba/receipt.json`. Independent
Orca Worker review subsequently found five further predicate gaps: success
Recovery tokens, the author-fail version, shared fields substituting for stale
gameplay differences, missing native checks on three lanes, and stale helper
identity. That strict revision is not accepted. Findings are preserved at
`artifacts/post-seal-strict-replay-review-k6zi/review.md`; a fresh checker-only
revision is required without changing the historical pin or raw streams.
The subsequent F1-F5 candidate (checker 7cd1d9f1) passes a targeted lead replay
of five actual 0/0/0/0/1 processes and 28 mutations. The 211-file raw closure
and pin remain unchanged. Evidence is
`artifacts/lead-current-delivery-disposition-20261018bh/strict-f1f5-lead-replay.json`.
Independent review confirms the F1-F5 repairs but rejects this candidate:
Update/Private expected paths still come from stdout FACTS. Consistently moving
FACTS and witness paths to same-byte copies is accepted in all four enabled
scenarios. The lead reproduces all eight full-path/Loaded-only cases at
`artifacts/lead-post-seal-final-path-20261018bm/receipt.json`.
The recorded-final-path repair subsequently anchors paths to command records.
Its stage-provenance derivative 3b0cedf3 closes duplicate-key last-wins selection
and pins two local stale maps, explicitly outside the historical 211 files.
Independent Orca Worker review rejects it because an outside final still
becomes an expectation after reporting expected-final-outside. The lead
reproduces three affected expectations with same-byte payload copies at
`artifacts/lead-post-seal-containment-20261018cb/receipt.json`. The batch entry
point would abort, so this does not invalidate the five recorded raw streams.
That rejected generation required null expectations for that stage and its
recovery users. Review is
`artifacts/post-seal-stage-provenance-review-k6zi-20261018/review.md`.
Historical raw files and the original pin remain unchanged.
The fresh 4bcceeed replay derivative withholds outside stages while keeping
them visible for duplicate-key rejection; recovery now selects only valid
staged keys. Lead copied replay passes all five real streams and four direct
same-byte outside/collision controls with null expectations. Evidence is
`artifacts/lead-post-seal-containment-replay-20261018cg/receipt.json`.
Independent Orca Worker review now grants scoped acceptance. The joined lead
adjudication is `artifacts/lead-post-seal-acceptance-20261018cj/receipt.json`.
This is offline checker acceptance without a native rerun. A command missing
`--final` is rejected before duplicate membership; a valid sibling may still
derive expectations, while batch main aborts on any problem. The five-file
derivative closure excludes existing evidence-tool dependencies and does not
claim a hermetic whole-tool closure.

Read-only PE checks of the durable2 products independently pass three private
and four update methods, metadata except MethodDef RVA relocation, both final
helper metadata dumps and three sealed Contract binary references. The old
update fails the same comparison. Evidence is
`artifacts/lead-durable2-product-parity-20261018av/receipt.json`; this establishes
product parity without another native run.

The game-owned step-2 interface experiment has also been delivered. Lead raw
review confirms five real exits, 17 round scopes, four recovery scopes and 187
enabled-round witnesses. It reproduces checker gaps for missing round scopes,
wrong call values, incorrect recovery source, an unclosed final scope and a
same-bytes witness image at the wrong path. Evidence is
`artifacts/lead-native-score-review-20261018aw/receipt.json`. Preserve the raw
measurement and fix its replay checker before claiming acceptance. This remains
an isolated Windows x64 experiment, without SDK or iOS promotion.

Lead source/product audit separately confirms 36 unchanged baseline files,
six diagnostic CLI lines and one new probe source, with gate, resolver,
signing, recovery and session algorithms unchanged. Host IL/R2R parity covers
597 methods and three static initializers; the good and mutant modules each
cover five methods. Normalizing both method and field-data address columns
leaves identical metadata, while a same-MVID static-data mutation is rejected.
All five final process payload directories contain only the module, using the
sealed Contract type identity. Evidence is
`artifacts/lead-native-score-product-audit-20261018bb/receipt.json`. This does
not accept the pending native-score checker or rerun native execution.

The score r2 offline checker subsequently passes lead replay of all five raw
processes, 14 original negatives and nine additional business/failure/native
negatives. Independent Orca Worker review scoped-accepts the existing Windows
x64 private-runtime measurement. The lead joins that review, source/product
parity and a fresh offline replay at
`artifacts/lead-score-acceptance-map-check-20261018bi/score-acceptance.json`.
The five original exits remain 0/0/0/0/1; this acceptance does not rerun native
execution or promote a reusable public API. Summary-line presence checks can
accept contradictory extra SOURCE lines, and binding requires a valid witness
per label without rejecting every extra invalid row. Private-key deletion
occurred after the first process. These limitations remain recorded in the
acceptance. Successful CALL lines retain their original shape without an
invented Completed field.

The relocated canonical repeated-call revision has now delivered a fresh
eight-process batch using copied products and moved driver sources. Its maps
use bundle-relative paths, preflight pins runtime hashes, and replay-only
mode is separately labeled. Raw result is
`artifacts/canonical-call-relocated-20261018-bocx5e/run-fresh/result.json`.
Independent review of relocation, closure and evidence remains required before
eng or CI promotion; the earlier draft's missing snapshots are not backfilled.
Lead replay verifies the eight actual exits, 13 command pairs, 28 recorded
inputs, 14 scopes and 21 bindings, but reproduces a remaining map-reference
gap: the table can name an unpinned bundle file that selected_files omits.
Evidence is `artifacts/lead-canonical-relocated-review-20261018bd/receipt.json`.
The actual table uses correct pinned files; retain the raw evidence and repair
reference pinning/snapshots before accepting the reusable driver.
The actual canonical repeated-call measurement now has lead and independent
Orca Worker scoped acceptance at
`artifacts/lead-current-delivery-disposition-20261018bh/canonical-measurement-acceptance.json`.
It uses the delivered correct table and recorded files. Acceptance covers that
Windows x64 private-runtime measurement; the reusable driver remains pending
map repair, and the run does not have a hermetic compiler-input closure.
The map-reference repair now passes lead preflight and validator-only replay:
six image digests select their pinned map bytes, and a byte-identical alias
is included in the frozen inputs. Changing that alias is rejected before
author loading and changes its snapshot. Evidence is
`artifacts/lead-score-acceptance-map-check-20261018bi/map-lead-check.json`.
Independent Orca Worker review now accepts the exact repair. The lead verified
the six map identities and 331 unchanged protected files and recorded scoped
acceptance at `artifacts/lead-map-closure-acceptance-20261018bj/receipt.json`.
This offline acceptance does not backfill the historical 28-file snapshot or
establish another native measurement. B DLL bytes are absent from this bundle;
the two B image digests are pinned to their corresponding map CSV hashes only.

A positive lane must bind each update Execute, private Read, and
DeliveryHostObject.Touch PC to the signed image SHA-256, an executable PE
section, an R2R RuntimeFunction, and that method's crossgen map. A negative
lane runs the same R2R bytes with DOTNET_ReadyToRun=0 and those matches must
be absent. Helper interpreter execution is proven only by precode 6 plus this
run's successful Compute IR dump. An environment variable alone is not proof.
If the host source does not build, the result status is host-build-blocked.

The harness records the receipt hash and final-tree hashes immediately before and after each host process. Later reads of those paths are not used as the timeline. Loaded entry, private, and helper paths must equal the signed final files, and each witness image must be that same path rather than another copy with the same hash. Helper observations must name that final helper. Contract ReadyToRun output replaces the contract assembly beside the host, and host crossgen receives the host's real managed references, including RuneCLR.TrustedUpdate.dll.

Managed Console lines and native interpreter printf share stdout, so a marker may begin in the middle of a diagnostic line. FACTS, WITNESS, and ENTRYOBSERVATION are decoded with JSONDecoder.raw_decode after the marker. DeliveryFacts names are mapped explicitly, including PrivateValue to PRIVATE and LoadedEntry to LOADED_ENTRY. One complete FACTS object is authoritative for that process. Human text cannot override it, and several FACTS objects are not collapsed into the last activation. Rejected markers stay in parseFailures. Original stdout and stderr bytes are kept beside each step.

Helper interpreter proof requires Interpreted true, precode 6, invocation evidence, this run Compute IR, and the signed final helper path. Interpreted false, a missing IR dump, or missing invocation evidence is not proof. Host crossgen references include DeliveryAppDep.dll, RuneCLR.TrustedUpdate.dll, and the contract. The r2r host directory is copied from the apphost directory.


The portable protocol probe does not execute native code and does not read historical artifacts or a private runtime:

    py -3 eng/verify-trusted-composition-delivery.py --probe --output <fresh-directory>

Its vectors are synthetic FACTS, WITNESS, ENTRYOBSERVATION, and Compute IR text constructed in the driver. probe passed is not a native execution result. An optional stdout replay is a parser check only:

    py -3 eng/verify-trusted-composition-delivery.py --probe --output <fresh-directory> --probe-log <stdout-file>

The accepted native measurement stays Windows x64: one signed ReadyToRun lane and the same payload bytes with ReadyToRun off. Lead acceptance is artifacts/lead-signed-native-acceptance-e432a00639f14acca37b77e7f2df8efd. The driver receipt is artifacts/trusted-composition-delivery-20261018-rerun4. Those runs are not iOS, a platform signature gate, a network service, anti-rollback, or collectible native R2R.

The lead also ran the same portable-probe source on macOS arm64 with Python
3.9.6. The fresh source tree contained only the driver and no artifacts; the
command exited 0 with probe passed and empty stderr. The driver SHA-256 matched
the accepted Windows portable-probe source. Evidence is named by
artifacts/lead-macos-portable-probe-acceptance-path.txt. This is a synthetic
protocol check on macOS, not macOS native execution evidence.
