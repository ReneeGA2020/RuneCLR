#!/usr/bin/env python3
"""Run owned debugger-free simulator callback timing brackets and retain raw evidence."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time
import uuid

APPLICATION_SHA = "e46aab12d2cd5ea56d4016b034dc65027ed11b4051bd9c776a5ddfc4ce7f66eb"
ASSESSOR_SHA = "33687721115a7c45e72e35345ecca1a44652ca650b07b8750d8cdbc92010809d"
PROFILES = (("exact-before", "best-exact", "0", "1"), ("N100", "N100", "64", "0"),
            ("N1000", "N1000", "3e8", "0"), ("exact-after", "best-exact", "0", "1"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def need(value, message):
    if not value:
        raise RuntimeError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    with Path(path).open("x", encoding="ascii") as stream:
        stream.write(json.dumps(value, indent=2) + chr(10))


def module(name, path, digest):
    need(sha(path) == digest, "Frozen timing helper changed: " + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def inventory(root):
    return {path.relative_to(root).as_posix(): sha(path) for path in sorted(root.rglob("*")) if path.is_file()}


def plan():
    return [{"profile": profile, "lane": lane, "intervalHex": interval, "derived": derived, "pair": pair, "mode": mode,
             "label": profile + "-pair" + str(pair) + "-" + mode, "warmups": 3, "sampleCount": 9}
            for profile, lane, interval, derived in PROFILES for pair in range(2)
            for mode in (("no-config", "high-budget") if pair == 0 else ("high-budget", "no-config"))]


def cap(argv):
    return subprocess.check_output([str(item) for item in argv], text=True).strip()


def command(argv, log, env=None, timeout=120):
    argv = [str(item) for item in argv]
    write(Path(str(log) + ".request.json"), {"argv": argv, "timeout": timeout})
    with log.open("x") as stream:
        process = subprocess.Popen(argv, stdout=stream, stderr=subprocess.STDOUT, env=env)
        expired = False
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            expired = True
            process.kill()
            code = process.wait()
    raw = {"argv": argv, "pid": process.pid, "exitCode": code, "timedOut": expired, "logSha256": sha(log)}
    write(Path(str(log) + ".process.json"), raw)
    need(code == 0 and not expired, "Owned simulator command failed: " + str(log))
    return raw


def blocked(name, args):
    base = Path(name).name
    if base in ("crossgen2", "clang", "clang++", "cc1", "cc1plus", "ninja", "cmake", "make", "gmake", "xcodebuild", "msbuild", "csc",
                "lldb", "lldb-server", "debugserver", "git", "codesign", "dsymutil", "Session"):
        return "compiler-debugger-or-source-audit"
    if base in ("dotnet", "corerun") and re.search(r"(?:\bbuild\b|\bmsbuild\b|csc\.dll|benchmark|BatchOverhead)", args, re.I):
        return "managed-build-or-benchmark"
    if re.search(r"(?:benchmark[^ /]*\.py|ios-batch-timing-run\.py|entry-capture\.py|compile-assessment\.py|source-proof\.py)", args):
        return "experiment-worker"
    return None


def quiet(path):
    names = cap(["ps", "-axo", "pid=,comm="])
    commands = cap(["ps", "-axo", "pid=,args="])
    parsed = {}
    for line in commands.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            parsed[int(parts[0])] = parts[1]
    rows = []
    for line in names.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        pid, name = int(parts[0]), parts[1]
        if pid == os.getpid():
            continue
        args = parsed.get(pid, "")
        rows.append({"pid": pid, "name": Path(name).name, "commandSha256": hashlib.sha256(args.encode()).hexdigest(),
                     "blockedReason": blocked(name, args)})
    result = {"passed": not any(row["blockedReason"] for row in rows), "controllerPid": os.getpid(), "processes": rows,
              "capturedUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "scope": "Compiler, debugger and recognized experiment-worker process gate; command arguments retained only as hashes."}
    write(path, result)
    need(result["passed"], "Timing requires compiler/debugger/other experiment workers to exit; preserve quiet gate evidence.")


def launch_settings(cell, nonce):
    return {"RUNECLR_TIMING_NONCE": nonce, "RUNECLR_TIMING_MODE": cell["mode"], "RUNECLR_TIMING_LANE": cell["lane"],
            "RUNECLR_TIMING_SAMPLES": "9", "RUNECLR_TIMING_HEX": cell["intervalHex"], "RUNECLR_TIMING_DERIVED": cell["derived"]}


def validate_log(log, cell, nonce, pid):
    native = (f"TIMING_NATIVE pid={pid} nonce={nonce} mode={cell['mode']} lane={cell['lane']} samples=9 "
              f"interval={cell['intervalHex']} DerivedLedger={cell['derived']} PhaseAcquireLoad=1 InterpMode=0 ReadyToRun=1")
    for marker in (native, "CORECLR_INITIALIZE_HRESULT=0x0", "CORECLR_EXECUTE_HRESULT=0x0; RUNECLR_EXIT=0"):
        need(len(re.findall("^" + re.escape(marker) + "$", log, re.M)) == 1, "Native launch/HRESULT marker differs.")
    completion = (f"MOBILE_BATCH_TIMING_COMPLETE nonce={nonce} pid={pid} lane={cell['lane']} "
                  f"mode={cell['mode']} callbacks=12")
    prefix = (r"(?:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3,6} " +
              re.escape("Session[" + str(pid) + ":") + r"\d+\] )?")
    need(len(re.findall("^" + prefix + re.escape(completion) + "$", log, re.M)) == 1, "Owned managed completion marker differs.")


def run(args):
    need(platform.system() == "Darwin", "Actual simulator timing requires the configured Mac.")
    application = module("owned_timing_application", args.application_tool, APPLICATION_SHA)
    accept = module("frozen_timing_native", args.accept_tool, application.ACCEPT_SHA)
    prepare = module("frozen_timing_pe", args.prepare_tool, application.PREPARE_SHA)
    assessor = module("strict_mobile_timing", args.assessor_tool, ASSESSOR_SHA)
    manifest = application.inputs(args.inputs)
    state, provenance = read(args.application / "state.json"), read(args.application / "timing-provenance.json")
    app = Path(state["app"])
    pe = prepare.readers()
    component = app / "RuneCLR.Abstractions.dll"
    expected = {"state": sha(args.application / "state.json"), "provenance": sha(args.application / "timing-provenance.json"),
                "manifest": sha(args.inputs / "input-manifest.json"), "driver": sha(__file__), "appTool": sha(args.application_tool),
                "assessor": sha(args.assessor_tool), "acceptTool": sha(args.accept_tool), "prepareTool": sha(args.prepare_tool)}
    need(provenance["passed"] is True and provenance["driverSha256"] == APPLICATION_SHA and
         provenance["inputManifestSha256"] == state["inputManifestSha256"] == application.INPUT_SHA and
         provenance["trustedHostRawSha256"] == state["compositeInputs"]["MobileBatchTimingProbe.dll"] == application.HOST_SHA and
         provenance["contractComponentSha256"] == sha(component) and
         pe["pe_mvid"](component)["moduleMvid"] == application.CONTRACT_MVID and
         accept.inventory(app) == state["bundleHashes"] and accept.native_platform(app / "libcoreclr.dylib") == state["native"] and
         not list(app.rglob("RuneCLR.BatchKernel.dll")), "Signed timing app provenance differs.")
    receipt = read(args.application / "matching-build.json")
    need(sha(args.application / "matching-build.json") == state["buildReceiptSha256"] and
         state["sourceNative"]["sha256"] == state["nativeSha256"] == receipt["nativeSha256"] and
         state["sourceCommit"] == receipt["commit"] == accept.COMMIT and
         state["sourceTree"] == receipt["tree"] == accept.TREE, "Matching raw/signed runtime provenance differs.")
    args.output.mkdir(parents=True, exist_ok=False)
    write(args.output / "request.json", {"schema": "runeclr.ios-batch-timing.run.v1", "driverSha256": sha(__file__),
          "application": str(args.application), "inputDirectory": str(args.inputs), "frozen": expected, "plan": plan(),
          "sourceCommit": state["sourceCommit"], "sourceTree": state["sourceTree"], "native": state["native"],
          "sourceNative": state["sourceNative"], "contractComponentSha256": provenance["contractComponentSha256"],
          "debugger": False, "comparativeTimingMeasured": False, "performanceVerified": False})
    simulator = None
    result = {"passed": False, "nativeEntryProof": False, "liveBatchPathVerified": False, "physicalDeviceVerified": False,
              "performanceVerified": False, "platform": "iossimulator.arm64", "observations": []}
    try:
        quiet(args.output / "quiet-before-setup.json")
        simulator = cap(["xcrun", "simctl", "create", "RuneCLR-DirectCallbackTiming", args.device_type, args.sim_runtime])
        write(args.output / "owned-simulator.json", {"id": simulator, "bundleId": state["bundleId"]})
        command(["xcrun", "simctl", "boot", simulator], args.output / "boot.log")
        command(["xcrun", "simctl", "bootstatus", simulator, "-b"], args.output / "bootstatus.log", timeout=180)
        command(["xcrun", "simctl", "install", simulator, app], args.output / "install.log")
        installed = Path(cap(["xcrun", "simctl", "get_app_container", simulator, state["bundleId"], "app"]))
        data = Path(cap(["xcrun", "simctl", "get_app_container", simulator, state["bundleId"], "data"]))
        before = inventory(installed)
        need(before == state["bundleHashes"], "Installed signed app differs.")
        write(args.output / "installed-before.json", before)
        plugin = data / "Documents/timing-plugin"
        plugin.mkdir(parents=True, exist_ok=False)
        for name in ("RuneCLR.BatchKernel.dll", "RuneCLR.Abstractions.dll"):
            shutil.copy2(args.inputs / "author" / name, plugin / name)
            need(sha(plugin / name) == manifest["files"]["author/" + name] and
                 prepare.il_layout(plugin / name) == {"ilOnly": True, "managedNativeRva": 0}, "Post-install raw author input differs.")
        author_before = inventory(plugin)
        write(args.output / "author-before.json", author_before)
        owners = []
        quiet(args.output / "quiet-before-window.json")
        for cell in plan():
            directory = args.output / cell["label"]
            directory.mkdir()
            quiet(directory / "quiet-before.json")
            nonce = uuid.uuid4().hex
            requested = launch_settings(cell, nonce)
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(("DOTNET_", "COMPlus_", "RUNECLR_", "SIMCTL_CHILD_", "DYLD_", "LD_"))}
            env.update({"SIMCTL_CHILD_" + key: value for key, value in requested.items()})
            argv = ["xcrun", "simctl", "launch", "--console", "--terminate-running-process", simulator, state["bundleId"]]
            write(directory / "request.json", dict(cell, argv=argv, settings=requested, nonce=nonce, debugger=False, timeout=args.timeout))
            raw = command(argv, directory / "native.log", env=env, timeout=args.timeout)
            quiet(directory / "quiet-after.json")
            target = data / ("Documents/timing-" + nonce + ".json")
            shutil.copy2(target, directory / "receipt.json")
            actual = read(directory / "receipt.json")
            pid = actual["processId"]
            validate_log((directory / "native.log").read_text(), cell, nonce, pid)
            reviewed = assessor.review(actual, cell["mode"], cell["lane"], nonce, pid, 9, "iossimulator.arm64", provenance["contractComponentSha256"])
            owners.append((pid, nonce))
            observation = dict(reviewed, profile=cell["profile"], pair=cell["pair"], label=cell["label"],
                               receiptSha256=sha(directory / "receipt.json"), nativeLogSha256=sha(directory / "native.log"), consoleProcess=raw)
            write(directory / "results.json", observation)
            result["observations"].append(observation)
            print(cell["label"] + ": owned callback timing/ledger observation PASS", flush=True)
        quiet(args.output / "quiet-after-window.json")
        need(len({pid for pid, nonce in owners}) == len({nonce for pid, nonce in owners}) == 16, "Timing brackets require sixteen fresh process/nonce pairs.")
        after, author_after = inventory(installed), inventory(plugin)
        write(args.output / "installed-after.json", after)
        write(args.output / "author-after.json", author_after)
        need(before == after and author_before == author_after and application.inputs(args.inputs) == manifest and
             inventory(app) == state["bundleHashes"] and sha(args.application / "state.json") == expected["state"] and
             sha(args.application / "timing-provenance.json") == expected["provenance"] and sha(__file__) == expected["driver"],
             "Timing-window input/application identity changed.")
        result.update(passed=True, processes=16, callbacks=192, measuredSamples=144, collections=16,
                      comparativeTimingMeasured=True, callbackTimingSimulatorObserved=True, debuggerFreeProcessGatesPassed=True)
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        if simulator is not None:
            try:
                cleanup = subprocess.run(["xcrun", "simctl", "shutdown", simulator], capture_output=True, text=True)
                devices = json.loads(cap(["xcrun", "simctl", "list", "devices", "--json"]))
                states = [item["state"] for group in devices["devices"].values() for item in group if item["udid"] == simulator]
                stopped = states == ["Shutdown"]
                write(args.output / "cleanup.json", {"simulator": simulator, "exitCode": cleanup.returncode, "stdout": cleanup.stdout,
                      "stderr": cleanup.stderr, "observedStates": states, "shutdownVerified": stopped})
                result["cleanupSucceeded"] = stopped
            except Exception as error:
                result["cleanupSucceeded"] = False
                result["cleanupError"] = str(error)
            result["passed"] = result["passed"] and result["cleanupSucceeded"]
        result["endedUtc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        write(args.output / "results.json", result)
        print(json.dumps({key: value for key, value in result.items() if key != "observations"}, indent=2), flush=True)
    need(result["passed"], "Actual timing run or owned simulator cleanup failed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("plan", "run"))
    parser.add_argument("--output", type=Path, required=True)
    for name in ("application", "inputs", "application-tool", "accept-tool", "prepare-tool", "assessor-tool"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--device-type", default="com.apple.CoreSimulator.SimDeviceType.iPhone-16")
    parser.add_argument("--sim-runtime", default="com.apple.CoreSimulator.SimRuntime.iOS-27-0")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    if args.phase == "plan":
        args.output.mkdir(parents=True, exist_ok=False)
        write(args.output / "results.json", {"passed": True, "driverSha256": sha(__file__), "plan": plan(), "processesPlanned": 16,
              "applicationBuilt": False, "timingExecuted": False, "performanceVerified": False})
        print("PLAN PASS: sixteen independent callback timing processes; no build or launch")
    else:
        for name in ("application", "inputs", "application_tool", "accept_tool", "prepare_tool", "assessor_tool"):
            need(getattr(args, name) is not None, "Missing --" + name.replace("_", "-") + ".")
        run(args)


if __name__ == "__main__":
    main()
