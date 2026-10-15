"""Private stock-Lua count-hook comparison; raw-log audit is a separate phase."""
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'artifacts/performance/tools/lua-5.4.9.tar.gz'
SOURCE = ROOT / 'artifacts/performance/tools/lua-5.4.9/src'
ARCHIVE_SHA = '2335b6c582a52654f94612bf10d2f4672805d05329aa6568b1d8cd9e5c6fb8e6'
INPUTS = ['benchmarks/scripts/lua-budget-runner.c', 'benchmarks/scripts/budget-workload.lua',
          'eng/benchmark-lua-budget.py']
MODES = [('no-config', 0), ('count1', 1), ('count100', 100), ('count1000', 1000)]
ORDERS = [[0, 1, 3, 2], [1, 2, 0, 3], [2, 3, 1, 0], [3, 0, 2, 1]]

def require(ok, message):
    if not ok:
        raise ValueError(message)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def verify_inputs(manifest, out):
    require(digest(ARCHIVE) == ARCHIVE_SHA == manifest['archiveSha256'], 'archive mismatch')
    for rel, expected in manifest['inputs'].items():
        require(digest(ROOT / rel) == expected == digest(out / 'source' / rel), 'input drift: ' + rel)
    for name, expected in manifest['luaSources'].items():
        require(digest(SOURCE / name) == expected, 'Lua source drift: ' + name)
    require(digest(out / 'build/lua-budget.exe') == manifest['exeSha256'], 'runner binary drift')
    require(digest(manifest['compiler']) == manifest['compilerSha256'], 'compiler drift')

