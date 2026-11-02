import subprocess, tempfile
from pathlib import Path
import importlib.util

VERIFIER = Path(__file__).with_name('verify-runtime-reflection.py')
spec = importlib.util.spec_from_file_location('verify_runtime_reflection', VERIFIER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def commit(repo, message):
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Provenance Test',
                    '-c', 'user.email=provenance@example.invalid', 'commit', '-q', '-m', message],
                   check=True, capture_output=True, text=True)
    return git(repo, 'rev-parse', 'HEAD')


def write(repo, name, value):
    (Path(repo) / name).write_text(value, encoding='utf-8')


def make_repo(change_names=('a.txt', 'b.txt')):
    tmp = tempfile.TemporaryDirectory()
    repo = Path(tmp.name)
    git(repo, 'init', '-q')
    for name in ('a.txt', 'b.txt', 'c.txt'):
        write(repo, name, 'base-' + name)
    git(repo, 'add', '.')
    base = commit(repo, 'base')
    for name in change_names:
        write(repo, name, 'candidate-' + name)
    git(repo, 'add', '.')
    candidate = commit(repo, 'candidate')
    return tmp, repo, base, candidate


def configure(module, base, candidate, files=('a.txt', 'b.txt')):
    module.RUNTIME_BASE = base
    module.RUNTIME_COMMIT = candidate
    module.RUNTIME_FILES = tuple(files)


def expect_error(name, action):
    try:
        action()
    except ValueError as error:
        print('PASS', name, '::', str(error).splitlines()[0])
        return
    raise AssertionError(name + ' was accepted')


def check_rejection(name, mutate):
    tmp, repo, base, candidate = make_repo()
    try:
        configure(module, base, candidate)
        mutate(repo)
        expect_error(name, lambda: module.verify_runtime_provenance(repo))
    finally:
        tmp.cleanup()


def stage_change(repo):
    write(repo, 'a.txt', 'changed')
    git(repo, 'add', 'a.txt')


def advance_head(repo):
    stage_change(repo)
    commit(repo, 'third')


def main():
    tmp, repo, base, candidate = make_repo()
    try:
        configure(module, base, candidate)
        assert module.verify_runtime_provenance(repo) == candidate
        print('PASS clean published provenance')
    finally:
        tmp.cleanup()

    check_rejection('wrong head', advance_head)
    check_rejection('dirty tracked', lambda repo: write(repo, 'a.txt', 'dirty'))
    check_rejection('staged', stage_change)
    check_rejection('untracked extra', lambda repo: write(repo, 'extra.txt', 'extra'))

    tmp, repo, base, candidate = make_repo(('a.txt', 'c.txt'))
    try:
        configure(module, base, candidate)
        expect_error('wrong file delta', lambda: module.verify_runtime_provenance(repo))
    finally:
        tmp.cleanup()

    tmp = tempfile.TemporaryDirectory()
    repo = Path(tmp.name)
    try:
        git(repo, 'init', '-q')
        for name in ('a.txt', 'b.txt', 'c.txt'):
            write(repo, name, 'first-' + name)
        git(repo, 'add', '.')
        first = commit(repo, 'first')
        for name in ('a.txt', 'b.txt'):
            write(repo, name, 'base-' + name)
        git(repo, 'add', '.')
        commit(repo, 'base')
        for name in ('a.txt', 'b.txt'):
            write(repo, name, 'candidate-' + name)
        git(repo, 'add', '.')
        candidate = commit(repo, 'candidate')
        configure(module, first, candidate)
        expect_error('wrong base', lambda: module.verify_runtime_provenance(repo))
    finally:
        tmp.cleanup()

    print('PROVENANCE NEGATIVE TESTS PASS')


if __name__ == '__main__':
    main()
