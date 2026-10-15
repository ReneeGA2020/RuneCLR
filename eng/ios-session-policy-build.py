#!/usr/bin/env python3
"""Build session-policy/CID source in a fresh matching iOS simulator worktree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import traceback

BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
TREE = '71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2'
PATCHES = {
    '0001-collectible-cid-publication.patch': '43b36606fa94967e97f2640e8d76dcfa8f0af21eeb77a065a0eea5c83c915857',
    '0003-collectible-interpreter-selection.patch': 'b7d446243a099c6fc01c19bdc6e83c151eb4771112001fd9bd7185a0d1950ccb',
    '0004-interpreter-required-load-context.patch': '714ba322b3df83ccb3feb5b91043b779e4c75b212ea9d4dbf95db06c0e330657',
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

def build(args):
    original = args.root.resolve() / 'runtime'
    if capture(['git', '-C', original, 'rev-parse', 'HEAD']) != BASE or not clean(original):
        raise RuntimeError('Unexpected or modified baseline source')
    for name, expected in PATCHES.items():
        if sha(args.patches / name) != expected:
            raise RuntimeError('Patch identity differs: ' + name)
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
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
        subprocess.run(['git', '-C', str(source), 'commit', '-m',
                        'Private experiment: immutable interpreter session policy and collectible CID lifetime'],
                       env=source_env, stdout=log, stderr=subprocess.STDOUT, check=True)
    commit = capture(['git', '-C', source, 'rev-parse', 'HEAD'])
    changed = capture(['git', '-C', source, 'diff', '--name-only', BASE]).splitlines()
    diff = subprocess.check_output(['git', '-C', str(source), 'diff', BASE])
    (logs / 'runtime.patch').write_bytes(diff)
    write(out / 'source.json', {'base': BASE, 'commit': commit, 'tree': TREE,
          'branch': 'detached', 'configuration': 'iossimulator.arm64.Release',
          'patches': PATCHES, 'combinedPatchSha256': sha(logs / 'runtime.patch'),
          'sourceHashes': {name: sha(source / name) for name in changed},
          'trackedClean': clean(source), 'description': 'Windows session-policy source plus only CID v2 publication guard'})
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
          'driverSha256': sha(__file__), 'baselineNativeBeforeSha256': baseline_sha,
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
    unchanged = sha(baseline_native) == baseline_sha
    tracked_clean = clean(source)
    result = {'success': status == 0 and unchanged and tracked_clean
                        and all(p.is_file() for p in [native, corelib, compiler]),
              'buildExit': status, 'base': BASE, 'commit': commit, 'tree': TREE,
              'target': 'iossimulator.arm64', 'configuration': 'Release',
              'sourceTrackedClean': tracked_clean, 'baselineNativeUnchanged': unchanged,
              'native': str(native), 'corelib': str(corelib), 'crossgen2': str(compiler),
              'nativeSha256': sha(native) if native.exists() else None,
              'corelibSha256': sha(corelib) if corelib.exists() else None,
              'crossgen2Sha256': sha(compiler) if compiler.exists() else None,
              'endedUtc': utc(), 'executionVerified': False}
    write(out / 'results.json', result)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result['success'] else status or 1

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['root', 'output', 'patches']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        return build(args)
    except Exception:
        if args.output.is_dir():
            failure = args.output / 'driver-failure.txt'
            if not failure.exists():
                failure.write_text(traceback.format_exc())
        raise

if __name__ == '__main__':
    raise SystemExit(main())
