"""Synthetic structural tests for the thin ARM64 Mach-O dylib inspector.

Images in this file are hand-built containers, not compiler output. A passing
test shows that the checker accepts or rejects those bytes. It is not evidence
that native code executed.
"""

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ios_trusted_update_macho as inspector

TOOL = Path(__file__).resolve().parent / "ios_trusted_update_macho.py"
UUID = bytes.fromhex("00112233445566778899aabbccddeeff")
UUID_TEXT = "00112233-4455-6677-8899-aabbccddeeff"
MINOS = (15 << 16) | (3 << 8)
SDK = 18 << 16
CLANG = 16 << 16


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def name16(text):
    raw = text.encode("ascii")
    if not 1 <= len(raw) <= 16:
        raise AssertionError(text)
    return raw + b"\0" * (16 - len(raw))


def pack_header(ncmds, sizeofcmds, filetype=6, cputype=0x0100000C, subtype=0, flags=0, magic=0xFEEDFACF):
    return struct.pack("<8I", magic, cputype, subtype, filetype, ncmds, sizeofcmds, flags, 0)


def raw_image(ncmds, region, payload=b"", sizeofcmds=None, **kwargs):
    if sizeofcmds is None:
        sizeofcmds = len(region)
    return pack_header(ncmds, sizeofcmds, **kwargs) + region + payload


def section(sect, seg, addr, size, offset, align, flags, nreloc=0, reloff=0):
    return struct.pack(
        "<16s16sQQ8I", name16(sect), name16(seg), addr, size, offset, align, reloff, nreloc, flags, 0, 0, 0)


def segment(segname, vmaddr, vmsize, fileoff, filesize, maxprot, initprot, sections, flags=0):
    body = b"".join(sections)
    cmdsize = 72 + len(body)
    header = struct.pack(
        "<II16s4Q4I", 0x19, cmdsize, name16(segname), vmaddr, vmsize, fileoff, filesize,
        maxprot, initprot, len(sections), flags)
    return header + body


def uuid_cmd(raw=UUID):
    return struct.pack("<II", 0x1B, 24) + raw


def build_cmd(platform, minos=MINOS, sdk=SDK, tools=((1, CLANG),)):
    blob = struct.pack("<6I", 0x32, 24 + 8 * len(tools), platform, minos, sdk, len(tools))
    for tool, version in tools:
        blob += struct.pack("<II", tool, version)
    return blob


def legacy_cmd(command, version=MINOS, sdk=SDK):
    return struct.pack("<4I", command, 16, version, sdk)


TEXT_VMADDR = 0x100000000
TEXT_VMSIZE = 0x4000
DATA_VMADDR = TEXT_VMADDR + TEXT_VMSIZE
DATA_VMSIZE = 0x1000


def standard_commands(platform, text_off, data_off):
    text = section("__text", "__TEXT", TEXT_VMADDR + text_off, 16, text_off, 2, 0x80000400)
    data = section("__data", "__DATA", DATA_VMADDR, 16, data_off, 3, 0)
    bss = section("__bss", "__DATA", DATA_VMADDR + 16, 32, 0, 3, 1)
    return [
        segment("__TEXT", TEXT_VMADDR, TEXT_VMSIZE, 0, data_off, 5, 5, [text]),
        segment("__DATA", DATA_VMADDR, DATA_VMSIZE, data_off, 16, 7, 3, [data, bss]),
        uuid_cmd(),
        build_cmd(platform),
    ]


def standard_image(platform, **kwargs):
    command_length = len(b"".join(standard_commands(platform, 0, 0)))
    text_off = 32 + command_length
    data_off = text_off + 16
    commands = standard_commands(platform, text_off, data_off)
    blob = raw_image(len(commands), b"".join(commands), b"\xC0\x03\x5F\xD6" * 4 + b"\x11" * 16, **kwargs)
    if len(blob) != data_off + 16:
        raise AssertionError("synthetic layout changed")
    meta = {
        "text_off": text_off,
        "data_off": data_off,
        "text_section": 32 + 72,
        "data_segment": 32 + len(commands[0]),
    }
    meta["data_section"] = meta["data_segment"] + 72
    meta["bss_section"] = meta["data_section"] + 80
    meta["build"] = meta["data_segment"] + len(commands[1]) + len(commands[2])
    return blob, meta


