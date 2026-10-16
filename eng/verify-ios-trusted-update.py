#!/usr/bin/env python3
"""Verify a trusted-update receipt, or the local preflight, without executing author code."""
import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def require(value, message, errors):
    if not value:
        errors.append(message)


def load_driver():
    spec = importlib.util.spec_from_file_location(
        "ios_trusted_update_driver", Path(__file__).with_name("ios-trusted-update.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify(path):
    root = Path(path).resolve()
    errors = []
    inputs = json.loads((root / "inputs.json").read_text(encoding="utf-8"))
    before = json.loads((root / "host" / "bundle-before.json").read_text(encoding="utf-8"))
    after_path = root / "host" / "bundle-after.json"
    after = json.loads(after_path.read_text(encoding="utf-8")) if after_path.exists() else {}
    require(before == after, "fixed host bundle changed after update runs", errors)
    require(inputs.get("target") == "iossimulator-arm64", "input target is not iossimulator-arm64", errors)
    results = json.loads((root / "results.json").read_text(encoding="utf-8"))
    runs = results.get("runs", {})
    require(set(runs) >= {"A", "B"}, "A/B independent startup results missing", errors)
    names = []
    pids = []
    for version in ("A", "B"):
        item = runs.get(version, {})
        owner = "TrustedUpdate.%s.r2r.dylib" % version
        names.append(item.get("ownerCompositeExecutable"))
        require(item.get("ownerCompositeExecutable") == owner, "%s owner filename mismatch" % version, errors)
        require(item.get("processPid") not in (None, 0), "%s process PID missing" % version, errors)
        if item.get("processPid"):
            pids.append(item["processPid"])
        require(item.get("installedUtc") and item.get("downloadedUtc") and item["installedUtc"] <= item["downloadedUtc"],
                "%s download ordering invalid" % version, errors)
        require(item.get("bundleUnchanged") is True, "%s host bundle changed" % version, errors)
        require(item.get("managedSuccess") is True, "%s managed update did not complete" % version, errors)
        require(item.get("launched") is True, "%s process was not launched" % version, errors)
        macho = item.get("macho") or {}
        segment = macho.get("executableSegment") or {}
        require(macho.get("provesNativeExecution") is False, "%s Mach-O audit claimed native execution" % version, errors)
        require(macho.get("platform") == 7 and macho.get("platformName") == "iossimulator",
                "%s Mach-O platform is not 7/iossimulator" % version, errors)
        require(isinstance(macho.get("byteCount"), int) and macho.get("byteCount") > 0, "%s Mach-O byte count missing" % version, errors)
        require(isinstance(macho.get("sha256"), str) and len(macho.get("sha256") or "") == 64, "%s Mach-O SHA-256 missing" % version, errors)
        require(isinstance(macho.get("uuid"), str) and macho.get("uuid"), "%s Mach-O UUID missing" % version, errors)
        for field in ("vmaddr", "vmsize", "fileoff", "filesize"):
            require(isinstance(segment.get(field), int), "%s executable segment %s missing" % (version, field), errors)
        require(item.get("bundledSameNameCountsAsDownload") is False, "%s bundled dylib was treated as the download" % version, errors)
        callback = item.get("callbackIdentity") or {}
        require(callback.get("ownerCompositeExecutable") == owner, "%s callback owner mismatch" % version, errors)
        require(callback.get("path") and Path(callback["path"]).name == owner, "%s callback path is not the selected owner" % version, errors)
        require(callback.get("sha256") == macho.get("sha256"), "%s callback file hash is not the audited owner" % version, errors)
        require(callback.get("base") and callback.get("imageSize"), "%s callback base or image size missing" % version, errors)
        require(item.get("downloadPathMatchesCallback") is True, "%s callback is not the downloaded owner" % version, errors)
        native = item.get("nativeEntry") or {}
        require(native.get("pcInMethodRange") is True, "%s selected native PC is not in the owner method range" % version, errors)
        require(native.get("countsAsR2RNativeExecution") is True, "%s method entry was not bound to the downloaded owner" % version, errors)
        require(native.get("ownerSha256") == macho.get("sha256"), "%s native entry hash is not the audited owner" % version, errors)
        require(native.get("ownerBase") == callback.get("baseValue"), "%s native entry base does not match the callback" % version, errors)
        helper = item.get("interpreterEntry") or {}
        require(helper.get("function") == "InterpreterStub", "%s IL helper InterpreterStub evidence missing" % version, errors)
        require(helper.get("countsAsR2RNativeExecution") is False, "%s interpreter path was counted as R2R native execution" % version, errors)
        require(helper.get("helperSha256") == item.get("helperSha256"), "%s IL helper hash mismatch" % version, errors)
    require(len(set(names)) == 2, "A/B owner composite filenames are not distinct", errors)
    require(len(set(pids)) == len(pids) == 2, "A/B did not use independent process PIDs", errors)
    fallback = results.get("runtimeFallback") or {}
    require(fallback.get("providedByRuntime") is False, "runtime IL fallback was claimed", errors)
    require(fallback.get("observedByCrashingProcess") is False, "fail-fast was observed by crashing a started runtime", errors)
    require(fallback.get("fixedRuntimeFailFastNotIntercepted") is True, "fixed-runtime fail-fast was intercepted or unstated", errors)
    require(results.get("nativeUnload") is False and results.get("sameProcessSwitch") is False,
            "same-process unload or version switch was claimed", errors)
    require(results.get("machoProvesNativeExecution") is False, "Mach-O audit was treated as native execution", errors)
    negative = results.get("negativeControl") or {}
    require(negative.get("classification") == "host-rejected-before-start", "negative control classification missing", errors)
    require(negative.get("fixedRuntimeFailFastNotIntercepted") is True, "negative control intercepted fail-fast", errors)
    require(negative.get("processStarted") is False, "negative control started a runtime process", errors)
    raw_path = Path(negative.get("rawLog") or "")
    raw = raw_path.read_text(encoding="utf-8", errors="replace") if raw_path.is_file() else ""
    require("missing RTR_HEADER" in raw and "wrong-owner" in raw, "negative owner/RTR raw log is incomplete", errors)
    require("processStarted=false" in raw and "fixedRuntimeFailFastNotIntercepted=true" in raw,
            "negative raw log does not show a pre-start rejection", errors)
    passed = not errors
    receipt = {
        "passed": passed,
        "errors": errors,
        "ownerFileNamesDiffer": results.get("ownerFileNamesDiffer"),
        "nativeExecutionProven": results.get("nativeExecutionProven") is True and passed,
        "machoProvesNativeExecution": False,
        "negativeControl": negative,
        "runtimeFallback": fallback,
        "scope": "simulator receipt; Mach-O structure is not method-entry evidence",
    }
    (root / "verification.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def local_audit(output):
    """Exercise host preflight on synthetic images. This does not run the simulator."""
    root = Path(output).resolve()
    if root.exists():
        raise SystemExit("local audit output already exists: " + str(root))
    root.mkdir(parents=True)
    errors = []
    driver = load_driver()
    fixtures = driver.load_macho_fixtures()
    plain = root / "plain-iossimulator.dylib"
    plain.write_bytes(fixtures.standard_image(7)[0])
    plain_audit = driver.macho_download_audit(plain)
    require(plain_audit["provesNativeExecution"] is False, "plain Mach-O audit claimed native execution", errors)
    require(plain_audit["platform"] == 7 and plain_audit["platformName"] == "iossimulator", "plain platform mismatch", errors)
    require(plain_audit["executableSegment"]["addressKind"] == "static_vmaddr", "static range was not labeled", errors)
    missing = driver.preflight_download(plain, plain.name, plain.name, [])
    require(missing["accepted"] is False and any("missing RTR_HEADER" in item for item in missing["errors"]),
            "missing RTR_HEADER was not rejected before start", errors)
    owner_a = root / "TrustedUpdate.A.r2r.dylib"
    owner_b_name = "TrustedUpdate.B.r2r.dylib"
    owner_a.write_bytes(driver.synthetic_owner_with_rtr(fixtures))
    component = root / "TrustedUpdate.Update.dll"
    component.write_bytes(driver.synthetic_component_dll(owner_a.name))
    embedded = driver.owner_composite_from_component(component)
    require(embedded and embedded["name"] == owner_a.name and embedded["platformNative"] and embedded["component"],
            "synthetic component owner name was not read", errors)
    accepted = driver.preflight_download(owner_a, owner_a.name, embedded["name"], ["libcoreclr.dylib"], embedded)
    require(accepted["accepted"] is True, "matching simulator owner was rejected: %s" % accepted["errors"], errors)
    require(accepted["macho"]["provesNativeExecution"] is False, "accepted audit claimed native execution", errors)
    require(accepted["processStarted"] is False and accepted["fixedRuntimeFailFastNotIntercepted"] is True,
            "structural acceptance started or intercepted the runtime", errors)
    wrong = root / "TrustedUpdate.invalid.r2r.dylib"
    wrong.write_bytes(owner_a.read_bytes())
    wrong_preflight = driver.preflight_download(wrong, wrong.name, embedded["name"], [], embedded)
    require(wrong_preflight["accepted"] is False, "wrong owner name was accepted", errors)
    device = root / "device.dylib"
    device.write_bytes(fixtures.standard_image(2)[0])
    device_preflight = driver.preflight_download(device, device.name, device.name, [])
    require(device_preflight["accepted"] is False and any("platform" in item for item in device_preflight["errors"]),
            "device platform was accepted for the simulator lane", errors)
    same = driver.preflight_download(owner_a, owner_a.name, embedded["name"], [owner_a.name], embedded)
    require(same["accepted"] is False and any("same-name" in item for item in same["errors"]),
            "same-name bundled dylib was accepted as the download", errors)
    require(owner_a.name != owner_b_name, "A/B owner filenames do not differ", errors)
    log = driver.negative_log_text([
        {"name": "missing-rtr-header", "preflight": missing},
        {"name": "wrong-owner", "preflight": wrong_preflight},
    ])
    (root / "negative-owner-preflight.log").write_text(log, encoding="utf-8")
    require("processStarted=false" in log and "fixedRuntimeFailFastNotIntercepted=true" in log,
            "local negative log is incomplete", errors)
    verifier = Path(__file__).with_name("verify-ios-trusted-update-macho.py")
    completed = subprocess.run([sys.executable, str(verifier)], capture_output=True, text=True, check=False)
    (root / "macho-verifier.log").write_text(completed.stdout + completed.stderr, encoding="utf-8")
    require(completed.returncode == 0, "read-only Mach-O verifier failed", errors)
    passed = not errors
    receipt = {
        "passed": passed,
        "errors": errors,
        "simulatorReceipt": False,
        "methodEntryCaptured": False,
        "nativeExecutionProven": False,
        "machoProvesNativeExecution": False,
        "runtimeFallbackProvided": False,
        "fixedRuntimeFailFastNotIntercepted": True,
        "ownerFileNamesDiffer": owner_a.name != owner_b_name,
        "ownerFileNames": [owner_a.name, owner_b_name],
        "macho": accepted.get("macho"),
        "missingRtrRejected": missing["accepted"] is False,
        "wrongOwnerRejected": wrong_preflight["accepted"] is False,
        "devicePlatformRejected": device_preflight["accepted"] is False,
        "sameNameBundleRejected": same["accepted"] is False,
        "scope": "local synthetic preflight only; not iOS simulator method-entry evidence",
    }
    (root / "local-audit.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--local-audit", action="store_true")
    parser.add_argument("--synthetic", action="store_true")
    args = parser.parse_args()
    if args.local_audit or args.synthetic:
        if args.output is None:
            parser.error("--output is required")
        receipt = local_audit(args.output)
        print(json.dumps(receipt, indent=2))
        return 0 if receipt["passed"] else 1
    if args.output is None:
        parser.error("--output is required unless --local-audit is supplied")
    receipt = verify(args.output)
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
