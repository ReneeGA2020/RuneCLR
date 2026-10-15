#!/usr/bin/env python3
"""Verify low-budget entity/API termination followed by fresh-session recovery."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONAL = ROOT / 'artifacts/representative-budget/functional-20261014-attempt3'
VERIFIER = ROOT / 'eng/verify-representative-budget.py'
LIMITS = (1, 32, 64, 128, 2048, 8192, 100000)
ERROR = 'The native prototype instruction budget terminated author execution.'

spec = importlib.util.spec_from_file_location('representative_functional', VERIFIER)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
require, sha, load, save = base.require, base.sha, base.load, base.save

def expected_launch(output, profile, nonce):
    argv, settings = base.launch(profile, 'host-api', 'high-budget', nonce, output)
    argv = argv[:4] + [str(output / 'host/RepresentativeBudgetRecovery.dll'),
                      str(FUNCTIONAL / 'author/RuneCLR.BudgetWorkloadScripts.dll'), nonce]
    return argv, settings

def validate(value, raw, output, profile, nonce):
    argv, settings = expected_launch(output, profile, nonce)
    require(raw['argv'] == argv and raw['settings'] == settings and raw['exitCode'] == 0, 'Launch profile differs.')
    require(value['passed'] and value['nonce'] == nonce and value['processId'] == raw['pid'] and
            value['architecture'] == 'X64' and value['runtime'].startswith('.NET 12.') and
            value['authorHash'].lower() == sha(FUNCTIONAL / 'author/RuneCLR.BudgetWorkloadScripts.dll'),
            'Owned process or author identity differs.')
    require(value['limits'] == list(LIMITS) and value['collected'] == 28, 'Budget/collection inventory differs.')
    expected = [(w, n, role) for w in ('entities', 'host-api') for n in LIMITS
                for role in ('terminated', 'recovery')]
    require([(r['Workload'], r['Limit'], r['Role']) for r in value['rows']] == expected, 'Exact failed/recovery order differs.')
    for row in value['rows']:
        report = row['Report']
        require(row['Collected'] and report['ExecutionPolicy'] == 1 and report['ExecutionPolicyVersion'] == 1 and
                report['RemainingEntities'] == 0 and report['CreatedEntities'] == report['ReleasedEntities'],
                'Policy/resource/collection observation differs.')
        budget = report['PrototypeBudget']
        require(budget['CleanupRemaining'] == 4096 and budget['CleanupExecuted'] == 0, 'Unexpected cleanup dispatches.')
        if row['Role'] == 'terminated':
            require(report['Outcome'] == 1 and report['CompletedTicks'] == 0 and report['Error'] == ERROR and
                    all(x == 'benchmark-tick' for x in report['Logs']), 'Premature continuation or false termination outcome.')
            require(budget == {'ExecutionRemaining': 0, 'ExecutionExecuted': row['Limit'],
                               'ExecutionExhausted': True, 'IsTerminated': True, 'Reason': 1,
                               'Phase': 1, 'CleanupRemaining': 4096, 'CleanupExecuted': 0},
                    'Low-budget terminal ledger differs.')
            if row['Workload'] == 'entities':
                require(report['CreatedEntities'] == 0 and not report['Logs'], 'Entity kernel unexpectedly used host API.')
        else:
            require(report['Outcome'] == 0 and report['CompletedTicks'] == 3 and report['Error'] is None and
                    report['CreatedEntities'] == 24576 and
                    report['Logs'] == ['benchmark-tick'] * 384 +
                    ['budget-workloads:host-api:starts=1;sum=302002176'],
                    'Fresh-session checksum/static/resource recovery differs.')
            require(budget == {'ExecutionRemaining': base.LIMIT - 689851, 'ExecutionExecuted': 689851,
                               'ExecutionExhausted': False, 'IsTerminated': False, 'Reason': 0,
                               'Phase': 0, 'CleanupRemaining': 4096, 'CleanupExecuted': 0},
                    'Fresh-session recovery ledger differs.')

def review(output):
    request = load(output / 'request.json')
    require(request['profiles'] == list(base.PROFILES), 'Profile inventory differs.')
    base.check_inputs(load(output / 'frozen-inputs.json'))
    observations = []
    controls = 0
    for profile in base.PROFILES:
        binding = load(output / (profile + '.binding.json'))
        for suffix in ('stdout', 'stderr', 'command.json'):
            require(sha(output / (profile + '.' + suffix)) == binding['hashes'][suffix], 'Raw launch evidence changed.')
        raw = load(output / (profile + '.command.json'))
        require(raw == binding['raw'], 'Launch record changed.')
        value = load(output / (profile + '.stdout'))
        validate(value, raw, output, profile, binding['nonce'])
        observations.append(value)
        for name, edit in (
            ('debit', lambda x: x['rows'][0]['Report']['PrototypeBudget'].__setitem__('ExecutionExecuted', 0)),
            ('post-terminal-stop', lambda x: x['rows'][0]['Report']['Logs'].append('budget-workloads:stop')),
            ('entity-release', lambda x: x['rows'][1]['Report'].__setitem__('ReleasedEntities', 0)),
            ('recovery-static', lambda x: x['rows'][1]['Report']['Logs'].__setitem__(-1, 'starts=2')),
            ('collection', lambda x: x['rows'][0].__setitem__('Collected', False)),
            ('recovery-latch', lambda x: x['rows'][1]['Report']['PrototypeBudget'].__setitem__('IsTerminated', True)),
        ):
            changed = copy.deepcopy(value)
            edit(changed)
            try:
                validate(changed, raw, output, profile, binding['nonce'])
            except RuntimeError:
                controls += 1
            else:
                raise RuntimeError('Altered recovery receipt accepted: ' + name)
        for name in ('runtime', 'switch'):
            changed = copy.deepcopy(raw)
            if name == 'runtime':
                changed['argv'][0] = str(ROOT / 'wrong-runtime/dotnet.exe')
            else:
                changed['settings']['DOTNET_RuneCLRDerivedLedger'] = '0' if profile == 'on' else '1'
            try:
                validate(value, changed, output, profile, binding['nonce'])
            except RuntimeError:
                controls += 1
            else:
                raise RuntimeError('Wrong recovery launch accepted: ' + name)
    require(len({x['processId'] for x in observations}) == 3 and
            len({x['nonce'] for x in observations}) == 3, 'Owned process identities reused.')
    require(all(x['rows'] == observations[0]['rows'] for x in observations), 'Cross-profile failure/recovery reports differ.')
    api_rows = [r for r in observations[0]['rows'] if r['Workload'] == 'host-api' and r['Role'] == 'terminated']
    require(any(r['Report']['CreatedEntities'] > 0 for r in api_rows), 'No low-budget host resource use was exercised.')
    return {'passed': True, 'profiles': list(base.PROFILES), 'processes': 3, 'collections': 84,
            'terminatedSessions': 42, 'recoverySessions': 42, 'negativeControls': controls,
            'apiPartialCounts': {str(r['Limit']): {'entities': r['Report']['CreatedEntities'],
                                'logs': len(r['Report']['Logs'])} for r in api_rows},
            'sameProcessRecovery': True, 'performanceMeasured': False, 'mobileVerified': False,
            'scope': 'Exact low-budget entity/API ledgers and same-process recovery; selected entry proof belongs to prior functional run.'}

def run(output):
    output.mkdir(parents=True, exist_ok=False)
    inputs = load(FUNCTIONAL / 'frozen-inputs.json')
    inputs[str(FUNCTIONAL / 'results.json')] = sha(FUNCTIONAL / 'results.json')
    inputs[str(FUNCTIONAL / 'frozen-inputs.json')] = sha(FUNCTIONAL / 'frozen-inputs.json')
    inputs[str(Path(__file__).resolve())] = sha(__file__)
    for path in (ROOT / 'eng/representative-budget-recovery-probe').iterdir():
        if path.suffix in ('.cs', '.csproj'):
            inputs[str(path)] = sha(path)
    base.check_inputs(inputs)
    save(output / 'request.json', {'schema': 'runeclr.representative-budget.recovery.v1',
         'profiles': list(base.PROFILES), 'limits': LIMITS, 'inputs': inputs})
    sdk = ROOT / 'artifacts/toolchains/dotnet-11-rc1/dotnet.exe'
    base.command([sdk, 'build', ROOT / 'eng/representative-budget-recovery-probe', '-c', 'Release',
                  '-o', output / 'host', '-nodeReuse:false'], output, 'build')
    for path in (output / 'host').iterdir():
        if path.is_file():
            inputs[str(path)] = sha(path)
    for name in ('RuneCLR.Runtime.dll', 'RuneCLR.Abstractions.dll', 'RuneCLR.Packages.dll'):
        require(sha(output / 'host' / name) == sha(FUNCTIONAL / 'host' / name), 'Production managed bytes differ: ' + name)
    save(output / 'frozen-inputs.json', inputs)
    for profile in base.PROFILES:
        nonce = uuid.uuid4().hex
        argv, settings = expected_launch(output, profile, nonce)
        base.check_inputs(inputs)
        raw = base.command(argv, output, profile, settings)
        validate(load(output / (profile + '.stdout')), raw, output, profile, nonce)
        hashes = {suffix: sha(output / (profile + '.' + suffix)) for suffix in ('stdout', 'stderr', 'command.json')}
        save(output / (profile + '.binding.json'), {'nonce': nonce, 'raw': raw, 'hashes': hashes})
        print(profile + ': 14 terminal sessions and 14 same-process recoveries passed', flush=True)
    result = review(output)
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
        result = review(output)
        require(result == load(output / 'results.json'), 'Recovery summary differs from raw receipts.')
        print(json.dumps(result))

if __name__ == '__main__':
    main()
