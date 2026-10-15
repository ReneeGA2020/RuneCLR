#!/usr/bin/env python3
"""Execute the reviewed v2 method-entry contract in an owned simulator lane.

This driver deliberately keeps the v2 offline planner immutable.  Live work is
gated by an explicit flag and a separately reviewed native-bind receipt.
"""
import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import uuid

V2_SHA = 'c9d6f483c22559e9629bc8a801619421ad3b7fa447484162446d2368fd0f559b'
OLD_SHA = 'bc922779f4a64b83ca69b6b5dd1f13a9f842277e9b7f60226910508c6f1d779a'
CAPTURE_READY = False
LIVE_CONTRACT = 'v2-live-ordinary-current-opcode-1'
BUDGET_AUDIT_SHA = '4ecc6e1751d59d9402eeeaf4e5b155c1a44fb2617ec56aadd183d8ca59ba34d4'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='ascii') as stream:
        json.dump(value, stream, indent=2)
        stream.write(chr(10))


def module(name, path, expected):
    path = Path(path)
    need(sha(path) == expected, 'Frozen helper changed: ' + path.name)
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def v2():
    return module('fresh_entry_v2_plan', Path(__file__).with_name('ios-fresh-author-entry-capture-v2.py'), V2_SHA)


def old():
    return module('fresh_entry_old', Path(__file__).with_name('ios-fresh-author-entry-capture.py'), OLD_SHA)


def native_review(path):
    root = Path(path).resolve()
    review = read(root / 'review.json')
    receipt = read(root / 'native-bind-receipt.json')
    result = read(root / 'results.json')
    need(review.get('passed') is True and receipt.get('passed') is True and result.get('passed') is True,
         'Native bind review is not passed')
    capture = Path(review['capturePath'])
    need(capture.is_file() and sha(capture) == review['captureSha256'] == V2_SHA,
         'Native bind review targets a different v2 planner')
    need(receipt.get('targetProcessCreated') is False and receipt.get('physicalDeviceExecuted') is False,
         'Native bind receipt has target or physical side effects')
    paths = receipt.get('paths', {})
    need(set(paths) == {'function-entry', 'ordinary-child-dispatch', 'delegate-child-dispatch'},
         'Native bind receipt does not cover three paths')
    for kind, value in paths.items():
        if isinstance(value, dict):
            value = [value.get('prefixHex'), value.get('filePc')]
        need(isinstance(value, list) and len(value) == 2 and re.fullmatch(r'[0-9a-f]{128}', value[0]),
             'Native bind prefix is not a 64-byte hex window: ' + kind)
        paths[kind] = value
    return root, review, receipt


def gate(args, request=None):
    # Keep this check before helper loading or any host command.
    need(args.enable_live, 'Live capture requires explicit --enable-live')
    need(CAPTURE_READY is False or args.enable_live, 'Live capture gate is disabled')
    need(args.native_bind_review is not None, 'Live capture requires --native-bind-review')
    root, review, receipt = native_review(args.native_bind_review)
    if request is not None:
        need(request.get('nativePrefixBound') is True, 'Plan has no native prefix binding')
        need(request.get('liveDriverSha256') == sha(__file__), 'Live plan must match this driver')
        need(request.get('requestContract') == LIVE_CONTRACT, 'Live contract version differs')
        need(request['nativeBindReviewSha256'] == sha(root / 'review.json')
             and request['nativeBindReceiptSha256'] == sha(root / 'native-bind-receipt.json'),
             'Native bind review changed after planning')
        need(request['timeoutSeconds'] == args.timeout, 'Timeout must match the plan')
        for key, path, leaf, digest in (
                ('prepare', args.prepare, 'identity.json', 'prepareIdentitySha256'),
                ('application', args.application, 'state.json', 'stateSha256')):
            need(request[key] == str(path.resolve()) and request[digest] == sha(path / leaf),
                 'Frozen plan input changed: ' + key)
        need(request['runtime'] == str(args.runtime.resolve()), 'Runtime path differs from plan')
        identity = read(args.prepare / 'identity.json')
        native = args.runtime / 'artifacts/bin/coreclr/iossimulator.arm64.Release/libcoreclr.dylib'
        need(receipt['nativeSha256'] == sha(native)
             and receipt['nativeUuid'] == identity['sourceNative']['uuid'], 'Native review image differs')
        need(sha(args.output / 'request.json') == read(args.output / 'live-results.json')['requestSha256'],
             'Live request changed after planning')
        for kind, value in receipt['paths'].items():
            need(request['paths'][kind]['filePc'] == value[1]
                 and request['paths'][kind]['prefixHex'] == value[0], 'Native path binding differs: ' + kind)
    return root, review, receipt


