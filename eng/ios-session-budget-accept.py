#!/usr/bin/env python3
import argparse,hashlib,json,os,plistlib,re,shutil,struct,subprocess,time,uuid
from pathlib import Path
BASE='0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
def sha(p):
 h=hashlib.sha256();
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
def cap(c):return subprocess.check_output([str(x) for x in c],text=True).strip()
def run(c,log=None,env=None,timeout=900,check=True):
 if log is None:return subprocess.run([str(x) for x in c],env=env,timeout=timeout,check=check).returncode
 with Path(log).open('w') as f:q=subprocess.run([str(x) for x in c],stdout=f,stderr=subprocess.STDOUT,env=env,timeout=timeout,check=False)
 if check and q.returncode:raise RuntimeError(f'command failed {q.returncode}: {log}')
 return q.returncode
def tree(root):return {str(p.relative_to(root)).replace('\\','/'):sha(p) for p in sorted(Path(root).rglob('*')) if p.is_file()}
def il_layout(path):
 b=Path(path).read_bytes();pe=struct.unpack_from('<I',b,0x3c)[0];opt=pe+24;dirs=opt+(112 if struct.unpack_from('<H',b,opt)[0]==0x20b else 96);cli=struct.unpack_from('<I',b,dirs+112)[0]
 for i in range(struct.unpack_from('<H',b,pe+6)[0]):
  s=opt+struct.unpack_from('<H',b,pe+20)[0]+i*40;size,rva,rawsize,raw=struct.unpack_from('<IIII',b,s+8)
  if rva<=cli<rva+max(size,rawsize):
   h=raw+cli-rva;return {'ilOnly':bool(struct.unpack_from('<I',b,h+16)[0]&1),'managedNativeRva':struct.unpack_from('<I',b,h+64)[0]}
 raise RuntimeError('managed header missing '+str(path))
def inputs(root):
 m=json.loads((root/'input-manifest.json').read_text())
 for n,d in m['files'].items():
  if not (root/n).is_file() or sha(root/n).lower()!=d.lower():raise RuntimeError('input hash mismatch '+n)
 return m
def compile_wrapper(a,out,app):
 w=a.wrapper_source.read_text();anchor='    char **managed_argv;'
 if w.count(anchor)!=1:raise RuntimeError('unknown wrapper initialization anchor')
 w=re.sub(r'^.*(?:un)?setenv\s*\(\s*"(?:DOTNET|COMPlus)_(?:Interp[A-Za-z]*|RuneCLRInterpretCollectible|ReadyToRun)"[^\n]*\n','',w,flags=re.M)
 w=re.sub(r'^.*printf\("SESSION_NATIVE_CONFIG[^\n]*\n','',w,flags=re.M)
 settings='    setenv("DOTNET_InterpMode", "0", 1);\n    setenv("DOTNET_RuneCLRInterpretCollectible", "0", 1);\n    setenv("DOTNET_ReadyToRun", "1", 1);\n    setenv("DOTNET_InterpList", "0", 1);\n    unsetenv("DOTNET_InterpDump");\n    setenv("RUNECLR_DOCUMENTS", [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES)[0] UTF8String], 1);\n    printf("MOBILE_BUDGET_NATIVE pid=%d nonce=%s InterpMode=0 RuneCLRInterpretCollectible=0 ReadyToRun=1\\n", getpid(), getenv("RUNECLR_BUDGET_NONCE")); fflush(stdout);\n'
 w=w.replace(anchor,settings+anchor);(out/'runtime.m').write_text(w)
 run(['xcrun','--sdk','iphonesimulator','clang','-target','arm64-apple-ios15.3-simulator','-fobjc-arc','-DINVARIANT_GLOBALIZATION=1','-I'+str(a.wrapper_source.parent),str(a.wrapper_source.parent/'main.m'),out/'runtime.m','-L'+str(app),'-lcoreclr','-framework','UIKit','-framework','Foundation','-Wl,-rpath,@executable_path','-o',app/'Session'],out/'logs/wrapper-build.log')
def sign_app(out,app):
 p=plistlib.loads((app/'Info.plist').read_bytes());bid='org.runeclr.hostbudget.'+uuid.uuid4().hex[:12];p.update(CFBundleExecutable='Session',CFBundleName='Session',CFBundleIdentifier=bid);(app/'Info.plist').write_bytes(plistlib.dumps(p))
 for p in app.glob('*.dylib'):run(['codesign','--force','--sign','-',p],out/'logs'/(p.name+'.sign.log'))
 run(['codesign','--force','--sign','-',app],out/'logs/app-sign.log')
 return bid
