#!/usr/bin/env python3
"""Run sixteen fresh owned Android processes with direct callback timing brackets."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import traceback
import uuid

PINS={'android-batch-timing-apk':'275a0b98780e06781327d22b0343a2ca368a16b0a31db6d2c847d3374a6fd666',
      'android-batch-boundary-entry-install':'58fa6da44ff2eaf3a4f6fcf35e1c370cfe90bce7891a9d1934fee283a04d6dfb',
      'review-android-batch-timing':'6491d61802cffad1c8a5d25438d5d8c9c80e5102c5290cc10d533ef9c0fda8f1'}
PROFILES=(('exact-before','best-exact','0','1'),('N100','N100','64','0'),
          ('N1000','N1000','3e8','0'),('exact-after','best-exact','0','1'))

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
    with Path(p).open('x',encoding='ascii') as s:s.write(json.dumps(v,indent=2)+chr(10))
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def helper(name):
    p=Path(__file__).with_name(name+'.py');assert sha(p)==PINS[name]
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),p)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def utc():return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def plan():
    return [{'profile':profile,'lane':lane,'intervalHex':hexcode,'derived':derived,'pair':pair,'mode':mode,
             'label':profile+'-pair'+str(pair)+'-'+mode,'warmups':3,'sampleCount':31}
            for profile,lane,hexcode,derived in PROFILES for pair in range(2)
            for mode in (('no-config','high-budget') if pair==0 else ('high-budget','no-config'))]

def quiet(path):
    script='Get-CimInstance Win32_Process | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress'
    q=subprocess.run(['C:/Program Files/PowerShell/7/pwsh.exe','-NoProfile','-Command',script],
                     capture_output=True,text=True,timeout=30)
    assert q.returncode==0
    records=[]
    for row in json.loads(q.stdout):
        pid=row['ProcessId'];name=(row['Name'] or '').lower();cmd=row['CommandLine'] or ''
        if pid==os.getpid():continue
        reason=None
        if name in ('lldb.exe','lldb-server.exe','clang.exe','clang++.exe','cl.exe','crossgen2.exe',
                    'ninja.exe','cmake.exe','csc.exe','msbuild.exe'):reason='compiler-or-debugger'
        if name=='dotnet.exe' and re.search(r'\bbuild\b|\bmsbuild\b|csc\.dll|benchmark|BatchOverhead',cmd,re.I):
            reason='managed-build-or-benchmark'
        if name.startswith('python') and re.search(r'benchmark[^ /\\]*\.py|entry-capture\.py|entry-run\.py|source-proof\.py|compile-assessment\.py|batch-timing-run\.py',cmd,re.I):
            reason='other-experiment-worker'
        records.append({'pid':pid,'name':name,'commandSha256':hashlib.sha256(cmd.encode()).hexdigest(),'blockedReason':reason})
    result={'passed':not any(r['blockedReason'] for r in records),'controllerPid':os.getpid(),
            'processes':records,'capturedUtc':utc(),
            'scope':'Windows compiler/debugger/recognized experiment process gate; unrelated OS load and affinity uncontrolled'}
    write(path,result);assert result['passed'],'Quiet gate rejected concurrent work; retained process hashes'

def run(a):
    base=helper('android-batch-timing-apk').adapted();installer=helper('android-batch-boundary-entry-install')
    review=helper('review-android-batch-timing')
    base.device(a);state=read(a.apk/'state.json');assert state['installed'] and state['authorHashes']
    assert sha(state['apk'])==state['apkSha256'] and sha(a.apk/'layout.json')==state['layoutSha256']
    a.output.mkdir(parents=True,exist_ok=False)
    shutil.copy2(__file__,a.output/'driver.py')
    write(a.output/'request.json',{'schema':'runeclr.android-batch-timing.run.v1','controllerPid':os.getpid(),
        'driverSha256':sha(__file__),'dependencyPins':PINS,'application':str(a.apk.resolve()),
        'inputDirectory':str(a.inputs.resolve()),'plan':plan(),'sourceCommit':state['runtimeCommit'],
        'sourceTree':state['runtimeTree'],'apkSha256':state['apkSha256'],'layoutSha256':state['layoutSha256'],
        'inputManifestSha256':state['inputManifestSha256'],'debugger':False,'settleSeconds':30,
        'physicalDeviceVerified':False,'performanceVerified':False,'startedUtc':utc()})
    appinfo=base.adb(a,['shell','dumpsys','package',state['package']])[0]
    match=re.search(r'(?m)^\s*(?:legacyNativeLibraryDir|nativeLibraryDir)=([^\s]+)',appinfo);assert match
    rows=base.adb(a,['shell','run-as',state['package'],'find',match[1],'-name','libcoreclr.so'])[0].splitlines();assert len(rows)==1
    native_dir=rows[0].rsplit('/',1)[0]
    before=installer.inventory(base,a,state,a.output,'installed-before',native_dir)
    component=review.bind_application(a.apk,a.output/'installed-before.json')
    write(a.output/'binding.json',{'success':True,'externalContractComponentSha256':component,
        'managedLocationExpectedAbsent':True,'installedEntries':len(before),'apkSha256':state['apkSha256'],
        'layoutSha256':state['layoutSha256'],'timingHostComponentSha256':state['appHashes']['MobileBatchTimingProbe.dll'],
        'nativeSha256':state['appHashes']['libcoreclr.so']})
    result={'passed':False,'observations':[],'nativeEntryProof':False,'liveBatchPathVerified':False,
            'physicalDeviceVerified':False,'performanceVerified':False,'platform':'Android.x64'}
    try:
        base.adb(a,['shell','am','force-stop',state['package']])
        quiet(a.output/'quiet-before-settle.json');started=time.monotonic();started_utc=utc()
        time.sleep(30)
        write(a.output/'settle.json',{'passed':True,'seconds':time.monotonic()-started,
                                    'startedUtc':started_utc,'endedUtc':utc(),'requiredSeconds':30})
        for cell in plan():
            out=a.output/cell['label'];out.mkdir();quiet(out/'quiet-before.json')
            nonce=uuid.uuid4().hex;pkg=state['package'];adbexe=a.android_root/'sdk/platform-tools/adb.exe'
            base.adb(a,['shell','am','force-stop',pkg])
            env={'RUNECLR_BATCH_NONCE':nonce,'RUNECLR_TIMING_MODE':cell['mode'],'RUNECLR_TIMING_LANE':cell['lane'],
                 'RUNECLR_TIMING_SAMPLES':'31','RUNECLR_TIMING_HEX':cell['intervalHex'],'RUNECLR_TIMING_DERIVED':cell['derived']}
            argv=[str(adbexe),'-s',a.serial,'shell','am','instrument','-w']
            for key,value in env.items():argv+=['-e','env:'+key,value]
            argv+=[pkg+'/net.dot.MonoRunner']
            request={**cell,'nonce':nonce,'environment':env,'argv':argv,'timeoutSeconds':a.timeout,
                     'startedUtc':utc(),'apkSha256':state['apkSha256'],'contractComponentSha256':component,'debugger':False}
            write(out/'request.json',request)
            with (out/'instrumentation.log').open('xb') as stream:
                child=subprocess.Popen(argv,stdout=stream,stderr=subprocess.STDOUT)
                write(out/'process-started.json',{'pid':child.pid,'argv':argv,'startedUtc':utc(),
                    'controllerPid':os.getpid(),'scope':'ADB instrumentation child; actual application PID independently queried'})
                timed_out=False
                try:code=child.wait(timeout=a.timeout)
                except subprocess.TimeoutExpired:
                    timed_out=True;base.adb(a,['shell','am','force-stop',pkg],False);child.kill();code=child.wait()
            write(out/'process.json',{'pid':child.pid,'exitCode':code,'timedOut':timed_out,'endedUtc':utc(),
                                    'instrumentationSha256':sha(out/'instrumentation.log')})
            assert code==0 and not timed_out
            for suffix,name in [('native.log','native.log'),('managed.log','managed.log'),
                    ('managed-result.json','managed-result.json'),('maps.log','maps.log'),
                    ('timing.json','receipt.json'),('pid-query.txt','pid-query.txt')]:
                q=subprocess.run([str(adbexe),'-s',a.serial,'exec-out','run-as',pkg,'cat','files/batch-'+nonce+'.'+suffix],
                                 capture_output=True,timeout=60)
                (out/name).write_bytes(q.stdout);(out/(name+'.pull-stderr.log')).write_bytes(q.stderr)
                write(out/(name+'.pull.json'),{'exitCode':q.returncode,'argv':q.args});assert q.returncode==0
            managed=read(out/'managed-result.json');pid=managed['appPid']
            assert managed=={'nonce':nonce,'mode':cell['mode'],'lane':cell['lane'],'samples':'31',
                             'interval':cell['intervalHex'],'exitCode':0,'appPid':pid}
            assert (out/'pid-query.txt').read_text().strip()=='android.os.Process.myPid='+str(pid)
            assert pid not in {row['processId'] for row in result['observations']}
            native=(out/'native.log').read_text()
            marker=f"TIMING_NATIVE pid={pid} nonce={nonce} mode={cell['mode']} lane={cell['lane']} samples=31 interval={cell['intervalHex']} DerivedLedger={cell['derived']} PhaseAcquireLoad=1 InterpMode=0 ReadyToRun=1"
            for value in (marker,'CORECLR_INITIALIZE_HRESULT=0x0','CORECLR_EXECUTE_HRESULT=0x0;RUNECLR_EXIT=0','CORECLR_SHUTDOWN_HRESULT=0x0'):
                assert len(re.findall(r'(?m)^'+re.escape(value)+r'$',native))==1
            complete=f"MOBILE_BATCH_TIMING_COMPLETE nonce={nonce} pid={pid} lane={cell['lane']} mode={cell['mode']} callbacks=34"
            assert native.count(complete)==(out/'managed.log').read_text().count(complete)==1
            instrumentation=(out/'instrumentation.log').read_text()
            assert re.findall(r'^INSTRUMENTATION_RESULT: return-code=([0-9-]+)\r?$',instrumentation,re.M)==['0']
            assert re.findall(r'^INSTRUMENTATION_CODE: ([0-9-]+)\r?$',instrumentation,re.M)==['0']
            maps=(out/'maps.log').read_text()
            for name in ('libcoreclr.so','libclrinterpreter.so','libclrjit.so'):
                assert set(re.findall(r'(?m)(/[^\s]+/'+re.escape(name)+r')$',maps))=={native_dir+'/'+name}
            receipt=read(out/'receipt.json');checked=review.review_observation(receipt,cell['mode'],cell['lane'],nonce,pid,31,component)
            write(out/'scalar-review.json',checked);quiet(out/'quiet-after.json')
            observation={**cell,'nonce':nonce,'processId':pid,'receipt':cell['label']+'/receipt.json',
                         'receiptSha256':sha(out/'receipt.json'),'passed':True,'callbacks':34,'collections':1,
                         'instrumentationAndManagedAndHRESULTsZero':True,'managedLocationAbsent':True}
            result['observations'].append(observation);write(out/'results.json',observation)
            write(a.output/('progress-'+str(len(result['observations']))+'.json'),result)
            print('ANDROID_TIMING_CELL_PASS',cell['label'],pid,flush=True)
        after=installer.inventory(base,a,state,a.output,'installed-after',native_dir);assert before==after
        result.update(passed=True,processes=16,callbacks=544,measuredCallbacks=496,collections=16,
                      installedUnchanged=True,installedEntries=len(after),sameProfilePairedModes=True,
                      debugger=False,settleSeconds=30,completedUtc=utc())
    except Exception:result['error']=traceback.format_exc()
    finally:
        base.adb(a,['shell','am','force-stop',state['package']],False)
        result['rawHashes']=base.files(a.output);write(a.output/'results.json',result)
    print('ANDROID_TIMING_RUN_PASS' if result['passed'] else 'ANDROID_TIMING_RUN_FAILED',len(result['observations']),flush=True)
    return 0 if result['passed'] else 1

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apk',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--inputs',type=Path,default=Path('artifacts/mobile-budget-batching/timing-inputs-20261015-attempt1'))
    p.add_argument('--android-root',type=Path,default=Path('D:/RuneCLR-Android'))
    p.add_argument('--serial',default='emulator-5556');p.add_argument('--timeout',type=int,default=300)
    return run(p.parse_args())

if __name__=='__main__':raise SystemExit(main())
