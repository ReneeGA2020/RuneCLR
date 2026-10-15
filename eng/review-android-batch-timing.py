#!/usr/bin/env python3
"""Review Android memory-bundle callback timings without rewriting original receipts."""
import argparse
import copy
import hashlib
import importlib.util
import json
import statistics
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timing_module():
    path = Path(__file__).with_name('assess-mobile-batch-timing.py')
    if sha(path) != '33687721115a7c45e72e35345ecca1a44652ca650b07b8750d8cdbc92010809d':
        raise RuntimeError('Frozen timing reviewer changed')
    spec = importlib.util.spec_from_file_location('android_timing_scalar', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def review_observation(receipt, mode, lane, nonce, pid, samples, component_hash):
    timing = timing_module()
    timing.kernel().need(type(receipt) is dict and 'loadedContractComponentHash' in receipt and
                         receipt['loadedContractComponentHash'] is None,
                         'Expected in-memory Android contract Location absence differs')
    adapted = copy.deepcopy(receipt)
    # Supplied bundle binding is external evidence; the managed Location remains absent.
    adapted['loadedContractComponentHash'] = component_hash
    result = timing.review(adapted, mode, lane, nonce, pid, samples, 'Android.x64', component_hash)
    result.update(originalLoadedContractComponentHash=None, originalReceiptUnchanged=True,
                  contractComponentSha256=component_hash,
                  contractBindingScope='Caller must independently establish the supplied R2R component hash from actual APK bytes, installed inventory and raw-IL/MVID provenance. The managed Location is absent.')
    return result


def bind_application(apk, installed):
    scalar = timing_module().kernel()
    read, need = scalar.load, scalar.need
    state, layout = read(apk / 'state.json'), read(apk / 'layout.json')
    need(sha(Path(state['apk'])) == state['apkSha256'] and
         sha(apk / 'layout.json') == state['layoutSha256'], 'Frozen APK/layout identity differs')
    need(layout['commit'] == state['runtimeCommit'] == '3126bbc9a8851a09ac6435b18a12882bad48f3ee' and
         layout['tree'] == state['runtimeTree'] == '710936ae1729a5689ab0e0896f3cf722ddd3d31c',
         'Runtime source binding differs')
    expected = dict(state['appHashes'], **{'apk/base.apk': state['apkSha256'],
                    'author/RuneCLR.BatchKernel.dll': scalar.AUTHOR,
                    'author/RuneCLR.Abstractions.dll': scalar.CONTRACT})
    need(read(installed) == expected, 'Installed APK/author/application inventory differs')
    for name, digest in state['appHashes'].items():
        path = (apk / 'app' / name).resolve()
        need(path.is_relative_to((apk / 'app').resolve()) and sha(path) == digest,
             'Actual application component differs: ' + name)
    need('RuneCLR.BatchKernel.dll' not in state['appHashes'], 'Author present in trusted application')
    contract = next(row for row in layout['files'] if row['path'] == 'managed/RuneCLR.Abstractions.dll')
    need(contract['inputSha256'] == scalar.CONTRACT and
         contract['sha256'] == state['appHashes']['RuneCLR.Abstractions.dll'], 'Raw IL to contract component binding differs')
    return contract['sha256']


def summarize_observations(observations):
    need = timing_module().kernel().need
    profiles, pids, nonces = {}, set(), set()
    need(len(observations) == 16, 'Four profiles require sixteen actual observations')
    for row in observations:
        need(row['passed'] is True and row['rawCallbackTimingVerified'] is True and
             row['scalarLedgerVerified'] is True and row['platform'] == 'Android.x64',
             'Unchecked Android observation')
        need(row['processId'] not in pids and row['nonce'] not in nonces, 'Process/nonce reused')
        pids.add(row['processId'])
        nonces.add(row['nonce'])
        need(row['measuredSamples'] == len(row['callbackMilliseconds']) == 31 and
             row['callbacks'] == 34 and row['collections'] == 1, 'Samples/warmups/collection differs')
    for profile in ('exact-before', 'N100', 'N1000', 'exact-after'):
        modes = {}
        lane = 'best-exact' if profile.startswith('exact-') else profile
        for mode in ('no-config', 'high-budget'):
            rows = sorted((row for row in observations if row['profile'] == profile and row['mode'] == mode),
                          key=lambda row: row['pair'])
            need(len(rows) == 2 and [row['pair'] for row in rows] == [0, 1] and
                 all(row['lane'] == lane for row in rows), 'Actual profile/pair selection differs')
            values = [value for row in rows for value in row['callbackMilliseconds']]
            medians = [statistics.median(row['callbackMilliseconds']) for row in rows]
            modes[mode] = {'medianMs': statistics.median(values), 'processMediansMs': medians,
                           'minimumMs': min(values), 'maximumMs': max(values)}
        modes['configuredOverNoConfig'] = modes['high-budget']['medianMs'] / modes['no-config']['medianMs']
        modes['pairedProcessRatios'] = [modes['high-budget']['processMediansMs'][pair] /
                                        modes['no-config']['processMediansMs'][pair] for pair in (0, 1)]
        profiles[profile] = modes
    return {'profiles': profiles, 'processes': 16, 'measuredSamples': 496, 'warmupCallbacks': 48,
            'collections': 16,
            'exactBracketDriftPercent': {mode: 100 * (profiles['exact-after'][mode]['medianMs'] /
                                                    profiles['exact-before'][mode]['medianMs'] - 1)
                                         for mode in ('no-config', 'high-budget')},
            'comparisons': {profile: {bracket + 'BudgetTimeReductionPercent': 100 * (1 -
                            profiles[profile]['high-budget']['medianMs'] / profiles[bracket]['high-budget']['medianMs'])
                            for bracket in ('exact-before', 'exact-after')} for profile in ('N100', 'N1000')},
            'N1000VersusN100BudgetTimeReductionPercent': 100 * (1 -
                profiles['N1000']['high-budget']['medianMs'] / profiles['N100']['high-budget']['medianMs']),
            'scope': 'Recomputed pooled and paired warmed callback medians. Launch order, product and quiet-window provenance must be independently checked before interpreting comparisons.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('apk', 'installed', 'receipt', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--mode', choices=('no-config', 'high-budget'), required=True)
    parser.add_argument('--lane', choices=('best-exact', 'N100', 'N1000'), required=True)
    parser.add_argument('--nonce', required=True)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--samples', type=int, default=31)
    args = parser.parse_args()
    component = bind_application(args.apk, args.installed)
    result = review_observation(timing_module().kernel().load(args.receipt), args.mode, args.lane,
                                args.nonce, args.pid, args.samples, component)
    result['receiptSha256'] = sha(args.receipt)
    result['reviewerSha256'] = sha(Path(__file__))
    with args.output.open('x', encoding='ascii') as stream:
        json.dump(result, stream, indent=2)
        stream.write(chr(10))
    print('Android actual bundle-bound timing/ledger PASS; full launch/process provenance remains separate')


if __name__ == '__main__':
    main()
