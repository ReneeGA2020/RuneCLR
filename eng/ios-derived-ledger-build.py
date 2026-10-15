#!/usr/bin/env python3
"""Build exact Windows29ff plus CIDv2 in a fresh iOS ARM64 simulator worktree."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
import traceback

BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
WINDOWS_COMMIT = '29ff781e157be82ba5a398a60bb05291e4a865af'
COMMIT = '2d86588f8cef4b3c48ce2ba4d4af15ad7bc83e7c'
TREE = '3292fc9acf3c15632f3bde34f675caec44f399e2'
PROOF_SHA = 'c860e8c483347c8b552b5128d7a5a28f6fe69bef4eb32a2426337a736fddca97'
BUNDLE_SHA = '9e000820efff8c0c41e4ccbb15d01c2afa996ddd7d6ba74f1ef95a8ce82fe843'
PARENT_SHA = '3ed2bae44ba4d9f8e021b554d0702671a7b2671a6157a39b18521dd9453aa613'
SDK_VERSION = '11.0.100-rc.1.26420.103'
PATCHES = {
    '0001-collectible-cid-publication.patch': '43b36606fa94967e97f2640e8d76dcfa8f0af21eeb77a065a0eea5c83c915857',
    '0003-collectible-interpreter-selection.patch': 'b7d446243a099c6fc01c19bdc6e83c151eb4771112001fd9bd7185a0d1950ccb',
    '0004-interpreter-required-load-context.patch': '714ba322b3df83ccb3feb5b91043b779e4c75b212ea9d4dbf95db06c0e330657',
    '0005-native-session-instruction-meter.patch': '5ecb5d595aba473c5709d8b172821ae7de228ee7705f140535df3b890ea7ec94',
    '0006-session-terminal-prototype.patch': '3acec56c4fb1946d38ff324d30b5bb7ee8220d1ab66439c5352c031cbb042d76',
    '0007-session-terminal-finalizer-boundary.patch': 'c21c940db0f5041f3e681d4bafafbc555f51412f2c9a188c142981af27c468ef',
    '0008-terminal-counter-increment.patch': 'a1bbecff236c5484a35e9c79643bd5c572e34a0eda8e843904c54bd31d04f108',
    'phase-load/0009-terminal-phase-acquire-load.patch': '9135972d74a95dff08c72dd349bb0fda6f533e0a2885373d71a539f589e6ae87',
    'derived-ledger/0010-terminal-derived-ledger.patch': '6055066b679d90b8475f3da92775d4b2aedc690a95bfbc9932be7a7884fb5c3b',
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def capture(argv):
    return subprocess.check_output([str(a) for a in argv], text=True).strip()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + chr(10), encoding='ascii')


def clean(source):
    return not capture(['git', '-C', source, 'status', '--porcelain', '--untracked-files=no'])


def inventory(root):
    return {path.relative_to(root).as_posix(): sha(path) for path in root.rglob('*') if path.is_file()}


def frozen_proof(args):
    require(sha(args.source_proof) == PROOF_SHA and sha(args.source_bundle) == BUNDLE_SHA,
            'Exact independently reviewed proof/bundle bytes required')
    proof = json.loads(args.source_proof.read_text())
    for key, expected in {'schema': 'runeclr.mobile-derived-ledger.source-proof.v1', 'base': BASE,
                          'windowsCommit': WINDOWS_COMMIT, 'sourceCommit': COMMIT, 'tree': TREE,
                          'changedFileCount': 37, 'privateIndexCompositionVerified': True,
                          'windowsDeltaOnlyCID': True, 'oldMobileDeltaOnlyMeterConfig': True,
                          'exactDerivedLedgerVerified': True, 'phaseAcquireLoadDefaultOff': True,
                          'terminalDerivedLedgerDefaultOff': True, 'phaseAndDerivedSwitchesIndependent': True,
                          'layoutSize': 64, 'layoutAlignment': 8, 'phaseFlagOffset': 2, 'derivedFlagOffset': 3}.items():
        require(proof.get(key) == expected, 'Exact derived-ledger proof field differs: ' + key)
    require(proof['patches'] == PATCHES and len(proof['sourceHashes']) == 37, 'Exact nine-patch/37-file proof required')
    for relative, expected in PATCHES.items():
        require(sha(args.patches / relative) == expected, 'Frozen patch differs: ' + relative)
    require(sha(args.parent_driver) == PARENT_SHA, 'Frozen original iOS native/CoreLib assessor differs')
    return proof


def preserved(root):
    paths = [root / 'runtime/artifacts/bin/coreclr/iossimulator.arm64.Debug/libcoreclr.dylib']
    for child, target in [('ios-session-policy-release-20261013', 'iossimulator.arm64.Release'),
                          ('ios-budget-increment-release-20261014-attempt1', 'iossimulator.arm64.Release'),
                          ('android-budget-increment-release-20261014-attempt1', 'android.x64.Release')]:
        source = root / child / 'runtime'
        require(clean(source), 'Older mobile source became tracked-dirty: ' + child)
        product = source / 'artifacts/bin/coreclr' / target
        native = 'libcoreclr.so' if target.startswith('android') else 'libcoreclr.dylib'
        compilers = [path for path in product.glob('**/crossgen2') if path.is_file()]
        require(len(compilers) == 1, 'Unique older Mac-host compiler required: ' + child)
        paths.extend([product / native, product / 'IL/System.Private.CoreLib.dll', compilers[0]])
    return {str(path): sha(path) for path in paths}


def environment(root):
    commands = [['uname', '-a'], ['xcodebuild', '-version'], ['xcode-select', '-p'],
                ['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'],
                ['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version'], ['xcrun', 'clang', '--version']]
    outputs = {' '.join(command): capture(command) for command in commands}
    compiler = Path(capture(['xcrun', '--find', 'clang']))
    build_path = str(root / 'tools/bin') + ':/opt/homebrew/bin:/usr/bin:/bin'
    cmake_name = shutil.which('cmake', path=build_path)
    ninja = shutil.which('ninja', path=build_path)
    require(cmake_name is not None and ninja is not None and compiler.is_file(), 'Actual compiler/CMake/Ninja required')
    cmake = Path(cmake_name)
    return {'commands': outputs, 'compiler': str(compiler), 'compilerSha256': sha(compiler),
            'cmake': str(cmake), 'cmakeSha256': sha(cmake), 'ninja': ninja, 'ninjaSha256': sha(ninja)}


def source_identity(source, proof):
    require(capture(['git', '-C', source, 'rev-parse', 'HEAD']) == COMMIT and clean(source), 'Exact committed clean mobile source required')
    require(capture(['git', '-C', source, 'rev-parse', 'HEAD^{tree}']) == TREE, 'Exact committed mobile tree differs')
    changed = capture(['git', '-C', source, 'diff', '--name-only', BASE, COMMIT]).splitlines()
    actual = {relative: sha(source / relative) for relative in changed}
    require(actual == proof['sourceHashes'], 'Actual 37 LF worktree sources differ from independent proof')
    for relative, expected in actual.items():
        blob = subprocess.check_output(['git', '-C', str(source), 'show', COMMIT + ':' + relative])
        require(hashlib.sha256(blob).hexdigest() == expected and (source / relative).read_bytes() == blob,
                'Actual source differs from exact Git blob: ' + relative)
    return actual


def build(args):
    require(sys.platform == 'darwin' and args.build_slot_granted, 'Darwin exclusive heavy-build slot required')
    args.root = args.root.resolve(); args.output = args.output.resolve()
    require(args.output.parent == args.root and not args.output.exists(), 'Fresh direct experiment child required')
    proof = frozen_proof(args)
    original = args.root / 'runtime'
    require(capture(['git', '-C', original, 'rev-parse', 'HEAD']) == BASE and clean(original), 'Unchanged official baseline required')
    original_status = capture(['git', '-C', original, 'status', '--porcelain'])
    before = preserved(args.root)
    before_environment = environment(args.root)
    sdk = original / '.dotnet'
    require(capture([sdk / 'dotnet', '--version']) == SDK_VERSION, 'Exact private source-build SDK required')
    sdk_inventory = inventory(sdk)
    args.output.mkdir(); args.created_output = True
    out = args.output; source = out / 'runtime'
    for path, name in [(args.source_proof, 'source-proof.json'), (args.source_bundle, 'runtime.bundle'),
                       (args.parent_driver, 'parent-driver.py'), (Path(__file__), 'driver.py')]:
        shutil.copyfile(path, out / name)
    write(out / 'environment.json', before_environment)
    write(out / 'sdk-source-inventory.json', sdk_inventory)
    with (out / 'source-setup.log').open('w') as log:
        subprocess.run(['git', '-C', str(original), 'bundle', 'verify', str(args.source_bundle.resolve())], stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run(['git', '-C', str(original), 'bundle', 'unbundle', str(args.source_bundle.resolve())], stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run(['git', '-C', str(original), 'worktree', 'add', '--detach', str(source), COMMIT], stdout=log, stderr=subprocess.STDOUT, check=True)
    source_hashes = source_identity(source, proof)
    require(not (source / 'artifacts').exists() and not (source / '.dotnet').exists(), 'Fresh source unexpectedly contains build outputs or private SDK')
    write(out / 'source.json', {'base': BASE, 'windowsCommit': WINDOWS_COMMIT, 'commit': COMMIT, 'tree': TREE,
          'branch': 'detached', 'configuration': 'iossimulator.arm64.Release', 'patches': PATCHES,
          'sourceHashes': source_hashes, 'trackedClean': True, 'sourceProofSha256': PROOF_SHA,
          'bundleSha256': BUNDLE_SHA, 'nativeMeterSize': 64, 'nativeMeterAlignment': 8,
          'scope': 'Actual committed 37 LF Git/worktree sources; header compile layout assertions remain in actual product builds.'})
    subprocess.run(['cp', '-cR', str(sdk), str(source / '.dotnet')], check=True)
    require(inventory(source / '.dotnet') == sdk_inventory, 'Actual private SDK clone inventory differs')
    command = ['./build.sh', 'clr.runtime+clr.native+clr.corelib+clr.tools+clr.crossarchtools',
               '-os', 'iossimulator', '-arch', 'arm64', '-cross', '-c', 'Release', '-clrinterpreter',
               '-ninja', '-cmakeargs', '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.3', '/m:1']
    env = dict(os.environ)
    removed = {}
    for key in list(env):
        if key.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_')) or key in ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH',
            'OBJC_INCLUDE_PATH', 'LIBRARY_PATH', 'SDKROOT', 'MACOSX_DEPLOYMENT_TARGET', 'CMAKE_PREFIX_PATH', 'PKG_CONFIG_PATH'):
            removed[key] = env.pop(key)
    env.update({'PATH': str(args.root / 'tools/bin') + ':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                'CMAKE_PREFIX_PATH': str(args.root / 'tools/icu'), 'PKG_CONFIG_PATH': str(args.root / 'tools/icu/lib/pkgconfig'),
                'DOTNET_CLI_HOME': str(out / 'dotnet-home'), 'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1',
                'MSBUILDDISABLENODEREUSE': '1', 'DOTNET_CLI_USE_MSBUILD_SERVER': '0', 'CMAKE_BUILD_PARALLEL_LEVEL': '2'})
    write(out / 'request.json', {'base': BASE, 'commit': COMMIT, 'tree': TREE, 'windowsCommit': WINDOWS_COMMIT,
          'target': 'iossimulator.arm64', 'configuration': 'Release', 'source': str(source), 'sdkVersion': SDK_VERSION,
          'command': command, 'cleanBuildObjects': True, 'reuse': 'Only fixed SDK APFS clone; no native/managed artifacts',
          'driverSha256': sha(__file__), 'parentDriverSha256': PARENT_SHA, 'sourceProofSha256': PROOF_SHA,
          'bundleSha256': BUNDLE_SHA, 'metadataToolSha256': sha(args.metadata_tool), 'sdkInventorySha256': sha(out / 'sdk-source-inventory.json'),
          'environmentSha256': sha(out / 'environment.json'), 'preservedBeforeHashes': before,
          'sanitizedEnvironmentKeys': sorted(removed), 'globalEnvironmentChanged': False, 'meterSize': 64,
          'startedUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'executionVerified': False})
    with (out / 'build.log').open('w') as log:
        child = subprocess.Popen(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
        write(out / 'build-process.json', {'pid': child.pid, 'driverPid': os.getpid(), 'command': command, 'source': str(source)})
        status = child.wait()
    (out / 'build.exit').write_text(str(status) + chr(10))
    require(status == 0, 'Fresh iOS runtime build failed; original output preserved')
    require(preserved(args.root) == before and inventory(sdk) == sdk_inventory, 'Older mobile products or source SDK changed')
    require(capture(['git', '-C', original, 'status', '--porcelain']) == original_status, 'Original checkout/index/status changed')
    require(environment(args.root) == before_environment, 'Compiler/Xcode/CMake/Ninja environment changed')
    require(source_identity(source, proof) == source_hashes, 'Actual mobile sources changed during build')
    product = source / 'artifacts/bin/coreclr/iossimulator.arm64.Release'
    spec = importlib.util.spec_from_file_location('frozen_original_ios_assessor', out / 'parent-driver.py')
    parent = importlib.util.module_from_spec(spec); spec.loader.exec_module(parent)
    assessment = parent.assess_product(source, product, out, args, COMMIT)
    native, corelib, compiler = product / 'libcoreclr.dylib', product / 'IL/System.Private.CoreLib.dll', product / 'arm64/crossgen2/crossgen2'
    artifacts = []
    for pattern in ['**/System.Private.CoreLib.dll', '**/crossgen2', '**/libcoreclr.dylib*', '**/libclrjit*.dylib', '**/libjitinterface*.dylib']:
        for path in sorted(product.glob(pattern)):
            if path.is_file(): artifacts.append({'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size})
    write(out / 'artifacts.json', artifacts)
    result = {'success': True, 'buildExit': status, 'base': BASE, 'commit': COMMIT, 'tree': TREE,
              'windowsCommit': WINDOWS_COMMIT, 'target': 'iossimulator.arm64', 'configuration': 'Release',
              'sourceTrackedClean': True, 'baselineNativeUnchanged': True, 'preservedAfterHashes': preserved(args.root),
              'native': str(native), 'corelib': str(corelib), 'crossgen2': str(compiler), 'nativeSha256': sha(native),
              'corelibSha256': sha(corelib), 'crossgen2Sha256': sha(compiler), 'assessment': assessment,
              'sourceProofSha256': PROOF_SHA, 'bundleSha256': BUNDLE_SHA, 'parentDriverSha256': PARENT_SHA,
              'nativeMeterSize': 64, 'nativeMeterAlignment': 8, 'executionVerified': False,
              'endedUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    write(out / 'results.json', result)
    print(json.dumps(result, indent=2), flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['root', 'output', 'patches', 'source-proof', 'source-bundle', 'parent-driver', 'metadata-tool']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--build-slot-granted', action='store_true')
    args = parser.parse_args()
    try:
        return build(args)
    except Exception:
        if getattr(args, 'created_output', False):
            (args.output / 'driver-failure.txt').write_text(traceback.format_exc())
            write(args.output / 'results.json', {'success': False, 'executionVerified': False,
                  'buildExit': (args.output / 'build.exit').read_text().strip() if (args.output / 'build.exit').exists() else None,
                  'failure': str(args.output / 'driver-failure.txt'), 'endedUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
        raise


if __name__ == '__main__':
    raise SystemExit(main())
