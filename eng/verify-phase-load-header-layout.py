#!/usr/bin/env python3
"""Compile frozen baseline/candidate meter headers to verify Windows x64 field layout only."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path('E:/runtime-phase-load-20261014')
COMPILER = Path('C:/Program Files/Microsoft Visual Studio/2022/Professional/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe')
INCLUDE = COMPILER.parents[3] / 'include'
UCRT = Path('C:/Program Files (x86)/Windows Kits/10/Include/10.0.26100.0/ucrt')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    checker_path = ROOT / 'eng/phase-load-runtime-candidate.py'
    spec = importlib.util.spec_from_file_location('phase_load_layout_candidate', checker_path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    candidate = checker.validate(RUNTIME)
    offsets = {'m_enabled': 0, 'm_terminalPrototype': 1, 'm_remaining': 8, 'm_executed': 16,
               'm_cleanupRemaining': 24, 'm_cleanupExecuted': 32, 'm_phase': 40}
    results = {}
    for name, commit in [('baseline', checker.BASELINE), ('candidate', checker.COMMIT)]:
        header = output / (name + '-meter.h')
        header.write_bytes(checker.git(RUNTIME, 'show', commit + ':' + checker.METER))
        lines = ['#include <stddef.h>',
                 'typedef long LONG;', 'typedef __int64 LONGLONG;', 'typedef __int64 INT64;',
                 '#define INT64_MAX 9223372036854775807i64', '#define FORCEINLINE __forceinline',
                 'LONG InterlockedCompareExchange(volatile LONG*, LONG, LONG);',
                 'LONGLONG InterlockedCompareExchange64(volatile LONGLONG*, LONGLONG, LONGLONG);',
                 'LONGLONG InterlockedIncrement64(volatile LONGLONG*);',
                 'template<typename T> T VolatileLoad(T const*);',
                 'struct CLRConfig { enum { EXTERNAL_RuneCLRPhaseAcquireLoad }; static int GetConfigValue(int); };',
                 '#define private public', '#include "' + header.name + '"', '#undef private']
        lines += ['static_assert(offsetof(RuneCLRInstructionMeter, ' + field + ') == ' + str(value) + ');'
                  for field, value in offsets.items()]
        lines += ['static_assert(sizeof(RuneCLRInstructionMeter) == 48);',
                  'static_assert(alignof(RuneCLRInstructionMeter) == 8);',
                  'int layout_size() { return sizeof(RuneCLRInstructionMeter); }']
        source = output / (name + '-layout.cpp')
        source.write_text(chr(10).join(lines) + chr(10), encoding='ascii')
        obj = output / (name + '-layout.obj')
        argv = [str(COMPILER), '/nologo', '/c', '/O2', '/std:c++17', '/Zp8',
                '/d1reportSingleClassLayoutRuneCLRInstructionMeter', '/I' + str(INCLUDE), '/I' + str(UCRT),
                '/Fo' + str(obj), str(source)]
        process = subprocess.run(argv, cwd=output, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (output / (name + '.stdout')).write_bytes(process.stdout)
        (output / (name + '.stderr')).write_bytes(process.stderr)
        if process.returncode != 0:
            raise RuntimeError('Header layout compile failed; attempt preserved: ' + name)
        results[name] = {'commit': commit, 'argv': argv, 'exitCode': process.returncode,
                         'headerSha256': sha(header), 'sourceSha256': sha(source),
                         'objectSha256': sha(obj), 'stdoutSha256': sha(output / (name + '.stdout')),
                         'stderrSha256': sha(output / (name + '.stderr'))}
    assert checker.validate(RUNTIME) == candidate
    result = {'passed': True, 'candidateValidation': candidate, 'compiler': str(COMPILER),
              'compilerSha256': sha(COMPILER), 'checkerSha256': sha(checker_path),
              'driverSha256': sha(Path(__file__)), 'results': results,
              'oldFieldOffsetsUnchanged': offsets, 'meterSize': 48, 'meterAlignment': 8,
              'newFlagOffset': 2, 'architecture': 'Windows x64 MSVC /Zp8',
              'scope': 'Actual paired header compilation proves layout; declarations mock runtime helpers and do not establish runtime semantics, codegen, or new path execution.'}
    (output / 'layout-receipt.json').write_text(json.dumps(result, indent=2), encoding='ascii')
    print('PASS paired native header layout: offsets unchanged, size48 align8, new flag in padding2', flush=True)

if __name__ == '__main__':
    main()
