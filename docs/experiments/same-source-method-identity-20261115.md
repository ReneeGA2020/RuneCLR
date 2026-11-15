# Same-source IL/R2R: evidence audit and method-site observations (2026-11-15)

The same-source build and basic behavior record already exists. This increment audited it,
then observed the retained images without rebuilding them. The result is **partial** for
paired method-mode acceptance: the R2R arm has positive native-entry evidence for
`TrustedGame.Update.GameRules.Tick(GameState, int)`; the IL arm's method mode/body remains
unproven. Neither missing evidence nor the observation-tool failures establish a runtime bug.

## What was already established

The maintained [TrustedGame build driver](../trusted-game-builds.md) compiles one IL set and
crossgens those same bytes into separate R2R artifacts. The five logical images are Host,
Contracts, RuneCLR.TrustedUpdate, Update A and Update B. For each image, original IL equals the
IL-layout bytes; R2R bytes differ while MVID is preserved. A/B are distinct business versions,
not merely the two artifact kinds of one version.

The retained two layouts already execute against the same oracle: results 1/3/6, score6/ticks3,
negative delta producing CallbackFailed then Closed, unchanged failure state, and refusal to
enter the module after close. Signed A/B activation and recovery are separately recorded.
These behavioral facts do not need another build or a repeat functional campaign.

The audit corrected earlier summaries that described same-source behavior, exceptions or
callbacks as absent. The common oracle is asserted per arm, rather than the original driver
performing an arm-to-arm text diff. Generic calls also have independent composition/stock
evidence; the maintained same-source sample itself has no generic contract member. Concurrent
interleaving and a fully hermetic compiler/reference-pack closure are additional scopes, not
failures of this synchronous example.

## Exact observation inputs

Platform: Windows x64, private CoreCLR 12 Checked, runtime source
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. Both layouts use the same runtime and the retained
configuration (ReadyToRun 1, InterpMode 1, tiering disabled). No runtime or business image was
rebuilt or changed. Six runtime/tool files and ten managed image files were pinned before and
after each observation; the crossgen2 file was an input pin, not a new invocation.

| target identity | value |
| --- | --- |
| method | TrustedGame.Update.GameRules.Tick(GameState, int) |
| MethodDef | 0x06000001; the only other method in this update image is .ctor, token 0x06000002 |
| common MVID | 51c8d04a-e989-45dc-81a8-ac57d21147b1 |
| IL SHA256 | 6ff7777f84402ac272d6cd198c4f30c5baae59aa0a39c9a4b25a24443457c053 |
| R2R SHA256 | 1589be9c84aa676fed4e4cf24f123e881d00d53e519f663f0705232e93f8e75a |
| native method RVA | [0x1660, 0x1702), 162 bytes, MethodWithGCInfo / RuntimeFunction |
| copied IL RVA in R2R image | 0x1758; not the native method body |

The earlier method-proof run-2 overlay had different image bytes and was not reused as if it
were this pair. Matching coreclr/clrinterpreter PDBs were available; stale clrjit/CoreLib PDBs
were identified and not used as matching type-layout evidence.

## Four launches, including the failed observations

All raw records are preserved. The first release and its replacement allowance were followed
by a separately released, single IL continuation. Four Host processes were launched in total;
there was no fifth, and no performance measurement, Publisher or crossgen run.

| run | arm | process outcome | method evidence |
| --- | --- | --- | --- |
| tick-il-20261115-01 | IL | timed out; Host/CDB exit 1 | no commands reached CDB because the operator session lacked TTY |
| tick-il-20261115-02 | IL | timed out; Host exit 1, CDB exit unavailable/null | invalid type-chain reads; no Tick witness |
| tick-r2r-20261115-02 | R2R | Host and CDB exit 0 | four positive native-body-entry observations |
| tick-il-20261115-03 | IL | Host and CDB exit 0 | same business oracle; no positive Tick interpreter/body witness |

The timeout runs were terminated by the observation controller; they are not evidence of a
runtime crash. The second run's null CDB exit remains null, not an inferred zero. Observation
deadlines were 180 seconds; teardown could take additional time. Debugger stdout/stderr and
debuggee console output share one captured stream, explicitly marked merged.

## R2R: positive observed native entry

The target ModLoad path bound to the retained R2R update, with image range
`0x7ff9e4690000–0x7ff9e4694000`. Memory inspection confirmed the MVID at base+0x1D2C, the PE
executable image and RuntimeFunction table. The table agrees with the hashed crossgen map and
the target range [0x1660,0x1702), rather than the copied-IL range.

