#!/usr/bin/env python3
"""Measure closed-generic effects on trusted-game IL and R2R DLL size.

The driver builds five explicit variants of the same small C# template with a
stock SDK, crossgens each IL image once with the pinned Checked crossgen2, and
records actual IL/R2R bytes, PE/ReadyToRun header fields, MVID parity, map code
and metadata nodes, and deterministic gzip sizes.

It does not execute the images, use a host, load author code, sign, build or
patch a runtime, or install anything.

The --replay-retained mode is offline-only: it reads a retained experiment
root, verifies image/map/log/source pins plus IL/R2R MVID and header bindings,
and writes a fresh report outside that root. It never starts a subprocess or
touches an SDK, runtime, crossgen or other product path.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / "trusted-game-generic-size"
PROJECT = FIXTURE / "TrustedGameGenericSize.csproj"
ASSEMBLY = "TrustedGameGenericSize.dll"
EXPECTED_DEFINES = ("BASELINE", "REF1", "REF8", "VAL1", "VAL8")

R2R_SECTION_NAMES = {
    100: "CompilerIdentifier",
    101: "ImportSections",
    102: "RuntimeFunctions",
    103: "MethodDefEntryPoints",
    104: "ExceptionInfo",
    105: "DebugInfo",
    106: "DelayLoadMethodCallThunks",
    108: "AvailableTypes",
    109: "InstanceMethodEntryPoints",
    110: "InliningInfo",
    111: "ProfileDataInfo",
    112: "ManifestMetadata",
    113: "AttributePresence",
    114: "InliningInfo2",
    115: "ComponentAssemblies",
    116: "OwnerCompositeExecutable",
    117: "PgoInstrumentationData",
    118: "ManifestAssemblyMvids",
    119: "CrossModuleInlineInfo",
    120: "HotColdMap",
    121: "MethodIsGenericMap",
    122: "EnclosingTypeMap",
    123: "TypeGenericInfoMap",
    124: "ExternalTypeMaps",
    125: "ProxyTypeMaps",
    126: "TypeMapAssemblyTargets",
    127: "WasmAsyncResumeInfo",
}

TYPE_ALIASES = {
    "int32": "int",
    "int64": "long",
    "int16": "short",
    "uint32": "uint",
    "uint64": "ulong",
    "uint16": "ushort",
    "uint8": "byte",
    "sbyte": "sbyte",
    "single": "float",
    "double": "double",
    "boolean": "bool",
    "char": "char",
    "string": "string",
    "object": "object",
    "guid": "guid",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gzip_size(data: bytes) -> int:
    return len(gzip.compress(data, compresslevel=9, mtime=0))


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def align4(value: int) -> int:
    return (value + 3) & ~3


def pe_sections(data: bytes, optional_offset: int, optional_size: int, count: int):
    sections = []
    base = optional_offset + optional_size
    for index in range(count):
        offset = base + index * 40
        sections.append(
            {
                "name": data[offset : offset + 8].rstrip(b"\0").decode("ascii", errors="replace"),
                "virtualSize": u32(data, offset + 8),
                "virtualAddress": u32(data, offset + 12),
                "rawSize": u32(data, offset + 16),
                "rawPointer": u32(data, offset + 20),
                "characteristics": u32(data, offset + 36),
            }
        )
    return sections


def rva_to_offset(rva: int, sections):
    for section in sections:
        span = max(section["virtualSize"], section["rawSize"])
        if section["virtualAddress"] <= rva < section["virtualAddress"] + span:
            return rva - section["virtualAddress"] + section["rawPointer"]
    return None


def parse_metadata(data: bytes, offset: int):
    if data[offset : offset + 4] != b"BSJB":
        raise RuntimeError("Metadata signature is not BSJB")
    version_length = u32(data, offset + 12)
    version = data[offset + 16 : offset + 16 + version_length].split(b"\0", 1)[0].decode(
        "utf-8", errors="replace"
    )
    cursor = offset + 16 + version_length
    stream_count = u16(data, cursor + 2)
    cursor += 4
    streams = {}
    for _ in range(stream_count):
        stream_offset = u32(data, cursor)
        stream_size = u32(data, cursor + 4)
        cursor += 8
        name_end = data.index(b"\0", cursor)
        name = data[cursor:name_end].decode("ascii", errors="replace")
        cursor = offset + align4(name_end + 1 - offset)
        streams[name] = {"offset": stream_offset, "size": stream_size}

    if "#GUID" not in streams:
        raise RuntimeError("Metadata has no #GUID heap")
    tables_name = "#~" if "#~" in streams else "#-"
    if tables_name not in streams:
        raise RuntimeError("Metadata has no #~ or #- tables stream")
    tables = streams[tables_name]
    table_offset = offset + tables["offset"]
    heap_sizes = data[table_offset + 6]
    valid = u64(data, table_offset + 8)
    cursor = table_offset + 24
    row_counts = []
    for table_index in range(64):
        if valid & (1 << table_index):
            row_counts.append(u32(data, cursor))
            cursor += 4
    if not row_counts or row_counts[0] < 1:
        raise RuntimeError("Metadata Module table is empty")
    string_size = 4 if heap_sizes & 0x01 else 2
    guid_size = 4 if heap_sizes & 0x02 else 2
    module_row = cursor
    mvid_index = (
        u32(data, module_row + 2 + string_size)
        if guid_size == 4
        else u16(data, module_row + 2 + string_size)
    )
    if mvid_index < 1:
        raise RuntimeError("Module table has no MVID")
    guid_offset = offset + streams["#GUID"]["offset"] + (mvid_index - 1) * 16
    guid = data[guid_offset : guid_offset + 16]
    if len(guid) != 16:
        raise RuntimeError("Truncated MVID in #GUID heap")
    first, second, third = struct.unpack_from("<IHH", guid, 0)
    tail = guid[8:16]
    mvid = (
        f"{first:08x}-{second:04x}-{third:04x}-"
        f"{tail[0]:02x}{tail[1]:02x}-"
        f"{''.join(f'{byte:02x}' for byte in tail[2:])}"
    )
    return {
        "version": version,
        "mvid": mvid,
        "heapSizes": heap_sizes,
        "streams": {name: dict(info) for name, info in streams.items()},
    }


def parse_pe(path: Path):
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise RuntimeError("Not a PE image: " + str(path))
    pe_offset = u32(data, 0x3C)
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise RuntimeError("Missing PE signature: " + str(path))
    coff = pe_offset + 4
    machine = u16(data, coff)
    section_count = u16(data, coff + 2)
    optional_size = u16(data, coff + 16)
    optional = coff + 20
    magic = u16(data, optional)
    if magic == 0x20B:
        image_base = u64(data, optional + 24)
        directory_count = u32(data, optional + 108)
        directories = optional + 112
        format_name = "PE32+"
    elif magic == 0x10B:
        image_base = u32(data, optional + 28)
        directory_count = u32(data, optional + 92)
        directories = optional + 96
        format_name = "PE32"
    else:
        raise RuntimeError(f"Unsupported optional header magic 0x{magic:x}")
    size_of_image = u32(data, optional + 56)
    sections = pe_sections(data, optional, optional_size, section_count)
    result = {
        "path": str(path),
        "format": format_name,
        "machine": f"0x{machine:04x}",
        "machineName": {0x8664: "AMD64", 0x14C: "I386", 0xAA64: "ARM64"}.get(machine, "unknown"),
        "imageBase": image_base,
        "sizeOfImage": size_of_image,
        "sections": sections,
        "sectionRawTotal": sum(section["rawSize"] for section in sections),
        "cor20": None,
        "r2r": None,
        "metadata": None,
    }
    if directory_count > 14:
        cor_rva = u32(data, directories + 14 * 8)
        cor_size = u32(data, directories + 14 * 8 + 4)
        result["cor20"] = {"rva": cor_rva, "size": cor_size}
        cor_file = rva_to_offset(cor_rva, sections)
        if cor_file is not None:
            metadata_rva = u32(data, cor_file + 8)
            metadata_size = u32(data, cor_file + 12)
            managed_rva = u32(data, cor_file + 64)
            managed_size = u32(data, cor_file + 68)
            result["cor20"].update(
                {
                    "cb": u32(data, cor_file),
                    "flags": u32(data, cor_file + 16),
                    "entryPoint": u32(data, cor_file + 20),
                    "metadataRva": metadata_rva,
                    "metadataSize": metadata_size,
                    "managedNativeHeaderRva": managed_rva,
                    "managedNativeHeaderSize": managed_size,
                }
            )
            metadata_file = rva_to_offset(metadata_rva, sections)
            if metadata_file is not None:
                result["metadata"] = parse_metadata(data, metadata_file)
            if managed_rva:
                native_file = rva_to_offset(managed_rva, sections)
                if native_file is None:
                    raise RuntimeError("ManagedNativeHeader RVA is not mapped")
                signature = u32(data, native_file)
                major = u16(data, native_file + 4)
                minor = u16(data, native_file + 6)
                flags = u32(data, native_file + 8)
                r2r_sections_count = u32(data, native_file + 12)
                r2r_sections = []
                for index in range(r2r_sections_count):
                    section_offset = native_file + 16 + index * 8
                    section_type = u32(data, section_offset)
                    r2r_sections.append(
                        {
                            "type": section_type,
                            "name": R2R_SECTION_NAMES.get(section_type, f"Unknown({section_type})"),
                            "rva": u32(data, section_offset + 4),
                        }
                    )
                result["r2r"] = {
                    "signature": f"0x{signature:08x}",
                    "signatureOk": signature == 0x00525452,
                    "major": major,
                    "minor": minor,
                    "flags": flags,
                    "sectionCount": r2r_sections_count,
                    "sections": r2r_sections,
                }
    return result


def normalize_type(label: str) -> str:
    text = label.strip()
    text = text.replace("System___Canon", "__Canon")
    if text.startswith("__Array<") and text.endswith(">"):
        return normalize_type(text[8:-1]) + "[]"
    if text.startswith("System."):
        text = text[7:]
    if text.startswith("System_"):
        text = text[7:]
    if text.startswith("S_P_CoreLib_"):
        text = text[len("S_P_CoreLib_") :]
    suffix = ""
    if text.endswith("[]"):
        suffix = "[]"
        text = text[:-2]
    text = text.split("_")[-1]
    text = TYPE_ALIASES.get(text.lower(), text.lower())
    return text + suffix


def extract_label(symbol: str):
    marker = "Cell_1<" if "Cell_1<" in symbol else ("Relay<" if "Relay<" in symbol else None)
    if marker is None:
        return None
    start = symbol.find(marker) + len(marker)
    depth = 1
    for index in range(start, len(symbol)):
        if symbol[index] == "<":
            depth += 1
        elif symbol[index] == ">":
            depth -= 1
            if depth == 0:
                return symbol[start:index]
    return None


def parse_map(map_csv: Path, map_text: Path, declared):
    rows = []
    with map_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            symbol = (raw.get("Symbol") or "").strip()
            node = (raw.get("Node Type") or "").strip()
            length_text = (raw.get("Length") or "").strip()
            try:
                length = int(length_text) if length_text else None
            except ValueError:
                length = None
            rows.append(
                {
                    "rva": (raw.get("Rva") or "").strip(),
                    "length": length,
                    "relocs": (raw.get("Relocs") or "").strip(),
                    "section": (raw.get("Section") or "").strip(),
                    "symbol": symbol,
                    "nodeType": node,
                }
            )

    def is_method_node(node: str) -> bool:
        return node in {
            "MethodWithGCInfo",
            "Method",
            "UnboxingStub",
            "InstantiatingStub",
            "Prestub",
        }

    generic_rows = []
    for row in rows:
        symbol = row["symbol"]
        label = extract_label(symbol)
        is_generic = "Cell_1<" in symbol or ("Relay" in symbol and label is not None)
        if not is_generic:
            continue
        row["label"] = label
        row["canonical"] = label is not None and "__Canon" in label
        row["methodNode"] = (
            row["section"] == ".text"
            and is_method_node(row["nodeType"])
            and row["length"] is not None
        )
        generic_rows.append(row)

    method_rows = [row for row in generic_rows if row["methodNode"]]
    exact_rows = [row for row in method_rows if not row["canonical"]]
    canonical_rows = [row for row in method_rows if row["canonical"]]
    labels = sorted({row["label"] for row in generic_rows if row["label"]})
    normalized_labels = {normalize_type(label) for label in labels}

    declared_observation = {}
    for item in declared:
        normalized = normalize_type(item)
        matching_rows = [
            row
            for row in generic_rows
            if row["label"] and normalize_type(row["label"]) == normalized
        ]
        matching_code = [row for row in matching_rows if row["methodNode"]]
        declared_observation[item] = {
            "normalized": normalized,
            "observedInMap": bool(matching_rows),
            "observedAsCanonical": any(row["canonical"] for row in matching_rows),
            "observedAsCode": bool(matching_code),
            "observedAsExactCode": any(not row["canonical"] for row in matching_code),
        }

    stats = {}
    for line in map_text.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(
            r"^\s*(\d+)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*(\d+)\s*\|\s*(.+?)\s*$",
            line,
        )
        if match:
            node = match.group(5)
            stats[node] = {
                "length": int(match.group(1)),
                "percentFile": float(match.group(2)),
                "average": float(match.group(3)),
                "count": int(match.group(4)),
            }

    return {
        "rows": len(rows),
        "genericMapEntries": len(generic_rows),
        "genericMethodNodeEntries": len(method_rows),
        "exactMethodNodeEntries": len(exact_rows),
        "canonicalMethodNodeEntries": len(canonical_rows),
        "exactMethodNodeBytes": sum(row["length"] for row in exact_rows),
        "canonicalMethodNodeBytes": sum(row["length"] for row in canonical_rows),
        "genericCodeBytes": sum(row["length"] for row in method_rows),
        "allMethodNodeBytes": sum(
            row["length"]
            for row in rows
            if row["section"] == ".text"
            and is_method_node(row["nodeType"])
            and row["length"] is not None
        ),
        "observedLabels": labels,
        "observedNormalizedLabels": sorted(normalized_labels),
        "declaredObservation": declared_observation,
        "methodSymbols": [
            {
                "symbol": row["symbol"],
                "label": row["label"],
                "canonical": row["canonical"],
                "nodeType": row["nodeType"],
                "bytes": row["length"],
            }
            for row in method_rows
        ],
        "nodeStats": stats,
        "nodeStatsSelected": {
            name: stats.get(name)
            for name in (
                "CopiedMetadataBlobNode",
                "ManifestMetadataTableNode",
                "TypesTableNode",
                "MethodEntryPointTableNode",
                "RuntimeFunctionsTableNode",
                "ExceptionInfoLookupTableNode",
                "DebugInfoTableNode",
                "MethodWithGCInfo",
                "CopiedMethodILNode",
            )
        },
    }


def load_variants():
    variants = json.loads((FIXTURE / "variants.json").read_text(encoding="utf-8"))
    if len(variants) != 5:
        raise RuntimeError("variants.json must contain exactly five variants")
    if tuple(item["define"] for item in variants) != EXPECTED_DEFINES:
        raise RuntimeError("variants.json defines are not the expected five variants")
    return variants


def resolve_dotnet(value: Path) -> Path:
    if value.is_dir():
        value = value / ("dotnet.exe" if os.name == "nt" else "dotnet")
    if not value.is_file():
        raise RuntimeError("SDK executable not found: " + str(value))
    return value.resolve()


def run_command(records, log_dir: Path, name: str, argv, cwd: Path, timeout: int):
    started = time.time()
    env = dict(os.environ)
    env.update(
        {
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
            "DOTNET_NOLOGO": "1",
            "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        }
    )
    try:
        process = subprocess.run(
            [str(item) for item in argv],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
        code = process.returncode
        stdout = process.stdout or ""
        stderr = process.stderr or ""
    except FileNotFoundError as error:
        code = None
        stdout = ""
        stderr = str(error)
    duration = round(time.time() - started, 3)
    stdout_path = log_dir / (name + ".stdout.log")
    stderr_path = log_dir / (name + ".stderr.log")
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    record = {
        "name": name,
        "argv": [str(item) for item in argv],
        "cwd": str(cwd),
        "exitCode": code,
        "durationSeconds": duration,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "stdoutSha256": sha256_file(stdout_path),
        "stderrSha256": sha256_file(stderr_path),
    }
    records.append(record)
    return record


def find_built_assembly(build_root: Path) -> Path:
    hits = []
    for path in build_root.rglob(ASSEMBLY):
        lowered = [part.lower() for part in path.parts]
        if "ref" in lowered or "obj" in lowered:
            continue
        if path.is_file():
            hits.append(path)
    if len(hits) != 1:
        raise RuntimeError(
            f"Expected one {ASSEMBLY} under {build_root}, found {len(hits)}: {hits}"
        )
    return hits[0]


def file_bytes(path: Path):
    data = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(data),
        "sha256": sha256_bytes(data),
        "gzipBytes": gzip_size(data),
    }


def build_report(output: Path, results) -> str:
    lines = []
    lines.append("# Trusted-game closed-generic size measurement")
    lines.append("")
    lines.append(f"Generated: {results['generatedAt']}")
    lines.append(f"Output root: {output}")
    lines.append("")
    replay = results.get("mode") == "offline-replay"
    lines.append("## Scope")
    lines.append("")
    if replay:
        lines.append(
            "Offline replay of retained IL/R2R/map/log bytes. No managed build, crossgen,"
            " dotnet, host, author code, product path or subprocess was used. Input pins"
            " were verified before and after replay."
        )
    else:
        lines.append(
            "Five stock managed Release builds of one template, each crossgened once with"
            " identical per-assembly Windows x64 settings. No image was executed, no host"
            " or author code was loaded, and no runtime or system installation was changed."
        )
    lines.append("")
    lines.append("## Inputs")
    lines.append("")
    if replay:
        parent = results["parent"]
        harness = results["harness"]
        pins = results["inputPins"]
        verification = results["verification"]
        lines.append(
            f"- Retained parent: {parent['root']} (results SHA-256 {parent['resultsSha256']},"
            f" failure SHA-256 {parent['failureSha256']})"
        )
        lines.append(
            f"- Parent report failure: status {parent['failureStatus']},"
            f" error {parent['failureError']}"
        )
        lines.append(
            f"- Launch harness pin: {harness['launch']['pinSha256']}"
            f" ({harness['launch']['pinBytes']} B); retained copy SHA-256"
            f" {harness['launch']['retainedSha256']}"
        )
        lines.append(
            f"- Final harness: {harness['final']['sha256']} ({harness['final']['bytes']} B)"
        )
        if harness.get("previousFinal"):
            lines.append(
                f"- Previous final harness pin: {harness['previousFinal']['sha256']}"
                f" ({harness['previousFinal']['bytes']} B)"
            )
        lines.append("- Harness note: " + harness["note"])
        lines.append(
            f"- Input pins: {pins['before']['fileCount']} files; before"
            f" {pins['before']['manifestSha256']}; after {pins['after']['manifestSha256']};"
            f" unchanged={pins['unchanged']}"
        )
        lines.append(
            f"- Verification: {verification['commands']['builds']} build logs,"
            f" {verification['commands']['crossgens']} crossgen logs,"
            f" {len(verification['variants'])} image/map/MVID/header sets,"
            f" {len(verification['sourceFixtures']['entries'])} source pins."
        )
        lines.append(
            "- Current fixture comparison is recorded; the current checkout is not"
            " claimed to be immutable at launch."
        )
    else:
        inputs = results["inputs"]
        lines.append(f"- SDK: {inputs['sdk']['path']} ({inputs['sdk']['version']})")
        lines.append(
            f"- Runtime: {inputs['runtime']['path']} branch {inputs['runtime']['branch']},"
            f" commit {inputs['runtime']['commit']}, clean={inputs['runtime']['clean']}"
        )
        lines.append(
            f"- crossgen2: {inputs['crossgen2']['path']} ({inputs['crossgen2']['version']},"
            f" SHA-256 {inputs['crossgen2']['sha256']})"
        )
        lines.append(
            f"- Framework references: {inputs['framework']['referenceCount']} DLLs from"
            f" {inputs['framework']['path']}"
        )
        lines.append(
            "- Evidence: source-pins.json, commands.json, references.json,"
            " crossgen-files.json and logs/."
        )
        regeneration = results.get("reportRegeneration")
        if regeneration:
            lines.append(
                "- Report regenerated from saved IL/R2R files: "
                f"{regeneration['newManagedBuilds']} new managed builds and "
                f"{regeneration['newCrossgenOutputs']} new crossgen outputs."
            )
            lines.append("- Corrections: " + " ".join(regeneration["corrections"]))
        if (output / "source-pins.final.json").is_file():
            lines.append(
                "- Final harness pins are in source-pins.final.json;"
                " source-pins.json retains the run-time harness pin."
            )
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append(
        "| variant | kind | closed types | IL bytes | R2R bytes | R2R/IL | R2R vs baseline |"
        " gzip IL | gzip R2R | generic method nodes (exact/canonical) | generic method-node bytes |"
    )
    lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for item in results["variants"]:
        variant = item["variant"]
        comparison = item["comparison"]
        map_info = item["map"]
        types = ", ".join(variant["instantiations"]) if variant["instantiations"] else "none"
        lines.append(
            "| {key} | {kind} | {types} | {il} | {r2r} | {ratio:.4f} | {delta:+d} ({pct:+.2f}%) |"
            " {gil} | {gr2r} | {exact}/{canonical} | {method_bytes} |".format(
                key=variant["key"],
                kind=variant["kind"],
                types=types,
                il=item["il"]["bytes"],
                r2r=item["r2r"]["bytes"],
                ratio=item["r2r"]["bytes"] / item["il"]["bytes"],
                delta=comparison["r2rDeltaVsBaseline"],
                pct=comparison["r2rPercentVsBaseline"],
                gil=item["il"]["gzipBytes"],
                gr2r=item["r2r"]["gzipBytes"],
                exact=map_info["exactMethodNodeEntries"],
                canonical=map_info["canonicalMethodNodeEntries"],
                method_bytes=map_info["genericCodeBytes"],
            )
        )
    lines.append("")
    lines.append("## Measured deltas")
    lines.append("")
    for comparison in results["comparisons"]:
        lines.append(
            "- {label}: IL {il:+.3f} B, gzip IL {gil:+.3f} B, R2R {r2r:+.3f} B,"
            " gzip R2R {gzip:+.3f} B, generic method-node bytes {method:+.3f} B"
            " per additional declared type (not per method body).".format(
                label=comparison["label"],
                il=comparison["ilPerInstantiation"],
                gil=comparison["gzipIlPerInstantiation"],
                r2r=comparison["r2rPerInstantiation"],
                gzip=comparison["gzipR2rPerInstantiation"],
                method=comparison["genericCodeBytesPerInstantiation"],
            )
        )
    lines.append("")
    lines.append("Direct one-to-eight comparisons use seven additional closed types;")
    lines.append("they are descriptive for this sample, not production multipliers.")
    lines.append("")
    baseline = next(item for item in results["variants"] if item["variant"]["key"] == "baseline")
    ref1 = next(item for item in results["variants"] if item["variant"]["key"] == "ref1")
    ref8 = next(item for item in results["variants"] if item["variant"]["key"] == "ref8")
    val1 = next(item for item in results["variants"] if item["variant"]["key"] == "val1")
    val8 = next(item for item in results["variants"] if item["variant"]["key"] == "val8")
    for left, right, label in (
        (baseline, ref8, "ref8 vs baseline"),
        (ref1, ref8, "ref8 vs ref1"),
        (baseline, val8, "val8 vs baseline"),
    ):
        left_text = next(
            (section["rawSize"] for section in left["pe"]["r2r"]["sections"] if section["name"] == ".text"),
            0,
        )
        right_text = next(
            (section["rawSize"] for section in right["pe"]["r2r"]["sections"] if section["name"] == ".text"),
            0,
        )
        left_meta = left["map"]["nodeStatsSelected"].get("CopiedMetadataBlobNode")
        right_meta = right["map"]["nodeStatsSelected"].get("CopiedMetadataBlobNode")
        lines.append(
            f"- {label} content: exact method-node bytes {right['map']['exactMethodNodeBytes'] - left['map']['exactMethodNodeBytes']:+d} B,"
            f" canonical method-node bytes {right['map']['canonicalMethodNodeBytes'] - left['map']['canonicalMethodNodeBytes']:+d} B,"
            f" copied metadata blob {((right_meta or {}).get('length', 0) - (left_meta or {}).get('length', 0)):+d} B,"
            f" generic map entries {right['map']['genericMapEntries'] - left['map']['genericMapEntries']:+d},"
            f" .text raw {right_text - left_text:+d} B, R2R file {right['r2r']['bytes'] - left['r2r']['bytes']:+d} B."
        )
    lines.append("")
    canonical_totals = {
        item["variant"]["key"]: item["map"]["canonicalMethodNodeBytes"]
        for item in results["variants"]
    }
    if len(set(canonical_totals.values())) == 1:
        lines.append(
            f"Canonical shared generic method-node bytes are {next(iter(canonical_totals.values()))} B"
            " in all five maps, consistent with the constant Cell<T>/Relay<T> bodies."
        )
    val1_exact = val1["map"]["exactMethodNodeBytes"]
    val8_exact = val8["map"]["exactMethodNodeBytes"]
    guid = val8["map"]["declaredObservation"].get("System.Guid")
    guid_note = (
        " Guid has no exact code body in the map. The "
        f"{val8_exact - val1_exact} added exact method-node bytes span six additional specialized types"
        f" ({val8['map']['exactMethodNodeEntries'] - val1['map']['exactMethodNodeEntries']} method nodes);"
        " this is not a per-method-body cost."
        if guid is not None and not guid["observedAsExactCode"]
        else ""
    )
    lines.append(
        f"val1 exact method-node bytes are {val1_exact} B; val8 exact method-node bytes are {val8_exact} B."
        + guid_note
    )
    lines.append("")
    lines.append("Types marked metadata/fixup only above have no exact code body in the map.")
    lines.append("A large raw R2R step can be section alignment; use the map code, metadata and .text deltas.")
    lines.append("")
    lines.append("## Map and image observations")
    lines.append("")
    for item in results["variants"]:
        map_info = item["map"]
        r2r_header = item["pe"]["r2r"]["r2r"]
        text_section = next(
            (section for section in item["pe"]["r2r"]["sections"] if section["name"] == ".text"),
            None,
        )
        text_raw = text_section["rawSize"] if text_section else None
        metadata_size = item["pe"]["r2r"]["cor20"]["metadataSize"]
        labels = ", ".join(map_info["observedLabels"]) if map_info["observedLabels"] else "none"
        lines.append(
            f"- {item['variant']['key']}: MVID {item['pe']['r2r']['metadata']['mvid']}"
            f" (IL/R2R match={item['mvidMatch']}), R2R header sig={r2r_header['signature']}"
            f" v{r2r_header['major']}.{r2r_header['minor']}, flags={r2r_header['flags']:#x},"
            f" {r2r_header['sectionCount']} sections, .text={text_raw} B,"
            f" COR20 metadata={metadata_size} B, generic map entries {map_info['genericMapEntries']},"
            f" exact method nodes"
            f" {map_info['exactMethodNodeEntries']} / canonical"
            f" {map_info['canonicalMethodNodeEntries']}, observed labels {labels}."
        )
        statuses = []
        for name, observation in map_info["declaredObservation"].items():
            if observation["observedAsExactCode"]:
                status = "exact code"
            elif observation["observedAsCode"]:
                status = "shared code"
            elif observation["observedInMap"]:
                status = "metadata/fixup only"
            else:
                status = "not observed"
            statuses.append(f"{name}={status}")
        if statuses:
            lines.append("  Declared types: " + "; ".join(statuses) + ".")
    lines.append("")
    lines.append(
        "Method-node bytes count .text code nodes only (MethodWithGCInfo/Method/stubs);"
        " data-section fixup, dictionary and signature nodes are excluded."
        " MethodWithGCInfo includes its GC/unwind payload."
    )
    lines.append(
        "No exact Guid method body is map-level sharing/omission evidence only;"
        " it does not establish interpreter or fallback execution."
    )
    lines.append("")
    lines.append("## Limits")
    lines.append("")
    lines.append(
        "The baseline still contains the open Cell<T>/Ops.Relay<T> definitions and"
        " eight non-generic blocks; it is not a zero-cost image. Generic variants also"
        " add unavoidable call sites, closed type/method specifications, entrypoints and"
        " metadata. Crossgen2 may share canonical bodies, specialize value types, or omit"
        " bodies that do not appear in the actual map; the map evidence above is the"
        " only basis used here. A five-build sample on one SDK/toolchain does not establish"
        " iOS behavior, interpreter fallback, runtime execution mode, or production growth."
        " Gzip figures are distribution size only; decompress before loading."
    )
    lines.append("")
    return "\n".join(lines)



class ReplayError(RuntimeError):
    pass


def _load_json_file(path: Path, label: str):
    if not path.is_file():
        raise ReplayError(f"{label} is missing: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise ReplayError(f"{label} is malformed: {path}: {error}") from error


def _retained_log_path(input_root: Path, parent_output, recorded):
    recorded_path = Path(recorded)
    if parent_output:
        try:
            relative = recorded_path.relative_to(Path(parent_output))
        except ValueError:
            relative = None
        if relative is not None:
            candidate = input_root / relative
            if candidate.is_file():
                return candidate
    name = recorded_path.name
    candidates = [input_root / "logs" / name]
    candidates.extend(input_root.glob(f"variants/*/logs/{name}"))
    hits = [candidate for candidate in candidates if candidate.is_file()]
    if len(hits) != 1:
        raise ReplayError(f"cannot resolve retained log: {recorded}")
    return hits[0]


def _replay_source_verification(input_root: Path):
    pin_path = input_root / "source-pins.run.json"
    if not pin_path.is_file():
        pin_path = input_root / "source-pins.json"
    pins = _load_json_file(pin_path, "retained source pins")
    source_dir = input_root / "source"
    entries = []
    launch = None
    seen = {}
    for recorded, pin in pins.items():
        name = Path(recorded).name
        if name in seen and seen[name] != pin:
            raise ReplayError("source pins disagree for " + name)
        seen[name] = pin
        copy_path = source_dir / name
        actual = file_bytes(copy_path)
        ok = actual["bytes"] == pin.get("bytes") and actual["sha256"] == pin.get("sha256")
        if not ok:
            raise ReplayError(
                f"source fixture pin mismatch: {name}: expected {pin.get('sha256')} "
                f"bytes {pin.get('bytes')}, got {actual['sha256']} bytes {actual['bytes']}"
            )
        current_path = (
            Path(__file__).resolve()
            if name == Path(__file__).name
            else FIXTURE / name
        )
        current = file_bytes(current_path) if current_path.is_file() else None
        entry = {
            "name": name,
            "retainedPath": str(copy_path),
            "pinSha256": pin.get("sha256"),
            "pinBytes": pin.get("bytes"),
            "retainedSha256": actual["sha256"],
            "retainedBytes": actual["bytes"],
            "currentPath": str(current_path) if current_path.is_file() else None,
            "currentSha256": current["sha256"] if current else None,
            "currentBytes": current["bytes"] if current else None,
            "currentMatchesLaunch": bool(current and current["sha256"] == pin.get("sha256")),
        }
        entries.append(entry)
        if name == Path(__file__).name:
            launch = entry
    if launch is None:
        raise ReplayError("retained source pins have no harness entry")
    final_path = Path(__file__).resolve()
    final = file_bytes(final_path)
    previous_final = None
    previous_path = input_root / "source-pins.final.json"
    if previous_path.is_file():
        previous_pins = _load_json_file(previous_path, "previous final source pins")
        for recorded, pin in previous_pins.items():
            if Path(recorded).name == final_path.name:
                previous_final = {
                    "pinFile": str(previous_path),
                    "sha256": pin.get("sha256"),
                    "bytes": pin.get("bytes"),
                }
    return {
        "pinFile": str(pin_path),
        "entries": entries,
        "launch": launch,
        "final": {
            "path": str(final_path),
            "sha256": final["sha256"],
            "bytes": final["bytes"],
        },
        "previousFinal": previous_final,
        "currentMatchesLaunch": launch["currentMatchesLaunch"],
        "sourceImmutabilityClaim": False,
        "note": (
            "The launch pin identifies the historical harness and fixture bytes. "
            "The current checkout is not claimed to be immutable at launch."
        ),
    }


def _replay_command_verification(input_root: Path, parent_output):
    commands = _load_json_file(input_root / "commands.json", "retained commands")
    if not isinstance(commands, list):
        raise ReplayError("retained commands.json is not a list")
    builds = [record for record in commands if record.get("name") == "build"]
    crossgens = [record for record in commands if record.get("name") == "crossgen"]
    if len(builds) != 5 or len(crossgens) != 5:
        raise ReplayError(
            f"retained command counts are not five/five: {len(builds)} builds, {len(crossgens)} crossgens"
        )
    logs = []
    for record in commands:
        if record.get("exitCode") != 0:
            raise ReplayError(f"retained command did not exit 0: {record.get('name')}")
        for stream in ("stdout", "stderr"):
            recorded = record.get(stream)
            if not recorded:
                raise ReplayError(f"retained command has no {stream} path: {record.get('name')}")
            path = _retained_log_path(input_root, parent_output, recorded)
            actual = file_bytes(path)
            expected = record.get(stream + "Sha256")
            if expected is None or actual["sha256"] != expected:
                raise ReplayError(
                    f"log pin mismatch: {record.get('name')} {stream}: {path}"
                )
            logs.append(
                {
                    "command": record.get("name"),
                    "stream": stream,
                    "path": str(path),
                    "bytes": actual["bytes"],
                    "sha256": actual["sha256"],
                }
            )
    return {
        "builds": len(builds),
        "crossgens": len(crossgens),
        "records": len(commands),
        "logs": logs,
        "allExitZero": True,
    }


def _replay_pin_info(path: Path):
    if not path.is_file():
        raise ReplayError("retained file is missing: " + str(path))
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": sha256_bytes(data)}


def _replay_variant(input_root: Path, parent_variant, variant_meta):
    key = variant_meta["key"]
    if parent_variant.get("variant", {}).get("key") != key:
        raise ReplayError("parent variant key mismatch: " + key)
    variant_dir = input_root / "variants" / key
    il_path = variant_dir / "il" / ASSEMBLY
    r2r_path = variant_dir / "r2r" / ASSEMBLY
    map_csv = r2r_path.with_suffix(".map.csv")
    map_text = r2r_path.with_suffix(".map")
    response_path = variant_dir / "crossgen.rsp"
    il_pin = _replay_pin_info(il_path)
    r2r_pin = _replay_pin_info(r2r_path)
    map_csv_pin = _replay_pin_info(map_csv)
    map_text_pin = _replay_pin_info(map_text)
    response_pin = _replay_pin_info(response_path)

    def compare(actual, expected, label):
        if expected is None:
            raise ReplayError(f"parent has no pin for {label}")
        if actual["sha256"] != expected.get("sha256"):
            raise ReplayError(
                f"image/map pin mismatch for {label}: expected {expected.get('sha256')}, "
                f"got {actual['sha256']}"
            )
        if expected.get("bytes") is not None and actual["bytes"] != expected["bytes"]:
            raise ReplayError(
                f"image/map byte-size mismatch for {label}: expected {expected['bytes']}, "
                f"got {actual['bytes']}"
            )
        if (
            expected.get("gzipBytes") is not None
            and actual.get("gzipBytes") is not None
            and actual["gzipBytes"] != expected["gzipBytes"]
        ):
            raise ReplayError(f"gzip pin mismatch for {label}")

    compare(il_pin, parent_variant.get("il"), key + "/il")
    compare(r2r_pin, parent_variant.get("r2r"), key + "/r2r")
    map_parent = parent_variant.get("map", {})
    compare(
        map_csv_pin,
        {"bytes": map_parent.get("csvBytes"), "sha256": map_parent.get("csvSha256")},
        key + "/map.csv",
    )
    compare(
        map_text_pin,
        {"bytes": map_parent.get("textBytes"), "sha256": map_parent.get("textSha256")},
        key + "/map",
    )
    rsp_parent = parent_variant.get("crossgenRsp", {})
    compare(
        response_pin,
        {"bytes": rsp_parent.get("bytes"), "sha256": rsp_parent.get("sha256")},
        key + "/crossgen.rsp",
    )

    il_pe = parse_pe(il_path)
    r2r_pe = parse_pe(r2r_path)
    if not r2r_pe.get("r2r") or not r2r_pe["r2r"].get("signatureOk"):
        raise ReplayError("R2R header is missing or invalid for " + key)
    if not il_pe.get("metadata") or not r2r_pe.get("metadata"):
        raise ReplayError("metadata/MVID is missing for " + key)
    il_mvid = il_pe["metadata"]["mvid"]
    r2r_mvid = r2r_pe["metadata"]["mvid"]
    if il_mvid != r2r_mvid:
        raise ReplayError(f"IL/R2R MVID differ for {key}: {il_mvid} vs {r2r_mvid}")
    parent_pe = parent_variant.get("pe", {})
    parent_il_mvid = (parent_pe.get("il") or {}).get("metadata", {}).get("mvid")
    parent_r2r_mvid = (parent_pe.get("r2r") or {}).get("metadata", {}).get("mvid")
    if parent_il_mvid != il_mvid or parent_r2r_mvid != r2r_mvid:
        raise ReplayError(f"retained MVID pin mismatch for {key}")
    parent_header = (parent_pe.get("r2r") or {}).get("r2r") or {}
    header = r2r_pe["r2r"]
    for field in ("signature", "major", "minor", "sectionCount"):
        if parent_header.get(field) != header.get(field):
            raise ReplayError(f"retained R2R header mismatch for {key}: {field}")
    map_info = parse_map(map_csv, map_text, variant_meta["instantiations"])
    il = file_bytes(il_path)
    r2r = file_bytes(r2r_path)
    for label, actual, expected in (
        ("il", il, parent_variant.get("il")),
        ("r2r", r2r, parent_variant.get("r2r")),
    ):
        if expected is not None and expected.get("gzipBytes") is not None:
            if actual["gzipBytes"] != expected["gzipBytes"]:
                raise ReplayError(f"gzip pin mismatch for {key}/{label}")
    result = {
        "variant": variant_meta,
        "il": il,
        "r2r": r2r,
        "sidecars": [
            {
                "name": item.name,
                "bytes": item.stat().st_size,
                "sha256": sha256_file(item),
            }
            for item in sorted((variant_dir / "il").iterdir(), key=lambda item: item.name.lower())
            if item.suffix in (".dll", ".json")
        ],
        "map": {
            "csvPath": str(map_csv),
            "csvBytes": map_csv_pin["bytes"],
            "csvSha256": map_csv_pin["sha256"],
            "textPath": str(map_text),
            "textBytes": map_text_pin["bytes"],
            "textSha256": map_text_pin["sha256"],
        },
        "pe": {"il": il_pe, "r2r": r2r_pe},
        "mvidMatch": True,
        "crossgenRsp": {
            "path": str(response_path),
            "bytes": response_pin["bytes"],
            "sha256": response_pin["sha256"],
        },
    }
    result["map"].update(map_info)
    verification = {
        "key": key,
        "il": {"sha256": il["sha256"], "bytes": il["bytes"], "gzipBytes": il["gzipBytes"]},
        "r2r": {"sha256": r2r["sha256"], "bytes": r2r["bytes"], "gzipBytes": r2r["gzipBytes"]},
        "mapCsv": {"sha256": map_csv_pin["sha256"], "bytes": map_csv_pin["bytes"]},
        "mapText": {"sha256": map_text_pin["sha256"], "bytes": map_text_pin["bytes"]},
        "crossgenRsp": {"sha256": response_pin["sha256"], "bytes": response_pin["bytes"]},
        "mvid": {"il": il_mvid, "r2r": r2r_mvid, "match": True},
        "r2rHeader": {
            "signature": header["signature"],
            "major": header["major"],
            "minor": header["minor"],
            "sectionCount": header["sectionCount"],
        },
    }
    return result, verification


def _replay_core_metrics(item):
    map_info = item["map"]
    pe = item["pe"]
    header = pe["r2r"]["r2r"]
    text_section = next(
        (section for section in pe["r2r"]["sections"] if section["name"] == ".text"),
        None,
    )
    metadata_blob = map_info["nodeStatsSelected"].get("CopiedMetadataBlobNode")
    return {
        "ilBytes": item["il"]["bytes"],
        "ilGzipBytes": item["il"]["gzipBytes"],
        "ilSha256": item["il"]["sha256"],
        "r2rBytes": item["r2r"]["bytes"],
        "r2rGzipBytes": item["r2r"]["gzipBytes"],
        "r2rSha256": item["r2r"]["sha256"],
        "mvid": pe["r2r"]["metadata"]["mvid"],
        "r2rSignature": header["signature"],
        "r2rMajor": header["major"],
        "r2rMinor": header["minor"],
        "r2rSectionCount": header["sectionCount"],
        "genericMapEntries": map_info["genericMapEntries"],
        "genericMethodNodeEntries": map_info["genericMethodNodeEntries"],
        "exactMethodNodeEntries": map_info["exactMethodNodeEntries"],
        "canonicalMethodNodeEntries": map_info["canonicalMethodNodeEntries"],
        "exactMethodNodeBytes": map_info["exactMethodNodeBytes"],
        "canonicalMethodNodeBytes": map_info["canonicalMethodNodeBytes"],
        "genericCodeBytes": map_info["genericCodeBytes"],
        "allMethodNodeBytes": map_info["allMethodNodeBytes"],
        "metadataBlobBytes": metadata_blob["length"] if metadata_blob else 0,
        "cor20MetadataBytes": pe["r2r"]["cor20"]["metadataSize"],
        "textRawBytes": text_section["rawSize"] if text_section else 0,
    }


def _replay_comparisons(variant_results):
    baseline = next(item for item in variant_results if item["variant"]["key"] == "baseline")
    base_r2r = baseline["r2r"]["bytes"]
    base_il = baseline["il"]["bytes"]
    base_gzip = baseline["r2r"]["gzipBytes"]
    for item in variant_results:
        item["comparison"] = {
            "r2rDeltaVsBaseline": item["r2r"]["bytes"] - base_r2r,
            "r2rPercentVsBaseline": round(
                (item["r2r"]["bytes"] - base_r2r) * 100.0 / base_r2r, 6
            ),
            "ilDeltaVsBaseline": item["il"]["bytes"] - base_il,
            "ilPercentVsBaseline": round(
                (item["il"]["bytes"] - base_il) * 100.0 / base_il, 6
            ),
            "gzipR2rDeltaVsBaseline": item["r2r"]["gzipBytes"] - base_gzip,
        }
    by_key = {item["variant"]["key"]: item for item in variant_results}
    comparisons = []
    for low_key, high_key, label, divisor in (
        ("ref1", "ref8", "Reference types: ref8 minus ref1", 7),
        ("val1", "val8", "Value types: val8 minus val1", 7),
        ("baseline", "ref8", "ref8 minus non-generic baseline", 8),
        ("baseline", "val8", "val8 minus non-generic baseline", 8),
    ):
        low = by_key[low_key]
        high = by_key[high_key]
        comparisons.append(
            {
                "label": label,
                "from": low_key,
                "to": high_key,
                "additionalInstantiations": divisor,
                "ilPerInstantiation": round(
                    (high["il"]["bytes"] - low["il"]["bytes"]) / divisor, 3
                ),
                "gzipIlPerInstantiation": round(
                    (high["il"]["gzipBytes"] - low["il"]["gzipBytes"]) / divisor, 3
                ),
                "r2rPerInstantiation": round(
                    (high["r2r"]["bytes"] - low["r2r"]["bytes"]) / divisor, 3
                ),
                "gzipR2rPerInstantiation": round(
                    (high["r2r"]["gzipBytes"] - low["r2r"]["gzipBytes"]) / divisor, 3
                ),
                "genericCodeBytesPerInstantiation": round(
                    (high["map"]["genericCodeBytes"] - low["map"]["genericCodeBytes"])
                    / divisor,
                    3,
                ),
            }
        )
    return comparisons


def _replay_observations(variant_results):
    observations = []
    for item in variant_results:
        map_info = item["map"]
        observations.append(
            {
                "variant": item["variant"]["key"],
                "declaredObserved": map_info["declaredObservation"],
                "exactLabels": sorted(
                    {row["label"] for row in map_info["methodSymbols"] if not row["canonical"]}
                ),
                "canonicalLabels": sorted(
                    {row["label"] for row in map_info["methodSymbols"] if row["canonical"]}
                ),
            }
        )
    return observations


def _replay_pin_paths(input_root: Path, variants):
    paths = set()
    for name in (
        "results.json",
        "results.failure.json",
        "commands.json",
        "source-pins.json",
        "source-pins.run.json",
        "source-pins.final.json",
        "references.json",
        "crossgen-files.json",
    ):
        path = input_root / name
        if path.is_file():
            paths.add(path)
    source_dir = input_root / "source"
    if source_dir.is_dir():
        for path in source_dir.rglob("*"):
            if path.is_file():
                paths.add(path)
    for variant in variants:
        variant_dir = input_root / "variants" / variant["key"]
        for relative in (
            f"il/{ASSEMBLY}",
            f"r2r/{ASSEMBLY}",
            f"r2r/{Path(ASSEMBLY).stem}.map.csv",
            f"r2r/{Path(ASSEMBLY).stem}.map",
            f"r2r/{Path(ASSEMBLY).stem}.nodestats.csv",
            "crossgen.rsp",
            "logs/build.stdout.log",
            "logs/build.stderr.log",
            "logs/crossgen.stdout.log",
            "logs/crossgen.stderr.log",
        ):
            path = variant_dir / relative
            if path.is_file():
                paths.add(path)
    return sorted(paths)


def _replay_snapshot(input_root: Path, variants):
    files = {}
    for path in _replay_pin_paths(input_root, variants):
        relative = path.relative_to(input_root).as_posix()
        files[relative] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    manifest = sha256_bytes(
        json.dumps(files, indent=2, sort_keys=True).encode("utf-8")
    )
    return {"root": str(input_root), "files": files, "manifestSha256": manifest}


def _write_replay_csv(output: Path, variant_results):
    with (output / "results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "variant",
                "kind",
                "instantiations",
                "blocks",
                "il_bytes",
                "il_sha256",
                "il_gzip_bytes",
                "r2r_bytes",
                "r2r_sha256",
                "r2r_gzip_bytes",
                "r2r_over_il",
                "r2r_delta_vs_baseline",
                "r2r_percent_vs_baseline",
                "mvid",
                "mvid_match",
                "r2r_major",
                "r2r_minor",
                "r2r_sections",
                "text_raw_bytes",
                "cor20_metadata_bytes",
                "metadata_blob_bytes",
                "all_method_node_bytes",
                "generic_map_entries",
                "generic_method_nodes",
                "exact_method_nodes",
                "canonical_method_nodes",
                "exact_method_bytes",
                "canonical_method_bytes",
                "generic_method_bytes",
                "observed_labels",
                "declared_all_observed",
                "declared_all_code",
                "declared_all_exact_code",
            ]
        )
        for item in variant_results:
            map_info = item["map"]
            r2r_pe = item["pe"]["r2r"]
            text_section = next(
                (section for section in r2r_pe["sections"] if section["name"] == ".text"),
                None,
            )
            metadata_blob = map_info["nodeStatsSelected"].get("CopiedMetadataBlobNode")
            declared = map_info["declaredObservation"]
            writer.writerow(
                [
                    item["variant"]["key"],
                    item["variant"]["kind"],
                    ";".join(item["variant"]["instantiations"]),
                    item["variant"]["blocks"],
                    item["il"]["bytes"],
                    item["il"]["sha256"],
                    item["il"]["gzipBytes"],
                    item["r2r"]["bytes"],
                    item["r2r"]["sha256"],
                    item["r2r"]["gzipBytes"],
                    round(item["r2r"]["bytes"] / item["il"]["bytes"], 6),
                    item["comparison"]["r2rDeltaVsBaseline"],
                    item["comparison"]["r2rPercentVsBaseline"],
                    r2r_pe["metadata"]["mvid"],
                    item["mvidMatch"],
                    r2r_pe["r2r"]["major"],
                    r2r_pe["r2r"]["minor"],
                    r2r_pe["r2r"]["sectionCount"],
                    text_section["rawSize"] if text_section else None,
                    r2r_pe["cor20"]["metadataSize"],
                    metadata_blob["length"] if metadata_blob else None,
                    map_info["allMethodNodeBytes"],
                    map_info["genericMapEntries"],
                    map_info["genericMethodNodeEntries"],
                    map_info["exactMethodNodeEntries"],
                    map_info["canonicalMethodNodeEntries"],
                    map_info["exactMethodNodeBytes"],
                    map_info["canonicalMethodNodeBytes"],
                    map_info["genericCodeBytes"],
                    ";".join(map_info["observedLabels"]),
                    all(value["observedInMap"] for value in declared.values()) if declared else "",
                    all(value["observedAsCode"] for value in declared.values()) if declared else "",
                    all(value["observedAsExactCode"] for value in declared.values()) if declared else "",
                ]
            )


def _replay_main(args):
    try:
        if not args.replay_retained:
            raise ReplayError("--replay-retained is required")
        if not args.output:
            raise ReplayError("--output is required for offline replay")
        input_root = Path(args.replay_retained).expanduser().resolve()
        if not input_root.is_dir():
            raise ReplayError("retained root is not a directory: " + str(input_root))
        output = Path(args.output).expanduser()
        if not output.is_absolute():
            output = (Path.cwd() / output).resolve()
        if output.exists():
            raise ReplayError("output already exists; refusing to mutate it: " + str(output))
        if output.is_relative_to(input_root):
            raise ReplayError("output must be outside the retained input root")
        variants = _load_json_file(input_root / "source" / "variants.json", "retained variants")
        if len(variants) != 5:
            raise ReplayError("retained variants.json does not contain five variants")
        before = _replay_snapshot(input_root, variants)
        parent = _load_json_file(input_root / "results.json", "parent results")
        if parent.get("status") != "complete":
            raise ReplayError("parent results are not complete")
        failure = _load_json_file(input_root / "results.failure.json", "parent report failure")
        if failure.get("status") != "failed":
            raise ReplayError("parent report failure is not marked failed")
        parent_by_key = {
            item.get("variant", {}).get("key"): item for item in parent.get("variants", [])
        }
        expected_keys = {variant["key"] for variant in variants}
        if set(parent_by_key) != expected_keys:
            raise ReplayError("parent variants do not match retained variants.json")
        source_verification = _replay_source_verification(input_root)
        command_verification = _replay_command_verification(
            input_root, parent.get("output")
        )
        variant_results = []
        variant_verifications = []
        for variant in variants:
            result, verification = _replay_variant(
                input_root, parent_by_key[variant["key"]], variant
            )
            variant_results.append(result)
            variant_verifications.append(verification)
        comparisons = _replay_comparisons(variant_results)
        observations = _replay_observations(variant_results)
        retained_comparison = []
        recomputed_by_key = {
            item["variant"]["key"]: item for item in variant_results
        }
        for variant in variants:
            key = variant["key"]
            parent_metrics = _replay_core_metrics(parent_by_key[key])
            current_metrics = _replay_core_metrics(recomputed_by_key[key])
            differences = {
                field: {"retained": parent_metrics[field], "recomputed": current_metrics[field]}
                for field in parent_metrics
                if parent_metrics[field] != current_metrics[field]
            }
            retained_comparison.append(
                {
                    "variant": key,
                    "matches": not differences,
                    "differences": differences,
                }
            )
            if differences:
                raise ReplayError(
                    f"recomputed metrics differ from retained metrics for {key}: "
                    + ", ".join(sorted(differences))
                )
        after_verify = _replay_snapshot(input_root, variants)
        if after_verify["manifestSha256"] != before["manifestSha256"]:
            raise ReplayError("retained input changed during verification")

        parent_failure_path = input_root / "results.failure.json"
        harness = {
            "launch": source_verification["launch"],
            "final": source_verification["final"],
            "previousFinal": source_verification["previousFinal"],
            "currentMatchesLaunch": source_verification["currentMatchesLaunch"],
            "sourceImmutabilityClaim": False,
            "note": source_verification["note"],
        }
        exact_delta = (
            recomputed_by_key["val8"]["map"]["exactMethodNodeBytes"]
            - recomputed_by_key["val1"]["map"]["exactMethodNodeBytes"]
        )
        exact_nodes = (
            recomputed_by_key["val8"]["map"]["exactMethodNodeEntries"]
            - recomputed_by_key["val1"]["map"]["exactMethodNodeEntries"]
        )
        guid_observation = recomputed_by_key["val8"]["map"]["declaredObservation"].get(
            "System.Guid", {}
        )
        verification = {
            "parentResults": {
                "path": str(input_root / "results.json"),
                "sha256": sha256_file(input_root / "results.json"),
            },
            "parentFailure": {
                "path": str(parent_failure_path),
                "sha256": sha256_file(parent_failure_path),
                "status": failure.get("status"),
                "error": failure.get("error"),
            },
            "sourceFixtures": source_verification,
            "commands": command_verification,
            "variants": variant_verifications,
            "checks": {
                "sourceFixtures": len(source_verification["entries"]),
                "commandLogs": len(command_verification["logs"]),
                "variants": len(variant_verifications),
                "retainedMetrics": sum(
                    1 for item in retained_comparison if item["matches"]
                ),
            },
            "allPassed": True,
        }
        results = {
            "schema": 2,
            "mode": "offline-replay",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "status": "complete",
            "output": str(output),
            "parent": {
                "root": str(input_root),
                "resultsSha256": verification["parentResults"]["sha256"],
                "failureSha256": verification["parentFailure"]["sha256"],
                "failureStatus": failure.get("status"),
                "failureError": failure.get("error"),
            },
            "harness": harness,
            "verification": verification,
            "inputPins": {
                "before": {
                    "manifestSha256": before["manifestSha256"],
                    "fileCount": len(before["files"]),
                    "file": "input-pins.before.json",
                },
                "after": {
                    "manifestSha256": after_verify["manifestSha256"],
                    "fileCount": len(after_verify["files"]),
                    "file": "input-pins.after.json",
                },
                "unchanged": after_verify["manifestSha256"] == before["manifestSha256"],
            },
            "boundaries": {
                "offlineReplay": True,
                "managedBuilds": 0,
                "crossgenOutputs": 0,
                "subprocessCalls": 0,
                "executed": False,
                "productsGenerated": False,
                "target": "retained windows-x64 artifacts",
                "compression": "gzip level 9, mtime 0 (distribution size only)",
            },
            "correctedUnits": {
                "exactMethodNodeDeltaBytes": exact_delta,
                "exactMethodNodeDeltaEntries": exact_nodes,
                "additionalSpecializedTypes": 6,
                "note": (
                    f"{exact_delta} exact method-node bytes across six additional specialized "
                    f"types ({exact_nodes} method nodes); this is not a per-method-body cost."
                ),
                "guidExactBodyObserved": bool(
                    guid_observation.get("observedAsExactCode")
                ),
                "guidNote": (
                    "No exact Guid method body is map-level sharing/omission evidence only; "
                    "it does not establish interpreter or fallback execution."
                ),
                "methodNodeCaveat": (
                    "MethodWithGCInfo includes its GC/unwind payload; it is not a pure "
                    "instruction-byte count."
                ),
            },
            "variants": variant_results,
            "comparisons": comparisons,
            "observations": observations,
            "retainedComparison": retained_comparison,
            "limitations": [
                "Offline replay reads retained bytes only; it does not execute images or prove runtime mode.",
                "No managed builds or crossgen outputs are produced; subprocess and product paths are not accessed.",
                "The launch harness/fixture pins identify historical bytes; the current checkout is not claimed immutable at launch.",
                "The retained parent report failure is preserved and copied, not overwritten.",
                "Raw R2R files are 4 KiB-aligned; use map method-node and metadata deltas for content cost.",
                "Gzip sizes describe distribution only; decompress before loading.",
            ],
        }

        output.mkdir(parents=True, exist_ok=False)
        (output / "input-pins.before.json").write_text(
            json.dumps(before, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (output / "verification.json").write_text(
            json.dumps(verification, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        copy_map = (
            ("results.json", "parent-results.json"),
            ("results.failure.json", "parent-results.failure.json"),
            ("commands.json", "parent-commands.json"),
            ("references.json", "parent-references.json"),
            ("crossgen-files.json", "parent-crossgen-files.json"),
            ("source-pins.run.json", "parent-source-pins.run.json"),
        )
        for source_name, target_name in copy_map:
            source_path = input_root / source_name
            if source_path.is_file():
                shutil.copy2(source_path, output / target_name)
        final_pins = {}
        for path in (
            Path(__file__).resolve(),
            FIXTURE / "Cell.cs",
            FIXTURE / "Program.cs",
            FIXTURE / "VariantRoot.cs",
            FIXTURE / "TrustedGameGenericSize.csproj",
            FIXTURE / "variants.json",
            FIXTURE / "README.md",
        ):
            final_pins[str(path)] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        (output / "source-pins.final.json").write_text(
            json.dumps(final_pins, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (output / "replay-command.json").write_text(
            json.dumps(
                {
                    "argv": sys.argv,
                    "cwd": str(Path.cwd()),
                    "pythonVersion": sys.version,
                    "retainedRoot": str(input_root),
                    "output": str(output),
                    "subprocessUsed": False,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        _write_replay_csv(output, variant_results)
        after_write = _replay_snapshot(input_root, variants)
        input_unchanged = after_write["manifestSha256"] == before["manifestSha256"]
        results["inputPins"]["after"] = {
            "manifestSha256": after_write["manifestSha256"],
            "fileCount": len(after_write["files"]),
            "file": "input-pins.after.json",
        }
        results["inputPins"]["unchanged"] = input_unchanged
        if not input_unchanged:
            results["status"] = "failed"
            results["error"] = "retained input changed during replay"
        (output / "input-pins.after.json").write_text(
            json.dumps(after_write, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (output / "results.json").write_text(
            json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (output / "README.md").write_text(build_report(output, results), encoding="utf-8")
        if not input_unchanged:
            print("offline replay failed: retained input changed during replay", file=sys.stderr)
            return 1
        print(f"offline replay complete: {output}")
        print(f"retained root: {input_root}")
        print(f"input pins unchanged: {input_unchanged}")
        return 0
    except Exception as error:
        print("offline replay failed: " + str(error), file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", help="dotnet executable or SDK root")
    parser.add_argument("--runtime", help="dotnet/runtime checkout root")
    parser.add_argument("--crossgen2", help="pinned crossgen2 executable")
    parser.add_argument("--framework", help="directory of framework reference DLLs")
    parser.add_argument(
        "--replay-retained",
        help="offline-only replay from a retained experiment root; no builds, crossgen, dotnet, host or author execution",
    )
    parser.add_argument(
        "--output",
        help="fresh output directory; required for offline replay and outside the retained root",
    )
    parser.add_argument("--configuration", default="Release")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    if args.replay_retained:
        return _replay_main(args)

    missing = [
        flag
        for flag, value in (
            ("--sdk", args.sdk),
            ("--runtime", args.runtime),
            ("--crossgen2", args.crossgen2),
            ("--framework", args.framework),
        )
        if not value
    ]
    if missing:
        parser.error("the following arguments are required: " + ", ".join(missing))

    sdk = resolve_dotnet(Path(args.sdk).expanduser())
    runtime = Path(args.runtime).expanduser().resolve()
    crossgen2 = Path(args.crossgen2).expanduser().resolve()
    framework = Path(args.framework).expanduser().resolve()
    for label, path in (("runtime", runtime), ("crossgen2", crossgen2), ("framework", framework)):
        if not path.exists():
            parser.error(f"{label} path does not exist: {path}")
    if not crossgen2.is_file():
        parser.error(f"crossgen2 is not a file: {crossgen2}")
    if not framework.is_dir():
        parser.error(f"framework is not a directory: {framework}")
    if not (framework / "System.Private.CoreLib.dll").is_file():
        parser.error("framework directory has no System.Private.CoreLib.dll")

    if args.output:
        output = Path(args.output).expanduser()
        if not output.is_absolute():
            output = (Path.cwd() / output).resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = Path(tempfile.gettempdir()) / f"trusted-game-generic-size-{stamp}-{os.getpid()}"

    if output.exists():
        parser.error(f"output already exists; refusing to mutate it: {output}")

    variants = load_variants()
    output.mkdir(parents=True, exist_ok=False)
    logs = output / "logs"
    logs.mkdir()
    records = []
    started_at = datetime.now(timezone.utc)

    try:
        source_dir = output / "source"
        source_dir.mkdir()
        source_hashes = {}
        for source in (
            PROJECT,
            FIXTURE / "Cell.cs",
            FIXTURE / "Program.cs",
            FIXTURE / "VariantRoot.cs",
            FIXTURE / "variants.json",
            FIXTURE / "README.md",
            Path(__file__).resolve(),
        ):
            if not source.exists():
                raise RuntimeError("Missing fixture source: " + str(source))
            target = source_dir / source.name
            shutil.copy2(source, target)
            source_hashes[str(source)] = {
                "sha256": sha256_file(source),
                "bytes": source.stat().st_size,
            }
        (output / "source-pins.json").write_text(
            json.dumps(source_hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        def git(*arguments):
            return subprocess.run(
                ["git", "-C", str(runtime), *arguments],
                capture_output=True,
                text=True,
                errors="replace",
            )

        branch = git("rev-parse", "--abbrev-ref", "HEAD")
        commit = git("rev-parse", "HEAD")
        status = git("status", "--porcelain=v1")
        if branch.returncode != 0 or commit.returncode != 0:
            raise RuntimeError("Runtime git metadata failed: " + branch.stderr + commit.stderr)
        runtime_info = {
            "path": str(runtime),
            "branch": branch.stdout.strip(),
            "commit": commit.stdout.strip(),
            "status": status.stdout.splitlines(),
            "clean": status.stdout.strip() == "",
        }
        cmake = runtime / "artifacts/obj/coreclr/windows.x64.Checked/CMakeCache.txt"
        runtime_info["checkedCMakeCache"] = str(cmake)
        runtime_info["checkedBuild"] = (
            cmake.is_file()
            and "CMAKE_BUILD_TYPE:STRING=Checked" in cmake.read_text(errors="replace")
        )
        if not runtime_info["checkedBuild"]:
            raise RuntimeError("The selected runtime does not expose a Checked build marker")

        sdk_version = run_command(
            records, logs, "sdk-version", [sdk, "--version"], ROOT, args.timeout
        )
        if sdk_version["exitCode"] != 0:
            raise RuntimeError("SDK version command failed")
        crossgen_version = run_command(
            records, logs, "crossgen-version", [crossgen2, "--version"], ROOT, args.timeout
        )
        if crossgen_version["exitCode"] != 0:
            raise RuntimeError("crossgen2 version command failed")
        sdk_text = Path(sdk_version["stdout"]).read_text(encoding="utf-8").strip()
        crossgen_text = Path(crossgen_version["stdout"]).read_text(encoding="utf-8").strip()

        reference_paths = sorted(
            (path for path in framework.glob("*.dll") if path.name != ASSEMBLY),
            key=lambda path: path.name.lower(),
        )
        references = [
            {
                "name": path.name,
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in reference_paths
        ]
        corelib_ref = next(
            (item for item in references if item["name"].lower() == "system.private.corelib.dll"),
            None,
        )
        references_info = {
            "path": str(framework),
            "referenceCount": len(references),
            "systemPrivateCoreLib": corelib_ref,
            "references": references,
        }
        (output / "references.json").write_text(
            json.dumps(references_info, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        crossgen_dir_hashes = []
        for path in sorted(crossgen2.parent.iterdir(), key=lambda item: item.name.lower()):
            if path.is_file():
                crossgen_dir_hashes.append(
                    {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
                )
        (output / "crossgen-files.json").write_text(
            json.dumps(crossgen_dir_hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        inputs = {
            "sdk": {"path": str(sdk), "version": sdk_text, "sha256": sha256_file(sdk)},
            "runtime": runtime_info,
            "crossgen2": {
                "path": str(crossgen2),
                "version": crossgen_text,
                "sha256": sha256_file(crossgen2),
            },
            "framework": {
                "path": str(framework),
                "referenceCount": len(references),
                "systemPrivateCoreLibSha256": corelib_ref["sha256"] if corelib_ref else None,
            },
            "sourcePins": source_hashes,
        }

        variant_results = []
        for variant in variants:
            key = variant["key"]
            variant_dir = output / "variants" / key
            variant_logs = variant_dir / "logs"
            variant_logs.mkdir(parents=True)
            build_root = output / "build" / key

            build = run_command(
                records,
                variant_logs,
                "build",
                [
                    sdk,
                    "build",
                    str(PROJECT),
                    "-c",
                    args.configuration,
                    "--artifacts-path",
                    str(build_root),
                    "--nologo",
                    "--disable-build-servers",
                    f"-p:VariantKind={variant['define']}",
                    "-p:UseSharedCompilation=false",
                    "-p:Deterministic=true",
                ],
                ROOT,
                args.timeout,
            )
            if build["exitCode"] != 0:
                raise RuntimeError(
                    f"Build failed for {key}; see {build['stdout']} and {build['stderr']}"
                )

            built = find_built_assembly(build_root)
            il_dir = variant_dir / "il"
            il_dir.mkdir()
            il_path = il_dir / ASSEMBLY
            shutil.copy2(built, il_path)
            sidecars = []
            for sidecar in sorted(built.parent.iterdir(), key=lambda item: item.name.lower()):
                if sidecar.is_file() and sidecar.name.startswith("TrustedGameGenericSize."):
                    if sidecar.suffix in (".dll", ".json"):
                        target = il_dir / sidecar.name
                        shutil.copy2(sidecar, target)
                        sidecars.append(
                            {
                                "name": target.name,
                                "bytes": target.stat().st_size,
                                "sha256": sha256_file(target),
                            }
                        )

            r2r_dir = variant_dir / "r2r"
            r2r_dir.mkdir()
            r2r_path = r2r_dir / ASSEMBLY
            response_path = variant_dir / "crossgen.rsp"
            response_lines = [
                "--targetos:windows",
                "--targetarch:x64",
                "--optimize",
                f"--out:{r2r_path}",
                "--map",
                "--mapcsv",
            ]
            response_lines.extend(f"-r:{path}" for path in reference_paths)
            response_lines.append(str(il_path))
            response_path.write_text("\n".join(response_lines) + "\n", encoding="utf-8")
            crossgen = run_command(
                records,
                variant_logs,
                "crossgen",
                [crossgen2, "@" + str(response_path)],
                ROOT,
                args.timeout,
            )
            if crossgen["exitCode"] != 0:
                raise RuntimeError(
                    f"Crossgen failed for {key}; see {crossgen['stdout']} and {crossgen['stderr']}"
                )
            if not r2r_path.is_file():
                raise RuntimeError("crossgen2 did not produce " + str(r2r_path))
            map_csv = r2r_path.with_suffix(".map.csv")
            map_text = r2r_path.with_suffix(".map")
            if not map_csv.is_file() or not map_text.is_file():
                raise RuntimeError("crossgen2 did not produce both map files for " + key)

            il_pe = parse_pe(il_path)
            r2r_pe = parse_pe(r2r_path)
            if not r2r_pe["r2r"] or not r2r_pe["r2r"]["signatureOk"]:
                raise RuntimeError("R2R header is missing or invalid for " + key)
            if not il_pe["metadata"] or not r2r_pe["metadata"]:
                raise RuntimeError("Metadata/MVID missing for " + key)
            mvid_match = il_pe["metadata"]["mvid"] == r2r_pe["metadata"]["mvid"]
            if not mvid_match:
                raise RuntimeError("IL/R2R MVID differ for " + key)

            map_info = parse_map(map_csv, map_text, variant["instantiations"])
            variant_result = {
                "variant": variant,
                "il": file_bytes(il_path),
                "r2r": file_bytes(r2r_path),
                "sidecars": sidecars,
                "map": {
                    "csvPath": str(map_csv),
                    "csvBytes": map_csv.stat().st_size,
                    "csvSha256": sha256_file(map_csv),
                    "textPath": str(map_text),
                    "textBytes": map_text.stat().st_size,
                    "textSha256": sha256_file(map_text),
                },
                "pe": {"il": il_pe, "r2r": r2r_pe},
                "mvidMatch": mvid_match,
                "crossgenRsp": {
                    "path": str(response_path),
                    "sha256": sha256_file(response_path),
                },
            }
            variant_result["map"].update(map_info)
            variant_results.append(variant_result)

        baseline = next(item for item in variant_results if item["variant"]["key"] == "baseline")
        base_r2r = baseline["r2r"]["bytes"]
        base_il = baseline["il"]["bytes"]
        base_gzip = baseline["r2r"]["gzipBytes"]
        for item in variant_results:
            item["comparison"] = {
                "r2rDeltaVsBaseline": item["r2r"]["bytes"] - base_r2r,
                "r2rPercentVsBaseline": round(
                    (item["r2r"]["bytes"] - base_r2r) * 100.0 / base_r2r, 6
                ),
                "ilDeltaVsBaseline": item["il"]["bytes"] - base_il,
                "ilPercentVsBaseline": round(
                    (item["il"]["bytes"] - base_il) * 100.0 / base_il, 6
                ),
                "gzipR2rDeltaVsBaseline": item["r2r"]["gzipBytes"] - base_gzip,
            }

        by_key = {item["variant"]["key"]: item for item in variant_results}
        comparisons = []
        for low_key, high_key, label, divisor in (
            ("ref1", "ref8", "Reference types: ref8 minus ref1", 7),
            ("val1", "val8", "Value types: val8 minus val1", 7),
            ("baseline", "ref8", "ref8 minus non-generic baseline", 8),
            ("baseline", "val8", "val8 minus non-generic baseline", 8),
        ):
            low = by_key[low_key]
            high = by_key[high_key]
            comparisons.append(
                {
                    "label": label,
                    "from": low_key,
                    "to": high_key,
                    "additionalInstantiations": divisor,
                    "ilPerInstantiation": round(
                        (high["il"]["bytes"] - low["il"]["bytes"]) / divisor, 3
                    ),
                    "r2rPerInstantiation": round(
                        (high["r2r"]["bytes"] - low["r2r"]["bytes"]) / divisor, 3
                    ),
                    "gzipIlPerInstantiation": round(
                        (high["il"]["gzipBytes"] - low["il"]["gzipBytes"]) / divisor, 3
                    ),
                    "gzipR2rPerInstantiation": round(
                        (high["r2r"]["gzipBytes"] - low["r2r"]["gzipBytes"]) / divisor, 3
                    ),
                    "genericCodeBytesPerInstantiation": round(
                        (high["map"]["genericCodeBytes"] - low["map"]["genericCodeBytes"])
                        / divisor,
                        3,
                    ),
                }
            )

        observations = []
        for item in variant_results:
            map_info = item["map"]
            observations.append(
                {
                    "variant": item["variant"]["key"],
                    "declaredObserved": map_info["declaredObservation"],
                    "exactLabels": sorted(
                        {row["label"] for row in map_info["methodSymbols"] if not row["canonical"]}
                    ),
                    "canonicalLabels": sorted(
                        {row["label"] for row in map_info["methodSymbols"] if row["canonical"]}
                    ),
                }
            )

        results = {
            "schema": 1,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "startedAt": started_at.isoformat(),
            "status": "complete",
            "output": str(output),
            "boundaries": {
                "managedBuilds": 5,
                "crossgenOutputs": 5,
                "composite": False,
                "executed": False,
                "target": "windows-x64",
                "compression": "gzip level 9, mtime 0 (distribution size only)",
            },
            "inputs": inputs,
            "variants": variant_results,
            "comparisons": comparisons,
            "observations": observations,
            "limitations": [
                "One small template, five builds, one SDK/crossgen2 pair, one x64 Windows target.",
                "The baseline retains the open generic definitions and eight non-generic blocks.",
                "Generic variants add call sites, closed specifications, entrypoints and metadata.",
                "No image was executed; this does not establish runtime mode or interpreter fallback.",
                "Small-sample deltas are not production growth multipliers.",
                "Gzip sizes describe distribution only; images are decompressed before loading.",
            ],
        }

        (output / "results.json").write_text(
            json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (output / "commands.json").write_text(
            json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        with (output / "results.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(
                [
                    "variant",
                    "kind",
                    "instantiations",
                    "blocks",
                    "il_bytes",
                    "il_sha256",
                    "il_gzip_bytes",
                    "r2r_bytes",
                    "r2r_sha256",
                    "r2r_gzip_bytes",
                    "r2r_over_il",
                    "r2r_delta_vs_baseline",
                    "r2r_percent_vs_baseline",
                    "mvid",
                    "mvid_match",
                    "r2r_major",
                    "r2r_minor",
                    "r2r_sections",
                    "text_raw_bytes",
                    "cor20_metadata_bytes",
                    "metadata_blob_bytes",
                    "all_method_node_bytes",
                    "generic_map_entries",
                    "generic_method_nodes",
                    "exact_method_nodes",
                    "canonical_method_nodes",
                    "exact_method_bytes",
                    "canonical_method_bytes",
                    "generic_method_bytes",
                    "observed_labels",
                    "declared_all_observed",
                    "declared_all_code",
                    "declared_all_exact_code",
                ]
            )
            for item in variant_results:
                map_info = item["map"]
                r2r_pe = item["pe"]["r2r"]
                text_section = next(
                    (section for section in r2r_pe["sections"] if section["name"] == ".text"),
                    None,
                )
                metadata_blob = map_info["nodeStatsSelected"].get("CopiedMetadataBlobNode")
                writer.writerow(
                    [
                        item["variant"]["key"],
                        item["variant"]["kind"],
                        ";".join(item["variant"]["instantiations"]),
                        item["variant"]["blocks"],
                        item["il"]["bytes"],
                        item["il"]["sha256"],
                        item["il"]["gzipBytes"],
                        item["r2r"]["bytes"],
                        item["r2r"]["sha256"],
                        item["r2r"]["gzipBytes"],
                        round(item["r2r"]["bytes"] / item["il"]["bytes"], 6),
                        item["comparison"]["r2rDeltaVsBaseline"],
                        item["comparison"]["r2rPercentVsBaseline"],
                        r2r_pe["metadata"]["mvid"],
                        item["mvidMatch"],
                        r2r_pe["r2r"]["major"],
                        r2r_pe["r2r"]["minor"],
                        r2r_pe["r2r"]["sectionCount"],
                        text_section["rawSize"] if text_section else None,
                        r2r_pe["cor20"]["metadataSize"],
                        metadata_blob["length"] if metadata_blob else None,
                        map_info["allMethodNodeBytes"],
                        map_info["genericMapEntries"],
                        map_info["genericMethodNodeEntries"],
                        map_info["exactMethodNodeEntries"],
                        map_info["canonicalMethodNodeEntries"],
                        map_info["exactMethodNodeBytes"],
                        map_info["canonicalMethodNodeBytes"],
                        map_info["genericCodeBytes"],
                        ";".join(map_info["observedLabels"]),
                        all(
                            value["observedInMap"]
                            for value in map_info["declaredObservation"].values()
                        )
                        if map_info["declaredObservation"]
                        else "",
                        all(
                            value["observedAsCode"]
                            for value in map_info["declaredObservation"].values()
                        )
                        if map_info["declaredObservation"]
                        else "",
                        all(
                            value["observedAsExactCode"]
                            for value in map_info["declaredObservation"].values()
                        )
                        if map_info["declaredObservation"]
                        else "",
                    ]
                )

        (output / "README.md").write_text(build_report(output, results), encoding="utf-8")
        print(f"measurement complete: {output}")
        print(f"variants: {len(variant_results)}, builds: 5, crossgen outputs: 5")
        for item in variant_results:
            print(
                f"  {item['variant']['key']:8s} IL={item['il']['bytes']:7d}"
                f" R2R={item['r2r']['bytes']:7d}"
                f" exact/canonical={item['map']['exactMethodNodeEntries']}/"
                f"{item['map']['canonicalMethodNodeEntries']}"
            )
        return 0

    except Exception as error:
        failure = {
            "schema": 1,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "output": str(output),
            "error": str(error),
            "commands": records,
        }
        (output / "results.json").write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("measurement failed: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
