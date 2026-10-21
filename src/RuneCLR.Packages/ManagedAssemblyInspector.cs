using System.Collections.Immutable;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;

namespace RuneCLR.Packages;

public sealed record ManagedAssemblyInfo(string AssemblyName, string SimpleName, string[] References);

/// <summary>Checks the initial managed-IL intake profile without loading input assemblies.
/// This is structural validation, not IL instruction/type/control-flow verification or a sandbox.</summary>
public static class ManagedAssemblyInspector
{
    public const int MaximumImageBytes = 32 * 1024 * 1024;

    public static ManagedAssemblyInfo Inspect(ReadOnlyMemory<byte> image) =>
        ReadImage(image, (_, metadata) =>
        {
            var definition = metadata.GetAssemblyDefinition();
            var identity = DefinitionIdentity(metadata);
            return new ManagedAssemblyInfo(identity, metadata.GetString(definition.Name),
                metadata.AssemblyReferences.Select(handle => ReferenceIdentity(metadata, handle)).ToArray());
        });

    public static ManagedAssemblyInfo Inspect(string path)
    {
        // Preserve path/access/read errors as normal I/O exceptions, and bound allocation before reading.
        using var stream = File.OpenRead(path);
        if (stream.Length > MaximumImageBytes)
            throw Invalid($"Assembly exceeds the {MaximumImageBytes}-byte managed-IL input limit.");
        var image = new byte[checked((int)stream.Length)];
        stream.ReadExactly(image);
        return Inspect(image);
    }

    public static void ValidateEntry(ReadOnlyMemory<byte> image, string entryType, string contractAssemblyIdentity, string? hostInterface = null) =>
        ReadImage(image, (_, metadata) =>
        {
            ValidateEntryType(metadata, entryType, contractAssemblyIdentity, hostInterface);
            return true;
        });

    private static T ReadImage<T>(ReadOnlyMemory<byte> image, Func<PEReader, MetadataReader, T> inspect)
    {
        if (image.IsEmpty || image.Length > MaximumImageBytes)
            throw Invalid($"Provide a nonempty managed assembly no larger than {MaximumImageBytes} bytes.");
        try
        {
            using var pe = new PEReader(ImmutableArray.CreateRange(image.ToArray()));
            ValidateImage(pe, image.Length);
            var metadata = pe.GetMetadataReader(MetadataReaderOptions.None);
            if (!metadata.IsAssembly)
                throw Invalid("Input is a metadata module, not a managed assembly.");
            _ = DefinitionIdentity(metadata);
            foreach (var reference in metadata.AssemblyReferences)
                _ = ReferenceIdentity(metadata, reference);
            ValidateMethods(pe, metadata);
            return inspect(pe, metadata);
        }
        catch (Exception error) when (error is BadImageFormatException or ArgumentException or
            InvalidOperationException or IndexOutOfRangeException or OverflowException)
        {
            throw Invalid($"Malformed managed assembly metadata or PE image: {error.Message}", error);
        }
    }

    private static void ValidateImage(PEReader pe, int length)
    {
        var headers = pe.PEHeaders;
        var optional = headers.PEHeader;
        var clr = headers.CorHeader;
        if (optional is null || clr is null || !pe.HasMetadata)
            throw Invalid("Input must be a complete PE image with a CLR header and managed metadata.");
        if (optional.SizeOfHeaders <= 0 || optional.SizeOfHeaders > length)
            throw Invalid("PE headers extend outside the input image.");
        foreach (var section in headers.SectionHeaders)
        {
            if (section.PointerToRawData < 0 || section.SizeOfRawData < 0 ||
                (long)section.PointerToRawData + section.SizeOfRawData > length)
                throw Invalid($"PE section '{section.Name}' extends outside the input image.");
        }
        if ((clr.Flags & CorFlags.ILOnly) == 0)
            throw Invalid("Input is not IL-only; mixed/native assemblies are unsupported.");
        if ((clr.Flags & CorFlags.NativeEntryPoint) != 0)
            throw Invalid("Native CLR entry points are unsupported; submit managed IL.");
        if (Present(clr.ManagedNativeHeaderDirectory))
            throw Invalid("ReadyToRun or another managed native header is present; submit the original IL assembly.");
        if (Present(clr.CodeManagerTableDirectory) || Present(clr.VtableFixupsDirectory) ||
            Present(clr.ExportAddressTableJumpsDirectory))
            throw Invalid("Native CLR code-manager/export/vtable directories are unsupported in managed-il-v1.");
        ValidateDirectory(pe, clr.MetadataDirectory, "metadata");
        ValidateDirectory(pe, clr.ResourcesDirectory, "managed resources");
        ValidateDirectory(pe, clr.StrongNameSignatureDirectory, "strong-name signature");
    }

