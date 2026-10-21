"""Orchestrate one offline verification and write a new report."""

import json
from pathlib import Path

from . import builder, replay
from .common import (ObservationError, OutputRefused, canonical_json, load_json,
                     need, same_path, sha256_bytes, sha256_file)
from .observations import check_gameplay


TOOL = 'eng/verify-trusted-game-observations.py'


def _observation_files(run_root, lanes):
    directory = run_root / 'observations'
    need(directory.is_dir(), 'observations-directory')
    paths = sorted(directory.glob('*.jsonl'))
    expected = {}
    for lane in lanes:
        for scenario, suffix in (('stageA', 'stage-A'), ('stageB', 'stage-B'),
                                 ('recoverB', 'recover-B')):
            expected[lane['lane'] + '-' + suffix + '.jsonl'] = (lane, scenario)
    need(len(paths) == 6, 'observation-file-count ' + str(len(paths)))
    need({path.name for path in paths} == set(expected), 'observation-file-names')
    parsed = {}
    for path in paths:
        from .observations import parse_observations
        try:
            text = path.read_text(encoding='utf-8')
        except OSError as error:
            raise ObservationError('observation-read ' + str(path) + ': ' + str(error))
        parsed[path] = parse_observations(text)
    for path, (lane, scenario) in expected.items():
        item = lane[scenario]
        need(same_path(item.get('obsPath'), directory / path),
             'observation-path ' + path)
        need(item.get('observations') == parsed[directory / path],
             'observation-embedding ' + path)
        need(len(parsed[directory / path]) == 6, 'observation-count ' + path)
    return paths, parsed


def _pin_specs(run_root, lanes, bindings, images, commands, preflight,
               observation_paths):
    specs = {}

    def add(path, category):
        key = str(Path(path))
        if key not in specs:
            specs[key] = category

    for name in ('lanes.json', 'bindings.json', 'images.json', 'commands.json',
                 'preflight.json', 'raw-log-hashes.json'):
        add(run_root / name, 'inputs')
    for name in ('checker-full.json', 'failure.json', 'parent.exit.txt'):
        path = run_root / name
        if path.is_file():
            add(path, 'inputs')
    for image in images.values():
        add(image['ilPath'], 'inputs')
        add(image['r2rPath'], 'inputs')
    for key in ('Host', 'A', 'B'):
        add(bindings[key]['method']['mapPath'], 'inputs')
    add(preflight['runtimeSeal']['files']['coreclr.dll']['framework'], 'inputs')
    add(run_root / 'leaf' / 'caller_leaf.dll', 'inputs')
    for name in ('A.signed.json', 'B.signed.json', 'demo.spki'):
        add(run_root / 'signing' / name, 'inputs')
    for lane in lanes:
        add(run_root / 'lanes' / lane['lane'] / 'receipt.json', 'inputs')
        for key in ('stagedA', 'stagedB', 'stagedRecover'):
            add(lane[key]['stagedPath'], 'inputs')
    for command in commands:
        add(command['stdout'], 'raw')
        add(command['stderr'], 'raw')
    for path in observation_paths:
        add(path, 'raw')
    return specs


def _pins(specs):
    result = {'inputs': {}, 'raw': {}}
    for path, category in sorted(specs.items()):
        result[category][path] = sha256_file(path)
    return result


def _historical(run_root, name):
    path = run_root / name
    if not path.is_file():
        return {'available': False, 'historical': True, 'recomputed': False,
                'source': None, 'sha256': None}
    data = load_json(path)
    result = {
        'available': True,
        'historical': True,
        'recomputed': False,
        'source': str(path),
        'sha256': sha256_file(path),
    }
    if isinstance(data, dict):
        for key in ('passed', 'error', 'at'):
            if key in data:
                result[key] = data[key]
    return result


def _pins_report(before, after):
    report = {'inputs': {}, 'raw': {}, 'allUnchanged': before == after}
    for category in ('inputs', 'raw'):
        for path, digest in before[category].items():
            report[category][path] = {
                'before': digest,
                'after': after[category][path],
                'unchanged': digest == after[category][path],
            }
    return report


