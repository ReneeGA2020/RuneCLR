"""Derive the expected call set from one retained run root.

Every value used by replay is rebuilt here from the actual commands, images,
maps, PE metadata, signed documents and receipts in this invocation. There is
no accepted external expected-file input.
"""

import base64
from pathlib import Path

from . import pe
from .common import (ObservationError, is_sha256, load_json, need, parse_json,
                     same_path, sha256_bytes, sha256_file)
from .observations import check_caller_line, check_facts, parse_signed_facts


SCENARIOS = (
    ('stageA', 'stagedA', 'game-rules-a', 'A', 'A.signed.json', 'stage-A'),
    ('stageB', 'stagedB', 'game-rules-b', 'B', 'B.signed.json', 'stage-B'),
    ('recoverB', 'stagedRecover', 'game-rules-b', 'B', 'B.signed.json', 'recover-B'),
)

COMMAND_FIELDS = {
    'name', 'argv', 'cwd', 'settings', 'startStatus', 'startedUtc', 'stdout',
    'stderr', 'pid', 'timedOut', 'exitCode', 'endedStatus', 'endedUtc',
    'stdoutBytes', 'stderrBytes',
}

LANE_NAMES = ('r2r0', 'r2r1')


def _need_sha(value, label):
    need(is_sha256(value), 'sha256 ' + label + ' ' + repr(value))
    return str(value).lower()


def _argv_value(argv, name, label):
    indices = [index for index, item in enumerate(argv) if item == name]
    need(len(indices) == 1, 'argv-option-count ' + label + ' ' + name)
    index = indices[0]
    need(index + 1 < len(argv), 'argv-option-value ' + label + ' ' + name)
    return argv[index + 1]


def _signed_document(path):
    try:
        document = Path(path).read_bytes()
    except OSError as error:
        raise ObservationError('signed-read ' + str(path) + ': ' + str(error))
    lines = document.splitlines()
    need(len(lines) >= 3 and lines[0] == b'RTRSIG1', 'signed-envelope ' + str(path))
    try:
        payload = parse_json(b'\n'.join(lines[2:]).decode('utf-8'),
                             str(path) + ':payload')
    except UnicodeDecodeError as error:
        raise ObservationError('signed-payload-utf8 ' + str(path) + ': ' + str(error))
    return document, payload


def validate_receipt(receipt_path, signed_document, manifest, content_root):
    receipt = load_json(receipt_path)
    need(receipt.get('v') == 1, 'receipt-version ' + str(receipt_path))
    need(receipt.get('contentRoot') == content_root, 'receipt-content')
    document = receipt.get('document')
    need(isinstance(document, str), 'receipt-document-type')
    try:
        decoded = base64.b64decode(document.encode('ascii'), validate=True)
    except Exception as error:
        raise ObservationError('receipt-document-base64: ' + str(error))
    need(decoded == signed_document, 'receipt-document')
    lines = decoded.splitlines()
    need(len(lines) >= 3 and lines[0] == b'RTRSIG1', 'receipt-envelope')
    try:
        payload = parse_json(b'\n'.join(lines[2:]).decode('utf-8'),
                             str(receipt_path) + ':payload')
    except UnicodeDecodeError as error:
        raise ObservationError('receipt-payload-utf8: ' + str(error))
    need(payload == manifest, 'receipt-payload')


