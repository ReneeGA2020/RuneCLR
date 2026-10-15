#!/usr/bin/env python3
"""Read-only append-only assessment of a Release package entry capture."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tarfile

def helper(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--capture',type=Path,required=True)
    out=parser.parse_args().capture.resolve()
    if (out/'entry-assessment.json').exists():raise RuntimeError('Preserve existing assessment')
    common,mobile,capture=helper('ios-r2r-fix-verify'),helper('verify-ios-packages'),helper('ios-release-package-entry-capture')
    load=lambda name:json.loads((out/name).read_text())
    identity,config,prior,bp=load('identity.json'),load('capture-config.json'),load('results.json'),load('breakpoints.json')
    entries,query,end,sim=load('interpreter-entries.json'),load('unified-query.json'),load('unified-query-completed.json'),load('simulator.json')
    pid=int(re.search(r': ([0-9]+)',(out/'launch.log').read_text()).group(1))
    events=capture.unified_events(out/'managed.unified.log',pid)
    passes=[event for event in events if event.get('eventMessage','').startswith('PASS ')]
    summaries=[event for event in events if event.get('eventMessage')=='15/15 package execution tests passed.']
    stdout=(out/'managed.stdout.log').read_text()
    installed=Path(re.search(r'R2R_NATIVE_LOADED=(.*)/framework.dylib',stdout).group(1))
    controlled=Path(next(iter(config['modules'])).split('/Documents/controlled/')[0])/'Documents/controlled'
    required=capture.required_keys()
    counts={key:sum(e['relativePath']+':'+e['metadataMethodName']==key for e in entries) for key in sorted(required)}
    valid=[]
    for e in entries:
        m=config['modules'].get(e['modulePath'])
        valid.append(bool(m and e['fileSha256']==m['sha256'] and e['relativePath']==m['relativePath']
            and m['methods'].get(e['metadataMethodName'])==e['methodDefToken'] and e['nativeModule']=='libcoreclr.dylib'
            and e['collectible'] and e['bytecodeStart']==e['methodDescBytecodeStart']
            and e['firstOpcodeAddress']==e['bytecodeStart']+8 and e['bytecodeSizeSlots']>0 and e['bytecodePrefixHex']
            and e['pc']==bp['stubAddress' if e['kind']=='stub' else 'childAddress']))
    normal=bool(prior['lldbExit']==0 and prior['normalExit'] and 'CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0' in stdout
        and re.search(r'exited with status = 0',(out/'lldb.log').read_text()))
    native=Path(identity['native'])
    checks={'methodEntries':len(required)==23 and set(prior['requiredMethodEntryCounts'])==required
        and set(config['requiredMethods'])==required and all(counts.values()) and all(valid),
        'noReadErrors':not (out/'capture-errors.json').exists(),'normalNativeExit':normal,
        'functional':len(passes)==15 and len(summaries)==1 and not any(e.get('eventMessage','').startswith('FAIL ') for e in events),
        'queryIdentity':query['appPid']==pid and query['simulator']==sim['uuid'] and query['command'][-1]=='processIdentifier == '+str(pid),
        'bundleUnchanged':mobile.tree(installed)==identity['bundleFiles']==mobile.tree(Path(identity['app'])),
        'payloadUnchanged':mobile.tree(controlled)==identity['payloadHashes'],
        'packageInputsUnchanged':all(common.sha(Path(identity['packages'])/p)==h for p,h in identity['payloadHashes'].items()),
        'driverUnchanged':common.sha(out/'driver.py')==identity['driverSha256'],
        'nativeUnchanged':common.sha(native)==identity['nativeSha256'] and common.sha(native.with_name(native.name+'.dwarf'))==identity['dwarfSha256']
            and mobile.macho_sections(installed/'libcoreclr.dylib')==identity['nativeSections'],
        'simulatorShutdown':sim['shutdownExit']==0}
    hashes={p.name:common.sha(p) for p in out.iterdir() if p.is_file() and p.suffix in ('.json','.log','.py','.lldb','.gz')}
    gates=load('preparation-gates.json')
    gate_kinds=[sorted({e['kind'] for e in entries if e['modulePath']==g['modulePath'] and e['methodDefToken']==g['methodDefToken']}) for g in gates]
    result={'passed':all(checks.values()),'checks':checks,'methodInterpreterProof':checks['methodEntries'] and normal,
        'functionalPassed':checks['functional'] and normal,'appRerun':False,'originalResultsPreserved':True,
        'originalAggregatePassed':prior['passed'],'parserIssue':'Raw JSON escapes slashes; parse actual eventMessage values',
        'requiredMethodGroups':len(required),'requiredMethodEntryCounts':counts,'validEntries':len(entries),
        'entryKinds':prior['entryKinds'],'processId':pid,'individualPassCount':len(passes),'unifiedEventCount':len(events),
        'summaryEvents':summaries,'passEvents':passes,'queryStartUtc':query['startUtc'],'queryEndUtc':end['endUtc'],
        'queryCommand':query['command'],'preparationGateExecutionKinds':gate_kinds,'originalFileHashes':hashes,
        'assessmentDriverSha256':common.sha(__file__),'readerSha256':common.sha(capture.__file__),
        'scope':'Execution entry samples and same-run functional completion; not complete invocation capture or physical-device acceptance'}
    common.write(out/'entry-assessment.json',result)
    shutil.copy2(__file__,out/'entry-assessment-driver.py');shutil.copy2(capture.__file__,out/'entry-assessment-reader.py')
    archive_path=out/'entry-assessment-evidence.tar.gz'
    if archive_path.exists():raise RuntimeError('Preserve existing archive')
    with tarfile.open(archive_path,'w:gz') as archive:
        for p in sorted(out.iterdir()):
            if p.is_file() and p.suffix in ('.json','.log','.py','.lldb'):archive.add(p,arcname=p.name)
        for name in ('ios-r2r-fix-verify','verify-ios-packages','ios-r2r-release-verify'):
            archive.add(Path(__file__).with_name(name+'.py'),arcname=name+'.py')
    print(json.dumps({'passed':result['passed'],'checks':checks,'groups':len(required),'entries':len(entries),
        'archive':str(archive_path),'size':archive_path.stat().st_size,'sha256':common.sha(archive_path)}))
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())

