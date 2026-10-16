"""Offline structural inspection of a thin little-endian ARM64 Mach-O dylib.

Reports file metadata for a downloaded-update audit: SHA-256, CPU, file type,
LC_UUID, LC_BUILD_VERSION, and executable LC_SEGMENT_64 ranges. Static vmaddr
values are Mach-O file fields, not runtime program counters. This report does
not prove native execution. ReadyToRun method ranges and debugger captures are
out of scope.

Accepted input is only MH_MAGIC_64, CPU_TYPE_ARM64, MH_DYLIB. Fat, 32-bit,
big-endian, and other CPU or file types are rejected. LC_VERSION_MIN_* cannot
separate an iOS device from the simulator and is never used as a platform guess.

A non-empty section that is not zerofill must use the ordinary file-to-vm
layout: section addr equals segment vmaddr + section file offset - segment
file offset. SG_HIGHVM, and any segment flag outside the known non-mapping
set, is rejected. Those flags are not passed through the ordinary formula.
"""

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

MH_MAGIC_64 = 0xFEEDFACF
MH_CIGAM_64 = 0xCFFAEDFE
MH_MAGIC = 0xFEEDFACE
MH_CIGAM = 0xCEFAEDFE
FAT_MAGICS = {0xCAFEBABE, 0xBEBAFECA, 0xCAFEBABF, 0xBFBAFECA}

CPU_TYPE_ARM64 = 0x0100000C
CPU_TYPE_ARM64_32 = 0x0200000C
MH_DYLIB = 6

LC_SEGMENT_64 = 0x19
LC_UUID = 0x1B
LC_VERSION_MIN_MACOSX = 0x24
LC_VERSION_MIN_IPHONEOS = 0x25
LC_VERSION_MIN_TVOS = 0x2F
LC_VERSION_MIN_WATCHOS = 0x30
LC_BUILD_VERSION = 0x32

VM_PROT_EXECUTE = 0x4
SG_HIGHVM = 0x1
SG_FVMLIB = 0x2
SG_NORELOC = 0x4
SG_PROTECTED_VERSION_1 = 0x8
SG_READ_ONLY = 0x10
# These flags do not move file bytes within the static vm range.
ORDINARY_SEGMENT_FLAGS = SG_FVMLIB | SG_NORELOC | SG_PROTECTED_VERSION_1 | SG_READ_ONLY
S_ZEROFILL = 0x1
S_GB_ZEROFILL = 0xC
S_THREAD_LOCAL_ZEROFILL = 0x12
ZEROFILL_TYPES = {S_ZEROFILL, S_GB_ZEROFILL, S_THREAD_LOCAL_ZEROFILL}

# Apple PLATFORM_* values. Platform 2 is the device; platform 7 is the simulator.
PLATFORM_NAMES = {
    1: "macos",
    2: "ios",
    3: "tvos",
    4: "watchos",
    5: "bridgeos",
    6: "maccatalyst",
    7: "iossimulator",
    8: "tvossimulator",
    9: "watchossimulator",
    10: "driverkit",
    11: "visionos",
    12: "visionossimulator",
}
EXPECTED_PLATFORMS = ("ios", "iossimulator")
TOOL_NAMES = {
    1: "clang",
    2: "swift",
    3: "ld",
    4: "lld",
}
CPU_SUBTYPE_NAMES = {
    0: "arm64_all",
    1: "arm64_v8",
    2: "arm64e",
}
LEGACY_COMMANDS = {
    LC_VERSION_MIN_MACOSX: ("LC_VERSION_MIN_MACOSX", {1}),
    LC_VERSION_MIN_IPHONEOS: ("LC_VERSION_MIN_IPHONEOS", {2, 7}),
    LC_VERSION_MIN_TVOS: ("LC_VERSION_MIN_TVOS", {3, 8}),
    LC_VERSION_MIN_WATCHOS: ("LC_VERSION_MIN_WATCHOS", {4, 9}),
}
FILE_TYPE_NAMES = {
    1: "mh_object",
    2: "mh_execute",
    6: "mh_dylib",
    8: "mh_bundle",
}
ADDRESS_NOTE = (
    "Static Mach-O vmaddr values are file metadata, not runtime program "
    "counters, and this report does not prove native execution."
)
NAME_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.$")
UINT64_LIMIT = 1 << 64


class MachOInspectionError(ValueError):
    """The file is not a supported Mach-O dylib, or its metadata is inconsistent."""


def inspect_macho(path):
    """Return structural metadata for a thin little-endian ARM64 MH_DYLIB."""
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise MachOInspectionError("cannot read Mach-O file: " + str(exc)) from exc
    report = _parse(data)
    report["path"] = str(path)
    report["file_size"] = len(data)
    report["sha256"] = hashlib.sha256(data).hexdigest()
    return report