def _validate_command(command, run_root, raw_logs):
    need(isinstance(command, dict), 'command-type')
    need(set(command) == COMMAND_FIELDS,
         'command-fields ' + repr(sorted(set(command) ^ COMMAND_FIELDS)))
    name = command.get('name')
    need(isinstance(name, str) and name, 'command-name ' + repr(name))
    argv = command.get('argv')
    need(isinstance(argv, list) and argv and
         all(isinstance(item, str) and item for item in argv),
         'command-argv ' + name)
    need(isinstance(command.get('settings'), dict), 'command-settings ' + name)
    need(same_path(command.get('cwd'), run_root), 'command-cwd ' + name)
    need(command.get('startStatus') == 'started', 'command-start ' + name)
    need(command.get('endedStatus') == 'exited', 'command-end ' + name)
    need(command.get('timedOut') is False, 'command-timeout ' + name)
    need(type(command.get('exitCode')) is int and command['exitCode'] == 0,
         'command-exit ' + name + ' ' + repr(command.get('exitCode')))
    need(type(command.get('pid')) is int and command['pid'] > 0, 'command-pid ' + name)
    need(isinstance(command.get('startedUtc'), str) and command['startedUtc'],
         'command-started ' + name)
    need(isinstance(command.get('endedUtc'), str) and command['endedUtc'],
         'command-ended ' + name)
    need(isinstance(command.get('stdout'), str) and command['stdout'],
         'stdout-path ' + name)
    need(isinstance(command.get('stderr'), str) and command['stderr'],
         'stderr-path ' + name)
    stdout_path = Path(command['stdout'])
    stderr_path = Path(command['stderr'])
    need(stdout_path.is_file(), 'stdout-missing ' + name)
    need(stderr_path.is_file(), 'stderr-missing ' + name)
    stdout = stdout_path.read_bytes()
    stderr = stderr_path.read_bytes()
    need(type(command.get('stdoutBytes')) is int and command['stdoutBytes'] == len(stdout),
         'stdout-bytes ' + name)
    need(type(command.get('stderrBytes')) is int and command['stderrBytes'] == len(stderr),
         'stderr-bytes ' + name)
    need(_need_sha(raw_logs.get(str(stdout_path)), 'raw-stdout ' + name) ==
         sha256_bytes(stdout), 'stdout-index ' + name)
    need(_need_sha(raw_logs.get(str(stderr_path)), 'raw-stderr ' + name) ==
         sha256_bytes(stderr), 'stderr-index ' + name)
    return stdout, stderr


def _validate_publish(command, run_root, key, image, signed_path, spki_path, version):
    argv = command['argv']
    need(Path(argv[0]).name.lower() in ('dotnet', 'dotnet.exe'), 'publish-dotnet ' + key)
    module = image['r2rPath']
    need(same_path(_argv_value(argv, '--module', key), module), 'publish-module ' + key)
    need(_argv_value(argv, '--version', key) == version, 'publish-version ' + key)
    need(_argv_value(argv, '--entry-type', key) == 'TrustedGame.Update.GameRules',
         'publish-entry-type ' + key)
    need(_argv_value(argv, '--entry-method', key) == 'Entry', 'publish-entry-method ' + key)
    need(same_path(_argv_value(argv, '--signed', key), signed_path), 'publish-signed ' + key)
    need(same_path(_argv_value(argv, '--spki', key), spki_path), 'publish-spki ' + key)
    need(same_path(_argv_value(argv, '--content-root', key), Path(module).parent),
         'publish-content-root ' + key)
    need(_argv_value(argv, '--runtime', key) == 'net11.0', 'publish-runtime ' + key)
    need(_argv_value(argv, '--architecture', key) == 'x64',
         'publish-architecture ' + key)
    need(same_path(_argv_value(argv, '--private-key', key),
                   run_root / 'signing' / 'demo.private.pem'), 'publish-key-path ' + key)
    need(command['settings'] == {}, 'publish-settings ' + key)


def _validate_assembly_identities(command, images):
    argv = command['argv']
    need(len(argv) >= 4, 'assembly-argv')
    need(argv[1] == '-NoProfile' and argv[2] == '-Command', 'assembly-argv-prefix')
    script = argv[3]
    paths = [images[key]['r2rPath'] for key in
             ('Host', 'Contracts', 'TrustedUpdate', 'A', 'B')]
    paths += [images[key]['ilPath'] for key in ('A', 'B')]
    for path in paths:
        need(str(Path(path)) in script, 'assembly-path ' + str(path))
    need(command['settings'] == {}, 'assembly-settings')


