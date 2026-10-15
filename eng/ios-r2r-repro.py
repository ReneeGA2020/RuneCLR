#!/usr/bin/env python3
"""Build a private compiled-interface repro beside the preserved iOS experiment."""
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else
    '/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr')
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'ios-r2r-interface-repro-struct'
RUNTIME = ROOT / 'runtime'
BASE = ROOT / 'preview6-experiment/pinned-debug-harness'
SDK = RUNTIME / '.dotnet/dotnet'
COMPILER = RUNTIME / 'artifacts/bin/coreclr/iossimulator.arm64.Debug/arm64/crossgen2/crossgen2'

SOURCES = {
    'ProbeContract': '''using System;
namespace Probe;
public readonly record struct Tick(int Index, TimeSpan DeltaTime);
public interface IProbe { void Start(); void Tick(Tick tick); void Stop(); }
''',
    'ProbePlugin': '''using System;
using Probe;
public sealed class Plugin : IProbe
{
    private static int counter;
    public void Start() => Console.WriteLine($"PLUGIN_START counter={counter}");
    public void Tick(Tick tick) => Console.WriteLine($"PLUGIN_TICK counter={++counter} index={tick.Index} ticks={tick.DeltaTime.Ticks}");
    public void Stop() => Console.WriteLine($"PLUGIN_STOP counter={counter}");
}
''',
    'ProbeHost': '''using System;
using System.Collections.Generic;
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
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void CallSite(IProbe probe)
    {
        Console.WriteLine("CALL_START"); probe.Start();
        Console.WriteLine("CALL_TICK"); probe.Tick(new Tick(0, TimeSpan.FromMilliseconds(16)));
        Console.WriteLine("CALL_STOP"); probe.Stop();
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static WeakReference Cycle(int index, bool unload, List<object> retained)
    {
        var context = new Context();
        var assembly = context.LoadFromAssemblyPath(Path.Combine(AppContext.BaseDirectory, "plugin", "ProbePlugin.dll"));
        var probe = (IProbe)Activator.CreateInstance(assembly.GetType("Plugin", throwOnError: true));
        Console.WriteLine($"CYCLE={index} LOADED collectible={context.IsCollectible}");
        CallSite(probe);
        Console.WriteLine($"CYCLE={index} RETURNED");
        var weak = new WeakReference(context);
        if (unload) context.Unload(); else retained.Add(context);
        return weak;
    }
    public static int Run()
    {
        string mode = Environment.GetEnvironmentVariable("PROBE_MODE") ?? "collect";
        int cycles = int.Parse(Environment.GetEnvironmentVariable("PROBE_CYCLES") ?? "20");
        if (cycles < 1 || (mode != "collect" && mode != "retain" && mode != "unload")) return 3;
        Console.WriteLine($"PROBE_BEGIN mode={mode} runtime={RuntimeInformation.FrameworkDescription} rid={RuntimeInformation.RuntimeIdentifier} compiled={RuntimeFeature.IsDynamicCodeCompiled}");
        sharedContract = typeof(IProbe).Assembly;
        var retained = new List<object>();
        for (int i = 1; i <= cycles; i++)
        {
            var weak = Cycle(i, mode != "retain", retained);
            if (mode == "collect")
            {
                for (int attempt = 0; attempt < 20 && weak.IsAlive; attempt++)
                { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }
                Console.WriteLine($"CYCLE={i} COLLECTED={!weak.IsAlive}");
                if (weak.IsAlive) return 2;
            }
        }
        GC.KeepAlive(retained);
        Console.WriteLine($"PROBE_PASS cycles={cycles}"); return 0;
    }
}
''',
    'ProbeEntry': '''public static class Program { public static int Main() => Driver.Run(); }
''',
}

