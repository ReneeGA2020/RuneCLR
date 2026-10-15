#!/usr/bin/env python3
"""Bounded current-image initial interpreter entry capture on the owned emulator."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time
import traceback
import uuid

BASE_SHA = '66adcf5a7a60a13db4695d43b2c4a18643ab39392d7f33884d74da7ba5e46c50'

def helper(name):
    path = Path(__file__).with_name(name + '.py')
    if name == 'android-batch-boundary-apk':
        assert hashlib.sha256(path.read_bytes()).hexdigest() == BASE_SHA
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def transport(args):
    base = helper('android-batch-boundary-apk')
    installer = helper('android-batch-boundary-entry-install')
    base.inventory = lambda a, s, o, n, d: installer.inventory(base, a, s, o, n, d)
    base.device(args)
    root = args.output.resolve()
    state = base.load(root / 'state.json')
    assert state['runtimeTree'] == base.TREE and state['installed']
    assert base.load(root / 'entry-build.json')['onlyJniOptInGateDelta']
    assert base.sha(state['apk']) == state['apkSha256']
    assert re.fullmatch(r'net.dot.RuneCLR_BatchBoundary_[0-9a-f]{12}', state['package'])
    pkg, nonce = state['package'], uuid.uuid4().hex
    out = root / ('capture-' + nonce)
    out.mkdir()
    shutil.copy2(__file__, out / 'driver.py')
    adbexe = args.android_root / 'sdk/platform-tools/adb.exe'
    ndk = args.android_root / 'sdk/ndk/27.2.12479018/toolchains/llvm/prebuilt/windows-x86_64'
    server_file = ndk / 'lib/clang/18/lib/linux/x86_64/lldb-server'
    records = []
    app = server = debugger = None
    forward = server_pid = None
    app_log = server_log = debug_log = None
    staging = '/data/local/tmp/runeclr-batch-lldb-' + nonce
    relative = 'files/runeclr-batch-lldb-' + nonce
    result = {'passed': False, 'nativeEntryProof': False, 'debugger': True, 'nonce': nonce,
              'package': pkg, 'serial': args.serial, 'driverSha256': base.sha(__file__),
              'configuredInterval': 100, 'matrixInterval': 100, 'intervalHex': '64',
              'scope': 'Four initial interpreter entries only; no dispatch cadence or performance claim; independent review required'}

    def adb(*argv, check=True):
        command = [str(adbexe), '-s', args.serial, *map(str, argv)]
        done = subprocess.run(command, capture_output=True, timeout=60)
        records.append({'command': command, 'exit': done.returncode,
                        'stdout': done.stdout.decode(errors='replace'), 'stderr': done.stderr.decode(errors='replace')})
        if check and done.returncode:
            raise RuntimeError('Owned ADB failed: ' + repr(command))
        return done.stdout.decode(errors='replace').strip()

    def owned(*argv, **kwargs):
        return adb('shell', 'run-as', pkg, *argv, **kwargs)

    try:
        appinfo = adb('shell', 'dumpsys', 'package', pkg)
        (out / 'package-before.txt').write_text(appinfo)
        match = re.search(r'(?m)^\s*(?:legacyNativeLibraryDir|nativeLibraryDir)=([^\s]+)', appinfo)
        assert match
        natives = owned('find', match[1], '-name', 'libcoreclr.so').splitlines()
        assert len(natives) == 1 and natives[0].endswith('/libcoreclr.so')
        native_dir = natives[0].rsplit('/', 1)[0]
        before = base.inventory(args, state, out, 'installed-before', native_dir)
        result['lldbServerSha256'] = base.sha(server_file)
        assert result['lldbServerSha256'] == '873ecfdf9fe588ace2a64122ac7f4b77b8c18bf684eb608653e0b127c9b651c7'
        adb('push', server_file, staging)
        owned('cp', staging, relative)
        owned('chmod', '700', relative)
        assert owned('sha256sum', relative).split()[0] == base.sha(server_file)
        adb('shell', 'am', 'force-stop', pkg)
        command = [str(adbexe), '-s', args.serial, 'shell', 'am', 'instrument', '-w',
                   '-e', 'env:RUNECLR_BATCH_NONCE', nonce, '-e', 'env:RUNECLR_BATCH_MATRIX', '100',
                   '-e', 'env:RUNECLR_BATCH_HEX', '64',
                   '-e', 'env:RUNECLR_BATCH_NATIVE_ENTRY_WAIT', '1', pkg + '/net.dot.MonoRunner']
        base.write(out / 'request.json', {'command': command, 'nonce': nonce, 'apkSha256': state['apkSha256'],
            'sourceTree': state['runtimeTree'], 'startedUtc': base.utc(), 'configured': 100, 'matrix': 100,
            'inputManifestSha256': state['inputManifestSha256'], 'layoutSha256': state['layoutSha256']})
        app_log = (out / 'instrumentation.log').open('wb')
        app = subprocess.Popen(command, stdout=app_log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            query = owned('cat', 'files/batch-' + nonce + '.pid-query.txt', check=False)
            native = owned('cat', 'files/batch-' + nonce + '.native.log', check=False)
            match = re.fullmatch(r'android.os.Process.myPid=([0-9]+)', query)
            if match and 'state=waiting' in native:
                break
            if app.poll() is not None:
                raise RuntimeError('App exited before gate')
            time.sleep(.3)
        else:
            raise RuntimeError('Owned gate absent within45seconds')
        pid = int(match[1])
        result['appPid'] = pid
        header = f'ANDROID_BATCH_NATIVE pid={pid} nonce={nonce} matrix=100 interval=64 PhaseAcquireLoad=1 DerivedLedger=0 InterpMode=0 ReadyToRun=1'
        gate = f'ANDROID_ENTRY_GATE pid={pid} runId={nonce}'
        assert header in native and gate + ' state=waiting dumpableResult=0' in native
        assert 'CORECLR_INITIALIZE_HRESULT' not in native
        (out / 'before-native.log').write_text(native + '\n')
        (out / 'pid-query.txt').write_text(query + '\n')
        server_log = (out / 'server.log').open('wb')
        server = subprocess.Popen([str(adbexe), '-s', args.serial, 'shell', 'run-as', pkg, 'sh'],
                                  stdin=subprocess.PIPE, stdout=server_log, stderr=subprocess.STDOUT)
        server.stdin.write(('echo OWNED_LLDB_SERVER_PID=$$\nexec ' + relative +
                            ' gdbserver 127.0.0.1:54329 --attach ' + str(pid) + '\n').encode())
        server.stdin.close()
        time.sleep(2)
        text = (out / 'server.log').read_text(errors='replace')
        match = re.search(r'OWNED_LLDB_SERVER_PID=([0-9]+)', text)
        assert match and server.poll() is None
        server_pid = int(match[1])
        forward = adb('forward', 'tcp:0', 'tcp:54329')
        assert re.fullmatch('[0-9]+', forward)
        executable = owned('readlink', f'/proc/{pid}/exe')
        assert re.fullmatch('/system/bin/[A-Za-z0-9_.-]+', executable)
        adb('pull', executable, out / 'app_process64')
        assert owned('sha256sum', executable).split()[0] == base.sha(out / 'app_process64')
        result.update(actualExecutablePath=executable, actualExecutableSha256=base.sha(out / 'app_process64'))
        maps = owned('cat', f'/proc/{pid}/maps')
        (out / 'pre-init-maps.log').write_text(maps + '\n')
        zero = [line.split() for line in maps.splitlines() if line.endswith('/libcoreclr.so') and int(line.split()[2], 16) == 0]
        assert len(zero) == 1 and zero[0][-1] == natives[0]
        slide = int(zero[0][0].split('-')[0], 16)
        core = root / 'app/libcoreclr.so'
        assert owned('sha256sum', natives[0]).split()[0] == base.sha(core) == state['appHashes']['libcoreclr.so']
        elf = core.read_bytes()
        phoff = struct.unpack_from('<Q', elf, 32)[0]
        width, count = struct.unpack_from('<HH', elf, 54)
        headers = [struct.unpack_from('<IIQQQQQQ', elf, phoff + i * width) for i in range(count)]
        load_zero = [h for h in headers if h[0] == 1 and h[2] == 0]
        assert len(load_zero) == 1 and load_zero[0][3] == 0
        result.update(coreclrSlide=hex(slide), actualCoreclrPath=natives[0], actualCoreclrSha256=base.sha(core))
        observer = out / 'observer'
        symbols = Path('E:/RuneCLR/artifacts/mobile-budget-batching/android-batch-entry-symbols-20261015-attempt1/raw')
        prep = [sys.executable, '-B', 'E:/RuneCLR/eng/android-batch-boundary-entry-capture.py',
                '--apk', str(root), '--symbols', str(symbols),
                '--inputs', 'E:/RuneCLR/artifacts/mobile-budget-batching/boundary-inputs-20261014-attempt1',
                '--pid', str(pid), '--nonce', nonce, '--package', pkg, '--output', str(observer)]
        with (out / 'prepare.log').open('wb') as stream:
            done = subprocess.run(prep, stdout=stream, stderr=subprocess.STDOUT, timeout=30)
        assert done.returncode == 0
        commands = ['platform select host', 'target create --arch x86_64-pc-linux-android ' + core.as_posix(),
            'target symbols add ' + (symbols / 'libcoreclr.so.dbg').as_posix(),
            'target modules add ' + (root / 'app/libclrinterpreter.so').as_posix(),
            'target symbols add ' + (symbols / 'libclrinterpreter.so.dbg').as_posix(),
            'gdb-remote 127.0.0.1:' + forward,
            'target modules load --file ' + core.as_posix() + ' --slide ' + hex(slide),
            'script e=lldb.SBError(); p=lldb.debugger.GetSelectedTarget().GetProcess(); data=p.ReadMemory(' + str(slide) + ',16,e); print("CORECLR_MEMORY_PREFIX="+data.hex()); assert p.GetProcessID()==' + str(pid) + ' and e.Success() and data==bytes.fromhex("' + elf[:16].hex() + '")',
            'process handle SIGBUS -s false -p true -n false', 'process handle SIGSEGV -s false -p true -n false',
            'command source ' + (observer / 'capture.lldb').as_posix()]
        script = out / 'capture.lldb'
        script.write_text('\n'.join(commands) + '\n')
        debug_log = (out / 'lldb.log').open('wb')
        debugger = subprocess.Popen([str(ndk / 'bin/lldb.cmd'), '--batch', '--source', str(script)],
                                    stdout=debug_log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            text = (out / 'lldb.log').read_text(errors='replace')
            if 'ANDROID_ENTRY_READY pid=' + str(pid) + ' runId=' + nonce in text:
                break
            if debugger.poll() is not None:
                raise RuntimeError('Observer exited before ready: ' + text[-4000:])
            time.sleep(.2)
        else:
            raise RuntimeError('Observer ready timeout')
        result['debuggerTransportPassed'] = True
        owned('touch', 'files/batch-' + nonce + '.entry-release')
        debugger.wait(timeout=args.timeout)
        debug_log.close()
        result['lldbExit'] = debugger.returncode
        assert debugger.returncode == 0
        app.wait(timeout=args.timeout)
        app_log.close()
        result['instrumentationExit'] = app.returncode
        assert app.returncode == 0
        for suffix in ('native.log', 'managed.log', 'managed-result.json', 'maps.log', 'boundary.json'):
            raw = subprocess.run([str(adbexe), '-s', args.serial, 'exec-out', 'run-as', pkg,
                                  'cat', 'files/batch-' + nonce + '.' + suffix], capture_output=True, timeout=60)
            (out / suffix).write_bytes(raw.stdout)
            (out / (suffix + '.pull-stderr.log')).write_bytes(raw.stderr)
            assert raw.returncode == 0
        managed, receipt = base.load(out / 'managed-result.json'), base.load(out / 'boundary.json')
        assert managed['appPid'] == pid and managed['nonce'] == nonce and managed['matrix'] == '100' and managed['interval'] == '64' and managed['exitCode'] == 0
        assert all(managed[k] == 1 for k in ('policy', 'meter', 'terminal', 'gc')) and managed['defaultPolicy'] == 0
        native = (out / 'native.log').read_text()
        assert header in native and gate + ' state=released' in native
        for marker in ('CORECLR_INITIALIZE_HRESULT=0x0', 'CORECLR_EXECUTE_HRESULT=0x0;RUNECLR_EXIT=0', 'CORECLR_SHUTDOWN_HRESULT=0x0'):
            assert len(re.findall(r'(?m)^' + re.escape(marker) + r'$', native)) == 1
        instrumentation = (out / 'instrumentation.log').read_text()
        assert re.findall(r'^INSTRUMENTATION_RESULT: return-code=([0-9-]+)\r?$', instrumentation, re.M) == ['0']
        assert re.findall(r'^INSTRUMENTATION_CODE: ([0-9-]+)\r?$', instrumentation, re.M) == ['0']
        marker = f"BATCH_BOUNDARY_COMPLETE nonce={nonce} pid={pid} N=100 rows={len(receipt['rows'])}"
        assert (out / 'managed.log').read_text().count(marker) == 1 and native.count(marker) == 1
        maps = (out / 'maps.log').read_text()
        for name in ('libcoreclr.so', 'libclrinterpreter.so', 'libclrjit.so'):
            actual = set(re.findall(r'(?m)(/[^\s]+/' + re.escape(name) + r')$', maps))
            assert actual == {native_dir + '/' + name}
        review = helper('assess-mobile-batch-boundary')
        assert base.sha(Path(review.__file__)) == base.REVIEW_SHA
        rows = review.review_lane(receipt, 100, 100, 'Android.x64', state['authorHashes']['author/BatchBoundary.Author.dll'], pid, nonce)
        after = base.inventory(args, state, out, 'installed-after', native_dir)
        assert before == after
        assert not (observer / 'capture-errors.json').exists()
        entries, config = base.load(observer / 'interpreter-entries.json'), base.load(observer / 'capture-config.json')
        assert len(entries) == 4 and {e['relativePath'] + ':' + e['metadataMethodName'] for e in entries} == set(config['requiredMethods'])
        assert base.load(observer / 'observation-disabled.json')['allObservationBreakpointsDisabled']
        debug = base.load(observer / 'debugger-result.json')
        assert debug['exited'] and debug['errors'] == 0 and debug['pid'] == pid and debug['runId'] == nonce
        result.update(passed=True, rows=len(rows), contexts=sum(r['Collected'] is True for r in rows),
                      installedUnchanged=True, installedEntries=len(before), entryGroups=4,
                      resumedFunctionalCompletion=True, initializeExecuteShutdownZero=True,
                      actualDebuggerExitStatus=debug['exitStatus'], observationDisabledAfterCoverage=True,
                      executionVerified=True, liveBatchPathVerified=False, performanceMeasured=False)
    except Exception:
        result['error'] = traceback.format_exc()
    finally:
        if debugger is not None and debugger.poll() is None:
            debugger.kill()
            debugger.wait(timeout=10)
        if forward:
            adb('forward', '--remove', 'tcp:' + forward, check=False)
        if app is not None and app.poll() is None:
            adb('shell', 'am', 'force-stop', pkg, check=False)
            try:
                app.wait(timeout=10)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait(timeout=10)
        if server is not None:
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if server_pid:
                    owned('kill', str(server_pid), check=False)
                server.kill()
                server.wait(timeout=5)
        owned('rm', '-f', relative, check=False)
        adb('shell', 'rm', '-f', staging, check=False)
        for stream in (app_log, server_log, debug_log):
            if stream is not None and not stream.closed:
                stream.close()
        base.write(out / 'commands.json', records)
        result['rawHashes'] = base.files(out)
        base.write(out / 'results.json', result)
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--android-root', type=Path, default=Path('D:/RuneCLR-Android'))
    p.add_argument('--serial', default='emulator-5556')
    p.add_argument('--timeout', type=int, default=600)
    return transport(p.parse_args())

if __name__ == '__main__':
    raise SystemExit(main())
