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
CHECKER = ROOT / 'eng/phase-load-runtime-candidate.py'
LEGACY_SHA = '6eafd60c29906f20a1d950f5b7ef22c99c2bdc54cc3d1b208c095c1a4eaba5ff'
CHECKER_SHA = '26e1aa4bb97d7bcfaa692a616945b2b848fa656d945893f91ff8346ace804976'
COMMIT = 'a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186'
SWITCH = 'DOTNET_RuneCLRPhaseAcquireLoad'
BENCHMARK = ROOT / 'eng/benchmark-phase-load-overhead.py'
BENCHMARK_SHA = '87506885bff5c07421f74e80c7f152cc07826c22ad286321395c7a15a15ad17b'
PREPARATION = ROOT / 'artifacts/phase-load/windows-benchmark-preparation-20261014-attempt1'
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
    legacy = module(LEGACY, 'phase_legacy_overhead_audit')
    checker = module(CHECKER, 'phase_overhead_exact_candidate')
    assert checker.COMMIT == COMMIT
    return legacy, checker


def verify_phase_binding(request, result, phase):
    assert type(phase) is int and phase in (0, 1)
    assert type(request['phaseAcquireValue']) is int and request['phaseAcquireValue'] == phase
    assert result['phaseAcquireValue'] == phase
    assert request['phaseAcquireSwitch'] == SWITCH
    assert result['phaseBenchmarkPreparationSha256'] == request['phaseBenchmarkPreparationSha256']
    assert request['legacyBenchmarkSha256'] == 'a4613a272323c013ed148008007e815049a7f72664d130db5f1638dcb765c30f'
    assert request['configuration'] == result['configuration'] == 'Release'
    assert request['pairs'] == 4 and request['samplesPerProcess'] == 9
    expected = {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0',
                'DOTNET_ReadyToRun': '1', 'DOTNET_TieredCompilation': '0',
                'DOTNET_MULTILEVEL_LOOKUP': '0', SWITCH: str(phase)}
    assert len(result['lanes']) == 8
    for lane in result['lanes']:
        assert lane['raw']['settings'] == expected


def verify_preparation(directory, request):
    prepared = load(directory / 'phase-benchmark-preparation.json')
    assert sha(directory / 'phase-benchmark-preparation.json') == request['phaseBenchmarkPreparationSha256']
    assert sha(PREPARATION / 'preparation.json') == request['phaseBenchmarkPreparationSha256']
    assert sha(directory / 'phase-benchmark-adapter.py') == request['phaseBenchmarkAdapterSha256'] == sha(BENCHMARK)
    assert sha(directory / 'source/eng/benchmark-phase-load-overhead.py') == request['phaseBenchmarkAdapterSha256']
    assert sha(directory / 'phase-legacy-benchmark.py') == request['legacyBenchmarkSha256']
    assert prepared['passed'] and prepared['candidateCommit'] == COMMIT
    assert prepared['baselineCommit'] == '20405f7ae23e183e038703aa5e356b3310fef427'
    assert prepared['configuration'] == 'Release' and prepared['pairs'] == 4 and prepared['samplesPerProcess'] == 9
    assert prepared['affinity'] == 4 and prepared['functionalCommands'] == 16 and prepared['liveWitnesses'] == 4
    assert prepared['phaseValues'] == ['0', '1'] and prepared['phaseAcquireSwitch'] == SWITCH
    assert prepared['adapterSha256'] == request['phaseBenchmarkAdapterSha256']
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
        for relative in ('source/eng/phase-load-runtime-candidate.py',
                         'provenance/phase-load-runtime-candidate.py', 'provenance/build-candidate-checker.py'):
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
    for phase in (0, 1):
        request = {'phaseAcquireValue': phase, 'phaseAcquireSwitch': SWITCH,
                   'phaseBenchmarkPreparationSha256': 'a' * 64, 'configuration': 'Release',
                   'legacyBenchmarkSha256': 'a4613a272323c013ed148008007e815049a7f72664d130db5f1638dcb765c30f',
                   'pairs': 4, 'samplesPerProcess': 9}
        settings = {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0', 'DOTNET_ReadyToRun': '1',
                    'DOTNET_TieredCompilation': '0', 'DOTNET_MULTILEVEL_LOOKUP': '0', SWITCH: str(phase)}
        result = {'phaseAcquireValue': phase, 'configuration': 'Release',
                  'phaseBenchmarkPreparationSha256': 'a' * 64,
                  'lanes': [{'raw': {'settings': dict(settings)}} for _ in range(8)]}
        verify_phase_binding(request, result, phase)
        changed = copy.deepcopy(result)
        changed['lanes'][0]['raw']['settings'][SWITCH] = str(1 - phase)
        try:
            verify_phase_binding(request, changed, phase)
        except AssertionError:
            rejected.append(phase)
        else:
            raise AssertionError('phase-environment substitution accepted')
    report = {'passed': True, 'preparedOnly': True, 'runtimeExecuted': False, 'benchmarkAudited': False,
              'originalControlsRetained': list(ORIGINAL_CONTROLS), 'phaseEnvironmentGuardProfiles': [0, 1],
              'preparationSubstitutionControlsRejected': rejected, 'astFiles': 4,
              'legacyAuditorSha256': LEGACY_SHA, 'phaseCheckerSha256': CHECKER_SHA,
              'benchmarkAdapterSha256': BENCHMARK_SHA,
              'adapterSha256': sha(Path(__file__)), 'scope': 'Preparation guards only; no benchmark/debugger/build'}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--phase-acquire', type=int, choices=(0, 1))
    parser.add_argument('--candidate-commit', default=COMMIT)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert not output.exists()
    if args.prepare_only:
        preparation(output)
        return
    assert args.evidence is not None and args.phase_acquire is not None and args.candidate_commit == COMMIT
    directory = args.evidence.resolve()
    legacy, checker = guard()
    legacy._candidate = checker
    legacy.CHECKER_PATH = CHECKER
    legacy.verify_candidate = candidate_verifier(checker)
    original_verify = legacy.verify
    verify_preparation(directory, load(directory / 'request.json'))

    def verify(directory, result, request_override=None, candidate_commit=COMMIT):
        request = request_override if request_override is not None else load(directory / 'request.json')
        verify_phase_binding(request, result, args.phase_acquire)
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
    changed['lanes'][0]['raw']['settings'][SWITCH] = str(1 - args.phase_acquire)
    try:
        verify_phase_binding(request, changed, args.phase_acquire)
    except AssertionError:
        pass
    else:
        raise AssertionError('phase-environment substitution accepted')
    review = dict(frozen)
    review.update({'assessorSha256': sha(Path(__file__)), 'phaseAcquireValue': args.phase_acquire,
                   'originalAuditorSha256': LEGACY_SHA, 'originalControlsReceiptSha256': sha(original_controls),
                   'corruptionControls': [*frozen['corruptionControls'], {'name': 'phase-environment-substitution', 'rejected': True}]})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps(review, indent=2))


if __name__ == '__main__':
    main()