    private static bool Present(DirectoryEntry directory) => directory.RelativeVirtualAddress != 0 || directory.Size != 0;

    private static void ValidateDirectory(PEReader pe, DirectoryEntry directory, string label)
    {
        if (!Present(directory)) return;
        if (directory.RelativeVirtualAddress <= 0 || directory.Size <= 0 ||
            pe.GetSectionData(directory.RelativeVirtualAddress).Length < directory.Size)
            throw Invalid($"The {label} directory has an invalid RVA or extends outside its PE section.");
    }

    private static void ValidateMethods(PEReader pe, MetadataReader metadata)
    {
        // Touch type/member strings and row ownership as well as method bodies; PEReader alone is lazy.
        foreach (var typeHandle in metadata.TypeDefinitions)
        {
            var type = metadata.GetTypeDefinition(typeHandle);
            if (metadata.GetString(type.Name).Length == 0)
                throw Invalid("A type definition has an empty name.");
            _ = metadata.GetString(type.Namespace);
            foreach (var fieldHandle in type.GetFields())
            {
                var field = metadata.GetFieldDefinition(fieldHandle);
                _ = metadata.GetString(field.Name);
                var signature = metadata.GetBlobReader(field.Signature);
                if (signature.ReadSignatureHeader().Kind != SignatureKind.Field)
                    throw Invalid("A field has a malformed signature header.");
            }
        }
        foreach (var handle in metadata.MethodDefinitions)
        {
            var method = metadata.GetMethodDefinition(handle);
            var name = metadata.GetString(method.Name);
            if (name.Length == 0) throw Invalid("A method definition has an empty name.");
            if ((method.Attributes & MethodAttributes.PinvokeImpl) != 0 ||
                (method.ImplAttributes & MethodImplAttributes.InternalCall) != 0)
                throw Invalid($"Method '{name}' token 0x{MetadataTokens.GetToken(handle):X8} uses P/Invoke or InternalCall, unsupported in managed-il-v1.");
            if ((method.ImplAttributes & MethodImplAttributes.CodeTypeMask) != MethodImplAttributes.IL ||
                (method.ImplAttributes & (MethodImplAttributes.Unmanaged | MethodImplAttributes.ForwardRef)) != 0)
                throw Invalid($"Method '{name}' token 0x{MetadataTokens.GetToken(handle):X8} has a non-IL/unmanaged/forward implementation, unsupported in managed-il-v1.");
            var signature = metadata.GetBlobReader(method.Signature);
            var header = signature.ReadSignatureHeader();
            if (header.Kind != SignatureKind.Method)
                throw Invalid($"Method '{name}' token 0x{MetadataTokens.GetToken(handle):X8} has a malformed signature header.");
            if (header.IsGeneric && signature.ReadCompressedInteger() != method.GetGenericParameters().Count)
                throw Invalid($"Method '{name}' token 0x{MetadataTokens.GetToken(handle):X8} has inconsistent generic signature metadata.");
            var parameterCount = signature.ReadCompressedInteger();
            if (parameterCount < 0 || parameterCount > ushort.MaxValue || signature.RemainingBytes == 0)
                throw Invalid($"Method '{name}' token 0x{MetadataTokens.GetToken(handle):X8} has an invalid parameter count or missing return type.");
            foreach (var parameterHandle in method.GetParameters())
            {
                var parameter = metadata.GetParameter(parameterHandle);
                if (parameter.SequenceNumber > parameterCount)
                    throw Invalid($"Method '{name}' token 0x{MetadataTokens.GetToken(handle):X8} has a parameter row outside its signature.");
                _ = metadata.GetString(parameter.Name);
            }
            var isAbstract = (method.Attributes & MethodAttributes.Abstract) != 0;
            if (isAbstract)
            {
                if (method.RelativeVirtualAddress != 0)
                    throw Invalid($"Abstract method '{name}' token 0x{MetadataTokens.GetToken(handle):X8} unexpectedly contains a method body.");
                continue;
            }
            if (method.RelativeVirtualAddress <= 0)
                throw Invalid($"Managed method '{name}' token 0x{MetadataTokens.GetToken(handle):X8} is missing its IL body.");
            var body = pe.GetMethodBody(method.RelativeVirtualAddress);
            var code = body.GetILBytes();
            if (code is null || code.Length == 0 ||
                pe.GetSectionData(method.RelativeVirtualAddress).Length < body.Size)
                throw Invalid($"Method '{name}' token 0x{MetadataTokens.GetToken(handle):X8} has an empty or out-of-bounds IL body.");
            if (!body.LocalSignature.IsNil)
            {
                var locals = metadata.GetBlobReader(metadata.GetStandaloneSignature(body.LocalSignature).Signature);
                if (locals.ReadSignatureHeader().Kind != SignatureKind.LocalVariables)
                    throw Invalid($"Method '{name}' token 0x{MetadataTokens.GetToken(handle):X8} has an invalid local signature.");
            }
            foreach (var region in body.ExceptionRegions)
            {
                if (region.TryOffset < 0 || region.TryLength <= 0 ||
                    (long)region.TryOffset + region.TryLength > code.Length ||
                    region.HandlerOffset < 0 || region.HandlerLength <= 0 ||
                    (long)region.HandlerOffset + region.HandlerLength > code.Length ||
                    (region.Kind == ExceptionRegionKind.Filter &&
                        (region.FilterOffset < 0 || region.FilterOffset >= code.Length)))
                    throw Invalid($"Method '{name}' token 0x{MetadataTokens.GetToken(handle):X8} has an exception region outside its IL body.");
                if (region.Kind == ExceptionRegionKind.Catch)
                    ValidateTypeHandle(metadata, region.CatchType, name);
            }
        }
        var entry = pe.PEHeaders.CorHeader!.EntryPointTokenOrRelativeVirtualAddress;
        if (entry != 0)
        {
            var entryHandle = MetadataTokens.EntityHandle(entry);
            if (entryHandle.Kind != HandleKind.MethodDefinition ||
                MetadataTokens.GetRowNumber(entryHandle) > metadata.MethodDefinitions.Count)
                throw Invalid("Managed executable entry token does not identify a method in this assembly.");
        }
    }

