#!/usr/bin/env python3
"""Join the four frozen parent/OFF/ON/parent runs without retiming them."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import statistics


PARENT = 'a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186'
CHILD = '29ff781e157be82ba5a398a60bb05291e4a865af'
LABELS = ('parent-before', 'off', 'on', 'parent-after')
SHARED_KEYS = ('upstreamBase', 'platform', 'configuration', 'hostBuildSdkSha256',
               'hostBuildSdkVersion', 'pairs', 'samplesPerProcess', 'machine',
               'processor', 'baseline', 'affinity', 'scope', 'cpu')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def load_run(root, label):
    directory = root / f'performance-{label}-20261014-attempt1'
    audit_path = root / f'performance-{label}-review-20261014-attempt1/results.json'
    request, result, audit = (read(directory / 'request.json'),
                              read(directory / 'results.json'), read(audit_path))
    expected_commit = CHILD if label in ('off', 'on') else PARENT
    assert request['candidateCommit'] == audit['evidence']['candidateCommit'] == expected_commit
    assert result['passed'] and audit['passed']
    assert audit['resultSha256'] == sha(directory / 'results.json')
    assert result['requestSha256'] == sha(directory / 'request.json')
    assert result['managedIdentitySha256'] == sha(directory / 'managed-identity.json')
    controls = audit['corruptionControls']
    assert len(controls) == (14 if label in ('off', 'on') else 13)
    assert len({c['name'] for c in controls}) == len(controls)
    assert all(c['rejected'] for c in controls)
    assessor = Path(__file__).with_name('audit-derived-ledger-overhead.py'
                     if label in ('off', 'on') else 'audit-phase-load-overhead.py')
    assert audit['assessorSha256'] == sha(assessor)
    bindings = {str(p): sha(p) for p in (directory / 'request.json',
                 directory / 'results.json', directory / 'managed-identity.json',
                 audit_path, assessor)}
    sources = {}
    for relative, expected in request['sourceHashes'].items():
        frozen = directory / 'source' / relative
        assert sha(frozen) == expected, relative
        bindings[str(frozen)] = expected
        if not relative.startswith('eng/'):
            sources[relative] = expected
    managed = read(directory / 'managed-identity.json')
    for relative, expected in managed.items():
        frozen = directory / relative
        assert sha(frozen) == expected, relative
        bindings[str(frozen)] = expected
    assert len(result['lanes']) == 8
    summaries, identities, collected = {}, [], 0
    for lane in result['lanes']:
        prefix, receipt, raw = lane['label'], lane['receipt'], lane['raw']
        for suffix in ('.process.json', '.stdout', '.stderr'):
            path = directory / (prefix + suffix)
            bindings[str(path)] = sha(path)
        assert read(directory / (prefix + '.process.json')) == raw
        assert read(directory / (prefix + '.stdout')) == receipt
        assert sha(directory / (prefix + '.stdout')) == raw['stdoutSha256']
        assert sha(directory / (prefix + '.stderr')) == raw['stderrSha256']
        assert raw['exitCode'] == 0 and not raw['timedOut'] and receipt['passed']
        assert receipt['processId'] == raw['pid']
        assert receipt['nonce'] in raw['argv'] and receipt['nonce'] in prefix
        if label in ('off', 'on'):
            value = 1 if label == 'on' else 0
            assert raw['settings']['DOTNET_RuneCLRDerivedLedger'] == str(value)
            assert request['derivedLedgerValue'] == result['derivedLedgerValue'] == value
        assert raw['settings']['DOTNET_RuneCLRPhaseAcquireLoad'] == '1'
        assert request['phaseAcquireValue'] == result['phaseAcquireValue'] == 1
        assert (receipt['iterations'], receipt['warmups'], receipt['sampleCount'],
                receipt['affinity'], receipt['cleanupLimit']) == (100000, 3, 9, 4, 4096)
        assert len(receipt['Callbacks']) == 9
        assert receipt['directCollected'] and receipt['sessionCollected'] == 12
        for callback in receipt['Callbacks']:
            assert callback['Checksum'] == 12749776
            if receipt['mode'] == 'high-budget':
                assert callback['DispatchDelta'] == 2600016
        collected += 1 + receipt['sessionCollected']
        identities.append({'pid': raw['pid'], 'nonce': receipt['nonce']})
    for mode in ('no-config', 'high-budget'):
        receipts = [l['receipt'] for l in result['lanes'] if l['receipt']['mode'] == mode]
        callbacks = [s['Milliseconds'] for r in receipts for s in r['Callbacks']]
        sessions = [s['Milliseconds'] for r in receipts for s in r['Samples'] if not s['Warmup']]
        assert len(receipts) == 4 and len(callbacks) == len(sessions) == 36
        summary = {'callbackMedianMs': statistics.median(callbacks),
                   'sessionMedianMs': statistics.median(sessions)}
        for key, value in summary.items():
            assert result['summaries'][mode][key] == value
        summaries[mode] = summary
    assert collected == audit['evidence']['contextsCollected'] == 104
    return {'label': label, 'commit': expected_commit, 'shared': {k: request[k] for k in SHARED_KEYS},
            'sources': sources, 'managed': managed, 'identities': identities,
            'collections': collected, 'summaries': summaries, 'bindings': bindings}


def verify_join(runs):
    assert [r['label'] for r in runs] == list(LABELS)
    reference = runs[0]
    assert len(reference['sources']) == 24 and len(reference['managed']) == 20
    for run in runs:
        assert run['shared'] == reference['shared']
        assert run['sources'] == reference['sources']
        assert run['managed'] == reference['managed']
    identities = [i for r in runs for i in r['identities']]
    assert len(identities) == len({i['pid'] for i in identities}) == 32
    assert len({i['nonce'] for i in identities}) == 32
    assert sum(r['collections'] for r in runs) == 416


def compare(runs):
    by_label = {r['label']: r['summaries'] for r in runs}
    ratios = {label: s['high-budget']['callbackMedianMs'] / s['no-config']['callbackMedianMs']
              for label, s in by_label.items()}
    changes = {}
    for baseline in ('parent-before', 'parent-after', 'off'):
        changes[baseline] = {key: 100 * (1 - by_label['on']['high-budget'][key] /
                                        by_label[baseline]['high-budget'][key])
                             for key in ('callbackMedianMs', 'sessionMedianMs')}
    drift = {mode: {key: 100 * (by_label['parent-after'][mode][key] /
                              by_label['parent-before'][mode][key] - 1)
                    for key in ('callbackMedianMs', 'sessionMedianMs')}
             for mode in ('no-config', 'high-budget')}
    return {'configuredCallbackRatios': ratios, 'onTimeReductionPercent': changes,
            'parentAfterIncreasePercent': drift}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite an existing comparison receipt')
    runs = [load_run(args.evidence_root, label) for label in LABELS]
    verify_join(runs)
    controls = []
    for name in ('managed-image', 'author-source', 'cpu', 'sample-count',
                 'duplicate-pid', 'duplicate-nonce', 'collection-total', 'order'):
        changed = copy.deepcopy(runs)
        if name == 'managed-image':
            changed[2]['managed'][next(iter(changed[2]['managed']))] = '0' * 64
        elif name == 'author-source':
            changed[2]['sources']['benchmarks/RuneCLR.BudgetKernel/Kernel.cs'] = '0' * 64
        elif name == 'cpu':
            changed[2]['shared']['cpu']['Name'] = 'different machine'
        elif name == 'sample-count':
            changed[2]['shared']['samplesPerProcess'] = 10
        elif name == 'duplicate-pid':
            changed[2]['identities'][0]['pid'] = changed[0]['identities'][0]['pid']
        elif name == 'duplicate-nonce':
            changed[2]['identities'][0]['nonce'] = changed[0]['identities'][0]['nonce']
        elif name == 'collection-total':
            changed[2]['collections'] -= 1
        else:
            changed[1], changed[2] = changed[2], changed[1]
        try:
            verify_join(changed)
        except AssertionError:
            controls.append({'name': name, 'rejected': True})
        else:
            raise AssertionError(f'Accepted corrupted join: {name}')
    report = {'passed': True, 'assessorSha256': sha(Path(__file__)), 'processes': 32,
              'contextsCollected': 416, 'sharedSourceFiles': 24, 'managedInventoryFiles': 20,
              'corruptionControls': controls, **compare(runs), 'runs': runs,
              'limits': 'One desktop arithmetic kernel; configured-meter incremental cost. '
                        'No batching, mobile performance or complete invocation trace.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'runs'}, indent=2))


if __name__ == '__main__':
    main()
