#!/usr/bin/env python3
"""Prepare/run small-budget batching controls without collecting performance timings."""
import argparse, copy, hashlib, json, os, subprocess, sys, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWITCH = 'DOTNET_RuneCLRBatchInterval'
LANES = ((1, 1), (1, 100), (1, 1000), (100, 100), (1000, 1000))
METHODS = ('ShortReturn', 'OrdinaryThrow', 'FiniteProgress', 'EndlessCatch')

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p, v):
    with Path(p).open('x', encoding='ascii') as f: json.dump(v, f, indent=2); f.write(chr(10))
def need(v, m):
    if not v: raise RuntimeError(m)
def verify_inputs(v):
    for n, h in v.items(): need(Path(n).is_file() and sha(n) == h, 'Frozen input differs: ' + n)

def prepare(out, sdk):
    out.mkdir(parents=True, exist_ok=False)
    fixture = ROOT / 'eng/batch-boundary-probe'
    sources = {str(p.resolve()): sha(p) for p in sorted(fixture.rglob('*')) if p.suffix in ('.cs', '.csproj') and not any(x in p.parts for x in ('bin', 'obj'))}
    sources[str(Path(__file__).resolve())] = sha(__file__)
    save(out / 'request.json', {'sources': sources, 'sdk': str(sdk), 'sdkSha256': sha(sdk), 'lanes': LANES, 'performanceMeasured': False})
    for name in ('Host', 'Author'):
        command = [str(sdk), 'build', str(fixture / name / (name + '.csproj')), '-c', 'Release', '--artifacts-path', str(out / 'build-obj'), '-o', str(out / name.lower()), '-nodeReuse:false']
        q = subprocess.run(command, text=True, capture_output=True)
        (out / (name + '.build.log')).write_text(q.stdout + q.stderr)
        save(out / (name + '.build.json'), {'command': command, 'exitCode': q.returncode, 'logSha256': sha(out / (name + '.build.log'))})
        need(q.returncode == 0, 'Fixture build failed: ' + name)
    need(sha(out / 'host/BatchBoundary.Contract.dll') == sha(out / 'author/BatchBoundary.Contract.dll'), 'Shared contract builds differ')
    for name in ('host', 'author'):
        for p in sorted((out / name).iterdir()):
            if p.is_file(): sources[str(p.resolve())] = sha(p)
    verify_inputs(sources)
    save(out / 'frozen-inputs.json', sources)
    save(out / 'results.json', {'prepared': True, 'runtimeExecutionVerified': False, 'performanceMeasured': False, 'laneCount': 5, 'sourceFiles': len(sources), 'scope': 'Fixture compilation only; batching candidate execution is unperformed.'})
    print('PREPARED 5 lanes; no runtime candidate executed', flush=True)

def valid_progress(p, finite=False):
    need(all(type(p[n]) is int and p[n] >= 0 for n in ('Starts', 'CompletedIterations', 'Catches', 'ReturnedMarkers', 'FinallyMarkers')), 'Invalid scalar progress')
    need(type(p['ProgressObserved']) is bool, 'Missing explicit progress-observation flag')
    need(p['ProgressObserved'] or p['CompletedIterations'] == 0, 'Unobserved progress must not claim an iteration count')
    if finite: need(p == {'Starts': 1, 'CompletedIterations': 7, 'Catches': 0, 'ReturnedMarkers': 1, 'FinallyMarkers': 0, 'ProgressObserved': True}, 'Completed finite author work differs')

