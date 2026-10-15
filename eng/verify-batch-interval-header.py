#!/usr/bin/env python3
"""Compile and execute actual batch candidate headers; no runtime build or timing."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path('E:/runtime-batch-interval-20261014')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    old=ROOT/'eng/verify-derived-ledger-header.py'
    spec=importlib.util.spec_from_file_location('native_fixture_tools',old)
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    inputs={}
    for original,name in ((RUNTIME/'src/coreclr/vm/runeclrinstructionmeter.h','candidate-meter.h'),
                          (RUNTIME/'src/coreclr/vm/runeclrbatchstate.h','candidate-state.h'),
                          (ROOT/'eng/batch-interval-header-probe/probe.cpp','probe.cpp'),
                          (Path(__file__),'driver.py'),(old,'original-driver.py')):
        shutil.copyfile(original,output/name);inputs[str(original)]=h.sha(original)
    (output/'request.json').write_text(json.dumps({'inputHashes':inputs,'compiler':str(h.COMPILER),'compilerSha256':h.sha(h.COMPILER)},indent=2))
    argv=[str(h.COMPILER),'/nologo','/O2','/std:c++17','/EHsc','/Zp8','/MT','/volatile:ms','/I'+str(h.MSVC/'include')]
    argv+=['/I'+str(h.KIT/'Include'/h.KIT_VERSION/d) for d in ('ucrt','shared','um')]
    argv+=['/Fo'+str(output/'probe.obj'),'/Fe'+str(output/'probe.exe'),str(output/'probe.cpp'),'/link',
           '/LIBPATH:'+str(h.MSVC/'lib/x64'),'/LIBPATH:'+str(h.KIT/'Lib'/h.KIT_VERSION/'ucrt/x64'),'/LIBPATH:'+str(h.KIT/'Lib'/h.KIT_VERSION/'um/x64')]
    _,compile_result=h.invoke(argv,output,'compile',120)
    process,run_result=h.invoke([str(output/'probe.exe')],output,'run',120)
    result=json.loads(process.stdout)
    if not result['passed'] or result['size']!=72 or [x['interval'] for x in result['cadence']] != [1,100,1000]:
        raise RuntimeError('Native semantic/cadence/layout inventory differs.')
    if any(h.sha(path)!=expected for path,expected in inputs.items()):
        raise RuntimeError('Header/fixture changed during native test.')
    (output/'results.json').write_text(json.dumps({'passed':True,'semantics':result,'compile':compile_result,'run':run_result,
        'inputHashes':inputs,'exeSha256':h.sha(output/'probe.exe'),'fullRuntimeBuilt':False,'performanceMeasured':False,
        'scope':'Actual candidate headers with real x64 MSVC intrinsics; post-admitted overshoot, partial/owner/unwind/cleanup/saturation and two live batch controls; not interpreter or CLR EH execution evidence.'},indent=2))
    print(json.dumps(result))

if __name__=='__main__': main()
