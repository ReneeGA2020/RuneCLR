#!/usr/bin/env python3
"""Build a Debug-only CID diagnostic in a separate pinned runtime worktree."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else
    '/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr')
OUT = ROOT / 'ios-r2r-cache-20261012'
BASE = ROOT / 'runtime'
SOURCE = OUT / 'runtime'
BASE_COMMIT = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
BRANCH = 'runeclr/iossim-cid-cache-diagnostic'
BASE_OBJ = BASE / 'artifacts/obj/coreclr/iossimulator.arm64.Debug'
OBJ = OUT / 'obj-trace'
LOGS = OUT / 'logs-trace'

def capture(args, cwd=None):
    return subprocess.check_output([str(a) for a in args], cwd=cwd, text=True).strip()

def run(args, log, cwd=None):
    with open(LOGS / log, 'w') as stream:
        subprocess.run([str(a) for a in args], cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=True)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def build():
    LOGS.mkdir(parents=True, exist_ok=True)
    if capture(['git', '-C', BASE, 'rev-parse', 'HEAD']) != BASE_COMMIT:
        raise RuntimeError('Baseline HEAD differs from the pinned source')
    (LOGS / 'baseline-status.txt').write_text(capture(['git', '-C', BASE, 'status', '--short']) + '\n')
    if not SOURCE.exists():
        run(['git', '-C', BASE, 'worktree', 'add', '-b', BRANCH, SOURCE, BASE_COMMIT], 'worktree.log')
    source_head = capture(['git', '-C', SOURCE, 'rev-parse', 'HEAD'])
    subprocess.run(['git', '-C', str(SOURCE), 'merge-base', '--is-ancestor', BASE_COMMIT, source_head], check=True)
    if capture(['git', '-C', SOURCE, 'status', '--porcelain']):
        raise RuntimeError('Diagnostic worktree is not clean; refusing to overwrite work')
    config = SOURCE / 'src/coreclr/inc/clrconfigvalues.h'
    text = config.read_text()
    anchor = '/// Assembly Loader'
    if text.count(anchor) != 1:
        raise RuntimeError('Unexpected configuration table')
    knob = '''CONFIG_DWORD_INFO(INTERNAL_RuneCLRDisableCollectibleInterfaceDispatchCache, W("RuneCLRDisableCollectibleInterfaceDispatchCache"), 0, "RuneCLR diagnostic: 1 disables collectible target caching, 2 traces without disabling.")

'''
    if source_head == BASE_COMMIT:
        text = text.replace('///\n' + anchor, knob + '///\n' + anchor, 1)
    if 'INTERNAL_RuneCLRDisableCollectibleInterfaceDispatchCache' not in text:
        raise RuntimeError('Configuration insertion failed')
    if source_head == BASE_COMMIT:
        config.write_text(text)
    source = SOURCE / 'src/coreclr/vm/virtualcallstub.cpp'
    text = source.read_text()
    start = text.index('PCODE CachedInterfaceDispatchResolveWorker(')
    position = text.index('    if (patch && pCallSite != NULL)', start)
    diagnostic = '''#if defined(_DEBUG)
    // Isolate collectible target lifetime without changing the default dispatch path.
    if (patch && pCallSite != NULL && objectType->Collectible())
    {
        DWORD diagnosticMode = CLRConfig::GetConfigValue(CLRConfig::INTERNAL_RuneCLRDisableCollectibleInterfaceDispatchCache);
        if (diagnosticMode != 0)
        {
            fprintf(stderr, "RUNECLR_CID_RESOLVE skip=%u cell=%p mt=%p target=%p\\n",
                diagnosticMode & 1, pCallSite->GetIndirectCell(), objectType, (void*)target);
            if ((diagnosticMode & 1) != 0)
                patch = FALSE;
        }
    }
#endif

'''
    if source_head == BASE_COMMIT:
        source.write_text(text[:position] + diagnostic + text[position:])
    elif 'diagnosticMode & 1' not in text:
        raise RuntimeError('Existing diagnostic worktree is not the trace-control revision')
    changed = capture(['git', '-C', SOURCE, 'diff', '--name-only', BASE_COMMIT]).splitlines()
    if set(changed) != {'src/coreclr/inc/clrconfigvalues.h', 'src/coreclr/vm/virtualcallstub.cpp'}:
        raise RuntimeError('Diagnostic worktree contains additional source changes')
    (LOGS / 'runtime.patch').write_text(capture(['git', '-C', SOURCE, 'diff', BASE_COMMIT]) + '\n')
    (LOGS / 'source.json').write_text(json.dumps({
        'base': BASE_COMMIT, 'branch': capture(['git', '-C', SOURCE, 'branch', '--show-current']),
        'patchSha256': sha(LOGS / 'runtime.patch'), 'sourceSha256': sha(source),
        'configSha256': sha(config), 'commit': source_head if source_head != BASE_COMMIT else 'uncommitted diagnostic patch',
    }, indent=2) + '\n')
    # APFS clones keep every untouched object bit-for-bit and never alter baseline outputs.
    if OBJ.exists():
        raise RuntimeError('Private object directory already exists')
    run(['cp', '-cR', BASE_OBJ, OBJ], 'clone-objects.log')
    overlay = OUT / 'headers-overlay.json'
    overlay.write_text(json.dumps({
        'version': 0, 'use-external-names': False,
        'roots': [{'type': 'file', 'name': str(BASE / 'src/coreclr/inc/clrconfigvalues.h'),
                   'external-contents': str(config)}],
    }, indent=2))
    commands = json.loads((BASE_OBJ / 'compile_commands.json').read_text())
    outputs = [
        'utilcode/CMakeFiles/utilcode.dir/cmake_pch.hxx.pch',
        'vm/wks/CMakeFiles/cee_wks_core.dir/cmake_pch.hxx.pch',
        'utilcode/CMakeFiles/utilcode.dir/clrconfig.cpp.o',
        'vm/wks/CMakeFiles/cee_wks_core.dir/__/virtualcallstub.cpp.o',
    ]
    selected = []
    for output in outputs:
        found = [c for c in commands if c['output'] == output]
        if len(found) != 1:
            raise RuntimeError('Expected exactly one compile command for ' + output)
        args = shlex.split(found[0]['command'])
        args = [a.replace(str(BASE_OBJ), str(OBJ)) for a in args]
        if output.endswith('virtualcallstub.cpp.o'):
            args = [str(source) if a == str(BASE / 'src/coreclr/vm/virtualcallstub.cpp') else a for a in args]
        args += ['-ivfsoverlay', str(overlay)]
        selected.append(args)
        run(args, 'compile-' + str(len(selected)) + '.log', cwd=OBJ)
    (LOGS / 'compile-commands.json').write_text(json.dumps(selected, indent=2) + '\n')
    ninja = ROOT / 'tools/bin/ninja'
    if not ninja.exists():
        ninja = Path('/opt/homebrew/bin/ninja')
    link_target = 'dlls/mscoree/coreclr/libcoreclr.dylib'
    link_lines = capture([ninja, '-C', BASE_OBJ, '-t', 'commands', link_target]).splitlines()
    matches = [line for line in link_lines if '-dynamiclib' in line and '-o ' + link_target in line]
    if len(matches) != 1:
        raise RuntimeError('Expected one CoreCLR dynamic-library link command')
    tokens = shlex.split(matches[0])
    begin = next(i for i, t in enumerate(tokens) if t.endswith('/clang++'))
    end = next((i for i in range(begin, len(tokens)) if tokens[i] == '&&'), len(tokens))
    args = [t.replace(str(BASE_OBJ), str(OBJ)) for t in tokens[begin:end]]
    (LOGS / 'link-command.json').write_text(json.dumps(args, indent=2) + '\n')
    run(args, 'link.log', cwd=OBJ)
    binary = OBJ / link_target
    (LOGS / 'artifacts.json').write_text(json.dumps({
        'libcoreclr': str(binary), 'libcoreclrSha256': sha(binary),
        'patchedObjects': {name: sha(OBJ / name) for name in outputs},
    }, indent=2) + '\n')
    (LOGS / 'build.exit').write_text('0\n')

if __name__ == '__main__':
    build()
