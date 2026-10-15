#!/usr/bin/env python3
"""Independently bind offline instruction rows to PE bytes, PDB identity and source."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import struct
import uuid


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pe_view(binary):
    pe = struct.unpack_from('<I', binary, 0x3c)[0]
    require(binary[pe:pe + 4] == b'PE\0\0', 'PE signature')
    optional = pe + 24
    require(struct.unpack_from('<H', binary, optional)[0] == 0x20b, 'PE32+ required')
    base = struct.unpack_from('<Q', binary, optional + 24)[0]
    sections = []
    count = struct.unpack_from('<H', binary, pe + 6)[0]
    size = struct.unpack_from('<H', binary, pe + 20)[0]
    for index in range(count):
        offset = optional + size + 40 * index
        virtual_size, rva, raw_size, raw_pointer = struct.unpack_from('<IIII', binary, offset + 8)
        sections.append((rva, virtual_size, raw_size, raw_pointer))

    def raw(rva, length):
        for start, _, raw_size, pointer in sections:
            if start <= rva and rva + length <= start + raw_size:
                return binary[pointer + rva - start:pointer + rva - start + length]
        raise ValueError('RVA is not wholly backed by PE raw bytes: ' + hex(rva))

    debug_rva, debug_size = struct.unpack_from('<II', binary, optional + 112 + 6 * 8)
    identities = []
    for offset in range(0, debug_size, 28):
        entry = raw(debug_rva + offset, 28)
        _, _, _, _, kind, data_size, _, pointer = struct.unpack('<IIHHIIII', entry)
        data = binary[pointer:pointer + data_size]
        if kind == 2 and data[:4] == b'RSDS':
            identities.append((str(uuid.UUID(bytes_le=data[4:20])), struct.unpack_from('<I', data, 20)[0]))
    require(len(identities) == 1, 'exactly one RSDS identity')
    return base, raw, identities[0]


def pdb_identity(binary, with_age_offset=False):
    require(binary[:32] == b'Microsoft C/C++ MSF 7.00\r\n\x1aDS\0\0\0', 'MSF 7 PDB required')
    block_size, _, _, directory_size, _, block_map = struct.unpack_from('<6I', binary, 32)
    directory_blocks = (directory_size + block_size - 1) // block_size
    numbers = struct.unpack_from('<' + str(directory_blocks) + 'I', binary, block_map * block_size)
    directory = b''.join(binary[n * block_size:(n + 1) * block_size] for n in numbers)[:directory_size]
    streams = struct.unpack_from('<I', directory)[0]
    sizes = struct.unpack_from('<' + str(streams) + 'I', directory, 4)
    offset = 4 + streams * 4
    stream_one = None
    for index, size in enumerate(sizes):
        count = 0 if size == 0xffffffff else (size + block_size - 1) // block_size
        blocks = struct.unpack_from('<' + str(count) + 'I', directory, offset)
        offset += count * 4
        if index == 1:
            stream_one = b''.join(binary[n * block_size:(n + 1) * block_size] for n in blocks)[:size]
            age_offset = blocks[0] * block_size + 8
    require(stream_one is not None and len(stream_one) >= 28, 'PDB info stream')
    identity = str(uuid.UUID(bytes_le=stream_one[12:28])), struct.unpack_from('<I', stream_one, 8)[0]
    return (identity, age_offset) if with_age_offset else identity


# These are the six operations on the admitted phase-0 path, not all lock rows.
NORMAL_LOCKS = {
    0x1986b8: 'f00fb17228', 0x198799: 'f00fb17228',
    0x1987b2: 'f0480fb17208', 0x1987c1: 'f0480fb14a08',
    0x1987cb: 'f0480fb17210', 0x1987d5: 'f0480fb14a10',
}
NORMAL_BRANCHES = {
    0x1986bf: ('7404', 0x1986c5),
    0x1986c9: ('0f847f000000', 0x19874e),
    0x198752: ('7543', 0x198797),
    0x1987a0: ('7404', 0x1987a6),
    0x1987aa: ('7404', 0x1987b0),
    0x1987bb: ('7e28', 0x1987e5),
    0x1987c7: ('751a', 0x1987e3),
    0x1987db: ('7504', 0x1987e1),
    0x1987df: ('eb12', 0x1987f3),
    0x1987f5: ('0f8596feffff', 0x198691),
}


def validate(evidence, request, result, instructions, build, binary, pdb):
    base, raw, identity = pe_view(binary)
    require(identity == pdb_identity(pdb), 'PE/PDB GUID and age match')
    require(result['passed'] and result['exitCode'] == 0 and result['offlineOnly'], 'offline observer success')
    for name in ('request', 'stdout', 'stderr', 'instructions'):
        filename = {'request': 'request.json', 'stdout': 'cdb.stdout', 'stderr': 'cdb.stderr', 'instructions': 'instructions.json'}[name]
        require(sha(evidence / filename) == result[name + 'Sha256'], 'raw ' + name + ' binding')
    require(sha(evidence / 'build-result.json') == request['buildResultSha256'], 'build receipt binding')
    require(sha(evidence / 'native-commands.txt') == request['nativeCommandsSha256'], 'native command binding')
    require(build['configuration'] == 'Release' and build['exitCode'] == 0, 'actual successful Release build')
    require(build['candidateCommit'] == request['candidateCommit'], 'source commit binding')
    for path, expected in request['files'].items():
        require(sha(path) == expected, 'actual input hash: ' + path)
        normalized = path.replace('\\', '/')
        if '/src/' in normalized:
            relative = 'src/' + normalized.split('/src/', 1)[1]
            require(sha(evidence / 'source' / relative) == expected, 'source snapshot: ' + relative)
            if relative in build['sourceHashes']:
                require(build['sourceHashes'][relative] == expected, 'compiled source binding: ' + relative)
        if Path(path).name == 'coreclr.dll':
            require(expected == build['criticalProductHashes']['coreclr.dll'], 'compiled PE binding')
    stdout = (evidence / 'cdb.stdout').read_text(encoding='utf-8', errors='replace')
    require('private pdb symbols' in stdout, 'private symbols loaded')
    for offset, name in ((0x8, 'm_remaining'), (0x10, 'm_executed'), (0x28, 'm_phase')):
        require(re.search(r'\+0x' + format(offset, '03x') + r'\s+' + name + r'\s+:', stdout), 'PDB field: ' + name)
    rows = {}
    for instruction in instructions:
        rva = int(instruction['rva'], 16)
        machine = bytes.fromhex(instruction['bytes'])
        require(int(instruction['address'], 16) == base + rva, 'instruction address')
        require(raw(rva, len(machine)) == machine, 'actual PE instruction bytes')
        rows[rva] = instruction
    require(len(instructions) == result['actualPeByteMatches'], 'instruction count')
    for rva, machine in NORMAL_LOCKS.items():
        require(rva in rows and rows[rva]['bytes'] == machine, 'normal lock row: ' + hex(rva))
        require('lock cmpxchg' in rows[rva]['assembly'], 'normal lock opcode')
    require(rows[0x19851a]['bytes'] == '33f6', 'RSI initialized to zero')
    for rva, (machine, target) in NORMAL_BRANCHES.items():
        require(rows[rva]['bytes'] == machine, 'normal branch bytes')
        encoded = bytes.fromhex(machine)
        displacement = struct.unpack('<b', encoded[-1:])[0] if len(encoded) == 2 else struct.unpack('<i', encoded[-4:])[0]
        require(rva + len(encoded) + displacement == target and target in rows, 'normal branch target')
    lock_rows = [row for row in instructions if 'lock ' in row['assembly']]
    require(len(lock_rows) == len(result['lockInstructionRows']), 'all observed lock rows')
    return {'pePdbGuid': identity[0], 'pePdbAge': identity[1], 'actualPeByteMatches': len(instructions),
            'observedLockRows': len(lock_rows), 'normalAdmittedPathLockRows': len(NORMAL_LOCKS),
            'normalPathBranchTargets': len(NORMAL_BRANCHES)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    evidence, output = Path(args.evidence).resolve(), Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    require(not output.exists(), 'preserve prior review')
    request, result, instructions, build = (json.loads((evidence / name).read_text()) for name in
                                           ('request.json', 'results.json', 'instructions.json', 'build-result.json'))
    dll = next(Path(path) for path in request['files'] if Path(path).name == 'coreclr.dll')
    pdb_path = next(Path(path) for path in request['files'] if Path(path).name == 'coreclr.pdb')
    binary, pdb = dll.read_bytes(), pdb_path.read_bytes()
    facts = validate(evidence, request, result, instructions, build, binary, pdb)
    controls = []
    for name in ('forged-count', 'forged-lock-bytes', 'forged-source-binding', 'forged-pe-hash', 'wrong-pdb-age', 'forged-branch-target'):
        changed_request, changed_result, changed_rows, changed_build = map(copy.deepcopy, (request, result, instructions, build))
        changed_pdb = pdb
        if name == 'forged-count':
            changed_result['actualPeByteMatches'] += 1
        elif name == 'forged-lock-bytes':
            next(row for row in changed_rows if row['rva'] == '0x1987cb')['bytes'] = '90'
        elif name == 'forged-source-binding':
            changed_build['sourceHashes']['src/coreclr/vm/runeclrinstructionmeter.h'] = '0' * 64
        elif name == 'forged-pe-hash':
            changed_request['files'][str(dll)] = '0' * 64
        elif name == 'wrong-pdb-age':
            _, age_offset = pdb_identity(pdb, with_age_offset=True)
            mutated = bytearray(pdb)
            struct.pack_into('<I', mutated, age_offset, facts['pePdbAge'] + 1)
            changed_pdb = bytes(mutated)
        else:
            next(row for row in changed_rows if row['rva'] == '0x1986c9')['bytes'] = '0f847e000000'
        try:
            validate(evidence, changed_request, changed_result, changed_rows, changed_build, binary, changed_pdb)
        except ValueError as error:
            controls.append({'name': name, 'rejected': True, 'reason': str(error)})
        else:
            raise ValueError('negative control accepted: ' + name)
    report = {'passed': True, 'scope': 'independent offline PE/PDB/source audit; no runtime execution or cycle attribution',
              'evidence': str(evidence), 'evidenceResultSha256': sha(evidence / 'results.json'),
              'auditorSha256': sha(__file__), 'facts': facts, 'negativeControls': controls}
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'passed': True, **facts, 'rejectedControls': len(controls)}, indent=2))


if __name__ == '__main__':
    main()
