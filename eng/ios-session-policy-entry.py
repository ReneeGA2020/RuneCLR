#!/usr/bin/env python3
"""Prepare an independent iOS session-policy fixture and native entry capture.

Never builds a runtime, installs an app or starts a simulator. The operator
supplies matching Release source/native/DWARF and actual installed paths.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil


def helper(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


MOBILE_ADAPTER = '''// Mobile-only adapter generated from the unchanged desktop probe.
// The native bridge invokes SelectionProbe.Host's entry point with zero args.
if (args.Length == 0)
{
    string directory = Environment.GetEnvironmentVariable("RUNECLR_PROBE_DIRECTORY")
        ?? Path.Combine(AppContext.BaseDirectory, "plugin");
    string evidence = Environment.GetEnvironmentVariable("RUNECLR_PROBE_EVIDENCE")
        ?? Path.Combine(Path.GetTempPath(), "runeclr-session-selection");
    string lane = Environment.GetEnvironmentVariable("RUNECLR_PROBE_LANE") ?? "required";
    Environment.SetEnvironmentVariable("RUNECLR_PROBE_FACTORY",
        Environment.GetEnvironmentVariable("RUNECLR_PROBE_FACTORY") ?? "required");
    args = lane switch
    {
        "required" => [directory, evidence],
        "refusal" => [directory, evidence, "--refusal-required", Path.Combine(directory, "Refusal")],
        "boxed" => [directory, evidence, "--bridges", Path.Combine(directory, "Boxed")],
        _ => throw new ArgumentException("Unknown mobile session probe lane.")
    };
    Console.Error.WriteLine($"MOBILE SELECTION lane={lane} directory={directory} evidence={evidence}");
}

'''


def fixture(args):
    root = Path(__file__).resolve().parent.parent
    sources = Path(__file__).with_name('execution-selection-probe')
    out = args.output.resolve()
    out.mkdir(exist_ok=False, parents=True)
    original = {}
    for path in sorted(sources.rglob('*')):
        if path.is_file() and path.suffix in ('.cs', '.csproj') and not {'bin', 'obj'} & set(path.parts):
            relative = path.relative_to(sources)
            destination = out / relative
            destination.parent.mkdir(exist_ok=True, parents=True)
            shutil.copy2(path, destination)
            original[str(relative)] = sha(path)
    for name in ('Directory.Build.props', 'global.json'):
        shutil.copy2(root / name, out / name)
    program = out / 'Host/Program.cs'
    text = program.read_text()
    anchor = '// Keep managed result markers separate from buffered native dump stdout.'
    if text.count(anchor) != 1:
        raise ValueError('Desktop host mobile insertion anchor changed')
    program.write_text(text.replace(anchor, MOBILE_ADAPTER + anchor))
    write(out / 'fixture-source.json', {
        'preparedOnly': True, 'applicationExecuted': False,
        'originalSourceHashes': original, 'adaptedHostSha256': sha(program),
        'trustedCompositeInputs': ['SelectionProbe.Host.dll', 'SelectionProbe.Contract.dll'],
        'ilPayloadInputs': ['plugin/SelectionProbe.Payload.dll', 'plugin/SelectionProbe.Private.dll'],
        'optionalRefusal': 'plugin/Refusal/SelectionProbe.Refusal.dll',
        'entry': 'SelectionProbe.Host entry point invoked with zero args',
        'scope': 'trusted experimental fixture; unchanged business bodies; mobile argv adapter only',
        'ordinaryControl': 'Not a positive JIT lane on iOS; dynamic native compilation unavailable'
    })
    print('SOURCE PREPARED, no build or application execution: ' + str(out))


def inventory(payload):
    reader = helper('ios-r2r-release-verify')
    targets = {
        'SelectionProbe.Payload.dll': {
            'SelectionUGC.Payload.Entry..cctor', 'SelectionUGC.Payload.Entry..ctor',
            'SelectionUGC.Payload.Entry.Run'},
        'SelectionProbe.Private.dll': {
            'SelectionUGC.Private.PrivateState..cctor', 'SelectionUGC.Private.PrivateState..ctor',
            'SelectionUGC.Private.PrivateState.InlineAdd',
            'SelectionUGC.Private.PrivateGeneric' + chr(96) + '1.Identity'}
    }
    modules, required = {}, set()
    for filename, fixed in targets.items():
        path = payload / filename
        methods = reader.plugin_methods(path, required=(), qualified=True)
        # Bind generated delegate bodies from metadata, not a guessed ordinal.
        suffix = '.<Run>b__0' if filename.endswith('Payload.dll') else '.<MakeDelegate>b__0'
        callbacks = [name for name in methods if name.endswith(suffix)]
        if len(callbacks) != 1 or not fixed <= methods.keys():
            raise ValueError('Expected fixture body metadata absent/ambiguous: ' + filename)
        selected = fixed | set(callbacks)
        modules[filename] = {'relativePath': filename, 'sha256': sha(path),
                             'simpleName': filename[:-4], 'methods': methods}
        required.update(filename + ':' + name for name in selected)
    if len(required) != 9:
        raise ValueError('Expected nine fixed entry groups')
    return modules, sorted(required)


def render_lldb():
    original = helper('ios-release-package-entry-capture').LLDB_HELPER
    replacements = {
        "NAMES = {'Gameplay','GameplayFailure','PrivateA','PrivateB','SharedGameplay'}":
            "NAMES = {m['simpleName'] for m in CONFIG['modules'].values()}",
        "if names[0].rsplit('.',1)[-1] not in ('OnStart','OnTick','OnStop','Read','Next'): return False":
            "if CONFIG['modules'][path]['relativePath']+':'+names[0] not in CONFIG['requiredMethods']: return False"
    }
    for old, new in replacements.items():
        if original.count(old) != 1:
            raise ValueError('Reviewed LLDB helper anchor changed: ' + old)
        original = original.replace(old, new)
    return original.replace('package_lldb.', 'session_lldb.').replace('PACKAGE_INTERPRETER_ENTRY', 'SESSION_POLICY_INTERPRETER_ENTRY')


def prepare(args):
    out = args.output.resolve()
    out.mkdir(exist_ok=False, parents=True)
    native, runtime, payload = args.native.resolve(), args.runtime.resolve(), args.payload.resolve()
    app, installed = args.app.resolve(), args.installed_payload.resolve()
    if not args.installed_payload.is_absolute():
        raise ValueError('Installed payload path must be the actual absolute Module path')
    dwarf = native.with_name(native.name + '.dwarf')
    if not dwarf.is_file():
        raise ValueError('Matching native .dwarf sibling required')
    source = runtime / 'src/coreclr/vm/interpexec.cpp'
    lines = source.read_text().splitlines()
    calls = [i for i, line in enumerate(lines) if '// Set execution state for the new frame' in line
             and 'pMethod = pFrame->startIp->Method;' in lines[i+1]
             and 'if (stack + pMethod->allocaSize' in '\n'.join(lines[i:i+10])]
    if len(calls) != 1:
        raise ValueError('Matching first-opcode source anchor unknown')
    dispatch = [i+1 for i in range(calls[0], calls[0]+20) if 'INTOP_NEXT;' in lines[i]]
    if len(dispatch) != 1:
        raise ValueError('Matching first-opcode dispatch line ambiguous')
    modules, required = inventory(payload)
    for filename, module in modules.items():
        if sha(installed / filename) != module['sha256']:
            raise ValueError('Installed IL payload mismatch: ' + filename)
    mobile = helper('verify-ios-packages')
    native_sections = mobile.macho_sections(native)
    if native_sections != mobile.macho_sections(app / 'libcoreclr.dylib'):
        raise ValueError('Installed app native code/data mismatch')
    layouts = {filename: mobile.il_layout(payload / filename) for filename in modules}
    if any(not item['ilOnly'] or item['managedNativeRva'] for item in layouts.values()):
        raise ValueError('Fixture must be plain IL, not submitted R2R or native payload')
    config = {'modules': {str(installed / name): value for name, value in modules.items()},
              'requiredMethods': required, 'source': str(source), 'dispatchLine': dispatch[0]}
    write(out / 'capture-config.json', config)
    (out / 'session_lldb.py').write_text(render_lldb())
    common = helper('ios-r2r-fix-verify')
    if common.capture(['git', '-C', runtime, 'status', '--porcelain', '--untracked-files=no']):
        raise ValueError('Matching runtime source must be tracked-clean')
    symbols = common.capture(['xcrun', 'dwarfdump', '--uuid', dwarf])
    dwarf_uuids = re.findall(r'UUID: ([0-9A-Fa-f-]+)', symbols)
    if len(dwarf_uuids) != 1 or dwarf_uuids[0].replace('-', '').lower() != native_sections['uuid'].lower():
        raise ValueError('Native/DWARF UUID mismatch')
    write(out / 'identity.json', {'preparedOnly': True, 'entryVerified': False,
          'app': str(app), 'bundleFiles': mobile.tree(app), 'payload': str(payload),
          'installedPayload': str(installed), 'native': str(native), 'dwarf': str(dwarf), 'source': str(source),
          'runtimeCommit': common.capture(['git', '-C', runtime, 'rev-parse', 'HEAD']),
          'nativeSha256': sha(native), 'dwarfSha256': sha(dwarf), 'sourceSha256': sha(source),
          'nativeSections': native_sections, 'dwarfUuid': dwarf_uuids[0], 'sourceTrackedClean': True,
          'driverSha256': sha(__file__), 'moduleLayouts': layouts, 'configSha256': sha(out / 'capture-config.json'),
          'scope': 'nine entry groups sampled; not complete invocation capture, not mobile-device evidence'})
    commands = ['breakpoint set -n coreclr_initialize', 'continue', 'breakpoint disable 1',
                'target symbols add ' + str(dwarf), 'command script import ' + str(out / 'session_lldb.py'),
                'script session_lldb.setup()', 'continue', 'process status',
                'script session_lldb.finish()', 'quit']
    (out / 'capture.lldb').write_text('\n'.join(commands) + '\n')
    print('CAPTURE PREPARED, no simulator launch or debugger attach: ' + str(out))


def assess(args):
    out = args.output.resolve()
    assessment = out / 'entry-assessment.json'
    if assessment.exists():
        raise ValueError('Preserve prior assessment; do not overwrite')
    config = json.loads((out / 'capture-config.json').read_text())
    identity = json.loads((out / 'identity.json').read_text())
    entries = json.loads((out / 'interpreter-entries.json').read_text())
    if (out / 'capture-errors.json').exists():
        raise ValueError('Capture read errors retained; this capture cannot pass')
    if sha(out / 'capture-config.json') != identity['configSha256']:
        raise ValueError('Prepared module/target map changed')
    mobile = helper('verify-ios-packages')
    if mobile.tree(Path(identity['app'])) != identity['bundleFiles']:
        raise ValueError('Installed app changed during capture')
    for key in ('native', 'dwarf', 'source'):
        if sha(identity[key]) != identity[key + 'Sha256']:
            raise ValueError('Pinned matching capture input changed: ' + key)
    for path, module in config['modules'].items():
        if sha(path) != module['sha256'] or sha(Path(identity['payload']) / module['relativePath']) != module['sha256']:
            raise ValueError('Pinned producer/installed payload changed: ' + path)
    counts = dict.fromkeys(config['requiredMethods'], 0)
    for entry in entries:
        module = config['modules'].get(entry['modulePath'])
        if module is None or entry['nativeModule'] != 'libcoreclr.dylib' or not entry['collectible']:
            raise ValueError('Entry native/collectible module identity mismatch')
        name = entry['metadataMethodName']
        if (module['methods'].get(name) != entry['methodDefToken'] or module['sha256'] != entry['fileSha256']
                or module['relativePath'] != entry['relativePath'] or module['simpleName'] != entry['moduleSimpleName']
                or entry['kind'] not in ('stub', 'child') or entry['bytecodeStart'] != entry['methodDescBytecodeStart']
                or entry['bytecodeSizeSlots'] <= 0 or not entry['bytecodePrefixHex']
                or entry['firstOpcodeAddress'] != entry['bytecodeStart'] + 8):
            raise ValueError('Live MethodDesc/bytecode/PE metadata identity mismatch')
        key = entry['relativePath'] + ':' + name
        if key in counts:
            counts[key] += 1
    if not counts or not all(counts.values()):
        raise ValueError('Missing required execution samples: ' + str(counts))
    streams = {}
    for name in ('managed.stderr.log', 'managed.stdout.log'):
        path = out / name
        if path.exists():
            streams[name] = path.read_text(errors='replace').splitlines()
    unified = out / 'managed.unified.log'
    if unified.exists():
        if args.app_pid is None:
            raise ValueError('Unified messages require actual captured --app-pid')
        streams['managed.unified.log'] = [event.get('eventMessage', '') for event in
            helper('ios-release-package-entry-capture').unified_events(unified, args.app_pid)]
    complete = '20/20 execution-selection sessions passed; 20/20 contexts collected'
    choices = [(name, messages) for name, messages in streams.items() if complete in messages]
    if not choices:
        raise ValueError('Missing independent 20-session functional completion')
    marker_source, messages = choices[0]
    text = '\n'.join(messages)
    query = re.findall(r'^POLICY context=.* phase=(\S+) value=([01]) collectible=true$', text, re.M)
    expected_retired = 21 if args.refusal else 20
    phases = Counter(phase for phase, value in query)
    expected_phases = {'before-load': expected_retired, 'before-explicit-load': 40 + int(args.refusal),
                       'after-explicit-load': 40 + int(args.refusal), 'before-run': 20,
                       'resolver-after-private': 20, 'after-run': 20, 'before-unload': expected_retired}
    # Core phases are deterministic fixture operations. Framework resolver
    # requests can vary by the mobile composite; every observed value must 1.
    if ('POLICY API version=1 factory=required default=0 immutable-api=true' not in messages
            or len(re.findall(r'^PASS session=\d+ .*collected=true$', text, re.M)) != 20
            or len(re.findall(r'^LATE private=absent policy=1$', text, re.M)) != 20
            or len(re.findall(r'^LATE private=loaded policy=1$', text, re.M)) != 20
            or len(re.findall(r'^RETIRED query=System.InvalidOperationException protected=true$', text, re.M)) != expected_retired
            or any(phases[phase] != count for phase, count in expected_phases.items())
            or phases['resolver-before'] < 40 or any(value != '1' for phase, value in query)):
        raise ValueError('Required creation/load/late-dependency/retirement acknowledgement incomplete')
    if args.refusal:
        all_text = '\n'.join('\n'.join(messages) for messages in streams.values())
        if ('PASS required-refusal exception=System.NotSupportedException collected=true' not in text
                or 'RuneCLRInterpreterRefusal: SelectionUGC.Refusal.Entry:Reject CORJIT_SKIPPED' not in all_text):
            raise ValueError('Real interpreter refusal and recovery evidence incomplete')
    lldb = (out / 'lldb.log').read_text(errors='replace')
    if not re.search(r'exited with status = 0', lldb):
        raise ValueError('Captured process did not exit normally')
    result = {'passed': True, 'appRerun': False, 'functionalSessions': 20, 'contextsCollected': 20,
              'policyVersion': 1, 'defaultPolicy': 0, 'requiredPolicyQueryCount': len(query), 'policyPhaseCounts': dict(phases),
              'retiredQueryGuards': expected_retired, 'markerSource': marker_source,
              'requiredMethodEntryCounts': counts, 'validEntrySamples': len(entries),
              'entryKinds': {kind: sum(entry['kind'] == kind for entry in entries) for kind in ('stub', 'child')},
              'runtimeCommit': identity['runtimeCommit'], 'refusalVerified': args.refusal,
              'scope': 'Release execution entry samples plus independent session values/collection; not complete invocation or device proof',
              'rawHashes': {name: sha(out / name) for name in ('identity.json', 'capture-config.json', 'interpreter-entries.json', 'lldb.log')}}
    write(assessment, result)
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    source = sub.add_parser('fixture', help='Copy independent fixture sources and add mobile zero-argv adapter')
    source.add_argument('--output', type=Path, required=True)
    source.set_defaults(action=fixture)
    mapping = sub.add_parser('inventory', help='Read plain PE metadata without loading author code')
    mapping.add_argument('--payload', type=Path, required=True)
    mapping.set_defaults(action=lambda args: print(json.dumps(dict(zip(('modules', 'requiredMethods'), inventory(args.payload))), indent=2)))
    capture = sub.add_parser('prepare', help='Bind matching installed inputs and write an LLDB command/helper')
    for name in ('native', 'runtime', 'app', 'payload', 'installed-payload', 'output'):
        capture.add_argument('--' + name, type=Path, required=True)
    capture.set_defaults(action=prepare)
    audit = sub.add_parser('assess', help='Read captured Release entries and independent session markers without rerunning')
    audit.add_argument('--output', type=Path, required=True)
    audit.add_argument('--app-pid', type=int)
    audit.add_argument('--refusal', action='store_true')
    audit.set_defaults(action=assess)
    args = parser.parse_args()
    args.action(args)


if __name__ == '__main__':
    main()
