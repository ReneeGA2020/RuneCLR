#!/usr/bin/env python3
"""Capture actual full and partial long-kernel RecordBatch invocations."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
import uuid

ENTRY_SHA='7190100e7e353e0090265bcfd9a6cac9df68702b4c3c335c166c525c7abb0504'
APP_SHA='4fecea104d0f74e1b38a9cb6753aff1466c6332ae8cc4212d9c2a63896ab23a1'
PREPARE_SHA='5956effd1046633755e6db7f70915ed8d4f1725cfa579fc7a0b740a1f76d99a8'
ACCEPT_SHA='d2bee86ffed7438f8b0fd7206e7569ff1ed4daf5331a5de090c5ccee996d0656'
REVIEW_SHA='8fc1563dede9273f6c2a2f065fdf8ceb6afe86130d975cbf9826a180b91deacf'

OBSERVER=r'''import json
from pathlib import Path
import lldb
OUT=Path(__file__).parent
CONFIG=json.loads((OUT/'capture-config.json').read_text())
SAMPLES,ERRORS,GATES=[],[],[]
HITS={'record':0,'gate':0}
RECORD=None
PARTIAL_BPS=[]
PENDING=None

def save(name,value): (OUT/name).write_text(json.dumps(value,indent=2)+chr(10))
def memory(process,address,size):
    error=lldb.SBError();data=process.ReadMemory(address,size,error)
    if error.Fail() or len(data)!=size: raise RuntimeError(str(error))
    return data
def integer(process,address,size=8): return int.from_bytes(memory(process,address,size),'little')
def count(kind): return sum(s['kind']==kind for s in SAMPLES)
def complete(): return count('full')>=2 and count('partial')>=2
def disable():
    if RECORD is not None: RECORD.SetEnabled(False)
    for bp in PARTIAL_BPS: bp.SetEnabled(False)
def fail(kind,frame,error):
    ERRORS.append({'kind':kind,'pc':frame.GetPC(),'error':str(error)});save('capture-errors.json',ERRORS);disable()

def owner(frame,batch_address,meter,admitted):
    process=frame.GetThread().GetProcess()
    if process.GetProcessID()!=CONFIG['pid']: raise RuntimeError('Owned target PID differs')
    offsets=CONFIG['layouts']['RuneCLRBatchState']['fields']
    batch={key:integer(process,batch_address+value,4 if key=='m_pending' else 8) for key,value in offsets.items()}
    if batch['m_meter']!=meter or batch['m_pending']!=admitted: raise RuntimeError('Live batch meter/pending differs from invocation ABI')
    fields=CONFIG['layouts']['RuneCLRInstructionMeter']['fields']
    sizes={'m_terminalPrototype':1,'m_phaseAcquireLoad':1,'m_derivedLedger':1,'m_phase':4,'m_batchInterval':4}
    state={key:integer(process,meter+value,sizes.get(key,8)) for key,value in fields.items()}
    if state['m_terminalPrototype']!=1 or state['m_phaseAcquireLoad']!=1 or state['m_derivedLedger']!=0 or state['m_phase']!=0:
        return None
    if state['m_batchInterval']!=CONFIG['interval']: raise RuntimeError('Actual meter batch interval differs')
    item=decode(lambda a,n:memory(process,a,n),batch['m_frame'],0,CONFIG)
    if item is None: return None
    if item['metadataMethodName']!='RuneCLR.BatchKernel.Kernel.Execute': return None
    if item['bytecodeStart']!=batch['m_start']: raise RuntimeError('Live batch start differs from owned Kernel bytecode')
    item.update(batchAddress=batch_address,batch=batch,meterAddress=meter,meter=state,admitted=admitted)
    return item

def batch_in_frame(frame):
    base=frame.FindRegister('x19').GetValueAsUnsigned();address=base+CONFIG['batchLocalOffset']
    value=frame.FindVariable('runeclrBatch')
    if not value.IsValid() or value.GetError().Fail() or value.GetLoadAddress()!=address:
        raise RuntimeError('Exact live caller DWARF batch location differs from unwound x19')
    return address,base

def physical_frames(thread):
    frames=[thread.GetFrameAtIndex(i) for i in range(thread.GetNumFrames())]
    save('last-native-stack.json',[{'index':i,'inlined':f.IsInlined(),'pc':f.GetPC(),
         'filePc':f.GetPCAddress().GetFileAddress(),'function':f.GetFunctionName(),
         'module':f.GetModule().GetFileSpec().GetFilename()} for i,f in enumerate(frames[:12])])
    return [f for f in frames if not f.IsInlined()]

def partial_gate(frame,location,internal):
    global PENDING
    HITS['gate']+=1
    try:
        if HITS['gate']>CONFIG['hitCap']: raise RuntimeError('Partial gate hit cap exceeded')
        if complete(): disable();return False
        file_pc=frame.GetPCAddress().GetFileAddress()
        if file_pc not in CONFIG['gatePcs']: raise RuntimeError('Current partial native callsite differs')
        process=frame.GetThread().GetProcess()
        admitted=frame.FindRegister('w1').GetValueAsUnsigned()
        if not 0<admitted<CONFIG['interval']: return False
        native=physical_frames(frame.GetThread())
        if not native or 'InterpExecMethod(' not in (native[0].GetFunctionName() or ''):
            raise RuntimeError('Partial gate has no exact physical interpreter frame')
        batch,base=batch_in_frame(native[0])
        item=owner(frame,batch,frame.FindRegister('x0').GetValueAsUnsigned(),admitted)
        if item is None: return False
        PENDING={'threadId':frame.GetThread().GetThreadID(),'callPc':frame.GetPC(),'fileCallPc':file_pc,
                 'batchAddress':batch,'meterAddress':item['meterAddress'],'admitted':admitted,'x19':base,
                 'methodDesc':item['methodDesc'],'bytecodeStart':item['bytecodeStart']}
        GATES.append(PENDING);save('partial-gates.json',GATES)
        RECORD.SetEnabled(True)
    except Exception as error: fail('partial-gate',frame,error)
    return False

def settlement(frame,location,internal):
    global PENDING
    HITS['record']+=1
    try:
        if HITS['record']>CONFIG['hitCap']: raise RuntimeError('Actual settlement hit cap exceeded')
        if frame.GetPC()!=CONFIG['recordLoadPc']: raise RuntimeError('Actual RecordBatch function entry differs')
        thread=frame.GetThread();process=thread.GetProcess();target=process.GetTarget()
        lr=frame.FindRegister('x30').GetValueAsUnsigned()
        native=physical_frames(thread)
        if len(native)<3: raise RuntimeError('Actual settlement native unwind incomplete')
        caller=native[1]
        # LLDB gives outer native frames an inlined-scope PC. The first inner
        # frame retains the actual return PC, independently checked against LR.
        return_frame=thread.GetFrameAtIndex(1)
        file_return=target.ResolveLoadAddress(lr).GetFileAddress()
        if lr!=return_frame.GetPC() or file_return!=return_frame.GetPCAddress().GetFileAddress():
            raise RuntimeError('Actual LR differs from exact inner unwind return PC')
        if file_return==CONFIG['admitReturnPc']:
            interp=native[2]
            if 'RuneCLRBatchState::Admit' not in (caller.GetFunctionName() or ''):
                raise RuntimeError('Exact full-batch caller function differs')
            batch,base=batch_in_frame(interp)
            if frame.FindRegister('x22').GetValueAsUnsigned()!=batch: raise RuntimeError('Live Admit batch register differs from caller unwind/DWARF')
            basis='Exact Admit return PC and live x22 bound to unwound invocation x19/DWARF'
        else:
            if PENDING is None or PENDING['threadId']!=thread.GetThreadID() or lr!=PENDING['callPc']+4 or file_return!=PENDING['fileCallPc']+4:
                raise RuntimeError('Partial exact invocation lacks matching native callsite gate')
            interp=caller;batch,base=batch_in_frame(interp)
            if batch!=PENDING['batchAddress'] or base!=PENDING['x19']: raise RuntimeError('Partial exact caller unwind differs from gate')
            basis='Exact current inlined Flush callsite, live LR, caller unwind and DWARF'
        if 'InterpExecMethod(' not in (interp.GetFunctionName() or ''): raise RuntimeError('Exact interpreter caller function differs')
        admitted=frame.FindRegister('w1').GetValueAsUnsigned();meter=frame.FindRegister('x0').GetValueAsUnsigned()
        item=owner(frame,batch,meter,admitted)
        if item is None: return False
        kind='full' if admitted==CONFIG['interval'] else 'partial'
        if not 0<admitted<=CONFIG['interval']: raise RuntimeError('Actual admitted chunk outside meter interval')
        if kind=='partial' and PENDING is not None:
            if any(item[k]!=PENDING[k] for k in ('meterAddress','admitted','methodDesc','bytecodeStart')):
                raise RuntimeError('Actual partial settlement differs from precise gate')
        if count(kind)<2:
            item.update(kind=kind,pid=process.GetProcessID(),threadId=thread.GetThreadID(),pc=frame.GetPC(),
                        nativeFilePc=CONFIG['record']['filePc'],callerReturnPc=lr,callerFileReturnPc=file_return,
                        physicalCallerPc=caller.GetPC(),physicalCallerFilePc=caller.GetPCAddress().GetFileAddress(),
                        interpreterCallerPc=interp.GetPC(),interpreterCallerFilePc=interp.GetPCAddress().GetFileAddress(),
                        callerX19=base,callerProof=basis,recordHit=HITS['record'],
                        stack=[{'pc':thread.GetFrameAtIndex(i).GetPC(),'filePc':thread.GetFrameAtIndex(i).GetPCAddress().GetFileAddress(),
                                'function':thread.GetFrameAtIndex(i).GetFunctionName(),'module':thread.GetFrameAtIndex(i).GetModule().GetFileSpec().GetFilename()}
                               for i in range(min(8,thread.GetNumFrames()))])
            SAMPLES.append(item);save('settlement-samples.json',SAMPLES)
            print('KERNEL_ACTUAL_RECORD_BATCH '+json.dumps(item),flush=True)
        PENDING=None
        if complete(): disable()
        elif count('full')>=2:
            RECORD.SetEnabled(False)
            for bp in PARTIAL_BPS: bp.SetEnabled(True)
    except Exception as error: fail('settlement',frame,error)
    return False

def setup():
    global RECORD
    target=lldb.debugger.GetSelectedTarget();process=target.GetProcess()
    if process.GetProcessID()!=CONFIG['pid']: raise RuntimeError('Owned PID differs')
    modules=[target.GetModuleAtIndex(i) for i in range(target.GetNumModules()) if target.GetModuleAtIndex(i).GetFileSpec().GetFilename()=='libcoreclr.dylib']
    if len(modules)!=1: raise RuntimeError('Loaded native ambiguous')
    native=modules[0]
    if native.GetUUIDString().replace('-','').lower()!=CONFIG['nativeUuid'] or str(native.GetFileSpec())!=CONFIG['installedNative']:
        raise RuntimeError('Actual loaded signed native UUID/path differs')
    for name,expected in CONFIG['layouts'].items():
        kind=target.FindFirstType(name)
        if not kind.IsValid() or kind.GetByteSize()!=expected['size']: raise RuntimeError('Live current DWARF type size differs: '+name)
        for field,value in expected['fields'].items():
            matches=[kind.GetFieldAtIndex(i) for i in range(kind.GetNumberOfFields()) if kind.GetFieldAtIndex(i).GetName()==field]
            if len(matches)!=1 or matches[0].GetOffsetInBytes()!=value: raise RuntimeError('Live current DWARF member differs: '+name+'.'+field)
    record=native.ResolveFileAddress(CONFIG['record']['filePc'])
    if not record.GetSymbol().IsValid() or record.GetSymbol().GetStartAddress().GetFileAddress()!=CONFIG['record']['filePc']:
        raise RuntimeError('Exact RecordBatch symbol entry differs')
    CONFIG['recordLoadPc']=record.GetLoadAddress(target)
    if memory(process,CONFIG['recordLoadPc'],64).hex()!=CONFIG['recordPrefixHex']: raise RuntimeError('Loaded RecordBatch entry bytes differ')
    RECORD=target.BreakpointCreateByAddress(CONFIG['recordLoadPc'])
    if RECORD.GetNumLocations()!=1: raise RuntimeError('Actual settlement breakpoint ambiguous')
    RECORD.SetScriptCallbackFunction('kernel_lldb.settlement')
    for item in CONFIG['gates']:
        address=native.ResolveFileAddress(item['filePc']);load=address.GetLoadAddress(target)
        if memory(process,load,4).hex()!=item['bytesHex']: raise RuntimeError('Current precise partial callsite bytes differ')
        bp=target.BreakpointCreateByAddress(load)
        if bp.GetNumLocations()!=1: raise RuntimeError('Precise partial gate breakpoint ambiguous')
        bp.SetScriptCallbackFunction('kernel_lldb.partial_gate');bp.SetEnabled(False);PARTIAL_BPS.append(bp)
    save('breakpoints.json',{'pid':CONFIG['pid'],'nativeUuid':CONFIG['nativeUuid'],'recordFilePc':CONFIG['record']['filePc'],
         'recordLoadPc':CONFIG['recordLoadPc'],'recordPrefixHex':CONFIG['recordPrefixHex'],
         'gateCount':len(PARTIAL_BPS),'admitReturnPc':CONFIG['admitReturnPc'],'layoutsValidated':CONFIG['layouts'],
         'batchLocalOffset':CONFIG['batchLocalOffset'],'partialInitiallyDisabled':True})

def safe_setup():
    try: setup()
    except Exception as error:
        ERRORS.append({'kind':'setup','error':str(error)});save('capture-errors.json',ERRORS);disable()
        lldb.debugger.GetSelectedTarget().GetProcess().Kill();raise
def finish():save('capture-hits.json',{'hits':HITS,'samples':len(SAMPLES),'errors':len(ERRORS),'full':count('full'),'partial':count('partial'),
    'complete':complete(),'recordDisabled':RECORD is not None and not RECORD.IsEnabled(),'allGatesDisabled':all(not bp.IsEnabled() for bp in PARTIAL_BPS)})
'''


def execute(a):
    def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    def module(name,p,d):
        if sha(p)!=d:raise RuntimeError('Frozen helper differs: '+str(p))
        spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    entry=module('frozen_entry',a.entry_tool,ENTRY_SHA)
    app_tool=module('frozen_kernel_app',a.application_tool,APP_SHA)
    prepare=module('frozen_prepare',a.prepare_tool,PREPARE_SHA)
    accepted=module('frozen_accept',a.accept_tool,ACCEPT_SHA)
    review=module('frozen_kernel_review',Path(__file__).with_name('assess-mobile-batch-kernel.py'),REVIEW_SHA)
    need,read,write,inventory=entry.need,entry.read,entry.write,entry.inventory
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    result={'passed':False,'nativeEntryProof':False,'liveBatchPathVerified':False,'performanceMeasured':False,'physicalDeviceVerified':False}
    sim,booted,launched,unified=None,False,False,None
    try:
        manifest=app_tool.inputs(a.inputs);state=read(a.application/'state.json');provenance=read(a.application/'kernel-provenance.json')
        identity=read(a.prepare/'identity.json');plan=read(a.prepare/'observer-plan.json')
        app=Path(state['app']);before=inventory(app)
        need(before==state['bundleHashes'] and provenance['passed'] and provenance['driverSha256']==APP_SHA and
             provenance['inputManifestSha256']==app_tool.INPUT_SHA and provenance['trustedHostRawSha256']==app_tool.HOST_SHA,
             'New kernel signed app/input provenance differs')
        native=a.runtime/'artifacts/bin/coreclr/iossimulator.arm64.Release/libcoreclr.dylib';dwarf=native.with_name(native.name+'.dwarf')
        need(prepare.native(native)==identity['sourceNative'] and sha(native)==prepare.SOURCE_NATIVE_SHA and sha(dwarf)==identity['dwarfSha256'], 'Current native/DWARF differs')
        signed=prepare.native(app/'libcoreclr.dylib')
        need({k:v for k,v in signed.items() if k!='sha256'}=={k:v for k,v in identity['sourceNative'].items() if k!='sha256'} and
             signed['sha256']==state['native']['sha256'],'New signed native differs from matching source code/UUID')
        proof=a.runtime.parent/'source-proof.json'
        need(sha(proof)==prepare.PROOF_SHA and all(sha(a.runtime/n)==d for n,d in read(proof)['sourceHashes'].items()) and
             accepted.cap(['git','-C',a.runtime,'rev-parse','HEAD'])==prepare.COMMIT and
             accepted.cap(['git','-C',a.runtime,'rev-parse','HEAD^{tree}'])==prepare.TREE and
             not accepted.cap(['git','-C',a.runtime,'status','--porcelain','--untracked-files=no']), 'Matching live source differs')
        pe=prepare.readers();contract=app/'RuneCLR.Abstractions.dll'
        need(sha(contract)==provenance['contractComponentSha256'] and pe['pe_mvid'](contract)['moduleMvid']==app_tool.CONTRACT_MVID,
             'New R2R shared contract provenance differs')
        method='RuneCLR.BatchKernel.Kernel.Execute';author=a.inputs/'author/RuneCLR.BatchKernel.dll'
        methods=pe['plugin_methods'](author,required=(method,),qualified=True)
        bound={'sha256':sha(author),'methods':methods,**pe['pe_mvid'](author)}
        need(bound['sha256']==app_tool.AUTHOR_SHA and prepare.il_layout(author)=={'ilOnly':True,'managedNativeRva':0},'Frozen late author differs')
        record=identity['symbols']['settlement'];blob=native.read_bytes();section=identity['sourceNative']['sections']['__TEXT,__text']
        def code_at(pc,size):
            offset=section['offset']+pc-section['address'];need(section['offset']<=offset and offset+size<=section['offset']+section['length'],'Native PC outside current text');return blob[offset:offset+size]
        raw=(a.cadence_layout/'invocation-disassembly.txt').read_text()
        gates=[{'filePc':int(m[1],16),'bytesHex':int(m[2],16).to_bytes(4,'little').hex()} for m in re.finditer(
            r'^\s*([0-9a-f]+): ([0-9a-f]{8})\s+bl\s+0x'+format(record['filePc'],'x')+r'\s',raw,re.M)]
        need(len(gates)==347 and all(code_at(g['filePc'],4).hex()==g['bytesHex'] for g in gates),'Current exact partial callsites differ')
        admit=(a.prepare/'admit-instructions.txt').read_text()
        calls=re.findall(r'^\s*([0-9a-f]+): ([0-9a-f]{8})\s+bl\s+0x'+format(record['filePc'],'x')+r'\s',admit,re.M)
        need(len(calls)==1 and code_at(int(calls[0][0],16),4)==int(calls[0][1],16).to_bytes(4,'little'),'Current exact Admit settlement caller differs')
        admit_return=int(calls[0][0],16)+4
        frozen={str(p.resolve()):sha(p) for p in (a.application/'state.json',a.application/'kernel-provenance.json',a.inputs/'input-manifest.json',
                a.prepare/'identity.json',a.prepare/'observer-plan.json',a.cadence_layout/'invocation-disassembly.txt',native,dwarf)}
        write(out/'request.json',{'driverSha256':sha(__file__),'configuredInterval':a.interval,'samplesPerKind':2,'frozenInputs':frozen,
              'sourceNativeSha256':sha(native),'signedNative':signed,'contractComponentSha256':sha(contract),'author':bound,
              'scope':'Debugger instrumented actual RecordBatch only; no timing or device proof.'})
        sim=accepted.cap(['xcrun','simctl','create','RuneCLR-Kernel-Cadence',a.device_type,a.sim_runtime]);write(out/'owned-simulator.json',{'id':sim,'bundleId':state['bundleId']})
        entry.process_command(['xcrun','simctl','boot',sim],out/'boot.log',60);booted=True
        entry.process_command(['xcrun','simctl','bootstatus',sim,'-b'],out/'bootstatus.log',180)
        entry.process_command(['xcrun','simctl','install',sim,app],out/'install.log',60)
        installed=Path(accepted.cap(['xcrun','simctl','get_app_container',sim,state['bundleId'],'app']))
        data=Path(accepted.cap(['xcrun','simctl','get_app_container',sim,state['bundleId'],'data']))
        need(inventory(installed)==before,'Installed signed kernel app differs')
        plugin=data/'Documents/kernel-plugin';plugin.mkdir(parents=True,exist_ok=False)
        for name in ('RuneCLR.BatchKernel.dll','RuneCLR.Abstractions.dll'):
            shutil.copy2(a.inputs/'author'/name,plugin/name);need(sha(plugin/name)==manifest['files']['author/'+name],'Late installed author/contract differs')
        author_before=inventory(plugin);write(out/'installed-before.json',before);write(out/'author-before.json',author_before)
        nonce=uuid.uuid4().hex;env={k:v for k,v in os.environ.items() if not k.startswith(('DOTNET_','COMPlus_','RUNECLR_',
              'SIMCTL_CHILD_DOTNET_','SIMCTL_CHILD_COMPlus_','SIMCTL_CHILD_RUNECLR_'))}
        env.update({'SIMCTL_CHILD_RUNECLR_BATCH_NONCE':nonce,'SIMCTL_CHILD_RUNECLR_BATCH_MATRIX':str(a.interval),
                    'SIMCTL_CHILD_RUNECLR_BATCH_HEX':format(a.interval,'x')})
        entry.process_command(['xcrun','simctl','launch','--wait-for-debugger','--stdout='+str(out/'native.stdout.log'),
             '--stderr='+str(out/'native.stderr.log'),sim,state['bundleId']],out/'launch.log',60,env);launched=True
        found=re.fullmatch(re.escape(state['bundleId'])+r': (\d+)\s*',(out/'launch.log').read_text());need(found is not None,'Owned launch marker differs');pid=int(found[1])
        bound['path']=str(plugin/'RuneCLR.BatchKernel.dll')
        config={'pid':pid,'nonce':nonce,'interval':a.interval,'author':bound,'layouts':identity['layouts'],'record':record,
                'recordPrefixHex':code_at(record['filePc'],64).hex(),'gates':gates,'gatePcs':[g['filePc'] for g in gates],
                'admitReturnPc':admit_return,'batchLocalOffset':plan['cadenceLanes']['batchLocal']['offset'],
                'nativeUuid':signed['uuid'],'installedNative':str(installed/'libcoreclr.dylib'),'hitCap':10000}
        need(config['layouts']['RuneCLRInstructionMeter']['size']==72 and config['layouts']['RuneCLRInstructionMeter']['fields']['m_batchInterval']==64 and
             config['batchLocalOffset']==296,'Current meter or invocation-local layout differs')
        write(out/'capture-config.json',config)
        decoder=entry.DECODER;need(decoder.count("'BatchBoundary.Author'")==1,'Frozen decoder anchor differs')
        source=OBSERVER.replace('\ndef owner(',decoder.replace("'BatchBoundary.Author'","'RuneCLR.BatchKernel'")+'\ndef owner(',1)
        compile(source,'kernel_lldb.py','exec');(out/'kernel_lldb.py').write_text(source,encoding='ascii')
        commands=['breakpoint set -n coreclr_initialize','continue','breakpoint disable 1','target symbols add "'+str(dwarf)+'"',
              'command script import "'+str(out/'kernel_lldb.py')+'"','script kernel_lldb.safe_setup()','continue','process status','script kernel_lldb.finish()','quit']
        (out/'capture.lldb').write_text(chr(10).join(commands)+chr(10),encoding='ascii')
        query=['xcrun','simctl','spawn',sim,'log','stream','--style','json','--predicate','processIdentifier == '+str(pid)]
        with (out/'unified.log').open('x') as messages,(out/'unified.stderr.log').open('x') as errors:
            unified=subprocess.Popen(query,stdout=messages,stderr=errors,start_new_session=True);write(out/'unified-query.json',{'pid':unified.pid,'targetPid':pid,'argv':query})
            try:entry.process_command(['xcrun','lldb','--batch','--attach-pid',str(pid),'--source',out/'capture.lldb'],out/'lldb.log',a.timeout)
            finally:
                if unified.poll() is None:os.killpg(unified.pid,signal.SIGINT)
                try:unified.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(unified.pid,signal.SIGKILL);unified.wait(timeout=10)
                write(out/'unified-exit.json',{'pid':unified.pid,'exitCode':unified.returncode})
        hits=read(out/'capture-hits.json')
        need(hits['complete'] and hits['full']==hits['partial']==2 and hits['errors']==0 and hits['recordDisabled'] and hits['allGatesDisabled'] and
             not (out/'capture-errors.json').exists(),'Actual full/partial settlement coverage failed')
        samples=read(out/'settlement-samples.json')
        bp=read(out/'breakpoints.json');need(bp['recordFilePc']==record['filePc'] and all(s['pc']==bp['recordLoadPc'] for s in samples),'Actual RecordBatch entry differs')
        for sample in samples:
            need(sample['pid']==pid and sample['modulePath']==bound['path'] and sample['moduleMvid']==bound['moduleMvid'] and
                 sample['loadedMetadataMvidValidated'] and sample['fileSha256']==bound['sha256'] and
                 sample['metadataMethodName']==method and sample['methodDefToken']==methods[method] and
                 sample['batch']['m_pending']==sample['admitted'] and sample['batch']['m_meter']==sample['meterAddress'] and
                 sample['batch']['m_start']==sample['bytecodeStart'] and sample['batchAddress']==sample['callerX19']+296 and
                 ((sample['kind']=='full' and sample['admitted']==a.interval) or (sample['kind']=='partial' and 0<sample['admitted']<a.interval)),
                 'Actual owned Kernel settlement sample differs')
        lldb_log=(out/'lldb.log').read_text();need(re.search(r'^Process '+str(pid)+r' exited with status = 0 \(0x00000000\)\s*$',lldb_log,re.M),'Target did not exit normally')
        log=chr(10).join((out/n).read_text(errors='replace') for n in ('native.stdout.log','native.stderr.log'))
        u=(out/'unified.log').read_text();first,last=u.find('['),u.rfind(']');events=json.loads(u[first:last+1]) if first>=0 and last>=first else []
        need(isinstance(events,list) and all(e.get('processID')==pid for e in events),'Unified log contains another process')
        log+=chr(10)+chr(10).join(e.get('eventMessage','') for e in events);(out/'combined-native.log').write_text(log,encoding='utf-8')
        marker=f'KERNEL_NATIVE pid={pid} nonce={nonce} matrix={a.interval} interval={a.interval:x} PhaseAcquireLoad=1 DerivedLedger=0 InterpMode=0 ReadyToRun=1'
        need(log.splitlines().count(marker)==1 and log.splitlines().count('CORECLR_INITIALIZE_HRESULT=0x0')==1 and
             log.splitlines().count('CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0')==1,'Native PID/settings/HRESULT completion differs')
        observations={}
        for name,mode in (('high','high-budget'),('recovery','no-config')):
            shutil.copy2(data/('Documents/kernel-'+name+'-'+nonce+'.json'),out/(name+'-receipt.json'));actual=read(out/(name+'-receipt.json'))
            assessed=review.review(actual,mode,nonce,pid,1,'iossimulator.arm64',provenance['contractComponentSha256'])
            write(out/(name+'-assessment.json'),assessed)
            need(actual['passed'] and actual['processId']==pid and actual['nonce']==nonce and actual['mode']==mode and
                 actual['architecture']=='Arm64' and actual['runtime'].startswith('.NET 12.') and actual['collected'] and
                 actual['loadedContractComponentHash']==provenance['contractComponentSha256'] and
                 actual['contractMvid']==app_tool.CONTRACT_MVID and actual['authorHash']==app_tool.AUTHOR_SHA and
                 actual['sampleCount']==1 and len(actual['Rows'])==4 and all(r['Checksum']==12749776 for r in actual['Rows']) and
                 accepted.completed(log,f'MOBILE_BATCH_KERNEL_COMPLETE nonce={nonce} pid={pid} mode={mode} callbacks=4',pid),
                 'Kernel ledger/recovery receipt identity or completion differs')
            if name=='high':
                need(actual['RetiredGetterRejections']==8 and actual['Final']['Executed']==8400064 and
                     actual['Final']['Remaining']==1000000000000-8400064 and actual['Final']['Phase']==0 and
                     all(r['DispatchDelta']==2100016 for r in actual['Rows']),'Exact high-budget callback ledger differs')
            observations[name]=actual
        write(out/'installed-after.json',inventory(installed));write(out/'author-after.json',inventory(plugin))
        need(inventory(installed)==before==inventory(app) and inventory(plugin)==author_before and
             all(sha(p)==d for p,d in frozen.items()) and app_tool.inputs(a.inputs)==manifest,'Original/frozen app or author inputs changed')
        result.update(passed=True,nativeEntryProof=True,liveBatchPathVerified=True,configuredInterval=a.interval,pid=pid,nonce=nonce,
             fullSamples=2,partialSamples=2,admitted=[s['admitted'] for s in samples],callbackDispatchDelta=2100016,
             callbacksPerContext=4,contextsCollected=2,sameProcessRecovery=True,driverSha256=sha(__file__),observerSha256=sha(out/'kernel_lldb.py'),
             scope='Actual exact RecordBatch full/partial invocations bound to owned Kernel bytecode, native caller/unwind and meter; scalar ledger and fresh meterless recovery; debugger timings excluded.')
    except Exception as error:
        result['error']=str(error);raise
    finally:
        if launched:
            q=subprocess.run(['xcrun','simctl','terminate',sim,state['bundleId']],capture_output=True,text=True)
            write(out/'target-termination.json',{'exitCode':q.returncode,'stdout':q.stdout,'stderr':q.stderr})
        if booted:
            q=subprocess.run(['xcrun','simctl','shutdown',sim],capture_output=True,text=True)
            write(out/'cleanup.json',{'simulator':sim,'exitCode':q.returncode,'stdout':q.stdout,'stderr':q.stderr})
            result['cleanupSucceeded']=q.returncode==0
            if q.returncode!=0:result['passed']=False
        result['endedUtc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());write(out/'results.json',result);print(json.dumps(result,indent=2),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('entry-tool','application-tool','prepare-tool','accept-tool','runtime','application','prepare','inputs','cadence-layout','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--interval',type=int,choices=(100,1000),required=True)
    p.add_argument('--device-type',default='com.apple.CoreSimulator.SimDeviceType.iPhone-16')
    p.add_argument('--sim-runtime',default='com.apple.CoreSimulator.SimRuntime.iOS-27-0')
    p.add_argument('--timeout',type=int,default=180)
    execute(p.parse_args())


if __name__=='__main__':main()
