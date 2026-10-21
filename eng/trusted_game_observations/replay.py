"""Replay JSONL observations against a freshly derived expected call set."""

from pathlib import Path

from . import pe
from .common import need, normalized_path, sha256_file
from .observations import as_int, positive_int, zero_int


def pe_sections(path):
    return [{'name': section['name'], 'va': section['va'],
             'size': section['size']}
            for section in pe.executable_sections(path)]


def in_section(offset, sections):
    return next((section for section in sections
                 if section['va'] <= offset < section['va'] + section['size']), None)


def check_query(record, key):
    pc = as_int(record.get('pc'), 'pc')
    need(record.get('vqStatus') == 'ok', 'vq-status ' + repr(key))
    zero_int(record.get('vqError'), 'vq-error ' + repr(key))
    base = as_int(record.get('queryBase'), 'queryBase')
    region = as_int(record.get('queryRegionSize'), 'queryRegionSize')
    need(base != 0 and region > 0 and record.get('inQueryRegion') is True,
         'query-region ' + repr(key))
    need(base <= pc < base + region, 'pc-region ' + repr(key))
    need(as_int(record.get('state'), 'state') == 0x1000,
         'not-committed ' + repr(key))
    protect = as_int(record.get('protect'), 'protect')
    need(protect & 0x100 == 0, 'page-guard ' + repr(key))
    need((protect & 0xff) in (0x10, 0x20, 0x40, 0x80),
         'not-executable ' + repr(key))
    alloc = as_int(record.get('allocBase'), 'allocBase')
    need(alloc != 0, 'base ' + repr(key))
    return pc, alloc


def check_target(record, call, binding):
    key = (call['pid'], call['version'], call['ordinal'], call['role'])
    pc, base = check_query(record, key)
    need(as_int(record.get('type'), 'type') == 0x1000000,
         'target-type ' + repr(key))
    need(record.get('mapStatus') == 'ok', 'target-map-status ' + repr(key))
    positive_int(record.get('mapLength'), 'target-map-length ' + repr(key))
    zero_int(record.get('mapError'), 'target-map-error ' + repr(key))
    need(record.get('pathStatus') == 'ok' and record.get('hashStatus') == 'ok',
         'target-path ' + repr(key))
    need(record.get('canonical') and
         normalized_path(record['canonical']) == normalized_path(call['path']),
         'target-full-path ' + repr(key))
    need(isinstance(record.get('device'), str) and record['device'],
         'target-device ' + repr(key))
    need(str(record.get('fileHash', '')).lower() ==
         str(call['imageSha']).lower(), 'target-sha ' + repr(key))
    need(record.get('headerStatus') == 'ok' and
         record.get('headerMachine') == '0x8664',
         'target-header ' + repr(key))
    offset = pc - base
    need(call['start'] <= offset < call['start'] + call['length'],
         'target-interval ' + repr(key))
    section = next((item for item in binding.get('executableSections', [])
                    if item['va'] <= offset < item['va'] + item['size']), None)
    need(section is not None, 'target-executable-section ' + repr(key))
    need(any(item['begin'] <= offset < item['end']
             for item in binding.get('runtimeFunctions', [])),
         'target-runtime-function ' + repr(key))
    return 'target'


def check_runtime(record, call, runtime_path, runtime_sha, runtime_sections):
    key = (call['pid'], call['version'], call['ordinal'], call['role'])
    pc, base = check_query(record, key)
    need(as_int(record.get('type'), 'type') == 0x1000000,
         'runtime-type ' + repr(key))
    need(record.get('mapStatus') == 'ok', 'runtime-map-status ' + repr(key))
    positive_int(record.get('mapLength'), 'runtime-map-length ' + repr(key))
    zero_int(record.get('mapError'), 'runtime-map-error ' + repr(key))
    need(record.get('pathStatus') == 'ok' and record.get('hashStatus') == 'ok',
         'runtime-path ' + repr(key))
    need(record.get('canonical') and
         normalized_path(record['canonical']) == normalized_path(runtime_path),
         'runtime-full-path ' + repr(key))
    need(str(record.get('fileHash', '')).lower() == runtime_sha,
         'runtime-sha ' + repr(key))
    need(record.get('headerStatus') == 'ok' and
         record.get('headerMachine') == '0x8664',
         'runtime-header ' + repr(key))
    offset = pc - base
    need(in_section(offset, runtime_sections) is not None,
         'runtime-executable-section ' + repr(key))
    return 'runtime'


def _method_key(version, role):
    if role == 'Host':
        return 'Host'
    return 'A' if version == 'game-rules-a' else 'B'


def replay(records, expected, bindings, runtime_path, runtime_sha):
    calls = expected['calls'] if isinstance(expected, dict) else expected
    by_key = {(call['pid'], call['version'], call['ordinal'], call['role']): call
              for call in calls}
    need(len(by_key) == len(calls) == 36, 'expected-count')
    need(Path(runtime_path).is_file(), 'runtime-missing')
    need(sha256_file(runtime_path) == str(runtime_sha).lower(), 'runtime-file-sha')
    runtime_sections = pe_sections(runtime_path)
    need(runtime_sections, 'runtime-executable-sections')
    seen = set()
    target = 0
    runtime = 0
    for record in records:
        key = (record.get('pid'), record.get('version'),
               record.get('ordinal'), record.get('role'))
        need(key in by_key, 'out-of-scope ' + repr(key))
        need(key not in seen, 'duplicate ' + repr(key))
        call = by_key[key]
        need(record.get('callId') ==
             str(call['pid']) + ':' + call['version'] + ':' +
             str(call['ordinal']) + ':' + call['role'],
             'call-id ' + repr(key))
        need(call['methodKey'] == _method_key(call['version'], call['role']),
             'method-key-lineage ' + repr(key))
        if call['image'] is True:
            binding = bindings[call['methodKey']]
            need(str(call['imageSha']).lower() ==
                 str(binding['sha256']).lower(),
                 'target-binding-sha ' + repr(key))
            need(call['start'] == binding['method']['rva'] and
                 call['length'] == binding['method']['length'],
                 'target-binding-interval ' + repr(key))
            check_target(record, call, binding)
            target += 1
        else:
            check_runtime(record, call, runtime_path, str(runtime_sha).lower(),
                          runtime_sections)
            runtime += 1
        need(record.get('exception') == 'none', 'exception ' + repr(key))
        zero_int(record.get('hresult'), 'hresult ' + repr(key))
        seen.add(key)
    missing = set(by_key) - seen
    need(not missing, 'missing ' + repr(sorted(missing)))
    need(target == 18 and runtime == 18, 'binding-counts ' + str((target, runtime)))
    return {
        'currentObservationChecks': {
            'passed': True,
            'recordCount': len(records),
            'targetImageBindings': target,
            'runtimeImageObservations': runtime,
            'checks': [
                'call-identity', 'method-key-lineage', 'query-state',
                'target-map-path-sha', 'target-interval',
                'target-executable-section', 'target-runtime-function',
                'runtime-map-path-sha', 'runtime-executable-section',
                'exception-hresult',
            ],
        },
        'targetImageBindings': target,
        'runtimeImageObservations': runtime,
        'runtimeImageObservationClaim':
            'PC lies in an executable section of the sealed coreclr.dll image',
        'runtimeImageObservationIsInterpreterProof': False,
        'interpreterIdentityProven': False,
        'targetMethodBodyProven': False,
        'overallAcceptance': False,
        'runtimeImage': {
            'path': str(Path(runtime_path).resolve()),
            'sha256': str(runtime_sha).lower(),
            'executableSections': runtime_sections,
        },
    }
