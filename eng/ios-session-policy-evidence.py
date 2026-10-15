#!/usr/bin/env python3
"""Archive completed session-policy evidence without launching applications."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + chr(10))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, out = args.root.resolve(), args.output.resolve()
    out.relative_to(root)
    out.mkdir(exist_ok=False)
    player = root / 'ios-session-policy-player-20261013-attempt1'
    entry = root / 'ios-session-policy-entry-20261013-attempt1'
    build = root / 'ios-session-policy-release-20261013'
    assessment = root / 'ios-session-policy-build-assessment-20261013'
    commit = '1724cdec553a7aff7a373a271a4be612651c7625'
    assert read(build / 'results.json')['success']
    assert read(assessment / 'results.json')['success']
    assert read(assessment / 'results.json')['candidateCommit'] == commit
    checked = 0

    def check_raw(directory, receipt):
        nonlocal checked
        for name, expected in receipt['rawHashes'].items():
            assert digest(directory / name) == expected, (directory, name)
            checked += 1

    lanes = {}
    for lane in ('sample', 'packages', 'lifecycle', 'selection'):
        directory = player / ('run-' + lane)
        result = read(directory / 'results.json')
        assert result['passed'] and result['functionalComplete']
        for key in ('normalNativeExit', 'nativeManagedExitZero',
                    'explicitMode0Diagnostic0', 'bundleUnchanged',
                    'payloadUnchanged', 'noCrashOrAssertion'):
            assert result[key], (lane, key)
        assert result['lldbExit'] == 0 and result['nativeAcknowledgementMarkers'] == 1
        check_raw(directory, result)
        lanes[lane] = result
    assert lanes['packages']['individualPassed'] == 15
    assert lanes['lifecycle']['individualPassed'] == 24
    outer, proof = read(entry / 'outer-results.json'), read(entry / 'entry-assessment.json')
    assert outer['outerTransportPassed'] and proof['passed'] and not proof['appRerun']
    assert proof['runtimeCommit'] == commit
    assert proof['functionalSessions'] == proof['contextsCollected'] == 20
    assert proof['requiredPolicyQueryCount'] == 260 and proof['retiredQueryGuards'] == 20
    assert proof['validEntrySamples'] == 11
    assert len(proof['requiredMethodEntryCounts']) == 9
    assert all(count == 1 for count in proof['requiredMethodEntryCounts'].values())
    assert proof['entryKinds'] == {'stub': 6, 'child': 5}
    check_raw(entry, outer)
    check_raw(entry, proof)
    cleanup = read(player / 'cleanup.json')
    assert cleanup['shutdownExit'] == 0
    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', '--json']))
    device = [item for group in devices['devices'].values() for item in group
              if item['udid'] == cleanup['simulator']]
    assert len(device) == 1 and device[0]['state'] == 'Shutdown'
    audit = {'passed': True, 'runtimeCommit': commit, 'rawHashesChecked': checked,
             'lanes': {name: row['passed'] for name, row in lanes.items()},
             'validEntrySamples': 11, 'requiredMethodGroups': 9,
             'policyQueries': 260, 'retiredQueryGuards': 20,
             'simulatorShutdown': True, 'applicationsRerun': False,
             'scope': 'Receipt integrity and cross-run identity; sampled entry proof is separate'}
    write(out / 'audit.json', audit)
    manifest_tool = Path(__file__).with_name('ios-session-policy-archive-manifest.py')
    manifest = json.loads(subprocess.check_output(['python3', str(manifest_tool),
        '--root', str(root), '--include-pe', '--format', 'json']))
    write(out / 'build-manifest.json', manifest)
    archives = {}

    def archive(label, paths):
        paths = sorted(set(path.resolve() for path in paths))
        rows = [{'path': path.relative_to(root).as_posix(), 'sha256': digest(path),
                 'sizeBytes': path.stat().st_size} for path in paths]
        ledger = out / (label + '-member-manifest.json')
        assert ledger not in paths and not ledger.exists(), 'Member manifest must be a new separate file'
        write(ledger, {'files': rows})
        target = out / (label + '.tar.gz')
        with tarfile.open(target, 'w:gz') as package:
            for path in [ledger, *paths]:
                package.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
        with tarfile.open(target) as package:
            names = package.getnames()
            assert len(names) == len(set(names)) == len(rows) + 1
            for row in rows:
                assert hashlib.sha256(package.extractfile(row['path']).read()).hexdigest() == row['sha256']
        archives[label] = {'path': str(target), 'sha256': digest(target),
                           'sizeBytes': target.stat().st_size, 'fileCount': len(rows) + 1}

    archive('build', [root / row['path'] for row in manifest['files']] +
            [out / 'build-manifest.json', manifest_tool, Path(__file__), out / 'audit.json'])
    suffixes = {'.json', '.log', '.rsp', '.lldb', '.py', '.cs', '.m', '.h'}
    player_files = [path for path in player.rglob('*') if path.is_file() and path.suffix in suffixes]
    player_files += list((player / 'input').glob('RuneCLR.*.dll'))
    for name in ('ios-session-policy-player-tools-20261013',
                 'ios-session-policy-postinstall-inputs-20261013',
                 'ios-session-policy-selection-inputs-20261013'):
        player_files += [path for path in (root / name).rglob('*')
                         if path.is_file() and path.suffix in {'.py', '.json', '.zip'}]
    archive('player', player_files + [out / 'audit.json'])
    entry_files = [path for path in entry.rglob('*') if path.is_file()]
    entry_files += [root / 'ios-session-policy-selection-inputs-20261013/selection-inputs.zip',
                    root / 'ios-session-policy-player-tools-20261013/ios-session-policy-entry.py',
                    root / 'ios-session-policy-player-tools-20261013/ios-session-policy-capture-run.py']
    archive('entry', entry_files + [out / 'audit.json'])
    write(out / 'archives.json', archives)
    print(json.dumps({'audit': audit, 'archives': archives}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
