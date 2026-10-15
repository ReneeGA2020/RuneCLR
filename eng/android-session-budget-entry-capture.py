#!/usr/bin/env python3
"""Prepare SHA-bound current-budget x64 observers without launching an app."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re

def helper(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def render():
    text = helper('android-session-policy-entry-capture').render()
    old = "fast_start = frame.FindRegister('r10').GetValueAsUnsigned() if kind=='stub' else field(typed(target,frame.FindVariable('pFrame').GetValueAsUnsigned(),'InterpMethodContextFrame'),'startIp')"
    new = """if kind=='child':
            for variable in ('pFrame','pMethod','ip'):
                value=frame.FindVariable(variable)
                if not value.IsValid() or value.GetError().Fail() or not value.GetValue():
                    raise RuntimeError('Actual optimized child DWARF unavailable: '+variable)
        fast_start = frame.FindRegister('r10').GetValueAsUnsigned() if kind=='stub' else field(typed(target,frame.FindVariable('pFrame').GetValueAsUnsigned(),'InterpMethodContextFrame'),'startIp')"""
    assert text.count(old) == 1
    text = text.replace(old, new)
    marker = "        expected = CONFIG['modules'][module_path]"
    added = marker + """
        base=field(module,'m_baseAddress')
        mapped_mvid=None
        for layout,root_key,mvid_key in [('rva','metadataRootRva','moduleMvidRva'),('flat','metadataRootOffset','moduleMvidOffset')]:
            try:
                if read(process,base+expected[root_key],4)==b'BSJB' and read(process,base+expected[mvid_key],16).hex()==expected['moduleMvidBytesHex']:
                    mapped_mvid=layout
                    break
            except RuntimeError: pass
        if mapped_mvid is None: raise RuntimeError('Actual loaded metadata MVID differs')"""
    assert text.count(marker) == 1
    text = text.replace(marker, added)
    text = text.replace("'metadataMethodName':names[0],'bytecodeStart':start", "'metadataMethodName':names[0],'moduleMvid':expected['moduleMvid'],'loadedMetadataMvidValidated':True,'loadedPELayout':mapped_mvid,'childDWARF':{n:{'value':frame.FindVariable(n).GetValue(),'type':frame.FindVariable(n).GetTypeName(),'location':frame.FindVariable(n).GetLocation()} for n in ('pFrame','pMethod','ip')} if kind=='child' else None,'bytecodeStart':start")
    text = text.replace('ANDROID_SESSION_INTERPRETER_ENTRY','ANDROID_BUDGET_INTERPRETER_ENTRY')
    start=text.index("        if kind=='child':\n            for variable")
    end=text.index("        fast_method =", start)
    text=text[:start]+"        fast_start = frame.FindRegister('r10').GetValueAsUnsigned() if kind=='stub' else field(typed(target,word(process,frame.FindRegister('rbp').GetValueAsUnsigned()-FRAME_SPILL),'InterpMethodContextFrame'),'startIp')\n"+text[end:]
    start=text.index("            context,method = frame.FindVariable('pFrame')")
    end=text.index("            if opcode_ip!=start+8:",start)
    text=text[:start]+"            context_address=word(process,frame.FindRegister('rbp').GetValueAsUnsigned()-FRAME_SPILL)\n            start=field(typed(target,context_address,'InterpMethodContextFrame'),'startIp')\n            method_address=word(process,start)\n            opcode_ip=frame.FindRegister('r12').GetValueAsUnsigned()\n"+text[end:]
    text=text.replace('CHILD_BP = None','CHILD_BP = None\nFRAME_SPILL = None')
    text=text.replace('def setup():','def setup():\n    global FRAME_SPILL')
    anchor="        bp.SetScriptCallbackFunction('android_entry_lldb.child')"
    contract="""        expected=[('movl','(%r12), %ebx'),('movq','-0xe40(%rbp), %rax'),('movq','0x8(%rax), %rax'),('movq','(%rax), %rax')]
        if address.GetFileAddress()!=0x3afe8d or text!=expected: raise RuntimeError('SHA-bound x64 first-opcode/frame load contract differs')
        start_fields=[TYPES['InterpMethodContextFrame'].GetFieldAtIndex(i) for i in range(TYPES['InterpMethodContextFrame'].GetNumberOfFields()) if TYPES['InterpMethodContextFrame'].GetFieldAtIndex(i).GetName()=='startIp']
        if len(start_fields)!=1 or start_fields[0].GetOffsetInBytes()!=8: raise RuntimeError('Matching DWARF startIp field differs')
        reinit=read(process,address.GetLoadAddress(target)-74,33).hex()
        if reinit!='4c89630848c74320000000004c8b6b1031c0488985a0f1ffff498b04244983c408': raise RuntimeError('Actual preceding ReInit/startIp load/ip advance bytes differ')
        reload=read(process,address.GetLoadAddress(target)-97,7).hex()
        if reload!='488b9dc0f1ffff': raise RuntimeError('Actual pre-ReInit frame reload differs')
        FRAME_SPILL=0xe40
        CONFIG['childFrameContract']={'filePc':address.GetFileAddress(),'frameRegister':'rbp','frameSpillOffset':FRAME_SPILL,'opcodeRegister':'r12','startIpDwarfOffset':8,'instructions':text,'precedingReInitHex':reinit,'precedingFrameReloadHex':reload,'localVariableDwarfAvailable':False,'scope':'Actual emitted loads and ReInit bytes plus matching DWARF type/line; no optimized-local location claim'}
