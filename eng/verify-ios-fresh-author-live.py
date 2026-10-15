#!/usr/bin/env python3
"""Synthetic acceptance controls; this script never launches a target or simulator."""
import argparse
from contextlib import redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
CASES = ('Normal', 'EndlessTick', 'StartLoop', 'CatchResume', 'BroadCatchResume',
         'SignalFilter', 'FilterExhaustion', 'ConstructorLoop', 'StaticConstructorLoop',
         'FiniteCleanup', 'InfiniteCleanup', 'StopLoop', 'MaliciousMessage',
         'ExplicitCanceled', 'Recovery')
TERM = 'The native prototype instruction budget terminated author execution.'
LOGS = {'EndlessTick': ['start', 'tick-before'], 'StartLoop': ['start'],
        'CatchResume': ['start'], 'BroadCatchResume': ['start'], 'SignalFilter': ['start'],
        'FilterExhaustion': ['start', 'filter-before'], 'ConstructorLoop': [],
        'StaticConstructorLoop': [],
        'FiniteCleanup': ['start', 'finally', 'private-finally', 'private-delegate'],
        'InfiniteCleanup': ['start', 'private-infinite-finally'],
        'StopLoop': ['start', 'tick=0', 'tick=1', 'tick=2', 'stop-before'],
        'MaliciousMessage': ['start', 'stop'], 'ExplicitCanceled': ['start', 'stop']}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='ascii')


def row(scenario, index):
    typ = ('Normal' if index % 2 else 'CatchResume') if scenario == 'Recovery' else scenario
    normal = typ == 'Normal'
    active = typ in ('Normal', 'MaliciousMessage', 'ExplicitCanceled')
    execution = 100 if active else 8192
    cleanup = 4096 if typ == 'InfiniteCleanup' else 100 if typ == 'FiniteCleanup' else 0
    error = (None if normal else 'HostBudgetUGC.BadMessage' if typ == 'MaliciousMessage'
             else 'System.OperationCanceledException' if typ == 'ExplicitCanceled'
             else 'OnStop: ' + TERM + '; ' + TERM if typ == 'StopLoop' else TERM)
    entities = 0 if typ in ('ConstructorLoop', 'StaticConstructorLoop') else 1
    return {'session': index // 2 + 1 if scenario == 'Recovery' else index + 1,
            'role': ('good' if index % 2 else 'bad') if scenario == 'Recovery' else 'case',
            'collected': True, 'report': {
                'MapId': 'host-budget-' + typ, 'CreatedEntities': entities,
                'ReleasedEntities': entities, 'RemainingEntities': 0,
                'ExecutionPolicy': 1, 'ExecutionPolicyVersion': 1, 'Outcome': 0 if normal else 1,
                'CompletedTicks': 3 if typ in ('Normal', 'StopLoop') else 0,
                'Logs': ['start', 'static=1', 'tick=0', 'tick=1', 'tick=2', 'stop'] if normal else LOGS[typ],
                'Error': error, 'PrototypeBudget': {
                    'IsTerminated': not active, 'Reason': 0 if active else 1,
                    'ExecutionExhausted': not active,
                    'ExecutionRemaining': (1000000 if normal else 8192) - execution,
                    'ExecutionExecuted': execution, 'CleanupRemaining': 4096 - cleanup,
                    'CleanupExecuted': cleanup, 'Phase': 0 if active else 2 if typ == 'InfiniteCleanup' else 1}}}


