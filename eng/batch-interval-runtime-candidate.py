#!/usr/bin/env python3
"""Freeze the exact experimental batch child; this proves source identity only."""
import hashlib
from pathlib import Path
import subprocess

COMMIT = 'd0da7dfafc0c4894ae7aa5332ee171f023a0a88e'
BASELINE = '29ff781e157be82ba5a398a60bb05291e4a865af'
UPSTREAM = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
TREE = 'adb0be61097c9514a2d4a817d93125666ed7c03e'
BRANCH = 'runeclr/batch-interval'
CONFIG = 'src/coreclr/inc/clrconfigvalues.h'
INTERPRETER = 'src/coreclr/vm/interpexec.cpp'
STATE = 'src/coreclr/vm/runeclrbatchstate.h'
METER = 'src/coreclr/vm/runeclrinstructionmeter.h'
CANDIDATE_HASHES = {
    CONFIG: 'a4b6aaa798c8ff20a17a52130314aa8b3447d469179fd1498973094e1e668405',
    INTERPRETER: 'a624682569458053ebe0e4e2469e92eff840b30716b115727505715900faa557',
    STATE: '194b97da0d517dd866918acdd29f35709a2739faae35d22d391354a53f3bd52e',
    METER: 'aeca0411b5db0b425a198deb895540e25e714351f5f578fbb9eb73ce2b2a8fa3',
}
MUTANTS = {
    'default_on': (CONFIG, b'BatchInterval"), 0,', b'BatchInterval"), 100,'),
    'mutable_interval': (METER, b'const UINT32 m_batchInterval;', b'UINT32 m_batchInterval;'),
    'unsupported_interval': (METER, b'value == 1 || value == 100 || value == 1000', b'value == 1 || value == 99 || value == 1000'),
    'derived_overshoot_hidden': (METER, b'if (m_derivedLedger && m_batchInterval == 0)', b'if (m_derivedLedger)'),
    'mixed_exact_overflow': (METER, b'AddSaturating(executed, 1);', b'InterlockedIncrement64(&executed);'),
    'cleanup_changed': (METER, b'TryConsume(m_cleanupRemaining, m_cleanupExecuted, m_derivedLedger)', b'TryConsume(m_remaining, m_executed, m_derivedLedger)'),
    'batch_flush_missing': (STATE, b'm_meter->RecordBatch(m_pending);', b'/* lost debt */'),
    'destructor_flush_missing': (STATE, b'~RuneCLRBatchState() { Flush(); }', b'~RuneCLRBatchState() {}'),
    'owner_check_missing': (STATE, b'm_meter != meter ||', b'false ||'),
    'frame_check_missing': (STATE, b'm_frame != frame ||', b'false ||'),
    'start_check_missing': (STATE, b'm_start != start ||', b'false ||'),
    'cadence_changed': (STATE, b'm_pending == meter->BatchInterval()', b'm_pending == 1'),
    'trap_race_flush_missing': (INTERPRETER, b'// The trap can become set after dispatch classified this opcode.\n                        runeclrBatch.Flush();', b'// lost trap flush'),
    'cleanup_batched': (INTERPRETER, b'threadContext->runeclrCleanupOwner != meter', b'true'),
    'dangerous_division_batched': (INTERPRETER, b'case INTOP_CONV_I8_I4:', b'case INTOP_DIV_I4: case INTOP_CONV_I8_I4:'),
}


def git(runtime, *args):
    return subprocess.check_output(['git', '-C', str(runtime), *args])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_blobs(blobs):
    if set(blobs) != set(CANDIDATE_HASHES) or any(sha(blobs[n]) != h for n, h in CANDIDATE_HASHES.items()):
        raise RuntimeError('Exact four-file batch interval source required.')
    return {name: sha(blob) for name, blob in blobs.items()}


def validate(runtime, candidate=COMMIT):
    runtime = Path(runtime).resolve()
    head = git(runtime, 'rev-parse', 'HEAD').decode().strip()
    branch = git(runtime, 'branch', '--show-current').decode().strip()
    tree = git(runtime, 'rev-parse', 'HEAD^{tree}').decode().strip()
    if candidate != COMMIT or head != COMMIT or branch != BRANCH or tree != TREE:
        raise RuntimeError('Exact pinned batch interval commit/tree/branch required.')
    if git(runtime, 'status', '--porcelain', '--untracked-files=no'):
        raise RuntimeError('Tracked-clean batch candidate required.')
    if git(runtime, 'rev-list', '--parents', '-n', '1', head).decode().split() != [COMMIT, BASELINE]:
        raise RuntimeError('Exact direct derived-ledger parent required.')
    changes = git(runtime, 'diff', '--name-status', BASELINE, head).decode().splitlines()
    expected = [('A' if name == STATE else 'M') + '\t' + name for name in sorted(CANDIDATE_HASHES)]
    if changes != expected:
        raise RuntimeError('Only exact four batch files accepted.')
    subprocess.run(['git', '-C', str(runtime), 'merge-base', '--is-ancestor', UPSTREAM, head], check=True)
    blobs = {name: git(runtime, 'show', head + ':' + name) for name in CANDIDATE_HASHES}
    validate_blobs(blobs)
    working = {}
    for name, blob in blobs.items():
        if git(runtime, 'ls-tree', head, '--', name).split()[0] != b'100644':
            raise RuntimeError('Source file mode differs: ' + name)
        actual = (runtime / name).read_bytes()
        if actual.replace(b'\r\n', b'\n') != blob:
            raise RuntimeError('Actual worktree differs: ' + name)
        working[name] = sha(actual)
    return {'version': 1, 'candidateCommit': head, 'baselineCommit': BASELINE, 'upstreamBase': UPSTREAM,
            'candidateTree': tree, 'branch': branch, 'trackedClean': True, 'kind': 'experimental-post-admission-batch-child',
            'candidateSourceHashes': dict(CANDIDATE_HASHES), 'workingSourceHashes': working,
            'batchIntervalSwitch': 'RuneCLRBatchInterval', 'batchIntervalDefault': 0, 'supportedIntervals': [1, 100, 1000],
            'batchIntervalEnvironmentRadix': 16, 'batchIntervalEnvironmentValues': {'1': '1', '100': '64', '1000': '3e8'},
            'meterSize': 72, 'meterAlignment': 8, 'batchIntervalOffset': 64,
            'cleanupAlwaysExact': True, 'singleActiveWorkerOvershootBound': 'interval - 1',
            'multipleWorkersNotCoveredBySingleWorkerBound': True, 'actualAdmittedCounterSaturates': True,
            'scope': 'Exact source acceptance only; not CLR execution, EH, safety, timing or device evidence.'}
