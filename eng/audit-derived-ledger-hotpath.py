#!/usr/bin/env python3
"""Bind explicit reviewed derived-ledger paths to real PE/PDB bytes offline."""
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
SUPPORT_SHA = 'd33f69318fec46e2cb16daaff114ff53c19c20b3dd69a0b709476ac105636a40'
CHECKER = ROOT / 'eng/derived-ledger-runtime-candidate.py'
FIELDS = {'0x000': 'm_enabled', '0x001': 'm_terminalPrototype', '0x002': 'm_phaseAcquireLoad',
          '0x003': 'm_derivedLedger', '0x008': 'm_remaining', '0x010': 'm_executed',
          '0x018': 'm_cleanupRemaining', '0x020': 'm_cleanupExecuted', '0x028': 'm_phase',
          '0x030': 'm_initialExecutionLimit', '0x038': 'm_initialCleanupLimit'}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def require(value, message):
    if not value:
        raise ValueError(message)

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def target(rva, data):
    if len(data) == 2 and (0x70 <= data[0] <= 0x7f or data[0] == 0xeb):
        return rva + 2 + struct.unpack('<b', data[1:])[0]
    if len(data) == 6 and data[0] == 0x0f and 0x80 <= data[1] <= 0x8f:
        return rva + 6 + struct.unpack('<i', data[2:])[0]
    if len(data) == 5 and data[0] in (0xe8, 0xe9):
        return rva + 5 + struct.unpack('<i', data[1:])[0]
    return None

