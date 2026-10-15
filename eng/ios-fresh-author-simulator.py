#!/usr/bin/env python3
"""Compose a private simulator host, then load IL compiled after installation."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import struct
import subprocess
import sys
import uuid

COMMIT = '3126bbc9a8851a09ac6435b18a12882bad48f3ee'
TREE = '710936ae1729a5689ab0e0896f3cf722ddd3d31c'
BUILD = 'c071b2c67103b5646f37cffdc8a442a8e711105585df9740635459ef1bb86745'
FRAMEWORK = '8a4f83d62d07a4bc75d270951989be6b9c46e7974c34abb636666556a03495cf'
HELPER = 'c86af795e75cc810ac949a3ff31269465cd7f34665f798f5c1c168a866c5c15d'
BRIDGE = 'e97b5ef13fa5029251dec29d171a640c1d1c342c658ba2859bc2fe015aa8de29'
AUTHOR = ('HostBudgetProbe.Payload.dll', 'HostBudgetProbe.Private.dll')
TRUSTED = ('RuneCLR.Abstractions.dll', 'RuneCLR.Packages.dll', 'RuneCLR.Runtime.dll', 'MobileHostBudgetProbe.dll')


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


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
        json.dump(value, stream, indent=2)
        stream.write('\n')


def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(Path(root).rglob('*')) if p.is_file()}


def module(filename, expected):
    path = Path(__file__).with_name(filename)
    need(sha(path) == expected, 'Frozen helper differs: ' + filename)
    spec = importlib.util.spec_from_file_location(filename.replace('-', '_'), path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def capture(argv):
    return subprocess.check_output(list(map(str, argv)), text=True).strip()


def stage(out, label, argv, env=None, timeout=900, before_timeout_retire=None):
    argv = list(map(str, argv))
    started = utc()
    write(out / (label + '.request.json'), {'argv': argv, 'cwd': str(Path.cwd()), 'startedUtc': started, 'timeoutSeconds': timeout})
    with (out / (label + '.stdout')).open('x') as stdout, (out / (label + '.stderr')).open('x') as stderr:
        process = subprocess.Popen(argv, stdout=stdout, stderr=stderr, env=env, start_new_session=True)
        write(out / (label + '.process.json'), {'pid': process.pid, 'driverPid': os.getpid(), 'argv': argv, 'startedUtc': utc()})
        timed_out = False
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if before_timeout_retire is not None:
                before_timeout_retire()
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                code = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                code = process.wait(timeout=10)
    result = {'exitCode': code, 'timedOut': timed_out, 'startedUtc': started, 'endedUtc': utc(), 'pid': process.pid,
              'stdoutSha256': sha(out / (label + '.stdout')), 'stderrSha256': sha(out / (label + '.stderr'))}
    write(out / (label + '.result.json'), result)
    need(code == 0 and not timed_out, 'Owned stage failed; preserve ' + label)
    return result


def native(path, kind):
    data = Path(path).read_bytes()
    need(len(data) >= 32 and struct.unpack_from('<II', data) == (0xfeedfacf, 0x100000c), 'Thin ARM64 Mach-O required')
    need(struct.unpack_from('<I', data, 12)[0] == kind, 'Mach-O file type differs')
    count, size = struct.unpack_from('<II', data, 16)
    cursor, limit, versions, signatures = 32, 32 + size, [], []
    need(limit <= len(data), 'Mach-O command bounds')
    for _ in range(count):
        need(cursor + 8 <= limit, 'Mach-O command header')
        command, length = struct.unpack_from('<II', data, cursor)
        need(length >= 8 and cursor + length <= limit, 'Mach-O command length')
        if command == 0x32:
            versions.append(struct.unpack_from('<III', data, cursor + 8))
        if command == 0x1d:
            signatures.append(struct.unpack_from('<II', data, cursor + 8))
        cursor += length
    need(cursor == limit and len(versions) == 1 and versions[0][0] == 7, 'iOS simulator platform7 required')
    return {'sha256': sha(path), 'fileType': kind, 'buildVersion': versions[0], 'signatures': signatures}


def verify_state(out):
    state = read(out / 'state.json')
    need(inventory(Path(state['app'])) == state['bundleHashes'], 'Frozen signed app changed')
    need(sha(out / 'matching-build.json') == BUILD, 'Matching simulator receipt changed')
    for name, digest in state['rawInputHashes'].items():
        need(sha(out / 'input' / name) == digest, 'Frozen raw composite input changed: ' + name)
    return state


def build(args):
    helper = module('ios-device-application-build.py', HELPER)
    out, runtime = args.output.resolve(), args.runtime.resolve()
    need(not out.exists(), 'Fresh output required')
    need(sys.platform == 'darwin', 'Configured Mac required')
    need(capture(['git', '-C', runtime, 'rev-parse', 'HEAD']) == COMMIT and capture(['git', '-C', runtime, 'rev-parse', 'HEAD^{tree}']) == TREE, 'Live source identity differs')
    need(not capture(['git', '-C', runtime, 'status', '--porcelain', '--untracked-files=no']), 'Live tracked source dirty')
    need(sha(args.build_receipt) == BUILD and sha(args.framework_manifest) == FRAMEWORK, 'Accepted receipt differs')
    receipt, framework = read(args.build_receipt), read(args.framework_manifest)
    need(receipt['success'] and receipt['buildExit'] == 0 and receipt['commit'] == COMMIT and receipt['tree'] == TREE and receipt['target'] == 'iossimulator.arm64', 'Matching Release simulator build required')
    product = runtime / 'artifacts/bin/coreclr/iossimulator.arm64.Release'
    critical = {'libcoreclr.dylib': (product / 'libcoreclr.dylib', 'nativeSha256'),
                'System.Private.CoreLib.dll': (product / 'IL/System.Private.CoreLib.dll', 'corelibSha256'),
                'crossgen2': (product / 'arm64/crossgen2/crossgen2', 'crossgen2Sha256')}
    for name, (path, key) in critical.items():
        need(sha(path) == receipt[key], 'Actual runtime product changed: ' + name)
    proof_path = runtime.parent / 'source-proof.json'
    proof = read(proof_path)
    need(sha(proof_path) == receipt['sourceProofSha256'], 'Native build source proof differs')
    for name, digest in proof['sourceHashes'].items():
        need(sha(runtime / name) == digest, 'Built runtime source changed: ' + name)
    baseline = inventory(args.baseline_app)
    need(baseline == read(args.baseline_app.parent.parent / 'state.json')['bundleHashes'], 'Original batch app changed')
    device = inventory(args.device_host)
    device_request = read(args.device_host / 'request.json')
    raw = read(args.device_host / 'raw-inputs.json')
    need(sha(args.device_host / 'input/SessionBridge.dll') == BRIDGE == raw['SessionBridge.dll'], 'Accepted raw bridge differs')
    for name in TRUSTED:
        need(sha(args.device_host / 'input' / name) == raw[name] == device_request['trustedRawHashes'][name], 'Accepted trusted host IL changed')
    framework_source = Path(framework['source'])
    reuse = framework['inputHashes']
    need(len(reuse) > 150 and 'System.Private.CoreLib.dll' not in reuse and not set(TRUSTED) & set(reuse), 'Framework-only inputs required')
    for name, digest in reuse.items():
        need(Path(name).name == name and sha(framework_source / name) == digest, 'Accepted framework input differs')
    out.mkdir(); (out / 'input').mkdir(); (out / 'source').mkdir(); (out / 'unsigned-native').mkdir()
    for source, target in ((args.build_receipt, 'matching-build.json'), (args.framework_manifest, 'framework-reuse.json'), (proof_path, 'source-proof.json'), (Path(__file__), 'driver.py')):
        shutil.copyfile(source, out / target)
    for name in ('request.json', 'results.json', 'raw-inputs.json'):
        shutil.copyfile(args.device_host / name, out / ('device-host-' + name))
    for relative in proof['sourceHashes']:
        target = out / 'source' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(runtime / relative, target)
    for relative, digest in helper.WRAPPERS.items():
        path = runtime / relative
        need(sha(path) == digest, 'Official LF wrapper source changed')
        target = out / 'wrapper-inputs' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if path.name != 'runtime-coreclr.m':
            shutil.copyfile(path, out / path.name)
    (out / 'main.m').write_text(helper.MAIN, encoding='ascii')
    wrapper = helper.wrapper(runtime / 'src/tasks/AppleAppBuilder/Templates/runtime-coreclr.m')
    need(wrapper.count('ios-arm64') == 1, 'Wrapper RID anchor differs')
    (out / 'runtime.m').write_text(wrapper.replace('ios-arm64', 'iossimulator-arm64').replace('DEVICE_APP_', 'FRESH_AUTHOR_SIM_'), encoding='ascii')
    app = out / 'app/Session.app'; app.mkdir(parents=True)
    for name in reuse:
        shutil.copyfile(framework_source / name, out / 'input' / name)
    for name in (*TRUSTED, 'SessionBridge.dll'):
        shutil.copyfile(args.device_host / 'input' / name, out / 'input' / name)
    shutil.copyfile(critical['System.Private.CoreLib.dll'][0], out / 'input/System.Private.CoreLib.dll')
    for path in args.baseline_app.glob('*.dylib'):
        if path.name == 'framework.dylib':
            continue
        source = critical['libcoreclr.dylib'][0] if path.name == 'libcoreclr.dylib' else path
        native(source, 6)
        shutil.copyfile(source, app / path.name)
        shutil.copyfile(source, out / 'unsigned-native' / path.name)
    shutil.copyfile(args.baseline_app / 'Microsoft.NETCore.App.deps.json', app / 'Microsoft.NETCore.App.deps.json')
    bundle_id = 'org.runeclr.freshauthor.' + uuid.uuid4().hex[:12]
    plist = plistlib.loads((args.baseline_app / 'Info.plist').read_bytes())
    plist.update(CFBundleIdentifier=bundle_id, CFBundleExecutable='Session', CFBundleName='Session', CFBundleSupportedPlatforms=['iPhoneSimulator'])
    (app / 'Info.plist').write_bytes(plistlib.dumps(plist))
    rsp = out / 'crossgen.rsp'
    rsp.write_text('\n'.join(['--targetos:iossimulator', '--targetarch:arm64', '--obj-format:macho', '--composite', '--inputbubble', '--parallelism:2', '--resilient', '--optimize', '--out:' + str(app / 'framework.dylib'), *map(str, sorted((out / 'input').glob('*.dll')))]) + '\n', encoding='ascii')
    raw_inputs = inventory(out / 'input')
    write(out / 'request.json', {'schema': 'runeclr.ios-fresh-author.simulator-build.v1', 'startedUtc': utc(), 'driverSha256': sha(__file__), 'sourceCommit': COMMIT, 'sourceTree': TREE, 'buildReceiptSha256': BUILD, 'sourceProofSha256': sha(proof_path), 'rawInputHashes': raw_inputs, 'deviceHostDirectory': str(args.device_host), 'deviceHostBeforeHashes': device, 'baselineBeforeHashes': baseline, 'wrapperHelperSha256': HELPER, 'originalNative': native(critical['libcoreclr.dylib'][0], 6), 'configuration': helper.PROFILE, 'trustedHostRecompiled': False, 'runtimeRebuilt': False, 'physicalDeviceExecuted': False})
    env = {k: v for k, v in os.environ.items() if not k.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_', 'DYLD_', 'LD_'))}
    result = {'passed': False, 'physicalDeviceExecuted': False, 'runtimeRebuilt': False, 'trustedHostRecompiled': False, 'nativeEntryProof': False}
    try:
        stage(out, 'crossgen', [critical['crossgen2'][0], '@' + str(rsp)], env)
        shutil.copyfile(app / 'framework.dylib', out / 'framework.o')
        stage(out, 'composite-link', ['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator', '-dynamiclib', out / 'framework.o', '-Wl,-install_name,@rpath/framework.dylib', '-o', app / 'framework.dylib'], env)
        stage(out, 'wrapper', ['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator', '-fobjc-arc', '-DINVARIANT_GLOBALIZATION=1', '-I' + str(out), out / 'main.m', out / 'runtime.m', out / 'util.m', '-L' + str(app), '-lcoreclr', '-framework', 'UIKit', '-framework', 'Foundation', '-Wl,-rpath,@executable_path', '-o', app / 'Session'], env)
        for name in ('Session', 'framework.dylib'):
            native(app / name, 2 if name == 'Session' else 6)
            shutil.copyfile(app / name, out / 'unsigned-native' / name)
        components = {}
        for name in raw_inputs:
            before, after = helper.managed(out / 'input' / name), helper.managed(app / name)
            need(before['managedNativeRva'] == 0 and after['managedNativeRva'] > 0 and before['mvid'] == after['mvid'], 'Trusted R2R component identity differs')
            components[name] = {'raw': before, 'component': after}
        need(not any(app.rglob('HostBudgetProbe.*.dll')), 'Author entered pre-install bundle')
        write(out / 'unsigned-bundle.json', inventory(app))
        for path in sorted(app.glob('*.dylib')):
            stage(out, 'sign-' + path.stem, ['codesign', '--force', '--sign', '-', path], env, 120)
        stage(out, 'sign-app', ['codesign', '--force', '--sign', '-', app], env, 120)
        stage(out, 'sign-verify', ['codesign', '--verify', '--strict', app], env, 120)
        need(inventory(args.device_host) == device and inventory(args.baseline_app) == baseline, 'Original host/application changed')
        need(inventory(out / 'input') == raw_inputs, 'Raw composite inputs changed')
        state = {'app': str(app), 'bundleId': bundle_id, 'bundleHashes': inventory(app), 'rawInputHashes': raw_inputs, 'components': components, 'nativeOutputs': {p.name: native(p, 2 if p.name == 'Session' else 6) for p in [app / 'Session', *app.glob('*.dylib')]}, 'sourceCommit': COMMIT, 'sourceTree': TREE, 'configuration': helper.PROFILE, 'physicalDeviceExecuted': False, 'nativeEntryProof': False}
        write(out / 'state.json', state)
        result.update(passed=True, managedComponents=len(components), applicationBuilt=True, authorBundled=False)
    finally:
        result['endedUtc'] = utc(); write(out / 'build-results.json', result)
        print(json.dumps(result), flush=True)


def install(args):
    out = args.output.resolve(); state = verify_state(out); dest = out / 'installation'; dest.mkdir()
    simulator = capture(['xcrun', 'simctl', 'create', 'RuneCLR-FreshAuthor', args.device_type, args.sim_runtime])
    write(out / 'owned-simulator.json', {'id': simulator, 'bundleId': state['bundleId'], 'createdUtc': utc()})
    stage(dest, 'boot', ['xcrun', 'simctl', 'boot', simulator], timeout=120)
    stage(dest, 'bootstatus', ['xcrun', 'simctl', 'bootstatus', simulator, '-b'], timeout=180)
    process = stage(dest, 'install', ['xcrun', 'simctl', 'install', simulator, state['app']], timeout=180)
    installed = Path(capture(['xcrun', 'simctl', 'get_app_container', simulator, state['bundleId'], 'app']))
    data = Path(capture(['xcrun', 'simctl', 'get_app_container', simulator, state['bundleId'], 'data']))
    need(inventory(installed) == state['bundleHashes'] and not any(installed.rglob('HostBudgetProbe.*.dll')), 'Installed app identity or author isolation differs')
    need(not (data / 'Documents/budget-plugin').exists(), 'Author destination must be absent after installation')
    write(dest / 'installed-before-copy.json', {'bundle': inventory(installed), 'authorFiles': {}, 'authorDirectoryExists': False, 'appPath': str(installed), 'dataPath': str(data), 'observedUtc': utc()})
    receipt = {'schema': 'runeclr.ios-fresh-author.simulator-install.v1', 'passed': True, 'simulator': simulator, 'bundleId': state['bundleId'], 'installedApp': str(installed), 'dataContainer': str(data), 'installEndedUtc': process['endedUtc'], 'readbackUtc': utc(), 'installResultSha256': sha(dest / 'install.result.json'), 'installRequestSha256': sha(dest / 'install.request.json'), 'readbackSha256': sha(dest / 'installed-before-copy.json'), 'stateSha256': sha(out / 'state.json'), 'physicalDeviceInstalled': False}
    write(dest / 'results.json', receipt)
    print(json.dumps(receipt), flush=True)


def retire_owned(out, dest, label):
    owned = read(out / 'owned-simulator.json')
    results = []
    for name, argv in [('terminate', ['xcrun', 'simctl', 'terminate', owned['id'], owned['bundleId']]), ('shutdown', ['xcrun', 'simctl', 'shutdown', owned['id']])]:
        started = utc()
        process = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        (dest / (label + '-' + name + '.stdout')).write_bytes(process.stdout)
        (dest / (label + '-' + name + '.stderr')).write_bytes(process.stderr)
        results.append({'argv': argv, 'exitCode': process.returncode, 'startedUtc': started, 'endedUtc': utc()})
    write(dest / (label + '-owned-retirement.json'), results)


def cleanup(args):
    out = args.output.resolve(); owned = read(out / 'owned-simulator.json'); dest = out / 'cleanup'; dest.mkdir()
    retire_owned(out, dest, 'cleanup')
    stage(dest, 'delete', ['xcrun', 'simctl', 'delete', owned['id']], timeout=120)
    listing = json.loads(capture(['xcrun', 'simctl', 'list', 'devices', '--json']))
    write(dest / 'devices-after.json', listing)
    need(not any(x['udid'] == owned['id'] for group in listing['devices'].values() for x in group), 'Owned simulator survived cleanup')
    write(dest / 'results.json', {'passed': True, 'simulator': owned['id'], 'deleted': True, 'physicalDeviceChanged': False, 'observedUtc': utc()})


def execute(args):
    out = args.output.resolve(); state = verify_state(out); install_receipt = read(out / 'installation/results.json')
    authors = args.authors.resolve(); compiled = read(authors / 'results.json')
    need(compiled['passed'] and compiled['authorCompilationCount'] == 2 and compiled['postDeviceHostBuildCompiled'] and compiled['authorIlOnly'], 'Actual fresh author compiler receipts required')
    need(datetime.fromisoformat(compiled['startedAfterHostBindingUtc']) > datetime.fromisoformat(install_receipt['readbackUtc']), 'Author compilation must follow simulator install readback')
    dest = out / 'run-all'; dest.mkdir(); shutil.copytree(authors, dest / 'author-compilation')
    simulator, bundle_id = install_receipt['simulator'], state['bundleId']
    installed, data = Path(install_receipt['installedApp']), Path(install_receipt['dataContainer'])
    need(inventory(installed) == state['bundleHashes'], 'Installed app changed before author transfer')
    plugin = data / 'Documents/budget-plugin'; need(not plugin.exists(), 'Fresh author destination required')
    started = utc(); plugin.mkdir(parents=True)
    for name in AUTHOR:
        need(sha(authors / 'plugin' / name) == compiled['authorHashes'][name], 'Fresh author input hash differs')
        shutil.copyfile(authors / 'plugin' / name, plugin / name)
    need(inventory(plugin) == compiled['authorHashes'], 'Post-install author readback differs')
    write(dest / 'transfer.json', {'startedUtc': started, 'endedUtc': utc(), 'sourceDirectory': str(authors), 'destination': str(plugin), 'authorHashes': inventory(plugin), 'compiledResultSha256': sha(authors / 'results.json'), 'installReceiptSha256': sha(out / 'installation/results.json')})
    before = {'bundle': inventory(installed), 'author': inventory(plugin)}; write(dest / 'installed-before.json', before)
    nonce = uuid.uuid4().hex
    env = {k: v for k, v in os.environ.items() if not k.startswith('SIMCTL_CHILD_')}
    env['SIMCTL_CHILD_RUNECLR_BUDGET_NONCE'] = nonce
    write(dest / 'request.json', {'nonce': nonce, 'configuration': state['configuration'], 'simulator': simulator, 'bundleId': bundle_id, 'environment': {'SIMCTL_CHILD_RUNECLR_BUDGET_NONCE': nonce}, 'debugger': False, 'physicalDeviceExecuted': False, 'launchCount': 1, 'startedUtc': utc()})
    result = {'passed': False, 'physicalDeviceExecuted': False, 'nativeEntryProof': False, 'debugger': False, 'launchCount': 1, 'nonce': nonce}
    try:
        stage(dest, 'launch', ['xcrun', 'simctl', 'launch', '--console', simulator, bundle_id], env, args.timeout, lambda: retire_owned(out, dest, 'timeout'))
        evidence = data / 'Documents' / ('budget-evidence-' + nonce)
        need(evidence.is_dir(), 'Managed evidence not emitted')
        shutil.copytree(evidence, dest / 'adapter-evidence')
        adapter = read(dest / 'adapter-evidence/result.json'); pid = adapter['processId']
        need(adapter['passed'] and adapter['nonce'] == nonce and adapter['contexts'] == 73 and len(adapter['cases']) == 15, 'Managed aggregate15/73 differs')
        total = 0
        for item in adapter['cases']:
            receipt = read(dest / 'adapter-evidence' / item['receipt'])
            need(receipt['passed'] and receipt['nonce'] == item['nonce'] and sha(dest / 'adapter-evidence' / item['receipt']) == item['receiptSha256'], 'Child raw receipt differs')
            total += len(receipt['rows'])
        need(total == 73 and all(row['collected'] for item in adapter['cases'] for row in read(dest / 'adapter-evidence' / item['receipt'])['rows']), 'Actual contexts/collection differ')
        log = (dest / 'launch.stdout').read_text() + (dest / 'launch.stderr').read_text()
        for marker in (f'FRESH_AUTHOR_SIM_NATIVE pid={pid} nonce={nonce} PhaseAcquireLoad=1 DerivedLedger=1 BatchInterval=0 InterpMode=0 InterpretCollectible=0 ReadyToRun=1', f'FRESH_AUTHOR_SIM_INITIALIZE pid={pid} nonce={nonce} hr=0', f'FRESH_AUTHOR_SIM_CREATE_DELEGATE pid={pid} nonce={nonce} hr=0', f'FRESH_AUTHOR_SIM_INVOKE pid={pid} nonce={nonce} managedExit=0', f'FRESH_AUTHOR_SIM_SHUTDOWN pid={pid} nonce={nonce} attempted=false reason=template-exit-path', f'FRESH_AUTHOR_SIM_EXIT pid={pid} nonce={nonce} managedExit=0 actualExit=0'):
            need(len(re.findall('^' + re.escape(marker) + '$', log, re.M)) == 1, 'Exact native process/configuration/exit marker missing')
        after = {'bundle': inventory(installed), 'author': inventory(plugin)}; write(dest / 'installed-after.json', after)
        need(before == after, 'Installed identities changed across execution')
        result.update(passed=True, platform='iossimulator.arm64', processId=pid, cases=15, contexts=73, installedUnchanged=True, authorCompiledAfterInstallation=True)
    except Exception:
        retire_owned(out, dest, 'error')
        raise
    finally:
        result['endedUtc'] = utc(); write(dest / 'results.json', result)
        print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('build', 'install', 'run', 'cleanup'))
    parser.add_argument('--output', type=Path, required=True)
    for name in ('runtime', 'build-receipt', 'framework-manifest', 'baseline-app', 'device-host', 'authors'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--device-type', default='com.apple.CoreSimulator.SimDeviceType.iPhone-16')
    parser.add_argument('--sim-runtime', default='com.apple.CoreSimulator.SimRuntime.iOS-27-0')
    parser.add_argument('--timeout', type=int, default=900)
    args = parser.parse_args()
    if args.phase == 'build':
        for name in ('runtime', 'build_receipt', 'framework_manifest', 'baseline_app', 'device_host'):
            if getattr(args, name) is None:
                parser.error('--' + name.replace('_', '-') + ' required')
        build(args)
    elif args.phase == 'install':
        install(args)
    elif args.phase == 'cleanup':
        cleanup(args)
    else:
        need(args.authors is not None, '--authors required for run'); execute(args)


if __name__ == '__main__':
    main()

