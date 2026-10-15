#!/usr/bin/env python3
"""Read-only budget evidence audit; incomplete mobile provenance stays pending."""
import argparse,copy,hashlib,json,re,zipfile
from pathlib import Path
CASES=('Normal','EndlessTick','StartLoop','CatchResume','BroadCatchResume','SignalFilter','FilterExhaustion','ConstructorLoop','StaticConstructorLoop','FiniteCleanup','InfiniteCleanup','StopLoop','MaliciousMessage','ExplicitCanceled','Recovery')
TERM='The native prototype instruction budget terminated author execution.'
LOGS={'EndlessTick':['start','tick-before'],'StartLoop':['start'],'CatchResume':['start'],'BroadCatchResume':['start'],'SignalFilter':['start'],'FilterExhaustion':['start','filter-before'],'ConstructorLoop':[],'StaticConstructorLoop':[],'FiniteCleanup':['start','finally','private-finally','private-delegate'],'InfiniteCleanup':['start','private-infinite-finally'],'StopLoop':['start','tick=0','tick=1','tick=2','stop-before'],'MaliciousMessage':['start','stop'],'ExplicitCanceled':['start','stop']}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def check(v,msg):
 if not v:raise AssertionError(msg)
def rows(a,receipts,nonce,pid):
 check(re.fullmatch('[0-9a-fA-F]{32}',nonce or '') and type(pid)is int and pid>0,'actual owner nonce/PID')
 check(a['passed']is True and a['nonce']==nonce and a['processId']==pid and a['scenario']=='all' and a['contexts']==73 and len(a['cases'])==15,'actual aggregate owner15/73')
 check(tuple(x['scenario'] for x in a['cases'])==CASES,'fixed ordered15 scenarios')
 total=0;metrics=[]
 for item in a['cases']:
  name=item['scenario'];derived=hashlib.sha256((nonce+':'+name).encode()).hexdigest()[:32];count=20 if name=='Normal' else 40 if name=='Recovery' else 1
  check(item['nonce']==derived and item['contexts']==count and item['receipt']==name+'/result.json','case nonce/path/count '+name)
  r=receipts[name];check(r['passed']is True and r['nonce']==derived and r['scenario']==name and r['mode']=='budget' and len(r['rows'])==count,'case result '+name)
  for i,row in enumerate(r['rows']):
   typ='Normal' if name=='Recovery' and i%2 else 'CatchResume' if name=='Recovery' else name
   session=i//2+1 if name=='Recovery' else i+1;role='good' if name=='Recovery' and i%2 else 'bad' if name=='Recovery' else 'case'
   check(row['session']==session and row['role']==role and row['collected']is True,'ordered collection '+name)
   report=row['report'];b=report['PrototypeBudget'];normal=typ=='Normal';active=typ in ('Normal','MaliciousMessage','ExplicitCanceled');entities=0 if typ in ('ConstructorLoop','StaticConstructorLoop')else 1
   check(report['MapId']=='host-budget-'+typ and report['CreatedEntities']==entities and report['ReleasedEntities']==entities and report['RemainingEntities']==0,'owned resources '+typ)
   check(report['ExecutionPolicy']==1 and report['ExecutionPolicyVersion']==1,'native required ack '+typ)
   check(report['Outcome']==(0 if normal else 1) and report['CompletedTicks']==(3 if typ in ('Normal','StopLoop')else 0),'truthful ticks '+typ)
   check(report['Logs']==(['start','static=1','tick=0','tick=1','tick=2','stop']if normal else LOGS[typ]),'actual static/catch/filter/continuation/cleanup '+typ)
   error=None if normal else 'HostBudgetUGC.BadMessage'if typ=='MaliciousMessage'else 'System.OperationCanceledException'if typ=='ExplicitCanceled'else 'OnStop: '+TERM+'; '+TERM if typ=='StopLoop'else TERM
   check(report['Error']==error,'safe error/native attribution '+typ)
   check(b['IsTerminated']is(not active)and b['Reason']==(0 if active else 1)and b['ExecutionExhausted']is(not active),'actual latch '+typ)
   for field in ('ExecutionRemaining','ExecutionExecuted','CleanupRemaining','CleanupExecuted'):check(type(b[field])is int and b[field]>=0,'nonnegative scalar '+field)
   limit=1000000 if normal else 8192
   check(b['ExecutionRemaining']+b['ExecutionExecuted']==limit and b['CleanupRemaining']+b['CleanupExecuted']==4096,'exact ledgers '+typ)
   if active:check(b['ExecutionExecuted']>0 and b['ExecutionRemaining']>0 and b['Phase']==0 and b['CleanupExecuted']==0,'active ordinary/normal '+typ)
   else:check(b['ExecutionRemaining']==0 and b['ExecutionExecuted']==8192 and b['Phase']==(2 if typ=='InfiniteCleanup'else 1),'terminal budget/phase '+typ)
   if typ=='InfiniteCleanup':check(b['CleanupExecuted']==4096 and b['CleanupRemaining']==0,'infinite cleanup bounded')
   elif typ=='FiniteCleanup':check(0<b['CleanupExecuted']<=4096,'finite private/delegate cleanup reserve')
   else:check(b['CleanupExecuted']==0,'unexpected cleanup reserve '+typ)
   total+=1
  metrics.append({'scenario':name,'contexts':count,'executionExecuted':r['rows'][0]['report']['PrototypeBudget']['ExecutionExecuted'],'cleanupExecuted':r['rows'][0]['report']['PrototypeBudget']['CleanupExecuted']})
 check(total==73,'actual73 rows')
 return metrics

