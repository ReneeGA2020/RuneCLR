#!/usr/bin/env python3
"""Run actual 1/100/1000 budget-interval controls and a same-binary bracket."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
FLAT = ROOT / 'artifacts/budget-batching/benchmark-inputs-20261014-attempt1'
REP = ROOT / 'artifacts/representative-budget/functional-20261014-attempt3'
INTERVALS = {'exact': 0, 'one-before': 1, 'hundred': 100, 'thousand': 1000, 'one-after': 1}
COUNTS = {'arithmetic': (2100016, 6300101), 'entities': (4135081, 12405370), 'host-api': (229908, 689851)}
LIMIT = 1_000_000_000_000


def need(value, message):
    if not value:
        raise RuntimeError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    with Path(path).open('x', encoding='ascii') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def images(workload):
    directory = FLAT if workload == 'arithmetic' else REP
    return (directory / 'host' / ('RuneCLR.BatchOverhead.dll' if workload == 'arithmetic' else 'RuneCLR.BudgetWorkloads.dll'),
            directory / 'author' / ('RuneCLR.BatchKernel.dll' if workload == 'arithmetic' else 'RuneCLR.BudgetWorkloadScripts.dll'))


def build_inputs(build):
    result, layout = read(build / 'build-result.json'), read(build / 'layout-receipt.json')
    need(result['exitCode'] == 0 and layout['passed'] and layout['configuration'] == 'Release', 'Successful matching Release build required.')
    need(layout['buildRequestSha256'] == sha(build / 'request.json') and
         layout['buildResultSha256'] == sha(build / 'build-result.json'), 'Build receipt chain differs.')
    source = Path(layout['runtime'])
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    need(head == layout['candidateCommit'] and not subprocess.check_output(
        ['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no'], text=True).strip(), 'Built source identity differs.')
    inputs = {str(build / name): sha(build / name) for name in ('request.json', 'build-result.json', 'layout-receipt.json')}
    for name, expected in result['sourceHashes'].items():
        need(sha(source / name) == sha(build / 'source' / name) == expected, 'Built source bytes differ: ' + name)
        inputs[str(source / name)] = expected
    for name, expected in layout['allLayoutHashes'].items():
        need(sha(build / 'layout' / name) == expected, 'Private layout differs: ' + name)
        inputs[str(build / 'layout' / name)] = expected
    need('RuneCLRBatchInterval' in (source / 'src/coreclr/inc/clrconfigvalues.h').read_text(), 'Interval experiment declaration missing.')
    return inputs


def all_inputs(build):
    result = build_inputs(build)
    for directory in (FLAT, REP):
        for subdir in ('host', 'author'):
            for path in (directory / subdir).iterdir():
                if path.is_file():
                    result[str(path)] = sha(path)
    for directory in ('benchmarks/RuneCLR.BatchKernel', 'benchmarks/RuneCLR.BatchOverhead'):
        for path in (ROOT / directory).iterdir():
            if path.is_file():
                result[str(path)] = sha(path)
    for path in (FLAT / 'baseline-smoke.json', FLAT / 'baseline-smoke.stdout', Path(__file__).resolve()):
        result[str(path)] = sha(path)
    need(read(FLAT / 'baseline-smoke.json')['callbackDispatches'] == COUNTS['arithmetic'][0], 'Flat-loop calibration differs.')
    need(not (FLAT / 'host/RuneCLR.BatchKernel.dll').exists() and
         sha(FLAT / 'host/RuneCLR.Abstractions.dll') == sha(FLAT / 'author/RuneCLR.Abstractions.dll'), 'Collectible author isolation differs.')
    return result


def check_hashes(values):
    for path, expected in values.items():
        need(sha(path) == expected, 'Input changed: ' + path)


def settings(interval):
    return {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0', 'DOTNET_ReadyToRun': '1',
            'DOTNET_TieredCompilation': '0', 'DOTNET_MULTILEVEL_LOOKUP': '0',
            'DOTNET_RuneCLRPhaseAcquireLoad': '1', 'DOTNET_RuneCLRDerivedLedger': '0',
            # CoreCLR DWORD environment switches parse hexadecimal values.
            'DOTNET_RuneCLRBatchInterval': format(interval, 'x')}


def oracle(workload, ticks=1):
    if workload == 'arithmetic':
        return 12749776 * ticks
    if workload == 'host-api':
        n = 8192 * ticks
        return n * (n + 1) // 2
    value = sum((13*i + 200*(i % 7+1)) % 65521 + (17*i + 200*(i % 11+1)) % 65521 +
                (100 + 200*i + 200*199//2) % 1000 for i in range(512))
    return value * ticks


def snapshot(value, count):
    need(value == {'ExecutionRemaining': LIMIT-count, 'ExecutionExecuted': count, 'ExecutionExhausted': False,
                  'IsTerminated': False, 'Reason': 0, 'Phase': 0, 'CleanupRemaining': 4096, 'CleanupExecuted': 0}, 'Exact completed ledger differs.')


def validate(lane, sample_count):
    r, raw, workload, mode = lane['receipt'], lane['raw'], lane['workload'], lane['mode']
    need(lane['interval'] in (0, 1, 100, 1000) and mode in ('no-config', 'high-budget'), 'Unknown interval/mode.')
    need(r['passed'] and raw['exitCode'] == 0 and not raw['timedOut'] and r['processId'] == raw['pid'] and
         r['nonce'] == lane['nonce'] and r['mode'] == mode and raw['settings'] == settings(lane['interval']), 'Actual process/interval binding differs.')
    need(r['affinity'] == 4 and r['sampleCount'] == sample_count and r['warmups'] == 3 and r['directCollected'] and
         r['sessionCollected'] == sample_count + 3 and len(r['Callbacks']) == sample_count and
         len(r['Samples']) == sample_count + 3 and [x['Warmup'] for x in r['Samples']] == [True]*3 + [False]*sample_count,
         'Actual sample/collection count differs.')
    need(r['architecture'] == 'X64' and r['runtime'].startswith('.NET 12.') and not r['hostProof']['Interpreted'] and
         len(r['Proof']) == (1 if workload == 'arithmetic' else 2) and
         all(p['Interpreted'] and p['StubType'] == 6 for p in r['Proof']), 'Actual runtime/selected-entry controls differ.')
    if workload != 'arithmetic':
        need(r['workload'] == workload and all(not p['Interpreted'] for p in r['trustedAdapterProof']), 'Trusted adapter/workload differs.')
    delta, session_count = COUNTS[workload]
    for i, x in enumerate(r['Callbacks']):
        need(math.isfinite(x['Milliseconds']) and x['Milliseconds'] > 0 and x['Checksum'] == oracle(workload), 'Callback checksum/time differs.')
        expected = (delta*(3+i), delta*(4+i), delta) if mode == 'high-budget' else (None, None, None)
        need((x['ExecutedBefore'], x['ExecutedAfter'], x['DispatchDelta']) == expected, 'Actual callback count/partial flush differs.')
    for x in r['Samples']:
        need(math.isfinite(x['Milliseconds']) and x['Milliseconds'] > 0 and x['Checksum'] == oracle(workload, 3), 'Session checksum/time differs.')
        if mode == 'high-budget':
            snapshot(x['Budget'], session_count)
        else:
            need(x['Budget'] is None, 'Unexpected no-config meter.')
        if workload != 'arithmetic':
            resources = 24576 if workload == 'host-api' else 0
            logs = ['benchmark-tick']*384 if resources else []
            logs += ['budget-workloads:' + workload + ':starts=1;sum=' + str(oracle(workload, 3))]
            need(x['CompletedTicks'] == 3 and x['CreatedEntities'] == x['ReleasedEntities'] == resources and
                 x['RemainingEntities'] == 0 and x['Logs'] == logs, 'Session resources/static reset differs.')
    if mode == 'high-budget':
        snapshot(r['FinalSnapshot'], delta*(sample_count+3))
    else:
        need(r['FinalSnapshot'] is None, 'Unexpected no-config final meter.')


def summarize(lanes):
    result = {}
    for workload in COUNTS:
        result[workload] = {}
        for profile in INTERVALS:
            row = {}
            for mode in ('no-config', 'high-budget'):
                rs = [x['receipt'] for x in lanes if x['workload'] == workload and x['profile'] == profile and x['mode'] == mode]
                row[mode] = {'processes': len(rs), 'callbackMedianMs': statistics.median(x['Milliseconds'] for r in rs for x in r['Callbacks']),
                             'sessionMedianMs': statistics.median(x['Milliseconds'] for r in rs for x in r['Samples'] if not x['Warmup'])}
            row['configuredRatio'] = {key: row['high-budget'][key]/row['no-config'][key] for key in ('callbackMedianMs', 'sessionMedianMs')}
            result[workload][profile] = row
        for profile in ('hundred', 'thousand'):
            result[workload][profile]['budgetedTimeReductionPercent'] = {
                bracket: {key: 100*(1-result[workload][profile]['high-budget'][key]/result[workload][bracket]['high-budget'][key])
                          for key in ('callbackMedianMs', 'sessionMedianMs')} for bracket in ('exact', 'one-before', 'one-after')}
    return result


def run(build, output, smoke, boundary):
    build, output = build.resolve(), output.resolve()
    inputs = all_inputs(build)
    if not smoke:
        need(boundary is not None and read(boundary)['passed'], 'Passing actual boundary receipt required before timing.')
        boundary_request = boundary.parent / 'request.json'
        profile = read(boundary_request)['profile']
        layout = read(build / 'layout-receipt.json')
        need(profile['sourceCommit'] == layout['candidateCommit'] and
             profile['dotnetSha256'] == sha(build/'layout/dotnet.exe') and
             profile['nativeSha256'] == sha(build/'layout/shared/Microsoft.NETCore.App/12.0.0/coreclr.dll') and
             profile['corelibSha256'] == sha(build/'layout/shared/Microsoft.NETCore.App/12.0.0/System.Private.CoreLib.dll'),
             'Boundary acceptance must use the measured source/native/CoreLib layout.')
        inputs[str(boundary.resolve())] = sha(boundary)
        inputs[str(boundary_request.resolve())] = sha(boundary_request)
    output.mkdir(parents=True, exist_ok=False)
    samples, pairs = (3, 1) if smoke else (9, 2)
    profiles = {'off': 0, 'one-before': 1, 'hundred': 100, 'thousand': 1000} if smoke else INTERVALS
    plan = [(profile, interval, workload, pair, mode) for profile, interval in profiles.items() for workload in COUNTS
            for pair in range(pairs) for mode in (('high-budget',) if smoke else
                (('no-config', 'high-budget') if pair % 2 == 0 else ('high-budget', 'no-config')))]
    request = {'driverSha256': sha(__file__), 'buildDirectory': str(build), 'inputHashes': inputs,
               'smoke': smoke, 'samples': samples, 'pairs': pairs, 'plan': plan,
               'performanceMeasured': not smoke, 'baseline': 'Same experimental binary; no configured meter still retains instrumentation/owner lookup.',
               'scope': 'Single Windows x64 worker. Boundary flushes may shorten effective batches; interval1/100/1000 semantics require separate termination/cadence evidence.'}
    save(output / 'request.json', request)
    lanes = []
    for profile, interval, workload, pair, mode in plan:
        host, author = images(workload)
        nonce = uuid.uuid4().hex
        argv = [str(build/'layout/dotnet.exe'), 'exec', '--fx-version', '12.0.0', str(host), str(author), mode]
        if workload != 'arithmetic':
            argv.append(workload)
        argv += [nonce, str(samples)]
        env = {k:v for k,v in os.environ.items() if not k.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_'))}
        env.update(settings(interval))
        check_hashes({str(p): inputs[str(p)] for p in (host, author)})
        label = str(len(lanes)).zfill(2) + '-' + profile + '-' + workload + '-' + mode + '-' + nonce
        process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            stdout, stderr = process.communicate()
        (output / (label+'.stdout')).write_bytes(stdout)
        (output / (label+'.stderr')).write_bytes(stderr)
        raw = {'argv': argv, 'settings': settings(interval), 'pid': process.pid, 'exitCode': process.returncode,
               'timedOut': timed_out, 'stdoutSha256': sha(output/(label+'.stdout')), 'stderrSha256': sha(output/(label+'.stderr'))}
        save(output / (label+'.command.json'), raw)
        need(process.returncode == 0 and not timed_out, 'Owned probe failed; raw evidence retained: ' + label)
        lane = {'profile': profile, 'interval': interval, 'workload': workload, 'pair': pair, 'mode': mode,
                'nonce': nonce, 'label': label, 'raw': raw, 'receipt': json.loads(stdout)}
        validate(lane, samples)
        lanes.append(lane)
        save(output / ('partial-'+str(len(lanes)).zfill(2)+'.json'), {'passed': False, 'lanes': lanes})
        print(label + ': passed', flush=True)
    check_hashes(inputs)
    result = {'passed': True, 'processes': len(lanes), 'collections': len(lanes)*(samples+4), 'performanceMeasured': not smoke,
              'requestSha256': sha(output/'request.json'), 'lanes': lanes}
    if not smoke:
        result['summaries'] = summarize(lanes)
    save(output / 'results.json', result)
    print(json.dumps({k:v for k,v in result.items() if k != 'lanes'}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('smoke', 'run', 'review'))
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--boundary', type=Path)
    args = parser.parse_args()
    if args.mode != 'review':
        run(args.build, args.output, args.mode == 'smoke', args.boundary)
        return
    request, result = read(args.output/'request.json'), read(args.output/'results.json')
    need(request['driverSha256'] == sha(__file__) and result['requestSha256'] == sha(args.output/'request.json') and
         request['buildDirectory'] == str(args.build.resolve()), 'Original driver/build request differs.')
    check_hashes(request['inputHashes'])
    observed_plan = [[x['profile'], x['interval'], x['workload'], x['pair'], x['mode']] for x in result['lanes']]
    need(observed_plan == request['plan'], 'Original interval/workload/mode order differs.')
    for lane in result['lanes']:
        for suffix in ('stdout', 'stderr'):
            need(sha(args.output/(lane['label']+'.'+suffix)) == lane['raw'][suffix+'Sha256'], 'Raw stream changed.')
        need(read(args.output/(lane['label']+'.command.json')) == lane['raw'] and
             read(args.output/(lane['label']+'.stdout')) == lane['receipt'], 'Original raw command/receipt differs.')
        host, author = images(lane['workload'])
        expected_argv = [str(args.build.resolve()/'layout/dotnet.exe'), 'exec', '--fx-version', '12.0.0', str(host), str(author), lane['mode']]
        if lane['workload'] != 'arithmetic':
            expected_argv.append(lane['workload'])
        expected_argv += [lane['nonce'], str(request['samples'])]
        need(lane['raw']['argv'] == expected_argv, 'Actual private launch executable/arguments differ.')
        validate(lane, request['samples'])
    need(len(result['lanes']) == len(request['plan']) and len({x['raw']['pid'] for x in result['lanes']}) == len(result['lanes']) and
         len({x['nonce'] for x in result['lanes']}) == len(result['lanes']), 'Independent processes/nonces missing.')
    need(result['collections'] == len(result['lanes'])*(request['samples']+4), 'Collection summary differs.')
    if result['performanceMeasured']:
        need(result['summaries'] == summarize(result['lanes']), 'Recomputed medians/ratios differ.')
    print(json.dumps({'passed': True, 'processes': len(result['lanes']), 'collections': result['collections'],
                      'performanceMeasured': result['performanceMeasured']}))


if __name__ == '__main__':
    main()
