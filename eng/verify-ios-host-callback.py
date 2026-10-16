#!/usr/bin/env python3
"""Run the iOS host source on the desktop and check that its callback closes.

This does not start a simulator and does not prove native execution.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "eng" / "ios-trusted-update" / "Host.cs"
CONTRACT = ROOT / "eng" / "ios-trusted-update" / "Contract.cs"


def write(path, text):
    path.write_text(text, encoding="utf-8", newline="\n")


def project(directory, name, output, sources, references):
    directory.mkdir(parents=True)
    refs = "\n".join('    <ProjectReference Include="%s" />' % ref for ref in references)
    compiles = "\n".join('    <Compile Include="%s" />' % source for source in sources)
    write(directory / (name + ".csproj"), """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net11.0</TargetFramework>
    <ImplicitUsings>disable</ImplicitUsings>
    <Nullable>disable</Nullable>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
    <AssemblyName>%s</AssemblyName>
    <OutputType>%s</OutputType>
  </PropertyGroup>
  <ItemGroup>
%s
  </ItemGroup>
  <ItemGroup>
%s
  </ItemGroup>
</Project>
""" % (name, output, compiles, refs))


def build(project_path, log_path):
    completed = subprocess.run(
        ["dotnet", "build", str(project_path), "-c", "Release", "--nologo"],
        cwd=project_path.parent, capture_output=True, text=True, check=False)
    log_path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    return completed.returncode == 0


def main():
    root = Path(tempfile.mkdtemp(prefix="runeclr-host-callback-"))
    try:
        contract = root / "contract"
        private = root / "private"
        helper = root / "helper"
        update = root / "update"
        host = root / "host"
        project(contract, "TrustedUpdate.Contract", "Library", [CONTRACT.as_posix()], [])
        project(private, "TrustedUpdate.Private", "Library", [(private / "Private.cs").as_posix()], [])
        project(helper, "TrustedUpdate.IlOnlyHelper", "Library", [(helper / "Helper.cs").as_posix()], [])
        project(update, "TrustedUpdate.Update", "Library", [(update / "Update.cs").as_posix()], [(contract / "TrustedUpdate.Contract.csproj").as_posix()])
        selector = ROOT / "src" / "RuneCLR.TrustedUpdate" / "RuneCLR.TrustedUpdate.csproj"
        project(host, "TrustedUpdate.HostProbe", "Exe", [HOST.as_posix(), (host / "Probe.cs").as_posix()], [(contract / "TrustedUpdate.Contract.csproj").as_posix(), selector.as_posix()])
        write(private / "Private.cs", "namespace TrustedUpdate { public static class PrivateBehavior { public static int Value() => 100; } }\n")
        write(helper / "Helper.cs", "namespace TrustedUpdate { public static class IlOnlyHelper { public static int Compute(int value) => value + 1; } }\n")
        write(update / "Update.cs", """using System;
namespace TrustedUpdate
{
    public static class Kept
    {
        public static IHostApi Host;
        public static Func<int, int> Callback;
    }

    public sealed class Update
    {
        public int Run(IHostApi host, Func<int, int> callback)
        {
            Kept.Host = host;
            Kept.Callback = callback;
            int echoed = host.Echo(41);
            int callbackValue = callback(41);
            Console.WriteLine("PROBE echo=" + echoed + " callback=" + callbackValue);
            return echoed + callbackValue;
        }
    }
}
""")
        write(host / "Probe.cs", """using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.Loader;

