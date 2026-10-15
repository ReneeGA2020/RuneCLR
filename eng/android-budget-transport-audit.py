#!/usr/bin/env python3
"""Offline ownership, raw-row and cleanup review of Android budget transport."""
import argparse
import importlib.util
import json
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('run', 'supplement', 'apk', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    spec = importlib.util.spec_from_file_location('budget_rows', Path(__file__).with_name('mobile-host-budget-audit.py'))
    rows = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rows)
    load, sha = rows.load, rows.sha
    original = load(args.run / 'results.json')
    pull = load(args.supplement / 'pull-results.json')
    state = load(args.apk / 'state.json')
    request = load(args.run / 'request.json')
    assert original['passed'] and original['debuggerTransportPassed']
    assert original['nativeEntryProof'] is False and original['debugger'] is True
    assert pull['passed'] and pull['priorRunResultSha256'] == sha(args.run / 'results.json')
    for root, hashes in ((args.run, original['rawHashes']), (args.supplement, pull['rawHashes'])):
        for path, expected in hashes.items():
            assert sha(root / path) == expected
    assert sha(args.apk / 'entry-driver.py') == load(args.apk / 'entry-build.json')['entryDriverSha256']
    assert sha(args.run / 'driver.py') == original['driverSha256']
    assert sha(state['apk']) == request['apkSha256'] == state['apkSha256']
    inputs = rows.inputs(args.inputs)
    assert inputs['files'] == state['inputFiles']
    assert sha(args.inputs / 'input-manifest.json') == state['inputManifestSha256']
    before, after = load(args.run / 'installed-before.json'), load(args.run / 'installed-after.json')
    expected = {**state['appHashes'], **state['authorHashes'], 'apk/base.apk': state['apkSha256']}
    assert before == after == expected and len(before) == original['installedEntries']
    build = load(args.apk / 'matching-build-review.json')
    assert request['sourceTree'] == state['runtimeTree'] == build['tree']
    assert sha(args.apk / 'matching-build-review.json') == state['buildReviewSha256']
    assert sha(args.apk / 'layout.json') == state['layoutSha256']
    assert original['actualCoreclrSha256'] == before['libcoreclr.so'] == build['criticalHashes']['native']
    assert before['libclrinterpreter.so'] == build['criticalHashes']['interpreter']
    pid, nonce = original['appPid'], original['nonce']
    assert pull['appPid'] == pid and pull['nonce'] == request['nonce'] == nonce
    assert (args.run / 'pid-query.txt').read_text().strip() == f'android.os.Process.myPid={pid}'
    aggregate, receipts, metrics, hashes = rows.adapter(args.supplement / 'adapter', nonce, pid)
    negatives = rows.negative_controls(aggregate, receipts, nonce, pid)
    native = (args.supplement / 'native.log').read_text()
    before_native = (args.run / 'before-native.log').read_text()
    header = f'MOBILE_BUDGET_NATIVE pid={pid} nonce={nonce} InterpMode=0 RuneCLRInterpretCollectible=0 ReadyToRun=1'
    gate = f'ANDROID_ENTRY_GATE pid={pid} runId={nonce}'
    assert header in before_native and 'CORECLR_INITIALIZE_HRESULT' not in before_native
    assert gate + ' state=waiting dumpableResult=0' in before_native
    assert header in native and gate + ' state=released' in native
    assert re.findall(r'^CORECLR_INITIALIZE_HRESULT=.*$', native, re.M) == ['CORECLR_INITIALIZE_HRESULT=0x0']
    assert re.findall(r'^CORECLR_EXECUTE_HRESULT=.*$', native, re.M) == ['CORECLR_EXECUTE_HRESULT=0x0;RUNECLR_EXIT=0']
    managed = load(args.supplement / 'managed-result.json')
    assert managed['appPid'] == pid and managed['nonce'] == nonce and managed['exitCode'] == 0
    assert all(managed[k] == 1 for k in ('policy', 'meter', 'terminal', 'gc')) and managed['defaultPolicy'] == 0
    assert original['lldbExit'] == original['instrumentationExit'] == 0
    assert re.findall(r'^INSTRUMENTATION_RESULT: return-code=([0-9-]+)\r?$', (args.run / 'instrumentation.log').read_text(), re.M) == ['0']
    debug = (args.run / 'lldb.log').read_text()
    assert f'Process {pid} detached' in debug and 'error:' not in debug.lower() and 'Traceback' not in debug
    core = args.apk / 'app/libcoreclr.so'
    assert 'CORECLR_MEMORY_PREFIX=' + core.read_bytes()[:16].hex() in debug
    maps = (args.run / 'pre-init-maps.log').read_text()
    zero = [line.split() for line in maps.splitlines() if line.endswith(original['actualCoreclrPath']) and int(line.split()[2], 16) == 0]
    assert len(zero) == 1 and int(zero[0][0].split('-')[0], 16) == int(original['coreclrSlide'], 16)
    assert sha(args.run / 'app_process64') == original['actualExecutableSha256']
    commands = load(args.run / 'commands.json')
    removals = [c for c in commands if c['command'][3:5] == ['forward', '--remove']]
    assert len(removals) == 1 and removals[0]['exit'] == 0
    result = {'passed': True, 'debuggerTransportPassed': True, 'nativeEntryProof': False,
              'processId': pid, 'nonce': nonce, 'cases': 15, 'contexts': 73,
              'installedEntries': len(before), 'negativeControls': negatives,
              'originalResultSha256': sha(args.run / 'results.json'), 'adapterHashes': hashes,
              'assessorSha256': sha(__file__), 'rowAssessorSha256': sha(rows.__file__),
              'scope': 'Debugger transport and exact same-run budget rows; no interpreter method-entry samples'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('adapterHashes', 'negativeControls')}, indent=2))
    print('PASS negative controls:', len(negatives))


if __name__ == '__main__':
    main()
