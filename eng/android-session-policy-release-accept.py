#!/usr/bin/env python3
"""Run/assess an independent Android Release functional lane; no method-entry claim."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import time
import traceback
import uuid

VALUES = dict(zip(('PayloadStatic','PayloadConstructor','Property','Inlined','GenericStatic',
                  'GenericMethod','Delegate','Virtual','DefaultInterface','Filter','PrivateStatic',
                  'PrivateConstructor','PrivateProperty','PrivateInline','PrivateGenericStatic',
                  'PrivateGenericMethod','PrivateDelegate'), (1,1,7,12,1,19,11,13,17,1,1,1,30,38,1,41,42)))
COMMIT = '1724cdec553a7aff7a373a271a4be612651c7625'
LIFECYCLE = ('Repeated sessions reset map statics and unload', 'Map-defined exceptions do not retain the map', 'Caught cooperative budget violations still fail the session', 'Entity quota failures reclaim host resources', 'OnStop failures still reclaim resources and unload', 'Log quotas bound retained host messages', 'Invalid entry types fail without retaining the context', 'Manifest rejects entry paths outside the package', 'Invalid options are rejected before map execution', 'Required interpretation is acknowledged or rejected before loading author IL', 'Invalid execution policies fail before opening author files', 'Private dependency versions and generic statics remain session-local', 'Generic collections and constrained calls execute and unload', 'Manifest rejects a missing declared dependency', 'Manifest rejects dependency identity mismatches', 'Manifest rejects dependency paths outside the package', 'Manifest rejects dependency hash mismatches', 'Manifest rejects entry hash mismatches', 'Manifest rejects entries using contract or framework identities', 'Manifest rejects duplicate private assembly identities', 'Direct package construction cannot bypass dependency validation', 'Map references cannot bind a different declared private version', 'Map compiled after the host executes and unloads', 'Undeclared private dependencies cannot fall back to the default context')
PACKAGES = ('Source package executes, resets statics, cleans entities and unloads', 'Raw IL import executes with the same lifecycle', 'Source executes again with fresh static state', 'Author exception stops, releases entities and unloads', 'Valid package recovers after author failure', 'Tampered package fails integrity before execution', 'Rehashed forbidden entry fails capability admission', 'Valid package recovers after invalid entries', 'Private helper A executes with fresh ordinary and generic statics', 'Same-name private helper B binds its declared version', 'Private helper A executes again with fresh statics', 'Imported entry retains its declared private helper', 'Rehashed forbidden private helper fails capability admission', 'Valid private package recovers after forbidden dependency', 'Player default context contains no operator compiler assemblies')
LANES = ('required', 'all', 'required-refusal', 'ordinary', 'unmarked-fallback')


def check(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write(chr(10))


def evidence(directory):
    state = read(directory/'state.json')
    check(state['candidateCommit']==COMMIT and re.fullmatch(r'net\.dot\.RuneCLR_Session_[0-9a-f]{12}',state['package']), 'Unexpected frozen app/source')
    for name,key in [('original-layout.json','layoutReceiptSha256'),('product-manifest.json','productManifestSha256'),
                     ('host-inputs.json','hostReceiptSha256'),('payload-producer.json','payloadReceiptSha256'),('managed-identity.json','managedIdentitySha256')]:
        check(sha(directory/name)==state[key], 'Frozen receipt changed: '+name)
    product=read(directory/'product-manifest.json');layout=read(directory/'original-layout.json')
    check(product['commit']==layout['commit']==COMMIT and product['platform']=='android' and product['abi']=='x86_64', 'Product/source/ABI identity')
    check(product['configuration']=='Release' and layout['nativeConfiguration']==layout['frameworkConfiguration']=='Release', 'Fresh matching Release inputs required')
    check(layout['features']['interpreter'] and layout['features']['dynamicCodeCompiled'], 'Build feature evidence absent')
    check(sha(state['apk'])==state['apkSha256'], 'Frozen APK changed')
    for name,value in state['appHashes'].items():
        check(sha(directory/'app'/name)==value, 'Frozen player input changed: '+name)
    check(all(state['appHashes'].get(name)==value for name,value in product['artifactHashes'].items()),'Product/player exact artifact binding')
    payloads=[p for p in directory.glob('payloads-*') if p.is_dir()]
    check(len(payloads)==1 and len(state['payloadHashes'])==43, 'Frozen43 payloads required')
    producer=read(directory/'payload-producer.json')
    check(producer['files']==state['payloadHashes'] and producer['apkSha256']==state['apkSha256'] and
          producer['installedUtc']==state['installedUtc'] and producer['installedUtc']<producer['productionStartedUtc']<producer['completedUtc'], 'Post-install production binding absent')
    for name,value in state['payloadHashes'].items():
        check(sha(payloads[0]/name)==value, 'Frozen author input changed: '+name)
    identity=read(directory/'managed-identity.json')
    check(identity['files']==dict(state['currentHostHashes'],**state['payloadHashes']), 'Frozen host/payload managed identity binding')
    return state,product


def expected_device(state, product, native_dir):
    expected={'files/'+name:value for name,value in state['appHashes'].items() if not name.endswith('.so')}
    expected.update({'files/'+name:value for name,value in state['payloadHashes'].items()})
    for name,value in product['artifactHashes'].items():
        expected['files/'+name if name=='System.Private.CoreLib.dll' else native_dir+'/'+name]=value
    check(len(expected)==246, 'Frozen installed inventory must contain246 files')
    return expected


def parse_hashes(path):
    rows={}
    for line in path.read_text().splitlines():
        value,name=line.split(maxsplit=1)
        check(re.fullmatch('[0-9a-f]{64}',value) and name.strip() not in rows,'Malformed/duplicate device hash row')
        rows[name.strip()]=value
    return rows


def functional(lane, native, managed, jit):
    check(not re.search(r'(?m)^FAIL |^Cannot run map:',managed),'Managed failure marker')
    check(re.findall(r'^ANDROID_SESSION_POLICY (.*)$',managed,re.M)==['version=1 default=0 ordinary=0 required=1'],'Native bridge acknowledgement')
    result={'lane':lane,'functionalPassed':True,'entryProofCollected':False}
    if lane=='all':
        check(tuple(re.findall(r'^PASS (.*)$',managed,re.M))==LIFECYCLE+PACKAGES,'Exact ordered24 lifecycle and15 package individual results')
        check(re.findall(r'^24/24 tests passed$',managed,re.M)==['24/24 tests passed'] and
              re.findall(r'^15/15 package execution tests passed\.$',managed,re.M)==['15/15 package execution tests passed.'],'Production suite summaries')
        check(len(re.findall(r'^SESSION_EXECUTION_POLICY required-interpreter version=1$',managed,re.M))==3,'Three production native policy acknowledgements')
        sample=re.findall(r'^\[(hello|arena)\] Completed; ticks=3\n(.*?)(?=^\[|\Z)',managed,re.M|re.S)
        check([x[0] for x in sample]==['hello','arena','hello'],'Ordered three sample completions')
        hello=['  Hello map started; start-count=1','  Hello tick 0','  Hello tick 1','  Hello tick 2','  Hello map stopped',
               '  entities: created=1, released=1, remaining=0','  unload: collected']
        arena=['  Arena started','  Spawned entity 1','  Spawned entity 2','  Spawned entity 3','  Arena stopped',
               '  entities: created=3, released=3, remaining=0','  unload: collected']
        check(all(text.splitlines()==(hello if name=='hello' else arena) for name,text in sample),'Exact sample static reset/ticks/entities/collections')
        check(re.search(r'JIT compiled\s+RuneCLR\.Runtime\.MapRunner:Run\(',jit),'Trusted MapRunner Run native JIT positive')
        check(len(re.findall(r'^DEFAULT_DEPENDENCY_SEED collectible=false module=[0-9a-f-]+ token=0x[0-9a-f]{8}$',managed,re.M))==1 and
              re.search(r'JIT compiled\s+RuneCLR\.PrivateDependency\.PrivateState.*:Start',jit),'Trusted default dependency seed native JIT positive')
        check(not re.search(r'JIT compiled\s+\.?(?:RuneCLR\.(?:TestMaps|DependencyMap|LateMap|Samples)\.|(?:GameScript|SharedHelper|GenericCounter|AuthorFailureException)[:\[\x60])',jit),'Targeted production author native JIT observed')
        return dict(result,lifecycleCases=24,packageCases=15,sampleContexts=3,sampleCollections=3,
                    productionPolicyAcknowledgements=3,scope='Release production lifecycle/package/sample functional acceptance; targeted author JIT0; default-context PrivateState seed is trusted control; no method-entry proof')
    refusal='RuneCLRInterpreterRefusal: SelectionUGC.Refusal.Entry:Reject CORJIT_SKIPPED'
    if lane=='unmarked-fallback':
        check(re.findall(r'^'+re.escape(refusal)+r'$',native,re.M)==[refusal],'Actual scoped compiler SKIPPED injection')
        check(len(re.findall(r'^PASS unmarked-refusal value=73 module=[0-9a-f-]+ token=0x06000001$',managed,re.M))==1,'Unmarked native fallback value/token')
        check(re.search(r'JIT compiled\s+\.?SelectionUGC\.Refusal\.Entry:Reject',jit),'Unmarked refused method JIT fallback positive')
        return dict(result,scope='Unmarked same-body mode1 compiler-SKIPPED/native-fallback control; no required-session claim')
    recovery=managed
    if lane=='required-refusal':
        marker='PASS required-refusal exception=System.NotSupportedException collected=true'
        check(re.findall(r'^'+re.escape(marker)+r'$',managed,re.M)==[marker],'Required refusal exception/collection')
        check(re.findall(r'^'+re.escape(refusal)+r'$',native,re.M)==[refusal],'Actual scoped compiler SKIPPED injection')
        prefix,recovery=managed.split(marker,1)
        refusal_queries=re.findall(r'^POLICY context=.* phase=(\S+) value=([01]) collectible=true$',prefix,re.M)
        check(all(value=='1' for _,value in refusal_queries) and
              [phase for phase,_ in refusal_queries if not phase.startswith('resolver-')]==['before-load','before-explicit-load','after-explicit-load','before-unload'],'Refused context native policy queries')
        check(len(re.findall(r'^RETIRED query=System\.InvalidOperationException protected=true$',prefix,re.M))==1,'Refused context retired guard')
        result.update(refusedContexts=1,refusedCollections=1,refusalQueries=len(refusal_queries),compilerSkipped=True)
    values=re.findall(r'^PASS session=([0-9]+) values=(\{.*\}) collected=true$',recovery,re.M)
    check([int(x[0]) for x in values]==list(range(1,21)) and all(json.loads(x[1])==VALUES for x in values),'20 exact17-field values/collections')
    queries=re.findall(r'^POLICY context=.* phase=(\S+) value=([01]) collectible=true$',recovery,re.M)
    expected='0' if lane=='ordinary' else '1'
    check(len(queries)==260 and all(q[1]==expected for q in queries),'260 session native policy queries')
    check(Counter(phase for phase,_ in queries)==Counter({'before-load':20,'before-explicit-load':40,'after-explicit-load':40,
          'resolver-before':80,'before-run':20,'resolver-after-private':20,'after-run':20,'before-unload':20}),
          'Exact session policy phase distribution')
    retired=len(re.findall(r'^RETIRED query=System\.InvalidOperationException protected=true$',managed,re.M))
    check(retired==(21 if lane=='required-refusal' else 20),'Exact retired query guards')
    check(re.search(r'JIT compiled\s+SelectionProbe\.Contract\.ProbeResult:',jit),'Trusted contract JIT positive')
    author_jit=re.search(r'JIT compiled\s+\.?SelectionUGC[.:]',jit)
    check(bool(author_jit) if lane=='ordinary' else not author_jit,'Ordinary JIT positive / required authorJIT0')
    return dict(result,observedSessions=20,observedCollections=20,requiredQueries=260 if lane!='ordinary' else 0,
                sessionPolicyQueries=260,retiredQueryGuards=retired,
                scope='Release '+lane+' exact selection values/policy/retirement/native-JIT diagnostics; no method-entry proof')


def assess(directory, run):
    result={'passed':False,'functionalPassed':False,'independentNonDebuggerAcceptance':False,
            'entryProofCollected':False,'platformAccepted':False,'applicationRerun':False,
            'scope':'Independent Release session values/policy/retirement/native-JIT diagnostics; no interpreter method-entry proof'}
    try:
        state,product=evidence(directory);request=read(run/'request.json');lane=request.get('lane','required')
        check(lane in LANES,'Unknown Release lane');mode='1' if lane=='unmarked-fallback' else '0'
        native=(run/'native.log').read_text();managed=(run/'managed.log').read_text();jit=(run/'jit.log').read_text()
        header=re.findall(r'^ANDROID_SESSION_NATIVE pid=([0-9]+) runId=([0-9a-f]{32}) InterpMode='+mode+r' RuneCLRInterpretCollectible=0$',native,re.M)
        check(len(header)==1,'Unique native mode0/diagnostic0 header absent')
        pid=int(header[0][0]);nonce=header[0][1];mr=read(run/'managed-result.json')
        check(mr['appPid']==pid and mr['runId']==nonce and mr['lane']==lane and mr['exitCode']==0 and
              mr['policyVersion']==mr['requiredPolicy']==1 and mr['ordinaryPolicy']==mr['defaultPolicy']==0,'Managed/native policy identity')
        check((run/'pid-query.txt').read_text().strip()=='android.os.Process.myPid='+str(pid),'Java PID identity')
        check('ANDROID_SESSION_MANAGED pid='+str(pid)+' runId='+nonce+' lane='+lane+' framework=.NET 12.0.0-dev arch=X64' in managed,'Managed runtime/nonce identity')
        check(re.findall(r'^CORECLR_INITIALIZE_HRESULT=(.*)$',native,re.M)==['0x0'] and
              re.findall(r'^CORECLR_EXECUTE_HRESULT=(.*)$',native,re.M)==['0x0;RUNECLR_EXIT=0'],
              'Exact native HRESULT/managed exit completion')
        instrumentation=(run/'instrumentation.log').read_text()
        check(re.findall(r'^INSTRUMENTATION_RESULT: return-code=(.*)$',instrumentation,re.M)==['0'] and
              re.findall(r'^INSTRUMENTATION_CODE: (.*)$',instrumentation,re.M)==['0'] and
              not re.search(r'(?i)process\s*crashed|fatal|instrumentation_failed',instrumentation),'Exact instrumentation completion')
        result.update(functional(lane,native,managed,jit),appPid=pid,runId=nonce)
        # A former gated/ptrace run must never become independent normal acceptance.
        check('ANDROID_ENTRY_GATE' not in native,'Gated run cannot receive independent non-debugger acceptance')
        check(not re.search(r'(?i)ptrace|lldb|gdbserver|entry.capture|observer',native),'Debugger/observer native marker in normal lane')
        check(request['schema']=='runeclr.android.release.functional-request.v1' and request['runId']==nonce and
              request['apkSha256']==state['apkSha256'] and request['gateOptInProvided'] is False and request['debuggerStarted'] is False and
              request['evidenceStateSha256']==sha(directory/'state.json') and request['candidateCommit']==COMMIT and
              request['deviceSerial']==state['deviceSerial'] and request['settings']=={'interpMode':mode,'diagnostic':'0','readyToRun':'1','tiered':'1'},'Independent fresh run request absent')
        argv=request['command']
        check(len(argv)==17 and argv[1:]==['-s',request['deviceSerial'],'shell','am','instrument','-w',
              '-e','env:RUNECLR_SESSION_RUN_ID',nonce,'-e','env:RUNECLR_SESSION_LANE',lane,
              '-e','env:RUNECLR_SESSION_MODE',mode,state['package']+'/net.dot.MonoRunner'],'Exact owned normal instrumentation command')
        check('env:RUNECLR_SESSION_NATIVE_ENTRY_WAIT' not in argv and not any('lldb' in token.lower() or 'gdbserver' in token.lower() for token in argv),'Debugger/gate opt-in in command')
        check((run/'instrumentation.log.exit').read_text().strip()=='0','Instrumentation process exit')
        transport=read(run/'transport-results.json')
        check(transport['success'] and transport['instrumentationLaunches']==1 and transport['runId']==nonce,'One fresh successful instrumentation launch required')
        required_raw={'request.json','native.log','managed.log','jit.log','managed-result.json','pid-query.txt','maps.log',
                      'instrumentation.log','instrumentation.log.exit','installed-before.log','installed-after.log',
                      'apk-before.log','apk-after.log','owned-processes-before.log','owned-processes-after.log',
                      'owned-processes-stopped.log','forwards-before.log','forwards-after.log','processes-after.log',
                      'commands.json','tracer-samples.json'}
        check(required_raw<=transport['rawHashes'].keys(),'Required original raw hashes missing')
        for name,value in transport['rawHashes'].items():
            check(Path(name).name==name and name not in ('transport-results.json','assessment.json'),'Unsafe/self-referential raw evidence path')
            check(sha(run/name)==value,'Original raw evidence changed: '+name)
        native_dir=transport['nativeDirectory']
        check(re.fullmatch(r'/data/app/[^\s]+/lib/x86_64',native_dir),'Installed Android native directory identity')
        maps=(run/'maps.log').read_text()
        for name in ('libcoreclr.so','libclrinterpreter.so','libclrjit.so'):
            paths=set(re.findall(r'(?m)^.*\s(\S*/'+re.escape(name)+r')$',maps))
            check((lane=='ordinary' and name=='libclrinterpreter.so' and not paths) or paths=={native_dir+'/'+name},'Actual mapped matching native image path mismatch: '+name)
        check(not re.search(r'(?i)lldb|gdbserver',maps),'Debugger image mapped in normal lane')
        check(parse_hashes(run/'installed-before.log')==parse_hashes(run/'installed-after.log')==expected_device(state,product,native_dir),'246 installed before/after identities')
        check(parse_hashes(run/'apk-before.log')==parse_hashes(run/'apk-after.log')=={transport['installedApkPath']:state['apkSha256']},'Installed APK before/after identity')
        samples=read(run/'tracer-samples.json')
        check(samples and all(x['pid']==pid and x['tracerPid']==0 for x in samples),'No actual live TracerPid0 observation')
        for x in samples:
            check(transport['rawHashes'].get(x['rawPath'])==x['sha256'] and sha(run/x['rawPath'])==x['sha256'] and
                  re.search(r'^TracerPid:\s+0$',(run/x['rawPath']).read_text(),re.M),'Live tracer raw identity')
        for name in ('owned-processes-before.log','owned-processes-after.log'):
            check(not re.search(r'(?i)lldb-server|gdbserver', (run/name).read_text()),'Owned debugger server in normal lane')
        check(not (run/'owned-processes-stopped.log').read_text().strip(),'Owned process still alive after force-stop; fresh launch unproven')
        for name in ('forwards-before.log','forwards-after.log'):
            check(not any(line.split() and line.split()[0]==request['deviceSerial'] for line in (run/name).read_text().splitlines()),'Owned serial debugger forward in normal lane')
        check(not re.search(r'^\s*'+str(pid)+r'\s',(run/'processes-after.log').read_text(),re.M),'Owned app has not exited')
        commands=read(run/'commands.json')
        check(all(command['argv'][1:3]==['-s',request['deviceSerial']] and
                  not any(re.search(r'(?i)lldb|gdbserver|ptrace',token) for token in command['argv']) for command in commands),'Foreign serial/debugger command in normal lane')
        check(not any(command['argv'][3:5]==['forward','tcp:0'] for command in commands),'Debugger forward created in normal lane')
        result.update(passed=True,independentNonDebuggerAcceptance=True,installedFileHashesVerified=246,
                      rawFileHashesVerified=len(transport['rawHashes']),tracerSamples=len(samples),apkSha256=state['apkSha256'],
                      transportReceiptSha256=sha(run/'transport-results.json'),requestSha256=sha(run/'request.json'))
    except Exception:
        result['error']=traceback.format_exc()
    return result


def run_owned(args):
    directory=args.evidence.resolve();out=args.output.resolve()
    check(not out.is_relative_to(directory) and not out.exists(),'Output must be fresh and outside frozen evidence')
    out.mkdir(parents=True)
    records=[];app=None;transport={'success':False,'instrumentationLaunches':0,'applicationRerun':False}
    def adb(*parts, input_text=None, allowed_failure=False, timeout=40):
        command=[str(args.adb.resolve()),'-s',args.serial,*map(str,parts)]
        done=subprocess.run(command,input=input_text,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
        records.append({'argv':command,'exitCode':done.returncode,'stdout':done.stdout,'stderr':done.stderr})
        check(allowed_failure or done.returncode==0,'Owned adb command failed; original record retained')
        return done
    def owned(*parts,**kw):return adb('shell','run-as',state['package'],*parts,**kw)
    try:
        state,product=evidence(directory)
        check(args.serial==state['deviceSerial'],'Explicit serial differs from frozen installation')
        check(adb('get-state').stdout.strip()=='device' and adb('emu','avd','name').stdout.splitlines()[0]=='RuneCLR_API_35_x64','Owned x64 AVD identity')
        check(adb('shell','uname','-m').stdout.strip()=='x86_64' and adb('shell','getprop','sys.boot_completed').stdout.strip()=='1','Booted x64 device required')
        check(adb('shell','getprop','ro.build.version.sdk').stdout.strip()=='35' and adb('shell','getconf','PAGESIZE').stdout.strip()=='4096','API35/4096-byte platform identity')
        installed=adb('shell','pm','path',state['package']).stdout.strip()
        check(installed.startswith('package:/data/app/') and chr(10) not in installed,'Ambiguous installed APK')
        apk_path=installed.removeprefix('package:');native_dir=apk_path.rsplit('/',1)[0]+'/lib/x86_64'
        inventory=expected_device(state,product,native_dir)
        def identity(label):
            script='set -e'+chr(10)+''.join('sha256sum '+shlex.quote(p)+chr(10) for p in inventory)
            raw=owned('sh',input_text=script).stdout;(out/('installed-'+label+'.log')).write_text(raw)
            check(parse_hashes(out/('installed-'+label+'.log'))==inventory,'Installed identity changed')
            raw=adb('shell','sha256sum',apk_path).stdout;(out/('apk-'+label+'.log')).write_text(raw)
            check(parse_hashes(out/('apk-'+label+'.log'))=={apk_path:state['apkSha256']},'Installed APK changed')
        uid=owned('id','-u').stdout.strip();check(re.fullmatch('[0-9]+',uid),'Owned UID absent')
        def processes(label):
            text=adb('shell','ps','-A','-o','PID,UID,ARGS').stdout
            rows=[line for line in text.splitlines() if len(line.split())>2 and line.split()[1]==uid]
            raw=chr(10).join(rows)+chr(10);(out/('owned-processes-'+label+'.log')).write_text(raw)
            check(not re.search(r'(?i)lldb-server|gdbserver',raw),'Existing owned debugger server; do not run normal lane')
            return text
        def forwards(label):
            raw=adb('forward','--list').stdout;(out/('forwards-'+label+'.log')).write_text(raw)
            check(not any(line.split() and line.split()[0]==args.serial for line in raw.splitlines()),'Owned serial forward exists; do not run normal lane')
        processes('before');forwards('before');identity('before')
        adb('shell','am','force-stop',state['package'])
        processes('stopped')
        check(not (out/'owned-processes-stopped.log').read_text().strip(),'Owned app did not stop; do not launch')
        nonce=uuid.uuid4().hex
        mode='1' if args.lane=='unmarked-fallback' else '0'
        command=[str(args.adb.resolve()),'-s',args.serial,'shell','am','instrument','-w',
                 '-e','env:RUNECLR_SESSION_RUN_ID',nonce,'-e','env:RUNECLR_SESSION_LANE',args.lane,
                 '-e','env:RUNECLR_SESSION_MODE',mode,state['package']+'/net.dot.MonoRunner']
        write(out/'request.json',{'schema':'runeclr.android.release.functional-request.v1','runId':nonce,'command':command,
              'apkSha256':state['apkSha256'],'candidateCommit':COMMIT,'gateOptInProvided':False,'debuggerStarted':False,
              'deviceSerial':args.serial,'evidenceStateSha256':sha(directory/'state.json'),'driverSha256':sha(__file__),
              'settings':{'interpMode':mode,'diagnostic':'0','readyToRun':'1','tiered':'1'},'lane':args.lane,'applicationRerun':False})
        samples=[];deadline=time.monotonic()+args.timeout
        with (out/'instrumentation.log').open('wb') as log:
            app=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT);transport['instrumentationLaunches']=1
            while app.poll() is None:
                check(time.monotonic()<deadline,'Instrumentation timeout; no automatic retry')
                query=owned('cat','files/session-'+nonce+'.pid-query.txt',allowed_failure=True,timeout=10)
                match=re.fullmatch(r'android.os.Process.myPid=([0-9]+)\s*',query.stdout)
                if match:
                    pid=int(match[1]);status=owned('cat','/proc/'+str(pid)+'/status',allowed_failure=True,timeout=10)
                    tracer=re.search(r'^TracerPid:\s+([0-9]+)$',status.stdout,re.M)
                    if tracer:
                        relative='tracer-status-'+str(len(samples))+'.log';(out/relative).write_text(status.stdout)
                        samples.append({'pid':pid,'tracerPid':int(tracer[1]),'rawPath':relative,'sha256':sha(out/relative)})
                time.sleep(.05)
        (out/'instrumentation.log.exit').write_text(str(app.returncode)+chr(10))
        check(app.returncode==0,'Instrumentation failed; no automatic retry')
        write(out/'tracer-samples.json',samples)
        for name in ('native.log','managed.log','jit.log','managed-result.json','pid-query.txt','maps.log'):
            # exec-out keeps raw log bytes intact and reads only the owned nonce filenames.
            done=subprocess.run([str(args.adb.resolve()),'-s',args.serial,'exec-out','run-as',state['package'],'cat','files/session-'+nonce+'.'+name],capture_output=True,timeout=40)
            check(done.returncode==0,'Owned raw log unavailable: '+name)
            (out/name).write_bytes(done.stdout)
        identity('after');forwards('after');text=processes('after');(out/'processes-after.log').write_text(text)
        write(out/'commands.json',records)
        transport.update(success=True,runId=nonce,nativeDirectory=native_dir,installedApkPath=apk_path)
    except Exception:
        transport['error']=traceback.format_exc()
        if app is not None and app.poll() is None:
            app.kill();app.wait()
            # Only the explicitly bound installed package can be stopped on failure.
            if 'state' in locals():adb('shell','am','force-stop',state['package'],allowed_failure=True)
        if not (out/'commands.json').exists():write(out/'commands.json',records)
    transport['rawHashes']={p.name:sha(p) for p in out.iterdir() if p.is_file()}
    write(out/'transport-results.json',transport)
    assessment=assess(directory,out) if transport['success'] else {'passed':False,'error':transport.get('error'),'entryProofCollected':False,'applicationRerun':False}
    write(out/'assessment.json',assessment)
    print(json.dumps(assessment,indent=2))
    return 0 if assessment['passed'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='phase',required=True)
    run=sub.add_parser('run');offline=sub.add_parser('assess')
    for p in (run,offline):
        p.add_argument('--evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    run.add_argument('--serial',required=True);run.add_argument('--adb',type=Path,required=True);run.add_argument('--timeout',type=int,default=180)
    run.add_argument('--lane',choices=LANES,default='required')
    offline.add_argument('--run',type=Path,required=True)
    args=parser.parse_args()
    if args.phase=='run':return run_owned(args)
    output=args.output.resolve();check(not output.exists() and not output.is_relative_to(args.evidence.resolve()) and not output.is_relative_to(args.run.resolve()),'Offline output must be fresh and outside input evidence')
    output.mkdir(parents=True);result=assess(args.evidence.resolve(),args.run.resolve());write(output/'assessment.json',result)
    print(json.dumps(result,indent=2));return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
