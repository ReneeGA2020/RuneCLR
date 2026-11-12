#!/usr/bin/env python3
"""Provenance negatives for the session-origin driver (source-manifest mode).

Builds tiny throwaway git repositories and layout/build fixtures; no runtime or
product sources are read or written. The published verifier is not involved.
"""
import argparse
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
    try:
        call()
    except ValueError as error:
        if contains.lower() not in str(error).lower():
            return label + ": rejected with unexpected message: " + str(error)
        print("PASS reject", label, "->", str(error).split(":")[0][:80])
        return None
    return label + ": was accepted but must be rejected"


def expect_accept(label, call):
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

    failures = [failure for failure in failures if failure]
    print("CASES", 16, "FAILURES", len(failures))
    for failure in failures:
        print("FAILED", failure)
    if failures:
        raise SystemExit(1)
    print("SESSION_ORIGIN_PROVENANCE PASS")


if __name__ == "__main__":
    main()
