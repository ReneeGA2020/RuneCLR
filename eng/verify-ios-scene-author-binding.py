#!/usr/bin/env python3
"""Bind fresh fixed-source author compilation to an independently reviewed scene child."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
BINDING_SHA = '6e250c0e58044d64ed6f093fdfd08a1646a1ffb5120c5757db5aba62bc85a976'
CHILD_SHA = '38180dfc40749b4b036ad1092138ae4e4477dfcb3969de930156f87db08830a6'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def helper():
    path = Path(__file__).with_name('verify-ios-device-author-binding.py')
    if sha(path) != BINDING_SHA:
        raise ValueError('Frozen original author binding helper changed')
    spec = importlib.util.spec_from_file_location('original_author_binding', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_binding(build_dir, review_path, review_sha, original):
    need, read = original.need, original.read
    need(sha(review_path) == review_sha, 'Independent complete application review hash differs')
    build, review = read(build_dir / 'results.json'), read(review_path)
    need(sha(build_dir / 'results.json') == CHILD_SHA and build['passed'] and build['applicationBuilt']
         and build['baselineBundleAndSourcesUnchanged'] and build['onlyBundleChanges'] == ['Info.plist', 'Session']
         and not any(build[k] for k in ('coreclrNativeRebuilt', 'trustedBridgeRecompiled', 'r2rRebuilt',
                                       'compositeRelinked', 'signingChanged', 'appLaunched', 'physicalDeviceVerified')),
         'Actual successful unsigned scene-only child build required')
    need(review['passed'] and review['builderResultsSha256'] == CHILD_SHA
         and review['appInventory'] == read(build_dir / 'bundle-inventory.json')
         and sha(build_dir / 'bundle-inventory.json') == build['bundleInventorySha256'],
         'Independent full application inventory must bind this actual child')
    stage = read(build_dir / 'wrapper.result.json')
    need(stage['exitCode'] == 0 and not stage['timedOut']
         and stage['endedUtc'] == review['wrapperEndedUtc'], 'Actual wrapper completion differs from reviewed build')
    for suffix in ('stdout', 'stderr'):
        need(sha(build_dir / ('wrapper.' + suffix)) == stage[suffix + 'Sha256'],
             'Original child wrapper stream changed')
    return review, stage['endedUtc']


def verify(args):
    original = helper()
    need, read, instant = original.need, original.read, original.instant
    need(not args.output.exists(), 'Fresh scene author review output required')
    review, ended = build_binding(args.build_directory, args.app_review, args.app_review_sha256, original)
    prepare = original.module(ROOT / 'eng/prepare-ios-device-author.py', original.PREPARE_SHA, 'scene_author_prepare')
    pe = original.module(ROOT / 'eng/verify-ios-device-author.py', original.PE_REVIEW_SHA, 'scene_author_pe')
    inventory = prepare.bundle(args.app)
    request, result = read(args.authors / 'request.json'), read(args.authors / 'results.json')
    need(inventory == review['appInventory'] == request['hostBundleHashes'],
         'Actual scene application bytes differ from independent review or compilation request')
    need(Path(request['app']).resolve() == args.app.resolve(), 'Author compiler bound another application')
    need(result['passed'] and result['phase'] == request['phase'] == 'prepare'
         and result['driverSha256'] == original.PREPARE_SHA and result['deviceHostBound']
         and result['hostBundleUnchanged'] and result['postDeviceHostBuildCompiled']
         and not result['physicalDeviceExecuted'] and not result['authorExecuted'],
         'Actual unsigned-host-bound fixed-source prepare compilation required')
    bound = instant(request['boundUtc'])
    need(instant(ended) < bound and result['startedAfterHostBindingUtc'] == request['boundUtc']
         and result['nonce'] == request['nonce'] and re.fullmatch('[0-9a-f]{32}', request['nonce']),
         'Scene wrapper must finish before fresh source binding and compilation')
    manifest = read(pe.INPUTS / 'input-manifest.json')
    need(sha(pe.INPUTS / 'input-manifest.json') == request['inputManifestSha256'] == prepare.MANIFEST
         and request['sourceHashes'] == {role: manifest['sourceHashes'][name] for role, name in prepare.SOURCES.items()},
         'Fixed source input manifest differs')
    references = sorted(pe.REFS.glob('*.dll'))
    need(request['referenceHashes'] == {p.name: sha(p) for p in references}, 'Actual compiler references differ')
    contract = pe.INPUTS / 'trusted/RuneCLR.Abstractions.dll'
    comparison = review['managedComparisons'][contract.name]
    need(sha(contract) == manifest['files']['trusted/RuneCLR.Abstractions.dll'] == comparison['rawSha256']
         and sha(args.app / contract.name) == comparison['componentSha256'],
         'Actual raw compiler/R2R host contract differs from the independently compared metadata pair')
    globals_path, attribute = args.authors / 'source/GlobalUsings.cs', args.authors / 'source/AfterHostBuild.cs'
    need(globals_path.read_text() == 'global using System;' + chr(10)
         and attribute.read_text() == '[assembly: System.Reflection.AssemblyVersion("1.0.0.0")]' + chr(10)
         + '[assembly: System.Reflection.AssemblyMetadata("RuneCLR.DeviceAuthor.AfterHost", "'
         + request['nonce'] + '")]' + chr(10), 'Exact global using or fresh nonce attribute differs')
    authors, processes, last = {}, [], bound
    old = read(args.previous_authors / 'results.json')
    need(old['passed'] and old['nonce'] != request['nonce'], 'Fresh author nonce replays previous compilation')
    for role, filename in zip(('Private', 'Payload'), prepare.AUTHOR):
        process = read(args.authors / (role + '.process.json'))
        need(process['exitCode'] == 0 and last <= instant(process['startedUtc']) <= instant(process['endedUtc']),
             'Actual successful ordered compiler process required: ' + role)
        last = instant(process['endedUtc'])
        for suffix in ('stdout', 'stderr'):
            need(sha(args.authors / (role + '.' + suffix)) == process[suffix + 'Sha256'], 'Compiler stream changed')
        response = args.authors / (role + '.rsp')
        need(sha(response) == process['responseSha256'], 'Compiler response hash differs')
        argv = process['argv']
        need(len(argv) == 4 and argv[2] == '-noconfig' and argv[3] == '@' + str(response.resolve())
             and Path(argv[0]).resolve() == (pe.SDK / 'dotnet.exe').resolve()
             and Path(argv[1]).resolve() == (pe.SDK / 'sdk/11.0.100-rc.1.26425.128/Roslyn/bincore/csc.dll').resolve()
             and sha(argv[0]) == request['sdkHostSha256'] and sha(argv[1]) == request['compilerSha256'],
             'Actual explicit compiler identity differs')
        source = args.authors / 'source' / (role + '.cs')
        need(sha(source) == request['sourceHashes'][role], 'Fixed author source differs')
        path = args.authors / 'plugin' / filename
        selected = references + [contract] + ([args.authors / 'plugin/HostBudgetProbe.Private.dll'] if role == 'Payload' else [])
        expected = ['-target:library', '-nostdlib+', '-deterministic+', '-optimize+', '-debug-',
                    '-nullable:enable', '-langversion:preview', '-warnaserror+', '-out:"' + str(path.resolve()) + '"']
        expected += ['-reference:"' + str(p.resolve()) + '"' for p in selected]
        expected += ['"' + str(p.resolve()) + '"' for p in (source, globals_path, attribute)]
        need(response.read_text().splitlines() == expected, 'Actual complete compiler response differs')
        image, previous = pe.pe_methods(path), pe.pe_methods(args.previous_authors / 'plugin' / filename)
        need(image['sha256'] == result['authorHashes'][filename] and image['ilOnly']
             and image['managedNativeRva'] == image['managedNativeSize'] == 0
             and image['sha256'] != previous['sha256'] == old['authorHashes'][filename]
             and image['moduleVersionId'] != previous['moduleVersionId']
             and request['nonce'].encode('ascii') in path.read_bytes(), 'Fresh author IL-only identity or replay check failed')
        authors[filename] = {k: image[k] for k in ('sha256', 'moduleVersionId', 'ilOnly', 'references')}
        processes.append(process)
    need(set(result['authorHashes']) == set(prepare.AUTHOR) and result['authorCompilationCount'] == 2
         and prepare.bundle(args.app) == inventory, 'Exactly two authors and unchanged scene application required')
    report = dict(schema='runeclr.ios-device.scene-author-binding.v1', passed=True, appFiles=len(inventory),
                  builderResultsSha256=CHILD_SHA, independentAppReviewSha256=sha(args.app_review),
                  authorRequestSha256=sha(args.authors / 'request.json'), authorResultsSha256=sha(args.authors / 'results.json'),
                  authors=authors, compilerProcesses=processes, buildEndedUtc=ended, authorBoundUtc=request['boundUtc'],
                  deviceHostBytesBound=True, postDeviceHostBuildCompiled=True, applicationUnchanged=True,
                  physicalDeviceExecuted=False, interpreterEntryProven=False, installedHostBound=False,
                  scope='Actual new unsigned scene child byte binding and subsequent fixed-source IL compilation only.',
                  reviewDriverSha256=sha(__file__))
    args.output.mkdir(parents=True)
    (args.output / 'review.json').write_text(json.dumps(report, indent=2) + chr(10), encoding='ascii')
    print(json.dumps({k: report[k] for k in ('passed', 'appFiles', 'postDeviceHostBuildCompiled', 'physicalDeviceExecuted')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('app', 'build-directory', 'app-review', 'authors', 'previous-authors', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--app-review-sha256', required=True)
    verify(parser.parse_args())


if __name__ == '__main__':
    main()
