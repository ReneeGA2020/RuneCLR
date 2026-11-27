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

        private void ValidateFinalizerSlots()
        {
            foreach (var typeHandle in metadata.TypeDefinitions)
            {
                var type = metadata.GetTypeDefinition(typeHandle);
                foreach (var implementationHandle in type.GetMethodImplementations())
                {
                    var bodyDescription = "MethodImpl";
                    try
                    {
                        var implementation = metadata.GetMethodImplementation(implementationHandle);
                        var bodyHandle = LocalMethod(implementation.MethodBody);
                        var body = metadata.GetMethodDefinition(bodyHandle);
                        bodyDescription = $"{Identifier(body.Name)} (body 0x{MetadataTokens.GetToken(bodyHandle):X8}, MethodImpl)";
                        if (body.GetDeclaringType() != typeHandle ||
                            (body.Attributes & (MethodAttributes.Virtual | MethodAttributes.Static)) != MethodAttributes.Virtual)
                            throw Invalid("MethodImpl body must be an instance virtual method on its declaring type.");
                        var slot = DeclarationSlot(implementation.MethodDeclaration, 0);
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
                    if (metadata.GetString(method.Name) != "Finalize") continue;
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
                        throw FinalizerMetadataError(typeHandle, methodHandle, "Finalize", error);
                    }
                }
            }
        }

        private InvalidDataException FinalizerMetadataError(TypeDefinitionHandle type, EntityHandle token,
            string method, Exception error) => Invalid(
                $"Type '{DefinitionTypeName(type, 0)}', method '{method}', metadata token 0x{MetadataTokens.GetToken(token):X8}: {error.Message}");

        private FinalizerSlot MethodSlot(MethodDefinitionHandle handle, int nesting)
        {
            if (nesting > 64) return FinalizerSlot.Unknown;
            var method = metadata.GetMethodDefinition(handle);
            CheckBlob(method.Signature);
            var signature = method.DecodeSignature(this, null);
            CheckSignature(signature);
            if (signature.Header.IsInstance == ((method.Attributes & MethodAttributes.Static) != 0) ||
                signature.GenericParameterCount != method.GetGenericParameters().Count ||
                (method.Attributes & (MethodAttributes.Virtual | MethodAttributes.Static)) ==
                (MethodAttributes.Virtual | MethodAttributes.Static))
                return FinalizerSlot.Unknown;

            // Explicit overrides can give an object finalizer any body name, including a newslot
            // name. Follow MethodImpl before considering the implicit name/signature/slot rules.
            foreach (var handleImpl in metadata.GetTypeDefinition(method.GetDeclaringType()).GetMethodImplementations())
            {
                var implementation = metadata.GetMethodImplementation(handleImpl);
                if (LocalMethod(implementation.MethodBody) != handle) continue;
                var slot = DeclarationSlot(implementation.MethodDeclaration, nesting + 1);
                if (slot != FinalizerSlot.Ordinary) return slot;
            }

            if (metadata.GetString(method.Name) != "Finalize" || !FinalizerSignature(signature) ||
                (method.Attributes & MethodAttributes.Virtual) == 0 ||
                (method.Attributes & MethodAttributes.NewSlot) != 0)
                return FinalizerSlot.Ordinary;

            return InheritedSlot(metadata.GetTypeDefinition(method.GetDeclaringType()).BaseType, nesting + 1);
        }

        private static bool FinalizerSignature(MethodSignature<Shape> signature) =>
            signature.Header.IsInstance && signature.GenericParameterCount == 0 &&
            signature.ParameterTypes.Length == 0 && signature.ReturnType.SignatureName == "System.Void";

        private FinalizerSlot InheritedSlot(EntityHandle typeHandle, int nesting)
        {
            if (nesting > 64 || typeHandle.IsNil) return FinalizerSlot.Unknown;
            if (typeHandle.Kind == HandleKind.TypeDefinition)
            {
                var type = metadata.GetTypeDefinition((TypeDefinitionHandle)typeHandle);
                if ((type.Attributes & TypeAttributes.Interface) != 0) return FinalizerSlot.Unknown;
                foreach (var handle in type.GetMethods())
                {
                    var method = metadata.GetMethodDefinition(handle);
                    if (metadata.GetString(method.Name) == "Finalize" &&
                        (method.Attributes & MethodAttributes.Virtual) != 0)
                    {
                        CheckBlob(method.Signature);
                        if (FinalizerSignature(method.DecodeSignature(this, null)))
                            return MethodSlot(handle, nesting + 1);
                    }
                }
                return InheritedSlot(type.BaseType, nesting + 1);
            }
            if (typeHandle.Kind == HandleKind.TypeReference)
            {
                var type = Type(typeHandle);
                if (type.Name == "System.Object" && IsTrustedBclAssembly(type.Assembly))
                    return FinalizerSlot.Finalizer;
            }
            // TypeSpec/external base layouts cannot be proved from the current image.
            return FinalizerSlot.Unknown;
        }

        private FinalizerSlot DeclarationSlot(EntityHandle declaration, int nesting)
        {
            if (nesting > 64 || declaration.IsNil) return FinalizerSlot.Unknown;
            if (declaration.Kind == HandleKind.MethodDefinition)
                return MethodSlot((MethodDefinitionHandle)declaration, nesting + 1);
            if (declaration.Kind != HandleKind.MemberReference) return FinalizerSlot.Unknown;
            var member = metadata.GetMemberReference((MemberReferenceHandle)declaration);
            if (member.GetKind() != MemberReferenceKind.Method) return FinalizerSlot.Unknown;
            CheckBlob(member.Signature);
            var signature = member.DecodeMethodSignature(this, null);
            CheckSignature(signature);
            if (member.Parent.Kind == HandleKind.TypeDefinition)
                return MethodSlot(LocalMethod(declaration), nesting + 1);
            if (metadata.GetString(member.Name) != "Finalize") return FinalizerSlot.Ordinary;
            if (!FinalizerSignature(signature)) return FinalizerSlot.Unknown;
            var parent = Type(member.Parent);
            return parent.Name == "System.Object" && IsTrustedBclAssembly(parent.Assembly)
                ? FinalizerSlot.Finalizer : FinalizerSlot.Unknown;
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
                if (member.Parent.Kind == HandleKind.TypeDefinition && member.GetKind() == MemberReferenceKind.Method)
                {
                    CheckBlob(member.Signature);
                    var matches = metadata.GetTypeDefinition((TypeDefinitionHandle)member.Parent).GetMethods()
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
    }
}
