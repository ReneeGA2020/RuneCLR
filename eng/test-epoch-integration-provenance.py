#!/usr/bin/env python3
"""Fixture regressions for eng/verify-epoch-integration.py.

Self-contained stdlib test: builds throwaway git/host/layout fixtures, imports the real
verifier module from --host-root and drives its real main() path with a fixture-only
subprocess.run stub for the harness child. Git, digest and input-pinning code all run for real.

This is the committed fixture set at eng/test-epoch-integration-provenance.py; the default
host root is Path(__file__).resolve().parents[1]. No native matrix is executed here.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_verifier(host_root):
    path = Path(host_root) / 'eng' / 'verify-epoch-integration.py'
    if not path.is_file():
        raise SystemExit('verifier not found: ' + str(path))
    spec = importlib.util.spec_from_file_location('epoch_verifier_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, digest(path)


NATIVE = {'coreclr.dll': b'coreclr-fixture', 'clrjit.dll': b'clrjit-fixture',
         'clrinterpreter.dll': b'interpreter-fixture', 'corerun.exe': b'corerun-fixture'}
DIRTY_FILE = 'src/RuneCLR.Runtime/Committed.cs'


class Fixture:
    def __init__(self, base, il_fallback=True, dirty=True):
        self.base = Path(base)
        self.il_fallback = il_fallback
        self.dirty = dirty
        self.host = self.base / 'host'
        self.runtime = self.base / 'runtime'
        self.layout = self.base / 'layout'
        self.build = self.runtime / 'artifacts/bin/coreclr/windows.x64.Release'
        self.manifest_path = self.base / 'source-manifest.json'
        self._build()

    def git(self, *args, check=True):
        return subprocess.run(['git', '-C', str(self.runtime), *args], capture_output=True, text=True, check=check)

    def _build(self):
        (self.host / 'eng').mkdir(parents=True)
        (self.host / 'RuneCLR.slnx').write_text('<Solution />' + chr(10), encoding='utf-8')
        (self.host / 'Directory.Build.props').write_text('<Project />' + chr(10), encoding='utf-8')
        harness_dir = self.host / 'tests/RuneCLR.EpochDeadline.Tests/bin/Release/net11.0'
        harness_dir.mkdir(parents=True)
        (harness_dir / 'RuneCLR.EpochDeadline.Tests.dll').write_bytes(b'harness-fixture')
        (self.host / 'src/RuneCLR.Runtime').mkdir(parents=True)
        (self.host / 'src/RuneCLR.Runtime/MapSession.cs').write_text('// fixture source' + chr(10), encoding='utf-8')
        (self.host / 'tests/RuneCLR.EpochDeadline.Tests/Program.cs').write_text('// fixture test' + chr(10), encoding='utf-8')

        self.build.mkdir(parents=True)
        for name, payload in NATIVE.items():
            (self.build / name).write_bytes(payload)
        corelib = b'corelib-fixture'
        if self.il_fallback:
            (self.build / 'IL').mkdir()
            (self.build / 'IL/System.Private.CoreLib.dll').write_bytes(corelib)
        else:
            (self.build / 'System.Private.CoreLib.dll').write_bytes(corelib)

        shared = self.layout / 'shared/Microsoft.NETCore.App/12.0.0'
        shared.mkdir(parents=True)
        for name, payload in NATIVE.items():
            (shared / name).write_bytes(payload)
        (shared / 'System.Private.CoreLib.dll').write_bytes(corelib)
        (self.layout / 'dotnet.exe').write_bytes(b'dotnet-fixture')

        self.runtime.mkdir(parents=True, exist_ok=True)
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'fixture')
        dirty = self.runtime / DIRTY_FILE
        dirty.parent.mkdir(parents=True)
        dirty.write_text('// baseline' + chr(10), encoding='utf-8')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'fixture baseline')
        if self.dirty:
            dirty.write_text('// dirty' + chr(10), encoding='utf-8')
        self.write_manifest()

    def head(self):
        return self.git('rev-parse', 'HEAD').stdout.strip()

    def manifest(self):
        files = {DIRTY_FILE: digest(self.runtime / DIRTY_FILE)} if self.dirty else {}
        return {'head': self.head(), 'dirty_files': files}

    def write_manifest(self, extra_space=False):
        text = json.dumps(self.manifest(), indent=2)
        if extra_space:
            text = text.replace('"', '" ', 1)
        self.manifest_path.write_text(text + chr(10), encoding='utf-8')

    def argv(self, output):
        return ['--host-root', str(self.host), '--layout', str(self.layout),
                '--runtime-root', str(self.runtime), '--source-manifest', str(self.manifest_path),
                '--output', str(output)]


def run_main(module, argv, on_harness=None, cwd=None):
    """Drive the real main() with a fixture-only child-process stub for the harness."""

    def stub(command, cwd=None, env=None, stdout=None, stderr=None, timeout=None, check=False):
        if on_harness is not None:
            on_harness()
        if stdout is not None:
            stdout.write(b'PASS fixture harness' + bytes([10]))
        return types.SimpleNamespace(returncode=0, stdout='', stderr='')

    # Give the verifier module its own subprocess shim so the git helpers in this file keep
    # using the real module (the verifier only uses run() for the harness child).
    real_subprocess = module.subprocess
    shim = types.SimpleNamespace(run=stub, check_output=real_subprocess.check_output,
                                 check_call=real_subprocess.check_call, PIPE=real_subprocess.PIPE,
                                 DEVNULL=real_subprocess.DEVNULL, STDOUT=real_subprocess.STDOUT,
                                 CalledProcessError=real_subprocess.CalledProcessError)

    previous_argv = sys.argv
    previous_cwd = Path.cwd()
    sys.argv = ['verify-epoch-integration.py'] + list(argv)
    module.subprocess = shim
    if cwd is not None:
        os.chdir(cwd)
    text = io.StringIO()
    try:
        with contextlib.redirect_stdout(text):
            module.main()
        return True, '', text.getvalue()
    except Exception as error:
        return False, str(error), text.getvalue()
    finally:
        module.subprocess = real_subprocess
        sys.argv = previous_argv
        if cwd is not None:
            os.chdir(previous_cwd)


def rejected(result, *keywords):
    ok, error, _ = result
    lowered = error.lower()
    return (not ok) and any(keyword.lower() in lowered for keyword in keywords)


def case_positive_dirty(fixture, module):
    output = fixture.base / 'out-positive'
    ok, error, text = run_main(module, fixture.argv(output))
    if not ok:
        return False, 'positive run rejected: ' + error
    pins = json.loads((output / 'pins-before.json').read_text(encoding='utf-8'))
    il = str(fixture.build / 'IL/System.Private.CoreLib.dll')
    if il not in pins:
        return False, 'accepted, but the produced IL CoreLib is not pinned (known gap)'
    return True, 'dirty declared source accepted and the IL produced file is pinned'


def case_il_produced_drift(fixture, module):
    output = fixture.base / 'out-il-drift'
    il = fixture.build / 'IL/System.Private.CoreLib.dll'

    def drift():
        il.write_bytes(il.read_bytes() + b'!')

    result = run_main(module, fixture.argv(output), on_harness=drift)
    if rejected(result, 'drift', 'changed during the run'):
        return True, 'IL produced file change rejected as drift'
    if result[0]:
        return False, 'IL produced file changed during the run but the run was accepted (known gap)'
    return False, 'rejected for an unexpected reason: ' + result[1]


def case_manifest_between_parse_and_pin(fixture, module):
    output = fixture.base / 'out-manifest-pin'
    real_digest = module.digest
    state = {'done': False}

    def wrapped(path):
        if not state['done'] and Path(path) == fixture.manifest_path:
            state['done'] = True
            fixture.write_manifest(extra_space=True)
        return real_digest(path)

    module.digest = wrapped
    try:
        result = run_main(module, fixture.argv(output))
    finally:
        module.digest = real_digest
    if not state['done']:
        return False, 'fixture did not reach the manifest pin'
    if result[0]:
        return False, 'manifest changed between parse and pin but the run was accepted (known gap)'
    return True, 'manifest parse/pin mismatch rejected'


def case_manifest_during_run(fixture, module):
    output = fixture.base / 'out-manifest-run'
    result = run_main(module, fixture.argv(output), on_harness=lambda: fixture.write_manifest(extra_space=True))
    if rejected(result, 'drift', 'changed during the run'):
        return True, 'manifest change during the run rejected as drift'
    return False, ('accepted despite a manifest change during the run' if result[0] else 'rejected for an unexpected reason: ' + result[1])


def case_consumed_copy(fixture, module):
    output = fixture.base / 'out-consumed'
    ok, error, _ = run_main(module, fixture.argv(output))
    if not ok:
        return False, 'positive run rejected: ' + error
    copies = [p for p in output.rglob('*') if p.is_file() and ('consumed' in p.name.lower() or 'copy' in p.name.lower())]
    if not copies:
        return None, 'verifier writes no consumed manifest copy, so copy drift cannot be exercised'
    source = digest(fixture.manifest_path)
    for copy in copies:
        if digest(copy) != source:
            return False, 'consumed copy does not match the manifest: ' + copy.name
    return True, 'consumed copy matches the manifest bytes'


def case_runtime_head_drift(fixture, module):
    output = fixture.base / 'out-head-drift'

    def drift():
        fixture.git('commit', '-q', '--allow-empty', '-m', 'fixture head drift')

    result = run_main(module, fixture.argv(output), on_harness=drift)
    if result[0]:
        return False, 'runtime HEAD changed during the run but the run was accepted (known gap)'
    return True, 'runtime HEAD change rejected: ' + result[1]


def case_stdout_append(fixture, module):
    output = fixture.base / 'out-stdout'
    ok, error, _ = run_main(module, fixture.argv(output))
    if not ok:
        return False, 'positive run rejected: ' + error
    pins = json.loads((output / 'pins-before.json').read_text(encoding='utf-8'))
    stdout_log = output / 'tests.stdout.log'
    if str(stdout_log) in pins:
        return False, 'the run stdout log is pinned as an input'
    summary = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
    if summary.get('drift'):
        return False, 'unexpected drift in a clean run: ' + repr(summary['drift'])
    with stdout_log.open('ab') as stream:
        stream.write(b'appended after the run' + bytes([10]))
    if digest(fixture.manifest_path) != pins.get(str(fixture.manifest_path), digest(fixture.manifest_path)):
        return False, 'manifest pin does not match the manifest'
    return True, 'stdout is not pinned and appending after the run is harmless'


def case_positive_clean(fixture, module):
    output = fixture.base / 'out-clean'
    ok, error, _ = run_main(module, fixture.argv(output))
    if not ok:
        return False, 'clean positive run rejected: ' + error
    pins = json.loads((output / 'pins-before.json').read_text(encoding='utf-8'))
    il = str(fixture.build / 'IL/System.Private.CoreLib.dll')
    if il not in pins:
        return False, 'accepted, but the produced IL CoreLib is not pinned'
    summary = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
    if summary.get('drift'):
        return False, 'unexpected drift in a clean run: ' + repr(summary['drift'])
    return True, 'clean committed worktree accepted and the IL produced file is pinned'


def case_consumed_copy_corrupt(fixture, module):
    output = fixture.base / 'out-consumed-corrupt'
    copy = output / 'source-manifest.copy.json'

    def corrupt():
        if copy.is_file():
            copy.write_bytes(copy.read_bytes() + b'!')

    result = run_main(module, fixture.argv(output), on_harness=corrupt)
    if rejected(result, 'consumed', 'copy drifted'):
        return True, 'consumed copy corrupted during the run was rejected'
    if result[0]:
        return False, 'consumed copy corrupted during the run but the run was accepted'
    return False, 'rejected for an unexpected reason: ' + result[1]


def case_runtime_status_drift(fixture, module):
    output = fixture.base / 'out-status-drift'

    def drift():
        (fixture.runtime / 'src/RuneCLR.Runtime/Untracked.cs').write_text('// untracked' + chr(10), encoding='utf-8')

    result = run_main(module, fixture.argv(output), on_harness=drift)
    if rejected(result, 'working tree drifted', 'status'):
        return True, 'untracked source status drift during the run was rejected'
    if result[0]:
        return False, 'untracked source appeared during the run but the run was accepted'
    return False, 'rejected for an unexpected reason: ' + result[1]


def case_relative_manifest(fixture, module):
    output = fixture.base / 'out-relative'
    argv = ['--host-root', str(fixture.host), '--layout', str(fixture.layout),
            '--runtime-root', str(fixture.runtime), '--source-manifest', fixture.manifest_path.name,
            '--output', str(output)]
    ok, error, _ = run_main(module, argv, cwd=fixture.base)
    if not ok:
        return False, 'relative --source-manifest run rejected: ' + error
    pins = json.loads((output / 'pins-before.json').read_text(encoding='utf-8'))
    resolved = str(fixture.manifest_path.resolve())
    if resolved not in pins:
        return False, 'the resolved manifest path is not pinned'
    if pins[resolved] != digest(fixture.manifest_path):
        return False, 'the pinned manifest hash differs from the manifest bytes'
    return True, 'relative --source-manifest resolved and pinned under a deliberate cwd'


CASES = [
    ('positive-dirty-il-fallback', case_positive_dirty, {}),
    ('positive-clean-commit', case_positive_clean, {'dirty': False}),
    ('il-produced-drift', case_il_produced_drift, {}),
    ('manifest-parse-pin-change', case_manifest_between_parse_and_pin, {}),
    ('manifest-during-run', case_manifest_during_run, {}),
    ('consumed-copy', case_consumed_copy, {}),
    ('consumed-copy-corrupt', case_consumed_copy_corrupt, {}),
    ('runtime-head-drift', case_runtime_head_drift, {}),
    ('runtime-status-drift', case_runtime_status_drift, {}),
    ('relative-source-manifest', case_relative_manifest, {}),
    ('stdout-append', case_stdout_append, {}),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--keep', action='store_true', help='keep the fixture directories')
    parser.add_argument('--workdir', type=Path, default=None)
    args = parser.parse_args()

    module, verifier_sha = load_verifier(args.host_root)
    print('VERIFIER ' + str((Path(args.host_root) / 'eng/verify-epoch-integration.py').resolve()) + ' sha256=' + verifier_sha)

    base = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix='epoch-provenance-'))
    base.mkdir(parents=True, exist_ok=True)
    failures = 0
    skipped = 0
    try:
        for name, case, fixture_options in CASES:
            fixture_root = base / name
            fixture_root.mkdir(parents=True, exist_ok=True)
            fixture = Fixture(fixture_root, **fixture_options)
            try:
                outcome, detail = case(fixture, module)
            except Exception as error:
                outcome, detail = False, 'fixture error: ' + type(error).__name__ + ': ' + str(error)
            if outcome is None:
                skipped += 1
                print('SKIP ' + name + ' :: ' + detail)
            elif outcome:
                print('PASS ' + name + ' :: ' + detail)
            else:
                failures += 1
                print('FAIL ' + name + ' :: ' + detail)
    finally:
        if not args.keep and args.workdir is None:
            shutil.rmtree(base, ignore_errors=True)
        else:
            print('WORKDIR ' + str(base))
    print('EPOCH_PROVENANCE_TESTS passed=' + str(len(CASES) - failures - skipped) +
          ' skipped=' + str(skipped) + ' failed=' + str(failures) + ' verifier=' + verifier_sha[:12])
    return 0 if failures == 0 else 1


if __name__ == '__main__':
    sys.exit(main())