# Large poll-interval epoch optimization — S2 (2026-11-14)

This record covers the experimental large poll-interval work on the opt-in epoch callback
deadline: the validated-segment fast path (S1) and its codegen follow-up (S2). It is a local
experiment record. The source commits named below are local pins; they are not published
branches, and this document deliberately contains no repository links for them.

Status: functional and counter acceptance passed for S2 against a dedicated reference build;
the timing protocol is READY but unmeasured. No performance number exists, and nothing here
supports a speed claim. Scope is Windows x64 Release interpreter only.

## Source chain

| pin | content |
| --- | --- |
| C `ca8c85eb0948301a97c385aef94b46c94d127b9a` | frozen candidate used by the earlier ABI4 work; accepts only 1/100/1000 |
| REF10K `6810f142b4e98d36f0b7ab98615e2a05bfdbab3b` | C plus only the two 10000 allowlist extensions (Clock and Epoch Configure); default interval unchanged |
| S1 `ead0248a86e2706af6ce4c1dff9f38578f7652a8` | validated-segment fast path |
| S2 `64571e93fb27d7817f00786dd22d7f549ca7fa00` | S1 plus the two codegen fixes below; final candidate |

Old C could not accept 10000 at all, so its 10000 rejection is a historical configuration-domain
observation, not a pass. REF10K exists only to give the 10000 experiments a fair reference that
differs from C by the allowlist alone. The parent of REF10K is C; the parent of S2 is S1; S1's
parent is C-derived.

Intended intervals: 10000 primary, 1000 control. Intervals 1/100 are not treated as a precision
gate for this experiment; the implementation nevertheless keeps the 1000 and 10000 counters
exact against REF10K, so no coarse-relaxation credit is being taken.

## What S2 changes

The fast path runs inside one verified, live and owned callback segment of the same frame. Up to
64 subsequent safe opcodes may be admitted without re-entering the full out-of-line helper; each
one still performs the sticky-failure probe, the live callback-token comparison and the actual
pending/admitted accounting. Everything else takes the full path:

- unsafe opcode and its successor, frame transitions, tail calls, exception recovery and
  re-entry into the main loop reset the segment;
- End, cleanup and terminated phases never receive a segment grant;
- the OFF path is unchanged and still enters the body without a deadline flag load.

S2 differs from S1 in two codegen-only ways:

1. The segment budget and token live in the existing per-invocation dispatch state, and the grant
   moved out of every checked stub into the single shared helper. The helper grants only after the
   check succeeded and only when failure is clear, the callback is active and the phase is
   execution; the terminated-cleanup branch returns before the grant.
2. The failure probe uses an explicit typed `VolatileLoad<LONG>`; the deadline field access stays
   volatile and the field layout and public volatile helpers are untouched. Only the temporary
   return value stopped being volatile.

Both changes are compiled only for the Windows AMD64 Release folded bank. Other backends do not
use this code.

Because the per-opcode accounting is unchanged, checks and admitted match REF10K exactly at
both 1000 and 10000; C is a valid counter reference only at its supported intervals. The poll
still happens at the interval threshold or at a boundary. Cleanup quota and the
configure-before-first-execution rule are unchanged.

## Codegen evidence (independent static review)

The table uses the independent reviewer's byte counts; raw address-range extents are shown in
parentheses. These conventions must not be mixed when calculating size changes.

| image | InterpExecMethod | full helper | VolatileLoad-family call sites (image / inside the method) |
| --- | ---: | ---: | ---: |
| REF10K | 44,491 (44,496) | 619 (624) | 10 / 0 |
| S1 | 107,548 (107,549) | 619 (624) | 1,187 / 1,177 |
| S2 | 56,410 (56,412) | 746 (752) | 107 / 97 |

- The 1,080-call drop is exactly 3 x 360: three grant-side volatile reads removed from each of the
  360 helper call sites. The per-op failure probe was not eliminated.
- S2 is still 11,919 bytes (about 11.6 KiB) larger than REF10K, and the helper grew by 127 bytes relative to S1,
  because of the single grant site and the extra callee-saved register.
