import collections
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tarfile

import argparse
p=argparse.ArgumentParser(description='Read-only new Android budget entry assessment')
for name in ('apk','capture','normal','normal-audit','symbols','contract','metadata','output'):p.add_argument('--'+name,type=Path,required=True)
args=p.parse_args()
apk,run,observe=args.apk,args.capture,args.capture/'observer'
out=args.output.parent
assert not args.output.exists()
load = lambda path: json.loads(path.read_text(encoding='utf-8-sig'))
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
result, state = load(run / 'results.json'), load(apk / 'state.json')
pid, nonce = result['appPid'], result['nonce']
assert pid>0 and re.fullmatch('[0-9a-f]{32}',nonce)
assert state['runtimeTree']=='91673a7980bda79006259e525741fecb04324444'
assert state['runtimeCommit']=='112e97408de1ae1c2a6cbd2967dcd250cd2d491c'
assert result['passed'] and result['lldbExit'] == result['instrumentationExit'] == 0
for relative, expected in result['rawHashes'].items():
    assert sha(run / relative) == expected, relative
config, prep, bp = [load(observe / name) for name in ['capture-config.json', 'preparation.json', 'breakpoints.json']]
assert sha(observe / 'android_entry_lldb.py') == prep['observerSha256']
assert sha(observe / 'capture-config.json') == prep['configSha256']
metadata_path = args.metadata
assert sha(metadata_path) == prep['metadataSha256']
metadata = {m['assembly'] + '.dll': m for m in load(metadata_path)}
for path, module in config['modules'].items():
    m = metadata[module['relativePath']]
    assert sha(Path(m['path'])) == m['sha256'] == module['sha256']
    assert module['moduleMvid'] == m['moduleMvid'] and m['managedNativeRva'] == 0
    assert sha(apk / 'postinstall-author' / module['relativePath']) == m['sha256']
    assert module['methods'] == {row['owner'] + '.' + row['name']: int(row['token'], 16) for row in m['methods']}
assert len(config['modules']) == 2 and len(config['requiredMethods']) == 9
assert config['appPid'] == bp['pid'] == pid and config['runId'] == bp['runId'] == nonce
slide = int(result['coreclrSlide'], 16)
assert bp['dispatch'][0]['line'] == 3751 and bp['dispatch'][0]['address'] == slide + 0x3b0aff
contract = bp['childFrameContract']
static = load(args.contract)
assert static['preparedOnly'] and static['runtimeTree']==state['runtimeTree']
assert contract['filePc'] == 0x3b0aff and contract['frameSpillOffset'] == 0xe48
assert contract['startIpDwarfOffset'] == 8 and contract['opcodeRegister'] == 'r14' and contract['frameRegister'] == 'rbp'
assert contract['localVariableDwarfAvailable'] is False
assert contract['instructions'] == bp['dispatch'][0]['instructions'] == [
    ['movl', '(%r14), %ebx'], ['movq', '-0xe48(%rbp), %rax'], ['movq', '0x8(%rax), %rax'], ['movq', '(%rax), %rax']]
assert contract['precedingReInitHex'] == static['codePieces']['reInit']['hex']
assert result['actualCoreclrSha256'] == static['products']['libcoreclr.so']['sha256'] == sha(apk / 'app/libcoreclr.so')
native_symbols = args.symbols/'libcoreclr.so.dbg'
assert sha(native_symbols)==static['products']['libcoreclr.so']['symbolsSha256']
assert contract['precedingFrameReloadHex']==static['codePieces']['frameReload']['hex']
nm = Path('D:/RuneCLR-Android/sdk/ndk/27.2.12479018/toolchains/llvm/prebuilt/windows-x86_64/bin/llvm-nm.exe')
symbols = subprocess.run([str(nm), '--defined-only', str(native_symbols)], capture_output=True, check=True).stdout.decode()
stub = re.findall(r'^([0-9a-f]+) [A-Za-z] InterpreterStub$', symbols, re.M)
assert len(stub) == 1 and bp['stubAddress'] == slide + int(stub[0], 16)
entries = load(observe / 'interpreter-entries.json')
def validate(samples):
    counts = dict.fromkeys(config['requiredMethods'], 0)
    for e in samples:
        module = config['modules'][e['modulePath']]
        assert e['pid'] == pid and e['runId'] == nonce
        assert e['nativeModule'] == 'libcoreclr.so' and e['collectible'] is True
        assert e['moduleSimpleName'] == module['simpleName']
        assert e['fileSha256'] == module['sha256'] and e['moduleMvid'] == module['moduleMvid']
        assert e['loadedMetadataMvidValidated'] is True and e['loadedPELayout'] in ('flat', 'rva')
        assert e['methodDefToken'] == module['methods'][e['metadataMethodName']]
        assert e['relativePath'] == module['relativePath']
        assert e['bytecodeStart'] == e['methodDescBytecodeStart'] > 0
        assert e['firstOpcodeAddress'] == e['bytecodeStart'] + 8
        assert e['bytecodeSizeSlots'] > 0 and len(bytes.fromhex(e['bytecodePrefixHex'])) == min(64, e['bytecodeSizeSlots'] * 4)
        assert all(e[name] > 0 for name in ['interpMethod', 'methodDesc', 'methodTable', 'managedModule'])
        assert e['kind'] in ('stub', 'child')
        if e['kind'] == 'child':
            assert e['pc'] == bp['dispatch'][0]['address']
            assert e['methodContextFrame'] > 0 and e['childFrameContract'] == contract
            assert e['childDWARF'] is None and e['childRegisters']['rbp'] > 0
            assert e['childRegisters']['r14'] == e['firstOpcodeAddress']
        else:
            assert e['pc'] == bp['stubAddress'] and e['function'] == 'InterpreterStub'
        key = e['relativePath'] + ':' + e['metadataMethodName']
        assert key in counts
        counts[key] += 1
    assert all(counts.values())
    return counts
