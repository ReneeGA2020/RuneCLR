#!/usr/bin/env python3
"""Review the increment candidate's actual PE/PDB and admitted dispatch path offline."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct

SUPPORT_PATH = Path(__file__).with_name('audit-budget-hotpath.py')
_spec = importlib.util.spec_from_file_location('hotpath_pe_support', SUPPORT_PATH)
_support = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_support)
CHECKER_PATH = Path(__file__).with_name('budget-runtime-candidate.py')
_spec = importlib.util.spec_from_file_location('budget_runtime_candidate', CHECKER_PATH)
_candidate = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_candidate)
CANDIDATE = '20405f7ae23e183e038703aa5e356b3310fef427'

# Freeze this profile only after manually following the matching emitted code.
PROFILE = {'pePdbGuid': 'e2db9951-8c20-40e4-bd72-1dd52ef9abe5',
 'pePdbAge': 1,
 'fields': {'0x000': 'm_enabled',
            '0x001': 'm_terminalPrototype',
            '0x008': 'm_remaining',
            '0x010': 'm_executed',
            '0x018': 'm_cleanupRemaining',
            '0x020': 'm_cleanupExecuted',
            '0x028': 'm_phase'},
 'supportRows': {'0x19851a': '4533f6', '0x19863a': '488bd0', '0x1987aa': 'ebe4', '0x19870d': 'ebe4'},
 'normalPath': ['0x198642',
                '0x198646',
                '0x1986a6',
                '0x1986a8',
                '0x1986ae',
                '0x1986b0',
                '0x1986b6',
                '0x1986b8',
                '0x1986ba',
                '0x198729',
                '0x19872d',
                '0x198767',
                '0x198769',
                '0x19876f',
                '0x198771',
                '0x198777',
                '0x198779',
                '0x19877b',
                '0x198781',
                '0x198783',
                '0x198789',
                '0x198790',
                '0x198793',
                '0x198795',
                '0x198799',
                '0x19879f',
                '0x1987a1',
                '0x1987a6',
                '0x1987a8',
                '0x1987ba',
                '0x1987bc',
                '0x198681',
                '0x198684',
                '0x198689',
                '0x19868f',
                '0x198696',
                '0x19869d',
                '0x1986a0'],
 'cleanupPath': ['0x198642',
                 '0x198646',
                 '0x1986a6',
                 '0x1986a8',
                 '0x1986ae',
                 '0x1986b0',
                 '0x1986b2',
                 '0x1986b4',
                 '0x1986b8',
                 '0x1986ba',
                 '0x1986bc',
                 '0x1986c0',
                 '0x1986c2',
                 '0x1986c6',
                 '0x1986c8',
                 '0x1986ca',
                 '0x1986d0',
                 '0x1986d2',
                 '0x1986d4',
                 '0x1986d6',
                 '0x1986da',
                 '0x1986dc',
                 '0x1986de',
                 '0x1986e0',
                 '0x1986e6',
                 '0x1986e9',
                 '0x1986eb',
                 '0x1986ed',
                 '0x1986f3',
                 '0x1986f6',
                 '0x1986f8',
                 '0x1986fc',
                 '0x198702',
                 '0x198704',
                 '0x198709',
                 '0x19870b',
                 '0x198724',
                 '0x1987ba',
                 '0x1987bc',
                 '0x198681',
                 '0x198684',
                 '0x198689',
                 '0x19868f',
                 '0x198696',
                 '0x19869d',
                 '0x1986a0'],
 'pathBytes': {'0x198642': '80780100',
               '0x198646': '755e',
               '0x1986a6': '33c0',
               '0x1986a8': 'f0440fb17228',
               '0x1986ae': '85c0',
               '0x1986b0': '7404',
               '0x1986b6': '32c0',
               '0x1986b8': '84c0',
               '0x1986ba': '746d',
               '0x198729': '807a0100',
               '0x19872d': '7538',
               '0x198767': '33c0',
               '0x198769': 'f0440fb17228',
               '0x19876f': '85c0',
               '0x198771': '7404',
               '0x198777': '32c0',
               '0x198779': '84c0',
               '0x19877b': '7404',
               '0x198781': '33c0',
               '0x198783': 'f04c0fb17208',
               '0x198789': '0f1f8000000000',
               '0x198790': '4885c0',
               '0x198793': '7e17',
               '0x198795': '488d48ff',
               '0x198799': 'f0480fb14a08',
               '0x19879f': '7509',
               '0x1987a1': 'f048ff4210',
               '0x1987a6': 'b001',
               '0x1987a8': 'eb10',
               '0x1987ba': '84c0',
               '0x1987bc': '0f85bffeffff',
               '0x198681': '8d47ff',
               '0x198684': '3d67010000',
               '0x198689': '0f87ee5a0000',
               '0x19868f': '488d156a79e6ff',
               '0x198696': '8b8c8200e31900',
               '0x19869d': '4803ca',
               '0x1986a0': 'ffe1',
               '0x1986b2': 'b001',
               '0x1986b4': 'eb02',
               '0x1986bc': '49395750',
               '0x1986c0': '7567',
               '0x1986c2': '807a0100',
               '0x1986c6': '745a',
               '0x1986c8': '33c0',
               '0x1986ca': 'f0440fb17228',
               '0x1986d0': '85c0',
               '0x1986d2': '7404',
               '0x1986d4': 'b001',
               '0x1986d6': 'eb02',
               '0x1986da': '84c0',
               '0x1986dc': '7444',
               '0x1986de': '33c0',
               '0x1986e0': 'f0440fb17228',
               '0x1986e6': '83f801',
               '0x1986e9': '7537',
               '0x1986eb': '33c0',
               '0x1986ed': 'f04c0fb17218',
               '0x1986f3': '4885c0',
               '0x1986f6': '7e17',
               '0x1986f8': '488d48ff',
               '0x1986fc': 'f0480fb14a18',
               '0x198702': '7509',
               '0x198704': 'f048ff4220',
               '0x198709': 'b001',
               '0x19870b': 'eb17',
               '0x198724': 'e991000000'},
 'branches': {'0x198646': '0x1986a6',
              '0x1986b0': '0x1986b6',
              '0x1986b4': '0x1986b8',
              '0x1986ba': '0x198729',
              '0x19872d': '0x198767',
              '0x198771': '0x198777',
              '0x19877b': '0x198781',
              '0x198793': '0x1987ac',
              '0x19879f': '0x1987aa',
              '0x1987aa': '0x198790',
              '0x1987a8': '0x1987ba',
              '0x1987bc': '0x198681',
              '0x1986c0': '0x198729',
              '0x1986c6': '0x198722',
              '0x1986d2': '0x1986d8',
              '0x1986d6': '0x1986da',
              '0x1986dc': '0x198722',
              '0x1986e9': '0x198722',
              '0x1986f6': '0x19870f',
              '0x198702': '0x19870d',
              '0x19870d': '0x1986f3',
              '0x19870b': '0x198724',
              '0x198724': '0x1987ba',
              '0x198689': '0x19e17d'},
 'atomics': {'0x1986a8': {'opcode': 'lock cmpxchg', 'operand': 'dword ptr [rdx+28h],r14d'},
             '0x198769': {'opcode': 'lock cmpxchg', 'operand': 'dword ptr [rdx+28h],r14d'},
             '0x198783': {'opcode': 'lock cmpxchg', 'operand': 'qword ptr [rdx+8],r14'},
             '0x198799': {'opcode': 'lock cmpxchg', 'operand': 'qword ptr [rdx+8],rcx'},
             '0x1987a1': {'opcode': 'lock inc', 'operand': 'qword ptr [rdx+10h]'}},
 'cleanupAtomics': {'0x1986a8': {'opcode': 'lock cmpxchg', 'operand': 'dword ptr [rdx+28h],r14d'},
                    '0x1986ca': {'opcode': 'lock cmpxchg', 'operand': 'dword ptr [rdx+28h],r14d'},
                    '0x1986e0': {'opcode': 'lock cmpxchg', 'operand': 'dword ptr [rdx+28h],r14d'},
                    '0x1986ed': {'opcode': 'lock cmpxchg', 'operand': 'qword ptr [rdx+18h],r14'},
                    '0x1986fc': {'opcode': 'lock cmpxchg', 'operand': 'qword ptr [rdx+18h],rcx'},
                    '0x198704': {'opcode': 'lock inc', 'operand': 'qword ptr [rdx+20h]'}},
 'assumptions': ['Definition-owned non-null enabled terminal meter; R14 is zero from the nonvolatile '
                 'prologue register initialization.',
                 'Normal path: both phase reads return zero, terminal flag stays set, remaining is positive, '
                 'the first admission CAS succeeds, and the opcode is valid.',
                 'Cleanup path: phase is one at all checks, the current cleanup owner matches, remaining '
                 'cleanup allowance is positive, and the first admission CAS succeeds.',
                 'CAS contention can retry; denial, diagnostics and other execution paths have different '
                 'operation counts.',
                 'The observed CDB function flow is incomplete; no full function inventory, invocation '
                 'trace, CPU sampling or timing attribution is claimed.']}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def branch_target(rva, encoded):
    if len(encoded) == 2 and (0x70 <= encoded[0] <= 0x7f or encoded[0] == 0xeb):
        return rva + 2 + struct.unpack('<b', encoded[1:])[0]
    if len(encoded) == 6 and encoded[0] == 0x0f and 0x80 <= encoded[1] <= 0x8f:
        return rva + 6 + struct.unpack('<i', encoded[2:])[0]
    if len(encoded) == 5 and encoded[0] == 0xe9:
        return rva + 5 + struct.unpack('<i', encoded[1:])[0]
    return None


def validate(evidence, request, result, instructions, build, binary, pdb, profile, candidate):
    require(profile is not None, 'Actual candidate DLL path profile has not been reviewed yet.')
    require(request['candidateCommit'] == build['candidateCommit'] == candidate == CANDIDATE, 'Exact increment candidate')
    proof = _candidate.validate(request['runtime'], candidate)
    require(proof == request['candidateValidation'] == build['candidateValidation'], 'Exact candidate source proof')
    require(build['candidateCheckerSha256'] == sha(CHECKER_PATH), 'Compiled candidate checker binding')
    base, raw, identity = _support.pe_view(binary)
    require(identity == _support.pdb_identity(pdb), 'Actual PE/PDB GUID and age match')
    require(result['passed'] and result['exitCode'] == 0 and result['offlineOnly'], 'Successful offline observer')
    for name, file in {'request': 'request.json', 'stdout': 'cdb.stdout',
                       'stderr': 'cdb.stderr', 'instructions': 'instructions.json'}.items():
        require(sha(evidence / file) == result[name + 'Sha256'], 'Raw observer binding: ' + name)
    require(sha(evidence / 'build-result.json') == request['buildResultSha256'], 'Build receipt binding')
    require(sha(evidence / 'native-commands.txt') == request['nativeCommandsSha256'] == build['nativeCommandsSha256'], 'Actual native compile commands')
    require(build['configuration'] == 'Release' and build['exitCode'] == 0, 'Matching successful Release build')
    for path, expected in request['files'].items():
        require(sha(path) == expected, 'Actual analysis input: ' + path)
        normalized = path.replace('\\', '/')
        if '/src/' in normalized:
            relative = 'src/' + normalized.split('/src/', 1)[1]
            require(sha(evidence / 'source' / relative) == expected, 'Source snapshot: ' + relative)
            if relative in build['sourceHashes']:
                require(build['sourceHashes'][relative] == expected, 'Compiled source binding: ' + relative)
        if Path(path).name == 'coreclr.dll':
            require(expected == build['criticalProductHashes']['coreclr.dll'], 'Compiled PE binding')
    require(sha(Path(request['runtime']) / _candidate.METER) == build['sourceHashes'][_candidate.METER], 'Actually compiled meter header')
    require(identity == (profile['pePdbGuid'], profile['pePdbAge']), 'Actual profile PE/PDB identity')
    stdout = (evidence / 'cdb.stdout').read_text(encoding='utf-8', errors='replace')
    require('private pdb symbols' in stdout, 'Private PDB symbols loaded')
    for offset, field in profile['fields'].items():
        require(re.search(r'\+' + re.escape(offset) + r'\s+' + re.escape(field) + r'\s+:', stdout), 'Typed PDB field: ' + field)
    rows = {}
    for instruction in instructions:
        rva = int(instruction['rva'], 16)
        machine = bytes.fromhex(instruction['bytes'])
        require(int(instruction['address'], 16) == base + rva, 'Instruction address')
        require(raw(rva, len(machine)) == machine, 'Actual PE instruction bytes')
        require(rva not in rows, 'Duplicate instruction row')
        rows[rva] = instruction
    require(len(instructions) == result['actualPeByteMatches'], 'Observed byte-match count')
    for key, expected in profile['supportRows'].items():
        require(rows[int(key, 16)]['bytes'] == expected, 'Admitted path prerequisite: ' + key)
    path_counts = {}
    for name, path, atomics in (('normal', profile['normalPath'], profile['atomics']),
                                ('cleanup', profile['cleanupPath'], profile['cleanupAtomics'])):
        for index, key in enumerate(path):
            rva = int(key, 16)
            row = rows[rva]
            require(row['bytes'] == profile['pathBytes'][key], 'Frozen actual path byte: ' + key)
            encoded = bytes.fromhex(row['bytes'])
            if index + 1 < len(path):
                following = int(path[index + 1], 16)
                target = branch_target(rva, encoded)
                allowed = (rva + len(encoded),) if target is None else (rva + len(encoded), target)
                require(following in allowed, 'Admitted path is not a real branch/fallthrough: ' + key)
        path_locks = [key for key in path if 'lock ' in rows[int(key, 16)]['assembly']]
        require(path_locks == list(atomics), 'All and only ' + name + ' path locked RMWs')
        for key, descriptor in atomics.items():
            assembly = rows[int(key, 16)]['assembly']
            require(descriptor['opcode'] in assembly and descriptor['operand'] in assembly, 'Actual atomic operation: ' + key)
        path_counts[name] = len(path_locks)
    decoded = {}
    for key, expected in profile['branches'].items():
        rva = int(key, 16)
        target = branch_target(rva, bytes.fromhex(rows[rva]['bytes']))
        require(target == int(expected, 16) and target in rows, 'Actual branch target: ' + key)
        decoded[key] = hex(target)
    total_locks = [row for row in instructions if 'lock ' in row['assembly']]
    require(len(total_locks) == len(result['lockInstructionRows']), 'Observed all-function lock inventory')
    return {'pePdbGuid': identity[0], 'pePdbAge': identity[1],
            'actualPeByteMatches': len(instructions), 'observedFunctionLockRows': len(total_locks),
            'normalAdmittedPathLockedRmws': path_counts['normal'], 'normalPathAtomics': profile['atomics'],
            'cleanupAdmittedPathLockedRmws': path_counts['cleanup'], 'cleanupPathAtomics': profile['cleanupAtomics'],
            'normalPathBranches': decoded, 'normalPathAssumptions': profile['assumptions'],
            'completeFunctionInventory': False, 'runtimeSampling': False, 'performanceClaim': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--candidate-commit', default=CANDIDATE)
    args = parser.parse_args()
    evidence, output = args.evidence.resolve(), args.output.resolve()
    require(not output.exists(), 'Fresh review output required')
    require(PROFILE is not None, 'Actual candidate DLL path profile has not been reviewed yet.')
    request, result, instructions, build = [json.loads((evidence / file).read_text()) for file in
                                          ('request.json', 'results.json', 'instructions.json', 'build-result.json')]
    dll = next(Path(path) for path in request['files'] if Path(path).name == 'coreclr.dll')
    pdb_file = next(Path(path) for path in request['files'] if Path(path).name == 'coreclr.pdb')
    binary, pdb = dll.read_bytes(), pdb_file.read_bytes()
    facts = validate(evidence, request, result, instructions, build, binary, pdb, PROFILE, args.candidate_commit)
    controls = []
    for name in ('atomic-bytes', 'branch-bytes', 'encoded-branch-target', 'pdb-age', 'compiled-source', 'per-opcode-count'):
        changed_request, changed_result, changed_rows, changed_build, changed_profile = map(copy.deepcopy, (request, result, instructions, build, PROFILE))
        changed_pdb = pdb
        if name == 'atomic-bytes':
            key = next(iter(PROFILE['atomics']))
            next(row for row in changed_rows if row['rva'] == key)['bytes'] = '90'
        elif name == 'branch-bytes':
            key = next(iter(PROFILE['branches']))
            row = next(row for row in changed_rows if row['rva'] == key)
            machine = bytearray.fromhex(row['bytes']); machine[-1] ^= 1; row['bytes'] = machine.hex()
        elif name == 'encoded-branch-target':
            key = next(iter(changed_profile['branches']))
            changed_profile['branches'][key] = hex(int(changed_profile['branches'][key], 16) + 1)
        elif name == 'pdb-age':
            _, offset = _support.pdb_identity(pdb, with_age_offset=True)
            modified = bytearray(pdb); struct.pack_into('<I', modified, offset, facts['pePdbAge'] + 1); changed_pdb = bytes(modified)
        elif name == 'compiled-source':
            changed_build['sourceHashes'][_candidate.METER] = '0' * 64
        else:
            changed_profile['atomics'].pop(next(iter(changed_profile['atomics'])))
        try:
            validate(evidence, changed_request, changed_result, changed_rows, changed_build, binary, changed_pdb, changed_profile, args.candidate_commit)
        except ValueError as error:
            controls.append({'name': name, 'rejected': True, 'reason': str(error)})
        else:
            raise ValueError('Negative control accepted: ' + name)
    output.parent.mkdir(parents=True, exist_ok=True)
    (output.parent / 'auditor.py').write_bytes(Path(__file__).read_bytes())
    (output.parent / SUPPORT_PATH.name).write_bytes(SUPPORT_PATH.read_bytes())
    (output.parent / CHECKER_PATH.name).write_bytes(CHECKER_PATH.read_bytes())
    (output.parent / 'path-profile.json').write_text(json.dumps(PROFILE, indent=2) + '\n')
    report = {'passed': True, 'evidence': str(evidence), 'candidateCommit': args.candidate_commit,
              'evidenceResultsSha256': sha(evidence / 'results.json'), 'auditorSha256': sha(__file__),
              'pePdbSupportSha256': sha(SUPPORT_PATH), 'candidateCheckerSha256': sha(CHECKER_PATH),
              'profileSha256': sha(output.parent / 'path-profile.json'), 'facts': facts, 'negativeControls': controls,
              'scope': 'Actual PE/PDB/source and manually reviewed admitted path offline; no runtime sampling or CPU-time attribution.'}
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': True, **facts, 'negativeControls': len(controls)}, indent=2))


if __name__ == '__main__':
    main()
