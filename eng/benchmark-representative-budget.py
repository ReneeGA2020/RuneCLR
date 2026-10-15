#!/usr/bin/env python3
"""Prepare, explicitly time, or review the frozen representative budget bracket."""
import argparse
import ast
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONAL = ROOT / 'artifacts/representative-budget/functional-20261014-attempt3'
VERIFIER = ROOT / 'eng/verify-representative-budget.py'
FUNCTIONAL_PINS = {
    VERIFIER: 'f0e539f415e411156676a8e50685bb91fbef607e9adaf419826dd6057e6544fd',
    FUNCTIONAL / 'results.json': '449ac485ec91678cfed7ed72566de8a8d646ba3f9c150cc24015bfd40a81e69e',
    FUNCTIONAL / 'frozen-inputs.json': '97f1cb45a61c8c72fb70bbf0d6c1be8765966de3248bb1d5a93f0dbf81d543d8',
    FUNCTIONAL / 'request.json': 'f3391de519d8fe2a79bdbdef6884ed4e352d3175438613a86ea043a6b5b840ac',
}
UPSTREAM = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
PARENT = 'a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186'
CHILD = '29ff781e157be82ba5a398a60bb05291e4a865af'
LABELS = ('parent-before', 'off', 'on', 'parent-after')
WORKLOADS = ('entities', 'host-api')
MODES = ('no-config', 'high-budget')
COUNTS = {'entities': {'callback': 4135081, 'session': 12405370},
          'host-api': {'callback': 229908, 'session': 689851}}
LIMIT = 1_000_000_000_000
BASELINE = 'Same instrumented required-interpreter runtime without a configured meter; owner lookup and null-meter branch remain.'
CALLBACK_SCOPE = 'Fresh trusted-adapter creation, author entry/helper execution, adapter verification; excludes ALC setup/collection.'
SESSION_SCOPE = 'Fresh MapRunner session, three ticks and retirement; excludes diagnostic collection.'
FEATURES = {'CLR_CMAKE_TARGET_ARCH': 'x64', 'CLR_CMAKE_TARGET_OS': 'windows',
            'CMAKE_BUILD_TYPE': 'Release', 'FEATURE_INTERPRETER': '1', 'FEATURE_DYNAMIC_CODE_COMPILED': '1'}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    with Path(path).open('x', encoding='ascii') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def hashes(paths):
    return {str(Path(path).resolve()): sha(path) for path in paths}


def check_hashes(values):
    for path, expected in values.items():
        require(sha(path) == expected, 'Bound input changed: ' + path)


def functional_inputs():
    check_hashes({str(path): value for path, value in FUNCTIONAL_PINS.items()})
    original = read(FUNCTIONAL / 'frozen-inputs.json')
    require(len(original) == 1111, 'Original 1111 source/native/managed inputs required.')
    check_hashes(original)
    verifier = module(VERIFIER, 'representative_functional_verifier')
    lanes = read(FUNCTIONAL / 'lanes.json')
    reviewed = verifier.review(lanes, FUNCTIONAL)
    require(reviewed['passed'] and reviewed['processes'] == 12 and reviewed['collections'] == 60 and
            reviewed['negativeControls'] == 90 and reviewed['dispatchCounts'] == COUNTS,
            'Accepted functional controls/counts differ.')
    saved = read(FUNCTIONAL / 'results.json')
    require(all(saved[key] == value for key, value in reviewed.items()), 'Functional summary differs.')
    extras = list(FUNCTIONAL_PINS) + [FUNCTIONAL / 'lanes.json']
    for lane in lanes:
        extras.extend(FUNCTIONAL / lane[key] for key in ('command', 'stdout', 'stderr'))
    return original, hashes(extras), lanes


