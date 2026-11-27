using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;

namespace RuneCLR.Packages;

public static partial class GameplayCapabilityPolicy
{
    private sealed partial class Inspection
    {
        // Resolve slots in this image only. An unresolved external Finalize override is denied,
        // rather than assuming that a caller's API allow rule proves its base-class layout.
        private enum FinalizerSlot { Ordinary, Finalizer, Unknown }
        private readonly Dictionary<MethodDefinitionHandle, FinalizerSlot> finalizerSlots = new();
        private readonly HashSet<MethodDefinitionHandle> resolvingFinalizerSlots = new();

        private void ValidateFinalizerSlots()
        {
            var implementations = new HashSet<MethodImplementationHandle>();
            foreach (var typeHandle in metadata.TypeDefinitions)
            {
                var type = metadata.GetTypeDefinition(typeHandle);
                foreach (var implementationHandle in type.GetMethodImplementations())
                {
                    var bodyDescription = "MethodImpl";
                    try
                    {
                        var implementation = metadata.GetMethodImplementation(implementationHandle);
                        if (implementation.Type != typeHandle || !implementations.Add(implementationHandle))
                            throw Invalid("Inconsistent MethodImpl declaring type metadata.");
                        var bodyHandle = LocalMethod(implementation.MethodBody);
                        var body = metadata.GetMethodDefinition(bodyHandle);
                        bodyDescription = $"{Identifier(body.Name)} (body 0x{MetadataTokens.GetToken(bodyHandle):X8}, MethodImpl)";
                        if (body.GetDeclaringType() != typeHandle)
                            throw Invalid("MethodImpl body must belong to its declaring type.");
                        if ((body.Attributes & (MethodAttributes.Static | MethodAttributes.Virtual)) == 0)
                            throw Invalid("Instance MethodImpl body must be virtual.");
                        var slot = DeclarationSlot(implementation.MethodDeclaration, 0, typeHandle);
                        if (slot != FinalizerSlot.Ordinary)
                            throw Invalid(slot == FinalizerSlot.Finalizer
                                ? "Author finalizers are unsupported (MethodImpl finalizer slot)."
                                : "Unresolved finalizer MethodImpl metadata is unsupported.");
                    }
                    catch (Exception error) when (error is InvalidDataException or BadImageFormatException or
                        ArgumentException or InvalidOperationException or IndexOutOfRangeException)
                    {
                        throw FinalizerMetadataError(typeHandle, implementationHandle, bodyDescription, error);
                    }
                }
                foreach (var methodHandle in type.GetMethods())
                {
                    var method = metadata.GetMethodDefinition(methodHandle);
                    var methodName = metadata.GetString(method.Name);
                    if (methodName != "Finalize" &&
                        (method.Attributes & (MethodAttributes.Virtual | MethodAttributes.NewSlot)) != MethodAttributes.Virtual)
                        continue;
                    try
                    {
                        var slot = MethodSlot(methodHandle, 0);
                        if (slot != FinalizerSlot.Ordinary)
                            throw Invalid(slot == FinalizerSlot.Finalizer
                                ? "Author finalizers are unsupported (object finalizer slot)."
                                : "Unresolved finalizer slot metadata is unsupported.");
                    }
                    catch (Exception error) when (error is InvalidDataException or BadImageFormatException or
                        ArgumentException or InvalidOperationException or IndexOutOfRangeException)
                    {
                        throw FinalizerMetadataError(typeHandle, methodHandle, Identifier(method.Name), error);
                    }
                }
            }
            // A malformed Class column/sort order must not hide a MethodImpl from the per-type
            // enumeration and thereby turn an explicit finalizer body into an ordinary method.
            for (var row = 1; row <= metadata.GetTableRowCount(TableIndex.MethodImpl); row++)
            {
                var handle = MetadataTokens.MethodImplementationHandle(row);
                if (!implementations.Contains(handle))
                    throw Invalid($"Type '<unresolved>', method 'MethodImpl', metadata token 0x{MetadataTokens.GetToken(handle):X8}: Unowned or unsorted MethodImpl metadata is unsupported.");
            }
        }

        private InvalidDataException FinalizerMetadataError(TypeDefinitionHandle type, EntityHandle token,
            string method, Exception error) => Invalid(
                $"Type '{DefinitionTypeName(type, 0)}', method '{method}', metadata token 0x{MetadataTokens.GetToken(token):X8}: {error.Message}");

        private FinalizerSlot MethodSlot(MethodDefinitionHandle handle, int nesting)
        {
            if (nesting > 64) return FinalizerSlot.Unknown;
            if (finalizerSlots.TryGetValue(handle, out var cached)) return cached;
            if (!resolvingFinalizerSlots.Add(handle)) return FinalizerSlot.Unknown;
            try
            {
                var slot = ResolveMethodSlot(handle, nesting);
                finalizerSlots.Add(handle, slot);
                return slot;
            }
            finally { resolvingFinalizerSlots.Remove(handle); }
        }

