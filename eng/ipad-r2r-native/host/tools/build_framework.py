#!/usr/bin/env python3
"""Build the iPadOS arm64 composite R2R framework from a private runtime checkout.

The output directory is exactly what build_host.py consumes with --framework-root:
  input/               managed inputs that went into the composite image
  layout/              deps.json, native libraries, rewritten component DLLs, framework.dylib
  input-inventory.json compositeInputs (names) + layout (names) + identity/pin details

The recipe mirrors the verified 2026-11-10 dev build: crossgen2 with --composite --inputbubble
--targetos:ios --targetarch:arm64 --obj-format:macho, then one iphoneos clang link of the
composite object as framework.dylib. It does not build the runtime itself and vendors nothing.

Usage:
  python3 -B eng/ipad-r2r-native/host/tools/build_framework.py \
      --runtime-root <private runtime checkout> --output <fresh dir> [--min-os 15.3]
"""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import time
import zipfile
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def run(argv, log_path, cwd=None):
    process = subprocess.run([str(a) for a in argv], cwd=str(cwd) if cwd else None,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    Path(log_path).write_bytes(process.stdout)
    return {'argv': [str(a) for a in argv], 'exitCode': process.returncode,
            'log': str(log_path), 'logSha256': sha(log_path)}


def macho(path):
    data = Path(path).read_bytes()
    if struct.unpack_from('<I', data, 0)[0] != 0xFEEDFACF:
        return {'error': 'not macho64'}
    cputype, subtype, filetype, ncmds = struct.unpack_from('<iiII', data, 4)
    off = 32
    platform = None
    minos = None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, off)
        if cmd == 0x32:
            platform, minos, _sdk = struct.unpack_from('<III', data, off + 8)
        off += size
    return {'cputype': cputype, 'filetype': filetype, 'platform': platform,
            'minos': minos, 'sha256': sha(path), 'bytes': len(data)}


