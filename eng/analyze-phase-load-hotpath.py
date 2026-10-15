#!/usr/bin/env python3
"""Inspect the exact phase-load candidate's private Release PE/PDB offline."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

PARENT_SHA = '32624a937991eb0501a287c06ad7dc1efd8da5ac4ab418517fc2f41b5e01a9e8'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    for argument in ('--runtime', '--build', '--output', '--candidate-commit'):
        if argument not in sys.argv:
            raise ValueError('Explicit matching input required: ' + argument)
    parent_path = Path(__file__).with_name('analyze-budget-hotpath.py')
    if sha(parent_path) != PARENT_SHA:
        raise ValueError('Frozen parent analysis driver changed.')
    checker_path = Path(__file__).with_name('phase-load-runtime-candidate.py')
    checker_sha = sha(checker_path)
    checker = module(checker_path, 'phase_load_analysis_candidate')
    runtime = Path(sys.argv[sys.argv.index('--runtime') + 1]).resolve()
    evidence = Path(sys.argv[sys.argv.index('--build') + 1]).resolve()
    output = Path(sys.argv[sys.argv.index('--output') + 1]).resolve()
    candidate = sys.argv[sys.argv.index('--candidate-commit') + 1]
    validation = checker.validate(runtime, candidate)
    build = json.loads((evidence / 'build-result.json').read_text())
    if build['candidateValidation'] != validation or build['candidateCheckerSha256'] != checker_sha:
        raise ValueError('Analysis checker differs from the actual build binding.')
    parent = module(parent_path, 'frozen_phase_analysis_parent')
    parent._candidate = checker
    parent.CHECKER_PATH = checker_path
    parent.COMMIT = checker.COMMIT
    parent.__file__ = __file__
    parent.main()
    if sha(parent_path) != PARENT_SHA or sha(checker_path) != checker_sha:
        raise ValueError('Analysis dependencies changed during inspection.')
    if checker.validate(runtime, candidate) != validation:
        raise ValueError('Analysis candidate changed during inspection.')
    shutil.copy2(parent_path, output / 'parent-analysis-driver.py')
    config = runtime / checker.CONFIG
    copied_config = output / 'source' / checker.CONFIG
    copied_config.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config, copied_config)
    binding = {'passed': True, 'parentDriverSha256': PARENT_SHA,
               'checkerSha256': checker_sha, 'driverSha256': sha(Path(__file__)),
               'candidateValidation': validation, 'configSha256': sha(config),
               'buildResultSha256': sha(evidence / 'build-result.json'),
               'offlineOnly': True, 'livePhaseBranchObserved': False,
               'scope': 'Actual compiled PE/PDB inventory; ON/OFF path analysis and live selection require separate evidence.'}
    (output / 'phase-analysis-binding.json').write_text(json.dumps(binding, indent=2) + chr(10))
    print('PASS exact phase-load offline analysis binding; live branch selection not claimed.')


if __name__ == '__main__':
    main()
