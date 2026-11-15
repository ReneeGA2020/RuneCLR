# Large poll-interval epoch optimization — S2 (2026-11-14)

This record covers the experimental large poll-interval work on the opt-in epoch callback
deadline: the validated-segment fast path (S1) and its codegen follow-up (S2). It is a local
experiment record. The source commits named below are local pins; they are not published
branches, and this document deliberately contains no repository links for them.

Status updated 2026-11-15: functional and counter acceptance passed, and one formal 90-process
batch passed independent capture review and independent offline statistical recomputation.
Epoch/10000 elapsed time fell by 19.2–41.8% across the three kernels, but OFF elapsed time rose
by 7.3–32.9%. These are median paired changes in one exploratory batch, not a general improvement
or a reason to promote S2 by default. Scope is Windows x64 Release interpreter only.

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

## Timing protocol and formal run

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

The initial user deferral was followed by a new quiet-window confirmation on 2026-11-15, after
other tasks and a CPU-heavy background process were stopped. Run `s2-quiet-20261115-153718`
executed exactly once: 90 processes, all exit 0, no timeout, no input drift. The controller's
real OS exit was 0, recorded by its launcher, not inferred from batch metadata. Its window was
15:39:13–15:40:27 +08:00. No pilot, extra ValidateOnly run, replacement sample or repeat timing
was added. The measurement window is closed; another timing batch needs a new quiet window.

The reporting plan is whole-kernel medians, ratio of arm medians, median paired candidate/reference
ratio, and the five per-pair ratios with their range. OFF is not a strict null because the same
interpreter function changed layout; the ON/OFF ratio is descriptive only. Five pairs are
exploratory: no significance, minimum detectable effect, or sub-percent exclusion is claimed, and
10000 is not extrapolated from 1000.

## Formal results (2026-11-15)

Ratio direction is candidate S2 / reference REF10K. Each row has five pairs. Arm medians and
the median of paired ratios are different statistics; the percentage column uses
`100 * (median paired ratio - 1)`, so a negative change means less elapsed time.

| kernel | lane | REF median ms | S2 median ms | ratio of arm medians | median paired ratio | elapsed change |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| TightLoop | Epoch/10000 primary | 385.5974 | 246.3384 | 0.638849 | 0.638849 | −36.1% |
| CallBoundary | Epoch/10000 primary | 76.4112 | 62.4344 | 0.817084 | 0.807949 | −19.2% |
| BusinessLoop | Epoch/10000 primary | 264.4680 | 154.6364 | 0.584707 | 0.581609 | −41.8% |
| TightLoop | OFF/10000 label | 79.2259 | 105.1505 | 1.327224 | 1.328517 | **+32.9%** |
| CallBoundary | OFF/10000 label | 22.9903 | 24.6778 | 1.073401 | 1.073401 | **+7.3%** |
| BusinessLoop | OFF/10000 label | 57.5320 | 66.9996 | 1.164562 | 1.169090 | **+16.9%** |
| TightLoop | Epoch/1000 control | 379.8864 | 240.6794 | 0.633556 | 0.628292 | −37.2% |
| CallBoundary | Epoch/1000 control | 75.7295 | 64.2120 | 0.847913 | 0.847820 | −15.2% |
| BusinessLoop | Epoch/1000 control | 266.4602 | 152.0967 | 0.570805 | 0.574976 | −42.5% |

All five primary pairs favour S2 for every kernel; all five OFF pairs favour REF10K for every
kernel. OFF has no configured deadline: its measured regression must stay visible even though
the unchecked body has no added deadline-flag access. This run does not identify the cause.
The bounded static follow-up below examined the regression; no new implementation or
automatic repeat timing is part of this acceptance.

CallBoundary Epoch/10000 pair 4 had a slow reference sample (101.9768 ms versus a 76.4112 ms
reference median) and a candidate sample of 66.5860 ms. Its ratio, 0.652952, is retained, not
discarded or winsorised; it is not the selected median paired ratio. The independent recompute
reproduced all 36 comparable analyzer fields within the analyzer's display precision.

The analyzer's optional normalized view is explicitly
`median(pair epoch candidate/reference) / median(pair OFF candidate/reference)`:
0.480874 / 0.752701 / 0.497489 for TightLoop / CallBoundary / BusinessLoop. This is not the
median of pairwise normalized ratios and is not a pure helper-cost or net-benefit estimate.
It does not erase the OFF regression. The measured span is typed-delegate dispatch plus the
interpreted kernel, not a separately timed admission helper.

