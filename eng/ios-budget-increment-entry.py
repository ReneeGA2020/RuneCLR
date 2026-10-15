#!/usr/bin/env python3
"""Independent debugger lane: sample the current budget author IL entry identities."""
import argparse,hashlib,subprocess,importlib.util,json,os,re,shutil,struct,subprocess,time,uuid
from pathlib import Path

PARENT_DRIVER_SHA256 = 'ba59203a2c692a607dee7a606bc42ead69160b63256777fd1c1f8e89c2fdb47c'
def helper(name):
 spec=importlib.util.spec_from_file_location(name.replace('-','_'),Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def pe_mvid(path):
 data=path.read_bytes();u16=lambda at:struct.unpack_from('<H',data,at)[0];u32=lambda at:struct.unpack_from('<I',data,at)[0];pe=u32(0x3c);opt=pe+24;dirs=opt+(112 if u16(opt)==0x20b else 96);sections=[opt+u16(pe+20)+40*i for i in range(u16(pe+6))]
 def offset(rva):
  for s in sections:
   if u32(s+12)<=rva<u32(s+12)+max(u32(s+8),u32(s+16)):return u32(s+20)+rva-u32(s+12)
  raise RuntimeError('metadata RVA outside sections')
 clr=offset(u32(dirs+14*8));rootRva=u32(clr+8);root=offset(rootRva)
 if data[root:root+4]!=b'BSJB':raise RuntimeError('metadata signature missing')
 at=root+16+((u32(root+12)+3)&~3);count=u16(at+2);at+=4;streams={}
 for _ in range(count):
  end=data.index(bytes([0]),at+8);streams[data[at+8:end].decode('ascii')]=u32(at);at=(end+4)&~3
 table=root+streams.get('#~',streams.get('#-'));flags=data[table+6];valid=struct.unpack_from('<Q',data,table+8)[0];row=table+24+4*bin(valid).count('1');stringSize=4 if flags&1 else 2;guidSize=4 if flags&2 else 2;index=(u32 if guidSize==4 else u16)(row+2+stringSize)
 if not valid&1 or index<=0:raise RuntimeError('Module MVID absent')
 guidRelative=streams['#GUID']+16*(index-1);value=data[root+guidRelative:root+guidRelative+16]
 return {'moduleMvid':str(uuid.UUID(bytes_le=value)),'moduleMvidBytesHex':value.hex(),'metadataRootRva':rootRva,'metadataRootOffset':root,'moduleMvidRva':rootRva+guidRelative,'moduleMvidOffset':root+guidRelative}

def render_observer(prior):
 text=prior.LLDB_HELPER.replace("NAMES = {'Gameplay','GameplayFailure','PrivateA','PrivateB','SharedGameplay'}","NAMES = {x['simpleName'] for x in CONFIG['modules'].values()}").replace("if names[0].rsplit('.',1)[-1] not in ('OnStart','OnTick','OnStop','Read','Next'): return False","if CONFIG['modules'][path]['relativePath']+':'+names[0] not in CONFIG['requiredMethods']: return False").replace('PACKAGE_INTERPRETER_ENTRY','BUDGET_INTERPRETER_ENTRY')
 text=text.replace("'x12' if kind=='stub' else 'x28'","'x12' if kind=='stub' else 'x24'")
 old="""            context,method = frame.FindVariable('pFrame'),frame.FindVariable('pMethod')
            if not context.IsValid() or context.GetError().Fail() or not method.IsValid() or method.GetError().Fail():
                raise RuntimeError('Post-ReInit DWARF variables unavailable')
            context_address = context.GetValueAsUnsigned()
            start = field(typed(target,context_address,'InterpMethodContextFrame'),'startIp')
            method_address = method.GetValueAsUnsigned()
            opcode_ip = frame.FindRegister('x28').GetValueAsUnsigned()"""
 new="""            context_address = word(process,frame.FindRegister('x19').GetValueAsUnsigned()+FRAME_SPILL)
            start = field(typed(target,context_address,'InterpMethodContextFrame'),'startIp')
            method_address = word(process,start)
            opcode_ip = frame.FindRegister('x24').GetValueAsUnsigned()"""
 if text.count(old)!=1:raise RuntimeError('old child observer differs')
 text=text.replace(old,new).replace("('MethodDescChunk','m_methodTable'),('MethodTable','m_dwFlags')]","('MethodDescChunk','m_methodTable'),('MethodTable','m_dwFlags'),('InterpMethodContextFrame','startIp')]")
 text=text.replace('import json\n','import json,re\n',1).replace('CHILD_BP = None','CHILD_BP = None\nFRAME_SPILL = None',1).replace('global CHILD_BP','global CHILD_BP, FRAME_SPILL',1)
 text=text.replace("bp = target.BreakpointCreateByLocation(CONFIG['source'],CONFIG['dispatchLine'])","bp = target.BreakpointCreateByLocation(CONFIG['source'],CONFIG['dispatchLine'])\n    bp.SetEnabled(False)\n    OBSERVATION_BPS.extend([stub_bp,bp])")
 text=text.replace("if not text or text[0]!=('ldr','w24, [x28]'):","if len(text)!=4 or text[0]!=('ldr','w25, [x24]') or 'x19' not in text[1][1]:").replace('Pinned first-opcode x28 dispatch differs: ','Pinned first-opcode/frame-register contract differs: ')
 anchor="    bp.SetScriptCallbackFunction('package_lldb.child')"
 contract=r"""    spill = re.fullmatch(r'x8, \[x19, #0x([0-9a-f]+)\]',text[1][1]) if text[1][0]=='ldr' else None
    if spill is None or text[2]!=('ldr','x8, [x8, #0x%x]'%OFFSETS['InterpMethodContextFrame.startIp']) or text[3]!=('ldr','x8, [x8]'):
        raise RuntimeError('Child frame spill/startIp load sequence differs')
    FRAME_SPILL = int(spill.group(1),16)
    # This Release function spills pFrame; x19 is the dynamic stack base.
    # Bind the live spill to DWARF at the immediately preceding ReInit state.
    file_pc = address.GetFileAddress()
    dwarf_locations = CONFIG['pFrameDwarfSpillLocations']
    frame_matches = [v for v in dwarf_locations if v['start']<=file_pc-40<v['end'] and v['offset']==FRAME_SPILL]
    prior = target.ReadInstructions(address.GetModule().ResolveFileAddress(file_pc-48),12)
    before = [(i.GetMnemonic(target),i.GetOperands(target)) for i in prior]
    if len(frame_matches)!=1 or len(before)!=12 or before[0]!=('str','x8, [x19, #0x%x]'%FRAME_SPILL) or before[2]!=('ldr','x8, [x24], #0x8'):
        raise RuntimeError('Child pFrame DWARF/ReInit spill identity differs')
    CONFIG['childFrameContract']={'filePc':file_pc,'frameSpillOffset':FRAME_SPILL,'dwarfLocation':frame_matches[0],'precedingInstructions':before}
"""
 if text.count(anchor)!=1:raise RuntimeError('child setup anchor differs')
 text=text.replace(anchor,contract+anchor).replace("'prefilterOffsets':OFFSETS,","'prefilterOffsets':OFFSETS,'childFrameContract':CONFIG['childFrameContract'],")
 marker="        expected = CONFIG['modules'][module_path]"
 added="""        expected = CONFIG['modules'][module_path]
        base = field(module,'m_baseAddress')
        mapped_mvid = None
        for layout,root_key,mvid_key in [('rva','metadataRootRva','moduleMvidRva'),('flat','metadataRootOffset','moduleMvidOffset')]:
            try:
                if read(process,base+expected[root_key],4)==b'BSJB' and read(process,base+expected[mvid_key],16).hex()==expected['moduleMvidBytesHex']:
                    mapped_mvid = layout
                    break
            except RuntimeError: pass
        if mapped_mvid is None: raise RuntimeError('Actual loaded metadata MVID differs from hash-bound author PE')"""
 if text.count(marker)!=1:raise RuntimeError('Module identity anchor differs')
 text=text.replace(marker,added).replace("'metadataMethodName':names[0],'bytecodeStart':start", "'metadataMethodName':names[0],'moduleMvid':expected['moduleMvid'],'loadedMetadataMvidValidated':True,'loadedPELayout':mapped_mvid,'bytecodeStart':start")
 text += """
def safe_setup():
    try: setup()
    except Exception as error:
        ERRORS.append({'kind':'setup','error':str(error)})
        (OUT/'capture-errors.json').write_text(json.dumps(ERRORS,indent=2)+chr(10))
        for bp in OBSERVATION_BPS: bp.SetEnabled(False)
        lldb.debugger.GetSelectedTarget().GetProcess().Kill()
        raise
"""
 compile(text,'package_lldb.py','exec')
 return text

def main():
 p=argparse.ArgumentParser();p.add_argument('--player',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--native',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert subprocess.check_output(['git','-C',str(a.runtime),'rev-parse','HEAD^{tree}'],text=True).strip()=='91673a7980bda79006259e525741fecb04324444';assert hashlib.sha256(a.native.read_bytes()).hexdigest()=='de7b2c8ddda01d44b65b67c1a78b895f38cf2b31f0668308998775112b6ec575';O=a.output.resolve();O.mkdir(exist_ok=False);shutil.copy2(__file__,O/'driver.py');c=helper('ios-r2r-fix-verify');m=helper('verify-ios-packages');metadata=helper('ios-r2r-release-verify');prior=helper('ios-release-package-entry-capture');s=json.loads((a.player/'state.json').read_text());app=Path(s['installedApp']);data=Path(s['dataContainer']);plugin=data/'Documents/budget-plugin';sim=s['simulator'];nonce=uuid.uuid4().hex;dwarf=a.native.with_name(a.native.name+'.dwarf');source=a.runtime/'src/coreclr/vm/interpexec.cpp';nativeSections=m.macho_sections(a.native)
 if not dwarf.is_file() or nativeSections!=m.macho_sections(app/'libcoreclr.dylib'):raise RuntimeError('matching native/DWARF missing or differing')
 symbols=c.capture(['xcrun','dwarfdump','--uuid',dwarf]);uuids=re.findall(r'UUID: ([0-9A-Fa-f-]+)',symbols)
 if len(uuids)!=1 or uuids[0].replace('-','').lower()!=nativeSections['uuid']:raise RuntimeError('native/DWARF UUID mismatch')
 if m.tree(app)!=s['bundleHashes']:raise RuntimeError('installed app differs')
 modules={};required=[]
 for name in ('HostBudgetProbe.Payload.dll','HostBudgetProbe.Private.dll'):
  p=plugin/name;q=a.inputs/'plugin'/name
  if c.sha(p)!=c.sha(q):raise RuntimeError('original author IL differs')
  methods=metadata.plugin_methods(p,required=(),qualified=True);layout=m.il_layout(p)
  if not layout['ilOnly'] or layout['managedNativeRva']:raise RuntimeError('author has native bodies')
  modules[str(p)]={'relativePath':name,'sha256':c.sha(p),'simpleName':name[:-4],'methods':methods,'layout':layout,**pe_mvid(p)}
  fixed=['HostBudgetUGC.Base..ctor','HostBudgetUGC.Base.OnStart','HostBudgetUGC.Base.OnStop','HostBudgetUGC.Normal..ctor','HostBudgetUGC.Normal.OnStart','HostBudgetUGC.Normal.OnTick','HostBudgetUGC.FiniteCleanup.OnTick'] if name.endswith('Payload.dll') else ['HostBudgetUGC.Private.Helper.Finite']+[n for n in methods if n.endswith('.<Finite>b__0')]
  if not set(fixed)<=methods.keys() or (name.endswith('Private.dll')and len(fixed)!=2):raise RuntimeError('current author metadata changed')
  required.extend(name+':'+n for n in fixed)
 lines=source.read_text().splitlines();anchors=[i for i,l in enumerate(lines) if '// Set execution state for the new frame' in l and 'pMethod = pFrame->startIp->Method;' in lines[i+1] and 'if (stack + pMethod->allocaSize' in chr(10).join(lines[i:i+10])]
 if len(anchors)!=1:raise RuntimeError('child source anchor differs')
 dispatch=[i+1 for i in range(anchors[0],anchors[0]+20) if 'INTOP_NEXT;' in lines[i]]
 if len(dispatch)!=1:raise RuntimeError('child dispatch source line ambiguous')
 dwarf_text=c.capture(['xcrun','dwarfdump','--name=pFrame',dwarf]);(O/'pframe-dwarf.txt').write_text(dwarf_text)
 locations=[]
 for block in dwarf_text.split(chr(10)+chr(10)):
  if 'interpexec.cpp' not in block:continue
  for match in re.finditer(r'\[0x([0-9a-f]+), 0x([0-9a-f]+)\): DW_OP_breg19 W19\+(\d+)',block):locations.append({'start':int(match[1],16),'end':int(match[2],16),'offset':int(match[3]),'die':block.splitlines()[0]})
 if not locations:raise RuntimeError('pFrame DWARF spill locations absent')
 c.write(O/'capture-config.json',{'modules':modules,'requiredMethods':required,'source':str(source),'dispatchLine':dispatch[0],'pFrameDwarfSpillLocations':locations})
 text=render_observer(prior);(O/'package_lldb.py').write_text(text)
 c.write(O/'identity.json',{'native':str(a.native),'nativeSha256':c.sha(a.native),'dwarf':str(dwarf),'dwarfSha256':c.sha(dwarf),'uuid':uuids[0],'runtimeCommit':c.capture(['git','-C',a.runtime,'rev-parse','HEAD']),'runtimeTree':c.capture(['git','-C',a.runtime,'rev-parse','HEAD^{tree}']),'sourceSha256':c.sha(source),'nativeSections':nativeSections,'moduleFiles':modules,'bundleFiles':s['bundleHashes'],'normalFunctionalLaneIndependent':True,'nativeEntryProof':False})
 env={k:v for k,v in os.environ.items() if not k.startswith(('SIMCTL_CHILD_DOTNET_','SIMCTL_CHILD_COMPlus_','SIMCTL_CHILD_RUNECLR_'))};env.update(SIMCTL_CHILD_RUNECLR_BUDGET_NONCE=nonce,SIMCTL_CHILD_DOTNET_InterpMode='0',SIMCTL_CHILD_DOTNET_RuneCLRInterpretCollectible='0',SIMCTL_CHILD_DOTNET_ReadyToRun='1');c.write(O/'request.json',{'nonce':nonce,'debugger':True,'simulator':sim,'bundleId':s['bundleId'],'environment':{k:v for k,v in env.items() if k.startswith('SIMCTL_CHILD_')}});r={'passed':False,'debugger':True,'nonce':nonce,'nativeEntryProof':False};booted=False
 try:
  c.logged(['xcrun','simctl','boot',sim],O/'boot-command.log');booted=True;c.logged(['xcrun','simctl','bootstatus',sim,'-b'],O/'boot.log')
  c.logged(['xcrun','simctl','launch','--wait-for-debugger','--stdout='+str(O/'managed.stdout.log'),'--stderr='+str(O/'managed.stderr.log'),sim,s['bundleId']],O/'launch.log',env=env);pid=int(re.search(r': ([0-9]+)',(O/'launch.log').read_text()).group(1));r['appPid']=pid
  commands=['breakpoint set -n coreclr_initialize','continue','breakpoint disable 1','target symbols add '+str(dwarf),'command script import '+str(O/'package_lldb.py'),'script package_lldb.safe_setup()','continue','process status','script package_lldb.finish()','quit'];(O/'capture.lldb').write_text(chr(10).join(commands)+chr(10));status=c.logged(['xcrun','lldb','--batch','--attach-pid',str(pid),'--source',O/'capture.lldb'],O/'lldb.log',timeout=600,check=False)
  dest=data/'Documents'/('budget-evidence-'+nonce)
  if dest.is_dir():shutil.copytree(dest,O/'adapter-evidence')
  es=json.loads((O/'interpreter-entries.json').read_text()) if (O/'interpreter-entries.json').exists() else [];counts={n:0 for n in required};valid=[]
  for e in es:
   module=modules.get(e['modulePath']);ok=bool(module and e['nativeModule']=='libcoreclr.dylib' and e['collectible'] and module['sha256']==e['fileSha256'] and module['methods'].get(e['metadataMethodName'])==e['methodDefToken'] and e['moduleSimpleName']==module['simpleName'] and e['moduleMvid']==module['moduleMvid'] and e['loadedMetadataMvidValidated'] is True and e['bytecodeStart']==e['methodDescBytecodeStart'] and e['firstOpcodeAddress']==e['bytecodeStart']+8 and e['bytecodeSizeSlots']>0 and e['bytecodePrefixHex']);valid.append(ok);key=e['relativePath']+':'+e['metadataMethodName']
   if key in counts:counts[key]+=1
  logs=(O/'managed.stdout.log').read_text(errors='replace')+(O/'managed.stderr.log').read_text(errors='replace');debuglog=(O/'lldb.log').read_text(errors='replace');adapter=json.loads((O/'adapter-evidence/result.json').read_text()) if (O/'adapter-evidence/result.json').exists() else {};complete=adapter.get('passed')is True and adapter.get('processId')==pid and adapter.get('nonce')==nonce and adapter.get('contexts')==73 and len(adapter.get('cases',[]))==15;unchanged=m.tree(app)==s['bundleHashes'] and all(c.sha(p)==v['sha256'] for p,v in modules.items())
  r.update(lldbExit=status,normalExit='exited with status = 0' in debuglog,adapterCompleted=complete,bundleAndAuthorUnchanged=unchanged,requiredMethodEntryCounts=counts,validEntries=len(es),allEntriesValid=all(valid),captureErrors=(O/'capture-errors.json').exists());r['passed']=status==0 and r['normalExit'] and complete and unchanged and bool(es) and all(valid) and all(counts.values()) and not r['captureErrors'];r['nativeEntryProof']=r['passed'];r['scope']='Targets nine current author method groups; observed counts are recorded separately; no full invocation or physical-device proof'
 finally:
  if booted:
   c.logged(['xcrun','simctl','terminate',sim,s['bundleId']],O/'terminate.log',check=False);q=c.logged(['xcrun','simctl','shutdown',sim],O/'shutdown.log',check=False);c.write(O/'cleanup.json',{'simulator':sim,'exit':q})
  c.write(O/'results.json',r);print(json.dumps(r,indent=2),flush=True)
if __name__=='__main__':main()
