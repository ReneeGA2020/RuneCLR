#!/usr/bin/env python3
"""Reconstruct the exact increment-plus-CID mobile tree using private Git indexes."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
WINDOWS = '20405f7ae23e183e038703aa5e356b3310fef427'
OLD_WINDOWS = '099dacd07d8d890822f7422f895337733457ab3c'
OLD_TREE = 'b54537ff42a066e41a01ea611a21f2e5e49934a1'
METER = 'src/coreclr/vm/runeclrinstructionmeter.h'
CID = 'src/coreclr/vm/virtualcallstub.cpp'
CHECKER = ROOT / 'eng/budget-runtime-candidate.py'
OLD_PROOF = ROOT / 'artifacts/mobile-session-budget/source-review-20261013/source-proof.json'
PATCHES = {
    '0001-collectible-cid-publication.patch': '43b36606fa94967e97f2640e8d76dcfa8f0af21eeb77a065a0eea5c83c915857',
    '0003-collectible-interpreter-selection.patch': 'b7d446243a099c6fc01c19bdc6e83c151eb4771112001fd9bd7185a0d1950ccb',
    '0004-interpreter-required-load-context.patch': '714ba322b3df83ccb3feb5b91043b779e4c75b212ea9d4dbf95db06c0e330657',
    '0005-native-session-instruction-meter.patch': '5ecb5d595aba473c5709d8b172821ae7de228ee7705f140535df3b890ea7ec94',
    '0006-session-terminal-prototype.patch': '3acec56c4fb1946d38ff324d30b5bb7ee8220d1ab66439c5352c031cbb042d76',
    '0007-session-terminal-finalizer-boundary.patch': 'c21c940db0f5041f3e681d4bafafbc555f51412f2c9a188c142981af27c468ef',
    '0008-terminal-counter-increment.patch': 'a1bbecff236c5484a35e9c79643bd5c572e34a0eda8e843904c54bd31d04f108',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def check(value, message):
    if not value:
        raise ValueError(message)


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def git(repo, *args, index=None):
    env = os.environ.copy()
    env.pop('GIT_INDEX_FILE', None)
    if index is not None:
        env['GIT_INDEX_FILE'] = str(Path(index).resolve())
    process = subprocess.run(['git', '-c', 'core.autocrlf=false', '-C', str(repo), *args],
                             env=env, capture_output=True, check=True)
    return process.stdout


def compose(repo, revision, patches, index, receipts):
    check(not index.exists(), 'Fresh private index required.')
    git(repo, 'read-tree', revision, index=index)
    for patch in patches:
        git(repo, 'apply', '--cached', '--check', str(patch), index=index)
        git(repo, 'apply', '--cached', str(patch), index=index)
        receipts.append({'index': index.name, 'patch': patch.name, 'sha256': sha(patch),
                         'checkExit': 0, 'applyExit': 0})
    return git(repo, 'write-tree', index=index).decode().strip()


def validate_patch_hashes(actual):
    check(actual == PATCHES, 'Expected exactly seven frozen CID/policy/budget/increment patches.')


def validate_sources(actual, expected):
    check(set(actual) == set(expected) and len(actual) == 37, 'Exact37 source path set required.')
    for name, data in actual.items():
        check(b'\r\n' not in data and digest(data) == expected[name], 'LF Git blob differs: ' + name)


def rejected(label, action, controls):
    try:
        action()
    except (ValueError, subprocess.CalledProcessError) as error:
        controls.append({'control': label, 'rejected': True, 'reason': str(error)})
    else:
        raise ValueError('Negative control was accepted: ' + label)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo, output = args.runtime_repo.resolve(), args.output.resolve()
    check(not output.is_relative_to(repo), 'Evidence must be outside runtime checkout.')
    output.mkdir(parents=True, exist_ok=False)
    receipts, controls = [], []
    try:
        spec = importlib.util.spec_from_file_location('budget_candidate', CHECKER)
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        validation = checker.validate(repo, WINDOWS)
        native_index = Path(git(repo, 'rev-parse', '--git-path', 'index').decode().strip())
        if not native_index.is_absolute():
            native_index = repo / native_index
        before = {'head': git(repo, 'rev-parse', 'HEAD').decode().strip(),
                  'branch': git(repo, 'branch', '--show-current').decode().strip(),
                  'trackedStatus': git(repo, 'status', '--porcelain', '--untracked-files=no').decode(),
                  'nativeIndexSha256': sha(native_index)}
        frozen = output / 'patches'
        frozen.mkdir()
        for name in PATCHES:
            shutil.copyfile(ROOT / 'eng/runtime-patches' / name, frozen / name)
        actual_patches = {name: sha(frozen / name) for name in PATCHES}
        validate_patch_hashes(actual_patches)
        shutil.copyfile(__file__, output / 'driver.py')
        shutil.copyfile(CHECKER, output / CHECKER.name)
        shutil.copyfile(OLD_PROOF, output / 'old-source-proof.json')
        old = json.loads(OLD_PROOF.read_text(encoding='utf-8-sig'))
        check(old['base'] == BASE and old['windowsCommit'] == OLD_WINDOWS and old['tree'] == OLD_TREE,
              'Original mobile evidence identity differs.')
        check(old['patches'] == {n: h for n, h in PATCHES.items() if not n.startswith('0008')},
              'Original mobile patch hashes differ.')
        old_paths = git(repo, 'diff', '--name-only', BASE, OLD_TREE).decode().splitlines()
        old_blobs = {n: git(repo, 'show', OLD_TREE + ':' + n) for n in old_paths}
        validate_sources(old_blobs, old['sourceHashes'])
        save(output / 'request.json', {'schema': 'runeclr.mobile-increment.source-request.v1',
             'createdUtc': datetime.now(timezone.utc).isoformat(), 'runtimeRepository': str(repo),
             'base': BASE, 'windowsCommit': WINDOWS, 'oldMobileTree': OLD_TREE,
             'patches': actual_patches, 'candidateValidation': validation,
             'driverSha256': sha(__file__), 'candidateCheckerSha256': sha(CHECKER),
             'oldSourceProofSha256': sha(OLD_PROOF), 'originalRuntime': before})
        names = list(PATCHES)
        windows_tree = compose(repo, WINDOWS, [frozen / names[0]], output / 'windows-cid.index', receipts)
        stack_tree = compose(repo, BASE, [frozen / n for n in names], output / 'base-stack.index', receipts)
        old_tree = compose(repo, OLD_TREE, [frozen / names[-1]], output / 'old-mobile-increment.index', receipts)
        check(windows_tree == stack_tree == old_tree, 'Three independent source compositions differ.')
        check(git(repo, 'diff', '--name-status', WINDOWS, windows_tree).decode().splitlines() == ['M\t' + CID],
              'Mobile versus Windows delta must only be CID.')
        check(git(repo, 'diff', '--name-status', OLD_TREE, windows_tree).decode().splitlines() == ['M\t' + METER],
              'New versus old mobile delta must only be increment header.')
        paths = git(repo, 'diff', '--name-only', BASE, windows_tree).decode().splitlines()
        check(set(paths) == set(old_paths), 'Changed37-file set differs from old mobile.')
        blobs = {n: git(repo, 'show', windows_tree + ':' + n) for n in paths}
        check(old_blobs[METER].count(checker.OLD) == 1 and
              blobs[METER] == old_blobs[METER].replace(checker.OLD, checker.NEW, 1),
              'Mobile header is not the unique exact terminal increment replacement.')
        hashes = {n: digest(blobs[n]) for n in paths}
        validate_sources(blobs, hashes)
        for name, data in blobs.items():
            target = output / 'source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (output / 'combined.patch').write_bytes(git(repo, 'diff', '--binary', BASE, windows_tree))
        bad_hashes = dict(actual_patches)
        bad_hashes[names[-1]] = '0' * 64
        rejected('incorrect-patch-hash', lambda: validate_patch_hashes(bad_hashes), controls)
        altered_patch = output / 'altered-increment.patch'
        altered_patch.write_bytes((frozen / names[-1]).read_bytes() + b'\ncorruption-control\n')
        bad_hashes = dict(actual_patches)
        bad_hashes[names[-1]] = sha(altered_patch)
        rejected('altered-patch-bytes', lambda: validate_patch_hashes(bad_hashes), controls)
        bad_blobs = dict(blobs)
        bad_blobs[METER] = blobs[METER].replace(b'InterlockedIncrement64(&executed);', b'InterlockedIncrement64(&remaining);', 1)
        rejected('altered-source-header', lambda: validate_sources(bad_blobs, hashes), controls)
        bad_blobs = dict(blobs)
        bad_blobs.pop(CID)
        rejected('missing-source-file', lambda: validate_sources(bad_blobs, hashes), controls)
        omitted = compose(repo, BASE, [frozen / n for n in names[:-1]], output / 'negative-missing-increment.index', receipts)
        rejected('actual-composition-missing-increment', lambda: check(omitted == windows_tree,
                 'Omitting0008 yields the original mobile tree, not candidate.'), controls)
        check(omitted == OLD_TREE, 'Negative composition unexpectedly differs from original mobile.')
        no_cid = compose(repo, BASE, [frozen / n for n in names[1:]], output / 'negative-missing-cid.index', receipts)
        rejected('actual-composition-missing-cid', lambda: check(no_cid == windows_tree,
                 'OmittingCID yields Windows tree, not mobile.'), controls)
        check(no_cid == git(repo, 'rev-parse', WINDOWS + '^{tree}').decode().strip(),
              'NoCID negative tree unexpectedly differs from Windows.')
        check(checker.validate(repo, WINDOWS) == validation, 'Runtime candidate changed during proof.')
        after = {'head': git(repo, 'rev-parse', 'HEAD').decode().strip(),
                 'branch': git(repo, 'branch', '--show-current').decode().strip(),
                 'trackedStatus': git(repo, 'status', '--porcelain', '--untracked-files=no').decode(),
                 'nativeIndexSha256': sha(native_index)}
        check(after == before, 'Runtime tracked checkout or native index changed.')
        for name, expected in PATCHES.items():
            check(sha(ROOT / 'eng/runtime-patches' / name) == expected, 'Original patch changed during proof.')
        check(sha(__file__) == sha(output / 'driver.py') and sha(CHECKER) == sha(output / CHECKER.name) and
              sha(OLD_PROOF) == sha(output / 'old-source-proof.json'), 'Frozen source tools/evidence changed.')
        proof = {'schema': 'runeclr.mobile-increment.source-proof.v1', 'base': BASE,
                 'windowsCommit': WINDOWS, 'tree': windows_tree, 'patches': actual_patches,
                 'sourceHashes': hashes, 'sourceHashFormat': 'SHA256 of exact Git blob bytes, LF; remote clean worktree must match',
                 'privateIndexCompositionVerified': True, 'windowsDeltaOnlyCID': True,
                 'oldMobileTree': OLD_TREE, 'oldWindowsCommit': OLD_WINDOWS,
                 'oldMobileSourceProofSha256': sha(OLD_PROOF), 'oldMobileDeltaOnlyMeter': True,
                 'exactIncrementVerified': True, 'changedFileCount': len(paths),
                 'compositionTrees': {'windowsPlusCID': windows_tree, 'basePlusSevenPatches': stack_tree,
                                      'oldMobilePlusIncrement': old_tree},
                 'driverSha256': sha(__file__), 'candidateCheckerSha256': sha(CHECKER),
                 'requestSha256': sha(output / 'request.json'), 'combinedPatchSha256': sha(output / 'combined.patch'),
                 'nativeBuildPerformed': False, 'executionVerified': False,
                 'runtimeTrackedCheckoutAndIndexUnchanged': True, 'sharedGitObjectStoreReceivesTrees': True,
                 'negativeControls': controls, 'claim': 'Exact mobile source composition only; no build, entry or device acceptance.'}
        save(output / 'source-proof.json', proof)
        save(output / 'results.json', {'passed': True, 'tree': windows_tree, 'sourceFileCount': len(paths),
             'negativeControlCount': len(controls), 'sourceProofSha256': sha(output / 'source-proof.json'),
             'runtimeBefore': before, 'runtimeAfter': after, 'patchApplications': receipts,
             'nativeBuildPerformed': False, 'executionVerified': False})
        print(json.dumps({'passed': True, 'tree': windows_tree, 'sourceFileCount': len(paths),
                          'negativeControls': len(controls), 'sourceProofSha256': sha(output / 'source-proof.json')}))
    except Exception as error:
        save(output / 'failure.json', {'passed': False, 'error': str(error),
                                      'patchApplications': receipts, 'negativeControls': controls})
        raise


if __name__ == '__main__':
    main()
