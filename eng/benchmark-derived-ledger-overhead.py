#!/usr/bin/env python3
"""Freeze the exact derived-ledger experiment; measure only via explicit run mode."""
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
COMMIT = '29ff781e157be82ba5a398a60bb05291e4a865af'
BASELINE = 'a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186'
SWITCH = 'DOTNET_RuneCLRDerivedLedger'
PHASE_SWITCH = 'DOTNET_RuneCLRPhaseAcquireLoad'
RUNTIME = Path('E:/runtime-derived-ledger-20261014')
BUILD = ROOT / 'artifacts/derived-ledger/windows-release-build-20261014-attempt1'
ACCEPTANCE = ROOT / 'artifacts/derived-ledger/windows-acceptance-run-20261014-attempt1'
PREPARED = ROOT / 'artifacts/derived-ledger/windows-acceptance-preparation-20261014-attempt1'
LIVE = ROOT / 'artifacts/derived-ledger/windows-live-witness-20261014-attempt1'
LEGACY = ROOT / 'eng/benchmark-budget-overhead.py'
CHECKER = ROOT / 'eng/derived-ledger-runtime-candidate.py'
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
    original = module(LEGACY, 'derived_original_benchmark')
    original.COMMIT = COMMIT
    original.CHECKER_PATH = CHECKER
    original._candidate = module(CHECKER, 'derived_exact_candidate')
    return original

def validate_build_binding(binding, validation):
    product = RUNTIME / 'artifacts/bin/coreclr/windows.x64.Release'
    cache = RUNTIME / 'artifacts/obj/coreclr/windows.x64.Release/CMakeCache.txt'
    request = load(BUILD / 'request.json')
    result = load(BUILD / 'build-result.json')
    layout = load(BUILD / 'layout-receipt.json')
    for value in (request, result, layout):
        require(value['candidateValidation'] == validation and value['candidateCheckerSha256'] == sha(CHECKER),
                'Actual build candidate/checker differs.')
    require(result['exitCode'] == 0 and layout['passed'] and
            result['requestSha256'] == layout['buildRequestSha256'] == sha(BUILD / 'request.json') and
            layout['buildResultSha256'] == sha(BUILD / 'build-result.json'), 'Successful build receipts differ.')
    features = {'CLR_CMAKE_TARGET_ARCH': 'x64', 'CLR_CMAKE_TARGET_OS': 'windows',
                'CMAKE_BUILD_TYPE': 'Release', 'FEATURE_INTERPRETER': '1', 'FEATURE_DYNAMIC_CODE_COMPILED': '1'}
    require(result['cmakeFeatures'] == features and result['cmakeCacheSha256'] == sha(cache),
            'Actual Release build configuration differs.')
    paths = {'build-request.json': BUILD / 'request.json', 'build-result.json': BUILD / 'build-result.json',
             'layout-receipt.json': BUILD / 'layout-receipt.json', 'CMakeCache.txt': cache,
             'native-commands.txt': BUILD / 'native-commands.txt', CHECKER.name: CHECKER,
             'build-candidate-checker.py': BUILD / CHECKER.name,
             'build.stdout': BUILD / 'build.stdout', 'build.stderr': BUILD / 'build.stderr'}
    require(result['sourceHashes'] == request['sourceHashes'] and len(request['sourceHashes']) == 36,
            'Complete runtime source inventory differs.')
    for relative, expected in request['sourceHashes'].items():
        source = BUILD / 'source' / relative
        require(sha(source) == sha(RUNTIME / relative) == expected, 'Built source differs: ' + relative)
        paths['runtime-source/' + relative] = source
    critical = ('coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll',
                'IL/System.Private.CoreLib.dll', 'x64/crossgen2/crossgen2.exe',
                'x64/crossgen2/clrjit_win_x64_x64.dll', 'x64/crossgen2/jitinterface_x64.dll')
    products = {relative: sha(product / relative) for relative in critical}
    require(products == result['criticalProductHashes'] == layout['criticalProductHashes'],
            'Actual native/CoreLib/compiler products differ.')
    expected_binding = {'version': 2, 'configuration': 'Release', 'cmakeFeatures': features,
                        'metadataHashes': {'provenance/' + name: sha(path) for name, path in paths.items()},
                        'criticalProductHashes': products, 'buildEvidencePath': str(BUILD),
                        'actualSourceCommit': COMMIT, 'candidateValidation': validation,
                        'candidateCheckerSha256': sha(CHECKER)}
    require(binding == expected_binding, 'Complete frozen build binding differs from actual products and provenance.')
    inputs = {path.resolve() for path in paths.values()}
    inputs.update((product / relative).resolve() for relative in critical)
    inputs.update((RUNTIME / relative).resolve() for relative in request['sourceHashes'])
    for relative, expected in layout['allLayoutHashes'].items():
        path = BUILD / 'layout' / relative
        require(sha(path) == expected, 'Actual runtime layout differs: ' + relative)
        inputs.add(path.resolve())
    return inputs

