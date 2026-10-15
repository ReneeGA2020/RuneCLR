#!/usr/bin/env python3
"""Prepare or run one owned debugger witness of the exact terminal derived ledger."""
import argparse
import ast
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
AUDITOR = ROOT / 'eng/audit-derived-ledger-windows-witness.py'

def audit_module():
    spec = importlib.util.spec_from_file_location('derived_owned_capture_review', AUDITOR)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value

def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + chr(10), encoding='ascii')

def prepare(args):
    audit = audit_module()
    output = args.output.resolve(); audit.require(not output.exists(), 'Fresh prepared lane output')
    output.mkdir(parents=True)
    build = args.build.resolve(); runtime = args.runtime.resolve(); fixture = args.fixture.resolve()
    checker = audit.module(audit.CHECKER, 'derived_capture_source')
    candidate = checker.validate(runtime, checker.COMMIT)
    built, layout_receipt = audit.load(build / 'build-result.json'), audit.load(build / 'layout-receipt.json')
    audit.require(built['exitCode'] == 0 and built['configuration'] == 'Release' and layout_receipt['passed'] and
                  built['candidateValidation'] == layout_receipt['candidateValidation'] == candidate and
                  built['candidateCheckerSha256'] == audit.sha(audit.CHECKER), 'Exact successful matching Release build')
    layout = Path(layout_receipt['layout']).resolve()
    for relative, expected in layout_receipt['allLayoutHashes'].items():
        audit.require(audit.sha(layout / relative) == expected, 'Actual matching private layout inventory')
    core = layout / 'shared/Microsoft.NETCore.App/12.0.0/coreclr.dll'
    pdb = core.with_suffix('.pdb'); dotnet = layout / 'dotnet.exe'
    cdb = Path('C:/Program Files (x86)/Windows Kits/10/Debuggers/x64/cdb.exe')
    profile = audit.load(args.profile)
    support = audit.module(audit.SUPPORT, 'derived_capture_pe')
    audit.require(audit.sha(audit.SUPPORT) == audit.SUPPORT_SHA, 'Exact independent PE reader')
    _, raw, identity = support.pe_view(core.read_bytes())
    audit.require(identity == support.pdb_identity(pdb.read_bytes()) == tuple(profile['pePdbIdentity']) and
                  profile['coreclrSha256'] == audit.sha(core) == built['criticalProductHashes']['coreclr.dll'] and
                  profile['candidateCommit'] == checker.COMMIT, 'Exact compiled native profile')
    witness = profile['witness']; branch = witness['on' if args.derived else 'off']
    points = {'enter': witness['enter'], 'action': branch['action'], 'after': branch['after']}
    for point in points.values():
        audit.require(raw(int(point['rva'], 16), len(bytes.fromhex(point['bytes']))).hex() == point['bytes'], 'Actual new witness PE bytes')
    audit.require(witness['meterRegister'] == 'rbx' and witness['flagRegister'] == 'dl', 'Reviewed emitted meter registers')
    host = fixture / 'host/TerminalProbe.Host.dll'; payload = fixture / 'payload'
    audit.require(host.is_file() and payload.is_dir(), 'Actual previously built trusted terminal fixture')
    nonce = uuid.uuid4().hex
    target = [str(dotnet), 'exec', '--fx-version', '12.0.0', str(host), str(payload), str(output / 'evidence'), args.scenario, nonce, 'terminal']
    settings = {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0', 'DOTNET_ReadyToRun': '1',
                'DOTNET_TieredCompilation': '1', 'DOTNET_MULTILEVEL_LOOKUP': '0',
                'DOTNET_RuneCLRPhaseAcquireLoad': '1', 'DOTNET_RuneCLRDerivedLedger': str(args.derived),
                'RUNECLR_POST_EXECUTION_PRECODE': '1', 'DOTNET_JitStdOutFile': str(output / 'jit.log')}
    commands = ['.printf "LEDGER_MODULE pid=%u base=%p' + chr(92) + 'n", @$tpid, coreclr',
                'lmv m coreclr', '.reload /f coreclr.dll', 'r @$t0=0']
    quote = chr(92) + chr(34); newline = chr(92) * 2 + 'n'
    for index, (label, point) in enumerate(points.items()):
        condition = ('((by(@rbx+1)==1)&(by(@rbx+3)==' + str(args.derived) +
                     ')&(dwo(@rbx+28)==0)&(qwo(@rbx+8)==(qwo(@rbx+30)-1))&(qwo(@rbx+10)==0))') if index == 0 else '(@rbx==@$t0)'
        remember = 'r @$t0=@rbx;' if index == 0 else ''
        fmt = ('LEDGER_' + label.upper() + ' pid=%u derived=%u phaseFlag=%u phase=%u meter=%p pc=%p dl=%u '
               'remaining=%p raw=%p initial=%p cleanupRemaining=%p cleanupRaw=%p cleanupInitial=%p' + newline)
        values = ('@$tpid,by(@$t0+3),by(@$t0+2),dwo(@$t0+28),@$t0,@rip,@dl,'
                  'qwo(@$t0+8),qwo(@$t0+10),qwo(@$t0+30),qwo(@$t0+18),qwo(@$t0+20),qwo(@$t0+38)')
        printf = '.printf ' + quote + fmt + quote + ',' + values + ';'
        commands.append('bp coreclr+' + point['rva'][2:] + ' ".if ' + condition + ' {' + remember +
                        'bc ' + str(index) + ';' + printf + 'db @rip L' + format(len(bytes.fromhex(point['bytes'])), 'x') + ';};gc"')
    commands.append('g')
    (output / 'loaded.cdb').write_text(chr(10).join(commands) + chr(10), encoding='ascii')
    (output / 'initial.cdb').write_text('sxd 0xe0434352' + chr(10) + 'sxe -c "$><' +
                  (output / 'loaded.cdb').as_posix() + '" ld:coreclr' + chr(10) + 'g' + chr(10), encoding='ascii')
    argv = [str(cdb), '-G', '-y', str(pdb.parent), '-cf', str(output / 'initial.cdb'), *target]
    inputs = [core, pdb, dotnet, cdb, audit.SUPPORT, audit.CHECKER, AUDITOR, args.profile.resolve(),
              build / 'build-result.json', build / 'layout-receipt.json', runtime / checker.METER, runtime / checker.CONFIG,
              *sorted((fixture / 'host').glob('*')), *sorted(payload.rglob('*.dll')),
              core.parent / 'clrinterpreter.dll', core.parent / 'clrjit.dll', core.parent / 'System.Private.CoreLib.dll']
    inputs = [path for path in inputs if path.is_file()]
    shutil.copyfile(__file__, output / 'driver.py'); shutil.copyfile(AUDITOR, output / 'auditor.py')
    shutil.copyfile(args.profile, output / 'native-profile.json')
    request = {'argv': argv, 'target': target, 'runtime': str(runtime), 'buildEvidence': str(build), 'coreclr': str(core),
               'candidateCommit': checker.COMMIT, 'candidateValidation': candidate, 'nonce': nonce,
               'scenario': args.scenario, 'derivedFlag': args.derived, 'settings': settings,
               'executionLimit': 1000000 if args.scenario == 'Good' else 2048, 'cleanupLimit': 4096,
               'meterSize': 64, 'fieldOffsets': {'derivedFlag': 3, 'initialExecutionLimit': 48, 'initialCleanupLimit': 56},
               'pePdbIdentity': identity, 'profileSha256': audit.sha(args.profile),
               'witnessRvas': {label: point['rva'] for label, point in points.items()},
               'fileCode': {label: point['bytes'] for label, point in points.items()},
               'inputHashes': {str(path): audit.sha(path) for path in inputs},
               'commandHashes': {name: audit.sha(output / name) for name in ('initial.cdb', 'loaded.cdb')},
               'driverSha256': audit.sha(__file__), 'auditorSha256': audit.sha(AUDITOR),
               'buildResultSha256': audit.sha(build / 'build-result.json'), 'layoutReceiptSha256': audit.sha(build / 'layout-receipt.json'),
               'parentRuntimeSettingsRemoved': True, 'preparedOnly': True, 'benchmark': False,
               'scope': 'Prepared first admitted normal branch; no live execution until explicit run.'}
    save(output / 'request.json', request)
    audit.preparation_guard(output)
    ast.parse(Path(__file__).read_text()); ast.parse(AUDITOR.read_text())
    save(output / 'preparation-review.json', {'passed': True, 'requestSha256': audit.sha(output / 'request.json'),
         'astParsed': True, 'preparedOnly': True, 'nativeProcessExecuted': False})
    print('PASS prepared exact64-byte debugger lane; no runtime launched')

