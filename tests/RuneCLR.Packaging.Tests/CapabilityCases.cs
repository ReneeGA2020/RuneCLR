using System.Buffers.Binary;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using RuneCLR.Compiler;
using RuneCLR.Packages;
using RuneCLR.Runtime;

internal static class CapabilityCases
{
    internal static IEnumerable<(string Name, Action Run)> Cases()
    {
        foreach (var (name, body) in new (string, string)[]
        {
            ("Object.GetType", "_ = new object().GetType();"),
            ("Type.GetType", "_ = System.Type.GetType(\"System.Environment\");"),
            ("Activator", "_ = System.Activator.CreateInstance<object>();"),
            ("GC", "System.GC.Collect();"),
            ("Environment", "_ = System.Environment.GetEnvironmentVariable(\"PATH\");"),
            ("reflection", "_ = System.Type.GetType(\"System.Object\")!.GetMethods();"),
            ("Task", "_ = System.Threading.Tasks.Task.Delay(1);"),
            ("delegate invocation", "System.Action action = () => { }; _ = action.DynamicInvoke();")
        })
        {
            var captured = body;
            yield return ($"Capability profile rejects {name} available in fixed references", () => RejectSource(Script(captured)));
        }
        yield return ("Capability profile rejects forbidden calls in unused helpers and constructors", HiddenMethods);
        yield return ("Capability profile rejects forbidden signature-only and generic argument types", ForbiddenSignatures);
        yield return ("Capability profile rejects unsafe pointer IL because SecurityAction is not approved", PointerSignature);
        yield return ("Capability profile rejects a pointer signature without executing it", PointerSignatureBlob);
        yield return ("Capability profile rejects an author ref struct because IsByRefLikeAttribute is not approved", RefStructRejected);
        yield return ("Capability profile rejects unsafe function-pointer IL because SecurityAction is not approved", FunctionPointerSignature);
        yield return ("Capability profile rejects finalizers, module initializers and ThreadStatic state", UnsupportedLifecycle);
        yield return ("Capability profile rejects threading and IO even with explicit wider references", WiderReferences);
        foreach (var (name, opcode) in new (string, byte[])[]
        {
            ("calli", [0x29]), ("jmp", [0x27]), ("localloc", [0xfe, 0x0f]), ("ldtoken", [0xd0])
        })
        {
            var capturedName = name; var capturedOpcode = opcode;
            yield return ($"Capability profile rejects synthetic {name} IL without executing it", () => ForbiddenOpcode(capturedName, capturedOpcode));
        }
        yield return ("Source capability rejection publishes no output and permits a safe recovery package", RejectedPublication);
        yield return ("Raw IL capability rejection publishes no output", RejectedImport);
        yield return ("Capability inspection covers unused private dependency methods", PrivateDependency);
        yield return ("Loader rejects forbidden entry IL after all content hashes are recomputed", RehashedEntry);
        yield return ("Loader rejects forbidden private IL after all content hashes are recomputed", RehashedDependency);
        yield return ("Capability profile cannot downgrade to the previous unrestricted input profile", RehashedProfileDowngrade);
        yield return ("Capability inspection rejects a framework reference with a spoofed public-key token", FrameworkIdentitySpoof);
        yield return ("Capability inspection binds private references by full identity instead of simple name", PrivateIdentityBinding);
        yield return ("Allowed collections, arithmetic and author exceptions retain clean session lifecycle", SafeLifecycle);
        yield return ("An author constructor runs before OnStart and the session still retires", AuthorConstructor);
        yield return ("An author static constructor runs before OnStart and the session still retires", AuthorStaticConstructor);
        yield return ("A throwing author constructor fails before OnStart and the next package still runs", AuthorConstructorFailure);
        yield return ("A throwing author static constructor fails before OnStart and the next package still runs", AuthorStaticConstructorFailure);
        yield return ("Generic, nested, abstract, internal and inherited entry shapes are rejected before run", UnsupportedEntryShapes);
        yield return ("Parameterized constructors and overloaded, explicit, or generic callbacks are rejected before run", UnsupportedCallbackShapes);
        yield return ("A throwing instance field initializer fails before OnStart, and a static field initializer runs only once touched", ThrowingFieldInitializers);
        yield return ("A throwing OnStart keeps the log, releases the entity, and the next package still runs", OnStartFailureRecovery);
        yield return ("An entry that does not implement IMapScript is rejected before run", MissingInterfaceRejected);
        yield return ("A throwing OnTick keeps the earlier log and the next package still runs", OnTickFailureRecovery);
        yield return ("A throwing OnStop is reported on its own and still releases the entity", OnStopFailureRecovery);
        yield return ("Custom delegates and async OnStart are rejected before run", RejectDelegateAndAsync);
        yield return ("An author exception filter runs, handles the failure, and the next package still runs", ExceptionFilterRecovery);
        yield return ("The cooperative API budget stops a second log but not a computation loop", CooperativeBudgetDoesNotStopLoop);
        yield return ("Schedule, resource, and posted-event APIs are rejected before run", RejectHostSchedulingApis);
        yield return ("Remaining schedule, work, and resource accessors are rejected before run", RejectRemainingHostAccessors);
        yield return ("A Signal subscription is rejected because Action is not approved", RejectSignalSubscription);
        yield return ("The approved MapId accessor runs and the next package still runs", ApprovedMapId);
        yield return ("An author Charge call spends the cooperative budget and the next package still runs", AuthorCharge);
    }

    private static string ContractIdentity => ManagedAssemblyInspector.Inspect(Fixtures.ContractAssembly).AssemblyName;
    private static ReferenceProfile Profile() => new(Fixtures.FrameworkReferenceDirectory, Fixtures.ContractAssembly);
    private static byte[] Compile(string source, string name = "CapabilityProbe", IReadOnlyList<string>? extra = null)
    {
        var result = SourceCompiler.Compile(name, [new("Capability.cs", source)],
            CompilerFixture.ApprovedReferences().Concat(extra ?? []).ToArray());
        Check.Assert(result.Succeeded, "Capability fixture did not compile: " + string.Join("; ", result.Diagnostics.Select(item => item.Message)));
        return result.Assembly!;
    }
    private static string Script(string start, string extra = "") => $$"""
        using RuneCLR;
        public sealed class GameScript : IMapScript
        {
            public void OnStart(IMapContext context) { {{start}} }
            public void OnTick(MapTick tick) { }
            public void OnStop() { }
            {{extra}}
        }
        """;
    private static void Validate(byte[] image, IReadOnlyCollection<string>? privateIdentities = null) =>
        GameplayCapabilityPolicy.Validate(image, privateIdentities ?? [], ContractIdentity);
    private static void RejectSource(string source, IReadOnlyList<string>? extra = null)
    {
        var error = Check.Throws<InvalidDataException>(() => Validate(Compile(source, extra: extra)));
        Check.Assert(error.Message.Contains(GameplayCapabilityPolicy.Profile, StringComparison.Ordinal),
            "Capability rejection did not identify the input profile.");
    }
    private static PackageBuildResult Build(string output, string source = SafeScript, IReadOnlyList<string>? dependencies = null) =>
        PackageBuilder.Compile("CapabilityGame", "GameScript", [new("Capability.cs", source)], Profile(), output, dependencies);

