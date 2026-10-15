using System.Reflection.Metadata;
using System.Collections.Immutable;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text.Json;

// Parse PE metadata with the host SDK. Never load the inspected assembly.
if (args.Length == 0) throw new ArgumentException("Supply managed PE paths.");
var files = args.Select(Inspect).ToArray();
Console.WriteLine(JsonSerializer.Serialize(files, new JsonSerializerOptions { WriteIndented = true }));

static object Inspect(string input)
{
    string path = Path.GetFullPath(input);
    byte[] bytes = File.ReadAllBytes(path);
    using var stream = new MemoryStream(bytes, writable: false);
    using var pe = new PEReader(stream);
    MetadataReader metadata = pe.GetMetadataReader();
    var methods = new List<object>();
    var fields = new List<object>();
    foreach (var handle in metadata.TypeDefinitions)
    {
        var type = metadata.GetTypeDefinition(handle);
        string owner = TypeName(metadata, handle);
        foreach (var methodHandle in type.GetMethods())
        {
            var method = metadata.GetMethodDefinition(methodHandle);
            string name = metadata.GetString(method.Name);
            var import = method.GetImport();
            string entry = import.Name.IsNil ? "" : metadata.GetString(import.Name);
            if (!name.StartsWith("RuneCLR_", StringComparison.Ordinal) &&
                name != "InitializeInterpreterRequiredLoadContext" &&
                name != "InitializeInstructionMeteredLoadContext" &&
                name != "InitializeTerminalPrototypeLoadContext" &&
                name != "RuneCLRIsTerminatedFrameOwner" &&
                !owner.EndsWith("+RuneCLRInterpreterLoadContext", StringComparison.Ordinal) &&
                !entry.StartsWith("AssemblyNative_RuneCLR", StringComparison.Ordinal) &&
                entry != "AssemblyNative_InitializeInterpreterRequiredLoadContext" &&
                entry != "AssemblyNative_InitializeInstructionMeteredLoadContext" &&
                entry != "AssemblyNative_InitializeTerminalPrototypeLoadContext" &&
                entry != "GCInterface_RuneCLRGetTerminalFinalizerBoundaryVersion" &&
                entry != "GCInterface_RuneCLRIsTerminatedFinalizerOwner" &&
                entry != "RuneCLRIsTerminatedFrameOwner") continue;
            var decoded = method.DecodeSignature(new InspectorTypeProvider(), genericContext: (object?)null);
            methods.Add(new { owner, name, token = $"0x{MetadataTokens.GetToken(methodHandle):x8}",
                attributes = method.Attributes.ToString(), nativeEntry = entry,
                signatureHex = Convert.ToHexString(metadata.GetBlobBytes(method.Signature)),
                decodedReturnType = decoded.ReturnType, decodedParameterTypes = decoded.ParameterTypes });
        }
        foreach (var fieldHandle in type.GetFields())
        {
            var field = metadata.GetFieldDefinition(fieldHandle);
            string name = metadata.GetString(field.Name);
            if (name != "CORJIT_FLAG_INTERPRET_REQUIRED") continue;
            var constantHandle = field.GetDefaultValue();
            long? value = null;
            if (!constantHandle.IsNil)
            {
                var constant = metadata.GetConstant(constantHandle);
                var blob = metadata.GetBlobReader(constant.Value);
                value = constant.TypeCode switch
                {
                    ConstantTypeCode.Int32 => blob.ReadInt32(),
                    ConstantTypeCode.UInt32 => blob.ReadUInt32(),
                    ConstantTypeCode.Int64 => blob.ReadInt64(),
                    ConstantTypeCode.UInt64 => checked((long)blob.ReadUInt64()),
                    _ => throw new InvalidDataException("Unexpected CORJIT constant type.")
                };
            }
            fields.Add(new { owner, name, value, token = $"0x{MetadataTokens.GetToken(fieldHandle):x8}" });
        }
    }
    return new { path, sha256 = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),
        assembly = metadata.IsAssembly ? metadata.GetString(metadata.GetAssemblyDefinition().Name) : null,
        moduleVersionId = metadata.GetGuid(metadata.GetModuleDefinition().Mvid),
        managedNativeRva = pe.PEHeaders.CorHeader!.ManagedNativeHeaderDirectory.RelativeVirtualAddress,
        methods, fields };
}

static string TypeName(MetadataReader metadata, TypeDefinitionHandle handle)
{
    var type = metadata.GetTypeDefinition(handle);
    string name = metadata.GetString(type.Name);
    var parent = type.GetDeclaringType();
    if (!parent.IsNil) return TypeName(metadata, parent) + "+" + name;
    string ns = metadata.GetString(type.Namespace);
    return ns.Length == 0 ? name : ns + "." + name;
}

// Resolve actual TypeDef/TypeRef/TypeSpec identities rather than accepting a coded-token prefix.
// None of these operations loads the inspected CoreLib or resolves a runtime Type.
sealed class InspectorTypeProvider : ISignatureTypeProvider<string, object?>
{
    public string GetArrayType(string elementType, ArrayShape shape) => elementType + "[" + new string(',', shape.Rank - 1) + "]";
    public string GetByReferenceType(string elementType) => elementType + "&";
    public string GetFunctionPointerType(MethodSignature<string> signature) =>
        "methodptr(" + signature.ReturnType + ";" + string.Join(',', signature.ParameterTypes) + ")";
    public string GetGenericInstantiation(string genericType, ImmutableArray<string> typeArguments) =>
        genericType + "<" + string.Join(',', typeArguments) + ">";
    public string GetGenericMethodParameter(object? context, int index) => "!!" + index;
    public string GetGenericTypeParameter(object? context, int index) => "!" + index;
    public string GetModifiedType(string modifier, string unmodifiedType, bool isRequired) =>
        (isRequired ? "modreq(" : "modopt(") + modifier + ")" + unmodifiedType;
    public string GetPinnedType(string elementType) => "pinned " + elementType;
    public string GetPointerType(string elementType) => elementType + "*";
    public string GetPrimitiveType(PrimitiveTypeCode typeCode) => typeCode.ToString();
    public string GetSZArrayType(string elementType) => elementType + "[]";
    public string GetTypeFromDefinition(MetadataReader reader, TypeDefinitionHandle handle, byte rawTypeKind)
    {
        var type = reader.GetTypeDefinition(handle);
        var parent = type.GetDeclaringType();
        var name = reader.GetString(type.Name);
        if (!parent.IsNil) return GetTypeFromDefinition(reader, parent, rawTypeKind) + "+" + name;
        var ns = reader.GetString(type.Namespace);
        return ns.Length == 0 ? name : ns + "." + name;
    }
    public string GetTypeFromReference(MetadataReader reader, TypeReferenceHandle handle, byte rawTypeKind)
    {
        var type = reader.GetTypeReference(handle);
        var name = reader.GetString(type.Name);
        if (type.ResolutionScope.Kind == HandleKind.TypeReference)
            return GetTypeFromReference(reader, (TypeReferenceHandle)type.ResolutionScope, rawTypeKind) + "+" + name;
        var ns = reader.GetString(type.Namespace);
        return ns.Length == 0 ? name : ns + "." + name;
    }
    public string GetTypeFromSpecification(MetadataReader reader, object? context, TypeSpecificationHandle handle, byte rawTypeKind) =>
        reader.GetTypeSpecification(handle).DecodeSignature(this, context);
}

