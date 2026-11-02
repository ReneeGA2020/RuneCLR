#!/usr/bin/env python3
"""Run the opt-in reflection-policy experiment against an existing private layout.

Build RuneCLR and CoreLib first. This driver never installs a runtime or builds
native binaries. The upstream source is compiled unchanged with real xUnit DLLs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape


RUNTIME_BASE = "5972a86966e56ae5f468a3e042327f0051e923d5"
RUNTIME_COMMIT = "7cbdad39669188c1f49f0a41216829d9a9005591"
RUNTIME_FILES = (
    "src/libraries/System.Private.CoreLib/src/System/Reflection/RuntimeMethodInfo.cs",
    "src/coreclr/System.Private.CoreLib/src/System/Reflection/RuneCLRReflectionPolicy.cs",
    "src/coreclr/System.Private.CoreLib/System.Private.CoreLib.csproj",
    "src/coreclr/System.Private.CoreLib/src/ILLink/ILLink.Descriptors.Shared.xml",
    "src/libraries/System.Private.CoreLib/src/System/Reflection/RuntimeConstructorInfo.cs",
    "src/coreclr/System.Private.CoreLib/src/System/Reflection/RuntimeMethodInfo.CoreCLR.cs",
    "src/coreclr/System.Private.CoreLib/src/System/Reflection/RtFieldInfo.cs",
    "src/coreclr/System.Private.CoreLib/src/System/Reflection/MdFieldInfo.cs",
    "src/libraries/System.Private.CoreLib/src/System/Reflection/MethodInvoker.cs",
    "src/coreclr/System.Private.CoreLib/src/System/Reflection/MethodInvoker.CoreCLR.cs",
    "src/libraries/System.Private.CoreLib/src/System/Reflection/ConstructorInvoker.cs",
    "src/libraries/System.Private.CoreLib/src/System/Activator.RuntimeType.cs",
    "src/coreclr/System.Private.CoreLib/src/System/RuntimeType.CoreCLR.cs",
    "src/coreclr/System.Private.CoreLib/src/System/Delegate.CoreCLR.cs",
    "src/coreclr/System.Private.CoreLib/src/System/Reflection/Emit/DynamicMethod.CoreCLR.cs",
    "src/libraries/System.Private.CoreLib/src/System/Reflection/InvokerEmitUtil.cs",
    "src/coreclr/System.Private.CoreLib/src/System/Reflection/RuntimeCustomAttributeData.CoreCLR.cs",
    "src/coreclr/System.Private.CoreLib/src/System/Runtime/Loader/AssemblyLoadContext.CoreCLR.cs",
    "src/coreclr/System.Private.CoreLib/src/System/Reflection/RuntimeAssembly.cs",
    "src/libraries/System.Private.CoreLib/src/System/Reflection/Assembly.cs",
    "src/libraries/System.Private.CoreLib/src/System/Runtime/Loader/AssemblyLoadContext.cs",
    "src/coreclr/System.Private.CoreLib/src/System/Reflection/Emit/RuntimeAssemblyBuilder.cs",
)
UPSTREAM = "src/tests/Loader/classloader/StaticVirtualMethods/Regression/GitHub_130545.cs"
UPSTREAM_FIELDS = "src/tests/Reflection/SetValue/TrySetReadonlyStaticField2.cs"
UPSTREAM_CONSTRUCTORS = "src/tests/Reflection/DisallowAbstractConstructors/DisallowAbstractConstructors.cs"
UPSTREAM_HELPER = "src/tests/Common/CoreCLRTestLibrary/CoreClrConfigurationDetection.cs"
XUNIT_FILES = ("xunit.core", "xunit.assert", "xunit.abstractions", "Microsoft.DotNet.XUnitExtensions")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def within(path, root):
    return path == root or root in path.parents

def verify_runtime_provenance(runtime):
    """Require the exact published runtime commit and clean 22-file source delta."""
    head = git(runtime, "rev-parse", "HEAD")
    if head != RUNTIME_COMMIT:
        raise ValueError("Runtime HEAD must be the published reflection commit "
                         + RUNTIME_COMMIT + "; found " + head + ".")
    parents = git(runtime, "rev-list", "--parents", "-n", "1", head).split()
    if len(parents) != 2 or parents[1] != RUNTIME_BASE:
        raise ValueError("Published runtime commit must have the session-policy base as its exact parent.")
    status = git(runtime, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise ValueError("Runtime worktree must be clean (tracked, index and untracked nonignored files).")
    delta = {}
    for line in git(runtime, "diff", "--name-status", RUNTIME_BASE + ".." + RUNTIME_COMMIT).splitlines():
        parts = line.split("\t")
        if len(parts) != 2 or parts[0] not in ("M", "A"):
            raise ValueError("Published runtime delta contains an unsupported change: " + line)
        delta[parts[1]] = parts[0]
    if set(delta) != set(RUNTIME_FILES) or len(delta) != len(RUNTIME_FILES):
        missing = sorted(set(RUNTIME_FILES) - set(delta))
        extra = sorted(set(delta) - set(RUNTIME_FILES))
        raise ValueError("Published runtime delta must be exactly the declared "
                         + str(len(RUNTIME_FILES)) + " files; missing="
                         + repr(missing) + " extra=" + repr(extra))
    for relative in RUNTIME_FILES:
        committed = git(runtime, "rev-parse", RUNTIME_COMMIT + ":" + relative)
        worktree = git(runtime, "hash-object", str(runtime / relative))
        if committed != worktree:
            raise ValueError("Runtime worktree bytes differ from the published commit for " + relative + ".")
    return head


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--layout", required=True, type=Path)
    parser.add_argument("--xunit-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dotnet", default="dotnet")
    parser.add_argument("--corelib", type=Path,
                        help="Built patched CoreLib; defaults to the Windows x64 Checked IL output.")
    parser.add_argument("--framework-version", default="12.0.0")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    runtime, layout, xunit, output = (path.resolve() for path in
                                    (args.runtime_root, args.layout, args.xunit_dir, args.output))
    if any(within(output, path) for path in (root, runtime, layout, xunit)):
        raise ValueError("Output must be outside source and input roots.")
    if output.exists():
        raise ValueError("Output must be a new directory.")
    runtime_head = verify_runtime_provenance(runtime)
    dotnet = Path(shutil.which(args.dotnet) or args.dotnet).resolve(strict=True)
    private_host = layout / ("dotnet.exe" if os.name == "nt" else "dotnet")
    framework = layout / "shared/Microsoft.NETCore.App" / args.framework_version
    corelib = (args.corelib or runtime / "artifacts/bin/coreclr/windows.x64.Checked/IL/System.Private.CoreLib.dll").resolve()
    if digest(corelib) != digest(framework / "System.Private.CoreLib.dll"):
        raise ValueError("The layout CoreLib does not equal the explicit patched build output.")
    harness = root / "tests/RuneCLR.ReflectionPolicy.Tests/bin/Release/net11.0/RuneCLR.ReflectionPolicy.Tests.dll"
    lifecycle = root / "tests/RuneCLR.Runtime.Tests/bin/Release/net11.0/RuneCLR.Runtime.Tests.dll"
    upstream = runtime / UPSTREAM
    inputs = {Path(__file__).resolve(), dotnet, private_host, upstream, corelib,
              runtime / UPSTREAM_FIELDS, runtime / UPSTREAM_CONSTRUCTORS, runtime / UPSTREAM_HELPER}
    inputs.update(runtime / name for name in RUNTIME_FILES)
    inputs.update(xunit / (name + ".dll") for name in XUNIT_FILES)
    for folder in (layout, harness.parent, lifecycle.parent):
        inputs.update(path for path in folder.rglob("*") if path.is_file())
    for folder in (root / "src", root / "tests"):
        inputs.update(path for path in folder.rglob("*") if path.is_file()
                      and not {"bin", "obj"}.intersection(path.relative_to(folder).parts))
    inputs.update((root / "RuneCLR.slnx", root / "Directory.Build.props"))
    pins = {str(path): digest(path) for path in sorted(inputs)}
    for path in (harness, lifecycle, framework / "System.Private.CoreLib.dll"):
        if str(path) not in pins:
            raise ValueError("Required built input absent: " + str(path))
    output.mkdir(parents=True)
    write_json(output / "pins-before.json", pins)
    write_json(output / "source-state.json", {
        "runtimeBase": RUNTIME_BASE, "runtimeCommit": RUNTIME_COMMIT, "runtimeHead": runtime_head,
        "runtimeBranch": git(runtime, "branch", "--show-current"),
        "runtimeStatus": git(runtime, "status", "--short"),
        "runeclrHead": git(root, "rev-parse", "HEAD"),
        "runeclrStatus": git(root, "status", "--short"),
        "nativeBuild": "Not rebuilt; existing layout binaries are pinned inputs.",
    })
    results = []
    environment = dict(os.environ)
    # Isolate known interpreter/diagnostic switches from the calling shell.
    for key in list(environment):
        if key.startswith(("DOTNET_", "COMPlus_")):
            del environment[key]
    environment.update({"DOTNET_MULTILEVEL_LOOKUP": "0", "DOTNET_RuneCLRInterpretCollectible": "1",
                        "DOTNET_InterpMode": "0", "DOTNET_ReadyToRun": "1", "DOTNET_TieredCompilation": "0"})

    def run(name, command, marker=None, diagnostics=False):
        env = dict(environment)
        if diagnostics:
            env.update({"DOTNET_InterpList": "1", "DOTNET_InterpDump": "*:*",
                        "DOTNET_JitDisasmSummary": "1", "DOTNET_JitStdOutFile": str(output / "private.jit")})
        write_json(output / (name + "-request.json"), {"argv": [str(p) for p in command],
                   "cwd": str(root), "runtimeEnvironment": {k: v for k, v in env.items() if k.startswith("DOTNET_")}})
        stdout, stderr = output / (name + ".stdout.log"), output / (name + ".stderr.log")
        result = {"name": name, "stdout": str(stdout), "stderr": str(stderr)}
        with stdout.open("wb") as out, stderr.open("wb") as err:
            try:
                process = subprocess.run(command, cwd=root, env=env, stdout=out, stderr=err, timeout=args.timeout)
                result["exit"] = process.returncode
            except subprocess.TimeoutExpired:
                result.update({"exit": None, "timeout": True})
        text = stdout.read_text(encoding="utf-8", errors="replace")
        result["passed"] = result["exit"] == 0 and (marker is None or marker in text)
        results.append(result)
        write_json(output / "results.json", results)
        print(f"{name}: {'PASS' if result['passed'] else 'FAIL'}; log={stdout}", flush=True)
        if not result["passed"]:
            raise RuntimeError(name + " failed; see " + str(stdout) + " and " + str(stderr))

    def private(assembly, *tail):
        return [private_host, "exec", "--fx-version", args.framework_version, assembly, *tail]

    failure = None
    try:
        run("stock", [dotnet, harness], "REFLECTION_POLICY_STOCK_TESTS PASS")
        run("disabled", private(harness), "REFLECTION_POLICY_STOCK_TESTS PASS")
        run("private", private(harness, "--require-private-runtime"),
            "REFLECTION_POLICY_PRIVATE_TESTS PASS cases=123", diagnostics=True)
        interpreted = re.findall(r"Compiled method: (.*ReflectionPolicy\.Author[^\r\n]*)",
                                 (output / "private.stdout.log").read_text(encoding="utf-8"))
        jit = (output / "private.jit").read_text(encoding="utf-8")
        proof = {"authorInterpreterMethods": interpreted,
                 "authorJitAbsent": not re.search(r"JIT compiled ReflectionPolicy\.Author\.", jit),
                 "compiledLibraryJit": "JIT compiled ReflectionPolicy.CompiledLibrary.ReflectionLibrary:Call(" in jit,
                 "compiledAccessLibraryJit": all("JIT compiled ReflectionPolicy.CompiledLibrary.ReflectionLibrary:" + name + "(" in jit
                                                 for name in ("Construct", "ReadField", "WriteField", "ReadProperty", "WriteProperty")),
                 "hostJit": "JIT compiled ReflectionPolicyTests:Exercise()" in jit}
        proof["compiledFactoryLibraryJit"] = all(
            "JIT compiled ReflectionPolicy.CompiledLibrary.ReflectionLibrary:" + name in jit
            for name in ("FastCall(", "FastConstruct(", "Activate["))
        stdout_text = (output / "private.stdout.log").read_text(encoding="utf-8")
        proof["sessionInterpreterMethods"] = re.findall(r"Compiled method: (.*ReflectionPolicy\.Author\.(?:SessionScript|LoadingScript|Denied\w+Script)[^\r\n]*)", stdout_text)
        proof["dynamicInterpreterMethods"] = re.findall(r"Compiled method: (.*DynamicDependency\.Payload[^\r\n]*)", stdout_text)
        proof["dynamicAuthorJitAbsent"] = "JIT compiled DynamicDependency.Payload:" not in jit
        proof["hostContractInterpreterMethods"] = re.findall(
            r"Compiled method: (.*HostContract\.(?:PolicyScript|DeniedScript|FailScript|PolicyDependency|ReflectScript|WrapperScript|DynamicScript|AliasScript|SessionDependencyScript|ShadowScript|SimpleScript|DependencyScript)\.[^\r\n]*)", stdout_text)
        proof["hostContractJitAbsent"] = not re.search(
            r"JIT compiled HostContract\.(?:PolicyScript|DeniedScript|FailScript|PolicyDependency|ReflectScript|WrapperScript|DynamicScript|AliasScript|SessionDependencyScript|ShadowScript|SimpleScript|DependencyScript)\.", jit)
        proof["hostContractHelperJit"] = "JIT compiled ReflectionPolicy.CompiledLibrary.SessionHooks:HostStartProbe(" in jit
        proof["hostContractDynamicAuthorJitAbsent"] = "JIT compiled System.Custom.DynamicAuthor." not in jit
        proof["hostContractDependencyInterpreterMethods"] = re.findall(
            r"Compiled method: (.*System\.Custom\.UgcDependency\.Call:Echo[^\r\n]*)", stdout_text)
        proof["hostContractDependencyJitAbsent"] = "JIT compiled System.Custom.UgcDependency.Call:" not in jit
        proof["genericContractInterpreterMethods"] = re.findall(
            r"Compiled method: (.*HostContract\.Generic[^\r\n]*)", stdout_text)
        proof["genericContractJitAbsent"] = not re.search(r"JIT compiled HostContract\.Generic", jit)
        proof["genericContractHelperJit"] = (
            "JIT compiled ReflectionPolicy.CompiledLibrary.SessionHooks:HostGenericReflectProbe(" in jit and
            "JIT compiled ReflectionPolicy.CompiledLibrary.SessionHooks:HostGenericBaseReflectProbe(" in jit and
            "JIT compiled ReflectionPolicy.CompiledLibrary.SessionHooks:HostGenericBaseAliasProbe(" in jit and
            "JIT compiled ReflectionPolicy.CompiledLibrary.SessionHooks:HostGenericBaseObjectControlProbe(" in jit)
        proof["compiledLoadHelperJit"] = "JIT compiled ReflectionPolicy.CompiledLibrary.SessionHooks:LoadTarget(" in jit
        proof["passed"] = (all(any(":" + name + "(" in method for method in interpreted)
                               for name in ("Own", "ThroughLibrary", "LibraryTouch", "FileWrite", "CatchDenied", "ABC", "RoundTrip", "LibraryRoundTrip",
                                            "Virtual", "Interface", "FastMethod", "GenericStruct"))
                           and proof["authorJitAbsent"] and proof["compiledLibraryJit"]
                           and proof["compiledAccessLibraryJit"] and proof["compiledFactoryLibraryJit"] and proof["hostJit"]
                           and proof["sessionInterpreterMethods"] and proof["dynamicInterpreterMethods"]
                           and proof["dynamicAuthorJitAbsent"] and proof["compiledLoadHelperJit"]
                           and any("PolicyScript" in method and "OnStart" in method
                                   for method in proof["hostContractInterpreterMethods"])
                           and proof["hostContractDependencyInterpreterMethods"]
                           and proof["hostContractDependencyJitAbsent"]
                           and any("GenericAllowed" in method and "OnStart" in method
                                   for method in proof["genericContractInterpreterMethods"])
                           and any("GenericReflect" in method and "OnStart" in method
                                   for method in proof["genericContractInterpreterMethods"])
                           and proof["genericContractJitAbsent"] and proof["genericContractHelperJit"]
                           and proof["hostContractJitAbsent"] and proof["hostContractHelperJit"]
                           and proof["hostContractDynamicAuthorJitAbsent"]
                           and any("ReflectScript" in method for method in proof["hostContractInterpreterMethods"]))
        write_json(output / "execution-proof.json", proof)
        if not proof["passed"]:
            raise RuntimeError("Interpreter/JIT evidence does not match the requested boundary.")
        run("lifecycle", private(lifecycle, "--require-interpreter"), "156/156 tests passed")

        # Compile the actual pinned upstream regression, without substitutes for xUnit.
        project = output / "upstream"
        project.mkdir()
        references = "".join('<Reference Include="' + name + '"><HintPath>' + escape(str(xunit / (name + ".dll")))
                             + '</HintPath></Reference>' for name in XUNIT_FILES)
        sources = "".join('<Compile Include="' + escape(str(source)) + '" />'
                          for source in (upstream, runtime / UPSTREAM_FIELDS, runtime / UPSTREAM_CONSTRUCTORS, runtime / UPSTREAM_HELPER))
        (project / "Upstream.csproj").write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
            '<TargetFramework>net11.0</TargetFramework><Nullable>annotations</Nullable></PropertyGroup><ItemGroup>'
            + sources + references + '</ItemGroup></Project>', encoding="utf-8")
        (project / "Driver.cs").write_text(
            'GitHub_130545.Test.DelegateOverStaticAbstractThroughGsharedvt();\n'
            'System.Console.WriteLine("UPSTREAM_GITHUB_130545 PASS");\n'
            'TrySetReadonlyStaticField2.TestSetValue();\n'
            'TrySetReadonlyStaticField2.TestSetValueDirect();\n'
            'System.Console.WriteLine("UPSTREAM_READONLY_FIELDS PASS cases=2");\n'
            'if (X.TestEntryPoint() != 100) throw new System.Exception("Abstract constructor regression failed.");\n'
            'System.Console.WriteLine("UPSTREAM_ABSTRACT_CONSTRUCTORS PASS");\n', encoding="utf-8")
        run("upstream-build", [dotnet, "build", project / "Upstream.csproj", "-c", "Release"])
        run("upstream-private", private(project / "bin/Release/net11.0/Upstream.dll"), "UPSTREAM_ABSTRACT_CONSTRUCTORS PASS")
    except Exception as error:
        failure = str(error)
    finally:
        after = {str(path): digest(path) if path.is_file() else None for path in sorted(inputs)}
        write_json(output / "pins-after.json", after)
        drift = [path for path in pins if pins[path] != after[path]]
        write_json(output / "summary.json", {"passed": failure is None and not drift, "failure": failure,
                   "inputCount": len(pins), "drift": drift, "runs": results,
                   "scope": "Opt-in MapSession automatic policy activation and controlled managed assembly loading on a matching private CoreLib; 13 ordinary loading routes; unsupported scoped delegate/dynamic routes refuse; no suppressed-flow/unmanaged/global all-load/sandbox acceptance."})
    if failure or drift:
        raise RuntimeError(failure or "Input drift: " + repr(drift))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("FAIL " + str(error), file=sys.stderr)
        sys.exit(1)
