using System.Collections.Immutable;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Buffers.Binary;
using RuneCLR.Packages;

internal static class IntakeCases
{
    private const string Entry = "RuneCLR.TestMaps.CounterMap";

    public static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("IL intake reads full identities without loading the submitted assembly", IdentityWithoutLoading);
        yield return ("IL intake rejects metadata names that could escape or break package paths", UnsafeAssemblyNames);
        yield return ("IL intake accepts the initial direct-contract entry profile", () =>
            ManagedAssemblyInspector.ValidateEntry(Input(), Entry, ContractIdentity()));
        yield return ("IL intake rejects an empty image", () => Rejected([], "nonempty"));
        yield return ("IL intake rejects a truncated PE header", () => Rejected(Input()[..64], "PE"));
        yield return ("IL intake rejects a truncated PE section", () => Rejected(Input()[..^1], "outside"));
        yield return ("IL intake bounds input size before metadata processing", () =>
            Rejected(new byte[ManagedAssemblyInspector.MaximumImageBytes + 1], "limit", "larger"));
        yield return ("IL intake preserves missing-file I/O errors", () =>
            Check.Throws<FileNotFoundException>(() => ManagedAssemblyInspector.Inspect(
                Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".dll"))));
        yield return ("IL intake rejects the mixed-mode flag even on an otherwise managed fixture", () =>
            Rejected(Mutate((bytes, pe, _) => Write32(bytes, pe.PEHeaders.CorHeaderStartOffset + 16,
                (uint)(pe.PEHeaders.CorHeader!.Flags & ~CorFlags.ILOnly))), "IL-only"));
        yield return ("IL intake rejects author-marked native entry points", () =>
            Rejected(Mutate((bytes, pe, _) => Write32(bytes, pe.PEHeaders.CorHeaderStartOffset + 16,
                (uint)(pe.PEHeaders.CorHeader!.Flags | CorFlags.NativeEntryPoint))), "Native CLR entry"));
        yield return ("IL intake rejects a managed-native directory header mutation", () =>
        {
            // This exercises the directory guard; it is not a genuine crossgen-produced R2R fixture.
            var mutated = Mutate((bytes, pe, _) =>
            {
                Write32(bytes, pe.PEHeaders.CorHeaderStartOffset + 64,
                    (uint)pe.PEHeaders.CorHeader!.MetadataDirectory.RelativeVirtualAddress);
                Write32(bytes, pe.PEHeaders.CorHeaderStartOffset + 68, 16);
            });
            Rejected(mutated, "ReadyToRun");
        });
        yield return ("IL intake rejects an author-marked native CLR vtable directory", () =>
            Rejected(Mutate((bytes, pe, _) => Write32(bytes, pe.PEHeaders.CorHeaderStartOffset + 48, 1)), "vtable"));
        yield return ("IL intake rejects PInvoke method metadata", () =>
            Rejected(MethodMutation((bytes, offset, method) => Write16(bytes, offset + 6,
                (ushort)(method.Attributes | MethodAttributes.PinvokeImpl))), "P/Invoke"));
        yield return ("IL intake rejects InternalCall method metadata", () =>
            Rejected(MethodMutation((bytes, offset, method) => Write16(bytes, offset + 4,
                (ushort)(method.ImplAttributes | MethodImplAttributes.InternalCall))), "InternalCall"));
        yield return ("IL intake rejects native method implementations", () =>
            Rejected(MethodMutation((bytes, offset, method) => Write16(bytes, offset + 4,
                (ushort)((method.ImplAttributes & ~MethodImplAttributes.CodeTypeMask) | MethodImplAttributes.Native))), "non-IL"));
        yield return ("IL intake rejects an invalid method RVA", () =>
            Rejected(MethodMutation((bytes, offset, _) => Write32(bytes, offset, 0x7ffffff0)), "Malformed"));
        yield return ("IL intake rejects an IL method missing its body", () =>
            Rejected(MethodMutation((bytes, offset, _) => Write32(bytes, offset, 0)), "missing its IL body"));
        yield return ("IL intake rejects an out-of-bounds fat method body", CorruptFatBody);
        yield return ("IL intake rejects an exception region beyond the method body", CorruptExceptionRegion);
        yield return ("Entry intake rejects a different approved contract identity", () =>
        {
            var wrong = new AssemblyName(ContractIdentity()) { Version = new Version(99, 0, 0, 0) };
            EntryRejected(Input(), wrong.FullName!, "approved", "directly implement");
        });
        yield return ("Entry intake rejects unsupported inherited implementations", () =>
            Check.Assert(Check.Throws<InvalidDataException>(() => ManagedAssemblyInspector.ValidateEntry(
                Input(), "RuneCLR.TestMaps.MapDefinedException", ContractIdentity())).Message.Contains("System.Object"),
                "Inherited entry rejection must explain the initial profile."));
        yield return ("Entry intake rejects abstract classes before execution", () =>
            EntryRejected(Mutate((bytes, pe, metadata) =>
            {
                var handle = EntryHandle(metadata);
                var type = metadata.GetTypeDefinition(handle);
                var offset = pe.PEHeaders.MetadataStartOffset + metadata.GetTableMetadataOffset(TableIndex.TypeDef)
                    + (MetadataTokens.GetRowNumber(handle) - 1) * metadata.GetTableRowSize(TableIndex.TypeDef);
                Write32(bytes, offset, (uint)(type.Attributes | TypeAttributes.Abstract));
            }), ContractIdentity(), "nonabstract"));
        yield return ("Entry intake requires a public no-argument constructor", () =>
            EntryRejected(Mutate((bytes, pe, metadata) =>
            {
                var handle = metadata.GetTypeDefinition(EntryHandle(metadata)).GetMethods().First(handle =>
                    metadata.GetString(metadata.GetMethodDefinition(handle).Name) == ".ctor");
                var method = metadata.GetMethodDefinition(handle);
                Write16(bytes, MethodOffset(pe, metadata, handle) + 6,
                    (ushort)((method.Attributes & ~MethodAttributes.MemberAccessMask) | MethodAttributes.Private));
            }), ContractIdentity(), "constructor"));
        yield return ("Entry intake rejects an obviously malformed callback return signature", CorruptCallbackSignature);
    }

    private static byte[] Input() => File.ReadAllBytes(Fixtures.TestAssembly);
    private static string ContractIdentity() => ManagedAssemblyInspector.Inspect(Fixtures.ContractAssembly).AssemblyName;

    private static void IdentityWithoutLoading()
    {
        var expected = AssemblyName.GetAssemblyName(Fixtures.TestAssembly);
        var before = AppDomain.CurrentDomain.GetAssemblies().Count(assembly => assembly.GetName().Name == expected.Name);
        var info = ManagedAssemblyInspector.Inspect(Fixtures.TestAssembly);
        Check.Assert(info.AssemblyName == expected.FullName && info.SimpleName == expected.Name,
            "Metadata identities must match the assembly's complete identity.");
        Check.Assert(info.AssemblyName.EndsWith("PublicKeyToken=null", StringComparison.Ordinal),
            "Unsigned identities must explicitly retain the null public-key token.");
        Check.Assert(info.References.Contains(ContractIdentity(), StringComparer.Ordinal),
            "AssemblyRef identities must include the exact approved contract.");
        Check.Assert(AppDomain.CurrentDomain.GetAssemblies().Count(assembly => assembly.GetName().Name == expected.Name) == before,
            "Metadata inspection must not load the submitted assembly.");
    }

    private static void UnsafeAssemblyNames()
    {
        foreach (var name in new[] { "../escape", "..\\escape", "C:escape", "bad\nname", "bad?name",
            "bad|name", "bad<name", ".", "..", "trailing.", "trailing ", "CON.dll", "NUL.dll", "LPT1.dll", "COM9.dll" })
        {
            var mutated = Mutate((bytes, pe, metadata) =>
            {
                var handle = metadata.GetAssemblyDefinition().Name;
                var existing = metadata.GetString(handle);
                var encoded = System.Text.Encoding.UTF8.GetBytes(name);
                Check.Assert(encoded.Length <= System.Text.Encoding.UTF8.GetByteCount(existing), "Mutation must fit the real metadata string.");
                var offset = pe.PEHeaders.MetadataStartOffset + metadata.GetHeapMetadataOffset(HeapIndex.String)
                    + MetadataTokens.GetHeapOffset(handle);
                bytes.AsSpan(offset, System.Text.Encoding.UTF8.GetByteCount(existing) + 1).Clear();
                encoded.CopyTo(bytes.AsSpan(offset));
            });
            Rejected(mutated, "basename");
        }
    }

    private static byte[] Mutate(Action<byte[], PEReader, MetadataReader> edit)
    {
        var bytes = Input();
        using var pe = new PEReader(ImmutableArray.CreateRange(bytes));
        edit(bytes, pe, pe.GetMetadataReader());
        return bytes;
    }

    private static byte[] MethodMutation(Action<byte[], int, MethodDefinition> edit) =>
        Mutate((bytes, pe, metadata) =>
        {
            var handle = metadata.MethodDefinitions.First(handle =>
                metadata.GetMethodDefinition(handle).RelativeVirtualAddress != 0);
            edit(bytes, MethodOffset(pe, metadata, handle), metadata.GetMethodDefinition(handle));
        });

    private static int MethodOffset(PEReader pe, MetadataReader metadata, MethodDefinitionHandle handle) =>
        pe.PEHeaders.MetadataStartOffset + metadata.GetTableMetadataOffset(TableIndex.MethodDef) +
        (MetadataTokens.GetRowNumber(handle) - 1) * metadata.GetTableRowSize(TableIndex.MethodDef);

    private static int FileOffset(PEReader pe, int rva)
    {
        var section = pe.PEHeaders.SectionHeaders.Single(section =>
            rva >= section.VirtualAddress && rva < (long)section.VirtualAddress + section.SizeOfRawData);
        return checked(section.PointerToRawData + rva - section.VirtualAddress);
    }

    private static TypeDefinitionHandle EntryHandle(MetadataReader metadata) => metadata.TypeDefinitions.Single(handle =>
        metadata.GetString(metadata.GetTypeDefinition(handle).Namespace) == "RuneCLR.TestMaps" &&
        metadata.GetString(metadata.GetTypeDefinition(handle).Name) == "CounterMap");

    private static void CorruptFatBody()
    {
        Rejected(Mutate((bytes, pe, metadata) =>
        {
            var rva = metadata.MethodDefinitions.Select(handle => metadata.GetMethodDefinition(handle).RelativeVirtualAddress)
                .First(rva => rva != 0 && (bytes[FileOffset(pe, rva)] & 3) == 3);
            Write32(bytes, FileOffset(pe, rva) + 4, int.MaxValue);
        }), "Malformed");
    }

    private static void CorruptExceptionRegion()
    {
        Rejected(Mutate((bytes, pe, metadata) =>
        {
            var rva = metadata.MethodDefinitions.Select(handle => metadata.GetMethodDefinition(handle).RelativeVirtualAddress)
                .First(rva => rva != 0 && pe.GetMethodBody(rva).ExceptionRegions.Length != 0);
            var body = pe.GetMethodBody(rva);
            var offset = FileOffset(pe, rva);
            var headerBytes = (BinaryPrimitives.ReadUInt16LittleEndian(bytes.AsSpan(offset, 2)) >> 12) * 4;
            var codeLength = body.GetILBytes()!.Length;
            var section = (offset + headerBytes + codeLength + 3) & ~3;
            Check.Assert((bytes[section] & 0x3f) == 1, "Expected a genuine compiler-generated exception table.");
            if ((bytes[section] & 0x40) != 0) Write32(bytes, section + 8, (uint)(codeLength + 1));
            else Write16(bytes, section + 6, checked((ushort)(codeLength + 1)));
        }), "exception region");
    }

    private static void CorruptCallbackSignature()
    {
        var mutated = Mutate((bytes, pe, metadata) =>
        {
            var handle = metadata.GetTypeDefinition(EntryHandle(metadata)).GetMethods().Single(handle =>
                metadata.GetString(metadata.GetMethodDefinition(handle).Name) == "OnTick");
            var signature = metadata.GetMethodDefinition(handle).Signature;
            var offset = pe.PEHeaders.MetadataStartOffset + metadata.GetHeapMetadataOffset(HeapIndex.Blob) + MetadataTokens.GetHeapOffset(signature);
            var prefixLength = (bytes[offset] & 0x80) == 0 ? 1 : (bytes[offset] & 0xc0) == 0x80 ? 2 : 4;
            offset += prefixLength;
            Check.Assert(bytes[offset] == 0x20 && bytes[offset + 1] == 1 && bytes[offset + 2] == 1,
                "Expected the real compiler's instance void OnTick signature.");
            bytes[offset + 2] = 0x08; // Structurally decodable return type changed from void to int32.
        });
        EntryRejected(mutated, ContractIdentity(), "signature");
    }

    private static void Rejected(byte[] image, params string[] reasons)
    {
        var exception = Check.Throws<InvalidDataException>(() => ManagedAssemblyInspector.Inspect(image));
        Check.Assert(reasons.Any(reason => exception.Message.Contains(reason, StringComparison.OrdinalIgnoreCase)),
            $"Expected actionable intake reason ({string.Join(", ", reasons)}), received: {exception.Message}");
    }

    private static void EntryRejected(byte[] image, string contract, params string[] reasons)
    {
        var exception = Check.Throws<InvalidDataException>(() => ManagedAssemblyInspector.ValidateEntry(image, Entry, contract));
        Check.Assert(reasons.Any(reason => exception.Message.Contains(reason, StringComparison.OrdinalIgnoreCase)),
            $"Expected actionable entry reason, received: {exception.Message}");
    }

    private static void Write32(byte[] bytes, int offset, uint value) =>
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(offset, 4), value);
    private static void Write16(byte[] bytes, int offset, ushort value) =>
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(offset, 2), value);
}