class Suite:
    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="macho-synthetic-")
        self.directory = Path(self.temporary.name)
        self.count = 0

    def write(self, blob):
        self.count += 1
        path = self.directory / ("case-%02d.dylib" % self.count)
        path.write_bytes(blob)
        return path

    def load(self, blob):
        return inspector.inspect_macho(self.write(blob))

    def reject(self, blob, snippet):
        try:
            inspector.inspect_macho(self.write(blob))
        except inspector.MachOInspectionError as exc:
            if snippet not in str(exc):
                raise AssertionError("missing %r in %r" % (snippet, exc))
            return str(exc)
        raise AssertionError("expected rejection containing " + snippet)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOL), *args], capture_output=True, text=True, check=False)


S = Suite()


def version_is(value, major, minor, patch):
    check(value == {
        "major": major, "minor": minor, "patch": patch,
        "raw": (major << 16) | (minor << 8) | patch,
        "text": "%d.%d.%d" % (major, minor, patch),
    }, value)


def test_minimal_simulator_and_device():
    simulator = S.load(raw_image(1, build_cmd(7, 0, 0, ()), flags=0))
    device = S.load(raw_image(1, build_cmd(2), flags=4))
    check(simulator["build_version"]["platform"] == 7, simulator["build_version"])
    check(simulator["build_version"]["platform_name"] == "iossimulator", simulator)
    check(simulator["build_version"]["ntools"] == 0, simulator)
    check(simulator["uuid"] is None and simulator["executable_segments"] == [], simulator)
    check(simulator["legacy_version_min"] is None, simulator)
    check(simulator["cpu_type_name"] == "arm64" and simulator["file_type_name"] == "mh_dylib", simulator)
    check(simulator["proves_native_execution"] is False, simulator)
    check(device["build_version"]["platform"] == 2, device)
    check(device["build_version"]["platform_name"] == "ios", device)
    check(device["flags"] == 4, device)
    version_is(device["build_version"]["minos"], 15, 3, 0)
    version_is(device["build_version"]["sdk"], 18, 0, 0)
    check(device["build_version"]["tools"] == [{
        "tool": 1, "tool_name": "clang",
        "version": {"major": 16, "minor": 0, "patch": 0, "raw": CLANG, "text": "16.0.0"},
    }], device["build_version"])
    inspector.require_platform(simulator, "iossimulator")
    inspector.require_platform(device, "ios")
    for report, expected in ((simulator, "ios"), (device, "iossimulator")):
        try:
            inspector.require_platform(report, expected)
        except inspector.MachOInspectionError as exc:
            check("platform mismatch" in str(exc), exc)
        else:
            raise AssertionError("platform mismatch was accepted")


def test_executable_ranges_are_static_file_metadata():
    blob, meta = standard_image(7)
    report = S.load(blob)
    check(report["sha256"] == hashlib.sha256(blob).hexdigest(), report["sha256"])
    check(report["uuid"] == UUID_TEXT, report["uuid"])
    check(report["uuid_hex"] == UUID.hex(), report["uuid_hex"])
    check(report["segment_count"] == 2, report["segment_count"])
    check(len(report["executable_segments"]) == 1, report["executable_segments"])
    segment = report["executable_segments"][0]
    check(segment["name"] == "__TEXT", segment)
    check(segment["initprot"] == 5 and segment["initprot_text"] == "r-x", segment)
    check(segment["vmaddr"] == TEXT_VMADDR and segment["vmaddr_hex"] == hex(TEXT_VMADDR), segment)
    check(segment["address_kind"] == "static_vmaddr", segment)
    check(segment["file_offset"] == 0 and segment["file_size"] == meta["data_off"], segment)
    check([item["section"] for item in segment["sections"]] == ["__text"], segment)
    body = segment["sections"][0]
    mapped = segment["vmaddr"] + body["file_offset"] - segment["file_offset"]
    check(body["addr"] == mapped and body["addr_hex"] == hex(mapped), body)
    check(body["file_offset"] == meta["text_off"] and body["addr"] != body["file_offset"], body)
    check(body["zerofill"] is False and body["address_kind"] == "static_vmaddr", body)
    check("runtime_pc" not in json.dumps(report), "static address was described as a runtime PC")
    check(report["address_note"] == inspector.ADDRESS_NOTE, report["address_note"])
    check(report["proves_native_execution"] is False, report)


