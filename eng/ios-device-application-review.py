#!/usr/bin/env python3
"""Read actual app bytes independently; never build, load, sign or run target code."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import struct
import uuid

TRUSTED = {
    'RuneCLR.Abstractions.dll': '86bc966dd4e9f5f349b0c3d8fb869e180f76823af0ee6aa6e1ce64e7bbd16f31',
    'RuneCLR.Packages.dll': 'bf16e2abe3d085509bec1b3019b51915221bc4cebec683c206ebb538e1a74de8',
    'RuneCLR.Runtime.dll': 'efe46aae2b1d867422ec770fd2f6a294a136b61c22d048ff1bd3d73a737a3424',
    'MobileHostBudgetProbe.dll': 'f34c78aca7bffe34584a02838c67d0e22c1e0ee1c1403ff95fceed9223f65d0b'}


def need(value, reason):
    if not value:
        raise ValueError(reason)


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


# ECMA-335 II.22 table layouts and II.24 coded-index widths.
CODED = {
    'TypeDefOrRef': (2, [2, 1, 27]), 'HasConstant': (2, [4, 8, 23]),
    'HasCustomAttribute': (5, [6, 4, 1, 2, 8, 9, 10, 0, 14, 23, 20, 17, 26, 27, 32, 35, 38, 39, 40, 42, 44, 43]),
    'HasFieldMarshal': (1, [4, 8]), 'HasDeclSecurity': (2, [2, 6, 32]),
    'MemberRefParent': (3, [2, 1, 26, 6, 27]), 'HasSemantics': (1, [20, 23]),
    'MethodDefOrRef': (1, [6, 10]), 'MemberForwarded': (1, [4, 6]),
    'Implementation': (2, [38, 35, 39]), 'CustomAttributeType': (3, [6, 10]),
    'ResolutionScope': (2, [0, 26, 35, 1]), 'TypeOrMethodDef': (1, [2, 6])}
SCHEMAS = [
    'u2 str guid guid guid', 'ResolutionScope str str', 'u4 str str TypeDefOrRef t4 t6',
    't4', 'u2 str blob', 't6', 'u4 u2 u2 str blob t8', 't8', 'u2 u2 str',
    't2 TypeDefOrRef', 'MemberRefParent str blob', 'u2 HasConstant blob',
    'HasCustomAttribute CustomAttributeType blob', 'HasFieldMarshal blob', 'u2 HasDeclSecurity blob',
    'u2 u4 t2', 'u4 t4', 'blob', 't2 t20', 't20', 'u2 str TypeDefOrRef',
    't2 t23', 't23', 'u2 str blob', 'u2 t6 HasSemantics', 't2 MethodDefOrRef MethodDefOrRef',
    'str', 'blob', 'u2 MemberForwarded str t26', 'u4 t4', 'u4 u4', 'u4',
    'u4 u2 u2 u2 u2 u4 blob str str', 'u4', 'u4 u4 u4',
    'u2 u2 u2 u2 u4 blob str str blob', 'u4 t35', 'u4 u4 u4 t35',
    'u4 str blob', 'u4 u4 str str Implementation', 'u4 u4 str Implementation',
    't2 t2', 'u2 u2 TypeOrMethodDef str', 'MethodDefOrRef blob', 't42 TypeDefOrRef']


def managed(path):
    image = Path(path).read_bytes()
    need(image[:2] == b'MZ', 'Managed input missing DOS header')
    pe = struct.unpack_from('<I', image, 60)[0]
    need(image[pe:pe + 4] == b'PE\0\0', 'Managed input missing PE header')
    sections, optional_size = struct.unpack_from('<H12xH', image, pe + 6)
    optional = pe + 24
    magic = struct.unpack_from('<H', image, optional)[0]
    directory = optional + (112 if magic == 0x20b else 96)
    need(magic in (0x10b, 0x20b), 'Unknown PE optional header')
    section_start = optional + optional_size
    regions = []
    for i in range(sections):
        size, rva, raw_size, offset = struct.unpack_from('<4I', image, section_start + i * 40 + 8)
        regions.append((rva, max(size, raw_size), offset, raw_size))

    def at(rva, size=1):
        for start, span, offset, raw_size in regions:
            if start <= rva and rva + size <= start + raw_size:
                return offset + rva - start
        raise ValueError('PE RVA outside actual raw sections')

    cli_rva, cli_size = struct.unpack_from('<2I', image, directory + 14 * 8)
    need(cli_size >= 72, 'Missing CLI header')
    cli = at(cli_rva, cli_size)
    metadata_rva, metadata_size = struct.unpack_from('<2I', image, cli + 8)
    native_rva, native_size = struct.unpack_from('<2I', image, cli + 64)
    r2r = None
    if native_rva:
        native_offset = at(native_rva, native_size)
        signature, major, minor, flags, section_count = struct.unpack_from('<IHHII', image, native_offset)
        need(signature == 0x00525452 and native_size >= 16 + section_count * 12, 'Invalid actual ReadyToRun header')
        owner = None
        for i in range(section_count):
            section, section_rva, section_size = struct.unpack_from('<3I', image, native_offset + 16 + i * 12)
            if section == 116:
                section_offset = at(section_rva, section_size)
                value = image[section_offset:section_offset + section_size]
                need(value.endswith(b'\0') and b'\0' not in value[:-1], 'Invalid composite owner name')
                owner = value[:-1].decode('utf-8')
        r2r = {'major': major, 'minor': minor, 'flags': flags, 'ownerComposite': owner}
    start = at(metadata_rva, metadata_size)
    metadata = image[start:start + metadata_size]
    need(metadata[:4] == b'BSJB', 'Unknown CLI metadata root')
    version_size = struct.unpack_from('<I', metadata, 12)[0]
    cursor = (16 + version_size + 3) & ~3
    stream_count = struct.unpack_from('<H', metadata, cursor + 2)[0]
    cursor += 4
    root_header = digest(metadata[:cursor])
    streams, stream_offsets = {}, {}
    for i in range(stream_count):
        offset, size = struct.unpack_from('<2I', metadata, cursor)
        end = metadata.index(0, cursor + 8)
        name = metadata[cursor + 8:end].decode('ascii')
        need(name not in streams and offset + size <= len(metadata), 'Invalid metadata stream')
        streams[name] = metadata[offset:offset + size]
        stream_offsets[name] = start + offset
        cursor = (end + 4) & ~3
    table_name = '#~' if '#~' in streams else '#-'
    table = streams[table_name]
    heap_sizes = table[6]
    valid = struct.unpack_from('<Q', table, 8)[0]
    counts, cursor = {}, 24
    for number in range(64):
        if valid & (1 << number):
            need(number < len(SCHEMAS), 'Unsupported metadata table')
            counts[number] = struct.unpack_from('<I', table, cursor)[0]
            cursor += 4

    def width(kind):
        if kind == 'u2':
            return 2
        if kind == 'u4':
            return 4
        if kind in ['str', 'guid', 'blob']:
            return 4 if heap_sizes & {'str': 1, 'guid': 2, 'blob': 4}[kind] else 2
        if kind.startswith('t') and kind[1:].isdigit():
            return 4 if counts.get(int(kind[1:]), 0) >= 65536 else 2
        bits, targets = CODED[kind]
        return 4 if max(counts.get(n, 0) for n in targets) >= 1 << (16 - bits) else 2

    locations = {}
    for number, count in sorted(counts.items()):
        kinds = SCHEMAS[number].split()
        widths = [width(kind) for kind in kinds]
        size = sum(widths)
        locations[number] = (cursor, widths, size)
        cursor += count * size
    need(cursor <= len(table), 'Truncated metadata table rows')

    def row(number, index):
        start, widths, size = locations[number]
        need(1 <= index <= counts[number], 'Invalid metadata row')
        offset, result = start + (index - 1) * size, []
        for length in widths:
            result.append(int.from_bytes(table[offset:offset + length], 'little'))
            offset += length
        return result

    def string(index):
        heap = streams['#Strings']
        return heap[index:heap.index(0, index)].decode('utf-8')

    def blob(index):
        heap = streams['#Blob']
        first = heap[index]
        if first < 128:
            length, offset = first, index + 1
        elif first < 192:
            length, offset = ((first & 63) << 8) | heap[index + 1], index + 2
        else:
            need(first < 224, 'Invalid compressed metadata blob length')
            length, offset = ((first & 31) << 24) | int.from_bytes(heap[index + 1:index + 4], 'big'), index + 4
        need(offset + length <= len(heap), 'Truncated metadata blob')
        return heap[offset:offset + length]

    def body(rva):
        if not rva:
            return None
        offset = at(rva)
        first = image[offset]
        if first & 3 == 2:
            end = offset + 1 + (first >> 2)
        else:
            flags = struct.unpack_from('<H', image, offset)[0]
            need(flags & 3 == 3, 'Unknown method header')
            header = (flags >> 12) * 4
            code_size = struct.unpack_from('<I', image, offset + 4)[0]
            end = offset + header + code_size
            if flags & 8:
                end = (end + 3) & ~3
                while True:
                    section = image[end]
                    size = int.from_bytes(image[end + 1:end + 4], 'little') if section & 64 else image[end + 1]
                    need(size >= 4, 'Invalid method data section')
                    end += size
                    if not section & 128:
                        break
                    end = (end + 3) & ~3
        need(end <= len(image), 'Truncated method body')
        return {'bytes': end - offset, 'sha256': digest(image[offset:end])}

    module = row(0, 1)
    guid_index = module[2]
    mvid = str(uuid.UUID(bytes_le=streams['#GUID'][(guid_index - 1) * 16:guid_index * 16]))
    assembly = row(32, 1)
    identity = {'name': string(assembly[7]), 'version': assembly[1:5], 'flags': assembly[5],
                'publicKeyHex': blob(assembly[6]).hex(), 'culture': string(assembly[8])}
    methods = []
    for i in range(1, counts.get(6, 0) + 1):
        values = row(6, i)
        methods.append({'token': 0x06000000 | i, 'name': string(values[3]),
                        'implFlags': values[1], 'attributes': values[2],
                        'signatureHex': blob(values[4]).hex(), 'body': body(values[0])})
    class_sizes = {row(15, i)[2]: row(15, i)[1] for i in range(1, counts.get(15, 0) + 1)}
    initialized_fields = []
    primitive_sizes = {2: 1, 3: 2, 4: 1, 5: 1, 6: 2, 7: 2, 8: 4, 9: 4,
                       10: 8, 11: 8, 12: 4, 13: 8}
    for i in range(1, counts.get(29, 0) + 1):
        rva, field_index = row(29, i)
        field = row(4, field_index)
        signature = blob(field[2])
        need(signature[0] == 6, 'Invalid initialized field signature')
        if signature[1] in primitive_sizes:
            size = primitive_sizes[signature[1]]
        else:
            need(signature[1] == 0x11, 'Unsupported initialized field type')
            token_bytes = signature[2:]
            first = token_bytes[0]
            if first < 128:
                token = first
            elif first < 192:
                token = ((first & 63) << 8) | token_bytes[1]
            else:
                need(first < 224, 'Invalid initialized field type token')
                token = ((first & 31) << 24) | int.from_bytes(token_bytes[1:4], 'big')
            need(token & 3 == 0 and token >> 2 in class_sizes, 'Initialized field TypeDef class size missing')
            size = class_sizes[token >> 2]
        offset = at(rva, size)
        initialized_fields.append({'token': 0x04000000 | field_index, 'name': string(field[1]),
                                   'size': size, 'sha256': digest(image[offset:offset + size])})
    # R2R can relocate IL and initialized field storage; compare every remaining metadata byte.
    canonical = bytearray(table)
    for number in (6, 29):
        if number not in locations:
            continue
        start, widths, size = locations[number]
        for i in range(counts[number]):
            canonical[start + i * size:start + i * size + 4] = b'\0' * 4
    canonical_streams = {name: digest(bytes(canonical) if name == table_name else value)
                         for name, value in streams.items()}
    return {'sha256': digest(image), 'metadataSha256': digest(metadata), 'canonicalStreams': canonical_streams,
            'metadataStreamImageOffsets': stream_offsets,
            'metadataRootHeaderSha256': root_header,
            'mvid': mvid, 'identity': identity, 'managedNativeRva': native_rva, 'managedNativeSize': native_size,
            'readyToRun': r2r, 'tableCounts': counts, 'methods': methods, 'initializedFields': initialized_fields}


def native(path):
    image = Path(path).read_bytes()
    need(len(image) >= 32 and struct.unpack_from('<2I', image) == (0xfeedfacf, 0x100000c),
         'Expected thin ARM64 Mach-O')
    kind, count, size = struct.unpack_from('<3I', image, 12)
    cursor, limit, versions, dependencies, signatures, rpaths = 32, 32 + size, [], [], [], []
    segments, symbols = [], None
    need(limit <= len(image), 'Truncated Mach-O command table')
    for i in range(count):
        command, length = struct.unpack_from('<2I', image, cursor)
        need(length >= 8 and cursor + length <= limit, 'Invalid Mach-O command bounds')
        payload = image[cursor:cursor + length]
        if command == 0x32:
            platform, minimum, sdk, tools = struct.unpack_from('<4I', payload, 8)
            need(length == 24 + tools * 8, 'Invalid LC_BUILD_VERSION')
            versions.append({'platform': platform, 'minimum': minimum, 'sdk': sdk})
        elif command in [0xc, 0x80000018, 0x8000001f, 0x80000023]:
            offset = struct.unpack_from('<I', payload, 8)[0]
            dependencies.append(payload[offset:payload.index(0, offset)].decode())
        elif command == 0x8000001c:
            offset = struct.unpack_from('<I', payload, 8)[0]
            rpaths.append(payload[offset:payload.index(0, offset)].decode())
        elif command == 0x1d:
            signatures.append(list(struct.unpack_from('<2I', payload, 8)))
        elif command == 0x19:
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<4Q', payload, 24)
            segments.append((vmaddr, vmsize, fileoff, filesize))
        elif command == 2:
            symbols = struct.unpack_from('<4I', payload, 8)
        cursor += length
    need(cursor == limit and len(versions) == 1 and versions[0]['platform'] == 2,
         'Device platform2 required')
    need(versions[0]['minimum'] <= 983808, 'Native minimum exceeds app minimum15.3')
    rtr_header = None
    if symbols:
        symbol_offset, symbol_count, string_offset, string_size = symbols
        need(symbol_offset + symbol_count * 16 <= len(image) and string_offset + string_size <= len(image),
             'Truncated Mach-O symbol table')
        for i in range(symbol_count):
            name_offset, kind_flags, section, description, value = struct.unpack_from('<IBBHQ', image, symbol_offset + i * 16)
            need(name_offset < string_size, 'Invalid Mach-O symbol name index')
            end = image.index(0, string_offset + name_offset, string_offset + string_size)
            name = image[string_offset + name_offset:end]
            if name == b'_RTR_HEADER':
                need(kind_flags & 0xf == 0xf and section > 0, 'RTR_HEADER is not an exported defined section symbol')
                location = next(fileoff + value - vmaddr for vmaddr, vmsize, fileoff, filesize in segments
                                if vmaddr <= value and value + 16 <= vmaddr + filesize)
                signature, major, minor, flags, section_count = struct.unpack_from('<IHHII', image, location)
                need(signature == 0x00525452, 'Exported native RTR_HEADER signature differs')
                rtr_header = {'major': major, 'minor': minor, 'flags': flags, 'sectionCount': section_count,
                              'symbolValue': value, 'imageOffset': location}
    return {'sha256': digest(image), 'kind': kind, 'buildVersion': versions[0],
            'dependencies': dependencies, 'rpaths': rpaths, 'codeSignatures': signatures, 'rtrHeader': rtr_header}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['app', 'inputs', 'builder-results', 'framework-inputs', 'framework-layout', 'corelib-abi', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--remote-app', required=True)
    args = parser.parse_args()
    need(not args.output.exists(), 'Fresh independent review output required')
    args.output.mkdir(parents=True)
    result = {'schema': 'runeclr.ios-device.application-independent-review.v1', 'success': False,
              'targetExecution': False, 'signingOperation': False, 'appDirectory': args.remote_app,
              'actualLocalApp': str(args.app.resolve()), 'builderResultsSha256': sha(args.builder_results),
              'reviewerSha256': sha(__file__)}
    try:
        build = args.builder_results.parent
        receipt, request = json.loads(args.builder_results.read_text()), json.loads((build / 'request.json').read_text())
        need(receipt['success'] and receipt['applicationBuilt'] and receipt['appDirectory'] == args.remote_app
             and receipt['sourceCommit'] == '3126bbc9a8851a09ac6435b18a12882bad48f3ee'
             and receipt['sourceTree'] == '710936ae1729a5689ab0e0896f3cf722ddd3d31c'
             and receipt['runtimeCriticalUnchanged'] and receipt['frameworkLayoutUnchanged'], 'Actual successful matching build receipt required')
        need(sha(build / 'driver.py') == request['driverSha256'] == 'c86af795e75cc810ac949a3ff31269465cd7f34665f798f5c1c168a866c5c15d',
             'Frozen reviewed builder source differs')
        commands = {}
        for label in ['bridge', 'crossgen', 'composite-link', 'wrapper']:
            stage = json.loads((build / (label + '.result.json')).read_text())
            actual = json.loads((build / (label + '.request.json')).read_text())
            need(stage['exitCode'] == 0 and not stage['timedOut'] and actual['argv'] == request['commands'][label],
                 'Actual stage differs from successful reviewed command: ' + label)
            need(all(sha(build / (label + '.' + stream)) == stage[stream + 'Sha256'] for stream in ['stdout', 'stderr']),
                 'Actual stage stream bytes changed')
            commands[label] = {'argv': actual['argv'], 'startedUtc': actual['startedUtc'], 'endedUtc': stage['endedUtc']}
        for name, expected in request['generatedSourceHashes'].items():
            need(sha(build / name) == expected, 'Actual generated source differs')
        result.update(actualCommands=commands, builderEndedUtc=receipt['endedUtc'],
                      builderRequestSha256=sha(build / 'request.json'),
                      generatedSourceHashes=request['generatedSourceHashes'])
        inventory = {p.relative_to(args.app).as_posix(): sha(p) for p in sorted(args.app.rglob('*')) if p.is_file()}
        need(inventory and not any(p.is_symlink() for p in args.app.rglob('*')), 'Empty or symlinked bundle')
        result['appInventory'] = inventory
        need(inventory == json.loads((build / 'bundle-inventory.json').read_text()) and
             sha(build / 'bundle-inventory.json') == receipt['bundleInventorySha256'], 'Whole actual bundle inventory binding differs')
        for name in inventory:
            need(not any(t in name.lower() for t in ['payload', 'private.dll', 'crossgen', 'ilcompiler', 'roslyn',
                                                    'microsoft.codeanalysis', 'csc.dll', 'budget-plugin',
                                                    'embedded.mobileprovision', '_codesignature']),
                 'Author/compiler/signing artifact present: ' + name)
        plist = plistlib.loads((args.app / 'Info.plist').read_bytes())
        need(plist['CFBundleIdentifier'] == 'org.runeclr.deviceprobe' and plist['CFBundleSupportedPlatforms'] == ['iPhoneOS']
             and plist['MinimumOSVersion'] == '15.3' and plist['UIDeviceFamily'] == [1, 2], 'Device Info.plist differs')
        binaries = {}
        executable = plist['CFBundleExecutable']
        for name in [executable] + sorted(n for n in inventory if n.endswith('.dylib')):
            row = native(args.app / name)
            need(row['kind'] == (2 if name == executable else 6), 'Mach-O executable/dylib role differs')
            if name in [executable, 'framework.dylib']:
                need(row['buildVersion']['minimum'] == 983808, 'Executable/composite minimum must be15.3')
            if name == 'framework.dylib':
                need(row['rtrHeader'] is not None, 'Native framework composite has no exported RTR_HEADER')
            need(not row['codeSignatures'], 'Actual Mach-O has LC_CODE_SIGNATURE: ' + name)
            for dependency in row['dependencies']:
                if dependency.startswith(('/usr/lib/', '/System/Library/')):
                    continue
                need(dependency.startswith(('@rpath/', '@loader_path/', '@executable_path/')), 'Unexpected absolute native dependency')
                need(Path(dependency).name in inventory, 'Native dependency absent: ' + dependency)
            binaries[name] = row
        result.update(nativeBinaries=binaries, infoPlist=plist)
        names = ['RuneCLR.Abstractions.dll', 'RuneCLR.Packages.dll', 'RuneCLR.Runtime.dll',
                 'MobileHostBudgetProbe.dll', 'SessionBridge.dll']
        comparisons = {}
        for name in names:
            raw, component = managed(args.inputs / name), managed(args.app / name)
            if name in TRUSTED:
                need(raw['sha256'] == TRUSTED[name], 'Frozen production trusted IL changed: ' + name)
            need(raw['managedNativeRva'] == 0 and component['managedNativeRva'] != 0, 'Expected raw IL and actual R2R component')
            need(component['readyToRun']['flags'] & 0x120 == 0x120 and component['readyToRun']['ownerComposite'] == 'framework.dylib',
                 'Trusted R2R component is not bound to bundled platform-native composite')
            for key in ['identity', 'mvid', 'metadataRootHeaderSha256', 'canonicalStreams', 'tableCounts', 'methods', 'initializedFields']:
                need(raw[key] == component[key], 'Raw/R2R metadata or IL changed: ' + name + ' ' + key)
            comparisons[name] = {'raw': raw, 'component': component}
        core_raw = managed(args.framework_inputs / 'System.Private.CoreLib.dll')
        core_component = managed(args.app / 'System.Private.CoreLib.dll')
        need(core_raw['sha256'] == '9ce8a9f4028c66521b6211f7ca58df060b980208d449dfddbec0c1fd4451c0b0', 'Accepted device CoreLib raw identity differs')
        for key in ['identity', 'mvid', 'metadataRootHeaderSha256', 'canonicalStreams', 'tableCounts', 'methods', 'initializedFields']:
            need(core_raw[key] == core_component[key], 'App CoreLib metadata/IL differs: ' + key)
        need(sha(args.corelib_abi) == '4756b2d2b6ac9be163727fa2917b4eeb8a17346700433ca1e83d2a7557643243',
             'Accepted actual CoreLib ABI baseline changed')
        baseline_rows = json.loads(args.corelib_abi.read_text())
        baseline = next(row for row in baseline_rows if row['sha256'] == core_raw['sha256'])
        need(len(baseline['methods']) == 52, 'Expected accepted52 private ABI methods')
        actual_methods = {m['token']: m for m in core_component['methods']}
        abi = []
        for expected in baseline['methods']:
            actual = actual_methods[int(expected['token'], 16)]
            need(actual['name'] == expected['name'] and actual['signatureHex'].upper() == expected['signatureHex'],
                 'Private ABI method token/name/signature changed')
            abi.append(dict(expected, actualBody=actual['body'], actualAttributes=actual['attributes']))
        expected_framework = {p.name: sha(p) for p in args.framework_inputs.glob('*.dll')}
        need({name for name in inventory if name.endswith('.dll')} == set(expected_framework) | set(names),
             'Actual managed bundle inventory contains unexpected or missing assemblies')
        framework_comparisons = {}
        for name, value in expected_framework.items():
            raw, component = managed(args.framework_inputs / name), managed(args.app / name)
            need(raw['managedNativeRva'] == 0 and component['managedNativeRva'] != 0, 'Framework IL/R2R role differs')
            need(component['readyToRun']['flags'] & 0x120 == 0x120 and component['readyToRun']['ownerComposite'] == 'framework.dylib',
                 'Framework R2R component owner or platform-native flag differs')
            for key in ['identity', 'mvid', 'metadataRootHeaderSha256', 'canonicalStreams', 'tableCounts', 'methods', 'initializedFields']:
                need(raw[key] == component[key], 'Framework metadata/IL changed: ' + name + ' ' + key)
            framework_comparisons[name] = {'rawSha256': raw['sha256'], 'componentSha256': component['sha256'],
                'mvid': raw['mvid'], 'methodCount': len(raw['methods']),
                'allMetadataAndMethodBodiesEqual': True}
        for p in args.framework_layout.glob('*.dylib'):
            if p.name == 'framework.dylib':
                continue
            need(inventory.get(p.name) == sha(p), 'Bundled framework/native device product changed: ' + p.name)
        need(sha(args.app / 'Microsoft.NETCore.App.deps.json') == sha(args.framework_layout / 'Microsoft.NETCore.App.deps.json'),
             'Bundled device deps changed')
        result.update(success=True, managedComparisons=comparisons, corelibPrivateMethods=abi,
                      corelibRawIdentity=core_raw['sha256'], corelibComponentSha256=core_component['sha256'],
                      frameworkComparisons=framework_comparisons, expectedFrameworkComponents=len(expected_framework),
                      actualAppFiles=len(inventory))
    except Exception as error:
        result['error'] = str(error)
    (args.output / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ['managedComparisons', 'appInventory', 'nativeBinaries',
                                                                'corelibPrivateMethods', 'frameworkComparisons', 'actualCommands']}))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
