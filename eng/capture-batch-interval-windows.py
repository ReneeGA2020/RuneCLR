#!/usr/bin/env python3
"""Bounded actual RecordBatch entry capture, independent of performance timing."""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / 'eng/batch-interval-runtime-candidate.py'
CHECKER_SHA = '8ba8eba6d21132f5c4e7837b6ea69a720faf825aa93efe52e00105c4b5ffe31c'
HELPER = ROOT / 'eng/audit-budget-hotpath.py'
HELPER_SHA = 'd33f69318fec46e2cb16daaff114ff53c19c20b3dd69a0b709476ac105636a40'
FIXTURE = ROOT / 'artifacts/budget-batching/benchmark-inputs-20261014-attempt1'
CDB = Path('C:/Program Files (x86)/Windows Kits/10/Debuggers/x64/cdb.exe')
SYMBOL = 'coreclr!RuneCLRInstructionMeter::RecordBatch'
SAMPLES = 2
HIT_LIMIT = 100000


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    with Path(path).open('x', encoding='ascii') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def load(path, expected, name):
    need(sha(path) == expected, 'Frozen dependency differs: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def settings(interval):
    need(interval in (1, 100, 1000), 'Unsupported interval')
    return {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0',
            'DOTNET_ReadyToRun': '1', 'DOTNET_TieredCompilation': '0',
            'DOTNET_MULTILEVEL_LOOKUP': '0', 'DOTNET_RuneCLRPhaseAcquireLoad': '1',
            'DOTNET_RuneCLRDerivedLedger': '0', 'DOTNET_RuneCLRBatchInterval': format(interval, 'x')}


def check_hashes(values):
    for path, expected in values.items():
        need(sha(path) == expected, 'Input differs: ' + path)


def scripts(output, interval):
    # CDB numbers are hexadecimal: +40 means byte offset 64, +28 means 40.
    quote, newline = chr(92) + chr(34), chr(92) * 2 + 'n'
    fmt = ('BATCH_SAMPLE pid=%u interval=%u admitted=%u phase=%u terminal=%u phaseFlag=%u '
           'derived=%u meter=%p pc=%p caller=%p kind=%u' + newline)
    values = ('@$tpid,dwo(@rcx+40),@edx,dwo(@rcx+28),by(@rcx+1),'
              'by(@rcx+2),by(@rcx+3),@rcx,@rip,poi(@rsp),@$t4')
    emit = '.printf ' + quote + fmt + quote + ',' + values + ';ln poi(@rsp);k4;'
    full = '(@edx==0n' + str(interval) + ')'
    partial = '((@edx>0)&(@edx<0n' + str(interval) + '))'
    done = '(@$t0>=0n' + str(SAMPLES) + ')'
    if interval > 1:
        done = '(' + done + '&(@$t1>=0n' + str(SAMPLES) + '))'
    gate = ('((by(@rcx+1)==1)&(by(@rcx+2)==1)&(by(@rcx+3)==0)&'
            '(dwo(@rcx+28)==0)&(dwo(@rcx+40)==0n' + str(interval) + '))')
    command = ('r @$t2=@$t2+1;.if ' + gate + ' {'
               '.if (' + full + '&(@$t0<0n' + str(SAMPLES) + ')) {'
               'r @$t4=0;r @$t0=@$t0+1;' + emit + '};'
               '.if (' + partial + '&(@$t1<0n' + str(SAMPLES) + ')) {'
               'r @$t4=1;r @$t1=@$t1+1;' + emit + '};};'
               '.if ' + done + ' {bc 0;.printf ' + quote +
               'BATCH_DONE full=%u partial=%u hits=%u' + newline + quote + ',@$t0,@$t1,@$t2;};'
               '.if (@$t2>=0n' + str(HIT_LIMIT) + ') {bc 0;.printf ' + quote +
               'BATCH_CAP hits=%u' + newline + quote + ',@$t2;};gc')
    loaded = ['.printf "BATCH_MODULE pid=%u base=%p\\n", @$tpid, coreclr',
              'lmv m coreclr', '.reload /f coreclr.dll', 'x ' + SYMBOL,
              '.printf "BATCH_SYMBOL pc=%p\\n", ' + SYMBOL,
              'r @$t0=0', 'r @$t1=0', 'r @$t2=0',
              'bp0 ' + SYMBOL + ' "' + command + '"', 'g']
    initial = ('sxd 0xe0434352\nsxe -c "$><' +
               (output / 'loaded.cdb').as_posix() + '" ld:coreclr\ng\n')
    return {'initial.cdb': initial, 'loaded.cdb': '\n'.join(loaded) + '\n'}


def prepare(args):
    output, build = args.output.resolve(), args.build.resolve()
    need(not output.exists(), 'Fresh owned output required')
    request = read(build / 'request.json')
    checker = load(CHECKER, CHECKER_SHA, 'batch_capture_candidate')
    candidate = checker.validate(Path(request['runtime']))
    built, receipt = read(build / 'build-result.json'), read(build / 'layout-receipt.json')
    layout = build / 'layout'
    need(built['exitCode'] == 0 and receipt['passed'] and receipt['configuration'] == 'Release' and
         built['candidateValidation'] == receipt['candidateValidation'] == request['candidateValidation'] == candidate and
         receipt['candidateCommit'] == checker.COMMIT and Path(receipt['layout']).resolve() == layout and
         receipt['buildRequestSha256'] == sha(build / 'request.json') and
         receipt['buildResultSha256'] == sha(build / 'build-result.json'), 'Completed exact Release layout required')
    inputs = {str(path): sha(path) for path in (CHECKER, HELPER, CDB, build / 'request.json',
              build / 'build-result.json', build / 'layout-receipt.json')}
    for name, expected in built['sourceHashes'].items():
        current = Path(request['runtime']) / name
        frozen = build / 'source' / name
        need(sha(current) == sha(frozen) == expected, 'Exact build source snapshot differs: ' + name)
        inputs[str(current)] = inputs[str(frozen)] = expected
    for name, expected in receipt['allLayoutHashes'].items():
        need(sha(layout / name) == expected, 'Built private layout differs: ' + name)
        inputs[str(layout / name)] = expected
    for name in ('host', 'author'):
        for path in sorted((FIXTURE / name).iterdir()):
            if path.is_file():
                inputs[str(path)] = sha(path)
    host = FIXTURE / 'host/RuneCLR.BatchOverhead.dll'
    author = FIXTURE / 'author/RuneCLR.BatchKernel.dll'
    need(host.is_file() and author.is_file() and not (host.parent / author.name).exists(), 'Existing isolated flat fixture required')
    need(sha(host.parent / 'RuneCLR.Abstractions.dll') == sha(author.parent / 'RuneCLR.Abstractions.dll'), 'Shared contract differs')
    support = load(HELPER, HELPER_SHA, 'batch_capture_pe')
    core = layout / 'shared/Microsoft.NETCore.App/12.0.0/coreclr.dll'
    _, _, identity = support.pe_view(core.read_bytes())
    need(identity == support.pdb_identity(core.with_suffix('.pdb').read_bytes()) and
         sha(core) == built['criticalProductHashes']['coreclr.dll'], 'Native/PDB/build identity differs')
    output.mkdir(parents=True)
    nonce = uuid.uuid4().hex
    target = [str(layout / 'dotnet.exe'), 'exec', '--fx-version', '12.0.0', str(host), str(author),
              'high-budget', nonce, '3']
    for name, content in scripts(output, args.interval).items():
        (output / name).write_text(content, encoding='ascii')
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    argv = [str(CDB), '-G', '-y', str(core.parent), '-cf', str(output / 'initial.cdb'), *target]
    save(output / 'request.json', {'version': 1, 'build': str(build), 'candidateValidation': candidate,
         'inputHashes': inputs, 'commandHashes': {n: sha(output / n) for n in scripts(output, args.interval)},
         'driverSha256': sha(__file__), 'target': target, 'argv': argv, 'nonce': nonce,
         'interval': args.interval, 'settings': settings(args.interval), 'pePdbIdentity': identity,
         'sampleLimitPerKind': SAMPLES, 'debuggerHitLimit': HIT_LIMIT, 'fieldOffsets': {'batchInterval': 64, 'phase': 40},
         'symbol': SYMBOL, 'abi': {'meter': 'rcx', 'admitted': 'edx'}, 'benchmark': False,
         'performanceMeasured': False, 'hostStopwatchFieldsIgnored': True,
         'scope': 'Bounded RecordBatch samples in one flat workload; not an all-workload cadence or termination-bound proof.'})
    guard(output)
    save(output / 'preparation-review.json', {'passed': True, 'requestSha256': sha(output / 'request.json'),
         'nativeProcessExecuted': False, 'performanceMeasured': False})
    print(json.dumps({'passed': True, 'interval': args.interval, 'nativeProcessExecuted': False}))


def guard(output):
    request = read(output / 'request.json')
    need(request['driverSha256'] == sha(__file__) == sha(output / 'driver.py'), 'Frozen capture driver differs')
    need(request['settings'] == settings(request['interval']) and request['symbol'] == SYMBOL and
         request['fieldOffsets'] == {'batchInterval': 64, 'phase': 40}, 'Interval encoding or ABI differs')
    check_hashes(request['inputHashes'])
    for name, expected in request['commandHashes'].items():
        need(sha(output / name) == expected and (output / name).read_text() ==
             scripts(output, request['interval'])[name], 'Debugger script differs')
    need(request['target'][-3:] == ['high-budget', request['nonce'], '3'], 'Fixture nonce/mode differs')
    return request


def address(value):
    return int(value.replace(chr(96), ''), 16)


def assess_text(text, request):
    need('BATCH_CAP hits=' not in text, 'Debugger hit cap reached; raw attempt retained')
    digits = '[0-9a-fA-F' + chr(96) + ']+'
    modules = re.findall(r'^BATCH_MODULE pid=(\d+) base=(' + digits + r')\s*$', text, re.M)
    symbols = re.findall(r'^BATCH_SYMBOL pc=(' + digits + r')\s*$', text, re.M)
    need(len(modules) == len(symbols) == 1, 'One original target/module/symbol required')
    pid, base = int(modules[0][0]), address(modules[0][1])
    entry = address(symbols[0])
    pattern = (r'^BATCH_SAMPLE pid=(\d+) interval=(\d+) admitted=(\d+) phase=(\d+) '
               r'terminal=(\d+) phaseFlag=(\d+) derived=(\d+) meter=(' + digits + r') '
               r'pc=(' + digits + r') caller=(' + digits + r') kind=(\d+)\s*$')
    matches = list(re.finditer(pattern, text, re.M))
    interval = request['interval']
    need(len(matches) == (SAMPLES if interval == 1 else SAMPLES * 2), 'Bounded full/partial sample count differs')
    samples = []
    for index, match in enumerate(matches):
        row = match.groups()
        count, kind = int(row[2]), int(row[10])
        need(int(row[0]) == pid and int(row[1]) == interval and row[3:7] == ('0', '1', '1', '0') and
             address(row[8]) == entry and address(row[7]) != 0, 'Actual meter/entry/process binding differs')
        need((kind == 0 and count == interval) or (kind == 1 and 0 < count < interval), 'Full/partial classification differs')
        end = matches[index + 1].start() if index + 1 < len(matches) else text.index('BATCH_DONE', match.end())
        need('coreclr!InterpExecMethod' in text[match.end():end], 'Sample lacks actual interpreter caller stack')
        samples.append({'admitted': count, 'kind': 'full' if kind == 0 else 'partial',
                        'meter': row[7], 'entryPc': row[8], 'callerPc': row[9]})
    done = re.findall(r'^BATCH_DONE full=(\d+) partial=(\d+) hits=(\d+)\s*$', text, re.M)
    need(len(done) == 1 and int(done[0][0]) == SAMPLES and int(done[0][1]) ==
         (0 if interval == 1 else SAMPLES) and int(done[0][2]) <= HIT_LIMIT, 'Bounded debugger completion differs')
    need(sum(row['kind'] == 'full' for row in samples) == SAMPLES and sum(row['kind'] == 'partial'
         for row in samples) == (0 if interval == 1 else SAMPLES), 'Sample categories differ')
    receipts = []
    for line in text.splitlines():
        if line.startswith('{'):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get('nonce') == request['nonce']:
                receipts.append(value)
    need(len(receipts) == 1, 'One original managed fixture receipt required')
    receipt = receipts[0]
    need(receipt['passed'] and receipt['processId'] == pid and receipt['mode'] == 'high-budget' and
         receipt['sampleCount'] == 3 and receipt['warmups'] == 3 and receipt['directCollected'] and
         receipt['sessionCollected'] == 6 and receipt['affinity'] == 4 and receipt['architecture'] == 'X64' and
         not receipt['hostProof']['Interpreted'] and len(receipt['Proof']) == 1 and
         receipt['Proof'][0]['Interpreted'] and receipt['Proof'][0]['StubType'] == 6 and
         receipt['Proof'][0]['Method'] == 'RuneCLR.BatchKernel.Kernel.Execute', 'Fixture interpretation/collection controls differ')
    need(len(receipt['Callbacks']) == 3 and all(row['Checksum'] == 12749776 and row['DispatchDelta'] == 2100016
         for row in receipt['Callbacks']) and len(receipt['Samples']) == 6 and
         all(row['Checksum'] == 3 * 12749776 and row['Budget']['ExecutionExecuted'] == 6300101 and
             not row['Budget']['IsTerminated'] for row in receipt['Samples']) and
         receipt['FinalSnapshot']['ExecutionExecuted'] == 12600096, 'Flat checksum/ledger differs')
    return {'passed': True, 'actualTargetPid': pid, 'actualMeterInterval': interval,
            'entryRva': entry - base, 'samples': samples, 'debuggerHits': int(done[0][2]),
            'managedReceipt': receipt, 'collections': 7, 'performanceMeasured': False,
            'hostStopwatchFieldsIgnored': True}


def review(output):
    request = guard(output)
    execution = read(output / 'execution.json')
    need(execution['exitCode'] == 0 and not execution['timedOut'], 'Owned debugger execution did not complete')
    for name in ('stdout', 'stderr'):
        need(sha(output / ('cdb.' + name)) == execution[name + 'Sha256'], 'Original debugger stream differs')
    report = assess_text((output / 'cdb.stdout').read_text(errors='replace'), request)
    helper = load(HELPER, HELPER_SHA, 'batch_capture_review_pe')
    core = Path(request['build']) / 'layout/shared/Microsoft.NETCore.App/12.0.0/coreclr.dll'
    _, read_rva, identity = helper.pe_view(core.read_bytes())
    need(list(identity) == request['pePdbIdentity'] == list(helper.pdb_identity(core.with_suffix('.pdb').read_bytes())), 'Original matching PE/PDB differs')
    report.update({'entryFileBytes': read_rva(report['entryRva'], 16).hex(), 'nativeSha256': sha(core),
                   'pdbSha256': sha(core.with_suffix('.pdb')), 'pePdbIdentity': identity,
                   'requestSha256': sha(output / 'request.json')})
    return report


def run(output):
    request = guard(output)
    need(not (output / 'process.json').exists() and not (output / 'execution.json').exists(), 'Prepared capture already launched')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_'))}
    env.update(request['settings'])
    timed_out = False
    with (output / 'cdb.stdout').open('xb') as stdout, (output / 'cdb.stderr').open('xb') as stderr:
        process = subprocess.Popen(request['argv'], env=env, cwd=ROOT, stdout=stdout, stderr=stderr)
        save(output / 'process.json', {'controllerPid': process.pid, 'target': request['target'],
                                      'settings': request['settings'], 'owned': True})
        try:
            code = process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            timed_out = True
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, check=False)
            process.wait()
            code = process.returncode
    save(output / 'execution.json', {'controllerPid': process.pid, 'exitCode': code, 'timedOut': timed_out,
         'stdoutSha256': sha(output / 'cdb.stdout'), 'stderrSha256': sha(output / 'cdb.stderr'), 'performanceMeasured': False})
    result = review(output)
    save(output / 'results.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'managedReceipt'}, indent=2))


def selftest(output):
    need(not output.exists(), 'Fresh offline checks output required')
    ast.parse(Path(__file__).read_text())
    checks = []
    for interval, encoding in ((1, '1'), (100, '64'), (1000, '3e8')):
        need(settings(interval)['DOTNET_RuneCLRBatchInterval'] == encoding and int(encoding, 16) == interval, 'Hex encoding differs')
        content = scripts(output, interval)['loaded.cdb']
        need('dwo(@rcx+40)==0n' + str(interval) in content and 'r @$t4=1' in content and
             'bp0 ' + SYMBOL in content and 'bc 0;' in content and '0n100000' in content and
             len(content.splitlines()) == 10,
             'Bounded CDB script structure differs')
        checks.append('N' + str(interval) + '-hex-and-bounded-script')
    for wrong in ('100', '1000'):
        need(int(wrong, 16) not in (100, 1000), 'Decimal-as-hex negative control differs')
        checks.append('reject-decimal-as-hex-' + wrong)
    output.mkdir(parents=True)
    save(output / 'results.json', {'passed': True, 'checks': checks, 'nativeProcessExecuted': False,
                                 'performanceMeasured': False, 'driverSha256': sha(__file__)})
    print(json.dumps(read(output / 'results.json'), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    lane = sub.add_parser('prepare')
    lane.add_argument('--build', type=Path, required=True)
    lane.add_argument('--interval', type=int, choices=(1, 100, 1000), required=True)
    lane.add_argument('--output', type=Path, required=True)
    for action in ('run', 'review'):
        lane = sub.add_parser(action)
        lane.add_argument('--prepared', type=Path, required=True)
    sub.add_parser('selftest').add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args)
    elif args.action == 'run':
        run(args.prepared.resolve())
    elif args.action == 'review':
        print(json.dumps(review(args.prepared.resolve()), indent=2))
    else:
        selftest(args.output.resolve())


if __name__ == '__main__':
    main()