static class Probe
{
    static int Main(string[] args)
    {
        Environment.SetEnvironmentVariable("RUNECLR_UPDATE_DIR", args[0]);
        if (string.IsNullOrEmpty(Environment.GetEnvironmentVariable("RUNECLR_EXPECTED_VERSION")))
            Environment.SetEnvironmentVariable("RUNECLR_EXPECTED_VERSION", "A");
        var writer = new StringWriter();
        Console.SetOut(writer);
        int code = TrustedUpdate.Driver.Run();
        string during = writer.ToString();
        if (code != 0)
        {
            Console.Error.WriteLine(during);
            Console.Error.WriteLine("code=" + code);
            return 1;
        }
        var update = AssemblyLoadContext.All.SelectMany(context => context.Assemblies)
            .First(assembly => assembly.GetName().Name == "TrustedUpdate.Update");
        var kept = update.GetType("TrustedUpdate.Kept");
        var host = (TrustedUpdate.IHostApi)kept.GetField("Host").GetValue(null);
        var callback = (Func<int, int>)kept.GetField("Callback").GetValue(null);
        bool echoClosed = false;
        bool callbackClosed = false;
        try { host.Echo(9); }
        catch (InvalidOperationException exception) when (exception.Message == "host callback closed") { echoClosed = true; }
        try { callback(9); }
        catch (InvalidOperationException exception) when (exception.Message == "host callback closed") { callbackClosed = true; }
        bool unchanged = writer.ToString() == during;
        var flags = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
        bool storesHost = typeof(TrustedUpdate.Driver).GetFields(flags).Any(field =>
            typeof(Delegate).IsAssignableFrom(field.FieldType) || typeof(TrustedUpdate.IHostApi).IsAssignableFrom(field.FieldType));
        bool once = during.Split("HOST_ECHO=").Length - 1 == 1 && during.Split("HOST_DELEGATE=").Length - 1 == 1;
        bool success = code == 0 && during.Contains("TRUSTED_UPDATE_SUCCESS version=A result=85") && during.Contains("PROBE echo=42 callback=43");
        bool passed = success && echoClosed && callbackClosed && unchanged && once && !storesHost;
        Console.Error.WriteLine(passed ? "HOST_CALLBACK_CLOSED" : "HOST_CALLBACK_OPEN");
        Console.Error.WriteLine("code=" + code + " echoClosed=" + echoClosed + " callbackClosed=" + callbackClosed + " unchanged=" + unchanged + " once=" + once + " storesHost=" + storesHost);
        Console.Error.WriteLine(during);
        return passed ? 0 : 1;
    }
}
""")
        logs = root / "logs"
        logs.mkdir()
        for name, path in (
            ("contract", contract / "TrustedUpdate.Contract.csproj"),
            ("private", private / "TrustedUpdate.Private.csproj"),
            ("helper", helper / "TrustedUpdate.IlOnlyHelper.csproj"),
            ("update", update / "TrustedUpdate.Update.csproj"),
            ("host", host / "TrustedUpdate.HostProbe.csproj"),
        ):
            if not build(path, logs / (name + ".log")):
                print((logs / (name + ".log")).read_text(encoding="utf-8")[-2000:])
                print("BUILD_FAIL " + name)
                return 1
        payload = root / "payload"
        payload.mkdir()
        for folder, assembly in (
            (update, "TrustedUpdate.Update.dll"),
            (private, "TrustedUpdate.Private.dll"),
            (helper, "TrustedUpdate.IlOnlyHelper.dll"),
            (contract, "TrustedUpdate.Contract.dll"),
        ):
            shutil.copy2(folder / "bin" / "Release" / "net11.0" / assembly, payload / assembly)
        probe = host / "bin" / "Release" / "net11.0" / "TrustedUpdate.HostProbe.dll"
        completed = subprocess.run(
            ["dotnet", "exec", str(probe), str(payload)],
            cwd=probe.parent, capture_output=True, text=True, check=False)
        sys.stderr.write(completed.stderr)
        sys.stdout.write(completed.stdout)
        if completed.returncode != 0:
            return completed.returncode
        def file_hash(path):
            return hashlib.sha256(path.read_bytes()).hexdigest()

        def write_list(names):
            lines = [name + " " + file_hash(payload / name) for name in names]
            (payload / "payload-files.txt").write_text("\n".join(lines) + "\n", encoding="ascii")

        def run_probe():
            return subprocess.run(
                ["dotnet", "exec", str(probe), str(payload)],
                cwd=probe.parent, capture_output=True, text=True, check=False)

        names = [
            "TrustedUpdate.Update.dll",
            "TrustedUpdate.Private.dll",
            "TrustedUpdate.IlOnlyHelper.dll",
            "TrustedUpdate.Contract.dll",
        ]
        write_list(names)
        listed = run_probe()
        sys.stderr.write(listed.stderr)
        if listed.returncode != 0 or "HOST_CALLBACK_CLOSED" not in listed.stderr:
            print("LISTED_FAIL")
            return 1
        write_list([name for name in names if name != "TrustedUpdate.Private.dll"])
        unlisted = run_probe()
        unlisted_text = unlisted.stdout + unlisted.stderr
        if unlisted.returncode == 0 or "payload file is not listed: TrustedUpdate.Private.dll" not in unlisted_text or "TRUSTED_UPDATE_SUCCESS" in unlisted_text:
            print(unlisted_text[-1500:])
            print("UNLISTED_FAIL")
            return 1
        write_list(names)
        private_bytes = bytearray((payload / "TrustedUpdate.Private.dll").read_bytes())
        private_bytes[-1] ^= 1
        (payload / "TrustedUpdate.Private.dll").write_bytes(private_bytes)
        tampered = run_probe()
        tampered_text = tampered.stdout + tampered.stderr
        if tampered.returncode == 0 or "payload file hash mismatch: TrustedUpdate.Private.dll" not in tampered_text or "TRUSTED_UPDATE_SUCCESS" in tampered_text:
            print(tampered_text[-1500:])
            print("TAMPER_FAIL")
            return 1
        print("PAYLOAD_LIST_CLOSED")
        shutil.copy2(private / "bin" / "Release" / "net11.0" / "TrustedUpdate.Private.dll", payload / "TrustedUpdate.Private.dll")
        write(update / "Update.cs", """using System;
