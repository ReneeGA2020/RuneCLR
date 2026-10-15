#!/usr/bin/env python3
"""Bind device-native symbols and fresh author metadata offline; never launch an app."""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import platform
import re
import struct
import subprocess
import uuid

COMMIT = '3126bbc9a8851a09ac6435b18a12882bad48f3ee'
TREE = '710936ae1729a5689ab0e0896f3cf722ddd3d31c'
NATIVE_SHA = '34c27daf3d6ef73a1558c21733d9f101bea4dcc839b9380d182d68cea2e2b93b'
PROOF_SHA = '29d83ae68ca57ec2067261d15a901e81f8422981609f1fe6aaad5cb37879de5e'
APP_RESULT_SHA = 'e437a2f78ae3a8433e5c63123f998b3032a1380f6c8afd0ca7d894191d215507'
AUTHOR = {
    'HostBudgetProbe.Payload.dll': {
        'sha256': 'f722ee94f8f6e03c7a8c4a820d4b8d89994e27616484de61386f89ee807b4aa7',
        'mvid': 'f3b655ec-5458-45b1-aeb4-2bc9f73bff7a',
    },
    'HostBudgetProbe.Private.dll': {
        'sha256': '3427628f9ab003aa92bc62670c4470b8b55db868464e37d2637a5fd692636dde',
        'mvid': '08897279-36fe-4a3e-b555-e2c75ad22db6',
    },
}
FIELDS = {
    'InterpMethodContextFrame': ('startIp',),
    'InterpMethod': ('methodHnd', 'codeSize'),
    'MethodDesc': ('m_chunkIndex', 'm_wFlags3AndTokenRemainder', 'm_interpreterCode'),
    'MethodDescChunk': ('m_methodTable', 'm_flagsAndTokenRange'),
    'MethodTable': ('m_dwFlags', 'm_pModule'),
    'Module': ('m_pSimpleName', 'm_path', 'm_baseAddress', 'm_pAssembly', 'm_pPEAssembly'),
}
EXPECTED_LAYOUTS = {
    'InterpMethodContextFrame': {'size': 48, 'fields': {'startIp': 8}},
    'InterpMethod': {'size': 56, 'fields': {'methodHnd': 0, 'codeSize': 36}},
    'MethodDesc': {'size': 24, 'fields': {'m_chunkIndex': 2, 'm_wFlags3AndTokenRemainder': 0, 'm_interpreterCode': 16}},
    'MethodDescChunk': {'size': 24, 'fields': {'m_methodTable': 0, 'm_flagsAndTokenRange': 18}},
    'MethodTable': {'size': 64, 'fields': {'m_dwFlags': 0, 'm_pModule': 24}},
    'Module': {'size': 976, 'fields': {'m_pSimpleName': 224, 'm_path': 232, 'm_baseAddress': 256,
                                        'm_pAssembly': 272, 'm_pPEAssembly': 248}},
}
EXPECTED_METHODS = {
    'HostBudgetProbe.Payload.dll': {'HostBudgetUGC.Base..ctor': 0x06000005,
        'HostBudgetUGC.Base.OnStart': 0x06000001, 'HostBudgetUGC.Base.OnStop': 0x06000003,
        'HostBudgetUGC.Normal..ctor': 0x06000008, 'HostBudgetUGC.Normal.OnStart': 0x06000006,
        'HostBudgetUGC.Normal.OnTick': 0x06000007, 'HostBudgetUGC.FiniteCleanup.OnTick': 0x0600001d},
    'HostBudgetProbe.Private.dll': {'HostBudgetUGC.Private.Helper.Finite': 0x06000001,
        '<>c__DisplayClass0_0.<Finite>b__0': 0x06000004},
}
HELPERS = {
    'ios-r2r-release-verify.py': ('29a782a093ee3a6dca355562c08d79b87c9afe96046218190df9507b1422fa7e', ('plugin_methods',)),
    'ios-budget-increment-entry.py': ('1991b6c0906d807b3b69dad69ea151f9ffbb8369c5aad7ceef1010a7fecd4dc1', ('pe_mvid',)),
    'ios-batch-boundary-entry-prepare.py': ('5956effd1046633755e6db7f70915ed8d4f1725cfa579fc7a0b740a1f76d99a8', ('il_layout', 'dwarf_layout')),
}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x', encoding='ascii') as stream:
        stream.write(json.dumps(value, indent=2) + chr(10))


