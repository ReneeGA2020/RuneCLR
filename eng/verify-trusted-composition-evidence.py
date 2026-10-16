#!/usr/bin/env python3
"""Mutate measured composition evidence to check rejection of false proofs."""

import argparse
import copy
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


def load_report(directory, name):
    report = directory / (name + ".json")
    if report.exists():
        return json.loads(report.read_text(encoding="utf-8-sig"))
    text = (directory / (name + ".stdout")).read_text(encoding="utf-8-sig", errors="replace")
    start = text.find('{"Passed"')
    if start < 0:
        raise ValueError("No measured functional report: " + name)
    return json.JSONDecoder().raw_decode(text[start:])[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    directory = args.evidence.resolve()
    spec = importlib.util.spec_from_file_location(
        "composition_evidence", Path(__file__).with_name("trusted-composition-evidence.py"))
    evidence = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evidence)
    report = load_report(directory, "r2r-native")
    maps = json.loads((directory / "image-maps.json").read_text(encoding="utf-8-sig"))
    diagnostics = "\n".join((directory / ("r2r-native." + extension)).read_text(
        encoding="utf-8-sig", errors="replace") for extension in ("stdout", "stderr"))

    class RealEvidenceTests(unittest.TestCase):
        def lost_proof(self, witnesses, image_maps=maps):
            try:
                self.assertFalse(evidence.assess_witnesses(witnesses, image_maps)["passed"])
            except ValueError:
                pass

        def test_measured_positive_native_and_helper(self):
            self.assertTrue(report["Passed"])
            result = evidence.assess_witnesses(report["Witnesses"], maps)
            self.assertTrue(result["passed"])
            self.assertTrue(evidence.assess_interpreter(report, diagnostics)["passed"])
            for session in report["Sessions"]:
                for label in ("update", "private"):
                    self.assertTrue(any(match["label"] == label and
                        Path(match["image"]).parent == Path(session["Directory"])
                        for match in result["matches"]))

        def test_deleted_native_frames_do_not_pass(self):
            self.lost_proof([])

        def test_wrong_image_hash_does_not_pass(self):
            self.lost_proof(report["Witnesses"], {"0" * 64: next(iter(maps.values()))})

        def test_corrupt_pc_does_not_pass(self):
            witnesses = copy.deepcopy(report["Witnesses"])
            for witness in witnesses:
                witness["Pc"] = "0x123"
            self.lost_proof(witnesses)

        def test_nonexecutable_page_does_not_pass(self):
            witnesses = copy.deepcopy(report["Witnesses"])
            for witness in witnesses:
                witness["Executable"] = False
            self.lost_proof(witnesses)

        def test_wrong_selected_label_does_not_pass(self):
            witnesses = copy.deepcopy(report["Witnesses"])
            for witness in witnesses:
                if witness["Label"] == "host":
                    witness["Label"] = "unselected"
            self.lost_proof(witnesses)

        def test_shifted_method_ranges_do_not_pass(self):
            with tempfile.TemporaryDirectory() as temporary:
                altered = {}
                for index, (digest, path) in enumerate(maps.items()):
                    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
                    for i, line in enumerate(lines):
                        fields = line.split(",")
                        if fields[-1] == "MethodWithGCInfo":
                            fields[0] = hex(int(fields[0], 16) + 0x1000000)
                            lines[i] = ",".join(fields)
                    destination = Path(temporary) / (str(index) + ".csv")
                    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    altered[digest] = str(destination)
                self.lost_proof(report["Witnesses"], altered)

        def test_helper_precode_without_dump_does_not_pass(self):
            with self.assertRaises(ValueError):
                evidence.assess_interpreter(report, "Interpreter compile method: Compute")

        def test_helper_dump_without_called_interpreter_entry_does_not_pass(self):
            altered = copy.deepcopy(report)
            for session in altered["Sessions"]:
                for located in session["Entries"]:
                    if located["Entry"]["Method"] == "Compute":
                        located["Entry"]["PrecodeType"] = 3
            with self.assertRaises(ValueError):
                evidence.assess_interpreter(altered, diagnostics)

        def test_helper_without_checked_invocation_does_not_pass(self):
            altered = copy.deepcopy(report)
            for session in altered["Sessions"]:
                for located in session["Entries"]:
                    if located["Entry"]["Method"] == "Compute":
                        located["Entry"]["InvocationEvidence"] = ""
            with self.assertRaises(ValueError):
                evidence.assess_interpreter(altered, diagnostics)

    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RealEvidenceTests))
    print(stream.getvalue(), end="")
    print(json.dumps({"passed": result.wasSuccessful(), "tests": result.testsRun,
                      "evidence": str(directory)}))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
