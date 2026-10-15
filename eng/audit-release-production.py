#!/usr/bin/env python3
"""Independently review Release functional raw rows and frozen input bindings."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess

BASELINE = '099dacd07d8d890822f7422f895337733457ab3c'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def require(value, message):
    if not value:
        raise RuntimeError(message)


def check_hashes(hashes):
    for path, expected in hashes.items():
        require(sha(path).lower() == expected.lower(), 'Input changed: ' + path)


def assess(row, text):
    name = row['name']
    require(row['passed'] and not row['timedOut'], 'Failure or timeout: ' + name)
    require(row['exitCode'] == (100 if name.startswith('official-') else 0), 'Unexpected exit: ' + name)
    require(not row['methodEntryProof'], 'Functional run falsely claims method-entry proof')
    require(not re.search('Assert failure|Fatal error|Unhandled exception|Failure -|Failed to unload', text), 'Fatal body text')
    if name.startswith('official-'):
        require(not row['skipped'] and row['originalAssertions'], 'Skipped or modified official test')
        if name.endswith('ByRefLocals'):
            require(len(re.findall(r'^1\r?$', text, re.M)) == 20, 'ByRef body incomplete')
        if name.endswith('ResolvedFromDifferentContext'):
            require(len(re.findall(r'^Running test case (ResolvingEvent|LoadOverride|ResolvingEventInNonCollectible|LoadOverrideInNonCollectible)\r?$', text, re.M)) == 4, 'Resolving body incomplete')
            require(text.count('TestInterface.Class.Test') == 2, 'Successful resolving payload bodies missing')
    else:
        require('SESSION_EXECUTION_POLICY required-interpreter version=1' in text, 'Policy not acknowledged')
        require('--require-interpreter' in row['command'], 'Required factory not requested')
        if name in ('lifecycle', 'package-execution'):
            expected = 24 if name == 'lifecycle' else 15
            marker = '24/24 tests passed' if name == 'lifecycle' else '15/15 package execution tests passed'
            require(marker in text and len(re.findall('^PASS ', text, re.M)) == expected, 'Harness business rows incomplete')
        else:
            expected = 1 if name == 'late-sample' else 3
            require(text.count('unload: collected') == expected and text.count('remaining=0') == expected, 'Sample collection/resource rows incomplete')
            require(len(re.findall(r'Completed; ticks=3', text)) == expected, 'Sample completion rows incomplete')
            if name == 'late-sample':
                require('late-map=42' in text, 'Late IL body marker absent')
            if name == 'controlled-sample':
                require(text.count('starts=1') == 3, 'Controlled static reset absent')
            pid = re.search(r'RuneCLR prototype \| \.NET 12\.0\.0 \| process (\d+)', text)
            require(pid and int(pid.group(1)) == row['processId'], 'Sample PID/runtime not bound')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--candidate-commit', default=BASELINE)
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    require(not args.output.exists(), 'New audit output required')
    result = load(evidence / 'results.json')
    request = load(evidence / 'request.json')
    provenance = load(evidence / 'runtime-provenance.json')
    require(request.get('candidateCommit', BASELINE) == result.get('candidateCommit', BASELINE) ==
            provenance['binding']['actualSourceCommit'] == args.candidate_commit, 'Expected exact source candidate')
    require(result['passed'] and result['configuration'] == 'Release' and not result['methodEntryProof'], 'Incorrect result scope')
    require(provenance['passed'] and provenance['configuration'] == 'Release', 'Release provenance absent')
    check_hashes(provenance['frozenInputHashes'])
    check_hashes({str(evidence / p): h for p, h in provenance['binding']['metadataHashes'].items()})
    root = Path(__file__).resolve().parents[1]
    candidate_check = subprocess.run(['py', '-3', '-B', str(root / 'eng/windows-runtime-validation.py'), 'check',
                                      '--output', str(evidence), '--candidate-commit', args.candidate_commit], capture_output=True)
    require(candidate_check.returncode == 0, 'Exact candidate source/build/layout check failed: ' + candidate_check.stderr.decode('utf-8', errors='replace'))
    source_hashes = load(evidence / 'source-hashes.json')
    require(source_hashes == request['sourceHashes'], 'Source request differs')
    check_hashes(source_hashes)
    for path, expected in source_hashes.items():
        require(sha(evidence / 'source' / Path(path).relative_to(root)) == expected, 'Frozen RuneCLR source mismatch')
    check_hashes(load(evidence / 'managed-input-hashes.json'))
    check_hashes(load(evidence / 'official-input-hashes.json'))
    original = load(evidence / 'upstream-request.json')
    upstream = Path(request['upstream'])
    official_sources = original['sourceHashes']
    for relative, expected in official_sources.items():
        for path in (Path(provenance['runtime']) / relative,
                     Path(original['baselineRuntimeRepo']) / relative, upstream / 'source' / relative):
            require(sha(path).lower() == expected.lower(), 'Official source/assertions differ: ' + relative)
    rows = result['runs']
    expected_names = {'lifecycle', 'sample', 'late-sample', 'controlled-sample', 'package-execution',
                      'official-GenericVirtualMethod', 'official-CollectibleStatics',
                      'official-ResolvedFromDifferentContext', 'official-ByRefLocals'}
    require(len(rows) == 9 and {r['name'] for r in rows} == expected_names, 'Functional row inventory incorrect')
    texts = {}
    dotnet = str(Path(provenance['binding']['buildEvidencePath']) / 'layout/dotnet.exe')
    for row in rows:
        name = row['name']
        receipt = load(evidence / (name + '.process.json'))
        for key, value in receipt.items():
            require(row[key] == value, 'Process receipt differs: ' + name + ' ' + key)
        require(Path(row['command'][0]).resolve() == Path(dotnet).resolve(), 'Another dotnet host used')
        require(row['settings']['DOTNET_InterpMode'] == '0' and row['settings']['DOTNET_GCStress'] == '0', 'Functional settings changed')
        require(row['settings']['DOTNET_RuneCLRInterpretCollectible'] == ('1' if name.startswith('official-') else '0'), 'Collectible policy differs')
        for suffix in ('stdout', 'stderr'):
            require(sha(evidence / (name + '.' + suffix)) == row[suffix + 'Sha256'], 'Raw receipt hash changed')
        text = (evidence / (name + '.stdout')).read_text() + (evidence / (name + '.stderr')).read_text()
        texts[name] = text
        assess(row, text)
        if name.startswith('official-'):
            generated = evidence / 'generated' / (name.removeprefix('official-') + '.cs')
            guard = load(evidence / 'upstream-generated-guards.json')[name.removeprefix('official-')]
            require(sha(generated) == row['generatedGuardSha256'] == guard['sha256'].lower(), 'Generated Main binding changed')
            require(guard['hostMethod'].split(':')[-1] in generated.read_text(), 'Generated body call missing')
            require(not Path(row['settings']['__TestOutOfProcessStatusFile']).exists(), 'Official test skipped')
    controls = []
    cases = [('exit', 'lifecycle'), ('timeout', 'sample'), ('trace-claim', 'sample'),
             ('skip', 'official-GenericVirtualMethod'), ('drop-test-row', 'lifecycle'),
             ('drop-late-marker', 'late-sample'), ('drop-byref-output', 'official-ByRefLocals'),
             ('drop-resolved-body', 'official-ResolvedFromDifferentContext')]
    for mutation, name in cases:
        row = copy.deepcopy(next(r for r in rows if r['name'] == name))
        text = texts[name]
        if mutation == 'exit': row['exitCode'] = 100
        elif mutation == 'timeout': row['timedOut'] = True
        elif mutation == 'trace-claim': row['methodEntryProof'] = True
        elif mutation == 'skip': row['skipped'] = True
        elif mutation == 'drop-test-row': text = text.replace('PASS ', 'DROPPED ', 1)
        elif mutation == 'drop-late-marker': text = text.replace('late-map=42', '')
        elif mutation == 'drop-byref-output': text = text.replace('1\n', '', 1)
        elif mutation == 'drop-resolved-body': text = text.replace('TestInterface.Class.Test', '', 1)
        rejected = False
        try: assess(row, text)
        except RuntimeError: rejected = True
        require(rejected, 'Corruption accepted: ' + mutation)
        controls.append({'mutation': mutation, 'rejected': rejected})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'passed': True, 'evidence': str(evidence),
         'candidateCommit': args.candidate_commit,
         'resultsSha256': sha(evidence / 'results.json'), 'runtimeProvenanceSha256': sha(evidence / 'runtime-provenance.json'),
         'driverSha256': sha(evidence / 'driver.py'), 'reviewerSha256': sha(__file__),
         'functionalRows': len(rows), 'originalOfficialSourceFiles': len(official_sources),
         'negativeControls': controls, 'methodEntryProof': False}, indent=2) + '\n')
    print('PASS independent Release production audit: 9 raw functional rows, original assertions/sources, 8 corruption controls')


if __name__ == '__main__':
    main()
