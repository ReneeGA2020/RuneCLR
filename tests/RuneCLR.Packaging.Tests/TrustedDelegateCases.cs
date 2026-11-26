using System.Buffers.Binary;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using RuneCLR.Compiler;
using RuneCLR.Packages;

internal static class TrustedDelegateCases
{
    private static readonly string CoreLib = typeof(object).Assembly.Location;
    private static readonly string Contract = typeof(RuneCLR.IMapScript).Assembly.FullName!;
    private const string DelegateName = "Trusted.Callbacks.Callback`1";
    private static readonly RuleBasedApiAccessPolicy Allow = new(ApiPolicyDefault.Allow, []);
    private const string ProviderSource = """
        using System.Threading.Tasks;
        [assembly: System.Reflection.AssemblyVersion("1.0.0.0")]
        namespace Trusted.Callbacks
        {
            public delegate Task<bool> Callback<T>(object sender, T value);
            public delegate int Plain(int value);
            public static class Host
            {
                public static Task<bool> Handle(object sender, object value) => Task.FromResult(true);
                public static Task<bool> Sibling(object sender, object value) => Task.FromResult(false);
                [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.InternalCall)]
                public static extern int TrustedNative();
            }
            public sealed class Fake { public Fake(object target, System.IntPtr pointer) { } }
        }
        """;
    private const string AuthorSource = """
        using System.Threading.Tasks;
        public static class Entry
        {
            static Task<bool> Handle(object sender, object value) => Task.FromResult(true);
            public static Trusted.Callbacks.Callback<object> Make() => Handle;
            public static Task<bool> Run(Trusted.Callbacks.Callback<object> callback) => callback(null, null);
        }
        """;

