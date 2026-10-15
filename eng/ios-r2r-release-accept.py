#!/usr/bin/env python3
"""Run full/minimal lifecycle fixtures built with matching Release runtime inputs."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import tarfile


def helper(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layout', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    common = helper('ios-r2r-fix-verify')
    mobile = helper('verify-ios-packages')
    minimal = helper('ios-r2r-minimal')
    layout = json.loads((args.layout / 'identity.json').read_text())
    receipt = json.loads((args.layout / 'results.json').read_text())
    if not receipt['buildSuccess'] or not receipt['sourceTrackedClean']:
        raise RuntimeError('Layout build did not pass')
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    common.write(out / 'layout-identity.json', layout)
    sim = common.capture(['xcrun', 'simctl', 'create', 'RuneCLR-Matching-Release-Acceptance',
                         'com.apple.CoreSimulator.SimDeviceType.iPhone-17', 'com.apple.CoreSimulator.SimRuntime.iOS-27-0'])
    common.write(out / 'simulator.json', {'uuid': sim})
    results = {}
    try:
        common.logged(['xcrun', 'simctl', 'boot', sim], out / 'boot-command.log')
        common.logged(['xcrun', 'simctl', 'bootstatus', sim, '-b'], out / 'boot.log')
        for kind in ('full', 'minimal'):
            app = Path(layout['apps'][kind]['app'])
            if mobile.tree(app) != layout['apps'][kind]['tree']:
                raise RuntimeError('Prepared layout changed')
            bundle = plistlib.loads((app / 'Info.plist').read_bytes())['CFBundleIdentifier']
            common.logged(['xcrun', 'simctl', 'install', sim, app], out / (kind + '-install.log'))
            installed = Path(common.capture(['xcrun', 'simctl', 'get_app_container', sim, bundle, 'app']))
            if mobile.tree(installed) != mobile.tree(app):
                raise RuntimeError('Installed bundle changed')
            env = {k: v for k, v in os.environ.items() if not k.startswith(('SIMCTL_CHILD_DOTNET_', 'SIMCTL_CHILD_COMPlus_', 'SIMCTL_CHILD_PROBE_'))}
            if kind == 'minimal':
                env.update({'SIMCTL_CHILD_PROBE_MODE': 'collect', 'SIMCTL_CHILD_PROBE_CYCLES': '20', 'SIMCTL_CHILD_PROBE_TICKS': '3'})
            log = out / (kind + '.log')
            status = common.logged(['xcrun', 'simctl', 'launch', '--console', sim, bundle], log, env=env, check=False, timeout=240)
            text = log.read_text(errors='replace')
            if kind == 'minimal':
                details = minimal.result(log, 20, 3, 'collect', 'none', status)
                passed = details['passed'] and 'compiled=False' in text
            else:
                details = {'expectedTests': 21}
                passed = status == 0 and '21/21 tests passed' in text and 'DynamicCodeCompiled=False' in text
            passed = (passed and 'RUNECLR_EXIT=0' in text and '.NET 12.0.0-dev' in text
                      and 'Got a SIGSEGV' not in text and 'Assert failure' not in text
                      and mobile.tree(installed) == mobile.tree(app))
            results[kind] = {'passed': bool(passed), 'launcherExit': status, 'details': details, 'logSha256': common.sha(log)}
            common.write(out / 'runs.json', results)
            print(kind + ': ' + json.dumps(results[kind]), flush=True)
            common.logged(['xcrun', 'simctl', 'terminate', sim, bundle], out / (kind + '-terminate.log'), check=False)
    finally:
        shutdown = common.logged(['xcrun', 'simctl', 'shutdown', sim], out / 'shutdown.log', check=False)
        common.write(out / 'simulator.json', {'uuid': sim, 'shutdownExit': shutdown})
    success = len(results) == 2 and all(r['passed'] for r in results.values()) and shutdown == 0
    common.write(out / 'results.json', {'success': success, 'runs': results,
                 'scope': 'functional acceptance; method interpreter entry recorded separately'})
    with tarfile.open(out / 'evidence.tar.gz', 'w:gz') as archive:
        for path in out.iterdir():
            if path.is_file() and path.suffix in ('.log', '.json'):
                archive.add(path, arcname=path.name)
        archive.add(Path(__file__), arcname='driver.py')
    print('Release functional archive SHA256=' + common.sha(out / 'evidence.tar.gz'), flush=True)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
