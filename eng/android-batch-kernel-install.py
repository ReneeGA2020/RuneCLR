#!/usr/bin/env python3
"""Install the fresh Kernel APK and transfer unchanged author IL after installation."""
import argparse
import hashlib
import importlib.util
import inspect
from pathlib import Path
import shutil

INSTALLER_SHA = '58fa6da44ff2eaf3a4f6fcf35e1c370cfe90bce7891a9d1934fee283a04d6dfb'

def helper(name):
    path = Path(__file__).with_name(name + '.py')
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=('start', 'install', 'cleanup'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--inputs', type=Path, default=Path('artifacts/mobile-budget-batching/kernel-inputs-20261015-attempt3'))
    p.add_argument('--android-root', type=Path, default=Path('D:/RuneCLR-Android'))
    p.add_argument('--serial', default='emulator-5556')
    p.add_argument('--shutdown', action='store_true')
    args = p.parse_args()
    base = helper('android-batch-kernel-apk').adapted()[0]
    if args.phase == 'start':
        base.start(args)
        return
    if args.phase == 'cleanup':
        base.cleanup(args)
        return
    base.device(args)
    state = base.load(args.output / 'state.json')
    assert not state.get('authorHashes')
    assert base.sha(state['apk']) == state['apkSha256']
    if not state['installed']:
        _, installed = base.adb(args, ['install', '-r', '-d', state['apk']])
        assert installed == 0
        state.update(installed=True, installedUtc=base.utc(), serial=args.serial)
        base.write(args.output / 'state.json', state)
    base.adb(args, ['shell', 'run-as', state['package'], 'mkdir', '-p', 'files'])
    path = Path(__file__).with_name('android-batch-boundary-entry-install.py')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == INSTALLER_SHA
    installer = helper('android-batch-boundary-entry-install')
    source = inspect.getsource(installer.main)
    source = source.replace("'author/BatchBoundary.Author.dll'", "'author/RuneCLR.BatchKernel.dll'").replace(
        "'author/BatchBoundary.Contract.dll'", "'author/RuneCLR.Abstractions.dll'")
    source = source.replace('entry-install-recovery-attempt1', 'kernel-install-attempt1')
    if (args.output / 'kernel-install-attempt1').exists():
        assert not state.get('authorHashes')
        source = source.replace('kernel-install-attempt1', 'kernel-install-attempt2')
    env = dict(installer.__dict__)
    env.update(base_module=lambda: base, __file__=__file__)
    # Keep the hash-bound bulk inventory while supplying this invocation's fixed arguments.
    import sys
    saved = sys.argv
    sys.argv = [__file__, '--output', str(args.output), '--inputs', str(args.inputs),
                '--android-root', str(args.android_root), '--serial', args.serial]
    try:
        exec(compile(source, str(Path(__file__).resolve()), 'exec'), env)
        env['main']()
    finally:
        sys.argv = saved
    shutil.copy2(__file__, args.output / 'kernel-install-driver.py')

if __name__ == '__main__':
    main()
