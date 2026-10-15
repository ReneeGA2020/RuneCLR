#!/usr/bin/env python3
"""Recompute direct-callback timestamps without claiming mobile comparative performance."""
import argparse
import copy
import hashlib
import importlib.util
import json
import math
import statistics
from pathlib import Path

KERNEL_SHA = '8fc1563dede9273f6c2a2f065fdf8ceb6afe86130d975cbf9826a180b91deacf'
TIMING_KEYS = ('lane', 'requestedSettings', 'stopwatchFrequency', 'stopwatchIsHighResolution',
               'callbackTimingObserved', 'timingScope', 'baseline')
ROW_TIMING_KEYS = ('StartedTimestamp', 'FinishedTimestamp', 'ElapsedTicks', 'Seconds')
TIMING_SCOPE = 'Stopwatch timestamps surround only the direct frozen Kernel.Execute delegate invocation.'


def kernel():
    path = Path(__file__).with_name('assess-mobile-batch-kernel.py')
    if hashlib.sha256(path.read_bytes()).hexdigest() != KERNEL_SHA:
        raise RuntimeError('Frozen scalar assessor differs')
    spec = importlib.util.spec_from_file_location('strict_kernel_scalar', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def settings(lane):
    return {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0', 'DOTNET_ReadyToRun': '1',
            'DOTNET_TieredCompilation': '0', 'DOTNET_MULTILEVEL_LOOKUP': '0', 'DOTNET_RuneCLRPhaseAcquireLoad': '1',
            'DOTNET_RuneCLRDerivedLedger': '1' if lane == 'best-exact' else '0',
            'DOTNET_RuneCLRBatchInterval': {'no-config': '0', 'best-exact': '0', 'N100': '64', 'N1000': '3e8'}[lane]}


def review(receipt, mode, lane, nonce, pid, samples, platform, component_hash):
    scalar = kernel()
    need = scalar.need
    need(lane in ('no-config', 'best-exact', 'N100', 'N1000'), 'Unsupported timing lane')
    need(not (mode == 'high-budget' and lane == 'no-config'), 'Meter-free lane cannot select a meter')
    need(type(receipt) is dict and receipt.get('schema') == 'runeclr.mobile-batch-timing.observation.v1',
         'Timing observation schema differs')
    need('performanceMeasured' not in receipt, 'Unexpected comparative timing claim')
    need(receipt.get('lane') == lane and receipt.get('timingScope') == TIMING_SCOPE, 'Lane/timing scope differs')
    scalar.same(receipt.get('requestedSettings'), settings(lane), 'requestedSettings')
    frequency = receipt.get('stopwatchFrequency')
    need(type(frequency) is int and frequency > 0, 'Invalid monotonic frequency')
    need(receipt.get('stopwatchIsHighResolution') is True and receipt.get('callbackTimingObserved') is True,
         'High-resolution callback timing acknowledgement missing')
    need(type(receipt.get('baseline')) is str and bool(receipt['baseline']), 'Timing baseline scope missing')
    adapted = copy.deepcopy(receipt)
    for key in TIMING_KEYS:
        del adapted[key]
    adapted['schema'] = 'runeclr.mobile-batch-kernel.observation.v1'
    adapted['performanceMeasured'] = False
    need(type(adapted.get('Rows')) is list, 'Timing callback rows missing')
    for row in adapted['Rows']:
        need(type(row) is dict, 'Timing callback row is not an object')
        for key in ROW_TIMING_KEYS:
            need(key in row, 'Timing row field missing: ' + key)
            del row[key]
    scalar.review(adapted, mode, nonce, pid, samples, platform, component_hash)
    previous_end, measured = None, []
    for row in receipt['Rows']:
        start, end, elapsed, seconds = (row[key] for key in ROW_TIMING_KEYS)
        need(all(type(value) is int for value in (start, end, elapsed)), 'Timestamp JSON types differ')
        need(0 <= start < end and elapsed == end - start, 'Raw timestamp delta differs')
        need(previous_end is None or start >= previous_end, 'Sequential callbacks overlap or timestamps go backwards')
        need(type(seconds) in (float, int) and math.isfinite(seconds) and seconds > 0
             and math.isclose(seconds, elapsed / frequency, rel_tol=1e-12, abs_tol=0),
             'Seconds do not match raw ticks/frequency')
        previous_end = end
        if not row['Warmup']:
            measured.append(elapsed / frequency * 1000)
    return {'passed': True, 'platform': platform, 'processId': pid, 'nonce': nonce, 'mode': mode, 'lane': lane,
            'callbacks': samples + 3, 'collections': 1, 'measuredSamples': len(measured),
            'callbackMilliseconds': measured, 'callbackMedianMilliseconds': statistics.median(measured),
            'scalarLedgerVerified': True, 'rawCallbackTimingVerified': True, 'performanceVerified': False,
            'mobileExecutionVerified': False, 'nativeEntryProof': False, 'liveBatchPathVerified': False,
            'physicalDeviceVerified': False,
            'scope': 'One observation: typed scalar ledgers and raw monotonic callback timings only; launch/product/debugger-free provenance and multi-process comparison remain external.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--mode', choices=('no-config', 'high-budget'), required=True)
    parser.add_argument('--lane', choices=('no-config', 'best-exact', 'N100', 'N1000'), required=True)
    parser.add_argument('--nonce', required=True)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--samples', type=int, required=True)
    parser.add_argument('--platform', choices=tuple(kernel().ARCHITECTURES), required=True)
    parser.add_argument('--component-hash', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = review(kernel().load(args.receipt), args.mode, args.lane, args.nonce, args.pid, args.samples,
                    args.platform, args.component_hash)
    result['receiptSha256'] = hashlib.sha256(args.receipt.read_bytes()).hexdigest()
    result['assessorSha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        with args.output.open('x', encoding='ascii') as stream:
            stream.write(text)
    print(text, end='')


if __name__ == '__main__':
    main()
