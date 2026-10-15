#!/usr/bin/env python3
"""Accept only the exact opt-in derived-ledger direct child; existing guards stay unchanged."""
import hashlib
from pathlib import Path
import subprocess

COMMIT = '29ff781e157be82ba5a398a60bb05291e4a865af'
BASELINE = 'a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186'
UPSTREAM = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
TREE = '685cb628b9cd5432e5589f8b0b6554b300915e76'
BRANCH = 'runeclr/terminal-derived-ledger'
METER = 'src/coreclr/vm/runeclrinstructionmeter.h'
CONFIG = 'src/coreclr/inc/clrconfigvalues.h'
BASE_HASHES = {
    METER: '5e92cda199ab92f46ea5032b06bf4948b8247d4dec19ea59d1bd7ae987faf5b9',
    CONFIG: '785c16504db347cb16c204200e714bc4afaf0e4880149f7e02d40fc8cf4aed59',
}
CANDIDATE_HASHES = {
    METER: 'd091244e5530ab54124ce07c90af00e54378623cd3cbd80d1ef6db6f8ec831f2',
    CONFIG: 'b7a16eb1d08827293ed21e77fb113fb77e3a03669e7c68d7670d12cc6cc38b5b',
}
MUTANTS = {
    'default_on': (CONFIG, b'DerivedLedger"), 0,', b'DerivedLedger"), 1,'),
    'mutable_flag': (METER, b'const bool m_derivedLedger;', b'bool m_derivedLedger;'),
    'legacy_meter_opted_in': (METER,
        b'm_derivedLedger(terminalPrototype && CLRConfig::GetConfigValue(CLRConfig::EXTERNAL_RuneCLRDerivedLedger) != 0)',
        b'm_derivedLedger(CLRConfig::GetConfigValue(CLRConfig::EXTERNAL_RuneCLRDerivedLedger) != 0)'),
    'phase_switch_coupled': (METER, b'return m_phaseAcquireLoad ? VolatileLoad(&m_phase)',
                            b'return m_derivedLedger ? VolatileLoad(&m_phase)'),
    'execution_allowance_changed': (METER, b'm_initialExecutionLimit(limit)', b'm_initialExecutionLimit(limit + 1)'),
    'cleanup_allowance_changed': (METER, b'm_initialCleanupLimit(cleanupLimit)', b'm_initialCleanupLimit(cleanupLimit + 1)'),
    'execution_derived_from_wrong_budget': (METER, b'return m_initialExecutionLimit - Remaining();',
                                           b'return m_initialExecutionLimit - CleanupRemaining();'),
    'cleanup_derived_from_wrong_budget': (METER, b'return m_initialCleanupLimit - CleanupRemaining();',
                                         b'return m_initialCleanupLimit - Remaining();'),
    'increment_condition_reversed': (METER, b'if (!derivedLedger)', b'if (derivedLedger)'),
    'remaining_admission_changed': (METER,
        b'LONGLONG observed = InterlockedCompareExchange64(&remaining, previous - 1, previous);',
        b'LONGLONG observed = InterlockedCompareExchange64(&remaining, previous - 2, previous);'),
    'execution_phase_writer_changed': (METER, b'InterlockedCompareExchange(&m_phase, 1, 0);',
                                       b'InterlockedCompareExchange(&m_phase, 2, 0);'),
    'cleanup_phase_writer_changed': (METER, b'InterlockedCompareExchange(&m_phase, 2, 1);',
                                     b'InterlockedCompareExchange(&m_phase, 1, 2);'),
    'legacy_charge_changed': (METER,
        b'InterlockedCompareExchange64(&m_executed, previous + 1, previous);',
        b'InterlockedCompareExchange64(&m_executed, previous + 2, previous);'),
    'immutable_allowance_removed': (METER, b'alignas(8) const INT64 m_initialExecutionLimit;',
                                    b'alignas(8) INT64 m_initialExecutionLimit;'),
    'field_size_contract_changed': (METER, b'static_assert(sizeof(RuneCLRInstructionMeter) == 64);',
                                    b'static_assert(sizeof(RuneCLRInstructionMeter) == 56);'),
}


