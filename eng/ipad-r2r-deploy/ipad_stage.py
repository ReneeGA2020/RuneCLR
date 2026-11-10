#!/usr/bin/env python3
"""Staged iPad deployment + durable receipts for RuneCLR R2R/IL experiments (v3).

Rules enforced here:
- Every external command runs through run_stage(): unique invocation dir, request.json
  (argv/cwd/env) written before spawn, real child pid/start/finish, stdout/stderr files,
  exit code, and an enforced --json-output outcome when required.
- A stage failure stops the caller. No success without durable evidence.
- Dry-run renders commands only; it never counts as signed/installed/generated.
- GUI signing is launched via Terminal. 'open' exit 0 means launched only; the
  signed state exists only after sign-collect sees a GUI receipt with exit 0.
- Tool binaries are overridable so behavioural self-tests use fake executables.
"""
import argparse
import datetime
import hashlib
import json
import os
import plistlib
import re
import shlex
import shutil
import struct
import subprocess
import sys
import time
import uuid
from pathlib import Path

NL = chr(10)
SECRET_RE = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|PRIVATE)", re.I)
READY_SCHEMES = ("runeclr.ipados.r2r.host-ready.v1", "runeclr.ipad.host-ready.v1")
PAYLOAD_SCHEMA = "runeclr.ipados.r2r.payload.v2"
RESULT_SCHEMA = "runeclr.ipados.r2r.result.v1"
GOLDENS = {"A": {"result": "216", "private": "100", "helper": "307"},
           "B": {"result": "216", "private": "200", "helper": "607"}}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def utc(when=None):
    when = when or datetime.datetime.now(datetime.timezone.utc)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(text):
    if not isinstance(text, str):
        return None
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def token_ok(value, name, limit=64):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise SystemExit("invalid " + name + ": " + repr(value))
    if any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for ch in value):
        raise SystemExit("invalid " + name + ": " + repr(value))
    return value


def safe_rel(name):
    if not isinstance(name, str) or not name or len(name) > 240:
        raise SystemExit("unsafe relative path: " + repr(name))
    if name.startswith("/") or "\\" in name or chr(0) in name:
        raise SystemExit("unsafe relative path: " + repr(name))
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise SystemExit("unsafe relative path: " + repr(name))
    return name


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def env_snapshot():
    return {key: value for key, value in os.environ.items() if not SECRET_RE.search(key)}


def walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item)


def nested_contains(value, needle):
    return any(needle == text or needle in text for text in walk_strings(value))


def load_plist_bytes(raw):
    for marker in (b"<?xml", b"bplist", b"<!DOCTYPE"):
        index = raw.find(marker)
        if index >= 0:
            return plistlib.loads(raw[index:])
    raise ValueError("no plist payload found")


def load_plist_file(path):
    return load_plist_bytes(Path(path).read_bytes())


def parse_dv(text):
    fields = {}
    authorities = []
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key == "Authority":
            authorities.append(value)
        elif key not in fields:
            fields[key] = value
    fields["authorities"] = authorities
    return fields


def macho_uuid(data):
    if len(data) < 32 or struct.unpack_from("<I", data, 0)[0] not in (0xFEEDFACF, 0xFEEDFACE):
        return None
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        if cmd == 0x1B and size >= 24:
            return data[off + 8:off + 24].hex()
        off += size
    return None


def macho_symbol(data, wanted):
    if len(data) < 32 or struct.unpack_from("<I", data, 0)[0] != 0xFEEDFACF:
        return None
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        if cmd == 0x2:
            symoff, nsyms, stroff, strsize = struct.unpack_from("<IIII", data, off + 8)
            for index in range(nsyms):
                n_strx, _n_type, n_sect, _n_desc, n_value = struct.unpack_from(
                    "<IBBhQ", data, symoff + index * 16)
                end = data.index(b"\x00", stroff + n_strx)
                if data[stroff + n_strx:end].decode("ascii", "replace") == wanted:
                    return {"symbol": wanted, "value": n_value, "section": n_sect}
        off += size
    return None


class Stage:
    def __init__(self, evidence, name):
        self.name = name
        stamp = utc().replace(":", "").replace("-", "")
        self.dir = Path(evidence) / name / (stamp + "-" + uuid.uuid4().hex[:8])
        if self.dir.exists():
            raise SystemExit("stage directory already exists: " + str(self.dir))
        self.dir.mkdir(parents=True)

    def path(self, name):
        return self.dir / name

    def write(self, name, payload):
        target = self.dir / name
        temporary = self.dir / (name + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + NL, encoding="utf-8")
        os.replace(temporary, target)
        return target

    def fail(self, message, extra=None):
        record = {"stage": self.name, "ok": False, "exitCode": 1, "error": message,
                  "finishedUtc": utc()}
        if extra:
            record.update(extra)
        if not self.path("request.json").exists():
            self.write("request.json", {"stage": self.name, "startedUtc": utc(), "argv": []})
        self.write("result.json", record)
        print(json.dumps({"ok": False, "stage": self.name, "error": message}))
        return 1


def run_stage(stage, argv, cwd=None, timeout=3600, extra=None, json_out=None,
              json_required=False, require_outcome=None, dry_run=False):
    """Run one child with durable request/process/streams/result records."""
    if stage.path("request.json").exists() or stage.path("result.json").exists():
        raise SystemExit("stage already used (repeat stage refused): " + str(stage.dir))
    argv = [str(item) for item in argv]
    started = utc()
    request = {"stage": stage.name, "argv": argv, "cwd": str(cwd or os.getcwd()),
               "env": env_snapshot(), "startedUtc": started, "dryRun": bool(dry_run),
               "jsonOut": str(json_out) if json_out else None}
    if extra:
        request.update(extra)
    stage.write("request.json", request)
    stdout = stage.path("stdout.log")
    stderr = stage.path("stderr.log")
    if dry_run:
        stdout.write_text("DRY-RUN: " + " ".join(argv) + NL, encoding="utf-8")
        stderr.write_text("", encoding="utf-8")
        result = {"stage": stage.name, "ok": True, "dryRun": True, "exitCode": 0, "childPid": None,
                  "startedUtc": started, "finishedUtc": utc(), "stdout": str(stdout),
                  "stderr": str(stderr), "jsonPath": str(json_out) if json_out else None}
        if extra:
            result.update(extra)
        stage.write("result.json", result)
        return True, result
    pid = None
    child_started = None
    timed_out = False
    began = time.time()
    try:
        with stdout.open("wb") as out, stderr.open("wb") as err:
            process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=err)
            pid = process.pid
            child_started = utc()
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                code = process.wait()
    except (OSError, ValueError) as error:
        stderr.write_text("spawn failed: " + str(error) + NL, encoding="utf-8")
        result = {"stage": stage.name, "ok": False, "exitCode": None, "childPid": None,
                  "spawnError": str(error), "startedUtc": started, "finishedUtc": utc(),
                  "stdout": str(stdout), "stderr": str(stderr)}
        if extra:
            result.update(extra)
        stage.write("result.json", result)
        return False, result
    finished = utc()
    detail = None
    json_path = Path(json_out) if json_out else None
    if json_path is not None and json_path.is_file():
        try:
            detail = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            detail = None
    outcome = None
    if isinstance(detail, dict) and isinstance(detail.get("info"), dict):
        outcome = detail["info"].get("outcome")
    result = {"stage": stage.name, "exitCode": code, "childPid": pid, "timedOut": timed_out,
              "dryRun": False, "startedUtc": started, "childStartedUtc": child_started,
              "finishedUtc": finished, "durationSeconds": round(time.time() - began, 3),
              "stdout": str(stdout), "stdoutSha256": sha(stdout),
              "stderr": str(stderr), "stderrSha256": sha(stderr),
              "jsonPath": str(json_path) if json_path else None,
              "jsonSha256": sha(json_path) if json_path and json_path.is_file() else None,
              "jsonOutcome": outcome}
    ok = code == 0 and not timed_out
    problems = []
    if timed_out:
        problems.append("child timed out after " + str(timeout) + "s")
    if ok and (json_out is not None and (json_required or require_outcome is not None)):
        if not (json_path.is_file() and isinstance(detail, dict)):
            ok = False
            problems.append("required --json-output receipt missing or unparsable")
        elif require_outcome is not None and outcome != require_outcome:
            ok = False
            problems.append("required outcome '" + str(require_outcome) + "' not observed (got "
                            + str(outcome) + ")")
    result["ok"] = ok
    if problems:
        result["error"] = "; ".join(problems)
    if extra:
        result.update(extra)
    stage.write("result.json", result)
    return ok, result

# ---------------------------------------------------------------- profile helpers

def profile_problems(profile, team, udid, bundle, now=None):
    """Validate a decoded provisioning-profile plist. Returns (problems, details)."""
    problems = []
    details = {}
    now = now or datetime.datetime.now(datetime.timezone.utc)
    teams = profile.get("TeamIdentifier") or []
    details["team"] = list(teams) if isinstance(teams, list) else teams
    if team and (not isinstance(teams, list) or list(teams) != [team]):
        problems.append("profile team mismatch: " + repr(teams))
    expiry = profile.get("ExpirationDate")
    if isinstance(expiry, datetime.datetime) and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=datetime.timezone.utc)
    details["expiry"] = str(expiry)
    if not isinstance(expiry, datetime.datetime):
        problems.append("profile expiry missing or invalid")
    elif expiry <= now:
        problems.append("profile expired at " + utc(expiry))
    devices = profile.get("ProvisionedDevices") or []
    details["deviceCount"] = len(devices)
    if udid and udid not in devices:
        problems.append("device UDID not provisioned in profile")
    ent = profile.get("Entitlements") or {}
    details["getTaskAllow"] = ent.get("get-task-allow")
    if ent.get("get-task-allow") is not True:
        problems.append("profile get-task-allow is not true")
    appid = ent.get("application-identifier")
    details["appIdentifier"] = appid
    if bundle:
        expected = (team + "." + bundle) if team else bundle
        if not appid:
            problems.append("profile application-identifier missing")
        elif not appid_covers(appid, expected):
            problems.append("profile application-identifier does not cover " + expected
                            + ": " + repr(appid))
    if team and ent.get("com.apple.developer.team-identifier") not in (None, team):
        problems.append("profile entitlement team-identifier mismatch: "
                        + repr(ent.get("com.apple.developer.team-identifier")))
    return problems, details


def appid_covers(appid, expected):
    if appid == expected:
        return True
    if appid.endswith(".*"):
        return expected.startswith(appid[:-1])
    return False


def signed_entitlement_problems(ent, team, bundle):
    problems = []
    expected = (team + "." + bundle) if team else bundle
    if ent.get("application-identifier") != expected:
        problems.append("signed entitlements application-identifier is not " + expected
                        + ": " + repr(ent.get("application-identifier")))
    if ent.get("get-task-allow") is not True:
        problems.append("signed entitlements get-task-allow is not true")
    if team and ent.get("com.apple.developer.team-identifier") not in (None, team):
        problems.append("signed entitlements team-identifier mismatch")
    return problems


# ---------------------------------------------------------------- bundle-verify

