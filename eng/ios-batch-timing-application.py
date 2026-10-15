#!/usr/bin/env python3
"""Build a fresh iOS timing app through a pinned, narrowly adapted composite workflow."""
import argparse
import ast
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path

ACCEPT_SHA = "d2bee86ffed7438f8b0fd7206e7569ff1ed4daf5331a5de090c5ccee996d0656"
PREPARE_SHA = "5956effd1046633755e6db7f70915ed8d4f1725cfa579fc7a0b740a1f76d99a8"
INPUT_SHA = "d8f2be284a6034ce415a740365b0b5f09dfdb57c66b1f3c1fad2e07ad327b98b"
HOST_SHA = "1bce4d5dfd010dc7bc7cf0906ded8add1f2fdca6e8d8c4766c5dd88d54a8ec2a"
AUTHOR_SHA = "d743ecb6ba897366a276ab700e79a42f3885ba2eaf69d1713bb086346f2fd09e"
CONTRACT_SHA = "ebfe72469b640b63991189123971beadbf9c3fe74d303a9b7ce66f87596a807b"
CONTRACT_MVID = "92efbbd4-8ae3-4686-824b-bafe67f2dd69"
BRIDGE = '''using System; using MobileBatchTimingProbe; public static class SessionBridge {
 public static int Main(string[] args) {
  var d=Environment.GetEnvironmentVariable("RUNECLR_DOCUMENTS") ?? throw new InvalidOperationException("documents");
  var n=Environment.GetEnvironmentVariable("RUNECLR_TIMING_NONCE") ?? throw new InvalidOperationException("nonce");
  var m=Environment.GetEnvironmentVariable("RUNECLR_TIMING_MODE") ?? throw new InvalidOperationException("mode");
  var l=Environment.GetEnvironmentVariable("RUNECLR_TIMING_LANE") ?? throw new InvalidOperationException("lane");
  var s=Environment.GetEnvironmentVariable("RUNECLR_TIMING_SAMPLES") ?? throw new InvalidOperationException("samples");
  return Entry.Run(new[]{d+"/timing-plugin/RuneCLR.BatchKernel.dll",m,l,n,s,d+"/timing-"+n+".json"});
 }}
'''
NATIVE_SETTINGS = r'''    const char *nonce = getenv("RUNECLR_TIMING_NONCE");
    const char *mode = getenv("RUNECLR_TIMING_MODE");
    const char *lane = getenv("RUNECLR_TIMING_LANE");
    const char *samples = getenv("RUNECLR_TIMING_SAMPLES");
    const char *batch_hex = getenv("RUNECLR_TIMING_HEX");
    const char *derived = getenv("RUNECLR_TIMING_DERIVED");
    if (!nonce || !mode || !lane || !samples || !batch_hex || !derived || strlen(nonce) != 32 ||
        (strcmp(mode,"no-config") && strcmp(mode,"high-budget")) ||
        (strcmp(lane,"no-config") && strcmp(lane,"best-exact") && strcmp(lane,"N100") && strcmp(lane,"N1000")) ||
        (!strcmp(lane,"no-config") && strcmp(mode,"no-config"))) exit(124);
    char *samples_end; long sample_count = strtol(samples, &samples_end, 10);
    if (*samples_end || sample_count < 1 || sample_count > 100) exit(124);
    const char *expected_hex = !strcmp(lane,"N1000") ? "3e8" : !strcmp(lane,"N100") ? "64" : "0";
    const char *expected_derived = !strcmp(lane,"best-exact") ? "1" : "0";
    if (strcmp(batch_hex,expected_hex) || strcmp(derived,expected_derived)) exit(124);
    setenv("DOTNET_InterpMode", "0", 1);
    setenv("DOTNET_RuneCLRInterpretCollectible", "0", 1);
    setenv("DOTNET_ReadyToRun", "1", 1);
    setenv("DOTNET_TieredCompilation", "0", 1);
    setenv("DOTNET_MULTILEVEL_LOOKUP", "0", 1);
    setenv("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT", "1", 1);
    setenv("DOTNET_InterpList", "0", 1);
    unsetenv("DOTNET_InterpDump");
    setenv("DOTNET_RuneCLRPhaseAcquireLoad", "1", 1);
    setenv("DOTNET_RuneCLRDerivedLedger", derived, 1);
    setenv("DOTNET_RuneCLRBatchInterval", batch_hex, 1);
    setenv("RUNECLR_DOCUMENTS", [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES)[0] UTF8String], 1);
    printf("TIMING_NATIVE pid=%d nonce=%s mode=%s lane=%s samples=%s interval=%s DerivedLedger=%s PhaseAcquireLoad=1 InterpMode=0 ReadyToRun=1\n", getpid(), nonce, mode, lane, samples, batch_hex, derived); fflush(stdout);
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def need(value, message):
    if not value:
        raise RuntimeError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    with Path(path).open("x", encoding="ascii") as stream:
        stream.write(json.dumps(value, indent=2) + chr(10))


def frozen_module(name, path, digest):
    need(sha(path) == digest, "Frozen helper differs: " + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inputs(root):
    root = root.resolve()
    manifest = read(root / "input-manifest.json")
    need(sha(root / "input-manifest.json") == INPUT_SHA and manifest["schema"] == "runeclr.mobile-batch-timing.inputs.v1" and
         manifest["authorSha256"] == AUTHOR_SHA and manifest["contractSha256"] == CONTRACT_SHA and
         manifest["contractMvid"] == CONTRACT_MVID and manifest["expectedDispatchDelta"] == 2100016 and
         manifest["expectedChecksum"] == 12749776 and manifest["iterations"] == 100000 and
         manifest["files"]["host/MobileBatchTimingProbe.dll"] == HOST_SHA, "Frozen timing inputs differ.")
    for name, digest in manifest["files"].items():
        path = (root / name).resolve()
        need(path.is_relative_to(root) and sha(path) == digest, "Timing input changed: " + name)
    return manifest


def adapted(accepted):
    source = inspect.getsource(accepted.build)
    tree = ast.parse(source)
    replacements = {"MobileBatchBoundaryProbe.dll": "MobileBatchTimingProbe.dll",
                    "BatchBoundary.Contract.dll": "RuneCLR.Abstractions.dll", "BatchBoundary.Author.dll": "RuneCLR.BatchKernel.dll",
                    "BUILD PASS: fresh batch boundary app; execution not yet verified":
                    "BUILD PASS: fresh timing app; execution and performance not yet verified"}
    counts = {key: 0 for key in replacements}
    bridge_changes = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in replacements:
            counts[node.value] += 1
            node.value = replacements[node.value]
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and
                node.func.value.id == "bridge" and node.func.attr == "write_text"):
            node.args[0] = ast.Constant(BRIDGE)
            bridge_changes += 1
    need(counts == {"MobileBatchBoundaryProbe.dll": 2, "BatchBoundary.Contract.dll": 2, "BatchBoundary.Author.dll": 1,
                   "BUILD PASS: fresh batch boundary app; execution not yet verified": 1} and bridge_changes == 1,
         "Frozen build adaptation anchors differ.")
    wrapper_tree = ast.parse(inspect.getsource(accepted.wrapper))
    wrapper_changes = 0
    for node in ast.walk(wrapper_tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "settings":
            need(isinstance(node.value, ast.Constant) and "BATCH_NATIVE pid=" in node.value.value, "Frozen wrapper settings anchor differs.")
            node.value = ast.Constant(NATIVE_SETTINGS)
            wrapper_changes += 1
    need(wrapper_changes == 1, "Frozen native settings adaptation count differs.")
    namespace = dict(accepted.__dict__)
    namespace.update(inputs=inputs, __file__=__file__)
    exec(compile(ast.fix_missing_locations(wrapper_tree), str(accepted.__file__), "exec"), namespace)
    exec(compile(ast.fix_missing_locations(tree), str(accepted.__file__), "exec"), namespace)
    evidence = {"constantReplacementCounts": counts, "bridgeReplacements": bridge_changes, "wrapperSettingsReplacements": wrapper_changes,
                "frozenBuildSourceSha256": hashlib.sha256(source.encode("ascii")).hexdigest(),
                "bridgeSha256": hashlib.sha256(BRIDGE.encode("ascii")).hexdigest(),
                "nativeSettingsSha256": hashlib.sha256(NATIVE_SETTINGS.encode("ascii")).hexdigest()}
    return namespace, evidence, ast.unparse(tree), ast.unparse(wrapper_tree)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("preflight", "build"))
    for name in ("accept-tool", "prepare-tool", "inputs", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("runtime", "build-receipt", "baseline-app", "wrapper-source", "wrapper-assets", "framework-input", "framework-manifest"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    accepted = frozen_module("frozen_timing_app_workflow", args.accept_tool, ACCEPT_SHA)
    prepare = frozen_module("frozen_timing_metadata", args.prepare_tool, PREPARE_SHA)
    manifest = inputs(args.inputs)
    pe = prepare.readers()
    need(pe["pe_mvid"](args.inputs / "host/RuneCLR.Abstractions.dll")["moduleMvid"] == CONTRACT_MVID and
         sha(args.inputs / "author/RuneCLR.Abstractions.dll") == CONTRACT_SHA and
         prepare.il_layout(args.inputs / "author/RuneCLR.BatchKernel.dll") == {"ilOnly": True, "managedNativeRva": 0},
         "Raw shared contract or late author layout differs.")
    namespace, evidence, build_source, wrapper_source = adapted(accepted)
    if args.phase == "preflight":
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "adapted-build.py").write_text(build_source + chr(10), encoding="ascii")
        (args.output / "adapted-wrapper.py").write_text(wrapper_source + chr(10), encoding="ascii")
        (args.output / "SessionBridge.cs").write_text(BRIDGE, encoding="ascii")
        (args.output / "native-settings.m").write_text(NATIVE_SETTINGS, encoding="ascii")
        write(args.output / "results.json", dict(evidence, passed=True, driverSha256=sha(__file__), inputManifestSha256=INPUT_SHA,
              applicationBuilt=False, mobileExecutionVerified=False, performanceVerified=False))
        print(json.dumps(read(args.output / "results.json"), indent=2))
        return
    for name in ("runtime", "build_receipt", "baseline_app", "wrapper_source", "wrapper_assets", "framework_input", "framework_manifest"):
        need(getattr(args, name) is not None, "Missing --" + name.replace("_", "-") + ".")
    namespace["build"](args)
    state = read(args.output / "state.json")
    app = Path(state["app"])
    component = app / "RuneCLR.Abstractions.dll"
    need(pe["pe_mvid"](component)["moduleMvid"] == CONTRACT_MVID and
         state["compositeInputs"]["MobileBatchTimingProbe.dll"] == HOST_SHA and
         state["compositeInputs"]["RuneCLR.Abstractions.dll"] == CONTRACT_SHA and not list(app.rglob("RuneCLR.BatchKernel.dll")) and
         inputs(args.inputs) == manifest, "Fresh trusted input/contract R2R provenance or author placement differs.")
    write(args.output / "timing-provenance.json", {"passed": True, "driverSha256": sha(__file__), "frozenWorkflowSha256": ACCEPT_SHA,
          "inputManifestSha256": INPUT_SHA, "trustedHostRawSha256": HOST_SHA, "authorSha256": AUTHOR_SHA,
          "contractRawSha256": CONTRACT_SHA, "contractIdentity": manifest["contractIdentity"], "contractMvid": CONTRACT_MVID,
          "contractComponentSha256": sha(component), "contractComponentMvid": pe["pe_mvid"](component)["moduleMvid"],
          "freshComposite": True, "nativeEntryProof": False, "liveBatchPathVerified": False, "mobileExecutionVerified": False,
          "performanceVerified": False, "scope": "Independent signed direct-callback timing application; no execution or timing-run claim."})
    write(args.output / "adapted-build.json", evidence)


if __name__ == "__main__":
    main()
