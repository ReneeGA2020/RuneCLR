#!/usr/bin/env python3
"""Run functional entity/API controls; durations are not benchmark results."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 1_000_000_000_000
PROFILES = {
    'parent': ('phase-load', 'a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186', '0'),
    'off': ('derived-ledger', '29ff781e157be82ba5a398a60bb05291e4a865af', '0'),
    'on': ('derived-ledger', '29ff781e157be82ba5a398a60bb05291e4a865af', '1'),
}

def require(value, message):
    if not value:
        raise RuntimeError(message)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def save(path, value):
    with Path(path).open('x', encoding='ascii') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')

def oracle(workload, ticks=1):
    if workload == 'host-api':
        n = 8192 * ticks
        return n * (n + 1) // 2
    total = sum((13*i + 200*(i%7+1)) % 65521 +
                (17*i + 200*(i%11+1)) % 65521 +
                (100 + 200*i + 200*199//2) % 1000 for i in range(512))
    return ticks * total

def snapshot(value):
    require(value['ExecutionExecuted'] > 0 and
            value['ExecutionRemaining'] + value['ExecutionExecuted'] == LIMIT and
            value['CleanupRemaining'] == 4096 and value['CleanupExecuted'] == 0 and
            not value['ExecutionExhausted'] and not value['IsTerminated'] and
            value['Reason'] == value['Phase'] == 0, 'Native ledger conservation differs.')

def launch(profile, workload, mode, nonce, output):
    kind, _, switch = PROFILES[profile]
    layout = ROOT / 'artifacts' / kind / 'windows-release-build-20261014-attempt1/layout'
    argv = [layout / 'dotnet.exe', 'exec', '--fx-version', '12.0.0',
            output / 'host/RuneCLR.BudgetWorkloads.dll',
            output / 'author/RuneCLR.BudgetWorkloadScripts.dll', mode, workload, nonce, '1']
    settings = {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0',
                'DOTNET_ReadyToRun': '1', 'DOTNET_TieredCompilation': '0',
                'DOTNET_MULTILEVEL_LOOKUP': '0', 'DOTNET_RuneCLRPhaseAcquireLoad': '1',
                'DOTNET_RuneCLRDerivedLedger': switch}
    return [str(arg) for arg in argv], settings

def validate(receipt, lane, output):
    require(lane['profile'] in PROFILES, 'Unknown runtime profile.')
    workload, mode = lane['workload'], lane['mode']
    argv, settings = launch(lane['profile'], workload, mode, lane['nonce'], output)
    require(lane['raw']['argv'] == argv and lane['raw']['settings'] == settings and
            lane['raw']['exitCode'] == 0, 'Actual launch runtime/profile settings differ.')
    require(receipt['passed'] and receipt['processId'] == lane['raw']['pid'] and
            receipt['nonce'] == lane['nonce'] and receipt['mode'] == mode and
            receipt['workload'] == workload and receipt['architecture'] == 'X64' and
            receipt['runtime'].startswith('.NET 12.') and receipt['affinity'] == 4 and
            receipt['sampleCount'] == 1 and receipt['warmups'] == 3 and
            receipt['iterations'] == (200 if workload == 'entities' else 8192),
            'Process/workload identity differs.')
    require(receipt['directCollected'] and receipt['sessionCollected'] == 4, 'Collection missing.')
    proof = receipt['Proof']
    expected = ['RuneCLR.BudgetWorkloadScripts.WorkloadEntries.' +
                ('Entities' if workload == 'entities' else 'HostApi'),
                'RuneCLR.Performance.Workloads.' +
                ('EntitiesObjects' if workload == 'entities' else 'HostApi')]
    require([p['Method'] for p in proof] == expected and
            all(p['Interpreted'] and p['StubType'] == 6 for p in proof), 'Selected author entries differ.')
    require(not receipt['hostProof']['Interpreted'] and
            receipt['hostProof']['Method'] == 'RuneCLR.Runtime.MapRunner.Run' and
            [p['Method'] for p in receipt['trustedAdapterProof']] ==
            ['BenchmarkMapContext.SpawnEntity', 'BenchmarkMapContext.DestroyEntity'] and
            all(not p['Interpreted'] for p in receipt['trustedAdapterProof']), 'Trusted adapter controls differ.')
    require(len(receipt['Callbacks']) == 1 and len(receipt['Samples']) == 4 and
            [s['Warmup'] for s in receipt['Samples']] == [True, True, True, False], 'Sample inventory differs.')
    callback = receipt['Callbacks'][0]
    require(callback['Checksum'] == oracle(workload), 'Callback independent oracle differs.')
    require(callback['AllocatedBytes'] >= 0 and len(callback['GcCounts']) == 3 and
            all(n >= 0 for n in callback['GcCounts']), 'Allocation/GC observation differs.')
    resources = 0 if workload == 'entities' else 24576
    expected_logs = (['benchmark-tick'] * 384 if resources else []) + [
        'budget-workloads:' + workload + ':starts=1;sum=' + str(oracle(workload, 3))]
    for sample in receipt['Samples']:
        require(sample['Checksum'] == oracle(workload, 3) and sample['CompletedTicks'] == 3 and
                sample['CreatedEntities'] == sample['ReleasedEntities'] == resources and
                sample['RemainingEntities'] == 0 and sample['Logs'] == expected_logs,
                'Session oracle/static/resource observations differ.')
    if mode == 'no-config':
        require(receipt['budgetLimit'] is None and receipt['FinalSnapshot'] is None and
                all(callback[key] is None for key in ('ExecutedBefore', 'ExecutedAfter', 'DispatchDelta')) and
                all(s['Budget'] is None for s in receipt['Samples']), 'No-config meter unexpectedly present.')
        return None
    require(receipt['budgetLimit'] == LIMIT and receipt['cleanupLimit'] == 4096, 'Budget limits differ.')
    delta = callback['DispatchDelta']
    require(delta > 0 and callback['ExecutedBefore'] == 3 * delta and
            callback['ExecutedAfter'] == 4 * delta and
            receipt['FinalSnapshot']['ExecutionExecuted'] == 4 * delta, 'Callback dispatch recurrence differs.')
    snapshot(receipt['FinalSnapshot'])
    counts = set()
    for sample in receipt['Samples']:
        snapshot(sample['Budget'])
        counts.add(sample['Budget']['ExecutionExecuted'])
    require(len(counts) == 1, 'Fresh session dispatch counts differ.')
    return (delta, counts.pop())

def review(lanes, output):
    expected = [(p, w, m) for p in PROFILES for w in ('entities', 'host-api')
                for m in ('no-config', 'high-budget')]
    require([(x['profile'], x['workload'], x['mode']) for x in lanes] == expected, 'Twelve exact lanes required.')
    require(len({x['raw']['pid'] for x in lanes}) == 12 and
            len({x['nonce'] for x in lanes}) == 12, 'Distinct owned process identities required.')
    references = {}
    controls = 0
    for lane in lanes:
        require(lane['raw']['exitCode'] == 0, 'Process failed.')
        require(sha(output / lane['stdout']) == lane['stdoutSha256'] and
                sha(output / lane['stderr']) == lane['stderrSha256'] and
                sha(output / lane['command']) == lane['commandSha256'], 'Raw streams/command changed.')
        require(load(output / lane['command']) == lane['raw'], 'Stored command differs from actual launch.')
        receipt = load(output / lane['stdout'])
        require(receipt == lane['receipt'], 'Stored receipt differs from raw stdout.')
        counts = validate(receipt, lane, output)
        if counts is not None:
            require(references.setdefault(lane['workload'], counts) == counts, 'Cross-profile exact counts differ.')
        mutations = []
        for name, edit in (
            ('checksum', lambda x: x['Callbacks'][0].__setitem__('Checksum', -1)),
            ('author-entry', lambda x: x['Proof'][0].__setitem__('Interpreted', False)),
            ('resources', lambda x: x['Samples'][0].__setitem__('ReleasedEntities', -1)),
            ('static-reset', lambda x: x['Samples'][0]['Logs'].__setitem__(-1, 'starts=2')),
            ('collection', lambda x: x.__setitem__('directCollected', False)),
        ):
            changed = copy.deepcopy(receipt)
            edit(changed)
            mutations.append((name, changed))
        if counts is not None:
            changed = copy.deepcopy(receipt)
            changed['FinalSnapshot']['ExecutionRemaining'] -= 1
            mutations.append(('ledger', changed))
        for name, changed in mutations:
            try:
                validate(changed, lane, output)
            except RuntimeError:
                controls += 1
            else:
                raise RuntimeError('Altered receipt accepted: ' + name)
        for name in ('runtime', 'switch'):
            changed_lane = copy.deepcopy(lane)
            if name == 'runtime':
                changed_lane['raw']['argv'][0] = str(ROOT / 'wrong-layout/dotnet.exe')
            else:
                changed_lane['raw']['settings']['DOTNET_RuneCLRDerivedLedger'] = (
                    '0' if lane['profile'] == 'on' else '1')
            try:
                validate(receipt, changed_lane, output)
            except RuntimeError:
                controls += 1
            else:
                raise RuntimeError('Altered launch accepted: ' + name)
    return {'passed': True, 'processes': 12, 'collections': 60, 'negativeControls': controls,
            'checksums': {w: {'callback': oracle(w), 'session': oracle(w, 3)} for w in references},
            'dispatchCounts': {w: {'callback': n[0], 'session': n[1]} for w, n in references.items()},
            'performanceMeasured': False, 'mobileVerified': False,
            'scope': 'Functional high-budget controls and selected author entries; no termination or timing claim.'}

def check_inputs(inputs):
    for path, expected in inputs.items():
        require(sha(path) == expected, 'Bound input changed: ' + path)

def command(argv, output, label, settings=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_'))}
    env.update(settings or {})
    process = subprocess.Popen([str(arg) for arg in argv], cwd=ROOT, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        stdout, stderr = process.communicate(timeout=180)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
    (output / (label + '.stdout')).write_bytes(stdout)
    (output / (label + '.stderr')).write_bytes(stderr)
    raw = {'argv': [str(arg) for arg in argv], 'settings': settings or {},
           'pid': process.pid, 'exitCode': process.returncode}
    save(output / (label + '.command.json'), raw)
    require(process.returncode == 0, 'Owned command failed; preserved raw evidence: ' + label)
    return raw

def run(output):
    output.mkdir(parents=True, exist_ok=False)
    inputs = {str(Path(__file__).resolve()): sha(__file__)}
    for folder in ('RuneCLR.BudgetWorkloads', 'RuneCLR.BudgetWorkloadScripts',
                   'RuneCLR.PerformanceHost', 'RuneCLR.Performance.Kernels'):
        for path in (ROOT / 'benchmarks' / folder).rglob('*'):
            if path.suffix in ('.cs', '.csproj') and not {'bin', 'obj'}.intersection(path.parts):
                inputs[str(path)] = sha(path)
    for folder in ('RuneCLR.Runtime', 'RuneCLR.Abstractions', 'RuneCLR.Packages'):
        for path in (ROOT / 'src' / folder).rglob('*'):
            if path.suffix in ('.cs', '.csproj') and not {'bin', 'obj'}.intersection(path.parts):
                inputs[str(path)] = sha(path)
    for name in ('Directory.Build.props', 'Directory.Build.targets', 'global.json', 'NuGet.Config'):
        if (ROOT / name).exists():
            inputs[str(ROOT / name)] = sha(ROOT / name)
    layouts = {}
    for profile, (kind, commit, switch) in PROFILES.items():
        build = ROOT / 'artifacts' / kind / 'windows-release-build-20261014-attempt1'
        receipt = load(build / 'layout-receipt.json')
        require(receipt['passed'] and receipt['candidateCommit'] == commit and
                receipt['buildResultSha256'] == sha(build / 'build-result.json'), 'Accepted layout binding differs.')
        for name in ('layout-receipt.json', 'build-result.json', 'request.json'):
            inputs[str(build / name)] = sha(build / name)
        for relative, expected in receipt['allLayoutHashes'].items():
            inputs[str(build / 'layout' / relative)] = expected
        layouts[profile] = build / 'layout'
    sdk = ROOT / 'artifacts/toolchains/dotnet-11-rc1/dotnet.exe'
    inputs[str(sdk)] = sha(sdk)
    check_inputs(inputs)
    save(output / 'request.json', {'schema': 'runeclr.representative-budget.functional.v1',
         'inputs': inputs, 'profiles': PROFILES, 'samples': 1, 'performanceMeasured': False})
    for project, subdir in (('BudgetWorkloads', 'host'), ('BudgetWorkloadScripts', 'author')):
        command([sdk, 'build', ROOT / ('benchmarks/RuneCLR.' + project), '-c', 'Release',
                 '-o', output / subdir, '-nodeReuse:false'], output, 'build-' + subdir)
        check_inputs(inputs)
    for subdir in ('host', 'author'):
        for path in (output / subdir).iterdir():
            if path.is_file():
                inputs[str(path)] = sha(path)
    require(sha(output / 'host/RuneCLR.Abstractions.dll') == sha(output / 'author/RuneCLR.Abstractions.dll'),
            'Shared contract builds differ.')
    require(not (output / 'host/RuneCLR.BudgetWorkloadScripts.dll').exists(), 'Host contains author assembly.')
    save(output / 'frozen-inputs.json', inputs)
    lanes = []
    for profile in PROFILES:
        for workload in ('entities', 'host-api'):
            for mode in ('no-config', 'high-budget'):
                nonce = uuid.uuid4().hex
                label = profile + '-' + workload + '-' + mode
                argv, settings = launch(profile, workload, mode, nonce, output)
                check_inputs(inputs)
                raw = command(argv, output, label, settings)
                lane = {'profile': profile, 'workload': workload, 'mode': mode, 'nonce': nonce, 'raw': raw,
                        'stdout': label + '.stdout', 'stderr': label + '.stderr',
                        'command': label + '.command.json',
                        'commandSha256': sha(output / (label + '.command.json')),
                        'stdoutSha256': sha(output / (label + '.stdout')),
                        'stderrSha256': sha(output / (label + '.stderr')),
                        'receipt': load(output / (label + '.stdout'))}
                validate(lane['receipt'], lane, output)
                lanes.append(lane)
                save(output / ('partial-' + str(len(lanes)) + '.json'), {'lanes': lanes, 'passed': False})
                print(label + ': passed', flush=True)
    check_inputs(inputs)
    result = review(lanes, output)
    result['boundInputs'] = len(inputs)
    save(output / 'lanes.json', lanes)
    save(output / 'results.json', result)
    print(json.dumps(result), flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('run', 'review'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.mode == 'run':
        run(output)
    else:
        check_inputs(load(output / 'frozen-inputs.json'))
        result = review(load(output / 'lanes.json'), output)
        require(all(load(output / 'results.json')[key] == value for key, value in result.items()),
                'Summary differs from raw observations.')
        print(json.dumps(result))

if __name__ == '__main__':
    main()
