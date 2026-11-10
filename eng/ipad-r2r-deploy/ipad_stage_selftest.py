#!/usr/bin/env python3
"""Behavioural self-tests for ipad_stage.py v3. Uses fake executables only."""
import hashlib
import json
import os
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE / "ipad_stage.py"
TEAM = "TESTTEAM01"
BUNDLE = "org.example.runeclr.test"
UDID = "00000000-0000000000000001"
IDENTITY = hashlib.sha1(b"fake-certificate").hexdigest().upper()
EXECUTABLE = "TrustedUpdateHost"
ASSEMBLY = "TrustedUpdate.Entry.dll"
INPUTS = ("TrustedUpdate.Update.dll", "TrustedUpdate.Contract.dll",
          "TrustedUpdate.AnchorHost.dll", "TrustedUpdate.AnchorEntry.dll")
RESULTS = []


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def note(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else ": " + detail))


def macho(uuid_hex, symbol_value=0x1234):
    body = b"\x00_RTR_HEADER\x00"
    symoff = 32 + 24 + 24 + 24
    stroff = symoff + 16
    data = bytearray(32)
    struct.pack_into("<IiiIIIII", data, 0, 0xFEEDFACF, 0x0100000C, 0, 6, 3, 72, 0, 0)
    data += struct.pack("<IIIIII", 0x32, 24, 2, 0x000F0300, 0x000F0300, 0)
    uuid = bytes.fromhex(uuid_hex)
    data += struct.pack("<II", 0x1B, 24) + uuid
    data += struct.pack("<IIIIII", 0x2, 24, symoff, 1, stroff, len(body))
    data += struct.pack("<IBBhQ", 1, 0x0F, 1, 0, symbol_value)
    data += body
    return bytes(data)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)
    return path


FAKE_CODESIGN = r'''#!/usr/bin/env python3
import os, sys, plistlib
args = sys.argv[1:]
mode = os.environ.get("FAKE_CODESIGN_MODE", "ok")
if mode == "exit":
    sys.exit(int(os.environ.get("FAKE_CODESIGN_EXIT", "1")))
if "--verify" in args:
    sys.exit(0)
if "-dv" in args:
    sys.stderr.write("Executable=" + os.environ.get("FAKE_APP", "") + "\n")
    sys.stderr.write("Identifier=" + os.environ.get("FAKE_DV_ID", "org.example.runeclr.test") + "\n")
    sys.stderr.write("TeamIdentifier=" + os.environ.get("FAKE_DV_TEAM", "TESTTEAM01") + "\n")
    authority = os.environ.get("FAKE_DV_AUTH", "Apple Development: Jiahao Shi (ABCDE)")
    if authority != "none":
        sys.stderr.write("Authority=" + authority + "\n")
        sys.stderr.write("Authority=Apple Worldwide Developer Relations Certification Authority\n")
    sys.exit(0)
if any(item.startswith("--extract-certificates") for item in args):
    option = next(item for item in args if item.startswith("--extract-certificates"))
    prefix = option.split("=", 1)[1] if "=" in option else args[args.index(option) + 1]
    cert = os.environ.get("FAKE_CERT", "fake-certificate").encode()
    with open(prefix + "0", "wb") as stream:
        stream.write(cert)
    sys.exit(0)
if "--entitlements" in args and "--force" not in args and "--sign" not in args:
    ent = {"application-identifier": os.environ.get("FAKE_ENT_APPID", "TESTTEAM01.org.example.runeclr.test"),
           "com.apple.developer.team-identifier": os.environ.get("FAKE_ENT_TEAM", "TESTTEAM01"),
           "get-task-allow": os.environ.get("FAKE_ENT_GTA", "true") == "true"}
    sys.stdout.buffer.write(plistlib.dumps(ent))
    sys.exit(0)
if "--force" in args or "--sign" in args:
    if os.environ.get("FAKE_SIGN_FAIL") == "1":
        sys.stderr.write("fake codesign signing failure\n")
        sys.exit(1)
    target = args[-1]
    if os.path.isdir(target):
        os.makedirs(os.path.join(target, "_CodeSignature"), exist_ok=True)
        with open(os.path.join(target, "_CodeSignature", "CodeResources"), "wb") as stream:
            stream.write(b"fake-signature")
    else:
        with open(target, "ab") as stream:
            stream.write(b"FAKESIG")
    sys.exit(0)
sys.exit(0)
'''


FAKE_SECURITY = r'''#!/usr/bin/env python3
import os, sys, plistlib
if os.environ.get("FAKE_CMS_EXIT") == "1":
    sys.exit(1)
if os.environ.get("FAKE_CMS_INVALID") == "1":
    sys.stdout.write("this is not a plist\n")
    sys.exit(0)
profile = {
    "TeamIdentifier": [os.environ.get("FAKE_CMS_TEAM", "TESTTEAM01")],
    "ExpirationDate": __import__("datetime").datetime(2027, 11, 10, 0, 0, 0),
    "ProvisionedDevices": [os.environ.get("FAKE_CMS_UDID", "00000000-0000000000000001")],
    "Entitlements": {
        "application-identifier": os.environ.get("FAKE_CMS_APPID", "TESTTEAM01.*"),
        "com.apple.developer.team-identifier": os.environ.get("FAKE_CMS_TEAM", "TESTTEAM01"),
        "get-task-allow": os.environ.get("FAKE_CMS_GTA", "true") == "true",
    },
}
sys.stdout.buffer.write(plistlib.dumps(profile))
'''


FAKE_PLUTIL = r'''#!/usr/bin/env python3
import plistlib, sys
args = sys.argv[1:]
source = args[-1]
target = args[args.index("-o") + 1]
with open(source, "rb") as stream:
    profile = plistlib.load(stream)
with open(target, "wb") as stream:
    plistlib.dump(profile.get("Entitlements", {}), stream)
'''



