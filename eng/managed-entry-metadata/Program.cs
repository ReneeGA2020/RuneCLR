using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text.Json;

if (args.Length == 0) throw new ArgumentException("Supply managed PE paths.");
var files = args.Select(Inspect).ToArray();
Console.WriteLine(JsonSerializer.Serialize(files, new JsonSerializerOptions { WriteIndented = true }));

static object Inspect(string path)
{
    byte[] bytes = File.ReadAllBytes(path);
    using var stream = new MemoryStream(bytes, writable: false);
    using var pe = new PEReader(stream);
    MetadataReader metadata = pe.GetMetadataReader();
    var methods = new List<object>();
    foreach (TypeDefinitionHandle handle in metadata.TypeDefinitions)
    {
        foreach (MethodDefinitionHandle methodHandle in metadata.GetTypeDefinition(handle).GetMethods())
        {
            MethodDefinition method = metadata.GetMethodDefinition(methodHandle);
            byte[]? il = method.RelativeVirtualAddress == 0 ? null : pe.GetMethodBody(method.RelativeVirtualAddress).GetILBytes();
            methods.Add(new { owner = Name(metadata, handle), name = metadata.GetString(method.Name),
                token = $"0x{MetadataTokens.GetToken(methodHandle):x8}", rva = method.RelativeVirtualAddress,
                ilBytes = il?.Length, ilSha256 = il is null ? null : Convert.ToHexString(SHA256.HashData(il)).ToLowerInvariant(),
                signatureHex = Convert.ToHexString(metadata.GetBlobBytes(method.Signature)) });
        }
    }
    return new { path = Path.GetFullPath(path), sha256 = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),
        assembly = metadata.GetString(metadata.GetAssemblyDefinition().Name),
        moduleMvid = metadata.GetGuid(metadata.GetModuleDefinition().Mvid),
        managedNativeRva = pe.PEHeaders.CorHeader!.ManagedNativeHeaderDirectory.RelativeVirtualAddress, methods };
}

static string Name(MetadataReader metadata, TypeDefinitionHandle handle)
{
    TypeDefinition type = metadata.GetTypeDefinition(handle);
    string name = metadata.GetString(type.Name);
    TypeDefinitionHandle parent = type.GetDeclaringType();
    if (!parent.IsNil) return Name(metadata, parent) + "+" + name;
    string ns = metadata.GetString(type.Namespace);
    return ns.Length == 0 ? name : ns + "." + name;
}

