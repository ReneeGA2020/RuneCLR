#!/usr/bin/env python3
"""Build an independent long-kernel app using the frozen batch-app build workflow."""
import argparse
import ast
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import types

ACCEPT_SHA = 'd2bee86ffed7438f8b0fd7206e7569ff1ed4daf5331a5de090c5ccee996d0656'
INPUT_SHA = '76609966a4adae5171b5081864fd6835083b752240d12019495bca3fe468ffec'
HOST_SHA = 'ee9ea4e284ff2296f437e8a97e7ef16efffaa61a13240d8e7468e1f5aef9bb87'
AUTHOR_SHA = 'd743ecb6ba897366a276ab700e79a42f3885ba2eaf69d1713bb086346f2fd09e'
CONTRACT_SHA = 'ebfe72469b640b63991189123971beadbf9c3fe74d303a9b7ce66f87596a807b'
CONTRACT_MVID = '92efbbd4-8ae3-4686-824b-bafe67f2dd69'
BRIDGE = '''using System; using MobileBatchKernelProbe; public static class SessionBridge {
 public static int Main(string[] args) {
  var d=Environment.GetEnvironmentVariable("RUNECLR_DOCUMENTS") ?? throw new InvalidOperationException("documents");
  var n=Environment.GetEnvironmentVariable("RUNECLR_BATCH_NONCE") ?? throw new InvalidOperationException("nonce");
  var p=d+"/kernel-plugin/RuneCLR.BatchKernel.dll";
  var result=Entry.Run(new[]{p,"high-budget",n,"1",d+"/kernel-high-"+n+".json"});
  return result==0 ? Entry.Run(new[]{p,"no-config",n,"1",d+"/kernel-recovery-"+n+".json"}) : result;
 }}
'''


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def need(value, message):
    if not value: raise RuntimeError(message)


def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def frozen_module(name, path, digest):
    need(sha(path) == digest, 'Frozen helper differs: ' + str(path))
    spec=importlib.util.spec_from_file_location(name, path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def inputs(root):
    manifest=read(root/'input-manifest.json')
    need(sha(root/'input-manifest.json') == INPUT_SHA and
         manifest['schema'] == 'runeclr.mobile-batch-kernel.inputs.v1' and
         manifest['authorSha256'] == AUTHOR_SHA and manifest['contractSha256'] == CONTRACT_SHA and
         manifest['contractMvid'] == CONTRACT_MVID and manifest['expectedDispatchDelta'] == 2100016 and
         manifest['expectedChecksum'] == 12749776 and manifest['iterations'] == 100000 and
         manifest['files']['host/MobileBatchKernelProbe.dll'] == HOST_SHA, 'Frozen kernel inputs differ')
    for name, digest in manifest['files'].items():
        path=(root/name).resolve()
        need(path.is_relative_to(root.resolve()) and sha(path)==digest, 'Kernel input changed: '+name)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('accept-tool','prepare-tool','inputs','runtime','build-receipt','baseline-app','wrapper-source',
                 'wrapper-assets','framework-input','framework-manifest','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    accepted=frozen_module('frozen_batch_app',args.accept_tool,ACCEPT_SHA)
    prepare=frozen_module('frozen_batch_layout',args.prepare_tool,
                          '5956effd1046633755e6db7f70915ed8d4f1725cfa579fc7a0b740a1f76d99a8')
    manifest=inputs(args.inputs)
    pe=prepare.readers()
    need(pe['pe_mvid'](args.inputs/'host/RuneCLR.Abstractions.dll')['moduleMvid']==CONTRACT_MVID and
         sha(args.inputs/'author/RuneCLR.Abstractions.dll')==CONTRACT_SHA and
         prepare.il_layout(args.inputs/'author/RuneCLR.BatchKernel.dll')=={'ilOnly':True,'managedNativeRva':0},
         'Raw shared contract or late author layout differs')
    source=inspect.getsource(accepted.build)
    tree=ast.parse(source)
    replacements={'MobileBatchBoundaryProbe.dll':'MobileBatchKernelProbe.dll',
                  'BatchBoundary.Contract.dll':'RuneCLR.Abstractions.dll',
                  'BatchBoundary.Author.dll':'RuneCLR.BatchKernel.dll',
                  'BUILD PASS: fresh batch boundary app; execution not yet verified':
                  'BUILD PASS: fresh long kernel app; execution not yet verified'}
    counts={key:0 for key in replacements}; bridge_changes=0
    for node in ast.walk(tree):
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value in replacements:
            counts[node.value]+=1; node.value=replacements[node.value]
        if (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and
                isinstance(node.func.value,ast.Name) and node.func.value.id=='bridge' and node.func.attr=='write_text'):
            node.args[0]=ast.Constant(BRIDGE);bridge_changes+=1
    need(counts=={'MobileBatchBoundaryProbe.dll':2,'BatchBoundary.Contract.dll':2,'BatchBoundary.Author.dll':1,
                  'BUILD PASS: fresh batch boundary app; execution not yet verified':1} and bridge_changes==1,
         'Frozen build adaptation anchors differ')
    namespace=dict(accepted.__dict__)
    namespace.update(inputs=inputs,__file__=__file__,wrapper=lambda p:accepted.wrapper(p).replace('BATCH_NATIVE pid=', 'KERNEL_NATIVE pid='))
    exec(compile(ast.fix_missing_locations(tree),str(args.accept_tool),'exec'),namespace)
    namespace['build'](args)
    state=read(args.output/'state.json');app=Path(state['app']);component=app/'RuneCLR.Abstractions.dll'
    need(pe['pe_mvid'](component)['moduleMvid']==CONTRACT_MVID and
         state['compositeInputs']['MobileBatchKernelProbe.dll']==HOST_SHA and
         state['compositeInputs']['RuneCLR.Abstractions.dll']==CONTRACT_SHA and
         not list(app.rglob('RuneCLR.BatchKernel.dll')) and inputs(args.inputs)==manifest,
         'Fresh trusted input/contract R2R provenance or author placement differs')
    accepted.write(args.output/'kernel-provenance.json',{'passed':True,'driverSha256':sha(__file__),
         'frozenWorkflowSha256':ACCEPT_SHA,'inputManifestSha256':INPUT_SHA,
         'trustedHostRawSha256':HOST_SHA,'authorSha256':AUTHOR_SHA,'contractRawSha256':CONTRACT_SHA,
         'contractIdentity':manifest['contractIdentity'],'contractMvid':CONTRACT_MVID,
         'contractComponentSha256':sha(component),'contractComponentMvid':pe['pe_mvid'](component)['moduleMvid'],
         'freshComposite':True,'nativeEntryProof':False,'liveBatchPathVerified':False,'performanceMeasured':False,
         'scope':'Independent new signed application; high-budget callback then fresh meterless recovery context; no execution claim.'})
    accepted.write(args.output/'adapted-build.json',{'constantReplacementCounts':counts,'bridgeReplacements':bridge_changes,
         'bridgeSha256':hashlib.sha256(BRIDGE.encode('ascii')).hexdigest(),'sourceSha256':hashlib.sha256(source.encode('ascii')).hexdigest()})


if __name__=='__main__':main()
