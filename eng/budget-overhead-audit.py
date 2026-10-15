#!/usr/bin/env python3
"""Read-only binding review of a pinned-CPU budget benchmark's actual raw outputs."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import statistics

CHECKER_PATH=Path(__file__).with_name('budget-runtime-candidate.py')
_spec=importlib.util.spec_from_file_location('budget_runtime_candidate',CHECKER_PATH)
_candidate=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_candidate)

def verify_candidate(directory,request,candidate_commit):
    assert request['candidateCommit']==candidate_commit
    proof=request.get('candidateValidation')
    if proof is None:
        # Historical baseline records precede the candidate checker. Their frozen
        # evidence remains baseline-only; no new candidate can reuse that exemption.
        assert candidate_commit==_candidate.BASELINE
        return
    actual=_candidate.validate(Path(request['runtime']),candidate_commit)
    assert proof==actual and request['upstreamBase']==_candidate.UPSTREAM
    expected=sha(CHECKER_PATH)
    assert request['candidateCheckerSha256']==expected
    assert sha(directory/'source/eng/budget-runtime-candidate.py')==expected
    binding=request['runtimeBuildBinding']
    assert binding['candidateValidation']==actual and binding['candidateCheckerSha256']==expected
    assert sha(directory/'provenance/budget-runtime-candidate.py')==expected
    meter=directory/'provenance/runtime-source'/_candidate.METER
    normalized=meter.read_bytes().replace(b'\r\n',b'\n')
    assert hashlib.sha256(normalized).hexdigest()==actual['candidateBlobSha256']
    build_request=json.loads((directory/'provenance/build-request.json').read_text(encoding='utf-8-sig'))
    if candidate_commit!=_candidate.BASELINE or 'candidateValidation' in build_request:
        for filename in ('build-request.json','build-result.json','layout-receipt.json'):
            value=json.loads((directory/'provenance'/filename).read_text(encoding='utf-8-sig'))
            assert value['candidateValidation']==actual and value['candidateCheckerSha256']==expected
        assert sha(directory/'provenance/build-candidate-checker.py')==expected
    assert candidate_commit in request['runtimeProductStamp']

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify_configuration(directory,request,result):
    configuration=request.get('configuration','Checked')
    assert configuration in ('Checked','Release')
    assert result.get('configuration',configuration)==configuration
    assert request['platform']=='Windows x64 '+configuration and request['runtimeSourceTrackedClean']
    expected_scope=('experimental '+configuration+' incremental configured-meter cost, not full instrumentation overhead or '+
                    ('Release/' if configuration=='Checked' else '')+'mobile/game performance')
    assert request['scope']==expected_scope and result['limits']==expected_scope
    binding=request.get('runtimeBuildBinding')
    if binding is None:
        # Legacy Checked records predate frozen build metadata. Verify their live
        # matching product/cache; a later request cannot relabel them as Release.
        assert configuration=='Checked' and 'configuration' not in request
        runtime=Path(request['runtime'])
        cache=(runtime/'artifacts/obj/coreclr/windows.x64.Checked/CMakeCache.txt').read_text()
        for name in ('coreclr.dll','clrinterpreter.dll','clrjit.dll','System.Private.CoreLib.dll'):
            expected=next(value for path,value in request['runtimeHashes'].items() if Path(path).name==name)
            assert sha(runtime/'artifacts/bin/coreclr/windows.x64.Checked'/name)==expected
    else:
        assert binding['configuration']==configuration and binding['actualSourceCommit']==request['candidateCommit']
        for relative,expected in binding['metadataHashes'].items(): assert sha(directory/relative)==expected
        cache=(directory/'provenance/CMakeCache.txt').read_text()
        build_request=json.loads((directory/'provenance/build-request.json').read_text(encoding='utf-8-sig'))
        built=json.loads((directory/'provenance/build-result.json').read_text(encoding='utf-8-sig'))
        layout=json.loads((directory/'provenance/layout-receipt.json').read_text(encoding='utf-8-sig'))
        assert build_request['candidateCommit']==request['candidateCommit']==layout['candidateCommit']
        assert built['exitCode']==0 and layout['passed']
        arguments=build_request['arguments']
        assert arguments[arguments.index('-configuration')+1]==configuration and '-clrinterpreter' in arguments
        if configuration=='Release':
            assert built['configuration']==layout['configuration']==configuration
            assert sha(directory/'provenance/build-result.json')==layout['buildResultSha256']
            assert sha(directory/'provenance/build-request.json')==layout['buildRequestSha256']
            assert sha(directory/'provenance/build.stdout')==built['stdoutSha256']
            assert sha(directory/'provenance/build.stderr')==built['stderrSha256']
            assert sha(directory/'provenance/CMakeCache.txt')==built['cmakeCacheSha256']
            assert sha(directory/'provenance/native-commands.txt')==built['nativeCommandsSha256']
            recorded_products=built['criticalProductHashes']
            assert layout['criticalProductHashes']==recorded_products
            assert build_request['sourceHashes']==built['sourceHashes']
            for relative,expected in build_request['sourceHashes'].items():
                source=directory/'provenance/runtime-source'/relative
                if binding.get('version',1)>=2: assert sha(source)==expected
        else:
            compiled=json.loads((directory/'provenance/compile-evidence.json').read_text(encoding='utf-8-sig'))
            assert compiled['passed'] and compiled['candidateCommit']==request['candidateCommit']
            assert sha(directory/'provenance/native-commands.txt')==compiled['nativeCommandsSha256']
            recorded_products=compiled['criticalProductHashes']
        assert binding['criticalProductHashes']==recorded_products
        assert len(recorded_products)==8
        if binding.get('version',1)>=2:
            assert len(request['hostBuildSdkSha256'])==64 and request['hostBuildSdkVersion']=='11.0.100-rc.1.26425.128'
            for name in ('BudgetKernel','BudgetOverhead'):
                host_build=json.loads((directory/('build-'+name+'.process.json')).read_text())
                assert host_build['argv'][0]==request['hostBuildSdk'] and host_build['exitCode']==0 and not host_build['timedOut']
        for name in ('coreclr.dll','clrinterpreter.dll','clrjit.dll','System.Private.CoreLib.dll'):
            expected=next(value for path,value in request['runtimeHashes'].items() if Path(path).name==name)
            assert recorded_products[name]==expected
    keys=('CLR_CMAKE_TARGET_ARCH','CLR_CMAKE_TARGET_OS','CMAKE_BUILD_TYPE','FEATURE_INTERPRETER','FEATURE_DYNAMIC_CODE_COMPILED')
    features={key:re.search(r'^'+key+r':[^=]+=(.*)$',cache,re.M).group(1) for key in keys}
    assert features=={'CLR_CMAKE_TARGET_ARCH':'x64','CLR_CMAKE_TARGET_OS':'windows','CMAKE_BUILD_TYPE':configuration,
                      'FEATURE_INTERPRETER':'1','FEATURE_DYNAMIC_CODE_COMPILED':'1'}
    if binding is not None: assert binding['cmakeFeatures']==features
    return configuration

def verify(directory, result, request_override=None, candidate_commit=_candidate.BASELINE):
    request_path = directory/'request.json'
    identity_path = directory/'managed-identity.json'
    request = request_override if request_override is not None else json.loads(request_path.read_text(encoding='utf-8'))
    assert result['passed'] and result['requestSha256'] == sha(request_path)
    assert result['managedIdentitySha256'] == sha(identity_path)
    verify_candidate(directory,request,candidate_commit)
    configuration=verify_configuration(directory,request,result)
    for relative, expected in request['sourceHashes'].items():
        assert sha(directory/'source'/relative) == expected, relative
    for relative, expected in json.loads(identity_path.read_text()).items():
        assert sha(directory/relative) == expected, relative
    # Independent checksum from the fixture's stated uint32 recurrence.
    state, checksum = 12345, 0
    for _ in range(100_000):
        state = (state*1664525+1013904223) & 0xffffffff
        checksum += state & 255
    assert checksum == 12749776
    lanes = result['lanes']
    assert len(lanes) == request['pairs'] * 2
    for pair in range(request['pairs']):
        paired = sorted((lane for lane in lanes if lane['pair'] == pair), key=lambda item:item['position'])
        expected_modes = ['no-config','high-budget'] if pair%2 == 0 else ['high-budget','no-config']
        assert [lane['receipt']['mode'] for lane in paired] == expected_modes
    for lane in lanes:
        label, receipt, raw = lane['label'], lane['receipt'], lane['raw']
        process_path = directory/(label+'.process.json')
        assert json.loads(process_path.read_text()) == raw
        assert sha(directory/(label+'.stdout')) == raw['stdoutSha256']
        assert sha(directory/(label+'.stderr')) == raw['stderrSha256']
        assert json.loads((directory/(label+'.stdout')).read_text(encoding='utf-8-sig')) == receipt
        assert receipt['passed'] and receipt['processId'] == raw['pid'] and not raw['timedOut'] and raw['exitCode'] == 0
        assert receipt['nonce'] in label and receipt['nonce'] in raw['argv']
        assert receipt['affinity'] == 4 and receipt['architecture'] == 'X64' and receipt['directCollected']
        assert not receipt['hostProof']['Interpreted'] and receipt['hostProof']['Method'] == 'RuneCLR.Runtime.MapRunner.Run'
        assert len(receipt['Proof']) == 2
        assert {item['Method'] for item in receipt['Proof']} == {
            'RuneCLR.BudgetKernel.Kernel.Execute','RuneCLR.BudgetKernel.Kernel.Update'}
        assert all(item['Interpreted'] and item['StubType']==6 for item in receipt['Proof'])
        assert len(receipt['Callbacks']) == request['samplesPerProcess'] == receipt['sampleCount']
        assert receipt['sessionCollected'] == request['samplesPerProcess']+3
        budgeted = receipt['mode'] == 'high-budget'
        for sample in receipt['Callbacks']:
            assert sample['Checksum'] == checksum and sample['Milliseconds'] > 0
            assert sample['AllocatedBytes'] == 0 and sample['GcCounts'] == [0,0,0]
            if budgeted:
                assert sample['ExecutedAfter']-sample['ExecutedBefore'] == sample['DispatchDelta'] == 2600016
            else:
                assert sample['ExecutedBefore'] is sample['ExecutedAfter'] is sample['DispatchDelta'] is None
        assert len(receipt['Samples']) == request['samplesPerProcess']+3
        assert sum(sample['Warmup'] for sample in receipt['Samples']) == 3
        for sample in receipt['Samples']:
            assert sample['Checksum'] == 3*checksum and sample['Milliseconds'] > 0
            if budgeted:
                snapshot=sample['Budget']
                assert snapshot['ExecutionExecuted'] == 7800101 and snapshot['ExecutionRemaining']+snapshot['ExecutionExecuted']==receipt['budgetLimit']
                assert not snapshot['IsTerminated'] and not snapshot['ExecutionExhausted'] and snapshot['Reason']==0
                assert snapshot['CleanupExecuted']==0 and snapshot['CleanupRemaining']==4096
            else:
                assert sample['Budget'] is None
        if budgeted:
            final=receipt['FinalSnapshot']
            assert final['ExecutionExecuted'] == (request['samplesPerProcess']+3)*2600016
            assert final['ExecutionRemaining']+final['ExecutionExecuted'] == receipt['budgetLimit']
            assert not final['IsTerminated'] and not final['ExecutionExhausted'] and final['Reason']==0
        else:
            assert receipt['FinalSnapshot'] is None and receipt['budgetLimit'] is None
    assert set(result['summaries'])=={'no-config','high-budget'}
    for mode, summary in result['summaries'].items():
        chosen = [lane for lane in lanes if lane['receipt']['mode'] == mode]
        callbacks = [sample['Milliseconds'] for lane in chosen for sample in lane['receipt']['Callbacks']]
        sessions = [sample['Milliseconds'] for lane in chosen for sample in lane['receipt']['Samples'] if not sample['Warmup']]
        assert summary['callbackMedianMs'] == statistics.median(callbacks)
        assert summary['sessionMedianMs'] == statistics.median(sessions)
        assert summary['processes']==len(chosen)==request['pairs']
        assert summary['callbackSamples']==len(callbacks)==request['pairs']*request['samplesPerProcess']
        assert summary['callbackMinMs']==min(callbacks) and summary['callbackMaxMs']==max(callbacks)
        assert summary['sessionMinMs']==min(sessions) and summary['sessionMaxMs']==max(sessions)
        assert summary['setupMedianMs']==statistics.median(lane['receipt']['SetupMilliseconds'] for lane in chosen)
    summaries=result['summaries']
    assert result['configuredMeterIncrementPercentFromPooledMedian']==100*(summaries['high-budget']['callbackMedianMs']/summaries['no-config']['callbackMedianMs']-1)
    assert len(result['pairedRounds'])==request['pairs']
    for pair,review in enumerate(result['pairedRounds']):
        chosen={lane['receipt']['mode']:lane for lane in lanes if lane['pair']==pair}
        medians={mode:statistics.median(sample['Milliseconds'] for sample in lane['receipt']['Callbacks']) for mode,lane in chosen.items()}
        assert review['pair']==pair and review['callbackMediansMs']==medians
        assert review['configuredMeterIncrementPercent']==100*(medians['high-budget']/medians['no-config']-1)
    return {'candidateCommit':candidate_commit,'configuration':configuration,'pairedRounds':request['pairs'],'processes':len(lanes), 'callbackSamplesPerMode':request['pairs']*request['samplesPerProcess'],
            'contextsCollected':len(lanes)*(1+request['samplesPerProcess']+3), 'checksum':checksum,
            'budgetedCallbackDispatchDelta':2600016, 'budgetedSessionExecuted':7800101}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--candidate-commit',default=_candidate.BASELINE)
    args=parser.parse_args()
    directory=Path(args.evidence).resolve()
    output=Path(args.output).resolve()
    if output.exists(): raise ValueError('Fresh review output required.')
    result_path=directory/'results.json'
    result=json.loads(result_path.read_text())
    evidence=verify(directory,result,candidate_commit=args.candidate_commit)
    controls=[]
    for name in ('pid','entry-proof','dispatch-delta','raw-hash','pooled-percent','paired-percent','summary-count','scope','configuration-label','candidate-label','candidate-proof','candidate-checker'):
        altered=copy.deepcopy(result)
        changed_request=None
        lane=next(item for item in altered['lanes'] if item['receipt']['mode']=='high-budget')
        if name=='pid': lane['receipt']['processId']+=1
        elif name=='entry-proof': lane['receipt']['Proof'][0]['Interpreted']=False
        elif name=='dispatch-delta': lane['receipt']['Callbacks'][0]['DispatchDelta']+=1
        elif name=='raw-hash': lane['raw']['stdoutSha256']='0'*64
        elif name=='pooled-percent': altered['configuredMeterIncrementPercentFromPooledMedian']+=1
        elif name=='paired-percent': altered['pairedRounds'][0]['configuredMeterIncrementPercent']+=1
        elif name=='summary-count': altered['summaries']['high-budget']['callbackSamples']+=1
        elif name=='scope': altered['limits']='production Release performance established'
        elif name=='configuration-label':
            changed_request=json.loads((directory/'request.json').read_text())
            fake='Release' if changed_request.get('configuration','Checked')=='Checked' else 'Checked'
            changed_request['configuration']=fake
            changed_request['platform']='Windows x64 '+fake
            changed_request['scope']='experimental '+fake+' incremental configured-meter cost, not full instrumentation overhead or '+('Release/' if fake=='Checked' else '')+'mobile/game performance'
            altered['configuration']=fake
            altered['limits']=changed_request['scope']
        else:
            changed_request=json.loads((directory/'request.json').read_text())
            if name=='candidate-label':
                changed_request['candidateCommit']='0'*40
            elif name=='candidate-proof':
                changed_request['candidateValidation']={'candidateCommit':args.candidate_commit,'kind':'arbitrary-source'}
            else:
                changed_request.setdefault('candidateValidation',{'candidateCommit':args.candidate_commit})
                changed_request['candidateCheckerSha256']='0'*64
        rejected=False
        try: verify(directory,altered,changed_request,args.candidate_commit)
        except (AssertionError,KeyError,ValueError,RuntimeError): rejected=True
        assert rejected,name
        controls.append({'name':name,'rejected':True})
    review={'passed':True,'assessorSha256':sha(__file__),'resultSha256':sha(result_path),
            'evidence':evidence,'corruptionControls':controls,'claims':evidence['configuration']+' incremental meter cost and observed execution/collection only'}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(review,indent=2),encoding='utf-8')
    print(json.dumps(review,indent=2))

if __name__=='__main__':
    main()
