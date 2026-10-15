#!/usr/bin/env python3
"""Build a fresh opt-in JNI gate over the accepted batch-boundary APK inputs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

BASE_SHA = '66adcf5a7a60a13db4695d43b2c4a18643ab39392d7f33884d74da7ba5e46c50'
GATE_SHA = 'b18c5a0523367870f87923bf7819dfb8adc060d6b9675147753d0cd07a871f50'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def helper(name, expected):
    path = Path(__file__).with_name(name + '.py')
    if sha(path) != expected:
        raise RuntimeError('Frozen input changed: ' + name)
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'baseline', 'layout', 'inputs'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--builder', type=Path, default=Path('D:/RuneCLR-Android/coreclr-smoke/run-20261012-172351/builder'))
    p.add_argument('--android-root', type=Path, default=Path('D:/RuneCLR-Android'))
    p.add_argument('--dotnet', type=Path, default=Path('E:/runtime/.dotnet/dotnet.exe'))
    args = p.parse_args()
    base = helper('android-batch-boundary-apk', BASE_SHA)
    baseline = base.load(args.baseline / 'state.json')
    base.require(baseline['runtimeTree'] == base.TREE and baseline['apkSha256'] ==
                 '1c5402860cf13aee832eb53bdda4f2e24b9ebc3f9cbe0999f4cdd75a53eec36d'
                 and sha(baseline['apk']) == baseline['apkSha256'], 'Accepted APK identity differs')
    before = base.files(args.baseline)
    gate = helper('android-session-policy-entry', GATE_SHA).GATE.replace(
        'RUNECLR_SESSION_NATIVE_ENTRY_WAIT', 'RUNECLR_BATCH_NATIVE_ENTRY_WAIT').replace(
        'session-%s.entry-release', 'batch-%s.entry-release')
    original = base.patch_template
    def patch(path, anchor, replacement):
        original(path, anchor, replacement)
        if anchor == '    setenv ("DOTNET_CrashReportBeforeSignalChaining", "1", true);':
            original(path, '#define PROPERTY_COUNT %AppContextPropertyCount%',
                     gate + '\n#define PROPERTY_COUNT %AppContextPropertyCount%')
            a = '    LOG_INFO ("Calling coreclr_initialize");'
            original(path, a, '    if (RuneCLR_EntryWait(g_bundle_path,nonce)!=0) return -1;\n' + a)
    base.patch_template = patch
    base.apk(args)
    state = base.load(args.output / 'state.json')
    base.require(state['appHashes'] == baseline['appHashes'], 'Managed/native app payload changed')
    native = args.output / 'builder/Templates/monodroid-coreclr.c'
    reverted = native.read_text().replace(gate + '\n', '', 1).replace(
        '    if (RuneCLR_EntryWait(g_bundle_path,nonce)!=0) return -1;\n', '', 1)
    base.require(reverted == (args.baseline / 'builder/Templates/monodroid-coreclr.c').read_text(),
                 'JNI source delta extends beyond explicit gate')
    base.require((args.output / 'builder/Templates/MonoRunner.java').read_bytes() ==
                 (args.baseline / 'builder/Templates/MonoRunner.java').read_bytes(), 'Java source changed')
    base.require(before == base.files(args.baseline), 'Accepted baseline files changed')
    shutil.copy2(__file__, args.output / 'entry-driver.py')
    (args.output / 'entry-gate.h').write_text(gate, encoding='ascii')
    base.write(args.output / 'entry-build.json', {
        'success': True, 'preparedOnly': True, 'nativeEntryProof': False,
        'driverSha256': sha(__file__), 'baseDriverSha256': BASE_SHA, 'gateDriverSha256': GATE_SHA,
        'baselineApkSha256': baseline['apkSha256'], 'newApkSha256': state['apkSha256'],
        'sameAppHashes': True, 'onlyJniOptInGateDelta': True, 'javaSourceUnchanged': True,
        'baselinePreserved': True, 'gateSha256': sha(args.output / 'entry-gate.h'),
        'optIn': 'RUNECLR_BATCH_NATIVE_ENTRY_WAIT=1', 'timeoutSeconds': 180})
    print('NEW_GATED_BATCH_BOUNDARY_APK_PASS', state['package'])

if __name__ == '__main__':
    main()