- Residual P2, non-blocking: the typed `VolatileLoad<LONG>` call is still out of line at the 97
  safe-opcode stubs. Its callee shrank to `mov eax,[rcx]; ret`, but the call and return remain.
  No third variant was attempted.
- No timing inference is made from any size or instruction count.

## Functional and counter results

Matched run `s2-10k-01` against the already captured REF10K run:

| item | result |
| --- | --- |
| processes / exit 0 / timeouts | 19 / 19 / 0 |
| failures / expected rejects / input drift | 0 / 0 / false |
| strict comparison vs REF10K | matched 19, problems 0; 26 informational lines are ticker-phase fields only |
| NoOverhead | 63 unique PASS lines plus the final PASS |
| ErrorGates | 19/19, including same-frame host End/Begin, DIV/REM counter conservation, foreign owner, finally-at-interval and the four G1 late-configure gates |
| self-tail | 5 assertions plus final PASS |

Representative counters (identical to REF10K in every lane and field):

| lane | interval | checks | admitted |
| --- | ---: | ---: | ---: |
| parity off | 1000 | 0 | 0 |
| parity clock | 1000 | 500,007 | 7,500,015 |
| parity epoch | 1000 | 500,007 | 7,500,015 |
| parity epoch | 10000 | 500,007 | 7,500,015 |
| tight loop | 10000 and 1000 | 800,013 | 12,000,030 |
| call-heavy | 10000 and 1000 | 3,200,013 | 9,600,030 |
| business loop | 10000 and 1000 | 2,409,542 | 15,629,375 |

These workloads are boundary-dominated, so their equal totals at 1000 and 10000 do not imply
that the interval configurations are equivalent. The admitted counter records admitted opcodes;
the checks counter is a separate quantity.

Query(4) readback through a dedicated probe: clock and epoch at 10000 and 1000 report the same
value before Begin, while active and after End; 0, -1 and 12345 are rejected in both modes. Ten
cases, 4 accepted and 6 rejected. This proves the runtime stored and returned the configured
interval; it does not by itself prove cadence quality.

## Host regression and provenance

The host overlay keeps the S2 native binaries and the frozen C managed set: host-layout coreclr
`7a0423acf4347aa591b6f3b14fc5e6a99a2e6ddab3c36b7cbe5ec490dd445718` and
System.Private.CoreLib `10913f56bc97b61f14dc74baefb135204724d4193a4fd7b5aed61455518aa720`.

| suite | result |
| --- | --- |
| epoch 24, direct | 24/24 passed, 0 skipped, 0 failed, exit 0 |
| lifecycle, ordinary | 156/156 passed, exit 0 |
| lifecycle, require-interpreter | 156/156 passed, exit 0 |
| four focused upstream tests | each Expected 100 / Actual 100, exit 0 |

The official integration verifier remains FAIL on this worktree: the CLR-only build directory
does not contain `System.Private.CoreLib.dll`, and the verifier refuses to run without comparing
the layout binary to a build output. No CoreLib was placed in any build directory and the failure
is preserved. The independent scoped provenance check instead joins each native image to the S2
Release build (RSDS to the S2 worktree) and the managed set to the frozen C cohort, and confirms
that the S2 worktree did not change CoreLib sources. This is a scoped experiment acceptance, not
an official integrated PASS and not a claim that CoreLib was rebuilt from the S2 source tree.

Layout identity: 267 entries = 259 managed + 6 native + 1 PDB + 1 manifest; all manifest entries
match actual files. CoreLib is byte-identical to the frozen C cohort on both arms. Six native
files: coreclr, clrjit, clrinterpreter and corerun are rebuilt per arm; msquic and
System.IO.Compression.Native are inherited from C and identical on both arms.

## Public surface versus private capability

Interval 10000 is available through the private QCall that this experiment uses. The public
`MapRunOptions` validation still accepts only 1/100/1000, so application-level support for 10000
is not claimed and no host API was extended in this work.

## Timing protocol readiness

