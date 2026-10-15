#!/usr/bin/env python3
"""Exercise independent review rejection gates against copied actual receipts."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation', type=Path, required=True)
    parser.add_argument('--measurement', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('independent', Path(__file__).with_name('review-representative-budget-independent.py'))
    review = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(review)
    review.need(not args.output.exists(), 'Fresh control output required')
    args.output.mkdir(parents=True)
    prep = review.read(args.preparation / 'preparation.json')
    measured = review.read(args.measurement / 'results.json')
    controls = []

    def rejected(name, call):
        try:
            call()
        except ValueError as error:
            controls.append({'name': name, 'rejected': True, 'reason': str(error)})
        else:
            controls.append({'name': name, 'rejected': False})

    # A wrong receipt remains wrong even if both recorded copies agree.
    for workload in ['entities', 'host-api']:
        for mode in ['no-config', 'high-budget']:
            lane = next(x for x in measured['lanes'] if x['profile'] == 'on' and x['workload'] == workload and x['mode'] == mode)
            raw = review.read(args.measurement / lane['command'])
            actual = review.read(args.measurement / lane['stdout'])
            review.receipt(actual, lane, raw)
            mutations = {
                'callback-checksum': lambda x: x['Callbacks'][0].update(Checksum=x['Callbacks'][0]['Checksum'] + 1),
                'session-checksum': lambda x: x['Samples'][0].update(Checksum=x['Samples'][0]['Checksum'] + 1),
                'uncollected-context': lambda x: x.update(sessionCollected=11),
                'author-jit-entry': lambda x: x['Proof'][0].update(Interpreted=False),
                'session-inventory': lambda x: x['Samples'][0].update(RemainingEntities=1),
                'missing-session-log': lambda x: x['Samples'][0]['Logs'].pop(),
                'callback-gc-shape': lambda x: x['Callbacks'][0].update(GcCounts=[0, 0]),
                'callback-duration': lambda x: x['Callbacks'][0].update(Milliseconds=0),
            }
            if mode == 'high-budget':
                mutations['admitted-dispatch-count'] = lambda x: x['Callbacks'][0].update(DispatchDelta=x['Callbacks'][0]['DispatchDelta'] + 1)
                mutations['terminal-latch'] = lambda x: x['Samples'][0]['Budget'].update(IsTerminated=True)
            else:
                mutations['unconfigured-count'] = lambda x: x['Callbacks'][0].update(DispatchDelta=1)
                mutations['unconfigured-meter'] = lambda x: x.update(FinalSnapshot={})
            for name, mutate in mutations.items():
                changed = copy.deepcopy(actual)
                mutate(changed)
                rejected(workload + '/' + mode + '/' + name, lambda c=changed: review.receipt(c, lane, raw))

    lane = next(x for x in measured['lanes'] if x['profile'] == 'on')
    raw = review.read(args.measurement / lane['command'])
    native = prep['buildBindings']['derived-ledger']
    review.launch_binding(args.preparation, native, lane, raw)
    for index, value in [(0, 'C:/Program Files/dotnet/dotnet.exe'), (3, '11.0.0'),
                         (4, 'D:/other/Host.dll'), (5, 'D:/other/Author.dll'), (9, '8')]:
        changed, plan = copy.deepcopy(raw), copy.deepcopy(lane)
        changed['argv'][index] = value
        plan['argv'] = changed['argv']
        rejected('coherent-argv-mutation-' + str(index), lambda c=changed, p=plan: review.launch_binding(args.preparation, native, p, c))
    for key in raw['settings']:
        changed, plan = copy.deepcopy(raw), copy.deepcopy(lane)
        changed['settings'][key] = '0' if changed['settings'][key] == '1' else '1'
        plan['settings'] = changed['settings']
        rejected('coherent-setting-mutation-' + key, lambda c=changed, p=plan: review.launch_binding(args.preparation, native, p, c))
    changed = copy.deepcopy(raw)
    changed['settings']['DOTNET_Unexpected'] = '1'
    rejected('unexpected-setting', lambda: review.launch_binding(args.preparation, native, lane, changed))
    for key, value in [('commit', '0' * 40), ('upstreamBase', '0' * 40), ('runtime', 'E:/other-runtime')]:
        changed = copy.deepcopy(native)
        changed[key] = value
        rejected('native-' + key, lambda c=changed: review.native_binding('derived-ledger', c))
    result = {'schema': 'runeclr.representative-budget.independent-review-controls.v1',
              'passed': all(x['rejected'] for x in controls), 'controls': controls,
              'rejected': sum(x['rejected'] for x in controls), 'total': len(controls),
              'reviewerSha256': review.sha(review.__file__), 'controlScriptSha256': review.sha(__file__),
              'actualReceiptPositiveControls': 4, 'actualLaunchPositiveControls': 1,
              'measurementSha256': review.sha(args.measurement / 'results.json'),
              'originalInputsMutated': False, 'timingPerformed': False}
    (args.output / 'results.json').write_text(json.dumps(result, indent=2) + chr(10))
    print(json.dumps({k: v for k, v in result.items() if k != 'controls'}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
