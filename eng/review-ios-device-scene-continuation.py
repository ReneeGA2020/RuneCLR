#!/usr/bin/env python3
"""Independently review a complete unsigned device scene continuation without executing it."""
import argparse
import copy
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import plistlib
import shlex

ROOT = Path(__file__).resolve().parent.parent
DRIVER_SHA = '3070765badac35979042550d98d37c1892fbd2dc4da8bac76a6d91932e9cd751'
LEGACY_SHA = 'c86af795e75cc810ac949a3ff31269465cd7f34665f798f5c1c168a866c5c15d'
PARENT_RESULT_SHA = 'e437a2f78ae3a8433e5c63123f998b3032a1380f6c8afd0ca7d894191d215507'
PARENT_REVIEW_SHA = 'b1a4d379aac39a99a25cb986df71ce29d28214f6cb2a8a50c562bd580a761dab'
PARSER_SHA = 'fda1c5747b3998195ea7584918c0a5b918164c6cdc929865b92892b8ef092148'
SIM_REVIEW_SHA = '8a6f4536cfea982c240c23f4efcaaeaae43966e66c004473fd3f830ca7b4be46'
SIM_HELPER_SHA = '99aea42ad9a4c5f0cb42aa2bb0910958b250b3c55a093fd7b2c85b073a76745d'
ROWS_SHA = '4ecc6e1751d59d9402eeeaf4e5b155c1a44fb2617ec56aadd183d8ca59ba34d4'
SCENE_MAIN_SHA = 'c49f3cd9050f5d6fcbf73b92996e8b3a1c291a7ec0fc7e3d44b4be722f3c670a'
COMMIT = '3126bbc9a8851a09ac6435b18a12882bad48f3ee'
TREE = '710936ae1729a5689ab0e0896f3cf722ddd3d31c'
SCENE = {'UIApplicationSupportsMultipleScenes': False}
SOURCES = ('runtime.m', 'util.m', 'util.h', 'runtime.h', 'coreclrhost.h', 'host_runtime_contract.h', 'SessionBridge.cs')
METADATA = ('identity', 'mvid', 'metadataRootHeaderSha256', 'canonicalStreams', 'tableCounts', 'methods', 'initializedFields')


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            result.update(block)
    return result.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def inventory(root):
    files = sorted(root.rglob('*'))
    need(not any(p.is_symlink() for p in files), 'Actual bundle cannot contain symlinks')
    return {p.relative_to(root).as_posix(): sha(p) for p in files if p.is_file()}


