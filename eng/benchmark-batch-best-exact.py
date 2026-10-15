#!/usr/bin/env python3
"""Compare derived-ledger exact admission with batching on identical Release IL."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess
import uuid

BASE_PATH = Path(__file__).with_name('benchmark-batch-interval.py')
SPEC = importlib.util.spec_from_file_location('batch_contract', BASE_PATH)
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)
PROFILES = {'exact-before': (0, 1), 'hundred': (100, 0),
            'thousand': (1000, 0), 'exact-after': (0, 1)}


def settings(interval, derived):
    value = BASE.settings(interval)
    value['DOTNET_RuneCLRDerivedLedger'] = str(derived)
    return value


def plan(smoke):
    return [(name, n, d, workload, pair, mode)
            for name, (n, d) in PROFILES.items() for workload in BASE.COUNTS
            for pair in range(1 if smoke else 2)
            for mode in (('high-budget',) if smoke else
                         (('no-config', 'high-budget') if pair == 0 else ('high-budget', 'no-config')))]


def argv(build, lane, samples):
    host, author = BASE.images(lane['workload'])
    value = [str(build/'layout/dotnet.exe'), 'exec', '--fx-version', '12.0.0',
             str(host), str(author), lane['mode']]
    if lane['workload'] != 'arithmetic':
        value.append(lane['workload'])
    return value + [lane['nonce'], str(samples)]


def validate(lane, samples):
    BASE.need(PROFILES[lane['profile']] == (lane['interval'], lane['derived']), 'Exact/batch profile differs.')
    BASE.need(lane['raw']['settings'] == settings(lane['interval'], lane['derived']), 'Actual derived/interval settings differ.')
    # The frozen fixture contract is identical; check our distinct settings before reuse.
    adapted = dict(lane, raw=dict(lane['raw'], settings=BASE.settings(lane['interval'])))
    BASE.validate(adapted, samples)


def summarize(lanes):
    result = {}
    keys = ('callbackMedianMs', 'sessionMedianMs')
    for workload in BASE.COUNTS:
        rows = {}
        for profile in PROFILES:
            row = {}
            for mode in ('no-config', 'high-budget'):
                receipts = [x['receipt'] for x in lanes if x['profile'] == profile and
                            x['workload'] == workload and x['mode'] == mode]
                row[mode] = {'callbackMedianMs': statistics.median(x['Milliseconds'] for r in receipts for x in r['Callbacks']),
                             'sessionMedianMs': statistics.median(x['Milliseconds'] for r in receipts for x in r['Samples'] if not x['Warmup'])}
            row['configuredRatio'] = {k: row['high-budget'][k]/row['no-config'][k] for k in keys}
            rows[profile] = row
        for profile in ('hundred', 'thousand'):
            rows[profile]['budgetedTimeReductionPercent'] = {
                bracket: {k: 100*(1-rows[profile]['high-budget'][k]/rows[bracket]['high-budget'][k]) for k in keys}
                for bracket in ('exact-before', 'exact-after')}
        rows['exactBudgetDriftPercent'] = {k: 100*(rows['exact-after']['high-budget'][k]/rows['exact-before']['high-budget'][k]-1) for k in keys}
        result[workload] = rows
    return result


def controls(lanes, samples):
    lane = next(x for x in lanes if x['mode'] == 'high-budget')
    edits = [lambda x: x['raw']['settings'].__setitem__('DOTNET_RuneCLRDerivedLedger', '0'),
             lambda x: x['raw']['settings'].__setitem__('DOTNET_RuneCLRBatchInterval', '64'),
             lambda x: x['receipt'].__setitem__('directCollected', False),
             lambda x: x['receipt']['Callbacks'][0].__setitem__('Checksum', -1),
             lambda x: x['receipt']['FinalSnapshot'].__setitem__('ExecutionExecuted', 0),
             lambda x: x['receipt']['Proof'][0].__setitem__('Interpreted', False)]
    for edit in edits:
        changed = copy.deepcopy(lane)
        edit(changed)
        try:
            validate(changed, samples)
        except RuntimeError:
            continue
        raise RuntimeError('Corrupted best-exact control accepted.')
    return len(edits)


def review(build, output):
    request, result = BASE.read(output/'request.json'), BASE.read(output/'results.json')
    BASE.need(request['driverSha256'] == BASE.sha(__file__) and request['contractSha256'] == BASE.sha(BASE_PATH) and
              request['buildDirectory'] == str(build) and result['requestSha256'] == BASE.sha(output/'request.json'), 'Frozen request/driver/build differs.')
    BASE.check_hashes(request['inputHashes'])
    expected = [list(x) for x in plan(request['smoke'])]
    observed = [[x[k] for k in ('profile', 'interval', 'derived', 'workload', 'pair', 'mode')] for x in result['lanes']]
    BASE.need(request['plan'] == observed == expected, 'Canonical exact-before/batch/exact-after plan differs.')
    for lane in result['lanes']:
        for suffix in ('stdout', 'stderr'):
            BASE.need(BASE.sha(output/(lane['label']+'.'+suffix)) == lane['raw'][suffix+'Sha256'], 'Original raw stream differs.')
        BASE.need(BASE.read(output/(lane['label']+'.command.json')) == lane['raw'] and
                  BASE.read(output/(lane['label']+'.stdout')) == lane['receipt'] and
                  lane['raw']['argv'] == argv(build, lane, request['samples']), 'Original argv/receipt differs.')
        validate(lane, request['samples'])
    BASE.need(len({x['nonce'] for x in result['lanes']}) == len(expected) and
              len({x['raw']['pid'] for x in result['lanes']}) == len(expected), 'Fresh owned identities missing.')
    BASE.need(result['passed'] and result['collections'] == len(expected)*(request['samples']+4) and
              result['processes'] == len(expected) and result['negativeControls'] == controls(result['lanes'], request['samples']) and
              result['performanceMeasured'] == (not request['smoke']), 'Result scope/count differs.')
    if result['performanceMeasured']:
        BASE.need(result['summaries'] == summarize(result['lanes']), 'Recomputed exact/batch medians differ.')
    return {'passed': True, 'processes': len(expected), 'collections': result['collections'],
            'negativeControls': result['negativeControls'], 'performanceMeasured': result['performanceMeasured']}


def run(build, output, boundary, smoke):
    inputs = BASE.all_inputs(build)
    inputs[str(Path(__file__).resolve())] = BASE.sha(__file__)
    boundary_request = boundary.parent/'request.json'
    profile = BASE.read(boundary_request)['profile']
    layout = BASE.read(build/'layout-receipt.json')
    BASE.need(BASE.read(boundary)['passed'] and profile['sourceCommit'] == layout['candidateCommit'], 'Passing same-source boundary required.')
    for key, relative in [('dotnet', 'dotnet.exe'), ('native', 'shared/Microsoft.NETCore.App/12.0.0/coreclr.dll'),
                          ('corelib', 'shared/Microsoft.NETCore.App/12.0.0/System.Private.CoreLib.dll')]:
        BASE.need(profile[key+'Sha256'] == BASE.sha(build/'layout'/relative), 'Boundary product differs: '+key)
    for path in (boundary, boundary_request):
        inputs[str(path)] = BASE.sha(path)
    output.mkdir(parents=True, exist_ok=False)
    samples = 3 if smoke else 9
    request = {'driverSha256': BASE.sha(__file__), 'contractSha256': BASE.sha(BASE_PATH), 'inputHashes': inputs,
               'buildDirectory': str(build), 'samples': samples, 'smoke': smoke, 'plan': plan(smoke),
               'scope': 'Same Release binary/IL; exact derived-ledger ON brackets, batches use independent counter; single worker.'}
    BASE.save(output/'request.json', request)
    lanes = []
    for name, n, d, workload, pair, mode in plan(smoke):
        lane = {'profile': name, 'interval': n, 'derived': d, 'workload': workload,
                'pair': pair, 'mode': mode, 'nonce': uuid.uuid4().hex}
        label = str(len(lanes)).zfill(2)+'-'+name+'-'+workload+'-'+mode+'-'+lane['nonce']
        lane['label'] = label
        env = {k:v for k,v in os.environ.items() if not k.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_'))}
        cfg = settings(n, d)
        env.update(cfg)
        host, author = BASE.images(workload)
        BASE.check_hashes({str(p): inputs[str(p)] for p in (host, author)})
        command = argv(build, lane, samples)
        process = subprocess.Popen(command, cwd=BASE.ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            stdout, stderr = process.communicate()
        (output/(label+'.stdout')).write_bytes(stdout)
        (output/(label+'.stderr')).write_bytes(stderr)
        lane['raw'] = {'argv': command, 'settings': cfg, 'pid': process.pid, 'exitCode': process.returncode,
                       'timedOut': timed_out, 'stdoutSha256': BASE.sha(output/(label+'.stdout')),
                       'stderrSha256': BASE.sha(output/(label+'.stderr'))}
        BASE.save(output/(label+'.command.json'), lane['raw'])
        BASE.need(process.returncode == 0 and not timed_out, 'Owned probe failed; preserved: '+label)
        lane['receipt'] = json.loads(stdout)
        validate(lane, samples)
        lanes.append(lane)
        BASE.save(output/('partial-'+str(len(lanes)).zfill(2)+'.json'), {'passed': False, 'lanes': lanes})
        print(label+': passed', flush=True)
    BASE.check_hashes(inputs)
    result = {'passed': True, 'processes': len(lanes), 'collections': len(lanes)*(samples+4),
              'performanceMeasured': not smoke, 'negativeControls': controls(lanes, samples),
              'requestSha256': BASE.sha(output/'request.json'), 'lanes': lanes}
    if not smoke:
        result['summaries'] = summarize(lanes)
    BASE.save(output/'results.json', result)
    print(json.dumps(review(build, output), indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('smoke', 'run', 'review'))
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--boundary', type=Path)
    args = p.parse_args()
    build, output = args.build.resolve(), args.output.resolve()
    if args.mode == 'review':
        print(json.dumps(review(build, output), indent=2))
    else:
        BASE.need(args.boundary is not None, '--boundary required.')
        run(build, output, args.boundary.resolve(), args.mode == 'smoke')


if __name__ == '__main__':
    main()
