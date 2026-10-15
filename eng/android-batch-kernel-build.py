#!/usr/bin/env python3
"""Build fresh trusted Android Kernel bridge/layout using frozen current-runtime workflows."""
import argparse
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path

BASE_APK_SHA = '66adcf5a7a60a13db4695d43b2c4a18643ab39392d7f33884d74da7ba5e46c50'
BASE_LAYOUT_SHA = '263172e1a992d3ec64b97d72e1c8849ae730e129cd917a90769c1fd298b524c2'
INPUT_SHA = '76609966a4adae5171b5081864fd6835083b752240d12019495bca3fe468ffec'
HOST_SHA = 'ee9ea4e284ff2296f437e8a97e7ef16efffaa61a13240d8e7468e1f5aef9bb87'
AUTHOR_SHA = 'd743ecb6ba897366a276ab700e79a42f3885ba2eaf69d1713bb086346f2fd09e'
CONTRACT_SHA = 'ebfe72469b640b63991189123971beadbf9c3fe74d303a9b7ce66f87596a807b'
BRIDGE_NAME = 'AndroidBatchKernelBridge.dll'
BRIDGE = r'''using System; using System.IO; using System.Runtime.InteropServices; using System.Text.Json;
static class AndroidBatchKernelBridge {
 public static int Main(string[] ignored) {
  string root=AppContext.BaseDirectory;
  string nonce=Environment.GetEnvironmentVariable("RUNECLR_BATCH_NONCE")??throw new InvalidOperationException("nonce");
  string interval=Environment.GetEnvironmentVariable("DOTNET_RuneCLRBatchInterval")??throw new InvalidOperationException("interval");
  if(nonce.Length!=32 || (interval!="64" && interval!="3e8"))throw new InvalidOperationException("lane");
  string prefix=Path.Combine(root,"batch-"+nonce),author=Path.Combine(root,"author/RuneCLR.BatchKernel.dll");
  TextWriter stdout=Console.Out,stderr=Console.Error;int code=1;
  using(var stream=new StreamWriter(prefix+".managed.log"){AutoFlush=true}) {
   Console.SetOut(stream);Console.SetError(stream);
   try {
    Console.WriteLine($"ANDROID_KERNEL_MANAGED pid={Environment.ProcessId} nonce={nonce} interval={interval} arch={RuntimeInformation.ProcessArchitecture}");
    code=MobileBatchKernelProbe.Entry.Run(new[]{author,"high-budget",nonce,"1",prefix+".high.json"});
    if(code==0)code=MobileBatchKernelProbe.Entry.Run(new[]{author,"no-config",nonce,"1",prefix+".recovery.json"});
   } catch(Exception error){code=1;Console.Error.WriteLine("ANDROID_KERNEL_FAILURE type="+error.GetType().FullName);}
   finally {Console.SetOut(stdout);Console.SetError(stderr);}
  }
  File.WriteAllText(prefix+".maps.log",File.ReadAllText("/proc/self/maps"));
  File.WriteAllText(prefix+".managed-result.json",JsonSerializer.Serialize(new{nonce,interval,exitCode=code,appPid=Environment.ProcessId}));
  return code;
 }
}
'''

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def need(value, why):
    if not value: raise RuntimeError(why)
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def inputs(path):
    m=read(path/'input-manifest.json')
    need(sha(path/'input-manifest.json')==INPUT_SHA and m['schema']=='runeclr.mobile-batch-kernel.inputs.v1'
         and m['authorSha256']==AUTHOR_SHA and m['contractSha256']==CONTRACT_SHA
         and m['files']['host/MobileBatchKernelProbe.dll']==HOST_SHA and m['expectedDispatchDelta']==2100016
         and m['expectedChecksum']==12749776 and m['warmups']==3 and len(m['files'])==10,'Frozen Kernel inputs differ')
    need(all((path/n).resolve().is_relative_to(path.resolve()) and sha(path/n)==h for n,h in m['files'].items()),'Kernel bytes changed')
    return m

