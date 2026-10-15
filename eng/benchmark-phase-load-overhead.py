#!/usr/bin/env python3
"""Freeze the exact phase-load experiment; measure only via explicit run mode."""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
COMMIT = 'a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186'
BASELINE = '20405f7ae23e183e038703aa5e356b3310fef427'
SWITCH = 'DOTNET_RuneCLRPhaseAcquireLoad'
RUNTIME = Path('E:/runtime-phase-load-20261014')
BUILD = ROOT / 'artifacts/phase-load/windows-release-build-20261014-attempt1'
ACCEPTANCE = ROOT / 'artifacts/phase-load/windows-acceptance-run-20261014-attempt1'
PREPARED = ROOT / 'artifacts/phase-load/windows-acceptance-preparation-20261014-attempt2'
LIVE = ROOT / 'artifacts/phase-load/windows-live-witness-20261014-attempt4'
LEGACY = ROOT / 'eng/benchmark-budget-overhead.py'
CHECKER = ROOT / 'eng/phase-load-runtime-candidate.py'
LEGACY_HASH = 'a4613a272323c013ed148008007e815049a7f72664d130db5f1638dcb765c30f'
ORDER = ('terminal', 'finalizer', 'host', 'budget-audit', 'concurrency', 'concurrency-audit', 'production', 'production-audit')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + chr(10), encoding='ascii')

def require(value, message):
    if not value:
        raise RuntimeError(message)

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def legacy_module():
    require(sha(LEGACY) == LEGACY_HASH, 'Original benchmark changed; a new preparation is required.')
    original = module(LEGACY, 'phase_original_benchmark')
    original.COMMIT = COMMIT
    original.CHECKER_PATH = CHECKER
    original._candidate = module(CHECKER, 'phase_exact_candidate')
    return original

def prerequisites():
    run = load(ACCEPTANCE / 'run-receipt.json')
    require(run['passed'] and len(run['runs']) == 16, 'Exactly sixteen passed functional commands required.')
    require([(x['profile'], x['suite']) for x in run['runs']] ==
            [(profile, suite) for profile in ('off', 'on') for suite in ORDER], 'Functional suite/profile inventory differs.')
    inputs = {ACCEPTANCE / 'run-receipt.json', PREPARED / 'preparation.json'}
    require(run['preparedManifestSha256'] == sha(PREPARED / 'preparation.json'), 'Functional preparation differs.')
    for row in run['runs']:
        require(row['passed'] and row['exitCode'] == 0 and not row['timedOut'], 'Functional command failed.')
        for stream in ('stdout', 'stderr'):
            path = ACCEPTANCE / (row['profile'] + '-' + row['suite'] + '.' + stream)
            require(sha(path) == row[stream + 'Sha256'], 'Functional raw stream changed.')
            inputs.add(path)
    prepared = load(PREPARED / 'preparation.json')
    require(prepared['passed'], 'Functional preparation failed.')
    for label in ('off', 'on'):
        directory = PREPARED / label / 'eng'
        profile_path = directory / 'profile.json'
        profile = load(profile_path)
        require(sha(profile_path) == prepared['profiles'][label]['profileSha256'], 'Functional profile changed.')
        require(profile['candidateCommit'] == COMMIT and profile['phaseAcquireValue'] == ('0' if label == 'off' else '1'),
                'Functional phase profile differs.')
        inputs.add(profile_path)
        for relative, expected in profile['snapshotHashes'].items():
            path = directory / relative
            require(sha(path) == expected, 'Functional snapshot changed.')
            inputs.add(path)
        for name, expected in profile['originalInputHashes'].items():
            path = Path(name)
            require(sha(path) == expected, 'Functional original input changed.')
            inputs.add(path)
    witness_path = LIVE / 'review/results.json'
    witness = load(witness_path)
    require(witness['passed'] and witness['processes'] == witness['collections'] == 4 and
            witness['actualOnOffHotLoopBranches'] and witness['sameFixtureNativeManagedInputs'] and
            witness['corruptionControlsRejected'] == 24 and not witness['benchmark'], 'Four live branch witnesses required.')
    require([(x['flag'], x['scenario']) for x in witness['lanes']] ==
            [(flag, scenario) for flag in (0, 1) for scenario in ('Good', 'TightLoop')], 'Live witness inventory differs.')
    inputs.add(witness_path)
    for name, expected in witness['boundFiles'].items():
        path = Path(name)
        require(sha(path) == expected, 'Live witness bound input changed.')
        inputs.add(path)
    for name, key in (('audit-phase-load-windows-witness.py', 'auditorSha256'),
                      ('audit-phase-load-windows-witness-set.py', 'joinerSha256')):
        path = ROOT / 'eng' / name
        require(sha(path) == witness[key], 'Live witness auditor changed.')
        inputs.add(path)
    return inputs