def query(host, out, name, argv):
    host.stage(out, name, argv, timeout=45)
    return (Path(out) / (name + '.stdout')).read_text().strip()


def retire(args, label):
    out = args.output.resolve()
    owned_path = out / 'owned-simulator.json'
    if not owned_path.is_file():
        return
    host = old().helper('ios-fresh-author-simulator-continuation.py', old().CONTINUATION_SHA)
    dest = out / label
    dest.mkdir(exist_ok=True)
    owned = read(owned_path)
    # The UUID is read only from this run's receipt; no global simulator cleanup.
    host.retire_owned(out, dest, label)
    host.stage(dest, 'delete', ['xcrun', 'simctl', 'delete', owned['id']], timeout=120)
    listing = json.loads(query(host, dest, 'devices-list', ['xcrun', 'simctl', 'list', 'devices', '--json']))
    write(dest / 'devices-after.json', listing)
    need(not any(x['udid'] == owned['id'] for group in listing['devices'].values() for x in group),
         'Owned simulator survived retirement')
    write(dest / 'results.json', {'passed': True, 'deleted': True, 'simulator': owned['id'],
                                  'physicalDeviceChanged': False})


def plan(args):
    planner = v2()
    # Delegate all frozen source/receipt reads and observer generation to v2.
    planner.plan(args)
    out = args.output.resolve()
    request_path = out / 'request.json'
    request = read(request_path)
    if args.native_bind_review is not None:
        _, review, receipt = native_review(args.native_bind_review)
        need(review['captureSha256'] == V2_SHA, 'Native review source differs from v2 planner')
        for kind, value in receipt['paths'].items():
            need(request['paths'][kind]['filePc'] == value[1], 'Native bind PC differs: ' + kind)
            request['paths'][kind]['prefixHex'] = value[0]
            request['paths'][kind]['nativePrefixBound'] = True
        request['nativePrefixBound'] = True
        request['nativeBindReviewSha256'] = sha(Path(args.native_bind_review) / 'review.json')
        request['nativeBindReceiptSha256'] = sha(Path(args.native_bind_review) / 'native-bind-receipt.json')
    else:
        request['nativePrefixBound'] = False
    request['liveDriverSha256'] = sha(Path(__file__))
    # At this ordinary-child PC the preceding add has already skipped the header.
    # Delegate dispatch still points before its pre-indexed load and needs +8.
    request['paths']['ordinary-child-dispatch']['opcodeAddressAdvance'] = 0
    request['requestContract'] = LIVE_CONTRACT
    request['liveCaptureReady'] = False
    request['livePending'] = ['Enable only after explicit --enable-live and reviewed native bind.']
    request_path.write_text(json.dumps(request, indent=2) + chr(10), encoding='ascii')
    write(out / 'live-results.json', {'passed': True, 'phase': 'plan', 'liveCaptureReady': False,
                                      'nativePrefixBound': request['nativePrefixBound'],
                                      'targetProcessCreated': False, 'physicalDeviceExecuted': False,
                                      'requestSha256': sha(request_path),
                                      'driverSha256': sha(Path(__file__))})


