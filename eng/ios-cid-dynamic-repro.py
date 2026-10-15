#!/usr/bin/env python3
"""Compare CID candidates with a noncollectible dynamic receiver and collectible implementation."""
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

SOURCES = {
    'ProbeContract': '''namespace Probe;
public interface IProbe { int Tick(int index); }
''',
    'ProbePlugin': '''using System;
using System.Runtime.InteropServices;
using Probe;
[DynamicInterfaceCastableImplementation]
public interface Plugin : IProbe
{
    private static int counter;
    int IProbe.Tick(int index)
    {
        int value = ++counter;
        Console.WriteLine($"DYNAMIC_BODY index={index} counter={value}");
        return value;
    }
}
''',
    'ProbeHost': '''using System;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using Probe;
public static class Driver
{
    private static Assembly sharedContract;
    private sealed class Context : AssemblyLoadContext
    {
        public Context() : base(isCollectible: true) { }
        protected override Assembly Load(AssemblyName name) =>
            name.Name == "ProbeContract" ? sharedContract : null;
    }
    private sealed class Receiver : IDynamicInterfaceCastable
    {
        public Type Implementation;
        public bool IsInterfaceImplemented(RuntimeTypeHandle requested, bool throwIfNotImplemented) =>
            requested.Equals(typeof(IProbe).TypeHandle) && Implementation != null;
        public RuntimeTypeHandle GetInterfaceImplementation(RuntimeTypeHandle requested)
        {
            if (!requested.Equals(typeof(IProbe).TypeHandle) || Implementation == null)
                throw new InvalidCastException();
            return Implementation.TypeHandle;
        }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void CallSite(IProbe probe)
    {
        for (int tick = 0; tick < 3; tick++)
        {
            Console.WriteLine($"DYNAMIC_BEFORE tick={tick}"); Console.Out.Flush();
            int value = probe.Tick(tick);
            if (value != tick + 1) throw new Exception($"Unexpected static counter {value}");
            Console.WriteLine($"DYNAMIC_AFTER tick={tick}"); Console.Out.Flush();
        }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static (WeakReference Context, WeakReference Type) Cycle(int index, Receiver receiver)
    {
        var context = new Context();
        var assembly = context.LoadFromAssemblyPath(Path.Combine(AppContext.BaseDirectory, "plugin", "ProbePlugin.dll"));
        Type implementation = assembly.GetType("Plugin", throwOnError: true);
        if (!implementation.Assembly.IsCollectible || receiver.GetType().Assembly.IsCollectible)
            throw new Exception("Incorrect receiver/implementation ownership");
        receiver.Implementation = implementation;
        Console.WriteLine($"DYNAMIC_CYCLE={index} RECEIVER_NONCOLLECTIBLE=True IMPLEMENTATION_COLLECTIBLE=True receiverMT={receiver.GetType().TypeHandle.Value:X}");
        try { CallSite((IProbe)(object)receiver); }
        finally { receiver.Implementation = null; }
        Console.WriteLine($"DYNAMIC_CYCLE={index} TYPE_CLEARED={receiver.Implementation == null}");
        var weakContext = new WeakReference(context);
        var weakType = new WeakReference(implementation);
        context.Unload();
        Console.WriteLine($"DYNAMIC_CYCLE={index} UNLOAD_REQUEST");
        return (weakContext, weakType);
    }
    public static int Run()
    {
        Console.WriteLine($"DYNAMIC_BEGIN runtime={RuntimeInformation.FrameworkDescription} compiled={RuntimeFeature.IsDynamicCodeCompiled}");
        sharedContract = typeof(IProbe).Assembly;
        Console.WriteLine("DYNAMIC_SHARED_CONTRACT_READY");
        var receiver = new Receiver();
        Console.WriteLine("DYNAMIC_RECEIVER_READY");
        for (int index = 1; index <= 20; index++)
        {
            var weak = Cycle(index, receiver);
            for (int attempt = 0; attempt < 20 && (weak.Context.IsAlive || weak.Type.IsAlive); attempt++)
            { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }
            bool collected = !weak.Context.IsAlive && !weak.Type.IsAlive;
            Console.WriteLine($"DYNAMIC_CYCLE={index} COLLECTED={collected}");
            if (!collected || receiver.Implementation != null) return 2;
        }
        GC.KeepAlive(receiver);
        Console.WriteLine("DYNAMIC_PASS cycles=20 ticks=60");
        return 0;
    }
}
''',
    'ProbeEntry': 'public static class Program { public static int Main() => Driver.Run(); }\n',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args, log, env=None, check=True, timeout=180):
    with log.open('w') as stream:
        try:
            status = subprocess.run([str(a) for a in args], stdout=stream, stderr=subprocess.STDOUT,
                                    env=env, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            status = 124
            stream.write('\nDYNAMIC_TIMEOUT\n')
    if check and status != 0:
        raise RuntimeError('Command failed; inspect ' + str(log))
    return status


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def build(root, out):
    script = Path(__file__).with_name('ios-r2r-repro.py')
    original_args = sys.argv
    try:
        sys.argv = [str(script), str(root), str(out)]
        spec = importlib.util.spec_from_file_location('dynamic_probe_builder', script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.argv = original_args
    module.SOURCES = SOURCES
    module.build()
    baseline = out / 'r2r/Probe.app'
    candidates = {'v1': root / 'ios-r2r-fix-20261012', 'v2': root / 'ios-r2r-fix-v2-20261012'}
    identities = {}
    sections = subprocess.check_output(['otool', '-s', '__TEXT', '__text', str(baseline / 'Probe')], text=True).splitlines()[1:]
    managed = {str(p.relative_to(baseline)): sha(p) for p in baseline.rglob('*.dll')}
    composites = {n: sha(baseline / n) for n in ['framework.dylib', 'probe.dylib']}
    for name, candidate in candidates.items():
        metadata = json.loads((candidate / 'logs/artifacts.json').read_text())
        source = json.loads((candidate / 'logs/source.json').read_text())
        native = Path(metadata['libcoreclr'])
        if sha(native) != metadata['libcoreclrSha256']:
            raise RuntimeError('Candidate native provenance differs')
        app = out / name / 'Probe.app'
        app.parent.mkdir()
        shutil.copytree(baseline, app)
        shutil.copy2(native, app / 'libcoreclr.dylib')
        command(['codesign', '--force', '--sign', '-', app / 'libcoreclr.dylib'], out / 'logs' / (name + '-native-sign.log'))
        command(['codesign', '--force', '--sign', '-', app], out / 'logs' / (name + '-app-sign.log'))
        if any(sha(app / n) != h for n, h in {**managed, **composites}.items()):
            raise RuntimeError('Managed/composite identity changed')
        text = subprocess.check_output(['otool', '-s', '__TEXT', '__text', str(app / 'Probe')], text=True).splitlines()[1:]
        if text != sections:
            raise RuntimeError('Native wrapper code changed')
        identities[name] = {'source': source, 'unsignedNativeSha256': sha(native),
                            'signedNativeSha256': sha(app / 'libcoreclr.dylib')}
    write_json(out / 'logs/identity.json', {'managed': managed, 'composites': composites,
        'sources': {p.name: sha(p) for p in (out / 'source').glob('*.cs')},
        'wrapperTextSha256': hashlib.sha256('\n'.join(sections).encode()).hexdigest(),
        'originalNativeSha256': sha(baseline / 'libcoreclr.dylib'), 'candidates': identities})


def inspect(log, status):
    text = log.read_text(errors='replace')
    collected = text.count('COLLECTED=True')
    cleared = text.count('TYPE_CLEARED=True')
    after = len(re.findall('DYNAMIC_AFTER tick=[0-9]+', text))
    receiver_types = set(re.findall('receiverMT=([0-9A-F]+)', text))
    body_dump = any('Interpreter compile method' in line and 'Plugin:' in line and 'Tick' in line
                    for line in text.splitlines()) and any(
                        'Compiled method:' in line and 'Plugin:' in line and 'Tick' in line
                        for line in text.splitlines())
    native_crash = 'SIGSEGV' in text or 'EXC_BAD_ACCESS' in text
    passed = (status == 0 and 'DYNAMIC_PASS cycles=20 ticks=60' in text and 'RUNECLR_EXIT=0' in text
              and collected == 20 and cleared == 20 and after == 60 and len(receiver_types) == 1
              and body_dump and '.NET 12.0.0-dev' in text and not native_crash and 'Assert failure' not in text)
    return {'passed': passed, 'launcherExit': status, 'collectedContextsAndTypes': collected,
        'clearedReceiverTypes': cleared, 'completedTicks': after, 'receiverTypeCount': len(receiver_types),
        'interpretedImplementationDump': body_dump, 'nativeCrash': native_crash,
        'assertion': 'Assert failure' in text,
        'managedExit0': 'RUNECLR_EXIT=0' in text, 'logSha256': sha(log)}


def run(out):
    work = out / 'run'
    work.mkdir()
    simulator = subprocess.check_output(['xcrun', 'simctl', 'create', 'RuneCLR-CID-Dynamic-Owner',
        'com.apple.CoreSimulator.SimDeviceType.iPhone-17', 'com.apple.CoreSimulator.SimRuntime.iOS-27-0'], text=True).strip()
    (work / 'simulator.uuid').write_text(simulator + '\n')
    results = {}
    env = {k: v for k, v in os.environ.items() if not k.startswith(('DOTNET_', 'COMPlus_', 'SIMCTL_CHILD_DOTNET_', 'SIMCTL_CHILD_COMPlus_'))}
    try:
        command(['xcrun', 'simctl', 'boot', simulator], work / 'boot-command.log')
        command(['xcrun', 'simctl', 'bootstatus', simulator, '-b'], work / 'boot.log')
        for name, lane in [('original', 'r2r'), ('v1', 'v1'), ('v2', 'v2'), ('il-control', 'il')]:
            bundle = 'org.runeclr.ios.r2r.probe.' + ('il' if lane == 'il' else 'r2r')
            command(['xcrun', 'simctl', 'install', simulator, out / lane / 'Probe.app'], work / (name + '-install.log'))
            log = work / (name + '.log')
            status = command(['xcrun', 'simctl', 'launch', '--console', simulator, bundle], log, env=env, check=False, timeout=90)
            results[name] = inspect(log, status)
            print(name, json.dumps(results[name]), flush=True)
            write_json(work / 'results.json', results)
            command(['xcrun', 'simctl', 'terminate', simulator, bundle], work / (name + '-terminate.log'), check=False)
    finally:
        shutdown = command(['xcrun', 'simctl', 'shutdown', simulator], work / 'shutdown.log', check=False)
        (work / 'shutdown.exit').write_text(str(shutdown) + '\n')
    success = results.get('v2', {}).get('passed', False) and results.get('il-control', {}).get('passed', False) and shutdown == 0
    write_json(work / 'results-verified.json', {'success': success, 'results': results, 'simulatorShutdown': shutdown == 0})
    return 0 if success else 1


def verify(out):
    work = out / 'run'
    previous = json.loads((work / 'results.json').read_text())
    results = {name: inspect(work / (name + '.log'), item['launcherExit'])
               for name, item in previous.items()}
    shutdown = (work / 'shutdown.exit').read_text().strip() == '0'
    success = (set(results) == {'original', 'v1', 'v2', 'il-control'}
               and results['v2']['passed'] and results['il-control']['passed'] and shutdown)
    target = work / 'results-reverified.json'
    if target.exists():
        raise RuntimeError('Preserve previous verified result')
    write_json(target, {'success': success, 'results': results, 'simulatorShutdown': shutdown})
    print(target.read_text())
    return 0 if success else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'run', 'all', 'verify'])
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    options = parser.parse_args()
    if options.action == 'verify':
        return verify(options.output)
    if options.action in ('build', 'all'):
        build(options.root, options.output)
    if options.action in ('run', 'all'):
        return run(options.output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
