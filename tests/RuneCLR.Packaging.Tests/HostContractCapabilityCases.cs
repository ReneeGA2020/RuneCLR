using RuneCLR.Compiler;
using RuneCLR.Packages;

internal static class HostContractCapabilityCases
{
    internal static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Host contract Echo is approved before loading", EchoApproved);
        yield return ("Host contract rejects Object.ToString before loading", RejectToString);
        yield return ("Host contract rejects an OnStart parameter that is not the host interface", RejectObjectParameter);
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

    private static byte[] CompileCustom(string source)
    {
        var script = SourceCompiler.Compile("HostScript", [new("Script.cs", source)], CompilerFixture.ApprovedReferences());
        Check.Assert(script.Succeeded && script.Assembly is not null,
            "Host script did not compile: " + string.Join("; ", script.Diagnostics.Select(item => item.Message)));
        return script.Assembly!;
    }
    private static byte[] CompileScript(string body)
    {
        using var directory = new TempDirectory();
        var contract = SourceCompiler.Compile("HostContract", [new("Contract.cs",
            "namespace HostContract { public interface IApi { int Echo(int value); } }")],
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
}
