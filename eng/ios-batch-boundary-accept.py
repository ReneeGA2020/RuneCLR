#!/usr/bin/env python3
"""Build and run the five single-worker batch boundary lanes on an iOS simulator."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import time
import uuid

COMMIT = '3126bbc9a8851a09ac6435b18a12882bad48f3ee'
TREE = '710936ae1729a5689ab0e0896f3cf722ddd3d31c'
PROOF_SHA = '29d83ae68ca57ec2067261d15a901e81f8422981609f1fe6aaad5cb37879de5e'
PARENT_SHA = 'cfe2ab27a62e84cbc3b181f40b582d1cb90ab6c93a8323f2de49d2ec5c1cc8a7'
REVIEW_SHA = '9aab8cae277ad138b6635b9db61bf30bcfa942ce14aa54c56df71e6bb683ccd2'
LANES = ((1, 1), (1, 100), (1, 1000), (100, 100), (1000, 1000))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def need(value, message):
    if not value:
        raise RuntimeError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='ascii')


def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def cap(argv):
    return subprocess.check_output([str(x) for x in argv], text=True).strip()


def run(argv, log, timeout=900, env=None):
    write(Path(str(log) + '.command.json'), {'argv': [str(x) for x in argv], 'timeout': timeout})
    with Path(log).open('x') as stream:
        result = subprocess.run([str(x) for x in argv], stdout=stream, stderr=subprocess.STDOUT,
                                timeout=timeout, env=env)
    need(result.returncode == 0, 'Command failed; preserve ' + str(log))


def module(name, filename, expected):
    path = Path(__file__).with_name(filename)
    need(sha(path) == expected, 'Frozen helper changed: ' + filename)
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def native_platform(path):
    data = Path(path).read_bytes()
    need(len(data) >= 32 and struct.unpack_from('<II', data) == (0xfeedfacf, 0x100000c),
         'Actual native image must be thin ARM64 Mach-O.')
    need(struct.unpack_from('<I', data, 12)[0] == 6, 'Native image must be MH_DYLIB.')
    commands_end = 32 + struct.unpack_from('<I', data, 20)[0]
    need(commands_end <= len(data), 'Native load commands exceed image.')
    offset, platforms = 32, []
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        need(offset + 8 <= commands_end, 'Native load-command header exceeds declared region.')
        command, size = struct.unpack_from('<II', data, offset)
        need(size >= 8 and offset + size <= commands_end, 'Invalid native load command.')
        if command == 0x32:
            need(size >= 24, 'Invalid native build-version command.')
            platforms.append(struct.unpack_from('<I', data, offset + 8)[0])
        offset += size
    need(offset == commands_end, 'Native load-command region size differs.')
    need(platforms == [7], 'Native platform must be iOS simulator, not device or macOS.')
    return {'architecture': 'Arm64', 'platform': 'iossimulator.arm64', 'sha256': sha(path)}


def inputs(root):
    manifest = read(root / 'input-manifest.json')
    need(manifest['schema'] == 'runeclr.mobile-batch-boundary.inputs.v1' and
         manifest['configuredLanes'] == [list(x) for x in LANES] and
         manifest['expectedContexts'] == 168, 'Frozen boundary input contract differs.')
    for name, expected in manifest['files'].items():
        path = (root / name).resolve()
        need(path.is_relative_to(root.resolve()) and sha(path) == expected, 'Input changed: ' + name)
    return manifest


def wrapper(source):
    text = Path(source).read_text()
    anchor = '    char **managed_argv;'
    need(text.count(anchor) == 1 and text.count('const char* executable = "SessionBridge.dll";') == 1,
         'Unknown native wrapper entry contract.')
    text = re.sub(r'^.*(?:un)?setenv\s*\(\s*"(?:DOTNET_|COMPlus_|RUNECLR_DOCUMENTS)[^\n]*\n',
                  '', text, flags=re.M)
    text = re.sub(r'^.*printf\("(?:SESSION_NATIVE_CONFIG|MOBILE_BUDGET_NATIVE|DERIVED_LEDGER_NATIVE)[^\n]*\n',
                  '', text, flags=re.M)
    settings = '''    const char *batch_hex = getenv("RUNECLR_BATCH_HEX");
    const char *nonce = getenv("RUNECLR_BATCH_NONCE");
    const char *matrix = getenv("RUNECLR_BATCH_MATRIX");
    if (!batch_hex || !nonce || !matrix ||
        (strcmp(batch_hex, "1") && strcmp(batch_hex, "64") && strcmp(batch_hex, "3e8"))) exit(124);
    setenv("DOTNET_InterpMode", "0", 1);
    setenv("DOTNET_RuneCLRInterpretCollectible", "0", 1);
    setenv("DOTNET_ReadyToRun", "1", 1);
    setenv("DOTNET_TieredCompilation", "0", 1);
    setenv("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT", "1", 1);
    setenv("DOTNET_InterpList", "0", 1);
    unsetenv("DOTNET_InterpDump");
    setenv("DOTNET_RuneCLRPhaseAcquireLoad", "1", 1);
    setenv("DOTNET_RuneCLRDerivedLedger", "0", 1);
    setenv("DOTNET_RuneCLRBatchInterval", batch_hex, 1);
    setenv("RUNECLR_BATCH_TEST_SWITCH", "DOTNET_RuneCLRBatchInterval", 1);
    setenv("RUNECLR_DOCUMENTS", [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES)[0] UTF8String], 1);
    printf("BATCH_NATIVE pid=%d nonce=%s matrix=%s interval=%s PhaseAcquireLoad=1 DerivedLedger=0 InterpMode=0 ReadyToRun=1\\n", getpid(), nonce, matrix, batch_hex); fflush(stdout);
'''
    text = text.replace(anchor, settings + anchor)
    exit_anchor = '    res=(int)managed_exit;'
    need(text.count(exit_anchor) == 1, 'Unknown native HRESULT exit contract.')
    text = text.replace(exit_anchor, exit_anchor + '\n    if (hr != 0 && res == 0) res = 125;')
    return text


def completed(log, marker, pid):
    # iOS Console may route managed stdout through NSLog; bind its process prefix too.
    prefix = (r'(?:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3,6} '
              + re.escape('Session[' + str(pid) + ':') + r'\d+\] )?')
    return len(re.findall('^' + prefix + re.escape(marker) + '$', log, re.M)) == 1


def build(args):
    need(platform.system() == 'Darwin', 'Application build requires the configured Mac.')
    parent = module('ios_frozen_parent', 'ios-session-budget-accept.py', PARENT_SHA)
    manifest = inputs(args.inputs)
    receipt = read(args.build_receipt)
    need(receipt['success'] is True and receipt['buildExit'] == 0 and receipt['commit'] == COMMIT and
         receipt['tree'] == TREE and receipt['target'] == 'iossimulator.arm64' and
         receipt['configuration'] == 'Release' and receipt['sourceProofSha256'] == PROOF_SHA and
         receipt['nativeMeterSize'] == 72 and receipt['nativeMeterAlignment'] == 8 and
         receipt['batchIntervalOffset'] == 64, 'Matching batch runtime build required.')
    need(receipt['assessment']['staticInterpreter'] is True and
         receipt['assessment']['dynamicJitEnabled'] is False and
         receipt['assessment']['batchCompile']['passed'] is True, 'Required native compiler assessment differs.')
    runtime = args.runtime.resolve()
    need(cap(['git', '-C', runtime, 'rev-parse', 'HEAD']) == COMMIT and
         cap(['git', '-C', runtime, 'rev-parse', 'HEAD^{tree}']) == TREE and
         not cap(['git', '-C', runtime, 'status', '--porcelain', '--untracked-files=no']),
         'Live runtime source differs.')
    proof = runtime.parent / 'source-proof.json'
    need(sha(proof) == PROOF_SHA, 'Source proof differs.')
    for name, expected in read(proof)['sourceHashes'].items():
        need(sha(runtime / name) == expected, 'Live source differs: ' + name)
    product = runtime / 'artifacts/bin/coreclr/iossimulator.arm64.Release'
    native, corelib, compiler = (product / 'libcoreclr.dylib', product / 'IL/System.Private.CoreLib.dll',
                                product / 'arm64/crossgen2/crossgen2')
    for path, key in ((native, 'nativeSha256'), (corelib, 'corelibSha256'), (compiler, 'crossgen2Sha256')):
        need(sha(path) == receipt[key], 'Matching runtime product differs: ' + key)
    native_info = native_platform(native)
    baseline_state = read(args.baseline_app.parent.parent / 'state.json')
    baseline = inventory(args.baseline_app)
    need(baseline == baseline_state['bundleHashes'], 'Prior signed app changed.')
    framework = read(args.framework_manifest)
    need(args.framework_input.resolve() == Path(framework['source']).resolve(), 'Original framework IL path differs.')
    reuse = framework['inputHashes']
    need(len(reuse) > 150 and 'System.Private.CoreLib.dll' not in reuse and
         all(Path(n).name == n and n.endswith('.dll') and
             (n.startswith(('System.', 'Microsoft.')) or n in ('netstandard.dll', 'mscorlib.dll', 'WindowsBase.dll'))
             for n in reuse), 'Framework reuse inventory contains unexpected components.')
    for name, expected in reuse.items():
        need(sha(args.framework_input / name) == expected, 'Original framework IL changed: ' + name)
    frozen = {str(p.resolve()): sha(p) for p in
              (Path(__file__), args.build_receipt, args.framework_manifest, args.wrapper_source,
               args.wrapper_assets / 'main.m', native, corelib, compiler)}
    frozen.update({str(p.resolve()): sha(p) for p in args.wrapper_assets.iterdir()
                   if p.is_file() and p.suffix in ('.h', '.m')})
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / 'logs').mkdir()
    write(output / 'request.json', {'driverSha256': sha(__file__), 'buildReceiptSha256': sha(args.build_receipt),
         'inputManifestSha256': sha(args.inputs / 'input-manifest.json'), 'sourceCommit': COMMIT, 'sourceTree': TREE,
         'native': native_info, 'frameworkManifestSha256': sha(args.framework_manifest),
         'wrapperInputSha256': sha(args.wrapper_source), 'frozenInputs': frozen,
         'lanes': LANES, 'executionVerified': False})
    app = output / 'app/Session.app'
    shutil.copytree(args.baseline_app, app)
    # Rebuild every managed component so no older trusted harness survives in the TPA list.
    for path in app.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        elif path.suffix == '.dll':
            path.unlink()
    shutil.copy2(native, app / 'libcoreclr.dylib')
    fresh = output / 'input'
    fresh.mkdir()
    for name in reuse:
        shutil.copy2(args.framework_input / name, fresh / name)
    for name in ('MobileBatchBoundaryProbe.dll', 'BatchBoundary.Contract.dll'):
        shutil.copy2(args.inputs / 'host' / name, fresh / name)
    shutil.copy2(corelib, fresh / corelib.name)
    bridge = output / 'SessionBridge.cs'
    bridge.write_text('using System; using MobileBatchBoundaryProbe; public static class SessionBridge { '
        'public static int Main(string[] a) { '
        'var d=Environment.GetEnvironmentVariable("RUNECLR_DOCUMENTS") ?? throw new InvalidOperationException("documents"); '
        'var n=Environment.GetEnvironmentVariable("RUNECLR_BATCH_NONCE") ?? throw new InvalidOperationException("nonce"); '
        'var m=Environment.GetEnvironmentVariable("RUNECLR_BATCH_MATRIX") ?? throw new InvalidOperationException("matrix"); '
        'return Entry.Run(new[]{d+"/batch-plugin/BatchBoundary.Author.dll",d+"/batch-"+n+".json",m,n}); }}\n',
        encoding='ascii')
    sdk = runtime / '.dotnet/dotnet'
    csc = runtime / '.dotnet/sdk' / cap([sdk, '--version']) / 'Roslyn/bincore/csc.dll'
    refs = sorted(fresh.glob('*.dll'))
    run([sdk, csc, '-nologo', '-noconfig', '-nostdlib+', '-optimize+', '-target:exe',
         '-out:' + str(fresh / 'SessionBridge.dll'), *['-r:' + str(p) for p in refs], bridge], output / 'logs/bridge.log')
    composite = sorted(fresh.glob('*.dll'))
    rsp = output / 'crossgen.rsp'
    rsp.write_text('\n'.join(['--targetos:iossimulator', '--targetarch:arm64', '--obj-format:macho',
        '--composite', '--inputbubble', '--parallelism:2', '--resilient', '--optimize',
        '--out:' + str(app / 'framework.dylib'), *[str(p) for p in composite]]) + '\n')
    run([compiler, '@' + str(rsp)], output / 'logs/crossgen.log')
    obj = output / 'framework.o'
    shutil.copy2(app / 'framework.dylib', obj)
    run(['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator',
         '-dynamiclib', obj, '-Wl,-install_name,@rpath/framework.dylib', '-o', app / 'framework.dylib'],
        output / 'logs/composite-link.log')
    native_source = output / 'runtime.m'
    native_source.write_text(wrapper(args.wrapper_source))
    run(['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator',
         '-fobjc-arc', '-DINVARIANT_GLOBALIZATION=1', '-I' + str(args.wrapper_assets),
         args.wrapper_assets / 'main.m', native_source, '-L' + str(app), '-lcoreclr',
         '-framework', 'UIKit', '-framework', 'Foundation', '-Wl,-rpath,@executable_path',
         '-o', app / 'Session'], output / 'logs/wrapper.log')
    layouts = {p.name: parent.il_layout(p) for p in app.glob('*.dll')}
    need(set(layouts) == {p.name for p in composite} and all(x['managedNativeRva'] for x in layouts.values()),
         'Every bundled managed assembly must be a fresh R2R component.')
    need(not list(app.rglob('BatchBoundary.Author.dll')), 'Author was bundled into trusted app.')
    bid = parent.sign_app(output, app)
    need(inputs(args.inputs) == manifest and inventory(args.baseline_app) == baseline,
         'Original application or boundary inputs changed.')
    for name, expected in reuse.items():
        need(sha(args.framework_input / name) == sha(fresh / name) == expected,
             'Framework input changed across build: ' + name)
    for name in ('MobileBatchBoundaryProbe.dll', 'BatchBoundary.Contract.dll'):
        need(sha(fresh / name) == manifest['files']['host/' + name], 'Trusted input changed across build: ' + name)
    for name, expected in frozen.items():
        need(sha(name) == expected, 'Frozen build input changed: ' + name)
    shutil.copy2(args.build_receipt, output / 'matching-build.json')
    shutil.copy2(args.inputs / 'input-manifest.json', output / 'input-manifest.json')
    write(output / 'state.json', {'app': str(app), 'bundleId': bid, 'bundleHashes': inventory(app),
         'buildReceiptSha256': sha(args.build_receipt), 'sourceCommit': COMMIT, 'sourceTree': TREE,
         'native': native_platform(app / 'libcoreclr.dylib'), 'sourceNative': native_info,
         'nativeSha256': sha(native), 'corelibSha256': sha(corelib),
         'compilerSha256': sha(compiler), 'inputManifestSha256': sha(args.inputs / 'input-manifest.json'),
         'frameworkInputs': reuse, 'compositeInputs': {p.name: sha(p) for p in composite},
         'layouts': layouts, 'executionVerified': False, 'nativeEntryProof': False})
    print('BUILD PASS: fresh batch boundary app; execution not yet verified', flush=True)


def rebind(args):
    """Keep the accepted signed app intact and repair only its launch metadata."""
    old = args.application.resolve()
    state = read(old / 'state.json')
    app = Path(state['app'])
    manifest = inputs(args.inputs)
    receipt = read(old / 'matching-build.json')
    need(state['sourceCommit'] == receipt['commit'] == COMMIT and
         state['sourceTree'] == receipt['tree'] == TREE and receipt['success'] is True and
         receipt['buildExit'] == 0 and receipt['target'] == 'iossimulator.arm64',
         'Original build identity differs.')
    need(sha(old / 'matching-build.json') == state['buildReceiptSha256'] and
         sha(args.inputs / 'input-manifest.json') == state['inputManifestSha256'] and
         inventory(app) == state['bundleHashes'], 'Original signed bundle or input binding changed.')
    source_native = state.get('sourceNative', state['native'])
    need(source_native['sha256'] == receipt['nativeSha256'] == state['nativeSha256'],
         'Original unsigned native binding differs.')
    signed_native = native_platform(app / 'libcoreclr.dylib')
    need(signed_native['sha256'] == state['bundleHashes']['libcoreclr.dylib'], 'Original signed native binding differs.')
    need(not list(app.rglob('BatchBoundary.Author.dll')) and manifest['expectedContexts'] == 168,
         'Original trusted/author layout differs.')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    write(output / 'request.json', {'driverSha256': sha(__file__), 'reusedApplication': str(old),
          'originalStateSha256': sha(old / 'state.json'), 'sourceNative': source_native,
          'signedNative': signed_native, 'appRebuilt': False, 'executionVerified': False})
    state.update(native=signed_native, sourceNative=source_native)
    write(output / 'state.json', state)
    for name in ('matching-build.json', 'input-manifest.json'):
        shutil.copy2(old / name, output / name)
    need(inventory(app) == state['bundleHashes'], 'Signed bundle changed during rebind.')
    print('REBIND PASS: original signed app retained; no recompilation or execution', flush=True)


def execute(args):
    need(platform.system() == 'Darwin', 'Simulator run requires the configured Mac.')
    review = module('mobile_boundary_review', 'assess-mobile-batch-boundary.py', REVIEW_SHA)
    review.validator_for('Arm64')
    app_state = read(args.application / 'state.json')
    manifest = inputs(args.inputs)
    app = Path(app_state['app'])
    need(inventory(app) == app_state['bundleHashes'] and
         sha(args.inputs / 'input-manifest.json') == app_state['inputManifestSha256'] and
         sha(args.application / 'matching-build.json') == app_state['buildReceiptSha256'], 'App binding changed.')
    need(native_platform(app / 'libcoreclr.dylib') == app_state['native'], 'Actual app native platform differs.')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    simulator, booted = None, False
    result = {'passed': False, 'platform': 'iossimulator.arm64', 'nativeEntryProof': False,
              'liveBatchPathVerified': False, 'performanceMeasured': False, 'physicalDeviceVerified': False}
    try:
        simulator = cap(['xcrun', 'simctl', 'create', 'RuneCLR-BatchBoundary', args.device_type, args.sim_runtime])
        write(output / 'owned-simulator.json', {'id': simulator, 'bundleId': app_state['bundleId']})
        run(['xcrun', 'simctl', 'boot', simulator], output / 'boot.log')
        booted = True
        run(['xcrun', 'simctl', 'bootstatus', simulator, '-b'], output / 'bootstatus.log', 180)
        run(['xcrun', 'simctl', 'install', simulator, app], output / 'install.log')
        installed = Path(cap(['xcrun', 'simctl', 'get_app_container', simulator, app_state['bundleId'], 'app']))
        before = inventory(installed)
        need(before == app_state['bundleHashes'], 'Installed signed app differs.')
        write(output / 'installed-before.json', before)
        data = Path(cap(['xcrun', 'simctl', 'get_app_container', simulator, app_state['bundleId'], 'data']))
        plugin = data / 'Documents/batch-plugin'
        plugin.mkdir(parents=True, exist_ok=False)
        for name in ('BatchBoundary.Author.dll', 'BatchBoundary.Contract.dll'):
            source = args.inputs / 'author' / name
            shutil.copy2(source, plugin / name)
            need(sha(plugin / name) == manifest['files']['author/' + name], 'Post-install author changed.')
            layout = module('ios_frozen_parent_run', 'ios-session-budget-accept.py', PARENT_SHA).il_layout(plugin / name)
            need(layout['ilOnly'] and not layout['managedNativeRva'], 'Author dependency must remain IL.')
        author_before = inventory(plugin)
        write(output / 'author-before.json', author_before)
        lanes, owners = {}, []
        for configured, matrix in LANES:
            label, nonce = f'N{configured}-matrix{matrix}', uuid.uuid4().hex
            lane = output / label
            lane.mkdir()
            env = {k: v for k, v in os.environ.items() if not k.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_')) and
                   not k.startswith(('SIMCTL_CHILD_DOTNET_', 'SIMCTL_CHILD_COMPlus_', 'SIMCTL_CHILD_RUNECLR_'))}
            settings = {'RUNECLR_BATCH_NONCE': nonce, 'RUNECLR_BATCH_MATRIX': str(matrix),
                        'RUNECLR_BATCH_HEX': format(configured, 'x')}
            env.update({'SIMCTL_CHILD_' + k: v for k, v in settings.items()})
            argv = ['xcrun', 'simctl', 'launch', '--console', '--terminate-running-process', simulator, app_state['bundleId']]
            write(lane / 'request.json', {'argv': argv, 'settings': settings, 'configured': configured,
                  'matrix': matrix, 'nonce': nonce, 'timeout': args.timeout, 'debugger': False})
            run(argv, lane / 'native.log', args.timeout, env)
            target = data / ('Documents/batch-' + nonce + '.json')
            shutil.copy2(target, lane / 'receipt.json')
            actual = read(lane / 'receipt.json')
            log = (lane / 'native.log').read_text()
            pid = actual['processId']
            marker = (f'BATCH_NATIVE pid={pid} nonce={nonce} matrix={matrix} interval={configured:x} '
                      'PhaseAcquireLoad=1 DerivedLedger=0 InterpMode=0 ReadyToRun=1')
            need(len(re.findall('^' + re.escape(marker) + '$', log, re.M)) == 1 and
                 len(re.findall(r'^CORECLR_INITIALIZE_HRESULT=0x0$', log, re.M)) == 1 and
                 len(re.findall(r'^CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0$', log, re.M)) == 1,
                 'Native PID/settings/HRESULT/exit markers differ.')
            rows = review.review_lane(actual, configured, matrix, 'iossimulator.arm64', author_before['BatchBoundary.Author.dll'], pid, nonce)
            complete = f'BATCH_BOUNDARY_COMPLETE nonce={nonce} pid={pid} N={matrix} rows={len(rows)}'
            need(completed(log, complete, pid), 'Managed completion marker differs.')
            lanes[(configured, matrix)] = rows
            owners.append((pid, nonce))
            write(lane / 'results.json', {'passed': True, 'pid': pid, 'nonce': nonce, 'rows': len(rows),
                  'collections': sum(r['Collected'] is True for r in rows), 'receiptSha256': sha(lane / 'receipt.json'),
                  'nativeLogSha256': sha(lane / 'native.log'), 'nativeEntryProof': False})
            print(label + ': simulator boundary/recovery PASS', flush=True)
        need(len({x[0] for x in owners}) == len({x[1] for x in owners}) == 5, 'Each configuration needs a fresh process.')
        for n in (100, 1000):
            for exact, batch in zip(lanes[(1, n)], lanes[(n, n)]):
                if batch['Role'] == 'calibration':
                    need(exact['Observations']['Snapshot']['Executed'] == batch['Observations']['Snapshot']['Executed'],
                         'Post-frame partial batch settlement differs from exact.')
        collections = sum(r['Collected'] is True for rows in lanes.values() for r in rows)
        after = inventory(installed)
        write(output / 'installed-after.json', after)
        write(output / 'author-after.json', inventory(plugin))
        need(collections == 168 and before == after and author_before == inventory(plugin), 'Collection or installed identity differs.')
        result.update(passed=True, processes=5, collections=collections, sameProcessRecovery=True,
                      functionalSimulatorVerified=True, inputManifestSha256=app_state['inputManifestSha256'],
                      buildReceiptSha256=app_state['buildReceiptSha256'], native=app_state['native'],
                      driverSha256=sha(__file__), reviewerSha256=REVIEW_SHA)
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        if booted:
            status = subprocess.run(['xcrun', 'simctl', 'shutdown', simulator], capture_output=True, text=True)
            write(output / 'cleanup.json', {'simulator': simulator, 'exitCode': status.returncode,
                                           'stdout': status.stdout, 'stderr': status.stderr})
            result['cleanupSucceeded'] = status.returncode == 0
        result['endedUtc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        write(output / 'results.json', result)
        print(json.dumps(result, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('build', 'rebind', 'run'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    for name in ('runtime', 'build-receipt', 'baseline-app', 'wrapper-source', 'wrapper-assets', 'framework-input', 'framework-manifest', 'application'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--device-type', default='com.apple.CoreSimulator.SimDeviceType.iPhone-16')
    parser.add_argument('--sim-runtime', default='com.apple.CoreSimulator.SimRuntime.iOS-27-0')
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    required = ('runtime', 'build_receipt', 'baseline_app', 'wrapper_source', 'wrapper_assets', 'framework_input', 'framework_manifest') if args.phase == 'build' else ('application',)
    for name in required:
        if getattr(args, name) is None:
            parser.error('--' + name.replace('_', '-') + ' required')
    if args.phase == 'build':
        build(args)
    elif args.phase == 'rebind':
        rebind(args)
    else:
        execute(args)


if __name__ == '__main__':
    main()
