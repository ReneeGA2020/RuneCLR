#!/usr/bin/env python3
"""Build independent trusted IL/R2R modules and measure Windows mixed execution."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
FIXTURE = ROOT / 'eng/trusted-composition'


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
        sections.append(dict(rva=rva, size=max(virtual_size, raw_size), rawSize=raw_size, offset=offset, executable=bool(flags & 0x20000000)))

    def file_offset(rva):
        for section in sections:
            if section['rva'] <= rva < section['rva'] + section['rawSize']:
                return section['offset'] + rva - section['rva']
        raise ValueError('RVA not in file')

    cli = file_offset(cli_rva)
    native_rva, native_size = struct.unpack_from('<II', data, cli + 64)
    r2r = native_rva != 0 and data[file_offset(native_rva):file_offset(native_rva) + 4] == b'RTR\0'
    return dict(machine=hex(machine), r2r=r2r, nativeHeaderRva=native_rva, nativeHeaderSize=native_size, sections=sections)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sdk', default='dotnet')
    parser.add_argument('--allow-known-collectible-blocker', action='store_true',
                        help='Return zero if measured controls pass despite the explicitly reported runtime blocker.')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    runtime = args.runtime.resolve()
    build = runtime / 'artifacts/bin/coreclr/windows.x64.Checked'
    layout = runtime / 'artifacts/bin/testhost/net11.0-windows-Release-x64'
    framework = layout / 'shared/Microsoft.NETCore.App/12.0.0'
    crossgen = build / 'crossgen2-published/crossgen2.exe'
    runs = []

    def execute(name, command, settings=None, timeout=180):
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(('DOTNET_', 'COMPLUS_', 'RUNECLR_', 'TRUSTED_COMPOSITION_', '__TEST'))}
        env.update(settings or {})
        started = datetime.now(timezone.utc).isoformat()
        process = subprocess.run([str(item) for item in command], cwd=ROOT, env=env,
                                 capture_output=True, timeout=timeout)
        (output / (name + '.stdout')).write_bytes(process.stdout)
        (output / (name + '.stderr')).write_bytes(process.stderr)
        record = dict(name=name, command=[str(item) for item in command], settings=settings or {},
                      startedUtc=started, exitCode=process.returncode)
        runs.append(record)
        save(output / 'commands.json', runs)
        if process.returncode:
            raise RuntimeError('Command failed: ' + name + '; see ' + str(output / (name + '.stderr')))
        return (process.stdout + process.stderr).decode('utf-8-sig', errors='replace')

    try:
        shutil.copy2(__file__, output / 'driver.py')
        commit = execute('runtime-commit', ['git', '-C', runtime, 'rev-parse', 'HEAD']).strip()
        state = execute('runtime-state', ['git', '-C', runtime, 'status', '--porcelain']).strip()
        if commit != BASE or state:
            raise RuntimeError('This scoped probe requires the clean pinned upstream runtime ' + BASE)
        execute('runtime-branch', ['git', '-C', runtime, 'branch', '--show-current'])
        source_hashes = {}
        for file in list(FIXTURE.rglob('*.cs')) + list(FIXTURE.rglob('*.csproj')) + [
                Path(__file__), ROOT / 'eng/trusted-composition-evidence.py',
                ROOT / 'eng/verify-trusted-composition-evidence.py',
                ROOT / 'eng/verify-trusted-composition-loader.py',
                ROOT / 'eng/windows-entry-observation/WindowsEntryObservation.cs', ROOT / 'Directory.Build.props']:
            if 'obj' in file.parts or 'bin' in file.parts:
                continue
            destination = output / 'source' / file.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, destination)
            source_hashes[str(file)] = sha(file)
        save(output / 'source-hashes.json', source_hashes)
        bindings = {}
        for name in ('coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll'):
            if sha(build / name) != sha(framework / name):
                raise RuntimeError('Private host does not match Checked build: ' + name)
            bindings[str(framework / name)] = sha(framework / name)
        cache = runtime / 'artifacts/obj/coreclr/windows.x64.Checked/CMakeCache.txt'
        cache_text = cache.read_text()
        if BASE not in cache_text or 'CMAKE_BUILD_TYPE:STRING=Checked' not in cache_text:
            raise RuntimeError('Checked source configuration does not match.')
        shutil.copy2(cache, output / 'runtime-CMakeCache.txt')
        native_stamp = execute('runtime-stamp', ['powershell', '-NoProfile', '-Command',
            "(Get-Item -LiteralPath '" + str(build / 'coreclr.dll').replace("'", "''") + "').VersionInfo.ProductVersion"]).strip()
        if BASE not in native_stamp:
            raise RuntimeError('Native CoreCLR stamp does not match source.')
        for file in framework.glob('*.dll'):
            bindings[str(file)] = sha(file)
        for file in (crossgen, layout / 'dotnet.exe'):
            bindings[str(file)] = sha(file)
        for file in (runtime / 'src/coreclr/vm/readytoruninfo.cpp', runtime / 'src/coreclr/vm/eeconfig.cpp'):
            bindings[str(file)] = sha(file)
            shutil.copy2(file, output / file.name)
        sdk_version = execute('sdk-version', [args.sdk, '--version']).strip()
        execute('sdk-info', [args.sdk, '--info'])
        crossgen_version = execute('crossgen-version', [crossgen, '--version']).strip()
        execute('build', [args.sdk, 'build', FIXTURE / 'Host/TrustedComposition.Host.csproj', '-c', 'Release', '-t:Rebuild'], timeout=600)
        compiler_inputs = json.loads(execute('compiler-inputs', [args.sdk, 'msbuild',
            FIXTURE / 'Host/TrustedComposition.Host.csproj', '-t:ResolveReferences', '-p:Configuration=Release',
            '-getItem:ReferencePath', '-getProperty:LangVersion,RoslynTargetsPath,TargetFramework']))
        compiler_hashes = {item['FullPath']: sha(item['FullPath'])
                           for item in compiler_inputs['Items']['ReferencePath']}
        csc = Path(compiler_inputs['Properties']['RoslynTargetsPath']) / 'bincore/csc.dll'
        compiler_hashes[str(csc)] = sha(csc)
        save(output / 'compiler-reference-hashes.json', compiler_hashes)
        save(output / 'inputs.json', dict(runtimeCommit=commit, nativeStamp=native_stamp, sdk=sdk_version,
             crossgenVersion=crossgen_version, target='windows-x64', configuration='Checked runtime / Release managed',
             runtimeHashes=bindings, sourceHashes=source_hashes, globalJsonPresent=(ROOT / 'global.json').exists(),
             language=compiler_inputs['Properties']['LangVersion'], sourceTargetFramework='net11.0',
             executionFramework='12.0.0 source build', compilerHashes=compiler_hashes, composite=False))

        def built(project, assembly=None):
            return FIXTURE / project / 'bin/Release/net11.0' / ((assembly or 'TrustedComposition.' + project) + '.dll')

        host_il = output / 'il/host'
        host_il.mkdir(parents=True)
        for file in built('Host').parent.iterdir():
            if file.suffix in ('.dll', '.json'):
                shutil.copy2(file, host_il / file.name)
        update_il = output / 'il/updates'
        for version in ('A', 'B'):
            directory = update_il / version
            directory.mkdir(parents=True)
            for project, assembly in [('Update.' + version, None), ('Private.' + version, 'TrustedComposition.Private'),
                                      ('IlOnlyHelper', None)]:
                file = built(project, assembly)
                shutil.copy2(file, directory / file.name)
        host_r2r = output / 'r2r/host'
        shutil.copytree(host_il, host_r2r)
        updates_r2r = output / 'r2r/updates'
        shutil.copytree(update_il, updates_r2r)
        maps = {}
        reference_hashes = {}

        def compile_one(name, source, target, additional):
            references = sorted(framework.glob('*.dll')) + list(additional)
            unique = {file.name: file for file in references if file.name != source.name}
            command = [crossgen, source, '-o', target, '--targetos', 'windows', '--targetarch', 'x64',
                       '-O', '--map', '--mapcsv'] + ['-r:' + str(file) for file in unique.values()]
            execute('crossgen-' + name, command)
            for file in unique.values():
                reference_hashes[str(file)] = sha(file)
            maps[sha(target)] = str(target.with_suffix('.map.csv'))
            if not pe(target)['r2r']:
                raise RuntimeError('Crossgen output lacks R2R header: ' + str(target))

        compile_one('contract', built('Contract'), host_r2r / 'TrustedComposition.Contract.dll', [])
        compile_one('host', built('Host'), host_r2r / 'TrustedComposition.Host.dll', [built('Contract')])
        for version in ('A', 'B'):
            private = built('Private.' + version, 'TrustedComposition.Private')
            helper = built('IlOnlyHelper')
            compile_one('private-' + version, private, updates_r2r / version / private.name, [built('Contract')])
            update = built('Update.' + version)
            compile_one('update-' + version, update, updates_r2r / version / update.name, [built('Contract'), helper, private])
        for version in ('A', 'B'):
            if pe(updates_r2r / version / 'TrustedComposition.IlOnlyHelper.dll')['r2r']:
                raise RuntimeError('Helper must remain IL-only.')
        save(output / 'reference-hashes.json', reference_hashes)
        save(output / 'image-maps.json', maps)
        map_hashes = {path: sha(path) for path in maps.values()}
        save(output / 'map-hashes.json', map_hashes)
        products = {}
        for directory in (output / 'il', output / 'r2r'):
            for file in directory.rglob('*.dll'):
                products[str(file)] = dict(sha256=sha(file), pe=pe(file))
        save(output / 'products.json', products)
        spec = importlib.util.spec_from_file_location('composition_evidence', ROOT / 'eng/trusted-composition-evidence.py')
        evidence = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(evidence)
        common = dict(DOTNET_ReadyToRun='1', DOTNET_TieredCompilation='0', DOTNET_TC_OnStackReplacement='0',
                      DOTNET_InterpMode='1', DOTNET_MULTILEVEL_LOOKUP='0', DOTNET_InterpList='1',
                      DOTNET_InterpDump='*:Compute', RUNECLR_POST_EXECUTION_PRECODE='1', TRUSTED_COMPOSITION_WITNESS='1')
        results = []
        expected_behavior = None
        lanes = [('il-collectible', update_il, True, False, '1'),
                 ('r2r-collectible', updates_r2r, True, False, '1'),
                 ('r2r-native', updates_r2r, False, False, '1'),
                 ('il-jit-control', update_il, True, True, '1'),
                 ('r2r-disabled-control', updates_r2r, False, False, '0')]
        for name, updates, collectible, jit, r2r in lanes:
            settings = dict(common, DOTNET_InterpMode='0' if jit else '1', DOTNET_ReadyToRun=r2r,
                            DOTNET_ReadyToRunLogFile=str(output / (name + '.r2r-log')))
            args_cli = ['--updates', updates, '--observe', '--report', output / (name + '.json')]
            expected_interpreter = not jit and (collectible or r2r == '0')
            if expected_interpreter:
                args_cli.append('--expect-interpreted')
            if not collectible:
                args_cli.append('--noncollectible')
            if jit:
                args_cli.append('--jit-control')
            # All lanes keep the host R2R enabled except the explicit disabled control.
            if r2r == '0':
                args_cli.append('--expect-host-interpreted')
            text = execute(name, [layout / 'dotnet.exe', 'exec', '--fx-version', '12.0.0',
                                  host_r2r / 'TrustedComposition.Host.dll'] + args_cli, settings)
            report = json.loads((output / (name + '.json')).read_text(encoding='utf-8-sig'))
            if not report or not report['Passed']:
                raise RuntimeError('Missing functional report: ' + name)
            save(output / (name + '.json'), report)
            behavior = [dict(version=session['Version'], calls=session['Calls'], error=session['ErrorType'])
                        for session in report['Sessions']]
            if expected_behavior is None:
                expected_behavior = behavior
            elif behavior != expected_behavior:
                raise RuntimeError('Same-source behavior differs between IL/R2R lanes: ' + name)
            native = evidence.assess_witnesses(report['Witnesses'], maps)
            if name == 'r2r-native':
                if not all(native['labels'][label]['passed'] for label in ('host', 'update', 'private')):
                    raise RuntimeError('Missing actual selected native R2R frame: ' + name)
                for session in report['Sessions']:
                    for label in ('update', 'private'):
                        if not any(match['label'] == label and Path(match['image']).parent == Path(session['Directory'])
                                   for match in native['matches']):
                            raise RuntimeError('Missing native R2R frame for session: ' + session['Directory'] + '/' + label)
            elif any(native['labels'][label]['passed'] for label in ('update', 'private')):
                raise RuntimeError('Native negative control unexpectedly has update R2R frames: ' + name)
            if r2r == '1' and not jit and not native['labels']['host']['passed']:
                raise RuntimeError('Host native witness missing: ' + name)
            if r2r == '0' and native['labels']['host']['passed']:
                raise RuntimeError('R2R-disabled control has native host witness')
            helper_entries = [entry['Entry'] for session in report['Sessions'] for entry in session['Entries']
                              if entry['Entry']['Method'] == 'Compute']
            if len(helper_entries) != 5 or any(entry['Interpreted'] == jit for entry in helper_entries):
                raise RuntimeError('Helper post-invocation evidence differs: ' + name)
            interpreter = evidence.assess_interpreter(report, text) if not jit else None
            dump = bool(re.search(r'^Compiled method: .*TrustedComposition\.IlOnlyHelper:Compute\(', text, re.MULTILINE))
            if jit and dump:
                raise RuntimeError('JIT control unexpectedly emitted helper interpreter dump')
            logs = list(output.glob(name + '.r2r-log.*'))
            disabled = any('Ready to Run disabled - collectible module' in file.read_text(errors='replace') for file in logs)
            if collectible and r2r == '1' and not disabled:
                raise RuntimeError('Collectible R2R refusal reason missing: ' + name)
            results.append(dict(name=name, functional=True, collected=sum(session['Collected'] for session in report['Sessions']),
                                native=native, helperInterpreter=not jit, helperDump=dump, interpreterEvidence=interpreter,
                                collectibleR2RRefused=disabled))
            save(output / 'lanes.json', results)
        execute('evidence-regressions', [sys.executable, '-B', ROOT / 'eng/verify-trusted-composition-evidence.py',
                                        '--evidence', output])
        execute('loader-regressions', [sys.executable, '-B', ROOT / 'eng/verify-trusted-composition-loader.py',
                                      '--evidence', output, '--runtime', runtime], timeout=600)
        if execute('runtime-final-state', ['git', '-C', runtime, 'status', '--porcelain']).strip():
            raise RuntimeError('Runtime working tree changed during execution.')
        for path, expected in {**bindings, **source_hashes, **reference_hashes, **compiler_hashes, **map_hashes}.items():
            if sha(path) != expected:
                raise RuntimeError('Frozen input changed: ' + path)
        result = dict(controlsPassed=True, milestoneComplete=False, status='blocked-collectible-r2r', lanes=results,
                      blocker='Pinned upstream ReadyToRunInfo::Initialize disables R2R for collectible modules. Native R2R controls use noncollectible contexts and do not establish native unloading.',
                      scope='Windows x64 only. No iOS delivery, signing or device claim.')
        save(output / 'result.json', result)
        print('PASS five functional/execution controls; BLOCKED combined collectible R2R acceptance. Evidence: ' + str(output))
        return 0 if args.allow_known_collectible_blocker else 2
    except Exception as error:
        save(output / 'result.json', dict(controlsPassed=False, milestoneComplete=False, error=str(error)))
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
