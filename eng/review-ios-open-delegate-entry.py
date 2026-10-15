#!/usr/bin/env python3
"""Review a preserved fresh-author open-delegate simulator capture offline."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

GENERAL_SHA = 'e690328cf688609d6b14d3a6b9d9d2ab638a58420c352d1eb40c3af1ee2f3053'
COMPILER_SHA = 'b36fb7482e04dbe27fe965523b2ac59a3c3622a5ed1ed58864a4244f5d1fbf0b'
BASE_COMPILER_SHA = '8bdf9a06b9b0236018300e0fb0c2bac7148a35de10403e84835d27595d62cf58'
VARIANT = 'runeclr.fresh-author.open-instance-delegate.v1'
SOURCE_HASHES = {'Private': 'c6eecd96e43788fcd9b63e5b7a8b0c6bbe8e541c484bee57ee1c1a3c23b342d9',
                 'Payload': '0080a7e6e084813a73c68524867dc8de477228435fa216c58dadc25651fc0951'}
CLOSURE = 'HostBudgetProbe.Private.dll:<>c__DisplayClass0_0.<Finite>b__0'
PATHS = {'function-entry', 'ordinary-child-dispatch', 'delegate-child-dispatch'}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def load_pinned(name, path, digest):
    need(sha(path) == digest, 'Frozen helper source differs: ' + path.name)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def capture_root(root):
    candidates = [p for p in root.iterdir() if (p / 'run-results.json').is_file()]
    need(len(candidates) == 1, 'Exactly one archived live run required')
    return candidates[0]


def verify_extra(root):
    """Additional open-delegate requirements; does not replace general review."""
    tools = root / 'source-freeze/eng'
    compiler = load_pinned('open_delegate_author_compiler',
                           tools / 'prepare-ios-open-delegate-author.py', COMPILER_SHA)
    need(sha(tools / 'prepare-ios-device-author.py') == BASE_COMPILER_SHA,
         'Baseline compiler source differs')
    capture = capture_root(root)
    compiled = capture / 'author-compilation-after-install'
    result, request = read(compiled / 'results.json'), read(compiled / 'request.json')
    need(result.get('passed') is True and result.get('authorCompilationCount') == 2
         and result.get('driverSha256') == COMPILER_SHA
         and result.get('authorIlOnly') is True and result.get('authorExecuted') is False
         and result.get('physicalDeviceExecuted') is False, 'Open-delegate compiler receipt differs')
    need(result.get('fixtureVariant') == request.get('fixtureVariant') == VARIANT
         and result.get('baselineCompilerSha256') == request.get('baselineCompilerSha256') == BASE_COMPILER_SHA
         and request.get('sourceHashes') == SOURCE_HASHES
         and request.get('inputManifestSha256') == compiler.MANIFEST
         and request.get('targetsRerun') is False, 'Compiler variant/baseline/source binding differs')
    transformed = {}
    for role, digest in SOURCE_HASHES.items():
        original = root / 'bindings/author-sources' / (role + '.cs')
        source = compiled / 'source' / (role + '.cs')
        need(sha(original) == digest, 'Frozen fixture source differs: ' + role)
        need(source.read_bytes() == compiler.variant_source(role, original.read_bytes()),
             'Compiled fixture transformation differs: ' + role)
        transformed[role] = sha(source)
        process = read(compiled / (role + '.process.json'))
        need(process.get('exitCode') == 0
             and process.get('responseSha256') == sha(compiled / (role + '.rsp'))
             and process.get('stdoutSha256') == sha(compiled / (role + '.stdout'))
             and process.get('stderrSha256') == sha(compiled / (role + '.stderr')),
             'Compiler process evidence differs: ' + role)
    need(result.get('compiledSourceHashes') == request.get('compiledSourceHashes') == transformed,
         'Compiled source hashes differ')
    entries = read(capture / 'diagnostic/interpreter-entries.json')
    observed = {entry['kind'] for entry in entries}
    need(observed == PATHS, 'All three actual interpreter entry paths required')
    closure = [entry for entry in entries if entry.get('methodGroup') == CLOSURE]
    need(len(closure) == 1, 'Exactly one original closure sample required')
    entry = closure[0]
    need(entry.get('kind') == 'delegate-child-dispatch', 'Original closure must use delegate child dispatch')
    need(entry.get('terminalPhase') == 1 and entry.get('meterGate', {}).get('phase') == 1
         and entry.get('meterTerminated') is True
         and type(entry.get('instructionMeter')) is int and entry['instructionMeter'] > 0
         and entry.get('cleanupOwner') == entry['instructionMeter'],
         'Open delegate must retain terminated phase1 cleanup ownership')
    return {'openDelegateEntryVerified': True, 'closureMethodGroup': CLOSURE,
            'closureEntryPath': entry['kind'], 'closurePhase': 1,
            'observedEntryPaths': sorted(observed), 'fixtureVariant': VARIANT,
            'fixtureCompilerSha256': COMPILER_SHA, 'compiledSourceHashes': transformed}


def review(root):
    general = load_pinned('general_fresh_author_review',
                          root / 'source-freeze/eng/review-ios-fresh-author-live.py', GENERAL_SHA)
    result = general.review(root)
    need(result.get('passed') is True, 'General fresh-author archive review failed')
    result.update(verify_extra(root))
    result['generalReviewerSha256'] = GENERAL_SHA
    result['reviewerSha256'] = sha(Path(__file__))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = review(args.archive_root.resolve())
    if args.output:
        with args.output.open('x', encoding='ascii') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
