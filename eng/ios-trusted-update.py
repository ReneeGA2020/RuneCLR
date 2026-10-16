#!/usr/bin/env python3
"""Build and run a fixed-host, post-install trusted iOS R2R update probe."""
import argparse
import hashlib
import importlib.util
import struct
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import time

BASE_COMMIT = "0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de"
PROJECT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT / "eng" / "ios-trusted-update"

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()

def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

def capture(argv):
    return subprocess.check_output([str(x) for x in argv], text=True).strip()

def run(argv, log, env=None, check=True, timeout=600):
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    with Path(log).open("w", encoding="utf-8", errors="replace") as stream:
        result = subprocess.run([str(x) for x in argv], stdout=stream, stderr=subprocess.STDOUT, env=env, check=False, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {argv[0]} ({log})")
    return result.returncode

def sdk_inputs(runtime):
    sdk = runtime / ".dotnet/dotnet"
    version = capture([sdk, "--version"])
    csc = runtime / ".dotnet/sdk" / version / "Roslyn/bincore/csc.dll"
    crossgen = runtime / "artifacts/bin/coreclr/iossimulator.arm64.Debug/arm64/crossgen2/crossgen2"
    base = runtime.parent / "preview6-experiment/pinned-debug-harness"
    for path in (sdk, csc, crossgen, base):
        if not path.exists():
            raise RuntimeError("missing matching Apple input: " + str(path))
    return sdk, csc, crossgen, base

def compile_managed(sdk, csc, output, sources, refs, target="library", log=None):
    command = [sdk, csc, "-nologo", "-noconfig", "-nostdlib+", "-optimize+", f"-target:{target}", f"-out:{output}"]
    command += [f"-r:{path}" for path in refs] + [str(path) for path in sources]
    run(command, log or Path(output).with_suffix(".compile.log"))

def crossgen(crossgen2, output, inputs, refs, outdir, stem, inputbubble=True):
    response = Path(outdir) / (stem + ".crossgen.rsp")
    args = ["--targetos:iossimulator", "--targetarch:arm64", "--obj-format:macho", "--composite"]
    if inputbubble: args.append("--inputbubble")
    args += ["--parallelism:2", "--resilient", "--optimize", "--out:" + str(output)]
    args += [str(path) for path in inputs] + ["-r:" + str(path) for path in refs]
    response.write_text("\n".join(args) + "\n", encoding="utf-8")
    run([crossgen2, "@" + str(response)], Path(outdir) / (stem + ".crossgen.log"))
    return response

def link(obj, dylib, log):
    run(["xcrun", "--sdk", "iphonesimulator", "clang", "-target", "arm64-apple-ios15.3-simulator", "-dynamiclib", obj, "-Wl,-install_name,@rpath/" + Path(dylib).name, "-o", dylib], log)
    run(["codesign", "--force", "--sign", "-", dylib], str(log) + ".sign.log")

def managed_refs(base):
    app = base / "app" / "RuneCLRPinnedHarness.app"
    refs = []
    for path in sorted((base / "original").glob("*.dll")):
        if path.name.startswith(("RuneCLR.", "HarnessBridge")):
            continue
        override = app / path.name
        refs.append(override if override.is_file() else path)
    return refs

def instrument_wrapper(source):
    """Record the actual Apple native-code callback identity."""
    text = source.replace("#include <stdio.h>", "#include <stdio.h>\n#include <string.h>")
    anchor = "    data->size = sizeof(struct host_runtime_contract_native_code_data);"
    if text.count(anchor) != 1:
        raise RuntimeError("Apple callback data anchor changed")
    replacement = """    struct stat owner_stat;
    memset(&owner_stat, 0, sizeof(owner_stat));
    stat(r2r_path, &owner_stat);
    printf("RUNECLR_NATIVE_CALLBACK owner=%s assembly=%s path=%s base=%p rtr_header=%p image_size=%zu file_size=%lld\\n",
           context->owner_composite_name, context->assembly_path, r2r_path,
           info.dli_fbase, r2r_header, get_image_size(header), (long long)owner_stat.st_size);
    fflush(stdout);

    data->size = sizeof(struct host_runtime_contract_native_code_data);"""
    text = text.replace(anchor, replacement)
    return text

def bundle_hashes(app):
    root = Path(app)
    return {str(path.relative_to(root)): sha(path) for path in sorted(root.rglob("*")) if path.is_file()}

def callback_identity(lines):
    if not lines:
        return None
    fields = {}
    for item in lines[-1].split()[1:]:
        if "=" in item:
            key, value = item.split("=", 1); fields[key] = value
    return {"ownerCompositeExecutable": fields.get("owner"), "assembly": fields.get("assembly"),
            "path": fields.get("path"), "base": fields.get("base"), "header": fields.get("rtr_header"),
            "imageSize": int(fields["image_size"]) if fields.get("image_size", "").isdigit() else None,
            "fileSize": int(fields["file_size"]) if fields.get("file_size", "").isdigit() else None,
            "baseValue": pointer_value(fields.get("base")),
            "line": lines[-1]}


READYTORUN_SIGNATURE = 0x00525452
OWNER_COMPOSITE_SECTION = 116
PLATFORM_NATIVE_FLAG = 0x100
COMPONENT_FLAG = 0x20


def load_macho_module():
    global _MACHO_MODULE
    if "_MACHO_MODULE" in globals() and _MACHO_MODULE is not None:
        return _MACHO_MODULE
    spec = importlib.util.spec_from_file_location(
        "ios_trusted_update_macho", Path(__file__).with_name("ios_trusted_update_macho.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _MACHO_MODULE = module
    return module


def load_macho_fixtures():
    spec = importlib.util.spec_from_file_location(
        "verify_ios_trusted_update_macho_fixtures",
        Path(__file__).with_name("verify-ios-trusted-update-macho.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def macho_download_audit(path):
    """Structural audit of one owner dylib prepared for loading.

    The Mach-O tool reports file structure, platform and static ranges only.
    provesNativeExecution is always false and is not a method-entry result.
    """
    inspector = load_macho_module()
    report = inspector.inspect_macho(path)
    inspector.require_platform(report, "iossimulator")
    if report.get("proves_native_execution") is not False:
        raise inspector.MachOInspectionError("Mach-O report claimed native execution")
    segments = report.get("executable_segments") or []
    if len(segments) != 1:
        raise inspector.MachOInspectionError(
            "expected one executable segment, found %d" % len(segments))
    build = report.get("build_version") or {}
    if build.get("platform") != 7 or build.get("platform_name") != "iossimulator":
        raise inspector.MachOInspectionError("platform is not 7/iossimulator")
    segment = segments[0]
    return {
        "path": str(Path(path)),
        "fileName": Path(path).name,
        "byteCount": report["file_size"],
        "sha256": report["sha256"],
        "uuid": report.get("uuid"),
        "platform": build["platform"],
        "platformName": build["platform_name"],
        "executableSegment": {
            "name": segment["name"],
            "vmaddr": segment["vmaddr"],
            "vmsize": segment["vmsize"],
            "fileoff": segment["file_offset"],
            "filesize": segment["file_size"],
            "addressKind": segment.get("address_kind"),
        },
        "provesNativeExecution": False,
        "addressNote": report.get("address_note"),
        "scope": "mach-o structure, platform and static range only; not runtime method entry",
    }


def _segments_and_symbols(data):
    if len(data) < 32 or struct.unpack_from("<I", data, 0)[0] != 0xFEEDFACF:
        raise ValueError("not a thin little-endian Mach-O")
    ncmds, sizeofcmds = struct.unpack_from("<II", data, 16)
    cursor, limit = 32, 32 + sizeofcmds
    if limit > len(data):
        raise ValueError("truncated Mach-O command table")
    segments, symbols = [], None
    for _ in range(ncmds):
        command, length = struct.unpack_from("<II", data, cursor)
        if length < 8 or cursor + length > limit:
            raise ValueError("invalid Mach-O command bounds")
        payload = data[cursor:cursor + length]
        if command == 0x19:
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", payload, 24)
            segments.append((vmaddr, vmsize, fileoff, filesize))
        elif command == 0x2 and len(payload) >= 24:
            symbols = struct.unpack_from("<IIII", payload, 8)
        cursor += length
    return segments, symbols


def exported_rtr_header(path):
    """Locate one exported _RTR_HEADER symbol. Absence is not a runtime crash."""
    data = Path(path).read_bytes()
    segments, symbols = _segments_and_symbols(data)
    if not symbols:
        return None
    symoff, nsyms, stroff, strsize = symbols
    if symoff + nsyms * 16 > len(data) or stroff + strsize > len(data):
        raise ValueError("Mach-O symbol table exceeds the file")
    found = None
    for index in range(nsyms):
        name_off, kind, section, _desc, value = struct.unpack_from("<IBBHQ", data, symoff + index * 16)
        if name_off >= strsize:
            raise ValueError("Mach-O symbol name exceeds the string table")
        end = data.index(b"\0", stroff + name_off, stroff + strsize)
        name = data[stroff + name_off:end]
        if name != b"_RTR_HEADER":
            continue
        if found is not None:
            raise ValueError("duplicate _RTR_HEADER export")
        if (kind & 0x0F) != 0x0F or section == 0:
            raise ValueError("RTR_HEADER is not an exported defined section symbol")
        matches = [
            item for item in segments
            if item[0] <= value and value + 16 <= item[0] + item[1] and value + 16 <= item[0] + item[3]
        ]
        if len(matches) != 1:
            raise ValueError("RTR_HEADER address is not in one ordinary segment")
        vmaddr, _vmsize, fileoff, _filesize = matches[0]
        location = fileoff + (value - vmaddr)
        if location < 0 or location + 16 > len(data):
            raise ValueError("RTR_HEADER file location exceeds the file")
        signature, major, minor, flags, section_count = struct.unpack_from("<IHHII", data, location)
        found = {
            "symbol": "_RTR_HEADER",
            "signature": signature,
            "signatureValid": signature == READYTORUN_SIGNATURE,
            "major": major,
            "minor": minor,
            "flags": flags,
            "sectionCount": section_count,
            "symbolValue": value,
            "imageOffset": location,
        }
    return found


def _pe_offset(data, rva):
    if data[:2] != b"MZ":
        raise ValueError("component is not a PE")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("component PE signature missing")
    section_count = struct.unpack_from("<H", data, pe + 6)[0]
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    section_start = optional + struct.unpack_from("<H", data, pe + 20)[0]
    if magic != 0x20B:
        raise ValueError("component is not PE32+")
    for index in range(section_count):
        section = section_start + 40 * index
        virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from("<IIII", data, section + 8)
        span = max(virtual_size, raw_size)
        if virtual_address <= rva < virtual_address + span:
            return raw_pointer + rva - virtual_address
    raise ValueError("RVA is outside component PE sections")


def owner_composite_from_component(path):
    """Read OwnerCompositeExecutable from a component assembly. None if it has no R2R header."""
    data = Path(path).read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    optional = pe + 24
    directories = optional + 112
    cli_rva, cli_size = struct.unpack_from("<II", data, directories + 14 * 8)
    if cli_rva == 0 or cli_size < 72:
        return None
    cli = _pe_offset(data, cli_rva)
    native_rva, native_size = struct.unpack_from("<II", data, cli + 64)
    if native_rva == 0 or native_size < 16:
        return None
    header = _pe_offset(data, native_rva)
    signature, major, minor, flags, count = struct.unpack_from("<IHHII", data, header)
    if signature != READYTORUN_SIGNATURE:
        raise ValueError("component managed-native header is not READYTORUN")
    if header + 16 + count * 12 > len(data):
        raise ValueError("component READYTORUN section table exceeds the file")
    name = None
    for index in range(count):
        section_type, section_rva, section_size = struct.unpack_from("<III", data, header + 16 + index * 12)
        if section_type != OWNER_COMPOSITE_SECTION:
            continue
        if name is not None:
            raise ValueError("duplicate OwnerCompositeExecutable section")
        if section_size < 2:
            raise ValueError("OwnerCompositeExecutable section is empty")
        start = _pe_offset(data, section_rva)
        raw = data[start:start + section_size]
        if b"\0" not in raw:
            raise ValueError("OwnerCompositeExecutable is not NUL-terminated")
        name = raw.split(b"\0", 1)[0].decode("utf-8")
    if not name:
        return None
    return {
        "name": name,
        "major": major,
        "minor": minor,
        "flags": flags,
        "component": bool(flags & COMPONENT_FLAG),
        "platformNative": bool(flags & PLATFORM_NATIVE_FLAG),
    }



def target_failure_of(host_target, candidate_target):
    """Return a selector failure when targets were supplied, otherwise None."""
    if host_target is None and candidate_target is None:
        return None
    if host_target is None or candidate_target is None:
        return "InvalidCandidate"
    host_runtime, host_arch = host_target
    candidate_runtime, candidate_arch = candidate_target
    parts = (host_runtime, host_arch, candidate_runtime, candidate_arch)
    if not all(str(part or "").strip() for part in parts):
        return "InvalidCandidate"
    if str(host_runtime) != str(candidate_runtime) or str(host_arch) != str(candidate_arch):
        return "IncompatibleTarget"
    return None


def is_under_content_root(content_root, assembly_path):
    root = Path(content_root).resolve()
    full = Path(assembly_path).resolve()
    try:
        relative = full.relative_to(root)
    except ValueError:
        return False
    return str(relative) not in ('', '.')

def startup_plan_failure(assembly_path, version_name, content_sha256, approval, host_target=None, candidate_target=None, content_root=None, additional=None):
    """Match TryPlanCandidate for one startup defect, without loading an assembly.

    A missing file wins over an empty version. A supplied target is checked
    before the content hash. Additional files are checked after the entry hash
    and before approval. Approval is a version, hash and id, not a signature.
    """
    assembly_path = Path(assembly_path)
    version = "" if version_name is None else str(version_name).strip()
    manifest = "" if content_sha256 is None else str(content_sha256).strip()
    if not assembly_path.is_file():
        return "MissingContent"
    if not version or not manifest:
        return "InvalidCandidate"
    if content_root is not None:
        if not str(content_root).strip():
            return "InvalidCandidate"
        if not is_under_content_root(content_root, assembly_path):
            return "OutsideContentRoot"
        for item in additional or []:
            extra_path = Path(str(item.get("path") or ""))
            if extra_path.is_file() and not is_under_content_root(content_root, extra_path):
                return "OutsideContentRoot"
    target_failure = target_failure_of(host_target, candidate_target)
    if target_failure is not None:
        return target_failure
    if sha(assembly_path).lower() != manifest.lower():
        return "ContentHashMismatch"
    for item in additional or []:
        extra_path = Path(str((item or {}).get("path") or ""))
        expected = str((item or {}).get("contentSha256") or "").strip()
        if not str((item or {}).get("path") or "").strip() or not expected:
            return "InvalidCandidate"
        if not extra_path.is_file():
            return "MissingContent"
        if sha(extra_path).lower() != expected.lower():
            return "ContentHashMismatch"
    if not approval_matches(version, manifest, approval):
        return "NotApproved"
    return None


def plan_staged_update(assembly_path, version_name, content_sha256, approval, host_target=None, candidate_target=None):
    """Decide whether a staged update may launch.

    A failure is returned before any simulator or runtime process is started.
    Approval is a version, content hash and approval id. It is not a signature.
    """
    return startup_plan_failure(
        assembly_path, version_name, content_sha256, approval, host_target, candidate_target)


def preflight_download(owner_path, expected_name, embedded_name, bundle_names, embedded_info=None):
    """Accept or reject one owner before any runtime process starts.

    A rejection is a host result. It does not intercept fixed-runtime fail-fast
    and it does not mean the runtime fell back to IL.
    """
    owner_path = Path(owner_path)
    errors = []
    bundle_names = set(bundle_names or [])
    if owner_path.name != expected_name:
        errors.append("owner filename is not the selected download")
    if expected_name in bundle_names or owner_path.name in bundle_names:
        errors.append("same-name bundled dylib is not this download version")
    macho, rtr = None, None
    inspector = load_macho_module()
    try:
        macho = macho_download_audit(owner_path)
    except inspector.MachOInspectionError as exc:
        errors.append(str(exc))
    except OSError as exc:
        errors.append("cannot read owner dylib: " + str(exc))
    if macho is not None:
        if not macho.get("uuid"):
            errors.append("owner dylib has no LC_UUID")
        try:
            rtr = exported_rtr_header(owner_path)
        except ValueError as exc:
            errors.append(str(exc))
        if rtr is None:
            errors.append("missing RTR_HEADER export")
        elif not rtr.get("signatureValid"):
            errors.append("RTR_HEADER signature mismatch")
    if embedded_name != expected_name:
        errors.append("embedded OwnerCompositeExecutable does not match the selected owner filename")
    if embedded_info is not None:
        if not embedded_info.get("component") or not embedded_info.get("platformNative"):
            errors.append("component header is not a platform-native composite owner")
    return {
        "accepted": not errors,
        "errors": errors,
        "expectedName": expected_name,
        "fileName": owner_path.name,
        "embeddedName": embedded_name,
        "macho": macho,
        "rtrHeader": rtr,
        "bundledSameNameCountsAsDownload": False,
        "runtimeFallbackProvided": False,
        "fixedRuntimeFailFastNotIntercepted": True,
        "processStarted": False,
    }


def declared_additional_content(manifest, destination):
    """File hashes the startup plan must match before launch.

    Private and IL-helper hashes come from additionalContent or from the
    compile manifest files map. This does not load those assemblies.
    """
    if not isinstance(manifest, dict):
        return None
    items = []
    declared = manifest.get("additionalContent")
    if isinstance(declared, list):
        for item in declared:
            if not isinstance(item, dict):
                items.append({"path": "", "contentSha256": ""})
                continue
            name = item.get("name")
            raw_path = item.get("path") or (str(Path(destination) / str(name)) if name else "")
            items.append({"path": raw_path, "contentSha256": item.get("contentSha256") or ""})
    files = manifest.get("files")
    if isinstance(files, dict):
        for name in ("TrustedUpdate.Private.dll", "TrustedUpdate.IlOnlyHelper.dll"):
            digest = files.get(name)
            if digest:
                items.append({"path": str(Path(destination) / name), "contentSha256": digest})
    return items or None


def write_payload_file_list(destination, files):
    """Write the host recheck list. This does not launch a process."""
    lines = ["%s %s" % (name, str(files[name]).strip().lower()) for name in sorted(files)]
    Path(destination, "payload-files.txt").write_text("\n".join(lines) + "\n", encoding="ascii")


def stage_downloaded_payload(lane, crossgen_out, destination):
    """Copy one launch payload without starting a process.

    Private and IL-helper files come from the lane. DLL and dylib files in
    crossgen-out are copied after that, so a rewritten component replaces
    an input file of the same name.
    """
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    lane = Path(lane)
    for name in ("TrustedUpdate.IlOnlyHelper.dll", "TrustedUpdate.Private.dll"):
        shutil.copy2(lane / name, destination / name)
    for path in Path(crossgen_out).iterdir():
        if path.is_file() and path.suffix in (".dll", ".dylib"):
            shutil.copy2(path, destination / path.name)
    return destination


def payload_manifest_files(crossgen_out, private, helper, owner):
    """Hashes of the files stage_downloaded_payload puts in the download.

    Rewritten components are read from crossgen-out, not from the input
    copies. Private and IL-helper files are the lane inputs.
    """
    crossgen_out = Path(crossgen_out)
    names = (
        "TrustedUpdate.Update.dll",
        "TrustedUpdate.Contract.dll",
        "TrustedUpdate.AnchorHost.dll",
        "TrustedUpdate.AnchorEntry.dll",
    )
    files = {name: sha(crossgen_out / name) for name in names}
    files[Path(private).name] = sha(private)
    files[Path(helper).name] = sha(helper)
    files[Path(owner).name] = sha(owner)
    return files

def payload_name_is_plain(name):
    text = "" if name is None else str(name)
    return bool(text) and text not in (".", "..") and "/" not in text and "\\" not in text and "\0" not in text


def retire_rejected_payload(candidate_dir, selected_dir):
    """Remove a rejected trusted-update directory after fallback staging.

    The selected directory is never removed. A directory whose name does not
    start with trusted-update-, or the last-known-good directory itself, is
    left in place. This does not launch a process.
    """
    candidate = Path(candidate_dir).resolve()
    selected = Path(selected_dir).resolve()
    if candidate == selected or not candidate.is_dir():
        return {"retired": False, "processStarted": False}
    if not candidate.name.startswith("trusted-update-") or candidate.name == "trusted-update-last-known-good":
        return {"retired": False, "processStarted": False}
    shutil.rmtree(candidate)
    return {"retired": True, "processStarted": False}

def stage_plain_payload(source_dir, destination):
    """Copy one selected payload's plain files. This does not launch a process."""
    source_dir = Path(source_dir)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    copied = []
    for path in source_dir.iterdir():
        if not path.is_file() or not payload_name_is_plain(path.name):
            continue
        shutil.copy2(path, destination / path.name)
        copied.append(path.name)
    return {"copied": sorted(copied), "processStarted": False}

def choose_startup_payload(candidate_manifest, candidate_dir, last_known_manifest=None, last_known_dir=None):
    """Choose a payload before any business process starts.

    A matching candidate is used. If it fails and the last-known-good files
    match, that directory is selected instead. Neither choice launches a
    process or loads an assembly. A candidate with no files map is still
    eligible, matching the previous launch behavior.
    """
    candidate_failure = payload_file_failure(candidate_manifest, candidate_dir)
    if candidate_failure is None:
        return {
            "selected": "candidate",
            "directory": str(candidate_dir),
            "candidateFailure": "None",
            "candidateFile": None,
            "fallbackFailure": None,
            "processStarted": False,
        }
    fallback_failure = None
    if last_known_dir is not None and isinstance(last_known_manifest, dict) and isinstance(last_known_manifest.get("files"), dict) and last_known_manifest.get("files"):
        fallback_failure = payload_file_failure(last_known_manifest, last_known_dir)
        if fallback_failure is None:
            return {
                "selected": "last-known-good",
                "directory": str(last_known_dir),
                "candidateFailure": candidate_failure["failure"],
                "candidateFile": candidate_failure.get("file"),
                "fallbackFailure": "None",
                "processStarted": False,
            }
    return {
        "selected": None,
        "directory": None,
        "candidateFailure": candidate_failure["failure"],
        "candidateFile": candidate_failure.get("file"),
        "fallbackFailure": None if fallback_failure is None else fallback_failure["failure"],
        "processStarted": False,
    }

def payload_file_failure(manifest, destination):
    """Compare compile-manifest file hashes with the copied payload.

    A missing manifest or files map does not fail. A listed file that is
    missing, or whose SHA-256 differs, fails before any business process.
    A blank hash is InvalidCandidate. This is not approval and does not
    load an assembly.
    """
    if not isinstance(manifest, dict):
        return None
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        return None
    destination = Path(destination)
    for name, expected in files.items():
        if not payload_name_is_plain(name):
            return {"failure": "InvalidCandidate", "file": str(name), "processStarted": False}
        digest = "" if expected is None else str(expected).strip()
        path = destination / str(name)
        if not digest:
            return {"failure": "InvalidCandidate", "file": str(name), "processStarted": False}
        if not path.is_file():
            return {"failure": "MissingContent", "file": str(name), "processStarted": False}
        actual = sha(path)
        if actual.lower() != digest.lower():
            return {
                "failure": "ContentHashMismatch",
                "file": str(name),
                "actualSha256": actual,
                "manifestSha256": digest,
                "processStarted": False,
            }
    return None

def plan_update_candidate(update_dll, version_name, manifest_sha256, approval, host_target=None, candidate_target=None, content_root=None, additional=None):
    """Decide whether a downloaded Update.dll may start, before any business process.

    Compares the file SHA-256, the manifest hash, an optional runtime and
    architecture pair, and an approval record of version name, content hash,
    and approval id. This is not a signature check and it does not load the
    assembly. The failure names match TrustedUpdateProcess.TryPlanCandidate.
    """
    failure = startup_plan_failure(
        update_dll, version_name, manifest_sha256, approval, host_target, candidate_target, content_root, additional)
    update_dll = Path(update_dll)
    actual = sha(update_dll) if update_dll.is_file() else None
    manifest = None if manifest_sha256 is None else str(manifest_sha256).strip()
    return {
        "accepted": failure is None,
        "failure": "None" if failure is None else failure,
        "classification": "planned" if failure is None else "host-rejected-before-start",
        "processStarted": False,
        "businessProcessPid": None,
        "assemblyLoadContextCreated": False,
        "actualSha256": actual,
        "manifestSha256": manifest,
        "approval": approval,
    }


def approval_matches(version_name, manifest_sha256, approval):
    if not isinstance(approval, dict):
        return False
    approval_id = str(approval.get("approvalId") or "").strip()
    approval_version = str(approval.get("versionName") or "").strip()
    approval_hash = str(approval.get("contentSha256") or "").strip()
    if not approval_id or not approval_version or not approval_hash:
        return False
    return (approval_version == version_name
            and approval_hash.lower() == str(manifest_sha256).strip().lower())


def synthetic_component_dll(owner_name):
    """PE32+ component whose only useful content is the composite owner name."""
    name = owner_name.encode("utf-8") + b"\0"
    blob = bytearray(0x400)
    blob[0:2] = b"MZ"
    struct.pack_into("<I", blob, 0x3C, 0x80)
    struct.pack_into("<I", blob, 0x80, 0x4550)
    struct.pack_into("<HHIIIHH", blob, 0x84, 0xAA64, 1, 0, 0, 0, 240, 0x22)
    optional = 0x98
    struct.pack_into("<H", blob, optional, 0x20B)
    directories = optional + 112
    struct.pack_into("<II", blob, directories + 14 * 8, 0x200, 72)
    struct.pack_into("<8sIIIIII", blob, 0x80 + 24 + 240, b".text\0\0\0", 0x200, 0x200, 0x200, 0x200, 0, 0)
    struct.pack_into("<IHH", blob, 0x200, 72, 2, 2)
    struct.pack_into("<II", blob, 0x200 + 64, 0x280, 16 + 12 + len(name))
    struct.pack_into("<IHHII", blob, 0x280, READYTORUN_SIGNATURE, 31, 0, COMPONENT_FLAG | PLATFORM_NATIVE_FLAG, 1)
    struct.pack_into("<III", blob, 0x280 + 16, OWNER_COMPOSITE_SECTION, 0x2C0, len(name))
    blob[0x2C0:0x2C0 + len(name)] = name
    return bytes(blob)


def synthetic_owner_with_rtr(fixtures):
    """Structural dylib with one simulator executable segment and an RTR export.

    The bytes are a host fixture, not compiler output and not execution evidence.
    """
    rtr = struct.pack("<IHHII", READYTORUN_SIGNATURE, 31, 0, PLATFORM_NATIVE_FLAG, 1)
    strings = b"\0_RTR_HEADER\0"
    probe = fixtures.standard_commands(7, 0, 0)
    probe.append(struct.pack("<6I", 0x2, 24, 0, 1, 0, len(strings)))
    command_length = len(b"".join(probe))
    text_off = 32 + command_length
    data_off = text_off + 16
    commands = fixtures.standard_commands(7, text_off, data_off)
    symoff = data_off + 16
    stroff = symoff + 16
    commands.append(struct.pack("<6I", 0x2, 24, symoff, 1, stroff, len(strings)))
    payload = b"\xC0\x03\x5F\xD6" * 4 + rtr
    image = fixtures.raw_image(len(commands), b"".join(commands), payload)
    symbol = struct.pack("<IBBHQ", 1, 0x0F, 2, 0, fixtures.DATA_VMADDR)
    return image + symbol + strings


def bundle_dylib_names(app):
    return sorted(path.name for path in Path(app).glob("*.dylib"))


def pointer_value(text):
    if not isinstance(text, str) or text in ("", "(nil)", "0x0", "0"):
        return None
    try:
        return int(text, 0)
    except ValueError:
        return None


def file_sha_if_present(path):
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_file():
        return None
    return sha(candidate)


def negative_log_text(cases):
    lines = [
        "classification=host-rejected-before-start",
        "fixedRuntimeFailFastNotIntercepted=true",
        "runtimeFallbackProvided=false",
        "processStarted=false",
        "note=host rejected the candidate before starting the fixed runtime; fail-fast was not intercepted and IL fallback was not observed",
    ]
    for case in cases:
        preflight = case["preflight"]
        lines.append("case=" + case["name"])
        lines.append("accepted=" + str(bool(preflight.get("accepted"))).lower())
        lines.append("owner=" + str(preflight.get("fileName")))
        lines.append("expected=" + str(preflight.get("expectedName")))
        lines.append("embedded=" + str(preflight.get("embeddedName")))
        for error in preflight.get("errors") or []:
            lines.append("error=" + error)
        lines.append("result=host-rejected-before-start")
    return "\n".join(lines) + "\n"

def build(args):
    out = args.output.resolve(); out.mkdir(parents=False, exist_ok=False)
    for name in ("logs", "source", "input", "host", "prepared"): (out / name).mkdir()
    runtime = args.runtime.resolve(); sdk, csc, crossgen2, base = sdk_inputs(runtime)
    head = capture(["git", "-C", runtime, "rev-parse", "HEAD"]); tracked = capture(["git", "-C", runtime, "status", "--porcelain", "--untracked-files=no"])
    if head != BASE_COMMIT or tracked: raise RuntimeError("runtime tracked source is not the pinned clean base")
    (out / "logs/source-head.txt").write_text(head + "\n", encoding="utf-8")
    (out / "logs/source-status.txt").write_text(capture(["git", "-C", runtime, "status", "--short"]) + "\n", encoding="utf-8")
    run([sdk, "--info"], out / "logs/sdk-info.txt"); run([crossgen2, "--version"], out / "logs/crossgen-version.txt")
    refs = managed_refs(base)
    for path in refs: shutil.copy2(path, out / "input" / path.name)
    source_app = base / "app/RuneCLRPinnedHarness.app"; app = out / "host/TrustedUpdate.app"; shutil.copytree(source_app, app)
    plist = plistlib.loads((app / "Info.plist").read_bytes()); plist.update(CFBundleExecutable="TrustedUpdate", CFBundleName="TrustedUpdate", CFBundleIdentifier="org.runeclr.trustedupdate." + out.name[-12:]); (app / "Info.plist").write_bytes(plistlib.dumps(plist))
    ref_names = {path.name for path in refs}
    for path in app.glob("*.dll"):
        if path.name.startswith(("HarnessBridge", "RuneCLR.TestMaps")) or path.name not in ref_names: path.unlink()
    contract = out / "input/TrustedUpdate.Contract.dll"; host = out / "input/TrustedUpdate.Host.dll"; entry = out / "input/TrustedUpdate.Entry.dll"
    trusted = out / "input/RuneCLR.TrustedUpdate.dll"
    compile_managed(sdk, csc, contract, [FIXTURE / "Contract.cs"], refs, log=out / "logs/contract.compile.log")
    compile_managed(sdk, csc, trusted, [PROJECT / "src/RuneCLR.TrustedUpdate/TrustedUpdateContracts.cs", PROJECT / "src/RuneCLR.TrustedUpdate/TrustedUpdateProcess.cs"], refs, log=out / "logs/trusted-update.compile.log")
    compile_managed(sdk, csc, host, [FIXTURE / "Host.cs"], refs + [contract, trusted], log=out / "logs/host.compile.log")
    compile_managed(sdk, csc, entry, [FIXTURE / "Entry.cs"], refs + [contract, trusted, host], "exe", out / "logs/entry.compile.log")
    for path in (contract, host, entry, trusted): shutil.copy2(path, app / path.name)
    obj = out / "host/TrustedUpdate.host.obj"; crossgen(crossgen2, obj, [contract, host, entry], refs, out / "host", "host"); link(obj, app / "TrustedUpdate.host.dylib", out / "logs/host-link.log")
    for name in ("main.m", "util.h", "coreclrhost.h", "host_runtime_contract.h"): shutil.copy2(base / name, out / "host" / name)
    wrapper = instrument_wrapper((base / "runtime.m").read_text(encoding="utf-8").replace("HarnessBridge.dll", "TrustedUpdate.Entry.dll")); (out / "host/runtime.m").write_text(wrapper, encoding="utf-8")
    run(["xcrun", "--sdk", "iphonesimulator", "clang", "-target", "arm64-apple-ios15.3-simulator", "-fobjc-arc", "-DINVARIANT_GLOBALIZATION=1", "-I" + str(out / "host"), out / "host/main.m", out / "host/runtime.m", "-L" + str(app), "-lcoreclr", "-framework", "UIKit", "-framework", "Foundation", "-Wl,-rpath,@executable_path", "-o", app / "TrustedUpdate"], out / "logs/native-build.log")
    for dylib in app.glob("*.dylib"): run(["codesign", "--force", "--sign", "-", dylib], out / "logs" / (dylib.name + ".sign.log"))
    run(["codesign", "--force", "--sign", "-", app], out / "logs/app-sign.log")
    before = bundle_hashes(app); write(out / "host/bundle-before.json", before)
    write(out / "inputs.json", {"runtime": str(runtime), "runtimeCommit": head, "sdk": capture([sdk, "--version"]), "crossgen2": str(crossgen2), "crossgen2Sha256": sha(crossgen2), "target": "iossimulator-arm64", "configuration": "Debug", "hostBundle": before})
    print("BUILD PASS", flush=True)

def compile_updates(out, sdk, csc, crossgen2, base):
    refs = managed_refs(base)
    prepared = {}
    for version, value_source in (("A", "PrivateVersion.cs"), ("B", "PrivateVersionB.cs")):
        lane = out / "prepared" / version; lane.mkdir()
        contract = lane / "TrustedUpdate.Contract.dll"
        helper = lane / "TrustedUpdate.IlOnlyHelper.dll"
        private = lane / "TrustedUpdate.Private.dll"
        update = lane / "TrustedUpdate.Update.dll"
        anchor_host = lane / "TrustedUpdate.AnchorHost.dll"
        anchor_entry = lane / "TrustedUpdate.AnchorEntry.dll"
        trusted = lane / "RuneCLR.TrustedUpdate.dll"
        compile_managed(sdk, csc, contract, [FIXTURE / "Contract.cs"], refs, log=lane / "contract.compile.log")
        compile_managed(sdk, csc, trusted, [PROJECT / "src/RuneCLR.TrustedUpdate/TrustedUpdateContracts.cs", PROJECT / "src/RuneCLR.TrustedUpdate/TrustedUpdateProcess.cs"], refs, log=lane / "trusted-update.compile.log")
        compile_managed(sdk, csc, anchor_host, [FIXTURE / "Host.cs"], refs + [contract, trusted], log=lane / "anchor-host.compile.log")
        compile_managed(sdk, csc, anchor_entry, [FIXTURE / "Entry.cs"], refs + [contract, trusted, anchor_host], "exe", lane / "anchor-entry.compile.log")
        compile_managed(sdk, csc, helper, [FIXTURE / "IlOnlyHelper.cs"], refs, log=lane / "helper.compile.log")
        compile_managed(sdk, csc, private, [FIXTURE / "PrivateLogic.cs", FIXTURE / value_source], refs, log=lane / "private.compile.log")
        compile_managed(sdk, csc, update, [FIXTURE / "Business.cs", FIXTURE / "Update.cs"], refs + [contract], log=lane / "update.compile.log")
        # Mach-O composites store the owner name as the crossgen output filename
        # with a .dylib extension, and the native-image cache key is that filename
        # only. Keep A and B distinct. Owner --out lives in crossgen-out, not beside
        # the input dlls: crossgen2 creates each rewritten component with
        # FileMode.Create, and an in-place --out truncates that input if emission
        # fails. Never copy those outputs back onto the input dlls. The host
        # composite above remains in place.
        crossgen_out = lane / "crossgen-out"
        crossgen_out.mkdir()
        owner = crossgen_out / ("TrustedUpdate." + version + ".r2r.dylib")
        prelinked = crossgen_out / ("TrustedUpdate." + version + ".r2r.obj")
        watched = (update, contract, anchor_host, anchor_entry, private, helper)
        before = {path: path.read_bytes() for path in watched}
        crossgen(crossgen2, prelinked, [update, contract, anchor_host, anchor_entry], refs, crossgen_out, "owner", inputbubble=True)
        for path, data in before.items():
            if path.read_bytes() != data:
                raise RuntimeError("owner crossgen changed an input dll: " + path.name)
        link(prelinked, owner, crossgen_out / "owner-link.log")
        rewritten_update = crossgen_out / "TrustedUpdate.Update.dll"
        embedded, embedded_error = None, None
        try:
            embedded = owner_composite_from_component(rewritten_update)
        except ValueError as exc:
            embedded_error = str(exc)
        macho, macho_error = None, None
        try:
            macho = macho_download_audit(owner)
        except Exception as exc:
            if exc.__class__.__name__ != "MachOInspectionError" and not isinstance(exc, (OSError, ValueError)):
                raise
            macho_error = str(exc)
        rtr, rtr_error = None, None
        try:
            rtr = exported_rtr_header(owner)
        except ValueError as exc:
            rtr_error = str(exc)
        manifest = {
            "version": version,
            "ownerCompositeExecutable": owner.name,
            "crossgenOutput": prelinked.relative_to(lane).as_posix(),
            "embeddedOwner": embedded,
            "embeddedOwnerError": embedded_error,
            "macho": macho,
            "machoError": macho_error,
            "rtrHeader": rtr,
            "rtrHeaderError": rtr_error,
            "provesNativeExecution": False,
            "files": payload_manifest_files(crossgen_out, private, helper, owner),
            "target": "iossimulator-arm64",
        }
        write(lane / "manifest.json", manifest)
        prepared[version] = manifest
    names = [prepared[version]["ownerCompositeExecutable"] for version in ("A", "B")]
    if len(set(names)) != 2:
        raise RuntimeError("A/B owner composite filenames are not distinct: " + ",".join(names))
    return prepared


def app_container(sim, bundle, kind):
    return Path(capture(["xcrun", "simctl", "get_app_container", sim, bundle, kind]))


def run_negative_preflight(out, bundle_names):
    fixtures = load_macho_fixtures()
    missing_path = out / "logs" / "missing-rtr-header.dylib"
    missing_path.write_bytes(fixtures.standard_image(7)[0])
    cases = [{
        "name": "missing-rtr-header",
        "preflight": preflight_download(missing_path, missing_path.name, missing_path.name, bundle_names),
    }]
    owner_a = out / "prepared" / "A" / "crossgen-out" / "TrustedUpdate.A.r2r.dylib"
    update_a = out / "prepared" / "A" / "crossgen-out" / "TrustedUpdate.Update.dll"
    wrong_path = out / "logs" / "TrustedUpdate.invalid.r2r.dylib"
    if owner_a.is_file() and update_a.is_file():
        shutil.copy2(owner_a, wrong_path)
        try:
            embedded = owner_composite_from_component(update_a)
        except ValueError:
            embedded = None
        embedded_name = None if embedded is None else embedded.get("name")
        cases.append({
            "name": "wrong-owner",
            "preflight": preflight_download(
                wrong_path, "TrustedUpdate.invalid.r2r.dylib", embedded_name, bundle_names, embedded),
        })
    else:
        cases.append({
            "name": "wrong-owner",
            "preflight": {
                "accepted": False,
                "errors": ["prepared owner A missing before negative preflight"],
                "fileName": wrong_path.name,
                "expectedName": "TrustedUpdate.invalid.r2r.dylib",
                "embeddedName": None,
            },
        })
    return cases


def launch_version(args, out, sim, bundle, version, bundle_names, installed_utc, before):
    lane = out / "prepared" / version
    crossgen_out = lane / "crossgen-out"
    owner_name = "TrustedUpdate." + version + ".r2r.dylib"
    owner = crossgen_out / owner_name
    update = crossgen_out / "TrustedUpdate.Update.dll"
    try:
        embedded = owner_composite_from_component(update)
    except ValueError as exc:
        embedded = None
        embedded_error = str(exc)
    else:
        embedded_error = None
    embedded_name = None if embedded is None else embedded.get("name")
    preflight = preflight_download(owner, owner_name, embedded_name, bundle_names, embedded)
    if embedded_error:
        preflight["errors"].append(embedded_error)
        preflight["accepted"] = False
    result = {
        "launched": False,
        "ownerCompositeExecutable": owner_name,
        "installedUtc": installed_utc,
        "bundleUnchanged": None,
        "preflight": preflight,
        "macho": preflight.get("macho"),
        "embeddedOwner": embedded,
        "managedSuccess": False,
        "failure": False,
        "nativeEntry": None,
        "interpreterEntry": None,
        "callbackIdentity": None,
        "bundledSameNameCountsAsDownload": False,
        "downloadPathMatchesCallback": False,
        "nativeImageCacheKey": {
            "kind": "owner-filename-only",
            "includesPath": False,
            "includesHash": False,
            "ownerFileName": owner_name,
        },
    }
    if not preflight["accepted"]:
        result["hostRejectedBeforeStart"] = True
        return result
    data = app_container(sim, bundle, "data")
    destination = data / "Documents" / ("trusted-update-" + version)
    destination.mkdir(parents=True)
    stage_downloaded_payload(lane, crossgen_out, destination)
    downloaded = destination / owner_name
    downloaded_audit = macho_download_audit(downloaded)
    if downloaded_audit["sha256"] != preflight["macho"]["sha256"]:
        result["hostRejectedBeforeStart"] = True
        result["preflight"] = dict(preflight)
        result["preflight"]["accepted"] = False
        result["preflight"]["errors"] = list(preflight["errors"]) + ["copied owner hash differs from the audited owner"]
        return result
    downloaded_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    compile_manifest = {}
    compile_manifest_path = lane / "manifest.json"
    if compile_manifest_path.is_file():
        compile_manifest = json.loads(compile_manifest_path.read_text(encoding="utf-8"))
    last_known_manifest = None
    last_known_dir = None
    recorded = None
    last_known_path = out / "last-known-good.json"
    if last_known_path.is_file():
        try:
            recorded = json.loads(last_known_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            recorded = None
        if isinstance(recorded, dict):
            last_known_manifest = recorded.get("manifest")
            last_known_dir = recorded.get("directory")
    choice = choose_startup_payload(compile_manifest, destination, last_known_manifest, last_known_dir)
    result["startupChoice"] = choice
    result["payloadFiles"] = {
        "failure": choice["candidateFailure"],
        "file": choice["candidateFile"],
        "processStarted": False,
    }
    launch_version_name = version
    candidate_destination = destination
    if choice["selected"] is None:
        result["processPid"] = None
        result["launched"] = False
        result["hostRejectedBeforeStart"] = True
        return result
    if choice["selected"] == "last-known-good":
        fallback_dest = data / "Documents" / "trusted-update-last-known-good"
        staged = stage_plain_payload(last_known_dir, fallback_dest)
        recheck = payload_file_failure(last_known_manifest, fallback_dest)
        result["startupChoice"]["staged"] = staged
        if recheck is not None:
            result["startupChoice"]["fallbackRecheck"] = recheck["failure"]
            result["processPid"] = None
            result["launched"] = False
            result["hostRejectedBeforeStart"] = True
            return result
        owners = sorted(path for path in fallback_dest.glob("*.r2r.dylib") if path.is_file())
        if len(owners) != 1:
            result["startupChoice"]["fallbackOwner"] = [path.name for path in owners]
            result["processPid"] = None
            result["launched"] = False
            result["hostRejectedBeforeStart"] = True
            return result
        destination = fallback_dest
        downloaded = owners[0]
        owner_name = downloaded.name
        downloaded_audit = macho_download_audit(downloaded)
        launch_version_name = str((recorded or {}).get("version") or version)
        listed = last_known_manifest.get("files") if isinstance(last_known_manifest, dict) else None
        if isinstance(listed, dict) and listed:
            write_payload_file_list(destination, listed)
        result["startupChoice"]["launchedDirectory"] = str(destination)
        result["startupChoice"]["launchedVersion"] = launch_version_name
        retired = retire_rejected_payload(candidate_destination, destination)
        result["startupChoice"]["candidateRetired"] = retired["retired"]
    else:
        listed = compile_manifest.get("files") if isinstance(compile_manifest, dict) else None
        if isinstance(listed, dict) and listed:
            write_payload_file_list(destination, listed)
    manifest_path = lane / "update-manifest.json"
    approval_path = lane / "approval.json"
    if choice["selected"] == "candidate" and (manifest_path.is_file() or approval_path.is_file()):
        manifest_file = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
        approval = json.loads(approval_path.read_text(encoding="utf-8")) if approval_path.is_file() else None
        host_target = None
        candidate_target = None
        if all(manifest_file.get(key) for key in ("runtime", "architecture", "hostRuntime", "hostArchitecture")):
            candidate_target = (manifest_file.get("runtime"), manifest_file.get("architecture"))
            host_target = (manifest_file.get("hostRuntime"), manifest_file.get("hostArchitecture"))
        additional = declared_additional_content(manifest_file, destination) or []
        additional.extend(declared_additional_content(compile_manifest, destination) or [])
        plan = plan_update_candidate(
            destination / "TrustedUpdate.Update.dll",
            manifest_file.get("versionName"),
            manifest_file.get("contentSha256"),
            approval,
            host_target,
            candidate_target,
            destination,
            additional or None)
        result["plan"] = plan
        if not plan["accepted"]:
            result["hostRejectedBeforeStart"] = True
            result["processPid"] = None
            result["launched"] = False
            return result
    capture_out = out / ("entry-" + version)
    capture_script = PROJECT / "eng" / "ios-trusted-update-entry-capture.py"
    capture_status = run(
        [sys.executable, capture_script, "--simulator", sim, "--bundle", bundle, "--version", launch_version_name,
         "--owner", downloaded, "--helper", destination / "TrustedUpdate.IlOnlyHelper.dll",
         "--update-dir", destination, "--output", capture_out],
        out / "logs" / ("capture-" + version + ".log"), check=False, timeout=720)
    capture_receipt = {}
    receipt_path = capture_out / "results.json"
    if receipt_path.exists():
        capture_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    stdout_path = capture_out / "managed.stdout.log"
    stderr_path = capture_out / "managed.stderr.log"
    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
    text = stdout_text + "\n" + stderr_text
    installed = app_container(sim, bundle, "app")
    after = bundle_hashes(installed)
    callback = callback_identity(capture_receipt.get("nativeCallbackLines", []))
    callback_sha = file_sha_if_present((callback or {}).get("path"))
    if callback is not None:
        callback = dict(callback)
        callback["sha256"] = callback_sha
    interpreter = next((entry for entry in capture_receipt.get("interpreterEntries", []) if entry.get("kind") == "interpreter-stub"), None)
    if interpreter is not None:
        interpreter = dict(interpreter)
        interpreter["countsAsR2RNativeExecution"] = False
        interpreter["classification"] = "interpreter-or-il-helper"
    native = capture_receipt.get("nativeEntry")
    download_match = bool(
        callback and callback.get("path") and Path(callback["path"]).name == owner_name
        and callback_sha == downloaded_audit["sha256"]
        and pointer_value(callback.get("base"))
        and callback.get("imageSize"))
    if native:
        native = dict(native)
        base_matches = pointer_value((callback or {}).get("base")) == native.get("ownerBase")
        native["countsAsR2RNativeExecution"] = bool(
            native.get("pcInMethodRange") is True
            and native.get("ownerSha256") == downloaded_audit["sha256"]
            and download_match and base_matches)
        native["classification"] = "r2r-method-entry" if native["countsAsR2RNativeExecution"] else "unbound-or-not-download-owner"
    result.update({
        "launched": True,
        "hostRejectedBeforeStart": False,
        "launcherExit": capture_status,
        "processPid": capture_receipt.get("pid"),
        "managedSuccess": capture_receipt.get("managedSuccess", "TRUSTED_UPDATE_SUCCESS" in text),
        "failure": "TRUSTED_UPDATE_FAILURE" in text,
        "downloadedUtc": downloaded_utc,
        "bundleUnchanged": before == after,
        "callbackIdentity": callback,
        "downloadPathMatchesCallback": download_match,
        "nativeEntry": native,
        "interpreterEntry": interpreter,
        "helperSha256": sha(destination / "TrustedUpdate.IlOnlyHelper.dll"),
        "macho": downloaded_audit,
        "payload": {path.name: sha(path) for path in destination.iterdir() if path.is_file()},
        "bundleAfter": after,
    })
    run(["xcrun", "simctl", "terminate", sim, bundle], out / "logs" / ("terminate-" + version + ".log"), check=False)
    return result


def run_process(args):
    out = args.output.resolve()
    state = json.loads((out / "inputs.json").read_text(encoding="utf-8"))
    runtime = Path(state["runtime"])
    sdk, csc, crossgen2, base = sdk_inputs(runtime)
    app = out / "host/TrustedUpdate.app"
    plist = plistlib.loads((app / "Info.plist").read_bytes())
    bundle = plist["CFBundleIdentifier"]
    bundle_names = bundle_dylib_names(app)
    sim = capture(["xcrun", "simctl", "create", "RuneCLR-Trusted-Update", "com.apple.CoreSimulator.SimDeviceType.iPhone-17", "com.apple.CoreSimulator.SimRuntime.iOS-27-0"])
    logs = out / "logs"
    try:
        run(["xcrun", "simctl", "boot", sim], logs / "boot.log")
        run(["xcrun", "simctl", "bootstatus", sim, "-b"], logs / "bootstatus.log")
        run(["xcrun", "simctl", "install", sim, app], logs / "install.log")
        installed_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        compile_updates(out, sdk, csc, crossgen2, base)
        negative_cases = run_negative_preflight(out, bundle_names)
        negative_log = logs / "negative-owner-preflight.log"
        negative_log.write_text(negative_log_text(negative_cases), encoding="utf-8")
        if any(case["preflight"].get("accepted") for case in negative_cases):
            raise RuntimeError("negative owner/RTR preflight was accepted; refusing to launch")
        before = json.loads((out / "host/bundle-before.json").read_text(encoding="utf-8"))
        results = {}
        after = before
        for version in ("A", "B"):
            item = launch_version(args, out, sim, bundle, version, bundle_names, installed_utc, before)
            after = item.pop("bundleAfter", after)
            results[version] = item
        proven = all((results[version].get("nativeEntry") or {}).get("countsAsR2RNativeExecution") is True for version in ("A", "B"))
        write(out / "host/bundle-after.json", after)
        write(out / "results.json", {
            "simulator": sim,
            "bundle": bundle,
            "runs": results,
            "ownerFileNames": [results[version].get("ownerCompositeExecutable") for version in ("A", "B")],
            "ownerFileNamesDiffer": results["A"].get("ownerCompositeExecutable") != results["B"].get("ownerCompositeExecutable"),
            "scope": "startup-selected single-version noncollectible iOS simulator lane",
            "nativeUnload": False,
            "sameProcessSwitch": False,
            "installedUtc": installed_utc,
            "nativeExecutionProven": proven,
            "machoProvesNativeExecution": False,
            "runtimeFallback": {
                "providedByRuntime": False,
                "observedByCrashingProcess": False,
                "fixedRuntimeFailFastNotIntercepted": True,
                "note": "On this pinned runtime, a failed Apple native-image callback fail-fasts in nativeimage.cpp and does not fall back to IL. This host rejects a bad owner or a missing RTR_HEADER before process start. Another version is selected only by a later process start.",
            },
            "negativeControl": {
                "ownerCompositeExecutable": "TrustedUpdate.invalid.r2r.dylib",
                "classification": "host-rejected-before-start",
                "rawLog": str(negative_log),
                "cases": [{"name": case["name"], "accepted": case["preflight"].get("accepted"), "errors": case["preflight"].get("errors")} for case in negative_cases],
                "fixedRuntimeFailFastNotIntercepted": True,
                "processStarted": False,
            },
        })
    finally:
        run(["xcrun", "simctl", "shutdown", sim], logs / "shutdown.log", check=False)
        run(["xcrun", "simctl", "delete", sim], logs / "delete.log", check=False)
    print("RUN COMPLETE", flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("phase", choices=("build", "run", "all")); parser.add_argument("--root", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args(); args.runtime = args.root / "runtime"
    if args.phase in ("build", "all"): build(args)
    if args.phase in ("run", "all"): run_process(args)

if __name__ == "__main__": raise SystemExit(main())


