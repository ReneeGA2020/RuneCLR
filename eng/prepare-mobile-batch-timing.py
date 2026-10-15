#!/usr/bin/env python3
"""Prepare portable direct-callback timing inputs; validate a small functional sanity, not a benchmark."""
import ast
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "artifacts/budget-batching/benchmark-inputs-20261014-attempt1"
AUTHOR = "d743ecb6ba897366a276ab700e79a42f3885ba2eaf69d1713bb086346f2fd09e"
CONTRACT = "ebfe72469b640b63991189123971beadbf9c3fe74d303a9b7ce66f87596a807b"
CONTRACT_IDENTITY = "RuneCLR.Abstractions, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null"
CONTRACT_MVID = "92efbbd4-8ae3-4686-824b-bafe67f2dd69"
COMMIT = "d0da7dfafc0c4894ae7aa5332ee171f023a0a88e"
LIMIT, DISPATCHES, CHECKSUM = 1_000_000_000_000, 2_100_016, 12_749_776
UNVERIFIED = ("nativeEntryProof", "liveBatchPathVerified", "mobileExecutionVerified",
              "physicalDeviceVerified", "performanceVerified")
LANES = ("no-config", "best-exact", "N100", "N1000")
TIMING_SCOPE = "Stopwatch timestamps surround only the direct frozen Kernel.Execute delegate invocation."


def settings(lane):
    need(lane in LANES, "Unknown timing lane.")
    return {"DOTNET_InterpMode": "0", "DOTNET_RuneCLRInterpretCollectible": "0", "DOTNET_ReadyToRun": "1",
            "DOTNET_TieredCompilation": "0", "DOTNET_MULTILEVEL_LOOKUP": "0", "DOTNET_RuneCLRPhaseAcquireLoad": "1",
            "DOTNET_RuneCLRDerivedLedger": "1" if lane == "best-exact" else "0",
            "DOTNET_RuneCLRBatchInterval": {"no-config": "0", "best-exact": "0", "N100": "64", "N1000": "3e8"}[lane]}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    with Path(path).open("x", encoding="ascii") as stream:
        json.dump(value, stream, indent=2)
        stream.write(chr(10))


def unchanged(files):
    for path, expected in files.items():
        need(sha(path) == expected, "Frozen input changed: " + path)


def owned(command, directory, env, prefix, timeout):
    with (directory / (prefix + ".stdout")).open("xb") as stdout, (directory / (prefix + ".stderr")).open("xb") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
        timed_out = False
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            code = process.wait()
    result = {"argv": command, "pid": process.pid, "exitCode": code, "timedOut": timed_out,
              "stdoutSha256": sha(directory / (prefix + ".stdout")), "stderrSha256": sha(directory / (prefix + ".stderr"))}
    save(directory / (prefix + ".process.json"), result)
    need(code == 0 and not timed_out, "Owned process failed: " + prefix)
    return result


def environment():
    return {k: v for k, v in os.environ.items() if not k.startswith(("DOTNET_", "COMPlus_", "RUNECLR_"))}


def source_controls(text):
    sequence = chr(10).join(("                long started = Stopwatch.GetTimestamp();",
                            "                long value = callback(Iterations);",
                            "                long finished = Stopwatch.GetTimestamp();"))
    need(text.count(sequence) == 1 and text.count("Stopwatch.GetTimestamp()") == 2, "Direct callback-only timestamp sequence differs.")
    need(all(word not in text for word in ("ProcessorAffinity", "Marshal.ReadByte", "GetFunctionPointer", "OperatingSystem.IsWindows")),
         "Portable variant contains desktop-specific observation.")
    need("[MethodImpl(MethodImplOptions.NoInlining)]" + chr(10) + "    private static Frame InvokeFrame" in text and
         "Collect(frame.Context);" in text and "return new(weak, initial, rows, final, retiredRejections);" in text,
         "Post-frame scalar collection ownership differs.")