def readers():
    namespace = {'struct': struct, 'uuid': uuid, 're': re, 'FIELDS': FIELDS, 'need': need}
    for name, (expected, functions) in HELPERS.items():
        path = Path(__file__).with_name(name)
        need(sha(path) == expected, 'Frozen offline reader differs: ' + name)
        nodes = [n for n in ast.parse(path.read_text(encoding='utf-8-sig')).body
                 if isinstance(n, ast.FunctionDef) and n.name in functions]
        need(len(nodes) == len(functions), 'Frozen reader functions not unique: ' + name)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def native(data):
    need(len(data) >= 32 and struct.unpack_from('<II', data) == (0xfeedfacf, 0x100000c)
         and struct.unpack_from('<I', data, 12)[0] == 6, 'Thin ARM64 device MH_DYLIB required')
    count, size = struct.unpack_from('<II', data, 16)
    end = 32 + size
    need(end <= len(data), 'Mach-O commands exceed image')
    at, uuids, versions, sections = 32, [], [], {}
    for _ in range(count):
        need(at + 8 <= end, 'Short Mach-O command')
        kind, length = struct.unpack_from('<II', data, at)
        need(length >= 8 and at + length <= end, 'Invalid Mach-O command size')
        need(kind != 0x1d, 'Unsigned source/device app library required')
        if kind == 0x1b:
            need(length >= 24, 'Short LC_UUID')
            uuids.append(data[at + 8:at + 24].hex())
        elif kind == 0x32:
            need(length >= 24, 'Short LC_BUILD_VERSION')
            versions.append(struct.unpack_from('<III', data, at + 8))
        elif kind == 0x19:
            need(length >= 72, 'Short LC_SEGMENT_64')
            nsections = struct.unpack_from('<I', data, at + 64)[0]
            need(length >= 72 + nsections * 80, 'Short Mach-O sections')
            for i in range(nsections):
                p = at + 72 + i * 80
                section, segment = [data[p + k:p + k + 16].split(bytes([0]))[0].decode('ascii') for k in (0, 16)]
                address, nbytes = struct.unpack_from('<QQ', data, p + 32)
                offset = struct.unpack_from('<I', data, p + 48)[0]
                if offset and nbytes:
                    need(offset + nbytes <= len(data), 'Section exceeds native file')
                    sections[segment + ',' + section] = {'address': address, 'bytes': nbytes, 'offset': offset}
        at += length
    need(at == end and len(uuids) == 1 and len(versions) == 1 and versions[0][0] == 2
         and versions[0][1] == 0x0f0300 and '__TEXT,__text' in sections,
         'Exact device platform2/minimum15.3/UUID/text required')
    return {'sha256': hashlib.sha256(data).hexdigest(), 'uuid': uuids[0], 'platform': 2,
            'minimumOsEncoded': versions[0][1], 'sdkEncoded': versions[0][2], 'sections': sections}


def command(argv, out, stem):
    argv = [str(x) for x in argv]
    write(out / (stem + '.command.json'), {'argv': argv, 'timeoutSeconds': 60, 'offlineOnly': True})
    q = subprocess.run(argv, text=True, capture_output=True, timeout=60)
    (out / (stem + '.stdout')).write_text(q.stdout, encoding='utf-8')
    (out / (stem + '.stderr')).write_text(q.stderr, encoding='utf-8')
    write(out / (stem + '.exit.json'), {'exitCode': q.returncode})
    need(q.returncode == 0, 'Offline command failed: ' + stem)
    return q.stdout