"""
    assert text.count(anchor)==1
    text=text.replace(anchor,contract+anchor)
    text=text.replace("'scope':'Execution observations only; no method preparation counted'","'childFrameContract':CONFIG['childFrameContract'],'scope':'Execution observations only; no method preparation counted'")
    text=text.replace("'childDWARF':{n:{'value':frame.FindVariable(n).GetValue(),'type':frame.FindVariable(n).GetTypeName(),'location':frame.FindVariable(n).GetLocation()} for n in ('pFrame','pMethod','ip')} if kind=='child' else None","'childDWARF':None,'childFrameContract':CONFIG.get('childFrameContract') if kind=='child' else None,'childRegisters':{n:frame.FindRegister(n).GetValueAsUnsigned() for n in ('rbp','r12')} if kind=='child' else None")
    ast.parse(text)
    return text

def prepare(args):
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    native=args.apk/'app/libcoreclr.so';symbols=args.symbols
    manifest=json.loads((symbols/'manifest.json').read_text())
    assert manifest['runtimeTree']=='b54537ff42a066e41a01ea611a21f2e5e49934a1'
    parser=helper('android-session-policy-layout')
    for name in ('libcoreclr.so','libclrinterpreter.so'):
        assert sha(args.apk/'app'/name)==manifest['nativeHashes'][name]
        assert sha(symbols/(name+'.dbg'))==manifest['files'][name+'.dbg']['sha256']
        assert parser.read_build_ids(args.apk/'app'/name)==parser.read_build_ids(symbols/(name+'.dbg'))
    source=symbols/'interpexec.cpp'
    assert sha(source)==manifest['files']['interpexec.cpp']['sha256']
    lines=source.read_text().splitlines()
    calls=[i for i,line in enumerate(lines[:-1]) if '// Set execution state for the new frame' in line and 'pMethod = pFrame->startIp->Method;' in lines[i+1] and 'if (stack + pMethod->allocaSize' in '\n'.join(lines[i:i+10])]
    assert len(calls)==1
    dispatch=[i+1 for i in range(calls[0],calls[0]+20) if 'INTOP_NEXT;' in lines[i]]
    assert len(dispatch)==1
    descriptors=[];data=native.read_bytes()
    for match in re.finditer(re.escape(b'{"version":'),data):
        try:
            raw=data[match.start():data.index(bytes([0]),match.start())];descriptor=json.loads(raw)
            if 'MethodTable' in descriptor.get('types',{}):descriptors.append((raw,descriptor))
        except (ValueError,UnicodeError):pass
    assert len(descriptors)==1
    raw,descriptor=descriptors[0]
    cdac={'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'methodTable':descriptor['types']['MethodTable']}
    modules={};required=[]
    metadata=json.loads(args.metadata.read_text())
    state=json.loads((args.apk/'state.json').read_text())
    assert state['package']==args.package
    for row in metadata:
        path=Path(row['path']);name=path.name
        assert sha(path)==row['sha256'] and row['managedNativeRva']==0
        assert state['authorHashes']['plugin/'+name]==row['sha256']
        methods={m['owner']+'.'+m['name']:int(m['token'],16) for m in row['methods']}
        identity=helper('ios-session-budget-entry').pe_mvid(path)
        assert identity['moduleMvid']==row['moduleMvid']
        modules['/data/user/0/'+args.package+'/files/plugin/'+name]={'relativePath':name,'simpleName':row['assembly'],'methods':methods,'sha256':row['sha256'],**identity}
        fixed=['HostBudgetUGC.Base..ctor','HostBudgetUGC.Base.OnStart','HostBudgetUGC.Base.OnStop','HostBudgetUGC.Normal..ctor','HostBudgetUGC.Normal.OnStart','HostBudgetUGC.Normal.OnTick','HostBudgetUGC.FiniteCleanup.OnTick'] if name.endswith('Payload.dll') else ['HostBudgetUGC.Private.Helper.Finite']+[n for n in methods if n.endswith('.<Finite>b__0')]
        assert set(fixed)<=set(methods)
        required.extend(name+':'+n for n in fixed)
    assert len(modules)==2 and len(required)==9
    config={'appPid':args.pid,'runId':args.nonce,'source':str(source.resolve()),'dispatchLines':dispatch,'cdac':cdac,'modules':modules,'requiredMethods':required}
    (out/'capture-config.json').write_text(json.dumps(config,indent=2)+'\n')
    (out/'android_entry_lldb.py').write_text(render())
    commands=['command script import '+(out/'android_entry_lldb.py').as_posix(),'script android_entry_lldb.setup()','continue','process status','script android_entry_lldb.finish()','quit']
    (out/'capture.lldb').write_text('\n'.join(commands)+'\n')
    (out/'preparation.json').write_text(json.dumps({'sourceSha256':sha(source),'manifestSha256':sha(symbols/'manifest.json'),'metadataSha256':sha(args.metadata),'observerSha256':sha(out/'android_entry_lldb.py'),'configSha256':sha(out/'capture-config.json'),'completeInvocationCapture':False,'dispatchPath':'regular child only; actual emitted loads/ReInit plus matching DWARF type/source-line contract'},indent=2)+'\n')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('apk','symbols','metadata','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--pid',type=int,required=True);p.add_argument('--nonce',required=True);p.add_argument('--package',required=True)
    prepare(p.parse_args())

if __name__=='__main__':main()