def validate(receipt, configured, matrix):
    need(receipt['observed'] and receipt['interval'] == matrix and receipt['configuredInterval'] == format(configured, 'x'), 'Owned interval/canonical DWORD hex setting differs')
    need(receipt['limits'] == [1, matrix - 1, matrix, matrix + 1] and receipt['capabilities'] == {'terminalVersion': 1, 'privateBridge': True}, 'Limit/private capability inventory differs')
    need(receipt['performanceMeasured'] is False and receipt['nativeEntryProof'] is False and receipt['liveBatchPathVerified'] is False, 'Evidence scope promoted')
    need(receipt['architecture'] == 'X64' and receipt['runtime'].startswith('.NET 12.'), 'Declared Windows X64 / .NET 12 experiment differs')
    rows = receipt['rows']; expected = [('calibration', 'high', 1000000, m) for m in METHODS[:3]]
    for label, limit in zip(('one', 'N-minus-one', 'N', 'N-plus-one'), receipt['limits']):
        if limit == 0: expected.extend([('zero-budget-rejected', label, 0, 'Create'), ('recovery', label, 0, 'FiniteProgress')])
        else:
            for m in METHODS: expected.extend([('boundary', label, limit, m), ('recovery', label, limit, 'FiniteProgress')])
    need([(r['Role'], r['LimitLabel'], r['Limit'], r['Method']) for r in rows] == expected, 'Exact ordered boundary/recovery matrix differs')
    for r in rows:
        if r['Role'] == 'zero-budget-rejected': need(r['Observations'] is None and r['Collected'] is None, 'Zero budget must not claim a created/collected context'); continue
        need(r['Collected'] is True, 'Completed collection missing')
        o, budget = r['Observations'], r['Observations']['Snapshot']; p = o['Progress']; valid_progress(p)
        need(all(type(budget[n]) is int and budget[n] >= 0 for n in ('Remaining', 'Executed', 'CleanupRemaining', 'CleanupExecuted')), 'Negative native ledger')
        need(budget['CleanupRemaining'] + budget['CleanupExecuted'] == 4096, 'Cleanup ledger differs')
        if budget['IsTerminated']:
            need(r['Role'] == 'boundary' and not o['Returned'] and o['ErrorType'] is not None and budget['Exhausted'] and budget['Reason'] == budget['Phase'] == 1 and budget['Remaining'] == 0 and budget['Executed'] >= r['Limit'], 'Sticky terminal boundary differs')
            need(p['Catches'] == p['ReturnedMarkers'] == 0, 'Author catch/continuation ran after quota')
            need(budget['Executed'] - r['Limit'] <= configured - 1, 'Declared single-worker dispatch overshoot bound exceeded')
        else:
            limit = 1000000 if r['Role'] in ('recovery', 'calibration') else r['Limit']
            need(not budget['Exhausted'] and budget['Reason'] == budget['Phase'] == 0 and budget['Executed'] > 0 and budget['Remaining'] + budget['Executed'] == limit and budget['CleanupExecuted'] == 0, 'Active ordinary/return ledger differs')
            need(r['Method'] != 'EndlessCatch', 'Endless author returned without native termination')
            if r['Method'] == 'OrdinaryThrow': need(not o['Returned'] and o['ErrorType'] == 'System.InvalidOperationException', 'Ordinary exception attribution differs')
            elif r['Method'] == 'ShortReturn': need(o['Returned'] and o['Value'] == 73 and o['ErrorType'] is None, 'Short normal return differs')
            else: need(o['Returned'] and o['Value'] == 21 and o['ErrorType'] is None, 'Finite checksum differs'); valid_progress(p, finite=True)
    return rows

