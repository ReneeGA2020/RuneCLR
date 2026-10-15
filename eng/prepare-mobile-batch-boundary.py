#!/usr/bin/env python3
"""Prepare a fixed native-delegate adapter from the accepted boundary fixture."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('boundary_contract', ROOT/'eng/verify-batch-boundary.py')
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def need(value, message):
    if not value:
        raise RuntimeError(message)


def save(path, value):
    with Path(path).open('x', encoding='ascii') as stream:
        json.dump(value, stream, indent=2)
        stream.write(chr(10))


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def generate(source):
    start, helper = 'if (args.Length != 4)', 'static void Recovery('
    need(source.count(start) == source.count(helper) == 1, 'Frozen source boundaries changed.')
    prefix, body = source.split(start, 1)
    top, methods = body.split(helper, 1)
    # Only wrap the accepted top-level runner; retain its assertions and method bodies.
    return (prefix + 'namespace MobileBatchBoundaryProbe;' + chr(10) +
            'public static class Entry {' + chr(10) +
            'public static int Main(string[] args) => Run(args);' + chr(10) +
            'public static int Run(string[] args) {' + chr(10) + start + top +
            'return 0;' + chr(10) + '}' + chr(10) + helper + methods + chr(10) + '}' + chr(10))


def prepare(args):
    output = args.output.resolve()
    prepared, accepted = args.prepared.resolve(), args.accepted.resolve()
    frozen = read(prepared/'frozen-inputs.json')
    CONTRACT.verify_inputs(frozen)
    result = read(accepted/'results.json')
    need(result['passed'] and result['collections'] == 168, 'Accepted actual five-lane boundary results required.')
    need(CONTRACT.review(accepted) == result, 'Actual original boundary results differ.')
    original = ROOT/'eng/batch-boundary-probe/Host/Program.cs'
    need(frozen[str(original.resolve())] == sha(original), 'Accepted host source changed.')
    output.mkdir(parents=True, exist_ok=False)
    generated = output/'FrozenBoundaryRunner.cs'
    generated.write_text(generate(original.read_text()), encoding='ascii')
    project = ROOT/'eng/mobile-batch-boundary-probe/MobileBatchBoundaryProbe.csproj'
    shared = prepared/'host/BatchBoundary.Contract.dll'
    need(sha(shared) == sha(prepared/'author/BatchBoundary.Contract.dll'), 'Accepted shared contract differs.')
    command = [str(args.sdk.resolve()), 'build', str(project), '-c', 'Release',
               '--artifacts-path', str(output/'build-obj'), '-o', str(output/'host'),
               '-p:MobileBatchRunnerSource='+str(generated), '-p:BatchBoundaryContractPath='+str(shared), '-nodeReuse:false']
    request = {'driverSha256': sha(__file__), 'contractDriverSha256': sha(CONTRACT.__file__),
               'acceptedRequestSha256': sha(accepted/'request.json'), 'acceptedResultSha256': sha(accepted/'results.json'),
               'originalHostSha256': sha(original), 'generatedHostSha256': sha(generated),
               'projectSha256': sha(project), 'sdkSha256': sha(args.sdk), 'argv': command,
               'assembly': 'MobileBatchBoundaryProbe', 'type': 'MobileBatchBoundaryProbe.Entry', 'method': 'Run',
               'signature': 'public static int Run(string[] args)', 'lanes': CONTRACT.LANES,
               'mobileExecutionVerified': False, 'runtimeBuildPerformed': False}
    save(output/'request.json', request)
    with (output/'build.stdout').open('xb') as stdout, (output/'build.stderr').open('xb') as stderr:
        q = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr)
    save(output/'build.json', {'exitCode': q.returncode, 'stdoutSha256': sha(output/'build.stdout'),
                              'stderrSha256': sha(output/'build.stderr')})
    need(q.returncode == 0, 'Adapter compilation failed; preserve output.')
    need(sha(output/'host/BatchBoundary.Contract.dll') == sha(shared), 'Trusted shared contract bytes changed.')
    (output/'author').mkdir()
    for name in ('BatchBoundary.Author.dll', 'BatchBoundary.Contract.dll'):
        (output/'author'/name).write_bytes((prepared/'author'/name).read_bytes())
    need(not (output/'host/BatchBoundary.Author.dll').exists(), 'Author assembly leaked into trusted host.')
    files = {p.relative_to(output).as_posix(): sha(p) for directory in ('host', 'author')
             for p in sorted((output/directory).iterdir()) if p.is_file()}
    save(output/'input-manifest.json', {'schema': 'runeclr.mobile-batch-boundary.inputs.v1', 'files': files,
         'assembly': request['assembly'], 'type': request['type'], 'method': request['method'],
         'arguments': ['absolute author DLL', 'fresh receipt path', 'matrix 1/100/1000', '32-hex nonce'],
         'configuredLanes': CONTRACT.LANES, 'expectedContexts': 168,
         'intervalEnvironment': {'1': '1', '100': '64', '1000': '3e8'},
         'nativeEntryProof': False, 'mobileExecutionVerified': False})
    archive = output/'mobile-batch-boundary-inputs.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as zipped:
        for name in (*files, 'input-manifest.json', 'request.json', 'FrozenBoundaryRunner.cs'):
            zipped.write(output/name, name)
    save(output/'results.json', {'prepared': True, 'sourceHostBodiesUnchanged': True,
         'sourceGeneratedOnlyByFixedWrapper': True, 'compiledTrustedAdapter': True,
         'authorAndContractBytesUnchanged': True, 'files': len(files), 'zipSha256': sha(archive),
         'mobileExecutionVerified': False, 'runtimeBuildPerformed': False})
    print(json.dumps(read(output/'results.json'), indent=2))


def windows_check(args):
    output, prepared, build = args.output.resolve(), args.prepared.resolve(), args.build.resolve()
    profile = read(args.profile)
    native = build/'layout/shared/Microsoft.NETCore.App/12.0.0/coreclr.dll'
    need(profile['sourceCommit'] == read(build/'build-result.json')['candidateCommit'] and
         sha(native) == profile['nativeSha256'] and sha(build/'layout/dotnet.exe') == profile['dotnetSha256'],
         'Matching candidate product profile differs.')
    manifest = read(prepared/'input-manifest.json')
    for name, h in manifest['files'].items():
        need(sha(prepared/name) == h, 'Prepared mobile input changed: '+name)
    output.mkdir(parents=True, exist_ok=False)
    save(output/'request.json', {'inputManifestSha256': sha(prepared/'input-manifest.json'),
         'driverSha256': sha(__file__), 'profile': profile, 'prepared': str(prepared),
         'mobileExecutionVerified': False, 'performanceMeasured': False})
    contexts = 0
    for configured, matrix in CONTRACT.LANES:
        label, nonce = f'N{configured}-matrix{matrix}', uuid.uuid4().hex
        receipt = output/(label+'.receipt.json')
        command = [str(build/'layout/dotnet.exe'), 'exec', '--fx-version', '12.0.0',
                   str(prepared/'host/MobileBatchBoundaryProbe.dll'),
                   str(prepared/'author/BatchBoundary.Author.dll'), str(receipt), str(matrix), nonce]
        cfg = CONTRACT.settings(configured)
        env = {k:v for k,v in os.environ.items() if not k.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_'))}
        env.update(cfg)
        with (output/(label+'.stdout')).open('xb') as stdout, (output/(label+'.stderr')).open('xb') as stderr:
            q = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
            timed_out = False
            try:
                exit_code = q.wait(timeout=45)
            except subprocess.TimeoutExpired:
                timed_out = True
                q.kill()
                exit_code = q.wait()
        save(output/(label+'.process.json'), {'argv': command, 'settings': cfg, 'nonce': nonce,
              'pid': q.pid, 'exitCode': exit_code, 'timedOut': timed_out})
        need(exit_code == 0 and not timed_out, 'Owned portable adapter failed: '+label)
        actual = read(receipt)
        need(actual['processId'] == q.pid and actual['nonce'] == nonce, 'Owned adapter identity differs.')
        rows = CONTRACT.validate(actual, configured, matrix)
        contexts += sum(r['Collected'] is True for r in rows)
        print(label+': actual portable runner PASS', flush=True)
    need(contexts == 168, 'Portable runner collection count differs.')
    save(output/'results.json', {'passed': True, 'processes': 5, 'collections': contexts,
         'publicRunUsedByMain': True, 'mobileExecutionVerified': False, 'performanceMeasured': False})
    print(json.dumps(read(output/'results.json')))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'windows-check'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--accepted', type=Path)
    p.add_argument('--sdk', type=Path, default=ROOT/'artifacts/toolchains/dotnet-11-rc1/dotnet.exe')
    p.add_argument('--build', type=Path)
    p.add_argument('--profile', type=Path)
    args = p.parse_args()
    if args.mode == 'prepare':
        need(args.accepted is not None, '--accepted required.')
        prepare(args)
    else:
        need(args.build is not None and args.profile is not None, '--build and --profile required.')
        windows_check(args)


if __name__ == '__main__':
    main()
