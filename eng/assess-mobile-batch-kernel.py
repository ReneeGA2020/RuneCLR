#!/usr/bin/env python3
"""Check long-kernel scalar ledgers; executable/native provenance stays external."""
import argparse
import hashlib
import json
import re
from pathlib import Path

AUTHOR = 'd743ecb6ba897366a276ab700e79a42f3885ba2eaf69d1713bb086346f2fd09e'
CONTRACT = 'ebfe72469b640b63991189123971beadbf9c3fe74d303a9b7ce66f87596a807b'
IDENTITY = 'RuneCLR.Abstractions, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null'
MVID = '92efbbd4-8ae3-4686-824b-bafe67f2dd69'
DISPATCHES, LIMIT, CHECKSUM = 2100016, 1000000000000, 12749776
ARCHITECTURES = {'Windows.x64': 'X64', 'Android.x64': 'X64', 'iossimulator.arm64': 'Arm64'}
UNVERIFIED = ('nativeEntryProof', 'liveBatchPathVerified', 'mobileExecutionVerified',
              'physicalDeviceVerified', 'performanceMeasured', 'performanceVerified')


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def same(actual, expected, path):
    # Python equates True with 1; native counters and acknowledgements must retain their types.
    need(type(actual) is type(expected), path + ': JSON type differs')
    if isinstance(expected, dict):
        need(actual.keys() == expected.keys(), path + ': fields differ')
        for key, value in expected.items():
            same(actual[key], value, path + '.' + key)
    elif isinstance(expected, list):
        need(len(actual) == len(expected), path + ': count differs')
        for index, value in enumerate(expected):
            same(actual[index], value, path + '[' + str(index) + ']')
    else:
        need(actual == expected, path + ': value differs')


def snapshot(count):
    return {'Remaining': LIMIT - count, 'Executed': count, 'Exhausted': False,
            'IsTerminated': False, 'Reason': 0, 'Phase': 0,
            'CleanupRemaining': 4096, 'CleanupExecuted': 0}


def review(receipt, mode, nonce, pid, samples, platform, component_hash):
    need(platform in ARCHITECTURES, 'Unsupported platform')
    need(mode in ('no-config', 'high-budget'), 'Unsupported budget mode')
    need(type(pid) is int and pid > 0, 'Expected PID must be positive')
    need(type(samples) is int and 1 <= samples <= 100, 'Sample count outside 1..100')
    need(isinstance(nonce, str) and re.fullmatch('[0-9a-fA-F]{32}', nonce) is not None,
         'Expected nonce is not 32 hexadecimal characters')
    need(isinstance(component_hash, str) and re.fullmatch('[0-9a-f]{64}', component_hash) is not None,
         'Trusted loaded contract component hash is missing')
    need(type(receipt) is dict, 'Observation must be a JSON object')
    budget = mode == 'high-budget'
    expected = {
        'schema': 'runeclr.mobile-batch-kernel.observation.v1', 'passed': True,
        'processId': pid, 'nonce': nonce, 'mode': mode, 'architecture': ARCHITECTURES[platform],
        'authorHash': AUTHOR, 'contractHash': CONTRACT, 'contractIdentity': IDENTITY, 'contractMvid': MVID,
        'loadedContractComponentHash': component_hash, 'iterations': 100000,
        'expectedChecksum': CHECKSUM, 'expectedDispatchDelta': DISPATCHES,
        'warmups': 3, 'sampleCount': samples, 'budgetLimit': LIMIT if budget else None,
        'cleanupLimit': 4096, 'collected': True, 'RetiredGetterRejections': 8 if budget else 0,
        'Capabilities': {'policyVersion': 1, 'terminalVersion': 1, 'finalizerVersion': 1, 'privateBridge': True},
        'Initial': snapshot(0) if budget else None,
        'Final': snapshot(DISPATCHES * (3 + samples)) if budget else None,
        'Rows': [{'Index': i, 'Warmup': i < 3, 'Checksum': CHECKSUM,
                  'Before': snapshot(i * DISPATCHES) if budget else None,
                  'After': snapshot((i + 1) * DISPATCHES) if budget else None,
                  'DispatchDelta': DISPATCHES if budget else None} for i in range(3 + samples)],
        **{key: False for key in UNVERIFIED}
    }
    need(receipt.keys() == expected.keys() | {'runtime', 'scope'}, 'Observation fields differ')
    for key, value in expected.items():
        same(receipt[key], value, key)
    need(type(receipt['runtime']) is str and receipt['runtime'].startswith('.NET 12.'),
         'Declared runtime differs')
    need(type(receipt['scope']) is str and bool(receipt['scope']), 'Observation scope missing')
    return {
        'passed': True, 'platform': platform, 'processId': pid, 'nonce': nonce, 'mode': mode,
        'callbacks': samples + 3, 'collections': 1, 'scalarLedgerVerified': True,
        'expectedDispatchDelta': DISPATCHES if budget else None,
        **{key: False for key in UNVERIFIED},
        'scope': 'Supplied process/author/component/architecture binding and exact post-callback scalar ledgers only; no native full/tail cadence, product provenance, mobile execution or timing proof.'
    }


def load(path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            need(key not in value, 'Duplicate JSON field: ' + key)
            value[key] = item
        return value
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=unique,
                      parse_constant=lambda value: need(False, 'Non-finite JSON constant: ' + value))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--mode', choices=('no-config', 'high-budget'), required=True)
    parser.add_argument('--nonce', required=True)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--samples', type=int, required=True)
    parser.add_argument('--platform', choices=tuple(ARCHITECTURES), required=True)
    parser.add_argument('--component-hash', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = review(load(args.receipt), args.mode, args.nonce, args.pid, args.samples, args.platform, args.component_hash)
    result['receiptSha256'] = hashlib.sha256(args.receipt.read_bytes()).hexdigest()
    result['assessorSha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        with args.output.open('x', encoding='ascii') as stream:
            stream.write(text)
    print(text, end='')


if __name__ == '__main__':
    main()