def review(out):
    request = load(out / 'request.json'); verify_inputs(load(out / 'frozen-inputs.json')); receipts = {}; controls = 0
    owners = []
    for configured, matrix in LANES:
        key = f'N{configured}-matrix{matrix}'; owner = load(out / (key + '.process.json')); receipt = load(out / (key + '.receipt.json'))
        need(owner['exitCode'] == 0 and owner['timedOut'] is False and receipt['processId'] == owner['pid'] and receipt['nonce'] == owner['nonce'], 'Owned process/exit/watchdog differs')
        need(owner['argv'] == arguments(request['profile'], Path(request['prepared']), out / (key + '.receipt.json'), matrix, owner['nonce']), 'Actual executable/arguments differ')
        owners.append((owner['pid'], owner['nonce']))
        for suffix in ('stdout', 'stderr', 'receipt.json'): need(sha(out / (key + '.' + suffix)) == owner['hashes'][suffix], 'Original stream/receipt hash differs')
        need(receipt['authorHash'].lower() == request['authorHash'] and owner['settings'] == settings(configured), 'Author/configuration binding differs')
        rows = validate(receipt, configured, matrix); receipts[(configured, matrix)] = rows
        for name, edit in [('uncollected', lambda x: x['rows'][0].__setitem__('Collected', False)), ('wrong-interval', lambda x: x.__setitem__('configuredInterval', '7')), ('forged-scope', lambda x: x.__setitem__('liveBatchPathVerified', True)), ('recovery-checksum', lambda x: next(r for r in x['rows'] if r['Role'] == 'recovery')['Observations'].__setitem__('Value', -1))]:
            v = copy.deepcopy(receipt); edit(v)
            try: validate(v, configured, matrix)
            except RuntimeError: controls += 1
            else: raise RuntimeError('Corrupted boundary control accepted: ' + name)
    need(len({pid for pid, nonce in owners}) == 5 and len({nonce for pid, nonce in owners}) == 5, 'Owned process identities reused')
    comparisons = []
    for n in (100, 1000):
        baseline, actual = receipts[(1, n)], receipts[(n, n)]
        for before, after in zip(baseline, actual):
            if after['Role'] not in ('boundary', 'calibration'): continue
            a, b = after['Observations'], before['Observations']; av, bv = a['Snapshot'], b['Snapshot']
            observed = a['Progress']['ProgressObserved'] and b['Progress']['ProgressObserved']
            comparisons.append({'interval': n, 'limitLabel': after['LimitLabel'], 'limit': after['Limit'], 'method': after['Method'], 'role': after['Role'], 'nativeReported': av['Executed'], 'nativeReportedN1': bv['Executed'], 'reportedDifference': av['Executed'] - bv['Executed'], 'quotaDispatchOvershoot': max(0, av['Executed'] - after['Limit']) if av['IsTerminated'] else None, 'actualProgress': a['Progress']['CompletedIterations'] if a['Progress']['ProgressObserved'] else None, 'actualProgressN1': b['Progress']['CompletedIterations'] if b['Progress']['ProgressObserved'] else None, 'progressDifference': a['Progress']['CompletedIterations'] - b['Progress']['CompletedIterations'] if observed else None, 'terminal': av['IsTerminated'], 'terminalN1': bv['IsTerminated'], 'returned': a['Returned'], 'returnedN1': b['Returned'], 'partialBatchReportedMatchesN1': av['Executed'] == bv['Executed'] if after['Role'] == 'calibration' else None})
    need(all(c['partialBatchReportedMatchesN1'] is not False for c in comparisons), 'Short return/ordinary exception/finite partial batch reporting differs from N1')
    return {'passed': True, 'processes': 5, 'collections': sum(r['Collected'] is True for rows in receipts.values() for r in rows), 'negativeControls': controls, 'comparisons': comparisons, 'sameProcessRecovery': True, 'configurationEncoding': 'canonical-hex-dword', 'performanceMeasured': False, 'liveBatchPathVerified': False, 'nativeEntryProof': False, 'mobileVerified': False, 'scope': 'Small-limit single-worker configured batching outcomes, native reported debit, pure-local progress where observable, partial batches and recovery only; markers are not opcode counts.'}