def verify_run(run_root, output):
    run_root = Path(run_root).resolve()
    output = Path(output).resolve()
    need(run_root.is_dir(), 'run-root-missing ' + str(run_root))
    if output.exists():
        raise OutputRefused('output-exists ' + str(output))
    if output == run_root or run_root in output.parents:
        raise OutputRefused('output-inside-run-root ' + str(output))

    lanes = load_json(run_root / 'lanes.json')
    bindings = load_json(run_root / 'bindings.json')
    images = load_json(run_root / 'images.json')
    commands = load_json(run_root / 'commands.json')
    preflight = load_json(run_root / 'preflight.json')
    raw_logs = load_json(run_root / 'raw-log-hashes.json')
    observation_paths, parsed = _observation_files(run_root, lanes)
    records = []
    for path in observation_paths:
        records.extend(parsed[path])

    specs = _pin_specs(run_root, lanes, bindings, images, commands, preflight,
                       observation_paths)
    before = _pins(specs)

    expected = builder.build_expected(lanes, bindings, images, commands, preflight,
                                      raw_logs, run_root)
    runtime_file = preflight['runtimeSeal']['files']['coreclr.dll']
    runtime_path = runtime_file['framework']
    runtime_sha = str(runtime_file['frameworkSha']).lower()
    result = replay.replay(records, expected, bindings, runtime_path, runtime_sha)

    facts = []
    for lane in lanes:
        for scenario, version, multiplier in (
            ('stageA', 'game-rules-a', 1),
            ('stageB', 'game-rules-b', 2),
            ('recoverB', 'game-rules-b', 2),
        ):
            check_gameplay(lane[scenario]['text'], multiplier)
            facts.append({'lane': lane['lane'], 'scenario': scenario, 'ok': True,
                          'version': version, 'multiplier': multiplier})

    after = _pins(specs)
    need(before == after, 'input-mutated')
    checker = _historical(run_root, 'checker-full.json')
    parent = _historical(run_root, 'failure.json')
    parent_exit = run_root / 'parent.exit.txt'
    if parent_exit.is_file():
        try:
            parent['exitCode'] = int(parent_exit.read_text(encoding='utf-8').strip())
        except ValueError:
            raise ObservationError('parent-exit-integer')

    expected_sha = sha256_bytes(canonical_json(expected).encode('utf-8'))
    report = {
        'schema': 'runeclr-trusted-game-observations/1',
        'tool': TOOL,
        'runRoot': str(run_root),
        'expected': {
            'sha256': expected_sha,
            'callCount': expected['counts']['calls'],
            'lanes': [lane['lane'] for lane in lanes],
            'scenarios': expected['scenarios'],
            'roles': expected['roles'],
            'lineage': expected['lineage'],
            'calls': expected['calls'],
        },
        'observations': {
            'files': [{'path': str(path), 'sha256': sha256_file(path),
                       'records': len(parsed[path])}
                      for path in observation_paths],
            'recordCount': len(records),
            'embeddedObservationsMatch': True,
            'targetImageBindings': result['targetImageBindings'],
            'runtimeImageObservations': result['runtimeImageObservations'],
        },
        'currentObservationChecks': result['currentObservationChecks'],
        'checks': {
            'derivedExpectedFromRunRoot': True,
            'commandsBound': True,
            'imagesBound': True,
            'mapsBound': True,
            'peMetadataBound': True,
            'receiptsBound': True,
            'rawLogsBound': True,
            'observationsBound': True,
            'targetImageChecks': result['currentObservationChecks']['passed'],
            'runtimeImageChecks': True,
            'factsGameplayValidated': True,
            'inputsUnchanged': True,
            'observationChecksPassed': result['currentObservationChecks']['passed'],
        },
        'acceptance': {
            'overallAcceptance': False,
            'originalPolicyPassed': checker.get('passed'),
            'originalPolicyRecomputed': False,
            'interpreterIdentityProven': False,
            'targetMethodBodyProven': False,
            'runtimeImageObservationIsInterpreterProof': False,
            'reason': 'Current checks are image/interval observations only; '
                      'overall acceptance stays false.',
        },
        'originalPolicy': checker,
        'historicalParent': parent,
        'facts': facts,
        'runtimeImage': result['runtimeImage'],
        'pins': _pins_report(before, after),
        'limitations': [
            'Expected calls are derived from this retained run root each invocation; '
            'the tool does not independently establish how that root was produced.',
            'Target-image bindings prove PC membership in the named method interval, '
            'an executable section and a RUNTIME_FUNCTION; they do not prove which '
            'method body executed or R2R versus interpreter selection.',
            'Runtime-image observations prove only that the PC lies in an executable '
            'section of the sealed coreclr.dll image; they are not method, nonimage '
            'or interpreter identity proof.',
            'The original checker and parent failures are historical values read from '
            'checker-full.json, failure.json and parent.exit.txt; they are not '
            'recomputed or promoted to new acceptance.',
            'Receipt checks compare the receipt document with the captured B signed '
            'bytes and compare payload fields with the staged manifest. No signature '
            'cryptography is performed.',
            'The stage-A receipt is superseded by the stage-B receipt; only its '
            'recorded hash is checked, not a retained A receipt document.',
            'The preflight-recorded dotnet.exe sha256 is not verified against the '
            'file; the dotnet path remains an external pin.',
            'The Publisher DLL and SDK/private dotnet.exe bytes are not hashed; '
            'their argv paths, command lifecycle and raw logs are bound instead.',
            'Only coreclr.dll framework bytes are hashed. The preflight checked '
            'coreclr/clrinterpreter/clrjit/CoreLib paths and the checked-build '
            'files other than coreclr.dll are not opened.',
            'Contracts and RuneCLR.TrustedUpdate are bound by actual IL/R2R SHA-256 '
            'and MVID; they have no target method bindings.',
            'Publish and assembly-identities commands are bound by names, argv paths, '
            'lifecycle, logs and raw hashes; their products are not re-run and the '
            'assembly-identities JSON content is not re-parsed.',
            'The signing private key is not opened, read, hashed or included in the '
            'pin set, and the signing directory is not recursively traversed.',
            'No product, build, crossgen, signing, Host, Publisher, private CLR, '
            'device or remote execution is performed.',
        ],
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True)
    report_path = output / 'report.json'
    report_bytes = (json.dumps(report, indent=1, ensure_ascii=False) + '\n').encode('utf-8')
    report_path.write_bytes(report_bytes)
    digest = sha256_bytes(report_bytes)
    sha_path = output / 'report.sha256'
    sha_path.write_text(digest + '  report.json\n', encoding='ascii')
    need(sha256_file(report_path) == digest, 'report-sha')
    return {
        'report': str(report_path),
        'reportSha256': digest,
        'sha256File': str(sha_path),
        'targetImageBindings': result['targetImageBindings'],
        'runtimeImageObservations': result['runtimeImageObservations'],
        'overallAcceptance': False,
        'observationChecksPassed': result['currentObservationChecks']['passed'],
        'originalPolicyPassed': checker.get('passed'),
    }
