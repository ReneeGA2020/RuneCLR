using System.Buffers.Binary;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using RuneCLR.Compiler;
using RuneCLR.Packages;

internal static class ExternalHostAdmissionCases
{
    private static string Contract => typeof(RuneCLR.IMapScript).Assembly.FullName!;
    private static readonly RuleBasedApiAccessPolicy AllowAll = new(ApiPolicyDefault.Allow, []);

    public static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("External public admission accepts method groups, closures and virtual BCL delegates", ManagedDelegates);
        yield return ("External delegate opt-in does not implicitly allow type tokens or reserved assembly names", IndependentOptions);
        yield return ("External default-deny delegate admission needs explicit framework dependencies", DefaultDeny);
        yield return ("External delegate target rules reopen one exact method and deny its sibling with rule diagnostics", TargetRules);
        yield return ("External policy can deny a standard delegate constructor despite the structural exception", ConstructorRules);
        yield return ("External admission rejects native signatures, custom delegates, PInvoke and InternalCall under default allow", NativeAndCustomShapes);
        yield return ("External admission rejects spoofed BCL identity and malformed known delegate constructors", SpoofedAndMalformedConstructors);
        yield return ("External static admission never loads images or runs author initializers or callbacks", MetadataOnly);
        yield return ("External intake and capability checks share an owned image snapshot", OwnedSnapshot);
    }

    private const string ActionSource = """
        namespace Author;
        public static class Entry
        {
            private static void Handler() { }
            public static System.Action Make() => Handler;
        }
        """;

    private static byte[] Compile(string name, string source, string[]? references = null, bool allowUnsafe = false)
    {
        var result = SourceCompiler.Compile(name, [new("Entry.cs", source)],
            references ?? CompilerFixture.ApprovedReferences(), allowUnsafe: allowUnsafe);
        Check.Assert(result.Succeeded, name + ": " + string.Join("; ", result.Diagnostics.Select(item => item.Message)));
        return result.Assembly!;
    }

    private static void Validate(byte[] image, IApiAccessPolicy? policy = null,
        bool allowReflectionTypeTokens = false, bool allowSessionAssemblyNames = false) =>
        GameplayCapabilityPolicy.ValidateWithStandardManagedDelegates(image, [], Contract, policy ?? AllowAll,
            allowReflectionTypeTokens, allowSessionAssemblyNames);

    private static void Denied(byte[] image, string reason, IApiAccessPolicy? policy = null)
    {
        var error = Check.Throws<InvalidDataException>(() => Validate(image, policy));
        Check.Assert(error.Message.Contains(reason, StringComparison.OrdinalIgnoreCase),
            "Expected rejection containing '" + reason + "': " + error.Message);
    }

    private static void ManagedDelegates()
    {
        var image = Compile("ExternalManagedDelegates", """
            namespace Author;
            public class Entry
            {
                public static System.Action Static() => new System.Action(Handler);
                private static void Handler() { }
                public System.Action Instance() => new System.Action(Run);
                public virtual void Run() { }
                public System.Action<int> Generic() => new System.Action<int>(Consume);
                public void Consume(int value) { }
                public static System.Func<string, int> Convert() => new System.Func<string, int>(Length);
                private static int Length(string value) => value.Length;
                public static System.Action Closure(int value) => () => ConsumeStatic(value);
                private static void ConsumeStatic(int value) { }
                public static System.EventHandler Event() => new System.EventHandler(OnEvent);
                private static void OnEvent(object sender, System.EventArgs args) { }
            }
            """);
        Validate(image);
        var identity = ManagedAssemblyInspector.Inspect(image).AssemblyName;
        var strict = Check.Throws<InvalidDataException>(() =>
            GameplayCapabilityPolicy.ValidateWithApiPolicy(image, [identity], Contract, AllowAll));
        Check.Assert(strict.Message.Contains("IntPtr", StringComparison.Ordinal),
            "The existing policy entry must retain its native-int rejection.");
        Check.Throws<InvalidDataException>(() => GameplayCapabilityPolicy.Validate(image, [identity], Contract));
    }

    private static void IndependentOptions()
    {
        var typeToken = Compile("ExternalTypeToken", """
            namespace Author;
            public static class Entry { public static object Token() => typeof(Entry); }
            """);
        Denied(typeToken, "ldtoken");
        Validate(typeToken, allowReflectionTypeTokens: true);
        var reserved = Compile("RuneCLR.ExternalName", ActionSource);
        Denied(reserved, "spoofs");
        Validate(reserved, allowSessionAssemblyNames: true);
    }

    private static void DefaultDeny()
    {
        var image = Compile("ExternalDefaultDeny", ActionSource);
        Denied(image, "configured default", new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny, []));
        Validate(image, new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new("framework", ApiRuleEffect.Include, AssemblyName: "System.Runtime")]));
    }

    private static void WithHostApi(Action<string[]> run)
    {
        using var directory = new TempDirectory();
        var api = Compile("ExternalHostApi", """
            namespace Host.Api;
            public static class Events
            {
                public static int Calls;
                public static void Allowed() { Calls++; }
                public static void Sibling() { Calls += 100; }
            }
            """);
        var path = Path.Combine(directory.Path, "ExternalHostApi.dll");
        File.WriteAllBytes(path, api);
        run(CompilerFixture.ApprovedReferences().Append(path).ToArray());
    }

    private static void TargetRules()
    {
        WithHostApi(references =>
        {
            var allowed = Compile("ExternalAllowed", """
                namespace Author;
                public static class Entry { public static System.Action Make() => Host.Api.Events.Allowed; }
                """, references);
            var sibling = Compile("ExternalSibling", """
                namespace Author;
                public static class Entry { public static System.Action Make() => Host.Api.Events.Sibling; }
                """, references);
            foreach (var defaultDecision in new[] { ApiPolicyDefault.Allow, ApiPolicyDefault.Deny })
            {
                ApiRule[] rules =
                [
                    new("framework", ApiRuleEffect.Include, AssemblyName: "System.Runtime"),
                    new("deny-host-type", ApiRuleEffect.Exclude, AssemblyName: "ExternalHostApi", TypeName: "Host.Api.Events"),
                    new("include-handler", ApiRuleEffect.Include, AssemblyName: "ExternalHostApi", TypeName: "Host.Api.Events",
                        MemberKind: ApiTargetKind.Method, MemberName: "Allowed",
                        Signature: new("System.Void", [], 0, false))
                ];
                var policy = new RuleBasedApiAccessPolicy(defaultDecision, rules);
                Validate(allowed, policy);
                Denied(sibling, "deny-host-type", policy);
                Denied(allowed, "deny-allowed", new RuleBasedApiAccessPolicy(defaultDecision,
                    rules.Append(new("deny-allowed", ApiRuleEffect.Exclude,
                        AssemblyName: "ExternalHostApi", TypeName: "Host.Api.Events",
                        MemberKind: ApiTargetKind.Method, MemberName: "Allowed",
                        Signature: new("System.Void", [], 0, false)))));
            }
        });
    }

    private static void ConstructorRules()
    {
        var image = Compile("ExternalCtorPolicy", ActionSource);
        var deny = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Allow,
        [new("deny-action-ctor", ApiRuleEffect.Exclude, TypeName: "System.Action", MemberKind: ApiTargetKind.Method,
            MemberName: ".ctor", Signature: new("System.Void", ["System.Object", "System.IntPtr"], 0, true))]);
        Denied(image, "deny-action-ctor", deny);
    }

    private static void NativeAndCustomShapes()
    {
        string[] sources =
        [
            "public static class Entry { public static System.IntPtr Echo(System.IntPtr value) => value; }",
            "public static class Entry { public static System.UIntPtr Value; }",
            "public static class Entry { public static unsafe void* Echo(void* value) => value; }",
            "public static class Entry { public static unsafe delegate*<void> Pointer; }",
            "public delegate void Custom(); public static class Entry { public static Custom Make() => Target; static void Target() {} }",
            "public class Fake { public Fake(object target, System.IntPtr pointer) {} }",
            "public static class Entry { public static System.Action<System.IntPtr> Value; }"
        ];
        foreach (var source in sources)
            Check.Throws<InvalidDataException>(() => Validate(Compile("ExternalUnsafeShape", source, allowUnsafe: true)));

        // CoreLib contains the real interop attributes; the tiny reference fixture does not.
        string[] references = [typeof(object).Assembly.Location];
        var pinvoke = Compile("ExternalPInvoke", """
            public static class Entry
            {
                [System.Runtime.InteropServices.DllImport("must-never-be-loaded")]
                public static extern int Native();
            }
            """, references);
        Denied(pinvoke, "P/Invoke");
        var internalCall = Compile("ExternalInternalCall", """
            public static class Entry
            {
                [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.InternalCall)]
                public static extern int Native();
            }
            """, references);
        Denied(internalCall, "InternalCall");
    }

    private static void SpoofedAndMalformedConstructors()
    {
        var image = Compile("ExternalMalformedCtor", ActionSource);
        Validate(image);
        using var pe = new PEReader(new MemoryStream(image, writable: false));
        var metadata = pe.GetMetadataReader();
        var constructor = metadata.MemberReferences.Select(metadata.GetMemberReference)
            .Single(member => metadata.GetString(member.Name) == ".ctor" &&
                member.Parent.Kind == HandleKind.TypeReference &&
                metadata.GetString(metadata.GetTypeReference((TypeReferenceHandle)member.Parent).Name) == "Action");
        var signature = BlobOffset(pe, metadata, constructor.Signature);
        Check.Assert(image.AsSpan(signature, 5).SequenceEqual(new byte[] { 0x20, 0x02, 0x01, 0x1C, 0x18 }),
            "The control must start with the canonical Action(object, native int) MemberRef signature.");
        foreach (var (index, value) in new[] { (0, (byte)0x00), (1, (byte)0x01), (4, (byte)0x08) })
        {
            var copy = (byte[])image.Clone();
            copy[signature + index] = value; // static ctor, missing native-int slot, or int32 slot
            Denied(copy, "delegate constructor");
        }
        var reference = metadata.AssemblyReferences.Select(metadata.GetAssemblyReference)
            .Single(item => metadata.GetString(item.Name) == "System.Runtime");
        var tokenOffset = BlobOffset(pe, metadata, reference.PublicKeyOrToken);
        var spoof = (byte[])image.Clone();
        spoof[tokenOffset] ^= 0x01; // same BCL simple/type name, wrong public key token
        Denied(spoof, "IntPtr");
    }

    private static int BlobOffset(PEReader pe, MetadataReader metadata, BlobHandle handle)
    {
        var offset = pe.PEHeaders.MetadataStartOffset + metadata.GetHeapMetadataOffset(HeapIndex.Blob) +
            MetadataTokens.GetHeapOffset(handle);
        var prefixSize = (pe.GetMetadataReader().GetBlobBytes(handle).Length < 0x80) ? 1 : 2;
        return offset + prefixSize; // all fixture blobs are short
    }

    private static void MetadataOnly()
    {
        var marker = "RUNECLR_EXTERNAL_ADMISSION_" + Guid.NewGuid().ToString("N");
        var name = "ExternalNoLoad" + Guid.NewGuid().ToString("N");
        var image = Compile(name, $$"""
            namespace Author;
            public static class Entry
            {
                static Entry() { System.Environment.SetEnvironmentVariable("{{marker}}", "initializer"); }
                public static System.Action Make() => Handler;
                private static void Handler() { System.Environment.SetEnvironmentVariable("{{marker}}", "callback"); }
            }
            """, [typeof(object).Assembly.Location]);
        var loaded = new List<string>();
        AssemblyLoadEventHandler onLoad = (_, args) => loaded.Add(args.LoadedAssembly.GetName().Name!);
        AppDomain.CurrentDomain.AssemblyLoad += onLoad;
        try
        {
            Validate(image);
            Denied(image, "deny-handler", new RuleBasedApiAccessPolicy(ApiPolicyDefault.Allow,
                [new("deny-handler", ApiRuleEffect.Exclude, TypeName: "System.Environment", MemberName: "SetEnvironmentVariable")]));
            Check.Assert(!loaded.Contains(name) && !AppDomain.CurrentDomain.GetAssemblies().Any(a => a.GetName().Name == name),
                "Validation must not load the author image into any context.");
            Check.Assert(Environment.GetEnvironmentVariable(marker) is null,
                "Neither the author initializer nor callback may run during admission.");
        }
        finally { AppDomain.CurrentDomain.AssemblyLoad -= onLoad; }
    }

    private static void OwnedSnapshot()
    {
        var image = Compile("ExternalSnapshot", ActionSource);
        using var pe = new PEReader(new MemoryStream(image, writable: false));
        var metadata = pe.GetMetadataReader();
        var handle = metadata.MethodDefinitions.First(item => metadata.GetString(metadata.GetMethodDefinition(item).Name) == "Make");
        var flagsOffset = pe.PEHeaders.MetadataStartOffset + metadata.GetTableMetadataOffset(TableIndex.MethodDef) +
            (MetadataTokens.GetRowNumber(handle) - 1) * metadata.GetTableRowSize(TableIndex.MethodDef) + 6;
        var policy = new MutatingPolicy(() => BinaryPrimitives.WriteUInt16LittleEndian(image.AsSpan(flagsOffset, 2),
            (ushort)(metadata.GetMethodDefinition(handle).Attributes | MethodAttributes.PinvokeImpl)));
        Validate(image, policy);
        Check.Assert(policy.Mutated, "The callback must mutate the caller-owned image during evaluation.");
        Denied(image, "P/Invoke"); // the caller's altered bytes are unsafe, the inspected snapshot was not
    }

    private sealed class MutatingPolicy(Action mutate) : IApiAccessPolicy
    {
        public bool Mutated { get; private set; }
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation)
        {
            if (!Mutated) { mutate(); Mutated = true; }
            return ApiDecision.Allow;
        }
    }
}
