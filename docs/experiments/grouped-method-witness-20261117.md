# Grouped host method-entry witness (2026-11-17)

The Windows x64 fixture now has measured method-entry evidence for ordinary JIT
framework code and required-interpreter author code in separate collectible
contexts. A bounded capture completed A -> B -> A, framework/author failures
followed by recovery, deliberate observer retention and release, collection of
both contexts, and target exit 0. Independent replay accepted 16 observations
with 635 checks, zero failures and no missing schema extensions.

This is a fixture method-entry result. It does not establish whole-method
coverage, absence of JIT elsewhere, performance, iOS support, or sandboxing.

## Reproducible cut

- RuneCLR base: `469b7cc0081d90129d1d98cdc918865c7366d6d6`; the new code changes
  tests and diagnostic tools, without product, contract or CoreCLR edits.
- Private runtime source: `ce298588cb29796be613928fcb5ecd6ad7407b47`, Release,
  Windows x64, private .NET 12 layout with its matching CoreLib, DAC, DBI and PDB.
- Reflection-policy and origin-scan capabilities enabled. Framework context
  policy was observed as 0, author policy as 1, and global
  `RuneCLRInterpretCollectible` as 0. These values are configuration diagnostics,
  not the execution evidence.
- CDB 10.0.22621.2428 and SOS 9.0.13.11903. Tiering disabled in the child only;
  no global interpreter selection and no force-compilation call.

The [portable scalar extract](../evidence/grouped-method-witness-20261117/summary.json)
records runtime/tool hashes, image identities, all 16 per-group observations,
raw artifact hashes and the accepted verifier report hash. It is an extract,
not a substitute for the original private PE inputs and debugger transcripts.
No machine paths or company payloads are published in that extract.

## What was observed

| Target | Execution observation | Number |
| --- | --- | --- |
| FrameworkEntry.Initialize | Actual native entry RIP equals DAC CodeAddr; `!ip2md` resolves the same MethodDesc | 4 |
| FrameworkEntry.Touch | Actual native entry with the same native/DAC/MethodDesc chain | 4 |
| AuthorEntry.Run | Native InterpExecMethod first-entry stop, frame chain equals author MethodDesc | 4 |
| AuthorEntry.OnFrameworkEvent | Same interpreter chain for the direct method-group callback raised by the framework | 4 |

Each normal A1/B1/A2 or recovered group contributes all four targets. The
before-author checkpoint is shared by Run and Touch. Image SHA-256, MVID,
MethodDef token, declared method, ALC name, PID, run and group ordinal bind
each observation to the staged bytes and the loaded method identity.

For author methods, r9 is zero, frame.startIp equals the live MethodDesc
interpreter-code pointer, and the method handle in the interpreter frame equals
the host RuntimeMethodHandle.Value. IR starts after the PDB-measured header and
has codeSize * 4 bytes. The stopped native PC belongs to InterpExecMethod and is
outside the IR buffer; it is never described as an IL or IR offset. Subsequent
entry/callback markers follow their checkpoint publication times.

Framework disassembly gives a contiguous span observed from the actual RIP.
It does not give whole-method coverage or the complete method size. Identity
uses the declared `host-methoddesc-chain`: MVID comes from the host and is
rebound to PE bytes; DAC independently corroborates MethodDef token and module
address. MVID is not represented as an independent debugger read. Collector
fidelity remains an explicit assumption.

## Natural compilation and hardware breakpoints

The accepted collector uses `--framework-natural-hardware`. It stops at
`coreclr!DACNotifyCompilationFinished` for the selected MethodDesc during
natural compilation. The observed rcx must equal that MethodDesc, and rdx must
equal the DAC-reported code address. A separate probe requires no interpreter
code, the host token, and `!ip2md` resolving the candidate code address to the
same MethodDesc. Only then is a hardware execution breakpoint armed at it.

The compiler notification, code probe and breakpoint arming produce no witness
events. A later real method-body stop must independently satisfy the native
RIP/DAC/MethodDesc checks. The measured code pages were mapped executable/read
views. No target-body software patch was used in the accepted capture.

Earlier attempts are retained as failed or partial evidence. SOS software
breakpoint insertion first failed with error 998. CDB `-robp` reached Initialize
but a later first-chance native access violation stopped that attempt; its cause
was not established. The hardware route continued without that observation.
No runtime defect or runtime fix is claimed from this comparison. Other
iterations corrected debugger expression/conditional grammar and log parsing.

## Callback scope and collection controls

The original fixture callback used a closure that called a private handler.
An interpreter can enter through the generated closure and invoke the private
handler inside its existing execution loop. The private handler's native-entry
breakpoint was not observed in that attempt, although its business marker ran.

Witness mode therefore uses an ordinary direct static method-group delegate
to `OnFrameworkEvent()`, with the host retained in an author-owned static and
the shared callback body in `OnFrameworkEventCore`. Both methods are NoInlining.
Non-witness modes retain the original closure behavior and policy checks.
The four accepted callback events prove this direct method-group route only;
they do not prove a private child-frame entry for the original closure.

Host records contain only copied scalars and always set witness_verified=false.
A deliberately retained MethodInfo kept the author and framework alive across
forced GC. Clearing that root and returning from the helper allowed both
contexts to collect. Normal and failed groups also pass their retirement gates.
There is no zero-GC sensitivity or collection-timing claim.

## Verification and preservation

Use the [collector instructions](../../eng/grouped-method-witness/README.md)
with explicit local input paths and a new artifact directory. Run the fixture
through the matching private runtime, then run the independent verifier. The
fixture-only exit 0 validates identity/lifecycle gates; it does not set an
execution verdict. `--method-witness` retains NOT-VERIFIED exit 3 because it
does not consume the external bundle inside the host process.

The final verifier checks the packed ECMA-335 metadata-table layout on real
managed PE images, raw UTF-8 byte ranges, genuine debugger stops, non-echo hit
labels, image/method/ALC binding, both targets in the shared checkpoint,
subsequent body markers and the target exit. Its parser also recognizes CDB's
strict `Last event: <pid>.<tid>: Hit breakpoint <n>` form. Echoed or embedded
lookalikes remain negative controls.

The original verifier report with eight unrecognized Last-event lines remains
preserved. The accepted report and an acceptance receipt bind the corrected
verifier source hash to the same unchanged bundle. One independent Orca Worker
audited all 16 raw observations; another independently reviewed the collector
and replayed the accepted bundle. Both accepted the stated scope.

Synthetic controls: 112 debugger-helper tests, 84 verifier tests, 20 collector
state-machine tests and 5 I/O controls. These controls are separate from the
measured capture and do not themselves establish execution.

The final standard baseline ran in an independent detached validation tree
with the changed source files copied byte-for-byte. Solution build passed with
zero warnings/errors, Runtime.Tests 156/156, Packaging.Tests 333/333 and
SampleHost --collect exit 0 with all sample unloads collected. Grouped stock
negative 2/2, policy negative 11/11 and policy audit zero denials also passed.
Accepted capture inputs were unchanged before and after those regressions.

An earlier --artifacts-path attempt could not stage all test inputs because
some existing targets hardcode standard bin paths. Its missing-fixture failures
remain recorded; standard paths inside the independent tree supplied the final
baseline without changing those targets or overwriting the capture inputs.
