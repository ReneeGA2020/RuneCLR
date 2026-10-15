#!/usr/bin/env python3
"""Prepare isolated exact-candidate ON/OFF acceptance tools; never start a runtime."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / 'eng/phase-load-runtime-candidate.py'
COMMIT = 'a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186'
SWITCH = 'DOTNET_RuneCLRPhaseAcquireLoad'
TEMPLATES = (
    'windows-runtime-validation.py', 'benchmark-budget-overhead.py',
    'verify-session-terminal.ps1', 'verify-session-finalizer.ps1', 'verify-host-budget.ps1',
    'audit-release-budget.py', 'run-terminal-concurrency.py', 'audit-terminal-concurrency.py',
    'verify-release-production.py', 'audit-release-production.py',
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Template anchor must occur exactly once: ' + old)
    return text.replace(old, new, 1)


def binding_helper():
    return '''#!/usr/bin/env python3
"""Validate preparation identity before any generated driver's child starts."""
import hashlib
import json
from pathlib import Path

def validate(directory=None):
    root = Path(directory or Path(__file__).parent).resolve()
    value = json.loads((root / 'profile.json').read_text())
    if value['candidateCommit'] != COMMIT or value['phaseAcquireValue'] != VALUE:
        raise RuntimeError('Exact phase-load preparation profile differs.')
    for relative, expected in value['snapshotHashes'].items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Prepared snapshot changed: ' + relative)
    for path, expected in value['originalInputHashes'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Original preparation input changed: ' + path)
    return value

if __name__ == '__main__':
    validate()
    print('PASS exact prepared phase-load profile; no runtime executed')
'''


def python_snapshot(name, text, value):
    text = text.replace("ROOT = Path(__file__).resolve().parents[1]", 'ROOT = Path(' + repr(ROOT.as_posix()) + ')')
    text = text.replace("root = Path(__file__).resolve().parents[1]", 'root = Path(' + repr(ROOT.as_posix()) + ')')
    text = text.replace('099dacd07d8d890822f7422f895337733457ab3c', COMMIT)
    text = text.replace("'budget-runtime-candidate.py'", "'phase-load-runtime-candidate.py'")
    for old in ("ROOT / 'eng/windows-runtime-validation.py'", "root / 'eng/windows-runtime-validation.py'",
                'ROOT / "eng/windows-runtime-validation.py"'):
        text = text.replace(old, "Path(__file__).with_name('windows-runtime-validation.py')")
    text = text.replace('default=_candidate.BASELINE', 'default=_candidate.COMMIT')
    if name == 'benchmark-budget-overhead.py':
        # Retain only the full provenance helper, so this profile cannot run the old benchmark.
        text = text.split('\ndef command(', 1)[0]
        text = replace_once(text, "if candidate_commit!=COMMIT or 'candidateValidation' in request:", 'if True:')
    if name in ('run-terminal-concurrency.py', 'verify-release-production.py'):
        text = replace_once(text, '    env.update(settings or {})',
                            "    settings = dict(settings or {}, " + SWITCH + '=' + repr(value) + ')\n    env.update(settings)')
        text = replace_once(text, 'def execute(', 'def execute(')
        marker = '    env =' if name == 'run-terminal-concurrency.py' else '    nonce ='
        text = replace_once(text, marker, '    _phase_validate()\n' + marker)
    if name == 'audit-terminal-concurrency.py':
        text = replace_once(text, '"RUNECLR_POST_EXECUTION_PRECODE": "1"}, "Frozen selection/observation settings")',
                            '"RUNECLR_POST_EXECUTION_PRECODE": "1", ' + repr(SWITCH) + ': ' + repr(value) +
                            '}, "Frozen selection/observation settings")')
    if name == 'audit-release-production.py':
        text = replace_once(text, 'def assess(row, text):\n',
                            'def assess(row, text):\n    require(row[\'settings\'].get(' + repr(SWITCH) + ') == ' + repr(value) +
                            ', \'Explicit phase-acquire profile differs\')\n')
        text = replace_once(text, "cases = [('exit', 'lifecycle')", "cases = [('phase-switch', 'sample'), ('exit', 'lifecycle')")
        text = replace_once(text, "if mutation == 'exit':", "if mutation == 'phase-switch': row['settings'][" + repr(SWITCH) + "] = " + repr('0' if value == '1' else '1') + "\n        elif mutation == 'exit':")
        text = text.replace('8 corruption controls', '9 corruption controls')
        text = replace_once(text, '    args.output.parent.mkdir(parents=True, exist_ok=True)',
                            "    require(len(controls) == 9, 'Exactly nine phase-profile production negatives required')" + chr(10) +
                            '    args.output.parent.mkdir(parents=True, exist_ok=True)')
    if name == 'audit-release-budget.py':
        start = text.index('def candidate_change_binding(')
        end = text.index('\ndef audit_experiment(', start)
        text = text[:start] + '''def candidate_change_binding(runtime, candidate):
    import importlib.util
    path = Path(__file__).with_name('phase-load-runtime-candidate.py')
    spec = importlib.util.spec_from_file_location('phase_candidate', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.validate(runtime, candidate)

''' + text[end:]
        start = text.index("    if candidate != COMMIT or 'candidateValidation' in binding:")
        end = text.index("    require(build_result['exitCode']", start)
        text = text[:start] + '''    validation = candidate_change_binding(Path(p['runtime']), candidate)
    require(binding['candidateValidation'] == validation and p['candidateValidation'] == validation and
            p['candidateCommit'] == candidate, 'Exact phase-load source/checker binding differs')
    checker = Path(__file__).with_name('phase-load-runtime-candidate.py')
    match_hash(checker, binding['candidateCheckerSha256'])
    match_hash(directory / 'provenance/phase-load-runtime-candidate.py', binding['candidateCheckerSha256'])
    match_hash(directory / 'provenance/build-candidate-checker.py', binding['candidateCheckerSha256'])
    for item in (build_request, build_result, layout):
        require(item['candidateValidation'] == validation and item['candidateCheckerSha256'] == binding['candidateCheckerSha256'],
                'Build/source-checker candidate validation differs')
''' + text[end:]
        text = replace_once(text, "    settings = p['settings']\n", "    settings = p['settings']\n    require(settings.get(" + repr(SWITCH) + ') == ' + repr(value) + ", 'Explicit phase-acquire profile differs')\n")
        anchor = "    negative('owned-raw-marker-substitution', fr_raw, lambda v: None,"
        extra = "    negative('launcher-phase-acquire-switch-substitution', process, lambda v: v['settings'].__setitem__(" + repr(SWITCH) + ', ' + repr('0' if value == '1' else '1') + "),\n             lambda v: process_binding(v, name, dict(lane, settings=v['settings']), request))\n"
        text = replace_once(text, anchor, extra + anchor)
        anchor = "    result = {'passed': True, 'candidateCommit': args.candidate_commit, 'experimentPaths':"
        text = replace_once(text, anchor,
                            "    require(len(negatives) == 22, 'Exactly twenty-two phase-profile budget negatives required')" + chr(10) + anchor)
    if name != 'benchmark-budget-overhead.py':
        text = replace_once(text, 'def main():\n', 'def main():\n    _phase_validate()\n')
        text += '''
'''
        # Import by exact sibling path; filenames intentionally cannot shadow normal modules.
        insert = '''import importlib.util as _phase_import
_phase_spec = _phase_import.spec_from_file_location('phase_profile_binding', Path(__file__).with_name('phase-profile-binding.py'))
_phase_module = _phase_import.module_from_spec(_phase_spec); _phase_spec.loader.exec_module(_phase_module)
_phase_validate = _phase_module.validate

'''
        text = replace_once(text, 'from pathlib import Path\n', 'from pathlib import Path\n' + insert)
    ast.parse(text, filename=name)
    return text


def powershell_snapshot(text, value):
    text = re.sub(r'\$repo\s*=\s*Split-Path \$PSScriptRoot -Parent', "$repo = '" + ROOT.as_posix() + "'", text)
    text = re.sub(r"Join-Path \$PSScriptRoot '(session-terminal-probe|session-finalizer-probe|host-budget-probe|windows-entry-observation/WindowsEntryObservation.cs)'",
                  lambda m: "Join-Path $repo 'eng/" + m.group(1) + "'", text)
    text = text.replace("$RuntimeConfiguration = 'Checked'", "$RuntimeConfiguration = 'Release'")
    # In-place Settings mutation also updates the retained lane Settings reference.
    text, count = re.subn(r'(function Invoke-Child[^\n]+\{\n)',
        lambda m: m.group(1) + "    & py -3 -B (Join-Path $PSScriptRoot 'phase-profile-binding.py')\n    if ($LASTEXITCODE -ne 0) { throw 'Prepared phase profile changed.' }\n    $Settings['" + SWITCH + "'] = '" + value + "'\n", text)
    if count != 1:
        raise RuntimeError('Exactly one sanitizer/child launcher required.')
    marker = "$ErrorActionPreference"
    index = text.index(marker)
    text = text[:index] + "if ($RuntimeConfiguration -ne 'Release' -or $StockSmoke) { throw 'Exact private Release profile required.' }\n& py -3 -B (Join-Path $PSScriptRoot 'phase-profile-binding.py')\nif ($LASTEXITCODE -ne 0) { throw 'Prepared phase profile changed.' }\n" + text[index:]
    return text


def commands(directory, evidence, args):
    pwsh = shutil.which('pwsh') or 'pwsh'
    py = [sys.executable, '-B']
    common = ['-RuntimeRepo', str(args.runtime), '-RuntimeLayout', str(args.build_evidence / 'layout'),
              '-CandidateCommit', COMMIT, '-RuntimeConfiguration', 'Release', '-BuildEvidence', str(args.build_evidence)]
    result = {}
    for suite, driver in (('terminal', 'verify-session-terminal.ps1'), ('finalizer', 'verify-session-finalizer.ps1'), ('host', 'verify-host-budget.ps1')):
        result[suite] = [pwsh, '-NoProfile', '-File', str(directory / driver), *common, '-EvidenceDirectory', str(evidence / suite)]
    result['budget-audit'] = [*py, str(directory / 'audit-release-budget.py'), '--candidate-commit', COMMIT,
        '--terminal-evidence', str(evidence / 'terminal'), '--finalizer-evidence', str(evidence / 'finalizer'),
        '--host-evidence', str(evidence / 'host'), '--output', str(evidence / 'budget-audit')]
    result['concurrency'] = [*py, str(directory / 'run-terminal-concurrency.py'), '--candidate-commit', COMMIT,
        '--runtime', str(args.runtime), '--build-evidence', str(args.build_evidence), '--output', str(evidence / 'concurrency')]
    result['concurrency-audit'] = [*py, str(directory / 'audit-terminal-concurrency.py'), '--candidate-commit', COMMIT,
        '--evidence', str(evidence / 'concurrency'), '--output', str(evidence / 'concurrency-audit.json')]
    if args.upstream:
        result['production'] = [*py, str(directory / 'verify-release-production.py'), '--candidate-commit', COMMIT,
            '--runtime', str(args.runtime), '--layout', str(args.build_evidence / 'layout'), '--build-evidence', str(args.build_evidence),
            '--upstream', str(args.upstream), '--output', str(evidence / 'production')]
        result['production-audit'] = [*py, str(directory / 'audit-release-production.py'), '--candidate-commit', COMMIT,
            '--evidence', str(evidence / 'production'), '--output', str(evidence / 'production-audit.json')]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, default=Path('E:/runtime-phase-load-20261014'))
    parser.add_argument('--build-evidence', type=Path, default=ROOT / 'artifacts/phase-load/windows-release-build-20261014-attempt1')
    parser.add_argument('--upstream', type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve(); args.runtime = args.runtime.resolve(); args.build_evidence = args.build_evidence.resolve()
    if args.output.exists() or not args.output.is_relative_to(ROOT / 'artifacts'):
        raise RuntimeError('Fresh output beneath this repository artifacts directory required.')
    spec = importlib.util.spec_from_file_location('phase_candidate', CHECKER)
    checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
    validation = checker.validate(args.runtime, COMMIT)
    originals = {str(ROOT / 'eng' / name): sha(ROOT / 'eng' / name) for name in TEMPLATES}
    originals.update({str(CHECKER): sha(CHECKER), str(Path(__file__).resolve()): sha(__file__)})
    args.output.mkdir(parents=True)
    profiles = {}
    for label, value in (('off', '0'), ('on', '1')):
        directory = args.output / label / 'eng'; directory.mkdir(parents=True)
        for name in TEMPLATES:
            text = (ROOT / 'eng' / name).read_text()
            generated = powershell_snapshot(text, value) if name.endswith('.ps1') else python_snapshot(name, text, value)
            (directory / name).write_text(generated, encoding='utf-8', newline='\n')
        shutil.copyfile(CHECKER, directory / CHECKER.name)
        helper = binding_helper().replace('COMMIT', repr(COMMIT)).replace('VALUE', repr(value))
        ast.parse(helper)
        (directory / 'phase-profile-binding.py').write_text(helper, encoding='utf-8', newline='\n')
        commands_record = commands(directory, args.output / label / 'evidence', args)
        (directory / 'commands.json').write_text(json.dumps(commands_record, indent=2) + '\n')
        profile = {'version': 1, 'preparedOnly': True, 'executionVerified': False, 'candidateCommit': COMMIT,
                   'candidateValidation': validation, 'phaseAcquireSwitch': SWITCH, 'phaseAcquireValue': value,
                   'originalInputHashes': originals, 'snapshotHashes': {p.name: sha(p) for p in directory.iterdir() if p.is_file()},
                   'scope': 'Syntax/hash preparation only; no runtime/build/benchmark/device execution.',
                   'expectedAuditControls': {'budget': 22, 'production': 9, 'concurrency': 4},
                   'sourceAuditScope': 'Pinned exact direct-child tree and two changed blobs; complete patched build-source inventory; three precode source files separately. This does not prove the acquire branch ran.',
                   'expectedSuites': {'terminal': '44 lanes/84 rows', 'finalizer': '9 recovery + 6 original fatal controls',
                                      'host': '15 cases/73 contexts', 'concurrency': '36 processes/72 contexts', 'production': '9 functional controls'}}
        (directory / 'profile.json').write_text(json.dumps(profile, indent=2) + '\n')
        profiles[label] = {'profile': str(directory / 'profile.json'), 'profileSha256': sha(directory / 'profile.json'),
                           'commands': commands_record}
    for path, expected in originals.items():
        if sha(path) != expected:
            raise RuntimeError('Preparation input changed while generating snapshots: ' + path)
    summary = {'passed': True, 'preparedOnly': True, 'candidateCommit': COMMIT, 'profiles': profiles,
               'productionCommandsPrepared': bool(args.upstream), 'scope': 'No build, suite, benchmark, or device run started.'}
    (args.output / 'preparation.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('PASS prepared exact phase-load ON/OFF acceptance snapshots; runtime execution remains unperformed')


if __name__ == '__main__':
    main()
