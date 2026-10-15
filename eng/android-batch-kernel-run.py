#!/usr/bin/env python3
"""Run bounded full/tail Kernel observations on the explicitly owned emulator."""
import argparse
import hashlib
import importlib.util
import inspect
from pathlib import Path
import re
import shutil

BASE_SHA='c3cc399d4580017f9a54880d6761ae23d0c92bb3c88ead72d1a10615298f529e'
REVIEW_SHA='8fc1563dede9273f6c2a2f065fdf8ceb6afe86130d975cbf9826a180b91deacf'

def helper(name):
    p=Path(__file__).with_name(name+'.py')
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),p)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

COMPLETION=r'''
        managed=base.load(out/'managed-result.json')
        assert managed['appPid']==pid and managed['nonce']==nonce and managed['interval']==HEX and managed['exitCode']==0
        native=(out/'native.log').read_text()
        assert header in native and gate+' state=released' in native
        for marker in ('CORECLR_INITIALIZE_HRESULT=0x0','CORECLR_EXECUTE_HRESULT=0x0;RUNECLR_EXIT=0','CORECLR_SHUTDOWN_HRESULT=0x0'):
            assert len(re.findall(r'(?m)^'+re.escape(marker)+r'$',native))==1
        instrumentation=(out/'instrumentation.log').read_text()
        assert re.findall(r'^INSTRUMENTATION_RESULT: return-code=([0-9-]+)\r?$',instrumentation,re.M)==['0']
        assert re.findall(r'^INSTRUMENTATION_CODE: ([0-9-]+)\r?$',instrumentation,re.M)==['0']
        for mode,suffix in [('high-budget','high'),('no-config','recovery')]:
            receipt=base.load(out/(suffix+'.json'))
            scalar=helper('assess-mobile-batch-kernel')
            assert base.sha(Path(scalar.__file__))==REVIEW_SHA
            scalar.review(receipt,mode,nonce,pid,1,'Android.x64',state['appHashes']['RuneCLR.Abstractions.dll'])
            marker=f'MOBILE_BATCH_KERNEL_COMPLETE nonce={nonce} pid={pid} mode={mode} callbacks=4'
            assert (out/'managed.log').read_text().count(marker)==1 and native.count(marker)==1
        maps=(out/'maps.log').read_text()
        for name in ('libcoreclr.so','libclrinterpreter.so','libclrjit.so'):
            actual=set(re.findall(r'(?m)(/[^\s]+/'+re.escape(name)+r')$',maps))
            assert actual=={native_dir+'/'+name}
        after=base.inventory(args,state,out,'installed-after',native_dir)
        assert before==after
        assert not (observer/'capture-errors.json').exists()
        entries=base.load(observer/'interpreter-entries.json')
        settlements=base.load(observer/'settlements.json')
        assert len(entries)>=2 and all(e['metadataMethodName']=='RuneCLR.BatchKernel.Kernel.Execute' for e in entries)
        assert len(settlements)==4 and [e['kind'] for e in settlements]==['full','full','tail','tail']
        assert [e['entryEsi'] for e in settlements[:2]]==[CONFIGURED,CONFIGURED]
        assert all(0<e['entryEsi']<CONFIGURED for e in settlements[2:])
        assert len({e['embeddedMeter'] for e in settlements})==1
        assert base.load(observer/'observation-disabled.json')['allObservationBreakpointsDisabled']
        debug=base.load(observer/'debugger-result.json')
        assert debug['exited'] and debug['errors']==0 and debug['pid']==pid and debug['runId']==nonce
        result.update(passed=True,contexts=2,callbacks=8,checksum=12749776,dispatchDelta=2100016,
                      fullSamples=[e['entryEsi'] for e in settlements[:2]],tailSamples=[e['entryEsi'] for e in settlements[2:]],
                      installedUnchanged=True,installedEntries=len(before),sameProcessNoConfigRecovery=True,
                      resumedFunctionalCompletion=True,initializeExecuteShutdownZero=True,
                      actualDebuggerExitStatus=debug['exitStatus'],observationDisabledAfterCoverage=True,
                      executionVerified=True,liveBatchPathVerified=False,performanceMeasured=False)
'''

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--android-root',type=Path,default=Path('D:/RuneCLR-Android'))
    p.add_argument('--serial',default='emulator-5556');p.add_argument('--timeout',type=int,default=300)
    p.add_argument('--interval',type=int,choices=(100,1000),required=True)
    args=p.parse_args()
    source_path=Path(__file__).with_name('android-batch-boundary-entry-run.py')
    assert hashlib.sha256(source_path.read_bytes()).hexdigest()==BASE_SHA
    old=helper('android-batch-boundary-entry-run')
    source=inspect.getsource(old.transport)
    source=source.replace('RuneCLR_BatchBoundary_','RuneCLR_BatchKernel_')
    source=source.replace('android-batch-boundary-entry-capture.py','android-batch-kernel-capture.py')
    source=source.replace('boundary-inputs-20261014-attempt1','kernel-inputs-20261015-attempt3')
    source=source.replace("'boundary.json'","'high.json', 'recovery.json'")
    source=source.replace("'--pid', str(pid), '--nonce', nonce, '--package', pkg, '--output', str(observer)]",
        "'--pid', str(pid), '--nonce', nonce, '--package', pkg, '--output', str(observer), '--interval', str(CONFIGURED), '--contract', 'E:/RuneCLR/artifacts/mobile-budget-batching/android-kernel-contract-20261015-attempt1']")
    start=source.index("        managed, receipt =")
    end=source.index('    except Exception:',start)
    source=source[:start]+COMPLETION+source[end:]
    source=re.sub(r'\b100\b',str(args.interval),source)
    source=source.replace("'64'",repr('64' if args.interval==100 else '3e8'))
    source=source.replace('interval=64','interval='+('64' if args.interval==100 else '3e8'))
    source=source.replace('Four initial interpreter entries only; no dispatch cadence or performance claim; independent review required',
        'Two full and two unsafe Flush active Kernel RecordBatch entries; independent review required; no timing claim')
    kernel=helper('android-batch-kernel-apk').adapted()[0]
    original_helper=old.helper
    def frozen(name):
        if name=='android-batch-boundary-apk':return kernel
        if name=='assess-mobile-batch-kernel':return helper(name)
        return original_helper(name)
    env=dict(old.__dict__);env.update(helper=frozen,__file__=__file__,CONFIGURED=args.interval,
        HEX='64' if args.interval==100 else '3e8',REVIEW_SHA=REVIEW_SHA)
    exec(compile(source,str(Path(__file__).resolve()),'exec'),env)
    return env['transport'](args)

if __name__=='__main__':raise SystemExit(main())
