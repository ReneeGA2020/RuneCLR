#!/usr/bin/env python3
"""Bind local fresh-author evidence and prepare a physical-device run plan offline."""
import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import uuid

PREPARE_SHA = '8bdf9a06b9b0236018300e0fb0c2bac7148a35de10403e84835d27595d62cf58'
PE_READER_SHA = '6b5d69d641c319a64f5b88cedb46434407b08f1b799184d439d4b19efc366a61'
HARNESS_SHA = 'b21874d855338441b128eeb9885d681a7f1b39d19f809622fc4b55b39785a1f7'
TRANSPORT_HELP_SHA = '9cf3a0b3a5cac9d2b2393ec623e1632a0152af2e8077449423ea085de6b5e8a0'
CASES = ('Normal', 'EndlessTick', 'StartLoop', 'CatchResume', 'BroadCatchResume',
         'SignalFilter', 'FilterExhaustion', 'ConstructorLoop', 'StaticConstructorLoop',
         'FiniteCleanup', 'InfiniteCleanup', 'StopLoop', 'MaliciousMessage',
         'ExplicitCanceled', 'Recovery')
AUTHORS = ('HostBudgetProbe.Private.dll', 'HostBudgetProbe.Payload.dll')
SOURCE_HASHES = {'Private': 'c6eecd96e43788fcd9b63e5b7a8b0c6bbe8e541c484bee57ee1c1a3c23b342d9',
                 'Payload': '0080a7e6e084813a73c68524867dc8de477228435fa216c58dadc25651fc0951'}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    with path.open('x', encoding='ascii') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def module(path, expected):
    need(sha(path) == expected, 'Frozen preparation helper changed: ' + path.name)
    spec = importlib.util.spec_from_file_location(path.stem.replace('-', '_'), path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--author-preparation', type=Path, required=True)
    parser.add_argument('--transport-help', type=Path,
                        help='Verified help-only receipt directory; does not establish device access')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directory = args.author_preparation.resolve()
    root = Path(__file__).resolve().parent.parent
    need(not args.output.exists(), 'Fresh plan output required')
    request, result = read(directory / 'request.json'), read(directory / 'results.json')
    need(result.get('passed') is True and result.get('phase') == 'prepare'
         and result.get('deviceHostBound') is True
         and result.get('postDeviceHostBuildCompiled') is True
         and result.get('hostBundleUnchanged') is True,
         'Actual device-host-bound prepare phase required; desktop sanity is insufficient')
    need(result.get('physicalDeviceExecuted') is False and result.get('authorExecuted') is False,
         'Preparation receipt must not claim device execution')
    need(result['driverSha256'] == PREPARE_SHA and request['sourceHashes'] == SOURCE_HASHES,
         'Fixed preparation driver/source identities changed')
    need(sha(root / 'eng/mobile-host-budget-probe/Entry.cs') == HARNESS_SHA,
         'Frozen mobile harness source changed')
    prepare = module(root / 'eng/prepare-ios-device-author.py', PREPARE_SHA)
    pe = module(root / 'eng/verify-ios-device-author.py', PE_READER_SHA)
    app = Path(request['app'])
    need(prepare.bundle(app) == request['hostBundleHashes'],
         'Unsigned local device host changed since actual author preparation')
    need(set(p.name for p in (directory / 'plugin').iterdir()) == set(AUTHORS),
         'Only the two fixed author DLLs may be staged')
    compilation_nonce = request['nonce']
    need(re.fullmatch('[0-9a-f]{32}', compilation_nonce) and result['nonce'] == compilation_nonce,
         'Actual compilation nonce differs')
    author = {}
    for role, name in zip(('Private', 'Payload'), AUTHORS):
        actual = pe.pe_methods(directory / 'plugin' / name)
        need(actual['ilOnly'] and actual['managedNativeRva'] == actual['managedNativeSize'] == 0,
             'Fresh delivered author must be IL-only without native bodies: ' + name)
        need(actual['sha256'] == result['authorHashes'][name], 'Author output hash changed: ' + name)
        need(compilation_nonce.encode() in (directory / 'plugin' / name).read_bytes(),
             'Compilation metadata nonce absent: ' + name)
        need(sha(directory / 'source' / (role + '.cs')) == SOURCE_HASHES[role],
             'Author source changed: ' + role)
        process = read(directory / (role + '.process.json'))
        need(process['exitCode'] == 0
             and process['responseSha256'] == sha(directory / (role + '.rsp'))
             and process['stdoutSha256'] == sha(directory / (role + '.stdout'))
             and process['stderrSha256'] == sha(directory / (role + '.stderr')),
             'Raw successful compiler evidence differs: ' + role)
        need(datetime.fromisoformat(request['boundUtc']) <= datetime.fromisoformat(process['startedUtc'])
             <= datetime.fromisoformat(process['endedUtc']), 'Host binding/compile order differs')
        author[name] = {key: actual[key] for key in
                       ('sha256', 'moduleVersionId', 'ilOnly', 'managedNativeRva', 'references')}
    run_nonce = uuid.uuid4().hex
    lanes = [{'scenario': name,
              'nonce': hashlib.sha256((run_nonce + ':' + name).encode()).hexdigest()[:32],
              'contexts': 20 if name == 'Normal' else 40 if name == 'Recovery' else 1,
              'receipt': name + '/result.json'} for name in CASES]
    need(sum(lane['contexts'] for lane in lanes) == 73, 'Fixed context count changed')
    transport_help = None
    if args.transport_help:
        help_review = args.transport_help / 'review.json'
        need(sha(help_review) == TRANSPORT_HELP_SHA, 'Recorded transport help review changed')
        help_result = read(help_review)
        for name, item in help_result['files'].items():
            need(sha(args.transport_help / name) == item['sha256'], 'Raw transport help changed: ' + name)
        help_plan = args.transport_help / 'parameter-plan.json'
        need(sha(help_plan) == help_result['planSha256'], 'Transport help parameter plan changed')
        transport_help = {'reviewSha256': sha(help_review), 'planSha256': sha(help_plan),
                          'parameterPlan': read(help_plan), 'actualTransportExecuted': False}
    manifest = {'schema': 'runeclr.ios-device.fresh-author-manifest.v1',
                'compilationNonce': compilation_nonce, 'authors': author,
                'sourceHashes': SOURCE_HASHES, 'prepareRequestSha256': sha(directory / 'request.json'),
                'prepareResultsSha256': sha(directory / 'results.json'),
                'unsignedHostBundleHashes': request['hostBundleHashes']}
    plan = {'schema': 'runeclr.ios-device.offline-run-plan.v1', 'runNonce': run_nonce,
            'compilationNonce': compilation_nonce, 'caseSelection': 'all', 'cases': lanes,
            'contexts': 73, 'launchEnvironment': {'RUNECLR_BUDGET_NONCE': run_nonce},
            'appDataPaths': {'plugin': 'Documents/budget-plugin',
                             'evidence': 'Documents/budget-evidence-' + run_nonce},
            'managedEntryArguments': ['<app Documents>/budget-plugin',
                                     '<app Documents>/budget-evidence-' + run_nonce, run_nonce, 'all'],
            'expectedManagedCompletion': 'MOBILE_HOST_BUDGET_COMPLETE nonce=' + run_nonce
                + ' scenario=all pid=<actual native PID> cases=15 contexts=73 passed=true',
            'expectedNativeMarkerNames': ['DEVICE_APP_NATIVE', 'DEVICE_APP_INITIALIZE',
                'DEVICE_APP_CREATE_DELEGATE', 'DEVICE_APP_INVOKE', 'DEVICE_APP_EXIT',
                'DEVICE_APP_SHUTDOWN'],
            'nativeEntryContract': 'coreclr_create_delegate -> SessionBridge.Run -> '
                'MobileHostBudgetProbe.Entry.Run; zero-argument int delegate',
            'nativeShutdownContract': 'Official template exit path; explicit attempted=false '
                'marker is expected, not a fabricated shutdown return code.',
            'transportReceiptRequirements': ['actual reachable physical target/capability receipt',
                'exact unsigned-to-signed host provenance and installed bundle identity',
                'installation completed before delivery started',
                'appDataContainer relative copy/readback of both author DLLs with fresh hashes/MVIDs',
                'fresh evidence directory absent before the owned launch',
                'actual launch environment, PID, UTC start/end, deadline, tool/application exit',
                'native initialize/create_delegate HRESULT, managed/actual exit and native PID/nonce log',
                'explicit shutdown attempt marker; template exit path does not invoke coreclr_shutdown',
                'aggregate and 15 original child receipts with raw recursive hashes',
                'installed signed-host and delivered-author inventory before/after',
                'separate actual interpreted method-entry and loaded metadata identity evidence'],
            'existingAuditReuse': 'mobile-host-budget-audit.adapter()/rows() can check fixed lifecycle rows; '
                'its existing mobile_gate and old author input hashes do not establish physical-device transport.',
            'confirmedTransportHelp': transport_help,
            'pending': ['inspect current device SessionBridge/native delegate source and bind its hashes',
                'actual appDataContainer copy/readback paths, access and launch JSON/exit behavior remain untested',
                'reachable physical device, project signing profile and approved device operations',
                'actual installation/delivery/launch/readback and method-entry capture']}
    if transport_help is None:
        plan['pending'].append('Attach --transport-help to bind the independently retrieved actual CLI help')
    args.output.mkdir(parents=True)
    write(args.output / 'fresh-author-manifest.json', manifest)
    write(args.output / 'plan.json', plan)
    write(args.output / 'results.json', {'passed': True, 'offlinePreparationOnly': True,
          'localUnsignedHostAndFreshAuthorBound': True, 'deviceTransportReady': False,
          'physicalDeviceExecuted': False, 'nativeEntryProof': False,
          'planSha256': sha(args.output / 'plan.json'),
          'freshAuthorManifestSha256': sha(args.output / 'fresh-author-manifest.json'),
          'driverSha256': sha(__file__)})
    print('Offline device run plan prepared: 15 cases/73 contexts; device execution=false')


if __name__ == '__main__':
    main()
