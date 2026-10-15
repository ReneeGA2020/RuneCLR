#!/usr/bin/env python3
"""Prepare/run Android session-budget APK with explicit private-source receipts."""
import argparse, hashlib, json, re, shutil, time, traceback
from pathlib import Path

BASE='0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'; COMMIT='1c623a776b4471e641e95e4e3c82959c6cb9590f'; TREE='b54537ff42a066e41a01ea611a21f2e5e49934a1'
BUILD_REVIEW_SHA='acc01bc9d00d8a6272ad4599652796bf63ff3e2a08985274ed506e304b94ea9e'; METADATA_REVIEW_SHA='0c501c54375764559aa1b3e66391b6230399ea78c3d63f80f5f303d0f77acc62'
INPUT_MANIFEST_SCHEMA='runeclr.mobile-host-budget.manifest.v1'
TRUSTED=('trusted/MobileHostBudgetProbe.dll','trusted/RuneCLR.Runtime.dll','trusted/RuneCLR.Packages.dll','trusted/RuneCLR.Abstractions.dll')
AUTHOR=('plugin/HostBudgetProbe.Payload.dll','plugin/HostBudgetProbe.Private.dll')
CASES=('Normal','EndlessTick','StartLoop','CatchResume','BroadCatchResume','SignalFilter','FilterExhaustion','ConstructorLoop','StaticConstructorLoop','FiniteCleanup','InfiniteCleanup','StopLoop','MaliciousMessage','ExplicitCanceled','Recovery')

def sha(path):
 d=hashlib.sha256(); f=Path(path).open('rb')
 for block in iter(lambda:f.read(1024*1024),b''): d.update(block)
 f.close(); return d.hexdigest()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value): Path(path).write_text(json.dumps(value,indent=2)+'\n')
def require(value,message):
 if not value: raise RuntimeError(message)
def inside(path,parent): Path(path).resolve().relative_to(Path(parent).resolve())

def validate_build(args):
 b=args.build.resolve(); review=read(b/'build-review/results.json'); metadata=read(b/'metadata-assessment/results.json'); original=read(b/'original/results.json')
 require(review['success'] and metadata['success'] and original['success'] is False and review['originalAggregateSuccess'] is False and review['buildExit']==0,'Fresh matching build/review receipts incomplete')
 require(review['tree']==metadata['tree']==TREE and review['commit']==metadata['commit']==COMMIT and len(review['criticalHashes'])==7,'Candidate identity/products differ')
 require(sha(b/'build-review/results.json')==BUILD_REVIEW_SHA and sha(b/'metadata-assessment/results.json')==METADATA_REVIEW_SHA,'Review receipt hash differs')
 c=metadata['checks']; require(metadata['corelibStages']==3 and metadata['managedCompilerMirrorStages']==1 and c['policyFamily']==5 and c['meterFamily']==8 and c['terminalFamily']==12 and c['gcFamily']==3,'Required ABI families absent')
 return review,metadata

def validate_layout(path,root):
 l=read(path); require(l.get('schema')=='runeclr.android.session-budget.layout.v1' and l.get('success') is True and l.get('base')==BASE and l.get('commit')==COMMIT and l.get('tree')==TREE and l.get('target')=='android.x64' and l.get('sourceTrackedClean') is True,'Layout is not matching fresh private source')
 require(l.get('buildReviewSha256')==BUILD_REVIEW_SHA and l.get('metadataReviewSha256')==METADATA_REVIEW_SHA and l.get('corelibComponentMetadataUnchanged') is True and l.get('coreCriticalUnchanged') is True and l.get('allElfDependenciesResolved') is True,'Fresh composite/native review gates absent')
 require(l.get('features',{}).get('interpreter') is True and l.get('features',{}).get('dynamicCodeCompiled') is True,'Layout feature evidence absent')
 roles={}
 for row in l['files']:
  p=root/row['path']; inside(p,root); require(p.is_file() and sha(p)==row['sha256'].lower(),'Layout hash mismatch: '+row['path']); require(row['sourceCommit']==COMMIT or row['role']=='ndk-native' or (row.get('reusedSameBase') is True and row.get('sourceBase')==BASE and row['sourceCommit']==l['reusedFrameworkSourceCommit'] and row['role'] in ('framework','os-native','android-java')),'Layout source owner differs'); roles.setdefault(row['role'],[]).append(row['path'])
 for role,name in [('runtime','native/libcoreclr.so'),('interpreter','native/libclrinterpreter.so'),('jit','native/libclrjit.so'),('corelib','managed/System.Private.CoreLib.dll')]: require(name in roles.get(role,[]),'Layout missing '+name)
 return l

def validate_inputs(root):
 m=read(root/'input-manifest.json'); require(m['schema']==INPUT_MANIFEST_SCHEMA and m['expectedContexts']==73,'Unexpected mobile input manifest')
 require(tuple(m['trustedCompositeOnly'])==TRUSTED and tuple(m['authorCollectibleILOnly'])==AUTHOR,'Trusted/author topology changed')
 for name in TRUSTED+AUTHOR:
  p=root/name; inside(p,root); require(p.is_file() and sha(p)==m['files'][name],'Input hash mismatch: '+name)
 require(len(m['sourceHashes'])==30 and all(sha(root/'source'/n)==v for n,v in m['sourceHashes'].items()),'Frozen source30 mismatch')
 e=m['entry']; require(e['assembly']=='MobileHostBudgetProbe' and e['type']=='MobileHostBudgetProbe.Entry' and e['method']=='Run' and e['signature']=='public static int Run(string[] args)' and e['arguments']==['pluginDirectory','freshEvidenceDirectory','ownedNonce32hex','all'],'Fixed public Entry.Run contract missing')
 return m