def instruction_bytes(image, identity, rows):
    text = identity['sections']['__TEXT,__text']
    for i, row in enumerate(rows):
        offset = row['filePc'] - text['address']
        need(0 <= offset and offset + 4 <= text['bytes'] and len(row['bytesHex']) == 8,
             'ARM64 instruction outside device text')
        need(bytes.fromhex(row['bytesHex']) == image[text['offset'] + offset:text['offset'] + offset + 4],
             'Offline instruction differs from actual device bytes')
        need(i == 0 or row['filePc'] == rows[i - 1]['filePc'] + 4, 'Noncontiguous device instructions')


def validate_identity(value, image, spills):
    need(value['sourceCommit'] == COMMIT and value['sourceTree'] == TREE
         and value['sourceProofSha256'] == PROOF_SHA, 'Exact source identity required')
    need(value['native'] == native(image) and value['native']['sha256'] == NATIVE_SHA, 'Native identity differs')
    need(value['dwarfUuid'].replace('-', '').lower() == value['native']['uuid'], 'DWARF identity differs')
    need(value['layouts'] == EXPECTED_LAYOUTS, 'Device DWARF field layout differs')
    modules = value['freshAuthorModules']
    need(set(modules) == set(AUTHOR), 'Fresh author module set differs')
    for name, expected in AUTHOR.items():
        module = modules[name]
        need(module['sha256'] == expected['sha256'] and module['moduleMvid'] == expected['mvid']
             and module['layout'] == {'ilOnly': True, 'managedNativeRva': 0}
             and module['methods'] == EXPECTED_METHODS[name], 'Fresh author MethodDef/MVID/hash differs')
    need(value['requiredMethods'] == [name + ':' + method for name in AUTHOR for method in EXPECTED_METHODS[name]],
         'Fixed nine method groups differ')
    child = value['childContract']
    need(child['filePc'] == 0x2f8b54 and child['line'] == 3784, 'Device child PC/line differs')
    need(len(child['before']) == 32 and len(child['instructions']) == 16
         and set(value['symbols']) == {'InterpreterStub', 'PrepareInterpreterCode'}
         and all(len(v['instructions']) == 16 for v in value['symbols'].values()),
         'Complete fixed device code windows required')
    for rows in (child['before'], child['instructions'], *[s['instructions'] for s in value['symbols'].values()]):
        instruction_bytes(image, value['native'], rows)
    pairs = [(row['mnemonic'], row['operands']) for row in child['instructions']]
    need(pairs[:6] == [('ldr', 'w8, [x9]'), ('str', 'x8, [x19, #0x80]'),
        ('ldr', 'x8, [x19, #0x98]'), ('ldr', 'x8, [x8, #0x8]'),
        ('ldr', 'x8, [x8]'), ('ldr', 'x0, [x8]')], 'Device opcode/frame/MethodDesc instruction contract differs')
    stores = [r for r in child['before'] if (r['mnemonic'], r['operands']) == ('str', 'x8, [x19, #0x98]')]
    headers = [r for r in child['before'] if (r['mnemonic'], r['operands']) == ('ldr', 'x8, [x9], #0x8')]
    need(len(stores) == len(headers) == 1 and stores[0]['filePc'] < headers[0]['filePc']
         and (child['before'][-1]['mnemonic'], child['before'][-1]['operands']) == ('ldr', 'x9, [x19, #0x78]'),
         'Device frame store/bytecode header skip/opcode reload differs')
    need(child['frameSpillStoreInstruction'] == stores[0]
         and child['contextDwarfInstruction'] == headers[0], 'Recorded contextual DWARF instruction differs')
    matches = [v for v in spills if v['register'] == 'x19' and v['offset'] == 0x98
               and v['start'] <= headers[0]['filePc'] < v['end']]
    need(len(matches) == 1 and child['matchingDwarfSpills'] == matches
         and child['frameSpillOffset'] == 0x98 and child['frameRegister'] == 'x19'
         and child['opcodePointerRegister'] == 'x9' and child['opcodeRegister'] == 'w8',
         'Device pFrame DWARF spill/register binding differs')
    need(child['pFrameDwarfCoversCapturePc'] is False and child['liveRegisterContentsVerified'] is False
         and not any(v['start'] <= child['filePc'] < v['end'] for v in matches),
         'Contextual DWARF must not be promoted to live capture state')
    stub = value['symbols']['InterpreterStub']
    need(stub['filePc'] == 0x3d470c and any((r['mnemonic'], r['operands']) == ('mov', 'x19, x12')
         for r in stub['instructions']), 'Device stub bytecode-register ABI differs')


