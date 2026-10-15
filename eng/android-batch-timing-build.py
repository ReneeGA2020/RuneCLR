#!/usr/bin/env python3
"""Build a fresh timing bridge/composite from the matching private Android products."""
import argparse
import ast
import hashlib
import importlib.util
from pathlib import Path

KERNEL_SHA='405ac0fd64dea388ccda49c505554e363f5ff3a43b4cca4226131cab9627d3b0'
INPUT_SHA='d8f2be284a6034ce415a740365b0b5f09dfdb57c66b1f3c1fad2e07ad327b98b'
HOST_SHA='1bce4d5dfd010dc7bc7cf0906ded8add1f2fdca6e8d8c4766c5dd88d54a8ec2a'
BRIDGE=r'''using System; using System.IO; using System.Runtime.InteropServices; using System.Text.Json;
static class AndroidBatchTimingBridge {
 public static int Main(string[] ignored) {
  string root=AppContext.BaseDirectory;
  string nonce=Environment.GetEnvironmentVariable("RUNECLR_BATCH_NONCE")??throw new InvalidOperationException("nonce");
  string mode=Environment.GetEnvironmentVariable("RUNECLR_TIMING_MODE")??throw new InvalidOperationException("mode");
  string lane=Environment.GetEnvironmentVariable("RUNECLR_TIMING_LANE")??throw new InvalidOperationException("lane");
  string samples=Environment.GetEnvironmentVariable("RUNECLR_TIMING_SAMPLES")??throw new InvalidOperationException("samples");
  string interval=Environment.GetEnvironmentVariable("DOTNET_RuneCLRBatchInterval")??throw new InvalidOperationException("interval");
  if(nonce.Length!=32 || samples!="31")throw new InvalidOperationException("request");
  string prefix=Path.Combine(root,"batch-"+nonce),author=Path.Combine(root,"author/RuneCLR.BatchKernel.dll");
  TextWriter stdout=Console.Out,stderr=Console.Error;int code=1;
  using(var stream=new StreamWriter(prefix+".managed.log"){AutoFlush=true}) {
   Console.SetOut(stream);Console.SetError(stream);
   try {
    Console.WriteLine($"ANDROID_TIMING_MANAGED pid={Environment.ProcessId} nonce={nonce} mode={mode} lane={lane} samples={samples} interval={interval} arch={RuntimeInformation.ProcessArchitecture}");
    code=MobileBatchTimingProbe.Entry.Run(new[]{author,mode,lane,nonce,samples,prefix+".timing.json"});
   } catch(Exception error){code=1;Console.Error.WriteLine("ANDROID_TIMING_FAILURE type="+error.GetType().FullName);}
   finally {Console.SetOut(stdout);Console.SetError(stderr);}
  }
  File.WriteAllText(prefix+".maps.log",File.ReadAllText("/proc/self/maps"));
  File.WriteAllText(prefix+".managed-result.json",JsonSerializer.Serialize(new{nonce,mode,lane,samples,interval,exitCode=code,appPid=Environment.ProcessId}));
  return code;
 }
}
'''

def adapted(path):
    assert hashlib.sha256(path.read_bytes()).hexdigest()==KERNEL_SHA
    source=path.read_text()
    for old,new in [
        ('76609966a4adae5171b5081864fd6835083b752240d12019495bca3fe468ffec',INPUT_SHA),
        ('ee9ea4e284ff2296f437e8a97e7ef16efffaa61a13240d8e7468e1f5aef9bb87',HOST_SHA),
        ('MobileBatchKernelProbe','MobileBatchTimingProbe'),('AndroidBatchKernelBridge','AndroidBatchTimingBridge'),
        ('RuneCLR.Android.BatchKernel.Framework.dll','RuneCLR.Android.BatchTiming.Framework.dll'),
        ('runeclr.mobile-batch-kernel.inputs.v1','runeclr.mobile-batch-timing.inputs.v1'),
        ('runeclr.android-batch-kernel.','runeclr.android-batch-timing.'),
        ('ios-kernel-inputs-20261015-attempt1','ios-timing-inputs-20261015-attempt1'),
        ('expectedContexts=2','expectedContexts=1'),("result['expectedContexts']==2","result['expectedContexts']==1")]:
        assert source.count(old)>0,old;source=source.replace(old,new)
    tree=ast.parse(source)
    changed=0
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='BRIDGE' for t in node.targets):
            node.value=ast.Constant(BRIDGE);changed+=1
    assert changed==1
    env={'__file__':__file__,'__name__':'timing_build_adaptation'}
    exec(compile(ast.fix_missing_locations(tree),str(Path(__file__).resolve()),'exec'),env)
    return env

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=('bridge','layout'));p.add_argument('--kernel-tool',type=Path,required=True)
    for name in ('output','base-tool','root','inputs','runtime','framework','bridge','bridge-receipt','elf-helper','inventory-helper','metadata-inspector','typed-inspector'):
        p.add_argument('--'+name,type=Path)
    for name in ('bridge-sha256','bridge-receipt-sha256'):p.add_argument('--'+name)
    p.add_argument('--build-slot-granted',action='store_true');p.add_argument('--validate-only',action='store_true');p.add_argument('--timeout',type=int,default=900)
    a=p.parse_args();assert a.build_slot_granted
    env=adapted(a.kernel_tool)
    env[a.phase](a)

if __name__=='__main__':main()