    private static void ValidateTypeHandle(MetadataReader metadata, EntityHandle handle, string method)
    {
        switch (handle.Kind)
        {
            case HandleKind.TypeDefinition: _ = metadata.GetTypeDefinition((TypeDefinitionHandle)handle); break;
            case HandleKind.TypeReference: _ = metadata.GetTypeReference((TypeReferenceHandle)handle); break;
            case HandleKind.TypeSpecification: _ = metadata.GetTypeSpecification((TypeSpecificationHandle)handle); break;
            default: throw Invalid($"Method '{method}' has an invalid exception catch type.");
        }
        if (handle.IsNil) throw Invalid($"Method '{method}' has a missing exception catch type.");
    }

    private static string DefinitionIdentity(MetadataReader metadata)
    {
        var definition = metadata.GetAssemblyDefinition();
        return Identity(metadata.GetString(definition.Name), definition.Version,
            metadata.GetString(definition.Culture), definition.Flags, metadata.GetBlobBytes(definition.PublicKey));
    }

    private static string ReferenceIdentity(MetadataReader metadata, AssemblyReferenceHandle handle)
    {
        var reference = metadata.GetAssemblyReference(handle);
        return Identity(metadata.GetString(reference.Name), reference.Version,
            metadata.GetString(reference.Culture), reference.Flags, metadata.GetBlobBytes(reference.PublicKeyOrToken));
    }

    private static string Identity(string name, Version version, string culture, AssemblyFlags flags, byte[] key)
    {
        ValidateSimpleName(name);
        var identity = new AssemblyName
        {
            Name = name, Version = version, CultureName = culture,
            Flags = (AssemblyNameFlags)(flags & AssemblyFlags.Retargetable),
            ContentType = (flags & AssemblyFlags.WindowsRuntime) != 0
                ? AssemblyContentType.WindowsRuntime : AssemblyContentType.Default
        };
        if ((flags & AssemblyFlags.PublicKey) != 0)
        {
            if (key.Length < 16) throw Invalid($"Assembly '{name}' contains an invalid public-key blob.");
            // Identity calculation is not signature verification or proof of publisher trust.
            var hash = System.Security.Cryptography.SHA1.HashData(key);
            identity.SetPublicKeyToken(hash[^8..].Reverse().ToArray());
        }
        else
        {
            if (key.Length != 0 && key.Length != 8)
                throw Invalid($"Assembly '{name}' has a public-key token that is not eight bytes.");
            identity.SetPublicKeyToken(key);
        }
        return identity.FullName!;
    }

