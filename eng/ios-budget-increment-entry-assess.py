#!/usr/bin/env python3
"""Verify frozen iOS budget entry samples without promoting partial coverage."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import zipfile


PARENT_ASSESSOR_SHA256 = '6c5126a78beabee97c6d87fdc847323970cc626513c306ab0991ec1141572f87'
def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_entries(entries, config, breakpoints, metadata):
    counts = dict.fromkeys(config['requiredMethods'], 0)
    for entry in entries:
        module = config['modules'][entry['modulePath']]
        independent = metadata[module['relativePath']]
        method = entry['metadataMethodName']
        token = entry['methodDefToken']
        assert module['sha256'] == independent['sha256'] == entry['fileSha256']
        assert module['moduleMvid'] == independent['moduleMvid'] == entry['moduleMvid']
        assert module['methods'][method] == independent['tokens'][method] == token
        assert independent['managedNativeRva'] == 0
        assert entry['loadedMetadataMvidValidated'] is True
        assert entry['loadedPELayout'] in ('flat', 'rva')
        assert entry['moduleSimpleName'] == independent['assembly']
        assert entry['relativePath'] == module['relativePath']
        assert entry['nativeModule'] == 'libcoreclr.dylib' and entry['collectible'] is True
        assert entry['kind'] in ('stub', 'child')
        if entry['kind'] == 'child':
            assert entry['methodContextFrame'] > 0
        assert entry['pc'] == breakpoints['stubAddress' if entry['kind'] == 'stub' else 'childAddress']
        assert entry['bytecodeStart'] == entry['methodDescBytecodeStart'] > 0
        assert entry['firstOpcodeAddress'] == entry['bytecodeStart'] + 8
        assert entry['bytecodeSizeSlots'] > 0 and bytes.fromhex(entry['bytecodePrefixHex'])
        assert all(entry[key] > 0 for key in ('interpMethod', 'methodDesc', 'methodTable', 'managedModule'))
        key = entry['relativePath'] + ':' + method
        if key in counts:
            counts[key] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError('Preserve existing assessment; use a new output path')
    assert sha(args.archive.read_bytes()) == args.sha256.lower()
    with zipfile.ZipFile(args.archive) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read('manifest.json'))
        assert set(archive.namelist()) == {'manifest.json'} | {'raw/' + n for n in manifest['files']}
        raw = {}
        for name, expected in manifest['files'].items():
            data = archive.read('raw/' + name)
            assert len(data) == expected['bytes'] and sha(data) == expected['sha256']
            raw[name] = data
    load = lambda name: json.loads(raw[name])
    build = json.loads(args.build_receipt.read_text(encoding='utf-8-sig'))
    identity = load('identity.json')
    assert build['success'] and build['buildExit'] == 0
    assert build['target'] == 'iossimulator.arm64' and build['configuration'] == 'Release'
    assert build['assessment']['dynamicJitEnabled'] is False
    assert identity['runtimeCommit'] == build['commit'] and identity['runtimeTree'] == build['tree']
    assert identity['nativeSha256'] == build['nativeSha256']
    assert identity['moduleFiles'] == load('capture-config.json')['modules']
    assert identity['uuid'].replace('-', '').lower() == identity['nativeSections']['uuid']
    metadata = {}
    for module in json.loads(args.metadata.read_text(encoding='utf-8-sig')):
        # This trusted PE-only inspector never loads the author assembly.
        assert sha(Path(module['path']).read_bytes()) == module['sha256']
        module['tokens'] = {}
        for method in module['methods']:
            full_name = method['owner'] + '.' + method['name']
            names = [full_name]
            # The capture's PE reader emits nested TypeDef names without the
            # declaring owner. Only accept an unambiguous same-token alias.
            if '+' in method['owner']:
                names.append(method['owner'].rsplit('+', 1)[1] + '.' + method['name'])
            for name in names:
                assert name not in module['tokens']
                module['tokens'][name] = int(method['token'], 16)
        metadata[module['assembly'] + '.dll'] = module
    entries, config, bp = load('interpreter-entries.json'), load('capture-config.json'), load('breakpoints.json')
    assert entries
    if any(entry['kind'] == 'child' for entry in entries):
        contract = bp['childFrameContract']
        spill = contract['frameSpillOffset']
        dwarf_locations = []
        for block in raw['pframe-dwarf.txt'].decode().split('\n\n'):
            if 'interpexec.cpp' not in block:
                continue
            for match in re.finditer(r'\[0x([0-9a-f]+), 0x([0-9a-f]+)\): DW_OP_breg19 W19\+(\d+)', block):
                dwarf_locations.append({'start': int(match[1], 16), 'end': int(match[2], 16),
                                        'offset': int(match[3]), 'die': block.splitlines()[0]})
        assert config['pFrameDwarfSpillLocations'] == dwarf_locations
        assert contract['dwarfLocation'] in config['pFrameDwarfSpillLocations']
        assert contract['dwarfLocation']['offset'] == spill
        assert contract['dwarfLocation']['start'] <= contract['filePc'] - 40 < contract['dwarfLocation']['end']
        assert contract['precedingInstructions'][0] == ['str', f'x8, [x19, #0x{spill:x}]']
        assert contract['precedingInstructions'][2] == ['ldr', 'x8, [x24], #0x8']
        assert bp['instructions'][:3] == [
            ['ldr', 'w25, [x24]'], ['ldr', f'x8, [x19, #0x{spill:x}]'],
            ['ldr', f'x8, [x8, #0x{bp["prefilterOffsets"]["InterpMethodContextFrame.startIp"]:x}]']]
    counts = validate_entries(entries, config, bp, metadata)
    lldb_entries = [json.loads(line.split('BUDGET_INTERPRETER_ENTRY ', 1)[1])
                    for line in raw['lldb.log'].decode().splitlines() if line.startswith('BUDGET_INTERPRETER_ENTRY ')]
    assert entries == lldb_entries
    original, request, adapter = load('results.json'), load('request.json'), load('adapter-evidence/result.json')
    pid = original['appPid']
    assert int(re.search(r': ([0-9]+)', raw['launch.log'].decode()).group(1)) == pid
    assert original['nonce'] == request['nonce'] == adapter['nonce']
    native_log = raw['managed.stdout.log'].decode() + raw['managed.stderr.log'].decode()
    assert f'MOBILE_BUDGET_NATIVE pid={pid} nonce={request["nonce"]} InterpMode=0 RuneCLRInterpretCollectible=0 ReadyToRun=1' in native_log
    assert 'CORECLR_INITIALIZE_HRESULT=0x0' in native_log
    assert 'CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0' in native_log
    assert adapter['processId'] == pid and adapter['passed'] and adapter['contexts'] == 73
    assert len(adapter['cases']) == 15
    assert original['normalExit'] and original['adapterCompleted'] and original['bundleAndAuthorUnchanged']
    assert original['lldbExit'] == 0 and load('cleanup.json')['exit'] == 0
    assert 'exited with status = 0' in raw['lldb.log'].decode()
    assert original['requiredMethodEntryCounts'] == counts and original['validEntries'] == len(entries)
    errors = load('capture-errors.json') if 'capture-errors.json' in raw else []
    assert original['captureErrors'] == bool(errors)
    full = all(counts.values()) and not errors
    assert original['nativeEntryProof'] == full and original['passed'] == full
    rejected = []
    for field, value in [('methodDefToken', 0), ('pc', 0), ('moduleMvid', 'wrong'), ('methodDescBytecodeStart', 0)]:
        changed = copy.deepcopy(entries)
        changed[0][field] = value
        try:
            validate_entries(changed, config, bp, metadata)
        except (AssertionError, KeyError):
            rejected.append(field)
    assert len(rejected) == 4
    result = {'passed': True, 'archiveSha256': args.sha256.lower(),
              'archiveMembers': len(manifest['files']) + 1, 'validSamples': len(entries),
              'sampledGroups': sum(n > 0 for n in counts.values()), 'requiredGroups': len(counts),
              'counts': counts, 'captureErrors': len(errors), 'nativeEntryProof': full,
              'processId': pid, 'nonce': request['nonce'], 'normalExit': True,
              'contexts': 73, 'negativeControlsRejected': rejected,
              'metadataSha256': sha(args.metadata.read_bytes()), 'assessorSha256': sha(Path(__file__).read_bytes()),
              'buildReceiptSha256': sha(args.build_receipt.read_bytes()), 'runtimeTree': identity['runtimeTree'],
              'scope': 'Offline consistency of live samples; partial coverage is retained; no complete invocation or device proof'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