def prepare(args):
 out=args.output.resolve(); require(not out.exists(),'Output must be fresh'); review,metadata=validate_build(args); layout=validate_layout(args.layout_receipt,args.layout_root.resolve()); inputs=validate_inputs(args.mobile_inputs.resolve()); out.mkdir(parents=True); (out/'trusted').mkdir(); (out/'plugin').mkdir()
 require(layout['critical7']==review['criticalHashes'] and layout['inputFiles']==inputs['files'],'Fresh layout critical/mobile inputs differ')
 for name in TRUSTED: shutil.copy2(args.layout_root/'managed'/Path(name).name,out/'trusted'/Path(name).name)
 for name in AUTHOR: shutil.copy2(args.mobile_inputs/name,out/'plugin'/Path(name).name)
 zip_path=args.mobile_inputs/'mobile-host-budget-inputs.zip'
 if not zip_path.is_file(): zip_path=args.mobile_inputs.parent/'mobile-host-budget-inputs.zip'
 req={'schema':'runeclr.android.session-budget.accept.v1','phase':'prepared-only','base':BASE,'commit':COMMIT,'tree':TREE,'target':'android.x64','configuration':'Release','buildReviewSha256':BUILD_REVIEW_SHA,'metadataReviewSha256':METADATA_REVIEW_SHA,'layoutReceiptSha256':sha(args.layout_receipt),'layoutFileCount':len(layout['files']),'mobileInputManifestSha256':sha(args.mobile_inputs/'input-manifest.json'),'mobileInputZipSha256':sha(zip_path),'sourceProofSha256':sha(args.build/'original/source-proof.json'),'trustedCompositeOnly':list(TRUSTED),'authorCollectibleILOnly':list(AUTHOR),'entry':inputs['entry'],'cases':list(CASES),'expectedContexts':73,'productCriticalHashes':review['criticalHashes'],'corelibChecks':metadata['checks'],'apkBuild':{'requiresMatchingCoreLibNativeInterpreterJit':True,'requiresAndroidX64':True,'requiresFreshPostInstallAuthorIL':True,'requiresJavaPidQuery':True,'requiresNativePolicyAck':True,'requiresInterpreterMode0':True,'requiresReadyToRun1':True,'requiresNoGlobalDiagnostic':True},'deviceRun':{'requiredArgs':inputs['entry']['arguments'],'adbOwnedSerialRequired':True,'entryProofCollected':False,'executionVerified':False}}
 write(out/'request.json',req); write(out/'prepared.json',{'success':True,'state':'prepared-only','apkBuilt':False,'installed':False,'executionVerified':False,'frameworkComplete':True,'trustedAreFreshR2RComponents':True,'trustedHashes':{p.name:sha(p) for p in (out/'trusted').glob('*.dll')},'authorHashes':{p.name:sha(p) for p in (out/'plugin').glob('*.dll')},'originalInputHashes':inputs['files'],'requestSha256':sha(out/'request.json')}); return 0

def run(args):
 require(args.build_slot_granted and re.fullmatch(r'[A-Za-z0-9._:-]+',args.serial),'Explicit heavy-slot grant and owned emulator serial required'); req=read(args.output/'request.json'); prepared=read(args.output/'prepared.json'); require(prepared['success'] and not prepared['installed'],'Prepared state changed')
 rid=hashlib.sha256((req['mobileInputZipSha256']+str(time.time_ns())).encode()).hexdigest()[:32]; run=args.output/('run-'+rid); run.mkdir(); write(run/'request.json',{'platform':'android','abi':'x86_64','serial':args.serial,'runId':rid,'lane':'all','entry':req['entry'],'settings':{'InterpMode':0,'RuneCLRInterpretCollectible':0,'ReadyToRun':1,'TieredCompilation':1,'JitDisasmSummary':1,'InterpList':1,'InterpDump':'*:*'},'command':args.command or 'operator-supplied APK launch','executionVerified':False}); write(run/'results.json',{'success':False,'started':True,'appPid':None,'nativeManagedExitZero':False,'functionalPassed':False,'executionVerified':False,'scope':'Receipt initialized; APK build/install/Entry.Run and raw logs are operator phases'}); return 0

def main():
 p=argparse.ArgumentParser(); s=p.add_subparsers(dest='phase',required=True); q=s.add_parser('prepare'); q.add_argument('--build',type=Path,required=True); q.add_argument('--layout-receipt',type=Path,required=True); q.add_argument('--layout-root',type=Path,required=True); q.add_argument('--mobile-inputs',type=Path,required=True); q.add_argument('--output',type=Path,required=True); r=s.add_parser('run'); r.add_argument('--output',type=Path,required=True); r.add_argument('--serial',required=True); r.add_argument('--build-slot-granted',action='store_true'); r.add_argument('--command'); a=p.parse_args()
 try: return prepare(a) if a.phase=='prepare' else run(a)
 except Exception:
  if getattr(a,'output',None) and a.output.exists(): write(a.output/('failure-'+str(time.time_ns())+'.json'),{'error':traceback.format_exc(),'executionVerified':False})
  raise
if __name__=='__main__': raise SystemExit(main())
