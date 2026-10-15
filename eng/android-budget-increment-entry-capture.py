#!/usr/bin/env python3
"""Prepare SHA-bound current-budget x64 observers without launching an app."""
import argparse
import struct
import subprocess
import shutil
import sys
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re

PARENT_DRIVER_SHA256 = '2427ff88a4d79c04863d4acbfb42407e18a5eae571293af0bac6f3b1a0d02deb'
NATIVE_SHA = 'd2e2b148216d14bd7f05175a4c61c413673def17a3781e723a83ca940ba859d6'
INTERPRETER_SHA = '045f426c2091b0445fd976324d93901a14e734413bd3812b78b234674c97bbfa'
CORE_SYMBOL_SHA = 'bd61167be1610de7e22c0ff5b1b2e7cdc997773ddf45df26b19ed6fbf78af919'
INTERPRETER_SYMBOL_SHA = '25104d963961ebcbde8bf867d45b851160c69daf124a0409b5f8a8168b3c99b7'
DEPENDENCY_HASHES = {
    'android-session-budget-entry-capture.py': PARENT_DRIVER_SHA256,
    'android-session-policy-entry-capture.py': '9ddde81f878a3e3495a3f71990da5278021d27a6813246c17a5050623c8e0d6f',
    'android-session-policy-layout.py': '3ab977377032cca005a41b959fb21b2162c67dcc7658b44a1e43df85ca7d61eb',
    'ios-release-package-entry-capture.py': '408500026eb1369fe1b98626a1dd09f4ccd408c9e179411dc3bca807baa60dee',
    'ios-session-budget-entry.py': 'ba59203a2c692a607dee7a606bc42ead69160b63256777fd1c1f8e89c2fdb47c',
}

def validate_sha(path, expected):
    if sha(path) != expected:
        raise ValueError('SHA-bound input differs: ' + str(path))

def dependencies():
    for name, expected in DEPENDENCY_HASHES.items():
        validate_sha(Path(__file__).with_name(name), expected)

