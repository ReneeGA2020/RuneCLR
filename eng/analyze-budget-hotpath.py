#!/usr/bin/env python3
"""Offline CDB analysis of the actual matching private Release DLL/PDB; no runtime runs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
COMMIT='099dacd07d8d890822f7422f895337733457ab3c'
CHECKER_PATH=Path(__file__).with_name('budget-runtime-candidate.py')
_spec=importlib.util.spec_from_file_location('budget_runtime_candidate',CHECKER_PATH)
_candidate=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_candidate)

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value): Path(path).write_text(json.dumps(value,indent=2),encoding='utf-8')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--runtime',default='E:/runtime-finalizer-20261013')
    parser.add_argument('--build',default=str(ROOT/'artifacts/budget-overhead/windows-release-build-20261013-attempt1'))
    parser.add_argument('--candidate-commit',default=COMMIT)
    args=parser.parse_args()
    output,runtime,build=Path(args.output).resolve(),Path(args.runtime).resolve(),Path(args.build).resolve()
    output.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(__file__,output/'analysis-driver.py')
    shutil.copyfile(CHECKER_PATH,output/CHECKER_PATH.name)
    product=runtime/'artifacts/bin/coreclr/windows.x64.Release'
    source_files=('src/coreclr/vm/interpexec.cpp','src/coreclr/vm/runeclrinstructionmeter.h',
                  'src/coreclr/binder/inc/customassemblybinder.h','src/coreclr/inc/volatile.h')
    validation=_candidate.validate(runtime,args.candidate_commit)
    head=validation['candidateCommit']
    receipt=json.loads((build/'build-result.json').read_text())
    if receipt['exitCode']!=0 or receipt['candidateCommit']!=head or receipt['configuration']!='Release':
        raise RuntimeError('Matching successful Release build required.')
    for name in ('coreclr.dll','clrinterpreter.dll','System.Private.CoreLib.dll'):
        if sha(product/name)!=receipt['criticalProductHashes'][name]: raise RuntimeError('Product mismatch: '+name)
    cdb=Path('C:/Program Files (x86)/Windows Kits/10/Debuggers/x64/cdb.exe')
    files={str(product/'coreclr.dll'):sha(product/'coreclr.dll'),
           str(product/'PDB/coreclr.pdb'):sha(product/'PDB/coreclr.pdb'),str(cdb):sha(cdb),
           str(CHECKER_PATH):sha(CHECKER_PATH)}
    for relative in source_files:
        target=output/'source'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(runtime/relative,target)
        files[str(runtime/relative)]=sha(target)
    for name in ('build-result.json','native-commands.txt','CMakeCache.txt'):
        shutil.copyfile(build/name,output/name)
    commands='lmvm coreclr; x coreclr!*RuneCLRInstructionMeter*; x coreclr!*RuneCLRChargeCurrentInstruction*; dt coreclr!RuneCLRInstructionMeter; dt coreclr!InterpMethodContextFrame; uf /o coreclr!InterpExecMethod; q'
    (output/'commands.txt').write_text(commands,encoding='ascii')
    argv=[str(cdb),'-z',str(product/'coreclr.dll'),'-y',str(product/'PDB'),'-c',commands]
    started=time.time()
    with (output/'cdb.stdout').open('wb') as stdout,(output/'cdb.stderr').open('wb') as stderr:
        process=subprocess.Popen(argv,stdout=stdout,stderr=stderr)
        save(output/'request.json',{'candidateCommit':head,'configuration':'Release','files':files,'argv':argv,
                                 'candidateValidation':validation,'runtime':str(runtime),
                                 'pid':process.pid,'buildResultSha256':sha(build/'build-result.json'),
                                 'nativeCommandsSha256':sha(build/'native-commands.txt'),'driverSha256':sha(__file__),
                                 'scope':'offline native machine-code/symbol inspection, not runtime CPU sampling or a timed benchmark'})
        code=process.wait(timeout=120)
    stdout=(output/'cdb.stdout').read_text(encoding='utf-8',errors='replace')
    locks=[line.strip() for line in stdout.splitlines() if 'lock ' in line]
    passed=code==0 and 'coreclr!InterpExecMethod:' in stdout and 'private pdb symbols' in stdout and 'm_phase' in stdout and bool(locks)
    binary=(product/'coreclr.dll').read_bytes()
    pe=struct.unpack_from('<I',binary,0x3c)[0]
    optional=pe+24
    image_base=struct.unpack_from('<Q',binary,optional+24)[0]
    count=struct.unpack_from('<H',binary,pe+6)[0]
    optional_size=struct.unpack_from('<H',binary,pe+20)[0]
    sections=[]
    for index in range(count):
        section=optional+optional_size+40*index
        virtual_size,rva,raw_size,raw_pointer=struct.unpack_from('<IIII',binary,section+8)
        sections.append((rva,max(virtual_size,raw_size),raw_pointer))
    instructions=[]
    for line in stdout.splitlines():
        match=re.match(r'^([0-9a-f]{8}`[0-9a-f]{8}) ([0-9a-f]+)\s+(.+)$',line)
        if not match: continue
        address=int(match.group(1).replace('`',''),16)
        rva=address-image_base
        machine=bytes.fromhex(match.group(2))
        section=next((entry for entry in sections if entry[0]<=rva<entry[0]+entry[1]),None)
        if section is None: raise RuntimeError('Disassembly instruction does not map into actual DLL.')
        raw_offset=section[2]+rva-section[0]
        if binary[raw_offset:raw_offset+len(machine)]!=machine:
            raise RuntimeError('CDB machine bytes differ from actual DLL at RVA '+hex(rva))
        instructions.append({'address':hex(address),'rva':hex(rva),'bytes':machine.hex(),'assembly':match.group(3)})
    save(output/'instructions.json',instructions)
    passed=passed and bool(instructions)
    result={'passed':passed,'exitCode':code,'elapsedSeconds':time.time()-started,'offlineOnly':True,
            'requestSha256':sha(output/'request.json'),'stdoutSha256':sha(output/'cdb.stdout'),'stderrSha256':sha(output/'cdb.stderr'),
            'instructionsSha256':sha(output/'instructions.json'),'actualPeByteMatches':len(instructions),
            'lockInstructionRows':locks,'claim':'actual Release DLL/PDB instruction inventory; path frequency/cycle attribution not established'}
    save(output/'results.json',result)
    for path,expected in files.items():
        if sha(path)!=expected: raise RuntimeError('Analysis input changed: '+path)
    if _candidate.validate(runtime,args.candidate_commit)!=validation:
        raise RuntimeError('Analysis source candidate changed.')
    print(json.dumps({'passed':passed,'exitCode':code,'lockRows':len(locks),'offlineOnly':True},indent=2))
    if not passed: raise RuntimeError('Offline observer checks failed; retain raw attempt.')

if __name__=='__main__': main()
