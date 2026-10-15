#!/usr/bin/env python3
"""Prepare Android Release LLDB observation; never launches a debugger, adb or an app."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re


def helper(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok,why):
    if not ok:raise ValueError(why)


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')


SETUP=r'''
def setup():
    target=lldb.debugger.GetSelectedTarget()
    process=target.GetProcess()
    if process.GetProcessID()!=CONFIG['appPid']: raise RuntimeError('Attached PID differs from independent Java PID')
    for name in ('InterpMethod','MethodDesc','MethodDescChunk','Module','InterpMethodContextFrame'):
        TYPES[name]=target.FindFirstType(name)
        if not TYPES[name].IsValid(): raise RuntimeError('Missing matching DWARF type: '+name)
    for name,member in [('InterpMethod','methodHnd'),('MethodDesc','m_chunkIndex'),
                        ('MethodDescChunk','m_methodTable')]:
        fields=[TYPES[name].GetFieldAtIndex(i) for i in range(TYPES[name].GetNumberOfFields())
                if TYPES[name].GetFieldAtIndex(i).GetName()==member]
        if len(fields)!=1: raise RuntimeError('Missing DWARF offset: '+name+'.'+member)
        OFFSETS[name+'.'+member]=fields[0].GetOffsetInBytes()
    descriptors=target.FindSymbols('DotNetRuntimeContractDescriptor')
    starts=[descriptors.GetContextAtIndex(i).GetSymbol().GetStartAddress() for i in range(descriptors.GetSize())
            if descriptors.GetContextAtIndex(i).GetModule().GetFileSpec().GetFilename()=='libcoreclr.so']
    if len(starts)!=1: raise RuntimeError('Actual cDAC descriptor export absent/ambiguous')
    address=starts[0].GetLoadAddress(target)
    header=read(process,address,40)
    if int.from_bytes(header[:8],'little')!=0x0043414443434e44 or int.from_bytes(header[8:12],'little')!=1:
        raise RuntimeError('Actual cDAC magic/pointer-size flags differ')
    size=int.from_bytes(header[12:16],'little')
    if size!=CONFIG['cdac']['size']: raise RuntimeError('Loaded cDAC size differs')
    descriptor=read(process,int.from_bytes(header[16:24],'little'),size)
    if hashlib.sha256(descriptor).hexdigest()!=CONFIG['cdac']['sha256']: raise RuntimeError('Loaded cDAC JSON differs from matched native file')
    method_table=json.loads(descriptor)['types']['MethodTable']
    if method_table!=CONFIG['cdac']['methodTable']: raise RuntimeError('Actual cDAC MethodTable fields differ')
    OFFSETS['MethodTable.m_dwFlags']=method_table['MTFlags']
    OFFSETS['MethodTable.m_pModule']=method_table['Module']
    symbols=target.FindSymbols('InterpreterStub')
    starts=[symbols.GetContextAtIndex(i).GetSymbol().GetStartAddress() for i in range(symbols.GetSize())
            if symbols.GetContextAtIndex(i).GetModule().GetFileSpec().GetFilename()=='libcoreclr.so']
    if len(starts)!=1: raise RuntimeError('InterpreterStub symbol absent/ambiguous')
    stub_bp=target.BreakpointCreateByAddress(starts[0].GetLoadAddress(target))
    stub_bp.SetScriptCallbackFunction('android_entry_lldb.stub')
    OBSERVATION_BPS.append(stub_bp)
    dispatch=[]
    for line in CONFIG['dispatchLines']:
        bp=target.BreakpointCreateByLocation(Path(CONFIG['source']).name,line)
        if bp.GetNumLocations()!=1: raise RuntimeError('Child dispatch DWARF line absent/ambiguous: '+str(line))
        address=bp.GetLocationAtIndex(0).GetAddress()
        instructions=target.ReadInstructions(address,4)
        text=[(i.GetMnemonic(target),i.GetOperands(target)) for i in instructions]
        bp.SetScriptCallbackFunction('android_entry_lldb.child')
        OBSERVATION_BPS.append(bp)
        dispatch.append({'line':line,'address':address.GetLoadAddress(target),'instructions':text})
    (OUT/'breakpoints.json').write_text(json.dumps({'pid':process.GetProcessID(),'runId':CONFIG['runId'],
        'stubAddress':starts[0].GetLoadAddress(target),'stubEntryRegister':'r10','dispatch':dispatch,
        'offsets':OFFSETS,'methodTableOffsetsSource':'Loaded SHA-verified cDAC JSON',
        'scope':'Execution observations only; no method preparation counted'},indent=2)+'\n')
    print('ANDROID_ENTRY_READY pid='+str(process.GetProcessID())+' runId='+CONFIG['runId'],flush=True)


def finish():
    process=lldb.debugger.GetSelectedTarget().GetProcess()
    (OUT/'capture-hits.json').write_text(json.dumps(HITS)+'\n')
    (OUT/'debugger-result.json').write_text(json.dumps({'pid':process.GetProcessID(),'runId':CONFIG['runId'],
        'exited':process.GetState()==lldb.eStateExited,'exitStatus':process.GetExitStatus(),'errors':len(ERRORS)},indent=2)+'\n')
'''


def render():
    original=helper('ios-release-package-entry-capture').LLDB_HELPER
    original=original[:original.index('def prepared(')]
    replacements={
        'import lldb':'import lldb,hashlib',
        'def typed(target,address,name):':
            "def typed(target,address,name):\n    if name=='MethodTable': return {'m_pModule':word(target.GetProcess(),address+OFFSETS['MethodTable.m_pModule']),'m_dwFlags':int.from_bytes(read(target.GetProcess(),address+OFFSETS['MethodTable.m_dwFlags'],4),'little')}",
        'def field(value,name):':
            "def field(value,name):\n    if isinstance(value,dict): return value[name]",
        "NAMES = {'Gameplay','GameplayFailure','PrivateA','PrivateB','SharedGameplay'}":"NAMES = {m['simpleName'] for m in CONFIG['modules'].values()}",
        "fast_start = frame.FindRegister('x12' if kind=='stub' else 'x28').GetValueAsUnsigned()\n        if kind=='child': fast_start -= 8":
            "fast_start = frame.FindRegister('r10').GetValueAsUnsigned() if kind=='stub' else field(typed(target,frame.FindVariable('pFrame').GetValueAsUnsigned(),'InterpMethodContextFrame'),'startIp')",
        "        if kind=='child' and fast_desc not in PENDING.get(thread_id,set()): return False\n":"",
        "frame.FindRegister('x12')":"frame.FindRegister('r10')",
        "frame.FindRegister('x28')":"frame.FindVariable('ip')",
        "            if word(process,start)!=method_address or opcode_ip!=start+8:\n                raise RuntimeError('Child execution method/first opcode mismatch')":
            "            if opcode_ip!=start+8: return False\n            if word(process,start)!=method_address: raise RuntimeError('Child live frame/method identity differs')",
        "        PENDING.get(thread_id,set()).discard(desc_address)\n        if not any(PENDING.values()): CHILD_BP.SetEnabled(False)\n":"",
        "'kind':kind,'pc':frame.GetPC(),'function':frame.GetFunctionName(),":
            "'kind':kind,'pid':process.GetProcessID(),'runId':CONFIG['runId'],'pc':frame.GetPC(),'function':frame.GetFunctionName(),",
        "        ENTRIES.append(entry)":
            "        key=entry['relativePath']+':'+entry['metadataMethodName']\n        if key not in CONFIG['requiredMethods']: return False\n        if process.GetProcessID()!=CONFIG['appPid']: raise RuntimeError('Entry PID ownership differs')\n        ENTRIES.append(entry)",
    }
    for old,new in replacements.items():
        require(original.count(old)==1,'Reviewed observer anchor changed: '+old[:80]);original=original.replace(old,new)
    result=(original+SETUP).replace('package_lldb.','android_entry_lldb.').replace('PACKAGE_INTERPRETER_ENTRY','ANDROID_SESSION_INTERPRETER_ENTRY')
    ast.parse(result)
    return result


def prepare(args):
    out=args.output.resolve();out.mkdir(exist_ok=False,parents=True)
    result={'preparedOnly':True,'entryVerified':False,'applicationExecuted':False,'completeInvocationCapture':False}
    try:
        layout=args.layout.resolve();receipt=read(layout/'layout.json')
        require(receipt['success'] and receipt['target']=='android.x64' and receipt['nativeConfiguration']=='Release','Actual accepted Release Android layout required')
        source=args.source.resolve();lines=source.read_text().splitlines()
        require(source.name=='interpexec.cpp','Supply actual matching interpexec.cpp')
        normalized=source.read_bytes().replace(bytes([13,10]),bytes([10]))
        require(hashlib.sha256(normalized).hexdigest()==args.expected_source_sha256,
                'Source differs from independently hashed matching build source after line-ending normalization')
        calls=[i for i,line in enumerate(lines[:-1]) if '// Set execution state for the new frame' in line
               and 'pMethod = pFrame->startIp->Method;' in lines[i+1]]
        require(len(calls)==2,'Expected normal-call and fast-delegate first-opcode source anchors')
        dispatch=[next(i+1 for i in range(start,start+20) if 'INTOP_NEXT;' in lines[i]) for start in calls]
        parser=helper('android-session-policy-layout');symbols=[]
        for name in ('libcoreclr.so','libclrinterpreter.so'):
            rows=[row for row in receipt['evidenceFiles'] if row.get('role')=='native-symbol-evidence' and row.get('matchingNativePath')=='native/'+name]
            require(len(rows)==1,'Exactly one matching symbol image required: '+name)
            row=rows[0];native=layout/'native'/name;debug=layout/row['path']
            require(sha(native)==row['matchingNativeSha256'] and sha(debug)==row['sha256']
                    and parser.read_build_ids(native)==parser.read_build_ids(debug)==row['gnuBuildIds'],'Native/debug actual hashes/build-id differ')
            symbols.append({'native':str(native),'sha256':sha(native),'debug':str(debug),'debugSha256':sha(debug),'buildIds':row['gnuBuildIds']})
        native_bytes=(layout/'native/libcoreclr.so').read_bytes()
        descriptors=[]
        for match in re.finditer(re.escape(b'{"version":'),native_bytes):
            try:
                raw=native_bytes[match.start():native_bytes.index(bytes([0]),match.start())]
                descriptor=json.loads(raw)
            except (ValueError,UnicodeError):continue
            if 'MethodTable' in descriptor.get('types',{}): descriptors.append((raw,descriptor))
        require(len(descriptors)==1,'Exactly one actual embedded cDAC MethodTable JSON required')
        raw,descriptor=descriptors[0];method_table=descriptor['types']['MethodTable']
        require(descriptor['version']==2 and isinstance(method_table.get('MTFlags'),int)
                and isinstance(method_table.get('Module'),int),'Actual cDAC MethodTable fields unavailable')
        cdac={'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'methodTable':method_table}
        modules,required=helper('ios-session-policy-entry').inventory(args.payload.resolve())
        identity=read(args.managed_identity);device=PurePosixPath(args.device_files)
        require(re.fullmatch(r'/data/(?:user/0|data)/[A-Za-z0-9_.]+/files',str(device)),'Actual owned app files path required')
        require(args.app_pid>0 and re.fullmatch(r'[0-9a-f]{32}',args.run_id),'Actual independently queried PID and fresh run nonce required')
        for name,module in modules.items():require(identity['files'].get('plugin/'+name)==module['sha256'],'Frozen fixture identity differs')
        config={'appPid':args.app_pid,'runId':args.run_id,'source':str(source),'dispatchLines':dispatch,'cdac':cdac,
                'modules':{str(device/'plugin'/name):row for name,row in modules.items()},'requiredMethods':required}
        write(out/'capture-config.json',config);(out/'android_entry_lldb.py').write_text(render())
        commands=['# Connect to the independently verified PID before sourcing this file.']
        for symbol in symbols:commands.append('target symbols add '+json.dumps(symbol['debug']))
        commands+=['command script import '+json.dumps(str(out/'android_entry_lldb.py')),'script android_entry_lldb.setup()',
                   '# After ANDROID_ENTRY_READY, release the nonce gate from a separate adb terminal.',
                   'continue','process status','script android_entry_lldb.finish()','quit']
        (out/'capture.lldb').write_text('\n'.join(commands)+'\n')
        result.update(success=True,layoutSha256=sha(layout/'layout.json'),managedIdentitySha256=sha(args.managed_identity),
                      source=str(source),sourceSha256=sha(source),symbols=symbols,appPid=args.app_pid,runId=args.run_id,
                      matchingBuildSourceNormalizedSha256=args.expected_source_sha256,
                      configSha256=sha(out/'capture-config.json'),observerSha256=sha(out/'android_entry_lldb.py'),driverSha256=sha(__file__),
                      sourceOriginVerification='Actual matching build source hash supplied independently; line endings normalized; DWARF line and live ip validated during observation',
                      requiredMethods=required,scope='Nine sampled fixture entry groups; actual ptrace/source mapping/optimized DWARF availability pending')
    except Exception as error:
        result.update(success=False,error=str(error));write(out/'results.json',result);raise
    write(out/'results.json',result);print('PREPARED Android Release native-entry observer; target execution pending: '+str(out))


def android_completion(args, config, capture, completed):
    """Bind Android's observed final status to original successful harness logs."""
    require(args.android_completion and args.apk_evidence and args.prepared_driver,
            'Status9 requires explicit Android completion, frozen APK evidence and original preparation driver')
    root=args.android_completion.resolve();apk=args.apk_evidence.resolve()
    require(capture==root/'observer','Completion belongs to another capture directory')
    original=read(root/'results.json');request=read(root/'request.json');state=read(apk/'state.json')
    require(original['appPid']==config['appPid'] and original['runId']==config['runId']
            and original['lldbExit']==0 and original['instrumentationExit']==0
            and original['debuggerTransportPassed'],'Original run completion/ownership differs')
    for name, expected in original['rawHashes'].items():
        require(sha(root/name)==expected,'Original raw completion bytes changed: '+name)
    require(sha(args.prepared_driver)==read(capture/'results.json')['driverSha256'],
            'Original preparation driver bytes differ')
    require(request['nonce']==config['runId'] and request['apkSha256']==state['apkSha256']
            and sha(state['apk'])==state['apkSha256'],'APK/request/run identity differs')
    package=state['package'];java=apk/'builder/Templates/MonoRunner.java'
    require(sha(java)==state['builderGeneratedHashes']['Templates/MonoRunner.java'],
            'Actual built MonoRunner source bytes differ')
    java_text=java.read_text()
    require('int retcode = executeEntryPoint(entryPointLibName, argsToForward);' in java_text
            and 'result.putInt("return-code", retcode);' in java_text
            and 'finish(retcode, result);' in java_text,'Actual Java completion path differs')
    instrumentation=(root/'instrumentation.log').read_text()
    require(re.findall(r'^INSTRUMENTATION_RESULT: return-code=([0-9-]+)$',instrumentation,re.M)==['0']
            and re.findall(r'^INSTRUMENTATION_CODE: ([0-9-]+)$',instrumentation,re.M)==['0']
            and 'Process crashed' not in instrumentation,'Android instrumentation did not finish successfully')
    managed=read(root/'managed-result.json');pid=config['appPid'];nonce=config['runId']
    require(managed['appPid']==pid and managed['runId']==nonce and managed['lane']=='required'
            and managed['exitCode']==0 and managed['policyVersion']==1 and managed['requiredPolicy']==1,
            'Actual managed completion/required policy differs')
    require((root/'pid-query.txt').read_text().strip()=='android.os.Process.myPid='+str(pid),
            'Independent Java PID query differs')
    before=(root/'before-native.log').read_text();native=(root/'native.log').read_text()
    header='ANDROID_SESSION_NATIVE pid='+str(pid)+' runId='+nonce+' InterpMode=0 RuneCLRInterpretCollectible=0'
    gate='ANDROID_ENTRY_GATE pid='+str(pid)+' runId='+nonce
    require(header in before and gate+' state=waiting dumpableResult=0' in before
            and 'CORECLR_INITIALIZE_HRESULT' not in before and header in native
            and gate+' state=released' in native
            and [line for line in native.splitlines() if line.startswith('CORECLR_INITIALIZE_HRESULT=')]==['CORECLR_INITIALIZE_HRESULT=0x0']
            and [line for line in native.splitlines() if line.startswith('CORECLR_EXECUTE_HRESULT=')]==['CORECLR_EXECUTE_HRESULT=0x0;RUNECLR_EXIT=0'],
            'Native ownership/gate/managed HRESULT completion differs')
    values=(root/'managed.log').read_text()
    require(re.findall(r'^PASS session=([0-9]+) values=.* collected=true$',values,re.M)==list(map(str,range(1,21)))
            and '20/20 execution-selection sessions passed; 20/20 contexts collected' in values
            and len(re.findall(r'^POLICY context=required-probe phase=[a-z-]+ value=1 collectible=true$',values,re.M))==260
            and len(re.findall(r'^RETIRED query=System\.InvalidOperationException protected=true$',values,re.M))==20,
            'Debugger-run lifecycle completion differs')
    text=(root/'lldb.log').read_text()
    require('ANDROID_ENTRY_READY pid='+str(pid)+' runId='+nonce in text
            and 'Process '+str(pid)+' exited with status = 9' in text
            and 'Traceback' not in text and 'error:' not in text.lower(),
            'Original debugger ready/completion/errors differ')
    return {'observedDebuggerExitStatus':9,'nativeManagedExitZero':True,
            'instrumentationFinishedReturnCode':0,'originalResultsSha256':sha(root/'results.json'),
            'monoRunnerSourceSha256':sha(java),'preparedDriverSha256':sha(args.prepared_driver),
            'interpretation':'Android post-completion process termination status; not a native exit0 or general crash allowance'}


