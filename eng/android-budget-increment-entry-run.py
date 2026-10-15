#!/usr/bin/env python3
"""Bounded opt-in Android budget debugger transport on an owned emulator."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time
import traceback
import uuid


PARENT_OPERATOR_SHA256 = 'ff9e577ad03f74116c72b2132c85288ec0f64326d1251ae6f446190a1a10a8ee'
PINS = {'android-budget-increment-apk.py':'0bbdd66b80cec5115635a690cd2099df9ed14e1869bd5d518019c540d584c73e','android-budget-increment-entry-install.py':'ca78f2190cf701e7b18a3b03ff6b6555ef0e5efadc163dc57e3eb1864fc300e9','android-budget-increment-entry-capture.py':'727b5d374d2eafcb90a58e4455393331fbf3b94ee1e4d04321728a4228984b34'}
def helper(name):
    target='android-budget-increment-apk' if name=='android-session-budget-apk' else name
    path=Path(__file__).with_name(target+'.py')
    assert hashlib.sha256(path.read_bytes()).hexdigest()==PINS[path.name]
    spec=importlib.util.spec_from_file_location(target.replace('-','_'),path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if name=='android-session-budget-apk':
        base=module.base;common=helper('android-budget-increment-entry-install')
        base.inventory=lambda args,state,out,name,native_dir:common.inventory(base,args,state,out,name,native_dir)
        return base
    return module

def transport(args):
    base = helper('android-session-budget-apk')
    base.device(args)
    root = args.output.resolve()
    state = base.load(root / 'state.json')
    import sys
    helper('android-budget-increment-apk').validate_state(root)
    assert state['runtimeTree']=='91673a7980bda79006259e525741fecb04324444' and base.load(root/'entry-build.json')['onlyJniOptInGateDelta']
    assert state['installed'] and base.sha(state['apk']) == state['apkSha256']
    assert re.fullmatch(r'net.dot.RuneCLR_Budget_[0-9a-f]{12}', state['package'])
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
    app_log = server_log = None
    staging = '/data/local/tmp/runeclr-budget-lldb-' + nonce
    relative = 'files/runeclr-budget-lldb-' + nonce
    result = {'passed': False, 'nativeEntryProof': False, 'debugger': True, 'nonce': nonce,
              'package': pkg, 'serial': args.serial, 'driverSha256': base.sha(__file__),
              'scope': 'Current budget nine-group method capture; independent inspection required; completeInvocationCapture=false'}

    def adb(*argv, check=True):
        command = [str(adbexe), '-s', args.serial, *map(str, argv)]
        done = subprocess.run(command, capture_output=True, timeout=60)
        records.append({'command': command, 'exit': done.returncode,
                        'stdout': done.stdout.decode(errors='replace'), 'stderr': done.stderr.decode(errors='replace')})
        if check and done.returncode:
            raise RuntimeError('Owned adb command failed: ' + repr(command))
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
        before = base.inventory(args, state, out, 'installed-before', natives[0].rsplit('/', 1)[0])
        result['lldbServerSha256'] = base.sha(server_file)
        assert result['lldbServerSha256'] == '873ecfdf9fe588ace2a64122ac7f4b77b8c18bf684eb608653e0b127c9b651c7'
        adb('push', server_file, staging)
        owned('cp', staging, relative)
        owned('chmod', '700', relative)
        assert owned('sha256sum', relative).split()[0] == base.sha(server_file)
        adb('shell', 'am', 'force-stop', pkg)
        command = [str(adbexe), '-s', args.serial, 'shell', 'am', 'instrument', '-w',
                   '-e', 'env:RUNECLR_BUDGET_NONCE', nonce, '-e', 'env:RUNECLR_BUDGET_SCENARIO', 'all',
                   '-e', 'env:RUNECLR_BUDGET_NATIVE_ENTRY_WAIT', '1', pkg + '/net.dot.MonoRunner']
        base.write(out / 'request.json', {'command': command, 'nonce': nonce, 'apkSha256': state['apkSha256'],
                                         'sourceTree': state['runtimeTree'], 'startedUtc': base.utc()})
        app_log = (out / 'instrumentation.log').open('wb')
        app = subprocess.Popen(command, stdout=app_log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            query = owned('cat', 'files/budget-' + nonce + '.pid-query.txt', check=False)
            native = owned('cat', 'files/budget-' + nonce + '.native.log', check=False)
            match = re.fullmatch(r'android.os.Process.myPid=([0-9]+)', query)
            if match and 'state=waiting' in native:
                break
            if app.poll() is not None:
                raise RuntimeError('App exited before owned gate')
            time.sleep(0.3)
        else:
            raise RuntimeError('Owned gate absent within 45 seconds')
        pid = int(match[1])
        result['appPid'] = pid
        header = f'MOBILE_BUDGET_NATIVE pid={pid} nonce={nonce} InterpMode=0 RuneCLRInterpretCollectible=0 ReadyToRun=1'
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
        phoff, entsize, count = struct.unpack_from('<Q', elf, 32)[0], struct.unpack_from('<H', elf, 54)[0], struct.unpack_from('<H', elf, 56)[0]
        headers = [struct.unpack_from('<IIQQQQQQ', elf, phoff + i * entsize) for i in range(count)]
        load_zero = [h for h in headers if h[0] == 1 and h[2] == 0]
        assert len(load_zero) == 1 and load_zero[0][3] == 0
        result.update(coreclrSlide=hex(slide), actualCoreclrPath=natives[0], actualCoreclrSha256=base.sha(core))
        expected = elf[:16].hex()
        observer=out/'observer'
        symbols=Path('E:/RuneCLR/artifacts/mobile-budget-increment/android-entry-symbols-20261014-attempt1/raw')
        import sys
        prep=[sys.executable,'-B','E:/RuneCLR/eng/android-budget-increment-entry-capture.py','--apk',str(root),'--symbols',str(symbols),'--metadata','E:/RuneCLR/artifacts/mobile-session-budget/author-entry-metadata-20261013/methods.json','--pid',str(pid),'--nonce',nonce,'--package',pkg,'--output',str(observer)]
        with (out/'prepare.log').open('wb') as stream:
            done=subprocess.run(prep,stdout=stream,stderr=subprocess.STDOUT,timeout=30)
        assert done.returncode==0
        commands=['platform select host','target create --arch x86_64-pc-linux-android '+core.as_posix(),
            'target symbols add '+(symbols/'libcoreclr.so.dbg').as_posix(),
            'target modules add '+(root/'app/libclrinterpreter.so').as_posix(),
            'target symbols add '+(symbols/'libclrinterpreter.so.dbg').as_posix(),
            'gdb-remote 127.0.0.1:'+forward,
            'target modules load --file '+core.as_posix()+' --slide '+hex(slide),
            'script e=lldb.SBError(); p=lldb.debugger.GetSelectedTarget().GetProcess(); data=p.ReadMemory('+str(slide)+',16,e); print("CORECLR_MEMORY_PREFIX="+data.hex()); assert p.GetProcessID()=='+str(pid)+' and e.Success() and data==bytes.fromhex("'+expected+'")',
            'process handle SIGBUS -s false -p true -n false','process handle SIGSEGV -s false -p true -n false',
            'command source '+(observer/'capture.lldb').as_posix()]
        script=out/'capture.lldb';script.write_text(chr(10).join(commands)+chr(10))
        debug_log=(out/'lldb.log').open('wb')
        debugger=subprocess.Popen([str(ndk/'bin/lldb.cmd'),'--batch','--source',str(script)],stdout=debug_log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            text=(out/'lldb.log').read_text(errors='replace')
            if 'ANDROID_ENTRY_READY pid='+str(pid)+' runId='+nonce in text:break
            if debugger.poll() is not None:raise RuntimeError('Observer exited before ready: '+text[-4000:])
            time.sleep(.2)
        else:raise RuntimeError('Observer ready timeout')
        result['debuggerTransportPassed']=True
        owned('touch','files/budget-'+nonce+'.entry-release')
        debugger.wait(timeout=args.timeout);debug_log.close();result['lldbExit']=debugger.returncode
        assert debugger.returncode==0
        app.wait(timeout=args.timeout)
        app_log.close()
        result['instrumentationExit'] = app.returncode
        assert app.returncode == 0
        for suffix in ('native.log', 'jit.log', 'managed.log', 'managed-result.json', 'maps.log'):
            raw = subprocess.run([str(adbexe), '-s', args.serial, 'exec-out', 'run-as', pkg,
                                  'cat', 'files/budget-' + nonce + '.' + suffix], capture_output=True, timeout=60)
            assert raw.returncode == 0
            (out / suffix).write_bytes(raw.stdout)
        raw=subprocess.run([str(adbexe),'-s',args.serial,'exec-out','run-as',pkg,'tar','-cf','-','-C','files/budget-evidence-'+nonce,'.'],capture_output=True,timeout=60)
        assert raw.returncode==0
        (out/'adapter-evidence.tar').write_bytes(raw.stdout)
        import tarfile
        with tarfile.open(out/'adapter-evidence.tar') as archive:
            assert all(not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in archive.getmembers())
            archive.extractall(out/'adapter-evidence',filter='data')
        evidence = owned('cat', 'files/budget-evidence-' + nonce + '/result.json')
        (out / 'adapter-result.json').write_text(evidence + '\n')
        adapter, managed = json.loads(evidence), base.load(out / 'managed-result.json')
        assert adapter['passed'] and adapter['processId'] == pid and adapter['nonce'] == nonce
        assert len(adapter['cases']) == 15 and adapter['contexts'] == 73
        assert managed['appPid'] == pid and managed['nonce'] == nonce and managed['exitCode'] == 0
        assert all(managed[k] == 1 for k in ('policy', 'meter', 'terminal', 'gc')) and managed['defaultPolicy'] == 0
        text = (out / 'native.log').read_text()
        assert header in text and gate + ' state=released' in text
        assert 'CORECLR_INITIALIZE_HRESULT=0x0' in text and 'CORECLR_EXECUTE_HRESULT=0x0;RUNECLR_EXIT=0' in text
        instrumentation = (out / 'instrumentation.log').read_text()
        assert re.findall(r'^INSTRUMENTATION_RESULT: return-code=([0-9-]+)\r?$', instrumentation, re.M) == ['0']
        after = base.inventory(args, state, out, 'installed-after', natives[0].rsplit('/', 1)[0])
        assert before == after
        assert (observer/'interpreter-entries.json').is_file()
        result.update(passed=True, cases=15, contexts=73, installedUnchanged=True,
                      installedEntries=len(before), resumedFunctionalCompletion=True)
    except Exception:
        result['error'] = traceback.format_exc()
    finally:
        if debugger is not None and debugger.poll() is None:
            debugger.kill(); debugger.wait(timeout=10)
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
        for stream in (app_log, server_log):
            if stream is not None and not stream.closed:
                stream.close()
        base.write(out / 'commands.json', records)
        result['rawHashes'] = base.files(out)
        base.write(out / 'results.json', result)
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=('capture','normal','cleanup'));p.add_argument('--output',type=Path,required=True);p.add_argument('--android-root',type=Path,default=Path('D:/RuneCLR-Android'));p.add_argument('--serial',default='emulator-5556');p.add_argument('--timeout',type=int,default=600);p.add_argument('--shutdown',action='store_true');a=p.parse_args()
    if a.phase=='capture':return transport(a)
    base=helper('android-session-budget-apk');helper('android-budget-increment-apk').validate_state(a.output)
    if a.phase=='normal':a.scenario='all';base.run(a)
    else:base.cleanup(a)
    return 0

if __name__=='__main__':raise SystemExit(main())
