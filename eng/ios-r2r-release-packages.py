#!/usr/bin/env python3
"""Build and functionally accept the controlled player with matching Release inputs.

Method-level interpretation requires separate native entry capture; this driver
does not use Debug dumps or claim that disabled JIT proves interpretation.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import plistlib
import re
import shutil
import tarfile
import uuid


def helper(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'),
                                                Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(args, common, mobile):
    prior = json.loads((args.controlled / 'state.json').read_text())
    managed = json.loads((args.managed / 'results.json').read_text())
    source = json.loads((args.candidate / 'logs/source.json').read_text())
    artifact = json.loads((args.candidate / 'logs/artifacts.json').read_text())
    runtime = args.candidate / 'runtime'
    native, corelib, compiler = (Path(artifact['libcoreclr']),
                                Path(managed['corelib']), Path(managed['crossgen2']))
    if (not managed['success'] or source['base'] != common.BASE
            or source['configuration'] != 'iossimulator.arm64.Release'
            or common.capture(['git', '-C', runtime, 'rev-parse', 'HEAD']) != source['commit']
            or common.capture(['git', '-C', runtime, 'status', '--porcelain', '--untracked-files=no'])
            or common.sha(native) != artifact['libcoreclrSha256']
            or common.sha(native) != managed['nativeSha256']
            or common.sha(corelib) != managed['corelibSha256']
            or common.sha(compiler) != managed['crossgen2Sha256']):
        raise RuntimeError('Matching Release provenance failed')
    original = Path(prior['app'])
    if mobile.tree(original) != prior['bundleHashes']:
        raise RuntimeError('Preserved controlled player changed')
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    logs = out / 'logs'
    logs.mkdir()
    inputs = out / 'input'
    shutil.copytree(args.controlled / 'input', inputs)
    shutil.copy2(corelib, inputs / corelib.name)
    app = out / 'app/Packages.app'
    shutil.copytree(original, app)
    executable = plistlib.loads((app / 'Info.plist').read_bytes())['CFBundleExecutable']
    wrapper = mobile.macho_sections(app / executable)
    shutil.copy2(native, app / 'libcoreclr.dylib')
    arguments = []
    for line in (args.controlled / 'crossgen.rsp').read_text().splitlines():
        if line.startswith('--out:'):
            arguments.append('--out:' + str(app / 'framework.dylib'))
        elif line.startswith('--'):
            arguments.append(line)
        else:
            reference = line.startswith('-r:')
            path = Path(line[3:] if reference else line)
            replacement = inputs / path.name
            if not replacement.is_file():
                raise RuntimeError('Missing composite input: ' + str(path))
            arguments.append(('-r:' if reference else '') + str(replacement))
    rsp = out / 'crossgen.rsp'
    rsp.write_text(chr(10).join(mobile.rsp_argument(a) for a in arguments) + chr(10))
    common.logged([compiler, '@' + str(rsp)], logs / 'crossgen.log', timeout=900)
    obj = out / 'framework.o'
    shutil.copy2(app / 'framework.dylib', obj)
    common.logged(['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target',
                   'arm64-apple-ios15.3-simulator', '-dynamiclib', obj,
                   '-Wl,-install_name,@rpath/framework.dylib', '-o', app / 'framework.dylib'],
                  logs / 'composite-link.log')
    for name in ('RuneCLR.Runtime.dll', 'RuneCLR.Packages.dll'):
        if (common.sha(inputs / name) != common.sha(app / name)
                or mobile.il_layout(app / name)['managedNativeRva']):
            raise RuntimeError('Selective host IL identity changed: ' + name)
    plist = plistlib.loads((app / 'Info.plist').read_bytes())
    plist['CFBundleIdentifier'] = 'org.runeclr.releasepackages.' + uuid.uuid4().hex[:12]
    (app / 'Info.plist').write_bytes(plistlib.dumps(plist))
    for path in app.glob('*.dylib'):
        common.logged(['codesign', '--force', '--sign', '-', path], logs / (path.name + '-sign.log'))
    common.logged(['codesign', '--force', '--sign', '-', app], logs / 'app-sign.log')
    if wrapper != mobile.macho_sections(app / executable):
        raise RuntimeError('Native wrapper code/data changed')
    if mobile.macho_sections(native) != mobile.macho_sections(app / 'libcoreclr.dylib'):
        raise RuntimeError('Release native code/data changed')
    if mobile.tree(original) != prior['bundleHashes']:
        raise RuntimeError('Preserved baseline bundle changed')
    if any(p.name.startswith(('RuneCLR.Compiler', 'RuneCLR.PackageFixtures', 'Microsoft.CodeAnalysis'))
           for p in app.rglob('*')):
        raise RuntimeError('Operator tools entered player')
    state = {'app': str(app), 'bundleId': plist['CFBundleIdentifier'],
             'bundleHashes': mobile.tree(app), 'source': source, 'managedBuild': managed,
             'nativeSections': mobile.macho_sections(native), 'wrapperSections': wrapper,
             'playerInputHashes': {name: common.sha(inputs / name) for name in mobile.PLAYER},
             'inputHashes': {p.name: common.sha(p) for p in inputs.glob('*.dll')},
             'layouts': {p.name: mobile.il_layout(p) for p in app.glob('*.dll')},
             'builtUtc': mobile.utc(), 'scope': 'matching Release native/CoreLib/compiler; preserved other same-base IL; Runtime/Packages IL; trusted composite rebuilt'}
    common.write(out / 'state.json', state)
    shutil.copy2(Path(__file__), out / 'driver.py')
    print('Matching Release controlled player BUILD PASS', flush=True)


def install(args, common, mobile):
    out, state = mobile.load(args)
    if 'simulator' in state or mobile.tree(Path(state['app'])) != state['bundleHashes']:
        raise RuntimeError('Installation requires an unchanged, previously uninstalled layout')
    sim = common.capture(['xcrun', 'simctl', 'create', 'RuneCLR-Release-Packages',
                          'com.apple.CoreSimulator.SimDeviceType.iPhone-17',
                          'com.apple.CoreSimulator.SimRuntime.iOS-27-0'])
    state['simulator'] = sim
    common.write(out / 'state.json', state)
    common.logged(['xcrun', 'simctl', 'boot', sim], out / 'logs/boot-command.log')
    common.logged(['xcrun', 'simctl', 'bootstatus', sim, '-b'], out / 'logs/boot.log')
    common.logged(['xcrun', 'simctl', 'install', sim, state['app']], out / 'logs/install.log')
    state['installedUtc'] = mobile.utc()
    for kind, key in [('app', 'installedApp'), ('data', 'dataContainer')]:
        state[key] = common.capture(['xcrun', 'simctl', 'get_app_container', sim, state['bundleId'], kind])
    common.write(out / 'state.json', state)
    if mobile.tree(Path(state['installedApp'])) != state['bundleHashes']:
        raise RuntimeError('Installed bundle changed')
    log = out / 'logs/before-packages.log'
    common.logged(['xcrun', 'simctl', 'launch', '--console', sim, state['bundleId']], log, timeout=120)
    text = log.read_text(errors='replace')
    if 'PACKAGE_WAITING_FOR_POSTINSTALL_IL' not in text or 'RUNECLR_EXIT=0' not in text:
        raise RuntimeError('Empty player did not complete successfully')
    print(json.dumps({'installedUtc': state['installedUtc'], 'bundleId': state['bundleId']}), flush=True)


def execute(args, common, mobile):
    out, state = mobile.load(args)
    receipt_path = args.packages / 'fixtures.json'
    receipt = json.loads(receipt_path.read_text())
    produced, generated, installed = (mobile.parse_utc(args.produced_utc),
                                     mobile.parse_utc(receipt['generatedUtc']),
                                     mobile.parse_utc(state['installedUtc']))
    if produced <= installed or generated < produced:
        raise RuntimeError('Fresh fixture production must follow installation')
    if (receipt['inputProfile'] != 'managed-il-gameplay-v1'
            or receipt['contractImageSha256'].lower() != state['playerInputHashes']['RuneCLR.Abstractions.dll']
            or set(item['directory'] for item in receipt['packages']) != set(mobile.PACKAGES)):
        raise RuntimeError('Fixture profile/contract/inventory mismatch')
    for item in receipt['packages']:
        if common.sha(args.packages / item['directory'] / 'package.json') != item['manifestSha256'].lower():
            raise RuntimeError('Transferred manifest differs from producer receipt')
    target = Path(state['dataContainer']) / 'Documents/controlled'
    if target.exists():
        raise RuntimeError('Preserve installed fixtures; use a new experiment')
    payload = {name + '/' + p: digest for name in mobile.PACKAGES
               for p, digest in mobile.tree(args.packages / name).items()}
    layouts = {p: mobile.il_layout(args.packages / p) for p in payload if p.endswith('.dll')}
    if any(not item['ilOnly'] or item['managedNativeRva'] for item in layouts.values()):
        raise RuntimeError('Payload has a native method body')
    target.mkdir(parents=True)
    for name in mobile.PACKAGES:
        shutil.copytree(args.packages / name, target / name)
    if mobile.tree(target) != payload:
        raise RuntimeError('Installed fixture bytes changed')
    shutil.copy2(receipt_path, out / 'fixtures.json')
    log = out / 'logs/packages-run.log'
    status = common.logged(['xcrun', 'simctl', 'launch', '--console', state['simulator'], state['bundleId']],
                           log, check=False, timeout=240)
    text = log.read_text(errors='replace')
    counts = re.search(r'([0-9]+)/([0-9]+) package execution tests passed', text)
    unchanged = mobile.tree(Path(state['installedApp'])) == state['bundleHashes']
    passed = bool(status == 0 and counts and counts.group(1) == counts.group(2) == '15'
                  and 'RUNECLR_EXIT=0' in text and 'DynamicCodeCompiled=False' in text
                  and 'PACKAGE_RUNTIME=.NET 12.0.0-dev' in text
                  and 'Got a SIGSEGV' not in text and 'Assert failure' not in text and unchanged)
    result = {'functionalPassed': passed, 'passed': int(counts.group(1)) if counts else 0,
              'total': int(counts.group(2)) if counts else 0, 'launcherExit': status,
              'bundleUnchanged': unchanged, 'installedUtc': state['installedUtc'],
              'productionStartedUtc': args.produced_utc, 'completedUtc': mobile.utc(),
              'payloadHashes': payload, 'payloadLayouts': layouts, 'receiptSha256': common.sha(receipt_path),
              'logSha256': common.sha(log), 'methodInterpreterProof': 'pending separate native capture',
              'scope': 'Release simulator functional acceptance; no physical-device or method-entry claim'}
    common.write(out / 'results.json', result)
    print(json.dumps(result, indent=2), flush=True)
    if not passed:
        raise RuntimeError('Release controlled-package functional acceptance failed; preserve logs')


def reassess(args, common, mobile):
    # Read-only reassessment of a completed run after correcting the count regex.
    # Preserve results.json and the original driver; never replay the app here.
    out, state = mobile.load(args)
    prior = json.loads((out / 'results.json').read_text())
    log = out / 'logs/packages-run.log'
    if (common.sha(log) != prior['logSha256']
            or common.sha(out / 'fixtures.json') != prior['receiptSha256']
            or mobile.tree(Path(state['installedApp'])) != state['bundleHashes']
            or mobile.tree(Path(state['dataContainer']) / 'Documents/controlled') != prior['payloadHashes']):
        raise RuntimeError('Completed-run evidence changed')
    text = log.read_text(errors='replace')
    counts = re.search(r'([0-9]+)/([0-9]+) package execution tests passed', text)
    passed = bool(prior['launcherExit'] == 0 and counts
                  and counts.group(1) == counts.group(2) == '15'
                  and text.count('] PASS ') == 15
                  and 'CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0' in text
                  and 'DynamicCodeCompiled=False' in text
                  and 'PACKAGE_RUNTIME=.NET 12.0.0-dev' in text
                  and 'Got a SIGSEGV' not in text and 'Assert failure' not in text
                  and prior['bundleUnchanged'])
    result = dict(prior, functionalPassed=passed,
                  passed=int(counts.group(1)) if counts else 0,
                  total=int(counts.group(2)) if counts else 0,
                  priorResultSha256=common.sha(out / 'results.json'),
                  originalDriverSha256=common.sha(out / 'driver.py'),
                  assessorSha256=common.sha(__file__), reassessedUtc=mobile.utc(),
                  correction='Original driver accidentally matched d+ instead of decimal digits; raw app run was 15/15',
                  appRerun=False)
    target = out / 'functional-reassessment.json'
    if target.exists():
        raise RuntimeError('Preserve previous reassessment')
    common.write(target, result)
    shutil.copy2(Path(__file__), out / 'reassessment-driver.py')
    print(json.dumps({k: result[k] for k in ('functionalPassed', 'passed', 'total', 'appRerun', 'methodInterpreterProof')}), flush=True)
    if not passed:
        raise RuntimeError('Completed-run reassessment did not pass')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['build', 'install', 'run', 'reassess', 'cleanup', 'archive'])
    parser.add_argument('--output', type=Path, required=True)
    for name in ('candidate', 'managed', 'controlled', 'packages'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--produced-utc')
    args = parser.parse_args()
    needed = ('candidate', 'managed', 'controlled') if args.phase == 'build' else ('packages', 'produced_utc') if args.phase == 'run' else ()
    for name in needed:
        if getattr(args, name) is None:
            parser.error('This phase requires --' + name.replace('_', '-'))
    common, mobile = helper('ios-r2r-fix-verify'), helper('verify-ios-packages')
    if args.phase == 'build':
        build(args, common, mobile)
    elif args.phase == 'install':
        install(args, common, mobile)
    elif args.phase == 'run':
        execute(args, common, mobile)
    elif args.phase == 'reassess':
        reassess(args, common, mobile)
    elif args.phase == 'cleanup':
        mobile.cleanup(args)
    else:
        with tarfile.open(args.output / 'evidence.tar.gz', 'w:gz') as archive:
            for path in sorted(args.output.rglob('*')):
                if path.is_file() and path.suffix in ('.json', '.log', '.rsp'):
                    archive.add(path, arcname=str(path.relative_to(args.output)))
            archive.add(args.output / 'driver.py', arcname='driver.py')
            if (args.output / 'reassessment-driver.py').exists():
                archive.add(args.output / 'reassessment-driver.py', arcname='reassessment-driver.py')
            for path in (args.output / 'input').glob('RuneCLR.*.dll'):
                archive.add(path, arcname='player-il/' + path.name)
        print(json.dumps({'sha256': common.sha(args.output / 'evidence.tar.gz'),
                          'bytes': (args.output / 'evidence.tar.gz').stat().st_size}), flush=True)


if __name__ == '__main__':
    main()
