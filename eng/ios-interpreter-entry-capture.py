#!/usr/bin/env python3
"""Capture a probe's interpreter entry or an early native startup fault with LLDB."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import tarfile

import importlib.util


def helper(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'),
                                                Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FAULT_HELPER = '''import json
from pathlib import Path
import lldb
def capture():
    target = lldb.debugger.GetSelectedTarget()
    process = target.GetProcess()
    thread = process.GetSelectedThread()
    frame = thread.GetFrameAtIndex(0)
    result = {'stopReason': thread.GetStopDescription(1024),
        'registers': {n: frame.FindRegister(n).GetValueAsUnsigned() for n in ['pc','lr','x0','x1','x8','x9','x10','x11','x12']},
        'frames': [{'pc': f.GetPC(), 'function': f.GetFunctionName(),
            'module': f.GetModule().GetFileSpec().GetFilename()} for f in thread]}
    (Path(__file__).parent/'fault.json').write_text(json.dumps(result, indent=2)+chr(10))
    print('STARTUP_FAULT '+json.dumps(result),flush=True)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('app', 'native', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--mode', choices=['interpreter', 'startup-fault'], default='interpreter')
    args = parser.parse_args()
    release = helper('ios-r2r-release-verify')
    common = helper('ios-r2r-fix-verify')
    mobile = helper('verify-ios-packages')
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    import plistlib
    bundle = plistlib.loads((args.app / 'Info.plist').read_bytes())['CFBundleIdentifier']
    if mobile.macho_sections(args.native) != mobile.macho_sections(args.app / 'libcoreclr.dylib'):
        raise RuntimeError('Native code/data differ from prepared app')
    expected = mobile.tree(args.app)
    common.write(out / 'identity.json', {'mode': args.mode, 'native': str(args.native), 'nativeSha256': common.sha(args.native),
                 'app': str(args.app), 'bundleFiles': expected, 'driverSha256': common.sha(__file__)})
    shutil.copy2(Path(__file__), out / 'driver.py')
    (out / 'release_lldb.py').write_text(release.LLDB_HELPER)
    (out / 'fault_lldb.py').write_text(FAULT_HELPER)
    sim = common.capture(['xcrun', 'simctl', 'create', 'RuneCLR-Native-Entry-Capture',
                         'com.apple.CoreSimulator.SimDeviceType.iPhone-17', 'com.apple.CoreSimulator.SimRuntime.iOS-27-0'])
    common.write(out / 'simulator.json', {'uuid': sim})
    result = {'passed': False, 'mode': args.mode}
    try:
        common.logged(['xcrun', 'simctl', 'boot', sim], out / 'boot-command.log')
        common.logged(['xcrun', 'simctl', 'bootstatus', sim, '-b'], out / 'boot.log')
        common.logged(['xcrun', 'simctl', 'install', sim, args.app], out / 'install.log')
        installed = Path(common.capture(['xcrun', 'simctl', 'get_app_container', sim, bundle, 'app']))
        if mobile.tree(installed) != expected:
            raise RuntimeError('Installed bundle differs')
        env = {k: v for k, v in os.environ.items() if not k.startswith(('SIMCTL_CHILD_DOTNET_', 'SIMCTL_CHILD_COMPlus_', 'SIMCTL_CHILD_PROBE_'))}
        env.update({'SIMCTL_CHILD_PROBE_MODE': 'collect', 'SIMCTL_CHILD_PROBE_CYCLES': '2', 'SIMCTL_CHILD_PROBE_TICKS': '3'})
        common.logged(['xcrun', 'simctl', 'launch', '--wait-for-debugger', '--stdout=' + str(out / 'managed.stdout.log'),
                       '--stderr=' + str(out / 'managed.stderr.log'), sim, bundle], out / 'launch.log', env=env)
        pid = re.search(r': (\d+)', (out / 'launch.log').read_text()).group(1)
        commands = ['breakpoint set -n coreclr_initialize', 'continue', 'breakpoint disable 1',
                    'target symbols add ' + str(args.native.with_name(args.native.name + '.dwarf'))]
        if args.mode == 'interpreter':
            commands += ['command script import ' + str(out / 'release_lldb.py'), 'script release_lldb.setup()', 'continue', 'process status']
        else:
            commands += ['command script import ' + str(out / 'fault_lldb.py'),
                         'process handle SIGSEGV -s true -n true -p false', 'continue',
                         'thread backtrace all', 'register read', 'disassemble --frame --count 20',
                         'script fault_lldb.capture()', 'process kill']
        commands += ['quit']
        script = out / 'capture.lldb'
        script.write_text('\n'.join(commands) + '\n')
        status = common.logged(['xcrun', 'lldb', '--batch', '--attach-pid', pid, '--source', script], out / 'lldb.log', timeout=240, check=False)
        if args.mode == 'interpreter':
            entries = json.loads((out / 'interpreter-entries.json').read_text()) if (out / 'interpreter-entries.json').exists() else []
            methods = release.plugin_methods(args.app / 'plugin/ProbePlugin.dll')
            valid = [e for e in entries if e['module'] == 'libcoreclr.dylib' and e['receiverMethodTable'] == e['methodTable']
                     and e['bytecodeStart'] == e['methodDescBytecodeStart'] and e['bytecodeSizeSlots'] > 0 and e['bytecodePrefixHex'] and e['readSuccess']]
            observed = {e['methodDefToken'] for e in valid}
            normal_exit = bool(re.search(r'exited with status = 0', (out / 'lldb.log').read_text()))
            counts = {name: sum(e['methodDefToken'] == methods[name] for e in valid) for name in ('Start', 'Tick', 'Stop')}
            completed = 'CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0' in (out / 'managed.stdout.log').read_text(errors='replace')
            expected_counts = {'Start': 2, 'Tick': 6, 'Stop': 2}
            passed = (status == 0 and normal_exit and completed and not (out / 'capture-error.json').exists()
                      and all(0 < counts[n] <= expected_counts[n] for n in counts))
            result.update({'passed': bool(passed), 'metadataMethods': methods, 'validEntries': len(valid),
                           'observedMethodTokens': sorted(observed), 'methodEntryCounts': counts, 'managedExitZero': completed,
                           'expectedInvocationCounts': expected_counts, 'completeInvocationCapture': counts == expected_counts})
        else:
            fault = json.loads((out / 'fault.json').read_text()) if (out / 'fault.json').exists() else {}
            passed = status == 0 and ('EXC_BAD_ACCESS' in fault.get('stopReason', '') or 'SIGSEGV' in fault.get('stopReason', ''))
            result.update({'passed': bool(passed), 'fault': fault, 'scope': 'captured expected startup fault; not successful script execution'})
        result.update({'lldbExit': status, 'bundleUnchanged': mobile.tree(installed) == expected})
    finally:
        common.logged(['xcrun', 'simctl', 'terminate', sim, bundle], out / 'terminate.log', check=False)
        shutdown = common.logged(['xcrun', 'simctl', 'shutdown', sim], out / 'shutdown.log', check=False)
        common.write(out / 'simulator.json', {'uuid': sim, 'shutdownExit': shutdown})
    result['passed'] = result['passed'] and result['bundleUnchanged'] and shutdown == 0
    common.write(out / 'results.json', result)
    with tarfile.open(out / 'evidence.tar.gz', 'w:gz') as archive:
        for path in sorted(out.iterdir()):
            if path.is_file() and path.suffix in ('.json', '.log', '.lldb', '.py'):
                archive.add(path, arcname=path.name)
        archive.add(Path(__file__).with_name('ios-r2r-release-verify.py'), arcname='ios-r2r-release-verify.py')
    print(json.dumps(result), flush=True)
    print('Capture archive SHA256=' + common.sha(out / 'evidence.tar.gz'), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
