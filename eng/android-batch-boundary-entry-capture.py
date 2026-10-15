#!/usr/bin/env python3
"""Prepare a current-image initial InterpExecMethod entry observer."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import uuid

PINS = {
    'android-session-policy-entry-capture': '9ddde81f878a3e3495a3f71990da5278021d27a6813246c17a5050623c8e0d6f',
    'android-session-policy-layout': '3ab977377032cca005a41b959fb21b2162c67dcc7658b44a1e43df85ca7d61eb',
    'ios-release-package-entry-capture': '408500026eb1369fe1b98626a1dd09f4ccd408c9e179411dc3bca807baa60dee',
    'ios-budget-increment-entry': '1991b6c0906d807b3b69dad69ea151f9ffbb8369c5aad7ceef1010a7fecd4dc1',
    'ios-r2r-release-verify': '29a782a093ee3a6dca355562c08d79b87c9afe96046218190df9507b1422fa7e',
}
MANIFEST_SHA = 'c3a7bb80fe6275407059e44b8005f28776482c0d1b5ca0b468e31fb14862d1c6'
AUTHOR_SHA = '5f1a0942c6f5f74441078b75732f0b413f3bb2412a026343cfaa214d51fbf9f5'
METHODS = ['BatchBoundary.Author.Entries.' + n for n in
           ('ShortReturn', 'OrdinaryThrow', 'FiniteProgress', 'EndlessCatch')]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def need(value, message):
    if not value:
        raise RuntimeError(message)

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='ascii')

def helper(name):
    path = Path(__file__).with_name(name + '.py')
    need(sha(path) == PINS[name], 'Frozen helper changed: ' + name)
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def reader(name, function):
    path = Path(__file__).with_name(name + '.py')
    need(sha(path) == PINS[name], 'Frozen PE reader changed')
    nodes = [n for n in ast.parse(path.read_text()).body
             if isinstance(n, ast.FunctionDef) and n.name == function]
    need(len(nodes) == 1, 'PE reader is not unique')
    env = {'struct': struct, 'uuid': uuid}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), env)
    return env[function]

def pe_metadata(path):
    identity = reader('ios-budget-increment-entry', 'pe_mvid')(path)
    data = path.read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    opt = pe + 24
    dirs = opt + (112 if struct.unpack_from('<H', data, opt)[0] == 0x20b else 96)
    sections = opt + struct.unpack_from('<H', data, pe + 20)[0]
    def offset(rva):
        for i in range(struct.unpack_from('<H', data, pe + 6)[0]):
            size, start, raw_size, raw = struct.unpack_from('<IIII', data, sections + 40 * i + 8)
            if start <= rva < start + max(size, raw_size):
                return raw + rva - start
        raise RuntimeError('RVA outside PE')
    cli = offset(struct.unpack_from('<I', data, dirs + 14 * 8)[0])
    size = struct.unpack_from('<I', data, cli + 12)[0]
    need(struct.unpack_from('<I', data, cli + 16)[0] & 1 and
         struct.unpack_from('<I', data, cli + 64)[0] == 0, 'Author must be IL-only without R2R')
    root = identity['metadataRootOffset']
    return {**identity, 'metadataSize': size,
            'metadataSha256': hashlib.sha256(data[root:root + size]).hexdigest()}

CAPTURE = r'''
def capture(frame, location, internal):
    HITS['initial'] = HITS.get('initial', 0) + 1
    process = frame.GetThread().GetProcess()
    target = process.GetTarget()
    try:
        if frame.GetPC() != CONFIG['loadedEntryAddress']:
            raise RuntimeError('Observer PC differs from exact initial entry')
        if frame.FindRegister('rcx').GetValueAsUnsigned():
            return False
        context_address = frame.FindRegister('rsi').GetValueAsUnsigned()
        start = field(typed(target, context_address, 'InterpMethodContextFrame'), 'startIp')
        method_address = word(process, start)
        desc_address = word(process, method_address + OFFSETS['InterpMethod.methodHnd'])
        chunk_index = read(process, desc_address + OFFSETS['MethodDesc.m_chunkIndex'], 1)[0]
        chunk_address = desc_address - TYPES['MethodDescChunk'].GetByteSize() - chunk_index * 8
        mt_address = word(process, chunk_address + OFFSETS['MethodDescChunk.m_methodTable'])
        flags = int.from_bytes(read(process, mt_address + OFFSETS['MethodTable.m_dwFlags'], 4), 'little')
        if not flags & 0x00200000:
            return False
        interp = typed(target, method_address, 'InterpMethod')
        desc = typed(target, desc_address, 'MethodDesc')
        chunk = typed(target, chunk_address, 'MethodDescChunk')
        mt = typed(target, mt_address, 'MethodTable')
        module_address = field(mt, 'm_pModule')
        module = typed(target, module_address, 'Module')
        error = lldb.SBError()
        simple = process.ReadCStringFromMemory(field(module, 'm_pSimpleName'), 256, error)
        if error.Fail():
            raise RuntimeError(str(error))
        if simple not in NAMES:
            return False
        path = utf16(process, field(module, 'm_path'))
        expected = CONFIG['modules'].get(path)
        if expected is None:
            raise RuntimeError('Target Module path differs: ' + path)
        token = 0x06000000 | ((field(chunk, 'm_flagsAndTokenRange') & 0xfff) << 12) | (field(desc, 'm_wFlags3AndTokenRemainder') & 0xfff)
        names = [n for n, value in expected['methods'].items() if value == token]
        if not names:
            return False
        if len(names) != 1:
            raise RuntimeError('Author token ambiguous')
        key = expected['relativePath'] + ':' + names[0]
        if key not in CONFIG['requiredMethods'] or key in SAMPLED:
            return False
        base = field(module, 'm_baseAddress')
        mapped = None
        for layout, root_key, mvid_key in [('rva', 'metadataRootRva', 'moduleMvidRva'), ('flat', 'metadataRootOffset', 'moduleMvidOffset')]:
            try:
                metadata = read(process, base + expected[root_key], expected['metadataSize'])
                mvid = read(process, base + expected[mvid_key], 16).hex()
                if hashlib.sha256(metadata).hexdigest() == expected['metadataSha256'] and mvid == expected['moduleMvidBytesHex']:
                    mapped = layout
                    break
            except RuntimeError:
                pass
        if mapped is None:
            raise RuntimeError('Actual loaded metadata bytes/MVID differ')
        size = field(interp, 'codeSize')
        desc_start = field(desc, 'm_interpreterCode')
        if size <= 0 or desc_start != start or field(interp, 'methodHnd') != desc_address:
            raise RuntimeError('Interpreter/definition/bytecode ownership differs')
        prefix = read(process, start + 8, min(size * 4, 64))
        entry = {'kind': 'initial', 'pid': process.GetProcessID(), 'runId': CONFIG['runId'],
            'pc': frame.GetPC(), 'function': frame.GetFunctionName(),
            'nativeModule': frame.GetModule().GetFileSpec().GetFilename(),
            'methodContextFrame': context_address, 'interpMethod': method_address,
            'methodDesc': desc_address, 'methodTable': mt_address, 'managedModule': module_address,
            'moduleAssembly': field(module, 'm_pAssembly'), 'modulePEAssembly': field(module, 'm_pPEAssembly'),
            'moduleBaseAddress': base, 'modulePath': path, 'moduleSimpleName': simple,
            'relativePath': expected['relativePath'], 'fileSha256': expected['sha256'],
            'collectible': True, 'methodDefToken': token, 'metadataMethodName': names[0],
            'moduleMvid': expected['moduleMvid'], 'loadedMetadataMvidValidated': True,
            'loadedMetadataBytesSha256': expected['metadataSha256'], 'loadedPELayout': mapped,
            'bytecodeStart': start, 'methodDescBytecodeStart': desc_start,
            'firstOpcodeAddress': start + 8, 'bytecodeSizeSlots': size,
            'bytecodePrefixHex': prefix.hex(), 'entryRsi': context_address, 'entryRcx': 0}
        ENTRIES.append(entry)
        SAMPLED.add(key)
        (OUT / 'interpreter-entries.json').write_text(json.dumps(ENTRIES, indent=2) + '\n')
        print('ANDROID_BATCH_INTERPRETER_ENTRY ' + json.dumps(entry), flush=True)
        if set(CONFIG['requiredMethods']) <= SAMPLED:
            for bp in OBSERVATION_BPS:
                bp.SetEnabled(False)
            (OUT / 'observation-disabled.json').write_text(json.dumps({'pid': process.GetProcessID(), 'runId': CONFIG['runId'], 'covered': sorted(SAMPLED), 'allObservationBreakpointsDisabled': all(not b.IsEnabled() for b in OBSERVATION_BPS)}) + '\n')
            print('ANDROID_BATCH_OBSERVATION_DISABLED', flush=True)
    except Exception as error:
        ERRORS.append({'pc': frame.GetPC(), 'error': str(error)})
        (OUT / 'capture-errors.json').write_text(json.dumps(ERRORS, indent=2) + '\n')
        for bp in OBSERVATION_BPS:
            bp.SetEnabled(False)
    return False
'''

SETUP = r'''
    start_fields = [TYPES['InterpMethodContextFrame'].GetFieldAtIndex(i) for i in range(TYPES['InterpMethodContextFrame'].GetNumberOfFields()) if TYPES['InterpMethodContextFrame'].GetFieldAtIndex(i).GetName() == 'startIp']
    if len(start_fields) != 1 or start_fields[0].GetOffsetInBytes() != CONFIG['entry']['startIpOffset']:
        raise RuntimeError('New matching DWARF startIp differs')
    symbols = target.FindSymbols('_Z16InterpExecMethodP16InterpreterFrameP24InterpMethodContextFrameP19InterpThreadContextP19ExceptionClauseArgs')
    starts = [symbols.GetContextAtIndex(i).GetSymbol().GetStartAddress() for i in range(symbols.GetSize()) if symbols.GetContextAtIndex(i).GetModule().GetFileSpec().GetFilename() == 'libcoreclr.so']
    if len(starts) != 1 or starts[0].GetFileAddress() != CONFIG['entry']['filePc']:
        raise RuntimeError('Current exact interpreter entry absent/ambiguous')
    address = starts[0].GetLoadAddress(target)
    live = read(process, address, len(bytes.fromhex(CONFIG['entry']['entryPrefixHex']))).hex()
    if live != CONFIG['entry']['entryPrefixHex']:
        raise RuntimeError('Actual loaded entry instructions differ from matched new ELF')
    CONFIG['loadedEntryAddress'] = address
    bp = target.BreakpointCreateByAddress(address)
    bp.SetScriptCallbackFunction('android_batch_entry_lldb.capture')
    OBSERVATION_BPS.append(bp)
    (OUT / 'breakpoints.json').write_text(json.dumps({'pid': process.GetProcessID(), 'runId': CONFIG['runId'], 'entryAddress': address, 'entry': CONFIG['entry'], 'liveEntryPrefixHex': live, 'offsets': OFFSETS, 'methodTableOffsetsSource': 'Loaded SHA-verified cDAC JSON'}, indent=2) + '\n')
    print('ANDROID_ENTRY_READY pid=' + str(process.GetProcessID()) + ' runId=' + CONFIG['runId'], flush=True)

def finish():
    process = lldb.debugger.GetSelectedTarget().GetProcess()
    (OUT / 'capture-hits.json').write_text(json.dumps(HITS) + '\n')
    (OUT / 'debugger-result.json').write_text(json.dumps({'pid': process.GetProcessID(), 'runId': CONFIG['runId'], 'exited': process.GetState() == lldb.eStateExited, 'exitStatus': process.GetExitStatus(), 'errors': len(ERRORS)}, indent=2) + '\n')
'''

def render():
    for name in PINS:
        need(sha(Path(__file__).with_name(name + '.py')) == PINS[name], 'Frozen dependency differs')
    original = helper('android-session-policy-entry-capture').render()
    prefix = original[:original.index('def capture(')]
    setup = original[original.index('def setup():'):original.index("    symbols=target.FindSymbols('InterpreterStub')")]
    text = prefix + CAPTURE + setup + SETUP
    ast.parse(text)
    return text

def prepare(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    need(re.fullmatch(r'[0-9a-f]{32}', args.nonce) and args.pid > 0 and
         re.fullmatch(r'net.dot.RuneCLR_BatchBoundary_[0-9a-f]{12}', args.package), 'Owned PID/package/nonce required')
    manifest = load(args.symbols / 'manifest.json')
    need(sha(args.symbols / 'manifest.json') == MANIFEST_SHA and manifest['success'], 'Current symbols manifest differs')
    need(all(sha(args.symbols / n) == r['sha256'] and (args.symbols / n).stat().st_size == r['bytes']
             for n, r in manifest['files'].items()), 'Downloaded native/source/DWARF evidence changed')
    state = load(args.apk / 'state.json')
    need(state['runtimeTree'] == manifest['runtimeTree'] and load(args.apk / 'entry-build.json')['onlyJniOptInGateDelta'], 'Gate runtime ownership differs')
    parser = helper('android-session-policy-layout')
    for name in ('libcoreclr.so', 'libclrinterpreter.so'):
        need(sha(args.apk / 'app' / name) == manifest['files'][name]['sha256'] and
             parser.read_build_ids(args.apk / 'app' / name) == parser.read_build_ids(args.symbols / (name + '.dbg')), 'Actual native/symbol image identity differs')
    data = (args.apk / 'app/libcoreclr.so').read_bytes()
    descriptors = []
    for match in re.finditer(re.escape(b'{"version":'), data):
        try:
            raw = data[match.start():data.index(bytes([0]), match.start())]
            descriptor = json.loads(raw)
            if 'MethodTable' in descriptor.get('types', {}):
                descriptors.append((raw, descriptor))
        except (ValueError, UnicodeError):
            pass
    need(len(descriptors) == 1, 'Actual cDAC MethodTable descriptor absent/ambiguous')
    raw, descriptor = descriptors[0]
    author = args.inputs / 'author/BatchBoundary.Author.dll'
    need(sha(author) == AUTHOR_SHA == state['authorHashes']['author/BatchBoundary.Author.dll'], 'Frozen author input differs')
    methods = reader('ios-r2r-release-verify', 'plugin_methods')(author, required=(), qualified=True)
    need(set(METHODS) <= methods.keys(), 'Four current author MethodDefs absent')
    module = {'relativePath': 'author/BatchBoundary.Author.dll', 'simpleName': 'BatchBoundary.Author',
              'sha256': AUTHOR_SHA, 'methods': methods, **pe_metadata(author)}
    config = {'appPid': args.pid, 'runId': args.nonce, 'entry': manifest['entry'],
              'modules': {'/data/user/0/' + args.package + '/files/author/BatchBoundary.Author.dll': module},
              'requiredMethods': [module['relativePath'] + ':' + n for n in METHODS],
              'cdac': {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                       'methodTable': descriptor['types']['MethodTable']}}
    write(out / 'capture-config.json', config)
    (out / 'android_batch_entry_lldb.py').write_text(render(), encoding='ascii')
    commands = ['command script import ' + (out / 'android_batch_entry_lldb.py').as_posix(),
                'script android_batch_entry_lldb.setup()', 'continue', 'process status',
                'script android_batch_entry_lldb.finish()', 'quit']
    (out / 'capture.lldb').write_text('\n'.join(commands) + '\n', encoding='ascii')
    write(out / 'preparation.json', {'success': True, 'preparedOnly': True, 'nativeEntryProof': False,
        'driverSha256': sha(__file__), 'dependencyPins': PINS, 'manifestSha256': MANIFEST_SHA,
        'configSha256': sha(out / 'capture-config.json'), 'observerSha256': sha(out / 'android_batch_entry_lldb.py'),
        'runtimeTree': manifest['runtimeTree'], 'entry': manifest['entry'],
        'scope': 'Four initial native interpreter entries only; no dispatch cadence, performance or complete invocation claim'})
    print('ANDROID_BATCH_ENTRY_PREPARATION_PASS', args.pid, args.nonce)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('apk', 'symbols', 'inputs', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--nonce', required=True)
    p.add_argument('--package', required=True)
    prepare(p.parse_args())

if __name__ == '__main__':
    main()
