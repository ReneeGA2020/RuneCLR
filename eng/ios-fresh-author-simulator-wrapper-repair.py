#!/usr/bin/env python3
"""Repair only the UIKit scene wrapper in a new immutable simulator bundle."""
import argparse
import importlib.util
from pathlib import Path
import plistlib
import shutil
import uuid

PREVIOUS = '2d99895d3d327d484da78ddafbdaaa841e17555af2743bace59ef087221e694b'
CONTINUATION = '53105c1f8f8321fbb7b4ae309e125f0fb30221abc62fd6eed598850afcbbda5e'
SCENE = 'c49f3cd9050f5d6fcbf73b92996e8b3a1c291a7ec0fc7e3d44b4be722f3c670a'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous', type=Path, required=True)
    parser.add_argument('--scene-main', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    helper_path = Path(__file__).with_name('ios-fresh-author-simulator-continuation.py')
    spec = importlib.util.spec_from_file_location('frozen_simulator_controller', helper_path)
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    helper.need(helper.sha(helper_path) == CONTINUATION, 'Frozen controller differs')
    old, out = args.previous.resolve(), args.output.resolve()
    state = helper.verify_state(old)
    helper.need(helper.read(old / 'request.json')['driverSha256'] == PREVIOUS, 'Original build binding differs')
    helper.need(helper.sha(args.scene_main) == SCENE, 'Accepted scene lifecycle template differs')
    helper.need(not out.exists(), 'Fresh repaired-app output required')
    old_inventory = helper.inventory(old)
    out.mkdir()
    for name in ('app', 'input', 'source', 'wrapper-inputs', 'critical-native', 'unsigned-native'):
        shutil.copytree(old / name, out / name)
    for name in ('matching-build.json', 'source-proof.json', 'framework-reuse.json', 'device-host-request.json', 'device-host-results.json', 'device-host-raw-inputs.json', 'runtime.m', 'util.m', 'util.h', 'runtime.h', 'coreclrhost.h', 'host_runtime_contract.h', 'wrapper-helper.py'):
        shutil.copyfile(old / name, out / name)
    shutil.copyfile(old / 'state.json', out / 'previous-state.json')
    shutil.copyfile(old / 'request.json', out / 'previous-build-request.json')
    shutil.copyfile(old / 'build-results.json', out / 'previous-build-results.json')
    shutil.copyfile(old / 'run-all/results.json', out / 'previous-run-failure.json')
    shutil.copytree(old / 'crash', out / 'previous-crash')
    shutil.copyfile(args.scene_main, out / 'scene-template-main.m')
    shutil.copyfile(args.scene_main, out / 'main.m')
    shutil.copyfile(__file__, out / 'driver.py')
    shutil.copyfile(helper_path, out / 'continuation.py')
    app = out / 'app/Session.app'
    old_bundle = helper.inventory(app)
    bundle_id = 'org.runeclr.freshauthorscene.' + uuid.uuid4().hex[:12]
    plist = plistlib.loads((app / 'Info.plist').read_bytes())
    plist.update(CFBundleIdentifier=bundle_id, UIApplicationSceneManifest={'UIApplicationSupportsMultipleScenes': False})
    (app / 'Info.plist').write_bytes(plistlib.dumps(plist))
    command = ['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator', '-fobjc-arc', '-DINVARIANT_GLOBALIZATION=1', '-I' + str(out), out / 'main.m', out / 'runtime.m', out / 'util.m', '-L' + str(app), '-lcoreclr', '-framework', 'UIKit', '-framework', 'Foundation', '-Wl,-rpath,@executable_path', '-o', app / 'Session']
    helper.write(out / 'request.json', {'schema': 'runeclr.ios-fresh-author.simulator-scene-repair.v1', 'driverSha256': helper.sha(__file__), 'previousBuildDriverSha256': PREVIOUS, 'continuationSha256': CONTINUATION, 'previousDirectory': str(old), 'previousBeforeHashes': old_inventory, 'previousBuildRequestSha256': helper.sha(old / 'request.json'), 'previousStateSha256': helper.sha(old / 'state.json'), 'sceneMainSource': str(args.scene_main), 'sceneMainSourceSha256': SCENE, 'sourceCommit': state['sourceCommit'], 'sourceTree': state['sourceTree'], 'buildReceiptSha256': helper.BUILD, 'configuration': state['configuration'], 'rawInputHashes': state['rawInputHashes'], 'wrapperCommand': list(map(str, command)), 'runtimeRebuilt': False, 'trustedHostRecompiled': False, 'r2rRebuilt': False, 'deviceAppRepaired': False, 'physicalDeviceExecuted': False, 'startedUtc': helper.utc()})
    result = {'passed': False, 'runtimeRebuilt': False, 'trustedHostRecompiled': False, 'r2rRebuilt': False, 'physicalDeviceExecuted': False, 'deviceAppRepaired': False}
    try:
        helper.stage(out, 'wrapper', command)
        shutil.copyfile(app / 'Session', out / 'unsigned-native/Session')
        helper.stage(out, 'sign-app', ['codesign', '--force', '--sign', '-', app], timeout=120)
        helper.stage(out, 'sign-verify', ['codesign', '--verify', '--strict', app], timeout=120)
        bundle = helper.inventory(app)
        preserved = [n for n in old_bundle if n not in ('Session', 'Info.plist') and not n.startswith('_CodeSignature/')]
        helper.need(all(bundle[n] == old_bundle[n] for n in preserved), 'Non-wrapper signed bundle bytes changed')
        helper.need(helper.inventory(out / 'input') == state['rawInputHashes'], 'Raw trusted inputs changed')
        helper.need(helper.inventory(old) == old_inventory, 'Failed original experiment changed')
        new_state = dict(state, app=str(app), bundleId=bundle_id, bundleHashes=bundle,
                         nativeOutputs={p.name: helper.native(p, 2 if p.name == 'Session' else 6) for p in [app / 'Session', *app.glob('*.dylib')]},
                         previousStateSha256=helper.sha(old / 'state.json'), sceneMainSha256=SCENE,
                         r2rRebuilt=False, wrapperOnlyRepair=True)
        helper.write(out / 'state.json', new_state)
        result.update(passed=True, applicationBuilt=True, managedComponents=len(state['components']), preservedNonWrapperFiles=len(preserved), authorBundled=False)
    finally:
        result['endedUtc'] = helper.utc(); helper.write(out / 'build-results.json', result)
        print(result, flush=True)


if __name__ == '__main__':
    main()

