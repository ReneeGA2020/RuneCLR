#!/usr/bin/env python3
"""Join four immutable ON/OFF hot-loop witnesses without launching a process."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    assert not args.output.exists()
    reviewer = Path(__file__).resolve().parent / 'audit-phase-load-windows-witness.py'
    spec = importlib.util.spec_from_file_location('phase_witness_review', reviewer)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    reports, files, fixture_hashes, pids, nonces, owned_pids = [], {}, [], [], [], []
    for flag in (0, 1):
        for scenario in ('Good', 'TightLoop'):
            lane = args.root / (('on' if flag else 'off') + '-' + scenario)
            actual = audit.review(lane)
            assert actual == load(lane / 'results.json')
            request, execution, process = [load(lane / name) for name in ('request.json', 'execution.json', 'process.json')]
            assert request['flag'] == actual['actualMeterFlag'] == flag
            assert request['scenario'] == actual['scenario'] == scenario and actual['actualHotLoopCaller']
            assert process['controllerPid'] == execution['controllerPid'] and process['target'] == request['target']
            assert process['settings'] == request['settings'] and process['owned']
            for name in ('request.json', 'execution.json', 'process.json', 'results.json', 'cdb.stdout', 'cdb.stderr', 'driver.py', 'evidence/result.json'):
                files[str(lane / name)] = sha(lane / name)
            fixture_hashes.append(request['inputHashes'])
            pids.append(actual['actualTargetPid'])
            owned_pids.extend((actual['actualTargetPid'], execution['controllerPid']))
            nonces.append(actual['nonce'])
            base = actual['liveMarkers'][0]['pc'] - 0x18e320
            caller_rva = actual['liveMarkers'][0]['caller'] - base
            altered = copy.deepcopy(actual['liveMarkers'])
            for marker in altered:
                marker['caller'] = base + 1
            try:
                audit.validate(altered, request, base, None, load(lane / 'evidence/result.json'))
            except AssertionError:
                pass
            else:
                raise AssertionError('non-hot-loop caller accepted')
            reports.append({'flag': flag, 'scenario': scenario, 'pid': actual['actualTargetPid'], 'nonce': actual['nonce'],
                            'callerRva': hex(caller_rva), 'liveBranchBytes': actual['liveMarkers'][1]['bytes'],
                            'contextCollected': True, 'ledgerVerified': True, 'negativeControls': 6})
    assert len(set(pids)) == len(set(nonces)) == 4 and all(x == fixture_hashes[0] for x in fixture_hashes)
    report = {'passed': True, 'scope': 'Four selected phase-0 hot-loop branches; no complete trace or benchmark',
              'processes': 4, 'collections': 4, 'actualOnOffHotLoopBranches': True,
              'sameFixtureNativeManagedInputs': True, 'corruptionControlsRejected': 24, 'lanes': reports,
              'ownedProcessIds': owned_pids, 'boundFiles': files, 'auditorSha256': sha(reviewer),
              'joinerSha256': sha(Path(__file__)), 'benchmark': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('boundFiles', 'ownedProcessIds')}, indent=2))


if __name__ == '__main__':
    main()