namespace TrustedUpdate
{
    public sealed class Update
    {
        public int Run(IHostApi host, Func<int, int> callback)
        {
            throw new InvalidOperationException(\"update-private-failure-9f3c\");
        }
    }
}
""")
        if not build(update / "TrustedUpdate.Update.csproj", logs / "throwing-update.log"):
            print((logs / "throwing-update.log").read_text(encoding="utf-8")[-2000:])
            print("THROWING_BUILD_FAIL")
            return 1
        shutil.copy2(update / "bin" / "Release" / "net11.0" / "TrustedUpdate.Update.dll", payload / "TrustedUpdate.Update.dll")
        list_path = payload / "payload-files.txt"
        if list_path.exists():
            list_path.unlink()
        thrown = run_probe()
        thrown_text = thrown.stdout + thrown.stderr
        if thrown.returncode == 0 or "failure=ActivationFailed" not in thrown_text or "update-private-failure-9f3c" in thrown_text or "TRUSTED_UPDATE_SUCCESS" in thrown_text:
            print(thrown_text[-1500:])
            print("THROWING_FAIL")
            return 1
        print("UPDATE_EXCEPTION_HIDDEN")
        write(update / "Update.cs", """using System;
namespace TrustedUpdate
{
    public sealed class Update
    {
        public int Run(IHostApi host, Func<int, int> callback)
        {
            throw new InvalidOperationException("payload file leaked-from-update");
        }
    }
}
""")
        if not build(update / "TrustedUpdate.Update.csproj", logs / "spoofed-update.log"):
            print((logs / "spoofed-update.log").read_text(encoding="utf-8")[-2000:])
            print("SPOOFED_BUILD_FAIL")
            return 1
        shutil.copy2(update / "bin" / "Release" / "net11.0" / "TrustedUpdate.Update.dll", payload / "TrustedUpdate.Update.dll")
        spoofed = run_probe()
        spoofed_text = spoofed.stdout + spoofed.stderr
        if spoofed.returncode == 0 or "failure=ActivationFailed" not in spoofed_text or "payload file leaked-from-update" in spoofed_text or "TRUSTED_UPDATE_SUCCESS" in spoofed_text:
            print(spoofed_text[-1500:])
            print("SPOOFED_FAIL")
            return 1
        print("UPDATE_DIAGNOSTIC_NOT_SPOOFED")
        write(update / "Update.cs", """using System;
namespace TrustedUpdate
{
    public static class Kept
    {
        public static IHostApi Host;
        public static Func<int, int> Callback;
    }

