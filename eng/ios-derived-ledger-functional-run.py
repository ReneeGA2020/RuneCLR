#!/usr/bin/env python3
"""One fresh non-debugger derived-ledger iOS budget run against an already installed owned app."""
import argparse,hashlib,json,os,re,shutil,subprocess,time,uuid
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def tree(root):return {p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
def write(p,v):p.write_text(json.dumps(v,indent=2)+chr(10))
def utc():return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def command(c,log,timeout,env=None):
 with log.open('w') as f:q=subprocess.run(c,stdout=f,stderr=subprocess.STDOUT,timeout=timeout,env=env)
 return q.returncode

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--player',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=int,default=900);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False);(out/'logs').mkdir();shutil.copy2(__file__,out/'controller.py')
 s=json.loads((a.player/'state.json').read_text());manifest=json.loads((a.inputs/'input-manifest.json').read_text());original=tree(a.player);nonce=uuid.uuid4().hex;sim=s['simulator'];result={'passed':False,'nonce':nonce,'startedUtc':utc(),'nativeEntryProof':False,'debugger':False,'launchCount':0};booted=False
 write(out/'request.json',{'player':str(a.player),'stateSha256':sha(a.player/'state.json'),'inputManifestSha256':sha(a.inputs/'input-manifest.json'),'nonce':nonce,'simulator':sim,'bundleId':s['bundleId'],'timeoutSeconds':a.timeout,'mode':0,'diagnostic':0,'readyToRun':1,'debugger':False,'derivedLedger':1,'phaseAcquireLoad':1,'controllerSha256':sha(__file__)})
 try:
  if s.get('runtimeCommit')!='2d86588f8cef4b3c48ce2ba4d4af15ad7bc83e7c' or s.get('runtimeTree')!='3292fc9acf3c15632f3bde34f675caec44f399e2' or s.get('phaseAcquireLoad')!=1 or s.get('derivedLedger')!=1:raise RuntimeError('exact candidate/settings missing')
  if sha(a.player/'derived-bindings.json')!=s.get('derivedBindingsSha256'):raise RuntimeError('derived app bindings changed')
  shutil.copy2(a.player/'derived-bindings.json',out/'derived-bindings.json')
  for relative,h in manifest['files'].items():
   if sha(a.inputs/relative)!=h:raise RuntimeError('frozen input changed '+relative)
  shutil.copy2(a.player/'matching-build.json',out/'matching-build.json');shutil.copy2(a.player/'state.json',out/'original-state.json');shutil.copy2(a.inputs/'input-manifest.json',out/'input-manifest.json')
  q=command(['xcrun','simctl','boot',sim],out/'logs/boot.log',120)
  if q:raise RuntimeError('owned simulator boot failed; preserve output')
  booted=True
  if command(['xcrun','simctl','bootstatus',sim,'-b'],out/'logs/bootstatus.log',180):raise RuntimeError('owned bootstatus failed')
  installed=Path(subprocess.check_output(['xcrun','simctl','get_app_container',sim,s['bundleId'],'app'],text=True).strip());data=Path(subprocess.check_output(['xcrun','simctl','get_app_container',sim,s['bundleId'],'data'],text=True).strip());plugin=data/'Documents/budget-plugin'
  def inventory():return {'bundle':tree(installed),'author':{'plugin/'+n:h for n,h in tree(plugin).items()}}
  before=inventory();expected={'plugin/'+n:h for n,h in s['pluginHashes'].items()}
  if before['bundle']!=s['bundleHashes'] or before['author']!=expected:raise RuntimeError('actual installed inputs changed before launch')
  write(out/'installed-before.json',before);write(out/'installed-before-observation.json',{'observedUtc':utc(),'appPath':str(installed),'authorPath':str(plugin),'inventorySha256':sha(out/'installed-before.json')})
  destination=data/'Documents'/('budget-evidence-'+nonce)
  if destination.exists():raise RuntimeError('nonce evidence already exists')
  env=dict(os.environ)
  for name in list(env):
   if name.startswith('SIMCTL_CHILD_') and any(x in name for x in ('DOTNET_','COMPlus_','RUNECLR_')):del env[name]
  env.update(SIMCTL_CHILD_RUNECLR_BUDGET_NONCE=nonce,SIMCTL_CHILD_DOTNET_InterpMode='0',SIMCTL_CHILD_DOTNET_RuneCLRInterpretCollectible='0',SIMCTL_CHILD_DOTNET_ReadyToRun='1',SIMCTL_CHILD_DOTNET_RuneCLRPhaseAcquireLoad='1',SIMCTL_CHILD_DOTNET_RuneCLRDerivedLedger='1');cmd=['xcrun','simctl','launch','--console','--terminate-running-process',sim,s['bundleId']];write(out/'launch-request.json',{'command':cmd,'environment':{n:v for n,v in env.items() if n.startswith('SIMCTL_CHILD_')},'startedUtc':utc()});result['launchCount']=1
  status=command(cmd,out/'launch.log',a.timeout,env=env);result['simctlExit']=status;result['timedOut']=False
  after=inventory();write(out/'installed-after.json',after);write(out/'installed-after-observation.json',{'observedUtc':utc(),'appPath':str(installed),'authorPath':str(plugin),'inventorySha256':sha(out/'installed-after.json')})
  if before!=after:raise RuntimeError('installed identity changed after launch')
  if destination.is_dir():shutil.copytree(destination,out/'adapter-evidence')
  adapter=json.loads((out/'adapter-evidence/result.json').read_text());pid=adapter['processId'];log=(out/'launch.log').read_text();header=f'MOBILE_BUDGET_NATIVE pid={pid} nonce={nonce} InterpMode=0 RuneCLRInterpretCollectible=0 ReadyToRun=1';complete=f'MOBILE_HOST_BUDGET_COMPLETE nonce={nonce} scenario=all pid={pid} cases=15 contexts=73 passed=true'
  if status!=0 or adapter.get('passed')is not True or adapter['nonce']!=nonce or adapter['contexts']!=73 or len(adapter['cases'])!=15:raise RuntimeError('actual adapter completion differs')
  if len(re.findall(re.escape(header)+'$',log,re.M))!=1 or len(re.findall(re.escape(complete)+'$',log,re.M))!=1 or not re.search(r'^CORECLR_INITIALIZE_HRESULT=0x0$',log,re.M) or not re.search(r'^CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0$',log,re.M):raise RuntimeError('native/managed PID nonce exact exit markers differ')
  derived_header=f'DERIVED_LEDGER_NATIVE pid={pid} nonce={nonce} PhaseAcquireLoad=1 DerivedLedger=1'
  if len(re.findall(re.escape(derived_header)+'$',log,re.M))!=1:raise RuntimeError('actual derived native settings header differs')
  count=0
  for c in adapter['cases']:
   f=out/'adapter-evidence'/c['receipt'];r=json.loads(f.read_text())
   if sha(f)!=c['receiptSha256'] or not r['passed'] or r['nonce']!=c['nonce']:raise RuntimeError('actual child receipt differs '+c['scenario'])
   count+=len(r['rows'])
  if count!=73:raise RuntimeError('actual child count differs')
  if tree(a.player)!=original:raise RuntimeError('frozen prior player/output changed')
  result.update(passed=True,platform='iossimulator.arm64',appPid=pid,contexts=73,cases=15,independentNormalLane=True)
  transport={'schema':'runeclr.ios-budget.transport.v2','platform':'iossimulator.arm64','appPid':pid,'nonce':nonce,'timedOut':False,'debugger':False,'simctlExit':status,'inputManifestSha256':sha(a.inputs/'input-manifest.json'),'inputFiles':manifest['files'],'runtimeCommit':s['runtimeCommit'],'runtimeTree':s['runtimeTree'],'nativeLog':'launch.log','buildReceiptRawPath':'matching-build.json','buildReceiptSha256':sha(out/'matching-build.json'),'installedInventory':{'before':before,'after':after,'beforeRawPath':'installed-before.json','afterRawPath':'installed-after.json','authorSources':expected},'bundleUnchanged':True,'rawHashes':tree(out),'nativeEntryProof':False,'launchCount':1,'derivedLedger':1,'phaseAcquireLoad':1};write(out/'transport-receipt.json',transport)
 except subprocess.TimeoutExpired as e:
  result.update(timedOut=True,error=str(e));raise
 except Exception as e:
  result['error']=str(e);raise
 finally:
  if booted:
   q=command(['xcrun','simctl','shutdown',sim],out/'logs/shutdown.log',120);write(out/'cleanup.json',{'simulator':sim,'exit':q,'observedUtc':utc()})
  result['endedUtc']=utc();write(out/'results.json',result);print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
