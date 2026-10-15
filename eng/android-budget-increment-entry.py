#!/usr/bin/env python3
"""Build a fresh opt-in JNI gate over the frozen minimal-increment layout."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

APK_DRIVER_SHA = '0bbdd66b80cec5115635a690cd2099df9ed14e1869bd5d518019c540d584c73e'
GATE_DRIVER_SHA = 'b18c5a0523367870f87923bf7819dfb8adc060d6b9675147753d0cd07a871f50'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_module(name):
    path=Path(__file__).with_name(name+'.py')
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def build(args):
    path=Path(__file__).with_name('android-budget-increment-apk.py')
    if sha(path)!=APK_DRIVER_SHA:raise RuntimeError('Frozen candidate APK adapter changed')
    adapter=load_module('android-budget-increment-apk');base=adapter.base
    baseline=base.load(args.baseline/'state.json')
    adapter.validate_state(args.baseline);adapter.validate_inputs(args.inputs);adapter.validate_layout(args.layout)
    before={p.relative_to(args.baseline).as_posix():sha(p) for p in args.baseline.rglob('*') if p.is_file()}
    if sha(Path(__file__).with_name('android-session-policy-entry.py'))!=GATE_DRIVER_SHA:raise RuntimeError('Frozen gate source changed')
    gate=load_module('android-session-policy-entry').GATE.replace('RUNECLR_SESSION_NATIVE_ENTRY_WAIT','RUNECLR_BUDGET_NATIVE_ENTRY_WAIT').replace('session-%s.entry-release','budget-%s.entry-release')
    original=base.patch_template
    def patch(path,anchor,replacement):
        original(path,anchor,replacement)
        if anchor=='    setenv ("DOTNET_CrashReportBeforeSignalChaining", "1", true);':
            original(path,'#define PROPERTY_COUNT %AppContextPropertyCount%',gate+'\n#define PROPERTY_COUNT %AppContextPropertyCount%')
            anchor='    LOG_INFO ("Calling coreclr_initialize");'
            original(path,anchor,'    if (RuneCLR_EntryWait(g_bundle_path,nonce)!=0) return -1;\n'+anchor)
    base.patch_template=patch
    adapter.apk(args)
    state=base.load(args.output/'state.json')
    if state['appHashes']!=baseline['appHashes']:raise RuntimeError('Native/managed/author-independent app inputs changed')
    native=args.output/'builder/Templates/monodroid-coreclr.c'
    reverted=native.read_text().replace(gate+'\n','',1).replace('    if (RuneCLR_EntryWait(g_bundle_path,nonce)!=0) return -1;\n','',1)
    if reverted!=(args.baseline/'builder/Templates/monodroid-coreclr.c').read_text():raise RuntimeError('JNI source delta extends beyond opt-in gate')
    if (args.output/'builder/Templates/MonoRunner.java').read_bytes()!=(args.baseline/'builder/Templates/MonoRunner.java').read_bytes():raise RuntimeError('Java wrapper source changed')
    if before!={p.relative_to(args.baseline).as_posix():sha(p) for p in args.baseline.rglob('*') if p.is_file()}:raise RuntimeError('Accepted original APK output changed')
    shutil.copy2(__file__,args.output/'entry-driver.py');(args.output/'entry-gate.h').write_text(gate)
    base.write(args.output/'entry-build.json',{'success':True,'preparedOnly':True,'deviceExecuted':False,'driverSha256':sha(__file__),'apkAdapterSha256':APK_DRIVER_SHA,'baselineStateSha256':sha(args.baseline/'state.json'),'baselineApkSha256':baseline['apkSha256'],'newApkSha256':state['apkSha256'],'newPackage':state['package'],'sameAppHashes':True,'onlyJniOptInGateDelta':True,'javaSourceUnchanged':True,'gateSha256':sha(args.output/'entry-gate.h'),'timeoutSeconds':180,'optIn':'RUNECLR_BUDGET_NATIVE_ENTRY_WAIT=1','nativeEntryProof':False})
    print('NEW_GATED_INCREMENT_APK_PASS',state['package'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--layout',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--builder',type=Path,default=Path('D:/RuneCLR-Android/coreclr-smoke/run-20261012-172351/builder'));p.add_argument('--android-root',type=Path,default=Path('D:/RuneCLR-Android'));p.add_argument('--dotnet',type=Path,default=Path('E:/runtime/.dotnet/dotnet.exe'))
    build(p.parse_args())

if __name__=='__main__':main()
