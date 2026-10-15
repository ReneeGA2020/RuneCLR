#!/usr/bin/env python3
"""Freeze exact derived-ledger source and a private SDK; prepare, but never run, its build."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path('E:/runtime-derived-ledger-20261014')
SOURCE_SDK = Path('E:/runtime-phase-load-20261014/.dotnet')
OUTPUT = ROOT / 'artifacts/derived-ledger/candidate-20261014-attempt1'
CHECKER = ROOT / 'eng/derived-ledger-runtime-candidate.py'
ORIGINAL_DRIVER = ROOT / 'eng/build-phase-load-release.py'
ORIGINAL_SHA = '7587aca3215b313f248ffa8dc42b5b8eefa2c9b362349f023516106f12e3cf99'
BASELINE = ROOT / 'artifacts/phase-load/windows-release-build-20261014-attempt1'
BASELINE_SHA = 'ff93d495de89510248450a357f37dc798afa1c6e5b3b7ea89f73d34d41ca0827'
SDK_RECEIPT = ROOT / 'artifacts/phase-load/candidate-20261014-attempt1/candidate-receipt.json'
SDK_RECEIPT_SHA = '05184760a95bd4f4151d986df928143c4782ed7cb75679882aba4a0d1f409fa4'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def refused(action):
    try:
        action()
    except RuntimeError as error:
        return str(error)
    raise AssertionError('Negative control unexpectedly accepted.')


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Expected one frozen adapter anchor: ' + old)
    return text.replace(old, new, 1)


def inventory(root):
    return {str(path.relative_to(root)): sha(path) for path in root.rglob('*') if path.is_file()}


def main():
    module = load(CHECKER, 'derived_ledger_candidate')
    accepted = module.validate(RUNTIME)
    if OUTPUT.exists() or (RUNTIME / '.dotnet').exists():
        raise RuntimeError('Fresh preparation and absent destination SDK required; preserve existing files.')
    for path, expected in ((ORIGINAL_DRIVER, ORIGINAL_SHA), (BASELINE / 'layout-receipt.json', BASELINE_SHA),
                           (SDK_RECEIPT, SDK_RECEIPT_SHA)):
        if sha(path) != expected:
            raise RuntimeError('Frozen preparation input changed: ' + str(path))
    baseline = json.loads((BASELINE / 'layout-receipt.json').read_text())
    if any(baseline.get(key) != value for key, value in {
            'passed': True, 'candidateCommit': module.BASELINE, 'upstreamBase': module.UPSTREAM,
            'platform': 'windows.x64', 'configuration': 'Release'}.items()):
        raise RuntimeError('Exact accepted phase-load Windows Release baseline required.')
    if inventory(BASELINE / 'layout') != baseline['allLayoutHashes']:
        raise RuntimeError('Exact baseline layout inventory changed.')
    sdk_receipt = json.loads(SDK_RECEIPT.read_text())
    sdk_hashes = inventory(SOURCE_SDK)
    if sdk_hashes != sdk_receipt['sdkFileHashes'] or sdk_receipt['sdkVersion'] != '11.0.100-rc.1.26420.103':
        raise RuntimeError('Source private SDK differs from its frozen candidate receipt.')
    blobs = {name: module.git(RUNTIME, 'show', module.COMMIT + ':' + name) for name in module.CANDIDATE_HASHES}
    old_checker = load(ROOT / 'eng/phase-load-runtime-candidate.py', 'phase_load_candidate')
    negative = {'wrong_commit': refused(lambda: module.validate(RUNTIME, module.BASELINE)),
                'old_checker_rejects_new_candidate': refused(lambda: old_checker.validate(RUNTIME, module.COMMIT)),
                'missing_config_inventory': refused(lambda: module.validate_blobs({module.METER: blobs[module.METER]})),
                'extra_source_inventory': refused(lambda: module.validate_blobs(dict(blobs, extra=b'')))}
    for name, (file, old, new) in module.MUTANTS.items():
        if blobs[file].count(old) != 1:
            raise RuntimeError('Exact mutant anchor missing or repeated: ' + name)
        changed = dict(blobs); changed[file] = blobs[file].replace(old, new, 1)
        negative[name] = refused(lambda changed=changed: module.validate_blobs(changed))
    OUTPUT.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, OUTPUT / 'prepare-driver.py')
    shutil.copyfile(CHECKER, OUTPUT / CHECKER.name)
    shutil.copyfile(ORIGINAL_DRIVER, OUTPUT / 'baseline-build-driver.py')
    for name in module.CANDIDATE_HASHES:
        target = OUTPUT / 'source' / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(RUNTIME / name, target)
    (OUTPUT / 'candidate.patch').write_bytes(module.git(RUNTIME, 'diff', '--binary', module.BASELINE, module.COMMIT))
    print('Frozen exact source and', len(negative), 'rejected source controls; copying', len(sdk_hashes), 'private SDK files', flush=True)
    destination = RUNTIME / '.dotnet'
    shutil.copytree(SOURCE_SDK, destination)
    if inventory(destination) != sdk_hashes or inventory(SOURCE_SDK) != sdk_hashes:
        raise RuntimeError('SDK copy/source inventory changed.')
    version = subprocess.check_output([str(destination / 'dotnet.exe'), '--version'], cwd=RUNTIME, text=True).strip()
    if version != sdk_receipt['sdkVersion'] or module.validate(RUNTIME) != accepted:
        raise RuntimeError('Copied SDK version or candidate changed during preparation.')
    receipt = {'passed': True, 'candidateValidation': accepted, 'sourceOnly': True,
               'sourceCheckerDoesNotProveNewPathExecution': True, 'negativeControls': negative,
               'candidateCheckerSha256': sha(CHECKER), 'prepareDriverSha256': sha(__file__),
               'baselineBuildDriverSha256': ORIGINAL_SHA, 'baselineLayoutReceiptSha256': BASELINE_SHA,
               'sourceSdkReceiptSha256': SDK_RECEIPT_SHA, 'candidatePatchSha256': sha(OUTPUT / 'candidate.patch'),
               'sdkSource': str(SOURCE_SDK), 'sdkDestination': str(destination), 'sdkVersion': version,
               'sdkFileHashes': sdk_hashes, 'existingBuildDriverUnchanged': sha(ORIGINAL_DRIVER) == ORIGINAL_SHA,
               'scope': 'Source and private SDK preparation only; no runtime build, suite, benchmark or device execution.'}
    receipt_path = OUTPUT / 'candidate-receipt.json'
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding='ascii')
    source = ORIGINAL_DRIVER.read_text()
    replacements = {
        module.BASELINE: module.COMMIT,
        "with_name('phase-load-runtime-candidate.py')": "with_name('derived-ledger-runtime-candidate.py')",
        'artifacts/phase-load/candidate-20261014-attempt1/candidate-receipt.json':
            'artifacts/derived-ledger/candidate-20261014-attempt1/candidate-receipt.json',
        '05184760a95bd4f4151d986df928143c4782ed7cb75679882aba4a0d1f409fa4': sha(receipt_path),
        'ef93b153857cac0f51ceb1f6d012b676ae8ddd620415a56627f65b21a5e1df78': BASELINE_SHA,
        "default='E:/runtime-phase-load-20261014'": "default='E:/runtime-derived-ledger-20261014'",
        'artifacts/budget-increment/windows-release-build-20261014-attempt1':
            'artifacts/phase-load/windows-release-build-20261014-attempt1',
        'separately inventoried phase-acquire layout.': 'separately inventoried opt-in derived-ledger layout.',
        'Frozen phase-load preparation receipt changed.': 'Frozen derived-ledger preparation receipt changed.',
        'Baseline must be the accepted increment Windows x64 Release layout.':
            'Baseline must be the accepted phase-load Windows x64 Release layout.',
    }
    for old, new in replacements.items():
        source = replace_once(source, old, new)
    ast.parse(source)
    generated = ROOT / 'eng/build-derived-ledger-release.py'
    with generated.open('x', encoding='ascii') as stream:
        stream.write(source)
    shutil.copyfile(generated, OUTPUT / generated.name)
    ledger = {'passed': True, 'preparedOnly': True, 'candidateCommit': module.COMMIT,
              'preparationReceiptSha256': sha(receipt_path), 'buildAdapterSha256': sha(generated),
              'originalBuildDriverUnchanged': sha(ORIGINAL_DRIVER) == ORIGINAL_SHA,
              'command': ['py', '-3', '-B', str(generated), '--output',
                          str(ROOT / 'artifacts/derived-ledger/windows-release-build-20261014-attempt1')],
              'scope': 'Build adapter frozen; build command was not executed.'}
    (OUTPUT / 'build-preparation.json').write_text(json.dumps(ledger, indent=2), encoding='ascii')
    print('PASS exact candidate,', len(negative), 'source controls,', len(sdk_hashes), 'SDK files and build adapter; build not started', flush=True)


if __name__ == '__main__':
    main()
