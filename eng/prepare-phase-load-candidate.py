#!/usr/bin/env python3
"""Freeze an exact phase-load candidate, reject source mutants, and copy its private SDK."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path('E:/runtime-phase-load-20261014')
SOURCE_SDK = Path('E:/runtime-increment-20261014/.dotnet')
OUTPUT = ROOT / 'artifacts/phase-load/candidate-20261014-attempt1'
CHECKER = ROOT / 'eng/phase-load-runtime-candidate.py'
ORIGINAL_DRIVER = ROOT / 'eng/build-budget-release.py'
ORIGINAL_SHA = 'd621563f44583416de2cd1768fc9dd4bde86310126325a6ac5a667168d4ce708'
BASELINE_RECEIPT = ROOT / 'artifacts/budget-increment/windows-release-build-20261014-attempt1/layout-receipt.json'
BASELINE_SHA = 'ef93b153857cac0f51ceb1f6d012b676ae8ddd620415a56627f65b21a5e1df78'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def refused(action):
    try:
        action()
    except RuntimeError as error:
        return str(error)
    raise AssertionError('Negative control unexpectedly accepted.')

def main():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, OUTPUT / 'prepare-driver.py')
    module = load(CHECKER, 'phase_load_candidate')
    accepted = module.validate(RUNTIME)
    old_checker = load(ROOT / 'eng/budget-runtime-candidate.py', 'old_budget_candidate')
    blobs = {name: module.git(RUNTIME, 'show', module.COMMIT + ':' + name) for name in module.CANDIDATE_HASHES}
    negative = {'wrong_commit': refused(lambda: module.validate(RUNTIME, module.BASELINE)),
                'old_checker_rejects_new_candidate': refused(lambda: old_checker.validate(RUNTIME, module.COMMIT)),
                'missing_config_inventory': refused(lambda: module.validate_blobs({module.METER: blobs[module.METER]}))}
    mutants = {
        'config_default_on': (module.CONFIG, b'AcquireLoad"), 0,', b'AcquireLoad"), 1,'),
        'phase_relaxed_helper': (module.METER, b'VolatileLoad(&m_phase)', b'VolatileLoadWithoutBarrier(&m_phase)'),
        'mutable_cache': (module.METER, b'const bool m_phaseAcquireLoad;', b'bool m_phaseAcquireLoad;'),
        'phase_writer_changed': (module.METER, b'InterlockedCompareExchange(&m_phase, 1, 0);', b'InterlockedCompareExchange(&m_phase, 2, 0);'),
        'admission_increment_changed': (module.METER, b'InterlockedIncrement64(&executed);', b'InterlockedIncrement64(&remaining);'),
    }
    for name, (file, old, new) in mutants.items():
        assert blobs[file].count(old) == 1
        changed = dict(blobs)
        changed[file] = blobs[file].replace(old, new, 1)
        negative[name] = refused(lambda changed=changed: module.validate_blobs(changed))
    assert sha(ORIGINAL_DRIVER) == ORIGINAL_SHA
    assert sha(BASELINE_RECEIPT) == BASELINE_SHA
    source = ORIGINAL_DRIVER.read_text()
    replacements = {
        '099dacd07d8d890822f7422f895337733457ab3c': module.COMMIT,
        "with_name('budget-runtime-candidate.py')": "with_name('phase-load-runtime-candidate.py')",
        "default='E:/runtime-finalizer-20261013'": "default='E:/runtime-phase-load-20261014'",
        "artifacts/session-finalizer/build-20261013-attempt1": "artifacts/budget-increment/windows-release-build-20261014-attempt1",
        "for name,expected in base_receipt['frameworkHashes'].items():": "for name,expected in base_receipt['allLayoutHashes'].items():",
        "sha(base_framework/name)": "sha(base_layout/name)",
    }
    for old, new in replacements.items():
        assert source.count(old) == 1, old
        source = source.replace(old, new, 1)
    source = source.replace('a separately inventoried layout.', 'a separately inventoried phase-acquire layout.', 1)
    generated = ROOT / 'eng/build-phase-load-release.py'
    with generated.open('x', encoding='ascii') as stream:
        stream.write(source)
    shutil.copyfile(ORIGINAL_DRIVER, OUTPUT / 'baseline-build-driver.py')
    shutil.copyfile(generated, OUTPUT / generated.name)
    shutil.copyfile(CHECKER, OUTPUT / CHECKER.name)
    for name in module.CANDIDATE_HASHES:
        target = OUTPUT / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(RUNTIME / name, target)
    patch = module.git(RUNTIME, 'diff', '--binary', module.BASELINE, module.COMMIT)
    (OUTPUT / 'candidate.patch').write_bytes(patch)
    sdk_paths = sorted(path for path in SOURCE_SDK.rglob('*') if path.is_file())
    sdk_hashes = {str(path.relative_to(SOURCE_SDK)): sha(path) for path in sdk_paths}
    print('Frozen candidate and', len(negative), 'rejected source controls; copying', len(sdk_hashes), 'private SDK files', flush=True)
    destination = RUNTIME / '.dotnet'
    shutil.copytree(SOURCE_SDK, destination)
    copied = {str(path.relative_to(destination)): sha(path) for path in destination.rglob('*') if path.is_file()}
    assert copied == sdk_hashes
    assert {str(path.relative_to(SOURCE_SDK)): sha(path) for path in SOURCE_SDK.rglob('*') if path.is_file()} == sdk_hashes
    sdk_version = subprocess.check_output([str(destination / 'dotnet.exe'), '--version'], cwd=RUNTIME, text=True).strip()
    assert sdk_version == '11.0.100-rc.1.26420.103'
    assert module.validate(RUNTIME) == accepted
    result = {'passed': True, 'candidateValidation': accepted, 'sourceOnly': True,
              'sourceCheckerDoesNotProveNewPathExecution': True, 'negativeControls': negative,
              'candidateCheckerSha256': sha(CHECKER), 'prepareDriverSha256': sha(Path(__file__)),
              'oldBuildDriverSha256': ORIGINAL_SHA, 'buildAdapterSha256': sha(generated),
              'baselineLayoutReceiptSha256': BASELINE_SHA,
              'candidatePatchSha256': sha(OUTPUT / 'candidate.patch'),
              'sdkSource': str(SOURCE_SDK), 'sdkDestination': str(destination),
              'sdkVersion': sdk_version, 'sdkFileHashes': sdk_hashes,
              'existingBuildDriverUnchanged': sha(ORIGINAL_DRIVER) == ORIGINAL_SHA}
    (OUTPUT / 'candidate-receipt.json').write_text(json.dumps(result, indent=2), encoding='ascii')
    print('PASS exact candidate,', len(negative), 'negative controls and', len(copied), 'hash-matched SDK files', flush=True)

if __name__ == '__main__':
    main()
