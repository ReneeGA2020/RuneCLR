#!/usr/bin/env python3
"""Build a fresh private device app without native rebuilds, signing or installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import shutil
import struct
import subprocess
import sys
import time
import traceback
import uuid

COMMIT = '3126bbc9a8851a09ac6435b18a12882bad48f3ee'
TREE = '710936ae1729a5689ab0e0896f3cf722ddd3d31c'
MANIFEST = 'ccf1ece09ef7d8f33a4da685234222526426f4712af1b1a5b2308de0dc97d685'
REVIEW = '02ec60b94821300e9f94bb3f84b7c209e29367c3ac521db6b9d942c95634ed11'
TRUSTED = ('RuneCLR.Abstractions.dll','RuneCLR.Packages.dll','RuneCLR.Runtime.dll','MobileHostBudgetProbe.dll')
AUTHOR = ('HostBudgetProbe.Payload.dll','HostBudgetProbe.Private.dll')
WRAPPERS = {
 'src/tasks/AppleAppBuilder/Templates/runtime-coreclr.m':'babc4168f0033156ada68e2d40225bb149f1c2050ee8f96bf91f9dfc565accd6',
 'src/tasks/AppleAppBuilder/Templates/util.m':'04d0cef6fc47277764a25171cc2282f47e3e992c77edb54491b9c4dfd1715439',
 'src/tasks/AppleAppBuilder/Templates/util.h':'ab22bf7549bf4f1f76c2501102e24a514b98a3d2cf238ecacd59e113ba399c5d',
 'src/tasks/AppleAppBuilder/Templates/runtime.h':'2df5fb08349dc5196d3803a3500fd21b1b60fbc848258ae306d8a18849d79ef6',
 'src/coreclr/hosts/inc/coreclrhost.h':'304545b7ea44b4aeb4318697c66ef4df5294c98e8c4135822e22cc1c1faf44f1',
 'src/native/corehost/host_runtime_contract.h':'7ae13b90115d10cead7095211375ee4042fd5054bc0b42682b7b8d52c8df2f7f'}
PROFILE = {'InterpMode':'0','RuneCLRInterpretCollectible':'0','ReadyToRun':'1',
 'TieredCompilation':'0','SYSTEM_GLOBALIZATION_INVARIANT':'1','InterpList':'0',
 'RuneCLRPhaseAcquireLoad':'1','RuneCLRDerivedLedger':'1','RuneCLRBatchInterval':'0'}
BRIDGE = '''using System; using MobileHostBudgetProbe;
public static class SessionBridge {
 public static int Run() {
  var d=Environment.GetEnvironmentVariable("RUNECLR_DOCUMENTS")??throw new InvalidOperationException("documents missing");
  var n=Environment.GetEnvironmentVariable("RUNECLR_BUDGET_NONCE")??throw new InvalidOperationException("nonce missing");
  return Entry.Run(new[]{d+"/budget-plugin",d+"/budget-evidence-"+n,n,"all"});
 }
}
'''
MAIN = '''#import <UIKit/UIKit.h>
#include "runtime.h"
@interface DeviceProbeDelegate : UIResponder <UIApplicationDelegate>
@property(strong,nonatomic) UIWindow *window;
@end
@implementation DeviceProbeDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
 self.window=[[UIWindow alloc] initWithFrame:[[UIScreen mainScreen] bounds]];
 UIViewController *view=[UIViewController new];
 self.window.rootViewController=view;
 UILabel *label=[[UILabel alloc] initWithFrame:[[UIScreen mainScreen] bounds]];
 label.text=@"RuneCLR device budget probe"; label.textAlignment=NSTextAlignmentCenter;
 [view.view addSubview:label]; [self.window makeKeyAndVisible];
 dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT,0), ^{mono_ios_runtime_init();});
 return YES;
}
@end
int main(int argc,char **argv) {
 @autoreleasepool {return UIApplicationMain(argc,argv,nil,NSStringFromClass([DeviceProbeDelegate class]));}
}
'''


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x',encoding='ascii') as stream:
        stream.write(json.dumps(value,indent=2)+'\n')


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())


def inventory(root):
    return {p.relative_to(root).as_posix():sha(p) for p in sorted(Path(root).rglob('*')) if p.is_file()}


def cap(argv):
    return subprocess.check_output(list(map(str,argv)),text=True).strip()


def managed(path):
    data=Path(path).read_bytes();u16=lambda at:struct.unpack_from('<H',data,at)[0];u32=lambda at:struct.unpack_from('<I',data,at)[0]
    need(data[:2]==b'MZ','Managed PE signature required')
    pe=u32(0x3c);opt=pe+24;dirs=opt+(112 if u16(opt)==0x20b else 96)
    sections=[opt+u16(pe+20)+40*i for i in range(u16(pe+6))]
    def offset(rva):
        for s in sections:
            if u32(s+12)<=rva<u32(s+12)+max(u32(s+8),u32(s+16)):return u32(s+20)+rva-u32(s+12)
        raise RuntimeError('Managed metadata RVA outside PE sections')
    cli=offset(u32(dirs+112));root=offset(u32(cli+8));need(data[root:root+4]==b'BSJB','Metadata root missing')
    at=root+16+((u32(root+12)+3)&~3);count=u16(at+2);at+=4;streams={}
    for _ in range(count):
        end=data.index(b'\0',at+8);streams[data[at+8:end].decode('ascii')]=u32(at);at=(end+4)&~3
    table=root+streams.get('#~',streams.get('#-'));flags=data[table+6];valid=struct.unpack_from('<Q',data,table+8)[0]
    row=table+24+4*bin(valid).count('1');strings=4 if flags&1 else 2;guids=4 if flags&2 else 2
    index=(u32 if guids==4 else u16)(row+2+strings);need(valid&1 and index>0,'Module MVID missing')
    start=root+streams['#GUID']+16*(index-1)
    return {'sha256':sha(path),'mvid':str(uuid.UUID(bytes_le=data[start:start+16])),
            'ilOnly':bool(u32(cli+16)&1),'managedNativeRva':u32(cli+64)}


def native(path,kind):
    data=Path(path).read_bytes();need(len(data)>=32 and struct.unpack_from('<II',data)==(0xfeedfacf,0x100000c),'Thin ARM64 device Mach-O required')
    need(struct.unpack_from('<I',data,12)[0]==kind,'Actual Mach-O filetype differs')
    count,length=struct.unpack_from('<II',data,16);cursor=32;versions=[];signatures=[];dependencies=[]
    for _ in range(count):
        need(cursor+8<=32+length<=len(data),'Native load-command header bounds')
        command,size=struct.unpack_from('<II',data,cursor);need(size>=8 and cursor+size<=32+length,'Native load-command bounds')
        if command==0x32:
            platform,minimum,sdk,tools=struct.unpack_from('<IIII',data,cursor+8);need(size==24+8*tools,'Build-version tool table differs')
            versions.append({'platform':platform,'minimum':minimum,'sdk':sdk})
        if command==0x1d:signatures.append(struct.unpack_from('<II',data,cursor+8))
        if command in (0xc,0x80000018,0x8000001f,0x80000023):
            start=cursor+struct.unpack_from('<I',data,cursor+8)[0];end=data.index(b'\0',start,cursor+size);dependencies.append(data[start:end].decode())
        cursor+=size
    need(cursor==32+length and len(versions)==1 and versions[0]['platform']==2 and versions[0]['minimum']<=983808,'Device platform2 minimum<=iOS15.3 required')
    need(not signatures,'Actual output contains LC_CODE_SIGNATURE; preserve signed-by-linker failure')
    return {'sha256':sha(path),'fileType':kind,'buildVersion':versions[0],'codeSignatures':signatures,'dependencies':dependencies}


def wrapper(source):
    text=Path(source).read_text()
    replacements={'//%APPLE_RUNTIME_IDENTIFIER%':'ios-arm64','%EnvVariables%':'',
        '%AppContextPropertyCount%':'6','%AppContextKeys%':'    appctx_keys[4]="NATIVE_DLL_SEARCH_DIRECTORIES";\n    appctx_keys[5]="System.Globalization.Invariant";',
        '%AppContextValues%':'    appctx_values[4]=bundle;\n    appctx_values[5]="true";', '%EntryPointLibName%':'SessionBridge.dll'}
    for old,new in replacements.items():
        need(text.count(old)==1,'Official wrapper substitution anchor differs: '+old);text=text.replace(old,new)
    settings='    const char *nonce=getenv("RUNECLR_BUDGET_NONCE");\n    if (!nonce || strlen(nonce)!=32) exit(124);\n    for(int i=0;i<32;i++) if (!isxdigit((unsigned char)nonce[i])) exit(124);\n'
    for key,value in PROFILE.items():
        settings+='    unsetenv("COMPlus_'+key+'"); setenv("DOTNET_'+key+'","'+value+'",1);\n'
    settings+='    unsetenv("DOTNET_InterpDump"); unsetenv("COMPlus_InterpDump");\n    setenv("RUNECLR_DOCUMENTS",[NSSearchPathForDirectoriesInDomains(NSDocumentDirectory,NSUserDomainMask,YES)[0] UTF8String],1);\n    printf("DEVICE_APP_NATIVE pid=%d nonce=%s PhaseAcquireLoad=1 DerivedLedger=1 BatchInterval=0 InterpMode=0 InterpretCollectible=0 ReadyToRun=1\\n",getpid(),nonce); fflush(stdout);\n'
    anchor='    char **managed_argv;';need(text.count(anchor)==1,'Native before-initialize anchor differs');text=text.replace(anchor,settings+anchor)
    anchor='    assert (res == 0);';need(text.count(anchor)==1,'Native initialize result anchor differs')
    text=text.replace(anchor,'    printf("DEVICE_APP_INITIALIZE pid=%d nonce=%s hr=%d\\n",getpid(),nonce,res); fflush(stdout);\n    if(res!=0) exit(126);')
    anchor='    coreclr_execute_assembly (coreclr_handle, coreclr_domainId, argi - 1, managed_argv + 1, path, &res);'
    need(text.count(anchor)==1,'Official managed invocation anchor differs')
    text=text.replace(anchor,'''    int (*managed_run)(void)=NULL;
    int hr=coreclr_create_delegate(coreclr_handle,coreclr_domainId,"SessionBridge","SessionBridge","Run",(void**)&managed_run);
    printf("DEVICE_APP_CREATE_DELEGATE pid=%d nonce=%s hr=%d\\n",getpid(),nonce,hr); fflush(stdout);
    if(hr!=0 || managed_run==NULL) exit(125);
    res=managed_run();
    printf("DEVICE_APP_INVOKE pid=%d nonce=%s managedExit=%d\\n",getpid(),nonce,res); fflush(stdout);''')
    anchor='    exit (res);';need(text.count(anchor)==1,'Official exit anchor differs')
    text=text.replace(anchor,'    printf("DEVICE_APP_SHUTDOWN pid=%d nonce=%s attempted=false reason=template-exit-path\\n",getpid(),nonce);\n    printf("DEVICE_APP_EXIT pid=%d nonce=%s managedExit=%d actualExit=%d\\n",getpid(),nonce,res,res); fflush(stdout);\n'+anchor)
    need(not re.search(r'%[A-Za-z][A-Za-z0-9]*%',text),'Unexpanded runtime template placeholder')
    return '#include <ctype.h>\n#include <unistd.h>\n#include <assert.h>\n#include <limits.h>\n'+text


def stage(out,label,argv,env,source):
    argv=list(map(str,argv));write(out/(label+'.request.json'),{'argv':argv,'cwd':str(source),'startedUtc':utc()})
    with (out/(label+'.stdout')).open('x') as stdout,(out/(label+'.stderr')).open('x') as stderr:
        child=subprocess.Popen(argv,cwd=source,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
        write(out/(label+'.process.json'),{'pid':child.pid,'driverPid':os.getpid(),'argv':argv})
        timed_out=False
        try:
            code=child.wait(timeout=1200)
        except subprocess.TimeoutExpired:
            timed_out=True
            # The stage owns a process group; retire it before hashing its streams.
            os.killpg(child.pid,signal.SIGTERM)
            try:
                code=child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGKILL);code=child.wait(timeout=10)
            try:
                os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:
                pass
    write(out/(label+'.result.json'),{'exitCode':code,'timedOut':timed_out,'endedUtc':utc(),'stdoutSha256':sha(out/(label+'.stdout')),'stderrSha256':sha(out/(label+'.stderr'))})
    need(code==0 and not timed_out,label+' failed; original attempt retained')


def sources(out,source):
    for relative,expected in WRAPPERS.items():
        path=source/relative;need(sha(path)==expected,'Frozen matching LF wrapper source changed: '+relative)
        if path.name!='runtime-coreclr.m':shutil.copyfile(path,out/path.name)
    (out/'runtime.m').write_text(wrapper(source/'src/tasks/AppleAppBuilder/Templates/runtime-coreclr.m'),encoding='ascii')
    (out/'main.m').write_text(MAIN,encoding='ascii');(out/'SessionBridge.cs').write_text(BRIDGE,encoding='ascii')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('phase',choices=('plan','build'))
    for name in ('root','runtime','native-build','framework','framework-review','inputs','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--build-slot-granted',action='store_true');args=parser.parse_args()
    out=args.output.resolve();need(not out.exists(),'Fresh output required; retain original products')
    manifest=read(args.inputs/'input-manifest.json');need(sha(args.inputs/'input-manifest.json')==MANIFEST,'Frozen host manifest differs')
    trusted={name:manifest['files']['trusted/'+name] for name in TRUSTED}
    for name,digest in trusted.items():need(sha(args.inputs/'trusted'/name)==digest,'Frozen trusted IL differs: '+name)
    need(sha(args.framework_review)==REVIEW and read(args.framework_review)['passed'],'Independent accepted framework review required')
    framework_result=read(args.framework/'results.json');framework_inventory=read(args.framework/'input-inventory.json')
    need(framework_result['success'] and framework_result['sourceCommit']==COMMIT and framework_result['sourceTree']==TREE and framework_result['target']=='ios.arm64','Matching device framework required')
    need(sha(args.framework/'input-inventory.json')==framework_result['inputInventorySha256'],'Framework inventory binding differs')
    for name,digest in framework_inventory['compositeInputs'].items():need(sha(args.framework/'input'/name)==digest,'Raw framework input differs: '+name)
    for name,digest in framework_inventory['layout'].items():need(sha(args.framework/'layout'/name)==digest,'Accepted framework layout differs: '+name)
    need(len(framework_inventory['compositeInputs'])==181 and not set(TRUSTED)&set(framework_inventory['compositeInputs']),'Expected181 framework-only raw inputs')
    native_receipt=read(args.native_build/'results.json')
    native_files=sorted(p.name for p in (args.framework/'layout').glob('*.dylib') if p.name!='framework.dylib')
    need(len(native_files)==9 and 'libcoreclr.dylib' in native_files,'Expected nine device runtime/diagnostic/shim libraries')
    for name in native_files:native(args.framework/'layout'/name,6)
    out.mkdir(parents=True);sources(out,args.runtime)
    app=out/'app/Session.app';fresh=out/'input';sdk=args.runtime/'.dotnet/dotnet'
    csc=args.runtime/'.dotnet/sdk/11.0.100-rc.1.26420.103/Roslyn/bincore/csc.dll'
    raw_names=sorted(list(framework_inventory['compositeInputs'])+list(TRUSTED));bridge=out/'SessionBridge.dll'
    compile_argv=[sdk,csc,'-nologo','-noconfig','-nostdlib+','-optimize+','-deterministic+','-target:library','-out:'+str(bridge)]+['-r:'+str(fresh/name) for name in raw_names]+[out/'SessionBridge.cs']
    options=['--targetos:ios','--targetarch:arm64','--obj-format:macho','--composite','--inputbubble','--parallelism:2','--resilient','--optimize','--out:'+str(app/'framework.dylib')]
    rsp=out/'crossgen.rsp';rsp.write_text('\n'.join(options+[str(fresh/name) for name in sorted(raw_names+['SessionBridge.dll'])])+'\n')
    commands={'bridge':list(map(str,compile_argv)),'crossgen':[native_receipt['crossgen2'],'@'+str(rsp)],
        'composite-link':['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios15.3','-dynamiclib',str(out/'framework.o'),'-Wl,-install_name,@rpath/framework.dylib','-o',str(app/'framework.dylib')],
        'wrapper':['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios15.3','-fobjc-arc','-DINVARIANT_GLOBALIZATION=1','-I'+str(out),str(out/'main.m'),str(out/'runtime.m'),str(out/'util.m'),'-L'+str(app),'-lcoreclr','-framework','UIKit','-framework','Foundation','-Wl,-rpath,@executable_path','-o',str(app/'Session')]}
    request={'schema':'runeclr.ios-device.application-build.v1','sourceCommit':COMMIT,'sourceTree':TREE,'startedUtc':utc(),
        'frameworkDirectory':str(args.framework),'frameworkResultSha256':sha(args.framework/'results.json'),'frameworkReviewSha256':REVIEW,
        'frameworkInventorySha256':sha(args.framework/'input-inventory.json'),'nativeBuildReceiptSha256':sha(args.native_build/'results.json'),
        'inputManifestSha256':MANIFEST,'trustedRawHashes':trusted,'wrapperSourceHashes':WRAPPERS,
        'generatedSourceHashes':{name:sha(out/name) for name in ('SessionBridge.cs','runtime.m','main.m')},
        'nativeFiles':native_files,'configuration':PROFILE,'commands':commands,'driverSha256':sha(__file__),
        'expectedCaseCount':15,'expectedContextCount':73,'nativeRebuildRequested':False,'codesignRequested':False,
        'physicalDeviceOperationsRequested':False,'frameworkLayoutBeforeHashes':framework_inventory['layout']}
    write(out/'request.json',request);shutil.copyfile(__file__,out/'driver.py')
    if args.phase=='plan':
        write(out/'results.json',{'passed':True,'applicationBuilt':False,'physicalDeviceExecuted':False,'plannedCommands':commands});print('PLAN PASS',out);return 0
    need(sys.platform=='darwin' and args.build_slot_granted,'Actual build requires exclusive configured Mac slot')
    need(out.parent==args.root.resolve(),'Build output must be a fresh private experiment sibling')
    source=args.runtime.resolve();need(cap(['git','-C',source,'rev-parse','HEAD'])==COMMIT and cap(['git','-C',source,'rev-parse','HEAD^{tree}'])==TREE and not cap(['git','-C',source,'status','--porcelain','--untracked-files=no']),'Matching source must be tracked clean')
    critical=read(args.framework/'request.json')['criticalBefore']
    need(all(sha(Path(name))==digest for name,digest in critical.items()),'Accepted runtime-critical files changed before application build')
    need(cap([sdk,'--version'])=='11.0.100-rc.1.26420.103','Frozen private compiler SDK differs')
    result={'schema':'runeclr.ios-device.application-build.v1','success':False,'applicationBuilt':False,'sourceCommit':COMMIT,
        'sourceTree':TREE,'appDirectory':str(app),'target':'ios.arm64','configuration':'Release','nativeEntryProof':False,
        'physicalDeviceExecuted':False,'signingChanged':False,'nativeRebuilt':False,'expectedCaseCount':15,'expectedContextCount':73}
    env={key:value for key,value in os.environ.items() if not key.startswith(('DOTNET_','COMPlus_','RUNECLR_','DYLD_','LD_'))
        and key not in ('SDKROOT','CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','OBJC_INCLUDE_PATH','LIBRARY_PATH','EXTRA_CFLAGS','EXTRA_CXXFLAGS','EXTRA_LDFLAGS')}
    env.update(DOTNET_CLI_HOME=str(out/'dotnet-home'),DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',DOTNET_CLI_USE_MSBUILD_SERVER='0')
    try:
        app.mkdir(parents=True);fresh.mkdir()
        for name in framework_inventory['compositeInputs']:shutil.copyfile(args.framework/'input'/name,fresh/name)
        for name in TRUSTED:shutil.copyfile(args.inputs/'trusted'/name,fresh/name)
        for name in native_files:shutil.copyfile(args.framework/'layout'/name,app/name)
        shutil.copyfile(args.framework/'layout/Microsoft.NETCore.App.deps.json',app/'Microsoft.NETCore.App.deps.json')
        (app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'org.runeclr.deviceprobe','CFBundleExecutable':'Session',
            'CFBundleName':'RuneCLR Device Probe','CFBundleInfoDictionaryVersion':'6.0','CFBundlePackageType':'APPL','CFBundleVersion':'1',
            'CFBundleShortVersionString':'1.0','LSRequiresIPhoneOS':True,'CFBundleSupportedPlatforms':['iPhoneOS'],
            'MinimumOSVersion':'15.3','UIDeviceFamily':[1,2],'UIFileSharingEnabled':True,'LSSupportsOpeningDocumentsInPlace':True,
            'UILaunchScreen':{},'UISupportedInterfaceOrientations':['UIInterfaceOrientationPortrait']}))
        stage(out,'bridge',commands['bridge'],env,source);shutil.copyfile(bridge,fresh/'SessionBridge.dll')
        write(out/'raw-inputs.json',inventory(fresh))
        stage(out,'crossgen',commands['crossgen'],env,source);shutil.copyfile(app/'framework.dylib',out/'framework.o')
        stage(out,'composite-link',commands['composite-link'],env,source);stage(out,'wrapper',commands['wrapper'],env,source)
        components={}
        for name in sorted(raw_names+['SessionBridge.dll']):
            before,after=managed(fresh/name),managed(app/name)
            need(before['managedNativeRva']==0 and after['managedNativeRva']!=0 and before['mvid']==after['mvid'],'Raw/R2R component identity differs: '+name)
            components[name]={'raw':before,'component':after}
        native_outputs={p.name:native(p,2 if p.name=='Session' else 6) for p in [app/'Session',*sorted(app.glob('*.dylib'))]}
        need(native_outputs['Session']['buildVersion']['minimum']==983808 and native_outputs['framework.dylib']['buildVersion']['minimum']==983808,'Executable/composite must have iOS15.3 minimum')
        for row in native_outputs.values():
            for dependency in row['dependencies']:
                if dependency.startswith(('@rpath/','@executable_path/')):need((app/Path(dependency).name).is_file(),'Private dylib dependency absent: '+dependency)
                else:need(dependency.startswith(('/System/Library/','/usr/lib/')),'Unexpected external native dependency: '+dependency)
        for name in AUTHOR:need(not list(app.rglob(name)),'Author IL entered preinstall bundle')
        need(sha(app/'libcoreclr.dylib')==native_receipt['nativeSha256'],'Matching private runtime native hash changed')
        write(out/'component-identities.json',components);write(out/'native-layout.json',native_outputs)
        write(out/'bundle-inventory.json',inventory(app));write(out/'state.json',{'app':str(app),'bundleId':'org.runeclr.deviceprobe','mode':0,'diagnostic':0,'readyToRun':1,'phaseAcquireLoad':1,'derivedLedger':1,'batchInterval':0,'executionVerified':False})
        result.update(success=True,applicationBuilt=True,bundleInventorySha256=sha(out/'bundle-inventory.json'),
            componentIdentitiesSha256=sha(out/'component-identities.json'),nativeLayoutSha256=sha(out/'native-layout.json'),
            actualManagedComponentCount=len(components),actualNativeFileCount=len(native_outputs),nativeUnsigned=True)
    except Exception as error:
        result['error']=str(error);(out/'driver-failure.txt').write_text(traceback.format_exc())
    finally:
        result.update(endedUtc=utc(),sourceTrackedClean=not cap(['git','-C',source,'status','--porcelain','--untracked-files=no']),
            runtimeCriticalUnchanged=all(sha(Path(name))==digest for name,digest in critical.items()),
            frameworkLayoutUnchanged=inventory(args.framework/'layout')==framework_inventory['layout'])
        result['success']=result['success'] and result['sourceTrackedClean'] and result['runtimeCriticalUnchanged'] and result['frameworkLayoutUnchanged']
        write(out/'results.json',result);print(json.dumps(result,indent=2))
    return 0 if result['success'] else 1


if __name__=='__main__':
    raise SystemExit(main())