def build_identity(kind):
    build = ROOT / 'artifacts' / kind / 'windows-release-build-20261014-attempt1'
    runtime = Path('E:/runtime-' + kind + '-20261014')
    checker = ROOT / ('eng/' + kind + '-runtime-candidate.py')
    commit = PARENT if kind == 'phase-load' else CHILD
    candidate = module(checker, 'representative_' + kind.replace('-', '_')).validate(runtime, commit)
    request, result, layout = (read(build / name) for name in ('request.json', 'build-result.json', 'layout-receipt.json'))
    for value in (request, result, layout):
        require(value['candidateCommit'] == commit and value['candidateValidation'] == candidate and
                value['candidateCheckerSha256'] == sha(checker) and value['configuration'] == 'Release',
                'Native build candidate/configuration binding differs: ' + kind)
    require(layout['passed'] and result['exitCode'] == 0 and layout['upstreamBase'] == UPSTREAM and
            request['upstreamBase'] == UPSTREAM and
            result['requestSha256'] == layout['buildRequestSha256'] == sha(build / 'request.json') and
            layout['buildResultSha256'] == sha(build / 'build-result.json'), 'Successful native receipt chain differs.')
    require(request['sourceHashes'] == result['sourceHashes'] and len(request['sourceHashes']) == 36,
            'Complete 36-file built-source inventory required.')
    product = runtime / 'artifacts/bin/coreclr/windows.x64.Release'
    cache = runtime / 'artifacts/obj/coreclr/windows.x64.Release/CMakeCache.txt'
    require(result['cmakeFeatures'] == FEATURES and result['cmakeCacheSha256'] == sha(cache),
            'Native Release interpreter feature/cache identity differs.')
    metadata = [build / name for name in ('request.json', 'build-result.json', 'layout-receipt.json',
                 'native-commands.txt', 'build.stdout', 'build.stderr', checker.name)] + [checker, cache]
    require(result['nativeCommandsSha256'] == sha(build / 'native-commands.txt') and
            result['stdoutSha256'] == sha(build / 'build.stdout') and result['stderrSha256'] == sha(build / 'build.stderr') and
            sha(build / checker.name) == sha(checker), 'Native build raw/checker identity differs.')
    inputs = hashes(metadata)
    for name, expected in request['sourceHashes'].items():
        for path in (runtime / name, build / 'source' / name):
            require(sha(path) == expected, 'Actual built-source bytes differ: ' + str(path))
            inputs[str(path.resolve())] = expected
    for name, expected in result['criticalProductHashes'].items():
        require(sha(product / name) == expected and layout['criticalProductHashes'][name] == expected,
                'Native/CoreLib/compiler product differs: ' + name)
        inputs[str((product / name).resolve())] = expected
    require(len(result['criticalProductHashes']) == 8, 'Eight critical native/CoreLib/compiler products required.')
    for name, expected in layout['allLayoutHashes'].items():
        path = build / 'layout' / name
        require(sha(path) == expected, 'Accepted native layout changed: ' + name)
        inputs[str(path.resolve())] = expected
    require(Path(layout['runtime']).resolve() == runtime.resolve() and
            Path(layout['product']).resolve() == product.resolve() and
            Path(layout['layout']).resolve() == (build / 'layout').resolve(), 'Native layout/source/product paths differ.')
    for name in ('coreclr.dll', 'clrjit.dll', 'clrinterpreter.dll', 'System.Private.CoreLib.dll'):
        require(sha(build / 'layout/shared/Microsoft.NETCore.App/12.0.0' / name) == result['criticalProductHashes'][name],
                'Loaded native/CoreLib layout differs from actual product: ' + name)
    require([item['name'] for item in layout['nativeStamps']] == ['coreclr.dll', 'clrjit.dll', 'clrinterpreter.dll'] and
            all('@Commit: ' + commit in item['stamp'] for item in layout['nativeStamps']), 'Accepted native source stamps differ.')
    return {'commit': commit, 'upstreamBase': UPSTREAM, 'runtime': str(runtime.resolve()),
            'layout': str((build / 'layout').resolve()), 'buildEvidence': str(build.resolve()),
            'candidateValidation': candidate, 'checkerSha256': sha(checker), 'cmakeFeatures': FEATURES,
            'receiptHashes': hashes(build / name for name in ('request.json', 'build-result.json', 'layout-receipt.json')),
            'sourceHashes': request['sourceHashes'], 'criticalProductHashes': result['criticalProductHashes'],
            'allLayoutHashes': layout['allLayoutHashes'], 'boundInputHashes': inputs}


def expected_contract():
    original, extras, _ = functional_inputs()
    bindings = {kind: build_identity(kind) for kind in ('phase-load', 'derived-ledger')}
    inputs = dict(original) | extras | hashes([Path(__file__).resolve()])
    for binding in bindings.values():
        for path, expected in binding['boundInputHashes'].items():
            require(path not in inputs or inputs[path] == expected, 'Input bindings disagree: ' + path)
            inputs[path] = expected
    return original, bindings, inputs


def parameters():
    return {'labels': list(LABELS), 'workloads': list(WORKLOADS), 'modes': list(MODES),
            'pairedRounds': 4, 'samples': 9, 'warmups': 3, 'affinityMask': 4,
            'executionLimit': LIMIT, 'cleanupLimit': 4096, 'expectedProcesses': 64,
            'expectedCollections': 832, 'configuration': 'Release', 'platform': 'windows.x64',
            'counts': COUNTS, 'baseline': BASELINE, 'callbackScope': CALLBACK_SCOPE, 'sessionScope': SESSION_SCOPE}


def launch(preparation, lane):
    kind = 'derived-ledger' if lane['profile'] in ('off', 'on') else 'phase-load'
    layout = Path(preparation['buildBindings'][kind]['layout'])
    directory = Path(preparation['directory'])
    argv = [str(layout / 'dotnet.exe'), 'exec', '--fx-version', '12.0.0',
            str(directory / 'host/RuneCLR.BudgetWorkloads.dll'),
            str(directory / 'author/RuneCLR.BudgetWorkloadScripts.dll'),
            lane['mode'], lane['workload'], lane['nonce'], '9']
    settings = {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0',
                'DOTNET_ReadyToRun': '1', 'DOTNET_TieredCompilation': '0', 'DOTNET_MULTILEVEL_LOOKUP': '0',
                'DOTNET_RuneCLRPhaseAcquireLoad': '1', 'DOTNET_RuneCLRDerivedLedger': '1' if lane['profile'] == 'on' else '0'}
    return argv, settings