A separate paired protocol exists and was independently accepted as READY:

- layouts: PE-only copies of the two arms, 265 files each (259 managed + 6 native), managed set
  identical, CoreLib frozen from C;
- driver unchanged at
  `5747c1e034587f99b96c53d2f85e0e7f97790156b059c4264a783f4e618ba7e0`;
  lanes OFF/10000 (tag only, no deadline configured), Epoch/10000 primary,
  Epoch/1000 control; three kernels; five alternating AB/BA pairs; 90 sequential processes;
- 541 frozen inputs with digest
  `bd211afb992f3c2088b52eed9f8fe062522af949aeb12c7ae58b39808f05dea2`, matching freeze,
  preflight and the validation batch before and after;
- 25 synthetic analyzer cases and 6 non-timing ValidateOnly captures pass; the analyzer enforces
  exact ordering, identity, raw hashes, exits and counter equality.

Formal measurement count so far: zero. The user deferred timing ("later"), so a new explicit
quiet-window confirmation is required before any of the 90 processes may run. Protocol READY means
the inputs are fit for one measurement; it is not a performance result.

The reporting plan is whole-kernel medians, ratio of arm medians, median paired candidate/reference
ratio, and the five per-pair ratios with their range. OFF is not a strict null because the same
interpreter function changed layout; the ON/OFF ratio is descriptive only. Five pairs are
exploratory: no significance, minimum detectable effect, or sub-percent exclusion is claimed, and
10000 is not extrapolated from 1000.

## Recording defect and containment

The first controller version serialized the full inherited child environment into every receipt.
The protocol review caught this before any formal S2 timing began. Five generated receipt files
(114 receipts, 10,488 environment entries) were redacted in place: full environment mappings were
removed, with only allowlisted fixed environment values retained. All non-environment fields
compare equal, and the raw
stdout/stderr streams are unchanged. Receipt hashes therefore changed; earlier receipt hashes are
pre-redaction evidence and must not be quoted as current bytes. The affected v1 controller and the
older ABI4 perf controllers must not be used for new runs. The corrected controller records only
the fixed five values plus a count.

## Limits

- Windows x64 Release interpreter only; no device, AOT, Linux, Wasm, JIT or R2R instrumentation
  claims.
- 10000 is a private experiment; the public host option surface is unchanged.
- No timing, so no throughput, latency or regression statement exists for S2.
- The interpreter segment path is not a sandbox; existing budget/enforcement limits and the
  author-finalizer restriction in a budgeted context are unchanged.
- The source pins above are local and unpublished.

## Evidence (local-only)

These paths exist only on the experiment machine; they are not repository-relative and will not
resolve from a clone.

- D:/RuneCLR-artifacts/epoch-large-interval-opt-20261114/REPORT.md
- D:/RuneCLR-artifacts/epoch-large-interval-opt-20261114/review/s2/binary/REVIEW-BINARY-S2.md
- D:/RuneCLR-artifacts/epoch-large-interval-opt-20261114/review/functional-s2/REVIEW-FUNCTIONAL-S2.md
- D:/RuneCLR-artifacts/epoch-large-interval-opt-20261114/review/perf-s2/PERF-S2-V2-ACCEPTANCE.md
- D:/RuneCLR-artifacts/epoch-large-interval-opt-20261114/host-s2/S2-FUNCTIONAL-RESULTS.md
- D:/RuneCLR-artifacts/epoch-large-interval-opt-20261114/native-s2/MANIFEST-S2.json
- D:/RuneCLR-artifacts/epoch-large-interval-opt-20261114/perf/v2/ (protocol inputs, logs, six ValidateOnly captures)

## Execution channels

Runtime implementation, builds, private layouts and static assembly inspection were done by an
Orca worker; functional harness, matched/Query(4)/host/upstream runs and the protocol review were
done by another Orca worker; independent source, binary and functional reviews by a third; the
Lead integrated sources, built the minimal perf protocol and performed the redaction. No push, PR
or merge happened in this work, and no installed runtime was replaced.