def completion_fixture(dest, config):
    pid, nonce = config['pid'], config['nonce']
    adapter = {'passed': True, 'processId': pid, 'nonce': nonce, 'scenario': 'all',
               'contexts': 73, 'cases': []}
    for scenario in CASES:
        count = 20 if scenario == 'Normal' else 40 if scenario == 'Recovery' else 1
        derived = hashlib.sha256((nonce + ':' + scenario).encode()).hexdigest()[:32]
        child = {'passed': True, 'nonce': derived, 'scenario': scenario, 'mode': 'budget',
                 'rows': [row(scenario, i) for i in range(count)]}
        relative = scenario + '/result.json'
        write(dest / 'adapter-evidence' / relative, child)
        adapter['cases'].append({'scenario': scenario, 'nonce': derived, 'contexts': count,
                                 'receipt': relative,
                                 'receiptSha256': hashlib.sha256((dest / 'adapter-evidence' / relative).read_bytes()).hexdigest()})
    write(dest / 'adapter-evidence/result.json', adapter)
    (dest / 'lldb.stdout').write_text(f'Process {pid} exited with status = 0 (0x00000000)\n')
    lines = [f'FRESH_AUTHOR_SIM_NATIVE pid={pid} nonce={nonce} PhaseAcquireLoad=1 DerivedLedger=1 BatchInterval=0 InterpMode=0 InterpretCollectible=0 ReadyToRun=1',
             f'FRESH_AUTHOR_SIM_INITIALIZE pid={pid} nonce={nonce} hr=0',
             f'FRESH_AUTHOR_SIM_CREATE_DELEGATE pid={pid} nonce={nonce} hr=0',
             f'FRESH_AUTHOR_SIM_INVOKE pid={pid} nonce={nonce} managedExit=0',
             f'FRESH_AUTHOR_SIM_SHUTDOWN pid={pid} nonce={nonce} attempted=false reason=template-exit-path',
             f'FRESH_AUTHOR_SIM_EXIT pid={pid} nonce={nonce} managedExit=0 actualExit=0',
             f'MOBILE_HOST_BUDGET_COMPLETE nonce={nonce} scenario=all pid={pid} cases=15 contexts=73 passed=true']
    (dest / 'native.stdout').write_text('\n'.join(lines) + '\n')
    (dest / 'native.stderr').write_text('')


def capture_fixture(driver, dest):
    frozen = driver.v2()
    required = ['Payload.dll:Synthetic.Method' + str(i) for i in range(7)] + sorted(frozen.PRIVATE_PHASE1)
    paths = {kind: {'filePc': pc, 'prefixHex': str(i + 1) * 128,
                    'opcodeAddressAdvance': 8 if kind == 'delegate-child-dispatch' else 0}
             for i, (kind, pc) in enumerate(zip(frozen.PATH_KINDS, (2662540, 3046156, 3042808)))}
    config = {'pid': 1234, 'nonce': '1234567890abcdef' * 2, 'paths': paths,
              'nativeUuid': 'a' * 32, 'installedNative': '/owned/Session.app/libcoreclr.dylib',
              'layouts': {'InterpThreadContext': {'size': 88, 'fields': {'pStackPointer': 16, 'runeclrCleanupOwner': 80}}},
              'requiredMethods': required, 'methodPhases': frozen.method_phases(required),
              'gate': {'phase': 0}, 'authors': {}, 'hitCap': 100000}
    breakpoints = {'pid': config['pid'], 'nativeUuid': config['nativeUuid'],
                   'layoutsValidated': copy.deepcopy(config['layouts']), 'paths': {
                       kind: dict(contract, loadPc=contract['filePc'] + 0x100000000, locations=1)
                       for kind, contract in paths.items()}}
    entries = []
    for i, group in enumerate(required):
        name, method = group.split(':', 1)
        author = config['authors'].setdefault(name, {'path': '/owned/plugin/' + name,
                    'simpleName': name[:-4], 'sha256': 'b' * 64, 'moduleMvid': 'c' * 32, 'methods': {}})
        author['methods'][method] = 0x06000001 + i
        kind = frozen.PATH_KINDS[i % 3]
        contract = paths[kind]
        phase = config['methodPhases'][group]
        meter = 0x20000 + driver.old().OWNER_LAYOUTS['CustomAssemblyBinder']['fields']['m_runeCLRInstructionMeter']
        entry = {'methodGroup': group, 'kind': kind, 'pid': config['pid'], 'nonce': config['nonce'],
                 'pc': breakpoints['paths'][kind]['loadPc'], 'nativeFilePc': contract['filePc'],
                 'nativeSlide': 0x100000000, 'nativeUuid': config['nativeUuid'],
                 'nativePath': config['installedNative'], 'nativeModule': 'libcoreclr.dylib',
                 'modulePath': author['path'], 'moduleSimpleName': author['simpleName'],
                 'fileSha256': author['sha256'], 'moduleMvid': author['moduleMvid'],
                 'metadataMethodName': method, 'methodDefToken': author['methods'][method],
                 'loadedMetadataMvidValidated': True, 'loadedPELayout': 'rva', 'collectible': True,
                 'exceptionArgs': 0, 'bytecodeStart': 0x30000, 'methodDescBytecodeStart': 0x30000,
                 'bytecodeSizeSlots': 4, 'bytecodePrefixHex': '00' * 16,
                 'definitionBinder': 0x20000, 'instructionMeter': meter,
                 'meterGate': {'phase': phase}, 'terminalPhase': phase, 'threadContext': 0x40000,
                 'cleanupOwner': meter if phase else 0, 'meterTerminated': bool(phase),
                 'terminationSignal': 'execution-limit' if phase else 'none'}
        if kind != 'function-entry':
            advance = contract['opcodeAddressAdvance']
            entry.update(firstOpcodeAddress=0x30008, opcodeAddressAdvance=advance,
                         opcodeRegisterValue=0x30008 - advance, frameSpillAddress=0x50098,
                         threadContextSpillAddress=0x50088, threadStackPointerAddress=0x40010)
        entries.append(entry)
    write(dest / 'interpreter-entries.json', entries)
    return config, breakpoints


