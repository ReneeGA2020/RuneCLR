#!/usr/bin/env python3
"""Recompute representative timing from raw receipts after exclusive timing ends."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

PROFILES = ['parent-before', 'off', 'on', 'parent-after']
WORKLOADS = ['entities', 'host-api']
MODES = ['no-config', 'high-budget']
COUNTS = {'entities': (4135081, 12405370), 'host-api': (229908, 689851)}
LIMIT = 1000000000000
UPSTREAM = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
COMMITS = {'phase-load': 'a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186',
           'derived-ledger': '29ff781e157be82ba5a398a60bb05291e4a865af'}
DRIVER = '19a3ba375d1e5694eac6ae7b7e8ddf262bfc4a5d8aac6f668ba3ef60e5f03a56'
FEATURES = {'CLR_CMAKE_TARGET_ARCH': 'x64', 'CLR_CMAKE_TARGET_OS': 'windows',
            'CMAKE_BUILD_TYPE': 'Release', 'FEATURE_INTERPRETER': '1',
            'FEATURE_DYNAMIC_CODE_COMPILED': '1'}


def need(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def oracle(workload, session=False):
    if workload == 'host-api':
        operations = 8192 * (3 if session else 1)
        return operations * (operations + 1) // 2
    checksum = sum((13 * i + 200 * (i % 7 + 1)) % 65521 +
                   (17 * i + 200 * (i % 11 + 1)) % 65521 +
                   (100 + 200 * i + 200 * 199 // 2) % 1000 for i in range(512))
    return checksum * (3 if session else 1)


def ledger(actual, count):
    need(actual == {'ExecutionRemaining': LIMIT - count, 'ExecutionExecuted': count,
                    'ExecutionExhausted': False, 'IsTerminated': False, 'Reason': 0, 'Phase': 0,
                    'CleanupRemaining': 4096, 'CleanupExecuted': 0}, 'Native admitted-dispatch ledger differs')


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def receipt(actual, plan, raw):
    workload, configured = plan['workload'], plan['mode'] == 'high-budget'
    delta, session_count = COUNTS[workload]
    need(actual['passed'] and actual['nonce'] == plan['nonce'] and actual['processId'] == raw['pid']
         and actual['workload'] == workload and actual['mode'] == plan['mode'], 'Raw receipt process/workload identity differs')
    need(actual['affinity'] == 4 and actual['architecture'] == 'X64' and actual['runtime'].startswith('.NET 12.')
         and actual['warmups'] == 3 and actual['sampleCount'] == 9 and actual['entityCount'] == 512
         and actual['iterations'] == (200 if workload == 'entities' else 8192) and actual['cleanupLimit'] == 4096
         and actual['budgetLimit'] == (LIMIT if configured else None), 'Raw sample/runtime/budget parameters differ')
    need(actual['directCollected'] and actual['sessionCollected'] == 12, 'Actual collectible contexts differ')
    need(len(actual['WarmupMilliseconds']) == 3 and all(positive(v) for v in actual['WarmupMilliseconds'])
         and positive(actual['SetupMilliseconds']), 'Missing actual setup/warmup durations')
    need(len(actual['Callbacks']) == 9 and len(actual['Samples']) == 12
         and [x['Warmup'] for x in actual['Samples']] == [True] * 3 + [False] * 9, 'Warmup/sample selection differs')
    names = ['RuneCLR.BudgetWorkloadScripts.WorkloadEntries.' + ('Entities' if workload == 'entities' else 'HostApi'),
             'RuneCLR.Performance.Workloads.' + ('EntitiesObjects' if workload == 'entities' else 'HostApi')]
    need([p['Method'] for p in actual['Proof']] == names and
         all(p['Interpreted'] and p['StubType'] == 6 for p in actual['Proof']) and
         not actual['hostProof']['Interpreted'] and all(not p['Interpreted'] for p in actual['trustedAdapterProof']),
         'Selected author/trusted method entry observations differ')
    for i, sample in enumerate(actual['Callbacks']):
        need(positive(sample['Milliseconds']) and sample['Checksum'] == oracle(workload)
             and type(sample['AllocatedBytes']) is int and sample['AllocatedBytes'] >= 0
             and len(sample['GcCounts']) == 3 and all(type(n) is int and n >= 0 for n in sample['GcCounts']),
             'Callback checksum/time/allocation/GC observation differs')
        if configured:
            need(sample['ExecutedBefore'] == (3 + i) * delta and sample['ExecutedAfter'] == (4 + i) * delta
                 and sample['DispatchDelta'] == delta, 'Configured callback execution quantity differs')
        else:
            need(all(sample[key] is None for key in ['ExecutedBefore', 'ExecutedAfter', 'DispatchDelta']),
                 'No-config callback reports a meter')
    if configured:
        ledger(actual['FinalSnapshot'], 12 * delta)
    else:
        need(actual['FinalSnapshot'] is None, 'No-config context reports a final meter')
    expected_logs = ((['benchmark-tick'] * 384 if workload == 'host-api' else []) +
        ['budget-workloads:' + workload + ':starts=1;sum=' + str(oracle(workload, True))])
    entities = 24576 if workload == 'host-api' else 0
    for sample in actual['Samples']:
        need(positive(sample['Milliseconds']) and sample['Checksum'] == oracle(workload, True)
             and sample['CompletedTicks'] == 3 and sample['CreatedEntities'] == sample['ReleasedEntities'] == entities
             and sample['RemainingEntities'] == 0 and sample['Logs'] == expected_logs,
             'Session execution/checksum/static reset/entities/logs differ')
        if configured:
            ledger(sample['Budget'], session_count)
        else:
            need(sample['Budget'] is None, 'No-config session reports a meter')
    return {'callback': [x['Milliseconds'] for x in actual['Callbacks']],
            'session': [x['Milliseconds'] for x in actual['Samples'] if not x['Warmup']],
            'callbackAllocations': [x['AllocatedBytes'] for x in actual['Callbacks']],
            'callbackGcTotals': [sum(x['GcCounts'][g] for x in actual['Callbacks']) for g in range(3)]}


def native_binding(kind, native):
    evidence = Path('E:/RuneCLR/artifacts') / kind / 'windows-release-build-20261014-attempt1'
    runtime = Path('E:/runtime-' + kind + '-20261014')
    need(Path(native['buildEvidence']) == evidence and Path(native['layout']) == evidence / 'layout'
         and Path(native['runtime']) == runtime and native['commit'] == COMMITS[kind]
         and native['upstreamBase'] == UPSTREAM and native['cmakeFeatures'] == FEATURES,
         'Native build scope/commit/path/features differ from independent fixed identities')
    request, built, layout = [read(evidence / name) for name in
                              ['request.json', 'build-result.json', 'layout-receipt.json']]
    for name, actual in [('request.json', request), ('build-result.json', built), ('layout-receipt.json', layout)]:
        need(actual['candidateCommit'] == COMMITS[kind] and
             actual['candidateCheckerSha256'] == native['checkerSha256'] and
             actual['candidateValidation'] == native['candidateValidation'] and
             actual['configuration'] == 'Release', 'Native receipt fixed candidate binding differs')
        need(sha(evidence / name) == native['receiptHashes'][str(evidence / name)],
             'Native receipt digest differs')
    need(request['upstreamBase'] == layout['upstreamBase'] == UPSTREAM and
         request['sourceHashes'] == built['sourceHashes'] == native['sourceHashes'] and
         len(native['sourceHashes']) == 36 and len(native['criticalProductHashes']) == 8 and
         built['criticalProductHashes'] == layout['criticalProductHashes'] == native['criticalProductHashes'] and
         built['cmakeFeatures'] == FEATURES and built['exitCode'] == 0 and layout['passed'] and
         built['requestSha256'] == layout['buildRequestSha256'] == sha(evidence / 'request.json') and
         layout['buildResultSha256'] == sha(evidence / 'build-result.json') and
         layout['allLayoutHashes'] == native['allLayoutHashes'], 'Native receipt source/product chain differs')
    for relative, expected in native['sourceHashes'].items():
        need(sha(runtime / relative) == expected, 'Current fixed runtime source differs: ' + relative)
    for relative, expected in native['criticalProductHashes'].items():
        need(sha(Path(layout['product']) / relative) == expected, 'Actual native build product differs: ' + relative)
    for relative, expected in native['allLayoutHashes'].items():
        need(sha(evidence / 'layout' / relative) == expected, 'Actual launched private runtime image differs: ' + relative)
    return {'commit': COMMITS[kind], 'sourceFiles': 36, 'criticalProducts': 8,
            'privateLayoutFiles': len(native['allLayoutHashes']), 'features': FEATURES,
            'loadedMemoryModulesEnumerated': False}


def launch_binding(preparation, native, plan, raw):
    expected_argv = [str(Path(native['layout']) / 'dotnet.exe'), 'exec', '--fx-version', '12.0.0',
                     str(preparation / 'host/RuneCLR.BudgetWorkloads.dll'),
                     str(preparation / 'author/RuneCLR.BudgetWorkloadScripts.dll'),
                     plan['mode'], plan['workload'], plan['nonce'], '9']
    expected_settings = {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0',
                         'DOTNET_ReadyToRun': '1', 'DOTNET_TieredCompilation': '0',
                         'DOTNET_MULTILEVEL_LOOKUP': '0', 'DOTNET_RuneCLRPhaseAcquireLoad': '1',
                         'DOTNET_RuneCLRDerivedLedger': '1' if plan['profile'] == 'on' else '0'}
    need(raw['argv'] == expected_argv and raw['settings'] == expected_settings,
         'Actual launch differs from independently derived executable/arguments/switches')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['preparation', 'measurement', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    need(not args.output.exists(), 'Fresh independent-review output required')
    args.output.mkdir(parents=True)
    result = {'schema': 'runeclr.representative-budget.independent-raw-review.v1', 'passed': False,
              'reviewerSha256': sha(__file__), 'timingPerformedByReviewer': False,
              'preparation': str(args.preparation), 'measurement': str(args.measurement)}
    try:
        prep = read(args.preparation / 'preparation.json')
        request, recorded = read(args.measurement / 'request.json'), read(args.measurement / 'results.json')
        need(prep['driverSha256'] == DRIVER and sha(Path(__file__).with_name('benchmark-representative-budget.py')) == DRIVER,
             'Preparation driver differs from independent fixed driver hash')
        native_review = {kind: native_binding(kind, prep['buildBindings'][kind]) for kind in COMMITS}
        need(prep['passed'] and prep['parameters']['labels'] == PROFILES and prep['parameters']['workloads'] == WORKLOADS
             and prep['parameters']['modes'] == MODES and prep['parameters']['samples'] == 9
             and prep['parameters']['warmups'] == 3 and prep['parameters']['pairedRounds'] == 4, 'Frozen exact bracket parameters differ')
        need(request['preparationSha256'] == sha(args.preparation / 'preparation.json')
             and request['selftestSha256'] == sha(args.preparation / 'selftest.json')
             and request['parameters'] == prep['parameters'] and request['plan'] == prep['plan']
             and request['driverSha256'] == prep['driverSha256'] and request['timingPerformed'] and not request['managedRebuilt'],
             'Actual run request differs from frozen preparation')
        need(recorded['passed'] and recorded['requestSha256'] == sha(args.measurement / 'request.json')
             and len(recorded['lanes']) == len(prep['plan']) == 64, 'Actual completed64 process set required')
        frozen_order = [(p, w, pair, i, mode) for p in PROFILES for w in WORKLOADS
                        for pair in range(4) for i, mode in enumerate(MODES if pair % 2 == 0 else list(reversed(MODES)))]
        need([(p['profile'], p['workload'], p['pair'], p['position'], p['mode']) for p in prep['plan']] == frozen_order,
             'Bracket/alternating-pair order changed')
        values, pids, nonces, raw_hashes, lane_details = {}, set(), set(), {}, []
        for planned, lane in zip(prep['plan'], recorded['lanes']):
            need(all(lane[key] == value for key, value in planned.items()), 'Actual lane relabeled from planned launch')
            for suffix in ['stdout', 'stderr', 'command']:
                path = args.measurement / lane[suffix]
                need(path.parent == args.measurement and sha(path) == lane[suffix + 'Sha256'], 'Raw lane filename/hash changed')
                raw_hashes[lane[suffix]] = sha(path)
            raw, actual = read(args.measurement / lane['command']), read(args.measurement / lane['stdout'])
            need(raw == lane['raw'] and actual == lane['receipt'] and raw['argv'] == planned['argv']
                 and raw['settings'] == planned['settings'] and raw['exitCode'] == 0 and not raw['timedOut']
                 and positive(raw['wallSeconds']) and raw['pid'] > 0, 'Actual process raw request/receipt differs')
            need(raw['pid'] not in pids and planned['nonce'] not in nonces, 'Process/nonce reused')
            pids.add(raw['pid']); nonces.add(planned['nonce'])
            profile, workload, mode = planned['profile'], planned['workload'], planned['mode']
            kind = 'derived-ledger' if profile in ['off', 'on'] else 'phase-load'
            native = prep['buildBindings'][kind]
            launch_binding(args.preparation, native, planned, raw)
            sample = receipt(actual, planned, raw)
            key = (profile, workload, mode)
            values.setdefault(key, []).append(sample)
            lane_details.append({'profile': profile, 'workload': workload, 'mode': mode, 'pair': planned['pair'],
                                 'pid': raw['pid'], 'nonce': planned['nonce'],
                                 'callbackMedianMs': statistics.median(sample['callback']),
                                 'sessionMedianMs': statistics.median(sample['session']),
                                 'callbackMedianAllocatedBytes': statistics.median(sample['callbackAllocations']),
                                 'callbackGcTotals': sample['callbackGcTotals']})
        # Only scan large frozen image/source inventories after timing has completed.
        for path, expected in prep['boundInputHashes'].items():
            need(sha(path) == expected, 'Source/native/managed input changed after measured bracket: ' + path)
        for path, expected in prep['snapshotHashes'].items():
            need(sha(args.preparation / path) == expected, 'Frozen source/image snapshot changed')
        for path, expected in prep['managedHashes'].items():
            need(sha(args.preparation / path) == expected, 'Measured host/author managed input changed')
        pooled, ratios, drift, pairs = {}, {}, {}, []
        for profile in PROFILES:
            pooled[profile], ratios[profile] = {}, {}
            for workload in WORKLOADS:
                pooled[profile][workload] = {}
                for mode in MODES:
                    samples = values[profile, workload, mode]
                    need(len(samples) == 4, 'Expected four process medians per cell')
                    pooled[profile][workload][mode] = {scope: {
                        'pooledSampleMedianMs': statistics.median(x for r in samples for x in r[scope]),
                        'medianOfProcessMediansMs': statistics.median(statistics.median(r[scope]) for r in samples),
                        'processMediansMs': [statistics.median(r[scope]) for r in samples]} for scope in ['callback', 'session']}
                ratios[profile][workload] = {scope: pooled[profile][workload]['high-budget'][scope]['pooledSampleMedianMs'] /
                    pooled[profile][workload]['no-config'][scope]['pooledSampleMedianMs'] for scope in ['callback', 'session']}
                for pair in range(4):
                    members = {x['mode']: x for x in lane_details if x['profile'] == profile
                               and x['workload'] == workload and x['pair'] == pair}
                    pairs.append({'profile': profile, 'workload': workload, 'pair': pair, 'configuredRatio':
                        {scope: members['high-budget'][scope + 'MedianMs'] / members['no-config'][scope + 'MedianMs']
                         for scope in ['callback', 'session']}})
        for workload in WORKLOADS:
            drift[workload] = {mode: {scope: pooled['parent-after'][workload][mode][scope]['pooledSampleMedianMs'] /
                pooled['parent-before'][workload][mode][scope]['pooledSampleMedianMs'] for scope in ['callback', 'session']} for mode in MODES}
        result.update(passed=True, processes=len(pids), contextsCollected=64 * 13, measuredCallbackSamples=64 * 9,
                      measuredSessionSamples=64 * 9, warmupSessionSamples=64 * 3, rawHashes=raw_hashes,
                      preparationSha256=sha(args.preparation / 'preparation.json'), resultSha256=sha(args.measurement / 'results.json'),
                      nativeAndSourceInventoryAfterUnchanged=True, nativeBuildReview=native_review,
                      independentlyDerivedLaunches=True, pooled=pooled, configuredRatios=ratios,
                      parentEndpointRatios=drift, pairedRatios=pairs, processMedians=lane_details,
                      noConfigMeaning='Required-interpreter instrumented build retaining owner lookup and null-meter branch',
                      callbackScope='Fresh adapter plus author entry/helper plus verification, warmed shared ALC; excludes setup/collection',
                      sessionScope='Fresh production MapRunner ALC with3ticks and retirement; excludes later diagnostic collection',
                      statisticalLimit='36 pooled samples/cell are nested in4processes; profiles form sequential time blocks, not interleaved cross-profile pairs',
                      batchingMeasured=False, selectedEntryProofOnly=True, physicalDeviceExecution=False)
    except Exception as error:
        result['error'] = str(error)
    (args.output / 'results.json').write_text(json.dumps(result, indent=2) + chr(10))
    print(json.dumps({k: v for k, v in result.items() if k not in ['pooled', 'rawHashes', 'processMedians', 'pairedRatios']}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