def controls(identity, image, spills):
    mutations = {
        'simulator-platform': lambda v: v['native'].update(platform=7),
        'changed-native-hash': lambda v: v['native'].update(sha256='0' * 64),
        'wrong-dwarf-uuid': lambda v: v.update(dwarfUuid='0' * 32),
        'changed-source-tree': lambda v: v.update(sourceTree='0' * 40),
        'wrong-frame-field-offset': lambda v: v['layouts']['InterpMethodContextFrame']['fields'].update(startIp=16),
        'simulator-opcode-pointer': lambda v: v['childContract']['instructions'][0].update(operands='w25, [x24]'),
        'changed-instruction-bytes': lambda v: v['childContract']['instructions'][0].update(bytesHex='00000000'),
        'wrong-frame-spill': lambda v: v['childContract'].update(frameSpillOffset=0x88),
        'promoted-live-register-proof': lambda v: v['childContract'].update(liveRegisterContentsVerified=True),
        'wrong-fresh-author-mvid': lambda v: v['freshAuthorModules']['HostBudgetProbe.Payload.dll'].update(moduleMvid='0' * 32),
        'changed-private-methoddef': lambda v: v['freshAuthorModules']['HostBudgetProbe.Private.dll']['methods'].update({'HostBudgetUGC.Private.Helper.Finite': 0x06000002}),
        'missing-method-group': lambda v: v['requiredMethods'].pop(),
    }
    rejected = []
    for name, mutate in mutations.items():
        changed = copy.deepcopy(identity); mutate(changed)
        try:
            validate_identity(changed, image, spills)
        except RuntimeError:
            rejected.append({'name': name, 'rejected': True, 'inMemoryOnly': True})
        else:
            raise RuntimeError('Altered device entry preparation accepted: ' + name)
    altered = bytearray(image)
    at = 32
    for _ in range(struct.unpack_from('<I', altered, 16)[0]):
        kind, size = struct.unpack_from('<II', altered, at)
        if kind == 0x32:
            struct.pack_into('<I', altered, at + 8, 7)
            break
        at += size
    try:
        native(altered)
    except RuntimeError:
        rejected.append({'name': 'actual-macho-platform7-bytes', 'rejected': True, 'inMemoryOnly': True})
    else:
        raise RuntimeError('Simulator LC_BUILD_VERSION bytes accepted')
    return rejected


