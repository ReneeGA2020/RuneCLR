#!/usr/bin/env python3
"""Review actual offline ordinary-child evidence and the sampler's blocked draft guards."""
import argparse
import ast
from contextlib import redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import struct
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
PLAN_DRIVER = 'b8953d80a49dc05f3b5ccc6bfabe5b16f264c73b2dc60a5e547f4930d56678ad'
DRAFT_DRIVER = 'bc922779f4a64b83ca69b6b5dd1f13a9f842277e9b7f60226910508c6f1d779a'
IDENTITY_SHA = 'd4d6298d0e839f333cd52ece0d2a8f1870b3b0d1e6dd8bcd77a7dbc1d4344df5'
NATIVE_SHA = 'b0670a7604bd8857409f1ea9ac543f293c99047286f6f762d0eb720ca6f877ae'


def need(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def module(path):
    spec = importlib.util.spec_from_file_location('offline_entry_review_' + path.stem.replace('-', '_'), path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def word(row):
    return struct.unpack('<I', bytes.fromhex(row['bytesHex']))[0]


def ordinary_contract(contract, observed, image, section, dwarf, source_sha):
    need(contract['filePc'] == 0x2e7b0c and contract['line'] == 3784
         and contract['frameRegister'] == 'x19' and contract['frameSpillOffset'] == 0x98
         and contract['opcodeRegister'] == 'w8' and contract['opcodePointerRegister'] == 'x9'
         and contract['sourceSha256'] == source_sha and not contract['targetProcessCreated']
         and not contract['liveRegisterContentsVerified'] and not contract['pFrameDwarfCoversCapturePc'],
         'Actual ordinary-child static source/PC/frame/opcode/scope identity differs')
    need(observed['targetProcessCreated'] is False and len(observed['locations']) == 1, 'Exactly one offline child location required')
    raw = observed['locations'][0]
    for key in ('filePc', 'line', 'before', 'instructions'):
        need(contract[key] == raw[key], 'Declared child contract differs from raw offline reader: ' + key)
    need(len(contract['before']) == 32 and len(contract['instructions']) == 16, 'Actual native32/16 instruction windows required')
    for rows in (contract['before'], contract['instructions']):
        for i, row in enumerate(rows):
            position = section['offset'] + row['filePc'] - section['address']
            need(section['offset'] <= position and position + 4 <= section['offset'] + section['length']
                 and image[position:position + 4].hex() == row['bytesHex']
                 and (i == 0 or row['filePc'] == rows[i - 1]['filePc'] + 4), 'Actual native instruction bytes/contiguity differ')
    need(contract['before'][0]['filePc'] == contract['filePc'] - 128
         and contract['instructions'][0]['filePc'] == contract['filePc'], 'Actual native windows do not surround capture PC')
    first = word(contract['instructions'][0])
    need(first & 0xffc00000 == 0xb9400000 and first & 31 == 8 and first >> 5 & 31 == 9
         and first >> 10 & 0xfff == 0, 'ARM64 actual capture bytes must load opcode w8 from x9')
    store, reload, header = contract['frameStore'], contract['frameReload'], contract['headerSkip']
    need(store in contract['before'] and header in contract['before'] and reload in contract['instructions'], 'Actual frame/header instructions absent from raw windows')
    for row, opcode in ((store, 0xf9000000), (reload, 0xf9400000)):
        value = word(row)
        need(value & 0xffc00000 == opcode and value & 31 == 8 and value >> 5 & 31 == 19
             and (value >> 10 & 0xfff) * 8 == 152, 'ARM64 actual frame slot store/reload bytes differ')
    value = word(header)
    need(value & 0xffe00c00 == 0xf8400400 and value & 31 == 8 and value >> 5 & 31 == 9
         and value >> 12 & 0x1ff == 8, 'ARM64 actual bytecode header skip bytes differ')
    contextual = contract['contextualDwarf']
    need(contextual == {'start': 3046104, 'end': 3046144, 'register': 'x19', 'offset': 152}
         and contextual['start'] <= header['filePc'] < contextual['end'] <= contract['filePc'],
         'Actual contextual pFrame DWARF scope must cover header but exclude capture')
    intervals = []
    for block in dwarf.split(chr(10) + chr(10)):
        if 'interpexec.cpp' not in block:
            continue
        intervals.extend((int(m[1], 16), int(m[2], 16), int(m[3]), int(m[4])) for m in
            re.finditer(r'\[0x([0-9a-f]+), 0x([0-9a-f]+)\): DW_OP_breg(\d+) W\d+\+(\d+)', block))
    need((contextual['start'], contextual['end'], 19, 152) in intervals, 'Actual raw contextual pFrame DWARF range missing')
    between = [row for row in contract['before'] if row['filePc'] > store['filePc']]
    need(between == contract['checkedFrameRegisterWindow'] and contract['frameRegisterStableAfterStore'], 'Actual frame-register stability window differs')
    for row in between:
        operands, mnemonic = row['operands'], row['mnemonic']
        branch = mnemonic in ('b', 'bl', 'br', 'blr', 'cbz', 'cbnz', 'tbz', 'tbnz') or mnemonic.startswith('b.')
        writes_first = operands.split(',', 1)[0] in ('x19', 'w19')
        need(not (writes_first and not branch and not mnemonic.startswith(('str', 'stp', 'stur', 'cmp', 'cmn', 'tst')))
             and not ('[x19,' in operands and (']!' in operands or '], ' in operands)), 'Actual x19 stability window writes frame register')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('receipts', 'identity', 'native', 'source-root', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    need(not args.output.exists(), 'Fresh independent offline-entry review output required')
    args.output.mkdir(parents=True)
    result = {'schema': 'runeclr.ios-fresh-author.entry-offline-independent-review.v1', 'passed': False,
              'draftOnly': True, 'captureReady': False, 'nativeEntryProof': False, 'liveRegistersVerified': False,
              'physicalDeviceExecuted': False, 'targetProcessCreated': False, 'debuggerStarted': False,
              'reviewerSha256': sha(__file__), 'pending': ['delegate-child dispatch', 'private cleanup phase1']}
    try:
        plan = args.receipts / 'extracted/plan'
        request, completed = read(plan / 'request.json'), read(plan / 'results.json')
        snapshot_path = args.receipts / 'source-freeze/eng/ios-fresh-author-entry-capture.py'
        draft_path = ROOT / 'eng/ios-fresh-author-entry-capture.py'
        need(sha(snapshot_path) == request['driverSha256'] == completed['driverSha256'] == PLAN_DRIVER
             and sha(draft_path) == DRAFT_DRIVER and sha(args.identity) == request['prepareIdentitySha256'] == IDENTITY_SHA,
             'Actual executed plan snapshot/current blocked draft/preparation identity differs')
        snapshot, draft = module(snapshot_path), module(draft_path)
        identity = read(args.identity)
        need(completed['passed'] and completed['phase'] == 'plan' and not completed['nativeEntryProof']
             and not completed['targetProcessCreated'] and not completed['physicalDeviceExecuted'], 'Offline plan completion promoted to live proof')
        observer = snapshot.observer_source()
        need(observer == draft.observer_source() == (plan / 'observer-draft.py').read_text()
             and hashlib.sha256(observer.encode('ascii')).hexdigest() == request['observerSha256'], 'Actual observer generation/frozen bytes differ')
        ast.parse(observer, feature_version=(3, 9))
        ast.parse(draft_path.read_text(), feature_version=(3, 9))
        need(draft.CAPTURE_READY is False and len(draft.PENDING) == 2
             and 'delegate' in draft.PENDING[0] and 'phase1' in draft.PENDING[1], 'Current draft must block incomplete delegate/phase1 coverage')
        need(request['ownerLayouts'] == draft.OWNER_LAYOUTS and request['gate'] == identity['gate']
             and request['nativeEntry'] == identity['symbol'] and request['requiredMethodGroups'] == identity['requiredMethods']
             and request['dwarfSha256'] == identity['dwarfSha256'] and request['timeoutSeconds'] == 180 and request['hitCap'] == 100000
             and not request['physicalDeviceExecuted'] and not request['targetProcessCreated'], 'Actual owner/entry/phase/cap/timeout plan binding differs')
        prepare = snapshot.helper('ios-fresh-author-entry-prepare.py', snapshot.PREPARE_SHA)
        readers = prepare.readers(); readers['dwarf_layout'].__globals__['FIELDS'] = snapshot.OWNER_FIELDS
        for label in ('PEAssembly', 'CustomAssemblyBinder', 'child-offline-lldb', 'child-pframe-dwarf'):
            stage, stage_request = read(plan / (label + '.result.json')), read(plan / (label + '.request.json'))
            need(stage['exitCode'] == 0 and stage_request['offlineOnly'] and stage_request['timeoutSeconds'] == 45
                 and (plan / (label + '.stderr')).read_text() == '', 'Actual bounded offline reader stage differs: ' + label)
        for name in snapshot.OWNER_FIELDS:
            need(readers['dwarf_layout']((plan / (name + '.stdout')).read_text(), name) == request['ownerLayouts'][name], 'Actual owner chain raw DWARF differs')
        native = readers['native'](args.native)
        need(sha(args.native) == NATIVE_SHA and native == identity['sourceNative'], 'Actual matching simulator native bytes/layout/UUID differ')
        source = args.source_root / 'src/coreclr/vm/interpexec.cpp'
        owner = args.source_root / 'src/coreclr/binder/inc/customassemblybinder.h'
        need(sha(owner) == request['ownerSourceSha256'], 'Actual definition-owned meter source differs')
        child_request = read(plan / 'child-request.json'); source_text = source.read_text()
        lines = source_text.splitlines()
        need(sha(source) == child_request['sourceSha256'] and child_request['line'] == 3784
             and lines[3783].strip() == 'INTOP_NEXT;' and '// Set execution state for the new frame' in lines[3770]
             and 'GetModule()->GetPEAssembly()->GetAssemblyBinder()' in source_text, 'Actual source dispatch anchor/definition binder ownership differs')
        observed = read(plan / 'child-offline.json'); contract = request['childContract']
        dwarf = (plan / 'child-pframe-dwarf.stdout').read_text()
        image = args.native.read_bytes(); section = native['sections']['__TEXT,__text']
        ordinary_contract(contract, observed, image, section, dwarf, sha(source))
        controls = []
        for name, mutate in {
            'wrong-child-PC': lambda c: c.update(filePc=c['filePc'] + 4),
            'wrong-frame-register': lambda c: c.update(frameRegister='x20'),
            'wrong-frame-spill': lambda c: c.update(frameSpillOffset=160),
            'wrong-opcode-pointer': lambda c: c.update(opcodePointerRegister='x10'),
            'context-DWARF-promoted': lambda c: c.update(pFrameDwarfCoversCapturePc=True),
            'live-registers-promoted': lambda c: c.update(liveRegisterContentsVerified=True),
            'wrong-child-source': lambda c: c.update(sourceSha256='0' * 64),
            'raw-window-changed': lambda c: c['before'][0].update(bytesHex='00000000'),
            'missing-frame-window': lambda c: c['checkedFrameRegisterWindow'].pop(),
            'wrong-context-scope': lambda c: c['contextualDwarf'].update(end=c['filePc'] + 4),
        }.items():
            altered = copy.deepcopy(contract); mutate(altered)
            try:
                ordinary_contract(altered, observed, image, section, dwarf, sha(source))
            except ValueError as error:
                controls.append({'name': name, 'rejected': True, 'reason': str(error), 'copiedOrInMemoryOnly': True})
            else:
                controls.append({'name': name, 'rejected': False})
        # Stub all runtime/host actions: the production draft must reject a relabeled ready plan first.
        forbidden = []
        fake_host = SimpleNamespace(stage=lambda *a, **k: forbidden.append('stage'))
        draft.frozen = lambda args: (None, fake_host, None, None, None, None)
        draft.retire = lambda *a: None
        for phase in ('install', 'run'):
            fixture = args.output / ('synthetic-guard-' + phase); fixture.mkdir()
            fake_request = dict(request, driverSha256=DRAFT_DRIVER, captureReady=True)
            (fixture / 'request.json').write_text(json.dumps(fake_request))
            (fixture / 'results.json').write_text(json.dumps({'passed': True}))
            (fixture / 'installation').mkdir()
            (fixture / 'installation/results.json').write_text(json.dumps({'passed': True}))
            try:
                with redirect_stdout(io.StringIO()):
                    getattr(draft, phase)(SimpleNamespace(output=fixture, timeout=180))
            except RuntimeError as error:
                need('Offline draft only:' in str(error) and not forbidden, 'Draft guard did not reject before target actions')
                controls.append({'name': 'draft-blocks-' + phase, 'rejected': True, 'reason': str(error), 'syntheticLocalOnly': True})
            else:
                raise ValueError('Current draft accepted relabeled-ready ' + phase)
        need(len(controls) == 12 and all(c['rejected'] for c in controls), 'Independent offline contract/draft guard control unexpectedly accepted')
        synthetic = read(args.receipts / 'extracted/frozen-tools/controls-plan2.json')
        need(synthetic['passed'] and synthetic['count'] == 36 and synthetic['driverSha256'] == PLAN_DRIVER
             and synthetic['observerSha256'] == request['observerSha256'] and synthetic['identitySha256'] == IDENTITY_SHA
             and not synthetic['targetProcessCreated'] and not synthetic['debuggerStarted'] and synthetic['syntheticMemoryOnly'], 'Actual36 synthetic ordinary-entry/child tests differ')
        draft_source = draft_path.read_text()
        need('timeout=45' in ast.get_source_segment(draft_source, next(n for n in ast.parse(draft_source).body if isinstance(n, ast.FunctionDef) and n.name == 'query'))
             and '30 <= args.timeout <= 600' in draft_source and "args.timeout == request['timeoutSeconds']" in draft_source
             and 'host.capture(' not in draft_source, 'Current draft query/CLI/frozen-run timeout guards differ')
        result.update(passed=True, planDriverSha256=PLAN_DRIVER, blockedDraftSha256=DRAFT_DRIVER,
                      ordinaryChildFilePc=contract['filePc'], frameRegister=contract['frameRegister'], frameSpillOffset=152,
                      opcodePointerRegister='x9', opcodeRegister='w8', contextualDwarf=contract['contextualDwarf'],
                      pFrameDwarfCoversCapturePc=False, actualNativeSha256=NATIVE_SHA, actualNativeUuid=native['uuid'],
                      actualObserverSha256=request['observerSha256'], ordinaryChildStaticBytesBound=True, ownerDwarfBound=True,
                      installGuardRejected=True, runGuardRejected=True, capsAndTimeoutSourceReviewed=True,
                      independentControls=controls, controlsTotal=12, controlsRejected=12, syntheticDecoderChecks=36,
                      rawReceiptHashes={str(p.relative_to(plan)): sha(p) for p in plan.rglob('*') if p.is_file()},
                      scope='Actual ordinary-child static native/source/contextual-DWARF contract and blocked current draft only. The36 synthetic checks do not establish real nine-group coverage; delegate-child and private-phase1 bindings remain pending.')
    except Exception as error:
        result['error'] = str(error)
    (args.output / 'results.json').write_text(json.dumps(result, indent=2) + chr(10), encoding='ascii')
    print(json.dumps({k: v for k, v in result.items() if k not in ('rawReceiptHashes', 'independentControls')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
