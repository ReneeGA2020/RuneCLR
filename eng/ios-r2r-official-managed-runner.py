#!/usr/bin/env python3
"""Package official generated managed entrypoints using the private simulator host."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import uuid

COMMIT = '8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d'
NATIVE = 'e97efd27370d02b6767bbaa1e4cb968f92fa3341d53e345626ff6f8498f572d8'
PROJECTS = {
    'GenericVirtualMethod': ('GenericVirtualMethod', 'GenericVirtualMethodUnloading__CallGenericVirtualMethodAcrossUnloads', 'DerivedMachine:* Machine:*'),
    'CollectibleStatics': ('Statics', 'Program__TestEntryPoint', 'StaticTest:*'),
    'ResolvedFromDifferentContext': ('ResolvedFromDifferentContext', 'Test__TestEntryPoint', 'TestClass.Class:*'),
    'ByRefLocals': ('ByRefLocals', 'Program__TestEntryPoint', 'SpanAccessor:*'),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def capture(command):
    return subprocess.check_output([str(x) for x in command], text=True).strip()


def logged(command, log, timeout=180, env=None, check=True):
    with Path(log).open('w') as stream:
        try:
            status = subprocess.run([str(x) for x in command], stdout=stream, stderr=subprocess.STDOUT, timeout=timeout, env=env).returncode
        except subprocess.TimeoutExpired:
            stream.write('\nOFFICIAL_RUNNER_TIMEOUT\n')
            status = 124
    if check and status != 0:
        raise RuntimeError('Command failed: ' + str(log))
    return status


def module(path):
    spec = importlib.util.spec_from_file_location('ios_helper', path)
    result = importlib.util.module_from_spec(spec)
    old = sys.argv
    try:
        sys.argv = [str(path)]
        spec.loader.exec_module(result)
    finally:
        sys.argv = old
    return result


def package(root, out, target):
    lane = out / ('apps-' + target)
    lane.mkdir(exist_ok=False)
    baseline = root / 'preview6-experiment/pinned-debug-harness'
    checkout = out / 'runtime'
    native = root / 'ios-r2r-clean-debug-20261012/runtime/artifacts/bin/coreclr/iossimulator.arm64.Debug/libcoreclr.dylib'
    if sha(native) != NATIVE or capture(['git', '-C', checkout, 'rev-parse', 'HEAD']) != COMMIT:
        raise RuntimeError('Unexpected source/native candidate')
    helper = module(root / 'ios-r2r-patched-regressions-20261012/verify-ios-packages.py')
    crossgen = checkout / 'artifacts/bin/coreclr/iossimulator.arm64.Debug/arm64/crossgen2/crossgen2'
    assemblies = checkout / ('artifacts/tests/coreclr/' + target + '.arm64.Debug/Loader/CollectibleAssemblies')
    generated = checkout / ('artifacts/tests/coreclr/obj/' + target + '.arm64.Debug/Managed/Loader/CollectibleAssemblies')
    records = {}
    for name, (folder, symbol, dump) in PROJECTS.items():
        dest = lane / name
        dest.mkdir()
        app = dest / 'Official.app'
        shutil.copytree(baseline / 'app/RuneCLRPinnedHarness.app', app)
        source = assemblies / folder / name
        shutil.copytree(source, dest / 'original-input')
        runners = list((generated / folder / name).rglob('SimpleRunner.g.cs'))
        if len(runners) != 1:
            raise RuntimeError('Missing unique official generated entrypoint: ' + name)
        shutil.copy2(runners[0], dest / 'SimpleRunner.g.cs')
        shutil.copytree(checkout / 'src/tests/Loader/CollectibleAssemblies' / folder, dest / 'official-source')
        for entry in source.iterdir():
            if entry.is_dir():
                shutil.copytree(entry, app / entry.name, dirs_exist_ok=True)
            elif entry.suffix == '.dll':
                shutil.copy2(entry, app / entry.name)
        for entry in (checkout / 'artifacts/TargetingPack').glob('*.dll'):
            if entry.name.startswith(('xunit.', 'Microsoft.DotNet.XUnit')):
                shutil.copy2(entry, app / entry.name)
        shared = [dest / 'original-input' / (name + '.dll')]
        for contract in ['Accessor.dll', 'SpanAccessor.dll']:
            if (app / contract).exists():
                shared.append(dest / 'original-input' / contract)
        inputs = {str(p.relative_to(app)): sha(p) for p in app.rglob('*.dll')}
        options = ['--targetos:iossimulator', '--targetarch:arm64', '--obj-format:macho', '--composite', '--inputbubble', '--resilient', '--optimize', '--parallelism:2', '--out:' + str(app / 'official.dylib')]
        options += ['-r:' + str(p) for p in app.glob('*.dll') if p.name not in {x.name for x in shared}] + [str(p) for p in shared]
        rsp = dest / 'crossgen.rsp'
        rsp.write_text('\n'.join(helper.rsp_argument(x) for x in options) + '\n')
        logged([crossgen, '@' + str(rsp)], dest / 'crossgen.log')
        shutil.copy2(app / 'official.dylib', dest / 'official.o')
        logged(['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator', '-dynamiclib', dest / 'official.o', '-Wl,-install_name,@rpath/official.dylib', '-o', app / 'official.dylib'], dest / 'link.log')
        for filename in ['main.m', 'util.h', 'coreclrhost.h', 'host_runtime_contract.h']:
            shutil.copy2(baseline / filename, dest / filename)
        wrapper = (baseline / 'runtime.m').read_text().replace('HarnessBridge.dll', name + '.dll')
        wrapper = wrapper.replace('RuneCLR.TestMaps.CounterMap:OnTick RuneCLR.LateMap.LateMap:*', dump)
        (dest / 'runtime.m').write_text(wrapper)
        shutil.copy2(native, app / 'libcoreclr.dylib')
        plist = plistlib.loads((app / 'Info.plist').read_bytes())
        bundle = 'org.runeclr.official.' + uuid.uuid4().hex[:12]
        plist.update(CFBundleExecutable='Official', CFBundleName='Official', CFBundleIdentifier=bundle)
        (app / 'Info.plist').write_bytes(plistlib.dumps(plist))
        logged(['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator', '-fobjc-arc', '-DINVARIANT_GLOBALIZATION=1', '-I' + str(dest), dest / 'main.m', dest / 'runtime.m', '-L' + str(app), '-lcoreclr', '-framework', 'UIKit', '-framework', 'Foundation', '-Wl,-rpath,@executable_path', '-o', app / 'Official'], dest / 'native-build.log')
        logged(['nm', '-n', app / 'official.dylib'], dest / 'symbols.log')
        for library in app.glob('*.dylib'):
            logged(['codesign', '--force', '--sign', '-', library], dest / (library.name + '-sign.log'))
        logged(['codesign', '--force', '--sign', '-', app], dest / 'app-sign.log')
        if helper.macho_sections(native) != helper.macho_sections(app / 'libcoreclr.dylib'):
            raise RuntimeError('Signed candidate native code/data differs')
        symbol_present = symbol in (dest / 'symbols.log').read_text()
        if not symbol_present:
            raise RuntimeError('Native upstream test method symbol missing: ' + name)
        generated_text = runners[0].read_text(encoding='utf-8-sig')
        records[name] = {'app': str(app), 'bundle': bundle, 'sourceTargetOS': target, 'nativeInput': NATIVE,
            'signedNative': sha(app / 'libcoreclr.dylib'), 'generatedMainSha256': sha(runners[0]),
            'generatedFalseCondition': '&& (false)' in generated_text, 'nativeSymbol': symbol,
            'inputHashes': inputs, 'packagedHashes': {str(p.relative_to(app)): sha(p) for p in app.rglob('*.dll')},
            'compositeSha256': sha(app / 'official.dylib')}
        write(lane / 'state.json', records)
        print('PACKAGED unchanged official Main ' + name + ' target=' + target, flush=True)


def run(root, out, target):
    lane = out / ('apps-' + target)
    state = json.loads((lane / 'state.json').read_text())
    logs = lane / 'run-logs'
    logs.mkdir(exist_ok=False)
    sim = capture(['xcrun', 'simctl', 'create', 'RuneCLR-Official-' + uuid.uuid4().hex[:8], 'com.apple.CoreSimulator.SimDeviceType.iPhone-17', 'com.apple.CoreSimulator.SimRuntime.iOS-27-0'])
    write(lane / 'simulator.json', {'uuid': sim, 'shutdown': False})
    results = {}
    try:
        logged(['xcrun', 'simctl', 'boot', sim], logs / 'boot.log')
        logged(['xcrun', 'simctl', 'bootstatus', sim, '-b'], logs / 'bootstatus.log')
        for name, item in state.items():
            env = dict(os.environ)
            for key in list(env):
                if key.startswith(('SIMCTL_CHILD_DOTNET_', 'SIMCTL_CHILD_COMPlus_')):
                    del env[key]
            logged(['xcrun', 'simctl', 'install', sim, item['app']], logs / (name + '-install.log'))
            log = logs / (name + '.log')
            status = logged(['xcrun', 'simctl', 'launch', '--console', sim, item['bundle']], log, timeout=120, env=env, check=False)
            text = log.read_text(errors='replace')
            prefixes = {'GenericVirtualMethod': '.DerivedMachine:', 'CollectibleStatics': '.StaticTest:', 'ResolvedFromDifferentContext': '.TestClass.Class:', 'ByRefLocals': '.SpanAccessor:'}
            dumps = len(re.findall(r'(?m)^Compiled method: ' + re.escape(prefixes[name]) + r'.*$', text))
            exit100 = 'CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=100' in text
            results[name] = {'launcherExit': status, 'managedExit100': exit100, 'payloadDumps': dumps,
                'passedWithExecutionEvidence': exit100 and dumps > 0 and 'Assert failure' not in text and not item['generatedFalseCondition'],
                'nativeFault': 'Got a SIGSEGV' in text, 'logSha256': sha(log)}
            write(lane / 'results.json', results)
            print(name + ': ' + json.dumps(results[name]), flush=True)
            logged(['xcrun', 'simctl', 'terminate', sim, item['bundle']], logs / (name + '-terminate.log'), check=False)
    finally:
        shutdown = logged(['xcrun', 'simctl', 'shutdown', sim], logs / 'shutdown.log', check=False)
        write(lane / 'simulator.json', {'uuid': sim, 'shutdown': shutdown == 0})
    print('EXECUTED official managed entrypoints; inspect execution evidence, not exit alone', flush=True)


def archive(root, out, target):
    path = out / ('official-managed-evidence-' + target + '.tar.gz')
    with tarfile.open(path, 'w:gz') as tar:
        for entry in out.iterdir():
            if entry.is_file() and entry.suffix == '.json':
                tar.add(entry, arcname=entry.name)
        for name in ['logs', 'source-evidence', 'iossimulator-generated']:
            tar.add(out / name, arcname=name)
        for name in ['ios-r2r-official-patched-tests-20261012.py', 'ios-r2r-official-patched-tests-20261012.first.py', 'ios-r2r-official-patched-tests-20261012.retry1.py', 'ios-r2r-official-patched-tests-20261012.retry2.py']:
            snapshot = root / name
            if snapshot.exists():
                tar.add(snapshot, arcname='driver-snapshots/' + name)
        failed = out / 'failed-inplace-apps-ios/GenericVirtualMethod/crossgen.log'
        if failed.exists():
            tar.add(failed, arcname='failed-inplace-crossgen.log')
        for lane in out.glob('apps-*'):
            for entry in lane.rglob('*'):
                if entry.is_file() and not any(p.endswith('.app') for p in entry.relative_to(lane).parts) and entry.suffix != '.o':
                    tar.add(entry, arcname=str(entry.relative_to(out)))
        tar.add(Path(__file__), arcname='managed-driver.py')
    print(json.dumps({'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}), flush=True)


def verify(root, out, target, test_commit=None):
    lane = out / ('apps-' + target)
    state = json.loads((lane / 'state.json').read_text())
    results = json.loads((lane / 'results.json').read_text())
    helper = module(root / 'ios-r2r-patched-regressions-20261012/verify-ios-packages.py')
    candidate = root / 'ios-r2r-clean-debug-20261012/runtime'
    native = candidate / 'artifacts/bin/coreclr/iossimulator.arm64.Debug/libcoreclr.dylib'
    checks = {}
    for name, item in state.items():
        app = Path(item['app'])
        dest = lane / name
        text = (lane / 'run-logs' / (name + '.log')).read_text(errors='replace')
        checks[name + '-actual-execution'] = results[name]['passedWithExecutionEvidence']
        methods = re.findall(r'(?m)^Compiled method: (.*)$', text)
        if name == 'GenericVirtualMethod':
            checks[name + '-ten-generic-bodies'] = methods.count('.DerivedMachine:Construct[System.__Canon]()') == 10
        elif name == 'CollectibleStatics':
            checks[name + '-static-bodies'] = all(sum(m.startswith('.StaticTest:' + method + '(') for m in methods) == 1 for method in ['SetStatic', 'GetStatic', 'SetStaticObject', 'GetStaticObject'])
        elif name == 'ResolvedFromDifferentContext':
            checks[name + '-two-positive-scenarios'] = methods.count('.TestClass.Class:MainTest()') == 2
        else:
            checks[name + '-byref-body-and-loop'] = methods.count('.SpanAccessor:GetSpan()') == 1 and len(re.findall(r'(?m)^.*Official\[\d+:\d+\] 1$', text)) == 20
            checks[name + '-emitted-method'] = 'Interpreter compile method GetSpanType:GetSpan()' in text
        checks[name + '-log-identity'] = sha(lane / 'run-logs' / (name + '.log')) == results[name]['logSha256']
        checks[name + '-generated-main'] = sha(dest / 'SimpleRunner.g.cs') == item['generatedMainSha256']
        checks[name + '-native-caller'] = item['nativeSymbol'] in (dest / 'symbols.log').read_text()
        method = 'GenericVirtualMethodUnloading:CallGenericVirtualMethodAcrossUnloads' if name == 'GenericVirtualMethod' else 'Test:TestEntryPoint' if name == 'ResolvedFromDifferentContext' else 'Program:TestEntryPoint'
        checks[name + '-native-caller'] = checks[name + '-native-caller'] and ('Interpreter compile method ' + method not in text)
        checks[name + '-signed-native'] = sha(app / 'libcoreclr.dylib') == item['signedNative'] and helper.macho_sections(native) == helper.macho_sections(app / 'libcoreclr.dylib')
        checks[name + '-packaged-inputs'] = all(sha(app / p) == digest for p, digest in item['packagedHashes'].items())
        checks[name + '-composite'] = sha(app / 'official.dylib') == item['compositeSha256'] and helper.il_layout(app / (name + '.dll'))['managedNativeRva'] > 0
        source = out / 'runtime/src/tests/Loader/CollectibleAssemblies' / PROJECTS[name][0]
        checks[name + '-official-source'] = all(sha(source / p.relative_to(dest / 'official-source')) == sha(p) for p in (dest / 'official-source').rglob('*') if p.is_file())
    simulator = json.loads((lane / 'simulator.json').read_text())
    devices = json.loads(capture(['xcrun', 'simctl', 'list', 'devices', '-j']))['devices']
    own = [d for group in devices.values() for d in group if d['udid'] == simulator['uuid']]
    checks['simulator-shutdown'] = simulator['shutdown'] and len(own) == 1 and own[0]['state'] == 'Shutdown'
    checks['clean-debug-native'] = sha(native) == NATIVE
    for label, checkout in [('candidate', candidate), ('test-source', out / 'runtime')]:
        expected = test_commit if label == 'test-source' and test_commit is not None else COMMIT
        checks[label + '-source'] = capture(['git', '-C', checkout, 'rev-parse', 'HEAD']) == expected and not capture(['git', '-C', checkout, 'status', '--porcelain', '--untracked-files=no'])
    success = len(results) == 4 and all(checks.values())
    write(lane / 'verified.json', {'success': success, 'checks': checks, 'results': results})
    if not success:
        raise RuntimeError('Official managed verification failed: ' + ', '.join(k for k, ok in checks.items() if not ok))
    print('PASS 4/4 official generated managed entrypoints on patched Debug ARM64 iOS simulator; actual payload IR, native hosts, unchanged source/input identities and simulator shutdown verified', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['package', 'run', 'verify', 'archive'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target-os', choices=['ios', 'iossimulator'], default='ios')
    args = parser.parse_args()
    globals()[args.phase](args.root.resolve(), args.output.resolve(), args.target_os)


if __name__ == '__main__':
    main()