def require_platform(report, expected):
    """Reject an unknown or non-matching iOS device/simulator platform.

    A missing LC_BUILD_VERSION, an unknown platform number, or a legacy
    LC_VERSION_MIN_* command is not evidence for either platform.
    """
    if expected not in EXPECTED_PLATFORMS:
        raise MachOInspectionError("unknown expected platform: " + str(expected))
    build = report.get("build_version")
    name = None if build is None else build.get("platform_name")
    if not name:
        raise MachOInspectionError(
            "platform cannot be determined from LC_BUILD_VERSION; refusing to guess")
    if name != expected:
        raise MachOInspectionError(
            "platform mismatch: file has %s (%s), expected %s"
            % (name, build["platform"], expected))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ios_trusted_update_macho",
        description=(
            "Read structural metadata from a thin little-endian ARM64 Mach-O "
            "dylib. This does not prove native execution."))
    parser.add_argument("path", help="path to a thin ARM64 MH_DYLIB")
    parser.add_argument(
        "--expected-platform",
        choices=EXPECTED_PLATFORMS,
        help="require LC_BUILD_VERSION platform ios (2) or iossimulator (7)")
    args = parser.parse_args(argv)
    try:
        report = inspect_macho(args.path)
        if args.expected_platform is not None:
            require_platform(report, args.expected_platform)
    except MachOInspectionError as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 1
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _fail(message):
    raise MachOInspectionError(message)


def _parse(data):
    if len(data) < 4:
        _fail("truncated Mach-O header")
    magic = struct.unpack_from("<I", data, 0)[0]
    magic_be = struct.unpack_from(">I", data, 0)[0]
    if magic in FAT_MAGICS or magic_be in FAT_MAGICS:
        _fail("fat/universal Mach-O is not supported; only a thin little-endian ARM64 dylib is accepted")
    if magic in (MH_MAGIC, MH_CIGAM) or magic_be == MH_MAGIC:
        _fail("32-bit Mach-O is not supported; only a thin little-endian ARM64 dylib is accepted")
    if magic == MH_CIGAM_64:
        _fail("big-endian Mach-O is not supported; only a thin little-endian ARM64 dylib is accepted")
    if magic != MH_MAGIC_64:
        _fail("not a thin little-endian Mach-O")
    if len(data) < 32:
        _fail("truncated Mach-O header")

    cpu_type, cpu_subtype_raw, file_type, ncmds, sizeofcmds, flags = struct.unpack_from("<6I", data, 4)
    if cpu_type == CPU_TYPE_ARM64_32:
        _fail("CPU type ARM64_32 is not 64-bit ARM64")
    if cpu_type != CPU_TYPE_ARM64:
        _fail("CPU type %#x is not ARM64" % cpu_type)
    if file_type != MH_DYLIB:
        name = FILE_TYPE_NAMES.get(file_type, "unknown")
        _fail("file type %s (%s) is not MH_DYLIB" % (file_type, name))
    if 32 + sizeofcmds < 32 or 32 + sizeofcmds > len(data):
        _fail("truncated Mach-O load-command table")

    state = _commands(data, ncmds, sizeofcmds)
    _cross_check(state)
    subtype = cpu_subtype_raw & 0x00FFFFFF
    return {
        "kind": "thin-mach-o-dylib",
        "endian": "little",
        "magic": magic,
        "magic_hex": "0x%08x" % magic,
        "cpu_type": cpu_type,
        "cpu_type_hex": "0x%08x" % cpu_type,
        "cpu_type_name": "arm64",
        "cpu_subtype_raw": cpu_subtype_raw,
        "cpu_subtype": subtype,
        "cpu_subtype_name": CPU_SUBTYPE_NAMES.get(subtype),
        "cpu_subtype_feature_bits": (cpu_subtype_raw >> 24) & 0xFF,
        "file_type": file_type,
        "file_type_name": "mh_dylib",
        "ncmds": ncmds,
        "sizeofcmds": sizeofcmds,
        "flags": flags,
        "uuid": state["uuid_text"],
        "uuid_hex": state["uuid_hex"],
        "build_version": state["build_version"],
        "legacy_version_min": state["legacy"],
        "segment_count": len(state["segments"]),
        "executable_segments": [item for item in state["segments"] if item["initprot"] & VM_PROT_EXECUTE],
        "address_note": ADDRESS_NOTE,
        "proves_native_execution": False,
    }


