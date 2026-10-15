#!/usr/bin/env python3
"""Observe four direct batch-author interpreter invocations on a separate simulator."""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import time
import uuid

PREPARE_SHA = '5956effd1046633755e6db7f70915ed8d4f1725cfa579fc7a0b740a1f76d99a8'
ACCEPT_SHA = 'd2bee86ffed7438f8b0fd7206e7569ff1ed4daf5331a5de090c5ccee996d0656'
REVIEW_SHA = '9aab8cae277ad138b6635b9db61bf30bcfa942ce14aa54c56df71e6bb683ccd2'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x', encoding='ascii') as stream:
        stream.write(json.dumps(value, indent=2) + chr(10))


def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def helper(filename, expected):
    path = Path(__file__).with_name(filename)
    need(sha(path) == expected, 'Frozen helper differs: ' + filename)
    spec = importlib.util.spec_from_file_location(filename.replace('.', '_'), path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


# This decoder receives only a bounded memory reader and hash-bound current offsets.
# It is shared verbatim with the observer and exercised by synthetic memory controls.
DECODER = r'''
def decode(memory, context, exception_args, config):
    if exception_args:
        return None
    def integer(address, count=8):
        value = memory(address, count)
        if len(value) != count: raise RuntimeError('Short native memory read')
        return int.from_bytes(value, 'little')
    def offset(kind, name): return config['layouts'][kind]['fields'][name]
    def text(address, width, limit):
        data = bytearray()
        for i in range(limit):
            unit = memory(address + width * i, width)
            if len(unit) != width: raise RuntimeError('Short module string read')
            if unit == bytes(width): return data.decode('ascii' if width == 1 else 'utf-16-le')
            data.extend(unit)
        raise RuntimeError('Unterminated module identity')
    start = integer(context + offset('InterpMethodContextFrame', 'startIp'))
    method = integer(start)
    desc = integer(method + offset('InterpMethod', 'methodHnd'))
    index = integer(desc + offset('MethodDesc', 'm_chunkIndex'), 1)
    chunk = desc - config['layouts']['MethodDescChunk']['size'] - index * 8
    table = integer(chunk + offset('MethodDescChunk', 'm_methodTable'))
    flags = integer(table + offset('MethodTable', 'm_dwFlags'), 4)
    if not flags & 0x00200000: return None
    module = integer(table + offset('MethodTable', 'm_pModule'))
    simple = text(integer(module + offset('Module', 'm_pSimpleName')), 1, 256)
    if simple != 'BatchBoundary.Author': return None
    path = text(integer(module + offset('Module', 'm_path')), 2, 4096)
    expected = config['author']
    if path != expected['path']: raise RuntimeError('Targeted loaded Module path differs')
    token = 0x06000000 | ((integer(chunk + offset('MethodDescChunk', 'm_flagsAndTokenRange'), 2) & 0xfff) << 12)
    token |= integer(desc + offset('MethodDesc', 'm_wFlags3AndTokenRemainder'), 2) & 0xfff
    names = [name for name, value in expected['methods'].items() if value == token]
    if len(names) != 1: raise RuntimeError('Targeted MethodDef token absent or ambiguous')
    size = integer(method + offset('InterpMethod', 'codeSize'), 4)
    desc_start = integer(desc + offset('MethodDesc', 'm_interpreterCode'))
    if size <= 0 or desc_start != start: raise RuntimeError('MethodDesc interpreter bytecode differs')
    base = integer(module + offset('Module', 'm_baseAddress'))
    mapped = None
    for label, root_key, mvid_key in (('rva', 'metadataRootRva', 'moduleMvidRva'),
                                      ('flat', 'metadataRootOffset', 'moduleMvidOffset')):
        try:
            if memory(base + expected[root_key], 4) == b'BSJB' and memory(base + expected[mvid_key], 16).hex() == expected['moduleMvidBytesHex']:
                mapped = label
                break
        except RuntimeError:
            pass
    if mapped is None: raise RuntimeError('Actual loaded PE MVID differs from frozen author')
    return {'methodContextFrame': context, 'exceptionArgs': exception_args, 'interpMethod': method,
            'methodDesc': desc, 'methodDescChunk': chunk, 'methodTable': table, 'managedModule': module,
            'modulePath': path, 'moduleSimpleName': simple, 'collectible': True, 'methodDefToken': token,
            'metadataMethodName': names[0], 'fileSha256': expected['sha256'],
            'moduleMvid': expected['moduleMvid'], 'loadedMetadataMvidValidated': True, 'loadedPELayout': mapped,
            'modulePEAssembly': integer(module + offset('Module', 'm_pPEAssembly')),
            'moduleAssembly': integer(module + offset('Module', 'm_pAssembly')), 'moduleBaseAddress': base,
            'bytecodeStart': start, 'methodDescBytecodeStart': desc_start, 'bytecodeSizeSlots': size,
            'bytecodePrefixHex': memory(start + 8, min(size * 4, 64)).hex()}
'''


OBSERVER = r'''import json
from pathlib import Path
import lldb
OUT = Path(__file__).parent
CONFIG = json.loads((OUT / 'capture-config.json').read_text())
ENTRIES, ERRORS = [], []
HITS = 0
BP = None

def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + chr(10))

def memory(process, address, size):
    error = lldb.SBError()
    value = process.ReadMemory(address, size, error)
    if error.Fail() or len(value) != size: raise RuntimeError(str(error))
    return value

def invocation(frame, location, internal):
    global HITS
    HITS += 1
    process, target = frame.GetThread().GetProcess(), frame.GetThread().GetProcess().GetTarget()
    try:
        if HITS > CONFIG['hitCap']: raise RuntimeError('Bounded invocation hit cap exceeded')
        if process.GetProcessID() != CONFIG['pid'] or frame.GetPC() != CONFIG['entryLoadPc']:
            raise RuntimeError('Owned PID or exact function-entry PC differs')
        item = decode(lambda a, n: memory(process, a, n), frame.FindRegister('x1').GetValueAsUnsigned(),
                      frame.FindRegister('x3').GetValueAsUnsigned(), CONFIG)
        if item is None: return False
        if item['metadataMethodName'] in {e['metadataMethodName'] for e in ENTRIES}: return False
        thread = frame.GetThread()
        item.update(kind='exact-invocation-entry', pc=frame.GetPC(), nativeFilePc=CONFIG['entry']['filePc'],
                    function=frame.GetFunctionName(), nativeModule=frame.GetModule().GetFileSpec().GetFilename(),
                    pid=process.GetProcessID(), threadId=thread.GetThreadID(), hit=HITS,
                    claim='Actual initial interpreter invocation; first opcode and child reinitializations not observed.',
                    stack=[{'pc':thread.GetFrameAtIndex(i).GetPC(), 'function':thread.GetFrameAtIndex(i).GetFunctionName(),
                            'module':thread.GetFrameAtIndex(i).GetModule().GetFileSpec().GetFilename()}
                           for i in range(min(thread.GetNumFrames(), 8))])
        ENTRIES.append(item)
        save('interpreter-entries.json', ENTRIES)
        print('BATCH_DIRECT_INTERPRETER_ENTRY ' + json.dumps(item), flush=True)
        if set(CONFIG['requiredMethods']) <= {e['metadataMethodName'] for e in ENTRIES}: BP.SetEnabled(False)
    except Exception as error:
        ERRORS.append({'hit':HITS, 'pc':frame.GetPC(), 'error':str(error)})
        save('capture-errors.json', ERRORS)
        if BP is not None: BP.SetEnabled(False)
    return False

def setup():
    global BP
    target = lldb.debugger.GetSelectedTarget()
    process = target.GetProcess()
    if process.GetProcessID() != CONFIG['pid']: raise RuntimeError('Attached PID differs')
    modules = [target.GetModuleAtIndex(i) for i in range(target.GetNumModules())
               if target.GetModuleAtIndex(i).GetFileSpec().GetFilename() == 'libcoreclr.dylib']
    if len(modules) != 1: raise RuntimeError('Loaded native module ambiguous')
    module = modules[0]
    if module.GetUUIDString().replace('-', '').lower() != CONFIG['nativeUuid']:
        raise RuntimeError('Loaded native UUID differs')
    path = str(module.GetFileSpec())
    if path != CONFIG['installedNative']: raise RuntimeError('Loaded native path differs')
    for name, expected in CONFIG['layouts'].items():
        kind = target.FindFirstType(name)
        if not kind.IsValid() or kind.GetByteSize() != expected['size']:
            raise RuntimeError('Live DWARF type differs: ' + name)
        for field, value in expected['fields'].items():
            matches = [kind.GetFieldAtIndex(i) for i in range(kind.GetNumberOfFields())
                       if kind.GetFieldAtIndex(i).GetName() == field]
            if len(matches) != 1 or matches[0].GetOffsetInBytes() != value:
                raise RuntimeError('Live DWARF offset differs: ' + name + '.' + field)
    address = module.ResolveFileAddress(CONFIG['entry']['filePc'])
    symbol = address.GetSymbol()
    if not address.IsValid() or not symbol.IsValid() or symbol.GetStartAddress().GetFileAddress() != CONFIG['entry']['filePc']:
        raise RuntimeError('Exact fresh interpreter symbol entry differs')
    CONFIG['entryLoadPc'] = address.GetLoadAddress(target)
    if memory(process, CONFIG['entryLoadPc'], 64).hex() != CONFIG['entryPrefixHex']:
        raise RuntimeError('Loaded function-entry bytes differ')
    BP = target.BreakpointCreateByAddress(CONFIG['entryLoadPc'])
    if BP.GetNumLocations() != 1: raise RuntimeError('Exact interpreter entry breakpoint not unique')
    BP.SetScriptCallbackFunction('batch_entry_lldb.invocation')
    save('breakpoints.json', {'pid':CONFIG['pid'], 'nativeUuid':CONFIG['nativeUuid'],
         'symbolName':CONFIG['entry']['name'], 'filePc':CONFIG['entry']['filePc'],
         'loadPc':CONFIG['entryLoadPc'], 'prefixHex':CONFIG['entryPrefixHex'], 'locations':BP.GetNumLocations(),
         'layoutsValidated':CONFIG['layouts'], 'claim':'Exact invocation entry only; not first-opcode execution.'})

def safe_setup():
    try: setup()
    except Exception as error:
        ERRORS.append({'kind':'setup', 'error':str(error)})
        save('capture-errors.json', ERRORS)
        if BP is not None: BP.SetEnabled(False)
        lldb.debugger.GetSelectedTarget().GetProcess().Kill()
        raise

def finish():
    save('capture-hits.json', {'invocationHits':HITS, 'entries':len(ENTRIES), 'errors':len(ERRORS),
         'disabledAfterCoverage':bool(BP is not None and not BP.IsEnabled()),
         'allRequiredCovered':set(CONFIG['requiredMethods']) <= {e['metadataMethodName'] for e in ENTRIES}})
'''


def observer_source():
    # The decoder is emitted before the actual callback without importing live tools.
    return OBSERVER.replace('\ndef invocation(', DECODER + '\ndef invocation(', 1)


def verify_entries(entries, config):
    need(len(entries) == len(config['requiredMethods']) and
         {e['metadataMethodName'] for e in entries} == set(config['requiredMethods']), 'Four direct methods not covered exactly once')
    for item in entries:
        need(item['kind'] == 'exact-invocation-entry' and item['pid'] == config['pid'] and
             item['nativeFilePc'] == config['entry']['filePc'] and item['nativeModule'] == 'libcoreclr.dylib' and
             item['pc'] > 0 and item['exceptionArgs'] == 0 and item['collectible'] is True and
             item['modulePath'] == config['author']['path'] and item['moduleSimpleName'] == 'BatchBoundary.Author' and
             item['fileSha256'] == config['author']['sha256'] and item['moduleMvid'] == config['author']['moduleMvid'] and
             item['loadedMetadataMvidValidated'] is True and item['loadedPELayout'] in ('rva', 'flat') and
             item['methodDefToken'] == config['author']['methods'][item['metadataMethodName']] and
             item['bytecodeStart'] == item['methodDescBytecodeStart'] and item['bytecodeSizeSlots'] > 0 and
             len(bytes.fromhex(item['bytecodePrefixHex'])) == min(item['bytecodeSizeSlots'] * 4, 64), 'Entry identity or bytecode binding differs')
    return True


def process_command(argv, log, timeout, env=None):
    write(Path(str(log) + '.command.json'), {'argv':[str(x) for x in argv], 'timeout':timeout})
    with log.open('x') as stream:
        process = subprocess.Popen([str(x) for x in argv], stdout=stream, stderr=subprocess.STDOUT,
                                   env=env, start_new_session=True)
        write(Path(str(log) + '.process.json'), {'pid':process.pid})
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=10)
            raise
    need(code == 0, 'Command failed; preserve ' + str(log))


