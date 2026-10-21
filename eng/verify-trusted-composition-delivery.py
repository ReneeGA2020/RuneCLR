#!/usr/bin/env python3
"""Windows x64 signed-delivery native R2R proof.
Not iOS, not a platform signature gate, not a network service, and not anti-rollback.
The old collectible R2R blocker is not this milestone."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = "0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de"
EXPECTED = {
    "coreclr.dll": "a9391606e33afcd41e2f117ea2c83f4a045c5e0bddc32320d50205a95fbf36dd",
    "clrinterpreter.dll": "6f9c915791e34054415ef7a3e0ff763f6abca0025432d3161d190e73f6d26ccc",
    "clrjit.dll": "c657302a3689b4b690d846fbd4a9d8efc4db1ac68329481e87ac1cc9c916808d",
    "System.Private.CoreLib.dll": "f3b765d3d04f816a418282bca88b05679084d70b42a4ff88533c7f0d71346db1",
}
CROSSGEN_SHA = "2adf7303383fb7528a1e4f61d361bfca6df12f292c16b4d3222fe971843b85d9"
PAYLOAD = {"A": ["TrustedComposition.Update.A.dll", "TrustedComposition.Private.dll", "TrustedComposition.IlOnlyHelper.dll"],
           "B": ["TrustedComposition.Update.B.dll", "TrustedComposition.Private.dll", "TrustedComposition.IlOnlyHelper.dll"]}
SUFFIX = {"host": "DeliveryHostObject__Touch", "update": "UpdateModule__Execute", "private": "PrivateLogic__Read"}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + chr(10), encoding='utf-8')


def is_r2r(path):
    data = Path(path).read_bytes()
    header = struct.unpack_from('<I', data, 0x3C)[0]
    if data[header:header + 4] != b'PE\0\0':
        return False
    optional_size = struct.unpack_from('<H', data, header + 20)[0]
    optional = header + 24
    magic = struct.unpack_from('<H', data, optional)[0]
    directories = optional + (112 if magic == 0x20B else 96)
    count = struct.unpack_from('<H', data, header + 6)[0]
    sections = []
    for index in range(count):
        start = optional + optional_size + index * 40
        _virtual_size, rva, raw_size, offset = struct.unpack_from('<IIII', data, start + 8)
        sections.append((rva, raw_size, offset))

    def file_offset(rva):
        for section_rva, raw_size, offset in sections:
            if section_rva <= rva < section_rva + raw_size:
                return offset + rva - section_rva
        raise ValueError('RVA not in file')

    cli = file_offset(struct.unpack_from('<I', data, directories + 14 * 8)[0])
    native_rva = struct.unpack_from('<I', data, cli + 64)[0]
    return native_rva != 0 and data[file_offset(native_rva):file_offset(native_rva) + 4] == b'RTR\0'

def load_evidence(path):
    spec = importlib.util.spec_from_file_location('composition_evidence', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def copy_one(hashes, source, destination_root):
    target = destination_root / source.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    hashes[str(source.relative_to(ROOT)).replace(os.sep, '/')] = sha(source)

def copy_sources(destination):
    roots = [ROOT / 'eng/trusted-composition', ROOT / 'eng/trusted-composition-delivery/Host',
             ROOT / 'eng/trusted-composition-delivery/NativeHarness', ROOT / 'src/RuneCLR.TrustedUpdate']
    hashes = {}
    for root in roots:
        for file in root.rglob('*'):
            if not file.is_file() or any(part in ('bin', 'obj') for part in file.parts):
                continue
            if file.suffix.lower() not in ('.cs', '.csproj', '.props', '.md'):
                continue
            copy_one(hashes, file, destination)
    copy_one(hashes, ROOT / 'Directory.Build.props', destination)
    copy_one(hashes, ROOT / 'eng/windows-entry-observation/WindowsEntryObservation.cs', destination)
    copy_one(hashes, ROOT / 'eng/trusted-composition-evidence.py', destination)
    copy_one(hashes, Path(__file__).resolve(), destination)
    return hashes

def select_assembly(root, name, marker=None):
    hits = []
    for item in Path(root).rglob(name):
        parts = [part.lower() for part in item.parts]
        if any(part in ('ref', 'refint', 'obj') for part in parts):
            continue
        if marker is not None and marker not in str(item):
            continue
        hits.append(item)
    label = name if marker is None else name + ' marker ' + marker
    if not hits:
        raise FileNotFoundError(label + ' count 0')
    stem = Path(name).stem.lower()
    owned = [item for item in hits if any(part.lower() == stem for part in item.parts)]
    chosen = owned or hits
    if len(chosen) != 1:
        if len({sha(item) for item in chosen}) != 1:
            raise FileNotFoundError(label + ' count ' + str(len(chosen)))
        chosen = [max(chosen, key=lambda item: item.stat().st_mtime)]
    return chosen[0]

def find_assembly(root, name):
    return select_assembly(root, name)

def find_marked(root, name, marker):
    return select_assembly(root, name, marker)

def map_file(dll):
    for candidate in (Path(str(dll) + '.map.csv'), Path(dll).with_suffix('.map.csv')):
        if candidate.exists():
            return candidate
    raise FileNotFoundError('map for ' + str(dll))

def isinstance_strict(value, kind):
    if kind is bool:
        return type(value) is bool
    if kind is int:
        return type(value) is int
    if kind is str:
        return type(value) is str
    return False

FACT_FIELDS = (
    ('Activated', 'ACTIVATED', bool),
    ('Version', 'VERSION', str),
    ('Source', 'SOURCE', str),
    ('Value', 'VALUE', int),
    ('PrivateValue', 'PRIVATE', int),
    ('HelperValue', 'HELPER', int),
    ('TouchValue', 'TOUCH', int),
    ('InterfaceValue', 'INTERFACE', int),
    ('DelegateValue', 'DELEGATE', int),
    ('GenericValue', 'GENERIC', int),
    ('StaticCount', 'STATIC', int),
    ('PrivateCount', 'PRIVATE_COUNT', int),
    ('PrivateVersion', 'PRIVATE_VERSION', str),
    ('Identity', 'IDENTITY', bool),
    ('Calls', 'CALLS', int),
    ('Detail', 'DETAIL', str),
    ('Stage', 'STAGE', str),
    ('Candidate', 'CANDIDATE', str),
    ('Recovery', 'RECOVERY', str),
    ('Persist', 'PERSIST', str),
    ('Entry', 'ENTRY', str),
    ('ListedPrivate', 'LISTED_PRIVATE', str),
    ('ListedHelper', 'LISTED_HELPER', str),
    ('LoadedEntry', 'LOADED_ENTRY', str),
    ('LoadedPrivate', 'LOADED_PRIVATE', str),
    ('LoadedHelper', 'LOADED_HELPER', str),
    ('HelperLoaded', 'HELPER_LOADED', bool),
    ('Witnesses', 'WITNESSES', int),
)
ENTRY_FIELDS = (
    ('DefiningType', str), ('Method', str), ('Assembly', str), ('ModuleMvid', str),
    ('MethodDefToken', str), ('Collectible', bool), ('Interpreted', bool), ('PrecodeType', int),
    ('EntryAddress', str), ('CodeAddress', str), ('Bytes', str), ('InvocationEvidence', str), ('Scope', str),
)
WITNESS_FIELDS = (
    ('Label', str), ('Pc', str), ('Image', str), ('AllocationBase', str), ('Rva', int), ('Executable', bool),
)
COMPUTE_IR = re.compile(r'Compiled method: [^\r\n]*TrustedComposition\.IlOnlyHelper:Compute\([^\r\n]*')

def extract_marked_json(text, marker):
    decoder = json.JSONDecoder()
    values, failures = [], []
    start = 0
    while True:
        index = text.find(marker, start)
        if index < 0:
            break
        at = index + len(marker)
        snippet = text[max(0, index - 80):index + 180]
        try:
            value, end = decoder.raw_decode(text, at)
        except json.JSONDecodeError as error:
            failures.append({'marker': marker, 'offset': index, 'error': 'json-decode-error',
                             'detail': error.msg, 'snippet': snippet})
            start = at
            continue
        values.append(value)
        start = end
    return values, failures

def shape_failure(marker, error, value):
    try:
        snippet = json.dumps(value, ensure_ascii=True)[:180]
    except TypeError:
        snippet = str(type(value))
    return {'marker': marker, 'error': error, 'snippet': snippet}

def valid_facts(value):
    return isinstance(value, dict) and all(name in value and isinstance_strict(value[name], kind) for name, _alias, kind in FACT_FIELDS)

def map_facts(value):
    return {alias: value[name] for name, alias, _kind in FACT_FIELDS}

def valid_observation(value):
    if not isinstance(value, dict) or 'Error' in value:
        return False
    entry = value.get('Entry')
    if not isinstance_strict(value.get('AssemblyPath'), str) or not isinstance(entry, dict):
        return False
    return all(name in entry and isinstance_strict(entry[name], kind) for name, kind in ENTRY_FIELDS)

def valid_witness(value):
    return isinstance(value, dict) and all(name in value and isinstance_strict(value[name], kind) for name, kind in WITNESS_FIELDS)

def compute_ir(text):
    return COMPUTE_IR.findall(text)

def parse_records(text):
    raw_facts, failures = extract_marked_json(text, 'FACTS ')
    raw_witnesses, witness_failures = extract_marked_json(text, 'WITNESS ')
    raw_observations, observation_failures = extract_marked_json(text, 'ENTRYOBSERVATION ')
    failures.extend(witness_failures)
    failures.extend(observation_failures)
    facts, witnesses, observations = [], [], []
    for value in raw_facts:
        if valid_facts(value):
            facts.append(value)
        else:
            failures.append(shape_failure('FACTS ', 'facts-shape', value))
    for value in raw_witnesses:
        if valid_witness(value):
            witnesses.append({name: value[name] for name, _kind in WITNESS_FIELDS})
        else:
            failures.append(shape_failure('WITNESS ', 'witness-shape', value))
    for value in raw_observations:
        if isinstance(value, dict) and 'Error' in value and 'Entry' not in value:
            failures.append(shape_failure('ENTRYOBSERVATION ', 'observation-diagnostic', value))
        elif valid_observation(value):
            observations.append(value)
        else:
            failures.append(shape_failure('ENTRYOBSERVATION ', 'observation-shape', value))
    return {'facts': facts, 'witnesses': witnesses, 'observations': observations,
            'compiled': compute_ir(text), 'failures': failures}

def parse_process(text):
    records = parse_records(text)
    failures = list(records['failures'])
    count = len(records['facts'])
    if count == 1:
        facts = map_facts(records['facts'][0])
    else:
        facts = {}
        failures.append({'marker': 'FACTS ', 'error': 'facts-missing' if count == 0 else 'facts-not-singular', 'count': count})
    return facts, records['witnesses'], records['observations'], failures

def pick(item, name):
    lowered = {str(key).lower(): value for key, value in item.items()}
    if name.lower() not in lowered:
        raise KeyError(name)
    return lowered[name.lower()]

def normalize_witness(item):
    if not valid_witness(item):
        raise ValueError('witness-shape')
    return {name: item[name] for name, _kind in WITNESS_FIELDS}

def same_path(left, right):
    if not left or not right:
        return False
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))

def bind_label(witnesses, label, suffix, expected_sha, expected_path, evidence, maps):
    matches = []
    for witness in witnesses:
        if witness['Label'] != label:
            continue
        image = Path(witness['Image'])
        if not image.exists() or not same_path(image, expected_path):
            continue
        digest = sha(image)
        if digest != expected_sha or digest not in maps:
            continue
        info = evidence.read_image(image)
        pc, base, rva = int(witness['Pc'], 16), int(witness['AllocationBase'], 16), witness['Rva']
        if pc - base != rva or not witness['Executable']:
            continue
        executable = any(section['executable'] and section['rva'] <= rva < section['rva'] + section['length'] for section in info['sections'])
        native = any(begin <= rva < end for begin, end in info['runtime_functions'])
        for method in evidence.parse_map(maps[digest]):
            if suffix.endswith('Touch') and 'DeliveryHostObject__Touch' not in method['symbol']:
                continue
            if not method['symbol'].endswith(suffix):
                continue
            if method['rva'] <= rva < method['rva'] + method['length'] and executable and native:
                matches.append({'label': label, 'sha256': digest, 'pc': witness['Pc'], 'rva': rva, 'symbol': method['symbol']})
    return matches

def helper_proof(text, observations, expected_helper=None):
    compiled = compute_ir(text)
    proven = 0
    for item in observations:
        entry = item.get('Entry') if isinstance(item, dict) else None
        if not isinstance(entry, dict):
            continue
        method = entry.get('Method')
        defining = str(entry.get('DefiningType') or '')
        if method == 'Compute' and 'IlOnlyHelper' in defining and entry.get('PrecodeType') == 6 and entry.get('Interpreted') is True and entry.get('InvocationEvidence'):
            if expected_helper is None or same_path(item.get('AssemblyPath'), expected_helper):
                proven += 1
    if not compiled:
        proven = 0
    return {'compiled': compiled, 'provenEntries': proven, 'observationCount': len(observations)}

def tree_sha(tree, relative):
    wanted = relative.replace('\\', '/').lower()
    for key, value in (tree or {}).items():
        if str(key).replace('\\', '/').lower() == wanted:
            return value
    return None

def timeline_problems(name, snap, stage_a):
    before = snap.get('ReceiptShaBefore', '')
    after = snap.get('ReceiptShaAfter', '')
    problems = []
    if name == 'stage-a':
        if before:
            problems.append('receipt-preexisting')
        if not after:
            problems.append('receipt-missing')
        if not tree_sha(snap.get('FinalTreeAfter'), 'final-a/TrustedComposition.Update.A.dll'):
            problems.append('final-missing')
        return problems
    anchor = stage_a.get('ReceiptShaAfter', '') if stage_a else ''
    final_a = 'final-a/TrustedComposition.Update.A.dll'
    if name in ('recover-a', 'fail-b', 'recover-a-again'):
        if before != anchor or after != anchor:
            problems.append('receipt-changed')
        if tree_sha(snap.get('FinalTreeBefore'), final_a) != tree_sha(snap.get('FinalTreeAfter'), final_a):
            problems.append('republish')
    if name == 'fail-b':
        failed = 'final-b-fail/TrustedComposition.Update.B.dll'
        if tree_sha(snap.get('FinalTreeBefore'), failed) or not tree_sha(snap.get('FinalTreeAfter'), failed):
            problems.append('final-missing')
    if name == 'stage-b':
        if before != anchor:
            problems.append('receipt-before-mismatch')
        if not after or after == anchor:
            problems.append('receipt-not-updated')
        if not tree_sha(snap.get('FinalTreeAfter'), 'final-b/TrustedComposition.Update.B.dll'):
            problems.append('final-missing')
    return problems

def outcome_problems(facts, version_key, source):
    spec = {'A': ('A', '101', '310', '112', '20', '20', '310', '1', '1', '1.0.0.0'),
            'B': ('B', '202', '613', '213', '20', '20', '613', '1', '1', '2.0.0.0')}[version_key]
    keys = ['VERSION', 'PRIVATE', 'HELPER', 'TOUCH', 'INTERFACE', 'DELEGATE', 'GENERIC', 'STATIC', 'PRIVATE_COUNT', 'PRIVATE_VERSION']
    problems = []
    for key, expected in zip(keys, spec):
        if str(facts.get(key, '')) != expected:
            problems.append(key.lower())
    if str(facts.get('SOURCE', '')) != source:
        problems.append('source')
    if str(facts.get('IDENTITY', '')).lower() != 'true':
        problems.append('identity')
    return problems

def run_probe(output, probe_log=None):
    good = {
        'stage-a': {'ReceiptShaBefore': '', 'ReceiptShaAfter': 'A', 'FinalTreeBefore': {}, 'FinalTreeAfter': {'final-a/TrustedComposition.Update.A.dll': 'ua'}},
        'recover-a': {'ReceiptShaBefore': 'A', 'ReceiptShaAfter': 'A', 'FinalTreeBefore': {'final-a/TrustedComposition.Update.A.dll': 'ua'}, 'FinalTreeAfter': {'final-a/TrustedComposition.Update.A.dll': 'ua'}},
        'fail-b': {'ReceiptShaBefore': 'A', 'ReceiptShaAfter': 'A', 'FinalTreeBefore': {'final-a/TrustedComposition.Update.A.dll': 'ua'}, 'FinalTreeAfter': {'final-a/TrustedComposition.Update.A.dll': 'ua', 'final-b-fail/TrustedComposition.Update.B.dll': 'ub'}},
        'recover-a-again': {'ReceiptShaBefore': 'A', 'ReceiptShaAfter': 'A', 'FinalTreeBefore': {'final-a/TrustedComposition.Update.A.dll': 'ua'}, 'FinalTreeAfter': {'final-a/TrustedComposition.Update.A.dll': 'ua'}},
        'stage-b': {'ReceiptShaBefore': 'A', 'ReceiptShaAfter': 'B', 'FinalTreeBefore': {}, 'FinalTreeAfter': {'final-b/TrustedComposition.Update.B.dll': 'ub'}},
    }
    bad = {name: {'ReceiptShaBefore': 'B', 'ReceiptShaAfter': 'B', 'FinalTreeBefore': {'final-a/TrustedComposition.Update.A.dll': 'ua', 'final-b/TrustedComposition.Update.B.dll': 'ub'}, 'FinalTreeAfter': {'final-a/TrustedComposition.Update.A.dll': 'ua', 'final-b/TrustedComposition.Update.B.dll': 'ub'}} for name in good}
    good_problems = {name: timeline_problems(name, snap, good['stage-a']) for name, snap in good.items()}
    bad_problems = {name: timeline_problems(name, snap, bad['stage-a']) for name, snap in bad.items()}
    final = r'E:\lane\releases\final-a\TrustedComposition.Update.A.dll'
    source = r'E:\lane\payload\A\TrustedComposition.Update.A.dll'
    helper = r'E:\lane\releases\final-a\TrustedComposition.IlOnlyHelper.dll'
    other_helper = r'E:\lane\payload\A\TrustedComposition.IlOnlyHelper.dll'
    report = {
        'goodTimelineAccepted': good_problems == {name: [] for name in good},
        'goodTimeline': good_problems,
        'badEndStateRejected': 'receipt-preexisting' in bad_problems['stage-a'] and 'receipt-not-updated' in bad_problems['stage-b'],
        'badEndState': bad_problems,
        'sameHashDifferentPathRejected': not same_path(source, final),
        'exactFinalPathAccepted': same_path(final, final),
        'helperPathRejected': not same_path(other_helper, helper),
        'helperPathAccepted': same_path(helper, helper),
    }
    report['kind'] = 'synthetic-protocol-probe'
    report['nativeExecution'] = False
    report['parser'] = parser_probe(probe_log)
    report['passed'] = all(report[key] for key in ('goodTimelineAccepted', 'badEndStateRejected', 'sameHashDifferentPathRejected', 'exactFinalPathAccepted', 'helperPathRejected', 'helperPathAccepted')) and report['parser']['passed']
    save(output / 'probe.json', report)
    print('probe ' + ('passed' if report['passed'] else 'failed'))
    return 0 if report['passed'] else 2

def parser_probe(probe_log=None):
    """Synthetic protocol checks. This is not a native execution proof."""
    nl = chr(10)

    def facts(version, private, helper, touch, generic, private_version, source, activated=True, detail='executed', calls=1, identity=True, private_override=None):
        suffix = version or 'none'
        entry = 'E:/synthetic/final-' + suffix + '/TrustedComposition.Update.' + (version or 'A') + '.dll'
        private_path = 'E:/synthetic/final-' + suffix + '/TrustedComposition.Private.dll'
        helper_path = 'E:/synthetic/final-' + suffix + '/TrustedComposition.IlOnlyHelper.dll'
        return {
            'Activated': activated, 'Version': version, 'Source': source, 'Value': private,
            'PrivateValue': private if private_override is None else private_override,
            'HelperValue': helper, 'TouchValue': touch, 'InterfaceValue': 20 if activated else 0,
            'DelegateValue': 20 if activated else 0, 'GenericValue': generic,
            'StaticCount': 1 if activated else 0, 'PrivateCount': 1 if activated else 0,
            'PrivateVersion': private_version, 'Identity': identity, 'Calls': calls, 'Detail': detail,
            'Stage': 'None//None', 'Candidate': 'None/None/None/', 'Recovery': 'None/None/None/',
            'Persist': 'None/', 'Entry': entry, 'ListedPrivate': private_path, 'ListedHelper': helper_path,
            'LoadedEntry': entry, 'LoadedPrivate': private_path, 'LoadedHelper': helper_path,
            'HelperLoaded': activated, 'Witnesses': 0,
        }

    def observation(path, interpreted=True, invocation='Execute returned checked helper result 310'):
        return {
            'AssemblyPath': path,
            'Entry': {
                'DefiningType': 'TrustedComposition.IlOnlyHelper', 'Method': 'Compute',
                'Assembly': 'TrustedComposition.IlOnlyHelper', 'ModuleMvid': '00000000-0000-0000-0000-000000000001',
                'MethodDefToken': '0x06000001', 'Collectible': False, 'Interpreted': interpreted, 'PrecodeType': 6,
                'EntryAddress': '0x1000', 'CodeAddress': '0x1100', 'Bytes': '4C8B15',
                'InvocationEvidence': invocation,
                'Scope': 'synthetic protocol vector; not a native execution proof',
            },
        }

    a_payload = facts('A', 101, 310, 112, 310, '1.0.0.0', 'Candidate')
    b_payload = facts('B', 202, 613, 213, 613, '2.0.0.0', 'Candidate')
    a_facts, _w, _o, a_failures = parse_process('FACTS ' + json.dumps(a_payload) + nl)
    b_facts, _w, _o, _b_failures = parse_process('FACTS ' + json.dumps(b_payload) + nl)
    a_problems = outcome_problems(a_facts, 'A', 'Candidate')
    b_problems = outcome_problems(b_facts, 'B', 'Candidate')
    conflict_payload = facts('A', 101, 310, 112, 310, '1.0.0.0', 'Candidate', private_override=999)
    conflict = nl.join(['ACTIVATED True', 'VERSION A', 'PRIVATE 101', 'HELPER 310', 'FACTS ' + json.dumps(conflict_payload)]) + nl
    conflict_facts, _w, _o, _c_failures = parse_process(conflict)
    conflict_problems = outcome_problems(conflict_facts, 'A', 'Candidate')
    human_facts, _w, _o, human_failures = parse_process('PRIVATE 101' + nl + 'HELPER 310' + nl + 'ACTIVATED True' + nl)
    inactive = facts('', 0, 0, 0, 0, '', 'None', activated=False, detail='', calls=0, identity=False)
    inactive['Version'] = ''
    lkg = facts('A', 101, 310, 112, 310, '1.0.0.0', 'LastKnownGood')
    helper_path = a_payload['LoadedHelper']
    obs = observation(helper_path)
    obs_b = observation(b_payload['LoadedHelper'], invocation='Execute returned checked helper result 613')
    multi = 'Interpreter compile method System.Text.JsonFACTS ' + json.dumps(a_payload) + nl
    multi += 'FACTS ' + json.dumps(lkg) + nl
    multi += 'prefixENTRYOBSERVATION ' + json.dumps(obs) + nl
    multi += 'ENTRYOBSERVATION ' + json.dumps(obs_b) + nl
    multi += 'Compiled method: .TrustedComposition.IlOnlyHelper:Compute(int)' + nl
    multi += 'prefixCompiled method: .TrustedComposition.IlOnlyHelper:Compute(int)' + nl
    multi += 'Interpreter compile method TailFACTS ' + json.dumps(inactive) + nl
    multi_records = parse_records(multi)
    multi_facts, _w, multi_observations, multi_failures = parse_process(multi)
    witness = {'Label': 'update', 'Pc': '0x10', 'Image': 'E:/synthetic/final-A/TrustedComposition.Update.A.dll', 'AllocationBase': '0x1000', 'Rva': 16, 'Executable': True}
    glued = 'Interpreter compile method RuneCLR.Experiments.EntryOENTRYOBSERVATION ' + json.dumps(obs)
    glued += nl + 'Interpreter compile method System.Text.JsonFACTS ' + json.dumps(a_payload)
    glued += nl + 'Interpreter compile method WitnessWITNESS ' + json.dumps(witness)
    glued += nl + 'prefixCompiled method: .TrustedComposition.IlOnlyHelper:Compute(int)'
    glued += nl + 'ENTRYOBSERVATION not-json' + nl + 'ENTRYOBSERVATION {"Error":"precode"}' + nl
    glued_records = parse_records(glued)
    glued_facts, glued_witnesses, glued_observations, glued_failures = parse_process(glued)
    ir_line = 'Compiled method: .TrustedComposition.IlOnlyHelper:Compute(int)'
    false_entry = dict(obs['Entry'])
    false_entry['Interpreted'] = False
    false_proof = helper_proof(ir_line, [{'AssemblyPath': helper_path, 'Entry': false_entry}], helper_path)
    missing_ir = helper_proof('', [obs], helper_path)
    bare_entry = dict(obs['Entry'])
    bare_entry['InvocationEvidence'] = ''
    bare_proof = helper_proof(ir_line, [{'AssemblyPath': helper_path, 'Entry': bare_entry}], helper_path)
    positive_proof = helper_proof(ir_line, [obs], helper_path)
    wrong_path = helper_proof(ir_line, [obs], helper_path + '.not-final')
    replay = {'ran': False, 'requested': probe_log is not None, 'nativeExecution': False}
    if probe_log is not None:
        file = Path(probe_log)
        if not file.is_file():
            replay['error'] = 'probe-log-missing'
        else:
            raw = file.read_bytes()
            text = raw.decode('utf-8', 'replace')
            records = parse_records(text)
            replay_facts, _w, _o, replay_failures = parse_process(text)
            many = len(records['facts']) != 1
            replay = {
                'ran': True, 'requested': True, 'bytes': len(raw), 'facts': len(records['facts']),
                'observations': len(records['observations']), 'compiled': len(records['compiled']),
                'notSingularWhenMany': (not many) or (replay_facts == {} and any(item.get('error') == 'facts-not-singular' and item.get('count') == len(records['facts']) for item in replay_failures)),
                'nativeExecution': False,
            }
    loaded_ok = lambda item, name: str(item.get(name, '')).replace(chr(92), '/').endswith
    report = {
        'kind': 'synthetic-protocol-probe',
        'nativeExecution': False,
        'usesHistoricalArtifacts': False,
        'factsOnlyAccepted': a_problems == [] and a_facts.get('PRIVATE') == 101 and a_facts.get('HELPER') == 310 and a_facts.get('TOUCH') == 112 and a_facts.get('INTERFACE') == 20 and a_facts.get('DELEGATE') == 20 and a_facts.get('GENERIC') == 310 and a_facts.get('STATIC') == 1 and a_facts.get('PRIVATE_COUNT') == 1 and a_facts.get('PRIVATE_VERSION') == '1.0.0.0' and loaded_ok(a_facts, 'LOADED_ENTRY')('TrustedComposition.Update.A.dll') and loaded_ok(a_facts, 'LOADED_PRIVATE')('TrustedComposition.Private.dll') and loaded_ok(a_facts, 'LOADED_HELPER')('TrustedComposition.IlOnlyHelper.dll') and not any(item.get('error') in ('facts-missing', 'facts-not-singular', 'facts-shape') for item in a_failures),
        'realBAccepted': b_problems == [] and b_facts.get('PRIVATE') == 202 and b_facts.get('HELPER') == 613 and b_facts.get('TOUCH') == 213 and b_facts.get('INTERFACE') == 20 and b_facts.get('DELEGATE') == 20 and b_facts.get('GENERIC') == 613 and b_facts.get('STATIC') == 1 and b_facts.get('PRIVATE_COUNT') == 1 and b_facts.get('PRIVATE_VERSION') == '2.0.0.0' and loaded_ok(b_facts, 'LOADED_ENTRY')('TrustedComposition.Update.B.dll') and loaded_ok(b_facts, 'LOADED_PRIVATE')('TrustedComposition.Private.dll') and loaded_ok(b_facts, 'LOADED_HELPER')('TrustedComposition.IlOnlyHelper.dll'),
        'conflictPrivate': conflict_facts.get('PRIVATE'),
        'conflictProblems': conflict_problems,
        'conflictRejectsJson': conflict_facts.get('PRIVATE') == 999 and conflict_problems == ['private'],
        'humanOnlyIgnored': human_facts == {} and any(item.get('error') == 'facts-missing' for item in human_failures),
        'multiFacts': len(multi_records['facts']),
        'multiObservations': len(multi_observations),
        'multiCompiled': len(multi_records['compiled']),
        'multiFactsRejected': multi_facts == {} and len(multi_records['facts']) == 3 and any(item.get('error') == 'facts-not-singular' and item.get('count') == 3 for item in multi_failures) and multi_records['facts'][-1].get('Calls') == 0 and 'ACTIVATED' not in multi_facts,
        'gluedAccepted': outcome_problems(glued_facts, 'A', 'Candidate') == [] and glued_facts.get('PRIVATE') == 101 and len(glued_observations) == 1 and len(glued_records['facts']) == 1 and len(glued_witnesses) == 1 and len(glued_records['compiled']) == 1,
        'notJsonRejected': any(item.get('error') == 'json-decode-error' and 'not-json' in item.get('snippet', '') for item in glued_failures),
        'diagnosticRejected': any(item.get('error') == 'observation-diagnostic' for item in glued_failures),
        'syntheticObservationsValid': len(multi_observations) == 2 and all(item['Entry']['Method'] == 'Compute' and item['Entry']['PrecodeType'] == 6 and item['Entry']['Interpreted'] is True and 'IlOnlyHelper' in item['Entry']['DefiningType'] and item['Entry']['InvocationEvidence'] and item['AssemblyPath'].endswith('TrustedComposition.IlOnlyHelper.dll') for item in multi_observations),
        'interpretedFalseRejected': false_proof['provenEntries'] == 0 and bool(false_proof['compiled']) and false_entry['PrecodeType'] == 6,
        'missingIrRejected': missing_ir['provenEntries'] == 0 and missing_ir['compiled'] == [],
        'missingInvocationRejected': bare_proof['provenEntries'] == 0 and bool(bare_proof['compiled']),
        'helperPathRejectedByProof': wrong_path['provenEntries'] == 0,
        'jointHelperAccepted': positive_proof['provenEntries'] == 1 and bool(positive_proof['compiled']),
        'historicalLogReplay': replay,
    }
    keys = (
        'factsOnlyAccepted', 'realBAccepted', 'conflictRejectsJson', 'humanOnlyIgnored', 'multiFactsRejected',
        'gluedAccepted', 'notJsonRejected', 'diagnosticRejected', 'syntheticObservationsValid',
        'interpretedFalseRejected', 'missingIrRejected', 'missingInvocationRejected',
        'helperPathRejectedByProof', 'jointHelperAccepted')
    report['passed'] = all(bool(report[key]) for key in keys) and report['multiFacts'] == 3 and report['multiObservations'] == 2 and report['multiCompiled'] == 2 and (not replay['requested'] or (replay.get('ran') and replay.get('notSingularWhenMany')))
    return report
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sdk', default='dotnet')
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--probe-log', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if args.probe:
        return run_probe(output, args.probe_log)
    if args.runtime is None:
        parser.error('--runtime is required unless --probe is set')
    runtime = args.runtime.resolve()
    layout = runtime / 'artifacts/bin/testhost/net11.0-windows-Release-x64'
    framework = layout / 'shared/Microsoft.NETCore.App/12.0.0'
    crossgen = runtime / 'artifacts/bin/coreclr/windows.x64.Checked/crossgen2-published/crossgen2.exe'
    runs = []
    result = {'kind': 'windows-x64-signed-delivery-native-r2r',
              'scope': 'Windows x64 private CoreCLR only. Not iOS, not a platform signature gate, not a network service, and not anti-rollback.',
              'collectibleNativeR2R': False, 'oldCollectibleBlockerIsNotThisMilestone': True,
              'status': 'started', 'passed': False, 'lanes': []}
    save(output / 'result.json', result)

    def execute(name, command, settings=None, timeout=240, check=True):
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith(('DOTNET_', 'COMPLUS_', 'RUNECLR_', 'TRUSTED_COMPOSITION_'))}
        env.update(settings or {})
        process = subprocess.run([str(item) for item in command], cwd=ROOT, env=env, capture_output=True, timeout=timeout)
        (output / (name + '.stdout')).write_bytes(process.stdout)
        (output / (name + '.stderr')).write_bytes(process.stderr)
        runs.append({'name': name, 'command': [str(item) for item in command], 'exitCode': process.returncode, 'startedUtc': datetime.now(timezone.utc).isoformat()})
        save(output / 'commands.json', runs)
        if check and process.returncode:
            tail = (process.stdout + process.stderr).decode('utf-8-sig', errors='replace')[-4000:]
            raise RuntimeError(name + ' exited ' + str(process.returncode) + chr(10) + tail)
        return (process.stdout + process.stderr).decode('utf-8-sig', errors='replace')

    try:
        shutil.copy2(__file__, output / 'driver.py')
        commit = execute('runtime-commit', ['git', '-C', runtime, 'rev-parse', 'HEAD']).strip()
        dirty = execute('runtime-state', ['git', '-C', runtime, 'status', '--porcelain', '--untracked-files=no']).strip()
        bindings = {}
        for name, expected in EXPECTED.items():
            digest = sha(framework / name)
            bindings[name] = {'sha256': digest, 'expected': expected, 'matched': digest == expected}
        crossgen_sha = sha(crossgen)
        save(output / 'inputs.json', {'runtimeCommit': commit, 'runtimeDirty': bool(dirty), 'expectedCommit': BASE,
             'bindings': bindings, 'crossgen': str(crossgen), 'crossgenSha256': crossgen_sha, 'expectedCrossgenSha256': CROSSGEN_SHA,
             'crossgenVersion': execute('crossgen-version', [crossgen, '--version']).strip(),
             'sdk': execute('sdk-version', [args.sdk, '--version']).strip(), 'sourceTargetFramework': 'net11.0',
             'executionFramework': '12.0.0', 'globalJsonPresent': (ROOT / 'global.json').exists()})
        if commit != BASE or dirty or crossgen_sha != CROSSGEN_SHA or any(not item['matched'] for item in bindings.values()):
            raise RuntimeError('Private runtime input binding does not match the reviewed bytes')
        frozen = output / 'frozen'
        frozen_hashes = copy_sources(frozen)
        session_sha = frozen_hashes.get('eng/trusted-composition-delivery/Host/DeliverySession.cs')
        if session_sha != '81e2a4b6fb20bf39b7127095ebc28d55500bb724926c6a888ed9e846f37ed213':
            raise RuntimeError('Frozen DeliverySession is not the reviewed host closure: ' + str(session_sha))
        typed_sha = frozen_hashes.get('eng/trusted-composition-delivery/Host/TypedSession.cs')
        if typed_sha != 'acf39c2ef6df8857df9a593bf4f2e9d14a4de3c79918fdd0cb524a006c1006f4':
            raise RuntimeError('Frozen TypedSession is not the reviewed host closure: ' + str(typed_sha))
        integration_sha = frozen_hashes.get('eng/trusted-composition-delivery/Host/IntegrationProbe.cs')
        if integration_sha != 'e7d54821b94db1b3e74bdc5d7bb763f200e8d7243eeb360f5d73d766d3e80f91':
            raise RuntimeError('Frozen IntegrationProbe is not the reviewed host closure: ' + str(integration_sha))
        for relative in ('eng/trusted-composition-delivery/Host/UnlistedDep/DeliveryAppDep.csproj', 'eng/trusted-composition-delivery/Host/UnlistedDep/Marker.cs', 'eng/trusted-composition-delivery/Host/UnlistedCaller/UnlistedCaller.csproj', 'eng/windows-entry-observation/WindowsEntryObservation.cs', 'eng/trusted-composition-evidence.py'):
            if relative not in frozen_hashes:
                raise RuntimeError('Frozen closure is missing ' + relative)
        save(output / 'frozen-source-hashes.json', frozen_hashes)
        execute('build-harness', [args.sdk, 'build', frozen / 'eng/trusted-composition-delivery/NativeHarness/TrustedComposition.NativeHarness.csproj', '-c', 'Release', '--artifacts-path', output / 'msbuild/harness'])
        execute('build-host', [args.sdk, 'build', frozen / 'eng/trusted-composition-delivery/Host/TrustedComposition.DeliveryHost.csproj', '-c', 'Release', '--artifacts-path', output / 'msbuild/host'])
        host_hits = [item for item in (output / 'msbuild/host').rglob('TrustedComposition.DeliveryHost.exe') if 'ref' not in item.parts and (item.parent / 'RuneCLR.TrustedUpdate.dll').exists()]
        if len(host_hits) != 1:
            raise RuntimeError('DeliveryHost apphost directory count ' + str(len(host_hits)))
        host_dir = host_hits[0].parent
        il_host, r2r_host = output / 'il/host', output / 'r2r/host'
        shutil.copytree(host_dir, il_host)
        shutil.copytree(host_dir, r2r_host)
        evidence = load_evidence(frozen / 'eng/trusted-composition-evidence.py')
        maps = {}

        def crossgen_one(name, source, target, additional):
            target.parent.mkdir(parents=True, exist_ok=True)
            unique = {item.name: item for item in list(framework.glob('*.dll')) + list(additional) if item.name != Path(source).name}
            command = [crossgen, source, '-o', target, '--targetos', 'windows', '--targetarch', 'x64', '-O', '--map', '--mapcsv']
            command += ['-r:' + str(item) for item in unique.values()]
            execute('crossgen-' + name, command, timeout=300)
            maps[sha(target)] = str(map_file(target))
            if not is_r2r(target):
                raise RuntimeError('Crossgen output lacks R2R header: ' + name)
            return target

        host_refs = [item for item in il_host.glob('*.dll') if item.name not in ('TrustedComposition.DeliveryHost.dll', 'TrustedComposition.Contract.dll')]
        required_refs = ('RuneCLR.TrustedUpdate.dll', 'DeliveryAppDep.dll')
        missing_refs = [name for name in required_refs if not any(item.name == name for item in host_refs)]
        if missing_refs:
            raise RuntimeError('DeliveryHost crossgen closure is missing ' + ', '.join(missing_refs))
        contract = crossgen_one('contract', il_host / 'TrustedComposition.Contract.dll', r2r_host / 'TrustedComposition.Contract.dll', host_refs)
        crossgen_one('host', il_host / 'TrustedComposition.DeliveryHost.dll', r2r_host / 'TrustedComposition.DeliveryHost.dll', host_refs + [contract])
        save(output / 'host-crossgen-closure.json', {'hostReferences': sorted(item.name for item in list(host_refs) + [contract]), 'includesDeliveryAppDep': True, 'includesTrustedUpdate': True, 'includesContract': True})
        payloads = {}
        for version in ('A', 'B'):
            update_name = 'TrustedComposition.Update.' + version + '.dll'
            private_il = find_marked(output / 'msbuild/host', 'TrustedComposition.Private.dll', 'Private.' + version)
            helper_il = find_assembly(output / 'msbuild/host', 'TrustedComposition.IlOnlyHelper.dll')
            if is_r2r(helper_il):
                raise RuntimeError('Helper IL is already R2R')
            private_r2r = crossgen_one('private-' + version, private_il, output / 'r2r/private' / version / 'TrustedComposition.Private.dll', [contract])
            update_r2r = crossgen_one('update-' + version, find_assembly(output / 'msbuild/host', update_name), output / 'r2r/update' / version / update_name, [contract, helper_il, private_r2r])
            folder = output / 'payload' / version
            folder.mkdir(parents=True)
            shutil.copy2(update_r2r, folder / update_name)
            shutil.copy2(private_r2r, folder / 'TrustedComposition.Private.dll')
            shutil.copy2(helper_il, folder / 'TrustedComposition.IlOnlyHelper.dll')
            if is_r2r(folder / 'TrustedComposition.IlOnlyHelper.dll'):
                raise RuntimeError('Helper must remain IL-only')
            payloads[version] = folder
        save(output / 'image-maps.json', maps)
        config_path = r2r_host / 'TrustedComposition.DeliveryHost.runtimeconfig.json'
        config = json.loads(config_path.read_text(encoding='utf-8-sig'))
        options = config.setdefault('runtimeOptions', {})
        options.setdefault('framework', {})['name'] = 'Microsoft.NETCore.App'
        options['framework']['version'] = '12.0.0'
        options['rollForward'] = 'Disable'
        config_path.write_text(json.dumps(config, indent=2) + chr(10), encoding='utf-8')
        products = {str(file): {'sha256': sha(file), 'r2r': is_r2r(file)} for file in list((output / 'r2r').rglob('*.dll')) + list((output / 'payload').rglob('*.dll'))}
        save(output / 'products.json', products)
        harness = find_assembly(output / 'msbuild/harness', 'TrustedComposition.NativeHarness.dll').with_suffix('.exe')
        host_exe = r2r_host / 'TrustedComposition.DeliveryHost.exe'
        common = {'DOTNET_TieredCompilation': '0', 'DOTNET_TC_OnStackReplacement': '0', 'DOTNET_InterpMode': '1',
                  'DOTNET_MULTILEVEL_LOOKUP': '0', 'DOTNET_InterpList': '1', 'DOTNET_InterpDump': '*:Compute',
                  'RUNECLR_POST_EXECUTION_PRECODE': '1', 'RUNECLR_DELIVERY_EXPECT_HELPER_INTERPRETED': '1',
                  'TRUSTED_COMPOSITION_WITNESS': '1', 'DOTNET_ROLL_FORWARD': 'Disable'}
        lanes = []
        specs = [('stage-a', 'stage-start', 'A', 'final-a', False, 0, '101', '310', 'executed', 'Candidate'),
                 ('recover-a', 'recover', '', '', False, 0, '101', '310', 'executed', 'LastKnownGood'),
                 ('fail-b', 'stage-start', 'B', 'final-b-fail', True, 1, '', '', 'author-failed', ''),
                 ('recover-a-again', 'recover', '', '', False, 0, '101', '310', 'executed', 'LastKnownGood'),
                 ('stage-b', 'stage-start', 'B', 'final-b', False, 0, '202', '613', 'executed', 'Candidate')]
        for lane_name, ready in (('signed-r2r', '1'), ('signed-r2r-disabled', '0')):
            lane_dir = output / 'lanes' / lane_name
            releases, state = lane_dir / 'releases', lane_dir / 'state'
            releases.mkdir(parents=True)
            state.mkdir()
            receipt = state / 'receipt.bin'
            settings = dict(common)
            settings['DOTNET_ReadyToRun'] = ready
            settings['DOTNET_ReadyToRunLogFile'] = str(lane_dir / 'r2r.log')
            plan = {'Host': str(host_exe), 'DotnetRoot': str(layout), 'Spki': str(lane_dir / 'host.spki'),
                    'Summary': str(lane_dir / 'summary.json'), 'Environment': settings, 'Packages': [], 'Steps': []}
            for version, folder in payloads.items():
                plan['Packages'].append({'Name': version, 'Root': str(folder), 'Document': str(lane_dir / (version + '.signed')),
                                         'Version': version, 'EntryType': 'TrustedComposition.UpdateModule', 'EntryMethod': 'Execute',
                                         'EntryPath': PAYLOAD[version][0], 'Files': PAYLOAD[version]})
            for name, mode, package, final, fail, _exit, _private, _helper, _detail, _source in specs:
                plan['Steps'].append({'Name': name, 'Mode': mode, 'Package': package, 'Releases': str(releases),
                                      'Final': str(releases / final) if final else '', 'Receipt': str(receipt), 'Fail': fail,
                                      'Stdout': str(lane_dir / (name + '.stdout')), 'Stderr': str(lane_dir / (name + '.stderr'))})
            save(lane_dir / 'plan.json', plan)
            execute('lane-' + lane_name, [harness, 'run', lane_dir / 'plan.json'], timeout=900)
            summary = json.loads((lane_dir / 'summary.json').read_text(encoding='utf-8-sig'))
            exits = {item['Name']: item['ExitCode'] for item in summary}
            snapshots = {item['Name']: item for item in summary}
            steps, native_rows = [], []
            compiled, proven_entries, observation_count = [], 0, 0
            functional_problems, native_problems = [], []
            for name, mode, package, final, fail, expect_exit, private, helper_value, detail, source in specs:
                text = (lane_dir / (name + '.stdout')).read_text(encoding='utf-8-sig', errors='replace')
                err = (lane_dir / (name + '.stderr')).read_text(encoding='utf-8-sig', errors='replace')
                facts, witnesses, observations, failures = parse_process(text)
                problems = []
                for code in ('facts-missing', 'facts-not-singular', 'facts-shape', 'observation-diagnostic'):
                    if any(item.get('error') == code for item in failures):
                        problems.append(code)
                if exits.get(name) != expect_exit:
                    problems.append('exit')
                if str(facts.get('ACTIVATED', '')).lower() != str(expect_exit == 0).lower():
                    problems.append('activated')
                if private and str(facts.get('PRIVATE', '')) != private:
                    problems.append('private')
                if helper_value and str(facts.get('HELPER', '')) != helper_value:
                    problems.append('helper')
                if detail and str(facts.get('DETAIL', '')) != detail:
                    problems.append('detail')
                if str(facts.get('CALLS', '')) != '1':
                    problems.append('calls')
                if expect_exit == 0 and str(facts.get('IDENTITY', '')).lower() != 'true':
                    problems.append('identity')
                if expect_exit == 0 and str(facts.get('SOURCE', '')) != source:
                    problems.append('source')
                use_package = package or 'A'
                update_dir = releases / 'final-a' if mode == 'recover' else releases / final
                paths = {'update': update_dir / PAYLOAD[use_package][0],
                         'private': update_dir / 'TrustedComposition.Private.dll',
                         'helper': update_dir / 'TrustedComposition.IlOnlyHelper.dll',
                         'host': r2r_host / 'TrustedComposition.DeliveryHost.dll'}
                images = {label: sha(path) for label, path in paths.items() if label != 'helper'}
                for key in ('LOADED_ENTRY', 'LOADED_PRIVATE', 'LOADED_HELPER'):
                    expected = {'LOADED_ENTRY': paths['update'], 'LOADED_PRIVATE': paths['private'], 'LOADED_HELPER': paths['helper']}[key]
                    if not same_path(facts.get(key, ''), expected):
                        problems.append(key.lower() + '-path')
                helper_paths = []
                for item in observations:
                    entry = item.get('Entry') or item.get('entry') or {}
                    defining = ''
                    if isinstance(entry, dict):
                        defining = str(entry.get('DefiningType') or entry.get('definingType') or '')
                    if 'IlOnlyHelper' in defining:
                        helper_paths.append(item.get('AssemblyPath') or item.get('assemblyPath') or '')
                if not any(same_path(item, paths['helper']) for item in helper_paths):
                    problems.append('helper-assembly-path')
                matches = []
                for label, suffix in SUFFIX.items():
                    matches.extend(bind_label(witnesses, label, suffix, images[label], paths[label], evidence, maps))
                labels = {item['label'] for item in matches}
                if ready == '1' and labels != set(SUFFIX):
                    native_problems.append(name + ':native-pc')
                if ready == '0' and matches:
                    native_problems.append(name + ':unexpected-native-pc')
                snap = snapshots[name]
                problems.extend(timeline_problems(name, snap, snapshots.get('stage-a')))
                if expect_exit == 0:
                    version_key = 'B' if name == 'stage-b' else 'A'
                    problems.extend(outcome_problems(facts, version_key, source))
                proof = helper_proof(text + chr(10) + err, observations, paths['helper'])
                compiled.extend(proof['compiled'])
                proven_entries += proof['provenEntries']
                observation_count += proof['observationCount']
                if not (proof['compiled'] and proof['provenEntries']):
                    native_problems.append(name + ':helper-unproven')
                native_rows_item = {'step': name, 'witnesses': len(witnesses), 'matches': matches}
                native_rows.append(native_rows_item)
                steps.append({'name': name, 'exitCode': exits.get(name), 'problems': problems, 'activated': facts.get('ACTIVATED'),
                              'version': facts.get('VERSION'), 'private': facts.get('PRIVATE'), 'helper': facts.get('HELPER'),
                              'detail': facts.get('DETAIL'), 'source': facts.get('SOURCE'), 'parseFailures': failures})
                functional_problems.extend(name + ':' + item for item in problems)
            helper = {'proven': proven_entries >= 5 and len(compiled) >= 5, 'compiled': len(compiled), 'provenEntries': proven_entries, 'observationCount': observation_count}
            blocking = [item for item in native_problems if item.endswith(('native-pc', 'unexpected-native-pc', 'helper-unproven'))]
            lane = {'name': lane_name, 'readyToRun': ready, 'functionalPassed': not functional_problems,
                    'functionalProblems': functional_problems, 'nativeProblems': native_problems,
                    'nativeBindingProven': ready == '1' and not any(item.endswith('native-pc') for item in native_problems),
                    'nativeBindingAbsent': ready == '0' and not any(item.endswith('unexpected-native-pc') for item in native_problems),
                    'helperInterpreterProven': helper['proven'], 'helper': helper, 'steps': steps, 'native': native_rows,
                    'passed': not functional_problems and not blocking and helper['proven']}
            lanes.append(lane)
            save(output / (lane_name + '.json'), lane)
        result['lanes'] = lanes
        result['passed'] = bool(lanes) and all(lane['passed'] for lane in lanes)
        result['status'] = 'proven' if result['passed'] else 'unproven'
        save(output / 'result.json', result)
        print(result['status'])
        return 0 if result['passed'] else 2
    except Exception as error:
        message = str(error)
        result['status'] = 'host-build-blocked' if 'build-host exited' in message else 'blocked'
        result['error'] = message
        result['passed'] = False
        save(output / 'result.json', result)
        print(result['status'], file=sys.stderr)
        print(message, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