        private FinalizerSlot ResolveMethodSlot(MethodDefinitionHandle handle, int nesting)
        {
            var method = metadata.GetMethodDefinition(handle);
            CheckBlob(method.Signature);
            var signature = method.DecodeSignature(this, null);
            CheckSignature(signature);
            if (signature.Header.IsInstance == ((method.Attributes & MethodAttributes.Static) != 0) ||
                signature.GenericParameterCount != method.GetGenericParameters().Count ||
                (method.Attributes & (MethodAttributes.Virtual | MethodAttributes.Static)) ==
                (MethodAttributes.Virtual | MethodAttributes.Static) &&
                (metadata.GetTypeDefinition(method.GetDeclaringType()).Attributes & TypeAttributes.Interface) == 0)
                return FinalizerSlot.Unknown;

            // Explicit overrides can give an object finalizer any body name, including a newslot
            // name. Follow MethodImpl before considering the implicit name/signature/slot rules.
            foreach (var handleImpl in metadata.GetTypeDefinition(method.GetDeclaringType()).GetMethodImplementations())
            {
                var implementation = metadata.GetMethodImplementation(handleImpl);
                if (LocalMethod(implementation.MethodBody) != handle) continue;
                var slot = DeclarationSlot(implementation.MethodDeclaration, nesting + 1, method.GetDeclaringType());
                if (slot != FinalizerSlot.Ordinary) return slot;
            }

            if (!FinalizerSignature(signature) ||
                (method.Attributes & MethodAttributes.Virtual) == 0)
                return FinalizerSlot.Ordinary;
            var name = metadata.GetString(method.Name);
            if (name != "Finalize" && (method.Attributes & MethodAttributes.NewSlot) != 0)
                return FinalizerSlot.Ordinary;
            if (!CanonicalFinalizerSignature(method.Signature)) return FinalizerSlot.Unknown;
            if ((method.Attributes & MethodAttributes.NewSlot) != 0) return FinalizerSlot.Ordinary;

            return InheritedSlot(metadata.GetTypeDefinition(method.GetDeclaringType()).BaseType, name, nesting + 1);
        }

        private static bool FinalizerSignature(MethodSignature<Shape> signature) =>
            signature.Header.IsInstance && signature.GenericParameterCount == 0 &&
            signature.ParameterTypes.Length == 0 && signature.ReturnType.SignatureName == "System.Void";

        private bool CanonicalFinalizerSignature(BlobHandle signature) =>
            metadata.GetBlobBytes(signature).AsSpan().SequenceEqual(new byte[] { 0x20, 0x00, 0x01 });

        private FinalizerSlot InheritedSlot(EntityHandle typeHandle, string name, int nesting)
        {
            if (nesting > 64 || typeHandle.IsNil) return FinalizerSlot.Unknown;
            typeHandle = SlotTypeDefinition(typeHandle);
            if (typeHandle.Kind == HandleKind.TypeDefinition)
            {
                var type = metadata.GetTypeDefinition((TypeDefinitionHandle)typeHandle);
                if ((type.Attributes & TypeAttributes.Interface) != 0) return FinalizerSlot.Unknown;
                MethodDefinitionHandle match = default;
                foreach (var handle in type.GetMethods())
                {
                    var method = metadata.GetMethodDefinition(handle);
                    if (metadata.GetString(method.Name) == name &&
                        (method.Attributes & MethodAttributes.Virtual) != 0)
                    {
                        CheckBlob(method.Signature);
                        var signature = method.DecodeSignature(this, null);
                        CheckSignature(signature);
                        if (!FinalizerSignature(signature)) continue;
                        if (!match.IsNil || !CanonicalFinalizerSignature(method.Signature))
                            return FinalizerSlot.Unknown;
                        match = handle;
                    }
                }
                return match.IsNil ? InheritedSlot(type.BaseType, name, nesting + 1) : MethodSlot(match, nesting + 1);
            }
            if (typeHandle.Kind == HandleKind.TypeReference)
            {
                var type = Type(typeHandle);
                if (type.Name == "System.Object" && IsTrustedBclAssembly(type.Assembly))
                    return name == "Finalize" ? FinalizerSlot.Finalizer : FinalizerSlot.Ordinary;
            }
            // External base layouts cannot be proved from the current image.
            return FinalizerSlot.Unknown;
        }

