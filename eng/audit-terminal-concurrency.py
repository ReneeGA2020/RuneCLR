#!/usr/bin/env python3
"""Audit frozen joined-worker raw results and PE definitions without author reruns."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '099dacd07d8d890822f7422f895337733457ab3c'


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def reconcile(value):
    require(value["passed"] and value["collected"] == 2, "Completed collections")
    require(value["RetiredQueriesRejected"] == [8, 8], "Retired access")
    require(value["OwnerIsolation"] and value["nativePolicyAcknowledged"] == 1, "Owner policy")
    owners = value["OwnershipSnapshots"]
    require(owners["goodBefore"] == owners["goodAfterBad"], "Idle owner charged")
    require(owners["badAfterBad"] == owners["badAfterGood"], "Finished owner charged")
    require(len(value["Rows"]) == 2, "Worker and recovery inventory")
    for index, row in enumerate(value["Rows"]):
        workers = value["workers"] if index == 0 else 1
        lane = value["lane"] if index == 0 else "high"
        require(row["Workers"] == workers and row["Lane"] == lane, "Lane ownership")
        require(row["Admitted"] and row["Joined"] and row["Entered"] == workers, "Admission/join")
        require(len(row["WorkerIds"]) == len(set(row["WorkerIds"])) == workers, "Distinct worker threads")
        require(row["Counters"]["entries"] == [1] * workers and row["StaticStarts"] == 1, "Actual entry/static reset")
        before, after = row["AtGate"], row["After"]
        if lane == "required":
            require(before is None and after is None, "Unmetered control")
        else:
            require(before["Executed"] > 0 and before["Remaining"] > 0, "Live common gate")
            require(row["PostGateDispatches"] == after["Executed"] - before["Executed"], "Post-gate difference")
            if lane != "diagnostic":
                for snapshot in (before, after):
                    require(snapshot["Remaining"] >= 0 and snapshot["Executed"] >= 0, "Nonnegative ledger")
                    require(snapshot["Remaining"] + snapshot["Executed"] == row["Allowance"], "Quiescent execution conservation")
                    require(snapshot["CleanupRemaining"] + snapshot["CleanupExecuted"] == row["CleanupAllowance"], "Quiescent cleanup conservation")
        if lane in ("terminal", "finite-cleanup", "tight-cleanup"):
            require(after["Executed"] == row["Allowance"] == 2048 and after["Remaining"] == 0, "Exact execution admission")
            require(after["Exhausted"] and after["IsTerminated"] and after["Reason"] == 1, "Sticky terminal reason")
            require(row["Returned"] == [False] * workers and row["Errors"] == ["System.OperationCanceledException"] * workers, "No terminal return")
            require(row["Completed"] == 0 and row["Counters"]["completed"] == [0] * workers, "No completion effects")
            if lane == "terminal":
                require(after["Phase"] == 1 and after["CleanupExecuted"] == 0, "No-finally control")
            elif lane == "finite-cleanup":
                require(after["Phase"] == 1 and row["Counters"]["cleanupCompleted"] == [1] * workers, "Finite finally completion")
                require(after["CleanupExecuted"] == 916 * workers, "Finite cleanup baseline")
            else:
                require(after["Phase"] == 2 and after["CleanupRemaining"] == 0 and after["CleanupExecuted"] == 64, "Shared cleanup bound")
                require(row["CleanupCompleted"] == 0, "Truncated cleanup")
        else:
            require(row["Returned"] == [True] * workers and row["Errors"] == [None] * workers, "Finite returns")
            require(row["Values"] == [4089345937] * workers and row["Counters"]["completed"] == [1] * workers, "Checksum/business effects")
            if lane == "high":
                require(not after["IsTerminated"] and after["Reason"] == after["Phase"] == 0, "High-budget control")
            if lane == "diagnostic":
                require(after["Remaining"] == 0 and after["Executed"] > 2048 and not after["IsTerminated"], "Diagnostic continuation")
    if value["lane"] in ("high", "diagnostic"):
        require(value["Rows"][0]["PostGateDispatches"] == value["workers"] * value["Rows"][1]["PostGateDispatches"], "Single-worker reference")
    require(owners["goodAfterGood"] == value["Rows"][1]["After"], "Recovery snapshot")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-commit", default=BASELINE)
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    require(not args.output.exists(), "New review directory required")
    args.output.mkdir(parents=True)
    shutil.copy2(__file__, args.output / "auditor.py")
    request, result = load(evidence / "request.json"), load(evidence / "results.json")
    provenance_binding = load(evidence / "runtime-provenance.json")
    require(request.get("candidateCommit", BASELINE) == result.get("candidateCommit", BASELINE) ==
            provenance_binding["binding"]["actualSourceCommit"] == args.candidate_commit, "Expected exact source candidate")
    require(request["configuration"] == "Release" and request["repeats"] == 3, "Fixed Release baseline")
    require(result["passed"] and result["laneCount"] == 36 and result["contextsCollected"] == 72, "Complete baseline")
    for relative, expected in request["sourceHashes"].items():
        require(sha(ROOT / relative) == sha(evidence / "source" / relative) == expected, "Source binding: " + relative)
    for relative, expected in load(evidence / "managed-identity.json").items():
        require(sha(evidence / relative) == expected, "Managed binding: " + relative)
    sdk = Path(request["hostSdk"])
    require(sha(sdk) == request["hostSdkSha256"], "Private SDK binding")
    inspector = ROOT / "eng/managed-entry-metadata/bin/Release/net11.0/RuneCLR.ManagedEntryMetadata.dll"
    metadata_raw = subprocess.check_output([str(sdk), str(inspector), str(evidence / "Payload/ConcurrencyProbe.Payload.dll")])
    (args.output / "metadata.json").write_bytes(metadata_raw)
    metadata = json.loads(metadata_raw)[0]
    require(metadata["managedNativeRva"] == 0 and metadata["sha256"] == sha(evidence / "Payload/ConcurrencyProbe.Payload.dll"), "Actual IL-only PE")
    provenance = subprocess.run(["py", "-3", "-B", str(ROOT / "eng/windows-runtime-validation.py"), "check", "--output", str(evidence),
                                 "--candidate-commit", args.candidate_commit], capture_output=True)
    (args.output / "provenance.stdout").write_bytes(provenance.stdout)
    (args.output / "provenance.stderr").write_bytes(provenance.stderr)
    require(provenance.returncode == 0, "Matching native/CoreLib/compiler/source layout")
    nonces, inventory, entries = set(), {}, 0
    for lane in result["lanes"]:
        name = lane["name"]
        receipt = load(evidence / (name + ".process.json"))
        value = load(evidence / name / "result.json")
        require(receipt == lane["receipt"] and value == lane["result"], "Raw/scalar receipt binding")
        require(sha(evidence / name / "result.json") == lane["resultSha256"], "Scalar hash")
        require(receipt["exitCode"] == 0 and not receipt["timedOut"], "Owned completion")
        require(receipt["settings"] == {"DOTNET_InterpMode": "0", "DOTNET_RuneCLRInterpretCollectible": "0",
                "DOTNET_ReadyToRun": "1", "DOTNET_TieredCompilation": "0", "DOTNET_MULTILEVEL_LOOKUP": "0",
                "RUNECLR_POST_EXECUTION_PRECODE": "1"}, "Frozen selection/observation settings")
        require(value["nonce"] == receipt["argv"][-2] and value["processId"] == receipt["pid"], "PID/nonce echo")
        require(value["nonce"] not in nonces, "Unique launch nonce")
        nonces.add(value["nonce"])
        require(Path(receipt["argv"][0]) == Path(request["layout"]) / "dotnet.exe", "Exact host command")
        for suffix in ("stdout", "stderr"):
            require(sha(evidence / (name + "." + suffix)) == receipt[suffix + "Sha256"], "Raw stream binding")
        require(load(evidence / (name + ".stdout")) == value, "Actual stdout receipt")
        raw_rows = [json.loads(line) for line in (evidence / (name + ".stderr")).read_text().splitlines() if line.startswith('{"Workers":')]
        require(raw_rows == value["Rows"], "Actual stderr business rows")
        reconcile(value)
        key = f"{value['workers']}-{value['lane']}"
        inventory[key] = inventory.get(key, 0) + 1
        for row in value["Rows"]:
            for entry in row["Entries"]:
                require(entry["Assembly"] == metadata["assembly"] and entry["ModuleMvid"] == metadata["moduleMvid"], "PE assembly/MVID")
                method = [m for m in metadata["methods"] if m["token"] == entry["MethodDefToken"] and m["owner"] == entry["DefiningType"] and m["name"] == entry["Method"]]
                require(len(method) == 1 and method[0]["ilBytes"] > 0, "Actual method definition/IL")
                require(entry["Interpreted"] and entry["Collectible"] and entry["PrecodeType"] == 6 and entry["InvocationEvidence"], "Selected post-invocation entry")
                require(bytes.fromhex(entry["Bytes"]).startswith(bytes.fromhex("4c8b15")), "Saved stub opcode")
                entries += 1
    expected = {f"{workers}-{lane}": 3 for workers in (2, 4) for lane in ("terminal", "finite-cleanup", "tight-cleanup", "high", "diagnostic", "required")}
    require(inventory == expected, "Lane/repetition inventory")
    controls = []
    for name in ("lost-execution", "lost-cleanup", "charged-idle-owner", "missing-join"):
        value = copy.deepcopy(next(lane["result"] for lane in result["lanes"] if lane["result"]["lane"] == "finite-cleanup"))
        if name == "lost-execution": value["Rows"][0]["After"]["Executed"] -= 1
        elif name == "lost-cleanup": value["Rows"][0]["After"]["CleanupExecuted"] -= 1
        elif name == "charged-idle-owner": value["OwnershipSnapshots"]["goodAfterBad"]["Executed"] += 1
        else: value["Rows"][0]["Joined"] = False
        try:
            reconcile(value)
        except RuntimeError:
            controls.append(name)
        else:
            raise RuntimeError("Corruption accepted: " + name)
    audit = {"passed": True, "evidence": str(evidence), "resultsSha256": sha(evidence / "results.json"),
             "candidateCommit": args.candidate_commit,
             "auditorSha256": sha(__file__), "metadataToolSha256": sha(inspector), "metadataSha256": sha(args.output / "metadata.json"),
             "ownedRawProcesses": 36, "contextsCollected": 72, "postInvocationEntries": entries,
             "laneInventory": inventory, "negativeControlsRejected": controls,
             "scope": "Independent offline raw/PE/quiescent-ledger audit; no author rerun, scheduler trace, or transactional snapshots"}
    (args.output / "results.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(f"PASS independent concurrency audit: 36 raw processes, 72 collections, {entries} PE-bound selected entries, 4 rejected ledger controls")


if __name__ == "__main__":
    main()