FAKE_NM = r'''#!/usr/bin/env python3
import sys
print("0000000000001000 T _Business.Execute")
print("0000000000001100 t helper")
'''

FAKE_LLDB = r'''#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
marker = os.environ.get("FAKE_LLDB_MARKER", "")
if marker:
    with open(marker, "a") as stream:
        stream.write(" ".join(args) + "\n")
print("lldb batch ok")
sys.exit(int(os.environ.get("FAKE_LLDB_EXIT", "0")))
'''

FAKE_OPEN = r'''#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
script = args[-1]
marker = os.environ.get("FAKE_OPEN_MARKER", "")
if marker:
    with open(marker, "a") as stream:
        stream.write(script + "\n")
sys.exit(int(os.environ.get("FAKE_OPEN_EXIT", "0")))
'''


FAKE_XCRUN = r'''#!/usr/bin/env python3
import json, os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
root = Path(os.environ["FAKE_DEVICE_ROOT"])
bundle = os.environ.get("FAKE_BUNDLE", "org.example.runeclr.test")
udid = os.environ.get("FAKE_UDID", "00000000-0000000000000001")
receipt = None
if "--json-output" in args:
    receipt = Path(args[args.index("--json-output") + 1])


def emit(outcome="success", extra=None):
    if receipt is None:
        return
    payload = {"info": {"outcome": outcome}, "result": extra or {}}
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(payload), encoding="utf-8")


if args[:3] == ["devicectl", "device", "install"]:
    mode = os.environ.get("FAKE_INSTALL", "ok")
    if mode == "exit":
        sys.exit(1)
    if mode == "nojson":
        sys.exit(0)
    if mode == "outcome":
        emit("failed")
        sys.exit(0)
    paths = [Path(item) for item in args if item.startswith("/") and Path(item).exists()]
    app = paths[0] if paths else Path("/")
    emit("success", {"installedApplication": {"bundleIdentifier": os.environ.get("FAKE_INSTALL_BUNDLE", bundle)},
                     "deviceIdentifier": udid, "installationURL": str(app)})
    sys.exit(0)
if args[:3] == ["devicectl", "device", "copy"]:
    direction = args[3]
    mode = os.environ.get("FAKE_COPY", "ok")
    if mode == "exit":
        sys.exit(1)
    if mode == "nojson":
        sys.exit(0)
    source = Path(args[args.index("--source") + 1])
    destination = Path(args[args.index("--destination") + 1])
    if direction == "to":
        device_path = root / destination
        device_path.parent.mkdir(parents=True, exist_ok=True)
        device_path.write_bytes(source.read_bytes())
    else:
        device_source = root / source
        if device_source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            for item in device_source.rglob("*"):
                if item.is_file():
                    target = destination / item.relative_to(device_source)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"corrupt" if mode == "corrupt" else item.read_bytes())
        else:
            target = destination if destination.suffix else destination / device_source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"corrupt" if mode == "corrupt" else device_source.read_bytes())
    if os.environ.get("FAKE_FAIL_NAME") and os.environ["FAKE_FAIL_NAME"] in str(source):
        sys.exit(2)
    emit("success", {"deviceIdentifier": udid})
    sys.exit(0)
if args[:3] == ["devicectl", "device", "process"]:
    if receipt is not None:
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({"result": {"process": {"pid": 4242}}}), encoding="utf-8")
    print("RUNECLR_PATH_OK pid=4242 runId=" + os.environ.get("FAKE_RUN", "run") + " payload=" + os.environ.get("FAKE_PAYLOAD", ""))
    sys.exit(0)
sys.exit(0)
'''


