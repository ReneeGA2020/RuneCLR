#!/usr/bin/env python3
"""Build and run the opt-in 16/74 pumped adapter on a private ARM64 simulator."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import uuid

COMMIT = '3126bbc9a8851a09ac6435b18a12882bad48f3ee'
TREE = '710936ae1729a5689ab0e0896f3cf722ddd3d31c'
SCENE = 'dad906720793ac28271f3c81f3ae5532100005bb3a9842dfc2987fb81dad09af'
HELPERS = {'ios-fresh-author-simulator-continuation.py': '53105c1f8f8321fbb7b4ae309e125f0fb30221abc62fd6eed598850afcbbda5e',
           'ios-device-application-build.py': 'c86af795e75cc810ac949a3ff31269465cd7f34665f798f5c1c168a866c5c15d'}
TRUSTED = ('RuneCLR.Abstractions', 'RuneCLR.Packages', 'RuneCLR.Runtime', 'MobileHostBudgetProbe', 'SessionBridge')
CASES = ('Normal', 'EndlessTick', 'StartLoop', 'CatchResume', 'BroadCatchResume', 'SignalFilter',
         'FilterExhaustion', 'ConstructorLoop', 'StaticConstructorLoop', 'FiniteCleanup', 'InfiniteCleanup',
         'StopLoop', 'MaliciousMessage', 'ExplicitCanceled', 'Recovery', 'TickWork')
USINGS = 'global using global::System; global using global::System.Collections.Generic; global using global::System.IO; global using global::System.Linq; global using global::System.Net.Http; global using global::System.Threading; global using global::System.Threading.Tasks;\n'
BRIDGE = '''using System;
public static class SessionBridge { public static int Run() {
 var d=Environment.GetEnvironmentVariable("RUNECLR_DOCUMENTS")??throw new InvalidOperationException();
 var n=Environment.GetEnvironmentVariable("RUNECLR_BUDGET_NONCE")??throw new InvalidOperationException();
 return MobileHostBudgetProbe.Entry.Run(new[]{d+"/budget-plugin",d+"/budget-evidence-"+n,n,"all","--pumped"});
}}
'''


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x', encoding='ascii') as stream:
        json.dump(value, stream, indent=2)
        stream.write(chr(10))


def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(Path(root).rglob('*')) if p.is_file()}


def load(name):
    path = Path(__file__).with_name(name)
    need(sha(path) == HELPERS[name], 'Frozen helper changed: ' + name)
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def capture(argv):
    return subprocess.check_output(list(map(str, argv)), text=True).strip()


def clean_env():
    return {k: v for k, v in os.environ.items() if not k.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_', 'DYLD_', 'SIMCTL_CHILD_'))}


def compile_one(helper, out, runtime, name, paths, references):
    compiler = runtime / '.dotnet/sdk/11.0.100-rc.1.26420.103/Roslyn/bincore/csc.dll'
    target = out / 'input' / (name + '.dll')
    rsp = out / (name + '.rsp')
    argv = ['-nologo', '-nostdlib+', '-nullable:enable', '-warnaserror+', '-langversion:preview',
            '-optimize+', '-deterministic+', '-target:library', '-out:' + str(target)]
    argv += ['-r:' + str(p) for p in references] + list(map(str, paths)) + [str(out / 'GlobalUsings.cs')]
    rsp.write_text(chr(10).join(argv) + chr(10), encoding='ascii')
    helper.stage(out, 'compile-' + name, [runtime / '.dotnet/dotnet', compiler, '-noconfig', '@' + str(rsp)], clean_env(), 180)
    return target


def build(args, helper, pe):
    out, scene, runtime, source = args.output.resolve(), args.scene.resolve(), args.runtime.resolve(), args.source.resolve()
    need(sys.platform == 'darwin' and not out.exists(), 'Configured Mac and fresh output required')
    need(sha(scene / 'state.json') == SCENE, 'Accepted immutable scene identity differs')
    state = read(scene / 'state.json')
    need(inventory(Path(state['app'])) == state['bundleHashes'], 'Accepted signed scene bundle changed')
    need(capture(['git', '-C', runtime, 'rev-parse', 'HEAD']) == COMMIT and capture(['git', '-C', runtime, 'rev-parse', 'HEAD^{tree}']) == TREE, 'Native source identity differs')
    need(not capture(['git', '-C', runtime, 'status', '--porcelain', '--untracked-files=no']), 'Tracked native source dirty')
    receipt = read(scene / 'matching-build.json')
    need(receipt['success'] and receipt['commit'] == COMMIT and receipt['target'] == 'iossimulator.arm64', 'Matching Release receipt required')
    product = runtime / 'artifacts/bin/coreclr/iossimulator.arm64.Release'
    for relative, key in (('libcoreclr.dylib', 'nativeSha256'), ('IL/System.Private.CoreLib.dll', 'corelibSha256'), ('arm64/crossgen2/crossgen2', 'crossgen2Sha256')):
        need(sha(product / relative) == receipt[key], 'Matching runtime binary differs: ' + relative)
    sources = read(source / 'source-manifest.json')
    need(all(sha(source / name) == digest for name, digest in sources.items()), 'Transferred host source differs')
    out.mkdir(); (out / 'input').mkdir(); (out / 'source').mkdir()
    for name in sources:
        dest = out / 'source' / name; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source / name, dest)
    write(out / 'source-manifest.json', sources)
    shutil.copyfile(Path(__file__), out / 'driver.py')
    shutil.copyfile(scene / 'matching-build.json', out / 'matching-build.json')
    (out / 'GlobalUsings.cs').write_text(USINGS, encoding='ascii')
    (out / 'SessionBridge.cs').write_text(BRIDGE, encoding='ascii')
    raw = read(scene / 'state.json')['rawInputHashes']
    for name, digest in raw.items():
        need(sha(scene / 'input' / name) == digest, 'Accepted raw framework changed: ' + name)
        if name not in [n + '.dll' for n in TRUSTED]:
            shutil.copyfile(scene / 'input' / name, out / 'input' / name)
    refs = sorted((out / 'input').glob('*.dll'))
    compiler = runtime / '.dotnet/sdk/11.0.100-rc.1.26420.103/Roslyn/bincore/csc.dll'
    write(out / 'request.json', {'schema': 'runeclr.ios-pumped-budget.application.v1', 'startedUtc': helper.utc(), 'driverSha256': sha(__file__),
          'sourceCommit': COMMIT, 'sourceTree': TREE, 'sceneStateSha256': SCENE, 'nativeSha256': receipt['nativeSha256'],
          'compilerSha256': sha(compiler), 'sdkHostSha256': sha(runtime / '.dotnet/dotnet'), 'sourceHashes': sources,
          'frameworkInputHashes': inventory(out / 'input'), 'configuration': pe.PROFILE, 'physicalDeviceExecuted': False,
          'runtimeRebuilt': False, 'trustedHostRecompiled': True, 'expectedCases': CASES, 'expectedContexts': 74})
    def cs(root):
        return sorted((out / 'source' / root).glob('*.cs'))
    abstraction = compile_one(helper, out, runtime, TRUSTED[0], cs('src/RuneCLR.Abstractions'), refs)
    packages = compile_one(helper, out, runtime, TRUSTED[1], cs('src/RuneCLR.Packages'), refs)
    host = compile_one(helper, out, runtime, TRUSTED[2], cs('src/RuneCLR.Runtime'), refs + [abstraction, packages])
    adapter = compile_one(helper, out, runtime, TRUSTED[3], cs('eng/mobile-host-budget-probe') + cs('eng/host-budget-probe/Host') + cs('eng/windows-entry-observation'), refs + [abstraction, packages, host])
    compile_one(helper, out, runtime, TRUSTED[4], [out / 'SessionBridge.cs'], refs + [adapter])
    app = out / 'app/Session.app'; app.mkdir(parents=True)
    for path in (scene / 'unsigned-native').glob('*.dylib'):
        if path.name != 'framework.dylib':
            shutil.copyfile(path, app / path.name)
    need(sha(app / 'libcoreclr.dylib') == receipt['nativeSha256'], 'Actual unsigned runtime changed')
    shutil.copyfile(Path(state['app']) / 'Microsoft.NETCore.App.deps.json', app / 'Microsoft.NETCore.App.deps.json')
    plist = plistlib.loads((Path(state['app']) / 'Info.plist').read_bytes())
    bundle = 'org.runeclr.pumpedbudget.' + uuid.uuid4().hex[:12]
    plist.update(CFBundleIdentifier=bundle)
    (app / 'Info.plist').write_bytes(plistlib.dumps(plist))
    for name in ('main.m', 'runtime.m', 'util.m', 'util.h', 'runtime.h', 'coreclrhost.h', 'host_runtime_contract.h'):
        shutil.copyfile(scene / name, out / name)
    rsp = out / 'crossgen.rsp'
    rsp.write_text(chr(10).join(['--targetos:iossimulator', '--targetarch:arm64', '--obj-format:macho', '--composite', '--inputbubble', '--parallelism:2', '--resilient', '--optimize', '--out:' + str(app / 'framework.dylib'), *map(str, sorted((out / 'input').glob('*.dll')))]) + chr(10), encoding='ascii')
    before = inventory(out / 'input')
    helper.stage(out, 'crossgen', [product / 'arm64/crossgen2/crossgen2', '@' + str(rsp)], clean_env(), 1200)
    shutil.copyfile(app / 'framework.dylib', out / 'framework.o')
    helper.stage(out, 'composite-link', ['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator', '-dynamiclib', out / 'framework.o', '-Wl,-install_name,@rpath/framework.dylib', '-o', app / 'framework.dylib'], clean_env())
    helper.stage(out, 'wrapper', ['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator', '-fobjc-arc', '-DINVARIANT_GLOBALIZATION=1', '-I' + str(out), out / 'main.m', out / 'runtime.m', out / 'util.m', '-L' + str(app), '-lcoreclr', '-framework', 'UIKit', '-framework', 'Foundation', '-Wl,-rpath,@executable_path', '-o', app / 'Session'], clean_env())
    components = {}
    for name in before:
        original, compiled = pe.managed(out / 'input' / name), pe.managed(app / name)
        need(original['managedNativeRva'] == 0 and compiled['managedNativeRva'] > 0 and original['mvid'] == compiled['mvid'], 'Trusted R2R identity differs: ' + name)
        components[name] = {'raw': original, 'component': compiled}
    need(not list(app.rglob('HostBudgetProbe.*.dll')), 'Author entered application composite')
    for path in sorted(app.glob('*.dylib')):
        helper.native(path, 6)
        helper.stage(out, 'sign-' + path.stem, ['codesign', '--force', '--sign', '-', path], clean_env(), 120)
    helper.native(app / 'Session', 2)
    helper.stage(out, 'sign-app', ['codesign', '--force', '--sign', '-', app], clean_env(), 120)
    helper.stage(out, 'sign-verify', ['codesign', '--verify', '--strict', app], clean_env(), 120)
    need(inventory(out / 'input') == before and inventory(Path(state['app'])) == state['bundleHashes'], 'Immutable build inputs changed')
    need(all(sha(out / 'source' / n) == h for n, h in sources.items()), 'Host source changed during build')
    write(out / 'state.json', {'app': str(app), 'bundleId': bundle, 'bundleHashes': inventory(app), 'rawInputHashes': before, 'components': components, 'sourceHashes': sources, 'configuration': pe.PROFILE})
    write(out / 'build-results.json', {'passed': True, 'managedComponents': len(components), 'runtimeRebuilt': False, 'trustedHostRecompiled': True, 'authorBundled': False, 'physicalDeviceExecuted': False, 'nativeEntryProof': False, 'endedUtc': helper.utc()})


def run(args, helper, pe):
    out, runtime = args.output.resolve(), args.runtime.resolve()
    state = read(out / 'state.json'); need(inventory(Path(state['app'])) == state['bundleHashes'], 'Signed application changed')
    if args.resume_installed:
        # Preserve a failed receipt writer and re-read the already installed app.
        helper.verify_state(out)
        need((out / 'installation/error.json').exists() and not (out / 'installation/results.json').exists(), 'Only a failed unreceipted installation can resume')
        owned = read(out / 'owned-simulator.json'); original = read(out / 'installation/installed-before-copy.json')
        need(read(out / 'installation/install.result.json')['exitCode'] == 0, 'Original installation did not succeed')
        resumed = out / 'installation/resume'; resumed.mkdir()
        helper.stage(resumed, 'boot', ['xcrun', 'simctl', 'boot', owned['id']], clean_env(), 120)
        helper.stage(resumed, 'bootstatus', ['xcrun', 'simctl', 'bootstatus', owned['id'], '-b'], clean_env(), 180)
        installed = Path(capture(['xcrun', 'simctl', 'get_app_container', owned['id'], state['bundleId'], 'app']))
        data = Path(capture(['xcrun', 'simctl', 'get_app_container', owned['id'], state['bundleId'], 'data']))
        need(str(installed) == original['appPath'] and str(data) == original['dataPath'] and inventory(installed) == state['bundleHashes'], 'Already installed application identity differs')
        need(not (data / 'Documents/budget-plugin').exists(), 'Author was already transferred')
        write(out / 'installation/results.json', {'passed': True, 'resumedExistingInstallation': True, 'driverSha256': sha(__file__), 'buildDriverSha256': sha(out / 'driver.py'), 'simulator': owned['id'], 'bundleId': state['bundleId'], 'installedApp': str(installed), 'dataContainer': str(data), 'readbackUtc': helper.utc(), 'installResultSha256': sha(out / 'installation/install.result.json'), 'stateSha256': sha(out / 'state.json'), 'physicalDeviceInstalled': False})
    else:
        helper.install(args)
    install = read(out / 'installation/results.json')
    authors = out / 'authors'; authors.mkdir(); (authors / 'input').mkdir()
    shutil.copyfile(out / 'GlobalUsings.cs', authors / 'GlobalUsings.cs')
    refs = sorted((out / 'input').glob('*.dll'))
    def cs(root):
        return sorted((out / 'source' / root).glob('*.cs'))
    started = helper.utc()
    private = compile_one(helper, authors, runtime, 'HostBudgetProbe.Private', cs('eng/host-budget-probe/Private'), refs)
    payload = compile_one(helper, authors, runtime, 'HostBudgetProbe.Payload', cs('eng/host-budget-probe/Payload'), refs + [private])
    author_hashes = inventory(authors / 'input')
    need(all(pe.managed(p)['managedNativeRva'] == 0 for p in (private, payload)), 'Fresh author native body found')
    write(authors / 'results.json', {'passed': True, 'authorCompilationCount': 2, 'startedUtc': started, 'endedUtc': helper.utc(), 'afterInstallReadbackUtc': install['readbackUtc'], 'authorHashes': author_hashes})
    data = Path(install['dataContainer']); plugin = data / 'Documents/budget-plugin'
    need(not plugin.exists(), 'Author destination already exists')
    shutil.copytree(authors / 'input', plugin)
    need(inventory(plugin) == author_hashes, 'Transferred fresh author bytes differ')
    dest = out / 'run-all'; dest.mkdir(); nonce = uuid.uuid4().hex
    env = clean_env(); env['SIMCTL_CHILD_RUNECLR_BUDGET_NONCE'] = nonce
    before = {'bundle': inventory(Path(install['installedApp'])), 'author': inventory(plugin)}
    write(dest / 'installed-before.json', before)
    write(dest / 'request.json', {'nonce': nonce, 'driverSha256': sha(__file__), 'buildDriverSha256': sha(out / 'driver.py'), 'simulator': install['simulator'], 'bundleId': state['bundleId'], 'configuration': state['configuration'], 'debugger': False, 'physicalDeviceExecuted': False, 'startedUtc': helper.utc()})
    result = {'passed': False, 'physicalDeviceExecuted': False, 'nativeEntryProof': False, 'nonce': nonce}
    try:
        helper.stage(dest, 'launch', ['xcrun', 'simctl', 'launch', '--console', install['simulator'], state['bundleId']], env, 900, lambda: helper.retire_owned(out, dest, 'timeout'))
        shutil.copytree(data / 'Documents' / ('budget-evidence-' + nonce), dest / 'adapter-evidence')
        adapter = read(dest / 'adapter-evidence/result.json'); pid = adapter['processId']
        need(adapter['passed'] and adapter['nonce'] == nonce and adapter['contexts'] == 74 and tuple(x['scenario'] for x in adapter['cases']) == CASES, 'Actual 16/74 aggregate differs')
        total = 0
        for item in adapter['cases']:
            path = dest / 'adapter-evidence' / item['receipt']; receipt = read(path)
            need(sha(path) == item['receiptSha256'] and receipt['passed'] and receipt['nonce'] == item['nonce'], 'Child receipt identity differs')
            for row in receipt['rows']:
                need(row['collected'] and row['pumped'] and row['retainedStoppedSessionCollected'] and row['successfulHostReturns'] == row['report']['CompletedTicks'], 'Pumped callback/retention result differs')
            total += len(receipt['rows'])
        need(total == 74, 'Collected context count differs')
        tick = read(dest / 'adapter-evidence/TickWork/result.json')['rows'][0]
        need(tick['successfulHostReturns'] >= 2 and tick['successfulHostReturns'] < 64, 'Cumulative budget did not stop across host returns')
        log = (dest / 'launch.stdout').read_text() + (dest / 'launch.stderr').read_text()
        markers = (f'FRESH_AUTHOR_SIM_NATIVE pid={pid} nonce={nonce} PhaseAcquireLoad=1 DerivedLedger=1 BatchInterval=0 InterpMode=0 InterpretCollectible=0 ReadyToRun=1', f'FRESH_AUTHOR_SIM_INITIALIZE pid={pid} nonce={nonce} hr=0', f'FRESH_AUTHOR_SIM_CREATE_DELEGATE pid={pid} nonce={nonce} hr=0', f'FRESH_AUTHOR_SIM_INVOKE pid={pid} nonce={nonce} managedExit=0', f'FRESH_AUTHOR_SIM_SHUTDOWN pid={pid} nonce={nonce} attempted=false reason=template-exit-path', f'FRESH_AUTHOR_SIM_EXIT pid={pid} nonce={nonce} managedExit=0 actualExit=0')
        need(all(helper.exact_marker(log, marker, pid) for marker in markers), 'Native PID/configuration/exit marker differs')
        after = {'bundle': inventory(Path(install['installedApp'])), 'author': inventory(plugin)}
        write(dest / 'installed-after.json', after)
        need(before == after, 'Installed author or application changed')
        result.update(passed=True, platform='iossimulator.arm64', processId=pid, cases=16, contexts=74, successfulTickWorkReturns=tick['successfulHostReturns'], authorCompiledAfterInstallation=True, installedUnchanged=True)
    except Exception as error:
        result['error'] = str(error)
        helper.retire_owned(out, dest, 'error')
        raise
    finally:
        result['endedUtc'] = helper.utc(); write(dest / 'results.json', result); print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('build', 'run', 'cleanup'))
    for name in ('output', 'runtime', 'scene', 'source'):
        parser.add_argument('--' + name, type=Path, required=name in ('output', 'runtime'))
    parser.add_argument('--device-type', default='com.apple.CoreSimulator.SimDeviceType.iPhone-16')
    parser.add_argument('--sim-runtime', default='com.apple.CoreSimulator.SimRuntime.iOS-27-0')
    parser.add_argument('--resume-installed', action='store_true', help='Resume only a failed receipt writer after successful app installation')
    args = parser.parse_args(); helper = load('ios-fresh-author-simulator-continuation.py'); pe = load('ios-device-application-build.py')
    if args.phase == 'build':
        need(args.source and args.scene, 'Build requires --source and --scene'); build(args, helper, pe)
    elif args.phase == 'run':
        run(args, helper, pe)
    else:
        helper.cleanup(args)


if __name__ == '__main__':
    main()
