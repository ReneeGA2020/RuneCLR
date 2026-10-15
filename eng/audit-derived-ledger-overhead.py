#!/usr/bin/env python3
"""Strict phase-candidate adapter for the unchanged raw benchmark auditor."""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / 'eng/budget-overhead-audit.py'
CHECKER = ROOT / 'eng/derived-ledger-runtime-candidate.py'
LEGACY_SHA = '6eafd60c29906f20a1d950f5b7ef22c99c2bdc54cc3d1b208c095c1a4eaba5ff'
CHECKER_SHA = 'd9ab9a5c9bcc78ef6c214864501ed1e930ac3f42d05770033235709dbc612380'
COMMIT = '29ff781e157be82ba5a398a60bb05291e4a865af'
SWITCH = 'DOTNET_RuneCLRDerivedLedger'
PHASE_SWITCH = 'DOTNET_RuneCLRPhaseAcquireLoad'
BENCHMARK = ROOT / 'eng/benchmark-derived-ledger-overhead.py'
BENCHMARK_SHA = 'e00eedab106d0b1ad7a4182f5a143eaf42e3e10377b9adc2c21676e8d0c31e8e'
PREPARATION = ROOT / 'artifacts/derived-ledger/windows-benchmark-preparation-20261014-attempt2'
ORIGINAL_CONTROLS = ('pid', 'entry-proof', 'dispatch-delta', 'raw-hash', 'pooled-percent',
                     'paired-percent', 'summary-count', 'scope', 'configuration-label',
                     'candidate-label', 'candidate-proof', 'candidate-checker')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def guard():
    assert sha(LEGACY) == LEGACY_SHA and sha(CHECKER) == CHECKER_SHA
    assert sha(BENCHMARK) == BENCHMARK_SHA
    legacy = module(LEGACY, 'derived_legacy_overhead_audit')
    checker = module(CHECKER, 'derived_overhead_exact_candidate')
    assert checker.COMMIT == COMMIT
    return legacy, checker


def verify_derived_binding(request, result, phase):
    assert type(phase) is int and phase in (0, 1)
    assert type(request['derivedLedgerValue']) is int and request['derivedLedgerValue'] == phase
    assert type(result['derivedLedgerValue']) is int and result['derivedLedgerValue'] == phase
    assert type(request['phaseAcquireValue']) is int and request['phaseAcquireValue'] == 1
    assert type(result['phaseAcquireValue']) is int and result['phaseAcquireValue'] == 1
    assert request['phaseAcquireSwitch'] == result['phaseAcquireSwitch'] == PHASE_SWITCH
    assert result['derivedLedgerSwitch'] == SWITCH
    assert request['derivedLedgerSwitch'] == SWITCH
    assert result['derivedBenchmarkPreparationSha256'] == request['derivedBenchmarkPreparationSha256']
    assert request['legacyBenchmarkSha256'] == 'a4613a272323c013ed148008007e815049a7f72664d130db5f1638dcb765c30f'
    assert request['configuration'] == result['configuration'] == 'Release'
    assert request['pairs'] == 4 and request['samplesPerProcess'] == 9
    expected = {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0',
                'DOTNET_ReadyToRun': '1', 'DOTNET_TieredCompilation': '0',
                'DOTNET_MULTILEVEL_LOOKUP': '0', SWITCH: str(phase), PHASE_SWITCH: '1'}
    assert len(result['lanes']) == 8
    for lane in result['lanes']:
        assert lane['raw']['settings'] == expected