FAKE_GENERATOR = r'''#!/usr/bin/env python3
import hashlib, json, os, struct, sys
args = sys.argv[1:]
if os.environ.get("FAKE_GEN_EXIT") == "1":
    sys.exit(1)
def option(name):
    return args[args.index(name) + 1]
version = option("--version")
sources = __import__("pathlib").Path(option("--sources"))
host_app = __import__("pathlib").Path(option("--host-app"))
output = __import__("pathlib").Path(option("--output"))
nonce = option("--nonce")
receipt = json.loads(__import__("pathlib").Path(option("--install-receipt")).read_text())
required = ("status", "installed", "signed", "bundleId", "deviceUdid", "platform",
            "installedUtc", "appDigestSha256", "archive", "rawReceiptPath", "rawReceiptSha256")
for key in required:
    if key not in receipt:
        raise SystemExit("derived receipt missing " + key)
if receipt["status"] != "installed" or receipt["installed"] is not True or receipt["signed"] is not True:
    raise SystemExit("derived receipt flags invalid")
if receipt["platform"] != 2:
    raise SystemExit("derived receipt platform invalid")
raw = json.loads(__import__("pathlib").Path(receipt["rawReceiptPath"]).read_text())
if raw.get("success") is not True or raw.get("bundleId") != receipt["bundleId"] or raw.get("deviceUdid") != receipt["deviceUdid"]:
    raise SystemExit("raw receipt wrapper invalid")
if hashlib.sha256(__import__("pathlib").Path(receipt["rawReceiptPath"]).read_bytes()).hexdigest() != receipt["rawReceiptSha256"]:
    raise SystemExit("raw receipt hash invalid")
if len(nonce) != 32:
    raise SystemExit("nonce invalid")
if output.exists():
    raise SystemExit("output exists")
if not host_app.is_dir() or not sources.is_dir():
    raise SystemExit("host app or sources missing")
output.mkdir(parents=True)
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def macho(uuid_hex):
    body = b"\x00_RTR_HEADER\x00"
    cmds = []
    seg = struct.pack("<II", 0x19, 72) + b"__TEXT".ljust(16, b"\x00")
    seg += struct.pack("<QQQQ", 0x100000000, 0x1000, 0, 0x1000) + struct.pack("<IIII", 7, 5, 0, 0)
    cmds.append(seg)
    cmds.append(struct.pack("<IIIIII", 0x32, 24, 2, 0x000F0300, 0x000F0300, 0))
    cmds.append(struct.pack("<II", 0x1B, 24) + bytes.fromhex(uuid_hex))
    sizeofcmds = sum(len(c) for c in cmds) + 24
    symoff = 32 + sizeofcmds
    stroff = symoff + 16
    data = bytearray(32)
    struct.pack_into("<IiiIIIII", data, 0, 0xFEEDFACF, 0x0100000C, 0, 6, 1 + len(cmds), sizeofcmds, 0, 0)
    for c in cmds:
        data += c
    data += struct.pack("<IIIIII", 0x2, 24, symoff, 1, stroff, len(body))
    data += struct.pack("<IBBhQ", 1, 0x0F, 1, 0, 0x1000)
    data += body
    return bytes(data)
deploy = output / "deploy"
deploy.mkdir()
uuid = ("%032x" % (0xA000 + ord(version)))
owner_name = "TrustedUpdate." + version + ".r2r.dylib"
files = {"TrustedUpdate.Update.dll": ("UPDATE-" + version).encode(),
         "TrustedUpdate.Private.dll": ("PRIVATE-" + version).encode(),
         "TrustedUpdate.IlOnlyHelper.dll": ("HELPER-" + version).encode()}
for name, content in files.items():
    (deploy / name).write_bytes(content)
owner = deploy / owner_name
owner.write_bytes(macho(uuid))
payload = {name: {"sha256": sha(deploy / name), "bytes": (deploy / name).stat().st_size}
           for name in list(files) + [owner_name]}
lines = [name + " " + payload[name]["sha256"] for name in sorted(payload)]
(deploy / "payload-files.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
manifest = {"schema": "runeclr.ipados.r2r.owner.v2", "version": version,
            "owner": {"name": owner_name, "rawSha256": payload[owner_name]["sha256"],
                      "bytes": payload[owner_name]["bytes"], "uuid": uuid, "platform": 2,
                      "text": {"vmaddr": 0x100000000, "vmsize": 0x1000, "fileoff": 0, "filesize": 0x1000},
                      "rtrHeader": {"symbol": "_RTR_HEADER", "value": 0x1000, "section": 1,
                                    "extra": {"source": "nm"}},
                      "signedSha256": None},
            "components": {name: payload[name] for name in files},
            "payload": payload, "payloadFilesSha256": sha(deploy / "payload-files.txt"),
            "deployable": sorted(payload) + ["payload-files.txt"], "nonce": nonce}
(output / "owner.json").write_text(json.dumps(manifest), encoding="utf-8")
print(json.dumps({"status": "PASS", "version": version, "nonce": nonce}))
'''


def make_profile(path, team=TEAM, udid=UDID, year=2027, gta=True, appid=None):
    profile = {"TeamIdentifier": [team],
               "ExpirationDate": __import__("datetime").datetime(year, 11, 10),
               "ProvisionedDevices": [udid],
               "Entitlements": {"application-identifier": appid or TEAM + ".*",
                                "com.apple.developer.team-identifier": team,
                                "get-task-allow": gta}}
    write(path, plistlib.dumps(profile))


def make_app(root, bundle=BUNDLE, executable=EXECUTABLE):
    app = root / "TrustedUpdateHost.app"
    write(app / "Info.plist", plistlib.dumps({"CFBundleIdentifier": bundle,
                                              "CFBundleExecutable": executable}))
    write(app / executable, b"EXECUTABLE")
    write(app / ASSEMBLY, b"ENTRY-IL")
    write(app / "TrustedUpdate.host.dylib", macho("11" * 16))
    write(app / "Frameworks" / "framework.dylib", macho("22" * 16))
    return app


def make_ready(app, root, bundle=BUNDLE, executable=EXECUTABLE, scheme="nested"):
    entries = []
    for path in sorted(p for p in app.rglob("*") if p.is_file()):
        entries.append({"path": path.relative_to(app).as_posix(), "sha256": sha(path),
                        "size": path.stat().st_size})
    if scheme == "nested":
        digest = hashlib.sha256()
        for entry in sorted(entries, key=lambda item: item["path"]):
            digest.update(entry["path"].encode() + b"\x00" + entry["sha256"].encode()
                          + b"\x00" + str(entry["size"]).encode() + b"\n")
        inventory = {"scheme": "sha256", "digest": digest.hexdigest(), "entries": entries,
                     "files": len(entries), "bytes": sum(e["size"] for e in entries),
                     "file": str(root / "inventory.json")}
        write(root / "inventory.json", json.dumps(inventory, indent=2))
        ready = {"schema": "runeclr.ipados.r2r.host-ready.v1", "bundleId": bundle,
                 "executable": executable, "signed": False,
                 "managedEntry": {"assembly": ASSEMBLY,
                                  "sha256": sha(app / ASSEMBLY)},
                 "inventory": inventory}
    else:
        ready = {"schema": "runeclr.ipad.host-ready.v1", "bundleId": bundle,
                 "executable": executable, "signed": False, "fileCount": len(entries),
                 "managedEntry": {"assembly": ASSEMBLY, "sha256": sha(app / ASSEMBLY)},
                 "files": {entry["path"]: {"sha256": entry["sha256"], "size": entry["size"]}
                           for entry in entries}}
    return write(root / "READY.json", json.dumps(ready, indent=2))


def fakes(root):
    directory = root / "bin"
    directory.mkdir()
    for name, body in (("codesign", FAKE_CODESIGN), ("security", FAKE_SECURITY),
                       ("plutil", FAKE_PLUTIL), ("open", FAKE_OPEN),
                       ("xcrun", FAKE_XCRUN), ("nm", FAKE_NM), ("lldb", FAKE_LLDB),
                       ("generate_update.py", FAKE_GENERATOR)):
        path = write(directory / name, body)
        path.chmod(0o755)
    return directory


