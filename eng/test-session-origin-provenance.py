#!/usr/bin/env python3
"""Provenance negatives for the session-origin driver (source-manifest mode).

Builds tiny throwaway git repositories and layout/build fixtures; no runtime or
product sources are read or written. The published verifier is not involved.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

NL = chr(10)
BACKSLASH = chr(92)
CASES = 0


def load_driver(root):
    path = root / "eng/verify-runtime-session-origin.py"
    spec = importlib.util.spec_from_file_location("session_origin_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(root, *args, check=True):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError("git " + " ".join(args) + " failed: " + result.stderr.strip())
    return result.stdout.strip()


def commit(root, message):
    run(root, "-c", "user.name=session-origin", "-c", "user.email=session-origin@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-q", "-m", message)


def digest_bytes(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def new_repo(base):
    repo = base / "repo"
    repo.mkdir(parents=True)
    run(repo, "init", "-q", "-b", "main")
    (repo / "src").mkdir()
    (repo / "src/x.cs").write_text("new" + NL, encoding="utf-8")
    (repo / "src/gone.cs").write_text("gone" + NL, encoding="utf-8")
    (repo / "a.txt").write_text("stable" + NL, encoding="utf-8")
    run(repo, "add", "-A")
    commit(repo, "base")
    base_commit = run(repo, "rev-parse", "HEAD")
    (repo / "src/x.cs").write_text("changed" + NL, encoding="utf-8")
    (repo / "src/new.cs").write_text("added" + NL, encoding="utf-8")
    return repo, base_commit


def manifest_for(repo, base_commit, names):
    return {"base": base_commit, "head": run(repo, "rev-parse", "HEAD"),
            "files": {name: digest_bytes(repo / name) for name in names}}


def expect_reject(label, call, contains):
    global CASES
    CASES += 1
    try:
        call()
    except ValueError as error:
        if contains.lower() not in str(error).lower():
            return label + ": rejected with unexpected message: " + str(error)
        print("PASS reject", label, "->", str(error).split(":")[0][:80])
        return None
    return label + ": was accepted but must be rejected"


def expect_accept(label, call):
    global CASES
    CASES += 1
    try:
        call()
    except Exception as error:
        return label + ": failed unexpectedly: " + str(error)
    print("PASS accept", label)
    return None


def native_fixture(base):
    build = base / "build"
    layout = base / "layout"
    shared = layout / "shared/Microsoft.NETCore.App/12.0.0"
    (build / "IL").mkdir(parents=True)
    shared.mkdir(parents=True)
    for name in ("coreclr.dll", "clrjit.dll", "clrinterpreter.dll", "corerun.exe"):
        (build / name).write_bytes(("built-" + name).encode())
        (shared / name).write_bytes(("built-" + name).encode())
    (build / "IL/System.Private.CoreLib.dll").write_bytes(b"built-corelib")
    (shared / "System.Private.CoreLib.dll").write_bytes(b"built-corelib")
    return build, layout, build / "IL/System.Private.CoreLib.dll"



def committed_fixture(base):
    """Synthetic repository: base commit, five-file integration commit, four raw and one canonical build form."""
    repo = base / "committed"
    repo.mkdir()
    run(repo, "init", "-q", "-b", "main")
    run(repo, "config", "core.autocrlf", "true")
    names = ["src/f1.cs", "src/f2.cs", "src/f3.cs", "src/f4.cs", "src/f5.cs"]
    for index, name in enumerate(names):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_bytes(("base-" + str(index) + NL).encode())
    run(repo, "add", "-A")
    commit(repo, "base")
    base_commit = run(repo, "rev-parse", "HEAD")
    for index, name in enumerate(names[:4]):
        (repo / name).write_bytes(("built-" + str(index) + chr(13) + NL).encode())
    (repo / names[4]).write_bytes(("built-" + str(4) + NL).encode())
    run(repo, "add", "-A")
    commit(repo, "integration")
    integration = run(repo, "rev-parse", "HEAD")
    # the canonical build form for the fifth file, materialised as CRLF by the checkout;
    # refreshing the index clears git's stat-cache entry without changing the blob
    (repo / names[4]).write_bytes(("built-" + str(4) + chr(13) + NL).encode())
    run(repo, "add", "--", names[4])
    if run(repo, "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("fixture worktree is unexpectedly dirty")
    canonical = {}
    build = {}
    relations = {}
    for index, name in enumerate(names):
        blob = subprocess.run(["git", "-C", str(repo), "show", integration + ":" + name], capture_output=True).stdout
        canonical[name] = hashlib.sha256(blob).hexdigest()
        if index < 4:
            build[name] = digest_bytes(repo / name)
            relations[name] = "raw"
        else:
            build[name] = hashlib.sha256(("built-" + str(4) + NL).encode()).hexdigest()
            relations[name] = "normalized-canonical"
    receipt = {"schema": "runeclr.session-origin.committed-source.v1",
               "buildSource": {"head": base_commit, "files": build},
               "integration": {"commit": integration, "parent": base_commit, "files": canonical},
               "binaries": {"coreclr.dll": "a" * 64, "clrjit.dll": "b" * 64,
                            "clrinterpreter.dll": "c" * 64, "corerun.exe": "d" * 64,
                            "System.Private.CoreLib.dll": "e" * 64},
               "relations": relations}
    return repo, receipt, integration


def committed_cases(base, driver):
    failures = []
    repo, receipt, integration = committed_fixture(base)
    receipt_path = base / "committed-receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    loaded = driver.load_committed_receipt(receipt_path)
    original_base = driver.RUNTIME_BASE
    driver.RUNTIME_BASE = receipt["buildSource"]["head"]
    try:
        def accept_shape():
            head, changed, relations = driver.verify_committed_source(repo, loaded)
            if head != integration or len(changed) != 5:
                raise ValueError("unexpected head or changed set")
            raw = [p for p, r in relations.items() if r == "raw"]
            normalized = [p for p, r in relations.items() if r == "normalized-canonical"]
            if len(raw) != 4 or len(normalized) != 1:
                raise ValueError("expected four raw and one normalized-canonical relation, got " + repr(relations))
        failures.append(expect_accept("committed source with four raw and one normalized-canonical file", accept_shape))

        wrong_source = copy.deepcopy(loaded)
        first = sorted(wrong_source["build"]["files"])[0]
        wrong_source["build"]["files"][first] = "0" * 64
        failures.append(expect_reject("committed wrong build source",
                                      lambda: driver.verify_committed_source(repo, wrong_source),
                                      "do not match the recorded build source"))

        wrong_parent = copy.deepcopy(loaded)
        wrong_parent["integration"]["parent"] = "1" * 40
        wrong_parent["build"]["head"] = "1" * 40
        failures.append(expect_reject("committed wrong parent",
                                      lambda: driver.verify_committed_source(repo, wrong_parent),
                                      "must equal the receipt parent"))

        inconsistent = json.loads(json.dumps(receipt))
        inconsistent["integration"]["parent"] = "2" * 40
        receipt_path = base / "inconsistent.json"
        receipt_path.write_text(json.dumps(inconsistent), encoding="utf-8")
        failures.append(expect_reject("committed inconsistent parent",
                                      lambda: driver.load_committed_receipt(receipt_path),
                                      "must equal buildSource.head"))

        (repo / "UNTRACKED.txt").write_text("dirty" + NL, encoding="utf-8")
        failures.append(expect_reject("committed unexpected dirty tree",
                                      lambda: driver.verify_committed_source(repo, loaded),
                                      "must be clean"))
        (repo / "UNTRACKED.txt").unlink()

        observed = dict(receipt["binaries"])
        expected = dict(observed)
        expected["coreclr.dll"] = "f" * 64
        global CASES
        CASES += 1
        problems = driver.check_binary_identity(observed, expected)
        failures.append(None if any("Binary hash mismatch for coreclr.dll" in p for p in problems)
                        else "committed binary mismatch was not detected")
        if not any("Binary hash mismatch for coreclr.dll" in p for p in problems):
            print("FAIL binary mismatch detection")
        else:
            print("PASS reject committed binary mismatch")

        drift_path = base / "receipt-drift.json"
        drift_path.write_text(json.dumps(receipt), encoding="utf-8")
        consumed = driver.load_committed_receipt(drift_path)
        copy_path = base / "receipt-copy.json"
        copy_path.write_bytes(consumed["raw"])
        drift_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        CASES += 1
        drift = driver.check_consumed_source(drift_path, consumed["sha256"], copy_path)
        failures.append(None if any("changed during the run" in p for p in drift)
                        else "receipt drift was not detected")
        if not any("changed during the run" in p for p in drift):
            print("FAIL receipt drift detection")
        else:
            print("PASS reject receipt drift")

        other_copy = base / "receipt-copy-other.json"
        other_copy.write_text("different" + NL, encoding="utf-8")
        CASES += 1
        mismatch = driver.check_consumed_source(drift_path, consumed["sha256"], other_copy)
        failures.append(None if any("copy does not match" in p for p in mismatch)
                        else "receipt copy mismatch was not detected")
        if not any("copy does not match" in p for p in mismatch):
            print("FAIL receipt copy mismatch detection")
        else:
            print("PASS reject receipt copy mismatch")
    finally:
        driver.RUNTIME_BASE = original_base
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    driver = load_driver(root)
    base = (args.workdir or Path(tempfile.mkdtemp(prefix="session-origin-provenance-"))).resolve()
    base.mkdir(parents=True, exist_ok=True)

    failures = []
    repo, base_commit = new_repo(base)
    manifest = manifest_for(repo, base_commit, ["src/x.cs", "src/new.cs"])

    failures.append(expect_accept("exact delta and hashes", lambda: driver.verify_source_manifest(repo, manifest)))

    extra = dict(manifest)
    extra["files"] = dict(manifest["files"])
    (repo / "src/extra.cs").write_text("extra" + NL, encoding="utf-8")
    failures.append(expect_reject("extra source", lambda: driver.verify_source_manifest(repo, extra), "outside the source manifest"))
    (repo / "src/extra.cs").unlink()

    wrong = dict(manifest)
    wrong["files"] = dict(manifest["files"])
    wrong["files"]["src/x.cs"] = "0" * 64
    failures.append(expect_reject("changed hash", lambda: driver.verify_source_manifest(repo, wrong), "hash mismatch"))

    wrong_head = dict(manifest)
    wrong_head["head"] = "1" * 40
    failures.append(expect_reject("head mismatch", lambda: driver.verify_source_manifest(repo, wrong_head), "must equal the source manifest head"))

    manifest_path = base / "manifest.json"
    manifest_path.write_text(json.dumps({"base": "0" * 40, "head": manifest["head"],
                                         "files": manifest["files"]}), encoding="utf-8")
    failures.append(expect_reject("base mismatch", lambda: driver.load_source_manifest(manifest_path), "base must be"))

    for label, name in (("path escape parent", "../escape.cs"),
                        ("path escape absolute", "/tmp/escape.cs"),
                        ("path escape drive", "C:/escape.cs"),
                        ("path escape backslash", "src" + BACKSLASH + "escape.cs")):
        manifest_path.write_text(json.dumps({"base": driver.RUNTIME_BASE, "head": manifest["head"],
                                             "files": {name: "a" * 64}}), encoding="utf-8")
        failures.append(expect_reject(label, lambda: driver.load_source_manifest(manifest_path), "escapes"))

    noop = dict(manifest)
    noop["files"] = dict(manifest["files"])
    noop["files"]["a.txt"] = digest_bytes(repo / "a.txt")
    failures.append(expect_reject("unchanged entry", lambda: driver.verify_source_manifest(repo, noop), "without a runtime change"))

    gone = dict(manifest)
    gone["files"] = dict(manifest["files"])
    gone["files"]["src/gone.cs"] = digest_bytes(repo / "src/gone.cs")
    (repo / "src/gone.cs").unlink()
    failures.append(expect_reject("deleted source", lambda: driver.verify_source_manifest(repo, gone), "rejects deletions"))

    failures.append(expect_reject("clean-commit mode unchanged",
                                  lambda: driver.verify_runtime_provenance(repo, ""), "worktree must be clean"))

    build, layout, corelib = native_fixture(base)
    failures.append(expect_accept("matching native outputs",
                                  lambda: driver.verify_native_identity(build, layout, "12.0.0", corelib)))

    (layout / "shared/Microsoft.NETCore.App/12.0.0/coreclr.dll").write_bytes(b"mixed-native")
    failures.append(expect_reject("native coreclr mismatch",
                                  lambda: driver.verify_native_identity(build, layout, "12.0.0", corelib),
                                  "does not equal the fresh runtime build output"))
    (layout / "shared/Microsoft.NETCore.App/12.0.0/coreclr.dll").write_bytes(b"built-coreclr.dll")

    (layout / "shared/Microsoft.NETCore.App/12.0.0/System.Private.CoreLib.dll").write_bytes(b"mixed-corelib")
    failures.append(expect_reject("native CoreLib mismatch",
                                  lambda: driver.verify_native_identity(build, layout, "12.0.0", corelib),
                                  "Layout CoreLib does not equal"))
    (layout / "shared/Microsoft.NETCore.App/12.0.0/System.Private.CoreLib.dll").write_bytes(b"built-corelib")

    (build / "clrinterpreter.dll").unlink()
    failures.append(expect_reject("missing build output",
                                  lambda: driver.verify_native_identity(build, layout, "12.0.0", corelib),
                                  "build output is absent"))
    (build / "clrinterpreter.dll").write_bytes(b"built-clrinterpreter.dll")

    failures.extend(committed_cases(base, driver))
    failures = [failure for failure in failures if failure]
    print("CASES", CASES, "FAILURES", len(failures))
    for failure in failures:
        print("FAILED", failure)
    if failures:
        raise SystemExit(1)
    print("SESSION_ORIGIN_PROVENANCE PASS")


if __name__ == "__main__":
    main()