def install(args):
    # Read local request before importing/starting any host adapter.
    out = args.output.resolve(); request = read(out / 'request.json')
    need(request.get('liveDriverSha256') == sha(Path(__file__)), 'Live plan must match this driver')
    need(request.get('nativePrefixBound') is True, 'Live plan has no native prefix binding')
    gate(args, request)
    helper = old(); prepare, host, identity, state, _, _ = helper.frozen(args)
    dest = out / 'installation'; dest.mkdir(exist_ok=False)
    try:
        host.stage(dest, 'create', ['xcrun', 'simctl', 'create', 'RuneCLR-Fresh-Author-Entry-V2',
                                   args.device_type, args.sim_runtime], timeout=60)
        simulator = (dest / 'create.stdout').read_text().strip()
        need(re.fullmatch(r'[0-9A-F-]{36}', simulator), 'Owned simulator UUID differs')
        write(out / 'owned-simulator.json', {'id': simulator, 'bundleId': state['bundleId'],
                                             'driverSha256': sha(Path(__file__))})
        host.stage(dest, 'boot', ['xcrun', 'simctl', 'boot', simulator], timeout=60)
        host.stage(dest, 'bootstatus', ['xcrun', 'simctl', 'bootstatus', simulator, '-b'], timeout=180)
        host.stage(dest, 'install', ['xcrun', 'simctl', 'install', simulator, state['app']], timeout=120)
        installed = Path(query(host, dest, 'app-container', ['xcrun', 'simctl', 'get_app_container', simulator, state['bundleId'], 'app']))
        data = Path(query(host, dest, 'data-container', ['xcrun', 'simctl', 'get_app_container', simulator, state['bundleId'], 'data']))
        need(simulator in str(installed) and simulator in str(data), 'Container paths belong to the owned simulator')
        need(host.inventory(installed) == state['bundleHashes'] and not (data / 'Documents/budget-plugin').exists(),
             'Diagnostic installation changed or author is already present')
        write(dest / 'results.json', {'passed': True, 'simulator': simulator, 'installedApp': str(installed),
            'dataContainer': str(data), 'authorDirectoryAbsent': True, 'readbackUtc': host.utc(),
            'stateSha256': sha(args.application / 'state.json'), 'driverSha256': sha(Path(__file__)),
            'physicalDeviceInstalled': False, 'appLaunched': False})
    except Exception:
        if (out / 'owned-simulator.json').is_file():
            try: retire(args, 'installation-error')
            except Exception: pass
        raise


def author_readback(args):
    out = args.output.resolve(); installation = read(out / 'installation/results.json')
    need(installation.get('passed') and installation.get('appLaunched') is False, 'Successful install receipt required')
    authors = args.authors.resolve(); compiled = read(authors / 'results.json')
    need(compiled.get('passed') and compiled.get('authorCompilationCount') == 2 and compiled.get('authorIlOnly'),
         'Fresh author compilation receipt is required')
    started = datetime.fromisoformat(compiled['startedAfterHostBindingUtc'])
    bound = datetime.fromisoformat(installation['readbackUtc'])
    need(started > bound, 'Author compilation must start after diagnostic install readback')
    plugin = Path(installation['dataContainer']) / 'Documents/budget-plugin'
    need(not plugin.exists(), 'Author directory was created before readback')
    shutil.copytree(authors / 'plugin', plugin, dirs_exist_ok=False)
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((authors / 'plugin').iterdir())}
    need(hashes == compiled['authorHashes'], 'Author readback source hashes differ')
    installed_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(plugin.iterdir())}
    need(installed_hashes == hashes, 'Installed author bytes differ')
    write(out / 'author-readback.json', {'passed': True, 'authors': str(authors), 'plugin': str(plugin),
        'authorHashes': hashes, 'compilerResultSha256': sha(authors / 'results.json'),
        'installReceiptSha256': sha(out / 'installation/results.json'), 'appLaunched': False,
        'physicalDeviceExecuted': False})