def test_arm64e_subtype_is_split_from_feature_bits():
    report = S.load(raw_image(1, build_cmd(7, 0, 0, ()), subtype=0x80000002))
    check(report["cpu_subtype_raw"] == 0x80000002, report)
    check(report["cpu_subtype"] == 2 and report["cpu_subtype_name"] == "arm64e", report)
    check(report["cpu_subtype_feature_bits"] == 0x80, report)
    unknown = S.load(raw_image(1, build_cmd(7, 0, 0, ()), subtype=9))
    check(unknown["cpu_subtype"] == 9 and unknown["cpu_subtype_name"] is None, unknown)


def test_legacy_version_cannot_guess_platform():
    legacy_only = S.load(raw_image(1, legacy_cmd(0x25)))
    check(legacy_only["build_version"] is None, legacy_only)
    check(legacy_only["legacy_version_min"]["command"] == "LC_VERSION_MIN_IPHONEOS", legacy_only)
    check(legacy_only["legacy_version_min"]["platform_distinguishable"] is False, legacy_only)
    version_is(legacy_only["legacy_version_min"]["version"], 15, 3, 0)
    try:
        inspector.require_platform(legacy_only, "ios")
    except inspector.MachOInspectionError as exc:
        check("refusing to guess" in str(exc), exc)
    else:
        raise AssertionError("legacy command was treated as iOS device")
    agreed = S.load(raw_image(2, build_cmd(7) + legacy_cmd(0x25)))
    check(agreed["build_version"]["platform_name"] == "iossimulator", agreed)
    check(agreed["legacy_version_min"]["platform_distinguishable"] is False, agreed)
    inspector.require_platform(agreed, "iossimulator")
    try:
        inspector.require_platform(agreed, "ios")
    except inspector.MachOInspectionError as exc:
        check("platform mismatch" in str(exc), exc)
    else:
        raise AssertionError("simulator image matched ios")


def test_container_and_identity_rejections():
    cases = [
        (b"\xCA\xFE\xBA\xBE" + b"\0" * 28, "fat/universal"),
        (b"\xBE\xBA\xFE\xCA" + b"\0" * 28, "fat/universal"),
        (b"\xCA\xFE\xBA\xBF" + b"\0" * 28, "fat/universal"),
        (struct.pack("<I", 0xFEEDFACE) + b"\0" * 28, "32-bit"),
        (struct.pack(">I", 0xFEEDFACF) + b"\0" * 28, "big-endian"),
        (b"\xCF\xFA\xED\xFE\x0C", "truncated Mach-O header"),
        (b"\0" * 32, "not a thin little-endian Mach-O"),
        (pack_header(0, 0, cputype=0x01000007), "not ARM64"),
        (pack_header(0, 0, cputype=0x0200000C), "ARM64_32"),
        (pack_header(0, 0, filetype=2), "not MH_DYLIB"),
        (pack_header(0, 0, filetype=8), "not MH_DYLIB"),
    ]
    for blob, snippet in cases:
        S.reject(blob, snippet)


def test_load_command_bounds():
    build = build_cmd(7, 0, 0, ())
    S.reject(raw_image(1, b"", sizeofcmds=24), "truncated Mach-O load-command table")
    S.reject(raw_image(1, b"\0" * 4, sizeofcmds=4), "truncated Mach-O load command header")
    short = bytearray(build)
    struct.pack_into("<I", short, 4, 12)
    S.reject(raw_image(1, bytes(short), sizeofcmds=16), "inconsistent cmdsize")
    oversized = bytearray(build)
    struct.pack_into("<I", oversized, 4, 32)
    S.reject(raw_image(1, bytes(oversized), sizeofcmds=24), "extends outside sizeofcmds")
    S.reject(raw_image(1, build + b"\0" * 8, sizeofcmds=32), "sizeofcmds does not match")
    S.reject(raw_image(2, build, sizeofcmds=24), "truncated Mach-O load command header")
    zero = struct.pack("<II", 0x32, 0)
    S.reject(raw_image(1, zero, sizeofcmds=8), "inconsistent cmdsize")
    S.reject(raw_image(1, struct.pack("<II", 1, 56) + b"\0" * 48), "32-bit LC_SEGMENT")


