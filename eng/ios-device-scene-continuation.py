#!/usr/bin/env python3
"""Rebuild only an unsigned device UIKit wrapper after verified simulator scene recovery."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import signal
import shutil
import struct
import subprocess
import sys

LEGACY_SHA = 'c86af795e75cc810ac949a3ff31269465cd7f34665f798f5c1c168a866c5c15d'
BASE_RESULT_SHA = 'e437a2f78ae3a8433e5c63123f998b3032a1380f6c8afd0ca7d894191d215507'
SCENE_SHA = 'c49f3cd9050f5d6fcbf73b92996e8b3a1c291a7ec0fc7e3d44b4be722f3c670a'
SIM_CONTROLLER_SHA = '53105c1f8f8321fbb7b4ae309e125f0fb30221abc62fd6eed598850afcbbda5e'
SIM_REPAIR_SHA = '5ad5a082100dc0eb7f3c810970111069dba7ed91b50a3d8e3c2815142e24e608'
ROWS_SHA = '4ecc6e1751d59d9402eeeaf4e5b155c1a44fb2617ec56aadd183d8ca59ba34d4'
SCENE = {'UIApplicationSupportsMultipleScenes': False}
SOURCES = ('runtime.m', 'util.m', 'util.h', 'runtime.h', 'coreclrhost.h', 'host_runtime_contract.h', 'SessionBridge.cs')


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x', encoding='ascii') as stream:
        stream.write(json.dumps(value, indent=2) + chr(10))


def helper(name, expected):
    path = Path(__file__).with_name(name)
    need(sha(path) == expected, 'Frozen helper changed: ' + name)
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def validate_change(before, after, original_plist, new_plist):
    need(len(before) == 199 and set(after) == set(before), 'Exact device bundle file set required')
    need({name for name in before if before[name] != after[name]} == {'Session', 'Info.plist'},
         'Only the UIKit executable and plist may change')
    expected = dict(original_plist, UIApplicationSceneManifest=SCENE)
    need(new_plist == expected, 'Only the declared scene manifest may change')
    need(new_plist['CFBundleIdentifier'] == 'org.runeclr.deviceprobe'
         and new_plist['MinimumOSVersion'] == '15.3', 'Device bundle/deployment identity differs')


def simulator_gate(directory, legacy):
    controller = helper('ios-fresh-author-simulator-continuation.py', SIM_CONTROLLER_SHA)
    rows = helper('mobile-host-budget-audit.py', ROWS_SHA)
    request, build = read(directory / 'request.json'), read(directory / 'build-results.json')
    state = controller.verify_state(directory)
    need(request['schema'] == 'runeclr.ios-fresh-author.simulator-scene-repair.v1'
         and request['driverSha256'] == SIM_REPAIR_SHA and request['continuationSha256'] == SIM_CONTROLLER_SHA
         and sha(directory / 'driver.py') == SIM_REPAIR_SHA
         and sha(directory / 'continuation.py') == SIM_CONTROLLER_SHA
         and request['sceneMainSourceSha256'] == sha(directory / 'main.m') == SCENE_SHA,
         'Actual frozen scene repair source required')
    need(build['passed'] is True and build['applicationBuilt'] is True and build['managedComponents'] == 186
         and build['runtimeRebuilt'] is False and build['trustedHostRecompiled'] is False
         and build['r2rRebuilt'] is False, 'Scene-only repaired simulator build required')
    need(state['sourceCommit'] == legacy.COMMIT and state['sourceTree'] == legacy.TREE
         and state['configuration'] == legacy.PROFILE
         and plistlib.loads((Path(state['app']) / 'Info.plist').read_bytes())['UIApplicationSceneManifest'] == SCENE,
         'Simulator repaired scene manifest/source/configuration differs')
    run = directory / 'run-all'
    outcome, launch, launch_request = read(run / 'results.json'), read(run / 'launch.result.json'), read(run / 'request.json')
    need(outcome['passed'] is True and outcome['platform'] == 'iossimulator.arm64'
         and outcome['driverSha256'] == SIM_CONTROLLER_SHA and outcome['debugger'] is False
         and outcome['launchCount'] == 1 and outcome['cases'] == 15 and outcome['contexts'] == 73,
         'Actual single normal simulator scene run15/73 must pass before device relink')
    need(launch['exitCode'] == 0 and launch['timedOut'] is False
         and launch['stdoutSha256'] == sha(run / 'launch.stdout')
         and launch['stderrSha256'] == sha(run / 'launch.stderr'), 'Actual simulator launch streams/exit differ')
    nonce, pid = outcome['nonce'], outcome['processId']
    need(launch_request['nonce'] == nonce and launch_request['launchCount'] == 1
         and launch_request['debugger'] is False and launch_request['configuration'] == legacy.PROFILE,
         'Single simulator launch owner/profile differs')
    need(launch_request['driverSha256'] == SIM_CONTROLLER_SHA
         and launch_request['buildDriverSha256'] == SIM_REPAIR_SHA
         and launch_request['bundleId'] == state['bundleId']
         and read(run / 'launch.request.json')['argv'] == ['xcrun', 'simctl', 'launch', '--console',
                launch_request['simulator'], state['bundleId']], 'Actual owned simulator launch command differs')
    aggregate, receipts, metrics, hashes = rows.adapter(run / 'adapter-evidence', nonce, pid)
    log = (run / 'launch.stdout').read_text() + (run / 'launch.stderr').read_text()
    for marker in (
        f'FRESH_AUTHOR_SIM_NATIVE pid={pid} nonce={nonce} PhaseAcquireLoad=1 DerivedLedger=1 BatchInterval=0 InterpMode=0 InterpretCollectible=0 ReadyToRun=1',
        f'FRESH_AUTHOR_SIM_INITIALIZE pid={pid} nonce={nonce} hr=0',
        f'FRESH_AUTHOR_SIM_CREATE_DELEGATE pid={pid} nonce={nonce} hr=0',
        f'FRESH_AUTHOR_SIM_INVOKE pid={pid} nonce={nonce} managedExit=0',
        f'FRESH_AUTHOR_SIM_SHUTDOWN pid={pid} nonce={nonce} attempted=false reason=template-exit-path',
        f'FRESH_AUTHOR_SIM_EXIT pid={pid} nonce={nonce} managedExit=0 actualExit=0',
    ):
        need(controller.exact_marker(log, marker, pid), 'Simulator native initialization/invocation/exit marker differs')
    before, after = read(run / 'installed-before.json'), read(run / 'installed-after.json')
    need(before == after and before['bundle'] == state['bundleHashes'], 'Simulator installed identities changed')
    return {'passed': True, 'scope': 'Existing simulator scene recovery only; no physical execution.',
            'processId': pid, 'nonce': nonce, 'cases': len(metrics), 'contexts': 73,
            'requestSha256': sha(directory / 'request.json'), 'buildResultSha256': sha(directory / 'build-results.json'),
            'stateSha256': sha(directory / 'state.json'), 'runResultSha256': sha(run / 'results.json'),
            'launchResultSha256': sha(run / 'launch.result.json'), 'rawResultHashes': hashes,
            'mainSha256': SCENE_SHA, 'physicalDeviceVerified': False, 'nativeEntryProof': False}


def controls(before, original):
    changed = dict(before, Session='synthetic-new-wrapper', **{'Info.plist': 'synthetic-scene-plist'})
    scene = dict(original, UIApplicationSceneManifest=copy.deepcopy(SCENE))
    validate_change(before, changed, original, scene)
    mutations = {
        'changed-coreclr': lambda b, p: b.update({'libcoreclr.dylib': 'changed'}),
        'changed-composite': lambda b, p: b.update({'framework.dylib': 'changed'}),
        'changed-managed-bridge': lambda b, p: b.update({'SessionBridge.dll': 'changed'}),
        'bundled-author': lambda b, p: b.update({'HostBudgetProbe.Payload.dll': 'author'}),
        'missing-r2r-component': lambda b, p: b.pop('RuneCLR.Runtime.dll'),
        'missing-scene-manifest': lambda b, p: p.pop('UIApplicationSceneManifest'),
        'multiple-scenes-enabled': lambda b, p: p['UIApplicationSceneManifest'].update(UIApplicationSupportsMultipleScenes=True),
        'changed-bundle-id': lambda b, p: p.update(CFBundleIdentifier='other.project'),
    }
    result = []
    for name, mutate in mutations.items():
        b, p = copy.deepcopy(changed), copy.deepcopy(scene); mutate(b, p)
        try:
            validate_change(before, b, original, p)
        except RuntimeError:
            result.append({'name': name, 'rejected': True, 'syntheticOnly': True, 'inMemoryOnly': True})
        else:
            raise RuntimeError('Altered scene-only plan accepted: ' + name)
    return result


def wrapper_stage(out, command, env, runtime, legacy):
    argv = list(map(str, command))
    write(out / 'wrapper.request.json', {'argv': argv, 'cwd': str(runtime),
          'timeoutSeconds': 120, 'startedUtc': legacy.utc()})
    timed_out = False
    with (out / 'wrapper.stdout').open('x') as stdout, (out / 'wrapper.stderr').open('x') as stderr:
        process = subprocess.Popen(argv, cwd=runtime, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
        write(out / 'wrapper.process.json', {'pid': process.pid, 'driverPid': os.getpid(), 'argv': argv})
        try:
            code = process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                code = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); code = process.wait(timeout=10)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    write(out / 'wrapper.result.json', {'exitCode': code, 'timedOut': timed_out, 'endedUtc': legacy.utc(),
          'stdoutSha256': sha(out / 'wrapper.stdout'), 'stderrSha256': sha(out / 'wrapper.stderr')})
    need(code == 0 and not timed_out, 'Owned UIKit-only relink failed; retain original attempt')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('plan', 'build'))
    for name in ('baseline', 'scene-main', 'simulator-acceptance', 'runtime', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--build-slot-granted', action='store_true')
    args = parser.parse_args()
    legacy = helper('ios-device-application-build.py', LEGACY_SHA)
    base, out = args.baseline.resolve(), args.output.resolve()
    need(not out.exists() and out.parent == base.parent, 'Fresh private sibling output required')
    need(sha(base / 'results.json') == BASE_RESULT_SHA, 'Exact accepted unsigned device baseline required')
    old_result, old_request = read(base / 'results.json'), read(base / 'request.json')
    need(old_result['success'] is True and old_result['applicationBuilt'] is True
         and old_result['actualManagedComponentCount'] == 186 and old_result['nativeUnsigned'] is True
         and old_request['driverSha256'] == LEGACY_SHA, 'Accepted baseline result/driver differs')
    old_app = base / 'app/Session.app'
    need(sha(base / 'bundle-inventory.json') == old_result['bundleInventorySha256'], 'Baseline inventory/result binding differs')
    before = legacy.inventory(old_app)
    need(before == read(base / 'bundle-inventory.json') and len(before) == 199, 'Actual unsigned baseline bytes changed')
    need(sha(base / 'component-identities.json') == old_result['componentIdentitiesSha256'], 'Accepted component receipt changed')
    components = read(base / 'component-identities.json')
    need(len(components) == 186 and all(before[n] == c['component']['sha256']
         and sha(base / 'input' / n) == c['raw']['sha256'] for n, c in components.items()), 'All186 raw/R2R components must remain unchanged')
    need(sha(args.scene_main) == SCENE_SHA, 'Exact accepted scene main required')
    need(legacy.cap(['git', '-C', args.runtime, 'rev-parse', 'HEAD']) == legacy.COMMIT
         and legacy.cap(['git', '-C', args.runtime, 'rev-parse', 'HEAD^{tree}']) == legacy.TREE
         and not legacy.cap(['git', '-C', args.runtime, 'status', '--porcelain', '--untracked-files=no']),
         'Matching runtime source must remain tracked clean')
    source_before = {name: sha(base / name) for name in (*SOURCES, 'main.m', 'request.json', 'results.json', 'raw-inputs.json')}
    for name in ('runtime.m', 'SessionBridge.cs', 'main.m'):
        need(source_before[name] == old_request['generatedSourceHashes'][name], 'Original generated source changed')
    need((base / 'main.m').read_text() == legacy.MAIN
         and (base / 'SessionBridge.cs').read_text() == legacy.BRIDGE, 'Frozen original main/bridge source differs')
    for relative, expected in legacy.WRAPPERS.items():
        need(sha(args.runtime / relative) == expected, 'Frozen official wrapper input differs: ' + relative)
        if Path(relative).name != 'runtime-coreclr.m':
            need(source_before[Path(relative).name] == expected, 'Retained official wrapper source differs')
    need((base / 'runtime.m').read_text() == legacy.wrapper(args.runtime / 'src/tasks/AppleAppBuilder/Templates/runtime-coreclr.m'),
         'Device runtime wrapper/profile/invocation bytes differ')
    original_plist = plistlib.loads((old_app / 'Info.plist').read_bytes())
    need('UIApplicationSceneManifest' not in original_plist, 'Original failed scene contract differs')
    candidate_plist = dict(original_plist, UIApplicationSceneManifest=copy.deepcopy(SCENE))
    out.mkdir()
    shutil.copyfile(__file__, out / 'driver.py')
    for name in SOURCES:
        shutil.copyfile(base / name, out / name)
    shutil.copyfile(args.scene_main, out / 'main.m')
    app = out / 'app/Session.app'
    command = ['xcrun', '--sdk', 'iphoneos', 'clang', '-target', 'arm64-apple-ios15.3', '-fobjc-arc',
               '-DINVARIANT_GLOBALIZATION=1', '-I' + str(out), out / 'main.m', out / 'runtime.m', out / 'util.m',
               '-L' + str(app), '-lcoreclr', '-framework', 'UIKit', '-framework', 'Foundation',
               '-Wl,-rpath,@executable_path', '-o', app / 'Session']
    request = {'schema': 'runeclr.ios-device.scene-continuation.v1', 'baseline': str(base),
               'baselineResultSha256': BASE_RESULT_SHA, 'baselineRequestSha256': sha(base / 'request.json'),
               'baselineBundleHashes': before, 'baselineSourceHashes': source_before,
               'sceneMainSource': str(args.scene_main), 'sceneMainSha256': SCENE_SHA,
               'sceneManifest': SCENE, 'simulatorAcceptance': str(args.simulator_acceptance),
               'wrapperCommand': list(map(str, command)), 'driverSha256': sha(__file__),
               'runtimeRebuildRequested': False, 'bridgeRecompileRequested': False,
               'r2rRebuildRequested': False, 'codesignRequested': False, 'physicalOperationsRequested': False}
    write(out / 'request.json', request); write(out / 'controls.json', controls(before, original_plist))
    result = {'passed': False, 'applicationBuilt': False, 'coreclrNativeRebuilt': False,
              'trustedBridgeRecompiled': False, 'r2rRebuilt': False, 'compositeRelinked': False,
              'signingChanged': False, 'appLaunched': False, 'physicalDeviceVerified': False,
              'nativeEntryProof': False, 'originalAuthorPairChanged': False, 'controls': 8}
    try:
        if args.phase == 'plan':
            result.update(passed=True, simulatorSceneRecoveryRequired=True,
                          scope='Source-reviewed scene-only device continuation plan and synthetic rejection controls; no compile/sign/install/run.')
            return
        need(sys.platform == 'darwin' and args.build_slot_granted, 'Configured Mac exclusive wrapper slot required')
        gate = simulator_gate(args.simulator_acceptance.resolve(), legacy)
        write(out / 'simulator-scene-gate.json', gate)
        app.parent.mkdir()
        legacy.cap(['/bin/cp', '-cR', old_app, app])
        (app / 'Info.plist').write_bytes(plistlib.dumps(candidate_plist))
        env = {k: v for k, v in os.environ.items() if not k.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_', 'DYLD_', 'LD_'))
               and k not in ('SDKROOT', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH',
                             'LIBRARY_PATH', 'EXTRA_CFLAGS', 'EXTRA_CXXFLAGS', 'EXTRA_LDFLAGS')}
        wrapper_stage(out, command, env, args.runtime, legacy)
        after = legacy.inventory(app)
        validate_change(before, after, original_plist, plistlib.loads((app / 'Info.plist').read_bytes()))
        layout = legacy.native(app / 'Session', 2)
        need(layout['buildVersion']['minimum'] == 983808, 'Device scene wrapper minimum15.3 required')
        need(len(list(app.glob('*.dll'))) == 186 and not any(app.rglob('HostBudgetProbe.*.dll')), 'Exact trusted components without authors required')
        need(all(sha(app / n) == c['component']['sha256'] for n, c in components.items()), 'Accepted R2R components changed')
        write(out / 'bundle-inventory.json', after); write(out / 'wrapper-native.json', layout)
        write(out / 'component-identities-reference.json', {'directory': str(base), 'sha256': sha(base / 'component-identities.json'),
                                                          'components': 186, 'rawInputsCopied': False, 'unchangedBundleFiles': 197})
        result.update(passed=True, applicationBuilt=True, onlyBundleChanges=['Info.plist', 'Session'],
                      unchangedBundleFiles=197, managedComponents=186, runtimeLibrariesPreserved=10,
                      bundleInventorySha256=sha(out / 'bundle-inventory.json'), simulatorSceneGateSha256=sha(out / 'simulator-scene-gate.json'),
                      scope='Unsigned device scene-only executable/plist rebuild; accepted CoreCLR/native/composite/186 components unchanged. No physical signing/install/run.')
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        need(legacy.inventory(old_app) == before and all(sha(base / n) == v for n, v in source_before.items()),
             'Original accepted device application/source changed')
        need(all(sha(out / n) == source_before[n] for n in SOURCES), 'Scene continuation changed retained wrapper/bridge sources')
        result['baselineBundleAndSourcesUnchanged'] = True
        write(out / 'results.json', result)
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
