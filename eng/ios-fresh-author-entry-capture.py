#!/usr/bin/env python3
"""Sample nine fresh-author method entries in a separate, owned simulator lane."""
import argparse
import ast
import copy
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import uuid

PREPARE_SHA = '0d93b52d36151bb3cd5c02f839b796021c0f33b4a5bdb4bb6b9f8e98cca928b8'
CONTINUATION_SHA = '53105c1f8f8321fbb7b4ae309e125f0fb30221abc62fd6eed598850afcbbda5e'
DECODER_BASE_SHA = '7190100e7e353e0090265bcfd9a6cac9df68702b4c3c335c166c525c7abb0504'
OWNER_FIELDS = {'PEAssembly': ('m_pAssemblyBinder',),
                'CustomAssemblyBinder': ('m_runeCLRInstructionMeter',)}
OWNER_LAYOUTS = {'PEAssembly': {'size': 80, 'fields': {'m_pAssemblyBinder': 72}},
                 'CustomAssemblyBinder': {'size': 344, 'fields': {'m_runeCLRInstructionMeter': 272}}}
CAPTURE_READY = False
PENDING = ['Bind and implement delegate child dispatch at the current source anchor.',
           'Bind private Helper.Finite and closure samples to terminal cleanup phase1.']
CHILD_READER = r'''import json
from pathlib import Path
import lldb
def inspect(debugger):
    root = Path(__file__).parent
    config = json.loads((root / 'child-request.json').read_text())
    target = debugger.GetSelectedTarget()
    breakpoint = target.BreakpointCreateByLocation(config['source'], config['line'])
    def row(instruction):
        error = lldb.SBError()
        data = instruction.GetData(target).ReadRawData(error, 0, instruction.GetByteSize())
        if error.Fail(): raise RuntimeError('Offline native instruction read failed')
        if isinstance(data, str): data = data.encode('latin1')
        return {'filePc': instruction.GetAddress().GetFileAddress(), 'mnemonic': instruction.GetMnemonic(target),
                'operands': instruction.GetOperands(target), 'bytesHex': data.hex()}
    locations = []
    for location in breakpoint:
        address = location.GetAddress(); pc = address.GetFileAddress(); module = address.GetModule()
        locations.append({'filePc': pc, 'line': address.GetLineEntry().GetLine(),
            'before': [row(i) for i in target.ReadInstructions(module.ResolveFileAddress(pc - 128), 32)],
            'instructions': [row(i) for i in target.ReadInstructions(address, 16)]})
    (root / 'child-offline.json').write_text(json.dumps({'targetProcessCreated': False, 'locations': locations}, indent=2))
'''


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x', encoding='ascii') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')


def query(host, out, name, argv):
    host.stage(out, name, argv, timeout=45)
    return (out / (name + '.stdout')).read_text().strip()


