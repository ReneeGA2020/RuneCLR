# Windows Release production functional acceptance

On 2026-10-14 the exact private Release candidate passed all five production
runs and four unchanged official loader controls. This closes the Release
functional baseline, separately from the terminal/finalizer probes and method
entry samples. No runtime source, native build, installed .NET, Android device
or SSH session was changed in this lane.

## Matching runtime and managed inputs

- Upstream base: `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`.
- Candidate: `099dacd07d8d890822f7422f895337733457ab3c`, tracked-clean private
  worktree `E:/runtime-finalizer-20261013`.
- Native/CoreLib/compiler configuration: `windows.x64.Release`, actual CMake
  interpreter feature enabled. The successful build and all 527 matching
  layout-file hashes bind the products to the recorded source. Framework
  libraries/hosts are the earlier same-base inputs, not a fresh shipping pack.
- Layout: `artifacts/budget-overhead/windows-release-build-20261013-attempt1/layout`.
- Private RuneCLR build SDK: `11.0.100-rc.1.26425.128`. `RuneCLR.slnx` Release
  build completed with zero warnings/errors. Host/runtime/player inputs were
  hashed before the later map rebuild. Late-map IL was rebuilt after the host
  with project-reference traversal disabled; prior host files remained unchanged.
- Operator compiler, package validator/importer and fixture generator ran on
  that SDK. Only their generated IL packages entered the private player.

The dedicated [driver](../eng/verify-release-production.py) freezes/checks the
existing [Release provenance tool](../eng/windows-runtime-validation.py). It
does not relax the older Checked launcher's diagnostic assertions or relabel
its output as Release. Raw stdout/stderr bytes, PID, per-process nonce in the
child environment, exact command/settings, timeout and file hashes are retained.
The nonce is an operator receipt binding; these unchanged applications do not
echo it. Samples independently echo the recorded PID and actual .NET 12 version.

## Production observations

| Run | Actual functional result |
| --- | --- |
| Lifecycle | 24/24 individual PASS rows and final summary; late IL included |
| Default sample | Three completed sessions, all resources released and contexts collected |
| Late sample | Post-host-build map returns `late-map=42`; completed/collected |
| Controlled source/import/source | Three completed/collected sessions; each `starts=1` |
| Package player | 15/15 individual PASS rows and final summary |

All five runs use `dotnet exec --fx-version 12.0.0`, mode 0, ReadyToRun and
tiering enabled, with explicit `--require-interpreter`. The native version-1
session-policy acknowledgement appears in each raw run. The process-wide
legacy collectible override is zero for these runs.

This is functional acceptance and actual policy acknowledgement, not a complete
method execution trace. Release lacks the Checked DEBUG bytecode dumps; their
absence is not treated as execution evidence. `methodEntryProof=false` is
explicit in every result. Separate Windows budget-entry observations and
[Android entry samples](android-budget-entry-acceptance.md) retain their own
method/target scopes. These unmetered production runs do not establish terminal
budgets, finalizer behavior, mobile performance or physical-device support.

## Unchanged official functional controls

Four existing standalone managed outputs from
`artifacts/session-finalizer/upstream-20261013-attempt1` ran on this Release
native/CoreLib layout. Their managed build configuration remains Checked plain
IL, reused byte-for-byte; it is not a new Release rebuild of the upstream tests.
All original test-source/assertion hashes match the frozen snapshot, the
candidate and the pinned official baseline. Their generated Windows Main guards
and original body calls remain unchanged.

| Official control | Actual acceptance |
| --- | --- |
| GenericVirtualMethod | Exit 100; original ten-iteration dispatch/unload assertions |
| CollectibleStatics | Exit 100; original ordinary/thread-static return assertions |
| ResolvedFromDifferentContext | Exit 100; four named scenarios and two successful payload prints |
| ByRefLocals | Exit 100; twenty actual `1` outputs and original return assertions |

The official lane uses the existing required-collectible override, GC stress
zero, and an explicit generated-Main out-of-process skip-status path. None
wrote a skip file. A nonzero exit, timeout, fatal output, missing business rows
or skip file fails acceptance. GenericVirtualMethod and CollectibleStatics are
silent on success; their evidence is original guarded entry/assertions, no skip
and expected return, not invented bytecode or per-payload execution logs.

## Evidence and reproduction

- [Production/upstream results](../artifacts/release-budget-functional/production-20261014-attempt1/results.json).
- [Exact runtime provenance](../artifacts/release-budget-functional/production-20261014-attempt1/runtime-provenance.json).
- [Lifecycle raw output](../artifacts/release-budget-functional/production-20261014-attempt1/lifecycle.stdout)
  and [player raw output](../artifacts/release-budget-functional/production-20261014-attempt1/package-execution.stdout).
- [Independent audit](../artifacts/release-budget-functional/production-review-20261014-attempt1/results.json)
  checks all nine raw process rows, original source/assertion/guard hashes,
  Release provenance and unchanged native/managed inputs. Eight in-memory
  corruption controls reject wrong exit, timeout, unsupported entry claim,
  skipped test, missing lifecycle PASS, missing late result, missing ByRef
  output and missing resolving payload body. Originals remain unchanged.
- [Root offline recheck](../artifacts/release-budget-functional/production-root-review-20261014-attempt1/results.json)
  on 2026-10-14 independently passes the same nine raw rows, twenty-four
  original official source-file bindings and eight corruption controls. No
  application was rerun in that review.

~~~powershell
py -3 -B eng/verify-release-production.py --runtime E:/runtime-finalizer-20261013 --layout artifacts/budget-overhead/windows-release-build-20261013-attempt1/layout --build-evidence artifacts/budget-overhead/windows-release-build-20261013-attempt1 --upstream artifacts/session-finalizer/upstream-20261013-attempt1 --output artifacts/release-budget-functional/production-new
py -3 -B eng/audit-release-production.py --evidence artifacts/release-budget-functional/production-new --output artifacts/release-budget-functional/production-review-new/results.json
~~~

Use a new directory for each attempt. The executed driver snapshot is retained
in its evidence directory. Production source/managed files and private layout
must remain unchanged for an offline re-audit.
