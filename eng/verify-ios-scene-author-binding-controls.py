#!/usr/bin/env python3
"""Reject stale child/author provenance using copied receipts without target execution."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('app', 'build-directory', 'app-review', 'authors', 'previous-authors', 'binding-review', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    path = Path(__file__).with_name('verify-ios-scene-author-binding.py')
    spec = importlib.util.spec_from_file_location('scene_author_binding_controls', path)
    tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)
    original = tool.helper(); read, need = original.read, original.need
    accepted = read(args.binding_review)
    need(accepted['passed'] and accepted['reviewDriverSha256'] == tool.sha(path)
         and accepted['authorRequestSha256'] == tool.sha(args.authors / 'request.json')
         and accepted['authorResultsSha256'] == tool.sha(args.authors / 'results.json'),
         'Actual passing current new author binding review required')
    need(not args.output.exists(), 'Fresh copied-control output required')
    args.output.mkdir(parents=True)
    review_sha = tool.sha(args.app_review)
    tool.build_binding(args.build_directory, args.app_review, review_sha, original)
    controls = []

    def reject(name, action):
        try:
            action()
        except (RuntimeError, ValueError, KeyError) as error:
            controls.append(dict(name=name, rejected=True, reason=str(error), copiedOrInMemoryOnly=True))
        else:
            controls.append(dict(name=name, rejected=False))

    reject('wrong-approved-application-review-hash', lambda: tool.build_binding(
        args.build_directory, args.app_review, '0' * 64, original))
    for name, change in {
        'coherent-old-parent-review': lambda r: r.update(builderResultsSha256='e437a2f78ae3a8433e5c63123f998b3032a1380f6c8afd0ca7d894191d215507'),
        'coherent-wrong-application-inventory': lambda r: r['appInventory'].update(Session='0' * 64),
        'coherent-stale-wrapper-time': lambda r: r.update(wrapperEndedUtc='2000-01-01T00:00:00Z'),
    }.items():
        altered = copy.deepcopy(read(args.app_review)); change(altered)
        copied = args.output / (name + '.json')
        copied.write_text(json.dumps(altered, indent=2) + chr(10), encoding='ascii')
        reject(name, lambda p=copied: tool.build_binding(args.build_directory, p, tool.sha(p), original))
    for name, filename, change in [
        ('timed-out-wrapper', 'wrapper.result.json', lambda r: r.update(timedOut=True)),
        ('failed-wrapper', 'wrapper.result.json', lambda r: r.update(exitCode=1)),
        ('changed-raw-wrapper-stream', None, None),
    ]:
        copied = args.output / name; copied.mkdir()
        for relative in ('results.json', 'bundle-inventory.json', 'wrapper.result.json', 'wrapper.stdout', 'wrapper.stderr'):
            shutil.copyfile(args.build_directory / relative, copied / relative)
        if filename:
            altered = read(copied / filename); change(altered)
            (copied / filename).write_text(json.dumps(altered, indent=2) + chr(10), encoding='ascii')
        else:
            (copied / 'wrapper.stderr').write_text('unbound additional output', encoding='ascii')
        reject(name, lambda p=copied: tool.build_binding(p, args.app_review, review_sha, original))
    for name, authors, previous in [('old-author-bound-to-original-host', args.previous_authors, args.previous_authors),
                                     ('current-pair-replayed-as-previous', args.authors, args.authors)]:
        candidate = argparse.Namespace(app=args.app, build_directory=args.build_directory,
            app_review=args.app_review, app_review_sha256=review_sha, authors=authors,
            previous_authors=previous, output=args.output / name)
        reject(name, lambda a=candidate: tool.verify(a))
    need(len(controls) == 9 and all(c['rejected'] for c in controls), 'Altered child/author provenance accepted')
    report = dict(passed=True, controls=controls, rejected=len(controls),
                  bindingReviewSha256=tool.sha(args.binding_review), bindingToolSha256=tool.sha(path),
                  controlToolSha256=tool.sha(__file__), originalInputsMutated=False,
                  targetCodeExecuted=False, physicalDeviceVerified=False)
    (args.output / 'results.json').write_text(json.dumps(report, indent=2) + chr(10), encoding='ascii')
    print(json.dumps({k: v for k, v in report.items() if k != 'controls'}))


if __name__ == '__main__':
    main()