def run_tool(evidence, command, *args, env=None):
    argv = [sys.executable, str(TOOL), "--evidence", str(evidence),
            "--bundle", BUNDLE, "--udid", UDID, "--team", TEAM, "--identity", IDENTITY,
            command] + [str(item) for item in args]
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return subprocess.run(argv, capture_output=True, text=True, env=merged, timeout=300)


def tool(evidence, command, *args, env=None, xcrun=None, dry_run=False):
    binary = evidence.parent / "bin"
    argv = [sys.executable, str(TOOL), "--evidence", str(evidence),
            "--bundle", BUNDLE, "--udid", UDID, "--team", TEAM, "--identity", IDENTITY,
            "--codesign-bin", str(binary / "codesign"),
            "--security-bin", str(binary / "security"),
            "--plutil-bin", str(binary / "plutil"),
            "--python-bin", sys.executable,
            "--xcrun-bin", str(xcrun or (binary / "xcrun")),
            "--open-bin", str(binary / "open"),
            "--nm-bin", str(binary / "nm"),
            "--lldb-bin", str(binary / "lldb")] + (["--dry-run"] if dry_run else []) \
            + [command] + [str(item) for item in args]
    merged = dict(os.environ)
    merged.setdefault("FAKE_DEVICE_ROOT", str(evidence.parent / "device"))
    merged.setdefault("FAKE_BUNDLE", BUNDLE)
    merged.setdefault("FAKE_UDID", UDID)
    if env:
        merged.update(env)
    return subprocess.run(argv, capture_output=True, text=True, env=merged, timeout=300)


def check(name, proc, expect_zero, needle=None):
    blob = (proc.stdout or "") + (proc.stderr or "")
    ok = (proc.returncode == 0) == expect_zero
    detail = ""
    if ok and needle and needle not in blob:
        ok = False
        detail = "missing " + repr(needle) + " in " + blob[-400:]
    if not ok and not detail:
        detail = "rc=" + str(proc.returncode) + " " + blob[-400:]
    note(name, ok, detail)


def latest(evidence, name):
    items = sorted((evidence / name).glob("*"))
    return items[-1] if items else None


def latest_ok(evidence, name):
    for directory in sorted((evidence / name).glob("*"), key=lambda item: item.stat().st_mtime,
                            reverse=True):
        try:
            record = json.loads((directory / "result.json").read_text())
        except (OSError, ValueError):
            continue
        if record.get("ok") is True:
            return directory
    return None


