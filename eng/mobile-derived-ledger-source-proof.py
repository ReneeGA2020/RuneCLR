#!/usr/bin/env python3
"""Freeze and independently reconstruct the derived-ledger plus CID mobile sources."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
WINDOWS = '29ff781e157be82ba5a398a60bb05291e4a865af'
OLD_TREE = '91673a7980bda79006259e525741fecb04324444'
OLD_WINDOWS = '20405f7ae23e183e038703aa5e356b3310fef427'
METER = 'src/coreclr/vm/runeclrinstructionmeter.h'
CONFIG = 'src/coreclr/inc/clrconfigvalues.h'
CID = 'src/coreclr/vm/virtualcallstub.cpp'
HELPER = ROOT / 'eng/mobile-increment-source-proof.py'
CHECKER = ROOT / 'eng/derived-ledger-runtime-candidate.py'
OLD_PROOF = ROOT / 'artifacts/mobile-budget-increment/source-review-20261014-attempt1/source-proof.json'
PINNED_TOOLS = {
    HELPER: '9e71e5414c222f109e76b702598e5bf9ff48b7d8694e4383e8fee09694540d8d',
    CHECKER: 'd9ab9a5c9bcc78ef6c214864501ed1e930ac3f42d05770033235709dbc612380',
    OLD_PROOF: '6dea87eae1bbbb3142319707c2af4f5cca142a5bc1e4fe8ef665d8a93a2e4d48',
}
EXTRA_PATCHES = {
    'phase-load/0009-terminal-phase-acquire-load.patch': '9135972d74a95dff08c72dd349bb0fda6f533e0a2885373d71a539f589e6ae87',
    'derived-ledger/0010-terminal-derived-ledger.patch': '6055066b679d90b8475f3da92775d4b2aedc690a95bfbc9932be7a7884fb5c3b',
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(helper, repo):
    index = Path(helper.git(repo, 'rev-parse', '--git-path', 'index').decode().strip())
    if not index.is_absolute():
        index = repo / index
    return {'head': helper.git(repo, 'rev-parse', 'HEAD').decode().strip(),
            'branch': helper.git(repo, 'branch', '--show-current').decode().strip(),
            'trackedStatus': helper.git(repo, 'status', '--porcelain', '--untracked-files=no').decode(),
            'nativeIndexSha256': helper.sha(index)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-repo', type=Path, required=True)
    parser.add_argument('--mobile-repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo, mobile, output = args.runtime_repo.resolve(), args.mobile_repo.resolve(), args.output.resolve()
    helper = load('increment_proof_helpers', HELPER)
    check, git, sha, save = helper.check, helper.git, helper.sha, helper.save
    for path, expected in PINNED_TOOLS.items():
        check(sha(path) == expected, 'Pinned tool/evidence changed: ' + str(path))
    checker = load('derived_ledger_candidate', CHECKER)
    patches = dict(helper.PATCHES) | EXTRA_PATCHES
    check(not output.is_relative_to(repo) and not output.is_relative_to(mobile), 'Evidence must be outside runtime checkouts.')
    output.mkdir(parents=True, exist_ok=False)
    receipts, controls = [], []
    try:
        validation = checker.validate(repo, WINDOWS)
        before, mobile_before = snapshot(helper, repo), snapshot(helper, mobile)
        check(not mobile_before['trackedStatus'] and mobile_before['branch'] == 'runeclr/mobile-derived-ledger',
              'Mobile source branch must be tracked clean.')
        source_commit = mobile_before['head']
        check(git(mobile, 'rev-list', '--parents', '-n', '1', source_commit).decode().split() == [source_commit, WINDOWS],
              'Mobile source commit must be a direct Windows candidate child.')
        frozen = output / 'patches'
        frozen.mkdir()
        frozen_paths = {}
        for name, expected in patches.items():
            path = frozen / Path(name).name
            shutil.copyfile(ROOT / 'eng/runtime-patches' / name, path)
            check(sha(path) == expected, 'Patch hash differs: ' + name)
            frozen_paths[name] = path
        for path in PINNED_TOOLS:
            target_name = 'old-source-proof.json' if path == OLD_PROOF else path.name
            shutil.copyfile(path, output / target_name)
        shutil.copyfile(__file__, output / 'driver.py')
        old = json.loads(OLD_PROOF.read_text(encoding='utf-8-sig'))
        check(old['base'] == BASE and old['windowsCommit'] == OLD_WINDOWS and old['tree'] == OLD_TREE and
              old['patches'] == helper.PATCHES, 'Old mobile increment evidence identity differs.')
        old_paths = git(repo, 'diff', '--name-only', BASE, OLD_TREE).decode().splitlines()
        old_blobs = {n: git(repo, 'show', OLD_TREE + ':' + n) for n in old_paths}
        helper.validate_sources(old_blobs, old['sourceHashes'])
        save(output / 'request.json', {'schema': 'runeclr.mobile-derived-ledger.source-request.v1',
             'createdUtc': datetime.now(timezone.utc).isoformat(), 'base': BASE, 'windowsCommit': WINDOWS,
             'sourceCommit': source_commit, 'oldMobileTree': OLD_TREE, 'patches': patches,
             'candidateValidation': validation, 'originalRuntime': before, 'originalMobile': mobile_before,
             'driverSha256': sha(__file__), 'candidateCheckerSha256': sha(CHECKER),
             'helperSha256': sha(HELPER), 'oldSourceProofSha256': sha(OLD_PROOF)})
        names = list(patches)
        windows_tree = helper.compose(repo, WINDOWS, [frozen_paths[names[0]]], output / 'windows-cid.index', receipts)
        stack_tree = helper.compose(repo, BASE, [frozen_paths[n] for n in names], output / 'base-stack.index', receipts)
        old_tree = helper.compose(repo, OLD_TREE, [frozen_paths[n] for n in EXTRA_PATCHES], output / 'old-mobile-derived.index', receipts)
        check(windows_tree == stack_tree == old_tree, 'Three independent source compositions differ.')
        check(git(mobile, 'rev-parse', source_commit + '^{tree}').decode().strip() == windows_tree,
              'Mobile clean commit differs from independent compositions.')
        check(git(repo, 'diff', '--name-status', WINDOWS, windows_tree).decode().splitlines() == ['M\t' + CID],
              'Mobile versus Windows delta must only be CID.')
        check(git(repo, 'diff', '--name-status', OLD_TREE, windows_tree).decode().splitlines() ==
              ['M\t' + n for n in sorted([METER, CONFIG])], 'Old mobile delta must only be meter and config.')
        paths = git(repo, 'diff', '--name-only', BASE, windows_tree).decode().splitlines()
        check(set(paths) == set(old_paths), 'Changed37-file set differs from old mobile.')
        blobs = {n: git(repo, 'show', windows_tree + ':' + n) for n in paths}
        hashes = {n: helper.digest(blobs[n]) for n in paths}
        helper.validate_sources(blobs, hashes)
        check({n: hashes[n] for n in checker.CANDIDATE_HASHES} == checker.CANDIDATE_HASHES,
              'Meter/config differ from exact Windows derived ledger.')
        for name, data in blobs.items():
            check((mobile / name).read_bytes() == data, 'Actual clean mobile LF bytes differ: ' + name)
            target = output / 'source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (output / 'combined.patch').write_bytes(git(repo, 'diff', '--binary', BASE, windows_tree))

        def validate_patch_hashes(actual):
            check(actual == patches, 'Exact nine frozen patch hashes required.')

        bad_hashes = dict(patches)
        bad_hashes[names[-1]] = '0' * 64
        helper.rejected('incorrect-patch-hash', lambda: validate_patch_hashes(bad_hashes), controls)
        altered = output / 'altered-derived.patch'
        altered.write_bytes(frozen_paths[names[-1]].read_bytes() + b'\ncorruption-control\n')
        bad_hashes = dict(patches)
        bad_hashes[names[-1]] = sha(altered)
        helper.rejected('altered-patch-bytes', lambda: validate_patch_hashes(bad_hashes), controls)
        for label, (name, before_bytes, after_bytes) in checker.MUTANTS.items():
            check(blobs[name].count(before_bytes) >= 1, 'Mutation anchor missing: ' + label)
            mutated = dict(blobs)
            mutated[name] = blobs[name].replace(before_bytes, after_bytes, 1)
            helper.rejected('source-' + label, lambda b=mutated: helper.validate_sources(b, hashes), controls)
        missing = dict(blobs)
        missing.pop(CID)
        helper.rejected('missing-source-file', lambda: helper.validate_sources(missing, hashes), controls)
        for label, omitted_name in [('cid', names[0]), ('derived', names[-1]), ('phase', names[-2])]:
            def negative_composition(name=omitted_name, control=label):
                negative = helper.compose(repo, BASE, [frozen_paths[n] for n in names if n != name],
                                          output / ('negative-missing-' + control + '.index'), receipts)
                check(negative == windows_tree, 'Composition missing ' + control + ' is not candidate.')
            helper.rejected('actual-composition-missing-' + label, negative_composition, controls)
        after, mobile_after = snapshot(helper, repo), snapshot(helper, mobile)
        check(after == before and mobile_after == mobile_before, 'A runtime checkout or native index changed.')
        check(checker.validate(repo, WINDOWS) == validation, 'Windows candidate changed during proof.')
        for name, expected in patches.items():
            check(sha(ROOT / 'eng/runtime-patches' / name) == expected, 'Original patch changed: ' + name)
        for path, expected in PINNED_TOOLS.items():
            target_name = 'old-source-proof.json' if path == OLD_PROOF else path.name
            check(sha(path) == expected and sha(output / target_name) == expected, 'Pinned source input changed.')
        check(sha(__file__) == sha(output / 'driver.py'), 'Proof driver changed during proof.')
        proof = {'schema': 'runeclr.mobile-derived-ledger.source-proof.v1', 'base': BASE,
                 'windowsCommit': WINDOWS, 'sourceCommit': source_commit, 'tree': windows_tree,
                 'patches': patches, 'sourceHashes': hashes, 'changedFileCount': len(paths),
                 'sourceHashFormat': 'SHA256 of exact Git blob bytes, LF; remote clean worktree must match',
                 'privateIndexCompositionVerified': True, 'windowsDeltaOnlyCID': True,
                 'oldMobileTree': OLD_TREE, 'oldWindowsCommit': OLD_WINDOWS,
                 'oldMobileSourceProofSha256': sha(OLD_PROOF), 'oldMobileDeltaOnlyMeterConfig': True,
                 'exactDerivedLedgerVerified': True, 'phaseAcquireLoadDefaultOff': True,
                 'terminalDerivedLedgerDefaultOff': True, 'phaseAndDerivedSwitchesIndependent': True,
                 'layoutSize': 64, 'layoutAlignment': 8,
                 'phaseFlagOffset': 2, 'derivedFlagOffset': 3,
                 'initialAllowanceOffsets': {'execution': 48, 'cleanup': 56},
                 'compositionTrees': {'windowsPlusCID': windows_tree, 'basePlusNinePatches': stack_tree,
                                      'oldMobilePlusPhaseAndDerived': old_tree},
                 'driverSha256': sha(__file__), 'candidateCheckerSha256': sha(CHECKER),
                 'helperSha256': sha(HELPER), 'requestSha256': sha(output / 'request.json'),
                 'combinedPatchSha256': sha(output / 'combined.patch'),
                 'appleGeneratorPatchIncluded': False, 'nativeBuildPerformed': False, 'executionVerified': False,
                 'runtimeTrackedCheckoutAndIndexUnchanged': True, 'sharedGitObjectStoreReceivesTrees': True,
                 'negativeControls': controls,
                 'claim': 'Exact mobile source composition only; no build, method entry or device acceptance.'}
        save(output / 'source-proof.json', proof)
        results = {'passed': True, 'sourceCommit': source_commit, 'tree': windows_tree,
                   'sourceFileCount': len(paths), 'patchCount': len(patches),
                   'negativeControlCount': len(controls), 'sourceProofSha256': sha(output / 'source-proof.json'),
                   'runtimeBefore': before, 'runtimeAfter': after,
                   'mobileBefore': mobile_before, 'mobileAfter': mobile_after, 'patchApplications': receipts,
                   'nativeBuildPerformed': False, 'executionVerified': False}
        save(output / 'results.json', results)
        print(json.dumps({k: v for k, v in results.items() if k not in
                          ['runtimeBefore', 'runtimeAfter', 'mobileBefore', 'mobileAfter', 'patchApplications']}))
    except Exception as error:
        save(output / 'failure.json', {'passed': False, 'error': str(error),
                                      'patchApplications': receipts, 'negativeControls': controls})
        raise


if __name__ == '__main__':
    main()