    private static void HiddenMethods()
    {
        RejectSource(Script("", "private static void Unused() { System.Environment.Exit(7); }"));
        RejectSource(Script("", "public GameScript() { System.GC.Collect(); }"));
        RejectSource(Script("", "private static int Value = Read(); private static int Read() => System.Environment.TickCount;"));
    }
    private static void PointerSignature() =>
        RejectUnsafe("public static class Probe { public static unsafe int* Read(int* value) => value; }",
            "System.Security.Permissions.SecurityAction");

    private static void FunctionPointerSignature() =>
        RejectUnsafe("public static class Probe { public static unsafe int Call(delegate*<int, int> value, int input) => value(input); }",
            "System.Security.Permissions.SecurityAction");

    private static void RefStructRejected()
{
        var image = Compile("public ref struct Marker { public int Value; }");
        var error = Check.Throws<InvalidDataException>(() => Validate(image));
        Check.Assert(error.Message.Contains("System.Runtime.CompilerServices.IsByRefLikeAttribute", StringComparison.Ordinal) && error.Message.Contains("is not approved", StringComparison.Ordinal), error.Message);
}

    private static void PointerSignatureBlob()
    {
        var image = Compile("public static class Probe { public static ref int Marker(ref int value) => ref value; }");
        var pattern = new byte[] { 0x06, 0x00, 0x01, 0x10, 0x08, 0x10, 0x08 };
        var found = 0;
        for (var i = 0; i <= image.Length - pattern.Length; i++)
        {
            var match = true;
            for (var j = 0; j < pattern.Length; j++)
                if (image[i + j] != pattern[j]) { match = false; break; }
            if (!match) continue;
            found++;
            image[i + 3] = 0x0F;
            image[i + 5] = 0x0F;
        }
        Check.Assert(found == 1, "Expected one ref int signature, found " + found + ".");
        var error = Check.Throws<InvalidDataException>(() => Validate(image));
        Check.Assert(error.Message.Contains("Pointer signatures are unsupported.", StringComparison.Ordinal), error.Message);
    }

    private static void RejectUnsafe(string source, string expected)
    {
        var result = SourceCompiler.Compile("PointerProbe", [new SourceFile("pointer.cs", source)],
            CompilerFixture.ApprovedReferences().ToArray(), allowUnsafe: true);
        Check.Assert(result.Succeeded && result.Assembly is not null,
            "Unsafe fixture did not compile: " + string.Join("; ", result.Diagnostics.Select(item => item.Message)));
        var error = Check.Throws<InvalidDataException>(() => Validate(result.Assembly!));
        Check.Assert(error.Message.Contains(expected, StringComparison.Ordinal), error.Message);
    }

