#!/usr/bin/env python3
"""Build and execute unchanged official tests with the simulator generator alias fix."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
import traceback


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    root, out = args.root.resolve(), args.output.resolve()
    tools = Path(__file__).resolve().parent
    import importlib.util
    spec = importlib.util.spec_from_file_location('official_runner', tools / 'ios-r2r-official-managed-runner.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    sha, capture, write = runner.sha, runner.capture, runner.write
    base = runner.COMMIT
    baseline = root / 'ios-r2r-official-patched-tests-20261012/runtime'
    checkout = out / 'runtime'
    patch = tools / '0002-apple-simulator-test-generator.patch'
    out.mkdir(exist_ok=False)
    (out / 'logs').mkdir()
    shutil.copytree(tools, out / 'driver-snapshots')
    request = {'startedUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'baseCommit': base, 'nativeSha256': runner.NATIVE, 'targetOS': 'iossimulator',
        'targetArchitecture': 'arm64', 'configuration': 'Debug', 'librariesConfiguration': 'Debug',
        'patchSha256': sha(patch), 'driverSha256': sha(__file__),
        'scope': 'Official generated standalone managed entrypoints; custom native UIKit wrapper, not full XHarness/Helix lane',
        'isolation': 'New detached worktree; APFS copy-on-write private SDK/artifact clones; old evidence untouched'}
    write(out / 'request.json', request)
    stage = 'prepare'
    try:
        if capture(['git', '-C', baseline, 'rev-parse', 'HEAD']) != base or capture(['git', '-C', baseline, 'status', '--porcelain', '--untracked-files=no']):
            raise RuntimeError('Unexpected baseline source')
        candidate = root / 'ios-r2r-clean-debug-20261012/runtime'
        if sha(candidate / 'artifacts/bin/coreclr/iossimulator.arm64.Debug/libcoreclr.dylib') != runner.NATIVE:
            raise RuntimeError('Unexpected native candidate')
        subprocess.run(['git', '-C', baseline, 'worktree', 'add', '--detach', checkout, base], check=True)
        for name in ['.dotnet', 'artifacts']:
            subprocess.run(['cp', '-cR', baseline / name, checkout / name], check=True)
        apply_patch = out / 'generator-apply-lf.patch'
        apply_patch.write_bytes(patch.read_bytes().replace(b'\r\n', b'\n'))
        request['applyPatchSha256'] = sha(apply_patch)
        request['patchLineEndingNormalization'] = ('CRLF to LF' if b'\r\n' in patch.read_bytes() else 'None; already LF') + '; original portable patch bytes preserved'
        write(out / 'request.json', request)
        subprocess.run(['git', '-C', checkout, 'apply', '--check', apply_patch], check=True)
        subprocess.run(['git', '-C', checkout, 'apply', apply_patch], check=True)
        generator = 'src/tests/Common/XUnitWrapperGenerator/XUnitWrapperGenerator.cs'
        subprocess.run(['git', '-C', checkout, 'add', generator], check=True)
        subprocess.run(['git', '-C', checkout, '-c', 'user.name=RuneCLR Experiment', '-c', 'user.email=runeclr-experiment@localhost', 'commit', '-m', 'Map Apple simulator aliases in official test generator'], check=True)
        commit = capture(['git', '-C', checkout, 'rev-parse', 'HEAD'])
        request.update({'sourceCommit': commit, 'sourceSdk': capture([checkout / '.dotnet/dotnet', '--version']),
            'generatorBeforeSha256': sha(baseline / generator), 'generatorAfterSha256': sha(checkout / generator)})
        (out / 'source-diff.patch').write_text(capture(['git', '-C', checkout, 'show', '--format=', commit]) + '\n')
        evidence = out / 'source-evidence'
        for name in [generator, 'docs/workflow/testing/coreclr/testing.md', 'docs/workflow/testing/coreclr/unix-test-instructions.md', 'docs/workflow/building/coreclr/README.md', 'src/tests/Directory.Build.props', 'src/tests/Common/CLRTest.Execute.Bash.targets', 'src/mono/msbuild/apple/build/AppleBuild.props']:
            dest = evidence / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(checkout / name, dest)
        write(out / 'request.json', request)
        print('PREPARED ' + commit, flush=True)
        stage = 'build'
        os.chdir(checkout)
        env = dict(os.environ)
        env.update(PATH=str(root / 'tools/bin') + ':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                   DOTNET_CLI_HOME=str(out / 'dotnet-home'), DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
        for key in list(env):
            if key.startswith(('DOTNET_Interp', 'COMPlus_Interp', 'DOTNET_RuneCLR', 'COMPlus_RuneCLR')):
                del env[key]
        common = ['-p:Configuration=Debug', '-p:TargetOS=iossimulator', '-p:TargetArchitecture=arm64',
            '-p:RuntimeFlavor=coreclr', '-p:LibrariesConfiguration=Debug', '-p:BuildAsStandalone=true',
            '-p:CLRTestPriorityToBuild=1', '-p:EmitCompilerGeneratedFiles=true', '-p:BuildTestsOnHelix=false',
            '-p:EnableAggressiveTrimming=false', '-p:PublishTrimmed=false']
        projects = ['Loader/CollectibleAssemblies/' + folder + '/' + name for name, (folder, _, _) in runner.PROJECTS.items()]
        commands = [('restore-dependencies', ['restore', 'src/tests/Common/test_dependencies/test_dependencies.csproj'] + common),
            ('external-targeting-pack', ['build', 'src/tests/Common/external/external.csproj'] + common)]
        commands += [(Path(name).name, ['build', 'src/tests/' + name + '.csproj', '-t:Rebuild'] + common) for name in projects]
        request['projects'] = projects
        request['buildProperties'] = common
        write(out / 'request.json', request)
        builds = []
        for name, arguments in commands:
            command = [checkout / 'dotnet.sh'] + arguments
            log = out / 'logs' / (name + '.log')
            status = runner.logged(command, log, timeout=900, env=env, check=False)
            builds.append({'name': name, 'command': [str(x) for x in command], 'exit': status, 'logSha256': sha(log)})
            write(out / 'build-results.json', builds)
            print('BUILD ' + name + ' exit=' + str(status), flush=True)
            if status:
                raise RuntimeError('Official build failed: ' + name)
        generated = checkout / 'artifacts/tests/coreclr/obj/iossimulator.arm64.Debug/Managed/Loader/CollectibleAssemblies'
        guards = {}
        for name, (folder, _, _) in runner.PROJECTS.items():
            files = list((generated / folder / name).rglob('SimpleRunner.g.cs'))
            if len(files) != 1:
                raise RuntimeError('Expected one generated runner: ' + name)
            text = files[0].read_text(encoding='utf-8-sig')
            dest = out / 'generated' / (name + '.cs')
            dest.parent.mkdir(exist_ok=True)
            shutil.copy2(files[0], dest)
            guards[name] = {'path': str(files[0]), 'sha256': sha(files[0]), 'falseGuardAbsent': '&& (false)' not in text,
                'conditionalIOSGuard': 'System.OperatingSystem.IsIOS()' in text and 'System.OperatingSystem.IsMacCatalyst()' in text,
                'officialSourcesUnchanged': not capture(['git', '-C', checkout, 'diff', base, '--', 'src/tests/Loader/CollectibleAssemblies/' + folder])}
        write(out / 'generated-guards.json', guards)
        if not all(x['falseGuardAbsent'] and x['officialSourcesUnchanged'] for x in guards.values()) or not all(guards[n]['conditionalIOSGuard'] for n in ['GenericVirtualMethod', 'ResolvedFromDifferentContext']):
            raise RuntimeError('Actual generated guard verification failed')
        print('GENERATED 4/4 guards verified with TargetOS=iossimulator', flush=True)
        stage = 'package'
        runner.COMMIT = commit
        runner.package(root, out, 'iossimulator')
        runner.COMMIT = base
        stage = 'run'
        runner.run(root, out, 'iossimulator')
        stage = 'verify'
        runner.verify(root, out, 'iossimulator', test_commit=commit)
        write(out / 'completion.json', {'success': True, 'stage': stage, 'completedUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    except Exception:
        write(out / 'completion.json', {'success': False, 'stage': stage, 'error': traceback.format_exc(), 'completedUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
        traceback.print_exc()
    finally:
        archive = out / 'generator-fixed-official-tests-evidence.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            for entry in out.rglob('*'):
                rel = entry.relative_to(out)
                if 'runtime' in rel.parts or 'dotnet-home' in rel.parts or any(x.endswith('.app') for x in rel.parts) or entry == archive:
                    continue
                if entry.is_file() and entry.suffix != '.o':
                    tar.add(entry, arcname=str(rel))
        receipt = {'path': str(archive), 'bytes': archive.stat().st_size, 'sha256': sha(archive)}
        write(out / 'archive.json', receipt)
        print('ARCHIVE ' + json.dumps(receipt), flush=True)
    return 0 if json.loads((out / 'completion.json').read_text())['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
