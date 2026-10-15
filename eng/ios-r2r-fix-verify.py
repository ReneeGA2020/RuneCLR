#!/usr/bin/env python3
"""Verify a private CID lifetime fix against preserved source iOS simulator inputs."""
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
import tarfile

BASE = "0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + "\n")


def capture(arguments):
    return subprocess.check_output([str(a) for a in arguments], text=True).strip()


def logged(arguments, path, env=None, check=True, timeout=180):
    with Path(path).open("w") as stream:
        try:
            status = subprocess.run([str(a) for a in arguments], stdout=stream,
                                    stderr=subprocess.STDOUT, env=env, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            stream.write("\nCANDIDATE_TIMEOUT\n")
            status = 124
    if check and status != 0:
        raise RuntimeError(f"Command returned {status}; see {path}")
    return status


def helper(name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_app(original, target, native, logs, sections):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(original, target)
    shutil.copy2(native, target / "libcoreclr.dylib")
    logged(["codesign", "--force", "--sign", "-", target / "libcoreclr.dylib"], logs / "native-sign.log")
    logged(["codesign", "--force", "--sign", "-", target], logs / "app-sign.log")
    plist = plistlib.loads((original / "Info.plist").read_bytes())
    managed = {str(p.relative_to(original)): sha(p) for p in original.rglob("*.dll")}
    composites = {p.name: sha(p) for p in original.glob("*.dylib") if p.name != "libcoreclr.dylib"}
    if any(sha(target / name) != value for name, value in {**managed, **composites}.items()):
        raise RuntimeError("Managed inputs or trusted native composites changed.")
    executable = plist["CFBundleExecutable"]
    if sections(original / executable) != sections(target / executable):
        raise RuntimeError("Native wrapper code/data changed during signing.")
    if sections(native) != sections(target / "libcoreclr.dylib"):
        raise RuntimeError("Candidate code/data changed during signing.")
    return {"app": str(target), "bundle": plist["CFBundleIdentifier"],
            "managedHashes": managed, "compositeHashes": composites,
            "wrapperSections": sections(target / executable),
            "candidateSections": sections(target / "libcoreclr.dylib"),
            "signedNativeSha256": sha(target / "libcoreclr.dylib")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "candidate", "minimal", "controlled", "packages", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    source = json.loads((args.candidate / "logs/source.json").read_text())
    artifact = json.loads((args.candidate / "logs/artifacts.json").read_text())
    native = Path(artifact["libcoreclr"])
    runtime = args.candidate / "runtime"
    if source["base"] != BASE or source["commit"] != capture(["git", "-C", runtime, "rev-parse", "HEAD"]):
        raise RuntimeError("Candidate source identity does not match the pinned source/commit.")
    if capture(["git", "-C", runtime, "status", "--porcelain", "--untracked-files=no"]):
        raise RuntimeError("Candidate worktree must have no tracked changes.")
    if sha(native) != artifact["libcoreclrSha256"]:
        raise RuntimeError("Candidate native artifact does not match its build receipt.")
    mobile = helper("verify-ios-packages")
    minimal = helper("ios-r2r-minimal")
    full = args.root / "preview6-experiment/pinned-debug-harness/app/RuneCLRPinnedHarness.app"
    originals = {"full": full, "minimal": args.minimal / "r2r/Probe.app",
                 "controlled": args.controlled / "app/Packages.app"}
    layouts = {}
    for name, app in originals.items():
        logs = out / name
        logs.mkdir()
        layouts[name] = copy_app(app, logs / app.name, native, logs, mobile.macho_sections)
    write(out / "identity.json", {"source": source, "artifact": artifact, "apps": layouts,
                                 "fixtureReceipt": json.loads((args.packages / "fixtures.json").read_text())})
    sim = capture(["xcrun", "simctl", "create", "RuneCLR-CID-Fix-Candidate",
                   "com.apple.CoreSimulator.SimDeviceType.iPhone-17", "com.apple.CoreSimulator.SimRuntime.iOS-27-0"])
    write(out / "simulator.json", {"uuid": sim})
    cases = [("original-full", full, "full", {}),
             ("candidate-full", Path(layouts["full"]["app"]), "full", {}),
             ("candidate-two-ticks", Path(layouts["minimal"]["app"]), "minimal",
              {"PROBE_MODE": "collect", "PROBE_CYCLES": "20", "PROBE_TICKS": "2"}),
             ("candidate-three-ticks", Path(layouts["minimal"]["app"]), "minimal",
              {"PROBE_MODE": "collect", "PROBE_CYCLES": "20", "PROBE_TICKS": "3"}),
             ("candidate-controlled", Path(layouts["controlled"]["app"]), "controlled", {})]
    results = {}
    try:
        logged(["xcrun", "simctl", "boot", sim], out / "boot-command.log")
        logged(["xcrun", "simctl", "bootstatus", sim, "-b"], out / "boot.log")
        for name, app, kind, settings in cases:
            logged(["xcrun", "simctl", "install", sim, app], out / (name + "-install.log"))
            bundle = layouts[kind]["bundle"]
            installed = Path(capture(["xcrun", "simctl", "get_app_container", sim, bundle, "app"]))
            expected_bundle = mobile.tree(app)
            if mobile.tree(installed) != expected_bundle:
                raise RuntimeError("Installed bundle does not match prepared app.")
            if kind == "controlled":
                data = Path(capture(["xcrun", "simctl", "get_app_container", sim, bundle, "data"]))
                payload = data / "Documents/controlled"
                if payload.exists():
                    raise RuntimeError("A fresh candidate app must not inherit previous payloads.")
                shutil.copytree(args.packages, payload)
                if mobile.tree(args.packages) != mobile.tree(payload):
                    raise RuntimeError("Copied controlled fixtures differ from the operator inputs.")
            env = dict(os.environ)
            for key in list(env):
                if key.startswith(("SIMCTL_CHILD_DOTNET_", "SIMCTL_CHILD_COMPlus_", "SIMCTL_CHILD_PROBE_")):
                    del env[key]
            env.update({"SIMCTL_CHILD_" + key: value for key, value in settings.items()})
            log = out / (name + ".log")
            status = logged(["xcrun", "simctl", "launch", "--console", sim, bundle], log,
                            env=env, check=False, timeout=240)
            text = log.read_text(errors="replace")
            fault = "Got a SIGSEGV while executing native code." in text
            normal = (status == 0 and "RUNECLR_EXIT=0" in text and not fault
                      and "Assert failure" not in text and "DynamicCodeCompiled=False" in text
                      and ".NET 12.0.0-dev" in text)
            callback_dumps = text.count("Compiled method: .RuneCLR.TestMaps.CounterMap:OnTick")
            passed = normal and "21/21 tests passed" in text and callback_dumps > 0
            details = {"counterMapTickDumps": callback_dumps}
            if name == "original-full":
                passed = status != 124 and fault and "CORECLR_INITIALIZE_HRESULT=0x0" in text and "RUNECLR_EXIT=0" not in text
            elif kind == "minimal":
                details = minimal.result(log, 20, int(settings["PROBE_TICKS"]), "collect", "none", status)
                passed = details["passed"] and ".NET 12.0.0-dev" in text and "compiled=False" in text
            elif kind == "controlled":
                dumps = {method: text.count("Compiled method: ." + method) for method in
                         ("GameScript:OnStart", "GameScript:OnTick", "GameScript:OnStop", "SharedHelper:Read", "GenericCounter`1")}
                details = {"interpreterDumps": dumps}
                passed = normal and "15/15 package execution tests passed" in text and all(dumps.values())
            unchanged = mobile.tree(installed) == expected_bundle
            results[name] = {"passed": bool(passed and unchanged), "launcherExit": status,
                             "nativeSigsegv": fault, "bundleUnchanged": unchanged,
                             "logSha256": sha(log), "details": details}
            write(out / "results.json", {"runs": results, "success": len(results) == len(cases) and all(r["passed"] for r in results.values())})
            print(name + ": " + json.dumps(results[name]), flush=True)
            logged(["xcrun", "simctl", "terminate", sim, bundle], out / (name + "-terminate.log"), check=False)
    finally:
        shutdown = logged(["xcrun", "simctl", "shutdown", sim], out / "shutdown.log", check=False)
        write(out / "simulator.json", {"uuid": sim, "shutdownExit": shutdown})
    with tarfile.open(out / "evidence.tar.gz", "w:gz") as archive:
        for path in sorted(out.rglob("*")):
            if path.is_file() and path.suffix in (".json", ".log"):
                archive.add(path, arcname=str(path.relative_to(out)))
        for path in (Path(__file__), args.candidate / "logs/runtime.patch"):
            archive.add(path, arcname=path.name)
    print("Candidate verification archive SHA256=" + sha(out / "evidence.tar.gz"), flush=True)
    return 0 if len(results) == len(cases) and all(r["passed"] for r in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
