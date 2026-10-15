#!/usr/bin/env python3
"""Assess actual mobile opcode compilation and replay preprocessing; no execution claim."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

COMMIT='3126bbc9a8851a09ac6435b18a12882bad48f3ee'
TREE='710936ae1729a5689ab0e0896f3cf722ddd3d31c'
HASHES={
    'src/coreclr/inc/clrconfigvalues.h':'a4b6aaa798c8ff20a17a52130314aa8b3447d469179fd1498973094e1e668405',
    'src/coreclr/vm/interpexec.cpp':'a624682569458053ebe0e4e2469e92eff840b30716b115727505715900faa557',
    'src/coreclr/vm/runeclrbatchstate.h':'194b97da0d517dd866918acdd29f35709a2739faae35d22d391354a53f3bd52e',
    'src/coreclr/vm/runeclrinstructionmeter.h':'aeca0411b5db0b425a198deb895540e25e714351f5f578fbb9eb73ce2b2a8fa3',
}
SAFE=set(('LDC_I4 LDC_I4_0 LDC_I8 LDC_I8_0 MOV_4 MOV_8 ADD_I4 ADD_I8 ADD_I4_IMM ADD_I8_IMM '
          'SUB_I4 SUB_I8 MUL_I4 MUL_I8 AND_I4 AND_I8 OR_I4 OR_I8 XOR_I4 XOR_I8 BR BRFALSE_I4 '
          'BRFALSE_I8 BRTRUE_I4 BRTRUE_I8 BEQ_I4 BEQ_I8 BNE_UN_I4 BNE_UN_I8 BGE_I4 BGE_I8 '
          'BGT_I4 BGT_I8 BLE_I4 BLE_I8 BLT_I4 BLT_I8 CEQ_I4 CEQ_I8 CGT_I4 CGT_I8 CLT_I4 CLT_I8 '
          'CONV_I8_I4 CONV_I8_U4 CONV_U8_U4 SAFEPOINT').split())


def require(value,message):
    if not value:raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    with Path(path).open('x',encoding='ascii') as stream:json.dump(value,stream,indent=2)


def compact(text):
    text=re.sub(r'/\*.*?\*/|//[^\r\n]*','',text,flags=re.S)
    return re.sub(r'\s+','',text)


def body(text,name):
    match=re.search(r'\b'+re.escape(name)+r'\s*\([^;{}]*\)[^;{}]*\{',text)
    require(match is not None,'Actual function body missing: '+name)
    start=text.index('{',match.start());depth=1;end=start+1
    while end<len(text) and depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    require(depth==0,'Unbalanced actual function body: '+name)
    return text[start:end]


def validate_preprocessed(text):
    expanded=re.sub(r'^#[^\r\n]*$','',text,flags=re.M)
    flat=compact(expanded)
    for assertion in ('sizeof(RuneCLRInstructionMeter)==72','alignof(RuneCLRInstructionMeter)==8',
                      'offsetof(RuneCLRInstructionMeter,m_batchInterval)==64'):
        require(assertion in flat,'Actual preprocessed layout assertion missing: '+assertion)
    safe=body(expanded,'RuneCLRIsBatchSafeOpcode')
    names=re.findall(r'case\s+INTOP_([A-Z0-9_]+)\s*:',safe)
    require(len(names)==47 and set(names)==SAFE,'Exact47 safe opcode classification differs.')
    require('returng_TrapReturningThreads==0;' in compact(safe),'Safe safepoint classification must test trap state.')
    charge=compact(body(expanded,'RuneCLRChargeCurrentInstruction'))
    require('threadContext->runeclrCleanupOwner!=meter&&RuneCLRIsBatchSafeOpcode(opcode))returnbatch.Admit(meter,frame,frame->startIp);batch.Flush();' in charge,
            'Unsafe dispatch must flush after safe-only/cleanup-exclusion branch.')
    require('returnmeter->TryChargeCleanup();' in charge and 'returnmeter->ChargeExecution();' in charge
            and charge.index('batch.Flush();')<charge.index('meter->IsTerminalPrototype()')
            and charge.endswith('batch.Flush();returntrue;}'),'Exact cleanup/unsafe/no-owner admission path differs.')
    macro=re.search(r'^#define INTOP_DISPATCH\(op\)[^\r\n]*$',text,re.M)
    require('#define USE_COMPUTED_GOTO 1' in text and macro is not None
            and 'RUNECLR_CHARGE_DISPATCH()' in macro.group(0) and 'goto *s_dispatchTable[opcode]' in macro.group(0)
            and 'RuneCLRChargeCurrentInstruction(pFrame,pThreadContext,runeclrBatch,opcode)' in flat
            and 'RuneCLRBatchStateruneclrBatch;' in flat and 'gotoRUNECLR_ABANDON_CLEANUP' in flat,
            'Actual computed-goto four-argument charging path missing.')
    trap_start=re.search(r'LABEL_INTOP_SAFEPOINT\s*:',expanded)
    require(trap_start is not None,'Actual computed-goto safepoint handler missing.')
    trap=expanded[trap_start.end():];next_label=re.search(r'\bLABEL_INTOP_[A-Z0-9_]+\s*:',trap)
    require(next_label is not None,'Next actual opcode handler missing.')
    trap=compact(trap[:next_label.start()])
    require('if(g_TrapReturningThreads){runeclrBatch.Flush();Thread*pThread=GetThread();' in trap
            and 'HandleThreadAbort' in trap,'Trap must flush pending debt inside trap branch before GC/abort work.')
    for snippet in ('m_derivedLedger&&m_batchInterval==0','AddSaturating(m_executed,admitted);',
                    'TryConsume(m_cleanupRemaining,m_cleanupExecuted,m_derivedLedger)',
                    'm_meter->RecordBatch(m_pending);','m_pending==meter->BatchInterval()',
                    'm_meter!=meter||m_frame!=frame||m_start!=start',
                    'if(saturating)AddSaturating(executed,1);'):
        require(snippet in flat,'Actual batch/cleanup/state contract missing: '+snippet)
    return {'safeOpcodes':['INTOP_'+n for n in names],'safeOpcodeCount':47,'nativeMeterSize':72,
            'nativeMeterAlignment':8,'nativeBatchIntervalOffset':64,'computedGotoBudgetPathCompiled':True,
            'unsafeFlushBeforeCharge':True,'actualTrapFlush':True,'cleanupAdmissionExact':True,
            'executionBatchCounterIndependent':True,'mixedExactCounterSaturates':True}


def preprocessing_command(tokens):
    result=[];i=0
    while i<len(tokens):
        if tokens[i:i+2]==['-Xclang','-include-pch']:
            require(i+3<len(tokens) and tokens[i+2]=='-Xclang','Unexpected actual PCH arguments.')
            i+=4
        elif tokens[i] in ('-o','-MF','-MT','-MQ'):
            require(i+1<len(tokens),'Missing actual output/dependency argument.');i+=2
        elif tokens[i] in ('-c','-MD','-MMD'):i+=1
        else:result.append(tokens[i]);i+=1
    return result+['-E','-dD']


def assess(source,obj,output):
    source,obj,output=[Path(p).resolve() for p in (source,obj,output)]
    def git(*args):return subprocess.check_output(['git','-C',str(source),*args],text=True).strip()
    require(git('rev-parse','HEAD')==COMMIT and git('rev-parse','HEAD^{tree}')==TREE
            and not git('status','--porcelain','--untracked-files=no'),'Exact clean mobile batch source required.')
    hashes={n:sha(source/n) for n in HASHES};require(hashes==HASHES,'Actual batch source differs from frozen LF blobs.')
    require(obj.is_relative_to(source),'Foreign actual object directory.')
    db=obj/'compile_commands.json';entries=json.loads(db.read_text())
    rows=[r for r in entries if Path(r['file']).resolve()==source/'src/coreclr/vm/interpexec.cpp'
          and 'cee_wks_core.dir' in r.get('output','')]
    require(len(rows)==1,'Unique actual opcode-meter compile row required.')
    row=rows[0];require(Path(row['directory']).resolve()==obj,'Actual compile directory differs.')
    object_file=(obj/row['output']).resolve()
    require(object_file.is_relative_to(obj) and object_file.is_file(),'Actual opcode-meter object missing/foreign.')
    tokens=row.get('arguments') or shlex.split(row['command'])
    defines={t[2:].partition('=')[0]:t[2:].partition('=')[2] or '1' for t in tokens if t.startswith('-D')}
    require({'FEATURE_INTERPRETER','NDEBUG'}<=set(defines) and not {'DEBUG','_DEBUG'}&set(defines)
            and any(flag in tokens for flag in ('-O2','-O3')),'Actual Release/interpreter compile flags missing.')
    if 'TARGET_IOS' in defines:
        require({'HOST_ARM64','TARGET_ARM64'}<=set(defines) and 'FEATURE_DYNAMIC_CODE_COMPILED' not in defines,
                'Actual iOS static-interpreter target features differ.')
    else:
        require({'HOST_ANDROID','HOST_AMD64','TARGET_AMD64','FEATURE_DYNAMIC_CODE_COMPILED'}<=set(defines),
                'Actual Android x64 interpreter target features differ.')
    compiler=Path(tokens[0]).resolve();require(compiler.is_file(),'Actual recorded compiler missing.')
    command=preprocessing_command(tokens)
    env={k:v for k,v in os.environ.items() if not k.startswith(('DOTNET_','COMPlus_','RUNECLR_'))
         and k not in ('CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','OBJC_INCLUDE_PATH','LIBRARY_PATH','SDKROOT',
                      'MACOSX_DEPLOYMENT_TARGET','CMAKE_PREFIX_PATH','PKG_CONFIG_PATH','EXTRA_CFLAGS','EXTRA_CXXFLAGS','EXTRA_LDFLAGS')}
    output.mkdir(parents=True,exist_ok=True)
    raw=output/'batch-interpexec.preprocessed.cpp';log=output/'batch-preprocess.stderr'
    before={'compileDatabase':sha(db),'object':sha(object_file),'compiler':sha(compiler)}
    with raw.open('xb') as stdout,log.open('xb') as stderr:
        process=subprocess.run(command,cwd=obj,env=env,stdout=stdout,stderr=stderr)
    save(output/'batch-preprocess-process.json',{'argv':command,'exitCode':process.returncode,'cwd':str(obj),
         'stdoutSha256':sha(raw),'stderrSha256':sha(log),'inputs':before,'compileRow':row})
    require(process.returncode==0,'Actual compiler preprocessing failed; raw streams retained.')
    result=validate_preprocessed(raw.read_text())
    require({n:sha(source/n) for n in HASHES}==HASHES and not git('status','--porcelain','--untracked-files=no')
            and before=={'compileDatabase':sha(db),'object':sha(object_file),'compiler':sha(compiler)},
            'Actual source/compile input changed during preprocessing.')
    result.update({'passed':True,'sourceCommit':COMMIT,'sourceTree':TREE,'sourceHashes':hashes,
                   'compileDatabase':str(db),'compileDatabaseSha256':sha(db),'actualObject':str(object_file),
                   'actualObjectSha256':sha(object_file),'compiler':str(compiler),'compilerSha256':sha(compiler),
                   'preprocessingCommand':command,'preprocessingExit':process.returncode,
                   'preprocessingSha256':sha(raw),'compileRow':row,'defines':defines,'assessorSha256':sha(__file__),
                   'batchIntervalEnvironmentRadix':16,'batchIntervalEnvironmentValues':{'1':'1','100':'64','1000':'3e8'},
                   'executionVerified':False,'performanceMeasured':False,
                   'scope':'Actual compiled object/flags and compiler preprocessing; no branch execution, bounds, timing or device proof.'})
    save(output/'batch-compile-assessment.json',result)
    return result