def build(a):
 out=a.output.resolve();out.mkdir(exist_ok=False);(out/'logs').mkdir();shutil.copy2(__file__,out/'driver.py');m=inputs(a.inputs);rt=a.runtime.resolve();commit=cap(['git','-C',rt,'rev-parse','HEAD']);treeid=cap(['git','-C',rt,'rev-parse','HEAD^{tree}'])
 if cap(['git','-C',rt,'status','--porcelain','--untracked-files=no']):raise RuntimeError('candidate source dirty')
 rec=json.loads(a.build_receipt.read_text())
 if not rec.get('success') or rec.get('base')!=BASE or rec.get('commit')!=commit or rec.get('tree')!=treeid or rec.get('configuration')!='Release' or rec.get('target') not in ('iossimulator','iossimulator.arm64','iossimulator.arm64.Release'):raise RuntimeError('build receipt identity mismatch')
 for p,k in ((a.native,'nativeSha256'),(a.corelib,'corelibSha256'),(a.compiler,'crossgen2Sha256')):
  if sha(p)!=rec[k]:raise RuntimeError('critical artifact hash mismatch '+k)
 app=out/'app/Session.app';shutil.copytree(a.baseline_app,app)
 # Baseline is a native/wrapper template only: replace every trusted managed
 # input with bytes bound by the current manifest; never silently retain an
 # older RuneCLR or adapter assembly from the template.
 baseline_bundle_hashes=tree(app)
 trusted_names=['RuneCLR.Abstractions.dll','RuneCLR.Packages.dll','RuneCLR.Runtime.dll','MobileHostBudgetProbe.dll']
 trusted_before={name:baseline_bundle_hashes.get(name) for name in trusted_names}
 # Remove prior harness/components and bundled old fixtures.  Framework-only
 # IL is regenerated below with current CoreLib and current trusted inputs.
 for path in sorted(app.glob('*.dll')):
  if path.name.startswith(('RuneCLR.','SelectionProbe.','SessionBridge','HarnessBridge','HostBudgetProbe.','MobileHostBudgetProbe')):path.unlink()
 for path in sorted(app.iterdir()):
  if path.is_dir() and path.name!='_CodeSignature':shutil.rmtree(path)
 for name in trusted_names:
  shutil.copy2(a.inputs/'trusted'/name,app/name)
 trusted_after={n:sha(app/n) for n in trusted_names}
 mismatches={n:{'actual':trusted_after[n].lower(),'expected':str(m['files'].get('trusted/'+n,'')).lower()} for n in trusted_names if trusted_after[n].lower()!=str(m['files'].get('trusted/'+n,'')).lower()}
 if mismatches:
  raise RuntimeError('trusted managed bundle replacement hash mismatch '+json.dumps(mismatches,sort_keys=True))
 shutil.copy2(a.native,app/'libcoreclr.dylib')
 tr=a.inputs/'trusted';names=['RuneCLR.Abstractions.dll','RuneCLR.Packages.dll','RuneCLR.Runtime.dll','MobileHostBudgetProbe.dll'];dlls=[tr/n for n in names]
 if any(not p.is_file() for p in dlls):raise RuntimeError('missing trusted adapter dll')
 bridge=out/'SessionBridge.cs';bridge.write_text('using System;using MobileHostBudgetProbe;public static class SessionBridge{public static int Main(string[] a){var d=Environment.GetEnvironmentVariable("RUNECLR_DOCUMENTS")??throw new InvalidOperationException("documents missing");var n=Environment.GetEnvironmentVariable("RUNECLR_BUDGET_NONCE")??throw new InvalidOperationException("nonce missing");return Entry.Run(new[]{d+"/budget-plugin",d+"/budget-evidence-"+n,n,"all"});}}\n')
 sdk=rt/'.dotnet/dotnet';ver=cap([sdk,'--version']);csc=rt/'.dotnet/sdk'/ver/'Roslyn/bincore/csc.dll';bridge_dll=out/'SessionBridge.dll'
 facade_refs=[p for p in sorted((a.wrapper_source.parent/'input').glob('*.dll')) if not p.name.startswith(('RuneCLR.','SelectionProbe.','SessionBridge','HarnessBridge')) and p.name!='System.Private.CoreLib.dll']
 run([sdk,csc,'-nologo','-noconfig','-nostdlib+','-optimize+','-target:exe','-out:'+str(bridge_dll),'-r:'+str(a.corelib),*['-r:'+str(p) for p in facade_refs+dlls],str(bridge)],out/'logs/bridge-build.log')
 # Reuse only unchanged framework IL from the already verified matching-base
 # input set.  The baseline app contains generated R2R components, so it is
 # not itself an IL source for rebuilding the new composite.
 framework_input=a.wrapper_source.parent/'input'
 if not framework_input.is_dir():raise RuntimeError('baseline original framework IL input directory missing')
 fresh_input=out/'input';fresh_input.mkdir()
 reused_framework={}
 for p in sorted(framework_input.glob('*.dll')):
  if p.name.startswith(('RuneCLR.','SelectionProbe.','SessionBridge','HarnessBridge')) or p.name=='System.Private.CoreLib.dll':continue
  shutil.copy2(p,fresh_input/p.name);reused_framework[p.name]=sha(p)
 for p in dlls:shutil.copy2(p,fresh_input/p.name)
 shutil.copy2(a.corelib,fresh_input/'System.Private.CoreLib.dll');shutil.copy2(bridge_dll,fresh_input/bridge_dll.name)
 composite=sorted(fresh_input.glob('*.dll'));rsp=out/'crossgen.rsp';opts=['--targetos:iossimulator','--targetarch:arm64','--obj-format:macho','--composite','--inputbubble','--parallelism:2','--resilient','--optimize','--out:'+str(app/'framework.dylib')];rsp.write_text('\n'.join(opts+[str(p) for p in composite])+'\n');run([a.compiler,'@'+str(rsp)],out/'logs/crossgen.log')
 obj=out/'framework.o';shutil.copy2(app/'framework.dylib',obj)
 run(['xcrun','--sdk','iphonesimulator','clang','-target','arm64-apple-ios15.3-simulator','-dynamiclib',obj,'-Wl,-install_name,@rpath/framework.dylib','-o',app/'framework.dylib'],out/'logs/composite-link.log')
 if any(app.rglob('HostBudgetProbe.Payload.dll')) or any(app.rglob('HostBudgetProbe.Private.dll')):raise RuntimeError('author IL entered preinstall app bundle')
 write(out/'framework-reuse.json',{'source':str(framework_input),'inputHashes':reused_framework,'currentTrustedInputHashes':trusted_after,'compositeInputs':{p.name:sha(p) for p in composite},'authorBundled':False})
 compile_wrapper(a,out,app)
 bid=sign_app(out,app)
 layouts={p.name:il_layout(p) for p in app.glob('*.dll')}
 required=(*trusted_names,'System.Private.CoreLib.dll','SessionBridge.dll')
 if any(not layouts[n]['managedNativeRva'] for n in required):raise RuntimeError('trusted component lacks R2R header')
 if tree(a.baseline_app)!=baseline_bundle_hashes:raise RuntimeError('baseline app mutated')
 if inputs(a.inputs)!=m:raise RuntimeError('mobile inputs mutated')
 for n,h in reused_framework.items():
  if sha(framework_input/n)!=h:raise RuntimeError('framework IL input mutated '+n)
 write(out/'state.json',{'app':str(app),'bundleId':bid,'runtimeCommit':commit,'runtimeTree':treeid,'buildReceiptSha256':sha(a.build_receipt),'nativeSha256':sha(a.native),'corelibSha256':sha(a.corelib),'compilerSha256':sha(a.compiler),'inputManifestSha256':sha(a.inputs/'input-manifest.json'),'inputFiles':m['files'],'baselineBundleHashes':baseline_bundle_hashes,'trustedBundleHashesBefore':trusted_before,'trustedInputHashes':trusted_after,'trustedFinalBundleHashes':{n:sha(app/n) for n in trusted_names},'bundleHashes':tree(app),'layouts':layouts,'wrapperSourceSha256':sha(out/'runtime.m'),'frameworkReuseSha256':sha(out/'framework-reuse.json'),'trustedBundleHashesBound':{n:m['files']['trusted/'+n] for n in trusted_names},'mode':0,'diagnostic':0,'readyToRun':1,'executionVerified':False});shutil.copy2(a.build_receipt,out/'matching-build.json');shutil.copy2(a.inputs/'input-manifest.json',out/'input-manifest.json');print('BUILD PASS',app)
