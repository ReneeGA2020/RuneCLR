#!/usr/bin/env python3
"""Accept only the exact opt-in phase-acquire child; old candidate guards stay unchanged."""
import hashlib
import subprocess
from pathlib import Path

COMMIT = 'a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186'
BASELINE = '20405f7ae23e183e038703aa5e356b3310fef427'
UPSTREAM = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
TREE = '574817c21738cb91fe666cd8e210a22d9d677cd5'
METER = 'src/coreclr/vm/runeclrinstructionmeter.h'
CONFIG = 'src/coreclr/inc/clrconfigvalues.h'
BASE_HASHES = {
    METER: '6b3abc45ff0edb3a3697a3d079ef57e8b0f4403e148d197fcbe4efd333f33b34',
    CONFIG: '61ef5366d422381d7981bcc978aca99380bd873b5ccaf44b7192dc37e71c0bae',
}
CANDIDATE_HASHES = {
    METER: '5e92cda199ab92f46ea5032b06bf4948b8247d4dec19ea59d1bd7ae987faf5b9',
    CONFIG: '785c16504db347cb16c204200e714bc4afaf0e4880149f7e02d40fc8cf4aed59',
}

def git(runtime, *args):
    return subprocess.check_output(['git', '-C', str(runtime), *args])

def sha(data):
    return hashlib.sha256(data).hexdigest()

def validate_blobs(blobs, expected=CANDIDATE_HASHES):
    if set(blobs) != set(expected):
        raise RuntimeError('Exact phase-load source inventory required.')
    if any(sha(blobs[name]) != value for name, value in expected.items()):
        raise RuntimeError('Phase-load source differs from frozen exact bytes.')
    return {name: sha(blob) for name, blob in blobs.items()}

def validate(runtime, candidate=COMMIT):
    runtime = Path(runtime).resolve()
    if candidate != COMMIT:
        raise RuntimeError('Only the pinned phase-acquire direct child is accepted.')
    head = git(runtime, 'rev-parse', 'HEAD').decode().strip()
    branch = git(runtime, 'branch', '--show-current').decode().strip()
    status = git(runtime, 'status', '--porcelain', '--untracked-files=no')
    if head != candidate or not branch or status:
        raise RuntimeError('Candidate must match HEAD on an identified tracked-clean branch.')
    parents = git(runtime, 'rev-list', '--parents', '-n', '1', head).decode().split()
    tree = git(runtime, 'rev-parse', head + '^{tree}').decode().strip()
    changes = git(runtime, 'diff', '--name-status', BASELINE, head).decode().splitlines()
    expected_changes = ['M' + chr(9) + name for name in sorted(CANDIDATE_HASHES)]
    if parents != [head, BASELINE] or tree != TREE or changes != expected_changes:
        raise RuntimeError('Exact direct-parent two-file phase-load change required.')
    subprocess.run(['git', '-C', str(runtime), 'merge-base', '--is-ancestor', UPSTREAM, head],
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    baseline_blobs = {name: git(runtime, 'show', BASELINE + ':' + name) for name in BASE_HASHES}
    blobs = {name: git(runtime, 'show', head + ':' + name) for name in CANDIDATE_HASHES}
    validate_blobs(baseline_blobs, BASE_HASHES)
    validate_blobs(blobs)
    working_hashes = {}
    for name, blob in blobs.items():
        if git(runtime, 'ls-tree', BASELINE, '--', name).split()[0] != git(runtime, 'ls-tree', head, '--', name).split()[0]:
            raise RuntimeError('Source mode changed: ' + name)
        working = (runtime / name).read_bytes()
        if working.replace(bytes([13, 10]), bytes([10])) != blob:
            raise RuntimeError('Actual worktree source differs from committed bytes: ' + name)
        working_hashes[name] = sha(working)
    return {'version': 1, 'candidateCommit': head, 'baselineCommit': BASELINE, 'upstreamBase': UPSTREAM,
            'branch': branch, 'trackedClean': True, 'kind': 'phase-acquire-load-child',
            'candidateTree': tree, 'meterPath': METER, 'configPath': CONFIG,
            'baselineBlobSha256': BASE_HASHES[METER], 'candidateBlobSha256': CANDIDATE_HASHES[METER],
            'workingMeterSha256': working_hashes[METER],
            'baselineSourceHashes': dict(BASE_HASHES), 'candidateSourceHashes': dict(CANDIDATE_HASHES),
            'workingSourceHashes': working_hashes,
            'phaseAcquireSwitch': 'RuneCLRPhaseAcquireLoad', 'phaseAcquireDefault': 0,
            'phaseAcquireField': 'm_phaseAcquireLoad', 'phaseAcquireFieldOffset': 2,
            'phaseAcquireLifetime': 'immutable per terminal meter; constructor-only config lookup',
            'scope': 'Exact opt-in acquire phase-load direct child only; source acceptance does not establish execution or performance.'}