def entries_from_ready(ready):
    schema = ready.get("schema")
    if schema not in READY_SCHEMES:
        raise SystemExit("unsupported READY schema: " + repr(schema))
    if ready.get("signed") is not None and not isinstance(ready.get("signed"), bool):
        raise SystemExit("READY signed must be a boolean when present")
    bundle = token_ok(ready.get("bundleId"), "READY.bundleId")
    executable = safe_rel(ready.get("executable"))
    if "/" in executable:
        raise SystemExit("READY.executable must be a plain file name")
    managed = ready.get("managedEntry")
    if not isinstance(managed, dict):
        raise SystemExit("READY.managedEntry missing")
    assembly = safe_rel(managed.get("assembly"))
    assembly_sha = managed.get("sha256")
    if not isinstance(assembly_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", assembly_sha):
        raise SystemExit("READY.managedEntry.sha256 invalid")
    entries = {}
    if schema == "runeclr.ipados.r2r.host-ready.v1":
        inventory = ready.get("inventory")
        if not isinstance(inventory, dict):
            raise SystemExit("READY.inventory missing")
        inv_file = Path(str(inventory.get("file")))
        if not inv_file.is_absolute() or not inv_file.is_file():
            raise SystemExit("READY.inventory.file missing: " + str(inv_file))
        payload = read_json(inv_file)
        if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
            raise SystemExit("inventory entries missing")
        declared_digest = inventory.get("digest")
        if payload.get("digest") != declared_digest:
            raise SystemExit("inventory digest does not match READY")
        for entry in payload["entries"]:
            if not isinstance(entry, dict):
                raise SystemExit("inventory entry is not an object")
            rel = safe_rel(entry.get("path"))
            if rel in entries:
                raise SystemExit("duplicate inventory path: " + rel)
            if not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
                raise SystemExit("inventory sha256 invalid: " + rel)
            if not isinstance(entry.get("size"), int) or entry["size"] < 0:
                raise SystemExit("inventory size invalid: " + rel)
            entries[rel] = {"sha256": entry["sha256"], "size": entry["size"]}
        if inventory.get("files") != len(entries):
            raise SystemExit("READY.inventory.files does not match entries")
        digest = hashlib.sha256()
        for rel in sorted(entries):
            digest.update(rel.encode("utf-8") + b"\x00" + entries[rel]["sha256"].encode("ascii")
                          + b"\x00" + str(entries[rel]["size"]).encode("ascii") + b"\n")
        if digest.hexdigest() != declared_digest:
            raise SystemExit("recomputed inventory digest mismatch")
        if inventory.get("bytes") is not None and inventory["bytes"] != sum(v["size"] for v in entries.values()):
            raise SystemExit("READY.inventory.bytes does not match entries")
    else:
        files = ready.get("files")
        if not isinstance(files, dict) or not files:
            raise SystemExit("READY.files must be a non-empty per-file map")
        for rel, value in files.items():
            safe_rel(rel)
            if not isinstance(value, dict):
                raise SystemExit("READY.files value must be an object: " + rel)
            if not isinstance(value.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"]):
                raise SystemExit("READY.files sha256 invalid: " + rel)
            if not isinstance(value.get("size"), int) or value["size"] < 0:
                raise SystemExit("READY.files size invalid: " + rel)
            entries[rel] = {"sha256": value["sha256"], "size": value["size"]}
    count = ready.get("fileCount")
    if count is not None and count != len(entries):
        raise SystemExit("READY.fileCount does not match the inventory")
    if assembly not in entries:
        raise SystemExit("managed entry assembly is not in the inventory")
    if entries[assembly]["sha256"] != assembly_sha:
        raise SystemExit("managed entry assembly hash mismatch")
    if executable not in entries:
        raise SystemExit("READY.executable is not in the inventory")
    return bundle, executable, assembly, entries


def cmd_bundle_verify(args, ev):
    stage = Stage(ev, "bundle-verify")
    app = Path(args.app).resolve()
    ready_path = Path(args.ready).resolve() if args.ready else None
    if not app.is_dir():
        return stage.fail("app directory missing: " + str(app))
    if ready_path is None or not ready_path.is_file():
        return stage.fail("READY json missing")
    try:
        ready = read_json(ready_path)
        bundle, executable, assembly, entries = entries_from_ready(ready)
    except (SystemExit, ValueError, OSError) as error:
        return stage.fail("READY invalid: " + str(error))
    actual = {}
    for path in sorted(p for p in app.rglob("*") if p.is_file()):
        actual[path.relative_to(app).as_posix()] = {"sha256": sha(path), "size": path.stat().st_size}
    problems = []
    for rel in sorted(entries):
        if rel not in actual:
            problems.append("missing in app: " + rel)
        elif actual[rel] != entries[rel]:
            problems.append("hash/size mismatch: " + rel)
    for rel in sorted(set(actual) - set(entries)):
        problems.append("file not covered by READY: " + rel)
    try:
        info = load_plist_file(app / "Info.plist")
    except Exception as error:
        info = {}
        problems.append("app Info.plist unreadable: " + str(error))
    if info.get("CFBundleIdentifier") != bundle:
        problems.append("app CFBundleIdentifier does not match READY.bundleId")
    if info.get("CFBundleExecutable") != executable:
        problems.append("app CFBundleExecutable does not match READY.executable")
    if ready.get("signed") is True:
        problems.append("READY declares an already-signed app; sign-plan needs unsigned input")
    stage.write("request.json", {"stage": "bundle-verify", "argv": [], "startedUtc": utc(),
                                 "app": str(app), "ready": str(ready_path),
                                 "readySha256": sha(ready_path), "schema": ready.get("schema"),
                                 "bundleId": bundle, "executable": executable,
                                 "managedAssembly": assembly, "fileCount": len(entries)})
    stage.write("inventory.json", {rel: entries[rel] for rel in sorted(entries)})
    stage.write("result.json", {"stage": "bundle-verify", "ok": not problems,
                                "exitCode": 0 if not problems else 1,
                                "fileCount": len(entries), "problems": problems})
    print(json.dumps({"ok": not problems, "fileCount": len(entries), "problems": problems}))
    return 0 if not problems else 1


# ---------------------------------------------------------------- GUI signing

def gui_script_common(q, dst, log, receipt):
    return [
        "#!/bin/bash",
        "set -Eeuo pipefail",
        "umask 022",
        "DST=" + q(dst),
        "LOG=" + q(log),
        "RECEIPT=" + q(receipt),
        "START=$(date -u +%Y-%m-%dT%H:%M:%SZ)",
        "finish() { code=$?; END=$(date -u +%Y-%m-%dT%H:%M:%SZ);"
        " printf '{\"stage\":\"gui-sign\",\"exit\":%s,\"status\":\"%s\",\"startedUtc\":\"%s\",\"finishedUtc\":\"%s\"}\\n'"
        " \"$code\" \"$([ \"$code\" -eq 0 ] && echo signed || echo failed)\" \"$START\" \"$END\""
        " > \"$RECEIPT.tmp\"; mv \"$RECEIPT.tmp\" \"$RECEIPT\"; }",
        "trap finish EXIT",
        "exec >> \"$LOG\" 2>&1",
        "echo \"gui-sign started $START\"",
    ]


def cmd_sign_plan(args, ev):
    stage = Stage(ev, "sign-plan")
    q = shlex.quote
    src = Path(args.app).resolve()
    sign_dir = Path(args.sign_dir).resolve()
    dst = sign_dir / src.name
    profile = Path(args.profile).resolve()
    if not src.is_dir() or not profile.is_file():
        return stage.fail("app or profile missing")
    if dst.exists():
        return stage.fail("signed destination already exists (refusing to delete): " + str(dst))
    try:
        safe_rel(args.executable)
    except SystemExit as error:
        return stage.fail(str(error))
    if "/" in args.executable or not (src / args.executable).is_file():
        return stage.fail("executable not found in app: " + repr(args.executable))
    if not args.team or not args.bundle or not args.identity or not args.udid:
        return stage.fail("--team, --bundle, --udid and --identity are required")
    if not args.dry_run:
        ok, preflight = run_stage(Stage(ev, "sign-plan-profile"),
                                  [args.security_bin, "cms", "-D", "-i", str(profile)],
                                  extra={"profile": str(profile)})
        if not ok:
            return stage.fail("profile decode failed before GUI launch")
        try:
            decoded = load_plist_bytes(Path(preflight["stdout"]).read_bytes())
        except Exception as error:
            return stage.fail("profile plist decode failed: " + str(error))
        problems, _details = profile_problems(decoded, args.team, args.udid, args.bundle)
        if problems:
            return stage.fail("profile preflight failed: " + "; ".join(problems))
    if not args.dry_run:
        sign_dir.mkdir(parents=True, exist_ok=True)
    script = sign_dir / ("sign-primary-" + uuid.uuid4().hex[:8] + ".command")
    log = sign_dir / "sign.log"
    receipt = sign_dir / "sign-receipt.json"
    ent = sign_dir / "entitlements.plist"
    payload_script = sign_dir / "make-entitlements.py"
    if script.exists() or log.exists() or receipt.exists():
        return stage.fail("GUI signing files already exist; use a fresh sign dir")
    if not args.dry_run:
        payload_script.write_text(ENTITLEMENT_HELPER.replace("@@TEAM@@", args.team).replace(
            "@@BUNDLE@@", args.bundle), encoding="utf-8")
    body = NL.join(gui_script_common(q, str(dst), str(log), str(receipt)) + [
        "[ -e \"$DST\" ] && { echo 'destination appeared; refusing' >&2; exit 3; }",
        "SRC=" + q(str(src)),
        "PROFILE=" + q(str(profile)),
        "ENT=" + q(str(ent)),
        "ditto \"$SRC\" \"$DST\"",
        "cp \"$PROFILE\" \"$DST/embedded.mobileprovision\"",
        q(args.security_bin) + " cms -D -i \"$PROFILE\" > \"$ENT.profile.plist\"",
        q(args.plutil_bin) + " -extract Entitlements xml1 -o \"$ENT.profile-ent.plist\" \"$ENT.profile.plist\"",
        q(args.python_bin) + " " + q(str(payload_script)) + " \"$ENT.profile-ent.plist\" \"$ENT\"",
        "echo 'signing nested code'",
        "find \"$DST\" -type f \\( -name '*.dylib' -o \\( -path '*/Frameworks/*' -perm -111 \\) \\) -print0"
        " | while IFS= read -r -d '' f; do " + q(args.codesign_bin) + " --force --sign "
        + q(args.identity) + " --timestamp=none \"$f\"; done",
        "echo 'signing main executable'",
        q(args.codesign_bin) + " --force --sign " + q(args.identity)
        + " --timestamp=none --entitlements \"$ENT\" --generate-entitlement-der \"$DST/"
        + args.executable + "\"",
        "echo 'signing bundle'",
        q(args.codesign_bin) + " --force --sign " + q(args.identity)
        + " --timestamp=none --entitlements \"$ENT\" --generate-entitlement-der \"$DST\"",
        "echo 'verifying nested signatures'",
        q(args.codesign_bin) + " --verify --deep --strict --verbose=2 \"$DST\"",
        "echo 'gui-sign complete'",
    ]) + NL
    before = {p.relative_to(src).as_posix(): sha(p) for p in sorted(src.rglob("*")) if p.is_file()}
    stage.write("input-hashes.json", before)
    if not args.dry_run:
        script.write_text(body, encoding="utf-8")
        script.chmod(0o755)
        (sign_dir / "input-hashes.json").write_text(json.dumps(before, indent=2) + NL, encoding="utf-8")
    stage.write("request.json", {"stage": "sign-plan", "argv": [], "startedUtc": utc(),
                                 "app": str(src), "signDir": str(sign_dir), "target": str(dst),
                                 "script": str(script), "profile": str(profile),
                                 "profileSha256": sha(profile), "identity": args.identity,
                                 "team": args.team, "bundle": args.bundle,
                                 "executable": args.executable, "inputFiles": len(before),
                                 "dryRun": bool(args.dry_run)})
    if args.dry_run:
        rendered = stage.path("script.rendered.sh")
        rendered.write_text(body, encoding="utf-8")
        stage.write("result.json", {"stage": "sign-plan", "ok": True, "dryRun": True,
                                    "exitCode": 0, "status": "RENDERED_ONLY",
                                    "script": str(rendered)})
        print(json.dumps({"ok": True, "dryRun": True, "status": "RENDERED_ONLY", "script": str(rendered)}))
        return 0
    ok, launch = run_stage(Stage(ev, "sign-launch"), [args.open_bin, "-a", "Terminal", str(script)],
                           extra={"script": str(script),
                                  "note": "open exit 0 = launched only; signing is proven by sign-collect"})
    stage.write("result.json", {"stage": "sign-plan", "ok": ok, "exitCode": 0 if ok else 1,
                                "launched": ok, "status": "AWAITING_GUI_SIGN",
                                "signed": False, "script": str(script), "signLog": str(log),
                                "receiptPath": str(receipt), "target": str(dst),
                                "signLaunchResult": launch})
    print(json.dumps({"ok": ok, "launched": ok, "status": "AWAITING_GUI_SIGN",
                      "target": str(dst), "signLog": str(log)}))
    return 0 if ok else 1


def cmd_sign_collect(args, ev):
    stage = Stage(ev, "sign-collect")
    sign_dir = Path(args.sign_dir).resolve()
    src = Path(args.app).resolve()
    dst = Path(args.signed_app).resolve()
    receipt = sign_dir / "sign-receipt.json"
    log = sign_dir / "sign.log"
    deadline = time.time() + max(0, args.wait)
    while not receipt.is_file() and time.time() < deadline:
        time.sleep(2)
    if not receipt.is_file():
        return stage.fail("GUI signing receipt missing (signing not completed): " + str(receipt))
    try:
        record = read_json(receipt)
    except (OSError, ValueError) as error:
        return stage.fail("GUI signing receipt unreadable: " + str(error))
    problems = []
    if record.get("exit") != 0:
        problems.append("GUI signing exit is not 0: " + repr(record.get("exit")))
    if record.get("status") != "signed":
        problems.append("GUI signing status is not 'signed'")
    if not log.is_file() or log.stat().st_size == 0:
        problems.append("GUI signing log missing or empty")
    before_path = sign_dir / "input-hashes.json"
    before = read_json(before_path) if before_path.is_file() else None
    input_unchanged = None
    if before is not None:
        after = {p.relative_to(src).as_posix(): sha(p) for p in sorted(src.rglob("*")) if p.is_file()}
        input_unchanged = before == after
        if not input_unchanged:
            problems.append("unsigned input changed during GUI signing")
    signed = {p.relative_to(dst).as_posix(): sha(p) for p in sorted(dst.rglob("*")) if p.is_file()} if dst.is_dir() else {}
    if not signed:
        problems.append("signed app is missing or empty")
    if dst.is_dir() and args.executable and (dst / args.executable).is_file():
        if before is not None and signed.get(args.executable) == before.get(args.executable):
            problems.append("main executable bytes did not change; signature was not applied")
    stage.write("request.json", {"stage": "sign-collect", "argv": [], "startedUtc": utc(),
                                 "signDir": str(sign_dir), "app": str(src), "signedApp": str(dst)})
    stage.write("signed-hashes.json", signed)
    stage.write("result.json", {"stage": "sign-collect", "ok": not problems,
                                "exitCode": 0 if not problems else 1, "problems": problems,
                                "guiReceipt": record, "signLog": str(log),
                                "signLogSha256": sha(log) if log.is_file() else None,
                                "inputUnchanged": input_unchanged, "signedFiles": len(signed)})
    print(json.dumps({"ok": not problems, "problems": problems, "signedFiles": len(signed)}))
    return 0 if not problems else 1


def cmd_sign_verify(args, ev):
    stage = Stage(ev, "sign-verify")
    app = Path(args.signed_app).resolve()
    if not app.is_dir():
        return stage.fail("signed app missing")
    if not (app / "embedded.mobileprovision").is_file():
        return stage.fail("embedded.mobileprovision missing")
    if not (args.team and args.bundle and args.udid):
        return stage.fail("--team, --bundle and --udid are required")
    started = utc()
    stage.write("request.json", {"stage": "sign-verify", "argv": [], "startedUtc": started,
                                 "signedApp": str(app), "team": args.team,
                                 "bundle": args.bundle, "udid": args.udid})
    steps = {}
    ok, verify = run_stage(Stage(ev, "sign-verify-codesign"),
                           [args.codesign_bin, "--verify", "--deep", "--strict", "--verbose=2", str(app)])
    steps["codesignVerify"] = verify
    if not ok:
        return stage.fail("codesign --verify --deep --strict failed", {"steps": steps})
    ok, dv = run_stage(Stage(ev, "sign-verify-dv"),
                       [args.codesign_bin, "-dv", "--verbose=4", str(app)])
    steps["codesignDv"] = dv
    if not ok:
        return stage.fail("codesign -dv failed", {"steps": steps})
    dv_text = Path(dv["stdout"]).read_text(errors="replace") + NL + \
        Path(dv["stderr"]).read_text(errors="replace")
    dv_fields = parse_dv(dv_text)
    ok, ent_stage = run_stage(Stage(ev, "sign-verify-entitlements"),
                              [args.codesign_bin, "-d", "--entitlements", ":-", str(app)])
    steps["codesignEntitlements"] = ent_stage
    if not ok:
        return stage.fail("codesign entitlements dump failed", {"steps": steps})
    try:
        signed_ent = load_plist_bytes(Path(ent_stage["stdout"]).read_bytes())
    except Exception as error:
        return stage.fail("signed entitlements decode failed: " + str(error))
    ok, cms = run_stage(Stage(ev, "sign-verify-profile"),
                        [args.security_bin, "cms", "-D", "-i", str(app / "embedded.mobileprovision")])
    steps["securityCms"] = cms
    if not ok:
        return stage.fail("security cms -D failed", {"steps": steps})
    try:
        profile = load_plist_bytes(Path(cms["stdout"]).read_bytes())
    except Exception as error:
        return stage.fail("profile plist decode failed: " + str(error))
    problems, details = profile_problems(profile, args.team, args.udid, args.bundle)
    problems.extend(signed_entitlement_problems(signed_ent, args.team, args.bundle))
    authorities = dv_fields.get("authorities") or []
    if not any(item.startswith("Apple Development:") for item in authorities):
        problems.append("codesign authority is not an Apple Development certificate: "
                        + repr(authorities[:2]))
    if args.team and dv_fields.get("TeamIdentifier") != args.team:
        problems.append("codesign TeamIdentifier mismatch: " + repr(dv_fields.get("TeamIdentifier")))
    if args.bundle and dv_fields.get("Identifier") != args.bundle:
        problems.append("codesign Identifier mismatch: " + repr(dv_fields.get("Identifier")))
    identity_checked = None
    if args.identity and re.fullmatch(r"[0-9A-Fa-f]{40}", args.identity):
        cert_dir = stage.path("certificates")
        cert_dir.mkdir()
        ok, cert = run_stage(Stage(ev, "sign-verify-cert"),
                             [args.codesign_bin, "-d", "--extract-certificates=cert", str(app)],
                             cwd=cert_dir)
        steps["codesignCertificates"] = cert
        if not ok:
            problems.append("codesign certificate extraction failed")
        else:
            files = sorted(cert_dir.glob("cert*"))
            if not files:
                problems.append("codesign certificate extraction produced no certificate")
            else:
                fingerprint = hashlib.sha1(files[0].read_bytes()).hexdigest().upper()
                identity_checked = fingerprint
                if fingerprint != args.identity.upper():
                    problems.append("codesign identity fingerprint mismatch: " + fingerprint)
    elif args.identity:
        joined = " ".join(authorities)
        if args.identity not in joined:
            problems.append("codesign authority does not contain the requested identity name")
    sign_receipt = Path(args.sign_receipt) if args.sign_receipt else None
    receipt_record = None
    if sign_receipt is not None:
        if not sign_receipt.is_file():
            problems.append("GUI signing receipt missing (signing may not have completed)")
        else:
            try:
                receipt_record = read_json(sign_receipt)
                if receipt_record.get("exit") != 0 or receipt_record.get("status") != "signed":
                    problems.append("GUI signing receipt does not record a successful signing")
            except (OSError, ValueError) as error:
                problems.append("GUI signing receipt unreadable: " + str(error))
    app_digest_value, _app_files, _app_bytes = app_digest(app)
    stage.write("checks.json", {"problems": problems, "appDigestSha256": app_digest_value,
                                "profile": details,
                                "signedEntitlements": {key: signed_ent.get(key) for key in (
                                    "application-identifier", "get-task-allow",
                                    "com.apple.developer.team-identifier")},
                                "codesign": {key: dv_fields.get(key) for key in (
                                    "Identifier", "TeamIdentifier", "authorities")},
                                "identityFingerprint": identity_checked})
    stage.write("result.json", {"stage": "sign-verify", "ok": not problems,
                                "exitCode": 0 if not problems else 1, "problems": problems,
                                "steps": steps, "guiReceipt": receipt_record,
                                "appDigestSha256": app_digest_value,
                                "bundleId": args.bundle, "udid": args.udid,
                                "startedUtc": started, "finishedUtc": utc()})
    print(json.dumps({"ok": not problems, "problems": problems}))
    return 0 if not problems else 1

# ---------------------------------------------------------------- install

def cmd_install(args, ev):
    stage = Stage(ev, "install")
    app = Path(args.signed_app).resolve()
    if not app.is_dir():
        return stage.fail("signed app missing")
    if not args.bundle or not args.udid:
        return stage.fail("--bundle and --udid are required")
    if args.sign_verify_result:
        try:
            verify = read_json(args.sign_verify_result)
        except (OSError, ValueError) as error:
            return stage.fail("sign-verify result unreadable: " + str(error))
        if verify.get("ok") is not True or verify.get("exitCode") != 0:
            return stage.fail("sign-verify result is not a pass")
    try:
        info = load_plist_file(app / "Info.plist")
    except Exception as error:
        return stage.fail("signed app Info.plist unreadable: " + str(error))
    if info.get("CFBundleIdentifier") != args.bundle:
        return stage.fail("signed app bundle id is not " + args.bundle)
    receipt = stage.path("devicectl-install.json")
    ok, result = run_stage(stage,
                           [args.xcrun_bin, "devicectl", "device", "install", "app",
                            "--device", args.udid, str(app), "--json-output", str(receipt)],
                           json_out=receipt, json_required=True, require_outcome="success",
                           extra={"bundle": args.bundle, "udid": args.udid,
                                  "app": str(app), "appInfoPlistSha256": sha(app / "Info.plist"),
                                  "signVerifyResult": args.sign_verify_result})
    if not ok:
        print(json.dumps({"ok": False, "receipt": str(receipt),
                          "outcome": result.get("jsonOutcome")}))
        return 1
    if args.dry_run:
        print(json.dumps({"ok": True, "dryRun": True, "stage": "install"}))
        return 0
    try:
        raw = read_json(receipt)
    except (OSError, ValueError) as error:
        return stage.fail("install receipt unparsable after success: " + str(error))
    problems = []
    if not nested_contains(raw, args.bundle):
        problems.append("install receipt is not bound to bundle " + args.bundle)
    if not nested_contains(raw, args.udid):
        problems.append("install receipt is not bound to device " + args.udid)
    installed = raw.get("result", {}).get("installedApplication") if isinstance(raw.get("result"), dict) else None
    if isinstance(installed, dict) and installed.get("bundleIdentifier") not in (None, args.bundle):
        problems.append("installedApplication bundleIdentifier mismatch")
    stage.write("install-summary.json", {"bundle": args.bundle, "udid": args.udid,
                                         "outcome": result.get("jsonOutcome"),
                                         "receiptSha256": result.get("jsonSha256"),
                                         "installedApplication": installed,
                                         "childPid": result.get("childPid"),
                                         "finishedUtc": result.get("finishedUtc"),
                                         "problems": problems})
    print(json.dumps({"ok": not problems, "receipt": str(receipt), "problems": problems}))
    return 0 if not problems else 1


# ---------------------------------------------------------------- generator + payload

NONCE_RE = re.compile(r"[0-9a-f]{32}")
HEX64_RE = re.compile(r"\b[0-9a-f]{64}\b")


def macho_platform(data):
    if len(data) < 32:
        return None
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic not in (0xFEEDFACF, 0xFEEDFACE):
        return None
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        if cmd == 0x32 and size >= 24:
            return struct.unpack_from("<I", data, off + 8)[0]
        if cmd == 0x25 and size >= 16:
            return 2
        off += size
    return None


def macho_text(data):
    if len(data) < 32 or struct.unpack_from("<I", data, 0)[0] != 0xFEEDFACF:
        return None
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        if cmd == 0x19 and size >= 72:
            name = data[off + 8:off + 24].split(b"\x00")[0].decode("ascii", "replace")
            if name == "__TEXT":
                vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, off + 24)
                return {"vmaddr": vmaddr, "vmsize": vmsize,
                        "fileoff": fileoff, "filesize": filesize}
        off += size
    return None


def app_digest(app):
    digest = hashlib.sha256()
    count = 0
    total = 0
    for path in sorted(p for p in Path(app).rglob("*") if p.is_file()):
        rel = path.relative_to(Path(app)).as_posix()
        size = path.stat().st_size
        digest.update(rel.encode("utf-8") + b"\x00" + sha(path).encode("ascii") + b"\x00"
                      + str(size).encode("ascii") + b"\n")
        count += 1
        total += size
    return digest.hexdigest(), count, total


def platform2_report(app):
    images = {}
    for path in sorted(p for p in Path(app).rglob("*") if p.is_file()):
        try:
            head = path.read_bytes()[:4]
        except OSError:
            continue
        if len(head) < 4 or struct.unpack("<I", head)[0] not in (0xFEEDFACF, 0xFEEDFACE):
            continue
        platform = macho_platform(path.read_bytes())
        if platform is not None:
            images[path.relative_to(Path(app)).as_posix()] = platform
    return {"platform2": bool(images) and all(value == 2 for value in images.values()),
            "images": images}


def source_inventory(directory):
    return {path.relative_to(directory).as_posix(): {"sha256": sha(path),
                                                    "size": path.stat().st_size}
            for path in sorted(p for p in Path(directory).rglob("*") if p.is_file())}


def validate_install_for_generation(path, bundle, udid):
    problems = []
    try:
        install = read_json(path)
    except (OSError, ValueError) as error:
        return None, ["install result unreadable: " + str(error)]
    if install.get("stage") != "install":
        problems.append("install result stage is not 'install'")
    if install.get("exitCode") != 0:
        problems.append("install exitCode != 0")
    if install.get("dryRun") is not False:
        problems.append("install result is dry-run or missing dryRun=false")
    if install.get("jsonOutcome") != "success":
        problems.append("install CoreDevice outcome != success")
    if not isinstance(install.get("childPid"), int) or install["childPid"] <= 0:
        problems.append("install result has no real child pid")
    if install.get("bundle") != bundle:
        problems.append("install result bundle mismatch")
    if install.get("udid") != udid:
        problems.append("install result device mismatch")
    receipt = install.get("jsonPath")
    raw = None
    if not receipt or not Path(receipt).is_file():
        problems.append("install raw receipt missing")
    else:
        raw = read_json(receipt)
        if install.get("jsonSha256") != sha(receipt):
            problems.append("install raw receipt hash changed")
        if not nested_contains(raw, bundle):
            problems.append("raw install receipt is not bound to the bundle")
        if not nested_contains(raw, udid):
            problems.append("raw install receipt is not bound to the device")
        if ((raw.get("info") or {}).get("outcome")) != "success":
            problems.append("raw install receipt outcome is not success")
    started = parse_utc(install.get("startedUtc"))
    finished = parse_utc(install.get("finishedUtc"))
    now = datetime.datetime.now(datetime.timezone.utc)
    if not started or not finished:
        problems.append("install chronology missing")
    elif finished < started:
        problems.append("install finishedUtc precedes startedUtc")
    elif finished > now:
        problems.append("install finishedUtc is in the future")
    return install, problems


def validate_sign_verify_for_generation(path, host_app, bundle, udid):
    problems = []
    try:
        verify = read_json(path)
    except (OSError, ValueError) as error:
        return None, ["sign-verify result unreadable: " + str(error)]
    if verify.get("stage") != "sign-verify":
        problems.append("sign-verify result stage mismatch")
    if verify.get("ok") is not True or verify.get("exitCode") != 0:
        problems.append("sign-verify did not pass")
    if verify.get("problems"):
        problems.append("sign-verify result still lists problems")
    checks_path = Path(path).parent / "checks.json"
    if not checks_path.is_file():
        problems.append("sign-verify checks.json missing")
    else:
        checks = read_json(checks_path)
        if checks.get("problems"):
            problems.append("sign-verify checks.json still lists problems")
    request_path = Path(path).parent / "request.json"
    if not request_path.is_file():
        problems.append("sign-verify request.json missing")
    else:
        request = read_json(request_path)
        if Path(str(request.get("signedApp", ""))).resolve() != Path(host_app).resolve():
            problems.append("sign-verify was not run on the host app")
    actual_digest, _count, _total = app_digest(host_app)
    if verify.get("appDigestSha256") != actual_digest:
        problems.append("signed host app changed after sign-verify")
    if verify.get("bundleId") != bundle:
        problems.append("sign-verify bundle mismatch")
    if verify.get("udid") != udid:
        problems.append("sign-verify device mismatch")
    return verify, problems


def derived_generator_receipt(stage, install, verify, host_app, bundle, udid):
    raw_path = Path(install["jsonPath"]).resolve()
    verify_path = Path(verify.get("resultPath", "")).resolve() if verify.get("resultPath") else None
    digest, count, total = app_digest(host_app)
    platform = platform2_report(host_app)
    if not platform["platform2"]:
        raise SystemExit("signed host app does not contain only platform-2 images")
    install_result_path = Path(install.get("resultPath", "")).resolve() if install.get("resultPath") else None
    wrapper = {
        "schema": "runeclr.ipados.r2r.install-receipt.v2",
        "derived": True,
        "note": "Derived archive from the actual devicectl receipt and sign-verify result; not a new install.",
        "success": True,
        "installed": True,
        "signed": True,
        "bundleId": bundle,
        "deviceUdid": udid,
        "platform": 2,
        "installedUtc": install.get("finishedUtc"),
        "appDigestSha256": digest,
        "devicectlReceiptPath": str(raw_path),
        "devicectlReceiptSha256": sha(raw_path),
        "devicectlOutcome": (read_json(raw_path).get("info") or {}).get("outcome"),
        "installResultPath": str(install_result_path) if install_result_path else None,
        "installResultSha256": sha(install_result_path) if install_result_path else None,
        "signVerifyResultPath": str(verify_path) if verify_path else None,
        "signVerifyResultSha256": sha(verify_path) if verify_path else None,
    }
    stage.write("install-receipt.json", wrapper)
    wrapper_path = stage.path("install-receipt.json")
    wrapper_sha = sha(wrapper_path)
    archive_record = dict(wrapper)
    archive_record["note"] = "Derived archive; raw devicectl receipt remains the origin."
    stage.write("install-archive.json", archive_record)
    record = {
        "schema": "runeclr.ipados.r2r.generator-install-receipt.v2",
        "derived": True,
        "note": "Derived from the actual devicectl install receipt and sign-verify result; not a new install.",
        "status": "installed",
        "installed": True,
        "signed": True,
        "bundleId": bundle,
        "deviceUdid": udid,
        "platform": 2,
        "platform2": True,
        "installedUtc": install.get("finishedUtc"),
        "appDigestSha256": digest,
        "appFileCount": count,
        "appBytes": total,
        "rawReceiptPath": str(wrapper_path),
        "rawReceiptSha256": wrapper_sha,
        "rawReceiptOrigin": {"path": str(raw_path), "sha256": sha(raw_path)},
        "archive": {"path": str(wrapper_path), "sha256": wrapper_sha},
        "rawReceipt": {"path": str(raw_path), "sha256": sha(raw_path)},
        "signVerify": {"path": str(verify_path) if verify_path else None,
                       "sha256": sha(verify_path) if verify_path else None},
        "platform2Images": platform["images"],
    }
    stage.write("generator-install-receipt.json", record)
    return stage.path("generator-install-receipt.json"), record


def read_generator_output(output):
    output = Path(output)
    owner_doc = read_json(output / "owner.json")
    owner = owner_doc.get("owner")
    if not isinstance(owner, dict):
        raise SystemExit("owner.json has no nested owner object")
    name = safe_rel(owner.get("name"))
    if "/" in name:
        raise SystemExit("owner.name must be a plain file name")
    if not isinstance(owner.get("rawSha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", owner["rawSha256"]):
        raise SystemExit("owner.rawSha256 invalid")
    if not isinstance(owner.get("uuid"), str) or not re.fullmatch(r"[0-9a-fA-F]{32}", owner["uuid"]):
        raise SystemExit("owner.uuid invalid")
    if owner.get("platform") != 2:
        raise SystemExit("owner.platform is not 2")
    text_info = owner.get("text")
    if not isinstance(text_info, dict):
        raise SystemExit("owner.text must be a __TEXT dictionary")
    for key in ("vmaddr", "vmsize", "fileoff", "filesize"):
        value = text_info.get(key)
        if not isinstance(value, int) or value < 0:
            raise SystemExit("owner.text." + key + " invalid")
    if text_info["vmsize"] <= 0 or text_info["filesize"] <= 0:
        raise SystemExit("owner.text vmsize/filesize must be positive")
    header = owner.get("rtrHeader")
    if not isinstance(header, dict) or header.get("symbol") != "_RTR_HEADER":
        raise SystemExit("owner.rtrHeader missing or wrong symbol")
    if not isinstance(header.get("value"), int) or header["value"] <= 0:
        raise SystemExit("owner.rtrHeader.value invalid")
    if not isinstance(header.get("section"), int) or header["section"] <= 0:
        raise SystemExit("owner.rtrHeader.section invalid")
    deploy = output / "deploy"
    if not deploy.is_dir():
        raise SystemExit("generator deploy directory missing")
    payload = owner_doc.get("payload")
    if not isinstance(payload, dict) or not payload:
        raise SystemExit("owner.json payload map is empty")
    if "payload-files.txt" in payload:
        raise SystemExit("payload map must exclude payload-files.txt")
    deployable = owner_doc.get("deployable") or []
    names = {name, "payload-files.txt"} | set(payload)
    for item in deployable:
        if isinstance(item, str):
            names.add(safe_rel(item))
        elif isinstance(item, dict):
            value = item.get("name") or item.get("filename")
            if value:
                names.add(safe_rel(value))
    actual = {p.relative_to(deploy).as_posix(): p for p in deploy.rglob("*") if p.is_file()}
    if set(actual) != names:
        raise SystemExit("deploy file set mismatch: " + repr(sorted(set(actual) ^ names)))
    if "payload-files.txt" not in actual:
        raise SystemExit("payload-files.txt missing from deploy")
    binaries = set(actual) - {"payload-files.txt"}
    if set(payload) != binaries:
        raise SystemExit("binary payload map mismatch: " + repr(sorted(set(payload) ^ binaries)))
    payload_files_sha = owner_doc.get("payloadFilesSha256")
    if not isinstance(payload_files_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", payload_files_sha):
        raise SystemExit("payloadFilesSha256 invalid")
    if sha(deploy / "payload-files.txt") != payload_files_sha:
        raise SystemExit("payloadFilesSha256 does not match payload-files.txt")
    for rel, info in payload.items():
        rel = safe_rel(rel)
        if not (deploy / rel).is_file():
            raise SystemExit("payload file missing: " + rel)
        if not isinstance(info, dict):
            raise SystemExit("payload entry is not an object: " + rel)
        if sha(deploy / rel) != info.get("sha256"):
            raise SystemExit("payload hash mismatch: " + rel)
        if (deploy / rel).stat().st_size != info.get("bytes"):
            raise SystemExit("payload byte count mismatch: " + rel)
    owner_info = payload.get(name)
    if not isinstance(owner_info, dict) or owner_info.get("sha256") != owner["rawSha256"]:
        raise SystemExit("owner payload hash does not match owner.rawSha256")
    if owner_info.get("bytes") != (deploy / name).stat().st_size:
        raise SystemExit("owner payload byte count mismatch")
    owner_bytes = (deploy / name).read_bytes()
    if macho_text(owner_bytes) != text_info:
        raise SystemExit("owner.text does not match the owner __TEXT segment")
    if not rtr_matches(macho_symbol(owner_bytes, "_RTR_HEADER"), header):
        raise SystemExit("owner.rtrHeader does not match the owner symbol table")
    return owner_doc, owner, deploy, payload, sorted(actual)


def cmd_gen_payload(args, ev):
    stage = Stage(ev, "gen-payload")
    try:
        token_ok(args.run, "run")
        if not NONCE_RE.fullmatch(args.nonce or ""):
            raise SystemExit("--nonce must be 32 lowercase hex characters")
    except SystemExit as error:
        return stage.fail(str(error))
    install, problems = validate_install_for_generation(Path(args.install_result), args.bundle,
                                                        args.udid)
    if install is not None:
        install["resultPath"] = str(Path(args.install_result).resolve())
    verify, verify_problems = validate_sign_verify_for_generation(
        Path(args.sign_verify_result), Path(args.host_app), args.bundle, args.udid)
    if verify is not None:
        verify["resultPath"] = str(Path(args.sign_verify_result).resolve())
    problems.extend(verify_problems)
    if problems:
        return stage.fail("install/sign-verify receipt rejected: " + "; ".join(problems),
                          {"problems": problems})
    host_app = Path(args.host_app).resolve()
    output = Path(args.output).resolve()
    sources = Path(args.sources).resolve()
    if output.exists():
        return stage.fail("generator output already exists (fresh output required): " + str(output))
    if not sources.is_dir():
        return stage.fail("generator sources directory missing")
    if not host_app.is_dir():
        return stage.fail("signed host app missing")
    before = source_inventory(sources)
    stage.write("sources-before.json", before)
    receipt, derived = derived_generator_receipt(stage, install, verify, host_app,
                                                 args.bundle, args.udid)
    argv = [args.python_bin, args.generator, "--version", args.version,
            "--sources", str(sources), "--host-app", str(host_app),
            "--install-receipt", str(receipt), "--nonce", args.nonce,
            "--output", str(output)]
    for flag, value in (("--runtime-root", args.runtime_root),
                        ("--framework-root", args.framework_root),
                        ("--dotnet", args.dotnet),
                        ("--csc", args.csc),
                        ("--crossgen2", args.crossgen2)):
        if value:
            argv.extend([flag, str(value)])
    argv.extend(["--udid", str(args.device_udid or args.udid),
                 "--bundle-id", str(args.bundle_id or args.bundle)])
    argv.extend(args.generator_arg or [])
    ok, result = run_stage(stage, argv,
                           extra={"run": args.run, "nonce": args.nonce, "version": args.version,
                                  "sources": str(sources), "hostApp": str(host_app),
                                  "installResult": str(args.install_result),
                                  "signVerifyResult": str(args.sign_verify_result),
                                  "installFinishedUtc": install.get("finishedUtc"),
                                  "generatorInstallReceipt": str(receipt),
                                  "generatorInstallReceiptSha256": sha(receipt)},
                           dry_run=args.dry_run)
    if not ok:
        print(json.dumps({"ok": False, "error": result.get("error")}))
        return 1
    if args.dry_run:
        print(json.dumps({"ok": True, "dryRun": True, "status": "RENDERED_ONLY",
                          "output": str(output)}))
        return 0
    after = source_inventory(sources)
    stage.write("sources-after.json", after)
    finish_dt = parse_utc(install.get("finishedUtc"))
    start_dt = parse_utc(result.get("startedUtc"))
    verify_dt = parse_utc(verify.get("finishedUtc"))
    chronology = {"installFinishedUtc": install.get("finishedUtc"),
                  "signVerifyFinishedUtc": verify.get("finishedUtc"),
                  "generatorStartedUtc": result.get("startedUtc"),
                  "generatorFinishedUtc": result.get("finishedUtc"),
                  "installBeforeGenerator": bool(finish_dt and start_dt and finish_dt <= start_dt),
                  "signVerifyBeforeGenerator": bool(verify_dt and start_dt and verify_dt <= start_dt),
                  "managedCompilerObserved": True,
                  "managedCompilerNote": "Generator invocation covers the managed compile stage; "
                                         "its stdout/stderr are recorded in this stage."}
    stage.write("chronology.json", chronology)

    def post_fail(message):
        stage.write("result.json", {"stage": "gen-payload", "ok": False, "exitCode": 1,
                                    "error": message, "generatorResult": result,
                                    "chronology": chronology})
        print(json.dumps({"ok": False, "error": message, "generatorResult": result}))
        return 1

    if before != after:
        return post_fail("generator changed the source tree")
    if not chronology["installBeforeGenerator"]:
        return post_fail("install receipt does not predate the generator spawn")
    if not chronology["signVerifyBeforeGenerator"]:
        return post_fail("sign-verify does not predate the generator spawn")
    try:
        owner_doc, owner, deploy, payload, depot_files = read_generator_output(output)
    except (SystemExit, OSError, ValueError) as error:
        return post_fail("generator output invalid: " + str(error))
    stage.write("owner-summary.json", {"version": args.version, "run": args.run,
                                       "nonce": args.nonce,
                                       "owner": owner,
                                       "ownerJson": str(output / "owner.json"),
                                       "ownerJsonSha256": sha(output / "owner.json"),
                                       "deploy": str(deploy),
                                       "deployFiles": depot_files,
                                       "payload": payload,
                                       "installReceipt": str(receipt),
                                       "installReceiptSha256": sha(receipt),
                                       "appDigestSha256": derived["appDigestSha256"]})
    print(json.dumps({"ok": True, "output": str(output), "owner": owner.get("name"),
                      "run": args.run, "nonce": args.nonce,
                      "payloadFiles": sorted(payload)}))
    return 0


def copy_deploy(deploy, target):
    target.mkdir(parents=True)
    for path in sorted(p for p in Path(deploy).rglob("*") if p.is_file()):
        rel = path.relative_to(Path(deploy)).as_posix()
        safe_rel(rel)
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())


def build_raw_manifest(run, nonce, version, host_bundle, install_sha, owner, payload,
                       run_dir):
    files = []
    for path in sorted(p for p in Path(run_dir).rglob("*") if p.is_file()):
        rel = path.relative_to(Path(run_dir)).as_posix()
        files.append({"path": rel, "sha256": sha(path), "size": path.stat().st_size})
    return {"schema": PAYLOAD_SCHEMA, "signed": False, "run": run, "nonce": nonce,
            "expectedVersion": version, "hostBundle": host_bundle,
            "installReceiptSha256": install_sha, "createdUtc": utc(),
            "owner": owner, "payload": payload,
            "payloadFiles": {"path": "payload-files.txt",
                             "sha256": sha(Path(run_dir) / "payload-files.txt")},
            "fileCount": len(files), "files": files}


def cmd_compose_payload(args, ev):
    stage = Stage(ev, "compose-payload")
    try:
        token_ok(args.run_a, "run-a")
        token_ok(args.run_b, "run-b")
        if args.run_a == args.run_b:
            raise SystemExit("run-a and run-b must be distinct")
        for value, label in ((args.nonce_a, "nonce-a"), (args.nonce_b, "nonce-b")):
            if not NONCE_RE.fullmatch(value or ""):
                raise SystemExit(label + " must be 32 lowercase hex characters")
        if args.nonce_a == args.nonce_b:
            raise SystemExit("nonce-a and nonce-b must be distinct")
        if not re.fullmatch(r"[0-9a-f]{64}", args.install_receipt_sha256 or ""):
            raise SystemExit("--install-receipt-sha256 must be a sha256 hex digest")
        root = Path(args.payload_root).resolve()
        if root.exists() and any(root.iterdir()):
            return stage.fail("payload root already exists and is not empty: " + str(root))
        root.mkdir(parents=True, exist_ok=True)
        records = {}
        for version, run, nonce, source in (("A", args.run_a, args.nonce_a, Path(args.a_dir)),
                                            ("B", args.run_b, args.nonce_b, Path(args.b_dir))):
            owner_doc, owner, deploy, payload, depot_files = read_generator_output(source.resolve())
            run_dir = root / run
            if run_dir.exists():
                return stage.fail("payload run directory already exists: " + str(run_dir))
            copy_deploy(deploy, run_dir)
            manifest = build_raw_manifest(run, nonce, version, args.bundle,
                                          args.install_receipt_sha256, owner, payload, run_dir)
            sidecar = root / (run + ".raw-manifest.json")
            if sidecar.exists():
                return stage.fail("raw manifest already exists: " + str(sidecar))
            sidecar.write_text(json.dumps(manifest, indent=2) + NL, encoding="utf-8")
            records[version] = {"run": run, "nonce": nonce, "expectedVersion": version,
                                "runDir": str(run_dir), "rawManifest": str(sidecar),
                                "rawManifestSha256": sha(sidecar),
                                "owner": owner.get("name"),
                                "ownerRawSha256": owner.get("rawSha256"),
                                "fileCount": len(depot_files)}
    except (SystemExit, OSError, ValueError) as error:
        return stage.fail("compose failed: " + str(error))
    stage.write("request.json", {"stage": "compose-payload", "argv": [], "startedUtc": utc(),
                                 "payloadRoot": str(args.payload_root),
                                 "runA": args.run_a, "runB": args.run_b,
                                 "nonceA": args.nonce_a, "nonceB": args.nonce_b,
                                 "installReceiptSha256": args.install_receipt_sha256,
                                 "hostBundle": args.bundle})
    stage.write("result.json", {"stage": "compose-payload", "ok": True, "exitCode": 0,
                                "versions": records})
    print(json.dumps({"ok": True, "versions": records}))
    return 0



def payload_runs(root):
    root = Path(root)
    runs = {}
    for sidecar in sorted(root.glob("*.raw-manifest.json")):
        run = sidecar.name[:-len(".raw-manifest.json")]
        manifest = read_json(sidecar)
        if manifest.get("run") != run:
            raise SystemExit("raw manifest run mismatch: " + str(sidecar))
        if not (root / run).is_dir():
            raise SystemExit("payload run directory missing: " + run)
        runs[run] = (sidecar, manifest)
    if not runs:
        raise SystemExit("no raw payload manifests under " + str(root))
    return runs


def cmd_sign_payload(args, ev):
    stage = Stage(ev, "sign-payload")
    q = shlex.quote
    if not args.identity:
        return stage.fail("--identity is required")
    src = Path(args.payload_root).resolve()
    dst = Path(args.signed_payload_root).resolve()
    try:
        runs = payload_runs(src)
    except SystemExit as error:
        return stage.fail(str(error))
    if dst.exists():
        return stage.fail("signed payload root already exists: " + str(dst))
    dylibs = []
    for run in runs:
        for path in sorted((src / run).rglob("*.dylib")):
            if path.is_file():
                dylibs.append(path)
    if not dylibs:
        return stage.fail("no owner dylibs to sign under " + str(src))
    if not args.dry_run:
        for run in runs:
            shutil.copytree(src / run, dst / run)
            (dst / run / "manifest.json").unlink(missing_ok=True)
    log = dst.parent / (dst.name + ".sign.log")
    receipt = dst.parent / (dst.name + ".sign-receipt.json")
    script = dst.parent / (dst.name + ".sign-" + uuid.uuid4().hex[:8] + ".command")
    hashes = dst.parent / (dst.name + ".signed-hashes.txt")
    for existing in (log, receipt, script, hashes):
        if existing.exists():
            return stage.fail("GUI signing artifact already exists: " + str(existing))
    body = NL.join(gui_script_common(q, str(dst), str(log), str(receipt)) + [
        "HASHES=" + q(str(hashes)),
        ": > \"$HASHES\"",
        "find \"$DST\" -type f -name '*.dylib' -print0 | while IFS= read -r -d '' f; do "
        + q(args.codesign_bin) + " --force --sign " + q(args.identity)
        + " --timestamp=none \"$f\"; rel=\"${f#$DST/}\"; run=\"${rel%%/*}\";"
        " sub=\"${rel#*/}\"; printf '%s\\t%s\\t%s\\n' \"$run\" \"$sub\""
        " \"$(/usr/bin/shasum -a 256 \"$f\" | cut -d ' ' -f 1)\" >> \"$HASHES\"; done",
        "echo 'sign-payload complete'",
    ]) + NL
    raw = {run: {p.relative_to(src / run).as_posix(): sha(p)
                 for p in sorted((src / run).rglob("*")) if p.is_file()} for run in runs}
    stage.write("request.json", {"stage": "sign-payload", "argv": [], "startedUtc": utc(),
                                 "script": str(script), "source": str(src), "target": str(dst),
                                 "runs": sorted(runs), "identity": args.identity,
                                 "signLog": str(log), "signReceipt": str(receipt),
                                 "signedHashes": str(hashes), "dryRun": bool(args.dry_run)})
    stage.write("raw-hashes.json", raw)
    if args.dry_run:
        rendered = stage.path("script.rendered.sh")
        rendered.write_text(body, encoding="utf-8")
        stage.write("result.json", {"stage": "sign-payload", "ok": True, "dryRun": True,
                                    "status": "RENDERED_ONLY", "script": str(rendered)})
        print(json.dumps({"ok": True, "dryRun": True, "status": "RENDERED_ONLY",
                          "script": str(rendered)}))
        return 0
    if not dst.parent.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(body, encoding="utf-8")
    script.chmod(0o755)
    ok, launch = run_stage(Stage(ev, "sign-payload-launch"),
                           [args.open_bin, "-a", "Terminal", str(script)],
                           extra={"script": str(script),
                                  "note": "open exit 0 = launched only; signing is proven by sign-collect-payload"})
    stage.write("result.json", {"stage": "sign-payload", "ok": ok, "exitCode": 0 if ok else 1,
                                "launched": ok, "status": "AWAITING_GUI_SIGN", "signed": False,
                                "script": str(script), "signLog": str(log),
                                "signReceipt": str(receipt), "signedHashes": str(hashes)})
    print(json.dumps({"ok": ok, "launched": ok, "status": "AWAITING_GUI_SIGN",
                      "signLog": str(log), "signReceipt": str(receipt)}))
    return 0 if ok else 1


def rtr_canonical(record):
    return (str(record.get("symbol")), int(record.get("value")), int(record.get("section")))


def rtr_matches(actual, expected):
    try:
        return rtr_canonical(actual) == rtr_canonical(expected)
    except (TypeError, ValueError, AttributeError):
        return False


def reconcile_payload_files(raw_text, owner_name, raw_sha, signed_sha, raw_size, signed_size):
    lines = raw_text.splitlines(keepends=True)
    changed = 0
    output = []
    for line in lines:
        new = line
        if owner_name in line:
            if raw_sha in new:
                new = new.replace(raw_sha, signed_sha, 1)
                changed += 1
            else:
                match = HEX64_RE.search(new)
                if match:
                    new = new[:match.start()] + signed_sha + new[match.end():]
                    changed += 1
            if raw_size is not None and re.search(r"(?<!\d)" + str(raw_size) + r"(?!\d)", new):
                new = re.sub(r"(?<!\d)" + str(raw_size) + r"(?!\d)", str(signed_size), new, count=1)
        output.append(new)
    if changed != 1:
        raise SystemExit("payload-files.txt has no single owner hash line for " + owner_name)
    text = "".join(output)
    if signed_sha not in text or raw_sha in text:
        raise SystemExit("payload-files.txt owner hash reconciliation failed")
    return text


def cmd_sign_collect_payload(args, ev):
    stage = Stage(ev, "sign-collect-payload")
    src = Path(args.payload_root).resolve()
    dst = Path(args.signed_payload_root).resolve()
    receipt = dst.parent / (dst.name + ".sign-receipt.json")
    log = dst.parent / (dst.name + ".sign.log")
    hashes = dst.parent / (dst.name + ".signed-hashes.txt")
    deadline = time.time() + max(0, args.wait)
    while not receipt.is_file() and time.time() < deadline:
        time.sleep(2)
    if not receipt.is_file():
        return stage.fail("GUI payload signing receipt missing (not completed): " + str(receipt))
    try:
        record = read_json(receipt)
        runs = payload_runs(src)
    except (OSError, ValueError, SystemExit) as error:
        return stage.fail("payload signing inputs unreadable: " + str(error))
    problems = []
    if record.get("exit") != 0 or record.get("status") != "signed":
        problems.append("GUI payload signing did not record success: " + repr(record))
    if not log.is_file() or log.stat().st_size == 0:
        problems.append("GUI payload signing log missing or empty")
    gui_hashes = {}
    if not hashes.is_file():
        problems.append("signed payload hash list missing")
    else:
        for line in hashes.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                return stage.fail("signed payload hash list line invalid: " + repr(line))
            run, rel, value = parts
            try:
                safe_rel(rel)
            except SystemExit as error:
                return stage.fail(str(error))
            gui_hashes.setdefault(run, {})[rel] = value
    records = {}
    for run, (sidecar, manifest) in runs.items():
        run_dir = dst / run
        if not run_dir.is_dir():
            problems.append("signed run directory missing: " + run)
            continue
        owner = manifest.get("owner") or {}
        owner_name = owner.get("name")
        raw_dir = src / run
        raw_hashes = {p.relative_to(raw_dir).as_posix(): sha(p)
                      for p in sorted(raw_dir.rglob("*")) if p.is_file()}
        signed_hashes = {p.relative_to(run_dir).as_posix(): sha(p)
                         for p in sorted(run_dir.rglob("*")) if p.is_file()}
        if set(signed_hashes) != set(raw_hashes):
            problems.append("signed run file set differs: " + run)
            continue
        expected = gui_hashes.get(run)
        actual_dylibs = {rel: value for rel, value in signed_hashes.items() if rel.endswith(".dylib")}
        if expected != actual_dylibs:
            problems.append("signed hash list does not match output for " + run)
        for rel, value in raw_hashes.items():
            if rel == owner_name or rel == "payload-files.txt":
                continue
            if signed_hashes.get(rel) != value:
                problems.append("non-owner payload file changed during signing: " + run + "/" + rel)
        owner_rel = str(owner_name)
        raw_owner = raw_hashes.get(owner_rel)
        signed_owner = signed_hashes.get(owner_rel)
        if raw_owner is None or signed_owner is None:
            problems.append("owner dylib missing: " + run)
            continue
        if raw_owner == signed_owner:
            problems.append("owner dylib bytes did not change after signing: " + run)
        raw_bytes = (raw_dir / owner_rel).read_bytes()
        signed_bytes = (run_dir / owner_rel).read_bytes()
        if macho_uuid(raw_bytes) != owner.get("uuid") or macho_uuid(signed_bytes) != owner.get("uuid"):
            problems.append("owner UUID changed during signing: " + run)
        if not rtr_matches(macho_symbol(raw_bytes, "_RTR_HEADER"), owner.get("rtrHeader")):
            problems.append("raw owner _RTR_HEADER mismatch: " + run)
        if not rtr_matches(macho_symbol(signed_bytes, "_RTR_HEADER"), owner.get("rtrHeader")):
            problems.append("signed owner _RTR_HEADER mismatch: " + run)
        raw_files_text = (raw_dir / "payload-files.txt").read_text(encoding="utf-8")
        reconciled = reconcile_payload_files(raw_files_text, owner_rel, raw_owner, signed_owner,
                                             (raw_dir / owner_rel).stat().st_size,
                                             (run_dir / owner_rel).stat().st_size)
        (run_dir / "payload-files.txt").write_text(reconciled, encoding="utf-8")
        if (run_dir / "payload-files.txt").read_text(encoding="utf-8") != reconciled:
            problems.append("payload-files.txt reconciliation not durable: " + run)
        run_record = {"run": run, "nonce": manifest.get("nonce"),
                      "expectedVersion": manifest.get("expectedVersion"),
                      "owner": owner_rel,
                      "rawSha256": raw_owner, "signedSha256": signed_owner,
                      "rawBytes": (raw_dir / owner_rel).stat().st_size,
                      "signedBytes": (run_dir / owner_rel).stat().st_size,
                      "payloadFilesSha256": sha(run_dir / "payload-files.txt"),
                      "signedHashes": signed_hashes}
        (dst / (run + ".signed-record.json")).write_text(
            json.dumps(run_record, indent=2) + NL, encoding="utf-8")
        records[run] = run_record
    stage.write("request.json", {"stage": "sign-collect-payload", "argv": [], "startedUtc": utc(),
                                 "payloadRoot": str(src), "signedPayloadRoot": str(dst)})
    stage.write("result.json", {"stage": "sign-collect-payload", "ok": not problems,
                                "exitCode": 0 if not problems else 1, "problems": problems,
                                "guiReceipt": record, "signLog": str(log),
                                "signLogSha256": sha(log) if log.is_file() else None,
                                "versions": records})
    print(json.dumps({"ok": not problems, "problems": problems,
                      "runs": sorted(records)}))
    return 0 if not problems else 1


def cmd_seal_payload(args, ev):
    stage = Stage(ev, "seal-payload")
    src = Path(args.payload_root).resolve()
    dst = Path(args.signed_payload_root).resolve()
    try:
        runs = payload_runs(src)
    except SystemExit as error:
        return stage.fail(str(error))
    if args.dry_run:
        stage.write("request.json", {"stage": "seal-payload", "argv": [], "startedUtc": utc(),
                                     "dryRun": True, "payloadRoot": str(src),
                                     "signedPayloadRoot": str(dst)})
        stage.write("result.json", {"stage": "seal-payload", "ok": True, "dryRun": True,
                                    "status": "RENDERED_ONLY", "exitCode": 0})
        print(json.dumps({"ok": True, "dryRun": True, "status": "RENDERED_ONLY"}))
        return 0
    problems = []
    sealed = {}
    for run, (_sidecar, manifest) in runs.items():
        run_dir = dst / run
        record_path = dst / (run + ".signed-record.json")
        if not run_dir.is_dir() or not record_path.is_file():
            problems.append("signed run or signed record missing: " + run)
            continue
        if (run_dir / "manifest.json").exists():
            problems.append("final manifest already exists: " + run)
            continue
        record = read_json(record_path)
        owner = manifest.get("owner") or {}
        owner_rel = owner.get("name")
        raw_dir = src / run
        signed_bytes = (run_dir / owner_rel).read_bytes()
        raw_bytes = (raw_dir / owner_rel).read_bytes()
        if sha(run_dir / owner_rel) != record.get("signedSha256"):
            problems.append("signed owner hash does not match the signed record: " + run)
        if macho_uuid(signed_bytes) != owner.get("uuid"):
            problems.append("signed owner UUID mismatch: " + run)
        if not rtr_matches(macho_symbol(signed_bytes, "_RTR_HEADER"), owner.get("rtrHeader")):
            problems.append("signed owner _RTR_HEADER mismatch: " + run)
        if macho_uuid(raw_bytes) != owner.get("uuid"):
            problems.append("raw owner UUID mismatch: " + run)
        if not rtr_matches(macho_symbol(raw_bytes, "_RTR_HEADER"), owner.get("rtrHeader")):
            problems.append("raw owner _RTR_HEADER mismatch: " + run)
        payload_text = (run_dir / "payload-files.txt").read_text(encoding="utf-8")
        if record.get("signedSha256") not in payload_text:
            problems.append("payload-files.txt does not reference the signed owner: " + run)
        if record.get("rawSha256") in payload_text:
            problems.append("payload-files.txt still references the raw owner: " + run)
        final_files = []
        for path in sorted(p for p in run_dir.rglob("*") if p.is_file()):
            rel = path.relative_to(run_dir).as_posix()
            if rel == "manifest.json":
                continue
            final_files.append({"path": rel, "sha256": sha(path), "size": path.stat().st_size})
        final_map = {item["path"]: item["sha256"] for item in final_files}
        raw_map = {item["path"]: item["sha256"] for item in manifest.get("files", [])}
        if set(final_map) != set(raw_map):
            problems.append("final payload file set differs from the raw manifest: " + run)
        payload = dict(manifest.get("payload") or {})
        payload[owner_rel] = {"sha256": record["signedSha256"],
                              "bytes": record["signedBytes"]}
        final = dict(manifest)
        final.update({"signed": True, "signedUtc": utc(),
                      "owner": dict(owner, signedSha256=record["signedSha256"],
                                    signedBytes=record["signedBytes"]),
                      "payload": payload,
                      "signedRecord": {"path": str(record_path), "sha256": sha(record_path)},
                      "payloadFilesSha256": sha(run_dir / "payload-files.txt"),
                      "fileCount": len(final_files), "files": final_files})
        temporary = run_dir / "manifest.json.tmp"
        temporary.write_text(json.dumps(final, indent=2) + NL, encoding="utf-8")
        os.replace(temporary, run_dir / "manifest.json")
        sealed[run] = {"manifest": str(run_dir / "manifest.json"),
                       "manifestSha256": sha(run_dir / "manifest.json"),
                       "signedSha256": record["signedSha256"]}
    if problems:
        stage.write("request.json", {"stage": "seal-payload", "argv": [], "startedUtc": utc(),
                                     "payloadRoot": str(src), "signedPayloadRoot": str(dst)})
        stage.write("result.json", {"stage": "seal-payload", "ok": False, "exitCode": 1,
                                    "problems": problems})
        print(json.dumps({"ok": False, "problems": problems}))
        return 1
    stage.write("request.json", {"stage": "seal-payload", "argv": [], "startedUtc": utc(),
                                 "payloadRoot": str(src), "signedPayloadRoot": str(dst)})
    stage.write("result.json", {"stage": "seal-payload", "ok": True, "exitCode": 0,
                                "versions": sealed})
    print(json.dumps({"ok": True, "versions": sealed}))
    return 0


def load_payload_manifest(run_dir):
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("payload manifest missing")
    manifest = read_json(manifest_path)
    if manifest.get("schema") != PAYLOAD_SCHEMA:
        raise SystemExit("payload manifest schema mismatch")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise SystemExit("payload manifest has no files (empty payload refused)")
    if manifest.get("fileCount") != len(files):
        raise SystemExit("payload manifest fileCount mismatch")
    expected = {}
    for item in files:
        if not isinstance(item, dict):
            raise SystemExit("payload manifest file entry is not an object")
        rel = safe_rel(item.get("path"))
        if rel in expected:
            raise SystemExit("duplicate payload path: " + rel)
        if not isinstance(item.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise SystemExit("payload manifest sha256 invalid: " + rel)
        if not isinstance(item.get("size"), int) or item["size"] < 0:
            raise SystemExit("payload manifest size invalid: " + rel)
        expected[rel] = item
    actual = {p.relative_to(run_dir).as_posix() for p in run_dir.rglob("*") if p.is_file()}
    actual.discard("manifest.json")
    if actual != set(expected):
        raise SystemExit("payload file set mismatch: " + repr(sorted(actual ^ set(expected))))
    for rel, item in expected.items():
        path = run_dir / rel
        if sha(path) != item["sha256"] or path.stat().st_size != item["size"]:
            raise SystemExit("payload file hash/size mismatch: " + rel)
    return manifest, expected


def cmd_push_payload(args, ev):
    stage = Stage(ev, "push-payload")
    if not args.bundle or not args.udid:
        return stage.fail("--bundle and --udid are required")
    if args.dry_run:
        stage.write("request.json", {"stage": "push-payload", "argv": [], "startedUtc": utc(),
                                     "dryRun": True, "payloadRoot": str(args.payload_root),
                                     "run": args.run})
        stage.write("result.json", {"stage": "push-payload", "ok": True, "dryRun": True,
                                    "status": "RENDERED_ONLY", "exitCode": 0})
        print(json.dumps({"ok": True, "dryRun": True, "status": "RENDERED_ONLY"}))
        return 0
    try:
        token_ok(args.run, "run")
        run_dir = Path(args.payload_root).resolve() / args.run
        manifest, expected = load_payload_manifest(run_dir)
        if manifest.get("run") != args.run:
            raise SystemExit("payload manifest run mismatch")
        if args.nonce and manifest.get("nonce") != args.nonce:
            raise SystemExit("payload manifest nonce mismatch")
        if manifest.get("signed") is not True and not args.allow_unsigned:
            raise SystemExit("payload manifest is not signed; sign owners and seal before pushing")
        if manifest.get("hostBundle") != args.bundle:
            raise SystemExit("payload manifest hostBundle mismatch")
    except (SystemExit, OSError, ValueError) as error:
        return stage.fail(str(error))
    stage.write("request.json", {"stage": "push-payload", "argv": [], "startedUtc": utc(),
                                 "run": args.run, "nonce": args.nonce, "bundle": args.bundle,
                                 "udid": args.udid, "manifestSha256": sha(run_dir / "manifest.json"),
                                 "files": sorted(expected)})
    records = []
    for rel in sorted(expected):
        local = run_dir / rel
        tag = rel.replace("/", "_")
        push_receipt = stage.path(tag + ".push.json")
        ok, push = run_stage(Stage(ev, "push-" + tag),
                             [args.xcrun_bin, "devicectl", "device", "copy", "to",
                              "--device", args.udid, "--domain-type", "appDataContainer",
                              "--domain-identifier", args.bundle, "--source", str(local),
                              "--destination", "Documents/payload/" + args.run + "/" + rel,
                              "--json-output", str(push_receipt)],
                             json_out=push_receipt, json_required=True, require_outcome="success")
        records.append({"file": rel, "push": push})
        if not ok:
            stage.write("result.json", {"stage": "push-payload", "ok": False, "exitCode": 1,
                                        "records": records})
            return 1
        readback_path = stage.path(tag + ".readback") / local.name
        if readback_path.parent.exists():
            return stage.fail("readback destination already exists: " + str(readback_path.parent))
        readback_path.parent.mkdir()
        read_receipt = stage.path(tag + ".readback.json")
        ok, read = run_stage(Stage(ev, "read-" + tag),
                             [args.xcrun_bin, "devicectl", "device", "copy", "from",
                              "--device", args.udid, "--domain-type", "appDataContainer",
                              "--domain-identifier", args.bundle,
                              "--source", "Documents/payload/" + args.run + "/" + rel,
                              "--destination", str(readback_path), "--json-output", str(read_receipt)],
                             json_out=read_receipt, json_required=True, require_outcome="success")
        candidates = [readback_path] if readback_path.is_file() else []
        device_sha = sha(candidates[0]) if len(candidates) == 1 else None
        match = ok and len(candidates) == 1 and device_sha == expected[rel]["sha256"]
        records.append({"file": rel, "readback": read, "deviceSha256": device_sha,
                        "sourceSha256": expected[rel]["sha256"], "match": match,
                        "candidates": [str(p) for p in candidates]})
        if not match:
            stage.write("result.json", {"stage": "push-payload", "ok": False, "exitCode": 1,
                                        "records": records})
            return 1
    stage.write("result.json", {"stage": "push-payload", "ok": True, "exitCode": 0,
                                "records": records, "fileCount": len(expected)})
    print(json.dumps({"ok": True, "files": len(expected)}))
    return 0


# ---------------------------------------------------------------- launch + result

def find_pid(value):
    if isinstance(value, dict):
        for key in ("pid", "processIdentifier", "processID"):
            item = value.get(key)
            if isinstance(item, int) and item > 0:
                return item
        for item in value.values():
            found = find_pid(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_pid(item)
            if found:
                return found
    return None


def cmd_launch(args, ev):
    stage = Stage(ev, "launch")
    if not args.bundle or not args.udid:
        return stage.fail("--bundle and --udid are required")
    try:
        token_ok(args.payload, "payload")
        if not NONCE_RE.fullmatch(args.nonce or ""):
            raise SystemExit("--nonce must be 32 lowercase hex")
    except SystemExit as error:
        return stage.fail(str(error))
    if not args.owner or not Path(args.owner).is_file():
        return stage.fail("--owner (generated owner dylib) is required for nm symbol resolution")
    goldens = GOLDENS[args.expected_version]
    env = {"RUNECLR_EXPECTED_VERSION": args.expected_version,
           "RUNECLR_GOLDEN_RESULT": goldens["result"],
           "RUNECLR_GOLDEN_PRIVATE": goldens["private"],
           "RUNECLR_GOLDEN_HELPER": goldens["helper"]}
    if args.documents:
        documents = args.documents.rstrip("/")
        env["RUNECLR_UPDATE_DIR"] = documents + "/payload/" + args.payload
        env["RUNECLR_RUN_ID"] = args.payload
        env["RUNECLR_RESULT_PATH"] = documents + "/results/" + args.payload + ".json"
    for item in args.env or []:
        if "=" not in item:
            return stage.fail("invalid --env (expected KEY=VALUE): " + item)
        key, value = item.split("=", 1)
        if key == "RUNECLR_FORCE_FAILURE" or key.startswith("RUNECLR_APPROVAL") or key == "RUNECLR_SELECTOR_PLAN":
            return stage.fail("forbidden launch environment key: " + key)
        env[key] = value
    nm_stage = Stage(ev, "launch-nm")
    ok, nm = run_stage(nm_stage, [args.nm_bin, "-nm", args.owner],
                       extra={"owner": str(Path(args.owner).resolve()), "symbol": args.symbol})
    if not ok:
        return stage.fail("nm failed for the generated owner")
    nm_text = Path(nm["stdout"]).read_text(encoding="utf-8", errors="replace")
    symbol = args.symbol.strip()
    if symbol and symbol in nm_text:
        resolved = symbol
    else:
        candidates = sorted({line.split()[-1] for line in nm_text.splitlines()
                             if len(line.split()) >= 3 and "Business" in line.split()[-1]
                             and "Execute" in line.split()[-1]})
        if len(candidates) != 1:
            return stage.fail("could not resolve a unique Business.Execute symbol from nm; candidates="
                              + repr(candidates))
        resolved = candidates[0]
    launch_json = stage.path("devicectl-launch.json")
    argv = [args.xcrun_bin, "devicectl", "device", "process", "launch", "--device", args.udid,
            "--start-stopped", "--environment-variables", json.dumps(env, separators=(",", ":")),
            "--json-output", str(launch_json), args.bundle, "--",
            "--payload", args.payload, "--nonce", args.nonce]
    if args.console:
        argv.insert(argv.index("--start-stopped") + 1, "--console")
    ok, result = run_stage(stage, argv, timeout=args.timeout, json_out=launch_json,
                           extra={"bundle": args.bundle, "udid": args.udid,
                                  "payload": args.payload, "nonce": args.nonce,
                                  "expectedVersion": args.expected_version,
                                  "environment": env, "symbol": resolved,
                                  "owner": str(Path(args.owner).resolve()),
                                  "startStopped": True})
    if not ok:
        return 1
    pid = find_pid(read_json(launch_json)) if launch_json.is_file() else None
    stage.write("launch-summary.json", {"ok": pid is not None, "pid": pid,
                                        "symbol": resolved, "environment": env,
                                        "argv": [str(item) for item in argv],
                                        "startStopped": True,
                                        "next": "run lldb-arm --pid <pid> --symbol <symbol> "
                                                "before process resume"})
    if not pid:
        print(json.dumps({"ok": False, "error": "start-stopped launch did not expose a pid"}))
        return 1
    print(json.dumps({"ok": True, "pid": pid, "symbol": resolved,
                      "payload": args.payload, "nonce": args.nonce}))
    return 0


def cmd_lldb_arm(args, ev):
    stage = Stage(ev, "lldb-arm")
    if not isinstance(args.pid, int) or args.pid <= 0:
        return stage.fail("--pid must be a positive integer")
    if not args.symbol or not args.symbol.strip():
        return stage.fail("--symbol is required")
    argv = [args.lldb_bin, "--batch",
            "-o", "device select " + args.udid,
            "-o", "device process attach -p " + str(args.pid),
            "-o", "breakpoint set -n " + args.symbol,
            "-o", "process continue"]
    ok, result = run_stage(stage, argv, timeout=args.timeout,
                           extra={"pid": args.pid, "symbol": args.symbol,
                                  "note": "pending breakpoint armed before continue"})
    print(json.dumps({"ok": ok, "pid": args.pid, "symbol": args.symbol,
                      "exit": result.get("exitCode")}))
    return 0 if ok else 1


def result_problems(payload, run, nonce, expected_version=None):
    problems = []
    if payload.get("schema") != RESULT_SCHEMA:
        return ["result schema is not " + RESULT_SCHEMA]
    if payload.get("runId") != run:
        problems.append("result runId does not match " + run)
    expected = expected_version or payload.get("expectedVersion")
    for key in ("expectedVersion", "scriptVersion", "observedVersion"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            problems.append("result " + key + " missing")
    if expected:
        for key in ("expectedVersion", "scriptVersion", "observedVersion"):
            if payload.get(key) != expected:
                problems.append("result " + key + " does not match " + expected)
    if not isinstance(payload.get("scriptNonce"), str) or not payload["scriptNonce"].strip():
        problems.append("result scriptNonce missing")
    if nonce is not None and payload.get("scriptNonce") != nonce:
        problems.append("result scriptNonce does not match the expected nonce")
    for key in ("nonceMatches", "versionMatches", "goldenMatches", "contractFromDefault"):
        if payload.get(key) is not True:
            problems.append("result " + key + " is not true")
    goldens = {}
    for key in ("observedResult", "observedPrivate", "observedHelper",
                "goldenResult", "goldenPrivate", "goldenHelper"):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            problems.append("result " + key + " missing")
        else:
            goldens[key] = value
    if len(goldens) == 6:
        if goldens["observedResult"] != goldens["goldenResult"]:
            problems.append("result observedResult does not match goldenResult")
        if goldens["observedPrivate"] != goldens["goldenPrivate"]:
            problems.append("result observedPrivate does not match goldenPrivate")
        if goldens["observedHelper"] != goldens["goldenHelper"]:
            problems.append("result observedHelper does not match goldenHelper")
    if payload.get("driverExitCode") != 0:
        problems.append("result driverExitCode is not 0")
    if not isinstance(payload.get("contractMvid"), str) or not payload["contractMvid"].strip():
        problems.append("result contractMvid missing")
    if payload.get("resultWriteFailed") is not False:
        problems.append("result resultWriteFailed is not false")
    if not isinstance(payload.get("logLength"), int) or payload["logLength"] < 0:
        problems.append("result logLength invalid")
    if not isinstance(payload.get("logExcerpt"), str):
        problems.append("result logExcerpt missing")
    if payload.get("ok") is not True:
        error = payload.get("error")
        if not isinstance(error, str) or not error.strip():
            problems.append("result ok=false without error diagnostic")
        else:
            problems.append("result ok=false: " + error)
        return problems
    if payload.get("error"):
        problems.append("result ok=true but error is non-empty: " + str(payload.get("error")))
    return problems


def cmd_read_result(args, ev):
    stage = Stage(ev, "read-result")
    if not args.bundle or not args.udid:
        return stage.fail("--bundle and --udid are required")
    try:
        token_ok(args.run, "run")
    except SystemExit as error:
        return stage.fail(str(error))
    dest = stage.path("results")
    dest.mkdir()
    receipt = stage.path("devicectl-results.json")
    ok, result = run_stage(stage,
                           [args.xcrun_bin, "devicectl", "device", "copy", "from",
                            "--device", args.udid, "--domain-type", "appDataContainer",
                            "--domain-identifier", args.bundle, "--source", "Documents/results",
                            "--destination", str(dest), "--json-output", str(receipt)],
                           json_out=receipt, json_required=True, require_outcome="success")
    if not ok:
        stage.write("result.json", {"stage": "read-result", "ok": False, "exitCode": 1,
                                    "error": "device results copy failed", "copyResult": result})
        print(json.dumps({"ok": False, "error": "device results copy failed",
                          "copyResult": result}))
        return 1
    if args.dry_run:
        print(json.dumps({"ok": True, "dryRun": True, "stage": "read-result"}))
        return 0
    matches = [p for p in dest.rglob("*") if p.is_file() and p.name == args.run + ".json"]
    if not matches:
        boundary = None
        if args.launch_result and Path(args.launch_result).is_file():
            try:
                boundary = read_json(args.launch_result)
            except (OSError, ValueError) as error:
                boundary = {"error": "launch result unreadable: " + str(error)}
        stage.write("result-extract.json", {"stage": "read-result", "ok": False, "exitCode": 1,
                                            "error": "result JSON missing (native load failure boundary; no JSON manufactured)",
                                            "copyResult": result, "launchResult": boundary,
                                            "launchStdout": (boundary or {}).get("stdout"),
                                            "launchStderr": (boundary or {}).get("stderr")})
        print(json.dumps({"ok": False, "error": "result JSON missing; native load boundary",
                          "launchResult": boundary}))
        return 1
    if len(matches) > 1:
        stage.write("result-extract.json", {"stage": "read-result", "ok": False, "exitCode": 1,
                                            "error": "expected exactly one " + args.run + ".json",
                                            "found": [str(p) for p in matches],
                                            "copyResult": result})
        print(json.dumps({"ok": False, "error": "expected exactly one " + args.run + ".json",
                          "found": [str(p) for p in matches]}))
        return 1
    try:
        payload = read_json(matches[0])
    except (OSError, ValueError) as error:
        stage.write("result-extract.json", {"stage": "read-result", "ok": False, "exitCode": 1,
                                            "error": "result json unreadable: " + str(error),
                                            "copyResult": result})
        return 1
    problems = result_problems(payload, args.run, args.nonce, args.expected_version)
    failure = payload.get("error") if payload.get("ok") is False else None
    stage.write("result-extract.json", {"stage": "read-result", "ok": not problems,
                                        "exitCode": 0 if not problems else 1,
                                        "source": str(matches[0]), "sha256": sha(matches[0]),
                                        "payloadOk": payload.get("ok"), "failure": failure,
                                        "problems": problems,
                                        "copyResult": result, "copyStdout": result.get("stdout"),
                                        "copyStderr": result.get("stderr")})
    print(json.dumps({"ok": not problems, "source": str(matches[0]), "problems": problems}))
    return 0 if not problems else 1


ENTITLEMENT_HELPER = '''#!/usr/bin/env python3
import plistlib
import sys

source, target = sys.argv[1], sys.argv[2]
with open(source, "rb") as stream:
    ent = plistlib.load(stream)
ent["application-identifier"] = "@@TEAM@@.@@BUNDLE@@"
ent["com.apple.developer.team-identifier"] = "@@TEAM@@"
ent["keychain-access-groups"] = ["@@TEAM@@.@@BUNDLE@@"]
ent["get-task-allow"] = True
with open(target, "wb") as stream:
    plistlib.dump(ent, stream)
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--bundle", default=os.environ.get("RUNE_BUNDLE", ""))
    parser.add_argument("--udid", default=os.environ.get("RUNE_UDID", ""))
    parser.add_argument("--identity", default=os.environ.get("RUNE_IDENTITY", ""))
    parser.add_argument("--team", default=os.environ.get("RUNE_TEAM", ""))
    parser.add_argument("--codesign-bin", default="/usr/bin/codesign")
    parser.add_argument("--security-bin", default="/usr/bin/security")
    parser.add_argument("--plutil-bin", default="/usr/bin/plutil")
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--xcrun-bin", default="/usr/bin/xcrun")
    parser.add_argument("--open-bin", default="/usr/bin/open")
    parser.add_argument("--nm-bin", default="/usr/bin/nm")
    parser.add_argument("--lldb-bin", default="/usr/bin/lldb")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("bundle-verify")
    p.add_argument("--app", required=True)
    p.add_argument("--ready", required=True)

    p = sub.add_parser("sign-plan")
    p.add_argument("--app", required=True)
    p.add_argument("--sign-dir", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--executable", required=True)

    p = sub.add_parser("sign-collect")
    p.add_argument("--sign-dir", required=True)
    p.add_argument("--app", required=True)
    p.add_argument("--signed-app", required=True)
    p.add_argument("--executable", required=True)
    p.add_argument("--wait", type=int, default=0)

    p = sub.add_parser("sign-verify")
    p.add_argument("--signed-app", required=True)
    p.add_argument("--sign-receipt")

    p = sub.add_parser("install")
    p.add_argument("--signed-app", required=True)
    p.add_argument("--sign-verify-result")

    p = sub.add_parser("gen-payload")
    p.add_argument("--generator", required=True)
    p.add_argument("--version", required=True, choices=("A", "B"))
    p.add_argument("--sources", required=True)
    p.add_argument("--host-app", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--install-result", required=True)
    p.add_argument("--sign-verify-result", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--nonce", required=True)
    p.add_argument("--runtime-root")
    p.add_argument("--framework-root")
    p.add_argument("--dotnet")
    p.add_argument("--csc")
    p.add_argument("--crossgen2")
    p.add_argument("--device-udid")
    p.add_argument("--bundle-id")
    p.add_argument("--generator-arg", action="append", default=[],
                   help="additional generator argv tokens for the finalized native CLI")

    p = sub.add_parser("compose-payload")
    p.add_argument("--payload-root", required=True)
    p.add_argument("--run-a", required=True)
    p.add_argument("--run-b", required=True)
    p.add_argument("--nonce-a", required=True)
    p.add_argument("--nonce-b", required=True)
    p.add_argument("--a-dir", required=True)
    p.add_argument("--b-dir", required=True)
    p.add_argument("--install-receipt-sha256", required=True)

    p = sub.add_parser("sign-payload")
    p.add_argument("--payload-root", required=True)
    p.add_argument("--signed-payload-root", required=True)

    p = sub.add_parser("sign-collect-payload")
    p.add_argument("--payload-root", required=True)
    p.add_argument("--signed-payload-root", required=True)
    p.add_argument("--wait", type=int, default=0)

    p = sub.add_parser("seal-payload")
    p.add_argument("--payload-root", required=True)
    p.add_argument("--signed-payload-root", required=True)

    p = sub.add_parser("push-payload")
    p.add_argument("--payload-root", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--nonce")
    p.add_argument("--allow-unsigned", action="store_true")

    p = sub.add_parser("launch")
    p.add_argument("--payload", required=True)
    p.add_argument("--nonce", required=True)
    p.add_argument("--expected-version", required=True, choices=("A", "B"))
    p.add_argument("--owner", required=True)
    p.add_argument("--documents")
    p.add_argument("--symbol", default="")
    p.add_argument("--console", action="store_true")
    p.add_argument("--env", action="append")
    p.add_argument("--timeout", type=int, default=600)

    p = sub.add_parser("lldb-arm")
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--timeout", type=int, default=600)

    p = sub.add_parser("read-result")
    p.add_argument("--run", required=True)
    p.add_argument("--nonce")
    p.add_argument("--expected-version", choices=("A", "B"))
    p.add_argument("--launch-result")

    args = parser.parse_args()
    handlers = {"bundle-verify": cmd_bundle_verify, "sign-plan": cmd_sign_plan,
                "sign-collect": cmd_sign_collect, "sign-verify": cmd_sign_verify,
                "install": cmd_install, "gen-payload": cmd_gen_payload,
                "compose-payload": cmd_compose_payload, "sign-payload": cmd_sign_payload,
                "sign-collect-payload": cmd_sign_collect_payload, "seal-payload": cmd_seal_payload,
                "push-payload": cmd_push_payload, "launch": cmd_launch,
                "lldb-arm": cmd_lldb_arm, "read-result": cmd_read_result}
    return handlers[args.command](args, args.evidence)


if __name__ == "__main__":
    sys.exit(main())
