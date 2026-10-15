#!/usr/bin/env python3
"""Bind a preserved UIKit startup failure to its actual bundle and sole launch."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path, PurePosixPath
import plistlib
import re


def crash_binding(review, header, body, native, state, owned, installed, stdout, launch):
    bundle = state['bundleId']
    match = re.fullmatch(re.escape(bundle) + r': ([1-9][0-9]*)\n?', stdout)
    review.need(match is not None, 'Failed sole launch must have only the actual simctl bundle/PID line')
    pid = int(match.group(1))
    executable = str(PurePosixPath(installed['installedApp']) / 'Session')
    suffix = executable[executable.index('/Library/Developer/CoreSimulator/Devices/'):]
    uuid = header['slice_uuid'].lower().replace('-', '')
    review.need(header['app_name'] == body['procName'] == 'Session' and header['platform'] == 7
                and header['bundleID'] == body['bundleInfo']['CFBundleIdentifier'] == bundle
                and body['pid'] == body['termination']['byPid'] == pid
                and body['procPath'].endswith(suffix) and '/Devices/' + owned['id'] + '/' in suffix
                and native['uuids'] == [uuid], 'Raw IPS PID/bundle/owned-container/signed-MachO UUID binding differs')
    sessions = [item for item in body['usedImages'] if item.get('name') == 'Session']
    review.need(len(sessions) == 1 and sessions[0]['uuid'].lower().replace('-', '') == uuid
                and sessions[0]['arch'] == 'arm64' and sessions[0]['CFBundleIdentifier'] == bundle
                and sessions[0]['path'].endswith(suffix), 'Raw IPS loaded Session image differs from signed executable')
    thread = body['threads'][body['faultingThread']]
    top = thread['frames'][0]
    image = body['usedImages'][top['imageIndex']]
    symbol = '___UIApplicationEvaluateRuntimeIssueForNoSceneLifecycleAdoption_block_invoke'
    review.need(body['exception']['type'] == 'EXC_BREAKPOINT' and body['exception']['signal'] == 'SIGTRAP'
                and body['termination']['namespace'] == 'SIGNAL' and body['termination']['code'] == 5
                and top['symbol'] == symbol and image['name'] == 'UIKitCore'
                and '/UIKitCore.framework/' in image['path'], 'Raw IPS must retain UIKit no-scene adoption trap')
    # Apple uses a space and compact numeric zone, unlike the process JSON ISO format.
    def apple_time(value):
        value = re.sub(r' ([+-][0-9]{2})([0-9]{2})$', r'\1:\2', value)
        return review.instant(value)
    review.need(review.instant(launch['startedUtc']) <= apple_time(body['procLaunch'])
                <= apple_time(body['captureTime']) <= review.instant(launch['endedUtc']),
                'Raw IPS launch/capture does not belong to actual sole launch interval')
    return {'applicationPid': pid, 'bundleId': bundle, 'sessionUuid': header['slice_uuid'],
            'faultingImage': image['name'], 'faultingSymbol': symbol, 'procLaunch': body['procLaunch'],
            'captureTime': body['captureTime'], 'signedSessionSha256': native['sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('experiment', 'authors', 'author-review', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--author-review-sha256', required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('failure_independent_sim', Path(__file__).with_name('review-ios-fresh-author-simulator.py'))
    review = importlib.util.module_from_spec(spec); spec.loader.exec_module(review)
    review.need(not args.output.exists(), 'Fresh startup-failure independent output required')
    args.output.mkdir(parents=True)
    result = {'schema': 'runeclr.ios-fresh-author.simulator-startup-failure-review.v1', 'passed': False,
              'reviewerSha256': review.sha(__file__), 'helperSha256': review.sha(review.__file__),
              'applicationRunPassed': False, 'lifecycleRowsVerified': False, 'physicalDeviceExecuted': False,
              'nativeEntryProof': False, 'runtimeInitializationObserved': False, 'authorExecutionObserved': False}
    try:
        root, run = args.experiment, args.experiment / 'run-all'
        state, owned = review.read(root / 'state.json'), review.read(root / 'owned-simulator.json')
        install = review.read(root / 'installation/results.json')
        process = review.stage_binding(root / 'installation', 'install', ['xcrun', 'simctl', 'install', owned['id'], state['app']])
        absent_path = root / 'installation/installed-before-copy.json'
        absent = review.read(absent_path)
        review.need(install['passed'] and install['simulator'] == owned['id'] and install['bundleId'] == state['bundleId']
                    and install['driverSha256'] == review.CONTINUATION_SHA and install['buildDriverSha256'] == review.BUILDER_SHA
                    and install['stateSha256'] == review.sha(root / 'state.json')
                    and install['installEndedUtc'] == process['endedUtc']
                    and install['readbackSha256'] == review.sha(absent_path) and absent['bundle'] == state['bundleHashes']
                    and not absent['authorDirectoryExists'] and absent['authorFiles'] == {}
                    and absent['appPath'] == install['installedApp'] and absent['dataPath'] == install['dataContainer']
                    and review.instant(process['endedUtc']) <= review.instant(absent['observedUtc']) <= review.instant(install['readbackUtc']),
                    'Actual failed-app installation and initially absent authors differ')
        managed = review.helper('failure_managed', 'ios-device-application-review.py', review.MANAGED_REVIEW_SHA)
        authors = review.author_binding(args.authors, args.author_review, args.author_review_sha256, install['readbackUtc'], managed)
        expected_snapshot = review.inventory(args.authors)
        expected_snapshot['author-binding-review.json'] = args.author_review_sha256
        review.need(review.inventory(run / 'author-compilation') == expected_snapshot, 'Preserved failed-run compilation differs from original NEW attempt1')
        transfer = review.read(run / 'transfer.json')
        before, after = review.read(run / 'installed-before.json'), review.read(run / 'installed-after-failure.json')
        review.transported_author(transfer, before, after, authors['identities'])
        review.need(before['bundle'] == state['bundleHashes'] == review.inventory(root / 'app/Session.app')
                    and transfer['compiledResultSha256'] == review.sha(args.authors / 'results.json')
                    and transfer['installReceiptSha256'] == review.sha(root / 'installation/results.json')
                    and transfer['destination'] == str(PurePosixPath(install['dataContainer']) / 'Documents/budget-plugin'),
                    'Preserved failed-run app/new-author transfer/readback differs')
        request = review.read(run / 'request.json')
        review.launch_identity(request, owned, state)
        launch = review.stage_binding(run, 'launch', ['xcrun', 'simctl', 'launch', '--console', owned['id'], state['bundleId']])
        review.ordering(install, authors['binding'], transfer, launch)
        stdout, stderr = (run / 'launch.stdout').read_text(), (run / 'launch.stderr').read_text()
        review.need(stderr == '' and 'FRESH_AUTHOR_SIM_' not in stdout and 'MOBILE_HOST_BUDGET_' not in stdout
                    and not (run / 'adapter-evidence').exists(), 'Failed startup emitted runtime or author execution evidence')
        actual = review.read(run / 'results.json')
        review.need(actual['passed'] is False and actual['error'] == 'Managed evidence not emitted'
                    and actual['driverSha256'] == review.CONTINUATION_SHA and actual['nonce'] == request['nonce']
                    and actual['debugger'] is False and actual['launchCount'] == 1
                    and not actual['physicalDeviceExecuted'] and not actual['nativeEntryProof'], 'Actual failed-run completion/scope differs')
        info = plistlib.loads((root / 'app/Session.app/Info.plist').read_bytes())
        wrapper = review.helper('failure_wrapper', 'ios-device-application-build.py', review.WRAPPER_HELPER_SHA)
        review.need((root / 'main.m').read_text() == wrapper.MAIN
                    and 'configurationForConnectingSceneSession' not in wrapper.MAIN
                    and info.get('UIApplicationSceneManifest') == {'UIApplicationSupportsMultipleScenes': False},
                    'Original failed application must retain actual legacy main and minimal scene manifest')
        crash_files = list((root / 'crash').glob('*.ips'))
        review.need(len(crash_files) == 1, 'Exactly one raw preserved crash report required')
        crash = crash_files[0]
        review.need(review.sha(crash) == 'd4d9f27d8f1a1ae95997d4388e5cb60d9423543565491601624de0d448efe391', 'Preserved original raw IPS bytes differ')
        first, rest = crash.read_text().split(chr(10), 1)
        header, body = json.loads(first), json.loads(rest)
        native = review.native_image(root / 'app/Session.app/Session')
        binding = crash_binding(review, header, body, native, state, owned, install, stdout, launch)
        deleted = review.stage_binding(root / 'cleanup', 'delete', ['xcrun', 'simctl', 'delete', owned['id']])
        devices, cleanup = review.read(root / 'cleanup/devices-after.json'), review.read(root / 'cleanup/results.json')
        review.need(cleanup['passed'] and cleanup['deleted'] and cleanup['simulator'] == owned['id']
                    and not cleanup['physicalDeviceChanged'] and review.instant(launch['endedUtc']) <= review.instant(deleted['startedUtc'])
                    and not any(d['udid'] == owned['id'] for group in devices['devices'].values() for d in group), 'Failed experiment owned-simulator cleanup differs')
        controls = []
        for name, mutate in {
            'wrong-crash-pid': lambda h, b, n: b.update(pid=1),
            'wrong-crash-bundle': lambda h, b, n: h.update(bundleID='wrong.bundle'),
            'wrong-signed-uuid': lambda h, b, n: n.update(uuids=['0' * 32]),
            'wrong-crash-container': lambda h, b, n: b.update(procPath='/other/Session'),
            'wrong-top-trap': lambda h, b, n: b['threads'][b['faultingThread']]['frames'][0].update(symbol='Other'),
            'wrong-crash-interval': lambda h, b, n: b.update(procLaunch='2000-01-01 00:00:00.00 +0800'),
        }.items():
            h, b, n = copy.deepcopy(header), copy.deepcopy(body), copy.deepcopy(native); mutate(h, b, n)
            try:
                crash_binding(review, h, b, n, state, owned, install, stdout, launch)
            except ValueError as error:
                controls.append({'name': name, 'rejected': True, 'reason': str(error)})
            else:
                controls.append({'name': name, 'rejected': False})
        review.need(all(c['rejected'] for c in controls), 'Startup-failure rejection control unexpectedly accepted')
        result.update(passed=True, crashBinding=binding, authorIdentities=authors['identities'],
                      postSimulatorInstallCompiled=True, installedInputsUnchanged=True, ownedSimulatorDeleted=True,
                      launchToolExitCode=launch['exitCode'], controls=controls, controlCount=len(controls),
                      classification='Our UIKit SDK27 wrapper scene-adoption failure before observed CoreCLR entry; no Microsoft runtime defect claim.',
                      rawCrashSha256=review.sha(crash), rawReceiptHashes={str(p.relative_to(root)): review.sha(p) for p in
                          [crash, absent_path] + [run / n for n in ('request.json', 'transfer.json', 'installed-before.json',
                           'installed-after-failure.json', 'launch.request.json', 'launch.process.json', 'launch.result.json',
                           'launch.stdout', 'launch.stderr', 'results.json')]})
    except Exception as error:
        result['error'] = str(error)
    (args.output / 'results.json').write_text(json.dumps(result, indent=2) + chr(10), encoding='ascii')
    print(json.dumps({k: v for k, v in result.items() if k not in ('rawReceiptHashes', 'authorIdentities', 'controls')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
