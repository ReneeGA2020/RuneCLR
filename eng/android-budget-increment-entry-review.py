#!/usr/bin/env python3
"""Independently cross-check frozen Android samples, native bytes and normal run."""
import argparse
import collections
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import zipfile


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(value, message):
    if not value:
        raise AssertionError(message)


def elf(data):
    check(data[:6] == b'\x7fELF\x02\x01', 'ELF64 little endian')
    phoff, shoff = struct.unpack_from('<QQ', data, 32)
    phsize, phcount, shsize, shcount = struct.unpack_from('<HHHH', data, 54)
    segments = [struct.unpack_from('<IIQQQQQQ', data, phoff + i * phsize) for i in range(phcount)]
    ids = []
    for i in range(shcount):
        section = struct.unpack_from('<IIQQQQIIQQ', data, shoff + i * shsize)
        if section[1] != 7:
            continue
        pos, end = section[4], section[4] + section[5]
        while pos < end:
            namesize, descsize, kind = struct.unpack_from('<III', data, pos)
            pos += 12
            name = data[pos:pos + namesize]
            pos += (namesize + 3) & ~3
            desc = data[pos:pos + descsize]
            pos += (descsize + 3) & ~3
            if kind == 3 and name.rstrip(b'\0') == b'GNU':
                ids.append(desc.hex())
    return segments, ids


def code_at(data, address, size):
    matches = [p for p in elf(data)[0] if p[0] == 1 and p[3] <= address and address + size <= p[3] + p[5]]
    check(len(matches) == 1, 'one file-backed PT_LOAD')
    offset = matches[0][2] + address - matches[0][3]
    return data[offset:offset + size]


