# Controlled packages with pumped native budgets

## Measured Windows acceptance - 2026-10-15

The approved-package loader, host-pumped `MapSession`, and private native
terminal budget now pass together on Windows x64 Release. This combines the
previously separate [package](package-execution-tests.md) and
[raw-IL budget](host-instruction-budget.md) lanes. The private runtime remains
`20405f7ae23e183e038703aa5e356b3310fef427`, based on upstream
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. No runtime source changed.

The operator fixture generator adds nine packages with `--include-budget`.
Default generation stays at nine packages; `--include-pumped` stays at twelve;
both flags generate twenty-one. New entries and their private cleanup helper
pass the unchanged `managed-il-gameplay-v1` capability gate. A first inherited
entry fixture was correctly rejected; the fixture was corrected to implement
the interface directly. The capability policy was not relaxed.

The player adds `--native-budget`, requiring `--pump --require-interpreter`.
Its original twenty-two unbudgeted pumped groups remain intact. Eleven extra
groups produce twenty-five native-budget session receipts, including thirteen
successful baseline/recovery sessions and twelve exhausted sessions. The
compiler-absence sentinel runs last.

| Controlled workload | Observed result |
| --- | --- |
| 64 arithmetic iterations per tick | Six successful host returns; tick seven terminates at exactly 8192 cumulative dispatches |
| Instance/static constructors, start, tick | Terminate at 8192; constructor cases never reach start or create an entity |
| Broad catch followed by resume | Neither catch nor resume marker runs; three further bad/good pairs recover |
| Finally calls private finite helper | Cleanup completes using 480 of its 4096 reserve; checksum 131194896 |
| Finally calls private infinite helper | Cleanup stops at exactly 4096; phase 2, zero reserve left |
| Stop callback loops | Two ticks complete; stop terminates at the cumulative 8192 boundary |
| Fresh source package after every failure | Static starts reset to one, two ticks complete, stop runs, resources release |

Every receipt checks policy version 1, execution and cleanup conservation,
completed ticks against successful host returns, expected logs, and release of
all entities. All twenty-five contexts collect after callbacks return while
their stopped session objects remain retained. Diagnostic forced GC is used
only for this collection observation. It is not a per-frame host policy.

## Reproduce

Build the solution with the private official RC1 SDK, then generate a fresh
fixture directory using the operator tool:

```powershell
dotnet build RuneCLR.slnx -c Release
dotnet run --project tools/RuneCLR.PackageFixtures -c Release --no-build -- --framework-refs tools/RuneCLR.PackageFixtures/bin/Release/net11.0/refs --contract src/RuneCLR.Abstractions/bin/Release/net11.0/RuneCLR.Abstractions.dll --output artifacts/packages/native-budget-new --include-pumped --include-budget
```

The ordinary SDK cannot execute these loops with native terminal enforcement.
Run the player using a matching private layout, or use the bounded controller:

```powershell
py -3 eng/verify-controlled-package-budget.py --output <NEW-evidence-directory> --fixtures artifacts/packages/native-budget-new --layout <private-dotnet-layout> --runtime <separate-runtime-checkout> --build-evidence <matching-Release-build-evidence> --dotnet <ordinary-RC1-dotnet.exe> --candidate-commit 20405f7ae23e183e038703aa5e356b3310fef427
```

The controller freezes/checks exact native, CoreLib, compiler, build, and source
provenance. It runs stock synchronous 15/15, stock pumped 22/22, required pumped
22/22, and required native-budget 33/33. Its child environment explicitly sets
`InterpMode=0`, `RuneCLRInterpretCollectible=0`, `ReadyToRun=1`, and
`TieredCompilation=1`. Native limits are 8192 execution / 4096 cleanup; finite
baseline/recovery sessions use a one-million execution allowance.

The stock native-mode control exits 2 before author files or collectible
assemblies load. Missing policy/pump options and orphan evidence options also
exit 2. Native evidence is an opt-in fresh directory; each scalar JSON receipt
must match the corresponding stdout receipt. The controller independently
checks all twenty-five receipts against the known author behavior.

## Evidence and limits

Evidence is under `artifacts/controlled-package-budget/`:

- `20261015-acceptance-attempt2/`: final bounded lanes, twenty-five native
  receipts, frozen source and ninety-two unchanged player/fixture/source inputs,
  plus successful before/after Release provenance checks.
- `20261015-receipt-review-attempt1/`: twenty-five actual receipts accepted and
  eleven altered receipt/stdout pairs rejected (ledger, ownership, policy,
  catch, phase, checksum, and retirement changes).
- `20261015-generator-attempt1/`: preserved default nine / pumped twelve
  generation and the initial correctly rejected inherited budget entry.
- `20261015-generator-attempt2/`: eighteen budget / twenty-one combined
  generation, plus duplicate-flag rejection without publication.
- `20261015-full-verify-attempt1/verify.log`: zero build warnings/errors,
  37/37 lifecycle, 84/84 packaging, 15/15 synchronous and 22/22 pumped cases,
  and all six sample contexts collected.

These are functional Windows results with native scalar accounting. They do
not add new method-entry samples, performance measurements, or mobile/physical
device evidence for this controlled-package combination. The separate updated
mobile adapter uses raw diagnostic IL fixtures. Package directories remain
trusted and immutable throughout each session; admission hashes do not close
filesystem races or establish authenticated distribution or a hostile-code
sandbox.
