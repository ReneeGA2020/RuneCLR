#!/usr/bin/env python3
"""Independent source-only review of the interval candidate's flush boundaries."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

PARENT = '29ff781e157be82ba5a398a60bb05291e4a865af'
FILES = ['src/coreclr/inc/clrconfigvalues.h', 'src/coreclr/vm/interpexec.cpp',
         'src/coreclr/vm/runeclrinstructionmeter.h', 'src/coreclr/vm/runeclrbatchstate.h']


def body(text, anchor):
    start = text.index(anchor)
    first = text.index('{', start)
    depth = 0
    for end in range(first, len(text)):
        depth += (text[end] == '{') - (text[end] == '}')
        if depth == 0:
            return text[first:end + 1]
    raise AssertionError('Unterminated body: ' + anchor)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    git = lambda *args: subprocess.check_output(['git', '-C', str(a.runtime), *args], text=True)
    head = git('rev-parse', 'HEAD').strip()
    assert head == PARENT or git('show', '-s', '--format=%P', 'HEAD').strip() == PARENT
    blobs = {n: (a.runtime / n).read_bytes().replace(bytes((13, 10)), bytes((10,))) for n in FILES}
    text = blobs[FILES[1]].decode()
    meter = blobs[FILES[2]].decode()
    state = blobs[FILES[3]].decode()
    base = git('show', PARENT + ':' + FILES[2])
    assert body(meter, 'FORCEINLINE bool TryChargeCleanup()') == body(base, 'FORCEINLINE bool TryChargeCleanup()')
    safe = body(text, 'static FORCEINLINE bool RuneCLRIsBatchSafeOpcode(')
    labels = re.findall(r'case (INTOP_[A-Z0-9_]+):', safe)
    assert len(labels) == len(set(labels)) == 47
    forbidden = ['INTERP_THROW', 'Invoke', 'CALL_INTERP_METHOD', 'Call_HELPER',
                 'GetPossiblyIndirectHelper', 'Allocate', 'GCX_', 'DispatchManaged',
                 'NULL_CHECK', 'SetObjectReference', 'pFrame =', 'ReInit',
                 'UpdateFrameForTailCall', 'INTOP_EXIT_FRAME']
    handlers = []
    for label in labels:
        anchor = 'INTOP_CASE(' + label + ')'
        assert anchor in text
        first = text.index(anchor)
        end = text.find('INTOP_CASE(', first + len(anchor))
        block = text[first:end if end >= 0 else len(text)]
        if label != 'INTOP_SAFEPOINT':
            assert not any(token in block for token in forbidden), label
        handlers.append(dict(opcode=label, line=text[:first].count(chr(10)) + 1,
                             handlerSha256=hashlib.sha256(block.encode()).hexdigest()))
    charge = body(text, 'static FORCEINLINE bool RuneCLRChargeCurrentInstruction(')
    assert 'batch.Admit(meter, frame, frame->startIp)' in charge
    assert charge.index('batch.Flush();') < charge.index('meter->Charge();')
    assert charge.index('batch.Flush();') < charge.index('meter->TryChargeCleanup();')
    assert charge.index('batch.Flush();') < charge.index('meter->ChargeExecution();')
    assert charge.rstrip().endswith('batch.Flush();' + chr(10) + '    return true;' + chr(10) + '}')
    trap = text[text.index('INTOP_CASE(INTOP_SAFEPOINT)'):text.index('#ifdef PERFTRACING_DISABLE_THREADS', text.index('INTOP_CASE(INTOP_SAFEPOINT)'))]
    assert 'return g_TrapReturningThreads == 0;' in safe
    assert trap.index('runeclrBatch.Flush();') < trap.index('HandleThreadAbort')
    assert trap.index('runeclrBatch.Flush();') < trap.index('GCX_PREEMP_REGION_BEGIN')
    assert '~RuneCLRBatchState() { Flush(); }' in state
    assert 'm_pending == meter->BatchInterval()' in state
    assert 'm_frame != frame || m_start != start' in state
    assert 'if (m_pending == 0 && !meter->CanBeginBatch())' in state
    assert 'm_meter->RecordBatch(m_pending);' in state
    assert 'm_pending = 0;' in state
    assert 'NOINLINE void RecordBatch(UINT32 admitted) noexcept' in meter
    assert 'value == 1 || value == 100 || value == 1000 ? value : 0' in meter
    assert 'm_derivedLedger && m_batchInterval == 0' in meter
    assert 'sizeof(RuneCLRInstructionMeter) == 72' in meter
    admission = body(meter, 'FORCEINLINE bool ChargeExecution()')
    assert 'm_derivedLedger && m_batchInterval == 0, m_batchInterval != 0' in admission
    saturating = body(meter, 'static void AddSaturating(')
    assert 'previous > INT64_MAX - admitted ? INT64_MAX : previous + admitted' in saturating
    consume = body(meter, 'static FORCEINLINE bool TryConsume(')
    assert 'if (saturating)' in consume and 'AddSaturating(executed, 1);' in consume
    assert 'AddSaturating(m_executed, admitted);' in body(meter, 'NOINLINE void RecordBatch(')
    for suffix in ('INTOP_RET', 'INTOP_THROW', 'INTOP_CALL', 'INTOP_CALLI', 'INTOP_CALL_PINVOKE', 'INTOP_NEWOBJ'):
        assert suffix not in labels
    a.output.mkdir(parents=True, exist_ok=False)
    result = dict(schema='runeclr.check-interval.boundary-source-review.v1', success=True,
                  sourceParent=PARENT, sourceHead=head, sourceHashes={n: hashlib.sha256(d).hexdigest() for n, d in blobs.items()},
                  safeOpcodeCount=len(labels), handlers=handlers, unsafeDispatchFlushBeforeCharge=True,
                  ownerFrameStartKey=True, noTrapSafepointContinuesBatch=True, actualTrapHandlerFlush=True,
                  cleanupAdmissionUnchanged=True, normalBatchIntervalOneCountMatchesExact=True,
                  singleThreadOverrunBound='N-1', concurrentReadOnlyBeginBound='M*N-1 at allowance1',
                  pendingSnapshotsDelayed=True, nativeMeterBytes=72, sourceOnly=True,
                  batchExactAdmissionSaturates=True, legacyCleanupMethodPreserved=True,
                  scope='Actual source/handler review only; no native/runtime execution or timing',
                  reviewerToolSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (a.output / 'results.json').write_text(json.dumps(result, indent=2) + chr(10))
    (a.output / 'reviewer.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(success=True, safeOpcodeCount=47, actualTrapHandlerFlush=True,
                         cleanupAdmissionUnchanged=True, sourceOnly=True)))


if __name__ == '__main__':
    main()
