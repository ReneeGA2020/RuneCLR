#!/usr/bin/env python3
"""Reject altered actual fresh-simulator receipts without launching target code."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import plistlib
import struct


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('experiment', 'review', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('independent_fresh_sim', Path(__file__).with_name('review-ios-fresh-author-simulator.py'))
    review = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(review)
    review.need(not args.output.exists(), 'Fresh independent control output required')
    args.output.mkdir(parents=True)
    accepted = review.read(args.review)
    review.need(accepted['passed'] and accepted['reviewerSha256'] == review.sha(review.__file__), 'Actual passing current independent review required')
    root, run = args.experiment, args.experiment / 'run-all'
    state, owned = review.read(root / 'state.json'), review.read(root / 'owned-simulator.json')
    previous = Path(accepted['previousExperiment']) if accepted.get('previousExperiment') else None
    build_request = review.read((previous if previous else root) / 'request.json')
    build = review.read(root / 'matching-build.json')
    active_builder = accepted['activeBuildDriverSha256']
    install = review.read(root / 'installation/results.json')
    launch, request, transfer = review.read(run / 'launch.result.json'), review.read(run / 'request.json'), review.read(run / 'transfer.json')
    before, after = review.read(run / 'installed-before.json'), review.read(run / 'installed-after.json')
    compilation = review.read(Path(accepted['authorReviewPath']))
    rows = review.helper('fixed_controls', 'mobile-host-budget-audit.py', review.ROWS_SHA)
    aggregate, receipts, _, _ = rows.adapter(run / 'adapter-evidence', accepted['nonce'], accepted['processId'])
    controls = rows.negative_controls(aggregate, receipts, accepted['nonce'], accepted['processId'])

    def reject(name, call):
        try:
            call()
        except (ValueError, AssertionError, KeyError) as error:
            controls.append({'name': name, 'rejected': True, 'reason': str(error), 'copiedOrInMemoryOnly': True})
        else:
            controls.append({'name': name, 'rejected': False})

    review.ordering(install, compilation, transfer, launch)
    for name, mutate in {
        'compile-before-install': lambda c, t, l: c.update(authorBoundUtc='2000-01-01T00:00:00Z'),
        'transfer-before-new-compile': lambda c, t, l: t.update(startedUtc=install['installEndedUtc']),
        'launch-before-copy': lambda c, t, l: l.update(startedUtc=install['installEndedUtc']),
    }.items():
        c, t, l = copy.deepcopy(compilation), copy.deepcopy(transfer), copy.deepcopy(launch)
        mutate(c, t, l)
        reject(name, lambda c=c, t=t, l=l: review.ordering(install, c, t, l))
    review.transported_author(transfer, before, after, accepted['authorIdentities'])
    for name, changed in [('coherent-wrong-delivered-author', {n: '0' * 64 for n in review.PREVIOUS_AUTHOR}),
                          ('coherent-old-author-replay', {n: v[0] for n, v in review.PREVIOUS_AUTHOR.items()}),
                          ('coherent-missing-private', {n: v for n, v in before['author'].items() if 'Private' not in n})]:
        t, b, a = copy.deepcopy(transfer), copy.deepcopy(before), copy.deepcopy(after)
        t['authorHashes'] = b['author'] = a['author'] = changed
        reject(name, lambda t=t, b=b, a=a: review.transported_author(t, b, a, accepted['authorIdentities']))
    review.launch_identity(request, owned, state, active_builder)
    for name, mutate in {
        'promoted-physical': lambda r: r.update(physicalDeviceExecuted=True),
        'debugger-launch': lambda r: r.update(debugger=True),
        'another-simulator': lambda r: r.update(simulator='00000000-0000-0000-0000-000000000000'),
        'another-bundle': lambda r: r.update(bundleId='other.bundle'),
        'two-launches': lambda r: r.update(launchCount=2),
        'extra-launch-switch': lambda r: r['environment'].update(SIMCTL_CHILD_DOTNET_InterpMode='3'),
        'wrong-continuation': lambda r: r.update(driverSha256=review.BUILDER_SHA),
    }.items():
        changed = copy.deepcopy(request); mutate(changed)
        reject(name, lambda c=changed: review.launch_identity(c, owned, state, active_builder))
    review.build_identity(build_request, build)
    for name, mutate in {
        'wrong-native-commit': lambda r, b: (r.update(sourceCommit='0' * 40), b.update(commit='0' * 40)),
        'wrong-native-tree': lambda r, b: (r.update(sourceTree='0' * 40), b.update(tree='0' * 40)),
        'batching-promoted': lambda r, b: r['configuration'].update(RuneCLRBatchInterval='64'),
        'physical-build-promoted': lambda r, b: r.update(physicalDeviceExecuted=True),
        'trusted-host-recompiled': lambda r, b: r.update(trustedHostRecompiled=True),
        'wrong-native-product': lambda r, b: b.update(nativeSha256='0' * 64),
    }.items():
        changed, bb = copy.deepcopy(build_request), copy.deepcopy(build); mutate(changed, bb)
        reject(name, lambda c=changed, b=bb: review.build_identity(c, b))
    if previous:
        scene_request = review.read(root / 'request.json')
        review.scene_scope_identity(scene_request, state)
        for name, mutate in {
            'scene-source-commit-changed': lambda r, s: r.update(sourceCommit='0' * 40),
            'scene-source-tree-changed': lambda r, s: r.update(sourceTree='0' * 40),
            'scene-builder-changed': lambda r, s: r.update(driverSha256=review.BUILDER_SHA),
            'scene-main-source-relabeled': lambda r, s: (r.update(sceneMainSourceSha256='0' * 64), s.update(sceneMainSha256='0' * 64)),
            'scene-runtime-rebuild-promoted': lambda r, s: r.update(runtimeRebuilt=True),
            'scene-host-rebuild-promoted': lambda r, s: r.update(trustedHostRecompiled=True),
            'scene-r2r-rebuild-promoted': lambda r, s: r.update(r2rRebuilt=True),
            'scene-device-repair-promoted': lambda r, s: r.update(deviceAppRepaired=True),
            'scene-physical-execution-promoted': lambda r, s: r.update(physicalDeviceExecuted=True),
            'scene-native-entry-promoted': lambda r, s: s.update(nativeEntryProof=True),
        }.items():
            changed, ss = copy.deepcopy(scene_request), copy.deepcopy(state); mutate(changed, ss)
            reject(name, lambda c=changed, s=ss: review.scene_scope_identity(c, s))
        main_bytes = (root / 'main.m').read_bytes()
        info = plistlib.loads((root / 'app/Session.app/Info.plist').read_bytes())
        review.scene_contract(main_bytes, info)
        reject('original-no-scene-main-replay', lambda: review.scene_contract((previous / 'main.m').read_bytes(), info))
        for name, mutate in {
            'missing-scene-manifest': lambda i: i.pop('UIApplicationSceneManifest'),
            'changed-scene-manifest': lambda i: i['UIApplicationSceneManifest'].update(UIApplicationSupportsMultipleScenes=True),
        }.items():
            changed = copy.deepcopy(info); mutate(changed)
            reject(name, lambda c=changed: review.scene_contract(main_bytes, c))
        old_bundle = review.inventory(previous / 'app/Session.app')
        scene_bundle = review.inventory(root / 'app/Session.app')
        review.scene_bundle_diff(old_bundle, scene_bundle)
        for name, mutate in {
            'scene-repair-changed-framework': lambda i: i.update({'framework.dylib': '0' * 64}),
            'scene-repair-changed-coreclr': lambda i: i.update({'libcoreclr.dylib': '0' * 64}),
            'scene-repair-changed-trusted-component': lambda i: i.update({'RuneCLR.Runtime.dll': '0' * 64}),
            'scene-repair-added-author': lambda i: i.update({'HostBudgetProbe.Payload.dll': '0' * 64}),
            'scene-repair-unchanged-main': lambda i: i.update({'Session': old_bundle['Session']}),
        }.items():
            changed = copy.deepcopy(scene_bundle); mutate(changed)
            reject(name, lambda c=changed: review.scene_bundle_diff(old_bundle, c))
        for name, value in [('failed-attempt1-author-replay',
                review.read(previous / 'run-all/transfer.json')['authorHashes'])]:
            t, b, a = copy.deepcopy(transfer), copy.deepcopy(before), copy.deepcopy(after)
            t['authorHashes'] = b['author'] = a['author'] = value
            reject(name, lambda: review.transported_author(t, b, a, accepted['authorIdentities']))
    text = (run / 'launch.stdout').read_text() + (run / 'launch.stderr').read_text()
    pid, nonce = accepted['processId'], accepted['nonce']
    review.markers(text, nonce, pid, state['bundleId'])
    native_marker = 'FRESH_AUTHOR_SIM_NATIVE pid=' + str(pid) + ' nonce=' + nonce + ' PhaseAcquireLoad=1 DerivedLedger=1 BatchInterval=0 InterpMode=0 InterpretCollectible=0 ReadyToRun=1'
    managed_marker = 'MOBILE_HOST_BUDGET_COMPLETE nonce=' + nonce + ' scenario=all pid=' + str(pid) + ' cases=15 contexts=73 passed=true'
    for name, changed in [
        ('duplicate-native-marker', text + chr(10) + native_marker + chr(10)),
        ('duplicate-managed-marker', text + chr(10) + managed_marker + chr(10)),
        ('native-wrong-pid', text.replace(native_marker, native_marker.replace('pid=' + str(pid), 'pid=' + str(pid + 1)))),
        ('native-trailing-text', text.replace(native_marker, native_marker + ' extra')),
        ('native-unrelated-prefix', text.replace(native_marker, 'unexpected ' + native_marker)),
        ('managed-wrong-nonce', text.replace(managed_marker, managed_marker.replace(nonce, '0' * 32))),
    ]:
        reject(name, lambda c=changed: review.markers(c, nonce, pid, state['bundleId']))
    source = review.native_image(root / 'unsigned-native/libcoreclr.dylib')
    signed = review.native_image(root / 'app/Session.app/libcoreclr.dylib')
    review.source_native_binding(source, signed)
    for name, mutate in {
        'signed-code-section-changed': lambda r: next(iter(r['sections'].values())).update(sha256='0' * 64),
        'signed-native-uuid-changed': lambda r: r.update(uuids=['0' * 32]),
        'signed-dependency-changed': lambda r: r['dependencies'].append('/tmp/other.dylib'),
    }.items():
        changed = copy.deepcopy(signed); mutate(changed)
        reject(name, lambda c=changed: review.source_native_binding(source, c))
    image = bytearray((root / 'unsigned-native/libSystem.Native.dylib').read_bytes())
    cursor, platform_at = 32, None
    for _ in range(struct.unpack_from('<I', image, 16)[0]):
        command, size = struct.unpack_from('<II', image, cursor)
        if command == 0x32: platform_at = cursor + 8
        cursor += size
    review.need(platform_at is not None, 'Actual native platform command required for binary controls')
    for name, offset, value in [('device-platform-in-simulator-image', platform_at, 2),
                                ('macos-platform-in-simulator-image', platform_at, 1),
                                ('incompatible-simulator-minimum', platform_at + 4, 0x00100300)]:
        changed = bytearray(image); struct.pack_into('<I', changed, offset, value)
        copied = args.output / (name + '.dylib'); copied.write_bytes(changed)
        reject(name, lambda p=copied: review.native_image(p))
    result = {'schema': 'runeclr.ios-fresh-author.simulator-independent-controls.v1',
              'passed': all(x['rejected'] for x in controls), 'total': len(controls),
              'rejected': sum(x['rejected'] for x in controls), 'controls': controls,
              'reviewerSha256': review.sha(review.__file__), 'controlScriptSha256': review.sha(__file__),
              'actualReviewSha256': review.sha(args.review), 'physicalDeviceExecuted': False,
              'originalInputsMutated': False, 'targetCodeExecuted': False}
    (args.output / 'results.json').write_text(json.dumps(result, indent=2) + chr(10))
    print(json.dumps({k: v for k, v in result.items() if k != 'controls'}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