def repair(a):
 out=a.output.resolve();out.mkdir(exist_ok=False);(out/'logs').mkdir();m=inputs(a.inputs);rt=a.runtime.resolve();rec=json.loads(a.build_receipt.read_text());commit=cap(['git','-C',rt,'rev-parse','HEAD']);treeid=cap(['git','-C',rt,'rev-parse','HEAD^{tree}'])
 if not rec.get('success') or rec.get('base')!=BASE or rec.get('commit')!=commit or rec.get('tree')!=treeid or rec.get('configuration')!='Release' or rec.get('target') not in ('iossimulator','iossimulator.arm64','iossimulator.arm64.Release'):raise RuntimeError('matching build identity mismatch')
 if cap(['git','-C',rt,'status','--porcelain','--untracked-files=no']):raise RuntimeError('candidate source dirty')
 for p,k in ((a.native,'nativeSha256'),(a.corelib,'corelibSha256'),(a.compiler,'crossgen2Sha256')):
  if sha(p)!=rec[k]:raise RuntimeError('critical artifact changed '+k)
 old=tree(a.reuse_build);app=out/'app/Session.app';shutil.copytree(a.reuse_build/'app/Session.app',app);shutil.copytree(a.reuse_build/'input',out/'input')
 for n in ('SessionBridge.cs','SessionBridge.dll','crossgen.rsp','framework.o'):shutil.copy2(a.reuse_build/n,out/n)
 shutil.copy2(__file__,out/'driver.py');shutil.copy2(a.build_receipt,out/'matching-build.json');shutil.copy2(a.inputs/'input-manifest.json',out/'input-manifest.json')
 reused=json.loads((a.reuse_build/'framework-reuse.json').read_text());shutil.copy2(a.reuse_build/'framework-reuse.json',out/'framework-reuse.json')
 for n,h in reused['inputHashes'].items():
  if sha(a.wrapper_source.parent/'input'/n)!=h:raise RuntimeError('reused framework changed '+n)
 trusted=('RuneCLR.Abstractions.dll','RuneCLR.Packages.dll','RuneCLR.Runtime.dll','MobileHostBudgetProbe.dll','SessionBridge.dll','System.Private.CoreLib.dll');layouts={n:il_layout(app/n) for n in trusted}
 if any(not x['managedNativeRva'] for x in layouts.values()):raise RuntimeError('trusted component lacks R2R header')
 if any(app.rglob('HostBudgetProbe.Payload.dll')) or any(app.rglob('HostBudgetProbe.Private.dll')):raise RuntimeError('author IL bundled')
 compile_wrapper(a,out,app)
 bid=sign_app(out,app)
 if tree(a.reuse_build)!=old:raise RuntimeError('reused failed build mutated')
 write(out/'reuse-build.json',{'source':str(a.reuse_build),'sourceFileHashes':old,'reusedCompositeSha256':sha(a.reuse_build/'app/Session.app/framework.dylib'),'newWrapper':True,'freshSigning':True})
 write(out/'state.json',{'app':str(app),'bundleId':bid,'runtimeCommit':commit,'runtimeTree':treeid,'buildReceiptSha256':sha(a.build_receipt),'nativeSha256':sha(a.native),'corelibSha256':sha(a.corelib),'compilerSha256':sha(a.compiler),'inputManifestSha256':sha(a.inputs/'input-manifest.json'),'inputFiles':m['files'],'mode':0,'diagnostic':0,'readyToRun':1,'bundleHashes':tree(app),'layouts':layouts,'wrapperSourceSha256':sha(out/'runtime.m'),'frameworkReuseSha256':sha(out/'framework-reuse.json'),'trustedCompositeInputs':reused['compositeInputs'],'executionVerified':False});print('REPAIR BUILD PASS',app)
