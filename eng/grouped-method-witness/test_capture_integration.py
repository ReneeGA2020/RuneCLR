"""State-machine controls using a fake debugger. These are not execution witnesses."""
import json
import tempfile
import types
import unittest
from unittest.mock import patch
from pathlib import Path

import capture
import verify as witness_verify


RUN = "f" * 32
NAMES = ("FrameworkEntry.Initialize", "FrameworkEntry.Touch", "AuthorEntry.Run", "AuthorEntry.OnFrameworkEvent")


class FakeHelper:
    def bootstrap_commands(self, root, sos):
        return ["bootstrap"]

    def layout_probe_commands(self):
        return ["dt coreclr!InterpMethodContextFrame"]

    def parse_layout(self, blocks):
        if "LAYOUT" not in blocks.get("InterpMethodContextFrame", ""):
            raise ValueError("layout probe was not captured")
        return {"start_ip_off": 8, "method_off": 0, "method_hnd_off": 0,
                "codesize_off": 40, "m_interp_code_off": 16, "bytecode_start_size": 8}

    def cleanup_commands(self):
        return ["clear-native", "clear-pending"]

    def framework_breakpoint_commands(self, md):
        return ["arm-jit %x" % md]

    def interp_breakpoint_command(self, md, layout):
        return "arm-interp %x" % md

    def capture_jit_commands(self, md):
        return ["query-jit %x" % md]

    def capture_interp_commands(self, layout, md):
        return ["query-interp %x" % md]

    def parse_jit_capture(self, text, expected_md):
        if "OBSERVED-JIT=%x" % expected_md not in text:
            raise ValueError("no actual JIT observation for expected MD")
        return {"md_value": expected_md, "pc": 0x9000 + expected_md, "stop_kind": "jit-native",
                "native_code_start": 0x9000 + expected_md, "native_code_size": 8,
                "ip2md_md": expected_md, "dac_token": 0x06000001, "dac_module": 0x5000}

    def parse_interp_capture(self, text, layout, expected_md):
        if "OBSERVED-INTERP=%x" % expected_md not in text:
            raise ValueError("no actual interpreter observation for expected MD")
        return {"md_value": expected_md, "method_hnd": expected_md, "pc": 0xABC0,
                "stop_kind": "interp-first-entry", "frame": 0x7000, "start_ip": 0x8000,
                "methoddesc_interpreter_code": 0x8000, "ir_code_start": 0x8008,
                "ir_code_size": 40, "bytecode_start_size": 8, "exception_clause_args": 0,
                "dac_token": 0x06000007, "dac_module": 0x6000}

    def code_probe_commands(self, md, layout):
        return ["probe-framework %x" % md]

    def parse_code_probe(self, text, layout, expected_md):
        if "PROBE-MD=%x" % expected_md not in text:
            raise ValueError("missing code probe")
        return {"current_code_addr": 0x9000 + expected_md, "methoddesc_interpreter_code": 0,
                "dac_token": 0x06000001 if expected_md % 0x100 == 0 else 0x06000002}

    def code_address_inspection_commands(self, address):
        return ["inspect-code %x" % address]

    def hardware_execute_breakpoint_commands(self, address):
        return ["arm-hardware %x" % address]

    def framework_compile_breakpoint_commands(self, md):
        return ["arm-compile %x" % md]

    def capture_compile_commands(self):
        return ["query-compile"]

    def parse_compile_stop(self, text, expected_md):
        if "COMPILEMD=%x" % expected_md not in text:
            raise ValueError("no actual natural compilation observation")
        return {"compiled_md": expected_md, "compiled_code": 0x9000 + expected_md,
                "execution_evidence": False}


