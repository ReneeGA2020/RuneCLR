# Configured instruction-budget cost - Windows

On 2026-10-13, two eight-process experiments compared the same author IL on
the same private 099dacd Windows x64 Checked runtime with native required-
interpreter policy in both lanes. Configuring a high terminal allowance made
this small arithmetic callback materially slower: in the pinned-CPU run its
pooled median changed from 31.505 ms to 91.655 ms, a 190.92% increment (2.91x).
This is experimental Checked cost; it does not predict Release, mobile or
game-frame performance.

The later matching Release run measures the same author IL: after the owned
Android emulator was shut down, callback medians are 18.850/90.434 ms
(+379.75%, 4.80x). Both actual Release runs and the Checked records remain
separate. The Release build, execution/accounting checks and measurement
limits are recorded in the final section of this document.

The later2026-10-14 [minimal counter increment](windows-budget-increment-hotpath.md)
has a separate matching20405f7 build, complete declared Windows acceptance
and five byte-verified locked RMWs on the normal admitted path. The original
099 timings below remain historical controls. A
[fresh same-machine baseline/candidate/baseline comparison](windows-budget-increment-performance.md)
measures14.73-16.06% less budgeted callback time in this kernel, with unchanged
managed images and independently reviewed accounting/retirement.

A [stock Lua native count-hook reference](lua-budget-overhead.md), measured
separately on2026-10-14, costs6.37x at count1 and2.49x/2.44x at count100/1000
in the same arithmetic recurrence. It uses ordinary per-state counters and
catchable Lua errors rather than shared atomic terminal/unwind accounting;
the enforcement and counted instruction units differ.

## What is compared

The no-config lane creates an interpreter-required collectible context with
no instruction meter. The high-budget lane creates a terminal-prototype
context with execution allowance 1,000,000,000,000 and cleanup allowance 4096.
Both acknowledge native policy 1 before loading the identical
RuneCLR.BudgetKernel.dll. Private trusted CoreLib policy, terminal and finalizer
versions must all acknowledge 1; no installed runtime is changed.

The [fixed author kernel](../benchmarks/RuneCLR.BudgetKernel/Kernel.cs) starts
uint32 state 12345, performs 100,000 LCG updates through a private non-inlined
helper, and sums each update's low byte. Every callback returns 12749776. A
separate trusted oracle and a Python raw-evidence review check the result. The
real MapRunner fixture calls the same kernel for three ticks and logs 38249328.
It uses the existing RequireInterpreter and optional
PrototypeInstructionBudget host options. The host remains a dirty development
checkout; frozen source and actual managed hashes bind it.

No-config is not instrumentation-off. In this candidate every interpreter
dispatch still obtains the current method definition's binder and follows the
null-meter branch. Configured terminal accounting adds the meter/latch/quota
work. Both lanes already include definition-owner lookup and the instrumented
dispatch path; this experiment cannot measure those baseline costs or the
full instrumentation overhead relative to an unpatched interpreter. There is
no JIT-author baseline.

## Timing and process design

Four paired rounds each run two fresh processes sequentially. Order alternates
no-config/high-budget then high-budget/no-config. Each direct-callback context
has three separately recorded warmups and nine measured callbacks. Setup
records context creation, author loading and delegate resolution separately;
the first warmup includes first author-method preparation. Native snapshots,
result checking, metadata inspection, JSON emission and diagnostic GC occur
outside the callback timer. Snapshots use separate synchronous scalar reads,
not an atomic concurrent observation.

The whole-session measurement uses three warmup sessions and nine timed fresh
MapRunner sessions per process. Its timer includes native bridge binding,
context creation/loading, constructor, start/three ticks/stop, host cleanup and
the unload request; validation and final diagnostic GC are outside. It includes
host budget-option overhead as well as runtime charging, so its delta cannot
be attributed wholly to the native meter.