    private static void ValidateSimpleName(string name)
    {
        // The controlled builder uses simple names as reference/private DLL basenames.
        // Reject portable filesystem hazards before an identity can become an output path.
        if (string.IsNullOrWhiteSpace(name) || name.Length > 128 || name is "." or ".." ||
            name.EndsWith('.') || name.EndsWith(' ') ||
            name.Any(ch => char.IsControl(ch) || "/\\:<>\"|?*".Contains(ch)))
            throw Invalid("Assembly simple name must be a safe portable basename of 1-128 characters, with no path separators, control characters, reserved punctuation or trailing dot/space.");
        var stem = name.Split('.')[0].TrimEnd(' ');
        var reserved = stem.Equals("CON", StringComparison.OrdinalIgnoreCase) ||
            stem.Equals("PRN", StringComparison.OrdinalIgnoreCase) ||
            stem.Equals("AUX", StringComparison.OrdinalIgnoreCase) ||
            stem.Equals("NUL", StringComparison.OrdinalIgnoreCase) ||
            stem.Equals("CLOCK$", StringComparison.OrdinalIgnoreCase) ||
            stem.Equals("CONIN$", StringComparison.OrdinalIgnoreCase) ||
            stem.Equals("CONOUT$", StringComparison.OrdinalIgnoreCase) ||
            (stem.Length == 4 && (stem.StartsWith("COM", StringComparison.OrdinalIgnoreCase) ||
                stem.StartsWith("LPT", StringComparison.OrdinalIgnoreCase)) && "123456789¹²³".Contains(stem[3]));
        if (reserved) throw Invalid($"Assembly simple name '{name}' is a reserved Windows device basename.");
    }

    private static void ValidateEntryType(MetadataReader metadata, string entryType, string approvedContract, string? hostInterface = null)
    {
        if (string.IsNullOrWhiteSpace(entryType) || string.IsNullOrWhiteSpace(approvedContract))
            throw Invalid("Provide an entry type and the full approved contract assembly identity.");
        var contract = new AssemblyName(approvedContract);
        if (contract.Version is null)
            throw Invalid("The approved contract must specify its full assembly identity, including version.");
        approvedContract = contract.FullName!;
        TypeDefinitionHandle selected = default;
        foreach (var handle in metadata.TypeDefinitions)
        {
            var definition = metadata.GetTypeDefinition(handle);
            var name = metadata.GetString(definition.Name);
            var ns = metadata.GetString(definition.Namespace);
            if ((ns.Length == 0 ? name : ns + "." + name) != entryType) continue;
            if (!selected.IsNil) throw Invalid($"Entry type '{entryType}' has duplicate definitions.");
            selected = handle;
        }
        if (selected.IsNil) throw Invalid($"Entry type '{entryType}' was not found; nested entries are unsupported.");
        var type = metadata.GetTypeDefinition(selected);
        if ((type.Attributes & TypeAttributes.VisibilityMask) != TypeAttributes.Public ||
            (type.Attributes & (TypeAttributes.Abstract | TypeAttributes.Interface)) != 0 ||
            !type.GetDeclaringType().IsNil || type.GetGenericParameters().Count != 0)
            throw Invalid($"Entry '{entryType}' must be a public, nonabstract, nongeneric, nonnested class.");
        if (type.BaseType.Kind != HandleKind.TypeReference)
            throw Invalid($"Entry '{entryType}' must directly extend System.Object; inherited entry implementations are unsupported.");
        var baseType = metadata.GetTypeReference((TypeReferenceHandle)type.BaseType);
        if (metadata.GetString(baseType.Namespace) != "System" || metadata.GetString(baseType.Name) != "Object" ||
            baseType.ResolutionScope.Kind != HandleKind.AssemblyReference)
            throw Invalid($"Entry '{entryType}' must directly extend System.Object; inherited entry implementations are unsupported.");
        var constructors = type.GetMethods().Where(handle =>
        {
            var method = metadata.GetMethodDefinition(handle);
            if (metadata.GetString(method.Name) != ".ctor" || !PublicInstance(method)) return false;
            var signature = metadata.GetBlobReader(method.Signature);
            var header = signature.ReadSignatureHeader();
            if (header.IsGeneric) return false;
            return signature.ReadCompressedInteger() == 0;
        }).ToArray();
        if (constructors.Length != 1)
            throw Invalid($"Entry '{entryType}' needs exactly one public instance parameterless constructor.");
        var constructor = metadata.GetMethodDefinition(constructors[0]);
        if ((constructor.Attributes & (MethodAttributes.SpecialName | MethodAttributes.RTSpecialName)) !=
            (MethodAttributes.SpecialName | MethodAttributes.RTSpecialName))
            throw Invalid("Entry constructor is missing required constructor metadata flags.");
        ValidateSignature(metadata, constructor, approvedContract, null, false);
        if (hostInterface is null || hostInterface == "RuneCLR.IMapContext")
        {
            var matchingInterfaces = type.GetInterfaceImplementations().Count(handle =>
                IsContractType(metadata, metadata.GetInterfaceImplementation(handle).Interface, "IMapScript", approvedContract));
            if (matchingInterfaces != 1)
                throw Invalid($"Entry '{entryType}' must directly implement RuneCLR.IMapScript from '{approvedContract}'.");
            ValidateCallback(metadata, type, "OnStart", approvedContract, "IMapContext", false);
            ValidateCallback(metadata, type, "OnTick", approvedContract, "MapTick", true);
            ValidateCallback(metadata, type, "OnStop", approvedContract, null, false);
        }
    }

