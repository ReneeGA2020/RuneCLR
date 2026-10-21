#!/usr/bin/env python3
"""Portable offline tests for the generic-size replay path.

The tests build a synthetic retained root in a temporary directory. They never
run dotnet, crossgen, a host, author code, a product path, or a subprocess.
"""

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "eng" / "measure-trusted-game-generic-size.py"
FIXTURE = ROOT / "eng" / "trusted-game-generic-size"
ASSEMBLY = "TrustedGameGenericSize.dll"
SPEC = importlib.util.spec_from_file_location("measure_trusted_game_generic_size", DRIVER)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_metadata(mvid):
    version = b"v4.0.30319\0\0"
    root = bytearray(0x200)
    struct.pack_into("<IHHII", root, 0, 0x424A5342, 1, 1, 0, len(version))
    root[16 : 16 + len(version)] = version
    struct.pack_into("<HH", root, 28, 0, 2)
    struct.pack_into("<II", root, 32, 0x70, 40)
    root[40:44] = b"#~\0\0"
    struct.pack_into("<II", root, 44, 0x98, 16)
    root[52:60] = b"#GUID\0\0\0"
    struct.pack_into("<IBBBBQQ", root, 0x70, 0, 2, 0, 0, 1, 1, 0)
    struct.pack_into("<I", root, 0x88, 1)
    struct.pack_into("<HHHHH", root, 0x8C, 0, 0, 1, 0, 0)
    root[0x98 : 0x98 + 16] = mvid
    return bytes(root)


def make_pe(mvid, r2r):
    data = bytearray(0x1200)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    coff = 0x84
    struct.pack_into("<HHIIIHH", data, coff, 0x8664, 1, 0, 0, 0, 0xF0, 0x22)
    opt = coff + 20
    struct.pack_into("<H", data, opt, 0x20B)
    struct.pack_into("<I", data, opt + 4, 0x1000)
    struct.pack_into("<I", data, opt + 20, 0x2000)
    struct.pack_into("<Q", data, opt + 24, 0x140000000)
    struct.pack_into("<I", data, opt + 32, 0x1000)
    struct.pack_into("<I", data, opt + 36, 0x200)
    struct.pack_into("<I", data, opt + 56, 0x4000)
    struct.pack_into("<I", data, opt + 60, 0x200)
    struct.pack_into("<H", data, opt + 68, 3)
    struct.pack_into("<I", data, opt + 108, 16)
    struct.pack_into("<II", data, opt + 112 + 14 * 8, 0x2000, 0x48)
    struct.pack_into(
        "<8sIIIIIIHHI",
        data,
        opt + 0xF0,
        b".text\0\0\0",
        0x1000,
        0x2000,
        0x1000,
        0x200,
        0,
        0,
        0,
        0,
        0x60000020,
    )
    cor = 0x200
    struct.pack_into("<IHHIIII", data, cor, 72, 2, 5, 0x2100, 0x200, 1, 0)
    struct.pack_into("<II", data, cor + 64, 0x2400 if r2r else 0, 0x100 if r2r else 0)
    data[0x300 : 0x300 + 0x200] = make_metadata(mvid)
    if r2r:
        struct.pack_into("<IHHII", data, 0x600, 0x00525452, 31, 0, 0x4B, 1)
        struct.pack_into("<II", data, 0x610, 100, 0x2410)
    return bytes(data)


def canonical_rows():
    return [
        ("0x00001000", "12", "0", ".text", "Test_Cell_1<System___Canon>___ctor", "MethodWithGCInfo"),
        ("0x00001020", "5", "0", ".text", "Test_Cell_1<System___Canon>__Get", "MethodWithGCInfo"),
        ("0x00001030", "12", "0", ".text", "Test_Cell_1<System___Canon>__Set", "MethodWithGCInfo"),
        ("0x00001040", "21", "0", ".text", "Test_Ops__Relay<System___Canon>", "MethodWithGCInfo"),
    ]


