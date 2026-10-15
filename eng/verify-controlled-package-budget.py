#!/usr/bin/env python3
"""Run controlled-package pumped/native-budget acceptance on a private Windows runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + chr(10), encoding='utf-8')


def review_receipts(path, stdout):
    evidence = json.loads(path.read_text(encoding='utf-8'))
    rows = evidence['receipts']
    console_rows = [json.loads(line.removeprefix('NATIVE_BUDGET_RECEIPT '))
                    for line in stdout.splitlines() if line.startswith('NATIVE_BUDGET_RECEIPT ')]
    expected = [('source', 'baseline')]
    bad_names = ('budget-work', 'budget-constructor-loop', 'budget-static-constructor-loop',
                 'budget-start-loop', 'budget-tick-loop', 'budget-catch-resume',
                 'budget-finite-cleanup', 'budget-infinite-cleanup', 'budget-stop-loop')
    for name in bad_names:
        expected += [(name, 'case'), ('source', 'recovery-after-' + name)]
    for index in range(3):
        expected += [('budget-catch-resume', 'repeated-bad-' + str(index)),
                     ('source', 'repeated-good-' + str(index))]
    if (evidence['schemaVersion'] != 1 or evidence['passed'] is not True
            or evidence['nativeGroups'] != 11 or evidence['packageTestsPassed'] != 33
            or evidence['packageTestsTotal'] != 33 or rows != console_rows
            or [(row['caseId'], row['role']) for row in rows] != expected):
        raise RuntimeError('Native receipts do not match the exact case/order/console contract.')
    for sequence, row in enumerate(rows, 1):
        name = row['caseId']
        good = name == 'source'
        budget = row['budget']
        limit = 1000000 if good else 8192
        entities = 0 if name in ('budget-constructor-loop', 'budget-static-constructor-loop') else 1
        if (row['sequence'] != sequence or row['executionLimit'] != limit or row['cleanupLimit'] != 4096
                or row['executionPolicy'] != 'RequireInterpreter' or row['executionPolicyVersion'] != 1
                or row['collected'] is not True or row['retainedStoppedSessionCollected'] is not True
                or row['completedTicks'] != row['successfulHostReturns']
                or row['created'] != entities or row['released'] != entities or row['remaining'] != 0
                or budget['ExecutionRemaining'] < 0 or budget['ExecutionExecuted'] <= 0
                or budget['ExecutionRemaining'] + budget['ExecutionExecuted'] != limit
                or budget['CleanupRemaining'] < 0 or budget['CleanupExecuted'] < 0
                or budget['CleanupRemaining'] + budget['CleanupExecuted'] != 4096
                or budget['IsTerminated'] != (not good) or budget['ExecutionExhausted'] != (not good)
                or budget['Reason'] != (0 if good else 1)):
            raise RuntimeError('Invalid scalar ledger/ownership/retirement receipt: ' + name)
        logs = row['logs']
        if good:
            valid = (row['outcome'] == 'Completed' and row['error'] is None
                     and row['completedTicks'] == 2 and budget['ExecutionRemaining'] > 0
                     and budget['Phase'] == 0 and budget['CleanupExecuted'] == 0
                     and logs == ['starts=1', 'tick=0', 'tick=1', 'stopped'])
        else:
            valid = (row['outcome'] == 'Failed' and budget['ExecutionRemaining'] == 0
                     and budget['ExecutionExecuted'] == 8192
                     and 'The native prototype instruction budget terminated author execution.' in (row['error'] or '')
                     and not set(logs).intersection(('stop', 'broad-catch', 'resume', 'start-after', 'tick-after', 'stop-after')))
            if name == 'budget-work':
                valid &= (2 <= row['completedTicks'] < 64 and len(logs) - 1 in
                          (row['completedTicks'], row['completedTicks'] + 1)
                          and logs == ['start'] + ['work=' + str(i) for i in range(len(logs) - 1)])
            else:
                valid &= row['completedTicks'] == (2 if name == 'budget-stop-loop' else 0)
                expected_logs = {
                    'budget-constructor-loop': [], 'budget-static-constructor-loop': [],
                    'budget-start-loop': ['start'], 'budget-tick-loop': ['start', 'tick-before'],
                    'budget-catch-resume': ['start'],
                    'budget-infinite-cleanup': ['start', 'helper-infinite-before'],
                    'budget-stop-loop': ['start', 'tick=0', 'tick=1', 'stop-before']}
                if name == 'budget-finite-cleanup':
                    checksum = 0
                    for index in range(32):
                        checksum = (checksum * 31 + index) & 0xffffffff
                    if checksum >= 0x80000000:
                        checksum -= 0x100000000
                    valid &= logs == ['start', 'finally', 'helper-finite', 'cleanup-checksum=' + str(checksum)]
                else:
                    valid &= logs == expected_logs[name]
            if name == 'budget-finite-cleanup':
                valid &= budget['Phase'] == 1 and 0 < budget['CleanupExecuted'] < 4096
            elif name == 'budget-infinite-cleanup':
                valid &= budget['Phase'] == 2 and budget['CleanupExecuted'] == 4096 and budget['CleanupRemaining'] == 0
            else:
                valid &= budget['Phase'] == 1 and budget['CleanupExecuted'] == 0
        if not valid:
            raise RuntimeError('Native receipt behavior differs from controlled author source: ' + name)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'fixtures', 'layout', 'runtime', 'build-evidence', 'dotnet'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--candidate-commit', required=True)
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('This controller requires Windows; mobile acceptance is separate.')
    root = Path(__file__).resolve().parent.parent
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    player = root / 'tests/RuneCLR.PackageExecution.Tests/bin/Release/net11.0/RuneCLR.PackageExecution.Tests.dll'
    fixtures, layout = args.fixtures.resolve(), args.layout.resolve()
    required_fixtures = ('frames', 'tick-failure', 'stop-failure', 'budget-work',
                         'budget-constructor-loop', 'budget-static-constructor-loop',
                         'budget-start-loop', 'budget-tick-loop', 'budget-catch-resume',
                         'budget-finite-cleanup', 'budget-infinite-cleanup', 'budget-stop-loop')
    for name in required_fixtures:
        if not (fixtures / name / 'package.json').is_file():
            raise RuntimeError('Missing opt-in controlled fixture: ' + name)
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(('DOTNET_', 'COMPLUS_', 'RUNECLR_'))}
    settings = {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0',
                'DOTNET_ReadyToRun': '1', 'DOTNET_TieredCompilation': '1',
                'DOTNET_MULTILEVEL_LOOKUP': '0'}
    env.update(settings)
    summary = {'passed': False, 'nativeEntryProof': False, 'mobileAccepted': False, 'lanes': {}}
    write(out / 'results.json', summary)

    def run(name, command, expected=0, timeout=180):
        command = [str(x) for x in command]
        started = time.time()
        child = subprocess.Popen(command, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        timed_out = False
        try:
            stdout, stderr = child.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'],
                           capture_output=True, timeout=20, check=False)
            stdout, stderr = child.communicate(timeout=20)
        (out / (name + '.stdout')).write_bytes(stdout)
        (out / (name + '.stderr')).write_bytes(stderr)
        record = {'command': command, 'processId': child.pid, 'exitCode': child.returncode,
                  'timedOut': timed_out, 'startedUnix': started, 'endedUnix': time.time(),
                  'settings': settings, 'stdoutSha256': sha(out / (name + '.stdout')),
                  'stderrSha256': sha(out / (name + '.stderr'))}
        write(out / (name + '.process.json'), record)
        if timed_out or child.returncode != expected:
            raise RuntimeError(name + ': unexpected exit/timeout; see preserved process/stdout/stderr.')
        return stdout.decode('utf-8-sig'), stderr.decode('utf-8-sig'), record

    def inventory():
        paths = set()
        for directory in (player.parent, fixtures):
            paths.update(p for p in directory.rglob('*') if p.is_file())
        for directory in ('src', 'tests/RuneCLR.PackageExecution.Tests', 'tools/RuneCLR.PackageFixtures'):
            paths.update(p for p in (root / directory).rglob('*')
                         if p.is_file() and p.suffix in ('.cs', '.csproj')
                         and not {'bin', 'obj'}.intersection(p.relative_to(root).parts))
        paths.update((Path(__file__).resolve(), root / 'eng/windows-runtime-validation.py'))
        return {str(p): sha(p) for p in sorted(paths)}

    before = inventory()
    write(out / 'inputs-before.json', before)
    for name in before:
        source = Path(name)
        if source.suffix in ('.cs', '.csproj', '.py') and not {'bin', 'obj', 'artifacts'}.intersection(source.relative_to(root).parts):
            target = out / 'source' / source.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    validator = root / 'eng/windows-runtime-validation.py'
    run('provenance-freeze', [sys.executable, validator, 'freeze', '--output', out,
                            '--runtime', args.runtime.resolve(), '--layout', layout,
                            '--build-evidence', args.build_evidence.resolve(),
                            '--candidate-commit', args.candidate_commit])
    for name, required, pump, native, count in (
            ('stock-synchronous', False, False, False, 15),
            ('stock-pumped', False, True, False, 22),
            ('required-pumped', True, True, False, 22),
            ('required-native-budget', True, True, True, 33)):
        command = ([layout / 'dotnet.exe', 'exec', '--fx-version', '12.0.0'] if required
                   else [args.dotnet.resolve(), 'exec']) + [player, '--packages', fixtures]
        if required:
            command.append('--require-interpreter')
        if pump:
            command.append('--pump')
        if native:
            command += ['--native-budget', '--budget-evidence', out / 'native-receipts']
        stdout, stderr, record = run(name, command)
        if (stderr or stdout.count('PASS ') != count or 'FAIL ' in stdout
                or not re.search(str(count) + '/' + str(count) + r' package execution tests passed.', stdout)
                or stdout.strip().splitlines()[-2] != 'PASS Player default context contains no operator compiler assemblies'):
            raise RuntimeError(name + ': package-case or compiler-absence proof missing.')
        summary['lanes'][name] = {'passed': True, 'caseCount': count, 'processId': record['processId']}
        if native:
            summary['nativeReceiptCount'] = review_receipts(out / 'native-receipts/results.json', stdout)
        write(out / 'results.json', summary)
        print(name + ': ' + str(count) + '/' + str(count) + ' passed; exit=0', flush=True)
    stock = [args.dotnet.resolve(), 'exec', player, '--packages', fixtures]
    stdout, stderr, record = run('stock-native-refusal', stock + [
        '--pump', '--require-interpreter', '--native-budget'], expected=2)
    if ('NATIVE_BUDGET_UNAVAILABLE beforeAuthorFile=true collectibleBefore=0 collectibleAfter=0 authorLoads=0'
            not in stdout + stderr or 'PASS ' in stdout or 'NATIVE_BUDGET_RECEIPT ' in stdout):
        raise RuntimeError('Stock runtime did not refuse native mode before author execution.')
    summary['lanes']['stock-native-refusal'] = {'passed': True, 'exitCode': 2, 'processId': record['processId']}
    for name, flags in (('missing-required', ['--pump', '--native-budget']),
                        ('missing-pump', ['--require-interpreter', '--native-budget']),
                        ('orphan-evidence', ['--budget-evidence', out / 'must-not-exist'])):
        stdout, stderr, _ = run(name, stock + flags, expected=2)
        if 'PASS ' in stdout or 'NATIVE_BUDGET_' in stdout + stderr:
            raise RuntimeError('Invalid options reached the native preflight or execution cases.')
        summary['lanes'][name] = {'passed': True, 'exitCode': 2}
    if (out / 'must-not-exist').exists():
        raise RuntimeError('Invalid options created budget evidence.')
    after = inventory()
    write(out / 'inputs-after.json', after)
    if before != after:
        raise RuntimeError('Player/fixtures/sources changed during acceptance.')
    run('provenance-check', [sys.executable, validator, 'check', '--output', out,
                           '--candidate-commit', args.candidate_commit])
    summary.update(passed=True, inputsUnchanged=True, inputCount=len(before),
                   runtimeProvenanceUnchanged=True, fixtureRoot=str(fixtures),
                   candidateCommit=args.candidate_commit)
    write(out / 'results.json', summary)
    print('PASS controlled package lanes, stock refusal, option controls and unchanged Release provenance', flush=True)


if __name__ == '__main__':
    main()
