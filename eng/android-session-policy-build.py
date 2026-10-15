#!/usr/bin/env python3
"""Build matching Android session-policy inputs in a fresh isolated worktree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import traceback

BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
COMMIT = '1724cdec553a7aff7a373a271a4be612651c7625'
TREE = '71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2'


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def capture(command):
    return subprocess.check_output([str(arg) for arg in command], text=True).strip()


def clean(source):
    return not capture(['git', '-C', source, 'status', '--porcelain', '--untracked-files=no'])


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + chr(10))


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def build(args):
    root, out = args.root.resolve(), args.output.resolve()
    configuration = args.configuration
    original = root / 'runtime'
    accepted = root / 'ios-session-policy-release-20261013'
    provenance = json.loads((accepted / 'source.json').read_text())
    ndk_receipt = json.loads((args.toolchain / 'results.json').read_text())
    assert provenance['commit'] == COMMIT and provenance['tree'] == TREE
    assert ndk_receipt['success'] and ndk_receipt['clangExecutableVerified']
    ndk = Path(ndk_receipt['ndk'])
    assert sha(ndk / 'build/cmake/android.toolchain.cmake') == ndk_receipt['toolchainSha256']
    assert capture(['git', '-C', original, 'rev-parse', 'HEAD']) == BASE and clean(original)
    assert capture(['git', '-C', original, 'rev-parse', COMMIT + '^{tree}']) == TREE
    baseline_native = original / 'artifacts/bin/coreclr/iossimulator.arm64.Debug/libcoreclr.dylib'
    baseline_hash = sha(baseline_native)
    out.relative_to(root)
    out.mkdir(exist_ok=False)
    source = out / 'runtime'
    with (out / 'source-setup.log').open('w') as log:
        subprocess.run(['git', '-C', str(original), 'worktree', 'add', '--detach',
                        str(source), COMMIT], stdout=log, stderr=subprocess.STDOUT, check=True)
    assert not (source / 'artifacts').exists()
    hashes = {name: sha(source / name) for name in provenance['sourceHashes']}
    assert hashes == provenance['sourceHashes'] and clean(source)
    write(out / 'source.json', {'base': BASE, 'commit': COMMIT, 'tree': TREE,
          'configuration': 'android.x64.' + configuration, 'branch': 'detached',
          'sourceHashes': hashes, 'trackedClean': True,
          'acceptedSourceReceiptSha256': sha(accepted / 'source.json'),
          'patches': provenance['patches'], 'description': 'Exact reviewed combined source; no platform source edits'})
    sdk_version = capture([original / '.dotnet/dotnet', '--version'])
    assert sdk_version == '11.0.100-rc.1.26420.103'
    subprocess.run(['cp', '-cR', str(original / '.dotnet'), str(source / '.dotnet')], check=True)
    assert capture([source / '.dotnet/dotnet', '--version']) == sdk_version
    command = ['./build.sh', 'clr.runtime+clr.native+clr.corelib+clr.tools+clr.crossarchtools',
               '-os', 'android', '-arch', 'x64', '-cross', '-c', 'Release',
               '-rc', configuration, '-lc', 'Release', '-clrinterpreter', '-ninja', '/m:1']
    env = dict(os.environ)
    removed_environment = {name: env.pop(name) for name in
        ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH',
         'LIBRARY_PATH', 'SDKROOT', 'MACOSX_DEPLOYMENT_TARGET', 'CMAKE_PREFIX_PATH',
         'PKG_CONFIG_PATH') if name in env}
    env.update({'PATH': str(root / 'tools/bin') + ':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                'ANDROID_NDK_ROOT': str(ndk), 'ANDROID_NDK_HOME': str(ndk),
                'DOTNET_CLI_HOME': str(out / 'dotnet-home'),
                'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1',
                'MSBUILDDISABLENODEREUSE': '1', 'DOTNET_CLI_USE_MSBUILD_SERVER': '0',
                'CMAKE_BUILD_PARALLEL_LEVEL': '2'})
    write(out / 'request.json', {'base': BASE, 'commit': COMMIT, 'tree': TREE,
          'target': 'android.x64', 'configuration': configuration, 'frameworkConfiguration': 'Release',
          'source': str(source), 'sdkVersion': sdk_version, 'command': command,
          'interpreterExplicitlyRequested': True, 'cleanBuildObjects': True,
          'reuse': 'Fixed SDK APFS clone only; no native/managed artifacts',
          'toolchainReceiptSha256': sha(args.toolchain / 'results.json'),
          'ndk': str(ndk), 'ndkVersion': '27.2.12479018',
          'driverSha256': sha(Path(__file__)), 'baselineNativeBeforeSha256': baseline_hash,
          'removedCrossCompilationEnvironment': removed_environment,
          'globalEnvironmentChanged': False,
          'startedUtc': utc(), 'executionVerified': False})
    with (out / 'build.log').open('w') as log:
        status = subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    (out / 'build.exit').write_text(str(status) + chr(10))
    product = source / ('artifacts/bin/coreclr/android.x64.' + configuration)
    natives = [product / name for name in ('libcoreclr.so', 'libclrinterpreter.so', 'libclrjit.so')]
    corelib = product / 'IL/System.Private.CoreLib.dll'
    compilers = list(product.glob('**/crossgen2'))
    compilers = [path for path in compilers if path.is_file()]
    compiler = compilers[0] if len(compilers) == 1 else None
    files = []
    for pattern in ('**/System.Private.CoreLib.dll', '**/crossgen2', '**/libcoreclr.so*',
                    '**/libclrinterpreter.so*', '**/libclrjit*', '**/libjitinterface*'):
        for path in sorted(product.glob(pattern)):
            if path.is_file():
                files.append({'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size})
    write(out / 'artifacts.json', files)
    unchanged, tracked_clean = sha(baseline_native) == baseline_hash, clean(source)
    result = {'success': status == 0 and unchanged and tracked_clean and
                        all(path.is_file() for path in [*natives, corelib]) and compiler is not None,
              'buildExit': status, 'base': BASE, 'commit': COMMIT, 'tree': TREE,
              'target': 'android.x64', 'configuration': configuration,
              'frameworkConfiguration': 'Release', 'sourceTrackedClean': tracked_clean,
              'baselineNativeUnchanged': unchanged, 'native': str(natives[0]),
              'interpreter': str(natives[1]), 'targetJit': str(natives[2]),
              'corelib': str(corelib), 'crossgen2': str(compiler) if compiler else None,
              'nativeSha256': sha(natives[0]) if natives[0].exists() else None,
              'corelibSha256': sha(corelib) if corelib.exists() else None,
              'crossgen2Sha256': sha(compiler) if compiler else None,
              'endedUtc': utc(), 'executionVerified': False,
              'frameworkComplete': False, 'scope': 'CoreCLR/CoreLib/compiler prerequisites; framework and APK are separate stages'}
    write(out / 'results.json', result)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result['success'] else status or 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'output', 'toolchain'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--configuration', choices=('Checked', 'Release'), default='Checked')
    args = parser.parse_args()
    try:
        return build(args)
    except Exception:
        if args.output.is_dir():
            write(args.output / 'driver-failure.json', {'error': traceback.format_exc(), 'executionVerified': False})
        raise


if __name__ == '__main__':
    raise SystemExit(main())
