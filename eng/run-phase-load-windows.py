#!/usr/bin/env python3
"""Run frozen phase ON/OFF functional commands serially; never benchmark."""
import argparse
import ast
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ORDER = ('terminal', 'finalizer', 'host', 'budget-audit', 'concurrency', 'concurrency-audit', 'production', 'production-audit')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + chr(10), encoding='ascii')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preparation', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profiles', nargs='+', choices=('off', 'on'), default=['off', 'on'])
    parser.add_argument('--suites', nargs='+', choices=ORDER, default=list(ORDER))
    args = parser.parse_args()
    preparation = args.preparation.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, output / 'run-driver.py')
    manifest_path = preparation / 'preparation.json'
    manifest = json.loads(manifest_path.read_text())
    assert manifest['passed'] and manifest['productionCommandsPrepared']
    parse_script = output / 'parse-prepared.ps1'
    parse_script.write_text(chr(10).join([
        'param([string]$Directory)', "$ErrorActionPreference='Stop'", '$count=0',
        "foreach($file in Get-ChildItem -LiteralPath $Directory -Filter '*.ps1' -Recurse -File){",
        '    $tokens=$null;$errors=$null',
        '    [System.Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors)|Out-Null',
        '    if($errors.Count){throw ($file.FullName+": "+($errors|Out-String))}',
        '    $count++', '}', "Write-Host ('PASS parsed PowerShell snapshots '+$count)",
    ]) + chr(10), encoding='ascii')
    parses = subprocess.run(['pwsh', '-NoProfile', '-File', str(parse_script), '-Directory', str(preparation)],
                            capture_output=True)
    (output / 'powershell-parse.stdout').write_bytes(parses.stdout)
    (output / 'powershell-parse.stderr').write_bytes(parses.stderr)
    if parses.returncode:
        raise RuntimeError('Prepared PowerShell syntax failed; raw retained.')
    controls = {}
    profiles = {}
    for label in args.profiles:
        directory = preparation / label / 'eng'
        profile_path = directory / 'profile.json'
        assert sha(profile_path) == manifest['profiles'][label]['profileSha256']
        profile = json.loads(profile_path.read_text())
        binding_path = directory / 'phase-profile-binding.py'
        binding = subprocess.run([sys.executable, '-B', str(binding_path)], capture_output=True)
        (output / (label + '-binding.stdout')).write_bytes(binding.stdout)
        (output / (label + '-binding.stderr')).write_bytes(binding.stderr)
        if binding.returncode:
            raise RuntimeError('Prepared profile binding failed: ' + label)
        count = 0
        for path in directory.glob('*.py'):
            ast.parse(path.read_text(), filename=str(path))
            count += 1
        spec = importlib.util.spec_from_file_location('phase_binding_' + label, binding_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.validate()
        original_load = module.json.loads
        negatives = []
        edits = {
            'switch_changed': lambda p: p.__setitem__('phaseAcquireValue', '1' if label == 'off' else '0'),
            'candidate_changed': lambda p: p.__setitem__('candidateCommit', '0' * 40),
            'snapshot_hash_changed': lambda p: p['snapshotHashes'].__setitem__('commands.json', '0' * 64),
            'original_hash_changed': lambda p: p['originalInputHashes'].__setitem__(next(iter(p['originalInputHashes'])), '0' * 64),
        }
        try:
            for name, edit in edits.items():
                mutant = copy.deepcopy(profile)
                edit(mutant)
                module.json.loads = lambda data, mutant=mutant: mutant
                try:
                    module.validate()
                except RuntimeError as error:
                    negatives.append({'name': name, 'rejected': True, 'reason': str(error)})
                else:
                    raise AssertionError('Profile corruption accepted: ' + name)
        finally:
            module.json.loads = original_load
        controls[label] = negatives
        commands = json.loads((directory / 'commands.json').read_text())
        assert commands == manifest['profiles'][label]['commands']
        assert set(commands) == set(ORDER)
        profiles[label] = {'astFiles': count, 'profileSha256': sha(profile_path), 'commands': commands,
                           'controls': negatives}
    state = {'passed': False, 'preparedManifestSha256': sha(manifest_path), 'profiles': profiles,
             'bindingControls': controls, 'runs': [], 'scope': 'Functional suite/auditor execution only; no timing comparison or complete method trace.'}
    save(output / 'run-receipt.json', state)
    for label in args.profiles:
        for suite in ORDER:
            if suite not in args.suites:
                continue
            command = profiles[label]['commands'][suite]
            prefix = label + '-' + suite
            for entry in command:
                if 'benchmark' in Path(entry).name:
                    raise RuntimeError('Benchmark execution forbidden.')
            stdout_path = output / (prefix + '.stdout')
            stderr_path = output / (prefix + '.stderr')
            print('START ' + prefix, flush=True)
            tick = time.monotonic()
            started = datetime.now(timezone.utc).isoformat()
            with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
                process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
                timed_out = False
                try:
                    exit_code = process.wait(timeout=900)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    process.kill()
                    exit_code = process.wait(timeout=15)
            row = {'profile': label, 'suite': suite, 'command': command, 'pid': process.pid,
                   'startedUtc': started, 'elapsedSeconds': time.monotonic() - tick,
                   'timedOut': timed_out, 'exitCode': exit_code, 'stdoutSha256': sha(stdout_path),
                   'stderrSha256': sha(stderr_path), 'passed': exit_code == 0 and not timed_out}
            state['runs'].append(row)
            save(output / (prefix + '.process.json'), row)
            save(output / 'run-receipt.json', state)
            if not row['passed']:
                raise RuntimeError('Functional command failed; all prior successful commands preserved: ' + prefix)
            print('PASS ' + prefix, flush=True)
    state['passed'] = True
    save(output / 'run-receipt.json', state)
    print('PASS phase functional commands ' + str(len(state['runs'])), flush=True)

if __name__ == '__main__':
    main()
