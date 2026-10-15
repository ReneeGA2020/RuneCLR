#!/usr/bin/env python3
"""Verify Release native compatibility and sample interpreter entry on iOS simulator.

Preserved managed/framework Debug inputs make this a native replacement lane,
not validation of complete Release framework packs.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import tarfile


def helper(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'),
                                                Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def plugin_methods(path, required=('Start', 'Tick', 'Stop'), qualified=False):
    # Read ECMA-335 tables preceding MethodDef without loading author code.
    data = path.read_bytes()
    u16 = lambda at: struct.unpack_from('<H', data, at)[0]
    u32 = lambda at: struct.unpack_from('<I', data, at)[0]
    pe = u32(0x3c)
    optional = pe + 24
    directories = optional + (112 if u16(optional) == 0x20b else 96)
    section_start = optional + u16(pe + 20)
    sections = [section_start + 40 * i for i in range(u16(pe + 6))]

    def offset(rva):
        for section in sections:
            start = u32(section + 12)
            if start <= rva < start + max(u32(section + 8), u32(section + 16)):
                return u32(section + 20) + rva - start
        raise ValueError('RVA is outside PE sections')

    clr = offset(u32(directories + 14 * 8))
    metadata = offset(u32(clr + 8))
    if data[metadata:metadata + 4] != b'BSJB':
        raise ValueError('Missing managed metadata')
    at = metadata + 16 + ((u32(metadata + 12) + 3) & ~3)
    count = u16(at + 2)
    at += 4
    streams = {}
    for _ in range(count):
        end = data.index(b'\0', at + 8)
        name = data[at + 8:end].decode('ascii')
        streams[name] = metadata + u32(at)
        at = (end + 4) & ~3
    tables = streams.get('#~', streams.get('#-'))
    heap_flags = data[tables + 6]
    valid = struct.unpack_from('<Q', data, tables + 8)[0]
    at = tables + 24
    rows = {}
    for table in range(64):
        if valid & (1 << table):
            rows[table] = u32(at)
            at += 4
    index = lambda table: 4 if rows.get(table, 0) >= 65536 else 2
    coded = lambda bits, choices: 4 if max(rows.get(t, 0) for t in choices) >= (1 << (16 - bits)) else 2
    string_size = 4 if heap_flags & 1 else 2
    guid_size = 4 if heap_flags & 2 else 2
    blob_size = 4 if heap_flags & 4 else 2
    sizes = [2 + string_size + 3 * guid_size,
             coded(2, [0, 26, 35, 1]) + 2 * string_size,
             4 + 2 * string_size + coded(2, [2, 1, 27]) + index(4) + index(6),
             index(4), 2 + string_size + blob_size, index(6)]
    starts = {}
    for table, size in enumerate(sizes):
        starts[table] = at
        at += rows.get(table, 0) * size
    def heap_string(offset):
        start = streams['#Strings'] + offset
        return data[start:data.index(b'\0', start)].decode('utf-8')
    types = []
    for row in range(rows.get(2, 0)):
        type_at = starts[2] + row * sizes[2]
        name = heap_string((u32 if string_size == 4 else u16)(type_at + 4))
        namespace = heap_string((u32 if string_size == 4 else u16)(type_at + 4 + string_size))
        first_method = (u32 if index(6) == 4 else u16)(type_at + sizes[2] - index(6))
        types.append((namespace + '.' + name if namespace else name, first_method))
    methods = {}
    size = 8 + string_size + blob_size + index(8)
    for row in range(rows.get(6, 0)):
        name_offset = (u32 if string_size == 4 else u16)(at + row * size + 8)
        start = streams['#Strings'] + name_offset
        name = data[start:data.index(b'\0', start)].decode('utf-8')
        if qualified:
            owners = [owner for i, (owner, first_method) in enumerate(types)
                      if first_method <= row + 1 < (types[i + 1][1] if i + 1 < len(types) else rows.get(6, 0) + 1)]
            if len(owners) != 1:
                raise ValueError('MethodDef owner is absent or ambiguous')
            name = owners[0] + '.' + name
            if name in methods:
                raise ValueError('Qualified method name is overloaded; explicit signature matching required')
        methods[name] = 0x06000001 + row
    if not set(required) <= methods.keys():
        raise ValueError('Unexpected probe metadata')
    return methods


LLDB_HELPER = '''import json
from pathlib import Path
import lldb
OUT = Path(__file__).parent
RECEIVER_MT = 0
ENTRIES = []

def word(process, address):
    error = lldb.SBError()
    value = process.ReadUnsignedFromMemory(address, 8, error)
    if not error.Success(): raise RuntimeError(str(error))
    return value

def typed(target, address, name):
    kind = target.FindFirstType(name)
    if not kind.IsValid(): raise RuntimeError('Missing DWARF type: ' + name)
    return target.CreateValueFromAddress(name, lldb.SBAddress(address, target), kind)

def field(value, name):
    child = value.GetChildMemberWithName(name)
    if not child.IsValid() or child.GetError().Fail(): raise RuntimeError('Missing field: ' + name)
    return child.GetValueAsUnsigned()

def dispatch(frame, location, internal):
    global RECEIVER_MT
    process = frame.GetThread().GetProcess()
    target = process.GetTarget()
    cell = frame.FindRegister('x11').GetValueAsUnsigned()
    if target.ResolveLoadAddress(cell).GetModule().GetFileSpec().GetFilename() == 'probe.dylib':
        receiver = frame.FindRegister('x0').GetValueAsUnsigned()
        RECEIVER_MT = word(process, receiver)
    return False

def entered(frame, location, internal):
    try:
        process = frame.GetThread().GetProcess()
        target = process.GetTarget()
        receiver = frame.FindRegister('x0').GetValueAsUnsigned()
        if not RECEIVER_MT: return False
        error = lldb.SBError()
        actual_mt = process.ReadUnsignedFromMemory(receiver, 8, error)
        if not error.Success() or actual_mt != RECEIVER_MT: return False
        ip = frame.FindRegister('x12').GetValueAsUnsigned()
        method = word(process, ip)
        interp = typed(target, method, 'InterpMethod')
        desc_address = field(interp, 'methodHnd')
        desc = typed(target, desc_address, 'MethodDesc')
        chunk_type = target.FindFirstType('MethodDescChunk')
        chunk_address = desc_address - chunk_type.GetByteSize() - field(desc, 'm_chunkIndex') * 8
        chunk = typed(target, chunk_address, 'MethodDescChunk')
        token = 0x06000000 | ((field(chunk, 'm_flagsAndTokenRange') & 0xfff) << 12) | (field(desc, 'm_wFlags3AndTokenRemainder') & 0xfff)
        error = lldb.SBError()
        code = process.ReadMemory(ip + 8, min(field(interp, 'codeSize') * 4, 64), error)
        entry = {'pc': frame.GetPC(), 'function': frame.GetFunctionName(),
                 'module': frame.GetModule().GetFileSpec().GetFilename(),
                 'receiver': receiver, 'receiverMethodTable': word(process, receiver),
                 'methodTable': field(chunk, 'm_methodTable'), 'methodDesc': desc_address,
                 'methodDefToken': token, 'bytecodeStart': ip, 'interpMethod': method,
                 'methodDescBytecodeStart': field(desc, 'm_interpreterCode'),
                 'bytecodeSizeSlots': field(interp, 'codeSize'), 'bytecodePrefixHex': code.hex(),
                 'readSuccess': error.Success()}
        ENTRIES.append(entry)
        (OUT / 'interpreter-entries.json').write_text(json.dumps(ENTRIES, indent=2) + chr(10))
        print('RELEASE_INTERPRETER_ENTRY ' + json.dumps(entry), flush=True)
    except Exception as error:
        (OUT / 'capture-error.json').write_text(json.dumps({'error': str(error)}) + chr(10))
    return False

def setup():
    target = lldb.debugger.GetSelectedTarget()
    symbols = target.FindSymbols('InterpreterStub')
    matches = [symbols.GetContextAtIndex(i).GetSymbol().GetStartAddress()
               for i in range(symbols.GetSize())
               if symbols.GetContextAtIndex(i).GetModule().GetFileSpec().GetFilename() == 'libcoreclr.dylib']
    if len(matches) != 1: raise RuntimeError('InterpreterStub entry is ambiguous or absent')
    bp = target.BreakpointCreateByAddress(matches[0].GetLoadAddress(target))
    bp.SetScriptCallbackFunction('release_lldb.entered')
    dispatch_bps = [target.BreakpointCreateByName(name, 'libcoreclr.dylib') for name in
                    ('RhpInitialInterfaceDispatch', 'RhpInterfaceDispatch1')]
    for dispatch_bp in dispatch_bps:
        dispatch_bp.SetScriptCallbackFunction('release_lldb.dispatch')
    (OUT / 'breakpoints.json').write_text(json.dumps({'interpreterAddress': matches[0].GetLoadAddress(target),
        'interpreterLocations': bp.GetNumLocations(), 'dispatchLocations': [b.GetNumLocations() for b in dispatch_bps]}) + chr(10))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'candidate', 'minimal', 'controlled', 'packages', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--capture-only', action='store_true', help='Preserve completed functional runs and retry only debugger evidence')
    parser.add_argument('--capture-name', default='capture')
    args = parser.parse_args()
    if not re.fullmatch(r'capture(?:-[a-z0-9]+)*', args.capture_name):
        raise ValueError('Capture name must be a single safe directory name')
    common = helper('ios-r2r-fix-verify')
    mobile = helper('verify-ios-packages')
    minimal = helper('ios-r2r-minimal')
    out = args.output.resolve()
    if not args.capture_only:
        out.mkdir(exist_ok=False)
    source = json.loads((args.candidate / 'logs/source.json').read_text())
    artifact = json.loads((args.candidate / 'logs/artifacts.json').read_text())
    native = Path(artifact['libcoreclr'])
    runtime = args.candidate / 'runtime'
    if (source['base'] != common.BASE or source['configuration'] != 'iossimulator.arm64.Release'
            or source['commit'] != common.capture(['git', '-C', runtime, 'rev-parse', 'HEAD'])
            or common.capture(['git', '-C', runtime, 'status', '--porcelain', '--untracked-files=no'])
            or common.sha(native) != artifact['libcoreclrSha256']):
        raise RuntimeError('Release source/native identity check failed')
    layouts = {}
    originals = {'full': args.root / 'preview6-experiment/pinned-debug-harness/app/RuneCLRPinnedHarness.app',
                 'minimal': args.minimal / 'r2r/Probe.app', 'controlled': args.controlled / 'app/Packages.app'}
    if args.capture_only:
        identity = json.loads((out / 'identity.json').read_text())
        if identity['source'] != source or identity['artifact'] != artifact:
            raise RuntimeError('Retry must retain original source/native identities')
        layouts = identity['apps']
        for layout in layouts.values():
            if common.sha(Path(layout['app']) / 'libcoreclr.dylib') != layout['signedNativeSha256']:
                raise RuntimeError('Prepared native input changed before retry')
    else:
        for kind, original in originals.items():
            directory = out / kind
            directory.mkdir()
            layouts[kind] = common.copy_app(original, directory / original.name, native, directory, mobile.macho_sections)
        common.write(out / 'identity.json', {'scope': 'Release native with preserved same-base Debug managed/framework inputs',
                     'source': source, 'artifact': artifact, 'apps': layouts})
    results = json.loads((out / 'functional-results.json').read_text()) if args.capture_only else {}
    if args.capture_only and (set(results) != {'full', 'minimal', 'controlled'} or not all(r['passed'] for r in results.values())):
        raise RuntimeError('Capture-only retry requires three completed passing functional runs')
    sim = common.capture(['xcrun', 'simctl', 'create', 'RuneCLR-CID-Release-Native',
                         'com.apple.CoreSimulator.SimDeviceType.iPhone-17', 'com.apple.CoreSimulator.SimRuntime.iOS-27-0'])
    simulator_receipt = out / (args.capture_name + '-simulator.json' if args.capture_only else 'simulator.json')
    common.write(simulator_receipt, {'uuid': sim})
    try:
        prefix = args.capture_name + '-' if args.capture_only else ''
        common.logged(['xcrun', 'simctl', 'boot', sim], out / (prefix + 'boot-command.log'))
        common.logged(['xcrun', 'simctl', 'bootstatus', sim, '-b'], out / (prefix + 'boot.log'))
        cases = [] if args.capture_only else [('full', {}), ('minimal', {'PROBE_MODE': 'collect', 'PROBE_CYCLES': '20', 'PROBE_TICKS': '3'}), ('controlled', {})]
        for kind, settings in cases:
            app = Path(layouts[kind]['app'])
            bundle = layouts[kind]['bundle']
            common.logged(['xcrun', 'simctl', 'install', sim, app], out / (kind + '-install.log'))
            installed = Path(common.capture(['xcrun', 'simctl', 'get_app_container', sim, bundle, 'app']))
            if mobile.tree(installed) != mobile.tree(app):
                raise RuntimeError('Installed app differs')
            if kind == 'controlled':
                data = Path(common.capture(['xcrun', 'simctl', 'get_app_container', sim, bundle, 'data']))
                payload = data / 'Documents/controlled'
                shutil.copytree(args.packages, payload)
                if mobile.tree(payload) != mobile.tree(args.packages):
                    raise RuntimeError('Controlled fixtures differ')
            env = {k: v for k, v in os.environ.items() if not k.startswith(('SIMCTL_CHILD_DOTNET_', 'SIMCTL_CHILD_COMPlus_', 'SIMCTL_CHILD_PROBE_'))}
            env.update({'SIMCTL_CHILD_' + k: v for k, v in settings.items()})
            log = out / (kind + '.log')
            status = common.logged(['xcrun', 'simctl', 'launch', '--console', sim, bundle], log, env=env, check=False, timeout=240)
            text = log.read_text(errors='replace')
            passed = status == 0 and 'RUNECLR_EXIT=0' in text and '.NET 12.0.0-dev' in text and 'Assert failure' not in text and 'Got a SIGSEGV' not in text
            if kind == 'minimal':
                details = minimal.result(log, 20, 3, 'collect', 'none', status)
                passed = passed and details['passed'] and 'compiled=False' in text
            else:
                details = {'expectedTests': 21 if kind == 'full' else 15}
                expected = '21/21 tests passed' if kind == 'full' else '15/15 package execution tests passed'
                passed = passed and expected in text and 'DynamicCodeCompiled=False' in text
            results[kind] = {'passed': bool(passed and mobile.tree(installed) == mobile.tree(app)), 'launcherExit': status, 'details': details, 'logSha256': common.sha(log)}
            common.write(out / 'functional-results.json', results)
            print(kind + ': ' + json.dumps(results[kind]), flush=True)
            common.logged(['xcrun', 'simctl', 'terminate', sim, bundle], out / (kind + '-terminate.log'), check=False)

        work = out / args.capture_name
        work.mkdir()
        (work / 'release_lldb.py').write_text(LLDB_HELPER)
        shutil.copy2(Path(__file__), work / 'driver.py')
        bundle = layouts['minimal']['bundle']
        if args.capture_only:
            common.logged(['xcrun', 'simctl', 'install', sim, layouts['minimal']['app']], work / 'install.log')
            env = {k: v for k, v in os.environ.items() if not k.startswith(('SIMCTL_CHILD_DOTNET_', 'SIMCTL_CHILD_COMPlus_', 'SIMCTL_CHILD_PROBE_'))}
        env.update({'SIMCTL_CHILD_PROBE_MODE': 'collect', 'SIMCTL_CHILD_PROBE_CYCLES': '2', 'SIMCTL_CHILD_PROBE_TICKS': '3'})
        common.logged(['xcrun', 'simctl', 'launch', '--wait-for-debugger', '--stdout=' + str(work / 'managed.stdout.log'),
                       '--stderr=' + str(work / 'managed.stderr.log'), sim, bundle], work / 'launch.log', env=env)
        pid = re.search(r': (\d+)', (work / 'launch.log').read_text()).group(1)
        script = work / 'capture.lldb'
        dwarf = native.with_name(native.name + '.dwarf')
        script.write_text('\n'.join(['breakpoint set -n coreclr_initialize', 'continue', 'breakpoint disable 1',
            'target symbols add ' + str(dwarf), 'command script import ' + str(work / 'release_lldb.py'),
            'script release_lldb.setup()', 'continue', 'process status', 'quit']) + '\n')
        status = common.logged(['xcrun', 'lldb', '--batch', '--attach-pid', pid, '--source', script], work / 'lldb.log', timeout=240, check=False)
        entries = json.loads((work / 'interpreter-entries.json').read_text()) if (work / 'interpreter-entries.json').exists() else []
        methods = plugin_methods(Path(layouts['minimal']['app']) / 'plugin/ProbePlugin.dll')
        valid = [e for e in entries if e['module'] == 'libcoreclr.dylib' and e['receiverMethodTable'] == e['methodTable']
                 and e['bytecodeStart'] == e['methodDescBytecodeStart'] and e['bytecodeSizeSlots'] > 0 and e['bytecodePrefixHex'] and e['readSuccess']]
        observed = {e['methodDefToken'] for e in valid}
        stdout = work / 'managed.stdout.log'
        debugger_log = (work / 'lldb.log').read_text(errors='replace')
        exited = bool(re.search(r'exited with status = 0', debugger_log))
        counts = {name: sum(e['methodDefToken'] == methods[name] for e in valid) for name in ('Start', 'Tick', 'Stop')}
        completed = 'CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0' in stdout.read_text(errors='replace')
        expected_counts = {'Start': 2, 'Tick': 6, 'Stop': 2}
        proof = (status == 0 and not (work / 'capture-error.json').exists() and all(methods[n] in observed for n in ('Start', 'Tick', 'Stop'))
                 and exited and completed and all(0 < counts[n] <= expected_counts[n] for n in counts))
        common.write(work / 'proof.json', {'passed': bool(proof), 'lldbExit': status, 'metadataMethods': methods,
                     'validEntries': len(valid), 'observedMethodTokens': sorted(observed), 'methodEntryCounts': counts,
                     'expectedInvocationCounts': expected_counts, 'completeInvocationCapture': counts == expected_counts,
                     'managedExitZero': completed, 'scope': 'ProbePlugin Start/Tick/Stop entry into native InterpreterStub'})
        results['interpreterProof'] = {'passed': bool(proof)}
        print('interpreterProof: ' + json.dumps(results['interpreterProof']), flush=True)
    finally:
        common.logged(['xcrun', 'simctl', 'terminate', sim, layouts['minimal']['bundle']], out / (prefix + 'capture-terminate.log'), check=False)
        shutdown = common.logged(['xcrun', 'simctl', 'shutdown', sim], out / (prefix + 'shutdown.log'), check=False)
        common.write(simulator_receipt, {'uuid': sim, 'shutdownExit': shutdown})
    success = len(results) == 4 and all(r['passed'] for r in results.values()) and shutdown == 0
    result_name = args.capture_name + '-results.json' if args.capture_only else 'results.json'
    common.write(out / result_name, {'success': success, 'runs': results})
    archive_name = 'evidence-' + args.capture_name + '.tar.gz' if args.capture_only else 'evidence.tar.gz'
    with tarfile.open(out / archive_name, 'w:gz') as archive:
        for path in sorted(out.rglob('*')):
            if path.is_file() and path.suffix in ('.json', '.log', '.lldb', '.py'):
                archive.add(path, arcname=str(path.relative_to(out)))
        for path in (Path(__file__), Path(__file__).with_name('ios-r2r-fix-verify.py'), args.candidate / 'logs/runtime.patch'):
            archive.add(path, arcname=path.name)
    print('Release compatibility archive SHA256=' + common.sha(out / archive_name), flush=True)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