def helper(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def render():
    dependencies()
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
    text=text[:start]+"            context_address=word(process,frame.FindRegister('rbp').GetValueAsUnsigned()-FRAME_SPILL)\n            start=field(typed(target,context_address,'InterpMethodContextFrame'),'startIp')\n            method_address=word(process,start)\n            opcode_ip=frame.FindRegister('r14').GetValueAsUnsigned()\n"+text[end:]
    text=text.replace('CHILD_BP = None','CHILD_BP = None\nFRAME_SPILL = None')
    text=text.replace('def setup():','def setup():\n    global FRAME_SPILL')
    anchor="        bp.SetScriptCallbackFunction('android_entry_lldb.child')"
    contract="""        expected=[('movl','(%r14), %ebx'),('movq','-0xe48(%rbp), %rax'),('movq','0x8(%rax), %rax'),('movq','(%rax), %rax')]
        if address.GetFileAddress()!=0x3b0aff or text!=expected: raise RuntimeError('SHA-bound x64 first-opcode/frame load contract differs')
        start_fields=[TYPES['InterpMethodContextFrame'].GetFieldAtIndex(i) for i in range(TYPES['InterpMethodContextFrame'].GetNumberOfFields()) if TYPES['InterpMethodContextFrame'].GetFieldAtIndex(i).GetName()=='startIp']
        if len(start_fields)!=1 or start_fields[0].GetOffsetInBytes()!=8: raise RuntimeError('Matching DWARF startIp field differs')
        reinit=read(process,address.GetLoadAddress(target)-73,32).hex()
        if reinit!='4c89730848c74320000000004c8b7b1031d248899590f1ffff498b064983c608': raise RuntimeError('Actual preceding ReInit/startIp load/ip advance bytes differ')
        reload=read(process,address.GetLoadAddress(target)-96,7).hex()
        if reload!='488b9db8f1ffff': raise RuntimeError('Actual pre-ReInit frame reload differs')
        FRAME_SPILL=0xe48
        CONFIG['childFrameContract']={'filePc':address.GetFileAddress(),'frameRegister':'rbp','frameSpillOffset':FRAME_SPILL,'opcodeRegister':'r14','startIpDwarfOffset':8,'instructions':text,'precedingReInitHex':reinit,'precedingFrameReloadHex':reload,'localVariableDwarfAvailable':False,'scope':'Actual emitted loads and ReInit bytes plus matching DWARF type/line; no optimized-local location claim'}
"""
    assert text.count(anchor)==1
    text=text.replace(anchor,contract+anchor)
    text=text.replace("'scope':'Execution observations only; no method preparation counted'","'childFrameContract':CONFIG['childFrameContract'],'scope':'Execution observations only; no method preparation counted'")
    text=text.replace("'childDWARF':{n:{'value':frame.FindVariable(n).GetValue(),'type':frame.FindVariable(n).GetTypeName(),'location':frame.FindVariable(n).GetLocation()} for n in ('pFrame','pMethod','ip')} if kind=='child' else None","'childDWARF':None,'childFrameContract':CONFIG.get('childFrameContract') if kind=='child' else None,'childRegisters':{n:frame.FindRegister(n).GetValueAsUnsigned() for n in ('rbp','r14')} if kind=='child' else None")
    ast.parse(text)
    return text

def prepare(args):
    dependencies()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    native=args.apk/'app/libcoreclr.so';symbols=args.symbols
    manifest=json.loads((symbols/'manifest.json').read_text())
    assert manifest['runtimeTree']=='91673a7980bda79006259e525741fecb04324444'
    assert manifest['nativeHashes']=={'libcoreclr.so':NATIVE_SHA,'libclrinterpreter.so':INTERPRETER_SHA}
    assert sha(symbols/'libcoreclr.so.dbg')==CORE_SYMBOL_SHA and sha(symbols/'libclrinterpreter.so.dbg')==INTERPRETER_SYMBOL_SHA
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
    (out/'preparation.json').write_text(json.dumps({'sourceSha256':sha(source),'manifestSha256':sha(symbols/'manifest.json'),'metadataSha256':sha(args.metadata),'observerSha256':sha(out/'android_entry_lldb.py'),'configSha256':sha(out/'capture-config.json'),'completeInvocationCapture':False,'dispatchPath':'regular child only; actual emitted loads/ReInit plus matching DWARF type/source-line contract','preparedOnly':True,'nativeEntryProof':False,'parentDriverSha256':PARENT_DRIVER_SHA256},indent=2)+'\n')

def contract(args):
    dependencies()
    out=args.output.resolve();out.mkdir(exist_ok=False);shutil.copy2(__file__,out/'driver.py')
    rec=json.loads(args.build_receipt.read_text());rt=args.runtime.resolve()
    assert rec['success'] and rec['buildExit']==0 and rec['commit']=='112e97408de1ae1c2a6cbd2967dcd250cd2d491c' and rec['tree']=='91673a7980bda79006259e525741fecb04324444'
    assert sha(args.build_receipt)=='ec0e464a3b420727214db7411b07993d14d4fcb2c863445e0b2d2ab92d0d832c'
    capture=lambda c:subprocess.check_output([str(v) for v in c],text=True).strip()
    assert capture(['git','-C',rt,'rev-parse','HEAD'])==rec['commit']
    assert capture(['git','-C',rt,'rev-parse','HEAD^{tree}'])==rec['tree']
    assert not capture(['git','-C',rt,'status','--porcelain','--untracked-files=no'])
    proof=args.build_receipt.parent/'source-proof.json'
    assert sha(proof)=='6dea87eae1bbbb3142319707c2af4f5cca142a5bc1e4fe8ef665d8a93a2e4d48'
    source_hashes=json.loads(proof.read_text())['sourceHashes']
    for n,h in source_hashes.items():assert sha(rt/n)==h,n
    native=Path(rec['native']);interpreter=Path(rec['interpreter']);parser=helper('android-session-policy-layout')
    expected={native:NATIVE_SHA,interpreter:INTERPRETER_SHA,Path(str(native)+'.dbg'):CORE_SYMBOL_SHA,Path(str(interpreter)+'.dbg'):INTERPRETER_SYMBOL_SHA}
    for p,h in expected.items():validate_sha(p,h)
    identities={}
    for p in (native,interpreter):
        ids=parser.read_build_ids(p);assert ids==parser.read_build_ids(Path(str(p)+'.dbg'))
        identities[p.name]={'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size,'buildIds':ids,'symbolsPath':str(p)+'.dbg','symbolsSha256':sha(Path(str(p)+'.dbg')),'symbolsBytes':Path(str(p)+'.dbg').stat().st_size}
    source=rt/'src/coreclr/vm/interpexec.cpp';lines=source.read_text().splitlines();assert lines[3750].strip()=='INTOP_NEXT;'
    pc=0x3b0aff;data=native.read_bytes()
    def at(blob,address,size):
        offset=struct.unpack_from('<Q',blob,32)[0];width,count=struct.unpack_from('<HH',blob,54)
        headers=[struct.unpack_from('<IIQQQQQQ',blob,offset+i*width) for i in range(count)]
        owners=[h for h in headers if h[0]==1 and h[3]<=address and address+size<=h[3]+h[5]];assert len(owners)==1
        position=owners[0][2]+address-owners[0][3];return blob[position:position+size].hex(),position
    pieces={'dispatch':(pc,17,'418b1e488b85b8f1ffff488b4008488b00'),'frameReload':(pc-96,7,'488b9db8f1ffff'),'reInit':(pc-73,32,'4c89730848c74320000000004c8b7b1031d248899590f1ffff498b064983c608')}
    def validate_code(blob):
        for name,(address,size,expected_hex) in pieces.items():
            if at(blob,address,size)[0]!=expected_hex:
                raise ValueError('SHA-bound emitted code differs: '+name)
    validate_code(data)
    commands={
      'disassembly':[args.toolchain/'llvm-objdump','-d','--start-address='+hex(pc-110),'--stop-address='+hex(pc+49),native],
      'dwarfLookup':[args.toolchain/'llvm-dwarfdump','--lookup='+hex(pc),str(native)+'.dbg'],
      'contextTypes':[args.toolchain/'llvm-dwarfdump','--name=InterpMethodContextFrame','--show-children',str(native)+'.dbg'],
      'lldbLine':['xcrun','lldb','--batch','-o','target create '+str(native),'-o','target symbols add '+str(native)+'.dbg','-o','breakpoint set -f interpexec.cpp -l 3751','-o','breakpoint list']}
    logs={}
    for name,cmd in commands.items():
        q=subprocess.run([str(v) for v in cmd],capture_output=True,text=True,timeout=60);assert q.returncode==0,(name,q.stderr)
        (out/(name+'.log')).write_text(q.stdout+q.stderr);logs[name]=q.stdout
    assert 'line 3751' in logs['dwarfLookup'] and 'InterpExecMethod' in logs['dwarfLookup']
    assert '0x00000000003b0aff' in logs['lldbLine'] and 'locations = 1' in logs['lldbLine']
    fields=[b for b in logs['contextTypes'].split(chr(10)+chr(10)) if 'DW_AT_name' in b and '("startIp")' in b]
    assert fields and all('DW_AT_data_member_location' in b and '(0x08)' in b for b in fields)
    observer=render();ast.parse(observer);(out/'android_entry_lldb.py').write_text(observer)
    assert "frame.FindRegister('r14')" in observer and "frame.FindRegister('r12')" not in observer
    negative=[]
    old=args.old_products
    for label,p,h in [('oldNative',old/'libcoreclr.so',NATIVE_SHA),('oldSymbols',old/'libcoreclr.so.dbg',CORE_SYMBOL_SHA)]:
        try:validate_sha(p,h)
        except ValueError as error:negative.append({'name':label,'rejected':True,'actualPath':str(p),'actualSha256':sha(p),'expectedSha256':h,'error':str(error),'validator':'validate_sha'})
        else:raise RuntimeError('Old input unexpectedly accepted: '+label)
    for name,(address,size,h) in pieces.items():
        changed=bytearray(data);position=at(data,address,size)[1];changed[position]^=1
        try:validate_code(changed)
        except ValueError as error:negative.append({'name':name+'Byte','rejected':True,'inMemoryOnly':True,'error':str(error),'validator':'validate_code'})
        else:raise RuntimeError('Changed emitted bytes unexpectedly accepted: '+name)
    raw={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in out.iterdir() if p.is_file()}
    result={'passed':True,'preparedOnly':True,'nativeEntryProof':False,'executionVerified':False,'runtimeCommit':rec['commit'],'runtimeTree':rec['tree'],'sourceTrackedClean':True,'sourceFilesVerified':len(source_hashes),'sourceSha256':sha(source),'buildReceiptSha256':sha(args.build_receipt),'sourceProofSha256':sha(proof),'products':identities,'filePc':pc,'sourceLine':3751,'frameSpillRegister':'rbp','frameSpillOffset':0xe48,'opcodeRegister':'r14','startIpDwarfOffset':8,'localVariableDwarfAvailable':False,'codePieces':{n:{'filePc':a,'bytes':z,'hex':h} for n,(a,z,h) in pieces.items()},'oldContract':{'filePc':0x3afe8d,'frameSpillOffset':0xe40,'opcodeRegister':'r12','reInitDistance':74,'frameReloadDistance':97},'negativeControls':negative,'rawFiles':raw,'driverSha256':sha(__file__),'scope':'Offline native/DWARF/source contract preparation only; no debugger attachment, app/emulator launch or build'}
    result['dependencyHashesVerified']=DEPENDENCY_HASHES
    (out/'results.json').write_text(json.dumps(result,indent=2)+chr(10));print(json.dumps({k:result[k] for k in ('passed','preparedOnly','nativeEntryProof','filePc','frameSpillOffset','opcodeRegister')},indent=2))

def main():
    if len(sys.argv)>1 and sys.argv[1]=='contract':
        p=argparse.ArgumentParser(description='Read-only matching native/DWARF contract; no app action')
        for name in ('runtime','build-receipt','toolchain','old-products','output'):p.add_argument('--'+name,type=Path,required=True)
        contract(p.parse_args(sys.argv[2:]));return
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('apk','symbols','metadata','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--pid',type=int,required=True);p.add_argument('--nonce',required=True);p.add_argument('--package',required=True)
    prepare(p.parse_args())

if __name__=='__main__':main()
