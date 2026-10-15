# Terminal counter increment - Windows Release

On 2026-10-14 the private runtime candidate
`20405f7ae23e183e038703aa5e356b3310fef427` implements the minimal terminal
counter change on parent `099dacd07d8d890822f7422f895337733457ab3c`. Its
upstream base remains `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. This is
an optimization of RuneCLR's custom meter, not a Microsoft runtime defect fix.

## Source and matching build

Only `src/coreclr/vm/runeclrinstructionmeter.h` changes. A successful
remaining-allowance CAS is followed by `InterlockedIncrement64(&executed)`
instead of an executed zero-CAS read and increment-CAS loop. The return value
is unused. Admission, both execution-phase checks, definition-owner lookup,
terminal latch, unwind handling, finalizers, diagnostic saturation and native
bridge layouts retain their parent implementation. TryConsume serves both
execution and cleanup counters.

The positive immutable allowance is at most INT64_MAX. Each increment follows
one successful admission, so at most that many increments occur and the
executed counter cannot overflow. Remaining plus executed equals the allowance
after in-flight charges finish; independent scalar snapshots are not a
transaction. The existing phase/admission gap remains.

The new tracked-clean worktree is `E:/runtime-increment-20261014`, branch
`runeclr/terminal-counter-increment`. The
[matching Windows x64 Release build](../artifacts/budget-increment/windows-release-build-20261014-attempt1/build-result.json)
reports zero warnings/errors. The
[layout receipt](../artifacts/budget-increment/windows-release-build-20261014-attempt1/layout-receipt.json)
binds 36 patch-source files, seven compilation owners and 527 layout files.
New native/CoreLib/compiler products overlay the preserved same-upstream-base
framework and hosts in a private layout. Installed .NET and the099 products
remain untouched.

## Actual admitted paths

The [offline inspection](../artifacts/budget-increment/hotpath-20261014-attempt1/results.json)
uses CDB on the actual PE and private PDB. The
[independent auditor](../eng/audit-budget-increment-hotpath.py) reads PE sections,
RSDS identity and the PDB info stream independently. Its
[result](../artifacts/budget-increment/hotpath-review-20261014-attempt1/results.json)
passes 289 actual instruction-byte matches, 24 encoded branch destinations,
38 connected normal-path rows and 46 connected cleanup-path rows. Six
in-memory corruption controls reject instruction/branch/source/PDB/count
alterations without changing original evidence.

PE/PDB GUID is `e2db9951-8c20-40e4-bd72-1dd52ef9abe5`, age1. PDB field
offsets are remaining0x08, executed0x10, cleanupRemaining0x18,
cleanupExecuted0x20 and phase0x28. The function prologue clears R14d at
RVA0x19851a; zero-CAS reads use R14/R14d.

| Normal admitted phase-0 path RVA | Operation |
| --- | --- |
| 0x1986a8 | Outer phase zero-CAS read |
| 0x198769 | ChargeExecution phase zero-CAS recheck |
| 0x198783 | Remaining zero-CAS read |
| 0x198799 | Remaining admission decrement CAS |
| 0x1987a1 | Executed `lock inc qword ptr [rdx+10h]` |

That path contains five locked RMW operations, versus the
[byte-verified099 baseline's six](budget-overhead.md). It assumes a non-null
terminal meter, phase0 at both reads, positive remaining and first-CAS success.
The reviewed cleanup-owner path has six locked operations: outer phase read,
cleanup eligibility recheck, phase1 check, cleanup remaining read, admission
CAS and `lock inc qword ptr [rdx+20h]` at0x198704. CAS contention can retry;
diagnostic, denial and other cleanup paths have different counts.

CDB observes20 lock rows across the emitted function flow, not20 per opcode.
The raw checksum warning (PE checksum0) and incomplete-flow warning remain
recorded. This is offline PE/PDB/source evidence, not runtime CPU sampling,
an exhaustive function inventory or a time-attribution result. Fewer locked
operations do not by themselves predict a particular speedup.

## Acceptance and reproduction

[Terminal, finalizer and host acceptance](windows-budget-increment-acceptance.md)
and [joined-worker/production acceptance](windows-budget-increment-concurrency.md)
pass on these matching products. Mobile builds and physical devices have not
accepted this new candidate. The
[exported patch stack](runtime-patch-reproduction.md) reconstructs all36
changed source files exactly while retaining the original099 reconstruction.

Use fresh directories:

~~~powershell
py -3 -B eng/analyze-budget-hotpath.py --candidate-commit 20405f7ae23e183e038703aa5e356b3310fef427 --runtime E:/runtime-increment-20261014 --build artifacts/budget-increment/windows-release-build-20261014-attempt1 --output artifacts/budget-increment/hotpath-new
py -3 -B eng/audit-budget-increment-hotpath.py --evidence artifacts/budget-increment/hotpath-new --output artifacts/budget-increment/hotpath-review-new/results.json
~~~

The audit profile binds this exact emitted PE/PDB. A rebuild with changed
RVA/identity requires reviewing and freezing a fresh actual path profile;
removing byte or identity checks does not validate another build.
