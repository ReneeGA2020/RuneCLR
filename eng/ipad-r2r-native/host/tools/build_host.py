#!/usr/bin/env python3
"""Build the unsigned iPhoneOS ARM64 fixed host for the trusted-update R2R route."""
import hashlib, json, plistlib, shutil, struct, subprocess, sys, traceback
from datetime import datetime, timezone
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_bundle_id = "org.runeclr.ipadr2r"
EXECUTABLE = "TrustedUpdateHost"
ENTRY = "RunEntry.dll"


def utc():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def inventory(root):
    root = Path(root)
    return {str(p.relative_to(root)): {'sha256': sha(p), 'bytes': p.stat().st_size}
            for p in sorted(root.rglob('*')) if p.is_file()}


def run_stage(out, name, argv, cwd):
    env = {k: v for k, v in __import__('os').environ.items()
           if not k.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_', 'DYLD_', 'LD_'))}
    env.update(DOTNET_CLI_HOME=str(out / 'dotnet-home'), DOTNET_CLI_USE_MSBUILD_SERVER='0')
    process = subprocess.Popen([str(a) for a in argv], cwd=str(cwd), env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    (out / (name + '.stdout')).write_bytes(stdout)
    (out / (name + '.stderr')).write_bytes(stderr)
    receipt = {'argv': [str(a) for a in argv], 'cwd': str(cwd), 'pid': process.pid,
               'exitCode': process.returncode, 'utc': utc(),
               'stdoutSha256': hashlib.sha256(stdout).hexdigest(),
               'stderrSha256': hashlib.sha256(stderr).hexdigest()}
    (out / (name + '.process.json')).write_text(json.dumps(receipt, indent=2) + chr(10), encoding='ascii')
    return receipt


def macho(path):
    data = Path(path).read_bytes()
    if struct.unpack_from('<I', data, 0)[0] != 0xFEEDFACF:
        raise RuntimeError('not macho64: ' + str(path))
    cputype, subtype, filetype, ncmds = struct.unpack_from('<iiII', data, 4)
    off = 32
    platform = None
    minos = None
    signed = False
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, off)
        if cmd == 0x32:
            platform, minos, _sdk = struct.unpack_from('<III', data, off + 8)
        if cmd == 0x1D:
            signed = True
        off += size
    return {'cputype': cputype, 'filetype': filetype, 'platform': platform,
            'minos': minos, 'signed': signed, 'sha256': sha(path), 'bytes': len(data)}


def managed(path):
    data = Path(path).read_bytes()
    e = struct.unpack_from('<I', data, 0x3C)[0]
    coff = e + 4
    sections = struct.unpack_from('<H', data, coff + 2)[0]
    opt_size = struct.unpack_from('<H', data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from('<H', data, opt)[0]
    directory = opt + (112 if magic == 0x20B else 96)
    clr_rva = struct.unpack_from('<I', data, directory + 14 * 8)[0]
    table = opt + opt_size
    def rva_off(rva):
        for i in range(sections):
            base = table + i * 40
            vs, va = struct.unpack_from('<II', data, base + 8)
            rs, rp = struct.unpack_from('<II', data, base + 16)
            if va <= rva < va + max(vs, rs):
                return rp + (rva - va)
        raise RuntimeError('rva unmapped')
    cor = rva_off(clr_rva)
    return {'ilOnly': struct.unpack_from('<I', data, cor + 64)[0] == 0}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework-root", type=Path, required=True,
                        help="device framework layout root (contains input/ and layout/)")
    parser.add_argument("--runtime-root", type=Path, required=True,
                        help="private CoreCLR/toolchain checkout (contains .dotnet/ and artifacts/)")
    parser.add_argument("--crossgen2", type=Path, default=None,
                        help="override device crossgen2 executable")
    parser.add_argument("--dotnet", type=Path, default=None, help="override private dotnet host")
    parser.add_argument("--csc", type=Path, default=None, help="override Roslyn csc.dll")
    parser.add_argument("--output", type=Path, required=True, help="fresh output directory")
    parser.add_argument("--bundle-id", default=DEFAULT_bundle_id)
    parser.add_argument("--min-os", default="15.3")
    parser.add_argument("--label", default="host")
    parser.add_argument("--source-root", type=Path, default=None,
                        help="native host sources (default: package host/src)")
    parser.add_argument("--update-source-root", type=Path, default=None,
                        help="managed host fixture sources (default: package source/update-src)")
    parser.add_argument("--trusted-source-root", type=Path, default=None,
                        help="RuneCLR.TrustedUpdate sources (default: package source/trusted-update-src)")
    args = parser.parse_args()

    framework = args.framework_root.resolve()
    runtime = args.runtime_root.resolve()
    crossgen2 = (args.crossgen2 or (runtime / "artifacts/bin/coreclr/ios.arm64.Release/arm64/crossgen2/crossgen2")).resolve()
    dotnet = (args.dotnet or (runtime / ".dotnet/dotnet")).resolve()
    sources = (args.source_root or (PACKAGE_ROOT / "host/src")).resolve()
    update_src = (args.update_source_root or (PACKAGE_ROOT / "source/update-src")).resolve()
    trusted_src = (args.trusted_source_root or (PACKAGE_ROOT / "source/trusted-update-src")).resolve()
    bundle_id = args.bundle_id
    min_os = args.min_os
    min_hex = (int(min_os.split(".")[0]) << 16) | (int(min_os.split(".")[1]) << 8)
    sdk = dotnet
    sdk_root = runtime / ".dotnet"
    csc = (args.csc or (sdk_root / "sdk/11.0.100-rc.1.26420.103/Roslyn/bincore/csc.dll")).resolve()
    out = args.output.resolve()
    if out.exists():
        raise SystemExit('fresh output required')
    out.mkdir(parents=True)
    app = out / (EXECUTABLE + '.app')
    app.mkdir()

    inventory_path = framework / 'input-inventory.json'
    if not inventory_path.is_file():
        raise SystemExit('framework root is missing input-inventory.json: ' + str(inventory_path) +
                         ' (expected <framework-root>/input-inventory.json, input/ and layout/)')
    inventory_data = json.loads(inventory_path.read_text())
    inputs = sorted(inventory_data['compositeInputs'])
    layout = inventory_data['layout']
    native_libs = sorted(n for n in layout if n.endswith('.dylib') and n != 'framework.dylib')
    host_il = []
    pinned_il = []
    source_names = ['main.m', 'runtime.m', 'util.m', 'util.h', 'runtime.h',
                    'coreclrhost.h', 'host_runtime_contract.h', 'path_norm.c', 'path_norm.h',
                    'RunEntry.cs']
    pins_before = {
        'schema': 'runeclr.ipados.r2r.host-inputs.v1', 'capturedUtc': utc(),
        'frameworkDirectory': str(framework), 'frameworkInputs': inputs,
        'frameworkLayout': layout,
        'crossgen2': str(crossgen2), 'crossgen2Sha256': sha(crossgen2),
        'hostIl': {p.name: sha(p) for p in pinned_il},
        'sources': {n: sha(sources / n) for n in source_names},
        'managedSources': {**{str(pp.relative_to(update_src)): sha(pp) for pp in sorted(update_src.rglob('*.cs'))},
                            **{str(pp.relative_to(trusted_src)): sha(pp) for pp in sorted(trusted_src.rglob('*.cs'))}},
        'managedSources': {**{str(pp.relative_to(update_src)): sha(pp) for pp in sorted(update_src.rglob('*.cs'))},
                            **{str(pp.relative_to(trusted_src)): sha(pp) for pp in sorted(trusted_src.rglob('*.cs'))}},
    }
    (out / 'inputs-before.json').write_text(json.dumps(pins_before, indent=2) + chr(10), encoding='ascii')

    result = {'schema': 'runeclr.ipados.r2r.host-build.v1', 'success': False, 'bundleId': bundle_id,
              'executable': EXECUTABLE, 'entryAssembly': ENTRY, 'target': 'ios.arm64',
              'signing': False, 'install': False, 'startedUtc': utc()}
    try:
        for name in layout:
            if name == 'Info.plist':
                continue
            shutil.copyfile(framework / 'layout' / name, app / name)
        for dll in host_il:
            shutil.copyfile(dll, app / dll.name)
        sdk = dotnet
        refs_all = [framework / 'input' / name for name in inputs]
        contract = app / 'TrustedUpdate.Contract.dll'
        compile_contract = [sdk, csc, '-nologo', '-noconfig', '-nostdlib+', '-optimize+', '-deterministic+',
                            '-target:library', '-out:' + str(contract)] + ['-r:' + str(r) for r in refs_all] + [str(update_src / 'Contract.cs')]
        cc = run_stage(out, 'contract-compile', compile_contract, PACKAGE_ROOT)
        if cc['exitCode'] != 0:
            raise RuntimeError('contract compile failed: ' + (out / 'contract-compile.stdout').read_text()[:1200])
        shutil.copyfile(contract, out / 'TrustedUpdate.Contract.raw.dll')
        host_dll = app / 'TrustedUpdate.Host.dll'
        entry_dll = app / 'RunEntry.dll'
        trusted_dll = app / 'RuneCLR.TrustedUpdate.dll'
        tu_sources = sorted(trusted_src.glob('*.cs'))
        compile_trusted = [sdk, csc, '-nologo', '-noconfig', '-nostdlib+', '-optimize+', '-deterministic+',
                           '-target:library', '-out:' + str(trusted_dll)] + ['-r:' + str(r) for r in refs_all + [contract]] + [str(x) for x in tu_sources]
        c0 = run_stage(out, 'trusted-compile', compile_trusted, PACKAGE_ROOT)
        if c0['exitCode'] != 0:
            raise RuntimeError('trusted-update compile failed: ' + (out / 'trusted-compile.stdout').read_text()[:1500])
        trusted = trusted_dll
        compile_host = [sdk, csc, '-nologo', '-noconfig', '-nostdlib+', '-optimize+', '-deterministic+',
                        '-target:library', '-out:' + str(host_dll)] + ['-r:' + str(r) for r in refs_all + [contract, trusted]] + [str(update_src / 'Host.cs')]
        c1 = run_stage(out, 'host-compile', compile_host, PACKAGE_ROOT)
        if c1['exitCode'] != 0:
            raise RuntimeError('host compile failed: ' + (out / 'host-compile.stderr').read_text()[:1500])
        compile_entry = [sdk, csc, '-nologo', '-noconfig', '-nostdlib+', '-optimize+', '-deterministic+',
                         '-target:exe', '-out:' + str(entry_dll)] + ['-r:' + str(r) for r in refs_all + [contract, trusted, host_dll]] + [str(sources / 'RunEntry.cs')]
        c2 = run_stage(out, 'entry-compile', compile_entry, PACKAGE_ROOT)
        if c2['exitCode'] != 0:
            raise RuntimeError('entry compile failed: ' + (out / 'entry-compile.stderr').read_text()[:1500])
        host_il = sorted([contract, trusted, host_dll, entry_dll])

        refs = [framework / 'input' / name for name in inputs]
        rsp = out / 'host-crossgen.rsp'
        options = ['--targetos:ios', '--targetarch:arm64', '--obj-format:macho', '--composite',
                   '--inputbubble', '--parallelism:2', '--resilient', '--optimize',
                   '--out:' + str(out / 'TrustedUpdate.host.obj')]
        rsp.write_text(chr(10).join(options + [str(p) for p in host_il]
                                    + ['-r:' + str(p) for p in refs]) + chr(10), encoding='ascii')
        crossgen = run_stage(out, 'host-crossgen', [crossgen2, '@' + str(rsp)], PACKAGE_ROOT)
        if crossgen['exitCode'] != 0:
            raise RuntimeError('host crossgen failed: ' + (out / 'host-crossgen.stderr').read_text()[:1500])
        components = {}
        for dll in host_il:
            rewritten = out / dll.name
            if not rewritten.is_file():
                raise RuntimeError('crossgen did not emit component: ' + dll.name)
            shutil.copyfile(rewritten, app / dll.name)
            components[dll.name] = sha(app / dll.name)
        link = run_stage(out, 'host-link', ['xcrun', '--sdk', 'iphoneos', 'clang',
                                            '-target', 'arm64-apple-ios' + min_os, '-dynamiclib',
                                            str(out / 'TrustedUpdate.host.obj'),
                                            '-Wl,-install_name,@rpath/TrustedUpdate.host.dylib',
                                            '-o', str(app / 'TrustedUpdate.host.dylib')], PACKAGE_ROOT)
        if link['exitCode'] != 0:
            raise RuntimeError('host link failed: ' + (out / 'host-link.stderr').read_text()[:1500])
        wrapper = run_stage(out, 'wrapper', ['xcrun', '--sdk', 'iphoneos', 'clang',
                                             '-target', 'arm64-apple-ios' + min_os, '-fobjc-arc',
                                             '-DINVARIANT_GLOBALIZATION=1', '-I' + str(sources),
                                             str(sources / 'main.m'), str(sources / 'runtime.m'),
                                             str(sources / 'util.m'), str(sources / 'path_norm.c'),
                                             '-L' + str(app), '-lcoreclr', '-framework', 'UIKit',
                                             '-framework', 'Foundation',
                                             '-Wl,-rpath,@executable_path', '-o', str(app / EXECUTABLE)], PACKAGE_ROOT)
        if wrapper['exitCode'] != 0:
            raise RuntimeError('wrapper link failed: ' + (out / 'wrapper.stderr').read_text()[:2000])

        plist = {
            'CFBundleIdentifier': bundle_id, 'CFBundleExecutable': EXECUTABLE,
            'CFBundleName': 'RuneCLR iPad R2R Host', 'CFBundleDisplayName': 'RuneCLR R2R',
            'CFBundleInfoDictionaryVersion': '6.0', 'CFBundlePackageType': 'APPL',
            'CFBundleVersion': '1', 'CFBundleShortVersionString': '1.0',
            'LSRequiresIPhoneOS': True, 'CFBundleSupportedPlatforms': ['iPhoneOS'],
            'MinimumOSVersion': min_os, 'UIDeviceFamily': [1, 2],
            'UIFileSharingEnabled': True, 'LSSupportsOpeningDocumentsInPlace': True,
            'UILaunchScreen': {},
            'UISupportedInterfaceOrientations': ['UIInterfaceOrientationPortrait'],
            'UIApplicationSceneManifest': {'UIApplicationSupportsMultipleScenes': False},
        }
        (app / 'Info.plist').write_bytes(plistlib.dumps(plist))

        natives = [app / EXECUTABLE, app / 'framework.dylib', app / 'TrustedUpdate.host.dylib'] +                   [app / n for n in native_libs]
        audit = {}
        for path in natives:
            info = macho(path)
            if info['platform'] != 2 or info['cputype'] != 0x0100000C or info['signed']:
                raise RuntimeError('native audit failed: ' + path.name)
            if info['minos'] < 0x0D0000:
                raise RuntimeError('minimum below 13.0: ' + path.name)
            audit[path.name] = info
        for required in (EXECUTABLE, 'framework.dylib', 'TrustedUpdate.host.dylib'):
            if audit[required]['minos'] != min_hex:
                raise RuntimeError('minimum is not 15.3: ' + required)
        for dll in host_il:
            info = managed(app / dll.name)
            if info['ilOnly']:
                raise RuntimeError('host component has no active R2R header: ' + dll.name)
            components[dll.name] = sha(app / dll.name)
        forbidden = [p.name for p in app.rglob('*.dll')
                     if p.name.startswith(('TrustedUpdate.Update', 'TrustedUpdate.Private',
                                           'TrustedUpdate.Anchor', 'TrustedUpdate.IlOnlyHelper',
                                           'TrustedUpdate.Business'))]
        if forbidden:
            raise RuntimeError('author/update payload bundled: ' + ','.join(forbidden))

        files = inventory(app)
        result.update(success=True, app=str(app), fileCount=len(files),
                      totalBytes=sum(v['bytes'] for v in files.values()),
                      nativeAudit=audit, hostComponents=components, hostIl={p.name: sha(p) for p in pinned_il},
                      compiledRawIl={name: sha(app / name) for name in
                                     ('TrustedUpdate.Contract.dll','RuneCLR.TrustedUpdate.dll',
                                      'TrustedUpdate.Host.dll','RunEntry.dll')},
                      contract={"schema":"raw-vs-component","rawSha256": sha(out / 'TrustedUpdate.Contract.raw.dll'),"componentSha256": sha(app / 'TrustedUpdate.Contract.dll')},
                      frameworkDylib=sha(app / 'framework.dylib'),
                      hostComposite=sha(app / 'TrustedUpdate.host.dylib'),
                      executableSha=sha(app / EXECUTABLE), infoPlistSha=sha(app / 'Info.plist'))
        (out / 'APP-INVENTORY.json').write_text(json.dumps(files, indent=2) + chr(10), encoding='ascii')
    except Exception as error:
        result['error'] = str(error)
        (out / 'failure.txt').write_text(traceback.format_exc())
    pins_after = {
        'schema': 'runeclr.ipados.r2r.host-inputs.v1', 'capturedUtc': utc(),
        'frameworkInputs': inputs, 'frameworkLayout': inventory(framework / 'layout'),
        'crossgen2Sha256': sha(crossgen2), 'hostIl': {p.name: sha(p) for p in pinned_il},
        'sources': {n: sha(sources / n) for n in source_names},
        'managedSources': {**{str(pp.relative_to(update_src)): sha(pp) for pp in sorted(update_src.rglob('*.cs'))},
                            **{str(pp.relative_to(trusted_src)): sha(pp) for pp in sorted(trusted_src.rglob('*.cs'))}},
    }
    (out / 'inputs-after.json').write_text(json.dumps(pins_after, indent=2) + chr(10), encoding='ascii')
    layout_same = all(pins_after['frameworkLayout'][name]['sha256'] == digest
                      for name, digest in pins_before['frameworkLayout'].items())
    unchanged = layout_same and pins_after['sources'] == pins_before['sources'] and         pins_after['managedSources'] == pins_before['managedSources']
    result['inputsUnchanged'] = unchanged
    result['success'] = bool(result.get('success')) and unchanged
    result['endedUtc'] = utc()
    (out / 'results.json').write_text(json.dumps(result, indent=2) + chr(10), encoding='ascii')
    print(json.dumps({'success': result['success'], 'app': result.get('app'), 'error': result.get('error')}, indent=2))
    return 0 if result.get('success') else 1


if __name__ == '__main__':
    sys.exit(main())
