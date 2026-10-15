#!/usr/bin/env python3
"""Build an isolated collectible CID candidate from pinned simulator objects."""
import hashlib
import argparse
import json
from pathlib import Path
import shlex
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('root', nargs='?', default='/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr')
parser.add_argument('--dynamic-publication-guard', action='store_true',
                    help='Also avoid caching dynamic interface implementation owners in a separate v2 worktree')
options = parser.parse_args()
ROOT = Path(options.root)
OUT = ROOT / ('ios-r2r-fix-v2-20261012' if options.dynamic_publication_guard else 'ios-r2r-fix-20261012')
BASE = ROOT / 'runtime'
SOURCE = OUT / 'runtime'
BASE_COMMIT = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
BRANCH = 'runeclr/iossim-cid-collectible-fix' + ('-v2' if options.dynamic_publication_guard else '')
BASE_OBJ = BASE / 'artifacts/obj/coreclr/iossimulator.arm64.Debug'
OBJ = OUT / 'obj'
LOGS = OUT / 'logs'
CHANGED = 'src/coreclr/vm/virtualcallstub.cpp'
OBJECT = 'vm/wks/CMakeFiles/cee_wks_core.dir/__/virtualcallstub.cpp.o'
LIBRARY = 'dlls/mscoree/coreclr/libcoreclr.dylib'


def capture(args, cwd=None):
    return subprocess.check_output([str(a) for a in args], cwd=cwd, text=True).strip()


def run(args, log, cwd=None):
    with (LOGS / log).open('w') as stream:
        subprocess.run([str(a) for a in args], cwd=cwd, stdout=stream,
                       stderr=subprocess.STDOUT, check=True)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(name, value):
    (LOGS / name).write_text(json.dumps(value, indent=2) + '\n')


def inventory(directory):
    return {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*'))
            if p.is_file() and p.suffix in ('.o', '.a', '.pch')}