    private static void ForbiddenSignatures()
    {
        RejectSource(Script("", "public System.Type? Value;"));
        RejectSource(Script("", "public System.Collections.Generic.List<System.Type>? Values;"));
        RejectSource(Script("", "public static System.Type? Unused(System.Type value) => value;"));
        RejectSource(Script("", "public static void Generic<T>(T value) { _ = value!.GetType(); }"));
    }
    private static void UnsupportedLifecycle()
    {
        RejectSource(Script("", "~GameScript() { }"));
        RejectSource(Script("") + " public static class Init { [System.Runtime.CompilerServices.ModuleInitializer] public static void Run() { } }");
        RejectSource(Script("", "[System.ThreadStatic] private static int value;"));
    }
    private static void WiderReferences()
    {
        var directory = Path.Combine(AppContext.BaseDirectory, "denied-refs");
        RejectSource(Script("System.Threading.Thread.Sleep(1);"), [Path.Combine(directory, "System.Threading.Thread.dll")]);
        RejectSource(Script("_ = System.IO.File.ReadAllText(\"never-opened\");"), [Path.Combine(directory, "System.IO.FileSystem.dll")]);
    }
    private static void ForbiddenOpcode(string name, byte[] opcode)
    {
        var image = Compile("public static class Probe { public static int ProbeMethod() => 123456; }");
        using var pe = new PEReader(new MemoryStream(image));
        var metadata = pe.GetMetadataReader();
        var handle = metadata.MethodDefinitions.First(handle => metadata.GetString(metadata.GetMethodDefinition(handle).Name) == "ProbeMethod");
        var method = metadata.GetMethodDefinition(handle);
        var section = pe.PEHeaders.SectionHeaders.First(section => method.RelativeVirtualAddress >= section.VirtualAddress
            && method.RelativeVirtualAddress < section.VirtualAddress + section.SizeOfRawData);
        var offset = section.PointerToRawData + method.RelativeVirtualAddress - section.VirtualAddress;
        var headerLength = (image[offset] & 3) == 2 ? 1 : (BinaryPrimitives.ReadUInt16LittleEndian(image.AsSpan(offset, 2)) >> 12) * 4;
        var il = image.AsSpan(offset + headerLength, pe.GetMethodBody(method.RelativeVirtualAddress).GetILBytes()!.Length);
        // Synthetic opcode mutations are inspected only, never loaded or executed.
        il.Clear(); opcode.CopyTo(il);
        if (opcode.Length == 1) BinaryPrimitives.WriteInt32LittleEndian(il[1..], MetadataTokens.GetToken(handle));
        il[^1] = 0x2a;
        var error = Check.Throws<InvalidDataException>(() => Validate(image));
        Check.Assert(error.Message.Contains(name, StringComparison.OrdinalIgnoreCase), "The opcode rejection did not identify " + name + ".");
        Check.Assert(error.Message.Contains("IL offset ", StringComparison.Ordinal), "The opcode rejection did not include an IL offset.");
    }
    private static void RejectedPublication()
    {
        using var temp = new TempDirectory(); var output = Path.Combine(temp.Path, "rejected");
        Check.Throws<InvalidDataException>(() => Build(output, Script("System.GC.Collect();")));
        Check.Assert(!Directory.Exists(output) && !Directory.EnumerateDirectories(temp.Path, ".runeclr-build-*").Any(),
            "Capability rejection left published output or staging files.");
        var safe = Build(output); Check.Assert(safe.Succeeded, "Recovery build failed."); RunSafe(safe.ManifestPath!);
    }
    private static void RejectedImport()
    {
        using var temp = new TempDirectory(); var input = Path.Combine(temp.Path, "input.dll");
        File.WriteAllBytes(input, Compile(Script("_ = new object().GetType();")));
        var output = Path.Combine(temp.Path, "rejected");
        Check.Throws<InvalidDataException>(() => PackageBuilder.Import("Imported", "GameScript", input, Profile(), output));
        Check.Assert(!Directory.Exists(output), "Forbidden imported IL was published.");
    }
    private static string WriteDependency(TempDirectory temp, string source)
    {
        var input = Path.Combine(temp.Path, "PrivateCapability.dll");
        File.WriteAllBytes(input, Compile(source, "PrivateCapability")); return input;
    }
    private static void PrivateDependency()
    {
        using var temp = new TempDirectory();
        var dependency = WriteDependency(temp, "public static class Helper { public static int Value() => 7; private static void Hidden() { System.GC.Collect(); } }");
        var output = Path.Combine(temp.Path, "rejected");
        Check.Throws<InvalidDataException>(() => Build(output, dependencies: [dependency]));
        Check.Assert(!Directory.Exists(output), "Unused forbidden private dependency was published.");
    }
    private static void RehashedEntry()
    {
        using var temp = new TempDirectory(); var built = Build(Path.Combine(temp.Path, "package"));
        Check.Assert(built.Succeeded, "Safe package build failed.");
        var saved = MapPackage.FromManifest(built.ManifestPath!);
        var manifest = PackageManifestIO.Read(built.ManifestPath!);
        ReplaceAndReseal(built.ManifestPath!, manifest.EntryAssembly, Compile(Script("System.GC.Collect();"), "CapabilityGame"));
        var error = Check.Throws<InvalidDataException>(() => MapPackage.FromManifest(built.ManifestPath!));
        Check.Assert(error.Message.Contains(GameplayCapabilityPolicy.Profile, StringComparison.Ordinal), "Loader missed entry assembly capability inspection.");
        Check.Throws<InvalidDataException>(() => new MapRunner().Run(saved));
        var recovery = Build(Path.Combine(temp.Path, "recovery"));
        Check.Assert(recovery.Succeeded, "Safe recovery package build failed."); RunSafe(recovery.ManifestPath!);
    }
    private static void RehashedDependency()
    {
        using var temp = new TempDirectory();
        var dependency = WriteDependency(temp, "public static class Helper { public static int Value() => 7; }");
        var built = Build(Path.Combine(temp.Path, "package"), dependencies: [dependency]);
        Check.Assert(built.Succeeded, "Safe private package build failed.");
        var manifest = PackageManifestIO.Read(built.ManifestPath!);
        ReplaceAndReseal(built.ManifestPath!, manifest.Dependencies[0].Path,
            Compile("public static class Helper { public static int Value() => 7; private static void Hidden() { System.GC.Collect(); } }", "PrivateCapability"));
        var error = Check.Throws<InvalidDataException>(() => MapPackage.FromManifest(built.ManifestPath!));
        Check.Assert(error.Message.Contains(GameplayCapabilityPolicy.Profile, StringComparison.Ordinal), "Loader missed private assembly capability inspection.");
    }
    private static void RehashedProfileDowngrade()
    {
        using var temp = new TempDirectory(); var built = Build(Path.Combine(temp.Path, "package"));
        Check.Assert(built.Succeeded, "Safe package build failed.");
        var manifest = PackageManifestIO.Read(built.ManifestPath!) with { InputProfile = "managed-il-v1" };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(built.ManifestPath!, manifest);
        var error = Check.Throws<InvalidDataException>(() => MapPackage.FromManifest(built.ManifestPath!));
        Check.Assert(error.Message.Contains("profile", StringComparison.OrdinalIgnoreCase), "Legacy profile rejection did not identify the unsupported profile.");
    }
    private static void FrameworkIdentitySpoof()
    {
        var image = Compile(Script("")); Validate(image);
        using var pe = new PEReader(new MemoryStream(image)); var metadata = pe.GetMetadataReader();
        var reference = metadata.GetAssemblyReference(metadata.AssemblyReferences.First(handle =>
            metadata.GetString(metadata.GetAssemblyReference(handle).Name) == "System.Runtime"));
        var offset = pe.PEHeaders.MetadataStartOffset + metadata.GetHeapMetadataOffset(HeapIndex.Blob)
            + MetadataTokens.GetHeapOffset(reference.PublicKeyOrToken);
        Check.Assert(image[offset] == 8, "Framework fixture does not contain the expected eight-byte token blob.");
        // Change identity metadata only; the framework's legitimate simple name remains intact.
        image[offset + 1] ^= 1;
        var error = Check.Throws<InvalidDataException>(() => Validate(image));
        Check.Assert(error.Message.Contains("System.Runtime", StringComparison.Ordinal)
            && error.Message.Contains(GameplayCapabilityPolicy.Profile, StringComparison.Ordinal),
            "Spoofed framework identity did not fail capability validation.");
    }
    private static void PrivateIdentityBinding()
    {
        using var temp = new TempDirectory();
        var dependency = WriteDependency(temp, "public static class Helper { public static int Value() => 7; }");
        var image = Compile(Script("context.Log(Helper.Value().ToString());"), extra: [dependency]);
        var identity = ManagedAssemblyInspector.Inspect(dependency).AssemblyName;
        Validate(image, [identity]);
        var wrongIdentity = new AssemblyName(identity) { Version = new Version(77, 0, 0, 0) }.FullName!;
        var error = Check.Throws<InvalidDataException>(() => Validate(image, [wrongIdentity]));
        Check.Assert(error.Message.Contains("PrivateCapability", StringComparison.Ordinal)
            && error.Message.Contains(GameplayCapabilityPolicy.Profile, StringComparison.Ordinal),
            "Private reference incorrectly matched an admitted assembly with the same simple name.");
    }
    private static void ReplaceAndReseal(string manifestPath, string relativePath, byte[] replacement)
    {
        var manifest = PackageManifestIO.Read(manifestPath); var hash = Fixtures.Hash(replacement);
        File.WriteAllBytes(Path.Combine(Path.GetDirectoryName(manifestPath)!, relativePath), replacement);
        manifest = manifest with
        {
            EntrySha256 = manifest.EntryAssembly == relativePath ? hash : manifest.EntrySha256,
            Files = manifest.Files.Select(file => file.Path == relativePath ? file with { Sha256 = hash } : file).ToArray(),
            Dependencies = manifest.Dependencies.Select(dependency => dependency.Path == relativePath ? dependency with { Sha256 = hash } : dependency).ToArray()
        };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(manifestPath, manifest);
    }
    private const string SafeScript = """
        using RuneCLR;
        using System;
        using System.Collections.Generic;
        public sealed class GameScript : IMapScript
        {
            private static int starts;
            private IMapContext? context;
            public void OnStart(IMapContext value)
            {
                context = value;
                var values = new List<int> { -3, 4 };
                var counts = new Dictionary<string, int>();
                int sum = 0;
                foreach (var item in values) sum += Math.Abs(item);
                counts["sum"] = Identity(Math.Max(sum, 1));
                context.Log("starts=" + (++starts) + ";sum=" + counts["sum"]);
                context.SpawnEntity("safe");
                try { throw new AuthorException("handled"); }
                catch (AuthorException error) { context.Log(error.Message); }
            }
            public void OnTick(MapTick tick) { }
            public void OnStop() { context!.Log("stopped"); }
            private static T Identity<T>(T value) => value;
        }
        public sealed class AuthorException : Exception { public AuthorException(string message) : base(message) { } }
        """;
    private static void AuthorStaticConstructorFailure()
{
        const string source = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                static GameScript() { throw new AuthorStaticCtorException(); }
                public void OnStart(IMapContext context) { context.Log("started"); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            public sealed class AuthorStaticCtorException : System.Exception { }
            """;
        using var temp = new TempDirectory();
        var built = Build(Path.Combine(temp.Path, "faulty"), source);
        Check.Assert(built.Succeeded, "Throwing static constructor failed compilation.");
        var result = new MapRunner().Run(MapPackage.FromManifest(built.ManifestPath!), new MapRunOptions { TickCount = 1 });
        Check.Assert(result.Report.Outcome == MapRunOutcome.Failed
            && result.Report.Error?.Contains("AuthorStaticCtorException", StringComparison.Ordinal) == true
            && result.Report.Logs.Count == 0
            && result.Report.CreatedEntities == 0 && result.Report.RemainingEntities == 0,
            result.Report.ToString());
        Check.Collected(result);
        var next = Build(Path.Combine(temp.Path, "next"));
        Check.Assert(next.Succeeded, "Next package failed to compile.");
        RunSafe(next.ManifestPath!);
}

    private static void AuthorConstructorFailure()
{
        const string source = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public GameScript() { throw new AuthorCtorException(); }
                public void OnStart(IMapContext context) { context.Log("started"); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { contextUnused(); }
                private static void contextUnused() { }
            }
            public sealed class AuthorCtorException : System.Exception { }
            """;
        using var temp = new TempDirectory();
        var built = Build(Path.Combine(temp.Path, "faulty"), source);
        Check.Assert(built.Succeeded, "Throwing constructor failed compilation.");
        var result = new MapRunner().Run(MapPackage.FromManifest(built.ManifestPath!), new MapRunOptions { TickCount = 1 });
        Check.Assert(result.Report.Outcome == MapRunOutcome.Failed
            && result.Report.Error?.Contains("AuthorCtorException", StringComparison.Ordinal) == true
            && result.Report.Logs.Count == 0
            && result.Report.CreatedEntities == 0 && result.Report.RemainingEntities == 0,
            result.Report.ToString());
        Check.Collected(result);
        var next = Build(Path.Combine(temp.Path, "next"));
        Check.Assert(next.Succeeded, "Next package failed to compile.");
        RunSafe(next.ManifestPath!);
}

    private static void AuthorStaticConstructor()
{
        const string source = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                private static int value;
                static GameScript() { value = 41; }
                public void OnStart(IMapContext context) { context.Log("value=" + value); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        using var temp = new TempDirectory();
        var built = Build(Path.Combine(temp.Path, "package"), source);
        Check.Assert(built.Succeeded, "Author static constructor failed compilation.");
        var result = new MapRunner().Run(MapPackage.FromManifest(built.ManifestPath!), new MapRunOptions { TickCount = 1 });
        Check.Assert(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Static constructor script did not finish.");
        Check.Assert(result.Report.Logs.SequenceEqual(new[] { "value=41" }), "Static constructor value was not observed.");
        Check.Collected(result);
}

    private static void AuthorConstructor()
{
        const string source = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                private readonly int value;
                public GameScript() { value = 41; }
                public void OnStart(IMapContext context) { context.Log("value=" + value); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        using var temp = new TempDirectory();
        var built = Build(Path.Combine(temp.Path, "package"), source);
        Check.Assert(built.Succeeded, "Author constructor failed compilation.");
        var result = new MapRunner().Run(MapPackage.FromManifest(built.ManifestPath!), new MapRunOptions { TickCount = 1 });
        Check.Assert(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Constructor script did not finish.");
        Check.Assert(result.Report.Logs.SequenceEqual(new[] { "value=41" }), "Constructor value was not observed.");
        Check.Collected(result);
}

    private static void SafeLifecycle()
    {
        using var temp = new TempDirectory(); var built = Build(Path.Combine(temp.Path, "package"));
        Check.Assert(built.Succeeded, "Allowed gameplay fixture failed compilation.");
        for (var cycle = 0; cycle < 3; cycle++) RunSafe(built.ManifestPath!);
    }
    private static void UnsupportedEntryShapes()
    {
        using var temp = new TempDirectory();
        void Reject(string directory, string source, string expected)
        {
            var error = Check.Throws<InvalidDataException>(() =>
            {
                var built = Build(Path.Combine(temp.Path, directory), source);
                var details = built.Diagnostics.Length == 0
                    ? "Build returned without an exception. Succeeded=" + built.Succeeded
                    : string.Join(" | ", built.Diagnostics.Select(item => item.Code + ": " + item.Message));
                throw new InvalidOperationException(details);
            });
            Check.Assert(error.Message.Contains(expected, StringComparison.Ordinal), error.Message);
        }

        Reject("generic", """
            using RuneCLR;
            public sealed class GameScript<T> : IMapScript
            {
                public void OnStart(IMapContext context) { }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """, "Entry type 'GameScript' was not found; nested entries are unsupported.");
        Reject("nested", """
            using RuneCLR;
            public sealed class Holder
            {
                public sealed class GameScript : IMapScript
                {
                    public void OnStart(IMapContext context) { }
                    public void OnTick(MapTick tick) { }
                    public void OnStop() { }
                }
            }
            """, "Entry 'GameScript' must be a public, nonabstract, nongeneric, nonnested class.");
        Reject("abstract", """
            using RuneCLR;
            public abstract class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """, "Entry 'GameScript' must be a public, nonabstract, nongeneric, nonnested class.");
        Reject("internal", """
            using RuneCLR;
            sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """, "Entry 'GameScript' must be a public, nonabstract, nongeneric, nonnested class.");
        Reject("inherited", """
            using RuneCLR;
            public class BaseScript : IMapScript
            {
                public void OnStart(IMapContext context) { }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            public sealed class GameScript : BaseScript { }
            """, "Entry 'GameScript' must directly extend System.Object; inherited entry implementations are unsupported.");
        var next = Build(Path.Combine(temp.Path, "next"));
        Check.Assert(next.Succeeded, "Next package failed to compile.");
        RunSafe(next.ManifestPath!);
    }

    private static void UnsupportedCallbackShapes()
    {
        using var temp = new TempDirectory();
        void Reject(string directory, string source, string expected)
        {
            var error = Check.Throws<InvalidDataException>(() =>
            {
                var built = Build(Path.Combine(temp.Path, directory), source);
                var details = built.Diagnostics.Length == 0
                    ? "Build returned without an exception. Succeeded=" + built.Succeeded
                    : string.Join(" | ", built.Diagnostics.Select(item => item.Code + ": " + item.Message));
                throw new InvalidOperationException(details);
            });
            Check.Assert(error.Message.Contains(expected, StringComparison.Ordinal), error.Message);
        }

        Reject("ctor", """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public GameScript(int value) { }
                public void OnStart(IMapContext context) { }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """, "Entry 'GameScript' needs exactly one public instance parameterless constructor.");
        Reject("overload", """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { }
                public void OnStart(int value) { }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """, "Entry callback 'OnStart' must be one public nongeneric instance method; explicit/inherited/overloaded callbacks are unsupported.");
        Reject("explicit", """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { }
                void IMapScript.OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """, "Entry callback 'OnTick' must be one public nongeneric instance method; explicit/inherited/overloaded callbacks are unsupported.");
        Reject("generic", """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
                public void OnStop<T>() { }
            }
            """, "Entry callback 'OnStop' must be one public nongeneric instance method; explicit/inherited/overloaded callbacks are unsupported.");
        var next = Build(Path.Combine(temp.Path, "next"));
        Check.Assert(next.Succeeded, "Next package failed to compile.");
        RunSafe(next.ManifestPath!);
    }

    private static void ThrowingFieldInitializers()
    {
        {
            const string source = """
                using RuneCLR;
                public sealed class GameScript : IMapScript
                {
                    private readonly int value = Fail();
                    private static int Fail() => throw new AuthorFieldException();
                    public void OnStart(IMapContext context) { context.Log("started"); }
                    public void OnTick(MapTick tick) { }
                    public void OnStop() { }
                }
                public sealed class AuthorFieldException : System.Exception { }
                """;
            using var temp = new TempDirectory();
            var built = Build(Path.Combine(temp.Path, "faulty"), source);
            Check.Assert(built.Succeeded, string.Join(" | ", built.Diagnostics.Select(item => item.Code + ": " + item.Message)));
            var result = new MapRunner().Run(MapPackage.FromManifest(built.ManifestPath!), new MapRunOptions { TickCount = 1 });
            Check.Assert(result.Report.Outcome == MapRunOutcome.Failed
                && result.Report.Error?.Contains("AuthorFieldException", StringComparison.Ordinal) == true
                && result.Report.Logs.Count == 0
                && result.Report.CreatedEntities == 0 && result.Report.RemainingEntities == 0,
                result.Report.Error ?? result.Report.ToString());
            Check.Collected(result);
            var next = Build(Path.Combine(temp.Path, "next"));
            Check.Assert(next.Succeeded, "Next package failed to compile.");
            RunSafe(next.ManifestPath!);
        }
        {
            const string source = """
                using RuneCLR;
                public sealed class GameScript : IMapScript
                {
                    private static readonly int value = Fail();
                    private readonly int copy = value;
                    private static int Fail() => throw new AuthorStaticFieldException();
                    public void OnStart(IMapContext context) { context.Log("started"); }
                    public void OnTick(MapTick tick) { }
                    public void OnStop() { }
                }
                public sealed class AuthorStaticFieldException : System.Exception { }
                """;
            using var temp = new TempDirectory();
            var built = Build(Path.Combine(temp.Path, "faulty"), source);
            Check.Assert(built.Succeeded, string.Join(" | ", built.Diagnostics.Select(item => item.Code + ": " + item.Message)));
            var result = new MapRunner().Run(MapPackage.FromManifest(built.ManifestPath!), new MapRunOptions { TickCount = 1 });
            Check.Assert(result.Report.Outcome == MapRunOutcome.Failed
                && result.Report.Error?.Contains("TypeInitializationException", StringComparison.Ordinal) == true
                && result.Report.Error.Contains("AuthorStaticFieldException", StringComparison.Ordinal)
                && result.Report.Logs.Count == 0
                && result.Report.CreatedEntities == 0 && result.Report.RemainingEntities == 0,
                result.Report.Error ?? result.Report.ToString());
            Check.Collected(result);
            var next = Build(Path.Combine(temp.Path, "next"));
            Check.Assert(next.Succeeded, "Next package failed to compile.");
            RunSafe(next.ManifestPath!);
        }
        {
            const string source = """
                using RuneCLR;
                public sealed class GameScript : IMapScript
                {
                    private static readonly int value = Fail();
                    private static int Fail() => throw new AuthorStaticFieldException();
                    public void OnStart(IMapContext context) { context.Log("started"); }
                    public void OnTick(MapTick tick) { }
                    public void OnStop() { }
                }
                public sealed class AuthorStaticFieldException : System.Exception { }
                """;
            using var temp = new TempDirectory();
            var built = Build(Path.Combine(temp.Path, "unread"), source);
            Check.Assert(built.Succeeded, string.Join(" | ", built.Diagnostics.Select(item => item.Code + ": " + item.Message)));
            var result = new MapRunner().Run(MapPackage.FromManifest(built.ManifestPath!), new MapRunOptions { TickCount = 1 });
            Check.Assert(result.Report.Outcome == MapRunOutcome.Completed
                && result.Report.Logs.SequenceEqual(new[] { "started" })
                && result.Report.CompletedTicks == 1,
                result.Report.Error ?? result.Report.ToString());
            Check.Collected(result);
        }
    }
    private static void OnStartFailureRecovery()
    {
        const string source = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                private IMapContext? context;
                public void OnStart(IMapContext value)
                {
                    context = value;
                    value.Log("before");
                    value.SpawnEntity("before-start-error");
                    throw new AuthorStartException();
                }
                public void OnTick(MapTick tick) { }
                public void OnStop() { context!.Log("stopped"); }
            }
            public sealed class AuthorStartException : System.Exception { }
            """;
        using var temp = new TempDirectory();
        var built = Build(Path.Combine(temp.Path, "faulty"), source);
        Check.Assert(built.Succeeded, string.Join(" | ", built.Diagnostics.Select(item => item.Code + ": " + item.Message)));
        var result = new MapRunner().Run(MapPackage.FromManifest(built.ManifestPath!), new MapRunOptions { TickCount = 1 });
        Check.Assert(result.Report.Outcome == MapRunOutcome.Failed
            && result.Report.Error?.Contains("AuthorStartException", StringComparison.Ordinal) == true
            && result.Report.CompletedTicks == 0
            && result.Report.Logs.SequenceEqual(new[] { "before", "stopped" })
            && result.Report.CreatedEntities == 1 && result.Report.ReleasedEntities == 1 && result.Report.RemainingEntities == 0,
            result.Report + " logs=[" + string.Join(",", result.Report.Logs) + "]");
        Check.Collected(result);
        var next = Build(Path.Combine(temp.Path, "next"));
        Check.Assert(next.Succeeded, "Next package failed to compile.");
        RunSafe(next.ManifestPath!);
    }

    private static void MissingInterfaceRejected()
    {
        const string source = """
            using RuneCLR;
            public sealed class GameScript
            {
                public void OnStart(IMapContext context) { }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        using var temp = new TempDirectory();
        var error = Check.Throws<InvalidDataException>(() =>
        {
            var built = Build(Path.Combine(temp.Path, "missing"), source);
            var details = built.Diagnostics.Length == 0
                ? "Build returned without an exception. Succeeded=" + built.Succeeded
                : string.Join(" | ", built.Diagnostics.Select(item => item.Code + ": " + item.Message));
            throw new InvalidOperationException(details);
        });
        Check.Assert(error.Message.Contains("Entry 'GameScript' must directly implement RuneCLR.IMapScript from '", StringComparison.Ordinal), error.Message);
        var next = Build(Path.Combine(temp.Path, "next"));
        Check.Assert(next.Succeeded, "Next package failed to compile.");
        RunSafe(next.ManifestPath!);
    }
    private static void OnTickFailureRecovery()
    {
        const string source = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                private IMapContext? context;
                public void OnStart(IMapContext value)
                {
                    context = value;
                    value.Log("started");
                    value.SpawnEntity("alive");
                }
                public void OnTick(MapTick tick)
                {
                    if (tick.Index == 1) throw new AuthorTickException();
                    context!.Log("tick=" + tick.Index);
                }
                public void OnStop() { context!.Log("stopped"); }
            }
            public sealed class AuthorTickException : System.Exception { }
            """;
        using var temp = new TempDirectory();
        var built = Build(Path.Combine(temp.Path, "faulty"), source);
        Check.Assert(built.Succeeded, string.Join(" | ", built.Diagnostics.Select(item => item.Code + ": " + item.Message)));
        var result = new MapRunner().Run(MapPackage.FromManifest(built.ManifestPath!), new MapRunOptions { TickCount = 2 });
        Check.Assert(result.Report.Outcome == MapRunOutcome.Failed
            && result.Report.Error?.Contains("AuthorTickException", StringComparison.Ordinal) == true
            && result.Report.CompletedTicks == 1
            && result.Report.Logs.SequenceEqual(new[] { "started", "tick=0", "stopped" })
            && result.Report.CreatedEntities == 1 && result.Report.ReleasedEntities == 1 && result.Report.RemainingEntities == 0,
            (result.Report.Error ?? "") + " logs=[" + string.Join(",", result.Report.Logs) + "] created=" + result.Report.CreatedEntities + " released=" + result.Report.ReleasedEntities + " remaining=" + result.Report.RemainingEntities);
        Check.Collected(result);
        var next = Build(Path.Combine(temp.Path, "next"));
        Check.Assert(next.Succeeded, "Next package failed to compile.");
        RunSafe(next.ManifestPath!);
    }

    private static void OnStopFailureRecovery()
    {
        const string source = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                private IMapContext? context;
                public void OnStart(IMapContext value)
                {
                    context = value;
                    value.Log("started");
                    value.SpawnEntity("alive");
                }
                public void OnTick(MapTick tick) { }
                public void OnStop() { throw new AuthorStopException(); }
            }
            public sealed class AuthorStopException : System.Exception { }
            """;
        using var temp = new TempDirectory();
        var built = Build(Path.Combine(temp.Path, "faulty"), source);
        Check.Assert(built.Succeeded, string.Join(" | ", built.Diagnostics.Select(item => item.Code + ": " + item.Message)));
        var result = new MapRunner().Run(MapPackage.FromManifest(built.ManifestPath!), new MapRunOptions { TickCount = 1 });
        Check.Assert(result.Report.Outcome == MapRunOutcome.Failed
            && result.Report.Error?.StartsWith("OnStop:", StringComparison.Ordinal) == true
            && result.Report.Error.Contains("AuthorStopException", StringComparison.Ordinal)
            && result.Report.CompletedTicks == 1
            && result.Report.Logs.SequenceEqual(new[] { "started" })
            && result.Report.CreatedEntities == 1 && result.Report.ReleasedEntities == 1 && result.Report.RemainingEntities == 0,
            (result.Report.Error ?? "") + " logs=[" + string.Join(",", result.Report.Logs) + "] created=" + result.Report.CreatedEntities + " released=" + result.Report.ReleasedEntities + " remaining=" + result.Report.RemainingEntities);
        Check.Collected(result);
        var next = Build(Path.Combine(temp.Path, "next"));
        Check.Assert(next.Succeeded, "Next package failed to compile.");
        RunSafe(next.ManifestPath!);
    }
    private static void RejectDelegateAndAsync()
    {
        const string delegates = """
            using RuneCLR;
            public delegate void AuthorCallback(int value);
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var delegateError = Check.Throws<InvalidDataException>(() => Validate(Compile(delegates)));
        Check.Assert(delegateError.Message.Contains("Capability profile 'managed-il-gameplay-v1':", StringComparison.Ordinal)
            && delegateError.Message.Contains("Type 'System.MulticastDelegate' is not approved.", StringComparison.Ordinal),
            delegateError.Message);
        const string asyncSource = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public async void OnStart(IMapContext context) { await System.Threading.Tasks.Task.Yield(); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var asyncError = Check.Throws<InvalidDataException>(() => Validate(Compile(asyncSource)));
        Check.Assert(asyncError.Message.Contains("Type 'System.Type' is not approved.", StringComparison.Ordinal), asyncError.Message);
        using var temp = new TempDirectory();
        var next = Build(Path.Combine(temp.Path, "next"));
        Check.Assert(next.Succeeded, "Next package failed to compile.");
        RunSafe(next.ManifestPath!);
    }
    private static void ExceptionFilterRecovery()
    {
        const string source = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                private static int misses;
                private static int hits;
                public void OnStart(IMapContext context)
                {
                    try { throw new AuthorFilterException("no"); }
                    catch (AuthorFilterException) when (Miss()) { context.Log("wrong"); }
                    catch (AuthorFilterException) when (Hit()) { context.Log("misses=" + misses + ";hits=" + hits); }
                }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
                private static bool Miss() { misses++; return false; }
                private static bool Hit() { hits++; return true; }
            }
            public sealed class AuthorFilterException : System.Exception
            {
                public AuthorFilterException(string message) : base(message) { }
            }
            """;
        using var temp = new TempDirectory();
        var built = Build(Path.Combine(temp.Path, "faulty"), source);
        Check.Assert(built.Succeeded, string.Join(" | ", built.Diagnostics.Select(item => item.Code + ": " + item.Message)));
        var result = new MapRunner().Run(MapPackage.FromManifest(built.ManifestPath!), new MapRunOptions { TickCount = 1 });
        Check.Assert(result.Report.Outcome == MapRunOutcome.Completed
            && result.Report.Logs.SequenceEqual(new[] { "misses=1;hits=1" })
            && result.Report.CompletedTicks == 1,
            (result.Report.Error ?? "") + " " + result.Report + " logs=[" + string.Join(",", result.Report.Logs) + "]");
        Check.Collected(result);
        var next = Build(Path.Combine(temp.Path, "next"));
        Check.Assert(next.Succeeded, "Next package failed to compile.");
        RunSafe(next.ManifestPath!);
    }
    private static void CooperativeBudgetDoesNotStopLoop()
    {
        using var temp = new TempDirectory();
        const string loop = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                private IMapContext? context;
                public void OnStart(IMapContext value) { context = value; }
                public void OnTick(MapTick tick)
                {
                    long sum = 0;
                    for (var i = 0; i < 1000; i++) sum += i;
                    context!.Log("sum=" + sum);
                }
                public void OnStop() { }
            }
            """;
        var loopBuilt = Build(Path.Combine(temp.Path, "loop"), loop);
        Check.Assert(loopBuilt.Succeeded, string.Join(" | ", loopBuilt.Diagnostics.Select(item => item.Code + ": " + item.Message)));
        var budget = new MapRunOptions { TickCount = 1, OperationBudgetPerCallback = 1 };
        var loopResult = new MapRunner().Run(MapPackage.FromManifest(loopBuilt.ManifestPath!), budget);
        Check.Assert(loopResult.Report.Outcome == MapRunOutcome.Completed
            && loopResult.Report.Logs.SequenceEqual(new[] { "sum=499500" })
            && loopResult.Report.CompletedTicks == 1,
            (loopResult.Report.Error ?? "") + " logs=[" + string.Join(",", loopResult.Report.Logs) + "] " + loopResult.Report);
        Check.Collected(loopResult);
        var loopNext = Build(Path.Combine(temp.Path, "loop-next"));
        Check.Assert(loopNext.Succeeded, "Next package failed to compile.");
        RunSafe(loopNext.ManifestPath!);

        const string logs = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                private IMapContext? context;
                public void OnStart(IMapContext value) { context = value; }
                public void OnTick(MapTick tick)
                {
                    context!.Log("one");
                    context!.Log("two");
                }
                public void OnStop() { }
            }
            """;
        var logBuilt = Build(Path.Combine(temp.Path, "logs"), logs);
        Check.Assert(logBuilt.Succeeded, string.Join(" | ", logBuilt.Diagnostics.Select(item => item.Code + ": " + item.Message)));
        var logResult = new MapRunner().Run(MapPackage.FromManifest(logBuilt.ManifestPath!), budget);
        Check.Assert(logResult.Report.Outcome == MapRunOutcome.Failed
            && logResult.Report.Error?.Contains("The cooperative operation budget was exceeded.", StringComparison.Ordinal) == true
            && logResult.Report.CompletedTicks == 0
            && logResult.Report.Logs.SequenceEqual(new[] { "one" }),
            (logResult.Report.Error ?? "") + " logs=[" + string.Join(",", logResult.Report.Logs) + "] " + logResult.Report);
        Check.Collected(logResult);
        var logNext = Build(Path.Combine(temp.Path, "logs-next"));
        Check.Assert(logNext.Succeeded, "Next package failed to compile.");
        RunSafe(logNext.ManifestPath!);
    }
    private static void RejectHostSchedulingApis()
    {
        using var temp = new TempDirectory();
        void Reject(string directory, string call, string member)
        {
            var source = $$"""
                using RuneCLR;
                public sealed class GameScript : IMapScript
                {
                    public void OnStart(IMapContext context) { {{call}} }
                    public void OnTick(MapTick tick) { }
                    public void OnStop() { }
                }
                """;
            var error = Check.Throws<InvalidDataException>(() =>
            {
                var built = Build(Path.Combine(temp.Path, directory), source);
                var details = built.Diagnostics.Length == 0
                    ? "Build returned without an exception. Succeeded=" + built.Succeeded
                    : string.Join(" | ", built.Diagnostics.Select(item => item.Code + ": " + item.Message));
                throw new InvalidOperationException(details);
            });
            Check.Assert(error.Message.Contains("Capability profile 'managed-il-gameplay-v1':", StringComparison.Ordinal)
                && error.Message.Contains(member, StringComparison.Ordinal), error.Message);
        }

        Reject("repeat", "context.Repeat(1, 1);", "Member 'RuneCLR.IMapContext.Repeat' is not approved.");
        Reject("resource", "context.RegisterResource(\"a\");", "Member 'RuneCLR.IMapContext.RegisterResource' is not approved.");
        Reject("posted", "context.Subscribe(1);", "Member 'RuneCLR.IMapContext.Subscribe' is not approved.");
        Reject("work", "context.RequestWork(\"a\");", "Member 'RuneCLR.IMapContext.RequestWork' is not approved.");
        var next = Build(Path.Combine(temp.Path, "next"));
        Check.Assert(next.Succeeded, "Next package failed to compile.");
        RunSafe(next.ManifestPath!);
    }
    private static void RejectRemainingHostAccessors()
    {
        using var temp = new TempDirectory();
        void Reject(string directory, string call, string member)
        {
            var source = $$"""
                using RuneCLR;
                public sealed class GameScript : IMapScript
                {
                    public void OnStart(IMapContext context) { {{call}} }
                    public void OnTick(MapTick tick) { }
                    public void OnStop() { }
                }
                """;
            var error = Check.Throws<InvalidDataException>(() =>
            {
                var built = Build(Path.Combine(temp.Path, directory), source);
                var details = built.Diagnostics.Length == 0
                    ? "Build returned without an exception. Succeeded=" + built.Succeeded
                    : string.Join(" | ", built.Diagnostics.Select(item => item.Code + ": " + item.Message));
                throw new InvalidOperationException(details);
            });
            Check.Assert(error.Message.Contains("Capability profile 'managed-il-gameplay-v1':", StringComparison.Ordinal)
                && error.Message.Contains(member, StringComparison.Ordinal), error.Message);
        }

        Reject("schedule", "context.Schedule(1, 1);", "Member 'RuneCLR.IMapContext.Schedule' is not approved.");
        Reject("take-scheduled", "int taken; context.TryTakeScheduled(out taken);", "Member 'RuneCLR.IMapContext.TryTakeScheduled' is not approved.");
        Reject("pending-scheduled", "_ = context.PendingScheduled;", "Member 'RuneCLR.IMapContext.get_PendingScheduled' is not approved.");
        Reject("release-resource", "context.ReleaseResource(\"a\");", "Member 'RuneCLR.IMapContext.ReleaseResource' is not approved.");
        Reject("pending-resources", "_ = context.PendingResources;", "Member 'RuneCLR.IMapContext.get_PendingResources' is not approved.");
        Reject("take-work", "long id; int value; bool ok; context.TryTakeWork(out id, out value, out ok);", "Member 'RuneCLR.IMapContext.TryTakeWork' is not approved.");
        Reject("pending-work", "_ = context.PendingWork;", "Member 'RuneCLR.IMapContext.get_PendingWork' is not approved.");
        Reject("raise-signal", "context.RaiseSignal(1);", "Member 'RuneCLR.IMapContext.RaiseSignal' is not approved.");
        Reject("take-posted", "int postedId; int postedValue; context.TryTakePosted(out postedId, out postedValue);", "Member 'RuneCLR.IMapContext.TryTakePosted' is not approved.");
        Reject("pending-posted", "_ = context.PendingPosted;", "Member 'RuneCLR.IMapContext.get_PendingPosted' is not approved.");
        var next = Build(Path.Combine(temp.Path, "next"));
        Check.Assert(next.Succeeded, "Next package failed to compile.");
        RunSafe(next.ManifestPath!);
    }
    private static void RejectSignalSubscription()
    {
        const string source = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Signal += value => { _ = value; }; }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        using var temp = new TempDirectory();
        var error = Check.Throws<InvalidDataException>(() =>
        {
            var built = Build(Path.Combine(temp.Path, "signal"), source);
            var details = built.Diagnostics.Length == 0
                ? "Build returned without an exception. Succeeded=" + built.Succeeded
                : string.Join(" | ", built.Diagnostics.Select(item => item.Code + ": " + item.Message));
            throw new InvalidOperationException(details);
        });
        Check.Assert(error.Message.Contains("Capability profile 'managed-il-gameplay-v1':", StringComparison.Ordinal)
            && error.Message.Contains("Type 'System.Action`1' is not approved.", StringComparison.Ordinal),
            error.Message);
        var next = Build(Path.Combine(temp.Path, "next"));
        Check.Assert(next.Succeeded, "Next package failed to compile.");
        RunSafe(next.ManifestPath!);
    }
    private static void ApprovedMapId()
    {
        const string source = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Log(context.MapId); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        using var temp = new TempDirectory();
        var built = Build(Path.Combine(temp.Path, "map-id"), source);
        Check.Assert(built.Succeeded, string.Join(" | ", built.Diagnostics.Select(item => item.Code + ": " + item.Message)));
        var result = new MapRunner().Run(MapPackage.FromManifest(built.ManifestPath!), new MapRunOptions { TickCount = 1 });
        Check.Assert(result.Report.Outcome == MapRunOutcome.Completed
            && result.Report.Logs.SequenceEqual(new[] { "CapabilityGame" })
            && result.Report.CompletedTicks == 1,
            (result.Report.Error ?? "") + " logs=[" + string.Join(",", result.Report.Logs) + "]");
        Check.Collected(result);
        var next = Build(Path.Combine(temp.Path, "next"));
        Check.Assert(next.Succeeded, "Next package failed to compile.");
        RunSafe(next.ManifestPath!);
    }
    private static void AuthorCharge()
    {
        using var temp = new TempDirectory();
        const string charged = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Charge(1); context.Log("charged"); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var chargedBuilt = Build(Path.Combine(temp.Path, "charged"), charged);
        Check.Assert(chargedBuilt.Succeeded, string.Join(" | ", chargedBuilt.Diagnostics.Select(item => item.Code + ": " + item.Message)));
        var chargedResult = new MapRunner().Run(MapPackage.FromManifest(chargedBuilt.ManifestPath!),
            new MapRunOptions { TickCount = 1, OperationBudgetPerCallback = 2 });
        Check.Assert(chargedResult.Report.Outcome == MapRunOutcome.Completed
            && chargedResult.Report.Logs.SequenceEqual(new[] { "charged" })
            && chargedResult.Report.CompletedTicks == 1,
            (chargedResult.Report.Error ?? "") + " logs=[" + string.Join(",", chargedResult.Report.Logs) + "]");
        Check.Collected(chargedResult);
        var chargedNext = Build(Path.Combine(temp.Path, "charged-next"));
        Check.Assert(chargedNext.Succeeded, "Next package failed to compile.");
        RunSafe(chargedNext.ManifestPath!);

        const string over = """
            using RuneCLR;
            public sealed class GameScript : IMapScript
            {
                public void OnStart(IMapContext context) { context.Charge(2); }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var overBuilt = Build(Path.Combine(temp.Path, "over"), over);
        Check.Assert(overBuilt.Succeeded, string.Join(" | ", overBuilt.Diagnostics.Select(item => item.Code + ": " + item.Message)));
        var overResult = new MapRunner().Run(MapPackage.FromManifest(overBuilt.ManifestPath!),
            new MapRunOptions { TickCount = 1, OperationBudgetPerCallback = 1 });
        Check.Assert(overResult.Report.Outcome == MapRunOutcome.Failed
            && overResult.Report.Error?.Contains("The cooperative operation budget was exceeded.", StringComparison.Ordinal) == true
            && overResult.Report.CompletedTicks == 0
            && overResult.Report.Logs.Count == 0,
            (overResult.Report.Error ?? "") + " logs=[" + string.Join(",", overResult.Report.Logs) + "]");
        Check.Collected(overResult);
        var overNext = Build(Path.Combine(temp.Path, "over-next"));
        Check.Assert(overNext.Succeeded, "Next package failed to compile.");
        RunSafe(overNext.ManifestPath!);
    }
    private static void RunSafe(string manifestPath)
    {
        var result = new MapRunner().Run(MapPackage.FromManifest(manifestPath), new MapRunOptions { TickCount = 1 });
        Check.Assert(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Allowed gameplay did not finish.");
        Check.Assert(result.Report.Logs.SequenceEqual(new[] { "starts=1;sum=7", "handled", "stopped" }),
            "Allowed gameplay state or exception handling changed.");
        Check.Assert(result.Report.CreatedEntities == 1 && result.Report.ReleasedEntities == 1 && result.Report.RemainingEntities == 0,
            "Allowed gameplay leaked host entities."); Check.Collected(result);
    }
}
