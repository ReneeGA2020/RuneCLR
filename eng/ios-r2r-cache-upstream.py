#!/usr/bin/env python3
"""Execute pinned upstream collectible tests through a standalone simulator adapter.

The test source is unchanged. The small adapter supplies attributes/assertions
and calls test methods directly; this is not the generated upstream test runner.
"""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else
    '/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr')
SOURCE = ROOT / 'runtime'
BASE = ROOT / 'preview6-experiment/pinned-debug-harness'
DIAGNOSTIC = ROOT / 'ios-r2r-cache-20261012'
OUT = DIAGNOSTIC / 'upstream-source-tests-trace'
SDK = SOURCE / '.dotnet/dotnet'

ADAPTER = '''using System;
using System.Collections.Generic;
namespace TestLibrary
{
    public enum TestRuntimes { Mono }
    public enum RuntimeTestModes { AnyGCStress }
    public static class Utilities { public static bool IsNativeAot => false; }
    public static class PlatformDetection { public static bool IsCollectibleAssembliesSupported => true; }
}
namespace Xunit
{
    [AttributeUsage(AttributeTargets.Method, AllowMultiple = true)]
    public sealed class ActiveIssueAttribute : Attribute
    {
        public ActiveIssueAttribute(string issue, Type type, string condition) { }
        public ActiveIssueAttribute(string issue, TestLibrary.TestRuntimes runtime) { }
    }
    public sealed class SkipOnCoreClrAttribute : Attribute
    { public SkipOnCoreClrAttribute(string reason, TestLibrary.RuntimeTestModes modes) { } }
    public sealed class ConditionalFactAttribute : Attribute
    { public ConditionalFactAttribute(Type type, string condition) { } }
    public sealed class FactAttribute : Attribute { }
    public static class Assert
    {
        public static void False(bool value, string message = null)
        { if (value) throw new Exception(message ?? "Assert.False failed"); }
        public static void NotNull(object value)
        { if (value is null) throw new Exception("Assert.NotNull failed"); }
        public static void Equal<T>(T expected, T actual)
        { if (!EqualityComparer<T>.Default.Equals(expected, actual)) throw new Exception($"Expected {expected}, got {actual}"); }
        public static T Throws<T>(Action action) where T : Exception
        {
            try { action(); }
            catch (Exception error)
            { if (error.GetType() == typeof(T)) return (T)error; throw; }
            throw new Exception($"Expected {typeof(T)}");
        }
    }
}
'''
BRIDGE = '''using System;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
public static class Program
{
    public static int Main()
    {
        Console.WriteLine($"UPSTREAM_BEGIN runtime={RuntimeInformation.FrameworkDescription} compiled={RuntimeFeature.IsDynamicCodeCompiled}");
        int resolved = Test.TestEntryPoint();
        if (resolved != 100) throw new Exception($"ResolvedFromDifferentContext returned {resolved}");
        Console.WriteLine("UPSTREAM_PASS ResolvedFromDifferentContext cases=4");
        GenericVirtualMethodUnloading.CallGenericVirtualMethodAcrossUnloads();
        Console.WriteLine("UPSTREAM_PASS GenericVirtualMethod cycles=10");
        Console.WriteLine("UPSTREAM_SUITE_PASS tests=2");
        return 0;
    }
}
'''

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(args, log, env=None, timeout=None, check=True):
    with open(log, 'w') as stream:
        try:
            result = subprocess.run([str(a) for a in args], stdout=stream, stderr=subprocess.STDOUT,
                env=env, timeout=timeout, check=check)
            return result.returncode
        except subprocess.TimeoutExpired:
            stream.write('\nUPSTREAM_TIMEOUT\n')
            return 124