def adapter(directory,nonce,pid):
 a=load(directory/'result.json');receipts={};hashes={'result.json':sha(directory/'result.json')}
 for item in a['cases']:
  check(item['receipt']==item['scenario']+'/result.json','fixed child path');p=directory/item['receipt']
  check(sha(p)==item['receiptSha256'],'actual child hash '+item['scenario']);hashes[item['receipt']]=sha(p);receipts[item['scenario']]=load(p)
 return a,receipts,rows(a,receipts,nonce,pid),hashes

def inputs(directory):
 m=load(directory/'input-manifest.json');expected={'trusted/MobileHostBudgetProbe.dll','trusted/RuneCLR.Runtime.dll','trusted/RuneCLR.Packages.dll','trusted/RuneCLR.Abstractions.dll','plugin/HostBudgetProbe.Payload.dll','plugin/HostBudgetProbe.Private.dll'}
 check(set(m['files'])==expected and tuple(m['cases'])==CASES,'fixed six DLL identities')
 with zipfile.ZipFile(directory/'mobile-host-budget-inputs.zip')as z:
  for name,value in m['files'].items():check(sha(directory/name)==value==hashlib.sha256(z.read(name)).hexdigest(),'actual source/archive DLL '+name)
 return m

def negative_controls(a,r,nonce,pid):
 mutations={'wrong-owner-nonce':lambda a,r:a.update(nonce='0'*32),'wrong-owner-pid':lambda a,r:a.update(processId=pid+1),'missing-case':lambda a,r:a['cases'].pop(),'not-collected':lambda a,r:r['Normal']['rows'][0].update(collected=False),'static-not-reset':lambda a,r:r['Normal']['rows'][0]['report']['Logs'].__setitem__(1,'static=2'),'terminal-resume':lambda a,r:r['CatchResume']['rows'][0]['report']['Logs'].append('resume'),'recovery-role':lambda a,r:r['Recovery']['rows'][1].update(role='bad'),'completed-ticks':lambda a,r:r['StopLoop']['rows'][0]['report'].update(CompletedTicks=0),'resource-leak':lambda a,r:r['EndlessTick']['rows'][0]['report'].update(RemainingEntities=1),'budget-ledger':lambda a,r:r['ConstructorLoop']['rows'][0]['report']['PrototypeBudget'].update(ExecutionExecuted=8191),'ordinary-oce-quota':lambda a,r:r['ExplicitCanceled']['rows'][0]['report']['PrototypeBudget'].update(Reason=1),'malicious-message-stop':lambda a,r:r['MaliciousMessage']['rows'][0]['report']['Logs'].remove('stop'),'infinite-finally-phase':lambda a,r:r['InfiniteCleanup']['rows'][0]['report']['PrototypeBudget'].update(Phase=1)}
 result=[]
 for name,mutation in mutations.items():
  aa,rr=copy.deepcopy(a),copy.deepcopy(r);mutation(aa,rr)
  try:rows(aa,rr,nonce,pid)
  except(AssertionError,KeyError):result.append({'name':name,'rejected':True,'inMemoryOnly':True})
  else:raise AssertionError('corrupted actual receipt accepted '+name)
 return result

