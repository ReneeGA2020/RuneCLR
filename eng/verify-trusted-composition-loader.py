#!/usr/bin/env python3
"""Reject broken trusted dependencies and verify fresh collectible recovery."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def hashes(directory):
    return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob('*.dll') if '.sessions' not in path.parts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    output = evidence / 'loader-controls'
    output.mkdir(parents=True, exist_ok=False)
    original = evidence / 'il/updates'
    original_hashes = hashes(original)
    host = evidence / 'r2r/host/TrustedComposition.Host.dll'
    dotnet = args.runtime.resolve() / 'artifacts/bin/testhost/net11.0-windows-Release-x64/dotnet.exe'
    settings = dict(DOTNET_ReadyToRun='1', DOTNET_InterpMode='1', DOTNET_TieredCompilation='0',
                    DOTNET_TC_OnStackReplacement='0', DOTNET_MULTILEVEL_LOOKUP='0')
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(('DOTNET_', 'COMPLUS_', 'RUNECLR_', 'TRUSTED_COMPOSITION_', '__TEST'))}
    env.update(settings)
    runs = []

    def invoke(name, defect=None):
        directory = output / name
        directory.mkdir()
        updates = directory / 'updates'
        # Previous driver lanes leave diagnostic session copies. Only copy the
        # declared A/B inputs, preserving the original evidence byte-for-byte.
        for version in ('A', 'B'):
            shutil.copytree(original / version, updates / version)
        if defect == 'wrong-private-version':
            shutil.copy2(updates / 'B/TrustedComposition.Private.dll', updates / 'A/TrustedComposition.Private.dll')
        elif defect == 'missing-helper':
            (updates / 'A/TrustedComposition.IlOnlyHelper.dll').unlink()
        report_path = directory / 'report.json'
        command = [str(dotnet), 'exec', '--fx-version', '12.0.0', str(host),
                   '--updates', str(updates), '--report', str(report_path)]
        process = subprocess.run(command, env=env, cwd=evidence, capture_output=True, timeout=180)
        (directory / 'stdout.log').write_bytes(process.stdout)
        (directory / 'stderr.log').write_bytes(process.stderr)
        record = dict(name=name, command=command, settings=settings, exitCode=process.returncode)
        runs.append(record)
        save(output / 'commands.json', runs)
        if not report_path.is_file():
            raise ValueError('Missing standalone JSON report: ' + name)
        report = json.loads(report_path.read_text(encoding='utf-8-sig'))
        if defect:
            if process.returncode != 1 or report.get('Passed') is not False:
                raise ValueError('Broken dependency unexpectedly accepted: ' + name)
            error = report.get('Error', '')
            expected = 'Private assembly identity differs' if defect == 'wrong-private-version' else 'TrustedComposition.IlOnlyHelper'
            if expected not in error:
                raise ValueError('Dependency rejected for an unexpected reason: ' + name + ': ' + error)
            record.update(passed=True, rejected=True, expectedDiagnostic=expected)
        else:
            sessions = report.get('Sessions', [])
            if process.returncode != 0 or report.get('Passed') is not True:
                raise ValueError('Fresh valid recovery failed: ' + name)
            if len(sessions) != 5 or not all(session.get('Collected') for session in sessions):
                raise ValueError('Recovery contexts did not all collect: ' + name)
            if [session['Version'] for session in sessions] != ['A', 'B', 'A', 'A', 'A']:
                raise ValueError('Recovery version sequence differs: ' + name)
            if sum(bool(session['ExpectedFailure']) for session in sessions) != 1 or report.get('HostTouches') != 9:
                raise ValueError('Recovery managed-failure/callback accounting differs: ' + name)
            record.update(passed=True, rejected=False, collected=5)
        save(output / 'commands.json', runs)

    try:
        invoke('wrong-private-version', 'wrong-private-version')
        invoke('recovery-after-wrong-private')
        invoke('missing-helper', 'missing-helper')
        invoke('recovery-after-missing-helper')
        if hashes(original) != original_hashes:
            raise ValueError('Original update inputs changed during loader controls')
        result = dict(passed=True, processes=4, rejected=2, recoveryProcesses=2,
                      recoveryContextsCollected=10, originalInputsUnchanged=True, controls=runs)
        save(output / 'result.json', result)
        print(json.dumps(result))
        return 0
    except Exception as error:
        result = dict(passed=False, error=str(error), controls=runs)
        save(output / 'result.json', result)
        print(json.dumps(result), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
