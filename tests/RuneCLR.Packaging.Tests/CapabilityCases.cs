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
    private static void SafeLifecycle()
    {
        using var temp = new TempDirectory(); var built = Build(Path.Combine(temp.Path, "package"));
        Check.Assert(built.Succeeded, "Allowed gameplay fixture failed compilation.");
        for (var cycle = 0; cycle < 3; cycle++) RunSafe(built.ManifestPath!);
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
