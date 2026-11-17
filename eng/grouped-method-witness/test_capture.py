
"""Plain-python unit tests for capture.py orchestration using fake subprocesses (no debuggee)."""
import importlib.util
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("capture", HERE / "capture.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)

FAILS = []

def check(name, fn):
    try:
        fn()
        print("PASS " + name)
    except Exception as err:
        FAILS.append(name)
        print("FAIL " + name + " :: " + repr(err))

class FakeStdin:
    def __init__(self):
        self.written = []
    def write(self, data):
        self.written.append(data)
    def flush(self):
        pass

class FakeStdout:
    def __init__(self, chunks, never_end=False):
        self.chunks = list(chunks)
        self.never_end = never_end
    def read(self, n=1):
        if self.chunks:
            return self.chunks.pop(0)
        if self.never_end:
            time.sleep(0.02)
            return b"."
        return b""

class FakeProc:
    def __init__(self, chunks, never_end=False, exit_code=0):
        self.stdin = FakeStdin()
        self.stdout = FakeStdout(chunks, never_end)
        self.pid = 4242
        self.returncode = None
        self._exit = exit_code
    def poll(self):
        return self.returncode
    def wait(self, timeout=None):
        self.returncode = self._exit
        return self._exit

def make_session(tmp, chunks, never_end=False, timeout=1.0, env=None):
    holder = {}
    proc = FakeProc(chunks, never_end)
    def factory(argv, **kwargs):
        holder["argv"] = argv
        holder["kwargs"] = kwargs
        return proc
    sess = capture.CdbProcess(["cdb"], tmp / "t.txt", tmp / "e.txt", timeout, env=env, popen_factory=factory)
    return sess, holder

def test_prompt_without_newline(tmp):
    sess, _ = make_session(tmp, [b"0:000> "], timeout=2.0)
    out = sess.read_until(capture.PROMPT, timeout_s=2.0)
    assert b"0:000>" in out
    sess.close()

def test_never_prompt_deadline(tmp):
    sess, _ = make_session(tmp, [], never_end=True, timeout=0.3)
    start = time.monotonic()
    try:
        sess.read_until(capture.PROMPT, timeout_s=0.3)
        raise AssertionError("expected RunnerError")
    except capture.RunnerError:
        pass
    assert time.monotonic() - start < 3.0
    assert sess.timed_out is True
    sess.close()

def test_child_env_forwarded(tmp):
    env = {"GROUPED_WITNESS_CDB": "1", "GROUPED_WITNESS_JSONL": "h.jsonl",
           "GROUPED_WITNESS_CHECKPOINT": "c.json", "DOTNET_TieredCompilation": "0"}
    sess, holder = make_session(tmp, [b"0:000> "], timeout=1.0, env=env)
    assert holder["kwargs"]["env"] is env
    assert holder["kwargs"]["env"]["GROUPED_WITNESS_CHECKPOINT"] == "c.json"
    sess.close()

def test_checkpoint_pid_mismatch(tmp):
    args = type("A", (), {})()
    args.output = str(tmp)
    args.checkpoint = str(tmp / "cp.json")
    args.host_jsonl = str(tmp / "host.jsonl")
    cap = capture.Capture(args)
    (tmp / "cp.json").write_text(json.dumps({"schema": capture.CHECKPOINT_SCHEMA, "checkpoint_id": "c1",
        "run_id": "r1", "process_id": 999, "group": "author", "group_ordinal": 1, "phase": "before-author"}))
    (tmp / "host.jsonl").write_text(json.dumps({"run_id": "r1", "group": "author", "method_handle": 4096}) + "\n")
    cp = cap.read_checkpoint()
    try:
        cap.bind(cp, cap.read_host_records(), target_pid=1000)
        raise AssertionError("expected PartialCapture")
    except capture.PartialCapture:
        pass

def test_stale_checkpoint_schema(tmp):
    args = type("A", (), {})()
    args.output = str(tmp)
    args.checkpoint = str(tmp / "cp.json")
    args.host_jsonl = str(tmp / "host.jsonl")
    cap = capture.Capture(args)
    (tmp / "cp.json").write_text(json.dumps({"schema": "other/1"}))
    try:
        cap.read_checkpoint()
        raise AssertionError("expected PartialCapture")
    except capture.PartialCapture:
        pass

def main():
    import tempfile
    names = sorted(n for n in globals() if n.startswith("test_") and callable(globals()[n]))
    for name in names:
        fn = globals()[name]
        with tempfile.TemporaryDirectory() as d:
            check(name, lambda d=d, fn=fn: fn(Path(d)))
    print("FAILURES " + str(len(FAILS)))
    return 1 if FAILS else 0
if __name__ == "__main__":
    sys.exit(main())
