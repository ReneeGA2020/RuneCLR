#!/usr/bin/env python3
"""Prepare a frozen batch candidate and new build adapter without running a build."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path('E:/runtime-batch-interval-20261014')
SOURCE_SDK = Path('E:/runtime-derived-ledger-20261014/.dotnet')
OUTPUT = ROOT / 'artifacts/budget-batching/candidate-20261014-attempt1'
CHECKER = ROOT / 'eng/batch-interval-runtime-candidate.py'
ORIGINAL_DRIVER = ROOT / 'eng/build-derived-ledger-release.py'
ORIGINAL_SHA = '4bf63866c7e40c0cde5471f7603e68bf0bf764c90f7f259de3b372ad34fb8a7c'
BASELINE = ROOT / 'artifacts/derived-ledger/windows-release-build-20261014-attempt1'
BASELINE_SHA = '7e66b11f9f676bb767307e5118d8f6c761bf6581ef15fbdd524a06f927f0bac1'
SDK_RECEIPT = ROOT / 'artifacts/derived-ledger/candidate-20261014-attempt1/candidate-receipt.json'
SDK_RECEIPT_SHA = 'd7c86e60f1aad2754a7868b2622d0ed180dfd6d4fec49b1ed2b797e7fead2f40'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def inventory(root):
    return {str(path.relative_to(root)): sha(path) for path in root.rglob('*') if path.is_file()}


def refused(action):
    try:
        action()
    except RuntimeError as error:
        return str(error)
    raise AssertionError('Negative control unexpectedly accepted.')


def main():
    module = load(CHECKER, 'batch_candidate')
    accepted = module.validate(RUNTIME)
    if OUTPUT.exists() or (RUNTIME / '.dotnet').exists():
        raise RuntimeError('Fresh preparation and absent private SDK required.')
    for path, expected in ((ORIGINAL_DRIVER, ORIGINAL_SHA), (BASELINE/'layout-receipt.json', BASELINE_SHA), (SDK_RECEIPT, SDK_RECEIPT_SHA)):
        if sha(path) != expected:
            raise RuntimeError('Frozen preparation input changed: ' + str(path))
    baseline = json.loads((BASELINE/'layout-receipt.json').read_text())
    if any(baseline.get(k) != v for k,v in {'passed': True, 'candidateCommit': module.BASELINE,
            'upstreamBase': module.UPSTREAM, 'platform': 'windows.x64', 'configuration': 'Release'}.items()):
        raise RuntimeError('Exact accepted derived-ledger Release baseline required.')
    if inventory(BASELINE/'layout') != baseline['allLayoutHashes']:
        raise RuntimeError('Baseline layout inventory changed.')
    sdk_receipt = json.loads(SDK_RECEIPT.read_text())
    sdk_hashes = inventory(SOURCE_SDK)
    if sdk_hashes != sdk_receipt['sdkFileHashes']:
        raise RuntimeError('Source SDK inventory changed.')
    blobs = {n: module.git(RUNTIME, 'show', module.COMMIT+':'+n) for n in module.CANDIDATE_HASHES}
    old_checker = load(ROOT/'eng/derived-ledger-runtime-candidate.py', 'old_candidate')
    negative = {'wrong_commit': refused(lambda: module.validate(RUNTIME, module.BASELINE)),
                'old_checker_rejects_new_candidate': refused(lambda: old_checker.validate(RUNTIME, module.COMMIT)),
                'missing_source': refused(lambda: module.validate_blobs({})),
                'extra_source': refused(lambda: module.validate_blobs(dict(blobs, extra=b'')))}
    for n, (file, old, new) in module.MUTANTS.items():
        if blobs[file].count(old) != 1:
            raise RuntimeError('Unique mutation anchor required: ' + n)
        changed = dict(blobs); changed[file] = blobs[file].replace(old, new, 1)
        negative[n] = refused(lambda changed=changed: module.validate_blobs(changed))
    OUTPUT.mkdir(parents=True, exist_ok=False)
    for source, target in ((Path(__file__), OUTPUT/'prepare-driver.py'), (CHECKER, OUTPUT/CHECKER.name), (ORIGINAL_DRIVER, OUTPUT/'baseline-build-driver.py')):
        shutil.copyfile(source, target)
    for n in blobs:
        target = OUTPUT/'source'/n; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(RUNTIME/n, target)
    (OUTPUT/'candidate.patch').write_bytes(module.git(RUNTIME, 'diff', '--binary', module.BASELINE, module.COMMIT))
    print('Frozen source and',len(negative),'source controls; copying',len(sdk_hashes),'SDK files', flush=True)
    shutil.copytree(SOURCE_SDK, RUNTIME/'.dotnet')
    if inventory(RUNTIME/'.dotnet') != sdk_hashes or inventory(SOURCE_SDK) != sdk_hashes:
        raise RuntimeError('SDK changed during copy.')
    version = subprocess.check_output([str(RUNTIME/'.dotnet/dotnet.exe'),'--version'],cwd=RUNTIME,text=True).strip()
    if version != '11.0.100-rc.1.26420.103' or module.validate(RUNTIME) != accepted:
        raise RuntimeError('SDK version/candidate changed.')
    receipt = {'passed': True, 'candidateValidation': accepted, 'sourceOnly': True,
               'sourceCheckerDoesNotProveNewPathExecution': True, 'negativeControls': negative,
               'candidateCheckerSha256': sha(CHECKER), 'prepareDriverSha256': sha(__file__),
               'baselineBuildDriverSha256': ORIGINAL_SHA, 'baselineLayoutReceiptSha256': BASELINE_SHA,
               'sourceSdkReceiptSha256': SDK_RECEIPT_SHA, 'candidatePatchSha256': sha(OUTPUT/'candidate.patch'),
               'sdkSource': str(SOURCE_SDK), 'sdkDestination': str(RUNTIME/'.dotnet'), 'sdkVersion': version,
               'sdkFileHashes': sdk_hashes, 'existingBuildDriverUnchanged': sha(ORIGINAL_DRIVER)==ORIGINAL_SHA,
               'scope': 'Source and SDK preparation; no CLR build, execution or timing.'}
    receipt_path = OUTPUT/'candidate-receipt.json'
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding='ascii')
    source = ORIGINAL_DRIVER.read_text()
    replacements = {
        module.BASELINE: module.COMMIT,
        "with_name('derived-ledger-runtime-candidate.py')": "with_name('batch-interval-runtime-candidate.py')",
        'artifacts/derived-ledger/candidate-20261014-attempt1/candidate-receipt.json': 'artifacts/budget-batching/candidate-20261014-attempt1/candidate-receipt.json',
        SDK_RECEIPT_SHA: sha(receipt_path),
        'ff93d495de89510248450a357f37dc798afa1c6e5b3b7ea89f73d34d41ca0827': BASELINE_SHA,
        "default='E:/runtime-derived-ledger-20261014'": "default='E:/runtime-batch-interval-20261014'",
        'artifacts/phase-load/windows-release-build-20261014-attempt1': 'artifacts/derived-ledger/windows-release-build-20261014-attempt1',
        'separately inventoried opt-in derived-ledger layout.': 'separately inventoried opt-in batch-interval layout.',
        'Frozen derived-ledger preparation receipt changed.': 'Frozen batch-interval preparation receipt changed.',
        'Baseline must be the accepted phase-load Windows x64 Release layout.': 'Baseline must be the accepted derived-ledger Windows x64 Release layout.',
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise RuntimeError('Unique frozen adapter anchor required: ' + old)
        source = source.replace(old,new,1)
    ast.parse(source)
    generated = ROOT/'eng/build-batch-interval-release.py'
    with generated.open('x', encoding='ascii') as stream:
        stream.write(source)
    shutil.copyfile(generated,OUTPUT/generated.name)
    ledger = {'passed': True, 'preparedOnly': True, 'candidateCommit': module.COMMIT,
              'preparationReceiptSha256': sha(receipt_path), 'buildAdapterSha256': sha(generated),
              'originalBuildDriverUnchanged': sha(ORIGINAL_DRIVER)==ORIGINAL_SHA,
              'command': ['py','-3.14','-B',str(generated),'--output',str(ROOT/'artifacts/budget-batching/windows-release-build-20261014-attempt1')],
              'scope': 'Build adapter ready; build not executed.'}
    (OUTPUT/'build-preparation.json').write_text(json.dumps(ledger,indent=2),encoding='ascii')
    print('PASS exact batch candidate,',len(negative),'source controls,',len(sdk_hashes),'SDK files; build adapter ready',flush=True)


if __name__ == '__main__':
    main()
