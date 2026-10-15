#!/usr/bin/env python3
"""Replay original simulator timing brackets and recompute callback comparisons."""
import argparse
import hashlib
import importlib.util
import json
import math
import statistics
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def need(value, message):
    if not value:
        raise RuntimeError(message)


def module(name, filename, digest):
    path = Path(filename)
    if not path.is_absolute():
        path = Path(__file__).parent / path
    need(sha(path) == digest, 'Frozen reviewer changed: ' + str(filename))
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def review(run, application, inputs, samples=9, driver_name='ios-batch-timing-run.py',
           driver_sha='6901a31f39ce40b70071fa9a4815db50bb54b3eb6956774d454ebaf8e04b7186'):
    need(type(samples) is int and 1 <= samples <= 100, 'Invalid callback sample count')
    timing = module('timing_replay', 'assess-mobile-batch-timing.py',
                    '33687721115a7c45e72e35345ecca1a44652ca650b07b8750d8cdbc92010809d')
    driver = module('ios_timing_original', driver_name, driver_sha)
    read = timing.kernel().load
    request, state = read(run / 'request.json'), read(application / 'state.json')
    provenance = read(application / 'timing-provenance.json')
    need(request['schema'] == 'runeclr.ios-batch-timing.run.v1' and request['debugger'] is False,
         'Original debugger-free request missing')
    need(request['plan'] == driver.plan(), 'Sixteen-process bracket order differs')
    need(request['frozen']['driver'] == driver_sha and request['driverSha256'] == driver_sha,
         'Requested runner source differs')
    need(all(cell['sampleCount'] == samples and cell['warmups'] == 3 for cell in driver.plan()),
         'Requested samples/warmups differ')
    settling = None
    if 'settleSeconds' in request:
        need(request['measuredSamplesPerProcess'] == samples and request['warmupsPerProcess'] == 3,
             'Repeat parameter fields differ')
        settling = read(run / 'settle.json')
        expected_settle = driver.SETTLE_SECONDS
        need(type(request['settleSeconds']) is int and request['settleSeconds'] == expected_settle and
             type(settling['requestedSeconds']) is int and settling['requestedSeconds'] == expected_settle,
             'Settling request differs')
        start, end, elapsed = (settling[key] for key in
                               ('startedMonotonic', 'finishedMonotonic', 'elapsedSeconds'))
        need(all(type(value) in (int, float) and math.isfinite(value) for value in (start, end, elapsed)) and
             0 <= start < end and elapsed >= expected_settle and
             math.isclose(elapsed, end - start, rel_tol=1e-12, abs_tol=0) and settling['passed'] is True,
             'Actual post-install settling duration differs')
    for key, path in (('state', application / 'state.json'),
                      ('provenance', application / 'timing-provenance.json'),
                      ('manifest', inputs / 'input-manifest.json')):
        need(sha(path) == request['frozen'][key], 'Request binding differs: ' + key)
    manifest = read(inputs / 'input-manifest.json')
    for name, digest in manifest['files'].items():
        path = (inputs / name).resolve()
        need(path.is_relative_to(inputs.resolve()) and sha(path) == digest, 'Frozen input differs: ' + name)
    component = provenance['contractComponentSha256']
    need(component == request['contractComponentSha256'] == state['bundleHashes']['RuneCLR.Abstractions.dll'],
         'Loaded contract binding differs')
    need(read(run / 'installed-before.json') == read(run / 'installed-after.json') == state['bundleHashes'],
         'Installed application changed during timing')
    need(read(run / 'author-before.json') == read(run / 'author-after.json') == {
        'RuneCLR.BatchKernel.dll': manifest['authorSha256'],
        'RuneCLR.Abstractions.dll': manifest['contractSha256']}, 'Post-install author bytes differ')
    cleanup = read(run / 'cleanup.json')
    need(cleanup['shutdownVerified'] is True and cleanup['observedStates'] == ['Shutdown'],
         'Owned simulator cleanup missing')
    quiet_files = list(run.glob('quiet-*.json')) + list(run.glob('*/quiet-*.json'))
    need(len(quiet_files) == 35, 'Quiet process snapshots missing')
    for path in quiet_files:
        quiet = read(path)
        need(quiet['passed'] is True and all(row['blockedReason'] is None for row in quiet['processes']),
             'Compiler/debugger/other experiment present: ' + str(path))
    observations, pids, nonces = [], set(), set()
    for cell in driver.plan():
        directory = run / cell['label']
        launch = read(directory / 'request.json')
        nonce = launch['nonce']
        need(all(launch[key] == value for key, value in cell.items()) and launch['debugger'] is False,
             'Cell order/identity differs')
        need(launch['settings'] == driver.launch_settings(cell, nonce), 'Native launch settings differ')
        owner = read(run / 'owned-simulator.json')
        need(launch['argv'] == ['xcrun', 'simctl', 'launch', '--console', '--terminate-running-process',
                                owner['id'], state['bundleId']], 'Owned application launch differs')
        process = read(directory / 'native.log.process.json')
        command = read(directory / 'native.log.request.json')
        need(process['exitCode'] == 0 and process['timedOut'] is False and
             process['argv'] == command['argv'] == launch['argv'] and
             process['logSha256'] == sha(directory / 'native.log'), 'Raw console process failed or changed')
        receipt = read(directory / 'receipt.json')
        pid = receipt['processId']
        need(pid not in pids and nonce not in nonces, 'Process/nonce reused')
        pids.add(pid)
        nonces.add(nonce)
        driver.validate_log((directory / 'native.log').read_text(encoding='utf-8'), cell, nonce, pid)
        assessed = timing.review(receipt, cell['mode'], cell['lane'], nonce, pid, samples,
                                 'iossimulator.arm64', component)
        observations.append(dict(assessed, profile=cell['profile'], pair=cell['pair'],
                                 receiptSha256=sha(directory / 'receipt.json')))
    profiles = {}
    for profile in ('exact-before', 'N100', 'N1000', 'exact-after'):
        modes = {}
        for mode in ('no-config', 'high-budget'):
            rows = [row for row in observations if row['profile'] == profile and row['mode'] == mode]
            values = [value for row in rows for value in row['callbackMilliseconds']]
            need(len(rows) == 2 and len(values) == 2 * samples, 'Profile process/sample count differs')
            modes[mode] = {'medianMs': statistics.median(values), 'minimumMs': min(values),
                           'maximumMs': max(values),
                           'processMediansMs': [row['callbackMedianMilliseconds'] for row in rows]}
        modes['configuredOverNoConfig'] = modes['high-budget']['medianMs'] / modes['no-config']['medianMs']
        modes['pairedProcessRatios'] = [modes['high-budget']['processMediansMs'][pair] /
                                        modes['no-config']['processMediansMs'][pair] for pair in range(2)]
        profiles[profile] = modes
    comparisons = {profile: {bracket + 'BudgetTimeReductionPercent':
        100 * (1 - profiles[profile]['high-budget']['medianMs'] / profiles[bracket]['high-budget']['medianMs'])
        for bracket in ('exact-before', 'exact-after')} for profile in ('N100', 'N1000')}
    drift = {mode: 100 * (profiles['exact-after'][mode]['medianMs'] /
                         profiles['exact-before'][mode]['medianMs'] - 1)
             for mode in ('no-config', 'high-budget')}
    additional = 100 * (1 - profiles['N1000']['high-budget']['medianMs'] /
                         profiles['N100']['high-budget']['medianMs'])
    return {'passed': True, 'platform': 'iossimulator.arm64', 'processes': 16, 'callbacks': 16 * (samples + 3),
            'measuredSamples': 16 * samples, 'warmupCallbacks': 48, 'collections': 16,
            'samplesPerProcess': samples, 'runnerSha256': driver_sha,
            'settling': settling,
            'quietSnapshots': len(quiet_files), 'profiles': profiles, 'comparisons': comparisons,
            'exactBracketDriftPercent': drift, 'observations': observations,
            'N1000VersusN100BudgetTimeReductionPercent': additional,
            'rawLaunchLedgerAndTimingVerified': True, 'nativeEntryProof': False,
            'physicalDeviceVerified': False,
            'scope': 'Original launches, installed hashes, typed ledgers and monotonic ticks replayed. Application build/native byte provenance needs separate review. Arithmetic kernel simulator callback timing only.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('run', 'application', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--samples', type=int, default=9)
    parser.add_argument('--driver', default='ios-batch-timing-run.py')
    parser.add_argument('--driver-sha256', default='6901a31f39ce40b70071fa9a4815db50bb54b3eb6956774d454ebaf8e04b7186')
    args = parser.parse_args()
    result = review(args.run, args.application, args.inputs, args.samples, args.driver, args.driver_sha256)
    result['reviewerSha256'] = sha(Path(__file__))
    with args.output.open('x', encoding='ascii') as stream:
        json.dump(result, stream, indent=2)
        stream.write(chr(10))
    print(json.dumps({key: value for key, value in result.items() if key != 'observations'}, indent=2))


if __name__ == '__main__':
    main()