def compile_authors_after_install(args):
    """Optionally invoke the frozen compiler only after install readback."""
    if args.author_inputs is None and args.author_sdk is None and args.author_refs is None:
        return args.authors
    need(args.author_inputs is not None and args.author_sdk is not None and args.author_refs is not None,
         'author-inputs, author-sdk and author-refs must be supplied together')
    out = args.output.resolve(); installation = read(out / 'installation/results.json')
    # The frozen compiler owns creation of its receipt directory.
    target = out / 'author-compilation-after-install'
    compiler = Path(__file__).with_name('prepare-ios-device-author.py')
    app = Path(installation['installedApp'])
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    simulator_bundle = info.get('CFBundleSupportedPlatforms') != ['iPhoneOS']
    phase = 'sanity' if simulator_bundle else 'prepare'
    command = [os.environ.get('PYTHON', sys.executable), '-B', str(compiler), phase,
               '--inputs', str(args.author_inputs.resolve()), '--sdk', str(args.author_sdk.resolve()),
               '--refs', str(args.author_refs.resolve()), '--output', str(target)]
    if not simulator_bundle:
        command += ['--app', installation['installedApp']]
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
    target.mkdir(exist_ok=True)
    (target / 'compiler.stdout').write_text(completed.stdout, encoding='utf-8')
    (target / 'compiler.stderr').write_text(completed.stderr, encoding='utf-8')
    need(completed.returncode == 0, 'Post-install author compiler failed')
    return target


def run(args):
    out = args.output.resolve(); request = read(out / 'request.json')
    result = {'passed': False, 'physicalDeviceExecuted': False, 'driverSha256': sha(__file__)}
    try:
        gate(args, request)
        need((out / 'installation/results.json').is_file(), 'Install receipt required')
        args.authors = compile_authors_after_install(args)
        author_readback(args)
        if not args.launch:
            _write_pending_observer(args, request)
            result.update(passed=True, phase='author-readback', targetProcessCreated=False)
        else:
            result.update(_launch_and_capture(args, request))
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        # Retire only the UUID recorded by this output directory.
        try:
            retire(args, 'cleanup')
            result['cleanupSucceeded'] = True
        except Exception as error:
            result.update(passed=False, cleanupSucceeded=False, cleanupError=str(error))
        write(out / 'run-results.json', result)
        print(json.dumps(result), flush=True)
    need(result['passed'], 'Run or owned simulator cleanup failed')


def _write_pending_observer(args, request):
    dest = args.output.resolve() / 'diagnostic'; dest.mkdir(exist_ok=False)
    observer = v2().observer_source()
    need(hashlib.sha256(observer.encode('ascii')).hexdigest() == request['observerSha256'],
         'Frozen v2 observer changed')
    (dest / 'fresh_author_entry_v2_lldb.py').write_text(observer, encoding='ascii')
    write(dest / 'capture-config.pending.json', {'pid': None, 'nonce': uuid.uuid4().hex,
        'paths': request['paths'], 'methodPhases': request['methodPhases'], 'layouts': request['layouts'],
        'threadContract': request['threadContract'], 'requiredMethods': request['requiredMethods'],
        'nativePrefixBound': True, 'targetProcessCreated': False, 'physicalDeviceExecuted': False})
    write(dest / 'results.json', {'passed': True, 'phase': 'author-readback', 'appLaunched': False,
        'observerWritten': True, 'targetProcessCreated': False, 'physicalDeviceExecuted': False,
        'driverSha256': sha(Path(__file__))})