def exact_value_rows(key):
    if key == "val1":
        return [
            ("0x00002000", "4", "0", ".text", "Test_Cell_1<Int32>___ctor", "MethodWithGCInfo"),
            ("0x00002010", "4", "0", ".text", "Test_Cell_1<Int32>__Get", "MethodWithGCInfo"),
            ("0x00002020", "4", "0", ".text", "Test_Cell_1<Int32>__Set", "MethodWithGCInfo"),
            ("0x00002030", "18", "0", ".text", "Test_Ops__Relay<Int32>", "MethodWithGCInfo"),
        ]
    if key != "val8":
        return []
    rows = []
    labels = ["UInt8", "Int16", "Int32", "Int64", "Single", "Double"]
    offset = 0x3000
    for label in labels:
        for length, suffix in ((4, "___ctor"), (5, "__Get"), (4, "__Set"), (19, None)):
            symbol = (
                "Test_Cell_1<" + label + ">" + suffix
                if suffix
                else "Test_Ops__Relay<" + label + ">"
            )
            rows.append((hex(offset), str(length), "0", ".text", symbol, "MethodWithGCInfo"))
            offset += 0x10
    blob_lengths = ((18, "___ctor"), (21, "__Get"), (18, "__Set"), (39, None))
    for length, suffix in blob_lengths:
        symbol = (
            "Test_Cell_1<Test_Blob>" + suffix
            if suffix
            else "Test_Ops__Relay<Test_Blob>"
        )
        rows.append((hex(offset), str(length), "0", ".text", symbol, "MethodWithGCInfo"))
        offset += 0x10
    return rows


def data_rows(key):
    if key == "baseline":
        return []
    if key == "ref1":
        return [
            ("0x00005000", "", "0", ".data", "Test_Ops__Relay<String>", "MethodFixupSignature")
        ]
    if key == "ref8":
        labels = [
            "String",
            "Object",
            "S_P_CoreLib_System_InvalidOperationException",
            "__Array<Int32>",
            "__Array<String>",
            "Test_RefA",
            "Test_RefB",
            "Test_RefC",
        ]
        return [
            ("0x00006000", "", "0", ".data", "Test_Ops__Relay<" + label + ">", "MethodFixupSignature")
            for label in labels
        ]
    if key == "val8":
        return [
            ("0x00007000", "", "0", ".data", "Test_Cell_1<S_P_CoreLib_System_Guid>", "TypeFixupSignature")
        ]
    return []


def write_maps(variant_dir, key):
    rows = canonical_rows() + exact_value_rows(key) + data_rows(key)
    csv_path = variant_dir / "r2r" / (Path(ASSEMBLY).stem + ".map.csv")
    lines = ["Rva,Length,Relocs,Section,Symbol,Node Type"]
    for row in rows:
        lines.append(",".join(row))
    write_text(csv_path, "\n".join(lines) + "\n")
    text_path = variant_dir / "r2r" / (Path(ASSEMBLY).stem + ".map")
    write_text(
        text_path,
        "Summary Info\n"
        "------------\n\n"
        "Node Type Statistics\n"
        "--------------------\n\n"
        "    LENGTH |   %FILE |    AVERAGE |  COUNT | NODETYPE\n"
        "-----------------------------------------------------\n"
        "      2612 |  12.754 |     2612.0 |      1 | CopiedMetadataBlobNode\n"
        "        50 |   0.244 |       12.5 |      4 | MethodWithGCInfo\n",
    )
    write_text(
        variant_dir / "r2r" / (Path(ASSEMBLY).stem + ".nodestats.csv"),
        "Node Type,Length\nCopiedMetadataBlobNode,2612\nMethodWithGCInfo,50\n",
    )
    return csv_path, text_path


def add_log(path, text):
    write_text(path, text)
    return {"bytes": path.stat().st_size, "sha256": sha_file(path)}


