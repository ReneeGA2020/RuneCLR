"""Synthetic parser-control tests for the grouped method-witness verifier.

Every fixture here is hand-built (images, host records, transcript, events). These tests exercise
the verifier's parsing and fail-closed rejection paths only. Nothing here is evidence that an
interpreter or JIT body ran, and none of it may be cited as a live capture.
"""
from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verify

RUN_ID = "0123456789abcdef0123456789abcdef"
HOST_PID = 4242
DEBUGGER_PID = 4343
FW_MVID = "11111111-2222-3333-4444-555566667777"
AA_MVID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
AB_MVID = "fedcba98-7654-3210-fedc-ba9876543210"

FRAMEWORK_TYPE = "RuneCLR.GroupedHost.Fixtures.FrameworkEntry"
AUTHOR_TYPE = "RuneCLR.GroupedHost.Fixtures.AuthorEntry"
TARGETS = ("Initialize", "Touch", "Run", "OnFrameworkEvent")
ROLE_OF = {"Initialize": "framework", "Touch": "framework", "Run": "author", "OnFrameworkEvent": "author"}
PHASE_OF = {"Initialize": "before-framework", "Touch": "before-author",
            "Run": "before-author", "OnFrameworkEvent": "before-callback"}
TOKEN_OF = {"Initialize": 0x06000001, "Touch": 0x06000002, "Run": 0x06000001, "OnFrameworkEvent": 0x06000002}


def guid_bytes(text):
    digits = text.replace("-", "")
    return (bytes.fromhex(digits[0:8])[::-1] + bytes.fromhex(digits[8:12])[::-1]
            + bytes.fromhex(digits[12:16])[::-1] + bytes.fromhex(digits[16:32]))


def pad4(size):
    return (size + 3) // 4 * 4


def build_image(path, mvid, module_name, types, typerefs=0, fields=0, params=0,
                truncate_rows=None, mvid_index=1, truncate_tables=0):
    """Emit a minimal ECMA-335 managed PE.

    The #~ stream follows ECMA-335 II.24.2.6: the Rows array holds one 4-byte count per table
    present in the Valid bitmask (packed, not 64 dense entries), in ascending table order, and the
    table data follows in the same order. Optional TypeRef/Field/Param tables exercise gaps in the
    bitmap; truncate_rows/mvid_index/drop_metadata_tail build malformed images for parser tests.
    """
    strings = bytearray(b"\x00")

    def intern(text):
        offset = len(strings)
        strings.extend(text.encode("utf-8") + b"\x00")
        return offset

    module_string = intern(module_name)
    type_rows = []
    method_names = []
    for full_name, methods in types:
        namespace, _, name = full_name.rpartition(".")
        type_rows.append((intern(name), intern(namespace) if namespace else 0, len(method_names) + 1))
        method_names.extend(methods)
    method_rows = [intern(name) for name in method_names]

    present = [0x00, 0x02, 0x06]
    if typerefs:
        present.append(0x01)
    if fields:
        present.append(0x04)
    if params:
        present.append(0x08)
    present.sort()
    counts = {0x00: 1, 0x02: len(type_rows), 0x06: len(method_rows)}
    if typerefs:
        counts[0x01] = typerefs
    if fields:
        counts[0x04] = fields
    if params:
        counts[0x08] = params
    valid = 0
    for table in present:
        valid |= 1 << table

    table = bytearray()
    table += struct.pack("<I", 0)
    table += struct.pack("<BBBB", 2, 0, 0, 0)
    table += struct.pack("<Q", valid)
    table += struct.pack("<Q", 0)
    written = len(present) if truncate_rows is None else max(0, min(truncate_rows, len(present)))
    for table_id in present[:written]:
        table += struct.pack("<I", counts[table_id])
    if truncate_rows is None or written == len(present):
        table += struct.pack("<HHHHH", 0, module_string, mvid_index, 0, 0)
        if 0x01 in present:
            table += b"\x00" * (6 * typerefs)
        for name_index, namespace_index, method_start in type_rows:
            table += struct.pack("<IHHHHH", 0, name_index, namespace_index, 0, 1, method_start)
        if 0x04 in present:
            table += b"\x00" * (6 * fields)
        for name_index in method_rows:
            table += struct.pack("<IHHHHH", 0x2000, 0, 6, name_index, 1, 1)
        if 0x08 in present:
            table += b"\x00" * (6 * params)
    tables = bytes(table)
    if truncate_tables:
        tables = tables[:-truncate_tables]
    strings_bytes = bytes(strings)
    guids = guid_bytes(mvid)

    version = b"v4.0.30319\x00\x00"
    header = bytearray()
    header += b"BSJB"
    header += struct.pack("<HH", 1, 1)
    header += struct.pack("<I", 0)
    header += struct.pack("<I", len(version))
    header += version
    header += struct.pack("<HH", 0, 3)
    entries = (("#~", len(tables)), ("#Strings", len(strings_bytes)), ("#GUID", len(guids)))
    data_offset = len(header) + sum(8 + pad4(len(name) + 1) for name, _ in entries)
    cursor = data_offset
    for name, size in entries:
        header += struct.pack("<II", cursor, size) + name.encode("ascii") + b"\x00"
        header += b"\x00" * ((-len(header)) % 4)
        cursor += size
    assert len(header) == data_offset, (len(header), data_offset)
    metadata = bytes(header) + tables + strings_bytes + guids

    pe_offset = 0x80
    optional_size = 240
    section_table = pe_offset + 24 + optional_size
    image = bytearray(0x200)
    image[0:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, pe_offset)
    image[pe_offset:pe_offset + 4] = b"PE\x00\x00"
    struct.pack_into("<HHIIIHH", image, pe_offset + 4, 0x8664, 1, 0, 0, 0, optional_size, 0x0022)
    optional = pe_offset + 24
    struct.pack_into("<H", image, optional, 0x20B)
    struct.pack_into("<I", image, optional + 108, 16)
    struct.pack_into("<II", image, optional + 112 + 14 * 8, 0x2000, 72)
    struct.pack_into("<8sIIII", image, section_table, b".text\x00\x00\x00", 0x1000, 0x2000, 0x1000, 0x200)
    cli = bytearray(72)
    struct.pack_into("<I", cli, 0, 72)
    struct.pack_into("<HH", cli, 4, 2, 5)
    struct.pack_into("<II", cli, 8, 0x2100, len(metadata))
    struct.pack_into("<I", cli, 16, 1)
    image += cli
    image += b"\x00" * (0x300 - len(image))
    image += metadata
    # A section declares 0x1000 raw bytes at 0x200; pad so the synthetic PE is well formed.
    image += b"\x00" * max(0, 0x200 + 0x1000 - len(image))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(image))
    return path