def main():
    OUT.mkdir(exist_ok=False)
    logs = OUT / 'logs'; logs.mkdir()
    sources = OUT / 'sources'; sources.mkdir()
    inputs = OUT / 'input'; inputs.mkdir()
    tests = SOURCE / 'src/tests/Loader/CollectibleAssemblies'
    hashes = {}
    relative = [
        'ResolvedFromDifferentContext/Interface.cs',
        'ResolvedFromDifferentContext/Class.cs',
        'ResolvedFromDifferentContext/ResolvedFromDifferentContext.cs',
        'GenericVirtualMethod/GenericVirtualMethodUnloaded.cs',
        'GenericVirtualMethod/GenericVirtualMethod.cs',
    ]
    for name in relative:
        p = tests / name; destination = sources / name
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(p, destination); hashes[name] = sha(p)
    (sources / 'Adapter.cs').write_text(ADAPTER)
    (sources / 'Bridge.cs').write_text(BRIDGE)
    (logs / 'upstream-source-hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
    version = subprocess.check_output([SDK, '--version'], text=True).strip()
    csc = SOURCE / '.dotnet/sdk' / version / 'Roslyn/bincore/csc.dll'
    refs = [f'-r:{p}' for p in sorted((BASE / 'original').glob('*.dll')) if not p.name.startswith(('RuneCLR.', 'HarnessBridge'))]
    def compile(name, source, references=(), executable=False):
        output = inputs / (name + '.dll')
        run([SDK, csc, '-nologo', '-noconfig', '-nostdlib+', '-optimize+',
            '-target:' + ('exe' if executable else 'library'), '-out:' + str(output),
            *refs, *[f'-r:{inputs / (ref + ".dll")}' for ref in references], source], logs / (name + '-compile.log'))
    compile('UpstreamAdapter', sources / 'Adapter.cs')
    compile('TestInterface', sources / 'ResolvedFromDifferentContext/Interface.cs')
    compile('TestClass', sources / 'ResolvedFromDifferentContext/Class.cs', ['TestInterface'])
    compile('UpstreamResolved', sources / 'ResolvedFromDifferentContext/ResolvedFromDifferentContext.cs', ['UpstreamAdapter'])
    compile('GenericVirtualMethodUnloaded', sources / 'GenericVirtualMethod/GenericVirtualMethodUnloaded.cs')
    compile('UpstreamGeneric', sources / 'GenericVirtualMethod/GenericVirtualMethod.cs', ['UpstreamAdapter'])
    compile('UpstreamBridge', sources / 'Bridge.cs', ['UpstreamResolved', 'UpstreamGeneric'], executable=True)
    app = OUT / 'UpstreamRegression.app'
    shutil.copytree(BASE / 'app/RuneCLRPinnedHarness.app', app)
    for name in ('UpstreamAdapter', 'UpstreamResolved', 'UpstreamGeneric', 'GenericVirtualMethodUnloaded', 'UpstreamBridge'):
        shutil.copy2(inputs / (name + '.dll'), app / (name + '.dll'))
    for name in ('TestInterface', 'TestClass'):
        (app / name).mkdir()
        shutil.copy2(inputs / (name + '.dll'), app / name / (name + '.dll'))
    for name in ('main.m', 'util.h', 'coreclrhost.h', 'host_runtime_contract.h'):
        shutil.copy2(BASE / name, OUT / name)
    (OUT / 'runtime.m').write_text((BASE / 'runtime.m').read_text().replace('HarnessBridge.dll', 'UpstreamBridge.dll'))
    plist = plistlib.loads((app / 'Info.plist').read_bytes())
    plist['CFBundleIdentifier'] = 'org.runeclr.cid.upstream'
    (app / 'Info.plist').write_bytes(plistlib.dumps(plist))
    run(['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator',
        '-fobjc-arc', '-DINVARIANT_GLOBALIZATION=1', '-I' + str(OUT), OUT / 'main.m', OUT / 'runtime.m',
        '-L' + str(app), '-lcoreclr', '-framework', 'UIKit', '-framework', 'Foundation',
        '-Wl,-rpath,@executable_path', '-o', app / 'RuneCLRPinnedHarness'], logs / 'native-build.log')
    run(['codesign', '--force', '--sign', '-', app], logs / 'baseline-sign.log')
    simulator = subprocess.check_output(['xcrun', 'simctl', 'create', 'RuneCLR-CID-Upstream-Diagnostic',
        'com.apple.CoreSimulator.SimDeviceType.iPhone-17', 'com.apple.CoreSimulator.SimRuntime.iOS-27-0'], text=True).strip()
    (logs / 'simulator.uuid').write_text(simulator + '\n')
    results = {}
    try:
        run(['xcrun', 'simctl', 'boot', simulator], logs / 'boot-command.log')
        run(['xcrun', 'simctl', 'bootstatus', simulator, '-b'], logs / 'boot.log', timeout=180)
        for case, switch, native in (('original', '0', BASE / 'app/RuneCLRPinnedHarness.app/libcoreclr.dylib'),
            ('diagnostic-off', '0', DIAGNOSTIC / 'obj-trace/dlls/mscoree/coreclr/libcoreclr.dylib'),
            ('diagnostic-on', '1', DIAGNOSTIC / 'obj-trace/dlls/mscoree/coreclr/libcoreclr.dylib')):
            shutil.copy2(native, app / 'libcoreclr.dylib')
            run(['codesign', '--force', '--sign', '-', app / 'libcoreclr.dylib'], logs / (case + '-native-sign.log'))
            run(['codesign', '--force', '--sign', '-', app], logs / (case + '-app-sign.log'))
            run(['xcrun', 'simctl', 'install', simulator, app], logs / (case + '-install.log'), timeout=60)
            env = dict(os.environ); env['SIMCTL_CHILD_DOTNET_RuneCLRDisableCollectibleInterfaceDispatchCache'] = switch
            log = logs / (case + '.log')
            status = run(['xcrun', 'simctl', 'launch', '--console', simulator, 'org.runeclr.cid.upstream'],
                log, env=env, timeout=90, check=False)
            data = log.read_text(errors='replace')
            results[case] = {'launcherExit': status, 'pass': 'UPSTREAM_SUITE_PASS tests=2' in data and 'RUNECLR_EXIT=0' in data,
                'cacheSkips': data.count('RUNECLR_CID_RESOLVE skip=1'), 'logSha256': sha(log), 'nativeSha256': sha(app / 'libcoreclr.dylib')}
            print(case + ': ' + json.dumps(results[case]), flush=True)
            (logs / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
            run(['xcrun', 'simctl', 'terminate', simulator, 'org.runeclr.cid.upstream'], logs / (case + '-terminate.log'), check=False)
    finally:
        run(['xcrun', 'simctl', 'shutdown', simulator], logs / 'shutdown.log', check=False)
    return 0 if len(results) == 3 and all(r['pass'] for r in results.values()) else 1

if __name__ == '__main__':
    sys.exit(main())
