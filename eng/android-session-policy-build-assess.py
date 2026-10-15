#!/usr/bin/env python3
"""Read-only assessment of matching Android x64 Checked/Release session-policy products."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import traceback

UTILITY_SHA256 = 'bada00fed05717d5d8b16e50e73705754bfe8629cd6b5a09fba38ca27c6e4645'
utility = Path(__file__).with_name('ios-session-policy-build-assess.py')
spec = importlib.util.spec_from_file_location('ios_build_utilities', utility)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
core.require(core.sha(utility) == UTILITY_SHA256, 'Frozen shared assessor utility mismatch')


def elf(path):
    data = Path(path).read_bytes()
    core.require(data[:4] == bytes([127]) + b'ELF' and data[4:7] == bytes([2, 1, 1]),
                 'Expected ELF64 little-endian image: ' + str(path))
    image_type, machine = struct.unpack_from('<HH', data, 16)
    core.require(image_type == 3 and machine == 62, 'Expected x86_64 shared ELF: ' + str(path))
    offset = struct.unpack_from('<Q', data, 40)[0]
    entry_size, count, names_index = struct.unpack_from('<HHH', data, 58)
    core.require(entry_size >= 64 and count > names_index, 'Missing ELF section table')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, offset + i * entry_size) for i in range(count)]
    names_row = sections[names_index]
    names = data[names_row[4]:names_row[4] + names_row[5]]
    build_ids = []
    for row in sections:
        start = row[0]
        name = names[start:names.find(bytes([0]), start)].decode('ascii', errors='replace')
        if name != '.note.gnu.build-id':
            continue
        cursor, end = row[4], row[4] + row[5]
        while cursor + 12 <= end:
            name_size, value_size, note_type = struct.unpack_from('<III', data, cursor)
            cursor += 12
            owner = data[cursor:cursor + name_size].rstrip(bytes([0]))
            cursor += (name_size + 3) & ~3
            value = data[cursor:cursor + value_size]
            cursor += (value_size + 3) & ~3
            if owner == b'GNU' and note_type == 3:
                build_ids.append(value.hex())
    return {'path': str(path), 'sha256': core.sha(path), 'format': 'ELF64-little-endian',
            'machine': 'x86_64', 'type': 'shared-object', 'buildIds': build_ids}


def cache_value(cache, name):
    match = re.search('^' + re.escape(name) + r':[^=]+=(.*)$', cache, re.M)
    return match[1] if match else None


def assess(args):
    build = args.build.resolve()
    runtime = build / 'runtime'
    output = (args.output or build.parent / 'android-session-policy-build-assessment-20261013').resolve()
    core.require(not core.below(output, runtime), 'Output must be outside the runtime worktree')
    output.mkdir(exist_ok=False)
    result = {'success': False, 'executionVerified': False, 'candidateCommit': core.COMMIT,
              'scope': 'Source/configuration/ELF/PE/compiler identity; no APK or emulator execution'}
    try:
        completed, source, request = [core.read(build / n) for n in ('results.json', 'source.json', 'request.json')]
        core.require(completed['success'] and completed['buildExit'] == 0 and
                     (build / 'build.exit').read_text().strip() == '0', 'Unsuccessful matching build')
        for row in (completed, source, request):
            core.require(row['base'] == core.BASE and row['commit'] == core.COMMIT and row['tree'] == core.TREE,
                         'Source/build/request identity mismatch')
        for row in (completed, request):
            core.require(row['target'] == 'android.x64' and row['configuration'] == args.configuration and
                         row['frameworkConfiguration'] == 'Release', 'Target/configuration mismatch')
        core.require(source['configuration'] == 'android.x64.' + args.configuration, 'Source configuration mismatch')
        result['configuration'] = args.configuration
        core.require(core.capture(['git', '-C', runtime, 'rev-parse', 'HEAD']) == core.COMMIT and
                     core.capture(['git', '-C', runtime, 'rev-parse', 'HEAD^{tree}']) == core.TREE and
                     not core.capture(['git', '-C', runtime, 'status', '--porcelain', '--untracked-files=no']),
                     'Live source commit/tree/clean mismatch')
        changed = core.capture(['git', '-C', runtime, 'diff', '--name-only', core.BASE, core.COMMIT]).splitlines()
        core.require(len(changed) == 27 and set(changed) == set(source['sourceHashes']), 'Expected exact source27')
        for name in changed:
            core.require(core.sha(runtime / name) == source['sourceHashes'][name], 'Changed source differs: ' + name)
        core.require(request['sdkVersion'] == '11.0.100-rc.1.26420.103' and request['cleanBuildObjects'],
                     'Unexpected SDK or reused build objects')
        baseline = build.parent / 'runtime/artifacts/bin/coreclr/iossimulator.arm64.Debug/libcoreclr.dylib'
        core.require(core.sha(baseline) == request['baselineNativeBeforeSha256'], 'Original baseline native changed')
        core.write(output / 'source-assessment.json', {'base': core.BASE, 'commit': core.COMMIT, 'tree': core.TREE,
                   'sourceHashes': source['sourceHashes'], 'sourceTrackedClean': True})
        compiled = assess_compilation(runtime, output, args.configuration)
        critical, identities = assess_native(args, runtime, completed, output)
        assess_metadata(args, runtime, critical, output)
        core.require(all(core.sha(path) == identities[name] for name, path in critical.items()), 'Products changed during assessment')
        core.require(not core.capture(['git', '-C', runtime, 'status', '--porcelain', '--untracked-files=no']), 'Tracked source changed')
        result.update(success=True, sourceFiles=27, compileOwners=len(compiled), sourceTrackedClean=True,
                      nativeConfigurationPassed=True, nativeGuidPassed=True, metadataPassed=True,
                      dynamicInterpreterLibrary=True, baselineNativeUnchanged=True,
                      criticalHashes=identities, assessorSha256=core.sha(__file__))
    except Exception:
        result['error'] = traceback.format_exc()
        core.write(output / 'results.json', result)
        raise
    core.write(output / 'results.json', result)
    print('PASS Android source27; ' + args.configuration + ' x64/API24; shared interpreter/native JIT; GUID; CoreLib bridge5/import3 at3 IL stages; bit33')
    print('Evidence: ' + str(output))
    return 0


def assess_compilation(runtime, output, configuration='Checked'):
    native_obj = runtime / ('artifacts/obj/coreclr/android.x64.' + configuration)
    host_obj = native_obj / 'arm64'
    cache = (native_obj / 'CMakeCache.txt').read_text()
    core.require((cache_value(cache, 'CMAKE_BUILD_TYPE') or '').upper() == configuration.upper() and
                 cache_value(cache, 'ANDROID_ABI') == 'x86_64' and
                 cache_value(cache, 'FEATURE_INTERPRETER') == '1' and
                 cache_value(cache, 'FEATURE_DYNAMIC_CODE_COMPILED') == '1', 'Android features/ABI/configuration mismatch')
    host_cache = (host_obj / 'CMakeCache.txt').read_text()
    core.require((cache_value(host_cache, 'CMAKE_BUILD_TYPE') or '').upper() == configuration.upper(),
                 'Host compiler configuration differs')
    feature_rules = runtime / 'src/coreclr/clrfeatures.cmake'
    rules = feature_rules.read_text()
    core.require('if (NOT FEATURE_DYNAMIC_CODE_COMPILED)' in rules and
                 'set(FEATURE_CORECLR_CACHED_INTERFACE_DISPATCH $<IF:$<CONFIG:Debug,Checked>,1,0>)' in rules and
                 'set(FEATURE_CORECLR_VIRTUAL_STUB_DISPATCH 1)' in rules, 'Source CID/VSD rule changed; review required')
    toolchain = cache_value(cache, 'CMAKE_TOOLCHAIN_FILE')
    core.require(toolchain and toolchain.endswith('/build/cmake/android.toolchain.cmake'), 'Missing NDK toolchain')
    ndk = Path(toolchain).parent.parent.parent
    properties = ndk / 'source.properties'
    core.require('Pkg.Revision = 27.2.12479018' in properties.read_text(), 'Expected Darwin r27c NDK')
    rows = []
    for database in (native_obj / 'compile_commands.json', host_obj / 'compile_commands.json'):
        entries = core.read(database)
        core.require(entries and all(core.below(e['file'], runtime) and core.below(e['directory'], runtime)
                     for e in entries), 'Compile database source/object owner differs')
        rows.extend((database, e) for e in entries)
    roles = {
        'vm-cid-worker': ('vm/virtualcallstub.cpp', 'cee_wks_core', native_obj),
        'vm-policy-router': ('vm/jitinterface.cpp', 'cee_wks_core', native_obj),
        'vm-native-factory': ('vm/assemblynative.cpp', 'cee_wks_core', native_obj),
        'binder-factory': ('binder/customassemblybinder.cpp', 'v3binder', native_obj),
        'interpreter-compiler': ('interpreter/eeinterp.cpp', 'clrinterpreter_objects', native_obj),
        'target-native-jit': ('jit/ee_il_dll.cpp', 'clrjit.dir', native_obj),
        'host-published-jit': ('jit/ee_il_dll.cpp', 'clrjit.dir', host_obj),
        'host-crossarch-jit': ('jit/ee_il_dll.cpp', 'clrjit_unix_x64_arm64', host_obj),
        'host-jitinterface-guid': ('tools/aot/jitinterface/jitwrapper.cpp', 'jitinterface_arm64', host_obj)}
    compiled = {}
    for role, (tail, owner, directory) in roles.items():
        matches = [(db, e) for db, e in rows if e['file'].endswith('/src/coreclr/' + tail) and
                   owner in e.get('output', '') and Path(e['directory']).resolve() == directory.resolve()]
        core.require(len(matches) == 1, 'Expected one compile owner: ' + role)
        db, entry = matches[0]
        tokens, defines = core.flags(entry)
        core.require('TARGET_AMD64' in defines, 'x64 compilation mismatch: ' + role)
        if configuration == 'Checked':
            core.require('-O2' in tokens and defines.get('URTBLDENV_FRIENDLY') == 'Checked' and
                         {'DEBUG', '_DEBUG', 'BUILDENV_CHECKED'} <= defines.keys(), 'Checked compilation mismatch: ' + role)
        else:
            optimization = '-O2' if directory == native_obj else '-O3'
            core.require(optimization in tokens and defines.get('URTBLDENV_FRIENDLY') == 'Retail' and
                         'NDEBUG' in defines and not ({'DEBUG', '_DEBUG', '_DBG', 'BUILDENV_CHECKED', 'BUILDENV_DEBUG'} & defines.keys()),
                         'Release compilation mismatch: ' + role)
        if directory == native_obj:
            core.require('HOST_AMD64' in defines and 'HOST_ANDROID' in defines and
                         any('x86_64' in t and 'linux-android24' in t for t in tokens), 'Android API24 target mismatch: ' + role)
            if role != 'target-native-jit':
                core.require({'FEATURE_INTERPRETER', 'FEATURE_DYNAMIC_CODE_COMPILED', 'FEATURE_READYTORUN'} <= defines.keys(),
                             'Missing interpreter/JIT/R2R definitions: ' + role)
        else:
            core.require('HOST_ARM64' in defines and 'HOST_OSX' in defines, 'Not Mac ARM64 host tool: ' + role)
        if role in ('vm-cid-worker', 'vm-policy-router', 'vm-native-factory'):
            core.require(('FEATURE_CACHED_INTERFACE_DISPATCH' in defines) == (configuration == 'Checked') and
                         'FEATURE_VIRTUAL_STUB_DISPATCH' in defines, 'Actual Android dynamic-code CID/VSD source rule differs')
        obj = directory / entry['output']
        core.require(obj.is_file(), 'Compiled owner object missing: ' + str(obj))
        compiled[role] = {'database': str(db), 'databaseSha256': core.sha(db), 'entry': entry,
                          'object': str(obj), 'objectSha256': core.sha(obj), 'defines': defines}
    core.write(output / 'compile-assessment.json', {'roles': compiled, 'roleCount': len(compiled), 'configuration': configuration,
               'featureRulesSha256': core.sha(feature_rules),
               'configurationRulesSha256': core.sha(runtime / 'eng/native/configurecompiler.cmake'),
               'optimizationRulesSha256': core.sha(runtime / 'eng/native/configureoptimization.cmake'),
               'cachedInterfaceDispatchCapability': configuration == 'Checked',
               'virtualStubDispatchCapability': True,
               'nativeCacheSha256': core.sha(native_obj / 'CMakeCache.txt'),
               'hostCacheSha256': core.sha(host_obj / 'CMakeCache.txt'),
               'ndkSourcePropertiesSha256': core.sha(properties), 'toolchainSha256': core.sha(toolchain)})
    return compiled


def assess_native(args, runtime, completed, output):
    product = runtime / ('artifacts/bin/coreclr/android.x64.' + args.configuration)
    compiler = Path(completed['crossgen2'])
    critical = {'native': Path(completed['native']), 'corelib': Path(completed['corelib']),
                'crossgen2': compiler, 'interpreter': Path(completed['interpreter']),
                'targetJit': Path(completed['targetJit']),
                'jitinterface': compiler.parent / 'libjitinterface_arm64.dylib',
                'crossarchJit': compiler.parent / 'libclrjit_unix_x64_arm64.dylib'}
    core.require(all(core.below(p, product) for p in critical.values()), 'Consumed product outside fresh tree')
    identities = {name: core.sha(path) for name, path in critical.items()}
    for name in ('native', 'corelib', 'crossgen2'):
        core.require(identities[name] == completed[name + 'Sha256'], 'Completed hash differs: ' + name)
    recorded = core.read(runtime.parent / 'artifacts.json')
    for name in ('interpreter', 'targetJit'):
        matches = [row for row in recorded if Path(row['path']).resolve() == critical[name].resolve()]
        core.require(len(matches) == 1 and identities[name] == matches[0]['sha256'], 'Recorded native component differs: ' + name)
    target_images = {name: elf(critical[name]) for name in ('native', 'interpreter', 'targetJit')}
    host_images = {name: core.macho(critical[name]) for name in ('crossgen2', 'jitinterface', 'crossarchJit')}
    core.require(all(any(row['platform'] == 1 for row in image['platforms']) for image in host_images.values()),
                 'Compiler inputs are not Mac-host images')
    # AotCompilerCommon.props publishes the host libclrjit.dylib under the
    # single-JIT target name on this x64 cross build. The separately built
    # unix-any-OS crossarch JIT is a different image, not that copy's source.
    published_sources = {'jitinterface': product / 'arm64' / critical['jitinterface'].name,
                         'crossarchJit': product / 'arm64/libclrjit.dylib'}
    props = runtime / 'src/coreclr/tools/aot/AotCompilerCommon.props'
    props_text = props.read_text()
    core.require('<SingleJitLibrarySourceName>$(_LibPrefix)clrjit$(_LibSuffix)</SingleJitLibrarySourceName>' in props_text and
                 'Link="$(SingleJitLibraryName)"' in props_text, 'Published single-JIT source mapping changed')
    for name, path in published_sources.items():
        core.require(identities[name] == core.sha(path), 'Host published compiler copy differs: ' + name)
    literals = [core.guid_literal(critical[name]) for name in ('native', 'interpreter', 'targetJit', 'crossarchJit')]
    core.require(all(row['literalOffsets'] for row in literals), 'VM/interpreter/native JIT GUID literal mismatch')
    disassembly = core.capture(['xcrun', 'llvm-objdump', '--macho', '--disassemble', '--dis-symname',
                                '_JitCompileMethod', critical['jitinterface']])
    (output / 'jitinterface-guid-disassembly.txt').write_text(disassembly + chr(10))
    shim_guid = core.jitinterface_guid(disassembly)
    symbol_source = critical['native']
    nm = args.llvm_bin.resolve() / 'llvm-nm'
    names = ('AssemblyNative_InitializeInterpreterRequiredLoadContext',
             'AssemblyNative_RuneCLRGetExecutionPolicyVersion', 'AssemblyNative_RuneCLRGetExecutionPolicy')
    def has_symbol(text, name):
        return any(line.split() and line.split()[-1] == name for line in text.splitlines())
    symbols = subprocess.run([str(nm), '--demangle', str(symbol_source)], capture_output=True, text=True)
    if not all(has_symbol(symbols.stdout, name) for name in names):
        debug = Path(str(symbol_source) + '.dbg')
        debug_image = elf(debug)
        core.require(debug_image['buildIds'] and debug_image['buildIds'] == target_images['native']['buildIds'],
                     'Native symbol image build-id mismatch')
        symbol_source = debug
        symbols = subprocess.run([str(nm), '--demangle', str(debug)], capture_output=True, text=True)
    core.require(symbols.returncode == 0, 'Native symbol inspection failed')
    kept = [line for line in symbols.stdout.splitlines() if line.split() and line.split()[-1] in names]
    core.require(all(has_symbol(symbols.stdout, name) for name in names), 'Native QCall entry symbols missing')
    (output / 'native-qcall-symbols.txt').write_text(chr(10).join(kept) + chr(10))
    core.write(output / 'native-binary-assessment.json', {'targetELF': target_images, 'hostMachO': host_images,
               'guidLiterals': literals, 'jitinterfaceGuid': shim_guid, 'nativeQCallSymbols': kept,
               'symbolImage': str(symbol_source), 'symbolImageSha256': core.sha(symbol_source),
               'publishedSources': {name: {'path': str(path), 'sha256': core.sha(path)}
                                    for name, path in published_sources.items()},
               'publicationProps': str(props), 'publicationPropsSha256': core.sha(props)})
    return critical, identities


def assess_metadata(args, runtime, critical, output):
    pre = runtime / ('artifacts/obj/coreclr/System.Private.CoreLib/android.x64.' + args.configuration + '/PreTrim/System.Private.CoreLib.dll')
    post = pre.parent.parent / pre.name
    mirrors = list((runtime / 'artifacts/obj/coreclr/ILCompiler.Compiler').glob('android.x64.*/ILCompiler.Compiler.dll'))
    core.require(len(mirrors) == 1, 'Expected one actual compiled managed JIT mirror')
    descriptor = pre.parent.parent / 'ILLink.Descriptors.xml'
    roots = descriptor.read_text()
    core.require(all('name="' + name + '"' in roots for name in core.BRIDGE if not name.endswith('Native')),
                 'Generated descriptor missing private API roots')
    sdk = args.sdk_dotnet.resolve() if args.sdk_dotnet else runtime / '.dotnet/dotnet'
    helper = args.metadata_tool.resolve()
    env = {key: value for key, value in os.environ.items() if not key.startswith(('DOTNET_', 'COMPlus_'))}
    versions = re.findall(r'^Microsoft[.]NETCore[.]App (11[.][^ ]+) ',
                          subprocess.check_output([str(sdk), '--list-runtimes'], env=env, text=True), re.M)
    core.require(versions, 'Host SDK runtime missing')
    command = [str(sdk), 'exec', '--fx-version', versions[-1], str(helper)] + [str(p) for p in (pre, post, critical['corelib'], mirrors[0])]
    process = subprocess.run(command, env=env, capture_output=True, text=True)
    (output / 'metadata-inspector.stdout.json').write_text(process.stdout)
    (output / 'metadata-inspector.stderr.txt').write_text(process.stderr)
    core.require(process.returncode == 0, 'Host-only PE inspection failed')
    metadata = json.loads(process.stdout)
    core.require(len(metadata) == 4, 'Expected three CoreLib stages and managed flag mirror')
    for row in metadata[:3]:
        core.require(row['assembly'] == 'System.Private.CoreLib' and row['managedNativeRva'] == 0, 'Unexpected CoreLib IL stage')
        bridges = [m for m in row['methods'] if m['owner'] == core.ALC and m['name'].startswith('RuneCLR_')]
        core.require({m['name'] for m in bridges} == core.BRIDGE and len(bridges) == 5 and
                     all('Private' in m['attributes'] for m in bridges), 'Private bridge trimmed or changed')
        nested = {m['name'] for m in row['methods'] if m['owner'] == core.ALC + '+RuneCLRInterpreterLoadContext'}
        core.require({'.ctor', 'Load', 'LoadUnmanagedDll'} <= nested and
                     core.NATIVE_ENTRIES <= {m['nativeEntry'] for m in row['methods']}, 'Nested context/native imports trimmed')
        core.require(core.sha(row['path']) == row['sha256'], 'Metadata input changed')
    core.require(metadata[1]['sha256'] == metadata[2]['sha256'], 'PostTrim and ProductIL differ')
    core.require(any(f['name'] == 'CORJIT_FLAG_INTERPRET_REQUIRED' and f['value'] == 33 for f in metadata[3]['fields']),
                 'Compiled managed bit33 missing')
    core.write(output / 'metadata-assessment.json', {'stages': metadata, 'descriptorSha256': core.sha(descriptor),
               'hostOnlyCommand': command, 'metadataInspectorSha256': core.sha(helper), 'hostRuntime': versions[-1],
               'inspectedAssembliesLoaded': False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--metadata-tool', type=Path, required=True)
    parser.add_argument('--llvm-bin', type=Path, required=True, help='Darwin-host r27c NDK LLVM bin directory')
    parser.add_argument('--sdk-dotnet', type=Path)
    parser.add_argument('--configuration', choices=('Checked', 'Release'), default='Checked')
    parser.add_argument('--output', type=Path)
    return assess(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