def order():
    return [(profile, workload, pair, position, mode) for profile in LABELS for workload in WORKLOADS
            for pair in range(4) for position, mode in enumerate(MODES if pair % 2 == 0 else tuple(reversed(MODES)))]


def validate_contract(value, directory, original, bindings, inputs):
    require(value['schema'] == 'runeclr.representative-budget.performance-preparation.v1' and value['passed'] and
            value['directory'] == str(directory) and value['measurementOutput'] == str(directory / 'measurement'),
            'Preparation directory/schema differs.')
    require(value['parameters'] == parameters() and value['buildBindings'] == bindings and
            value['originalFunctionalInputs'] == original and value['boundInputHashes'] == inputs,
            'Exact parameters/native/source/function input contract differs.')
    require(value['functionalDirectory'] == str(FUNCTIONAL) and value['functionalPins'] ==
            {str(path): expected for path, expected in FUNCTIONAL_PINS.items()}, 'Functional identity differs.')
    require(value['driverSha256'] == sha(__file__) and not value['timingPerformed'] and not value['buildPerformed'],
            'Preparation driver/scope differs.')
    expected_snapshots = {'inputs/' + str(i) + '/' + Path(name).name: expected
                          for i, (name, expected) in enumerate(sorted(inputs.items()))}
    require(value['snapshotHashes'] == expected_snapshots, 'Complete input snapshot inventory differs.')
    managed = {subdir + '/' + path.name: inputs[str(path.resolve())] for subdir in ('host', 'author')
               for path in (FUNCTIONAL / subdir).iterdir() if path.is_file()}
    require(value['managedHashes'] == managed and
            managed['host/RuneCLR.Abstractions.dll'] == managed['author/RuneCLR.Abstractions.dll'] and
            'host/RuneCLR.BudgetWorkloadScripts.dll' not in managed, 'Byte-identical isolated host/author inventory differs.')
    plan = value['plan']
    require([(x['profile'], x['workload'], x['pair'], x['position'], x['mode']) for x in plan] == order() and
            len({x['nonce'] for x in plan}) == 64 and
            all(len(x['nonce']) == 32 and all(c in '0123456789abcdef' for c in x['nonce']) for x in plan),
            'Four brackets/four alternating pairs/unique nonce plan differs.')
    for number, lane in enumerate(plan):
        require(lane['index'] == number and lane['label'] == str(number).zfill(2) + '-' + lane['profile'] + '-' +
                lane['workload'] + '-pair-' + str(lane['pair']) + '-' + lane['mode'] + '-' + lane['nonce'] and
                (lane['argv'], lane['settings']) == launch(value, lane), 'Planned launch identity differs.')
    require(value['machine']['os'] == platform.platform() and value['machine']['node'] == platform.node() and
            value['machine']['architecture'] == platform.machine(), 'Preparation machine differs.')


def validate_preparation(directory, value=None):
    directory = Path(directory).resolve()
    value = read(directory / 'preparation.json') if value is None else value
    original, bindings, inputs = expected_contract()
    validate_contract(value, directory, original, bindings, inputs)
    check_hashes(inputs)
    check_hashes({str(directory / relative): expected for relative, expected in value['snapshotHashes'].items()})
    check_hashes({str(directory / relative): expected for relative, expected in value['managedHashes'].items()})
    actual = {subdir + '/' + path.name for subdir in ('host', 'author')
              for path in (directory / subdir).iterdir() if path.is_file()}
    require(actual == set(value['managedHashes']), 'Prepared managed files added/omitted.')
    return value


