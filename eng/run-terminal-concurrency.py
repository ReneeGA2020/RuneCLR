#!/usr/bin/env python3
"""Fresh Windows Release trusted-worker terminal accounting experiment."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '099dacd07d8d890822f7422f895337733457ab3c'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')

def execute(argv, output, name, settings=None):
    env = {key: value for key, value in os.environ.items() if not key.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_'))}
    env.update(settings or {})
    start = time.time()
    child = subprocess.Popen([str(value) for value in argv], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timeout = False
    try:
        stdout, stderr = child.communicate(timeout=100)
    except subprocess.TimeoutExpired:
        timeout = True
        child.kill()
        stdout, stderr = child.communicate()
    (output / (name + '.stdout')).write_bytes(stdout)
    (output / (name + '.stderr')).write_bytes(stderr)
    raw = {'argv': [str(value) for value in argv], 'pid': child.pid, 'exitCode': child.returncode, 'timedOut': timeout,
           'settings': settings or {}, 'wallSeconds': time.time() - start,
           'stdoutSha256': sha(output / (name + '.stdout')), 'stderrSha256': sha(output / (name + '.stderr'))}
    save(output / (name + '.process.json'), raw)
    if timeout or child.returncode != 0:
        raise RuntimeError('Owned process failed; raw files retained: ' + name)
    return stdout, raw

def assess(value):
    assert value['passed'] and value['OwnerIsolation'] and value['collected'] == 2
    assert value['RetiredQueriesRejected'] == [8, 8] and value['nativePolicyAcknowledged'] == 1
    ownership = value['OwnershipSnapshots']
    assert ownership['goodBefore'] == ownership['goodAfterBad']
    assert ownership['badAfterBad'] == ownership['badAfterGood']
    assert ownership['goodAfterGood'] == value['Rows'][1]['After']
    assert len(value['Rows']) == 2
    for index, row in enumerate(value['Rows']):
        workers = value['workers'] if index == 0 else 1
        lane = value['lane'] if index == 0 else 'high'
        assert row['Workers'] == workers and row['Lane'] == lane
        assert row['Admitted'] and row['Joined'] and row['Entered'] == workers and row['StaticStarts'] == 1
        assert len(set(row['WorkerIds'])) == workers and all(thread > 0 for thread in row['WorkerIds'])
        assert row['Counters']['entries'] == [1] * workers
        assert len(row['Returned']) == len(row['Values']) == len(row['Errors']) == workers
        entries = row['Entries']
        assert entries and all(entry['Interpreted'] and entry['PrecodeType'] == 6 and entry['Collectible'] for entry in entries)
        assert {entry['Method'] for entry in entries} >= {'Warm', 'WorkFinally' if 'cleanup' in lane else 'Work'}
        assert all(entry['ModuleMvid'] and entry['MethodDefToken'].startswith('0x06') and entry['InvocationEvidence'] for entry in entries)
        before, after = row['AtGate'], row['After']
        if lane != 'required':
            assert before['Remaining'] > 0 and before['Executed'] > 0
            assert after['Remaining'] >= 0 and after['Executed'] >= before['Executed']
            assert row['PostGateDispatches'] == after['Executed'] - before['Executed']
        if lane in ('terminal', 'finite-cleanup', 'tight-cleanup'):
            assert not any(row['Returned']) and row['Completed'] == 0
            assert row['Errors'] == ['System.OperationCanceledException'] * workers
            assert after['Remaining'] == 0 and after['Executed'] == row['Allowance'] == 2048
            assert after['IsTerminated'] and after['Exhausted'] and after['Reason'] == 1
            assert after['CleanupRemaining'] + after['CleanupExecuted'] == row['CleanupAllowance']
            if lane == 'terminal':
                assert after['Phase'] == 1 and after['CleanupExecuted'] == 0
            if lane == 'finite-cleanup':
                assert after['Phase'] == 1 and row['CleanupStarted'] == row['CleanupCompleted'] == workers
                assert after['CleanupExecuted'] > 0
            if lane == 'tight-cleanup':
                assert after['Phase'] == 2 and after['CleanupRemaining'] == 0 and after['CleanupExecuted'] == 64
                assert row['CleanupCompleted'] == 0
        else:
            expected = 1
            for _ in range(10000):
                expected = (expected * 1664525 + 1013904223) & 0xffffffff
            assert row['Returned'] == [True] * workers and row['Errors'] == [None] * workers
            assert row['Values'] == [expected] * workers and row['Completed'] == workers
            if lane == 'high':
                assert not after['IsTerminated'] and after['Reason'] == after['Phase'] == 0
                assert after['Remaining'] + after['Executed'] == row['Allowance']
            if lane == 'diagnostic':
                assert after['Remaining'] == 0 and after['Executed'] > 2048 and not after['IsTerminated']
            if lane == 'required':
                assert before is None and after is None
    if value['lane'] in ('high', 'diagnostic'):
        assert value['Rows'][0]['PostGateDispatches'] == value['workers'] * value['Rows'][1]['PostGateDispatches']
    return True

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, default=Path('E:/runtime-finalizer-20261013'))
    parser.add_argument('--build-evidence', type=Path, default=ROOT / 'artifacts/budget-overhead/windows-release-build-20261013-attempt1')
    parser.add_argument('--candidate-commit', default=BASELINE)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        raise ValueError('Positive repetitions required')
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    build = args.build_evidence.resolve(); layout = build / 'layout'
    provenance = ROOT / 'eng/windows-runtime-validation.py'
    execute(['py', '-3', '-B', provenance, 'freeze', '--output', output, '--runtime', args.runtime, '--layout', layout, '--build-evidence', build, '--candidate-commit', args.candidate_commit], output, 'provenance-freeze')
    fixture = ROOT / 'eng/session-terminal-concurrency-probe'
    sources = [path for path in fixture.rglob('*') if path.suffix in ('.cs', '.csproj') and not {'bin', 'obj'}.intersection(path.parts)]
    sources += [ROOT / 'eng/windows-entry-observation/WindowsEntryObservation.cs', Path(__file__).resolve(), ROOT / 'Directory.Build.props', ROOT / 'global.json']
    hashes = {}
    for source in sources:
        relative = source.relative_to(ROOT).as_posix(); hashes[relative] = sha(source)
        target = output / 'source' / relative; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
    sdk = ROOT / 'artifacts/toolchains/dotnet-11-rc1/dotnet.exe'
    save(output / 'request.json', {'runtime': str(args.runtime.resolve()), 'layout': str(layout), 'configuration': 'Release',
         'candidateCommit': args.candidate_commit,
         'sourceHashes': hashes, 'hostSdk': str(sdk), 'hostSdkSha256': sha(sdk), 'repeats': args.repeats,
         'scope': 'Trusted host creates joined workers; finite author loops; snapshots only at quiescence'})
    for name in ('Host', 'Payload'):
        execute([sdk, 'build', fixture / name / (name + '.csproj'), '-c', 'Release', '--output', output / name, '-nodeReuse:false'], output, 'build-' + name)
    managed = {path.relative_to(output).as_posix(): sha(path) for folder in ('Host', 'Payload') for path in (output / folder).iterdir() if path.is_file()}
    save(output / 'managed-identity.json', managed)
    settings = {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0', 'DOTNET_ReadyToRun': '1',
                'DOTNET_TieredCompilation': '0', 'DOTNET_MULTILEVEL_LOOKUP': '0', 'RUNECLR_POST_EXECUTION_PRECODE': '1'}
    lanes = []
    for workers in (2, 4):
        for lane in ('terminal', 'finite-cleanup', 'tight-cleanup', 'high', 'diagnostic', 'required'):
            for repeat in range(args.repeats):
                nonce = uuid.uuid4().hex; name = f'{workers}-{lane}-{repeat}-{nonce}'
                target = output / name; target.mkdir()
                stdout, raw = execute([layout / 'dotnet.exe', 'exec', '--fx-version', '12.0.0', output / 'Host/ConcurrencyProbe.Host.dll',
                                      output / 'Payload/ConcurrencyProbe.Payload.dll', workers, lane, nonce, target], output, name, settings)
                value = json.loads(stdout)
                assert value['nonce'] == nonce and value['processId'] == raw['pid'] and value['workers'] == workers and value['lane'] == lane
                assess(value)
                lanes.append({'name': name, 'receipt': raw, 'result': value, 'resultSha256': sha(target / 'result.json')})
                save(output / 'partial-results.json', {'passed': False, 'lanes': lanes})
                print('PASS', workers, lane, repeat, 'execution', value['Rows'][0]['After'], 'contexts collected2', flush=True)
    for relative, expected in hashes.items():
        assert sha(ROOT / relative) == sha(output / 'source' / relative) == expected
    for relative, expected in managed.items():
        assert sha(output / relative) == expected
    execute(['py', '-3', '-B', provenance, 'check', '--output', output, '--candidate-commit', args.candidate_commit], output, 'provenance-check')
    negatives = []
    exemplar = next(lane['result'] for lane in lanes if lane['result']['lane'] == 'terminal')
    mutations = {
        'lost-executed-increment': lambda value: value['Rows'][0]['After'].update(Executed=2047),
        'quota-overshoot': lambda value: value['Rows'][0]['After'].update(Executed=2049),
        'missing-worker-admission': lambda value: value['Rows'][0].update(Entered=1),
        'unjoined-worker': lambda value: value['Rows'][0].update(Joined=False),
        'owner-cross-charge': lambda value: value.update(OwnerIsolation=False),
        'fake-prepared-entry': lambda value: value['Rows'][0]['Entries'][1].update(InvocationEvidence=''),
        'terminal-catch-escape': lambda value: value['Rows'][0].update(Returned=[True] * value['workers']),
        'retained-context': lambda value: value.update(collected=1),
        'retired-query-accepted': lambda value: value.update(RetiredQueriesRejected=[7, 8]),
        'forged-owner-isolation': lambda value: value['OwnershipSnapshots']['goodAfterBad'].update(Executed=1),
    }
    for name, mutate in mutations.items():
        corrupted = copy.deepcopy(exemplar); mutate(corrupted)
        try:
            assess(corrupted)
        except AssertionError:
            negatives.append(name)
        else:
            raise RuntimeError('Negative control accepted: ' + name)
    save(output / 'results.json', {'passed': True, 'candidateCommit': args.candidate_commit, 'lanes': lanes, 'laneCount': len(lanes), 'contextsCollected': 2 * len(lanes),
         'negativeControlsRejected': negatives, 'scope': '2/4 trusted joined workers, finite author workloads; no author thread API, stress coverage, or per-opcode atomic snapshots'})
    print(f'PASS {len(lanes)} owned Release processes; {2 * len(lanes)} contexts collected; {len(negatives)} corruption controls rejected')

if __name__ == '__main__':
    main()