def ios_transport_v1_gate(path,directory,a,input_directory,m):
 # Compatibility for the preserved first simulator run. Its hash paths are
 # explicitly relative to run-all. Its before inventory was built-before-
 # install, so even a valid actual run cannot pass installed-before acceptance.
 run=load(path);root=path.parent.resolve();raw=root/'run-all';pending=[]
 def need(value,message):
  if not value:pending.append(message)
 need(run.get('platform')=='iossimulator.arm64','actual iOS simulator platform missing')
 need(run.get('appPid')==a['processId']and run.get('nonce')==a['nonce'],'actual native/controller owner differs')
 need(run.get('simctlExit')==0 and run.get('debugger')is False and run.get('launchCount')==1,'actual single nondebugger completion missing')
 need(run.get('inputFiles')==m['files']and run.get('inputManifestSha256')==sha(input_directory/'input-manifest.json'),'six source DLL binding differs')
 hashes=run.get('rawHashes',{});need(len(hashes)>=18,'actual recursive run-all raw hash inventory missing')
 for relative,value in hashes.items():
  file=(raw/relative).resolve();need(file.is_relative_to(raw)and file.is_file()and sha(file)==value.lower(),'actual raw hash mismatch '+relative)
 for file in[directory/'result.json',*[directory/x['receipt']for x in a['cases']]]:
  relative=file.resolve().relative_to(raw).as_posix()if file.resolve().is_relative_to(raw)else None
  need(relative is not None and hashes.get(relative,'').lower()==sha(file),'actual original adapter receipt unbound '+str(file))
 state=load(root/'state.json');build=load(root/'matching-build.json');request=load(raw/'request.json')
 need(sha(root/'state.json')==run.get('stateSha256'),'actual state SHA differs')
 need(sha(root/'matching-build.json')==run.get('buildReceiptSha256')==state.get('buildReceiptSha256'),'actual matching build SHA differs')
 need(build.get('success')is True and build.get('base')=='0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'and build.get('commit')==run.get('runtimeCommit')==state.get('runtimeCommit')and build.get('tree')==run.get('runtimeTree')==state.get('runtimeTree'),'actual source base/commit/tree differs')
 need(build.get('configuration')=='Release'and build.get('target')=='iossimulator.arm64'and build.get('assessment',{}).get('staticInterpreter')is True and build.get('assessment',{}).get('dynamicJitEnabled')is False,'actual Release ARM64 static interpreter build missing')
 need(request.get('nonce')==a['nonce']and request.get('bundleId')==state.get('bundleId')and request.get('simulator')==state.get('simulator')and request.get('mode')==0 and request.get('diagnostic')==0 and request.get('readyToRun')==1 and request.get('debugger')is False,'actual platform request/config differs')
 need(run.get('pluginHashes')==state.get('pluginHashes')=={Path(k).name:v for k,v in m['files'].items()if k.startswith('plugin/')},'actual installed author original hashes differ')
 before=state.get('bundleHashes',{});after=run.get('installedBundleHashes',{})
 need(bool(before)and before==after and len(after)==run.get('bundleHashCount'),'built-before/install-postrun actual bundle identity differs')
 for name in('System.Private.CoreLib.dll','SessionBridge.dll','MobileHostBudgetProbe.dll','RuneCLR.Runtime.dll','RuneCLR.Packages.dll','RuneCLR.Abstractions.dll'):
  need(name in after and state.get('layouts',{}).get(name,{}).get('managedNativeRva',0)>0,'actual trusted R2R component missing '+name)
 need(state.get('wrapperSourceSha256')==sha(root/'runtime.m')and run.get('sourceDriverSha256')==sha(root/'driver.py'),'actual rebuilt wrapper/controller source SHA differs')
 text=(raw/'launch.log').read_text(encoding='utf-8',errors='replace')
 header=f"MOBILE_BUDGET_NATIVE pid={a['processId']} nonce={a['nonce']} InterpMode=0 RuneCLRInterpretCollectible=0 ReadyToRun=1"
 need(len(re.findall(re.escape(header)+r'$',text,re.M))==1,'actual native owner/config header missing')
 need(re.search(r'CORECLR_INITIALIZE_HRESULT=0x0(?:;|\s|$)',text)and re.search(r'CORECLR_EXECUTE_HRESULT=0x0(?:;|\s|$)',text)and re.search(r'RUNECLR_EXIT=0(?:;|\s|$)',text),'actual native initialize/execute/managed zero exits missing')
 complete=f"MOBILE_HOST_BUDGET_COMPLETE nonce={a['nonce']} scenario=all pid={a['processId']} cases=15 contexts=73 passed=true"
 need(len(re.findall(re.escape(complete)+r'$',text,re.M))==1,'actual owned aggregate completion missing')
 need(text.splitlines().count(str(state.get('bundleId'))+': '+str(a['processId']))==1,'actual simctl bundle/PID marker missing')
 verified=not pending
 pending.append('Installed-app pre-run inventory was not sampled: before scope is built-before-install; do not reconstruct installed-before from postrun hashes')
 return{'mobileVerified':False,'mobileFunctionalVerified':verified,'platform':'iossimulator.arm64','pending':pending,'nativeEntryProof':False,'inventoryBeforeScope':'built-before-install','inventoryAfterScope':'installed-postrun','installedBeforeObserved':False,'actualBundleCount':len(after),'mobileRawFilesVerified':len(hashes)}

