#!/usr/bin/env python3
"""Verify downloaded immutable session-policy archives and every member hash."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--assemble-parts', action='store_true')
    args = parser.parse_args()
    root = args.directory.resolve()
    catalog = json.loads((root / 'archives.json').read_text())
    ledgers, selected, member_hashes, members_checked = {}, {}, {}, 0
    for label, record in catalog.items():
        archive = root / (label + '.tar.gz')
        if args.assemble_parts:
            with archive.open('xb') as stream:
                for offset in range(0, record['sizeBytes'], 16000):
                    block = (root / 'parts' / (label + '-' + str(offset) + '.bin')).read_bytes()
                    assert len(block) == min(16000, record['sizeBytes'] - offset)
                    stream.write(block)
        assert archive.stat().st_size == record['sizeBytes'], label
        assert digest(archive.read_bytes()) == record['sha256'], label
        with tarfile.open(archive) as package:
            members = package.getmembers()
            assert len(members) == record['fileCount']
            names = [item.name for item in members]
            assert len(set(names)) == len(names)
            for item in members:
                name = PurePosixPath(item.name)
                assert item.isfile() and not name.is_absolute() and '..' not in name.parts
            ledger_name = next(name for name in names if name.endswith('/' + label + '-member-manifest.json'))
            ledger = json.load(package.extractfile(ledger_name))
            assert set(names) == {ledger_name, *(row['path'] for row in ledger['files'])}
            for row in ledger['files']:
                data = package.extractfile(row['path']).read()
                assert len(data) == row['sizeBytes'] and digest(data) == row['sha256'], row['path']
                assert member_hashes.get(row['path'], row['sha256']) == row['sha256']
                member_hashes[row['path']] = row['sha256']
                members_checked += 1
                if row['path'].endswith('.json'):
                    selected[row['path']] = json.loads(data)
            ledgers[label] = ledger
    prefix = 'ios-session-policy-player-20261013-attempt1/'
    lanes = {lane: selected[prefix + 'run-' + lane + '/results.json']
             for lane in ('sample', 'packages', 'lifecycle', 'selection')}
    assert all(result['passed'] and result['nativeManagedExitZero'] and
               result['explicitMode0Diagnostic0'] and result['bundleUnchanged'] and
               result['payloadUnchanged'] and result['lldbExit'] == 0 for result in lanes.values())
    assert lanes['lifecycle']['individualPassed'] == 24
    assert lanes['packages']['individualPassed'] == 15
    assert lanes['selection']['individualPassed'] == 20
    proof = selected['ios-session-policy-entry-20261013-attempt1/entry-assessment.json']
    assert proof['passed'] and not proof['appRerun']
    assert proof['validEntrySamples'] == 11 and len(proof['requiredMethodEntryCounts']) == 9
    assert all(value == 1 for value in proof['requiredMethodEntryCounts'].values())
    assert proof['contextsCollected'] == 20 and proof['requiredPolicyQueryCount'] == 260
    assert proof['retiredQueryGuards'] == 20 and proof['refusalVerified'] is False
    entry_prefix = 'ios-session-policy-entry-20261013-attempt1/'
    state = selected[prefix + 'state.json']
    identity = selected[entry_prefix + 'identity.json']
    source = selected['ios-session-policy-release-20261013/source.json']
    assessment = selected['ios-session-policy-build-assessment-20261013/results.json']
    assert source['commit'] == assessment['candidateCommit'] == identity['runtimeCommit'] == proof['runtimeCommit']
    assert source['tree'] == '71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2'
    assert source['base'] == '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
    assert identity['nativeSha256'] == state['nativeSha256'] == assessment['criticalHashes']['native']
    assert identity['bundleFiles'] == state['bundleHashes']
    for name, expected in source['sourceHashes'].items():
        assert member_hashes['ios-session-policy-release-20261013/runtime/' + name] == expected
    raw_checked = 0
    for directory, receipt in [(prefix + 'run-' + lane + '/', result) for lane, result in lanes.items()] + [
            (entry_prefix, proof), (entry_prefix, selected[entry_prefix + 'outer-results.json'])]:
        for name, expected in receipt['rawHashes'].items():
            assert member_hashes[directory + name] == expected
            raw_checked += 1
    assert selected[prefix + 'cleanup.json']['shutdownExit'] == 0
    assert assessment['success']
    summary = {'passed': True, 'archiveCount': len(catalog), 'memberHashesChecked': members_checked,
               'lifecyclePassed': 24, 'packagePassed': 15, 'selectionSessions': 20,
               'entrySamples': 11, 'requiredMethodGroups': 9, 'policyQueries': 260,
               'retiredQueryGuards': 20, 'shutdownExit': 0, 'refusalVerified': False,
               'applicationsRerun': False, 'rawHashesChecked': raw_checked,
               'sourceHashesChecked': len(source['sourceHashes']),
               'archiveHashes': {key: value['sha256'] for key, value in catalog.items()}}
    receipt = root / 'local-verification.json'
    assert not receipt.exists(), 'Preserve original verification receipt'
    receipt.write_text(json.dumps(summary, indent=2) + chr(10))
    print('PASS ' + json.dumps(summary))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