def _validate_manifest(manifest, version, entry_path, staged_sha, label):
    need(isinstance(manifest, dict), 'manifest-type ' + label)
    need(manifest.get('formatVersion') == 1, 'manifest-format ' + label)
    need(manifest.get('version') == version, 'manifest-version ' + label)
    need(manifest.get('runtime') == 'net11.0', 'manifest-runtime ' + label)
    need(manifest.get('architecture') == 'x64', 'manifest-architecture ' + label)
    need(manifest.get('entryType') == 'TrustedGame.Update.GameRules',
         'manifest-entry-type ' + label)
    need(manifest.get('entryMethod') == 'Entry', 'manifest-entry-method ' + label)
    need(manifest.get('entryPath') == entry_path, 'manifest-entry-path ' + label)
    files = manifest.get('files')
    need(isinstance(files, list) and len(files) == 1, 'manifest-files ' + label)
    need(files[0] == {'path': entry_path, 'sha256': staged_sha},
         'manifest-file ' + label)


def _validate_images(images):
    need(isinstance(images, dict), 'images-type')
    need(set(images) == {'Host', 'Contracts', 'TrustedUpdate', 'A', 'B'},
         'images-keys')
    for key, image in images.items():
        need(isinstance(image, dict), 'image-type ' + key)
        need(image.get('r2r') is True and image.get('ilR2R') is False,
             'image-kinds ' + key)
        for path_key in ('ilPath', 'r2rPath'):
            need(isinstance(image.get(path_key), str) and image[path_key],
                 'image-path ' + key + ' ' + path_key)
            need(Path(image[path_key]).is_file(),
                 'image-missing ' + key + ' ' + path_key)
        _need_sha(image.get('ilSha'), 'image-il-sha ' + key)
        _need_sha(image.get('r2rSha'), 'image-r2r-sha ' + key)
        need(image['ilSha'].lower() == sha256_file(image['ilPath']),
             'image-il-file-sha ' + key)
        need(image['r2rSha'].lower() == sha256_file(image['r2rPath']),
             'image-r2r-file-sha ' + key)
        need(pe.mvid(image['ilPath']).lower() == str(image.get('ilMvid')).lower(),
             'image-il-mvid ' + key)
        need(pe.mvid(image['r2rPath']).lower() == str(image.get('r2rMvid')).lower(),
             'image-r2r-mvid ' + key)
    need(len({str(image['r2rMvid']).lower() for image in images.values()}) == 5,
         'image-mvid-distinct')


def _validate_bindings(bindings, images):
    need(isinstance(bindings, dict), 'bindings-type')
    need(set(bindings) == {'Host', 'A', 'B'}, 'bindings-keys')
    for key, binding in bindings.items():
        need(isinstance(binding, dict), 'binding-type ' + key)
        need(set(binding) >= {'path', 'sha256', 'method', 'executableSections',
                              'runtimeFunctions'}, 'binding-fields ' + key)
        image = images[key]
        need(same_path(binding.get('path'), image['r2rPath']), 'image-path ' + key)
        need(_need_sha(binding.get('sha256'), 'binding-sha ' + key) ==
             image['r2rSha'].lower(), 'image-binding-sha ' + key)
        method = binding.get('method')
        need(isinstance(method, dict), 'method-type ' + key)
        need(set(method) >= {'symbol', 'rva', 'length', 'section', 'mapPath', 'mapSha'},
             'method-fields ' + key)
        need(isinstance(method.get('symbol'), str) and method['symbol'],
             'method-symbol ' + key)
        need(type(method.get('rva')) is int and method['rva'] >= 0,
             'method-rva ' + key)
        need(type(method.get('length')) is int and method['length'] > 0,
             'method-length ' + key)
        need(Path(method.get('mapPath', '')).is_file(), 'map-missing ' + key)
        need(_need_sha(method.get('mapSha'), 'map-sha ' + key) ==
             sha256_file(method['mapPath']), 'map-file-sha ' + key)
        row = pe.map_method(method['mapPath'], method['symbol'])
        need(row['rva'] == method['rva'] and row['length'] == method['length'] and
             row['section'] == method.get('section'), 'map-method ' + key)
        sections = pe.executable_sections(image['r2rPath'])
        need(binding.get('executableSections') == sections,
             'executable-sections ' + key)
        runtime_functions = pe.pdata(image['r2rPath'])
        need(binding.get('runtimeFunctions') == runtime_functions,
             'runtime-functions ' + key)
        section = next((item for item in sections
                        if item['name'] == method['section'] and
                        item['va'] <= method['rva'] and
                        method['rva'] + method['length'] <= item['va'] + item['size']),
                       None)
        need(section is not None, 'method-section ' + key)
        need(any(item['begin'] <= method['rva'] and
                 method['rva'] + method['length'] <= item['end']
                 for item in runtime_functions), 'runtime-function-method ' + key)