| call | RIP | RVA | observed delta argument |
| --- | --- | --- | ---: |
| 1 | 0x7ff9e4691660 | 0x1660 | 1 |
| 2 | 0x7ff9e4691660 | 0x1660 | 2 |
| 3 | 0x7ff9e4691660 | 0x1660 | 3 |
| 4, negative session | 0x7ff9e4691660 | 0x1660 | −1 |

The first three calls share instance/state pointers; the fourth uses the new negative-session
objects. Raw output contains normal results 1/3/6, score6/ticks3, then CallbackFailed/Closed
with score0, and OK. Only four body-entry hits occurred, consistent with the source refusing
the later calls after close. Host PID27472 and CDB PID27372 both have real OS exit 0. All sixteen
input hashes still match their recorded expectations.

This supports arrival at the target R2R native-body entry for these calls. It does not establish
that every instruction, every method or every call in an application executes natively.

## IL: no positive target-method mode witness

The successful IL continuation loaded the correct IL update at
`0x274fc100000–0x274fc108000`, with the expected MVID at base+0x2614. Host PID33660 and CDB
PID30400 exit 0; business output matches the R2R arm, and all sixteen inputs remain pinned.

One `InterpExecMethod` entry was observed, but its MethodDesc token remainder was 0x21, not
Tick's 1, and its module was not bound. A subsequent conditional breakpoint had no logged
positive match. It evaluated the current frame per hit, but checked only the low token remainder,
not the full token/module identity, and its effectiveness was not demonstrated.

Thus no Tick MethodDesc/module/token/IR-dispatch witness was obtained. Absence of a positive
match does not establish that the breakpoint never ran, that Tick used JIT, or that the runtime
failed to interpret it. A conditional command may continue without a positive stop; the audit
does not turn this negative observation into a mode classification.

At this runtime pin, InterpMode 1 requests interpretation except for methods with usable R2R
code and CoreLib code; mode >=2 disables R2R, and mode 3 is the interpreter-only configuration.
These source rules and environment settings express selection policy, not this method's
observed execution. The paired method-mode claim therefore remains open.

## Observation-tool corrections and limits

The failed type walk was an instrumentation error: PEAssembly is not a PEImage subclass.
The valid chain is Module.m_pPEAssembly → PEAssembly.m_PEImage → PEImage.m_pLayouts[1] →
PEImageLayout.m_peDecoder.m_base. The earlier direct cast read unrelated memory. Neither
zero nor the debug-heap fill pattern was evidence that runtime initialization was too early.
The original pre-run GO was withdrawn and its correction retained.

The interpreter dispatches transformed IR, not the PE's raw IL bytes. A future positive
interpreter claim needs the target frame's MethodDesc/module/token and current IR pointer
inside that method's IR buffer. Merely stopping at a generic interpreter function, seeing a
kind-6 entry, or finding a PC inside coreclr.dll is insufficient. Entry-frame ip may be null;
the independently checked dispatch site is InterpExecMethod+0x2A0, with R15 as frame and R14
as current IR pointer. This site was not reached for a positively identified Tick in this run.

The controller also appended repeated debuggee-exit events while polling an already exited
child. These are logging duplicates, not additional processes or exits. The process handles,
PIDs and final receipts were independently checked.

This increment is stopped. Any later attempt should first validate an unconditioned entry
trace/full-token/module filter, then observe the matched frame's IR dispatch. Repeating the
same unvalidated conditional breakpoint or rebuilding the products is not the needed increment.
No further observation, runtime change or broader compatibility work is authorised by this record.

## Evidence and execution channels

[Portable selected records and provenance](../evidence/same-source-method-identity-20261115/README.md)
include the four-run ledger, image/runtime hashes and four native entry readings. They exclude
inherited environment values and are not a substitute for the complete raw streams.

Local-only records, not links that resolve from a clone:

- D:/RuneCLR-artifacts/same-source-audit-20261115/SUMMARY.md (the preceding read-only audit)
- D:/RuneCLR-artifacts/same-source-method-proof-20261115/runs/ (all four immutable captures)
- same root: review-capture/REVIEW-R2R.md and REVIEW-IL-FINAL.md
- same root: review-capture-control/REVIEW-CONTROL-FINAL.md and ledger-4runs.json
- same root: prep-native/ROOTCAUSE.md and review-prep/CORRECTION-ROOTCAUSE.md

Capture was executed by Orca Worker developer-5. Orca Worker developer-3 independently checked
method/image/raw evidence and selection-source semantics; Orca Worker developer-4 independently
checked launch/exit/input/ledger evidence. Lead reconciled the scopes, checked the raw native
readings and published the record. No native subagent, runtime rebuild or installed-runtime
replacement was used.
