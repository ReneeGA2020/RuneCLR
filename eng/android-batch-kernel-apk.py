#!/usr/bin/env python3
"""Build a fresh gated Kernel APK without changing the accepted boundary workflow."""
import argparse
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import shutil

BASE_SHA = '66adcf5a7a60a13db4695d43b2c4a18643ab39392d7f33884d74da7ba5e46c50'
KERNEL_SHA = '405ac0fd64dea388ccda49c505554e363f5ff3a43b4cca4226131cab9627d3b0'
GATE_SHA = 'b18c5a0523367870f87923bf7819dfb8adc060d6b9675147753d0cd07a871f50'

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def helper(name, digest):
    path = Path(__file__).with_name(name + '.py')
    assert sha(path) == digest, 'Frozen helper changed: ' + name
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def adapted():
    base = helper('android-batch-boundary-apk', BASE_SHA)
    kernel = helper('android-batch-kernel-build', KERNEL_SHA)
    source = inspect.getsource(base.apk)
    replacements = {
        'runeclr.android-batch-boundary.layout.v1': 'runeclr.android-batch-kernel.layout.v1',
        "l['expectedContexts']==168": "l['expectedContexts']==2",
        'RuneCLR_BatchBoundary_': 'RuneCLR_BatchKernel_',
        'BatchBoundary.Author.dll': 'RuneCLR.BatchKernel.dll',
        'BatchBoundary.Author.': 'RuneCLR.BatchKernel.',
    }
    counts = {}
    for old, new in replacements.items():
        counts[old] = source.count(old)
        assert counts[old] > 0, old
        source = source.replace(old, new)
    gate = helper('android-session-policy-entry', GATE_SHA).GATE.replace(
        'RUNECLR_SESSION_NATIVE_ENTRY_WAIT', 'RUNECLR_BATCH_NATIVE_ENTRY_WAIT').replace(
        'session-%s.entry-release', 'batch-%s.entry-release')
    original = base.patch_template
    def patch(path, anchor, replacement):
        original(path, anchor, replacement)
        if anchor == '    setenv ("DOTNET_CrashReportBeforeSignalChaining", "1", true);':
            original(path, '#define PROPERTY_COUNT %AppContextPropertyCount%',
                     gate + '\n#define PROPERTY_COUNT %AppContextPropertyCount%')
            anchor2 = '    LOG_INFO ("Calling coreclr_initialize");'
            original(path, anchor2, '    if (RuneCLR_EntryWait(g_bundle_path,nonce)!=0) return -1;\n' + anchor2)
    env = dict(base.__dict__)
    env.update(inputs=kernel.inputs, INPUT_SHA=kernel.INPUT_SHA,
               BRIDGE_NAME=kernel.BRIDGE_NAME, patch_template=patch, __file__=__file__)
    exec(compile(source, str(Path(__file__).resolve()), 'exec'), env)
    base.apk = env['apk']
    base.inputs = kernel.inputs
    return base, counts, gate

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'layout', 'inputs'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--builder', type=Path, default=Path('D:/RuneCLR-Android/coreclr-smoke/run-20261012-172351/builder'))
    p.add_argument('--android-root', type=Path, default=Path('D:/RuneCLR-Android'))
    p.add_argument('--dotnet', type=Path, default=Path('E:/runtime/.dotnet/dotnet.exe'))
    args = p.parse_args()
    base, counts, gate = adapted()
    base.apk(args)
    state = base.load(args.output / 'state.json')
    shutil.copy2(__file__, args.output / 'kernel-apk-driver.py')
    (args.output / 'entry-gate.h').write_text(gate, encoding='ascii')
    base.write(args.output / 'entry-build.json', {
        'success': True, 'preparedOnly': True, 'nativeEntryProof': False,
        'driverSha256': sha(__file__), 'baseDriverSha256': BASE_SHA,
        'kernelDriverSha256': KERNEL_SHA, 'gateDriverSha256': GATE_SHA,
        'sourceReplacementCounts': counts, 'newApkSha256': state['apkSha256'],
        'onlyJniOptInGateDelta': True, 'gateSha256': sha(args.output / 'entry-gate.h'),
        'optIn': 'RUNECLR_BATCH_NATIVE_ENTRY_WAIT=1', 'timeoutSeconds': 180,
        'scope': 'Fresh Kernel bridge/composite APK; no target execution or entry claim'})
    print('NEW_GATED_KERNEL_APK_PASS', state['package'])

if __name__ == '__main__':
    main()
