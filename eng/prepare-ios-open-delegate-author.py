#!/usr/bin/env python3
"""Compile an explicit open-instance-delegate variant of the fixed author IL."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import struct
import subprocess
import uuid


MANIFEST = 'ccf1ece09ef7d8f33a4da685234222526426f4712af1b1a5b2308de0dc97d685'
DEVICE_NATIVE = '34c27daf3d6ef73a1558c21733d9f101bea4dcc839b9380d182d68cea2e2b93b'
SOURCES = {'Private': 'eng/host-budget-probe/Private/Helper.cs',
           'Payload': 'eng/host-budget-probe/Payload/Maps.cs'}
AUTHOR = ('HostBudgetProbe.Private.dll', 'HostBudgetProbe.Payload.dll')
BASE_COMPILER = '8bdf9a06b9b0236018300e0fb0c2bac7148a35de10403e84835d27595d62cf58'
VARIANT = 'runeclr.fresh-author.open-instance-delegate.v1'
FINITE = 'public static void Finite(RuneCLR.IMapContext context){context.Log("private-finally");Action callback=()=>context.Log("private-delegate");callback();}'
OPEN_FINITE = '''public static void Finite(RuneCLR.IMapContext context)
    {
        context.Log("private-finally");
        Action callback=()=>context.Log("private-delegate");
        typeof(Helper).GetMethod(nameof(OpenInvoke))!
            .MakeGenericMethod(callback.Target!.GetType())
            .Invoke(null,new object[]{callback.Target!,callback.Method});
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void OpenInvoke<T>(T target,System.Reflection.MethodInfo method) where T:class
    {
        Action<T> open=method.CreateDelegate<Action<T>>();
        if(open.Target is not null)throw new InvalidOperationException("Expected open instance delegate.");
        open(target);
    }'''


def variant_source(role, data):
    if role != 'Private':
        return data
    text = data.decode('ascii')
    need(text.count(FINITE) == 1, 'Frozen finite cleanup source anchor differs')
    # Keep the first capturing lambda in Finite, including its generated name.
    # Reflection supplies its inaccessible closure type as the open receiver type.
    return text.replace(FINITE, OPEN_FINITE).encode('ascii')


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    with path.open('x', encoding='ascii') as stream:
        json.dump(value, stream, indent=2)
        stream.write(chr(10))


def il_only(path):
    data = path.read_bytes()
    need(data[:2] == b'MZ', 'Author is not PE: ' + str(path))
    pe = struct.unpack_from('<I', data, 60)[0]
    need(data[pe:pe + 4] == b'PE\0\0', 'PE signature missing')
    opt = pe + 24
    magic = struct.unpack_from('<H', data, opt)[0]
    need(magic in (0x10b, 0x20b), 'Unsupported PE header')
    directories = opt + (96 if magic == 0x10b else 112)
    cli = struct.unpack_from('<I', data, directories + 14 * 8)[0]
    section_count = struct.unpack_from('<H', data, pe + 6)[0]
    section = opt + struct.unpack_from('<H', data, pe + 20)[0]
    for index in range(section_count):
        size, rva, raw_size, raw = struct.unpack_from('<IIII', data, section + index * 40 + 8)
        if rva <= cli < rva + max(size, raw_size):
            header = raw + cli - rva
            flags = struct.unpack_from('<I', data, header + 16)[0]
            native_rva, native_size = struct.unpack_from('<II', data, header + 64)
            need(flags & 1 and not native_rva and not native_size, 'Author must be IL-only without R2R')
            return dict(ilOnly=True, managedNativeRva=0)
    raise RuntimeError('CLI header missing')


def unsigned_macho(path, filetype):
    data = path.read_bytes()
    need(len(data) >= 32 and struct.unpack_from('<II', data) == (0xfeedfacf, 0x100000c),
         'Unsigned device input must be thin ARM64 Mach-O')
    need(struct.unpack_from('<I', data, 12)[0] == filetype,
         'Bundle main must be MH_EXECUTE; native libraries must be MH_DYLIB')
    count, size = struct.unpack_from('<II', data, 16)
    cursor, limit, versions = 32, 32 + size, []
    need(limit <= len(data), 'Truncated Mach-O command table')
    for _ in range(count):
        need(cursor + 8 <= limit, 'Truncated Mach-O command header')
        command, length = struct.unpack_from('<II', data, cursor)
        need(length >= 8 and cursor + length <= limit, 'Invalid Mach-O command length')
        need(command != 0x1d, 'Unsigned bundle contains LC_CODE_SIGNATURE')
        if command == 0x32:
            need(length >= 24, 'Truncated LC_BUILD_VERSION')
            platform, minimum, _, tools = struct.unpack_from('<IIII', data, cursor + 8)
            need(length == 24 + tools * 8, 'Invalid Mach-O tool table')
            versions.append((platform, minimum))
        cursor += length
    need(cursor == limit and len(versions) == 1 and versions[0][0] == 2
         and versions[0][1] <= 0x000f0300, 'Device native minimum must be compatible with iOS15.3')


def bundle(app):
    root = app.resolve()
    info = plistlib.loads((root / 'Info.plist').read_bytes())
    executable = info['CFBundleExecutable']
    need(type(executable) is str and Path(executable).name == executable and executable not in ('.', '..'),
         'Bundle executable is not a single filename')
    need(info.get('CFBundleSupportedPlatforms') == ['iPhoneOS'], 'Actual device platform declaration missing')
    need(not any(path.name in AUTHOR for path in root.rglob('*')), 'Author already present in trusted bundle')
    helper = Path(__file__).with_name('ios-device-batch-build.py')
    need(sha(helper) == '24fe654ead15f3fe170ab02cdae191270d72080d409337a805701a31c5c3ea8b',
         'Frozen device platform helper changed')
    spec = importlib.util.spec_from_file_location('device_native_platform', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.macho_device(root / executable)
    module.macho_device(root / 'libcoreclr.dylib')
    unsigned_macho(root / executable, 2)
    for path in root.rglob('*.dylib'):
        unsigned_macho(path, 6)
    need(info.get('MinimumOSVersion') == '15.3', 'Device bundle minimum must be15.3')
    need(sha(root / 'libcoreclr.dylib') == DEVICE_NATIVE, 'Unsigned matching device native differs')
    return {path.relative_to(root).as_posix(): sha(path) for path in sorted(root.rglob('*')) if path.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('sanity', 'prepare'))
    for name in ('inputs', 'sdk', 'refs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--app', type=Path)
    args = parser.parse_args()
    need((args.app is not None) == (args.phase == 'prepare'), 'Only prepare binds an actual device application')
    args.output.mkdir(parents=True, exist_ok=False)
    result = dict(passed=False, physicalDeviceExecuted=False, authorExecuted=False,
                  phase=args.phase, deviceHostBound=False, postDeviceHostBuildCompiled=False)
    try:
        need(sha(Path(__file__).with_name('prepare-ios-device-author.py')) == BASE_COMPILER,
             'Frozen baseline author compiler changed')
        manifest_path = args.inputs / 'input-manifest.json'
        need(sha(manifest_path) == MANIFEST, 'Frozen host-budget input manifest changed')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        for name, digest in manifest['files'].items():
            path = (args.inputs / name).resolve()
            need(path.is_relative_to(args.inputs.resolve()) and sha(path) == digest, 'Frozen input changed: ' + name)
        frozen = {}
        for role, name in SOURCES.items():
            path = args.inputs / 'source' / name
            need(sha(path) == manifest['sourceHashes'][name], 'Frozen fixture source changed: ' + role)
            frozen[role] = path
        dotnet = args.sdk / ('dotnet.exe' if os.name == 'nt' else 'dotnet')
        candidates = list((args.sdk / 'sdk').glob('*/Roslyn/bincore/csc.dll'))
        need(len(candidates) == 1 and dotnet.is_file(), 'One explicit private Roslyn SDK required')
        compiler = candidates[0]
        references = sorted(args.refs.glob('*.dll'))
        need(len(references) >= 100 and (args.refs / 'System.Runtime.dll').is_file(), 'Explicit framework references missing')
        inventory = bundle(args.app) if args.app else None
        nonce, bound_utc = uuid.uuid4().hex, utc()
        write(args.output / 'request.json', dict(phase=args.phase, nonce=nonce, boundUtc=bound_utc,
              app=str(args.app.resolve()) if args.app else None, hostBundleHashes=inventory,
              inputManifestSha256=MANIFEST, sourceHashes={role: sha(path) for role, path in frozen.items()},
              sdkHostSha256=sha(dotnet), compilerSha256=sha(compiler),
              referenceHashes={path.name: sha(path) for path in references}, targetsRerun=False,
              fixtureVariant=VARIANT, baselineCompilerSha256=BASE_COMPILER,
              compiledSourceHashes={role: hashlib.sha256(variant_source(role, path.read_bytes())).hexdigest()
                                    for role, path in frozen.items()}))
        source = args.output / 'source'
        source.mkdir()
        globals_path = source / 'GlobalUsings.cs'
        globals_path.write_text('global using System;' + chr(10), encoding='ascii')
        attribute = source / 'AfterHostBuild.cs'
        attribute.write_text('[assembly: System.Reflection.AssemblyVersion("1.0.0.0")]' + chr(10) +
                             '[assembly: System.Reflection.AssemblyMetadata("RuneCLR.DeviceAuthor.AfterHost", "' + nonce + '")]' + chr(10),
                             encoding='ascii')
        contract = args.inputs / 'trusted/RuneCLR.Abstractions.dll'
        plugin = args.output / 'plugin'
        plugin.mkdir()
        processes = []
        for role, filename in zip(('Private', 'Payload'), AUTHOR):
            copied = source / (role + '.cs')
            copied.write_bytes(variant_source(role, frozen[role].read_bytes()))
            output = plugin / filename
            selected = references + [contract] + ([plugin / AUTHOR[0]] if role == 'Payload' else [])
            response = args.output / (role + '.rsp')
            lines = ['-target:library', '-nostdlib+', '-deterministic+', '-optimize+', '-debug-',
                     '-nullable:enable', '-langversion:preview', '-warnaserror+', '-out:"' + str(output.resolve()) + '"']
            lines += ['-reference:"' + str(path.resolve()) + '"' for path in selected]
            lines += ['"' + str(path.resolve()) + '"' for path in (copied, globals_path, attribute)]
            response.write_text(chr(10).join(lines) + chr(10), encoding='ascii')
            argv = [str(dotnet.resolve()), str(compiler.resolve()), '-noconfig', '@' + str(response.resolve())]
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_'))}
            started = utc()
            process = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=120)
            (args.output / (role + '.stdout')).write_bytes(process.stdout)
            (args.output / (role + '.stderr')).write_bytes(process.stderr)
            receipt = dict(argv=argv, exitCode=process.returncode, startedUtc=started, endedUtc=utc(),
                           responseSha256=sha(response), stdoutSha256=sha(args.output / (role + '.stdout')),
                           stderrSha256=sha(args.output / (role + '.stderr')))
            write(args.output / (role + '.process.json'), receipt)
            need(process.returncode == 0, 'Controlled fixed-source compiler failed: ' + role)
            il_only(output)
            need(sha(output) != manifest['files']['plugin/' + filename], 'Compiled author reused old fixture bytes')
            processes.append(receipt)
        need(not args.app or bundle(args.app) == inventory, 'Device host bundle changed during author compilation')
        need(all(sha(frozen[role]) == manifest['sourceHashes'][name] for role, name in SOURCES.items()),
             'Frozen source changed during compilation')
        result.update(passed=True, nonce=nonce, authorCompilationCount=len(processes),
                      fixtureVariant=VARIANT, baselineCompilerSha256=BASE_COMPILER,
                      compiledSourceHashes={role: sha(source / (role + '.cs')) for role in SOURCES},
                      authorHashes={path.name: sha(path) for path in plugin.iterdir()},
                      deviceHostBound=inventory is not None, postDeviceHostBuildCompiled=inventory is not None,
                      hostBundleUnchanged=inventory is not None, startedAfterHostBindingUtc=bound_utc,
                      authorIlOnly=True, preparationOnly=args.phase == 'sanity',
                      scope='Fixed trusted open-instance-delegate fixture compilation; prepare binds unsigned device host bytes. Neither phase installs or executes author IL.')
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        result['driverSha256'] = sha(Path(__file__))
        write(args.output / 'results.json', result)
    print('Fresh author IL compilation PASS: 2 assemblies; device host bound=' + str(result['deviceHostBound']))


if __name__ == '__main__':
    main()
