#!/usr/bin/env python3
"""Capture native R2R and IL-helper entry evidence for one simulator process."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def run(argv, log, env=None, check=True, timeout=600):
    with Path(log).open('w', encoding='utf-8', errors='replace') as stream:
        status = subprocess.run([str(value) for value in argv], stdout=stream,
                                stderr=subprocess.STDOUT, env=env,
                                check=False, timeout=timeout).returncode
    if check and status:
        raise RuntimeError(f'{argv[0]} failed ({status}); see {log}')
    return status


def methods(path):
    spec = importlib.util.spec_from_file_location('trusted_update_metadata', Path(__file__).with_name('ios-r2r-release-verify.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.plugin_methods(Path(path), required=(), qualified=True)


def nm_ranges(owner, log):
    text = subprocess.check_output(['nm', '-nm', str(owner)], text=True, errors='replace')
    Path(log).write_text(text, encoding='utf-8')
    rows = []
    for line in text.splitlines():
        match = re.search(r'^\s*([0-9a-fA-F]+)\s+([^ ]+)\s+(.+)$', line)
        if not match:
            continue
        try:
            address = int(match.group(1), 16)
        except ValueError:
            continue
        name = match.group(3).strip()
        if 'TrustedUpdate' in name:
            rows.append({'address': address, 'name': name, 'kind': match.group(2)})
    rows.sort(key=lambda row: row['address'])
    # Prefer the downloaded update method. A name that merely contains both
    # Update and Run also matches AnchorHost Driver.Run and must not win.
    execute = '_TrustedUpdate_Update_TrustedUpdate_Business__Execute'
    update_run = '_TrustedUpdate_Update_TrustedUpdate_Update__Run'
    def text_named(token):
        return [row for row in rows if '__TEXT' in row['kind'] and token in row['name'] and row['name'].endswith(token)]
    selected = text_named(execute)
    rule = 'Business.Execute'
    if not selected:
        selected = text_named(update_run)
        rule = 'Update.Run'
    if not selected:
        raise RuntimeError('R2R owner has no Business.Execute or Update.Run __TEXT symbol; see ' + str(log))
    first = dict(selected[0])
    first['selection'] = rule
    following = next((row['address'] for row in rows if row['address'] > first['address']), first['address'] + 1)
    first['end'] = following
    return rows, first


LLDB_HELPER = r'''import json
from pathlib import Path
import lldb
OUT = Path(__file__).parent
CONFIG = json.loads((OUT / 'capture-config.json').read_text())
EVENTS = []
NATIVE_BP = None
DLOPEN_BP = None

def region(process, address):
    info = lldb.SBMemoryRegionInfo(); error = process.GetMemoryRegionInfo(address, info)
    return {'base': info.GetRegionBase(), 'end': info.GetRegionEnd(), 'readable': info.IsReadable(),
            'writable': info.IsWritable(), 'executable': info.IsExecutable(), 'error': str(error)}

def module_for(target, name):
    for module in target.modules:
        if module.file.basename == name: return module
    return None

def capture_native(frame, location, internal):
    process = frame.thread.process; target = process.target; pc = frame.pc
    owner = module_for(target, CONFIG['ownerBasename'])
    if owner is None: return False
    base = owner.GetObjectFileHeaderAddress().GetLoadAddress(target)
    start = base + CONFIG['method']['address']; end = base + CONFIG['method']['end']
    if not (start <= pc < end): return False
    event = {'kind':'r2r-method','pc':pc,'ownerPath':CONFIG['ownerPath'],
             'ownerSha256':CONFIG['ownerSha256'],'ownerBase':base,'methodStart':start,
             'methodEnd':end,'pcInMethodRange':True,'module':owner.file.fullpath,
             'region':region(process, pc)}
    EVENTS.append(event)
    (OUT/'native-entry.json').write_text(json.dumps(event, indent=2)+'\n')
    location.GetBreakpoint().SetEnabled(False)
    return False

def capture_stub(frame, location, internal):
    regs = {name: frame.FindRegister(name).GetValueAsUnsigned() for name in ('pc','x0','x12','lr')}
    module = frame.module.file.fullpath if frame.module.IsValid() else ''
    event = {'kind':'interpreter-stub','pc':regs['pc'],'function':frame.GetFunctionName(),
             'module':module,'registers':regs,'bytecodeHeader':regs['x12'],
             'helperPath':CONFIG['helperPath'],'helperSha256':CONFIG['helperSha256'],
             'helperMethods':CONFIG['helperMethods'],'scope':'stub identity/call evidence'}
    EVENTS.append(event)
    (OUT/'interpreter-entries.json').write_text(json.dumps(EVENTS, indent=2)+'\n')
    return False

def record_address_locations(count):
    path = OUT / 'breakpoints.json'
    data = json.loads(path.read_text()) if path.exists() else {}
    data['addressBreakpointLocations'] = count
    path.write_text(json.dumps(data, indent=2)+'\n')

def install_address_breakpoint(target):
    global NATIVE_BP, DLOPEN_BP
    if NATIVE_BP is not None:
        return
    owner = module_for(target, CONFIG['ownerBasename'])
    if owner is None:
        return
    base = owner.GetObjectFileHeaderAddress().GetLoadAddress(target)
    if base == lldb.LLDB_INVALID_ADDRESS:
        return
    NATIVE_BP = target.BreakpointCreateByAddress(base + CONFIG['method']['address'])
    NATIVE_BP.SetScriptCallbackFunction('trusted_lldb.capture_native')
    record_address_locations(NATIVE_BP.num_locations)
    if DLOPEN_BP is not None:
        DLOPEN_BP.SetEnabled(False)

def on_dlopen(frame, location, internal):
    target = frame.thread.process.target
    if module_for(target, CONFIG['ownerBasename']) is not None:
        install_address_breakpoint(target)
        return False
    # Owner is not in target.modules at dlopen entry. Keep this breakpoint
    # enabled and look up the module again after dlopen returns.
    ra = frame.FindRegister('lr').GetValueAsUnsigned()
    if ra:
        ret = target.BreakpointCreateByAddress(ra)
        ret.SetOneShot(True)
        ret.SetScriptCallbackFunction('trusted_lldb.after_dlopen_return')
    return False

def after_dlopen_return(frame, location, internal):
    install_address_breakpoint(frame.thread.process.target)
    return False

def setup():
    global DLOPEN_BP
    target = lldb.debugger.GetSelectedTarget()
    stub = target.BreakpointCreateByName('InterpreterStub'); stub.SetScriptCallbackFunction('trusted_lldb.capture_stub')
    DLOPEN_BP = target.BreakpointCreateByName('dlopen'); DLOPEN_BP.SetScriptCallbackFunction('trusted_lldb.on_dlopen')
    (OUT/'breakpoints.json').write_text(json.dumps({'stubLocations':stub.num_locations,
        'dlopenLocations':DLOPEN_BP.num_locations,'addressBreakpointLocations':None}, indent=2)+'\n')

def finish():
    (OUT/'entry-events.json').write_text(json.dumps(EVENTS, indent=2)+'\n')
'''


def capture(args):
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    owner = args.owner.resolve(); helper = args.helper.resolve()
    rows, selected = nm_ranges(owner, out / 'owner.nm.log')
    config = {'simulator': args.simulator, 'bundle': args.bundle, 'version': args.version,
              'ownerPath': str(owner), 'ownerBasename': owner.name, 'ownerSha256': sha(owner),
              'method': selected, 'ownerSymbols': rows, 'helperPath': str(helper),
              'helperSha256': sha(helper), 'helperMethods': methods(helper),
              'startedUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    (out / 'capture-config.json').write_text(json.dumps(config, indent=2)+'\n')
    (out / 'trusted_lldb.py').write_text(LLDB_HELPER, encoding='ascii')
    env = dict(os.environ)
    env.update({'SIMCTL_CHILD_RUNECLR_UPDATE_DIR': str(args.update_dir),
                'SIMCTL_CHILD_RUNECLR_EXPECTED_VERSION': args.version})
    stdout_log = out/'managed.stdout.log'
    stderr_log = out/'managed.stderr.log'
    stdout_log.touch()
    stderr_log.touch()
    run(['xcrun','simctl','launch','--wait-for-debugger','--stdout='+str(stdout_log),
         '--stderr='+str(stderr_log), args.simulator, args.bundle], out/'launch.log', env=env)
    match = re.search(r': (\d+)\s*$', (out/'launch.log').read_text())
    if not match: raise RuntimeError('simctl wait-for-debugger PID marker missing')
    pid = int(match.group(1)); (out/'pid.txt').write_text(str(pid)+'\n')
    console_log = out/'managed.console.log'
    console_handle = console_log.open('w', encoding='utf-8')
    log_proc = subprocess.Popen(
        ['xcrun', 'simctl', 'spawn', args.simulator, 'log', 'stream', '--level', 'debug', '--style', 'compact',
         '--predicate', 'process CONTAINS "TrustedUpdate"'],
        stdout=console_handle, stderr=subprocess.STDOUT)
    time.sleep(1)
    source = out/'capture.lldb'
    source.write_text('\n'.join(['breakpoint set -n coreclr_initialize','continue',
        'breakpoint disable 1','command script import "'+str(out/'trusted_lldb.py')+'"',
        'script trusted_lldb.setup()','continue','process status',
        'script trusted_lldb.finish()','quit'])+'\n', encoding='ascii')
    try:
        status = run(['xcrun','lldb','--batch','--attach-pid',str(pid),'--source',str(source)],
                     out/'lldb.log', check=False, timeout=args.timeout)
    finally:
        log_proc.terminate()
        try:
            log_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            log_proc.kill()
        console_handle.close()
    run(['xcrun','simctl','terminate',args.simulator,args.bundle], out/'terminate.log', check=False)
    stdout_path = out/'managed.stdout.log'
    stdout = stdout_path.read_text(errors='replace') if stdout_path.exists() else ''
    stderr_path = out/'managed.stderr.log'
    stderr = stderr_path.read_text(errors='replace') if stderr_path.exists() else ''
    console_path = out/'managed.console.log'
    console = console_path.read_text(errors='replace') if console_path.exists() else ''
    # iOS Console.WriteLine reaches unified logging. Debugger stdout and stderr
    # files can stay empty; log stream records that channel.
    if 'TRUSTED_UPDATE_SUCCESS' in stdout:
        managed_log = 'stdout'
    elif 'TRUSTED_UPDATE_SUCCESS' in stderr:
        managed_log = 'stderr'
    elif 'TRUSTED_UPDATE_SUCCESS' in console:
        managed_log = 'console'
    else:
        managed_log = None
    callback = [line for line in stdout.splitlines() if line.startswith('RUNECLR_NATIVE_CALLBACK ')]
    result = {'version':args.version,'pid':pid,'lldbExit':status,
              'managedSuccess':managed_log is not None,'managedSuccessLog':managed_log,'nativeCallbackLines':callback,
              'nativeEntry':(json.loads((out/'native-entry.json').read_text()) if (out/'native-entry.json').exists() else None),
              'interpreterEntries':(json.loads((out/'interpreter-entries.json').read_text()) if (out/'interpreter-entries.json').exists() else []),
              'stdoutSha256':sha(stdout_path) if stdout_path.exists() else None,'endedUtc':time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    (out/'results.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator', required=True); parser.add_argument('--bundle', required=True)
    parser.add_argument('--version', required=True); parser.add_argument('--owner', type=Path, required=True)
    parser.add_argument('--helper', type=Path, required=True); parser.add_argument('--update-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--timeout', type=int, default=600)
    args = parser.parse_args(); print(json.dumps(capture(args), indent=2)); return 0

if __name__ == '__main__': raise SystemExit(main())



