#!/usr/bin/env python3
"""Prepare fixed trusted host-budget mobile inputs locally; no runtime/device execution."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

TRUSTED = ('MobileHostBudgetProbe.dll', 'RuneCLR.Runtime.dll', 'RuneCLR.Packages.dll', 'RuneCLR.Abstractions.dll')
PLUGIN = ('HostBudgetProbe.Payload.dll', 'HostBudgetProbe.Private.dll')
CASES = ('Normal', 'EndlessTick', 'StartLoop', 'CatchResume', 'BroadCatchResume', 'SignalFilter',
         'FilterExhaustion', 'ConstructorLoop', 'StaticConstructorLoop', 'FiniteCleanup', 'InfiniteCleanup',
         'StopLoop', 'MaliciousMessage', 'ExplicitCanceled', 'Recovery')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write(chr(10))


def check(value, reason):
    if not value:
        raise RuntimeError(reason)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path)
    parser.add_argument('--windows-evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent.parent
    sdk = (args.sdk or repo/'artifacts/toolchains/dotnet-11-rc1/dotnet.exe').resolve()
    parent = args.windows_evidence.resolve()
    output = args.output.resolve()
    check(not output.exists(), 'Fresh output required; preserve failed preparation.')
    output.mkdir(parents=True)
    result = {'success': False, 'executionVerified': False, 'mobileAccepted': False,
              'nativeEntryProof': False, 'prototypeOnly': True, 'authorFinalizersProductionSupported': False}
    try:
        frozen = read(parent/'request.json')
        accepted = read(parent/'results.json')
        check(accepted['passed'] and not frozen['stockSmoke'] and not frozen['capabilityRefusal'], 'Actual complete Windows candidate fixture provenance required.')
        check(tuple(frozen['cases']) == CASES and len(accepted['lanes']) == 15, 'Actual unchanged15-scenario provenance required.')
        check(all(v['passed'] for v in accepted['lanes'].values()), 'Parent contains failed scenario.')
        for name, value in frozen['sourceHashes'].items():
            check(sha(repo/name).lower() == value.lower(), 'Accepted host/fixture source changed: '+name)
        sources = {}
        roots = ('eng/mobile-host-budget-probe', 'eng/host-budget-probe', 'src/RuneCLR.Runtime',
                 'src/RuneCLR.Packages', 'src/RuneCLR.Abstractions')
        for root in roots:
            for path in sorted((repo/root).rglob('*')):
                relative = path.relative_to(repo)
                if path.is_file() and not set(relative.parts).intersection({'obj', 'bin'}) and (path.suffix in ('.cs', '.csproj') or path.name == 'BridgeCall.cs.txt'):
                    sources[relative.as_posix()] = sha(path)
        for name in ('Directory.Build.props', 'Directory.Build.targets', 'global.json', 'NuGet.Config', 'eng/mobile-budget-inputs.py'):
            if (repo/name).is_file():
                sources[name] = sha(repo/name)
        for name in sources:
            destination = output/'source'/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo/name, destination)
        request = {'schema': 'runeclr.mobile-host-budget.inputs.v1', 'createdUtc': datetime.now(timezone.utc).isoformat(),
                   'sdk': str(sdk), 'sdkSha256': sha(sdk), 'sourceHashes': sources,
                   'windowsEvidence': str(parent), 'windowsRequestSha256': sha(parent/'request.json'),
                   'windowsResultsSha256': sha(parent/'results.json'), 'windowsDriverSha256': sha(parent/'driver.ps1'),
                   'cases': CASES, 'expectedContexts': 73, 'linkedHostSourceUnmodified': True,
                   'payloadCompilationReused': True, 'runtimeSourceCommitRequired': '099dacd07d8d890822f7422f895337733457ab3c',
                   'executionVerified': False, 'nativeEntryProof': False}
        write(output/'request.json', request)
        for name in ('request.json', 'results.json', 'managed-identity.json'):
            shutil.copyfile(parent/name, output/('windows-'+name))
        build = output/'build'
        command = [str(sdk), 'build', str(repo/'eng/mobile-host-budget-probe/MobileHostBudgetProbe.csproj'),
                   '-c', 'Release', '--output', str(build), '-nodeReuse:false']
        env = {k: v for k, v in os.environ.items() if not k.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_'))}
        process = subprocess.Popen(command, cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=20)
            else:
                process.kill()
            stdout, stderr = process.communicate(timeout=20)
        (output/'build.stdout').write_bytes(stdout)
        (output/'build.stderr').write_bytes(stderr)
        write(output/'build-process.json', {'command': command, 'processId': process.pid, 'exitCode': process.returncode,
              'timedOut': timed_out, 'stdoutSha256': sha(output/'build.stdout'), 'stderrSha256': sha(output/'build.stderr')})
        check(not timed_out and process.returncode == 0, 'Build failed or watchdog expired; raw preparation retained.')
        for name, value in sources.items():
            check(sha(repo/name) == value, 'Source changed during preparation: '+name)
        identity = read(parent/'managed-identity.json')
        source_managed = {Path(path).resolve(): value.lower() for path, value in identity.items()}
        files = {}
        for name in TRUSTED:
            path = build/name
            check(path.is_file(), 'Trusted dependency missing: '+name)
            if name != 'MobileHostBudgetProbe.dll':
                old = (parent/'host'/name).resolve()
                check(old in source_managed and sha(path) == source_managed[old], 'Newly built trusted DLL differs from accepted fixed source bytes: '+name)
            destination = output/'trusted'/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            files['trusted/'+name] = sha(destination)
        for name in PLUGIN:
            path = (parent/'payload'/name).resolve()
            check(path in source_managed and sha(path) == source_managed[path], 'Accepted author IL changed: '+name)
            destination = output/'plugin'/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            files['plugin/'+name] = sha(destination)
        check(not any((output/'trusted'/name).exists() for name in PLUGIN), 'Author IL must never enter trusted composite.')
        write(output/'input-manifest.json', {'schema': 'runeclr.mobile-host-budget.manifest.v1', 'files': files,
              'sourceHashes': sources, 'requestSha256': sha(output/'request.json'),
              'trustedCompositeOnly': ['trusted/'+name for name in TRUSTED], 'authorCollectibleILOnly': ['plugin/'+name for name in PLUGIN],
              'entry': {'assembly': 'MobileHostBudgetProbe', 'type': 'MobileHostBudgetProbe.Entry', 'method': 'Run',
                        'signature': 'public static int Run(string[] args)', 'arguments': ['pluginDirectory', 'freshEvidenceDirectory', 'ownedNonce32hex', 'all']},
              'settingsRequired': {'InterpMode': 0, 'RuneCLRInterpretCollectible': 0, 'ReadyToRun': 1},
              'cases': CASES, 'expectedContexts': 73, 'executionVerified': False, 'nativeEntryProof': False,
              'claim': 'Compiled fixed trusted adapter; unchanged author IL. No mobile runtime execution or platform acceptance.'})
        archive = output/'mobile-host-budget-inputs.zip'
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as stream:
            for path in sorted(output.rglob('*')):
                if path.is_file() and path != archive and not path.is_relative_to(build):
                    stream.write(path, path.relative_to(output).as_posix())
        result.update(success=True, sourceUnchanged=True, trustedBytesMatchWindows=True,
                      originalAuthorBytesUnchanged=True, files=files, sourceCount=len(sources),
                      archive=str(archive), archiveSha256=sha(archive), manifestSha256=sha(output/'input-manifest.json'))
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        write(output/'results.json', result)
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
