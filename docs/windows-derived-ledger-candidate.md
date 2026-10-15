# Windows terminal derived-ledger candidate

On 2026-10-14, an isolated runtime candidate implements terminal admitted counts
as immutable initial allowance minus an atomic remaining read. Execution and
cleanup retain separate allowances. A successful debit still admits exactly
one interpreter opcode; there are no reservations, counter batches or delayed
terminal checks. Diagnostic mode retains its independent saturating counter
and continues accounting after its remaining allowance reaches zero.

This candidate is committed and has passed native header tests and a fresh
matching Windows x64 Release CLR build. All 16 ON/OFF functional commands and
the static native-path review pass. Four live hot-loop witnesses and the
[new bracketed performance experiment](windows-derived-ledger-performance.md)
also pass. ON configured callback time falls 8.1%/9.6% against the parents;
its configured/no-config ratio is3.60x. The accepted
[phase-load products and timings](windows-phase-load-performance.md) remain
the baseline. Neither this change nor those desktop results establish device
execution or real-game frame costs.

## Isolated source

| Item | Value |
| --- | --- |
| Upstream | `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` |
| Direct parent | `a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186` |
| Candidate | `29ff781e157be82ba5a398a60bb05291e4a865af` |
| Candidate tree | `685cb628b9cd5432e5589f8b0b6554b300915e76` |
| Separate worktree | `E:/runtime-derived-ledger-20261014` |
| Branch | `runeclr/terminal-derived-ledger` |
| New switch | `DOTNET_RuneCLRDerivedLedger=1`, default `0` |
| Changed files | `src/coreclr/inc/clrconfigvalues.h`, `src/coreclr/vm/runeclrinstructionmeter.h` |

The immutable switch is read during terminal-meter construction only.
Nonterminal diagnostic meters cannot opt in. The phase-load switch remains
independent. OFF retains the old counter updates; ON skips the separate
executed increment after a successful remaining CAS. Remaining reads, debit
CAS, exhaustion latches, dispatch owner selection and exception handling are
unchanged. The legacy `Charge()` body is unchanged.

The candidate appends two immutable initial allowances, rather than reusing
counter slots for different data. Existing field offsets remain; the new flag
occupies offset 3, and execution/cleanup initial allowances occupy 48/56.
Meter size changes from 48 to 64 bytes, alignment 8, so matching native binder
products must be rebuilt. In ON terminal mode the old executed-counter slots
stay zero and are not authoritative: observers must use the scalar getters
and preserve the exact build/layout contract. Old 48-byte debugger evidence
cannot verify this new layout.

The [exported patch and reproduction record](runtime-patch-reproduction.md)
preserve a separate inventory. Fresh source reconstruction passes eight
desktop patches and exactly 36 changed files; two optional upstream defect
patches also apply in a separate snapshot. This optimization is local RuneCLR
work, not a new Microsoft defect. Source application is not native execution.

## Observation semantics

Counts mean CAS-admitted dispatches, including an admitted opcode that later
throws or is still running. ON getters include an admission as soon as its
debit CAS succeeds. OFF has a real interval between that CAS and the separate
counter increment. At quiescence both ledgers agree; their in-flight observation
timing differs deliberately. Separate Remaining/Executed host getter calls
remain nontransactional, as do the phase and cleanup observations.

Positive terminal allowances and unit decrements ensure subtraction stays
within signed 64-bit range. The host's existing positive-allowance validation
remains part of the contract. The
[source/algebra review](../artifacts/budget-batching/derived-ledger-review-20261014-attempt1/review.md)
explains why diagnostic post-exhaustion counts cannot use this formula.

## Actual native header acceptance

The [header driver](../eng/verify-derived-ledger-header.py) compiles a frozen
copy of the actual candidate header using Windows x64 MSVC with real CAS32,
CAS64 and Increment64 intrinsics. The
[fixture](../eng/derived-ledger-header-probe/probe.cpp) supplies controllable
CLRConfig values and a thin MSVC volatile-load wrapper, preserving the
runtime's AMD64 load convention. This is header-level testing with runtime
helpers wrapped for observation; it does not run CoreCLR.