def prepare(args):
    original, sdk, output = args.original.resolve(), args.sdk.resolve(), args.output.resolve()
    need(sha(original / "author/RuneCLR.BatchKernel.dll") == AUTHOR, "Accepted original author differs.")
    need(sha(original / "author/RuneCLR.Abstractions.dll") == sha(original / "host/RuneCLR.Abstractions.dll") == CONTRACT,
         "Accepted shared contract differs.")
    calibration = read(original / "baseline-smoke.json")
    need(calibration["passed"] is True and calibration["callbackChecksum"] == CHECKSUM and
         calibration["callbackDispatches"] == DISPATCHES, "Accepted arithmetic calibration differs.")
    project = ROOT / "eng/mobile-batch-timing-probe/MobileBatchTimingProbe.csproj"
    source = ROOT / "eng/mobile-batch-timing-probe/Entry.cs"
    source_controls(source.read_text())
    sdk_directory = sdk.parent / "sdk/11.0.100-rc.1.26425.128"
    references = sdk.parent / "packs/Microsoft.NETCore.App.Ref/11.0.0-rc.1.26425.128/ref/net11.0"
    inputs = [Path(__file__).resolve(), project, source, ROOT / "Directory.Build.props", ROOT / "global.json", sdk,
              sdk_directory / "Roslyn/bincore/csc.dll", sdk_directory / "Roslyn/bincore/csc.deps.json",
              sdk_directory / "Roslyn/bincore/csc.runtimeconfig.json", original / "baseline-smoke.json",
              original / "baseline-smoke.stdout", original / "author/RuneCLR.BatchKernel.dll",
              original / "author/RuneCLR.Abstractions.dll", original / "host/RuneCLR.Abstractions.dll"]
    old_source, old_driver = ROOT / "eng/mobile-batch-kernel-probe/Entry.cs", ROOT / "eng/prepare-mobile-batch-kernel.py"
    need(sha(old_source) == "842417b258973cb932135355332e8a809fcc554d53ef79bfcf2779415204bb74" and
         sha(old_driver) == "e7364d077c88e13f6613f398baf9975c7a5eaed96f290f7468a1f66ec3bba4e8", "Original frozen kernel tools changed.")
    inputs += [old_source, old_driver]
    inputs += sorted(references.glob("*.dll"))
    need(references.is_dir() and len(inputs) > 100, "Pinned RC1 compiler/reference pack missing.")
    frozen = {str(path): sha(path) for path in inputs}
    output.mkdir(parents=True, exist_ok=False)
    (output / "source").mkdir()
    (output / "source/Entry.cs").write_bytes(source.read_bytes())
    command = [str(sdk), "build", str(project), "-c", "Release", "--artifacts-path", str(output / "build-obj"),
               "-o", str(output / "host"), "-p:MobileBatchTimingSource=" + str(output / "source/Entry.cs"),
               "-p:MobileBatchTimingContractPath=" + str(original / "host/RuneCLR.Abstractions.dll"),
               "-p:UseSharedCompilation=false", "-nodeReuse:false"]
    save(output / "request.json", {"schema": "runeclr.mobile-batch-timing.prepare.v1", "driverSha256": sha(__file__),
         "frozenInputs": frozen, "generatedSourceSha256": sha(output / "source/Entry.cs"), "argv": command,
         "signature": "public static int MobileBatchTimingProbe.Entry.Run(string[] args)",
         "authorCompilationPerformed": False, "runtimeBuildPerformed": False, "mobileExecutionVerified": False})
    env = environment()
    env["MSBUILDDISABLENODEREUSE"] = "1"
    env["DOTNET_CLI_UI_LANGUAGE"] = "en-US"
    process = owned(command, output, env, "build", 120)
    unchanged(frozen)
    text = (output / "build.stdout").read_text(encoding="utf-8-sig")
    need("0 Warning(s)" in text and "0 Error(s)" in text, "Trusted adapter build must have no warnings/errors.")
    need(sha(output / "host/RuneCLR.Abstractions.dll") == CONTRACT, "Built shared contract bytes differ.")
    need(not (output / "host/RuneCLR.BatchKernel.dll").exists(), "Author leaked into trusted host output.")
    (output / "author").mkdir()
    for name in ("RuneCLR.BatchKernel.dll", "RuneCLR.Abstractions.dll"):
        (output / "author" / name).write_bytes((original / "author" / name).read_bytes())
    files = {path.relative_to(output).as_posix(): sha(path)
             for subdir in ("host", "author", "source") for path in sorted((output / subdir).iterdir()) if path.is_file()}
    save(output / "input-manifest.json", {"schema": "runeclr.mobile-batch-timing.inputs.v1", "files": files,
         "assembly": "MobileBatchTimingProbe", "type": "MobileBatchTimingProbe.Entry", "method": "Run",
         "arguments": ["absolute author DLL", "no-config|high-budget", "no-config|best-exact|N100|N1000", "32-hex nonce", "sample count 1..100", "fresh receipt path"],
         "laneSettings": {lane: settings(lane) for lane in LANES}, "timingScope": TIMING_SCOPE,
         "warmups": 3, "iterations": 100000, "expectedChecksum": CHECKSUM, "expectedDispatchDelta": DISPATCHES,
         "authorSha256": AUTHOR, "contractSha256": CONTRACT, "contractIdentity": CONTRACT_IDENTITY, "contractMvid": CONTRACT_MVID,
         "contractBinding": "Frozen raw contract retained beside author; trusted loaded default-context component has exact identity/MVID; mobile R2R byte provenance requires an independent layout receipt.",
         "performanceVerified": False, "nativeEntryProof": False})
    archive = output / "mobile-batch-timing-inputs.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as zipped:
        for name in (*files, "input-manifest.json", "request.json"):
            zipped.write(output / name, name)
    save(output / "results.json", {"prepared": True, "compiledTrustedAdapter": True, "authorAndContractBytesUnchanged": True,
         "buildPid": process["pid"], "zipSha256": sha(archive), "inputManifestSha256": sha(output / "input-manifest.json"),
         "runtimeBuildPerformed": False, "mobileExecutionVerified": False, "performanceVerified": False})
    print(json.dumps(read(output / "results.json"), indent=2))


