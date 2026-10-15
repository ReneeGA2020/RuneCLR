#!/usr/bin/env python3
"""Build an Android timing APK with validated native lane settings and no debugger gate."""
import argparse
import hashlib
import importlib.util
import inspect
from pathlib import Path
import shutil

BASE_SHA='66adcf5a7a60a13db4695d43b2c4a18643ab39392d7f33884d74da7ba5e46c50'
TIMING_SHA='ce4b764476dfa84d8644286babc3c0e903e720d47c0e227670809cf875143081'
NATIVE=r'''
    const char* nonce=getenv("RUNECLR_BATCH_NONCE");
    const char* mode=getenv("RUNECLR_TIMING_MODE");
    const char* lane=getenv("RUNECLR_TIMING_LANE");
    const char* samples=getenv("RUNECLR_TIMING_SAMPLES");
    const char* batch_hex=getenv("RUNECLR_TIMING_HEX");
    const char* derived=getenv("RUNECLR_TIMING_DERIVED");
    if (!nonce || !mode || !lane || !samples || !batch_hex || !derived || strlen(nonce)!=32 ||
        strspn(nonce,"0123456789abcdef")!=32 || strcmp(samples,"31") ||
        (strcmp(mode,"no-config") && strcmp(mode,"high-budget")) ||
        (strcmp(lane,"best-exact") && strcmp(lane,"N100") && strcmp(lane,"N1000"))) return -1;
    const char* expected_hex=!strcmp(lane,"N1000")?"3e8":!strcmp(lane,"N100")?"64":"0";
    const char* expected_derived=!strcmp(lane,"best-exact")?"1":"0";
    if (strcmp(batch_hex,expected_hex) || strcmp(derived,expected_derived)) return -1;
    char native_path[2048];
    snprintf(native_path,sizeof(native_path),"%s/batch-%s.native.log",g_bundle_path,nonce);
    if (freopen(native_path,"w",stdout)==NULL || dup2(fileno(stdout),fileno(stderr))<0) return -1;
    setvbuf(stdout,NULL,_IONBF,0);setvbuf(stderr,NULL,_IONBF,0);
    setenv("DOTNET_InterpMode","0",1);
    setenv("DOTNET_RuneCLRInterpretCollectible","0",1);
    setenv("DOTNET_ReadyToRun","1",1);setenv("DOTNET_TieredCompilation","0",1);
    setenv("DOTNET_MULTILEVEL_LOOKUP","0",1);setenv("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT","1",1);
    setenv("DOTNET_InterpList","0",1);unsetenv("DOTNET_InterpDump");
    unsetenv("DOTNET_JitDisasm");unsetenv("DOTNET_JitDisasmSummary");unsetenv("DOTNET_JitStdOutFile");
    setenv("DOTNET_RuneCLRPhaseAcquireLoad","1",1);
    setenv("DOTNET_RuneCLRDerivedLedger",derived,1);
    setenv("DOTNET_RuneCLRBatchInterval",batch_hex,1);
    unsetenv("DOTNET_RuneCLRInterpreterRefuseMethods");
    printf("TIMING_NATIVE pid=%d nonce=%s mode=%s lane=%s samples=%s interval=%s DerivedLedger=%s PhaseAcquireLoad=1 InterpMode=0 ReadyToRun=1\n",getpid(),nonce,mode,lane,samples,batch_hex,derived);
'''

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def helper(name,digest=None):
    p=Path(__file__).with_name(name+'.py')
    if digest:assert sha(p)==digest
    s=importlib.util.spec_from_file_location(name.replace('-','_'),p)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def adapted():
    base=helper('android-batch-boundary-apk',BASE_SHA)
    timing=helper('android-batch-timing-build',TIMING_SHA)
    kernel=Path(__file__).with_name('android-batch-kernel-build.py')
    inp=timing.adapted(kernel)['inputs']
    source=inspect.getsource(base.apk)
    for old,new in [('runeclr.android-batch-boundary.layout.v1','runeclr.android-batch-timing.layout.v1'),
        ("l['expectedContexts']==168","l['expectedContexts']==1"),('RuneCLR_BatchBoundary_','RuneCLR_BatchTiming_'),
        ('BatchBoundary.Author.dll','RuneCLR.BatchKernel.dll'),('BatchBoundary.Author.','RuneCLR.BatchKernel.')]:
        assert source.count(old)>0;source=source.replace(old,new)
    env=dict(base.__dict__);env.update(inputs=inp,INPUT_SHA=timing.INPUT_SHA,
        BRIDGE_NAME='AndroidBatchTimingBridge.dll',NATIVE=NATIVE,__file__=__file__)
    exec(compile(source,str(Path(__file__).resolve()),'exec'),env)
    base.apk=env['apk'];base.inputs=inp
    return base

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('output','layout','inputs'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--builder',type=Path,default=Path('D:/RuneCLR-Android/coreclr-smoke/run-20261012-172351/builder'))
    p.add_argument('--android-root',type=Path,default=Path('D:/RuneCLR-Android'))
    p.add_argument('--dotnet',type=Path,default=Path('E:/runtime/.dotnet/dotnet.exe'))
    a=p.parse_args();base=adapted();base.apk(a)
    shutil.copy2(__file__,a.output/'timing-apk-driver.py')
    base.write(a.output/'timing-build.json',{'success':True,'driverSha256':sha(__file__),
        'baseDriverSha256':BASE_SHA,'timingBuildDriverSha256':TIMING_SHA,
        'nativeSettingsSha256':hashlib.sha256(NATIVE.encode('ascii')).hexdigest(),
        'debuggerGate':False,'executionVerified':False,'performanceMeasured':False})

if __name__=='__main__':main()