Capture review rechecked all 541 immutable inputs, 9 pins, 90 unique process identities,
180 raw streams and all 45 across-arm counter cells. Every epoch row had a stopped/joined
ticker with no ticker fault. Fixed-only environment recording was preserved. Resource samples
before the run reported CPU 2–6%, 15,245–15,324 MiB available and nonzero PagesInputPerSec
(12,485 then 10,557). These are pre-run readings, not continuous telemetry; this is not a claim
of a page-free window. The raw stdout file times corroborate ordering, but receipts do not
contain per-child start/end timestamps.

Portable, allowlisted [sample readings, pair ratios and provenance](../evidence/epoch-s2-20261115/README.md)
are included in the repository. The complete local streams and the two independent reviews
remain separately identified below. No raw inherited environment or absolute child-file path
is included in the portable sample CSV.

## Bounded OFF diagnosis and stopping point (2026-11-15)

Two Orca Workers independently inspected the exact formal-run binaries, using dumpbin/PDB and
a separate PE mapping/Capstone disassembly. OFF does not execute segment admission or grant,
but its generated instruction stream is not unchanged:

| inspected window | REF10K | S2 |
| --- | --- | --- |
| per-opcode dispatch head and back-edge | 16 instructions, 2 memory reads | 16 instructions, 4 memory reads |
| instruction pointer | kept in a register across dispatch | stack home reloaded at dispatch, copied to a body register and written back by IP updates |
| mode offset at dispatch | register | stack-home read |
| sampled constant-zero body | reference IP update | one extra load and one extra store |
| sampled branch-body path | reference IP update | three extra loads and one extra store |
| stack frame/prologue | 8 pushes, 0x408 allocation, 4 XMM saves | same size and saves; local/home slots moved |

The image-base `lea` moved from the back-edge to the head; it exists in both arms, is address
arithmetic rather than a memory load, and is not an added-load explanation. The dispatch-state
growth from 16 to 32 bytes did not increase the total frame allocation.

This establishes extra executed memory accesses in OFF. It does not establish which source
change caused the compiler's allocation decision, or how much of the 7–33% regression comes
from those accesses versus instruction/cache/branch layout. No CPU sampling or additional
timing was performed. In particular, instruction counts cannot be converted into CPU-cost
percentages.

No small, correctness-preserving fix was identified in the bounded pass. Moving segment TRY
out of line or separating the checked dispatch loop would be a structural follow-up, not an
already validated hint or one-line fix. The decision is to stop this S2 optimization round,
retain its measured results and REF10K comparison, and leave S2 experimental without default
promotion. This does not abandon or disable the previously accepted optional epoch mechanism.
No third variant, build, target run or new quiet window was started.

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
- One 90-process exploratory batch only; no general throughput/latency claim, statistical
  significance, minimum detectable effect or default promotion. OFF regressed in all three kernels.
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
- D:/RuneCLR-artifacts/epoch-large-interval-opt-20261114/review/perf-s2/formal/REVIEW-FORMAL-S2.md
- D:/RuneCLR-artifacts/epoch-large-interval-opt-20261114/review/perf-s2/statistics/RECOMPUTED-S2.md
- D:/RuneCLR-artifacts/epoch-large-interval-opt-20261114/review/off-diagnosis/native/OFF-DIAGNOSIS.md
- D:/RuneCLR-artifacts/epoch-large-interval-opt-20261114/review/off-diagnosis/triage/verify-off-asm/VERIFY-OFF-ASM.md
- D:/RuneCLR-artifacts/epoch-large-interval-opt-20261114/host-s2/S2-FUNCTIONAL-RESULTS.md
- D:/RuneCLR-artifacts/epoch-large-interval-opt-20261114/native-s2/MANIFEST-S2.json
- D:/RuneCLR-artifacts/epoch-large-interval-opt-20261114/perf/v2/ (frozen protocol, six ValidateOnly captures, and the sole formal run out/s2-quiet-20261115-153718)

## Execution channels

Runtime implementation, builds, private layouts and static assembly inspection were done by an
Orca worker; functional harness, matched/Query(4)/host/upstream runs and the protocol review were
done by another Orca worker; independent source, binary and functional reviews by a third; the
Lead integrated sources, built the minimal perf protocol and performed the redaction. The sole
formal run and initial analysis were executed by Orca Worker developer-4. Orca Worker developer-3
independently reviewed capture/identity/integrity, while Orca Worker developer-5 independently
parsed raw timings and recomputed statistics. Lead reviewed and published the documentation and
allowlisted data extract. Runtime source pins remain unpublished; no runtime PR or merge happened,
and no installed runtime was replaced.
The bounded OFF diagnosis was performed by Orca Worker developer-5 and independently checked
by Orca Worker developer-3; Lead reviewed the instruction windows and recorded the stopping point.
