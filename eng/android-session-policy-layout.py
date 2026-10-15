#!/usr/bin/env python3
"""Assemble a private Android layout from actual matching build/assessment receipts.

No builds, target execution or remote operations. Failed fresh outputs are retained.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import traceback

BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
COMMIT = '1724cdec553a7aff7a373a271a4be612651c7625'
TREE = '71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2'
ALC = 'System.Runtime.Loader.AssemblyLoadContext'
API = {'RuneCLR_CreateInterpreterRequired', 'RuneCLR_GetExecutionPolicyVersion', 'RuneCLR_GetExecutionPolicy'}
BRIDGES = API | {'RuneCLR_GetExecutionPolicyVersionNative', 'RuneCLR_GetExecutionPolicyNative'}
IMPORTS = {'AssemblyNative_InitializeInterpreterRequiredLoadContext',
           'AssemblyNative_RuneCLRGetExecutionPolicyVersion', 'AssemblyNative_RuneCLRGetExecutionPolicy'}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def identity(row):
    require(row.get('base') == BASE and row.get('commit') == COMMIT and row.get('tree') == TREE,
            'Mismatched combined source identity')


def elf(path):
    """Read the actual load segments/dynamic table, including stripped images."""
    data = Path(path).read_bytes()
    require(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01', 'Not ELF64 little-endian: ' + str(path))
    require(struct.unpack_from('<HH', data, 16) == (3, 62), 'Not x86_64 shared ELF: ' + str(path))
    offset = struct.unpack_from('<Q', data, 32)[0]
    width, count = struct.unpack_from('<HH', data, 54)
    require(width >= 56 and offset + width * count <= len(data), 'Malformed ELF program headers')
    headers = [struct.unpack_from('<IIQQQQQQ', data, offset + width * i) for i in range(count)]
    dynamic = [h for h in headers if h[0] == 2]
    require(len(dynamic) == 1, 'Missing/ambiguous ELF PT_DYNAMIC: ' + str(path))
    header = dynamic[0]
    require(header[5] % 16 == 0 and header[2] + header[5] <= len(data), 'Truncated ELF dynamic segment')
    rows = []
    terminated = False
    for position in range(header[2], header[2] + header[5], 16):
        tag, value = struct.unpack_from('<qQ', data, position)
        if tag == 0:
            terminated = True
            break
        rows.append((tag, value))
    require(terminated, 'ELF dynamic table has no DT_NULL')
    strings = [v for t, v in rows if t == 5]
    sizes = [v for t, v in rows if t == 10]
    require(len(strings) == len(sizes) == 1, 'Missing/ambiguous ELF dynamic strings')
    owners = [h for h in headers if h[0] == 1 and h[3] <= strings[0] and strings[0] + sizes[0] <= h[3] + h[5]]
    require(len(owners) == 1, 'ELF dynamic strings not backed by one file segment')
    start = owners[0][2] + strings[0] - owners[0][3]
    require(start + sizes[0] <= len(data), 'Truncated ELF dynamic strings')
    heap = data[start:start + sizes[0]]
    def name(value):
        require(value < len(heap) and heap.find(b'\0', value) >= 0, 'Invalid ELF dynamic string offset')
        answer = heap[value:heap.find(b'\0', value)].decode('ascii')
        require(answer and Path(answer).name == answer, 'Non-basename ELF dependency')
        return answer
    needed = [name(v) for t, v in rows if t == 1]
    sonames = [name(v) for t, v in rows if t == 14]
    require(len(sonames) <= 1, 'Multiple ELF SONAME records')
    return {'path': str(path), 'sha256': sha(path), 'abi': 'x86_64', 'needed': needed,
            'soname': sonames[0] if sonames else None}


def read_build_ids(path):
    """Read GNU note IDs from real ELF section bytes, including separate debug images."""
    data = Path(path).read_bytes()
    require(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01'
            and struct.unpack_from('<HH', data, 16) == (3, 62), 'Not shared ELF64 x86_64 symbol input')
    offset = struct.unpack_from('<Q', data, 40)[0]
    width, count, names_index = struct.unpack_from('<HHH', data, 58)
    require(width >= 64 and count > names_index and count > 0
            and offset+width*count <= len(data), 'Missing/truncated ELF symbol section table')
    rows = [struct.unpack_from('<IIQQQQIIQQ', data, offset+i*width) for i in range(count)]
    strings_row = rows[names_index]
    require(strings_row[4]+strings_row[5] <= len(data), 'Truncated ELF section name strings')
    strings = data[strings_row[4]:strings_row[4]+strings_row[5]]
    ids = []
    for row in rows:
        require(row[0] < len(strings) and strings.find(b'\0', row[0]) >= 0, 'Invalid ELF section name offset')
        name = strings[row[0]:strings.find(b'\0', row[0])]
        if name != b'.note.gnu.build-id':
            continue
        cursor, end = row[4], row[4]+row[5]
        require(row[1] == 7 and end <= len(data), 'Invalid/truncated GNU build-id note section')
        while cursor < end:
            require(cursor+12 <= end, 'Truncated ELF note header')
            owner_size, value_size, kind = struct.unpack_from('<III', data, cursor)
            cursor += 12
            require(cursor+((owner_size+3)&~3)+((value_size+3)&~3) <= end, 'Truncated ELF note value')
            owner = data[cursor:cursor+owner_size].rstrip(b'\0')
            cursor += (owner_size+3)&~3
            value = data[cursor:cursor+value_size]
            cursor += (value_size+3)&~3
            if owner == b'GNU' and kind == 3:
                require(value, 'Empty GNU build-id')
                ids.append(value.hex())
    require(len(ids) == 1, 'Expected exactly one actual GNU build-id')
    return ids


class PeTypes:
    """Resolve actual TypeDef/TypeRef names referenced by fixed bridge signatures."""
    def __init__(self, path):
        data = Path(path).read_bytes()
        require(data[:2] == b'MZ', 'CoreLib is not PE')
        pe = struct.unpack_from('<I', data, 60)[0]
        require(data[pe:pe+4] == b'PE\0\0', 'Invalid PE signature')
        count, optional_size = struct.unpack_from('<H', data, pe+6)[0], struct.unpack_from('<H', data, pe+20)[0]
        opt = pe + 24
        magic = struct.unpack_from('<H', data, opt)[0]
        require(magic in (0x10b, 0x20b), 'Invalid PE optional header')
        directory = opt + (112 if magic == 0x20b else 96)
        sections = [struct.unpack_from('<IIII', data, opt+optional_size+40*i+8) for i in range(count)]
        def rva(value):
            matches = [raw + value - start for size, start, rawsize, raw in sections if start <= value < start + rawsize]
            require(len(matches) == 1, 'PE RVA lacks one raw section owner')
            return matches[0]
        clr = rva(struct.unpack_from('<I', data, directory+14*8)[0])
        require(struct.unpack_from('<II', data, clr+64) == (0, 0), 'Expected IL CoreLib; managed-native directory present')
        meta = rva(struct.unpack_from('<I', data, clr+8)[0])
        require(data[meta:meta+4] == b'BSJB', 'Invalid CLR metadata root')
        length = struct.unpack_from('<I', data, meta+12)[0]
        cursor = meta+16+((length+3)&~3)
        streams = struct.unpack_from('<H', data, cursor+2)[0]
        cursor += 4
        heaps = {}
        for _ in range(streams):
            start, size = struct.unpack_from('<II', data, cursor)
            cursor += 8
            end = data.index(b'\0', cursor)
            name = data[cursor:end].decode('ascii')
            cursor = (end+4)&~3
            heaps[name] = data[meta+start:meta+start+size]
        strings = heaps['#Strings']
        table = heaps.get('#~', heaps.get('#-'))
        require(table is not None, 'Metadata tables absent')
        bits = table[6]
        valid = struct.unpack_from('<Q', table, 8)[0]
        rows = {}
        cursor = 24
        for index in range(64):
            if valid & (1 << index):
                rows[index] = struct.unpack_from('<I', table, cursor)[0]
                cursor += 4
        if bits & 0x40:
            cursor += 4
        s = 4 if bits & 1 else 2
        g = 4 if bits & 2 else 2
        def coded(indices, width):
            return 4 if max((rows.get(i, 0) for i in indices), default=0) >= (1 << (16-width)) else 2
        def integer(position, width):
            return int.from_bytes(table[position:position+width], 'little')
        def text(value):
            return strings[value:strings.index(b'\0', value)].decode('utf-8')
        self.names = {}
        cursor += rows.get(0, 0) * (2+s+3*g)
        scope = coded([0, 26, 35, 1], 2)
        for rid in range(1, rows.get(1, 0)+1):
            name = text(integer(cursor+scope, s)); ns = text(integer(cursor+scope+s, s))
            self.names[(1, rid)] = ns + '.' + name if ns else name
            cursor += scope+2*s
        typedef_width = 4+2*s+coded([2, 1, 27], 2)+(4 if rows.get(4, 0)>=65536 else 2)+(4 if rows.get(6, 0)>=65536 else 2)
        for rid in range(1, rows.get(2, 0)+1):
            name = text(integer(cursor+4, s)); ns = text(integer(cursor+4+s, s))
            self.names[(0, rid)] = ns + '.' + name if ns else name
            cursor += typedef_width

    def signature(self, signature_hex):
        data = bytes.fromhex(signature_hex)
        index = 0
        def compressed():
            nonlocal index
            value = data[index]; index += 1
            if value & 0x80 == 0:
                return value
            if value & 0xc0 == 0x80:
                value = ((value & 0x3f) << 8) | data[index]; index += 1
                return value
            require(value & 0xe0 == 0xc0, 'Invalid signature compressed integer')
            value = ((value & 0x1f) << 24) | int.from_bytes(data[index:index+3], 'big'); index += 3
            return value
        def type_name():
            nonlocal index
            kind = data[index]; index += 1
            if kind in (1, 8, 14, 24):
                return {1:'System.Void',8:'System.Int32',14:'System.String',24:'System.IntPtr'}[kind]
            if kind in (0x11, 0x12):
                value = compressed()
                require((value & 3, value >> 2) in self.names, 'Unsupported/invalid bridge signature type')
                return self.names[(value & 3, value >> 2)]
            if kind == 0x15:
                owner = type_name()
                return owner + '[' + ','.join(type_name() for _ in range(compressed())) + ']'
            raise ValueError('Unexpected fixed bridge signature element: '+hex(kind))
        flags = data[index]; index += 1
        count = compressed()
        returns = type_name()
        parameters = [type_name() for _ in range(count)]
        require(index == len(data), 'Trailing fixed bridge signature bytes')
        return {'flags': flags, 'returns': returns, 'parameters': parameters}


def frozen_metadata(evidence, assessment, native, source, reviewed, configuration):
    """Bind immutable PE copies to the prior actual metadata assessment."""
    result, request = (read(evidence/name) for name in ('results.json', 'request.json'))
    receipt = read(assessment/'metadata-assessment.json')
    for row in (result, request):
        identity(row)
        require(row.get('target') == 'android.x64' and row.get('configuration') == configuration,
                'Frozen CoreLib evidence target/configuration mismatch')
    require(result.get('success') is True and result.get('buildExit') == 0
            and (evidence/'build.exit').read_text().strip() == '0'
            and result.get('coreCriticalUnchanged') is True and result.get('sourceTrackedClean') is True
            and result.get('descriptorMatchesOriginal') is True, 'Frozen CoreLib evidence failed')
    require(result.get('buildInvoked') == request.get('buildInvoked')
            and isinstance(request.get('buildInvoked'), bool)
            and (request['buildInvoked'] or request.get('command') is None), 'Frozen build invocation receipt mismatch')
    require(request.get('sourceReceiptSha256') == sha(native/'source.json')
            and request.get('sourceHashes') == source['sourceHashes']
            and request.get('criticalBefore') == result.get('criticalAfter') == reviewed['criticalHashes'],
            'Frozen CoreLib evidence source/critical product binding differs')
    require(request.get('metadataBeforeSha256') == result.get('metadataAssessmentSha256')
            == sha(assessment/'metadata-assessment.json')
            and Path(result['metadataAssessment']).resolve() == (assessment/'metadata-assessment.json').resolve(),
            'Frozen CoreLib evidence binds a different metadata assessment')
    rows = result.get('frozenStages', [])
    stages = receipt['stages']
    require(len(rows) == len(stages) == 4, 'Exactly four original frozen PE stages required')
    require(len({row['originalPath'] for row in rows}) == 4
            and len({str(Path(row['path']).resolve()) for row in rows}) == 4, 'Frozen stage paths alias')
    mapping = {}
    for index, (row, stage) in enumerate(zip(rows, stages)):
        path = Path(row['path']).resolve()
        require(path.parent == evidence.resolve()/'managed-pe'
                and path.name == 'stage'+str(index)+'-'+Path(stage['path']).name and path.is_file()
                and row['originalPath'] == stage['path'] and row.get('matchesOriginal') is True
                and row.get('sha256') == row.get('originalAssessmentSha256') == stage['sha256'] == sha(path),
                'Frozen PE does not match its exact original assessed stage')
        mapping[stage['path']] = path
    descriptor = Path(result['descriptorPath']).resolve()
    require(descriptor.is_relative_to(evidence.resolve())
            and descriptor.name == 'ILLink.Descriptors.xml'
            and sha(descriptor) == result['descriptorSha256'] == receipt['descriptorSha256'],
            'Frozen descriptor is not the original assessed descriptor')
    return mapping, descriptor, {'directory': str(evidence), 'resultsSha256': sha(evidence/'results.json'),
                                'requestSha256': sha(evidence/'request.json'),
                                'metadataBeforeSha256': request['metadataBeforeSha256'],
                                'buildInvoked': request['buildInvoked'], 'frozenStages': rows,
                                'descriptorPath': str(descriptor), 'descriptorSha256': sha(descriptor)}


def metadata(assessment, corelib, frozen=None):
    receipt = read(assessment/'metadata-assessment.json')
    stages = receipt['stages']
    require(len(stages) == 4 and receipt.get('inspectedAssembliesLoaded') is False, 'Expected host-only PE assessment')
    require(read(assessment/'metadata-inspector.stdout.json')==stages, 'Preserved actual metadata inspector output differs')
    helper=Path(receipt['hostOnlyCommand'][4])
    require(sha(helper)==receipt['metadataInspectorSha256'], 'Actual metadata helper identity differs')
    mapping, descriptor, snapshot = frozen if frozen else ({}, Path(stages[0]['path']).parent.parent/'ILLink.Descriptors.xml', None)
    require(sha(descriptor)==receipt['descriptorSha256'], 'Actual trim descriptor changed')
    require(all('name="'+name+'"' in descriptor.read_text() for name in API), 'Fixed reflection roots absent from actual descriptor')
    evidence = []
    expected = {'RuneCLR_GetExecutionPolicyVersion': (0, 'System.Int32', []),
                'RuneCLR_GetExecutionPolicy': (0x20, 'System.Int32', [])}
    # The Func arity is metadata's literal grave-accent plus 3, not CLR generic display notation.
    expected['RuneCLR_CreateInterpreterRequired'] = (0, ALC, ['System.String', 'System.Func'+chr(96)+'3['+ALC+',System.Reflection.AssemblyName,System.Reflection.Assembly]'])
    for row in stages[:3]:
        path = mapping.get(row['path'], Path(row['path']))
        require(sha(path) == row['sha256'].lower() and row['assembly'] == 'System.Private.CoreLib'
                and row['managedNativeRva'] == 0, 'CoreLib stage metadata/file mismatch')
        methods = [m for m in row['methods'] if m['owner'] == ALC and m['name'].startswith('RuneCLR_')]
        require(len(methods) == 5 and {m['name'] for m in methods} == BRIDGES and all('Private' in m['attributes'] for m in methods), 'Missing/private bridge mismatch')
        names = PeTypes(path)
        signatures = {}
        for method in methods:
            if method['name'] not in API:
                continue
            signature = names.signature(method['signatureHex'])
            require((signature['flags'], signature['returns'], signature['parameters']) == expected[method['name']], 'Fixed reflection API signature changed: '+method['name'])
            require(('Static' in method['attributes']) == (method['name'] != 'RuneCLR_GetExecutionPolicy'), 'Fixed API static/instance attributes changed')
            signatures[method['name']] = signature
        imports = [m for m in row['methods'] if m['nativeEntry'] in IMPORTS]
        require(len(imports) == 3 and {m['nativeEntry'] for m in imports} == IMPORTS
                and all('PinvokeImpl' in m['attributes'] and 'Static' in m['attributes'] for m in imports), 'Real QCall imports missing')
        nested = {m['name'] for m in row['methods'] if m['owner'] == ALC+'+RuneCLRInterpreterLoadContext'}
        require({'.ctor','Load','LoadUnmanagedDll'} <= nested, 'Private factory context methods missing')
        evidence.append({'path':str(path),'originalPath':row['path'],'sha256':row['sha256'],'fixedSignatures':signatures,'imports':imports})
    require(stages[1]['sha256'] == stages[2]['sha256'] == sha(corelib), 'PostTrim/ProductIL/layout CoreLib mismatch')
    mirror = stages[3]
    require(sha(mapping.get(mirror['path'], mirror['path'])) == mirror['sha256'] and any(f['name']=='CORJIT_FLAG_INTERPRET_REQUIRED' and f['value']==33 for f in mirror['fields']), 'Actual compiler bit33 mirror mismatch')
    return {'corelibSha256':sha(corelib),'fixedBridgeSignaturesVerified':True,'privateApiCount':3,'privateWrapperCount':5,
            'actualPInvokeImportCount':3,'stages':evidence,'sourceMetadataReceiptSha256':sha(assessment/'metadata-assessment.json'),
            'metadataInspectorSha256':receipt['metadataInspectorSha256'],
            'sourceMetadataInspectorStdoutSha256':sha(assessment/'metadata-inspector.stdout.json'),
            'inspectedAssembliesLoaded':False,
            'frozenEvidence':snapshot}


def assemble(args):
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    configuration = args.configuration
    result = {'success':False,'executionVerified':False,'nativeConfiguration':configuration,
              'frameworkConfiguration':'Release','scope':'Private matching Android layout; no APK/device execution'}
    try:
        build, assessment, framework, toolchain = (p.resolve() for p in (args.build,args.assessment,args.framework,args.toolchain))
        native, request, source = (read(build/n) for n in ('results.json','request.json','source.json'))
        reviewed = read(assessment/'results.json'); fw = read(framework/'results.json'); tools = read(toolchain/'results.json')
        for row in (native,request,source,fw): identity(row)
        require(native['success'] and native['buildExit']==0 and (build/'build.exit').read_text().strip()=='0'
                and native['sourceTrackedClean'] and source['trackedClean'] and native['target']=='android.x64'
                and native['configuration']==configuration and native['frameworkConfiguration']=='Release', 'Native build/source not successful/clean/matched')
        require(request['configuration']==configuration and request['frameworkConfiguration']=='Release'
                and request['target']=='android.x64' and source['configuration']=='android.x64.'+configuration,
                'Native request/source configuration mismatch')
        require(reviewed['success'] and reviewed['candidateCommit']==COMMIT and reviewed['sourceFiles']==27 and reviewed['compileOwners']==9
                and reviewed['metadataPassed'] and reviewed['nativeGuidPassed'] and reviewed['nativeConfigurationPassed']
                and reviewed.get('configuration','Checked')==configuration, 'Actual build assessment incomplete')
        require(fw['success'] and fw['target']=='android.x64' and fw['configuration']==configuration
                and fw['frameworkConfiguration']=='Release' and fw['sourceTrackedClean'] and fw['coreCriticalUnchanged']
                and fw['frameworkInputsAvailable'] and fw['depsGenerated'], 'Matching Android framework build incomplete')
        require(all((framework/(stage+'.exit')).read_text().strip()=='0' for stage in ('libraries','deps')),
                'Actual framework/deps process exits were not zero')
        android_tools_path=Path(fw['androidToolsReceipt'])
        require(sha(android_tools_path)==fw['androidToolsReceiptSha256'] and read(android_tools_path)['success'], 'Framework SDK/JDK receipt changed/failed')
        require(tools['success'] and tools['package']=='ndk;27.2.12479018' and tools['clangExecutableVerified'], 'Actual Darwin NDK receipt missing')
        require(request['toolchainReceiptSha256']==sha(toolchain/'results.json'), 'Native build uses a different NDK receipt')
        runtime = Path(request['source'])
        require(subprocess.check_output(['git','-C',str(runtime),'rev-parse','HEAD'],text=True).strip()==COMMIT
                and subprocess.check_output(['git','-C',str(runtime),'rev-parse','HEAD^{tree}'],text=True).strip()==TREE
                and not subprocess.check_output(['git','-C',str(runtime),'status','--porcelain','--untracked-files=no'],text=True).strip(),
                'Current source commit/tree/tracked state differs')
        require(len(source['sourceHashes'])==27 and all(sha(runtime/name)==value for name,value in source['sourceHashes'].items()), 'Source27 files differ from reviewed receipt')
        ndk = Path(tools['ndk']); prebuilt = ndk/'toolchains/llvm/prebuilt/darwin-x86_64'
        require(sha(ndk/'source.properties')==tools['sourcePropertiesSha256'] and sha(ndk/'build/cmake/android.toolchain.cmake')==tools['toolchainSha256'], 'NDK installation differs from receipt')
        compile_receipt = read(assessment/'compile-assessment.json')
        require(compile_receipt.get('configuration','Checked')==configuration, 'Compile assessment configuration mismatch')
        roles = compile_receipt['roles']
        require(len(roles)==9 and all(sha(row['database'])==row['databaseSha256'] and sha(row['object'])==row['objectSha256'] for row in roles.values()), 'Actual compile owners changed')
        wanted = ('vm-policy-router','interpreter-compiler','vm-native-factory')
        require(all(all(roles[name]['defines'].get(feature)=='1' for feature in ('FEATURE_INTERPRETER','FEATURE_DYNAMIC_CODE_COMPILED')) for name in wanted), 'Required actual feature compile evidence absent')
        cache=runtime/('artifacts/obj/coreclr/android.x64.'+configuration+'/CMakeCache.txt')
        require(sha(cache)==compile_receipt['nativeCacheSha256'], 'Actual native CMake cache changed')
        require(re.search(r'^CMAKE_BUILD_TYPE:[^=]+='+re.escape(configuration)+r'\s*$',cache.read_text(),re.M|re.I),
                'Actual native CMake build configuration differs')
        host_cache=cache.parent/'arm64/CMakeCache.txt'
        require(sha(host_cache)==compile_receipt['hostCacheSha256']
                and re.search(r'^CMAKE_BUILD_TYPE:[^=]+='+re.escape(configuration)+r'\s*$',host_cache.read_text(),re.M|re.I),
                'Actual host compiler CMake configuration differs')
        for key,value in {'FEATURE_INTERPRETER':'1','FEATURE_DYNAMIC_CODE_COMPILED':'1','ANDROID_ABI':'x86_64'}.items():
            require(re.search('^'+key+r':[^=]+='+re.escape(value)+r'\s*$',cache.read_text(),re.M), 'Actual CMake feature/ABI differs: '+key)
        for directory in ('native','managed','headers','receipts'): (out/directory).mkdir()
        files = []
        def copy(path, relative, role, ndk_component=False):
            path = Path(path)
            target = out/relative
            require(not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'Escaping layout destination: '+relative)
            if target.exists():
                require(sha(target)==sha(path), 'Different inputs collide at layout destination: '+relative)
                next(row for row in files if row['path']==relative).setdefault('additionalSourcePaths',[]).append(str(path))
                return
            target.parent.mkdir(parents=True,exist_ok=True)
            before = sha(path); shutil.copy2(path,target)
            require(sha(target)==before==sha(path), 'Input changed during copy: '+str(path))
            row = {'path':relative,'sha256':before,'sourcePath':str(path),'role':role,'sourceCommit':None if ndk_component else COMMIT}
            if ndk_component: row['toolchainReceiptSha256']=sha(toolchain/'results.json')
            files.append(row)
        native_roles = {'native':('libcoreclr.so','runtime'),'interpreter':('libclrinterpreter.so','interpreter'),'targetJit':('libclrjit.so','jit')}
        for key,(name,role) in native_roles.items():
            require(sha(native[key])==reviewed['criticalHashes'][key], 'Reviewed native input changed: '+key)
            copy(native[key],'native/'+name,role)
        require(sha(native['corelib'])==native['corelibSha256']==reviewed['criticalHashes']['corelib'], 'Matching '+configuration+' CoreLib changed')
        copy(native['corelib'],'managed/System.Private.CoreLib.dll','corelib')
        inventory = read(framework/'input-inventory.json')
        identity(inventory)
        require(inventory['target']=='android.x64' and inventory['configuration']==configuration and inventory['frameworkConfiguration']=='Release', 'Framework input inventory configuration mismatch')
        require(sha(framework/'input-inventory.json')==fw['inputInventorySha256'], 'Framework inventory receipt changed')
        require(set(inventory['groups'])=={'framework','native','headers','deps'}, 'Expected actual framework/native/header/deps groups')
        omitted=[]; evidence_files=[]
        if configuration == 'Release':
            artifact_path=build/'artifacts.json'
            artifact_rows=read(artifact_path)
            for key in ('native','interpreter'):
                image=Path(native[key]).resolve()
                debug=Path(str(image)+'.dbg')
                require(debug.is_file(), 'Release method-entry preparation requires symbol image: '+str(debug))
                for path in (image,debug):
                    matches=[row for row in artifact_rows if Path(row['path']).resolve()==path]
                    require(len(matches)==1 and matches[0]['sha256']==sha(path)
                            and matches[0]['size']==path.stat().st_size, 'Symbol/native image differs from original build artifact inventory')
                ids=read_build_ids(image)
                require(read_build_ids(debug)==ids, 'Release symbol/native GNU build-id mismatch')
                target=out/'receipts/symbols'/debug.name
                target.parent.mkdir(parents=True,exist_ok=True)
                require(not target.exists(), 'Duplicate symbol evidence image')
                before=sha(debug);shutil.copy2(debug,target)
                require(sha(debug)==sha(target)==before, 'Symbol evidence changed during copy')
                evidence_files.append({'path':target.relative_to(out).as_posix(),'sha256':before,
                                       'sourcePath':str(debug),'sourceCommit':COMMIT,'role':'native-symbol-evidence',
                                       'matchingNativePath':'native/'+image.name,'matchingNativeSha256':sha(image),
                                       'gnuBuildIds':ids,'gnuBuildIdVerified':True,
                                       'sourceArtifactBinding':{'path':str(artifact_path),'sha256':sha(artifact_path)}})
        for group,rows in inventory['groups'].items():
            for row in rows:
                path=Path(row['path'])
                require(sha(path)==row['sha256'] and path.stat().st_size==row['size'], 'Framework/header inventory changed')
                if group in ('framework','deps'):
                    require(path.suffix in ('.dll','.json'), 'Unexpected framework input format')
                    copy(path,'managed/'+path.name,'framework')
                elif group=='native':
                    if path.suffix=='.dex':
                        header=path.read_bytes()[:8]
                        require(len(header)==8 and header[:4]==b'dex\n' and header[4:7].isdigit()
                                and header[7]==0 and path.stat().st_size>=112, 'Framework Java companion is not actual DEX')
                        copy(path,'java/'+path.name,'android-java')
                        continue
                    if path.suffix=='.jar':
                        relative='receipts/java/'+path.name
                        target=out/relative; target.parent.mkdir(parents=True,exist_ok=True)
                        require(not target.exists(), 'Duplicate Java archive evidence basename')
                        shutil.copy2(path,target)
                        require(sha(target)==row['sha256']==sha(path), 'Java archive evidence changed during copy')
                        evidence_files.append({'path':relative,'sha256':row['sha256'],'sourcePath':str(path),
                                               'sourceCommit':COMMIT,'role':'android-java-build'})
                        continue
                    if path.suffix=='.a':
                        omitted.append(dict(row,reason='Not a runtime-loaded ELF shared library'))
                        continue
                    require(path.suffix=='.so', 'Unexpected framework OS-native input format')
                    copy(path,'native/'+path.name,'os-native')
                else:
                    # Build-native headers remain in the actual framework inventory.
                    # JNI hosting consumes the fixed source headers copied below.
                    omitted.append(dict(row,reason='Build-native header; fixed source hosting headers copied separately'))
        for relative,destination in [('src/coreclr/hosts/inc/coreclrhost.h','headers/hosts/coreclrhost.h'),
                                     ('src/native/corehost/host_runtime_contract.h','headers/native/corehost/host_runtime_contract.h')]:
            copy(runtime/relative,destination,'header')
        require(sha(fw['depsFile'])==fw['depsSha256']==sha(out/'managed/Microsoft.NETCore.App.deps.json'), 'Actual generated framework deps differs')
        deps=read(out/'managed/Microsoft.NETCore.App.deps.json')
        require('android-x64' in deps.get('runtimeTarget',{}).get('name','') and deps.get('targets') and deps.get('libraries'), 'Invalid actual Android framework deps')
        assets={Path(name).name for target in deps['targets'].values() for library in target.values()
                for category in ('runtime','native','runtimeTargets') for name in library.get(category,{})}
        require({'System.Private.CoreLib.dll','System.Runtime.dll','libcoreclr.so','libclrinterpreter.so','libclrjit.so'} <= assets, 'Actual deps missing critical runtime assets')
        require(all(any(Path(row['path']).name==name for row in files) for name in assets
                    if name.endswith(('.dll','.so'))), 'Generated deps declares managed/native assets absent from actual layout')
        require(fw['metadataAssessmentSha256']==sha(assessment/'metadata-assessment.json')
                and fw['assessmentReceiptSha256']==sha(assessment/'results.json'), 'Framework consumed a different CoreLib/build assessment')
        required = {'managed/Microsoft.NETCore.App.deps.json','managed/System.Runtime.dll','native/libSystem.Native.so',
                    'headers/hosts/coreclrhost.h','headers/native/corehost/host_runtime_contract.h'}
        require(required <= {row['path'] for row in files}, 'Incomplete Android framework/native/header inventory')
        require('java/libSystem.Security.Cryptography.Native.Android.dex' in {row['path'] for row in files}
                and 'receipts/java/libSystem.Security.Cryptography.Native.Android.jar' in {row['path'] for row in evidence_files},
                'Required actual Android crypto DEX/JAR inputs absent')
        frozen = frozen_metadata(args.corelib_evidence.resolve(),assessment,build,source,reviewed,configuration) if args.corelib_evidence else None
        trim = metadata(assessment,Path(native['corelib']),frozen)
        if frozen:
            origins=[('results.json',args.corelib_evidence.resolve()/'results.json'),
                     ('request.json',args.corelib_evidence.resolve()/'request.json'),
                     ('build.exit',args.corelib_evidence.resolve()/'build.exit'),
                     ('ILLink.Descriptors.xml',frozen[1])]
            origins += [('managed-pe/'+path.name,path) for path in frozen[0].values()]
            for name,origin in origins:
                target=out/'receipts/corelib-evidence'/name
                target.parent.mkdir(parents=True,exist_ok=True)
                require(not target.exists(), 'Frozen evidence destination collision')
                before=sha(origin); shutil.copy2(origin,target)
                require(sha(origin)==sha(target)==before, 'Frozen evidence changed during copy')
                evidence_files.append({'path':target.relative_to(out).as_posix(),'sha256':before,
                                       'sourcePath':str(origin),'sourceCommit':COMMIT,'role':'corelib-metadata-evidence'})
        packaged = {Path(row['path']).name:out/row['path'] for row in files if row['path'].startswith('native/')}
        queue = list(packaged.values()); examined = {}; dependencies = []
        sysroot = prebuilt/'sysroot/usr/lib/x86_64-linux-android'
        while queue:
            path = queue.pop(0)
            if str(path) in examined: continue
            image = elf(path); examined[str(path)]=image
            require(image['soname'] in (None,path.name), 'ELF SONAME does not match packaged/resolved basename')
            for name in image['needed']:
                if name in packaged:
                    dependency = packaged[name]; disposition='packaged'
                elif name=='libc++_shared.so':
                    dependency = sysroot/name
                    require(dependency.is_file(), 'Actual NDK libc++_shared dependency unavailable')
                    copy(dependency,'native/'+name,'ndk-native',True)
                    packaged[name]=out/'native'/name; dependency=packaged[name]; disposition='packaged-ndk'
                elif (sysroot/'24'/name).is_file():
                    dependency = sysroot/'24'/name
                    disposition='android-system-api24'
                else: raise ValueError('Unresolved actual ELF DT_NEEDED dependency: '+name+' from '+str(path))
                dependencies.append({'owner':str(path),'needed':name,'resolvedPath':str(dependency),'sha256':sha(dependency),'disposition':disposition})
                queue.append(dependency)
        elf_receipt = {'allDependenciesResolved':True,'abi':'x86_64','api':24,'images':list(examined.values()),'dependencies':dependencies,'toolchainReceiptSha256':sha(toolchain/'results.json'),
                       'systemResolutionScope':'Actual pinned NDK API24 ELF linker stubs; not deployed-device library identities'}
        feature_receipt = {'featureInterpreter':True,'featureDynamicCodeCompiled':True,'compileEvidenceVerified':True,
                           'compileOwners':{name:roles[name] for name in wanted},'sourceCompileAssessmentSha256':sha(assessment/'compile-assessment.json')}
        receipts = []
        values = {'native-build':native,'framework-build':fw,'source':source,'features':feature_receipt,'trim-api':trim,'elf-needed':elf_receipt}
        for kind,value in values.items():
            relative = 'receipts/'+kind+'.json'; write(out/relative,value)
            receipts.append({'kind':kind,'path':relative,'sha256':sha(out/relative)})
        provenance=[]
        for prefix,directory,names in [('native',build,('results.json','request.json','source.json','build.exit')
                                                     + (('artifacts.json',) if configuration=='Release' else ())),
                                      ('assessment',assessment,('results.json','source-assessment.json','compile-assessment.json','native-binary-assessment.json','metadata-assessment.json','metadata-inspector.stdout.json')),
                                      ('framework',framework,('results.json','request.json','input-inventory.json','libraries.exit','libraries.request.json','libraries.results.json',
                                                              'deps.exit','deps.request.json','deps.results.json','deps-evaluated.json','core-critical-after.json')),
                                      ('toolchain',toolchain,('results.json','request.json'))]:
            for name in names:
                origin=directory/name
                destination=out/'receipts'/(prefix+'-'+name)
                before=sha(origin); shutil.copy2(origin,destination)
                require(before==sha(origin)==sha(destination), 'Provenance changed during receipt copy')
                provenance.append({'path':destination.relative_to(out).as_posix(),'sha256':before,'sourcePath':str(origin)})
        destination=out/'receipts/framework-android-tools.json'
        shutil.copy2(android_tools_path,destination)
        require(sha(destination)==fw['androidToolsReceiptSha256']==sha(android_tools_path), 'Framework SDK/JDK provenance changed during copy')
        provenance.append({'path':destination.relative_to(out).as_posix(),'sha256':sha(destination),'sourcePath':str(android_tools_path)})
        result.update(schema='runeclr.android.session-policy.layout.v1',success=True,base=BASE,commit=COMMIT,tree=TREE,
                      sourceTrackedClean=True,target='android.x64',nativeConfiguration=configuration,frameworkConfiguration='Release',
                      features={'interpreter':True,'dynamicCodeCompiled':True},files=files,receipts=receipts,
                      omittedFrameworkInputs=omitted,evidenceFiles=evidence_files+provenance,provenanceFiles=provenance,driverSha256=sha(__file__),sourceBuildReceiptSha256=sha(build/'results.json'),
                      sourceAssessmentReceiptSha256=sha(assessment/'results.json'),sourceFrameworkReceiptSha256=sha(framework/'results.json'))
    except Exception:
        result['error']=traceback.format_exc(); write(out/'results.json',result)
        raise
    write(out/'results.json',result)
    write(out/'layout.json',result)
    require((out/'results.json').read_bytes()==(out/'layout.json').read_bytes(), 'Layout/result receipt bytes differ')
    print('PASS private Android x64 '+configuration+' layout; matching Release framework; actual fixed API signatures and ELF closure; target execution not performed')
    print(str(out/'layout.json'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('build','assessment','framework','toolchain','output'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--configuration', choices=('Checked','Release'), default='Checked')
    parser.add_argument('--corelib-evidence', type=Path, help='Successful immutable CoreLib evidence snapshot directory; original stage hashes remain mandatory')
    assemble(parser.parse_args())


if __name__=='__main__': main()