def authors(directory, pe):
    modules, required = {}, []
    preparation = read(directory / 'results.json')
    need(preparation['passed'] is True and preparation['phase'] == 'prepare'
         and preparation['postDeviceHostBuildCompiled'] is True
         and preparation['authorHashes'] == {n: v['sha256'] for n, v in AUTHOR.items()},
         'Exact post-device-host author preparation required')
    for name, expected in AUTHOR.items():
        path = directory / 'plugin' / name
        need(sha(path) == expected['sha256'], 'Fresh author bytes differ: ' + name)
        methods = pe['plugin_methods'](path, required=(), qualified=True)
        layout, mvid = pe['il_layout'](path), pe['pe_mvid'](path)
        need(layout['ilOnly'] is True and layout['managedNativeRva'] == 0
             and mvid['moduleMvid'] == expected['mvid'], 'Fresh author IL/MVID differs: ' + name)
        fixed = ['HostBudgetUGC.Base..ctor', 'HostBudgetUGC.Base.OnStart', 'HostBudgetUGC.Base.OnStop',
                 'HostBudgetUGC.Normal..ctor', 'HostBudgetUGC.Normal.OnStart', 'HostBudgetUGC.Normal.OnTick',
                 'HostBudgetUGC.FiniteCleanup.OnTick'] if name.endswith('Payload.dll') else [
                     'HostBudgetUGC.Private.Helper.Finite'] + [n for n in methods if n.endswith('.<Finite>b__0')]
        need(len(fixed) == (7 if name.endswith('Payload.dll') else 2) and set(fixed) <= set(methods),
             'Frozen nine method groups changed')
        modules[name] = {'sha256': sha(path), 'simpleName': name[:-4], 'methods': {n: methods[n] for n in fixed},
                         'layout': layout, **mvid}
        required.extend(name + ':' + n for n in fixed)
    return modules, required


