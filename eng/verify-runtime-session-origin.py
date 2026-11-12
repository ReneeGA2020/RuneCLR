#!/usr/bin/env python3
"""Run the opt-in session-origin baseline or fixed acceptance matrix.

Baseline mode reproduces the pre-fix gap on the published runtime. Fixed mode
requires every in-scope author-frame, gate, capability and lifetime control to
pass on the new runtime build. The published reflection verifier stays separate.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

NL = chr(10)
VERIFIER = Path(__file__).with_name("verify-runtime-reflection.py")
spec = importlib.util.spec_from_file_location("published_reflection_verifier", VERIFIER)
published = importlib.util.module_from_spec(spec)
spec.loader.exec_module(published)

RUNTIME_BASE = published.RUNTIME_COMMIT
BUILD_RID = "windows.x64.Checked"
NATIVE_OUTPUTS = ("coreclr.dll", "clrjit.dll", "clrinterpreter.dll", "corerun.exe")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + NL, encoding="utf-8")


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def git_raw(root, *args):
    # Porcelain status encodes the index/worktree flags in the first two columns;
    # stripping the output would eat the leading space of the first line.
    return subprocess.check_output(["git", "-C", str(root), *args], text=True)


def verify_runtime_provenance(runtime, expected):
    """Require a clean worktree carrying only in-tree runtime source changes."""
    status = git(runtime, "status", "--porcelain", "--untracked-files=normal")
    if status:
        raise ValueError("Runtime worktree must be clean; found: " + status.replace(NL, " | "))
    head = git(runtime, "rev-parse", "HEAD")
    if expected and head != expected:
        raise ValueError("Runtime HEAD must be " + expected + "; found " + head + ".")
    if subprocess.run(["git", "-C", str(runtime), "merge-base", "--is-ancestor", RUNTIME_BASE, head]).returncode:
        raise ValueError("Runtime HEAD " + head + " is not descended from published base " + RUNTIME_BASE + ".")
    changed = [line for line in git(runtime, "diff", "--name-only", RUNTIME_BASE + ".." + head).splitlines() if line]
    outside = [path for path in changed if not path.startswith("src/")]
    if outside:
        raise ValueError("Runtime changes outside src/: " + ", ".join(outside))
    if not changed and head != RUNTIME_BASE:
        raise ValueError("Runtime HEAD carries no source delta over the published base.")
    return head, changed


def runtime_build_dir(runtime, build_rid):
    return runtime / "artifacts/bin/coreclr" / build_rid


def runtime_corelib(runtime, build_rid=BUILD_RID):
    return runtime_build_dir(runtime, build_rid) / "IL/System.Private.CoreLib.dll"


def load_source_manifest(path):
    """Read the explicit local-experiment manifest: {base, head, files{path: sha256}}."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"base", "head", "files"}:
        raise ValueError("Source manifest must contain exactly base, head and files.")
    base, head, files = data["base"], data["head"], data["files"]
    if base != RUNTIME_BASE:
        raise ValueError("Source manifest base must be " + RUNTIME_BASE + "; found " + str(base) + ".")
    if not isinstance(head, str) or len(head) != 40:
        raise ValueError("Source manifest head must be a full commit id.")
    if not isinstance(files, dict) or not files:
        raise ValueError("Source manifest files must be a non-empty object.")
    for name, value in files.items():
        if not isinstance(name, str) or not isinstance(value, str) or len(value) != 64:
            raise ValueError("Source manifest entry is malformed: " + repr(name))
        if name.startswith("/") or chr(92) in name or ":" in name or ".." in name.split("/"):
            raise ValueError("Source manifest path escapes the runtime tree: " + name)
    return {"base": base, "head": head, "files": dict(files)}


def worktree_delta(runtime):
    """Exactly the tracked, staged and untracked non-ignored paths the worktree changes."""
    status = git_raw(runtime, "status", "--porcelain=v1", "--untracked-files=normal")
    changed = set()
    for line in status.splitlines():
        code, rest = line[:2], line[3:]
        if " -> " in rest or '"' in rest:
            raise ValueError("Source-manifest mode rejects renames and quoted paths: " + line)
        if code.strip().startswith("D"):
            raise ValueError("Source-manifest mode rejects deletions: " + rest)
        changed.add(rest)
    return changed


