#!/usr/bin/env python3
"""Settle completed Kernel captures without replaying either application launch."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
from types import SimpleNamespace

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def write(p,v): Path(p).write_text(json.dumps(v,indent=2)+'\n')
def helper(name):
    p=Path(__file__).with_name(name+'.py')
    s=importlib.util.spec_from_file_location(name.replace('-','_'),p)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apk',type=Path,required=True)
    p.add_argument('--android-root',type=Path,default=Path('D:/RuneCLR-Android'))
    a=p.parse_args();a.serial='emulator-5556'
    base=helper('android-batch-kernel-apk').adapted()[0]
    installer=helper('android-batch-boundary-entry-install')
    base.device(a);state=read(a.apk/'state.json')
    appinfo=base.adb(a,['shell','dumpsys','package',state['package']])[0]
    match=re.search(r'(?m)^\s*(?:legacyNativeLibraryDir|nativeLibraryDir)=([^\s]+)',appinfo)
    assert match
    rows=base.adb(a,['shell','run-as',state['package'],'find',match[1],'-name','libcoreclr.so'])[0].splitlines()
    assert len(rows)==1
    native_dir=rows[0].rsplit('/',1)[0]
    captures=sorted(a.apk.glob('capture-*'));assert len(captures)==2
    for out in captures:
        result=read(out/'results.json');nonce=result['nonce'];pid=result['appPid'];interval=result['configuredInterval']
        assert result['instrumentationExit']==result['lldbExit']==0 and result['debuggerTransportPassed']
        assert result['error'].endswith('RuntimeError: loadedContractComponentHash: JSON type differs\n')
        assert all(sha(out/n)==digest for n,digest in result['rawHashes'].items())
        native=(out/'native.log').read_text()
        for marker in ('CORECLR_INITIALIZE_HRESULT=0x0','CORECLR_EXECUTE_HRESULT=0x0;RUNECLR_EXIT=0','CORECLR_SHUTDOWN_HRESULT=0x0'):
            assert len(re.findall(r'(?m)^'+re.escape(marker)+r'$',native))==1
        assert f'ANDROID_BATCH_NATIVE pid={pid} nonce={nonce} matrix={interval} interval=' in native
        instrumentation=(out/'instrumentation.log').read_text()
        assert re.findall(r'^INSTRUMENTATION_RESULT: return-code=([0-9-]+)\r?$',instrumentation,re.M)==['0']
        assert re.findall(r'^INSTRUMENTATION_CODE: ([0-9-]+)\r?$',instrumentation,re.M)==['0']
        managed=read(out/'managed-result.json')
        assert managed=={'nonce':nonce,'interval':'64' if interval==100 else '3e8','exitCode':0,'appPid':pid}
        observer=out/'observer';assert not (observer/'capture-errors.json').exists()
        entries=read(observer/'interpreter-entries.json');settlements=read(observer/'settlements.json')
        assert len(entries)==2 and all(e['methodDefToken']==0x06000001 and e['loadedMetadataMvidValidated'] for e in entries)
        assert len(settlements)==4 and [e['kind'] for e in settlements]==['full','full','tail','tail']
        assert [e['entryEsi'] for e in settlements[:2]]==[interval,interval]
        assert all(0<e['entryEsi']<interval for e in settlements[2:])
        config=read(observer/'capture-config.json')
        assert all(e['innerReturnFilePc'] in config['allReturnPcs'] and
                   e['actualInnerReturnPc']==int(result['coreclrSlide'],16)+e['innerReturnFilePc'] and
                   e['entryRdi']==e['embeddedMeter']==e['assemblyBinder']+0x110 and
                   e['metadataMethodName']=='RuneCLR.BatchKernel.Kernel.Execute' for e in settlements)
        assert len({e['embeddedMeter'] for e in settlements})==1
        assert read(observer/'observation-disabled.json')['allObservationBreakpointsDisabled']
        debug=read(observer/'debugger-result.json')
        assert debug['exited'] and debug['errors']==0 and debug['pid']==pid and debug['runId']==nonce
        before=read(out/'installed-before.json')
        after=installer.inventory(base,a,state,out,'installed-after-settlement',native_dir)
        assert before==after and len(after)==201
        for mode,suffix in [('high-budget','high'),('no-config','recovery')]:
            receipt=read(out/(suffix+'.json'))
            assert receipt['processId']==pid and receipt['nonce']==nonce and receipt['mode']==mode
            assert receipt['collected'] and receipt['loadedContractComponentHash'] is None
            marker=f'MOBILE_BATCH_KERNEL_COMPLETE nonce={nonce} pid={pid} mode={mode} callbacks=4'
            assert native.count(marker)==1 and (out/'managed.log').read_text().count(marker)==1
        summary={'success':True,'scalarReviewPending':True,'nativeEntryProof':False,
                 'independentReviewRequired':True,'originalFailedReviewPreserved':True,
                 'pid':pid,'nonce':nonce,'configuredInterval':interval,
                 'fullSamples':[e['entryEsi'] for e in settlements[:2]],
                 'tailSamples':[e['entryEsi'] for e in settlements[2:]],
                 'sameProcessNoConfigRecoveryCompleted':True,'managedInstrumentationAndHRESULTsZero':True,
                 'installedActualHashesUnchanged':True,'installedEntries':len(after),'contextsCollected':2,
                 'actualDebuggerExitStatus':debug['exitStatus'],'physicalDeviceTouched':False,
                 'applicationLaunchReplayed':False,'driverSha256':sha(__file__),'rawHashes':base.files(out)}
        write(out/'entry-completion.json',summary)
        print('ANDROID_KERNEL_COMPLETION_PASS',interval,summary['fullSamples'],summary['tailSamples'],pid)

if __name__=='__main__':main()
