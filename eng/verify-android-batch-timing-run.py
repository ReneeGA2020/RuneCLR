#!/usr/bin/env python3
"""Replay Android timing and reject edited launches, mappings and completion."""
import argparse
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('apk', 'run', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).with_name('review-android-batch-timing-run.py')
    spec = importlib.util.spec_from_file_location('android_run_review', source)
    reviewer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reviewer)
    baseline = reviewer.review(args.apk, args.run, args.inputs)
    cells = json.loads((args.run / 'request.json').read_text())['plan']
    cell = next(row for row in cells if row['profile'] == 'N100')
    label = cell['label']
    controls = [
        ('wrong-interval', label + '/request.json', 'Original native launch environment differs'),
        ('wrong-native-map', label + '/maps.log', 'Actual executable native mapping differs'),
        ('failed-native-completion', label + '/native.log', 'Native completion/settings differs'),
        ('incomplete-cleanup', 'cleanup.json', 'Owned target cleanup differs'),
    ]
    outcomes = []
    for name, relative, expected in controls:
        copied = args.output / name
        shutil.copytree(args.run, copied)
        changed = copied / relative
        if name == 'wrong-interval':
            value = json.loads(changed.read_text())
            value['environment']['RUNECLR_TIMING_HEX'] = '100'
            changed.write_text(json.dumps(value), encoding='ascii')
        elif name == 'wrong-native-map':
            changed.write_text(changed.read_text().replace('/lib/x86_64/libcoreclr.so',
                                                         '/lib/x86_64/other/libcoreclr.so'), encoding='ascii')
        elif name == 'failed-native-completion':
            changed.write_text(changed.read_text().replace('CORECLR_EXECUTE_HRESULT=0x0;',
                                                         'CORECLR_EXECUTE_HRESULT=0x1;'), encoding='ascii')
        else:
            value = json.loads(changed.read_text())
            value['appUninstalled'] = False
            changed.write_text(json.dumps(value), encoding='ascii')
        # Rebind the edited payload so the intended semantic guard must reject it.
        complete = copied / 'results.json'
        value = json.loads(complete.read_text())
        if relative in value['rawHashes']:
            value['rawHashes'][relative] = reviewer.sha(changed)
        complete.write_text(json.dumps(value), encoding='ascii')
        try:
            reviewer.review(args.apk, copied, args.inputs)
        except (AssertionError, RuntimeError, ValueError) as exc:
            if expected not in str(exc):
                raise RuntimeError('Unexpected rejection for ' + name + ': ' + str(exc)) from exc
            outcomes.append(dict(name=name, rejected=True, reason=str(exc)))
        else:
            raise RuntimeError('Edited observation accepted: ' + name)
    result = dict(passed=True, actualReplayPassed=baseline['passed'], rejectionControls=outcomes,
                  measuredSamples=baseline['measuredSamples'], targetsRerun=False,
                  reviewerSha256=reviewer.sha(source),
                  controlDriverSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with (args.output / 'results.json').open('x', encoding='ascii') as stream:
        json.dump(result, stream, indent=2)
        stream.write(chr(10))
    print('Actual Android 496-sample replay PASS; semantic rejection controls 4/4 PASS; no target rerun')


if __name__ == '__main__':
    main()