Attempt1 was unpinned. Attempt2 pins every child to logical CPU2 (affinity
mask 4), checks the actual acknowledged affinity and adds a trusted MapRunner
native-entry positive control. The i7-10700K machine has 8 cores/16 logical
processors. Machine-wide load, CPU clocks, thermals and OS caches are not
isolated; other project tasks may run concurrently. The pairing controls some
drift but does not supply confidence intervals. Setup timings remain raw
observations, not a separate configured-meter performance claim.

| Timing scope, attempt2 | No-config median ms (min-max) | High-budget median ms (min-max) |
| --- | ---: | ---: |
| Warm kernel callback, 36 samples per lane |31.505 (26.440-52.992)|91.655 (83.019-123.838)|
| Whole fresh three-tick session, 36 samples per lane |99.580 (84.827-240.483)|275.261 (254.831-417.122)|

The four paired callback increments are 141.82%, 199.06%, 205.39% and 190.91%.
The earlier unpinned callback pooled medians are 29.405/85.546 ms (+190.92%).
The first run is preserved with its then-current source snapshot and no
affinity/native-host positive control; it is not substituted for attempt2.

## Execution, native accounting and retirement

After execution, each of eight attempt2 processes inspects both author
Kernel.Execute and private Kernel.Update through the pinned Windows x64
precode observer. Both positively identify interpreter-precode type 6.
MapRunner.Run is native in all eight processes. Global interpretation and the
collectible diagnostic switch are both 0; the private native policy and actual
entry observations establish the tested path. The observer reads executed
method entries; it is not an exhaustive native invocation trace.

Every measured high-budget callback advances the native execution ledger by
2,600,016 IR dispatches. Each high-budget three-tick host session reports
7,800,101 dispatches. Every final snapshot preserves execution remaining plus
executed equal to the original allowance, no exhaustion/terminal latch,
reason 0, and cleanup executed 0/remaining 4096. No-config returns null budget
snapshots rather than a fabricated zero-dispatch counter.

Each measured direct callback reports zero current-thread allocations and zero
GC collection-count deltas. Each process retires its direct context and twelve
host contexts after execution frames return: all 104 contexts collect in
attempt2. Attempt1 also collects 104. Forced collection is a post-run
diagnostic, not a timed/per-frame policy or proof of whole-process memory
isolation.

## Reproduction and binding

Use a fresh output directory:

~~~powershell
py -3 -B eng/benchmark-budget-overhead.py --output artifacts/budget-overhead/new-run --pairs 4 --samples 9
py -3 -B eng/budget-overhead-audit.py --evidence artifacts/budget-overhead/new-run --output artifacts/budget-overhead/new-review/results.json
~~~

The launcher checks tracked-clean runtime 099dacd07d8d890822f7422f895337733457ab3c
against matching private native products and source stamps. Upstream base is
0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de. It hashes seven native/CoreLib/host
files, frozen host/author/configuration sources, and all built managed files;
native/managed/source inputs are checked for changes across measurement.
Its private SDK is 11.0.100-rc.1.26425.128; both benchmark projects build with
zero warnings/errors. Every actual process has a PID/nonce/argument/environment
receipt, hashed stdout/stderr, and a 180-second owned watchdog that always
fails the run on expiry. None timed out.

- [Pinned run results and all lane identities](../artifacts/budget-overhead/windows-checked-20261013-attempt2/results.json), SHA256 1f05b19aa71ab2e3011bfece8df1418382e1809ba54663c3b93e8f091e8b7dfb.
- [Pinned request, source and runtime hashes](../artifacts/budget-overhead/windows-checked-20261013-attempt2/request.json), SHA256 196e5b0b1b4518b23dfd14aa0a76f30d382d63e8a9d9dd0cc3f03b021afa0326.
- [Actual managed images](../artifacts/budget-overhead/windows-checked-20261013-attempt2/managed-identity.json): author DLL SHA256 74504451a283fa9995f4762429538ec0ed44787c43c2621bfd2182e3b93f3bb8.
- [Raw binding/scalar/checksum review](../artifacts/budget-overhead/windows-checked-20261013-attempt2-review/results.json) checks process/raw/source/image bindings, executed entries, all ledgers and all collections. Four alterations of result JSON (PID, entry flag, dispatch delta and raw hash) are rejected without modifying original evidence.
- [Root independent review](../artifacts/budget-overhead/windows-checked-20261013-attempt2-root-review/results.json) separately passes the same raw binding, arithmetic oracle, entry/ledger checks and four corruption controls.
- [First unpinned run](../artifacts/budget-overhead/windows-checked-20261013-attempt1/results.json). A later PowerShell reader used case-insensitive JSON conversion on keys samples/Samples and failed; its correction uses Python, while attempt2 gives the count a distinct sampleCount key. This was a read-only observer failure.

