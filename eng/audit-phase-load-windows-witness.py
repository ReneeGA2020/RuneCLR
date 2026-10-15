#!/usr/bin/env python3
"""Offline review of actual CDB meter switch, instruction bytes and collection."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def require(value, message):
    if not value:
        raise AssertionError(message)


def validate(markers, request, base, data, result):
    require([m['label'] for m in markers] == ['ENTER', 'BRANCH', 'AFTER'], 'three actual live markers')
    require(len({m['pid'] for m in markers}) == len({m['meter'] for m in markers}) == 1, 'same target/meter')
    for marker in markers:
        label = marker['label'].lower()
        require(marker['flag'] == request['flag'] and marker['phase'] == 0, 'actual terminal meter flag/phase')
        require(marker['pc'] == base + int(request['phaseRvas'][label], 16), 'actual instruction PC/RVA')
        require(marker['bytes'] == request['fileCode'][label], 'actual memory equals instruction bytes')
    require(markers[-1]['eax'] == 0, 'actual phase load result in EAX')
    if request.get('hotLoopCaller'):
        require(len({m['caller'] for m in markers}) == 1, 'same actual caller across load')
        require(markers[0]['caller'] - base in [int(rva, 16) for rva in request['callerRvas']], 'actual hot-loop caller')
    require(result['passed'] and result['nonce'] == request['nonce'] and result['scenario'] == request['scenario'] and result['mode'] == 'terminal', 'owned completed result')
    require(len(result['rows']) == 1, 'one actual completed/collected context')
    row = result['rows'][0]
    s = row['Snapshot']
    if request['scenario'] == 'Good':
        require(row['Returned'] and row['Value'] == 73 and row['ExceptionType'] is None, 'actual normal return')
        require(s['Phase'] == 0 and not s['IsTerminated'] and s['Executed'] == 53 and s['Remaining'] == 999947, 'normal meter ledger')
    else:
        require(not row['Returned'] and row['ExceptionType'] == 'System.OperationCanceledException', 'actual terminal failure')
        require(s['Executed'] == 2048 and s['Remaining'] == 0 and s['IsTerminated'] and s['Reason'] == 1 and s['Phase'] == 1, 'exact exhaustion ledger')
        require(row['Counts'][0] == 1 and all(n == 0 for n in row['Counts'][1:]), 'author catch/continuation suppressed')


def review(out):
    request, execution = load(out / 'request.json'), load(out / 'execution.json')
    require(execution['exitCode'] == 0 and not request['benchmark'], 'actual debugger completion; no benchmark')
    require(sha(out / 'driver.py') == request['driverSha256'], 'original capture driver snapshot')
    for path, digest in request['inputHashes'].items():
        require(sha(Path(path)) == digest, 'immutable actual input SHA')
    for path, digest in request['commandHashes'].items():
        require(sha(Path(path)) == digest, 'original debugger command SHA')
    for stream in ('stdout', 'stderr'):
        require(sha(out / ('cdb.' + stream)) == execution[stream + 'Sha256'], 'actual raw stream hash')
    text = (out / 'cdb.stdout').read_text(errors='replace')
    # A deferred-symbol warning can interrupt printf after its literal prefix.
    normalized = re.sub(r'\*\*\* WARNING: Unable to verify checksum for [^\r\n]+\r?\n', '', text)
    pattern = r'PHASE_(ENTER|BRANCH|AFTER) pid=(\d+) flag=(\d+) phase=(\d+) meter=([0-9a-f\x60]+) pc=([0-9a-f\x60]+) eax=([0-9a-f]+)(?: caller=([0-9a-f\x60]+))?'
    hits = list(re.finditer(pattern, normalized))
    markers = []
    for i, hit in enumerate(hits):
        segment = normalized[hit.end():hits[i + 1].start() if i + 1 < len(hits) else len(normalized)]
        dumped = b''
        for line in segment.splitlines():
            match = re.match(r'^([0-9a-f]{8}\x60[0-9a-f]{8})  ([0-9a-f -]+)', line)
            if match:
                address = int(match[1].replace(chr(96), ''), 16)
                require(address == int(hit[6].replace(chr(96), ''), 16) + len(dumped), 'contiguous actual memory dump')
                dumped += bytes.fromhex(match[2].strip().replace('-', ' '))
            elif dumped:
                break
        markers.append({'label': hit[1], 'pid': int(hit[2]), 'flag': int(hit[3]), 'phase': int(hit[4]),
                        'meter': int(hit[5].replace(chr(96), ''), 16), 'pc': int(hit[6].replace(chr(96), ''), 16),
                        'eax': int(hit[7], 16), 'bytes': dumped.hex(),
                        'caller': int(hit[8].replace(chr(96), ''), 16) if hit[8] else None})
    module = re.findall(r'PHASE_MODULE pid=(\d+) base=([0-9a-f]+)', normalized)
    require(len(module) == 1, 'one actual CoreCLR module/base')
    base = int(module[0][1], 16)
    require(markers and int(module[0][0]) == markers[0]['pid'], 'actual module/target owner')
    helper = Path(__file__).resolve().parent / 'audit-budget-hotpath.py'
    require(sha(helper) == 'd33f69318fec46e2cb16daaff114ff53c19c20b3dd69a0b709476ac105636a40', 'frozen PE reader')
    spec = importlib.util.spec_from_file_location('live_phase_pe', helper)
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    core = next(Path(p) for p in request['inputHashes'] if Path(p).name == 'coreclr.dll')
    pdb = core.with_suffix('.pdb')
    _, data, identity = support.pe_view(core.read_bytes())
    require(identity == support.pdb_identity(pdb.read_bytes()) == tuple(request['pePdbIdentity']), 'actual PE/PDB identity')
    require(str(core) in normalized, 'actual mapped DLL path')
    for label, rva in request['phaseRvas'].items():
        expected = request['fileCode'][label]
        require(data(int(rva, 16), len(bytes.fromhex(expected))).hex() == expected, 'actual PE raw bytes')
    result_path = out / 'evidence/result.json'
    result = load(result_path)
    validate(markers, request, base, data, result)
    completion = (out / 'cdb.stderr').read_text(errors='replace')
    require(f'PASS terminal-case={request["scenario"]} collected=true' in completion, 'actual returned stack collection')
    require(f'TERMINAL COMPLETE nonce={request["nonce"]} case={request["scenario"]} mode=terminal rows=1' in completion, 'actual completion nonce')
    negatives = []
    for name, mutation in [('wrong-meter-flag', lambda m, r: m[1].update(flag=1-request['flag'])),
                           ('wrong-live-pc', lambda m, r: m[1].update(pc=0)),
                           ('changed-live-bytes', lambda m, r: m[1].update(bytes='00')),
                           ('changed-phase-value', lambda m, r: m[2].update(eax=1)),
                           ('changed-final-ledger', lambda m, r: r['rows'][0]['Snapshot'].update(Executed=0))]:
        altered, changed = copy.deepcopy(markers), copy.deepcopy(result)
        mutation(altered, changed)
        try:
            validate(altered, request, base, data, changed)
        except (AssertionError, KeyError):
            negatives.append(name)
        else:
            raise AssertionError('corrupted witness accepted: ' + name)
    return {'passed': True, 'actualTargetPid': markers[0]['pid'], 'nonce': request['nonce'], 'scenario': request['scenario'],
            'actualHotLoopCaller': bool(request.get('hotLoopCaller')),
            'actualMeterFlag': request['flag'], 'branch': 'acquire-load' if request['flag'] else 'locked-compare-exchange',
            'liveMarkers': markers, 'normalOrTerminalResultVerified': True, 'contextCollected': True,
            'negativeControlsRejected': negatives, 'terminalResultSha256': sha(result_path), 'requestSha256': sha(out / 'request.json'),
            'executionSha256': sha(out / 'execution.json'), 'auditorSha256': sha(Path(__file__)), 'benchmark': False,
            'scope': 'One actual phase-0 meter branch per owned process; no complete invocation or per-dispatch trace'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lane', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'fresh review receipt')
    report = review(args.lane)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
