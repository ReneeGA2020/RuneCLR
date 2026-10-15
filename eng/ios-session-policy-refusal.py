#!/usr/bin/env python3
"""Run one isolated Release iOS session-policy refusal/recovery experiment."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tarfile
import uuid

COMMIT = '1724cdec553a7aff7a373a271a4be612651c7625'
REFUSE = 'SelectionUGC.Refusal.Entry:Reject'
MARKER = 'RuneCLRInterpreterRefusal: ' + REFUSE + ' CORJIT_SKIPPED'
FILES = ('SelectionProbe.Payload.dll', 'SelectionProbe.Private.dll', 'Refusal/SelectionProbe.Refusal.dll')


def helper(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(test, message):
    if not test:
        raise RuntimeError(message)


def load(out):
    return json.loads((out / 'state.json').read_text())


def unchanged(state, mobile):
    return (mobile.tree(Path(state['originalApp'])) == state['bundleHashes']
            and mobile.tree(Path(state['app'])) == state['bundleHashes']
            and ('installedApp' not in state or mobile.tree(Path(state['installedApp'])) == state['bundleHashes']))


def prepare(args, common, mobile):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'logs').mkdir()
    (out / 'provenance').mkdir()
    old = json.loads((args.player / 'state.json').read_text())
    build = json.loads((args.build / 'results.json').read_text())
    require(build['success'] and build['commit'] == COMMIT and build['configuration'] == 'Release'
            and build['target'] == 'iossimulator.arm64', 'Matching Release simulator build required')
    require(old['matchingBuildReceiptSha256'] == sha(args.build / 'results.json'), 'Player build identity differs')
    require(mobile.tree(Path(old['app'])) == old['bundleHashes'], 'Original player bytes differ')
    runtime = args.build / 'runtime'
    require(common.capture(['git', '-C', runtime, 'rev-parse', 'HEAD']) == COMMIT
            and not common.capture(['git', '-C', runtime, 'status', '--porcelain', '--untracked-files=no']),
            'Matching tracked-clean runtime source required')
    config = runtime / 'src/coreclr/interpreter/interpconfigvalues.h'
    code = runtime / 'src/coreclr/interpreter/eeinterp.cpp'
    require('RELEASE_CONFIG_METHODSET(RuneCLRInterpreterRefuseMethods' in config.read_text(), 'No retail refusal config')
    require('return CORJIT_SKIPPED;' in code.read_text() and 'SelectionUGC.Refusal' in code.read_text(), 'No actual refusal owner')
    source_native = Path(build['native'])
    app_native = Path(old['app']) / 'libcoreclr.dylib'
    require(sha(source_native) == build['nativeSha256'], 'Source native changed')
    require(mobile.macho_sections(source_native) == mobile.macho_sections(app_native), 'Signed app native section mismatch')
    require(MARKER.encode() in app_native.read_bytes(), 'Actual signed Release native has no refusal marker')
    for name in ('SelectionProbe.Host.dll', 'SelectionProbe.Contract.dll', 'SessionBridge.dll', 'RuneCLR.Runtime.dll'):
        require(mobile.il_layout(Path(old['app']) / name)['managedNativeRva'] > 0, 'Trusted component must be R2R: ' + name)
    fixture_hashes = {}
    layouts = {}
    for name in FILES:
        path = args.fixtures / name
        require(path.is_file(), 'Missing fixture: ' + name)
        layout = mobile.il_layout(path)
        require(layout['ilOnly'] and layout['managedNativeRva'] == layout['managedNativeSize'] == 0, 'Fixture must be IL')
        fixture_hashes[name] = sha(path)
        layouts[name] = layout
    shutil.copytree(Path(old['app']), out / 'app/Session.app')
    for source, name in [(args.player / 'state.json', 'original-player-state.json'),
                         (args.build / 'results.json', 'matching-build.json'),
                         (args.player / 'runtime.m', 'runtime.m'), (args.player / 'SessionBridge.cs', 'SessionBridge.cs'),
                         (config, 'interpconfigvalues.h'), (code, 'eeinterp.cpp')]:
        shutil.copy2(source, out / 'provenance' / name)
    shutil.copy2(Path(__file__), out / 'driver.py')
    state = {'schema': 'runeclr.ios.session-policy.refusal.v1', 'createdUtc': utc(), 'runId': uuid.uuid4().hex,
             'originalPlayer': str(args.player), 'originalApp': old['app'], 'app': str(out / 'app/Session.app'),
             'bundleId': old['bundleId'], 'bundleHashes': old['bundleHashes'], 'matchingBuild': build,
             'matchingBuildReceiptSha256': sha(args.build / 'results.json'), 'driverSha256': sha(Path(__file__)),
             'currentHostInputs': old['currentHostInputs'], 'fixtureSource': str(args.fixtures),
             'fixtureHashes': fixture_hashes, 'fixtureLayouts': layouts,
             'scope': 'Existing fixture bytes transferred after new installation; no new compilation claim',
             'preparationOnly': True}
    write(out / 'state.json', state)
    require(unchanged(state, mobile), 'Fresh player copy changed bytes')
    print('PREPARED ' + str(out), flush=True)


def install(args, common, mobile):
    out, state = args.output, load(args.output)
    require('simulator' not in state and unchanged(state, mobile), 'Preserve prior installation/changed app')
    sim = common.capture(['xcrun', 'simctl', 'create', 'RuneCLR-Session-Refusal-' + state['runId'][:8],
                          args.device_type, args.sim_runtime])
    state['simulator'] = sim
    write(out / 'state.json', state)
    common.logged(['xcrun', 'simctl', 'boot', sim], out / 'logs/boot-command.log')
    common.logged(['xcrun', 'simctl', 'bootstatus', sim, '-b'], out / 'logs/boot.log')
    common.logged(['xcrun', 'simctl', 'install', sim, state['app']], out / 'logs/install.log')
    state['installedApp'] = common.capture(['xcrun', 'simctl', 'get_app_container', sim, state['bundleId'], 'app'])
    state['dataContainer'] = common.capture(['xcrun', 'simctl', 'get_app_container', sim, state['bundleId'], 'data'])
    state['installedUtc'] = utc()
    write(out / 'state.json', state)
    require(unchanged(state, mobile), 'Installed bundle bytes differ')
    source = Path(state['fixtureSource'])
    inputs = out / 'postinstall-fixture-inputs'
    inputs.mkdir()
    destination = Path(state['dataContainer']) / 'Documents/refusal-plugin'
    destination.mkdir(parents=True, exist_ok=False)
    for name, expected in state['fixtureHashes'].items():
        require(sha(source / name) == expected, 'Original fixture changed')
        for root in (inputs, destination):
            (root / name).parent.mkdir(exist_ok=True, parents=True)
            shutil.copy2(source / name, root / name)
    state['fixtureDirectory'] = str(destination)
    state['evidenceDirectory'] = str(Path(state['dataContainer']) / 'Documents/refusal-evidence')
    state['transferredUtc'] = utc()
    write(out / 'state.json', state)
    require(mobile.tree(destination) == state['fixtureHashes'], 'Transferred fixture bytes differ')
    print('INSTALL/POSTINSTALL TRANSFER PASS ' + sim, flush=True)


def assess(messages):
    text = '\n'.join(messages)
    sessions = re.findall(r'^PASS session=([0-9]+) values=.* collected=true$', text, re.M)
    queries = re.findall(r'^POLICY context=.* phase=(\S+) value=([01]) collectible=true$', text, re.M)
    phases = Counter(phase for phase, _ in queries)
    retired = len(re.findall(r'^RETIRED query=System.InvalidOperationException protected=true$', text, re.M))
    return {'functionalComplete': (sorted(map(int, sessions)) == list(range(1, 21))
                and '20/20 execution-selection sessions passed; 20/20 contexts collected' in messages),
            'refusalComplete': messages.count('PASS required-refusal exception=System.NotSupportedException collected=true') == 1,
            'nativeAcknowledgement': 'POLICY API version=1 factory=required default=0 immutable-api=true' in messages,
            'requiredQueries': len(queries), 'policyPhases': dict(phases), 'retiredQueryGuards': retired,
            'allQueriesRequired': bool(queries) and all(value == '1' for _, value in queries),
            'policyCountsComplete': phases['before-load'] == phases['before-unload'] == 21
                and phases['before-explicit-load'] == phases['after-explicit-load'] == 41
                and phases['before-run'] == phases['after-run'] == 20
                and phases['resolver-after-private'] == 20 and phases['resolver-before'] >= 41 and retired == 21}


def run(args, common, mobile, accept):
    out, state = args.output, load(args.output)
    require(unchanged(state, mobile), 'Player changed before run')
    evidence = out / 'run-refusal'
    evidence.mkdir(exist_ok=False)
    env = {k:v for k,v in os.environ.items() if not k.startswith(('SIMCTL_CHILD_DOTNET_', 'SIMCTL_CHILD_COMPlus_', 'SIMCTL_CHILD_RUNECLR_'))}
    controls = {'RUNECLR_SESSION_PHASE':'selection', 'RUNECLR_PROBE_LANE':'refusal', 'RUNECLR_PROBE_FACTORY':'required',
                'RUNECLR_PROBE_DIRECTORY':state['fixtureDirectory'], 'RUNECLR_PROBE_EVIDENCE':state['evidenceDirectory'],
                'RUNECLR_REFUSAL_RUN_ID':state['runId'], 'DOTNET_RuneCLRInterpreterRefuseMethods':REFUSE}
    env.update({'SIMCTL_CHILD_' + k:v for k,v in controls.items()})
    write(evidence / 'request.json', {'startedUtc':utc(), 'runId':state['runId'], 'simulator':state['simulator'],
          'candidateCommit':COMMIT, 'environment':controls, 'settings':{'interpMode':0,'globalCollectibleDiagnostic':0},
          'fixtureDirectory':state['fixtureDirectory'], 'fixtureHashes':state['fixtureHashes'],
          'currentHostInputs':state['currentHostInputs'], 'matchingBuildReceiptSha256':state['matchingBuildReceiptSha256']})
    result = {'passed':False, 'appRerun':False, 'runId':state['runId'], 'methodNativeEntryProof':'not collected'}
    pid = None
    try:
        common.logged(['xcrun','simctl','launch','--wait-for-debugger','--stdout=' + str(evidence / 'managed.stdout.log'),
                       '--stderr=' + str(evidence / 'managed.stderr.log'),state['simulator'],state['bundleId']], evidence / 'launch.log', env=env)
        pid = int(re.search(r': ([0-9]+)', (evidence / 'launch.log').read_text()).group(1))
        query = ['xcrun','simctl','spawn',state['simulator'],'log','stream','--style','json','--predicate','processIdentifier == ' + str(pid)]
        write(evidence / 'unified-query.json', {'command':query,'appPid':pid,'startUtc':utc(),'runId':state['runId']})
        with (evidence / 'managed.unified.log').open('w') as output, (evidence / 'unified.stderr.log').open('w') as errors:
            stream = subprocess.Popen(query,stdout=output,stderr=errors,start_new_session=True)
            try:
                script = evidence / 'run.lldb'
                script.write_text('breakpoint set -n coreclr_initialize\ncontinue\nimage list -o -f\n'
                    'expr -- (char*)getenv("DOTNET_RuneCLRInterpreterRefuseMethods")\n'
                    'expr -- (char*)getenv("RUNECLR_PROBE_DIRECTORY")\n'
                    'expr -- (char*)getenv("RUNECLR_REFUSAL_RUN_ID")\n'
                    'breakpoint delete 1\ncontinue\nprocess status\nquit\n')
                status = common.logged(['xcrun','lldb','--batch','--attach-pid',str(pid),'--source',script],
                                       evidence / 'lldb.log',timeout=args.timeout,check=False)
            finally:
                if stream.poll() is None: stream.send_signal(signal.SIGINT)
                try: stream.wait(timeout=15)
                except subprocess.TimeoutExpired: stream.kill();stream.wait(timeout=15)
                write(evidence / 'unified-completed.json', {'endUtc':utc(),'streamExit':stream.returncode})
        parsed = accept.events(evidence / 'managed.unified.log',pid)
        messages = [x.get('eventMessage','') for x in parsed]
        write(evidence / 'managed-messages.json',messages)
        result.update(assess(messages))
        stdout = (evidence / 'managed.stdout.log').read_text(errors='replace')
        stderr = (evidence / 'managed.stderr.log').read_text(errors='replace')
        lldb = (evidence / 'lldb.log').read_text(errors='replace')
        raw = stdout + stderr + '\n'.join(messages)
        refusal = stdout.count(MARKER)
        if not refusal: refusal = stderr.count(MARKER)
        if not refusal: refusal = messages.count(MARKER)
        result.update({'appPid':pid,'unifiedEvents':len(parsed),'lldbExit':status,
            'actualNativeRefusalCount':refusal,'normalNativeExit':bool(re.search(r'exited with status = 0',lldb)),
            'nativeManagedExitZero':'CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0' in stdout,
            'mode0Diagnostic0':'SESSION_NATIVE_CONFIG InterpMode=0 RuneCLRInterpretCollectible=0' in stdout,
            'initializationRuntimePathBound':str(Path(state['installedApp']) / 'libcoreclr.dylib') in lldb,
            'actualEnvironmentBound':all(x in lldb for x in (REFUSE,state['fixtureDirectory'],state['runId'])),
            'bundleUnchanged':unchanged(state,mobile), 'payloadUnchanged':mobile.tree(Path(state['fixtureDirectory'])) == state['fixtureHashes'],
            'noCrashOrAssertion':not any(x in raw + lldb for x in ('Got a SIGSEGV','Assert failure','Assertion failed')),
            'completedUtc':utc(), 'scope':'Release scoped compiler refusal and subsequent functional recovery; no JIT exists on this iOS lane'})
        result['passed'] = all(result[k] for k in ('functionalComplete','refusalComplete','nativeAcknowledgement',
            'allQueriesRequired','policyCountsComplete','normalNativeExit','nativeManagedExitZero','mode0Diagnostic0',
            'initializationRuntimePathBound','actualEnvironmentBound','bundleUnchanged','payloadUnchanged','noCrashOrAssertion')) and status == 0 and refusal == 1
        if Path(state['evidenceDirectory']).is_dir():
            shutil.copytree(Path(state['evidenceDirectory']),evidence / 'probe-evidence')
    except Exception as error:
        result['driverError'] = repr(error)
    finally:
        common.logged(['xcrun','simctl','terminate',state['simulator'],state['bundleId']],evidence / 'terminate.log',check=False)
        result['rawHashes'] = mobile.tree(evidence)
        write(evidence / 'results.json',result)
    print(json.dumps(result,indent=2),flush=True)
    require(result['passed'], 'Refusal acceptance failed; retain this run')


def cleanup(args, common):
    state = load(args.output)
    require(not (args.output / 'cleanup.json').exists(), 'Preserve original cleanup')
    status = common.logged(['xcrun','simctl','shutdown',state['simulator']],args.output / 'logs/shutdown.log',check=False)
    devices = json.loads(common.capture(['xcrun','simctl','list','devices','--json']))
    actual = [d for ds in devices['devices'].values() for d in ds if d['udid'] == state['simulator']]
    write(args.output / 'cleanup.json',{'simulator':state['simulator'],'shutdownExit':status,'completedUtc':utc(),
          'confirmedShutdown':len(actual) == 1 and actual[0]['state'] == 'Shutdown'})
    require(status == 0 and len(actual) == 1 and actual[0]['state'] == 'Shutdown','Owned simulator shutdown not confirmed')


def archive(args, mobile):
    out = args.output
    target = out / 'evidence.tar.gz'
    require(not target.exists(), 'Preserve prior archive')
    roots = [out / n for n in ('logs','provenance','postinstall-fixture-inputs','run-refusal')]
    files = [out / n for n in ('state.json','driver.py','cleanup.json')]
    files += [p for root in roots for p in root.rglob('*') if p.is_file()]
    manifest = {str(p.relative_to(out)):sha(p) for p in sorted(files)}
    write(out / 'archive-manifest.json',{'files':manifest,'appExcluded':True,'appBundleHashes':load(out)['bundleHashes']})
    with tarfile.open(target,'w:gz') as package:
        for p in files + [out / 'archive-manifest.json']:
            package.add(p,arcname=str(p.relative_to(out)))
    receipt = {'archive':str(target),'sha256':sha(target),'bytes':target.stat().st_size,'members':len(files)+1}
    write(out / 'archive-receipt.json',receipt)
    print(json.dumps(receipt),flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('prepare','install','run','cleanup','archive'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--player',type=Path)
    parser.add_argument('--build',type=Path)
    parser.add_argument('--fixtures',type=Path)
    parser.add_argument('--device-type',default='com.apple.CoreSimulator.SimDeviceType.iPhone-17')
    parser.add_argument('--sim-runtime',default='com.apple.CoreSimulator.SimRuntime.iOS-27-0')
    parser.add_argument('--timeout',type=int,default=300)
    args = parser.parse_args()
    if args.phase == 'prepare' and any(getattr(args,k) is None for k in ('player','build','fixtures')):
        parser.error('prepare requires --player --build --fixtures')
    common,mobile = helper('ios-r2r-fix-verify'),helper('verify-ios-packages')
    if args.phase == 'prepare': prepare(args,common,mobile)
    elif args.phase == 'install': install(args,common,mobile)
    elif args.phase == 'run': run(args,common,mobile,helper('ios-session-policy-accept'))
    elif args.phase == 'cleanup': cleanup(args,common)
    else: archive(args,mobile)


if __name__ == '__main__': main()