The next performance decision needs measurements on actual game workloads
and target devices. The original measurement did not change owner lookup,
atomics or sampling frequency. Later changes require separate invariant and
termination acceptance.

## Matching Windows Release increment

The matching Release build also completed on 2026-10-13. It uses the unchanged
tracked-clean runeclr/session-finalizer worktree at the same candidate
099dacd07d8d890822f7422f895337733457ab3c, upstream base
0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de. Fresh Release product/object
directories were created separately from existing Checked outputs.

The actual build of
clr.runtime+clr.jit+clr.hosts+clr.corelib+clr.tools+clr.nativecorelib completed
in 8m52s with zero warnings/errors using private source SDK
11.0.100-rc.1.26420.103. Thirty-six patch-source files, actual CMake Release
configuration with interpreter/native-JIT features, seven native compilation
owners/objects, and eight native/CoreLib/compiler products were verified.
Actual owner commands contain FEATURE_INTERPRETER and /O2, without DEBUG.
The native stamps identify the candidate commit.

The new layout overlays nine fresh Release runtime/CoreLib files, including
the GC and diagnostic libraries, onto previously hashed unchanged same-
upstream-base framework libraries/hosts. CoreLib IL, its compiled image and
crossgen2 all come from the fresh Release build. There are 527 layout file
hashes. The installed runtime and Checked products remain unchanged. This is
a private matching layout, not shipping packs or a complete production budget
acceptance.

### Actual runs and load boundary

Both Release runs use the unchanged arithmetic fixture DLL, the same
RequireInterpreter/no-config versus high-budget comparison, CPU2 affinity,
four alternating paired rounds, three warmups and nine samples per process.
No runtime build ran during either measurement.

Attempt1 overlapped the independent Android debugger/emulator task. Its large
spread prompted a second run after that task reported owned app uninstall,
emulator shutdown and empty ADB devices/forwards. Root also paused builds and
runtime tests throughout attempt2. The first run is preserved; the second
reduces that observed concurrent workload, without claiming complete machine
isolation or selecting a lower number. In fact, its high-budget callback
median is higher. Uncontrolled system scheduling/clocks/cache effects and
wide within-run ranges remain.

| Release timing scope | No-config median ms (min-max) | High-budget median ms (min-max) |
| --- | ---: | ---: |
| Attempt1 warm callback |19.150 (13.096-48.399)|86.805 (76.252-221.992)|
| Attempt1 fresh three-tick session |52.331 (39.846-109.190)|267.620 (234.400-404.245)|
| Attempt2 warm callback |18.850 (13.626-28.771)|90.434 (78.112-134.159)|
| Attempt2 fresh three-tick session |57.090 (45.014-124.141)|268.199 (242.003-305.639)|

Each row contains 36 samples per lane. The attempt2 pooled callback increment
is 379.752%, or 4.7975x. The paired increments are 539.64%, 334.75%, 420.11%
and 328.29%; this variation prevents a universal slowdown claim. The ratio
compares configured native accounting against the already instrumented null-
meter path, and does not estimate the cost of all instrumentation. Whole-
session timing additionally includes the host's budget option/binding/query
work. The large measured incremental cost warrants profiling before a game
pilot. The offline inspection below identifies repeated atomic work in the
actual gate; its share of elapsed time is not established.

### Execution, scalar and provenance checks