def source_inputs():
    inputs = set()
    for folder in ('benchmarks/RuneCLR.BudgetKernel', 'benchmarks/RuneCLR.BudgetOverhead',
                   'src/RuneCLR.Runtime', 'src/RuneCLR.Abstractions', 'src/RuneCLR.Packages'):
        base = ROOT / folder
        inputs.update(path for path in base.rglob('*') if path.suffix in ('.cs', '.csproj') and
                      not {'obj', 'bin'}.intersection(path.relative_to(base).parts))
    inputs.update(path for path in (ROOT / 'Directory.Build.props', ROOT / 'Directory.Build.targets',
                  ROOT / 'global.json', ROOT / 'NuGet.Config') if path.exists())
    inputs.update((Path(__file__).resolve(), LEGACY, CHECKER, ROOT / 'artifacts/toolchains/dotnet-11-rc1/dotnet.exe'))
    return inputs

def validate_live_build(witness):
    require(witness['candidateCommit'] == COMMIT and
            witness['buildResultSha256'] == sha(BUILD / 'build-result.json') and
            witness['layoutReceiptSha256'] == sha(BUILD / 'layout-receipt.json'),
            'Live witness belongs to a different runtime build.')
    bound = {Path(name).resolve(): expected for name, expected in witness['boundFiles'].items()}
    framework = BUILD / 'layout/shared/Microsoft.NETCore.App/12.0.0'
    inventory = {Path(name).as_posix(): expected for name, expected in
                 load(BUILD / 'layout-receipt.json')['allLayoutHashes'].items()}
    for name in ('coreclr.dll', 'coreclr.pdb', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll'):
        path = (framework / name).resolve()
        relative = path.relative_to((BUILD / 'layout').resolve()).as_posix()
        require(bound.get(path) == inventory[relative] == sha(path), 'Live native input differs: ' + name)

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
        require(profile['candidateCommit'] == COMMIT and profile['derivedLedgerValue'] == ('0' if label == 'off' else '1') and profile['phaseAcquireValue'] == '1',
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
            witness['corruptionControlsRejected'] >= 24 and not witness['benchmark'], 'Four live branch witnesses required.')
    require([(x['derivedFlag'], x['scenario']) for x in witness['lanes']] ==
            [(flag, scenario) for flag in (0, 1) for scenario in ('Good', 'TightLoop')], 'Live witness inventory differs.')
    require(witness['meterSize'] == 64 and witness['fieldOffsets'] ==
            {'derivedFlag': 3, 'initialExecutionLimit': 48, 'initialCleanupLimit': 56}, 'New native meter layout required.')
    require(all(lane['actualMeterFlag'] == lane['derivedFlag'] and lane['normalAdmittedBranchObserved'] and
                lane['rawCounterExpected'] and lane['ledgerVerified'] and lane['contextCollected']
                for lane in witness['lanes']), 'Actual admission/counter/getter observations required.')
    validate_live_build(witness)
    inputs.add(witness_path)
    for name, expected in witness['boundFiles'].items():
        path = Path(name)
        require(sha(path) == expected, 'Live witness bound input changed.')
        inputs.add(path)
    for name, key in (('audit-derived-ledger-windows-witness.py', 'auditorSha256'),
                      ('audit-derived-ledger-windows-witness-set.py', 'joinerSha256')):
        path = ROOT / 'eng' / name
        require(sha(path) == witness[key], 'Live witness auditor changed.')
        inputs.add(path)
    return inputs

def validate_preparation(directory, value=None):
    directory = Path(directory).resolve()
    value = load(directory / 'preparation.json') if value is None else value
    require(value['passed'] and value['candidateCommit'] == COMMIT and value['baselineCommit'] == BASELINE,
            'Pinned derived ledger benchmark candidate differs.')
    require(value['pairs'] == 4 and value['samplesPerProcess'] == 9 and value['affinity'] == 4 and
            value['configuration'] == 'Release' and value['functionalCommands'] == 16 and value['liveWitnesses'] == 4,
            'Frozen benchmark parameters/prerequisites differ.')
    require(value['derivedValues'] == ['0', '1'] and value['derivedLedgerSwitch'] == SWITCH and
            value['phaseAcquireValue'] == '1' and value['phaseAcquireSwitch'] == PHASE_SWITCH, 'Frozen switch contract differs.')
    require(value['runtime'] == str(RUNTIME.resolve()) and value['layout'] == str((BUILD / 'layout').resolve()) and
            value['buildEvidence'] == str(BUILD.resolve()), 'Frozen runtime/build/layout differs.')
    require(value['candidateValidation'] == module(CHECKER, 'derived_guard_candidate').validate(RUNTIME, COMMIT),
            'Exact source candidate changed.')
    require(value['runtimeBuildBinding']['actualSourceCommit'] == COMMIT and
            value['runtimeBuildBinding']['candidateValidation'] == value['candidateValidation'], 'Build candidate binding differs.')
    required_inputs = validate_build_binding(value['runtimeBuildBinding'], value['candidateValidation'])
    required_inputs.update(path.resolve() for path in prerequisites() | source_inputs())
    require(set(value['originalInputHashes']) == {str(path) for path in required_inputs},
            'Complete build, functional, live and author input inventory required.')
    required_snapshots = {'inputs/' + str(number) + '/' + path.name for number, path in
                          enumerate(sorted(required_inputs, key=str))}
    required_snapshots.update(value['runtimeBuildBinding']['metadataHashes'])
    require(set(value['snapshotHashes']) == required_snapshots, 'Complete frozen snapshot inventory required.')
    for number, path in enumerate(sorted(required_inputs, key=str)):
        relative = 'inputs/' + str(number) + '/' + path.name
        require(value['snapshotHashes'][relative] == value['originalInputHashes'][str(path)],
                'Frozen snapshot differs from its original input: ' + relative)
    require(all(value['snapshotHashes'][relative] == expected for relative, expected in
                value['runtimeBuildBinding']['metadataHashes'].items()), 'Frozen provenance inventory differs.')
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
    inputs.update(source_inputs())
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
             'functionalCommands': 16, 'liveWitnesses': 4, 'derivedValues': ['0', '1'], 'derivedLedgerSwitch': SWITCH,
             'phaseAcquireValue': '1', 'phaseAcquireSwitch': PHASE_SWITCH,
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
        'derived-switch': lambda x: x.__setitem__('derivedLedgerSwitch', PHASE_SWITCH),
        'phase-setting': lambda x: x.__setitem__('phaseAcquireValue', '0'),
        'derived-values': lambda x: x.__setitem__('derivedValues', ['1']),
        'layout': lambda x: x.__setitem__('layout', str(ROOT)),
        'build-candidate': lambda x: x['runtimeBuildBinding'].__setitem__('actualSourceCommit', BASELINE),
        'build-products': lambda x: x['runtimeBuildBinding']['criticalProductHashes'].__setitem__('coreclr.dll', '0' * 64),
        'build-features': lambda x: x['runtimeBuildBinding']['cmakeFeatures'].__setitem__('FEATURE_INTERPRETER', '0'),
        'build-metadata': lambda x: x['runtimeBuildBinding']['metadataHashes'].__setitem__('provenance/build-result.json', '0' * 64),
        'build-path': lambda x: x['runtimeBuildBinding'].__setitem__('buildEvidencePath', str(ROOT)),
        'original-omitted': lambda x: x['originalInputHashes'].clear(),
        'snapshots-omitted': lambda x: x['snapshotHashes'].clear(),
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
    def derived_command(argv, directory, label, settings=None):
        guard()
        settings = dict(settings or {})
        require(SWITCH not in settings or settings[SWITCH] == flag, 'Conflicting derived ledger setting.')
        settings[SWITCH] = flag
        require(PHASE_SWITCH not in settings or settings[PHASE_SWITCH] == '1', 'Phase load must stay enabled.')
        settings[PHASE_SWITCH] = '1'
        result = old_command(argv, directory, label, settings)
        guard()
        return result
    def derived_save(path, data):
        name = Path(path).name
        if name in ('request.json', 'results.json'):
            data.update({'derivedLedgerValue': int(flag), 'derivedLedgerSwitch': SWITCH,
                         'phaseAcquireValue': 1, 'phaseAcquireSwitch': PHASE_SWITCH,
                         'derivedBenchmarkPreparationSha256': preparation_hash,
                         'derivedBenchmarkAdapterSha256': value['adapterSha256'],
                         'legacyBenchmarkSha256': value['legacyBenchmarkSha256']})
        if name == 'request.json':
            shutil.copyfile(preparation / 'preparation.json', Path(path).parent / 'derived-benchmark-preparation.json')
            shutil.copyfile(__file__, Path(path).parent / 'derived-benchmark-adapter.py')
            shutil.copyfile(LEGACY, Path(path).parent / 'derived-legacy-benchmark.py')
        old_save(path, data)
    original.command, original.save = derived_command, derived_save
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
    measurement.add_argument('--derived-ledger', choices=('0', '1'), required=True)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.output)
    else:
        run(args.preparation, args.output, args.derived_ledger)

if __name__ == '__main__':
    main()