def iso(seconds):
    return "2026-11-17T10:%02d:%02d.0000000+00:00" % ((seconds // 60) % 60, seconds % 60)


class Bundle:
    """One synthetic capture bundle: staged images, host records, transcript, events, manifest."""

    def __init__(self, root, groups=(("A1", 1, "author-a"), ("B1", 2, "author-b")), preamble=b""):
        self.root = Path(root)
        self.groups = groups
        self.omit = set()
        self.overrides = {}
        self.framing = False
        self.events = []
        self.records = []
        self.transcript = bytearray(preamble)
        self.serial = 0
        self.build_images()
        self.build_records()
        self.write()

    def build_images(self):
        specs = {
            "framework": (FW_MVID, "RuneCLR.GroupedHost.Framework", [(FRAMEWORK_TYPE, ["Initialize", "Touch"])]),
            "author-a": (AA_MVID, "RuneCLR.GroupedHost.Author", [(AUTHOR_TYPE, ["Run", "OnFrameworkEvent"])]),
            "author-b": (AB_MVID, "RuneCLR.GroupedHost.Author", [(AUTHOR_TYPE, ["Run", "OnFrameworkEvent"])]),
        }
        self.images = {}
        for key, (mvid, module, types) in specs.items():
            path = build_image(self.root / "images" / key / (module + ".dll"), mvid, module, types)
            self.images[key] = {"path": path, "mvid": mvid, "sha": verify.sha256_file(path)}
        self.runtime = self.root / "runtime" / "coreclr.dll"
        self.runtime.parent.mkdir(parents=True, exist_ok=True)
        self.runtime.write_bytes(b"synthetic-coreclr")

    def next_checkpoint(self):
        self.serial += 1
        return "%s-%02d" % (RUN_ID, self.serial)

    def handle(self, target, ordinal):
        base = 0x7FF800001000 + (ordinal - 1) * 0x1000
        return base + (0x0 if target in ("Initialize", "Run") else 0x10) + (0x1000 if target in ("Run", "OnFrameworkEvent") else 0)

    def module_address(self, role, ordinal):
        return (0x7FF9E4000000 if role == "framework" else 0x7FF9E4690000) + (ordinal - 1) * 0x100000

    def native_rip(self, index, target):
        return 0x7FFB12345000 + index * 0x1000 + (0x10 if target == "OnFrameworkEvent" else 0)

    def identity(self, group, ordinal, role, target, image_key, timestamp):
        image = self.images[image_key]
        prefix = "RuneCLR.Group.Framework:" if role == "framework" else "RuneCLR.Group.Author:"
        entry_type = FRAMEWORK_TYPE if role == "framework" else AUTHOR_TYPE
        return {
            "schema": "runeclr-grouped-witness/1", "phase": "identity", "role": role,
            "call_ordinal": 0, "group": group, "group_ordinal": ordinal, "run_id": RUN_ID,
            "process_id": HOST_PID, "image_name": image["path"].stem,
            "image_full_name": image["path"].stem + ", Version=1.0.0.0", "image_sha256": image["sha"],
            "image_mvid": image["mvid"], "image_bytes": image["path"].stat().st_size,
            "alc_name": prefix + group + str(ordinal), "method_token": TOKEN_OF[target],
            "method_handle": self.handle(target, ordinal), "declared_entry": entry_type + "." + target,
            "marker_kind": "identity", "marker_run": 0, "marker_token": "",
            "witness_source": "host", "witness_verified": False, "timestamp_utc": timestamp,
        }

    def marker(self, group, ordinal, kind, timestamp):
        target = "Run" if kind == "author:witness-entry" else "OnFrameworkEvent"
        return {
            "schema": "runeclr-grouped-witness/1", "phase": "entry", "role": "author",
            "call_ordinal": 1, "group": group, "group_ordinal": ordinal, "run_id": RUN_ID,
            "process_id": HOST_PID, "image_name": "RuneCLR.GroupedHost.Author",
            "image_full_name": "RuneCLR.GroupedHost.Author", "image_sha256": self.images["author-a"]["sha"],
            "image_mvid": self.images["author-a"]["mvid"], "image_bytes": 0,
            "alc_name": "RuneCLR.Group.Author:" + group + str(ordinal), "method_token": 0, "method_handle": 0,
            "declared_entry": AUTHOR_TYPE + "." + target, "marker_kind": kind, "marker_run": 1,
            "marker_token": "", "witness_source": "host", "witness_verified": False, "timestamp_utc": timestamp,
        }

    def append_transcript(self, event):
        begin = len(self.transcript)
        framing = b""
        if self.framing:
            framing = ("0:000> .echo GROUPED-WITNESS-HIT checkpoint_id=%s md=0x%x\n"
                       % (event["checkpoint_id"], event["md_value"])).encode("utf-8")
        self.transcript += framing + (
            "0:000> g\n"
            "(1f2c.3a10): Break instruction exception - code 80000003 (first chance)\n"
            "0:000> GROUPED-WITNESS-HIT checkpoint_id=%s md=0x%x\n"
            "0:000> " % (event["checkpoint_id"], event["md_value"])).encode("utf-8")
        event["transcript_begin_offset"] = begin
        event["transcript_end_offset"] = len(self.transcript)

    def rebuild_transcript(self):
        self.transcript = bytearray()
        for event in self.events:
            self.append_transcript(event)

    def build_records(self):
        for index, (group, ordinal, author_key) in enumerate(self.groups):
            for target in TARGETS:
                role = ROLE_OF[target]
                image_key = "framework" if role == "framework" else author_key
                self.records.append(self.identity(group, ordinal, role, target, image_key, iso(index * 20)))
            self.records.append(self.marker(group, ordinal, "author:witness-entry", iso(index * 20 + 10)))
            self.records.append(self.marker(group, ordinal, "author:witness-callback", iso(index * 20 + 10)))
            checkpoint_time = iso(index * 20 + 5)
            framework_checkpoint = self.next_checkpoint()
            author_checkpoint = self.next_checkpoint()
            callback_checkpoint = self.next_checkpoint()
            identifiers = {"Initialize": framework_checkpoint, "Touch": author_checkpoint,
                           "Run": author_checkpoint, "OnFrameworkEvent": callback_checkpoint}
            for target in TARGETS:
                role = ROLE_OF[target]
                md = self.handle(target, ordinal)
                event = {
                    "checkpoint_id": identifiers[target], "phase": PHASE_OF[target], "group": group,
                    "group_ordinal": ordinal, "target": target, "md_value": md,
                    "dac_token": TOKEN_OF[target], "dac_module": self.module_address(role, ordinal),
                    "checkpoint_created_utc": checkpoint_time, "host_pid": HOST_PID,
                    "diagnostic_error": None, "transcript_begin_offset": 0, "transcript_end_offset": 0,
                }
                if role == "author":
                    start_ip = 0x7FF800003000 + index * 0x1000 + (0x10 if target == "OnFrameworkEvent" else 0)
                    header = 0x10
                    event.update({
                        "stop_kind": "interp-native-entry", "pc": self.native_rip(index, target),
                        "frame": 0x7FF800005000 + index * 0x1000, "start_ip": start_ip,
                        "method_hnd": md, "exception_clause_args": 0,
                        "ir_code_start": start_ip + header, "ir_code_size": 0x40,
                        "methoddesc_interpreter_code": start_ip,
                        "native_code_start": None, "native_code_size": None,
                        "native_code_addr": None, "range_kind": None, "ip2md_md": None,
                        "stop_symbol": "coreclr!InterpExecMethod", "bytecode_start_size": header,
                    })
                else:
                    native = 0x7FF9E5000000 + index * 0x1000 + (0x10 if target == "Touch" else 0)
                    event.update({
                        "stop_kind": "jit-native", "pc": native, "frame": None, "start_ip": None,
                        "method_hnd": None, "exception_clause_args": None,
                        "ir_code_start": None, "ir_code_size": None, "methoddesc_interpreter_code": None,
                        "native_code_start": native, "native_code_size": 0x30,
                        "native_code_addr": native, "range_kind": "observed-instructions-from-rip",
                        "ip2md_md": md, "stop_symbol": None, "bytecode_start_size": None,
                    })
                self.append_transcript(event)
                self.events.append(event)

    def write(self):
        host_path = self.root / "host.jsonl"
        transcript_path = self.root / "cdb-transcript.txt"
        events_path = self.root / "debugger-events.jsonl"
        host_path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in self.records),
                             encoding="utf-8", newline="\n")
        transcript_path.write_bytes(bytes(self.transcript))
        events_path.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in self.events),
                               encoding="utf-8", newline="\n")
        manifest = {
            "schema": "runeclr-grouped-method-witness/1", "host_run_id": RUN_ID,
            "host_pid": HOST_PID, "debugger_pid": DEBUGGER_PID, "debugger_target_pid": HOST_PID,
            "runtime_files": [{"path": str(self.runtime), "sha256": verify.sha256_file(self.runtime)}],
            "images": [{"path": str(image["path"]), "sha256": image["sha"]} for image in self.images.values()],
            "host_records_path": str(host_path), "transcript_path": str(transcript_path),
            "debugger_events_path": str(events_path), "exit_code": 0,
            "observer_config": {"sos": "sos.dll", "mode": "manual"},
            "layout": {"stage": "synthetic", "module_roots": ["images", "runtime"]},
            "host_records_sha256": verify.sha256_file(host_path),
            "transcript_sha256": verify.sha256_file(transcript_path),
            "debugger_events_sha256": verify.sha256_file(events_path),
        }
        for key in self.omit:
            manifest.pop(key, None)
        manifest.update(self.overrides)
        self.manifest_path = self.root / "manifest.json"
        self.manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                      encoding="utf-8", newline="\n")

    def event(self, target, group="A1"):
        for event in self.events:
            if event.get("target") == target and event.get("group") == group:
                return event
        raise KeyError((group, target))

    def record(self, target, group="A1"):
        for record in self.records:
            if record.get("phase") == "identity" and record.get("group") == group \
                    and str(record.get("declared_entry", "")).endswith("." + target):
                return record
        raise KeyError((group, target))

    def mark(self, kind, group="A1"):
        for record in self.records:
            if record.get("marker_kind") == kind and record.get("group") == group:
                return record
        raise KeyError((group, kind))