All sixteen actual Release processes positively observe interpreted type 6
entries for Kernel.Execute and private Kernel.Update after invocation, with
trusted MapRunner.Run native. Every direct callback returns checksum 12749776
and each fresh three-tick host session logs 38249328. High-budget callback
native dispatch delta is still 2,600,016; session execution is 7,800,101.
Snapshots preserve the original allowance, remain nonterminal with reason 0,
and use no cleanup instructions. No-config snapshots remain null. Every
measured direct callback reports allocation 0 and GC deltas 0. All 104 contexts
collect in each run, after frames return. This is finite normal-execution
evidence, not a fresh exhaustive Release terminal/finalizer acceptance.

The benchmark now accepts an explicit --configuration Checked or Release;
Checked remains the default. It binds the requested configuration to actual
CMake/cache/command and successful build/layout receipts, matching native
and CoreLib/compiler products, and the exact loaded runtime hashes. The
second Release run additionally freezes all 36 native patch sources and the
actual host-build SDK executable/version. All source/runtime/product/layout
inputs are rechecked across measurement. Its author DLL SHA256 is the same
74504451a283fa9995f4762429538ec0ed44787c43c2621bfd2182e3b93f3bb8 as Checked.

The enhanced reviewer recomputes all pooled counts/min/max/medians/setup,
paired medians/percentages and pooled percentage, and verifies that scope and
configuration agree with actual build/CoreLib provenance. Nine modifications
of result/request views are rejected, including false percentages, counts,
scope and a forged configuration label. Original evidence is unchanged.
The old Checked record is also accepted by the enhanced reviewer using its
original schema and matching live Checked products/cache.

- [Fresh Release build result](../artifacts/budget-overhead/windows-release-build-20261013-attempt1/build-result.json).
- [Matching Release layout and all 527 hashes](../artifacts/budget-overhead/windows-release-build-20261013-attempt1/layout-receipt.json), SHA256 9f598275487ff92e823abcdfa9d847aa58353f537aaf97c73009b8f9df811778.
- [Release attempt1 raw-bound results](../artifacts/budget-overhead/windows-release-20261013-attempt1/results.json), SHA256 2b2c73e89b8ff15509604f93613fb3e7a9df2ba2e4a56451115926c211b101be.
- [Release attempt2 raw-bound results](../artifacts/budget-overhead/windows-release-20261013-attempt2/results.json), SHA256 b9292c354a94cbaf1516e353ddc7b0cd4ceab7c3e06720b4fb500517675220e1.
- [Release attempt2 expanded review](../artifacts/budget-overhead/windows-release-20261013-attempt2-review/results.json), passing native/configuration/ledger/binding/summary checks and nine rejection controls.
- [Original Checked record expanded review](../artifacts/budget-overhead/windows-checked-20261013-expanded-review/results.json), same original results SHA, now with nine rejection controls.

Use a fresh build and experiment directory. This command requires that fresh
Release product/object directories do not already exist, so preserve existing
products and use another dedicated source worktree for a new full build:

~~~powershell
py -3 -B eng/build-budget-release.py --runtime <tracked-clean-099dacd-worktree> --output <new-build-evidence>
py -3 -B eng/benchmark-budget-overhead.py --configuration Release --runtime <same-worktree> --layout <new-build-evidence>/layout --build-evidence <new-build-evidence> --output <new-benchmark-evidence> --pairs 4 --samples 9
py -3 -B eng/budget-overhead-audit.py --evidence <new-benchmark-evidence> --output <new-review>/results.json
~~~

## Offline inspection of the matching Release dispatch gate

On 2026-10-13 the actual Release coreclr.dll and private PDB were inspected
with Windows SDK CDB 10.0.22621.2428, using -z to open the PE image offline.
No managed runtime process, debugger attach, timed sweep or native rebuild ran
in this increment. The DLL has unchanged SHA256
38d00ec31958fe700f6ebc732f46f41440c5ad7c0cfe6fd481904efa621e6fa1.
Its PE RSDS identity and actual PDB info stream independently match GUID
61416689-f306-42cf-9d99-ea3802f2c670, age 1. InterpExecMethod starts at RVA
0x1984a0. The private PDB places remaining at +0x08, executed at +0x10 and
phase at +0x28. Source snapshots match the unchanged candidate and the build
receipt's patched-source hashes.