def main():
    global FAKE_SECURITY, FAKE_XCRUN
    evidence = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
    if evidence.exists():
        shutil.rmtree(evidence)
    evidence.mkdir(parents=True)
    shutil.rmtree(evidence.parent / "bin", ignore_errors=True)
    shutil.rmtree(evidence.parent / "device", ignore_errors=True)
    FAKE_SECURITY = FAKE_SECURITY.replace(
        "datetime(2027, 11, 10, 0, 0, 0)",
        "datetime(int(os.environ.get('FAKE_CMS_YEAR', '2027')), 11, 10, 0, 0, 0)")
    FAKE_XCRUN = FAKE_XCRUN.replace('''        device_source = root / source
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / device_source.name
        if mode == "corrupt":
            target.write_bytes(b"corrupt")
        else:
            target.write_bytes(device_source.read_bytes())''', '''        device_source = root / source
        destination.mkdir(parents=True, exist_ok=True)
        if device_source.is_dir():
            for item in device_source.rglob("*"):
                if item.is_file():
                    target = destination / item.relative_to(device_source)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"corrupt" if mode == "corrupt" else item.read_bytes())
        else:
            target = destination / device_source.name
            target.write_bytes(b"corrupt" if mode == "corrupt" else device_source.read_bytes())''')
    binary = fakes(evidence.parent)
    fixture = evidence / "fixture"
    app = make_app(fixture)
    ready = make_ready(app, fixture)
    profile = write(fixture / "profile.mobileprovision", b"PROFILE")
    device = evidence.parent / "device"

    check("bundle-verify/nested-valid", tool(evidence, "bundle-verify", "--app", app, "--ready", ready), True)
    flat_root = evidence / "flat"
    flat_app = make_app(flat_root)
    flat_ready = make_ready(flat_app, flat_root, scheme="flat")
    check("bundle-verify/flat-valid", tool(evidence, "bundle-verify", "--app", flat_app, "--ready", flat_ready), True)
    bad_root = evidence / "bad-schema"
    bad_app = make_app(bad_root)
    bad_ready = make_ready(bad_app, bad_root)
    payload = json.loads(bad_ready.read_text())
    payload["schema"] = "unknown"
    bad_ready.write_text(json.dumps(payload))
    check("bundle-verify/unknown-schema", tool(evidence, "bundle-verify", "--app", bad_app, "--ready", bad_ready), False)
    trav_root = evidence / "trav"
    trav_app = make_app(trav_root)
    trav_ready = make_ready(trav_app, trav_root)
    inv = json.loads((trav_root / "inventory.json").read_text())
    inv["entries"][0]["path"] = "../escape"
    (trav_root / "inventory.json").write_text(json.dumps(inv))
    check("bundle-verify/traversal", tool(evidence, "bundle-verify", "--app", trav_app, "--ready", trav_ready), False)
    extra_root = evidence / "extra"
    extra_app = make_app(extra_root)
    extra_ready = make_ready(extra_app, extra_root)
    write(extra_app / "unlisted.bin", b"x")
    check("bundle-verify/extra-file", tool(evidence, "bundle-verify", "--app", extra_app, "--ready", extra_ready), False)
    size_root = evidence / "size"
    size_app = make_app(size_root)
    size_ready = make_ready(size_app, size_root)
    inv = json.loads((size_root / "inventory.json").read_text())
    inv["entries"][0]["size"] += 1
    digest = hashlib.sha256()
    for entry in sorted(inv["entries"], key=lambda item: item["path"]):
        digest.update(entry["path"].encode() + b"\x00" + entry["sha256"].encode()
                      + b"\x00" + str(entry["size"]).encode() + b"\n")
    inv["digest"] = digest.hexdigest()
    (size_root / "inventory.json").write_text(json.dumps(inv))
    payload = json.loads(size_ready.read_text())
    payload["inventory"]["digest"] = inv["digest"]
    size_ready.write_text(json.dumps(payload))
    check("bundle-verify/size-mismatch", tool(evidence, "bundle-verify", "--app", size_app, "--ready", size_ready), False)
    check("bundle-verify/app-missing", tool(evidence, "bundle-verify", "--app", evidence / "nope", "--ready", ready), False)

    signed = evidence / "signed.app"
    shutil.copytree(app, signed)
    write(signed / "embedded.mobileprovision", b"PROFILE")
    sv = ["sign-verify", "--signed-app", signed]
    check("sign-verify/success", tool(evidence, *sv), True)
    check("sign-verify/wrong-team", tool(evidence, *sv, env={"FAKE_CMS_TEAM": "OTHER"}), False, "team")
    check("sign-verify/wrong-udid", tool(evidence, *sv, env={"FAKE_CMS_UDID": "OTHER"}), False, "UDID")
    check("sign-verify/expired", tool(evidence, *sv, env={"FAKE_CMS_YEAR": "2020"}), False, "expired")
    check("sign-verify/no-gta", tool(evidence, *sv, env={"FAKE_CMS_GTA": "false"}), False, "get-task-allow")
    check("sign-verify/entitlement-mismatch", tool(evidence, *sv, env={"FAKE_ENT_APPID": "TESTTEAM01.other"}), False, "application-identifier")
    check("sign-verify/cms-invalid", tool(evidence, *sv, env={"FAKE_CMS_INVALID": "1"}), False, "decode")
    check("sign-verify/no-authority", tool(evidence, *sv, env={"FAKE_DV_AUTH": "none"}), False, "authority")
    check("sign-verify/identity-fingerprint", tool(evidence, *sv, env={"FAKE_CERT": "other-cert"}), False, "fingerprint")
    check("sign-verify/missing-receipt", tool(evidence, *sv, "--sign-receipt", evidence / "missing.json"), False, "receipt")

    sign_dir = evidence / "sign-primary"
    sign_dir.mkdir()
    (sign_dir / app.name).mkdir()
    check("sign-plan/refuse-existing-dest", tool(evidence, "sign-plan", "--app", app, "--sign-dir", sign_dir,
                                                 "--profile", profile, "--executable", EXECUTABLE), False, "already exists")
    dry_dir = evidence / "sign-dry"
    dry_proc = tool(evidence, "sign-plan", "--app", app, "--sign-dir", dry_dir,
                    "--profile", profile, "--executable", EXECUTABLE, dry_run=True)
    check("dry-run/sign-plan-renders", dry_proc, True, "RENDERED_ONLY")
    note("dry-run/sign-plan-no-side-effect", not dry_dir.exists() and not (dry_dir / app.name).exists(),
         "sign dir or destination was created")
    sign_dir2 = evidence / "sign-primary-2"
    marker = evidence / "open-marker.txt"
    proc = tool(evidence, "sign-plan", "--app", app, "--sign-dir", sign_dir2, "--profile", profile,
                "--executable", EXECUTABLE, env={"FAKE_OPEN_MARKER": str(marker)})
    check("sign-plan/launch", proc, True, "AWAITING_GUI_SIGN")
    script = sorted(sign_dir2.glob("sign-primary-*.command"))[0]
    receipt = sign_dir2 / "sign-receipt.json"
    fresh = dict(os.environ, FAKE_DEVICE_ROOT=str(device), FAKE_BUNDLE=BUNDLE, FAKE_UDID=UDID)
    gui = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=fresh, timeout=300)
    check("sign-plan/gui-success-exit", gui, True)
    check("sign-collect/success", tool(evidence, "sign-collect", "--sign-dir", sign_dir2,
                                      "--app", app, "--signed-app", sign_dir2 / app.name,
                                      "--executable", EXECUTABLE), True)
    check("sign-verify/with-receipt", tool(evidence, "sign-verify", "--signed-app", sign_dir2 / app.name,
                                           "--sign-receipt", receipt), True)
    fail_dir = evidence / "sign-fail"
    tool(evidence, "sign-plan", "--app", app, "--sign-dir", fail_dir, "--profile", profile,
         "--executable", EXECUTABLE, env={"FAKE_OPEN_MARKER": str(marker)})
    fail_script = sorted(fail_dir.glob("sign-primary-*.command"))[0]
    subprocess.run(["bash", str(fail_script)], capture_output=True, text=True,
                   env=dict(fresh, FAKE_SIGN_FAIL="1"), timeout=300)
    check("sign-plan/gui-failure-exit", tool(evidence, "sign-collect", "--sign-dir", fail_dir,
                                             "--app", app, "--signed-app", fail_dir / app.name,
                                             "--executable", EXECUTABLE), False, "not 0")

    check("install/spawn-error", tool(evidence, "install", "--signed-app", signed,
                                     xcrun=evidence / "missing-xcrun"), False)
    check("install/no-json", tool(evidence, "install", "--signed-app", signed, env={"FAKE_INSTALL": "nojson"}), False)
    check("install/outcome-failed", tool(evidence, "install", "--signed-app", signed, env={"FAKE_INSTALL": "outcome"}), False)
    check("install/wrong-bundle", tool(evidence, "install", "--signed-app", signed,
                                       env={"FAKE_INSTALL_BUNDLE": "other.bundle"}), False)
    check("install/success", tool(evidence, "install", "--signed-app", signed), True)
    install_stage = latest_ok(evidence, "install")
    install_result = install_stage / "result.json"
    install_payload = json.loads(install_result.read_text())
    note("install/child-pid-recorded", isinstance(install_payload.get("childPid"), int)
         and install_payload["childPid"] > 0, repr(install_payload.get("childPid")))

    sv_stage = latest_ok(evidence, "sign-verify")
    sv_result = sv_stage / "result.json"
    host_app = sign_dir2 / app.name
    sources = evidence / "sources"
    write(sources / "Program.cs", "// v2 source fixture")
    write(sources / "Update.cs", "// v2 source fixture 2")
    nonce_a = "a" * 32
    nonce_b = "b" * 32

    def gen_args(version, run, nonce, output):
        return ["gen-payload", "--generator", binary / "generate_update.py",
                "--version", version, "--sources", sources, "--host-app", host_app,
                "--install-result", install_result, "--sign-verify-result", sv_result,
                "--run", run, "--nonce", nonce, "--output", output]

    broken = evidence / "install-broken.json"
    for name, mutate in (
        ("exit-code", lambda p: p.update(exitCode=1)),
        ("dry-run", lambda p: p.update(dryRun=True)),
        ("outcome", lambda p: p.update(jsonOutcome="failed")),
        ("missing-receipt", lambda p: p.update(jsonPath=str(evidence / "missing-receipt.json"))),
        ("hash", lambda p: p.update(jsonSha256="0" * 64)),
        ("bundle", lambda p: p.update(bundle="other.bundle")),
        ("udid", lambda p: p.update(udid="other-udid")),
    ):
        payload = json.loads(install_result.read_text())
        mutate(payload)
        broken.write_text(json.dumps(payload))
        args = gen_args("A", "run-reject", nonce_a, evidence / ("gen-" + name))
        args[args.index(install_result)] = str(broken)
        check("gen-payload/reject-" + name, tool(evidence, *args), False)
    bad_verify = evidence / "sign-verify-broken.json"
    verify_payload = json.loads(sv_result.read_text())
    verify_payload["ok"] = False
    bad_verify.write_text(json.dumps(verify_payload))
    args = gen_args("A", "run-reject", nonce_a, evidence / "gen-bad-verify")
    args[args.index(sv_result)] = str(bad_verify)
    check("gen-payload/reject-sign-verify", tool(evidence, *args), False)
    check("gen-payload/reject-nonce", tool(evidence, *gen_args("A", "run-reject", "abc",
                                                               evidence / "gen-bad-nonce")), False)

    gen_a = evidence / "gen-a"
    gen_b = evidence / "gen-b"
    check("gen-payload/accept-a", tool(evidence, *gen_args("A", "run-A", nonce_a, gen_a)),
          True, "run-A")
    derived_a = sha(latest_ok(evidence, "gen-payload") / "generator-install-receipt.json")
    derived_record = json.loads((latest_ok(evidence, "gen-payload")
                                 / "generator-install-receipt.json").read_text())
    derived_wrapper = json.loads(Path(derived_record["rawReceiptPath"]).read_text())
    note("gen-payload/derived-top-level",
         derived_record.get("platform") == 2
         and derived_record.get("rawReceiptPath")
         and derived_record.get("rawReceiptSha256") == sha(Path(derived_record["rawReceiptPath"]))
         and derived_record.get("archive", {}).get("sha256") == derived_record.get("rawReceiptSha256")
         and derived_wrapper.get("success") is True
         and derived_wrapper.get("bundleId") == BUNDLE
         and derived_wrapper.get("deviceUdid") == UDID,
         "derived receipt top-level contract mismatch")
    check("gen-payload/accept-b", tool(evidence, *gen_args("B", "run-B", nonce_b, gen_b)),
          True, "run-B")
    passthrough = evidence / "gen-passthrough"
    check("gen-payload/config-passthrough",
          tool(evidence, *gen_args("A", "run-pass", "e" * 32, passthrough),
               "--runtime-root", "/tmp/runtime-ref",
               "--framework-root", "/tmp/framework-ref",
               "--dotnet", "/tmp/dotnet",
               "--csc", "/tmp/csc.dll",
               "--crossgen2", "/tmp/crossgen2",
               "--device-udid", "00000000-0000000000000001",
               "--bundle-id", "org.example.runeclr.test"), True)
    pass_request = json.loads((latest_ok(evidence, "gen-payload") / "request.json").read_text())
    pass_argv = pass_request["argv"]
    note("gen-payload/config-passthrough-argv",
         all(token in pass_argv for token in (
             "--runtime-root", "/tmp/runtime-ref", "--framework-root", "/tmp/framework-ref",
             "--dotnet", "/tmp/dotnet", "--csc", "/tmp/csc.dll",
             "--crossgen2", "/tmp/crossgen2", "--udid",
             "00000000-0000000000000001", "--bundle-id",
             "org.example.runeclr.test")),
         "generator config was not passed through")

    payload_root = evidence / "payload-v2"
    compose = ["compose-payload", "--payload-root", payload_root,
               "--run-a", "run-A", "--run-b", "run-B",
               "--nonce-a", nonce_a, "--nonce-b", nonce_b,
               "--a-dir", gen_a, "--b-dir", gen_b,
               "--install-receipt-sha256", derived_a]
    check("compose-payload/v2-success", tool(evidence, *compose), True)
    def compose_bad(label, mutate):
        bad = evidence / ("gen-bad-" + label)
        shutil.copytree(gen_a, bad)
        doc = json.loads((bad / "owner.json").read_text())
        mutate(doc)
        (bad / "owner.json").write_text(json.dumps(doc))
        bad_root = evidence / ("payload-bad-" + label)
        args = ["compose-payload", "--payload-root", bad_root,
                "--run-a", "run-bad-" + label, "--run-b", "run-B",
                "--nonce-a", "c" * 32, "--nonce-b", nonce_b,
                "--a-dir", bad, "--b-dir", gen_b,
                "--install-receipt-sha256", derived_a]
        check("compose-payload/reject-" + label, tool(evidence, *args), False)

    compose_bad("owner-text", lambda d: d["owner"].__setitem__("text", "not-a-dict"))
    compose_bad("payload-list", lambda d: d["payload"].__setitem__(
        "payload-files.txt", {"sha256": "0" * 64, "bytes": 1}))
    compose_bad("payload-hash", lambda d: d.pop("payloadFilesSha256", None))
    compose_bad("rtr-header", lambda d: d["owner"]["rtrHeader"].__setitem__(
        "value", d["owner"]["rtrHeader"]["value"] + 1))
    compose_bad("binary-map", lambda d: d["payload"].pop("TrustedUpdate.Private.dll", None))
    note("gen-payload/rtr-extra-metadata",
         "extra" in json.loads((gen_a / "owner.json").read_text())["owner"]["rtrHeader"],
         "extra rtrHeader metadata was not preserved")
    check("push-payload/no-manifest-refused",
          tool(evidence, "push-payload", "--payload-root", payload_root, "--run", "run-A"),
          False, "manifest missing")
    check("push-payload/no-manifest-run-b",
          tool(evidence, "push-payload", "--payload-root", payload_root, "--run", "run-B"),
          False, "manifest missing")

    signed_root = evidence / "signed-root"
    check("sign-payload/launch", tool(evidence, "sign-payload", "--payload-root", payload_root,
                                      "--signed-payload-root", signed_root), True)
    sign_script = sorted(evidence.glob("signed-root.sign-*.command"))[0]
    gui = subprocess.run(["bash", str(sign_script)], capture_output=True, text=True,
                         env=fresh, timeout=300)
    check("sign-payload/gui", gui, True)
    check("sign-collect-payload/v2-success",
          tool(evidence, "sign-collect-payload", "--payload-root", payload_root,
               "--signed-payload-root", signed_root), True)
    check("seal-payload/v2-success",
          tool(evidence, "seal-payload", "--payload-root", payload_root,
               "--signed-payload-root", signed_root), True)
    owner_doc = json.loads((gen_a / "owner.json").read_text())
    owner_path = gen_a / "deploy" / owner_doc["owner"]["name"]
    check("launch/stop-args", tool(evidence, "launch", "--payload", "run-A", "--nonce", nonce_a,
                                   "--expected-version", "A", "--owner", owner_path), True)
    launch_stage = latest_ok(evidence, "launch")
    launch_request = json.loads((launch_stage / "request.json").read_text())
    launch_argv = launch_request["argv"]
    note("launch/argv-contract",
         "--start-stopped" in launch_argv
         and launch_argv[-4:] == ["--payload", "run-A", "--nonce", nonce_a]
         and launch_argv[-5] == "--",
         "launch argv does not carry start-stopped/payload/nonce in order")
    expected_env = {"RUNECLR_EXPECTED_VERSION": "A", "RUNECLR_GOLDEN_RESULT": "216",
                    "RUNECLR_GOLDEN_PRIVATE": "100", "RUNECLR_GOLDEN_HELPER": "307"}
    note("launch/exact-env", launch_request["environment"] == expected_env,
         "launch environment differs: " + repr(launch_request["environment"]))
    check("launch/forbidden-env", tool(evidence, "launch", "--payload", "run-A",
                                       "--nonce", nonce_a, "--expected-version", "A",
                                       "--owner", owner_path,
                                       "--env", "RUNECLR_FORCE_FAILURE=1"), False, "forbidden")
    check("launch/wrong-nonce", tool(evidence, "launch", "--payload", "run-A", "--nonce", "abc",
                                     "--expected-version", "A", "--owner", owner_path),
          False, "nonce")
    check("lldb-arm/pending", tool(evidence, "lldb-arm", "--pid", "4242",
                                   "--symbol", "Business.Execute"), True)
    lldb_request = json.loads((latest_ok(evidence, "lldb-arm") / "request.json").read_text())
    lldb_argv = lldb_request["argv"]
    note("lldb-arm/order",
         lldb_argv[lldb_argv.index("-o") + 1] == "device select " + UDID
         and "device process attach -p 4242" in lldb_argv
         and "breakpoint set -n Business.Execute" in lldb_argv
         and lldb_argv[-1] == "process continue",
         "lldb command order is not device-select -> attach -> breakpoint -> continue")
    final_manifest = json.loads((signed_root / "run-A" / "manifest.json").read_text())
    note("seal-payload/binary-map-excludes-list",
         "payload-files.txt" not in final_manifest["payload"]
         and final_manifest["payloadFilesSha256"] == sha(signed_root / "run-A" / "payload-files.txt"),
         "final payload map includes payload-files.txt or list hash is stale")
    for run in ("run-A", "run-B"):
        signed_text = (signed_root / run / "payload-files.txt").read_text(encoding="utf-8")
        raw_manifest = json.loads((payload_root / (run + ".raw-manifest.json")).read_text())
        signed_record = json.loads((signed_root / (run + ".signed-record.json")).read_text())
        note("seal-payload/payload-files-" + run,
             signed_record["signedSha256"] in signed_text
             and raw_manifest["owner"]["rawSha256"] not in signed_text,
             "payload-files.txt still references the raw owner")
        check("push-payload/" + run,
              tool(evidence, "push-payload", "--payload-root", signed_root, "--run", run,
                   "--nonce", nonce_a if run == "run-A" else nonce_b), True)
    check("push-payload/corrupt-readback",
          tool(evidence, "push-payload", "--payload-root", signed_root, "--run", "run-A",
               env={"FAKE_COPY": "corrupt"}), False)
    check("push-payload/copy-exit",
          tool(evidence, "push-payload", "--payload-root", signed_root, "--run", "run-A",
               env={"FAKE_COPY": "exit"}), False)
    check("push-payload/copy-nojson",
          tool(evidence, "push-payload", "--payload-root", signed_root, "--run", "run-A",
               env={"FAKE_COPY": "nojson"}), False)
    unsigned_root = evidence / "unsigned-root"
    shutil.copytree(signed_root / "run-A", unsigned_root / "run-A")
    manifest = json.loads((unsigned_root / "run-A" / "manifest.json").read_text())
    manifest["signed"] = False
    (unsigned_root / "run-A" / "manifest.json").write_text(json.dumps(manifest))
    check("push-payload/unsigned-manifest-refused",
          tool(evidence, "push-payload", "--payload-root", unsigned_root, "--run", "run-A"),
          False, "not signed")
    empty = evidence / "payload-empty" / "run-empty"
    empty.mkdir(parents=True)
    write(empty / "manifest.json", json.dumps({"schema": "runeclr.ipados.r2r.payload.v2",
                                                "signed": True, "run": "run-empty", "nonce": "n",
                                                "hostBundle": BUNDLE, "fileCount": 0, "files": []}))
    check("push-payload/empty",
          tool(evidence, "push-payload", "--payload-root", empty.parent, "--run", "run-empty",
               "--allow-unsigned"), False, "empty")

    result_base = {
        "schema": "runeclr.ipados.r2r.result.v1", "runId": "run-1",
        "expectedVersion": "A", "scriptVersion": "A", "observedVersion": "A",
        "scriptNonce": "n" * 32, "nonceMatches": True, "versionMatches": True,
        "goldenMatches": True, "observedResult": "216", "observedPrivate": "100",
        "observedHelper": "307", "goldenResult": "216", "goldenPrivate": "100",
        "goldenHelper": "307", "driverExitCode": 0,
        "contractMvid": "ae965c68-163a-4756-8d66-eb3c5719c12b",
        "contractFromDefault": True, "resultWriteFailed": False, "ok": True,
        "error": "", "logLength": 32, "logExcerpt": "TRUSTED_UPDATE_SUCCESS",
    }
    result_cases = [
        ("native-result-ok", result_base, True),
        ("native-missing-runid", {k: v for k, v in result_base.items() if k != "runId"}, False),
        ("native-old-schema", {"run": "run-1", "nonce": "n" * 32, "ok": True,
                               "allRecordsOk": True, "exitCode": 0}, False),
        ("native-nonce-false", dict(result_base, nonceMatches=False), False),
        ("native-version-false", dict(result_base, versionMatches=False), False),
        ("native-golden-false", dict(result_base, goldenMatches=False), False),
        ("native-golden-value", dict(result_base, observedPrivate="101"), False),
        ("native-contract-default", dict(result_base, contractFromDefault=False), False),
        ("native-write-failed", dict(result_base, resultWriteFailed=True), False),
        ("native-driver-exit", dict(result_base, driverExitCode=1), False),
        ("native-ok-false", dict(result_base, ok=False, error="nonce-mismatch"), False),
        ("native-ok-false-no-error", dict(result_base, ok=False, error=""), False),
    ]
    for name, payload, expected in result_cases:
        if device.exists():
            shutil.rmtree(device)
        results = device / "Documents" / "results"
        results.mkdir(parents=True)
        write(results / "run-1.json", json.dumps(payload))
        check("read-result/" + name,
              tool(evidence, "read-result", "--run", "run-1", "--nonce", "n" * 32,
                   "--expected-version", "A"), expected)
    if device.exists():
        shutil.rmtree(device)
    (device / "Documents" / "results").mkdir(parents=True)
    launch_result = evidence / "launch-result.json"
    write(launch_result, json.dumps({"stdout": "console.log", "stderr": "crash.log"}))
    check("read-result/missing-json-boundary",
          tool(evidence, "read-result", "--run", "run-1", "--nonce", "n" * 32,
               "--expected-version", "A", "--launch-result", launch_result),
          False, "missing")
    extracts = [json.loads(item.read_text()) for item in
                (evidence / "read-result").glob("*/result-extract.json")]
    note("read-result/boundary-archive",
         any("native load failure" in item.get("error", "")
             and item.get("launchResult", {}).get("stdout") == "console.log"
             for item in extracts),
         "native load failure boundary was not archived")
    if device.exists():
        shutil.rmtree(device)
    results = device / "Documents" / "results"
    write(results / "a" / "run-1.json", json.dumps(result_base))
    write(results / "b" / "run-1.json", json.dumps(result_base))
    check("read-result/duplicate", tool(evidence, "read-result", "--run", "run-1", "--nonce", "n" * 32,
                                       "--expected-version", "A"), False, "exactly one")

    spec = importlib.util.spec_from_file_location("ipad_stage_under_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stage = module.Stage(evidence, "repeat-stage")
    module.run_stage(stage, [sys.executable, "-c", "print(1)"])
    repeated = False
    try:
        module.run_stage(stage, [sys.executable, "-c", "print(2)"])
    except SystemExit:
        repeated = True
    note("run-stage/refuses-repeat", repeated, "second run was allowed")

    unit = HERE / "pc_capture_unit.py"
    if unit.is_file():
        proc = subprocess.run([sys.executable, "-B", str(unit)],
                              capture_output=True, text=True)
        note("pc-capture/unit-fixtures", proc.returncode == 0,
             (proc.stderr or proc.stdout)[-300:])
    passed = sum(1 for _n, ok, _d in RESULTS if ok)
    print(json.dumps({"passed": passed, "total": len(RESULTS)}))
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
