#!/usr/bin/env python3
"""Small stdlib-only tests for the TrustedGame build driver's runner records."""

import argparse
import ast
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / 'eng/verify-trusted-game-builds.py'


def load_verify():
    spec = importlib.util.spec_from_file_location('trusted_game_verify', VERIFY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(output, name):
    values = json.loads((output / 'commands.json').read_text(encoding='utf-8'))
    matches = [item for item in values if item.get('name') == name]
    assert len(matches) == 1, (name, matches)
    return matches[0]


def check_ast_import_links():
    ast.parse(VERIFY.read_text(encoding='utf-8'))
    ast.parse(Path(__file__).read_text(encoding='utf-8'))
    module = load_verify()
    assert callable(module.Runner)
    assert module.resolve_tool(sys.executable).is_file()
    parser = module.build_parser()
    base = ['--sdk', 'dotnet', '--runtime', 'runtime', '--output', 'output']
    assert parser.parse_args(base).signed_ab is False
    assert parser.parse_args(base + ['--signed-ab']).signed_ab is True
    default_files = {path.relative_to(ROOT).as_posix() for path in module.collect_source_files()}
    signed_files = {path.relative_to(ROOT).as_posix() for path in module.collect_source_files(True)}
    assert 'samples/TrustedGame.UpdateV2/TrustedGame.UpdateV2.csproj' not in default_files
    assert 'samples/TrustedGame.Publisher/TrustedGame.Publisher.csproj' not in default_files
    assert 'samples/TrustedGame.UpdateV2/TrustedGame.UpdateV2.csproj' in signed_files
    assert 'samples/TrustedGame.Publisher/TrustedGame.Publisher.csproj' in signed_files
    check_signed_facts_offline(module)
    files = {path.relative_to(ROOT).as_posix(): path for path in module.collect_source_files()}
    assert 'src/RuneCLR.TrustedUpdate/TrustedModuleSession.cs' in files
    assert 'src/RuneCLR.TrustedUpdate/RuneCLR.TrustedUpdate.csproj' in files
    assert 'Directory.Build.props' in files
    assert 'eng/trusted-game.ps1' in files
    assert 'docs/trusted-game-builds.md' in files
    assert not any('/obj/' in name or '/bin/' in name for name in files)
    docs = ROOT / 'docs/trusted-game-builds.md'
    text = docs.read_text(encoding='utf-8')
    for target in re.findall(r'\]\(([^)]+)\)', text):
        if target.startswith(('http://', 'https://', '#')):
            continue
        path = target.split('#', 1)[0]
        assert (docs.parent / path).resolve().exists(), target


def check_signed_facts_offline(module):
    happy_stage = (
        'SIGNED-FACTS mode=stage stage=OK stageDetail= expectedScoreMultiplier=1 '
        'candidateVerification=None candidatePlan=None candidateActivation=None '
        'recoveryVerification=None recoveryPlan=None recoveryActivation=None '
        'persistence=None persistenceDetail= activated=True source=Candidate '
        'version=game-rules-a activatorCalls=1\n'
        'TRUSTED-GAME normal results=1,3,6 score=6 ticks=3 multiplier=1\n'
        'TRUSTED-GAME negative failure=CallbackFailed next=Closed score=0\n'
        'TRUSTED-GAME OK\n'
    )
    module.parse_signed_facts(happy_stage, 'stage', 1, 'game-rules-a', 'Candidate')
    module.check_signed_gameplay(happy_stage, 1)
    happy_recover = (
        'SIGNED-FACTS mode=recover stage=NA stageDetail= expectedScoreMultiplier=2 '
        'candidateVerification=None candidatePlan=None candidateActivation=None '
        'recoveryVerification=None recoveryPlan=None recoveryActivation=None '
        'persistence=None persistenceDetail= activated=True source=LastKnownGood '
        'version=game-rules-b activatorCalls=1\n'
        'TRUSTED-GAME normal results=2,6,12 score=12 ticks=3 multiplier=2\n'
        'TRUSTED-GAME negative failure=CallbackFailed next=Closed score=0\n'
        'TRUSTED-GAME OK\n'
    )
    module.parse_signed_facts(happy_recover, 'recover', 2, 'game-rules-b', 'LastKnownGood')
    module.check_signed_gameplay(happy_recover, 2)

    fake_mixed = (
        'SIGNED-FACTS mode=stage stage=VerificationFailed stageDetail= '
        'expectedScoreMultiplier=1 candidateVerification=None candidatePlan=None '
        'candidateActivation=None recoveryVerification=None recoveryPlan=None '
        'recoveryActivation=None persistence=None persistenceDetail= activated=True '
        'source=LastKnownGood version=wrong-version activatorCalls=1\n'
        'TRUSTED-GAME normal results=1,3,6 score=6 ticks=3 multiplier=1\n'
        'TRUSTED-GAME negative failure=CallbackFailed next=Closed score=0\n'
        'TRUSTED-GAME OK\n'
    )
    cases = (
        ('wrong-source', happy_stage.replace('source=Candidate', 'source=LastKnownGood'),
         'stage', 1, 'game-rules-a', 'Candidate'),
        ('wrong-version', happy_stage.replace('version=game-rules-a', 'version=wrong-version'),
         'stage', 1, 'game-rules-a', 'Candidate'),
        ('wrong-stage', happy_stage.replace('stage=OK', 'stage=VerificationFailed'),
         'stage', 1, 'game-rules-a', 'Candidate'),
        ('candidate-activation-failed',
         happy_stage.replace('candidateActivation=None', 'candidateActivation=ActivationFailed'),
         'stage', 1, 'game-rules-a', 'Candidate'),
        ('recovery-activation-failed',
         happy_stage.replace('recoveryActivation=None', 'recoveryActivation=ActivationFailed'),
         'stage', 1, 'game-rules-a', 'Candidate'),
        ('missing-candidate-plan',
         happy_stage.replace(' candidatePlan=None', ''),
         'stage', 1, 'game-rules-a', 'Candidate'),
        ('nonempty-stage-detail',
         happy_stage.replace('stageDetail=', 'stageDetail=bad'),
         'stage', 1, 'game-rules-a', 'Candidate'),
        ('nonempty-persistence-detail',
         happy_stage.replace('persistenceDetail=', 'persistenceDetail=bad'),
         'stage', 1, 'game-rules-a', 'Candidate'),
        ('fake-mixed-row', fake_mixed, 'stage', 1, 'game-rules-a', 'Candidate'),
        ('duplicate-key',
         happy_stage.replace('activated=True', 'activated=True activated=True', 1),
         'stage', 1, 'game-rules-a', 'Candidate'),
    )
    for name, text, mode, multiplier, version, source in cases:
        try:
            module.parse_signed_facts(text, mode, multiplier, version, source)
        except RuntimeError:
            continue
        raise AssertionError('offline signed-facts negative accepted: ' + name)
    try:
        module.parse_signed_facts(happy_stage + happy_stage, 'stage', 1,
                                  'game-rules-a', 'Candidate')
    except RuntimeError:
        pass
    else:
        raise AssertionError('duplicate SIGNED-FACTS row accepted')


def check_success(module, root):
    runner = module.Runner(root)
    process = runner.run('success', [
        sys.executable, '-B', '-c',
        'import sys; print("SUCCESS-OUT"); print("SUCCESS-ERR", file=sys.stderr)',
    ])
    item = record(root, 'success')
    assert process.returncode == 0
    assert b'SUCCESS-OUT' in process.stdout
    assert 'SUCCESS-ERR' in runner.text(process)
    assert item['exitCode'] == 0 and item['endedStatus'] == 'exited'
    assert item['startStatus'] == 'started' and item['pid'] > 0
    assert item['cwd'] == str(module.ROOT)
    assert item['command'] == [
        sys.executable, '-B', '-c',
        'import sys; print("SUCCESS-OUT"); print("SUCCESS-ERR", file=sys.stderr)',
    ]
    assert item['settings'] == {}
    assert b'SUCCESS-OUT' in Path(item['stdout']).read_bytes()
    assert b'SUCCESS-ERR' in Path(item['stderr']).read_bytes()


def check_nonzero_false(module, root):
    runner = module.Runner(root)
    process = runner.run('nonzero-false', [
        sys.executable, '-B', '-c',
        'import sys; print("BAD-OUT"); print("BAD-ERR", file=sys.stderr); sys.exit(7)',
    ], check=False)
    item = record(root, 'nonzero-false')
    assert process.returncode == 7
    assert b'BAD-OUT' in process.stdout
    assert item['exitCode'] == 7 and item['endedStatus'] == 'exited'
    assert b'BAD-OUT' in Path(item['stdout']).read_bytes()
    assert b'BAD-ERR' in Path(item['stderr']).read_bytes()


def check_nonzero_true(module, root):
    runner = module.Runner(root)
    try:
        runner.run('nonzero-true', [
            sys.executable, '-B', '-c',
            'import sys; print("CHECKED-OUT"); print("CHECKED-ERR", file=sys.stderr); sys.exit(9)',
        ], check=True)
    except RuntimeError as error:
        assert 'exit=9' in str(error)
    else:
        raise AssertionError('check=True did not raise')
    item = record(root, 'nonzero-true')
    assert item['exitCode'] == 9 and item['endedStatus'] == 'exited'
    assert b'CHECKED-OUT' in Path(item['stdout']).read_bytes()
    assert b'CHECKED-ERR' in Path(item['stderr']).read_bytes()


def check_missing(module, root):
    runner = module.Runner(root)
    missing = root / 'does-not-exist.exe'
    try:
        runner.run('missing', [str(missing)])
    except RuntimeError as error:
        assert 'Command failed to start' in str(error)
    else:
        raise AssertionError('missing executable did not raise')
    item = record(root, 'missing')
    assert item['startStatus'] == 'os-error' and item['endedStatus'] == 'os-error'
    assert item['failureType'] == 'FileNotFoundError'
    assert item['command'] == [str(missing)]
    assert item['cwd'] == str(module.ROOT)
    assert 'exitCode' not in item
    assert Path(item['stdout']).read_bytes() == b''
    assert Path(item['stderr']).read_bytes() == b''


def check_timeout(module, root):
    runner = module.Runner(root)
    child = (
        'import sys, time; '
        'print("TIMEOUT-OUT", flush=True); '
        'print("TIMEOUT-ERR", file=sys.stderr, flush=True); '
        'time.sleep(5)'
    )
    try:
        runner.run('timeout', [sys.executable, '-B', '-c', child], timeout=0.6)
    except RuntimeError as error:
        assert 'Command timed out' in str(error)
    else:
        raise AssertionError('timeout did not raise')
    item = record(root, 'timeout')
    assert item['startStatus'] == 'started' and item['endedStatus'] == 'timeout'
    assert item['timedOut'] is True and item['timeoutSeconds'] == 0.6
    assert 'exitCode' not in item
    assert b'TIMEOUT-OUT' in Path(item['stdout']).read_bytes()
    assert b'TIMEOUT-ERR' in Path(item['stderr']).read_bytes()


def make_output(arguments):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        help='new output directory; default is a fresh portable tempfile.mkdtemp root')
    args = parser.parse_args(arguments)
    if args.output is not None:
        output = args.output.expanduser().resolve()
        if output.exists():
            parser.error('--output must not already exist: ' + str(output))
        output.mkdir(parents=True, exist_ok=False)
    else:
        output = Path(tempfile.mkdtemp(prefix='trusted-game-runner-'))
    print('RUNNER_OUTPUT ' + str(output), flush=True)
    return output


def main(arguments=None):
    output = make_output(sys.argv[1:] if arguments is None else arguments)
    module = load_verify()
    checks = [
        ('ast-import-links', lambda root: check_ast_import_links()),
        ('success', lambda root: check_success(module, root)),
        ('nonzero-false', lambda root: check_nonzero_false(module, root)),
        ('nonzero-true', lambda root: check_nonzero_true(module, root)),
        ('missing', lambda root: check_missing(module, root)),
        ('timeout', lambda root: check_timeout(module, root)),
    ]
    for name, fn in checks:
        target = output / name
        if target.exists():
            raise AssertionError('fresh output unexpectedly contains ' + str(target))
        target.mkdir(parents=True)
        fn(target)
        print('PASS ' + name)
    print('RUNNER_SELFTEST PASS ' + str(len(checks)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
