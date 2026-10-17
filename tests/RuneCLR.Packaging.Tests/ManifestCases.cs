using System.Buffers.Binary;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Text.Json.Nodes;
using RuneCLR.Compiler;
using RuneCLR.Packages;
using RuneCLR.Runtime;

internal static class ManifestCases
{
    private static readonly Lazy<byte[]> ScriptImage = new(() =>
    {
        const string source = """
            using RuneCLR;
            namespace RuneCLR.TestMaps;
            public sealed class CounterMap : IMapScript
            {
                private static int starts;
                private IMapContext context = null!;
                public void OnStart(IMapContext value)
                {
                    context = value;
                    context.Log("starts=" + (++starts));
                    context.SpawnEntity("fixture");
                }
                public void OnTick(MapTick tick) { context.Log("tick=" + tick.Index); }
                public void OnStop() { context.Log("stopped"); }
            }
            """;
        var compiled = SourceCompiler.Compile("ManifestScript", [new("CounterMap.cs", source)],
            CompilerFixture.ApprovedReferences());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        return compiled.Assembly!;
    });

    public static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Versioned manifest roundtrips and retains collectible lifecycle", Roundtrip);
        yield return ("Manifest host interface fields run the host-contract check on load", HostInterfaceAllowList);
        yield return ("Manifest host interface fields reject an unlisted OnStart call", HostInterfaceRejectsUnlisted);
        yield return ("Manifest rejects a host interface without allowed methods", HostInterfacePairRequired);
        yield return ("Canonical content identity ignores array order and its own hash field", CanonicalIdentity);
        yield return ("Versioned reader rejects unknown and duplicate properties", StrictReader);
        yield return ("Versioned fields cannot downgrade to the trusted legacy reader", StrictDispatch);
        yield return ("Versioned packages bind the real host contract identity without image hash equality", HostContractIdentity);
        yield return ("Versioned reader bounds manifest bytes", ManifestSize);
        yield return ("Package rejects unsupported format, API and input profiles", UnsupportedProfiles);
        yield return ("Package requires producer and input identities", RequiredProvenance);
        yield return ("Package requires consistent entry, dependency and file declarations", FileDeclarations);
        yield return ("Package rejects duplicate paths and provenance inputs", DuplicateIdentities);
        yield return ("Package rejects noncanonical and escaping content paths", InvalidPaths);
        yield return ("Package detects extra and missing physical files", PhysicalInventory);
        yield return ("Package detects changed file bytes and manifest content identities", ChangedContent);
        yield return ("Versioned package cannot include the shared host contract", ContractCopy);
        yield return ("Versioned runtime snapshot cannot be bypassed by record with modifications", SnapshotFields);
        yield return ("Versioned runtime revalidates a changed manifest before each session", SnapshotManifest);
    }


    private static void HostInterfaceAllowList()
    {
        using var temp = new TempDirectory();
        var manifest = Seal(HostMap(temp) with { HostInterface = "RuneCLR.IMapContext", AllowedMethods = ["SpawnEntity", "Log"] });
        var path = ManifestPath(temp);
        PackageManifestIO.Write(path, manifest);
        var read = PackageManifestIO.Read(path);
        PackageValidator.Validate(read, path);
        Check.Assert(read.HostInterface == "RuneCLR.IMapContext", "Host interface was not retained.");
        Check.Assert(read.AllowedMethods is not null && read.AllowedMethods.SequenceEqual(["Log", "SpawnEntity"]), "Allowed methods were not stored canonically.");
    }

    private static void HostInterfaceRejectsUnlisted()
    {
        using var temp = new TempDirectory();
        Reject(Seal(HostMap(temp) with { HostInterface = "RuneCLR.IMapContext", AllowedMethods = ["Log"] }), temp);
    }

    private static void HostInterfacePairRequired()
    {
        using var temp = new TempDirectory();
        Reject(Seal(HostMap(temp) with { HostInterface = "RuneCLR.IMapContext" }), temp);
    }

    private static PackageManifest HostMap(TempDirectory temp)
    {
        const string source = """
            using RuneCLR;
            public sealed class HostMap : IMapScript
            {
                public void OnStart(IMapContext context)
                {
                    context.Log("ok");
                    context.SpawnEntity("fixture");
                }
                public void OnTick(MapTick tick) { }
                public void OnStop() { }
            }
            """;
        var compiled = SourceCompiler.Compile("HostMapScript", [new("HostMap.cs", source)], CompilerFixture.ApprovedReferences());
        Check.Assert(compiled.Succeeded && compiled.Assembly is not null, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        File.WriteAllBytes(Path.Combine(temp.Path, "Script.dll"), compiled.Assembly!);
        var hash = Fixtures.Hash(compiled.Assembly!);
        return new(PackageFormat.CurrentVersion, PackageFormat.CurrentApiVersion, PackageFormat.InputProfile,
            "host-interface", "Script.dll", "HostMap", hash, [], [new("Script.dll", hash)], Fixtures.ValidProducer(), "");
    }
    private static PackageManifest Create(TempDirectory temp)
    {
        var bytes = ScriptImage.Value;
        File.WriteAllBytes(Path.Combine(temp.Path, "Script.dll"), bytes);
        var hash = Fixtures.Hash(bytes);
        return Seal(new(PackageFormat.CurrentVersion, PackageFormat.CurrentApiVersion, PackageFormat.InputProfile,
            "manifest-test", "Script.dll", "RuneCLR.TestMaps.CounterMap", hash, [],
            [new("Script.dll", hash)], Fixtures.ValidProducer(), ""));
    }

    private static PackageManifest Seal(PackageManifest manifest) =>
        manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
    private static string ManifestPath(TempDirectory temp) => Path.Combine(temp.Path, PackageFormat.ManifestFileName);
    private static void Reject(PackageManifest manifest, TempDirectory temp) =>
        Check.Throws<InvalidDataException>(() => PackageValidator.Validate(manifest, ManifestPath(temp)));

    private static void Roundtrip()
    {
        using var temp = new TempDirectory(); var manifest = Create(temp); var path = ManifestPath(temp);
        PackageManifestIO.Write(path, manifest);
        var read = PackageManifestIO.Read(path); PackageValidator.Validate(read, path);
        Check.Assert(read.ContentSha256 == manifest.ContentSha256, "Manifest roundtrip changed content identity.");
        var result = new MapRunner().Run(MapPackage.FromManifest(path));
        Check.Assert(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Versioned fixture failed.");
        Check.Assert(result.Report.Logs[0] == "starts=1" && result.Report.RemainingEntities == 0, "Lifecycle/static cleanup mismatch.");
        Check.Collected(result);
    }

    private static void CanonicalIdentity()
    {
        using var temp = new TempDirectory(); var original = Create(temp); var hash = original.EntrySha256;
        // Synthetic declarations exercise only canonical ordering, not file validity.
        var manifest = original with
        {
            Dependencies = [new("A.dll", "A, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null", hash),
                new("B.dll", "B, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null", hash)],
            Files = [new("A.dll", hash), new("B.dll", hash), original.Files[0]],
            Producer = original.Producer with
            {
                Compiler = [new("a", hash), new("b", hash)], Sources = [new("a.cs", hash), new("b.cs", hash)]
            }
        };
        var reordered = manifest with
        {
            Dependencies = manifest.Dependencies.Reverse().ToArray(), Files = manifest.Files.Reverse().ToArray(),
            Producer = manifest.Producer with
            {
                Compiler = manifest.Producer.Compiler.Reverse().ToArray(), References = manifest.Producer.References.Reverse().ToArray(),
                Sources = manifest.Producer.Sources.Reverse().ToArray()
            }, ContentSha256 = new string('0', 64)
        };
        Check.Assert(PackageManifestIO.ComputeContentSha256(manifest) == PackageManifestIO.ComputeContentSha256(reordered),
            "Canonical hashing depends on input array ordering or its own digest.");
    }

    private static void StrictReader()
    {
        using var temp = new TempDirectory(); var path = ManifestPath(temp); PackageManifestIO.Write(path, Create(temp));
        var json = File.ReadAllText(path);
        foreach (var invalid in new[]
        {
            json.Insert(1, "\"unknown\":true,"), json.Insert(1, "\"formatVersion\":1,"),
            json.Replace("\"tool\":", "\"tool\":\"duplicate\",\"tool\":", StringComparison.Ordinal),
            json.Replace("\"tool\":", "\"unexpectedNestedField\":true,\"tool\":", StringComparison.Ordinal)
        })
        {
            File.WriteAllText(path, invalid);
            Check.Throws<InvalidDataException>(() => PackageManifestIO.Read(path));
        }
    }

    private static void ManifestSize()
    {
        using var temp = new TempDirectory(); var path = ManifestPath(temp);
        File.WriteAllBytes(path, new byte[PackageManifestIO.MaximumManifestBytes + 1]);
        Check.Throws<InvalidDataException>(() => PackageManifestIO.Read(path));
    }

    private static void StrictDispatch()
    {
        using var temp = new TempDirectory(); var path = ManifestPath(temp); var manifest = Create(temp);
        PackageManifestIO.Write(path, manifest);
        var versioned = JsonNode.Parse(File.ReadAllText(path))!.AsObject();
        versioned.Remove("formatVersion");
        File.WriteAllText(path, versioned.ToJsonString());
        Check.Throws<InvalidDataException>(() => MapPackage.FromManifest(path));

        var legacy = new JsonObject
        {
            ["id"] = manifest.Id, ["entryAssembly"] = manifest.EntryAssembly, ["entryType"] = manifest.EntryType
        };
        File.WriteAllText(path, legacy.ToJsonString());
        Check.Assert(MapPackage.FromManifest(path).Id == manifest.Id, "The trusted legacy schema stopped loading.");
        foreach (var marker in new[] { "formatVersion", "apiVersion", "inputProfile", "files", "producer", "contentSha256" })
        {
            var marked = legacy.DeepClone().AsObject();
            // A marker alone must select the required new schema, even if its casing is wrong.
            marked[marker.ToUpperInvariant()] = null;
            File.WriteAllText(path, marked.ToJsonString());
            Check.Throws<InvalidDataException>(() => MapPackage.FromManifest(path));
        }
    }

    private static void HostContractIdentity()
    {
        using var temp = new TempDirectory(); var path = ManifestPath(temp); var manifest = Create(temp);
        var contractBytes = File.ReadAllBytes(Fixtures.ContractAssembly);
        var contractIdentity = ManagedAssemblyInspector.Inspect(contractBytes).AssemblyName;
        // A managed reference image may differ from the host's installed/R2R image
        // without changing its ABI identity. Provenance is not an approval assertion.
        var alternateImage = contractBytes.Concat(new byte[] { 0 }).ToArray();
        Check.Assert(ManagedAssemblyInspector.Inspect(alternateImage).AssemblyName == contractIdentity,
            "Alternate contract image changed assembly identity.");
        var compatible = Seal(manifest with { Producer = manifest.Producer with
        {
            References = manifest.Producer.References.Select(input => input.AssemblyName == contractIdentity
                ? input with { Sha256 = Fixtures.Hash(alternateImage) } : input).ToArray()
        } });
        PackageManifestIO.Write(path, compatible);
        var result = new MapRunner().Run(MapPackage.FromManifest(path));
        Check.Assert(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Compatible contract identity was rejected.");
        Check.Collected(result);

        var entryBytes = File.ReadAllBytes(Path.Combine(temp.Path, manifest.EntryAssembly));
        SetContractMajorVersion(entryBytes, definition: false);
        SetContractMajorVersion(contractBytes, definition: true);
        var incompatibleIdentity = ManagedAssemblyInspector.Inspect(contractBytes).AssemblyName;
        Check.Assert(ManagedAssemblyInspector.Inspect(entryBytes).References.Contains(incompatibleIdentity),
            "Entry fixture mutation did not change its actual contract reference.");
        File.WriteAllBytes(Path.Combine(temp.Path, manifest.EntryAssembly), entryBytes);
        var hash = Fixtures.Hash(entryBytes);
        var incompatible = Seal(manifest with
        {
            EntrySha256 = hash, Files = [new(manifest.EntryAssembly, hash)],
            Producer = manifest.Producer with
            {
                References = manifest.Producer.References.Select(input => input.AssemblyName == contractIdentity
                    ? input with { AssemblyName = incompatibleIdentity, Sha256 = Fixtures.Hash(contractBytes) } : input).ToArray(),
                Sources = [new(Path.GetFileName(Fixtures.TestAssembly), hash, ManagedAssemblyInspector.Inspect(entryBytes).AssemblyName)]
            }
        });
        // Self-consistent input metadata is valid packaging provenance, but cannot
        // replace the runtime's actual shared contract binding.
        PackageManifestIO.Write(path, incompatible);
        PackageValidator.Validate(incompatible, path);
        var exception = Check.Throws<InvalidDataException>(() => MapPackage.FromManifest(path));
        Check.Assert(exception.Message.Contains("incompatible host contract", StringComparison.Ordinal),
            "Incompatible host contract was not rejected at the runtime package boundary.");
    }

    private static void SetContractMajorVersion(byte[] bytes, bool definition)
    {
        using var pe = new PEReader(new MemoryStream(bytes, writable: false));
        var metadata = pe.GetMetadataReader();
        var table = definition ? TableIndex.Assembly : TableIndex.AssemblyRef;
        var row = definition ? 1 : MetadataTokens.GetRowNumber(metadata.AssemblyReferences.Single(handle =>
            metadata.GetString(metadata.GetAssemblyReference(handle).Name) == "RuneCLR.Abstractions"));
        var offset = pe.PEHeaders.MetadataStartOffset + metadata.GetTableMetadataOffset(table) +
            (row - 1) * metadata.GetTableRowSize(table) + (definition ? 4 : 0);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(offset, 2), 900);
    }

    private static void UnsupportedProfiles()
    {
        using var temp = new TempDirectory(); var manifest = Create(temp);
        foreach (var invalid in new[] { manifest with { FormatVersion = 2 }, manifest with { ApiVersion = 2 },
            manifest with { InputProfile = "native-v1" } }) Reject(Seal(invalid), temp);
    }

    private static void RequiredProvenance()
    {
        using var temp = new TempDirectory(); var manifest = Create(temp); var producer = manifest.Producer;
        Reject(manifest with { Producer = null! }, temp);
        foreach (var invalid in new[] { producer with { Tool = "" }, producer with { ToolVersion = "" },
            producer with { Sources = [] }, producer with { References = [] },
            producer with { InputKind = "source", Compiler = [] }, producer with { InputKind = "author-r2r" },
            producer with { Sources = [producer.Sources[0] with { Sha256 = "invalid" }] } })
            Reject(Seal(manifest with { Producer = invalid }), temp);
    }

    private static void FileDeclarations()
    {
        using var temp = new TempDirectory(); var manifest = Create(temp);
        Reject(Seal(manifest with { Files = [] }), temp);
        Reject(Seal(manifest with { Files = [manifest.Files[0] with { Sha256 = new string('0', 64) }] }), temp);
        Reject(Seal(manifest with { Dependencies = [new("Other.dll",
            "Other, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null", manifest.EntrySha256)] }), temp);
    }

    private static void DuplicateIdentities()
    {
        using var temp = new TempDirectory(); var manifest = Create(temp);
        Reject(Seal(manifest with { Files = [manifest.Files[0], manifest.Files[0]] }), temp);
        Reject(Seal(manifest with { Producer = manifest.Producer with
            { Sources = [manifest.Producer.Sources[0], manifest.Producer.Sources[0]] } }), temp);
    }

    private static void InvalidPaths()
    {
        using var temp = new TempDirectory(); var manifest = Create(temp);
        foreach (var path in new[] { "../Script.dll", "./Script.dll", "lib//Script.dll", "lib/../Script.dll",
            Path.GetFullPath(Path.Combine(temp.Path, "Script.dll")), "lib" + (char)92 + "Script.dll", "C:Script.dll" })
            Reject(Seal(manifest with { EntryAssembly = path, Files = [new(path, manifest.EntrySha256)] }), temp);
    }

    private static void PhysicalInventory()
    {
        using var temp = new TempDirectory(); var manifest = Create(temp);
        var extra = Path.Combine(temp.Path, "extra.txt"); File.WriteAllText(extra, "extra"); Reject(manifest, temp);
        File.Delete(extra); File.Delete(Path.Combine(temp.Path, "Script.dll")); Reject(manifest, temp);
    }

    private static void ChangedContent()
    {
        using var temp = new TempDirectory(); var manifest = Create(temp);
        Reject(manifest with { ContentSha256 = new string('0', 64) }, temp);
        File.AppendAllText(Path.Combine(temp.Path, "Script.dll"), "changed"); Reject(manifest, temp);
    }

    private static void ContractCopy()
    {
        using var temp = new TempDirectory(); var manifest = Create(temp); var bytes = File.ReadAllBytes(Fixtures.ContractAssembly);
        File.WriteAllBytes(Path.Combine(temp.Path, "Script.dll"), bytes); var hash = Fixtures.Hash(bytes);
        Reject(Seal(manifest with { EntrySha256 = hash, Files = [new("Script.dll", hash)] }), temp);
    }

    private static void SnapshotFields()
    {
        using var temp = new TempDirectory(); var path = ManifestPath(temp); PackageManifestIO.Write(path, Create(temp));
        var package = MapPackage.FromManifest(path);
        foreach (var changed in new[] { package with { Id = "changed" }, package with { EntryType = "Changed" },
            package with { AssemblyPath = Fixtures.TestAssembly }, package with { EntrySha256 = null },
            package with { Dependencies = [new("Other.dll", "Other", new string('0', 64))] } })
            Check.Throws<InvalidDataException>(() => new MapRunner().Run(changed));
    }

    private static void SnapshotManifest()
    {
        using var temp = new TempDirectory(); var path = ManifestPath(temp); var manifest = Create(temp);
        PackageManifestIO.Write(path, manifest); var package = MapPackage.FromManifest(path);
        PackageManifestIO.Write(path, Seal(manifest with { Id = "changed" }));
        Check.Throws<InvalidDataException>(() => new MapRunner().Run(package));
    }
}
