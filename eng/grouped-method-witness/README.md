# Grouped host method witnesses

Windows x64 diagnostic tools for grouped-host method entries. The
[November 17 fixture record](../../docs/experiments/grouped-method-witness-20261117.md)
has 16 live entry observations accepted by the independent verifier. Build
success, policy values and compilation notifications do not prove execution.

## Tools and use

- `capture.py`: one hidden CDB/debuggee pair; scalar checkpoint binding, raw
  UTF-8 stdout, separate stderr, events and a hash-bound manifest.
- `cdb_commands.py`: debugger commands and fail-closed output parsers.
- `verify.py`: independent bundle verification against staged PE bytes. Only
  its report can carry `verified=true`; it never changes host records.
- `test_*.py`: synthetic controls, never live execution evidence.

Supply all paths explicitly. Keep artifacts outside the repository and use new
output, host JSONL and checkpoint paths for every run:

```text
py -3 capture.py --run --framework-natural-hardware --runtime-root <private-layout> \
  --runtimeconfig <runtimeconfig.json> --harness <harness.dll> \
  --fixture <staged-fixtures> --cdb <cdb.exe> --sos <sos.dll> \
  --helper <cdb_commands.py> --output <new-artifact-directory> \
  --host-jsonl <new-host.jsonl> --checkpoint <new-checkpoint.json> \
  --timeout 120 --harness-args --method-witness-fixture
```

`--dry-run` prints bootstrap commands without launching. A watchdog terminates
only this runner's process tree. Tiering is disabled in the child environment
and recorded; no global interpreter selector or forced compilation is enabled.
The runner supplies GROUPED_WITNESS_CDB=1 plus GROUPED_WITNESS_JSONL and
GROUPED_WITNESS_CHECKPOINT to the child. The host checks for an attached native
debugger, flushes identities, atomically publishes the checkpoint, then breaks.
Without the environment variable its debugger helper is inactive.

## Phases

Checkpoint schema `runeclr-grouped-checkpoint/1` contains checkpoint_id, run_id,
process_id, group, group_ordinal, phase and created_utc. Normal A/B/A and recovered
groups each follow:

| Phase | Required observations |
| --- | --- |
| before-framework | FrameworkEntry.Initialize |
| before-author | AuthorEntry.Run and FrameworkEntry.Touch |
| before-callback | AuthorEntry.OnFrameworkEvent |
| before-cleanup | Clear native and SOS pending breakpoints |

Failure and deliberate observer-root groups exercise lifecycle controls only.
Completion requires all phases and targets, the fixture lifecycle summary,
actual target exit 0 and unchanged inputs. Host records remain scalar-only and
always carry witness_verified=false. The fixture-only exit 0 proves its own
identity/lifecycle gates; --method-witness retains NOT-VERIFIED exit 3.

## Evidence and limits

Framework observations require actual native RIP equal to DAC Current CodeAddr
and !ip2md resolving that PC to the host MethodDesc. Disassembly is a contiguous
observed instruction span, not whole-method size or coverage. The default arm
uses SOS !bpmd. The optional --framework-hardware-fallback inspects naturally
compiled code after a failed software breakpoint at a real CLR notification,
then arms a hardware execution breakpoint. Address probes and arming never
produce a body event: a later actual stop must pass the same capture parser.

The accepted --framework-natural-hardware route instead observes the runtime's
DACNotifyCompilationFinished hook directly. Its rcx/rdx values must match the
host MethodDesc and DAC code address before a hardware execution breakpoint is
armed. It creates no compile/probe event and uses no software method-body patch.
--cdb-readonly-breakpoints passes CDB -robp; that exploratory route is not the
accepted capture. Choose only one framework observation route.

Author observations stop at native coreclr!InterpExecMethod with first-entry
r9=0. The frame chain must equal the host MethodDesc, and startIp must equal
its live interpreter-code pointer. PDB probes supply offsets and header size in
that run. Executor RIP and interpreter IR addresses are separate. Subsequent
body/callback markers bind the observation to the invocation.

--diagnose-framework-interpreter is an incompatible diagnostic mode observing
only whether Initialize enters the interpreter. It cannot satisfy mixed-mode
acceptance. Missing an interpreter hit is not JIT proof.

The manifest binds inputs, host records, events and raw transcript by SHA-256.
Transcript spans use UTF-8 byte offsets. The verifier joins per-group MethodDesc,
token, host MVID, staged PE bytes and ALC identity. Its identity source is
host-methoddesc-chain: MVID comes from the host and is rebound to bytes, not
claimed as an independent debugger read. DAC token and module address provide
corroboration. Collector fidelity remains an assumption.

```text
py -3 verify.py --manifest <manifest.json> --repo-dir <repository-root> \
  --json-out <verify-report.json>
```

Missing targets, stale identities, bad hashes, failed breakpoint insertion,
resume frames, command-echo-only spans, early exit and absent body markers fail
closed. Entry evidence proves neither whole-method coverage nor absence of JIT
elsewhere, performance, hostile-code isolation, or iOS support.