def gate_fixture(driver, dest, config):
    prepare, app, runtime, review = (dest / name for name in ('prepare', 'application', 'runtime', 'review'))
    write(prepare / 'identity.json', {'sourceNative': {'uuid': config['nativeUuid']}})
    write(app / 'state.json', {'syntheticOnly': True})
    native = runtime / 'artifacts/bin/coreclr/iossimulator.arm64.Release/libcoreclr.dylib'
    native.parent.mkdir(parents=True)
    native.write_bytes(b'Synthetic bytes; not a loadable native library.')
    write(review / 'review.json', {'passed': True,
          'capturePath': str(ROOT / 'ios-fresh-author-entry-capture-v2.py'),
          'captureSha256': driver.V2_SHA})
    write(review / 'native-bind-receipt.json', {'passed': True, 'targetProcessCreated': False,
          'physicalDeviceExecuted': False, 'nativeSha256': driver.sha(native),
          'nativeUuid': config['nativeUuid'],
          'paths': {name: [value['prefixHex'], value['filePc']] for name, value in config['paths'].items()}})
    write(review / 'results.json', {'passed': True})
    args = SimpleNamespace(enable_live=True, native_bind_review=review, output=dest,
                           prepare=prepare, application=app, runtime=runtime, timeout=180)
    request = {'nativePrefixBound': True, 'liveDriverSha256': driver.sha(ROOT / 'ios-fresh-author-entry-capture-v2-live.py'),
               'requestContract': driver.LIVE_CONTRACT, 'timeoutSeconds': 180,
               'prepare': str(prepare.resolve()), 'prepareIdentitySha256': driver.sha(prepare / 'identity.json'),
               'application': str(app.resolve()), 'stateSha256': driver.sha(app / 'state.json'),
               'runtime': str(runtime.resolve()), 'paths': copy.deepcopy(config['paths']),
               'nativeBindReviewSha256': driver.sha(review / 'review.json'),
               'nativeBindReceiptSha256': driver.sha(review / 'native-bind-receipt.json')}
    seal_gate(driver, args, request)
    return args, request, native


