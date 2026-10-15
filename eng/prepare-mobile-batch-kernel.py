#!/usr/bin/env python3
"""Prepare a portable frozen arithmetic callback host and run a small non-timing control."""
import argparse
import copy
import hashlib
import json
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
              "physicalDeviceVerified", "performanceMeasured", "performanceVerified")


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


def prepare(args):
    original, sdk, output = args.original.resolve(), args.sdk.resolve(), args.output.resolve()
    need(sha(original / "author/RuneCLR.BatchKernel.dll") == AUTHOR, "Accepted original author differs.")
    need(sha(original / "author/RuneCLR.Abstractions.dll") == sha(original / "host/RuneCLR.Abstractions.dll") == CONTRACT,
         "Accepted shared contract differs.")
    calibration = read(original / "baseline-smoke.json")
    need(calibration["passed"] is True and calibration["callbackChecksum"] == CHECKSUM and
         calibration["callbackDispatches"] == DISPATCHES, "Accepted arithmetic calibration differs.")
    project = ROOT / "eng/mobile-batch-kernel-probe/MobileBatchKernelProbe.csproj"
    source = ROOT / "eng/mobile-batch-kernel-probe/Entry.cs"
    sdk_directory = sdk.parent / "sdk/11.0.100-rc.1.26425.128"
    references = sdk.parent / "packs/Microsoft.NETCore.App.Ref/11.0.0-rc.1.26425.128/ref/net11.0"
    inputs = [Path(__file__).resolve(), project, source, ROOT / "Directory.Build.props", ROOT / "global.json", sdk,
              sdk_directory / "Roslyn/bincore/csc.dll", sdk_directory / "Roslyn/bincore/csc.deps.json",
              sdk_directory / "Roslyn/bincore/csc.runtimeconfig.json", original / "baseline-smoke.json",
              original / "baseline-smoke.stdout", original / "author/RuneCLR.BatchKernel.dll",
              original / "author/RuneCLR.Abstractions.dll", original / "host/RuneCLR.Abstractions.dll"]
    inputs += sorted(references.glob("*.dll"))
    need(references.is_dir() and len(inputs) > 100, "Pinned RC1 compiler/reference pack missing.")
    frozen = {str(path): sha(path) for path in inputs}
    output.mkdir(parents=True, exist_ok=False)
    (output / "source").mkdir()
    (output / "source/Entry.cs").write_bytes(source.read_bytes())
    command = [str(sdk), "build", str(project), "-c", "Release", "--artifacts-path", str(output / "build-obj"),
               "-o", str(output / "host"), "-p:MobileBatchKernelSource=" + str(output / "source/Entry.cs"),
               "-p:MobileBatchKernelContractPath=" + str(original / "host/RuneCLR.Abstractions.dll"),
               "-p:UseSharedCompilation=false", "-nodeReuse:false"]
    save(output / "request.json", {"schema": "runeclr.mobile-batch-kernel.prepare.v1", "driverSha256": sha(__file__),
         "frozenInputs": frozen, "generatedSourceSha256": sha(output / "source/Entry.cs"), "argv": command,
         "signature": "public static int MobileBatchKernelProbe.Entry.Run(string[] args)",
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
    save(output / "input-manifest.json", {"schema": "runeclr.mobile-batch-kernel.inputs.v1", "files": files,
         "assembly": "MobileBatchKernelProbe", "type": "MobileBatchKernelProbe.Entry", "method": "Run",
         "arguments": ["absolute author DLL", "no-config|high-budget", "32-hex nonce", "sample count 1..100", "fresh receipt path"],
         "warmups": 3, "iterations": 100000, "expectedChecksum": CHECKSUM, "expectedDispatchDelta": DISPATCHES,
         "authorSha256": AUTHOR, "contractSha256": CONTRACT, "contractIdentity": CONTRACT_IDENTITY, "contractMvid": CONTRACT_MVID,
         "contractBinding": "Frozen raw contract retained beside author; trusted loaded default-context component has exact identity/MVID; mobile R2R byte provenance requires an independent layout receipt.",
         "performanceVerified": False, "nativeEntryProof": False})
    archive = output / "mobile-batch-kernel-inputs.zip"
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


def review(receipt, mode, nonce, pid, samples=1):
    need(receipt["schema"] == "runeclr.mobile-batch-kernel.observation.v1" and receipt["passed"] is True and
         receipt["processId"] == pid and receipt["nonce"] == nonce and receipt["mode"] == mode, "Owned receipt binding differs.")
    need(receipt["runtime"].startswith(".NET 12.") and receipt["architecture"] in ("X64", "Arm64"), "Runtime/architecture differs.")
    need(receipt["authorHash"] == AUTHOR and receipt["contractHash"] == CONTRACT and receipt["iterations"] == 100000 and
         receipt["expectedChecksum"] == CHECKSUM and receipt["expectedDispatchDelta"] == DISPATCHES, "Frozen callback contract differs.")
    need(receipt["contractIdentity"] == CONTRACT_IDENTITY and receipt["contractMvid"] == CONTRACT_MVID,
         "Loaded trusted shared contract identity/MVID differs.")
    need(receipt["warmups"] == 3 and receipt["sampleCount"] == samples and len(receipt["Rows"]) == samples + 3 and
         receipt["collected"] is True, "Callback/collection count differs.")
    need(all(receipt[key] is False for key in UNVERIFIED), "Observation overclaims unperformed evidence.")
    need(receipt["Capabilities"] == {"policyVersion": 1, "terminalVersion": 1, "finalizerVersion": 1, "privateBridge": True},
         "Private native capability acknowledgement differs.")
    budget = mode == "high-budget"
    need(receipt["budgetLimit"] == (LIMIT if budget else None) and receipt["cleanupLimit"] == 4096 and
         receipt["RetiredGetterRejections"] == (8 if budget else 0), "Budget retirement acknowledgement differs.")
    need(receipt["Initial"] == (snapshot(0) if budget else None) and
         receipt["Final"] == (snapshot(DISPATCHES * (samples + 3)) if budget else None), "Initial/final ledger differs.")
    for index, row in enumerate(receipt["Rows"]):
        need(row == {"Index": index, "Warmup": index < 3, "Checksum": CHECKSUM,
                     "Before": snapshot(index * DISPATCHES) if budget else None,
                     "After": snapshot((index + 1) * DISPATCHES) if budget else None,
                     "DispatchDelta": DISPATCHES if budget else None}, "Exact callback row differs.")


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
    settings = {"DOTNET_InterpMode": "0", "DOTNET_RuneCLRInterpretCollectible": "0", "DOTNET_ReadyToRun": "1",
                "DOTNET_TieredCompilation": "0", "DOTNET_MULTILEVEL_LOOKUP": "0", "DOTNET_RuneCLRPhaseAcquireLoad": "1",
                "DOTNET_RuneCLRDerivedLedger": "0", "DOTNET_RuneCLRBatchInterval": "3e8"}
    env = environment()
    env.update(settings)
    save(output / "request.json", {"driverSha256": sha(__file__), "inputManifestSha256": sha(prepared / "input-manifest.json"),
         "privateRuntimeCommit": COMMIT, "frozenInputs": frozen, "settings": settings, "sampleCount": 1, "timingPerformed": False})
    mutants = 0
    for mode in ("no-config", "high-budget"):
        nonce, receipt_path = uuid.uuid4().hex, output / (mode + ".receipt.json")
        command = [str(build / "layout/dotnet.exe"), "exec", "--fx-version", "12.0.0",
                   str(prepared / "host/MobileBatchKernelProbe.dll"), str(prepared / "author/RuneCLR.BatchKernel.dll"),
                   mode, nonce, "1", str(receipt_path)]
        process = owned(command, output, env, mode, 45)
        receipt = read(receipt_path)
        review(receipt, mode, nonce, process["pid"])
        need(receipt["architecture"] == "X64", "Actual Windows process architecture differs.")
        need(receipt["loadedContractComponentHash"] == CONTRACT, "Windows raw trusted contract component differs.")
        marker = "MOBILE_BATCH_KERNEL_COMPLETE nonce=" + nonce + " pid=" + str(process["pid"]) + " mode=" + mode + " callbacks=4"
        need((output / (mode + ".stdout")).read_text(encoding="utf-8-sig").splitlines().count(marker) == 1, "Owned completion marker differs.")
        changes = [(["nonce"], "0" * 32), (["authorHash"], "0" * 64), (["collected"], False),
                   (["contractMvid"], "0" * 36), (["contractIdentity"], "wrong"),
                   (["nativeEntryProof"], True), (["Rows", 3, "Checksum"], 1), (["Rows", 3, "Warmup"], True)]
        if mode == "high-budget":
            changes += [(["Rows", 3, "After", "Executed"], 0), (["Rows", 3, "DispatchDelta"], DISPATCHES - 1),
                        (["Final", "CleanupExecuted"], 1), (["RetiredGetterRejections"], 7)]
        for keys, value in changes:
            changed = copy.deepcopy(receipt)
            target = changed
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = value
            rejected = False
            try:
                review(changed, mode, nonce, process["pid"])
            except RuntimeError:
                rejected = True
            need(rejected, "Corrupted receipt accepted: " + repr(keys))
            mutants += 1
        print(mode + ": four exact callback checks and post-frame collection PASS", flush=True)
    unchanged(frozen)
    unchanged(request["frozenInputs"])
    save(output / "results.json", {"passed": True, "processes": 2, "callbacks": 8, "collections": 2, "receiptMutantsRejected": mutants,
         "interval": 1000, "privateRuntimeCommit": COMMIT, "authorAndContractBytesUnchanged": True,
         "nativeEntryProof": False, "liveBatchPathVerified": False, "mobileExecutionVerified": False,
         "performanceMeasured": False, "performanceVerified": False,
         "scope": "Small portable-host functional sanity only; no timing, affinity, Windows entry observer, full benchmark or mobile run."})
    print(json.dumps(read(output / "results.json"), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "windows-check"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--original", type=Path, default=ORIGINAL)
    parser.add_argument("--sdk", type=Path, default=ROOT / "artifacts/toolchains/dotnet-11-rc1/dotnet.exe")
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--build", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args)
    else:
        need(args.prepared is not None and args.build is not None, "--prepared and --build required.")
        windows_check(args)


if __name__ == "__main__":
    main()