def mobile_gate(path,directory,a,input_directory,m):
 if load(path).get('schema')=='runeclr.ios-budget.transport.v1':return ios_transport_v1_gate(path,directory,a,input_directory,m)
 run=load(path);root=path.parent.resolve();pending=[]
 def need(v,msg):
  if not v:pending.append(msg)
 platform=run.get('platform');need(platform in ('iossimulator.arm64','android.x86_64'),'explicit actual mobile platform/ABI missing')
 need(run.get('appPid')==a['processId'] and run.get('nonce')==a['nonce'],'native/controller PID/nonce not bound')
 need(run.get('timedOut')is False and run.get('debugger')is False,'nondebugger deadline/completion evidence missing')
 need(run.get('simctlExit')==0 if platform=='iossimulator.arm64'else run.get('instrumentationExit')==0,'actual platformrunner exit0 missing')
 need(run.get('inputManifestSha256')==sha(input_directory/'input-manifest.json')and run.get('inputFiles')==m['files'],'original six source DLL bindings missing')
 need(re.fullmatch('[0-9a-f]{40}',str(run.get('runtimeCommit','')))and re.fullmatch('[0-9a-f]{40}',str(run.get('runtimeTree',''))),'matching runtime commit/tree missing')
 hashes=run.get('rawHashes',{});need(bool(hashes),'recursive raw SHA inventory missing')
 for relative,value in hashes.items():
  file=(root/relative).resolve();need(file.is_relative_to(root)and file.is_file()and sha(file)==value.lower(),'actual raw file/hash mismatch '+relative)
 for file in [directory/'result.json',*[directory/x['receipt']for x in a['cases']]]:
  relative=file.resolve().relative_to(root).as_posix()if file.resolve().is_relative_to(root)else None
  need(relative is not None and hashes.get(relative,'').lower()==sha(file),'original adapter receipt unbound '+str(file))
 native_relative=run.get('nativeLog');native_path=(root/str(native_relative)).resolve()if native_relative else None
 if native_path and native_path.is_relative_to(root)and native_path.is_file():
  text=native_path.read_text(encoding='utf-8',errors='replace');need(hashes.get(native_relative,'').lower()==sha(native_path),'native stream SHA missing')
  marker=f"MOBILE_BUDGET_NATIVE pid={a['processId']} nonce={a['nonce']} InterpMode=0 RuneCLRInterpretCollectible=0 ReadyToRun=1"
  need(len(re.findall(re.escape(marker)+r'$',text,re.M))==1,'owned native PID/nonce/config header missing')
  need(len(re.findall(r'^CORECLR_INITIALIZE_HRESULT=0x0\s*$',text,re.M))==1 and len(re.findall(r'^CORECLR_EXECUTE_HRESULT=0x0;\s*RUNECLR_EXIT=0\s*$',text,re.M))==1,'exact native initialize/execute HRESULT0/managed exit0 missing')
  # AndroidConsole owns a separate original managed stream; no copied or
  # synthesized completion marker is required in the native FD stream.
  managed_text=text
  if platform=='android.x86_64':
   managed_relative=run.get('managedLog','managed.log');managed_path=(root/managed_relative).resolve()
   if managed_path.is_relative_to(root)and managed_path.is_file():
    need(hashes.get(managed_relative,'').lower()==sha(managed_path),'original Android managed stream SHA missing')
    managed_text=managed_path.read_text(encoding='utf-8',errors='replace')
   else:managed_text='';pending.append('original Android managed stream missing')
  marker=f"MOBILE_HOST_BUDGET_COMPLETE nonce={a['nonce']} scenario=all pid={a['processId']} cases=15 contexts=73 passed=true"
  need(len(re.findall(re.escape(marker)+r'$',managed_text,re.M))==1,'actual managed owned completion missing')
 else:pending.append('native raw stream path missing')
 inventory=run.get('installedInventory',{});need(bool(inventory.get('before'))and inventory.get('before')==inventory.get('after'),'actual complete installed inventory before/after missing')
 for stage in ('before','after'):
  relative=inventory.get(stage+'RawPath');file=(root/str(relative)).resolve()if relative else None
  if file and file.is_relative_to(root)and file.is_file():
   need(hashes.get(relative,'').lower()==sha(file),'installed '+stage+' inventory raw SHA missing')
   need(load(file)==inventory.get(stage),'installed '+stage+' inventory does not match original raw receipt')
  else:pending.append('installed '+stage+' raw inventory file missing')
 need(inventory.get('authorSources')=={k:v for k,v in m['files'].items()if k.startswith('plugin/')},'actual installed author original hashes missing')
 need(run.get('bundleUnchanged')is True,'installed bundle unchanged proof missing')
 need(run.get('buildReceiptSha256')and hashes.get(run.get('buildReceiptRawPath'))==run.get('buildReceiptSha256'),'matching build receipt raw SHA missing')
 relative=run.get('buildReceiptRawPath');file=(root/str(relative)).resolve()if relative else None
 if file and file.is_relative_to(root)and file.is_file():
  build=load(file)
  need(build.get('success')is True and build.get('base')=='0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'and build.get('commit')==run.get('runtimeCommit')and build.get('tree')==run.get('runtimeTree'),'actual build source identity/content missing')
  expected_target='iossimulator.arm64'if platform=='iossimulator.arm64'else 'android.x64'
  need(build.get('configuration')=='Release'and build.get('target')==expected_target,'matching build Release/mobile ABI differs')
 else:pending.append('actual matching build receipt contents missing')
 if platform=='android.x86_64':android_binding(root,run,a,m,need)
 return {'mobileVerified':not pending,'platform':platform,'pending':pending,'nativeEntryProof':False}

