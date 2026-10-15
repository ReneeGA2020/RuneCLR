#!/usr/bin/env python3
"""Run a prepared session-policy LLDB capture on the owned simulator only."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess

def helper(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--player', type=Path, required=True)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    common, mobile = helper('ios-r2r-fix-verify'), helper('verify-ios-packages')
    state = json.loads((args.player / 'state.json').read_text())
    out = args.capture.resolve()
    if (out / 'capture-request.json').exists():
        raise ValueError('Preserve existing capture; prepare a new output')
    if not json.loads((args.player / 'run-selection/results.json').read_text())['passed']:
        raise ValueError('Independent functional selection run required first')
    app, sim, bundle = Path(state['installedApp']), state['simulator'], state['bundleId']
    if mobile.tree(app) != state['bundleHashes'] or mobile.tree(Path(state['app'])) != state['bundleHashes']:
        raise ValueError('Player identity changed')
    if not (out / 'capture.lldb').is_file():
        raise ValueError('Prepare matching capture first')
    env = {key: value for key, value in os.environ.items() if not key.startswith(('SIMCTL_CHILD_DOTNET_', 'SIMCTL_CHILD_COMPlus_', 'SIMCTL_CHILD_RUNECLR_', 'SIMCTL_CHILD_PROBE_'))}
    env.update({'SIMCTL_CHILD_RUNECLR_SESSION_PHASE': 'selection',
                'SIMCTL_CHILD_RUNECLR_PROBE_LANE': 'required',
                'SIMCTL_CHILD_RUNECLR_PROBE_DIRECTORY': str(app / 'plugin'),
                'SIMCTL_CHILD_RUNECLR_PROBE_EVIDENCE': str(Path(state['dataContainer']) / 'Documents/selection-capture-evidence')})
    common.write(out / 'capture-request.json', {'simulator': sim, 'bundleId': bundle,
        'environment': {key: value for key, value in env.items() if key.startswith('SIMCTL_CHILD_')},
        'captureScriptSha256': common.sha(out / 'capture.lldb'), 'driverSha256': common.sha(__file__),
        'functionalReceiptSha256': common.sha(args.player / 'run-selection/results.json')})
    shutil.copy2(__file__, out / 'capture-run-driver.py')
    result = {'outerTransportPassed': False}
    try:
        common.logged(['xcrun', 'simctl', 'launch', '--wait-for-debugger',
            '--stdout=' + str(out / 'managed.stdout.log'), '--stderr=' + str(out / 'managed.stderr.log'),
            sim, bundle], out / 'launch.log', env=env)
        pid = int(re.search(': ([0-9]+)', (out / 'launch.log').read_text()).group(1))
        query = ['xcrun', 'simctl', 'spawn', sim, 'log', 'stream', '--style', 'json', '--predicate', 'processIdentifier == ' + str(pid)]
        common.write(out / 'unified-query.json', {'command': query, 'appPid': pid})
        with (out / 'managed.unified.log').open('w') as output, (out / 'unified.stderr.log').open('w') as errors:
            stream = subprocess.Popen(query, stdout=output, stderr=errors, start_new_session=True)
            try:
                status = common.logged(['xcrun', 'lldb', '--batch', '--attach-pid', str(pid), '--source', out / 'capture.lldb'],
                                       out / 'lldb.log', timeout=args.timeout, check=False)
            finally:
                if stream.poll() is None: stream.send_signal(signal.SIGINT)
                try: stream.wait(timeout=15)
                except subprocess.TimeoutExpired: stream.kill(); stream.wait(timeout=15)
                common.write(out / 'unified-completed.json', {'streamExit': stream.returncode})
        raw = (out / 'managed.unified.log').read_text(errors='replace')
        first, last = raw.find('['), raw.rfind(']')
        events = json.loads(raw[first:last + 1])
        if not isinstance(events, list) or any(event.get('processID') != pid for event in events):
            raise ValueError('Unified logs must belong to the actual captured PID')
        common.write(out / 'managed-messages.json', [event.get('eventMessage', '') for event in events])
        stdout = (out / 'managed.stdout.log').read_text(errors='replace')
        stderr = (out / 'managed.stderr.log').read_text(errors='replace')
        debugger = (out / 'lldb.log').read_text(errors='replace')
        result.update({'appPid': pid, 'lldbExit': status,
            'normalNativeExit': 'exited with status = 0' in debugger,
            'nativeManagedExitZero': 'CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0' in stdout,
            'explicitMode0Diagnostic0': 'SESSION_NATIVE_CONFIG InterpMode=0 RuneCLRInterpretCollectible=0' in stdout,
            'bundleUnchanged': mobile.tree(app) == state['bundleHashes'],
            'noCrashOrAssertion': not any(word in stdout + stderr + debugger for word in ['SIGSEGV', 'Assert failure', 'Assertion failed']),
            'methodProof': 'Separate read-only entry assessor required; transport status is not method proof'})
        result['outerTransportPassed'] = all([status == 0, result['normalNativeExit'], result['nativeManagedExitZero'],
            result['explicitMode0Diagnostic0'], result['bundleUnchanged'], result['noCrashOrAssertion']])
    except Exception as error:
        result['driverError'] = repr(error)
    finally:
        common.logged(['xcrun', 'simctl', 'terminate', sim, bundle], out / 'terminate.log', check=False)
        result['rawHashes'] = {path.name: common.sha(path) for path in sorted(out.iterdir()) if path.is_file()}
        common.write(out / 'outer-results.json', result)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result['outerTransportPassed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
