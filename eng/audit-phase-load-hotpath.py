#!/usr/bin/env python3
"""Bind the reviewed phase-load paths to actual private Release PE/PDB bytes."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / 'eng/audit-budget-hotpath.py'
CHECKER = ROOT / 'eng/phase-load-runtime-candidate.py'
PROFILE = ROOT / 'eng/runtime-patches/phase-load-hotpath-profile.json'
SUPPORT_SHA = 'd33f69318fec46e2cb16daaff114ff53c19c20b3dd69a0b709476ac105636a40'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def destination(rva, data):
    if len(data) == 2 and (0x70 <= data[0] <= 0x7f or data[0] == 0xeb):
        return rva + 2 + struct.unpack('<b', data[1:])[0]
    if len(data) == 6 and data[0] == 0x0f and 0x80 <= data[1] <= 0x8f:
        return rva + 6 + struct.unpack('<i', data[2:])[0]
    if len(data) == 5 and data[0] in (0xe8, 0xe9):
        return rva + 5 + struct.unpack('<i', data[1:])[0]
    return None


def helper_rows(text, base):
    # CDB occasionally joins two output rows; bytes remain separately encoded.
    matches = list(re.finditer(r'([0-9a-f]{8}`[0-9a-f]{8}) ([0-9a-f]+) +', text))
    rows = []
    for index, match in enumerate(matches):
        address = int(match[1].replace('`', ''), 16)
        if base + 0x18e320 <= address <= base + 0x18e33b:
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            rows.append({'rva': hex(address - base), 'bytes': match[2],
                         'assembly': text[match.end():end].split(chr(10))[0].strip()})
    return rows


def validate(evidence, helper, request, result, build, rows, profile, binary, pdb):
    support = module(SUPPORT, 'phase_pe_support')
    checker = module(CHECKER, 'phase_source_guard')
    require(sha(SUPPORT) == SUPPORT_SHA, 'Frozen PE/PDB support')
    proof = checker.validate(request['runtime'], profile['candidateCommit'])
    require(proof == request['candidateValidation'] == build['candidateValidation'], 'Exact compiled child source')
    require(build['candidateCommit'] == profile['candidateCommit'], 'Exact candidate commit')
    require(build['candidateCheckerSha256'] == sha(CHECKER), 'Compiled checker binding')
    require(build['exitCode'] == 0 and build['configuration'] == 'Release', 'Successful Release build')
    require(result['passed'] and result['exitCode'] == 0 and result['offlineOnly'], 'Offline observer passed')
    for key, file in {'request': 'request.json', 'stdout': 'cdb.stdout',
                      'stderr': 'cdb.stderr', 'instructions': 'instructions.json'}.items():
        require(sha(evidence / file) == result[key + 'Sha256'], 'Original observer binding: ' + key)
    require(sha(evidence / 'build-result.json') == request['buildResultSha256'], 'Original build receipt')
    require(sha(evidence / 'native-commands.txt') == request['nativeCommandsSha256'] == build['nativeCommandsSha256'], 'Compile commands')
    for file, expected in profile['helperHashes'].items():
        require(sha(helper / file) == expected, 'Supplement raw binding: ' + file)
    for path, expected in request['files'].items():
        require(sha(path) == expected, 'Actual observer input: ' + path)
        normalized = path.replace('\\', '/')
        if '/src/' in normalized:
            relative = 'src/' + normalized.split('/src/', 1)[1]
            require(sha(evidence / 'source' / relative) == expected, 'Source snapshot')
            if relative in build['sourceHashes']:
                require(build['sourceHashes'][relative] == expected, 'Compiled source hash')
    for relative in (checker.METER, checker.CONFIG):
        require(sha(Path(request['runtime']) / relative) == build['sourceHashes'][relative], 'Compiled phase source: ' + relative)
    base, raw, identity = support.pe_view(binary)
    require(identity == support.pdb_identity(pdb) == (profile['pePdbGuid'], profile['pePdbAge']), 'PE/PDB identity')
    require(hashlib.sha256(binary).hexdigest() == build['criticalProductHashes']['coreclr.dll'], 'Compiled native PE')
    text = (evidence / 'cdb.stdout').read_text(errors='replace')
    for offset, field in profile['fields'].items():
        require(re.search(r'\+' + re.escape(offset) + r'\s+' + field + r'\s+:', text), 'PDB field: ' + field)
    mapping = {}
    for row in rows:
        rva, data = int(row['rva'], 16), bytes.fromhex(row['bytes'])
        require(raw(rva, len(data)) == data and rva not in mapping, 'Unique actual PE instruction: ' + row['rva'])
        mapping[rva] = row
    require(len(rows) == result['actualPeByteMatches'] + 10, 'Main plus ten helper rows')
    for key, expected in profile['bytes'].items():
        require(mapping[int(key, 16)]['bytes'] == expected, 'Frozen path byte: ' + key)
    facts = {}
    for name, path in profile['paths'].items():
        returns, locks, calls, phase_loads = [], [], [], []
        for index, key in enumerate(path):
            rva = int(key, 16)
            data = bytes.fromhex(mapping[rva]['bytes'])
            if data[0] == 0xf0:
                locks.append(key)
            if key == '0x18e326':
                phase_loads.append(key)
            if index + 1 == len(path):
                require(data == bytes.fromhex('ffe1') and not returns, 'Completed admitted dispatch path')
                continue
            following = int(path[index + 1], 16)
            target = destination(rva, data)
            if data[0] == 0xe8:
                require(target == 0x18e320 and following == target, 'Exact Phase call destination')
                returns.append(rva + len(data))
                calls.append(key)
            elif data == bytes([0xc3]):
                require(returns and following == returns.pop(), 'Matched actual call return')
            else:
                allowed = (rva + len(data),) if target is None else (rva + len(data), target)
                require(following in allowed, 'Connected branch/fallthrough: ' + key)
        expected = profile['expected'][name]
        require(locks == expected['lockRows'], 'Exact path locked RMW inventory: ' + name)
        require(len(calls) == expected['phaseCalls'] and len(phase_loads) == expected['phaseLoads'], 'Exact phase call/load count')
        facts[name] = {'lockedRmws': len(locks), 'phaseCalls': len(calls),
                       'phaseLoads': len(phase_loads), 'connectedRows': len(path)}
    return {'actualPeByteMatches': len(rows), 'pePdbGuid': identity[0], 'pePdbAge': identity[1],
            'paths': facts, 'liveBranchObserved': False, 'performanceMeasured': False,
            'completeFunctionInventory': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--helper', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evidence, helper, output = args.evidence.resolve(), args.helper.resolve(), args.output.resolve()
    require(not output.exists(), 'Fresh output required')
    request, result, build, rows = [json.loads((evidence / file).read_text()) for file in
                                   ('request.json', 'results.json', 'build-result.json', 'instructions.json')]
    profile = json.loads(PROFILE.read_text())
    dll = next(Path(p) for p in request['files'] if Path(p).name == 'coreclr.dll')
    pdb_file = next(Path(p) for p in request['files'] if Path(p).name == 'coreclr.pdb')
    binary, pdb = dll.read_bytes(), pdb_file.read_bytes()
    support = module(SUPPORT, 'phase_initial_pe')
    rows += helper_rows((helper / 'cdb.stdout').read_text(errors='replace'), support.pe_view(binary)[0])
    facts = validate(evidence, helper, request, result, build, rows, profile, binary, pdb)
    controls = []
    for name in ('load-byte', 'call-byte', 'branch-path', 'call-return', 'pdb-age', 'compiled-source', 'lock-count'):
        changed_rows, changed_profile, changed_build = map(copy.deepcopy, (rows, profile, build))
        changed_pdb = pdb
        if name in ('load-byte', 'call-byte'):
            key = '0x18e326' if name == 'load-byte' else '0x1986f0'
            next(row for row in changed_rows if row['rva'] == key)['bytes'] = '90'
        elif name == 'branch-path':
            changed_profile['paths']['normalOn'][1] = '0x198688'
        elif name == 'call-return':
            path = changed_profile['paths']['normalOn']
            path[path.index('0x18e331') + 1] = '0x1986f7'
        elif name == 'pdb-age':
            _, offset = support.pdb_identity(pdb, with_age_offset=True)
            data = bytearray(pdb)
            struct.pack_into('<I', data, offset, facts['pePdbAge'] + 1)
            changed_pdb = bytes(data)
        elif name == 'compiled-source':
            changed_build['sourceHashes']['src/coreclr/vm/runeclrinstructionmeter.h'] = '0' * 64
        else:
            changed_profile['expected']['normalOn']['lockRows'].pop()
        try:
            validate(evidence, helper, request, result, changed_build, changed_rows, changed_profile, binary, changed_pdb)
        except ValueError as error:
            controls.append({'name': name, 'rejected': True, 'reason': str(error)})
        else:
            raise ValueError('Negative control accepted: ' + name)
    output.mkdir(parents=True)
    for path in (Path(__file__), SUPPORT, CHECKER, PROFILE):
        (output / path.name).write_bytes(path.read_bytes())
    report = {'passed': True, 'candidateCommit': profile['candidateCommit'], 'facts': facts,
              'auditorSha256': sha(__file__), 'profileSha256': sha(PROFILE),
              'evidenceResultsSha256': sha(evidence / 'results.json'),
              'helperRawHashes': profile['helperHashes'], 'negativeControls': controls,
              'assumptions': profile['assumptions'],
              'scope': 'Reviewed emitted paths only; shared frozen PE/PDB parser, no live execution or timing.'}
    (output / 'results.json').write_text(json.dumps(report, indent=2) + chr(10))
    print(json.dumps({'passed': True, **facts, 'negativeControls': len(controls)}, indent=2))


if __name__ == '__main__':
    main()
