# Windows Release Budget Acceptance

On 2026-10-14 an independent offline review accepted the retained Windows x64
Release terminal, finalizer and host-budget results. The review did not rerun
the applications, change the runtime, or replace earlier experiment receipts.

| Experiment | Accepted behavior | Selected entry observations |
| --- | --- | --- |
| Terminal attempt 2 | 44 process lanes, 84 scalar rows; catches and filters suppressed after native exhaustion; bounded cleanup; constructor and static-constructor boundaries; two-context isolation and twenty bad/good recovery pairs | 70 interpreted entries and 14 ordinary native entries |
| Finalizer attempt 2 | Nine positive cases recover; six ordinary explicit exceptions still terminate their own processes; two queue sentinels and a fresh good session per positive case | Seven authored interpreted finalizers, one inherited trusted native finalizer, one suppressed finalizer with no execution claim |
| Host budget attempt 1 | 15 cases, 73 completed collectible-context retirements; resources released; lifecycle failures, cleanup, ordinary exceptions and subsequent sessions verified | 15 trusted `MapRunner.Run` native observations; author methods not individually sampled in this suite |

The terminal and finalizer suites are focused private runtime probes. Production
author finalizers remain unsupported; these results do not approve that feature
for UGC packages. See the [host budget limits](host-instruction-budget.md),
[terminal prototype](runtime-session-terminal-prototype.md) and
[finalizer boundary](runtime-session-finalizer-boundary.md).

## Runtime Identity

The reviewed processes used the same matching private Release runtime as the
[budget overhead measurement](budget-overhead.md):

- Upstream: `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` (.NET 12).
- Candidate: `099dacd07d8d890822f7422f895337733457ab3c`.
- Platform: Windows x64, `Release`, `FEATURE_INTERPRETER=1`,
  `FEATURE_DYNAMIC_CODE_COMPILED=1`.
- Product: `E:/runtime-finalizer-20261013/artifacts/bin/coreclr/windows.x64.Release`.
- Layout: `artifacts/budget-overhead/windows-release-build-20261013-attempt1/layout`.

The reviewer checked the frozen build request, successful raw build output,
CMake configuration, source snapshots, native source stamps, compiler/CoreLib
products, entire recorded layout inventory, SDK, managed fixture files and
post-execution immutable-input receipts. This is a private matched layout,
not a complete official shipping runtime pack.

The runtime image hashes are:

| Image | SHA-256 |
| --- | --- |
| `coreclr.dll` | `38d00ec31958fe700f6ebc732f46f41440c5ad7c0cfe6fd481904efa621e6fa1` |
| `clrinterpreter.dll` | `075338c6432b31fff389b79b50d62d43efcf0ae343cd7f57ccd5950043c5e6b4` |
| `clrjit.dll` | `4ba446c4853bd0f6b77f08ff86b4229c772173f58f22ae962d1e0b940aba1e2f` |
| `System.Private.CoreLib.dll` | `c9764acb6d32606050c85d22159a50291a3215d0a74cda778a6659f840c3794a` |

## Entry Evidence

Each terminal selected entry follows an actual constructor/static-constructor
or `Run` invocation counter and a completed callback frame or host-caught
failure. Finalizer entries follow a finalization drain and the authored or
trusted-base entry counter. The trusted host observation follows a validated
`MapRunner.Run` report and collected unload ticket.

The frozen Windows x64 observer resolves an optional indirect entry jump, reads
the precode instruction shape and its data type byte, and retains the selected
method definition, MVID, token, code addresses, 16 code bytes and invocation
counter description. The separate PE-only metadata reader bound these definitions
to the actual frozen DLLs without loading author code. It checked author fixture
images have no managed-native header.

The reviewer additionally froze three source files from the exact candidate Git
tree: `precode.h`, `amd64/thunktemplates.asm` and `amd64/asmconstants.h`.
`InterpreterPrecodeData` places its type byte after two 64-bit fields and assigns
interpreter precode type `0x06`. The x64 stub loads its first data field into
`r10` and jumps through the second. This verifies the observer's displacement
and type-offset interpretation for this candidate and architecture.

These are post-invocation selected-entry observations. They do not capture every
invocation or child dispatch. The raw code span does not include the separate
data type byte; that value is the frozen observer's runtime read. None of the
six fatal controls supplies a per-method entry sample. The already-terminated
finalizer is explicitly recorded as skipped rather than interpreted. The host
budget suite's author methods remain individually unsampled; the
[mobile entry experiments](mobile-host-budget-acceptance.md) are separate.

## Independent Audit

Accepted review output:
`artifacts/release-budget-functional/root-independent-review-20261014-attempt5/results.json`.
It contains the reviewed request/result hashes, runtime identity, frozen precode
source hashes/Git blobs, 14 unique managed PE identities, process bindings and
21 rejected semantic corruption controls.

The review verifies each launcher's positive PID, argument/environment binding,
owned nonce, termination status, watchdog status and raw stdout/stderr hashes.
The managed raw run/completion records contain the nonce, case and mode but no
independent PID field; PID attribution is the launcher's recorded process
binding. A watchdog termination is never accepted as successful recovery or an
expected fatal finalizer result.

The semantic checks cover exact native execution/cleanup arithmetic and sticky
latches, ordinary/diagnostic controls, author catch/filter suppression,
constructor counters, private cleanup/delegate counters, cross-context ledger
isolation, finalizer definition ownership, queue progress, original unhandled
exception types, retired-query rejection, host resource ownership and observed
collection after frames return. Fatal controls retain their original
`OperationCanceledException` or `InvalidOperationException` and original
`Finalize`/`GC.RunFinalizers` stack evidence, with no positive result file.

Negative controls independently corrupt counters, latches, ledger arithmetic,
precode type, MVID/token, finalizer ownership, sentinel count, collection,
next-session output, resources, continuation logs, PID, nonce, watchdog state,
switches, raw owned markers and cross-session ledger isolation. All 21 are
rejected without editing the retained evidence or rerunning its processes.

Run another offline review into a fresh directory:

```powershell
py -3 -B eng/audit-release-budget.py --output artifacts/release-budget-functional/root-independent-review-FRESH
```

Observed output:

```text
PASS Release audit: terminal 44 lanes/84 rows/70 interpreted+14 native entries; finalizer 9 recovery+6 original fatal controls/7 interpreted+1 trusted native/1 suppressed; host 15 cases/73 collected contexts; 21 semantic corruption controls rejected
```

Review attempts 1-3 remain as reviewer failures: an incorrect shared override
type name and two differing host-driver schema assumptions. Each has a
`failure.json`; no experiment evidence was changed. Attempt 4 passed the first
15 semantic controls; attempt 5 adds pinned precode source snapshots and six
process/raw/ownership controls. The original Release attempts 1 and the Checked
comparison runs also remain intact. This independent review accepts only the
three experiment directories listed here; it does not reclassify earlier runs.

Physical-device acceptance, broader method tracing, supported execution/API
boundaries and budget performance work remain separate milestones.

The [root offline recheck](../artifacts/release-budget-functional/budget-root-review-20261014-attempt1/results.json)
independently reruns this audit on 2026-10-14, passing all declared rows,
definition/entry bindings and 21 corruption controls without replaying any
application. The separate [production acceptance](windows-release-production.md)
and [joined-worker baseline](windows-terminal-concurrency.md) supply their own
functional/concurrent coverage on the same matching Release products.
