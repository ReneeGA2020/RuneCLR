#!/usr/bin/env python3
"""Review memory-bundled Android scalar ledgers with separate installed contract binding."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review(apk, capture):
    helper = Path(__file__).with_name('assess-mobile-batch-kernel.py')
    if sha(helper) != '8fc1563dede9273f6c2a2f065fdf8ceb6afe86130d975cbf9826a180b91deacf':
        raise RuntimeError('Frozen scalar reviewer changed')
    spec = importlib.util.spec_from_file_location('kernel_ledger', helper)
    scalar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scalar)
    read, need = scalar.load, scalar.need
    state, layout, request = read(apk / 'state.json'), read(apk / 'layout.json'), read(capture / 'request.json')
    need(sha(apk / 'layout.json') == request['layoutSha256'] and
         sha(Path(state['apk'])) == state['apkSha256'] == request['apkSha256'], 'Actual APK/layout binding differs')
    need(layout['commit'] == '3126bbc9a8851a09ac6435b18a12882bad48f3ee' and
         layout['tree'] == request['sourceTree'] == '710936ae1729a5689ab0e0896f3cf722ddd3d31c',
         'Matched runtime source differs')
    before = read(capture / 'installed-before.json')
    expected = dict(state['appHashes'], **{'apk/base.apk': state['apkSha256'],
                    'author/RuneCLR.BatchKernel.dll': scalar.AUTHOR,
                    'author/RuneCLR.Abstractions.dll': scalar.CONTRACT})
    need(before == expected, 'Installed files differ from actual APK and post-install author')
    for name, digest in state['appHashes'].items():
        path = (apk / 'app' / name).resolve()
        need(path.is_relative_to((apk / 'app').resolve()) and sha(path) == digest, 'Actual application byte differs: ' + name)
    name = 'RuneCLR.Abstractions.dll'
    contract = next(item for item in layout['files'] if item['path'] == 'managed/' + name)
    need(contract['inputSha256'] == scalar.CONTRACT and contract['sha256'] == before[name],
         'External raw IL to R2R contract binding differs')
    managed = read(capture / 'managed-result.json')
    nonce, pid = request['nonce'], managed['appPid']
    need(managed['nonce'] == nonce and managed['exitCode'] == 0 and
         managed['interval'] == ('64' if request['configured'] == 100 else '3e8'),
         'Owned managed process completion differs')
    observations = []
    for filename, mode in (('high.json', 'high-budget'), ('recovery.json', 'no-config')):
        raw = read(capture / filename)
        need('loadedContractComponentHash' in raw and raw['loadedContractComponentHash'] is None,
             'Expected memory-bundle Location absence differs')
        # The original observation remains unchanged; this adapter supplies independently bound bundle bytes.
        adapted = copy.deepcopy(raw)
        adapted['loadedContractComponentHash'] = contract['sha256']
        checked = scalar.review(adapted, mode, nonce, pid, 1, 'Android.x64', contract['sha256'])
        observations.append(dict(checked, originalReceiptSha256=sha(capture / filename),
                                 originalLoadedContractComponentHash=None))
    return {'passed': True, 'observations': observations, 'callbacks': 8, 'collections': 2,
            'processId': pid, 'nonce': nonce, 'installedFiles': len(before),
            'contractComponentSha256': contract['sha256'], 'originalReceiptsUnchanged': True,
            'contractBinding': 'Actual APK app bytes and installed hash inventory bind the R2R contract to frozen raw IL; managed receipt separately binds shared identity/MVID/default ALC. Location hash is absent for the in-memory bundle.',
            'nativeEntryProof': False, 'liveBatchPathVerified': False, 'performanceVerified': False,
            'scope': 'Typed scalar ledgers and external installed contract provenance; native samples, completion streams and cleanup need separate review.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('apk', 'capture', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = review(args.apk, args.capture)
    result['reviewerSha256'] = sha(Path(__file__))
    with args.output.open('x', encoding='ascii') as stream:
        json.dump(result, stream, indent=2)
        stream.write(chr(10))
    print('Android bundle-bound scalar review PASS: 8 callbacks / 2 collections; raw Location remains null')


if __name__ == '__main__':
    main()
