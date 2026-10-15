#!/usr/bin/env python3
"""Apply exported patches in isolated source snapshots, without editing runtime."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
CANDIDATE = '099dacd07d8d890822f7422f895337733457ab3c'
CHECKER = ROOT / 'eng/budget-runtime-candidate.py'
_spec = importlib.util.spec_from_file_location('budget_runtime_candidate', CHECKER)
_candidate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_candidate)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def git(repo, *args, check=True):
    return subprocess.run(['git', '-c', 'core.autocrlf=false', '-C', str(repo),
                           *args], capture_output=True, check=check)


def patch_paths(path):
    text = path.read_text(encoding='utf-8')
    pairs = re.findall(r'^diff --git a/(\S+) b/(\S+)$', text, re.M)
    if not pairs or len(pairs) != text.count('diff --git '):
        raise ValueError('Expected textual patches with explicit paths: ' + path.name)
    paths = set()
    for old, new in pairs:
        parts = PurePosixPath(new).parts
        if old != new or not new.startswith('src/') or '..' in parts or '\\' in new or ':' in new:
            raise ValueError('Unsupported patch path: ' + new)
        paths.add(new)
    return paths


def snapshot(repo, revision, paths, destination):
    destination.mkdir()
    git(destination, 'init', '--quiet')
    hashes = {}
    for relative in sorted(paths):
        blob = git(repo, 'show', revision + ':' + relative, check=False)
        if blob.returncode:
            # A later patch can introduce a file absent from the official base.
            if git(repo, 'cat-file', '-e', revision + ':' + relative, check=False).returncode == 0:
                raise RuntimeError('Failed to read existing blob: ' + relative)
            hashes[relative] = None
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob.stdout)
        hashes[relative] = sha(target)
    return hashes


def apply(destination, patch, receipts):
    check = git(destination, 'apply', '--check', str(patch), check=False)
    receipt = {'patch': patch.name, 'sha256': sha(patch), 'checkExit': check.returncode,
               'checkStderr': check.stderr.decode('utf-8', errors='replace')}
    receipts.append(receipt)
    if check.returncode:
        raise RuntimeError('Patch application check failed: ' + patch.name)
    actual = git(destination, 'apply', str(patch), check=False)
    receipt.update({'applyExit': actual.returncode,
                    'applyStderr': actual.stderr.decode('utf-8', errors='replace')})
    if actual.returncode:
        raise RuntimeError('Patch application failed: ' + patch.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--candidate-commit', default=CANDIDATE)
    args = parser.parse_args()
    repo, output = args.runtime_repo.resolve(), args.output.resolve()
    if output.is_relative_to(repo):
        raise ValueError('Evidence must be outside the runtime source checkout.')
    output.mkdir(parents=True, exist_ok=False)
    receipts = []
    try:
        head = git(repo, 'rev-parse', 'HEAD').stdout.decode().strip()
        status = git(repo, 'status', '--porcelain', '--untracked-files=no').stdout
        validation = _candidate.validate(repo, args.candidate_commit)
        candidate = validation['candidateCommit']
        git(repo, 'merge-base', '--is-ancestor', BASE, candidate)
        patches = sorted((ROOT / 'eng/runtime-patches').glob('*.patch'))
        if len(patches) != 8 or [p.name[:4] for p in patches] != [f'{i:04}' for i in range(1, 9)]:
            raise ValueError('Expected the eight numbered exported patches.')
        if candidate == CANDIDATE:
            patches = patches[:7]
        frozen = output / 'patches'
        frozen.mkdir()
        for patch in patches:
            shutil.copyfile(patch, frozen / patch.name)
        patches = [frozen / p.name for p in patches]
        paths = set().union(*(patch_paths(p) for p in patches))
        desktop_paths = set().union(*(patch_paths(p) for p in patches[2:]))
        changes = set(git(repo, 'diff', '--name-only', BASE, candidate).stdout.decode().splitlines())
        if changes != desktop_paths:
            raise ValueError('Desktop patches do not cover exactly the candidate changed files.')
        source_hashes = snapshot(repo, BASE, paths, output / 'desktop')
        request = {'upstreamBase': BASE, 'desktopCandidate': candidate, 'candidateValidation': validation,
                   'runtimeRepository': str(repo), 'runtimeTrackedClean': True,
                   'driverSha256': sha(__file__), 'candidateCheckerSha256': sha(CHECKER), 'baseSourceHashes': source_hashes,
                   'patchHashes': {p.name: sha(p) for p in patches}}
        shutil.copyfile(__file__, output / 'driver.py')
        shutil.copyfile(CHECKER, output / CHECKER.name)
        save(output / 'request.json', request)
        for patch in patches[2:]:
            apply(output / 'desktop', patch, receipts)
        desktop_hashes = {}
        for relative in sorted(desktop_paths):
            actual = (output / 'desktop' / relative).read_bytes()
            expected = git(repo, 'show', candidate + ':' + relative).stdout
            if actual != expected:
                raise ValueError('Reconstructed candidate differs: ' + relative)
            desktop_hashes[relative] = sha(output / 'desktop' / relative)
        # The optional CID/generator patches remain separate from desktop policy.
        shutil.copytree(output / 'desktop', output / 'with-upstream-fixes',
                        ignore=shutil.ignore_patterns('.git'))
        git(output / 'with-upstream-fixes', 'init', '--quiet')
        for patch in patches[:2]:
            apply(output / 'with-upstream-fixes', patch, receipts)
        if (git(repo, 'rev-parse', 'HEAD').stdout.decode().strip() != head or
                git(repo, 'status', '--porcelain', '--untracked-files=no').stdout != status):
            raise ValueError('Runtime source changed during source verification.')
        if _candidate.validate(repo, candidate) != validation or sha(CHECKER) != request['candidateCheckerSha256']:
            raise ValueError('Candidate source checker changed during verification.')
        for patch in patches:
            if sha(ROOT / 'eng/runtime-patches' / patch.name) != request['patchHashes'][patch.name]:
                raise ValueError('Exported patch changed during verification.')
        save(output / 'results.json', {'passed': True, 'requestSha256': sha(output / 'request.json'),
             'desktopCandidateByteIdentical': True, 'desktopChangedFiles': len(desktop_hashes),
             'desktopPatchCount': len(patches) - 2,
             'desktopSourceHashes': desktop_hashes, 'patches': receipts,
             'optionalFixSourceHashes': {p: sha(output / 'with-upstream-fixes' / p)
                                        for p in sorted(paths)},
             'optionalFixesApply': True, 'nativeExecutionPerformed': False,
             'scope': 'Source reconstruction and optional-fix application only; no mobile build or execution proof'})
        print(f'PASS: {len(patches) - 2} desktop patches reconstruct {len(desktop_hashes)} exact candidate files; '
              'CID and generator patches apply separately; runtime checkout unchanged.')
    except Exception as error:
        save(output / 'failure.json', {'passed': False, 'error': str(error), 'patches': receipts})
        raise


if __name__ == '__main__':
    main()