def seal_gate(driver, args, request):
    write(args.output / 'request.json', request)
    write(args.output / 'live-results.json', {'requestSha256': driver.sha(args.output / 'request.json')})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    driver = load('fresh_live_under_test', ROOT / 'ios-fresh-author-entry-capture-v2-live.py')
    host = driver.old().helper('ios-fresh-author-simulator-continuation.py', driver.old().CONTINUATION_SHA)
    results = []

    def check(name, invoke, reject=False):
        try:
            invoke()
        except (RuntimeError, AssertionError, KeyError, ValueError) as error:
            if not reject:
                raise AssertionError(name + ': ' + str(error)) from error
            results.append({'name': name, 'passed': True, 'corruptionRejected': True})
        else:
            if reject:
                raise AssertionError('Corrupted synthetic evidence accepted: ' + name)
            results.append({'name': name, 'passed': True})

    with tempfile.TemporaryDirectory(prefix='runeclr-live-controls-') as temporary:
        root = Path(temporary)
        baseline = root / 'baseline'
        baseline.mkdir()
        config, breakpoints = capture_fixture(driver, baseline)
        completion_fixture(baseline, config)
        check('synthetic-nine-entry-baseline-real-v2-verifier',
              lambda: driver.verify_capture(baseline, config, breakpoints))
        check('synthetic-15-case-73-context-completion-baseline',
              lambda: driver.validate_completion(baseline, config, host))
        two_paths = root / 'two-observed-paths'
        two_paths.mkdir()
        two_entries = driver.read(baseline / 'interpreter-entries.json')
        ordinary = config['paths']['ordinary-child-dispatch']
        for entry in two_entries:
            if entry['kind'] == 'delegate-child-dispatch':
                entry.update(kind='ordinary-child-dispatch', nativeFilePc=ordinary['filePc'],
                             pc=breakpoints['paths']['ordinary-child-dispatch']['loadPc'],
                             opcodeAddressAdvance=0, opcodeRegisterValue=entry['firstOpcodeAddress'])
        write(two_paths / 'interpreter-entries.json', two_entries)
        check('nine-groups-with-two-observed-paths-no-special-delegate-claim',
              lambda: driver.verify_capture(two_paths, config, breakpoints))

        def completion_control(name, mutate):
            import shutil
            dest = root / name
            shutil.copytree(baseline, dest)
            mutate(dest)
            check(name, lambda: driver.validate_completion(dest, config, host), reject=True)

        def change_json(dest, relative, mutate):
            path = dest / relative
            value = driver.read(path)
            mutate(value)
            write(path, value)

        completion_control('target-exit-one', lambda d: (d / 'lldb.stdout').write_text('Process 1234 exited with status = 1 (0x00000001)\n'))
        completion_control('wrong-target-pid', lambda d: (d / 'lldb.stdout').write_text('Process 1235 exited with status = 0 (0x00000000)\n'))
        completion_control('aggregate-pid', lambda d: change_json(d, 'adapter-evidence/result.json', lambda a: a.update(processId=1235)))
        completion_control('aggregate-nonce', lambda d: change_json(d, 'adapter-evidence/result.json', lambda a: a.update(nonce='0' * 32)))
        completion_control('child-hash', lambda d: (d / 'adapter-evidence/Normal/result.json').write_text('{}'))
        completion_control('native-exit-marker', lambda d: (d / 'native.stdout').write_text((d / 'native.stdout').read_text().replace('actualExit=0', 'actualExit=1')))
        completion_control('native-marker-duplicate', lambda d: (d / 'native.stdout').write_text((d / 'native.stdout').read_text() * 2))
        completion_control('duplicate-child-receipt', lambda d: change_json(d, 'adapter-evidence/result.json', lambda a: a['cases'].__setitem__(1, a['cases'][0])))
        completion_control('child-path-escape', lambda d: change_json(d, 'adapter-evidence/result.json', lambda a: a['cases'][0].update(receipt='../result.json')))

        def alter_child(dest, scenario, mutate):
            relative = scenario + '/result.json'
            change_json(dest, 'adapter-evidence/' + relative, mutate)
            digest = driver.sha(dest / 'adapter-evidence' / relative)
            change_json(dest, 'adapter-evidence/result.json',
                        lambda a: next(x for x in a['cases'] if x['scenario'] == scenario).update(receiptSha256=digest))

        completion_control('uncollected-context-with-valid-hash', lambda d: alter_child(d, 'Normal', lambda a: a['rows'][0].update(collected=False)))
        completion_control('child-nonce-with-valid-hash', lambda d: alter_child(d, 'Normal', lambda a: a.update(nonce='0' * 32)))
        completion_control('static-not-reset-with-valid-hash', lambda d: alter_child(d, 'Normal', lambda a: a['rows'][0]['report']['Logs'].__setitem__(1, 'static=2')))
        completion_control('terminal-script-resumed-with-valid-hash', lambda d: alter_child(d, 'CatchResume', lambda a: a['rows'][0]['report']['Logs'].append('resume')))
        completion_control('budget-ledger-with-valid-hash', lambda d: alter_child(d, 'ConstructorLoop', lambda a: a['rows'][0]['report']['PrototypeBudget'].update(ExecutionExecuted=8191)))
        completion_control('recovery-role-with-valid-hash', lambda d: alter_child(d, 'Recovery', lambda a: a['rows'][1].update(role='bad')))

        def capture_control(name, mutate_bp=None, mutate_entry=None):
            import shutil
            dest = root / name
            shutil.copytree(baseline, dest)
            bp = copy.deepcopy(breakpoints)
            if mutate_bp:
                mutate_bp(bp)
            if mutate_entry:
                change_json(dest, 'interpreter-entries.json', mutate_entry)
            check(name, lambda: driver.verify_capture(dest, config, bp), reject=True)

        capture_control('breakpoint-pid', lambda b: b.update(pid=1235))
        capture_control('breakpoint-uuid', lambda b: b.update(nativeUuid='0' * 32))
        capture_control('breakpoint-layout', lambda b: b['layoutsValidated']['InterpThreadContext'].update(size=96))
        capture_control('breakpoint-prefix', lambda b: b['paths']['ordinary-child-dispatch'].update(prefixHex='0' * 128))
        capture_control('breakpoint-slide', lambda b: b['paths']['ordinary-child-dispatch'].update(loadPc=1))
        capture_control('breakpoint-location-count', lambda b: b['paths']['delegate-child-dispatch'].update(locations=2))
        capture_control('entry-loaded-mvid', mutate_entry=lambda e: e[0].update(moduleMvid='0' * 32))
        capture_control('entry-eh-reentry', mutate_entry=lambda e: e[0].update(exceptionArgs=1))
        capture_control('entry-cleanup-owner', mutate_entry=lambda e: e[-1].update(cleanupOwner=0))
        capture_control('ordinary-old-advance-eight', mutate_entry=lambda e: e[1].update(opcodeAddressAdvance=8))
        capture_control('entry-opcode-frame-mismatch', mutate_entry=lambda e: e[1].update(firstOpcodeAddress=0x30010))
        capture_control('entry-incomplete-method-groups', mutate_entry=lambda e: e.pop())

        gate_args, request, _ = gate_fixture(driver, root / 'gate-baseline', config)
        check('synthetic-native-review-gate-baseline', lambda: driver.gate(gate_args, request))

        def gate_control(name, mutate, reseal=False):
            gate_args, request, native = gate_fixture(driver, root / name, config)
            mutate(gate_args, request, native)
            if reseal:
                seal_gate(driver, gate_args, request)
            check(name, lambda: driver.gate(gate_args, request), reject=True)

        gate_control('missing-live-flag', lambda a, r, n: setattr(a, 'enable_live', False))
        gate_control('different-driver-source-hash', lambda a, r, n: r.update(liveDriverSha256='0' * 64), True)
        gate_control('unreviewed-contract-version', lambda a, r, n: r.update(requestContract='old'), True)
        gate_control('changed-plan-timeout', lambda a, r, n: setattr(a, 'timeout', 181))
        gate_control('changed-native-image', lambda a, r, n: n.write_bytes(b'Changed bytes'))
        gate_control('changed-state', lambda a, r, n: write(a.application / 'state.json', {'changed': True}))
        gate_control('changed-prepare-identity', lambda a, r, n: write(a.prepare / 'identity.json', {'changed': True}))
        gate_control('native-receipt-pc-mismatch', lambda a, r, n: r['paths']['ordinary-child-dispatch'].update(filePc=1), True)
        gate_control('native-receipt-prefix-mismatch', lambda a, r, n: r['paths']['ordinary-child-dispatch'].update(prefixHex='0' * 128), True)
        def change_ordinary_contract(args, request, native):
            changed = copy.deepcopy(request)
            changed['paths']['ordinary-child-dispatch']['opcodeAddressAdvance'] = 8
            write(args.output / 'request.json', changed)

        gate_control('ordinary-contract-changed-after-plan', change_ordinary_contract)

        def cleanup_outcome(fail):
            isolated = load('fresh_live_cleanup_control', ROOT / 'ios-fresh-author-entry-capture-v2-live.py')
            dest = root / ('cleanup-failure' if fail else 'cleanup-success')
            run_args, _, _ = gate_fixture(isolated, dest, config)
            write(dest / 'installation/results.json', {'syntheticOnly': True})
            run_args.launch = True
            run_args.authors = dest / 'synthetic-authors'
            calls = []

            def compile_authors(args):
                calls.append('compile')
                return args.authors

            def readback(args):
                calls.append('readback')

            def launch(args, request):
                calls.append('launch')
                return {'passed': True, 'phase': 'synthetic-launch', 'targetProcessCreated': False}

            def retire(args, label):
                calls.append(label)
                if fail:
                    raise RuntimeError('synthetic cleanup failure')

            error = None
            # Keep the real gate, run orchestration and persisted-result handling.
            with patch.object(isolated, 'compile_authors_after_install', compile_authors), \
                    patch.object(isolated, 'author_readback', readback), \
                    patch.object(isolated, '_launch_and_capture', launch), \
                    patch.object(isolated, 'retire', retire), redirect_stdout(io.StringIO()):
                try:
                    isolated.run(run_args)
                except RuntimeError as caught:
                    error = caught
            result = isolated.read(dest / 'run-results.json')
            assert calls == ['compile', 'readback', 'launch', 'cleanup'], calls
            assert result['passed'] is (not fail), result
            assert result['cleanupSucceeded'] is (not fail), result
            assert result['phase'] == 'synthetic-launch', result
            assert result['driverSha256'] == isolated.sha(ROOT / 'ios-fresh-author-entry-capture-v2-live.py')
            if fail:
                assert error is not None and str(error) == 'Run or owned simulator cleanup failed', error
                assert result['cleanupError'] == 'synthetic cleanup failure', result
            else:
                assert error is None and 'cleanupError' not in result, result

        check('successful-launch-and-cleanup-persists-success', lambda: cleanup_outcome(False))
        check('successful-launch-with-cleanup-failure-persists-failure-and-raises', lambda: cleanup_outcome(True))

    result = {'passed': all(x['passed'] for x in results), 'checks': len(results),
              'syntheticOnly': True, 'targetProcessCreated': False, 'physicalDeviceExecuted': False,
              'captureVerifier': 'real frozen v2 verifier; synthetic addresses and metadata',
              'driverSha256': driver.sha(ROOT / 'ios-fresh-author-entry-capture-v2-live.py'),
              'results': results}
    if args.output:
        write(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