def _commands(data, ncmds, sizeofcmds):
    cursor = 32
    limit = 32 + sizeofcmds
    state = {
        "uuid_text": None,
        "uuid_hex": None,
        "build_version": None,
        "legacy": None,
        "segments": [],
    }
    for _ in range(ncmds):
        if cursor + 8 > limit:
            _fail("truncated Mach-O load command header")
        command, cmdsize = struct.unpack_from("<II", data, cursor)
        if cmdsize < 8 or cmdsize % 8 != 0:
            _fail("inconsistent cmdsize %#x" % cmdsize)
        if cursor + cmdsize > limit:
            _fail("load command extends outside sizeofcmds")
        payload = data[cursor:cursor + cmdsize]
        if command == LC_UUID:
            _uuid(payload, state)
        elif command == LC_BUILD_VERSION:
            _build_version(payload, state)
        elif command in LEGACY_COMMANDS:
            _legacy(command, payload, state)
        elif command == LC_SEGMENT_64:
            state["segments"].append(_segment(payload, data))
        elif command == 0x1:
            _fail("32-bit LC_SEGMENT in a 64-bit image")
        cursor += cmdsize
    if cursor != limit:
        _fail("sizeofcmds does not match the load commands")
    return state


def _uuid(payload, state):
    if len(payload) != 24:
        _fail("inconsistent LC_UUID cmdsize")
    if state["uuid_hex"] is not None:
        _fail("duplicate LC_UUID")
    raw = payload[8:24]
    state["uuid_hex"] = raw.hex()
    state["uuid_text"] = "%s-%s-%s-%s-%s" % (
        raw[0:4].hex(), raw[4:6].hex(), raw[6:8].hex(), raw[8:10].hex(), raw[10:16].hex())


def _build_version(payload, state):
    if len(payload) < 24:
        _fail("truncated LC_BUILD_VERSION")
    if state["build_version"] is not None:
        _fail("duplicate LC_BUILD_VERSION")
    platform, minos, sdk, ntools = struct.unpack_from("<IIII", payload, 8)
    if len(payload) != 24 + ntools * 8:
        _fail("inconsistent LC_BUILD_VERSION cmdsize")
    tools = []
    for index in range(ntools):
        tool, version = struct.unpack_from("<II", payload, 24 + index * 8)
        tools.append({
            "tool": tool,
            "tool_name": TOOL_NAMES.get(tool),
            "version": _version(version),
        })
    state["build_version"] = {
        "command": "LC_BUILD_VERSION",
        "platform": platform,
        "platform_name": PLATFORM_NAMES.get(platform),
        "minos": _version(minos),
        "sdk": _version(sdk),
        "ntools": ntools,
        "tools": tools,
    }


def _legacy(command, payload, state):
    if len(payload) != 16:
        _fail("inconsistent legacy version cmdsize")
    if state["legacy"] is not None:
        _fail("duplicate legacy version command")
    version, sdk = struct.unpack_from("<II", payload, 8)
    name, _family = LEGACY_COMMANDS[command]
    state["legacy"] = {
        "command": name,
        "command_id": command,
        "version": _version(version),
        "sdk": _version(sdk),
        "platform_distinguishable": False,
    }


def _segment(payload, data):
    if len(payload) < 72:
        _fail("truncated LC_SEGMENT_64")
    name = _macho_name(payload[8:24], "segment name")
    vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", payload, 24)
    maxprot, initprot, nsects, flags = struct.unpack_from("<IIII", payload, 56)
    if 72 + 80 * nsects != len(payload):
        _fail("inconsistent LC_SEGMENT_64 cmdsize for %s" % name)
    _fit_range(vmaddr, vmsize, "segment %s vm" % name)
    _fit_range(fileoff, filesize, "segment %s file" % name)
    if fileoff + filesize > len(data):
        _fail("segment %s file range exceeds the file" % name)
    _require_ordinary_segment(flags, name)
    sections = []
    names = set()
    for index in range(nsects):
        section = _section(payload[72 + index * 80:72 + (index + 1) * 80], name, vmaddr, vmsize, fileoff, filesize, data)
        if section["section"] in names:
            _fail("duplicate section %s,%s" % (name, section["section"]))
        names.add(section["section"])
        sections.append(section)
    file_sections = [item for item in sections if not item["zerofill"]]
    _reject_overlaps(file_sections, "file_offset", "size", "section file ranges in %s" % name)
    _reject_overlaps(sections, "addr", "size", "section vm ranges in %s" % name)
    return {
        "name": name,
        "vmaddr": vmaddr,
        "vmaddr_hex": hex(vmaddr),
        "vmsize": vmsize,
        "vmsize_hex": hex(vmsize),
        "file_offset": fileoff,
        "file_size": filesize,
        "maxprot": maxprot,
        "maxprot_text": _prot_text(maxprot),
        "initprot": initprot,
        "initprot_text": _prot_text(initprot),
        "flags": flags,
        "address_kind": "static_vmaddr",
        "sections": sections,
    }


