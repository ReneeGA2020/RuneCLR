#!/usr/bin/env python3
"""Prepare current iOS batch symbols and metadata without creating a debug target."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import platform
import plistlib
import re
import struct
import subprocess
import uuid

COMMIT = '3126bbc9a8851a09ac6435b18a12882bad48f3ee'
TREE = '710936ae1729a5689ab0e0896f3cf722ddd3d31c'
PROOF_SHA = '29d83ae68ca57ec2067261d15a901e81f8422981609f1fe6aaad5cb37879de5e'
BUILD_SHA = 'c071b2c67103b5646f37cffdc8a442a8e711105585df9740635459ef1bb86745'
SOURCE_NATIVE_SHA = 'b0670a7604bd8857409f1ea9ac543f293c99047286f6f762d0eb720ca6f877ae'
SIGNED_NATIVE_SHA = '71b0aa28e76e8672ff7041a442f1a2696006ed53f2fc423f7324385713f05ef9'
METADATA_SHA = '29a782a093ee3a6dca355562c08d79b87c9afe96046218190df9507b1422fa7e'
MVID_SHA = '1991b6c0906d807b3b69dad69ea151f9ffbb8369c5aad7ceef1010a7fecd4dc1'
CADENCE_AUTHOR_SHA = 'd743ecb6ba897366a276ab700e79a42f3885ba2eaf69d1713bb086346f2fd09e'
METHODS = tuple('BatchBoundary.Author.Entries.' + n for n in
                ('ShortReturn', 'OrdinaryThrow', 'FiniteProgress', 'EndlessCatch'))
SYMBOLS = {
    'interpreter': '__Z16InterpExecMethodP16InterpreterFrameP24InterpMethodContextFrameP19InterpThreadContextP19ExceptionClauseArgs',
    'admit': '__ZN17RuneCLRBatchState5AdmitEP23RuneCLRInstructionMeterPKvS3_',
    'settlement': '__ZN23RuneCLRInstructionMeter11RecordBatchEj',
}
FIELDS = {
    'RuneCLRInstructionMeter': ('m_terminalPrototype', 'm_phaseAcquireLoad', 'm_derivedLedger',
                               'm_remaining', 'm_executed', 'm_phase', 'm_batchInterval'),
    'RuneCLRBatchState': ('m_meter', 'm_frame', 'm_start', 'm_pending'),
    'InterpMethodContextFrame': ('startIp',),
    'InterpMethod': ('methodHnd', 'codeSize'),
    'MethodDesc': ('m_chunkIndex', 'm_wFlags3AndTokenRemainder', 'm_interpreterCode'),
    'MethodDescChunk': ('m_methodTable', 'm_flagsAndTokenRange'),
    'MethodTable': ('m_dwFlags', 'm_pModule'),
    'Module': ('m_pSimpleName', 'm_path', 'm_baseAddress', 'm_pAssembly', 'm_pPEAssembly'),
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


def inventory(path):
    return {p.relative_to(path).as_posix(): sha(p) for p in sorted(path.rglob('*')) if p.is_file()}


def command(argv, output):
    write(Path(str(output) + '.command.json'), {'argv': [str(x) for x in argv], 'timeout': 45})
    q = subprocess.run([str(x) for x in argv], capture_output=True, text=True, timeout=45)
    output.write_text(q.stdout + q.stderr, encoding='utf-8')
    need(q.returncode == 0, 'Offline reader failed: ' + str(output))
    return q.stdout


def readers():
    namespace = {'struct': struct, 'uuid': uuid}
    for filename, expected, function in (('ios-r2r-release-verify.py', METADATA_SHA, 'plugin_methods'),
                                         ('ios-budget-increment-entry.py', MVID_SHA, 'pe_mvid')):
        path = Path(__file__).with_name(filename)
        need(sha(path) == expected, 'Frozen PE reader differs: ' + filename)
        tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function]
        need(len(selected) == 1, 'PE reader function not unique')
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def il_layout(path):
    data = path.read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    optional = pe + 24
    directories = optional + (112 if struct.unpack_from('<H', data, optional)[0] == 0x20b else 96)
    cli = struct.unpack_from('<I', data, directories + 112)[0]
    start = optional + struct.unpack_from('<H', data, pe + 20)[0]
    for i in range(struct.unpack_from('<H', data, pe + 6)[0]):
        size, rva, raw_size, raw = struct.unpack_from('<IIII', data, start + i * 40 + 8)
        if rva <= cli < rva + max(size, raw_size):
            header = raw + cli - rva
            return {'ilOnly': bool(struct.unpack_from('<I', data, header + 16)[0] & 1),
                    'managedNativeRva': struct.unpack_from('<I', data, header + 64)[0]}
    raise RuntimeError('Managed header missing: ' + str(path))


def native(path):
    data = path.read_bytes()
    need(len(data) >= 32 and struct.unpack_from('<II', data) == (0xfeedfacf, 0x100000c)
         and struct.unpack_from('<I', data, 12)[0] == 6, 'Expected thin ARM64 MH_DYLIB')
    end = 32 + struct.unpack_from('<I', data, 20)[0]
    need(end <= len(data), 'Invalid Mach-O command region')
    offset, image_uuid, platforms, sections = 32, [], [], {}
    digest = hashlib.sha256()
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        need(offset + 8 <= end, 'Short Mach-O command')
        kind, size = struct.unpack_from('<II', data, offset)
        need(size >= 8 and offset + size <= end, 'Invalid Mach-O command size')
        if kind == 0x1b:
            need(size >= 24, 'Short LC_UUID')
            image_uuid.append(data[offset + 8:offset + 24].hex())
        if kind == 0x32:
            need(size >= 24, 'Short LC_BUILD_VERSION')
            platforms.append(struct.unpack_from('<I', data, offset + 8)[0])
        if kind == 0x19:
            need(size >= 72, 'Short segment command')
            count = struct.unpack_from('<I', data, offset + 64)[0]
            need(72 + 80 * count <= size, 'Short segment sections')
            for i in range(count):
                at = offset + 72 + i * 80
                section, segment = (data[at + n:at + n + 16].split(bytes([0]))[0].decode('ascii')
                                    for n in (0, 16))
                address, length = struct.unpack_from('<QQ', data, at + 32)
                start = struct.unpack_from('<I', data, at + 48)[0]
                if start and length:
                    need(start + length <= len(data), 'File-backed section exceeds image')
                    digest.update(data[at:at + 32]); digest.update(data[start:start + length])
                    sections[segment + ',' + section] = {'address': address, 'length': length, 'offset': start}
        offset += size
    need(offset == end and platforms == [7] and len(image_uuid) == 1 and
         '__TEXT,__text' in sections, 'Native UUID/platform/text contract differs')
    return {'uuid': image_uuid[0], 'platform': 7, 'fileBackedSectionsSha256': digest.hexdigest(),
            'sections': sections, 'sha256': sha(path)}


def dwarf_layout(text, name):
    entries = list(re.finditer(r'^0x[0-9a-f]+: ( *)DW_TAG_([a-z_]+)', text, re.M))
    layouts = []
    for i, node in enumerate(entries):
        end = entries[i + 1].start() if i + 1 < len(entries) else len(text)
        own = text[node.start():end]
        if (node[2] not in ('class_type', 'structure_type') or
                re.search(r'DW_AT_name\s+\("' + re.escape(name) + r'"\)', own) is None):
            continue
        size = re.search(r'DW_AT_byte_size\s+\((0x[0-9a-f]+)\)', own)
        if size is None:
            continue
        fields = {}
        for j in range(i + 1, len(entries)):
            child = entries[j]
            if len(child[1]) <= len(node[1]):
                break
            if child[2] != 'member' or len(child[1]) != len(node[1]) + 2:
                continue
            end = entries[j + 1].start() if j + 1 < len(entries) else len(text)
            own = text[child.start():end]
            member = re.search(r'DW_AT_name\s+\("([^"]+)"\)', own)
            location = re.search(r'DW_AT_data_member_location\s+\((0x[0-9a-f]+)\)', own)
            if member and location:
                fields[member[1]] = int(location[1], 16)
        if set(FIELDS[name]) <= set(fields):
            layouts.append({'size': int(size[1], 16), 'fields': {n: fields[n] for n in FIELDS[name]}})
    need(layouts and all(x == layouts[0] for x in layouts), 'No consistent complete DWARF layout: ' + name)
    return layouts[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'build-receipt', 'application', 'functional', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--cadence-author', type=Path)
    args = parser.parse_args()
    need(platform.system() == 'Darwin', 'Offline Apple readers require the configured Mac')
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    result = {'passed': False, 'debuggerStarted': False, 'targetProcessCreated': False,
              'nativeEntryProof': False, 'liveBatchPathVerified': False,
              'performanceMeasured': False, 'physicalDeviceVerified': False}
    try:
        build = read(args.build_receipt); state = read(args.application / 'state.json')
        accepted = read(args.functional / 'results.json'); manifest = read(args.inputs / 'input-manifest.json')
        need(sha(args.build_receipt) == BUILD_SHA and build['success'] and build['buildExit'] == 0
             and build['commit'] == state['sourceCommit'] == COMMIT
             and build['tree'] == state['sourceTree'] == TREE, 'Exact accepted build required')
        proof = args.runtime.parent / 'source-proof.json'
        need(sha(proof) == PROOF_SHA, 'Source proof differs')
        need(command(['git', '-C', args.runtime, 'rev-parse', 'HEAD'], out / 'source-commit.txt').strip() == COMMIT
             and command(['git', '-C', args.runtime, 'rev-parse', 'HEAD^{tree}'], out / 'source-tree.txt').strip() == TREE
             and not command(['git', '-C', args.runtime, 'status', '--porcelain', '--untracked-files=no'],
                             out / 'source-status.txt').strip(), 'Current source HEAD/tree/status differs')
        for n, expected in read(proof)['sourceHashes'].items():
            need(sha(args.runtime / n) == expected, 'Live source changed: ' + n)
        need(accepted['passed'] and accepted['processes'] == 5 and accepted['collections'] == 168
             and accepted['cleanupSucceeded'] and accepted['buildReceiptSha256'] == BUILD_SHA
             and accepted['inputManifestSha256'] == sha(args.inputs / 'input-manifest.json')
             == state['inputManifestSha256'], 'Accepted five-lane functional binding differs')
        app = Path(state['app']); original = inventory(app)
        need(original == state['bundleHashes'], 'Accepted signed bundle changed')
        for n, expected in manifest['files'].items():
            need(sha(args.inputs / n) == expected, 'Boundary input changed: ' + n)
        source_native = args.runtime / 'artifacts/bin/coreclr/iossimulator.arm64.Release/libcoreclr.dylib'
        signed_native = app / 'libcoreclr.dylib'; dwarf = source_native.with_name(source_native.name + '.dwarf')
        need(sha(source_native) == SOURCE_NATIVE_SHA == build['nativeSha256']
             and sha(signed_native) == SIGNED_NATIVE_SHA == state['native']['sha256']
             and dwarf.is_file(), 'Unsigned/signed native or DWARF differs')
        first, signed = native(source_native), native(signed_native)
        need({k: v for k, v in first.items() if k != 'sha256'} ==
             {k: v for k, v in signed.items() if k != 'sha256'}, 'Signing changed code/data/UUID/platform')
        uuids = re.findall(r'UUID: ([0-9A-Fa-f-]+)', command(
            ['xcrun', 'dwarfdump', '--uuid', dwarf], out / 'dwarf-uuid.txt'))
        need(len(uuids) == 1 and uuids[0].replace('-', '').lower() == first['uuid'], 'DWARF UUID differs')
        nm = command(['xcrun', 'nm', '-nm', source_native], out / 'symbols.txt')
        symbols = {}
        for name, symbol in SYMBOLS.items():
            found = re.findall(r'^([0-9a-f]+) \(__TEXT,__text\).* ' + re.escape(symbol) + r'$', nm, re.M)
            need(len(found) == 1, 'Current native symbol not unique: ' + name)
            address = int(found[0], 16); symbols[name] = {'name': symbol, 'filePc': address}
            command(['xcrun', 'llvm-objdump', '--disassemble', '--start-address=' + hex(address),
                     '--stop-address=' + hex(address + (512 if name == 'admit' else 256)), source_native],
                    out / (name + '-instructions.txt'))
        layouts = {}
        for name in FIELDS:
            raw = command(['xcrun', 'dwarfdump', '--name=' + name, '--show-children', '--recurse-depth=1', dwarf],
                          out / (name + '-dwarf.txt'))
            layouts[name] = dwarf_layout(raw, name)
        meter, batch = layouts['RuneCLRInstructionMeter'], layouts['RuneCLRBatchState']
        need(meter['size'] == 72 and meter['fields']['m_batchInterval'] == 64 and
             meter['fields']['m_phase'] == 40 and batch == {'size': 32, 'fields':
             {'m_meter': 0, 'm_frame': 8, 'm_start': 16, 'm_pending': 24}}, 'Current batch/meter layout differs')
        raw = command(['xcrun', 'dwarfdump', '--name=runeclrBatch', dwarf], out / 'batch-local-dwarf.txt')
        local = re.findall(r'DW_OP_breg19 W19\+(\d+)', raw)
        need(len(local) == 1, 'Current invocation batch DWARF location not unique')
        pe = readers(); author = args.inputs / 'author/BatchBoundary.Author.dll'
        methods = pe['plugin_methods'](author, required=METHODS, qualified=True)
        layout = il_layout(author)
        need(layout['ilOnly'] and not layout['managedNativeRva'], 'Boundary author must remain IL only')
        owned = read(args.functional / 'owned-simulator.json')
        need(owned['bundleId'] == state['bundleId'] and
             read(args.functional / 'author-before.json') == read(args.functional / 'author-after.json'),
             'Accepted simulator bundle or installed-author receipts differ')
        containers = Path.home() / 'Library/Developer/CoreSimulator/Devices' / owned['id'] / 'data/Containers/Data/Application'
        candidates = []
        for container in sorted(containers.iterdir()):
            metadata = container / '.com.apple.mobile_container_manager.metadata.plist'
            if metadata.is_file():
                with metadata.open('rb') as stream:
                    identifier = plistlib.load(stream).get('MCMMetadataIdentifier')
                if identifier == state['bundleId']:
                    candidates.append(container / 'Documents/batch-plugin/BatchBoundary.Author.dll')
        need(len(candidates) == 1, 'Accepted simulator offline data-container identity not unique')
        installed_author = candidates[0]
        write(out / 'accepted-data-container.json', {'basis': 'Read-only owned simulator container metadata; no boot or simctl lookup.',
              'simulatorId': owned['id'], 'bundleId': state['bundleId'], 'authorPath': str(installed_author),
              'acceptedReceiptSha256': sha(args.functional / 'author-after.json')})
        need(sha(installed_author) == read(args.functional / 'author-after.json')['BatchBoundary.Author.dll'],
             'Accepted author receipt differs from offline installed file')
        need(sha(installed_author) == sha(author) and pe['pe_mvid'](installed_author) == pe['pe_mvid'](author),
             'Accepted post-install author path or MVID differs')
        module = {'sha256': sha(author), 'methods': {n: methods[n] for n in METHODS},
                  'installedAuthorPath': str(installed_author), 'layout': layout, **pe['pe_mvid'](author)}
        cadence = {'requiresSeparateTrustedHostAndApp': True, 'mobileLongBatchConfirmed': False,
                   'method': 'RuneCLR.BatchKernel.Kernel.Execute', 'iterations': 100000,
                   'expectedChecksum': 12749776, 'executionBudget': 1000000000000}
        if args.cadence_author is not None:
            need(sha(args.cadence_author) == CADENCE_AUTHOR_SHA, 'Frozen Windows cadence author differs')
            layout = il_layout(args.cadence_author)
            need(layout['ilOnly'] and not layout['managedNativeRva'], 'Cadence author must remain IL only')
            names = pe['plugin_methods'](args.cadence_author, required=(cadence['method'],), qualified=True)
            cadence.update(authorSha256=CADENCE_AUTHOR_SHA, methodDefToken=names[cadence['method']],
                           layout=layout, module=pe['pe_mvid'](args.cadence_author))
        plan = {'entryLane': {'reuseAcceptedBoundaryApp': True, 'requiredMethods': METHODS,
                 'breakpoint': symbols['interpreter'], 'abi': {'contextFrame': 'x1', 'exceptionArgs': 'x3'},
                 'coverage': 'At least one actual interpreter invocation per four direct author methods; not all invocations or first-opcode execution.'},
                'cadenceLanes': {'configuredIntervals': [100, 1000], 'samplesPerKindPerLane': 2,
                 'breakpoint': symbols['settlement'], 'abi': {'meter': 'x0', 'admitted': 'w1'},
                 'gate': {'terminalPrototype': 1, 'phaseAcquireLoad': 1, 'derivedLedger': 0, 'phase': 0},
                 'full': 'admitted == configuredInterval', 'partial': '0 < admitted < configuredInterval',
                 'bindAuthor': 'Read batch frame/start, MethodDesc token, loaded PE MVID and actual Module path; preserve caller stack.',
                 'batchLocal': {'register': 'x19', 'offset': int(local[0]), 'basis': 'Matching new DWARF; verify live caller register/PC before use.'},
                 'workload': cadence, 'boundaryFixtureGuaranteesLongBatches': False},
                'observerLimits': {'hitCap': 100000, 'timeoutSeconds': 180,
                 'disableAfterCoverage': True, 'doNotTraceEveryOpcode': True,
                 'newCaptureReviewRequired': True},
                'pending': ['Implement and review observer callbacks against these fresh addresses and DWARF.',
                            'Build separate trusted high-budget cadence host/app with late frozen Kernel IL.',
                            'Capture and validate full/partial samples; preparation does not establish cadence.']}
        write(out / 'observer-plan.json', plan)
        write(out / 'identity.json', {'sourceNative': first, 'signedNative': signed,
              'dwarfSha256': sha(dwarf), 'buildReceiptSha256': BUILD_SHA, 'sourceProofSha256': PROOF_SHA,
              'sourceCommit': COMMIT, 'sourceTree': TREE, 'symbols': symbols, 'layouts': layouts,
              'boundaryAuthor': module, 'driverSha256': sha(__file__)})
        need(inventory(app) == original and all(sha(args.inputs / n) == s for n, s in manifest['files'].items()),
             'Original accepted app or boundary inputs changed')
        result.update(passed=True, scope='Offline symbol, DWARF, immutable native and author metadata preparation only; no debugger, app launch or mobile cadence evidence.')
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        write(out / 'results.json', result); print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