class FakeDebugger:
    def __init__(self, owner, groups):
        self.owner = owner
        self.proc = types.SimpleNamespace(pid=9999, returncode=None)
        self.commands = []
        self.raw = bytearray()
        self.last_action = None
        self.last_hit = None
        self.closed_after_exit = False
        self.actions = []
        for group, ordinal in groups:
            base = 0x1000 + ordinal * 0x100
            for index, phase in enumerate(capture.PHASES):
                cp = {"schema": capture.CHECKPOINT_SCHEMA, "checkpoint_id": RUN + "-%02d" % (ordinal * 4 + index),
                      "run_id": RUN, "process_id": 4242, "group": group, "group_ordinal": ordinal,
                      "phase": phase, "created_utc": "2026-11-17T01:00:00.0000000+00:00"}
                self.actions.append(("checkpoint", cp))
                if index == 0:
                    self.actions.append(("jit", base))
                elif index == 1:
                    self.actions += [("interp", base + 16), ("jit", base + 8)]
                elif index == 2:
                    self.actions.append(("interp", base + 24))
        self.actions.append(("exit", 0))

    def output(self, text):
        data = (text + "\n0:000> ").encode()
        self.raw.extend(data)
        self.owner.transcript.write_bytes(self.raw)
        return data

    def read_until(self, pattern, timeout=None):
        return self.output("initial")

    def send(self, command, timeout=None):
        self.commands.append(command)
        self.raw.extend(("\n0:000> " + command + "\n").encode())
        if command == "bootstrap":
            return self.output("Breakpoint 0 hit\ncoreclr!Assembly::ExecuteMainMethod:\nProcessId: 4242")
        if command.startswith('.printf "WITNESS-TARGET-PID'):
            return self.output("WITNESS-TARGET-PID=4242")
        if command.startswith("dt coreclr!"):
            return self.output("LAYOUT")
        if command == "g":
            if not self.actions:
                raise capture.RunnerError("unexpected extra g")
            kind, value = self.actions.pop(0)
            self.last_action = kind
            if kind == "checkpoint":
                cp = value
                Path(self.owner.args.checkpoint).write_text(json.dumps(cp))
                self.write_identities(cp)
                return self.output("Break instruction exception - code 80000003\nKERNELBASE!DebugBreak:")
            if kind in ("jit", "interp"):
                self.last_hit = (kind, value)
                symbol = "coreclr!InterpExecMethod" if kind == "interp" else "FrameworkEntry"
                if kind == "interp" and getattr(self.owner.args, "fake_prompted_interp", False):
                    return self.output("Breakpoint 2 hit\n0:000> WITNESS-INTERP-HIT")
                return self.output("Breakpoint 2 hit\n" + symbol + ":")
            if kind == "compile":
                self.last_hit = (kind, value)
                return self.output("Breakpoint 2 hit\n0:000> WITNESS-COMPILE-READY")
            if kind == "unknown":
                self.last_hit = None
                return self.output("Breakpoint 99 hit\nUnknownBody:")
            if kind == "jit-failed":
                return self.output("CLR notification exception - code e0444143\n"
                                   "Unable to insert breakpoint 0, Win32 error 0n998\nWaitForEvent failed")
            if kind == "exit":
                self.exit_value = value
                if value == 0:
                    return self.output("FIXTURE-ONLY identity/lifecycle gates PASS (not a method witness)")
                return self.output("fixture failed")
        if command == ".lastevent":
            if self.last_action == "exit":
                return self.output("Last event: 1092.1: Exit process 4242, code %x" % self.exit_value)
            return self.output("Last event: breakpoint")
        if command == "ln @rip" and self.last_hit is not None:
            symbol = "DACNotifyCompilationFinished" if self.last_hit[0] == "compile" else "InterpExecMethod"
            return self.output("coreclr!" + symbol)
        if command == "query-compile":
            return self.output("COMPILEMD=%x" % self.last_hit[1])
        if command.startswith("query-"):
            requested_kind = "jit" if command.startswith("query-jit") else "interp"
            if self.last_hit is None or self.last_hit[0] != requested_kind:
                return self.output("no observation")
            return self.output("OBSERVED-%s=%x" % (requested_kind.upper(), self.last_hit[1]))
        if command.startswith("probe-framework "):
            return self.output("PROBE-MD=" + command.split()[-1])
        if command.startswith("inspect-code "):
            return self.output("0:000> MethodDesc: %x" % (int(command.split()[-1], 16) - 0x9000))
        return self.output("ok")

    def write_identities(self, cp):
        path = Path(self.owner.args.host_jsonl)
        if cp["phase"] != "before-framework":
            return
        with path.open("a", encoding="utf-8") as stream:
            for offset, name in enumerate(NAMES):
                role = "framework" if name.startswith("Framework") else "author"
                record = {"schema": "runeclr-grouped-witness/1", "phase": "identity", "run_id": RUN,
                          "process_id": 4242, "group": cp["group"], "group_ordinal": cp["group_ordinal"],
                          "declared_entry": "Fixture." + name, "role": role,
                          "image_mvid": "11111111-1111-1111-1111-111111111111", "method_token": 0x06000001 + offset,
                          "alc_name": "RuneCLR.Group." + role.title() + ":" + cp["group"],
                          "method_handle": 0x1000 + cp["group_ordinal"] * 0x100 + offset * 8,
                          "witness_verified": False}
                stream.write(json.dumps(record) + "\n")

    def transcript_bytes(self):
        return bytes(self.raw)

    def close(self):
        self.closed_after_exit = self.last_action == "exit"
        self.proc.returncode = 0
        return 0


