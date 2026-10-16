"""Validate pinned Windows x64 native-frame and interpreter observations."""

import csv
import hashlib
import re
import struct
from pathlib import Path


def parse_map(path):
    """Read crossgen2 --mapcsv method bodies, excluding imports and stubs."""
    methods = []
    with open(path, newline="", encoding="utf-8-sig") as source:
        reader = csv.reader(source)
        if next(reader, None) != ["Rva", "Length", "Relocs", "Section", "Symbol", "Node Type"]:
            raise ValueError("Unrecognized crossgen2 map schema: " + str(path))
        for row in reader:
            if len(row) < 6 or row[-1] != "MethodWithGCInfo":
                continue
            length = int(row[1])
            if length > 0:
                methods.append({"rva": int(row[0], 16), "length": length,
                                "symbol": ",".join(row[4:-1])})
    if not methods:
        raise ValueError("No native method bodies in crossgen2 map: " + str(path))
    return methods


def read_image(path):
    """Read executable sections and AMD64 R2R RuntimeFunctions ranges."""
    data = Path(path).read_bytes()

    def unpack(fmt, offset):
        size = struct.calcsize(fmt)
        if offset < 0 or offset + size > len(data):
            raise ValueError("Truncated PE image: " + str(path))
        return struct.unpack_from(fmt, data, offset)

    if data[:2] != b"MZ":
        raise ValueError("Missing DOS header: " + str(path))
    pe = unpack("<I", 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Missing PE signature: " + str(path))
    section_count = unpack("<H", pe + 6)[0]
    optional_size = unpack("<H", pe + 20)[0]
    optional = pe + 24
    magic = unpack("<H", optional)[0]
    if magic not in (0x10B, 0x20B):
        raise ValueError("Unsupported PE optional header")
    directories = optional + (112 if magic == 0x20B else 96)
    sections = []
    for i in range(section_count):
        offset = optional + optional_size + i * 40
        virtual_size, rva, raw_size, raw = unpack("<IIII", offset + 8)
        flags = unpack("<I", offset + 36)[0]
        sections.append({"rva": rva, "length": max(virtual_size, raw_size),
                         "raw": raw, "raw_length": raw_size,
                         "executable": bool(flags & 0x20000000)})

    def file_offset(rva, length=1):
        for section in sections:
            relative = rva - section["rva"]
            if 0 <= relative and relative + length <= section["raw_length"]:
                return section["raw"] + relative
        raise ValueError("PE RVA has no file-backed section: " + hex(rva))

    cor_rva, cor_size = unpack("<II", directories + 14 * 8)
    if not cor_rva or cor_size < 72:
        raise ValueError("Missing CLR header: " + str(path))
    cor = file_offset(cor_rva, 72)
    native_rva, native_size = unpack("<II", cor + 64)
    if not native_rva or native_size < 16:
        raise ValueError("Missing R2R header: " + str(path))
    header = file_offset(native_rva, native_size)
    signature, major, minor, flags, count = unpack("<IHHII", header)
    if signature != 0x00525452:
        raise ValueError("Invalid R2R signature: " + str(path))
    if flags & 0x20:
        raise ValueError("Fixture must use independent per-assembly R2R images")
    functions = []
    for i in range(count):
        kind, rva, size = unpack("<III", header + 16 + i * 12)
        if kind != 102:
            continue
        table = file_offset(rva, size)
        # AMD64 entries are BeginAddress, EndAddress, UnwindInfo RVA; the
        # crossgen table can end with an extra four-byte sentinel.
        for j in range(size // 12):
            begin, end, _ = unpack("<III", table + j * 12)
            if begin < end:
                functions.append((begin, end))
    if not functions:
        raise ValueError("Missing AMD64 R2R RuntimeFunctions: " + str(path))
    return {"sha256": hashlib.sha256(data).hexdigest(), "sections": sections,
            "runtime_functions": functions, "r2r_version": [major, minor]}


def assess_witnesses(witnesses, image_maps):
    """Bind active return PCs to exact precompiled methods by image SHA-256."""
    expected = {"host": "TrustedComposition_HostObject__Touch",
                "update": "TrustedComposition_UpdateModule__Execute",
                "private": "TrustedComposition_PrivateLogic__Read"}
    image_maps = {key.lower(): value for key, value in image_maps.items()}
    image_cache, map_cache = {}, {}
    matches = []
    for witness in witnesses:
        label = witness["Label"]
        if label not in expected:
            continue
        path = witness["Image"]
        if path not in image_cache:
            digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            image_cache[path] = read_image(path) if digest in image_maps else {"sha256": digest}
        image = image_cache[path]
        digest = image["sha256"]
        if digest not in image_maps:
            continue
        if digest not in map_cache:
            map_cache[digest] = parse_map(image_maps[digest])
        pc, base = int(witness["Pc"], 16), int(witness["AllocationBase"], 16)
        rva = int(witness["Rva"])
        if pc - base != rva or not witness["Executable"]:
            raise ValueError("Native witness address/protection differs")
        executable = any(section["executable"] and section["rva"] <= rva <
                         section["rva"] + section["length"] for section in image["sections"])
        native = any(begin <= rva < end for begin, end in image["runtime_functions"])
        for method in map_cache[digest]:
            if not method["symbol"].endswith("_" + expected[label]):
                continue
            if not method["rva"] <= rva < method["rva"] + method["length"]:
                continue
            if not executable or not native:
                raise ValueError("Selected method PC is outside executable R2R RuntimeFunctions")
            matches.append({"label": label, "image": path, "sha256": digest,
                            "pc": witness["Pc"], "rva": rva,
                            "symbol": method["symbol"], "method_rva": method["rva"],
                            "method_length": method["length"]})
    counts = {label: sum(match["label"] == label for match in matches) for label in expected}
    return {"passed": all(counts.values()),
            "labels": {label: {"passed": count > 0} for label, count in counts.items()},
            "counts": counts, "matches": matches}


def assess_interpreter(report, diagnostics):
    """Require called helper precode plus positive successful interpreter IR."""
    entries = []
    sessions = report["Sessions"]
    if not sessions:
        raise ValueError("Missing executed sessions")
    for session in sessions:
        found = [item["Entry"] for item in session["Entries"]
                 if item["Entry"]["DefiningType"] == "TrustedComposition.IlOnlyHelper"
                 and item["Entry"]["Method"] == "Compute"]
        if len(found) != 1:
            raise ValueError("Missing unique executed IL-only helper observation")
        entry = found[0]
        if not entry["Interpreted"] or entry["PrecodeType"] != 6 or not entry["InvocationEvidence"]:
            raise ValueError("Executed helper did not retain interpreter precode")
        entries.append(entry)
    compiled = re.findall(r"^Compiled method: .*TrustedComposition\.IlOnlyHelper:Compute\([^\r\n]*",
                          diagnostics, re.MULTILINE)
    if not compiled:
        raise ValueError("Missing successful IL-only helper interpreter bytecode dump")
    return {"passed": True, "observed_sessions": len(entries), "compiled_methods": compiled,
            "scope": "Selected helper after checked invocations; no full child-dispatch coverage"}
