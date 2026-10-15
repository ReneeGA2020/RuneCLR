#!/usr/bin/env python3
"""Build exact private Windows Release budget source and a separately inventoried opt-in batch-interval layout."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

COMMIT = 'd0da7dfafc0c4894ae7aa5332ee171f023a0a88e'
BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = Path(__file__).with_name('batch-interval-runtime-candidate.py')
PREPARATION = ROOT/'artifacts/budget-batching/candidate-20261014-attempt1/candidate-receipt.json'
PREPARATION_SHA = '15a4a8c82b26a1543782c4cd95bd24e58af30756f86d633800a58916c64da430'
BASELINE_RECEIPT_SHA = '7e66b11f9f676bb767307e5118d8f6c761bf6581ef15fbdd524a06f927f0bac1'
_spec = importlib.util.spec_from_file_location('budget_runtime_candidate', CHECKER_PATH)
_candidate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_candidate)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2), encoding='utf-8')

def git(runtime, *args):
    return subprocess.check_output(['git','-C',str(runtime),*args], text=True).strip()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--runtime', default='E:/runtime-batch-interval-20261014')
    parser.add_argument('--candidate-commit', default=COMMIT)
    parser.add_argument('--baseline', default=str(ROOT/'artifacts/derived-ledger/windows-release-build-20261014-attempt1'))
    args=parser.parse_args()
    runtime, evidence, baseline=Path(args.runtime).resolve(),Path(args.output).resolve(),Path(args.baseline).resolve()
    evidence.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(__file__,evidence/'build-driver.py')
    shutil.copyfile(CHECKER_PATH,evidence/CHECKER_PATH.name)
    candidate_commit=args.candidate_commit
    candidate_validation=_candidate.validate(runtime,candidate_commit)
    checker_hash=sha(CHECKER_PATH)
    if sha(PREPARATION)!=PREPARATION_SHA:
        raise RuntimeError('Frozen batch-interval preparation receipt changed.')
    preparation=json.loads(PREPARATION.read_text())
    if preparation['candidateValidation']!=candidate_validation or preparation['candidateCheckerSha256']!=checker_hash:
        raise RuntimeError('Prepared candidate/checker mismatch.')
    if Path(preparation['sdkDestination']).resolve()!=runtime/'.dotnet':
        raise RuntimeError('Private copied SDK destination mismatch.')
    for name,expected in preparation['sdkFileHashes'].items():
        if sha(runtime/'.dotnet'/name)!=expected:
            raise RuntimeError('Copied SDK changed before build: '+name)
    if sha(baseline/'layout-receipt.json')!=BASELINE_RECEIPT_SHA:
        raise RuntimeError('Frozen baseline layout receipt mismatch.')
    baseline_control=json.loads((baseline/'layout-receipt.json').read_text())
    if any(baseline_control.get(key)!=value for key,value in {
            'passed':True,'candidateCommit':_candidate.BASELINE,'upstreamBase':BASE,
            'configuration':'Release','platform':'windows.x64'}.items()):
        raise RuntimeError('Baseline must be the accepted derived-ledger Windows x64 Release layout.')
    for name,expected in baseline_control['allLayoutHashes'].items():
        if sha(baseline/'layout'/name)!=expected:
            raise RuntimeError('Baseline layout changed before build: '+name)
    shutil.copyfile(PREPARATION,evidence/'preparation-receipt.json')
    product=runtime/'artifacts/bin/coreclr/windows.x64.Release'
    obj=runtime/'artifacts/obj/coreclr/windows.x64.Release'
    if product.exists() or obj.exists():
        raise ValueError('Fresh Release product/object directories required; preserve existing output.')
    source_paths=git(runtime,'diff','--name-only',BASE,candidate_commit).splitlines()
    hashes={}
    for relative in source_paths:
        target=evidence/'source'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(runtime/relative,target)
        hashes[relative]=sha(target)
    arguments=['-subset','clr.runtime+clr.jit+clr.hosts+clr.corelib+clr.tools+clr.nativecorelib',
               '-configuration','Release','-arch','x64','-clrinterpreter']
    argv=['cmd.exe','/d','/c',str(runtime/'build.cmd'),*arguments]
    env={key:value for key,value in os.environ.items() if not key.startswith(('DOTNET_','COMPlus_','RUNECLR_'))}
    env.update({'MSBUILDDISABLENODEREUSE':'1','DOTNET_CLI_USE_MSBUILD_SERVER':'0'})
    request={'candidateCommit':candidate_commit,'candidateValidation':candidate_validation,
             'candidateCheckerSha256':checker_hash,'upstreamBase':BASE,'branch':git(runtime,'branch','--show-current'),
             'runtimeSourceTrackedClean':True,'runtime':str(runtime),'configuration':'Release','platform':'windows.x64',
             'argv':argv,'arguments':arguments,'sourceHashes':hashes,'startedUnix':time.time(),
             'sdkVersion':subprocess.check_output([str(runtime/'.dotnet/dotnet.exe'),'--version'],text=True).strip(),
             'sdkSha256':sha(runtime/'.dotnet/dotnet.exe'),'driverSha256':sha(__file__)}
    request['preparationReceiptSha256']=PREPARATION_SHA
    request['baselineControlReceiptSha256']=BASELINE_RECEIPT_SHA
    with (evidence/'build.stdout').open('wb') as stdout,(evidence/'build.stderr').open('wb') as stderr:
        process=subprocess.Popen(argv,cwd=runtime,env=env,stdout=stdout,stderr=stderr)
        request['pid']=process.pid
        save(evidence/'request.json',request)
        print('Started fresh Release build PID',process.pid,flush=True)
        code=process.wait()
    build={'exitCode':code,'pid':process.pid,'completedUnix':time.time(),
           'stdoutSha256':sha(evidence/'build.stdout'),'stderrSha256':sha(evidence/'build.stderr'),
           'requestSha256':sha(evidence/'request.json')}
    save(evidence/'build-result.json',build)
    if code!=0: raise RuntimeError('Release build failed; raw evidence preserved.')
    if _candidate.validate(runtime,candidate_commit)!=candidate_validation or sha(CHECKER_PATH)!=checker_hash:
        raise RuntimeError('Runtime source/checker changed during build.')
    for relative,expected in hashes.items():
        if sha(runtime/relative)!=expected: raise RuntimeError('Source changed: '+relative)
    cache=(obj/'CMakeCache.txt').read_text()
    keys=('CLR_CMAKE_TARGET_ARCH','CLR_CMAKE_TARGET_OS','CMAKE_BUILD_TYPE','FEATURE_INTERPRETER','FEATURE_DYNAMIC_CODE_COMPILED')
    features={key:re.search(r'^'+key+r':[^=]+=(.*)$',cache,re.M).group(1) for key in keys}
    if features!={'CLR_CMAKE_TARGET_ARCH':'x64','CLR_CMAKE_TARGET_OS':'windows','CMAKE_BUILD_TYPE':'Release',
                  'FEATURE_INTERPRETER':'1','FEATURE_DYNAMIC_CODE_COMPILED':'1'}:
        raise RuntimeError('Actual CMake feature configuration mismatch.')
    shutil.copyfile(obj/'CMakeCache.txt',evidence/'CMakeCache.txt')
    ninja=re.search(r'^CMAKE_MAKE_PROGRAM:[^=]+=(.*)$',cache,re.M).group(1)
    commands=subprocess.check_output([ninja,'-t','commands'],cwd=obj)
    (evidence/'native-commands.txt').write_bytes(commands)
    compiled={}
    lines=commands.decode('utf-8',errors='replace').splitlines()
    for name in ('interpexec.cpp','eetwain.cpp','exceptionhandling.cpp','assemblynative.cpp',
                 'customassemblybinder.cpp','comutilnative.cpp','qcallentrypoints.cpp'):
        owners=[line for line in lines if name in line and ' -c ' in line]
        objects=list(obj.rglob(name+'.obj'))
        if not owners or not objects: raise RuntimeError('Actual owner/object missing: '+name)
        if not all('-DFEATURE_INTERPRETER' in owner and '-DDEBUG ' not in owner and '/O2 ' in owner for owner in owners):
            raise RuntimeError('Release interpreter compile contract missing: '+name)
        compiled[name]={'compileCommands':owners,'objects':{str(path.relative_to(obj)):{'sha256':sha(path),'size':path.stat().st_size} for path in objects}}
    critical=('coreclr.dll','clrinterpreter.dll','clrjit.dll','System.Private.CoreLib.dll',
              'IL/System.Private.CoreLib.dll','x64/crossgen2/crossgen2.exe',
              'x64/crossgen2/clrjit_win_x64_x64.dll','x64/crossgen2/jitinterface_x64.dll')
    product_hashes={relative:sha(product/relative) for relative in critical}
    build['candidateCommit']=candidate_commit
    build['candidateValidation']=candidate_validation
    build['candidateCheckerSha256']=checker_hash
    build['configuration']='Release'
    build['cmakeFeatures']=features
    build['sourceHashes']=hashes
    build['compiledOwners']=compiled
    build['criticalProductHashes']=product_hashes
    build['nativeCommandsSha256']=sha(evidence/'native-commands.txt')
    build['cmakeCacheSha256']=sha(evidence/'CMakeCache.txt')
    save(evidence/'build-result.json',build)
    base_receipt=json.loads((baseline/'layout-receipt.json').read_text(encoding='utf-8-sig'))
    base_layout=baseline/'layout'
    base_framework=base_layout/'shared/Microsoft.NETCore.App/12.0.0'
    for name,expected in base_receipt['allLayoutHashes'].items():
        if sha(base_layout/name)!=expected: raise RuntimeError('Baseline layout changed: '+name)
    layout=evidence/'layout'
    shutil.copytree(base_layout,layout)
    framework=layout/'shared/Microsoft.NETCore.App/12.0.0'
    overlays=[]
    symbol_overlays={}
    omitted_old_symbols=[]
    for path in product.glob('*.dll'):
        if (framework/path.name).exists():
            shutil.copyfile(path,framework/path.name)
            overlays.append(path.name)
            candidates=(product/'PDB'/path.with_suffix('.pdb').name,path.with_suffix('.pdb'))
            pdb=next((item for item in candidates if item.exists()),None)
            target_symbol=framework/path.with_suffix('.pdb').name
            if pdb is not None:
                shutil.copyfile(pdb,target_symbol)
                symbol_overlays[path.name]={'source':str(pdb),'sha256':sha(pdb)}
            elif target_symbol.exists():
                omitted_old_symbols.append(target_symbol.name)
                target_symbol.unlink()
    for name in ('coreclr.dll','clrinterpreter.dll','clrjit.dll','System.Private.CoreLib.dll','mscordaccore.dll','mscordbi.dll'):
        if name not in overlays: raise RuntimeError('Required native/CoreLib overlay missing: '+name)
    for name in ('coreclr.dll','clrinterpreter.dll','clrjit.dll','mscordaccore.dll','mscordbi.dll'):
        if name not in symbol_overlays: raise RuntimeError('Fresh native PDB overlay missing: '+name)
    library_hashes={str(path.relative_to(layout)):sha(path) for path in layout.rglob('*') if path.is_file()}
    stamps_text=subprocess.check_output(['pwsh','-NoProfile','-Command',
        '$p='+"'"+str(framework).replace("'","''")+"'; @('coreclr.dll','clrjit.dll','clrinterpreter.dll') | ForEach-Object { [ordered]@{name=$_;stamp=(Get-Item -LiteralPath (Join-Path $p $_)).VersionInfo.ProductVersion} } | ConvertTo-Json"],text=True)
    stamps=json.loads(stamps_text)
    if any(candidate_commit not in item['stamp'] for item in stamps): raise RuntimeError('Native source stamp mismatch.')
    result={'passed':True,'candidateCommit':candidate_commit,'candidateValidation':candidate_validation,
            'candidateCheckerSha256':checker_hash,'upstreamBase':BASE,'configuration':'Release','platform':'windows.x64',
            'runtime':str(runtime),'layout':str(layout),'product':str(product),
            'buildResultSha256':sha(evidence/'build-result.json'),'buildRequestSha256':sha(evidence/'request.json'),
            'baselineReceiptSha256':sha(baseline/'layout-receipt.json'),'baselinePath':str(baseline),
            'overlay':overlays,'nativeStamps':stamps,'allLayoutHashes':library_hashes,
            'symbolOverlays':symbol_overlays,'omittedOldSymbols':omitted_old_symbols,
            'preparationReceiptSha256':PREPARATION_SHA,'baselineControlReceiptSha256':BASELINE_RECEIPT_SHA,
            'criticalProductHashes':product_hashes,
            'scope':'matching fresh Release runtime/CoreLib/compiler over unchanged same-upstream-base Release framework libraries/hosts; not shipping packs'}
    save(evidence/'layout-receipt.json',result)
    print('PASS matching Release build/layout,',len(hashes),'patch sources,',len(compiled),'owners,',len(library_hashes),'layout files',flush=True)

if __name__=='__main__':
    main()
