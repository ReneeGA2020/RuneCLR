#!/usr/bin/env python3
"""Exercise fresh-author observer decoding/review without creating any target."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--request', type=Path)
    args = parser.parse_args()
    driver = Path(__file__).with_name('ios-fresh-author-entry-capture.py')
    spec = importlib.util.spec_from_file_location('fresh_capture', driver)
    capture = importlib.util.module_from_spec(spec); spec.loader.exec_module(capture)
    observer = capture.observer_source(); compile(observer, 'fresh_author_entry_lldb.py', 'exec')
    namespace = {}; exec(compile(capture.decoder_source(), 'decoder', 'exec'), namespace); decode = namespace['decode']
    identity = json.loads(args.identity.read_text()); config = {
        'layouts': dict(identity['layouts'], **capture.OWNER_LAYOUTS), 'authors': {},
        'requiredMethods': identity['requiredMethods'], 'entry': identity['symbol'],
        'nativeUuid': identity['signedNative']['uuid'], 'gate': identity['gate'], 'pid': 42, 'nonce': 'fixture-nonce'}
    config['childContract'] = json.loads(args.request.read_text())['childContract'] if args.request else {
        'frameSpillOffset': 8, 'filePc': 0x200000}
    for name, values in identity['modules'].items():
        config['authors'][name] = dict(values, fileName=name, simpleName=name[:-4], path='/owned/plugin/' + name)
    tests = []

    def fixture(name='HostBudgetProbe.Payload.dll', token=None, mapped='rva'):
        expected = config['authors'][name]; data = {}
        if token is None: token = next(iter(expected['methods'].values()))
        def put(address, value):
            for i, byte in enumerate(value): data[address + i] = byte
        def integer(address, value, size=8): put(address, value.to_bytes(size, 'little'))
        def field(address, kind, name, value, size=8):
            integer(address + config['layouts'][kind]['fields'][name], value, size)
        def memory(address, size):
            try: return bytes(data[address + i] for i in range(size))
            except KeyError: raise RuntimeError('Synthetic unmapped memory')
        context, start, method, chunk, table, module, base = 0x1000, 0x2000, 0x3000, 0x4000, 0x5000, 0x6000, 0x10000
        desc = chunk + config['layouts']['MethodDescChunk']['size'] + 3 * 8
        field(context, 'InterpMethodContextFrame', 'startIp', start); integer(start, method)
        field(method, 'InterpMethod', 'methodHnd', desc); field(method, 'InterpMethod', 'codeSize', 16, 4)
        field(desc, 'MethodDesc', 'm_chunkIndex', 3, 1); field(desc, 'MethodDesc', 'm_interpreterCode', start)
        field(desc, 'MethodDesc', 'm_wFlags3AndTokenRemainder', token & 0xfff, 2)
        field(chunk, 'MethodDescChunk', 'm_flagsAndTokenRange', (token >> 12) & 0xfff, 2)
        field(chunk, 'MethodDescChunk', 'm_methodTable', table); field(table, 'MethodTable', 'm_dwFlags', 0x00200000, 4)
        field(table, 'MethodTable', 'm_pModule', module); field(module, 'Module', 'm_pSimpleName', 0x8000)
        field(module, 'Module', 'm_path', 0x9000); put(0x8000, expected['simpleName'].encode() + bytes(1))
        put(0x9000, expected['path'].encode('utf-16-le') + bytes(2))
        field(module, 'Module', 'm_baseAddress', base); field(module, 'Module', 'm_pPEAssembly', 0xa000)
        field(module, 'Module', 'm_pAssembly', 0xb000); field(0xa000, 'PEAssembly', 'm_pAssemblyBinder', 0xc000)
        meter = 0xc000 + capture.OWNER_LAYOUTS['CustomAssemblyBinder']['fields']['m_runeCLRInstructionMeter']
        for k, f, n in [('terminalPrototype', 'm_terminalPrototype', 1), ('phaseAcquireLoad', 'm_phaseAcquireLoad', 1),
                       ('derivedLedger', 'm_derivedLedger', 1), ('batchInterval', 'm_batchInterval', 8), ('phase', 'm_phase', 4)]:
            field(meter, 'RuneCLRInstructionMeter', f, config['gate'][k], n)
        root = expected['metadataRootRva' if mapped == 'rva' else 'metadataRootOffset']
        mvid = expected['moduleMvidRva' if mapped == 'rva' else 'moduleMvidOffset']
        put(base + root, b'BSJB'); put(base + mvid, bytes.fromhex(expected['moduleMvidBytesHex']))
        put(start + 8, bytes(range(64)))
        integer(0xd000 + config['childContract']['frameSpillOffset'], context)
        return {'memory': memory, 'put': put, 'field': field, 'context': context, 'desc': desc, 'table': table,
                'module': module, 'base': base, 'meter': meter}

    entries = []
    for name, expected in config['authors'].items():
        for method, token in expected['methods'].items():
            for layout in ('rva', 'flat'):
                f = fixture(name, token, layout); item = decode(f['memory'], f['context'], 0, config)
                assert item['methodGroup'] == name + ':' + method and item['loadedPELayout'] == layout
                assert item['definitionBinder'] == 0xc000 and item['instructionMeter'] == f['meter']
            item.update(kind='exact-invocation-entry', pid=42, nonce=config['nonce'],
                nativeFilePc=config['entry']['filePc'], nativeModule='libcoreclr.dylib', pc=0x100000,
                nativeUuid=config['nativeUuid'], nativeSlide=0x100000 - config['entry']['filePc'])
            entries.append(item); tests.append('decode-rva-and-flat:' + name + ':' + method)
    capture.verify_entries(entries, config, {'loadPc': 0x100000}); tests.append('review-nine-method-groups')
    child_decode = namespace['decode_child']
    for name in config['authors']:
        f = fixture(name); child = child_decode(f['memory'], 0xd000, 0x2008, config)
        assert child['firstOpcodeAddress'] == 0x2008 and child['frameSpillAddress'] == 0xd000 + config['childContract']['frameSpillOffset']
        tests.append('child-spill-header-opcode:' + name)
    f = fixture()
    try: child_decode(f['memory'], 0xd000, 0x2010, config)
    except RuntimeError: tests.append('child-wrong-opcode-pointer')
    else: raise RuntimeError('Wrong child opcode pointer accepted')
    try: child_decode(f['memory'], 0xd001, 0x2008, config)
    except RuntimeError: tests.append('child-wrong-frame-spill')
    else: raise RuntimeError('Wrong child frame spill accepted')
    child_entries = copy.deepcopy(entries)
    child_entries[-1].update(kind='child-frame-dispatch', pc=0x100000-config['entry']['filePc']+config['childContract']['filePc'],
        nativeFilePc=config['childContract']['filePc'], firstOpcodeAddress=child_entries[-1]['bytecodeStart']+8, frameSpillAddress=0xd008)
    child_bp = {'loadPc': 0x100000, 'childLoadPc': child_entries[-1]['pc']}
    capture.verify_entries(child_entries, config, child_bp); tests.append('review-mixed-invocation-and-child-groups')
    child_entries[-1]['firstOpcodeAddress'] += 4
    try: capture.verify_entries(child_entries, config, child_bp)
    except RuntimeError: tests.append('review-wrong-child-opcode-pointer')
    else: raise RuntimeError('Wrong child opcode review accepted')

    def reject(label, change):
        f = fixture(); change(f)
        try: decode(f['memory'], f['context'], 0, config)
        except RuntimeError: tests.append(label); return
        raise RuntimeError('Invalid decoder memory accepted: ' + label)

    f = fixture(); f['field'](f['table'], 'MethodTable', 'm_dwFlags', 0, 4)
    assert decode(f['memory'], f['context'], 0, config) is None; tests.append('noncollectible-prefilter')
    assert decode(lambda a, n: (_ for _ in ()).throw(RuntimeError('must-not-read')), 0, 1, config) is None
    tests.append('exception-reentry-prefilter')
    f = fixture(token=0x060000ff); assert decode(f['memory'], f['context'], 0, config) is None
    tests.append('unrequested-method-prefilter')
    reject('wrong-MVID', lambda f: f['put'](f['base'] + config['authors']['HostBudgetProbe.Payload.dll']['moduleMvidRva'], bytes(16)))
    reject('wrong-loaded-path', lambda f: f['put'](0x9000, '/other'.encode('utf-16-le') + bytes(2)))
    reject('wrong-bytecode-owner', lambda f: f['field'](f['desc'], 'MethodDesc', 'm_interpreterCode', 1))
    reject('short-memory', lambda f: f.update(memory=lambda a, n: bytes(max(0, n - 1))))
    reject('missing-binder', lambda f: f['field'](0xa000, 'PEAssembly', 'm_pAssemblyBinder', 0))
    reject('derived-ledger-disabled', lambda f: f['field'](f['meter'], 'RuneCLRInstructionMeter', 'm_derivedLedger', 0, 1))
    reject('batch-enabled', lambda f: f['field'](f['meter'], 'RuneCLRInstructionMeter', 'm_batchInterval', 1000))
    reject('cleanup-phase', lambda f: f['field'](f['meter'], 'RuneCLRInstructionMeter', 'm_phase', 1, 4))
    for label, key, value in [('wrong-PID', 'pid', 43), ('wrong-nonce', 'nonce', 'other'),
        ('wrong-load-PC', 'pc', 1), ('wrong-native-UUID', 'nativeUuid', '0' * 32),
        ('wrong-token', 'methodDefToken', 0x060000ff), ('wrong-private-MVID', 'moduleMvid', 'other'),
        ('wrong-owner', 'definitionBinder', 1), ('wrong-meter-gate', 'meterGate', {})]:
        changed = copy.deepcopy(entries); changed[-1][key] = value
        try: capture.verify_entries(changed, config, {'loadPc': 0x100000})
        except RuntimeError: tests.append('review:' + label); continue
        raise RuntimeError('Invalid reviewer row accepted: ' + label)
    try: capture.verify_entries(entries[:-1], config, {'loadPc': 0x100000})
    except RuntimeError: tests.append('review:missing-group')
    else: raise RuntimeError('Incomplete reviewer coverage accepted')
    result = {'passed': True, 'controls': tests, 'count': len(tests), 'driverSha256': hashlib.sha256(driver.read_bytes()).hexdigest(),
        'observerSha256': hashlib.sha256(observer.encode('ascii')).hexdigest(), 'identitySha256': hashlib.sha256(args.identity.read_bytes()).hexdigest(),
        'targetProcessCreated': False, 'debuggerStarted': False, 'nativeEntryProof': False, 'syntheticMemoryOnly': True}
    with args.output.open('x', encoding='ascii') as stream: stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'controls'}))


if __name__ == '__main__':
    main()
