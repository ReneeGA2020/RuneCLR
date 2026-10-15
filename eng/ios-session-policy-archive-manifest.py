#!/usr/bin/env python3
"""Print a read-only manifest for the completed combined-build evidence archive."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Archive working directory")
    parser.add_argument("--build", type=Path)
    parser.add_argument("--assessment", type=Path)
    parser.add_argument("--include-pe", action="store_true")
    parser.add_argument("--include-objects", action="store_true")
    parser.add_argument("--include-critical-binaries", action="store_true")
    parser.add_argument("--tool", type=Path, action="append", default=[])
    parser.add_argument("--format", choices=("json", "paths"), default="json")
    args = parser.parse_args()
    root = args.root.resolve()
    build = (args.build or root / "ios-session-policy-release-20261013").resolve()
    assessment = (args.assessment or root / "ios-session-policy-build-assessment-20261013").resolve()
    runtime = build / "runtime"
    result, completed = read(assessment / "results.json"), read(build / "results.json")
    if not result["success"] or not completed["success"] or result["candidateCommit"] != completed["commit"]:
        raise RuntimeError("Completed source/build assessment identity required")
    files = {}

    def add(path, category, expected=None):
        path = path.resolve()
        name = path.relative_to(root).as_posix()
        if not path.is_file() or chr(10) in name or chr(13) in name:
            raise RuntimeError("Missing or invalid archive input: " + name)
        checksum = digest(path)
        if expected is not None and checksum != expected:
            raise RuntimeError("Evidence hash changed: " + name)
        row = files.setdefault(name, {"path": name, "sizeBytes": path.stat().st_size,
                                    "sha256": checksum, "categories": []})
        if category not in row["categories"]:
            row["categories"].append(category)

    for name in ("artifacts.json", "build.exit", "build.log", "request.json",
                 "results.json", "source-setup.log", "source.json"):
        add(build / name, "build-log-or-receipt")
    for path in sorted(assessment.rglob("*")):
        if path.is_file():
            add(path, "assessment-log-or-receipt")
    native_obj = runtime / "artifacts/obj/coreclr/iossimulator.arm64.Release"
    for directory in (native_obj, native_obj / "arm64"):
        for name in ("CMakeCache.txt", "compile_commands.json"):
            add(directory / name, "original-build-configuration")
    metadata = read(assessment / "metadata-assessment.json")
    descriptor = runtime / "artifacts/obj/coreclr/System.Private.CoreLib/iossimulator.arm64.Release/ILLink.Descriptors.xml"
    add(descriptor, "original-linker-configuration", metadata["descriptorSha256"])
    for name, checksum in read(build / "source.json")["sourceHashes"].items():
        add(runtime / name, "changed-source-snapshot", checksum)
    for name, row in read(assessment / "source-interface-consumers.json").items():
        add(runtime / name, "interface-consumer-source-snapshot", row["sha256"])
    if args.include_pe:
        for row in metadata["stages"]:
            add(Path(row["path"]), "managed-pe-evidence", row["sha256"])
    if args.include_objects:
        for row in read(assessment / "compile-assessment.json")["roles"].values():
            add(Path(row["object"]), "compiled-owner-object", row["objectSha256"])
    if args.include_critical_binaries:
        product = runtime / "artifacts/bin/coreclr/iossimulator.arm64.Release"
        paths = {"native": product / "libcoreclr.dylib",
                 "corelib": product / "IL/System.Private.CoreLib.dll",
                 "crossgen2": product / "arm64/crossgen2/crossgen2",
                 "jitinterface": product / "arm64/crossgen2/libjitinterface_arm64.dylib",
                 "crossarchJit": product / "arm64/crossgen2/libclrjit_universal_arm64_arm64.dylib"}
        for name, path in paths.items():
            add(path, "critical-binary-evidence", result["criticalHashes"][name])
    for path in args.tool:
        add(path, "assessment-tool")
    rows = [files[name] for name in sorted(files)]
    if args.format == "paths":
        print(chr(10).join(row["path"] for row in rows))
    else:
        print(json.dumps({"root": str(root), "candidateCommit": result["candidateCommit"],
                          "fileCount": len(rows), "totalBytes": sum(row["sizeBytes"] for row in rows),
                          "archiveCreated": False, "files": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