All 307 emitted instruction rows were mapped through the PE section table
and compared byte-for-byte to the actual DLL. The charge and meter functions
are inlined into InterpExecMethod. CDB's "Unable to verify checksum" warning
corresponds to PE CheckSum zero; private PDB symbols loaded. Its "Flow analysis
was incomplete" notice prevents a complete-function inventory claim. The
central gate and normal admitted branch, including destinations, are present.

### Normal admitted opcode path

With a terminal meter, phase 0, positive allowance and first-attempt CAS
success, each dispatch executes six locked RMWs:

| Actual RVA | Meter operation | Actual opcode |
| --- | --- | --- |
| 0x1986b8 | Outer IsTerminated phase read | lock cmpxchg dword ptr [rdx+28h],esi |
| 0x198799 | ChargeExecution repeats phase read | lock cmpxchg dword ptr [rdx+28h],esi |
| 0x1987b2 | Read remaining using zero CAS | lock cmpxchg qword ptr [rdx+8],rsi |
| 0x1987c1 | Admit instruction by decrement CAS | lock cmpxchg qword ptr [rdx+8],rcx |
| 0x1987cb | Read executed using zero CAS | lock cmpxchg qword ptr [rdx+10h],rsi |
| 0x1987d5 | Increment executed using CAS | lock cmpxchg qword ptr [rdx+10h],rcx |

The phase-0 branch at 0x1986c9 selects 0x19874e; the terminal flag selects
0x198797; the second phase-0 check selects 0x1987b0. Positive remaining and
CAS success reach 0x1987dd and 0x1987f3, returning to the opcode switch at
0x198691. The output contains 22 lock rows across diagnostic, cleanup and
rejection branches, not 22 per opcode. Contention can repeat CAS operations;
denied execution and cleanup follow different paths.

The 0x198610-0x198652 owner block contains nine pointer loads, a MethodDesc
chunk-index byte load and a CFG-guarded virtual meter getter call. Source
ownership follows the current definition through Module, PEAssembly and
AssemblyBinder on every dispatch. Null meter branches to 0x198691. Both
benchmark lanes already pay that lookup and virtual call. The 4.7975x ratio
therefore does not attribute the shared cost. Disassembly does not establish
a CPU-time percentage for the atomics; no sampling result is claimed.

### Smallest candidate change

The first candidate replaces terminal TryConsume's executed zero-CAS read and
increment-CAS retry loop with one InterlockedIncrement64, ignoring its return. Keep quota
admission CAS, both phase checks, owner lookup and diagnostic Charge's original
saturating behavior. Shared TryConsume serves execution and terminal cleanup
ledgers, so both require acceptance. The separate20405f7 candidate now
[implements and accepts this change on Windows](windows-budget-increment-acceptance.md).
Mobile acceptance for the new candidate remains outstanding.

The immutable positive allowance is at most INT64_MAX; executed starts at
zero. Every increment follows one successful remaining decrement, admitting
at most allowance increments. The terminal ledger cannot overflow, every
admitted charge is counted once with concurrent callers, and remaining +
executed = allowance holds after in-flight charges finish. Snapshots remain
independent scalar reads, not a two-field transaction. Interlocked increment
retains full ordering without changing owner lifetime, layout, contracts or
phases. If the matching compiler emits one atomic increment, this removes one
locked operation from the normal six-operation path. It does not predict a
one-sixth time improvement; fresh disassembly and paired measurement are needed.