def git(runtime, *args):
    return subprocess.check_output(['git', '-C', str(runtime), *args])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_blobs(blobs, expected=CANDIDATE_HASHES):
    if set(blobs) != set(expected):
        raise RuntimeError('Exact derived-ledger two-file source inventory required.')
    if any(sha(blobs[name]) != value for name, value in expected.items()):
        raise RuntimeError('Derived-ledger source differs from frozen exact bytes.')
    return {name: sha(blob) for name, blob in blobs.items()}


def validate(runtime, candidate=COMMIT):
    runtime = Path(runtime).resolve()
    if candidate != COMMIT:
        raise RuntimeError('Only the pinned derived-ledger direct child is accepted.')
    head = git(runtime, 'rev-parse', 'HEAD').decode().strip()
    branch = git(runtime, 'branch', '--show-current').decode().strip()
    status = git(runtime, 'status', '--porcelain', '--untracked-files=no')
    if head != candidate or branch != BRANCH or status:
        raise RuntimeError('Candidate must match HEAD on the exact tracked-clean derived-ledger branch.')
    parents = git(runtime, 'rev-list', '--parents', '-n', '1', head).decode().split()
    tree = git(runtime, 'rev-parse', head + '^{tree}').decode().strip()
    changes = git(runtime, 'diff', '--name-status', BASELINE, head).decode().splitlines()
    expected_changes = ['M' + chr(9) + name for name in sorted(CANDIDATE_HASHES)]
    if parents != [head, BASELINE] or tree != TREE or changes != expected_changes:
        raise RuntimeError('Exact direct-parent two-file derived-ledger tree/change required.')
    subprocess.run(['git', '-C', str(runtime), 'merge-base', '--is-ancestor', UPSTREAM, head],
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    baseline_blobs = {name: git(runtime, 'show', BASELINE + ':' + name) for name in BASE_HASHES}
    blobs = {name: git(runtime, 'show', head + ':' + name) for name in CANDIDATE_HASHES}
    validate_blobs(baseline_blobs, BASE_HASHES); validate_blobs(blobs)
    working_hashes = {}
    for name, blob in blobs.items():
        if any(git(runtime, 'ls-tree', revision, '--', name).split()[0] != b'100644' for revision in (BASELINE, head)):
            raise RuntimeError('Exact source file mode differs: ' + name)
        working = (runtime / name).read_bytes()
        if working.replace(bytes([13, 10]), bytes([10])) != blob:
            raise RuntimeError('Actual worktree source differs from committed bytes: ' + name)
        working_hashes[name] = sha(working)
    return {'version': 1, 'candidateCommit': head, 'baselineCommit': BASELINE, 'upstreamBase': UPSTREAM,
            'branch': branch, 'trackedClean': True, 'kind': 'terminal-derived-ledger-child',
            'candidateTree': tree, 'meterPath': METER, 'configPath': CONFIG,
            'baselineBlobSha256': BASE_HASHES[METER], 'candidateBlobSha256': CANDIDATE_HASHES[METER],
            'workingMeterSha256': working_hashes[METER], 'baselineSourceHashes': dict(BASE_HASHES),
            'candidateSourceHashes': dict(CANDIDATE_HASHES), 'workingSourceHashes': working_hashes,
            'derivedLedgerSwitch': 'RuneCLRDerivedLedger', 'derivedLedgerDefault': 0,
            'derivedLedgerField': 'm_derivedLedger', 'derivedLedgerFieldOffset': 3,
            'derivedLedgerLifetime': 'immutable per terminal meter; constructor-only terminal-gated config lookup',
            'initialAllowanceOffsets': {'execution': 48, 'cleanup': 56}, 'meterSize': 64, 'meterAlignment': 8,
            'phaseAcquireSwitch': 'RuneCLRPhaseAcquireLoad', 'phaseAcquireDefault': 0,
            'phaseAcquireFieldOffset': 2, 'phaseAcquireSwitchIndependent': True,
            'admittedCountSemantics': 'initial allowance minus remaining; admitted dispatches, not completed bodies; separate getters are not transactional',
            'scope': 'Exact source acceptance only; no new-path execution, safety, performance or device proof.'}