def install(a):
 s=json.loads((a.output/'state.json').read_text());sim=cap(['xcrun','simctl','create','RuneCLR-HostBudget',a.device_type,a.sim_runtime]);run(['xcrun','simctl','boot',sim],a.output/'logs/boot.log');run(['xcrun','simctl','bootstatus',sim,'-b'],a.output/'logs/bootstatus.log');run(['xcrun','simctl','install',sim,s['app']],a.output/'logs/install.log');data=cap(['xcrun','simctl','get_app_container',sim,s['bundleId'],'data']);s.update(simulator=sim,dataContainer=data,installedUtc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()));write(a.output/'state.json',s);print('INSTALL PASS',sim)
def transfer(a):
 s=json.loads((a.output/'state.json').read_text());d=Path(s['dataContainer'])/'Documents'/'budget-plugin';
 if d.exists():raise RuntimeError('existing plugin destination')
 d.mkdir(parents=True);[shutil.copy2(a.inputs/'plugin'/n,d/n) for n in ('HostBudgetProbe.Payload.dll','HostBudgetProbe.Private.dll')];s['pluginHashes']=tree(d);write(a.output/'state.json',s);print('TRANSFER PASS')
def execute(a):
 s=json.loads((a.output/'state.json').read_text());n=uuid.uuid4().hex;e=a.output/'run-all';e.mkdir();env=dict(os.environ);env.update({'SIMCTL_CHILD_RUNECLR_BUDGET_NONCE':n,'SIMCTL_CHILD_DOTNET_InterpMode':'0','SIMCTL_CHILD_DOTNET_RuneCLRInterpretCollectible':'0','SIMCTL_CHILD_DOTNET_ReadyToRun':'1'});write(e/'request.json',{'nonce':n,'simulator':s['simulator'],'bundleId':s['bundleId'],'mode':0,'diagnostic':0,'readyToRun':1,'debugger':False});status=run(['xcrun','simctl','launch','--console','--terminate-running-process',s['simulator'],s['bundleId']],e/'launch.log',env=env,timeout=a.timeout,check=False);d=Path(s['dataContainer'])/'Documents'/('budget-evidence-'+n);d.exists() and shutil.copytree(d,e/'adapter-evidence');adapter=e/'adapter-evidence/result.json';aresult=json.loads(adapter.read_text()) if adapter.is_file() else {};valid=status==0 and aresult.get('passed') is True and aresult.get('nonce')==n and aresult.get('contexts')==73 and len(aresult.get('cases',[]))==15;r={'passed':valid,'simctlExit':status,'nonce':n,'adapterEvidencePresent':adapter.is_file(),'adapterContexts':aresult.get('contexts'),'adapterCases':len(aresult.get('cases',[])),'executionVerified':False,'nativeEntryProof':False,'rawHashes':{p.name:sha(p) for p in e.iterdir() if p.is_file()}};write(e/'results.json',r);print(json.dumps(r,indent=2));
 if not r['passed']:raise RuntimeError('iOS budget acceptance failed; preserve this attempt')