def validate(entries, config, bp, controller, pieces):
    counts = collections.Counter()
    for row in entries:
        module = config['modules'][row['modulePath']]
        check(row['pid'] == controller['appPid'] and row['runId'] == controller['nonce'], 'entry owner')
        check(row['collectible'] is True and row['nativeModule'] == 'libcoreclr.so', 'definition owner')
        check(row['fileSha256'] == module['sha256'] and row['moduleMvid'] == module['moduleMvid'], 'PE identity')
        check(row['loadedMetadataMvidValidated'] is True, 'loaded metadata read')
        check(row['methodDefToken'] == module['methods'][row['metadataMethodName']], 'method token')
        check(row['relativePath'] == module['relativePath'], 'module path')
        check(row['bytecodeStart'] == row['methodDescBytecodeStart'] > 0, 'bytecode identity')
        check(row['firstOpcodeAddress'] == row['bytecodeStart'] + 8, 'typed first opcode')
        check(len(bytes.fromhex(row['bytecodePrefixHex'])) == min(64, row['bytecodeSizeSlots'] * 4), 'bytecode size')
        if row['kind'] == 'child':
            c = row['childFrameContract']
            check(row['pc'] == int(controller['coreclrSlide'], 16) + pieces['dispatch']['filePc'], 'child PC')
            check(c == bp['childFrameContract'], 'live contract')
            check(c['precedingReInitHex'] == pieces['reInit']['hex'], 'live ReInit')
            check(c['precedingFrameReloadHex'] == pieces['frameReload']['hex'], 'live reload')
            check(c['opcodeRegister'] == 'r14' and c['frameSpillOffset'] == 0xe48, 'register/spill')
            check(row['childRegisters']['r14'] == row['firstOpcodeAddress'], 'live opcode register')
        else:
            check(row['kind'] == 'stub' and row['pc'] == bp['stubAddress'], 'stub PC')
        counts[row['relativePath'] + ':' + row['metadataMethodName']] += 1
    check(set(counts) == set(config['requiredMethods']), 'nine requested identities')
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('artifacts/mobile-budget-increment'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    check(not args.output.exists(), 'new receipt required')
    root = args.root
    apk = root / 'android-entry-apk-20261014-attempt1'
    capture = apk / 'capture-2e12397007a444e89535aef1f90158e4'
    normal = apk / 'run-all-d836914c338145ae9883d4abc463975d'
    assessment_path = root / 'android-entry-assessment-20261014-attempt1/results.json'
    contract_path = root / 'android-entry-contract-20261014-attempt1/raw/results.json'
    symbols_root = root / 'android-entry-symbols-20261014-attempt1'
    state, build, controller = [load(p) for p in (apk / 'state.json', apk / 'entry-build.json', capture / 'results.json')]
    assessment, contract = load(assessment_path), load(contract_path)
    check(assessment['assessorSha256'] == sha(Path('eng/android-budget-increment-entry-assess.py')), 'assessment tool SHA')
    symbols = load(symbols_root / 'verification.json')
    normal_audit = load(root / 'android-entry-normal-audit-20261014-attempt1/results.json')
    check(state['runtimeTree'] == contract['runtimeTree'] == symbols['runtimeTree'] == assessment['runtimeTree'], 'tree agreement')
    check(state['runtimeCommit'] == contract['runtimeCommit'] == '112e97408de1ae1c2a6cbd2967dcd250cd2d491c', 'commit')
    check(state['appHashes'] == load(root / 'android-apk-20261014-attempt1/state.json')['appHashes'], 'preserved inputs')
    check(build['sameAppHashes'] and build['onlyJniOptInGateDelta'] and build['javaSourceUnchanged'], 'gate-only build')
    check(sha(Path(state['apk'])) == state['apkSha256'] == build['newApkSha256'], 'actual APK SHA')
    for relative, digest in controller['rawHashes'].items():
        check(sha(capture / relative) == digest, 'actual raw SHA ' + relative)
    with zipfile.ZipFile(state['apk']) as archive:
        for name, product in contract['products'].items():
            native = (apk / 'app' / name).read_bytes()
            debug = (symbols_root / 'raw' / (name + '.dbg')).read_bytes()
            check(hashlib.sha256(native).hexdigest() == product['sha256'] == symbols['nativeHashes'][name], 'native SHA')
            check(hashlib.sha256(debug).hexdigest() == product['symbolsSha256'], 'debug SHA')
            check(elf(native)[1] == elf(debug)[1] == product['buildIds'] == symbols['symbolsBuildIds'][name], 'GNU IDs')
            matches = [n for n in archive.namelist() if n.endswith('/' + name)]
            check(len(matches) == 1 and archive.read(matches[0]) == native, 'APK native bytes')
    native = (apk / 'app/libcoreclr.so').read_bytes()
    for name, piece in contract['codePieces'].items():
        check(code_at(native, piece['filePc'], piece['bytes']).hex() == piece['hex'], 'ELF code ' + name)
    config = load(capture / 'observer/capture-config.json')
    bp = load(capture / 'observer/breakpoints.json')
    metadata = load(Path('artifacts/mobile-session-budget/author-entry-metadata-20261013/methods.json'))
    for module in config['modules'].values():
        original = next(m for m in metadata if m['assembly'] + '.dll' == module['relativePath'])
        check(module['sha256'] == original['sha256'] == sha(Path(original['path'])), 'original author PE SHA')
        check(module['moduleMvid'] == original['moduleMvid'], 'original PE metadata MVID')
        check(module['methods'] == {m['owner'] + '.' + m['name']: int(m['token'], 16) for m in original['methods']}, 'original PE method identities')
        check(sha(apk / 'postinstall-author' / module['relativePath']) == original['sha256'], 'post-install author bytes')
    check(config['appPid'] == bp['pid'] == controller['appPid'] and config['runId'] == bp['runId'] == controller['nonce'], 'capture-config actual owner')
    raw = [json.loads(line.partition('ANDROID_BUDGET_INTERPRETER_ENTRY ')[2])
           for line in (capture / 'lldb.log').read_text().splitlines() if line.startswith('ANDROID_BUDGET_INTERPRETER_ENTRY ')]
    check(load(capture / 'observer/interpreter-entries.json') == raw, 'raw LLDB extraction')
    counts = validate(raw, config, bp, controller, contract['codePieces'])
    check(counts == assessment['groupCounts'] and len(raw) == assessment['samples'] == 178, 'independent counts')
    check(dict(collections.Counter(r['kind'] for r in raw)) == assessment['kinds'], 'sample kind counts')
    check(assessment['nativeEntryProof'] and not assessment['completeInvocationCapture'], 'sampled scope')
    spec = importlib.util.spec_from_file_location('budget_rows', 'eng/mobile-host-budget-audit.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    for directory, pid, nonce in ((capture, controller['appPid'], controller['nonce']),
                                  (normal, normal_audit['processId'], normal_audit['nonce'])):
        aggregate, rows, _, hashes = audit.adapter(directory / 'adapter-evidence', nonce, pid)
        check(aggregate['contexts'] == 73 and len(aggregate['cases']) == 15, 'complete15/73 ledger')
        before = load(directory / 'installed-before.json')
        check(before == load(directory / 'installed-after.json') and len(before) == 203, 'unchanged203 installed entries')
        check(load(directory / 'request.json')['apkSha256'] == state['apkSha256'], 'same APK request')
        native_log = (directory / 'native.log').read_text()
        check(f'MOBILE_BUDGET_NATIVE pid={pid} nonce={nonce} InterpMode=0 RuneCLRInterpretCollectible=0 ReadyToRun=1' in native_log, 'native owner/config')
        check('CORECLR_INITIALIZE_HRESULT=0x0' in native_log, 'native initialization')
        text = (directory / 'instrumentation.log').read_text()
        check(re.findall(r'^INSTRUMENTATION_RESULT: return-code=([0-9-]+)$', text, re.M) == ['0'], 'Java exit')
        check(re.findall(r'^INSTRUMENTATION_CODE: ([0-9-]+)$', text, re.M) == ['0'], 'instrumentation exit')
        check('CORECLR_EXECUTE_HRESULT=0x0;RUNECLR_EXIT=0' in (directory / 'native.log').read_text(), 'native/managed exit')
        if directory == capture:
            check(hashes == assessment['adapterRawHashes'], 'raw ledger hashes')
        else:
            check(hashes == normal_audit['adapterRawHashes'], 'normal audit raw ledger hashes')
            check(before == load(capture / 'installed-before.json'), 'same observed203 inputs across runs')
    check(not any('ENTRY_WAIT' in str(x) for x in load(normal / 'request.json')['command']), 'normal gate not requested')
    check('ANDROID_ENTRY_GATE' not in (normal / 'native.log').read_text(), 'normal gate absent')
    check(normal_audit['passed'] and normal_audit['mobileVerified'], 'strict gate-off audit')
    cleanup, cleaned = load(apk / 'cleanup.json'), load(apk / 'cleanup-check.json')
    check(cleanup['package'] == state['package'] == controller['package'] and cleanup['appUninstalled'], 'owned uninstall')
    check(cleaned['passed'] and all(cleaned[k] for k in ('ownedEmulatorAbsent', 'ownedEmulatorProcessAbsent', 'ownedForwardsAbsent')), 'recorded cleanup')
    check(cleaned['appUninstallReceiptSha256'] == sha(apk / 'cleanup.json'), 'cleanup SHA')
    check(cleaned['serial'] not in (apk / 'cleanup-devices.txt').read_text(), 'actual devices list')
    check(not (apk / 'cleanup-forwards.txt').read_text().strip(), 'actual empty forward list')
    check(not cleanup['physicalDeviceTouched'] and not cleaned['physicalDeviceTouched'], 'no physical device')
    rejected = []
    for field, value in [('pc', 0), ('methodDefToken', 0), ('moduleMvid', 'wrong'), ('methodDescBytecodeStart', 0)]:
        altered = copy.deepcopy(raw)
        altered[0][field] = value
        try:
            validate(altered, config, bp, controller, contract['codePieces'])
        except (AssertionError, KeyError):
            rejected.append(field)
        else:
            raise AssertionError('corrupted sample accepted: ' + field)
    report = {'passed': True, 'scope': 'Independent offline cross-check; no new process/device actions',
              'samples': len(raw), 'groups': len(counts), 'groupCounts': counts,
              'contextsPerRun': 73, 'casesPerRun': 15, 'nativeEntryProof': True,
              'completeInvocationCapture': False, 'actualElfCodePieces': 3,
              'actualNativeDebugBuildIdPairs': 2, 'captureRawHashes': len(controller['rawHashes']),
              'sameApkGateOffPassed': True, 'recordedCleanupPassed': True,
              'negativeControlsRejected': rejected, 'reviewerSha256': sha(Path(__file__)),
              'evidenceHashes': {str(p): sha(p) for p in (assessment_path, contract_path,
                  apk / 'entry-build.json', apk / 'cleanup.json', apk / 'cleanup-check.json',
                  capture / 'results.json', normal / 'request.json')}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