def execute(args):
    need(platform.system() == 'Darwin', 'Simulator capture requires the configured Mac')
    prepare = helper('ios-batch-boundary-entry-prepare.py', PREPARE_SHA)
    accepted = helper('ios-batch-boundary-accept.py', ACCEPT_SHA)
    review = helper('assess-mobile-batch-boundary.py', REVIEW_SHA)
    result = {'passed':False, 'nativeEntryProof':False, 'firstOpcodeProof':False,
              'liveBatchPathVerified':False, 'performanceMeasured':False, 'physicalDeviceVerified':False}
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    simulator, booted, launched, unified = None, False, False, None
    try:
        identity = read(args.prepare / 'identity.json'); plan = read(args.prepare / 'observer-plan.json')
        need(read(args.prepare / 'results.json')['passed'] and identity['driverSha256'] == PREPARE_SHA and
             identity['sourceCommit'] == prepare.COMMIT and identity['sourceTree'] == prepare.TREE and
             identity['sourceProofSha256'] == prepare.PROOF_SHA and identity['buildReceiptSha256'] == prepare.BUILD_SHA and
             plan['entryLane']['requiredMethods'] == list(prepare.METHODS) and
             identity['symbols']['interpreter']['name'] == prepare.SYMBOLS['interpreter'], 'Fresh accepted preparation differs')
        state = read(args.application / 'state.json'); app = Path(state['app']); app_before = inventory(app)
        manifest = accepted.inputs(args.inputs)
        need(app_before == state['bundleHashes'] and sha(args.application / 'matching-build.json') == prepare.BUILD_SHA and
             sha(args.inputs / 'input-manifest.json') == state['inputManifestSha256'], 'Frozen application binding differs')
        source_native = args.runtime / 'artifacts/bin/coreclr/iossimulator.arm64.Release/libcoreclr.dylib'
        dwarf = source_native.with_name(source_native.name + '.dwarf')
        need(sha(source_native) == prepare.SOURCE_NATIVE_SHA and sha(app / 'libcoreclr.dylib') == prepare.SIGNED_NATIVE_SHA and
             sha(dwarf) == identity['dwarfSha256'] and prepare.native(source_native) == identity['sourceNative'] and
             prepare.native(app / 'libcoreclr.dylib') == identity['signedNative'], 'Exact native/DWARF identity differs')
        need(accepted.cap(['git','-C',args.runtime,'rev-parse','HEAD']) == prepare.COMMIT and
             accepted.cap(['git','-C',args.runtime,'rev-parse','HEAD^{tree}']) == prepare.TREE and
             not accepted.cap(['git','-C',args.runtime,'status','--porcelain','--untracked-files=no']), 'Live source differs')
        proof = args.runtime.parent / 'source-proof.json'
        need(sha(proof) == prepare.PROOF_SHA and all(sha(args.runtime / n) == value for n, value in read(proof)['sourceHashes'].items()),
             'Frozen source-proof bytes differ')
        frozen = {str(p.resolve()):sha(p) for p in (args.prepare / 'identity.json', args.prepare / 'observer-plan.json',
                  args.prepare / 'results.json', args.application / 'state.json', args.inputs / 'input-manifest.json',
                  args.application / 'matching-build.json', source_native, dwarf)}
        write(output / 'request.json', {'driverSha256':sha(__file__), 'frozenInputs':frozen,
              'scope':'New independent simulator exact direct-author invocation lane; no timings or cadence.',
              'configuredInterval':1000, 'matrix':1000, 'requiredMethods':prepare.METHODS, 'timeout':args.timeout})
        simulator = accepted.cap(['xcrun','simctl','create','RuneCLR-Batch-Direct-Entry',args.device_type,args.sim_runtime])
        write(output / 'owned-simulator.json', {'id':simulator,'bundleId':state['bundleId']})
        process_command(['xcrun','simctl','boot',simulator], output / 'boot.log', 60); booted = True
        process_command(['xcrun','simctl','bootstatus',simulator,'-b'], output / 'bootstatus.log', 180)
        process_command(['xcrun','simctl','install',simulator,app], output / 'install.log', 60)
        installed = Path(accepted.cap(['xcrun','simctl','get_app_container',simulator,state['bundleId'],'app']))
        data = Path(accepted.cap(['xcrun','simctl','get_app_container',simulator,state['bundleId'],'data']))
        need(inventory(installed) == app_before, 'Separate installed signed app differs')
        plugin = data / 'Documents/batch-plugin'; plugin.mkdir(parents=True, exist_ok=False)
        for name in ('BatchBoundary.Author.dll', 'BatchBoundary.Contract.dll'):
            shutil.copy2(args.inputs / 'author' / name, plugin / name)
            need(sha(plugin / name) == manifest['files']['author/' + name] and
                 prepare.il_layout(plugin / name) == {'ilOnly':True,'managedNativeRva':0}, 'Late author IL differs')
        author_before = inventory(plugin)
        write(output / 'installed-before.json', app_before); write(output / 'author-before.json', author_before)
        nonce = uuid.uuid4().hex
        env = {k:v for k,v in os.environ.items() if not k.startswith(('DOTNET_','COMPlus_','RUNECLR_',
                'SIMCTL_CHILD_DOTNET_','SIMCTL_CHILD_COMPlus_','SIMCTL_CHILD_RUNECLR_'))}
        env.update({'SIMCTL_CHILD_RUNECLR_BATCH_NONCE':nonce,'SIMCTL_CHILD_RUNECLR_BATCH_MATRIX':'1000',
                    'SIMCTL_CHILD_RUNECLR_BATCH_HEX':'3e8'})
        process_command(['xcrun','simctl','launch','--wait-for-debugger','--stdout='+str(output / 'native.stdout.log'),
                         '--stderr='+str(output / 'native.stderr.log'),simulator,state['bundleId']], output / 'launch.log', 60, env)
        launched = True
        match = re.fullmatch(re.escape(state['bundleId']) + r': (\d+)\s*', (output / 'launch.log').read_text())
        need(match is not None, 'Owned wait-for-debugger launch PID marker differs'); pid = int(match[1])
        entry = identity['symbols']['interpreter']; section = identity['sourceNative']['sections']['__TEXT,__text']
        at = section['offset'] + entry['filePc'] - section['address']
        need(0 <= at and at + 64 <= section['offset'] + section['length'], 'Prepared entry lies outside current native text')
        author = dict(identity['boundaryAuthor']); author.update(path=str(plugin / 'BatchBoundary.Author.dll'))
        metadata = prepare.readers()
        need(author['sha256'] == sha(plugin / 'BatchBoundary.Author.dll') and
             metadata['plugin_methods'](plugin / 'BatchBoundary.Author.dll', required=prepare.METHODS, qualified=True) == author['methods'] and
             all(author[name] == value for name, value in metadata['pe_mvid'](plugin / 'BatchBoundary.Author.dll').items()),
             'Late installed hash, MethodDef ownership or MVID differs')
        config = {'pid':pid,'nonce':nonce,'author':author,'requiredMethods':list(prepare.METHODS),
                  'entry':entry,'entryPrefixHex':source_native.read_bytes()[at:at+64].hex(),
                  'layouts':{n:identity['layouts'][n] for n in ('InterpMethodContextFrame','InterpMethod','MethodDesc','MethodDescChunk','MethodTable','Module')},
                  'nativeUuid':identity['signedNative']['uuid'],'installedNative':str(installed / 'libcoreclr.dylib'), 'hitCap':100000}
        write(output / 'capture-config.json', config)
        source = observer_source(); compile(source, 'batch_entry_lldb.py', 'exec')
        (output / 'batch_entry_lldb.py').write_text(source, encoding='ascii')
        commands = ['breakpoint set -n coreclr_initialize','continue','breakpoint disable 1',
                    'target symbols add "'+str(dwarf)+'"', 'command script import "'+str(output / 'batch_entry_lldb.py')+'"',
                    'script batch_entry_lldb.safe_setup()','continue','process status','script batch_entry_lldb.finish()','quit']
        (output / 'capture.lldb').write_text(chr(10).join(commands) + chr(10), encoding='ascii')
        query = ['xcrun','simctl','spawn',simulator,'log','stream','--style','json','--predicate','processIdentifier == '+str(pid)]
        with (output / 'unified.log').open('x') as messages, (output / 'unified.stderr.log').open('x') as errors:
            unified = subprocess.Popen(query, stdout=messages, stderr=errors, start_new_session=True)
            write(output / 'unified-query.json', {'argv':query,'pid':unified.pid,'targetPid':pid})
            try:
                process_command(['xcrun','lldb','--batch','--attach-pid',str(pid),'--source',output / 'capture.lldb'], output / 'lldb.log', args.timeout)
            finally:
                if unified.poll() is None: os.killpg(unified.pid, signal.SIGINT)
                try: unified.wait(timeout=10)
                except subprocess.TimeoutExpired: os.killpg(unified.pid, signal.SIGKILL); unified.wait(timeout=10)
                write(output / 'unified-exit.json', {'pid':unified.pid,'exitCode':unified.returncode})
        hits = read(output / 'capture-hits.json'); entries = read(output / 'interpreter-entries.json')
        lldb_log = (output / 'lldb.log').read_text(errors='replace')
        need(re.search(r'^Process ' + str(pid) + r' exited with status = 0 \(0x00000000\)\s*$', lldb_log, re.M),
             'Owned target did not exit normally in debugger lane')
        need(hits['allRequiredCovered'] and hits['errors'] == 0 and hits['disabledAfterCoverage'] and
             4 <= hits['invocationHits'] <= config['hitCap'] and not (output / 'capture-errors.json').exists(), 'Observer errors or bounded coverage failure')
        breakpoint = read(output / 'breakpoints.json')
        need(breakpoint['pid'] == pid and breakpoint['filePc'] == entry['filePc'] and breakpoint['locations'] == 1 and
             breakpoint['nativeUuid'] == config['nativeUuid'] and breakpoint['prefixHex'] == config['entryPrefixHex'] and
             all(e['pc'] == breakpoint['loadPc'] for e in entries), 'Fresh loaded function-entry contract differs')
        verify_entries(entries, config)
        receipt = data / ('Documents/batch-' + nonce + '.json'); shutil.copy2(receipt, output / 'receipt.json')
        actual = read(output / 'receipt.json')
        rows = review.review_lane(actual, 1000, 1000, 'iossimulator.arm64', author_before['BatchBoundary.Author.dll'], pid, nonce)
        unified_text = (output / 'unified.log').read_text(errors='replace'); first, last = unified_text.find('['), unified_text.rfind(']')
        events = json.loads(unified_text[first:last+1]) if first >= 0 and last >= first else []
        need(isinstance(events, list) and all(e.get('processID') == pid for e in events), 'Unified log contains another process')
        log = chr(10).join((output / n).read_text(errors='replace') for n in ('native.stdout.log','native.stderr.log'))
        log += chr(10) + chr(10).join(e.get('eventMessage','') for e in events)
        (output / 'combined-native.log').write_text(log, encoding='utf-8')
        marker = f'BATCH_NATIVE pid={pid} nonce={nonce} matrix=1000 interval=3e8 PhaseAcquireLoad=1 DerivedLedger=0 InterpMode=0 ReadyToRun=1'
        need(len(re.findall('^'+re.escape(marker)+'$',log,re.M)) == 1 and
             len(re.findall(r'^CORECLR_INITIALIZE_HRESULT=0x0$',log,re.M)) == 1 and
             len(re.findall(r'^CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0$',log,re.M)) == 1 and
             accepted.completed(log, f'BATCH_BOUNDARY_COMPLETE nonce={nonce} pid={pid} N=1000 rows={len(rows)}',pid), 'Native or managed process completion markers differ')
        write(output / 'installed-after.json', inventory(installed)); write(output / 'author-after.json', inventory(plugin))
        need(inventory(installed) == app_before == inventory(app) and inventory(plugin) == author_before and
             all(sha(path) == value for path, value in frozen.items()) and accepted.inputs(args.inputs) == manifest,
             'Frozen app, author, source or preparation changed')
        result.update(passed=True, nativeEntryProof=True, directMethods=4, pid=pid, nonce=nonce,
                      rows=len(rows), collections=sum(r['Collected'] is True for r in rows),
                      sameProcessRecovery=True, configuredInterval=1000, nativeFilePc=entry['filePc'],
                      driverSha256=sha(__file__), observerSha256=sha(output / 'batch_entry_lldb.py'),
                      scope='Four sampled initial author interpreter invocations, exact fresh entry, loaded MVID/path/token and normal recovery; no first-opcode or full/partial batch cadence claim.')
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        if launched:
            cleanup = subprocess.run(['xcrun','simctl','terminate',simulator,state['bundleId']], capture_output=True, text=True)
            write(output / 'target-termination.json', {'simulator':simulator, 'exitCode':cleanup.returncode,
                  'stdout':cleanup.stdout, 'stderr':cleanup.stderr, 'note':'Already exited is acceptable only with successful HRESULT/completion evidence.'})
        if booted:
            cleanup = subprocess.run(['xcrun','simctl','shutdown',simulator], capture_output=True, text=True)
            write(output / 'cleanup.json', {'simulator':simulator,'exitCode':cleanup.returncode,'stdout':cleanup.stdout,'stderr':cleanup.stderr})
            result['cleanupSucceeded'] = cleanup.returncode == 0
            if cleanup.returncode != 0: result['passed'] = False
        result['endedUtc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        write(output / 'results.json', result); print(json.dumps(result, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime','prepare','application','inputs','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--device-type', default='com.apple.CoreSimulator.SimDeviceType.iPhone-16')
    parser.add_argument('--sim-runtime', default='com.apple.CoreSimulator.SimRuntime.iOS-27-0')
    parser.add_argument('--timeout', type=int, default=180)
    execute(parser.parse_args())


if __name__ == '__main__':
    main()
