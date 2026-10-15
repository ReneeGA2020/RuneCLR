#!/usr/bin/env python3
"""Read-only baseline anchors and interval-debt algebra, not runtime evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

COMMIT = '29ff781e157be82ba5a398a60bb05291e4a865af'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert subprocess.check_output(['git', '-C', str(a.runtime), 'rev-parse', 'HEAD'], text=True).strip() == COMMIT
    assert not subprocess.check_output(['git', '-C', str(a.runtime), 'status', '--porcelain', '--untracked-files=no'], text=True).strip()
    names = ['src/coreclr/vm/interpexec.cpp', 'src/coreclr/vm/interpexec.h',
             'src/coreclr/vm/eetwain.cpp', 'src/coreclr/vm/exceptionhandling.cpp',
             'src/coreclr/vm/runeclrinstructionmeter.h', 'src/coreclr/interpreter/compiler.cpp']
    files = {n: (a.runtime / n).read_bytes() for n in names}
    text = files[names[0]].decode('utf-8')
    anchors = ['RuneCLRChargeCurrentInstruction', 'RUNECLR_CHARGE_DISPATCH',
               'UpdateFrameForTailCall', 'CALL_INTERP_METHOD:', 'INTOP_CASE(INTOP_SAFEPOINT)',
               'if (g_TrapReturningThreads)', 'HandleThreadAbort',
               'catch (const ResumeAfterCatchException& ex)', 'RUNECLR_ABANDON_CLEANUP:',
               'EXIT_FRAME:', 'RETHROW_RESUME_AFTER_CATCH:']
    locations = {}
    for anchor in anchors:
        assert anchor in text
        locations[anchor] = [i for i, line in enumerate(text.splitlines(), 1) if anchor in line]
    assert 'Backwards branch, emit safepoint' in files[names[-1]].decode('utf-8')
    assert 'runeclrCleanupOwner = previous' in files[names[2]].decode('utf-8')
    checks = 0
    examples = []
    for interval in (1, 100, 1000):
        limits = sorted(set(range(1, 31)) | {interval, interval + 1, 2 * interval - 1,
                                          2 * interval, 3 * interval + 7, 2**63 - 1})
        for allowance in limits:
            admitted = ((allowance + interval - 1) // interval) * interval
            overshoot = admitted - allowance
            assert 0 <= overshoot < interval
            checks += 1
        examples.append(dict(interval=interval, singleThreadMaxOvershoot=interval - 1,
                             exactLimit=1, admittedAtFirstFullFlush=interval,
                             overrunAtFirstFullFlush=interval - 1))
        for workers in (2, 3, 4):
            # With read-only start checks, all workers can see allowance1.
            admitted = workers * interval
            overshoot = admitted - 1
            assert overshoot == workers * interval - 1
            assert overshoot > workers * (interval - 1)
            checks += 1
        for partial in range(interval):
            # Owner/callback/return boundaries must publish each partial debt.
            total_before = partial
            parent_pending_after_flush = 0
            child_pending = interval
            assert total_before + parent_pending_after_flush + child_pending == partial + interval
            assert parent_pending_after_flush == 0
            checks += 2
    result = dict(schema='runeclr.check-interval.boundary-model.v1', success=True,
                  sourceCommit=COMMIT, sourceTrackedClean=True,
                  sourceHashes={n: hashlib.sha256(d).hexdigest() for n, d in files.items()},
                  baselineAnchors=locations, algebraChecks=checks, intervals=examples,
                  singleThreadAssumptions=['One pending debt holder per executing author thread',
                                          'Flush before every potential call, throw, frame change, return or owner transition',
                                          'No-trap safepoint only; trapped handler flushes before GC/abort',
                                          'Cleanup uses original exact per-opcode admission'],
                  concurrentReadOnlyStartBound='M*N-1 at allowance1; N-1 is not a global bound',
                  snapshots='Pending debt is invisible until flush; count actual admitted excess independently of clamped remaining',
                  productionKernelCadence='Old NoInlining Update call must flush each iteration; use separate direct-arithmetic kernel',
                  sourceOnly=True, candidateImplemented=False, targetExecutionVerified=False, performanceMeasured=False,
                  scope='Source anchors and finite algebra only; no native build, runtime execution or timing')
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / 'results.json').write_text(json.dumps(result, indent=2) + chr(10))
    print(json.dumps(dict(success=True, algebraChecks=checks, intervals=examples,
                         sourceOnly=True, targetExecutionVerified=False, performanceMeasured=False)))


if __name__ == '__main__':
    main()