def module(path, expected):
    need(sha(path)==expected,'Frozen build workflow differs: '+str(path))
    spec=importlib.util.spec_from_file_location(path.stem.replace('-','_'),path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def bridge(a):
    base=module(a.base_tool,BASE_APK_SHA)
    source=inspect.getsource(base.bridge)
    source=source.replace('MobileBatchBoundaryProbe.dll','MobileBatchKernelProbe.dll').replace('BatchBoundary.Contract.dll','RuneCLR.Abstractions.dll').replace('AndroidBatchBoundaryBridge','AndroidBatchKernelBridge').replace('runeclr.android-batch-boundary.bridge.v1','runeclr.android-batch-kernel.bridge.v1')
    env=dict(base.__dict__);env.update(inputs=inputs,BRIDGE=BRIDGE,BRIDGE_NAME=BRIDGE_NAME,INPUT_SHA=INPUT_SHA,__file__=__file__)
    exec(compile(source,str(Path(__file__).resolve()),'exec'),env);env['bridge'](a)
    need(read(a.output/'bridge.json')['inputManifestSha256']==INPUT_SHA,'Kernel bridge ownership differs')

def layout(a):
    base=module(a.base_tool,BASE_LAYOUT_SHA)
    source=a.base_tool.read_text()
    replacements={
      '82ea9368e8fe6e7070b6d181e09c2294aed0aacb3d2008399ae92a15ae88d3fb':INPUT_SHA,
      'ios-batch-boundary-inputs-20261015-attempt1':'ios-kernel-inputs-20261015-attempt1',
      'runeclr.mobile-batch-boundary.inputs.v1':'runeclr.mobile-batch-kernel.inputs.v1',
      "inputs['expectedContexts'] == 168":"inputs['expectedDispatchDelta'] == 2100016",
      "inputs['configuredLanes'] == LANES and len(inputs['files']) == 9":"inputs['warmups'] == 3 and len(inputs['files']) == 10",
      'MobileBatchBoundaryProbe.dll':'MobileBatchKernelProbe.dll',
      'BatchBoundary.Contract.dll':'RuneCLR.Abstractions.dll',
      'BatchBoundary.Author.dll':'RuneCLR.BatchKernel.dll',
      'AndroidBatchBoundaryBridge.dll':BRIDGE_NAME,
      'RuneCLR.Android.BatchBoundary.Framework.dll':'RuneCLR.Android.BatchKernel.Framework.dll',
      'runeclr.android-batch-boundary.layout.v1':'runeclr.android-batch-kernel.layout.v1',
      'expectedContexts=168':'expectedContexts=2',
    }
    counts={}
    for old,new in replacements.items():
        counts[old]=source.count(old);need(counts[old]>0,'Frozen build anchor absent: '+old);source=source.replace(old,new)
    env=dict(base.__dict__);env.update(__name__='kernel_layout_adaptation',__file__=__file__)
    exec(compile(source,str(Path(__file__).resolve()),'exec'),env);env['build'](a)
    result=read(a.output/'layout/layout.json')
    need(result['inputManifestSha256']==INPUT_SHA and result['compositeInputCount']==184 and
         result['executableAssembly']==BRIDGE_NAME and result['expectedContexts']==2,'New Kernel layout differs')
    (a.output/'workflow-adaptation.json').write_text(json.dumps({'baseWorkflowSha256':BASE_LAYOUT_SHA,'driverSha256':sha(__file__),'replacementCounts':counts,'nativeBuildPerformed':False,'freshComposite':True},indent=2)+'\n')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=('bridge','layout'))
    for name in ('output','base-tool','root','inputs','runtime','framework','bridge','bridge-receipt','elf-helper','inventory-helper','metadata-inspector','typed-inspector'):
        p.add_argument('--'+name,type=Path)
    for name in ('bridge-sha256','bridge-receipt-sha256'):p.add_argument('--'+name)
    p.add_argument('--build-slot-granted',action='store_true');p.add_argument('--validate-only',action='store_true');p.add_argument('--timeout',type=int,default=900)
    a=p.parse_args();need(a.output and a.base_tool,'Fresh output and frozen base tool required')
    need(a.build_slot_granted,'Coordinated Mac resource slot required')
    if a.phase=='bridge':bridge(a)
    else:layout(a)

if __name__=='__main__':main()