def _section(raw, segment, vmaddr, vmsize, fileoff, filesize, data):
    section = _macho_name(raw[0:16], "section name")
    recorded = _macho_name(raw[16:32], "section segment name")
    if recorded != segment:
        _fail("section %s records segment %s but is inside %s" % (section, recorded, segment))
    addr, size = struct.unpack_from("<QQ", raw, 32)
    offset, align, reloff, nreloc, flags = struct.unpack_from("<IIIII", raw, 48)
    _fit_range(addr, size, "section %s vm" % section)
    if size == 0:
        if addr < vmaddr or addr > vmaddr + vmsize:
            _fail("section %s vm address is outside its segment" % section)
    elif addr < vmaddr or addr + size > vmaddr + vmsize:
        _fail("section %s vm range is outside its segment" % section)
    section_type = flags & 0xFF
    zerofill = section_type in ZEROFILL_TYPES
    if zerofill:
        if offset != 0:
            _fail("zerofill section %s has a non-zero file offset" % section)
    elif size:
        if offset + size < offset or offset + size > len(data):
            _fail("section %s file range exceeds the file" % section)
        if offset < fileoff or offset + size > fileoff + filesize:
            _fail("section %s file range is outside its segment" % section)
        mapped = vmaddr + (offset - fileoff)
        if addr != mapped:
            _fail("section %s static address does not match its ordinary file mapping" % section)
    if nreloc:
        reloc_end = reloff + nreloc * 8
        if reloc_end < reloff or reloc_end > len(data):
            _fail("section %s relocation range exceeds the file" % section)
    return {
        "section": section,
        "segment": segment,
        "addr": addr,
        "addr_hex": hex(addr),
        "size": size,
        "file_offset": offset,
        "align": align,
        "reloff": reloff,
        "nreloc": nreloc,
        "flags": flags,
        "section_type": section_type,
        "zerofill": zerofill,
        "address_kind": "static_vmaddr",
    }


def _require_ordinary_segment(flags, name):
    if flags & SG_HIGHVM:
        _fail("SG_HIGHVM segment %s is not supported; its file bytes do not use "
              "the ordinary static address mapping" % name)
    unknown = flags & ~ORDINARY_SEGMENT_FLAGS
    if unknown:
        _fail("unsupported segment flags %#x on %s; only ordinary file-to-vm mapping is supported"
              % (unknown, name))


def _cross_check(state):
    names = [item["name"] for item in state["segments"]]
    if len(names) != len(set(names)):
        _fail("duplicate segment name")
    _reject_segment_overlaps(state["segments"], "vmaddr", "vmsize", "segment vm ranges")
    _reject_segment_overlaps(state["segments"], "file_offset", "file_size", "segment file ranges")
    build = state["build_version"]
    legacy = state["legacy"]
    if build is None or legacy is None:
        return
    _name, family = LEGACY_COMMANDS[legacy["command_id"]]
    if build["platform"] not in family:
        _fail("contradictory platform metadata between LC_BUILD_VERSION and " + legacy["command"])
    if build["minos"]["raw"] != legacy["version"]["raw"] or build["sdk"]["raw"] != legacy["sdk"]["raw"]:
        _fail("contradictory version metadata between LC_BUILD_VERSION and " + legacy["command"])


def _reject_segment_overlaps(items, start_key, size_key, label):
    ranges = [(item[start_key], item[start_key] + item[size_key]) for item in items if item[size_key]]
    _reject_range_list(ranges, label)


def _reject_overlaps(items, start_key, size_key, label):
    ranges = [(item[start_key], item[start_key] + item[size_key]) for item in items if item[size_key]]
    _reject_range_list(ranges, label)


def _reject_range_list(ranges, label):
    for index, (start, end) in enumerate(ranges):
        for other_start, other_end in ranges[index + 1:]:
            if start < other_end and other_start < end:
                _fail("overlapping " + label)


def _fit_range(start, size, label):
    if start >= UINT64_LIMIT or size >= UINT64_LIMIT or start + size > UINT64_LIMIT:
        _fail(label + " range overflows uint64")


def _version(raw):
    return {
        "major": (raw >> 16) & 0xFFFF,
        "minor": (raw >> 8) & 0xFF,
        "patch": raw & 0xFF,
        "raw": raw,
        "text": "%d.%d.%d" % ((raw >> 16) & 0xFFFF, (raw >> 8) & 0xFF, raw & 0xFF),
    }


def _macho_name(raw, what):
    head, separator, tail = raw.partition(b"\0")
    if separator and tail.strip(b"\0"):
        _fail("inconsistent NUL padding in " + what)
    try:
        name = head.decode("ascii")
    except UnicodeDecodeError:
        _fail("non-ASCII " + what)
    if not name or any(char not in NAME_CHARS for char in name):
        _fail("invalid " + what)
    return name


def _prot_text(value):
    return "%s%s%s" % (
        "r" if value & 1 else "-",
        "w" if value & 2 else "-",
        "x" if value & 4 else "-",
    )


if __name__ == "__main__":
    sys.exit(main())