def prepare(out):
    require(os.name == 'nt', 'Windows x64 experiment only')
    require(not out.exists(), 'use a fresh output directory')
    require(digest(ARCHIVE) == ARCHIVE_SHA, 'official archive SHA mismatch')
    sources = {}
    with tarfile.open(ARCHIVE, 'r:gz') as archive:
        for member in archive.getmembers():
            if member.isfile() and member.name.startswith('lua-5.4.9/src/'):
                name = member.name.rsplit('/', 1)[-1]
                if name.endswith(('.c', '.h')):
                    expected = hashlib.sha256(archive.extractfile(member).read()).hexdigest()
                    require(digest(SOURCE / name) == expected, 'modified Lua input: ' + name)
                    sources[name] = expected
    require(len(sources) >= 50, 'incomplete official inputs')
    (out / 'build').mkdir(parents=True)
    for rel in INPUTS:
        target = out / 'source' / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / rel).read_bytes())
    vswhere = Path(os.environ['ProgramFiles(x86)']) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    vs = subprocess.check_output([str(vswhere), '-latest', '-products', '*', '-requires',
        'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], text=True).strip()
    require(bool(vs), 'MSVC Build Tools missing')
    builddir = out / 'build'
    c_files = sorted(str(SOURCE / name) for name in sources if name.endswith('.c') and name not in ('lua.c', 'luac.c'))
    flags = ['/nologo', '/O2', '/DNDEBUG', '/MD', '/DLUA_USE_WINDOWS']
    command = 'cl ' + ' '.join(flags) + ' /I"' + str(SOURCE) + '" /Fe:"' + str(builddir / 'lua-budget.exe') + '" '
    command += ' '.join('"' + p + '"' for p in c_files + [str(ROOT / INPUTS[0])])
    script = '\n'.join(['@echo off', 'call "' + str(Path(vs) / 'Common7/Tools/VsDevCmd.bat') + '" -arch=x64 -host_arch=x64',
        'if errorlevel 1 exit /b %errorlevel%', 'where cl > compiler-path.txt',
        'cl /Bv > compiler-version.txt 2>&1', command, 'exit /b %errorlevel%', ''])
    (builddir / 'build.cmd').write_text(script, encoding='ascii')
    result = subprocess.run(['cmd.exe', '/d', '/c', str(builddir / 'build.cmd')], cwd=builddir, capture_output=True)
    (out / 'build.stdout').write_bytes(result.stdout)
    (out / 'build.stderr').write_bytes(result.stderr)
    require(result.returncode == 0, 'Lua compile failed; see build.stdout/build.stderr')
    compiler = (builddir / 'compiler-path.txt').read_text().splitlines()[0].strip()
    machine = subprocess.check_output(['powershell.exe', '-NoProfile', '-Command',
        '[pscustomobject]@{cpu=(Get-CimInstance Win32_Processor).Name;os=[Environment]::OSVersion.VersionString;processorCount=[Environment]::ProcessorCount} | ConvertTo-Json -Compress'], text=True)
    manifest = dict(createdUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        archiveSha256=ARCHIVE_SHA, luaSources=sources, inputs={rel: digest(ROOT / rel) for rel in INPUTS},
        exeSha256=digest(builddir / 'lua-budget.exe'), compiler=compiler, compilerSha256=digest(compiler),
        compilerFlags=flags, machine=json.loads(machine), warmups=3, samples=9, rounds=4,
        affinityMask=4, logicalProcessor=2, timer='QueryPerformanceCounter, wall clock; setup excluded',
        modes=MODES, orders=ORDERS, expectedChecksum=12749776, iterations=100000)
    write(out / 'manifest.json', manifest)
    verify_inputs(manifest, out)
    print(json.dumps(dict(prepared=True, exeSha256=manifest['exeSha256'], output=str(out))))

def measure(out):
    manifest = read(out / 'manifest.json')
    verify_inputs(manifest, out)
    require(not (out / 'raw').exists(), 'raw output already exists; do not replay')
    (out / 'raw').mkdir()
    receipts = []
    for round_index, order in enumerate(ORDERS):
        for mode_index in order:
            name, interval = MODES[mode_index]
            nonce = uuid.uuid4().hex
            label = 'round%d-%s' % (round_index + 1, name)
            command = [str(out / 'build/lua-budget.exe'), str(ROOT / INPUTS[1]), str(interval), '9', nonce]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(timeout=180)
            (out / 'raw' / (label + '.stdout')).write_bytes(stdout)
            (out / 'raw' / (label + '.stderr')).write_bytes(stderr)
            receipts.append(dict(round=round_index + 1, mode=name, interval=interval, nonce=nonce,
                pid=process.pid, exitCode=process.returncode, command=command,
                stdout='raw/' + label + '.stdout', stderr='raw/' + label + '.stderr',
                stdoutSha256=hashlib.sha256(stdout).hexdigest(), stderrSha256=hashlib.sha256(stderr).hexdigest()))
            write(out / 'processes.json', receipts)
            require(process.returncode == 0, 'runner failed: ' + label)
            print(label + ' PASS', flush=True)
    verify_inputs(manifest, out)

def verify_raw(manifest, receipts, logs):
    require(len(receipts) == 16, 'expected sixteen fresh owned processes')
    require(len({r['nonce'] for r in receipts}) == 16, 'nonce reuse')
    reference_events = []
    summaries = {name: [] for name, _ in MODES}
    for index, receipt in enumerate(receipts):
        round_index, position = divmod(index, 4)
        name, interval = MODES[ORDERS[round_index][position]]
        require(receipt['round'] == round_index + 1 and receipt['mode'] == name and receipt['interval'] == interval, 'process order mismatch')
        require(receipt['exitCode'] == 0, 'runner failed')
        records = logs[index]
        require(len(records) == (15 if interval else 13), 'record count mismatch')
        header = records[0]
        require(header['kind'] == 'process' and header['lua'] == 'Lua 5.4.9' and header['pid'] == receipt['pid']
            and header['nonce'] == receipt['nonce'] and header['interval'] == interval and header['affinity'] == 4
            and header['qpcFrequency'] > 0 and header['highBudget'] == 1000000000000, 'process identity/settings mismatch')
        events = []
        for sample_index, record in enumerate(records[1:13]):
            require(record['kind'] == ('warmup' if sample_index < 3 else 'sample')
                and record['index'] == (sample_index if sample_index < 3 else sample_index - 3), 'warmup/sample order mismatch')
            require(record['checksum'] == 12749776, 'workload checksum mismatch')
            expected_ms = record['elapsedTicks'] * 1000 / header['qpcFrequency']
            require(record['elapsedTicks'] > 0 and abs(record['elapsedMs'] - expected_ms) < 0.000001, 'QPC timing mismatch')
            if interval:
                require(type(record['events']) is int and record['events'] > 0 and record['estimatedCountedInstructions'] == record['events'] * interval, 'event estimate mismatch')
                events.append(record['events'])
            else:
                require(record['events'] is None and record['estimatedCountedInstructions'] is None, 'disabled hook reported count')
        if interval:
            require(len(set(events)) == 1, 'unstable hook event count')
            reference_events.append((interval, events[0]))
            for control_index, control in enumerate(records[13:]):
                require(control == dict(kind='control', name='small-quota' if control_index else 'zero-quota',
                    allowance=interval * 2 if control_index else 0, events=3 if control_index else 1,
                    remaining=0, rejected=True, recoveredChecksum=12749776), 'quota/recovery control mismatch')
        times = [r['elapsedMs'] for r in records[4:13]]
        summaries[name].append(dict(round=round_index + 1, medianMs=statistics.median(times), times=times,
            eventsPerInvocation=events[0] if events else None))
    reference = {events for interval, events in reference_events if interval == 1}
    require(len(reference) == 1, 'count1 reference unstable')
    reference = next(iter(reference))
    for interval, events in reference_events:
        require(0 <= reference - interval * events < interval, 'batched instruction-count remainder mismatch')
    baseline = summaries['no-config']
    result = []
    for name, interval in MODES:
        rows = summaries[name]
        times = [t for r in rows for t in r['times']]
        ratio = statistics.median(times) / statistics.median([t for r in baseline for t in r['times']])
        round_ratios = [rows[i]['medianMs'] / baseline[i]['medianMs'] for i in range(4)]
        result.append(dict(mode=name, interval=interval, medianMs=statistics.median(times), minMs=min(times),
            maxMs=max(times), relativeToNoConfig=ratio, addedTimePercent=(ratio - 1) * 100,
            roundRelativeRange=[min(round_ratios), max(round_ratios)], rounds=rows))
    return dict(passed=True, processes=16, timedSamples=144, warmups=48, quotaRecoveryControls=24,
        count1EventsPerInvocation=reference, summary=result)

def audit(out):
    require(not (out / 'audit.json').exists(), 'audit output already exists')
    manifest = read(out / 'manifest.json')
    verify_inputs(manifest, out)
    receipts = read(out / 'processes.json')
    logs = []
    for receipt in receipts:
        require(digest(out / receipt['stdout']) == receipt['stdoutSha256'] and digest(out / receipt['stderr']) == receipt['stderrSha256'], 'raw log hash mismatch')
        require(not (out / receipt['stderr']).read_bytes(), 'unexpected runner stderr')
        logs.append([json.loads(line) for line in (out / receipt['stdout']).read_text().splitlines()])
    result = verify_raw(manifest, receipts, logs)
    mutations = [('checksum', 0, 4, 'checksum', 1), ('elapsed', 0, 4, 'elapsedTicks', 1),
        ('affinity', 0, 0, 'affinity', 1), ('nonce', 0, 0, 'nonce', 'invalid'),
        ('events', 1, 4, 'events', 1), ('recovery', 1, 13, 'recoveredChecksum', 1)]
    rejected = []
    for name, process_index, record_index, field, value in mutations:
        changed = copy.deepcopy(logs)
        changed[process_index][record_index][field] = value
        try:
            verify_raw(manifest, receipts, changed)
        except (ValueError, KeyError, TypeError):
            rejected.append(name)
    require(len(rejected) == len(mutations), 'negative audit control accepted')
    result['negativeControlsRejected'] = rejected
    result['manifestSha256'] = digest(out / 'manifest.json')
    result['processesSha256'] = digest(out / 'processes.json')
    write(out / 'audit.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'summary'}))
    for row in result['summary']:
        print(json.dumps({k: v for k, v in row.items() if k != 'rounds'}))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['prepare', 'measure', 'audit'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.is_relative_to(ROOT / 'artifacts/lua-budget'), 'output must be under artifacts/lua-budget')
    {'prepare': prepare, 'measure': measure, 'audit': audit}[args.phase](out)

if __name__ == '__main__':
    main()
