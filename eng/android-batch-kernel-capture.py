#!/usr/bin/env python3
"""Prepare exact-image Kernel full and unsafe-flush settlement observations."""
import argparse
import ast
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import re

BASE_SHA = 'c881847ff9a46eb2ab65226c1c908f13084026d34d48eb39b8bcbd45a99303f9'
AUTHOR_SHA = 'd743ecb6ba897366a276ab700e79a42f3885ba2eaf69d1713bb086346f2fd09e'
METHODS = ['RuneCLR.BatchKernel.Kernel.Execute']

def helper():
    p = Path(__file__).with_name('android-batch-boundary-entry-capture.py')
    assert hashlib.sha256(p.read_bytes()).hexdigest() == BASE_SHA
    s = importlib.util.spec_from_file_location('boundary_capture', p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

EXTRA = r'''
ACTIVE = {}
SETTLEMENTS = []
COUNTS = {'full': 0, 'tail': 0}
TAIL_BPS = []
RECORD_BP = None
EXPECTED_TAIL = None

def fail_capture(frame, error):
    ERRORS.append({'pc': frame.GetPC(), 'error': str(error)})
    (OUT / 'capture-errors.json').write_text(json.dumps(ERRORS, indent=2)+'\n')
    for bp in OBSERVATION_BPS: bp.SetEnabled(False)

def owner(process, frame_address, expected_start, expected_desc):
    target = process.GetTarget()
    start = field(typed(target, frame_address, 'InterpMethodContextFrame'), 'startIp')
    method = word(process, start)
    desc = word(process, method + OFFSETS['InterpMethod.methodHnd'])
    if start != expected_start or desc != expected_desc:
        raise RuntimeError('Active invocation frame/method bytecode ownership changed')
    chunk_index = read(process, desc + OFFSETS['MethodDesc.m_chunkIndex'], 1)[0]
    chunk = desc - TYPES['MethodDescChunk'].GetByteSize() - chunk_index * 8
    mt = word(process, chunk + OFFSETS['MethodDescChunk.m_methodTable'])
    module = typed(target, field(typed(target, mt, 'MethodTable'), 'm_pModule'), 'Module')
    pe = field(module, 'm_pPEAssembly')
    binder = word(process, pe + CONFIG['peBinderOffset'])
    meter = binder + CONFIG['binderMeterOffset']
    if read(process, meter, 4) != bytes([1, 1, 1, 0]):
        raise RuntimeError('Actual embedded meter flags differ')
    if int.from_bytes(read(process, meter+64, 4), 'little') != CONFIG['interval']:
        raise RuntimeError('Actual embedded interval differs')
    return pe, binder, meter

def begin(frame, entry):
    global ACTIVE
    process = frame.GetThread().GetProcess()
    # The precise entry precedes push RBP; emitted prologue establishes this frame base.
    rbp = frame.FindRegister('rsp').GetValueAsUnsigned() - 8
    pe, binder, meter = owner(process, entry['methodContextFrame'], entry['bytecodeStart'], entry['methodDesc'])
    entry.update(invocationRbp=rbp, embeddedMeter=meter, assemblyBinder=binder,
                 peAssembly=pe, threadId=frame.GetThread().GetThreadID())
    ACTIVE = dict(entry)
    (OUT/'interpreter-entries.json').write_text(json.dumps(ENTRIES,indent=2)+'\n')

def verify_active(frame, meter):
    process = frame.GetThread().GetProcess()
    if not ACTIVE or frame.GetThread().GetThreadID() != ACTIVE['threadId']:
        return None
    rbp = frame.FindRegister('rbp').GetValueAsUnsigned()
    if rbp != ACTIVE['invocationRbp']: return None
    live_frame = word(process, rbp-0xf48)
    if live_frame != ACTIVE['methodContextFrame']:
        raise RuntimeError('Emitted physical interpreter pFrame spill differs')
    pe, binder, owned_meter = owner(process, live_frame, ACTIVE['bytecodeStart'], ACTIVE['methodDesc'])
    if meter != owned_meter or meter != ACTIVE['embeddedMeter']:
        raise RuntimeError('RecordBatch meter is not active Kernel binder meter')
    return process, rbp, pe, binder

def tail_gate(frame, location, internal):
    global EXPECTED_TAIL
    HITS['tailGate'] = HITS.get('tailGate', 0)+1
    try:
        meter = frame.FindRegister('rdi').GetValueAsUnsigned()
        if verify_active(frame, meter) is None: return False
        admitted = frame.FindRegister('esi').GetValueAsUnsigned()
        if not 0 < admitted < CONFIG['interval']:
            raise RuntimeError('Unsafe Flush did not present a partial admitted batch')
        EXPECTED_TAIL = (frame.GetPC()+5, admitted, meter)
        RECORD_BP.SetEnabled(True)
    except Exception as error: fail_capture(frame,error)
    return False

def record(frame, location, internal):
    global EXPECTED_TAIL
    HITS['record'] = HITS.get('record',0)+1
    try:
        if frame.GetPC() != CONFIG['loadedRecordAddress']:
            raise RuntimeError('RecordBatch observation is not exact native entry')
        meter = frame.FindRegister('rdi').GetValueAsUnsigned()
        active = verify_active(frame,meter)
        if active is None: return False
        process, rbp, pe, binder = active
        admitted = frame.FindRegister('esi').GetValueAsUnsigned()
        rsp = frame.FindRegister('rsp').GetValueAsUnsigned()
        ret = word(process,rsp)
        retfile = process.GetTarget().ResolveLoadAddress(ret).GetFileAddress()
        if retfile not in CONFIG['allReturnPcs']:
            raise RuntimeError('Actual stack inner return PC is not a matched emitted callsite')
        if EXPECTED_TAIL is not None:
            if (ret, admitted, meter) != EXPECTED_TAIL:
                raise RuntimeError('Unsafe gate to actual RecordBatch inner entry differs')
            kind='tail'; EXPECTED_TAIL=None
        else:
            if admitted != CONFIG['interval']: return False
            kind='full'
        row = {'kind':kind,'pid':process.GetProcessID(),'runId':CONFIG['runId'],
               'threadId':frame.GetThread().GetThreadID(),'pc':frame.GetPC(),
               'nativeEntryFilePc':0x493990,'actualInnerReturnPc':ret,'innerReturnFilePc':retfile,
               'callsiteFilePc':retfile-5,'entryRdi':meter,'entryEsi':admitted,
               'activeInvocationRbp':rbp,'methodContextFrame':ACTIVE['methodContextFrame'],
               'bytecodeStart':ACTIVE['bytecodeStart'],'methodDesc':ACTIVE['methodDesc'],
               'metadataMethodName':ACTIVE['metadataMethodName'],'methodDefToken':ACTIVE['methodDefToken'],
               'loadedMetadataBytesSha256':ACTIVE['loadedMetadataBytesSha256'],
               'moduleMvid':ACTIVE['moduleMvid'],'fileSha256':ACTIVE['fileSha256'],
               'peAssembly':pe,'assemblyBinder':binder,'embeddedMeter':meter,
               'remainingBefore':int.from_bytes(read(process,meter+8,8),'little',signed=True),
               'executedBefore':int.from_bytes(read(process,meter+16,8),'little',signed=True)}
        SETTLEMENTS.append(row); COUNTS[kind]+=1
        (OUT/'settlements.json').write_text(json.dumps(SETTLEMENTS,indent=2)+'\n')
        print('ANDROID_KERNEL_SETTLEMENT '+json.dumps(row),flush=True)
        if COUNTS['full']==2:
            RECORD_BP.SetEnabled(False)
            for bp in TAIL_BPS: bp.SetEnabled(COUNTS['tail']<2)
        if COUNTS['tail']==2:
            for bp in OBSERVATION_BPS: bp.SetEnabled(False)
            (OUT/'observation-disabled.json').write_text(json.dumps({'pid':process.GetProcessID(),
                'runId':CONFIG['runId'],'counts':COUNTS,'allObservationBreakpointsDisabled':
                all(not b.IsEnabled() for b in OBSERVATION_BPS)})+'\n')
            print('ANDROID_BATCH_OBSERVATION_DISABLED',flush=True)
    except Exception as error: fail_capture(frame,error)
    return False
'''

MORE_SETUP = r'''
    global RECORD_BP
    for typename, member, offset in [('PEAssembly','m_pAssemblyBinder',CONFIG['peBinderOffset']),
            ('CustomAssemblyBinder','m_runeCLRInstructionMeter',CONFIG['binderMeterOffset'])]:
        typ=target.FindFirstType(typename)
        fields=[typ.GetFieldAtIndex(i) for i in range(typ.GetNumberOfFields())
                if typ.GetFieldAtIndex(i).GetName()==member]
        if len(fields)!=1 or fields[0].GetOffsetInBytes()!=offset:
            raise RuntimeError('Matching DWARF embedded-meter ownership offset differs')
    record_address=target.ResolveFileAddress(0x493990).GetLoadAddress(target)
    if read(process,record_address,16).hex()!=CONFIG['recordEntryHex']:
        raise RuntimeError('Actual RecordBatch entry code differs')
    CONFIG['loadedRecordAddress']=record_address
    RECORD_BP=target.BreakpointCreateByAddress(record_address)
    RECORD_BP.SetScriptCallbackFunction('android_kernel_lldb.record')
    OBSERVATION_BPS.append(RECORD_BP)
    for gate in CONFIG['tailCallsites']:
        address=target.ResolveFileAddress(gate).GetLoadAddress(target)
        if read(process,address,5).hex()!=CONFIG['callsiteBytes'][str(gate)]:
            raise RuntimeError('Actual unsafe Flush call instruction differs')
        bp=target.BreakpointCreateByAddress(address)
        bp.SetScriptCallbackFunction('android_kernel_lldb.tail_gate')
        bp.SetEnabled(False); TAIL_BPS.append(bp); OBSERVATION_BPS.append(bp)
'''

def render():
    base=helper()
    text=base.render()
    text=text.replace(' or key in SAMPLED','')
    text=text.replace("        ENTRIES.append(entry)","        ENTRIES.append(entry)\n        begin(frame, entry)")
    start=text.index("        if set(CONFIG['requiredMethods']) <= SAMPLED:")
    end=text.index('    except Exception as error:',start)
    text=text[:start]+text[end:]
    text=text.replace("    print('ANDROID_ENTRY_READY pid='",MORE_SETUP+"\n    print('ANDROID_ENTRY_READY pid='")
    text=text.replace('android_batch_entry_lldb','android_kernel_lldb')
    text+=EXTRA
    ast.parse(text); return text

def gates(contract):
    text=(contract/'invocation-recursive-dwarf.log').read_text()
    ranges=[]
    for block in re.split(r'(?m)^0x[0-9a-f]+:',text):
        if '"_ZN17RuneCLRBatchState5FlushEv"' not in block: continue
        if not re.search(r'DW_AT_call_line\s+\(947\)',block): continue
        assert 'interpexec.cpp' in block
        low=re.search(r'DW_AT_low_pc\s+\(0x([0-9a-f]+)\)',block)
        high=re.search(r'DW_AT_high_pc\s+\(0x([0-9a-f]+)\)',block)
        if low and high: ranges.append((int(low[1],16),int(high[1],16)))
        else: ranges.extend((int(a,16),int(b,16)) for a,b in re.findall(r'\[0x([0-9a-f]+), 0x([0-9a-f]+)\)',block))
    dis=(contract/'invocation-disassembly.log').read_text()
    calls={int(pc,16):code.strip().replace(' ','') for pc,code in re.findall(
        r'(?m)^\s*([0-9a-f]+): ((?:[0-9a-f]{2} ){4}[0-9a-f]{2})\s+callq\s+0x493990',dis)}
    tail=sorted(pc for pc in calls if any(lo<=pc<hi for lo,hi in ranges))
    assert len(calls)==1032 and len(tail)>250
    return sorted(pc+5 for pc in calls),tail,calls

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('apk','symbols','inputs','output','contract'): p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--pid',type=int,required=True);p.add_argument('--nonce',required=True)
    p.add_argument('--package',required=True);p.add_argument('--interval',type=int,choices=(100,1000),required=True)
    a=p.parse_args();base=helper()
    source=inspect.getsource(base.prepare)
    for old,new in [('RuneCLR_BatchBoundary_','RuneCLR_BatchKernel_'),
                    ('author/BatchBoundary.Author.dll','author/RuneCLR.BatchKernel.dll'),
                    ("'BatchBoundary.Author'","'RuneCLR.BatchKernel'"),
                    ('android_batch_entry_lldb','android_kernel_lldb')]: source=source.replace(old,new)
    env=dict(base.__dict__);env.update(AUTHOR_SHA=AUTHOR_SHA,METHODS=METHODS,render=render,__file__=__file__)
    exec(compile(source,str(Path(__file__).resolve()),'exec'),env);env['prepare'](a)
    config=base.load(a.output/'capture-config.json')
    returns,tail,calls=gates(a.contract)
    raw=(a.apk/'app/libcoreclr.so').read_bytes()
    # This exact ELF has a zero-offset PT_LOAD containing the sampled file PCs.
    import struct
    phoff=struct.unpack_from('<Q',raw,32)[0];width,count=struct.unpack_from('<HH',raw,54)
    headers=[struct.unpack_from('<IIQQQQQQ',raw,phoff+i*width) for i in range(count)]
    def bytes_at(pc,size):
        rows=[h for h in headers if h[0]==1 and h[3]<=pc and pc+size<=h[3]+h[5]]
        assert len(rows)==1;h=rows[0];off=h[2]+pc-h[3];return raw[off:off+size].hex()
    assert all(bytes_at(pc,5)==code for pc,code in calls.items())
    config.update(interval=a.interval,peBinderOffset=0x48,binderMeterOffset=0x110,
        recordEntryHex=bytes_at(0x493990,16),allReturnPcs=returns,tailCallsites=tail,
        callsiteBytes={str(pc):calls[pc] for pc in tail},
        gateDwarfSha256=hashlib.sha256((a.contract/'invocation-recursive-dwarf.log').read_bytes()).hexdigest())
    base.write(a.output/'capture-config.json',config)
    prep=base.load(a.output/'preparation.json');prep.update(configSha256=base.sha(a.output/'capture-config.json'),
        sourceDriverSha256=BASE_SHA,fullSamples=2,tailSamples=2,tailGateCount=len(tail),
        scope='Exact active Kernel full and unsafe Flush RecordBatch entry samples; no timing claim')
    base.write(a.output/'preparation.json',prep)
    print('KERNEL_SETTLEMENT_PREPARATION_PASS',len(tail))

if __name__=='__main__': main()