def _launch_and_capture(args, request):
    out = args.output.resolve(); dest = out / 'diagnostic'; dest.mkdir(exist_ok=False)
    install = read(out / 'installation/results.json'); simulator = install['simulator']
    authors = args.authors.resolve(); compiled = read(authors / 'results.json')
    helper = old(); prepare = helper.helper('ios-fresh-author-entry-prepare.py', helper.PREPARE_SHA)
    _, host, identity, state, source, dwarf = helper.frozen(args)
    pe = prepare.readers(); module_rows = {}
    installed = Path(install['installedApp'])
    plugin = Path(install['dataContainer']) / 'Documents/budget-plugin'
    before = {'bundle': host.inventory(installed), 'author': host.inventory(plugin)}
    need(before['bundle'] == state['bundleHashes'] and before['author'] == compiled['authorHashes'],
         'Installed bundle or author bytes changed before launch')
    write(dest / 'installed-before.json', before)
    for name, old_module in identity['modules'].items():
        path = authors / 'plugin' / name
        need(sha(path) == compiled['authorHashes'][name], 'Author output hash differs')
        layout = pe['il_layout'](path); need(layout == {'ilOnly': True, 'managedNativeRva': 0}, 'Author IL-only header differs')
        methods = pe['plugin_methods'](path, required=tuple(old_module['methods']), qualified=True)
        module_rows[name] = {'fileName': name, 'simpleName': name[:-4], 'sha256': sha(path),
            'methods': {n: methods[n] for n in old_module['methods']}, 'path': str(Path(install['dataContainer']) / 'Documents/budget-plugin' / name),
            **pe['pe_mvid'](path)}
        need(module_rows[name]['moduleMvid'] != old_module['moduleMvid'], 'Fresh author MVID required')
    nonce = uuid.uuid4().hex
    env = {k: v for k, v in os.environ.items() if not k.startswith('SIMCTL_CHILD_')}
    env['SIMCTL_CHILD_RUNECLR_BUDGET_NONCE'] = nonce
    host.stage(dest, 'wait-launch', ['xcrun', 'simctl', 'launch', '--wait-for-debugger',
        '--stdout=' + str(dest / 'native.stdout'), '--stderr=' + str(dest / 'native.stderr'), simulator, state['bundleId']], env, 60)
    marker = re.fullmatch(re.escape(state['bundleId']) + r': (\d+)\s*', (dest / 'wait-launch.stdout').read_text())
    need(marker is not None, 'Exact owned target launch PID marker differs')
    pid = int(marker[1]); installed = Path(install['installedApp'])
    layouts = dict(identity['layouts'], **request['layouts'], **helper.OWNER_LAYOUTS)
    paths = json.loads(json.dumps(request['paths']))
    config = {'pid': pid, 'nonce': nonce, 'authors': module_rows, 'requiredMethods': request['requiredMethods'],
        'methodPhases': request['methodPhases'], 'gate': request['gate'], 'layouts': layouts,
        'threadContract': request['threadContract'], 'paths': paths, 'nativeUuid': identity['signedNative']['uuid'],
        'installedNative': str(installed / 'libcoreclr.dylib'), 'sourcePath': str(args.runtime.resolve() / Path('src/coreclr/vm/interpexec.cpp')),
        'hitCap': request['hitCap']}
    write(dest / 'capture-config.json', config)
    observer = v2().observer_source()
    if args.debug_observer:
        # Preserve the frozen callback while recording register state for a contract mismatch.
        needle = "        ERRORS.append({'hit':HITS,'pc':frame.GetPC(),'error':str(error)}); save('capture-errors.json',ERRORS); disable_all()"
        replacement = "        ERRORS.append({'hit':HITS,'pc':frame.GetPC(),'error':str(error),'function':frame.GetFunctionName(), 'registers': {name: frame.FindRegister(name).GetValueAsUnsigned() for name in ('x9','x19','x26','x1','x2','x3')}}); save('capture-errors.json',ERRORS); disable_all()"
        need(needle in observer, 'Frozen observer debug hook is unavailable')
        observer = observer.replace(needle, replacement, 1)
        mismatch = "    if opcode != item['bytecodeStart'] + 8: raise RuntimeError('Child opcode pointer differs from its current frame')"
        detail = "    if opcode != item['bytecodeStart'] + 8: raise RuntimeError(f'Child opcode pointer differs from its current frame: register={opcode_register_value} advance={contract[\"opcodeAddressAdvance\"]} actual={opcode} expected={item[\"bytecodeStart\"] + 8} frame={frame_base} spill={frame_address} bytecode={item[\"bytecodeStart\"]}')"
        need(mismatch in observer, 'Frozen child debug hook is unavailable')
        observer = observer.replace(mismatch, detail, 1)
    else:
        need(hashlib.sha256(observer.encode('ascii')).hexdigest() == request['observerSha256'], 'Frozen v2 observer changed')
    (dest / 'fresh_author_entry_v2_lldb.py').write_text(observer, encoding='ascii')
    actual_observer_sha = sha(dest / 'fresh_author_entry_v2_lldb.py')
    commands = ['breakpoint set -n coreclr_initialize', 'continue', 'breakpoint disable 1',
        'target symbols add "' + str(dwarf) + '"', 'command script import "' + str(dest / 'fresh_author_entry_v2_lldb.py') + '"',
        'script fresh_author_entry_v2_lldb.safe_setup()', 'continue', 'process status',
        'script fresh_author_entry_v2_lldb.finish()', 'quit']
    (dest / 'capture.lldb').write_text('\n'.join(commands) + '\n', encoding='utf-8')
    try:
        host.stage(dest, 'lldb', ['xcrun', 'lldb', '--batch', '--no-lldbinit', '--attach-pid', str(pid), '--source', dest / 'capture.lldb'],
                   timeout=args.timeout, before_timeout_retire=lambda: host.retire_owned(out, dest, 'timeout'))
        hits = read(dest / 'capture-hits.json'); breakpoints = read(dest / 'breakpoints.json')
        need(hits['allRequiredCovered'] and hits['errors'] == 0 and hits['entries'] == 9 and hits['disabledAfterCoverage']
             and 9 <= hits['hits'] <= config['hitCap'] and not (dest / 'capture-errors.json').exists(),
             'Diagnostic coverage failed')
        verify_capture(dest, config, breakpoints)
        evidence = Path(install['dataContainer']) / 'Documents' / ('budget-evidence-' + nonce)
        shutil.copytree(evidence, dest / 'adapter-evidence')
        validate_completion(dest, config, host)
        after = {'bundle': host.inventory(installed), 'author': host.inventory(plugin)}
        write(dest / 'installed-after.json', after)
        need(before == after and host.inventory(Path(state['app'])) == state['bundleHashes'],
             'Installed/frozen bundle or author bytes changed')
        result = {'passed': True, 'phase': 'live-capture', 'pid': pid, 'nonce': nonce,
            'methodGroups': 9, 'targetProcessCreated': True, 'physicalDeviceExecuted': False,
            'nativeEntryProof': True, 'firstOpcodeProof': False, 'contexts': 73, 'cases': 15,
            'debuggerTargetExitStatus': 0, 'actualTargetExitObservedByDebugger': True,
            'authorCompiledAfterDiagnosticInstallation': True, 'installedInputsUnchanged': True,
            'requestContract': LIVE_CONTRACT, 'debugObserver': args.debug_observer,
            'observedEntryPaths': sorted({item['kind'] for item in read(dest / 'interpreter-entries.json')}),
            'delegateSpecialDispatchRequired': False,
            'nativePrefixBound': True, 'observerSha256': actual_observer_sha, 'driverSha256': sha(Path(__file__))}
        write(dest / 'results.json', result)
        return result
    except Exception as error:
        write(dest / 'results.json', {'passed': False, 'phase': 'live-capture', 'pid': pid, 'error': str(error),
            'targetProcessCreated': True, 'physicalDeviceExecuted': False, 'driverSha256': sha(Path(__file__))})
        raise