    public sealed class Update
    {
        public int Run(IHostApi host, Func<int, int> callback)
        {
            Kept.Host = host;
            Kept.Callback = callback;
            int echoed = host.Echo(41);
            int callbackValue = callback(41);
            Console.WriteLine("PROBE echo=" + echoed + " callback=" + callbackValue);
            return echoed + callbackValue;
        }
    }
}
""")
        if not build(update / "TrustedUpdate.Update.csproj", logs / "planned-update.log"):
            print((logs / "planned-update.log").read_text(encoding="utf-8")[-2000:])
            print("PLANNED_BUILD_FAIL")
            return 1
        shutil.copy2(update / "bin" / "Release" / "net11.0" / "TrustedUpdate.Update.dll", payload / "TrustedUpdate.Update.dll")
        digest = hashlib.sha256((payload / "TrustedUpdate.Update.dll").read_bytes()).hexdigest()
        plan_lines = [
            "versionName A",
            "contentSha256 " + digest,
            "assemblyFile TrustedUpdate.Update.dll",
            "entryTypeName TrustedUpdate.Update",
            "entryMethodName Run",
            "runtime ios-simulator",
            "architecture arm64",
        ]
        (payload / "selector-plan.txt").write_text(chr(10).join(plan_lines) + chr(10), encoding="ascii")

        def run_planned(approval_hash):
            env = dict(os.environ)
            env["RUNECLR_HOST_RUNTIME"] = "ios-simulator"
            env["RUNECLR_HOST_ARCHITECTURE"] = "arm64"
            env["RUNECLR_APPROVAL_ID"] = "desktop-plan"
            env["RUNECLR_APPROVAL_VERSION"] = "A"
            env["RUNECLR_APPROVAL_HASH"] = approval_hash
            return subprocess.run(
                ["dotnet", "exec", str(probe), str(payload)],
                cwd=probe.parent, capture_output=True, text=True, check=False, env=env)

        rejected = run_planned("0" * 64)
        rejected_text = rejected.stdout + rejected.stderr
        if (rejected.returncode == 0 or "failure=NotApproved" not in rejected_text
                or "TRUSTED_UPDATE_SUCCESS" in rejected_text or "HOST_ECHO=" in rejected_text
                or "SELECTOR_PLAN" in rejected_text):
            print(rejected_text[-1500:])
            print("SELECTOR_REJECT_FAIL")
            return 1
        accepted = run_planned(digest)
        accepted_text = accepted.stdout + accepted.stderr
        if (accepted.returncode != 0 or "SELECTOR_PLAN version=A" not in accepted_text
                or "TRUSTED_UPDATE_SUCCESS version=A result=85" not in accepted_text
                or "failure=NotApproved" in accepted_text):
            print(accepted_text[-1500:])
            print("SELECTOR_ACCEPT_FAIL")
            return 1
        print("SELECTOR_PLAN_BEFORE_LOAD")
        good_dir = payload.parent / "payload-good"
        if good_dir.exists():
            shutil.rmtree(good_dir)
        shutil.copytree(payload, good_dir)
        store = payload.parent / "last-known-good.json"
        root_dir = str(payload.parent)

        def run_dir(target, approval_version, approval_hash, expected, fallback=None):
            env = dict(os.environ)
            env["RUNECLR_HOST_RUNTIME"] = "ios-simulator"
            env["RUNECLR_HOST_ARCHITECTURE"] = "arm64"
            env["RUNECLR_APPROVAL_ID"] = "desktop-plan"
            env["RUNECLR_APPROVAL_VERSION"] = approval_version
            env["RUNECLR_APPROVAL_HASH"] = approval_hash
            env["RUNECLR_EXPECTED_VERSION"] = expected
            env["RUNECLR_LAST_KNOWN_GOOD"] = str(store)
            env["RUNECLR_LAST_KNOWN_GOOD_ROOT"] = root_dir
            if fallback is not None:
                env["RUNECLR_FALLBACK_APPROVAL_ID"] = fallback[0]
                env["RUNECLR_FALLBACK_APPROVAL_VERSION"] = fallback[1]
                env["RUNECLR_FALLBACK_APPROVAL_HASH"] = fallback[2]
            return subprocess.run(
                ["dotnet", "exec", str(probe), str(target)],
                cwd=probe.parent, capture_output=True, text=True, check=False, env=env)

        recorded = run_dir(good_dir, "A", digest, "A")
        recorded_text = recorded.stdout + recorded.stderr
        if recorded.returncode != 0 or "SELECTOR_PLAN version=A" not in recorded_text or not store.is_file():
            print(recorded_text[-1500:])
            print("STORE_FAIL")
            return 1
        stored_bytes = store.read_bytes()
        if b"Exception" in stored_bytes or b"update-private-failure-9f3c" in stored_bytes:
            print("STORE_LEAK")
            return 1
        quote = chr(34)
        throwing = chr(10).join([
            "using System;",
            "namespace TrustedUpdate",
            "{",
            "    public sealed class Update",
            "    {",
            "        public int Run(IHostApi host, Func<int, int> callback)",
            "        {",
            "            throw new InvalidOperationException(" + quote + "update-private-failure-9f3c" + quote + ");",
            "        }",
            "    }",
            "}",
            "",
        ])
        write(update / "Update.cs", throwing)
        if not build(update / "TrustedUpdate.Update.csproj", logs / "fallback-throw.log"):
            print((logs / "fallback-throw.log").read_text(encoding="utf-8")[-2000:])
            print("FALLBACK_BUILD_FAIL")
            return 1
        bad_dir = payload.parent / "payload-bad"
        if bad_dir.exists():
            shutil.rmtree(bad_dir)
        shutil.copytree(payload, bad_dir)
        shutil.copy2(update / "bin" / "Release" / "net11.0" / "TrustedUpdate.Update.dll", bad_dir / "TrustedUpdate.Update.dll")
        bad_digest = hashlib.sha256((bad_dir / "TrustedUpdate.Update.dll").read_bytes()).hexdigest()
        bad_plan = [
            "versionName B",
            "contentSha256 " + bad_digest,
            "assemblyFile TrustedUpdate.Update.dll",
            "entryTypeName TrustedUpdate.Update",
            "entryMethodName Run",
            "runtime ios-simulator",
            "architecture arm64",
        ]
        (bad_dir / "selector-plan.txt").write_text(chr(10).join(bad_plan) + chr(10), encoding="ascii")
        fallback = ("desktop-plan", "A", digest)
        restored = run_dir(bad_dir, "B", "0" * 64, "B", fallback)
        restored_text = restored.stdout + restored.stderr
        if (restored.returncode != 0
                or "SELECTOR_FALLBACK version=A candidateFailure=NotApproved" not in restored_text
                or "TRUSTED_UPDATE_SUCCESS version=A result=85" not in restored_text
                or "SELECTOR_PLAN" in restored_text
                or "update-private-failure-9f3c" in restored_text
                or store.read_bytes() != stored_bytes):
            print(restored_text[-1800:])
            print("FALLBACK_FAIL")
            return 1
        activated = run_dir(bad_dir, "B", bad_digest, "B", fallback)
        activated_text = activated.stdout + activated.stderr
        if (activated.returncode == 0
                or "failure=ActivationFailed" not in activated_text
                or "SELECTOR_FALLBACK" in activated_text
                or "TRUSTED_UPDATE_SUCCESS" in activated_text
                or "update-private-failure-9f3c" in activated_text
                or store.read_bytes() != stored_bytes):
            print(activated_text[-1800:])
            print("ACTIVATION_STORE_FAIL")
            return 1
        print("SELECTOR_FALLBACK_BEFORE_LOAD")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