def validate_preparation(directory, value=None):
    directory = Path(directory).resolve()
    value = load(directory / 'preparation.json') if value is None else value
    require(value['passed'] and value['candidateCommit'] == COMMIT and value['baselineCommit'] == BASELINE,
            'Pinned phase benchmark candidate differs.')
    require(value['pairs'] == 4 and value['samplesPerProcess'] == 9 and value['affinity'] == 4 and
            value['configuration'] == 'Release' and value['functionalCommands'] == 16 and value['liveWitnesses'] == 4,
            'Frozen benchmark parameters/prerequisites differ.')
    require(value['runtime'] == str(RUNTIME.resolve()) and value['layout'] == str((BUILD / 'layout').resolve()) and
            value['buildEvidence'] == str(BUILD.resolve()), 'Frozen runtime/build/layout differs.')
    require(value['candidateValidation'] == module(CHECKER, 'phase_guard_candidate').validate(RUNTIME, COMMIT),
            'Exact source candidate changed.')
    require(value['runtimeBuildBinding']['actualSourceCommit'] == COMMIT and
            value['runtimeBuildBinding']['candidateValidation'] == value['candidateValidation'], 'Build candidate binding differs.')
    for name, expected in value['originalInputHashes'].items():
        require(sha(name) == expected, 'Frozen original input changed: ' + name)
    for relative, expected in value['snapshotHashes'].items():
        require(sha(directory / relative) == expected, 'Frozen snapshot changed: ' + relative)
    require(value['adapterSha256'] == sha(__file__) and value['legacyBenchmarkSha256'] == sha(LEGACY) == LEGACY_HASH,
            'Frozen adapter/original benchmark differs.')
    return value

