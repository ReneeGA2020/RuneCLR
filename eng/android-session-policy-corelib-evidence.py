#!/usr/bin/env python3
"""Freeze matching CoreLib trim inputs, optionally regenerating after incremental cleanup."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('build', 'assessment', 'output'):
        p.add_argument('--' + n, type=Path, required=True)
    p.add_argument('--configuration', choices=('Checked', 'Release'), default='Checked')
    p.add_argument('--freeze-only', action='store_true', help='Copy existing assessed bytes without invoking any build')
    a = p.parse_args()
    source = a.build.resolve() / 'runtime'
    out = a.output.resolve()
    assert not out.is_relative_to(source)
    out.mkdir(exist_ok=False)
    completed, assessed = read(a.build / 'results.json'), read(a.assessment / 'results.json')
    provenance = read(a.build / 'source.json')
    assert completed['success'] and assessed['success']
    assert completed['base'] == provenance['base'] == '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
    assert completed['commit'] == provenance['commit'] == assessed['candidateCommit'] == '1724cdec553a7aff7a373a271a4be612651c7625'
    assert completed['tree'] == provenance['tree'] == '71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2'
    assert completed['target'] == 'android.x64' and completed['configuration'] == a.configuration
    assert assessed.get('configuration', 'Checked') == a.configuration
    product = source / ('artifacts/bin/coreclr/android.x64.' + a.configuration)
    compiler = Path(completed['crossgen2'])
    paths = {n:Path(completed[n]) for n in ('native','corelib','crossgen2','interpreter','targetJit')}
    paths.update(jitinterface=compiler.parent/'libjitinterface_arm64.dylib',
                 crossarchJit=compiler.parent/'libclrjit_unix_x64_arm64.dylib')
    assert {n:sha(f) for n,f in paths.items()} == assessed['criticalHashes']
    assert all(f.resolve().is_relative_to(product.resolve()) for f in paths.values())
    assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip() == completed['commit']
    assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD^{tree}'],text=True).strip() == completed['tree']
    assert len(provenance['sourceHashes']) == 27 and all(sha(source/n)==h for n,h in provenance['sourceHashes'].items())
    metadata = read(a.assessment / 'metadata-assessment.json')
    command = ['./build.sh','clr.corelib','-os','android','-arch','x64','-cross',
               '-c','Release','-rc',a.configuration,'-lc','Release','-clrinterpreter',
               '-rebuild','/m:1','/p:RuntimeFlavor=CoreCLR']
    env = dict(os.environ)
    for n in ('CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','OBJC_INCLUDE_PATH',
              'LIBRARY_PATH','SDKROOT','MACOSX_DEPLOYMENT_TARGET','CMAKE_PREFIX_PATH','PKG_CONFIG_PATH'):
        env.pop(n,None)
    root = a.build.resolve().parent
    original_request = read(a.build / 'request.json')
    assert original_request['configuration'] == a.configuration
    env.update(PATH=str(root/'tools/bin')+':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
               ANDROID_NDK_ROOT=original_request['ndk'],ANDROID_NDK_HOME=original_request['ndk'],
               DOTNET_CLI_HOME=str(out/'dotnet-home'),MSBUILDDISABLENODEREUSE='1',
               DOTNET_CLI_USE_MSBUILD_SERVER='0')
    request = {'command':None if a.freeze_only else command,'buildInvoked':not a.freeze_only,
               'configuration':a.configuration,'target':'android.x64','base':completed['base'],
               'commit':completed['commit'],'tree':completed['tree'],'criticalBefore':assessed['criticalHashes'],
               'sourceReceiptSha256':sha(a.build/'source.json'),'sourceHashes':provenance['sourceHashes'],
               'metadataBeforeSha256':sha(a.assessment/'metadata-assessment.json'),
               'driverSha256':sha(__file__),'executionVerified':False}
    (out/'request.json').write_text(json.dumps(request,indent=2)+chr(10))
    if a.freeze_only:
        status = 0
    else:
        with (out/'build.log').open('w') as log:
            status = subprocess.run(command,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
    (out/'build.exit').write_text(str(status)+chr(10))
    after = {n:sha(f) if f.exists() else None for n,f in paths.items()}
    copies = []
    for i,row in enumerate(metadata['stages']):
        origin = Path(row['path'])
        if origin.is_file():
            target = out/'managed-pe'/('stage'+str(i)+'-'+origin.name)
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(origin,target)
            copies.append({'originalPath':str(origin),'path':str(target),'sha256':sha(target),
                           'originalAssessmentSha256':row['sha256'],'matchesOriginal':sha(target)==row['sha256']})
    descriptor = source/('artifacts/obj/coreclr/System.Private.CoreLib/android.x64.' + a.configuration + '/ILLink.Descriptors.xml')
    if descriptor.exists():
        shutil.copy2(descriptor,out/descriptor.name)
    clean = not subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no'],text=True).strip()
    result = {'success':status==0 and after==assessed['criticalHashes'] and clean and
                        len(copies)==4 and all(r['matchesOriginal'] for r in copies),
              'buildExit':status,'coreCriticalUnchanged':after==assessed['criticalHashes'],
              'configuration':a.configuration,'target':'android.x64','base':completed['base'],
              'commit':completed['commit'],'tree':completed['tree'],'buildInvoked':not a.freeze_only,
              'criticalAfter':after,'sourceTrackedClean':clean,'frozenStages':copies,
              'descriptorMatchesOriginal':descriptor.exists() and sha(descriptor)==metadata['descriptorSha256'],
              'descriptorPath':str(out/descriptor.name),'descriptorSha256':sha(out/descriptor.name) if (out/descriptor.name).exists() else None,
              'metadataAssessment':str(a.assessment.resolve()/'metadata-assessment.json'),
              'metadataAssessmentSha256':sha(a.assessment/'metadata-assessment.json'),
              'executionVerified':False,'scope':'Recreated bytes must match prior actual assessment; no new runtime capability'}
    result['success'] = result['success'] and result['descriptorMatchesOriginal']
    (out/'results.json').write_text(json.dumps(result,indent=2)+chr(10))
    print(json.dumps(result,indent=2),flush=True)
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
