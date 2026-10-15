#!/usr/bin/env python3
"""Windows-only private required-interpreter budget measurement; no installed runtime changes."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '099dacd07d8d890822f7422f895337733457ab3c'
CHECKER_PATH = Path(__file__).with_name('budget-runtime-candidate.py')
_spec = importlib.util.spec_from_file_location('budget_runtime_candidate', CHECKER_PATH)
_candidate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_candidate)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2), encoding='utf-8')

def freeze_build_binding(runtime, layout, configuration, build_evidence, output, candidate_commit=COMMIT):
    candidate_validation=_candidate.validate(runtime,candidate_commit)
    product=runtime/f'artifacts/bin/coreclr/windows.x64.{configuration}'
    obj=runtime/f'artifacts/obj/coreclr/windows.x64.{configuration}'
    cache=(obj/'CMakeCache.txt').read_text()
    keys=('CLR_CMAKE_TARGET_ARCH','CLR_CMAKE_TARGET_OS','CMAKE_BUILD_TYPE','FEATURE_INTERPRETER','FEATURE_DYNAMIC_CODE_COMPILED')
    features={key:re.search(r'^'+key+r':[^=]+=(.*)$',cache,re.M).group(1) for key in keys}
    expected={'CLR_CMAKE_TARGET_ARCH':'x64','CLR_CMAKE_TARGET_OS':'windows','CMAKE_BUILD_TYPE':configuration,
              'FEATURE_INTERPRETER':'1','FEATURE_DYNAMIC_CODE_COMPILED':'1'}
    if features!=expected: raise RuntimeError('Actual native configuration differs from requested configuration.')
    request=json.loads((build_evidence/'request.json').read_text(encoding='utf-8-sig'))
    result=json.loads((build_evidence/'build-result.json').read_text(encoding='utf-8-sig'))
    receipt=json.loads((build_evidence/'layout-receipt.json').read_text(encoding='utf-8-sig'))
    if request['candidateCommit']!=candidate_commit or result['exitCode']!=0 or receipt['candidateCommit']!=candidate_commit or not receipt['passed']:
        raise RuntimeError('Matching successful native build provenance required.')
    checker_hash=digest(CHECKER_PATH)
    if candidate_commit!=COMMIT or 'candidateValidation' in request:
        for value in (request,result,receipt):
            if value.get('candidateValidation')!=candidate_validation or value.get('candidateCheckerSha256')!=checker_hash:
                raise RuntimeError('Native build candidate/checker validation mismatch.')
        if digest(build_evidence/CHECKER_PATH.name)!=checker_hash:
            raise RuntimeError('Frozen build candidate checker changed.')
    arguments=request['arguments']
    if arguments[arguments.index('-configuration')+1]!=configuration or '-clrinterpreter' not in arguments:
        raise RuntimeError('Build request configuration/interpreter does not match.')
    metadata={'build-request.json':build_evidence/'request.json', 'build-result.json':build_evidence/'build-result.json',
              'layout-receipt.json':build_evidence/'layout-receipt.json','CMakeCache.txt':obj/'CMakeCache.txt',
              'native-commands.txt':build_evidence/'native-commands.txt',
              CHECKER_PATH.name:CHECKER_PATH,
              'runtime-source/'+_candidate.METER:runtime/_candidate.METER}
    if 'candidateValidation' in request:
        metadata['build-candidate-checker.py']=build_evidence/CHECKER_PATH.name
    if configuration=='Release':
        if (receipt['configuration']!=configuration or receipt['buildResultSha256']!=digest(build_evidence/'build-result.json') or
            receipt['buildRequestSha256']!=digest(build_evidence/'request.json') or
            result['cmakeFeatures']!=features or result['cmakeCacheSha256']!=digest(obj/'CMakeCache.txt')):
            raise RuntimeError('Release source/build/layout binding inconsistent.')
        if Path(receipt['layout']).resolve()!=layout.resolve() or Path(receipt['product']).resolve()!=product.resolve():
            raise RuntimeError('Release receipt describes another layout/product.')
        for relative,expected_hash in receipt['allLayoutHashes'].items():
            if digest(layout/relative)!=expected_hash: raise RuntimeError('Release layout inventory mismatch: '+relative)
        for relative,expected_hash in request['sourceHashes'].items():
            if digest(runtime/relative)!=expected_hash: raise RuntimeError('Release source changed since build: '+relative)
            source=build_evidence/'source'/relative
            if digest(source)!=expected_hash: raise RuntimeError('Frozen Release source differs: '+relative)
            metadata['runtime-source/'+relative]=source
        for name in ('build.stdout','build.stderr'):
            metadata[name]=build_evidence/name
        if result['stdoutSha256']!=digest(build_evidence/'build.stdout') or result['stderrSha256']!=digest(build_evidence/'build.stderr'):
            raise RuntimeError('Release build raw log binding mismatch.')
    else:
        compiled=json.loads((build_evidence/'compile-evidence.json').read_text(encoding='utf-8-sig'))
        if not compiled['passed'] or compiled['candidateCommit']!=candidate_commit or compiled['cmakeFeatures']!=features:
            raise RuntimeError('Checked compile provenance mismatch.')
        metadata['compile-evidence.json']=build_evidence/'compile-evidence.json'
    critical=('coreclr.dll','clrinterpreter.dll','clrjit.dll','System.Private.CoreLib.dll',
              'IL/System.Private.CoreLib.dll','x64/crossgen2/crossgen2.exe',
              'x64/crossgen2/clrjit_win_x64_x64.dll','x64/crossgen2/jitinterface_x64.dll')
    products={relative:digest(product/relative) for relative in critical}
    recorded=result['criticalProductHashes'] if configuration=='Release' else compiled['criticalProductHashes']
    if products!=recorded: raise RuntimeError('Native/CoreLib/compiler products changed since build.')
    frozen=output/'provenance'
    frozen.mkdir()
    metadata_hashes={}
    for name,path in metadata.items():
        (frozen/name).parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,frozen/name)
        metadata_hashes['provenance/'+name]=digest(frozen/name)
    binding={'version':2,'configuration':configuration,'cmakeFeatures':features,'metadataHashes':metadata_hashes,
             'criticalProductHashes':products,'buildEvidencePath':str(build_evidence),'actualSourceCommit':candidate_commit,
             'candidateValidation':candidate_validation,'candidateCheckerSha256':checker_hash}
    frozen_inputs={str(path):digest(path) for path in metadata.values()}
    frozen_inputs.update({str(product/relative):expected_hash for relative,expected_hash in products.items()})
    if configuration=='Release':
        frozen_inputs.update({str(layout/relative):expected_hash for relative,expected_hash in receipt['allLayoutHashes'].items()})
        frozen_inputs.update({str(runtime/relative):expected_hash for relative,expected_hash in request['sourceHashes'].items()})
    return binding,frozen_inputs

def command(argv, directory, label, settings=None):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_'))}
    env.update(settings or {})
    started = time.time()
    process = subprocess.Popen([str(arg) for arg in argv], cwd=ROOT, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=180)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate()
    stdout_path, stderr_path = directory / (label+'.stdout'), directory / (label+'.stderr')
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    receipt = {'argv': [str(arg) for arg in argv], 'settings': settings or {}, 'pid': process.pid,
               'exitCode': process.returncode, 'timedOut': timed_out, 'wallSeconds': time.time()-started,
               'stdoutSha256': digest(stdout_path), 'stderrSha256': digest(stderr_path)}
    save(directory/(label+'.process.json'), receipt)
    if process.returncode != 0 or timed_out:
        raise RuntimeError('Owned subprocess failed; raw evidence preserved: '+label)
    return stdout.decode('utf-8-sig'), receipt

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--runtime', default='E:/runtime-finalizer-20261013')
    parser.add_argument('--candidate-commit', default=COMMIT)
    parser.add_argument('--layout', default=str(ROOT/'artifacts/session-finalizer/build-20261013-attempt1/layout'))
    parser.add_argument('--configuration', choices=('Checked','Release'), default='Checked')
    parser.add_argument('--build-evidence')
    parser.add_argument('--pairs', type=int, default=4)
    parser.add_argument('--samples', type=int, default=9)
    args = parser.parse_args()
    if args.pairs < 2 or args.samples < 3:
        raise ValueError('At least two paired process rounds/three samples required.')
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    runtime, layout = Path(args.runtime).resolve(), Path(args.layout).resolve()
    framework = layout/'shared/Microsoft.NETCore.App/12.0.0'
    product = runtime/f'artifacts/bin/coreclr/windows.x64.{args.configuration}'
    candidate_validation=_candidate.validate(runtime,args.candidate_commit)
    head=candidate_validation['candidateCommit']
    build_evidence=Path(args.build_evidence).resolve() if args.build_evidence else layout.parent
    build_binding,provenance_hashes=freeze_build_binding(runtime,layout,args.configuration,build_evidence,output,args.candidate_commit)
    source_paths = []
    for name in ('benchmarks/RuneCLR.BudgetKernel', 'benchmarks/RuneCLR.BudgetOverhead',
                 'src/RuneCLR.Runtime', 'src/RuneCLR.Abstractions', 'src/RuneCLR.Packages'):
        source_paths.extend(path for path in (ROOT/name).rglob('*') if path.suffix in ('.cs','.csproj')
                            and not {'obj','bin'}.intersection(path.relative_to(ROOT/name).parts))
    source_paths.extend(path for path in (ROOT/'Directory.Build.props', ROOT/'Directory.Build.targets',
                        ROOT/'global.json', ROOT/'NuGet.Config', Path(__file__).resolve(), CHECKER_PATH) if path.exists())
    source_hashes = {str(path.relative_to(ROOT)).replace('\\','/'): digest(path) for path in source_paths}
    for path in source_paths:
        target = output/'source'/path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    def check_inputs():
        if _candidate.validate(runtime,args.candidate_commit)!=candidate_validation:
            raise RuntimeError('Candidate source validation changed during measurement.')
        for path in source_paths:
            if digest(path) != source_hashes[str(path.relative_to(ROOT)).replace('\\','/')]:
                raise RuntimeError('Source changed after freeze: '+str(path))
        for path, expected in native_hashes.items():
            if digest(path) != expected:
                raise RuntimeError('Runtime changed during measurement: '+path)
        for path, expected in provenance_hashes.items():
            if digest(path)!=expected: raise RuntimeError('Build provenance changed during measurement: '+path)
        if digest(sdk)!=sdk_hash: raise RuntimeError('Host build SDK changed during measurement.')
    native_hashes = {}
    for name in ('coreclr.dll','clrjit.dll','clrinterpreter.dll','System.Private.CoreLib.dll'):
        path = framework/name
        if digest(path) != digest(product/name):
            raise RuntimeError('Layout does not match actual '+args.configuration+' product: '+name)
        native_hashes[str(path)] = digest(path)
    for path in (layout/'dotnet.exe', layout/'host/fxr/12.0.0/hostfxr.dll', framework/'hostpolicy.dll'):
        native_hashes[str(path)] = digest(path)
    version_script = '$p=Get-Item -LiteralPath '+"'"+str(framework/'coreclr.dll').replace("'","''")+"'; $p.VersionInfo.ProductVersion"
    stamp = subprocess.check_output(['pwsh','-NoProfile','-Command',version_script], text=True).strip()
    if args.candidate_commit not in stamp:
        raise RuntimeError('Native source stamp mismatch.')
    sdk = ROOT/'artifacts/toolchains/dotnet-11-rc1/dotnet.exe'
    sdk_hash=digest(sdk)
    sdk_version=subprocess.check_output([str(sdk),'--version'],text=True).strip()
    request = {'candidateCommit':head, 'candidateValidation':candidate_validation,
               'candidateCheckerSha256':digest(CHECKER_PATH), 'upstreamBase':'0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de',
               'platform':'Windows x64 '+args.configuration,'configuration':args.configuration, 'runtimeSourceTrackedClean':True, 'runtime':str(runtime),
               'runtimeBuildBinding':build_binding,
               'hostBuildSdk':str(sdk),'hostBuildSdkSha256':sdk_hash,'hostBuildSdkVersion':sdk_version,
               'layout':str(layout), 'runtimeProductStamp':stamp, 'runtimeHashes':native_hashes,
               'sourceHashes':source_hashes, 'pairs':args.pairs, 'samplesPerProcess':args.samples,
               'machine':platform.platform(), 'processor':platform.processor(),
               'baseline':'same instrumented runtime, required policy, no configured meter; per-dispatch owner lookup remains',
               'affinity':'all children pin logical CPU2 (mask4); no machine-wide isolation or clock governor changes',
               'scope':'experimental '+args.configuration+' incremental configured-meter cost, not full instrumentation overhead or '+
                       ('Release/' if args.configuration=='Checked' else '')+'mobile/game performance'}
    cpu_text,_ = command(['pwsh','-NoProfile','-Command',
        'Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json'],
        output,'cpu')
    request['cpu']=json.loads(cpu_text)
    save(output/'request.json',request)
    for name in ('BudgetKernel','BudgetOverhead'):
        check_inputs()
        command([sdk,'build',ROOT/f'benchmarks/RuneCLR.{name}/RuneCLR.{name}.csproj','-c','Release',
                 '--output',output/name,'-nodeReuse:false'],output,'build-'+name)
        check_inputs()
    host = output/'BudgetOverhead/RuneCLR.BudgetOverhead.dll'
    author = output/'BudgetKernel/RuneCLR.BudgetKernel.dll'
    managed_hashes = {str(path.relative_to(output)):digest(path) for name in ('BudgetKernel','BudgetOverhead')
                      for path in (output/name).iterdir() if path.is_file()}
    save(output/'managed-identity.json',managed_hashes)
    settings={'DOTNET_InterpMode':'0','DOTNET_RuneCLRInterpretCollectible':'0',
              'DOTNET_ReadyToRun':'1','DOTNET_TieredCompilation':'0','DOTNET_MULTILEVEL_LOOKUP':'0'}
    lanes=[]
    for pair in range(args.pairs):
        modes=('no-config','high-budget') if pair%2==0 else ('high-budget','no-config')
        for position,mode in enumerate(modes):
            check_inputs()
            for relative,expected in managed_hashes.items():
                if digest(output/relative)!=expected: raise RuntimeError('Managed bytes changed: '+relative)
            nonce=uuid.uuid4().hex
            label=f'pair-{pair}-position-{position}-{mode}-{nonce}'
            stdout,raw=command([layout/'dotnet.exe','exec','--fx-version','12.0.0',host,author,mode,nonce,str(args.samples)],
                               output,label,settings)
            receipt=json.loads(stdout)
            if not receipt['passed'] or receipt['nonce']!=nonce or receipt['processId']!=raw['pid'] or receipt['mode']!=mode:
                raise RuntimeError('Managed/native process identity mismatch.')
            if not receipt['directCollected'] or receipt['sessionCollected'] != args.samples+3:
                raise RuntimeError('Context collection missing.')
            if any(not entry['Interpreted'] or entry['StubType']!=6 for entry in receipt['Proof']):
                raise RuntimeError('Author entry proof missing.')
            if receipt['affinity'] != 4 or receipt['hostProof']['Interpreted']:
                raise RuntimeError('Pinned CPU or trusted native positive control missing.')
            deltas=[sample['DispatchDelta'] for sample in receipt['Callbacks']]
            if mode=='high-budget' and (len(set(deltas))!=1 or not deltas[0] or receipt['FinalSnapshot']['IsTerminated']):
                raise RuntimeError('Native dispatch accounting inconsistent.')
            if mode=='no-config' and (any(delta is not None for delta in deltas) or receipt['FinalSnapshot'] is not None):
                raise RuntimeError('No-config lane unexpectedly configured.')
            lane={'pair':pair,'position':position,'label':label,'raw':raw,'receipt':receipt}
            lanes.append(lane)
            save(output/'partial-results.json',{'passed':False,'lanes':lanes})
            print('PASS',pair,position,mode,'callbacks median ms',statistics.median(sample['Milliseconds'] for sample in receipt['Callbacks']),flush=True)
    check_inputs()
    summaries={}
    paired=[]
    for mode in ('no-config','high-budget'):
        selected=[lane for lane in lanes if lane['receipt']['mode']==mode]
        callbacks=[sample['Milliseconds'] for lane in selected for sample in lane['receipt']['Callbacks']]
        sessions=[sample['Milliseconds'] for lane in selected for sample in lane['receipt']['Samples'] if not sample['Warmup']]
        summaries[mode]={'processes':len(selected),'callbackSamples':len(callbacks),'callbackMedianMs':statistics.median(callbacks),
                         'callbackMinMs':min(callbacks),'callbackMaxMs':max(callbacks),
                         'sessionMedianMs':statistics.median(sessions),'sessionMinMs':min(sessions),'sessionMaxMs':max(sessions),
                         'setupMedianMs':statistics.median(lane['receipt']['SetupMilliseconds'] for lane in selected)}
    for pair in range(args.pairs):
        matched={lane['receipt']['mode']:lane for lane in lanes if lane['pair']==pair}
        callback_medians={mode:statistics.median(sample['Milliseconds'] for sample in lane['receipt']['Callbacks']) for mode,lane in matched.items()}
        paired.append({'pair':pair,'callbackMediansMs':callback_medians,
                       'configuredMeterIncrementPercent':100*(callback_medians['high-budget']/callback_medians['no-config']-1)})
    result={'passed':True,'configuration':args.configuration,'requestSha256':digest(output/'request.json'),'managedIdentitySha256':digest(output/'managed-identity.json'),
            'summaries':summaries,'pairedRounds':paired,'lanes':lanes,
            'configuredMeterIncrementPercentFromPooledMedian':100*(summaries['high-budget']['callbackMedianMs']/summaries['no-config']['callbackMedianMs']-1),
            'nativeEntryProof':'pinned Windows x64 post-execution interpreter-precode type6 for author kernel and private update, not exhaustive invocation trace',
            'limits':request['scope']}
    save(output/'results.json',result)
    print(json.dumps({'passed':True,'summaries':summaries,'pairedRounds':paired},indent=2))

if __name__=='__main__':
    main()