def verify_preparation(directory, request):
    prepared = load(directory / 'derived-benchmark-preparation.json')
    assert sha(directory / 'derived-benchmark-preparation.json') == request['derivedBenchmarkPreparationSha256']
    assert sha(PREPARATION / 'preparation.json') == request['derivedBenchmarkPreparationSha256']
    assert sha(directory / 'derived-benchmark-adapter.py') == request['derivedBenchmarkAdapterSha256'] == sha(BENCHMARK)
    assert sha(directory / 'source/eng/benchmark-derived-ledger-overhead.py') == request['derivedBenchmarkAdapterSha256']
    assert sha(directory / 'derived-legacy-benchmark.py') == request['legacyBenchmarkSha256']
    assert prepared['passed'] and prepared['candidateCommit'] == COMMIT
    assert prepared['baselineCommit'] == 'a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186'
    assert prepared['configuration'] == 'Release' and prepared['pairs'] == 4 and prepared['samplesPerProcess'] == 9
    assert prepared['affinity'] == 4 and prepared['functionalCommands'] == 16 and prepared['liveWitnesses'] == 4
    assert prepared['phaseAcquireValue'] == '1' and prepared['phaseAcquireSwitch'] == PHASE_SWITCH
    assert prepared['derivedValues'] == ['0', '1'] and prepared['derivedLedgerSwitch'] == SWITCH
    assert prepared['adapterSha256'] == request['derivedBenchmarkAdapterSha256']
    assert prepared['legacyBenchmarkSha256'] == request['legacyBenchmarkSha256']
    assert prepared['candidateValidation'] == request['candidateValidation']
    assert prepared['runtimeBuildBinding'] == request['runtimeBuildBinding']
    assert prepared['runtime'] == request['runtime'] and prepared['layout'] == request['layout']
    for path, expected in prepared['originalInputHashes'].items():
        assert sha(path) == expected
    for relative, expected in prepared['snapshotHashes'].items():
        assert sha(PREPARATION / relative) == expected


def candidate_verifier(checker):
    def verify_candidate(directory, request, candidate_commit):
        assert candidate_commit == request['candidateCommit'] == COMMIT
        actual = checker.validate(Path(request['runtime']), candidate_commit)
        assert request['candidateValidation'] == actual and request['upstreamBase'] == checker.UPSTREAM
        assert request['candidateCheckerSha256'] == CHECKER_SHA
        for relative in ('source/eng/derived-ledger-runtime-candidate.py',
                         'provenance/derived-ledger-runtime-candidate.py', 'provenance/build-candidate-checker.py'):
            assert sha(directory / relative) == CHECKER_SHA
        binding = request['runtimeBuildBinding']
        assert binding['version'] == 2 and binding['candidateValidation'] == actual
        assert binding['candidateCheckerSha256'] == CHECKER_SHA
        for name, expected in actual['candidateSourceHashes'].items():
            source = directory / 'provenance/runtime-source' / name
            assert hashlib.sha256(source.read_bytes().replace(b'\r\n', b'\n')).hexdigest() == expected
        for filename in ('build-request.json', 'build-result.json', 'layout-receipt.json'):
            value = load(directory / 'provenance' / filename)
            assert value['candidateValidation'] == actual and value['candidateCheckerSha256'] == CHECKER_SHA
        layout = load(directory / 'provenance/layout-receipt.json')
        assert Path(layout['layout']).resolve() == Path(request['layout']).resolve()
        for relative, expected in layout['allLayoutHashes'].items():
            assert sha(Path(request['layout']) / relative) == expected
        for path, expected in request['runtimeHashes'].items():
            assert sha(path) == expected
        assert candidate_commit in request['runtimeProductStamp']
    return verify_candidate


