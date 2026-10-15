#!/usr/bin/env python3
"""Prepare and sample phase-aware function, ordinary-child and delegate-child entries."""
import argparse
import ast
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

OLD_SHA = 'bc922779f4a64b83ca69b6b5dd1f13a9f842277e9b7f60226910508c6f1d779a'
CAPTURE_READY = False
PENDING = ['Bind live delegate child dispatch bytes/register contract.',
           'Bind private Helper.Finite and closure samples to cleanup phase1.']
PRIVATE_PHASE1 = {
    'HostBudgetProbe.Private.dll:HostBudgetUGC.Private.Helper.Finite',
    'HostBudgetProbe.Private.dll:<>c__DisplayClass0_0.<Finite>b__0',
}
PATH_KINDS = ('function-entry', 'ordinary-child-dispatch', 'delegate-child-dispatch')


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


def receipt_prefix(path, fallback):
    """Read a bounded native prefix from a frozen disassembly receipt."""
    if Path(path).is_file():
        text = Path(path).read_text(encoding='utf-8', errors='replace')
        words = []
        for line in text.splitlines():
            match = re.match(r'^\s*[0-9a-f]+:\s+((?:[0-9a-f]{8}\s*)+)', line, re.I)
            if match:
                words.extend(re.findall(r'[0-9a-f]{8}', match.group(1), re.I))
                if len(words) >= 16:
                    return ''.join(words[:16]).lower()
    return fallback