def prepare(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    original, bindings, inputs = expected_contract()
    snapshots = {}
    for number, (name, expected) in enumerate(sorted(inputs.items())):
        relative = 'inputs/' + str(number) + '/' + Path(name).name
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(name, target)
        require(sha(target) == expected, 'Frozen input copy differs.')
        snapshots[relative] = expected
    managed = {}
    for subdir in ('host', 'author'):
        (directory / subdir).mkdir()
        for path in (FUNCTIONAL / subdir).iterdir():
            if path.is_file():
                target = directory / subdir / path.name
                shutil.copyfile(path, target)
                managed[subdir + '/' + path.name] = sha(target)
    value = {'schema': 'runeclr.representative-budget.performance-preparation.v1', 'passed': True,
             'createdUtc': datetime.now(timezone.utc).isoformat(), 'directory': str(directory),
             'measurementOutput': str(directory / 'measurement'), 'driverSha256': sha(__file__),
             'functionalDirectory': str(FUNCTIONAL), 'functionalPins': {str(p): h for p, h in FUNCTIONAL_PINS.items()},
             'parameters': parameters(), 'originalFunctionalInputs': original, 'buildBindings': bindings,
             'boundInputHashes': inputs, 'snapshotHashes': snapshots, 'managedHashes': managed,
             'machine': {'os': platform.platform(), 'node': platform.node(), 'architecture': platform.machine()},
             'plan': [], 'timingPerformed': False, 'buildPerformed': False,
             'scope': 'Exact input/launch preparation only. Timing requires a separate explicit run after owned builds/debuggers/audits are idle.'}
    for number, (profile, workload, pair, position, mode) in enumerate(order()):
        nonce = uuid.uuid4().hex
        lane = {'index': number, 'profile': profile, 'workload': workload, 'pair': pair,
                'position': position, 'mode': mode, 'nonce': nonce,
                'label': str(number).zfill(2) + '-' + profile + '-' + workload + '-pair-' + str(pair) + '-' + mode + '-' + nonce}
        lane['argv'], lane['settings'] = launch(value, lane)
        value['plan'].append(lane)
    save(directory / 'preparation.json', value)
    validate_preparation(directory)
    print(json.dumps({'passed': True, 'functionalInputs': len(original), 'boundInputs': len(inputs),
                      'preparedProcesses': 64, 'managedFiles': len(managed), 'timingPerformed': False, 'buildPerformed': False}))


def valid_time(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def snapshot(value, executed):
    require(value == {'ExecutionRemaining': LIMIT - executed, 'ExecutionExecuted': executed,
                     'ExecutionExhausted': False, 'IsTerminated': False, 'Reason': 0, 'Phase': 0,
                     'CleanupRemaining': 4096, 'CleanupExecuted': 0}, 'Exact admitted ledger/conservation differs.')


def validate_lane(lane, planned, preparation):
    require({k: lane[k] for k in planned} == planned, 'Observed lane differs from frozen plan.')
    receipt, raw = lane['receipt'], lane['raw']
    require(raw['argv'] == planned['argv'] and raw['settings'] == planned['settings'] and raw['exitCode'] == 0 and
            raw['pid'] > 0 and not raw['timedOut'] and valid_time(raw['wallSeconds']), 'Actual launch/process identity differs.')
    workload, mode = planned['workload'], planned['mode']
    require(receipt['passed'] and receipt['processId'] == raw['pid'] and receipt['nonce'] == planned['nonce'] and
            receipt['workload'] == workload and receipt['mode'] == mode and receipt['affinity'] == 4 and
            receipt['architecture'] == 'X64' and receipt['runtime'].startswith('.NET 12.') and
            receipt['warmups'] == 3 and receipt['sampleCount'] == 9 and receipt['entityCount'] == 512 and
            receipt['iterations'] == (200 if workload == 'entities' else 8192) and receipt['cleanupLimit'] == 4096,
            'Receipt workload/runtime/CPU/sample identity differs.')
    require(receipt['directCollected'] and receipt['sessionCollected'] == 12 and len(receipt['Callbacks']) == 9 and
            len(receipt['Samples']) == 12 and [s['Warmup'] for s in receipt['Samples']] == [True]*3 + [False]*9 and
            len(receipt['WarmupMilliseconds']) == 3 and valid_time(receipt['SetupMilliseconds']) and
            all(valid_time(t) for t in receipt['WarmupMilliseconds']), 'Samples, setup/warmup durations or collections differ.')
    author = ('Entities', 'EntitiesObjects') if workload == 'entities' else ('HostApi', 'HostApi')
    require([p['Method'] for p in receipt['Proof']] == ['RuneCLR.BudgetWorkloadScripts.WorkloadEntries.' + author[0],
            'RuneCLR.Performance.Workloads.' + author[1]] and
            all(p['Interpreted'] and p['StubType'] == 6 for p in receipt['Proof']), 'Selected interpreted author entries differ.')
    require(receipt['hostProof']['Method'] == 'RuneCLR.Runtime.MapRunner.Run' and not receipt['hostProof']['Interpreted'] and
            [p['Method'] for p in receipt['trustedAdapterProof']] == ['BenchmarkMapContext.SpawnEntity', 'BenchmarkMapContext.DestroyEntity'] and
            all(not p['Interpreted'] for p in receipt['trustedAdapterProof']), 'Trusted entry controls differ.')
    require(receipt['callbackScope'] == 'fresh trusted adapter, author entry and helper, adapter verification; excludes ALC setup/collection' and
            receipt['sessionScope'] == 'fresh MapRunner session with three ticks and retirement; excludes diagnostic collection' and
            receipt['baseline'] == 'same instrumented runtime; no-config retains definition-owner lookup and null-meter branch; not compile-time instrumentation-off',
            'Actual timer scopes or baseline differ.')
    oracle = module(VERIFIER, 'representative_checksum_oracle').oracle
    delta = COUNTS[workload]['callback']
    for number, callback in enumerate(receipt['Callbacks']):
        require(callback['Checksum'] == oracle(workload) and valid_time(callback['Milliseconds']) and
                callback['AllocatedBytes'] >= 0 and len(callback['GcCounts']) == 3 and
                all(type(n) is int and n >= 0 for n in callback['GcCounts']), 'Callback oracle/time/allocation/GC differs.')
        if mode == 'high-budget':
            require(callback['DispatchDelta'] == delta and callback['ExecutedBefore'] == (3 + number)*delta and
                    callback['ExecutedAfter'] == (4 + number)*delta, 'Exact callback admitted recurrence differs.')
        else:
            require(all(callback[key] is None for key in ('DispatchDelta', 'ExecutedBefore', 'ExecutedAfter')), 'No-config callback reports a meter.')
    resources = 24576 if workload == 'host-api' else 0
    logs = (['benchmark-tick']*384 if resources else []) + ['budget-workloads:' + workload + ':starts=1;sum=' + str(oracle(workload, 3))]
    for sample in receipt['Samples']:
        require(sample['Checksum'] == oracle(workload, 3) and valid_time(sample['Milliseconds']) and
                sample['CompletedTicks'] == 3 and sample['CreatedEntities'] == sample['ReleasedEntities'] == resources and
                sample['RemainingEntities'] == 0 and sample['Logs'] == logs, 'Session oracle/static/resource/time observations differ.')
        if mode == 'high-budget':
            snapshot(sample['Budget'], COUNTS[workload]['session'])
        else:
            require(sample['Budget'] is None, 'No-config session reports a meter.')
    if mode == 'high-budget':
        require(receipt['budgetLimit'] == LIMIT, 'Configured budget limit differs.')
        snapshot(receipt['FinalSnapshot'], 12*delta)
    else:
        require(receipt['budgetLimit'] is None and receipt['FinalSnapshot'] is None, 'No-config final meter unexpectedly present.')


def summaries(lanes):
    pooled, paired = {}, []
    for profile in LABELS:
        pooled[profile] = {}
        for workload in WORKLOADS:
            pooled[profile][workload] = {}
            for mode in MODES:
                selected = [lane['receipt'] for lane in lanes if lane['profile'] == profile and lane['workload'] == workload and lane['mode'] == mode]
                callbacks = [s['Milliseconds'] for r in selected for s in r['Callbacks']]
                sessions = [s['Milliseconds'] for r in selected for s in r['Samples'] if not s['Warmup']]
                require(len(selected) == 4 and len(callbacks) == len(sessions) == 36, 'Four processes/36 samples per workload/mode/profile required.')
                pooled[profile][workload][mode] = {'processes': 4, 'callbackSamples': 36, 'sessionSamples': 36,
                    'callbackMedianMs': statistics.median(callbacks), 'sessionMedianMs': statistics.median(sessions),
                    'callbackMinMs': min(callbacks), 'callbackMaxMs': max(callbacks),
                    'sessionMinMs': min(sessions), 'sessionMaxMs': max(sessions)}
            for pair in range(4):
                pair_lanes = {x['mode']: x['receipt'] for x in lanes if x['profile'] == profile and x['workload'] == workload and x['pair'] == pair}
                medians = {mode: {'callback': statistics.median(x['Milliseconds'] for x in r['Callbacks']),
                                  'session': statistics.median(x['Milliseconds'] for x in r['Samples'] if not x['Warmup'])} for mode, r in pair_lanes.items()}
                paired.append({'profile': profile, 'workload': workload, 'pair': pair, 'mediansMs': medians,
                    'configuredRatio': {scope: medians['high-budget'][scope] / medians['no-config'][scope] for scope in ('callback', 'session')}})
    configured, reduction, drift = {}, {}, {}
    for workload in WORKLOADS:
        configured[workload] = {profile: {scope: pooled[profile][workload]['high-budget'][scope+'MedianMs'] /
                                                pooled[profile][workload]['no-config'][scope+'MedianMs'] for scope in ('callback', 'session')} for profile in LABELS}
        reduction[workload] = {profile: {scope: 100*(1-pooled['on'][workload]['high-budget'][scope+'MedianMs'] /
                                                       pooled[profile][workload]['high-budget'][scope+'MedianMs']) for scope in ('callback', 'session')}
                              for profile in ('parent-before', 'off', 'parent-after')}
        drift[workload] = {mode: {scope: 100*(pooled['parent-after'][workload][mode][scope+'MedianMs'] /
                                            pooled['parent-before'][workload][mode][scope+'MedianMs']-1) for scope in ('callback', 'session')} for mode in MODES}
    return {'pooled': pooled, 'pairedRounds': paired, 'configuredRatios': configured,
            'onConfiguredTimeReductionPercent': reduction, 'parentAfterIncreasePercent': drift}


def validate_set(lanes, preparation):
    require(len(lanes) == 64 and len({x['raw']['pid'] for x in lanes}) == 64 and
            len({x['nonce'] for x in lanes}) == 64, '64 independent owned processes/nonces required.')
    for lane, planned in zip(lanes, preparation['plan']):
        validate_lane(lane, planned, preparation)
    return summaries(lanes)


def check_raw(lane, directory):
    for stream in ('stdout', 'stderr', 'command'):
        require(lane[stream] == lane['label'] + ('.command.json' if stream == 'command' else '.' + stream) and
                sha(directory / lane[stream]) == lane[stream+'Sha256'], 'Raw stream/command hash or path differs.')
    require(read(directory / lane['command']) == lane['raw'] and read(directory / lane['stdout']) == lane['receipt'],
            'Raw command/stdout differs from stored process/receipt.')
    require(lane['raw']['stdoutSha256'] == lane['stdoutSha256'] and lane['raw']['stderrSha256'] == lane['stderrSha256'],
            'Original process raw hashes differ.')


def observed_result(lanes, preparation, request_hash):
    return {'schema': 'runeclr.representative-budget.performance-result.v1', 'passed': True,
            'requestSha256': request_hash, 'processes': 64, 'contextsCollected': 832,
            'parameters': parameters(), 'summaries': validate_set(lanes, preparation),
            'lanes': lanes, 'performanceMeasured': True, 'mobileVerified': False,
            'limits': 'One Windows x64 machine; two selected author workloads, exact configured-meter incremental cost. No compile-time instrumentation-off baseline, batching, complete invocation trace or mobile/game acceptance.'}


def command(lane, directory):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_'))}
    env.update(lane['settings'])
    started = time.monotonic()
    process = subprocess.Popen(lane['argv'], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=180)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate()
    stdout_path, stderr_path = directory / (lane['label']+'.stdout'), directory / (lane['label']+'.stderr')
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    raw = {'argv': lane['argv'], 'settings': lane['settings'], 'pid': process.pid, 'exitCode': process.returncode,
           'timedOut': timed_out, 'wallSeconds': time.monotonic()-started,
           'stdoutSha256': sha(stdout_path), 'stderrSha256': sha(stderr_path)}
    command_path = directory / (lane['label']+'.command.json')
    save(command_path, raw)
    require(not timed_out and process.returncode == 0, 'Owned process failed; raw evidence preserved: ' + lane['label'])
    return dict(lane) | {'raw': raw, 'receipt': read(stdout_path), 'stdout': stdout_path.name,
                        'stderr': stderr_path.name, 'command': command_path.name,
                        'stdoutSha256': sha(stdout_path), 'stderrSha256': sha(stderr_path), 'commandSha256': sha(command_path)}


def validate_selftest(directory, report=None):
    report = read(directory / 'selftest.json') if report is None else report
    controls = report['negativeControls']
    require(report['schema'] == 'runeclr.representative-budget.performance-selftest.v1' and report['passed'] and
            report['preparationSha256'] == sha(directory / 'preparation.json') and report['driverSha256'] == sha(__file__) and
            report['syntheticValidationOnly'] and report['syntheticLanesValidated'] == 64 and
            not report['timingPerformed'] and not report['authorExecuted'] and not report['buildPerformed'] and
            len(controls) >= 38 and len({x['name'] for x in controls}) == len(controls) and all(x['rejected'] for x in controls),
            'Matching preparation/driver/synthetic selftest required.')
    return report


def run(preparation_directory, output):
    preparation_directory = Path(preparation_directory).resolve()
    preparation = validate_preparation(preparation_directory)
    validate_selftest(preparation_directory)
    output = Path(output).resolve()
    require(str(output) == preparation['measurementOutput'], 'Output must match frozen measurement path.')
    output.mkdir(parents=True, exist_ok=False)
    request = {'schema': 'runeclr.representative-budget.performance-request.v1',
               'preparationSha256': sha(preparation_directory / 'preparation.json'),
               'preparationDirectory': str(preparation_directory), 'selftestSha256': sha(preparation_directory / 'selftest.json'),
               'driverSha256': sha(__file__), 'parameters': parameters(), 'machine': preparation['machine'],
               'plan': preparation['plan'], 'timingPerformed': True, 'managedRebuilt': False,
               'scope': 'Explicit timing run; caller must arrange idle owned builds/debuggers/audits.'}
    save(output / 'request.json', request)
    request_hash = sha(output / 'request.json')
    lanes = []
    for planned in preparation['plan']:
        validate_preparation(preparation_directory)
        validate_selftest(preparation_directory)
        require(sha(preparation_directory / 'selftest.json') == request['selftestSha256'], 'Selftest changed during run.')
        require(sha(output / 'request.json') == request_hash, 'Run request changed.')
        lane = command(planned, output)
        check_raw(lane, output)
        validate_lane(lane, planned, preparation)
        lanes.append(lane)
        save(output / ('partial-' + str(len(lanes)).zfill(2) + '.json'), {'passed': False, 'lanes': lanes})
        print(planned['label'] + ': passed', flush=True)
    validate_preparation(preparation_directory)
    result = observed_result(lanes, preparation, request_hash)
    save(output / 'results.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'lanes'}, indent=2))


def review(preparation_directory, directory):
    preparation_directory, directory = Path(preparation_directory).resolve(), Path(directory).resolve()
    preparation = validate_preparation(preparation_directory)
    validate_selftest(preparation_directory)
    require(str(directory) == preparation['measurementOutput'], 'Review measurement path differs.')
    request, result = read(directory / 'request.json'), read(directory / 'results.json')
    require(request['schema'] == 'runeclr.representative-budget.performance-request.v1' and
            request['preparationSha256'] == sha(preparation_directory / 'preparation.json') and
            request['selftestSha256'] == sha(preparation_directory / 'selftest.json') and
            request['preparationDirectory'] == str(preparation_directory) and request['driverSha256'] == sha(__file__) and
            request['parameters'] == parameters() and request['machine'] == preparation['machine'] and
            request['plan'] == preparation['plan'] and request['timingPerformed'] and not request['managedRebuilt'],
            'Run request/preparation/managed/source bindings differ.')
    for lane in result['lanes']:
        check_raw(lane, directory)
    expected = observed_result(result['lanes'], preparation, sha(directory / 'request.json'))
    require(result == expected, 'Result/summary/paired ratios differ from raw observations.')
    print(json.dumps({'passed': True, 'processes': 64, 'contextsCollected': 832,
                      'resultSha256': sha(directory / 'results.json'), 'performanceMeasured': True,
                      'summaries': expected['summaries']}, indent=2))


def selftest(directory):
    directory = Path(directory).resolve()
    preparation = validate_preparation(directory)
    original, bindings, inputs = expected_contract()
    controls = []

    def rejected(name, action):
        try:
            action()
        except (RuntimeError, ValueError, KeyError) as error:
            controls.append({'name': name, 'rejected': True, 'reason': str(error)})
        else:
            raise RuntimeError('Corruption accepted: ' + name)

    for name, edit in (
        ('bad-native-commit', lambda x: x['buildBindings']['derived-ledger'].__setitem__('commit', PARENT)),
        ('bad-native-layout', lambda x: x['buildBindings']['derived-ledger'].__setitem__('layout', str(ROOT))),
        ('bad-native-feature', lambda x: x['buildBindings']['phase-load']['cmakeFeatures'].__setitem__('FEATURE_INTERPRETER', '0')),
        ('bad-native-product', lambda x: x['buildBindings']['derived-ledger']['criticalProductHashes'].__setitem__('coreclr.dll', '0'*64)),
        ('bad-built-source', lambda x: x['buildBindings']['derived-ledger']['sourceHashes'].__setitem__('src/coreclr/vm/runeclrinstructionmeter.h', '0'*64)),
        ('bad-receipt-chain', lambda x: x['buildBindings']['phase-load']['receiptHashes'].__setitem__(str(ROOT), '0'*64)),
        ('bad-switch', lambda x: x['plan'][0]['settings'].__setitem__('DOTNET_RuneCLRPhaseAcquireLoad', '0')),
        ('bad-launch-layout', lambda x: x['plan'][0]['argv'].__setitem__(0, x['plan'][32]['argv'][0])),
        ('bad-sample-argument', lambda x: x['plan'][0]['argv'].__setitem__(-1, '1')),
        ('bad-pair-count', lambda x: x['parameters'].__setitem__('pairedRounds', 1)),
        ('bad-affinity', lambda x: x['parameters'].__setitem__('affinityMask', 1)),
        ('bad-scope', lambda x: x['parameters'].__setitem__('callbackScope', 'author only')),
        ('bad-count-oracle', lambda x: x['parameters']['counts']['entities'].__setitem__('callback', 1)),
        ('missing-original-input', lambda x: x['originalFunctionalInputs'].pop(next(iter(x['originalFunctionalInputs'])))),
        ('changed-bound-input', lambda x: x['boundInputHashes'].__setitem__(next(iter(x['boundInputHashes'])), '0'*64)),
        ('missing-snapshot', lambda x: x['snapshotHashes'].pop(next(iter(x['snapshotHashes'])))),
        ('changed-managed-image', lambda x: x['managedHashes'].__setitem__('host/RuneCLR.BudgetWorkloads.dll', '0'*64)),
        ('duplicate-plan-nonce', lambda x: x['plan'][1].__setitem__('nonce', x['plan'][0]['nonce'])),
        ('bracket-order', lambda x: x['plan'].reverse()),
    ):
        changed = copy.deepcopy(preparation)
        edit(changed)
        rejected(name, lambda x=changed: validate_contract(x, directory, original, bindings, inputs))
    functional_lanes = read(FUNCTIONAL / 'lanes.json')
    synthetic = []
    for plan in preparation['plan']:
        profile = 'parent' if plan['profile'].startswith('parent') else plan['profile']
        receipt = copy.deepcopy(next(x['receipt'] for x in functional_lanes if (x['profile'], x['workload'], x['mode']) ==
                                    (profile, plan['workload'], plan['mode'])))
        receipt.update(processId=plan['index']+10000, nonce=plan['nonce'], sampleCount=9)
        callback = receipt['Callbacks'][0]
        receipt['Callbacks'] = [copy.deepcopy(callback) for _ in range(9)]
        if plan['mode'] == 'high-budget':
            delta = COUNTS[plan['workload']]['callback']
            for number, item in enumerate(receipt['Callbacks']):
                item.update(ExecutedBefore=(3+number)*delta, ExecutedAfter=(4+number)*delta)
            receipt['FinalSnapshot']['ExecutionExecuted'] = 12*delta
            receipt['FinalSnapshot']['ExecutionRemaining'] = LIMIT-12*delta
        receipt['Samples'] += [copy.deepcopy(receipt['Samples'][-1]) for _ in range(8)]
        for item in receipt['Callbacks'] + receipt['Samples']:
            item['Milliseconds'] = 1.0
        receipt.update(sessionCollected=12, SetupMilliseconds=1.0, WarmupMilliseconds=[1.0]*3)
        synthetic.append(dict(plan) | {'receipt': receipt, 'raw': {'argv': plan['argv'], 'settings': plan['settings'],
                         'pid': receipt['processId'], 'exitCode': 0, 'timedOut': False, 'wallSeconds': 1.0}})
    validate_set(synthetic, preparation)
    configured = next(x for x in synthetic if x['mode'] == 'high-budget')
    planned = preparation['plan'][configured['index']]
    for name, edit in (
        ('wrong-runtime', lambda x: x['raw']['argv'].__setitem__(0, str(ROOT/'wrong/dotnet.exe'))),
        ('wrong-derived-switch', lambda x: x['raw']['settings'].__setitem__('DOTNET_RuneCLRDerivedLedger', '1')),
        ('wrong-phase-switch', lambda x: x['raw']['settings'].__setitem__('DOTNET_RuneCLRPhaseAcquireLoad', '0')),
        ('wrong-pid', lambda x: x['raw'].__setitem__('pid', 1)),
        ('wrong-nonce', lambda x: x['receipt'].__setitem__('nonce', '0'*32)),
        ('wrong-dispatch-count', lambda x: x['receipt']['Callbacks'][0].__setitem__('DispatchDelta', 1)),
        ('wrong-session-count', lambda x: x['receipt']['Samples'][0]['Budget'].__setitem__('ExecutionExecuted', 1)),
        ('wrong-ledger', lambda x: x['receipt']['FinalSnapshot'].__setitem__('ExecutionRemaining', 0)),
        ('wrong-checksum', lambda x: x['receipt']['Callbacks'][0].__setitem__('Checksum', 0)),
        ('wrong-resources', lambda x: x['receipt']['Samples'][0].__setitem__('ReleasedEntities', -1)),
        ('wrong-static-reset', lambda x: x['receipt']['Samples'][0]['Logs'].__setitem__(-1, 'starts=2')),
        ('missing-collection', lambda x: x['receipt'].__setitem__('directCollected', False)),
        ('wrong-author-entry', lambda x: x['receipt']['Proof'][0].__setitem__('Interpreted', False)),
        ('wrong-trusted-entry', lambda x: x['receipt']['hostProof'].__setitem__('Interpreted', True)),
        ('wrong-sample-count', lambda x: x['receipt']['Callbacks'].pop()),
        ('nonfinite-duration', lambda x: x['receipt']['Callbacks'][0].__setitem__('Milliseconds', float('nan'))),
    ):
        changed = copy.deepcopy(configured)
        edit(changed)
        rejected(name, lambda x=changed: validate_lane(x, planned, preparation))
    changed_raw = copy.deepcopy(functional_lanes[0])
    changed_raw['label'] = changed_raw['stdout'].removesuffix('.stdout')
    changed_raw['stdoutSha256'] = '0'*64
    rejected('raw-hash', lambda: check_raw(changed_raw, FUNCTIONAL))
    changed = copy.deepcopy(synthetic)
    changed[1]['raw']['pid'] = changed[0]['raw']['pid']
    rejected('duplicate-process', lambda: validate_set(changed, preparation))
    changed = copy.deepcopy(synthetic)
    changed[0], changed[16] = changed[16], changed[0]
    rejected('wrong-observed-bracket', lambda: validate_set(changed, preparation))
    ast.parse(Path(__file__).read_text(), filename=__file__)
    report = {'schema': 'runeclr.representative-budget.performance-selftest.v1',
         'passed': True, 'preparationSha256': sha(directory/'preparation.json'),
         'driverSha256': sha(__file__), 'negativeControls': controls, 'syntheticValidationOnly': True,
         'syntheticLanesValidated': 64, 'timingPerformed': False, 'authorExecuted': False, 'buildPerformed': False,
         'scope': 'Corruption tests use in-memory nine-sample receipts expanded from accepted functional smoke; synthetic durations are not measurements.'}
    validate_selftest(directory, report)
    for name, key in (('selftest-preparation-substitution', 'preparationSha256'), ('selftest-driver-substitution', 'driverSha256')):
        altered = copy.deepcopy(report)
        altered[key] = '0'*64
        rejected(name, lambda value=altered: validate_selftest(directory, value))
    validate_selftest(directory, report)
    save(directory / 'selftest.json', report)
    print(json.dumps({'passed': True, 'negativeControls': len(controls), 'syntheticLanesValidated': 64,
                      'timingPerformed': False, 'authorExecuted': False, 'buildPerformed': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='mode', required=True)
    prep = actions.add_parser('prepare')
    prep.add_argument('--output', type=Path, required=True)
    for mode in ('run', 'review'):
        action = actions.add_parser(mode)
        action.add_argument('--preparation', type=Path, required=True)
        action.add_argument('--output', type=Path, required=True)
    test = actions.add_parser('selftest')
    test.add_argument('--preparation', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.output)
    elif args.mode == 'selftest':
        selftest(args.preparation)
    elif args.mode == 'run':
        run(args.preparation, args.output)
    else:
        review(args.preparation, args.output)


if __name__ == '__main__':
    main()
