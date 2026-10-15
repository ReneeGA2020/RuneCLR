#!/usr/bin/env python3
"""Replay existing real kernel receipts and reject altered counters/bindings."""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipts', type=Path, default=ROOT / 'artifacts/mobile-budget-batching/kernel-windows-sanity-20261015-attempt2')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assessor = ROOT / 'eng/assess-mobile-batch-kernel.py'
    spec = importlib.util.spec_from_file_location('kernel_assessor', assessor)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    args.output.mkdir(parents=True, exist_ok=False)
    actual, rejected, files = [], [], {}
    for mode in ('no-config', 'high-budget'):
        receipt_path = args.receipts / (mode + '.receipt.json')
        process_path = args.receipts / (mode + '.process.json')
        process, receipt = module.load(process_path), module.load(receipt_path)
        stdout = args.receipts / (mode + '.stdout')
        stderr = args.receipts / (mode + '.stderr')
        need(process['exitCode'] == 0 and process['timedOut'] is False, 'Original process did not complete')
        need(process['stdoutSha256'] == sha(stdout) and process['stderrSha256'] == sha(stderr), 'Original streams changed')
        argv = process['argv']
        need(argv[-4:-1] == [mode, receipt['nonce'], str(receipt['sampleCount'])], 'Original invocation differs')
        need(sha(Path(argv[-5])) == module.AUTHOR, 'Original author input bytes differ')
        need(sha(Path(argv[-6])) == 'ee9ea4e284ff2296f437e8a97e7ef16efffaa61a13240d8e7468e1f5aef9bb87',
             'Original trusted host input bytes differ')
        need(Path(argv[-1]).resolve() == receipt_path.resolve(), 'Process receipt path differs')
        marker = 'MOBILE_BATCH_KERNEL_COMPLETE nonce={nonce} pid={pid} mode={mode} callbacks={count}'.format(
            nonce=receipt['nonce'], pid=process['pid'], mode=mode, count=3 + receipt['sampleCount'])
        need(stdout.read_text(encoding='utf-8-sig').splitlines().count(marker) == 1, 'Original completion marker differs')
        for path in (receipt_path, process_path, stdout, stderr):
            files[str(path.resolve())] = sha(path)
        def review(value, **changes):
            bindings = {'mode': mode, 'nonce': receipt['nonce'], 'pid': process['pid'],
                        'samples': receipt['sampleCount'], 'platform': 'Windows.x64', 'component_hash': module.CONTRACT}
            bindings.update(changes)
            return module.review(value, **bindings)
        actual.append(review(receipt))
        mutations = [(('processId',), True), (('nonce',), '0' * 32), (('mode',), 'unknown'),
                     (('architecture',), 'Arm64'), (('authorHash',), '0' * 64),
                     (('loadedContractComponentHash',), '0' * 64), (('contractMvid',), '0' * 36),
                     (('Capabilities', 'policyVersion'), True), (('collected',), 1),
                     (('sampleCount',), True), (('Rows', 0, 'Index'), False),
                     (('Rows', 3, 'Checksum'), module.CHECKSUM + 1), (('Rows', 3, 'Warmup'), True),
                     (('RetiredGetterRejections',), 7), (('nativeEntryProof',), True),
                     (('liveBatchPathVerified',), True), (('performanceMeasured',), True),
                     (('physicalDeviceVerified',), True)]
        if mode == 'high-budget':
            mutations += [(('Rows', 3, 'After', 'Executed'), 0), (('Rows', 3, 'After', 'Remaining'), module.LIMIT),
                          (('Rows', 3, 'After', 'Phase'), False), (('Rows', 3, 'Before', 'CleanupExecuted'), 1),
                          (('Rows', 3, 'DispatchDelta'), module.DISPATCHES - 1), (('Final', 'Exhausted'), True)]
        else:
            mutations += [(('Initial',), module.snapshot(0)), (('Rows', 3, 'DispatchDelta'), module.DISPATCHES)]
        for keys, value in mutations:
            altered = copy.deepcopy(receipt)
            target = altered
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = value
            try:
                review(altered)
            except RuntimeError:
                rejected.append(mode + ':' + '.'.join(map(str, keys)))
            else:
                raise RuntimeError('Altered receipt accepted: ' + repr(keys))
        for label, mutate in (('missing-row', lambda r: r['Rows'].pop()),
                              ('reordered-row', lambda r: r['Rows'].reverse()),
                              ('unexpected-native-promotion', lambda r: r.update(nativeVerified=True))):
            altered = copy.deepcopy(receipt)
            mutate(altered)
            try:
                review(altered)
            except RuntimeError:
                rejected.append(mode + ':' + label)
            else:
                raise RuntimeError('Altered structure accepted: ' + label)
        try:
            review(receipt, samples=True)
        except RuntimeError:
            rejected.append(mode + ':boolean-sample-binding')
        else:
            raise RuntimeError('Boolean expected sample count accepted')
    for label, value in (('duplicate', '{"key":1,"key":2}'), ('non-finite', '{"key":NaN}')):
        path = args.output / (label + '.json')
        path.write_text(value, encoding='ascii')
        try:
            module.load(path)
        except RuntimeError:
            rejected.append(label + '-json')
        else:
            raise RuntimeError('Malformed JSON accepted: ' + label)
    for path in (Path(__file__), assessor):
        ast.parse(path.read_text(encoding='utf-8-sig'), feature_version=(3, 9))
    for name, expected in files.items():
        need(sha(Path(name)) == expected, 'Source receipt changed during replay')
    result = {'passed': True, 'actualReceiptReplays': len(actual),
              'callbacksReplayed': sum(row['callbacks'] for row in actual),
              'collectionsReplayed': len(actual), 'rejectionControls': len(rejected),
              'rejected': rejected, 'originalFiles': files, 'assessorSha256': sha(assessor),
              'python39SyntaxVerified': True, 'mobileExecutionVerified': False,
              'liveBatchPathVerified': False, 'performanceMeasured': False,
              'scope': 'Offline review of retained actual Windows host sanity; no process, benchmark or simulator rerun.'}
    (args.output / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='ascii')
    print(json.dumps({key: value for key, value in result.items() if key not in ('rejected', 'originalFiles')}, indent=2))


if __name__ == '__main__':
    main()