def _validate_preflight(preflight):
    need(isinstance(preflight, dict), 'preflight-type')
    need(isinstance(preflight.get('framework'), str) and preflight['framework'],
         'preflight-framework')
    need(isinstance(preflight.get('layout'), str) and preflight['layout'],
         'preflight-layout')
    seal = preflight.get('runtimeSeal')
    need(isinstance(seal, dict), 'preflight-seal')
    dotnet = seal.get('layoutDotnet')
    need(isinstance(dotnet, dict) and isinstance(dotnet.get('path'), str),
         'preflight-dotnet')
    _need_sha(dotnet.get('sha256'), 'preflight-dotnet-sha')
    files = seal.get('files')
    need(isinstance(files, dict), 'preflight-files')
    coreclr = files.get('coreclr.dll')
    need(isinstance(coreclr, dict), 'preflight-coreclr')
    need(isinstance(coreclr.get('framework'), str) and coreclr['framework'],
         'preflight-coreclr-path')
    for field in ('frameworkSha', 'checkedSha', 'expected'):
        _need_sha(coreclr.get(field), 'preflight-coreclr-' + field)
    need(coreclr['frameworkSha'].lower() == coreclr['checkedSha'].lower() ==
         coreclr['expected'].lower(), 'preflight-coreclr-hashes')
    need(Path(coreclr['framework']).is_file(), 'coreclr-missing')
    need(coreclr['frameworkSha'].lower() == sha256_file(coreclr['framework']),
         'coreclr-file-sha')
    need(same_path(Path(coreclr['framework']).parent, preflight['framework']),
         'coreclr-framework-parent')
    return coreclr


