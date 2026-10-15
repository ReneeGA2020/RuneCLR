#!/usr/bin/env python3
"""Reconstruct the opt-in derived-ledger child in an isolated source snapshot."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / 'eng/verify-runtime-patch-stack.py'
SUPPORT_SHA = '34c46fd66a9807007ddb0d3154d5271dac0c875db3954f04f02a66da19891015'
CHECKER = ROOT / 'eng/derived-ledger-runtime-candidate.py'
PHASE_PATCH = ROOT / 'eng/runtime-patches/phase-load/0009-terminal-phase-acquire-load.patch'
PHASE_SHA = '9135972d74a95dff08c72dd349bb0fda6f533e0a2885373d71a539f589e6ae87'
PATCH = ROOT / 'eng/runtime-patches/derived-ledger/0010-terminal-derived-ledger.patch'
PATCH_SHA = '6055066b679d90b8475f3da92775d4b2aedc690a95bfbc9932be7a7884fb5c3b'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    runtime, output = args.runtime_repo.resolve(), args.output.resolve()
    if output.exists() or output.is_relative_to(runtime):
        raise ValueError('Fresh output outside runtime required.')
    if sha(SUPPORT) != SUPPORT_SHA or sha(PATCH) != PATCH_SHA or sha(PHASE_PATCH) != PHASE_SHA:
        raise ValueError('Frozen source reconstruction input changed.')
    support, checker = module(SUPPORT, 'phase_stack_support'), module(CHECKER, 'phase_stack_checker')
    proof = checker.validate(runtime)
    patches = sorted((ROOT / 'eng/runtime-patches').glob('*.patch'))
    if len(patches) != 8 or [p.name[:4] for p in patches] != [f'{i:04}' for i in range(1, 9)]:
        raise ValueError('Original eight patches required unchanged as an inventory.')
    patches.extend([PHASE_PATCH, PATCH])
    input_hashes = {str(p): sha(p) for p in patches + [SUPPORT, CHECKER, Path(__file__)]}
    output.mkdir(parents=True)
    receipts = []
    try:
        frozen = output / 'patches'
        frozen.mkdir()
        for path in patches:
            shutil.copyfile(path, frozen / path.name)
        paths = set().union(*(support.patch_paths(p) for p in patches))
        desktop_paths = set().union(*(support.patch_paths(p) for p in patches[2:]))
        changes = set(support.git(runtime, 'diff', '--name-only', checker.UPSTREAM, checker.COMMIT).stdout.decode().splitlines())
        if changes != desktop_paths or support.patch_paths(PATCH) != {checker.METER, checker.CONFIG}:
            raise ValueError('Exact candidate source and two-file child coverage required.')
        base = support.snapshot(runtime, checker.UPSTREAM, paths, output / 'desktop')
        support.save(output / 'request.json', {'candidateValidation': proof, 'baseSourceHashes': base,
                     'inputHashes': input_hashes, 'runtime': str(runtime), 'sourceOnly': True})
        for path in patches[2:]:
            support.apply(output / 'desktop', frozen / path.name, receipts)
        hashes = {}
        for relative in sorted(desktop_paths):
            file = output / 'desktop' / relative
            if file.read_bytes() != support.git(runtime, 'show', checker.COMMIT + ':' + relative).stdout:
                raise ValueError('Candidate source reconstruction differs: ' + relative)
            hashes[relative] = sha(file)
        shutil.copytree(output / 'desktop', output / 'with-upstream-fixes', ignore=shutil.ignore_patterns('.git'))
        support.git(output / 'with-upstream-fixes', 'init', '--quiet')
        for path in patches[:2]:
            support.apply(output / 'with-upstream-fixes', frozen / path.name, receipts)
        if checker.validate(runtime) != proof or any(sha(Path(p)) != value for p, value in input_hashes.items()):
            raise ValueError('Reconstruction inputs changed during verification.')
        for path in (Path(__file__), SUPPORT, CHECKER):
            shutil.copyfile(path, output / path.name)
        support.save(output / 'results.json', {'passed': True, 'candidateCommit': checker.COMMIT,
                     'requestSha256': sha(output / 'request.json'), 'desktopChangedFiles': len(hashes),
                     'desktopPatchCount': 8, 'desktopSourceHashes': hashes, 'patches': receipts,
                     'optionalFixesApply': True, 'runtimeTrackedClean': True,
                     'nativeExecutionPerformed': False,
                     'scope': 'Eight desktop patches reconstruct exact committed candidate; two defect fixes apply separately.'})
        print(f'PASS eight desktop patches; {len(hashes)} exact files; two optional fixes; source only.')
    except Exception as error:
        support.save(output / 'failure.json', {'passed': False, 'error': str(error), 'patches': receipts})
        raise


if __name__ == '__main__':
    main()
