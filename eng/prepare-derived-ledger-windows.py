#!/usr/bin/env python3
"""Prepare exact derived-ledger acceptance snapshots without runtime execution."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '29ff781e157be82ba5a398a60bb05291e4a865af'
SWITCH = 'DOTNET_RuneCLRDerivedLedger'
PHASE_SWITCH = 'DOTNET_RuneCLRPhaseAcquireLoad'
CHECKER = ROOT / 'eng/derived-ledger-runtime-candidate.py'
ADAPTER = ROOT / 'eng/prepare-phase-load-windows.py'
ADAPTER_SHA = '79acb2a27e2d5ba01c8cade7eb59f6bb360ea1e9251e5f473112e548eb245bfb'
PHASE_PREPARATION = ROOT / 'artifacts/phase-load/windows-acceptance-preparation-20261014-attempt2'
TEMPLATE_HASHES = {
    'windows-runtime-validation.py': 'b5cf3075410bf220fb79eaa4e8031286bf082aa67a19976087e6d03550ff6bee',
    'benchmark-budget-overhead.py': 'a4613a272323c013ed148008007e815049a7f72664d130db5f1638dcb765c30f',
    'verify-session-terminal.ps1': '52eb5231a68f02a3aa1225e0b30cab319f9f95ae0bf6f3faede203072d8d6224',
    'verify-session-finalizer.ps1': 'dcd5843422c71b788c3ee40761752ab460cebac39af3ac8e156a761b2a093ec3',
    'verify-host-budget.ps1': '7f22db7303cb12af85fd64ef8acf82289e52adc7f216f897b1c61156fdeeabe2',
    'audit-release-budget.py': '5ad5301f58bf53d43db7b0735e601466979fa7af03e584aad074ab9d1b4b2531',
    'run-terminal-concurrency.py': '212a124ac2e0a9a6dd35eeece71b64e73769d4756f5f9c25f5cfe3df75df7c88',
    'audit-terminal-concurrency.py': '125d37a41e7ccbb9b0fa9503cb8dc74b2233ef7852cbf345c4e742608d735341',
    'verify-release-production.py': '050c08bcbdf74aef15a311e307261949e66e8c8935fd561a2f9dbfaea992bae4',
    'audit-release-production.py': '95ea6bde35445df1a6a8024dcf641f000f87f2bfe004fec80e6d3e6d86ed59fc',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replace_exact(text, old, new, count=1):
    if text.count(old) != count:
        raise RuntimeError('Exact derived snapshot anchor count differs: ' + repr(old))
    return text.replace(old, new)


def binding_helper(value):
    text = '''#!/usr/bin/env python3
"""Validate exact prepared derived-ledger identities before child launch."""
import hashlib
import json
from pathlib import Path

def validate(directory=None):
    root = Path(directory or Path(__file__).parent).resolve()
    value = json.loads((root / 'profile.json').read_text())
    if value['candidateCommit'] != COMMIT or value['derivedLedgerValue'] != VALUE or value['phaseAcquireValue'] != '1':
        raise RuntimeError('Exact derived-ledger preparation profile differs.')
    if value['derivedLedgerSwitch'] != 'DOTNET_RuneCLRDerivedLedger' or value['phaseAcquireSwitch'] != 'DOTNET_RuneCLRPhaseAcquireLoad':
        raise RuntimeError('Exact derived-ledger preparation switch identity differs.')
    for relative, expected in value['snapshotHashes'].items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Prepared snapshot changed: ' + relative)
    for path, expected in value['originalInputHashes'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Original preparation input changed: ' + path)
    return value

if __name__ == '__main__':
    validate()
    print('PASS exact prepared derived-ledger profile; no runtime executed')
'''
    return replace_exact(replace_exact(text, 'COMMIT', repr(COMMIT)), 'VALUE', repr(value))


def transform(module, name, text, value):
    if name.endswith('.ps1'):
        generated = module.powershell_snapshot(text, value)
        generated = replace_exact(generated, 'phase-profile-binding.py', 'derived-profile-binding.py', 2)
        return replace_exact(generated, "    $Settings['" + SWITCH + "'] = '" + value + "'\n",
                             "    $Settings['" + SWITCH + "'] = '" + value + "'\n    $Settings['" + PHASE_SWITCH + "'] = '1'\n")
    generated = module.python_snapshot(name, text, value)
    checker_counts = {'windows-runtime-validation.py': 1, 'benchmark-budget-overhead.py': 1, 'audit-release-budget.py': 3}
    if name in checker_counts:
        generated = replace_exact(generated, 'phase-load-runtime-candidate.py', 'derived-ledger-runtime-candidate.py', checker_counts[name])
    if name != 'benchmark-budget-overhead.py':
        generated = replace_exact(generated, 'phase-profile-binding.py', 'derived-profile-binding.py')
    if name in ('run-terminal-concurrency.py', 'verify-release-production.py'):
        generated = replace_exact(generated,
            '    settings = dict(settings or {}, ' + SWITCH + '=' + repr(value) + ')\n',
            '    settings = dict(settings or {}, ' + SWITCH + '=' + repr(value) + ', ' + PHASE_SWITCH + "='1')\n")
    if name == 'audit-release-budget.py':
        generated = replace_exact(generated,
            "    require(settings.get(" + repr(SWITCH) + ') == ' + repr(value) + ", 'Explicit phase-acquire profile differs')\n",
            "    require(settings.get(" + repr(SWITCH) + ') == ' + repr(value) + " and settings.get(" + repr(PHASE_SWITCH) + ") == '1', 'Explicit derived-ledger and fixed phase-acquire profiles differ')\n")
        generated = replace_exact(generated, 'launcher-phase-acquire-switch-substitution', 'launcher-derived-ledger-switch-substitution')
        anchor = "    negative('owned-raw-marker-substitution', fr_raw, lambda v: None,"
        generated = replace_exact(generated, anchor,
            "    negative('launcher-fixed-phase-acquire-switch-substitution', process, lambda v: v['settings'].__setitem__(" + repr(PHASE_SWITCH) + ", '0'),\n" +
            "             lambda v: process_binding(v, name, dict(lane, settings=v['settings']), request))\n" + anchor)
        generated = replace_exact(generated, "require(len(negatives) == 22, 'Exactly twenty-two phase-profile budget negatives required')",
                                  "require(len(negatives) == 23, 'Exactly twenty-three derived-profile budget negatives required')")
    if name == 'audit-release-production.py':
        generated = replace_exact(generated,
            "    require(row['settings'].get(" + repr(SWITCH) + ') == ' + repr(value) + ", 'Explicit phase-acquire profile differs')\n",
            "    require(row['settings'].get(" + repr(SWITCH) + ') == ' + repr(value) + " and row['settings'].get(" + repr(PHASE_SWITCH) + ") == '1', 'Explicit derived-ledger and fixed phase-acquire profiles differ')\n")
        generated = replace_exact(generated, "cases = [('phase-switch', 'sample'),", "cases = [('fixed-phase-switch', 'sample'), ('derived-switch', 'sample'),")
        generated = replace_exact(generated, "if mutation == 'phase-switch':", "if mutation == 'fixed-phase-switch': row['settings'][" + repr(PHASE_SWITCH) + "] = '0'\n        elif mutation == 'derived-switch':")
        generated = replace_exact(generated, '9 corruption controls', '10 corruption controls')
        generated = replace_exact(generated, "require(len(controls) == 9, 'Exactly nine phase-profile production negatives required')",
                                  "require(len(controls) == 10, 'Exactly ten derived-profile production negatives required')")
    if name == 'audit-terminal-concurrency.py':
        settings = ('{"DOTNET_InterpMode": "0", "DOTNET_RuneCLRInterpretCollectible": "0",\n'
                    '                "DOTNET_ReadyToRun": "1", "DOTNET_TieredCompilation": "0", "DOTNET_MULTILEVEL_LOOKUP": "0",\n'
                    '                "RUNECLR_POST_EXECUTION_PRECODE": "1", ' + repr(SWITCH) + ': ' + repr(value) + '}')
        generated = replace_exact(generated, '        require(receipt["settings"] == ' + settings + ', "Frozen selection/observation settings")',
                                  '        validate_settings(receipt["settings"])')
        expected_settings = settings[:-1] + ', ' + repr(PHASE_SWITCH) + ": '1'}"
        generated = replace_exact(generated, 'def main():\n', 'def validate_settings(settings):\n    require(settings == ' + expected_settings + ', "Frozen selection/observation/derived/fixed-phase settings")\n\ndef main():\n')
        anchor = '    audit = {"passed": True,'
        extra = ("    for name, key, wrong in [('derived-switch', " + repr(SWITCH) + ', ' + repr('1' if value == '0' else '0') + "), ('fixed-phase-switch', " + repr(PHASE_SWITCH) + ", '0')]:\n"
                 "        settings = copy.deepcopy(result['lanes'][0]['receipt']['settings'])\n"
                 "        settings[key] = wrong\n"
                 "        try: validate_settings(settings)\n"
                 "        except RuntimeError: controls.append(name)\n"
                 "        else: raise RuntimeError('Switch corruption accepted: ' + name)\n"
                 "    require(len(controls) == 6, 'Exactly six concurrent ledger/profile negatives required')\n")
        generated = replace_exact(generated, anchor, extra + anchor)
        generated = replace_exact(generated, '4 rejected ledger controls', '6 rejected ledger/profile controls')
    ast.parse(generated, filename=name)
    return generated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, default=Path('E:/runtime-derived-ledger-20261014'))
    parser.add_argument('--build-evidence', type=Path, default=ROOT / 'artifacts/derived-ledger/windows-release-build-20261014-attempt1')
    args = parser.parse_args()
    args.output = args.output.resolve(); args.runtime = args.runtime.resolve(); args.build_evidence = args.build_evidence.resolve()
    if args.output.exists() or not args.output.is_relative_to(ROOT / 'artifacts'):
        raise RuntimeError('Fresh output beneath this repository artifacts directory required.')
    if sha(ADAPTER) != ADAPTER_SHA:
        raise RuntimeError('Exact previously accepted phase generator changed.')
    for name, expected in TEMPLATE_HASHES.items():
        if sha(ROOT / 'eng' / name) != expected:
            raise RuntimeError('Exact frozen original acceptance template changed: ' + name)
    module = load_module(ADAPTER, 'derived_acceptance_template')
    module.COMMIT = COMMIT; module.SWITCH = SWITCH
    checker = load_module(CHECKER, 'derived_acceptance_candidate')
    validation = checker.validate(args.runtime, COMMIT)
    previous_path = PHASE_PREPARATION / 'preparation.json'
    previous = json.loads(previous_path.read_text())
    upstreams = []
    previous_profiles = []
    for label in ('off', 'on'):
        profile_path = PHASE_PREPARATION / label / 'eng/profile.json'
        if sha(profile_path) != previous['profiles'][label]['profileSha256']:
            raise RuntimeError('Previously accepted phase production profile changed.')
        previous_profiles.append(profile_path)
        command = previous['profiles'][label]['commands']['production']
        upstreams.append(Path(command[command.index('--upstream') + 1]).resolve())
    if upstreams[0] != upstreams[1]:
        raise RuntimeError('Previously accepted ON/OFF official controls differ.')
    args.upstream = upstreams[0]
    originals = {str(ROOT / 'eng' / name): expected for name, expected in TEMPLATE_HASHES.items()}
    for path in [ADAPTER, CHECKER, Path(__file__).resolve(), ROOT / 'eng/run-derived-ledger-windows.py',
                 previous_path, *previous_profiles]:
        originals[str(path)] = sha(path)
    args.output.mkdir(parents=True)
    inputs = args.output / 'inputs'; inputs.mkdir()
    for index, path in enumerate(originals):
        folder = inputs / str(index); folder.mkdir()
        shutil.copyfile(path, folder / Path(path).name)
    profiles = {}
    for label, value in [('off', '0'), ('on', '1')]:
        directory = args.output / label / 'eng'; directory.mkdir(parents=True)
        for name in TEMPLATE_HASHES:
            generated = transform(module, name, (ROOT / 'eng' / name).read_text(), value)
            (directory / name).write_text(generated, encoding='utf-8', newline='\n')
        shutil.copyfile(CHECKER, directory / CHECKER.name)
        helper = binding_helper(value); ast.parse(helper)
        (directory / 'derived-profile-binding.py').write_text(helper, encoding='ascii', newline='\n')
        command_record = module.commands(directory, args.output / label / 'evidence', args)
        if len(command_record) != 8:
            raise RuntimeError('All eight exact derived-ledger functional/audit commands required.')
        (directory / 'commands.json').write_text(json.dumps(command_record, indent=2) + '\n', encoding='ascii')
        profile = {'version': 1, 'preparedOnly': True, 'executionVerified': False, 'candidateCommit': COMMIT,
                   'candidateValidation': validation, 'derivedLedgerSwitch': SWITCH, 'derivedLedgerValue': value,
                   'phaseAcquireSwitch': PHASE_SWITCH, 'phaseAcquireValue': '1',
                   'originalInputHashes': originals, 'snapshotHashes': {p.name: sha(p) for p in directory.iterdir() if p.is_file()},
                   'expectedAuditControls': {'budget': 23, 'production': 10, 'concurrency': 6},
                   'expectedSuites': {'terminal': '44 lanes/84 rows', 'finalizer': '9 recovery + 6 original fatal controls',
                                      'host': '15 cases/73 contexts', 'concurrency': '36 processes/72 contexts', 'production': '9 functional controls'},
                   'sourceAuditScope': 'Exact committed derived-ledger source/checker/build binding. Native meter size64 is separately proven by actual header fixture; older size48 baseline provenance establishes no candidate ABI. Managed scalar getter interface unchanged.',
                   'scope': 'Prepared only; original strict functional, source, raw, managed, PE and build guards preserved. No runtime/build/benchmark/device execution.'}
        (directory / 'profile.json').write_text(json.dumps(profile, indent=2) + '\n', encoding='ascii')
        profiles[label] = {'profile': str(directory / 'profile.json'), 'profileSha256': sha(directory / 'profile.json'), 'commands': command_record}
    for path, expected in originals.items():
        if sha(path) != expected:
            raise RuntimeError('Preparation input changed while generating snapshots: ' + path)
    summary = {'passed': True, 'preparedOnly': True, 'executionVerified': False, 'candidateCommit': COMMIT,
               'profiles': profiles, 'productionCommandsPrepared': True, 'upstreamControls': str(args.upstream),
               'templateAdapterSha256': ADAPTER_SHA, 'frozenTemplateHashes': TEMPLATE_HASHES,
               'scope': 'Snapshot/hash/Python syntax preparation only. No build, suite, benchmark, or device run started.'}
    (args.output / 'preparation.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='ascii')
    print('PASS prepared exact derived-ledger ON/OFF acceptance snapshots with fixed phase=1; runtime execution unperformed')


if __name__ == '__main__':
    main()