The [independent source review](../artifacts/budget-overhead/minimum-increment-source-review-20261014-attempt1/review.md)
on 2026-10-14 binds the exact header, dispatch callers and target interlocked
implementations. It finds no blocker under the finite-admission invariant,
while retaining the existing phase/admission race and separate snapshot reads.
The [matching Release budget acceptance](windows-release-budget-acceptance.md),
[production controls](windows-release-production.md) and
[joined-worker baseline](windows-terminal-concurrency.md) now pass. These are
the pre-change baseline. The
[new candidate's actual PE/PDB review](windows-budget-increment-hotpath.md)
binds its own emitted code separately.

A later candidate can replace the two phase zero-CAS reads and initial
remaining zero-CAS read with explicitly atomic acquire loads. Together with
the first change, normal execution could retain two locked RMWs: quota CAS and
executed increment. Target/compiler alignment and atomicity must be proved
for Windows x64 and each ARM64 build; VolatileLoad's generic contract alone
does not guarantee atomicity. Preserve a safe fallback for other targets. Keep
the second phase check until concurrent admission/phase transitions have been
reviewed. Plain loads and deleting the recheck are outside the minimum change.

Per-frame meter caching is a separate larger proposal, requiring ownership
refresh and lifetime proofs across child/tail calls, CALLI, EH filters, cleanup,
finalizers and retirement. Receiver-based or process-wide caches do not
preserve definition-owner attribution. This inspection does not justify that
change yet.

Required acceptance before replacing the current patch:

- Exact allowance and denial before the next opcode; constructor/static
  constructor/tick/stop accounting; no catch/filter continuation.
- Finite/infinite finally/helper/delegate cleanup; exact separate allowance
  and phase 1-to-2 transition.
- Finalizer queue/exhaustion, inherited trusted finalizers versus overrides,
  recovery and collection after strong roots and frames return.
- Controlled same-context concurrent admission, no quota overshoot or lost
  increments, and quiescent reconciliation; snapshots cannot prove a
  two-field transaction.
- Owner/framework transitions, reentrancy/tail calls, retired-query rejection
  and unchanged default/legacy diagnostic behavior.
- Matching native/CoreLib builds and actual entry evidence on each target,
  upstream controls, host-budget and lifecycle suites, then the unchanged
  paired kernel to measure rather than infer the improvement.

### Evidence and independent controls

- [Successful offline inspection](../artifacts/budget-overhead/hotpath-offline-20261013-attempt2/results.json),
  [raw CDB output](../artifacts/budget-overhead/hotpath-offline-20261013-attempt2/cdb.stdout),
  [all byte-matched instructions](../artifacts/budget-overhead/hotpath-offline-20261013-attempt2/instructions.json).
- [Independent PE/PDB/source review](../artifacts/budget-overhead/hotpath-offline-20261013-attempt2-final-review/results.json):
  GUID/age, source/build/input/raw bindings, 307 PE byte matches, six normal-path
  lock rows and ten decoded branch targets pass. Six in-memory corruption
  controls reject false counts, forged instructions/branch targets, compiled-
  source mismatch, forged DLL hash and actual modified PDB-info age.
- [Root review on 2026-10-14](../artifacts/budget-overhead/hotpath-root-review-20261014-attempt1/results.json):
  the independent audit passes against the unchanged matching DLL/PDB and
  source: 307 instruction-byte matches, 22 observed lock rows, six normal
  admitted-path lock rows, ten branch destinations and six rejected corruption
  controls. This remains offline machine-code evidence, not CPU sampling.
- [Preserved first inspection](../artifacts/budget-overhead/hotpath-offline-20261013-attempt1/results.json):
  CDB exit 0; observer expected "private symbols" rather than the emitted
  "private pdb symbols" and reported false. The corrected attempt adds PE
  byte verification. The final independent review supersedes its initial
  synthetic PDB-age comparison with an actual in-memory info-stream mutation.
  No original DLL, PDB, source or evidence file was changed.

~~~powershell
py -3 -B eng/analyze-budget-hotpath.py --runtime <tracked-clean-099dacd-worktree> --build <matching-release-build-evidence> --output <new-offline-evidence>
py -3 -B eng/audit-budget-hotpath.py --evidence <new-offline-evidence> --output <new-review>/results.json
~~~
