#!/usr/bin/env python3
"""Run related upstream adapters and explicit CID regressions on a pinned iOS fix."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import time
import uuid

BASE = "0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de"
COMMIT = "8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d"
NATIVE = "475e10c45d81c62d212a631dc6fc61ea6a40dcaf369fa97a3870426b1ec8c438"
CASES = ("values", "defaults", "generic", "exceptions")

SOURCES = {
    "RegressionContract": r'''using System;
namespace Regression;
public readonly record struct Tick(int Index, TimeSpan DeltaTime);
public interface IValues { long Map(Tick tick); }
public interface IDefaults { int Map(int value) => -1; }
public interface IGeneric<T> { T Map(T value); }
public interface IExceptions { int Map(int value); }
''',
    "RegressionPlugin": r'''using System;
using Regression;
public static class Counters { public static int Values, Defaults, Generic, Exceptions; }
public interface LocalDefault : IDefaults
{
    int IDefaults.Map(int value) => 100 + value + ++Counters.Defaults;
}
public class PluginBase : LocalDefault { }
public sealed class Plugin : PluginBase, IValues, IGeneric<int>, IExceptions
{
    long IValues.Map(Tick tick) => 1000L * ++Counters.Values + tick.Index + tick.DeltaTime.Ticks;
    int IGeneric<int>.Map(int value) => value + ++Counters.Generic;
    int IExceptions.Map(int value)
    {
        int count = ++Counters.Exceptions;
        if (value == 1) throw new AuthorError("expected=" + count);
        return value + count;
    }
}
public sealed class AuthorError : Exception { public AuthorError(string message) : base(message) { } }
''',
    "RegressionHost": r'''using System;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using Regression;
public static class RegressionDriver
{
    private static Assembly contract;
    private sealed class Context : AssemblyLoadContext
    {
        public Context() : base(isCollectible: true) { }
        protected override Assembly Load(AssemblyName name) => name.Name == "RegressionContract" ? contract : null;
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void Values(IValues receiver)
    {
        for (int i = 0; i < 3; i++)
        {
            Before(i);
            long value = receiver.Map(new Tick(i, TimeSpan.FromMilliseconds(16)));
            Require(value == 1000L * (i + 1) + i + 160000, "Value argument or return mismatch");
            After(i);
        }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void Defaults(IDefaults receiver)
    {
        for (int i = 0; i < 3; i++)
        {
            Before(i); Require(receiver.Map(i) == 101 + 2 * i, "Inherited default interface result mismatch"); After(i);
        }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void Generic(IGeneric<int> receiver)
    {
        for (int i = 0; i < 3; i++)
        {
            Before(i); Require(receiver.Map(i) == 1 + 2 * i, "Closed generic interface result mismatch"); After(i);
        }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void Exceptions(IExceptions receiver)
    {
        for (int i = 0; i < 3; i++)
        {
            Before(i);
            try
            {
                int value = receiver.Map(i);
                Require(i != 1 && value == 1 + 2 * i, "Exception or recovery result mismatch");
            }
            catch (Exception error) when (i == 1 && error.Message == "expected=2")
            { Console.WriteLine("AUTHOR_EXCEPTION_CAUGHT"); }
            After(i);
        }
    }
    private static void Before(int index) { Console.WriteLine("REGRESSION_BEFORE index=" + index); Console.Out.Flush(); }
    private static void After(int index) { Console.WriteLine("REGRESSION_AFTER index=" + index); Console.Out.Flush(); }
    private static void Require(bool condition, string message) { if (!condition) throw new Exception(message); }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static WeakReference Cycle(string kind, int index)
    {
        var context = new Context();
        var assembly = context.LoadFromAssemblyPath(Path.Combine(AppContext.BaseDirectory, "plugin", "RegressionPlugin.dll"));
        object instance = Activator.CreateInstance(assembly.GetType("Plugin", throwOnError: true));
        Console.WriteLine("REGRESSION_CYCLE=" + index + " LOADED");
        switch (kind)
        {
            case "values": Values((IValues)instance); break;
            case "defaults": Defaults((IDefaults)instance); break;
            case "generic": Generic((IGeneric<int>)instance); break;
            case "exceptions": Exceptions((IExceptions)instance); break;
            default: throw new Exception("Unknown regression case");
        }
        Console.WriteLine("REGRESSION_CYCLE=" + index + " RETURNED");
        var weak = new WeakReference(context);
        context.Unload();
        return weak;
    }
    public static int Run()
    {
        string kind = Environment.GetEnvironmentVariable("REGRESSION_CASE") ?? "values";
        Console.WriteLine($"REGRESSION_BEGIN case={kind} runtime={RuntimeInformation.FrameworkDescription} compiled={RuntimeFeature.IsDynamicCodeCompiled}");
        contract = typeof(IValues).Assembly;
        for (int index = 1; index <= 20; index++)
        {
            var weak = Cycle(kind, index);
            for (int attempt = 0; attempt < 20 && weak.IsAlive; attempt++)
            { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }
            Console.WriteLine("REGRESSION_CYCLE=" + index + " COLLECTED=" + !weak.IsAlive);
            Require(!weak.IsAlive, "Collectible context retained");
        }
        Console.WriteLine("REGRESSION_PASS case=" + kind + " cycles=20 calls=60");
        return 0;
    }
}
''',
    "RegressionEntry": "public static class Program { public static int Main() => RegressionDriver.Run(); }\n",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def capture(arguments):
    return subprocess.check_output([str(a) for a in arguments], text=True).strip()


def logged(arguments, path, timeout=180, env=None, check=True):
    with Path(path).open("w") as stream:
        try:
            status = subprocess.run([str(a) for a in arguments], stdout=stream, stderr=subprocess.STDOUT, timeout=timeout, env=env).returncode
        except subprocess.TimeoutExpired:
            stream.write("\nREGRESSION_TIMEOUT\n")
            status = 124
    if check and status != 0:
        raise RuntimeError(f"Command failed ({status}): {arguments[0]}; see {path}")
    return status


def helper(name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    old_args = sys.argv
    try:
        sys.argv = [str(path)]
        spec.loader.exec_module(module)
    finally:
        sys.argv = old_args
    return module


def build(args):
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    logs, inputs, sources = (out / n for n in ("logs", "input", "source"))
    for path in logs, inputs, sources:
        path.mkdir()
    root = args.root.resolve()
    baseline = root / "preview6-experiment/pinned-debug-harness"
    original_app = baseline / "app/RuneCLRPinnedHarness.app"
    runtime = root / "runtime"
    candidate = args.candidate.resolve()
    record = json.loads((candidate / "logs/artifacts.json").read_text())
    identity = json.loads((candidate / "logs/source.json").read_text())
    native = Path(record["libcoreclr"])
    if capture(["git", "-C", candidate / "runtime", "rev-parse", "HEAD"]) != COMMIT or identity["base"] != BASE:
        raise RuntimeError("Candidate must match the recorded v2 source identity.")
    if capture(["git", "-C", candidate / "runtime", "status", "--porcelain", "--untracked-files=no"]):
        raise RuntimeError("Candidate tracked source is dirty.")
    if sha(native) != NATIVE or record["libcoreclrSha256"] != NATIVE:
        raise RuntimeError("Candidate native receipt mismatch.")
    mobile = helper("verify-ios-packages")
    provenance = mobile.provenance(runtime, root / "source12-selective-experiment")
    sdk = runtime / ".dotnet/dotnet"
    version = capture([sdk, "--version"])
    csc = runtime / ".dotnet/sdk" / version / "Roslyn/bincore/csc.dll"
    refs = [p for p in sorted((baseline / "original").glob("*.dll")) if not p.name.startswith(("RuneCLR.", "HarnessBridge"))]
    for name, source in SOURCES.items():
        src = sources / (name + ".cs")
        src.write_text(source)
        extra = [inputs / "RegressionContract.dll"] if name in ("RegressionHost", "RegressionPlugin") else [inputs / "RegressionHost.dll"] if name == "RegressionEntry" else []
        logged([sdk, csc, "-nologo", "-noconfig", "-nostdlib+", "-optimize+", "-target:" + ("exe" if name == "RegressionEntry" else "library"),
                "-out:" + str(inputs / (name + ".dll")), *["-r:" + str(p) for p in refs + extra], src], logs / (name + "-compile.log"))
    app = out / "apps/Regression.app"
    shutil.copytree(original_app, app)
    (app / "plugin").mkdir()
    shutil.copy2(inputs / "RegressionPlugin.dll", app / "plugin/RegressionPlugin.dll")
    crossgen = runtime / "artifacts/bin/coreclr/iossimulator.arm64.Debug/arm64/crossgen2/crossgen2"
    rsp = out / "crossgen.rsp"
    composite = [inputs / (name + ".dll") for name in ("RegressionContract", "RegressionHost", "RegressionEntry")]
    options = ["--targetos:iossimulator", "--targetarch:arm64", "--obj-format:macho", "--composite", "--inputbubble", "--resilient", "--optimize", "--parallelism:2", "--out:" + str(app / "regression.dylib")]
    rsp.write_text("\n".join(mobile.rsp_argument(a) for a in options + ["-r:" + str(p) for p in refs] + [str(p) for p in composite]) + "\n")
    logged([crossgen, "@" + str(rsp)], logs / "crossgen.log")
    obj = out / "regression.o"
    shutil.copy2(app / "regression.dylib", obj)
    logged(["xcrun", "--sdk", "iphonesimulator", "clang", "-target", "arm64-apple-ios15.3-simulator", "-dynamiclib", obj, "-Wl,-install_name,@rpath/regression.dylib", "-o", app / "regression.dylib"], logs / "composite-link.log")
    for name in ("main.m", "util.h", "coreclrhost.h", "host_runtime_contract.h"):
        shutil.copy2(baseline / name, out / name)
    wrapper = (baseline / "runtime.m").read_text().replace("HarnessBridge.dll", "RegressionEntry.dll")
    wrapper = wrapper.replace("RuneCLR.TestMaps.CounterMap:OnTick RuneCLR.LateMap.LateMap:*", "Plugin:* LocalDefault:* RegressionDriver:*")
    (out / "runtime.m").write_text(wrapper)
    bundle = "org.runeclr.cid.regressions." + uuid.uuid4().hex[:12]
    plist = plistlib.loads((app / "Info.plist").read_bytes())
    plist.update(CFBundleExecutable="Regression", CFBundleName="Regression", CFBundleIdentifier=bundle)
    (app / "Info.plist").write_bytes(plistlib.dumps(plist))
    logged(["xcrun", "--sdk", "iphonesimulator", "clang", "-target", "arm64-apple-ios15.3-simulator", "-fobjc-arc", "-DINVARIANT_GLOBALIZATION=1", "-I" + str(out), out / "main.m", out / "runtime.m", "-L" + str(app), "-lcoreclr", "-framework", "UIKit", "-framework", "Foundation", "-Wl,-rpath,@executable_path", "-o", app / "Regression"], logs / "native-build.log")
    logged(["nm", "-n", app / "regression.dylib"], logs / "symbols.log")
    for path in app.glob("*.dylib"):
        logged(["codesign", "--force", "--sign", "-", path], logs / (path.name + "-sign.log"))
    logged(["codesign", "--force", "--sign", "-", app], logs / "app-sign.log")
    apps = {}
    for label, library in (("original", original_app / "libcoreclr.dylib"),
                           ("trace", root / "ios-r2r-cache-20261012/obj-trace/dlls/mscoree/coreclr/libcoreclr.dylib"),
                           ("candidate", native)):
        target = out / "apps" / label / "Regression.app"
        target.parent.mkdir()
        shutil.copytree(app, target)
        shutil.copy2(library, target / "libcoreclr.dylib")
        logged(["codesign", "--force", "--sign", "-", target / "libcoreclr.dylib"], logs / (label + "-native-sign.log"))
        logged(["codesign", "--force", "--sign", "-", target], logs / (label + "-app-sign.log"))
        if mobile.macho_sections(library) != mobile.macho_sections(target / "libcoreclr.dylib"):
            raise RuntimeError("Signed native code/data changed.")
        apps[label] = {"app": str(target), "bundle": bundle, "nativeInputSha256": sha(library), "signedNativeSha256": sha(target / "libcoreclr.dylib")}
    shared = {str(p.relative_to(app)): sha(p) for p in app.rglob("*.dll")}
    for item in apps.values():
        if any(sha(Path(item["app"]) / n) != h for n, h in shared.items()) or sha(Path(item["app"]) / "regression.dylib") != sha(app / "regression.dylib"):
            raise RuntimeError("Native comparison changed managed/composite inputs.")
    upstream_root = root / "ios-r2r-cache-20261012/upstream-source-tests-trace"
    upstream = out / "apps/upstream/UpstreamRegression.app"
    upstream.parent.mkdir()
    shutil.copytree(upstream_root / "UpstreamRegression.app", upstream)
    upstream_shared = {str(p.relative_to(upstream)): sha(p) for p in upstream.rglob("*.dll")}
    shutil.copytree(upstream_root / "sources", out / "upstream-source")
    shutil.copy2(native, upstream / "libcoreclr.dylib")
    up_plist = plistlib.loads((upstream / "Info.plist").read_bytes())
    up_plist["CFBundleIdentifier"] = bundle + ".upstream"
    (upstream / "Info.plist").write_bytes(plistlib.dumps(up_plist))
    logged(["codesign", "--force", "--sign", "-", upstream / "libcoreclr.dylib"], logs / "upstream-native-sign.log")
    logged(["codesign", "--force", "--sign", "-", upstream], logs / "upstream-app-sign.log")
    if any(sha(upstream / n) != h for n, h in upstream_shared.items()):
        raise RuntimeError("Upstream managed source-adapter inputs changed.")
    layouts = {"host": mobile.il_layout(app / "RegressionHost.dll"), "plugin": mobile.il_layout(app / "plugin/RegressionPlugin.dll")}
    if not layouts["host"]["managedNativeRva"] or layouts["plugin"]["managedNativeRva"]:
        raise RuntimeError("Expected R2R host and IL-only plugin.")
    write(out / "state.json", {"candidateSource": identity, "candidateArtifact": record, "frameworkProvenance": provenance,
        "sourceSdk": version, "sourceHashes": {p.name: sha(p) for p in sources.glob("*.cs")}, "layouts": layouts,
        "managedHashes": shared, "compositeSha256": sha(app / "regression.dylib"), "apps": apps,
        "upstream": {"app": str(upstream), "bundle": up_plist["CFBundleIdentifier"], "managedHashes": upstream_shared}})
    print("BUILT independent v2 regression apps", flush=True)


def execute(args):
    out = args.output.resolve()
    state = json.loads((out / "state.json").read_text())
    logs = out / "logs"
    sim = capture(["xcrun", "simctl", "create", "RuneCLR-CID-Patched-Regressions-" + uuid.uuid4().hex[:8], "com.apple.CoreSimulator.SimDeviceType.iPhone-17", "com.apple.CoreSimulator.SimRuntime.iOS-27-0"])
    write(out / "simulator.json", {"uuid": sim, "shutdown": False})
    results = {}
    try:
        logged(["xcrun", "simctl", "boot", sim], logs / "boot.log")
        logged(["xcrun", "simctl", "bootstatus", sim, "-b"], logs / "bootstatus.log")
        groups = [(label + "-" + kind, label, kind) for label in ("original", "trace", "candidate") for kind in CASES]
        groups.append(("candidate-upstream", "upstream", "upstream"))
        for name, label, kind in groups:
            item = state["upstream"] if label == "upstream" else state["apps"][label]
            logged(["xcrun", "simctl", "install", sim, item["app"]], logs / (name + "-install.log"))
            env = dict(os.environ)
            for key in list(env):
                if key.startswith(("SIMCTL_CHILD_DOTNET_", "SIMCTL_CHILD_COMPlus_", "SIMCTL_CHILD_REGRESSION_")):
                    del env[key]
            env["SIMCTL_CHILD_REGRESSION_CASE"] = kind
            if label == "trace": env["SIMCTL_CHILD_DOTNET_RuneCLRDisableCollectibleInterfaceDispatchCache"] = "2"
            log = logs / (name + ".log")
            status = logged(["xcrun", "simctl", "launch", "--console", sim, item["bundle"]], log, env=env, check=False, timeout=120)
            text = log.read_text(errors="replace")
            passed = "RUNECLR_EXIT=0" in text and "CORECLR_EXECUTE_HRESULT=0x0" in text and "Assert failure" not in text and "REGRESSION_TIMEOUT" not in text
            collections = len(re.findall(r"REGRESSION_CYCLE=\d+ COLLECTED=True", text))
            dumps = text.count("Compiled method: .Plugin:") + text.count("Compiled method: .LocalDefault:")
            if kind == "upstream":
                passed = passed and "UPSTREAM_SUITE_PASS tests=2" in text
            else:
                passed = passed and f"REGRESSION_PASS case={kind} cycles=20 calls=60" in text and collections == 20 and dumps > 0
                for index in range(3):
                    passed = passed and text.count("REGRESSION_BEFORE index=" + str(index)) == 20 and text.count("REGRESSION_AFTER index=" + str(index)) == 20
                caller = {"values": "Values", "defaults": "Defaults", "generic": "Generic", "exceptions": "Exceptions"}[kind]
                passed = passed and "Interpreter compile method RegressionDriver:" + caller not in text
                if kind == "exceptions": passed = passed and text.count("AUTHOR_EXCEPTION_CAUGHT") == 20
            result = {"passed": passed, "launcherExit": status, "nativeFault": "Got a SIGSEGV while executing native code." in text,
                "collections": collections, "successfulPluginDumps": dumps, "before": len(re.findall(r"REGRESSION_BEFORE index=\d", text)),
                "after": len(re.findall(r"REGRESSION_AFTER index=\d", text)), "cacheRecords": text.count("RUNECLR_CID_RESOLVE"),
                "exceptionCaught": text.count("AUTHOR_EXCEPTION_CAUGHT"), "logSha256": sha(log)}
            results[name] = result
            write(out / "results.json", results)
            print(name + ": " + json.dumps(result), flush=True)
            logged(["xcrun", "simctl", "terminate", sim, item["bundle"]], logs / (name + "-terminate.log"), check=False)
    finally:
        shutdown = logged(["xcrun", "simctl", "shutdown", sim], logs / "shutdown.log", check=False)
        write(out / "simulator.json", {"uuid": sim, "shutdown": shutdown == 0})
    success = len(results) == 13 and all(results["candidate-" + kind]["passed"] for kind in CASES + ("upstream",))
    success = success and all(results["trace-" + kind]["cacheRecords"] > 0 for kind in CASES)
    write(out / "verified.json", {"success": success, "candidateCases": 4, "candidateSourceAdapterTests": 2, "results": results})
    if not success: raise RuntimeError("Patched CID regression acceptance failed; preserve logs.")
    print("PASS v2: 4 CID cases + 2 unchanged upstream source-adapter tests", flush=True)


def archive(args):
    out = args.output.resolve()
    artifact = out / "evidence.tar.gz"
    with tarfile.open(artifact, "w:gz") as tar:
        for name in ("logs", "source", "upstream-source", "input", "state.json", "results.json", "verified.json", "simulator.json", "crossgen.rsp", "runtime.m", "main.m"):
            path = out / name
            if path.exists(): tar.add(path, arcname=name)
        tar.add(Path(__file__), arcname="driver.py")
        for name in ("build-driver.py", "build-driver.log", "run-driver.log", "verify-driver.log"):
            path = out.parent / name
            if path.exists(): tar.add(path, arcname="driver-snapshots/" + name)
    print(json.dumps({"path": str(artifact), "sha256": sha(artifact), "bytes": artifact.stat().st_size}), flush=True)


def verify(args):
    out = args.output.resolve()
    state = json.loads((out / "state.json").read_text())
    results = json.loads((out / "results.json").read_text())
    checks = {}
    symbols = (out / "logs/symbols.log").read_text()
    for kind, caller in zip(CASES, ("Values", "Defaults", "Generic", "Exceptions")):
        if "RegressionDriver__" + caller not in symbols:
            raise RuntimeError("Native trusted caller symbol missing: " + caller)
        for label in ("original", "trace", "candidate"):
            name = label + "-" + kind
            result = results[name]
            text = (out / "logs" / (name + ".log")).read_text(errors="replace")
            result["runtimeReported"] = "runtime=.NET 12.0.0-dev compiled=False" in text
            result["initialized"] = "CORECLR_INITIALIZE_HRESULT=0x0" in text
            result["nativeCaller"] = "Interpreter compile method RegressionDriver:" + caller not in text
            prefix = {"values": ".Plugin:Regression.IValues.Map", "defaults": ".LocalDefault:Regression.IDefaults.Map",
                      "generic": ".Plugin:Regression.IGeneric", "exceptions": ".Plugin:Regression.IExceptions.Map"}[kind]
            result["callbackSuccessfulDumps"] = len(re.findall(r"(?m)^Compiled method: " + re.escape(prefix) + r".*$", text))
            valid = result["runtimeReported"] and result["initialized"] and result["nativeCaller"]
            valid = valid and "Assert failure" not in text
            if label == "candidate":
                valid = valid and result["passed"] and result["callbackSuccessfulDumps"] == 20
            else:
                sample = out / "logs" / (name + "-sample.txt")
                # A bounded stall with a native-stack sample is a negative control.
                stall = (kind == "defaults" and result["launcherExit"] == 124 and sample.exists()
                         and result["collections"] == 1 and result["before"] == 4 and result["after"] == 3
                         and "RegressionHost_RegressionDriver__Cycle" in sample.read_text(errors="replace"))
                result["sampledRetirementStall"] = stall
                valid = valid and (result["passed"] or result["nativeFault"] or stall)
            if label == "trace": valid = valid and result["cacheRecords"] > 0
            checks[name] = valid
    upstream = (out / "logs/candidate-upstream.log").read_text(errors="replace")
    checks["candidate-upstream"] = results["candidate-upstream"]["passed"] and "runtime=.NET 12.0.0-dev compiled=False" in upstream
    checks["candidate-upstream"] = checks["candidate-upstream"] and all(marker in upstream for marker in (
        "UPSTREAM_PASS ResolvedFromDifferentContext cases=4", "UPSTREAM_PASS GenericVirtualMethod cycles=10"))
    mobile = helper("verify-ios-packages")
    for name, item in state["apps"].items():
        app = Path(item["app"])
        checks[name + "-managed-identity"] = all(sha(app / path) == digest for path, digest in state["managedHashes"].items())
        checks[name + "-composite-identity"] = sha(app / "regression.dylib") == state["compositeSha256"]
    candidate = args.candidate.resolve()
    checks["candidate-source"] = capture(["git", "-C", candidate / "runtime", "rev-parse", "HEAD"]) == COMMIT
    checks["candidate-source"] = checks["candidate-source"] and not capture(["git", "-C", candidate / "runtime", "status", "--porcelain", "--untracked-files=no"])
    checks["candidate-native"] = sha(state["candidateArtifact"]["libcoreclr"]) == NATIVE
    checks["candidate-native"] = checks["candidate-native"] and mobile.macho_sections(state["candidateArtifact"]["libcoreclr"]) == mobile.macho_sections(Path(state["apps"]["candidate"]["app"]) / "libcoreclr.dylib")
    simulator = json.loads((out / "simulator.json").read_text())
    devices = json.loads(capture(["xcrun", "simctl", "list", "devices", "-j"]))["devices"]
    own = [d for group in devices.values() for d in group if d["udid"] == simulator["uuid"]]
    checks["simulator-shutdown"] = len(own) == 1 and own[0]["state"] == "Shutdown"
    success = len(results) == 13 and all(checks.values())
    write(out / "verified.json", {"success": success, "candidateCases": 4, "candidateSourceAdapterTests": 2, "checks": checks, "results": results})
    if not success:
        raise RuntimeError("Regression verification failed: " + ", ".join(name for name, ok in checks.items() if not ok))
    print("PASS v2 CID regressions 4/4 + unchanged upstream adapters 2/2; native callers, CID trace controls, input identities and simulator shutdown verified", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("build", "run", "verify", "archive"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    {"build": build, "run": execute, "verify": verify, "archive": archive}[args.phase](args)


if __name__ == "__main__":
    main()