def verify_capture(dest, config, breakpoints):
    need(breakpoints['pid'] == config['pid'] and breakpoints['nativeUuid'] == config['nativeUuid']
         and breakpoints['layoutsValidated'] == config['layouts']
         and set(breakpoints['paths']) == set(config['paths']), 'Live breakpoint process/layout differs')
    slides = set()
    for kind, contract in config['paths'].items():
        bp = breakpoints['paths'][kind]
        need(bp['filePc'] == contract['filePc'] and bp['prefixHex'] == contract['prefixHex']
             and bp['locations'] == 1 and bp['loadPc'] > 0, 'Live breakpoint native bytes differ: ' + kind)
        slides.add(bp['loadPc'] - bp['filePc'])
    need(len(slides) == 1, 'Live breakpoint native slides differ')
    entries = read(dest / 'interpreter-entries.json')
    need({'function-entry', 'ordinary-child-dispatch'} <= {item['kind'] for item in entries},
         'Function and ordinary-child live paths required')
    v2().verify_entries(entries, config, breakpoints)


def validate_completion(dest, config, host):
    pid, nonce = config['pid'], config['nonce']
    need(re.search(r'^Process ' + str(pid) + r' exited with status = 0 \(0x00000000\)\s*$',
                   (dest / 'lldb.stdout').read_text(), re.M), 'Owned target debugger exit status differs')
    adapter = read(dest / 'adapter-evidence/result.json')
    need(adapter['passed'] and adapter['processId'] == pid and adapter['nonce'] == nonce
         and adapter['contexts'] == 73 and len(adapter['cases']) == 15, 'Managed aggregate differs')
    rows = []
    receipts = set()
    for item in adapter['cases']:
        path = (dest / 'adapter-evidence' / item['receipt']).resolve()
        need(path.is_relative_to((dest / 'adapter-evidence').resolve()) and path not in receipts,
             'Child receipt path escapes evidence or repeats')
        receipts.add(path)
        child = read(path)
        need(sha(path) == item['receiptSha256'] and child['passed'] and child['nonce'] == item['nonce'],
             'Child receipt binding differs')
        rows.extend(child['rows'])
    need(len(rows) == 73 and all(x['collected'] for x in rows), 'Context collection differs')
    audit = module('fresh_live_budget_audit', Path(__file__).with_name('mobile-host-budget-audit.py'), BUDGET_AUDIT_SHA)
    audit.adapter(dest / 'adapter-evidence', nonce, pid)
    log = (dest / 'native.stdout').read_text() + '\n' + (dest / 'native.stderr').read_text()
    markers = [f'FRESH_AUTHOR_SIM_NATIVE pid={pid} nonce={nonce} PhaseAcquireLoad=1 DerivedLedger=1 BatchInterval=0 InterpMode=0 InterpretCollectible=0 ReadyToRun=1',
        f'FRESH_AUTHOR_SIM_INITIALIZE pid={pid} nonce={nonce} hr=0',
        f'FRESH_AUTHOR_SIM_CREATE_DELEGATE pid={pid} nonce={nonce} hr=0',
        f'FRESH_AUTHOR_SIM_INVOKE pid={pid} nonce={nonce} managedExit=0',
        f'FRESH_AUTHOR_SIM_SHUTDOWN pid={pid} nonce={nonce} attempted=false reason=template-exit-path',
        f'FRESH_AUTHOR_SIM_EXIT pid={pid} nonce={nonce} managedExit=0 actualExit=0']
    need(all(host.exact_marker(log, marker, pid) for marker in markers), 'Native completion marker differs')


