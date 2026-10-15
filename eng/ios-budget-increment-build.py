#!/usr/bin/env python3
"""Build the exact terminal-counter increment plus CID v2 in a fresh iOS simulator worktree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import shlex
import struct
import subprocess
import time
import traceback
import uuid

PROOF_SHA = '6dea87eae1bbbb3142319707c2af4f5cca142a5bc1e4fe8ef665d8a93a2e4d48'
EXPECTED_TREE = '91673a7980bda79006259e525741fecb04324444'
PARENT_DRIVER_SHA256 = 'c7468dde6416b8882f25b59497db830308e880918fc68a230a5df5a05974cbb4'
BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
WINDOWS_COMMIT = '20405f7ae23e183e038703aa5e356b3310fef427'
OLD_COMMIT = '1724cdec553a7aff7a373a271a4be612651c7625'
PATCHES = {
    '0001-collectible-cid-publication.patch': '43b36606fa94967e97f2640e8d76dcfa8f0af21eeb77a065a0eea5c83c915857',
    '0003-collectible-interpreter-selection.patch': 'b7d446243a099c6fc01c19bdc6e83c151eb4771112001fd9bd7185a0d1950ccb',
    '0004-interpreter-required-load-context.patch': '714ba322b3df83ccb3feb5b91043b779e4c75b212ea9d4dbf95db06c0e330657',
    '0005-native-session-instruction-meter.patch': '5ecb5d595aba473c5709d8b172821ae7de228ee7705f140535df3b890ea7ec94',
    '0006-session-terminal-prototype.patch': '3acec56c4fb1946d38ff324d30b5bb7ee8220d1ab66439c5352c031cbb042d76',
    '0007-session-terminal-finalizer-boundary.patch': 'c21c940db0f5041f3e681d4bafafbc555f51412f2c9a188c142981af27c468ef',
    '0008-terminal-counter-increment.patch': 'a1bbecff236c5484a35e9c79643bd5c572e34a0eda8e843904c54bd31d04f108',
}

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def capture(arguments):
    return subprocess.check_output([str(a) for a in arguments], text=True).strip()

def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + chr(10))

def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

def clean(source):
    return not capture(['git', '-C', source, 'status', '--porcelain', '--untracked-files=no'])

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def require(value, message):
    if not value: raise RuntimeError(message)


def preserved(root):
    old = root / 'ios-session-policy-release-20261013/runtime'
    require(capture(['git', '-C', old, 'rev-parse', 'HEAD']) == OLD_COMMIT and clean(old), 'Old iOS source changed')
    paths = [root / 'runtime/artifacts/bin/coreclr/iossimulator.arm64.Debug/libcoreclr.dylib']
    product = old / 'artifacts/bin/coreclr/iossimulator.arm64.Release'
    paths += [product / 'libcoreclr.dylib', product / 'IL/System.Private.CoreLib.dll', product / 'arm64/crossgen2/crossgen2']
    return {str(path): sha(path) for path in paths}


def assess_product(source, product, out, args, commit):
    obj = source / 'artifacts/obj/coreclr/iossimulator.arm64.Release'
    host = obj / 'arm64'
    cache = (obj / 'CMakeCache.txt').read_text()
    for expression in (r'^CMAKE_BUILD_TYPE:[^=]+=RELEASE$',
                       r'^CMAKE_OSX_SYSROOT:[^=]+=iphonesimulator$',
                       r'^CMAKE_OSX_DEPLOYMENT_TARGET:[^=]+=15\.3$',
                       r'^FEATURE_INTERPRETER:[^=]+=1$'):
        require(re.search(expression, cache, re.M), 'Actual iOS simulator Release/interpreter cache mismatch')
    rows = []
    for directory in (obj, host):
        db = directory / 'compile_commands.json'
        for row in read(db): rows.append((directory, db, row))
    roles = {
        'cid': ('vm/virtualcallstub.cpp', 'cee_wks_core', obj),
        'selection': ('vm/jitinterface.cpp', 'cee_wks_core', obj),
        'factory': ('vm/assemblynative.cpp', 'cee_wks_core', obj),
        'finalizer': ('vm/comutilnative.cpp', 'cee_wks_core', obj),
        'eh': ('vm/exceptionhandling.cpp', 'cee_wks_core', obj),
        'binder': ('binder/customassemblybinder.cpp', 'v3binder', obj),
        'opcode-meter': ('vm/interpexec.cpp', 'cee_wks_core', obj),
        'interpreter-compiler': ('interpreter/eeinterp.cpp', 'clrinterpreter_objects', obj),
        'crossarch-jit': ('jit/ee_il_dll.cpp', 'clrjit_universal_arm64_arm64', host),
        'jitinterface': ('tools/aot/jitinterface/jitwrapper.cpp', 'jitinterface_arm64', host),
    }
    compiled = {}
    for role, (tail, owner, directory) in roles.items():
        matches = [(db, row) for actual_dir, db, row in rows if actual_dir == directory
                   and row['file'].endswith('/src/coreclr/' + tail) and owner in row.get('output', '')]
        require(len(matches) == 1, 'Actual native compile owner not unique: ' + role)
        db, row = matches[0]
        require(Path(row['file']).resolve().is_relative_to(source.resolve())
                and Path(row['directory']).resolve() == directory.resolve(), 'Foreign compile source/object tree')
        tokens = row.get('arguments') or shlex.split(row['command'])
        defines = dict((token[2:].partition('=')[0], token[2:].partition('=')[2] or '1')
                       for token in tokens if token.startswith('-D'))
        require('-O3' in tokens and defines.get('URTBLDENV_FRIENDLY') == 'Retail'
                and 'NDEBUG' in defines and not {'DEBUG', '_DEBUG'} & defines.keys(), 'Not actual Release: ' + role)
        require({'HOST_ARM64', 'TARGET_ARM64'} <= defines.keys(), 'Not actual ARM64 compile: ' + role)
        if directory == obj:
            require({'FEATURE_INTERPRETER', 'FEATURE_READYTORUN', 'TARGET_IOS'} <= defines.keys()
                    and 'FEATURE_DYNAMIC_CODE_COMPILED' not in defines
                    and '-mios-simulator-version-min=15.3' in tokens, 'Unexpected simulator features: ' + role)
            require('iPhoneSimulator' in tokens[tokens.index('-isysroot') + 1], 'Not simulator sysroot')
        else:
            require('HOST_OSX' in defines, 'Compiler is not macOS hosted')
        if role in ('cid', 'selection', 'factory', 'finalizer', 'eh'):
            require('FEATURE_CACHED_INTERFACE_DISPATCH' in defines, 'CID unexpectedly absent')
        object_file = directory / row['output']
        require(object_file.is_file(), 'Actual compiled object missing: ' + role)
        compiled[role] = {'database': str(db), 'databaseSha256': sha(db), 'entry': row,
                          'defines': defines, 'object': str(object_file), 'objectSha256': sha(object_file)}
    write(out / 'native-compile-assessment.json', {'roles': compiled, 'cacheSha256': sha(obj / 'CMakeCache.txt')})
    native = product / 'libcoreclr.dylib'
    native_bytes = native.read_bytes()
    require(struct.unpack_from('<I', native_bytes)[0] == 0xfeedfacf
            and struct.unpack_from('<I', native_bytes, 4)[0] == 0x100000c, 'Not thin ARM64 Mach-O runtime')
    require(('@Commit: ' + commit).encode() in native_bytes, 'CoreCLR candidate source stamp missing')
    guid = uuid.UUID('7c844228-f051-4b9b-9b8f-4e221230806f').bytes_le
    crossjit = product / 'arm64/crossgen2/libclrjit_universal_arm64_arm64.dylib'
    require(guid in native_bytes and guid in crossjit.read_bytes(), 'Matching VM/interpreter and crossarch JIT GUID missing')
    coreobj = source / 'artifacts/obj/coreclr/System.Private.CoreLib/iossimulator.arm64.Release'
    stages = [coreobj / 'PreTrim/System.Private.CoreLib.dll', coreobj / 'System.Private.CoreLib.dll',
              product / 'IL/System.Private.CoreLib.dll']
    require(all(p.is_file() for p in stages), 'Missing actual CoreLib stage')
    versions = [line.split()[1] for line in capture([source / '.dotnet/dotnet', '--list-runtimes']).splitlines()
                if line.startswith('Microsoft.NETCore.App ')]
    require(versions, 'Private SDK host runtime missing')
    command = [str(source / '.dotnet/dotnet'), 'exec', '--fx-version', versions[-1], str(args.metadata_tool.resolve()), *map(str, stages)]
    with (out / 'metadata-inspector.stdout.json').open('w') as stdout, (out / 'metadata-inspector.stderr.log').open('w') as stderr:
        env = {key: value for key, value in os.environ.items() if not key.startswith(('DOTNET_', 'COMPlus_'))}
        done = subprocess.run(command, stdout=stdout, stderr=stderr, env=env)
    require(done.returncode == 0, 'Trusted host PE inspector failed; original streams retained')
    metadata = read(out / 'metadata-inspector.stdout.json')
    require(len(metadata) == 3, 'Expected three actual CoreLib stages')
    required = {'RuneCLR_CreateInterpreterRequired', 'RuneCLR_GetExecutionPolicyVersion', 'RuneCLR_GetExecutionPolicy',
                'RuneCLR_GetExecutionPolicyVersionNative', 'RuneCLR_GetExecutionPolicyNative'}
    meter = {'RuneCLR_CreateInstructionMetered', 'RuneCLR_GetInstructionMeterVersion', 'RuneCLR_GetInstructionMeterRemaining',
             'RuneCLR_GetInstructionMeterExecuted', 'RuneCLR_GetInstructionMeterExhausted', 'RuneCLR_GetInstructionMeterVersionNative',
             'RuneCLR_GetInstructionMeterRemainingNative', 'RuneCLR_GetInstructionMeterExecutedNative'}
    terminal = {'RuneCLR_CreateTerminalPrototype', 'RuneCLR_GetTerminalPrototypeVersion', 'RuneCLR_GetTerminalPrototypeIsTerminated',
                'RuneCLR_GetTerminalPrototypeReason', 'RuneCLR_GetTerminalPrototypePhase', 'RuneCLR_GetTerminalPrototypeCleanupRemaining',
                'RuneCLR_GetTerminalPrototypeCleanupExecuted', 'RuneCLR_GetTerminalPrototypeVersionNative',
                'RuneCLR_GetTerminalPrototypeReasonNative', 'RuneCLR_GetTerminalPrototypePhaseNative',
                'RuneCLR_GetTerminalPrototypeCleanupRemainingNative', 'RuneCLR_GetTerminalPrototypeCleanupExecutedNative'}
    gc = {'RuneCLR_GetTerminalFinalizerBoundaryVersion', 'RuneCLR_GetTerminalFinalizerBoundaryVersionNative',
          'RuneCLR_IsTerminatedFinalizerOwner'}
    signatures = {'GCInterface_RuneCLRGetTerminalFinalizerBoundaryVersion': '000008',
                  'AssemblyNative_InitializeInterpreterRequiredLoadContext': '000218180F18',
                  'AssemblyNative_InitializeInstructionMeteredLoadContext': '000318180A0F18',
                  'AssemblyNative_InitializeTerminalPrototypeLoadContext': '000418180A0A0F18'}
    for path, row in zip(stages, metadata):
        require(row['sha256'] == sha(path), 'PE inspector actual identity differs')
        methods = row['methods']
        outer = [m for m in methods if m['owner'] == 'System.Runtime.Loader.AssemblyLoadContext' and m['name'].startswith('RuneCLR_')]
        gc_methods = [m for m in methods if m['owner'] == 'System.GC' and m['name'].startswith('RuneCLR_')]
        require({m['name'] for m in outer} == required | meter | terminal
                and {m['name'] for m in gc_methods} == gc, 'Actual private bridge family stripped or changed')
        require(all('Private' in m['attributes'] for m in outer + gc_methods), 'Private API visibility changed')
        nested = [m for m in methods if m['owner'].endswith('+RuneCLRInterpreterLoadContext')]
        require({m['name'] for m in nested} == {'.ctor', 'Load', 'LoadUnmanagedDll'}
                and sorted(int(m['signatureHex'][2:4], 16) for m in nested if m['name'] == '.ctor') == [2, 3, 4], 'Actual nested context shape stripped')
        for entry, signature in signatures.items():
            require([m['signatureHex'] for m in methods if m['nativeEntry'] == entry] == [signature], 'Actual private QCall ABI differs: ' + entry)
        for entry, prefix in [('GCInterface_RuneCLRIsTerminatedFinalizerOwner', '00010511'), ('RuneCLRIsTerminatedFrameOwner', '0001050F11')]:
            found = [m for m in methods if m['nativeEntry'] == entry]
            require(len(found) == 1 and found[0]['signatureHex'].startswith(prefix), 'NoGC owner query ABI differs')
    require(metadata[1]['sha256'] == metadata[2]['sha256'], 'PostTrim/ProductIL disagree')
    descriptor = coreobj / 'ILLink.Descriptors.xml'
    descriptor_text = descriptor.read_text()
    roots = {n for n in required | meter | terminal if not n.endswith('Native')} | {'RuneCLR_GetTerminalFinalizerBoundaryVersion'}
    require(all('name="' + name + '"' in descriptor_text for name in roots), 'Actual generated roots missing')
    write(out / 'metadata-assessment.json', {'stages': metadata, 'command': command, 'metadataToolSha256': sha(args.metadata_tool),
          'descriptorSha256': sha(descriptor), 'executionVerified': False})
    return {'nativeCompileOwners': len(compiled), 'release': True, 'staticInterpreter': True,
            'dynamicJitEnabled': False, 'matchingGuid': True, 'corelibStages': 3,
            'policyFamily': 5, 'meterFamily': 8, 'terminalFamily': 12, 'gcFamily': 3, 'privateApisRetained': True}


def build(args):
    require(sys.platform == 'darwin' and args.build_slot_granted, 'Darwin exclusive heavy-build slot required')
    require(args.output.resolve().parent == args.root.resolve(), 'Fresh direct experiment child required')
    require(sha(args.source_proof) == PROOF_SHA, 'Frozen increment source proof differs')
    proof = read(args.source_proof)
    require(proof['tree'] == EXPECTED_TREE and proof['exactIncrementVerified'] and
            proof['oldMobileDeltaOnlyMeter'] and proof['windowsDeltaOnlyCID'] and
            proof['privateIndexCompositionVerified'] and len(proof['sourceHashes']) == 37,
            'Exact reviewed minimal mobile increment required')
    require(proof['base'] == BASE and proof['windowsCommit'] == WINDOWS_COMMIT and proof['patches'] == PATCHES, 'Independent source proof identity differs')
    TREE = proof['tree']
    require(len(TREE) == 40 and proof['sourceHashes'], 'Independent source tree/hashes missing')
    before = preserved(args.root.resolve())
    original = args.root.resolve() / 'runtime'
    if capture(['git', '-C', original, 'rev-parse', 'HEAD']) != BASE or not clean(original):
        raise RuntimeError('Unexpected or modified baseline source')
    for name, expected in PATCHES.items():
        if sha(args.patches / name) != expected:
            raise RuntimeError('Patch identity differs: ' + name)
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    args.created_output = True
    (out / 'source-proof.json').write_bytes(args.source_proof.read_bytes())
    (out / 'driver.py').write_bytes(Path(__file__).read_bytes())
    source = out / 'runtime'
    logs = out / 'logs'
    logs.mkdir()
    baseline_native = original / 'artifacts/bin/coreclr/iossimulator.arm64.Debug/libcoreclr.dylib'
    baseline_sha = sha(baseline_native)
    source_env = dict(os.environ)
    source_env.update({'GIT_AUTHOR_NAME': 'RuneCLR Experiment',
                       'GIT_AUTHOR_EMAIL': 'experiment@runeclr.invalid',
                       'GIT_COMMITTER_NAME': 'RuneCLR Experiment',
                       'GIT_COMMITTER_EMAIL': 'experiment@runeclr.invalid'})
    with (out / 'source-setup.log').open('w') as log:
        subprocess.run(['git', '-C', str(original), 'worktree', 'add', '--detach', str(source), BASE],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
        for name in PATCHES:
            subprocess.run(['git', '-C', str(source), '-c', 'core.autocrlf=false',
                            'apply', '--check', str((args.patches / name).resolve())],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
            subprocess.run(['git', '-C', str(source), '-c', 'core.autocrlf=false',
                            'apply', '--index', str((args.patches / name).resolve())],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        if capture(['git', '-C', source, 'write-tree']) != TREE:
            raise RuntimeError('Combined tree differs from independently reviewed source')
        changed = capture(['git', '-C', source, 'diff', '--cached', '--name-only', BASE]).splitlines()
        actual_hashes = {name: sha(source / name) for name in changed}
        require(actual_hashes == proof['sourceHashes'], 'Combined file set or source hashes differ from root independent proof')
        subprocess.run(['git', '-C', str(source), 'commit', '-m',
                        'Private experiment: terminal counter increment plus CID v2'],
                       env=source_env, stdout=log, stderr=subprocess.STDOUT, check=True)
    commit = capture(['git', '-C', source, 'rev-parse', 'HEAD'])
    changed = capture(['git', '-C', source, 'diff', '--name-only', BASE]).splitlines()
    diff = subprocess.check_output(['git', '-C', str(source), 'diff', BASE])
    (logs / 'runtime.patch').write_bytes(diff)
    write(out / 'source.json', {'base': BASE, 'commit': commit, 'tree': TREE,
          'branch': 'detached', 'configuration': 'iossimulator.arm64.Release',
          'patches': PATCHES, 'combinedPatchSha256': sha(logs / 'runtime.patch'),
          'sourceHashes': {name: sha(source / name) for name in changed},
          'trackedClean': clean(source), 'windowsCommit': WINDOWS_COMMIT, 'sourceProofSha256': sha(args.source_proof),
          'description': 'Windows204 minimal terminal counter increment plus only CID v2 publication guard'})
    if (source / 'artifacts').exists():
        raise RuntimeError('Fresh worktree unexpectedly contains build artifacts')
    sdk = original / '.dotnet'
    sdk_version = capture([sdk / 'dotnet', '--version'])
    if sdk_version != '11.0.100-rc.1.26420.103':
        raise RuntimeError('Unexpected source-build SDK')
    subprocess.run(['cp', '-cR', str(sdk), str(source / '.dotnet')], check=True)
    if capture([source / '.dotnet/dotnet', '--version']) != sdk_version:
        raise RuntimeError('Private SDK clone differs')
    command = ['./build.sh', 'clr.runtime+clr.native+clr.corelib+clr.tools+clr.crossarchtools',
               '-os', 'iossimulator', '-arch', 'arm64', '-cross', '-c', 'Release',
               '-clrinterpreter', '-ninja', '-cmakeargs', '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.3', '/m:1']
    env = dict(os.environ)
    removed = {}
    for key in ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH', 'LIBRARY_PATH',
                'SDKROOT', 'MACOSX_DEPLOYMENT_TARGET', 'CMAKE_PREFIX_PATH', 'PKG_CONFIG_PATH'):
        if key in env: removed[key] = env.pop(key)
    env.update({'PATH': str(args.root / 'tools/bin') + ':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                'CMAKE_PREFIX_PATH': str(args.root / 'tools/icu'),
                'PKG_CONFIG_PATH': str(args.root / 'tools/icu/lib/pkgconfig'),
                'DOTNET_CLI_HOME': str(out / 'dotnet-home'),
                'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1',
                'MSBUILDDISABLENODEREUSE': '1', 'DOTNET_CLI_USE_MSBUILD_SERVER': '0',
                'CMAKE_BUILD_PARALLEL_LEVEL': '2'})
    write(out / 'request.json', {'base': BASE, 'commit': commit, 'tree': TREE,
          'target': 'iossimulator.arm64', 'configuration': 'Release',
          'source': str(source), 'sdkVersion': sdk_version, 'command': command,
          'cleanBuildObjects': True, 'reuse': 'Only fixed SDK APFS clone; no native/managed artifacts',
          'driverSha256': sha(__file__), 'parentDriverSha256': PARENT_DRIVER_SHA256, 'sourceProofSha256': sha(args.source_proof),
          'metadataToolSha256': sha(args.metadata_tool), 'windowsCommit': WINDOWS_COMMIT,
          'preservedBeforeHashes': before, 'sanitizedEnvironmentKeys': sorted(removed),
          'globalEnvironmentChanged': False, 'baselineNativeBeforeSha256': baseline_sha,
          'startedUtc': utc()})
    with (out / 'build.log').open('w') as log:
        status = subprocess.run(command, cwd=source, env=env, stdout=log,
                                stderr=subprocess.STDOUT).returncode
    (out / 'build.exit').write_text(str(status) + chr(10))
    product = source / 'artifacts/bin/coreclr/iossimulator.arm64.Release'
    native = product / 'libcoreclr.dylib'
    corelib = product / 'IL/System.Private.CoreLib.dll'
    compiler = product / 'arm64/crossgen2/crossgen2'
    artifacts = []
    for pattern in ['**/System.Private.CoreLib.dll', '**/crossgen2', '**/libcoreclr.dylib*',
                    '**/libclrjit*.dylib', '**/libjitinterface*.dylib']:
        for path in sorted(product.glob(pattern)):
            if path.is_file():
                artifacts.append({'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size})
    write(out / 'artifacts.json', artifacts)
    unchanged = sha(baseline_native) == baseline_sha and preserved(args.root.resolve()) == before
    tracked_clean = clean(source)
    assessment = None
    if status == 0 and unchanged and tracked_clean and all(p.is_file() for p in [native, corelib, compiler]):
        assessment = assess_product(source, product, out, args, commit)
    result = {'success': status == 0 and unchanged and tracked_clean and assessment is not None
                        and all(p.is_file() for p in [native, corelib, compiler]),
              'buildExit': status, 'base': BASE, 'commit': commit, 'tree': TREE,
              'target': 'iossimulator.arm64', 'configuration': 'Release',
              'sourceTrackedClean': tracked_clean, 'baselineNativeUnchanged': unchanged,
              'native': str(native), 'corelib': str(corelib), 'crossgen2': str(compiler),
              'nativeSha256': sha(native) if native.exists() else None,
              'corelibSha256': sha(corelib) if corelib.exists() else None,
              'crossgen2Sha256': sha(compiler) if compiler.exists() else None,
              'windowsCommit': WINDOWS_COMMIT, 'assessment': assessment,
              'sourceProofSha256': sha(args.source_proof), 'preservedAfterHashes': preserved(args.root.resolve()),
              'endedUtc': utc(), 'executionVerified': False}
    write(out / 'results.json', result)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result['success'] else status or 1

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['root', 'output', 'patches', 'source-proof', 'metadata-tool']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--build-slot-granted', action='store_true')
    args = parser.parse_args()
    try:
        return build(args)
    except Exception:
        if getattr(args, 'created_output', False):
            failure = args.output / 'driver-failure.txt'
            if not failure.exists():
                failure.write_text(traceback.format_exc())
            result = args.output / 'results.json'
            if not result.exists():
                write(result, {'success': False, 'executionVerified': False,
                      'failure': str(failure), 'buildExit': (args.output / 'build.exit').read_text().strip()
                      if (args.output / 'build.exit').is_file() else None, 'endedUtc': utc()})
        raise

if __name__ == '__main__':
    raise SystemExit(main())
