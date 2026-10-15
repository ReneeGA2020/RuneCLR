#!/usr/bin/env python3
"""Bind the exact derived-ledger candidate to a fresh iOS budget application."""
import argparse
import hashlib
import importlib.util
import json
import platform
import re
import shutil
import subprocess
from pathlib import Path

COMMIT = '2d86588f8cef4b3c48ce2ba4d4af15ad7bc83e7c'
TREE = '3292fc9acf3c15632f3bde34f675caec44f399e2'
PROOF_SHA = 'c860e8c483347c8b552b5128d7a5a28f6fe69bef4eb32a2426337a736fddca97'
BUILD_SHA = 'a80501359effdf25bedf7f30bc6f07ab700a68f0efb0fd59f6b80c9c4ac8b7d0'
PARENT_SHA = 'cfe2ab27a62e84cbc3b181f40b582d1cb90ab6c93a8323f2de49d2ec5c1cc8a7'
FUNCTIONAL_SHA = 'cd88560e2d406b915726054917bbfb22c1fb6cb7ad887574fec2ea95b30cb74e'
MANIFEST_SHA = 'ccf1ece09ef7d8f33a4da685234222526426f4712af1b1a5b2308de0dc97d685'

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()

def capture(c):
    return subprocess.check_output([str(x) for x in c], text=True).strip()

def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')

def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}