def prepare(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    original = legacy_module()
    inputs = prerequisites()
    binding, build_inputs = original.freeze_build_binding(RUNTIME, BUILD / 'layout', 'Release', BUILD, output, COMMIT)
    inputs.update(Path(name) for name in build_inputs)
    for folder in ('benchmarks/RuneCLR.BudgetKernel', 'benchmarks/RuneCLR.BudgetOverhead',
                   'src/RuneCLR.Runtime', 'src/RuneCLR.Abstractions', 'src/RuneCLR.Packages'):
        base = ROOT / folder
        inputs.update(path for path in base.rglob('*') if path.suffix in ('.cs', '.csproj') and
                      not {'obj', 'bin'}.intersection(path.relative_to(base).parts))
    inputs.update(path for path in (ROOT / 'Directory.Build.props', ROOT / 'Directory.Build.targets',
                  ROOT / 'global.json', ROOT / 'NuGet.Config') if path.exists())
    inputs.update((Path(__file__).resolve(), LEGACY, CHECKER, ROOT / 'artifacts/toolchains/dotnet-11-rc1/dotnet.exe'))
    snapshots = {}
    originals = {}
    for number, path in enumerate(sorted(inputs, key=str)):
        relative = 'inputs/' + str(number) + '/' + path.name
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        snapshots[relative] = sha(target)
        originals[str(path.resolve())] = sha(path)
    snapshots.update({str(path.relative_to(output)).replace('\\', '/'): sha(path)
                      for path in (output / 'provenance').rglob('*') if path.is_file()})
    value = {'passed': True, 'version': 1, 'candidateCommit': COMMIT, 'baselineCommit': BASELINE,
             'runtime': str(RUNTIME.resolve()), 'layout': str((BUILD / 'layout').resolve()), 'buildEvidence': str(BUILD.resolve()),
             'candidateValidation': binding['candidateValidation'], 'runtimeBuildBinding': binding,
             'configuration': 'Release', 'pairs': 4, 'samplesPerProcess': 9, 'affinity': 4,
             'functionalCommands': 16, 'liveWitnesses': 4, 'phaseValues': ['0', '1'], 'phaseAcquireSwitch': SWITCH,
             'adapterSha256': sha(__file__), 'legacyBenchmarkSha256': sha(LEGACY),
             'originalInputHashes': originals, 'snapshotHashes': snapshots,
             'scope': 'Original arithmetic callback and whole-session fixtures only; no timing performed during preparation.'}
    save(output / 'preparation.json', value)
    validate_preparation(output)
    controls = []
    edits = {
        'candidate': lambda x: x.__setitem__('candidateCommit', '0' * 40),
        'baseline': lambda x: x.__setitem__('baselineCommit', '0' * 40),
        'pairs': lambda x: x.__setitem__('pairs', 1),
        'affinity': lambda x: x.__setitem__('affinity', 1),
        'functional-count': lambda x: x.__setitem__('functionalCommands', 15),
        'witness-count': lambda x: x.__setitem__('liveWitnesses', 3),
        'layout': lambda x: x.__setitem__('layout', str(ROOT)),
        'build-candidate': lambda x: x['runtimeBuildBinding'].__setitem__('actualSourceCommit', BASELINE),
        'original-hash': lambda x: x['originalInputHashes'].__setitem__(next(iter(x['originalInputHashes'])), '0' * 64),
        'snapshot-hash': lambda x: x['snapshotHashes'].__setitem__(next(iter(x['snapshotHashes'])), '0' * 64),
    }
    for name, edit in edits.items():
        altered = copy.deepcopy(value)
        edit(altered)
        try:
            validate_preparation(output, altered)
        except RuntimeError as error:
            controls.append({'name': name, 'rejected': True, 'reason': str(error)})
        else:
            raise RuntimeError('Preparation corruption accepted: ' + name)
    ast.parse(Path(__file__).read_text(), filename=__file__)
    save(output / 'review.json', {'passed': True, 'preparationSha256': sha(output / 'preparation.json'),
         'astParsed': True, 'negativeControls': controls, 'benchmarkExecuted': False, 'buildExecuted': False})
    print(json.dumps({'passed': True, 'frozenInputs': len(originals), 'negativeControls': len(controls),
                      'functionalCommands': 16, 'liveWitnesses': 4, 'benchmarkExecuted': False}, indent=2))

def run(preparation, output, flag):
    preparation = preparation.resolve()
    value = validate_preparation(preparation)
    original = legacy_module()
    original.__file__ = str(Path(__file__).resolve())
    old_command, old_save = original.command, original.save
    preparation_hash = sha(preparation / 'preparation.json')
    def guard():
        require(sha(preparation / 'preparation.json') == preparation_hash, 'Preparation receipt changed during measurement.')
        validate_preparation(preparation)
    def phase_command(argv, directory, label, settings=None):
        guard()
        settings = dict(settings or {})
        require(SWITCH not in settings or settings[SWITCH] == flag, 'Conflicting phase setting.')
        settings[SWITCH] = flag
        result = old_command(argv, directory, label, settings)
        guard()
        return result
    def phase_save(path, data):
        name = Path(path).name
        if name in ('request.json', 'results.json'):
            data.update({'phaseAcquireValue': int(flag), 'phaseAcquireSwitch': SWITCH,
                         'phaseBenchmarkPreparationSha256': preparation_hash,
                         'phaseBenchmarkAdapterSha256': value['adapterSha256'],
                         'legacyBenchmarkSha256': value['legacyBenchmarkSha256']})
        if name == 'request.json':
            shutil.copyfile(preparation / 'preparation.json', Path(path).parent / 'phase-benchmark-preparation.json')
            shutil.copyfile(__file__, Path(path).parent / 'phase-benchmark-adapter.py')
            shutil.copyfile(LEGACY, Path(path).parent / 'phase-legacy-benchmark.py')
        old_save(path, data)
    original.command, original.save = phase_command, phase_save
    sys.argv = [str(Path(__file__).resolve()), '--output', str(output.resolve()), '--runtime', value['runtime'],
                '--candidate-commit', COMMIT, '--layout', value['layout'], '--configuration', 'Release',
                '--build-evidence', value['buildEvidence'], '--pairs', '4', '--samples', '9']
    original.main()
    guard()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    preparation = actions.add_parser('prepare')
    preparation.add_argument('--output', type=Path, required=True)
    measurement = actions.add_parser('run')
    measurement.add_argument('--preparation', type=Path, required=True)
    measurement.add_argument('--output', type=Path, required=True)
    measurement.add_argument('--phase-acquire', choices=('0', '1'), required=True)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.output)
    else:
        run(args.preparation, args.output, args.phase_acquire)

if __name__ == '__main__':
    main()
