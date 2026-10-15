#!/usr/bin/env python3
"""Synthetic controls for extra open-delegate checks; never execute author IL."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='ascii')


def fixture(root, reviewer):
    tools = root / 'source-freeze/eng'
    tools.mkdir(parents=True)
    for name in ('prepare-ios-device-author.py', 'prepare-ios-open-delegate-author.py'):
        shutil.copyfile(ROOT / name, tools / name)
    compiler = load('synthetic_open_compiler', tools / 'prepare-ios-open-delegate-author.py')
    capture = root / 'synthetic-capture'
    write(capture / 'run-results.json', {'syntheticOnly': True})
    compiled = capture / 'author-compilation-after-install'
    hashes = {}
    for role, relative in compiler.SOURCES.items():
        original = ROOT.parent / relative
        copied = root / 'bindings/author-sources' / (role + '.cs')
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, copied)
        source = compiled / 'source' / (role + '.cs')
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(compiler.variant_source(role, original.read_bytes()))
        hashes[role] = reviewer.sha(source)
        for suffix in ('rsp', 'stdout', 'stderr'):
            (compiled / (role + '.' + suffix)).write_text('Synthetic evidence only.\n', encoding='ascii')
        write(compiled / (role + '.process.json'), {'exitCode': 0,
              'responseSha256': reviewer.sha(compiled / (role + '.rsp')),
              'stdoutSha256': reviewer.sha(compiled / (role + '.stdout')),
              'stderrSha256': reviewer.sha(compiled / (role + '.stderr'))})
    shared = {'fixtureVariant': reviewer.VARIANT, 'baselineCompilerSha256': reviewer.BASE_COMPILER_SHA,
              'compiledSourceHashes': hashes}
    write(compiled / 'request.json', dict(shared, sourceHashes=reviewer.SOURCE_HASHES,
          inputManifestSha256=compiler.MANIFEST, targetsRerun=False))
    write(compiled / 'results.json', dict(shared, passed=True, authorCompilationCount=2,
          driverSha256=reviewer.COMPILER_SHA, authorIlOnly=True, authorExecuted=False,
          physicalDeviceExecuted=False))
    entries = [{'kind': kind, 'methodGroup': 'Synthetic.' + kind} for kind in sorted(reviewer.PATHS)]
    entries.append({'methodGroup': reviewer.CLOSURE, 'kind': 'delegate-child-dispatch',
                    'terminalPhase': 1, 'meterGate': {'phase': 1}, 'meterTerminated': True,
                    'instructionMeter': 1234, 'cleanupOwner': 1234})
    write(capture / 'diagnostic/interpreter-entries.json', entries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    reviewer = load('open_delegate_review_under_test', ROOT / 'review-ios-open-delegate-entry.py')
    checks = []
    with tempfile.TemporaryDirectory(prefix='runeclr-open-delegate-controls-') as temporary:
        root = Path(temporary)
        baseline = root / 'baseline'
        fixture(baseline, reviewer)
        reviewer.verify_extra(baseline)
        checks.append({'name': 'synthetic-extra-checks-baseline', 'passed': True})

        def check(name, relative, mutate, raw=False):
            altered = root / name
            shutil.copytree(baseline, altered)
            path = altered / relative
            value = path.read_bytes() if raw else reviewer.read(path)
            changed = mutate(copy.deepcopy(value))
            if raw:
                path.write_bytes(changed)
            else:
                write(path, changed)
            try:
                reviewer.verify_extra(altered)
            except (RuntimeError, KeyError, ValueError) as error:
                checks.append({'name': name, 'passed': True, 'corruptionRejected': True, 'reason': str(error)})
            else:
                raise AssertionError('Synthetic corruption accepted: ' + name)

        entries = 'synthetic-capture/diagnostic/interpreter-entries.json'
        compiler = 'synthetic-capture/author-compilation-after-install/'

        def closure_update(**values):
            def update(rows):
                rows[-1].update(values)
                return rows
            return update

        def remove_special(rows):
            for row in rows:
                if row['kind'] == 'delegate-child-dispatch':
                    row['kind'] = 'ordinary-child-dispatch'
            return rows

        check('missing-special-path', entries, remove_special)
        check('closure-wrong-path-with-three-other-paths', entries, closure_update(kind='ordinary-child-dispatch'))
        check('closure-execution-phase', entries, closure_update(terminalPhase=0))
        check('closure-meter-gate-phase', entries, closure_update(meterGate={'phase': 0}))
        check('closure-no-termination', entries, closure_update(meterTerminated=False))
        check('closure-wrong-cleanup-owner', entries, closure_update(cleanupOwner=5678))
        check('closure-zero-meter', entries, closure_update(instructionMeter=0, cleanupOwner=0))
        check('closure-missing', entries, lambda rows: rows[:-1])
        check('closure-duplicate', entries, lambda rows: rows + [rows[-1]])
        check('compiled-private-source-mutated', compiler + 'source/Private.cs', lambda data: data + b'// changed', raw=True)
        check('compiled-payload-source-mutated', compiler + 'source/Payload.cs', lambda data: data + b'// changed', raw=True)
        check('original-source-mutated', 'bindings/author-sources/Private.cs', lambda data: data + b'// changed', raw=True)
        check('variant-compiler-source-mutated', 'source-freeze/eng/prepare-ios-open-delegate-author.py', lambda data: data + b'# changed', raw=True)
        check('baseline-compiler-source-mutated', 'source-freeze/eng/prepare-ios-device-author.py', lambda data: data + b'# changed', raw=True)
        for name, field, value in (('variant-receipt-mutated', 'fixtureVariant', 'other'),
                                   ('compiler-receipt-mutated', 'driverSha256', '0' * 64),
                                   ('baseline-receipt-mutated', 'baselineCompilerSha256', '0' * 64),
                                   ('compiled-hashes-mutated', 'compiledSourceHashes', {}),
                                   ('compiler-executed-author', 'authorExecuted', True)):
            check(name, compiler + 'results.json', lambda receipt, field=field, value=value: dict(receipt, **{field: value}))
        check('source-manifest-mutated', compiler + 'request.json', lambda receipt: dict(receipt, sourceHashes={}))
        check('compiler-process-failure', compiler + 'Private.process.json', lambda receipt: dict(receipt, exitCode=1))
        check('compiler-log-mutated', compiler + 'Private.stdout', lambda data: data + b'changed', raw=True)
    result = {'passed': True, 'controls': len(checks), 'checks': checks, 'syntheticOnly': True,
              'scope': 'Extra open-delegate requirements only; not general archive review or actual execution.',
              'targetProcessCreated': False, 'physicalDeviceExecuted': False}
    if args.output:
        with args.output.open('x', encoding='ascii') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
