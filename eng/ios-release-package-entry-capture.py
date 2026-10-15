#!/usr/bin/env python3
"""Capture interpreter execution entries for immutable Release controlled packages."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import subprocess
import datetime
import signal


def helper(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(__file__).with_name(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def package_methods(path):
    # Bind TypeDef ownership and MethodDef token without loading author code.
    release = helper('ios-r2r-release-verify')
    return release.plugin_methods(path, required=(), qualified=True)


def required_keys():
    entries = {'source':'Gameplay','import':'GameplayImport','private-a':'PrivateA',
               'private-b':'PrivateB','private-import':'PrivateImport'}
    keys = {package+'/'+assembly+'.dll:GameScript.'+name for package,assembly in entries.items()
            for name in ('OnStart','OnTick','OnStop')}
    keys.update('failure/GameplayFailure.dll:GameScript.'+name for name in ('OnStart','OnStop'))
    keys.update(package+'/lib/SharedGameplay.dll:'+name for package in ('private-a','private-b','private-import')
                for name in ('SharedHelper.Read','GenericCounter'+chr(96)+'1.Next'))
    return keys


def unified_events(path, pid):
    # log stream emits a Filtering header; JSON escapes slash characters.
    text = Path(path).read_text(errors='replace')
    first, last = text.find('['), text.rfind(']')
    if first < 0 or last < first:
        return []
    events = json.loads(text[first:last+1])
    if not isinstance(events, list) or any(event.get('processID') != int(pid) for event in events):
        raise ValueError('Unified events do not belong to the captured process')
    return events


LLDB_HELPER = r'''import json
from pathlib import Path
import lldb
OUT = Path(__file__).parent
CONFIG = json.loads((OUT/'capture-config.json').read_text())
ENTRIES = []
ERRORS = []
HITS = {'stub':0,'child':0}
NAMES = {'Gameplay','GameplayFailure','PrivateA','PrivateB','SharedGameplay'}
TYPES = {}
OFFSETS = {}
CHILD_BP = None
PENDING = {}
SAMPLED = set()
GATES = []
OBSERVATION_BPS = []

def read(process,address,size):
    error = lldb.SBError()
    result = process.ReadMemory(address,size,error)
    if error.Fail() or len(result)!=size: raise RuntimeError(str(error))
    return result

def word(process,address): return int.from_bytes(read(process,address,8),'little')

def typed(target,address,name):
    kind = TYPES.get(name) or target.FindFirstType(name)
    if not kind.IsValid(): raise RuntimeError('Missing DWARF type: '+name)
    return target.CreateValueFromAddress(name,lldb.SBAddress(address,target),kind)

def field(value,name):
    child = value.GetChildMemberWithName(name)
    if not child.IsValid() or child.GetError().Fail(): raise RuntimeError('Unreadable field: '+name)
    return child.GetValueAsUnsigned()

def utf16(process,address):
    data = bytearray()
    for i in range(4096):
        unit = read(process,address+2*i,2)
        if unit==b'\0\0': return data.decode('utf-16-le')
        data.extend(unit)
    raise RuntimeError('Unterminated Module path')

def capture(frame,kind):
    HITS[kind] += 1
    process = frame.GetThread().GetProcess()
    target = process.GetTarget()
    try:
        # Read only the immutable DWARF offsets and live pointers for a cheap
        # collectible prefilter. Never cache a recyclable MethodTable/Module.
        fast_start = frame.FindRegister('x12' if kind=='stub' else 'x28').GetValueAsUnsigned()
        if kind=='child': fast_start -= 8
        fast_method = word(process,fast_start)
        fast_desc = word(process,fast_method+OFFSETS['InterpMethod.methodHnd'])
        thread_id = frame.GetThread().GetThreadID()
        if kind=='child' and fast_desc not in PENDING.get(thread_id,set()): return False
        chunk_index = read(process,fast_desc+OFFSETS['MethodDesc.m_chunkIndex'],1)[0]
        fast_chunk = fast_desc-TYPES['MethodDescChunk'].GetByteSize()-chunk_index*8
        fast_mt = word(process,fast_chunk+OFFSETS['MethodDescChunk.m_methodTable'])
        flags = int.from_bytes(read(process,fast_mt+OFFSETS['MethodTable.m_dwFlags'],4),'little')
        if not flags&0x00200000: return False
        if kind=='stub':
            start = frame.FindRegister('x12').GetValueAsUnsigned()
            method_address = word(process,start)
            context_address = 0
            opcode_ip = start+8
        else:
            context,method = frame.FindVariable('pFrame'),frame.FindVariable('pMethod')
            if not context.IsValid() or context.GetError().Fail() or not method.IsValid() or method.GetError().Fail():
                raise RuntimeError('Post-ReInit DWARF variables unavailable')
            context_address = context.GetValueAsUnsigned()
            start = field(typed(target,context_address,'InterpMethodContextFrame'),'startIp')
            method_address = method.GetValueAsUnsigned()
            opcode_ip = frame.FindRegister('x28').GetValueAsUnsigned()
            if word(process,start)!=method_address or opcode_ip!=start+8:
                raise RuntimeError('Child execution method/first opcode mismatch')
        interp = typed(target,method_address,'InterpMethod')
        desc_address = field(interp,'methodHnd')
        desc = typed(target,desc_address,'MethodDesc')
        chunk_address = desc_address-target.FindFirstType('MethodDescChunk').GetByteSize()-field(desc,'m_chunkIndex')*8
        chunk = typed(target,chunk_address,'MethodDescChunk')
        mt_address = field(chunk,'m_methodTable')
        mt = typed(target,mt_address,'MethodTable')
        module_address = field(mt,'m_pModule')
        module = typed(target,module_address,'Module')
        error = lldb.SBError()
        simple = process.ReadCStringFromMemory(field(module,'m_pSimpleName'),256,error)
        if error.Fail(): raise RuntimeError(str(error))
        if simple not in NAMES: return False
        module_path = utf16(process,field(module,'m_path'))
        if module_path not in CONFIG['modules']: raise RuntimeError('Unexpected targeted Module path: '+module_path)
        expected = CONFIG['modules'][module_path]
        token = 0x06000000|((field(chunk,'m_flagsAndTokenRange')&0xfff)<<12)|(field(desc,'m_wFlags3AndTokenRemainder')&0xfff)
        names = [name for name,value in expected['methods'].items() if value==token]
        if not names: return False
        if len(names)!=1: raise RuntimeError('Token ambiguous in bound file')
        size,desc_start = field(interp,'codeSize'),field(desc,'m_interpreterCode')
        if size<=0 or desc_start!=start: raise RuntimeError('MethodDesc bytecode identity mismatch')
        prefix = read(process,start+8,min(size*4,64))
        entry = {'kind':kind,'pc':frame.GetPC(),'function':frame.GetFunctionName(),
            'nativeModule':frame.GetModule().GetFileSpec().GetFilename(),'methodContextFrame':context_address,
            'interpMethod':method_address,'methodDesc':desc_address,'methodTable':mt_address,
            'managedModule':module_address,'modulePath':module_path,'moduleSimpleName':simple,
            'modulePEAssembly':field(module,'m_pPEAssembly'),'moduleBaseAddress':field(module,'m_baseAddress'),
            'moduleAssembly':field(module,'m_pAssembly'),'collectible':bool(field(mt,'m_dwFlags')&0x00200000),
            'relativePath':expected['relativePath'],'fileSha256':expected['sha256'],'methodDefToken':token,
            'metadataMethodName':names[0],'bytecodeStart':start,'methodDescBytecodeStart':desc_start,
            'firstOpcodeAddress':opcode_ip,'bytecodeSizeSlots':size,'bytecodePrefixHex':prefix.hex()}
        ENTRIES.append(entry)
        SAMPLED.add((module_path,token))
        PENDING.get(thread_id,set()).discard(desc_address)
        if not any(PENDING.values()): CHILD_BP.SetEnabled(False)
        (OUT/'interpreter-entries.json').write_text(json.dumps(ENTRIES,indent=2)+'\n')
        print('PACKAGE_INTERPRETER_ENTRY '+json.dumps(entry),flush=True)
        observed = {e['relativePath']+':'+e['metadataMethodName'] for e in ENTRIES}
        if set(CONFIG['requiredMethods']) <= observed:
            for breakpoint in OBSERVATION_BPS: breakpoint.SetEnabled(False)
    except Exception as error:
        ERRORS.append({'kind':kind,'pc':frame.GetPC(),'error':str(error)})
        (OUT/'capture-errors.json').write_text(json.dumps(ERRORS,indent=2)+'\n')
    return False

def stub(frame,location,internal): return capture(frame,'stub')
def child(frame,location,internal): return capture(frame,'child')

def prepared(frame,location,internal):
    # Preparation only opens a bounded observation window; it is never an entry.
    process = frame.GetThread().GetProcess()
    target = process.GetTarget()
    try:
        desc_address = frame.FindRegister('x0').GetValueAsUnsigned()
        index = read(process,desc_address+OFFSETS['MethodDesc.m_chunkIndex'],1)[0]
        chunk_address = desc_address-TYPES['MethodDescChunk'].GetByteSize()-index*8
        mt_address = word(process,chunk_address+OFFSETS['MethodDescChunk.m_methodTable'])
        flags = int.from_bytes(read(process,mt_address+OFFSETS['MethodTable.m_dwFlags'],4),'little')
        if not flags&0x00200000: return False
        mt = typed(target,mt_address,'MethodTable')
        module_address = field(mt,'m_pModule')
        module = typed(target,module_address,'Module')
        error = lldb.SBError()
        name = process.ReadCStringFromMemory(field(module,'m_pSimpleName'),256,error)
        if error.Fail(): raise RuntimeError(str(error))
        if name not in NAMES: return False
        path = utf16(process,field(module,'m_path'))
        if path not in CONFIG['modules']: raise RuntimeError('Unknown prepared package Module')
        desc = typed(target,desc_address,'MethodDesc')
        chunk = typed(target,chunk_address,'MethodDescChunk')
        token = 0x06000000|((field(chunk,'m_flagsAndTokenRange')&0xfff)<<12)|(field(desc,'m_wFlags3AndTokenRemainder')&0xfff)
        names = [n for n,t in CONFIG['modules'][path]['methods'].items() if t==token]
        if len(names)!=1: raise RuntimeError('Prepared token absent or ambiguous')
        if names[0].rsplit('.',1)[-1] not in ('OnStart','OnTick','OnStop','Read','Next'): return False
        if (path,token) in SAMPLED: return False
        thread_id = frame.GetThread().GetThreadID()
        PENDING.setdefault(thread_id,set()).add(desc_address)
        CHILD_BP.SetEnabled(True)
        GATES.append({'methodDesc':desc_address,'managedModule':module_address,'modulePath':path,
            'methodDefToken':token,'metadataMethodName':names[0],'threadId':thread_id,'scope':'Preparation gate only; not execution evidence'})
        (OUT/'preparation-gates.json').write_text(json.dumps(GATES,indent=2)+'\n')
    except Exception as error:
        ERRORS.append({'kind':'preparation-gate','pc':frame.GetPC(),'error':str(error)})
        (OUT/'capture-errors.json').write_text(json.dumps(ERRORS,indent=2)+'\n')
    return False

def setup():
    global CHILD_BP
    target = lldb.debugger.GetSelectedTarget()
    for name in ('InterpMethod','MethodDesc','MethodDescChunk','MethodTable','Module','InterpMethodContextFrame'):
        TYPES[name] = target.FindFirstType(name)
        if not TYPES[name].IsValid(): raise RuntimeError('Missing DWARF type: '+name)
    for name,member in [('InterpMethod','methodHnd'),('MethodDesc','m_chunkIndex'),
                        ('MethodDescChunk','m_methodTable'),('MethodTable','m_dwFlags')]:
        matches = [TYPES[name].GetFieldAtIndex(i) for i in range(TYPES[name].GetNumberOfFields())
                   if TYPES[name].GetFieldAtIndex(i).GetName()==member]
        if len(matches)!=1: raise RuntimeError('Missing DWARF offset: '+name+'.'+member)
        OFFSETS[name+'.'+member] = matches[0].GetOffsetInBytes()
    symbols = target.FindSymbols('InterpreterStub')
    matches = [symbols.GetContextAtIndex(i).GetSymbol().GetStartAddress() for i in range(symbols.GetSize())
        if symbols.GetContextAtIndex(i).GetModule().GetFileSpec().GetFilename()=='libcoreclr.dylib']
    if len(matches)!=1: raise RuntimeError('Ambiguous InterpreterStub')
    stub_bp = target.BreakpointCreateByAddress(matches[0].GetLoadAddress(target))
    stub_bp.SetScriptCallbackFunction('package_lldb.stub')
    bp = target.BreakpointCreateByLocation(CONFIG['source'],CONFIG['dispatchLine'])
    if bp.GetNumLocations()!=1: raise RuntimeError('Child dispatch breakpoint not unique')
    address = bp.GetLocationAtIndex(0).GetAddress()
    instructions = target.ReadInstructions(address,4)
    text = [(i.GetMnemonic(target),i.GetOperands(target)) for i in instructions]
    if not text or text[0]!=('ldr','w24, [x28]'):
        raise RuntimeError('Pinned first-opcode x28 dispatch differs: '+str(text))
    bp.SetScriptCallbackFunction('package_lldb.child')
    CHILD_BP = bp
    bp.SetEnabled(False)
    prepared_symbols = target.FindSymbols('PrepareInterpreterCode')
    prepared_matches = [prepared_symbols.GetContextAtIndex(i).GetSymbol().GetStartAddress()
        for i in range(prepared_symbols.GetSize())
        if prepared_symbols.GetContextAtIndex(i).GetModule().GetFileSpec().GetFilename()=='libcoreclr.dylib']
    if len(prepared_matches)!=1: raise RuntimeError('Preparation gate symbol not unique')
    gate = target.BreakpointCreateByAddress(prepared_matches[0].GetLoadAddress(target))
    gate.SetScriptCallbackFunction('package_lldb.prepared')
    OBSERVATION_BPS.extend([stub_bp,bp,gate])
    (OUT/'breakpoints.json').write_text(json.dumps({'stubAddress':matches[0].GetLoadAddress(target),
        'childAddress':address.GetLoadAddress(target),'childLine':address.GetLineEntry().GetLine(),
        'instructions':text,'stubLocations':stub_bp.GetNumLocations(),'childLocations':bp.GetNumLocations(),
        'prefilterOffsets':OFFSETS,'preparationGateAddress':prepared_matches[0].GetLoadAddress(target),
        'preparationGateLocations':gate.GetNumLocations(),'childInitiallyDisabled':True},indent=2)+'\n')

def finish(): (OUT/'capture-hits.json').write_text(json.dumps(HITS)+'\n')
'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('app','packages','native','runtime','output'): parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    common,mobile = helper('ios-r2r-fix-verify'),helper('verify-ios-packages')
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    app,packages,native = args.app.resolve(),args.packages.resolve(),args.native.resolve()
    dwarf = native.with_name(native.name+'.dwarf')
    source = args.runtime.resolve()/'src/coreclr/vm/interpexec.cpp'
    lines = source.read_text().splitlines()
    calls = [i for i,line in enumerate(lines) if '// Set execution state for the new frame' in line
        and 'pMethod = pFrame->startIp->Method;' in lines[i+1]
        and 'if (stack + pMethod->allocaSize' in '\n'.join(lines[i:i+10])]
    if len(calls)!=1: raise RuntimeError('Unknown child-call source')
    dispatch_line = next(i+1 for i in range(calls[0],calls[0]+20) if 'INTOP_NEXT;' in lines[i])
    if mobile.macho_sections(native)!=mobile.macho_sections(app/'libcoreclr.dylib'): raise RuntimeError('Native identity mismatch')
    expected = mobile.tree(app)
    payload = {name+'/'+path:digest for name in mobile.PACKAGES for path,digest in mobile.tree(packages/name).items()}
    common.write(out/'identity.json',{'app':str(app),'bundleFiles':expected,'packages':str(packages),'payloadHashes':payload,
        'native':str(native),'nativeSha256':common.sha(native),'dwarfSha256':common.sha(dwarf),'nativeSections':mobile.macho_sections(native),
        'sourceSha256':common.sha(source),'runtimeCommit':common.capture(['git','-C',args.runtime,'rev-parse','HEAD']),
        'driverSha256':common.sha(__file__),'scope':'Existing immutable fixtures; no new post-install generation claim'})
    shutil.copy2(__file__,out/'driver.py')
    (out/'package_lldb.py').write_text(LLDB_HELPER)
    import plistlib
    bundle = plistlib.loads((app/'Info.plist').read_bytes())['CFBundleIdentifier']
    sim = common.capture(['xcrun','simctl','create','RuneCLR-Release-Package-Entry','com.apple.CoreSimulator.SimDeviceType.iPhone-17','com.apple.CoreSimulator.SimRuntime.iOS-27-0'])
    common.write(out/'simulator.json',{'uuid':sim})
    result = {'passed':False}
    try:
        common.logged(['xcrun','simctl','boot',sim],out/'boot-command.log')
        common.logged(['xcrun','simctl','bootstatus',sim,'-b'],out/'boot.log')
        common.logged(['xcrun','simctl','install',sim,app],out/'install.log')
        installed = Path(common.capture(['xcrun','simctl','get_app_container',sim,bundle,'app']))
        container = Path(common.capture(['xcrun','simctl','get_app_container',sim,bundle,'data']))
        destination = container/'Documents/controlled'
        destination.mkdir(parents=True,exist_ok=False)
        for name in mobile.PACKAGES: shutil.copytree(packages/name,destination/name)
        if mobile.tree(installed)!=expected or mobile.tree(destination)!=payload: raise RuntimeError('Installed inputs differ')
        modules = {str(destination/p):{'relativePath':p,'sha256':digest,'methods':package_methods(packages/p)} for p,digest in payload.items() if p.endswith('.dll')}
        common.write(out/'capture-config.json',{'modules':modules,'source':str(source),'dispatchLine':dispatch_line,
            'requiredMethods':sorted(required_keys())})
        env = {k:v for k,v in os.environ.items() if not k.startswith(('SIMCTL_CHILD_DOTNET_','SIMCTL_CHILD_COMPlus_','SIMCTL_CHILD_PROBE_'))}
        common.logged(['xcrun','simctl','launch','--wait-for-debugger','--stdout='+str(out/'managed.stdout.log'),'--stderr='+str(out/'managed.stderr.log'),sim,bundle],out/'launch.log',env=env)
        pid = re.search(r': ([0-9]+)',(out/'launch.log').read_text()).group(1)
        commands = ['breakpoint set -n coreclr_initialize','continue','breakpoint disable 1','target symbols add '+str(dwarf),
            'command script import '+str(out/'package_lldb.py'),'script package_lldb.setup()','continue','process status','script package_lldb.finish()','quit']
        (out/'capture.lldb').write_text('\n'.join(commands)+'\n')
        query = ['xcrun','simctl','spawn',sim,'log','stream','--style','json','--predicate','processIdentifier == '+pid]
        with (out/'managed.unified.log').open('w') as unified, (out/'unified-command.stderr.log').open('w') as query_errors:
            stream = subprocess.Popen(query,stdout=unified,stderr=query_errors,start_new_session=True)
            common.write(out/'unified-query.json',{'startUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'command':query,'appPid':int(pid),'simulator':sim,'hostStreamPid':stream.pid})
            try:
                status = common.logged(['xcrun','lldb','--batch','--attach-pid',pid,'--source',out/'capture.lldb'],out/'lldb.log',timeout=600,check=False)
            finally:
                if stream.poll() is None: stream.send_signal(signal.SIGINT)
                try: stream.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    stream.kill(); stream.wait(timeout=30)
                common.write(out/'unified-query-completed.json',{'endUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'streamExit':stream.returncode})
        entries = json.loads((out/'interpreter-entries.json').read_text()) if (out/'interpreter-entries.json').exists() else []
        stdout = (out/'managed.stdout.log').read_text(errors='replace')
        stderr = (out/'managed.stderr.log').read_text(errors='replace')
        events = unified_events(out/'managed.unified.log', pid)
        messages = [event.get('eventMessage','') for event in events]
        managed = stdout + '\n' + stderr + '\n' + '\n'.join(messages)
        required = {}
        for path,module in modules.items():
            package = module['relativePath'].split('/')[0]
            if package not in ('source','import','failure','private-a','private-b','private-import'): continue
            for name,token in module['methods'].items():
                method_name = name.rsplit('.',1)[-1]
                if (name.startswith('GameScript.') and method_name in ('OnStart','OnStop','OnTick') and (package!='failure' or method_name!='OnTick')) or name in ('SharedHelper.Read','GenericCounter'+chr(96)+'1.Next'):
                    key = module['relativePath']+':'+name
                    required[key] = sum(e['modulePath']==path and e['methodDefToken']==token for e in entries)
        unchanged = mobile.tree(installed)==expected and mobile.tree(app)==expected
        fixtures_unchanged = mobile.tree(destination)==payload and all(common.sha(packages/p)==h for p,h in payload.items())
        pass_count = sum(message.startswith('PASS ') for message in messages)
        complete = ('15/15 package execution tests passed.' in messages and pass_count == 15
                    and not any(message.startswith('FAIL ') for message in messages)
                    and 'CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0' in stdout)
        normal_exit = bool(re.search(r'exited with status = 0',(out/'lldb.log').read_text()))
        result.update({'passed':bool(status==0 and normal_exit and complete and unchanged and fixtures_unchanged
            and not (out/'capture-errors.json').exists() and set(required)==required_keys() and all(required.values())),
            'functionalPassed':complete,'lldbExit':status,'normalExit':normal_exit,'bundleUnchanged':unchanged,'fixturesUnchanged':fixtures_unchanged,
            'individualPassCount':pass_count,'unifiedEventCount':len(events),
            'validEntries':len(entries),'entryKinds':{kind:sum(e['kind']==kind for e in entries) for kind in ('stub','child')},
            'requiredMethodEntryCounts':required,'requiredMethodSetMatches':set(required)==required_keys(),
            'scope':'Execution entry sampling; not complete invocation capture or physical-device acceptance'})
    finally:
        common.logged(['xcrun','simctl','terminate',sim,bundle],out/'terminate.log',check=False)
        shutdown = common.logged(['xcrun','simctl','shutdown',sim],out/'shutdown.log',check=False)
        common.write(out/'simulator.json',{'uuid':sim,'shutdownExit':shutdown})
    result['passed'] = result['passed'] and shutdown==0
    common.write(out/'results.json',result)
    with tarfile.open(out/'evidence.tar.gz','w:gz') as archive:
        for path in sorted(out.iterdir()):
            if path.is_file() and path.suffix in ('.json','.log','.lldb','.py'): archive.add(path,arcname=path.name)
        for name in ('ios-r2r-fix-verify','verify-ios-packages','ios-r2r-release-verify'): archive.add(Path(__file__).with_name(name+'.py'),arcname=name+'.py')
    print(json.dumps(result),flush=True)
    print('Archive SHA256='+common.sha(out/'evidence.tar.gz'),flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
