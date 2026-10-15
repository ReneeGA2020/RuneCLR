#!/usr/bin/env python3
"""Review one mobile batching lane; controller owns actual runtime/platform binding."""
import argparse
import ast
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / 'eng/verify-batch-boundary.py'
VALIDATOR_SHA256 = '3ca777aa01599fc6198cb83622a1a079f7fd5a5ccb92a3964db95acc3b873cdb'
ARCHITECTURES = {'iossimulator.arm64': 'Arm64', 'Android.x64': 'X64', 'Windows.x64': 'X64'}
LANES = ((1, 1), (1, 100), (1, 1000), (100, 100), (1000, 1000))


def need(value, message):
    if not value:
        raise RuntimeError(message)


def validator_for(architecture):
    raw = VALIDATOR.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == VALIDATOR_SHA256, 'Frozen boundary validator differs')
    source = raw.decode('utf-8-sig')
    tree = ast.parse(source, filename=str(VALIDATOR))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    validate = functions['validate']
    replacements = 0
    for node in ast.walk(validate):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        if (isinstance(left, ast.Subscript) and isinstance(left.value, ast.Name)
                and left.value.id == 'receipt' and isinstance(left.slice, ast.Constant)
                and left.slice.value == 'architecture' and len(node.ops) == 1
                and isinstance(node.ops[0], ast.Eq) and len(node.comparators) == 1
                and isinstance(node.comparators[0], ast.Constant)
                and node.comparators[0].value == 'X64'):
            # Only the frozen validator's precise architecture literal changes.
            node.comparators[0].value = architecture
            replacements += 1
    need(replacements == 1, 'Frozen architecture comparison is not unique')
    namespace = {'need': need, 'METHODS': ('ShortReturn', 'OrdinaryThrow', 'FiniteProgress', 'EndlessCatch')}
    selected = ast.Module(body=[functions['valid_progress'], validate], type_ignores=[])
    exec(compile(ast.fix_missing_locations(selected), str(VALIDATOR), 'exec'), namespace)
    return namespace['validate']


def review_lane(receipt, configured, matrix, platform, author_hash, pid, nonce):
    """Return frozen single-worker semantic rows, without promoting mobile evidence."""
    need(platform in ARCHITECTURES, 'Unsupported explicitly selected platform')
    need(type(configured) is int and type(matrix) is int and (configured, matrix) in LANES,
         'Unsupported configured interval / boundary matrix lane')
    need(type(pid) is int and pid > 0 and type(receipt.get('processId')) is int
         and receipt['processId'] == pid, 'Owned process identity differs')
    need(isinstance(nonce, str) and bool(nonce) and receipt.get('nonce') == nonce,
         'Owned process nonce differs')
    need(isinstance(author_hash, str) and re.fullmatch(r'[0-9a-fA-F]{64}', author_hash) is not None
         and isinstance(receipt.get('authorHash'), str)
         and receipt['authorHash'].lower() == author_hash.lower(), 'Frozen author hash differs')
    architecture = ARCHITECTURES[platform]
    need(receipt.get('architecture') == architecture, 'Declared architecture differs for ' + platform)
    need(isinstance(receipt.get('runtime'), str) and receipt['runtime'].startswith('.NET 12.'),
         'Declared .NET 12 runtime differs')
    return validator_for(architecture)(receipt, configured, matrix)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--configured', type=int, required=True)
    parser.add_argument('--matrix', type=int, required=True)
    parser.add_argument('--platform', choices=tuple(ARCHITECTURES), required=True)
    parser.add_argument('--author-hash', required=True)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--nonce', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    raw = args.receipt.read_bytes()
    receipt = json.loads(raw.decode('utf-8-sig'))
    rows = review_lane(receipt, args.configured, args.matrix, args.platform, args.author_hash, args.pid, args.nonce)
    result = {
        'passed': True, 'platform': args.platform, 'architecture': ARCHITECTURES[args.platform],
        'configuredInterval': args.configured, 'matrixInterval': args.matrix,
        'processId': args.pid, 'nonce': args.nonce, 'authorHash': args.author_hash.lower(),
        'receiptSha256': hashlib.sha256(raw).hexdigest(), 'validatorSha256': VALIDATOR_SHA256,
        'rows': len(rows), 'collections': sum(row['Collected'] is True for row in rows),
        'singleLaneSemanticsVerified': True, 'nativeEntryProof': False, 'mobileVerified': False,
        'performanceMeasured': False,
        'scope': 'Single-worker lane semantics and supplied author/process/architecture binding only; actual executable, environment, runtime/native platform and product ownership require controller evidence.'
    }
    rendered = json.dumps(result, indent=2) + '\n'
    if args.output:
        with args.output.open('x', encoding='ascii') as stream:
            stream.write(rendered)
    print(rendered, end='')


if __name__ == '__main__':
    main()
