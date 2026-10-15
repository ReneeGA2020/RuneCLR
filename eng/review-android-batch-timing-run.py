#!/usr/bin/env python3
"""Replay actual Android timing launches and recompute the four-profile matrix."""
import argparse
import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(name, filename, digest):
    path = Path(__file__).with_name(filename)
    if sha(path) != digest:
        raise RuntimeError('Frozen helper differs: ' + filename)
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def review(apk, run, inputs):
    driver_sha = 'd0919029d33eb9aa79202624599a1ffd12a511c26bcca62cf6b45c8842a9ec07'
    driver = module('actual_android_timing', 'android-batch-timing-run.py', driver_sha)
    adapter = module('android_bundle_timing', 'review-android-batch-timing.py',
                     '6491d61802cffad1c8a5d25438d5d8c9c80e5102c5290cc10d533ef9c0fda8f1')
    read, need = adapter.timing_module().kernel().load, adapter.timing_module().kernel().need
    state, request, completed = read(apk / 'state.json'), read(run / 'request.json'), read(run / 'results.json')
    need(sha(run / 'driver.py') == request['driverSha256'] == driver_sha and
         request['plan'] == driver.plan() and request['dependencyPins'] == driver.PINS,
         'Actual runner/matrix source differs')
    need(request['schema'] == 'runeclr.android-batch-timing.run.v1' and request['debugger'] is False and
         completed['passed'] is True and completed['processes'] == 16, 'Actual debugger-free run failed')
    manifest = inputs / 'input-manifest.json'
    need(sha(manifest) == state['inputManifestSha256'] == request['inputManifestSha256'] ==
         'd8f2be284a6034ce415a740365b0b5f09dfdb57c66b1f3c1fad2e07ad327b98b', 'Frozen timing input differs')
    for name, digest in read(manifest)['files'].items():
        path = (inputs / name).resolve()
        need(path.is_relative_to(inputs.resolve()) and sha(path) == digest, 'Timing input byte differs: ' + name)
    component = adapter.bind_application(apk, run / 'installed-before.json')
    need(read(run / 'installed-before.json') == read(run / 'installed-after.json'), 'Installed products changed')
    installed_paths = {}
    for phase in ('before', 'after'):
        inventory = read(run / ('installed-' + phase + '.json'))
        rows = (run / ('installed-' + phase + '.sha256sum.log')).read_text().splitlines()
        command = read(run / ('installed-' + phase + '.command.json'))
        actual = [row.split(None, 1) for row in rows]
        need(len(actual) == len(inventory) == 201 and command['exit'] == 0 and
             command['argv'][:8] == [str(Path('D:/RuneCLR-Android/sdk/platform-tools/adb.exe')),
                                    '-s', 'emulator-5556', 'exec-out', 'run-as',
                                    state['package'], 'sha256sum', actual[0][1]] and
             command['argv'][7:] == [row[1] for row in actual], 'Actual installed inventory command differs')
        paths = {}
        for (name, digest), (actual_digest, location) in zip(inventory.items(), actual):
            need(digest == actual_digest, 'Actual installed hash differs: ' + name)
            if name.endswith('.so'):
                need(location.startswith('/data/app/') and location.endswith('/lib/x86_64/' + name) and
                     state['package'] + '-' in location, 'Native install path differs: ' + name)
            elif name == 'apk/base.apk':
                need(location.startswith('/data/app/') and location.endswith('/base.apk') and
                     state['package'] + '-' in location, 'APK install path differs')
            else:
                need(location == 'files/' + name, 'Managed/author install path differs: ' + name)
            paths[name] = location
        need(not installed_paths or installed_paths == paths, 'Installed native paths changed')
        installed_paths = paths
    for name, digest in completed['rawHashes'].items():
        path = (run / name).resolve()
        need(path.is_relative_to(run.resolve()) and sha(path) == digest, 'Raw run payload differs: ' + name)
    settle = read(run / 'settle.json')
    need(request['settleSeconds'] == settle['requiredSeconds'] == 30 and settle['passed'] is True and
         type(settle['seconds']) in (int, float) and math.isfinite(settle['seconds']) and settle['seconds'] >= 30,
         'Actual post-install settling duration differs')
    quiet_files = list(run.glob('quiet-*.json')) + list(run.glob('*/quiet-*.json'))
    need(len(quiet_files) == 33, 'Quiet process snapshots missing')
    for path in quiet_files:
        quiet = read(path)
        need(quiet['passed'] is True and all(row['blockedReason'] is None for row in quiet['processes']),
             'Compiler/debugger/other experiment present: ' + str(path))
    observations = []
    for cell in driver.plan():
        path = run / cell['label']
        launch, process = read(path / 'request.json'), read(path / 'process.json')
        need(all(launch[key] == value for key, value in cell.items()) and launch['debugger'] is False,
             'Actual profile/order differs')
        nonce, env = launch['nonce'], launch['environment']
        expected_env = {'RUNECLR_BATCH_NONCE': nonce, 'RUNECLR_TIMING_MODE': cell['mode'],
                        'RUNECLR_TIMING_LANE': cell['lane'], 'RUNECLR_TIMING_SAMPLES': '31',
                        'RUNECLR_TIMING_HEX': cell['intervalHex'], 'RUNECLR_TIMING_DERIVED': cell['derived']}
        need(env == expected_env, 'Original native launch environment differs')
        argv = [str(Path('D:/RuneCLR-Android/sdk/platform-tools/adb.exe')), '-s', 'emulator-5556',
                'shell', 'am', 'instrument', '-w']
        for key, value in expected_env.items():
            argv.extend(['-e', 'env:' + key, value])
        argv.append(state['package'] + '/net.dot.MonoRunner')
        started = read(path / 'process-started.json')
        need(launch['argv'] == started['argv'] == argv and started['pid'] == process['pid'] and
             process['exitCode'] == 0 and process['timedOut'] is False and
             process['instrumentationSha256'] == sha(path / 'instrumentation.log'), 'Owned ADB process differs')
        managed = read(path / 'managed-result.json')
        pid = managed['appPid']
        need(managed == dict(nonce=nonce, mode=cell['mode'], lane=cell['lane'], samples='31',
                             interval=cell['intervalHex'], exitCode=0, appPid=pid), 'Managed completion differs')
        need((path / 'pid-query.txt').read_text().strip() == 'android.os.Process.myPid=' + str(pid),
             'Actual Java PID differs')
        native, managed_log = (path / 'native.log').read_text(), (path / 'managed.log').read_text()
        marker = (f"TIMING_NATIVE pid={pid} nonce={nonce} mode={cell['mode']} lane={cell['lane']} samples=31 "
                  f"interval={cell['intervalHex']} DerivedLedger={cell['derived']} PhaseAcquireLoad=1 InterpMode=0 ReadyToRun=1")
        for line in (marker, 'CORECLR_INITIALIZE_HRESULT=0x0', 'CORECLR_EXECUTE_HRESULT=0x0;RUNECLR_EXIT=0',
                     'CORECLR_SHUTDOWN_HRESULT=0x0'):
            need(len(re.findall('^' + re.escape(line) + '$', native, re.M)) == 1, 'Native completion/settings differs')
        completion = f"MOBILE_BATCH_TIMING_COMPLETE nonce={nonce} pid={pid} lane={cell['lane']} mode={cell['mode']} callbacks=34"
        need(native.count(completion) == managed_log.count(completion) == 1, 'Raw managed completion missing')
        instrumentation = (path / 'instrumentation.log').read_text()
        for expression in (r'^INSTRUMENTATION_RESULT: return-code=([0-9-]+)\r?$', r'^INSTRUMENTATION_CODE: ([0-9-]+)\r?$'):
            need(re.findall(expression, instrumentation, re.M) == ['0'], 'Instrumentation exit differs')
        maps = (path / 'maps.log').read_text()
        for name in ('libcoreclr.so', 'libclrinterpreter.so', 'libclrjit.so'):
            matches = re.findall(r'(?m)^([0-9a-f]+)-([0-9a-f]+) ([rwxps-]+) [0-9a-f]+ [0-9a-f:]+ [0-9]+ +(/[^ ]+/' +
                                 re.escape(name) + r')$', maps)
            need(matches and {row[3] for row in matches} == {installed_paths[name]} and
                 any('x' in row[2] and int(row[1], 16) > int(row[0], 16) for row in matches),
                 'Actual executable native mapping differs: ' + name)
        checked = adapter.review_observation(read(path / 'receipt.json'), cell['mode'], cell['lane'], nonce, pid, 31, component)
        observations.append(dict(checked, profile=cell['profile'], pair=cell['pair'],
                                 receiptSha256=sha(path / 'receipt.json')))
    cleanup = read(run / 'cleanup.json')
    need(all(cleanup.get(key) is True for key in ('success', 'appUninstalled', 'ownedSerialAbsent',
                                                'ownedForwardsAbsent', 'shutdownVisibilityEventuallyVerified')) and
         cleanup['physicalDeviceTouched'] is False and 'emulator-5556' not in cleanup['devicesOutput'] and
         'emulator-5556' not in cleanup['forwardsOutput'], 'Owned target cleanup differs')
    return dict(adapter.summarize_observations(observations), passed=True, callbacks=544,
                quietSnapshots=len(quiet_files), rawLaunchLedgerAndTimingVerified=True,
                installedRawHashesAndNativeMappingsVerified=True, cleanupVerified=True,
                cleanupSha256=sha(run / 'cleanup.json'), rawPayloads=len(completed['rawHashes']),
                settling=settle, contractComponentSha256=component, nativeEntryProof=False,
                physicalDeviceVerified=False, observations=observations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('apk', 'run', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = review(args.apk, args.run, args.inputs)
    result['reviewerSha256'] = sha(Path(__file__))
    with args.output.open('x', encoding='ascii') as stream:
        json.dump(result, stream, indent=2)
        stream.write(chr(10))
    print(json.dumps({key: value for key, value in result.items() if key != 'observations'}, indent=2))


if __name__ == '__main__':
    main()