def test_duplicate_and_contradictory_metadata():
    S.reject(raw_image(2, uuid_cmd() + uuid_cmd()), "duplicate LC_UUID")
    S.reject(raw_image(2, build_cmd(7) + build_cmd(2)), "duplicate LC_BUILD_VERSION")
    bad_tools = bytearray(build_cmd(7, 0, 0, ()))
    struct.pack_into("<I", bad_tools, 20, 1)
    S.reject(raw_image(1, bytes(bad_tools)), "inconsistent LC_BUILD_VERSION cmdsize")
    S.reject(raw_image(2, build_cmd(7) + legacy_cmd(0x25, (12 << 16), SDK)), "contradictory version")
    S.reject(raw_image(2, build_cmd(7) + legacy_cmd(0x24)), "contradictory platform")
    S.reject(raw_image(2, legacy_cmd(0x25) + legacy_cmd(0x25)), "duplicate legacy version command")
    unknown = S.load(raw_image(1, build_cmd(99, 0, 0, ())))
    check(unknown["build_version"]["platform"] == 99, unknown)
    check(unknown["build_version"]["platform_name"] is None, unknown)
    try:
        inspector.require_platform(unknown, "ios")
    except inspector.MachOInspectionError as exc:
        check("refusing to guess" in str(exc), exc)
    else:
        raise AssertionError("unknown platform number was accepted")
    try:
        inspector.require_platform(unknown, "macos")
    except inspector.MachOInspectionError as exc:
        check("unknown expected platform" in str(exc), exc)
    else:
        raise AssertionError("unknown expected platform was accepted")


def test_segment_and_section_bounds():
    blob, meta = standard_image(2)
    too_large = bytearray(blob)
    struct.pack_into("<Q", too_large, meta["text_section"] + 40, 0x2000)
    S.reject(bytes(too_large), "file range exceeds the file")
    outside = bytearray(blob)
    struct.pack_into("<I", outside, meta["text_section"] + 48, meta["data_off"])
    S.reject(bytes(outside), "outside its segment")
    beyond_vm = bytearray(blob)
    struct.pack_into("<Q", beyond_vm, meta["text_section"] + 32, 0x5000)
    S.reject(bytes(beyond_vm), "vm range is outside its segment")
    bad_pad = bytearray(blob)
    bad_pad[meta["text_section"] + 16:meta["text_section"] + 32] = name16("__DATA")
    S.reject(bytes(bad_pad), "records segment")
    bad_zero = bytearray(blob)
    struct.pack_into("<I", bad_zero, meta["bss_section"] + 48, 4)
    S.reject(bytes(bad_zero), "non-zero file offset")
    S.reject(overlapping_segment_files(), "overlapping segment file ranges")
    data = bytearray(blob)
    struct.pack_into("<Q", data, meta["data_section"] + 40, 0x200)
    S.reject(bytes(data), "file range exceeds the file")
    wrapped = segment("__TEXT", (1 << 64) - 8, 16, 0, 0, 5, 5, [])
    S.reject(raw_image(1, wrapped), "overflows uint64")
    duplicated = segment("__TEXT", 0, 0x1000, 0, 0, 5, 5, []) + segment("__TEXT", 0x1000, 0x1000, 0, 0, 5, 5, [])
    S.reject(raw_image(2, duplicated), "duplicate segment name")
    short = struct.pack("<II16s4Q4I", 0x19, 72, name16("__TEXT"), 0, 0, 0, 0, 5, 5, 1, 0)
    S.reject(raw_image(1, short), "inconsistent LC_SEGMENT_64 cmdsize")
    first = section("__a", "__TEXT", 100, 32, 100, 0, 0)
    second = section("__b", "__TEXT", 116, 32, 116, 0, 0)
    shared = segment("__TEXT", 0, 0x1000, 0, 32 + 72 + 160, 5, 5, [first, second])
    S.reject(raw_image(1, shared), "overlapping section file ranges")
    low = section("__bss", "__DATA", 0x100, 32, 0, 0, 1)
    high = section("__common", "__DATA", 0x110, 32, 0, 0, 1)
    virtual = segment("__DATA", 0, 0x1000, 0, 0, 3, 3, [low, high])
    S.reject(raw_image(1, virtual), "overlapping section vm ranges")
    dirty = struct.pack("<II", 0x19, 72) + b"A\0B" + b"\0" * 13 + struct.pack("<4Q4I", 0, 0, 0, 0, 5, 5, 0, 0)
    S.reject(raw_image(1, dirty), "inconsistent NUL padding")
    binary = struct.pack("<II", 0x19, 72) + b"\xff" + b"\0" * 15 + struct.pack("<4Q4I", 0, 0, 0, 0, 5, 5, 0, 0)
    S.reject(raw_image(1, binary), "non-ASCII")
    relocated = bytearray(blob)
    struct.pack_into("<II", relocated, meta["text_section"] + 56, 0xFFFFFFF0, 4)
    S.reject(bytes(relocated), "relocation range exceeds the file")


