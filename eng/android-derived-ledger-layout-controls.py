#!/usr/bin/env python3
"""Check actual layout receipt preservation and reject prerequisite mutants."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--driver', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('layout', a.driver)
    layout = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(layout)
    root = a.root
    original = root / 'android-derived-ledger-layout-20261014-attempt1'
    descriptor = json.loads((original / 'results.json').read_text())
    request = json.loads((original / 'request.json').read_text())
    core = root / 'android-derived-ledger-release-20261014-attempt1'
    source = Path(json.loads((core / 'request.json').read_text())['source'])
    core_receipt = json.loads((core / 'results.json').read_text())
    source_receipt = json.loads((core / 'source.json').read_text())
    assert descriptor['success'] and descriptor['compositeInputCount'] == 185
    assert descriptor['compositeFileCount'] == 186 and len(descriptor['files']) == 200
    assert sha(original / 'request.json') == descriptor['requestSha256']
    assert sha(original / 'layout/layout.json') == sha(original / 'results.json')
    assert sha(a.driver) == descriptor['layoutDriverSha256']
    assert len(source_receipt['sourceHashes']) == 37
    assert all(sha(source / n) == v for n, v in source_receipt['sourceHashes'].items())
    assert all(sha(core_receipt[k]) == v for k, v in descriptor['critical7'].items())
    assert all(sha(original / 'layout' / row['path']) == row['sha256'] for row in descriptor['files'])
    assert all(sha(original / 'layout' / row['path']) == row['sha256'] for row in descriptor['receipts'])
    assert all(sha(original / 'input' / n) == v for n, v in request['compositeInputHashes'].items())
    previous = root / 'android-budget-increment-layout-20261014-attempt1/layout'
    assert layout.layout_inventory(previous) == request['previousLayoutHashes']
    assert all(sha(n) == v for n, v in request['preservedProducts'].items())
    assert len(layout.layout_inventory(original / 'layout')) == 210
    base = dict(
        build=core, review=core,
        metadata=root / 'android-derived-ledger-metadata-20261014-attempt1',
        framework=root / 'android-session-policy-release-framework-20261013-attempt2',
        toolchain=root / 'android-toolchain-r27c-20261013',
        inputs=root / 'ios-session-budget-inputs-20261013-chunked/unpacked',
        layout_helper=root / 'android-session-policy-tools-20261013/android-session-policy-layout-release-v2-20261013.py',
        metadata_inspector=root / 'ios-session-budget-tools-20261013-attempt1/RuneCLR.MetadataInspector.dll',
        validate_only=True, build_slot_granted=False)
    positive = SimpleNamespace(**base, output=a.output / 'positive-preflight')
    layout.build(positive)
    assert json.loads((positive.output / 'results.json').read_text())['success']
    controls = []
    tests = [
        ('missing-build-slot', None, None, 'Exclusive heavy-build slot required'),
        ('metadata-receipt-changed', 'metadata', 'results.json', 'Reviewed receipts changed'),
        ('helper-bytes-changed', 'layout_helper', None, 'Pinned metadata inspector/ELF helper differs'),
        ('framework-receipt-changed', 'framework', 'results.json', 'Pinned original framework receipts differ'),
        ('trusted-manifest-changed', 'inputs', 'input-manifest.json', 'Pinned trusted input manifest differs'),
    ]
    for name, key, child, expected in tests:
        args = dict(base)
        if key:
            mutant = a.output / (name + '-input')
            if child:
                mutant.mkdir()
                (mutant / child).write_bytes((base[key] / child).read_bytes() + b' ')
            else:
                mutant.write_bytes(base[key].read_bytes() + b' ')
            args[key] = mutant
        else:
            args['validate_only'] = False
        out = a.output / name
        try:
            layout.build(SimpleNamespace(**args, output=out))
            raise AssertionError('Mutant unexpectedly passed: ' + name)
        except RuntimeError as error:
            assert expected in str(error), (name, str(error))
            if key:
                result = json.loads((out / 'results.json').read_text())
                assert not result['success'] and expected in result['error']
            else:
                assert not out.exists()
            assert not (out / 'input').exists() and not (out / 'crossgen.request.json').exists()
            controls.append(dict(name=name, rejected=True, expectedError=expected, compilationPerformed=False))
    assert sha(original / 'layout/layout.json') == sha(original / 'results.json')
    assert all(sha(original / 'layout' / row['path']) == row['sha256'] for row in descriptor['files'])
    result = dict(schema='runeclr.android.derived-ledger.layout-controls.v1', success=True,
                  layoutResultSha256=sha(original / 'results.json'), driverSha256=sha(a.driver),
                  controlsDriverSha256=sha(__file__), verifiedProducts=200, verifiedReceipts=9,
                  verifiedCompositeInputs=185, verifiedSourceFiles=37, verifiedCoreProducts=7,
                  verifiedPreviousLayoutFiles=210, verifiedPreservedProducts=13,
                  positivePreflightSha256=sha(positive.output / 'results.json'), controls=controls,
                  targetExecutionVerified=False, methodEntryVerified=False, apkBuilt=False)
    (a.output / 'results.json').write_text(json.dumps(result, indent=2) + chr(10))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
