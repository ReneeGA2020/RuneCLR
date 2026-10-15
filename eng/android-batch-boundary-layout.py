#!/usr/bin/env python3
"""Build a fresh Android x64 boundary composite; never execute target code or build APKs."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time
import traceback
import uuid
import zipfile

BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
COMMIT = '3126bbc9a8851a09ac6435b18a12882bad48f3ee'
TREE = '710936ae1729a5689ab0e0896f3cf722ddd3d31c'
OLD = '1724cdec553a7aff7a373a271a4be612651c7625'
BUILD_SHA = 'e4f0451abf6dcc47671b1ae400a98bf3316b0bf27478c468d1022cab0dd37769'
PROOF_SHA = '29d83ae68ca57ec2067261d15a901e81f8422981609f1fe6aaad5cb37879de5e'
FRAMEWORK_SHA = 'ac491a83b59ffd6d9abd396f2da3a415d4f171830e7c4b1af287e1948cfc86a3'
FRAMEWORK_INVENTORY_SHA = 'bb87538a5f80cecb6f6dbe82eee7f41a1e7f735929d42438d582d960f4fd013e'
INPUT_SHA = '82ea9368e8fe6e7070b6d181e09c2294aed0aacb3d2008399ae92a15ae88d3fb'
ELF_HELPER_SHA = '3ab977377032cca005a41b959fb21b2162c67dcc7658b44a1e43df85ca7d61eb'
INVENTORY_HELPER_SHA = 'eaf45e90e452282d8fa48b281de46fd04a8a4bf5b269144b466d89f322e95a2a'
INSPECTOR_SHA = '57934b53bc3665d3ad1b7f2def5acd084cdb0bf1d089f1f23a774d90d58aaaa6'
TYPED_SHA = '4605f5d3a34676e5fb6c8da856c1c7478620a2c29622b5fe73724d6a51c68cfe'
SDK_VERSION = '11.0.100-rc.1.26420.103'
FX_VERSION = '11.0.0-rc.1.26420.103'
LANES = [[1, 1], [1, 100], [1, 1000], [100, 100], [1000, 1000]]
CRITICAL = {'native', 'interpreter', 'targetJit', 'corelib', 'crossgen2', 'jitinterface', 'crossarchJit'}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x', encoding='ascii') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def cap(argv):
    return subprocess.check_output(list(map(str, argv)), text=True, timeout=120).strip()


def inventory(directory):
    return {p.relative_to(directory).as_posix(): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}


def helper(path, expected, name):
    need(sha(path) == expected, 'Frozen helper changed: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pe_layout(path):
    data = Path(path).read_bytes()
    need(len(data) >= 64 and data[:2] == b'MZ', 'Expected managed PE: ' + str(path))
    pe = struct.unpack_from('<I', data, 60)[0]
    need(pe + 24 <= len(data) and data[pe:pe + 4] == b'PE\0\0', 'Invalid PE signature')
    machine, count = struct.unpack_from('<HH', data, pe + 4)
    opt, size = pe + 24, struct.unpack_from('<H', data, pe + 20)[0]
    need(opt + size + count * 40 <= len(data), 'Truncated PE headers')
    magic = struct.unpack_from('<H', data, opt)[0]
    need(magic in (0x10b, 0x20b), 'Unsupported PE optional header')
    dirs = opt + (112 if magic == 0x20b else 96)
    need(dirs + 15 * 8 <= opt + size, 'Missing PE CLI directory')
    sections = [struct.unpack_from('<IIII', data, opt + size + i * 40 + 8) for i in range(count)]
    def offset(rva, length):
        owners = [raw + rva - va for vs, va, rs, raw in sections if va <= rva and rva + length <= va + rs]
        need(len(owners) == 1 and owners[0] + length <= len(data), 'PE RVA has no unique actual file owner')
        return owners[0]
    cli = offset(struct.unpack_from('<I', data, dirs + 14 * 8)[0], 72)
    native, native_size = struct.unpack_from('<II', data, cli + 64)
    need(bool(native) == bool(native_size), 'Partial managed-native directory')
    if native:
        need(native_size >= 16 and data[offset(native, 16):offset(native, 16) + 4] == b'RTR\0',
             'Missing ReadyToRun native signature')
        need(machine == (0x8664 ^ 0x7B79), 'ReadyToRun target must be actual Linux x64 PE machine')
    return {'machine': machine, 'ilOnly': bool(struct.unpack_from('<I', data, cli + 16)[0] & 1),
            'managedNativeRva': native, 'managedNativeSize': native_size, 'sha256': sha(path)}


def command(argv, output, name, env, timeout):
    argv = list(map(str, argv))
    write(output / (name + '.request.json'), {'argv': argv, 'timeoutSeconds': timeout, 'startedUtc': utc()})
    with (output / (name + '.stdout.log')).open('x') as stdout, (output / (name + '.stderr.log')).open('x') as stderr:
        process = subprocess.Popen(argv, stdout=stdout, stderr=stderr, env=env)
        write(output / (name + '.process.json'), {'pid': process.pid, 'argv': argv, 'startedUtc': utc()})
        timed_out = False
        try:
            status = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            status = process.returncode
    write(output / (name + '.exit.json'), {'exitCode': status, 'timedOut': timed_out, 'endedUtc': utc()})
    need(status == 0 and not timed_out, 'Owned command failed: ' + name)


def check_files(rows):
    for row in rows:
        need(sha(row['path']) == row['sha256'] and Path(row['path']).stat().st_size == row['size'],
             'Original inventoried input changed: ' + row['path'])


def source_identity(source, proof):
    need(cap(['git', '-C', source, 'rev-parse', 'HEAD']) == COMMIT
         and cap(['git', '-C', source, 'rev-parse', 'HEAD^{tree}']) == TREE
         and not cap(['git', '-C', source, 'status', '--porcelain', '--untracked-files=no']),
         'Actual runtime source is not the clean batch candidate')
    need(len(proof['sourceHashes']) == 38 and len(proof['patches']) == 10
         and proof['sourceCommit'] == COMMIT and proof['tree'] == TREE
         and proof['layoutSize'] == 72 and proof['layoutAlignment'] == 8
         and proof['batchIntervalOffset'] == 64, 'Exact38/10/meter72 source proof differs')
    for name, expected in proof['sourceHashes'].items():
        need(sha(source / name) == expected, 'Actual source bytes changed: ' + name)


def prerequisites(args):
    root = args.root.resolve()
    build = root / 'android-batch-interval-release-20261015-attempt1'
    record = read(build / 'results.json')
    need(sha(build / 'results.json') == BUILD_SHA and record['success'] is True and record['buildExit'] == 0
         and (build / 'build.exit').read_text().strip() == '0' and record['base'] == BASE
         and record['commit'] == COMMIT and record['tree'] == TREE and record['target'] == 'android.x64'
         and record['configuration'] == 'Release' and record['nativeMeterSize'] == 72
         and record['nativeMeterAlignment'] == 8 and record['nativeBatchIntervalOffset'] == 64
         and record['typedOwnerQueryAbiVerified'] is True and record['safeOpcodeCount'] == 47,
         'Frozen actual batch build identity differs')
    proof_path = build / 'source-proof.json'
    need(sha(proof_path) == PROOF_SHA == record['sourceProofSha256'], 'Frozen source proof differs')
    proof, source = read(proof_path), build / 'runtime'
    source_identity(source, proof)
    need(set(record['criticalHashes']) == CRITICAL, 'Exact seven critical products absent')
    products = {name: {'path': record[name], 'sha256': value} for name, value in record['criticalHashes'].items()}
    need(all(sha(row['path']) == row['sha256'] for row in products.values()), 'Critical product bytes differ')
    metadata = read(build / 'metadata-assessment.json')
    batch = read(build / 'shared-batch-compile/batch-compile-assessment.json')
    need(sha(build / 'metadata-assessment.json') == record['metadataAssessmentSha256'] and metadata['success'] is True
         and metadata['corelibStages'] == 3 and metadata['managedCompilerMirrorStages'] == 1
         and sha(build / 'shared-batch-compile/batch-compile-assessment.json') == record['sharedCompileAssessmentSha256']
         and batch['passed'] is True and batch['safeOpcodeCount'] == 47
         and batch['unsafeFlushBeforeCharge'] and batch['actualTrapFlush'] and batch['cleanupAdmissionExact'],
         'Actual native/compiler/private ABI receipt differs')
    need(all(sha(path) == expected for path, expected in metadata['actualPeHashes'].items()), 'Retained typed CoreLib/compiler mirror changed')
    guid_text = (source / 'src/coreclr/inc/jiteeversionguid.h').read_text()
    found = re.search(r'^constexpr GUID JITEEVersionIdentifier = \{ /\* ([0-9a-f-]+) \*/', guid_text, re.M)
    need(found is not None and found[1] == metadata['compilerGuid'], 'Actual source/compiler GUID differs')
    guid = uuid.UUID(found[1]).bytes_le
    need(all(Path(record[name]).read_bytes().count(guid) == metadata['criticalGuidByteCounts'][name]
             for name in ('native', 'interpreter', 'targetJit', 'crossarchJit')), 'Actual native/compiler GUID bytes changed')
    framework = root / 'android-session-policy-release-framework-20261013-attempt2'
    need(sha(framework / 'results.json') == FRAMEWORK_SHA
         and sha(framework / 'input-inventory.json') == FRAMEWORK_INVENTORY_SHA, 'Frozen original framework receipts differ')
    fw, raw = read(framework / 'results.json'), read(framework / 'input-inventory.json')
    need(fw['success'] and fw['base'] == BASE and fw['commit'] == OLD and fw['target'] == 'android.x64'
         and fw['configuration'] == 'Release' and fw['inputInventorySha256'] == FRAMEWORK_INVENTORY_SHA,
         'Original framework source/target/configuration differs')
    difference = cap(['git', '-C', source, 'diff', '--name-only', OLD, COMMIT, '--', 'src/libraries', 'src/native']).splitlines()
    need(difference == ['src/libraries/System.Private.CoreLib/src/System/Runtime/Loader/AssemblyLoadContext.cs'],
         'Reused framework/native source difference exceeds replaced CoreLib')
    groups = raw['groups']
    need(len(groups['framework']) == 180 and len(groups['native']) == 28 and len(groups['deps']) == 1,
         'Original180 framework /28 native /1 deps inventory differs')
    raw_rows = [row for rows in groups.values() for row in rows]
    check_files(raw_rows)
    names = [Path(row['path']).name for row in groups['framework']]
    need(len(set(names)) == 180 and 'System.Private.CoreLib.dll' not in names
         and all(n.startswith(('System.', 'Microsoft.')) or n in ('netstandard.dll', 'mscorlib.dll', 'WindowsBase.dll') for n in names),
         'Original framework has unexpected trusted/author components')
    need(all(pe_layout(row['path'])['managedNativeRva'] == 0 for row in groups['framework']), 'Original framework is not all raw IL')
    boundary = root / 'ios-batch-boundary-inputs-20261015-attempt1'
    need(sha(boundary / 'input-manifest.json') == INPUT_SHA, 'Frozen boundary manifest differs')
    inputs = read(boundary / 'input-manifest.json')
    need(inputs['schema'] == 'runeclr.mobile-batch-boundary.inputs.v1' and inputs['expectedContexts'] == 168
         and inputs['configuredLanes'] == LANES and len(inputs['files']) == 9, 'Boundary topology differs')
    need(all(sha(boundary / name) == value for name, value in inputs['files'].items()), 'Frozen boundary bytes differ')
    need(sha(args.bridge) == args.bridge_sha256 and sha(args.bridge_receipt) == args.bridge_receipt_sha256
         and args.bridge.name == 'AndroidBatchBoundaryBridge.dll' and pe_layout(args.bridge)['managedNativeRva'] == 0,
         'Pinned raw boundary executable bridge differs')
    bridge = read(args.bridge_receipt)
    need(bridge['success'] is True and bridge['bridgeSha256'] == args.bridge_sha256
         and bridge['inputManifestSha256'] == INPUT_SHA and bridge['executionVerified'] is False,
         'Bridge compilation ownership receipt differs')
    elf = helper(args.elf_helper, ELF_HELPER_SHA, 'frozen_android_elf')
    full = helper(args.inventory_helper, INVENTORY_HELPER_SHA, 'frozen_android_inventory')
    for name in ('native', 'interpreter', 'targetJit'):
        need(elf.elf(record[name])['abi'] == 'x86_64', 'Actual core ELF architecture differs')
    dependencies_path = build / 'dependency-inventories.json'
    need(sha(dependencies_path) == record['dependencyInventoriesSha256'], 'Frozen SDK/dependency inventories differ')
    dependencies = read(dependencies_path)
    full.require_unchanged(source / '.dotnet', dependencies['sdk'])
    compiler_folder = Path(record['crossgen2']).parent
    compiler_inventory = full.inventory(compiler_folder)
    for folder, expected in dependencies['inspectorPackages'].items():
        full.require_unchanged(folder, expected)
    need(sha(args.metadata_inspector) == INSPECTOR_SHA and sha(args.typed_inspector) == TYPED_SHA, 'Frozen metadata-only inspectors differ')
    ndk_receipt = root / 'android-toolchain-r27c-20261013/results.json'
    request = read(build / 'request.json')
    need(sha(ndk_receipt) == request['toolchainReceiptSha256'], 'Pinned NDK receipt differs')
    ndk = Path(read(ndk_receipt)['ndk'])
    full.require_unchanged(ndk, dependencies['ndk'])
    need(cap([source / '.dotnet/dotnet', '--version']) == SDK_VERSION, 'Exact source-private SDK differs')
    preserved = request['preservedFiles']
    need(all(sha(path) == value for path, value in preserved.items()), 'Preserved older products differ')
    frozen = {str(p.resolve()): sha(p) for p in (Path(__file__), build / 'results.json', proof_path,
              build / 'metadata-assessment.json', build / 'shared-batch-compile/batch-compile-assessment.json',
              dependencies_path, framework / 'results.json', framework / 'input-inventory.json',
              boundary / 'input-manifest.json', args.bridge, args.bridge_receipt, args.elf_helper,
              args.inventory_helper, args.metadata_inspector, args.typed_inspector, ndk_receipt)}
    return dict(root=root, build=build, record=record, source=source, proof=proof, products=products,
                metadata=metadata, framework=framework, raw=raw, raw_rows=raw_rows, boundary=boundary, inputs=inputs,
                elf=elf, full=full, dependencies=dependencies, compiler_folder=compiler_folder,
                compiler_inventory=compiler_inventory, ndk=ndk, preserved=preserved, frozen=frozen, libraryDifference=difference)


def build(args):
    need(sys.platform == 'darwin', 'This composite requires the configured Darwin build host')
    need(args.validate_only or args.build_slot_granted, 'Exclusive heavy-build slot required')
    root, output = args.root.resolve(), args.output.resolve()
    need(output.parent == root and not output.exists(), 'Fresh direct experiment child required')
    output.mkdir()
    result = dict(success=False, schema='runeclr.android-batch-boundary.layout.v1', base=BASE, commit=COMMIT,
                  tree=TREE, target='android.x64', configuration='Release', executionVerified=False,
                  nativeEntryProof=False, performanceMeasured=False, expectedContexts=168)
    try:
        state = prerequisites(args)
        record, source, full, elf = state['record'], state['source'], state['full'], state['elf']
        write(output / 'frozen-inputs.json', state['frozen'])
        write(output / 'sdk-inventory.json', state['dependencies']['sdk'])
        write(output / 'raw-framework-inventory.json', state['raw'])
        write(output / 'compiler-inventory.json', state['compiler_inventory'])
        if args.validate_only:
            result.update(success=True, frameworkBuildPerformed=False, sourceTrackedClean=True, sourceFiles=38, patches=10,
                          nativeMeterSize=72, nativeMeterAlignment=8, nativeBatchIntervalOffset=64,
                          scope='Actual read-only matching composite prerequisites; no framework build or target execution')
            write(output / 'results.json', result)
            print('PREFLIGHT PASS: exact batch/native/framework/boundary prerequisites', flush=True)
            return
        layout, inputs = output / 'layout', output / 'input'
        inputs.mkdir()
        for folder in ('managed', 'native', 'java', 'headers', 'receipts'):
            (layout / folder).mkdir(parents=True)
        input_hashes = {}
        for row in state['raw']['groups']['framework']:
            name = Path(row['path']).name
            if name == 'System.Private.CoreLib.dll':
                continue
            shutil.copy2(row['path'], inputs / name)
            input_hashes[name] = row['sha256']
        for path in (Path(record['corelib']), state['boundary'] / 'host/MobileBatchBoundaryProbe.dll',
                     state['boundary'] / 'host/BatchBoundary.Contract.dll', args.bridge):
            need(not (inputs / path.name).exists(), 'Composite input collision')
            shutil.copy2(path, inputs / path.name)
            input_hashes[path.name] = sha(path)
        composite = sorted(inputs.glob('*.dll'))
        need(len(composite) == 184 and all(sha(p) == input_hashes[p.name] and pe_layout(p)['managedNativeRva'] == 0 for p in composite),
             'Exactly184 raw framework/current-CoreLib/new-trusted inputs required')
        need('BatchBoundary.Author.dll' not in input_hashes, 'Author entered trusted composite')
        rsp = output / 'crossgen.rsp'
        rsp.write_text('\n'.join(['--targetos:linux', '--targetarch:x64', '--composite', '--inputbubble', '--resilient',
            '--optimize', '--parallelism:2', '--out:' + str(layout / 'managed/RuneCLR.Android.BatchBoundary.Framework.dll'),
            *map(str, composite)]) + '\n', encoding='ascii')
        env = {k: v for k, v in os.environ.items() if not k.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_'))
               and k not in ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH', 'LIBRARY_PATH',
                             'SDKROOT', 'MACOSX_DEPLOYMENT_TARGET', 'CMAKE_PREFIX_PATH', 'PKG_CONFIG_PATH',
                             'DYLD_LIBRARY_PATH', 'DYLD_INSERT_LIBRARIES', 'LD_LIBRARY_PATH', 'LD_PRELOAD')}
        removed_keys = sorted(set(os.environ) - set(env))
        env.update(PATH=str(root / 'tools/bin') + ':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                   DOTNET_CLI_HOME=str(output / 'dotnet-home'), DOTNET_CLI_USE_MSBUILD_SERVER='0')
        write(output / 'request.json', dict(driverSha256=sha(__file__), buildReceiptSha256=BUILD_SHA,
              sourceProofSha256=PROOF_SHA, sourceCommit=COMMIT, sourceTree=TREE, actualCriticalProducts=state['products'],
              inputManifestSha256=INPUT_SHA, bridgeSha256=args.bridge_sha256, bridgeReceiptSha256=args.bridge_receipt_sha256,
              compositeInputHashes=input_hashes, frameworkSourceCommit=OLD, libraryDifference=state['libraryDifference'],
              frozenInputs=state['frozen'], rspSha256=sha(rsp), removedEnvironmentKeys=removed_keys,
              timeoutSeconds=args.timeout, heavyBuildSlotGranted=True,
              executionVerified=False, startedUtc=utc()))
        command([record['crossgen2'], '@' + str(rsp)], output, 'crossgen', env, args.timeout)
        generated = sorted((layout / 'managed').glob('*.dll'))
        expected_names = set(input_hashes) | {'RuneCLR.Android.BatchBoundary.Framework.dll'}
        need({p.name for p in generated} == expected_names and len(generated) == 185, 'Exact185 fresh R2R outputs required')
        file_rows = []
        for path in generated:
            image = pe_layout(path)
            need(image['managedNativeRva'] != 0, 'Fresh component lacks ReadyToRun body')
            file_rows.append(dict(path=path.relative_to(layout).as_posix(), sha256=sha(path), size=path.stat().st_size,
                                  role='corelib' if path.name == 'System.Private.CoreLib.dll' else 'framework',
                                  inputSha256=input_hashes.get(path.name), target='linux.x64', pe=image))
        def copy(path, relative, role):
            path, target = Path(path), layout / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            need(not target.exists(), 'Layout output collision: ' + relative)
            shutil.copy2(path, target)
            file_rows.append(dict(path=relative, sha256=sha(target), size=target.stat().st_size, role=role, sourcePath=str(path)))
        for key, name in (('native', 'libcoreclr.so'), ('interpreter', 'libclrinterpreter.so'), ('targetJit', 'libclrjit.so')):
            copy(record[key], 'native/' + name, key)
        for row in state['raw']['groups']['native']:
            path = Path(row['path'])
            if path.name in ('libcoreclr.so', 'libclrinterpreter.so', 'libclrjit.so'):
                continue
            if path.suffix == '.so':
                copy(path, 'native/' + path.name, 'os-native')
            elif path.suffix == '.dex':
                copy(path, 'java/' + path.name, 'android-java')
        for row in state['raw']['groups']['deps']:
            copy(row['path'], 'managed/' + Path(row['path']).name, 'deps')
        for name, relative in [('src/coreclr/hosts/inc/coreclrhost.h', 'headers/hosts/coreclrhost.h'),
                               ('src/native/corehost/host_runtime_contract.h', 'headers/native/corehost/host_runtime_contract.h')]:
            copy(source / name, relative, 'header')
        packaged = {p.name: p for p in (layout / 'native').glob('*.so')}
        queue, seen, dependencies = list(packaged.values()), set(), []
        sysroot = state['ndk'] / 'toolchains/llvm/prebuilt/darwin-x86_64/sysroot/usr/lib/x86_64-linux-android'
        while queue:
            path = queue.pop(0)
            if str(path) in seen:
                continue
            seen.add(str(path))
            image = elf.elf(path)
            for name in image['needed']:
                if name in packaged:
                    target, disposition = packaged[name], 'packaged'
                elif name == 'libc++_shared.so':
                    copy(sysroot / name, 'native/' + name, 'ndk-native')
                    target = layout / 'native' / name
                    packaged[name], disposition = target, 'pinned-ndk'
                elif (sysroot / '24' / name).is_file():
                    target, disposition = sysroot / '24' / name, 'android-system-api24'
                else:
                    raise RuntimeError('Unresolved actual ELF dependency: ' + name)
                dependencies.append(dict(owner=path.name, needed=name, disposition=disposition, sha256=sha(target)))
                queue.append(target)
        current_corelib, new_corelib = Path(record['corelib']), layout / 'managed/System.Private.CoreLib.dll'
        for label, tool in (('component-metadata', args.metadata_inspector), ('component-typed', args.typed_inspector)):
            command([source / '.dotnet/dotnet', 'exec', '--fx-version', FX_VERSION, tool, current_corelib, new_corelib],
                    output, label, env, args.timeout)
        rows, typed = read(output / 'component-metadata.stdout.log'), read(output / 'component-typed.stdout.log')
        need(len(rows) == len(typed) == 2 and rows[0]['sha256'] == typed[0]['sha256'] == sha(current_corelib)
             and rows[1]['sha256'] == typed[1]['sha256'] == sha(new_corelib), 'Actual original/component metadata input hashes differ')
        need(rows[0]['methods'] == rows[1]['methods'] and rows[0]['fields'] == rows[1]['fields']
             and rows[0]['moduleVersionId'] == rows[1]['moduleVersionId'] and typed[0]['queries'] == typed[1]['queries'],
             'Fresh CoreLib component changed retained private APIs/MVID/typed QCall ABI')
        source_identity(source, state['proof'])
        check_files(state['raw_rows'])
        need(all(sha(row['path']) == row['sha256'] for row in state['products'].values()), 'Critical7 changed during composite build')
        need(all(sha(path) == value for path, value in state['metadata']['actualPeHashes'].items()), 'Typed CoreLib/compiler mirror changed')
        need(all(sha(path) == value for path, value in state['frozen'].items()), 'Frozen build input changed')
        need(all(sha(path) == value for path, value in state['preserved'].items()), 'Older product changed during build')
        need(inventory(inputs) == input_hashes, 'Composite input bytes changed during build')
        full.require_unchanged(source / '.dotnet', state['dependencies']['sdk'])
        full.require_unchanged(state['compiler_folder'], state['compiler_inventory'])
        full.require_unchanged(state['ndk'], state['dependencies']['ndk'])
        need(not list(layout.rglob('BatchBoundary.Author.dll')), 'Author entered export layout')
        receipts = []
        for name, path in [('native-build-review', state['build'] / 'results.json'), ('source-proof', state['build'] / 'source-proof.json'),
            ('native-metadata', state['build'] / 'metadata-assessment.json'), ('batch-compile', state['build'] / 'shared-batch-compile/batch-compile-assessment.json'),
            ('framework-build', state['framework'] / 'results.json'), ('framework-inventory', state['framework'] / 'input-inventory.json'),
            ('boundary-inputs', state['boundary'] / 'input-manifest.json'), ('bridge-build', args.bridge_receipt),
            ('component-metadata', output / 'component-metadata.stdout.log'), ('component-typed', output / 'component-typed.stdout.log')]:
            target = layout / 'receipts' / (name + '.json')
            shutil.copy2(path, target)
            receipts.append(dict(path=target.relative_to(layout).as_posix(), sha256=sha(target), size=target.stat().st_size))
        result.update(success=True, frameworkBuildPerformed=True, sourceTrackedClean=True, sourceFiles=38, patches=10,
            files=file_rows, receipts=receipts, criticalProducts=state['products'], critical7=record['criticalHashes'],
            coreCriticalUnchanged=True, corelibComponentMetadataUnchanged=True, typedOwnerQueryAbiVerified=True,
            originalFrameworkInputs=180, compositeInputCount=184, compositeFileCount=185,
            inputManifestSha256=INPUT_SHA, inputFiles=state['inputs']['files'], bridgeSha256=args.bridge_sha256,
            bridgeReceiptSha256=args.bridge_receipt_sha256, executableAssembly='AndroidBatchBoundaryBridge.dll',
            sourceProofSha256=PROOF_SHA, buildReceiptSha256=BUILD_SHA, nativeMeterSize=72, nativeMeterAlignment=8, nativeBatchIntervalOffset=64,
            frameworkReuseIsOriginalIL=True, reusedFrameworkSourceCommit=OLD, allElfDependenciesResolved=True, elfDependencies=dependencies,
            features={'interpreter': True, 'dynamicCodeCompiled': True}, layoutDriverSha256=sha(__file__),
            requestSha256=sha(output / 'request.json'), endedUtc=utc(),
            scope='Fresh184 IL inputs/185 Linux x64 R2R components and matched Android ELF layout; no APK or target execution')
        write(layout / 'layout.json', result)
        write(output / 'results.json', result)
        members = {p.relative_to(output).as_posix(): dict(sha256=sha(p), size=p.stat().st_size)
                   for p in sorted(layout.rglob('*')) if p.is_file()}
        archive = output / 'export.zip'
        with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as zipped:
            for name in members:
                zipped.write(output / name, name)
        write(output / 'export-manifest.json', dict(archive=str(archive), sha256=sha(archive), size=archive.stat().st_size,
              members=members, executionVerified=False, nativeEntryProof=False))
        print('LAYOUT PASS:184 trusted IL /185 R2R; no APK or execution', flush=True)
    except Exception:
        result.update(error=traceback.format_exc(), endedUtc=utc())
        if not (output / 'results.json').exists():
            write(output / 'results.json', result)
        else:
            write(output / 'export-failure.json', dict(success=False, error=result['error']))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'output', 'bridge', 'bridge-receipt'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('bridge-sha256', 'bridge-receipt-sha256'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--elf-helper', type=Path)
    parser.add_argument('--inventory-helper', type=Path, default=Path(__file__).with_name('android-derived-ledger-inventory.py'))
    parser.add_argument('--metadata-inspector', type=Path)
    parser.add_argument('--typed-inspector', type=Path)
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--build-slot-granted', action='store_true')
    parser.add_argument('--timeout', type=int, default=900)
    args = parser.parse_args()
    args.root = args.root.resolve()
    args.elf_helper = args.elf_helper or args.root / 'android-session-policy-tools-20261013/android-session-policy-layout-release-v2-20261013.py'
    args.metadata_inspector = args.metadata_inspector or args.root / 'ios-derived-ledger-tools-20261014-attempt2/metadata/RuneCLR.MetadataInspector.dll'
    args.typed_inspector = args.typed_inspector or args.root / 'android-session-budget-tools-20261013/metadata/tool/TypedQueryInspector.dll'
    build(args)


if __name__ == '__main__':
    main()