def inspect(args):
    """Entry-only check: intentionally cannot establish platform acceptance."""
    capture=args.capture.resolve();out=args.output.resolve();require(not out.exists(),'Preserve prior observations')
    config=read(capture/'capture-config.json');prepared=read(capture/'results.json')
    require(prepared['success'] and sha(capture/'capture-config.json')==prepared['configSha256']
            and sha(capture/'android_entry_lldb.py')==prepared['observerSha256'],'Prepared capture bytes changed')
    require(not (capture/'capture-errors.json').exists(),'Native pointer/DWARF errors retained')
    completed=read(capture/'debugger-result.json')
    require(completed['exited'] and completed['errors']==0
            and completed['pid']==config['appPid'] and completed['runId']==config['runId'],'Debugger completion/ownership differs')
    completion=None
    if completed['exitStatus']==9: completion=android_completion(args,config,capture,completed)
    else: require(completed['exitStatus']==0,'Unexpected debugger final status')
    breakpoints=read(capture/'breakpoints.json')
    require(breakpoints['pid']==config['appPid'] and breakpoints['runId']==config['runId'],
            'Actual execution breakpoints belong to another capture')
    child_pcs={row['address']:row['line'] for row in breakpoints['dispatch']}
    dispatch_counts=dict.fromkeys(map(str,child_pcs.values()),0)
    entries=read(capture/'interpreter-entries.json');counts=dict.fromkeys(config['requiredMethods'],0)
    for entry in entries:
        module=config['modules'].get(entry['modulePath']);require(module is not None,'Unknown live module')
        require(entry['pid']==config['appPid'] and entry['runId']==config['runId']
                and entry['nativeModule']=='libcoreclr.so' and entry['collectible'],'Native/collectible/PID ownership differs')
        require(module['methods'].get(entry['metadataMethodName'])==entry['methodDefToken']
                and module['sha256']==entry['fileSha256'] and module['simpleName']==entry['moduleSimpleName'],'Live token/file identity differs')
        require(entry['kind'] in ('stub','child') and entry['bytecodeStart']==entry['methodDescBytecodeStart']
                and entry['firstOpcodeAddress']==entry['bytecodeStart']+8 and entry['bytecodeSizeSlots']>0
                and entry['bytecodePrefixHex'],'Live bytecode identity differs')
        require(entry['pc']==breakpoints['stubAddress'] if entry['kind']=='stub' else entry['pc'] in child_pcs,
                'Sample PC differs from actual observation breakpoint')
        if entry['kind']=='child':dispatch_counts[str(child_pcs[entry['pc']])]+=1
        key=module['relativePath']+':'+entry['metadataMethodName'];require(key in counts,'Unknown target group');counts[key]+=1
    require(entries and all(counts.values()),'Incomplete entry groups: '+str(counts))
    write(out,{'entryPointerChecksPassed':True,'platformAccepted':False,'functionalProofPending':True,
               'completeInvocationCapture':False,'entryGroupCounts':counts,'entrySamples':len(entries),
               'observedDispatchLineSampleCounts':dispatch_counts,'androidCompletion':completion,
               'breakpointsSha256':sha(capture/'breakpoints.json'),'assessmentDriverSha256':sha(__file__),
               'appPid':config['appPid'],'runId':config['runId'],'entriesSha256':sha(capture/'interpreter-entries.json'),
               'scope':'Entry-only inspection; independent same-APK functional/installed-hash/PID/map/source provenance must still be assessed'})
    print('Entry pointer/token checks passed; platform acceptance remains pending')


def main():
    p=argparse.ArgumentParser(description=__doc__);commands=p.add_subparsers(dest='command',required=True)
    a=commands.add_parser('prepare')
    for name in ('layout','source','payload','managed-identity','output'):a.add_argument('--'+name,type=Path,required=True)
    a.add_argument('--device-files',required=True);a.add_argument('--app-pid',type=int,required=True);a.add_argument('--run-id',required=True);a.set_defaults(func=prepare)
    a.add_argument('--expected-source-sha256',required=True,help='Independent matching build interpexec.cpp SHA256 with CRLF normalized to LF')
    b=commands.add_parser('inspect');b.add_argument('--capture',type=Path,required=True);b.add_argument('--output',type=Path,required=True);b.set_defaults(func=inspect)
    b.add_argument('--android-completion',type=Path)
    b.add_argument('--apk-evidence',type=Path)
    b.add_argument('--prepared-driver',type=Path)
    args=p.parse_args();args.func(args)


if __name__=='__main__':main()
