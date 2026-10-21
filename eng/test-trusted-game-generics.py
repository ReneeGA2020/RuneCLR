#!/usr/bin/env python3
"""Build and run the stock-SDK trusted-game generics fixture.

This runner is deliberately side-effect-free on import. All work happens in
main(), which requires Python 3 explicitly.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
from datetime import datetime, timezone
import io
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "eng" / "trusted-game-generics"
HOST_PROJECT = FIXTURE / "Host" / "TrustedGameGenerics.Host.csproj"
MODULE_A_PROJECT = FIXTURE / "Module.A" / "TrustedGameGenerics.Module.A.csproj"
MODULE_B_PROJECT = FIXTURE / "Module.B" / "TrustedGameGenerics.Module.B.csproj"

HOST_PROJECT_NAME = "TrustedGameGenerics.Host"
CONTRACT_PROJECT_NAME = "TrustedGameGenerics.Contracts"
TRUSTED_UPDATE_PROJECT_NAME = "RuneCLR.TrustedUpdate"
MODULE_A_PROJECT_NAME = "TrustedGameGenerics.Module.A"
MODULE_B_PROJECT_NAME = "TrustedGameGenerics.Module.B"
MODULE_ASSEMBLY = "TrustedGameGenerics.Module"
CONTRACT_ASSEMBLY = "TrustedGameGenerics.Contracts"
TRUSTED_UPDATE_ASSEMBLY = "RuneCLR.TrustedUpdate"
LATE_TYPE = "TrustedGameGenerics.Module.LateToken"
SHAPE_KEYS = ("reference", "structs", "nested", "interface", "delegate", "late")
SHAPE_PROPERTIES = {
    "reference": "referenceChecksum",
    "structs": "structChecksum",
    "nested": "nestedChecksum",
    "interface": "interfaceChecksum",
    "delegate": "delegateChecksum",
    "late": "lateChecksum",
}
SANITIZED_PREFIXES = ("RUNECLR_", "TRUSTED_", "COMPLUS_", "__TEST", "DOTNET_")
CONTEXT_MODES = ("collectible", "resident")
CONTEXT_FIELDS = ("requestedContextMode", "contextIsCollectible", "unloadRequested", "collectionClaimed")
FIXTURE_GUID = "8c2d4f2e-4f5a-4b39-9a6f-0f1c2d3e4f50"
FIXTURE_VARIANTS = {
    "A": {"code": 1, "salt": 0x1111, "label": "A", "factor": 19},
    "B": {"code": 2, "salt": 0x2222, "label": "B", "factor": 23},
}
FIXTURE_GOLDEN = {
    "A": {
        "echoReferenceChecksums": [8077, 118189],
        "measureResults": [2229, -2043316012, -550109084],
        "shapes": {
            "reference": 118189,
            "structs": -1182435073,
            "nested": 1373189203,
            "interface": 127145520,
            "delegate": 31105,
            "late": 457608557,
        },
        "lateDigest": 457608521,
        "ledger": 248,
        "aggregate": -6047711,
    },
    "B": {
        "echoReferenceChecksums": [9086, 128374],
        "measureResults": [2694, -2043314772, -550107441],
        "shapes": {
            "reference": 128374,
            "structs": -1182415977,
            "nested": 330390114,
            "interface": 2063251341,
            "delegate": 36047,
            "late": 915177477,
        },
        "lateDigest": 915177441,
        "ledger": 342,
        "aggregate": 295548138,
    },
}
HOST_FULL_NAME = "TrustedGameGenerics.Host, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null"
CONTRACT_FULL_NAME = "TrustedGameGenerics.Contracts, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null"
TRUSTED_UPDATE_FULL_NAME = "RuneCLR.TrustedUpdate, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null"
MODULE_FULL_NAME = "TrustedGameGenerics.Module, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null"
_PE_CACHE = {}


class RunnerError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def decode(data: bytes) -> str:
    return data.decode("utf-8-sig", errors="replace")


def clean_env() -> dict:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(SANITIZED_PREFIXES)
    }
    env["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
    env["DOTNET_NOLOGO"] = "1"
    return env


def run_process(name, command, cwd, timeout, logs, commands, commands_path):
    logs.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    process = subprocess.Popen(
        [str(item) for item in command],
        cwd=str(cwd),
        env=clean_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        timed_out = True
    completed = utc_now()
    stdout_path = logs / (name + ".stdout")
    stderr_path = logs / (name + ".stderr")
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    record = {
        "name": name,
        "command": [str(item) for item in command],
        "cwd": str(cwd),
        "processId": process.pid,
        "startedUtc": iso(started),
        "completedUtc": iso(completed),
        "durationMs": round((completed - started).total_seconds() * 1000.0, 3),
        "exitCode": None if timed_out else process.returncode,
        "timedOut": timed_out,
        "stdoutPath": str(stdout_path),
        "stderrPath": str(stderr_path),
        "environment": {
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
            "DOTNET_NOLOGO": "1",
            "sanitizedPrefixes": list(SANITIZED_PREFIXES),
        },
    }
    commands.append(record)
    save_json(commands_path, commands)
    if timed_out:
        raise RunnerError(f"{name} timed out after {timeout} seconds")
    return record, stdout, stderr


def require_exit(record, name):
    if record["exitCode"] != 0:
        raise RunnerError(
            f"{name} exited {record['exitCode']}; see {record['stderrPath']}"
        )


def artifact_dll(artifacts_root: Path, project_name: str, assembly_name: str) -> Path:
    base = artifacts_root / "bin" / project_name
    matches = [
        path
        for path in base.rglob(assembly_name + ".dll")
        if path.is_file()
        and "ref" not in path.parts
        and "refint" not in path.parts
    ]
    if len(matches) != 1:
        raise RunnerError(
            f"expected one {assembly_name}.dll under {base}; found {matches}"
        )
    return matches[0]


def snapshot(directory: Path) -> dict:
    result = {}
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        result[path.relative_to(directory).as_posix()] = {
            "sha256": sha256(path),
            "size": stat.st_size,
            "mtimeNs": stat.st_mtime_ns,
        }
    return result


def snapshot_inputs(host_dir: Path, contracts_dir: Path, trusted_update_dir: Path) -> dict:
    return {
        "host": snapshot(host_dir),
        "contracts": snapshot(contracts_dir),
        "trustedUpdate": snapshot(trusted_update_dir),
    }


def compare_snapshots(before: dict, after: dict, label: str):
    if before == after:
        return
    changes = []
    for group in sorted(set(before) | set(after)):
        left = before.get(group, {})
        right = after.get(group, {})
        for name in sorted(set(left) | set(right)):
            if left.get(name) != right.get(name):
                changes.append(f"{group}/{name}")
    raise RunnerError(f"{label} changed input outputs: {', '.join(changes[:12])}")


def assembly_name(full_name: str) -> str:
    if not full_name:
        return ""
    return full_name.split(",", 1)[0].strip()


def int32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def check(checks, condition, name, detail=""):
    passed = bool(condition)
    checks.append({"name": name, "passed": passed, "detail": detail})
    if not passed:
        raise RunnerError(name + (": " + detail if detail else ""))


def shape_value(outcome, key):
    name = SHAPE_PROPERTIES[key]
    if name not in outcome:
        raise RunnerError(f"missing per-shape value {name} for shape {key}")
    return outcome[name]


def shape_values(outcome):
    return {key: shape_value(outcome, key) for key in SHAPE_KEYS}

def _guid_hash(text):
    data = uuid.UUID(text).bytes_le
    parts = [int.from_bytes(data[index:index + 4], "little") for index in range(0, 16, 4)]
    return int32(parts[0] ^ parts[1] ^ parts[2] ^ parts[3])


def _vector_value(x, y, z):
    return int32(x * 3 + y * 5 + z * 7)


def _pair_value(left, right):
    return int32(int32(left ^ (left >> 32)) + right * 37)


def _measure(value, type_name):
    return int32(value * 31 + len(type_name) + 17)


def _reference_checksum(label, code, revision):
    return int32((7 + code) * 1009 + revision * 9176 + len("ref-" + label))


def _fold_envelopes(code, label):
    accumulated = 100 + code
    for name, seed, count in (
        ("env-" + label + "-one", code, 3),
        ("env-" + label + "-two", code + 4, 2),
    ):
        accumulated = int32(accumulated * 31 + len(name))
        groups = {"alpha": [], "beta": []}
        for index in range(count):
            x = seed + index
            groups["alpha"].append((x, x + 1, x + 2))
            groups["beta"].append((x + 10, x + 11, x + 12))
        for key in sorted(groups):
            accumulated = int32(accumulated * 17 + len(key))
            for x, y, z in groups[key]:
                accumulated = int32(accumulated * 101 + _vector_value(x, y, z))
    return accumulated


def _reduce_pair(code, factor):
    pairs = [
        (11_000_000 + code, 2 + code),
        (22_000_000 + code, 4 + code),
        (33_000_000 + code, 6 + code),
    ]
    accumulated = 9 + code
    for left, right in pairs:
        accumulated = int32(accumulated * factor + _pair_value(left, right))
    return accumulated


def _delegate_vectors(code):
    vectors = [
        (code, 2 + code, 3 + code),
        (4 + code, 5 + code, 6 + code),
        (7 + code, 8 + code, 9 + code),
    ]
    accumulated = 9 + code
    for x, y, z in vectors:
        accumulated = int32(accumulated * 13 + _vector_value(x, y, z))
    return accumulated


def _late_values(code, salt, label):
    digest = int32((code + 5) * 7919 + salt * 104729 + len("late-" + label))
    return digest, int32(digest + len(LATE_TYPE))


def _ledger_total(shapes):
    moduli = (97, 89, 83, 79, 73, 71)
    total = 0
    for index, key in enumerate(SHAPE_KEYS):
        checksum = shapes[key]
        delta = int32((checksum & 0xFFFFFFFF) % moduli[index] + index + 1)
        total = int32(total + delta)
    return total


def fixture_expected(variant):
    spec = FIXTURE_VARIANTS[variant]
    code = spec["code"]
    label = spec["label"]
    initial = _reference_checksum(label, code, 0)
    reference = _reference_checksum(label, code, 11 + code)
    vector_measure = _measure(_vector_value(2 + code, 3 + code, 5 + code), "ScoreVector")
    pair_measure = _measure(_pair_value(7_000_000_000 + code, 13 + code), "ScorePair")
    stamp_value = int32(_guid_hash(FIXTURE_GUID) + (3 + code) * 53)
    stamp_measure = _measure(stamp_value, "ScoreStamp")
    measures = [vector_measure, pair_measure, stamp_measure]
    nested = _fold_envelopes(code, label)
    interface = _reduce_pair(code, spec["factor"])
    delegated = _delegate_vectors(code)
    late_digest, late = _late_values(code, spec["salt"], label)
    shapes = {
        "reference": reference,
        "structs": int32(vector_measure * 3 + pair_measure * 5 + stamp_measure * 7),
        "nested": nested,
        "interface": interface,
        "delegate": delegated,
        "late": late,
    }
    aggregate = int32(
        shapes["reference"] * 3
        + shapes["structs"] * 5
        + shapes["nested"] * 7
        + shapes["interface"] * 11
        + shapes["delegate"] * 13
        + shapes["late"] * 17
    )
    return {
        "variant": label,
        "echoTypes": [CONTRACT_ASSEMBLY + ".ScorePacket", CONTRACT_ASSEMBLY + ".ScorePacket"],
        "echoReferenceChecksums": [initial, reference],
        "measureTypes": [
            CONTRACT_ASSEMBLY + ".ScoreVector",
            CONTRACT_ASSEMBLY + ".ScorePair",
            CONTRACT_ASSEMBLY + ".ScoreStamp",
        ],
        "measureResults": measures,
        "reducerType": MODULE_ASSEMBLY + ".VariantReducer",
        "reducerAssembly": MODULE_ASSEMBLY,
        "lateTypeName": LATE_TYPE,
        "lateAssembly": MODULE_ASSEMBLY,
        "lateIsValueType": True,
        "lateDigest": late_digest,
        "shapes": shapes,
        "aggregate": aggregate,
        "ledgerTotal": _ledger_total(shapes),
        "ledgerApplications": 6,
    }


def validate_fixture_expectations(checks, label, report):
    expected = fixture_expected(label)
    outcome = report["outcome"]
    check(checks, report.get("echoTypes") == expected["echoTypes"], f"{label}/fixture/echo-types/order", "fixture-source-recomputation")
    check(checks, report.get("echoReferenceChecksums") == expected["echoReferenceChecksums"],
          f"{label}/fixture/echo-reference/initial-and-final", "fixture-source-recomputation")
    check(checks, report.get("measureTypes") == expected["measureTypes"], f"{label}/fixture/measure-types/order", "fixture-source-recomputation")
    check(checks, report.get("measureResults") == expected["measureResults"], f"{label}/fixture/measure-results", "fixture-source-recomputation")
    check(checks, report.get("reduceImplementations") == [expected["reducerType"]],
          f"{label}/fixture/reducer-type", "fixture-source-recomputation")
    check(checks, report.get("lateProbe", {}).get("typeName") == expected["lateTypeName"],
          f"{label}/fixture/late-type-name", "fixture-source-recomputation")
    check(checks, report.get("lateProbe", {}).get("assemblyName") == expected["lateAssembly"],
          f"{label}/fixture/late-assembly", "fixture-source-recomputation")
    check(checks, report.get("lateProbe", {}).get("isValueType") is True,
          f"{label}/fixture/late-is-value-type", "fixture-source-recomputation")
    check(checks, report.get("lateProbe", {}).get("digest") == expected["lateDigest"],
          f"{label}/fixture/late-digest", "fixture-source-recomputation")
    for key in SHAPE_KEYS:
        check(
            checks,
            outcome.get(SHAPE_PROPERTIES[key]) == expected["shapes"][key],
            f"{label}/fixture/shape/{key}",
            f"{expected['shapes'][key]} (fixture-source-recomputation)",
        )
    check(checks, outcome.get("aggregateChecksum") == expected["aggregate"],
          f"{label}/fixture/aggregate", "fixture-source-recomputation")
    check(checks, report.get("successValue") == expected["aggregate"],
          f"{label}/fixture/session-value", "fixture-source-recomputation")
    check(checks, outcome.get("ledgerTotal") == expected["ledgerTotal"],
          f"{label}/fixture/ledger-total", "fixture-source-recomputation")
    check(checks, report.get("ledger", {}).get("total") == expected["ledgerTotal"],
          f"{label}/fixture/host-ledger-total", "fixture-source-recomputation")
    check(checks, outcome.get("ledgerApplications") == expected["ledgerApplications"],
          f"{label}/fixture/ledger-applications", "fixture-source-recomputation")
    check(checks, report.get("ledger", {}).get("applications") == expected["ledgerApplications"],
          f"{label}/fixture/host-ledger-applications", "fixture-source-recomputation")

def validate_context_mode_cli(argv):
    args = list(sys.argv[1:] if argv is None else argv)
    positions = [
        index for index, argument in enumerate(args)
        if argument == "--context-mode" or argument.startswith("--context-mode=")
    ]
    if len(positions) > 1:
        raise RunnerError("--context-mode specified more than once")
    if not positions:
        return "collectible"
    index = positions[0]
    if args[index] != "--context-mode":
        raise RunnerError("--context-mode requires a separate value")
    if index + 1 >= len(args):
        raise RunnerError("--context-mode requires a value")
    value = args[index + 1]
    if value not in CONTEXT_MODES:
        raise RunnerError(f"invalid --context-mode {value!r}; expected collectible or resident")
    return value


def resolve_context_mode(report):
    arguments = report.get("arguments", [])
    if not isinstance(arguments, list):
        raise RunnerError("report arguments must be a list")
    positions = [
        index for index, argument in enumerate(arguments)
        if argument == "--context-mode" or argument.startswith("--context-mode=")
    ]
    if len(positions) > 1:
        raise RunnerError("duplicate --context-mode arguments")
    argv_mode = None
    if positions:
        index = positions[0]
        if arguments[index] != "--context-mode":
            raise RunnerError("--context-mode requires a separate value")
        if index + 1 >= len(arguments):
            raise RunnerError("--context-mode requires a value")
        argv_mode = arguments[index + 1]
        if argv_mode not in CONTEXT_MODES:
            raise RunnerError(f"invalid --context-mode {argv_mode!r}; expected collectible or resident")

    new_present = [field for field in ("requestedContextMode", "contextIsCollectible") if field in report]
    if not new_present:
        if argv_mode is not None:
            raise RunnerError("context mode argv present but report mode fields are missing")
        missing_legacy = [field for field in ("unloadRequested", "collectionClaimed") if field not in report]
        if missing_legacy:
            raise RunnerError(
                "historical-implicit-collectible requires unloadRequested and collectionClaimed; missing: "
                + ", ".join(missing_legacy)
            )
        if type(report["unloadRequested"]) is not bool or report["unloadRequested"] is not True:
            raise RunnerError("historical unloadRequested must be the boolean true")
        if type(report["collectionClaimed"]) is not bool or report["collectionClaimed"] is not False:
            raise RunnerError("historical collectionClaimed must be the boolean false")
        return {
            "format": "historical-implicit-collectible",
            "requested": "collectible",
            "isCollectible": True,
            "unloadRequested": True,
            "collectionClaimed": False,
            "argvMode": None,
        }

    missing = [field for field in CONTEXT_FIELDS if field not in report]
    if missing:
        raise RunnerError("partial context mode fields; missing: " + ", ".join(missing))
    requested = report["requestedContextMode"]
    if not isinstance(requested, str) or requested not in CONTEXT_MODES or requested != requested.strip().lower():
        raise RunnerError(f"invalid requestedContextMode: {requested!r}")
    for field in ("contextIsCollectible", "unloadRequested", "collectionClaimed"):
        if type(report[field]) is not bool:
            raise RunnerError(f"{field} must be a JSON boolean")
    expected_collectible = requested == "collectible"
    if report["contextIsCollectible"] != expected_collectible:
        raise RunnerError("contextIsCollectible does not match requestedContextMode")
    if report["unloadRequested"] != expected_collectible:
        raise RunnerError("unloadRequested does not match requestedContextMode")
    if report["collectionClaimed"] is not False:
        raise RunnerError("collectionClaimed must be false")
    if argv_mode is None:
        raise RunnerError("new-format report is missing --context-mode in argv")
    if argv_mode != requested:
        raise RunnerError("argv --context-mode does not match requestedContextMode")
    return {
        "format": "new",
        "requested": requested,
        "isCollectible": report["contextIsCollectible"],
        "unloadRequested": report["unloadRequested"],
        "collectionClaimed": report["collectionClaimed"],
        "argvMode": argv_mode,
    }


def expect_runner_error(checks, name, callback, detail=""):
    try:
        callback()
    except RunnerError as error:
        checks.append({"name": name, "passed": True, "detail": str(error)})
    else:
        check(checks, False, name, detail or "expected RunnerError")


def context_mode_checks(checks):
    historical = {
        "arguments": ["host.dll", "--module", "m.dll", "--variant", "A", "--report", "r.json"],
        "unloadRequested": True,
        "collectionClaimed": False,
    }
    resolved = resolve_context_mode(historical)
    check(checks, resolved["format"] == "historical-implicit-collectible", "context/historical/format")
    check(
        checks,
        resolved["requested"] == "collectible"
        and resolved["isCollectible"] is True
        and resolved["unloadRequested"] is True
        and resolved["collectionClaimed"] is False,
        "context/historical/implicit-collectible",
    )

    missing_unload = copy.deepcopy(historical)
    del missing_unload["unloadRequested"]
    expect_runner_error(checks, "context/historical/missing-unload", lambda: resolve_context_mode(missing_unload))
    missing_collection = copy.deepcopy(historical)
    del missing_collection["collectionClaimed"]
    expect_runner_error(checks, "context/historical/missing-collection", lambda: resolve_context_mode(missing_collection))
    missing_both = copy.deepcopy(historical)
    del missing_both["unloadRequested"]
    del missing_both["collectionClaimed"]
    expect_runner_error(checks, "context/historical/missing-both", lambda: resolve_context_mode(missing_both))
    false_unload = copy.deepcopy(historical)
    false_unload["unloadRequested"] = False
    expect_runner_error(checks, "context/historical/unload-false", lambda: resolve_context_mode(false_unload))
    true_collection = copy.deepcopy(historical)
    true_collection["collectionClaimed"] = True
    expect_runner_error(checks, "context/historical/collection-true", lambda: resolve_context_mode(true_collection))
    int_unload = copy.deepcopy(historical)
    int_unload["unloadRequested"] = 1
    expect_runner_error(checks, "context/historical/int-unload", lambda: resolve_context_mode(int_unload))
    int_collection = copy.deepcopy(historical)
    int_collection["collectionClaimed"] = 0
    expect_runner_error(checks, "context/historical/int-collection", lambda: resolve_context_mode(int_collection))

    def new_report(mode):
        return {
            "arguments": ["host.dll", "--module", "m.dll", "--variant", "A", "--context-mode", mode, "--report", "r.json"],
            "requestedContextMode": mode,
            "contextIsCollectible": mode == "collectible",
            "unloadRequested": mode == "collectible",
            "collectionClaimed": False,
        }

    for mode in CONTEXT_MODES:
        resolved = resolve_context_mode(new_report(mode))
        check(checks, resolved["format"] == "new", f"context/new/{mode}/format")
        check(checks, resolved["requested"] == mode, f"context/new/{mode}/requested")
        check(checks, resolved["isCollectible"] == (mode == "collectible"), f"context/new/{mode}/collectible")
        check(checks, resolved["unloadRequested"] == (mode == "collectible"), f"context/new/{mode}/unload")
        check(checks, resolved["collectionClaimed"] is False, f"context/new/{mode}/collection")
        check(checks, resolved["argvMode"] == mode, f"context/new/{mode}/argv")
        synthetic = new_report(mode)
        synthetic["hostPath"] = "HOST"
        synthetic["modulePath"] = "MODULE"
        expected = expected_host_arguments(synthetic, "A", Path("RUN"))
        check(
            checks,
            expected == [
                "HOST",
                "--module",
                "MODULE",
                "--variant",
                "A",
                "--context-mode",
                mode,
                "--report",
                str((Path("RUN") / "report.json").resolve()),
            ],
            f"context/new/{mode}/expected-argv",
        )

    expect_runner_error(
        checks,
        "context/negative/partial-fields",
        lambda: resolve_context_mode({"arguments": historical["arguments"], "requestedContextMode": "collectible"}),
    )
    missing_field = new_report("collectible")
    del missing_field["unloadRequested"]
    expect_runner_error(checks, "context/negative/missing-field", lambda: resolve_context_mode(missing_field))

    missing_flag = new_report("collectible")
    missing_flag["arguments"] = ["host.dll", "--module", "m.dll", "--variant", "A", "--report", "r.json"]
    expect_runner_error(checks, "context/negative/missing-argv", lambda: resolve_context_mode(missing_flag))

    duplicate_flag = new_report("collectible")
    duplicate_flag["arguments"] = duplicate_flag["arguments"] + ["--context-mode", "collectible"]
    expect_runner_error(checks, "context/negative/duplicate-argv", lambda: resolve_context_mode(duplicate_flag))

    invalid_flag = new_report("collectible")
    invalid_flag["arguments"][invalid_flag["arguments"].index("--context-mode") + 1] = "invalid"
    expect_runner_error(checks, "context/negative/invalid-argv", lambda: resolve_context_mode(invalid_flag))

    equals_flag = new_report("collectible")
    index = equals_flag["arguments"].index("--context-mode")
    equals_flag["arguments"][index:index + 2] = ["--context-mode=resident"]
    expect_runner_error(checks, "context/negative/equals-argv", lambda: resolve_context_mode(equals_flag))

    missing_value = new_report("collectible")
    index = missing_value["arguments"].index("--context-mode")
    del missing_value["arguments"][index + 1]
    expect_runner_error(checks, "context/negative/missing-argv-value", lambda: resolve_context_mode(missing_value))

    mismatch_collectible = new_report("collectible")
    mismatch_collectible["contextIsCollectible"] = False
    expect_runner_error(checks, "context/negative/collectible-bool-mismatch", lambda: resolve_context_mode(mismatch_collectible))

    mismatch_unload = new_report("collectible")
    mismatch_unload["unloadRequested"] = False
    expect_runner_error(checks, "context/negative/unload-mismatch", lambda: resolve_context_mode(mismatch_unload))

    mismatch_collection = new_report("collectible")
    mismatch_collection["collectionClaimed"] = True
    expect_runner_error(checks, "context/negative/collection-claim", lambda: resolve_context_mode(mismatch_collection))

    int_collectible = new_report("collectible")
    int_collectible["contextIsCollectible"] = 1
    expect_runner_error(checks, "context/negative/int-collectible", lambda: resolve_context_mode(int_collectible))

    int_unload = new_report("collectible")
    int_unload["unloadRequested"] = 0
    expect_runner_error(checks, "context/negative/int-unload", lambda: resolve_context_mode(int_unload))

    int_collection = new_report("collectible")
    int_collection["collectionClaimed"] = 0
    expect_runner_error(checks, "context/negative/int-collection", lambda: resolve_context_mode(int_collection))

    invalid_requested = new_report("collectible")
    invalid_requested["requestedContextMode"] = "Collectible"
    expect_runner_error(checks, "context/negative/noncanonical-requested", lambda: resolve_context_mode(invalid_requested))

    invalid_argv_mode = new_report("collectible")
    invalid_argv_mode["arguments"][invalid_argv_mode["arguments"].index("--context-mode") + 1] = "resident"
    expect_runner_error(checks, "context/negative/argv-mismatch", lambda: resolve_context_mode(invalid_argv_mode))

    historical_flag = copy.deepcopy(historical)
    historical_flag["arguments"] = historical_flag["arguments"] + ["--context-mode", "collectible"]
    expect_runner_error(checks, "context/negative/historical-argv", lambda: resolve_context_mode(historical_flag))

    check(checks, validate_context_mode_cli(["--context-mode", "resident"]) == "resident", "context/cli/resident")
    check(checks, validate_context_mode_cli([]) == "collectible", "context/cli/default")
    expect_runner_error(checks, "context/cli/invalid", lambda: validate_context_mode_cli(["--context-mode", "invalid"]))
    expect_runner_error(checks, "context/cli/missing-value", lambda: validate_context_mode_cli(["--context-mode"]))
    expect_runner_error(
        checks,
        "context/cli/duplicate",
        lambda: validate_context_mode_cli(["--context-mode", "collectible", "--context-mode", "resident"]),
    )
    expect_runner_error(checks, "context/cli/equals-form", lambda: validate_context_mode_cli(["--context-mode=resident"]))

def capture_sources(output: Path) -> dict:
    selected = [
        path
        for path in FIXTURE.rglob("*")
        if path.is_file()
        and path.suffix in (".cs", ".csproj", ".md")
        and not any(part in ("bin", "obj") for part in path.parts)
    ]
    selected.extend(
        [
            Path(__file__).resolve(),
            ROOT / "Directory.Build.props",
            ROOT / "src" / "RuneCLR.TrustedUpdate" / "RuneCLR.TrustedUpdate.csproj",
            ROOT / "src" / "RuneCLR.TrustedUpdate" / "TrustedModuleSession.cs",
        ]
    )
    hashes = {}
    seen = set()
    for path in selected:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        try:
            relative = path.resolve().relative_to(ROOT)
        except ValueError:
            relative = Path("external") / path.name
        destination = output / "source" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        hashes[relative.as_posix()] = sha256(path)
    save_json(output / "source-hashes.json", hashes)
    return hashes


def resolve_sdk(sdk_cmd, output, timeout, commands, commands_path) -> dict:
    result = {}
    for name, arguments in (
        ("version", ["--version"]),
        ("info", ["--info"]),
        ("list-sdks", ["--list-sdks"]),
        ("list-runtimes", ["--list-runtimes"]),
    ):
        record, stdout, stderr = run_process(
            "sdk-" + name,
            [sdk_cmd, *arguments],
            ROOT,
            timeout,
            output / "logs" / "sdk",
            commands,
            commands_path,
        )
        require_exit(record, "sdk-" + name)
        text = decode(stdout) + decode(stderr)
        (output / "logs" / "sdk" / (name + ".txt")).write_text(text, encoding="utf-8")
        result[name] = text.strip()
    return result


def build(name, project, sdk_cmd, artifacts_root, output, timeout, commands, commands_path, extra=()):
    command = [
        sdk_cmd,
        "build",
        str(project),
        "-c",
        "Release",
        f"-p:ArtifactsPath={artifacts_root}",
        "-p:UseArtifactsOutput=true",
        "-p:Deterministic=true",
        *extra,
    ]
    record, _, _ = run_process(
        name,
        command,
        ROOT,
        timeout,
        output / "logs" / "build",
        commands,
        commands_path,
    )
    require_exit(record, name)
    return record

def run_host(label, host_dll, module_dll, context_mode, sdk_cmd, output, timeout, commands, commands_path):
    run_dir = output / "runs" / label
    stage = run_dir / "module"
    stage.mkdir(parents=True, exist_ok=True)
    staged = stage / module_dll.name
    shutil.copy2(module_dll, staged)
    report_path = run_dir / "report.json"
    command = [
        sdk_cmd,
        str(host_dll),
        "--module",
        str(staged),
        "--variant",
        label,
        "--context-mode",
        context_mode,
        "--report",
        str(report_path),
    ]
    record, stdout, stderr = run_process(
        "host-" + label,
        command,
        run_dir,
        timeout,
        run_dir / "logs",
        commands,
        commands_path,
    )
    process_info = {
        "label": label,
        "command": [str(item) for item in command],
        "cwd": str(run_dir),
        "processId": record["processId"],
        "exitCode": record["exitCode"],
        "timedOut": record["timedOut"],
        "startedUtc": record["startedUtc"],
        "completedUtc": record["completedUtc"],
        "durationMs": record["durationMs"],
        "stdoutPath": record["stdoutPath"],
        "stderrPath": record["stderrPath"],
        "reportPath": str(report_path),
    }
    save_json(run_dir / "process.json", process_info)
    if record["exitCode"] != 0:
        if report_path.exists():
            failure = json.loads(report_path.read_text(encoding="utf-8-sig"))
            raise RunnerError(f"host {label} failed: {failure.get('error', failure)}")
        raise RunnerError(
            f"host {label} exited {record['exitCode']}; see {record['stderrPath']}"
        )
    if not report_path.exists():
        raise RunnerError(f"host {label} did not write {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    return {
        "record": record,
        "report": report,
        "dir": run_dir,
        "module": staged,
        "process": process_info,
    }


def validate_run(checks, label, run, expected_variant):
    report = run["report"]
    context = resolve_context_mode(report)
    check(checks, report.get("passed") is True, f"{label}/passed", str(report.get("error", "")))
    check(checks, report.get("variant") == expected_variant, f"{label}/variant", str(report.get("variant")))
    outcome = report["outcome"]
    check(checks, outcome.get("variant") == expected_variant, f"{label}/outcome-variant", str(outcome.get("variant")))

    check(
        checks,
        report["loadedModuleFullName"] == report["moduleReportedFullName"],
        f"{label}/module-identity-roundtrip",
    )
    check(
        checks,
        report["loadedModuleMvid"] == report["moduleReportedMvid"],
        f"{label}/module-mvid-roundtrip",
    )
    check(
        checks,
        assembly_name(report["loadedModuleFullName"]) == MODULE_ASSEMBLY,
        f"{label}/module-assembly-name",
        report["loadedModuleFullName"],
    )
    check(checks, outcome["moduleFullName"] == report["loadedModuleFullName"], f"{label}/outcome-module-full-name")
    check(checks, outcome["moduleMvid"] == report["loadedModuleMvid"], f"{label}/outcome-module-mvid")

    check(
        checks,
        assembly_name(report["contractFullName"]) == CONTRACT_ASSEMBLY,
        f"{label}/contract-assembly-name",
        report["contractFullName"],
    )
    check(checks, outcome["contractFullName"] == report["contractFullName"], f"{label}/shared-contract-full-name")
    check(checks, outcome["contractMvid"] == report["contractMvid"], f"{label}/shared-contract-mvid")

    check(
        checks,
        Path(report["modulePath"]).resolve() == run["module"].resolve(),
        f"{label}/module-path",
        report["modulePath"],
    )
    check(
        checks,
        report["moduleSha256"].lower() == sha256(run["module"]),
        f"{label}/module-sha256",
        report["moduleSha256"],
    )

    check(checks, outcome["lateTypeName"] == LATE_TYPE, f"{label}/late-type-name", outcome["lateTypeName"])
    check(checks, outcome["lateAssemblyName"] == MODULE_ASSEMBLY, f"{label}/late-assembly", outcome["lateAssemblyName"])
    check(checks, outcome["lateIsValueType"] is True, f"{label}/late-value-type")
    check(checks, report["lateProbe"]["typeName"] == LATE_TYPE, f"{label}/late-probe-name", report["lateProbe"]["typeName"])
    check(checks, report["lateProbe"]["assemblyName"] == MODULE_ASSEMBLY, f"{label}/late-probe-assembly")
    check(checks, report["lateProbe"]["isValueType"] is True, f"{label}/late-probe-value-type")

    expected_counts = {"echo": 2, "measure": 3, "fold": 1, "reduce": 1, "delegate": 1, "late": 1}
    check(checks, report["callCounts"] == expected_counts, f"{label}/call-counts", json.dumps(report["callCounts"]))
    check(checks, len(report["echoReferenceChecksums"]) == 2, f"{label}/reference-observations")
    check(checks, len(report["measureResults"]) == 3, f"{label}/struct-observations")
    check(checks, len(report["foldResults"]) == 1, f"{label}/nested-observations")
    check(checks, len(report["reduceResults"]) == 1, f"{label}/interface-observations")
    check(checks, len(report["delegateResults"]) == 1, f"{label}/delegate-observations")

    check(
        checks,
        outcome["referenceChecksum"] == report["echoReferenceChecksums"][1],
        f"{label}/checksum/reference",
    )
    expected_structs = int32(
        report["measureResults"][0] * 3
        + report["measureResults"][1] * 5
        + report["measureResults"][2] * 7
    )
    check(checks, outcome["structChecksum"] == expected_structs, f"{label}/checksum/structs")
    check(checks, outcome["nestedChecksum"] == report["foldResults"][0], f"{label}/checksum/nested")
    check(checks, outcome["interfaceChecksum"] == report["reduceResults"][0], f"{label}/checksum/interface")
    check(checks, outcome["delegateChecksum"] == report["delegateResults"][0], f"{label}/checksum/delegate")
    check(
        checks,
        outcome["lateChecksum"] == int32(report["lateProbe"]["digest"] + len(report["lateProbe"]["typeName"])),
        f"{label}/checksum/late",
    )

    check(checks, outcome["ledgerApplications"] == 6, f"{label}/module-ledger-applications")
    check(checks, report["ledger"]["applications"] == 6, f"{label}/host-ledger-applications")
    check(checks, outcome["ledgerTotal"] == report["ledger"]["total"], f"{label}/ledger-total")
    check(checks, outcome["aggregateChecksum"] == report["successValue"], f"{label}/session-return")

    check(checks, report["failureResult"] == "CallbackFailed", f"{label}/failure-result", report["failureResult"])
    check(checks, report["postFailureResult"] == "Closed", f"{label}/post-failure-result", report["postFailureResult"])
    check(checks, report["failureLedgerUnchanged"] is True, f"{label}/failure-ledger-unchanged")
    check(checks, report["sessionClosedAfterFailure"] is True, f"{label}/session-closed")
    check(checks, report["outcomesReported"] == 1, f"{label}/outcomes-reported")
    check(checks, report["invocations"] == 3, f"{label}/invocations")
    check(checks, context["requested"] in CONTEXT_MODES, f"{label}/context/requested", context["requested"])
    check(
        checks,
        context["isCollectible"] == (context["requested"] == "collectible"),
        f"{label}/context/collectible",
    )
    check(
        checks,
        context["unloadRequested"] == context["isCollectible"],
        f"{label}/context/unload",
    )
    check(checks, context["collectionClaimed"] is False, f"{label}/context/collection")
    check(checks, isinstance(report["processId"], int), f"{label}/process-id")
    check(checks, "--variant" in report["arguments"], f"{label}/arguments")
    check(
        checks,
        bool(report["runtime"]) and bool(report["osDescription"]) and bool(report["processArchitecture"]),
        f"{label}/environment",
    )

    references = [assembly_name(name) for name in report["hostReferences"]]
    check(checks, MODULE_ASSEMBLY not in references, f"{label}/host-references/no-module")
    check(checks, CONTRACT_ASSEMBLY in references, f"{label}/host-references/contract")
    check(checks, TRUSTED_UPDATE_ASSEMBLY in references, f"{label}/host-references/trusted-update")

    for snapshot_name in ("before", "afterSuccess", "afterFailure"):
        value = report[snapshot_name]
        check(
            checks,
            isinstance(value["managedBytes"], int) and value["managedBytes"] > 0,
            f"{label}/resident/{snapshot_name}/managed",
        )
        check(
            checks,
            isinstance(value["workingSetBytes"], int) and value["workingSetBytes"] > 0,
            f"{label}/resident/{snapshot_name}/working-set",
        )

    check(checks, report["successValue"] == outcome["aggregateChecksum"], f"{label}/aggregate")
    for key in SHAPE_KEYS:
        check(checks, isinstance(shape_value(outcome, key), int), f"{label}/shape/{key}")

    check(checks, len(report["measureTypes"]) == 3, f"{label}/measure-types/count")
    for suffix in ("ScoreVector", "ScorePair", "ScoreStamp"):
        check(checks, any(name.endswith(suffix) for name in report["measureTypes"]), f"{label}/measure-types/{suffix}")
    check(checks, len(report["reduceImplementations"]) == 1, f"{label}/reducer/count")
    check(
        checks,
        report["reduceImplementations"][0].endswith("VariantReducer"),
        f"{label}/reducer/type",
        report["reduceImplementations"][0],
    )

    validate_fixture_expectations(checks, label, report)

    return {
        "variant": expected_variant,
        "fixtureExpected": fixture_expected(label),
        "modulePath": report["modulePath"],
        "moduleSha256": report["moduleSha256"],
        "moduleFullName": report["loadedModuleFullName"],
        "moduleMvid": report["loadedModuleMvid"],
        "contractFullName": report["contractFullName"],
        "contractMvid": report["contractMvid"],
        "trustedUpdateFullName": report["trustedUpdateFullName"],
        "trustedUpdateMvid": report["trustedUpdateMvid"],
        "hostFullName": report["hostFullName"],
        "hostMvid": report["hostMvid"],
        "lateTypeName": outcome["lateTypeName"],
        "lateAssemblyName": outcome["lateAssemblyName"],
        "lateProbe": report["lateProbe"],
        "shapes": shape_values(outcome),
        "aggregate": outcome["aggregateChecksum"],
        "ledger": report["ledger"],
        "callCounts": report["callCounts"],
        "resident": {name: report[name] for name in ("before", "afterSuccess", "afterFailure")},
        "context": context,
        "failure": {
            "failureResult": report["failureResult"],
            "failureLedgerUnchanged": report["failureLedgerUnchanged"],
            "postFailureResult": report["postFailureResult"],
            "sessionClosedAfterFailure": report["sessionClosedAfterFailure"],
            "outcomesReported": report["outcomesReported"],
            "invocations": report["invocations"],
        },
        "processId": report["processId"],
    }

def validate_cross_run(checks, a, b):
    check(checks, a["moduleFullName"] == b["moduleFullName"], "A/B/same-assembly-identity")
    check(checks, a["moduleMvid"] != b["moduleMvid"], "A/B/different-mvid")
    check(checks, a["moduleSha256"] != b["moduleSha256"], "A/B/different-bytes")
    check(checks, a["processId"] != b["processId"], "A/B/fresh-process")
    for key in SHAPE_KEYS:
        check(
            checks,
            a["shapes"][key] != b["shapes"][key],
            f"A/B/different/{key}",
            f"{a['shapes'][key]} vs {b['shapes'][key]}",
        )
    check(checks, a["aggregate"] != b["aggregate"], "A/B/different/aggregate")
    check(checks, a["ledger"]["total"] != b["ledger"]["total"], "A/B/different/ledger-total")
    check(checks, a["ledger"]["applications"] == 6 and b["ledger"]["applications"] == 6, "A/B/six-effects")
    check(checks, a["lateProbe"]["digest"] != b["lateProbe"]["digest"], "A/B/different/late-digest")
    check(checks, a["contractMvid"] == b["contractMvid"], "A/B/same-contract-mvid")
    check(checks, a["context"]["requested"] == b["context"]["requested"], "A/B/same-context-mode")
    check(checks, a["context"]["format"] == b["context"]["format"], "A/B/same-context-format")

def write_validation(path: Path, summary: dict) -> None:
    lines = [
        "# Trusted-game generics validation",
        "",
        f"- Passed: {summary.get('passed')}",
        f"- Scope: {summary.get('scope')}",
        f"- SDK: {summary.get('sdk', {}).get('version', '')}",
        f"- Context mode: {summary.get('contextMode', '')}",
        f"- Output: {summary.get('output', '')}",
        "",
    ]
    if summary.get("error"):
        lines.extend(["## Error", "", summary["error"], ""])
    runs = summary.get("runs", {})
    if runs:
        lines.extend(
            [
                "## Per-shape results",
                "",
                "| Shape | A | B | Different |",
                "| --- | ---: | ---: | --- |",
            ]
        )
        for key in SHAPE_KEYS:
            a = runs["A"]["shapes"][key]
            b = runs["B"]["shapes"][key]
            lines.append(f"| {key} | {a} | {b} | {a != b} |")
        lines.append(
            f"| aggregate | {runs['A']['aggregate']} | {runs['B']['aggregate']} | "
            f"{runs['A']['aggregate'] != runs['B']['aggregate']} |"
        )
        lines.append(
            f"| ledger total | {runs['A']['ledger']['total']} | {runs['B']['ledger']['total']} | "
            f"{runs['A']['ledger']['total'] != runs['B']['ledger']['total']} |"
        )
        lines.extend(
            [
                "",
                "## Identity",
                "",
                f"- Module identity (A/B): {runs['A']['moduleFullName']}",
                f"- Module MVID A: {runs['A']['moduleMvid']}",
                f"- Module MVID B: {runs['B']['moduleMvid']}",
                f"- Contract identity: {runs['A']['contractFullName']}",
                f"- Contract MVID: {runs['A']['contractMvid']}",
                f"- Trusted update MVID: {runs['A']['trustedUpdateMvid']}",
                f"- Late type: {runs['A']['lateTypeName']} in {runs['A']['lateAssemblyName']}",
                "",
                "## Failure path",
                "",
                f"- A: {runs['A']['failure']['failureResult']} then "
                f"{runs['A']['failure']['postFailureResult']}, ledger unchanged="
                f"{runs['A']['failure']['failureLedgerUnchanged']}",
                f"- B: {runs['B']['failure']['failureResult']} then "
                f"{runs['B']['failure']['postFailureResult']}, ledger unchanged="
                f"{runs['B']['failure']['failureLedgerUnchanged']}",
                "",
                "## Resident observations",
                "",
                f"- A managed bytes before/after success/after failure: "
                f"{runs['A']['resident']['before']['managedBytes']} / "
                f"{runs['A']['resident']['afterSuccess']['managedBytes']} / "
                f"{runs['A']['resident']['afterFailure']['managedBytes']}",
                f"- B managed bytes before/after success/after failure: "
                f"{runs['B']['resident']['before']['managedBytes']} / "
                f"{runs['B']['resident']['afterSuccess']['managedBytes']} / "
                f"{runs['B']['resident']['afterFailure']['managedBytes']}",
                "",
            ]
        )
    checks = summary.get("checks", [])
    failures = [item for item in checks if not item["passed"]]
    lines.extend(
        [
            "## Checks",
            "",
            f"- {len(checks) - len(failures)}/{len(checks)} passed",
            f"- Failed: {len(failures)}",
            "",
            "## Remaining coverage",
            "",
        ]
    )
    for item in summary.get("remaining", []):
        lines.append(f"- {item}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_json(path: Path):
    if not path.is_file():
        raise RunnerError(f"missing retained file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as error:
        raise RunnerError(f"invalid retained JSON {path}: {error}") from error


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def pe_info(path: Path) -> dict:
    path = Path(path).resolve()
    key = str(path)
    if key in _PE_CACHE:
        return _PE_CACHE[key]

    data = path.read_bytes()

    def u16(offset):
        return struct.unpack_from("<H", data, offset)[0]

    def u32(offset):
        return struct.unpack_from("<I", data, offset)[0]

    pe = u32(0x3C)
    if data[pe:pe + 4] != b"PE\0\0":
        raise RunnerError(f"not a PE image: {path}")
    coff = pe + 4
    section_count = u16(coff + 2)
    optional_size = u16(coff + 16)
    optional = coff + 20
    magic = u16(optional)
    directories = optional + (112 if magic == 0x20B else 96)
    section_base = optional + optional_size
    sections = []
    for index in range(section_count):
        at = section_base + index * 40
        virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from("<IIII", data, at + 8)
        sections.append((virtual_address, max(virtual_size, raw_size), raw_offset))

    def file_offset(rva):
        for virtual_address, size, raw_offset in sections:
            if virtual_address <= rva < virtual_address + size:
                return raw_offset + rva - virtual_address
        raise RunnerError(f"RVA not mapped in {path}")

    cli = file_offset(u32(directories + 14 * 8))
    metadata = file_offset(u32(cli + 8))
    version_length = u32(metadata + 12)
    at = (metadata + 16 + version_length + 3) & ~3
    stream_count = u16(at + 2)
    at += 4
    streams = {}
    for _ in range(stream_count):
        stream_offset = u32(at)
        stream_size = u32(at + 4)
        end = data.index(b"\0", at + 8)
        name = data[at + 8:end].decode("ascii")
        streams[name] = (metadata + stream_offset, stream_size)
        at = (end + 4) & ~3

    tables_offset = streams["#~"][0]
    heap_sizes = data[tables_offset + 6]
    valid = struct.unpack_from("<Q", data, tables_offset + 8)[0]
    position = tables_offset + 24
    rows = {}
    for index in range(64):
        if (valid >> index) & 1:
            rows[index] = u32(position)
            position += 4
    string_size = 4 if heap_sizes & 1 else 2
    guid_size = 4 if heap_sizes & 2 else 2
    blob_size = 4 if heap_sizes & 4 else 2

    def table_index(table):
        return 4 if rows.get(table, 0) >= 65536 else 2

    coded_indexes = {
        "TypeDefOrRef": (2, [0x02, 0x01, 0x1B]),
        "HasConstant": (2, [0x04, 0x08, 0x17]),
        "HasCustomAttribute": (5, [0x06, 0x04, 0x01, 0x02, 0x08, 0x09, 0x0A, 0x00, 0x0E, 0x17, 0x14, 0x11, 0x1A, 0x1B, 0x20, 0x23, 0x26, 0x27, 0x28, 0x2A, 0x2B, 0x2C]),
        "HasFieldMarshal": (1, [0x04, 0x08]),
        "HasDeclSecurity": (2, [0x02, 0x06, 0x20]),
        "MemberRefParent": (3, [0x02, 0x01, 0x1A, 0x06, 0x1B]),
        "HasSemantics": (1, [0x14, 0x17]),
        "MethodDefOrRef": (1, [0x06, 0x0A]),
        "MemberForwarded": (1, [0x04, 0x06]),
        "Implementation": (2, [0x26, 0x23, 0x27]),
        "CustomAttributeType": (3, [0x06, 0x0A]),
        "ResolutionScope": (2, [0x00, 0x1A, 0x23, 0x01]),
        "TypeOrMethodDef": (1, [0x02, 0x06]),
    }

    def coded_size(name):
        bits, tables = coded_indexes[name]
        maximum = max(rows.get(table, 0) for table in tables)
        return 4 if maximum >= (1 << (16 - bits)) else 2

    schema = {
        0x00: [("u16", 0), ("str", 0), ("guid", 0), ("guid", 0), ("guid", 0)],
        0x01: [("c", "ResolutionScope"), ("str", 0), ("str", 0)],
        0x02: [("u32", 0), ("str", 0), ("str", 0), ("c", "TypeDefOrRef"), ("t", 0x04), ("t", 0x06)],
        0x03: [("t", 0x04)],
        0x04: [("u16", 0), ("str", 0), ("blob", 0)],
        0x05: [("t", 0x06)],
        0x06: [("u32", 0), ("u16", 0), ("u16", 0), ("str", 0), ("blob", 0), ("t", 0x08)],
        0x07: [("t", 0x08)],
        0x08: [("u16", 0), ("u16", 0), ("str", 0)],
        0x09: [("t", 0x02), ("c", "TypeDefOrRef")],
        0x0A: [("c", "MemberRefParent"), ("str", 0), ("blob", 0)],
        0x0B: [("u8", 0), ("u8", 0), ("c", "HasConstant"), ("blob", 0)],
        0x0C: [("c", "HasCustomAttribute"), ("c", "CustomAttributeType"), ("blob", 0)],
        0x0D: [("c", "HasFieldMarshal"), ("blob", 0)],
        0x0E: [("u16", 0), ("c", "HasDeclSecurity"), ("blob", 0)],
        0x0F: [("u16", 0), ("u32", 0), ("t", 0x02)],
        0x10: [("u32", 0), ("t", 0x04)],
        0x11: [("blob", 0)],
        0x12: [("t", 0x02), ("t", 0x14)],
        0x13: [("t", 0x14)],
        0x14: [("u16", 0), ("str", 0), ("c", "TypeDefOrRef")],
        0x15: [("t", 0x02), ("t", 0x17)],
        0x16: [("t", 0x17)],
        0x17: [("u16", 0), ("str", 0), ("blob", 0)],
        0x18: [("u16", 0), ("t", 0x06), ("c", "HasSemantics")],
        0x19: [("t", 0x02), ("c", "MethodDefOrRef"), ("c", "MethodDefOrRef")],
        0x1A: [("str", 0)],
        0x1B: [("blob", 0)],
        0x1C: [("u16", 0), ("c", "MemberForwarded"), ("str", 0), ("t", 0x1A)],
        0x1D: [("u32", 0), ("t", 0x04)],
        0x1E: [("u32", 0), ("u32", 0)],
        0x1F: [("u32", 0)],
        0x20: [("u32", 0), ("u16", 0), ("u16", 0), ("u16", 0), ("u16", 0), ("u32", 0), ("blob", 0), ("str", 0), ("str", 0)],
        0x21: [("u32", 0)],
        0x22: [("u32", 0), ("u32", 0), ("u32", 0)],
        0x23: [("u16", 0), ("u16", 0), ("u16", 0), ("u16", 0), ("u32", 0), ("blob", 0), ("str", 0), ("str", 0), ("blob", 0)],
    }

    def column_size(kind, argument):
        if kind == "u8":
            return 1
        if kind == "u16":
            return 2
        if kind == "u32":
            return 4
        if kind == "str":
            return string_size
        if kind == "guid":
            return guid_size
        if kind == "blob":
            return blob_size
        if kind == "t":
            return table_index(argument)
        if kind == "c":
            return coded_size(argument)
        raise RunnerError(f"unknown metadata column {kind}")

    def row_size(table):
        return sum(column_size(kind, argument) for kind, argument in schema[table])

    offsets = {}
    cursor = position
    for table in range(0x24):
        if table in rows:
            offsets[table] = cursor
            cursor += rows[table] * row_size(table)

    def read_string(index):
        base = streams["#Strings"][0]
        end = data.index(b"\0", base + index)
        return data[base + index:end].decode("utf-8")

    def read_index(offset, size):
        return u16(offset) if size == 2 else u32(offset)

    def read_guid(index):
        base = streams["#GUID"][0]
        return uuid.UUID(bytes_le=data[base + 16 * (index - 1):base + 16 * index])

    module_offset = offsets[0x00] + 2
    module_name = read_string(read_index(module_offset, string_size))
    module_mvid = read_guid(read_index(module_offset + string_size, guid_size))

    assembly_name_value = None
    assembly_version = None
    assembly_culture = None
    public_key_index = 0
    if 0x20 in rows:
        offset = offsets[0x20]
        offset += 4
        major = u16(offset)
        minor = u16(offset + 2)
        build = u16(offset + 4)
        revision = u16(offset + 6)
        offset += 8
        offset += 4
        public_key_index = read_index(offset, blob_size)
        offset += blob_size
        name_index = read_index(offset, string_size)
        offset += string_size
        culture_index = read_index(offset, string_size)
        assembly_name_value = read_string(name_index)
        assembly_version = (major, minor, build, revision)
        assembly_culture = read_string(culture_index)

    references = []
    if 0x23 in rows:
        for index in range(rows[0x23]):
            offset = offsets[0x23] + index * row_size(0x23)
            offset += 12
            offset += blob_size
            name_index = read_index(offset, string_size)
            references.append(read_string(name_index))

    types = []
    if 0x02 in rows:
        for index in range(rows[0x02]):
            offset = offsets[0x02] + index * row_size(0x02)
            offset += 4
            name_index = read_index(offset, string_size)
            offset += string_size
            namespace_index = read_index(offset, string_size)
            name = read_string(name_index)
            namespace = read_string(namespace_index)
            types.append(namespace + "." + name if namespace else name)

    result = {
        "path": str(path),
        "module": module_name,
        "mvid": str(module_mvid),
        "assembly": assembly_name_value,
        "version": assembly_version,
        "culture": assembly_culture,
        "publicKeyIndex": public_key_index,
        "refs": references,
        "types": types,
    }
    _PE_CACHE[key] = result
    return result


def pe_full_name(info):
    name = info["assembly"]
    version = info["version"]
    culture = info["culture"] or "neutral"
    token = "null" if info["publicKeyIndex"] == 0 else "non-null"
    return f"{name}, Version={version[0]}.{version[1]}.{version[2]}.{version[3]}, Culture={culture}, PublicKeyToken={token}"

def validate_retained_sources(checks, retained: Path, source_hashes: dict) -> dict:
    check(checks, isinstance(source_hashes, dict) and bool(source_hashes), "retained/source-hashes/nonempty")
    source_dir = retained / "source"
    check(checks, source_dir.is_dir(), "retained/source/exists")
    for relative, expected in source_hashes.items():
        path = source_dir / relative
        check(checks, path.is_file(), f"retained/source/{relative}/exists")
        check(checks, sha256(path) == expected, f"retained/source/{relative}/hash", str(path))
    return {"root": str(source_dir), "files": len(source_hashes)}


def validate_retained_commands(checks, commands, retained: Path) -> dict:
    build_commands = [item for item in commands if item.get("name", "").startswith("build-")]
    host_commands = [item for item in commands if item.get("name", "").startswith("host-")]
    check(checks, len(build_commands) == 3, "retained/commands/three-builds", str(len(build_commands)))
    check(checks, len(host_commands) == 2, "retained/commands/two-hosts", str(len(host_commands)))
    check(
        checks,
        [item["name"] for item in build_commands] == ["build-host", "build-module-a", "build-module-b"],
        "retained/commands/build-order",
        json.dumps([item["name"] for item in build_commands]),
    )
    check(
        checks,
        [item["name"] for item in host_commands] == ["host-A", "host-B"],
        "retained/commands/host-order",
        json.dumps([item["name"] for item in host_commands]),
    )
    check(checks, all(item.get("exitCode") == 0 for item in build_commands), "retained/commands/build-exits")
    check(checks, all(item.get("exitCode") == 0 for item in host_commands), "retained/commands/host-exits")
    for item in commands:
        for key in ("stdoutPath", "stderrPath"):
            path = Path(item[key])
            check(checks, is_inside(path, retained), f"retained/commands/{item['name']}/{key}/inside")
            check(checks, path.is_file(), f"retained/commands/{item['name']}/{key}/exists")
    host_build = build_commands[0]["command"]
    check(
        checks,
        any("TrustedGameGenerics.Host.csproj" in str(part) for part in host_build),
        "retained/commands/host-build/project",
    )
    check(
        checks,
        not any("BuildProjectReferences=false" in str(part) for part in host_build),
        "retained/commands/host-build/rebuilds-references",
    )
    for item in build_commands[1:]:
        check(
            checks,
            any("BuildProjectReferences=false" in str(part) for part in item["command"]),
            f"retained/commands/{item['name']}/no-dependencies",
        )
    for item in host_commands:
        label = item["name"][-1]
        check(checks, "--variant" in item["command"], f"retained/commands/{item['name']}/variant-flag")
        check(
            checks,
            item["command"][item["command"].index("--variant") + 1] == label,
            f"retained/commands/{item['name']}/variant-value",
        )
    return {
        "builds": [{"name": item["name"], "exitCode": item["exitCode"]} for item in build_commands],
        "hosts": [{"name": item["name"], "exitCode": item["exitCode"]} for item in host_commands],
        "total": len(commands),
    }


def expected_host_arguments(report, label, run_dir: Path):
    context = resolve_context_mode(report)
    arguments = [
        report.get("hostPath"),
        "--module",
        report.get("modulePath"),
        "--variant",
        label,
    ]
    if context["format"] == "new":
        arguments.extend(["--context-mode", context["requested"]])
    arguments.extend(["--report", str((run_dir / "report.json").resolve())])
    return arguments

def validate_retained_process(checks, label, report, process, run_dir: Path) -> None:
    check(checks, process.get("label") == label, f"{label}/process/label", str(process.get("label")))
    check(checks, process.get("processId") == report.get("processId"), f"{label}/process/pid")
    check(checks, process.get("exitCode") == 0, f"{label}/process/exit", str(process.get("exitCode")))
    check(checks, process.get("timedOut") is False, f"{label}/process/timeout")
    command = process.get("command", [])
    check(checks, len(command) > 1, f"{label}/process/command-length")
    expected_arguments = expected_host_arguments(report, label, run_dir)
    check(checks, report.get("arguments") == expected_arguments, f"{label}/process/arguments-exact", json.dumps(report.get("arguments")))
    check(checks, command == [command[0]] + expected_arguments, f"{label}/process/command-exact", json.dumps(command))
    check(checks, "--variant" in command, f"{label}/process/variant-flag")
    check(
        checks,
        command[command.index("--variant") + 1] == label,
        f"{label}/process/variant-value",
    )
    check(
        checks,
        any(str(part).endswith(MODULE_ASSEMBLY + ".dll") for part in command),
        f"{label}/process/module-argument",
    )
    check(
        checks,
        Path(process.get("reportPath", "")).resolve() == (run_dir / "report.json").resolve(),
        f"{label}/process/report-path",
    )
    stdout_path = Path(process.get("stdoutPath", ""))
    stderr_path = Path(process.get("stderrPath", ""))
    check(checks, stdout_path.is_file(), f"{label}/process/stdout-exists")
    check(checks, stderr_path.is_file(), f"{label}/process/stderr-exists")
    check(checks, stdout_path.stat().st_size > 0, f"{label}/process/stdout-nonempty")


def validate_retained_outputs(checks, reports, runs) -> None:
    for label in ("A", "B"):
        report = reports[label]
        host_path = Path(report["hostPath"])
        contract_path = Path(report["contractPath"])
        trusted_update_path = Path(report["trustedUpdatePath"])
        module_path = runs[label]["module"]
        check(checks, host_path.is_file(), f"{label}/replay/host-exists")
        check(checks, contract_path.is_file(), f"{label}/replay/contract-exists")
        check(checks, trusted_update_path.is_file(), f"{label}/replay/trusted-update-exists")
        check(checks, module_path.is_file(), f"{label}/replay/module-exists")
        host_dir = host_path.parent
        host_files = [path.name for path in host_dir.iterdir() if path.is_file()]
        check(
            checks,
            not any(name.startswith(MODULE_ASSEMBLY) for name in host_files),
            f"{label}/replay/host-output/no-module",
            json.dumps(host_files),
        )
        host_deps = host_dir / (HOST_PROJECT_NAME + ".deps.json")
        check(checks, host_deps.is_file(), f"{label}/replay/host-deps/exists")
        check(
            checks,
            MODULE_ASSEMBLY not in host_deps.read_text(encoding="utf-8-sig"),
            f"{label}/replay/host-deps/no-module",
        )
        host_bytes = host_path.read_bytes()
        contract_bytes = contract_path.read_bytes()
        module_bytes = module_path.read_bytes()
        check(checks, b"LateToken" not in host_bytes, f"{label}/replay/late-type/absent-host")
        check(checks, b"LateToken" not in contract_bytes, f"{label}/replay/late-type/absent-contract")
        check(checks, b"LateToken" in module_bytes, f"{label}/replay/late-type/present-module")
        check(checks, LATE_TYPE.encode("ascii") not in host_bytes, f"{label}/replay/late-type/full-name-absent-host")


def validate_retained_preservation(checks, retained: Path) -> dict:
    snapshots = {}
    for name in ("after-host", "after-module-a", "after-module-b"):
        snapshots[name] = read_json(retained / "build" / "snapshots" / (name + ".json"))
    check(
        checks,
        snapshots["after-host"] == snapshots["after-module-a"] == snapshots["after-module-b"],
        "retained/preservation/snapshots-equal",
    )
    return {
        "stable": True,
        "groups": {
            name: {group: len(files) for group, files in value.items()}
            for name, value in snapshots.items()
        },
    }

def validate_command_process_join(checks, label, commands, process):
    name = "host-" + label
    records = [item for item in commands if item.get("name") == name]
    check(checks, len(records) == 1, f"{label}/command-join/one-record", str(len(records)))
    record = records[0]
    check(checks, record.get("processId") == process.get("processId"), f"{label}/command-join/pid")
    check(checks, record.get("exitCode") == process.get("exitCode"), f"{label}/command-join/exit")
    check(checks, record.get("command") == process.get("command"), f"{label}/command-join/argv")
    check(checks, record.get("stdoutPath") == process.get("stdoutPath"), f"{label}/command-join/stdout")
    check(checks, record.get("stderrPath") == process.get("stderrPath"), f"{label}/command-join/stderr")


def validate_artifact_binding(checks, label, report, run_dir: Path, retained: Path) -> None:
    host_path = (retained / "build" / "artifacts" / "bin" / HOST_PROJECT_NAME / "release" / "TrustedGameGenerics.Host.dll").resolve()
    contract_project = (retained / "build" / "artifacts" / "bin" / CONTRACT_PROJECT_NAME / "release" / "TrustedGameGenerics.Contracts.dll").resolve()
    trusted_project = (retained / "build" / "artifacts" / "bin" / TRUSTED_UPDATE_PROJECT_NAME / "release" / "RuneCLR.TrustedUpdate.dll").resolve()
    module_project_name = MODULE_A_PROJECT_NAME if label == "A" else MODULE_B_PROJECT_NAME
    module_project = (retained / "build" / "artifacts" / "bin" / module_project_name / "release" / "TrustedGameGenerics.Module.dll").resolve()
    staged_module = (run_dir / "module" / "TrustedGameGenerics.Module.dll").resolve()
    contract_copy = (host_path.parent / "TrustedGameGenerics.Contracts.dll").resolve()
    trusted_copy = (host_path.parent / "RuneCLR.TrustedUpdate.dll").resolve()

    check(checks, Path(report.get("hostPath", "")).resolve() == host_path, f"{label}/artifact/host-path")
    check(checks, Path(report.get("contractPath", "")).resolve() == contract_copy, f"{label}/artifact/contract-copy-path")
    check(checks, Path(report.get("trustedUpdatePath", "")).resolve() == trusted_copy, f"{label}/artifact/trusted-update-copy-path")
    check(checks, Path(report.get("modulePath", "")).resolve() == staged_module, f"{label}/artifact/staged-module-path")
    for name, path in (("host", host_path), ("contract", contract_project), ("trusted-update", trusted_project), ("module", module_project), ("staged", staged_module)):
        check(checks, path.is_file(), f"{label}/artifact/{name}/exists", str(path))

    host_pe = pe_info(host_path)
    contract_pe = pe_info(contract_project)
    trusted_pe = pe_info(trusted_project)
    module_pe = pe_info(module_project)

    check(checks, report.get("hostFullName") == HOST_FULL_NAME, f"{label}/artifact/host-full-name", str(report.get("hostFullName")))
    check(checks, pe_full_name(host_pe) == HOST_FULL_NAME, f"{label}/artifact/host-pe-full-name", pe_full_name(host_pe))
    check(checks, host_pe["mvid"] == report.get("hostMvid"), f"{label}/artifact/host-pe-mvid", host_pe["mvid"])
    check(checks, report.get("contractFullName") == CONTRACT_FULL_NAME, f"{label}/artifact/contract-full-name", str(report.get("contractFullName")))
    check(checks, pe_full_name(contract_pe) == CONTRACT_FULL_NAME, f"{label}/artifact/contract-pe-full-name", pe_full_name(contract_pe))
    check(checks, contract_pe["mvid"] == report.get("contractMvid"), f"{label}/artifact/contract-pe-mvid", contract_pe["mvid"])
    check(checks, report.get("trustedUpdateFullName") == TRUSTED_UPDATE_FULL_NAME, f"{label}/artifact/trusted-update-full-name", str(report.get("trustedUpdateFullName")))
    check(checks, pe_full_name(trusted_pe) == TRUSTED_UPDATE_FULL_NAME, f"{label}/artifact/trusted-update-pe-full-name", pe_full_name(trusted_pe))
    check(checks, trusted_pe["mvid"] == report.get("trustedUpdateMvid"), f"{label}/artifact/trusted-update-pe-mvid", trusted_pe["mvid"])

    check(checks, report.get("loadedModuleFullName") == MODULE_FULL_NAME, f"{label}/artifact/module-full-name", str(report.get("loadedModuleFullName")))
    check(checks, report.get("moduleReportedFullName") == MODULE_FULL_NAME, f"{label}/artifact/module-reported-full-name")
    check(checks, pe_full_name(module_pe) == MODULE_FULL_NAME, f"{label}/artifact/module-pe-full-name", pe_full_name(module_pe))
    check(checks, module_pe["mvid"] == report.get("loadedModuleMvid"), f"{label}/artifact/module-pe-mvid", module_pe["mvid"])
    check(checks, module_pe["mvid"] == report.get("moduleReportedMvid"), f"{label}/artifact/module-reported-mvid")

    expected = fixture_expected(label)
    check(checks, report.get("reduceImplementations") == [expected["reducerType"]], f"{label}/artifact/reducer-type", json.dumps(report.get("reduceImplementations")))
    check(checks, expected["reducerType"] in module_pe["types"], f"{label}/artifact/reducer-in-module-metadata", expected["reducerType"])
    check(checks, assembly_name(report.get("loadedModuleFullName", "")) == expected["reducerAssembly"], f"{label}/artifact/reducer-assembly")
    check(checks, LATE_TYPE in module_pe["types"], f"{label}/artifact/late-type-in-module-metadata", LATE_TYPE)

    check(checks, MODULE_ASSEMBLY not in host_pe["refs"], f"{label}/artifact/host-metadata/no-module", json.dumps(host_pe["refs"]))
    check(checks, CONTRACT_ASSEMBLY in host_pe["refs"], f"{label}/artifact/host-metadata/contract", json.dumps(host_pe["refs"]))
    check(checks, TRUSTED_UPDATE_ASSEMBLY in host_pe["refs"], f"{label}/artifact/host-metadata/trusted-update", json.dumps(host_pe["refs"]))
    check(checks, CONTRACT_ASSEMBLY in module_pe["refs"], f"{label}/artifact/module-metadata/contract", json.dumps(module_pe["refs"]))
    check(checks, HOST_PROJECT_NAME not in module_pe["refs"], f"{label}/artifact/module-metadata/no-host", json.dumps(module_pe["refs"]))
    check(checks, TRUSTED_UPDATE_ASSEMBLY not in module_pe["refs"], f"{label}/artifact/module-metadata/no-trusted-update", json.dumps(module_pe["refs"]))

    snapshots = read_json(retained / "build" / "snapshots" / "after-host.json")
    host_hash = sha256(host_path)
    contract_hash = sha256(contract_project)
    trusted_hash = sha256(trusted_project)
    module_hash = sha256(module_project)
    check(checks, host_hash == snapshots["host"]["TrustedGameGenerics.Host.dll"]["sha256"], f"{label}/artifact/host-hash-binding", host_hash)
    check(checks, contract_hash == snapshots["contracts"]["TrustedGameGenerics.Contracts.dll"]["sha256"], f"{label}/artifact/contract-hash-binding", contract_hash)
    check(checks, trusted_hash == snapshots["trustedUpdate"]["RuneCLR.TrustedUpdate.dll"]["sha256"], f"{label}/artifact/trusted-update-hash-binding", trusted_hash)
    check(checks, sha256(contract_copy) == contract_hash, f"{label}/artifact/contract-copy-hash")
    check(checks, sha256(trusted_copy) == trusted_hash, f"{label}/artifact/trusted-update-copy-hash")
    check(checks, sha256(staged_module) == module_hash, f"{label}/artifact/staged-module-hash")
    check(checks, report.get("moduleSha256", "").lower() == module_hash, f"{label}/artifact/report-module-hash", module_hash)

    outcome = report["outcome"]
    check(checks, outcome.get("moduleFullName") == MODULE_FULL_NAME, f"{label}/artifact/outcome-module-full-name")
    check(checks, outcome.get("moduleMvid") == module_pe["mvid"], f"{label}/artifact/outcome-module-mvid")
    check(checks, outcome.get("contractFullName") == CONTRACT_FULL_NAME, f"{label}/artifact/outcome-contract-full-name")
    check(checks, outcome.get("contractMvid") == contract_pe["mvid"], f"{label}/artifact/outcome-contract-mvid")


def offline_case_checks(root: Path, report, process, commands):
    checks = []
    label = report["variant"]
    run_dir = root / "runs" / label
    validate_retained_commands(checks, commands, root)
    validate_retained_process(checks, label, report, process, run_dir)
    validate_command_process_join(checks, label, commands, process)
    run = {"report": report, "module": Path(report["modulePath"]), "dir": run_dir, "process": process}
    validate_run(checks, label, run, label)
    validate_artifact_binding(checks, label, report, run_dir, root)
    return checks

def write_replay_validation(path: Path, replay: dict) -> None:
    historical = replay.get("historical", {})
    lines = [
        "# Offline replay validation",
        "",
        f"- Replay passed: {replay.get('passed')}",
        f"- Retained root: {replay.get('retainedRoot')}",
        f"- Historical campaign status: {historical.get('campaignPassed')}",
        f"- Historical error: {historical.get('campaignError')}",
        f"- Scope: {replay.get('scope')}",
        f"- Expectation basis: {replay.get('expectationBasis')}",
        "",
    ]
    runs = replay.get("runs", {})
    if runs:
        lines.extend([
            "## Per-shape results",
            "",
            "| Shape | A | B | Different |",
            "| --- | ---: | ---: | --- |",
        ])
        for key in SHAPE_KEYS:
            a = runs["A"]["shapes"][key]
            b = runs["B"]["shapes"][key]
            lines.append(f"| {key} | {a} | {b} | {a != b} |")
        lines.append(
            f"| aggregate | {runs['A']['aggregate']} | {runs['B']['aggregate']} | "
            f"{runs['A']['aggregate'] != runs['B']['aggregate']} |"
        )
        lines.append(
            f"| ledger total | {runs['A']['ledger']['total']} | {runs['B']['ledger']['total']} | "
            f"{runs['A']['ledger']['total'] != runs['B']['ledger']['total']} |"
        )
        lines.extend([
            "",
            "## Identity",
            "",
            f"- Module identity (A/B): {runs['A']['moduleFullName']}",
            f"- Module MVID A: {runs['A']['moduleMvid']}",
            f"- Module MVID B: {runs['B']['moduleMvid']}",
            f"- Contract identity: {runs['A']['contractFullName']}",
            f"- Contract MVID: {runs['A']['contractMvid']}",
            f"- Trusted update MVID: {runs['A']['trustedUpdateMvid']}",
            "",
        ])
    if runs:
        expected_a = runs["A"].get("fixtureExpected", {})
        expected_b = runs["B"].get("fixtureExpected", {})
        if expected_a and expected_b:
            lines.extend([
                "",
                "## Fixture expectations",
                "",
                f"- A echo types: {expected_a.get('echoTypes')}",
                f"- B echo types: {expected_b.get('echoTypes')}",
                f"- A echo checksums: {expected_a.get('echoReferenceChecksums')}",
                f"- B echo checksums: {expected_b.get('echoReferenceChecksums')}",
                f"- A measure types: {expected_a.get('measureTypes')}",
                f"- B measure types: {expected_b.get('measureTypes')}",
                f"- A measure results: {expected_a.get('measureResults')}",
                f"- B measure results: {expected_b.get('measureResults')}",
                f"- Reducer type: {expected_a.get('reducerType')} in {expected_a.get('reducerAssembly')}",
                f"- A late digest: {expected_a.get('lateDigest')}; B late digest: {expected_b.get('lateDigest')}",
                f"- A ledger/aggregate: {expected_a.get('ledgerTotal')}/{expected_a.get('aggregate')}",
                f"- B ledger/aggregate: {expected_b.get('ledgerTotal')}/{expected_b.get('aggregate')}",
                "- Basis: fixture-specific source-input recomputation; not general generic correctness.",
                "",
            ])
    if runs:
        lines.extend([
            "",
            "## Context modes",
            "",
            f"- A: {json.dumps(runs['A'].get('context', {}))}",
            f"- B: {json.dumps(runs['B'].get('context', {}))}",
            "",
        ])
    commands = replay.get("commands", {})
    if commands:
        lines.extend([
            "## Retained commands",
            "",
            f"- Builds: {commands.get('builds')}",
            f"- Hosts: {commands.get('hosts')}",
            f"- Total recorded commands: {commands.get('total')}",
            "",
        ])
    source = replay.get("sourceSnapshot", {})
    if source:
        lines.extend([
            "## Source snapshot",
            "",
            f"- Files verified: {source.get('files')}",
            f"- Root: {source.get('root')}",
            "",
        ])
    preservation = replay.get("preservation", {})
    if preservation:
        lines.extend([
            "## Build preservation",
            "",
            f"- Stable: {preservation.get('stable')}",
            f"- Groups: {preservation.get('groups')}",
            "",
        ])
    execution = replay.get("execution", {})
    if execution:
        lines.extend([
            "## Replay execution",
            "",
            f"- Builds: {execution.get('builds')}",
            f"- Host executions: {execution.get('hosts')}",
            f"- SDK calls: {execution.get('sdkCalls')}",
            f"- Subprocesses: {execution.get('subprocesses')}",
            "",
        ])
    pins = replay.get("pins", {})
    lines.extend([
        "## Pins",
        "",
        f"- Before/after unchanged: {pins.get('unchanged')}",
        f"- Files pinned: {len(pins.get('before', {}))}",
        "",
    ])
    checks = replay.get("checks", [])
    failures = [item for item in checks if not item["passed"]]
    lines.extend([
        "## Checks",
        "",
        f"- {len(checks) - len(failures)}/{len(checks)} passed",
        f"- Failed: {len(failures)}",
        "",
        "## Limits",
        "",
        "- This replay reads retained files only. It launches no subprocess, SDK, build, or Host.",
        "- Historical campaign status is preserved in replay.json; the replay result is separate.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def replay_campaign(retained: Path, output: Path) -> int:
    if not retained.is_dir():
        print(f"replay root not found: {retained}", file=sys.stderr)
        return 2
    if output.exists():
        print(f"refusing to reuse existing output: {output}", file=sys.stderr)
        return 2
    if is_inside(output, retained):
        print("replay output must not be inside the retained root", file=sys.stderr)
        return 2
    if is_inside(retained, output):
        print("replay output must not contain the retained root", file=sys.stderr)
        return 2
    output.mkdir(parents=True, exist_ok=False)
    checks = []
    before = snapshot(retained)
    replay = {
        "mode": "offline-replay",
        "passed": False,
        "retainedRoot": str(retained),
        "output": str(output),
        "scope": "offline validation of retained evidence; no builds, Host executions, SDK calls, or subprocesses",
        "expectationBasis": "fixture-specific source-input recomputation; not a general generic-correctness oracle",
        "execution": {"builds": 0, "hosts": 0, "sdkCalls": 0, "subprocesses": 0},
        "historical": {},
        "sourceSnapshot": {},
        "commands": {},
        "runs": {},
        "preservation": {},
        "pins": {},
        "checks": checks,
    }
    try:
        historical = read_json(retained / "summary.json")
        replay["historical"] = {
            "campaignPassed": historical.get("passed"),
            "campaignError": historical.get("error"),
            "output": historical.get("output"),
            "buildCount": len(historical.get("builds", [])),
            "checksRecorded": len(historical.get("checks", [])),
            "sdkVersion": historical.get("sdk", {}).get("version"),
            "head": historical.get("commits", {}).get("head"),
            "note": "Retained campaign status is historical and is not overwritten.",
        }
        check(
            checks,
            Path(historical.get("output", "")).resolve() == retained.resolve(),
            "retained/summary-output",
        )
        check(checks, len(historical.get("builds", [])) == 3, "retained/summary-build-count")
        commands = read_json(retained / "commands.json")
        replay["commands"] = validate_retained_commands(checks, commands, retained)
        source_hashes = read_json(retained / "source-hashes.json")
        replay["sourceSnapshot"] = validate_retained_sources(checks, retained, source_hashes)
        check(checks, historical.get("sources") == source_hashes, "retained/summary-sources-match")
        replay["preservation"] = validate_retained_preservation(checks, retained)
        reports = {}
        runs = {}
        for label in ("A", "B"):
            run_dir = retained / "runs" / label
            report = read_json(run_dir / "report.json")
            process = read_json(run_dir / "process.json")
            validate_retained_process(checks, label, report, process, run_dir)
            validate_command_process_join(checks, label, commands, process)
            validate_artifact_binding(checks, label, report, run_dir, retained)
            module_path = Path(report["modulePath"])
            check(checks, is_inside(module_path, retained), f"{label}/module-inside-retained", str(module_path))
            check(checks, module_path.is_file(), f"{label}/module-exists", str(module_path))
            staged_files = [path.name for path in (run_dir / "module").iterdir() if path.is_file()]
            check(
                checks,
                staged_files == [MODULE_ASSEMBLY + ".dll"],
                f"{label}/staged-module/only-module",
                json.dumps(staged_files),
            )
            runs[label] = {"report": report, "module": module_path, "dir": run_dir, "process": process}
            reports[label] = report
        a = validate_run(checks, "A", runs["A"], "A")
        b = validate_run(checks, "B", runs["B"], "B")
        validate_cross_run(checks, a, b)
        replay["runs"] = {"A": a, "B": b}
        validate_retained_outputs(checks, reports, runs)
        replay["passed"] = True
    except RunnerError as error:
        replay["error"] = str(error)
    except Exception:
        replay["error"] = traceback.format_exc()
    finally:
        after = snapshot(retained)
        replay["pins"] = {
            "kind": "non-key-file-pins-sha256-size-mtime",
            "before": before,
            "after": after,
            "unchanged": before == after,
            "filesBefore": len(before),
            "filesAfter": len(after),
        }
        if replay["passed"] and not replay["pins"]["unchanged"]:
            replay["passed"] = False
            replay["error"] = "retained files changed during replay"
        save_json(output / "pins.before.json", before)
        save_json(output / "pins.after.json", after)
        save_json(output / "replay.json", replay)
        write_replay_validation(output / "VALIDATION-REPLAY.md", replay)
    print(json.dumps({
        "passed": replay["passed"],
        "output": str(output),
        "retainedRoot": str(retained),
        "historicalPassed": replay.get("historical", {}).get("campaignPassed"),
        "checks": len(checks),
        "error": replay.get("error"),
    }, indent=2))
    return 0 if replay["passed"] else 1

def offline_mutation_checks(root: Path, report, process, commands, checks):
    def set_report(path, value):
        def mutate(target_report, target_process, target_commands):
            target = target_report
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
        return mutate

    def set_report_item(path, index, value):
        def mutate(target_report, target_process, target_commands):
            target = target_report
            for key in path[:-1]:
                target = target[key]
            target[path[-1]][index] = value
        return mutate

    def swap_report_item(path, index):
        def mutate(target_report, target_process, target_commands):
            target = target_report
            for key in path[:-1]:
                target = target[key]
            items = target[path[-1]]
            items[index], items[index + 1] = items[index + 1], items[index]
        return mutate

    def set_process(key, value):
        def mutate(target_report, target_process, target_commands):
            target_process[key] = value
        return mutate

    def set_host_command(key, value):
        def mutate(target_report, target_process, target_commands):
            record = next(item for item in target_commands if item.get("name") == "host-A")
            record[key] = value
        return mutate

    def set_build_exit(value):
        def mutate(target_report, target_process, target_commands):
            record = next(item for item in target_commands if item.get("name") == "build-host")
            record["exitCode"] = value
        return mutate

    def remove_module_no_deps(target_report, target_process, target_commands):
        record = next(item for item in target_commands if item.get("name") == "build-module-a")
        record["command"] = [part for part in record["command"] if "BuildProjectReferences=false" not in str(part)]

    def set_host_variant(target_report, target_process, target_commands):
        record = next(item for item in target_commands if item.get("name") == "host-A")
        index = record["command"].index("--variant")
        record["command"][index + 1] = "B"

    def set_host_stdout_missing(target_report, target_process, target_commands):
        record = next(item for item in target_commands if item.get("name") == "host-A")
        record["stdoutPath"] = str(root / "missing.stdout")

    mutations = [
        ("echo-types", set_report_item(["echoTypes"], 0, "Other.EchoType")),
        ("echo-initial-checksum", set_report_item(["echoReferenceChecksums"], 0, 0)),
        ("echo-final-checksum", set_report_item(["echoReferenceChecksums"], 1, 0)),
        ("measure-types-order", swap_report_item(["measureTypes"], 0)),
        ("measure-vector", set_report_item(["measureResults"], 0, 0)),
        ("measure-pair", set_report_item(["measureResults"], 1, 0)),
        ("measure-stamp", set_report_item(["measureResults"], 2, 0)),
        ("reducer-type", set_report_item(["reduceImplementations"], 0, "Other.Reducer")),
        ("late-digest", set_report(["lateProbe", "digest"], 0)),
        ("late-type-name", set_report(["lateProbe", "typeName"], "Other.LateToken")),
        ("late-assembly", set_report(["lateProbe", "assemblyName"], "Other")),
        ("late-is-value-type", set_report(["lateProbe", "isValueType"], False)),
        ("shape-reference", set_report(["outcome", "referenceChecksum"], 0)),
        ("shape-structs", set_report(["outcome", "structChecksum"], 0)),
        ("shape-nested", set_report(["outcome", "nestedChecksum"], 0)),
        ("shape-interface", set_report(["outcome", "interfaceChecksum"], 0)),
        ("shape-delegate", set_report(["outcome", "delegateChecksum"], 0)),
        ("shape-late", set_report(["outcome", "lateChecksum"], 0)),
        ("aggregate", set_report(["outcome", "aggregateChecksum"], 0)),
        ("success-value", set_report(["successValue"], 0)),
        ("ledger-total", set_report(["ledger", "total"], 0)),
        ("ledger-applications", set_report(["ledger", "applications"], 5)),
        ("outcome-ledger-total", set_report(["outcome", "ledgerTotal"], 0)),
        ("outcome-ledger-applications", set_report(["outcome", "ledgerApplications"], 5)),
        ("host-full-name", set_report(["hostFullName"], "Other.Host")),
        ("host-mvid", set_report(["hostMvid"], "00000000-0000-0000-0000-000000000000")),
        ("host-path", set_report(["hostPath"], str(root / "other-host.dll"))),
        ("contract-full-name", set_report(["contractFullName"], "Other.Contracts")),
        ("contract-mvid", set_report(["contractMvid"], "00000000-0000-0000-0000-000000000000")),
        ("contract-path", set_report(["contractPath"], str(root / "other-contracts.dll"))),
        ("trusted-full-name", set_report(["trustedUpdateFullName"], "Other.TrustedUpdate")),
        ("trusted-mvid", set_report(["trustedUpdateMvid"], "00000000-0000-0000-0000-000000000000")),
        ("trusted-path", set_report(["trustedUpdatePath"], str(root / "other-trusted.dll"))),
        ("loaded-module-full-name", set_report(["loadedModuleFullName"], "Other.Module")),
        ("loaded-module-mvid", set_report(["loadedModuleMvid"], "00000000-0000-0000-0000-000000000000")),
        ("module-reported-full-name", set_report(["moduleReportedFullName"], "Other.Module")),
        ("module-reported-mvid", set_report(["moduleReportedMvid"], "00000000-0000-0000-0000-000000000000")),
        ("module-sha256", set_report(["moduleSha256"], "0" * 64)),
        ("module-path", set_report(["modulePath"], str(root / "other-module.dll"))),
        ("outcome-module-full-name", set_report(["outcome", "moduleFullName"], "Other.Module")),
        ("outcome-module-mvid", set_report(["outcome", "moduleMvid"], "00000000-0000-0000-0000-000000000000")),
        ("outcome-contract-full-name", set_report(["outcome", "contractFullName"], "Other.Contracts")),
        ("outcome-contract-mvid", set_report(["outcome", "contractMvid"], "00000000-0000-0000-0000-000000000000")),
        ("process-id", set_report(["processId"], 0)),
        ("arguments", set_report(["arguments"], [])),
        ("host-references-module", lambda target_report, target_process, target_commands: target_report["hostReferences"].append(MODULE_FULL_NAME)),
        ("failure-result", set_report(["failureResult"], "None")),
        ("post-failure-result", set_report(["postFailureResult"], "None")),
        ("failure-ledger-unchanged", set_report(["failureLedgerUnchanged"], False)),
        ("session-closed", set_report(["sessionClosedAfterFailure"], False)),
        ("outcomes-reported", set_report(["outcomesReported"], 2)),
        ("invocations", set_report(["invocations"], 2)),
        ("collection-claimed", set_report(["collectionClaimed"], True)),
        ("unload-requested", set_report(["unloadRequested"], False)),
        ("outcome-late-type", set_report(["outcome", "lateTypeName"], "Other.LateToken")),
        ("outcome-late-assembly", set_report(["outcome", "lateAssemblyName"], "Other")),
        ("outcome-late-value-type", set_report(["outcome", "lateIsValueType"], False)),
        ("process-pid-json", set_process("processId", 0)),
        ("process-argv-json", lambda target_report, target_process, target_commands: target_process["command"].append("--extra")),
        ("command-join-pid", set_host_command("processId", 0)),
        ("command-join-exit", set_host_command("exitCode", 1)),
        ("command-join-argv", set_host_command("command", [])),
        ("commands-build-exit", set_build_exit(1)),
        ("commands-module-no-deps", remove_module_no_deps),
        ("commands-host-variant", set_host_variant),
        ("commands-stdout-missing", set_host_stdout_missing),
    ]

    caught = 0
    for name, mutate in mutations:
        mutated_report = copy.deepcopy(report)
        mutated_process = copy.deepcopy(process)
        mutated_commands = copy.deepcopy(commands)
        try:
            mutate(mutated_report, mutated_process, mutated_commands)
            offline_case_checks(root, mutated_report, mutated_process, mutated_commands)
        except RunnerError as error:
            caught += 1
            checks.append({"name": f"mutation/{name}/rejected", "passed": True, "detail": str(error)})
        else:
            check(checks, False, f"mutation/{name}/rejected", "mutation was not rejected")
    return len(mutations), caught

def self_test(root=None) -> int:
    checks = []
    try:
        check(checks, set(SHAPE_KEYS) == set(SHAPE_PROPERTIES), "shape-mapping/coverage")
        check(checks, SHAPE_PROPERTIES["structs"] == "structChecksum", "shape-mapping/structs-singular")
        sample = {SHAPE_PROPERTIES[key]: index + 1 for index, key in enumerate(SHAPE_KEYS)}
        expected = {key: index + 1 for index, key in enumerate(SHAPE_KEYS)}
        check(checks, shape_values(sample) == expected, "shape-mapping/values")
        try:
            shape_value({"structsChecksum": 2}, "structs")
        except RunnerError as error:
            message = str(error)
            check(
                checks,
                "structChecksum" in message and "structs" in message,
                "shape-mapping/plural-report-fails-clearly",
                message,
            )
        else:
            check(checks, False, "shape-mapping/plural-report-fails-clearly")

        for variant in ("A", "B"):
            expected_fixture = fixture_expected(variant)
            golden = FIXTURE_GOLDEN[variant]
            check(checks, expected_fixture["echoReferenceChecksums"] == golden["echoReferenceChecksums"],
                  f"fixture-golden/{variant}/echo-reference")
            check(checks, expected_fixture["measureResults"] == golden["measureResults"],
                  f"fixture-golden/{variant}/measure-results")
            check(checks, expected_fixture["shapes"] == golden["shapes"],
                  f"fixture-golden/{variant}/shapes", json.dumps(expected_fixture["shapes"]))
            check(checks, expected_fixture["lateDigest"] == golden["lateDigest"],
                  f"fixture-golden/{variant}/late-digest")
            check(checks, expected_fixture["ledgerTotal"] == golden["ledger"],
                  f"fixture-golden/{variant}/ledger")
            check(checks, expected_fixture["aggregate"] == golden["aggregate"],
                  f"fixture-golden/{variant}/aggregate")

        context_mode_checks(checks)

        keys = ("DOTNET_REPLAY_SELF_TEST", "dotnet_replay_self_test")
        for key in keys:
            os.environ[key] = "1"
        try:
            env = clean_env()
            for key in keys:
                check(checks, key not in env, f"clean-env/removes/{key}")
        finally:
            for key in keys:
                os.environ.pop(key, None)

        if root is None:
            check(checks, True, "mutation/skipped-no-root", "no --self-test-root supplied")
            result = {
                "passed": True,
                "checks": checks,
                "mutationRoot": None,
                "baseChecks": 0,
                "mutations": {
                    "status": "SKIPPED",
                    "attempted": 0,
                    "caught": 0,
                    "reason": "no --self-test-root supplied",
                },
            }
            print(json.dumps(result, indent=2))
            return 0

        candidate = Path(root)
        if not candidate.is_dir():
            raise RunnerError(f"--self-test-root is not a directory: {candidate}")
        required = [
            candidate / "commands.json",
            candidate / "runs" / "A" / "report.json",
            candidate / "runs" / "A" / "process.json",
        ]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise RunnerError("--self-test-root is missing required retained files: " + ", ".join(missing))
        candidate = candidate.resolve()
        check(checks, True, "mutation/root-available", str(candidate))
        report = read_json(candidate / "runs" / "A" / "report.json")
        process = read_json(candidate / "runs" / "A" / "process.json")
        commands = read_json(candidate / "commands.json")
        base_checks = offline_case_checks(
            candidate,
            copy.deepcopy(report),
            copy.deepcopy(process),
            copy.deepcopy(commands),
        )
        failures = [item for item in base_checks if not item["passed"]]
        check(checks, not failures, "mutation/base-case/passes", f"{len(base_checks)} checks")
        for mode in CONTEXT_MODES:
            synthetic = copy.deepcopy(report)
            synthetic["arguments"] = [
                report["hostPath"],
                "--module",
                report["modulePath"],
                "--variant",
                "A",
                "--context-mode",
                mode,
                "--report",
                str((candidate / "runs" / "A" / "report.json").resolve()),
            ]
            synthetic["requestedContextMode"] = mode
            synthetic["contextIsCollectible"] = mode == "collectible"
            synthetic["unloadRequested"] = mode == "collectible"
            synthetic["collectionClaimed"] = False
            synthetic_checks = []
            validate_run(
                synthetic_checks,
                "A",
                {"report": synthetic, "module": Path(report["modulePath"]), "dir": candidate / "runs" / "A"},
                "A",
            )
            synthetic_failures = [item for item in synthetic_checks if not item["passed"]]
            check(
                checks,
                not synthetic_failures,
                f"context/full/{mode}/positive",
                f"{len(synthetic_checks)} checks",
            )

        for missing_name, missing_fields in (
            ("missing-unload", ("unloadRequested",)),
            ("missing-collection", ("collectionClaimed",)),
            ("missing-both", ("unloadRequested", "collectionClaimed")),
        ):
            mutated = copy.deepcopy(report)
            for field in missing_fields:
                del mutated[field]
            expect_runner_error(
                checks,
                f"context/full/historical/{missing_name}",
                lambda mutated=mutated: validate_run(
                    [],
                    "A",
                    {"report": mutated, "module": Path(report["modulePath"]), "dir": candidate / "runs" / "A"},
                    "A",
                ),
            )
        attempted, caught = offline_mutation_checks(candidate, report, process, commands, checks)
        result = {
            "passed": True,
            "checks": checks,
            "mutationRoot": str(candidate),
            "baseChecks": len(base_checks),
            "mutations": {"status": "RUN", "attempted": attempted, "caught": caught},
        }
        print(json.dumps(result, indent=2))
        return 0
    except RunnerError as error:
        print(json.dumps({"passed": False, "error": str(error), "checks": checks}, indent=2))
        return 1

def self_test_portability(root=None) -> int:
    results = {
        "passed": False,
        "subprocessPatched": False,
        "pathDiscoveryPatchedForDefault": True,
        "default": {},
        "invalid": {},
        "explicit": {},
    }
    original_subprocess = {}
    original_is_dir = Path.is_dir

    def raise_subprocess(*args, **kwargs):
        raise AssertionError("subprocess entrypoint was called")

    def raise_is_dir(self):
        raise AssertionError("filesystem root discovery was attempted by default self-test")

    try:
        for name in ("Popen", "run", "call", "check_call", "check_output"):
            original_subprocess[name] = getattr(subprocess, name)
            setattr(subprocess, name, raise_subprocess)
        results["subprocessPatched"] = True

        Path.is_dir = raise_is_dir
        try:
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                default_code = self_test(None)
            default_output = stream.getvalue()
        finally:
            Path.is_dir = original_is_dir
        default_result = json.loads(default_output)
        results["default"] = {
            "exit": default_code,
            "passed": default_result.get("passed"),
            "checks": len(default_result.get("checks", [])),
            "mutations": default_result.get("mutations"),
        }

        invalid_root = ROOT / "artifacts" / "self-test-invalid-root-does-not-exist"
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            invalid_code = self_test(invalid_root)
        invalid_result = json.loads(stream.getvalue())
        results["invalid"] = {
            "exit": invalid_code,
            "passed": invalid_result.get("passed"),
            "error": invalid_result.get("error", ""),
        }

        if root is None:
            results["explicit"] = {"status": "SKIPPED", "reason": "no --self-test-root supplied"}
        else:
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                explicit_code = self_test(root)
            explicit_result = json.loads(stream.getvalue())
            results["explicit"] = {
                "exit": explicit_code,
                "passed": explicit_result.get("passed"),
                "checks": len(explicit_result.get("checks", [])),
                "mutations": explicit_result.get("mutations"),
                "mutationRoot": explicit_result.get("mutationRoot"),
            }

        checks = []
        check(
            checks,
            default_code == 0
            and results["default"]["passed"] is True
            and results["default"]["checks"] == 64
            and results["default"]["mutations"].get("status") == "SKIPPED",
            "portability/default",
            json.dumps(results["default"]),
        )
        check(
            checks,
            invalid_code == 1
            and results["invalid"]["passed"] is False
            and "--self-test-root" in results["invalid"].get("error", ""),
            "portability/explicit-invalid",
            json.dumps(results["invalid"]),
        )
        if root is None:
            check(checks, True, "portability/explicit-valid/skipped")
        else:
            check(
                checks,
                explicit_code == 0
                and results["explicit"]["passed"] is True
                and results["explicit"]["checks"] == 136
                and results["explicit"]["mutations"].get("attempted") == 66
                and results["explicit"]["mutations"].get("caught") == 66,
                "portability/explicit-valid",
                json.dumps(results["explicit"]),
            )
        results["checks"] = checks
        results["passed"] = True
    except Exception as error:
        results["error"] = f"{type(error).__name__}: {error}"
    finally:
        for name, value in original_subprocess.items():
            setattr(subprocess, name, value)
        Path.is_dir = original_is_dir
    print(json.dumps(results, indent=2))
    return 0 if results["passed"] else 1

def main(argv=None) -> int:
    if sys.version_info < (3, 8):
        print("This runner requires Python 3.8 or newer.", file=sys.stderr)
        return 2
    try:
        cli_context_mode = validate_context_mode_cli(argv)
    except RunnerError as error:
        print(str(error), file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="fresh output directory")
    parser.add_argument("--sdk", default="dotnet", help="dotnet CLI to invoke")
    parser.add_argument("--timeout", type=float, default=180.0, help="per-process timeout in seconds")
    parser.add_argument("--context-mode", choices=CONTEXT_MODES, default="collectible", help="Host AssemblyLoadContext mode")
    parser.add_argument("--self-test", action="store_true", help="run offline runner regressions; no subprocess")
    parser.add_argument("--self-test-portability", action="store_true", help="test portable default and explicit self-test paths; no subprocess")
    parser.add_argument("--self-test-root", type=Path, help="retained campaign root for offline mutation tests")
    parser.add_argument("--replay-root", type=Path, help="retained campaign root to validate offline")
    args = parser.parse_args(argv)
    args.context_mode = cli_context_mode

    if args.self_test_portability:
        return self_test_portability(args.self_test_root)
    if args.self_test:
        return self_test(args.self_test_root)
    if args.replay_root is not None:
        if args.output is None:
            print("--replay-root requires --output", file=sys.stderr)
            return 2
        return replay_campaign(args.replay_root.resolve(), args.output.resolve())

    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    default_output = ROOT / "artifacts" / "trusted-game-generics" / f"{stamp}-{os.getpid()}"
    output = (args.output or default_output).resolve()
    if output.exists():
        print(f"refusing to reuse existing output: {output}", file=sys.stderr)
        return 2
    output.mkdir(parents=True, exist_ok=False)
    commands = []
    commands_path = output / "commands.json"
    save_json(commands_path, commands)
    checks = []
    summary = {
        "passed": False,
        "scope": "stock SDK managed generic compatibility; not R2R, interpreter, execution-mode, unloading, or mobile proof",
        "fixture": str(FIXTURE.relative_to(ROOT)),
        "output": str(output),
        "contextMode": args.context_mode,
        "commits": {},
        "sdk": {},
        "builds": [],
        "runs": {},
        "preservation": {},
        "checks": checks,
        "remaining": [
            "R2R specialization and execute-method behavior for these generic shapes",
            "interpreter fallback and execution-mode attribution",
            "assembly unload and collection claims; this run only asserts session close and reports CollectionClaimed=false",
            "iOS and physical-device delivery",
            "hostile-code and restricted-UGC capability behavior",
        ],
    }

    try:
        summary["sources"] = capture_sources(output)

        head_record, head_stdout, _ = run_process(
            "git-head",
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            ROOT,
            args.timeout,
            output / "logs" / "git",
            commands,
            commands_path,
        )
        require_exit(head_record, "git-head")
        summary["commits"]["head"] = decode(head_stdout).strip()
        status_record, status_stdout, _ = run_process(
            "git-status",
            ["git", "-C", str(ROOT), "status", "--porcelain"],
            ROOT,
            args.timeout,
            output / "logs" / "git",
            commands,
            commands_path,
        )
        require_exit(status_record, "git-status")
        summary["commits"]["status"] = decode(status_stdout)

        summary["sdk"] = resolve_sdk(
            args.sdk, output, args.timeout, commands, commands_path
        )
        check(checks, bool(summary["sdk"]["version"]), "sdk/version")

        artifacts_root = output / "build" / "artifacts"
        summary["artifactsRoot"] = str(artifacts_root)

        summary["builds"].append(
            build(
                "build-host",
                HOST_PROJECT,
                args.sdk,
                artifacts_root,
                output,
                args.timeout,
                commands,
                commands_path,
            )
        )
        host_dll = artifact_dll(artifacts_root, HOST_PROJECT_NAME, HOST_PROJECT_NAME)
        contracts_dll = artifact_dll(artifacts_root, CONTRACT_PROJECT_NAME, CONTRACT_PROJECT_NAME)
        trusted_update_dll = artifact_dll(artifacts_root, TRUSTED_UPDATE_PROJECT_NAME, TRUSTED_UPDATE_PROJECT_NAME)
        host_dir = host_dll.parent
        contracts_dir = contracts_dll.parent
        trusted_update_dir = trusted_update_dll.parent
        after_host = snapshot_inputs(host_dir, contracts_dir, trusted_update_dir)
        save_json(output / "build" / "snapshots" / "after-host.json", after_host)

        summary["builds"].append(
            build(
                "build-module-a",
                MODULE_A_PROJECT,
                args.sdk,
                artifacts_root,
                output,
                args.timeout,
                commands,
                commands_path,
                ["-p:BuildProjectReferences=false"],
            )
        )
        module_a_dll = artifact_dll(artifacts_root, MODULE_A_PROJECT_NAME, MODULE_ASSEMBLY)
        after_a = snapshot_inputs(host_dir, contracts_dir, trusted_update_dir)
        save_json(output / "build" / "snapshots" / "after-module-a.json", after_a)
        compare_snapshots(after_host, after_a, "module A late build")
        check(checks, after_host == after_a, "late-build/A/preserves-host-contract-trusted-update")

        summary["builds"].append(
            build(
                "build-module-b",
                MODULE_B_PROJECT,
                args.sdk,
                artifacts_root,
                output,
                args.timeout,
                commands,
                commands_path,
                ["-p:BuildProjectReferences=false"],
            )
        )
        module_b_dll = artifact_dll(artifacts_root, MODULE_B_PROJECT_NAME, MODULE_ASSEMBLY)
        after_b = snapshot_inputs(host_dir, contracts_dir, trusted_update_dir)
        save_json(output / "build" / "snapshots" / "after-module-b.json", after_b)
        compare_snapshots(after_host, after_b, "module B late build")
        check(checks, after_host == after_b, "late-build/B/preserves-host-contract-trusted-update")
        summary["preservation"] = {
            "afterHost": after_host,
            "afterModuleA": after_a,
            "afterModuleB": after_b,
            "stable": after_host == after_a == after_b,
        }

        host_text = HOST_PROJECT.read_text(encoding="utf-8-sig")
        check(checks, "../Contracts/TrustedGameGenerics.Contracts.csproj" in host_text, "host/project-reference/contract")
        check(
            checks,
            "../../../src/RuneCLR.TrustedUpdate/RuneCLR.TrustedUpdate.csproj" in host_text,
            "host/project-reference/trusted-update",
        )
        check(checks, "Module.A" not in host_text, "host/no-module-a-reference")
        check(checks, "Module.B" not in host_text, "host/no-module-b-reference")

        host_files = [path.name for path in host_dir.iterdir() if path.is_file()]
        check(
            checks,
            not any(name.startswith(MODULE_ASSEMBLY) for name in host_files),
            "host/output/no-module",
            json.dumps(host_files),
        )
        host_deps = host_dir / (HOST_PROJECT_NAME + ".deps.json")
        check(checks, host_deps.exists(), "host/deps/exists")
        check(
            checks,
            MODULE_ASSEMBLY not in host_deps.read_text(encoding="utf-8-sig"),
            "host/deps/no-module",
        )

        host_bytes = host_dll.read_bytes()
        contract_bytes = contracts_dll.read_bytes()
        module_a_bytes = module_a_dll.read_bytes()
        module_b_bytes = module_b_dll.read_bytes()
        check(checks, b"LateToken" not in host_bytes, "late-type/absent-from-host")
        check(checks, b"LateToken" not in contract_bytes, "late-type/absent-from-contracts")
        check(checks, b"LateToken" in module_a_bytes, "late-type/present-in-module-a")
        check(checks, b"LateToken" in module_b_bytes, "late-type/present-in-module-b")
        check(checks, LATE_TYPE.encode("ascii") not in host_bytes, "late-type/full-name-absent-from-host")

        run_a = run_host(
            "A", host_dll, module_a_dll, args.context_mode, args.sdk, output, args.timeout, commands, commands_path
        )
        run_b = run_host(
            "B", host_dll, module_b_dll, args.context_mode, args.sdk, output, args.timeout, commands, commands_path
        )
        a = validate_run(checks, "A", run_a, "A")
        b = validate_run(checks, "B", run_b, "B")
        summary["runs"] = {"A": a, "B": b}

        validate_cross_run(checks, a, b)

        for label, run in (("A", run_a), ("B", run_b)):
            staged_files = [path.name for path in (run["dir"] / "module").iterdir() if path.is_file()]
            check(
                checks,
                staged_files == [MODULE_ASSEMBLY + ".dll"],
                f"{label}/staged-module/only-module",
                json.dumps(staged_files),
            )

        build_commands = [item for item in commands if item["name"].startswith("build-")]
        host_commands = [item for item in commands if item["name"].startswith("host-")]
        check(checks, len(build_commands) == 3, "builds/exactly-three")
        check(checks, len(host_commands) == 2, "hosts/exactly-two")
        check(checks, all(item["exitCode"] == 0 for item in build_commands), "builds/zero-exit")
        check(checks, all(item["exitCode"] == 0 for item in host_commands), "hosts/zero-exit")

        summary["passed"] = True
    except RunnerError as error:
        summary["error"] = str(error)
    except Exception:
        summary["error"] = traceback.format_exc()
    finally:
        save_json(output / "summary.json", summary)
        write_validation(output / "VALIDATION.md", summary)

    print(json.dumps({
        "passed": summary["passed"],
        "output": str(output),
        "error": summary.get("error"),
        "checks": len(checks),
    }, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())