def validate(evidence, profile, rows, build, binary, pdb):
    require(sha(SUPPORT) == SUPPORT_SHA, 'Frozen independent PE/PDB reader')
    support = module(SUPPORT, 'derived_hotpath_pe')
    checker = module(CHECKER, 'derived_hotpath_source')
    request = json.loads((evidence / 'request.json').read_text())
    result = json.loads((evidence / 'results.json').read_text())
    binding = json.loads((evidence / 'derived-analysis-binding.json').read_text())
    validation = checker.validate(request['runtime'], checker.COMMIT)
    require(validation == request['candidateValidation'] == build['candidateValidation'] == binding['candidateValidation'], 'Exact candidate source binding')
    require(build['candidateCommit'] == profile['candidateCommit'] == checker.COMMIT and
            build['candidateCheckerSha256'] == sha(CHECKER) and build['exitCode'] == 0 and
            build['configuration'] == 'Release', 'Successful exact Release build')
    require(result['passed'] and result['offlineOnly'] and result['exitCode'] == 0, 'Passed offline instruction inventory')
    for key, filename in {'request': 'request.json', 'stdout': 'cdb.stdout', 'stderr': 'cdb.stderr', 'instructions': 'instructions.json'}.items():
        require(sha(evidence / filename) == result[key + 'Sha256'], 'Original raw observer hash: ' + key)
    require(sha(evidence / 'build-result.json') == request['buildResultSha256'], 'Frozen native build receipt')
    require(sha(evidence / 'native-commands.txt') == request['nativeCommandsSha256'] == build['nativeCommandsSha256'], 'Frozen native compile commands')
    for name, expected in request['files'].items():
        require(sha(name) == expected, 'Original observer source/native/tool changed: ' + name)
    for name in (checker.METER, checker.CONFIG):
        require(sha(Path(request['runtime']) / name) == sha(evidence / 'source' / name) == build['sourceHashes'][name], 'Compiled ledger source: ' + name)
    base, raw, identity = support.pe_view(binary)
    require(identity == support.pdb_identity(pdb) == tuple(profile['pePdbIdentity']), 'Exact PE/PDB identity')
    require(hashlib.sha256(binary).hexdigest() == profile['coreclrSha256'] == build['criticalProductHashes']['coreclr.dll'], 'Exact compiled native bytes')
    text = (evidence / 'cdb.stdout').read_text(errors='replace')
    require(profile['meterSize'] == 64 and profile['meterAlignment'] == 8 and profile['fields'] == FIELDS, '64-byte meter field contract')
    for offset, field in FIELDS.items():
        require(re.search(r'[+]' + re.escape(offset) + r' +' + re.escape(field) + r' +:', text), 'Actual PDB field: ' + field)
    mapping = {}
    for row in rows:
        rva, machine = int(row['rva'], 16), bytes.fromhex(row['bytes'])
        require(raw(rva, len(machine)) == machine, 'Actual instruction maps to compiled PE bytes')
        if rva in mapping:
            require(mapping[rva]['bytes'] == row['bytes'], 'Duplicate symbol instruction bytes agree')
        mapping[rva] = row
    require(len(rows) == result['actualPeByteMatches'], 'Original inventory row count')
    for key, expected in profile['bytes'].items():
        require(mapping[int(key, 16)]['bytes'] == expected, 'Pinned reviewed instruction: ' + key)
    facts = {}
    for name, path in profile['paths'].items():
        pending_returns, locks = [], []
        for index, key in enumerate(path['rows']):
            rva = int(key, 16)
            machine = bytes.fromhex(mapping[rva]['bytes'])
            if machine[0] == 0xf0:
                locks.append(key)
            if index + 1 == len(path['rows']):
                require(machine.hex() == path['endBytes'] and not pending_returns, 'Reviewed path end: ' + name)
                continue
            following = int(path['rows'][index + 1], 16)
            destination = target(rva, machine)
            if machine[0] == 0xe8:
                require(following == destination, 'Matched direct helper call target')
                pending_returns.append(rva + len(machine))
            elif machine == bytes([0xc3]):
                require(pending_returns and following == pending_returns.pop(), 'Matched helper return')
            elif machine[0] in (0xe9, 0xeb):
                require(following == destination, 'Matched unconditional jump')
            else:
                require(following in ((rva + len(machine),) if destination is None else (rva + len(machine), destination)), 'Connected reviewed path: ' + key)
        require(locks == path['lockRows'], 'Exact selected path locked instruction list')
        facts[name] = {'lockedRmws': len(locks), 'connectedRows': len(path['rows'])}
    required_paths = ('normalOn', 'normalOff', 'cleanupOn', 'cleanupOff', 'executionGetterOn', 'cleanupGetterOn', 'diagnostic')
    require(all(name in facts for name in required_paths), 'Normal, cleanup, getters and diagnostic reviewed paths')
    for domain in ('normal', 'cleanup'):
        increment = profile['counterIncrements'][domain]
        require(increment in profile['paths'][domain + 'Off']['rows'] and
                increment not in profile['paths'][domain + 'On']['rows'], 'ON bypasses OFF admitted-counter RMW')
        instruction = mapping[int(increment, 16)]
        require(bytes.fromhex(instruction['bytes'])[0] == 0xf0 and 'inc' in instruction['assembly'], 'Actual locked counter increment')
    for name, claim in profile['semanticInstructions'].items():
        require(mapping[int(claim['rva'], 16)]['bytes'] == claim['bytes'] and
                re.search(claim['assemblyRegex'], mapping[int(claim['rva'], 16)]['assembly']), 'Reviewed actual semantic instruction: ' + name)
    require({'derivedFlagRead', 'executionAllowanceRead', 'cleanupAllowanceRead', 'executionSubtract',
             'cleanupSubtract', 'diagnosticExecutedIncrement'} <= set(profile['semanticInstructions']), 'Flag, immutable allowances, subtract and diagnostic inventory')
    return {'actualPeByteMatches': len(rows), 'uniqueInstructionRows': len(mapping), 'pePdbIdentity': identity,
            'paths': facts, 'meterSize': 64, 'getterCountsAdmitted': True,
            'liveBranchObserved': False, 'performanceMeasured': False, 'completeFunctionInventory': False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'Fresh review output')
    evidence = args.evidence.resolve()
    request = json.loads((evidence / 'request.json').read_text())
    profile = json.loads(args.profile.read_text())
    rows = json.loads((evidence / 'instructions.json').read_text())
    build = json.loads((evidence / 'build-result.json').read_text())
    dll = next(Path(p) for p in request['files'] if Path(p).name == 'coreclr.dll')
    pdb_file = next(Path(p) for p in request['files'] if Path(p).name == 'coreclr.pdb')
    binary, pdb = dll.read_bytes(), pdb_file.read_bytes()
    facts = validate(evidence, profile, rows, build, binary, pdb)
    negatives = []
    for name in ('instruction-byte', 'branch-connectivity', 'lock-list', 'field-offset', 'meter-size', 'compiled-source', 'pdb-age'):
        altered_profile, altered_rows, altered_build = map(copy.deepcopy, (profile, rows, build))
        altered_pdb = pdb
        if name == 'instruction-byte':
            altered_rows[0]['bytes'] = '90' if altered_rows[0]['bytes'] != '90' else 'cc'
        elif name == 'branch-connectivity':
            altered_profile['paths']['normalOn']['rows'][1] = altered_profile['paths']['normalOn']['rows'][0]
        elif name == 'lock-list':
            altered_profile['paths']['normalOff']['lockRows'].clear()
        elif name == 'field-offset':
            altered_profile['fields']['0x003'] = 'm_phaseAcquireLoad'
        elif name == 'meter-size':
            altered_profile['meterSize'] = 48
        elif name == 'compiled-source':
            altered_build['sourceHashes']['src/coreclr/vm/runeclrinstructionmeter.h'] = '0' * 64
        else:
            support = module(SUPPORT, 'derived_negative_pdb')
            _, offset = support.pdb_identity(pdb, with_age_offset=True)
            data = bytearray(pdb)
            struct.pack_into('<I', data, offset, facts['pePdbIdentity'][1] + 1)
            altered_pdb = bytes(data)
        try:
            validate(evidence, altered_profile, altered_rows, altered_build, binary, altered_pdb)
        except (ValueError, KeyError) as error:
            negatives.append({'name': name, 'rejected': True, 'reason': str(error)})
        else:
            raise ValueError('Corruption control accepted: ' + name)
    args.output.mkdir(parents=True)
    for path in (Path(__file__), SUPPORT, CHECKER, args.profile):
        shutil_target = args.output / path.name
        shutil_target.write_bytes(path.read_bytes())
    bound = {str(evidence / name): sha(evidence / name) for name in
             ('request.json', 'results.json', 'instructions.json', 'build-result.json', 'native-commands.txt', 'cdb.stdout', 'cdb.stderr', 'derived-analysis-binding.json')}
    report = {'passed': True, 'candidateCommit': profile['candidateCommit'], 'facts': facts,
              'auditorSha256': sha(__file__), 'profileSha256': sha(args.profile), 'boundFiles': bound,
              'negativeControls': negatives, 'offlineOnly': True, 'liveBranchObserved': False, 'benchmark': False,
              'scope': 'Explicit manually reviewed connected emitted paths; no actual branch execution or timing.'}
    (args.output / 'results.json').write_text(json.dumps(report, indent=2) + chr(10))
    print(json.dumps({'passed': True, **facts, 'negativeControls': len(negatives)}, indent=2))

if __name__ == '__main__':
    main()