    private static bool PublicInstance(MethodDefinition method) =>
        (method.Attributes & MethodAttributes.MemberAccessMask) == MethodAttributes.Public &&
        (method.Attributes & (MethodAttributes.Static | MethodAttributes.Abstract)) == 0 &&
        method.GetGenericParameters().Count == 0;

    private static void ValidateCallback(MetadataReader metadata, TypeDefinition type, string name,
        string approvedContract, string? parameter, bool valueType)
    {
        var candidates = type.GetMethods().Where(handle =>
            metadata.GetString(metadata.GetMethodDefinition(handle).Name) == name).ToArray();
        if (candidates.Length != 1 || !PublicInstance(metadata.GetMethodDefinition(candidates[0])))
            throw Invalid($"Entry callback '{name}' must be one public nongeneric instance method; explicit/inherited/overloaded callbacks are unsupported.");
        ValidateSignature(metadata, metadata.GetMethodDefinition(candidates[0]), approvedContract, parameter, valueType);
    }

    private static void ValidateSignature(MetadataReader metadata, MethodDefinition method, string contract,
        string? parameter, bool valueType)
    {
        var signature = metadata.GetBlobReader(method.Signature);
        var header = signature.ReadSignatureHeader();
        if (header.Kind != SignatureKind.Method || header.CallingConvention != SignatureCallingConvention.Default ||
            !header.IsInstance || header.HasExplicitThis || header.IsGeneric ||
            signature.ReadCompressedInteger() != (parameter is null ? 0 : 1) || signature.ReadByte() != 0x01)
            throw Invalid($"Entry method '{metadata.GetString(method.Name)}' has an unsupported instance/void/parameter signature.");
        if (parameter is not null)
        {
            // ECMA-335 ELEMENT_TYPE_CLASS/VALUETYPE followed by a TypeDefOrRef-coded index.
            var code = signature.ReadByte();
            var encoded = signature.ReadCompressedInteger();
            if (code != (valueType ? 0x11 : 0x12) || encoded <= 0 || (encoded & 3) != 1 ||
                !IsContractType(metadata, MetadataTokens.TypeReferenceHandle(encoded >> 2), parameter, contract))
                throw Invalid($"Entry callback parameter must be RuneCLR.{parameter} from the approved contract assembly.");
        }
        if (signature.RemainingBytes != 0)
            throw Invalid($"Entry method '{metadata.GetString(method.Name)}' has trailing signature data.");
    }

    private static bool IsContractType(MetadataReader metadata, EntityHandle handle, string name, string contract)
    {
        if (handle.Kind != HandleKind.TypeReference || handle.IsNil) return false;
        var type = metadata.GetTypeReference((TypeReferenceHandle)handle);
        return metadata.GetString(type.Namespace) == "RuneCLR" && metadata.GetString(type.Name) == name &&
            type.ResolutionScope.Kind == HandleKind.AssemblyReference &&
            string.Equals(ReferenceIdentity(metadata, (AssemblyReferenceHandle)type.ResolutionScope), contract, StringComparison.Ordinal);
    }

    private static InvalidDataException Invalid(string reason, Exception? inner = null) => new(reason, inner);
}
