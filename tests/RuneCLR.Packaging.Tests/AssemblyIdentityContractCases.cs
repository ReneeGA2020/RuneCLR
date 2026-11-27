using System.Reflection;
using RuneCLR.Compiler;
using RuneCLR.Packages;

internal static class AssemblyIdentityContractCases
{
    public static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Unsigned AssemblyName.FullName needs explicit culture and token for admission", UnsignedIdentity);
        yield return ("AssemblyName normalization preserves identity fields and does not approve mismatches", ExactIdentity);
    }

    private static string Contract => ManagedAssemblyInspector.Inspect(File.ReadAllBytes(Fixtures.ContractAssembly)).AssemblyName;

    private static string Normalize(AssemblyName actual)
    {
        var copy = (AssemblyName)actual.Clone();
        if (string.IsNullOrWhiteSpace(copy.Name) || copy.Version is null)
            throw new ArgumentException("An actual assembly name and version are required.", nameof(actual));

        copy.CultureName ??= string.Empty;
        if (copy.GetPublicKeyToken() is null)
            copy.SetPublicKeyToken([]);
        return copy.FullName!;
    }

    private static void UnsignedIdentity()
    {
        var result = SourceCompiler.Compile("UnsignedIdentityFixture", [new("Fixture.cs", """
            [assembly: System.Reflection.AssemblyVersion("2.3.4.5")]
            public static class Fixture
            {
                public static int Value() => 42;
            }
            """)], CompilerFixture.ApprovedReferences());
        Check.Assert(result.Succeeded, string.Join("; ", result.Diagnostics.Select(item => item.Message)));
        var image = result.Assembly!;
        var metadataIdentity = ManagedAssemblyInspector.Inspect(image).AssemblyName;
        var metadataName = new AssemblyName(metadataIdentity);
        var constructed = new AssemblyName
        {
            Name = metadataName.Name,
            Version = metadataName.Version,
            CultureName = metadataName.CultureName
        };
        var incomplete = constructed.FullName!;
        Check.Assert(incomplete.Contains("Culture=neutral", StringComparison.Ordinal) &&
            !incomplete.Contains("PublicKeyToken=", StringComparison.Ordinal), incomplete);
        var contract = Contract;
        var policy = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Allow, []);

        void Admit(string identity) =>
            GameplayCapabilityPolicy.ValidateWithStandardManagedDelegates(image, [identity], contract, policy);

        var rejection = Check.Throws<InvalidDataException>(() => Admit(incomplete));
        Check.Assert(rejection.Message.Contains("version, culture and public-key token", StringComparison.Ordinal), rejection.Message);
        Check.Throws<InvalidDataException>(() => Admit(metadataName.Name!));
        Check.Throws<InvalidDataException>(() => Admit(metadataIdentity.Replace(", Culture=neutral", "", StringComparison.Ordinal)));

        constructed.CultureName = null;
        var normalized = Normalize(constructed);
        Check.Assert(normalized == metadataIdentity &&
            normalized.EndsWith("Culture=neutral, PublicKeyToken=null", StringComparison.Ordinal), normalized);
        Check.Assert(constructed.CultureName is null && constructed.GetPublicKeyToken() is null,
            "Normalization must not modify the caller's AssemblyName.");
        Admit(metadataIdentity);
        Admit(normalized);
    }

    private static void ExactIdentity()
    {
        var actual = new AssemblyName("IdentityFixture, Version=2.3.4.5, Culture=fr, PublicKeyToken=1122334455667788, " +
            "Retargetable=Yes, ContentType=WindowsRuntime");
        var approved = Normalize(actual);
        Check.Assert(approved == actual.FullName, "Normalization changed an already complete identity.");
        var policy = GameplayCapabilityPolicy.CreateApiPolicy([approved], Contract);
        ApiDecision Evaluate(string identity) => policy.Evaluate(new(identity, ApiTargetKind.Assembly), ApiOperation.Reference);

        Check.Assert(Evaluate(approved).Allowed, "The exact identity should be approved.");
        foreach (var (field, original, replacement) in new[]
        {
            ("version", "Version=2.3.4.5", "Version=2.3.4.6"),
            ("culture", "Culture=fr", "Culture=neutral"),
            ("public-key token", "PublicKeyToken=1122334455667788", "PublicKeyToken=null"),
            ("content type", ", ContentType=WindowsRuntime", ""),
            ("retargetable flag", ", Retargetable=Yes", "")
        })
        {
            var mismatch = approved.Replace(original, replacement, StringComparison.Ordinal);
            Check.Assert(mismatch != approved && !Evaluate(mismatch).Allowed, $"A different {field} must not match.");
        }
    }
}
