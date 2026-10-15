#!/usr/bin/env python3
"""Inspect the exact derived-ledger private Release PE/PDB offline only."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

PARENT_SHA = '32624a937991eb0501a287c06ad7dc1efd8da5ac4ab418517fc2f41b5e01a9e8'
COMMANDS = ('lmvm coreclr; x coreclr!*RuneCLRInstructionMeter*; x coreclr!*RuneCLRChargeCurrentInstruction*; '
            'dt coreclr!RuneCLRInstructionMeter; dt coreclr!InterpMethodContextFrame; '
            'uf /o coreclr!InterpExecMethod; '
            'uf /o coreclr!RuneCLRInstructionMeter::Phase; '
            'uf /o coreclr!AssemblyNative_RuneCLRGetInstructionMeterExecuted; '
            'uf /o coreclr!AssemblyNative_RuneCLRGetTerminalPrototypeCleanupExecuted; '
            'uf /o coreclr!RuneCLRInstructionMeter::Executed; '
            'uf /o coreclr!RuneCLRInstructionMeter::CleanupExecuted; q')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def main():
    for argument in ('--runtime', '--build', '--output', '--candidate-commit'):
        if argument not in sys.argv:
            raise ValueError('Explicit matching input required: ' + argument)
    parent_path = Path(__file__).with_name('analyze-budget-hotpath.py')
    if sha(parent_path) != PARENT_SHA:
        raise ValueError('Frozen original analysis driver changed.')
    checker_path = Path(__file__).with_name('derived-ledger-runtime-candidate.py')
    checker_sha = sha(checker_path)
    checker = module(checker_path, 'derived_native_candidate')
    runtime = Path(sys.argv[sys.argv.index('--runtime') + 1]).resolve()
    build = Path(sys.argv[sys.argv.index('--build') + 1]).resolve()
    output = Path(sys.argv[sys.argv.index('--output') + 1]).resolve()
    candidate = sys.argv[sys.argv.index('--candidate-commit') + 1]
    validation = checker.validate(runtime, candidate)
    built = json.loads((build / 'build-result.json').read_text())
    if built['candidateValidation'] != validation or built['candidateCheckerSha256'] != checker_sha:
        raise ValueError('Build does not bind exact derived-ledger candidate/checker.')
    parent = module(parent_path, 'derived_frozen_native_parent')
    text = parent_path.read_text()
    old = next(line for line in text.splitlines() if line.startswith('    commands='))
    text = text.replace(old, '    commands=' + repr(COMMANDS))
    ast.parse(text, filename=str(parent_path))
    exec(compile(text, str(parent_path), 'exec'), parent.__dict__)
    parent._candidate = checker
    parent.CHECKER_PATH = checker_path
    parent.COMMIT = checker.COMMIT
    parent.__file__ = __file__
    parent.main()
    if sha(parent_path) != PARENT_SHA or sha(checker_path) != checker_sha:
        raise ValueError('Offline analysis dependency changed.')
    if checker.validate(runtime, candidate) != validation:
        raise ValueError('Source candidate changed during inspection.')
    shutil.copyfile(parent_path, output / 'parent-analysis-driver.py')
    (output / 'adapted-analysis-source.py').write_text(text, encoding='ascii')
    config = runtime / checker.CONFIG
    copied = output / 'source' / checker.CONFIG
    copied.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(config, copied)
    binding = {'passed': True, 'driverSha256': sha(__file__), 'parentDriverSha256': PARENT_SHA,
               'adaptedSourceSha256': sha(output / 'adapted-analysis-source.py'),
               'checkerSha256': checker_sha, 'candidateValidation': validation,
               'configSha256': sha(config), 'buildResultSha256': sha(build / 'build-result.json'),
               'meterSize': 64, 'fieldOffsets': {'derivedFlag': 3, 'initialExecutionLimit': 48, 'initialCleanupLimit': 56},
               'offlineOnly': True, 'liveLedgerBranchObserved': False, 'performanceMeasured': False,
               'scope': 'Compiled instruction inventory only; independent connected-path review and actual live selection remain separate.'}
    (output / 'derived-analysis-binding.json').write_text(json.dumps(binding, indent=2) + chr(10))
    print('PASS derived-ledger offline PE/PDB inventory; live branch not claimed.')

if __name__ == '__main__':
    main()
