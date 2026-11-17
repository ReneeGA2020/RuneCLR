#!/usr/bin/env python3
"""Independent, fail-closed verifier for grouped method-witness evidence.

Consumes a capture manifest (runeclr-grouped-method-witness/1), the raw CDB transcript,
debugger-events.jsonl, host.jsonl and the pinned staged images/runtime files.

It never writes to host.jsonl and never sets a host "verified" flag. It produces its own
report (runeclr-grouped-witness-verify/1) and exits 0 only when every check passed.

Standard library only. Source contracts (see REVIEW-INTERP-FRAME-WITNESS.md):
  * InterpExecMethod(InterpreterFrame*, InterpMethodContextFrame*, InterpThreadContext*, ExceptionClauseArgs*)
    -- vm/interpexec.cpp:1750; @r9 == 0 is a first method entry, non-zero is an EH-clause resume.
  * frame->startIp->Method->methodHnd is the MethodDesc (vm/interpexec.cpp:1769,
    interpreter/inc/interpretershared.h:40); the MethodDesc holds m_interpreterCode
    (vm/method.hpp:1996-2008, poison == 1).
  * Interpreted-to-interpreted calls loop in the same InterpExecMethod (vm/interpexec.cpp:3909-3910,
    4021-4022); JIT -> interpreter enters prestub.cpp:2176-2190/2055-2082 with r9 == 0.
  * Framework arm needs a real JIT native body PC (MethodDesc::GetNativeCode, vm/method.cpp:1268-1292)
    plus DAC identity (DacpMethodDescData, src/coreclr/inc/dacprivate.h:557-570).
  * At the InterpExecMethod breakpoint the reported pc is the actual native @rip inside the executor,
    never an IR offset; the IR body begins at startIp + the measured bytecode header size.
  * Framework evidence is a contiguous observed-instruction window starting at the DAC NativeCodeAddr;
    it is not a whole-method size.
  * A stdin-pipe CDB prints the previous prompt in front of actual output ("0:000> SENTENCE"), so a
    prompt is stripped before a line is classified; only a bare hit line counts as runtime evidence.
  * Transcript offsets are UTF-8 BYTE offsets into the raw file: spans are sliced as bytes and then
    decoded, and an unsupported encoding fails closed.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST_SCHEMA = "runeclr-grouped-method-witness/1"
CHECKPOINT_SCHEMA = "runeclr-grouped-checkpoint/1"
HOST_SCHEMA = "runeclr-grouped-witness/1"
REPORT_SCHEMA = "runeclr-grouped-witness-verify/1"

PHASES = ("before-framework", "before-author", "before-callback", "before-cleanup")
TARGETS = ("Initialize", "Touch", "Run", "OnFrameworkEvent")
TARGET_ROLE = {"Initialize": "framework", "Touch": "framework", "Run": "author", "OnFrameworkEvent": "author"}
# Convention: Touch is called from interpreted Run, so it is observed after the before-author checkpoint.
TARGET_PHASE = {"Initialize": "before-framework", "Run": "before-author",
                "OnFrameworkEvent": "before-callback", "Touch": "before-author"}

EXT_HASHES = (("host_records_sha256", "host_records"),
              ("transcript_sha256", "transcript"),
              ("debugger_events_sha256", "debugger_events"))
EXT_CHECKPOINT_TIME = "checkpoint_created_utc"
EXT_IP2MD = "ip2md_md"
EXT_DAC_MVID = "dac_module_mvid"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(str(path) + " is not a JSON object")
    return value


def load_jsonl(path: Path) -> list:
    records = []
    with path.open("r", encoding="utf-8") as fh:
        for number, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(str(path) + ":" + str(number) + " is not a JSON object")
            records.append(value)
    return records


def guid_from_le(data: bytes) -> str:
    if len(data) < 16:
        raise ImageError("GUID slice is shorter than 16 bytes")
    d1, d2, d3 = struct.unpack_from("<IHH", data, 0)
    tail = data[8:16]
    return "%08x-%04x-%04x-%02x%02x-%s" % (d1, d2, d3, tail[0], tail[1], tail[2:].hex())


class ImageError(RuntimeError):
    pass


def _read_u16(data: bytes, position: int, what: str) -> int:
    if position < 0 or position + 2 > len(data):
        raise ImageError("%s is truncated at offset %d" % (what, position))
    return struct.unpack_from("<H", data, position)[0]


def _read_u32(data: bytes, position: int, what: str) -> int:
    if position < 0 or position + 4 > len(data):
        raise ImageError("%s is truncated at offset %d" % (what, position))
    return struct.unpack_from("<I", data, position)[0]


def _rva_to_offset(sections, rva: int) -> int:
    for virtual_address, virtual_size, raw_pointer, raw_size in sections:
        if virtual_address <= rva < virtual_address + max(virtual_size, raw_size):
            return raw_pointer + (rva - virtual_address)
    raise ImageError("RVA 0x%X is not mapped by any section" % rva)


def _heap_size(heap_sizes: int, bit: int) -> int:
    return 4 if heap_sizes & bit else 2


def _table_size(rows, table: int) -> int:
    return 4 if rows.get(table, 0) >= 0x10000 else 2


def _coded_size(rows, targets, bits: int) -> int:
    largest = max([rows.get(target, 0) for target in targets] + [0])
    return 4 if largest >= (1 << (16 - bits)) else 2


def _index(block: bytes, position: int, size: int, what: str) -> int:
    if position < 0 or position + size > len(block):
        raise ImageError("%s is truncated at table-stream offset %d" % (what, position))
    return struct.unpack_from("<H", block, position)[0] if size == 2 else struct.unpack_from("<I", block, position)[0]


def parse_managed_image(path: Path) -> dict:
    """Return {mvid, module, methods{token: {name, type}}} from a managed PE image.

    The #~/#- table stream stores one 4-byte row count for every table present in the Valid
    bitmask (packed), not 64 dense entries. Row sizes are derived from the present counts and
    the heap-size flags, and every index is bounds-checked before use.
    """
    data = path.read_bytes()
    if len(data) < 0x40:
        raise ImageError("file is shorter than a DOS header")
    if data[:2] != b"MZ":
        raise ImageError("missing MZ header")
    pe = _read_u32(data, 0x3C, "e_lfanew")
    if pe < 0x40 or pe + 24 > len(data) or data[pe:pe + 4] != b"PE\x00\x00":
        raise ImageError("missing or out-of-bounds PE signature")
    section_count = _read_u16(data, pe + 6, "NumberOfSections")
    optional_size = _read_u16(data, pe + 20, "SizeOfOptionalHeader")
    optional = pe + 24
    if optional + optional_size > len(data):
        raise ImageError("optional header is out of bounds")
    magic = _read_u16(data, optional, "optional header magic")
    if magic not in (0x10B, 0x20B):
        raise ImageError("unsupported optional header magic 0x%X" % magic)
    directories = optional + (112 if magic == 0x20B else 96)
    if directories + 15 * 8 > optional + optional_size:
        raise ImageError("data directories are truncated")
    cli_rva, cli_size = struct.unpack_from("<II", data, directories + 14 * 8)
    if cli_rva == 0 or cli_size < 72:
        raise ImageError("no usable CLI header directory (not a managed image)")
    section_table = optional + optional_size
    if section_table + section_count * 40 > len(data):
        raise ImageError("section table is out of bounds")
    sections = []
    for index in range(section_count):
        at = section_table + index * 40
        virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from("<IIII", data, at + 8)
        if raw_size and raw_pointer + raw_size > len(data):
            raise ImageError("section %d raw data is out of bounds" % index)
        sections.append((virtual_address, virtual_size, raw_pointer, raw_size))
    cli = _rva_to_offset(sections, cli_rva)
    if cli + 72 > len(data):
        raise ImageError("CLI header is truncated")
    md_rva, md_size = struct.unpack_from("<II", data, cli + 8)
    if md_rva == 0 or md_size < 20:
        raise ImageError("no metadata directory")
    root = data[_rva_to_offset(sections, md_rva):]
    root = root[:md_size]
    if len(root) < 20 or root[:4] != b"BSJB":
        raise ImageError("missing or truncated BSJB metadata signature")
    version_length = _read_u32(root, 12, "metadata version length")
    position = 16 + version_length
    if position + 4 > len(root):
        raise ImageError("metadata version string is out of bounds")
    position += (-position) % 4
    stream_count = _read_u16(root, position + 2, "stream count")
    position += 4
    streams = {}
    for _ in range(stream_count):
        offset = _read_u32(root, position, "stream offset")
        size = _read_u32(root, position + 4, "stream size")
        position += 8
        end = root.find(b"\x00", position)
        if end < 0:
            raise ImageError("stream name is not terminated")
        name = root[position:end].decode("ascii", "replace")
        position = end + 1
        position += (-position) % 4
        if offset > len(root) or size > len(root) - offset:
            raise ImageError("stream %s is out of bounds" % name)
        streams[name] = (offset, size)
    table_name = "#~" if "#~" in streams else ("#-" if "#-" in streams else None)
    if table_name is None:
        raise ImageError("missing #~/#- table stream")
    for required in ("#Strings", "#GUID"):
        if required not in streams:
            raise ImageError("missing %s stream" % required)
    tables = root[streams[table_name][0]:streams[table_name][0] + streams[table_name][1]]
    strings = root[streams["#Strings"][0]:streams["#Strings"][0] + streams["#Strings"][1]]
    guids = root[streams["#GUID"][0]:streams["#GUID"][0] + streams["#GUID"][1]]
    if len(tables) < 24:
        raise ImageError("table stream is shorter than its 24-byte header")
    _major, _minor, heap_sizes, _reserved = struct.unpack_from("<BBBB", tables, 4)
    valid = struct.unpack_from("<Q", tables, 8)[0]
    position = 24
    present = [table for table in range(64) if valid & (1 << table)]
    if not present:
        raise ImageError("the table stream declares no tables")
    if position + 4 * len(present) > len(tables):
        raise ImageError("table stream is truncated inside the row-count array")
    rows = {}
    for table in present:
        rows[table] = struct.unpack_from("<I", tables, position)[0]
        position += 4
    string_size = _heap_size(heap_sizes, 1)
    guid_size = _heap_size(heap_sizes, 2)
    blob_size = _heap_size(heap_sizes, 4)
    field_list_table = 0x03 if rows.get(0x03, 0) else 0x04
    method_list_table = 0x05 if rows.get(0x05, 0) else 0x06
    param_list_table = 0x07 if rows.get(0x07, 0) else 0x08
    row_sizes = {
        0x00: 2 + string_size + guid_size * 3,
        0x01: _coded_size(rows, [0x00, 0x1A, 0x23, 0x01], 2) + string_size * 2,
        0x02: 4 + string_size * 2 + _coded_size(rows, [0x02, 0x01, 0x1B], 2)
              + _table_size(rows, field_list_table) + _table_size(rows, method_list_table),
        0x03: _table_size(rows, 0x04),
        0x04: 2 + string_size + blob_size,
        0x05: _table_size(rows, 0x06),
        0x06: 4 + 2 + 2 + string_size + blob_size + _table_size(rows, param_list_table),
    }
    offsets = {}
    cursor = position
    for table in present:
        if table > 0x06:
            break
        offsets[table] = cursor
        end = cursor + row_sizes[table] * rows[table]
        if end > len(tables):
            raise ImageError("table stream is truncated inside table 0x%02X rows" % table)
        cursor = end
    for required, name in ((0x00, "Module"), (0x02, "TypeDef"), (0x06, "MethodDef")):
        if required not in offsets:
            raise ImageError("missing %s table" % name)

    def read_string(index: int) -> str:
        if index < 0 or index >= len(strings):
            raise ImageError("#Strings index %d is outside the heap" % index)
        end = strings.find(b"\x00", index)
        if end < 0:
            raise ImageError("#Strings entry at %d is not terminated" % index)
        return strings[index:end].decode("utf-8", "replace")

    module_at = offsets[0x00]
    mvid_index = _index(tables, module_at + 2 + string_size, guid_size, "Module.Mvid")
    guid_count = len(guids) // 16
    if mvid_index < 1 or mvid_index > guid_count:
        raise ImageError("Module.Mvid index %d is outside the #GUID heap (%d GUIDs)" % (mvid_index, guid_count))
    mvid = guid_from_le(guids[(mvid_index - 1) * 16:(mvid_index - 1) * 16 + 16])
    module_name = read_string(_index(tables, module_at + 2, string_size, "Module.Name"))

    type_rows = []
    base = offsets[0x02]
    extends_size = _coded_size(rows, [0x02, 0x01, 0x1B], 2)
    field_size = _table_size(rows, field_list_table)
    method_size = _table_size(rows, method_list_table)
    for index in range(rows[0x02]):
        at = base + index * row_sizes[0x02]
        type_name = read_string(_index(tables, at + 4, string_size, "TypeDef.TypeName"))
        namespace = read_string(_index(tables, at + 4 + string_size, string_size, "TypeDef.TypeNamespace"))
        method_start = _index(tables, at + 4 + string_size * 2 + extends_size + field_size, method_size, "TypeDef.MethodList")
        type_rows.append((type_name if not namespace else namespace + "." + type_name, method_start))

    method_rows = []
    base = offsets[0x06]
    for index in range(rows[0x06]):
        at = base + index * row_sizes[0x06]
        method_rows.append((0x06000000 | (index + 1), read_string(_index(tables, at + 8, string_size, "MethodDef.Name"))))

    method_ptr_indices = None
    if rows.get(0x05, 0):
        pointer_size = _table_size(rows, 0x06)
        method_ptr_indices = []
        for index in range(rows[0x05]):
            at = offsets[0x05] + index * pointer_size
            method_ptr_indices.append(_index(tables, at, pointer_size, "MethodPtr.Method"))

    type_of = {}
    for position, (full_name, method_start) in enumerate(type_rows):
        if position + 1 < len(type_rows):
            end = type_rows[position + 1][1]
        elif method_ptr_indices is not None:
            end = len(method_ptr_indices) + 1
        else:
            end = len(method_rows) + 1
        if method_start < 1 or end < method_start:
            raise ImageError("TypeDef.MethodList range %d..%d is invalid" % (method_start, end))
        for method_index in range(method_start, end):
            if method_ptr_indices is not None:
                if method_index > len(method_ptr_indices):
                    raise ImageError("TypeDef.MethodList index %d is outside MethodPtr" % method_index)
                method_def = method_ptr_indices[method_index - 1]
            else:
                method_def = method_index
            if 1 <= method_def <= len(method_rows):
                type_of[method_rows[method_def - 1][0]] = full_name
    return {"mvid": mvid, "module": module_name,
            "methods": {token: {"name": name, "type": type_of.get(token, "")} for token, name in method_rows}}


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


ROLE_PREFIX = {"framework": "RuneCLR.Group.Framework:", "author": "RuneCLR.Group.Author:"}
ROLE_TARGETS = (("framework", "Initialize"), ("framework", "Touch"),
                ("author", "Run"), ("author", "OnFrameworkEvent"))
MARKER_KIND = {"Run": "author:witness-entry", "OnFrameworkEvent": "author:witness-callback"}
GUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
HIT_RE = re.compile(r"GROUPED-WITNESS-HIT\s+checkpoint_id=(\S+)\s+md=(0x[0-9a-fA-F]+)")
BREAK_RE = re.compile(r"(Break instruction exception|Breakpoint\s+\d+\s+hit)")
LAST_EVENT_HIT_RE = re.compile(
    r"^Last event:\s*[0-9a-fA-F]+\.[0-9a-fA-F]+:\s*Hit breakpoint\s+\d+\s*$")
PROMPT_RE = re.compile(r"^\s*\d+:\d+>\s?")
HIT_LINE_PREFIX = "GROUPED-WITNESS-HIT"
FRAMEWORK_FIELD_ALIASES = {"native_code_addr": "dac_native_code_addr"}
EXT_DEBUGGER_PID = "debugger_target_pid"
EXT_REPO = "--repo-dir"
EXT_STOP_SYMBOL = "stop_symbol"
EXT_BYTECODE_SIZE = "bytecode_start_size"
EXT_RANGE_KIND = "range_kind"
EXT_NATIVE_CODE_ADDR = "native_code_addr"
EXT_LAYOUT = "layout"
IDENTITY_SOURCE = "host-methoddesc-chain"
AUTHOR_STOP_KINDS = ("interp-native-entry", "interp-first-entry")
FRAMEWORK_STOP_KINDS = ("jit-native",)
FRAMEWORK_RANGE_KIND = "observed-instructions-from-rip"
REQUIRED_MANIFEST_KEYS = ("host_run_id", "host_pid", "debugger_pid", "runtime_files", "images",
                          "host_records_path", "transcript_path", "debugger_events_path",
                          "exit_code", "observer_config")
REQUIRED_EVENT_FIELDS = ("checkpoint_id", "phase", "group", "group_ordinal", "target", "md_value",
                         "stop_kind", "pc", "frame", "start_ip", "method_hnd", "exception_clause_args",
                         "ir_code_start", "ir_code_size", "methoddesc_interpreter_code",
                         "native_code_start", "native_code_size", "dac_token", "dac_module",
                         "transcript_begin_offset", "transcript_end_offset", "diagnostic_error")
AUTHOR_EVENT_FIELDS = ("stop_symbol", "bytecode_start_size")
FRAMEWORK_EVENT_FIELDS = ("native_code_addr", "range_kind", "ip2md_md")
EVIDENCE_CHAIN = (
    "identity: observed native MethodDesc == host MethodInfo.MethodHandle.Value; the same host MethodInfo "
    "supplied ModuleVersionId + MethodDef token + ALC name, and that MVID + the staged PE SHA256 are re-bound "
    "to the staged bytes (identity_source=host-methoddesc-chain).",
    "identity corroboration: DAC token equals the host MethodDef token; the observed DAC module address is "
    "stable per loaded role image; an optional dac_module_mvid is cross-checked, and MVID is never claimed as "
    "a debugger read.",
    "author: native InterpExecMethod entry stop (symbol evidence), r9 == 0, frame-chain MethodDesc == host "
    "MethodDesc, startIp == live m_interpreterCode, non-empty IR whose start is startIp + measured "
    "bytecode_start_size; the native rip is reported as pc and is never treated as an IR offset.",
    "framework: stop pc equals the DAC NativeCodeAddr and ip2md returns the same MethodDesc; the reported "
    "range is a contiguous observed-instruction window from that pc, not a whole-method size.",
    "transcript: exact UTF-8 byte offsets into the raw file, a real break indication, and a genuine "
    "prompt-stripped GROUPED-WITNESS-HIT line; .echo/.printf/bp framing output is never evidence.",
)
LIMITATIONS = (
    "Collector fidelity is assumed: this verifier proves that the emitted event values match the host "
    "records, the staged image bytes and the raw transcript spans, but it cannot prove that the collector "
    "read those values from the stopped process instead of copying them.",
    "Host records are host-authored scalars; method_handle/token/MVID are re-bound here to staged image "
    "bytes, yet the host remains the source of the loaded-method identity.",
    "MVID is host-supplied and re-bound to the staged PE bytes; it is not read from the debugger by this "
    "verifier. Only the DAC token and the DAC module address are independent debugger-side corroboration.",
    "The framework range is a contiguous observed-instruction window from the stopped pc. It is not the "
    "whole method body and says nothing about unobserved code.",
    "No live capture has been verified with this verifier. Unit fixtures are synthetic parser controls and "
    "are never evidence of interpreter or JIT execution.",
)


def real_break_indication(span: str) -> bool:
    """A genuine debugger stop: a module-style break line or CDB's .lastevent hit form.

    The .lastevent form is matched only on a prompt-stripped line that starts with
    "Last event:", so command echoes and substrings never count.
    """
    if BREAK_RE.search(span):
        return True
    for line in span.splitlines():
        body = strip_prompts(line).strip()
        if body.startswith("Last event:") and LAST_EVENT_HIT_RE.match(body):
            return True
    return False


def first_present(event, name):
    """Return a role field, honouring the documented native_code_addr alias."""
    value = event.get(name)
    if value is not None:
        return value
    alias = FRAMEWORK_FIELD_ALIASES.get(name)
    return event.get(alias) if alias else None


def strip_prompts(text):
    """Drop the prompt(s) a stdin-pipe CDB prints in front of actual output."""
    for _ in range(8):
        stripped = PROMPT_RE.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    return text


def as_int(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text, 16) if text[:2].lower() == "0x" else int(text, 10)
        except ValueError:
            return None
    return None


def as_address(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        text = value.strip()
        if text[:2].lower() == "0x":
            try:
                number = int(text, 16)
            except ValueError:
                return None
            return number if number > 0 else None
    return None


def as_mvid(value):
    if not isinstance(value, str):
        return None
    match = GUID_RE.fullmatch(value.strip().strip("{}"))
    return match.group(0).lower() if match else None


def as_utc(value):
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text[-1:] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    if "." in text:
        head, _, rest = text.partition(".")
        digits = ""
        index = 0
        while index < len(rest) and rest[index].isdigit():
            digits += rest[index]
            index += 1
        text = head + "." + (digits + "000000")[:6] + rest[index:]
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed

@dataclass
class Verifier:
    manifest_path: Path
    repo_dir: Path | None = None
    checks: list = field(default_factory=list)
    failures: list = field(default_factory=list)
    extensions: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    info: dict = field(default_factory=dict)

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append(Check(name, bool(ok), detail))
        if not ok:
            self.failures.append((name + ": " + detail) if detail else name)
        return bool(ok)

    def extend(self, name: str, detail: str = "") -> None:
        if name not in self.extensions:
            self.extensions.append(name)
            self.notes.append(name + ": " + detail)

    def require(self, name: str, ok: bool, detail: str = "", extension: str | None = None) -> bool:
        if extension is not None and not ok:
            self.extend(extension, detail)
        return self.check(name, ok, detail)

    def _artifact(self, key: str):
        value = self.info["manifest"].get(key)
        if not isinstance(value, str) or not value:
            self.check("manifest." + key + " present", False, "missing path")
            return None
        path = Path(value)
        path = (self.manifest_path.parent / path).resolve() if not path.is_absolute() else path.resolve()
        return path

    def _outside_repo(self, label: str, path: Path) -> bool:
        if self.repo_dir is None:
            self.extend(EXT_REPO, "artifact paths were not checked against the tracked source tree")
            return True
        try:
            path.relative_to(self.repo_dir)
        except ValueError:
            return True
        return self.check(label + " outside tracked source", False, str(path) + " is inside " + str(self.repo_dir))

    def run(self) -> None:
        manifest = load_json(self.manifest_path)
        self.info["manifest"] = manifest
        self.check("manifest schema", manifest.get("schema") == MANIFEST_SCHEMA, str(manifest.get("schema")))
        missing = [key for key in REQUIRED_MANIFEST_KEYS if key not in manifest]
        self.check("manifest required fields", not missing, "missing: " + ", ".join(missing))
        if missing:
            return
        host_pid = as_int(manifest.get("host_pid"))
        debugger_pid = as_int(manifest.get("debugger_pid"))
        self.check("manifest pids are integers", host_pid is not None and debugger_pid is not None,
                   str(manifest.get("host_pid")) + "/" + str(manifest.get("debugger_pid")))
        if host_pid is None or debugger_pid is None:
            return
        self.check("debugger pid differs from the host pid", host_pid != debugger_pid, str(host_pid) + " == " + str(debugger_pid))
        self.check("host exit code is 0", as_int(manifest.get("exit_code")) == 0, str(manifest.get("exit_code")))
        self.check("observer config is recorded", isinstance(manifest.get("observer_config"), dict),
                   str(manifest.get("observer_config")))
        layout = manifest.get("layout")
        if isinstance(layout, dict):
            self.info["layout"] = layout
        else:
            self.extend(EXT_LAYOUT, "manifest does not record the capture layout (stage/module placement)")
        run_id = manifest.get("host_run_id")
        self.check("host run id present", isinstance(run_id, str) and bool(run_id), str(run_id))
        attach_pid = as_int(manifest.get("debugger_target_pid"))
        if attach_pid is None:
            self.extend(EXT_DEBUGGER_PID, "manifest does not record the debugger attach target; the event host_pid is host-authored")
        else:
            self.check("debugger attach target equals the host pid", attach_pid == host_pid,
                       str(attach_pid) + " vs " + str(host_pid))

        host_path = self._artifact("host_records_path")
        transcript_path = self._artifact("transcript_path")
        events_path = self._artifact("debugger_events_path")
        if not host_path or not transcript_path or not events_path:
            return
        for label, path in (("host records", host_path), ("transcript", transcript_path), ("debugger events", events_path)):
            self.check(label + " exists", path.is_file(), str(path))
            self._outside_repo(label, path)
        if not all(path.is_file() for path in (host_path, transcript_path, events_path)):
            return

        self.info["hashes"] = {
            "host_records": sha256_file(host_path),
            "transcript": sha256_file(transcript_path),
            "debugger_events": sha256_file(events_path),
        }
        for key, computed in EXT_HASHES:
            declared = manifest.get(key)
            self.require("manifest." + key + " binds " + computed,
                         isinstance(declared, str) and declared.lower() == self.info["hashes"][computed],
                         "declared " + str(declared) + " vs " + self.info["hashes"][computed], key)

        transcript_bytes = transcript_path.read_bytes()
        self.info["transcript_bytes"] = len(transcript_bytes)
        try:
            transcript_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            self.check("transcript is valid UTF-8", False, str(error))

        image_sha = {}
        for group_key in ("runtime_files", "images"):
            entries = manifest.get(group_key)
            if not isinstance(entries, list) or not entries:
                self.check("manifest." + group_key + " non-empty", False, "missing")
                continue
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not isinstance(entry.get("sha256"), str):
                    self.check("manifest." + group_key + " entry shape", False, str(entry))
                    continue
                path = Path(entry["path"]).resolve()
                self.check(group_key + " file exists", path.is_file(), str(path))
                if not path.is_file():
                    continue
                self.check(group_key + " sha256 matches", sha256_file(path) == entry["sha256"].lower(), str(path))
                if group_key == "images":
                    image_sha[str(path)] = entry["sha256"].lower()

        parsed = {}
        for path_text, sha in image_sha.items():
            path = Path(path_text)
            if not path.is_file():
                continue
            try:
                parsed[path_text] = parse_managed_image(path)
            except (ImageError, OSError, struct.error, ValueError) as error:
                self.check("image parses " + path.name, False, str(error))
        self.info["parsed"] = parsed
        if not parsed:
            self.check("at least one staged image is readable", False, "no images were parsed")

        host_records = load_jsonl(host_path)
        self.check("host records non-empty", bool(host_records))
        for index, record in enumerate(host_records):
            self.check("host record " + str(index) + " schema", record.get("schema") == HOST_SCHEMA, str(record.get("schema")))
        self.check("host records never claim verified",
                   not any(record.get("witness_verified") is True or record.get("verified") is True for record in host_records),
                   "a host record sets a verified flag")
        run_ids = {record.get("run_id") for record in host_records}
        self.check("host records share the manifest run id", run_ids == {run_id}, str(run_ids))
        host_pids = {as_int(record.get("process_id")) for record in host_records}
        self.check("host records process id matches the manifest", host_pids == {host_pid}, str(host_pids))

        identity_index = {}
        for record in host_records:
            if record.get("phase") != "identity":
                continue
            role = record.get("role")
            group = str(record.get("group"))
            ordinal = as_int(record.get("group_ordinal"))
            label = "host identity [" + group + "/" + str(ordinal) + "] " + str(role)
            if role not in ROLE_PREFIX:
                self.check(label + " role recognized", False, str(role))
                continue
            if ordinal is None:
                self.check(label + " group ordinal present", False, str(record.get("group_ordinal")))
                continue
            token = as_int(record.get("method_token"))
            mvid = str(record.get("image_mvid", "")).lower()
            sha = str(record.get("image_sha256", "")).lower()
            bound = None
            for path_text, info in parsed.items():
                if info["mvid"].lower() == mvid and image_sha.get(path_text) == sha:
                    bound = info
                    break
            if bound is None:
                self.check(label + " binds a staged image by MVID and SHA256", False,
                           "mvid=" + mvid + " sha=" + sha)
                continue
            method = bound["methods"].get(token)
            if method is None:
                self.check(label + " MethodDef token exists in the staged image", False, "token=" + str(token))
                continue
            self.check(label + " declared entry matches the image",
                       record.get("declared_entry") == method["type"] + "." + method["name"],
                       str(record.get("declared_entry")) + " vs " + method["type"] + "." + method["name"])
            self.check(label + " ALC name matches the role",
                       str(record.get("alc_name", "")).startswith(ROLE_PREFIX[role]), str(record.get("alc_name")))
            handle = as_int(record.get("method_handle"))
            self.check(label + " method handle is an address", handle is not None and handle != 0, str(record.get("method_handle")))
            key = (group, ordinal, role, method["name"])
            if key in identity_index:
                self.check(label + " identity is unique", False, "duplicate identity for " + method["name"])
            identity_index[key] = record

        events = load_jsonl(events_path)
        self.check("debugger events non-empty", bool(events))
        self.check("events never carry a verdict flag",
                   not any(event.get("verified") is True or event.get("witness_verified") is True for event in events),
                   "an event sets a verified flag")

        groups = {}
        for event in events:
            group = str(event.get("group"))
            ordinal = as_int(event.get("group_ordinal"))
            if ordinal is None:
                self.check("event group ordinal present", False, str(event.get("group_ordinal")))
                continue
            groups.setdefault((group, ordinal), []).append(event)
        self.check("at least one observed group", bool(groups))

        checkpoint_index = {}
        for index, record in enumerate(host_records):
            identifier = record.get("checkpoint_id")
            if isinstance(identifier, str) and (record.get("marker_kind") in ("checkpoint", "checkpoint-published")
                                                or record.get("phase") == "checkpoint"):
                checkpoint_index.setdefault(identifier, index)

        seen_checkpoints = {}
        contexts = {}
        for (group, ordinal), group_events in sorted(groups.items()):
            self._verify_group(group, ordinal, group_events, identity_index, host_records, transcript_bytes,
                               str(run_id), host_pid, seen_checkpoints, checkpoint_index, contexts)
        for name, owners in sorted(contexts.items()):
            self.check("load context " + name + " belongs to one group", len(owners) == 1, str(sorted(owners)))

    def _verify_group(self, group, ordinal, events, identity_index, host_records, raw,
                      run_id, host_pid, seen_checkpoints, checkpoint_index, contexts) -> None:
        label = "[" + group + "/" + str(ordinal) + "]"
        target_events = {}
        for event in events:
            phase = event.get("phase")
            target = event.get("target")
            if phase == "before-cleanup":
                self.check(label + " cleanup stop carries no role target", target in (None, ""), str(target))
                continue
            if target not in TARGETS:
                self.check(label + " event target recognized", False, str(target))
                continue
            if target in target_events:
                self.check(label + " " + target + " observed once", False, "duplicate target")
                continue
            target_events[target] = event
        for target in TARGETS:
            self.check(label + " " + target + " observed", target in target_events, "missing target event")

        phases_by_checkpoint = {}
        for target, event in target_events.items():
            identifier = event.get("checkpoint_id")
            if isinstance(identifier, str) and identifier:
                phases_by_checkpoint.setdefault(identifier, set()).add(event.get("phase"))
        for identifier, phases in phases_by_checkpoint.items():
            self.check(label + " checkpoint " + identifier + " maps to one phase", len(phases) == 1,
                       str(sorted(str(phase) for phase in phases)))
        run_event = target_events.get("Run", {})
        touch_event = target_events.get("Touch", {})
        self.check(label + " Run and Touch share the before-author checkpoint",
                   "Run" in target_events and "Touch" in target_events
                   and run_event.get("checkpoint_id") == touch_event.get("checkpoint_id"),
                   str(run_event.get("checkpoint_id")) + " vs " + str(touch_event.get("checkpoint_id")))

        for role in ("framework", "author"):
            names = []
            for role_name, target in ROLE_TARGETS:
                if role_name != role:
                    continue
                identity = identity_index.get((group, ordinal, role, target))
                if identity is not None:
                    names.append(str(identity.get("alc_name")))
            self.check(label + " " + role + " identities share one load context", len(set(names)) == 1, str(names))
        framework_names = {str(identity_index[key].get("alc_name")) for key in identity_index
                           if key[0] == group and key[1] == ordinal and key[2] == "framework"}
        author_names = {str(identity_index[key].get("alc_name")) for key in identity_index
                        if key[0] == group and key[1] == ordinal and key[2] == "author"}
        self.check(label + " framework and author use separate load contexts", not (framework_names & author_names),
                   str(framework_names) + " / " + str(author_names))
        for name in framework_names | author_names:
            contexts.setdefault(name, set()).add((group, ordinal))

        for role, role_targets in (("framework", ("Initialize", "Touch")), ("author", ("Run", "OnFrameworkEvent"))):
            addresses = []
            for target in role_targets:
                event = target_events.get(target)
                address = as_address(event.get("dac_module")) if event is not None else None
                if address is not None:
                    addresses.append(address)
            self.check(label + " " + role + " events share one DAC module address", len(set(addresses)) == 1, str(addresses))
        framework_addresses = {as_address(target_events[t].get("dac_module")) for t in ("Initialize", "Touch") if t in target_events}
        author_addresses = {as_address(target_events[t].get("dac_module")) for t in ("Run", "OnFrameworkEvent") if t in target_events}
        self.check(label + " framework and author modules are distinct",
                   not (framework_addresses & author_addresses - {None}),
                   str(framework_addresses) + " / " + str(author_addresses))

        for target in TARGETS:
            event = target_events.get(target)
            if event is None:
                continue
            role = TARGET_ROLE[target]
            identity = identity_index.get((group, ordinal, role, target))
            if identity is None:
                self.check(label + " " + target + " host identity for this group", False,
                           "no identity record for " + role + "/" + target + " at this group/ordinal")
                continue
            self._verify_target(label, group, ordinal, target, role, event, identity, host_records, raw,
                                run_id, host_pid, seen_checkpoints, checkpoint_index)

    def _verify_target(self, label, group, ordinal, target, role, event, identity, host_records, raw,
                       run_id, host_pid, seen_checkpoints, checkpoint_index) -> None:
        prefix = label + " " + target
        for name in REQUIRED_EVENT_FIELDS:
            if name not in event:
                self.check(prefix + " field " + name + " present", False, "event field is missing")
        for name in (AUTHOR_EVENT_FIELDS if role == "author" else FRAMEWORK_EVENT_FIELDS):
            if first_present(event, name) is None:
                extension = {"stop_symbol": EXT_STOP_SYMBOL, "bytecode_start_size": EXT_BYTECODE_SIZE,
                             "range_kind": EXT_RANGE_KIND, "native_code_addr": EXT_NATIVE_CODE_ADDR,
                             "ip2md_md": EXT_IP2MD}.get(name)
                self.require(prefix + " field " + name + " present", False, "event field is missing or null", extension)

        identifier = event.get("checkpoint_id")
        if isinstance(identifier, str) and identifier:
            self.check(prefix + " checkpoint id carries the host run id", identifier.startswith(run_id + "-"),
                       identifier + " vs run " + run_id)
            key = (group, ordinal, identifier, target)
            previous = seen_checkpoints.get(key)
            self.check(prefix + " checkpoint id and target are unique", previous is None, str(previous))
            seen_checkpoints[key] = prefix
        else:
            self.check(prefix + " checkpoint id present", False, str(identifier))
        self.check(prefix + " phase matches the target convention", event.get("phase") == TARGET_PHASE[target],
                   str(event.get("phase")) + " vs " + TARGET_PHASE[target])
        self.check(prefix + " diagnostic error is empty", event.get("diagnostic_error") in (None, ""),
                   str(event.get("diagnostic_error")))
        allowed = AUTHOR_STOP_KINDS if role == "author" else FRAMEWORK_STOP_KINDS
        self.check(prefix + " stop kind is an execution stop", event.get("stop_kind") in allowed, str(event.get("stop_kind")))
        if host_pid is not None and event.get("host_pid") is not None:
            self.check(prefix + " event host pid matches the manifest", as_int(event.get("host_pid")) == host_pid,
                       str(event.get("host_pid")))

        md = as_int(identity.get("method_handle"))
        self.check(prefix + " observed native MethodDesc equals the host MethodHandle.Value",
                   md is not None and as_int(event.get("md_value")) == md,
                   str(event.get("md_value")) + " vs " + str(identity.get("method_handle")))
        token = as_int(identity.get("method_token"))
        self.check(prefix + " DAC token equals the host MethodDef token",
                   token is not None and as_int(event.get("dac_token")) == token,
                   str(event.get("dac_token")) + " vs " + str(identity.get("method_token")))
        module_address = as_address(event.get("dac_module"))
        module_mvid = as_mvid(event.get("dac_module_mvid"))
        if module_address is None:
            claim = as_mvid(event.get("dac_module_mvid")) or as_mvid(event.get("dac_module"))
            if claim is not None:
                self.require(prefix + " observed DAC module address", False,
                             "an MVID claim exists without an observed module address", EXT_DAC_MVID)
            else:
                self.require(prefix + " observed DAC module address", False,
                             "dac_module is missing or zero: " + str(event.get("dac_module")), EXT_DAC_MVID)
        else:
            self.check(prefix + " observed DAC module address", True)
            if module_mvid is not None:
                self.check(prefix + " claimed DAC module MVID equals the host MVID",
                           module_mvid == str(identity.get("image_mvid", "")).lower(),
                           module_mvid + " vs " + str(identity.get("image_mvid")))
        self.check(prefix + " ALC name matches the role", str(identity.get("alc_name", "")).startswith(ROLE_PREFIX[role]),
                   str(identity.get("alc_name")))

        if role == "author":
            self.check(prefix + " frame chain returns the host MethodDesc",
                       md is not None and as_int(event.get("method_hnd")) == md,
                       str(event.get("method_hnd")) + " vs " + str(event.get("md_value")))
            symbol = event.get("stop_symbol")
            self.check(prefix + " stop is inside InterpExecMethod",
                       isinstance(symbol, str) and "InterpExecMethod" in symbol, str(symbol))
            frame = as_int(event.get("frame"))
            self.check(prefix + " live interpreter frame pointer present", frame is not None and frame != 0,
                       str(event.get("frame")))
            self.check(prefix + " r9 exception clause args == 0 (first method entry)",
                       as_int(event.get("exception_clause_args")) == 0,
                       "exception_clause_args=" + str(event.get("exception_clause_args")))
            start_ip = as_int(event.get("start_ip"))
            interpreter_code = as_int(event.get("methoddesc_interpreter_code"))
            self.check(prefix + " m_interpreterCode is live (not 0/poison 1)",
                       interpreter_code is not None and interpreter_code not in (0, 1),
                       str(event.get("methoddesc_interpreter_code")))
            self.check(prefix + " startIp equals m_interpreterCode",
                       start_ip is not None and start_ip != 0 and start_ip == interpreter_code,
                       str(event.get("start_ip")) + " vs " + str(event.get("methoddesc_interpreter_code")))
            ir_start = as_int(event.get("ir_code_start"))
            ir_size = as_int(event.get("ir_code_size"))
            header_size = as_int(event.get("bytecode_start_size"))
            self.check(prefix + " bytecode header size is the measured PDB sizeof",
                       header_size is not None and header_size > 0, str(event.get("bytecode_start_size")))
            self.check(prefix + " IR body is non-empty", ir_size is not None and ir_size > 0, str(event.get("ir_code_size")))
            self.check(prefix + " IR body starts at startIp + measured bytecode header",
                       start_ip is not None and ir_start is not None and header_size is not None
                       and ir_start == start_ip + header_size,
                       "start_ip=" + str(event.get("start_ip")) + " ir=" + str(event.get("ir_code_start"))
                       + " size=" + str(event.get("bytecode_start_size")))
            pc = as_int(event.get("pc"))
            self.check(prefix + " native stop pc present", pc is not None and pc != 0, str(event.get("pc")))
            self.check(prefix + " native stop pc is not an IR offset",
                       pc is not None and ir_start is not None and pc != ir_start,
                       "pc=" + str(event.get("pc")) + " ir=" + str(event.get("ir_code_start")))
            self.check(prefix + " native stop pc is outside the IR buffer",
                       pc is not None and ir_start is not None and ir_size is not None
                       and not (ir_start <= pc < ir_start + ir_size),
                       "pc=" + str(event.get("pc")) + " ir buffer=" + str(event.get("ir_code_start"))
                       + "+" + str(event.get("ir_code_size")))
            self._marker_after_entry(prefix, group, ordinal, target, event, host_records, checkpoint_index)
        else:
            self.check(prefix + " range kind is observed instructions from the stop pc",
                       event.get("range_kind") == FRAMEWORK_RANGE_KIND, str(event.get("range_kind")))
            pc = as_int(event.get("pc"))
            native_address = as_int(first_present(event, "native_code_addr"))
            start = as_int(event.get("native_code_start"))
            size = as_int(event.get("native_code_size"))
            self.check(prefix + " DAC NativeCodeAddr is known",
                       native_address is not None and native_address != 0, str(event.get("native_code_addr")))
            self.check(prefix + " stop pc equals the DAC NativeCodeAddr",
                       pc is not None and native_address is not None and pc == native_address,
                       "pc=" + str(event.get("pc")) + " native=" + str(event.get("native_code_addr")))
            self.check(prefix + " observed range starts at the stop pc",
                       start is not None and pc is not None and start == pc,
                       "start=" + str(event.get("native_code_start")) + " pc=" + str(event.get("pc")))
            self.check(prefix + " observed range is non-empty", size is not None and size > 0,
                       str(event.get("native_code_size")))
            ip2md = as_int(event.get("ip2md_md"))
            self.check(prefix + " ip2md returns the same MethodDesc", ip2md is not None and ip2md == md,
                       "ip2md=" + str(event.get("ip2md_md")) + " vs md=" + str(event.get("md_value")))
        self._transcript_span(prefix, event, raw)

    def _marker_after_entry(self, prefix, group, ordinal, target, event, host_records, checkpoint_index) -> None:
        kind = MARKER_KIND[target]
        marker = None
        marker_index = None
        count = 0
        for index, record in enumerate(host_records):
            if str(record.get("group")) != group or as_int(record.get("group_ordinal")) != ordinal:
                continue
            if record.get("marker_kind") != kind:
                continue
            count += 1
            marker, marker_index = record, index
        self.check(prefix + " host execution marker present", marker is not None, kind)
        if marker is None:
            return
        self.check(prefix + " host execution marker is unique", count == 1, str(count))
        self.check(prefix + " marker is an author-side record", marker.get("role") == "author", str(marker.get("role")))
        checkpoint_time = as_utc(event.get("checkpoint_created_utc"))
        marker_time = as_utc(marker.get("timestamp_utc"))
        if checkpoint_time is not None and marker_time is not None:
            self.check(prefix + " marker follows the checkpoint publish", marker_time >= checkpoint_time,
                       str(marker.get("timestamp_utc")) + " vs " + str(event.get("checkpoint_created_utc")))
            return
        published_index = checkpoint_index.get(str(event.get("checkpoint_id")))
        if published_index is not None:
            self.check(prefix + " marker follows the checkpoint publish", marker_index > published_index,
                       "marker line " + str(marker_index) + " vs checkpoint line " + str(published_index))
            return
        self.require(prefix + " marker follows the checkpoint publish", False,
                     "no checkpoint_created_utc on the event and no checkpoint record in host.jsonl",
                     EXT_CHECKPOINT_TIME)

    def _transcript_span(self, prefix, event, raw) -> None:
        begin = as_int(event.get("transcript_begin_offset"))
        end = as_int(event.get("transcript_end_offset"))
        if raw is None:
            self.check(prefix + " transcript bytes available", False, "the raw transcript was not read")
            return
        if begin is None or end is None or begin < 0 or end <= begin or end > len(raw):
            self.check(prefix + " transcript byte range is valid",
                       False, str(begin) + ".." + str(end) + " of " + str(len(raw)) + " bytes")
            return
        try:
            span = raw[begin:end].decode("utf-8")
        except UnicodeDecodeError as error:
            self.check(prefix + " transcript byte range decodes as UTF-8", False, str(error))
            return
        self.check(prefix + " transcript byte range decodes as UTF-8", True)
        self.check(prefix + " transcript shows a real debugger stop", real_break_indication(span),
                   "no break indication in the span")
        genuine = []
        echoed = 0
        for line in span.splitlines():
            match = HIT_RE.search(line)
            if match is None:
                continue
            body = strip_prompts(line).lstrip()
            if body.startswith(HIT_LINE_PREFIX):
                genuine.append(match)
            else:
                echoed += 1
        if not genuine:
            self.check(prefix + " transcript hit is runtime output, not a command echo", False,
                       "only command/framing hit lines were found" if echoed else "no GROUPED-WITNESS-HIT line")
            return
        self.check(prefix + " transcript hit is runtime output, not a command echo", True)
        by_checkpoint = [match for match in genuine if match.group(1) == str(event.get("checkpoint_id"))]
        self.check(prefix + " transcript hit checkpoint matches", bool(by_checkpoint),
                   "no genuine hit for checkpoint " + str(event.get("checkpoint_id")))
        if not by_checkpoint:
            return
        observed = []
        for match in by_checkpoint:
            try:
                observed.append(int(match.group(2), 16))
            except ValueError:
                continue
        self.check(prefix + " transcript hit MethodDesc matches",
                   as_int(event.get("md_value")) in observed, str([hex(value) for value in observed]))


def build_report(verifier: Verifier) -> dict:
    manifest_sha = sha256_file(verifier.manifest_path) if verifier.manifest_path.is_file() else None
    return {
        "schema": REPORT_SCHEMA,
        "manifest_path": str(verifier.manifest_path),
        "manifest_sha256": manifest_sha,
        "verified": not verifier.failures,
        "identity_source": IDENTITY_SOURCE,
        "evidence_chain": list(EVIDENCE_CHAIN),
        "failures": list(verifier.failures),
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in verifier.checks],
        "schema_extensions_required": sorted(verifier.extensions),
        "extension_notes": list(verifier.notes),
        "artifact_hashes": verifier.info.get("hashes"),
        "layout": verifier.info.get("layout"),
        "limitations": list(LIMITATIONS),
        "note": "verified is computed by this verifier only; host.jsonl and any host verdict flag are never modified",
    }


def main(argv) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed grouped method-witness verifier")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--repo-dir", default=None, help="tracked source root; artifact paths must be outside it")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)
    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.is_file():
        print("NOT-VERIFIED: manifest not found: " + str(manifest_path), file=sys.stderr)
        return 1
    verifier = Verifier(manifest_path=manifest_path,
                        repo_dir=Path(args.repo_dir).resolve() if args.repo_dir else None)
    try:
        verifier.run()
    except Exception as error:
        verifier.check("verifier completed", False, type(error).__name__ + ": " + str(error))
    report = build_report(verifier)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    print(text)
    summary = "VERIFIED" if report["verified"] else "NOT-VERIFIED"
    print(summary + ": " + str(len(report["failures"])) + " failure(s), "
          + str(len(report["schema_extensions_required"])) + " schema extension(s)", file=sys.stderr)
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
