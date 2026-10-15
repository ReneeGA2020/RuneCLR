#!/usr/bin/env python3
"""One owned CDB phase-switch witness with unchanged trusted fixtures."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def require(value, message):
    if not value:
        raise AssertionError(message)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--flag', type=int, choices=(0, 1), required=True)
    p.add_argument('--scenario', choices=('Good', 'CatchReturn', 'TightLoop'), required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    require(not out.exists(), 'Fresh owned output required')
    out.mkdir(parents=True)
    root = Path(__file__).resolve().parents[1]
    layout = root / 'artifacts/phase-load/windows-release-build-20261014-attempt1/layout'
    core = layout / 'shared/Microsoft.NETCore.App/12.0.0/coreclr.dll'
    pdb = core.with_suffix('.pdb')
    dotnet = layout / 'dotnet.exe'
    cdb = Path('C:/Program Files (x86)/Windows Kits/10/Debuggers/x64/cdb.exe')
    fixture = root / 'artifacts/phase-load/windows-acceptance-preparation-20261014-attempt2/off/evidence/terminal'
    host, payload = fixture / 'host/TerminalProbe.Host.dll', fixture / 'payload'
    helper = root / 'eng/audit-budget-hotpath.py'
    require(sha(core) == 'b1e9c8ffc40ffa20f4c4744a280152fe65fc2c7bfac0191486ca329e25b06b3c', 'Exact candidate DLL')
    require(sha(helper) == 'd33f69318fec46e2cb16daaff114ff53c19c20b3dd69a0b709476ac105636a40', 'Frozen PE/PDB reader')
    spec = importlib.util.spec_from_file_location('phase_pe', helper)
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    _, read_rva, identity = support.pe_view(core.read_bytes())
    require(identity == support.pdb_identity(pdb.read_bytes()) == ('ab785a5f-4446-4757-8a83-ae3f8db1834e', 1), 'Exact PE/PDB identity')
    nonce = uuid.uuid4().hex
    evidence = out / 'evidence'
    target = [str(dotnet), 'exec', '--fx-version', '12.0.0', str(host), str(payload), str(evidence), args.scenario, nonce, 'terminal']
    settings = {'DOTNET_InterpMode': '0', 'DOTNET_RuneCLRInterpretCollectible': '0', 'DOTNET_ReadyToRun': '1',
                'DOTNET_TieredCompilation': '1', 'DOTNET_MULTILEVEL_LOOKUP': '0',
                'DOTNET_RuneCLRPhaseAcquireLoad': str(args.flag), 'RUNECLR_POST_EXECUTION_PRECODE': '1',
                'DOTNET_JitStdOutFile': str(out / 'jit.log')}
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_')):
            del env[key]
    env.update(settings)
    branch = 0x18e326 if args.flag else 0x18e336
    after = 0x18e329 if args.flag else 0x18e33b
    loaded = out / 'loaded.cdb'
    commands = ['.printf "PHASE_MODULE pid=%u base=%p\\n", @$tpid, coreclr', 'lmv m coreclr', '.reload /f coreclr.dll', 'r @$t0=0', 'r @$t1=0']
    for index, (label, rva, size) in enumerate([('ENTER', 0x18e320, 0x1c), ('BRANCH', branch, 3 if args.flag else 5), ('AFTER', after, 3 if args.flag else 1)]):
        printf = ('.printf \\"PHASE_' + label + ' pid=%u flag=%u phase=%u meter=%p pc=%p eax=%x caller=%p\\\\n\\",'
                  '@$tpid,by(@rcx+2),dwo(@rcx+28),@rcx,@rip,@eax,poi(@rsp);')
        condition = '((poi(@rsp)==coreclr+1986f5)|(poi(@rsp)==coreclr+1987bf))' if index == 0 else '((@rcx==@$t0)&(poi(@rsp)==@$t1))'
        remember = 'r @$t0=@rcx;r @$t1=poi(@rsp);' if index == 0 else ''
        commands.append('bp coreclr+' + format(rva, 'x') + ' ".if ' + condition + ' {' + remember +
                        'bc ' + str(index) + ';' + printf + 'db @rip L' + format(size, 'x') + ';};gc"')
    commands.append('g')
    loaded.write_text('\n'.join(commands) + '\n')
    initial = out / 'initial.cdb'
    initial.write_text('sxd 0xe0434352\nsxe -c "$><' + loaded.as_posix() + '" ld:coreclr\ng\n')
    argv = [str(cdb), '-G', '-y', str(pdb.parent), '-cf', str(initial), *target]
    inputs = [core, pdb, dotnet, cdb, helper, *sorted((fixture / 'host').glob('*')), *sorted(payload.rglob('*.dll')),
              core.parent / 'clrinterpreter.dll', core.parent / 'clrjit.dll', core.parent / 'System.Private.CoreLib.dll']
    inputs = [x for x in inputs if x.is_file()]
    (out / 'driver.py').write_bytes(Path(__file__).read_bytes())
    request = {'argv': argv, 'target': target, 'nonce': nonce, 'scenario': args.scenario, 'flag': args.flag,
               'settings': settings, 'parentRuntimeSettingsRemoved': True, 'pePdbIdentity': identity,
               'hotLoopCaller': True, 'callerRvas': ['0x1986f5', '0x1987bf'],
               'phaseRvas': {'enter': hex(0x18e320), 'branch': hex(branch), 'after': hex(after)},
               'fileCode': {'enter': read_rva(0x18e320, 0x1c).hex(), 'branch': read_rva(branch, 3 if args.flag else 5).hex(),
                            'after': read_rva(after, 3 if args.flag else 1).hex()},
               'inputHashes': {str(x): sha(x) for x in inputs}, 'driverSha256': sha(__file__),
               'commandHashes': {str(x): sha(x) for x in (initial, loaded)},
               'startedUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'benchmark': False}
    write(out / 'request.json', request)
    start = time.monotonic()
    with (out / 'cdb.stdout').open('wb') as stdout, (out / 'cdb.stderr').open('wb') as stderr:
        proc = subprocess.Popen(argv, env=env, cwd=root, stdout=stdout, stderr=stderr)
        write(out / 'process.json', {'controllerPid': proc.pid, 'target': target, 'settings': settings, 'owned': True})
        try:
            code = proc.wait(timeout=90)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, check=False)
            proc.wait()
            write(out / 'failure.json', {'timedOut': True, 'controllerPid': proc.pid})
            raise
    write(out / 'execution.json', {'controllerPid': proc.pid, 'exitCode': code, 'elapsedSeconds': time.monotonic() - start,
                                  'stdoutSha256': sha(out / 'cdb.stdout'), 'stderrSha256': sha(out / 'cdb.stderr')})
    require(code == 0, 'Actual CDB completion')
    audit_spec = importlib.util.spec_from_file_location('phase_witness_audit', root / 'eng/audit-phase-load-windows-witness.py')
    audit = importlib.util.module_from_spec(audit_spec)
    audit_spec.loader.exec_module(audit)
    report = audit.review(out)
    write(out / 'results.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
