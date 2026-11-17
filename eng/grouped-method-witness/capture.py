
"""External CDB capture runner for grouped method witnesses (orchestration).

Command text and transcript parsing live in cdb_commands.py (helper worker). This module owns
process I/O, checkpoint binding, the per-phase loop and raw event/manifest emission.

SOURCE-READY: nothing launches unless --run is used with a complete helper; --run refuses when
the helper is missing/incomplete. The runner never writes verified=true.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

CHECKPOINT_SCHEMA = "runeclr-grouped-checkpoint/1"
MANIFEST_SCHEMA = "runeclr-grouped-method-witness/1"
PHASES = ("before-framework", "before-author", "before-callback", "before-cleanup")
TARGET_BY_PHASE = {
    "before-framework": "FrameworkEntry.Initialize",
    "before-author": "AuthorEntry.Run",
    "before-callback": "AuthorEntry.OnFrameworkEvent",
}
TARGETS_BY_PHASE = {
    "before-framework": ("FrameworkEntry.Initialize",),
    "before-author": ("AuthorEntry.Run", "FrameworkEntry.Touch"),
    "before-callback": ("AuthorEntry.OnFrameworkEvent",),
    "before-cleanup": (),
}
PROMPT = re.compile(rb"\d+:\d+>[ ]*$")

class RunnerError(RuntimeError):
    pass

class PartialCapture(RunnerError):
    """Unknown/unsupported stop: the capture is partial, never verified."""

def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def load_helper(path: str | None):
    if not path:
        raise RunnerError("--helper is required (path to cdb_commands.py)")
    p = Path(path)
    if not p.exists():
        raise RunnerError("helper not found: %s" % p)
    spec = importlib.util.spec_from_file_location("cdb_commands", p)
    if spec is None or spec.loader is None:
        raise RunnerError("cannot load helper: %s" % p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    required = ("bootstrap_commands", "parse_layout", "framework_breakpoint_commands",
                "capture_jit_commands", "parse_jit_capture", "interp_breakpoint_command",
                "capture_interp_commands", "parse_interp_capture", "cleanup_commands")
    missing = [n for n in required if not hasattr(module, n)]
    if missing:
        raise RunnerError("helper API incomplete, missing: " + ", ".join(missing))
    return module

class CdbProcess:
    """Popen wrapper: byte pump + queue (prompt without newline is observable), watchdog, own-tree kill."""

    def __init__(self, argv, transcript: Path, stderr_path: Path, timeout_s: float,
                 env: dict | None = None, popen_factory=None):
        self.transcript = transcript
        self.deadline = time.monotonic() + timeout_s
        self.queue: "queue.Queue[bytes]" = queue.Queue()
        self.closed = threading.Event()
        self.timed_out = False
        creation = 0x08000000 if (os.name == "nt" and popen_factory is None) else 0
        factory = popen_factory or subprocess.Popen
        self._stderr = stderr_path.open("wb")
        self._log = transcript.open("wb")
        self.proc = factory(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._stderr,
                            creationflags=creation, env=env)
        self._reader_thread = threading.Thread(target=self._pump, daemon=True)
        self._watcher_thread = threading.Thread(target=self._watch, daemon=True)
        self._reader_thread.start()
        self._watcher_thread.start()

    def _pump(self):
        try:
            while not self.closed.is_set():
                reader = getattr(self.proc.stdout, "read1", self.proc.stdout.read)
                chunk = reader(4096)
                if not chunk or self.closed.is_set():
                    break
                self._log.write(chunk); self._log.flush(); self.queue.put(chunk)
        finally:
            self.closed.set()

    def _watch(self):
        while not self.closed.is_set():
            if time.monotonic() > self.deadline:
                self.timed_out = True
                self.kill_tree(); self.closed.set(); return
            time.sleep(0.05)

    def read_until(self, pattern: re.Pattern, timeout_s: float | None = None) -> bytes:
        buf = bytearray()
        end = time.monotonic() + (timeout_s if timeout_s is not None else self.remaining())
        while time.monotonic() < end:
            try:
                chunk = self.queue.get(timeout=max(0.01, min(0.2, end - time.monotonic())))
            except queue.Empty:
                if self.closed.is_set() and self.queue.empty():
                    break
                continue
            buf += chunk
            if pattern.search(bytes(buf)):
                return bytes(buf)
        if not pattern.search(bytes(buf)):
            if time.monotonic() >= self.deadline:
                self.timed_out = True
                self.kill_tree()
            raise RunnerError("debugger timeout while waiting for output")
        return bytes(buf)

    def send(self, command: str, timeout_s: float | None = None) -> bytes:
        if self.proc.poll() is not None:
            raise RunnerError("debugger already exited; cannot send: " + command)
        self.proc.stdin.write((command + "\n").encode("utf-8")); self.proc.stdin.flush()
        return self.read_until(PROMPT, timeout_s)

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def kill_tree(self):
        if self.proc.poll() is None and os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True)

    def close(self, grace_s: float = 10.0) -> int:
        try:
            if self.proc.poll() is None:
                try:
                    self.proc.stdin.write(b"q\n"); self.proc.stdin.flush()
                except Exception:
                    pass
                try:
                    self.proc.wait(timeout=grace_s)
                except subprocess.TimeoutExpired:
                    self.kill_tree(); self.proc.wait(timeout=grace_s)
        finally:
            self.closed.set()
            self._reader_thread.join(timeout=2.0)
            self._log.close()
            self._stderr.close()
        return self.proc.returncode if self.proc.returncode is not None else -1

    def transcript_bytes(self) -> bytes:
        try:
            return self.transcript.read_bytes()
        except Exception:
            return b""

class Capture:
    def __init__(self, args, session_factory=None):
        self.args = args
        self.out = Path(args.output).resolve()
        self.transcript = self.out / "cdb-transcript.txt"
        self.stderr_path = self.out / "cdb-stderr.txt"
        self.events_path = self.out / "debugger-events.jsonl"
        self.manifest_path = self.out / "manifest.json"
        self.helper = None
        self.session_factory = session_factory
        self.events: list[dict] = []
        self.run_id = None
        self.layout = {}
        self.target_exit_code = None
        self.completed = False
        self.hardware_recoveries = []

    # ---------- prerequisites ----------
    def validate(self):
        a = self.args
        for name in ("runtime_root", "runtimeconfig", "harness", "fixture", "cdb", "sos", "helper"):
            if not Path(getattr(a, name)).exists():
                raise RunnerError("missing prerequisite %s: %s" % (name, getattr(a, name)))
        self.helper = load_helper(a.helper)
        if getattr(a, "framework_hardware_fallback", False) or getattr(a, "framework_natural_hardware", False):
            required = ("code_probe_commands", "parse_code_probe", "code_address_inspection_commands",
                        "hardware_execute_breakpoint_commands")
            if any(not callable(getattr(self.helper, name, None)) for name in required):
                raise RunnerError("helper lacks hardware fallback APIs")
        if getattr(a, "framework_natural_hardware", False):
            required = ("framework_compile_breakpoint_commands", "capture_compile_commands", "parse_compile_stop")
            if any(not callable(getattr(self.helper, name, None)) for name in required):
                raise RunnerError("helper lacks natural compilation observation APIs")
        self.out.mkdir(parents=True, exist_ok=True)
        if not (Path(a.runtime_root) / "dotnet.exe").is_file():
            raise RunnerError("runtime-root has no dotnet.exe")
        if not 0 < a.timeout <= 600:
            raise RunnerError("timeout must be positive and at most 600 seconds")
        if sum(bool(getattr(a, name, False)) for name in ("diagnose_framework_interpreter",
                "framework_hardware_fallback", "framework_natural_hardware")) > 1:
            raise RunnerError("choose one framework observation route")

    def pinned_files(self) -> dict:
        a = self.args
        paths = [Path(a.runtimeconfig), Path(a.harness), Path(a.cdb), Path(a.sos),
                 Path(a.helper), Path(__file__)]
        paths += list(Path(a.harness).parent.glob("*.dll"))
        root = Path(a.runtime_root)
        paths += sorted(root.rglob("coreclr.dll")) + sorted(root.rglob("clrinterpreter.dll"))
        paths += sorted(root.rglob("System.Private.CoreLib.dll"))
        paths += sorted(root.rglob("clrjit.dll")) + sorted(root.rglob("coreclr.pdb"))
        paths += sorted(root.rglob("mscordaccore.dll")) + sorted(root.rglob("mscordbi.dll"))
        paths += [root / "dotnet.exe"]
        fixture = Path(a.fixture)
        if fixture.is_dir():
            paths += [p for p in sorted(fixture.rglob("*")) if p.is_file()]
        elif fixture.exists():
            paths.append(fixture)
        return {str(p.resolve()): sha256_path(p) for p in paths if p.is_file()}

    def runtime_version_hint(self):
        try:
            data = json.loads(Path(self.args.runtimeconfig).read_text(encoding="utf-8"))
            v = data.get("runtimeOptions", {}).get("framework", {}).get("version")
            if isinstance(v, str) and v:
                return v
        except Exception:
            pass
        return None

    def child_env(self) -> dict:
        env = dict(os.environ)
        for key in ("DOTNET_Interpreter", "COMPlus_Interpreter", "DOTNET_InterpMode", "COMPlus_InterpMode",
                    "DOTNET_RuneCLRInterpretCollectible", "COMPlus_RuneCLRInterpretCollectible",
                    "DOTNET_JitName", "COMPlus_JitName", "DOTNET_AltJit", "COMPlus_AltJit"):
            if env.get(key) not in (None, "", "0"):
                raise RunnerError("unexpected global interpreter selector: " + key)
        env["GROUPED_WITNESS_CDB"] = "1"
        env["GROUPED_WITNESS_JSONL"] = self.args.host_jsonl
        env["GROUPED_WITNESS_CHECKPOINT"] = self.args.checkpoint
        env["DOTNET_TieredCompilation"] = "0"
        env["DOTNET_TC_QuickJit"] = "0"
        env["DOTNET_TC_OnStackReplacement"] = "0"
        env["COMPlus_TieredCompilation"] = "0"
        return env

    # ---------- checkpoint ----------
    def read_checkpoint(self) -> dict:
        p = Path(self.args.checkpoint)
        if not p.exists():
            raise PartialCapture("checkpoint file missing at stop: %s" % p)
        try:
            cp = json.loads(p.read_text(encoding="utf-8"))
        except Exception as err:
            raise PartialCapture("checkpoint unreadable: %s" % err)
        if cp.get("schema") != CHECKPOINT_SCHEMA:
            raise PartialCapture("unexpected checkpoint schema: %r" % cp.get("schema"))
        for key in ("checkpoint_id", "run_id", "process_id", "group", "group_ordinal", "phase"):
            if key not in cp:
                raise PartialCapture("checkpoint missing field: " + key)
        if cp["phase"] not in PHASES:
            raise PartialCapture("checkpoint phase unsupported: %r" % cp["phase"])
        return cp

    def read_host_records(self) -> list[dict]:
        p = Path(self.args.host_jsonl)
        if not p.exists():
            raise PartialCapture("host records missing at stop: %s" % p)
        out = []
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                raise PartialCapture("host record is not valid JSON")
        if not out:
            raise PartialCapture("host records empty at stop")
        return out

    # ---------- identity binding ----------
    def bind(self, checkpoint: dict, records: list[dict], target_pid: int | None,
             target: str | None = None) -> tuple[dict, int]:
        run_id, pid = checkpoint["run_id"], checkpoint["process_id"]
        phase = checkpoint["phase"]
        same = [r for r in records if r.get("run_id") == run_id and r.get("process_id") == pid and
                r.get("group") == checkpoint["group"] and r.get("group_ordinal") == checkpoint["group_ordinal"]]
        if not same:
            raise PartialCapture("no identity record for run/process/group/ordinal")
        if target_pid is not None and pid != target_pid:
            raise PartialCapture("checkpoint process_id != debugger target pid")
        if phase == "before-cleanup":
            return same[-1], 0
        expected = target or TARGET_BY_PHASE[phase]
        matches = [r for r in same if r.get("phase") == "identity" and
                   str(r.get("declared_entry", "")).endswith(expected)]
        if len(matches) != 1:
            raise PartialCapture("identity not unique for %s: %d matches" % (expected, len(matches)))
        record = matches[0]
        for key in ("image_mvid", "method_token", "alc_name"):
            if not record.get(key):
                raise PartialCapture("identity record missing " + key)
        md = record.get("method_handle")
        if not isinstance(md, int) or md <= 0:
            raise PartialCapture("identity record has no positive method_handle")
        return record, md

    def helper_call(self, name, *a):
        try:
            return getattr(self.helper, name)(*a)
        except ValueError as err:
            raise PartialCapture("helper %s rejected the stop: %s" % (name, err))

    # ---------- events/manifest ----------
    def emit(self, checkpoint, record, event, begin, end):
        result = dict(event)
        result.update({
            "checkpoint_id": checkpoint.get("checkpoint_id"), "phase": checkpoint.get("phase"),
            "group": checkpoint.get("group"), "group_ordinal": checkpoint.get("group_ordinal"),
            "target": str(record.get("declared_entry", "")).rsplit(".", 1)[-1],
            "declared_entry": record.get("declared_entry"), "md_value": event.get("md_value"),
            "stop_kind": event.get("stop_kind"), "pc": event.get("pc"), "frame": event.get("frame"),
            "start_ip": event.get("start_ip"), "method_hnd": event.get("method_hnd"),
            "exception_clause_args": event.get("exception_clause_args"),
            "ir_code_start": event.get("ir_code_start"), "ir_code_size": event.get("ir_code_size"),
            "methoddesc_interpreter_code": event.get("methoddesc_interpreter_code"),
            "native_code_start": event.get("native_code_start"),
            "native_code_size": event.get("native_code_size"),
            "dac_token": event.get("dac_token"), "dac_module": event.get("dac_module"),
            "transcript_begin_offset": begin, "transcript_end_offset": end,
            "diagnostic_error": event.get("diagnostic_error"),
            "host_pid": record.get("process_id"), "host_run_id": record.get("run_id"),
            "checkpoint_created_utc": checkpoint.get("created_utc"),
        })
        result["native_code_addr"] = event.get("dac_native_code_addr")
        self.events.append(result)

    def write_events(self):
        with self.events_path.open("w", encoding="utf-8") as fh:
            for e in self.events:
                fh.write(json.dumps(e, sort_keys=True) + "\n")

    def write_manifest(self, before, after, target_pid, debugger_pid, exit_code):
        image_paths = {str(p.resolve()) for p in Path(self.args.fixture).rglob("*.dll")} if Path(self.args.fixture).is_dir() else {str(Path(self.args.fixture).resolve())}
        def digest(path):
            return sha256_path(Path(path)) if Path(path).is_file() else None
        manifest = {
            "schema": MANIFEST_SCHEMA, "host_run_id": self.run_id, "host_pid": target_pid,
            "debugger_pid": debugger_pid,
            "debugger_target_pid": target_pid,
            "runtime_files": [{"path": p, "sha256": h} for p, h in sorted(before.items()) if p not in image_paths],
            "images": [{"path": p, "sha256": h} for p, h in sorted(before.items()) if p in image_paths],
            "input_hashes_before": before, "input_hashes_after": after,
            "host_records_path": self.args.host_jsonl, "transcript_path": str(self.transcript),
            "debugger_events_path": str(self.events_path), "exit_code": exit_code,
            "host_records_sha256": digest(self.args.host_jsonl),
            "transcript_sha256": digest(self.transcript),
            "debugger_events_sha256": digest(self.events_path),
            "capture_complete": self.completed,
            "layout": self.layout,
            "observer_config": {"mode": "cdb-sos-external", "timeout_seconds": self.args.timeout,
                                "framework_interpreter_diagnostic": bool(getattr(self.args, "diagnose_framework_interpreter", False)),
                                "framework_hardware_fallback": bool(getattr(self.args, "framework_hardware_fallback", False)),
                                "framework_natural_hardware": bool(getattr(self.args, "framework_natural_hardware", False)),
                                "cdb_readonly_breakpoints": bool(getattr(self.args, "cdb_readonly_breakpoints", False)),
                                "hardware_recoveries": self.hardware_recoveries,
                                "tiering_disabled_in_child_env": True, "sos_path": self.args.sos,
                                "cdb_path": self.args.cdb, "helper_path": self.args.helper,
                                "checkpoint_schema": CHECKPOINT_SCHEMA,
                                "runtime_version_hint": self.runtime_version_hint()},
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # ---------- dry run ----------
    def dry_run(self) -> int:
        self.validate()
        text = "\n".join(self.helper.bootstrap_commands(self.args.runtime_root, self.args.sos))
        (self.out / "generated-bootstrap.txt").write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0

    # ---------- run ----------
    def make_session(self):
        argv = [str(Path(self.args.runtime_root) / "dotnet.exe"), "exec", "--runtimeconfig",
                self.args.runtimeconfig, self.args.harness] + list(getattr(self.args, "harness_args", []) or ["--method-witness-fixture"])
        if self.session_factory is not None:
            return self.session_factory(argv, self.transcript, self.stderr_path, self.args.timeout, self.child_env())
        cdb_options = ["-robp"] if getattr(self.args, "cdb_readonly_breakpoints", False) else []
        return CdbProcess([str(self.args.cdb)] + cdb_options + argv, self.transcript, self.stderr_path,
                          self.args.timeout, env=self.child_env())

    def _offset(self, session) -> int:
        try:
            return len(session.transcript_bytes())
        except Exception:
            return 0

    def _commands(self, session, commands):
        return "\n".join(session.send(cmd, self.args.timeout).decode("utf-8", "replace") for cmd in commands)

    @staticmethod
    def _exit_code(text):
        patterns = (r"Exit process[^\r\n]*?code\s+(?:0x)?([0-9a-f]+)",
                    r"exited with (?:exit )?code\s+(?:0x)?([0-9a-f]+)")
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return int(match.group(1), 16)
        return None

    def _advance(self, session):
        begin = self._offset(session)
        text = session.send("g", self.args.timeout).decode("utf-8", "replace")
        # .lastevent reports the actual target exit code even when CDB itself is still running.
        text += "\n" + session.send(".lastevent", self.args.timeout).decode("utf-8", "replace")
        return text, begin

    def _checkpoint_order(self, cp, previous, seen):
        if cp["checkpoint_id"] in seen:
            raise PartialCapture("checkpoint_id replayed")
        phase = PHASES.index(cp["phase"])
        if previous is None:
            if phase != 0:
                raise PartialCapture("first checkpoint is not before-framework")
        else:
            old_group = (previous["group"], previous["group_ordinal"])
            group = (cp["group"], cp["group_ordinal"])
            old_phase = PHASES.index(previous["phase"])
            if group == old_group:
                if phase != old_phase + 1:
                    raise PartialCapture("out-of-order checkpoint phase")
            elif old_phase != 3 or phase != 0 or cp["group_ordinal"] <= previous["group_ordinal"]:
                raise PartialCapture("invalid group transition")
        if self.run_id is not None and cp["run_id"] != self.run_id:
            raise PartialCapture("run_id changed within target process")
        self.run_id = cp["run_id"]

    def _capture_hit(self, session, text, begin, cp, identities, pending, layout):
        is_interp = bool(re.search(r"(?m)^(?:\s*\d+:\d+>)*\s*WITNESS-INTERP-HIT\s*$", text)) or "coreclr!InterpExecMethod" in text
        diagnostic = bool(getattr(self.args, "diagnose_framework_interpreter", False))
        if re.search(r"Unable to insert breakpoint|WaitForEvent failed", text, re.I):
            raise PartialCapture("debugger could not install the pending breakpoint; this is not a body hit")
        candidates = [name for name in pending if (diagnostic or name.startswith("AuthorEntry.")) == is_interp]
        if len(candidates) != 1:
            raise PartialCapture("unknown or ambiguous body stop in " + cp["phase"])
        name = candidates[0]
        record, md = identities[name]
        label = "GROUPED-WITNESS-HIT checkpoint_id=" + cp["checkpoint_id"] + " md=0x%x" % md
        captured = text
        if is_interp:
            captured += "\n" + self._commands(session, ["ln @rip"])
            captured += "\n" + self._commands(session, self.helper.capture_interp_commands(layout, md))
            event = self.helper_call("parse_interp_capture", captured, layout, md)
            symbol = re.search(r"\bcoreclr!InterpExecMethod(?:\+0x[0-9a-fA-F]+)?", captured)
            event["stop_symbol"] = symbol.group(0) if symbol else None
        else:
            captured += "\n" + self._commands(session, self.helper.capture_jit_commands(md))
            event = self.helper_call("parse_jit_capture", captured, md)
        if event.get("diagnostic_error"):
            raise PartialCapture(str(event["diagnostic_error"]))
        # Emit the correlation label only after the runtime-derived observation was parsed successfully.
        self._commands(session, [".echo " + label])
        self.emit(cp, record, event, begin, self._offset(session))
        pending.remove(name)

    def _recover_framework_breakpoint(self, session, text, cp, identities, pending, layout, compiled=None):
        """Inspect naturally compiled code, then arm hardware; this emits no body event."""
        if compiled is None and not re.search(r"exception[^\n]*code\s+e0444143\b", text, re.I):
            raise PartialCapture("hardware fallback requires a real CLR compilation-notification stop")
        names = [name for name in pending if name.startswith("FrameworkEntry.")]
        if len(names) != 1:
            raise PartialCapture("hardware fallback has no unique pending framework target")
        name = names[0]
        record, md = identities[name]
        if any(r["checkpoint_id"] == cp["checkpoint_id"] and r["target"] == name
               for r in self.hardware_recoveries):
            raise PartialCapture("hardware fallback already attempted for this target")
        self._commands(session, self.helper.cleanup_commands())
        probe = self._commands(session, self.helper.code_probe_commands(md, layout))
        values = self.helper_call("parse_code_probe", probe, layout, md)
        address = values.get("current_code_addr")
        interp_code = values.get("methoddesc_interpreter_code")
        if not isinstance(address, int) or address <= 1:
            raise PartialCapture("hardware fallback has no observed native code address")
        if interp_code not in (0, 1):
            raise PartialCapture("framework has interpreter code; refusing to arm hardware on possible IR")
        if values.get("dac_token") != record["method_token"]:
            raise PartialCapture("framework code probe token differs from host identity")
        if compiled is not None and (compiled.get("compiled_md") != md or compiled.get("compiled_code") != address):
            raise PartialCapture("natural compilation registers differ from the observed MethodDesc/code address")
        inspection = self._commands(session, self.helper.code_address_inspection_commands(address))
        observed = {int(value.replace("`", ""), 16) for value in re.findall(
            r"(?im)^(?:\s*\d+:\d+>)*\s*MethodDesc:\s*(?:0x)?([0-9a-f`]+)\s*$", inspection)}
        if observed != {md} or "Failed to request MethodData" in inspection:
            raise PartialCapture("code-address !ip2md does not independently resolve the framework MethodDesc")
        # A prior clear also removed interpreter breakpoints. Re-arm all pending author targets.
        for other in pending:
            if other.startswith("AuthorEntry."):
                rearmed = self._commands(session, [self.helper.interp_breakpoint_command(identities[other][1], layout)])
                if re.search(r"error|failed|unable|syntax", rearmed, re.I):
                    raise PartialCapture("author interpreter breakpoint could not be re-armed after recovery")
        armed = self._commands(session, self.helper.hardware_execute_breakpoint_commands(address) + ["bl"])
        if re.search(r"error|failed|unable|syntax", armed, re.I):
            raise PartialCapture("hardware execution breakpoint could not be armed")
        self.hardware_recoveries.append({"checkpoint_id": cp["checkpoint_id"], "target": name,
                                         "md_value": md, "code_addr": address,
                                         "interpreter_code": interp_code})

    def _capture_compile_stop(self, session, text, cp, identities, pending, layout):
        names = [name for name in pending if name.startswith("FrameworkEntry.")]
        if len(names) != 1:
            raise PartialCapture("natural compile stop has no unique pending framework target")
        md = identities[names[0]][1]
        captured = text + "\n" + self._commands(session, ["ln @rip"])
        captured += "\n" + self._commands(session, self.helper.capture_compile_commands())
        compiled = self.helper_call("parse_compile_stop", captured, md)
        self._recover_framework_breakpoint(session, text, cp, identities, pending, layout, compiled)

    def run(self) -> int:
        self.validate()
        if Path(self.args.host_jsonl).exists() or Path(self.args.checkpoint).exists():
            raise RunnerError("use fresh host-record and checkpoint paths for every capture")
        before = self.pinned_files()
        session = self.make_session()
        target_pid = None
        debugger_pid = getattr(session.proc, "pid", None)
        exit_code = -1
        failure = None
        try:
            session.read_until(PROMPT, self.args.timeout)
            boot = self._commands(session, self.helper.bootstrap_commands(self.args.runtime_root, self.args.sos))
            if not re.search(r"Breakpoint\s+\d+\s+hit[\s\S]*?coreclr!Assembly::ExecuteMainMethod", boot, re.I):
                raise PartialCapture("initialized runtime breakpoint not observed")
            pid_text = self._commands(session, ['.printf "WITNESS-TARGET-PID=%d\\n", @$tpid'])
            match = re.search(r"(?m)^WITNESS-TARGET-PID=(\d+)\s*$", pid_text)
            if not match:
                match = re.search(r"ProcessId:\s*(\d+)", boot)
            if not match:
                raise PartialCapture("debugger target PID not observed")
            target_pid = int(match.group(1))
            self._commands(session, ['.printf "WITNESS-GLOBAL-COLLECTIBLE=%d\\n", @@c++(coreclr!g_pConfig->runeCLRInterpretCollectible)'])
            blocks = {}
            current_type = None
            for command in self.helper.layout_probe_commands():
                if command.startswith("dt coreclr!"):
                    current_type = command.split("!")[-1]
                if current_type is None:
                    raise PartialCapture("unattributed PDB layout probe")
                blocks[current_type] = blocks.get(current_type, "") + "\n" + session.send(command).decode("utf-8", "replace")
            layout = self.helper_call("parse_layout", blocks)
            self.layout = layout
            self._commands(session, self.helper.cleanup_commands())
            self._commands(session, ["sxe epr"])
            last, seen, pending, identities = None, set(), set(), {}
            text, begin = self._advance(session)
            while True:
                code = self._exit_code(text)
                if code is not None:
                    exit_code = code
                    if pending or last is None or last["phase"] != "before-cleanup":
                        raise PartialCapture("target exited before all phases and targets completed")
                    transcript = session.transcript_bytes().decode("utf-8", "replace")
                    if code != 0 or "FIXTURE-ONLY identity/lifecycle gates PASS" not in transcript:
                        raise PartialCapture("target did not report successful fixture completion")
                    self.completed = True
                    break
                cp = self.read_checkpoint()
                if last is None or cp["checkpoint_id"] != last["checkpoint_id"]:
                    if pending:
                        raise PartialCapture("next checkpoint reached without targets: " + ", ".join(sorted(pending)))
                    self._checkpoint_order(cp, last, seen)
                    if cp["process_id"] != target_pid:
                        raise PartialCapture("checkpoint process_id != debugger target pid")
                    seen.add(cp["checkpoint_id"])
                    self._commands(session, self.helper.cleanup_commands())
                    records = self.read_host_records()
                    names = TARGETS_BY_PHASE[cp["phase"]]
                    diagnostic = bool(getattr(self.args, "diagnose_framework_interpreter", False))
                    if diagnostic:
                        names = ("FrameworkEntry.Initialize",) if cp["phase"] == "before-framework" else ()
                    identities = {name: self.bind(cp, records, target_pid, name) for name in names}
                    pending = set(identities)
                    for name, (_, md) in identities.items():
                        if name.startswith("FrameworkEntry.") and not diagnostic:
                            if getattr(self.args, "framework_natural_hardware", False):
                                commands = self.helper.framework_compile_breakpoint_commands(md)
                            else:
                                commands = self.helper.framework_breakpoint_commands(md)
                        else:
                            commands = [self.helper.interp_breakpoint_command(md, layout)]
                        self._commands(session, commands)
                    last = cp
                else:
                    if (getattr(self.args, "framework_natural_hardware", False) and
                            ("coreclr!DACNotifyCompilationFinished" in text or
                             re.search(r"(?m)^(?:\s*\d+:\d+>)*\s*WITNESS-COMPILE-READY\s*$", text))):
                        self._capture_compile_stop(session, text, cp, identities, pending, layout)
                        text, begin = self._advance(session)
                        continue
                    if (getattr(self.args, "framework_hardware_fallback", False) and
                            re.search(r"Unable to insert breakpoint", text, re.I)):
                        self._recover_framework_breakpoint(session, text, cp, identities, pending, layout)
                        text, begin = self._advance(session)
                        continue
                    # CLR debugger notifications can stop before a pending JIT breakpoint is bound.
                    if re.search(r"(?:exception.*code\s+|ExceptionCode:\s*)0?4242420\b", text, re.I):
                        text, begin = self._advance(session)
                        continue
                    if not pending:
                        raise PartialCapture("unexpected stop after all targets in this phase")
                    self._capture_hit(session, text, begin, cp, identities, pending, layout)
                text, begin = self._advance(session)
        except BaseException as error:
            failure = error
            if isinstance(error, PartialCapture):
                # Preserve the unexpected stop before the owned process is closed.
                # These reads are diagnostics only and never become witness events.
                try:
                    for command in (".echo GROUPED-WITNESS-FAILURE-DIAGNOSTICS", "r", "kb 0x28", ".exr -1", "!clrstack"):
                        session.send(command, min(10, self.args.timeout))
                except Exception:
                    pass
        finally:
            session.close()
            self.write_events()
            after = self.pinned_files()
            if after != before and failure is None:
                self.completed = False
                failure = PartialCapture("input hashes changed during capture")
            self.write_manifest(before, after, target_pid, debugger_pid, exit_code)
        if failure is not None:
            raise failure
        return 0 if self.completed else 4

def build_parser():
    ap = argparse.ArgumentParser(description="External CDB capture runner (orchestration)")
    ap.add_argument("--runtime-root", required=True)
    ap.add_argument("--runtimeconfig", required=True)
    ap.add_argument("--harness", required=True)
    ap.add_argument("--harness-args", nargs=argparse.REMAINDER, default=[])
    ap.add_argument("--fixture", required=True, help="staged fixture image or directory to pin")
    ap.add_argument("--cdb", required=True)
    ap.add_argument("--sos", required=True)
    ap.add_argument("--helper", required=True, help="path to cdb_commands.py")
    ap.add_argument("--output", required=True)
    ap.add_argument("--host-jsonl", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--diagnose-framework-interpreter", action="store_true",
                    help="diagnostic only: observe whether Initialize enters the interpreter; never a mixed-mode acceptance")
    ap.add_argument("--framework-hardware-fallback", action="store_true",
                    help="after a failed SOS software breakpoint, inspect natural code and arm a hardware execution breakpoint")
    ap.add_argument("--cdb-readonly-breakpoints", action="store_true",
                    help="pass CDB -robp to allow software breakpoints in read-only code pages")
    ap.add_argument("--framework-natural-hardware", action="store_true",
                    help="observe natural compilation at the runtime hook, then hardware-break at the actual framework entry")
    return ap

def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    cap = Capture(args)
    try:
        if args.run:
            return cap.run()
        return cap.dry_run()
    except PartialCapture as err:
        print("PARTIAL: " + str(err), file=sys.stderr); return 3
    except RunnerError as err:
        print("BLOCKED: " + str(err), file=sys.stderr); return 2

if __name__ == "__main__":
    sys.exit(main())