def run_verify(bundle):
    verifier = verify.Verifier(manifest_path=bundle.manifest_path, repo_dir=bundle.root / "tracked-source")
    verifier.run()
    return verify.build_report(verifier)


class ParserControlTests(unittest.TestCase):
    """Parser controls over hand-built images; they are not loaded or executed by any runtime."""

    def test_reads_mvid_module_and_methods(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.dll"
            build_image(path, FW_MVID, "Sample.Assembly", [(FRAMEWORK_TYPE, ["Initialize", "Touch"])])
            info = verify.parse_managed_image(path)
        self.assertEqual(info["mvid"], FW_MVID)
        self.assertEqual(info["module"], "Sample.Assembly")
        self.assertEqual(info["methods"][0x06000001]["name"], "Initialize")
        self.assertEqual(info["methods"][0x06000002]["name"], "Touch")
        self.assertEqual(info["methods"][0x06000001]["type"], FRAMEWORK_TYPE)

    def test_rejects_non_pe_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "text.dll"
            path.write_bytes(b"not a portable executable")
            with self.assertRaises(verify.ImageError):
                verify.parse_managed_image(path)

    def test_rejects_managed_pointer_without_cli_header(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "native.dll"
            build_image(path, FW_MVID, "Sample.Assembly", [(FRAMEWORK_TYPE, ["Initialize"])])
            data = bytearray(path.read_bytes())
            struct.pack_into("<II", data, 0x98 + 112 + 14 * 8, 0, 0)
            path.write_bytes(bytes(data))
            with self.assertRaises(verify.ImageError):
                verify.parse_managed_image(path)

    def test_missing_file_raises(self):
        with self.assertRaises(OSError):
            verify.parse_managed_image(Path("does-not-exist-verify-image.dll"))


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def bundle(self):
        return Bundle(self.root)

    def assertFails(self, bundle, needle):
        report = run_verify(bundle)
        self.assertFalse(report["verified"], "bundle unexpectedly verified")
        joined = "\n".join(report["failures"])
        self.assertIn(needle, joined, joined)
        return report

    def assertVerifies(self, bundle):
        report = run_verify(bundle)
        self.assertTrue(report["verified"], "\n".join(report["failures"]))
        return report

    def _replace_run_span(self, bundle, lines):
        event = bundle.event("Run")
        begin = len(bundle.transcript)
        bundle.transcript += "".join(line + "\n" for line in lines).encode("utf-8")
        event["transcript_begin_offset"] = begin
        event["transcript_end_offset"] = len(bundle.transcript)
        bundle.write()
        return event

    def test_lastevent_hit_breakpoint_is_accepted(self):
        bundle = self.bundle()
        event = bundle.event("Run")
        begin = len(bundle.transcript)
        bundle.transcript += (
            "0:000> Last event: 1e90.4768: Hit breakpoint 0\n"
            "0:000> GROUPED-WITNESS-HIT checkpoint_id=%s md=0x%x\n"
            "0:000> " % (event["checkpoint_id"], event["md_value"])).encode("utf-8")
        event["transcript_begin_offset"] = begin
        event["transcript_end_offset"] = len(bundle.transcript)
        bundle.write()
        self.assertVerifies(bundle)

    def test_lastevent_echo_only_is_rejected(self):
        bundle = self.bundle()
        event = bundle.event("Run")
        self._replace_run_span(bundle, [
            "0:000> .echo Last event: 1e90.4768: Hit breakpoint 0",
            "0:000> GROUPED-WITNESS-HIT checkpoint_id=%s md=0x%x" % (event["checkpoint_id"], event["md_value"])])
        self.assertFails(bundle, "transcript shows a real debugger stop")

    def test_lastevent_substring_is_rejected(self):
        bundle = self.bundle()
        event = bundle.event("Run")
        self._replace_run_span(bundle, [
            "0:000> note Last event: 1e90.4768: Hit breakpoint 0",
            "0:000> GROUPED-WITNESS-HIT checkpoint_id=%s md=0x%x" % (event["checkpoint_id"], event["md_value"])])
        self.assertFails(bundle, "transcript shows a real debugger stop")

    def test_lastevent_non_break_is_rejected(self):
        bundle = self.bundle()
        event = bundle.event("Run")
        self._replace_run_span(bundle, [
            "0:000> Last event: 1e90.4768: Exit process 1e90, code 0",
            "0:000> GROUPED-WITNESS-HIT checkpoint_id=%s md=0x%x" % (event["checkpoint_id"], event["md_value"])])
        self.assertFails(bundle, "transcript shows a real debugger stop")

    def test_lastevent_without_method_hit_is_rejected(self):
        bundle = self.bundle()
        self._replace_run_span(bundle, [
            "0:000> Last event: 1e90.4768: Hit breakpoint 0"])
        self.assertFails(bundle, "transcript hit is runtime output, not a command echo")

    def test_positive_bundle_verifies(self):
        bundle = self.bundle()
        report = self.assertVerifies(bundle)
        self.assertEqual(report["failures"], [])
        self.assertEqual(report["schema_extensions_required"], [])
        self.assertEqual(report["identity_source"], "host-methoddesc-chain")
        self.assertTrue(report["evidence_chain"])
        self.assertEqual(report["layout"], {"stage": "synthetic", "module_roots": ["images", "runtime"]})
        self.assertEqual(report["schema"], "runeclr-grouped-witness-verify/1")
        self.assertEqual(len(report["artifact_hashes"]), 3)
        self.assertTrue(report["limitations"])
        self.assertEqual(bundle.event("Run")["checkpoint_id"], bundle.event("Touch")["checkpoint_id"])

    def test_verifier_does_not_modify_host_records(self):
        bundle = self.bundle()
        before = verify.sha256_file(bundle.root / "host.jsonl")
        self.assertVerifies(bundle)
        self.assertEqual(verify.sha256_file(bundle.root / "host.jsonl"), before)

    def test_framework_events_carry_no_interpreter_field(self):
        bundle = self.bundle()
        self.assertIsNone(bundle.event("Initialize")["method_hnd"])
        self.assertIsNone(bundle.event("Touch")["method_hnd"])
        report = self.assertVerifies(bundle)
        self.assertFalse(any(value == "method_hnd" for value in report["failures"]))

    def test_host_verdict_flag_fails(self):
        bundle = self.bundle()
        bundle.records[0]["witness_verified"] = True
        bundle.write()
        self.assertFails(bundle, "host records never claim verified")

    def test_host_pid_mismatch_fails(self):
        bundle = self.bundle()
        bundle.records[0]["process_id"] = 9999
        bundle.write()
        self.assertFails(bundle, "host records process id matches the manifest")

    def test_identity_mvid_mismatch_fails(self):
        bundle = self.bundle()
        bundle.record("Initialize")["image_mvid"] = AB_MVID
        bundle.write()
        self.assertFails(bundle, "binds a staged image by MVID and SHA256")

    def test_identity_token_mismatch_fails(self):
        bundle = self.bundle()
        bundle.record("Initialize")["method_token"] = 0x06000009
        bundle.write()
        self.assertFails(bundle, "MethodDef token exists in the staged image")

    def test_declared_entry_mismatch_fails(self):
        bundle = self.bundle()
        bundle.record("Initialize")["declared_entry"] = "Initialize"
        bundle.write()
        self.assertFails(bundle, "declared entry matches the image")

    def test_identity_must_match_the_event_group(self):
        bundle = self.bundle()
        bundle.records = [record for record in bundle.records
                          if not (record.get("phase") == "identity" and record.get("group") == "B1"
                                  and str(record.get("declared_entry", "")).endswith(".Run"))]
        bundle.write()
        self.assertFails(bundle, "Run host identity for this group")

    def test_stale_group_identity_reuse_fails(self):
        bundle = self.bundle()
        for target in TARGETS:
            stale = bundle.record(target, "A1")
            current = bundle.record(target, "B1")
            current["method_handle"] = stale["method_handle"]
            current["alc_name"] = stale["alc_name"]
        for event in bundle.events:
            if event.get("group") != "B1":
                continue
            stale_md = bundle.record(event["target"], "A1")["method_handle"]
            event["md_value"] = stale_md
            if event.get("method_hnd") is not None:
                event["method_hnd"] = stale_md
            if event.get("ip2md_md") is not None:
                event["ip2md_md"] = stale_md
        bundle.rebuild_transcript()
        bundle.write()
        self.assertFails(bundle, "load context RuneCLR.Group.Framework:A11 belongs to one group")

    def test_event_method_desc_mismatch_fails(self):
        bundle = self.bundle()
        bundle.event("Run")["md_value"] = 0x7FF80000FFFF
        bundle.write()
        self.assertFails(bundle, "observed native MethodDesc equals the host MethodHandle.Value")

    def test_author_frame_chain_mismatch_fails(self):
        bundle = self.bundle()
        bundle.event("Run")["method_hnd"] = 0x7FF80000FFFF
        bundle.write()
        self.assertFails(bundle, "frame chain returns the host MethodDesc")

    def test_dac_token_mismatch_fails(self):
        bundle = self.bundle()
        bundle.event("Touch")["dac_token"] = 0x06000007
        bundle.write()
        self.assertFails(bundle, "DAC token equals the host MethodDef token")

    def test_alc_name_mismatch_fails(self):
        bundle = self.bundle()
        bundle.record("Run")["alc_name"] = "RuneCLR.Group.Framework:wrong"
        bundle.write()
        self.assertFails(bundle, "ALC name matches the role")

    def test_exception_resume_fails(self):
        bundle = self.bundle()
        bundle.event("Run")["exception_clause_args"] = 2
        bundle.write()
        self.assertFails(bundle, "r9 exception clause args == 0")

    def test_empty_ir_body_fails(self):
        bundle = self.bundle()
        bundle.event("OnFrameworkEvent")["ir_code_size"] = 0
        bundle.write()
        self.assertFails(bundle, "IR body is non-empty")

    def test_poison_interpreter_code_fails(self):
        bundle = self.bundle()
        bundle.event("Run")["methoddesc_interpreter_code"] = 1
        bundle.write()
        self.assertFails(bundle, "m_interpreterCode is live")

    def test_start_ip_mismatch_fails(self):
        bundle = self.bundle()
        bundle.event("Run")["start_ip"] = 0x7FF800003001
        bundle.write()
        self.assertFails(bundle, "startIp equals m_interpreterCode")

    def test_ir_offset_uses_the_measured_header_size(self):
        bundle = self.bundle()
        bundle.event("Run")["ir_code_start"] = bundle.event("Run")["start_ip"] + 8
        bundle.write()
        self.assertFails(bundle, "IR body starts at startIp + measured bytecode header")

    def test_missing_bytecode_header_size_fails_closed(self):
        bundle = self.bundle()
        bundle.event("Run")["bytecode_start_size"] = None
        bundle.write()
        report = self.assertFails(bundle, "field bytecode_start_size present")
        self.assertIn("bytecode_start_size", report["schema_extensions_required"])

    def test_native_pc_falsely_equal_to_ir_offset_fails(self):
        bundle = self.bundle()
        event = bundle.event("Run")
        event["pc"] = event["ir_code_start"]
        bundle.write()
        self.assertFails(bundle, "native stop pc is not an IR offset")

    def test_native_pc_inside_the_ir_buffer_fails(self):
        bundle = self.bundle()
        event = bundle.event("Run")
        event["pc"] = event["ir_code_start"] + 4
        bundle.write()
        self.assertFails(bundle, "native stop pc is outside the IR buffer")

    def test_author_stop_symbol_missing_fails_closed(self):
        bundle = self.bundle()
        bundle.event("Run")["stop_symbol"] = None
        bundle.write()
        report = self.assertFails(bundle, "field stop_symbol present")
        self.assertIn("stop_symbol", report["schema_extensions_required"])

    def test_author_stop_symbol_must_be_interp_exec_method(self):
        bundle = self.bundle()
        bundle.event("Run")["stop_symbol"] = "coreclr!InterpDoWork"
        bundle.write()
        self.assertFails(bundle, "stop is inside InterpExecMethod")

    def test_framework_pc_must_equal_native_code_addr(self):
        bundle = self.bundle()
        bundle.event("Initialize")["pc"] = bundle.event("Initialize")["native_code_addr"] + 0x10
        bundle.write()
        self.assertFails(bundle, "stop pc equals the DAC NativeCodeAddr")

    def test_framework_unknown_native_code_addr_fails(self):
        bundle = self.bundle()
        event = bundle.event("Touch")
        event["native_code_addr"] = 0
        event["pc"] = 0
        event["native_code_start"] = 0
        bundle.write()
        self.assertFails(bundle, "DAC NativeCodeAddr is known")

    def test_framework_range_kind_missing_fails_closed(self):
        bundle = self.bundle()
        bundle.event("Touch")["range_kind"] = None
        bundle.write()
        report = self.assertFails(bundle, "field range_kind present")
        self.assertIn("range_kind", report["schema_extensions_required"])

    def test_framework_range_kind_must_be_observed_instructions(self):
        bundle = self.bundle()
        bundle.event("Touch")["range_kind"] = "whole-method"
        bundle.write()
        self.assertFails(bundle, "range kind is observed instructions from the stop pc")

    def test_framework_observed_range_starts_at_the_stop_pc(self):
        bundle = self.bundle()
        event = bundle.event("Initialize")
        event["native_code_start"] = event["native_code_addr"] - 0x10
        bundle.write()
        self.assertFails(bundle, "observed range starts at the stop pc")

    def test_framework_ip2md_mismatch_fails(self):
        bundle = self.bundle()
        bundle.event("Initialize")["ip2md_md"] = 0x7FF80000FFFF
        bundle.write()
        self.assertFails(bundle, "ip2md returns the same MethodDesc")

    def test_module_mvid_claim_without_address_fails(self):
        bundle = self.bundle()
        event = bundle.event("Run")
        event["dac_module"] = None
        event["dac_module_mvid"] = AA_MVID
        bundle.write()
        report = self.assertFails(bundle, "MVID claim exists without an observed module address")
        self.assertIn("dac_module_mvid", report["schema_extensions_required"])

    def test_optional_dac_module_mvid_is_cross_checked(self):
        bundle = self.bundle()
        for event in bundle.events:
            role = ROLE_OF[event["target"]]
            key = "framework" if role == "framework" else ("author-a" if event["group"] == "A1" else "author-b")
            event["dac_module_mvid"] = bundle.images[key]["mvid"]
        bundle.write()
        self.assertVerifies(bundle)

    def test_wrong_dac_module_mvid_claim_fails(self):
        bundle = self.bundle()
        bundle.event("OnFrameworkEvent")["dac_module_mvid"] = FW_MVID
        bundle.write()
        self.assertFails(bundle, "claimed DAC module MVID equals the host MVID")

    def test_dac_module_address_must_be_stable_per_role(self):
        bundle = self.bundle()
        bundle.event("Touch")["dac_module"] = bundle.event("Initialize")["dac_module"] + 0x1000
        bundle.write()
        self.assertFails(bundle, "framework events share one DAC module address")

    def test_stop_kind_precode_fails(self):
        bundle = self.bundle()
        bundle.event("Run")["stop_kind"] = "precode-stub"
        bundle.write()
        self.assertFails(bundle, "stop kind is an execution stop")

    def test_missing_transcript_hit_fails(self):
        bundle = self.bundle()
        event = bundle.event("Run")
        event["transcript_begin_offset"] = 0
        event["transcript_end_offset"] = len(b"0:000> g\n")
        bundle.write()
        self.assertFails(bundle, "transcript hit is runtime output, not a command echo")

    def test_transcript_without_break_stop_fails(self):
        bundle = self.bundle()
        event = bundle.event("Touch")
        begin = len(bundle.transcript)
        bundle.transcript += ("GROUPED-WITNESS-HIT checkpoint_id=%s md=0x%x\n"
                              % (event["checkpoint_id"], event["md_value"])).encode("utf-8")
        event["transcript_begin_offset"] = begin
        event["transcript_end_offset"] = len(bundle.transcript)
        bundle.write()
        self.assertFails(bundle, "transcript shows a real debugger stop")

    def test_command_echo_only_span_fails_with_forged_md(self):
        bundle = self.bundle()
        event = bundle.event("Run")
        begin = len(bundle.transcript)
        bundle.transcript += (
            "0:000> .echo GROUPED-WITNESS-HIT checkpoint_id=%s md=0x%x\n"
            "(1f2c.3a10): Break instruction exception - code 80000003 (first chance)\n"
            % (event["checkpoint_id"], event["md_value"])).encode("utf-8")
        event["transcript_begin_offset"] = begin
        event["transcript_end_offset"] = len(bundle.transcript)
        bundle.write()
        self.assertFails(bundle, "transcript hit is runtime output, not a command echo")

    def test_framing_echo_with_genuine_hit_verifies(self):
        bundle = self.bundle()
        bundle.framing = True
        bundle.rebuild_transcript()
        bundle.write()
        self.assertVerifies(bundle)

    def test_transcript_hit_md_mismatch_fails(self):
        bundle = self.bundle()
        event = bundle.event("Run")
        begin = len(bundle.transcript)
        bundle.transcript += (
            "0:000> g\n"
            "(1f2c.3a10): Break instruction exception - code 80000003 (first chance)\n"
            "0:000> GROUPED-WITNESS-HIT checkpoint_id=%s md=0x%x\n"
            "0:000> " % (event["checkpoint_id"], event["md_value"] + 1)).encode("utf-8")
        event["transcript_begin_offset"] = begin
        event["transcript_end_offset"] = len(bundle.transcript)
        bundle.write()
        self.assertFails(bundle, "transcript hit MethodDesc matches")

    def test_missing_transcript_file_fails(self):
        bundle = self.bundle()
        bundle.overrides["transcript_path"] = str(bundle.root / "missing-transcript.txt")
        bundle.write()
        self.assertFails(bundle, "transcript exists")

    def test_missing_artifact_hash_fails_closed(self):
        bundle = self.bundle()
        bundle.omit = {"transcript_sha256"}
        bundle.write()
        report = self.assertFails(bundle, "manifest.transcript_sha256 binds transcript")
        self.assertIn("transcript_sha256", report["schema_extensions_required"])

    def test_missing_host_execution_marker_fails(self):
        bundle = self.bundle()
        bundle.records = [record for record in bundle.records
                          if record.get("marker_kind") != "author:witness-entry"]
        bundle.write()
        self.assertFails(bundle, "host execution marker present")

    def test_marker_before_checkpoint_fails(self):
        bundle = self.bundle()
        bundle.mark("author:witness-entry")["timestamp_utc"] = iso(0)
        bundle.write()
        self.assertFails(bundle, "marker follows the checkpoint publish")

    def test_marker_order_without_timestamps_fails_closed(self):
        bundle = self.bundle()
        for event in bundle.events:
            event.pop("checkpoint_created_utc", None)
        bundle.write()
        report = self.assertFails(bundle, "marker follows the checkpoint publish")
        self.assertIn("checkpoint_created_utc", report["schema_extensions_required"])

    def test_checkpoint_record_can_prove_marker_order(self):
        bundle = self.bundle()
        markers = [record for record in bundle.records if str(record.get("marker_kind", "")).startswith("author:")]
        others = [record for record in bundle.records if record not in markers]
        published = []
        for event in bundle.events:
            event.pop("checkpoint_created_utc", None)
            published.append({
                "schema": "runeclr-grouped-witness/1", "phase": "checkpoint", "marker_kind": "checkpoint-published",
                "run_id": RUN_ID, "process_id": HOST_PID, "group": event["group"],
                "group_ordinal": event["group_ordinal"], "checkpoint_id": event["checkpoint_id"],
                "method_handle": 0, "method_token": 0, "witness_verified": False, "timestamp_utc": iso(0),
            })
        bundle.records = others + published + markers
        bundle.write()
        self.assertVerifies(bundle)

    def test_duplicate_checkpoint_and_target_fails(self):
        bundle = self.bundle()
        bundle.events.append(dict(bundle.event("Run")))
        bundle.write()
        self.assertFails(bundle, "Run observed once")

    def test_same_checkpoint_for_two_phases_fails(self):
        bundle = self.bundle()
        bundle.event("OnFrameworkEvent")["checkpoint_id"] = bundle.event("Run")["checkpoint_id"]
        bundle.write()
        self.assertFails(bundle, "maps to one phase")

    def test_run_and_touch_must_share_the_before_author_checkpoint(self):
        bundle = self.bundle()
        bundle.event("Touch")["checkpoint_id"] = bundle.next_checkpoint()
        bundle.write()
        self.assertFails(bundle, "Run and Touch share the before-author checkpoint")

    def test_missing_target_in_one_group_fails(self):
        bundle = self.bundle()
        bundle.events = [event for event in bundle.events
                         if not (event.get("group") == "B1" and event.get("target") == "OnFrameworkEvent")]
        bundle.write()
        self.assertFails(bundle, "OnFrameworkEvent observed")

    def test_missing_event_field_is_reported_precisely(self):
        bundle = self.bundle()
        del bundle.event("Touch")["pc"]
        bundle.write()
        self.assertFails(bundle, "Touch field pc present")

    def test_metadata_only_without_events_fails(self):
        bundle = self.bundle()
        bundle.events = []
        bundle.write()
        self.assertFails(bundle, "debugger events non-empty")

    def test_cleanup_stop_only_fails(self):
        bundle = self.bundle()
        bundle.events = [{
            "checkpoint_id": RUN_ID + "-99", "phase": "before-cleanup", "group": "A1", "group_ordinal": 1,
            "target": None, "md_value": None, "stop_kind": None, "pc": None, "frame": None, "start_ip": None,
            "method_hnd": None, "exception_clause_args": None, "ir_code_start": None, "ir_code_size": None,
            "methoddesc_interpreter_code": None, "native_code_start": None, "native_code_size": None,
            "dac_token": None, "dac_module": None, "transcript_begin_offset": 0, "transcript_end_offset": 0,
            "diagnostic_error": None,
        }]
        bundle.write()
        self.assertFails(bundle, "Initialize observed")

    def test_event_verdict_flag_fails(self):
        bundle = self.bundle()
        bundle.event("Run")["verified"] = True
        bundle.write()
        self.assertFails(bundle, "events never carry a verdict flag")

    def test_event_host_pid_mismatch_fails(self):
        bundle = self.bundle()
        bundle.event("Run")["host_pid"] = 1111
        bundle.write()
        self.assertFails(bundle, "event host pid matches the manifest")

    def test_checkpoint_id_must_carry_the_host_run_id(self):
        bundle = self.bundle()
        bundle.event("Touch")["checkpoint_id"] = "aabbccdd-01"
        bundle.write()
        self.assertFails(bundle, "checkpoint id carries the host run id")

    def test_debugger_target_pid_is_reported_when_missing(self):
        bundle = self.bundle()
        bundle.omit = {"debugger_target_pid"}
        bundle.write()
        report = self.assertVerifies(bundle)
        self.assertIn("debugger_target_pid", report["schema_extensions_required"])

    def test_missing_layout_is_reported_without_blocking_identity(self):
        bundle = self.bundle()
        bundle.omit = {"layout"}
        bundle.write()
        report = self.assertVerifies(bundle)
        self.assertIn("layout", report["schema_extensions_required"])

    def test_cli_exit_code_is_not_zero_for_a_failed_bundle(self):
        import contextlib
        import io
        bundle = self.bundle()
        bundle.events = []
        bundle.write()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = verify.main(["--manifest", str(bundle.manifest_path)])
        self.assertEqual(code, 1)

    def test_cli_exit_code_is_zero_for_a_verified_bundle(self):
        import contextlib
        import io
        bundle = self.bundle()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = verify.main(["--manifest", str(bundle.manifest_path)])
        self.assertEqual(code, 0)


    def test_prompt_prefixed_hit_is_the_pipe_format(self):
        bundle = self.bundle()
        self.assertIn("0:000> GROUPED-WITNESS-HIT", bytes(bundle.transcript).decode("utf-8"))
        self.assertVerifies(bundle)

    def test_double_prompt_prefix_is_accepted(self):
        bundle = self.bundle()
        event = bundle.event("Run")
        begin = len(bundle.transcript)
        bundle.transcript += (
            "0:000> g\n"
            "(1f2c.3a10): Break instruction exception - code 80000003 (first chance)\n"
            "0:000> 0:000> GROUPED-WITNESS-HIT checkpoint_id=%s md=0x%x\n"
            "0:000> " % (event["checkpoint_id"], event["md_value"])).encode("utf-8")
        event["transcript_begin_offset"] = begin
        event["transcript_end_offset"] = len(bundle.transcript)
        bundle.write()
        self.assertVerifies(bundle)

    def test_byte_offsets_survive_multibyte_prefix(self):
        prefix = b"\xe2\x88\x9a\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e\xe2\x9c\x93 caf\xc3\xa9\n"
        self.assertGreater(len(prefix), len(prefix.decode("utf-8")))
        bundle = Bundle(self.root, preamble=prefix)
        self.assertVerifies(bundle)

    def test_character_offsets_after_multibyte_prefix_fail(self):
        prefix = b"\xe2\x88\x9a\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e\xe2\x9c\x93 caf\xc3\xa9\n"
        bundle = Bundle(self.root, preamble=prefix)
        shift = len(prefix) - len(prefix.decode("utf-8"))
        event = bundle.event("Run")
        event["transcript_begin_offset"] -= shift
        event["transcript_end_offset"] -= shift
        bundle.write()
        self.assertFails(bundle, "transcript hit")

    def test_invalid_utf8_transcript_fails_closed(self):
        bundle = self.bundle()
        event = bundle.event("Run")
        begin = len(bundle.transcript)
        bundle.transcript += b"0:000> g\n\xff\xfe GROUPED-WITNESS-HIT checkpoint_id=x md=0x1\n"
        event["transcript_begin_offset"] = begin
        event["transcript_end_offset"] = len(bundle.transcript)
        bundle.write()
        self.assertFails(bundle, "transcript is valid UTF-8")

    def test_native_code_addr_alias_is_accepted(self):
        bundle = self.bundle()
        for target in ("Initialize", "Touch"):
            event = bundle.event(target)
            event["dac_native_code_addr"] = event["native_code_addr"]
            event["native_code_addr"] = None
        bundle.write()
        self.assertVerifies(bundle)

    def test_alias_unknown_native_code_addr_still_fails(self):
        bundle = self.bundle()
        event = bundle.event("Touch")
        event["native_code_addr"] = None
        event["dac_native_code_addr"] = 0
        bundle.write()
        self.assertFails(bundle, "DAC NativeCodeAddr is known")

    def test_echo_named_program_output_is_not_evidence(self):
        bundle = self.bundle()
        event = bundle.event("Run")
        begin = len(bundle.transcript)
        bundle.transcript += (
            "0:000> g\n"
            "(1f2c.3a10): Break instruction exception - code 80000003 (first chance)\n"
            "0:000> SIZEOF-InterpByteCodeStart 0x8 GROUPED-WITNESS-HIT checkpoint_id=%s md=0x%x\n"
            % (event["checkpoint_id"], event["md_value"])).encode("utf-8")
        event["transcript_begin_offset"] = begin
        event["transcript_end_offset"] = len(bundle.transcript)
        bundle.write()
        self.assertFails(bundle, "transcript hit is runtime output, not a command echo")


    def test_sparse_present_table_bitmap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sparse.dll"
            build_image(path, FW_MVID, "Sparse.Assembly",
                        [(FRAMEWORK_TYPE, ["Initialize", "Touch"])], typerefs=3, fields=2, params=2)
            info = verify.parse_managed_image(path)
        self.assertEqual(info["mvid"], FW_MVID)
        self.assertEqual(info["module"], "Sparse.Assembly")
        self.assertEqual(len(info["methods"]), 2)
        self.assertEqual(info["methods"][0x06000001], {"name": "Initialize", "type": FRAMEWORK_TYPE})
        self.assertEqual(info["methods"][0x06000002]["name"], "Touch")

    def test_truncated_row_count_array_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "truncated-rows.dll"
            build_image(path, FW_MVID, "Sample.Assembly", [(FRAMEWORK_TYPE, ["Initialize"])], truncate_rows=1)
            with self.assertRaises(verify.ImageError) as ctx:
                verify.parse_managed_image(path)
        self.assertIn("row-count", str(ctx.exception))

    def test_truncated_table_rows_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "truncated-tables.dll"
            build_image(path, FW_MVID, "Sample.Assembly", [(FRAMEWORK_TYPE, ["Initialize"])],
                        truncate_tables=40)
            with self.assertRaises(verify.ImageError) as ctx:
                verify.parse_managed_image(path)
        self.assertIn("truncated", str(ctx.exception))

    def test_guid_index_out_of_range_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-guid.dll"
            build_image(path, FW_MVID, "Sample.Assembly", [(FRAMEWORK_TYPE, ["Initialize"])], mvid_index=0)
            with self.assertRaises(verify.ImageError) as ctx:
                verify.parse_managed_image(path)
        self.assertIn("#GUID", str(ctx.exception))


FIXTURES = (Path(__file__).resolve().parents[2] / "tests" / "RuneCLR.GroupedHost.Tests" / "bin"
            / "Release" / "net11.0" / "fixtures")


class RealImageTests(unittest.TestCase):
    """Identity checks against the real staged fixtures. Framework/contract pins are the SRM-derived
    values recorded by the host; author pins follow the current expected source shape (direct
    method-group callback at token 0x06000008) and superseded MVIDs are not reused."""

    def parse_fixture(self, relative):
        path = FIXTURES / relative
        if not path.is_file():
            self.skipTest("staged fixture is not present: " + str(path))
        return verify.parse_managed_image(path)

    def test_framework_image_identity(self):
        info = self.parse_fixture("framework/RuneCLR.GroupedHost.Framework.dll")
        self.assertEqual(info["mvid"], "55b4952e-4784-4ff6-b542-4cc936515ae2")
        self.assertEqual(info["module"], "RuneCLR.GroupedHost.Framework.dll")
        self.assertEqual(len(info["methods"]), 16)
        self.assertEqual(info["methods"][0x06000005], {"name": "Initialize", "type": FRAMEWORK_TYPE})
        self.assertEqual(info["methods"][0x06000007], {"name": "Touch", "type": FRAMEWORK_TYPE})

    def test_author_images_identity(self):
        # Current expected source shape: witness-only direct method-group callback, so
        # OnFrameworkEvent is void() at token 0x06000008 and Run stays at 0x06000007.
        # The old closure-shaped images (callback 0x06000009) are superseded; A/B MVIDs are
        # checked structurally and must be valid, distinct and different from the old pins.
        author_a = self.parse_fixture("author-a/RuneCLR.GroupedHost.Author.dll")
        author_b = self.parse_fixture("author-b/RuneCLR.GroupedHost.Author.dll")
        old_mvids = {"79832692-2181-4c66-9060-20b12cae1963", "b412c5d9-2780-45c6-bd7a-575968d55535"}
        for info in (author_a, author_b):
            self.assertRegex(info["mvid"], r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
            self.assertNotIn(info["mvid"], old_mvids)
            self.assertEqual(info["module"], "RuneCLR.GroupedHost.Author.dll")
            self.assertEqual(len(info["methods"]), 15)
            self.assertEqual(info["methods"][0x06000007], {"name": "Run", "type": AUTHOR_TYPE})
            self.assertEqual(info["methods"][0x06000008], {"name": "OnFrameworkEvent", "type": AUTHOR_TYPE})
            self.assertNotEqual(info["methods"][0x06000009]["name"], "OnFrameworkEvent")
        self.assertNotEqual(author_a["mvid"], author_b["mvid"])

    def test_contract_image_identity(self):
        info = self.parse_fixture("framework/RuneCLR.GroupedHost.Contracts.dll")
        self.assertEqual(info["mvid"], "1b94ceec-5661-479e-a966-d798acc879ac")
        self.assertEqual(info["module"], "RuneCLR.GroupedHost.Contracts.dll")
        self.assertEqual(len(info["methods"]), 5)



if __name__ == "__main__":
    unittest.main()