def build_retained_root(base):
    root = base / "retained"
    root.mkdir()
    variants = json.loads((FIXTURE / "variants.json").read_text(encoding="utf-8"))
    source = root / "source"
    source.mkdir()
    for name in (
        "Cell.cs",
        "Program.cs",
        "VariantRoot.cs",
        "TrustedGameGenericSize.csproj",
        "variants.json",
        "README.md",
    ):
        shutil.copy2(FIXTURE / name, source / name)
    write_text(source / "measure-trusted-game-generic-size.py", "# launch harness\n")
    source_pins = {}
    for path in sorted(source.iterdir()):
        source_pins[str(path)] = {"bytes": path.stat().st_size, "sha256": sha_file(path)}
    write_text(root / "source-pins.json", json.dumps(source_pins, indent=2, sort_keys=True) + "\n")
    write_text(root / "source-pins.run.json", json.dumps(source_pins, indent=2, sort_keys=True) + "\n")
    final_pins = {}
    for path in (DRIVER, FIXTURE / "Cell.cs", FIXTURE / "Program.cs", FIXTURE / "VariantRoot.cs",
                 FIXTURE / "TrustedGameGenericSize.csproj", FIXTURE / "variants.json", FIXTURE / "README.md"):
        final_pins[str(path)] = {"bytes": path.stat().st_size, "sha256": sha_file(path)}
    write_text(root / "source-pins.final.json", json.dumps(final_pins, indent=2, sort_keys=True) + "\n")

    commands = []
    for name, text in (("sdk-version", "test-sdk\n"), ("crossgen-version", "test-crossgen\n")):
        stdout = root / "logs" / (name + ".stdout.log")
        stderr = root / "logs" / (name + ".stderr.log")
        out_info = add_log(stdout, text)
        err_info = add_log(stderr, "")
        commands.append(
            {
                "name": name,
                "argv": ["test"],
                "cwd": str(root),
                "exitCode": 0,
                "stdout": str(stdout),
                "stderr": str(stderr),
                "stdoutSha256": out_info["sha256"],
                "stderrSha256": err_info["sha256"],
            }
        )

    parent_variants = []
    for variant in variants:
        key = variant["key"]
        variant_dir = root / "variants" / key
        il_dir = variant_dir / "il"
        r2r_dir = variant_dir / "r2r"
        il_dir.mkdir(parents=True)
        r2r_dir.mkdir(parents=True)
        mvid = hashlib.sha256(("mvid-" + key).encode("utf-8")).digest()[:16]
        il_path = il_dir / ASSEMBLY
        r2r_path = r2r_dir / ASSEMBLY
        write_bytes(il_path, make_pe(mvid, False))
        write_bytes(r2r_path, make_pe(mvid, True))
        write_text(il_dir / (Path(ASSEMBLY).stem + ".deps.json"), "{}\n")
        write_text(il_dir / (Path(ASSEMBLY).stem + ".runtimeconfig.json"), "{}\n")
        csv_path, text_path = write_maps(variant_dir, key)
        write_text(variant_dir / "crossgen.rsp", "--targetos:windows\n")
        for name, text in (
            ("build.stdout.log", "build\n"),
            ("build.stderr.log", ""),
            ("crossgen.stdout.log", "crossgen\n"),
            ("crossgen.stderr.log", ""),
        ):
            add_log(variant_dir / "logs" / name, text)
        for command_name in ("build", "crossgen"):
            stdout = variant_dir / "logs" / (command_name + ".stdout.log")
            stderr = variant_dir / "logs" / (command_name + ".stderr.log")
            commands.append(
                {
                    "name": command_name,
                    "argv": ["test"],
                    "cwd": str(root),
                    "exitCode": 0,
                    "stdout": str(stdout),
                    "stderr": str(stderr),
                    "stdoutSha256": sha_file(stdout),
                    "stderrSha256": sha_file(stderr),
                }
            )
        il_info = M.file_bytes(il_path)
        r2r_info = M.file_bytes(r2r_path)
        csv_info = M.file_bytes(csv_path)
        text_info = M.file_bytes(text_path)
        rsp_info = M.file_bytes(variant_dir / "crossgen.rsp")
        map_info = M.parse_map(csv_path, text_path, variant["instantiations"])
        parent_variant = {
            "variant": variant,
            "il": il_info,
            "r2r": r2r_info,
            "sidecars": [],
            "map": {
                "csvPath": str(csv_path),
                "csvBytes": csv_info["bytes"],
                "csvSha256": csv_info["sha256"],
                "textPath": str(text_path),
                "textBytes": text_info["bytes"],
                "textSha256": text_info["sha256"],
            },
            "pe": {"il": M.parse_pe(il_path), "r2r": M.parse_pe(r2r_path)},
            "mvidMatch": True,
            "crossgenRsp": {"path": str(variant_dir / "crossgen.rsp"), "sha256": rsp_info["sha256"]},
        }
        parent_variant["map"].update(map_info)
        parent_variants.append(parent_variant)

    write_text(root / "commands.json", json.dumps(commands, indent=2, sort_keys=True) + "\n")
    write_text(root / "results.failure.json", json.dumps({"status": "failed", "error": "'metadata'", "commands": []}, indent=2) + "\n")
    write_text(root / "references.json", json.dumps({"path": str(root / "framework"), "referenceCount": 0, "references": []}, indent=2) + "\n")
    write_text(root / "crossgen-files.json", "[]\n")
    parent = {
        "schema": 1,
        "status": "complete",
        "generatedAt": "2026-10-21T00:00:00+00:00",
        "output": str(root),
        "boundaries": {"managedBuilds": 5, "crossgenOutputs": 5},
        "inputs": {
            "sdk": {"path": "test-sdk", "version": "test", "sha256": "0" * 64},
            "runtime": {"path": "test-runtime", "branch": "test", "commit": "0" * 40, "clean": True},
            "crossgen2": {"path": "test-crossgen", "version": "test", "sha256": "0" * 64},
            "framework": {"path": "test-framework", "referenceCount": 0},
            "sourcePins": source_pins,
        },
        "variants": parent_variants,
        "harnessAfterRun": {"path": str(DRIVER), "sha256": sha_file(DRIVER), "bytes": DRIVER.stat().st_size},
    }
    write_text(root / "results.json", json.dumps(parent, indent=2, sort_keys=True) + "\n")
    return root


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = build_retained_root(self.base)
        self.out = self.base / "replay"

    def tearDown(self):
        self.temp.cleanup()

    def run_replay(self, output=None):
        output = output or self.out
        args = argparse.Namespace(replay_retained=str(self.root), output=str(output))
        stderr = io.StringIO()
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("subprocess.run")), \
             mock.patch.object(subprocess, "Popen", side_effect=AssertionError("subprocess.Popen")), \
             mock.patch.object(os, "system", side_effect=AssertionError("os.system")), \
             contextlib.redirect_stderr(stderr):
            code = M._replay_main(args)
        return code, stderr.getvalue()

    def test_success_is_offline_and_recomputes(self):
        code, error = self.run_replay()
        self.assertEqual(code, 0, error)
        result = json.loads((self.out / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(result["mode"], "offline-replay")
        self.assertEqual(result["boundaries"]["managedBuilds"], 0)
        self.assertEqual(result["boundaries"]["crossgenOutputs"], 0)
        self.assertEqual(result["boundaries"]["subprocessCalls"], 0)
        self.assertTrue(result["inputPins"]["unchanged"])
        self.assertEqual(result["correctedUnits"]["exactMethodNodeDeltaBytes"], 258)
        self.assertEqual(result["correctedUnits"]["exactMethodNodeDeltaEntries"], 24)
        self.assertFalse(result["correctedUnits"]["guidExactBodyObserved"])
        self.assertIn("24 method nodes", result["correctedUnits"]["note"])
        self.assertNotEqual(
            result["harness"]["launch"]["pinSha256"],
            result["harness"]["final"]["sha256"],
        )
        self.assertTrue(result["harness"]["launch"]["currentPath"])
        self.assertNotEqual(
            result["harness"]["launch"]["currentSha256"],
            result["harness"]["launch"]["pinSha256"],
        )
        self.assertFalse(result["harness"]["sourceImmutabilityClaim"])
        self.assertTrue(result["verification"]["allPassed"])
        self.assertEqual(
            sha_file(self.out / "parent-results.failure.json"),
            sha_file(self.root / "results.failure.json"),
        )
        self.assertEqual(
            result["parent"]["failureSha256"],
            sha_file(self.root / "results.failure.json"),
        )
        self.assertEqual(list(self.out.glob("*.dll")), [])
        self.assertFalse((self.out / "variants").exists())
        before = json.loads((self.out / "input-pins.before.json").read_text(encoding="utf-8"))
        after = json.loads((self.out / "input-pins.after.json").read_text(encoding="utf-8"))
        self.assertEqual(before["manifestSha256"], after["manifestSha256"])

    def test_wrong_image_hash_is_rejected_before_output(self):
        image = self.root / "variants" / "ref8" / "il" / ASSEMBLY
        data = bytearray(image.read_bytes())
        data[-1] ^= 0xFF
        image.write_bytes(data)
        code, error = self.run_replay()
        self.assertEqual(code, 1)
        self.assertIn("pin mismatch", error)
        self.assertFalse(self.out.exists())

    def test_wrong_map_hash_is_rejected_before_output(self):
        map_path = self.root / "variants" / "ref8" / "r2r" / (Path(ASSEMBLY).stem + ".map.csv")
        map_path.write_text(map_path.read_text(encoding="utf-8") + "0,1,0,.text,Test_X,Method\n", encoding="utf-8")
        code, error = self.run_replay()
        self.assertEqual(code, 1)
        self.assertIn("pin mismatch", error)
        self.assertFalse(self.out.exists())

    def test_wrong_log_hash_is_rejected_before_output(self):
        log_path = self.root / "variants" / "ref8" / "logs" / "build.stdout.log"
        log_path.write_text("changed\n", encoding="utf-8")
        code, error = self.run_replay()
        self.assertEqual(code, 1)
        self.assertIn("log pin mismatch", error)
        self.assertFalse(self.out.exists())

    def test_wrong_source_fixture_pin_is_rejected_before_output(self):
        fixture = self.root / "source" / "Cell.cs"
        fixture.write_text(fixture.read_text(encoding="utf-8") + "\n// changed\n", encoding="utf-8")
        code, error = self.run_replay()
        self.assertEqual(code, 1)
        self.assertIn("source fixture pin mismatch", error)
        self.assertFalse(self.out.exists())

    def test_malformed_input_is_rejected_before_output(self):
        (self.root / "results.json").write_text("{not-json", encoding="utf-8")
        code, error = self.run_replay()
        self.assertEqual(code, 1)
        self.assertIn("malformed", error)
        self.assertFalse(self.out.exists())

    def test_existing_output_is_refused_without_mutation(self):
        self.out.mkdir()
        marker = self.out / "marker.txt"
        marker.write_text("keep\n", encoding="utf-8")
        code, error = self.run_replay()
        self.assertEqual(code, 1)
        self.assertIn("already exists", error)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep\n")
        self.assertEqual([item.name for item in self.out.iterdir()], ["marker.txt"])

    def test_output_inside_input_is_refused(self):
        inside = self.root / "inside-replay"
        code, error = self.run_replay(inside)
        self.assertEqual(code, 1)
        self.assertIn("outside", error)
        self.assertFalse(inside.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
