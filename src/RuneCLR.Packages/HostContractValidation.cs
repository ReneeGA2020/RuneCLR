using System.Collections.Immutable;
using System.Reflection.Emit;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;

namespace RuneCLR.Packages;

public static partial class GameplayCapabilityPolicy
{
    public static void ValidateHostContract(ReadOnlyMemory<byte> image, string entryType, string interfaceFullName,
        IReadOnlyCollection<string> allowedMethods) =>
        ValidateHostContract(image, entryType, interfaceFullName, allowedMethods, Array.Empty<byte[]>());

    public static void ValidateHostContract(ReadOnlyMemory<byte> image, string entryType, string interfaceFullName,
        IReadOnlyCollection<string> allowedMethods, IReadOnlyCollection<byte[]> privateImages)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(entryType);
        ArgumentException.ThrowIfNullOrWhiteSpace(interfaceFullName);
        ArgumentNullException.ThrowIfNull(allowedMethods);
        ArgumentNullException.ThrowIfNull(privateImages);
        if (image.IsEmpty || image.Length > ManagedAssemblyInspector.MaximumImageBytes)
            throw HostInvalid("Provide a nonempty assembly within the managed-IL image limit.");
        var allowed = new HashSet<string>(allowedMethods, StringComparer.Ordinal);
        var readers = new List<PEReader>();
        try
        {
            var entryPe = OpenHostImage(image);
            readers.Add(entryPe);
            var entryReader = entryPe.GetMetadataReader(MetadataReaderOptions.None);
            var entryName = entryReader.GetString(entryReader.GetAssemblyDefinition().Name);
            var privateAssemblies = new Dictionary<string, HostImage>(StringComparer.OrdinalIgnoreCase);
            foreach (var privateImage in privateImages)
            {
                if (privateImage is null || privateImage.Length == 0 || privateImage.Length > ManagedAssemblyInspector.MaximumImageBytes)
                    throw HostInvalid("Provide a nonempty assembly within the managed-IL image limit.");
                var pe = OpenHostImage(privateImage);
                readers.Add(pe);
                var reader = pe.GetMetadataReader(MetadataReaderOptions.None);
                var name = reader.GetString(reader.GetAssemblyDefinition().Name);
                if (string.Equals(name, entryName, StringComparison.OrdinalIgnoreCase) ||
                    !privateAssemblies.TryAdd(name, new HostImage(reader, pe)))
                    throw new InvalidDataException("Duplicate private dependency identity: " + name + ".");
            }

            var entry = FindHostEntry(entryReader, entryType);
            var startMethod = FindHostOnStart(entryReader, entry);
            RequireHostParameter(entryReader, startMethod, interfaceFullName);
            if (startMethod.RelativeVirtualAddress == 0)
                throw HostInvalid("OnStart has no managed body.");
            var il = entryPe.GetMethodBody(startMethod.RelativeVirtualAddress).GetILBytes()
                ?? throw HostInvalid("OnStart has no IL.");
            var walk = new HostWalk(entryReader, entryPe, interfaceFullName, allowed, privateAssemblies);
            walk.Seen.Add(entryName + " " + entryType + " OnStart");
            WalkHostCalls(walk, il);
        }
        catch (InvalidDataException)
        {
            throw;
        }
        catch (Exception error) when (error is BadImageFormatException or ArgumentException or
            InvalidOperationException or IndexOutOfRangeException or OverflowException)
        {
            throw HostInvalid(error.Message);
        }
        finally
        {
            foreach (var reader in readers) reader.Dispose();
        }
    }

    private readonly record struct HostImage(MetadataReader Reader, PEReader Pe);

    private sealed class HostWalk
    {
        public HostWalk(MetadataReader reader, PEReader pe, string interfaceName, HashSet<string> allowed,
            Dictionary<string, HostImage> privateAssemblies, HashSet<string>? seen = null)
        {
            Reader = reader;
            Pe = pe;
            InterfaceName = interfaceName;
            Allowed = allowed;
            PrivateAssemblies = privateAssemblies;
            Seen = seen ?? new HashSet<string>(StringComparer.Ordinal);
        }

        public MetadataReader Reader { get; }
        public PEReader Pe { get; }
        public string InterfaceName { get; }
        public HashSet<string> Allowed { get; }
        public Dictionary<string, HostImage> PrivateAssemblies { get; }
        public HashSet<string> Seen { get; }

        public HostWalk With(HostImage image) =>
            new(image.Reader, image.Pe, InterfaceName, Allowed, PrivateAssemblies, Seen);
    }

    private static PEReader OpenHostImage(ReadOnlyMemory<byte> image) =>
        new(ImmutableArray.CreateRange(image.Span.ToArray()));

    private static void WalkHostCalls(HostWalk walk, byte[] il)
    {
        var index = 0;
        while (index < il.Length)
        {
            var operation = ReadHostOpCode(il, ref index);
            if (operation.Value == OpCodes.Call.Value || operation.Value == OpCodes.Callvirt.Value)
                CheckHostCall(walk, ReadHostInt32(il, ref index));
            else if (operation.Value == OpCodes.Calli.Value || operation.Value == OpCodes.Newobj.Value || operation.Value == OpCodes.Jmp.Value)
                throw HostInvalid("OnStart uses an unsupported call.");
            else
                SkipHostOperand(operation, il, ref index);
        }
    }

    private static void CheckHostCall(HostWalk walk, int token)
    {
        var handle = MetadataTokens.EntityHandle(token);
        if (handle.Kind == HandleKind.MethodSpecification)
            throw HostInvalid("OnStart calls a generic method.");
        if (handle.Kind == HandleKind.MethodDefinition)
        {
            var method = walk.Reader.GetMethodDefinition((MethodDefinitionHandle)handle);
            WalkAuthorMethod(walk, new HostImage(walk.Reader, walk.Pe), method);
            return;
        }

        if (handle.Kind != HandleKind.MemberReference)
            throw HostInvalid("OnStart calls a method that is not declared by the host interface.");
        var member = walk.Reader.GetMemberReference((MemberReferenceHandle)handle);
        if (member.GetKind() != MemberReferenceKind.Method)
            throw HostInvalid("OnStart calls a non-method member.");
        var name = walk.Reader.GetString(member.Name);
        if (member.Parent.Kind == HandleKind.TypeDefinition)
        {
            var defined = walk.Reader.GetTypeDefinition((TypeDefinitionHandle)member.Parent);
            var definedName = HostTypeName(walk.Reader, defined.Namespace, defined.Name);
            WalkAuthorMethod(walk, new HostImage(walk.Reader, walk.Pe), FindSingleMethod(walk.Reader, definedName, name));
            return;
        }

        if (member.Parent.Kind == HandleKind.TypeReference)
        {
            var type = walk.Reader.GetTypeReference((TypeReferenceHandle)member.Parent);
            var parent = HostTypeName(walk.Reader, type.Namespace, type.Name);
            if (string.Equals(parent, walk.InterfaceName, StringComparison.Ordinal))
            {
                if (!walk.Allowed.Contains(name)) throw HostInvalid(parent + "." + name);
                return;
            }

            if (type.ResolutionScope.Kind == HandleKind.AssemblyReference)
            {
                var assembly = walk.Reader.GetAssemblyReference((AssemblyReferenceHandle)type.ResolutionScope);
                var assemblyName = walk.Reader.GetString(assembly.Name);
                if (walk.PrivateAssemblies.TryGetValue(assemblyName, out var target))
                {
                    WalkAuthorMethod(walk.With(target), target, FindSingleMethod(target.Reader, parent, name));
                    return;
                }
            }

            throw HostInvalid(parent + "." + name);
        }

        throw HostInvalid(HostParentName(walk.Reader, member.Parent) + "." + name);
    }

    private static void WalkAuthorMethod(HostWalk walk, HostImage image, MethodDefinition method)
    {
        var reader = image.Reader;
        if (method.GetGenericParameters().Count != 0)
            throw HostInvalid("OnStart calls a generic method.");
        var type = reader.GetTypeDefinition(method.GetDeclaringType());
        foreach (var handle in type.GetMethods())
        {
            if (reader.GetString(reader.GetMethodDefinition(handle).Name) == ".cctor")
                throw HostInvalid("A called author type declares a type initializer.");
        }

        var typeName = HostTypeName(reader, type.Namespace, type.Name);
        var methodName = reader.GetString(method.Name);
        var assemblyName = reader.GetString(reader.GetAssemblyDefinition().Name);
        if (!walk.Seen.Add(assemblyName + " " + typeName + " " + methodName)) return;
        if (method.RelativeVirtualAddress == 0)
            throw HostInvalid("OnStart calls a method with no managed body.");
        var il = image.Pe.GetMethodBody(method.RelativeVirtualAddress).GetILBytes()
            ?? throw HostInvalid("OnStart has no IL.");
        WalkHostCalls(walk.With(image), il);
    }

    private static MethodDefinition FindSingleMethod(MetadataReader reader, string typeFullName, string methodName)
    {
        MethodDefinition? found = null;
        foreach (var handle in reader.TypeDefinitions)
        {
            var type = reader.GetTypeDefinition(handle);
            if (!string.Equals(HostTypeName(reader, type.Namespace, type.Name), typeFullName, StringComparison.Ordinal)) continue;
            foreach (var methodHandle in type.GetMethods())
            {
                var method = reader.GetMethodDefinition(methodHandle);
                if (reader.GetString(method.Name) != methodName) continue;
                if (found is not null) throw HostInvalid(typeFullName + "." + methodName + " is ambiguous.");
                found = method;
            }
        }

        return found ?? throw HostInvalid(typeFullName + "." + methodName);
    }

    private static string HostTypeName(MetadataReader reader, StringHandle namespaceName, StringHandle typeName)
    {
        var name = reader.GetString(namespaceName);
        var type = reader.GetString(typeName);
        return name.Length == 0 ? type : name + "." + type;
    }

    private static InvalidDataException HostInvalid(string detail)
    {
        var message = "Capability profile 'host-contract': OnStart calls a method that is not a host contract member.";
        if (!string.IsNullOrWhiteSpace(detail)) message += " " + detail;
        return new InvalidDataException(message);
    }

    private static TypeDefinition FindHostEntry(MetadataReader reader, string entryType)
    {
        TypeDefinition? found = null;
        foreach (var handle in reader.TypeDefinitions)
        {
            var definition = reader.GetTypeDefinition(handle);
            if (!definition.GetDeclaringType().IsNil) continue;
            var full = HostTypeName(reader, definition.Namespace, definition.Name);
            if (!string.Equals(full, entryType, StringComparison.Ordinal)) continue;
            if (found is not null) throw HostInvalid("The entry type is duplicated.");
            found = definition;
        }

        return found ?? throw HostInvalid("The entry type was not found.");
    }

    private static MethodDefinition FindHostOnStart(MetadataReader reader, TypeDefinition entry)
    {
        MethodDefinition? found = null;
        foreach (var handle in entry.GetMethods())
        {
            var method = reader.GetMethodDefinition(handle);
            if (reader.GetString(method.Name) != "OnStart") continue;
            if (found is not null) throw HostInvalid("OnStart is duplicated.");
            found = method;
        }

        return found ?? throw HostInvalid("OnStart was not found.");
    }

    private static void RequireHostParameter(MetadataReader reader, MethodDefinition start, string interfaceFullName)
    {
        var blob = reader.GetBlobReader(start.Signature);
        var header = blob.ReadSignatureHeader();
        if (!header.IsInstance || header.IsGeneric)
            throw HostInvalid("OnStart must be an instance method.");
        if (blob.ReadCompressedInteger() != 1)
            throw HostInvalid("OnStart must take exactly one parameter.");
        if (blob.ReadCompressedInteger() != 0x01)
            throw HostInvalid("OnStart must return void.");
        var element = blob.ReadCompressedInteger();
        if (element != 0x11 && element != 0x12)
            throw HostInvalid("OnStart parameter is not the host interface.");
        var coded = blob.ReadCompressedInteger();
        var name = HostCodedTypeName(reader, coded);
        if (!string.Equals(name, interfaceFullName, StringComparison.Ordinal))
            throw HostInvalid("OnStart parameter is " + name + ".");
    }

    private static string HostCodedTypeName(MetadataReader reader, int coded)
    {
        var tag = coded & 0x3;
        var row = coded >> 2;
        if (tag == 1)
        {
            var type = reader.GetTypeReference(MetadataTokens.TypeReferenceHandle(row));
            return HostTypeName(reader, type.Namespace, type.Name);
        }

        if (tag == 0)
        {
            var type = reader.GetTypeDefinition(MetadataTokens.TypeDefinitionHandle(row));
            return HostTypeName(reader, type.Namespace, type.Name);
        }

        throw HostInvalid("OnStart parameter is not the host interface.");
    }

    private static string HostParentName(MetadataReader reader, EntityHandle parent)
    {
        if (parent.Kind == HandleKind.TypeReference)
        {
            var type = reader.GetTypeReference((TypeReferenceHandle)parent);
            var name = reader.GetString(type.Namespace);
            var typeName = reader.GetString(type.Name);
            return name.Length == 0 ? typeName : name + "." + typeName;
        }

        if (parent.Kind == HandleKind.TypeDefinition)
        {
            var type = reader.GetTypeDefinition((TypeDefinitionHandle)parent);
            var name = reader.GetString(type.Namespace);
            var typeName = reader.GetString(type.Name);
            return name.Length == 0 ? typeName : name + "." + typeName;
        }

        throw HostInvalid("OnStart calls a method with an unsupported declaring type.");
    }

    private static OpCode ReadHostOpCode(byte[] il, ref int index)
    {
        if (index >= il.Length) throw HostInvalid("OnStart IL ended early.");
        var first = il[index++];
        var value = (short)first;
        if (first == 0xFE)
        {
            if (index >= il.Length) throw HostInvalid("OnStart IL ended early.");
            value = (short)(0xFE00 | il[index++]);
        }

        foreach (var field in typeof(OpCodes).GetFields(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static))
        {
            if (field.FieldType != typeof(OpCode)) continue;
            var operation = (OpCode)field.GetValue(null)!;
            if (operation.Value == value) return operation;
        }

        throw HostInvalid("OnStart contains an unknown instruction.");
    }

    private static int ReadHostInt32(byte[] il, ref int index)
    {
        if (index + 4 > il.Length) throw HostInvalid("OnStart IL ended early.");
        var value = BitConverter.ToInt32(il, index);
        index += 4;
        return value;
    }

    private static void SkipHostOperand(OpCode operation, byte[] il, ref int index)
    {
        switch (operation.OperandType)
        {
            case OperandType.InlineNone:
                return;
            case OperandType.ShortInlineBrTarget:
            case OperandType.ShortInlineI:
            case OperandType.ShortInlineVar:
                index += 1;
                break;
            case OperandType.InlineVar:
                index += 2;
                break;
            case OperandType.InlineBrTarget:
            case OperandType.InlineField:
            case OperandType.InlineI:
            case OperandType.InlineMethod:
            case OperandType.InlineSig:
            case OperandType.InlineString:
            case OperandType.InlineTok:
            case OperandType.InlineType:
            case OperandType.ShortInlineR:
                index += 4;
                break;
            case OperandType.InlineI8:
            case OperandType.InlineR:
                index += 8;
                break;
            case OperandType.InlineSwitch:
                var count = ReadHostInt32(il, ref index);
                index += count * 4;
                break;
            default:
                throw HostInvalid("OnStart contains an unsupported instruction.");
        }

        if (index > il.Length) throw HostInvalid("OnStart IL ended early.");
    }
}
