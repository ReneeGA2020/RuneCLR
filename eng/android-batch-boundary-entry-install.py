#!/usr/bin/env python3
"""Finish an owned gated APK installation with one hash-bound asset transfer."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import uuid

BASE_SHA = '66adcf5a7a60a13db4695d43b2c4a18643ab39392d7f33884d74da7ba5e46c50'

def base_module():
    path = Path(__file__).with_name('android-batch-boundary-apk.py')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == BASE_SHA
    spec = importlib.util.spec_from_file_location('boundary_base', path)
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    return base

def inventory(base, args, state, out, name, native_dir):
    expected = dict(state['appHashes'])
    expected.update(state['authorHashes'])
    paths = {n: native_dir + '/' + n if n.endswith('.so') else 'files/' + n for n in expected}
    apkpath = base.adb(args, ['shell', 'pm', 'path', state['package']])[0].removeprefix('package:')
    assert '\n' not in apkpath and apkpath.startswith('/data/app/')
    paths['apk/base.apk'] = apkpath
    expected['apk/base.apk'] = state['apkSha256']
    argv = [str(args.android_root / 'sdk/platform-tools/adb.exe'), '-s', args.serial,
            'exec-out', 'run-as', state['package'], 'sha256sum', *paths.values()]
    assert all(re.fullmatch('[A-Za-z0-9_/+=.~-]+', path) for path in paths.values())
    q = subprocess.run(argv, capture_output=True, timeout=60)
    (out / (name + '.sha256sum.log')).write_bytes(q.stdout)
    (out / (name + '.stderr.log')).write_bytes(q.stderr)
    base.write(out / (name + '.command.json'), {'argv': argv, 'exit': q.returncode})
    assert q.returncode == 0
    rows = q.stdout.decode().splitlines()
    assert len(rows) == len(paths)
    for (name_key, path), row in zip(paths.items(), rows):
        digest, actual_path = row.split(None, 1)
        assert actual_path == path and digest == expected[name_key], 'Installed actual path/hash differs: ' + name_key
    base.write(out / (name + '.json'), expected)
    return expected

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--android-root', type=Path, default=Path('D:/RuneCLR-Android'))
    p.add_argument('--serial', default='emulator-5556')
    p.add_argument('--verify-only', action='store_true')
    args = p.parse_args()
    base = base_module()
    base.device(args)
    root = args.output.resolve()
    state = base.load(root / 'state.json')
    if args.verify_only:
        assert state['installed'] and state.get('authorHashes')
        out = root / 'entry-install-recovery-attempt2'
        out.mkdir(exist_ok=False)
        appinfo = base.adb(args, ['shell', 'dumpsys', 'package', state['package']])[0]
        m = re.search(r'(?m)^\s*(?:legacyNativeLibraryDir|nativeLibraryDir)=([^\s]+)', appinfo)
        assert m
        native = base.adb(args, ['shell', 'run-as', state['package'], 'find', m[1], '-name', 'libcoreclr.so'])[0].splitlines()
        assert len(native) == 1
        verified = inventory(base, args, state, out, 'installed-final', native[0].rsplit('/', 1)[0])
        base.write(out / 'results.json', {'success': True, 'verifiedEntries': len(verified),
            'verificationOnly': True, 'transfersNotReplayed': True, 'driverSha256': base.sha(__file__),
            'apkSha256': state['apkSha256'], 'physicalDeviceTouched': False})
        print('ANDROID_BATCH_ENTRY_INSTALL_VERIFICATION_PASS', len(verified), state['package'])
        return
    assert state['installed'] and not state.get('authorHashes') and base.sha(state['apk']) == state['apkSha256']
    out = root / 'entry-install-recovery-attempt1'
    out.mkdir(exist_ok=False)
    base.inputs(args.inputs)
    manifest = base.load(args.inputs / 'input-manifest.json')
    assert state['inputFiles'] == manifest['files']
    transferred = {n: h for n, h in state['appHashes'].items() if not n.endswith('.so')}
    archive_path = out / 'installed-assets.tar'
    with tarfile.open(archive_path, 'w') as archive:
        for name, digest in transferred.items():
            assert re.fullmatch('[A-Za-z0-9_.-]+', name) and base.sha(root / 'app' / name) == digest
            archive.add(root / 'app' / name, arcname=name, recursive=False)
    staged = '/data/local/tmp/runeclr-batch-entry-assets-' + uuid.uuid4().hex
    owned = 'files/entry-assets-' + uuid.uuid4().hex + '.tar'
    base.adb(args, ['push', archive_path, staged])
    try:
        base.adb(args, ['shell', 'run-as', state['package'], 'cp', staged, owned])
        assert base.adb(args, ['shell', 'run-as', state['package'], 'sha256sum', owned])[0].split()[0] == base.sha(archive_path)
        base.adb(args, ['shell', 'run-as', state['package'], 'tar', '-xf', owned, '-C', 'files'])
    finally:
        base.adb(args, ['shell', 'run-as', state['package'], 'rm', '-f', owned], False)
        base.adb(args, ['shell', 'rm', '-f', staged], False)
    produced = root / 'postinstall-author'
    produced.mkdir(exist_ok=False)
    started = base.utc()
    for name in ('author/BatchBoundary.Author.dll', 'author/BatchBoundary.Contract.dll'):
        target = produced / Path(name).name
        shutil.copy2(args.inputs / name, target)
        base.push(args, state, target, name, out / 'author-transfer.log')
    state['authorHashes'] = {n: manifest['files'][n] for n in ('author/BatchBoundary.Author.dll', 'author/BatchBoundary.Contract.dll')}
    base.write(root / 'postinstall-author.json', {'installedUtc': state['installedUtc'], 'transferStartedUtc': started,
        'completedUtc': base.utc(), 'apkSha256': state['apkSha256'],
        'source': 'Unchanged frozen author IL copied after successful APK installation; no newly compiled author claim',
        'files': state['authorHashes']})
    state['authorTransferredUtc'] = base.utc()
    base.write(root / 'state.json', state)
    appinfo = base.adb(args, ['shell', 'dumpsys', 'package', state['package']])[0]
    m = re.search(r'(?m)^\s*(?:legacyNativeLibraryDir|nativeLibraryDir)=([^\s]+)', appinfo)
    assert m
    native = base.adb(args, ['shell', 'run-as', state['package'], 'find', m[1], '-name', 'libcoreclr.so'])[0].splitlines()
    assert len(native) == 1
    verified = inventory(base, args, state, out, 'installed-final', native[0].rsplit('/', 1)[0])
    base.write(out / 'results.json', {'success': True, 'driverSha256': base.sha(__file__), 'baseDriverSha256': BASE_SHA,
        'preservedFailedOriginalInstallation': True, 'apkInstalledAlready': True, 'verifiedEntries': len(verified),
        'archiveSha256': base.sha(archive_path), 'apkSha256': state['apkSha256'], 'physicalDeviceTouched': False})
    print('ANDROID_BATCH_ENTRY_INSTALL_RECOVERY_PASS', len(verified), state['package'])

if __name__ == '__main__':
    main()