def cleanup(args):
    retire(args, 'manual-cleanup')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('plan', 'install', 'run', 'cleanup'))
    for name in ('prepare', 'application', 'runtime', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--authors', type=Path)
    parser.add_argument('--author-inputs', type=Path)
    parser.add_argument('--author-sdk', type=Path)
    parser.add_argument('--author-refs', type=Path)
    parser.add_argument('--native-bind-review', type=Path)
    parser.add_argument('--enable-live', action='store_true')
    parser.add_argument('--launch', action='store_true')
    parser.add_argument('--debug-observer', action='store_true')
    parser.add_argument('--device-type', default='com.apple.CoreSimulator.SimDeviceType.iPhone-16')
    parser.add_argument('--sim-runtime', default='com.apple.CoreSimulator.SimRuntime.iOS-27-0')
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    need(30 <= args.timeout <= 600, 'Diagnostic timeout must be between 30 and 600 seconds')
    if args.phase == 'plan':
        plan(args)
    else:
        # Platform and readiness checks happen after the explicit gate, so a
        # missing flag cannot even probe a host adapter or simulator.
        need(args.enable_live, 'Live capture requires explicit --enable-live')
        need(platform.system() == 'Darwin', 'Simulator tool requires the configured Mac')
        if args.phase == 'install': install(args)
        elif args.phase == 'run':
            need(args.authors is not None or
                 (args.author_inputs is not None and args.author_sdk is not None and args.author_refs is not None),
                 '--authors or all post-install compiler inputs are required for run')
            run(args)
        else: cleanup(args)


if __name__ == '__main__':
    main()