def run(args, log):
    with open(log, 'w') as stream:
        subprocess.run([str(a) for a in args], stdout=stream, stderr=subprocess.STDOUT, check=True)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def build():
    # Refuse to silently replace an earlier experiment.
    OUT.mkdir(exist_ok=False)
    (OUT / 'logs').mkdir()
    (OUT / 'source').mkdir()
    (OUT / 'input').mkdir()
    head = subprocess.check_output(['git', '-C', str(RUNTIME), 'rev-parse', 'HEAD'], text=True).strip()
    if head != '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de':
        raise RuntimeError('Expected pinned source; refusing another runtime revision')
    (OUT / 'logs/source-status.txt').write_text(subprocess.check_output(['git', '-C', str(RUNTIME), 'status', '--short'], text=True))
    (OUT / 'logs/source-head.txt').write_text(head + '\n')
    run([SDK, '--info'], OUT / 'logs/sdk-info.txt')
    run([COMPILER, '--version'], OUT / 'logs/crossgen-version.txt')
    (OUT / 'logs/source-artifact-hashes.json').write_text(json.dumps({str(p): sha(p) for p in [COMPILER, BASE / 'app/RuneCLRPinnedHarness.app/libcoreclr.dylib', BASE / 'original/System.Private.CoreLib.dll']}, indent=2))
    refs = [p for p in sorted((BASE / 'original').glob('*.dll')) if not p.name.startswith(('RuneCLR.', 'HarnessBridge'))]
    for p in refs:
        shutil.copy2(p, OUT / 'input' / p.name)
    sdk_version = subprocess.check_output([SDK, '--version'], text=True).strip()
    csc = RUNTIME / '.dotnet/sdk' / sdk_version / 'Roslyn/bincore/csc.dll'
    for name, source in SOURCES.items():
        src = OUT / 'source' / (name + '.cs')
        src.write_text(source)
        references = [f'-r:{p}' for p in refs]
        if name in ('ProbeHost', 'ProbePlugin'):
            references.append(f'-r:{OUT / "input/ProbeContract.dll"}')
        if name == 'ProbeEntry':
            references.append(f'-r:{OUT / "input/ProbeHost.dll"}')
        target = 'exe' if name == 'ProbeEntry' else 'library'
        run([SDK, csc, '-nologo', '-noconfig', '-nostdlib+', '-optimize+', f'-target:{target}', f'-out:{OUT / "input" / (name + ".dll")}', *references, src], OUT / 'logs' / (name + '-compile.log'))
    for variant in ('r2r', 'il'):
        lane = OUT / variant
        app = lane / 'Probe.app'
        app.mkdir(parents=True)
        (lane / 'logs').mkdir()
        (app / 'plugin').mkdir()
        shutil.copy2(OUT / 'input/ProbePlugin.dll', app / 'plugin/ProbePlugin.dll')
        # Keep the matching, already measured framework composite unchanged.
        for p in (BASE / 'app/RuneCLRPinnedHarness.app').iterdir():
            if p.is_file() and p.suffix in ('.dll', '.dylib'):
                shutil.copy2(p, app / p.name)
        inputs = [p for p in sorted((OUT / 'input').glob('Probe*.dll')) if p.name != 'ProbePlugin.dll']
        composite = [p for p in inputs if variant == 'r2r' or p.name != 'ProbeHost.dll']
        args = ['--targetos:iossimulator', '--targetarch:arm64', '--obj-format:macho', '--composite', '--inputbubble', '--parallelism:2', '--resilient', '--optimize', f'--out:{app / "probe.dylib"}', *map(str, composite), *[f'-r:{p}' for p in refs]]
        if variant == 'il':
            args.append(f'-r:{OUT / "input/ProbeHost.dll"}')
        rsp = lane / 'crossgen.rsp'
        rsp.write_text('\n'.join(args) + '\n')
        run([COMPILER, '@' + str(rsp)], lane / 'logs/crossgen.log')
        if variant == 'il':
            shutil.copy2(OUT / 'input/ProbeHost.dll', app / 'ProbeHost.dll')
        obj = lane / 'probe.o'
        shutil.copy2(app / 'probe.dylib', obj)
        run(['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator', '-dynamiclib', obj, '-Wl,-install_name,@rpath/probe.dylib', '-o', app / 'probe.dylib'], lane / 'logs/composite-link.log')
        for name in ('main.m', 'util.h', 'coreclrhost.h', 'host_runtime_contract.h'):
            shutil.copy2(BASE / name, lane / name)
        wrapper = (BASE / 'runtime.m').read_text().replace('HarnessBridge.dll', 'ProbeEntry.dll').replace('RuneCLR.TestMaps.CounterMap:OnTick RuneCLR.LateMap.LateMap:*', 'Plugin:* Driver:*')
        (lane / 'runtime.m').write_text(wrapper)
        plist = plistlib.loads((BASE / 'app/RuneCLRPinnedHarness.app/Info.plist').read_bytes())
        plist.update(CFBundleExecutable='Probe', CFBundleName='Probe', CFBundleIdentifier='org.runeclr.ios.r2r.probe.' + variant)
        (app / 'Info.plist').write_bytes(plistlib.dumps(plist))
        run(['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator', '-fobjc-arc', '-DINVARIANT_GLOBALIZATION=1', '-I' + str(lane), lane / 'main.m', lane / 'runtime.m', '-L' + str(app), '-lcoreclr', '-framework', 'UIKit', '-framework', 'Foundation', '-Wl,-rpath,@executable_path', '-o', app / 'Probe'], lane / 'logs/native-build.log')
        for p in app.glob('*.dylib'):
            run(['codesign', '--force', '--sign', '-', p], lane / 'logs' / (p.name + '-sign.log'))
        run(['codesign', '--force', '--sign', '-', app], lane / 'logs/app-sign.log')
    (OUT / 'logs/build.status').write_text('0\n')

if __name__ == '__main__':
    build()
