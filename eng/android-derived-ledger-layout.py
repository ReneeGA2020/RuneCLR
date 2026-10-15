#!/usr/bin/env python3
"""Rebuild Android trusted R2R components with reviewed budget critical products.

Reuses explicitly inventoried Android framework IL/OS libraries from the same
upstream base. It does not build a runtime, APK or execute target managed code.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import time
import traceback

BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
COMMIT = '2d86588f8cef4b3c48ce2ba4d4af15ad7bc83e7c'
TREE = '3292fc9acf3c15632f3bde34f675caec44f399e2'
OLD = '1724cdec553a7aff7a373a271a4be612651c7625'
REVIEW = '8831f2f0a7b094fffb0203b21a00c7a2533f23d7f57df3b480ab65dee625aa51'
METADATA = 'e9c7c090b721c130206b38794f365f3dba18de486d7fb1816d988fd941fcec77'
ZIP = 'acf7ac2b4eb61d34e18a0cbe76d7a0e2dcae8e4d4f54e40154587ffd7e06aba4'
PROOF = 'c860e8c483347c8b552b5128d7a5a28f6fe69bef4eb32a2426337a736fddca97'
LAYOUT_HELPER = '3ab977377032cca005a41b959fb21b2162c67dcc7658b44a1e43df85ca7d61eb'
FRAMEWORK_SHA = 'ac491a83b59ffd6d9abd396f2da3a415d4f171830e7c4b1af287e1948cfc86a3'
FRAMEWORK_INVENTORY_SHA = 'bb87538a5f80cecb6f6dbe82eee7f41a1e7f735929d42438d582d960f4fd013e'
MOBILE_MANIFEST_SHA = 'ccf1ece09ef7d8f33a4da685234222526426f4712af1b1a5b2308de0dc97d685'
INSPECTOR = '57934b53bc3665d3ad1b7f2def5acd084cdb0bf1d089f1f23a774d90d58aaaa6'
SANITIZE = ('CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','OBJC_INCLUDE_PATH',
            'LIBRARY_PATH','SDKROOT','MACOSX_DEPLOYMENT_TARGET','CMAKE_PREFIX_PATH','PKG_CONFIG_PATH')

def require(value, message):
    if not value: raise RuntimeError(message)

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): digest.update(block)
    return digest.hexdigest()

def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path, value): Path(path).write_text(json.dumps(value, indent=2)+'\n')
def utc(): return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
def cap(command): return subprocess.check_output(list(map(str,command)),text=True).strip()

def pe_native(path):
    data=Path(path).read_bytes(); pe=struct.unpack_from('<I',data,60)[0]
    require(data[pe:pe+4]==b'PE\0\0','Not PE: '+str(path))
    count=struct.unpack_from('<H',data,pe+6)[0]; size=struct.unpack_from('<H',data,pe+20)[0]
    opt=pe+24; dd=opt+(112 if struct.unpack_from('<H',data,opt)[0]==523 else 96)
    cli=struct.unpack_from('<I',data,dd+14*8)[0]
    for index in range(count):
        vs,va,rs,fo=struct.unpack_from('<IIII',data,opt+size+40*index+8)
        if va<=cli<va+max(vs,rs): return struct.unpack_from('<II',data,fo+cli-va+64)
    raise RuntimeError('CLI RVA not mapped: '+str(path))

def run(command,out,name,env):
    command=list(map(str,command));write(out/(name+'.request.json'),{'command':command,'startedUtc':utc()})
    with (out/(name+'.stdout.log')).open('w') as stdout,(out/(name+'.stderr.log')).open('w') as stderr:
        proc=subprocess.Popen(command,stdout=stdout,stderr=stderr,env=env)
        write(out/(name+'.process.json'),{'pid':proc.pid,'command':command,'startedUtc':utc()})
        try: code=proc.wait(timeout=900)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try: proc.wait(timeout=10)
            except subprocess.TimeoutExpired: proc.kill();proc.wait()
            write(out/(name+'.exit.json'),{'timeout':True,'exit':proc.returncode,'endedUtc':utc()})
            raise RuntimeError(name+' exceeded owned 900s timeout')
    write(out/(name+'.exit.json'),{'exit':code,'timeout':False,'endedUtc':utc()})
    require(code==0,name+' failed; raw logs preserved')

def layout_inventory(path):
    return {p.relative_to(path).as_posix():sha(p) for p in path.rglob('*') if p.is_file()}


def build(a):
    require(a.validate_only or a.build_slot_granted, 'Exclusive heavy-build slot required for composite compilation')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    result={'success':False,'executionVerified':False,'nativeEntryProof':False,'base':BASE,'commit':COMMIT,
            'tree':TREE,'target':'android.x64','nativeConfiguration':'Release','frameworkConfiguration':'Release',
            'frameworkReuseIsOriginalIL':True,'scope':'Fresh matching trusted R2R composite; no APK or device execution'}
    try:
        b=a.build.resolve();review=read(a.review/'results.json');metadata=read(a.metadata/'results.json')
        original=read(b/'results.json');request=read(b/'request.json');source=Path(request['source'])
        require(sha(a.review/'results.json')==REVIEW and sha(a.metadata/'results.json')==METADATA,'Reviewed receipts changed')
        require(review['success'] and metadata['success'] and original['success'] and review['buildExit']==0
                and metadata['originalBuildReceiptSha256']==sha(b/'results.json'), 'Successful native and metadata receipt binding absent')
        require(review['commit']==metadata['commit']==COMMIT and review['tree']==metadata['tree']==TREE,'Candidate identity changed')
        require(cap(['git','-C',source,'rev-parse','HEAD'])==COMMIT and cap(['git','-C',source,'rev-parse','HEAD^{tree}'])==TREE
                and not cap(['git','-C',source,'status','--porcelain','--untracked-files=no']),'Candidate source is not clean/matching')
        provenance=read(b/'source.json');proof=read(b/'source-proof.json')
        require(sha(b/'source-proof.json') == PROOF and metadata['sourceProofSha256'] == PROOF
                and proof['exactDerivedLedgerVerified'] and proof['oldMobileDeltaOnlyMeterConfig']
                and proof['phaseAndDerivedSwitchesIndependent'] and proof['phaseAcquireLoadDefaultOff']
                and proof['terminalDerivedLedgerDefaultOff'] and proof['sourceCommit'] == COMMIT
                and proof['tree'] == TREE and proof['layoutSize'] == 64 and proof['layoutAlignment'] == 8,
                'Exact default-OFF derived source proof differs')
        require(sha(a.metadata_inspector) == INSPECTOR and sha(a.layout_helper) == LAYOUT_HELPER,
                'Pinned metadata inspector/ELF helper differs')
        previous_layout = b.parent / 'android-budget-increment-layout-20261014-attempt1/layout'
        require(previous_layout.is_dir(), 'Preserved previous Android layout missing')
        preserved_layout = layout_inventory(previous_layout)
        require(len(preserved_layout) == 210, 'Expected complete previous layout200 plus receipt9 and descriptor')
        preserved_products = request['preservedFiles']
        require(all(sha(path) == value for path,value in preserved_products.items()), 'Preserved original products changed')
        source_hashes=provenance.get('sourceHashes',proof.get('sourceHashes',proof.get('files',{})))
        require(len(source_hashes)==37 and all(sha(source/n)==v for n,v in source_hashes.items()),'Exact source37 changed')
        critical=review['criticalHashes'];require(len(critical)==7 and all(sha(review[k])==v for k,v in critical.items()),'Critical7 changed')
        require(all(sha(path) == value for path,value in metadata['actualPeHashes'].items()), 'Reviewed retained PE bytes changed')
        require(sha(a.framework/'results.json') == FRAMEWORK_SHA and
                sha(a.framework/'input-inventory.json') == FRAMEWORK_INVENTORY_SHA,
                'Pinned original framework receipts differ')
        fw=read(a.framework/'results.json');inventory=read(a.framework/'input-inventory.json')
        require(fw['success'] and fw['base']==BASE and fw['commit']==OLD and fw['configuration']=='Release'
                and fw['target']=='android.x64' and sha(a.framework/'input-inventory.json')==fw['inputInventorySha256'],'Original Android IL receipt changed')
        libdiff=cap(['git','-C',source,'diff','--name-only',OLD,COMMIT,'--','src/libraries','src/native']).splitlines()
        require(libdiff==['src/libraries/System.Private.CoreLib/src/System/Runtime/Loader/AssemblyLoadContext.cs'],
                'Reused library/native sources differ beyond replaced CoreLib')
        for rows in inventory['groups'].values():
            for row in rows: require(sha(row['path'])==row['sha256'] and Path(row['path']).stat().st_size==row['size'],'Original framework input changed')
        require(sha(a.inputs/'input-manifest.json') == MOBILE_MANIFEST_SHA, 'Pinned trusted input manifest differs')
        m=read(a.inputs/'input-manifest.json');require(len(m['files'])==6 and m['expectedContexts']==73 and len(m['sourceHashes'])==30,'Mobile manifest topology differs')
        require(sha(a.inputs.parent/'mobile-host-budget-inputs.zip')==ZIP,'Mobile ZIP differs')
        require(all(sha(a.inputs/n)==v for n,v in m['files'].items()) and all(sha(a.inputs/'source'/n)==v for n,v in m['sourceHashes'].items()),'Mobile DLL/source inventory differs')
        require(len(inventory['groups']['framework'])==180 and all(pe_native(r['path'])==(0,0) for r in inventory['groups']['framework']),
                'Framework reuse must be complete original IL, not previous R2R components')
        ndk_receipt=read(a.toolchain/'results.json');ndk=Path(ndk_receipt['ndk'])
        require(ndk_receipt['success'] and sha(ndk/'build/cmake/android.toolchain.cmake')==ndk_receipt['toolchainSha256']
                and sha(a.toolchain/'results.json')==request['toolchainReceiptSha256'],'Pinned NDK changed')
        if a.validate_only:
            result.update(success=True, schema='runeclr.android.derived-ledger.layout-preflight.v1',
                  frameworkBuildPerformed=False, sourceTrackedClean=True, metadataVerified=True,
                  nativeBuildReceiptSha256=REVIEW, metadataReviewSha256=METADATA,
                  sourceProofSha256=PROOF, coreCritical7=critical, nativeMeterSize=64, nativeMeterAlignment=8,
                  previousLayoutFileCount=len(preserved_layout), previousLayoutHashes=preserved_layout,
                  preservedProducts=preserved_products, frameworkReceiptSha256=FRAMEWORK_SHA,
                  frameworkInventorySha256=FRAMEWORK_INVENTORY_SHA, mobileManifestSha256=MOBILE_MANIFEST_SHA,
                  actualReusedInputInventory=inventory, trustedInputs=m, helperSha256=sha(a.layout_helper),
                  driverSha256=sha(__file__), scope='Actual read-only layout prerequisites only; composite compilation not performed')
            write(out/'results.json', result)
            return
        input_dir=out/'input';input_dir.mkdir();layout=out/'layout' 
        for n in ('managed','native','java','headers','receipts'): (layout/n).mkdir(parents=True)
        reused=[]
        for row in inventory['groups']['framework']:
            p=Path(row['path'])
            if p.name=='System.Private.CoreLib.dll': continue
            shutil.copy2(p,input_dir/p.name);reused.append(row)
        shutil.copy2(review['corelib'],input_dir/'System.Private.CoreLib.dll')
        for name in m['trustedCompositeOnly']: shutil.copy2(a.inputs/name,input_dir/Path(name).name)
        inputs=sorted(input_dir.glob('*.dll'))
        require(len(inputs) == 185 and all(pe_native(p) == (0,0) for p in inputs),
                'Expected exact185 trusted IL inputs, without R2R bodies')
        require(not any(p.name.startswith('HostBudgetProbe.') for p in inputs),'Author IL entered trusted composite')
        opts=['--targetos:linux','--targetarch:x64','--composite','--inputbubble','--resilient','--optimize',
              '--parallelism:2','--out:'+str(layout/'managed/RuneCLR.Android.Framework.dll')]
        rsp=out/'crossgen.rsp';rsp.write_text('\n'.join(opts+[str(p) for p in inputs])+'\n')
        env=dict(os.environ);removed={n:env.pop(n) for n in SANITIZE if n in env}
        env['PATH']=str(b.parent/'tools/bin')+':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'
        write(out/'request.json',{'schema':'runeclr.android.derived-ledger.layout-build.v1','base':BASE,'commit':COMMIT,'tree':TREE,
              'buildReviewSha256':REVIEW,'metadataReviewSha256':METADATA,'originalBuildSha256':sha(b/'results.json'),
              'frameworkReceiptSha256':sha(a.framework/'results.json'),'frameworkInventorySha256':sha(a.framework/'input-inventory.json'),
              'reusedFrameworkSourceCommit':OLD,'reusedFrameworkSourceBase':BASE,'librarySourceDifference':libdiff,
              'critical7':critical,'mobileManifestSha256':sha(a.inputs/'input-manifest.json'),'mobileZipSha256':ZIP,
              'mobileFiles':m['files'],'mobileSourceHashes':m['sourceHashes'],'compositeInputHashes':{p.name:sha(p) for p in inputs},
              'command':[review['crossgen2'],'@'+str(rsp)],'rspSha256':sha(rsp),'removedProcessEnvironment':removed,
              'driverSha256':sha(__file__), 'layoutHelperSha256':LAYOUT_HELPER,
              'previousLayoutHashes':preserved_layout, 'preservedProducts':preserved_products,
              'nativeMeterSize':64, 'nativeMeterAlignment':8, 'phaseAcquireLoadDefaultOff':True,
              'derivedLedgerDefaultOff':True, 'heavyBuildSlotGranted':True,
              'startedUtc':utc(),'executionVerified':False})
        run([review['crossgen2'],'@'+str(rsp)],out,'crossgen',env)
        generated=sorted((layout/'managed').glob('*.dll'))
        require(len(generated) == 186 and {p.name for p in generated} ==
                {p.name for p in inputs} | {'RuneCLR.Android.Framework.dll'},
                'Expected exactly185 component images and one new composite')
        require(pe_native(layout/'managed/System.Private.CoreLib.dll')!=(0,0),'New CoreLib component has no R2R header')
        files=[]
        for p in generated:
            files.append({'path':p.relative_to(layout).as_posix(),'sha256':sha(p),'role':'corelib' if p.name=='System.Private.CoreLib.dll' else 'framework',
                          'sourceCommit':COMMIT,'inputSha256':sha(input_dir/p.name) if (input_dir/p.name).exists() else None,
                          'inputSourceCommit':COMMIT if p.name=='System.Private.CoreLib.dll' or p.name in [Path(n).name for n in m['trustedCompositeOnly']] else OLD,
                          'generatedByCriticalCrossgen2Sha256':critical['crossgen2'],'managedNativeHeader':pe_native(p)})
        def copy(p,relative,role,owner=COMMIT):
            p=Path(p);target=layout/relative;target.parent.mkdir(parents=True,exist_ok=True)
            require(not target.exists(),'Layout collision: '+relative);shutil.copy2(p,target)
            files.append({'path':relative,'sha256':sha(target),'role':role,'sourceCommit':owner,'sourceBase':BASE,
                          'reusedSameBase':owner==OLD,'sourcePath':str(p)})
        for key,name,role in [('native','libcoreclr.so','runtime'),('interpreter','libclrinterpreter.so','interpreter'),('targetJit','libclrjit.so','jit')]: copy(review[key],'native/'+name,role)
        for row in inventory['groups']['native']:
            p=Path(row['path'])
            if p.name in ('libcoreclr.so','libclrinterpreter.so','libclrjit.so'):continue
            if p.suffix=='.so':copy(p,'native/'+p.name,'os-native',OLD)
            elif p.suffix=='.dex':copy(p,'java/'+p.name,'android-java',OLD)
        for row in inventory['groups']['deps']:copy(row['path'],'managed/'+Path(row['path']).name,'framework',OLD)
        for src,dest in [('src/coreclr/hosts/inc/coreclrhost.h','headers/hosts/coreclrhost.h'),('src/native/corehost/host_runtime_contract.h','headers/native/corehost/host_runtime_contract.h')]:copy(source/src,dest,'header')
        spec=importlib.util.spec_from_file_location('elfhelper',a.layout_helper);helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        packaged={p.name:p for p in (layout/'native').glob('*.so')};queue=list(packaged.values());seen=set();dependencies=[]
        sysroot=ndk/'toolchains/llvm/prebuilt/darwin-x86_64/sysroot/usr/lib/x86_64-linux-android'
        while queue:
            p=queue.pop(0)
            if str(p) in seen:continue
            seen.add(str(p));image=helper.elf(p)
            for name in image['needed']:
                if name in packaged:target=packaged[name];disposition='packaged'
                elif name=='libc++_shared.so':
                    copy(sysroot/name,'native/'+name,'ndk-native',None);target=layout/'native'/name;packaged[name]=target;disposition='pinned-ndk'
                elif (sysroot/'24'/name).is_file():target=sysroot/'24'/name;disposition='android-system-api24'
                else:raise RuntimeError('Unresolved ELF dependency '+name)
                dependencies.append({'owner':p.name,'needed':name,'disposition':disposition,'sha256':sha(target),'path':str(target)});queue.append(target)
        require(all(sha(review[k])==v for k,v in critical.items()),'Crossgen modified critical7')
        metadata_command=[source/'.dotnet/dotnet','exec','--fx-version','11.0.0-rc.1.26420.103',a.metadata_inspector,
                          review['corelib'],review['corelib'],layout/'managed/System.Private.CoreLib.dll']
        run(metadata_command,out,'component-metadata',env)
        rows=read(out/'component-metadata.stdout.log');require(len(rows)==3,'Metadata inspector output count differs')
        require(rows[0]['methods']==rows[2]['methods'] and rows[0]['fields']==rows[2]['fields']
                and rows[0]['moduleVersionId']==rows[2]['moduleVersionId'],'New CoreLib component private ABI/MVID changed')
        receipts=[]
        for kind,p in [('native-build-review',a.review/'results.json'),('native-core-build',b/'results.json'),
                       ('corelib-metadata',a.metadata/'results.json'),('reused-framework-build',a.framework/'results.json'),
                       ('reused-framework-inventory',a.framework/'input-inventory.json'),('source',b/'source.json'),('source-proof',b/'source-proof.json'),
                       ('mobile-inputs',a.inputs/'input-manifest.json'),('toolchain',a.toolchain/'results.json')]:
            target=layout/'receipts'/(kind+'.json');shutil.copy2(p,target);receipts.append({'kind':kind,'path':target.relative_to(layout).as_posix(),'sha256':sha(target)})
        require(layout_inventory(previous_layout) == preserved_layout and
                all(sha(path) == value for path,value in preserved_products.items()),
                'Previous layouts/products changed during compilation')
        require(all(sha(source/n) == v for n,v in source_hashes.items()) and
                all(sha(path) == value for path,value in metadata['actualPeHashes'].items()),
                'Reviewed source/CoreLib/compiler mirror changed during compilation')
        require(all(sha(row['path']) == row['sha256'] and Path(row['path']).stat().st_size == row['size']
                for rows in inventory['groups'].values() for row in rows), 'Original IL/OS inputs changed')
        result.update(success=True,schema='runeclr.android.derived-ledger.layout.v1' ,configuration='Release',sourceTrackedClean=True,
                      features={'interpreter':True,'dynamicCodeCompiled':True},files=files,receipts=receipts,
                      reusedFrameworkSourceCommit=OLD,critical7=critical,buildReviewSha256=REVIEW,metadataReviewSha256=METADATA,
                      compositeFileCount=len(generated),compositeInputCount=len(inputs),allElfDependenciesResolved=True,
                      elfDependencies=dependencies,helperSha256=sha(a.layout_helper),metadataInspectorSha256=sha(a.metadata_inspector),
                      corelibComponentMetadataUnchanged=True,coreCriticalUnchanged=True,
                      previousLayoutFilesUnchanged=True, preservedProductCount=len(preserved_products),
                      nativeMeterSize=64, nativeMeterAlignment=8, phaseAcquireLoadDefaultOff=True,
                      derivedLedgerDefaultOff=True, layoutDriverSha256=sha(__file__), inputManifestSha256=sha(a.inputs/'input-manifest.json'),
                      inputFiles=m['files'],sourceProofSha256=sha(b/'source-proof.json'),sourceInputsVerified=30,expectedContexts=73,requestSha256=sha(out/'request.json'),endedUtc=utc())
        write(layout/'layout.json',result);write(out/'results.json',result)
    except Exception:
        result['error']=traceback.format_exc();result['endedUtc']=utc();write(out/'results.json',result);raise

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('build','review','metadata','framework','toolchain','inputs','layout-helper','metadata-inspector','output'):
        p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--validate-only', action='store_true', help='Read/hash prerequisites and freeze a receipt without compiling')
    p.add_argument('--build-slot-granted', action='store_true')
    build(p.parse_args())

if __name__=='__main__':main()
