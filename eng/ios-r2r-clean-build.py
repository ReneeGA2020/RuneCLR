#!/usr/bin/env python3
"""Build the pinned CID candidate natively in a fresh private runtime worktree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
CANDIDATE = '8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def capture(arguments):
    return subprocess.check_output([str(a) for a in arguments], text=True).strip()


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--configuration', choices=['Debug', 'Checked', 'Release'], default='Debug')
    parser.add_argument('--complete-native', action='store_true',
                        help='Finish a preserved failed clean build with all native dependency targets')
    args = parser.parse_args()
    original = args.root / 'runtime'
    candidate = args.root / 'ios-r2r-fix-v2-20261012/runtime'
    for checkout, expected in [(original, BASE), (candidate, CANDIDATE)]:
        if capture(['git', '-C', checkout, 'rev-parse', 'HEAD']) != expected:
            raise RuntimeError('Unexpected runtime source revision')
        if capture(['git', '-C', checkout, 'status', '--porcelain', '--untracked-files=no']):
            raise RuntimeError('Tracked runtime changes must be preserved; refusing build')
    out = args.output.resolve()
    source = out / 'runtime'
    prefix = 'native-completion-' if args.complete_native else ''
    if args.complete_native:
        previous = json.loads((out / 'results.json').read_text())
        request = json.loads((out / 'request.json').read_text())
        if previous['buildExit'] == 0 or not request['cleanNativeObjects']:
            raise RuntimeError('Completion requires a preserved failed clean-native attempt')
        if request['configuration'] != args.configuration:
            raise RuntimeError('Completion must retain the original build configuration')
        if (out / (prefix + 'request.json')).exists():
            raise RuntimeError('Preserve an existing completion attempt')
        if capture(['git', '-C', source, 'rev-parse', 'HEAD']) != CANDIDATE:
            raise RuntimeError('Preserved source revision differs')
        if capture(['git', '-C', source, 'status', '--porcelain', '--untracked-files=no']):
            raise RuntimeError('Preserved source has tracked changes')
        sdk_version = capture([source / '.dotnet/dotnet', '--version'])
    else:
        out.mkdir(exist_ok=False)
        subprocess.run(['git', '-C', str(original), 'worktree', 'add', '--detach',
                        str(source), CANDIDATE], check=True)
        # Clone only the fixed SDK. Native objects and generated headers start empty.
        sdk = original / '.dotnet'
        if not sdk.is_dir():
            raise RuntimeError('The recorded private source SDK is missing')
        sdk_version = capture([sdk / 'dotnet', '--version'])
        subprocess.run(['cp', '-cR', str(sdk), str(source / '.dotnet')], check=True)
        if capture([source / '.dotnet/dotnet', '--version']) != sdk_version:
            raise RuntimeError('Private SDK clone differs')
        if (source / 'artifacts').exists():
            raise RuntimeError('Clean native build requires no previous artifacts')
    baseline_native = original / 'artifacts/bin/coreclr/iossimulator.arm64.Debug/libcoreclr.dylib'
    original_hash = sha(baseline_native)
    command = ['./build.sh', 'clr.runtime+clr.native', '-os', 'iossimulator', '-arch', 'arm64',
               '-cross', '-c', args.configuration, '-ninja',
               '-cmakeargs', '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.3', '/m:1']
    env = dict(os.environ)
    env.update({'PATH': str(args.root / 'tools/bin') + ':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                'CMAKE_PREFIX_PATH': str(args.root / 'tools/icu'),
                'PKG_CONFIG_PATH': str(args.root / 'tools/icu/lib/pkgconfig'),
                'DOTNET_CLI_HOME': str(out / 'dotnet-home'),
                'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1',
                'CMAKE_BUILD_PARALLEL_LEVEL': '4'})
    write(out / (prefix + 'request.json'), {'base': BASE, 'commit': CANDIDATE,
          'configuration': args.configuration, 'target': 'iossimulator.arm64',
          'sdkVersion': sdk_version, 'command': command,
          'cleanNativeObjects': not args.complete_native,
          'completesFailedCleanBuild': args.complete_native,
          'driverSha256': sha(__file__),
          'startedUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
          'baselineNativeSha256': original_hash})
    with (out / (prefix + 'build.log')).open('w') as log:
        status = subprocess.run(command, cwd=source, env=env, stdout=log,
                                stderr=subprocess.STDOUT).returncode
    (out / (prefix + 'build.exit')).write_text(str(status) + '\n')
    native = source / ('artifacts/bin/coreclr/iossimulator.arm64.' + args.configuration) / 'libcoreclr.dylib'
    unchanged = sha(baseline_native) == original_hash
    clean = not capture(['git', '-C', source, 'status', '--porcelain', '--untracked-files=no'])
    write(out / (prefix + 'results.json'), {'buildExit': status, 'baselineNativeUnchanged': unchanged,
          'candidateTrackedClean': clean, 'native': str(native),
          'nativeSha256': sha(native) if native.exists() else None,
          'endedUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    if not unchanged or not clean:
        raise RuntimeError('Build isolation verification failed')
    if status == 0:
        logs = out / 'logs'
        logs.mkdir()
        patch = capture(['git', '-C', source, 'diff', BASE])
        (logs / 'runtime.patch').write_text(patch + chr(10))
        write(logs / 'source.json', {'base': BASE, 'commit': CANDIDATE,
              'branch': 'detached', 'configuration': 'iossimulator.arm64.' + args.configuration,
              'patchSha256': sha(logs / 'runtime.patch'), 'defaultBehavior': True,
              'diagnosticSwitchRequired': False, 'dynamicInterfaceReceiverGuard': True})
        write(logs / 'artifacts.json', {'libcoreclr': str(native),
              'libcoreclrSha256': sha(native), 'baselineNativeUnchanged': unchanged,
              'reuse': 'Private SDK clone only; fresh native objects and generated headers'})
    return status


if __name__ == '__main__':
    raise SystemExit(main())
