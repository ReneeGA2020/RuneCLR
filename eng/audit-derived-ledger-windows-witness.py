#!/usr/bin/env python3
"""Review actual 64-byte terminal ledger branch witnesses without launching code."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / 'eng/audit-budget-hotpath.py'
SUPPORT_SHA = 'd33f69318fec46e2cb16daaff114ff53c19c20b3dd69a0b709476ac105636a40'
CHECKER = ROOT / 'eng/derived-ledger-runtime-candidate.py'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load(path):
    return json.loads(Path(path).read_text())

def require(value, message):
    if not value:
        raise AssertionError(message)

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value

def validate(markers, request, base, result):
    require([x['label'] for x in markers] == ['ENTER', 'ACTION', 'AFTER'], 'Exactly three live admitted-path markers')
    require(len({x['pid'] for x in markers}) == len({x['meter'] for x in markers}) == 1, 'Same actual process/meter')
    for marker in markers:
        label = marker['label'].lower()
        require(marker['pc'] == base + int(request['witnessRvas'][label], 16) and
                marker['bytes'] == request['fileCode'][label], 'Actual live PC and compiled bytes')
        require(marker['derivedFlag'] == marker['dl'] == request['derivedFlag'] and marker['phaseFlag'] == 1 and
                marker['phase'] == 0, 'Actual cached switches and phase at selected admitted path')
        require(marker['initial'] == request['executionLimit'] and marker['remaining'] == request['executionLimit'] - 1 and
                marker['cleanupInitial'] == marker['cleanupRemaining'] == 4096 and marker['cleanupRaw'] == 0,
                'Actual immutable allowances and first successful remaining debit')
    require(markers[0]['raw'] == markers[1]['raw'] == 0 and
            markers[2]['raw'] == (0 if request['derivedFlag'] else 1), 'Actual ON bypass / OFF completed counter increment')
    require(result['passed'] and result['nonce'] == request['nonce'] and result['scenario'] == request['scenario'] and
            result['mode'] == 'terminal' and len(result['rows']) == 1, 'Owned completed terminal fixture')
    row = result['rows'][0]; snapshot = row['Snapshot']
    if request['scenario'] == 'Good':
        require(row['Returned'] and row['Value'] == 73 and row['ExceptionType'] is None and
                snapshot['Executed'] == 53 and snapshot['Remaining'] == 999947 and snapshot['Phase'] == 0 and
                not snapshot['IsTerminated'], 'Normal final admitted ledger')
    else:
        require(not row['Returned'] and row['ExceptionType'] == 'System.OperationCanceledException' and
                snapshot['Executed'] == 2048 and snapshot['Remaining'] == 0 and snapshot['Phase'] == 1 and
                snapshot['IsTerminated'] and snapshot['Reason'] == 1 and row['Counts'][0] == 1 and
                all(x == 0 for x in row['Counts'][1:]), 'Exact exhaustion and suppressed author continuation')
    require(snapshot['CleanupExecuted'] == 0 and snapshot['CleanupRemaining'] == 4096, 'Untouched cleanup account')

def preparation_guard(out):
    request = load(out / 'request.json')
    require(request['candidateCommit'] == '29ff781e157be82ba5a398a60bb05291e4a865af' and
            request['meterSize'] == 64 and request['fieldOffsets'] ==
            {'derivedFlag': 3, 'initialExecutionLimit': 48, 'initialCleanupLimit': 56}, 'Exact new meter candidate/layout')
    checker = module(CHECKER, 'derived_live_exact_source')
    require(checker.validate(request['runtime'], request['candidateCommit']) == request['candidateValidation'], 'Exact live source candidate')
    for name, digest in request['inputHashes'].items():
        require(sha(name) == digest, 'Actual native/managed/source/tool input changed: ' + name)
    for name, digest in request['commandHashes'].items():
        require(sha(out / name) == digest, 'Prepared debugger command changed')
    require(sha(out / 'driver.py') == request['driverSha256'] and sha(out / 'native-profile.json') == request['profileSha256'] and
            sha(out / 'auditor.py') == sha(__file__) == request['auditorSha256'], 'Original capture/profile/audit snapshots')
    require(sha(SUPPORT) == SUPPORT_SHA, 'Frozen PE/PDB reader')
    support = module(SUPPORT, 'derived_live_pe')
    core = Path(request['coreclr']); pdb = core.with_suffix('.pdb')
    _, raw, identity = support.pe_view(core.read_bytes())
    require(identity == support.pdb_identity(pdb.read_bytes()) == tuple(request['pePdbIdentity']), 'Actual exact PE/PDB identity')
    profile = load(out / 'native-profile.json')
    require(profile['coreclrSha256'] == sha(core) and profile['candidateCommit'] == request['candidateCommit'], 'Compiled profile candidate')
    for label, rva in request['witnessRvas'].items():
        code = request['fileCode'][label]
        require(raw(int(rva, 16), len(bytes.fromhex(code))).hex() == code, 'Compiled actual witness instruction bytes')
    build = Path(request['buildEvidence'])
    require(sha(build / 'build-result.json') == request['buildResultSha256'] and
            sha(build / 'layout-receipt.json') == request['layoutReceiptSha256'], 'Actual matching build/layout receipts')
    return request

def review(out):
    out = Path(out).resolve()
    request = preparation_guard(out)
    execution = load(out / 'execution.json'); process = load(out / 'process.json')
    require(execution['exitCode'] == 0 and not execution['timedOut'] and process['owned'] and
            process['controllerPid'] == execution['controllerPid'] and process['target'] == request['target'] and
            process['settings'] == request['settings'] and not request['benchmark'], 'Owned successful debugger process')
    require(request['settings']['DOTNET_RuneCLRDerivedLedger'] == str(request['derivedFlag']) and
            request['settings']['DOTNET_RuneCLRPhaseAcquireLoad'] == '1', 'Explicit independent runtime settings')
    for stream in ('stdout', 'stderr'):
        require(sha(out / ('cdb.' + stream)) == execution[stream + 'Sha256'], 'Immutable actual debugger stream')
    text = (out / 'cdb.stdout').read_text(errors='replace')
    require(request['coreclr'] in text, 'Actual mapped candidate DLL path')
    clean = re.sub(r'[*][*][*] WARNING: Unable to verify checksum for [^' + chr(13) + chr(10) + r']+[' + chr(13) + r']?[' + chr(10) + r']', '', text)
    number = r'([0-9a-f`]+)'
    pattern = (r'LEDGER_(ENTER|ACTION|AFTER) pid=([0-9]+) derived=([0-9]+) phaseFlag=([0-9]+) phase=([0-9]+) '
               'meter=' + number + ' pc=' + number + r' dl=([0-9]+) remaining=' + number + ' raw=' + number +
               ' initial=' + number + ' cleanupRemaining=' + number + ' cleanupRaw=' + number + ' cleanupInitial=' + number)
    hits = list(re.finditer(pattern, clean)); markers = []
    for index, hit in enumerate(hits):
        segment = clean[hit.end():hits[index + 1].start() if index + 1 < len(hits) else len(clean)]
        dumped = b''
        pc = int(hit[7].replace(chr(96), ''), 16)
        for line in segment.splitlines():
            match = re.match(r'^([0-9a-f]{8}`[0-9a-f]{8})  ([0-9a-f -]+)', line)
            if match:
                require(int(match[1].replace(chr(96), ''), 16) == pc + len(dumped), 'Contiguous actual memory bytes')
                dumped += bytes.fromhex(match[2].strip().replace('-', ' '))
            elif dumped:
                break
        marker = {'label': hit[1], 'pid': int(hit[2]), 'derivedFlag': int(hit[3]), 'phaseFlag': int(hit[4]),
                  'phase': int(hit[5]), 'meter': int(hit[6].replace(chr(96), ''), 16), 'pc': pc, 'dl': int(hit[8]),
                  'bytes': dumped.hex()}
        for group, name in enumerate(('remaining', 'raw', 'initial', 'cleanupRemaining', 'cleanupRaw', 'cleanupInitial'), 9):
            marker[name] = int(hit[group].replace(chr(96), ''), 16)
        markers.append(marker)
    module_hits = re.findall(r'LEDGER_MODULE pid=([0-9]+) base=([0-9a-f`]+)', clean)
    require(len(module_hits) == 1 and markers and int(module_hits[0][0]) == markers[0]['pid'], 'Actual loaded module/process owner')
    base = int(module_hits[0][1].replace(chr(96), ''), 16)
    result = load(out / 'evidence/result.json')
    validate(markers, request, base, result)
    completion = (out / 'cdb.stderr').read_text(errors='replace')
    require('PASS terminal-case=' + request['scenario'] + ' collected=true' in completion and
            'TERMINAL COMPLETE nonce=' + request['nonce'] + ' case=' + request['scenario'] + ' mode=terminal rows=1' in completion,
            'Actual fixture stack return and collection')
    negatives = []
    for name, change in (('wrong-derived-flag', lambda m, r: m[1].update(derivedFlag=1-request['derivedFlag'])),
                         ('wrong-live-pc', lambda m, r: m[1].update(pc=0)),
                         ('changed-live-bytes', lambda m, r: m[1].update(bytes='00')),
                         ('changed-counter-outcome', lambda m, r: m[2].update(raw=2)),
                         ('wrong-initial-allowance', lambda m, r: m[1].update(initial=0)),
                         ('changed-final-ledger', lambda m, r: r['rows'][0]['Snapshot'].update(Executed=0))):
        altered, changed = copy.deepcopy(markers), copy.deepcopy(result); change(altered, changed)
        try:
            validate(altered, request, base, changed)
        except (AssertionError, KeyError):
            negatives.append(name)
        else:
            raise AssertionError('Corrupted live evidence accepted: ' + name)
    return {'passed': True, 'candidateCommit': request['candidateCommit'], 'actualTargetPid': markers[0]['pid'],
            'nonce': request['nonce'], 'scenario': request['scenario'], 'actualMeterFlag': request['derivedFlag'],
            'normalAdmittedBranchObserved': True, 'rawCounterExpected': True, 'ledgerVerified': True, 'contextCollected': True,
            'liveMarkers': markers, 'negativeControlsRejected': negatives, 'meterSize': 64, 'fieldOffsets': request['fieldOffsets'],
            'buildResultSha256': request['buildResultSha256'], 'layoutReceiptSha256': request['layoutReceiptSha256'],
            'auditorSha256': sha(__file__), 'terminalResultSha256': sha(out / 'evidence/result.json'),
            'benchmark': False, 'scope': 'One actual first admitted normal branch per process; no cleanup branch, complete trace or performance proof.'}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lane', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); require(not args.output.exists(), 'Fresh offline review output')
    report = review(args.lane); args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + chr(10)); print(json.dumps(report, indent=2))