def android_binding(root,run,a,m,need):
 # These original Android receipts are SHA-bound by mobile_gate above. Read
 # their content rather than accepting the aggregate executionVerified flag.
 required=('request.json','instrumentation.log','instrumentation.log.process.json','managed-result.json','pid-query.txt','layout.json','postinstall-author.json','installed-before.sha256sum.log','installed-after.sha256sum.log','maps.log','native-path-query.txt')
 if any(not(root/n).is_file()or n not in run['rawHashes']for n in required):
  need(False,'Android original ownership/source/inventory receipts missing');return
 request=load(root/'request.json');process=load(root/'instrumentation.log.process.json');managed=load(root/'managed-result.json');layout=load(root/'layout.json');build=load(root/run['buildReceiptRawPath'])
 command=request.get('command',[]);nonce=a['nonce'];pid=a['processId']
 need(request.get('nonce')==nonce and request.get('scenario')=='all'and request.get('sourceCommit')==run['runtimeCommit']and request.get('tree')==run['runtimeTree'],'Android original owned request/source differs')
 need(process.get('command')==command and process.get('exitCode')==0 and process.get('timedOut')is False and process.get('logSha256')==sha(root/'instrumentation.log'),'Android actual process/deadline/raw completion differs')
 need('-w'in command and 'instrument'in command and command.count(nonce)==1 and command[command.index(nonce)-1]=='env:RUNECLR_BUDGET_NONCE'and request.get('deviceSerial')in command,'Android actual instrument arguments/nonce missing')
 lines=(root/'instrumentation.log').read_text().splitlines()
 need(lines.count('INSTRUMENTATION_RESULT: return-code=0')==1 and lines.count('INSTRUMENTATION_CODE: 0')==1 and len(lines)==2,'Android exact instrumentation completion differs')
 need((root/'pid-query.txt').read_text().strip()=='android.os.Process.myPid='+str(pid),'Android actual Java PID query differs')
 need(managed=={'nonce':nonce,'scenario':'all','exitCode':0,'appPid':pid,'policy':1,'meter':1,'terminal':1,'gc':1,'defaultPolicy':0},'Android original managed capability/owner/completion differs')
 need(request.get('settings')==run.get('settings')=={'InterpMode':0,'RuneCLRInterpretCollectible':0,'ReadyToRun':1,'TieredCompilation':1},'Android original request execution settings differ')
 need(layout.get('success')is True and layout.get('base')==build.get('base')and layout.get('commit')==run['runtimeCommit']and layout.get('tree')==run['runtimeTree']and layout.get('target')=='android.x64'and layout.get('configuration')=='Release','Android actual matching layout source differs')
 need(sha(root/'layout.json')==request.get('layoutSha256')and layout.get('buildReviewSha256')==run.get('buildReceiptSha256')and layout.get('critical7')==build.get('criticalHashes')and len(build.get('criticalHashes',{}))==7,'Android seven critical build/layout identities differ')
 need(build.get('buildExit')==0 and build.get('sourceTrackedClean')is True and build.get('computedGotoBudgetPathCompiled')is True and build.get('featureInterpreter')is True and build.get('featureDynamicCodeCompiled')is True,'Android actual compiled budget source evidence missing')
 need(layout.get('inputFiles')==m['files']and layout.get('inputManifestSha256')==run['inputManifestSha256'],'Android actual composite source DLL bindings differ')
 inventory=run['installedInventory']['before'];files=layout.get('files',[])
 need(len({x['path']for x in files})==len(files),'Android layout duplicated identities')
 for entry in files:
  name=Path(entry['path']).name
  if entry.get('role')=='header':continue # Build inputs, not installed APK assets.
  need(inventory.get(name)==entry['sha256'],'Android installed layout file differs '+name)
  original=m['files'].get('trusted/'+name)
  if original:need(entry.get('inputSha256')==original and entry.get('generatedByCriticalCrossgen2Sha256')==build['criticalHashes']['crossgen2']and entry.get('managedNativeHeader',[0])[0]>0,'Android original trusted IL/composite binding differs '+name)
 for key,name in(('native','libcoreclr.so'),('interpreter','libclrinterpreter.so'),('targetJit','libclrjit.so')):need(inventory.get(name)==build['criticalHashes'][key],'Android installed native critical hash differs '+name)
 for stage in ('before','after'):
  parsed={}
  for line in(root/('installed-'+stage+'.sha256sum.log')).read_text().splitlines():
   match=re.fullmatch(r'([0-9a-f]{64})\s+(.+)',line)
   if not match:need(False,'Android original sha256sum line malformed');continue
   path=match[2];key='plugin/'+Path(path).name if '/plugin/'in path else 'apk/base.apk'if path.endswith('/base.apk')else Path(path).name
   need(key not in parsed,'Android duplicate observed installed hash '+key);parsed[key]=match[1]
  need(parsed==run['installedInventory'][stage],'Android actual device sha256sum/inventory differs '+stage)
 author=load(root/'postinstall-author.json');need(author.get('files')==run['installedInventory']['authorSources']and author.get('apkSha256')==request.get('apkSha256')==inventory.get('apk/base.apk')and author.get('installedUtc','')<author.get('transferStartedUtc','')<=author.get('completedUtc','')<request.get('startedUtc',''),'Android actual postinstall original author IL chronology differs')
 native=(root/'native-path-query.txt').read_text().strip();maps=(root/'maps.log').read_text()
 need(native.endswith('/lib/x86_64/libcoreclr.so')and native in maps and native.replace('libcoreclr.so','libclrinterpreter.so')in maps,'Android actual CoreCLR/interpreter mapped installed paths missing')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--desktop',type=Path);p.add_argument('--mobile-run',type=Path);p.add_argument('--adapter-evidence',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--negative-controls',action='store_true');args=p.parse_args()
 check(bool(args.desktop)!=bool(args.mobile_run),'choose desktop control or actual mobile receipt');out=args.output.resolve();check(not out.exists(),'fresh audit directory required');out.mkdir(parents=True)
 result={'passed':False,'mobileVerified':False,'nativeEntryProof':False,'scope':'offline actual rows/hash review; no process/device actions'}
 try:
  m=inputs(args.inputs)
  if args.desktop:
   owner=load(args.desktop/'process.json');check(owner['exitCode']==0 and owner['timedOut']is False,'actual desktop exit/watchdog')
   for stream in('stdout','stderr'):check(sha(args.desktop/('run.'+stream))==owner[stream+'Sha256'].lower(),'desktop stream SHA '+stream)
   directory=args.desktop/'actual';nonce,pid=owner['nonce'],owner['pid'];argv=owner['arguments'];check(len(argv)==8 and argv[:3]==['exec','--fx-version','12.0.0']and Path(argv[4]).resolve()==(args.inputs/'plugin').resolve()and Path(argv[5]).resolve()==directory.resolve()and argv[6:]==[nonce,'all'],'four actual adapter args');result['platform']='windows.x64'
  else:
   check(args.adapter_evidence is not None,'actual mobile adapter evidence directory required');directory=args.adapter_evidence;owner=load(args.mobile_run);nonce,pid=owner.get('nonce'),owner.get('appPid')
  a,r,metrics,hashes=adapter(directory,nonce,pid);result.update(functionalRowsVerified=True,processId=pid,nonce=nonce,cases=15,contexts=73,inputManifestSha256=sha(args.inputs/'input-manifest.json'),originalSixDllHashes=m['files'],adapterRawHashes=hashes,metrics=metrics,architectureCountsHardcoded=False)
  if args.mobile_run:result.update(mobile_gate(args.mobile_run,directory,a,args.inputs,m))
  else:result['pending']=['No mobile app run receipt; desktop control cannot establish mobile execution']
  if args.negative_controls:
   result['negativeControls']=negative_controls(a,r,nonce,pid)
   for name,file,expected in [('trusted-input-byte-flip',args.inputs/'trusted/MobileHostBudgetProbe.dll',m['files']['trusted/MobileHostBudgetProbe.dll']),('case-receipt-byte-flip',directory/a['cases'][0]['receipt'],a['cases'][0]['receiptSha256'])]:
    altered=bytearray(file.read_bytes());altered[0]^=1;check(hashlib.sha256(altered).hexdigest()!=expected,'actual byte corruption accepted '+name);result['negativeControls'].append({'name':name,'rejected':True,'inMemoryOnly':True})
  result['passed']=True;result['assessorSha256']=sha(__file__)
 except Exception as error:result['error']=str(error);raise
 finally:
  with(out/'results.json').open('x',encoding='utf-8')as f:json.dump(result,f,indent=2);f.write(chr(10))
  print(json.dumps(result,indent=2))
if __name__=='__main__':main()