def settings(n):
    # CLRConfig DWORD environment values use hexadecimal parsing on this frozen source.
    return {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0', 'DOTNET_ReadyToRun': '1', 'DOTNET_TieredCompilation': '0', 'DOTNET_MULTILEVEL_LOOKUP': '0', 'DOTNET_RuneCLRPhaseAcquireLoad': '1', 'DOTNET_RuneCLRDerivedLedger': '0', SWITCH: format(n, 'x'), 'RUNECLR_BATCH_TEST_SWITCH': SWITCH}

def arguments(profile, prepared, receipt, matrix, nonce):
    return [str(Path(profile['dotnet']).resolve()), 'exec', '--fx-version', '12.0.0', str(prepared / 'host/BatchBoundary.Host.dll'), str(prepared / 'author/BatchBoundary.Author.dll'), str(receipt), str(matrix), nonce]

def run(out, prepared, profile_path, timeout):
    out.mkdir(parents=True, exist_ok=False); profile = load(profile_path); frozen = load(prepared / 'frozen-inputs.json'); verify_inputs(frozen)
    # Caller supplies exact matching product identities; this runner never creates a runtime layout.
    for key in ('dotnet', 'native', 'corelib', 'buildReceipt', 'sourceProof'):
        path = Path(profile[key]).resolve(); need(sha(path) == profile[key + 'Sha256'], 'Matching profile hash differs: ' + key); frozen[str(path)] = sha(path)
    layout = Path(profile['dotnet']).resolve().parent
    need(Path(profile['native']).resolve().is_relative_to(layout) and Path(profile['corelib']).resolve().is_relative_to(layout), 'Native/CoreLib must belong to the selected private layout')
    build = load(profile['buildReceipt'])
    build_exit = build.get('buildExit', build.get('exitCode'))
    commit = build.get('commit', build.get('candidateCommit'))
    tree = build.get('tree', build.get('candidateValidation', {}).get('candidateTree'))
    need(build_exit == 0 and commit == profile['sourceCommit'] and tree == profile['sourceTree'] and build.get('configuration') == 'Release', 'Matching build source/configuration differs')
    frozen[str(profile_path.resolve())] = sha(profile_path); frozen[str(Path(__file__).resolve())] = sha(__file__)
    save(out / 'frozen-inputs.json', frozen); save(out / 'request.json', {'profile': profile, 'prepared': str(prepared), 'authorHash': sha(prepared / 'author/BatchBoundary.Author.dll'), 'lanes': LANES, 'intervalEnvironment': {str(n): format(n, 'x') for n in (1, 100, 1000)}, 'configurationEncoding': 'canonical-hex-dword', 'timeoutSeconds': timeout, 'performanceMeasured': False})
    for configured, matrix in LANES:
        key = f'N{configured}-matrix{matrix}'; nonce = uuid.uuid4().hex; receipt = out / (key + '.receipt.json')
        argv = arguments(profile, prepared, receipt, matrix, nonce)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_'))}; cfg = settings(configured); env.update(cfg); verify_inputs(frozen)
        owner = {'argv': argv, 'settings': cfg, 'nonce': nonce, 'timedOut': False}
        with (out / (key + '.stdout')).open('wb') as stdout, (out / (key + '.stderr')).open('wb') as stderr:
            q = subprocess.Popen(argv, stdout=stdout, stderr=stderr, env=env); owner['pid'] = q.pid
            try: owner['exitCode'] = q.wait(timeout=timeout)
            except subprocess.TimeoutExpired: q.kill(); q.wait(); owner.update(timedOut=True, exitCode=q.returncode)
        owner['hashes'] = {s: sha(out / (key + '.' + s)) for s in ('stdout', 'stderr', 'receipt.json') if (out / (key + '.' + s)).is_file()}; save(out / (key + '.process.json'), owner)
        need(owner['exitCode'] == 0 and not owner['timedOut'], 'Boundary process failed; preserve this attempt: ' + key); validate(load(receipt), configured, matrix)
        print(key + ': actual boundary observations and recovery completed', flush=True)
    result = review(out); save(out / 'results.json', result); print(json.dumps(result))

def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('mode', choices=('prepare', 'run', 'review')); p.add_argument('--output', type=Path, required=True); p.add_argument('--sdk', type=Path, default=ROOT / 'artifacts/toolchains/dotnet-11-rc1/dotnet.exe'); p.add_argument('--prepared', type=Path); p.add_argument('--profile', type=Path); p.add_argument('--timeout', type=int, default=45); a = p.parse_args(); out = a.output.resolve()
    if a.mode == 'prepare': prepare(out, a.sdk.resolve())
    elif a.mode == 'run':
        need(a.prepared is not None and a.profile is not None, '--prepared and --profile are required'); run(out, a.prepared.resolve(), a.profile.resolve(), a.timeout)
    else: result = review(out); need(result == load(out / 'results.json'), 'Summary differs from raw observations'); print(json.dumps(result))

if __name__ == '__main__': main()