def overlapping_segment_files():
    text = section("__text", "__TEXT", 0, 16, 0, 2, 0x80000400)
    data = section("__data", "__DATA", 0, 16, 0, 3, 0)
    measured = [
        segment("__TEXT", TEXT_VMADDR, TEXT_VMSIZE, 0, 0, 5, 5, [text]),
        segment("__DATA", DATA_VMADDR, DATA_VMSIZE, 0, 0, 3, 3, [data]),
    ]
    payload_at = 32 + len(b"".join(measured))
    text = section("__text", "__TEXT", TEXT_VMADDR + payload_at, 16, payload_at, 2, 0x80000400)
    data = section("__data", "__DATA", DATA_VMADDR, 16, payload_at + 8, 3, 0)
    commands = [
        segment("__TEXT", TEXT_VMADDR, TEXT_VMSIZE, 0, payload_at + 24, 5, 5, [text]),
        segment("__DATA", DATA_VMADDR, DATA_VMSIZE, payload_at + 8, 24, 3, 3, [data]),
    ]
    return raw_image(2, b"".join(commands), b"\x22" * 32)


def test_ordinary_file_mapping():
    blob, meta = standard_image(7)
    report = S.load(blob)
    body = report["executable_segments"][0]["sections"][0]
    text_segment = report["executable_segments"][0]
    check(body["addr"] == text_segment["vmaddr"] + body["file_offset"] - text_segment["file_offset"], body)
    shifted_addr = bytearray(blob)
    struct.pack_into("<Q", shifted_addr, meta["text_section"] + 32, body["addr"] + 32)
    addr_error = S.reject(bytes(shifted_addr), "ordinary file mapping")
    check("outside" not in addr_error and "exceeds" not in addr_error, addr_error)
    shifted_offset = bytearray(blob)
    struct.pack_into("<I", shifted_offset, meta["text_section"] + 48, meta["text_off"] - 16)
    offset_error = S.reject(bytes(shifted_offset), "ordinary file mapping")
    check("outside" not in offset_error and "exceeds" not in offset_error, offset_error)
    ordinary = section("__text", "__TEXT", 0, 16, 0, 2, 0x80000400)
    readonly = segment("__TEXT", 0, 0x1000, 0, 16, 5, 5, [ordinary], flags=0x10)
    accepted = S.load(raw_image(1, readonly))
    check(accepted["executable_segments"][0]["flags"] == 0x10, accepted)
    high = segment("__TEXT", 0, 0x1000, 0, 16, 5, 5, [ordinary], flags=0x1)
    S.reject(raw_image(1, high), "SG_HIGHVM")
    unknown = segment("__TEXT", 0, 0x1000, 0, 0, 5, 5, [], flags=0x20)
    S.reject(raw_image(1, unknown), "unsupported segment flags")


def test_command_line():
    device, _meta = standard_image(2)
    simulator, _meta = standard_image(7)
    device_path = S.write(device)
    simulator_path = S.write(simulator)
    accepted = S.cli(str(device_path), "--expected-platform", "ios")
    check(accepted.returncode == 0, accepted.stderr)
    parsed = json.loads(accepted.stdout)
    check(parsed["build_version"]["platform_name"] == "ios", parsed)
    check(parsed["sha256"] == hashlib.sha256(device).hexdigest(), parsed["sha256"])
    check(parsed["proves_native_execution"] is False, parsed)
    rejected = S.cli(str(simulator_path), "--expected-platform", "ios")
    check(rejected.returncode == 1 and "platform mismatch" in rejected.stderr, rejected.stderr)
    legacy = S.write(raw_image(1, legacy_cmd(0x25)))
    guessed = S.cli(str(legacy), "--expected-platform", "iossimulator")
    check(guessed.returncode == 1 and "refusing to guess" in guessed.stderr, guessed.stderr)
    unknown = S.cli(str(device_path), "--expected-platform", "macos")
    check(unknown.returncode != 0, unknown.stderr)
    missing = S.cli(str(S.directory / "missing.dylib"))
    check(missing.returncode == 1 and "cannot read Mach-O file" in missing.stderr, missing.stderr)


def main():
    print("synthetic structural tests only; not native-execution evidence")
    print("python", sys.version.split()[0])
    tests = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
        except Exception as exc:
            failed += 1
            print("FAIL", test_fn.__name__ + ":", exc)
        else:
            print("PASS", test_fn.__name__)
    print("%d passed, %d failed" % (len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