def snapshot(count):
    return {"Remaining": LIMIT - count, "Executed": count, "Exhausted": False, "IsTerminated": False,
            "Reason": 0, "Phase": 0, "CleanupRemaining": 4096, "CleanupExecuted": 0}


def exact(value, expected, message):
    if isinstance(expected, dict):
        need(type(value) is dict and value.keys() == expected.keys(), message)
        for key, item in expected.items():
            exact(value[key], item, message)
    else:
        need(type(value) is type(expected) and value == expected, message)


def review(receipt, mode, lane, nonce, pid, samples=1, architecture=None):
    need(lane in LANES and mode in ("no-config", "high-budget") and not (mode == "high-budget" and lane == "no-config"),
         "Requested lane/mode combination differs.")
    need(receipt["schema"] == "runeclr.mobile-batch-timing.observation.v1" and receipt["passed"] is True and
         type(receipt["processId"]) is int and receipt["processId"] == pid and receipt["nonce"] == nonce and receipt["mode"] == mode and
         receipt["lane"] == lane, "Owned receipt binding differs.")
    exact(receipt["requestedSettings"], settings(lane), "Requested lane environment differs.")
    need(receipt["runtime"].startswith(".NET 12.") and receipt["architecture"] in ("X64", "Arm64"), "Runtime/architecture differs.")
    need(architecture is None or receipt["architecture"] == architecture, "Independently requested architecture differs.")
    need(receipt["authorHash"] == AUTHOR and receipt["contractHash"] == CONTRACT and receipt["iterations"] == 100000 and
         receipt["expectedChecksum"] == CHECKSUM and receipt["expectedDispatchDelta"] == DISPATCHES, "Frozen callback contract differs.")
    for key in ("iterations", "expectedChecksum", "expectedDispatchDelta", "warmups", "sampleCount", "cleanupLimit", "RetiredGetterRejections"):
        need(type(receipt[key]) is int, "Scalar integer type differs: " + key)
    need(receipt["contractIdentity"] == CONTRACT_IDENTITY and receipt["contractMvid"] == CONTRACT_MVID,
         "Loaded trusted shared contract identity/MVID differs.")
    component_hash = receipt["loadedContractComponentHash"]
    need(component_hash is None or type(component_hash) is str and len(component_hash) == 64 and
         all(c in "0123456789abcdef" for c in component_hash), "Loaded contract component hash format differs.")
    need(receipt["warmups"] == 3 and receipt["sampleCount"] == samples and len(receipt["Rows"]) == samples + 3 and
         receipt["collected"] is True, "Callback/collection count differs.")
    need(all(receipt[key] is False for key in UNVERIFIED), "Observation overclaims unperformed evidence.")
    exact(receipt["Capabilities"], {"policyVersion": 1, "terminalVersion": 1, "finalizerVersion": 1, "privateBridge": True},
          "Private native capability acknowledgement differs.")
    frequency = receipt["stopwatchFrequency"]
    need(type(frequency) is int and frequency > 0 and type(receipt["stopwatchIsHighResolution"]) is bool and
         receipt["callbackTimingObserved"] is True and receipt["timingScope"] == TIMING_SCOPE, "Callback timing contract differs.")
    budget = mode == "high-budget"
    exact(receipt["budgetLimit"], LIMIT if budget else None, "Budget limit type/value differs.")
    need(receipt["cleanupLimit"] == 4096 and
         receipt["RetiredGetterRejections"] == (8 if budget else 0), "Budget retirement acknowledgement differs.")
    exact(receipt["Initial"], snapshot(0) if budget else None, "Initial ledger differs.")
    exact(receipt["Final"], snapshot(DISPATCHES * (samples + 3)) if budget else None, "Final ledger differs.")
    previous = -1
    for index, row in enumerate(receipt["Rows"]):
        fields = ("Index", "Warmup", "Checksum", "Before", "After", "DispatchDelta")
        need(set(row) == set(fields) | {"StartedTimestamp", "FinishedTimestamp", "ElapsedTicks", "Seconds"}, "Callback row shape differs.")
        exact({key: row[key] for key in fields},
              {"Index": index, "Warmup": index < 3, "Checksum": CHECKSUM,
               "Before": snapshot(index * DISPATCHES) if budget else None,
               "After": snapshot((index + 1) * DISPATCHES) if budget else None,
               "DispatchDelta": DISPATCHES if budget else None}, "Exact callback row differs.")
        start, finish, ticks, seconds = (row[key] for key in ("StartedTimestamp", "FinishedTimestamp", "ElapsedTicks", "Seconds"))
        need(all(type(value) is int for value in (start, finish, ticks)) and start >= 0 and start >= previous and
             finish > start and ticks == finish - start and ticks > 0, "Monotonic raw callback ticks differ.")
        need(type(seconds) in (int, float) and math.isfinite(seconds) and seconds > 0 and
             math.isclose(seconds, ticks / frequency, rel_tol=1e-12, abs_tol=0.0), "Callback tick/frequency conversion differs.")
        previous = finish


