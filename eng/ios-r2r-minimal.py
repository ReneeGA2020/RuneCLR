#!/usr/bin/env python3
"""Reduce iOS CID failure by varying callbacks at one unchanged R2R call site."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path('/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr')

LLDB_HELPER = '''import json
from pathlib import Path
import struct
import lldb
OUT = Path(__file__).parent
COUNT = 0
def region(process, address):
    info = lldb.SBMemoryRegionInfo()
    error = process.GetMemoryRegionInfo(address, info)
    return {"error": str(error), "base": info.GetRegionBase(), "end": info.GetRegionEnd(),
        "readable": info.IsReadable(), "writable": info.IsWritable(), "executable": info.IsExecutable()}
def read(process, address, count):
    error = lldb.SBError()
    data = process.ReadMemory(address, count, error)
    return data if error.Success() else b""
def word(process, address):
    data = read(process, address, 8)
    return int.from_bytes(data, "little") if len(data) == 8 else None
def snapshot(frame, label):
    process = frame.GetThread().GetProcess()
    registers = {n: frame.FindRegister(n).GetValueAsUnsigned() for n in
        ["x0","x9","x10","x11","x12","x13","pc","lr"]}
    cell = registers["x11"]; cache = word(process, cell + 8)
    target = word(process, cache + 40) if cache and cache & 3 == 0 else None
    object_type = word(process, registers["x0"])
    cached_type = word(process, cache + 32) if cache and cache & 3 == 0 else None
    code = read(process, target, 32) if target else b""
    literals = []
    for index in range(0, len(code), 4):
        instruction = struct.unpack_from("<I", code, index)[0]
        if instruction & 0xff000000 == 0x58000000:
            displacement = (instruction >> 5) & 0x7ffff
            if displacement & 0x40000: displacement -= 0x80000
            slot = target + index + displacement * 4
            literals.append({"register": "x" + str(instruction & 31),
                "instruction": target + index, "slot": slot, "value": word(process, slot),
                "region": region(process, slot)})
    result = {"label": label, "registers": registers, "cell": cell, "cache": cache,
        "objectMethodTable": object_type, "cachedMethodTable": cached_type,
        "cachedTarget": target, "targetCodeHex": code.hex(), "literalData": literals,
        "cellRegion": region(process, cell),
        "targetRegion": region(process, target) if target else None}
    (OUT / (label + ".json")).write_text(json.dumps(result, indent=2) + chr(10))
    print("MINIMAL_SNAPSHOT " + json.dumps(result), flush=True)
    process.SetSelectedThread(frame.GetThread())
    frame.GetThread().SetSelectedFrame(frame.GetFrameID())
    for cmd in ["register read x0 x9 x10 x11 x12 x13 pc lr",
        "memory read -fx -s8 -c2 "+hex(cell),
        "memory read -fx -s8 -c12 "+hex(cache or 0),
        "disassemble -s "+hex(target or 0)+" -c8",
        "disassemble -s "+hex(registers["lr"]-24)+" -c8"]:
        lldb.debugger.HandleCommand(cmd)
    return result
def dispatch(frame, location, internal):
    global COUNT
    target = frame.GetThread().GetProcess().GetTarget()
    cell = frame.FindRegister("x11").GetValueAsUnsigned()
    module = target.ResolveLoadAddress(cell).GetModule().GetFileSpec().GetFilename()
    if module != "probe.dylib": return False
    COUNT += 1
    snapshot(frame, "dispatch-" + str(COUNT))
    if COUNT >= 2:
        location.GetBreakpoint().SetEnabled(False)
        return True
    return False
def fault():
    frame = lldb.debugger.GetSelectedTarget().GetProcess().GetSelectedThread().GetFrameAtIndex(0)
    snapshot(frame, "fault")
'''

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def command(args, log, timeout=180, env=None, check=True):
    with log.open('w') as stream:
        try:
            status = subprocess.run([str(a) for a in args], stdout=stream,
                stderr=subprocess.STDOUT, timeout=timeout, env=env).returncode
        except subprocess.TimeoutExpired:
            stream.write('\nMINIMAL_TIMEOUT\n')
            status = 124
    if check and status != 0:
        raise RuntimeError(f'{args[0]} returned {status}; see {log}')
    return status

def reduction_sources(sources):
    result = dict(sources)
    host = result['ProbeHost']
    host = host.replace('CallSite(IProbe probe)', 'CallSite(IProbe probe, int ticks)')
    host = host.replace('Console.WriteLine("CALL_TICK"); probe.Tick(new Tick(0, TimeSpan.FromMilliseconds(16)));',
        '''for (int i = 0; i < ticks; i++)
        {
            Console.WriteLine($"TICK_BEFORE index={i}"); Console.Out.Flush();
            probe.Tick(new Tick(i, TimeSpan.FromMilliseconds(16)));
            Console.WriteLine($"TICK_AFTER index={i}"); Console.Out.Flush();
        }''')
    host = host.replace('Cycle(int index, bool unload, List<object> retained)',
        'Cycle(int index, int ticks, bool unload, List<object> retained)')
    host = host.replace('CallSite(probe);', 'CallSite(probe, ticks);')
    host = host.replace('if (unload) context.Unload(); else retained.Add(context);',
        'if (unload) { Console.WriteLine($"CYCLE={index} UNLOAD_REQUEST"); context.Unload(); } else retained.Add(context);')
    host = host.replace('if (cycles < 1 ||',
        'int ticks = int.Parse(Environment.GetEnvironmentVariable("PROBE_TICKS") ?? "3");\n        if (ticks < 1 || cycles < 1 ||')
    host = host.replace('Cycle(i, mode !=', 'Cycle(i, ticks, mode !=')
    host = host.replace('PROBE_BEGIN mode={mode}', 'PROBE_BEGIN mode={mode} ticks={ticks} cycles={cycles}')
    if 'TICK_BEFORE' not in host or 'Cycle(i, ticks,' not in host:
        raise RuntimeError('Original probe template changed')
    result['ProbeHost'] = host
    return result

def builder(root, out):
    original = Path(__file__).with_name('ios-r2r-repro.py')
    old_args = sys.argv
    try:
        sys.argv = [str(original), str(root), str(out)]
        spec = importlib.util.spec_from_file_location('original_probe', original)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.argv = old_args
    return module

def build(root, out):
    module = builder(root, out)
    module.SOURCES = reduction_sources(module.SOURCES)
    module.build()
    native = root / 'ios-r2r-cache-20261012/obj-trace/dlls/mscoree/coreclr/libcoreclr.dylib'
    original = out / 'r2r/Probe.app'
    diagnostic = out / 'diagnostic/Probe.app'
    diagnostic.parent.mkdir()
    shutil.copytree(original, diagnostic)
    shutil.copy2(native, diagnostic / 'libcoreclr.dylib')
    command(['codesign', '--force', '--sign', '-', diagnostic / 'libcoreclr.dylib'], out / 'logs/diagnostic-native-sign.log')
    command(['codesign', '--force', '--sign', '-', diagnostic], out / 'logs/diagnostic-app-sign.log')
    verify_build(root, out)

def verify_build(root, out):
    native = root / 'ios-r2r-cache-20261012/obj-trace/dlls/mscoree/coreclr/libcoreclr.dylib'
    original = out / 'r2r/Probe.app'
    diagnostic = out / 'diagnostic/Probe.app'
    managed = {str(p.relative_to(original)): sha(p) for p in original.rglob('*.dll')}
    if any(sha(diagnostic / n) != h for n, h in managed.items()):
        raise RuntimeError('Diagnostic managed inputs differ')
    for name in ['framework.dylib', 'probe.dylib']:
        if sha(original / name) != sha(diagnostic / name):
            raise RuntimeError('Diagnostic trusted native input changed')
    # Signing the enclosing app updates the executable signature; compare its code.
    executable_code = [subprocess.check_output(['otool', '-s', '__TEXT', '__text', str(p / 'Probe')],
        text=True).splitlines()[1:] for p in [original, diagnostic]]
    if executable_code[0] != executable_code[1]:
        raise RuntimeError('Diagnostic native wrapper code changed')
    identity = {'managedFiles': managed, 'frameworkSha256': sha(original / 'framework.dylib'),
        'probeCompositeSha256': sha(original / 'probe.dylib'),
        'originalNativeSha256': sha(original / 'libcoreclr.dylib'),
        'diagnosticUnsignedSha256': sha(native),
        'diagnosticSignedSha256': sha(diagnostic / 'libcoreclr.dylib'),
        'nativeWrapperTextSha256': hashlib.sha256('\n'.join(executable_code[0]).encode()).hexdigest(),
        'sources': {p.name: sha(p) for p in (out / 'source').glob('*.cs')}}
    (out / 'logs/identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    command(['nm', '-n', original / 'probe.dylib'], out / 'logs/native-symbols.txt')

def result(log, cycles, ticks, mode, switch, status):
    data = log.read_text(errors='replace')
    configuration = f'PROBE_BEGIN mode={mode} ticks={ticks} cycles={cycles}' in data
    native_fault = 'Got a SIGSEGV while executing native code.' in data
    passed = (f'PROBE_PASS cycles={cycles}' in data and 'RUNECLR_EXIT=0' in data
        and len(re.findall(r'CYCLE=\d+ RETURNED', data)) == cycles
        and len(re.findall(r'TICK_AFTER index=\d+', data)) == cycles * ticks
        and (mode != 'collect' or data.count('COLLECTED=True') == cycles)
        and 'Assert failure' not in data and status == 0 and configuration
        and not native_fault)
    pids = re.findall(r'org\.runeclr\.ios\.r2r\.probe\.\w+: (\d+)', data)
    return {'cycles': cycles, 'ticks': ticks, 'mode': mode, 'switch': switch,
        'launcherExit': status, 'passed': passed, 'nativeSigsegv': native_fault,
        'configurationConfirmed': configuration,
        'assertion': 'Assert failure' in data, 'initialized': 'CORECLR_INITIALIZE_HRESULT=0x0' in data,
        'before': len(re.findall(r'TICK_BEFORE index=\d+', data)),
        'after': len(re.findall(r'TICK_AFTER index=\d+', data)),
        'returned': len(re.findall(r'CYCLE=\d+ RETURNED', data)),
        'unloadRequested': len(re.findall(r'CYCLE=\d+ UNLOAD_REQUEST', data)),
        'collected': data.count('COLLECTED=True'),
        'cacheRecords': data.count('RUNECLR_CID_RESOLVE'),
        'cacheSkips': data.count('RUNECLR_CID_RESOLVE skip=1'),
        'pid': int(pids[-1]) if pids else None, 'logSha256': sha(log)}

def matrix_valid(results):
    invalid = [name for name, item in results.items() if not item['initialized']
        or not item['configurationConfirmed'] or item['assertion']
        or not (item['passed'] or item['nativeSigsegv']) or item['launcherExit'] == 124]
    controls_failed = [name for name, item in results.items()
        if name.startswith(('skip-', 'il-')) and not item['passed']]
    return len(results) == 40 and not invalid and not controls_failed

def verify_run(work):
    previous = json.loads((work / 'results.json').read_text())
    results = {name: result(work / (name + '.log'), item['cycles'], item['ticks'],
        item['mode'], item['switch'], item['launcherExit']) for name, item in previous.items()}
    (work / 'results-verified.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps({'matrixValid': matrix_valid(results), 'results': results}, indent=2))
    return 0 if matrix_valid(results) else 1

def capture(root, out):
    work = out / ('capture-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
    work.mkdir()
    (work / 'minimal_lldb.py').write_text(LLDB_HELPER)
    simulator = subprocess.check_output(['xcrun', 'simctl', 'create', 'RuneCLR-R2R-Minimal-Capture',
        'com.apple.CoreSimulator.SimDeviceType.iPhone-17', 'com.apple.CoreSimulator.SimRuntime.iOS-27-0'], text=True).strip()
    (work / 'simulator.uuid').write_text(simulator + '\n')
    env = dict(os.environ)
    for key, value in {'PROBE_MODE': 'collect', 'PROBE_CYCLES': '20', 'PROBE_TICKS': '3',
            'DOTNET_RuneCLRDisableCollectibleInterfaceDispatchCache': '2'}.items():
        env['SIMCTL_CHILD_' + key] = value
    bundle = 'org.runeclr.ios.r2r.probe.r2r'
    try:
        command(['xcrun', 'simctl', 'boot', simulator], work / 'boot-command.log')
        command(['xcrun', 'simctl', 'bootstatus', simulator, '-b'], work / 'boot.log')
        command(['xcrun', 'simctl', 'install', simulator, out / 'diagnostic/Probe.app'], work / 'install.log')
        command(['xcrun', 'simctl', 'launch', '--wait-for-debugger',
            '--stdout=' + str(work / 'managed.stdout.log'), '--stderr=' + str(work / 'managed.stderr.log'),
            simulator, bundle], work / 'launch.log', env=env)
        pid = int(re.search(r': (\d+)', (work / 'launch.log').read_text()).group(1))
        script = work / 'capture.lldb'
        script.write_text('\n'.join([
            'command script import ' + str(work / 'minimal_lldb.py'),
            'breakpoint set -n RhpInterfaceDispatch1',
            'breakpoint command add -F minimal_lldb.dispatch 1',
            'process handle SIGSEGV -s true -n true -p false',
            'continue', 'thread backtrace', 'disassemble -n RhpInterfaceDispatch1',
            'continue', 'thread backtrace', 'script minimal_lldb.fault()',
            'process kill', 'quit']) + '\n')
        status = command(['xcrun', 'lldb', '--batch', '--attach-pid', str(pid), '--source', script],
            work / 'lldb.log', timeout=240, check=False)
        (work / 'lldb.exit').write_text(str(status) + '\n')
    finally:
        command(['xcrun', 'simctl', 'terminate', simulator, bundle], work / 'terminate.log', check=False)
        command(['xcrun', 'simctl', 'shutdown', simulator], work / 'shutdown.log', check=False)
    return 0 if (work / 'fault.json').exists() and (work / 'dispatch-2.json').exists() else 1

def collect_crashes(work, results):
    directory = Path.home() / 'Library/Logs/DiagnosticReports'
    wanted = {r['pid']: name for name, r in results.items() if r['nativeSigsegv'] and r['pid']}
    found = {}
    for attempt in range(6):
        for path in sorted(directory.glob('Probe-*.ips')):
            try:
                text = path.read_text(); data = json.loads(text[text.index('\n') + 1:])
                pid = data.get('pid')
                if pid not in wanted or pid in found:
                    continue
                name = wanted[pid]
                copied = work / (name + '-crash.ips')
                shutil.copy2(path, copied)
                thread = next(t for t in data['threads'] if t.get('triggered'))
                frames = thread.get('frames', [])
                found[pid] = {'case': name, 'pid': pid, 'exception': data.get('exception'),
                    'pc': thread.get('threadState', {}).get('pc'), 'frames': frames[:8],
                    'images': data.get('usedImages'), 'reportSha256': sha(copied)}
            except (ValueError, KeyError, StopIteration):
                continue
        if len(found) == len(wanted):
            break
        time.sleep(1)
    (work / 'native-crashes.json').write_text(json.dumps(list(found.values()), indent=2) + '\n')

def run(root, out):
    work = out / ('run-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
    work.mkdir()
    simulator = subprocess.check_output(['xcrun', 'simctl', 'create', 'RuneCLR-R2R-Minimal',
        'com.apple.CoreSimulator.SimDeviceType.iPhone-17', 'com.apple.CoreSimulator.SimRuntime.iOS-27-0'], text=True).strip()
    (work / 'simulator.uuid').write_text(simulator + '\n')
    results = {}
    cases = [('one-tick', 1, 1, 'retain'), ('two-ticks', 1, 2, 'retain'),
        ('three-ticks', 1, 3, 'retain'), ('twenty-one', 20, 1, 'collect'),
        ('twenty-two', 20, 2, 'collect'), ('retain-three', 20, 3, 'retain'),
        ('collect-three', 20, 3, 'collect'), ('unload-three', 20, 3, 'unload')]
    try:
        command(['xcrun', 'simctl', 'boot', simulator], work / 'boot-command.log')
        command(['xcrun', 'simctl', 'bootstatus', simulator, '-b'], work / 'boot.log')
        for variant, lane, switch in [('original', 'r2r', '0'), ('off', 'diagnostic', '0'),
                ('trace', 'diagnostic', '2'), ('skip', 'diagnostic', '1'), ('il', 'il', '0')]:
            package = out / lane / 'Probe.app'
            bundle = 'org.runeclr.ios.r2r.probe.' + ('il' if lane == 'il' else 'r2r')
            command(['xcrun', 'simctl', 'install', simulator, package], work / (variant + '-install.log'), timeout=60)
            for case, cycles, ticks, mode in cases:
                name = variant + '-' + case
                env = dict(os.environ)
                for key, value in {'PROBE_MODE': mode, 'PROBE_CYCLES': str(cycles),
                        'PROBE_TICKS': str(ticks), 'DOTNET_RuneCLRDisableCollectibleInterfaceDispatchCache': switch}.items():
                    env['SIMCTL_CHILD_' + key] = value
                log = work / (name + '.log')
                status = command(['xcrun', 'simctl', 'launch', '--console', simulator, bundle],
                    log, timeout=60, env=env, check=False)
                results[name] = result(log, cycles, ticks, mode, switch, status)
                print(name + ': ' + json.dumps(results[name]), flush=True)
                (work / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
                command(['xcrun', 'simctl', 'terminate', simulator, bundle], work / (name + '-terminate.log'), check=False)
        collect_crashes(work, results)
    finally:
        command(['xcrun', 'simctl', 'shutdown', simulator], work / 'shutdown.log', check=False)
    return 0 if matrix_valid(results) else 1

def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ('build', 'verify-build', 'verify-run', 'run', 'capture'):
        raise SystemExit('Usage: ios-r2r-minimal.py build|verify-build|run|capture ROOT UNIQUE_OUTPUT; verify-run ROOT RUN_DIRECTORY')
    action, root, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    if action == 'build':
        return build(root, out)
    if action == 'verify-build':
        return verify_build(root, out)
    if action == 'verify-run':
        return verify_run(out)
    if action == 'capture':
        return capture(root, out)
    return run(root, out)

if __name__ == '__main__':
    sys.exit(main())