class IntegrationTests(unittest.TestCase):
    def make_capture(self, folder, groups=(("A1", 1), ("B1", 2), ("A2", 3), ("recovered", 5))):
        root = Path(folder)
        args = types.SimpleNamespace(output=str(root), checkpoint=str(root / "checkpoint.json"),
                                     host_jsonl=str(root / "host.jsonl"), fixture=str(root / "fixtures"),
                                     runtime_root=folder, runtimeconfig=str(root / "cfg.json"),
                                     harness=str(root / "harness.dll"), harness_args=["--method-witness-fixture"],
                                     cdb="cdb", sos="sos", helper="helper", timeout=1)
        Path(args.fixture).mkdir()
        cap = capture.Capture(args)
        cap.validate = lambda: setattr(cap, "helper", FakeHelper())
        cap.pinned_files = lambda: {"input": "stable"}
        debugger = FakeDebugger(cap, groups)
        cap.make_session = lambda: debugger
        return cap, debugger

    def test_all_groups_and_dual_target_phase(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder)
            self.assertEqual(cap.run(), 0)
            self.assertEqual(len(cap.events), 16)
            self.assertEqual(debugger.commands.count("bootstrap"), 1)
            self.assertTrue(debugger.closed_after_exit)
            self.assertEqual({e["group"] for e in cap.events}, {"A1", "B1", "A2", "recovered"})
            self.assertEqual(len([e for e in cap.events if e["phase"] == "before-author"]), 8)
            self.assertTrue(all(e["transcript_begin_offset"] < e["transcript_end_offset"] for e in cap.events))
            self.assertFalse(any(e.get("witness_verified") for e in cap.events))
            for event in cap.events:
                span = debugger.transcript_bytes()[event["transcript_begin_offset"]:event["transcript_end_offset"]].decode()
                self.assertIn("GROUPED-WITNESS-HIT checkpoint_id=" + event["checkpoint_id"], span)
                match = witness_verify.HIT_RE.search(span)
                self.assertIsNotNone(match)
                self.assertEqual(match.group(1), event["checkpoint_id"])
                self.assertEqual(int(match.group(2), 16), event["md_value"])
            self.assertEqual(debugger.commands.count("clear-native"), 17)
            manifest = json.loads(cap.manifest_path.read_text())
            self.assertTrue(manifest["capture_complete"])
            self.assertEqual(manifest["host_run_id"], RUN)
            self.assertEqual(manifest["exit_code"], 0)

    def test_early_target_exit_is_not_debugger_success(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder)
            debugger.actions = [("exit", 0)]
            with self.assertRaises(capture.PartialCapture):
                cap.run()
            self.assertFalse(cap.completed)

    def test_nonzero_target_exit_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder, (("A1", 1),))
            debugger.actions[-1] = ("exit", 1)
            with self.assertRaises(capture.PartialCapture):
                cap.run()

    def test_missing_touch_does_not_pass_next_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder, (("A1", 1),))
            debugger.actions = [a for a in debugger.actions if a != ("jit", 0x1108)]
            with self.assertRaises(capture.PartialCapture):
                cap.run()

    def test_unknown_stop_does_not_create_a_hit(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder, (("A1", 1),))
            debugger.actions[1] = ("unknown", 0)
            with self.assertRaises(capture.PartialCapture):
                cap.run()
            self.assertEqual(cap.events, [])

    def test_input_drift_rejects_completed_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder, (("A1", 1),))
            values = iter(({"input": "first"}, {"input": "changed"}))
            cap.pinned_files = lambda: next(values)
            with self.assertRaises(capture.PartialCapture):
                cap.run()
            self.assertFalse(cap.completed)

    def test_callback_identity_cannot_replace_initialize(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder, (("A1", 1),))
            cp = debugger.actions[0][1]
            debugger.write_identities(cp)
            rows = cap.read_host_records()
            record, md = cap.bind(cp, rows, 4242)
            self.assertTrue(record["declared_entry"].endswith("FrameworkEntry.Initialize"))
            self.assertEqual(md, 0x1100)
            with self.assertRaises(capture.PartialCapture):
                cap.bind(cp, rows + [record], 4242)
            with self.assertRaises(capture.PartialCapture):
                cap.bind(cp, rows, 4243)

    def test_out_of_order_checkpoint_rejects(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder, (("A1", 1),))
            debugger.actions[2][1]["phase"] = "before-callback"
            with self.assertRaises(capture.PartialCapture):
                cap.run()

    def test_framework_interpreter_diagnostic_observes_only_initialize(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder)
            cap.args.diagnose_framework_interpreter = True
            actions = []
            for kind, value in debugger.actions:
                if kind == "jit" and value % 0x100 == 0:
                    actions.append(("interp", value))
                elif kind in ("checkpoint", "exit"):
                    actions.append((kind, value))
            debugger.actions = actions
            self.assertEqual(cap.run(), 0)
            self.assertEqual(len(cap.events), 4)
            self.assertTrue(all(e["target"] == "Initialize" and
                                e["stop_kind"] == "interp-first-entry" for e in cap.events))
            self.assertFalse(any(cmd.startswith("arm-jit") for cmd in debugger.commands))
            self.assertEqual(sum(cmd.startswith("arm-interp") for cmd in debugger.commands), 4)
            self.assertTrue(debugger.closed_after_exit)
            manifest = json.loads(cap.manifest_path.read_text())
            self.assertTrue(manifest["observer_config"]["framework_interpreter_diagnostic"])
            self.assertFalse(any(e.get("verified") for e in cap.events))

    def test_framework_diagnostic_missing_interpreter_hit_is_partial(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder, (("A1", 1),))
            cap.args.diagnose_framework_interpreter = True
            debugger.actions = [a for a in debugger.actions if a[0] in ("checkpoint", "exit")]
            with self.assertRaisesRegex(capture.PartialCapture, "next checkpoint reached without targets"):
                cap.run()
            self.assertEqual(cap.events, [])
            self.assertFalse(cap.completed)

    def test_breakpoint_install_failure_is_not_a_body_hit(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder, (("A1", 1),))
            cp = debugger.actions[0][1]
            debugger.write_identities(cp)
            identity = cap.bind(cp, cap.read_host_records(), 4242)
            pending = {"FrameworkEntry.Initialize"}
            with self.assertRaisesRegex(capture.PartialCapture, "could not install"):
                cap._capture_hit(debugger, "Unable to insert breakpoint 0\nWaitForEvent failed",
                                 0, cp, {"FrameworkEntry.Initialize": identity}, pending, {})
            self.assertEqual(cap.events, [])
            self.assertFalse(any("GROUPED-WITNESS-HIT" in cmd for cmd in debugger.commands))

    def test_hardware_fallback_still_requires_real_body_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder)
            cap.args.framework_hardware_fallback = True
            actions = []
            for kind, value in debugger.actions:
                if kind == "jit":
                    actions.append(("jit-failed", value))
                actions.append((kind, value))
            debugger.actions = actions
            self.assertEqual(cap.run(), 0)
            self.assertEqual(len(cap.events), 16)
            self.assertEqual(len(cap.hardware_recoveries), 8)
            self.assertEqual(sum(cmd.startswith("arm-hardware") for cmd in debugger.commands), 8)

    def test_hardware_probe_without_body_hit_never_creates_event(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder, (("A1", 1),))
            cap.args.framework_hardware_fallback = True
            debugger.actions[1] = ("jit-failed", 0x1100)
            with self.assertRaisesRegex(capture.PartialCapture, "next checkpoint reached without targets"):
                cap.run()
            self.assertEqual(len(cap.hardware_recoveries), 1)
            self.assertEqual(cap.events, [])

    def test_hardware_fallback_refuses_interpreter_pointer(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder, (("A1", 1),))
            cap.args.framework_hardware_fallback = True
            debugger.actions.insert(1, ("jit-failed", 0x1100))
            cap.helper = FakeHelper()
            cap.helper.parse_code_probe = lambda text, layout, md: {
                "current_code_addr": 0xa100, "methoddesc_interpreter_code": 0xa100, "dac_token": 0x06000001}
            cap.validate = lambda: None
            with self.assertRaisesRegex(capture.PartialCapture, "possible IR"):
                cap.run()
            self.assertEqual(cap.events, [])
            self.assertFalse(any(cmd.startswith("arm-hardware") for cmd in debugger.commands))

    def test_hardware_fallback_requires_notification_and_unique_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder, (("A1", 1),))
            cap.helper = FakeHelper()
            cp = debugger.actions[0][1]
            debugger.write_identities(cp)
            identities = {"FrameworkEntry.Initialize": cap.bind(cp, cap.read_host_records(), 4242)}
            pending = set(identities)
            with self.assertRaisesRegex(capture.PartialCapture, "real CLR"):
                cap._recover_framework_breakpoint(debugger, "Unable to insert breakpoint", cp, identities, pending, {})
            notification = "CLR notification exception - code e0444143\nUnable to insert breakpoint"
            cap._recover_framework_breakpoint(debugger, notification, cp, identities, pending, {})
            self.assertEqual(cap.events, [])
            with self.assertRaisesRegex(capture.PartialCapture, "already attempted"):
                cap._recover_framework_breakpoint(debugger, notification, cp, identities, pending, {})

    def test_hardware_fallback_rejects_wrong_token_and_ip2md(self):
        for wrong in ("token", "ip2md"):
            with self.subTest(wrong=wrong), tempfile.TemporaryDirectory() as folder:
                cap, debugger = self.make_capture(folder, (("A1", 1),))
                cap.args.framework_hardware_fallback = True
                cap.helper = FakeHelper()
                cap.validate = lambda: None
                debugger.actions.insert(1, ("jit-failed", 0x1100))
                if wrong == "token":
                    cap.helper.parse_code_probe = lambda text, layout, md: {
                        "current_code_addr": 0xa100, "methoddesc_interpreter_code": 0,
                        "dac_token": 0x0600ffff}
                else:
                    cap.helper.code_address_inspection_commands = lambda addr: ["inspect-code ffff"]
                with self.assertRaises(capture.PartialCapture):
                    cap.run()
                self.assertEqual(cap.events, [])
                self.assertFalse(any(cmd.startswith("arm-hardware") for cmd in debugger.commands))

    def test_readonly_breakpoint_option_applies_to_debugger_only(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder)
            cap.args.cdb_readonly_breakpoints = True
            with patch.object(capture, "CdbProcess", return_value=debugger) as constructor:
                capture.Capture.make_session(cap)
            argv = constructor.call_args.args[0]
            self.assertEqual(argv[:2], ["cdb", "-robp"])
            self.assertEqual(argv[2], str(Path(folder) / "dotnet.exe"))
            self.assertEqual(argv[-1], "--method-witness-fixture")
            self.assertNotIn("DOTNET_Interpreter", constructor.call_args.kwargs["env"])

    def test_natural_compile_then_hardware_observes_all_targets(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder)
            cap.args.framework_natural_hardware = True
            cap.args.fake_prompted_interp = True
            actions = []
            for kind, value in debugger.actions:
                if kind == "jit":
                    actions.append(("compile", value))
                actions.append((kind, value))
            debugger.actions = actions
            self.assertEqual(cap.run(), 0)
            self.assertEqual(len(cap.events), 16)
            self.assertEqual(len(cap.hardware_recoveries), 8)
            self.assertFalse(any(cmd.startswith("arm-jit") for cmd in debugger.commands))
            self.assertEqual(sum(cmd.startswith("arm-compile") for cmd in debugger.commands), 8)

    def test_natural_compile_observation_without_body_is_partial(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder, (("A1", 1),))
            cap.args.framework_natural_hardware = True
            debugger.actions[1] = ("compile", 0x1100)
            with self.assertRaisesRegex(capture.PartialCapture, "next checkpoint reached without targets"):
                cap.run()
            self.assertEqual(cap.events, [])

    def test_natural_compile_code_pointer_mismatch_refuses_arm(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, debugger = self.make_capture(folder, (("A1", 1),))
            cap.args.framework_natural_hardware = True
            debugger.actions.insert(1, ("compile", 0x1100))
            cap.helper = FakeHelper()
            cap.helper.parse_compile_stop = lambda text, md: {"compiled_md": md, "compiled_code": 0xBAD}
            cap.validate = lambda: None
            with self.assertRaisesRegex(capture.PartialCapture, "compilation registers differ"):
                cap.run()
            self.assertEqual(cap.events, [])
            self.assertFalse(any(cmd.startswith("arm-hardware") for cmd in debugger.commands))


if __name__ == "__main__":
    unittest.main()