def files(names, root):
    return {name: {'sha256': sha(Path(root) / name), 'bytes': (Path(root) / name).stat().st_size}
            for name in sorted(names)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pack', type=Path, default=None, help='runtime pack nupkg (default: discover)')
    parser.add_argument('--crossgen2', type=Path, default=None)
    parser.add_argument('--dotnet', type=Path, default=None)
    parser.add_argument('--runtime-identifier', default='ios-arm64')
    parser.add_argument('--architecture', default='arm64')
    parser.add_argument('--min-os', default='15.3')
    parser.add_argument('--parallelism', type=int, default=4)
    args = parser.parse_args()

    runtime = args.runtime_root.resolve()
    out = args.output.resolve()
    if out.exists():
        raise SystemExit('fresh output required: ' + str(out))
    if not (runtime / 'artifacts').is_dir():
        raise SystemExit('runtime root has no artifacts/: ' + str(runtime))

    crossgen2 = (args.crossgen2 or (runtime / 'artifacts/bin/coreclr/ios.arm64.Release/arm64/crossgen2/crossgen2')).resolve()
    dotnet = (args.dotnet or (runtime / '.dotnet/dotnet')).resolve()
    if not crossgen2.is_file():
        raise SystemExit('crossgen2 not found: ' + str(crossgen2))

    pack = args.pack
    if pack is None:
        shipping = runtime / 'artifacts/packages/Release/Shipping'
        candidates = sorted(p for p in shipping.glob('*.nupkg')
                            if args.runtime_identifier in p.name and 'symbols' not in p.name)
        if len(candidates) != 1:
            raise SystemExit('expected exactly one runtime pack in %s, found %d' % (shipping, len(candidates)))
        pack = candidates[0]
    pack = pack.resolve()
    if not pack.is_file():
        raise SystemExit('runtime pack not found: ' + str(pack))

    out.mkdir(parents=True)
    (out / 'input').mkdir()
    (out / 'layout').mkdir()
    (out / 'work').mkdir()

    with zipfile.ZipFile(pack) as archive:
        archive.extractall(out / 'pack')

    lib_root = out / 'pack' / 'runtimes' / args.runtime_identifier / 'lib'
    lib_dirs = sorted(p for p in lib_root.glob('*') if (p / 'System.Private.CoreLib.dll').is_file())
    if len(lib_dirs) != 1:
        raise SystemExit('expected one managed lib dir under ' + str(lib_root))
    lib_dir = lib_dirs[0]
    native_dir = out / 'pack' / 'runtimes' / args.runtime_identifier / 'native'
    if not native_dir.is_dir():
        raise SystemExit('missing native dir: ' + str(native_dir))

    inputs = []
    for item in sorted(lib_dir.glob('*.dll')):
        shutil.copyfile(item, out / 'input' / item.name)
        inputs.append(item.name)
    deps_name = ''
    for item in sorted(lib_dir.glob('*.deps.json')):
        shutil.copyfile(item, out / 'layout' / item.name)
        deps_name = item.name
        break
    native_names = []
    for pattern in ('*.dylib', '*.a'):
        for item in sorted(native_dir.glob(pattern)):
            shutil.copyfile(item, out / 'layout' / item.name)
            native_names.append(item.name)

    rsp = out / 'crossgen.rsp'
    rsp_lines = ['--targetos:ios', '--targetarch:' + args.architecture, '--obj-format:macho',
                 '--composite', '--inputbubble', '--parallelism:%d' % args.parallelism,
                 '--resilient', '--optimize', '--out:%s' % (out / 'work' / 'framework.o')]
    rsp_lines += [str(out / 'input' / name) for name in inputs]
    rsp.write_text('\n'.join(rsp_lines) + '\n', encoding='utf-8')

    crossgen = run([crossgen2, '@' + str(rsp)], out / 'crossgen.log')
    if crossgen['exitCode'] != 0:
        raise SystemExit('crossgen2 failed (%d): %s' % (crossgen['exitCode'], out / 'crossgen.log'))

    min_hex = (int(args.min_os.split('.')[0]) << 16) | (int(args.min_os.split('.')[1]) << 8)
    link = run(['xcrun', '--sdk', 'iphoneos', 'clang', '-target',
                '%s-apple-ios%s' % (args.architecture, args.min_os), '-dynamiclib',
                str(out / 'work' / 'framework.o'), '-Wl,-install_name,@rpath/framework.dylib',
                '-o', str(out / 'layout' / 'framework.dylib')], out / 'link.log')
    if link['exitCode'] != 0:
        raise SystemExit('framework link failed (%d): %s' % (link['exitCode'], out / 'link.log'))

    rewritten = []
    for item in sorted((out / 'work').glob('*.dll')):
        shutil.copyfile(item, out / 'layout' / item.name)
        rewritten.append(item.name)

    layout_names = sorted(p.name for p in (out / 'layout').iterdir() if p.is_file())
    corelib_input = out / 'input' / 'System.Private.CoreLib.dll'
    corelib_shipped = out / 'layout' / 'System.Private.CoreLib.dll'
    dotnet_version = ''
    if dotnet.is_file():
        probe = subprocess.run([str(dotnet), '--version'], capture_output=True, text=True)
        dotnet_version = probe.stdout.strip() if probe.returncode == 0 else ''
    git = {}
    if (runtime / '.git').exists():
        for key, argv in (('commit', ['git', '-C', str(runtime), 'rev-parse', 'HEAD']),
                          ('status', ['git', '-C', str(runtime), 'status', '--porcelain']),
                          ('diff', ['git', '-C', str(runtime), 'diff'])):
            proc = subprocess.run(argv, capture_output=True, text=True)
            git[key] = proc.stdout
    patch_text = git.get('diff', '')

    input_details = files(inputs, out / 'input')
    layout_details = files(layout_names, out / 'layout')
    dylib_audit_names = ['framework.dylib'] + [n for n in native_names
                                               if n.endswith('.dylib') and n != 'framework.dylib'][:3]
    inventory = {
        'compositeInputs': {name: info['sha256'] for name, info in input_details.items()},
        'layout': {name: info['sha256'] for name, info in layout_details.items()},
        'depsFile': deps_name,
        'sourceCommit': git.get('commit', '').strip(),
        'target': {'runtimeIdentifier': args.runtime_identifier,
                   'architecture': args.architecture, 'minOs': args.min_os,
                   'minOsHex': hex(min_hex), 'platform': 2},
        'pack': {'path': str(pack), 'sha256': sha(pack), 'managedLibDir': lib_dir.name,
                 'nativeFiles': native_names},
        'crossgen2': {'path': str(crossgen2), 'sha256': sha(crossgen2)},
        'dotnet': {'path': str(dotnet), 'version': dotnet_version,
                   'sha256': sha(dotnet) if dotnet.is_file() else ''},
        'coreLib': {'inputSha256': sha(corelib_input) if corelib_input.is_file() else '',
                    'shippedSha256': sha(corelib_shipped) if corelib_shipped.is_file() else ''},
        'runtimePatch': {'statusPorcelain': git.get('status', ''),
                         'diffSha256': hashlib.sha256(patch_text.encode()).hexdigest()},
        'inputs': input_details,
        'layoutFiles': layout_details,
        'rewrittenComponents': {name: sha(out / 'layout' / name) for name in rewritten},
        'nativeAudit': {name: macho(out / 'layout' / name) for name in dylib_audit_names},
        'stages': {'crossgen': crossgen, 'link': link},
        'capturedUtc': utc(),
    }
    (out / 'input-inventory.json').write_text(json.dumps(inventory, indent=1) + '\n', encoding='ascii')

    print(json.dumps({'output': str(out), 'inputs': len(inputs), 'layout': len(layout_names),
                      'frameworkDylib': inventory['layoutFiles']['framework.dylib']['sha256'],
                      'coreLibInput': inventory['coreLib']['inputSha256'],
                      'coreLibShipped': inventory['coreLib']['shippedSha256'],
                      'pack': inventory['pack']['sha256'],
                      'dotnet': dotnet_version,
                      'crossgen2': inventory['crossgen2']['sha256'],
                      'nativeAudit': inventory['nativeAudit']['framework.dylib']}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