def old():
    path = Path(__file__).with_name('ios-fresh-author-entry-capture.py')
    need(sha(path) == OLD_SHA, 'Frozen previous draft differs')
    spec = importlib.util.spec_from_file_location('previous_fresh_capture', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def decoder_source():
    previous = old(); text = previous.decoder_source().split('\ndef decode_child(', 1)[0]
    text = previous.replace_once(text, "    if gate != config['gate']: raise RuntimeError('Live definition-owned meter gate differs')",
        "    group = expected['fileName'] + ':' + names[0]\n"
        "    expected_gate = dict(config['gate'], phase=config['methodPhases'][group])\n"
        "    if gate != expected_gate: raise RuntimeError('Live method-specific meter gate differs')")
    return text + r'''

def bind_thread(memory, item, thread_context, config):
    if item is None: return None
    if not thread_context: raise RuntimeError('Missing actual interpreter thread context')
    offset = config['layouts']['InterpThreadContext']['fields']['runeclrCleanupOwner']
    raw = memory(thread_context + offset, 8)
    if len(raw) != 8: raise RuntimeError('Short cleanup-owner read')
    owner = int.from_bytes(raw, 'little')
    phase = config['methodPhases'][item['methodGroup']]
    expected = item['instructionMeter'] if phase == 1 else 0
    if owner != expected: raise RuntimeError('Current cleanup owner does not match method definition owner/phase')
    item.update(threadContext=thread_context, cleanupOwner=owner, terminalPhase=phase,
                meterTerminated=(phase != 0), terminationSignal='execution-limit' if phase else 'none')
    return item

def decode_child(memory, frame_base, opcode_register_value, contract, config):
    def integer(address):
        raw = memory(address, 8)
        if len(raw) != 8: raise RuntimeError('Short child-frame/thread-context read')
        return int.from_bytes(raw, 'little')
    frame_address = frame_base + contract['frameSpillOffset']
    item = decode(memory, integer(frame_address), 0, config)
    if item is None: return None
    opcode = opcode_register_value + contract['opcodeAddressAdvance']
    if opcode != item['bytecodeStart'] + 8: raise RuntimeError('Child opcode pointer differs from its current frame')
    thread_context = integer(frame_base + config['threadContract']['rawSpillOffset'])
    stack_slot = integer(frame_base + config['threadContract']['stackPointerAddressSpillOffset'])
    if stack_slot != thread_context + config['layouts']['InterpThreadContext']['fields']['pStackPointer']:
        raise RuntimeError('Raw thread-context spill and derived stack-pointer address disagree')
    item.update(firstOpcodeAddress=opcode, opcodeRegisterValue=opcode_register_value,
        opcodeAddressAdvance=contract['opcodeAddressAdvance'], frameSpillAddress=frame_address,
        threadContextSpillAddress=frame_base+config['threadContract']['rawSpillOffset'],
        threadStackPointerAddress=stack_slot)
    return bind_thread(memory, item, thread_context, config)
'''


OBSERVER = r'''import json
from pathlib import Path
import lldb
OUT = Path(__file__).parent
CONFIG = json.loads((OUT / 'capture-config.json').read_text())
ENTRIES, ERRORS, BREAKPOINTS, LOAD_PCS = [], [], {}, {}
HITS = 0

def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + chr(10))

def memory(process, address, size):
    error = lldb.SBError(); value = process.ReadMemory(address, size, error)
    if error.Fail() or len(value) != size: raise RuntimeError('Bounded actual memory read failed: '+str(error))
    return value

def disable_all():
    for breakpoint in BREAKPOINTS.values(): breakpoint.SetEnabled(False)

def invocation(frame, location, internal):
    global HITS
    HITS += 1; process = frame.GetThread().GetProcess()
    try:
        if HITS > CONFIG['hitCap']: raise RuntimeError('Bounded hit cap exceeded')
        if process.GetProcessID() != CONFIG['pid']: raise RuntimeError('Owned process PID differs')
        paths = [name for name, value in LOAD_PCS.items() if value == frame.GetPC()]
        if len(paths) != 1: raise RuntimeError('Actual sample PC is not one exact prepared entry')
        kind = paths[0]; contract = CONFIG['paths'][kind]
        if frame.GetModule().GetUUIDString().replace('-', '').lower() != CONFIG['nativeUuid']:
            raise RuntimeError('Actual sample native UUID differs')
        if kind == 'function-entry':
            item = decode(lambda a,n:memory(process,a,n), frame.FindRegister('x1').GetValueAsUnsigned(),
                          frame.FindRegister('x3').GetValueAsUnsigned(), CONFIG)
            item = bind_thread(lambda a,n:memory(process,a,n), item, frame.FindRegister('x2').GetValueAsUnsigned(), CONFIG)
        else:
            item = decode_child(lambda a,n:memory(process,a,n),
                frame.FindRegister(contract['frameRegister']).GetValueAsUnsigned(),
                frame.FindRegister(contract['opcodePointerRegister']).GetValueAsUnsigned(), contract, CONFIG)
        if item is None or item['methodGroup'] in {e['methodGroup'] for e in ENTRIES}: return False
        thread = frame.GetThread(); target = process.GetTarget()
        item.update(kind=kind, pid=process.GetProcessID(), nonce=CONFIG['nonce'], pc=frame.GetPC(),
            nativeFilePc=contract['filePc'], nativeSlide=LOAD_PCS[kind]-contract['filePc'],
            nativeUuid=CONFIG['nativeUuid'], nativeModule=frame.GetModule().GetFileSpec().GetFilename(),
            nativePath=str(frame.GetModule().GetFileSpec()), threadId=thread.GetThreadID(), hit=HITS,
            claim='Selected interpreter entry/child dispatch sample; opcode execution and complete invocation tracing are not established.',
            stack=[{'pc':thread.GetFrameAtIndex(i).GetPC(),'function':thread.GetFrameAtIndex(i).GetFunctionName(),
                    'module':thread.GetFrameAtIndex(i).GetModule().GetFileSpec().GetFilename()}
                   for i in range(min(thread.GetNumFrames(),8))])
        ENTRIES.append(item); save('interpreter-entries.json',ENTRIES)
        print('FRESH_AUTHOR_V2_ENTRY '+json.dumps(item),flush=True)
        if set(CONFIG['requiredMethods']) == {e['methodGroup'] for e in ENTRIES}: disable_all()
    except Exception as error:
        ERRORS.append({'hit':HITS,'pc':frame.GetPC(),'error':str(error)}); save('capture-errors.json',ERRORS); disable_all()
    return False

def setup():
    target = lldb.debugger.GetSelectedTarget(); process = target.GetProcess()
    if process.GetProcessID()!=CONFIG['pid']: raise RuntimeError('Attached PID differs')
    modules = [target.GetModuleAtIndex(i) for i in range(target.GetNumModules())
               if target.GetModuleAtIndex(i).GetFileSpec().GetFilename()=='libcoreclr.dylib']
    if len(modules)!=1: raise RuntimeError('Actual runtime native module ambiguous')
    module=modules[0]
    if module.GetUUIDString().replace('-','').lower()!=CONFIG['nativeUuid'] or str(module.GetFileSpec())!=CONFIG['installedNative']:
        raise RuntimeError('Actual runtime UUID/path differs')
    for name,expected in CONFIG['layouts'].items():
        kind=target.FindFirstType(name)
        if not kind.IsValid() or kind.GetByteSize()!=expected['size']: raise RuntimeError('Live DWARF type differs: '+name)
        for field,offset in expected['fields'].items():
            matches=[kind.GetFieldAtIndex(i) for i in range(kind.GetNumberOfFields()) if kind.GetFieldAtIndex(i).GetName()==field]
            if len(matches)!=1 or matches[0].GetOffsetInBytes()!=offset: raise RuntimeError('Live DWARF field differs: '+name+'.'+field)
    details={}; slides=set()
    for name,contract in CONFIG['paths'].items():
        address=module.ResolveFileAddress(contract['filePc']); pc=address.GetLoadAddress(target)
        if not address.IsValid() or pc==lldb.LLDB_INVALID_ADDRESS: raise RuntimeError('Prepared native PC not loaded')
        if name=='function-entry':
            symbol=address.GetSymbol()
            if not symbol.IsValid() or symbol.GetStartAddress().GetFileAddress()!=contract['filePc']:
                raise RuntimeError('Exact interpreter function entry differs')
        else:
            line=address.GetLineEntry()
            if not line.IsValid() or line.GetLine()!=contract['line'] or str(line.GetFileSpec())!=CONFIG['sourcePath']:
                raise RuntimeError('Actual child source line/path differs')
        if memory(process,pc,64).hex()!=contract['prefixHex']: raise RuntimeError('Loaded native code window differs')
        breakpoint=target.BreakpointCreateByAddress(pc); BREAKPOINTS[name]=breakpoint; LOAD_PCS[name]=pc
        if breakpoint.GetNumLocations()!=1: raise RuntimeError('Exact breakpoint ambiguous')
        breakpoint.SetScriptCallbackFunction('fresh_author_entry_v2_lldb.invocation')
        slides.add(pc-contract['filePc'])
        details[name]={'loadPc':pc,'filePc':contract['filePc'],'prefixHex':contract['prefixHex'],'locations':breakpoint.GetNumLocations()}
    if len(slides)!=1 or len(BREAKPOINTS)!=3: raise RuntimeError('Three-path native slide/coverage differs')
    save('breakpoints.json',{'pid':CONFIG['pid'],'nativeUuid':CONFIG['nativeUuid'],'paths':details,'layoutsValidated':CONFIG['layouts']})

def safe_setup():
    try: setup()
    except Exception as error:
        ERRORS.append({'kind':'setup','error':str(error)}); save('capture-errors.json',ERRORS); disable_all()
        process=lldb.debugger.GetSelectedTarget().GetProcess()
        if process.GetProcessID()==CONFIG['pid']: process.Kill()
        raise

def finish():
    save('capture-hits.json',{'hits':HITS,'entries':len(ENTRIES),'errors':len(ERRORS),
        'disabledAfterCoverage':len(BREAKPOINTS)==3 and all(not b.IsEnabled() for b in BREAKPOINTS.values()),
        'allRequiredCovered':set(CONFIG['requiredMethods'])=={e['methodGroup'] for e in ENTRIES}})
'''


def observer_source():
    return OBSERVER.replace('\ndef invocation(', decoder_source() + '\ndef invocation(', 1)


def method_phases(required):
    need(len(required) == 9 and PRIVATE_PHASE1 <= set(required), 'Exact private cleanup method groups required')
    return {name: int(name in PRIVATE_PHASE1) for name in required}


def verify_entries(entries, config, breakpoints):
    need(len(entries) == 9 and {e['methodGroup'] for e in entries} == set(config['requiredMethods']), 'Nine actual method groups required')
    need(config['methodPhases'] == method_phases(config['requiredMethods']), 'Exact method phase map differs')
    for item in entries:
        name, method = item['methodGroup'].split(':', 1); author = config['authors'][name]; kind = item['kind']
        need(kind in PATH_KINDS, 'Unknown sample kind')
        contract = config['paths'][kind]; bp = breakpoints['paths'][kind]; phase = config['methodPhases'][item['methodGroup']]
        need(item['pid'] == config['pid'] and item['nonce'] == config['nonce']
            and item['pc'] == bp['loadPc'] and item['nativeFilePc'] == contract['filePc']
            and item['nativeSlide'] == bp['loadPc'] - contract['filePc'] and item['nativeUuid'] == config['nativeUuid']
            and item['nativePath'] == config['installedNative'] and item['nativeModule'] == 'libcoreclr.dylib'
            and item['modulePath'] == author['path'] and item['moduleSimpleName'] == author['simpleName']
            and item['fileSha256'] == author['sha256'] and item['moduleMvid'] == author['moduleMvid']
            and item['metadataMethodName'] == method and item['methodDefToken'] == author['methods'][method]
            and item['loadedMetadataMvidValidated'] is True and item['loadedPELayout'] in ('rva', 'flat')
            and item['collectible'] is True and item['exceptionArgs'] == 0
            and item['bytecodeStart'] == item['methodDescBytecodeStart'] and item['bytecodeSizeSlots'] > 0
            and len(bytes.fromhex(item['bytecodePrefixHex'])) == min(item['bytecodeSizeSlots']*4,64)
            and item['definitionBinder'] != 0 and item['instructionMeter'] == item['definitionBinder']+old().OWNER_LAYOUTS['CustomAssemblyBinder']['fields']['m_runeCLRInstructionMeter']
            and item['meterGate'] == dict(config['gate'], phase=phase) and item['terminalPhase'] == phase
            and item['threadContext'] != 0 and item['cleanupOwner'] == (item['instructionMeter'] if phase else 0)
            and item['meterTerminated'] is bool(phase) and item['terminationSignal'] == ('execution-limit' if phase else 'none'),
            'Actual sample process/native/module/definition-owner/cleanup-owner binding differs')
        if kind != 'function-entry':
            need(item['firstOpcodeAddress'] == item['bytecodeStart']+8
                and item['opcodeAddressAdvance'] == contract['opcodeAddressAdvance']
                and item['opcodeRegisterValue']+item['opcodeAddressAdvance'] == item['firstOpcodeAddress']
                and item['frameSpillAddress'] > 0 and item['threadContextSpillAddress'] > 0
                and item['threadStackPointerAddress'] == item['threadContext']+config['layouts']['InterpThreadContext']['fields']['pStackPointer'],
                'Child current frame/opcode/thread-context binding differs')
    return True


def plan(args):
    """Create an offline, non-executing three-path capture contract.

    This phase deliberately only reads frozen receipts and source text.  It does
    not invoke a host adapter, LLDB, CoreSimulator, or any process operation.
    """
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    prepare = args.prepare.resolve(); application = args.application.resolve(); runtime = args.runtime.resolve()
    identity_path = prepare / 'identity.json'
    need(identity_path.is_file(), 'Frozen prepare identity is required')
    identity = read(identity_path)
    need(identity.get('symbol', {}).get('filePc') == 2662540, 'Frozen interpreter entry PC differs')
    need(identity.get('requiredMethods') and len(identity['requiredMethods']) == 9, 'Frozen nine-method inventory required')
    need((application / 'state.json').is_file(), 'Frozen application state is required')
    need((runtime / 'src/coreclr/vm/interpexec.cpp').is_file(), 'Frozen runtime source is required')
    owner = runtime / 'src/coreclr/binder/inc/customassemblybinder.h'
    need(owner.is_file() and 'm_runeCLRInstructionMeter' in owner.read_text(encoding='utf-8'),
         'Definition-owned meter source differs')

    # The function prefix is bound to the frozen native instruction receipt when
    # available.  Child prefixes remain explicitly diagnostic until LLDB reads
    # the matching image in a future capture phase.
    entry_prefix = receipt_prefix(prepare / 'entry-instructions.stdout', 'a9ba6ffc')
    ordinary_prefix = '280140b9684200f9684e40f9680540f908010f90000140f9'
    delegate_prefix = '0000000000000000'
    paths = {
        'function-entry': {'filePc': 2662540, 'prefixHex': entry_prefix, 'nativePrefixBound': False},
        'ordinary-child-dispatch': {'filePc': 3046156, 'line': 3784, 'frameRegister': 'x19',
            'frameSpillOffset': 152, 'opcodeRegister': 'w8', 'opcodePointerRegister': 'x9',
            'opcodeAddressAdvance': 8, 'frameSpillKind': 'raw136', 'stackSpillKind': 'stack80',
            'prefixHex': ordinary_prefix, 'nativePrefixBound': False},
        'delegate-child-dispatch': {'filePc': 3042808, 'line': 3667, 'frameRegister': 'x19',
            'frameSpillOffset': 152, 'opcodeRegister': 'w26', 'opcodePointerRegister': 'x26',
            'opcodeAddressAdvance': 8, 'frameSpillKind': 'raw136', 'stackSpillKind': 'stack80',
            'prefixHex': delegate_prefix, 'nativePrefixBound': False},
    }
    layouts = {'InterpThreadContext': {'size': 88, 'fields': {'pStackPointer': 16, 'runeclrCleanupOwner': 80}}}
    thread_contract = {'rawSpillOffset': 136, 'stackPointerAddressSpillOffset': 80}
    phases = method_phases(identity['requiredMethods'])
    source = observer_source(); ast.parse(source, feature_version=(3, 9))
    (out / 'observer-draft.py').write_text(source, encoding='ascii')
    request = {'driverSha256': sha(__file__), 'prepare': str(prepare),
        'prepareIdentitySha256': sha(identity_path), 'application': str(application),
        'stateSha256': sha(application / 'state.json'), 'runtime': str(runtime),
        'nativeEntry': {'name': identity['symbol']['name'], 'filePc': 2662540},
        'paths': paths, 'layouts': layouts, 'threadContract': thread_contract,
        'requiredMethods': identity['requiredMethods'], 'methodPhases': phases,
        'gate': identity['gate'], 'observerSha256': hashlib.sha256(source.encode('ascii')).hexdigest(),
        'captureReady': CAPTURE_READY, 'pending': PENDING, 'timeoutSeconds': args.timeout,
        'hitCap': 100000, 'physicalDeviceExecuted': False, 'targetProcessCreated': False,
        'nativePrefixBound': False, 'planOnly': True}
    write(out / 'request.json', request)
    write(out / 'results.json', {'passed': True, 'phase': 'plan', 'planOnly': True,
        'nativeEntryProof': False, 'targetProcessCreated': False, 'physicalDeviceExecuted': False,
        'requiredMethods': 9, 'paths': list(paths), 'driverSha256': sha(__file__)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('plan', 'install', 'run'))
    for name in ('prepare', 'application', 'runtime', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--authors', type=Path)
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    need(30 <= args.timeout <= 600, 'Diagnostic timeout must be between 30 and 600 seconds')
    if args.phase == 'plan':
        plan(args)
        return
    # Keep the readiness gate outside any cleanup/finalizer path.  Incomplete
    # contracts must fail before a host adapter could stage a command.
    need(CAPTURE_READY, 'Offline draft only: delegate child/cleanup-phase contracts pending')
    raise RuntimeError('Install/run are unavailable until CAPTURE_READY is enabled')


if __name__ == '__main__':
    main()
