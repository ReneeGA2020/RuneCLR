#!/usr/bin/env python3
"""Owned Android budget executable bridge, fresh APK and functional acceptance.

bridge runs on the private Mac build host; build/install/run/cleanup run on the
Windows operator. Author DLLs are copied only after installation. No entry
observer or device-security claim is made.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import traceback
import uuid
import zipfile

BASE='0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
COMMIT='1c623a776b4471e641e95e4e3c82959c6cb9590f'
TREE='b54537ff42a066e41a01ea611a21f2e5e49934a1'
BRIDGE_NAME='RuneCLR.AndroidBudgetBridge.dll'
SANITIZE=('CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','LIBRARY_PATH','SDKROOT','MACOSX_DEPLOYMENT_TARGET')
BRIDGE=r'''
using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using System.Text.Json;
static class AndroidBudgetBridge {
 static int Version(Type owner,string name) {
  MethodInfo? method=owner.GetMethod(name,BindingFlags.NonPublic|BindingFlags.Static,null,Type.EmptyTypes,null);
  if(method?.ReturnType!=typeof(int))throw new PlatformNotSupportedException("Trusted budget version missing");
  int value=method.CreateDelegate<Func<int>>()();
  if(value!=1)throw new PlatformNotSupportedException("Trusted budget native version differs");
  return value;
 }
 public static int Main(string[] ignored) {
  string root=AppContext.BaseDirectory;
  string nonce=Environment.GetEnvironmentVariable("RUNECLR_BUDGET_NONCE")??throw new InvalidOperationException("No nonce");
  string scenario=Environment.GetEnvironmentVariable("RUNECLR_BUDGET_SCENARIO")??"all";
  if(nonce.Length!=32)throw new InvalidOperationException("Invalid nonce");
  string prefix=Path.Combine(root,"budget-"+nonce), evidence=Path.Combine(root,"budget-evidence-"+nonce);
  TextWriter originalOut=Console.Out, originalError=Console.Error;
  int code=1,policy=-1,meter=-1,terminal=-1,gc=-1,defaultPolicy=-1;
  using(var writer=new StreamWriter(prefix+".managed.log"){AutoFlush=true}) {
   Console.SetOut(writer);Console.SetError(writer);
   try {
    policy=Version(typeof(AssemblyLoadContext),"RuneCLR_GetExecutionPolicyVersion");
    meter=Version(typeof(AssemblyLoadContext),"RuneCLR_GetInstructionMeterVersion");
    terminal=Version(typeof(AssemblyLoadContext),"RuneCLR_GetTerminalPrototypeVersion");
    gc=Version(typeof(GC),"RuneCLR_GetTerminalFinalizerBoundaryVersion");
    var query=typeof(AssemblyLoadContext).GetMethod("RuneCLR_GetExecutionPolicy",BindingFlags.NonPublic|BindingFlags.Instance,null,Type.EmptyTypes,null);
    if(query?.ReturnType!=typeof(int))throw new PlatformNotSupportedException("Native default policy query missing");
    defaultPolicy=query.CreateDelegate<Func<AssemblyLoadContext,int>>()(AssemblyLoadContext.Default);
    if(defaultPolicy!=0)throw new PlatformNotSupportedException("Trusted default policy differs");
    Console.WriteLine($"ANDROID_BUDGET_POLICY policy={policy} meter={meter} terminal={terminal} gc={gc} default={defaultPolicy}");
    Console.WriteLine($"ANDROID_BUDGET_MANAGED pid={Environment.ProcessId} nonce={nonce} arch={RuntimeInformation.ProcessArchitecture}");
    code=MobileHostBudgetProbe.Entry.Run([Path.Combine(root,"plugin"),evidence,nonce,scenario]);
   } catch(Exception error) {
    // Do not invoke an author exception's Message or ToString virtual property.
    code=1;Console.Error.WriteLine("ANDROID_BUDGET_BRIDGE_FAILURE type="+error.GetType().FullName);
   } finally {Console.SetOut(originalOut);Console.SetError(originalError);}
  }
  // Forward the actual completed managed stream unchanged into native stdout.
  // This preserves the adapter's original marker, not a derived scalar summary.
  originalOut.Write(File.ReadAllText(prefix+".managed.log"));originalOut.Flush();
  File.WriteAllText(prefix+".maps.log",File.ReadAllText("/proc/self/maps"));
  File.WriteAllText(prefix+".managed-result.json",JsonSerializer.Serialize(new {nonce,scenario,exitCode=code,appPid=Environment.ProcessId,policy,meter,terminal,gc,defaultPolicy}));
  return code;
 }
}
'''
NATIVE=r'''
    const char* nonce = getenv("RUNECLR_BUDGET_NONCE");
    if (nonce == NULL || strlen(nonce) != 32 || strspn(nonce,"0123456789abcdef") != 32) return -1;
    char native_path[2048], jit_path[2048];
    snprintf(native_path,sizeof(native_path),"%s/budget-%s.native.log",g_bundle_path,nonce);
    snprintf(jit_path,sizeof(jit_path),"%s/budget-%s.jit.log",g_bundle_path,nonce);
    if (freopen(native_path,"w",stdout)==NULL || dup2(fileno(stdout),fileno(stderr))<0) return -1;
    setvbuf(stdout,NULL,_IONBF,0);setvbuf(stderr,NULL,_IONBF,0);
    setenv("DOTNET_InterpMode","0",1);
    setenv("DOTNET_RuneCLRInterpretCollectible","0",1);
    setenv("DOTNET_ReadyToRun","1",1);
    setenv("DOTNET_TieredCompilation","1",1);
    setenv("DOTNET_InterpList","1",1);
    setenv("DOTNET_InterpDump","*:*",1);
    setenv("DOTNET_JitDisasmSummary","1",1);
    setenv("DOTNET_JitStdOutFile",jit_path,1);
    setenv("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT","1",1);
    unsetenv("DOTNET_RuneCLRInterpreterRefuseMethods");
    printf("MOBILE_BUDGET_NATIVE pid=%d nonce=%s InterpMode=0 RuneCLRInterpretCollectible=0 ReadyToRun=1\n",getpid(),nonce);
'''
JAVA=r'''
        try {
            String nonce = android.system.Os.getenv("RUNECLR_BUDGET_NONCE");
            if (nonce == null || !nonce.matches("[0-9a-f]{32}")) throw new RuntimeException("Missing owned nonce");
            java.io.FileOutputStream stream = new java.io.FileOutputStream(new java.io.File(filesDir,"budget-"+nonce+".pid-query.txt"));
            stream.write(("android.os.Process.myPid="+android.os.Process.myPid()+"\n").getBytes(java.nio.charset.StandardCharsets.UTF_8));stream.close();
        } catch (java.io.IOException error) { throw new RuntimeException(error); }
'''

def require(v,m):
 if not v:raise RuntimeError(m)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,d):Path(p).write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8')
def utc():return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def files(p):return {f.relative_to(p).as_posix():sha(f) for f in sorted(Path(p).rglob('*')) if f.is_file() and '__pycache__' not in str(f)}
def clean_env():
 e=dict(os.environ)
 for n in SANITIZE:e.pop(n,None)
 return e
def command(argv,log,env=None,cwd=None,timeout=900,check=True):
 argv=list(map(str,argv));start=utc()
 with Path(log).open('wb') as f:
  p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,env=env,cwd=cwd)
  timed=False
  try:code=p.wait(timeout=timeout)
  except subprocess.TimeoutExpired:
   timed=True;p.kill();code=p.wait()
 write(str(log)+'.process.json',{'command':argv,'pid':p.pid,'exitCode':code,'timedOut':timed,'startedUtc':start,'endedUtc':utc(),'logSha256':sha(log)})
 if check:require(code==0 and not timed,'Command failed; original raw log preserved: '+str(log))
 return code,timed

def bridge(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);old=a.layout.resolve();original=load(old/'layout.json')
 require(original['success'] and original['commit']==COMMIT and original['tree']==TREE and len(original['files'])==200,'Fresh200 matching layout required')
 require(all(sha(old/r['path'])==r['sha256'] for r in original['files']),'Fresh layout inputs changed')
 base=a.layout.parent;inp=out/'input';shutil.copytree(base/'input',inp)
 source=a.runtime.resolve();sdk=source/'.dotnet/dotnet';require(subprocess.check_output([str(sdk),'--version'],text=True).strip()=='11.0.100-rc.1.26420.103','Private SDK differs')
 review=load(old/'receipts/native-build-review.json');critical=review['criticalHashes'];require(all(sha(review[k])==v for k,v in critical.items()),'Matching critical7 differs')
 src=out/'AndroidBudgetBridge.cs';src.write_text(BRIDGE)
 csc=source/'.dotnet/sdk/11.0.100-rc.1.26420.103/Roslyn/bincore/csc.dll';refs=sorted(inp.glob('*.dll'))
 rsp=out/'bridge.rsp';rsp.write_text('\n'.join(['/noconfig','/nostdlib+','/target:exe','/langversion:preview','/nullable:enable','/optimize+','/deterministic+','/out:'+str(inp/BRIDGE_NAME)]+['/r:'+str(p) for p in refs]+[str(src)])+'\n')
 env=clean_env();command([sdk,'exec',csc,'@'+str(rsp)],out/'bridge-build.log',env)
 dest=out/'layout';shutil.copytree(old,dest)
 for p in (dest/'managed').glob('*.dll'):p.unlink()
 inputs=sorted(inp.glob('*.dll'));opts=['--targetos:linux','--targetarch:x64','--composite','--inputbubble','--resilient','--optimize','--parallelism:2','--out:'+str(dest/'managed/RuneCLR.Android.Framework.dll')]
 rsp2=out/'crossgen.rsp';rsp2.write_text('\n'.join(opts+list(map(str,inputs)))+'\n')
 command([review['crossgen2'],'@'+str(rsp2)],out/'crossgen.log',env)
 require(all((dest/'managed'/p.name).is_file() for p in inputs),'Regenerated components missing')
 command([sdk,'exec','--fx-version','11.0.0-rc.1.26420.103',a.metadata_inspector,review['corelib'],review['corelib'],dest/'managed/System.Private.CoreLib.dll'],out/'metadata.log',env)
 text=(out/'metadata.log').read_text();data=json.loads(text)
 require(data[0]['methods']==data[2]['methods'] and data[0]['fields']==data[2]['fields'] and data[0]['moduleVersionId']==data[2]['moduleVersionId'],'Fresh bridge composite changed CoreLib private ABI')
 rows=[r for r in original['files'] if not r['path'].startswith('managed/') or not r['path'].endswith('.dll')]
 originals={Path(r['path']).name:r for r in original['files']}
 for p in sorted((dest/'managed').glob('*.dll')):
  row=dict(originals.get(p.name,{'role':'framework','sourceCommit':COMMIT}));row.update(path=p.relative_to(dest).as_posix(),sha256=sha(p),inputSha256=sha(inp/p.name) if (inp/p.name).exists() else None,generatedByCriticalCrossgen2Sha256=critical['crossgen2'])
  rows.append(row)
 original.update(files=rows,derivedWithExecutableBridge=True,original200LayoutReceiptSha256=sha(old/'layout.json'),bridgeSourceSha256=sha(src),bridgeInputSha256=sha(inp/BRIDGE_NAME),bridgeComponentSha256=sha(dest/'managed'/BRIDGE_NAME),compositeInputCount=len(inputs),compositeFileCount=len(list((dest/'managed').glob('*.dll'))),driverSha256=sha(__file__),executionVerified=False)
 write(dest/'layout.json',original);write(out/'results.json',{'success':True,'base':BASE,'commit':COMMIT,'tree':TREE,'configuration':'Release','target':'android.x64','layoutSha256':sha(dest/'layout.json'),'files':len(rows),'compositeInputs':len(inputs),'compositeOutputs':original['compositeFileCount'],'critical7Unchanged':all(sha(review[k])==v for k,v in critical.items()),'corelibPrivateMetadataUnchanged':True,'rawHashes':{f.name:sha(f) for f in out.iterdir() if f.is_file()},'executionVerified':False})
 print('BRIDGE_COMPOSITE_PASS',out)

def patch_template(p,anchor,replacement):
 t=p.read_text();require(t.count(anchor)==1,'Official wrapper anchor changed: '+anchor);p.write_text(t.replace(anchor,replacement))

def apk(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);layout=a.layout.resolve();l=load(layout/'layout.json')
 require(l['success'] and l['commit']==COMMIT and l['tree']==TREE and l['derivedWithExecutableBridge'],'Matching bridge layout required')
 require(all(sha(layout/r['path'])==r['sha256'] for r in l['files']),'Layout actual hashes changed')
 app=out/'app';app.mkdir();headers=out/'headers';headers.mkdir()
 for r in l['files']:
  if r['path'].startswith(('managed/','native/','java/')):target=app/Path(r['path']).name
  elif r['path'].startswith('headers/'):target=out/r['path'];target.parent.mkdir(parents=True,exist_ok=True)
  else:continue
  require(not target.exists(),'Layout basename collision');shutil.copy2(layout/r['path'],target)
 shutil.copy2(layout/'layout.json',out/'layout.json');shutil.copy2(layout/'receipts/native-build-review.json',out/'matching-build-review.json')
 builder=out/'builder';shutil.copytree(a.builder,builder,ignore=shutil.ignore_patterns('bin','obj'));builder_before=files(a.builder)
 native=builder/'Templates/monodroid-coreclr.c'
 anchor='    setenv ("DOTNET_CrashReportBeforeSignalChaining", "1", true);';patch_template(native,anchor,anchor+'\n'+NATIVE)
 patch_template(native,'    unsigned int rv;','    unsigned int rv = 255;')
 anchor='    coreclr_execute_assembly (coreclr_handle, coreclr_domainId, managed_argc, managed_argv, executable_path, &rv);'
 patch_template(native,anchor,'    int execute_hr = coreclr_execute_assembly (coreclr_handle, coreclr_domainId, managed_argc, managed_argv, executable_path, &rv);\n    printf("CORECLR_EXECUTE_HRESULT=0x%x;RUNECLR_EXIT=%u\\n",execute_hr,rv);\n    if (execute_hr != 0) return 255;')
 anchor='    LOG_INFO ("coreclr_initialize returned 0x%x", rv);';patch_template(native,anchor,anchor+'\n    printf("CORECLR_INITIALIZE_HRESULT=0x%x\\n",rv);')
 anchor='        coreclr_shutdown (g_coreclr_handle, g_coreclr_domainId);';patch_template(native,anchor,'        int shutdown_hr = coreclr_shutdown (g_coreclr_handle, g_coreclr_domainId);\n        printf("CORECLR_SHUTDOWN_HRESULT=0x%x\\n",shutdown_hr);')
 java=builder/'Templates/MonoRunner.java';anchor='        int rv = initRuntime(filesDir, entryPointLibName, localDateTimeOffset);';patch_template(java,anchor,JAVA+'\n'+anchor)
 (out/'Directory.Build.props').write_text('<Project />\n');(out/'global.json').write_text(json.dumps({'sdk':{'version':'11.0.100-rc.1.26420.103','rollForward':'disable'}}))
 (app/'runtimeconfig.bin').write_bytes(b'\x00')
 name='RuneCLR_Budget_'+uuid.uuid4().hex[:12]
 proj='''<Project><UsingTask TaskName="AndroidAppBuilderTask" AssemblyFile="$(MSBuildThisFileDirectory)builder/bin/Release/net11.0/AndroidSmokeBuilder.dll"/><Target Name="Build"><AndroidAppBuilderTask AppDir="$(MSBuildThisFileDirectory)app" MainLibraryFileName="'''+BRIDGE_NAME+'''" RuntimeIdentifier="android-x64" RuntimeFlavor="CoreCLR" ProjectName="$(AndroidProjectName)" OutputDir="$(MSBuildThisFileDirectory)apk" AndroidSdk="$(AndroidSdk)" AndroidNdk="$(AndroidNdk)" RuntimeHeaders="$(MSBuildThisFileDirectory)headers/hosts;$(MSBuildThisFileDirectory)headers/native" BuildApiLevel="36" BuildToolsVersion="35.0.1" TargetApiLevel="35" MinApiLevel="24" StaticLinkedRuntime="false" ForceInterpreter="false" ForceAOT="false" StripDebugSymbols="false"/></Target></Project>'''
 (out/'package.proj').write_text(proj)
 e=clean_env();ar=a.android_root.resolve();sdk=ar/'sdk';ndk=sdk/'ndk/27.2.12479018';j=ar/'android-studio/jbr'
 e.update(JAVA_HOME=str(j),ANDROID_HOME=str(sdk),ANDROID_SDK_ROOT=str(sdk),ANDROID_NDK_ROOT=str(ndk),PATH=str(j/'bin')+';C:/Program Files/Microsoft Visual Studio/2022/Professional/Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja;'+e['PATH'])
 command([a.dotnet,'build','builder/builder.csproj','-c','Release'],out/'builder-build.log',e,out)
 command([a.dotnet,'msbuild','package.proj','/t:Build','/p:AndroidSdk='+str(sdk),'/p:AndroidNdk='+str(ndk),'/p:AndroidProjectName='+name,'/v:minimal'],out/'apk-build.log',e,out)
 apkfile=out/'apk/bin'/(name+'.apk');require(apkfile.is_file(),'Official builder did not produce APK')
 staged=files(app);packaged={};natives={};dexes={}
 with zipfile.ZipFile(apkfile) as z:
  require('assets/assets.zip' in z.namelist(),'Nested official assets missing')
  with zipfile.ZipFile(io.BytesIO(z.read('assets/assets.zip'))) as assets:
   for n in assets.namelist():
    if n.endswith('/'):continue
    require('/' not in n and not n.startswith('HostBudgetProbe.'),'Author/operator material bundled')
    packaged[n]=hashlib.sha256(assets.read(n)).hexdigest()
  for n in z.namelist():
   if n.startswith('lib/') and n.endswith('.so'):
    require(n.startswith('lib/x86_64/'),'Non x64 APK native image');natives[n]=hashlib.sha256(z.read(n)).hexdigest();packaged[Path(n).name]=natives[n]
   if re.fullmatch(r'classes([2-9]|[1-9][0-9]+)\.dex',n):dexes[n]=hashlib.sha256(z.read(n)).hexdigest()
 for n,h in staged.items():
  if n.endswith('.dex'):
   require(sum(v==h for v in dexes.values())==1,'Crypto DEX must appear exactly once as classesN.dex');packaged[n]=h
  require(packaged.get(n)==h,'APK changed actual input: '+n)
 state={'success':True,'package':'net.dot.'+name,'apk':str(apkfile),'apkSha256':sha(apkfile),'appHashes':staged,'packagedHashes':packaged,'apkNativeHashes':natives,'apkDexHashes':dexes,'runtimeCommit':COMMIT,'runtimeTree':TREE,'inputManifestSha256':sha(a.inputs/'input-manifest.json'),'inputFiles':load(a.inputs/'input-manifest.json')['files'],'layoutSha256':sha(out/'layout.json'),'buildReviewSha256':sha(out/'matching-build-review.json'),'builderOriginalHashes':builder_before,'builderGeneratedHashes':files(builder),'nativeSourceSha256':sha(native),'javaSourceSha256':sha(java),'driverSha256':sha(__file__),'createdUtc':utc(),'installed':False,'executionVerified':False}
 write(out/'state.json',state);shutil.copy2(a.inputs/'input-manifest.json',out/'input-manifest.json');shutil.copy2(__file__,out/'driver.py');print('APK_BUILD_PASS',apkfile)

def adb(a,argv,check=True):
 p=subprocess.run([str(a.android_root/'sdk/platform-tools/adb.exe'),'-s',a.serial,*map(str,argv)],capture_output=True,timeout=60)
 if check:require(p.returncode==0,'Owned ADB failed: '+' '.join(map(str,argv))+' '+p.stderr.decode(errors='replace'))
 return p.stdout.decode(errors='replace').strip(),p.returncode
def device(a):
 require(a.serial=='emulator-5556','Only explicitly owned emulator-5556 accepted')
 require(adb(a,['get-state'])[0]=='device' and adb(a,['shell','uname','-m'])[0]=='x86_64','Owned emulator not ready/x64')
 require(adb(a,['emu','avd','name'])[0].splitlines()[0]=='RuneCLR_API_35_x64','Wrong AVD owner')

def start(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);adbexe=a.android_root/'sdk/platform-tools/adb.exe'
 require(a.serial=='emulator-5556','Only owned5556 startup supported')
 p=subprocess.run([str(adbexe),'devices'],capture_output=True,text=True);require(a.serial not in p.stdout,'Owned emulator already running; record separate receipt')
 env=clean_env();env.update(ANDROID_HOME=str(a.android_root/'sdk'),ANDROID_SDK_ROOT=str(a.android_root/'sdk'),ANDROID_AVD_HOME=str(a.android_root/'avd'))
 argv=[str(a.android_root/'sdk/emulator/emulator.exe'),'-avd','RuneCLR_API_35_x64','-port','5556','-gpu','software','-no-snapshot','-no-metrics','-no-window']
 # CREATE_NO_WINDOW keeps the owned helper process hidden on Windows.
 with (out/'emulator.stdout.log').open('wb') as stdout,(out/'emulator.stderr.log').open('wb') as stderr:
  child=subprocess.Popen(argv,stdout=stdout,stderr=stderr,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 write(out/'request.json',{'pid':child.pid,'command':argv,'serial':a.serial,'startedUtc':utc(),'devicePhysical':False})
 deadline=time.time()+180
 while time.time()<deadline:
  try:
   if adb(a,['shell','getprop','sys.boot_completed'],False)[0]=='1':device(a);write(out/'results.json',{'success':True,'pid':child.pid,'serial':a.serial,'readyUtc':utc()});return
  except Exception:pass
  time.sleep(3)
 raise RuntimeError('Owned emulator startup timed out')

def push(a,state,source,relative,log):
 require(re.fullmatch('[A-Za-z0-9_./-]+',relative) and '..' not in relative,'Invalid owned relative path')
 temp='/data/local/tmp/runeclr-budget-'+uuid.uuid4().hex
 adb(a,['push',source,temp]);adb(a,['shell','run-as',state['package'],'mkdir','-p','files/'+str(Path(relative).parent).replace('\\','/')])
 try:
  adb(a,['shell','run-as',state['package'],'cp',temp,'files/'+relative]);line=adb(a,['shell','run-as',state['package'],'sha256sum','files/'+relative])[0]
  require(line.split()[0]==sha(source),'Transferred input hash differs')
  with Path(log).open('a') as f:f.write(line+'\n')
 finally:adb(a,['shell','rm',temp])

def install(a):
 device(a);out=a.output.resolve();s=load(out/'state.json');require(not s['installed'] and sha(s['apk'])==s['apkSha256'],'Fresh APK identity differs')
 require(s['package'] not in adb(a,['shell','pm','list','packages',s['package']])[0],'Fresh appID already exists')
 command([a.android_root/'sdk/platform-tools/adb.exe','-s',a.serial,'install',s['apk']],out/'install.log',timeout=180)
 s['installed']=True;s['installedUtc']=utc();s['serial']=a.serial;s['device']={'api':adb(a,['shell','getprop','ro.build.version.sdk'])[0],'pageSize':adb(a,['shell','getconf','PAGESIZE'])[0],'architecture':adb(a,['shell','uname','-m'])[0]};write(out/'state.json',s)
 for n,h in s['appHashes'].items():
  if not n.endswith('.so'):push(a,s,out/'app'/n,n,out/'install-hash-reads.log')
 require(time.time()>0 and a.inputs is not None,'Explicit frozen mobile IL required')
 m=load(a.inputs/'input-manifest.json');require(sha(a.inputs/'input-manifest.json')==s['inputManifestSha256'] and m['files']==s['inputFiles'],'Frozen original mobile inputs differ')
 produced=out/'postinstall-author';produced.mkdir(exist_ok=False);started=utc()
 for n in m['authorCollectibleILOnly']:
  require(sha(a.inputs/n)==m['files'][n],'Original author IL changed');target=produced/Path(n).name;shutil.copy2(a.inputs/n,target);push(a,s,target,n,out/'transfer-hash-reads.log')
 write(out/'postinstall-author.json',{'installedUtc':s['installedUtc'],'transferStartedUtc':started,'completedUtc':utc(),'apkSha256':s['apkSha256'],'source':'Unchanged frozen original author IL copied after install; no newly compiled author claim','files':{n:m['files'][n] for n in m['authorCollectibleILOnly']}})
 s['authorHashes']={n:m['files'][n] for n in m['authorCollectibleILOnly']};s['authorTransferredUtc']=utc();write(out/'state.json',s);print('INSTALL_TRANSFER_PASS',s['package'])

def inventory(a,s,out,name,native_dir):
 values={};lines=[]
 for n,h in s['appHashes'].items():
  path=native_dir+'/'+n if n.endswith('.so') else 'files/'+n
  line=adb(a,['shell','run-as',s['package'],'sha256sum',path])[0];require(line.split()[0]==h,'Installed immutable hash differs '+n);values[n]=h;lines.append(line)
 for n,h in s['authorHashes'].items():
  line=adb(a,['shell','run-as',s['package'],'sha256sum','files/'+n])[0];require(line.split()[0]==h,'Installed author IL differs');values[n]=h;lines.append(line)
 apkpath=adb(a,['shell','pm','path',s['package']])[0].removeprefix('package:');require('\n' not in apkpath,'Split APK unexpected')
 line=adb(a,['shell','sha256sum',apkpath])[0];require(line.split()[0]==s['apkSha256'],'Installed APK hash differs');values['apk/base.apk']=s['apkSha256'];lines.append(line)
 (out/(name+'.sha256sum.log')).write_text('\n'.join(lines)+'\n');write(out/(name+'.json'),values);return values

def run(a):
 device(a);root=a.output.resolve();s=load(root/'state.json');require(s['installed'] and s.get('authorHashes') and sha(s['apk'])==s['apkSha256'],'Frozen installed state required')
 nonce=uuid.uuid4().hex;out=root/('run-'+a.scenario+'-'+nonce);out.mkdir();result={'success':False,'platform':'android.x86_64','nonce':nonce,'appPid':None,'runtimeCommit':COMMIT,'runtimeTree':TREE,'inputManifestSha256':s['inputManifestSha256'],'inputFiles':s['inputFiles'],'timedOut':False,'debugger':False,'instrumentationExit':None,'executionVerified':False,'nativeEntryProof':False,'bundleUnchanged':False}
 for n in ('matching-build-review.json','layout.json','postinstall-author.json','input-manifest.json'):shutil.copy2(root/n,out/n)
 result.update(buildReceiptRawPath='matching-build-review.json',buildReceiptSha256=sha(out/'matching-build-review.json'),settings={'InterpMode':0,'RuneCLRInterpretCollectible':0,'ReadyToRun':1,'TieredCompilation':1})
 try:
  appinfo=adb(a,['shell','dumpsys','package',s['package']])[0];(out/'package-before.txt').write_text(appinfo)
  match=re.search(r'(?m)^\s*(?:legacyNativeLibraryDir|nativeLibraryDir)=([^\s]+)',appinfo);require(match,'Installed native library path absent');native_dir=match.group(1)
  # Android's legacyNativeLibraryDir is the ABI parent, not the loaded directory.
  observed,code=adb(a,['shell','run-as',s['package'],'find',native_dir,'-name','libcoreclr.so'],False)
  paths=observed.splitlines() if code==0 else []
  require(len(paths)==1 and paths[0].startswith(native_dir+'/') and paths[0].endswith('/libcoreclr.so'),'Actual installed CoreCLR native path is ambiguous/missing')
  native_dir=paths[0].rsplit('/',1)[0];(out/'native-path-query.txt').write_text(observed+'\n')
  before=inventory(a,s,out,'installed-before',native_dir)
  adb(a,['shell','am','force-stop',s['package']])
  args=[a.android_root/'sdk/platform-tools/adb.exe','-s',a.serial,'shell','am','instrument','-w','-e','env:RUNECLR_BUDGET_NONCE',nonce,'-e','env:RUNECLR_BUDGET_SCENARIO',a.scenario,s['package']+'/net.dot.MonoRunner']
  write(out/'request.json',{'command':list(map(str,args)),'startedUtc':utc(),'nonce':nonce,'scenario':a.scenario,'sourceCommit':COMMIT,'tree':TREE,'deviceSerial':a.serial,'apkSha256':s['apkSha256'],'layoutSha256':s['layoutSha256'],'inputManifestSha256':s['inputManifestSha256'],'settings':result['settings']})
  code,timed=command(args,out/'instrumentation.log',timeout=a.timeout,check=False);result.update(instrumentationExit=code,timedOut=timed)
  if timed:adb(a,['shell','am','force-stop',s['package']])
  for suffix in ['native.log','jit.log','managed.log','managed-result.json','pid-query.txt','maps.log']:
   p=subprocess.run([str(a.android_root/'sdk/platform-tools/adb.exe'),'-s',a.serial,'exec-out','run-as',s['package'],'cat','files/budget-'+nonce+'.'+suffix],capture_output=True,timeout=60)
   (out/suffix).write_bytes(p.stdout);(out/(suffix+'.pull-stderr.log')).write_bytes(p.stderr)
   require(p.returncode==0,'Owned raw pull failed '+suffix)
  proc=subprocess.run([str(a.android_root/'sdk/platform-tools/adb.exe'),'-s',a.serial,'exec-out','run-as',s['package'],'tar','-cf','-','-C','files/budget-evidence-'+nonce,'.'],capture_output=True,timeout=60)
  (out/'adapter-evidence.tar').write_bytes(proc.stdout);require(proc.returncode==0,'Owned adapter evidence pull failed')
  import tarfile
  with tarfile.open(out/'adapter-evidence.tar') as t:
   require(all(not Path(n.name).is_absolute() and '..' not in Path(n.name).parts for n in t.getmembers()),'Evidence archive path escapes');t.extractall(out/'adapter-evidence')
  native=(out/'native.log').read_text(errors='replace');managed=load(out/'managed-result.json');pidquery=(out/'pid-query.txt').read_text().strip()
  match=re.findall(r'(?m)^MOBILE_BUDGET_NATIVE pid=([0-9]+) nonce=([0-9a-f]{32}) InterpMode=0 RuneCLRInterpretCollectible=0 ReadyToRun=1$',native)
  require(len(match)==1 and match[0][1]==nonce,'Unique native ownership header missing');pid=int(match[0][0]);result['appPid']=pid
  require(pidquery=='android.os.Process.myPid='+str(pid) and managed['appPid']==pid and managed['nonce']==nonce,'Java/native/managed PIDnonce differs')
  require(code==0 and not timed and re.search(r'(?m)^INSTRUMENTATION_RESULT: return-code=0\r?$',(out/'instrumentation.log').read_text()) and re.search(r'(?m)^CORECLR_EXECUTE_HRESULT=0x0;RUNECLR_EXIT=0$',native) and managed['exitCode']==0,'Actual instrumentation/native/managed completion failed')
  require(all(managed[k]==1 for k in ('policy','meter','terminal','gc')) and managed['defaultPolicy']==0,'Native budget capability acknowledgements differ')
  maps=(out/'maps.log').read_text();actual=re.findall(r'(?m)(/[^\s]+/libcoreclr\.so)$',maps);require(actual and actual[0].rsplit('/',1)[0]==native_dir,'Mapped CoreCLR path differs from installed native directory')
  require('/libclrinterpreter.so' in maps,'Actual dynamic interpreter not mapped')
  after=inventory(a,s,out,'installed-after',native_dir);require(before==after,'Installed bundle/payload inventory changed')
  result.update(bundleUnchanged=True,installedInventory={'before':before,'after':after,'beforeRawPath':'installed-before.json','afterRawPath':'installed-after.json','authorSources':s['authorHashes']},nativeLog='native.log',normalExitCode=code,nativeManagedExitZero=True,success=True,executionVerified=True)
 except Exception:result['error']=traceback.format_exc();raise
 finally:
  result['rawHashes']=files(out);write(out/'mobile-run.json',result);print('RUN_RECEIPT',out/'mobile-run.json')

def cleanup(a):
 root=a.output.resolve();s=load(root/'state.json');device(a);adb(a,['shell','am','force-stop',s['package']]);text,code=adb(a,['uninstall',s['package']]);require('Success' in text,'Owned fresh app uninstall failed');write(root/'cleanup.json',{'success':True,'package':s['package'],'serial':a.serial,'appUninstalled':True,'physicalDeviceTouched':False,'completedUtc':utc()})
 if a.shutdown:
  adb(a,['emu','kill']);write(root/'emulator-shutdown.json',{'requested':True,'serial':a.serial,'completedUtc':utc()})

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=('bridge','build','start','install','run','cleanup'))
 p.add_argument('--output',type=Path,required=True);p.add_argument('--layout',type=Path);p.add_argument('--runtime',type=Path);p.add_argument('--metadata-inspector',type=Path);p.add_argument('--inputs',type=Path)
 p.add_argument('--builder',type=Path,default=Path('D:/RuneCLR-Android/coreclr-smoke/run-20261012-172351/builder'));p.add_argument('--android-root',type=Path,default=Path('D:/RuneCLR-Android'));p.add_argument('--dotnet',type=Path,default=Path('E:/runtime/.dotnet/dotnet.exe'));p.add_argument('--serial',default='emulator-5556');p.add_argument('--scenario',choices=('Normal','all'),default='all');p.add_argument('--timeout',type=int,default=900);p.add_argument('--shutdown',action='store_true');a=p.parse_args()
 try:{'bridge':bridge,'build':apk,'start':start,'install':install,'run':run,'cleanup':cleanup}[a.phase](a)
 except Exception:
  if a.output.exists():write(a.output/('phase-failure-'+a.phase+'-'+uuid.uuid4().hex+'.json'),{'error':traceback.format_exc(),'phase':a.phase,'executionVerified':False,'utc':utc()})
  raise

if __name__=='__main__':main()