def cleanup(a):
 s=json.loads((a.output/'state.json').read_text());q=run(['xcrun','simctl','shutdown',s['simulator']],a.output/'logs/shutdown.log',check=False);write(a.output/'cleanup.json',{'simulator':s['simulator'],'exit':q})
def main():
 p=argparse.ArgumentParser();p.add_argument('phase',choices=('build','repair','install','transfer','run','cleanup'));p.add_argument('--output',type=Path,required=True);p.add_argument('--reuse-build',type=Path);p.add_argument('--inputs',type=Path);p.add_argument('--runtime',type=Path);p.add_argument('--native',type=Path);p.add_argument('--corelib',type=Path);p.add_argument('--compiler',type=Path);p.add_argument('--build-receipt',type=Path);p.add_argument('--baseline-app',type=Path);p.add_argument('--wrapper-source',type=Path);p.add_argument('--device-type',default='com.apple.CoreSimulator.SimDeviceType.iPhone-16');p.add_argument('--sim-runtime',default='com.apple.CoreSimulator.SimRuntime.iOS-27-0');p.add_argument('--timeout',type=int,default=900);a=p.parse_args()
 if a.phase in ('build','repair'):
  for n in ('inputs','runtime','native','corelib','compiler','build_receipt','baseline_app','wrapper_source'):
   if getattr(a,n) is None:p.error('--'+n.replace('_','-')+' required for build')
  if a.phase=='repair':
   if a.reuse_build is None:p.error('--reuse-build required for repair')
   repair(a)
  else:build(a)
 elif a.phase=='install':install(a)
 elif a.phase=='transfer':transfer(a)
 elif a.phase=='run':execute(a)
 else:cleanup(a)
if __name__=='__main__':main()

