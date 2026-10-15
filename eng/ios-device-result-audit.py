#!/usr/bin/env python3
"""Audit fixed budget lifecycle rows; local receipts alone never prove a device run."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
AUDIT_SHA = '4ecc6e1751d59d9402eeeaf4e5b155c1a44fb2617ec56aadd183d8ca59ba34d4'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def audit_rows(directory, nonce, pid, controls=False):
    helper = ROOT / 'eng/mobile-host-budget-audit.py'
    need(sha(helper) == AUDIT_SHA, 'Frozen lifecycle semantic auditor changed')
    spec = importlib.util.spec_from_file_location('fixed_device_budget_rows', helper)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    aggregate, receipts, metrics, hashes = audit.adapter(directory, nonce, pid)
    rejected = audit.negative_controls(aggregate, receipts, nonce, pid) if controls else []
    return aggregate, metrics, hashes, rejected


def match_plan(aggregate, plan):
    need(plan['schema'] == 'runeclr.ios-device.offline-run-plan.v1'
         and plan['caseSelection'] == 'all' and plan['contexts'] == 73, 'Fixed physical run plan required')
    need(aggregate['nonce'] == plan['runNonce'], 'Run result belongs to another planned launch')
    expected = [(r['scenario'], r['nonce'], r['contexts'], r['receipt']) for r in plan['cases']]
    actual = [(r['scenario'], r['nonce'], r['contexts'], r['receipt']) for r in aggregate['cases']]
    need(expected == actual, 'Run scenario identities differ from frozen plan')
    nonce = aggregate['nonce']
    need(plan['launchEnvironment'] == {'RUNECLR_BUDGET_NONCE': nonce},
         'Native launch environment differs from planned nonce')
    need(plan['appDataPaths'] == {'plugin': 'Documents/budget-plugin',
                                 'evidence': 'Documents/budget-evidence-' + nonce},
         'Device data paths differ from planned launch')
    need(plan['managedEntryArguments'] == ['<app Documents>/budget-plugin',
                                          '<app Documents>/budget-evidence-' + nonce, nonce, 'all'],
         'Managed entry arguments differ from planned launch')


def plan_controls(aggregate, plan):
    mutations = {
        'another-planned-launch': lambda p: p.update(runNonce='0' * 32
            if p['runNonce'] != '0' * 32 else '1' * 32),
        'changed-plan-case': lambda p: p['cases'][0].update(contexts=19),
        'changed-launch-environment': lambda p: p['launchEnvironment'].update(RUNECLR_BUDGET_NONCE='bad'),
        'changed-plugin-path': lambda p: p['appDataPaths'].update(plugin='Documents/other-plugin'),
        'changed-evidence-path': lambda p: p['appDataPaths'].update(evidence='Documents/old-evidence'),
        'changed-managed-arguments': lambda p: p['managedEntryArguments'].__setitem__(2, 'bad'),
    }
    rejected = []
    for name, mutation in mutations.items():
        changed = copy.deepcopy(plan)
        mutation(changed)
        try:
            match_plan(aggregate, changed)
        except RuntimeError:
            rejected.append({'name': name, 'rejected': True, 'inMemoryOnly': True})
        else:
            raise RuntimeError('Altered plan accepted: ' + name)
    return rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--nonce', required=True)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    need(not args.output.exists(), 'Fresh output required; preserve failed reviews')
    aggregate, metrics, hashes, rejected = audit_rows(args.evidence, args.nonce, args.pid, args.selftest)
    if args.plan:
        plan = read(args.plan)
        match_plan(aggregate, plan)
        if args.selftest:
            rejected.extend(plan_controls(aggregate, plan))
    result = {'schema': 'runeclr.ios-device.lifecycle-rows-review.v1', 'passed': True,
              'lifecycleRowsVerified': True, 'cases': len(metrics), 'contexts': 73,
              'nonce': args.nonce, 'processId': args.pid, 'rawResultHashes': hashes, 'metrics': metrics,
              'planSha256': sha(args.plan) if args.plan else None, 'controls': rejected,
              'physicalDeviceVerified': False, 'installedHostProven': False,
              'deliveredAuthorIdentityProven': False, 'interpreterEntryProven': False,
              'pending': ['physical target and signed-to-installed host provenance',
                          'post-install delivery/readback and actual loaded author identity',
                          'native launch/exit/log bindings and interpreted method entries'],
              'scope': 'Fixed 15-case/73-context lifecycle semantics only; receipt content does not establish transport or execution backend.',
              'auditorSha256': AUDIT_SHA, 'driverSha256': sha(Path(__file__))}
    args.output.mkdir(parents=True)
    (args.output / 'results.json').write_text(json.dumps(result, indent=2) + chr(10), encoding='ascii')
    print(json.dumps({'passed': True, 'cases': len(metrics), 'contexts': 73,
                      'corruptionControls': len(rejected), 'physicalDeviceVerified': False}))


if __name__ == '__main__':
    main()
