#!/usr/bin/env python3
"""Build unchanged official CoreCLR projects in an isolated patched iOS test tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

COMMIT = '8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d'
NATIVE = 'e97efd27370d02b6767bbaa1e4cb968f92fa3341d53e345626ff6f8498f572d8'
PROJECTS = [
    'Loader/CollectibleAssemblies/GenericVirtualMethod/GenericVirtualMethod',
    'Loader/CollectibleAssemblies/Statics/CollectibleStatics',
    'Loader/CollectibleAssemblies/ResolvedFromDifferentContext/ResolvedFromDifferentContext',
    'Loader/CollectibleAssemblies/ByRefLocals/ByRefLocals',
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def capture(command):
    return subprocess.check_output([str(x) for x in command], text=True).strip()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['prepare', 'build'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--attempt', default='first')
    parser.add_argument('--target-os', choices=['iossimulator', 'ios'], default='iossimulator')
    args = parser.parse_args()
    root, out = args.root.resolve(), args.output.resolve()
    baseline = root / 'runtime'
    candidate = root / 'ios-r2r-clean-debug-20261012/runtime'
    native_dir = candidate / 'artifacts/bin/coreclr/iossimulator.arm64.Debug'
    if capture(['git', '-C', candidate, 'rev-parse', 'HEAD']) != COMMIT:
        raise RuntimeError('Unexpected clean candidate source revision')
    if capture(['git', '-C', candidate, 'status', '--porcelain', '--untracked-files=no']):
        raise RuntimeError('Preserve candidate tracked changes')
    if sha(native_dir / 'libcoreclr.dylib') != NATIVE:
        raise RuntimeError('Unexpected clean candidate native input')
    checkout = out / 'runtime'
    if args.phase == 'prepare':
        out.mkdir(exist_ok=False)
        subprocess.run(['git', '-C', str(baseline), 'worktree', 'add', '--detach', str(checkout), COMMIT], check=True)
        for name in ['.dotnet', 'artifacts']:
            subprocess.run(['cp', '-cR', str(baseline / name), str(checkout / name)], check=True)
        private_native = checkout / 'artifacts/bin/coreclr/iossimulator.arm64.Debug'
        pack_native = checkout / 'artifacts/bin/microsoft.netcore.app.runtime.iossimulator-arm64/Debug/runtimes/iossimulator-arm64/native'
        replacements = {}
        for source in list(native_dir.glob('*.dylib')) + list(native_dir.glob('*.a')):
            digest = sha(source)
            for destination in [private_native / source.name, pack_native / source.name, private_native / 'sharedFramework' / source.name]:
                if destination.parent.is_dir():
                    shutil.copy2(source, destination)
                    if sha(destination) != digest:
                        raise RuntimeError('Private native copy differs')
                    replacements[str(destination.relative_to(checkout))] = digest
        (out / 'logs').mkdir()
        instructions = [
            'docs/workflow/testing/coreclr/testing.md',
            'docs/workflow/testing/coreclr/unix-test-instructions.md',
            'src/tests/build.sh', 'src/tests/Directory.Build.props',
            'src/tests/Common/CLRTest.Execute.Bash.targets',
            'src/tests/Common/XUnitWrapperGenerator/XUnitWrapperGenerator.cs',
            'src/mono/msbuild/apple/build/AppleBuild.props',
        ]
        for name in instructions:
            target = out / 'source-evidence' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(checkout / name, target)
        write(out / 'request.json', {'commit': COMMIT, 'nativeSha256': NATIVE,
            'sourceSdk': capture([checkout / '.dotnet/dotnet', '--version']),
            'replacements': replacements, 'projects': PROJECTS,
            'isolation': 'Detached worktree; APFS private baseline artifact clone; clean candidate native replacements',
            'driverSha256': sha(__file__), 'startedUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
        print('PREPARED isolated patched official iOS test tree', flush=True)
        return
    if capture(['git', '-C', checkout, 'rev-parse', 'HEAD']) != COMMIT:
        raise RuntimeError('Private test source differs')
    logdir = out / 'logs'
    env = dict(os.environ)
    env.update({'PATH': str(root / 'tools/bin') + ':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                'DOTNET_CLI_HOME': str(out / 'dotnet-home'), 'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1'})
    for key in list(env):
        if key.startswith(('DOTNET_Interp', 'COMPlus_Interp', 'DOTNET_RuneCLR', 'COMPlus_RuneCLR')):
            del env[key]
    common = ['-p:Configuration=Debug', '-p:TargetOS=' + args.target_os, '-p:TargetArchitecture=arm64',
              '-p:RuntimeFlavor=coreclr', '-p:LibrariesConfiguration=Debug',
              '-p:BuildAsStandalone=true', '-p:CLRTestPriorityToBuild=1',
              '-p:EmitCompilerGeneratedFiles=true', '-p:BuildTestsOnHelix=false']
    if args.target_os == 'ios':
        common += ['-p:EnableAggressiveTrimming=false', '-p:PublishTrimmed=false']
    commands = [('restore-dependencies', ['restore', 'src/tests/Common/test_dependencies/test_dependencies.csproj'] + common)]
    commands += [('external-targeting-pack', ['build', 'src/tests/Common/external/external.csproj'] + common)]
    commands += [(Path(name).name, ['build', 'src/tests/' + name + '.csproj'] + common) for name in PROJECTS]
    results = []
    for name, arguments in commands:
        command = [str(checkout / 'dotnet.sh')] + arguments
        log = logdir / (args.attempt + '-' + name + '.log')
        if log.exists():
            raise RuntimeError('Preserve prior attempt: ' + name)
        with log.open('w') as stream:
            status = subprocess.run(command, cwd=checkout, env=env, stdout=stream, stderr=subprocess.STDOUT).returncode
        results.append({'name': name, 'command': command, 'exit': status, 'logSha256': sha(log)})
        write(out / (args.attempt + '-build-results.json'), results)
        print(name + ' exit=' + str(status), flush=True)
        if status != 0:
            print('Preserved official build failure: ' + str(log), flush=True)
            return status
    print('BUILT four unchanged official iOS test projects', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