def runtime_inputs(build):
    result, layout = read(build / "build-result.json"), read(build / "layout-receipt.json")
    need(result["exitCode"] == 0 and layout["passed"] is True and layout["configuration"] == "Release" and
         result["candidateCommit"] == layout["candidateCommit"] == COMMIT and
         layout["buildRequestSha256"] == sha(build / "request.json") and
         layout["buildResultSha256"] == sha(build / "build-result.json"), "Private batch Release build receipt chain differs.")
    source = Path(layout["runtime"])
    need(subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() == COMMIT and
         not subprocess.check_output(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"], text=True).strip(),
         "Built runtime source commit/clean tree differs.")
    frozen = {str(build / name): sha(build / name) for name in ("request.json", "build-result.json", "layout-receipt.json")}
    for name, expected in result["sourceHashes"].items():
        need(sha(source / name) == sha(build / "source" / name) == expected, "Built runtime source differs: " + name)
        frozen[str(source / name)] = expected
        frozen[str(build / "source" / name)] = expected
    for name, expected in layout["allLayoutHashes"].items():
        frozen[str(build / "layout" / name)] = expected
    unchanged(frozen)
    return frozen


def windows_check(args):
    prepared, build, output = args.prepared.resolve(), args.build.resolve(), args.output.resolve()
    request, manifest = read(prepared / "request.json"), read(prepared / "input-manifest.json")
    unchanged(request["frozenInputs"])
    frozen = runtime_inputs(build)
    frozen.update({str(prepared / name): expected for name, expected in manifest["files"].items()})
    frozen[str(prepared / "input-manifest.json")] = sha(prepared / "input-manifest.json")
    unchanged(frozen)
    output.mkdir(parents=True, exist_ok=False)
    lane = "N1000"
    configured = settings(lane)
    env = environment()
    env.update(configured)
    save(output / "request.json", {"driverSha256": sha(__file__), "inputManifestSha256": sha(prepared / "input-manifest.json"),
         "privateRuntimeCommit": COMMIT, "frozenInputs": frozen, "settings": configured, "sampleCount": 1, "lane": lane,
         "callbackTimingObserved": True, "comparativePerformanceMeasured": False})
    for mode in ("no-config", "high-budget"):
        nonce, receipt_path = uuid.uuid4().hex, output / (mode + ".receipt.json")
        command = [str(build / "layout/dotnet.exe"), "exec", "--fx-version", "12.0.0",
                   str(prepared / "host/MobileBatchTimingProbe.dll"), str(prepared / "author/RuneCLR.BatchKernel.dll"),
                   mode, lane, nonce, "1", str(receipt_path)]
        process = owned(command, output, env, mode, 45)
        receipt = read(receipt_path)
        review(receipt, mode, lane, nonce, process["pid"], architecture="X64")
        need(receipt["loadedContractComponentHash"] == CONTRACT, "Windows raw trusted contract component differs.")
        save(output / (mode + ".command.json"), dict(process, settings=configured, mode=mode, lane=lane, nonce=nonce, sampleCount=1))
        marker = "MOBILE_BATCH_TIMING_COMPLETE nonce=" + nonce + " pid=" + str(process["pid"]) + " lane=" + lane + " mode=" + mode + " callbacks=4"
        need((output / (mode + ".stdout")).read_text(encoding="utf-8-sig").splitlines().count(marker) == 1, "Owned completion marker differs.")
        print(mode + ": callback-only timestamp/ledger checks and post-frame collection PASS", flush=True)
    unchanged(frozen)
    unchanged(request["frozenInputs"])
    save(output / "results.json", {"passed": True, "processes": 2, "callbacks": 8, "collections": 2,
         "interval": 1000, "privateRuntimeCommit": COMMIT, "authorAndContractBytesUnchanged": True,
         "nativeEntryProof": False, "liveBatchPathVerified": False, "mobileExecutionVerified": False,
         "callbackTimingObserved": True, "comparativePerformanceMeasured": False, "performanceVerified": False,
         "scope": "Small timestamp and functional sanity only; raw callback values are not a desktop performance rerun or mobile performance evidence."})
    print(json.dumps(read(output / "results.json"), indent=2))


def controls(args):
    accepted, output = args.accepted.resolve(), args.output.resolve()
    request = read(accepted / "request.json")
    need(request["driverSha256"] == sha(__file__) and request["lane"] == "N1000", "Frozen accepted sanity driver/lane differs.")
    unchanged(request["frozenInputs"])
    output.mkdir(parents=True, exist_ok=False)
    rejected, synthetic = [], 0
    for mode in ("no-config", "high-budget"):
        raw = read(accepted / (mode + ".command.json"))
        need(raw["exitCode"] == 0 and raw["timedOut"] is False and raw["sampleCount"] == 1 and raw["settings"] == settings("N1000"),
             "Accepted actual process binding differs.")
        for suffix in ("stdout", "stderr"):
            need(sha(accepted / (mode + "." + suffix)) == raw[suffix + "Sha256"], "Accepted raw process stream differs.")
        receipt = read(accepted / (mode + ".receipt.json"))
        review(receipt, mode, "N1000", raw["nonce"], raw["pid"], architecture="X64")
        for architecture in ("X64", "Arm64"):
            for lane in LANES:
                if mode == "high-budget" and lane == "no-config":
                    continue
                adapted = copy.deepcopy(receipt)
                adapted.update(lane=lane, requestedSettings=settings(lane), architecture=architecture)
                review(adapted, mode, lane, raw["nonce"], raw["pid"], architecture=architecture)
                synthetic += 1
        row = receipt["Rows"][3]
        edits = [(["nonce"], "0" * 32), (["processId"], True), (["lane"], "best-exact"), (["authorHash"], "0" * 64),
                 (["contractMvid"], "0" * 36), (["contractIdentity"], "wrong"), (["loadedContractComponentHash"], "garbage"),
                 (["collected"], False), (["sampleCount"], True), (["warmups"], 2), (["expectedChecksum"], float(CHECKSUM)),
                 (["Capabilities", "policyVersion"], True), (["RetiredGetterRejections"], True),
                 (["nativeEntryProof"], True), (["liveBatchPathVerified"], True), (["mobileExecutionVerified"], True),
                 (["physicalDeviceVerified"], True), (["performanceVerified"], True), (["callbackTimingObserved"], 1),
                 (["requestedSettings", "DOTNET_RuneCLRDerivedLedger"], "1"),
                 (["requestedSettings", "DOTNET_RuneCLRBatchInterval"], "1000"),
                 (["stopwatchFrequency"], 0), (["stopwatchFrequency"], True), (["stopwatchFrequency"], float(receipt["stopwatchFrequency"])),
                 (["stopwatchIsHighResolution"], 1), (["timingScope"], "process startup"),
                 (["Rows", 3, "Checksum"], 1), (["Rows", 3, "Warmup"], True), (["Rows", 3, "Index"], 0),
                 (["Rows", 3, "StartedTimestamp"], row["FinishedTimestamp"]),
                 (["Rows", 3, "FinishedTimestamp"], row["StartedTimestamp"]), (["Rows", 3, "StartedTimestamp"], -1),
                 (["Rows", 3, "ElapsedTicks"], row["ElapsedTicks"] + 1), (["Rows", 3, "ElapsedTicks"], float(row["ElapsedTicks"])),
                 (["Rows", 3, "Seconds"], 0), (["Rows", 3, "Seconds"], -1), (["Rows", 3, "Seconds"], float("nan")),
                 (["Rows", 3, "Seconds"], float("inf")), (["Rows", 3, "Seconds"], "wrong"),
                 (["Rows", 3, "Seconds"], row["Seconds"] * 1.1)]
        if mode == "high-budget":
            edits += [(["Rows", 3, "After", "Executed"], 0), (["Rows", 3, "DispatchDelta"], DISPATCHES - 1),
                      (["Rows", 3, "Before", "Exhausted"], 0), (["Rows", 3, "After", "Reason"], False),
                      (["Initial", "Executed"], False), (["Final", "CleanupExecuted"], 1),
                      (["Final", "CleanupRemaining"], 4095), (["RetiredGetterRejections"], 7)]
        else:
            edits += [(["Initial"], snapshot(0)), (["Rows", 3, "DispatchDelta"], DISPATCHES), (["Final"], snapshot(4 * DISPATCHES))]
        for keys, value in edits:
            changed = copy.deepcopy(receipt)
            target = changed
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = value
            try:
                review(changed, mode, "N1000", raw["nonce"], raw["pid"], architecture="X64")
            except (RuntimeError, KeyError, TypeError, ValueError):
                rejected.append({"mode": mode, "path": keys, "replacementType": type(value).__name__})
                continue
            raise RuntimeError("Corrupted timing receipt accepted: " + repr(keys))
    source = (ROOT / "eng/mobile-batch-timing-probe/Entry.cs").read_text()
    source_controls(source)
    source_mutations = (source.replace("long value = callback(Iterations);", "GC.Collect(); long value = callback(Iterations);"),
                        source.replace("long finished = Stopwatch.GetTimestamp();", "long finished = started;"),
                        source.replace("private static Frame InvokeFrame", "private static Frame InlineFrame"),
                        source + chr(10) + "// Stopwatch.GetTimestamp()", source + chr(10) + "// ProcessorAffinity")
    source_rejections = 0
    for changed in source_mutations:
        try:
            source_controls(changed)
        except RuntimeError:
            source_rejections += 1
            continue
        raise RuntimeError("Changed direct timing scope accepted.")
    ast.parse(Path(__file__).read_text(), feature_version=(3, 9))
    unchanged(request["frozenInputs"])
    save(output / "results.json", {"passed": True, "acceptedSanityResultSha256": sha(accepted / "results.json"),
         "driverSha256": sha(__file__), "actualReceiptsReplayed": 2, "actualCallbacksReplayed": 8,
         "syntheticLaneArchitectureChecks": synthetic, "syntheticChecksAreNotRuns": True,
         "receiptMutantsRejected": len(rejected), "rejected": rejected, "sourceMutantsRejected": source_rejections,
         "python39Syntax": True, "nativeEntryProof": False, "mobileExecutionVerified": False, "performanceVerified": False})
    print(json.dumps({key: value for key, value in read(output / "results.json").items() if key != "rejected"}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "windows-check", "controls"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--original", type=Path, default=ORIGINAL)
    parser.add_argument("--sdk", type=Path, default=ROOT / "artifacts/toolchains/dotnet-11-rc1/dotnet.exe")
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--accepted", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args)
    elif args.mode == "windows-check":
        need(args.prepared is not None and args.build is not None, "--prepared and --build required.")
        windows_check(args)
    else:
        need(args.accepted is not None, "--accepted required.")
        controls(args)


if __name__ == "__main__":
    main()