    public static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Trusted provider definitions admit generic Task<bool> delegates without loading provider or author", GenericTaskDelegate);
        yield return ("Trusted metadata supports closed generic methods and instance managed handlers", GenericAndInstanceHandlers);
        yield return ("Trusted provider evidence snapshots bytes and exposes full identity and hash", EvidenceSnapshot);
        yield return ("Trusted evidence rejects nondelegate types, missing names and conflicting provider identities", InvalidEvidence);
        yield return ("Trusted provider cannot be reclassified as author private or impersonated by author", AuthorOwnership);
        yield return ("Trusted delegate signature and generic arguments must match actual provider metadata", MismatchedSignatures);
        yield return ("Trusted delegate rejects mismatched handler signatures and unsafe construction IL", InvalidHandlerAndIl);
        yield return ("Trusted delegate default-deny and exact include exceptions preserve policy diagnostics", PolicyRules);
        yield return ("Trusted delegate constructor, Invoke and signature dependency excludes remain effective", DependencyRules);
        yield return ("Trusted delegate route keeps native, PInvoke and author-defined delegates rejected", UnsafeAuthor);
        yield return ("Trusted delegate metadata does not enable independent type-token options", IndependentOptions);
        yield return ("Retained provider evidence and scalar policy do not root retired provider or author contexts", EvidenceRetirement);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly TempDirectory directory = new();
        public byte[] Provider { get; } = Compile("TrustedCallbackProvider", ProviderSource, [CoreLib]);
        public TrustedDelegateProvider Evidence { get; }
        public string ProviderPath { get; }
        public Fixture()
        {
            ProviderPath = Path.Combine(directory.Path, "TrustedCallbackProvider.dll");
            File.WriteAllBytes(ProviderPath, Provider);
            Evidence = TrustedDelegateProvider.Create(Provider, DelegateName, "Trusted.Callbacks.Plain");
        }
        public byte[] Author(string source = AuthorSource, bool allowUnsafe = false) =>
            Compile("TrustedDelegateAuthor", source, [CoreLib, ProviderPath], allowUnsafe);
        public void Validate(byte[] image, IApiAccessPolicy? policy = null, bool typeTokens = false) =>
            GameplayCapabilityPolicy.ValidateWithTrustedManagedDelegates(image, [], Contract, policy ?? Allow,
                [Evidence], allowReflectionTypeTokens: typeTokens);
        public void Dispose() => directory.Dispose();
    }
    private static byte[] Compile(string name, string source, string[] references, bool allowUnsafe = false)
    {
        var result = SourceCompiler.Compile(name, [new("Entry.cs", source)], references, allowUnsafe);
        Check.Assert(result.Succeeded, string.Join("; ", result.Diagnostics.Select(d => d.Message)));
        return result.Assembly!;
    }
    private static void Reject(Action action, string contains = "")
    {
        var error = Check.Throws<InvalidDataException>(action);
        Check.Assert(error.Message.Contains(contains, StringComparison.OrdinalIgnoreCase), error.Message);
    }
    private static void GenericTaskDelegate()
    {
        using var f = new Fixture();
        var author = f.Author();
        var loaded = new List<string>();
        AssemblyLoadEventHandler onLoad = (_, e) => loaded.Add(e.LoadedAssembly.GetName().Name!);
        AppDomain.CurrentDomain.AssemblyLoad += onLoad;
        try
        {
            // Recreate evidence under the observer too: selected provider runtime delegate methods
            // and unrelated InternalCall are metadata, never author-loaded or subjected to author intake.
            var evidence = TrustedDelegateProvider.Create(f.Provider, DelegateName);
            GameplayCapabilityPolicy.ValidateWithTrustedManagedDelegates(author, [], Contract, Allow, [evidence]);
            Check.Assert(!loaded.Contains("TrustedCallbackProvider") && !loaded.Contains("TrustedDelegateAuthor") &&
                !AppDomain.CurrentDomain.GetAssemblies().Any(a => a.GetName().Name is "TrustedCallbackProvider" or "TrustedDelegateAuthor"),
                "Neither provider evidence nor author validation may load code.");
        }
        finally { AppDomain.CurrentDomain.AssemblyLoad -= onLoad; }
        Reject(() => GameplayCapabilityPolicy.ValidateWithStandardManagedDelegates(author, [], Contract, Allow), "IntPtr");
        Reject(() => GameplayCapabilityPolicy.ValidateWithApiPolicy(author, [], Contract, Allow), "IntPtr");
    }
    private static void GenericAndInstanceHandlers()
    {
        using var f = new Fixture();
        f.Validate(f.Author("""
            using System.Threading.Tasks;
            public class Entry
            {
                public virtual Task<bool> Handle(object sender, string value) => Task.FromResult(true);
                static Task<bool> Generic<T>(object sender, T value) => Task.FromResult(true);
                public Trusted.Callbacks.Callback<string> Instance() => Handle;
                public static Trusted.Callbacks.Callback<int> ClosedGeneric() => Generic<int>;
                private static int Number(int value) => value;
                public static Trusted.Callbacks.Plain NonGeneric() => Number;
                public static System.Action Standard() => () => { };
            }
            """));
    }
    private static void EvidenceSnapshot()
    {
        using var f = new Fixture();
        var before = f.Evidence.ImageSha256;
        Check.Assert(before == Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(f.Provider)).ToLowerInvariant(), "Evidence hash binds bytes.");
        Check.Assert(f.Evidence.AssemblyIdentity == "TrustedCallbackProvider, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null", "Full provider identity.");
        var author = f.Author();
        Array.Fill(f.Provider, (byte)0);
        f.Validate(author);
        Check.Assert(f.Evidence.ImageSha256 == before, "Mutable input bytes must not change the evidence.");
    }
    private static void InvalidEvidence()
    {
        using var f = new Fixture();
        Reject(() => TrustedDelegateProvider.Create(f.Provider, "Trusted.Callbacks.Fake"), "delegate");
        Reject(() => TrustedDelegateProvider.Create(f.Provider, "Missing"), "not found");
        Check.Throws<ArgumentException>(() => TrustedDelegateProvider.Create(f.Provider, DelegateName, DelegateName));
        Check.Throws<ArgumentException>(() => GameplayCapabilityPolicy.ValidateWithTrustedManagedDelegates(f.Author(), [], Contract, Allow, [f.Evidence, f.Evidence]));
        var other = Compile("TrustedCallbackProvider", ProviderSource.Replace("Task<bool>", "Task<int>").Replace("FromResult(true)", "FromResult(1)").Replace("FromResult(false)", "FromResult(2)"), [CoreLib]);
        var conflict = TrustedDelegateProvider.Create(other, DelegateName);
        Check.Throws<ArgumentException>(() => GameplayCapabilityPolicy.ValidateWithTrustedManagedDelegates(f.Author(), [], Contract, Allow, [f.Evidence, conflict]));
        var malformed = PatchCtor(f.Provider, definition: true, (bytes, offset) => bytes[offset + 4] = 0x08);
        Reject(() => TrustedDelegateProvider.Create(malformed, DelegateName), "constructor");
        var unsafeProvider = Compile("UnsafeProvider", "public delegate System.IntPtr Native(object value);", [CoreLib]);
        Reject(() => TrustedDelegateProvider.Create(unsafeProvider, "Native"), "Unsafe");
    }
    private static void AuthorOwnership()
    {
        using var f = new Fixture();
        Reject(() => GameplayCapabilityPolicy.ValidateWithTrustedManagedDelegates(f.Author(), [f.Evidence.AssemblyIdentity], Contract, Allow, [f.Evidence]), "author/private");
        // Even when its simple name and shape are identical, an author-supplied TypeDef receives no grant.
        var fake = Compile("TrustedDelegateAuthor", """
            public delegate System.Threading.Tasks.Task<bool> Local<T>(object sender, T value);
            public static class Entry { static System.Threading.Tasks.Task<bool> H(object s, object v) => null; public static Local<object> Make() => H; }
            """, [CoreLib]);
        Reject(() => f.Validate(fake));
        // Identity mismatch is not resolved by a matching type name.
        var wrong = Compile("DifferentProvider", ProviderSource, [CoreLib]);
        var evidence = TrustedDelegateProvider.Create(wrong, DelegateName);
        Reject(() => GameplayCapabilityPolicy.ValidateWithTrustedManagedDelegates(f.Author(), [], Contract, Allow, [evidence]), "IntPtr");
    }
    private static void MismatchedSignatures()
    {
        using var f = new Fixture();
        var author = f.Author();
        var wrongProvider = Compile("TrustedCallbackProvider", ProviderSource.Replace("Task<bool>", "Task<int>").Replace("FromResult(true)", "FromResult(1)").Replace("FromResult(false)", "FromResult(2)"), [CoreLib]);
        var evidence = TrustedDelegateProvider.Create(wrongProvider, DelegateName);
        Reject(() => GameplayCapabilityPolicy.ValidateWithTrustedManagedDelegates(author, [], Contract, Allow, [evidence]), "signature");
        Reject(() => f.Validate(PatchCtor(author, false, (bytes, offset) => bytes[offset + 4] = 0x08)), "signature");
        Reject(() => f.Validate(f.Author("""
            public static class Entry { public static Trusted.Callbacks.Callback<System.IntPtr> Value; }
            """)), "IntPtr");
    }
    private static void InvalidHandlerAndIl()
    {
        using var f = new Fixture();
        var image = f.Author();
        using var pe = new PEReader(new MemoryStream(image));
        var r = pe.GetMetadataReader();
        var method = r.GetMethodDefinition(r.MethodDefinitions.First(h => r.GetString(r.GetMethodDefinition(h).Name) == "Make"));
        var body = pe.GetMethodBody(method.RelativeVirtualAddress).GetILBytes()!;
        var ctorToken = r.MemberReferences.First(h => r.GetString(r.GetMemberReference(h).Name) == ".ctor" &&
            r.GetMemberReference(h).Parent.Kind == HandleKind.TypeSpecification);
        var tokenBytes = BitConverter.GetBytes(MetadataTokens.GetToken(ctorToken));
        var newobj = Enumerable.Range(0, body.Length - 4).First(i => body[i] == 0x73 && body.AsSpan(i + 1, 4).SequenceEqual(tokenBytes));
        var section = pe.PEHeaders.SectionHeaders.First(s => method.RelativeVirtualAddress >= s.VirtualAddress && method.RelativeVirtualAddress < s.VirtualAddress + s.SizeOfRawData);
        var start = section.PointerToRawData + method.RelativeVirtualAddress - section.VirtualAddress;
        var ilStart = start + ((image[start] & 3) == 2 ? 1 : (image[start + 1] >> 4) * 4);
        var badCall = (byte[])image.Clone();
        badCall[ilStart + newobj] = 0x28;
        Reject(() => f.Validate(badCall), "only newobj");
        var badProducer = (byte[])image.Clone();
        Array.Fill(badProducer, (byte)0, ilStart + newobj - 6, 6);
        Reject(() => f.Validate(badProducer), "ldftn");
        var badHandler = (byte[])image.Clone();
        // Existing Run returns Task<bool> but its parameter is the delegate, unlike Invoke(object,object).
        var run = r.MethodDefinitions.First(h => r.GetString(r.GetMethodDefinition(h).Name) == "Run");
        BinaryPrimitives.WriteInt32LittleEndian(badHandler.AsSpan(ilStart + newobj - 4, 4), MetadataTokens.GetToken(run));
        Reject(() => f.Validate(badHandler), "handler signature");
    }
    private static RuleBasedApiAccessPolicy Policy(ApiPolicyDefault decision, params ApiRule[] rules) => new(decision, rules);
    private static void PolicyRules()
    {
        using var f = new Fixture();
        var allowed = f.Author("""
            public static class Entry { public static Trusted.Callbacks.Callback<object> Make() => Trusted.Callbacks.Host.Handle; }
            """);
        var sibling = f.Author("""
            public static class Entry { public static Trusted.Callbacks.Callback<object> Make() => Trusted.Callbacks.Host.Sibling; }
            """);
        foreach (var decision in new[] { ApiPolicyDefault.Allow, ApiPolicyDefault.Deny })
        {
            ApiRule[] rules = [
                new("bcl", ApiRuleEffect.Include, AssemblyName: "System.Private.CoreLib"),
                new("provider", ApiRuleEffect.Include, AssemblyName: "TrustedCallbackProvider"),
                new("deny-host", ApiRuleEffect.Exclude, TypeName: "Trusted.Callbacks.Host"),
                new("include-handler", ApiRuleEffect.Include, TypeName: "Trusted.Callbacks.Host", MemberName: "Handle",
                    Signature: new("System.Threading.Tasks.Task`1<System.Boolean>", ["System.Object", "System.Object"], 0, false))];
            var policy = Policy(decision, rules);
            f.Validate(allowed, policy);
            Reject(() => f.Validate(sibling, policy), "deny-host");
            Reject(() => f.Validate(allowed, new RuleBasedApiAccessPolicy(decision, rules.Append(rules[^1] with { Id = "equal-deny", Effect = ApiRuleEffect.Exclude }))), "equal-deny");
        }
        Reject(() => f.Validate(allowed, Policy(ApiPolicyDefault.Deny)), "default");
        // A private handler MethodDef must be checked too, not only external MemberRefs.
        Reject(() => f.Validate(f.Author(), Policy(ApiPolicyDefault.Allow,
            new ApiRule("deny-author-handler", ApiRuleEffect.Exclude, TypeName: "Entry", MemberName: "Handle"))), "deny-author-handler");
    }
    private static void DependencyRules()
    {
        using var f = new Fixture();
        foreach (var name in new[] { ".ctor", "Invoke" })
            Reject(() => f.Validate(f.Author(), Policy(ApiPolicyDefault.Allow,
                new ApiRule("deny-member", ApiRuleEffect.Exclude, TypeName: DelegateName, MemberName: name))), "deny-member");
        Reject(() => f.Validate(f.Author(), Policy(ApiPolicyDefault.Allow,
            new ApiRule("deny-task", ApiRuleEffect.Exclude, TypeName: "System.Threading.Tasks.Task`1"))), "deny-task");
        Reject(() => f.Validate(f.Author(), Policy(ApiPolicyDefault.Allow,
            new ApiRule("deny-delegate", ApiRuleEffect.Exclude, TypeName: DelegateName))), "deny-delegate");
    }
    private static void UnsafeAuthor()
    {
        using var f = new Fixture();
        var native = f.Author("""
            public static class Entry { public static System.IntPtr Echo(System.IntPtr p) => p; }
            """);
        Reject(() => f.Validate(native), "IntPtr");
        var pinvoke = f.Author("""
            public static class Entry { [System.Runtime.InteropServices.DllImport("never-load")] public static extern int Native(); }
            """);
        Reject(() => f.Validate(pinvoke), "P/Invoke");
    }
    private static void IndependentOptions()
    {
        using var f = new Fixture();
        var image = f.Author(AuthorSource.Replace("public static class Entry", "public static class Entry").Replace("Make() => Handle;", "Make() => Handle; public static object Token() => typeof(Entry);"));
        Reject(() => f.Validate(image), "ldtoken");
        f.Validate(image, typeTokens: true);
    }

    private static void EvidenceRetirement()
    {
        var (provider, author, providerBytes, authorBytes, evidence, policy) = RetireSyntheticGroup();
        for (var attempt = 0; attempt < 15 && (provider.IsAlive || author.IsAlive || providerBytes.IsAlive || authorBytes.IsAlive); attempt++)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();
        }
        Check.Assert(!provider.IsAlive && !author.IsAlive, "Evidence or policy retained a collectible context after the execution stack returned.");
        Check.Assert(!providerBytes.IsAlive && !authorBytes.IsAlive, "Evidence or validation retained an input image buffer.");
        GC.KeepAlive(evidence);
        GC.KeepAlive(policy);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static (WeakReference Provider, WeakReference Author, WeakReference ProviderBytes, WeakReference AuthorBytes,
        TrustedDelegateProvider Evidence, IApiAccessPolicy Policy) RetireSyntheticGroup()
    {
        using var fixture = new Fixture();
        var image = fixture.Author();
        IApiAccessPolicy policy = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Allow, []);
        fixture.Validate(image, policy);
        var providerContext = new AssemblyLoadContext("delegate-evidence-provider", isCollectible: true);
        var authorContext = new AssemblyLoadContext("delegate-evidence-author", isCollectible: true);
        using var providerStream = new MemoryStream(fixture.Provider, writable: false);
        var providerAssembly = providerContext.LoadFromStream(providerStream);
        authorContext.Resolving += (_, name) => name.Name == "TrustedCallbackProvider" ? providerAssembly : null;
        try
        {
            using var authorStream = new MemoryStream(image, writable: false);
            var authorAssembly = authorContext.LoadFromStream(authorStream);
            var callback = (Delegate)authorAssembly.GetType("Entry")!.GetMethod("Make")!.Invoke(null, null)!;
            var result = (Task<bool>)callback.DynamicInvoke(null, new object())!;
            Check.Assert(result.GetAwaiter().GetResult(), "The synthetic ordinary managed callback must execute before retirement.");
            return (new(providerContext), new(authorContext), new(fixture.Provider), new(image), fixture.Evidence, policy);
        }
        finally
        {
            authorContext.Unload();
            providerContext.Unload();
        }
    }

    private static byte[] PatchCtor(byte[] image, bool definition, Action<byte[], int> edit)
    {
        using var pe = new PEReader(new MemoryStream(image));
        var r = pe.GetMetadataReader();
        BlobHandle blob;
        if (definition)
        {
            var type = r.TypeDefinitions.First(h => r.GetString(r.GetTypeDefinition(h).Name) == "Callback`1");
            blob = r.GetTypeDefinition(type).GetMethods().Select(r.GetMethodDefinition).First(m => r.GetString(m.Name) == ".ctor").Signature;
        }
        else blob = r.MemberReferences.Select(r.GetMemberReference).First(m => r.GetString(m.Name) == ".ctor" && m.Parent.Kind == HandleKind.TypeSpecification).Signature;
        Check.Assert(r.GetBlobBytes(blob).Length == 5, "Canonical short ctor fixture.");
        var offset = pe.PEHeaders.MetadataStartOffset + r.GetHeapMetadataOffset(HeapIndex.Blob) + MetadataTokens.GetHeapOffset(blob) + 1;
        var copy = (byte[])image.Clone();
        edit(copy, offset);
        return copy;
    }
}
