#!/usr/bin/env python3
"""Run production and frozen upstream functional controls on exact private Release."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '099dacd07d8d890822f7422f895337733457ab3c'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def execute(argv, output, name, settings=None, timeout=180, cwd=ROOT, expected=0):
    nonce = uuid.uuid4().hex
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_', '__Test'))}
    env.update(settings or {})
    env['RUNECLR_RELEASE_FUNCTIONAL_NONCE'] = nonce
    started = datetime.now(timezone.utc).isoformat()
    tick = time.monotonic()
    process = subprocess.Popen([str(a) for a in argv], cwd=cwd, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate(timeout=15)
    (output / (name + '.stdout')).write_bytes(stdout)
    (output / (name + '.stderr')).write_bytes(stderr)
    record = dict(name=name, command=[str(a) for a in argv], cwd=str(cwd),
                  settings=settings or {}, nonce=nonce, processId=process.pid,
                  startedUtc=started, elapsedSeconds=time.monotonic() - tick,
                  watchdogSeconds=timeout, timedOut=timed_out, exitCode=process.returncode,
                  expectedExitCode=expected, stdoutSha256=sha(output / (name + '.stdout')),
                  stderrSha256=sha(output / (name + '.stderr')))
    save(output / (name + '.process.json'), record)
    if timed_out or process.returncode != expected:
        raise RuntimeError('Process failed or timed out: ' + name)
    return record, (stdout + stderr).decode('utf-8', errors='replace')


def inventory(root):
    return {str(p.resolve()): sha(p) for p in root.rglob('*') if p.is_file()}


def check_hashes(hashes):
    for path, expected in hashes.items():
        if sha(path).lower() != expected.lower():
            raise RuntimeError('Frozen input changed: ' + path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--layout', type=Path, required=True)
    parser.add_argument('--build-evidence', type=Path, required=True)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, default=ROOT / 'artifacts/toolchains/dotnet-11-rc1/dotnet.exe')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--candidate-commit', default=BASELINE)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError('New evidence directory required; preserve all attempts.')
    output.mkdir(parents=True)
    runs = []
    stage = 'freeze'
    try:
        shutil.copyfile(__file__, output / 'driver.py')
        source_hashes = {}
        files = subprocess.check_output(['rg', '--files', '--hidden', '-g', '!artifacts/**',
                                         '-g', '!**/bin/**', '-g', '!**/obj/**',
                                         '-g', '!**/.git/**', 'src', 'tests', 'samples', 'tools'],
                                        cwd=ROOT, text=True).splitlines()
        files += ['RuneCLR.slnx', 'Directory.Build.props', 'global.json', 'NuGet.Config']
        for relative in files:
            file = ROOT / relative
            if not file.is_file():
                continue
            dest = output / 'source' / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, dest)
            source_hashes[str(file.resolve())] = sha(file)
        save(output / 'source-hashes.json', source_hashes)
        provenance = ROOT / 'eng/windows-runtime-validation.py'
        freeze_args = ['py', '-3', '-B', provenance, 'freeze', '--output', output,
                       '--runtime', args.runtime, '--layout', args.layout,
                       '--build-evidence', args.build_evidence, '--candidate-commit', args.candidate_commit]
        execute(freeze_args, output, 'runtime-freeze')
        version, text = execute([args.sdk, '--version'], output, 'sdk-version')
        if text.strip() != '11.0.100-rc.1.26425.128':
            raise RuntimeError('Unexpected private SDK version.')
        save(output / 'request.json', dict(configuration='Release', sdk=str(args.sdk.resolve()),
             candidateCommit=args.candidate_commit,
             sdkSha256=sha(args.sdk), sdkVersion=text.strip(), sourceHashes=source_hashes,
             upstream=str(args.upstream.resolve()),
             scope='Functional controls only; no DEBUG bytecode dumps or complete method execution trace.'))
        stage = 'build'
        execute([args.sdk, 'build', ROOT / 'RuneCLR.slnx', '-c', 'Release'],
                output, 'solution-build', timeout=600)
        dirs = {name: ROOT / path / 'bin/Release/net11.0' for name, path in {
            'tests': 'tests/RuneCLR.Runtime.Tests', 'sample': 'samples/RuneCLR.SampleHost',
            'player': 'tests/RuneCLR.PackageExecution.Tests'}.items()}
        managed = {}
        for directory in dirs.values():
            managed.update(inventory(directory))
        late_started = time.time_ns()
        execute([args.sdk, 'build', ROOT / 'tests/RuneCLR.LateMap', '-c', 'Release',
                 '-t:Rebuild', '-p:BuildProjectReferences=false'], output, 'late-build', timeout=600)
        late_dir = ROOT / 'tests/RuneCLR.LateMap/bin/Release/net11.0'
        if (late_dir / 'RuneCLR.LateMap.dll').stat().st_mtime_ns < late_started:
            raise RuntimeError('Late IL was not built after the host.')
        check_hashes(managed)
        managed.update(inventory(late_dir))
        package_tool = ROOT / 'tools/RuneCLR.PackageTool/bin/Release/net11.0/RuneCLR.PackageTool.dll'
        refs = ROOT / 'tests/RuneCLR.Packaging.Tests/bin/Release/net11.0/refs'
        contract = ROOT / 'src/RuneCLR.Abstractions/bin/Release/net11.0/RuneCLR.Abstractions.dll'
        execute([args.sdk, package_tool, 'compile', '--source', ROOT / 'samples/Source',
                 '--id', 'ControlledGameplay', '--entry-type', 'Gameplay', '--framework-refs', refs,
                 '--contract', contract, '--output', output / 'controlled-source'], output, 'package-build')
        manifest = output / 'controlled-source/package.json'
        execute([args.sdk, package_tool, 'validate', '--manifest', manifest], output, 'package-validate')
        execute([args.sdk, package_tool, 'import', '--assembly', output / 'controlled-source/ControlledGameplay.dll',
                 '--id', 'ControlledImported', '--entry-type', 'Gameplay', '--framework-refs', refs,
                 '--contract', contract, '--output', output / 'controlled-import'], output, 'package-import')
        execute([args.sdk, ROOT / 'tools/RuneCLR.PackageFixtures/bin/Release/net11.0/RuneCLR.PackageFixtures.dll',
                 '--framework-refs', refs, '--contract', contract, '--output', output / 'package-fixtures'],
                output, 'fixture-build')
        for name in ('controlled-source', 'controlled-import', 'package-fixtures'):
            managed.update(inventory(output / name))
        save(output / 'managed-input-hashes.json', managed)
        settings = {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0',
                    'DOTNET_ReadyToRun': '1', 'DOTNET_TieredCompilation': '1',
                    'DOTNET_GCStress': '0', 'DOTNET_MULTILEVEL_LOOKUP': '0'}
        dotnet = args.layout.resolve() / 'dotnet.exe'
        command = [dotnet, 'exec', '--fx-version', '12.0.0']
        stage = 'production'
        cases = [
            ('lifecycle', dirs['tests'] / 'RuneCLR.Runtime.Tests.dll',
             ['--late-map', late_dir / 'map.json'], '24/24 tests passed', None),
            ('sample', dirs['sample'] / 'RuneCLR.SampleHost.dll', ['--collect'], None, 3),
            ('late-sample', dirs['sample'] / 'RuneCLR.SampleHost.dll', ['--collect', late_dir / 'map.json'], None, 1),
            ('controlled-sample', dirs['sample'] / 'RuneCLR.SampleHost.dll',
             ['--collect', manifest, output / 'controlled-import/package.json', manifest], None, 3),
            ('package-execution', dirs['player'] / 'RuneCLR.PackageExecution.Tests.dll',
             ['--packages', output / 'package-fixtures'], '15/15 package execution tests passed', None)]
        for name, assembly, arguments, marker, collected in cases:
            record, text = execute(command + [assembly] + arguments + ['--require-interpreter'],
                                   output, name, settings)
            policy = 'SESSION_EXECUTION_POLICY required-interpreter version=1' in text
            body = (marker is None or marker in text)
            count = text.count('unload: collected')
            if not policy or not body or (collected is not None and count != collected):
                raise RuntimeError('Production business result missing: ' + name)
            if name == 'controlled-sample' and text.count('starts=1') != 3:
                raise RuntimeError('Controlled static reset missing.')
            record.update(passed=True, policyAcknowledged=policy, functionalMarker=marker,
                          collectedSamples=count, methodEntryProof=False)
            runs.append(record)
            save(output / 'runs.json', runs)
            print('PASS Release production ' + name, flush=True)
        stage = 'upstream'
        upstream = args.upstream.resolve()
        previous = load(upstream / 'results.json')
        if not previous['success'] or not previous['complete']:
            raise RuntimeError('Original frozen official acceptance absent.')
        old_hashes = load(upstream / 'managed-input-hashes.json')
        check_hashes(old_hashes)
        official_hashes = dict(old_hashes)
        for filename in ('results.json', 'managed-input-hashes.json', 'generated-guards.json', 'request.json'):
            shutil.copyfile(upstream / filename, output / ('upstream-' + filename))
            official_hashes[str(upstream / filename)] = sha(upstream / filename)
        guards = load(upstream / 'generated-guards.json')
        runtimeconfig = output / 'official.runtimeconfig.json'
        save(runtimeconfig, {'runtimeOptions': {'tfm': 'net12.0', 'framework': {
             'name': 'Microsoft.NETCore.App', 'version': '12.0.0'}, 'rollForward': 'Disable'}})
        for old_run in previous['runs']:
            name = old_run['test']
            guard = guards[name]
            generated = upstream / 'generated' / (name + '.cs')
            if not guard['passed'] or sha(generated).upper() != guard['sha256'].upper():
                raise RuntimeError('Official generated Main guard binding failed: ' + name)
            guard_text = generated.read_text()
            if guard['hostMethod'].split(':')[-1] not in guard_text or re.search(r'if\s*\(\s*false\s*\)|&&\s*\(false\)', guard_text):
                raise RuntimeError('Official generated Main would omit body: ' + name)
            dest = output / 'generated' / generated.name
            dest.parent.mkdir(exist_ok=True)
            shutil.copyfile(generated, dest)
            official_hashes[str(generated)] = sha(generated)
            assembly = Path(old_run['command'][-1])
            skip_file = output / (name + '.skip.txt')
            lane_settings = dict(settings, DOTNET_RuneCLRInterpretCollectible='1',
                                 __TestOutOfProcessStatusFile=str(skip_file))
            record, text = execute([dotnet, 'exec', '--runtimeconfig', runtimeconfig,
                                   '--fx-version', '12.0.0', assembly], output, 'official-' + name,
                                  lane_settings, cwd=assembly.parent, expected=100)
            if skip_file.exists() or re.search('Assert failure|Fatal error|Unhandled exception|Failure -|Failed to unload', text):
                raise RuntimeError('Official control failed or skipped: ' + name)
            markers = {}
            if name == 'ByRefLocals':
                markers['loopOutputs'] = len(re.findall(r'^1\r?$', text, re.M))
                if markers['loopOutputs'] != 20:
                    raise RuntimeError('ByRefLocals body not observed.')
            if name == 'ResolvedFromDifferentContext':
                markers['scenarioCount'] = len(re.findall(r'^Running test case (ResolvingEvent|LoadOverride|ResolvingEventInNonCollectible|LoadOverrideInNonCollectible)\r?$', text, re.M))
                if markers['scenarioCount'] != 4:
                    raise RuntimeError('ResolvedFromDifferentContext body not observed.')
            record.update(passed=True, generatedGuardSha256=sha(generated), skipped=False,
                          originalAssertions=True, businessMarkers=markers, methodEntryProof=False,
                          managedBuildConfiguration='Checked standalone IL reused unchanged')
            runs.append(record)
            save(output / 'runs.json', runs)
            print('PASS Release official functional ' + name + ' exit100', flush=True)
        save(output / 'official-input-hashes.json', official_hashes)
        stage = 'check'
        check_hashes(source_hashes)
        check_hashes(managed)
        check_hashes(official_hashes)
        execute(['py', '-3', '-B', provenance, 'check', '--output', output, '--candidate-commit', args.candidate_commit], output, 'runtime-check')
        save(output / 'results.json', dict(passed=True, configuration='Release', runs=runs,
             candidateCommit=args.candidate_commit,
             productionRuns=5, lifecycle='24/24', player='15/15', upstreamFunctional='4/4 exit100',
             sourceInputsUnchanged=True, managedInputsUnchanged=True, methodEntryProof=False,
             lateBuiltAfterHost=True, finishedUtc=datetime.now(timezone.utc).isoformat(),
             scope='Functional acceptance and native per-session policy acknowledgement; no complete interpreted-method execution proof.'))
        print('PASS exact Release production 5/5, lifecycle24/24, player15/15, upstream4/4', flush=True)
    except Exception as error:
        save(output / 'failure.json', dict(stage=stage, error=str(error), runs=runs))
        raise


if __name__ == '__main__':
    main()