def build_expected(lanes, bindings, images, commands, preflight, raw_logs, run_root):
    run_root = Path(run_root).resolve()
    need(isinstance(lanes, list) and len(lanes) == 2, 'lanes-count')
    need(isinstance(commands, list), 'commands-type')
    need(isinstance(raw_logs, dict), 'raw-logs-type')
    _validate_images(images)
    _validate_bindings(bindings, images)
    coreclr = _validate_preflight(preflight)

    names = [item.get('name') if isinstance(item, dict) else None
             for item in commands]
    need(all(isinstance(name, str) and name for name in names), 'command-names')
    need(len(names) == 9 and len(set(names)) == 9, 'duplicate-command-name')
    expected_names = {lane + '-' + suffix for lane in LANE_NAMES
                      for suffix in ('stage-A', 'stage-B', 'recover-B')}
    expected_names |= {'assembly-identities', 'publish-A', 'publish-B'}
    need(set(names) == expected_names,
         'command-name-set ' + repr(sorted(set(names))))
    command_by_name = {item['name']: item for item in commands}
    for item in commands:
        _validate_command(item, run_root, raw_logs)
    need(len({item['pid'] for item in commands}) == 9, 'command-pid-distinct')
    expected_raw = set()
    for item in commands:
        expected_raw.add(str(Path(item['stdout'])))
        expected_raw.add(str(Path(item['stderr'])))
    need(set(raw_logs) == expected_raw, 'raw-log-inventory')

    a_signed = run_root / 'signing' / 'A.signed.json'
    b_signed = run_root / 'signing' / 'B.signed.json'
    spki = run_root / 'signing' / 'demo.spki'
    _a_document, a_payload = _signed_document(a_signed)
    b_document, b_payload = _signed_document(b_signed)
    need(spki.is_file(), 'spki-missing')

    _validate_publish(command_by_name['publish-A'], run_root, 'A', images['A'],
                      a_signed, spki, 'game-rules-a')
    _validate_publish(command_by_name['publish-B'], run_root, 'B', images['B'],
                      b_signed, spki, 'game-rules-b')
    _validate_assembly_identities(command_by_name['assembly-identities'], images)

    leaf_path = run_root / 'leaf' / 'caller_leaf.dll'
    need(leaf_path.is_file(), 'leaf-missing')
    leaf_sha = sha256_file(leaf_path)

    framework_version = Path(preflight['framework']).name
    dotnet = preflight['runtimeSeal']['layoutDotnet']['path']
    host_path = str(Path(images['Host']['r2rPath']).resolve())
    calls = []
    pids = set()
    seen_lanes = set()
    lineage_receipts = {}
    for lane in lanes:
        need(isinstance(lane, dict), 'lane-type')
        lane_name = lane.get('lane')
        need(lane_name in LANE_NAMES and lane_name not in seen_lanes, 'lane')
        seen_lanes.add(lane_name)
        need(isinstance(lane.get('readyToRun'), bool), 'readyToRun')
        ready = '1' if lane['readyToRun'] else '0'
        expected_settings = {
            'DOTNET_ROOT': preflight['layout'], 'DOTNET_ReadyToRun': ready,
            'DOTNET_InterpMode': '1', 'DOTNET_TieredCompilation': '0',
            'DOTNET_TC_QuickJit': '0', 'DOTNET_TC_OnStackReplacement': '0',
            'DOTNET_MULTILEVEL_LOOKUP': '0', 'DOTNET_ROLL_FORWARD': 'Disable',
            'TRUSTED_GAME_OBSERVE': '1', 'RUNECLR_CALLER_LEAF': str(leaf_path),
        }
        need((lane.get('settings') or {}) == expected_settings,
             'lane-settings ' + lane_name)
        for receipt_key in ('receiptA', 'receiptB', 'receiptRecover'):
            _need_sha(lane.get(receipt_key), 'lane-' + receipt_key + ' ' + lane_name)
        need(lane['receiptRecover'] == lane['receiptB'],
             'receipt-recover ' + lane_name)
        need(lane['receiptA'] != lane['receiptB'],
             'receipt-superseded ' + lane_name)
        staged_a = lane.get('stagedA') or {}
        staged_b = lane.get('stagedB') or {}
        need(_need_sha(staged_a.get('receiptSha'), 'staged-a-receipt ' + lane_name) ==
             str(lane['receiptA']).lower(), 'receipt-a ' + lane_name)
        need(_need_sha(staged_b.get('receiptSha'), 'staged-b-receipt ' + lane_name) ==
             str(lane['receiptB']).lower(), 'receipt-b ' + lane_name)
        need(_need_sha((lane.get('stagedRecover') or {}).get('receiptSha'),
                       'staged-recover-receipt ' + lane_name) ==
             str(lane['receiptRecover']).lower(),
             'receipt-recover-staged ' + lane_name)
        need(a_payload == staged_a.get('manifest'), 'signed-a-payload ' + lane_name)
        need(b_payload == staged_b.get('manifest'), 'signed-b-payload ' + lane_name)
        lineage_receipts[lane_name] = {
            'a': lane['receiptA'], 'b': lane['receiptB'],
            'recover': lane['receiptRecover'],
        }
        for scenario_name, staged_key, version, method_key, signed_name, suffix in SCENARIOS:
            scenario = lane.get(scenario_name)
            staged = lane.get(staged_key)
            need(isinstance(scenario, dict) and isinstance(staged, dict),
                 'scenario/staged ' + lane_name + '/' + scenario_name)
            need({'name', 'record', 'text', 'fields', 'obsPath', 'observations'} <=
                 set(scenario), 'scenario-fields ' + scenario_name)
            need({'receiptSha', 'contentRoot', 'entryPath', 'stagedPath',
                  'stagedSha', 'manifest'} <= set(staged),
                 'staged-fields ' + staged_key)
            expected_name = lane_name + '-' + suffix
            need(scenario.get('name') == expected_name,
                 'scenario-name-embedded ' + expected_name)
            record = scenario.get('record') or {}
            need(isinstance(record, dict), 'record-type ' + expected_name)
            need(set(record) == COMMAND_FIELDS,
                 'record-fields ' + expected_name + ' ' +
                 repr(sorted(set(record) ^ COMMAND_FIELDS)))
            need(record.get('name') == expected_name,
                 'scenario-name ' + str(record.get('name')))
            command = command_by_name.get(expected_name)
            need(isinstance(command, dict), 'command-missing ' + expected_name)
            for field in COMMAND_FIELDS:
                need(record.get(field) == command.get(field),
                     'record-command ' + field + ' ' + expected_name)
            need(type(record.get('pid')) is int and record['pid'] > 0,
                 'pid ' + expected_name)
            need(record['pid'] not in pids, 'pid-duplicate ' + expected_name)
            pids.add(record['pid'])
            need(record.get('startStatus') == 'started' and
                 record.get('endedStatus') == 'exited', 'lifecycle ' + expected_name)
            need(type(record.get('exitCode')) is int and record['exitCode'] == 0 and
                 record.get('timedOut') is False, 'exit ' + expected_name)
            need(same_path(record.get('cwd'), run_root), 'cwd ' + expected_name)
            need(record.get('settings') == expected_settings,
                 'settings ' + expected_name)
            need(isinstance(scenario.get('text'), str), 'scenario-text ' + expected_name)
            parsed_fields = parse_signed_facts(scenario['text'])
            need(parsed_fields == scenario.get('fields'),
                 'scenario-fields-embedding ' + expected_name)
            mode = 'recover' if scenario_name == 'recoverB' else 'stage'
            source = 'LastKnownGood' if mode == 'recover' else 'Candidate'
            multiplier = 2 if version == 'game-rules-b' else 1
            check_facts(parsed_fields, mode, version, multiplier, source)
            releases = str(run_root / 'lanes' / lane_name / 'releases')
            receipt = str(run_root / 'lanes' / lane_name / 'receipt.json')
            signed = str(run_root / 'signing' / signed_name)
            if mode == 'stage':
                expected_argv = [
                    dotnet, 'exec', '--fx-version', framework_version,
                    host_path, '--stage-signed',
                    str(Path(images[method_key]['r2rPath']).parent),
                    '--signed', signed, '--spki', str(spki),
                    '--releases-root', releases, '--receipt', receipt,
                    '--expected-score-multiplier', str(multiplier)]
            else:
                expected_argv = [
                    dotnet, 'exec', '--fx-version', framework_version,
                    host_path, '--recover-signed', '--spki', str(spki),
                    '--releases-root', releases, '--receipt', receipt,
                    '--expected-score-multiplier', str(multiplier)]
            need(record.get('argv') == expected_argv,
                 'argv-semantics ' + expected_name)
            stdout_path = Path(record['stdout'])
            stdout = stdout_path.read_bytes()
            decoded = stdout.decode('utf-8')
            need(scenario['text'] == decoded.replace('\r\n', '\n'),
                 'inline-stdout ' + expected_name)
            check_caller_line(decoded, leaf_path, leaf_sha)
            manifest = staged.get('manifest') or {}
            content_root = staged.get('contentRoot')
            entry_path = staged.get('entryPath')
            need(isinstance(content_root, str) and content_root,
                 'content-root ' + expected_name)
            need(isinstance(entry_path, str) and entry_path,
                 'entry-path ' + expected_name)
            staged_sha = _need_sha(staged.get('stagedSha'),
                                   'staged-sha ' + expected_name)
            staged_path = Path(staged.get('stagedPath', ''))
            expected_module = Path(releases) / content_root / entry_path
            need(same_path(staged_path, expected_module),
                 'module-path ' + expected_name)
            need(staged_path.is_file() and
                 sha256_file(staged_path) == staged_sha,
                 'staged-file-sha ' + expected_name)
            _validate_manifest(manifest, version, entry_path, staged_sha,
                               expected_name)
            image = images[method_key]
            binding = bindings[method_key]
            need(staged_sha == image['r2rSha'].lower(),
                 'staged-image-sha ' + expected_name)
            need(staged_sha == str(binding['sha256']).lower(),
                 'staged-binding-sha ' + expected_name)
            if mode == 'recover':
                need(Path(receipt).is_file(), 'receipt-missing ' + expected_name)
                need(sha256_file(receipt) == lane['receiptRecover'].lower(),
                     'receipt-sha ' + expected_name)
                need(staged_b.get('receiptSha') == staged.get('receiptSha'),
                     'receipt-pair ' + expected_name)
                validate_receipt(receipt, b_document, manifest, content_root)
            host = {'path': host_path, 'sha': images['Host']['r2rSha'],
                    'method': bindings['Host']['method'], 'key': 'Host'}
            module = {'path': str(staged_path.resolve()), 'sha': staged_sha,
                      'method': binding['method'], 'key': method_key}
            for ordinal in (1, 2, 3):
                for role, owner in (('Host', host), ('Tick', module)):
                    method = owner['method']
                    calls.append({
                        'pid': record['pid'], 'version': version,
                        'ordinal': ordinal, 'role': role,
                        'image': lane['readyToRun'], 'methodKey': owner['key'],
                        'path': owner['path'], 'imageSha': owner['sha'],
                        'start': method['rva'], 'length': method['length'],
                        'lane': lane_name, 'scenario': scenario_name,
                    })
    need(seen_lanes == set(LANE_NAMES), 'lanes-set')
    need(len(calls) == 36 and len(pids) == 6, 'call/pid-count')
    methods = {key: {
        'path': str(Path(bindings[key]['path']).resolve()),
        'sha256': str(bindings[key]['sha256']).lower(),
        'symbol': bindings[key]['method']['symbol'],
        'rva': bindings[key]['method']['rva'],
        'length': bindings[key]['method']['length'],
        'section': bindings[key]['method']['section'],
        'mapPath': str(Path(bindings[key]['method']['mapPath']).resolve()),
        'mapSha': str(bindings[key]['method']['mapSha']).lower(),
        'executableSections': bindings[key]['executableSections'],
        'runtimeFunctions': bindings[key]['runtimeFunctions'],
    } for key in ('Host', 'A', 'B')}
    lineage = {
        'images': {key: {
            'ilPath': str(Path(image['ilPath']).resolve()),
            'r2rPath': str(Path(image['r2rPath']).resolve()),
            'ilSha': str(image['ilSha']).lower(),
            'r2rSha': str(image['r2rSha']).lower(),
            'ilMvid': str(image['ilMvid']).lower(),
            'r2rMvid': str(image['r2rMvid']).lower(),
        } for key, image in images.items()},
        'methods': methods,
        'receipts': lineage_receipts,
        'leaf': {'path': str(leaf_path.resolve()), 'sha256': leaf_sha},
        'runtime': {'path': str(Path(coreclr['framework']).resolve()),
                    'sha256': str(coreclr['frameworkSha']).lower()},
    }
    return {
        'calls': calls,
        'lineage': lineage,
        'counts': {'calls': len(calls), 'lanes': len(lanes), 'pids': len(pids)},
        'scenarios': ['stageA', 'stageB', 'recoverB'],
        'roles': ['Host', 'Tick'],
    }