def build():
    if OUT.exists():
        raise RuntimeError('Candidate directory already exists; preserve previous evidence')
    if capture(['git', '-C', BASE, 'rev-parse', 'HEAD']) != BASE_COMMIT:
        raise RuntimeError('Baseline differs from pinned source')
    if capture(['git', '-C', BASE, 'status', '--porcelain', '--untracked-files=no']):
        raise RuntimeError('Baseline has tracked changes; refuse object reuse')
    OUT.mkdir()
    LOGS.mkdir()
    (LOGS / 'baseline-status.txt').write_text(capture(['git', '-C', BASE, 'status', '--short']) + '\n')
    evidence = json.loads((ROOT / 'target-compiler-evidence.json').read_text())
    if evidence['sourceCommit'] != BASE_COMMIT or evidence['target'] != 'iossimulator.arm64.Debug':
        raise RuntimeError('Baseline compiler provenance differs')
    if not evidence['hasInterpreter'] or not evidence['hasCollectibleTypes']:
        raise RuntimeError('Baseline lacks interpreter/collectible configuration')
    write_json('baseline-compiler-evidence.json', evidence)
    cache = (BASE_OBJ / 'CMakeCache.txt').read_text()
    if 'FEATURE_INTERPRETER:UNINITIALIZED=1' not in cache or 'CMAKE_OSX_SYSROOT:STRING=iphonesimulator' not in cache:
        raise RuntimeError('Unexpected native build configuration')
    baseline_objects = inventory(BASE_OBJ)
    baseline_native = sha(BASE_OBJ / LIBRARY)
    write_json('baseline-objects.json', baseline_objects)
    run(['git', '-C', BASE, 'worktree', 'add', '-b', BRANCH, SOURCE, BASE_COMMIT], 'worktree.log')
    source = SOURCE / CHANGED
    text = source.read_text()
    start = text.index('PCODE CachedInterfaceDispatchResolveWorker(')
    anchor = '    if (patch && pCallSite != NULL)'
    position = text.index(anchor, start)
    guard = '''    // A longer-lived dispatch cell must not retain a collectible receiver's
    // MethodTable or its implementation entrypoint beyond allocator retirement.
    if (objectType->Collectible())
        patch = FALSE;

'''
    if options.dynamic_publication_guard:
        guard = '''    // Do not retain collectible receiver metadata, or a dynamic implementation
    // whose owner can differ from the receiver's loader allocator.
    if (objectType->Collectible() || objectType->IsIDynamicInterfaceCastable())
        patch = FALSE;

'''
    source.write_text(text[:position] + guard + text[position:])
    if capture(['git', '-C', SOURCE, 'diff', '--name-only']).splitlines() != [CHANGED]:
        raise RuntimeError('Candidate changes exceed the publication guard')
    run(['git', '-C', SOURCE, 'diff', '--check'], 'diff-check.log')
    run(['git', '-C', SOURCE, 'add', CHANGED], 'stage.log')
    title = ('Avoid caching collectible and dynamic interface receivers' if options.dynamic_publication_guard
             else 'Avoid caching collectible receivers in cached interface dispatch')
    run(['git', '-C', SOURCE, 'commit', '-m', title], 'commit.log')
    revision = capture(['git', '-C', SOURCE, 'rev-parse', 'HEAD'])
    (LOGS / 'runtime.patch').write_text(capture(['git', '-C', SOURCE, 'diff', BASE_COMMIT]) + '\n')
    write_json('source.json', {'base': BASE_COMMIT, 'branch': BRANCH, 'commit': revision,
        'patchSha256': sha(LOGS / 'runtime.patch'), 'sourceSha256': sha(source),
        'configuration': 'iossimulator.arm64.Debug', 'defaultBehavior': True,
        'diagnosticSwitchRequired': False, 'dynamicInterfaceReceiverGuard': options.dynamic_publication_guard})
    # The only changed translation unit uses unchanged baseline headers/PCH.
    run(['cp', '-cR', BASE_OBJ, OBJ], 'clone-objects.log')
    if inventory(OBJ) != baseline_objects:
        raise RuntimeError('Private clone differs from baseline objects')
    commands = json.loads((BASE_OBJ / 'compile_commands.json').read_text())
    found = [c for c in commands if c['output'] == OBJECT]
    if len(found) != 1:
        raise RuntimeError('Expected one VM translation-unit command')
    args = [a.replace(str(BASE_OBJ), str(OBJ)) for a in shlex.split(found[0]['command'])]
    args = [str(source) if a == str(BASE / CHANGED) else a for a in args]
    write_json('compile-command.json', args)
    run(args, 'compile.log', cwd=OBJ)
    ninja = ROOT / 'tools/bin/ninja'
    if not ninja.exists():
        ninja = Path('/opt/homebrew/bin/ninja')
    lines = capture([ninja, '-C', BASE_OBJ, '-t', 'commands', LIBRARY]).splitlines()
    links = [line for line in lines if '-dynamiclib' in line and '-o ' + LIBRARY in line]
    if len(links) != 1:
        raise RuntimeError('Expected one CoreCLR link command')
    tokens = shlex.split(links[0])
    begin = next(i for i, t in enumerate(tokens) if t.endswith('/clang++'))
    end = next((i for i in range(begin, len(tokens)) if tokens[i] == '&&'), len(tokens))
    link = [a.replace(str(BASE_OBJ), str(OBJ)) for a in tokens[begin:end]]
    write_json('link-command.json', link)
    run(link, 'link.log', cwd=OBJ)
    candidate_objects = inventory(OBJ)
    changes = [n for n, value in candidate_objects.items() if baseline_objects.get(n) != value]
    if set(candidate_objects) != set(baseline_objects) or changes != [OBJECT]:
        raise RuntimeError('Unexpected object changes: ' + repr(changes))
    if inventory(BASE_OBJ) != baseline_objects or sha(BASE_OBJ / LIBRARY) != baseline_native:
        raise RuntimeError('Baseline native artifacts changed during the build')
    if capture(['git', '-C', SOURCE, 'status', '--porcelain']):
        raise RuntimeError('Candidate worktree not clean after build')
    write_json('artifacts.json', {'libcoreclr': str(OBJ / LIBRARY),
        'libcoreclrSha256': sha(OBJ / LIBRARY), 'baselineLibcoreclrSha256': baseline_native,
        'changedObjects': {n: sha(OBJ / n) for n in changes},
        'unchangedObjectCount': len(baseline_objects) - 1,
        'baselineObjectsUnchanged': True, 'baselineNativeUnchanged': True,
        'compileCommandsSha256': sha(BASE_OBJ / 'compile_commands.json'),
        'cmakeCacheSha256': sha(BASE_OBJ / 'CMakeCache.txt'),
        'reuse': 'APFS clone of same-base Debug objects; one VM cpp recompiled; unchanged headers/PCH; private relink'})
    (LOGS / 'build.exit').write_text('0\n')
    print(json.dumps({'commit': revision, 'libcoreclr': str(OBJ / LIBRARY),
                      'sha256': sha(OBJ / LIBRARY)}))


if __name__ == '__main__':
    build()
