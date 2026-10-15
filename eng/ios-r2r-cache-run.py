#!/usr/bin/env python3
"""Compare an unchanged full R2R host on original and diagnostic native runtimes."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else
    '/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr')
OUT = ROOT / 'ios-r2r-cache-20261012'
ORIGINAL = ROOT / 'preview6-experiment/pinned-debug-harness/app/RuneCLRPinnedHarness.app'
NATIVE = OUT / 'obj-trace/dlls/mscoree/coreclr/libcoreclr.dylib'
BUNDLE_ID = 'org.runeclr.pinned.debug.harness'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def capture(args):
    return subprocess.check_output([str(a) for a in args], text=True).strip()

def run(args, log, timeout=None, env=None, check=True):
    with open(log, 'w') as stream:
        try:
            result = subprocess.run([str(a) for a in args], stdout=stream,
                stderr=subprocess.STDOUT, timeout=timeout, env=env, check=check)
            return result.returncode
        except subprocess.TimeoutExpired:
            stream.write('\nRUNECLR_DIAGNOSTIC_TIMEOUT\n')
            return 124

def parse_result(log, switch, status):
    data = log.read_text(errors='replace')
    return {
        'switch': switch, 'launcherExit': status,
        'managedExit0': 'RUNECLR_EXIT=0' in data,
        'nativeInitialized': 'CORECLR_INITIALIZE_HRESULT=0x0' in data,
        'suitePassed21': bool(re.search(r'(?<!\d)21/21 tests passed', data)),
        'nativeSigsegv': 'Got a SIGSEGV while executing native code.' in data,
        'cacheSkips': data.count('RUNECLR_CID_RESOLVE skip=1'),
        'cacheTraces': data.count('RUNECLR_CID_RESOLVE'),
        'assertion': 'Assert failure' in data,
        'logSha256': sha(log),
    }

def matrix_passed(results):
    failures = [results.get(name, {}) for name in
        ('original', 'diagnostic-off', 'diagnostic-trace')]
    enabled = results.get('diagnostic-on', {})
    return (all(item.get('nativeInitialized') and item.get('nativeSigsegv')
            and not item.get('managedExit0') and not item.get('assertion')
            and item.get('launcherExit') != 124 for item in failures)
        and results.get('original', {}).get('cacheTraces') == 0
        and results.get('diagnostic-off', {}).get('cacheTraces') == 0
        and results.get('diagnostic-trace', {}).get('cacheTraces', 0) > 0
        and results.get('diagnostic-trace', {}).get('cacheSkips') == 0
        and enabled.get('nativeInitialized') and enabled.get('managedExit0')
        and enabled.get('suitePassed21') and not enabled.get('assertion')
        and not enabled.get('nativeSigsegv') and enabled.get('launcherExit') == 0
        and enabled.get('cacheSkips', 0) > 0)

def verify_existing(work):
    recorded = json.loads((work / 'results.json').read_text())
    results = {name: parse_result(work / (name + '.log'), item['switch'],
        item['launcherExit']) for name, item in recorded.items()}
    (work / 'results-verified.json').write_text(json.dumps(results, indent=2) + '\n')
    passed = matrix_passed(results)
    print(json.dumps({'matrixPassed': passed, 'results': results}, indent=2))
    return 0 if passed else 1

def main():
    if len(sys.argv) == 4 and sys.argv[2] == '--verify-existing':
        return verify_existing(Path(sys.argv[3]))
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    work = OUT / ('compare-' + stamp)
    work.mkdir(exist_ok=False)
    app = work / 'patched/RuneCLRPinnedHarness.app'
    app.parent.mkdir()
    shutil.copytree(ORIGINAL, app)
    shutil.copy2(NATIVE, app / 'libcoreclr.dylib')
    run(['codesign', '--force', '--sign', '-', app / 'libcoreclr.dylib'], work / 'native-sign.log')
    run(['codesign', '--force', '--sign', '-', app], work / 'app-sign.log')
    original_managed = {str(p.relative_to(ORIGINAL)): sha(p) for p in ORIGINAL.rglob('*')
        if p.is_file() and p.suffix == '.dll'}
    patched_managed = {name: sha(app / name) for name in original_managed}
    if original_managed != patched_managed:
        raise RuntimeError('Managed package changed during the native comparison')
    if sha(ORIGINAL / 'framework.dylib') != sha(app / 'framework.dylib'):
        raise RuntimeError('Trusted host/framework composite changed')
    (work / 'identity.json').write_text(json.dumps({
        'managedFiles': original_managed,
        'frameworkSha256': sha(app / 'framework.dylib'),
        'originalNativeSha256': sha(ORIGINAL / 'libcoreclr.dylib'),
        'patchedNativeUnsignedSha256': sha(NATIVE),
        'patchedNativeSignedSha256': sha(app / 'libcoreclr.dylib'),
        'source': json.loads((OUT / 'logs-trace/source.json').read_text()),
    }, indent=2) + '\n')
    simulator = capture(['xcrun', 'simctl', 'create', 'RuneCLR-CID-Cache-Diagnostic',
        'com.apple.CoreSimulator.SimDeviceType.iPhone-17', 'com.apple.CoreSimulator.SimRuntime.iOS-27-0'])
    (work / 'simulator.uuid').write_text(simulator + '\n')
    results = {}
    try:
        run(['xcrun', 'simctl', 'boot', simulator], work / 'boot-command.log')
        run(['xcrun', 'simctl', 'bootstatus', simulator, '-b'], work / 'boot.log', timeout=180)
        for name, package, switch in (('original', ORIGINAL, '0'),
                ('diagnostic-off', app, '0'), ('diagnostic-trace', app, '2'), ('diagnostic-on', app, '1')):
            run(['xcrun', 'simctl', 'install', simulator, package], work / (name + '-install.log'), timeout=60)
            env = dict(os.environ)
            env['SIMCTL_CHILD_DOTNET_RuneCLRDisableCollectibleInterfaceDispatchCache'] = switch
            log = work / (name + '.log')
            status = run(['xcrun', 'simctl', 'launch', '--console', simulator, BUNDLE_ID],
                log, timeout=90, env=env, check=False)
            results[name] = parse_result(log, switch, status)
            print(name + ': ' + json.dumps(results[name]), flush=True)
            (work / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
            run(['xcrun', 'simctl', 'terminate', simulator, BUNDLE_ID],
                work / (name + '-terminate.log'), check=False)
    finally:
        run(['xcrun', 'simctl', 'shutdown', simulator], work / 'shutdown.log', check=False)
    return 0 if matrix_passed(results) else 1

if __name__ == '__main__':
    sys.exit(main())
