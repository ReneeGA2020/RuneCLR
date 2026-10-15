#!/usr/bin/env python3
"""Accept only the frozen budget baseline or its exact one-change increment child."""
import hashlib
import re
import subprocess
from pathlib import Path

BASELINE = '099dacd07d8d890822f7422f895337733457ab3c'
UPSTREAM = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
METER = 'src/coreclr/vm/runeclrinstructionmeter.h'
OLD = b'''                previous = InterlockedCompareExchange64(&executed, 0, 0);
                while (true)
                {
                    observed = InterlockedCompareExchange64(&executed, previous + 1, previous);
                    if (observed == previous)
                        return true;
                    previous = observed;
                }'''
NEW = b'''                InterlockedIncrement64(&executed);
                return true;'''


def git(runtime, *arguments):
    return subprocess.check_output(['git', '-C', str(runtime), *arguments])


def validate(runtime, candidate=BASELINE):
    runtime = Path(runtime).resolve()
    if not re.fullmatch('[0-9a-f]{40}', candidate):
        raise RuntimeError('Explicit full lowercase candidate commit required.')
    head = git(runtime, 'rev-parse', 'HEAD').decode().strip()
    branch = git(runtime, 'branch', '--show-current').decode().strip()
    status = git(runtime, 'status', '--porcelain', '--untracked-files=no')
    if head != candidate or not branch or status:
        raise RuntimeError('Candidate must match HEAD on an identified tracked-clean branch.')
    subprocess.run(['git', '-C', str(runtime), 'merge-base', '--is-ancestor', UPSTREAM, head],
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    original = git(runtime, 'show', BASELINE + ':' + METER)
    if original.count(OLD) != 1:
        raise RuntimeError('Frozen baseline increment block is not unique.')
    actual = git(runtime, 'show', head + ':' + METER)
    kind = 'baseline'
    if head != BASELINE:
        parents = git(runtime, 'rev-list', '--parents', '-n', '1', head).decode().split()
        changes = git(runtime, 'diff', '--name-status', BASELINE, head).decode().splitlines()
        old_mode = git(runtime, 'ls-tree', BASELINE, '--', METER).split()[0]
        new_mode = git(runtime, 'ls-tree', head, '--', METER).split()[0]
        if parents != [head, BASELINE] or changes != ['M\t' + METER] or old_mode != new_mode:
            raise RuntimeError('Only a direct single-parent/single-file exact increment child is accepted.')
        if actual != original.replace(OLD, NEW, 1):
            raise RuntimeError('Candidate contains changes beyond the exact terminal increment replacement.')
        kind = 'terminal-increment-child'
    elif actual != original:
        raise RuntimeError('Frozen baseline source mismatch.')
    working = (runtime / METER).read_bytes()
    if working.replace(b'\r\n', b'\n') != actual:
        raise RuntimeError('Actual worktree meter differs from accepted committed bytes.')
    return {'version': 1, 'candidateCommit': head, 'baselineCommit': BASELINE, 'upstreamBase': UPSTREAM,
            'branch': branch, 'trackedClean': True, 'kind': kind, 'meterPath': METER,
            'baselineBlobSha256': hashlib.sha256(original).hexdigest(),
            'candidateBlobSha256': hashlib.sha256(actual).hexdigest(),
            'workingMeterSha256': hashlib.sha256(working).hexdigest(),
            'scope': 'Baseline or exact terminal executed atomic-increment child only; no arbitrary runtime candidate.'}