def preparation(output):
    legacy, checker = guard()
    for path in (Path(__file__), LEGACY, CHECKER, BENCHMARK):
        ast.parse(path.read_text())
    assert all(repr(name) in LEGACY.read_text() for name in ORIGINAL_CONTROLS)
    rejected = []
    phase_rejected = []
    for phase in (0, 1):
        request = {'derivedLedgerValue': phase, 'derivedLedgerSwitch': SWITCH,
                   'phaseAcquireValue': 1, 'phaseAcquireSwitch': PHASE_SWITCH,
                   'derivedBenchmarkPreparationSha256': 'a' * 64, 'configuration': 'Release',
                   'legacyBenchmarkSha256': 'a4613a272323c013ed148008007e815049a7f72664d130db5f1638dcb765c30f',
                   'pairs': 4, 'samplesPerProcess': 9}
        settings = {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0', 'DOTNET_ReadyToRun': '1',
                    'DOTNET_TieredCompilation': '0', 'DOTNET_MULTILEVEL_LOOKUP': '0', SWITCH: str(phase), PHASE_SWITCH: '1'}
        result = {'derivedLedgerValue': phase, 'derivedLedgerSwitch': SWITCH, 'configuration': 'Release',
                  'phaseAcquireValue': 1, 'phaseAcquireSwitch': PHASE_SWITCH,
                  'derivedBenchmarkPreparationSha256': 'a' * 64,
                  'lanes': [{'raw': {'settings': dict(settings)}} for _ in range(8)]}
        verify_derived_binding(request, result, phase)
        changed = copy.deepcopy(result)
        changed['lanes'][0]['raw']['settings'][SWITCH] = str(1 - phase)
        try:
            verify_derived_binding(request, changed, phase)
        except AssertionError:
            rejected.append(phase)
        else:
            raise AssertionError('phase-environment substitution accepted')
        changed = copy.deepcopy(result)
        changed['lanes'][0]['raw']['settings'][PHASE_SWITCH] = '0'
        try:
            verify_derived_binding(request, changed, phase)
        except AssertionError:
            phase_rejected.append(phase)
        else:
            raise AssertionError('fixed-phase substitution accepted')
    report = {'passed': True, 'preparedOnly': True, 'runtimeExecuted': False, 'benchmarkAudited': False,
              'originalControlsRetained': list(ORIGINAL_CONTROLS), 'phaseEnvironmentGuardProfiles': [0, 1],
              'preparationSubstitutionControlsRejected': rejected, 'fixedPhaseControlsRejected': phase_rejected, 'astFiles': 4,
              'legacyAuditorSha256': LEGACY_SHA, 'phaseCheckerSha256': CHECKER_SHA,
              'benchmarkAdapterSha256': BENCHMARK_SHA,
              'adapterSha256': sha(Path(__file__)), 'scope': 'Preparation guards only; no benchmark/debugger/build'}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--derived-ledger', type=int, choices=(0, 1))
    parser.add_argument('--candidate-commit', default=COMMIT)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert not output.exists()
    if args.prepare_only:
        preparation(output)
        return
    assert args.evidence is not None and args.derived_ledger is not None and args.candidate_commit == COMMIT
    directory = args.evidence.resolve()
    legacy, checker = guard()
    legacy._candidate = checker
    legacy.CHECKER_PATH = CHECKER
    legacy.verify_candidate = candidate_verifier(checker)
    original_verify = legacy.verify
    verify_preparation(directory, load(directory / 'request.json'))

    def verify(directory, result, request_override=None, candidate_commit=COMMIT):
        request = request_override if request_override is not None else load(directory / 'request.json')
        verify_derived_binding(request, result, args.derived_ledger)
        return original_verify(directory, result, request_override, candidate_commit)

    legacy.verify = verify
    original_controls = output.with_name(output.stem + '-original-controls.json')
    assert not original_controls.exists()
    previous = sys.argv
    try:
        sys.argv = [str(LEGACY), '--evidence', str(directory), '--output', str(original_controls), '--candidate-commit', COMMIT]
        legacy.main()
    finally:
        sys.argv = previous
    frozen = load(original_controls)
    assert [control['name'] for control in frozen['corruptionControls']] == list(ORIGINAL_CONTROLS)
    request, result = load(directory / 'request.json'), load(directory / 'results.json')
    changed = copy.deepcopy(result)
    changed['lanes'][0]['raw']['settings'][SWITCH] = str(1 - args.derived_ledger)
    try:
        verify_derived_binding(request, changed, args.derived_ledger)
    except AssertionError:
        pass
    else:
        raise AssertionError('phase-environment substitution accepted')
    changed = copy.deepcopy(result)
    changed['lanes'][0]['raw']['settings'][PHASE_SWITCH] = '0'
    try:
        verify_derived_binding(request, changed, args.derived_ledger)
    except AssertionError:
        pass
    else:
        raise AssertionError('fixed-phase substitution accepted')
    review = dict(frozen)
    review.update({'assessorSha256': sha(Path(__file__)), 'derivedLedgerValue': args.derived_ledger,
                   'originalAuditorSha256': LEGACY_SHA, 'originalControlsReceiptSha256': sha(original_controls),
                   'corruptionControls': [*frozen['corruptionControls'], {'name': 'derived-environment-substitution', 'rejected': True},
                                          {'name': 'fixed-phase-substitution', 'rejected': True}]})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps(review, indent=2))


if __name__ == '__main__':
    main()
