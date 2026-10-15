#!/usr/bin/env python3
"""Read-only source, native configuration and PE assessment of the combined build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import traceback
import uuid

BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
COMMIT = '1724cdec553a7aff7a373a271a4be612651c7625'
TREE = '71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2'
GUID = '7c844228-f051-4b9b-9b8f-4e221230806f'
ALC = 'System.Runtime.Loader.AssemblyLoadContext'
BRIDGE = {'RuneCLR_CreateInterpreterRequired', 'RuneCLR_GetExecutionPolicyVersion',
          'RuneCLR_GetExecutionPolicy', 'RuneCLR_GetExecutionPolicyVersionNative',
          'RuneCLR_GetExecutionPolicyNative'}
NATIVE_ENTRIES = {'AssemblyNative_InitializeInterpreterRequiredLoadContext',
                  'AssemblyNative_RuneCLRGetExecutionPolicyVersion',
                  'AssemblyNative_RuneCLRGetExecutionPolicy'}


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + chr(10))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def capture(arguments):
    return subprocess.check_output([str(x) for x in arguments], text=True).strip()


def below(path, root):
    try:
        Path(path).resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def flags(entry):
    tokens = entry.get('arguments') or shlex.split(entry['command'])
    defines = {}
    for token in tokens:
        if token.startswith('-D'):
            name, _, value = token[2:].partition('=')
            defines[name] = value or '1'
    return tokens, defines


def macho(path):
    data = Path(path).read_bytes()
    require(len(data) >= 32 and struct.unpack_from('<I', data)[0] == 0xfeedfacf,
            'Expected a thin 64-bit Mach-O image: ' + str(path))
    cpu, _, kind, count, size = struct.unpack_from('<5I', data, 4)
    require(cpu == 0x100000c, 'Native input is not ARM64: ' + str(path))
    offset = 32
    platforms = []
    for _ in range(count):
        command, length = struct.unpack_from('<II', data, offset)
        require(length >= 8 and offset + length <= 32 + size, 'Malformed Mach-O load command')
        if command == 0x32:
            platform, minimum, sdk = struct.unpack_from('<III', data, offset + 8)
            platforms.append({'platform': platform, 'minimum': minimum, 'sdk': sdk})
        elif command == 0x24:
            platforms.append({'platform': 1, 'legacyMacOSCommand': True})
        offset += length
    return {'cpu': 'arm64', 'fileType': kind, 'platforms': platforms, 'sha256': sha(path)}


def guid_literal(path):
    data = Path(path).read_bytes()
    target = uuid.UUID(GUID).bytes_le
    offsets, offset = [], 0
    while True:
        offset = data.find(target, offset)
        if offset < 0:
            break
        offsets.append(offset)
        offset += 1
    return {'path': str(path), 'sha256': sha(path), 'guid': GUID,
            'byteOrder': 'native little-endian GUID struct', 'literalOffsets': offsets}


def jitinterface_guid(disassembly):
    # AppleClang folds the 16-byte memcmp into two immediate-register compares.
    # Decode the actual ARM64 MOVZ/MOVK bytes, rather than text constants alone.
    registers, comparisons = {}, []
    expected = struct.unpack('<QQ', uuid.UUID(GUID).bytes_le)
    for line in disassembly.splitlines():
        match = re.match(r'\s*([0-9a-fA-F]+):\s*((?:[0-9a-fA-F]{2}\s+){4})\s*(\w+)\s*(.*)', line)
        if not match:
            continue
        instruction = int.from_bytes(bytes.fromhex(match[2]), 'little')
        opcode = instruction & 0xff800000
        register = instruction & 31
        shift = ((instruction >> 21) & 3) * 16
        immediate = (instruction >> 5) & 0xffff
        if opcode == 0xd2800000:
            registers[register] = immediate << shift
        elif opcode == 0xf2800000 and register in registers:
            registers[register] = ((registers[register] & ~(0xffff << shift)) |
                                   (immediate << shift))
        elif match[3] in ('cmp', 'ccmp'):
            regs = re.match(r'x(\d+),\s*x(\d+)', match[4])
            if regs:
                for index in (int(regs[1]), int(regs[2])):
                    if registers.get(index) in expected:
                        comparisons.append({'address': match[1], 'mnemonic': match[3],
                                            'constant': registers[index], 'register': index})
        elif match[3] in ('mov', 'ldr', 'ldp', 'add', 'adrp'):
            operands = re.match(r'x(\d+)(?:,\s*x(\d+))?', match[4])
            if operands:
                registers.pop(int(operands[1]), None)
                if match[3] == 'ldp' and operands[2]:
                    registers.pop(int(operands[2]), None)
    require(set(item['constant'] for item in comparisons) == set(expected),
            'Actual JitCompileMethod GUID compares do not identify the matching interface')
    require('blr' in disassembly and re.search(r'ldr\s+x\d+, \[x\d+, #0x10\]', disassembly),
            'No observed virtual getVersionIdentifier slot before native GUID comparison')
    return {'guid': GUID, 'evidence': 'JitCompileMethod instruction bytes decode two GUID compare constants',
            'comparisons': comparisons, 'halvesLittleEndian': list(expected)}


def assess(args):
    build = args.build.resolve()
    output = (args.output or build.parent / 'build-assessment-20261013').resolve()
    require(not below(output, build / 'runtime'), 'Assessment output must be outside the runtime worktree')
    output.mkdir(exist_ok=False)
    result = {'success': False, 'executionVerified': False, 'candidateCommit': COMMIT,
              'scope': 'Source/build/configuration/PE/native bytes; no simulator launch or method execution'}
    try:
        completed, source, request = [read(build / name) for name in ('results.json', 'source.json', 'request.json')]
        runtime = build / 'runtime'
        product = runtime / 'artifacts/bin/coreclr/iossimulator.arm64.Release'
        require(completed['success'] and completed['buildExit'] == 0 and
                (build / 'build.exit').read_text().strip() == '0', 'Build did not complete successfully')
        for receipt in (completed, source, request):
            require(receipt['base'] == BASE and receipt['commit'] == COMMIT and receipt['tree'] == TREE,
                    'Build/source/request identity disagreement')
        require(capture(['git', '-C', runtime, 'rev-parse', 'HEAD']) == COMMIT and
                capture(['git', '-C', runtime, 'rev-parse', 'HEAD^{tree}']) == TREE and
                not capture(['git', '-C', runtime, 'status', '--porcelain', '--untracked-files=no']),
                'Live committed source/tree/clean state does not match')
        changed = capture(['git', '-C', runtime, 'diff', '--name-only', BASE, COMMIT]).splitlines()
        require(len(changed) == 27 and set(changed) == set(source['sourceHashes']), 'Expected exact 27-file source set')
        for name in changed:
            require(sha(runtime / name) == source['sourceHashes'][name], 'Changed source hash mismatch: ' + name)
        consumers = {
            'src/coreclr/inc/jiteeversionguid.h': [GUID, '0x7c844228'],
            'src/coreclr/inc/corjitflags.h': ['CORJIT_FLAG_INTERPRET_REQUIRED       = 33'],
            'src/coreclr/jit/jitee.h': ['JIT_FLAG_INTERPRET_REQUIRED       = 33',
                'FLAGS_EQUAL(CORJIT_FLAGS::CORJIT_FLAG_INTERPRET_REQUIRED, JIT_FLAG_INTERPRET_REQUIRED)'],
            'src/coreclr/tools/Common/JitInterface/CorInfoTypes.cs': ['CORJIT_FLAG_INTERPRET_REQUIRED       = 33'],
            'src/coreclr/tools/superpmi/superpmi-shared/methodcontext.cpp': ['CORJIT_FLAG_INTERPRET_REQUIRED'],
            'src/coreclr/tools/superpmi/superpmi-shared/spmidumphelper.cpp': ['AddFlag(INTERPRET_REQUIRED)'],
            'src/coreclr/interpreter/eeinterp.cpp': ['memcpy(versionIdentifier, &JITEEVersionIdentifier, sizeof(GUID))'],
            'src/coreclr/tools/aot/jitinterface/jitwrapper.cpp': ['pJit->getVersionIdentifier(&versionId)',
                'memcmp(&versionId, &JITEEVersionIdentifier, sizeof(GUID))']}
        consumer_receipts = {}
        for name, needles in consumers.items():
            text = (runtime / name).read_text()
            require(all(needle in text for needle in needles), 'Source interface consumer mismatch: ' + name)
            consumer_receipts[name] = {'sha256': sha(runtime / name), 'requiredFragments': needles}
        write(output / 'source-interface-consumers.json', consumer_receipts)
        require(request['sdkVersion'] == '11.0.100-rc.1.26420.103' and request['cleanBuildObjects'],
                'Unexpected SDK or reused build objects')
        baseline = build.parent / 'runtime/artifacts/bin/coreclr/iossimulator.arm64.Debug/libcoreclr.dylib'
        require(sha(baseline) == request['baselineNativeBeforeSha256'], 'Original native baseline changed')
        write(output / 'source-assessment.json', {'base': BASE, 'commit': COMMIT, 'tree': TREE,
              'sourceHashes': source['sourceHashes'], 'sourceTrackedClean': True,
              'requestSha256': sha(build / 'request.json'), 'sourceReceiptSha256': sha(build / 'source.json')})

        native_obj = runtime / 'artifacts/obj/coreclr/iossimulator.arm64.Release'
        host_obj = native_obj / 'arm64'
        cache = (native_obj / 'CMakeCache.txt').read_text()
        require(re.search(r'^CMAKE_BUILD_TYPE:[^=]+=RELEASE$', cache, re.M) and
                re.search(r'^CMAKE_OSX_SYSROOT:[^=]+=iphonesimulator$', cache, re.M) and
                re.search(r'^CMAKE_OSX_DEPLOYMENT_TARGET:[^=]+=15\.3$', cache, re.M) and
                re.search(r'^FEATURE_INTERPRETER:[^=]+=1$', cache, re.M), 'Unexpected native CMake configuration')
        entries = []
        for database in (native_obj / 'compile_commands.json', host_obj / 'compile_commands.json'):
            rows = read(database)
            require(rows and all(below(row['file'], runtime) and below(row['directory'], runtime)
                                for row in rows), 'Compile database refers to another source/object tree')
            entries.extend((database, row) for row in rows)
        roles = {
            'vm-cid-worker': ('vm/virtualcallstub.cpp', 'cee_wks_core', native_obj),
            'vm-policy-router': ('vm/jitinterface.cpp', 'cee_wks_core', native_obj),
            'vm-native-factory': ('vm/assemblynative.cpp', 'cee_wks_core', native_obj),
            'binder-factory': ('binder/customassemblybinder.cpp', 'v3binder', native_obj),
            'interpreter-compiler': ('interpreter/eeinterp.cpp', 'clrinterpreter_objects', native_obj),
            'host-crossarch-jit': ('jit/ee_il_dll.cpp', 'clrjit_universal_arm64_arm64', host_obj),
            'host-jitinterface-guid': ('tools/aot/jitinterface/jitwrapper.cpp', 'jitinterface_arm64', host_obj)}
        compiled = {}
        for role, (tail, owner, directory) in roles.items():
            matches = [(db, row) for db, row in entries if row['file'].endswith('/src/coreclr/' + tail)
                       and owner in row.get('output', '') and Path(row['directory']).resolve() == directory.resolve()]
            require(len(matches) == 1, 'Expected one actual compile owner: ' + role)
            db, row = matches[0]
            tokens, defines = flags(row)
            require('-O3' in tokens and defines.get('URTBLDENV_FRIENDLY') == 'Retail' and
                    'NDEBUG' in defines and not ({'DEBUG', '_DEBUG'} & defines.keys()), 'Not Release compilation: ' + role)
            require('HOST_ARM64' in defines and 'TARGET_ARM64' in defines, 'Unexpected native architecture: ' + role)
            if directory == native_obj:
                require('FEATURE_INTERPRETER' in defines and 'FEATURE_READYTORUN' in defines and
                        'FEATURE_MAP_THUNKS_FROM_IMAGE' in defines and 'TARGET_IOS' in defines and
                        'FEATURE_DYNAMIC_CODE_COMPILED' not in defines and
                        '-mios-simulator-version-min=15.3' in tokens, 'Unexpected mobile feature definitions: ' + role)
                require('iPhoneSimulator' in tokens[tokens.index('-isysroot') + 1], 'Not simulator sysroot: ' + role)
            else:
                require('HOST_OSX' in defines and '-mmacosx-version-min=14.0' in tokens, 'Not macOS host compiler: ' + role)
            if role in ('vm-cid-worker', 'vm-policy-router', 'vm-native-factory'):
                require('FEATURE_CACHED_INTERFACE_DISPATCH' in defines, 'CID omitted from VM compilation')
            obj = directory / row['output']
            require(obj.is_file(), 'Compiled object missing: ' + str(obj))
            compiled[role] = {'database': str(db), 'databaseSha256': sha(db), 'entry': row,
                              'object': str(obj), 'objectSha256': sha(obj), 'defines': defines}
        write(output / 'compile-assessment.json', {'roles': compiled, 'cmakeCacheSha256': sha(native_obj / 'CMakeCache.txt'),
              'crossCmakeCacheSha256': sha(host_obj / 'CMakeCache.txt'), 'allCompileEntriesFresh': True,
              'totalCompileEntries': len(entries)})

        critical = {'native': product / 'libcoreclr.dylib', 'corelib': product / 'IL/System.Private.CoreLib.dll',
                    'crossgen2': product / 'arm64/crossgen2/crossgen2',
                    'jitinterface': product / 'arm64/crossgen2/libjitinterface_arm64.dylib',
                    'crossarchJit': product / 'arm64/crossgen2/libclrjit_universal_arm64_arm64.dylib'}
        identities = {name: sha(path) for name, path in critical.items()}
        for name in ('native', 'corelib', 'crossgen2'):
            require(identities[name] == completed[name + 'Sha256'], 'Final consumed file differs: ' + name)
        for name in ('jitinterface', 'crossarchJit'):
            require(identities[name] == sha(product / 'arm64' / critical[name].name), 'Compiler dependency copy differs')
        binary = {name: macho(path) for name, path in critical.items() if name != 'corelib'}
        require(any(row['platform'] == 7 for row in binary['native']['platforms']), 'Runtime image is not iOS simulator Mach-O')
        for name in ('crossgen2', 'jitinterface', 'crossarchJit'):
            require(any(row['platform'] == 1 for row in binary[name]['platforms']), 'Compiler tool cannot run on macOS host: ' + name)
        symbols = capture(['nm', '-C', critical['native']])
        kept_symbols = [line for line in symbols.splitlines() if 'CILInterp::compileMethod(' in line or
                        'CILInterp::getVersionIdentifier(' in line or 'CachedInterfaceDispatchResolveWorker(' in line]
        require(len(kept_symbols) == 3, 'Static interpreter/CID symbols missing in final CoreCLR')
        (output / 'static-interpreter-symbols.txt').write_text(chr(10).join(kept_symbols) + chr(10))
        literals = [guid_literal(critical[name]) for name in ('native', 'crossarchJit')]
        require(all(row['literalOffsets'] for row in literals), 'Matching VM/interpreter or native JIT GUID literal missing')
        disassembly = capture(['xcrun', 'llvm-objdump', '--macho', '--disassemble', '--dis-symname',
                               '_JitCompileMethod', critical['jitinterface']])
        (output / 'jitinterface-guid-disassembly.txt').write_text(disassembly + chr(10))
        shim_guid = jitinterface_guid(disassembly)
        write(output / 'native-binary-assessment.json', {'inputs': binary, 'guidLiterals': literals,
              'jitinterfaceGuid': shim_guid, 'disassemblySha256': sha(output / 'jitinterface-guid-disassembly.txt'),
              'staticInterpreterSymbols': kept_symbols})

        pre = runtime / 'artifacts/obj/coreclr/System.Private.CoreLib/iossimulator.arm64.Release/PreTrim/System.Private.CoreLib.dll'
        post = pre.parent.parent / pre.name
        mirror = runtime / 'artifacts/obj/coreclr/ILCompiler.Compiler/iossimulator.arm64.Release/ILCompiler.Compiler.dll'
        descriptor = pre.parent.parent / 'ILLink.Descriptors.xml'
        descriptor_text = descriptor.read_text()
        require(all('name="' + name + '"' in descriptor_text for name in BRIDGE if not name.endswith('Native')),
                'Actual generated linker descriptor omits private bridge roots')
        sdk = args.sdk_dotnet.resolve() if args.sdk_dotnet else runtime / '.dotnet/dotnet'
        helper = args.metadata_tool.resolve()
        env = {key: value for key, value in os.environ.items() if not key.startswith(('DOTNET_', 'COMPlus_'))}
        runtimes = subprocess.check_output([str(sdk), '--list-runtimes'], env=env, text=True)
        versions = re.findall(r'^Microsoft\.NETCore\.App (11\.[^ ]+) ', runtimes, re.M)
        require(versions, 'Host SDK .NET 11 runtime missing for trusted PE inspector')
        command = [str(sdk), 'exec', '--fx-version', versions[-1], str(helper)] + [str(p) for p in (pre, post, critical['corelib'], mirror)]
        process = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        (output / 'metadata-inspector.stdout.json').write_text(process.stdout)
        (output / 'metadata-inspector.stderr.txt').write_text(process.stderr)
        require(process.returncode == 0, 'Host-only PE metadata inspection failed; retained raw streams')
        metadata = json.loads(process.stdout)
        require(len(metadata) == 4, 'Expected three CoreLib stages and compiled managed flag mirror')
        for row in metadata[:3]:
            require(row['assembly'] == 'System.Private.CoreLib' and row['managedNativeRva'] == 0, 'Unexpected CoreLib IL stage')
            bridges = [m for m in row['methods'] if m['owner'] == ALC and m['name'].startswith('RuneCLR_')]
            require({m['name'] for m in bridges} == BRIDGE and len(bridges) == 5 and
                    all('Private' in m['attributes'] for m in bridges), 'Exact private bridge missing after trim')
            nested = {m['name'] for m in row['methods'] if m['owner'] == ALC + '+RuneCLRInterpreterLoadContext'}
            require({'.ctor', 'Load', 'LoadUnmanagedDll'} <= nested, 'Nested required-context methods removed')
            require(NATIVE_ENTRIES <= {m['nativeEntry'] for m in row['methods']}, 'QCall PInvoke implementation missing')
            require(row['sha256'] == sha(row['path']), 'Metadata input changed')
        require(metadata[1]['sha256'] == metadata[2]['sha256'], 'PostTrim and ProductIL differ')
        require(any(f['name'] == 'CORJIT_FLAG_INTERPRET_REQUIRED' and f['value'] == 33 for f in metadata[3]['fields']),
                'Compiled managed CORJIT enum mirror does not contain bit33')
        write(output / 'metadata-assessment.json', {'stages': metadata, 'descriptorSha256': sha(descriptor),
              'hostOnlyCommand': command, 'metadataInspectorSha256': sha(helper), 'hostRuntime': versions[-1],
              'inspectedAssembliesLoaded': False, 'bridgeMethodsEachStage': 5, 'nativeEntriesEachStage': 3})
        require(all(sha(path) == identities[name] for name, path in critical.items()), 'Native/managed compiler inputs changed during assessment')
        require(not capture(['git', '-C', runtime, 'status', '--porcelain', '--untracked-files=no']), 'Assessment changed tracked source')
        result.update(success=True, sourceFiles=27, criticalHashes=identities, sourceTrackedClean=True,
                      metadataPassed=True, nativeGuidPassed=True, nativeConfigurationPassed=True,
                      baselineNativeUnchanged=True, assessorSha256=sha(__file__))
    except Exception:
        result['error'] = traceback.format_exc()
        write(output / 'results.json', result)
        raise
    write(output / 'results.json', result)
    print('PASS combined source27; Release simulator/static-interpreter features; nativeGUID; CoreLib bridge5/import3 at3 IL stages; managed bit33')
    print('Evidence: ' + str(output))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--metadata-tool', type=Path, required=True)
    parser.add_argument('--sdk-dotnet', type=Path)
    parser.add_argument('--output', type=Path)
    return assess(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
