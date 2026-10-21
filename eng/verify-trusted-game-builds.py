#!/usr/bin/env python3
"""Build one TrustedGame IL set and independent R2R derivatives, then run both layouts."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from datetime import datetime, timezone
import uuid

ROOT = Path(__file__).resolve().parents[1]
HOST_PROJECT = ROOT / 'samples/TrustedGame.Host/TrustedGame.Host.csproj'
UPDATE_PROJECT = ROOT / 'samples/TrustedGame.Update/TrustedGame.Update.csproj'
UPDATE_B_PROJECT = ROOT / 'samples/TrustedGame.UpdateV2/TrustedGame.UpdateV2.csproj'
PUBLISHER_PROJECT = ROOT / 'samples/TrustedGame.Publisher/TrustedGame.Publisher.csproj'
HOST_ASSEMBLY = 'TrustedGame.Host.dll'
CONTRACTS_ASSEMBLY = 'TrustedGame.Contracts.dll'
TRUSTED_ASSEMBLY = 'RuneCLR.TrustedUpdate.dll'
UPDATE_ASSEMBLY = 'TrustedGame.Update.dll'
PUBLISHER_ASSEMBLY = 'TrustedGame.Publisher.dll'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def pe(path):
    data = Path(path).read_bytes()
    header = struct.unpack_from('<I', data, 0x3c)[0]
    if data[header:header + 4] != b'PE\0\0':
        raise ValueError('Not a PE image: ' + str(path))
    machine, count = struct.unpack_from('<HH', data, header + 4)
    optional_size = struct.unpack_from('<H', data, header + 20)[0]
    optional = header + 24
    magic = struct.unpack_from('<H', data, optional)[0]
    directories = optional + (112 if magic == 0x20b else 96)
    cli_rva = struct.unpack_from('<I', data, directories + 14 * 8)[0]
    sections = []
    for index in range(count):
        start = optional + optional_size + index * 40
        virtual_size, rva, raw_size, offset = struct.unpack_from('<IIII', data, start + 8)
        flags = struct.unpack_from('<I', data, start + 36)[0]
        sections.append(dict(rva=rva, size=max(virtual_size, raw_size), rawSize=raw_size,
                             offset=offset, executable=bool(flags & 0x20000000)))

    def file_offset(rva):
        for section in sections:
            if section['rva'] <= rva < section['rva'] + section['rawSize']:
                return section['offset'] + rva - section['rva']
        raise ValueError('RVA not in file')

    cli = file_offset(cli_rva)
    native_rva, native_size = struct.unpack_from('<II', data, cli + 64)
    r2r = native_rva != 0 and data[file_offset(native_rva):file_offset(native_rva) + 4] == b'RTR\0'
    return dict(machine=hex(machine), r2r=r2r, nativeHeaderRva=native_rva,
                nativeHeaderSize=native_size, size=len(data))


def mvid(path):
    data = Path(path).read_bytes()
    u16 = lambda at: struct.unpack_from('<H', data, at)[0]
    u32 = lambda at: struct.unpack_from('<I', data, at)[0]
    pe_at = u32(0x3c)
    optional = pe_at + 24
    directories = optional + (112 if u16(optional) == 0x20b else 96)
    sections = [optional + u16(pe_at + 20) + 40 * i for i in range(u16(pe_at + 6))]

    def offset(rva):
        for section in sections:
            if u32(section + 12) <= rva < u32(section + 12) + max(u32(section + 8), u32(section + 16)):
                return u32(section + 20) + rva - u32(section + 12)
        raise RuntimeError('metadata RVA outside sections')

    cli = offset(u32(directories + 14 * 8))
    root_rva = u32(cli + 8)
    root = offset(root_rva)
    if data[root:root + 4] != b'BSJB':
        raise RuntimeError('metadata signature missing')
    at = root + 16 + ((u32(root + 12) + 3) & ~3)
    count = u16(at + 2)
    at += 4
    streams = {}
    for _ in range(count):
        end = data.index(bytes([0]), at + 8)
        streams[data[at + 8:end].decode('ascii')] = u32(at)
        at = (end + 4) & ~3
    table = root + streams.get('#~', streams.get('#-'))
    flags = data[table + 6]
    valid = struct.unpack_from('<Q', data, table + 8)[0]
    row = table + 24 + 4 * bin(valid).count('1')
    string_size = 4 if flags & 1 else 2
    guid_size = 4 if flags & 2 else 2
    index = (u32 if guid_size == 4 else u16)(row + 2 + string_size)
    if not valid & 1 or index <= 0:
        raise RuntimeError('Module MVID absent')
    relative = streams['#GUID'] + 16 * (index - 1)
    value = data[root + relative:root + relative + 16]
    return dict(moduleMvid=str(uuid.UUID(bytes_le=value)),
                moduleMvidBytesHex=value.hex(), metadataRootRva=root_rva,
                moduleMvidRva=root_rva + relative)


def identity(path):
    return dict(path=str(path), sha256=sha(path), mvid=mvid(path)['moduleMvid'], pe=pe(path))


def clean_env(extra=None):
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(('DOTNET_', 'COMPLUS_', 'RUNECLR_', 'TRUSTED_'))}
    if extra:
        env.update(extra)
    return env


def collect_source_files(include_signed_ab=False):
    source_files = []
    trusted_source = ROOT / 'src/RuneCLR.TrustedUpdate'
    directories = [ROOT / 'samples/TrustedGame.Contracts', ROOT / 'samples/TrustedGame.Update',
                   ROOT / 'samples/TrustedGame.Host', trusted_source]
    if include_signed_ab:
        directories.extend([ROOT / 'samples/TrustedGame.UpdateV2',
                            ROOT / 'samples/TrustedGame.Publisher'])
    for directory in directories:
        for path in directory.rglob('*'):
            if not path.is_file() or 'bin' in path.parts or 'obj' in path.parts:
                continue
            if directory == trusted_source and path.suffix not in ('.cs', '.csproj'):
                continue
            source_files.append(path)
    for name in ('global.json', 'Directory.Build.props', 'Directory.Build.targets',
                 'Directory.Packages.props', 'NuGet.config'):
        path = ROOT / name
        if path.is_file():
            source_files.append(path)
    source_files.extend([ROOT / 'eng/trusted-game.ps1', ROOT / 'docs/trusted-game.md',
                         ROOT / 'docs/trusted-game-builds.md', Path(__file__)])
    return sorted(set(source_files))


class Runner:
    def __init__(self, output):
        self.output = output
        self.logs = output / 'logs'
        self.logs.mkdir(parents=True, exist_ok=True)
        self.commands = []

    def run(self, name, command, settings=None, timeout=600, check=True):
        command = [str(item) for item in command]
        started = datetime.now(timezone.utc).isoformat()
        stdout_file = self.logs / (name + '.stdout')
        stderr_file = self.logs / (name + '.stderr')
        record = dict(name=name, command=command, cwd=str(ROOT),
                      settings=dict(settings or {}), startStatus='starting',
                      startedUtc=started, stdout=str(stdout_file), stderr=str(stderr_file))
        self.commands.append(record)
        save(self.output / 'commands.json', self.commands)
        stdout_handle = stdout_file.open('wb')
        stderr_handle = stderr_file.open('wb')
        try:
            process = subprocess.Popen(command, cwd=ROOT, env=clean_env(settings),
                                       stdout=stdout_handle, stderr=stderr_handle)
        except OSError as error:
            stdout_handle.close()
            stderr_handle.close()
            record.update(startStatus='os-error', endedStatus='os-error',
                          endedUtc=datetime.now(timezone.utc).isoformat(),
                          failureType=type(error).__name__, failureMessage=str(error),
                          stdoutBytes=0, stderrBytes=0)
            save(self.output / 'commands.json', self.commands)
            raise RuntimeError('Command failed to start: ' + name + ' cwd=' + str(ROOT) +
                               ' ' + type(error).__name__ + ': ' + str(error)) from error
        record.update(startStatus='started', pid=process.pid)
        save(self.output / 'commands.json', self.commands)
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            timed_out = True
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        finally:
            stdout_handle.close()
            stderr_handle.close()
        stdout = stdout_file.read_bytes()
        stderr = stderr_file.read_bytes()
        process.stdout = stdout
        process.stderr = stderr
        if timed_out:
            record.update(endedStatus='timeout', endedUtc=datetime.now(timezone.utc).isoformat(),
                          timedOut=True, timeoutSeconds=timeout,
                          stdoutBytes=len(stdout), stderrBytes=len(stderr))
            save(self.output / 'commands.json', self.commands)
            raise RuntimeError('Command timed out: ' + name + ' timeout=' + str(timeout) +
                               ' stdout=' + str(stdout_file) + ' stderr=' + str(stderr_file))
        record.update(endedStatus='exited', endedUtc=datetime.now(timezone.utc).isoformat(),
                      exitCode=process.returncode, stdoutBytes=len(stdout), stderrBytes=len(stderr))
        save(self.output / 'commands.json', self.commands)
        if check and process.returncode != 0:
            text = (stdout + stderr).decode('utf-8-sig', errors='replace')
            raise RuntimeError('Command failed: ' + name + ' exit=' + str(process.returncode) +
                               ' output=' + text[-2000:])
        return process

    def text(self, process):
        return (process.stdout + process.stderr).decode('utf-8-sig', errors='replace')


def copy_files(source, destination, exclude=()):
    destination.mkdir(parents=True, exist_ok=True)
    excluded = set(exclude)
    for item in source.iterdir():
        if item.is_file() and item.name not in excluded:
            shutil.copy2(item, destination / item.name)


def resolve_tool(command):
    path = Path(command)
    if path.is_file():
        return path.resolve()
    found = shutil.which(command)
    if not found:
        raise RuntimeError('Executable not found on PATH or at path: ' + str(command))
    resolved = Path(found).resolve()
    if not resolved.is_file():
        raise RuntimeError('Resolved executable is not a file: ' + str(resolved))
    return resolved


def find_output(build_root, assembly):
    hits = [path for path in (build_root / 'bin').rglob(assembly)
            if path.is_file() and 'ref' not in path.parts]
    if len(hits) != 1:
        raise RuntimeError('Expected one ' + assembly + ' in artifacts path, got ' + str(hits))
    return hits[0]


def crossgen_one(runner, name, source, target, additional, framework, maps):
    references = {}
    for item in list(framework.glob('*.dll')) + list(additional):
        if item.name != source.name:
            references[item.name] = item
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [runner.crossgen, source, '-o', target, '--targetos', 'windows',
               '--targetarch', 'x64', '-O', '--map', '--mapcsv']
    command += ['-r:' + str(item) for item in references.values()]
    runner.run('crossgen-' + name, command, timeout=600)
    result = pe(target)
    if not result['r2r']:
        raise RuntimeError('Crossgen output lacks R2R header: ' + str(target))
    map_path = target.with_suffix('.map.csv')
    if not map_path.exists():
        map_path = target.with_suffix('.map')
    if not map_path.exists():
        map_path = None
    maps[name] = dict(path=str(map_path) if map_path else None,
                      sha256=sha(map_path) if map_path else None,
                      r2r=result)
    return result


def launch(runner, name, layout, host_dir, update_dir, framework_version, settings):
    host = host_dir / HOST_ASSEMBLY
    update = update_dir / UPDATE_ASSEMBLY
    module_sha = sha(update)
    command = [layout / 'dotnet.exe', 'exec', '--fx-version', framework_version,
               host, '--module', update, '--sha256', module_sha,
               '--approval', 'local-trusted-build']
    process = runner.run(name, command, settings=settings, timeout=120)
    text = runner.text(process)
    required = [
        'TRUSTED-GAME normal results=1,3,6 score=6 ticks=3',
        'TRUSTED-GAME negative failure=CallbackFailed next=Closed score=0',
        'TRUSTED-GAME OK',
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError('Functional output missing: ' + repr(missing))
    if 'TRUSTED-GAME FAILED' in text:
        raise RuntimeError('Functional run reported a failure')
    return dict(exitCode=process.returncode, moduleSha256=module_sha,
                stdout=str(runner.logs / (name + '.stdout')),
                stderr=str(runner.logs / (name + '.stderr')),
                checkedOutput=True)


def reject_wrong_hash(runner, name, layout, host_dir, update_dir, framework_version, settings):
    host = host_dir / HOST_ASSEMBLY
    update = update_dir / UPDATE_ASSEMBLY
    command = [layout / 'dotnet.exe', 'exec', '--fx-version', framework_version,
               host, '--module', update, '--sha256', '0' * 64,
               '--approval', 'local-trusted-build']
    process = runner.run(name, command, settings=settings, timeout=120, check=False)
    text = runner.text(process)
    if process.returncode != 3 or 'ContentHashMismatch' not in text:
        raise RuntimeError('Wrong-hash run did not reject with ContentHashMismatch/exit3')
    return dict(exitCode=process.returncode, failure='ContentHashMismatch',
                stdout=str(runner.logs / (name + '.stdout')),
                stderr=str(runner.logs / (name + '.stderr')))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, help='dotnet executable/command')
    parser.add_argument('--runtime', required=True, type=Path, help='runtime repository root')
    parser.add_argument('--output', required=True, type=Path, help='new artifact output directory')
    parser.add_argument('--configuration', default='Release')
    parser.add_argument('--framework-version', default='12.0.0')
    parser.add_argument('--dotnet-root', default=None, help='private testhost layout; defaults from runtime')
    parser.add_argument('--signed-ab', action='store_true',
                        help='also build Publisher/B, crossgen B, and sign/stage A/B signed layouts')
    return parser


def find_project_output(build_root, project_name, assembly):
    hits = [path for path in (build_root / 'bin' / project_name).rglob(assembly)
            if path.is_file() and 'ref' not in path.parts]
    if len(hits) != 1:
        raise RuntimeError('Expected one ' + assembly + ' under bin/' + project_name + ', got ' + str(hits))
    return hits[0]


def signed_package_hashes(path):
    lines = Path(path).read_text(encoding='utf-8').splitlines()
    if len(lines) < 3 or lines[0] != 'RTRSIG1':
        raise RuntimeError('Unexpected signed envelope: ' + str(path))
    payload = json.loads('\n'.join(lines[2:]))
    return {item['path']: item['sha256'].lower() for item in payload.get('files', [])}


def find_staged_module(releases_root, receipt_path):
    receipt = json.loads(Path(receipt_path).read_text(encoding='utf-8'))
    relative = receipt.get('contentRoot')
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise RuntimeError('Receipt has no safe contentRoot: ' + str(receipt_path))
    root = Path(releases_root).resolve()
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise RuntimeError('Receipt contentRoot escapes releases root: ' + relative)
    hits = [path for path in target.rglob(UPDATE_ASSEMBLY) if path.is_file()]
    if len(hits) != 1:
        raise RuntimeError('Expected one staged ' + UPDATE_ASSEMBLY + ' under receipt contentRoot ' +
                           str(target) + ', got ' + str(hits))
    return hits[0]


def publish_layout(runner, sdk_path, publisher, layout, version, signed, spki, private_key, label):
    signed.parent.mkdir(parents=True, exist_ok=True)
    command = [sdk_path, publisher, '--module', layout / UPDATE_ASSEMBLY,
               '--version', version, '--entry-type', 'TrustedGame.Update.GameRules',
               '--entry-method', 'Entry', '--signed', signed, '--spki', spki,
               '--private-key', private_key, '--content-root', layout,
               '--runtime', 'net11.0', '--architecture', 'x64']
    process = runner.run('signed-' + label + '-publish', command, timeout=120)
    text = runner.text(process)
    if 'PUBLISHER OK' not in text:
        raise RuntimeError('Publisher did not report success: ' + label)
    module_sha = sha(layout / UPDATE_ASSEMBLY)
    hashes = signed_package_hashes(signed)
    if hashes.get(UPDATE_ASSEMBLY) != module_sha:
        raise RuntimeError('Signed payload hash does not match layout input: ' + label)
    return dict(exitCode=process.returncode, signed=str(signed), spki=str(spki),
                moduleSha256=module_sha, signedSha256=sha(signed),
                signedFileHashes=hashes,
                stdout=str(runner.logs / ('signed-' + label + '-publish.stdout')),
                stderr=str(runner.logs / ('signed-' + label + '-publish.stderr')))


def parse_signed_facts(text, mode, multiplier, version, source):
    rows = [line for line in text.splitlines() if line.startswith('SIGNED-FACTS ')]
    if len(rows) != 1:
        raise RuntimeError('Expected exactly one SIGNED-FACTS row, got ' + str(len(rows)))
    fields = {}
    for token in rows[0].split()[1:]:
        if '=' not in token:
            raise RuntimeError('Malformed SIGNED-FACTS token: ' + token)
        key, value = token.split('=', 1)
        if key in fields:
            raise RuntimeError('Duplicate SIGNED-FACTS key: ' + key)
        fields[key] = value
    expected = {
        'mode': mode,
        'stage': 'OK' if mode == 'stage' else 'NA',
        'stageDetail': '',
        'expectedScoreMultiplier': str(multiplier),
        'candidateVerification': 'None',
        'candidatePlan': 'None',
        'candidateActivation': 'None',
        'recoveryVerification': 'None',
        'recoveryPlan': 'None',
        'recoveryActivation': 'None',
        'persistence': 'None',
        'persistenceDetail': '',
        'activated': 'True',
        'source': source,
        'version': version,
        'activatorCalls': '1',
    }
    for key, value in expected.items():
        if fields.get(key) != value:
            raise RuntimeError('SIGNED-FACTS ' + key + '=' + str(fields.get(key)) +
                               ', expected ' + value)
    return fields


def check_signed_gameplay(text, multiplier):
    expected = {1: (1, 3, 6), 2: (2, 6, 12)}[multiplier]
    required = [
        'TRUSTED-GAME normal results=' + ','.join(map(str, expected)) +
        ' score=' + str(expected[2]) + ' ticks=3 multiplier=' + str(multiplier),
        'TRUSTED-GAME negative failure=CallbackFailed next=Closed score=0',
        'TRUSTED-GAME OK',
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError('Signed gameplay output missing: ' + repr(missing))
    if 'TRUSTED-GAME FAILED' in text:
        raise RuntimeError('Signed gameplay reported a failure')


def run_signed_host(runner, runtime_dotnet, host, host_args, name, settings,
                    framework_version, multiplier, expected_mode, version, source):
    command = [runtime_dotnet, 'exec', '--fx-version', framework_version, host] + host_args
    process = runner.run(name, command, settings=settings, timeout=120)
    text = runner.text(process)
    parse_signed_facts(text, expected_mode, multiplier, version, source)
    check_signed_gameplay(text, multiplier)
    return dict(exitCode=process.returncode,
                stdout=str(runner.logs / (name + '.stdout')),
                stderr=str(runner.logs / (name + '.stderr')))


def exercise_signed_ab(runner, sdk_path, publisher, runtime_dotnet, host_layout,
                       update_a, update_b, framework_version, settings, root, label):
    base = root / ('signed-' + label)
    base.mkdir(parents=True, exist_ok=True)
    host = host_layout / HOST_ASSEMBLY
    module_a = update_a / UPDATE_ASSEMBLY
    module_b = update_b / UPDATE_ASSEMBLY
    if sha(module_a) == sha(module_b):
        raise RuntimeError('A/B layout hashes are not distinct: ' + label)
    if mvid(module_a)['moduleMvid'] == mvid(module_b)['moduleMvid']:
        raise RuntimeError('A/B layout MVIDs are not distinct: ' + label)

    signed_a = base / 'A.signed.json'
    signed_b = base / 'B.signed.json'
    spki = base / 'demo.spki'
    private_key = base / 'demo.private.pem'
    releases = base / 'releases'
    receipt = base / 'receipt.json'

    pub_a = publish_layout(runner, sdk_path, publisher, update_a, 'game-rules-a',
                           signed_a, spki, private_key, label + '-A')
    stage_a = run_signed_host(
        runner, runtime_dotnet, host,
        ['--stage-signed', update_a, '--signed', signed_a, '--spki', spki,
         '--releases-root', releases, '--receipt', receipt,
         '--expected-score-multiplier', '1'],
        'signed-' + label + '-stage-A', settings, framework_version, 1, 'stage',
        'game-rules-a', 'Candidate')
    receipt_a = sha(receipt)
    staged_a = find_staged_module(releases, receipt)
    if sha(staged_a) != sha(module_a):
        raise RuntimeError('Staged A bytes do not match ' + label + ' layout input')

    pub_b = publish_layout(runner, sdk_path, publisher, update_b, 'game-rules-b',
                           signed_b, spki, private_key, label + '-B')
    stage_b = run_signed_host(
        runner, runtime_dotnet, host,
        ['--stage-signed', update_b, '--signed', signed_b, '--spki', spki,
         '--releases-root', releases, '--receipt', receipt,
         '--expected-score-multiplier', '2'],
        'signed-' + label + '-stage-B', settings, framework_version, 2, 'stage',
        'game-rules-b', 'Candidate')
    receipt_b = sha(receipt)
    if receipt_a == receipt_b:
        raise RuntimeError('Receipt did not change from A to B: ' + label)
    staged_b = find_staged_module(releases, receipt)
    if sha(staged_b) != sha(module_b):
        raise RuntimeError('Staged B bytes do not match ' + label + ' layout input')
    recover_b = run_signed_host(
        runner, runtime_dotnet, host,
        ['--recover-signed', '--spki', spki, '--releases-root', releases,
         '--receipt', receipt, '--expected-score-multiplier', '2'],
        'signed-' + label + '-recover-B', settings, framework_version, 2, 'recover',
        'game-rules-b', 'LastKnownGood')
    receipt_after_recover = sha(receipt)
    if receipt_b != receipt_after_recover:
        raise RuntimeError('Receipt B changed during fresh recovery: ' + label)
    wrong_b = reject_wrong_hash(runner, 'signed-' + label + '-wrong-hash-B',
                                runtime_dotnet.parent, host_layout, update_b,
                                framework_version, settings)
    return dict(
        A=dict(publisher=pub_a, stage=stage_a, staged=str(staged_a),
               signedFileHashes=pub_a['signedFileHashes'], moduleSha256=sha(module_a),
               moduleMvid=mvid(module_a)['moduleMvid']),
        B=dict(publisher=pub_b, stage=stage_b, recover=recover_b, staged=str(staged_b),
               signedFileHashes=pub_b['signedFileHashes'], moduleSha256=sha(module_b),
               moduleMvid=mvid(module_b)['moduleMvid']),
        shared=dict(spki=str(spki), releases=str(releases), receipt=str(receipt)),
        receiptA=receipt_a,
        receiptB=dict(path=str(receipt), before=receipt_b, after=receipt_after_recover,
                      changedFromA=receipt_a != receipt_b,
                      stableOnRecovery=receipt_b == receipt_after_recover),
        wrongHashB=wrong_b,
    )

def main():
    parser = build_parser()
    args = parser.parse_args()
    signed_ab = args.signed_ab

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    runtime = args.runtime.resolve()
    build = runtime / 'artifacts/bin/coreclr/windows.x64.Checked'
    layout = (Path(args.dotnet_root).resolve() if args.dotnet_root else
              runtime / 'artifacts/bin/testhost/net11.0-windows-Release-x64')
    framework = layout / 'shared/Microsoft.NETCore.App' / args.framework_version
    crossgen = build / 'crossgen2-published/crossgen2.exe'
    runner = Runner(output)
    result = dict(passed=False, acceptance=False, configuration=args.configuration,
                  frameworkVersion=args.framework_version, target='windows-x64')

    try:
        sdk_path = resolve_tool(args.sdk)
        for path in (build, layout, framework, crossgen, layout / 'dotnet.exe'):
            if not path.exists():
                raise RuntimeError('Missing runtime/tool input: ' + str(path))
        runner.crossgen = crossgen
        for name in ('coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll'):
            if sha(build / name) != sha(framework / name):
                raise RuntimeError('Private package differs from Checked build: ' + name)
        cache = runtime / 'artifacts/obj/coreclr/windows.x64.Checked/CMakeCache.txt'
        if not cache.exists() or 'CMAKE_BUILD_TYPE:STRING=Checked' not in cache.read_text(errors='replace'):
            raise RuntimeError('Checked build provenance missing')
        shutil.copy2(cache, output / 'runtime-CMakeCache.txt')

        source_files = collect_source_files(signed_ab)
        source_hashes = {}
        for path in source_files:
            relative = path.relative_to(ROOT) if path.is_relative_to(ROOT) else Path(path.name)
            target = output / 'source' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            source_hashes[str(path)] = sha(path)
        save(output / 'source-pins.json', source_hashes)

        sdk_version = runner.run('sdk-version', [sdk_path, '--version']).stdout.decode('utf-8-sig', errors='replace').strip()
        runner.run('sdk-info', [sdk_path, '--info'], timeout=120)
        crossgen_version = runner.run('crossgen-version', [crossgen, '--version']).stdout.decode('utf-8-sig', errors='replace').strip()
        runner.run('runtime-commit', ['git', '-C', runtime, 'rev-parse', 'HEAD'])
        runner.run('runtime-status', ['git', '-C', runtime, 'status', '--porcelain'])

        build_root = output / 'build'
        build_root.mkdir(parents=True)
        runner.run('build-host', [sdk_path, 'build', HOST_PROJECT, '-c', args.configuration,
                                  '--artifacts-path', build_root, '--nologo'], timeout=1200)
        host_dll = find_output(build_root, HOST_ASSEMBLY)
        host_dir = host_dll.parent
        resident = {name: host_dir / name for name in (HOST_ASSEMBLY, CONTRACTS_ASSEMBLY, TRUSTED_ASSEMBLY)}
        for name, path in resident.items():
            if not path.exists():
                raise RuntimeError('Resident assembly missing after Host build: ' + str(path))
        resident_before = {name: dict(path=str(path), sha256=sha(path)) for name, path in resident.items()}
        host_deps = host_dir / 'TrustedGame.Host.deps.json'
        if not host_deps.exists():
            raise RuntimeError('Host deps file missing')
        host_deps_has_update = 'TrustedGame.Update' in host_deps.read_text(errors='replace')

        runner.run('build-update', [sdk_path, 'build', UPDATE_PROJECT, '-c', args.configuration,
                                    '--artifacts-path', build_root, '--nologo',
                                    '-p:BuildProjectReferences=false'], timeout=1200)
        update_dll = find_output(build_root, UPDATE_ASSEMBLY)
        update_dir = update_dll.parent
        resident_after = {name: dict(path=str(path), sha256=sha(path)) for name, path in resident.items()}
        if resident_before != resident_after:
            raise RuntimeError('Resident Host/Contracts/TrustedUpdate hashes changed during Update build')
        if (host_dir / UPDATE_ASSEMBLY).exists() or host_deps_has_update:
            raise RuntimeError('Host output/deps unexpectedly contains the late Update')

        publisher_dll = None
        update_b_dll = None
        publisher_dir = None
        update_b_dir = None
        resident_after_signed = resident_after
        if signed_ab:
            runner.run('build-publisher', [sdk_path, 'build', PUBLISHER_PROJECT, '-c', args.configuration,
                                           '--artifacts-path', build_root, '--nologo',
                                           '-p:BuildProjectReferences=false'], timeout=1200)
            publisher_dll = find_project_output(build_root, 'TrustedGame.Publisher', PUBLISHER_ASSEMBLY)
            publisher_dir = publisher_dll.parent
            runner.run('build-update-b', [sdk_path, 'build', UPDATE_B_PROJECT, '-c', args.configuration,
                                          '--artifacts-path', build_root, '--nologo',
                                          '-p:BuildProjectReferences=false'], timeout=1200)
            update_b_dll = find_project_output(build_root, 'TrustedGame.UpdateV2', UPDATE_ASSEMBLY)
            update_b_dir = update_b_dll.parent
            resident_after_signed = {name: dict(path=str(path), sha256=sha(path))
                                     for name, path in resident.items()}
            if resident_before != resident_after_signed:
                raise RuntimeError('Resident Host/Contracts/TrustedUpdate hashes changed during Publisher/B build')

        il_host = output / 'il/host'
        il_update = output / 'il/update'
        copy_files(host_dir, il_host, exclude=(UPDATE_ASSEMBLY,))
        copy_files(update_dir, il_update, exclude=(CONTRACTS_ASSEMBLY, HOST_ASSEMBLY, TRUSTED_ASSEMBLY))
        runtime_config = {
            'runtimeOptions': {
                'tfm': 'net11.0',
                'framework': {'name': 'Microsoft.NETCore.App', 'version': args.framework_version},
                'rollForward': 'Disable',
            }
        }
        save(il_host / 'TrustedGame.Host.runtimeconfig.json', runtime_config)

        il_update_b = None
        r2r_update_b = None
        if signed_ab:
            il_update_b = output / 'il/update-b'
            copy_files(update_b_dir, il_update_b,
                       exclude=(CONTRACTS_ASSEMBLY, HOST_ASSEMBLY, TRUSTED_ASSEMBLY))
        r2r_host = output / 'r2r/host'
        r2r_update = output / 'r2r/update'
        shutil.copytree(il_host, r2r_host)
        shutil.copytree(il_update, r2r_update)
        if signed_ab:
            r2r_update_b = output / 'r2r/update-b'
            shutil.copytree(il_update_b, r2r_update_b)
        maps = {}
        crossgen_one(runner, 'contracts', il_host / CONTRACTS_ASSEMBLY,
                     r2r_host / CONTRACTS_ASSEMBLY, [], framework, maps)
        crossgen_one(runner, 'trusted-update', il_host / TRUSTED_ASSEMBLY,
                     r2r_host / TRUSTED_ASSEMBLY, [], framework, maps)
        host_refs = [path for path in il_host.glob('*.dll')
                     if path.name not in (HOST_ASSEMBLY, CONTRACTS_ASSEMBLY, TRUSTED_ASSEMBLY)]
        crossgen_one(runner, 'host', il_host / HOST_ASSEMBLY, r2r_host / HOST_ASSEMBLY,
                     host_refs + [il_host / CONTRACTS_ASSEMBLY, il_host / TRUSTED_ASSEMBLY], framework, maps)
        crossgen_one(runner, 'update', il_update / UPDATE_ASSEMBLY, r2r_update / UPDATE_ASSEMBLY,
                     [il_host / CONTRACTS_ASSEMBLY], framework, maps)
        if signed_ab:
            crossgen_one(runner, 'update-b', il_update_b / UPDATE_ASSEMBLY,
                         r2r_update_b / UPDATE_ASSEMBLY,
                         [il_host / CONTRACTS_ASSEMBLY], framework, maps)
        save(output / 'image-maps.json', maps)

        logical = {
            'Host': (il_host / HOST_ASSEMBLY, r2r_host / HOST_ASSEMBLY),
            'Contracts': (il_host / CONTRACTS_ASSEMBLY, r2r_host / CONTRACTS_ASSEMBLY),
            'TrustedUpdate': (il_host / TRUSTED_ASSEMBLY, r2r_host / TRUSTED_ASSEMBLY),
            'Update': (il_update / UPDATE_ASSEMBLY, r2r_update / UPDATE_ASSEMBLY),
        }
        if signed_ab:
            logical['UpdateB'] = (il_update_b / UPDATE_ASSEMBLY, r2r_update_b / UPDATE_ASSEMBLY)
        products = {}
        for name, (il_path, r2r_path) in logical.items():
            il_id = identity(il_path)
            r2r_id = identity(r2r_path)
            if il_id['mvid'] != r2r_id['mvid']:
                raise RuntimeError('MVID changed across IL/R2R: ' + name)
            if il_id['pe']['r2r'] or not r2r_id['pe']['r2r']:
                raise RuntimeError('Unexpected IL/R2R PE kind: ' + name)
            products[name] = dict(originalIl=il_id, ilLayout=il_id, r2rLayout=r2r_id)
        save(output / 'products.json', products)

        settings = {
            'DOTNET_ROOT': str(layout),
            'DOTNET_ReadyToRun': '1',
            'DOTNET_InterpMode': '1',
            'DOTNET_TieredCompilation': '0',
            'DOTNET_TC_QuickJit': '0',
            'DOTNET_TC_OnStackReplacement': '0',
            'DOTNET_MULTILEVEL_LOOKUP': '0',
            'DOTNET_ROLL_FORWARD': 'Disable',
        }
        functional = {}
        rejection = {}
        for label, host_layout, update_layout in (('il', il_host, il_update), ('r2r', r2r_host, r2r_update)):
            functional[label] = launch(runner, label + '-functional', layout, host_layout,
                                       update_layout, args.framework_version, settings)
            rejection[label] = reject_wrong_hash(runner, label + '-wrong-hash', layout,
                                                 host_layout, update_layout, args.framework_version, settings)

        signed_ab_result = {}
        if signed_ab:
            for label, host_layout, update_a_layout, update_b_layout in (
                    ('il', il_host, il_update, il_update_b),
                    ('r2r', r2r_host, r2r_update, r2r_update_b)):
                signed_ab_result[label] = exercise_signed_ab(
                    runner, sdk_path, publisher_dll, layout / 'dotnet.exe', host_layout,
                    update_a_layout, update_b_layout,
                    args.framework_version, settings, output, label)

        runtime_hashes = {}
        for name in ('coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll'):
            runtime_hashes[str(framework / name)] = sha(framework / name)
        runtime_hashes[str(crossgen)] = sha(crossgen)
        runtime_hashes[str(layout / 'dotnet.exe')] = sha(layout / 'dotnet.exe')
        build_result = dict(host=str(host_dll), update=str(update_dll),
                            residentBefore=resident_before, residentAfter=resident_after,
                            hostDepsHasUpdate=host_deps_has_update)
        layouts_result = dict(il=dict(host=str(il_host), update=str(il_update)),
                              r2r=dict(host=str(r2r_host), update=str(r2r_update)))
        result_status = 'functional IL/R2R passed; R2R artifact proof recorded; execution mode not proven'
        unproven = ['actual Host/Update execution mode', 'R2R vs interpreter method selection',
                    'whole-method/native coverage', 'performance', 'unload', 'iOS/mobile/device']
        if signed_ab:
            build_result.update(publisher=str(publisher_dll), updateB=str(update_b_dll),
                                residentAfterSigned=resident_after_signed)
            layouts_result['ilB'] = dict(update=str(il_update_b))
            layouts_result['r2rB'] = dict(update=str(r2r_update_b))
            result_status += '; signed A/B staging/recovery passed; gameplay is not execution-mode proof'
            unproven.append('signed A/B gameplay vs executed method mode')
        result.update(
            passed=True,
            status=result_status,
            sdk=dict(command=str(args.sdk), path=str(sdk_path), sha256=sha(sdk_path), version=sdk_version),
            sourceScope='captured project-source/build-config set; not a full compiler/reference/pack closure',
            crossgen=dict(path=str(crossgen), version=crossgen_version),
            runtime=dict(root=str(runtime), layout=str(layout), framework=str(framework),
                         buildConfiguration='Checked', hashes=runtime_hashes),
            sourcePins=source_hashes,
            build=build_result,
            layouts=layouts_result,
            functional=functional,
            wrongHash=rejection,
            artifactProof=dict(
                ilAllR2R=False,
                r2rAllR2R=True,
                images={name: dict(il=value['ilLayout']['pe'], r2r=value['r2rLayout']['pe'])
                        for name, value in products.items()},
                note='R2R PE headers prove artifact kind; they do not prove which method body actually executed.'),
            executionMode='not proven: no observer, dump, debugger, native PC or interpreter mode proof',
            switches=settings,
            unproven=unproven,
        )
        if signed_ab:
            result['signedAb'] = signed_ab_result
        save(output / 'results.json', result)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as error:
        result.update(passed=False, error=str(error))
        save(output / 'results.json', result)
        print(json.dumps(result, indent=2))
        return 1


if __name__ == '__main__':
    sys.exit(main())
