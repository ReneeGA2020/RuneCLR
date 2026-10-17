using System.Collections.Immutable;
using System.Reflection.Emit;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;

namespace RuneCLR.Packages;

public static partial class GameplayCapabilityPolicy
{
    public static void ValidateHostContract(ReadOnlyMemory<byte> image, string entryType, string interfaceFullName,
        IReadOnlyCollection<string> allowedMethods)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(entryType);
        ArgumentException.ThrowIfNullOrWhiteSpace(interfaceFullName);
        ArgumentNullException.ThrowIfNull(allowedMethods);
        if (image.IsEmpty || image.Length > ManagedAssemblyInspector.MaximumImageBytes)
            throw HostInvalid("Provide a nonempty assembly within the managed-IL image limit.");
        var allowed = new HashSet<string>(allowedMethods, StringComparer.Ordinal);
        try
        {
            using var pe = new PEReader(ImmutableArray.CreateRange(image.ToArray()));
            var reader = pe.GetMetadataReader(MetadataReaderOptions.None);
            var entry = FindHostEntry(reader, entryType);
            var start = FindHostOnStart(reader, entry);
            RequireHostParameter(reader, start, interfaceFullName);
            if (start.RelativeVirtualAddress == 0)
                throw HostInvalid("OnStart has no managed body.");
            var il = pe.GetMethodBody(start.RelativeVirtualAddress).GetILBytes()
                ?? throw HostInvalid("OnStart has no IL.");
            WalkHostCalls(reader, il, interfaceFullName, allowed);
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
            var name = reader.GetString(definition.Namespace);
            var typeName = reader.GetString(definition.Name);
            var full = name.Length == 0 ? typeName : name + "." + typeName;
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
            var ns = reader.GetString(type.Namespace);
            var typeName = reader.GetString(type.Name);
            return ns.Length == 0 ? typeName : ns + "." + typeName;
        }

        if (tag == 0)
        {
            var type = reader.GetTypeDefinition(MetadataTokens.TypeDefinitionHandle(row));
            var ns = reader.GetString(type.Namespace);
            var typeName = reader.GetString(type.Name);
            return ns.Length == 0 ? typeName : ns + "." + typeName;
        }

        throw HostInvalid("OnStart parameter is not the host interface.");
    }
    private static void WalkHostCalls(MetadataReader reader, byte[] il, string interfaceFullName, HashSet<string> allowed)
    {
        var index = 0;
        while (index < il.Length)
        {
            var operation = ReadHostOpCode(il, ref index);
            if (operation.Value == OpCodes.Call.Value || operation.Value == OpCodes.Callvirt.Value)
            {
                CheckHostCall(reader, ReadHostInt32(il, ref index), interfaceFullName, allowed);
            }
            else if (operation.Value == OpCodes.Calli.Value || operation.Value == OpCodes.Newobj.Value || operation.Value == OpCodes.Jmp.Value)
            {
                throw HostInvalid("OnStart uses an unsupported call.");
            }
            else
            {
                SkipHostOperand(operation, il, ref index);
            }
        }
    }

    private static void CheckHostCall(MetadataReader reader, int token, string interfaceFullName, HashSet<string> allowed)
    {
        var handle = MetadataTokens.EntityHandle(token);
        if (handle.Kind != HandleKind.MemberReference)
            throw HostInvalid("OnStart calls a method that is not declared by the host interface.");
        var member = reader.GetMemberReference((MemberReferenceHandle)handle);
        if (member.GetKind() != MemberReferenceKind.Method)
            throw HostInvalid("OnStart calls a non-method member.");
        var name = reader.GetString(member.Name);
        var parent = HostParentName(reader, member.Parent);
        if (!string.Equals(parent, interfaceFullName, StringComparison.Ordinal) || !allowed.Contains(name))
            throw HostInvalid(parent + "." + name);
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
