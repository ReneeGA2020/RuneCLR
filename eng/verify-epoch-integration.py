#!/usr/bin/env python3
"""Acceptance for the optional 10 ms epoch callback deadline in the RuneCLR host.

Pins every input before the run, requires the frozen Release runtime outputs to
equal the layout copies, runs the epoch-deadline test harness against that
layout, and re-pins afterwards (zero drift required).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

NL = chr(10)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--layout", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--framework-version", default="12.0.0")
    parser.add_argument("--build-rid", default="windows.x64.Release")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    root = args.host_root.resolve()
    layout = args.layout.resolve()
    runtime = args.runtime_root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Output must be a new directory.")
    output.mkdir(parents=True)

    # Normalise the manifest path once: the pins use resolved paths, so a relative --source-manifest
    # must resolve to the same key or the parse-to-pin equality would report a false missing pin.
    source_manifest = args.source_manifest.resolve()
    manifest_bytes = source_manifest.read_bytes()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_length = len(manifest_bytes)
    (output / "source-manifest.copy.json").write_bytes(manifest_bytes)
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    head = git(runtime, "rev-parse", "HEAD")
    if head != (manifest.get("head") or manifest.get("baseline_head")):
        raise ValueError("Runtime HEAD mismatch: " + head)
    files = manifest.get("dirty_files") or manifest.get("files") or {}
    status = subprocess.check_output(["git", "-C", str(runtime), "status", "--porcelain", "--untracked-files=normal"],
                                     text=True).splitlines()
    changed = sorted(line[3:].strip() for line in status if line.strip())
    if changed != sorted(files):
        raise ValueError("Runtime delta does not equal the source manifest.")
    for name, value in files.items():
        if digest(runtime / name) != value:
            raise ValueError("Source hash mismatch: " + name)

    build = runtime / "artifacts/bin/coreclr" / args.build_rid
    shared = layout / "shared/Microsoft.NETCore.App" / args.framework_version
    outputs = {"System.Private.CoreLib.dll": "CoreLib", "coreclr.dll": "coreclr", "clrjit.dll": "clrjit",
               "clrinterpreter.dll": "clrinterpreter", "corerun.exe": "corerun"}
    artifact = {}
    produced_paths = {}
    for name in outputs:
        produced, installed = build / name, shared / name
        if not produced.is_file():
            # This build publishes the CoreLib as IL/<name> (no crossgen copy in the
            # clr.runtime+clr.corelib+libs subset); accept that exact produced file.
            alternate = build / "IL" / name
            if alternate.is_file():
                produced = alternate
        if not produced.is_file():
            raise ValueError("Runtime artifact output absent (build not terminal): " + str(produced))
        if not installed.is_file():
            raise ValueError("Layout is missing " + name)
        if digest(produced) != digest(installed):
            raise ValueError("Layout " + name + " does not equal the runtime build output.")
        artifact[name] = digest(produced)
        produced_paths[name] = produced

    harness = root / "tests/RuneCLR.EpochDeadline.Tests/bin/Release/net11.0/RuneCLR.EpochDeadline.Tests.dll"
    inputs = {harness, Path(__file__).resolve(), root / "RuneCLR.slnx", root / "Directory.Build.props",
              source_manifest}
    inputs.update(path for path in harness.parent.rglob("*") if path.is_file())
    for folder in (root / "src", root / "tests"):
        inputs.update(path for path in folder.rglob("*") if path.is_file()
                      and not {"bin", "obj"}.intersection(path.relative_to(folder).parts))
    inputs.update(path for path in layout.rglob("*") if path.is_file())
    inputs.update(produced_paths[name] for name in outputs)
    pins = {str(path): digest(path) for path in sorted(inputs) if path.is_file()}
    # Parse-to-pin consistency: the bytes parsed above must be the bytes pinned now.
    pin_sha = pins.get(str(source_manifest))
    if pin_sha is None:
        raise RuntimeError("Source manifest is missing from the input pins.")
    if pin_sha != manifest_sha:
        raise RuntimeError("Source manifest changed between parse and pin.")
    loaded_sha = manifest_sha
    write = output / "pins-before.json"
    write.write_text(json.dumps(pins, indent=2) + NL, encoding="utf-8")

    environment = {k: v for k, v in os.environ.items() if not k.startswith(("DOTNET_", "COMPlus_"))}
    environment.update({"DOTNET_MULTILEVEL_LOOKUP": "0", "DOTNET_RuneCLRInterpretCollectible": "1",
                        "DOTNET_InterpMode": "0", "DOTNET_ReadyToRun": "1", "DOTNET_TieredCompilation": "0"})
    command = [str(layout / ("dotnet.exe" if os.name == "nt" else "dotnet")), "exec",
               "--fx-version", args.framework_version, str(harness)]
    stdout = output / "tests.stdout.log"
    stderr = output / "tests.stderr.log"
    with stdout.open("wb") as out, stderr.open("wb") as err:
        process = subprocess.run(command, cwd=root, env=environment, stdout=out, stderr=err, timeout=args.timeout)
    text = stdout.read_text(encoding="utf-8", errors="replace")
    print(("PASS" if process.returncode == 0 else "FAIL"), "epoch-deadline tests",
          "exit=" + str(process.returncode), "log=" + stdout.name)
    if process.returncode != 0:
        failures = [line for line in text.splitlines() if line.startswith("FAIL ")]
        print("  " + (failures[0] if failures else "see log"))

    after = {str(path): digest(path) if path.is_file() else None for path in sorted(inputs)}
    # Post-run re-validation: the runtime HEAD, its worktree state and the declared source files must be
    # unchanged, and the consumed manifest copy must still hash to the bytes read at pin time.
    if git(runtime, "rev-parse", "HEAD") != head:
        raise RuntimeError("Runtime HEAD drifted during the run.")
    status_after = subprocess.check_output(["git", "-C", str(runtime), "status", "--porcelain", "--untracked-files=normal"], text=True).splitlines()
    changed_after = sorted(line[3:].strip() for line in status_after if line.strip())
    if changed_after != sorted(files):
        raise RuntimeError("Runtime working tree drifted during the run.")
    for name, value in files.items():
        if digest(runtime / name) != value:
            raise RuntimeError("Declared runtime source drifted during the run: " + name)
    if hashlib.sha256(source_manifest.read_bytes()).hexdigest() != loaded_sha:
        raise RuntimeError("Original source manifest changed during the run.")
    if hashlib.sha256((output / "source-manifest.copy.json").read_bytes()).hexdigest() != loaded_sha:
        raise RuntimeError("Consumed source manifest copy drifted.")
    (output / "pins-after.json").write_text(json.dumps(after, indent=2) + NL, encoding="utf-8")
    drift = [path for path in pins if pins[path] != after[path]]
    summary = {"harnessExit": process.returncode, "pinCount": len(pins), "drift": drift,
               "buildRID": args.build_rid, "artifact": artifact,
               "sourceIdentity": {"head": head, "deltaFiles": len(files),
                                  "localUncommitted": bool(files),
                                  "manifestSha256": manifest_sha, "manifestBytes": manifest_length},
               "layoutFiles": sum(1 for p in layout.rglob("*") if p.is_file())}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + NL, encoding="utf-8")
    if drift:
        raise RuntimeError("Input drift: " + repr(drift))
    if process.returncode != 0:
        raise RuntimeError("Epoch-deadline tests failed.")
    print("EPOCH_INTEGRATION PASS; pins=" + str(len(pins)) + "; layout=" + str(summary["layoutFiles"]))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("FAIL " + str(error), file=sys.stderr)
        raise
