#!/usr/bin/env python3
"""Rebuild private full/minimal iOS fixtures with matching Release native/CoreLib/tools."""
import argparse
import importlib.util
import json
from pathlib import Path
import plistlib
import shutil
import tarfile


def helper(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'),
                                                Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'candidate', 'managed', 'minimal', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    common = helper('ios-r2r-fix-verify')
    mobile = helper('verify-ios-packages')
    managed = json.loads((args.managed / 'results.json').read_text())
    source = json.loads((args.candidate / 'logs/source.json').read_text())
    native_receipt = json.loads((args.candidate / 'logs/artifacts.json').read_text())
    native = Path(native_receipt['libcoreclr'])
    corelib = Path(managed['corelib'])
    compiler = Path(managed['crossgen2'])
    runtime = args.candidate / 'runtime'
    if (not managed['success'] or source['configuration'] != 'iossimulator.arm64.Release'
            or source['base'] != common.BASE
            or common.capture(['git', '-C', runtime, 'rev-parse', 'HEAD']) != source['commit']
            or common.capture(['git', '-C', runtime, 'status', '--porcelain', '--untracked-files=no'])
            or common.sha(native) != managed['nativeSha256']
            or common.sha(native) != native_receipt['libcoreclrSha256']
            or common.sha(corelib) != managed['corelibSha256']
            or common.sha(compiler) != managed['crossgen2Sha256']):
        raise RuntimeError('Matching Release input identity check failed')
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    logs = out / 'logs'
    logs.mkdir()
    inputs = out / 'input'
    inputs.mkdir()
    baseline = args.root / 'preview6-experiment/pinned-debug-harness'
    original_hashes = {p.name: common.sha(p) for p in (baseline / 'original').glob('*.dll')}
    for path in (baseline / 'original').glob('*.dll'):
        shutil.copy2(path, inputs / path.name)
    shutil.copy2(corelib, inputs / corelib.name)
    for path in (args.minimal / 'input').glob('Probe*.dll'):
        shutil.copy2(path, inputs / path.name)
    full = out / 'full/RuneCLRPinnedHarness.app'
    minimal = out / 'minimal/Probe.app'
    shutil.copytree(baseline / 'app/RuneCLRPinnedHarness.app', full)
    shutil.copytree(args.minimal / 'r2r/Probe.app', minimal)
    wrappers = {}
    for kind, app in [('full', full), ('minimal', minimal)]:
        executable = plistlib.loads((app / 'Info.plist').read_bytes())['CFBundleExecutable']
        wrappers[kind] = mobile.macho_sections(app / executable)
        shutil.copy2(native, app / 'libcoreclr.dylib')

    def composite(response, app, name):
        arguments = []
        for line in response.read_text().splitlines():
            if line.startswith('--out:'):
                arguments.append('--out:' + str(app / name))
            elif line.startswith('--'):
                arguments.append(line)
            else:
                reference = line.startswith('-r:')
                path = Path(line[3:] if reference else line)
                replacement = inputs / path.name
                if not replacement.is_file():
                    raise RuntimeError('Composite input unavailable: ' + str(path))
                arguments.append(('-r:' if reference else '') + str(replacement))
        rsp = logs / (name + '.rsp')
        rsp.write_text(chr(10).join(arguments) + chr(10))
        common.logged([compiler, '@' + str(rsp)], logs / (name + '-compile.log'), timeout=900)
        obj = logs / (name + '.o')
        shutil.copy2(app / name, obj)
        common.logged(['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator',
                       '-dynamiclib', obj, '-Wl,-install_name,@rpath/' + name, '-o', app / name], logs / (name + '-link.log'))

    composite(baseline / 'crossgen.rsp', full, 'framework.dylib')
    # The framework's generated R2R component DLLs must accompany its new image.
    shutil.copy2(full / 'framework.dylib', minimal / 'framework.dylib')
    for path in full.glob('*.dll'):
        shutil.copy2(path, minimal / path.name)
    composite(args.minimal / 'r2r/crossgen.rsp', minimal, 'probe.dylib')
    apps = {}
    for kind, app in [('full', full), ('minimal', minimal)]:
        for path in app.glob('*.dylib'):
            common.logged(['codesign', '--force', '--sign', '-', path], logs / (kind + '-' + path.name + '-sign.log'))
        common.logged(['codesign', '--force', '--sign', '-', app], logs / (kind + '-app-sign.log'))
        executable = plistlib.loads((app / 'Info.plist').read_bytes())['CFBundleExecutable']
        if wrappers[kind] != mobile.macho_sections(app / executable):
            raise RuntimeError('Native wrapper code/data changed')
        if mobile.macho_sections(native) != mobile.macho_sections(app / 'libcoreclr.dylib'):
            raise RuntimeError('Release native code/data changed')
        if mobile.il_layout(app / 'System.Private.CoreLib.dll')['managedNativeRva'] == 0:
            raise RuntimeError('CoreLib is not a generated framework R2R component')
        apps[kind] = {'app': str(app), 'tree': mobile.tree(app), 'wrapperSections': wrappers[kind]}
    if original_hashes != {p.name: common.sha(p) for p in (baseline / 'original').glob('*.dll')}:
        raise RuntimeError('Preserved baseline inputs changed')
    if common.sha(minimal / 'plugin/ProbePlugin.dll') != common.sha(args.minimal / 'r2r/Probe.app/plugin/ProbePlugin.dll'):
        raise RuntimeError('IL plugin fixture changed')
    common.write(out / 'identity.json', {'source': source, 'managedBuild': managed,
                 'inputHashes': {p.name: common.sha(p) for p in inputs.glob('*.dll')},
                 'baselineInputHashes': original_hashes, 'apps': apps,
                 'scope': 'matching Release native/CoreLib/compiler; preserved other managed libraries and IL fixtures; rebuilt trusted R2R composites'})
    common.write(out / 'results.json', {'buildSuccess': True, 'executionVerified': False,
                 'sourceTrackedClean': not common.capture(['git', '-C', runtime, 'status', '--porcelain', '--untracked-files=no'])})
    with tarfile.open(out / 'evidence.tar.gz', 'w:gz') as archive:
        for path in sorted(out.rglob('*')):
            if path.is_file() and path.suffix in ('.json', '.log', '.rsp'):
                archive.add(path, arcname=str(path.relative_to(out)))
        archive.add(Path(__file__), arcname='driver.py')
    print('Matching Release full/minimal layout BUILD PASS; execution pending', flush=True)
    print('Layout evidence SHA256=' + common.sha(out / 'evidence.tar.gz'), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