READER = '''import json
from pathlib import Path
import lldb

def inspect(debugger):
    root=Path(__file__).parent
    c=json.loads((root/'request.json').read_text())
    target=debugger.GetSelectedTarget()
    if target.GetProcess().IsValid(): raise RuntimeError('Offline target has a process')
    bp=target.BreakpointCreateByLocation(c['source'],c['dispatchLine'])
    locations=[]
    def row(i):
        error=lldb.SBError()
        data=i.GetData(target).ReadRawData(error,0,i.GetByteSize())
        if error.Fail(): raise RuntimeError('Offline instruction bytes unavailable')
        if isinstance(data,str): data=data.encode('latin1')
        return {'filePc':i.GetAddress().GetFileAddress(),'mnemonic':i.GetMnemonic(target),
                'operands':i.GetOperands(target),'bytesHex':data.hex()}
    for loc in bp:
        address=loc.GetAddress()
        pc=address.GetFileAddress()
        def instructions(start,count):
            return [row(i) for i in target.ReadInstructions(address.GetModule().ResolveFileAddress(start),count)]
        locations.append({'filePc':pc,'line':address.GetLineEntry().GetLine(),
                          'before':instructions(pc-128,32),'instructions':instructions(pc,16)})
    symbols={}
    for name in ('InterpreterStub','PrepareInterpreterCode'):
        found=target.FindSymbols(name)
        matches=[found.GetContextAtIndex(i).GetSymbol().GetStartAddress() for i in range(found.GetSize())
                 if found.GetContextAtIndex(i).GetModule().GetFileSpec().GetFilename()=='libcoreclr.dylib']
        if len(matches)!=1: raise RuntimeError('Offline symbol not unique: '+name)
        a=matches[0]
        symbols[name]={'filePc':a.GetFileAddress(),
                      'instructions':[row(i) for i in target.ReadInstructions(a,16)]}
    (root/'offline-target.json').write_text(json.dumps({'targetProcessCreated':False,'locations':locations,'symbols':symbols},indent=2)+chr(10))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'build-receipt', 'application', 'author', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    need(platform.system() == 'Darwin', 'Offline Apple readers require the configured Mac')
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    result = {'passed': False, 'targetProcessCreated': False, 'appLaunched': False,
              'physicalDeviceVerified': False, 'nativeEntryProof': False, 'authorExecuted': False}
    try:
        pe = readers(); build = read(args.build_receipt)
        need(build['success'] is True and build['buildExit'] == 0 and build['target'] == 'ios.arm64'
             and build['configuration'] == 'Release' and build['commit'] == COMMIT
             and build['tree'] == TREE and build['nativeSha256'] == NATIVE_SHA,
             'Exact accepted device build required')
        proof = args.runtime.parent / 'source-proof.json'
        need(sha(proof) == PROOF_SHA, 'Frozen device source proof differs')
        need(command(['git', '-C', args.runtime, 'rev-parse', 'HEAD'], out, 'source-head').strip() == COMMIT
             and command(['git', '-C', args.runtime, 'rev-parse', 'HEAD^{tree}'], out, 'source-tree').strip() == TREE
             and not command(['git', '-C', args.runtime, 'status', '--porcelain', '--untracked-files=no'], out, 'source-status').strip(),
             'Current source HEAD/tree/status differs')
        for name, expected in read(proof)['sourceHashes'].items():
            need(sha(args.runtime / name) == expected, 'Live source changed: ' + name)
        source_native = args.runtime / 'artifacts/bin/coreclr/ios.arm64.Release/libcoreclr.dylib'
        app_native = args.application / 'app/Session.app/libcoreclr.dylib'
        source = args.runtime / 'src/coreclr/vm/interpexec.cpp'
        need(sha(args.application / 'results.json') == APP_RESULT_SHA, 'Accepted device app build receipt differs')
        image = source_native.read_bytes(); identity = native(image)
        need(identity['sha256'] == sha(app_native) == NATIVE_SHA, 'Device app/source native mismatch')
        dwarf = source_native.with_name(source_native.name + '.dwarf')
        dwarf_uuid = re.findall(r'UUID: ([0-9A-Fa-f-]+)', command(['xcrun', 'dwarfdump', '--uuid', dwarf], out, 'dwarf-uuid'))
        need(len(dwarf_uuid) == 1 and dwarf_uuid[0].replace('-', '').lower() == identity['uuid'], 'Device DWARF UUID mismatch')
        layouts = {}
        for name in FIELDS:
            raw = command(['xcrun', 'dwarfdump', '--name=' + name, '--show-children', '--recurse-depth=1', dwarf], out, name + '-dwarf')
            layouts[name] = pe['dwarf_layout'](raw, name)
        raw = command(['xcrun', 'dwarfdump', '--name=pFrame', dwarf], out, 'pframe-dwarf')
        spills = []
        for block in raw.split(chr(10) + chr(10)):
            if 'interpexec.cpp' not in block:
                continue
            for match in re.finditer(r'\[0x([0-9a-f]+), 0x([0-9a-f]+)\): DW_OP_breg(\d+) W\d+\+(\d+)', block):
                spills.append({'start': int(match[1], 16), 'end': int(match[2], 16),
                               'register': 'x' + match[3], 'offset': int(match[4]), 'die': block.splitlines()[0]})
        need(spills, 'Device child pFrame DWARF spill missing')
        lines = source.read_text().splitlines()
        anchors = [i for i, line in enumerate(lines) if '// Set execution state for the new frame' in line
                   and 'pMethod = pFrame->startIp->Method;' in lines[i + 1]
                   and 'if (stack + pMethod->allocaSize' in chr(10).join(lines[i:i + 10])]
        need(len(anchors) == 1, 'Current child source anchor not unique')
        dispatch = [i + 1 for i in range(anchors[0], anchors[0] + 20) if 'INTOP_NEXT;' in lines[i]]
        need(len(dispatch) == 1, 'Current child dispatch line not unique')
        modules, required = authors(args.author, pe)
        write(out / 'request.json', {'source': str(source), 'dispatchLine': dispatch[0], 'offlineOnly': True})
        (out / 'offline_reader.py').write_text(READER, encoding='ascii')
        command(['xcrun', 'lldb', '--batch', '--no-lldbinit', '-o', 'target create ' + str(source_native),
                 '-o', 'target symbols add ' + str(dwarf), '-o', 'script import sys; sys.path.insert(0, ' + repr(str(out)) + ')',
                 '-o', 'script import offline_reader; offline_reader.inspect(lldb.debugger)'], out, 'offline-lldb')
        observed = read(out / 'offline-target.json')
        need(observed['targetProcessCreated'] is False and len(observed['locations']) == 1, 'Offline child dispatch location not unique')
        contract = observed['locations'][0]
        need(contract['line'] == dispatch[0], 'Child source line differs')
        # Read this product's code and DWARF instead of assuming simulator registers.
        child = contract['instructions']
        op = re.fullmatch(r'(w\d+), \[(x\d+)\]', child[0]['operands'])
        frame = re.fullmatch(r'(x\d+), \[(x\d+), #0x([0-9a-f]+)\]', child[2]['operands'])
        need(child[0]['mnemonic'] == child[2]['mnemonic'] == 'ldr' and op and frame,
             'Review new device first-opcode/frame spill sequence')
        headers = [r for r in contract['before'] if (r['mnemonic'], r['operands']) == ('ldr', 'x8, [x9], #0x8')]
        stores = [r for r in contract['before'] if (r['mnemonic'], r['operands']) == ('str', 'x8, [x19, #0x98]')]
        need(len(headers) == len(stores) == 1 and stores[0]['filePc'] < headers[0]['filePc'],
             'Recorded child header load must follow the frame spill store')
        matches = [v for v in spills if v['register'] == frame[2] and v['offset'] == int(frame[3], 16)
                   and v['start'] <= headers[0]['filePc'] < v['end']]
        need(len(matches) == 1, 'Device child spill does not bind matching DWARF')
        contract.update(opcodeRegister=op[1], opcodePointerRegister=op[2], frameRegister=frame[2],
                        frameSpillOffset=int(frame[3], 16), matchingDwarfSpills=matches,
                        frameSpillStoreInstruction=stores[0], contextDwarfInstruction=headers[0],
                        pFrameDwarfCoversCapturePc=any(v['start'] <= contract['filePc'] < v['end'] for v in matches),
                        liveRegisterContentsVerified=False,
                        dwarfScopeRationale='Contextual pFrame location at the recorded bytecode-header load, after the frame spill store. The DWARF interval does not cover the capture PC; actual spill reload bytes bind the offset, not live register contents.')
        prepared = {'sourceCommit': COMMIT, 'sourceTree': TREE, 'sourceProofSha256': PROOF_SHA,
              'buildReceiptSha256': sha(args.build_receipt), 'applicationResultSha256': APP_RESULT_SHA,
              'native': identity, 'dwarfSha256': sha(dwarf), 'dwarfUuid': dwarf_uuid[0], 'sourceSha256': sha(source),
              'layouts': layouts, 'childContract': contract, 'symbols': observed['symbols'],
              'freshAuthorModules': modules, 'requiredMethods': required,
              'helperHashes': {name: value[0] for name, value in HELPERS.items()}, 'driverSha256': sha(__file__)}
        validate_identity(prepared, image, spills)
        rejected = controls(prepared, image, spills) if args.selftest else []
        write(out / 'identity.json', prepared)
        write(out / 'controls.json', rejected)
        need(sha(source_native) == sha(app_native) == NATIVE_SHA and sha(proof) == PROOF_SHA,
             'Original device bytes changed during offline inspection')
        need(all(sha(args.author / 'plugin' / n) == v['sha256'] for n, v in AUTHOR.items()), 'Original fresh author bytes changed')
        result.update(passed=True, requiredMethodGroups=len(required), dispatchLine=dispatch[0],
                      corruptionControls=len(rejected),
                      nativeUuid=identity['uuid'], childFilePc=contract['filePc'],
                      scope='Matching device Mach-O/DWARF/source and fresh IL method metadata only; no target process, author execution or interpreter-entry proof.',
                      pending=['Implement and review physical observer callbacks and app launch bindings.',
                               'Reachable provisioned target, signed-to-installed host provenance and post-install author readback.',
                               'Actual stub/child entry samples with loaded Module MVID/token/bytecode identity and lifecycle15/73.'])
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        write(out / 'results.json', result)
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
