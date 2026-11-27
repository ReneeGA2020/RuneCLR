using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using RuneCLR.Compiler;
using RuneCLR.Packages;

internal static class FinalizerCapabilityCases
{
    private static string Contract => typeof(RuneCLR.IMapScript).Assembly.FullName!;
    private const MethodAttributes Virtual = MethodAttributes.Public | MethodAttributes.Virtual | MethodAttributes.HideBySig;
    private static readonly byte[] InstanceVoid = [0x20, 0, 1];

    public static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Finalize names on static, private, parameterized and generic ordinary methods are admitted", OrdinaryNames);
        yield return ("A newslot Finalize and an override of that ordinary slot are admitted", OrdinarySlots);
        yield return ("An explicit implementation of a local interface Finalize is admitted", InterfaceSlot);
        yield return ("Static abstract interface implementations retain ordinary admission", StaticInterfaceSlots);
        yield return ("External interface mappings cannot be confused with unresolved external class slots", ExternalInterfaceSlots);
        yield return ("C# destructors and inherited author destructors remain rejected", CSharpDestructors);
        yield return ("An implicit object finalizer slot is rejected through a local base chain", InheritedSlot);
        yield return ("A renamed newslot body explicitly overriding Object.Finalize is rejected", ExplicitObjectSlot);
        yield return ("MethodDef and MemberRef explicit finalizer declarations are rejected", ExplicitLocalSlots);
        yield return ("Unresolved external finalizer overrides remain rejected under allow-all API policy", UnknownSlots);
        yield return ("Malformed finalizer flags, signatures and cyclic inheritance fail closed", MalformedSlots);
        yield return ("Modified or ambiguous inherited Finalize signatures fail closed", ModifiedSlots);
        yield return ("Generic Finalize slot resolution rejects invalid kind, arity and trailing metadata", MalformedGenericSlots);
        yield return ("Malformed MethodImpl bodies and declaration tokens fail closed with bounded diagnostics", MalformedImplementations);
    }

    private static byte[] Compile(string name, string source, IReadOnlyList<string>? references = null)
    {
        var result = SourceCompiler.Compile(name, [new("Probe.cs", source)], references ?? CompilerFixture.ApprovedReferences());
        Check.Assert(result.Succeeded, string.Join("; ", result.Diagnostics.Select(d => d.Message)));
        return result.Assembly!;
    }

    private static void Validate(byte[] image, bool allowAll = false)
    {
        if (allowAll)
            GameplayCapabilityPolicy.ValidateWithApiPolicy(image, [], Contract, new RuleBasedApiAccessPolicy(ApiPolicyDefault.Allow, []));
        else GameplayCapabilityPolicy.Validate(image, [], Contract);
    }

    private static void Denied(byte[] image, string reason, bool allowAll = false)
    {
        var error = Check.Throws<InvalidDataException>(() => Validate(image, allowAll));
        Check.Assert(error.Message.Contains(reason, StringComparison.OrdinalIgnoreCase), error.Message);
        Check.Assert((error.Message.Contains("Author.", StringComparison.Ordinal) || error.Message.Contains("Type '<unresolved>'", StringComparison.Ordinal)) &&
            error.Message.Contains("metadata token 0x", StringComparison.Ordinal) && error.Message.Length <= 2048,
            "Finalizer errors must identify the type and metadata token within the diagnostic limit: " + error.Message);
    }

    private static void OrdinaryNames()
    {
        var image = Compile("OrdinaryFinalizeNames", """
            namespace Author;
            public class Ordinary
            {
                public static void Finalize(System.Collections.Generic.List<int> values) { }
                private void Finalize() { }
                public void Finalize(int value) { }
                public static T Finalize<T>(T value) => value;
            }
            public class VirtualOrdinary { public virtual void Finalize(int value) { } }
            """);
        Validate(image);
        Validate(image, allowAll: true);
        GameplayCapabilityPolicy.ValidateWithStandardManagedDelegates(image, [], Contract,
            new RuleBasedApiAccessPolicy(ApiPolicyDefault.Allow, []));
    }

    private static void OrdinarySlots()
    {
        Validate(Build([new("Base", 0, [new("Finalize", Virtual | MethodAttributes.NewSlot)]),
            new("Derived", 1, [new("Finalize", Virtual)])]));
        Validate(Compile("GenericOrdinaryFinalizeSlot", """
            namespace Author;
            public class Base<T> { public virtual void Finalize() { } }
            public class Derived : Base<int> { public override void Finalize() { } }
            """));
    }

    private static void InterfaceSlot()
    {
        Validate(Compile("InterfaceFinalizeName", """
            namespace Author;
            public interface ICleanup { void Finalize(); }
            public class Entry : ICleanup { void ICleanup.Finalize() { } }
            public interface ICleanup<T> { void Finalize(); }
            public class GenericEntry : ICleanup<int> { void ICleanup<int>.Finalize() { } }
            """));
    }

    private static void CSharpDestructors()
    {
        Denied(Compile("RealDestructor", "namespace Author; public class Entry { ~Entry() { } }"), "Author finalizers");
        Denied(Compile("InheritedDestructor", "namespace Author; public class Base { ~Base() { } } public class Entry : Base { }"), "Author finalizers");
        Denied(Compile("DerivedDestructor", "namespace Author; public class Base { } public class Entry : Base { ~Entry() { } }"), "Author finalizers");
    }

    private static void StaticInterfaceSlots() => Validate(Compile("StaticInterfaceFinalizeName", """
        namespace Author;
        public interface ICleanup
        {
            static abstract int Ordinary();
            static abstract void Finalize();
        }
        public sealed class Entry : ICleanup
        {
            static int ICleanup.Ordinary() => 42;
            static void ICleanup.Finalize() { }
        }
        """));

    private static void ExternalInterfaceSlots()
    {
        using var temp = new TempDirectory();
        var provider = Compile("ExternalInterfaceFixture", """
            namespace External;
            public interface ICleanup { void Cleanup(); void Finalize(); }
            """);
        var reference = Path.Combine(temp.Path, "ExternalInterfaceFixture.dll");
        File.WriteAllBytes(reference, provider);
        var author = Compile("ExternalInterfaceAuthor", """
            namespace Author;
            public class Entry : External.ICleanup
            {
                void External.ICleanup.Cleanup() { }
                void External.ICleanup.Finalize() { }
            }
            """, CompilerFixture.ApprovedReferences().Append(reference).ToArray());
        Validate(author, allowAll: true);
        Denied(Build([new("Entry", -1, [new("Cleanup", Virtual | MethodAttributes.NewSlot)])],
            implementation: 12), "Unresolved finalizer", allowAll: true);
        Denied(Build([new("Entry", -1, [new("Cleanup", Virtual)])]), "Unresolved finalizer", allowAll: true);
        Validate(Build([new("Base", 0, [new("Cleanup", Virtual | MethodAttributes.NewSlot)]),
            new("Entry", 1, [new("Cleanup", Virtual)])]));
        Denied(Build([new("Entry", -1, [new("Cleanup", Virtual | MethodAttributes.NewSlot)])],
            implementation: 14), "Unresolved finalizer", allowAll: true);
    }

    private static void InheritedSlot() => Denied(Build([new("Base", 0, []),
        new("Middle", 1, []), new("Derived", 2, [new("Finalize", Virtual)])]), "Author finalizers");

    private static void ExplicitObjectSlot() => Denied(Build([new("Entry", 0,
        [new("Cleanup", Virtual | MethodAttributes.NewSlot)])], implementation: 1), "MethodImpl finalizer slot");

    private static void ExplicitLocalSlots()
    {
        foreach (var declaration in new[] { 10, 11 })
            Denied(Build([new("Derived", 2, [new("Cleanup", Virtual | MethodAttributes.NewSlot)]),
                new("Base", 0, [new("Finalize", Virtual)])],
                implementation: declaration), "MethodImpl finalizer slot");
    }

    private static void UnknownSlots()
    {
        Denied(Build([new("Entry", -1, [new("Finalize", Virtual)])]), "Unresolved finalizer", allowAll: true);
        Denied(Build([new("Entry", -1, [new("Cleanup", Virtual | MethodAttributes.NewSlot)])],
            implementation: 4), "Unresolved finalizer", allowAll: true);
    }

    private static void MalformedSlots()
    {
        Denied(Build([new("Entry", 0, [new("Finalize", Virtual | MethodAttributes.Static)])]), "Unresolved finalizer");
        Denied(Build([new("Entry", 0, [new("Finalize", Virtual, [0x60, 0, 1])])]), "explicit-this");
        Denied(Build([new("Entry", 1, [new("Finalize", Virtual)])]), "Unresolved finalizer");
    }

    private static void ModifiedSlots()
    {
        foreach (var modifier in new byte[] { 0x1f, 0x20 })
            Denied(Build([new("Derived", 2, [new("Finalize", Virtual)]),
                new("Base", 0, [new("Finalize", Virtual | MethodAttributes.NewSlot,
                    [0x20, 0, modifier, 0x05 /* TypeRef Object */, 1])])]), "Unresolved finalizer");
        Denied(Build([new("Derived", 2, [new("Finalize", Virtual)]),
            new("Base", 0, [new("Finalize", Virtual | MethodAttributes.NewSlot),
                new("Finalize", Virtual | MethodAttributes.NewSlot)])]), "Unresolved finalizer");
    }

    private static void MalformedGenericSlots()
    {
        Type[] types = [new("Derived", -2, [new("Finalize", Virtual)]),
            new("Base`1", 0, [new("Finalize", Virtual | MethodAttributes.NewSlot)], 1)];
        Validate(Build(types, baseSpecification: [0x15, 0x12, 0x0c /* TypeDef Base */, 1, 0x08]));
        foreach (var signature in new byte[][]
        {
            [0x15, 0x11 /* VALUETYPE */, 0x0c, 1, 0x08],
            [0x15, 0x12, 0x0c, 0],
            [0x15, 0x12, 0x0c, 2, 0x08, 0x08],
            [0x15, 0x12, 0x0c, 1, 0x08, 0x08]
        }) Denied(Build(types, baseSpecification: signature), "metadata");
    }

    private static void MalformedImplementations()
    {
        foreach (var declaration in new[] { 5, 6, 7, 8, 9 })
            Denied(Build([new("Entry", 0, [new("Cleanup", Virtual | MethodAttributes.NewSlot)])],
                implementation: declaration), "MethodImpl");
    }

    private sealed record Method(string Name, MethodAttributes Attributes, byte[]? Signature = null);
    // Base: 0 = Object, -1 = unresolved external class, positive = local type index (1 based).
    private sealed record Type(string Name, int Base, Method[] Methods, int Arity = 0);

    // These tiny images are metadata fixtures only. Malformed variants are never loaded/executed.
    private static byte[] Build(Type[] types, int implementation = 0, byte[]? baseSpecification = null)
    {
        var metadata = new MetadataBuilder();
        var il = new BlobBuilder();
        var bodies = new MethodBodyStreamEncoder(il);
        metadata.AddModule(0, metadata.GetOrAddString("FinalizerFixture.dll"), metadata.GetOrAddGuid(Guid.NewGuid()), default, default);
        metadata.AddAssembly(metadata.GetOrAddString("FinalizerFixture"), new Version(1, 0, 0, 0), default, default, 0, AssemblyHashAlgorithm.None);
        var core = new AssemblyName(typeof(object).Assembly.FullName!);
        var coreRef = metadata.AddAssemblyReference(metadata.GetOrAddString(core.Name!), core.Version!, default,
            metadata.GetOrAddBlob(core.GetPublicKeyToken()!), 0, default);
        var objectType = metadata.AddTypeReference(coreRef, metadata.GetOrAddString("System"), metadata.GetOrAddString("Object"));
        var unknownType = objectType;
        TypeReferenceHandle nestedInterface = default;
        if (types.Any(type => type.Base == -1) || implementation is 4 or 12 or 14)
        {
            var unknownRef = metadata.AddAssemblyReference(metadata.GetOrAddString("ExternalBase"), new Version(1, 0, 0, 0), default, default, 0, default);
            unknownType = metadata.AddTypeReference(unknownRef, metadata.GetOrAddString("External"), metadata.GetOrAddString("Base"));
            if (implementation == 14)
            {
                var outer = metadata.AddTypeReference(unknownRef, metadata.GetOrAddString("External"), metadata.GetOrAddString("Outer"));
                nestedInterface = metadata.AddTypeReference(outer, default, metadata.GetOrAddString("Contract"));
                unknownType = metadata.AddTypeReference(unknownRef, metadata.GetOrAddString("External"), metadata.GetOrAddString("Outer+Contract"));
            }
        }
        metadata.AddTypeDefinition(TypeAttributes.NotPublic, default, metadata.GetOrAddString("<Module>"), default,
            MetadataTokens.FieldDefinitionHandle(1), MetadataTokens.MethodDefinitionHandle(1));
        var allMethods = new List<MethodDefinitionHandle>();
        for (var index = 0; index < types.Length; index++)
        {
            var type = types[index];
            EntityHandle baseType = type.Base switch
            {
                0 => objectType,
                -1 => unknownType,
                -2 => metadata.AddTypeSpecification(metadata.GetOrAddBlob(baseSpecification!)),
                _ => MetadataTokens.TypeDefinitionHandle(type.Base + 1)
            };
            metadata.AddTypeDefinition(TypeAttributes.Public, metadata.GetOrAddString("Author"), metadata.GetOrAddString(type.Name), baseType,
                MetadataTokens.FieldDefinitionHandle(1), MetadataTokens.MethodDefinitionHandle(allMethods.Count + 1));
            foreach (var method in type.Methods)
            {
                var code = new BlobBuilder();
                var encoder = new InstructionEncoder(code);
                encoder.OpCode(System.Reflection.Metadata.ILOpCode.Ret);
                allMethods.Add(metadata.AddMethodDefinition(method.Attributes, MethodImplAttributes.IL,
                    metadata.GetOrAddString(method.Name), metadata.GetOrAddBlob(method.Signature ?? InstanceVoid),
                    bodies.AddMethodBody(encoder), MetadataTokens.ParameterHandle(1)));
            }
        }
        for (var index = 0; index < types.Length; index++)
            for (var parameter = 0; parameter < types[index].Arity; parameter++)
                metadata.AddGenericParameter(MetadataTokens.TypeDefinitionHandle(index + 2), GenericParameterAttributes.None,
                    metadata.GetOrAddString("T" + parameter), parameter);
        if (implementation == 14)
            metadata.AddInterfaceImplementation(MetadataTokens.TypeDefinitionHandle(2), nestedInterface);
        if (implementation != 0)
        {
            EntityHandle declaration = implementation switch
            {
                2 => allMethods[0],
                3 => metadata.AddMemberReference(MetadataTokens.TypeDefinitionHandle(2), metadata.GetOrAddString("Finalize"), metadata.GetOrAddBlob(InstanceVoid)),
                5 => MetadataTokens.MethodDefinitionHandle(999),
                6 => metadata.AddMemberReference(objectType, metadata.GetOrAddString("Finalize"), metadata.GetOrAddBlob(new byte[] { 0x06, 0x08 })),
                9 => allMethods[^1],
                10 => allMethods[^1],
                11 => metadata.AddMemberReference(MetadataTokens.TypeDefinitionHandle(3), metadata.GetOrAddString("Finalize"), metadata.GetOrAddBlob(InstanceVoid)),
                _ => metadata.AddMemberReference(implementation is 4 or 12 or 14 ? unknownType : objectType,
                    metadata.GetOrAddString(implementation is 12 or 14 ? "Cleanup" : "Finalize"), metadata.GetOrAddBlob(InstanceVoid))
            };
            metadata.AddMethodImplementation(MetadataTokens.TypeDefinitionHandle(implementation == 8 ? 999 : implementation is 10 or 11 ? 2 : types.Length + 1),
                implementation == 7 ? MetadataTokens.MethodDefinitionHandle(999) : implementation is 10 or 11 ? allMethods[0] : allMethods[^1], declaration);
        }
        var pe = new ManagedPEBuilder(new PEHeaderBuilder(imageCharacteristics: Characteristics.ExecutableImage | Characteristics.Dll),
            new MetadataRootBuilder(metadata), il, flags: CorFlags.ILOnly);
        var image = new BlobBuilder();
        pe.Serialize(image);
        return image.ToArray();
    }
}