The [actual receipt](../artifacts/derived-ledger/header-semantics-20261014-attempt1/results.json)
passes 41 cases and 807 checks, compile/run exit 0, without compiler warnings
or errors. It binds compiler, fixture, frozen header, executable, object and
raw streams. The actual/frozen header SHA-256 is
`efe68bcc740ceac4e12237ebc7d8ed9a2eaae206ff37973d84f95d2b65ab5e41`.
The test ran before committing the two-file change, against the parent HEAD
plus the retained source diff. The same actual header bytes were checked
before the candidate commit; its LF-normalized committed blob hash is
`d091244e5530ab54124ce07c90af00e54378623cd3cbd80d1ef6db6f8ec831f2`.

- ON/OFF crossed with phase-load ON/OFF preserves exact execution and cleanup
  exhaustion, sticky phases and independent allowances.
- Constructor-cached options remain unchanged when config values change later.
- Diagnostic mode continues after zero and saturates at INT64_MAX. Controlled
  private-field injections test near-INT64_MAX behavior without that many calls.
- Eight trusted 2/4-thread runs each admit exactly 20003 execution and 10007
  cleanup units after all workers join. This is not a script threading API.
- Eight controlled pauses occur after a real successful debit CAS, before its
  wrapper returns. Remaining and legacy slots are zero; ON getters report 1
  and OFF getters report 0. Execution remains phase 0, cleanup phase 1.

The native harness also tests zero cleanup directly; the production bridge
continues rejecting nonpositive terminal allowances. It does not expand that
bridge's allowed inputs.

## Prepared runtime acceptance

The [new preparation tool](../eng/prepare-derived-ledger-windows.py) freezes
the exact checker, prior generator and ten unchanged validation templates.
The [fresh manifest](../artifacts/derived-ledger/windows-acceptance-preparation-20261014-attempt1/preparation.json)
contains complete terminal/finalizer/host, joined-worker, production and audit
commands for derived OFF/ON. Both profiles explicitly enable phase-load.
The existing four official loader controls are selected from the earlier
accepted phase-load manifest. The
[preparation review](../artifacts/derived-ledger/windows-acceptance-preparation-20261014-attempt1/review-attempt2/results.json)
passes syntax, frozen identities and 22 profile/auditor alteration controls.
These reject substitutions of either switch before a runtime is launched.
Actual-run audit controls are budget23, production10 and concurrency6
per profile; all were executed and rejected the altered evidence.

The first preparation review stopped on an expected budget rejection because
its exception handler only caught RuntimeError, while the retained budget
auditor raises ValueError. The failed review and driver remain; a fresh second
review accepts both rejection types without changing the prepared snapshots.
This was a review-driver issue, not a runtime failure.

The [new serial runner](../eng/run-derived-ledger-windows.py) validates frozen
profiles before starting any suite and retains raw outputs, commands, exit
codes and failures. It forbids benchmark execution.

## Matching build preparation

The [exact source checker](../eng/derived-ledger-runtime-candidate.py) binds
the direct parent, complete candidate tree, branch, two changed blobs and
actual tracked-clean worktree. The
[fresh build preparation](../artifacts/derived-ledger/candidate-20261014-attempt1/candidate-receipt.json)
passes 19 source alteration controls, all 527 baseline layout files and
32965 copied private SDK files with matching source/destination hashes. The
actual private SDK version is `11.0.100-rc.1.26420.103`; this is the separate
runtime checkout's toolchain, not an installed runtime replacement.

The [new build adapter](../eng/build-derived-ledger-release.py) retains the
prior build's fresh-product, exact-source, compiler-owner, complete layout,
native stamp and symbol-overlay guards. The
[adapter preparation receipt](../artifacts/derived-ledger/candidate-20261014-attempt1/build-preparation.json)
freezes its command and hashes. After all pre-build input checks, the driver
started the actual fresh Release build entry point, PID11840. The
[actual request](../artifacts/derived-ledger/windows-release-build-20261014-attempt1/request.json)
binds the candidate,36 source hashes and all preparation/baseline receipts.
The build completed successfully with zero warnings and errors. The
[actual result](../artifacts/derived-ledger/windows-release-build-20261014-attempt1/build-result.json)
and [layout receipt](../artifacts/derived-ledger/windows-release-build-20261014-attempt1/layout-receipt.json)
bind all fresh native/CoreLib/compiler products. An
[independent review](../artifacts/derived-ledger/build-review-20261014-attempt1/results.json)
passes 36 source files, seven compiled owners, eight critical products, all
527 layout files and five actual PE/PDB GUID-age pairs, with two rejected
symbol-identity mutations. The original build processes exited; no duplicate
build was started when the tool session ID became unavailable.

