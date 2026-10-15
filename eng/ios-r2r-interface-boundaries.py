#!/usr/bin/env python3
"""Test covariant CID and interpreted constrained value calls on clean Debug iOS."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
COMMIT = '8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d'
NATIVE = 'e97efd27370d02b6767bbaa1e4cb968f92fa3341d53e345626ff6f8498f572d8'

SOURCES = {
    'ProbeContract': '''namespace Boundary;
public interface IProducer<out T> { T Produce(); }
public interface IValueStep { int Next(); }
public interface IConstrainedProbe { int Run(int count); }
''',
    'ProbePlugin': '''using System;
using Boundary;
public struct BoundaryCounter : IValueStep
{
    private int value;
    public int Next() => ++value;
}
public sealed class Plugin : IProducer<string>, IConstrainedProbe
{
    private static int produced, runs;
    public string Produce() => "item=" + ++produced;
    private static int Step<T>(ref T value) where T : struct, IValueStep => value.Next();
    public int Run(int count)
    {
        var value = new BoundaryCounter();
        int invocation = ++runs, sum = 0;
        for (int i = 0; i < count; i++)
        {
            int next = Step(ref value);
            if (next != i + 1) throw new Exception("Constrained ref value mutation failed");
            sum += next;
            Console.WriteLine("CONSTRAINED_STEP index=" + i + " value=" + next);
        }
        Console.WriteLine("CONSTRAINED_RESET=" + invocation + " SUM=" + sum);
        return sum * 100 + invocation;
    }
}
''',
    'ProbeHost': '''using System;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using Boundary;
public static class Driver
{
    private static Assembly contract;
    private sealed class Context : AssemblyLoadContext
    {
        public Context() : base(isCollectible: true) { }
        protected override Assembly Load(AssemblyName name) => name.Name == "ProbeContract" ? contract : null;
    }
    private static void Require(bool value, string message) { if (!value) throw new Exception(message); }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void Variance(IProducer<object> receiver)
    {
        for (int i = 0; i < 3; i++)
        {
            Console.WriteLine("BOUNDARY_BEFORE index=" + i); Console.Out.Flush();
            object value = receiver.Produce();
            Require(value is string text && text == "item=" + (i + 1), "Covariant result or static reset failed");
            Console.WriteLine("BOUNDARY_AFTER index=" + i); Console.Out.Flush();
        }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void Constrained(IConstrainedProbe receiver)
    {
        Console.WriteLine("BOUNDARY_BEFORE index=0"); Console.Out.Flush();
        Require(receiver.Run(3) == 601, "Constrained sum or static reset failed");
        Console.WriteLine("BOUNDARY_AFTER index=0"); Console.Out.Flush();
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static WeakReference Cycle(string kind, int index)
    {
        var context = new Context();
        var assembly = context.LoadFromAssemblyPath(Path.Combine(AppContext.BaseDirectory, "plugin", "ProbePlugin.dll"));
        var type = assembly.GetType("Plugin", throwOnError: true);
        object instance = Activator.CreateInstance(type);
        Console.WriteLine("BOUNDARY_CYCLE=" + index + " LOADED");
        if (kind == "variance")
        {
            Require(instance is IProducer<string> && instance is IProducer<object>, "Covariance conversion failed");
            Console.WriteLine("VARIANCE_CONVERSION_OK");
            Variance((IProducer<object>)instance);
        }
        else if (kind == "constrained")
        {
            var method = type.GetMethod("Step", BindingFlags.NonPublic | BindingFlags.Static);
            Console.WriteLine("CONSTRAINED_IL=" + Convert.ToHexString(method.GetMethodBody().GetILAsByteArray()));
            Constrained((IConstrainedProbe)instance);
        }
        else throw new Exception("Unknown boundary case");
        Console.WriteLine("BOUNDARY_CYCLE=" + index + " RETURNED");
        var weak = new WeakReference(context);
        context.Unload();
        return weak;
    }
    public static int Run()
    {
        string kind = Environment.GetEnvironmentVariable("BOUNDARY_CASE") ?? "variance";
        Console.WriteLine($"BOUNDARY_BEGIN case={kind} runtime={RuntimeInformation.FrameworkDescription} compiled={RuntimeFeature.IsDynamicCodeCompiled}");
        contract = typeof(IProducer<>).Assembly;
        for (int i = 1; i <= 20; i++)
        {
            var weak = Cycle(kind, i);
            for (int attempt = 0; attempt < 20 && weak.IsAlive; attempt++)
            { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }
            Console.WriteLine("BOUNDARY_CYCLE=" + i + " COLLECTED=" + !weak.IsAlive);
            Require(!weak.IsAlive, "Collectible context retained");
        }
        Console.WriteLine("BOUNDARY_PASS case=" + kind + " cycles=20");
        return 0;
    }
}
''',
    'ProbeEntry': 'public static class Program { public static int Main() => Driver.Run(); }\n',
}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n')

def capture(args):
    return subprocess.check_output([str(a) for a in args], text=True).strip()

def logged(args, log, timeout=180, env=None, check=True):
    with Path(log).open('w') as stream:
        try:
            status = subprocess.run([str(a) for a in args], stdout=stream, stderr=subprocess.STDOUT,
                timeout=timeout, env=env).returncode
        except subprocess.TimeoutExpired:
            stream.write('\nBOUNDARY_TIMEOUT\n'); status = 124
    if check and status != 0:
        raise RuntimeError(f'Command exit {status}: {args[0]}; see {log}')
    return status

def helper(name, args=None):
    path = Path(__file__).with_name(name + '.py')
    old = sys.argv
    try:
        sys.argv = [str(path), *(args or [])]
        spec = importlib.util.spec_from_file_location(name.replace('-', '_'), path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module
    finally:
        sys.argv = old

def build(args):
    root, out = args.root.resolve(), args.output.resolve()
    candidate = root / 'ios-r2r-clean-debug-20261012'
    source = candidate / 'runtime'
    native = source / 'artifacts/bin/coreclr/iossimulator.arm64.Debug/libcoreclr.dylib'
    if capture(['git', '-C', source, 'rev-parse', 'HEAD']) != COMMIT or sha(native) != NATIVE:
        raise RuntimeError('Clean Debug candidate identity differs')
    if capture(['git', '-C', source, 'status', '--porcelain', '--untracked-files=no']):
        raise RuntimeError('Candidate tracked source must be clean')
    if (candidate / 'native-completion-build.exit').read_text().strip() != '0':
        raise RuntimeError('Clean native build completion is not verified')
    original = helper('ios-r2r-repro', [str(root), str(out)])
    original.SOURCES = SOURCES
    original.build()
    mobile = helper('verify-ios-packages')
    app = out / 'r2r/Probe.app'; logs = out / 'logs'
    libraries = {'original': app / 'libcoreclr.dylib',
        'trace': root / 'ios-r2r-cache-20261012/obj-trace/dlls/mscoree/coreclr/libcoreclr.dylib',
        'candidate': native}
    shared = {str(p.relative_to(app)): sha(p) for p in app.rglob('*.dll')}
    framework = sha(app / 'framework.dylib'); composite = sha(app / 'probe.dylib')
    wrapper = mobile.macho_sections(app / 'Probe'); apps = {}
    for label, library in libraries.items():
        target = out / 'apps' / label / 'Probe.app'; target.parent.mkdir(parents=True)
        shutil.copytree(app, target); shutil.copy2(library, target / 'libcoreclr.dylib')
        logged(['codesign', '--force', '--sign', '-', target / 'libcoreclr.dylib'], logs / (label + '-native-sign.log'))
        logged(['codesign', '--force', '--sign', '-', target], logs / (label + '-app-sign.log'))
        if (any(sha(target / name) != digest for name, digest in shared.items())
                or sha(target / 'framework.dylib') != framework or sha(target / 'probe.dylib') != composite
                or mobile.macho_sections(target / 'Probe') != wrapper
                or mobile.macho_sections(library) != mobile.macho_sections(target / 'libcoreclr.dylib')):
            raise RuntimeError('Signing or comparison changed shared/native sections')
        apps[label] = {'app': str(target), 'bundle': 'org.runeclr.ios.r2r.probe.r2r',
            'nativeInputSha256': sha(library), 'signedNativeSha256': sha(target / 'libcoreclr.dylib')}
    logged(['nm', '-n', app / 'probe.dylib'], logs / 'native-symbols.log')
    layouts = {'host': mobile.il_layout(app / 'ProbeHost.dll'),
        'plugin': mobile.il_layout(app / 'plugin/ProbePlugin.dll')}
    if not layouts['host']['managedNativeRva'] or layouts['plugin']['managedNativeRva']:
        raise RuntimeError('Expected trusted R2R host and IL-only plugin')
    write(out / 'state.json', {'base': BASE, 'commit': COMMIT, 'native': str(native),
        'candidateConfiguration': 'iossimulator.arm64.Debug', 'candidateSha256': sha(native),
        'sharedManaged': shared, 'frameworkSha256': framework, 'compositeSha256': composite,
        'nativeWrapperSections': wrapper, 'layouts': layouts, 'apps': apps,
        'sourceHashes': {p.name: sha(p) for p in (out / 'source').glob('*.cs')}})
    print('Built independent interface boundaries with matched clean Debug candidate', flush=True)

def parse(log, case, status):
    text = Path(log).read_text(errors='replace')
    caller = 'Variance' if case == 'variance' else 'Constrained'
    callbacks = len(re.findall(r'(?m)^Compiled method: \.Plugin:' + ('Produce' if case == 'variance' else 'Run') + r'\(', text))
    step_dumps = len(re.findall(r'(?m)^Compiled method: \.Plugin:Step.*$', text))
    counter_notices = len(re.findall(r'(?m)^Interpreter compile method BoundaryCounter:Next\(', text))
    il = re.findall(r'CONSTRAINED_IL=([0-9A-F]{12,})', text)
    constrained_il = len(il) == 20 and all(any(data[i:i+2] == b'\xfe\x16'
        and i+6 < len(data) and data[i+6] == 0x6f for i in range(len(data)-6)) for data in map(bytes.fromhex, il))
    expected = 60 if case == 'variance' else 20
    before = len(re.findall(r'BOUNDARY_BEFORE index=\d+', text))
    after = len(re.findall(r'BOUNDARY_AFTER index=\d+', text))
    returned = len(re.findall(r'BOUNDARY_CYCLE=\d+ RETURNED', text))
    collected = len(re.findall(r'BOUNDARY_CYCLE=\d+ COLLECTED=True', text))
    fault = 'Got a SIGSEGV while executing native code.' in text
    initialized = 'CORECLR_INITIALIZE_HRESULT=0x0' in text
    configuration = f'BOUNDARY_BEGIN case={case} runtime=.NET 12.0.0-dev compiled=False' in text
    native_caller = 'Interpreter compile method Driver:' + caller not in text
    passed = (status == 0 and not fault and 'Assert failure' not in text and initialized and configuration
        and native_caller and f'BOUNDARY_PASS case={case} cycles=20' in text
        and 'CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0' in text
        and before == expected and after == expected and returned == 20 and collected == 20 and callbacks == 20)
    if case == 'variance':
        passed = passed and text.count('VARIANCE_CONVERSION_OK') == 20
    else:
        passed = (passed and constrained_il and step_dumps == 20 and counter_notices == 20
            and text.count('CONSTRAINED_RESET=1 SUM=6') == 20
            and all(text.count('CONSTRAINED_STEP index=' + str(i) + ' value=' + str(i+1)) == 20 for i in range(3)))
    return {'passed': passed, 'case': case, 'launcherExit': status, 'nativeFault': fault,
        'initialized': initialized, 'configuration': configuration, 'nativeCaller': native_caller,
        'before': before, 'after': after, 'returned': returned, 'collected': collected,
        'callbackDumps': callbacks, 'stepDumps': step_dumps, 'counterCompilationNotices': counter_notices,
        'constrainedIlConfirmed': constrained_il, 'cacheRecords': text.count('RUNECLR_CID_RESOLVE'),
        'assertion': 'Assert failure' in text, 'logSha256': sha(log)}

def verify(args):
    out = args.output.resolve(); state = json.loads((out / 'state.json').read_text())
    old = json.loads((out / 'results.json').read_text())
    results = {name: parse(out / 'logs' / (name + '.log'), item['case'], item['launcherExit']) for name, item in old.items()}
    checks = {'candidate-native': sha(state['native']) == NATIVE}
    symbols = (out / 'logs/native-symbols.log').read_text()
    checks['native-caller-symbols'] = all('Driver__' + caller in symbols for caller in ['Variance', 'Constrained'])
    mobile = helper('verify-ios-packages')
    for label, item in state['apps'].items():
        app = Path(item['app'])
        checks[label + '-managed'] = all(sha(app / name) == digest for name, digest in state['sharedManaged'].items())
        checks[label + '-composite'] = sha(app / 'probe.dylib') == state['compositeSha256']
        checks[label + '-wrapper'] = mobile.macho_sections(app / 'Probe') == state['nativeWrapperSections']
    for name, item in results.items():
        checks[name] = item['passed'] if name.startswith('candidate-') or item['case'] == 'constrained' else (
            item['initialized'] and item['configuration'] and item['nativeCaller'] and not item['assertion']
            and (item['passed'] or item['nativeFault']) and item['launcherExit'] != 124)
    checks['variance-cid-trace'] = results['trace-variance']['cacheRecords'] > 0
    sim = json.loads((out / 'simulator.json').read_text())
    devices = json.loads(capture(['xcrun','simctl','list','devices','-j']))['devices']
    own = [d for group in devices.values() for d in group if d['udid'] == sim['uuid']]
    checks['simulator-shutdown'] = len(own) == 1 and own[0]['state'] == 'Shutdown'
    success = len(results) == 6 and all(checks.values())
    write(out / 'verified.json', {'success': success, 'checks': checks, 'results': results})
    print(json.dumps({'success': success, 'checks': checks, 'results': results}), flush=True)
    if not success: raise RuntimeError('Boundary verification failed; preserve the results')

def execute(args):
    out = args.output.resolve(); state = json.loads((out / 'state.json').read_text()); logs = out / 'logs'
    sim = capture(['xcrun', 'simctl', 'create', 'RuneCLR-CID-Interface-Boundaries',
        'com.apple.CoreSimulator.SimDeviceType.iPhone-17', 'com.apple.CoreSimulator.SimRuntime.iOS-27-0'])
    write(out / 'simulator.json', {'uuid': sim, 'shutdown': False}); results = {}
    try:
        logged(['xcrun', 'simctl', 'boot', sim], logs / 'boot.log')
        logged(['xcrun', 'simctl', 'bootstatus', sim, '-b'], logs / 'bootstatus.log')
        for label in ['original', 'trace', 'candidate']:
            item = state['apps'][label]
            logged(['xcrun', 'simctl', 'install', sim, item['app']], logs / (label + '-install.log'))
            for case in ['variance', 'constrained']:
                name = label + '-' + case; env = dict(os.environ)
                for key in list(env):
                    if key.startswith(('SIMCTL_CHILD_DOTNET_', 'SIMCTL_CHILD_COMPlus_', 'SIMCTL_CHILD_BOUNDARY_')): del env[key]
                env['SIMCTL_CHILD_BOUNDARY_CASE'] = case
                if label == 'trace': env['SIMCTL_CHILD_DOTNET_RuneCLRDisableCollectibleInterfaceDispatchCache'] = '2'
                log = logs / (name + '.log')
                status = logged(['xcrun', 'simctl', 'launch', '--console', sim, item['bundle']],
                    log, env=env, timeout=120, check=False)
                results[name] = parse(log, case, status); write(out / 'results.json', results)
                print(name + ': ' + json.dumps(results[name]), flush=True)
                logged(['xcrun', 'simctl', 'terminate', sim, item['bundle']], logs / (name + '-terminate.log'), check=False)
    finally:
        status = logged(['xcrun', 'simctl', 'shutdown', sim], logs / 'shutdown.log', check=False)
        write(out / 'simulator.json', {'uuid': sim, 'shutdown': status == 0})
    verify(args)

def archive(args):
    out = args.output.resolve(); artifact = out / 'evidence.tar.gz'
    with tarfile.open(artifact, 'w:gz') as tar:
        for name in ['logs','source','input','state.json','results.json','verified.json','simulator.json',
            'r2r/crossgen.rsp','r2r/runtime.m','r2r/main.m','r2r/logs']:
            path = out / name
            if path.exists(): tar.add(path, arcname=name)
        tar.add(Path(__file__), arcname='driver.py')
        for name in ['ios-r2r-repro','verify-ios-packages']:
            tar.add(Path(__file__).with_name(name + '.py'), arcname='tools/' + name + '.py')
    print(json.dumps({'archive':str(artifact),'bytes':artifact.stat().st_size,'sha256':sha(artifact)}), flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['build','run','verify','archive'])
    parser.add_argument('--root', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    {'build':build,'run':execute,'verify':verify,'archive':archive}[args.phase](args)

if __name__ == '__main__':
    main()
