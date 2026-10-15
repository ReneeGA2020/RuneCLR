#!/usr/bin/env python3
"""Independently test fresh fixed author compilation and finite stock lifecycle only."""
import argparse, ast, bisect, hashlib, importlib.util, json, os, pathlib, plistlib, shutil, struct, subprocess, sys, uuid
ROOT=pathlib.Path(__file__).resolve().parent.parent
DRIVER=ROOT/'eng/prepare-ios-device-author.py'
DRIVER_SHA='8bdf9a06b9b0236018300e0fb0c2bac7148a35de10403e84835d27595d62cf58'
INPUTS=ROOT/'artifacts/host-budget/mobile-inputs-20261013-attempt1'
SDK=ROOT/'artifacts/toolchains/dotnet-11-rc1'
REFS=SDK/'packs/Microsoft.NETCore.App.Ref/11.0.0-rc.1.26425.128/ref/net11.0'
STOCK=ROOT/'artifacts/host-budget/fixture-stock-20261013-attempt1'
PRIOR=pathlib.Path('D:/RuneCLR-Android/device-build/fresh-author-sanity-20261015-attempt1')
CHECKS=[]
def need(value,message):
    if not value:raise RuntimeError(message)
    CHECKS.append(message)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='ascii')
def load_driver():
    need(sha(DRIVER)==DRIVER_SHA,'Frozen actual author preparation driver')
    spec=importlib.util.spec_from_file_location('fixed_author',DRIVER);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def pe_methods(p):
    d=p.read_bytes();u16=lambda a:struct.unpack_from('<H',d,a)[0];u32=lambda a:struct.unpack_from('<I',d,a)[0]
    pe=u32(0x3c);opt=pe+24;dirs=opt+(112 if u16(opt)==0x20b else 96);sections=opt+u16(pe+20)
    def offset(rva):
        for i in range(u16(pe+6)):
            size,start,rawsize,raw=struct.unpack_from('<IIII',d,sections+40*i+8)
            if start<=rva<start+max(size,rawsize):return raw+rva-start
        raise RuntimeError('PE unmapped RVA')
    cli=offset(u32(dirs+14*8));root=offset(u32(cli+8));need(d[root:root+4]==b'BSJB','PE CLI metadata signature')
    at=root+16+((u32(root+12)+3)&~3);n=u16(at+2);at+=4;streams={}
    for _ in range(n):
        end=d.index(b'\0',at+8);streams[d[at+8:end].decode('ascii')]=root+u32(at);at=(end+4)&~3
    table=streams.get('#~',streams.get('#-'));heap=d[table+6];valid=struct.unpack_from('<Q',d,table+8)[0];at=table+24;rows={}
    for i in range(64):
        if valid&(1<<i):rows[i]=u32(at);at+=4
    S=4 if heap&1 else 2;G=4 if heap&2 else 2;B=4 if heap&4 else 2
    idx=lambda t:4 if rows.get(t,0)>=65536 else 2
    coded=lambda tabs,bits:4 if max(rows.get(t,0) for t in tabs)>=(1<<(16-bits)) else 2
    sizes={0:2+S+3*G,1:coded((0,26,35,1),2)+2*S,2:4+2*S+coded((2,1,27),2)+idx(4)+idx(6),3:idx(4),4:2+S+B,5:idx(6),6:8+S+B+idx(8)}
    get=lambda a,s:u32(a) if s==4 else u16(a)
    positions={};cursor=at
    sizes.update({7:idx(8),8:4+S,9:idx(2)+coded((2,1,27),2),10:coded((2,1,26,6,27),3)+S+B,11:2+coded((4,8,23),2)+B,12:coded((6,4,1,2,8,9,10,0,14,23,20,17,26,27,32,35,38,39,40,42,44,43),5)+coded((6,10),3)+B,13:coded((4,8),1)+B,14:2+coded((2,6,32),2)+B,15:6+idx(2),16:4+idx(4),17:B,18:idx(2)+idx(20),19:idx(20),20:2+S+coded((2,1,27),2),21:idx(2)+idx(23),22:idx(23),23:2+S+B,24:2+idx(6)+coded((20,23),1),25:idx(2)+2*coded((6,10),1),26:S,27:B,28:2+coded((4,6),1)+S+idx(26),29:4+idx(4),30:8,31:4,32:16+B+2*S,33:4,34:12,35:12+2*B+2*S,36:4+idx(35),37:12+idx(35),38:4+S+B,39:8+2*S+coded((38,35,39),2),40:8+S+coded((38,35,39),2),41:2*idx(2)})
    for i in range(42):positions[i]=cursor;cursor+=rows.get(i,0)*sizes[i]
    module=positions[0];guididx=get(module+2+S,G);mvid=str(uuid.UUID(bytes_le=d[streams['#GUID']+16*(guididx-1):streams['#GUID']+16*guididx]))
    def string(index):
        start=streams['#Strings']+index;return d[start:d.index(b'\0',start)].decode('utf-8')
    def blob(index):
        start=streams['#Blob']+index;x=d[start]
        if x<128:length=x;header=1
        elif x<192:length=((x&63)<<8)|d[start+1];header=2
        else:length=((x&31)<<24)|(d[start+1]<<16)|(d[start+2]<<8)|d[start+3];header=4
        return d[start+header:start+header+length].hex().upper()
    types=[]
    for i in range(rows.get(2,0)):
        a=positions[2]+i*sizes[2];name=string(get(a+4,S));ns=string(get(a+4+S,S));first=get(a+sizes[2]-idx(6),idx(6));types.append((ns+'.'+name if ns else name,first))
    nested={}
    for i in range(rows.get(41,0)):
        a=positions[41]+i*sizes[41];nested[get(a,idx(2))]=get(a+idx(2),idx(2))
    def qualified(tid):
        return qualified(nested[tid])+'+'+types[tid-1][0] if tid in nested else types[tid-1][0]
    types=[(qualified(i+1),v[1]) for i,v in enumerate(types)]
    native_entries={}
    for i in range(rows.get(28,0)):
        a=positions[28]+i*sizes[28];member=get(a+2,coded((4,6),1))
        if member&1:native_entries[member>>1]=string(get(a+2+coded((4,6),1),S))
    starts=[v[1] for v in types]
    methods={}
    for i in range(rows.get(6,0)):
        a=positions[6]+i*sizes[6];owner_index=bisect.bisect_right(starts,i+1)-1;owners=[types[owner_index][0]] if owner_index>=0 else []
        need(len(owners)==1,'MethodDef owner maps uniquely')
        methods['0x%08x'%(0x06000001+i)]={'owner':owners[0],'name':string(get(a+8,S)),'flags':u16(a+6),'nativeEntry':native_entries.get(i+1,''),'signatureHex':blob(get(a+8+S,B))}
    refs=[]
    for i in range(rows.get(35,0)):
        a=positions[35]+i*sizes[35]
        refs.append({'name':string(get(a+12+B,S)),'version':list(struct.unpack_from('<4H',d,a)),'culture':string(get(a+12+B+S,S)),'publicKeyTokenHex':blob(get(a+12,B))})
    return {'sha256':sha(p),'moduleVersionId':mvid,'managedNativeRva':u32(cli+64),'managedNativeSize':u32(cli+68),'ilOnly':bool(u32(cli+16)&1),'methods':methods,'references':refs}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=pathlib.Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(__file__,out/'driver.py')
    env={k:v for k,v in os.environ.items() if not k.startswith(('DOTNET_','COMPlus_','RUNECLR_'))}
    processes=[]
    def process(label,argv,timeout=120):
        completed=subprocess.run([str(a) for a in argv],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=timeout)
        (out/(label+'.stdout')).write_bytes(completed.stdout);(out/(label+'.stderr')).write_bytes(completed.stderr)
        row={'argv':[str(a) for a in argv],'exitCode':completed.returncode,
             'stdoutSha256':sha(out/(label+'.stdout')),'stderrSha256':sha(out/(label+'.stderr'))}
        processes.append(row);write(out/(label+'.process.json'),row);return completed
    driver=load_driver()
    stock_inventory=read(STOCK/'managed-identity.json')
    for path,digest in stock_inventory.items():need(sha(pathlib.Path(path)).lower()==digest.lower(),'Frozen stock artifact '+path)
    inputs_before={p.relative_to(INPUTS).as_posix():sha(p) for p in INPUTS.rglob('*') if p.is_file()}
    second=out/'second-compile'
    compiled=process('fresh-compile',[sys.executable,DRIVER,'sanity','--inputs',INPUTS,'--sdk',SDK,'--refs',REFS,'--output',second])
    need(compiled.returncode==0,'Second real fixed-source compilation exits zero')
    previous_request=read(PRIOR/'request.json');request=read(second/'request.json')
    previous_results=read(PRIOR/'results.json');results=read(second/'results.json')
    need(previous_results['passed'] and results['passed'] and previous_request['nonce']!=request['nonce'],'Two passing compilations with distinct nonce')
    need(previous_request['sourceHashes']==request['sourceHashes'],'Fixed source hashes identical across compilations')
    need(previous_request['referenceHashes']==request['referenceHashes'] and previous_request['compilerSha256']==request['compilerSha256'] and previous_request['sdkHostSha256']==request['sdkHostSha256'],'Same explicit compiler and fixed references')
    need(not request['hostBundleHashes'] and not results['deviceHostBound'] and not results['postDeviceHostBuildCompiled'],'Sanity result accurately unbound to device host')
    author=[]
    manifest=read(INPUTS/'input-manifest.json')
    for role,filename in zip(('Private','Payload'),driver.AUTHOR):
        old=pe_methods(PRIOR/'plugin'/filename);new=pe_methods(second/'plugin'/filename)
        need(old['sha256']!=new['sha256'] and old['moduleVersionId']!=new['moduleVersionId'],'Fresh output hash and MVID differ '+role)
        need(new['ilOnly'] and new['managedNativeRva']==new['managedNativeSize']==0,'Actual author PE IL-only without R2R '+role)
        need(sha(second/'source'/(role+'.cs'))==request['sourceHashes'][role]==sha(PRIOR/'source'/(role+'.cs')),'Copied author source unchanged '+role)
        for folder in (PRIOR,second):
            receipt=read(folder/(role+'.process.json'))
            need(receipt['exitCode']==0 and receipt['responseSha256']==sha(folder/(role+'.rsp')) and receipt['stdoutSha256']==sha(folder/(role+'.stdout')) and receipt['stderrSha256']==sha(folder/(role+'.stderr')),'Raw compiler receipt/logs rechecked '+role)
        need(request['nonce'].encode() in (second/'plugin'/filename).read_bytes(),'Fresh nonce exists in actual assembly metadata '+role)
        author.append({k:new[k] for k in ('sha256','moduleVersionId','managedNativeRva','managedNativeSize','ilOnly','references')})
    private_refs=[r for r in author[1]['references'] if r['name']=='HostBudgetProbe.Private']
    need(len(private_refs)==1 and private_refs[0]['version']==[1,0,0,0] and not private_refs[0]['culture'] and not private_refs[0]['publicKeyTokenHex'],'Payload references declared private identity 1.0.0.0')
    nonce=uuid.uuid4().hex;lane=out/'stock-Normal'
    normal=process('stock-Normal',[SDK/'dotnet.exe',STOCK/'host/HostBudgetProbe.Host.dll',second/'plugin',lane,'Normal',nonce,'stock'])
    need(normal.returncode==0,'Fresh author Normal stock process exits zero')
    report=read(lane/'result.json');need(report['passed'] and report['nonce']==nonce and report['mode']=='stock' and report['scenario']=='Normal' and len(report['rows'])==20,'Actual stock Normal evidence bound to 20 sessions')
    for i,row in enumerate(report['rows'],1):
        r=row['report']
        need(row['session']==i and row['collected'] and r['Outcome']==0 and r['CompletedTicks']==3 and r['Error'] is None,'Normal completed and collected session '+str(i))
        need(r['Logs']==['start','static=1','tick=0','tick=1','tick=2','stop'],'Static state resets and exact callback logs session '+str(i))
        need(r['CreatedEntities']==r['ReleasedEntities']==1 and r['RemainingEntities']==0 and r['PrototypeBudget'] is None,'Resources released and stock reports no native budget')
    controls=[]
    def rejected(name,function,expected,synthetic=True):
        try:function()
        except RuntimeError as error:
            need(expected in str(error),'Expected rejection '+name)
            controls.append({'name':name,'synthetic':synthetic,'rejected':True,'error':str(error)})
            return
        raise RuntimeError('Negative control accepted: '+name)
    synthetic=out/'synthetic-controls';synthetic.mkdir()
    def fake_app(name):
        p=synthetic/name;p.mkdir();(p/'Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable':'Session','CFBundleSupportedPlatforms':['iPhoneOS']}));return p
    bundled=fake_app('author-already-bundled');(bundled/driver.AUTHOR[0]).write_bytes(b'synthetic author marker')
    rejected('author-already-bundled',lambda:driver.bundle(bundled),'Author already present')
    simulator=fake_app('platform7')
    (simulator/'Session').write_bytes(struct.pack('<8I',0xfeedfacf,0x100000c,0,2,1,24,0,0)+struct.pack('<6I',0x32,24,7,0x000f0300,0x001b0000,0))
    rejected('simulator-platform7',lambda:driver.bundle(simulator),'platform2/minimum15.3')
    bad_inputs=synthetic/'changed-manifest';bad_inputs.mkdir();(bad_inputs/'input-manifest.json').write_text('{}\n',encoding='ascii')
    changed=process('changed-manifest',[sys.executable,DRIVER,'sanity','--inputs',bad_inputs,'--sdk',SDK,'--refs',REFS,'--output',synthetic/'changed-manifest-output'])
    need(changed.returncode!=0 and 'Frozen host-budget input manifest changed' in read(synthetic/'changed-manifest-output/results.json')['error'],'Actual driver rejects modified frozen manifest before compilation')
    controls.append({'name':'frozen-manifest-changed','synthetic':True,'rejected':True,'subprocessExit':changed.returncode})
    # Normal declares the helper but never calls it; test corrupt dependency rejection separately.
    bad_plugin=synthetic/'corrupt-private';bad_plugin.mkdir()
    for filename in driver.AUTHOR:shutil.copy2(second/'plugin'/filename,bad_plugin/filename)
    (bad_plugin/driver.AUTHOR[0]).write_bytes(b'not a PE assembly')
    corrupt=process('corrupt-private-stock-Normal',[SDK/'dotnet.exe',STOCK/'host/HostBudgetProbe.Host.dll',bad_plugin,synthetic/'corrupt-private-evidence','Normal',uuid.uuid4().hex,'stock'])
    need(corrupt.returncode!=0 and b'BadImageFormatException' in corrupt.stderr,'Actual finite Normal control rejects corrupt declared dependency')
    controls.append({'name':'corrupt-declared-private','synthetic':True,'rejected':True,'subprocessExit':corrupt.returncode})
    for path,digest in stock_inventory.items():need(sha(pathlib.Path(path)).lower()==digest.lower(),'Frozen stock artifacts unchanged '+path)
    need(inputs_before=={p.relative_to(INPUTS).as_posix():sha(p) for p in INPUTS.rglob('*') if p.is_file()},'All frozen input source/manifest bytes unchanged')
    need(sha(DRIVER)==DRIVER_SHA,'Actual preparation driver remains frozen')
    review={'passed':True,'checksPassed':len(CHECKS),'driverSha256':DRIVER_SHA,'verificationDriverSha256':sha(pathlib.Path(__file__)),
            'compileCount':2,'firstCompile':str(PRIOR),'secondCompile':str(second),'authors':author,'normalSessions':20,'normalContextsCollected':20,
            'dependencyScope':'Payload AssemblyRef identity and declared dependency acceptance/rejection; Normal does not call Private.Helper.',
            'controls':controls,'rawProcesses':processes,'deviceHostBound':False,'physicalDeviceExecuted':False,'interpreterEntryProven':False,
            'scope':'Private Windows RC1 Roslyn sanity and fixed finite stock-host Normal regression only; no device application binding or runtime enforcement evidence.'}
    write(out/'review.json',review);write(out/'checked-assertions.json',CHECKS)
    print(json.dumps({'passed':True,'normalSessions':20,'collected':20,'controls':len(controls),'reviewSha256':sha(out/'review.json')}))

if __name__=='__main__':
    main()
