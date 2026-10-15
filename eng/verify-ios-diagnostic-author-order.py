#!/usr/bin/env python3
"""Bind post-install author compilation to one fresh simulator host state.

This tool records a witness after install readback and verifies the later
compiler receipts without installing or launching anything.  Its controls are
in-memory provenance mutations only.
"""
import argparse
import copy
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import re
import struct
import uuid

DRIVER_SHA = '8bdf9a06b9b0236018300e0fb0c2bac7148a35de10403e84835d27595d62cf58'
PE_SHA = '6b5d69d641c319a64f5b88cedb46434407b08f1b799184d439d4b19efc366a61'
AUTHOR = ('HostBudgetProbe.Private.dll', 'HostBudgetProbe.Payload.dll')

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def instant(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone required: ' + value)
    return result

def need(value, message):
    if not value:
        raise RuntimeError(message)

def write_new(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open('x', encoding='ascii') as stream:
        json.dump(value, stream, indent=2)
        stream.write(chr(10))

def load_pe(path):
    tool = Path(__file__).with_name('verify-ios-device-author.py')
    need(sha(tool) == PE_SHA, 'Frozen PE reviewer changed')
    spec = importlib.util.spec_from_file_location('diagnostic_pe', tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.pe_methods(Path(path))

def inventory(root):
    root = Path(root)
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}

def author_identity(path, expected_hash):
    image = load_pe(path)
    need(image['sha256'] == expected_hash and image['ilOnly']
         and image['managedNativeRva'] == image['managedNativeSize'] == 0,
         'Fresh author must be IL-only and match its receipt')
    return {'sha256': image['sha256'], 'moduleVersionId': image['moduleVersionId'],
            'ilOnly': image['ilOnly'], 'managedNativeRva': image['managedNativeRva'],
            'managedNativeSize': image['managedNativeSize']}

def prior_pair(path):
    path = Path(path)
    result = read(path / 'results.json')
    review = None
    for candidate in (path / 'review.json', path.parent / 'post-device-app-author-review-20261015-attempt1/review.json'):
        if candidate.is_file():
            try:
                obj = read(candidate)
                if isinstance(obj.get('authors'), dict):
                    review = obj
            except Exception:
                pass
    identities = review.get('authors', {}) if review else {}
    return {'directory': str(path.resolve()), 'nonce': result.get('nonce'),
            'hashes': result.get('authorHashes', {}),
            'mvids': {name: identities.get(name, {}).get('moduleVersionId') for name in AUTHOR}}

def witness(args):
    out = Path(args.output).resolve()
    need(not out.exists(), 'Fresh witness output required')
    install = read(args.installation)
    install_result = Path(args.installation).resolve()
    need(install.get('passed') is True and install.get('physicalDeviceInstalled') is False,
         'Successful non-physical install receipt required')
    install_json = install_result.parent / 'install.result.json'
    readback_json = install_result.parent / 'installed-before-copy.json'
    need(install_json.is_file() and readback_json.is_file(), 'Install result/readback receipts required')
    install_run = read(install_json); readback = read(readback_json)
    need(install_run['exitCode'] == 0 and install_run['timedOut'] is False,
         'Install process must exit zero without timeout')
    need(readback.get('authorFiles') == {} and readback.get('authorDirectoryExists') is False,
         'Author destination must be empty at install readback')
    state = read(args.state)
    app = Path(args.app).resolve()
    actual = inventory(app)
    expected = state.get('bundleHashes', state.get('bundle'))
    need(expected and actual == expected, 'Host app bytes differ from frozen state readback')
    frozen = {}
    for value in args.frozen_tool:
        path = Path(value).resolve(); need(path.is_file(), 'Frozen tool missing: ' + str(path))
        frozen[str(path)] = sha(path)
    prior = [prior_pair(path) for path in args.previous_author]
    nonce = uuid.uuid4().hex
    need(len(nonce) == 32 and all(c in '0123456789abcdef' for c in nonce), 'Fresh nonce generation failed')
    contract = app / 'RuneCLR.Abstractions.dll'
    contract_hash = sha(contract) if contract.is_file() else None
    value = {'schema': 'runeclr.ios-diagnostic-author.order-witness.v1', 'passed': True,
             'witnessBoundUtc': datetime.now().astimezone().isoformat(), 'freshNonce': nonce,
             'app': str(app), 'appInventory': actual, 'stateSha256': sha(args.state),
             'installationReceiptSha256': sha(args.installation),
             'installResultSha256': sha(install_json), 'installReadbackSha256': sha(readback_json),
             'installationDriverSha256': install.get('driverSha256'), 'buildDriverSha256': install.get('buildDriverSha256'),
             'frozenToolHashes': frozen, 'previousPairs': prior, 'contractComponentSha256': contract_hash,
             'authorDirectoryEmptyAtReadback': True, 'physicalDeviceInstalled': False,
             'authorCompiled': False, 'scope': 'Post-install witness only; no compiler, transfer, launch or physical-device operation.'}
    write_new(out / 'witness.json', value)
    print(json.dumps({'passed': True, 'witness': str(out / 'witness.json'), 'freshNonce': nonce,
                      'previousPairs': len(prior), 'authorDirectoryEmptyAtReadback': True}))

def verify(args):
    witness = read(args.witness); authors = Path(args.authors).resolve(); out = Path(args.output).resolve()
    need(not out.exists(), 'Fresh order review output required')
    need(witness['passed'] and witness['authorCompiled'] is False and witness['physicalDeviceInstalled'] is False,
         'Post-install uncompiled witness required')
    need(Path(witness['app']).resolve() == Path(args.app).resolve(), 'Witness app path differs')
    need(sha(args.state) == witness['stateSha256'], 'Host state changed after witness')
    app_now = inventory(args.app); need(app_now == witness['appInventory'], 'Host app changed after witness')
    install = read(args.installation); need(sha(args.installation) == witness['installationReceiptSha256'], 'Install receipt changed')
    need(install.get('passed') and install.get('physicalDeviceInstalled') is False, 'Install receipt scope differs')
    compiled = read(authors / 'results.json'); request = read(authors / 'request.json')
    need(compiled['passed'] and compiled['authorCompilationCount'] == 2 and compiled['authorIlOnly'], 'Two successful author compiles required')
    need(request['nonce'] == compiled['nonce'] and request['nonce'] == witness['freshNonce'], 'Fresh nonce mismatch')
    need(instant(install['readbackUtc']) < instant(request['boundUtc'])
         and request['boundUtc'] == compiled['startedAfterHostBindingUtc'], 'Compiler must bind after install readback')
    need(instant(request['boundUtc']) >= instant(witness['witnessBoundUtc']), 'Compiler predates witness')
    last = instant(request['boundUtc']); identities = {}
    for role, filename in zip(('Private', 'Payload'), AUTHOR):
        process = read(authors / (role + '.process.json'))
        need(process['exitCode'] == 0 and not process.get('timedOut', False)
             and last <= instant(process['startedUtc']) <= instant(process['endedUtc']), 'Ordered compiler process failed: ' + role)
        last = instant(process['endedUtc'])
        for stream in ('stdout', 'stderr'):
            need(sha(authors / (role + '.' + stream)) == process[stream + 'Sha256'], 'Compiler stream changed: ' + role)
        rsp = authors / (role + '.rsp'); need(sha(rsp) == process['responseSha256'], 'Compiler response changed: ' + role)
        path = authors / 'plugin' / filename
        identities[filename] = author_identity(path, compiled['authorHashes'][filename])
        need(request['nonce'].encode('ascii') in path.read_bytes(), 'Fresh nonce absent from ' + filename)
    need(inventory(args.app) == witness['appInventory'], 'Host app changed during author compilation')
    prior = witness['previousPairs']; current_hashes = compiled['authorHashes']
    for pair in prior:
        need(pair['nonce'] != request['nonce'], 'Nonce replayed an earlier author pair')
        for filename in AUTHOR:
            need(pair['hashes'].get(filename) != current_hashes[filename], 'Author hash replayed an earlier pair')
            old_mvid = pair['mvids'].get(filename)
            need(not old_mvid or old_mvid != identities[filename]['moduleVersionId'], 'Author MVID replayed an earlier pair')
    report = {'schema': 'runeclr.ios-diagnostic-author.order-review.v1', 'passed': True,
              'appFiles': len(app_now), 'witnessSha256': sha(args.witness), 'installationReceiptSha256': sha(args.installation),
              'stateSha256': sha(args.state), 'authorRequestSha256': sha(authors / 'request.json'),
              'authorResultsSha256': sha(authors / 'results.json'), 'authorIdentities': identities,
              'compilerProcesses': 2, 'previousPairsRejected': len(prior), 'installationReadbackBound': True,
              'authorDirectoryEmptyAtReadback': True, 'applicationUnchanged': True,
              'physicalDeviceExecuted': False, 'simulatorLaunchedByThisTool': False,
              'scope': 'Post-install host witness, fresh ordered compiler receipts and replay rejection; no launch or physical execution.',
              'reviewDriverSha256': sha(__file__)}
    write_new(out / 'review.json', report); print(json.dumps({'passed': True, 'appFiles': len(app_now), 'compilerProcesses': 2, 'previousPairsRejected': len(prior)}))

def controls(args):
    witness = read(args.witness); out = Path(args.output).resolve(); need(not out.exists(), 'Fresh controls output required')
    controls = []
    def reject(name, altered, reason):
        accepted = all(altered.get(key) == witness.get(key) for key in
                       ('installationReceiptSha256', 'stateSha256', 'freshNonce',
                        'authorDirectoryEmptyAtReadback', 'physicalDeviceInstalled'))
        controls.append({'name': name, 'rejected': not accepted, 'syntheticOnly': True, 'inMemoryOnly': True, 'reason': reason})
    for name, key, reason in [('changed-install-receipt', 'installationReceiptSha256', 'install binding mismatch'),
                              ('changed-state', 'stateSha256', 'host state mismatch'),
                              ('replayed-nonce', 'freshNonce', 'nonce replay'),
                              ('author-present-at-readback', 'authorDirectoryEmptyAtReadback', 'author destination was not empty'),
                              ('physical-install-claimed', 'physicalDeviceInstalled', 'physical operation flag')]:
        altered = copy.deepcopy(witness); altered[key] = 'changed' if key != 'authorDirectoryEmptyAtReadback' and key != 'physicalDeviceInstalled' else (True if key == 'authorDirectoryEmptyAtReadback' else True)
        reject(name, altered, reason)
    need(all(item['rejected'] for item in controls), 'Synthetic order controls accepted')
    report = {'schema': 'runeclr.ios-diagnostic-author.order-controls.v1', 'passed': True, 'controls': controls,
              'rejected': len(controls), 'targetCodeExecuted': False, 'physicalDeviceVerified': False,
              'controlDriverSha256': sha(__file__)}
    write_new(out / 'results.json', report); print(json.dumps({'passed': True, 'rejected': len(controls), 'syntheticOnly': True}))

def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='phase', required=True)
    w = sub.add_parser('witness')
    for name in ('installation', 'state', 'app', 'output'): w.add_argument('--' + name, required=True)
    w.add_argument('--previous-author', action='append', default=[]); w.add_argument('--frozen-tool', action='append', default=[]); w.set_defaults(run=witness)
    v = sub.add_parser('verify')
    for name in ('witness', 'installation', 'state', 'app', 'authors', 'output'): v.add_argument('--' + name, required=True)
    v.set_defaults(run=verify)
    c = sub.add_parser('controls'); c.add_argument('--witness', required=True); c.add_argument('--output', required=True); c.set_defaults(run=controls)
    args = parser.parse_args(); args.run(args)

if __name__ == '__main__': main()
