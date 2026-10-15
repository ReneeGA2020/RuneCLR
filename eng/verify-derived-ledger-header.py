#!/usr/bin/env python3
"""Freeze and test the actual derived-ledger header with real Windows x64 intrinsics."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path('E:/runtime-derived-ledger-20261014')
COMPILER = Path('C:/Program Files/Microsoft Visual Studio/2022/Professional/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe')
MSVC = COMPILER.parents[3]
KIT = Path('C:/Program Files (x86)/Windows Kits/10')
KIT_VERSION = '10.0.26100.0'
HEADER = 'src/coreclr/vm/runeclrinstructionmeter.h'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*arguments):
    return subprocess.check_output(['git', '-C', str(RUNTIME), *arguments])


def invoke(argv, output, name, timeout):
    (output / (name + '-argv.json')).write_text(json.dumps(argv, indent=2), encoding='ascii')
    process = subprocess.run(argv, cwd=output, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    (output / (name + '.stdout')).write_bytes(process.stdout)
    (output / (name + '.stderr')).write_bytes(process.stderr)
    result = {'argv': argv, 'exitCode': process.returncode,
              'stdoutSha256': sha(output / (name + '.stdout')),
              'stderrSha256': sha(output / (name + '.stderr'))}
    (output / (name + '-process.json')).write_text(json.dumps(result, indent=2), encoding='ascii')
    if process.returncode:
        raise RuntimeError('Native header ' + name + ' failed; preserved evidence: ' + str(output))
    return process, result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    actual_header = RUNTIME / HEADER
    frozen_header = output / 'candidate-meter.h'
    frozen_fixture = output / 'probe.cpp'
    source_fixture = ROOT / 'eng/derived-ledger-header-probe/probe.cpp'
    shutil.copyfile(actual_header, frozen_header)
    shutil.copyfile(source_fixture, frozen_fixture)
    shutil.copyfile(Path(__file__), output / Path(__file__).name)
    shutil.copyfile(RUNTIME / 'src/coreclr/inc/volatile.h', output / 'runtime-volatile.h')
    (output / 'runtime-status.txt').write_bytes(git('status', '--porcelain'))
    (output / 'runtime-diff.patch').write_bytes(git('diff', '--binary', 'HEAD'))
    initial = {'runtime': str(RUNTIME), 'runtimeHead': git('rev-parse', 'HEAD').decode().strip(),
               'runtimeBranch': git('branch', '--show-current').decode().strip(),
               'actualHeaderSha256': sha(actual_header), 'frozenHeaderSha256': sha(frozen_header),
               'fixtureSha256': sha(frozen_fixture), 'driverSha256': sha(Path(__file__)),
               'runtimeVolatileHeaderSha256': sha(output / 'runtime-volatile.h'),
               'compiler': str(COMPILER), 'compilerSha256': sha(COMPILER)}
    (output / 'input-receipt.json').write_text(json.dumps(initial, indent=2), encoding='ascii')
    executable = output / 'probe.exe'
    argv = [str(COMPILER), '/nologo', '/O2', '/std:c++17', '/EHsc', '/Zp8', '/MT', '/volatile:ms',
            '/d1reportSingleClassLayoutRuneCLRInstructionMeter', '/I' + str(MSVC / 'include')]
    argv += ['/I' + str(KIT / 'Include' / KIT_VERSION / directory) for directory in ['ucrt', 'shared', 'um']]
    argv += ['/Fo' + str(output / 'probe.obj'), '/Fe' + str(executable), str(frozen_fixture), '/link',
             '/LIBPATH:' + str(MSVC / 'lib/x64'), '/LIBPATH:' + str(KIT / 'Lib' / KIT_VERSION / 'ucrt/x64'),
             '/LIBPATH:' + str(KIT / 'Lib' / KIT_VERSION / 'um/x64')]
    _, compile_result = invoke(argv, output, 'compile', 120)
    process, run_result = invoke([str(executable)], output, 'run', 120)
    semantics = json.loads(process.stdout)
    if not semantics['passed'] or semantics['caseCount'] != 41 or len(set(semantics['cases'])) != 41:
        raise RuntimeError('Missing expected 41 native header semantic cases.')
    pauses = semantics['CASPauseObservations']
    concurrency = semantics['trustedConcurrencyObservations']
    if len(pauses) != 8 or len(concurrency) != 8:
        raise RuntimeError('Missing expected paired CAS pause or trusted thread observations.')
    for value in pauses:
        if (value['remaining'], value['getter'], value['oldSlot'], value['phase']) != (
                0, value['derived'], 0, int(value['cleanup'])):
            raise RuntimeError('Wrong successful debit CAS window ledger observation.')
    for value in concurrency:
        if (value['executionAdmitted'], value['cleanupAdmitted']) != (20003, 10007):
            raise RuntimeError('Wrong trusted concurrent quiescent ledger.')
    if sha(actual_header) != initial['actualHeaderSha256'] or sha(source_fixture) != initial['fixtureSha256']:
        raise RuntimeError('Source changed during native header validation; preserve attempt and rerun.')
    result = {'passed': True, **initial, 'compile': compile_result, 'run': run_result,
              'semantics': semantics, 'executableSha256': sha(executable), 'objectSha256': sha(output / 'probe.obj'),
              'oldFieldOffsets': {'enabled': 0, 'terminalPrototype': 1, 'phaseAcquireLoad': 2, 'remaining': 8,
                                  'executed': 16, 'cleanupRemaining': 24, 'cleanupExecuted': 32, 'phase': 40},
              'newFieldOffsets': {'derivedLedger': 3, 'initialExecutionLimit': 48, 'initialCleanupLimit': 56},
              'size': 64, 'alignment': 8,
              'helpers': 'Actual MSVC Windows x64 Interlocked CAS32/CAS64/Increment64; MSVC volatile aligned phase load with /volatile:ms, mirroring runtime volatile.h AMD64 branch; controllable CLRConfig values.',
              'scope': 'Native header harness only. Actual unchanged candidate header, faithful thin runtime-helper wrappers, private-field near-boundary injection, trusted shared-meter threads and CAS scheduling pause. Not CLR lifecycle, interpreter method entry, performance or product evidence.'}
    (output / 'results.json').write_text(json.dumps(result, indent=2), encoding='ascii')
    print('PASS native header harness: ' + str(semantics['caseCount']) + ' cases, ' + str(semantics['checks']) + ' checks; size64 align8; ON/OFF terminal, diagnostic, exact quiescent ledgers, successful-debit CAS pause.')


if __name__ == '__main__':
    main()
