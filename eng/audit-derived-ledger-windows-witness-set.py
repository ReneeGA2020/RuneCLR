#!/usr/bin/env python3
"""Join four immutable normal admitted-ledger witnesses offline, without launching code."""
import argparse
import importlib.util
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    auditor = Path(__file__).with_name('audit-derived-ledger-windows-witness.py')
    spec = importlib.util.spec_from_file_location('derived_join_audit', auditor)
    audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
    audit.require(not args.output.exists(), 'Fresh joined receipt')
    bound, lanes, fixtures, pids, nonces, builds, owned = {}, [], [], [], [], [], []
    for flag in (0, 1):
        for scenario in ('Good', 'TightLoop'):
            lane = args.root / (('on' if flag else 'off') + '-' + scenario)
            result = audit.review(lane)
            audit.require(result == audit.load(lane / 'results.json'), 'Replayed original completed lane receipt')
            request = audit.load(lane / 'request.json'); process = audit.load(lane / 'process.json')
            audit.require(result['actualMeterFlag'] == request['derivedFlag'] == flag and result['scenario'] == scenario,
                          'Actual profile/scenario joined inventory')
            for name, digest in request['inputHashes'].items():
                audit.require(name not in bound or bound[name] == digest, 'Shared input agrees across lanes')
                bound[name] = digest
            for name in ('request.json', 'execution.json', 'process.json', 'results.json', 'driver.py', 'auditor.py',
                         'native-profile.json', 'initial.cdb', 'loaded.cdb', 'cdb.stdout', 'cdb.stderr', 'evidence/result.json'):
                bound[str(lane.resolve() / name)] = audit.sha(lane / name)
            fixtures.append({name: digest for name, digest in request['inputHashes'].items()
                             if '/host/' in name.replace(chr(92), '/') or '/payload/' in name.replace(chr(92), '/')})
            builds.append((request['candidateCommit'], request['buildResultSha256'], request['layoutReceiptSha256']))
            pids.append(result['actualTargetPid']); nonces.append(result['nonce'])
            owned.extend((result['actualTargetPid'], process['controllerPid']))
            lanes.append({'derivedFlag': flag, 'scenario': scenario, 'pid': result['actualTargetPid'], 'nonce': result['nonce'],
                          'actualMeterFlag': flag, 'normalAdmittedBranchObserved': result['normalAdmittedBranchObserved'],
                          'rawCounterExpected': result['rawCounterExpected'], 'ledgerVerified': result['ledgerVerified'],
                          'contextCollected': result['contextCollected'], 'negativeControls': len(result['negativeControlsRejected'])})
    audit.require(len(set(pids)) == len(set(nonces)) == 4 and all(x == fixtures[0] for x in fixtures) and
                  all(x == builds[0] for x in builds), 'Four distinct processes, identical fixture and actual build')
    expected_runtime = {'coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll', 'coreclr.pdb'}
    audit.require(expected_runtime <= {Path(name).name for name in bound}, 'Actual build runtime DLLs and PDB bound')
    report = {'passed': True, 'candidateCommit': builds[0][0], 'buildResultSha256': builds[0][1], 'layoutReceiptSha256': builds[0][2],
              'processes': 4, 'collections': 4, 'actualOnOffHotLoopBranches': True, 'sameFixtureNativeManagedInputs': True,
              'corruptionControlsRejected': sum(x['negativeControls'] for x in lanes), 'lanes': lanes, 'boundFiles': bound,
              'meterSize': 64, 'fieldOffsets': {'derivedFlag': 3, 'initialExecutionLimit': 48, 'initialCleanupLimit': 56},
              'auditorSha256': audit.sha(auditor), 'joinerSha256': audit.sha(__file__), 'ownedProcessIds': owned,
              'benchmark': False, 'scope': 'Four selected first normal admissions; no cleanup live branch, exhaustive trace or timing.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + chr(10))
    print(json.dumps({key: value for key, value in report.items() if key not in ('boundFiles', 'ownedProcessIds')}, indent=2))

if __name__ == '__main__':
    main()
