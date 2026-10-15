#!/usr/bin/env python3
"""Review post-build author IL against independently inspected unsigned app bytes."""
import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PREPARE_SHA = '8bdf9a06b9b0236018300e0fb0c2bac7148a35de10403e84835d27595d62cf58'
PE_REVIEW_SHA = '6b5d69d641c319a64f5b88cedb46434407b08f1b799184d439d4b19efc366a61'


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def instant(value):
    time = datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(time.utcoffset() is not None, 'Timezone required for build/compile ordering')
    return time


def module(path, expected, name):
    need(sha(path) == expected, 'Frozen verification helper changed: ' + path.name)
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('app', 'build-result', 'app-review', 'authors', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    need(not args.output.exists(), 'Fresh review output required')
    build, review = read(args.build_result), read(args.app_review)
    need(build['success'] and build['applicationBuilt'], 'Actual successful application build required')
    need(review['success'] and review['builderResultsSha256'] == sha(args.build_result),
         'Independent application review must bind this actual build receipt')
    prepare = module(ROOT / 'eng/prepare-ios-device-author.py', PREPARE_SHA, 'device_author_binding')
    pe = module(ROOT / 'eng/verify-ios-device-author.py', PE_REVIEW_SHA, 'device_author_pe')
    inventory = prepare.bundle(args.app)
    request, result = read(args.authors / 'request.json'), read(args.authors / 'results.json')
    need(result['passed'] and result['phase'] == request['phase'] == 'prepare'
         and result['driverSha256'] == PREPARE_SHA, 'Successful frozen prepare phase required')
    need(result['deviceHostBound'] and result['postDeviceHostBuildCompiled'] and result['hostBundleUnchanged']
         and not result['physicalDeviceExecuted'] and not result['authorExecuted'],
         'Compilation must bind an unchanged unsigned host without claiming execution')
    need(inventory == review['appInventory'] == request['hostBundleHashes'],
         'Current app bytes differ from independent review or pre-compile inventory')
    need(Path(request['app']).resolve() == args.app.resolve(), 'Author request bound another app directory')
    bound = instant(request['boundUtc'])
    need(instant(build['endedUtc']) < bound and result['startedAfterHostBindingUtc'] == request['boundUtc'],
         'Application build must finish before author source generation')
    need(result['nonce'] == request['nonce'], 'Fresh author nonce differs')
    manifest_path = pe.INPUTS / 'input-manifest.json'
    need(sha(manifest_path) == request['inputManifestSha256'] == prepare.MANIFEST,
         'Author compilation must use the frozen host-budget input manifest')
    manifest = read(manifest_path)
    need(request['sourceHashes'] == {role: manifest['sourceHashes'][name]
         for role, name in prepare.SOURCES.items()}, 'Author source pins differ from fixed fixtures')
    need(request['referenceHashes'] == {p.name: sha(p) for p in sorted(pe.REFS.glob('*.dll'))},
         'Actual private RC1 reference assemblies differ')
    authors, processes = {}, []
    last = bound
    for role, filename in zip(('Private', 'Payload'), prepare.AUTHOR):
        process = read(args.authors / (role + '.process.json'))
        need(process['exitCode'] == 0 and last < instant(process['startedUtc'])
             <= instant(process['endedUtc']), 'Actual ordered successful compiler process required: ' + role)
        last = instant(process['endedUtc'])
        for stream in ('stdout', 'stderr'):
            need(sha(args.authors / (role + '.' + stream)) == process[stream + 'Sha256'],
                 'Compiler stream changed: ' + role + ' ' + stream)
        response = args.authors / (role + '.rsp')
        need(sha(response) == process['responseSha256'], 'Compiler response changed: ' + role)
        argv = process['argv']
        need(len(argv) == 4 and argv[2] == '-noconfig' and argv[3] == '@' + str(response.resolve())
             and Path(argv[0]).resolve() == (pe.SDK / 'dotnet.exe').resolve()
             and Path(argv[1]).resolve() == (pe.SDK / 'sdk/11.0.100-rc.1.26425.128/Roslyn/bincore/csc.dll').resolve()
             and sha(Path(argv[0])) == request['sdkHostSha256']
             and sha(Path(argv[1])) == request['compilerSha256'], 'Explicit compiler identity changed: ' + role)
        need(sha(args.authors / 'source' / (role + '.cs')) == request['sourceHashes'][role],
             'Fixed author source changed: ' + role)
        path = args.authors / 'plugin' / filename
        image = pe.pe_methods(path)
        need(image['sha256'] == result['authorHashes'][filename] and image['ilOnly']
             and image['managedNativeRva'] == image['managedNativeSize'] == 0, 'Author PE must be IL-only: ' + role)
        need(request['nonce'].encode('ascii') in path.read_bytes(), 'Compiled nonce absent: ' + role)
        authors[filename] = {k: image[k] for k in ('sha256', 'moduleVersionId', 'ilOnly', 'references')}
        processes.append(process)
    need(set(result['authorHashes']) == set(prepare.AUTHOR) and result['authorCompilationCount'] == 2,
         'Exactly two fresh author assemblies required')
    need(prepare.bundle(args.app) == inventory, 'Application changed during review')
    report = {'schema': 'runeclr.ios-device.postbuild-author-review.v1', 'passed': True,
              'appFiles': len(inventory), 'builderResultsSha256': sha(args.build_result),
              'independentAppReviewSha256': sha(args.app_review), 'authorRequestSha256': sha(args.authors / 'request.json'),
              'authorResultsSha256': sha(args.authors / 'results.json'), 'authors': authors,
              'buildEndedUtc': build['endedUtc'], 'authorBoundUtc': request['boundUtc'], 'compilerProcesses': processes,
              'deviceHostBytesBound': True, 'postDeviceHostBuildCompiled': True, 'applicationUnchanged': True,
              'physicalDeviceExecuted': False, 'interpreterEntryProven': False,
              'scope': 'Unsigned device app byte binding and actual subsequent IL compilation; no installation or execution.',
              'reviewDriverSha256': sha(Path(__file__))}
    args.output.mkdir(parents=True)
    (args.output / 'review.json').write_text(json.dumps(report, indent=2) + chr(10), encoding='ascii')
    print(json.dumps({'passed': True, 'appFiles': len(inventory), 'authorAssemblies': len(authors),
                      'postDeviceHostBuildCompiled': True, 'physicalDeviceExecuted': False}))


if __name__ == '__main__':
    main()