def committed_hash(runtime, commit, name):
    result = subprocess.run(["git", "-C", str(runtime), "rev-parse", commit + ":" + name],
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def verify_source_manifest(runtime, manifest):
    """Require the worktree delta to equal the manifest exactly, with matching hashes."""
    head = git(runtime, "rev-parse", "HEAD")
    if head != manifest["head"]:
        raise ValueError("Runtime HEAD must equal the source manifest head "
                         + manifest["head"] + "; found " + head + ".")
    changed = worktree_delta(runtime)
    expected = set(manifest["files"])
    extra = sorted(changed - expected)
    absent = sorted(expected - changed)
    if extra:
        raise ValueError("Runtime changes outside the source manifest: " + ", ".join(extra))
    if absent:
        raise ValueError("Source manifest entries without a runtime change: " + ", ".join(absent))
    for name, value in sorted(manifest["files"].items()):
        target = runtime / name
        if not target.is_file():
            raise ValueError("Source manifest file is absent in the worktree: " + name)
        actual = digest(target)
        if actual != value:
            raise ValueError("Source manifest hash mismatch for " + name +
                             ": expected " + value + ", found " + actual + ".")
        if committed_hash(runtime, manifest["base"], name) == actual:
            raise ValueError("Source manifest entry does not differ from the base commit: " + name)
    return head, sorted(manifest["files"])


COMMITTED_SCHEMA = "runeclr.session-origin.committed-source.v1"


def load_committed_receipt(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != COMMITTED_SCHEMA:
        raise ValueError("Unexpected committed-source receipt schema: " + repr(data.get("schema") if isinstance(data, dict) else None))
    build, integ, binaries = data.get("buildSource"), data.get("integration"), data.get("binaries")
    for name, value in (("buildSource", build), ("integration", integ), ("binaries", binaries)):
        if not isinstance(value, dict):
            raise ValueError("Committed-source receipt is missing " + name + ".")
    for key in ("head", "files"):
        if key not in build:
            raise ValueError("buildSource is missing " + key + ".")
    for key in ("commit", "parent", "files"):
        if key not in integ:
            raise ValueError("integration is missing " + key + ".")
    if not isinstance(build["files"], dict) or not build["files"]:
        raise ValueError("buildSource.files must be a non-empty object.")
    if set(build["files"]) != set(integ["files"]):
        raise ValueError("buildSource and integration file sets differ.")
    for path in build["files"]:
        if not isinstance(path, str) or path.startswith("/") or chr(92) in path or ":" in path or ".." in path.split("/"):
            raise ValueError("Committed-source path escapes the runtime tree: " + repr(path))
        for table in (build["files"], integ["files"]):
            if not isinstance(table[path], str) or len(table[path]) != 64:
                raise ValueError("Committed-source hash is malformed for " + path)
    if not isinstance(binaries, dict) or not binaries:
        raise ValueError("Committed-source binaries must be a non-empty object.")
    for name, value in binaries.items():
        if not isinstance(name, str) or not isinstance(value, str) or len(value) != 64:
            raise ValueError("Committed-source binary entry is malformed: " + repr(name))
    for field, value in (("head", build["head"]), ("commit", integ["commit"]), ("parent", integ["parent"])):
        if not isinstance(value, str) or len(value) != 40:
            raise ValueError("Committed-source " + field + " must be a full commit id.")
    if integ["parent"] != build["head"]:
        raise ValueError("integration.parent must equal buildSource.head.")
    relations = data.get("relations") or {}
    if not isinstance(relations, dict):
        raise ValueError("relations must be an object.")
    return {"build": build, "integration": integ, "binaries": dict(binaries), "relations": dict(relations)}


def verify_committed_source(runtime, receipt):
    """Require the exact committed integration snapshot with a recorded build source.

    The build ran at buildSource.head plus the recorded raw files. The commit is the
    canonical (LF) form of the same files, parented on that exact build head. The
    worktree must be clean; working bytes count as the raw build form only when their
    hash matches the receipt, otherwise their newline-normalised form must equal the
    committed blob and the relation must be declared as normalized.
    """
    status = git_raw(runtime, "status", "--porcelain=v1", "--untracked-files=all")
    if status.strip():
        raise ValueError("Runtime worktree must be clean for committed-source mode; found: " + status.replace(NL, " | "))
    head = git(runtime, "rev-parse", "HEAD")
    integ = receipt["integration"]
    if head != integ["commit"]:
        raise ValueError("Runtime HEAD must equal the receipt commit " + integ["commit"] + "; found " + head + ".")
    parent = git(runtime, "rev-parse", "HEAD^")
    if parent != integ["parent"]:
        raise ValueError("Runtime parent must equal the receipt parent " + integ["parent"] + "; found " + parent + ".")
    if subprocess.run(["git", "-C", str(runtime), "merge-base", "--is-ancestor", RUNTIME_BASE, head]).returncode:
        raise ValueError("Runtime HEAD " + head + " is not descended from published base " + RUNTIME_BASE + ".")
    declared = set(integ["files"])
    changed = {}
    for line in git(runtime, "diff", "--name-status", parent + ".." + head).splitlines():
        if not line:
            continue
        code, name = line.split(chr(9), 1)
        changed[name] = code
    if set(changed) != declared:
        extra = sorted(set(changed) - declared)
        absent = sorted(declared - set(changed))
        raise ValueError("Committed delta does not match the receipt: extra=" + repr(extra) + " absent=" + repr(absent))
    relations = {}
    for path in sorted(declared):
        if changed[path] != "M":
            raise ValueError("Committed file is not a modification: " + path + " (" + changed[path] + ")")
        blob = subprocess.run(["git", "-C", str(runtime), "show", head + ":" + path], capture_output=True).stdout
        if hashlib.sha256(blob).hexdigest() != integ["files"][path]:
            raise ValueError("Committed blob hash mismatch for " + path + ".")
        parent_blob = subprocess.run(["git", "-C", str(runtime), "show", parent + ":" + path], capture_output=True).stdout
        if parent_blob == blob:
            raise ValueError("Committed file does not differ from its parent: " + path)
        work = (runtime / path).read_bytes()
        normalized = work.replace(b"\r\n", b"\n")
        if normalized != blob:
            raise ValueError("Working bytes are not the committed content modulo newlines: " + path)
        raw_sha = hashlib.sha256(work).hexdigest()
        src_sha = receipt["build"]["files"][path]
        declared_rel = receipt["relations"].get(path)
        if raw_sha == src_sha:
            relation = "raw"
        elif src_sha == integ["files"][path]:
            # The build read the canonical (LF) form while the checkout materialises CRLF.
            relation = "normalized-canonical"
        else:
            raise ValueError("Working bytes do not match the recorded build source: " + path)
        if declared_rel is not None and declared_rel != relation:
            raise ValueError("Source relation mismatch for " + path + ": declared " + str(declared_rel) + ", observed " + relation + ".")
        relations[path] = relation
    return head, sorted(declared), relations


def verify_native_identity(runtime_build, layout, framework, corelib):
    """Require the layout native files to equal the fresh runtime build outputs."""
    shared = layout / "shared/Microsoft.NETCore.App" / framework
    observed = {}
    for name in NATIVE_OUTPUTS:
        produced = runtime_build / name
        installed = shared / name
        if not produced.is_file():
            raise ValueError("Fresh runtime build output is absent: " + str(produced))
        if not installed.is_file():
            raise ValueError("Layout is missing " + name + ": " + str(installed))
        built, copied = digest(produced), digest(installed)
        if built != copied:
            raise ValueError("Layout " + name + " does not equal the fresh runtime build output.")
        observed[name] = built
    if not corelib.is_file():
        raise ValueError("Runtime build CoreLib is absent: " + str(corelib))
    installed_corelib = shared / "System.Private.CoreLib.dll"
    if digest(corelib) != digest(installed_corelib):
        raise ValueError("Layout CoreLib does not equal the runtime build output.")
    observed["System.Private.CoreLib.dll"] = digest(corelib)
    return observed


def build_layout(layout, core_root, host_source, framework_version, framework_manifest=None):
    """Compose a private layout: build output bits plus a private host.

    The build's Core_Root-like directory can carry the framework assemblies and
    native outputs without Microsoft.NETCore.App.deps.json; a read-only copy of
    that metadata file completes the framework without contributing binaries.
    """
    if not core_root.exists():
        raise ValueError("Core_Root is absent: " + str(core_root))
    if not (core_root / "System.Private.CoreLib.dll").exists():
        raise ValueError("Core_Root has no System.Private.CoreLib.dll: " + str(core_root))
    if layout.exists():
        raise ValueError("--build-layout requires a new layout directory.")
    shared = layout / "shared/Microsoft.NETCore.App" / framework_version
    shared.parent.mkdir(parents=True)
    shutil.copytree(core_root, shared)
    if framework_manifest is not None:
        if not framework_manifest.is_file():
            raise ValueError("Framework manifest is absent: " + str(framework_manifest))
        shutil.copy2(framework_manifest, shared / "Microsoft.NETCore.App.deps.json")
    name = "dotnet.exe" if os.name == "nt" else "dotnet"
    if not (host_source / name).exists():
        raise ValueError("Host source has no " + name + ": " + str(host_source))
    shutil.copy2(host_source / name, layout / name)
    if (host_source / "host").is_dir():
        shutil.copytree(host_source / "host", layout / "host")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--layout", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dotnet", default="dotnet")
    parser.add_argument("--corelib", type=Path)
    parser.add_argument("--core-root", type=Path)
    parser.add_argument("--framework-manifest", type=Path)
    parser.add_argument("--host-source", type=Path)
    parser.add_argument("--framework-version", default="12.0.0")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--runtime-commit", default="")
    parser.add_argument("--runtime-source-manifest", type=Path)
    parser.add_argument("--runtime-committed-source", type=Path)
    parser.add_argument("--build-rid", default=BUILD_RID)
    parser.add_argument("--build-layout", action="store_true")
    parser.add_argument("--expect-fixed", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    runtime = args.runtime_root.resolve()
    layout = args.layout.resolve()
    output = args.output.resolve()
    if published.within(output, root) or published.within(output, runtime) or published.within(output, layout):
        raise ValueError("Output must be outside source/runtime/layout roots.")
    if output.exists():
        raise ValueError("Output must be a new directory.")

    manifest_file = None
    receipt_file = None
    committed_receipt = None
    source_relations = None
    if args.runtime_committed_source:
        if args.runtime_source_manifest or args.runtime_commit:
            raise ValueError("--runtime-committed-source is mutually exclusive with --runtime-source-manifest/--runtime-commit.")
        receipt_file = args.runtime_committed_source.resolve()
        if published.within(receipt_file, runtime) or published.within(receipt_file, root):
            raise ValueError("The committed-source receipt must live outside the source and runtime trees.")
        committed_receipt = load_committed_receipt(receipt_file)
        runtime_head, runtime_changed, source_relations = verify_committed_source(runtime, committed_receipt)
        provenance = "committed-integration"
    elif args.runtime_source_manifest:
        if args.runtime_commit:
            raise ValueError("--runtime-source-manifest and --runtime-commit are mutually exclusive.")
        manifest_file = args.runtime_source_manifest.resolve()
        if published.within(manifest_file, runtime) or published.within(manifest_file, root):
            raise ValueError("The source manifest must live outside the source and runtime trees.")
        manifest = load_source_manifest(manifest_file)
        runtime_head, runtime_changed = verify_source_manifest(runtime, manifest)
        provenance = "source-manifest"
    else:
        runtime_head, runtime_changed = verify_runtime_provenance(runtime, args.runtime_commit)
        provenance = "clean-commit"

    if args.build_layout:
        core_root = (args.core_root or
                     runtime / "artifacts/tests/coreclr/windows.x64.Checked/Tests/Core_Root").resolve()
        host_source = (args.host_source or runtime / ".dotnet").resolve()
        build_layout(layout, core_root, host_source, args.framework_version,
                     args.framework_manifest.resolve() if args.framework_manifest else None)

    private_host = layout / ("dotnet.exe" if os.name == "nt" else "dotnet")
    framework = layout / "shared/Microsoft.NETCore.App" / args.framework_version
    runtime_build = runtime_build_dir(runtime, args.build_rid)
    corelib = (args.corelib or runtime_corelib(runtime, args.build_rid)).resolve()
    if not private_host.exists():
        raise ValueError("Private layout host is absent: " + str(private_host))
    native = verify_native_identity(runtime_build, layout, args.framework_version, corelib)
    if provenance == "committed-integration":
        if set(committed_receipt["binaries"]) != set(native):
            raise ValueError("Committed-source receipt binary set does not match the fresh build outputs: "
                             + repr(sorted(committed_receipt["binaries"])) + " vs " + repr(sorted(native)))
        for name, expected in sorted(committed_receipt["binaries"].items()):
            if native[name] != expected:
                raise ValueError("Binary hash mismatch for " + name + ": expected " + expected + ", found " + native[name] + ".")

    harness = root / "tests/RuneCLR.SessionOrigin.Tests/bin/Release/net11.0/RuneCLR.SessionOrigin.Tests.dll"
    fixtures = harness.parent / "session-origin"
    required = [harness, fixtures / "SessionOrigin.Author.dll",
                fixtures / "SessionOrigin.Compiled.dll",
                fixtures / "SessionOrigin.Chain.dll",
                fixtures / "ReflectionPolicy.DeniedDependency.dll"]
    for path in required:
        if not path.exists():
            raise ValueError("Required fixture absent: " + str(path))

    inputs = {Path(__file__).resolve(), VERIFIER.resolve(), private_host, harness, corelib,
              framework / "System.Private.CoreLib.dll"}
    inputs.update(runtime_build / name for name in NATIVE_OUTPUTS)
    inputs.update(required[1:])
    # Everything the harness actually loads, plus the sources that produced it:
    # the runtime source manifest alone cannot prove the managed host is current.
    inputs.update(path for path in harness.parent.rglob("*") if path.is_file())
    for folder in (root / "src", root / "tests"):
        inputs.update(path for path in folder.rglob("*") if path.is_file()
                      and not {"bin", "obj"}.intersection(path.relative_to(folder).parts))
    inputs.update({root / "RuneCLR.slnx", root / "Directory.Build.props"})
    if manifest_file is not None:
        inputs.add(manifest_file)
    inputs.update(runtime / name for name in published.RUNTIME_FILES)
    inputs.update(runtime / name for name in runtime_changed)
    inputs.update(path for path in layout.rglob("*") if path.is_file())
    pins = {str(path): digest(path) for path in sorted(inputs)}

    output.mkdir(parents=True)
    environment = dict(os.environ)
    for key in list(environment):
        if key.startswith(("DOTNET_", "COMPlus_")):
            del environment[key]
    environment.update({"DOTNET_MULTILEVEL_LOOKUP": "0", "DOTNET_RuneCLRInterpretCollectible": "1",
                        "DOTNET_InterpMode": "0", "DOTNET_ReadyToRun": "1", "DOTNET_TieredCompilation": "0"})

    # The origin-scan switch is latched during runtime startup, so a switch-off
    # process must be configured before the runtime starts, never from Main.
    harness_config = json.loads((harness.parent / "RuneCLR.SessionOrigin.Tests.runtimeconfig.json")
                                .read_text(encoding="utf-8"))

    def startup_config(name, scan):
        data = json.loads(json.dumps(harness_config))
        properties = data.setdefault("runtimeOptions", {}).setdefault("configProperties", {})
        properties["RuneCLR.EnableReflectionPolicyOriginScan"] = bool(scan)
        path = output / (name + ".runtimeconfig.json")
        write_json(path, data)
        return path

    def run_mode(name, mode_args, startup_scan=None):
        stdout = output / (name + ".stdout.log")
        stderr = output / (name + ".stderr.log")
        command = [str(private_host), "exec", "--fx-version", args.framework_version]
        if startup_scan is not None:
            command += ["--runtimeconfig", str(startup_config(name, startup_scan))]
        command += [str(harness), *mode_args]
        write_json(output / (name + "-request.json"), {"argv": command, "cwd": str(root),
                                                       "startupOriginScan": startup_scan})
        with stdout.open("wb") as out, stderr.open("wb") as err:
            process = subprocess.run(command, cwd=root, env=environment, stdout=out, stderr=err,
                                     timeout=args.timeout)
        text = stdout.read_text(encoding="utf-8", errors="replace")
        parsed = None
        start = text.find("{")
        if start >= 0:
            try: parsed = json.loads(text[start:])
            except json.JSONDecodeError: parsed = None
        return {"exit": process.returncode, "stdout": str(stdout), "stderr": str(stderr), "parsed": parsed}

    modes = {}
    failures = []
    if not args.expect_fixed:
        mode = run_mode("baseline", ["--require-private-runtime"])
        modes["baseline"] = mode
        observed = mode["exit"] == 0 and mode["parsed"] is not None and mode["parsed"].get("baselineGapObserved") is True
        if not observed:
            failures.append("baseline gap not observed")
        result = {"mode": "baseline", "baselineGapObserved": observed}
    else:
        checks = []

        def bit0(value):
            return isinstance(value, int) and (value & 1) == 1

        def capability(parsed):
            return bit0(parsed.get("originScanCapability"))

        def run_check(name, mode_args, predicate, description, startup_scan=None):
            mode = run_mode(name, mode_args, startup_scan)
            modes[name] = mode
            parsed = mode["parsed"] or {}
            ok = mode["exit"] == 0 and mode["parsed"] is not None and bool(predicate(parsed))
            checks.append({"name": name, "passed": ok, "description": description,
                           "exit": mode["exit"], "parsed": parsed})
            if not ok:
                failures.append(name + ": " + description)
            return ok

        def reached_or_refused(ran, failure):
            """The probe either ran its body or was refused before entry with a named error."""
            return ran is True or (isinstance(failure, str) and failure != "")

        def reached_missing_author_file(parsed):
            return parsed.get("rejectedBeforeFile") is False and parsed.get("errorType") in (
                "System.IO.FileNotFoundException", "System.IO.DirectoryNotFoundException")

        def gate_refused_before_file(parsed):
            return parsed.get("rejectedBeforeFile") is True and                 parsed.get("errorType") == "System.PlatformNotSupportedException"

        run_check("fixed", ["--expect-fixed", "--require-origin"],
                  lambda p: p.get("fixedModeObserved") is True and capability(p),
                  "normal/suppressed/compiled-helper author frames restricted with capability bit0", startup_scan=True)

        frame = run_mode("frame", ["--frame-probes", "--require-origin"], startup_scan=True)
        modes["frame"] = frame
        parsed = frame["parsed"] or {}
        frame_ok = (frame["exit"] == 0 and frame["parsed"] is not None and
                    parsed.get("hidden", {}).get("FixedRestricted") is True and
                    parsed.get("inlined", {}).get("FixedRestricted") is True and
                    parsed.get("compiledOnlySuppressedRan") is True)
        checks.append({"name": "frame", "passed": frame_ok, "exit": frame["exit"],
                       "description": "hidden/inlined author frames restricted; the compiled-only suppressed child "
                                      "attempts forbidden reflection with no author frame and its outcome is "
                                      "recorded, not required (ran=" +
                                      str(parsed.get("compiledOnlySuppressedRan")) + ", escaped=" +
                                      str(parsed.get("compiledOnlyEscaped")) + ", failure=" +
                                      str(parsed.get("compiledOnlyFailure")) + ", effects=" +
                                      str(parsed.get("compiledOnlyEffects")) + ")",
                       "parsed": parsed})
        if not frame_ok:
            failures.append("frame: hidden/inlined author-frame control failed")

        run_check("retirement", ["--retirement", "--require-origin"],
                  lambda p: p.get("Effects") == 0 and
                            reached_or_refused(p.get("RetiredProbeRan"), p.get("RetiredFailure")),
                  "retired owner cannot revive a captured author probe: probe ran or was refused by name, "
                  "and no forbidden effect happened", startup_scan=True)
        run_check("conflict", ["--conflict", "--require-origin"],
                  lambda p: p.get("BStored") is True and p.get("Effects") == 0 and
                            reached_or_refused(p.get("ConflictProbeRan"), p.get("ConflictFailure")),
                  "actual A/B owner conflict fails closed deny-wins: probe ran or was refused by name, "
                  "and no forbidden effect happened", startup_scan=True)
        run_check("overflow", ["--overflow", "--require-origin"],
                  lambda p: p.get("Effects") == 0 and p.get("ChainDepth") == 17 and
                            p.get("ChainCompleted") is True and
                            p.get("ChainLeafFailure") == "System.NotSupportedException",
                  "17-deep foreign collectible-ALC stack reaches the leaf and is refused with "
                  "System.NotSupportedException (native saturation), with no forbidden effect", startup_scan=True)
        run_check("disposal", ["--disposal", "--require-origin"],
                  lambda p: p.get("Effects") == 0 and
                            ((p.get("Parked") is True and p.get("ChildJoined") is True and
                              p.get("ReflectionDenied") is True) or
                             (isinstance(p.get("ChildFailure"), str) and p.get("ChildFailure") != "")),
                  "disposed owner fail-closes a live author frame: parked probe reached its denied reflection "
                  "or the entry was refused by name, with no forbidden effect", startup_scan=True)
        run_check("default-off", ["--capability-probe", "false"],
                  lambda p: not capability(p) and p.get("switchEffective") is False,
                  "an absent RuneCLR.EnableReflectionPolicyOriginScan keeps the experiment off, so a host "
                  "that does not opt in keeps the pre-existing reflection-policy behavior")
        run_check("capability-on", ["--capability-probe", "true"],
                  lambda p: capability(p) and p.get("switchEffective") is True,
                  "capability bit0 present with the startup switch true", startup_scan=True)
        run_check("capability-off", ["--capability-probe", "false"],
                  lambda p: not capability(p) and p.get("switchEffective") is False,
                  "capability bit0 absent when the process starts with the switch false", startup_scan=False)
        run_check("map-gate-on", ["--required-origin-gate", "true"],
                  reached_missing_author_file,
                  "Map required-origin gate accepts the capability and fails on the intentionally absent "
                  "author file (FileNotFound/DirectoryNotFound)",
                  startup_scan=True)
        run_check("map-gate-off", ["--required-origin-gate", "false"],
                  gate_refused_before_file,
                  "Map required-origin gate rejects a startup-off process before author loading "
                  "(PlatformNotSupportedException)",
                  startup_scan=False)
        run_check("host-gate-on", ["--host-required-origin-gate", "true"],
                  reached_missing_author_file,
                  "HostContract required-origin gate accepts the capability and fails on the intentionally "
                  "absent author file (FileNotFound/DirectoryNotFound)",
                  startup_scan=True)
        run_check("host-gate-off", ["--host-required-origin-gate", "false"],
                  gate_refused_before_file,
                  "HostContract required-origin gate rejects a startup-off process before author loading "
                  "(PlatformNotSupportedException)",
                  startup_scan=False)
        run_check("toggle-on", ["--toggle-gate", "true"],
                  lambda p: bit0(p.get("capabilityAfter")) and
                            p.get("mapRejectedBeforeFile") is False and
                            p.get("hostRejectedBeforeFile") is False,
                  "a post-latch switch-off does not revoke the latched capability", startup_scan=True)
        run_check("toggle-off", ["--toggle-gate", "false"],
                  lambda p: not bit0(p.get("capabilityBefore")) and not bit0(p.get("capabilityAfter")) and
                            p.get("mapRejectedBeforeFile") is True and
                            p.get("hostRejectedBeforeFile") is True,
                  "a startup-off process stays latched off after the switch is turned on", startup_scan=False)

        run_check("invalid-option-combos", ["--invalid-option-combos"],
                  lambda p: p.get("invalidRejected") is True and
                            p.get("mapError") == "System.ArgumentException" and
                            p.get("hostError") == "System.ArgumentException",
                  "RequireOriginScan without RequireInterpreter and a policy is rejected with ArgumentException "
                  "for both MapRunOptions and HostContractSessionOptions")

        result = {"mode": "fixed", "checks": checks,
                  "compiledOnlyBoundary": (modes["frame"]["parsed"] or {}).get("compiledOnlySuppressedRan"),
                  "uncovered": [
                      "native walker status 2 (no thread, aborted walk, unmaterialisable owner) has no "
                      "executable injection; it stays an explicit uncovered branch",
                      "status 1 (saturation) is witnessed only through the managed overflow lane, which "
                      "requires the leaf refusal System.NotSupportedException rather than a raw status value",
                      "compiled-only suppressed child has no author frame; its reflection outcome is recorded "
                      "as a boundary and scheduling-token/escaped-target work is deliberately deferred",
                      "unmanaged entry, AOT/mobile and global all-load coverage remain outside this milestone"]}

    after = {str(path): digest(path) if path.is_file() else None for path in sorted(inputs)}
    drift = [path for path in pins if pins[path] != after[path]]
    result["modes"] = {name: {"exit": mode["exit"], "parsed": mode["parsed"] is not None,
                              "stdout": mode["stdout"], "stderr": mode["stderr"]}
                       for name, mode in modes.items()}
    result["failures"] = failures
    result["inputCount"] = len(pins)
    result["drift"] = drift
    result["runtimeBase"] = RUNTIME_BASE
    result["runtimeHead"] = runtime_head
    result["runtimeChangedFiles"] = runtime_changed
    result["layoutBuilt"] = bool(args.build_layout)
    result["provenance"] = provenance
    result["committedIntegration"] = provenance == "committed-integration"
    result["committedReceipt"] = str(receipt_file) if receipt_file is not None else None
    result["buildSourceHead"] = committed_receipt["build"]["head"] if committed_receipt else None
    result["integrationCommit"] = committed_receipt["integration"]["commit"] if committed_receipt else None
    result["sourceRelations"] = source_relations
    result["runtimeSourceManifest"] = str(manifest_file) if manifest_file is not None else None
    result["localUncommitted"] = provenance == "source-manifest"
    result["publishedAcceptance"] = provenance == "clean-commit"
    result["nativeIdentity"] = native
    result["passed"] = not failures and not drift and all(
        mode["exit"] == 0 and mode["parsed"] is not None for mode in modes.values())
    write_json(output / "pins-before.json", pins)
    write_json(output / "pins-after.json", after)
    write_json(output / "summary.json", result)
    if not result["passed"]:
        raise RuntimeError("; ".join(failures) if failures else "input drift or mode failure")
    label = ("SESSION_ORIGIN_FIXED" if args.expect_fixed else "SESSION_ORIGIN_BASELINE")
    if provenance == "source-manifest":
        label += " LOCAL_UNCOMMITTED_SOURCE_MANIFEST (not published acceptance)"
    elif provenance == "committed-integration":
        label += " COMMITTED_INTEGRATION_SOURCE (build source recorded)"
    print(label + " PASS; modes=" + str(len(modes)) + "; pins=" + str(len(pins)) +
          "; runtimeHead=" + runtime_head)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("FAIL " + str(error), file=sys.stderr)
        raise