        private FinalizerSlot DeclarationSlot(EntityHandle declaration, int nesting, TypeDefinitionHandle owner)
        {
            if (nesting > 64 || declaration.IsNil) return FinalizerSlot.Unknown;
            if (declaration.Kind == HandleKind.MethodDefinition)
            {
                var method = metadata.GetMethodDefinition((MethodDefinitionHandle)declaration);
                return (method.Attributes & MethodAttributes.Virtual) != 0
                    ? MethodSlot((MethodDefinitionHandle)declaration, nesting + 1) : FinalizerSlot.Unknown;
            }
            if (declaration.Kind != HandleKind.MemberReference) return FinalizerSlot.Unknown;
            var member = metadata.GetMemberReference((MemberReferenceHandle)declaration);
            if (member.GetKind() != MemberReferenceKind.Method) return FinalizerSlot.Unknown;
            CheckBlob(member.Signature);
            var signature = member.DecodeMethodSignature(this, null);
            CheckSignature(signature);
            if (SlotTypeDefinition(member.Parent).Kind == HandleKind.TypeDefinition)
                return DeclarationSlot(LocalMethod(declaration), nesting + 1, owner);
            if (!FinalizerSignature(signature)) return FinalizerSlot.Ordinary;
            if (!CanonicalFinalizerSignature(member.Signature)) return FinalizerSlot.Unknown;
            var parent = Type(member.Parent);
            if (parent.Name == "System.Object" && IsTrustedBclAssembly(parent.Assembly))
                return metadata.GetString(member.Name) == "Finalize" ? FinalizerSlot.Finalizer : FinalizerSlot.Unknown;
            // A class can expose its finalizer slot under another name via MethodImpl. A
            // void() declaration on an unresolved external class is therefore not proof of
            // an ordinary slot. Interface mappings have no Object finalizer vtable slot.
            return DeclaresInterface(owner, member.Parent, 0) ? FinalizerSlot.Ordinary : FinalizerSlot.Unknown;
        }

        private bool DeclaresInterface(TypeDefinitionHandle owner, EntityHandle target, int nesting)
        {
            if (nesting > 64) return false;
            var type = metadata.GetTypeDefinition(owner);
            foreach (var handle in type.GetInterfaceImplementations())
            {
                // Exact metadata identity avoids flattening a nested name into an ambiguous
                // display string containing '+'. Duplicate/unresolved references stay unknown.
                if (metadata.GetInterfaceImplementation(handle).Interface == target)
                    return true;
            }
            if (type.BaseType.IsNil) return false;
            var parent = SlotTypeDefinition(type.BaseType);
            return parent.Kind == HandleKind.TypeDefinition &&
                DeclaresInterface((TypeDefinitionHandle)parent, target, nesting + 1);
        }

        private MethodDefinitionHandle LocalMethod(EntityHandle handle)
        {
            if (!handle.IsNil && handle.Kind == HandleKind.MethodDefinition)
            {
                _ = metadata.GetMethodDefinition((MethodDefinitionHandle)handle).Name;
                return (MethodDefinitionHandle)handle;
            }
            if (!handle.IsNil && handle.Kind == HandleKind.MemberReference)
            {
                var member = metadata.GetMemberReference((MemberReferenceHandle)handle);
                var parent = SlotTypeDefinition(member.Parent);
                if (parent.Kind == HandleKind.TypeDefinition && member.GetKind() == MemberReferenceKind.Method)
                {
                    CheckBlob(member.Signature);
                    var matches = metadata.GetTypeDefinition((TypeDefinitionHandle)parent).GetMethods()
                        .Where(candidate =>
                        {
                            var method = metadata.GetMethodDefinition(candidate);
                            CheckBlob(method.Signature);
                            return metadata.StringComparer.Equals(method.Name, metadata.GetString(member.Name)) &&
                                metadata.GetBlobBytes(method.Signature).AsSpan().SequenceEqual(metadata.GetBlobBytes(member.Signature));
                        }).Take(2).ToArray();
                    if (matches.Length == 1) return matches[0];
                }
            }
            throw Invalid("Unresolved or ambiguous MethodImpl method metadata.");
        }

        private EntityHandle SlotTypeDefinition(EntityHandle type)
        {
            if (type.Kind != HandleKind.TypeSpecification) return type;
            // Finalizer slot matching is instance void(), so class type arguments cannot
            // change that signature. Prove the complete local class instantiation, rather
            // than relying on a decoder that accepts trailing data or ignores class arity.
            _ = Type(type);
            var signature = metadata.GetTypeSpecification((TypeSpecificationHandle)type).Signature;
            CheckBlob(signature);
            var blob = metadata.GetBlobReader(signature);
            if (blob.ReadByte() != 0x15 /* GENERICINST */ || blob.ReadByte() != 0x12 /* CLASS */)
                throw Invalid("Unresolved finalizer generic type shape.");
            var definition = blob.ReadTypeHandle();
            if (definition.Kind != HandleKind.TypeDefinition) return type;
            var count = blob.ReadCompressedInteger();
            if (count != metadata.GetTypeDefinition((TypeDefinitionHandle)definition).GetGenericParameters().Count)
                throw Invalid("Unresolved finalizer generic type arity.");
            var decoder = new SignatureDecoder<Shape, object?>(this, metadata, null);
            for (var argument = 0; argument < count; argument++) _ = decoder.DecodeType(ref blob);
            if (blob.RemainingBytes != 0) throw Invalid("Trailing finalizer generic type metadata.");
            return definition;
        }
    }
}
