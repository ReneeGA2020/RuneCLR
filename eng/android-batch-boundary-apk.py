#!/usr/bin/env python3
"""Fresh Android batch boundary bridge, APK and five-lane functional acceptance.

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
COMMIT='3126bbc9a8851a09ac6435b18a12882bad48f3ee'
TREE='710936ae1729a5689ab0e0896f3cf722ddd3d31c'
BRIDGE_NAME='AndroidBatchBoundaryBridge.dll'
BUILD_SHA='e4f0451abf6dcc47671b1ae400a98bf3316b0bf27478c468d1022cab0dd37769'
PROOF_SHA='29d83ae68ca57ec2067261d15a901e81f8422981609f1fe6aaad5cb37879de5e'
FRAMEWORK_SHA='ac491a83b59ffd6d9abd396f2da3a415d4f171830e7c4b1af287e1948cfc86a3'
FRAMEWORK_INVENTORY_SHA='bb87538a5f80cecb6f6dbe82eee7f41a1e7f735929d42438d582d960f4fd013e'
INPUT_SHA='82ea9368e8fe6e7070b6d181e09c2294aed0aacb3d2008399ae92a15ae88d3fb'
REVIEW_SHA='9aab8cae277ad138b6635b9db61bf30bcfa942ce14aa54c56df71e6bb683ccd2'
LANES=((1,1),(1,100),(1,1000),(100,100),(1000,1000))
HEX={1:'1',100:'64',1000:'3e8'}
SANITIZE=('CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','LIBRARY_PATH','SDKROOT','MACOSX_DEPLOYMENT_TARGET','CMAKE_PREFIX_PATH','PKG_CONFIG_PATH','DYLD_LIBRARY_PATH','DYLD_FALLBACK_LIBRARY_PATH','LD_LIBRARY_PATH','LD_PRELOAD')
BRIDGE=r'''
using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using System.Text.Json;
static class AndroidBatchBoundaryBridge {
 static int Version(Type owner,string name) {
  MethodInfo? method=owner.GetMethod(name,BindingFlags.NonPublic|BindingFlags.Static,null,Type.EmptyTypes,null);
  if(method?.ReturnType!=typeof(int))throw new PlatformNotSupportedException("Trusted budget version missing");
  int value=method.CreateDelegate<Func<int>>()();
  if(value!=1)throw new PlatformNotSupportedException("Trusted budget native version differs");
  return value;
 }
 public static int Main(string[] ignored) {
  string root=AppContext.BaseDirectory;
  string nonce=Environment.GetEnvironmentVariable("RUNECLR_BATCH_NONCE")??throw new InvalidOperationException("No nonce");
  string matrix=Environment.GetEnvironmentVariable("RUNECLR_BATCH_MATRIX")??throw new InvalidOperationException("No matrix");
  string interval=Environment.GetEnvironmentVariable("DOTNET_RuneCLRBatchInterval")??throw new InvalidOperationException("No actual interval");
  if(nonce.Length!=32 || (matrix!="1" && matrix!="100" && matrix!="1000"))throw new InvalidOperationException("Invalid lane");
  string prefix=Path.Combine(root,"batch-"+nonce), receipt=prefix+".boundary.json";
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
    Console.WriteLine($"ANDROID_BATCH_POLICY policy={policy} meter={meter} terminal={terminal} gc={gc} default={defaultPolicy}");
    Console.WriteLine($"ANDROID_BATCH_MANAGED pid={Environment.ProcessId} nonce={nonce} matrix={matrix} interval={interval} arch={RuntimeInformation.ProcessArchitecture}");
    code=MobileBatchBoundaryProbe.Entry.Run(new[]{Path.Combine(root,"author/BatchBoundary.Author.dll"),receipt,matrix,nonce});
   } catch(Exception error) {
    // Do not invoke an author exception's Message or ToString virtual property.
    code=1;Console.Error.WriteLine("ANDROID_BATCH_BRIDGE_FAILURE type="+error.GetType().FullName);
   } finally {Console.SetOut(originalOut);Console.SetError(originalError);}
  }
  // Forward the actual completed managed stream unchanged into native stdout.
  // This preserves the adapter's original marker, not a derived scalar summary.
  originalOut.Write(File.ReadAllText(prefix+".managed.log"));originalOut.Flush();
  File.WriteAllText(prefix+".maps.log",File.ReadAllText("/proc/self/maps"));
  File.WriteAllText(prefix+".managed-result.json",JsonSerializer.Serialize(new {nonce,matrix,interval,exitCode=code,appPid=Environment.ProcessId,policy,meter,terminal,gc,defaultPolicy}));
  return code;
 }
}
'''
NATIVE=r'''
    const char* nonce = getenv("RUNECLR_BATCH_NONCE");
    const char* matrix = getenv("RUNECLR_BATCH_MATRIX");
    const char* batch_hex = getenv("RUNECLR_BATCH_HEX");
    if (!nonce || strlen(nonce) != 32 || strspn(nonce,"0123456789abcdef") != 32 || !matrix || !batch_hex) return -1;
    if ((strcmp(matrix,"1") && strcmp(matrix,"100") && strcmp(matrix,"1000")) ||
        (strcmp(batch_hex,"1") && strcmp(batch_hex,"64") && strcmp(batch_hex,"3e8"))) return -1;
    char native_path[2048];
    snprintf(native_path,sizeof(native_path),"%s/batch-%s.native.log",g_bundle_path,nonce);
    if (freopen(native_path,"w",stdout)==NULL || dup2(fileno(stdout),fileno(stderr))<0) return -1;
    setvbuf(stdout,NULL,_IONBF,0);setvbuf(stderr,NULL,_IONBF,0);
    setenv("DOTNET_InterpMode","0",1);
    setenv("DOTNET_RuneCLRInterpretCollectible","0",1);
    setenv("DOTNET_ReadyToRun","1",1);
    setenv("DOTNET_TieredCompilation","0",1);
    setenv("DOTNET_InterpList","0",1);
    unsetenv("DOTNET_InterpDump");
    unsetenv("DOTNET_JitDisasm");unsetenv("DOTNET_JitDisasmSummary");unsetenv("DOTNET_JitStdOutFile");
    setenv("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT","1",1);
    setenv("DOTNET_RuneCLRPhaseAcquireLoad","1",1);
    setenv("DOTNET_RuneCLRDerivedLedger","0",1);
    setenv("DOTNET_RuneCLRBatchInterval",batch_hex,1);
    setenv("RUNECLR_BATCH_TEST_SWITCH","DOTNET_RuneCLRBatchInterval",1);
    unsetenv("DOTNET_RuneCLRInterpreterRefuseMethods");
    printf("ANDROID_BATCH_NATIVE pid=%d nonce=%s matrix=%s interval=%s PhaseAcquireLoad=1 DerivedLedger=0 InterpMode=0 ReadyToRun=1\n",getpid(),nonce,matrix,batch_hex);
'''
JAVA=r'''
        try {
            String nonce = android.system.Os.getenv("RUNECLR_BATCH_NONCE");
            if (nonce == null || !nonce.matches("[0-9a-f]{32}")) throw new RuntimeException("Missing owned nonce");
            java.io.FileOutputStream stream = new java.io.FileOutputStream(new java.io.File(filesDir,"batch-"+nonce+".pid-query.txt"));
            stream.write(("android.os.Process.myPid="+android.os.Process.myPid()+"\n").getBytes(java.nio.charset.StandardCharsets.UTF_8));stream.close();
        } catch (java.io.IOException error) { throw new RuntimeException(error); }
'''
FORWARD=r'''
    char managed_path[2048];
    snprintf(managed_path,sizeof(managed_path),"%s/batch-%s.managed.log",g_bundle_path,getenv("RUNECLR_BATCH_NONCE"));
    FILE* managed_file = fopen(managed_path,"rb");
    if (!managed_file) return 255;
    char managed_buffer[4096];
    size_t managed_bytes;
    while ((managed_bytes = fread(managed_buffer,1,sizeof(managed_buffer),managed_file)) != 0) {
        if (fwrite(managed_buffer,1,managed_bytes,stdout) != managed_bytes) { fclose(managed_file); return 255; }
    }
    int managed_read_error = ferror(managed_file);
    int managed_close_error = fclose(managed_file);
    if (managed_read_error || managed_close_error || fflush(stdout)) return 255;
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
 e={k:v for k,v in os.environ.items() if not k.startswith(('DOTNET_','COMPlus_','RUNECLR_'))}
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

def inputs(root):
 root=root.resolve();m=load(root/'input-manifest.json')
 require(sha(root/'input-manifest.json')==INPUT_SHA and m['schema']=='runeclr.mobile-batch-boundary.inputs.v1'
         and m['expectedContexts']==168 and m['configuredLanes']==[list(x) for x in LANES],'Frozen boundary manifest differs')
 for n,h in m['files'].items():
  p=(root/n).resolve();require(p.is_relative_to(root) and sha(p)==h,'Frozen input changed '+n)
 return m

def bridge(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);source=a.runtime.resolve();build=load(source.parent/'results.json')
 require(sha(source.parent/'results.json')==BUILD_SHA and build['success'] and build['commit']==COMMIT and build['tree']==TREE,'Matching new batch build required')
 require(sha(source.parent/'source-proof.json')==PROOF_SHA,'Source proof differs')
 proof=load(source.parent/'source-proof.json');require(all(sha(source/n)==h for n,h in proof['sourceHashes'].items()),'Live source38 bytes differ')
 require(subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==COMMIT and subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD^{tree}'],text=True).strip()==TREE and not subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no'],text=True).strip(),'Live source identity differs')
 require(all(sha(build[k])==h for k,h in build['criticalHashes'].items()),'Critical7 differs')
 require(sha(a.framework/'results.json')==FRAMEWORK_SHA and sha(a.framework/'input-inventory.json')==FRAMEWORK_INVENTORY_SHA,'Original framework receipts differ')
 inventory=load(a.framework/'input-inventory.json');rows=inventory['groups']['framework'];require(len(rows)==180,'Original IL180 required')
 require(all(sha(r['path'])==r['sha256'] for r in rows),'Original framework bytes changed')
 m=inputs(a.inputs);sdk=source/'.dotnet/dotnet';require(subprocess.check_output([str(sdk),'--version'],text=True).strip()=='11.0.100-rc.1.26420.103','Private SDK differs')
 src=out/'AndroidBatchBoundaryBridge.cs';src.write_text(BRIDGE,encoding='ascii');refs=[Path(r['path']) for r in rows if Path(r['path']).name!='System.Private.CoreLib.dll']+[Path(build['corelib']),a.inputs/'host/MobileBatchBoundaryProbe.dll',a.inputs/'host/BatchBoundary.Contract.dll']
 csc=source/'.dotnet/sdk/11.0.100-rc.1.26420.103/Roslyn/bincore/csc.dll';rsp=out/'bridge.rsp';target=out/BRIDGE_NAME
 require(sha(csc)=='209354dc17c97c459d20339ec2232876c40203355ed3d9d648d704d92627a606' and sha(sdk)=='5da85c9c6ab686aca9a4f61ff5a8a517ee6a67151d7a17d941326a5032a9150d','Actual private compiler/SDK differs')
 references={str(p):sha(p) for p in refs}
 rsp.write_text('\n'.join(['/nostdlib+','/target:exe','/langversion:preview','/nullable:enable','/optimize+','/deterministic+','/out:'+str(target)]+['/r:'+str(p) for p in refs]+[str(src)])+'\n')
 command([sdk,'exec',csc,'/noconfig','@'+str(rsp)],out/'bridge-build.log',clean_env())
 require(all(sha(p)==h for p,h in references.items()) and all(sha(build[k])==h for k,h in build['criticalHashes'].items()),'Bridge compilation changed original refs/critical7')
 write(out/'bridge.json',{'success':True,'schema':'runeclr.android-batch-boundary.bridge.v1','commit':COMMIT,'tree':TREE,'assembly':BRIDGE_NAME,'bridgePath':str(target),'bridgeSha256':sha(target),'sourcePath':str(src),'sourceSha256':sha(src),'buildReceiptSha256':BUILD_SHA,'sourceProofSha256':PROOF_SHA,'frameworkReceiptSha256':FRAMEWORK_SHA,'frameworkInventorySha256':FRAMEWORK_INVENTORY_SHA,'inputManifestSha256':INPUT_SHA,'inputFiles':m['files'],'referenceHashes':{str(p):sha(p) for p in refs},'cscSha256':sha(csc),'rspSha256':sha(rsp),'driverSha256':sha(__file__),'executionVerified':False})
 print('ANDROID_BATCH_BRIDGE_PASS',target)

def patch_template(p,anchor,replacement):
 t=p.read_text();require(t.count(anchor)==1,'Official wrapper anchor changed: '+anchor);p.write_text(t.replace(anchor,replacement))

def apk(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);layout=a.layout.resolve();l=load(layout/'layout.json')
 require(l['success'] and l['commit']==COMMIT and l['tree']==TREE and l['schema']=='runeclr.android-batch-boundary.layout.v1' and l['expectedContexts']==168 and l['executableAssembly']==BRIDGE_NAME,'Matching bridge layout required')
 require(all(sha(layout/r['path'])==r['sha256'] for r in l['files']),'Layout actual hashes changed')
 require(all(sha(layout/r['path'])==r['sha256'] for r in l['receipts']),'Layout receipt bytes changed')
 require(l['buildReceiptSha256']==BUILD_SHA and l['sourceProofSha256']==PROOF_SHA and l['inputManifestSha256']==INPUT_SHA and l['compositeInputCount']==184 and l['compositeFileCount']==185,'Fresh matching composite ownership differs')
 m=inputs(a.inputs);require(l['inputFiles']==m['files'],'Layout boundary input ownership differs')
 app=out/'app';app.mkdir();headers=out/'headers';headers.mkdir()
 for r in l['files']:
  if r['path'].startswith(('managed/','native/','java/')):target=app/Path(r['path']).name
  elif r['path'].startswith('headers/'):target=out/r['path'];target.parent.mkdir(parents=True,exist_ok=True)
  else:continue
  require(not target.exists(),'Layout basename collision');shutil.copy2(layout/r['path'],target)
 shutil.copy2(layout/'layout.json',out/'layout.json');shutil.copy2(layout/'receipts/native-build-review.json',out/'matching-build-review.json')
 require(sha(out/'matching-build-review.json')==BUILD_SHA,'Pinned actual native build receipt differs')
 builder=out/'builder';shutil.copytree(a.builder,builder,ignore=shutil.ignore_patterns('bin','obj'));builder_before=files(a.builder)
 native=builder/'Templates/monodroid-coreclr.c'
 anchor='    setenv ("DOTNET_CrashReportBeforeSignalChaining", "1", true);';patch_template(native,anchor,anchor+'\n'+NATIVE)
 patch_template(native,'    unsigned int rv;','    unsigned int rv = 255;')
 anchor='    coreclr_execute_assembly (coreclr_handle, coreclr_domainId, managed_argc, managed_argv, executable_path, &rv);'
 patch_template(native,anchor,'    int execute_hr = coreclr_execute_assembly (coreclr_handle, coreclr_domainId, managed_argc, managed_argv, executable_path, &rv);\n    printf("CORECLR_EXECUTE_HRESULT=0x%x;RUNECLR_EXIT=%u\\n",execute_hr,rv);\n    if (execute_hr != 0) return 255;\n'+FORWARD)
 anchor='    LOG_INFO ("coreclr_initialize returned 0x%x", rv);';patch_template(native,anchor,anchor+'\n    printf("CORECLR_INITIALIZE_HRESULT=0x%x\\n",rv);')
 anchor='        coreclr_shutdown (g_coreclr_handle, g_coreclr_domainId);';patch_template(native,anchor,'        int shutdown_hr = coreclr_shutdown (g_coreclr_handle, g_coreclr_domainId);\n        printf("CORECLR_SHUTDOWN_HRESULT=0x%x\\n",shutdown_hr);')
 patch_template(native,'        g_coreclr_handle = NULL;','        g_coreclr_handle = NULL;\n        g_coreclr_domainId = 0;')
 anchor='    for (int i = 0; i < g_mapped_files_count; ++i)\n    {\n        munmap (g_mapped_files[i], g_mapped_file_sizes[i]);\n    }'
 patch_template(native,anchor,anchor+'\n    g_mapped_files_count = 0;')
 java=builder/'Templates/MonoRunner.java';anchor='        int rv = initRuntime(filesDir, entryPointLibName, localDateTimeOffset);';patch_template(java,anchor,JAVA+'\n'+anchor)
 anchor='        int retcode = executeEntryPoint(entryPointLibName, argsToForward);'
 patch_template(java,anchor,anchor+'\n        // Complete native shutdown before publishing the instrumentation result.\n        freeNativeResources();')
 (out/'Directory.Build.props').write_text('<Project />\n');(out/'global.json').write_text(json.dumps({'sdk':{'version':'11.0.100-rc.1.26420.103','rollForward':'disable'}}))
 (app/'runtimeconfig.bin').write_bytes(b'\x00')
 name='RuneCLR_BatchBoundary_'+uuid.uuid4().hex[:12]
 proj='''<Project><UsingTask TaskName="AndroidAppBuilderTask" AssemblyFile="$(MSBuildThisFileDirectory)builder/bin/Release/net11.0/AndroidSmokeBuilder.dll"/><Target Name="Build"><AndroidAppBuilderTask AppDir="$(MSBuildThisFileDirectory)app" MainLibraryFileName="'''+BRIDGE_NAME+'''" RuntimeIdentifier="android-x64" RuntimeFlavor="CoreCLR" ProjectName="$(AndroidProjectName)" OutputDir="$(MSBuildThisFileDirectory)apk" AndroidSdk="$(AndroidSdk)" AndroidNdk="$(AndroidNdk)" RuntimeHeaders="$(MSBuildThisFileDirectory)headers/hosts;$(MSBuildThisFileDirectory)headers/native" BuildApiLevel="36" BuildToolsVersion="35.0.1" TargetApiLevel="35" MinApiLevel="24" StaticLinkedRuntime="false" ForceInterpreter="false" ForceAOT="false" StripDebugSymbols="false"/></Target></Project>'''
 (out/'package.proj').write_text(proj)
 e=clean_env();ar=a.android_root.resolve();sdk=ar/'sdk';ndk=sdk/'ndk/27.2.12479018';j=ar/'android-studio/jbr'
 e.update(JAVA_HOME=str(j),ANDROID_HOME=str(sdk),ANDROID_SDK_ROOT=str(sdk),ANDROID_NDK_ROOT=str(ndk),PATH=str(j/'bin')+';C:/Program Files/Microsoft Visual Studio/2022/Professional/Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja;'+e['PATH'])
 command([a.dotnet,'build','builder/builder.csproj','-c','Release'],out/'builder-build.log',e,out)
 command([a.dotnet,'msbuild','package.proj','/t:Build','/p:AndroidSdk='+str(sdk),'/p:AndroidNdk='+str(ndk),'/p:AndroidProjectName='+name,'/v:minimal'],out/'apk-build.log',e,out)
 require(files(a.builder)==builder_before,'Preserved official builder changed during APK compilation')
 apkfile=out/'apk/bin'/(name+'.apk');require(apkfile.is_file(),'Official builder did not produce APK')
 staged=files(app);packaged={};natives={};dexes={}
 require('BatchBoundary.Author.dll' not in staged and BRIDGE_NAME in staged,'Fresh trusted APK payload topology differs')
 with zipfile.ZipFile(apkfile) as z:
  require('assets/assets.zip' in z.namelist(),'Nested official assets missing')
  with zipfile.ZipFile(io.BytesIO(z.read('assets/assets.zip'))) as assets:
   for n in assets.namelist():
    if n.endswith('/'):continue
    require('/' not in n and not n.startswith('BatchBoundary.Author.'),'Author/operator material bundled')
    packaged[n]=hashlib.sha256(assets.read(n)).hexdigest()
  for n in z.namelist():
   if n.startswith('lib/') and n.endswith('.so'):
    require(n.startswith('lib/x86_64/'),'Non x64 APK native image');natives[n]=hashlib.sha256(z.read(n)).hexdigest();packaged[Path(n).name]=natives[n]
   if re.fullmatch(r'classes([2-9]|[1-9][0-9]+)\.dex',n):dexes[n]=hashlib.sha256(z.read(n)).hexdigest()
 for n,h in staged.items():
  if n.endswith('.dex'):
   require(sum(v==h for v in dexes.values())==1,'Crypto DEX must appear exactly once as classesN.dex');packaged[n]=h
  require(packaged.get(n)==h,'APK changed actual input: '+n)
 for key,native_name in (('native','libcoreclr.so'),('interpreter','libclrinterpreter.so'),('targetJit','libclrjit.so')):
  require(staged[native_name]==l['critical7'][key],'Staged actual runtime bytes differ '+native_name)
 corelib_rows=[r for r in l['files'] if r['path']=='managed/System.Private.CoreLib.dll']
 require(len(corelib_rows)==1 and corelib_rows[0]['inputSha256']==l['critical7']['corelib'],'R2R CoreLib input ownership differs')
 state={'success':True,'package':'net.dot.'+name,'apk':str(apkfile),'apkSha256':sha(apkfile),'appHashes':staged,'packagedHashes':packaged,'apkNativeHashes':natives,'apkDexHashes':dexes,'runtimeCommit':COMMIT,'runtimeTree':TREE,'inputManifestSha256':sha(a.inputs/'input-manifest.json'),'inputFiles':load(a.inputs/'input-manifest.json')['files'],'layoutSha256':sha(out/'layout.json'),'buildReviewSha256':sha(out/'matching-build-review.json'),'builderOriginalHashes':builder_before,'builderGeneratedHashes':files(builder),'nativeSourceSha256':sha(native),'javaSourceSha256':sha(java),'driverSha256':sha(__file__),'createdUtc':utc(),'installed':False,'executionVerified':False}
 state.update(builderOriginalAfterHashes=files(a.builder),critical7=l['critical7'],corelibInputSha256=corelib_rows[0]['inputSha256'],corelibComponentSha256=staged['System.Private.CoreLib.dll'],sourceProofSha256=PROOF_SHA,nativeEntryProof=False,liveBatchPathVerified=False,performanceMeasured=False)
 write(out/'state.json',state);shutil.copy2(a.inputs/'input-manifest.json',out/'input-manifest.json');shutil.copy2(__file__,out/'driver.py');print('APK_BUILD_PASS',apkfile,flush=True)

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
 for n in ('author/BatchBoundary.Author.dll','author/BatchBoundary.Contract.dll'):
  require(sha(a.inputs/n)==m['files'][n],'Original author IL changed');target=produced/Path(n).name;shutil.copy2(a.inputs/n,target);push(a,s,target,n,out/'transfer-hash-reads.log')
 write(out/'postinstall-author.json',{'installedUtc':s['installedUtc'],'transferStartedUtc':started,'completedUtc':utc(),'apkSha256':s['apkSha256'],'source':'Unchanged frozen original author IL copied after install; no newly compiled author claim','files':{n:m['files'][n] for n in ('author/BatchBoundary.Author.dll','author/BatchBoundary.Contract.dll')}})
 s['authorHashes']={n:m['files'][n] for n in ('author/BatchBoundary.Author.dll','author/BatchBoundary.Contract.dll')};s['authorTransferredUtc']=utc();write(out/'state.json',s);print('INSTALL_TRANSFER_PASS',s['package'])

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

def lane(a,s,configured,matrix):
 root=a.output.resolve();nonce=uuid.uuid4().hex;out=root/('lane-'+str(configured)+'-'+str(matrix)+'-'+nonce);out.mkdir(exist_ok=False)
 result={'success':False,'platform':'Android.x64','configuredInterval':configured,'matrixInterval':matrix,'intervalHex':HEX[configured],'nonce':nonce,'appPid':None,'runtimeCommit':COMMIT,'runtimeTree':TREE,'timedOut':False,'debugger':False,'executionVerified':False,'nativeEntryProof':False,'liveBatchPathVerified':False,'performanceMeasured':False,'bundleUnchanged':False}
 for n in ('matching-build-review.json','layout.json','postinstall-author.json','input-manifest.json'):shutil.copy2(root/n,out/n)
 settings={'InterpMode':0,'RuneCLRInterpretCollectible':0,'ReadyToRun':1,'TieredCompilation':0,'InterpList':0,'RuneCLRPhaseAcquireLoad':1,'RuneCLRDerivedLedger':0,'RuneCLRBatchIntervalHex':HEX[configured]};result['settings']=settings
 try:
  appinfo=adb(a,['shell','dumpsys','package',s['package']])[0];(out/'package-before.txt').write_text(appinfo)
  match=re.search(r'(?m)^\s*(?:legacyNativeLibraryDir|nativeLibraryDir)=([^\s]+)',appinfo);require(match,'Installed native library path absent');native_dir=match.group(1)
  observed,code=adb(a,['shell','run-as',s['package'],'find',native_dir,'-name','libcoreclr.so'],False);paths=observed.splitlines() if code==0 else []
  require(len(paths)==1 and paths[0].startswith(native_dir+'/') and paths[0].endswith('/libcoreclr.so'),'Installed CoreCLR native path ambiguous/missing');native_dir=paths[0].rsplit('/',1)[0];(out/'native-path-query.txt').write_text(observed+'\n')
  before=inventory(a,s,out,'installed-before',native_dir);adb(a,['shell','am','force-stop',s['package']])
  args=[a.android_root/'sdk/platform-tools/adb.exe','-s',a.serial,'shell','am','instrument','-w','-e','env:RUNECLR_BATCH_NONCE',nonce,'-e','env:RUNECLR_BATCH_MATRIX',str(matrix),'-e','env:RUNECLR_BATCH_HEX',HEX[configured],s['package']+'/net.dot.MonoRunner']
  write(out/'request.json',{'command':list(map(str,args)),'startedUtc':utc(),'nonce':nonce,'configured':configured,'matrix':matrix,'commit':COMMIT,'tree':TREE,'deviceSerial':a.serial,'apkSha256':s['apkSha256'],'layoutSha256':s['layoutSha256'],'inputManifestSha256':s['inputManifestSha256'],'settings':settings})
  code,timed=command(args,out/'instrumentation.log',timeout=a.timeout,check=False);result.update(instrumentationExit=code,timedOut=timed)
  if timed:adb(a,['shell','am','force-stop',s['package']])
  for suffix in ('native.log','managed.log','managed-result.json','pid-query.txt','maps.log','boundary.json'):
   p=subprocess.run([str(a.android_root/'sdk/platform-tools/adb.exe'),'-s',a.serial,'exec-out','run-as',s['package'],'cat','files/batch-'+nonce+'.'+suffix],capture_output=True,timeout=60)
   (out/suffix).write_bytes(p.stdout);(out/(suffix+'.pull-stderr.log')).write_bytes(p.stderr);require(p.returncode==0,'Owned raw pull failed '+suffix)
  native=(out/'native.log').read_text(errors='replace');managed=load(out/'managed-result.json');pidquery=(out/'pid-query.txt').read_text().strip();receipt=load(out/'boundary.json')
  marker=r'(?m)^ANDROID_BATCH_NATIVE pid=([0-9]+) nonce=([0-9a-f]{32}) matrix='+str(matrix)+' interval='+HEX[configured]+r' PhaseAcquireLoad=1 DerivedLedger=0 InterpMode=0 ReadyToRun=1$'
  match=re.findall(marker,native);require(len(match)==1 and match[0][1]==nonce,'Unique actual native configuration header missing');pid=int(match[0][0]);result['appPid']=pid
  require(pidquery=='android.os.Process.myPid='+str(pid) and managed['appPid']==pid and managed['nonce']==nonce and managed['matrix']==str(matrix) and managed['interval']==HEX[configured],'Java/native/managed PID/nonce/config differs')
  instrumentation=(out/'instrumentation.log').read_text();require(code==0 and not timed and re.search(r'(?m)^INSTRUMENTATION_RESULT: return-code=0\r?$',instrumentation) and managed['exitCode']==0,'Instrumentation/managed completion failed')
  for marker in ('CORECLR_INITIALIZE_HRESULT=0x0','CORECLR_EXECUTE_HRESULT=0x0;RUNECLR_EXIT=0','CORECLR_SHUTDOWN_HRESULT=0x0'):
   require(len(re.findall(r'(?m)^'+re.escape(marker)+r'$',native))==1,'Missing/ambiguous actual CLR result '+marker)
  require(all(managed[k]==1 for k in ('policy','meter','terminal','gc')) and managed['defaultPolicy']==0,'Native capability acknowledgements differ')
  completion=f"BATCH_BOUNDARY_COMPLETE nonce={nonce} pid={pid} N={matrix} rows={len(receipt['rows'])}"
  managed_stream=(out/'managed.log').read_text();require(len(re.findall(r'(?m)^'+re.escape(completion)+r'$',managed_stream))==1 and len(re.findall(r'(?m)^'+re.escape(completion)+r'$',native))==1,'Original completed managed stream missing')
  maps=(out/'maps.log').read_text()
  for name in ('libcoreclr.so','libclrinterpreter.so','libclrjit.so'):
   actual=set(re.findall(r'(?m)(/[^\s]+/'+re.escape(name)+r')$',maps));require(actual=={native_dir+'/'+name},'Mapped critical native path differs '+name)
  review_path=Path(__file__).with_name('assess-mobile-batch-boundary.py');require(sha(review_path)==REVIEW_SHA,'Frozen lane reviewer differs');spec=importlib.util.spec_from_file_location('boundary_review',review_path);review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)
  rows=review.review_lane(receipt,configured,matrix,'Android.x64',s['authorHashes']['author/BatchBoundary.Author.dll'],pid,nonce)
  after=inventory(a,s,out,'installed-after',native_dir);require(before==after,'Installed bundle/author bytes changed')
  result.update(success=True,executionVerified=True,singleLaneSemanticsVerified=True,bundleUnchanged=True,rows=len(rows),collections=sum(r['Collected'] is True for r in rows),installedBeforeSha256=sha(out/'installed-before.json'),installedAfterSha256=sha(out/'installed-after.json'),boundaryReceiptSha256=sha(out/'boundary.json'),reviewerSha256=REVIEW_SHA,actualNativeRuntimeDirectory=native_dir,javaNativeManagedIdentityVerified=True,initializeExecuteShutdownZero=True)
 except Exception:result['error']=traceback.format_exc();adb(a,['shell','am','force-stop',s['package']],False);raise
 finally:result['rawHashes']=files(out);write(out/'mobile-run.json',result);print('LANE_RECEIPT',out/'mobile-run.json',flush=True)
 return result,out

def run(a):
 device(a);root=a.output.resolve();s=load(root/'state.json');require(s['installed'] and s.get('authorHashes') and sha(s['apk'])==s['apkSha256'],'Frozen installed state required')
 require(sha(__file__)==s['driverSha256'],'Frozen controller differs');inputs(a.inputs)
 summary={'success':False,'schema':'runeclr.android.batch-boundary.acceptance.v1','platform':'Android.x64','runtimeCommit':COMMIT,'runtimeTree':TREE,'apkSha256':s['apkSha256'],'layoutSha256':s['layoutSha256'],'inputManifestSha256':INPUT_SHA,'driverSha256':sha(__file__),'lanes':[],'executionVerified':False,'nativeEntryProof':False,'liveBatchPathVerified':False,'performanceMeasured':False,'physicalDeviceTouched':False}
 require(not (root/'matrix-results.json').exists(),'Do not replay an existing matrix attempt')
 try:
  for configured,matrix in LANES:
   result,out=lane(a,s,configured,matrix);summary['lanes'].append({'configured':configured,'matrix':matrix,'pid':result['appPid'],'nonce':result['nonce'],'rows':result['rows'],'collections':result['collections'],'receipt':out.name+'/mobile-run.json','receiptSha256':sha(out/'mobile-run.json')})
   write(root/'matrix-progress.json',summary)
  require(len(set(r['pid'] for r in summary['lanes']))==5 and len(set(r['nonce'] for r in summary['lanes']))==5,'Each lane must own a fresh process/nonce')
  require(sum(r['rows'] for r in summary['lanes'])==169 and sum(r['collections'] for r in summary['lanes'])==168,'Full expected169 rows/168 contexts not completed/collected')
  summary.update(success=True,executionVerified=True,singleWorkerFiveLanesVerified=True,totalRows=169,totalContexts=168,collections=168,endedUtc=utc());print('ANDROID_BATCH_BOUNDARY_MATRIX_PASS lanes5 rows169 contexts168 collections168',flush=True)
 except Exception:summary['error']=traceback.format_exc();raise
 finally:write(root/'matrix-results.json',summary)

def cleanup(a):
 root=a.output.resolve();s=load(root/'state.json');device(a);adb(a,['shell','am','force-stop',s['package']]);text,code=adb(a,['uninstall',s['package']]);require('Success' in text,'Owned fresh app uninstall failed');write(root/'cleanup.json',{'success':True,'package':s['package'],'serial':a.serial,'appUninstalled':True,'physicalDeviceTouched':False,'completedUtc':utc()})
 if a.shutdown:
  adb(a,['emu','kill']);write(root/'emulator-shutdown.json',{'requested':True,'serial':a.serial,'completedUtc':utc()})

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=('bridge','build','start','install','run','cleanup'))
 p.add_argument('--output',type=Path,required=True);p.add_argument('--layout',type=Path);p.add_argument('--runtime',type=Path);p.add_argument('--framework',type=Path);p.add_argument('--metadata-inspector',type=Path);p.add_argument('--inputs',type=Path)
 p.add_argument('--builder',type=Path,default=Path('D:/RuneCLR-Android/coreclr-smoke/run-20261012-172351/builder'));p.add_argument('--android-root',type=Path,default=Path('D:/RuneCLR-Android'));p.add_argument('--dotnet',type=Path,default=Path('E:/runtime/.dotnet/dotnet.exe'));p.add_argument('--serial',default='emulator-5556');p.add_argument('--timeout',type=int,default=900);p.add_argument('--shutdown',action='store_true');a=p.parse_args()
 try:{'bridge':bridge,'build':apk,'start':start,'install':install,'run':run,'cleanup':cleanup}[a.phase](a)
 except Exception:
  if a.output.exists():write(a.output/('phase-failure-'+a.phase+'-'+uuid.uuid4().hex+'.json'),{'error':traceback.format_exc(),'phase':a.phase,'executionVerified':False,'utc':utc()})
  raise

if __name__=='__main__':main()