def checked_parent():
    path = Path(__file__).with_name('ios-session-budget-accept.py')
    if sha(path) != PARENT_SHA: raise RuntimeError('frozen parent driver differs')
    spec = importlib.util.spec_from_file_location('frozen_ios_budget', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def derived_compile_wrapper(a, out, app):
    parent = checked_parent()
    w = a.wrapper_source.read_text()
    anchor = '    char **managed_argv;'
    if w.count(anchor) != 1: raise RuntimeError('unknown wrapper initialization anchor')
    w = re.sub(r'^.*(?:un)?setenv\s*\(\s*"(?:DOTNET|COMPlus)_(?:Interp[A-Za-z]*|RuneCLR[A-Za-z]*|ReadyToRun)"[^\n]*\n', '', w, flags=re.M)
    w = re.sub(r'^.*printf\("SESSION_NATIVE_CONFIG[^\n]*\n', '', w, flags=re.M)
    settings = ('    setenv("DOTNET_InterpMode", "0", 1);\n'
                '    setenv("DOTNET_RuneCLRInterpretCollectible", "0", 1);\n'
                '    setenv("DOTNET_ReadyToRun", "1", 1);\n'
                '    setenv("DOTNET_InterpList", "0", 1);\n'
                '    unsetenv("DOTNET_InterpDump");\n'
                '    setenv("DOTNET_RuneCLRPhaseAcquireLoad", "1", 1);\n'
                '    setenv("DOTNET_RuneCLRDerivedLedger", "1", 1);\n'
                '    setenv("RUNECLR_DOCUMENTS", [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES)[0] UTF8String], 1);\n'
                '    printf("MOBILE_BUDGET_NATIVE pid=%d nonce=%s InterpMode=0 RuneCLRInterpretCollectible=0 ReadyToRun=1\\n", getpid(), getenv("RUNECLR_BUDGET_NONCE")); fflush(stdout);\n'
                '    printf("DERIVED_LEDGER_NATIVE pid=%d nonce=%s PhaseAcquireLoad=%s DerivedLedger=%s\\n", getpid(), getenv("RUNECLR_BUDGET_NONCE"), getenv("DOTNET_RuneCLRPhaseAcquireLoad"), getenv("DOTNET_RuneCLRDerivedLedger")); fflush(stdout);\n')
    (out / 'runtime.m').write_text(w.replace(anchor, settings + anchor))
    parent.run(['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator',
                '-fobjc-arc', '-DINVARIANT_GLOBALIZATION=1', '-I' + str(a.wrapper_source.parent),
                str(a.wrapper_source.parent / 'main.m'), out / 'runtime.m', '-L' + str(app), '-lcoreclr',
                '-framework', 'UIKit', '-framework', 'Foundation', '-Wl,-rpath,@executable_path',
                '-o', app / 'Session'], out / 'logs/wrapper-build.log')

def bindings(a):
    if platform.system() != 'Darwin': raise RuntimeError('this application lane requires Darwin')
    for p, h in ((a.source_proof, PROOF_SHA), (a.build_receipt, BUILD_SHA),
                 (a.inputs / 'input-manifest.json', MANIFEST_SHA)):
        if sha(p) != h: raise RuntimeError('frozen receipt differs ' + str(p))
    rec = json.loads(a.build_receipt.read_text()); proof = json.loads(a.source_proof.read_text())
    if proof.get('layoutSize') != 64 or proof.get('layoutAlignment') != 8 or proof.get('phaseFlagOffset') != 2 or proof.get('derivedFlagOffset') != 3: raise RuntimeError('candidate meter layout differs')
    if not all(proof.get(k) is True for k in ('exactDerivedLedgerVerified', 'phaseAcquireLoadDefaultOff', 'terminalDerivedLedgerDefaultOff', 'phaseAndDerivedSwitchesIndependent')): raise RuntimeError('candidate switch contracts differ')
    if rec.get('nativeMeterSize') != 64 or rec.get('nativeMeterAlignment') != 8: raise RuntimeError('compiled meter layout differs')
    if not rec['success'] or rec['commit'] != COMMIT or rec['tree'] != TREE: raise RuntimeError('candidate receipt identity differs')
    if capture(['git', '-C', a.runtime, 'rev-parse', 'HEAD']) != COMMIT or capture(['git', '-C', a.runtime, 'rev-parse', 'HEAD^{tree}']) != TREE: raise RuntimeError('live candidate identity differs')
    if capture(['git', '-C', a.runtime, 'status', '--porcelain', '--untracked-files=no']): raise RuntimeError('live source dirty')
    for n, h in proof['sourceHashes'].items():
        if sha(a.runtime / n) != h: raise RuntimeError('live source differs ' + n)
    for p, k in ((a.native, 'nativeSha256'), (a.corelib, 'corelibSha256'), (a.compiler, 'crossgen2Sha256')):
        if sha(p) != rec[k]: raise RuntimeError('critical candidate product differs ' + k)
    parent = checked_parent(); manifest = parent.inputs(a.inputs)
    prior = json.loads((a.baseline_app.parent.parent / 'framework-reuse.json').read_text())
    framework = a.wrapper_source.parent / 'input'
    framework_hashes = {n: sha(framework / n) for n in prior['inputHashes']}
    if framework_hashes != prior['inputHashes']: raise RuntimeError('original framework IL differs')
    old_state = json.loads((a.baseline_app.parent.parent / 'state.json').read_text())
    baseline = inventory(a.baseline_app)
    if baseline != old_state['bundleHashes']: raise RuntimeError('frozen old application differs')
    if manifest['files'] != old_state['inputFiles']: raise RuntimeError('trusted/author input identity differs')
    return {'runtimeCommit': COMMIT, 'runtimeTree': TREE, 'sourceProofSha256': PROOF_SHA,
            'buildReceiptSha256': BUILD_SHA, 'sourceFiles': len(proof['sourceHashes']),
            'inputManifestSha256': MANIFEST_SHA, 'inputFiles': manifest['files'],
            'parentDriverSha256': PARENT_SHA, 'driverSha256': sha(__file__),
            'baselineApp': str(a.baseline_app), 'baselineBundleHashes': baseline,
            'wrapperSourceSha256': sha(a.wrapper_source),
            'wrapperMainSha256': sha(a.wrapper_source.parent / 'main.m'),
            'frameworkInputHashes': framework_hashes, 'executionVerified': False,
            'phaseAcquireLoad': 1, 'derivedLedger': 1, 'nativeMeterSize': 64, 'nativeMeterAlignment': 8}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=('preflight', 'build', 'install', 'transfer', 'run', 'cleanup'))
    p.add_argument('--output', type=Path, required=True)
    for name in ('inputs', 'runtime', 'native', 'corelib', 'compiler', 'build-receipt', 'baseline-app', 'wrapper-source', 'source-proof'):
        p.add_argument('--' + name, type=Path)
    p.add_argument('--build-slot-granted', action='store_true')
    p.add_argument('--device-type', default='com.apple.CoreSimulator.SimDeviceType.iPhone-16')
    p.add_argument('--sim-runtime', default='com.apple.CoreSimulator.SimRuntime.iOS-27-0')
    p.add_argument('--timeout', type=int, default=900)
    a = p.parse_args(); parent = checked_parent()
    if a.phase in ('preflight', 'build'):
        bound = bindings(a)
        if a.phase == 'preflight':
            a.output.mkdir(exist_ok=False); shutil.copy2(__file__, a.output / 'driver.py')
            write(a.output / 'results.json', dict(bound, passed=True, heavyBuildStarted=False))
            print('PREFLIGHT PASS', bound['sourceFiles'], len(bound['frameworkInputHashes']), 'source/framework files'); return
        if not a.build_slot_granted: raise RuntimeError('exclusive Mac build slot required')
        parent.compile_wrapper = derived_compile_wrapper
        parent.build(a)
        shutil.copy2(__file__, a.output / 'derived-driver.py'); write(a.output / 'derived-bindings.json', bound)
        state = json.loads((a.output / 'state.json').read_text())
        state.update(derivedBindingsSha256=sha(a.output / 'derived-bindings.json'), phaseAcquireLoad=1, derivedLedger=1)
        write(a.output / 'state.json', state)
        if bindings(a) != bound: raise RuntimeError('frozen inputs changed across application build')
    elif a.phase == 'install':
        parent.install(a)
        s = json.loads((a.output / 'state.json').read_text())
        installed = Path(capture(['xcrun', 'simctl', 'get_app_container', s['simulator'], s['bundleId'], 'app']))
        if inventory(installed) != s['bundleHashes']: raise RuntimeError('installed application differs from signed build')
        if any(installed.rglob('HostBudgetProbe.*.dll')): raise RuntimeError('author IL bundled before post-install transfer')
        s['installedApp'] = str(installed); write(a.output / 'state.json', s)
        write(a.output / 'installed-before-transfer.json', {'bundle': inventory(installed), 'authorBundled': False})
    elif a.phase == 'transfer':
        parent.inputs(a.inputs); parent.transfer(a)
        s = json.loads((a.output / 'state.json').read_text()); m = parent.inputs(a.inputs)
        if s['pluginHashes'] != {n.split('/', 1)[1]: h for n, h in m['files'].items() if n.startswith('plugin/')}: raise RuntimeError('post-install author bytes differ')
    elif a.phase == 'run':
        helper = Path(__file__).with_name('ios-derived-ledger-functional-run.py')
        if sha(helper) != FUNCTIONAL_SHA: raise RuntimeError('frozen functional observer differs')
        subprocess.run(['/usr/bin/python3', str(helper), '--player', str(a.output), '--inputs', str(a.inputs), '--output', str(a.output.parent / (a.output.name + '-functional')), '--timeout', str(a.timeout)], check=True)
    else: parent.cleanup(a)

if __name__ == '__main__': main()
