#!/usr/bin/env python3
"""Build and accept a fresh matching iOS session-policy player; runtime builds are external."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import subprocess
import tarfile
import uuid

BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
PLAYER = ('RuneCLR.Runtime.dll', 'RuneCLR.Packages.dll', 'RuneCLR.Abstractions.dll', 'RuneCLR.PackageExecution.Tests.dll')
TRUSTED = ('RuneCLR.PackageExecution.Tests.dll', 'RuneCLR.Runtime.Tests.dll', 'RuneCLR.SampleHost.dll')
BRIDGE = r'''using System;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
public static class SessionBridge
{
    public static int Main(string[] args)
    {
        var phase = args.Length == 0 ? "packages" : args[0];
        var docs = Environment.GetEnvironmentVariable("RUNECLR_DOCUMENTS")!;
        Console.WriteLine($"SESSION_PHASE={phase}; Runtime={RuntimeInformation.FrameworkDescription}; DynamicCodeCompiled={RuntimeFeature.IsDynamicCodeCompiled}");
        try
        {
            switch (phase)
            {
                case "packages":
                    var packages = Path.Combine(docs, "controlled");
                    if (!Directory.Exists(packages)) { Console.WriteLine("PACKAGE_WAITING_FOR_POSTINSTALL_IL"); return 0; }
                    return RuneCLR.PackageExecution.Tests.PackageExecutionHarness.Run(new[] { "--packages", packages, "--require-interpreter" });
                case "lifecycle":
                    var late = Path.Combine(docs, "late", "map.json");
                    if (!File.Exists(late)) throw new FileNotFoundException("Postinstall late IL is required for current 24-case acceptance.", late);
                    return Invoke("RuneCLR.Runtime.Tests", new[] { "--late-map", late, "--require-interpreter" });
                case "sample":
                    return Invoke("RuneCLR.SampleHost", new[] { "--collect", "--require-interpreter" });
                case "selection":
                    return Invoke("SelectionProbe.Host", Array.Empty<string>());
                default: throw new ArgumentException("Unknown session acceptance phase: " + phase);
            }
        }
        catch (Exception error) { Console.WriteLine(error); return 3; }
    }
    private static int Invoke(string name, string[] args)
    {
        // These are fixed trusted harness identities included in the rebuilt composite.
        var entry = Assembly.Load(name).EntryPoint ?? throw new InvalidOperationException("Trusted harness entry missing.");
        return (int)entry.Invoke(null, new object[] { args })!;
    }
    // Compile an int-instantiated native seed body without executing or loading
    // the default dependency before the harness's final collision test.
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static string NativeSeedInstantiation(int value) => RuneCLR.PrivateDependency.PrivateState<int>.Start(value);
}
'''


def helper(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def utc():
    return datetime.now(timezone.utc).isoformat()


def inventories(args, mobile):
    roots = {'player': args.player, 'lifecycle': args.lifecycle, 'sample': args.sample}
    files = {}
    for lane, root in roots.items():
        if root is None: raise ValueError('Missing --' + lane)
        required = PLAYER if lane == 'player' else PLAYER[:3] + (('RuneCLR.Runtime.Tests.dll',) if lane == 'lifecycle' else ('RuneCLR.SampleHost.dll',))
        for name in required:
            files[lane + '/' + name] = mobile.sha(root / name)
        folders = ('fixtures', 'dependency-a', 'dependency-b') if lane == 'lifecycle' else ('maps',) if lane == 'sample' else ()
        for folder in folders:
            selected = [p for p in sorted((root / folder).rglob('*')) if p.is_file() and (p.suffix == '.dll' or p.name == 'map.json')]
            if not selected: raise ValueError('Missing fixture directory: ' + str(root / folder))
            for path in selected: files[lane + '/' + path.relative_to(root).as_posix()] = mobile.sha(path)
    if args.selection_dir:
        roots['selection'] = args.selection_dir
        for name in ('trusted/SelectionProbe.Host.dll', 'trusted/SelectionProbe.Contract.dll'):
            files['selection/' + name] = mobile.sha(args.selection_dir / name)
        for path in sorted((args.selection_dir / 'plugin').rglob('*.dll')):
            files['selection/' + path.relative_to(args.selection_dir).as_posix()] = mobile.sha(path)
        if 'selection/plugin/SelectionProbe.Payload.dll' not in files or 'selection/plugin/SelectionProbe.Private.dll' not in files:
            raise ValueError('Missing explicit selection plugin IL')
    for name in PLAYER[:3]:
        if len({files[lane + '/' + name] for lane in ('player', 'lifecycle', 'sample')}) != 1:
            raise ValueError('Current harnesses have different shared host bytes: ' + name)
    return roots, files


def snapshot(args, mobile):
    roots, files = inventories(args, mobile)
    if args.host_receipt.exists(): raise ValueError('Preserve existing host snapshot')
    write(args.host_receipt, {'schema': 'runeclr.ios-session-policy.host-inputs.v1', 'createdUtc': utc(),
        'files': files, 'rootsAtSnapshot': {key: str(path.resolve()) for key, path in roots.items()},
        'driverSha256': mobile.sha(__file__), 'claim': 'Exact current prebuilt host and fixture inputs; no managed rebuild'})
    print(json.dumps({'hostReceipt': str(args.host_receipt), 'sha256': mobile.sha(args.host_receipt), 'files': len(files)}))


def matching(args, common, mobile):
    result = json.loads(args.build_receipt.read_text())
    if not result.get('success'): raise ValueError('Matching runtime build did not pass')
    head = common.capture(['git', '-C', args.runtime, 'rev-parse', 'HEAD'])
    tree = common.capture(['git', '-C', args.runtime, 'rev-parse', 'HEAD^{tree}'])
    if result.get('base') != BASE or result.get('commit') != head or result.get('tree') != tree:
        raise ValueError('Matching runtime source base/commit/tree mismatch')
    if common.capture(['git', '-C', args.runtime, 'status', '--porcelain', '--untracked-files=no']):
        raise ValueError('Matching runtime tracked source is dirty')
    if result.get('target') not in ('iossimulator', 'iossimulator.arm64', 'iossimulator.arm64.Release') or result.get('configuration') not in ('Release', 'iossimulator.arm64.Release'):
        raise ValueError('Matching inputs must be iossimulator arm64 Release')
    if int.from_bytes(args.native.read_bytes()[4:8], 'little') != 0x0100000c:
        raise ValueError('Matching native CPU must be arm64')
    for path, key in ((args.native, 'nativeSha256'), (args.corelib, 'corelibSha256'), (args.compiler, 'crossgen2Sha256')):
        if mobile.sha(path) != result.get(key): raise ValueError('Matching artifact mismatch: ' + key)
    return result


def build(args, common, mobile):
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    logs = out / 'logs'; logs.mkdir()
    shutil.copy2(__file__, out / 'driver.py')
    roots, files = inventories(args, mobile)
    receipt = json.loads(args.host_receipt.read_text())
    write(out / 'build-request.json', {'startedUtc': utc(), 'runtime': str(args.runtime), 'native': str(args.native),
        'corelib': str(args.corelib), 'compiler': str(args.compiler), 'buildReceipt': str(args.build_receipt),
        'hostReceipt': str(args.host_receipt), 'hostReceiptSha256': mobile.sha(args.host_receipt),
        'currentHostInputs': files, 'matchingBuildReceiptSha256': mobile.sha(args.build_receipt),
        'baseline': str(args.baseline), 'previousPlayer': str(args.previous_player) if args.previous_player else None,
        'selectionDirectory': str(args.selection_dir) if args.selection_dir else None})
    if receipt.get('schema') != 'runeclr.ios-session-policy.host-inputs.v1' or receipt.get('files') != files:
        raise ValueError('Transferred current host input bytes differ from the immutable host snapshot')
    matched = matching(args, common, mobile)
    inputs = out / 'input'; inputs.mkdir()
    original = args.baseline / 'original'
    baseline_app = next((args.baseline / 'app').glob('*.app'))
    old_hashes = mobile.tree(baseline_app)
    for path in sorted(original.glob('*.dll')):
        if not path.name.startswith(('RuneCLR.', 'HarnessBridge', 'PackageBridge', 'Microsoft.CodeAnalysis')):
            shutil.copy2(path, inputs / path.name)
    shutil.copy2(args.corelib, inputs / 'System.Private.CoreLib.dll')
    for name in PLAYER: shutil.copy2(args.player / name, inputs / name)
    for name, root in (('RuneCLR.Runtime.Tests.dll', args.lifecycle), ('RuneCLR.SampleHost.dll', args.sample)):
        shutil.copy2(root / name, inputs / name)
    seed_relative = 'dependency-a/RuneCLR.PrivateDependency.dll'
    shutil.copy2(args.lifecycle / seed_relative, inputs / 'RuneCLR.PrivateDependency.dll')
    if args.selection_dir:
        for path in (args.selection_dir / 'trusted').glob('*.dll'):
            if path.name not in ('SelectionProbe.Host.dll', 'SelectionProbe.Contract.dll'): raise ValueError('Unexpected selection trusted input')
            shutil.copy2(path, inputs / path.name)
    source = out / 'SessionBridge.cs'; source.write_text(BRIDGE)
    sdk = args.runtime / '.dotnet/dotnet'
    version = common.capture([sdk, '--version'])
    csc = args.runtime / '.dotnet/sdk' / version / 'Roslyn/bincore/csc.dll'
    common.logged([sdk, csc, '-nologo', '-noconfig', '-nostdlib+', '-optimize+', '-nullable:enable', '-target:exe',
        '-out:' + str(inputs / 'SessionBridge.dll'), *['-r:' + str(p) for p in sorted(inputs.glob('*.dll'))], source], logs / 'bridge-build.log')
    app = out / 'app/Session.app'; app.mkdir(parents=True)
    for path in baseline_app.glob('*.dylib'):
        if path.name != 'framework.dylib': shutil.copy2(args.native if path.name == 'libcoreclr.dylib' else path, app / path.name)
    if not (app / 'libcoreclr.dylib').exists(): shutil.copy2(args.native, app / 'libcoreclr.dylib')
    deps = baseline_app / 'Microsoft.NETCore.App.deps.json'
    if deps.exists(): shutil.copy2(deps, app / deps.name)
    # iOS has no dynamic JIT. With mode 0, ordinary trusted definitions need R2R.
    # Only per-session UGC/private fixtures remain IL outside this composite.
    composite = sorted(inputs.glob('*.dll'))
    options = ['--targetos:iossimulator', '--targetarch:arm64', '--obj-format:macho', '--composite', '--inputbubble',
        '--parallelism:2', '--resilient', '--optimize', '--out:' + str(app / 'framework.dylib')]
    rsp = out / 'crossgen.rsp'
    rsp.write_text('\n'.join(mobile.rsp_argument(a) for a in options + [str(p) for p in composite]) + '\n')
    common.logged([args.compiler, '@' + str(rsp)], logs / 'crossgen.log', timeout=900)
    obj = out / 'framework.o'; shutil.copy2(app / 'framework.dylib', obj)
    common.logged(['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator',
        '-dynamiclib', obj, '-Wl,-install_name,@rpath/framework.dylib', '-o', app / 'framework.dylib'], logs / 'composite-link.log')
    payload = {}
    for key, digest in files.items():
        lane, relative = key.split('/', 1)
        if '/' not in relative or relative.startswith('trusted/'): continue
        source_path = roots[lane] / relative
        relative_app = relative if lane != 'selection' else relative
        target = app / relative_app
        if target.exists() and mobile.sha(target) != digest: raise ValueError('Fixture path collision: ' + relative)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source_path, target)
        payload[relative_app] = digest
    # The existing lifecycle harness seeds this exact version A in Default last.
    # Reuse the generated component in marked private copies as an R2R refusal control.
    generated_seed = app / 'RuneCLR.PrivateDependency.dll'
    seed_layout = mobile.il_layout(generated_seed)
    if not seed_layout['managedNativeRva']: raise ValueError('Default collision seed has no R2R component')
    shutil.copy2(generated_seed, app / seed_relative)
    payload[seed_relative] = mobile.sha(generated_seed)
    payload_layouts = {relative: mobile.il_layout(app / relative) for relative in payload if relative.endswith('.dll')}
    if any(not layout['ilOnly'] or layout['managedNativeRva'] for relative, layout in payload_layouts.items() if relative != seed_relative):
        raise ValueError('Map/fixture/selection payload must be pure IL')
    for name in ('main.m', 'util.h', 'coreclrhost.h', 'host_runtime_contract.h'):
        shutil.copy2(args.baseline / name, out / name)
    wrapper = (args.baseline / 'runtime.m').read_text()
    wrapper = wrapper.replace('HarnessBridge.dll', 'SessionBridge.dll')
    wrapper = re.sub(r'^.*setenv\s*\(\s*"(?:DOTNET|COMPlus)_(?:Interp[A-Za-z]*|RuneCLRInterpretCollectible)"[^\n]*\n', '', wrapper, flags=re.M)
    anchor = '    char **managed_argv;'
    if wrapper.count(anchor) != 1: raise ValueError('Unknown native wrapper initialization template')
    settings = '\n'.join('    setenv("DOTNET_' + name + '", "' + value + '", 1);' for name, value in
        (('InterpMode','0'), ('RuneCLRInterpretCollectible','0'), ('InterpList','0')))
    settings += '\n    unsetenv("DOTNET_InterpDump");\n'
    settings += '    printf("SESSION_NATIVE_CONFIG InterpMode=%s RuneCLRInterpretCollectible=%s\\n", getenv("DOTNET_InterpMode"), getenv("DOTNET_RuneCLRInterpretCollectible")); fflush(stdout);\n'
    settings += '    setenv("RUNECLR_DOCUMENTS", [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES)[0] UTF8String], 1);\n'
    wrapper = wrapper.replace(anchor, settings + anchor)
    owner_anchor = '    void* handle = dlopen(r2r_path, RTLD_LAZY | RTLD_LOCAL);'
    if wrapper.count(owner_anchor) != 1: raise ValueError('Unknown native composite-loader template')
    wrapper = wrapper.replace(owner_anchor,
        '    // Controlled component copies can reside in fixture or temporary directories.\n'
        '    if (!strcmp(context->owner_composite_name, "framework.dylib"))\n'
        '        snprintf(r2r_path, sizeof(r2r_path), "%s/framework.dylib", get_bundle_path());\n' + owner_anchor)
    # Existing pinned wrapper uses argc 0; rebuild it with a single host-owned phase argument.
    call = r'coreclr_execute_assembly\s*\(coreclr_handle,\s*coreclr_domainId,\s*0,\s*NULL,\s*path,\s*&managed_exit\)'
    if len(re.findall(call, wrapper)) != 1: raise ValueError('Unknown native managed-entry call template')
    wrapper = re.sub(call, 'coreclr_execute_assembly(coreclr_handle, coreclr_domainId, 1, session_argv, path, &managed_exit)', wrapper)
    wrapper = wrapper.replace('unsigned int managed_exit=0;', 'const char* phase = getenv("RUNECLR_SESSION_PHASE");\n    const char* session_argv[] = {phase ? phase : "packages"};\n    unsigned int managed_exit=0;')
    if 'const char* session_argv[]' not in wrapper: raise ValueError('Unknown managed exit declaration')
    (out / 'runtime.m').write_text(wrapper)
    plist = plistlib.loads((baseline_app / 'Info.plist').read_bytes())
    bundle_id = 'org.runeclr.sessionpolicy.' + uuid.uuid4().hex[:12]
    plist.update(CFBundleExecutable='Session', CFBundleName='Session', CFBundleIdentifier=bundle_id)
    (app / 'Info.plist').write_bytes(plistlib.dumps(plist))
    common.logged(['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator', '-fobjc-arc',
        '-DINVARIANT_GLOBALIZATION=1', '-I' + str(out), out / 'main.m', out / 'runtime.m', '-L' + str(app),
        '-lcoreclr', '-framework', 'UIKit', '-framework', 'Foundation', '-Wl,-rpath,@executable_path', '-o', app / 'Session'], logs / 'wrapper-build.log')
    for path in app.glob('*.dylib'): common.logged(['codesign', '--force', '--sign', '-', path], logs / (path.name + '-sign.log'))
    common.logged(['codesign', '--force', '--sign', '-', app], logs / 'app-sign.log')
    layouts = {p.name: mobile.il_layout(p) for p in app.glob('*.dll')}
    trusted_components = set(PLAYER) | set(TRUSTED) | {'System.Private.CoreLib.dll', 'SessionBridge.dll', 'RuneCLR.PrivateDependency.dll'}
    if args.selection_dir: trusted_components |= {'SelectionProbe.Host.dll', 'SelectionProbe.Contract.dll'}
    if any(not layouts[name]['managedNativeRva'] for name in trusted_components):
        raise ValueError('Matching trusted R2R composite components missing')
    if mobile.macho_sections(args.native) != mobile.macho_sections(app / 'libcoreclr.dylib'):
        raise ValueError('Signed native sections differ from matching build')
    if any(p.name.startswith(('RuneCLR.Compiler', 'RuneCLR.PackageFixtures', 'Microsoft.CodeAnalysis')) for p in app.rglob('*')):
        raise ValueError('Operator/compiler entered player')
    if mobile.tree(baseline_app) != old_hashes or inventories(args, mobile)[1] != files or matching(args, common, mobile) != matched:
        raise ValueError('Read-only build inputs changed')
    shutil.copy2(args.host_receipt, out / 'host-inputs.json')
    shutil.copy2(args.build_receipt, out / 'matching-build.json')
    previous = json.loads((args.previous_player / 'state.json').read_text()) if args.previous_player else None
    write(out / 'state.json', {'app': str(app), 'bundleId': bundle_id, 'bundleHashes': mobile.tree(app),
        'matchingBuild': matched, 'matchingBuildReceiptSha256': mobile.sha(args.build_receipt),
        'hostSnapshotSha256': mobile.sha(args.host_receipt), 'currentHostInputs': files,
        'previousPlayer': str(args.previous_player) if args.previous_player else None,
        'previousPlayerInputHashes': previous.get('playerInputHashes') if previous else None,
        'previousPlayerBundleHashes': previous.get('bundleHashes') if previous else None,
        'originalFrameworkInputHashes': mobile.tree(original), 'inputHashes': mobile.tree(inputs),
        'nativeSections': mobile.macho_sections(args.native), 'nativeSha256': mobile.sha(args.native),
        'wrapperSections': mobile.macho_sections(app / 'Session'), 'bridgeSha256': mobile.sha(source),
        'wrapperSourceSha256': mobile.sha(out / 'runtime.m'), 'layouts': layouts, 'fixtureHashes': payload,
        'fixtureLayouts': payload_layouts, 'builtUtc': utc(), 'expectedLifecycleTests': 24,
        'defaultSeedR2RControl': {'path': seed_relative, 'originalILSha256': files['lifecycle/' + seed_relative],
            'generatedComponentSha256': payload[seed_relative], 'layout': seed_layout,
            'scope': 'Ordinary default seed requires native R2R; marked private copies must interpret the same definitions',
            'ownerMapping': 'Known framework.dylib owner always resolves to the immutable bundle root composite'},
        'runtime': str(args.runtime), 'native': str(args.native), 'selectionIncluded': bool(args.selection_dir),
        'trustedTopology': 'Framework/CoreLib/bridge/current Runtime/Packages/harnesses/contract are fresh composite R2R components',
        'ugcTopology': 'Other session fixture/map/private/selection payload is pure IL outside the composite; version A private dependency is an explicit submitted-R2R collision control',
        'scope': 'Fresh current trusted R2R player with matching combined runtime; per-session UGC/private payload remains IL; no device claim'})
    print('BUILD PASS ' + str(app), flush=True)


def load(args):
    out = args.output.resolve()
    return out, json.loads((out / 'state.json').read_text())


def verify_bundle(state, mobile):
    if mobile.tree(Path(state['app'])) != state['bundleHashes']: raise ValueError('Built player changed')
    if state.get('installedApp') and mobile.tree(Path(state['installedApp'])) != state['bundleHashes']:
        raise ValueError('Installed player changed')


def install(args, common, mobile):
    out, state = load(args)
    if 'simulator' in state: raise ValueError('Preserve existing installation; use a new output')
    verify_bundle(state, mobile)
    sim = common.capture(['xcrun', 'simctl', 'create', 'RuneCLR-Session-Policy', args.device_type, args.sim_runtime])
    state['simulator'] = sim
    write(out / 'state.json', state)
    common.logged(['xcrun', 'simctl', 'boot', sim], out / 'logs/boot-command.log')
    common.logged(['xcrun', 'simctl', 'bootstatus', sim, '-b'], out / 'logs/boot.log')
    common.logged(['xcrun', 'simctl', 'install', sim, state['app']], out / 'logs/install.log')
    for kind, key in (('app', 'installedApp'), ('data', 'dataContainer')):
        state[key] = common.capture(['xcrun', 'simctl', 'get_app_container', sim, state['bundleId'], kind])
    state['installedUtc'] = utc()
    write(out / 'state.json', state)
    verify_bundle(state, mobile)
    print('INSTALL PASS ' + sim, flush=True)


def transfer(args, common, mobile):
    out, state = load(args)
    verify_bundle(state, mobile)
    if 'installedUtc' not in state: raise ValueError('Install before transferring postinstall payload')
    target = Path(state['dataContainer']) / 'Documents'
    if args.packages:
        destination = target / 'controlled'
        if destination.exists(): raise ValueError('Preserve previous controlled payload')
        receipt_path = args.packages / 'fixtures.json'
        receipt = json.loads(receipt_path.read_text())
        if receipt.get('inputProfile') != 'managed-il-gameplay-v1' or receipt.get('contractImageSha256', '').lower() != state['currentHostInputs']['player/RuneCLR.Abstractions.dll']:
            raise ValueError('Controlled fixtures profile/current contract mismatch')
        if set(item['directory'] for item in receipt['packages']) != set(mobile.PACKAGES): raise ValueError('Expected nine controlled fixtures')
        for item in receipt['packages']:
            if mobile.sha(args.packages / item['directory'] / 'package.json') != item['manifestSha256'].lower():
                raise ValueError('Fixture manifest differs from producer receipt')
        payload = {name + '/' + rel: digest for name in mobile.PACKAGES for rel, digest in mobile.tree(args.packages / name).items()}
        layouts = {rel: mobile.il_layout(args.packages / rel) for rel in payload if rel.endswith('.dll')}
        if any(not layout['ilOnly'] or layout['managedNativeRva'] for layout in layouts.values()): raise ValueError('Controlled payload has native bodies')
        destination.mkdir(parents=True, exist_ok=False)
        for name in mobile.PACKAGES: shutil.copytree(args.packages / name, destination / name)
        if mobile.tree(destination) != payload: raise ValueError('Controlled transfer changed bytes')
        shutil.copy2(receipt_path, out / 'fixtures.json')
        manifests = {name: json.loads((args.packages / name / 'package.json').read_text()) for name in mobile.PACKAGES}
        state['controlled'] = {'source': str(args.packages), 'destination': str(destination), 'hashes': payload, 'layouts': layouts,
            'receiptSha256': mobile.sha(receipt_path), 'manifests': manifests, 'transferredUtc': utc(),
            'productionClaim': 'Existing producer receipt; new session-policy execution, no new production chronology claim'}
        write(out / 'state.json', state)
    if args.late:
        destination = target / 'late'
        if destination.exists(): raise ValueError('Preserve previous late payload')
        if not args.late_produced_utc: raise ValueError('Late IL requires explicit --late-produced-utc producer timestamp')
        produced = mobile.parse_utc(args.late_produced_utc)
        if produced <= mobile.parse_utc(state['installedUtc']) or produced <= mobile.parse_utc(state['builtUtc']):
            raise ValueError('Late IL must be produced after this player build and installation')
        manifest = json.loads((args.late / 'map.json').read_text())
        if manifest.get('entryAssembly') != 'RuneCLR.LateMap.dll' or manifest.get('entryType') != 'RuneCLR.LateMap.LateMap': raise ValueError('Unexpected late fixture')
        layout = mobile.il_layout(args.late / 'RuneCLR.LateMap.dll')
        if not layout['ilOnly'] or layout['managedNativeRva']: raise ValueError('Late fixture is not pure IL')
        destination.mkdir(parents=True, exist_ok=False)
        for name in ('map.json', 'RuneCLR.LateMap.dll'): shutil.copy2(args.late / name, destination / name)
        state['late'] = {'source': str(args.late), 'destination': str(destination), 'hashes': mobile.tree(destination),
            'layout': layout, 'productionStartedUtc': args.late_produced_utc, 'transferredUtc': utc(),
            'chronologyEvidence': 'Caller-supplied producer timestamp; preserve actual producer command/log/source hashes separately'}
        if args.late_receipt:
            shutil.copy2(args.late_receipt, out / 'late-producer.json')
            state['late']['producerReceiptSha256'] = mobile.sha(args.late_receipt)
        write(out / 'state.json', state)
    if not args.packages and not args.late: raise ValueError('Transfer needs --packages and/or --late')
    verify_bundle(state, mobile)
    print('TRANSFER PASS', flush=True)


def events(path, pid):
    raw = Path(path).read_text(errors='replace')
    first, last = raw.find('['), raw.rfind(']')
    if first < 0 or last < first: raise ValueError('Unified JSON event array missing')
    parsed = json.loads(raw[first:last + 1])
    if not isinstance(parsed, list) or any(event.get('processID') != int(pid) for event in parsed):
        raise ValueError('Unified JSON events are not from this owned PID')
    return parsed


def assess_messages(lane, messages):
    text = '\n'.join(messages)
    ack = sum(message == 'SESSION_EXECUTION_POLICY required-interpreter version=1' for message in messages)
    failure = any(message.startswith('FAIL ') for message in messages)
    if lane == 'packages':
        passed = sum(message.startswith('PASS ') for message in messages)
        complete = '15/15 package execution tests passed.' in messages and passed == 15
    elif lane == 'lifecycle':
        passed = sum(message.startswith('PASS ') for message in messages)
        complete = '24/24 tests passed' in messages and passed == 24 and 'PASS Map compiled after the host executes and unloads' in messages
    elif lane == 'sample':
        passed = sum(message.strip() == 'unload: collected' for message in messages)
        complete = passed == 3 and sum('Hello map started; start-count=1' in message for message in messages) == 2
        complete = complete and '[arena] Completed; ticks=3' in messages and sum(message == '[hello] Completed; ticks=3' for message in messages) == 2
    else:
        # Selection proof has its own stronger body/native-entry assessor; this phase is functional transport only.
        passed = len(re.findall(r'^PASS session=[0-9]+ .*collected=true$', text, re.M))
        complete = passed == 20 and '20/20 execution-selection sessions passed; 20/20 contexts collected' in messages
        ack = sum(message == 'POLICY API version=1 factory=required default=0 immutable-api=true' for message in messages)
    return {'functionalComplete': complete and not failure, 'individualPassed': passed, 'nativeAcknowledgementMarkers': ack,
        'noManagedFailure': not failure, 'scope': 'Harness semantics and native policy acknowledgement; method execution evidence is separate'}


def execute(args, common, mobile):
    out, state = load(args)
    verify_bundle(state, mobile)
    lane = args.lane
    if lane == 'packages' and 'controlled' not in state: raise ValueError('Transfer controlled fixtures first')
    if lane == 'lifecycle' and 'late' not in state: raise ValueError('Transfer late fixture first; current lifecycle requires 24 cases')
    if lane == 'selection' and not state['selectionIncluded']: raise ValueError('Selection adapter was not included in composite')
    evidence = out / ('run-' + lane)
    evidence.mkdir(exist_ok=False)
    environment = {key: value for key, value in os.environ.items() if not key.startswith(('SIMCTL_CHILD_DOTNET_', 'SIMCTL_CHILD_COMPlus_', 'SIMCTL_CHILD_RUNECLR_', 'SIMCTL_CHILD_PROBE_'))}
    environment['SIMCTL_CHILD_RUNECLR_SESSION_PHASE'] = lane
    if lane == 'selection':
        environment['SIMCTL_CHILD_RUNECLR_PROBE_LANE'] = 'required'
        environment['SIMCTL_CHILD_RUNECLR_PROBE_DIRECTORY'] = str(Path(state['installedApp']) / 'plugin')
        environment['SIMCTL_CHILD_RUNECLR_PROBE_EVIDENCE'] = str(Path(state['dataContainer']) / 'Documents/selection-evidence')
    sim, bundle = state['simulator'], state['bundleId']
    write(evidence / 'request.json', {'lane': lane, 'startUtc': utc(), 'simulator': sim, 'bundle': bundle,
        'environment': {key: value for key, value in environment.items() if key.startswith('SIMCTL_CHILD_')},
        'wrapperOverrides': {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0', 'DOTNET_InterpList': '0'},
        'hostInputsSha256': state['hostSnapshotSha256'], 'builtBundleHashes': state['bundleHashes']})
    result = {'passed': False, 'lane': lane}
    try:
        common.logged(['xcrun', 'simctl', 'launch', '--wait-for-debugger', '--stdout=' + str(evidence / 'managed.stdout.log'),
            '--stderr=' + str(evidence / 'managed.stderr.log'), sim, bundle], evidence / 'launch.log', env=environment)
        pid = int(re.search(r': ([0-9]+)', (evidence / 'launch.log').read_text()).group(1))
        query = ['xcrun', 'simctl', 'spawn', sim, 'log', 'stream', '--style', 'json', '--predicate', 'processIdentifier == ' + str(pid)]
        write(evidence / 'unified-query.json', {'command': query, 'appPid': pid, 'startUtc': utc(), 'simulator': sim})
        with (evidence / 'managed.unified.log').open('w') as output, (evidence / 'unified.stderr.log').open('w') as errors:
            stream = subprocess.Popen(query, stdout=output, stderr=errors, start_new_session=True)
            try:
                script = evidence / 'run.lldb'
                script.write_text('continue\nprocess status\nquit\n')
                status = common.logged(['xcrun', 'lldb', '--batch', '--attach-pid', str(pid), '--source', script], evidence / 'lldb.log', timeout=args.timeout, check=False)
            finally:
                if stream.poll() is None: stream.send_signal(signal.SIGINT)
                try: stream.wait(timeout=15)
                except subprocess.TimeoutExpired: stream.kill(); stream.wait(timeout=15)
                write(evidence / 'unified-completed.json', {'endUtc': utc(), 'streamExit': stream.returncode})
        parsed = events(evidence / 'managed.unified.log', pid)
        messages = [event.get('eventMessage', '') for event in parsed]
        write(evidence / 'managed-messages.json', messages)
        stdout = (evidence / 'managed.stdout.log').read_text(errors='replace')
        stderr = (evidence / 'managed.stderr.log').read_text(errors='replace')
        native_log = (evidence / 'lldb.log').read_text(errors='replace')
        result.update(assess_messages(lane, messages))
        unchanged = mobile.tree(Path(state['app'])) == state['bundleHashes'] and mobile.tree(Path(state['installedApp'])) == state['bundleHashes']
        payload_unchanged = all(mobile.tree(Path(state[name]['destination'])) == state[name]['hashes'] for name in ('controlled', 'late') if name in state)
        result.update({'appPid': pid, 'unifiedEvents': len(parsed), 'lldbExit': status, 'normalNativeExit': bool(re.search(r'exited with status = 0', native_log)),
            'nativeManagedExitZero': 'CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0' in stdout,
            'explicitMode0Diagnostic0': 'SESSION_NATIVE_CONFIG InterpMode=0 RuneCLRInterpretCollectible=0' in stdout,
            'bundleUnchanged': unchanged, 'payloadUnchanged': payload_unchanged,
            'noCrashOrAssertion': not any(marker in stdout + stderr + native_log + '\n'.join(messages) for marker in ('Got a SIGSEGV', 'Assert failure', 'Assertion failed')),
            'completedUtc': utc()})
        result['passed'] = all((result['functionalComplete'], result['nativeAcknowledgementMarkers'] > 0, status == 0,
            result['normalNativeExit'], result['nativeManagedExitZero'], result['explicitMode0Diagnostic0'], unchanged,
            payload_unchanged, result['noCrashOrAssertion']))
    except Exception as error:
        result['driverError'] = repr(error)
    finally:
        common.logged(['xcrun', 'simctl', 'terminate', sim, bundle], evidence / 'terminate.log', check=False)
        result['rawHashes'] = {path.name: mobile.sha(path) for path in sorted(evidence.iterdir()) if path.is_file()}
        write(evidence / 'results.json', result)
    print(json.dumps(result, indent=2), flush=True)
    if not result['passed']: raise RuntimeError('Acceptance failed; preserve this run and create a new attempt')


def cleanup(args, common):
    out, state = load(args)
    if (out / 'cleanup.json').exists(): raise ValueError('Preserve original cleanup receipt')
    status = common.logged(['xcrun', 'simctl', 'shutdown', state['simulator']], out / 'logs/shutdown.log', check=False)
    write(out / 'cleanup.json', {'simulator': state['simulator'], 'shutdownExit': status, 'completedUtc': utc()})
    if status: raise RuntimeError('Owned simulator shutdown failed')


def archive(args, mobile):
    out, state = load(args)
    verify_bundle(state, mobile)
    target = out / 'evidence.tar.gz'
    if target.exists(): raise ValueError('Preserve previous archive')
    with tarfile.open(target, 'w:gz') as package:
        for path in sorted(out.rglob('*')):
            if path.is_file() and path.suffix in ('.json', '.log', '.rsp', '.lldb', '.py', '.cs', '.m', '.h'):
                package.add(path, arcname=str(path.relative_to(out)))
        for name in ('ios-r2r-fix-verify.py', 'verify-ios-packages.py'):
            package.add(Path(__file__).with_name(name), arcname='helpers/' + name)
        for path in sorted((out / 'input').glob('RuneCLR.*.dll')):
            package.add(path, arcname='current-player-il/' + path.name)
    print(json.dumps({'archive': str(target), 'sha256': mobile.sha(target), 'bytes': target.stat().st_size}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('snapshot', 'build', 'install', 'transfer', 'run', 'cleanup', 'archive'))
    parser.add_argument('--output', type=Path)
    for name in ('runtime', 'native', 'corelib', 'compiler', 'build-receipt', 'baseline', 'player', 'lifecycle', 'sample',
                 'host-receipt', 'previous-player', 'selection-dir', 'packages', 'late', 'late-receipt'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--late-produced-utc')
    parser.add_argument('--lane', choices=('packages', 'lifecycle', 'sample', 'selection'), default='packages')
    parser.add_argument('--device-type', default='com.apple.CoreSimulator.SimDeviceType.iPhone-17')
    parser.add_argument('--sim-runtime', default='com.apple.CoreSimulator.SimRuntime.iOS-27-0')
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    needed = ('player', 'lifecycle', 'sample', 'host_receipt') if args.phase == 'snapshot' else ('output',)
    if args.phase == 'build': needed += ('runtime', 'native', 'corelib', 'compiler', 'build_receipt', 'baseline', 'player', 'lifecycle', 'sample', 'host_receipt')
    for name in needed:
        if getattr(args, name) is None: parser.error('This phase requires --' + name.replace('_', '-'))
    common, mobile = helper('ios-r2r-fix-verify'), helper('verify-ios-packages')
    if args.phase == 'snapshot': snapshot(args, mobile)
    elif args.phase == 'build': build(args, common, mobile)
    elif args.phase == 'install': install(args, common, mobile)
    elif args.phase == 'transfer': transfer(args, common, mobile)
    elif args.phase == 'run': execute(args, common, mobile)
    elif args.phase == 'cleanup': cleanup(args, common)
    else: archive(args, mobile)


if __name__ == '__main__': main()