def helper(name, expected):
    path = Path(__file__).with_name(name)
    need(sha(path) == expected, 'Frozen helper changed: ' + name)
    spec = importlib.util.spec_from_file_location(name.replace('.', '_').replace('-', '_'), path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def replace_once(text, before, after):
    need(text.count(before) == 1, 'Frozen decoder/observer fragment not unique')
    return text.replace(before, after, 1)


def decoder_source():
    text = helper('ios-batch-boundary-entry-capture.py', DECODER_BASE_SHA).DECODER
    text = replace_once(text, "    if simple != 'BatchBoundary.Author': return None",
        "    candidates = [v for v in config['authors'].values() if v['simpleName'] == simple]\n"
        "    if not candidates: return None\n"
        "    if len(candidates) != 1: raise RuntimeError('Author simple name ambiguous')")
    text = replace_once(text, "    expected = config['author']", "    expected = candidates[0]")
    text = replace_once(text, "    if len(names) != 1: raise RuntimeError('Targeted MethodDef token absent or ambiguous')",
        "    if not names: return None\n"
        "    if len(names) != 1: raise RuntimeError('Targeted MethodDef token ambiguous')")
    text = replace_once(text, "    return {'methodContextFrame': context,",
        "    peassembly = integer(module + offset('Module', 'm_pPEAssembly'))\n"
        "    binder = integer(peassembly + offset('PEAssembly', 'm_pAssemblyBinder'))\n"
        "    if not peassembly or not binder: raise RuntimeError('Missing definition-owned binder')\n"
        "    meter = binder + offset('CustomAssemblyBinder', 'm_runeCLRInstructionMeter')\n"
        "    gate = {name: integer(meter + offset('RuneCLRInstructionMeter', field), width)\n"
        "            for name, field, width in [('terminalPrototype','m_terminalPrototype',1),\n"
        "              ('phaseAcquireLoad','m_phaseAcquireLoad',1), ('derivedLedger','m_derivedLedger',1),\n"
        "              ('batchInterval','m_batchInterval',8), ('phase','m_phase',4)]}\n"
        "    if gate != config['gate']: raise RuntimeError('Live definition-owned meter gate differs')\n"
        "    return {'methodGroup': expected['fileName'] + ':' + names[0],\n"
        "            'definitionBinder': binder, 'instructionMeter': meter, 'meterGate': gate,\n"
        "            'methodContextFrame': context,")
    return text + r'''
def decode_child(memory, frame_base, opcode, config):
    address = frame_base + config['childContract']['frameSpillOffset']
    raw = memory(address, 8)
    if len(raw) != 8: raise RuntimeError('Short child frame spill read')
    item = decode(memory, int.from_bytes(raw, 'little'), 0, config)
    if item is not None:
        if opcode != item['bytecodeStart'] + 8:
            raise RuntimeError('Child opcode pointer not at current frame bytecode start')
        item.update(firstOpcodeAddress=opcode, frameSpillAddress=address)
    return item
'''


def observer_source():
    text = helper('ios-batch-boundary-entry-capture.py', DECODER_BASE_SHA).OBSERVER
    text = text.replace('metadataMethodName', 'methodGroup')
    text = text.replace('BATCH_DIRECT_INTERPRETER_ENTRY ', 'FRESH_AUTHOR_INTERPRETER_ENTRY ')
    text = text.replace('batch_entry_lldb.invocation', 'fresh_author_entry_lldb.invocation')
    text = text.replace('ENTRIES, ERRORS = [], []', 'ENTRIES, ERRORS = [], []\nCHILD_BP = None')
    text = replace_once(text, "        if process.GetProcessID() != CONFIG['pid'] or frame.GetPC() != CONFIG['entryLoadPc']:",
        "        if process.GetProcessID() != CONFIG['pid'] or frame.GetPC() not in (CONFIG['entryLoadPc'], CONFIG['childLoadPc']):")
    text = replace_once(text, "        item = decode(lambda a, n: memory(process, a, n), frame.FindRegister('x1').GetValueAsUnsigned(),\n"
        "                      frame.FindRegister('x3').GetValueAsUnsigned(), CONFIG)",
        "        child = frame.GetPC() == CONFIG['childLoadPc']\n"
        "        if child:\n"
        "            contract = CONFIG['childContract']\n"
        "            register = frame.FindRegister(contract['frameRegister']).GetValueAsUnsigned()\n"
        "            opcode = frame.FindRegister(contract['opcodePointerRegister']).GetValueAsUnsigned()\n"
        "            item = decode_child(lambda a, n: memory(process, a, n), register, opcode, CONFIG)\n"
        "        else:\n"
        "            item = decode(lambda a, n: memory(process, a, n), frame.FindRegister('x1').GetValueAsUnsigned(),\n"
        "                          frame.FindRegister('x3').GetValueAsUnsigned(), CONFIG)")
    text = replace_once(text, "        item.update(kind='exact-invocation-entry',",
        "        if frame.GetModule().GetUUIDString().replace('-', '').lower() != CONFIG['nativeUuid']:\n"
        "            raise RuntimeError('Invocation native UUID differs')\n"
        "        item.update(nonce=CONFIG['nonce'], nativeUuid=CONFIG['nativeUuid'],\n"
        "                    nativeSlide=CONFIG['entryLoadPc']-CONFIG['entry']['filePc'],\n"
        "                    kind='child-frame-dispatch' if child else 'exact-invocation-entry',")
    text = replace_once(text, "nativeFilePc=CONFIG['entry']['filePc'],",
        "nativeFilePc=CONFIG['childContract']['filePc'] if child else CONFIG['entry']['filePc'],")
    text = replace_once(text, "claim='Actual initial interpreter invocation; first opcode and child reinitializations not observed.',",
        "claim='Actual interpreter invocation or child-frame dispatch sample; opcode execution and full coverage not established.',")
    text = replace_once(text, "if set(CONFIG['requiredMethods']) <= {e['methodGroup'] for e in ENTRIES}: BP.SetEnabled(False)",
        "if set(CONFIG['requiredMethods']) <= {e['methodGroup'] for e in ENTRIES}:\n"
        "            BP.SetEnabled(False); CHILD_BP.SetEnabled(False)")
    text = text.replace('global BP\n', 'global BP, CHILD_BP\n')
    text = replace_once(text, "    BP.SetScriptCallbackFunction('fresh_author_entry_lldb.invocation')",
        "    BP.SetScriptCallbackFunction('fresh_author_entry_lldb.invocation')\n"
        "    child = module.ResolveFileAddress(CONFIG['childContract']['filePc'])\n"
        "    CONFIG['childLoadPc'] = child.GetLoadAddress(target)\n"
        "    if memory(process, CONFIG['childLoadPc'], 64).hex() != CONFIG['childPrefixHex']:\n"
        "        raise RuntimeError('Actual loaded child dispatch bytes differ')\n"
        "    if CONFIG['childLoadPc']-CONFIG['childContract']['filePc'] != CONFIG['entryLoadPc']-CONFIG['entry']['filePc']:\n"
        "        raise RuntimeError('Child and invocation native slides differ')\n"
        "    CHILD_BP = target.BreakpointCreateByAddress(CONFIG['childLoadPc'])\n"
        "    if CHILD_BP.GetNumLocations() != 1: raise RuntimeError('Child breakpoint not unique')\n"
        "    CHILD_BP.SetScriptCallbackFunction('fresh_author_entry_lldb.invocation')")
    text = replace_once(text, "'loadPc':CONFIG['entryLoadPc'], 'prefixHex':CONFIG['entryPrefixHex'],",
        "'loadPc':CONFIG['entryLoadPc'], 'childLoadPc':CONFIG['childLoadPc'],\n"
        "         'childFilePc':CONFIG['childContract']['filePc'], 'childPrefixHex':CONFIG['childPrefixHex'],\n"
        "         'childLocations':CHILD_BP.GetNumLocations(), 'prefixHex':CONFIG['entryPrefixHex'],")
    text = text.replace("if BP is not None: BP.SetEnabled(False)",
        "if BP is not None: BP.SetEnabled(False)\n        if CHILD_BP is not None: CHILD_BP.SetEnabled(False)")
    text = replace_once(text, "'disabledAfterCoverage':bool(BP is not None and not BP.IsEnabled()),",
        "'disabledAfterCoverage':bool(BP is not None and CHILD_BP is not None and not BP.IsEnabled() and not CHILD_BP.IsEnabled()),")
    text = replace_once(text, "        lldb.debugger.GetSelectedTarget().GetProcess().Kill()",
        "        owned = lldb.debugger.GetSelectedTarget().GetProcess()\n"
        "        if owned.GetProcessID() == CONFIG['pid']: owned.Kill()")
    return replace_once(text, '\ndef invocation(', decoder_source() + '\ndef invocation(')


def verify_entries(entries, config, breakpoint):
    need(len(entries) == 9 and {e['methodGroup'] for e in entries} == set(config['requiredMethods']),
         'Nine method groups not covered exactly once')
    for item in entries:
        file_name, method_name = item['methodGroup'].split(':', 1); author = config['authors'][file_name]
        child = item['kind'] == 'child-frame-dispatch'
        need(item['kind'] in ('child-frame-dispatch', 'exact-invocation-entry'), 'Unknown sample kind')
        if child:
            need(item['firstOpcodeAddress'] == item['bytecodeStart'] + 8 and item['frameSpillAddress'] > 0, 'Child bytecode/frame binding differs')
        need(item['pid'] == config['pid'] and item['nonce'] == config['nonce']
             and item['pc'] == breakpoint['childLoadPc' if child else 'loadPc']
             and item['nativeFilePc'] == (config['childContract']['filePc'] if child else config['entry']['filePc'])
             and item['nativeUuid'] == config['nativeUuid']
             and item['nativeSlide'] == breakpoint['loadPc'] - config['entry']['filePc']
             and item['nativeModule'] == 'libcoreclr.dylib'
             and item['exceptionArgs'] == 0 and item['collectible'] is True
             and item['modulePath'] == author['path'] and item['moduleSimpleName'] == author['simpleName']
             and item['fileSha256'] == author['sha256'] and item['moduleMvid'] == author['moduleMvid']
             and item['loadedMetadataMvidValidated'] is True and item['loadedPELayout'] in ('rva', 'flat')
             and item['metadataMethodName'] == method_name and item['methodDefToken'] == author['methods'][method_name]
             and item['bytecodeStart'] == item['methodDescBytecodeStart'] and item['bytecodeSizeSlots'] > 0
             and len(bytes.fromhex(item['bytecodePrefixHex'])) == min(item['bytecodeSizeSlots'] * 4, 64)
             and item['definitionBinder'] != 0
             and item['instructionMeter'] == item['definitionBinder'] + OWNER_LAYOUTS['CustomAssemblyBinder']['fields']['m_runeCLRInstructionMeter']
             and item['meterGate'] == config['gate'], 'Sample PID/PC/module/bytecode/owner/gate differs')
    return True


def frozen(args):
    prepare = helper('ios-fresh-author-entry-prepare.py', PREPARE_SHA)
    continuation = helper('ios-fresh-author-simulator-continuation.py', CONTINUATION_SHA)
    identity = read(args.prepare / 'identity.json'); result = read(args.prepare / 'results.json')
    need(result['passed'] and result['driverSha256'] == PREPARE_SHA, 'Frozen offline preparation differs')
    prepare.validate_contract(identity)
    state = continuation.verify_state(args.application)
    source = args.runtime / 'artifacts/bin/coreclr/iossimulator.arm64.Release/libcoreclr.dylib'
    dwarf = source.with_name(source.name + '.dwarf')
    pe = prepare.readers()
    need(pe['native'](source) == identity['sourceNative']
         and pe['native'](Path(state['app']) / source.name) == identity['signedNative']
         and sha(dwarf) == identity['dwarfSha256'], 'Matching native/DWARF changed')
    need(sha(args.application / 'state.json') == prepare.STATE_SHA
         and sha(args.application / 'run-all/results.json') == prepare.ACCEPTANCE_SHA, 'Normal app receipts changed')
    return prepare, continuation, identity, state, source, dwarf


def child_contract(args, out, prepare, native, dwarf):
    source = args.runtime / 'src/coreclr/vm/interpexec.cpp'; lines = source.read_text().splitlines()
    anchors = [i for i, line in enumerate(lines) if '// Set execution state for the new frame' in line
        and 'pMethod = pFrame->startIp->Method;' in lines[i + 1]
        and 'if (stack + pMethod->allocaSize' in '\n'.join(lines[i:i + 10])]
    need(len(anchors) == 1, 'Current child ReInit dispatch source anchor not unique')
    dispatch = [i + 1 for i in range(anchors[0], anchors[0] + 20) if 'INTOP_NEXT;' in lines[i]]
    need(len(dispatch) == 1, 'Current child dispatch line not unique')
    proof = read(args.application / 'source-proof.json')
    need(sha(source) == proof['sourceHashes']['src/coreclr/vm/interpexec.cpp'], 'Current child source hash differs')
    write(out / 'child-request.json', {'source': str(source), 'line': dispatch[0], 'sourceSha256': sha(source), 'offlineOnly': True})
    (out / 'child_offline_reader.py').write_text(CHILD_READER, encoding='ascii')
    prepare.command(['xcrun', 'lldb', '--batch', '--no-lldbinit', '-o', 'target create "' + str(native) + '"',
        '-o', 'target symbols add "' + str(dwarf) + '"', '-o', 'script import sys; sys.path.insert(0, ' + repr(str(out)) + ')',
        '-o', 'script import child_offline_reader; child_offline_reader.inspect(lldb.debugger)'], out, 'child-offline-lldb')
    observed = read(out / 'child-offline.json')
    need(observed['targetProcessCreated'] is False and len(observed['locations']) == 1, 'Current native child dispatch not unique')
    contract = observed['locations'][0]; need(contract['line'] == dispatch[0], 'Child source line differs')
    pe = prepare.readers(); native_identity = pe['native'](native); section = native_identity['sections']['__TEXT,__text']
    image = native.read_bytes()
    for rows in (contract['before'], contract['instructions']):
        for index, row in enumerate(rows):
            at = section['offset'] + row['filePc'] - section['address']
            need(section['offset'] <= at and at + 4 <= section['offset'] + section['length']
                 and len(row['bytesHex']) == 8 and image[at:at + 4] == bytes.fromhex(row['bytesHex'])
                 and (index == 0 or row['filePc'] == rows[index - 1]['filePc'] + 4), 'Actual child code window differs')
    opcode = re.fullmatch(r'(w\d+), \[(x\d+)\]', contract['instructions'][0]['operands'])
    need(contract['instructions'][0]['mnemonic'] == 'ldr' and opcode, 'Review actual child opcode dispatch instruction')
    raw = prepare.command(['xcrun', 'dwarfdump', '--name=pFrame', dwarf], out, 'child-pframe-dwarf')
    spills = set()
    for block in raw.split('\n\n'):
        if 'interpexec.cpp' not in block: continue
        for match in re.finditer(r'\[0x([0-9a-f]+), 0x([0-9a-f]+)\): DW_OP_breg(\d+) W\d+\+(\d+)', block):
            spills.add((int(match[1], 16), int(match[2], 16),
                        'sp' if match[3] == '31' else 'x' + match[3], int(match[4])))
    headers = [r for r in contract['before'] if r['mnemonic'] == 'ldr'
        and re.fullmatch(r'x\d+, \[' + re.escape(opcode[2]) + r'\], #0x8', r['operands'])]
    need(len(headers) == 1, 'Current child bytecode-header skip not unique')
    matches = [s for s in spills if s[0] <= headers[0]['filePc'] < s[1]]
    need(len(matches) == 1, 'Current contextual pFrame DWARF interval not unique')
    start, end, register, offset = matches[0]
    stores = [r for r in contract['before'] if r['mnemonic'] == 'str' and
        re.fullmatch(r'x\d+, \[' + re.escape(register) + r', #0x' + format(offset, 'x') + r'\]', r['operands'])]
    reloads = [r for r in contract['instructions'][:8] if r['mnemonic'] == 'ldr' and
        re.fullmatch(r'x\d+, \[' + re.escape(register) + r', #0x' + format(offset, 'x') + r'\]', r['operands'])]
    need(len(stores) == len(reloads) == 1 and stores[0]['filePc'] < headers[0]['filePc'], 'Actual pFrame spill/store/reload sequence differs')
    between = [r for r in contract['before'] if r['filePc'] > stores[0]['filePc']]
    writes = []
    for row in between:
        operands = row['operands']; mnemonic = row['mnemonic']
        first = operands.split(',', 1)[0]
        target = first in (register, register.replace('x', 'w', 1))
        branch = mnemonic in ('b', 'bl', 'br', 'blr', 'cbz', 'cbnz', 'tbz', 'tbnz') or mnemonic.startswith('b.')
        if ((target and not branch and not mnemonic.startswith(('str', 'stp', 'stur', 'cmp', 'cmn', 'tst')))
                or (('[' + register + ',') in operands and (']!' in operands or '], ' in operands))):
            writes.append(row)
    need(not writes, 'Contextual frame register is overwritten before child capture PC')
    contract.update(frameRegister=register, frameSpillOffset=offset, opcodeRegister=opcode[1],
        opcodePointerRegister=opcode[2], frameStore=stores[0], frameReload=reloads[0], headerSkip=headers[0],
        contextualDwarf={'start': start, 'end': end, 'register': register, 'offset': offset},
        pFrameDwarfCoversCapturePc=start <= contract['filePc'] < end, liveRegisterContentsVerified=False,
        frameRegisterStableAfterStore=True, checkedFrameRegisterWindow=between,
        sourceSha256=sha(source), targetProcessCreated=False)
    return contract


def plan(args):
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    prepare, _, identity, state, source, dwarf = frozen(args)
    pe = prepare.readers(); pe['dwarf_layout'].__globals__['FIELDS'] = OWNER_FIELDS
    layouts = {}
    for name in OWNER_FIELDS:
        raw = prepare.command(['xcrun', 'dwarfdump', '--name=' + name, '--show-children', '--recurse-depth=1', dwarf], out, name)
        layouts[name] = pe['dwarf_layout'](raw, name)
    need(layouts == OWNER_LAYOUTS, 'Actual owner-chain DWARF differs')
    owner_source = args.runtime / 'src/coreclr/binder/inc/customassemblybinder.h'
    need('&m_runeCLRInstructionMeter' in owner_source.read_text(), 'Definition-owned embedded meter source differs')
    child = child_contract(args, out, prepare, source, dwarf)
    source = observer_source(); ast.parse(source, feature_version=(3, 9))
    (out / 'observer-draft.py').write_text(source, encoding='ascii')
    write(out / 'request.json', {'driverSha256': sha(__file__), 'prepareDriverSha256': PREPARE_SHA,
        'continuationSha256': CONTINUATION_SHA, 'decoderBaseSha256': DECODER_BASE_SHA,
        'prepare': str(args.prepare.resolve()), 'prepareIdentitySha256': sha(args.prepare / 'identity.json'),
        'application': str(args.application.resolve()), 'stateSha256': sha(args.application / 'state.json'),
        'runtime': str(args.runtime.resolve()), 'dwarfSha256': identity['dwarfSha256'],
        'ownerLayouts': layouts, 'ownerSourceSha256': sha(owner_source), 'nativeEntry': identity['symbol'],
        'childContract': child,
        'observerSha256': hashlib.sha256(source.encode('ascii')).hexdigest(),
        'captureReady': CAPTURE_READY, 'pending': PENDING,
        'requiredMethodGroups': identity['requiredMethods'], 'gate': identity['gate'],
        'timeoutSeconds': args.timeout, 'hitCap': 100000, 'physicalDeviceExecuted': False,
        'normalReceiptUnchanged': True, 'targetProcessCreated': False})
    write(out / 'results.json', {'passed': True, 'phase': 'plan', 'nativeEntryProof': False,
        'targetProcessCreated': False, 'physicalDeviceExecuted': False, 'ownerDwarfBound': True,
        'requiredMethods': 9, 'driverSha256': sha(__file__)})


def install(args):
    prepare, host, identity, state, _, _ = frozen(args); out = args.output.resolve()
    request = read(out / 'request.json')
    need(request['driverSha256'] == sha(__file__) and read(out / 'results.json')['passed'], 'Plan must match this frozen driver')
    need(request['captureReady'] and CAPTURE_READY, 'Offline draft only: delegate child/cleanup-phase contracts pending')
    dest = out / 'installation'; dest.mkdir()
    try:
        host.stage(dest, 'create', ['xcrun', 'simctl', 'create', 'RuneCLR-Fresh-Author-Entry', args.device_type, args.sim_runtime], timeout=60)
        simulator = (dest / 'create.stdout').read_text().strip(); need(re.fullmatch(r'[0-9A-F-]{36}', simulator), 'Owned simulator UUID differs')
        write(out / 'owned-simulator.json', {'id': simulator, 'bundleId': state['bundleId']})
        host.stage(dest, 'boot', ['xcrun', 'simctl', 'boot', simulator], timeout=60)
        host.stage(dest, 'bootstatus', ['xcrun', 'simctl', 'bootstatus', simulator, '-b'], timeout=180)
        host.stage(dest, 'install', ['xcrun', 'simctl', 'install', simulator, state['app']], timeout=120)
        installed = Path(query(host, dest, 'app-container', ['xcrun', 'simctl', 'get_app_container', simulator, state['bundleId'], 'app']))
        data = Path(query(host, dest, 'data-container', ['xcrun', 'simctl', 'get_app_container', simulator, state['bundleId'], 'data']))
        need(simulator in str(installed) and simulator in str(data), 'Container paths must belong to the owned simulator')
        need(host.inventory(installed) == state['bundleHashes'] and not (data / 'Documents/budget-plugin').exists(),
             'Diagnostic installation not byte-identical or author absent')
        write(dest / 'results.json', {'passed': True, 'simulator': simulator, 'installedApp': str(installed),
            'dataContainer': str(data), 'authorDirectoryAbsent': True, 'readbackUtc': host.utc(),
            'stateSha256': sha(args.application / 'state.json'), 'driverSha256': sha(__file__),
            'physicalDeviceInstalled': False, 'appLaunched': False})
    except Exception:
        if (out / 'owned-simulator.json').exists(): retire(args, 'installation-error')
        raise


def retire(args, label):
    host = helper('ios-fresh-author-simulator-continuation.py', CONTINUATION_SHA)
    out = args.output.resolve(); dest = out / label; dest.mkdir()
    host.retire_owned(out, dest, label)
    owned = read(out / 'owned-simulator.json')
    host.stage(dest, 'delete', ['xcrun', 'simctl', 'delete', owned['id']], timeout=120)
    listing = json.loads(query(host, dest, 'devices-list', ['xcrun', 'simctl', 'list', 'devices', '--json']))
    write(dest / 'devices-after.json', listing)
    need(not any(x['udid'] == owned['id'] for group in listing['devices'].values() for x in group), 'Owned simulator survived retirement')
    write(dest / 'results.json', {'passed': True, 'deleted': True, 'simulator': owned['id'], 'physicalDeviceChanged': False})


def run(args):
    out = args.output.resolve(); dest = out / 'diagnostic'; dest.mkdir(); nonce = uuid.uuid4().hex
    result = {'passed': False, 'debugger': True, 'launchCount': 1, 'nonce': nonce,
              'nativeEntryProof': False, 'firstOpcodeProof': False, 'performanceMeasured': False,
              'physicalDeviceExecuted': False, 'driverSha256': sha(__file__)}
    try:
        prepare, host, identity, state, source, dwarf = frozen(args)
        request = read(out / 'request.json'); installation = read(out / 'installation/results.json')
        need(request['driverSha256'] == sha(__file__) and installation['passed'], 'Frozen plan/installation required')
        need(request['captureReady'] and CAPTURE_READY, 'Offline draft only: delegate child/cleanup-phase contracts pending')
        need(args.timeout == request['timeoutSeconds'], 'Diagnostic timeout must match its frozen plan')
        authors = args.authors.resolve(); compiled = read(authors / 'results.json')
        need(compiled['passed'] and compiled['authorCompilationCount'] == 2 and compiled['authorIlOnly']
             and datetime.fromisoformat(compiled['startedAfterHostBindingUtc']) > datetime.fromisoformat(installation['readbackUtc']),
             'New compilation must follow diagnostic install readback')
        shutil.copytree(authors, dest / 'author-compilation')
        installed, data = Path(installation['installedApp']), Path(installation['dataContainer'])
        simulator = installation['simulator']
        need(host.inventory(installed) == state['bundleHashes'], 'Installed bundle changed')
        plugin = data / 'Documents/budget-plugin'; plugin.mkdir(parents=True, exist_ok=False)
        pe = prepare.readers(); module_rows = {}
        for name, old in identity['modules'].items():
            path = authors / 'plugin' / name
            need(sha(path) == compiled['authorHashes'][name] and sha(path) != old['sha256'], 'New compiler/file identity required')
            layout = pe['il_layout'](path); need(layout == {'ilOnly': True, 'managedNativeRva': 0}, 'Author IL-only header differs')
            methods = pe['plugin_methods'](path, required=tuple(old['methods']), qualified=True)
            module_rows[name] = {'fileName': name, 'simpleName': name[:-4], 'sha256': sha(path),
                'layout': layout, 'methods': {n: methods[n] for n in old['methods']},
                'path': str(plugin / name), **pe['pe_mvid'](path)}
            need(module_rows[name]['moduleMvid'] != old['moduleMvid'], 'New author MVID required')
            shutil.copyfile(path, plugin / name)
        before = {'bundle': host.inventory(installed), 'author': host.inventory(plugin)}
        need(before['author'] == compiled['authorHashes'], 'Installed new author bytes differ')
        write(dest / 'installed-before.json', before)
        write(dest / 'transfer.json', {'endedUtc': host.utc(), 'authorHashes': before['author'],
            'compilerResultSha256': sha(authors / 'results.json'), 'installReceiptSha256': sha(out / 'installation/results.json')})
        env = {k: v for k, v in os.environ.items() if not k.startswith('SIMCTL_CHILD_')}
        env['SIMCTL_CHILD_RUNECLR_BUDGET_NONCE'] = nonce
        host.stage(dest, 'wait-launch', ['xcrun', 'simctl', 'launch', '--wait-for-debugger',
            '--stdout=' + str(dest / 'native.stdout'), '--stderr=' + str(dest / 'native.stderr'),
            simulator, state['bundleId']], env, 60)
        matched = re.fullmatch(re.escape(state['bundleId']) + r': (\d+)\s*', (dest / 'wait-launch.stdout').read_text())
        need(matched is not None, 'Exact owned target launch PID marker differs'); pid = int(matched[1])
        result['pid'] = pid
        section = identity['sourceNative']['sections']['__TEXT,__text']; entry = identity['symbol']
        position = section['offset'] + entry['filePc'] - section['address']
        need(section['offset'] <= position and position + 64 <= section['offset'] + section['length'], 'Prepared native entry outside text')
        config = {'pid': pid, 'nonce': nonce, 'authors': module_rows, 'requiredMethods': identity['requiredMethods'],
            'gate': identity['gate'], 'layouts': dict(identity['layouts'], **request['ownerLayouts']),
            'entry': entry, 'entryPrefixHex': source.read_bytes()[position:position + 64].hex(),
            'nativeUuid': identity['signedNative']['uuid'], 'installedNative': str(installed / 'libcoreclr.dylib'),
            'hitCap': 100000}
        child = request['childContract']; child_at = section['offset'] + child['filePc'] - section['address']
        need(section['offset'] <= child_at and child_at + 64 <= section['offset'] + section['length'], 'Prepared child dispatch outside text')
        config.update(childContract=child, childPrefixHex=source.read_bytes()[child_at:child_at + 64].hex())
        write(dest / 'capture-config.json', config)
        observer = observer_source(); need(hashlib.sha256(observer.encode('ascii')).hexdigest() == request['observerSha256'], 'Frozen observer changed')
        (dest / 'fresh_author_entry_lldb.py').write_text(observer, encoding='ascii')
        commands = ['breakpoint set -n coreclr_initialize', 'continue', 'breakpoint disable 1',
            'target symbols add "' + str(dwarf) + '"', 'command script import "' + str(dest / 'fresh_author_entry_lldb.py') + '"',
            'script fresh_author_entry_lldb.safe_setup()', 'continue', 'process status',
            'script fresh_author_entry_lldb.finish()', 'quit']
        (dest / 'capture.lldb').write_text('\n'.join(commands) + '\n', encoding='ascii')
        host.stage(dest, 'lldb', ['xcrun', 'lldb', '--batch', '--no-lldbinit', '--attach-pid', str(pid), '--source', dest / 'capture.lldb'],
                   timeout=args.timeout, before_timeout_retire=lambda: host.retire_owned(out, dest, 'timeout'))
        hits = read(dest / 'capture-hits.json'); breakpoint = read(dest / 'breakpoints.json')
        need(hits['allRequiredCovered'] and hits['errors'] == 0 and hits['entries'] == 9
             and hits['disabledAfterCoverage'] and 9 <= hits['invocationHits'] <= config['hitCap']
             and not (dest / 'capture-errors.json').exists(), 'Diagnostic coverage failed')
        need(breakpoint['pid'] == pid and breakpoint['nativeUuid'] == config['nativeUuid']
             and breakpoint['filePc'] == entry['filePc'] and breakpoint['locations'] == 1
             and breakpoint['prefixHex'] == config['entryPrefixHex']
             and breakpoint['childLocations'] == 1 and breakpoint['childFilePc'] == child['filePc']
             and breakpoint['childPrefixHex'] == config['childPrefixHex'], 'Native breakpoint identity differs')
        verify_entries(read(dest / 'interpreter-entries.json'), config, breakpoint)
        need(re.search(r'^Process ' + str(pid) + r' exited with status = 0 \(0x00000000\)\s*$',
                       (dest / 'lldb.stdout').read_text(), re.M), 'Owned target debugger exit status differs')
        evidence = data / 'Documents' / ('budget-evidence-' + nonce); shutil.copytree(evidence, dest / 'adapter-evidence')
        adapter = read(dest / 'adapter-evidence/result.json')
        need(adapter['passed'] and adapter['processId'] == pid and adapter['nonce'] == nonce
             and adapter['contexts'] == 73 and len(adapter['cases']) == 15, 'Diagnostic managed aggregate differs')
        rows = []
        for item in adapter['cases']:
            path = dest / 'adapter-evidence' / item['receipt']; child = read(path)
            need(sha(path) == item['receiptSha256'] and child['passed'] and child['nonce'] == item['nonce'], 'Diagnostic child receipt binding differs')
            rows.extend(child['rows'])
        need(len(rows) == 73 and all(x['collected'] for x in rows), 'Diagnostic context collection differs')
        log = (dest / 'native.stdout').read_text() + '\n' + (dest / 'native.stderr').read_text()
        markers = [f'FRESH_AUTHOR_SIM_NATIVE pid={pid} nonce={nonce} PhaseAcquireLoad=1 DerivedLedger=1 BatchInterval=0 InterpMode=0 InterpretCollectible=0 ReadyToRun=1',
            f'FRESH_AUTHOR_SIM_INITIALIZE pid={pid} nonce={nonce} hr=0',
            f'FRESH_AUTHOR_SIM_CREATE_DELEGATE pid={pid} nonce={nonce} hr=0',
            f'FRESH_AUTHOR_SIM_INVOKE pid={pid} nonce={nonce} managedExit=0',
            f'FRESH_AUTHOR_SIM_SHUTDOWN pid={pid} nonce={nonce} attempted=false reason=template-exit-path',
            f'FRESH_AUTHOR_SIM_EXIT pid={pid} nonce={nonce} managedExit=0 actualExit=0']
        need(all(host.exact_marker(log, marker, pid) for marker in markers), 'Diagnostic native completion marker differs')
        after = {'bundle': host.inventory(installed), 'author': host.inventory(plugin)}; write(dest / 'installed-after.json', after)
        need(before == after and host.inventory(Path(state['app'])) == state['bundleHashes'], 'Frozen/installed bundle or authors changed')
        result.update(passed=True, nativeEntryProof=True, methodGroups=9, contexts=73, cases=15,
            debuggerTargetExitStatus=0, actualTargetExitObservedByDebugger=True,
            nativeManagedExitMarker=0, nativeActualExitMarker=0, lldbExitIsNotTargetExit=True,
            authorCompiledAfterDiagnosticInstallation=True, observerSha256=request['observerSha256'])
    except Exception as error:
        result['error'] = str(error); raise
    finally:
        try:
            retire(args, 'cleanup'); result['cleanupSucceeded'] = True
        except Exception as error:
            result['cleanupSucceeded'] = False; result['cleanupError'] = str(error); result['passed'] = False
        write(dest / 'results.json', result); print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('plan', 'install', 'run', 'cleanup'))
    for name in ('prepare', 'application', 'runtime', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--authors', type=Path)
    parser.add_argument('--device-type', default='com.apple.CoreSimulator.SimDeviceType.iPhone-16')
    parser.add_argument('--sim-runtime', default='com.apple.CoreSimulator.SimRuntime.iOS-27-0')
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args(); need(platform.system() == 'Darwin', 'Simulator tool requires the configured Mac')
    need(30 <= args.timeout <= 600, 'Diagnostic timeout must be between 30 and 600 seconds')
    if args.phase == 'plan': plan(args)
    elif args.phase == 'install': install(args)
    elif args.phase == 'cleanup': retire(args, 'manual-cleanup')
    else:
        need(args.authors is not None, '--authors required for diagnostic run'); run(args)


if __name__ == '__main__':
    main()