counts = validate(entries)
raw_entries = [json.loads(line.split('ANDROID_BUDGET_INTERPRETER_ENTRY ', 1)[1])
    for line in (run / 'lldb.log').read_text().splitlines() if line.startswith('ANDROID_BUDGET_INTERPRETER_ENTRY ')]
assert entries == raw_entries
assert not (observe / 'capture-errors.json').exists()
debugger = load(observe / 'debugger-result.json')
assert debugger['pid'] == pid and debugger['runId'] == nonce and debugger['exited'] and debugger['errors'] == 0
assert debugger['exitStatus'] == 9
rejected = []
for field, value in [('methodDefToken', 0), ('pc', 0), ('moduleMvid', 'wrong'), ('methodDescBytecodeStart', 0)]:
    samples = copy.deepcopy(entries)
    samples[0][field] = value
    try:
        validate(samples)
    except (AssertionError, KeyError):
        rejected.append(field)
assert len(rejected) == 4
with tarfile.open(run/'adapter-evidence.tar') as archive:
    for member in archive.getmembers():
        if member.isfile():
            relative=member.name.removeprefix('./')
            assert archive.extractfile(member).read()==(run/'adapter-evidence'/relative).read_bytes()
spec = importlib.util.spec_from_file_location('budget_audit', 'eng/mobile-host-budget-audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
aggregate, rows, metrics, hashes = audit.adapter(run / 'adapter-evidence', nonce, pid)
assert aggregate == load(run / 'adapter-result.json')
ledger_controls = audit.negative_controls(aggregate, rows, nonce, pid)
native, managed = [(run / name).read_text() for name in ['native.log', 'managed.log']]
assert f'MOBILE_BUDGET_NATIVE pid={pid} nonce={nonce} InterpMode=0 RuneCLRInterpretCollectible=0 ReadyToRun=1' in native
assert 'CORECLR_INITIALIZE_HRESULT=0x0' in native and 'CORECLR_EXECUTE_HRESULT=0x0;RUNECLR_EXIT=0' in native
assert f'MOBILE_HOST_BUDGET_COMPLETE nonce={nonce} scenario=all pid={pid} cases=15 contexts=73 passed=true' in managed
instrumentation = (run / 'instrumentation.log').read_text()
assert re.findall(r'^INSTRUMENTATION_RESULT: return-code=([0-9-]+)$', instrumentation, re.M) == ['0']
assert re.findall(r'^INSTRUMENTATION_CODE: ([0-9-]+)$', instrumentation, re.M) == ['0']
java = apk / 'builder/Templates/MonoRunner.java'
assert sha(java) == state['builderGeneratedHashes']['Templates/MonoRunner.java']
assert all(text in java.read_text() for text in ['int retcode = executeEntryPoint(entryPointLibName, argsToForward);', 'result.putInt("return-code", retcode);', 'finish(retcode, result);'])
assert (run / 'pid-query.txt').read_text().strip() == 'android.os.Process.myPid=' + str(pid)
mr = load(run / 'managed-result.json')
assert mr['appPid'] == pid and mr['nonce'] == nonce and mr['exitCode'] == 0
before, after = [load(run / name) for name in ['installed-before.json', 'installed-after.json']]
assert before == after and len(before) == 203
for stage in ['before', 'after']:
    parsed = {}
    for line in (run / ('installed-' + stage + '.sha256sum.log')).read_text().splitlines():
        digest, relative = line.split(None, 1)
        path = relative.strip()
        relative = 'plugin/' + Path(path).name if '/plugin/' in path else 'apk/base.apk' if path.endswith('/base.apk') else Path(path).name
        assert relative not in parsed
        parsed[relative] = digest
    assert parsed == before
normal = load(args.normal_audit)
assert normal['mobileVerified'] and normal['cases'] == 15 and normal['contexts'] == 73
normal_run = args.normal
assert load(normal_run / 'request.json')['apkSha256'] == load(run / 'request.json')['apkSha256'] == state['apkSha256']
assert sha(Path(state['apk'])) == state['apkSha256']
assert 'ANDROID_ENTRY_GATE' not in (normal_run / 'native.log').read_text()
report = {'passed': True, 'nativeEntryProof': True, 'completeInvocationCapture': False,
    'processId': pid, 'nonce': nonce, 'samples': len(entries), 'kinds': dict(collections.Counter(e['kind'] for e in entries)),
    'requiredGroups': len(counts), 'sampledGroups': sum(n > 0 for n in counts.values()), 'groupCounts': counts,
    'negativeControlsRejected': rejected, 'ledgerNegativeControls': len(ledger_controls), 'contexts': 73,
    'installedEntries': len(before), 'debuggerExitStatus': 9, 'nativeManagedInstrumentationExitZero': True,
    'optimizedLocalDwarfAvailable': False, 'actualEmittedChildContractVerified': True,
    'staticSpillReloadOnly': False,'liveSpillReloadVerified':True,'runtimeTree':state['runtimeTree'], 'independentNormalPassed': True,
    'captureRawHashes': len(result['rawHashes']), 'adapterRawHashes': hashes,
    'assessorSha256': sha(Path(__file__)),
    'scope': 'Current author nine method groups sampled; no complete invocation, receiver identity, physical device or live complete invocation claim'}
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+chr(10))
print(json.dumps(report, indent=2))
