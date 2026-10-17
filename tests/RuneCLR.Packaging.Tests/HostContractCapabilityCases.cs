using RuneCLR.Compiler;
using RuneCLR.Packages;

internal static class HostContractCapabilityCases
{
    internal static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Host contract Echo is approved before loading", EchoApproved);
        yield return ("Host contract rejects Object.ToString before loading", RejectToString);
        yield return ("Host contract rejects an OnStart parameter that is not the host interface", RejectObjectParameter);
        yield return ("Host contract rejects an interface method that is not allowed", RejectUnlistedMethod);
        yield return ("Host contract allows a same-assembly helper", SameAssemblyHelper);
        yield return ("Host contract allows a declared private helper", PrivateHelper);
        yield return ("Host contract rejects a private helper call outside the interface", PrivateHelperRejectsFile);
        yield return ("Host contract rejects a private helper that was not supplied", PrivateHelperRequiresImage);
        yield return ("Host contract allows a private helper to call the entry", PrivateHelperCallsEntry);
        yield return ("Host contract rejects a BCL call reached through the entry", PrivateHelperEntryRejectsBcl);
        yield return ("Host contract constructs an author type", AuthorNewIsChecked);
        yield return ("Host contract rejects a framework constructor", FrameworkNewIsRejected);
    }

    private static void EchoApproved() =>
        GameplayCapabilityPolicy.ValidateHostContract(CompileScript("api.Echo(41);"), "Script", "HostContract.IApi", ["Echo"]);

    private static void RejectToString()
    {
        var error = Check.Throws<InvalidDataException>(() =>
            GameplayCapabilityPolicy.ValidateHostContract(CompileScript("api.Echo(41); _ = api.ToString();"), "Script", "HostContract.IApi", ["Echo"]));
        Check.Assert(error.Message.Contains("Capability profile", StringComparison.Ordinal)
            && error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
    }


    private static void RejectObjectParameter()
    {
        var error = Check.Throws<InvalidDataException>(() =>
            GameplayCapabilityPolicy.ValidateHostContract(CompileCustom(
                "public sealed class Script { public void OnStart(object api) { } }"),
                "Script", "HostContract.IApi", ["Echo"]));
        Check.Assert(error.Message.Contains("Capability profile", StringComparison.Ordinal)
            && error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
    }

    private static void SameAssemblyHelper() =>
        GameplayCapabilityPolicy.ValidateHostContract(CompileContractType(
            "public sealed class Script { public void OnStart(HostContract.IApi api) { api.Echo(Add(40)); } private static int Add(int value) => value + 1; }"),
            "Script", "HostContract.IApi", ["Echo"]);

    private static void PrivateHelper()
    {
        var (script, helper) = CompilePrivateCall(false);
        GameplayCapabilityPolicy.ValidateHostContract(script, "Script", "HostContract.IApi", ["Echo"], [helper]);
    }

    private static void PrivateHelperRejectsFile()
    {
        var (script, helper) = CompilePrivateCall(true);
        var error = Check.Throws<InvalidDataException>(() =>
            GameplayCapabilityPolicy.ValidateHostContract(script, "Script", "HostContract.IApi", ["Echo"], [helper]));
        Check.Assert(error.Message.Contains("host contract member", StringComparison.Ordinal)
            && error.Message.Contains("ReadAllText", StringComparison.Ordinal), error.Message);
    }



    private static void AuthorNewIsChecked() =>
        GameplayCapabilityPolicy.ValidateHostContract(CompileContractType(
            "public sealed class Box { public int Value; public Box(int value) { Value = value; } public int Get() => Value; } public sealed class Script { public void OnStart(HostContract.IApi api) { api.Echo(new Box(41).Get()); } }"),
            "Script", "HostContract.IApi", ["Echo"]);

    private static void FrameworkNewIsRejected()
    {
        var error = Check.Throws<InvalidDataException>(() =>
            GameplayCapabilityPolicy.ValidateHostContract(CompileScript("throw new System.InvalidOperationException(\"x\");"), "Script", "HostContract.IApi", ["Echo"]));
        Check.Assert(error.Message.Contains("host contract member", StringComparison.Ordinal)
            && error.Message.Contains("InvalidOperationException", StringComparison.Ordinal), error.Message);
    }

    private static void PrivateHelperCallsEntry() =>
        GameplayCapabilityPolicy.ValidateHostContract(CompileMutual(false).Script, "Script", "HostContract.IApi", ["Echo"], [CompileMutual(false).Helper]);

    private static void PrivateHelperEntryRejectsBcl()
    {
        var built = CompileMutual(true);
        var error = Check.Throws<InvalidDataException>(() =>
            GameplayCapabilityPolicy.ValidateHostContract(built.Script, "Script", "HostContract.IApi", ["Echo"], [built.Helper]));
        Check.Assert(error.Message.Contains("host contract member", StringComparison.Ordinal)
            && error.Message.Contains("IsNullOrEmpty", StringComparison.Ordinal), error.Message);
    }

    private static (byte[] Script, byte[] Helper) CompileMutual(bool foreignEntry)
    {
        using var directory = new TempDirectory();
        var contract = SourceCompiler.Compile("HostContract", [new("Contract.cs",
            "namespace HostContract { public interface IApi { int Echo(int value); } }")],
            CompilerFixture.ApprovedReferences());
        Check.Assert(contract.Succeeded && contract.Assembly is not null, "Host contract did not compile.");
        var contractPath = Path.Combine(directory.Path, "HostContract.dll");
        File.WriteAllBytes(contractPath, contract.Assembly!);
        var references = CompilerFixture.ApprovedReferences();
        var first = SourceCompiler.Compile("HostScript", [new("Script.cs",
            "public sealed class Script { public static int Adjust(int value) => value; public void OnStart(HostContract.IApi api) { api.Echo(Adjust(1)); } }")],
            references.Concat([contractPath]).ToArray());
        Check.Assert(first.Succeeded && first.Assembly is not null,
            "Entry did not compile: " + string.Join("; ", first.Diagnostics.Select(item => item.Message)));
        var firstPath = Path.Combine(directory.Path, "HostScript.dll");
        File.WriteAllBytes(firstPath, first.Assembly!);
        var helper = SourceCompiler.Compile("HostHelper", [new("Helper.cs",
            "public static class Math { public static int AddOne(int value) => Script.Adjust(value) + 1; }")],
            references.Concat([firstPath]).ToArray());
        Check.Assert(helper.Succeeded && helper.Assembly is not null,
            "Helper did not compile: " + string.Join("; ", helper.Diagnostics.Select(item => item.Message)));
        var helperPath = Path.Combine(directory.Path, "HostHelper.dll");
        File.WriteAllBytes(helperPath, helper.Assembly!);
        var adjust = foreignEntry
            ? "public static int Adjust(int value) { _ = string.IsNullOrEmpty(\"x\"); return value; }"
            : "public static int Adjust(int value) => value;";
        var second = SourceCompiler.Compile("HostScript", [new("Script.cs",
            "public sealed class Script { " + adjust + " public void OnStart(HostContract.IApi api) { api.Echo(Math.AddOne(40)); } }")],
            references.Concat([contractPath, helperPath]).ToArray());
        Check.Assert(second.Succeeded && second.Assembly is not null,
            "Callback entry did not compile: " + string.Join("; ", second.Diagnostics.Select(item => item.Message)));
        return (second.Assembly!, helper.Assembly!);
    }

    private static void PrivateHelperRequiresImage()
    {
        var (script, _) = CompilePrivateCall(false);
        var error = Check.Throws<InvalidDataException>(() =>
            GameplayCapabilityPolicy.ValidateHostContract(script, "Script", "HostContract.IApi", ["Echo"]));
        Check.Assert(error.Message.Contains("host contract member", StringComparison.Ordinal)
            && error.Message.Contains("Math.AddOne", StringComparison.Ordinal), error.Message);
    }

    private static (byte[] Script, byte[] Helper) CompilePrivateCall(bool readFile)
    {
        var helperSource = readFile
            ? "public static class Math { public static int AddOne(int value) { _ = System.IO.File.ReadAllText(\"x\"); return value + 1; } }"
            : "public static class Math { public static int AddOne(int value) => value + 1; }";
        var helper = SourceCompiler.Compile("HostHelper", [new("Helper.cs", helperSource)], CompilerFixture.ApprovedReferences());
        Check.Assert(helper.Succeeded && helper.Assembly is not null,
            "Host helper did not compile: " + string.Join("; ", helper.Diagnostics.Select(item => item.Message)));
        using var directory = new TempDirectory();
        var contract = SourceCompiler.Compile("HostContract", [new("Contract.cs",
            "namespace HostContract { public interface IApi { int Echo(int value); } }")],
            CompilerFixture.ApprovedReferences());
        Check.Assert(contract.Succeeded && contract.Assembly is not null, "Host contract did not compile.");
        var contractPath = Path.Combine(directory.Path, "HostContract.dll");
        var helperPath = Path.Combine(directory.Path, "HostHelper.dll");
        File.WriteAllBytes(contractPath, contract.Assembly!);
        File.WriteAllBytes(helperPath, helper.Assembly!);
        var script = SourceCompiler.Compile("HostScript", [new("Script.cs",
            "public sealed class Script { public void OnStart(HostContract.IApi api) { api.Echo(Math.AddOne(40)); } }")],
            CompilerFixture.ApprovedReferences().Concat([contractPath, helperPath]).ToArray());
        Check.Assert(script.Succeeded && script.Assembly is not null,
            "Host script did not compile: " + string.Join("; ", script.Diagnostics.Select(item => item.Message)));
        return (script.Assembly!, helper.Assembly!);
    }

    private static void RejectUnlistedMethod()
    {
        var error = Check.Throws<InvalidDataException>(() =>
            GameplayCapabilityPolicy.ValidateHostContract(CompileContractScript(
                "namespace HostContract { public interface IApi { int Echo(int value); int Other(int value); } }",
                "api.Other(1);"),
                "Script", "HostContract.IApi", ["Echo"]));
        Check.Assert(error.Message.Contains("Capability profile", StringComparison.Ordinal)
            && error.Message.Contains("host contract member", StringComparison.Ordinal)
            && error.Message.Contains("HostContract.IApi.Other", StringComparison.Ordinal), error.Message);
    }
    private static byte[] CompileCustom(string source)
    {
        var script = SourceCompiler.Compile("HostScript", [new("Script.cs", source)], CompilerFixture.ApprovedReferences());
        Check.Assert(script.Succeeded && script.Assembly is not null,
            "Host script did not compile: " + string.Join("; ", script.Diagnostics.Select(item => item.Message)));
        return script.Assembly!;
    }
    private static byte[] CompileContractScript(string contractSource, string body)
    {
        using var directory = new TempDirectory();
        var contract = SourceCompiler.Compile("HostContract", [new("Contract.cs", contractSource)],
            CompilerFixture.ApprovedReferences());
        Check.Assert(contract.Succeeded && contract.Assembly is not null, "Host contract did not compile.");
        var contractPath = Path.Combine(directory.Path, "HostContract.dll");
        File.WriteAllBytes(contractPath, contract.Assembly!);
        var script = SourceCompiler.Compile("HostScript", [new("Script.cs",
            "public sealed class Script { public void OnStart(HostContract.IApi api) { " + body + " } }")],
            CompilerFixture.ApprovedReferences().Concat([contractPath]).ToArray());
        Check.Assert(script.Succeeded && script.Assembly is not null,
            "Host script did not compile: " + string.Join("; ", script.Diagnostics.Select(item => item.Message)));
        return script.Assembly!;
    }

    private static byte[] CompileContractType(string scriptSource) =>
        CompileContractSource("namespace HostContract { public interface IApi { int Echo(int value); } }", scriptSource);

    private static byte[] CompileContractSource(string contractSource, string scriptSource)
    {
        using var directory = new TempDirectory();
        var contract = SourceCompiler.Compile("HostContract", [new("Contract.cs", contractSource)],
            CompilerFixture.ApprovedReferences());
        Check.Assert(contract.Succeeded && contract.Assembly is not null, "Host contract did not compile.");
        var contractPath = Path.Combine(directory.Path, "HostContract.dll");
        File.WriteAllBytes(contractPath, contract.Assembly!);
        var script = SourceCompiler.Compile("HostScript", [new("Script.cs", scriptSource)],
            CompilerFixture.ApprovedReferences().Concat([contractPath]).ToArray());
        Check.Assert(script.Succeeded && script.Assembly is not null,
            "Host script did not compile: " + string.Join("; ", script.Diagnostics.Select(item => item.Message)));
        return script.Assembly!;
    }

    private static byte[] CompileScript(string body) => CompileContractScript(
        "namespace HostContract { public interface IApi { int Echo(int value); } }", body);
}
