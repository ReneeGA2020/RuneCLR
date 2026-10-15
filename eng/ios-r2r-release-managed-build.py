#!/usr/bin/env python3
"""Build matching Release CoreLib and host tools beside a preserved native build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
CANDIDATE = '8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d'
NATIVE_SHA = '8ed0a3cae73584f69f59ab43020b3d6a5ae17be9ce9a0f74b7099cffbbfd1a8e'


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
    args = parser.parse_args()
    native_stage = args.root / 'ios-r2r-clean-release-20261012'
    source = native_stage / 'runtime'
    baseline = args.root / 'runtime'
    for checkout, expected in [(baseline, BASE), (source, CANDIDATE)]:
        if capture(['git', '-C', checkout, 'rev-parse', 'HEAD']) != expected:
            raise RuntimeError('Unexpected runtime source revision')
        if capture(['git', '-C', checkout, 'status', '--porcelain', '--untracked-files=no']):
            raise RuntimeError('Tracked runtime changes must be preserved')
    receipt = json.loads((native_stage / 'configuration-verified.json').read_text())
    if not receipt.get('success'):
        raise RuntimeError('Completed native configuration receipt is required')
    product = source / 'artifacts/bin/coreclr/iossimulator.arm64.Release'
    native = product / 'libcoreclr.dylib'
    baseline_native = baseline / 'artifacts/bin/coreclr/iossimulator.arm64.Debug/libcoreclr.dylib'
    if sha(native) != NATIVE_SHA:
        raise RuntimeError('Preserved Release native hash differs')
    original_hash = sha(baseline_native)
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    command = ['./build.sh', 'clr.corelib+clr.tools+clr.crossarchtools',
               '-os', 'iossimulator', '-arch', 'arm64', '-cross', '-c', 'Release',
               '-ninja', '-cmakeargs', '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.3', '/m:1']
    env = dict(os.environ)
    env.update({'PATH': str(args.root / 'tools/bin') + ':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                'CMAKE_PREFIX_PATH': str(args.root / 'tools/icu'),
                'PKG_CONFIG_PATH': str(args.root / 'tools/icu/lib/pkgconfig'),
                'DOTNET_CLI_HOME': str(out / 'dotnet-home'),
                'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1',
                'CMAKE_BUILD_PARALLEL_LEVEL': '4'})
    write(out / 'request.json', {'base': BASE, 'commit': CANDIDATE,
          'configuration': 'Release', 'target': 'iossimulator.arm64',
          'sdkVersion': capture([source / '.dotnet/dotnet', '--version']),
          'command': command, 'source': str(source), 'driverSha256': sha(__file__),
          'nativeReceiptSha256': sha(native_stage / 'configuration-verified.json'),
          'nativeBeforeSha256': NATIVE_SHA, 'baselineNativeBeforeSha256': original_hash,
          'startedUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    with (out / 'build.log').open('w') as log:
        status = subprocess.run(command, cwd=source, env=env, stdout=log,
                                stderr=subprocess.STDOUT).returncode
    (out / 'build.exit').write_text(str(status) + '\n')
    corelib = product / 'IL/System.Private.CoreLib.dll'
    crossgen = product / 'arm64/crossgen2/crossgen2'
    native_after = sha(native)
    baseline_after = sha(baseline_native)
    clean = not capture(['git', '-C', source, 'status', '--porcelain', '--untracked-files=no'])
    artifacts = []
    for pattern in ['**/System.Private.CoreLib.dll', '**/crossgen2', '**/libclrjit*.dylib',
                    '**/libjitinterface*.dylib', '**/libclrgc*.dylib']:
        for path in sorted(product.glob(pattern)):
            if path.is_file():
                artifacts.append({'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size})
    write(out / 'artifacts.json', artifacts)
    success = (status == 0 and clean and native_after == NATIVE_SHA and
               baseline_after == original_hash and corelib.is_file() and crossgen.is_file())
    write(out / 'results.json', {'buildExit': status, 'success': success,
          'candidateTrackedClean': clean, 'nativeUnchanged': native_after == NATIVE_SHA,
          'nativeSha256': native_after, 'baselineNativeUnchanged': baseline_after == original_hash,
          'corelib': str(corelib), 'corelibSha256': sha(corelib) if corelib.exists() else None,
          'crossgen2': str(crossgen), 'crossgen2Sha256': sha(crossgen) if crossgen.exists() else None,
          'endedUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    if status == 0 and not success:
        raise RuntimeError('Managed build provenance/artifact verification failed')
    return status


if __name__ == '__main__':
    raise SystemExit(main())
