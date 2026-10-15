#!/usr/bin/env python3
"""Build/install/run post-install controlled packages on a prepared source iOS simulator lane."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import tarfile
import uuid

BASE_COMMIT = "0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de"
PLAYER = ("RuneCLR.PackageExecution.Tests.dll", "RuneCLR.Runtime.dll",
          "RuneCLR.Packages.dll", "RuneCLR.Abstractions.dll")
PACKAGES = ("source", "import", "failure", "tampered", "forbidden",
            "private-a", "private-b", "private-import", "private-forbidden")
BRIDGE = r'''using System;
using System.IO;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
public static class Program
{
    public static int Main()
    {
        Console.WriteLine($"PACKAGE_RUNTIME={RuntimeInformation.FrameworkDescription}; RID={RuntimeInformation.RuntimeIdentifier}; OS={RuntimeInformation.OSDescription}; Arch={RuntimeInformation.ProcessArchitecture}; DynamicCodeSupported={RuntimeFeature.IsDynamicCodeSupported}; DynamicCodeCompiled={RuntimeFeature.IsDynamicCodeCompiled}");
        var root = Path.Combine(Environment.GetEnvironmentVariable("RUNECLR_DOCUMENTS")!, "controlled");
        if (!Directory.Exists(root)) { Console.WriteLine("PACKAGE_WAITING_FOR_POSTINSTALL_IL"); return 0; }
        try { return RuneCLR.PackageExecution.Tests.PackageExecutionHarness.Run(new[] { "--packages", root }); }
        catch (Exception error) { Console.WriteLine(error); return 3; }
    }
}
'''


def utc():
    return datetime.now(timezone.utc).isoformat()


def parse_utc(value):
    # .NET receipts carry seven fractional digits; Xcode's Python 3.9 accepts at most six.
    value = re.sub(r"(\.\d{6})\d+", r"\1", value.replace("Z", "+00:00"))
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise RuntimeError("Evidence timestamps require an explicit UTC offset.")
    return parsed


def rsp_argument(value):
    return '"' + value.replace('"', '\\"') + '"' if any(character.isspace() for character in value) else value


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree(path):
    return {str(p.relative_to(path)): sha(p) for p in sorted(Path(path).rglob("*")) if p.is_file()}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def capture(args):
    return subprocess.check_output([str(a) for a in args], text=True).strip()


def logged(args, log, timeout=600):
    with Path(log).open("w") as stream:
        subprocess.run([str(a) for a in args], stdout=stream, stderr=subprocess.STDOUT,
                       check=True, timeout=timeout)


def macho_sections(path):
    data = Path(path).read_bytes()
    if struct.unpack_from("<I", data)[0] != 0xfeedfacf:
        raise RuntimeError("Expected a 64-bit little-endian Mach-O image.")
    digest = hashlib.sha256()
    offset, sections, image_uuid = 32, 0, None
    for _ in range(struct.unpack_from("<I", data, 16)[0]):
        command, size = struct.unpack_from("<II", data, offset)
        if command == 0x1b:
            image_uuid = data[offset + 8:offset + 24].hex()
        if command == 0x19:
            for index in range(struct.unpack_from("<I", data, offset + 64)[0]):
                section = offset + 72 + index * 80
                length = struct.unpack_from("<Q", data, section + 40)[0]
                start = struct.unpack_from("<I", data, section + 48)[0]
                if start and length:
                    digest.update(data[section:section + 32])
                    digest.update(data[start:start + length])
                    sections += 1
        offset += size
    return {"uuid": image_uuid, "fileBackedSections": sections, "sectionsSha256": digest.hexdigest()}


def provenance(runtime, baseline):
    pack = runtime / "artifacts/bin/microsoft.netcore.app.runtime.iossimulator-arm64/Debug/runtimes/iossimulator-arm64"
    baseline_app = next((baseline / "app").glob("*.app"))
    native_source, native_app = pack / "native/libcoreclr.dylib", baseline_app / "libcoreclr.dylib"
    source_sections, app_sections = macho_sections(native_source), macho_sections(native_app)
    # Ad-hoc signing changes Mach-O signature/load-command bytes; all file-backed code/data sections must match.
    if source_sections != app_sections:
        raise RuntimeError("Baseline native runtime does not match selected source Debug code/data.")
    frameworks = {}
    for path in sorted((baseline / "original").glob("*.dll")):
        if path.name.startswith(("RuneCLR.", "HarnessBridge")):
            continue
        candidates = list(pack.rglob(path.name))
        if len(candidates) != 1 or sha(candidates[0]) != sha(path):
            raise RuntimeError("Baseline framework does not match selected source Debug pack: " + path.name)
        frameworks[path.name] = sha(path)
    crossgen = runtime / "artifacts/bin/coreclr/iossimulator.arm64.Debug/arm64/crossgen2/crossgen2"
    recorded = (baseline / "logs/source-artifact-hashes.txt").read_text()
    if not any(line.startswith(sha(crossgen)) and line.endswith(str(crossgen)) for line in recorded.splitlines()):
        raise RuntimeError("Source crossgen does not match baseline compiler provenance.")
    return {"nativeSections": source_sections, "sourceNativeSha256": sha(native_source),
            "signedBaselineNativeSha256": sha(native_app), "frameworkHashes": frameworks, "crossgenSha256": sha(crossgen)}


def il_layout(path):
    data = Path(path).read_bytes()
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    count, optional_size = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    directory = optional + (112 if struct.unpack_from("<H", data, optional)[0] == 0x20b else 96)
    cli_rva = struct.unpack_from("<I", data, directory + 14 * 8)[0]
    for index in range(count):
        section = optional + optional_size + index * 40
        size, rva, raw_size, raw = struct.unpack_from("<IIII", data, section + 8)
        if rva <= cli_rva < rva + max(size, raw_size):
            cli = raw + cli_rva - rva
            flags = struct.unpack_from("<I", data, cli + 16)[0]
            native_rva, native_size = struct.unpack_from("<II", data, cli + 64)
            return {"ilOnly": bool(flags & 1), "managedNativeRva": native_rva, "managedNativeSize": native_size}
    raise RuntimeError("Cannot locate managed header: " + str(path))


def build(args):
    out = args.output.resolve()
    if args.resume_build and (out / "state.json").exists():
        raise RuntimeError("A finalized or installed experiment cannot be rebuilt in place.")
    out.mkdir(exist_ok=args.resume_build)
    logs = out / "logs"
    logs.mkdir(exist_ok=args.resume_build)
    baseline, runtime, player = args.baseline.resolve(), args.runtime.resolve(), args.player.resolve()
    shutil.copy2(Path(__file__), out / "driver.py")
    artifact_provenance = provenance(runtime, baseline)
    head = capture(["git", "-C", runtime, "rev-parse", "HEAD"])
    if head != BASE_COMMIT:
        raise RuntimeError("This driver requires the recorded unpatched source base.")
    status = capture(["git", "-C", runtime, "status", "--short"])
    if any(line and not line.startswith("??") for line in status.splitlines()):
        raise RuntimeError("Tracked runtime source changes require a separate experiment.")
    (logs / "runtime-status.txt").write_text(status + "\n")
    sdk = runtime / ".dotnet/dotnet"
    crossgen = runtime / "artifacts/bin/coreclr/iossimulator.arm64.Debug/arm64/crossgen2/crossgen2"
    baseline_app = next((baseline / "app").glob("*.app"))
    inputs = out / "input"
    inputs.mkdir(exist_ok=args.resume_build)
    frameworks = [p for p in sorted((baseline / "original").glob("*.dll"))
                  if not p.name.startswith(("RuneCLR.", "HarnessBridge", "Microsoft.CodeAnalysis"))]
    for path in frameworks:
        shutil.copy2(path, inputs / path.name)
    for name in PLAYER:
        if args.resume_build and (inputs / name).exists() and sha(inputs / name) != sha(player / name):
            raise RuntimeError("Cannot resume changed player input bytes: " + name)
        shutil.copy2(player / name, inputs / name)
    src = out / "PackageBridge.cs"
    if args.resume_build and src.exists() and src.read_text() != BRIDGE:
        raise RuntimeError("Cannot resume changed managed bridge source.")
    src.write_text(BRIDGE)
    version = capture([sdk, "--version"])
    csc = runtime / ".dotnet/sdk" / version / "Roslyn/bincore/csc.dll"
    references = ["-r:" + str(path) for path in sorted(inputs.glob("*.dll"))]
    if not (args.resume_build and (inputs / "PackageBridge.dll").exists()):
        logged([sdk, csc, "-nologo", "-noconfig", "-nostdlib+", "-optimize+", "-nullable:enable",
                "-target:exe", "-out:" + str(inputs / "PackageBridge.dll"), *references, src], logs / "bridge-build.log")
    app = out / "app/Packages.app"
    app.mkdir(parents=True, exist_ok=args.resume_build)
    for path in baseline_app.glob("*.dylib"):
        if path.name != "framework.dylib":
            shutil.copy2(path, app / path.name)
    deps = baseline_app / "Microsoft.NETCore.App.deps.json"
    if deps.exists():
        shutil.copy2(deps, app / deps.name)
    il_names = {"RuneCLR.Runtime.dll", "RuneCLR.Packages.dll"}
    composite = [p for p in sorted(inputs.glob("*.dll")) if p.name not in il_names]
    options = ["--targetos:iossimulator", "--targetarch:arm64", "--obj-format:macho",
               "--composite", "--inputbubble", "--parallelism:2", "--resilient", "--optimize",
               "--out:" + str(app / "framework.dylib")]
    options += ["-r:" + str(inputs / name) for name in sorted(il_names)]
    rsp = out / "crossgen.rsp"
    rsp.write_text("\n".join(rsp_argument(value) for value in options + [str(p) for p in composite]) + "\n")
    obj = out / "framework.o"
    if args.resume_build and obj.exists():
        if obj.read_bytes()[:4] != bytes.fromhex("cffaedfe"):
            raise RuntimeError("Cannot resume an invalid composite Mach-O object.")
        if not all((app / path.name).exists() for path in composite):
            raise RuntimeError("Cannot resume missing composite components.")
        (logs / "resume-composite.txt").write_text("Reused this uninstalled experiment's completed object: " + sha(obj) + "\n")
    else:
        logged([crossgen, "@" + str(rsp)], logs / "crossgen.log")
        shutil.copy2(app / "framework.dylib", obj)
    for name in il_names:
        shutil.copy2(inputs / name, app / name)
    logged(["xcrun", "--sdk", "iphonesimulator", "clang", "-target", "arm64-apple-ios15.3-simulator",
            "-dynamiclib", obj, "-Wl,-install_name,@rpath/framework.dylib", "-o", app / "framework.dylib"], logs / "composite-link.log")
    for name in ("main.m", "util.h", "coreclrhost.h", "host_runtime_contract.h"):
        shutil.copy2(baseline / name, out / name)
    wrapper = (baseline / "runtime.m").read_text().replace("HarnessBridge.dll", "PackageBridge.dll")
    wrapper = wrapper.replace("RuneCLR.TestMaps.CounterMap:OnTick RuneCLR.LateMap.LateMap:*",
                              "GameScript:* SharedHelper:* GenericCounter`1:*")
    (out / "runtime.m").write_text(wrapper)
    bundle_id = "org.runeclr.packages." + uuid.uuid4().hex[:12]
    plist = plistlib.loads((baseline_app / "Info.plist").read_bytes())
    plist.update(CFBundleExecutable="Packages", CFBundleName="Packages", CFBundleIdentifier=bundle_id)
    (app / "Info.plist").write_bytes(plistlib.dumps(plist))
    logged(["xcrun", "--sdk", "iphonesimulator", "clang", "-target", "arm64-apple-ios15.3-simulator",
            "-fobjc-arc", "-DINVARIANT_GLOBALIZATION=1", "-I" + str(out), out / "main.m", out / "runtime.m",
            "-L" + str(app), "-lcoreclr", "-framework", "UIKit", "-framework", "Foundation",
            "-Wl,-rpath,@executable_path", "-o", app / "Packages"], logs / "native-build.log")
    for path in app.glob("*.dylib"):
        logged(["codesign", "--force", "--sign", "-", path], logs / (path.name + "-sign.log"))
    logged(["codesign", "--force", "--sign", "-", app], logs / "app-sign.log")
    inventory = tree(app)
    if any(Path(name).name.startswith(("RuneCLR.Compiler", "Microsoft.CodeAnalysis", "RuneCLR.PackageFixtures")) for name in inventory):
        raise RuntimeError("Operator/compiler files entered player bundle.")
    layouts = {name: il_layout(app / name) for name in PLAYER + ("PackageBridge.dll",)}
    if any(layouts[name]["managedNativeRva"] for name in il_names):
        raise RuntimeError("Runtime and Packages must retain their original IL.")
    if any(sha(inputs / name) != sha(app / name) for name in il_names):
        raise RuntimeError("Host IL bytes changed during packaging.")
    write_json(out / "state.json", {"output": str(out), "app": str(app), "bundleId": bundle_id,
               "runtime": str(runtime), "runtimeBase": head, "sourceSdk": version, "baseline": str(baseline),
               "runtimeProvenance": artifact_provenance,
               "playerInputHashes": {name: sha(player / name) for name in PLAYER},
               "runtimeArtifactHashes": {str(p): sha(p) for p in (crossgen, app / "libcoreclr.dylib", inputs / "System.Private.CoreLib.dll")},
               "layouts": layouts, "bundleHashes": inventory, "builtUtc": utc()})
    print("Built fresh selective IL player: " + str(app), flush=True)


def load(args):
    out = args.output.resolve()
    return out, json.loads((out / "state.json").read_text())


def install(args):
    out, state = load(args)
    state["runtimeProvenance"] = provenance(Path(state["runtime"]), Path(state["baseline"]))
    shutil.copy2(Path(__file__), out / "driver.py")
    if "simulator" in state:
        raise RuntimeError("This experiment already owns a simulator; preserve its earlier installation.")
    sim = capture(["xcrun", "simctl", "create", "RuneCLR-packages-" + uuid.uuid4().hex[:8],
                   args.device_type, args.simulator_runtime])
    state["simulator"] = sim
    write_json(out / "state.json", state)
    logged(["xcrun", "simctl", "boot", sim], out / "logs/boot.log")
    logged(["xcrun", "simctl", "bootstatus", sim, "-b"], out / "logs/bootstatus.log")
    logged(["xcrun", "simctl", "install", sim, state["app"]], out / "logs/install.log")
    state["installedUtc"] = utc()
    state["installedApp"] = capture(["xcrun", "simctl", "get_app_container", sim, state["bundleId"], "app"])
    state["dataContainer"] = capture(["xcrun", "simctl", "get_app_container", sim, state["bundleId"], "data"])
    if tree(Path(state["installedApp"])) != state["bundleHashes"]:
        raise RuntimeError("Installed app hashes do not match built bundle.")
    write_json(out / "state.json", state)
    logged(["xcrun", "simctl", "launch", "--console", sim, state["bundleId"]], out / "logs/before-packages.log", timeout=120)
    if "PACKAGE_WAITING_FOR_POSTINSTALL_IL" not in (out / "logs/before-packages.log").read_text():
        raise RuntimeError("Installed player did not confirm that new IL is absent.")
    print(json.dumps({"installedUtc": state["installedUtc"], "simulator": sim, "bundleId": state["bundleId"]}), flush=True)


def execute(args):
    out, state = load(args)
    produced = parse_utc(args.produced_utc)
    if produced <= parse_utc(state["installedUtc"]):
        raise RuntimeError("Package production must begin after this APK-equivalent app installation.")
    packages = args.packages.resolve()
    receipt_path = packages / "fixtures.json"
    receipt = json.loads(receipt_path.read_text())
    generated = parse_utc(receipt["generatedUtc"])
    if generated <= parse_utc(state["installedUtc"]) or generated < produced:
        raise RuntimeError("Fixture receipt does not establish post-install generation.")
    if receipt["contractImageSha256"].lower() != state["playerInputHashes"]["RuneCLR.Abstractions.dll"].lower():
        raise RuntimeError("Fixture producer used a different portable host contract image.")
    if receipt["inputProfile"] != "managed-il-gameplay-v1":
        raise RuntimeError("Fixture receipt has the wrong capability profile.")
    if set(item["directory"] for item in receipt["packages"]) != set(PACKAGES):
        raise RuntimeError("Receipt package inventory does not match acceptance fixtures.")
    for item in receipt["packages"]:
        if item["manifestSha256"].lower() != sha(packages / item["directory"] / "package.json"):
            raise RuntimeError("Transferred manifest hash does not match operator receipt.")
    shutil.copy2(receipt_path, out / "fixtures.json")
    if not all((packages / name / "package.json").is_file() for name in PACKAGES):
        raise RuntimeError("Expected all nine controlled package fixture directories.")
    target = Path(state["dataContainer"]) / "Documents/controlled"
    if target.exists():
        raise RuntimeError("Preserve previous payloads; use a new installed app for another run.")
    target.mkdir(parents=True)
    for name in PACKAGES:
        shutil.copytree(packages / name, target / name)
    payloads = {name + "/" + path: digest for name in PACKAGES for path, digest in tree(packages / name).items()}
    if tree(target) != payloads:
        raise RuntimeError("Installed package hashes do not match operator output.")
    payload_layouts = {path: il_layout(target / path) for path in payloads if path.endswith(".dll")}
    if any(layout["managedNativeRva"] or not layout["ilOnly"] for layout in payload_layouts.values()):
        raise RuntimeError("UGC payload contains a native body.")
    before = tree(Path(state["installedApp"]))
    logged(["xcrun", "simctl", "launch", "--console", state["simulator"], state["bundleId"]], out / "logs/packages-run.log", timeout=240)
    text = (out / "logs/packages-run.log").read_text(errors="replace")
    after = tree(Path(state["installedApp"]))
    counts = re.search(r"(\d+)/(\d+) package execution tests passed", text)
    success = bool(counts and counts.group(1) == counts.group(2) == "15" and "RUNECLR_EXIT=0" in text)
    result = {"completedUtc": utc(), "installedUtc": state["installedUtc"], "productionStartedUtc": args.produced_utc,
              "passed": int(counts.group(1)) if counts else 0, "total": int(counts.group(2)) if counts else 0,
              "success": success, "bundleUnchanged": before == after == state["bundleHashes"],
              "receipt": receipt, "receiptSha256": sha(receipt_path), "payloadHashes": payloads, "payloadLayouts": payload_layouts,
              "dynamicCompilationDisabled": "DynamicCodeCompiled=False" in text,
              "source12RuntimeReported": "PACKAGE_RUNTIME=.NET 12.0.0-dev" in text,
              "interpreterNotices": {name: text.count("Interpreter compile method " + name) for name in
                                     ("GameScript:OnStart", "GameScript:OnTick", "GameScript:OnStop", "SharedHelper:Read", "GenericCounter`1")},
              "interpreterDumps": {name: text.count("Compiled method: ." + name) for name in
                                   ("GameScript:OnStart", "GameScript:OnTick", "GameScript:OnStop", "SharedHelper:Read", "GenericCounter`1")},
              "scope": "Unpatched source .NET 12 Debug iOS simulator; Runtime and Packages IL; no physical-device or hostile-code acceptance"}
    write_json(out / "logs/installed-bundle-after.json", after)
    result["success"] = success and result["bundleUnchanged"] and result["dynamicCompilationDisabled"] and result["source12RuntimeReported"] and all(
        result["interpreterDumps"][name] > 0 for name in ("GameScript:OnStart", "GameScript:OnTick", "GameScript:OnStop", "SharedHelper:Read", "GenericCounter`1"))
    write_json(out / "results.json", result)
    if not result["success"]:
        raise RuntimeError("Controlled package acceptance failed; preserve original logs and results.json.")
    print(f"PASS {result['passed']}/{result['total']} iOS controlled package tests; bundle unchanged; native compilation disabled", flush=True)


def cleanup(args):
    out, state = load(args)
    if "simulator" not in state:
        return
    logged(["xcrun", "simctl", "shutdown", state["simulator"]], out / "logs/shutdown.log")
    state["shutdownUtc"] = utc()
    write_json(out / "state.json", state)
    print("Owned simulator shut down: " + state["simulator"], flush=True)


def archive(args):
    out, state = load(args)
    artifact = out / "evidence.tar.gz"
    with tarfile.open(artifact, "w:gz") as tar:
        for name in ("build-driver.log", "resumed-build-driver.log", "install-driver.log", "run-driver.log", "run-driver-first-attempt.log"):
            if (out.parent / name).exists():
                tar.add(out.parent / name, arcname="driver-logs/" + name)
        for name in ("logs", "state.json", "results.json", "fixtures.json", "PackageBridge.cs", "runtime.m", "main.m", "crossgen.rsp", "driver.py"):
            if (out / name).exists():
                tar.add(out / name, arcname=name)
        for name in PLAYER + ("PackageBridge.dll",):
            tar.add(out / "input" / name, arcname="player-il/" + name)
    print(json.dumps({"archive": str(artifact), "sha256": sha(artifact), "bytes": artifact.stat().st_size}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("build", "install", "run", "cleanup", "archive"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--player", type=Path)
    parser.add_argument("--packages", type=Path)
    parser.add_argument("--produced-utc")
    parser.add_argument("--resume-build", action="store_true", help="Resume this driver's uninstalled failed build using its completed composite object.")
    parser.add_argument("--device-type", default="com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro")
    parser.add_argument("--simulator-runtime", default="com.apple.CoreSimulator.SimRuntime.iOS-27-0")
    args = parser.parse_args()
    needed = ("runtime", "baseline", "player") if args.phase == "build" else ("packages", "produced_utc") if args.phase == "run" else ()
    for name in needed:
        if getattr(args, name) is None:
            parser.error("This phase requires --" + name.replace("_", "-"))
    {"build": build, "install": install, "run": execute, "cleanup": cleanup, "archive": archive}[args.phase](args)


if __name__ == "__main__":
    main()