def run(args):
    audit = audit_module(); output = args.prepared.resolve()
    audit.require(not (output / 'execution.json').exists() and not (output / 'process.json').exists(), 'Prepared lane not previously executed')
    request = audit.preparation_guard(output)
    env = {key: value for key, value in os.environ.items() if not key.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_'))}
    env.update(request['settings'])
    started = datetime.now(timezone.utc).isoformat(); begin = time.monotonic(); timed_out = False
    with (output / 'cdb.stdout').open('wb') as stdout, (output / 'cdb.stderr').open('wb') as stderr:
        process = subprocess.Popen(request['argv'], cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
        save(output / 'process.json', {'controllerPid': process.pid, 'target': request['target'], 'settings': request['settings'], 'owned': True})
        try:
            code = process.wait(timeout=90)
        except subprocess.TimeoutExpired:
            timed_out = True
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, check=False)
            process.wait(); code = process.returncode
    save(output / 'execution.json', {'controllerPid': process.pid, 'exitCode': code, 'timedOut': timed_out,
         'startedUtc': started, 'elapsedSeconds': time.monotonic() - begin,
         'stdoutSha256': audit.sha(output / 'cdb.stdout'), 'stderrSha256': audit.sha(output / 'cdb.stderr')})
    audit.require(code == 0 and not timed_out, 'Owned debugger completion failed; original attempt retained')
    report = audit.review(output); save(output / 'results.json', report)
    print(json.dumps({'passed': True, 'pid': report['actualTargetPid'], 'derivedFlag': report['actualMeterFlag'],
          'scenario': report['scenario'], 'contextCollected': True, 'negativeControls': len(report['negativeControlsRejected'])}, indent=2))

def main():
    parser = argparse.ArgumentParser(description=__doc__); actions = parser.add_subparsers(dest='action', required=True)
    p = actions.add_parser('prepare')
    for name in ('runtime', 'build', 'fixture', 'profile', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--derived', type=int, choices=(0, 1), required=True)
    p.add_argument('--scenario', choices=('Good', 'TightLoop'), required=True)
    r = actions.add_parser('run'); r.add_argument('--prepared', type=Path, required=True)
    args = parser.parse_args()
    prepare(args) if args.action == 'prepare' else run(args)

if __name__ == '__main__':
    main()