def helper(name, filename, expected):
    path = ROOT / 'eng' / filename
    need(sha(path) == expected, 'Frozen review helper changed: ' + filename)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def instant(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(parsed.utcoffset() is not None, 'Ordering timestamps require explicit timezone')
    return parsed


def bundle_change(before, after, old_info, new_info):
    need(len(before) == 199 and set(after) == set(before), 'Actual child must retain exactly the parent199-file set')
    need({name for name in before if before[name] != after[name]} == {'Session', 'Info.plist'},
         'Actual child may change only Session and Info.plist')
    need('UIApplicationSceneManifest' not in old_info and new_info == dict(old_info, UIApplicationSceneManifest=SCENE),
         'Actual child plist may only add the fixed scene manifest')
    need(new_info['CFBundleIdentifier'] == 'org.runeclr.deviceprobe'
         and new_info['CFBundleExecutable'] == 'Session' and new_info['CFBundleSupportedPlatforms'] == ['iPhoneOS']
         and new_info['MinimumOSVersion'] == '15.3', 'Actual device bundle/deployment identity differs')


def scope_identity(request, result):
    need(request['schema'] == 'runeclr.ios-device.scene-continuation.v1' and request['driverSha256'] == DRIVER_SHA
         and request['sceneMainSha256'] == SCENE_MAIN_SHA and request['sceneManifest'] == SCENE
         and request['baselineResultSha256'] == PARENT_RESULT_SHA
         and result['passed'] and result['applicationBuilt'] and result['baselineBundleAndSourcesUnchanged']
         and result['unchangedBundleFiles'] == 197 and result['managedComponents'] == 186
         and result['runtimeLibrariesPreserved'] == 10 and result['onlyBundleChanges'] == ['Info.plist', 'Session']
         and not any(request[key] for key in ('runtimeRebuildRequested', 'bridgeRecompileRequested', 'r2rRebuildRequested',
                                             'codesignRequested', 'physicalOperationsRequested'))
         and not any(result[key] for key in ('coreclrNativeRebuilt', 'trustedBridgeRecompiled', 'r2rRebuilt',
                                             'compositeRelinked', 'signingChanged', 'appLaunched', 'physicalDeviceVerified',
                                             'nativeEntryProof', 'originalAuthorPairChanged')),
         'Actual unsigned scene-only repair/source/scope differs')


def native_scope(native, name, files):
    need(native['kind'] == (2 if name == 'Session' else 6) and native['buildVersion']['platform'] == 2
         and native['buildVersion']['minimum'] <= 983808 and not native['codeSignatures'],
         'Actual native role/platform2/minimum15.3/unsigned boundary differs: ' + name)
    if name in ('Session', 'framework.dylib'):
        need(native['buildVersion']['minimum'] == 983808, 'Actual executable/composite must declare minimum15.3')
    if name == 'framework.dylib':
        need(native['rtrHeader'] and native['rtrHeader']['major'] == 31, 'Actual composite must export RTR31 header')
    for dependency in native['dependencies']:
        need(dependency.startswith(('/usr/lib/', '/System/Library/'))
             or dependency.startswith(('@rpath/', '@loader_path/', '@executable_path/')) and PurePosixPath(dependency).name in files,
             'Actual native dependency is outside system/current application')


def wrapper_argv(request, stage, process, expected):
    need(request['wrapperCommand'] == stage['argv'] == process['argv'] == expected
         and process['pid'] > 0 and process['driverPid'] > 0, 'Actual wrapper command/PID differs from independent derivation')


def gate_identity(gate, simulator, accepted):
    need(gate['passed'] and gate['processId'] == accepted['processId'] and gate['nonce'] == accepted['nonce']
         and gate['cases'] == 15 and gate['contexts'] == 73 and gate['mainSha256'] == SCENE_MAIN_SHA
         and not gate['physicalDeviceVerified'] and not gate['nativeEntryProof'], 'Actual simulator scene gate run/scope differs')
    for key, relative in {'requestSha256': 'request.json', 'buildResultSha256': 'build-results.json',
                          'stateSha256': 'state.json', 'runResultSha256': 'run-all/results.json',
                          'launchResultSha256': 'run-all/launch.result.json'}.items():
        need(gate[key] == sha(simulator / relative), 'Actual gate receipt differs from accepted normal simulator: ' + key)
    need(gate['rawResultHashes'] == accepted['lifecycleReceiptHashes'], 'Actual gate raw15-case receipts differ')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('child', 'parent', 'parent-review', 'simulator', 'simulator-review', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    need(not args.output.exists(), 'Fresh complete child independent review output required')
    args.output.mkdir(parents=True)
    result = {'schema': 'runeclr.ios-device.scene-continuation-independent-review.v1', 'passed': False,
              'reviewerSha256': sha(__file__), 'physicalDeviceExecuted': False, 'physicalDeviceInstalled': False,
              'nativeEntryProof': False, 'signingOperation': False, 'targetCodeExecuted': False, 'freshChildAuthorBound': False}
    try:
        child, parent = args.child, args.parent
        managed = helper('scene_device_metadata', 'ios-device-application-review.py', PARSER_SHA)
        normal = helper('scene_simulator_review', 'review-ios-fresh-author-simulator.py', SIM_HELPER_SHA)
        rows = helper('scene_fixed_rows', 'mobile-host-budget-audit.py', ROWS_SHA)
        need(sha(args.parent_review) == PARENT_REVIEW_SHA, 'Accepted original-device independent review changed')
        accepted_parent = read(args.parent_review)
        parent_request, parent_result = read(parent / 'request.json'), read(parent / 'results.json')
        need(accepted_parent['success'] and sha(parent / 'results.json') == PARENT_RESULT_SHA
             and accepted_parent['builderResultsSha256'] == PARENT_RESULT_SHA
             and sha(parent / 'request.json') == accepted_parent['builderRequestSha256']
             and parent_request['driverSha256'] == sha(parent / 'driver.py') == LEGACY_SHA
             and parent_request['sourceCommit'] == parent_result['sourceCommit'] == COMMIT
             and parent_request['sourceTree'] == parent_result['sourceTree'] == TREE
             and parent_request['configuration'] == normal.PROFILE
             and parent_result['sourceTrackedClean'] and parent_result['nativeUnsigned'],
             'Actual parent accepted builder/source/profile binding differs')
        request, built = read(child / 'request.json'), read(child / 'results.json')
        scope_identity(request, built)
        need(sha(child / 'driver.py') == sha(child / 'eng/ios-device-scene-continuation.py') == DRIVER_SHA
             and sha(child / 'eng/ios-device-application-build.py') == LEGACY_SHA
             and request['baselineRequestSha256'] == sha(parent / 'request.json'), 'Actual child frozen source/parent-request differs')
        old_app, new_app = parent / 'app/Session.app', child / 'app/Session.app'
        before, after = inventory(old_app), inventory(new_app)
        need(before == accepted_parent['appInventory'] == read(parent / 'bundle-inventory.json') == request['baselineBundleHashes']
             and after == read(child / 'bundle-inventory.json')
             and sha(child / 'bundle-inventory.json') == built['bundleInventorySha256'], 'Actual complete parent/child app inventory binding differs')
        old_info, new_info = plistlib.loads((old_app / 'Info.plist').read_bytes()), plistlib.loads((new_app / 'Info.plist').read_bytes())
        bundle_change(before, after, old_info, new_info)
        for name in before:
            if name not in ('Session', 'Info.plist'):
                need((old_app / name).read_bytes() == (new_app / name).read_bytes(), 'Actual protected197 file bytes differ: ' + name)
        for name, source in {'baseline-results.json': 'results.json', 'baseline-request.json': 'request.json',
                             'baseline-bundle-inventory.json': 'bundle-inventory.json',
                             'baseline-component-identities.json': 'component-identities.json',
                             'baseline-native-layout.json': 'native-layout.json'}.items():
            need(sha(child / name) == sha(parent / source), 'Actual child parent receipt snapshot differs: ' + name)
        for name, expected in request['baselineSourceHashes'].items():
            need(sha(parent / name) == expected, 'Actual retained baseline source changed: ' + name)
        for name in SOURCES:
            need((child / name).read_bytes() == (parent / name).read_bytes(), 'Actual unchanged trusted wrapper/bridge source differs: ' + name)
        need(sha(child / 'main.m') == SCENE_MAIN_SHA, 'Actual child main differs from accepted scene template')
        reference = read(child / 'component-identities-reference.json')
        components = read(parent / 'component-identities.json')
        raw_hashes = read(parent / 'raw-inputs.json')
        need(reference['directory'] == request['baseline'] and reference['sha256'] == sha(parent / 'component-identities.json')
             == parent_result['componentIdentitiesSha256'] and reference['components'] == 186
             and not reference['rawInputsCopied'] and reference['unchangedBundleFiles'] == 197
             and len(components) == 186 and inventory(parent / 'input') == raw_hashes
             and {n for n in after if n.endswith('.dll')} == set(components) == set(raw_hashes), 'Actual child parent/raw186-component binding differs')
        comparisons = {}
        for name in sorted(components):
            raw, current = managed.managed(parent / 'input' / name), managed.managed(new_app / name)
            need(raw['sha256'] == components[name]['raw']['sha256'] and current['sha256'] == components[name]['component']['sha256']
                 and raw['managedNativeRva'] == 0 and current['managedNativeRva'] > 0
                 and current['readyToRun']['ownerComposite'] == 'framework.dylib' and current['readyToRun']['flags'] & 0x120 == 0x120,
                 'Actual raw/R2R component identity/role/owner differs: ' + name)
            need(all(raw[key] == current[key] for key in METADATA), 'Actual whole canonical metadata/IL/EH/field comparison differs: ' + name)
            comparisons[name] = {'rawSha256': raw['sha256'], 'componentSha256': current['sha256'],
                                 'mvid': current['mvid'], 'methodCount': len(current['methods'])}
        binaries = {}
        for name in ['Session'] + sorted(n for n in after if n.endswith('.dylib')):
            image = managed.native(new_app / name); native_scope(image, name, after); binaries[name] = image
        need(len(binaries) == 11 and len([n for n in after if n.endswith('.dylib')]) == 10, 'Exactly11 native images/10 preserved dylibs required')
        recorded_native = read(child / 'wrapper-native.json')
        need(recorded_native['fileType'] == binaries['Session']['kind']
             and all(recorded_native[key] == binaries['Session'][key]
                     for key in ('sha256', 'buildVersion', 'dependencies', 'codeSignatures')),
             'Actual independently parsed new native wrapper receipt differs')
        need(sha(args.simulator_review) == SIM_REVIEW_SHA, 'Accepted normal scene simulator independent review changed')
        accepted_sim = read(args.simulator_review)
        need(accepted_sim['passed'] and accepted_sim['lifecycleRowsVerified'] and accepted_sim['postSimulatorInstallCompiled']
             and not accepted_sim['physicalDeviceExecuted'] and not accepted_sim['nativeEntryProof'], 'Complete normal scene simulator review required')
        for name, expected in accepted_sim['actualRawReceiptHashes'].items():
            need(sha(args.simulator / name) == expected, 'Actual accepted simulator raw receipt changed: ' + name)
        simstate = read(args.simulator / 'state.json')
        simrun = args.simulator / 'run-all'
        _, _, _, receipt_hashes = rows.adapter(simrun / 'adapter-evidence', accepted_sim['nonce'], accepted_sim['processId'])
        need(receipt_hashes == accepted_sim['lifecycleReceiptHashes'], 'Actual simulator15/73 raw rows differ')
        normal.markers((simrun / 'launch.stdout').read_text() + (simrun / 'launch.stderr').read_text(),
                       accepted_sim['nonce'], accepted_sim['processId'], simstate['bundleId'])
        gate = read(child / 'simulator-scene-gate.json'); gate_identity(gate, args.simulator, accepted_sim)
        need(sha(child / 'simulator-scene-gate.json') == built['simulatorSceneGateSha256'], 'Child actual simulator gate digest differs')
        stage, process, completion = (read(child / n) for n in ('wrapper.request.json', 'wrapper.process.json', 'wrapper.result.json'))
        remote = PurePosixPath(request['wrapperCommand'][-1]).parent.parent.parent
        need(remote.parent == PurePosixPath(request['baseline']).parent and remote.name == child.name, 'Actual private scene child must be a new parent sibling')
        expected = ['xcrun', '--sdk', 'iphoneos', 'clang', '-target', 'arm64-apple-ios15.3', '-fobjc-arc',
                    '-DINVARIANT_GLOBALIZATION=1', '-I' + str(remote), str(remote / 'main.m'), str(remote / 'runtime.m'),
                    str(remote / 'util.m'), '-L' + str(remote / 'app/Session.app'), '-lcoreclr', '-framework', 'UIKit',
                    '-framework', 'Foundation', '-Wl,-rpath,@executable_path', '-o', str(remote / 'app/Session.app/Session')]
        wrapper_argv(request, stage, process, expected)
        need(stage['cwd'] == read(parent / 'wrapper.request.json')['cwd'] and stage['timeoutSeconds'] == 120
             and completion['exitCode'] == 0 and not completion['timedOut']
             and instant(read(simrun / 'launch.result.json')['endedUtc']) <= instant(stage['startedUtc']) <= instant(completion['endedUtc']),
             'Actual sole child wrapper cwd/timeout/exit/gate-before-build ordering differs')
        for suffix in ('stdout', 'stderr'):
            need(sha(child / ('wrapper.' + suffix)) == completion[suffix + 'Sha256'], 'Actual wrapper process raw stream differs')
        master = read(child / 'master-build-execution.json')
        command = shlex.split(master['command'])
        need(master['ok'] and master['exitCode'] == 0 and master['host'] == 'mac-172-26-202-95'
             and json.loads(master['stdout']) == built and master['stderr'] == ''
             and command[:2] == ['/usr/bin/python3', '-B']
             and PurePosixPath(command[2]).name == 'ios-device-scene-continuation.py'
             and command[3:] == ['build', '--baseline', request['baseline'], '--scene-main', request['sceneMainSource'],
                                '--simulator-acceptance', request['simulatorAcceptance'], '--runtime', stage['cwd'],
                                '--output', str(remote), '--build-slot-granted'], 'Actual master-owned sole build invocation/result differs')
        controls = []
        def reject(name, call):
            try:
                call()
            except (ValueError, KeyError) as error:
                controls.append({'name': name, 'rejected': True, 'reason': str(error), 'copiedOrInMemoryOnly': True})
            else:
                controls.append({'name': name, 'rejected': False})
        if args.selftest:
            for name, mutate in {
                'changed-coreclr': lambda b, i: b.update({'libcoreclr.dylib': '0' * 64}),
                'changed-composite': lambda b, i: b.update({'framework.dylib': '0' * 64}),
                'changed-managed-host': lambda b, i: b.update({'RuneCLR.Runtime.dll': '0' * 64}),
                'added-author': lambda b, i: b.update({'HostBudgetProbe.Payload.dll': '0' * 64}),
                'removed-component': lambda b, i: b.pop('RuneCLR.Runtime.dll'),
                'missing-scene-manifest': lambda b, i: i.pop('UIApplicationSceneManifest'),
                'changed-bundle-id': lambda b, i: i.update(CFBundleIdentifier='other.bundle'),
            }.items():
                b, info = copy.deepcopy(after), copy.deepcopy(new_info); mutate(b, info)
                reject(name, lambda b=b, info=info: bundle_change(before, b, old_info, info))
            reject('replayed-legacy-main', lambda: need(sha(parent / 'main.m') == SCENE_MAIN_SHA, 'Legacy main cannot satisfy fixed scene template'))
            altered = copy.deepcopy(binaries['Session']); altered['codeSignatures'] = [{'offset': 1, 'size': 1}]
            reject('signed-device-wrapper', lambda: native_scope(altered, 'Session', after))
            changed = copy.deepcopy(stage); changed['argv'][5] = 'arm64-apple-ios15.3-simulator'
            reject('wrong-wrapper-target', lambda: wrapper_argv(request, changed, process, expected))
            altered_gate = copy.deepcopy(gate); altered_gate['nonce'] = '0' * 32
            reject('wrong-simulator-gate-run', lambda: gate_identity(altered_gate, args.simulator, accepted_sim))
            altered_result = copy.deepcopy(built); altered_result['physicalDeviceVerified'] = True
            reject('physical-device-promoted', lambda: scope_identity(request, altered_result))
            need(len(controls) == 12 and all(c['rejected'] for c in controls), 'Meaningful independent scene rejection control accepted alteration')
        result.update(passed=True, builderResultsSha256=sha(child / 'results.json'), builderRequestSha256=sha(child / 'request.json'),
                      actualLocalApp=str(new_app.resolve()), appInventory=after, appFiles=199, sourceCommit=COMMIT, sourceTree=TREE,
                      configuration=normal.PROFILE, wrapperEndedUtc=completion['endedUtc'], wrapperPid=process['pid'],
                      protectedFileBytesCompared=197, managedComponents=186, nativeImages=11, preservedNativeLibraries=10,
                      managedComparisons=comparisons, nativeBinaries=binaries, parentReviewSha256=PARENT_REVIEW_SHA,
                      simulatorReviewSha256=SIM_REVIEW_SHA, gatePid=gate['processId'], gateNonce=gate['nonce'],
                      controls=controls, controlsTotal=len(controls), controlsRejected=sum(c['rejected'] for c in controls),
                      rawReceiptHashes={name: sha(child / name) for name in ('request.json', 'results.json', 'bundle-inventory.json',
                          'wrapper.request.json', 'wrapper.process.json', 'wrapper.result.json', 'wrapper.stdout', 'wrapper.stderr',
                          'master-build-execution.json', 'simulator-scene-gate.json', 'component-identities-reference.json')},
                      scope='Actual complete199-file unsigned device scene-only child with197 protected bytes and186 whole raw/R2R metadata/IL/EH/fields comparisons; no signing/install/physical execution/new-child-author/method-entry claim.')
    except Exception as error:
        result['error'] = str(error)
    (args.output / 'results.json').write_text(json.dumps(result, indent=2) + chr(10), encoding='ascii')
    print(json.dumps({k: v for k, v in result.items() if k not in ('appInventory', 'managedComparisons', 'nativeBinaries', 'rawReceiptHashes', 'controls')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
