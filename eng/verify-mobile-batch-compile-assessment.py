#!/usr/bin/env python3
"""Offline source-derived parser controls; do not run a compiler or mobile program."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil

ROOT=Path(__file__).resolve().parents[1]
HELPER=ROOT/'eng/mobile-batch-compile-assessment.py'
HELPER_SHA='de0b4215f210a44023c3a3a021563b502c46fd2dc7e0dec7e06ea109a64615da'
SOURCE=Path('E:/runtime-mobile-batch-interval-20261014/src/coreclr/vm')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    assert hashlib.sha256(HELPER.read_bytes()).hexdigest()==HELPER_SHA
    output.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(HELPER,output/'frozen-assessor.py');shutil.copyfile(__file__,output/'driver.py')
    spec=importlib.util.spec_from_file_location('frozen_mobile_compile_assessor',HELPER)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    ast.parse(HELPER.read_text(),feature_version=(3,9))
    text='\n'.join((SOURCE/n).read_text() for n in ('runeclrinstructionmeter.h','runeclrbatchstate.h','interpexec.cpp'))
    text=re.sub(r'INTOP_CASE\((INTOP_[A-Z0-9_]+)\)',r'LABEL_\1:',text)
    (output/'source-derived-fixture.cpp').write_text(text,encoding='utf-8')
    baseline=module.validate_preprocessed(text)
    mutants={
        'old-size64':('sizeof(RuneCLRInstructionMeter) == 72','sizeof(RuneCLRInstructionMeter) == 64'),
        'wrong-offset':('m_batchInterval) == 64','m_batchInterval) == 56'),
        'same47-but-overflow-danger':('case INTOP_ADD_I4:','case INTOP_ADD_OVF_I4:'),
        'same47-but-heap-danger':('case INTOP_SUB_I4:','case INTOP_NEWOBJ:'),
        'unsafe-flush-removed':('            batch.Flush();\n            if (!meter->IsTerminalPrototype())','            if (!meter->IsTerminalPrototype())'),
        'trap-flush-removed':('                        runeclrBatch.Flush();','                        ;'),
        'cleanup-owner-batched':('threadContext->runeclrCleanupOwner != meter','true'),
        'cleanup-exact-charge-removed':('return meter->TryChargeCleanup();','return true;'),
        'old-two-argument-dispatch':('RuneCLRChargeCurrentInstruction(pFrame, pThreadContext, runeclrBatch, opcode)','RuneCLRChargeCurrentInstruction(pFrame, pThreadContext)'),
        'owner-check-removed':('m_meter != meter || m_frame != frame || m_start != start','false'),
        'exact-saturation-removed':('AddSaturating(executed, 1);','InterlockedIncrement64(&executed);'),
    }
    controls=[]
    for name,(old,new) in mutants.items():
        assert text.count(old)==1,(name,text.count(old))
        changed=text.replace(old,new,1)
        try:module.validate_preprocessed(changed)
        except RuntimeError as error:controls.append({'name':name,'rejected':True,'reason':str(error)})
        else:raise AssertionError('Accepted negative control '+name)
    tokens=['/usr/bin/clang++','-Xclang','-include-pch','-Xclang','/obj/pch.pch','-include','/obj/pch.hxx',
            '-c','/src/interpexec.cpp','-o','/obj/interpexec.o','-MF','/obj/interpexec.d','-MD']
    assert module.preprocessing_command(tokens)==['/usr/bin/clang++','-include','/obj/pch.hxx','/src/interpexec.cpp','-E','-dD']
    # Clang expands offsetof into its builtin; this spelling must also be accepted.
    module.validate_preprocessed(text.replace('offsetof(RuneCLRInstructionMeter, m_batchInterval)',
                                              '__builtin_offsetof(RuneCLRInstructionMeter, m_batchInterval)'))
    assert hashlib.sha256(HELPER.read_bytes()).hexdigest()==HELPER_SHA
    result={'passed':True,'helperSha256':HELPER_SHA,'python39Syntax':True,'sourceDerivedSyntheticFixturePassed':True,
            'builtinOffsetofSpellingAccepted':True,'preprocessorOutputAndBinaryPchRemoved':True,
            'negativeControls':controls,'negativeControlCount':len(controls),'safeOpcodeCount':baseline['safeOpcodeCount'],
            'nativeMeterSize':72,'nativeBatchIntervalOffset':64,'actualCompilerRun':False,'nativeBuildPerformed':False,
            'executionVerified':False,'scope':'Offline source-derived parser/command controls only; not actual mobile preprocessing or compilation.'}
    (output/'results.json').write_text(json.dumps(result,indent=2),encoding='ascii')
    print(json.dumps({k:v for k,v in result.items() if k!='negativeControls'}))


if __name__=='__main__':main()