The frozen 16-command ON/OFF run completed: every command exited 0 without a
timeout. The [actual summary](../artifacts/derived-ledger/windows-acceptance-run-20261014-attempt1/acceptance-summary.json)
binds each process record and raw stream. Each profile passes:

| Suite | Actual result per profile |
| --- | --- |
| Terminal | 44 lanes, 84 rows, 70 interpreted and 14 native post-invocation entries |
| Finalizer | Nine recovery lanes and six original fatal controls; seven interpreted, one trusted native and one suppressed entry |
| Host | 15 cases and 73 collected contexts |
| Joined workers | 36 raw processes, 72 collected contexts, 156 PE-bound post-invocation entries |
| Production | Nine rows, retaining 24 official source files; no production method-entry claim |
| Audit mutations | Budget23, concurrency6 and production10 rejected |

All 16 suite drivers exited and the separate runtime tracked tree remains
clean. These distinct suites retain their own native/managed-entry boundaries;
the successful run is not a complete trace of every invoked method.

## Static Native Paths

The [actual PE/PDB review](../artifacts/derived-ledger/windows-hotpath-review-20261014-attempt1/results.json)
passes 417 byte-matched instruction rows, including 384 unique rows, and seven
alteration controls. With phase-load enabled, connected normal and cleanup
admitted paths each have two locked RMW operations when derived-ledger is ON
and three when OFF. ON skips the separate executed increment. Both getters
subtract the actual atomic remaining read from the initial allowance at48/56;
the diagnostic path retains four locked RMW operations and its saturation guard.
The static inventory does not establish which branch a live process selected
or its frequency/cost. The
[four new 64-byte live witnesses](../artifacts/derived-ledger/windows-live-witness-20261014-attempt1/review/results.json)
now pass, with four collected contexts and 24 rejected alterations. ON/OFF
crossed with Good/TightLoop records the actual new flag, immutable allowances
and remaining/raw-counter slots. ON reaches the emitted skip join with raw
executed slot zero after successful debit; OFF executes lock increment and
observes raw executed one. The joined evidence binds this build's four native
runtime/CoreLib DLLs and actual coreclr PE/PDB pair. These are live normal-admission
observations; cleanup remains static-path evidence, and the getter formulas
are emitted-code plus final-result evidence. No complete invocation trace or
performance cost is claimed.

## Performance Tool Preparation

The new [benchmark adapter](../eng/benchmark-derived-ledger-overhead.py),
[auditor](../eng/audit-derived-ledger-overhead.py) and
[comparison joiner](../eng/compare-derived-ledger-overhead.py) preserve the
original arithmetic callback/session fixture. Both derived profiles fix
phase-load to 1. Preparation requires the full 16-command acceptance and four
new live witnesses of the actual 64-byte meter, including admitted branches,
raw counter expectations and getters. The
[auditor preparation](../artifacts/derived-ledger/benchmark-tools-preparation-20261014-attempt3/auditor-review.json)
passes syntax and rejects both derived-switch and fixed-phase substitutions
for both profiles, retaining the original twelve benchmark audit controls.
The [build/native-binding guard checks](../artifacts/derived-ledger/benchmark-tools-preparation-20261014-attempt3/results.json)
reject ten build and six native-input alterations, using the actual build and
an explicitly synthetic cross-binding fixture. Complete original/snapshot
inventories are required; an empty inventory cannot omit functional/live gates.
The earlier Windows-separator failure is retained in attempt2. These are
tool-preparation results; the later full preparation and actual timing are
recorded separately.

The [full frozen preparation](../artifacts/derived-ledger/windows-benchmark-preparation-20261014-attempt2/preparation.json)
now passes with 785 inputs, 19 rejected alterations, 16 functional commands
and four live witnesses, after adding explicit snapshot/original hash
correspondence identified by independent review. The new phase-parent before,
derived OFF, derived ON and phase-parent after runs all complete. The
joiner requires identical 24 common source files and 20 managed products,
32 distinct process/nonce identities and 416 collected contexts. Historical
phase-load timings are not reused as a new bracket.

## Next validation

Retain the completed fresh Release native/CoreLib/compiler products and
the accepted phase-load layout as an inventoried baseline. Preserve the passed
ON/OFF terminal, finalizer, host, joined-worker, production and official controls.
Preserve the [actual timing result](windows-derived-ledger-performance.md)
with its single-kernel scope. Extend representative workloads before wider
performance claims. No100/1000 batch result is claimed. Mobile matching builds
and physical-device validation require separate products and evidence.
